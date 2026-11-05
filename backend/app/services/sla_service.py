import json
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from ..redis_client import get_redis_client
from ..database import SessionLocal
from ..models import AuditEvent, Job

logger = logging.getLogger(__name__)

def make_utc_aware(dt: datetime) -> datetime:
    if dt is None:
        return None
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except ValueError:
            return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class SLAService:
    def __init__(self, redis_client=None):
        self.redis = redis_client or get_redis_client()

    def start_sla_timer(self, job_id: str, deadline: datetime) -> None:
        if not self.redis:
            return
        
        now = datetime.now(timezone.utc)
        deadline_aware = make_utc_aware(deadline)
        remaining_seconds = max(0, (deadline_aware - now).total_seconds())
        
        state = {
            "job_id": str(job_id),
            "sla_deadline": deadline_aware.isoformat(),
            "status": "active",
            "started_at": now.isoformat(),
            "paused_at": None,
            "remaining_seconds": remaining_seconds,
            "elapsed_percentage": 0.0,
            "is_breached": False,
            "is_critical": False,
            "milestone_reached": None
        }
        
        key = f"sla:{job_id}"
        try:
            ttl = int(state["remaining_seconds"]) + 86400  # deadline + 1 day buffer
            self.redis.setex(key, ttl, json.dumps(state))
            logger.info(f"Started SLA timer for job {job_id} (deadline: {state['sla_deadline']}, TTL: {ttl})")
        except Exception as e:
            logger.error(f"Failed to start SLA timer in Redis: {e}")

    def pause_sla_timer(self, job_id: str) -> None:
        if not self.redis:
            return
            
        key = f"sla:{job_id}"
        try:
            raw = self.redis.get(key)
            if not raw:
                logger.warning(f"Pause SLA timer failed: no active SLA found in Redis for job {job_id}")
                return
                
            state = json.loads(raw)
            if state["status"] == "paused":
                return
                
            now = datetime.now(timezone.utc)
            state["status"] = "paused"
            state["paused_at"] = now.isoformat()
            
            # Recalculate remaining seconds frozen at pause time
            deadline = make_utc_aware(state["sla_deadline"])
            state["remaining_seconds"] = max(0, (deadline - now).total_seconds())
            
            self.redis.setex(key, 86400 * 7, json.dumps(state))  # Keep paused SLA state for 7 days
            logger.info(f"Paused SLA timer for job {job_id} at {state['paused_at']}")
        except Exception as e:
            logger.error(f"Failed to pause SLA timer in Redis: {e}")

    def resume_sla_timer(self, job_id: str) -> None:
        if not self.redis:
            return
            
        key = f"sla:{job_id}"
        try:
            raw = self.redis.get(key)
            if not raw:
                logger.warning(f"Resume SLA timer failed: no active SLA found in Redis for job {job_id}")
                return
                
            state = json.loads(raw)
            if state["status"] == "active":
                return
                
            now = datetime.now(timezone.utc)
            paused_at = make_utc_aware(state["paused_at"])
            pause_duration = (now - paused_at).total_seconds()
            
            # Adjust deadline forward by duration of pause
            old_deadline = make_utc_aware(state["sla_deadline"])
            new_deadline = old_deadline + (now - paused_at)
            
            state["status"] = "active"
            state["sla_deadline"] = new_deadline.isoformat()
            state["paused_at"] = None
            state["remaining_seconds"] = max(0, (new_deadline - now).total_seconds())
            
            ttl = int(state["remaining_seconds"]) + 86400
            self.redis.setex(key, ttl, json.dumps(state))
            logger.info(f"Resumed SLA timer for job {job_id}. Adjusted deadline from {old_deadline.isoformat()} to {new_deadline.isoformat()} (Pause duration: {pause_duration}s)")
        except Exception as e:
            logger.error(f"Failed to resume SLA timer in Redis: {e}")

    def get_sla_state(self, job_id: str) -> Optional[Dict[str, Any]]:
        if not self.redis:
            return None
            
        key = f"sla:{job_id}"
        try:
            raw = self.redis.get(key)
            if not raw:
                # Fallback to Database
                db = SessionLocal()
                try:
                    job = db.query(Job).filter(Job.id == int(job_id) if str(job_id).isdigit() else Job.id == job_id).first()
                    if job and job.sla_deadline and job.status not in ("COMPLETED", "CLOSED", "CANCELLED"):
                        # Re-initialize SLA timer
                        self.start_sla_timer(str(job.id), job.sla_deadline)
                        raw = self.redis.get(key)
                    else:
                        return None
                finally:
                    db.close()
                
            if not raw:
                return None
                
            state = json.loads(raw)
            now = datetime.now(timezone.utc)
            deadline = make_utc_aware(state["sla_deadline"])
            started_at = make_utc_aware(state["started_at"])
            
            if state["status"] == "active":
                state["remaining_seconds"] = max(0, (deadline - now).total_seconds())
                
                # Elapsed percentage calculation
                total_duration = (deadline - started_at).total_seconds()
                if total_duration > 0:
                    elapsed = (now - started_at).total_seconds()
                    state["elapsed_percentage"] = min(100.0, max(0.0, (elapsed / total_duration) * 100.0))
                else:
                    state["elapsed_percentage"] = 100.0
            else:
                # If paused, remaining time and percentage are frozen as of paused_at
                paused_at = make_utc_aware(state["paused_at"])
                state["remaining_seconds"] = max(0, (deadline - paused_at).total_seconds())
                
                total_duration = (deadline - started_at).total_seconds()
                if total_duration > 0:
                    elapsed = (paused_at - started_at).total_seconds()
                    state["elapsed_percentage"] = min(100.0, max(0.0, (elapsed / total_duration) * 100.0))
                else:
                    state["elapsed_percentage"] = 100.0

            state["is_breached"] = state["remaining_seconds"] <= 0
            state["is_critical"] = state["remaining_seconds"] < 900 and not state["is_breached"]
            
            # Milestone alerts check
            self._check_and_log_milestones(state)
            
            # Save state back to Redis
            if state["status"] == "active":
                ttl = int(state["remaining_seconds"]) + 86400
                self.redis.setex(key, ttl, json.dumps(state))
            else:
                self.redis.setex(key, 86400 * 7, json.dumps(state))
                
            return state
        except Exception as e:
            logger.error(f"Failed to get SLA state from Redis: {e}")
            return None

    def clear_sla_timer(self, job_id: str) -> None:
        if not self.redis:
            return
            
        key = f"sla:{job_id}"
        try:
            self.redis.delete(key)
            logger.info(f"Cleared SLA timer for job {job_id}")
        except Exception as e:
            logger.error(f"Failed to clear SLA timer from Redis: {e}")

    def _check_and_log_milestones(self, state: dict) -> None:
        elapsed = state["elapsed_percentage"]
        milestone = state.get("milestone_reached")
        job_id = state["job_id"]
        
        target_milestone = None
        message = ""
        
        if elapsed >= 100.0 and milestone != "100%":
            target_milestone = "100%"
            message = "100% SLA milestone breached"
        elif elapsed >= 75.0 and elapsed < 100.0 and milestone not in ("75%", "100%"):
            target_milestone = "75%"
            message = "75% SLA milestone elapsed"
        elif elapsed >= 50.0 and elapsed < 75.0 and milestone not in ("50%", "75%", "100%"):
            target_milestone = "50%"
            message = "50% SLA milestone elapsed"
            
        if target_milestone:
            state["milestone_reached"] = target_milestone
            logger.warning(f"SLA Milestone Alert: Job {job_id} reached {target_milestone} of SLA deadline. {message}.")
            
            db = SessionLocal()
            try:
                # Add SLA alert to AuditEvent
                job = db.query(Job).filter(Job.id == int(job_id) if str(job_id).isdigit() else Job.id == job_id).first()
                audit = AuditEvent(
                    event_type="SLA_MILESTONE",
                    tech_id=str(job.assigned_technician_id) if job and job.assigned_technician_id else "system",
                    tenant_id=job.tenant_id if job else "system",
                    old_status=job.status if job else None,
                    new_status=job.status if job else None,
                    reason=message,
                    job_id=job_id,
                    details={
                        "elapsed_percentage": elapsed,
                        "remaining_seconds": state["remaining_seconds"],
                        "milestone": target_milestone
                    }
                )
                db.add(audit)
                db.commit()
            except Exception as e:
                logger.error(f"Failed to write SLA Milestone event to DB: {e}")
                db.rollback()
            finally:
                db.close()

# ---------------------------------------------------------------------------
# High-Priority Queue Management (Story: Create high-priority queue)
# ---------------------------------------------------------------------------

from app.celery_app import (
    HIGH_PRIORITY_QUEUE,
    HIGH_PRIORITY_ROUTING_KEY,
    PRIORITY_QUEUE,
    PRIORITY_ROUTING_KEY,
    get_high_priority_queue_config,
    create_high_priority_queue,
    CreateHighPriorityQueue,
    Create_high_priority_queue,
    CreatePriorityQueue,
    create_priority_queue,
    Create_priority_queue,
)

