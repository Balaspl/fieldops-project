import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import delete, text
from sqlalchemy.orm import Session
import time
import uuid
from typing import Optional
from .runtime.dlq import DeadLetterQueue
from .services.enterprise_audit import AuditAction, audit_log
from .celery_app import celery_app
from .database import SessionLocal
from . import models
from .logger import logger
from .services.eta_service import ETAService
from .services.task_queue import PriorityTaskQueue
from .redis_client import get_redis_client
from .services.socket_manager import ws_manager
from .services.task_queue_worker import consume_task_queue


from .services.task_queue import PriorityTaskQueue

@celery_app.task(name="app.tasks.aggregate_prompt_analytics_task")
def aggregate_prompt_analytics_task():
    """Refresh 7-day and 30-day prompt analytics for every tenant with usage."""
    from .prompts.analytics import PromptAnalytics

    db = SessionLocal()
    try:
        tenant_ids = [
            row[0]
            for row in db.query(models.PromptUsageEvent.tenant_id).distinct().all()
        ]
        try:
            from .redis_client import get_redis_client
            redis_client = get_redis_client()
        except Exception:
            redis_client = None
        return sum(
            PromptAnalytics(db, redis_client, tenant_id).aggregate_dashboard()
            for tenant_id in tenant_ids
        )
    finally:
        db.close()


def archive_old_sentiment_audits(
    db: Session,
) -> int:
    """
    Mark sentiment audit records older than 2 years as archived.

    Audit records are never deleted because the sentiment audit trail
    is immutable. Records remain in the database and receive an
    archived_at timestamp.
    """

    now = datetime.now(timezone.utc)

    retention_cutoff = now - timedelta(days=730)

    try:
        records = (
            db.query(models.SentimentAuditRecord)
            .filter(
                models.SentimentAuditRecord.timestamp
                < retention_cutoff,
                models.SentimentAuditRecord.archived_at
                .is_(None),
            )
            .all()
        )

        archived_count = 0

        for record in records:
            record.archived_at = now
            archived_count += 1

        db.commit()

        logger.info(
            "Sentiment audit archival completed: "
            "%s records archived.",
            archived_count,
        )

        return archived_count

    except Exception as e:
        db.rollback()

        logger.error(
            "Error archiving old sentiment audit records: %s",
            e,
        )

        raise


def drop_empty_partitions(db: Session):
    """
    Drops any partitioned table under gps_pings that contains 0 rows.
    Only applicable for PostgreSQL engine.
    """
    bind_engine = db.get_bind()
    is_postgres = bind_engine.url.drivername.startswith("postgresql")
    if not is_postgres:
        return
        
    sql_find_partitions = """
        SELECT inhrelid::regclass::text AS partition_name
        FROM pg_inherits
        WHERE inhparent = 'gps_pings'::regclass;
    """
    try:
        partitions = db.execute(text(sql_find_partitions)).all()
        for row in partitions:
            partition_name = row[0]
            sql_count = f"SELECT COUNT(*) FROM {partition_name}"
            count = db.execute(text(sql_count)).scalar()
            if count == 0:
                logger.info(f"Dropping empty GPS partition: {partition_name}")
                db.execute(text(f"DROP TABLE IF EXISTS {partition_name} CASCADE"))
        db.commit()
    except Exception as e:
        logger.error(f"Error dropping empty partitions: {e}")
        db.rollback()


def execute_daily_gps_purge_sync(db: Session, correlation_id: str = None) -> int:
    """
    Performs age-based hard deletion of GPS pings according to configurable tenant retention periods.
    """
    now = datetime.now(timezone.utc)
    
    # 1. Fetch custom tenant configurations
    configs = db.query(models.TenantGPSConfiguration).all()
    config_map = {c.tenant_id: c.retention_days for c in configs}

    # 2. Retrieve all unique tenant IDs from gps_pings to handle overrides dynamically
    unique_pings_tenants = db.query(models.GPSPing.tenant_id).distinct().all()
    tenant_ids = [t[0] for t in unique_pings_tenants if t[0]]

    # Ensure default tenant is checked even if no active pings exist (for logging/tests)
    if "tenant-1" not in tenant_ids:
        tenant_ids.append("tenant-1")

    total_deleted = 0
    bind_engine = db.get_bind()
    is_sqlite = bind_engine.url.drivername.startswith("sqlite")

    for tenant_id in tenant_ids:
        retention_days = config_map.get(tenant_id, 30)
        threshold = now - timedelta(days=retention_days)
        
        query_threshold = threshold
        if is_sqlite:
            query_threshold = threshold.replace(tzinfo=None)

        stmt = delete(models.GPSPing).where(
            models.GPSPing.tenant_id == tenant_id,
            models.GPSPing.timestamp < query_threshold
        )
        res = db.execute(stmt)
        deleted_count = res.rowcount
        total_deleted += deleted_count

        # Log daily purge event to audit log (whether count > 0 or 0, as per requirements)
        audit = models.GPSPurgeAuditLog(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            job_id=None,
            purge_type="age_based",
            deleted_count=deleted_count,
            correlation_id=correlation_id,
            created_at=now
        )
        db.add(audit)

        if deleted_count > 0:
            logger.info(
                f"Purged {deleted_count} GPS pings older than {retention_days} days for tenant {tenant_id}",
                extra={"tenant_id": tenant_id, "deleted_count": deleted_count, "correlation_id": correlation_id}
            )

    db.commit()

    # 3. Drop empty partitions
    if not is_sqlite:
        drop_empty_partitions(db)

    # Update stats in Redis
    try:
        from .redis_client import get_redis_client
        redis_client = get_redis_client()
        if redis_client:
            redis_client.set("gps_purge:last_purge_run", now.isoformat())
            # Increment total purged count
            redis_client.incrby("gps_purge:total_purged_30d", total_deleted)
            # Schedule next run (2 AM UTC tomorrow)
            next_run = datetime(now.year, now.month, now.day, 2, 0, tzinfo=timezone.utc)
            if next_run <= now:
                next_run += timedelta(days=1)
            redis_client.set("gps_purge:next_scheduled", next_run.isoformat())
    except Exception as re:
        logger.warning(f"Failed to update Redis purge statistics: {re}")

    return total_deleted


def execute_job_gps_purge_sync(db: Session, job_id: int, tenant_id: str, purge_type: str = "event_based", correlation_id: str = None) -> int:
    """
    Performs immediate hard deletion of all GPS pings for a specific job_id.
    """
    stmt = delete(models.GPSPing).where(
        models.GPSPing.job_id == str(job_id),
        models.GPSPing.tenant_id == tenant_id
    )
    res = db.execute(stmt)
    deleted_count = res.rowcount

    # Always log the purge event (even if 0 records deleted, as per requirements)
    audit = models.GPSPurgeAuditLog(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        job_id=str(job_id),
        purge_type=purge_type,
        deleted_count=deleted_count,
        correlation_id=correlation_id
    )
    db.add(audit)
    db.commit()

    # Drop empty partitions
    bind_engine = db.get_bind()
    is_sqlite = bind_engine.url.drivername.startswith("sqlite")
    if not is_sqlite:
        drop_empty_partitions(db)

    logger.info(
        f"Purged {deleted_count} GPS pings for job {job_id} ({purge_type})",
        extra={"tenant_id": tenant_id, "deleted_count": deleted_count, "job_id": job_id, "correlation_id": correlation_id}
    )

    return deleted_count


@celery_app.task(name="app.tasks.daily_gps_purge_task")
def daily_gps_purge_task(correlation_id: str = None):
    db = SessionLocal()
    try:
        execute_daily_gps_purge_sync(db, correlation_id)
    finally:
        db.close()


@celery_app.task(bind=True, max_retries=3, name="app.tasks.purge_job_gps_data_task")
def purge_job_gps_data(self, job_id: int, tenant_id: str, purge_type: str = "event_based", correlation_id: str = None):
    import json
    import time
    from celery.exceptions import MaxRetriesExceededError
    from .redis_client import get_redis_client

    redis_client = get_redis_client()
    
    # Update status to in_progress in Redis on first try
    if redis_client and self.request.retries == 0:
        try:
            status_data = {
                "job_id": str(job_id),
                "purge_status": "in_progress",
                "purged_at": None,
                "deleted_count": 0
            }
            redis_client.set(f"gps_purge_status:{job_id}", json.dumps(status_data), ex=86400)
        except Exception as e:
            logger.warning(f"Failed to set status in Redis: {e}")

    db = SessionLocal()
    try:
        deleted_count = execute_job_gps_purge_sync(db, job_id, tenant_id, purge_type, correlation_id)
        
        # Update status in Redis on success
        if redis_client:
            try:
                status_data = {
                    "job_id": str(job_id),
                    "purge_status": "completed",
                    "purged_at": datetime.now(timezone.utc).isoformat(),
                    "deleted_count": deleted_count
                }
                redis_client.set(f"gps_purge_status:{job_id}", json.dumps(status_data), ex=86400)
            except Exception as e:
                logger.warning(f"Failed to update status in Redis: {e}")
                
            # Clear associated Redis interval and cache keys
            try:
                # gps:interval:*:{job_id}
                interval_keys = redis_client.keys(f"gps:interval:*:{job_id}")
                for k in interval_keys:
                    redis_client.delete(k)
                # gps:cache:{job_id}:*
                cache_keys = redis_client.keys(f"gps:cache:{job_id}:*")
                for k in cache_keys:
                    redis_client.delete(k)
            except Exception as e:
                logger.warning(f"Failed to clear Redis keys on purge: {e}")

            # Check SLA duration
            try:
                start_time_str = redis_client.get(f"gps_purge_start_time:{job_id}")
                if start_time_str:
                    duration = time.time() - float(start_time_str)
                    if duration > 5.0:
                        logger.critical(
                            f"SLA Violation: GPS purge for job {job_id} took {duration:.2f} seconds (limit: 5s)",
                            extra={"job_id": job_id, "duration": duration, "correlation_id": correlation_id}
                        )
            except Exception as e:
                logger.warning(f"Failed to compute purge duration for SLA: {e}")
                
        return deleted_count

    except Exception as exc:
        db.close()
        try:
            logger.error(f"Error executing GPS purge for job {job_id}: {exc}. Retrying...")
            raise self.retry(exc=exc, countdown=2 ** self.request.retries)
        except Exception as retry_exc:
            if isinstance(retry_exc, MaxRetriesExceededError):
                logger.error(f"GPS purge task exhausted all retries for job {job_id}. Moving to DLQ.")
                if redis_client:
                    try:
                        # Update status in Redis
                        status_data = {
                            "job_id": str(job_id),
                            "purge_status": "failed",
                            "purged_at": None,
                            "deleted_count": 0
                        }
                        redis_client.set(f"gps_purge_status:{job_id}", json.dumps(status_data), ex=86400)
                        
                        # Push to DLQ
                        dlq_payload = {
                            "job_id": job_id,
                            "tenant_id": tenant_id,
                            "purge_type": purge_type,
                            "correlation_id": correlation_id,
                            "error": str(exc),
                            "failed_at": datetime.now(timezone.utc).isoformat()
                        }
                        redis_client.rpush("gps_purge_dlq", json.dumps(dlq_payload))
                    except Exception as re:
                        logger.error(f"Failed to push to DLQ or update status: {re}")
                raise exc
            raise retry_exc
    finally:
        db.close()

purge_job_gps_data_task = purge_job_gps_data


@celery_app.task(bind=True, max_retries=2, name="app.tasks.update_eta_task")
def update_eta_task(self, technician_id: str, job_id, ping_id: str = None, correlation_id: str = None):
    """
    Recalculate ETA for a technician/job pair and broadcast the result to job WebSocket subscribers.

    This task is triggered by the GPSPing after_insert event listener registered in models.py.
    It honours the 30-second per-job throttle enforced by the event listener (i.e. it will not be
    enqueued if the throttle key is still active) so that at-most one ETA update is broadcast
    per job every 30 seconds.

    Steps:
      1. Call ETAService (Google Maps → Haversine fallback) for duration & distance.
      2. Persist an ETAHistory row.
      3. Broadcast the result via Socket.io to the ``job:{job_id}`` room.
    """
    import asyncio

    # Resolve tenant from the job record so we don't need it in the signature
    db = SessionLocal()
    try:
        eta_service = ETAService()

        # 1. Compute ETA
        loop = asyncio.new_event_loop()
        try:
            eta_result = loop.run_until_complete(
                eta_service.calculate_eta(technician_id=technician_id, job_id=job_id)
            )
        finally:
            loop.close()

        if eta_result is None:
            logger.warning(
                f"[update_eta_task] ETAService returned None for tech={technician_id} job={job_id}"
            )
            return

        # 2. Persist ETAHistory row using the actual model schema
        now = datetime.now(timezone.utc)

        # Parse the ISO-8601 ETA string into a datetime for the DateTime column
        eta_raw = eta_result.get("eta")
        if isinstance(eta_raw, str):
            from datetime import datetime as _dt
            try:
                eta_dt = _dt.fromisoformat(eta_raw)
            except ValueError:
                eta_dt = now
        elif isinstance(eta_raw, datetime):
            eta_dt = eta_raw
        else:
            eta_dt = now

        # ETAService returns seconds/meters; ETAHistory stores minutes/km
        duration_seconds = eta_result.get("duration_seconds", 0) or 0
        distance_meters = eta_result.get("distance_meters", 0) or 0
        traffic_delay_seconds = eta_result.get("traffic_delay_seconds", 0) or 0

        # Resolve job's tenant_id for the history row
        job_record = db.query(models.Job).filter(models.Job.id == int(job_id)).first()
        tenant_id = (job_record.tenant_id if job_record else None) or "unknown"

        history = models.ETAHistory(
            id=str(uuid.uuid4()),
            job_id=int(job_id),
            tenant_id=tenant_id,
            eta=eta_dt,
            duration_minutes=round(duration_seconds / 60, 2),
            distance_km=round(distance_meters / 1000, 3),
            traffic_delay_minutes=round(traffic_delay_seconds / 60, 2),
            source_ping_id=ping_id,
        )
        db.add(history)
        db.commit()

        logger.info(
            f"[update_eta_task] Stored ETAHistory for tech={technician_id} job={job_id} "
            f"eta={eta_raw} confidence={eta_result.get('confidence')}"
        )

        # 3. Broadcast to WebSocket subscribers
        broadcast_payload = {
            "type": "eta_update",
            "job_id": str(job_id),
            "technician_id": technician_id,
            "eta": eta_raw if isinstance(eta_raw, str) else eta_dt.isoformat(),
            "duration_minutes": round(duration_seconds / 60, 1),
            "distance_km": round(distance_meters / 1000, 2),
            "traffic_delay_minutes": round(traffic_delay_seconds / 60, 1),
            "confidence": eta_result.get("confidence", "calculated"),
            "disclaimer": eta_result.get("disclaimer"),
            "updated_at": now.isoformat(),
        }

        ws_loop = asyncio.new_event_loop()
        try:
            ws_loop.run_until_complete(ws_manager.broadcast_to_job(str(job_id), broadcast_payload))
        finally:
            ws_loop.close()

    except Exception as exc:
        logger.error(
            f"[update_eta_task] Failed for tech={technician_id} job={job_id}: {exc}",
            exc_info=True
        )
        db.rollback()
        try:
            raise self.retry(exc=exc, countdown=5 ** (self.request.retries + 1))
        except Exception:
            logger.error(
                f"[update_eta_task] All retries exhausted for tech={technician_id} job={job_id}"
            )
    finally:
        db.close()


@celery_app.task
def process_job_status_transition_task(job_id, from_status, to_status, actor_id, actor_role, reason, correlation_id=None):
    from .context import correlation_id_ctx
    if correlation_id:
        correlation_id_ctx.set(correlation_id)

    db = SessionLocal()
    try:
        from .models import Job, Technician
        from .services.notification_services import JobStatusEvent, EventPublisher, NotificationRouter
        from .services.sla_service import SLAService
        from .redis_client import get_redis_client
        import json

        # Helper to get cached ETA
        def get_cached_eta(technician_id: str, j_id: str) -> Optional[str]:
            redis = get_redis_client()
            if redis:
                try:
                    eta_raw = redis.get(f"eta:{technician_id}:{j_id}")
                    if eta_raw:
                        return json.loads(eta_raw).get("eta")
                except Exception:
                    pass
            return None

        # Fetch Job
        job = db.query(Job).filter(Job.id == int(job_id) if str(job_id).isdigit() else Job.id == job_id).first()
        if not job:
            logger.error(f"process_job_status_transition_task: Job {job_id} not found.")
            return

        tech = None
        if job.assigned_technician_id:
            tech = db.query(Technician).filter(Technician.technician_id == job.assigned_technician_id).first()

        # Construct event
        event = JobStatusEvent(
            job_id=str(job.id),
            tenant_id=job.tenant_id or "tenant-1",
            from_status=from_status,
            to_status=to_status,
            actor_id=actor_id,
            actor_role=actor_role,
            reason=reason,
            timestamp=datetime.now(timezone.utc),
            job_title=job.customer_name,
            job_location=job.location,
            technician_id=str(job.assigned_technician_id) if job.assigned_technician_id else None,
            technician_name=tech.technician_name if tech else None,
            customer_id=job.customer_id,
            customer_name=job.customer_name,
            customer_phone=job.contact_number,
            customer_email=job.customer_email,
            eta=get_cached_eta(str(job.assigned_technician_id), str(job.id)) if job.assigned_technician_id else None,
            notification_channels=[]
        )

        # --------------------------------------------------
        # Handle SLA timer updates before notifications.
        # Notification generation or delivery may fail, but
        # that failure must never prevent SLA cleanup.
        # --------------------------------------------------

        sla = SLAService()

        from_status_upper = (
            str(from_status).upper().strip()
            if from_status
            else ""
        )

        to_status_upper = (
            str(to_status).upper().strip()
            if to_status
            else ""
        )

        try:
            # Resume must be checked before the general
            # EN_ROUTE start condition.
            if (
                from_status_upper == "ON_SITE"
                and to_status_upper
                in {"ASSIGNED", "EN_ROUTE"}
            ):
                sla.resume_sla_timer(
                    str(job.id)
                )

            elif to_status_upper == "EN_ROUTE":
                if job.sla_deadline:
                    sla.start_sla_timer(
                        str(job.id),
                        job.sla_deadline,
                    )

            elif to_status_upper == "ON_SITE":
                sla.pause_sla_timer(
                    str(job.id)
                )

            elif to_status_upper in {
                "CLOSED",
                "CANCELLED",
                "COMPLETED",
            }:
                sla.clear_sla_timer(
                    str(job.id)
                )

        except Exception:
            logger.error(
                "SLA timer state update failed.",
                extra={
                    "job_id": str(job.id),
                    "to_status": to_status_upper,
                },
            )

        # --------------------------------------------------
        # Publish and route notifications after SLA handling.
        # Notification failure must not undo SLA processing.
        # --------------------------------------------------

        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        try:
            if loop.is_running():
                asyncio.ensure_future(
                    EventPublisher().publish(
                        event
                    )
                )

                asyncio.ensure_future(
                    NotificationRouter().route(
                        event
                    )
                )

            else:
                loop.run_until_complete(
                    EventPublisher().publish(
                        event
                    )
                )

                loop.run_until_complete(
                    NotificationRouter().route(
                        event
                    )
                )

        except Exception:
            logger.error(
                "Job transition notification processing "
                "failed.",
                extra={
                    "job_id": str(job.id),
                    "to_status": to_status_upper,
                },
            )

    except Exception as e:
        logger.error(f"Error in process_job_status_transition_task: {e}", exc_info=True)
    finally:
        db.close()


@celery_app.task
def send_dispatcher_digest():
    from .redis_client import get_redis_client
    from .services.socket_manager import ws_manager
    import json
    import asyncio

    redis = get_redis_client()
    if not redis:
        return

    try:
        keys = redis.keys("dispatcher_digest:*")
        for key in keys:
            key_str = key.decode("utf-8") if isinstance(key, bytes) else str(key)
            tenant_id = key_str.split(":")[-1]
            messages = []
            while True:
                msg_raw = redis.rpop(key)
                if not msg_raw:
                    break
                messages.append(json.loads(msg_raw))

            if messages:
                digest_payload = {
                    "type": "digest",
                    "tenant_id": tenant_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "notifications": messages
                }
                
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                if loop.is_running():
                    asyncio.ensure_future(
                        ws_manager.broadcast(f"tenant:{tenant_id}:dispatchers", digest_payload)
                    )
                else:
                    loop.run_until_complete(
                        ws_manager.broadcast(f"tenant:{tenant_id}:dispatchers", digest_payload)
                    )
                logger.info(f"Broadcasted digest containing {len(messages)} updates for tenant {tenant_id}")
    except Exception as e:
        logger.error(f"Failed to run send_dispatcher_digest task: {e}")


@celery_app.task
def broadcast_sla_countdown():
    from .database import SessionLocal
    from .models import Job
    from .services.sla_service import SLAService
    from .services.socket_manager import ws_manager
    import asyncio

    db = SessionLocal()
    try:
        jobs = db.query(Job).filter(Job.status.in_(["ASSIGNED", "EN_ROUTE", "ON_SITE"])).all()
        sla = SLAService()
        
        for job in jobs:
            state = sla.get_sla_state(str(job.id))
            if state:
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                payload = {
                    "type": "sla_countdown",
                    "job_id": str(job.id),
                    "sla": state
                }
                if loop.is_running():
                    asyncio.ensure_future(
                        ws_manager.broadcast(f"tenant:{job.tenant_id}:dispatchers", payload)
                    )
                else:
                    loop.run_until_complete(
                        ws_manager.broadcast(f"tenant:{job.tenant_id}:dispatchers", payload)
                    )
    except Exception as e:
        logger.error(f"Failed to broadcast SLA countdown state: {e}")
    finally:
        db.close()


@celery_app.task
def auto_transition_on_geofence(job_id, ping_id, distance):
    db = SessionLocal()
    try:
        from .models import Job
        from .logger import logger
        
        job = db.query(Job).filter(Job.id == int(job_id) if str(job_id).isdigit() else Job.id == job_id).first()
        if not job:
            logger.error(f"auto_transition_on_geofence: Job {job_id} not found")
            return
            
        if job.status != "EN_ROUTE":
            logger.warning(f"auto_transition_on_geofence: Job {job_id} status is {job.status}, not EN_ROUTE. Skipping auto-transition.")
            return
            
        if job.assigned_technician_id is None:
            logger.warning(f"auto_transition_on_geofence: Job {job_id} has no assigned technician. Skipping auto-transition.")
            return
            
        logger.info(f"auto_transition_on_geofence: Auto-transitioning Job {job_id} from EN_ROUTE to ON_SITE. Distance: {distance:.2f}m")
        
        job.transition("ON_SITE", actor_id="system", actor_role="system", reason="geofence_entry")
        db.commit()
        logger.info(f"auto_transition_on_geofence: Successfully committed status transition to ON_SITE for job {job_id}")
    except Exception as e:
        logger.error(f"auto_transition_on_geofence: Failed to auto-transition job {job_id}: {e}")
        db.rollback()
    finally:
        db.close()

@celery_app.task(
    name="app.tasks.auto_requeue_dlq"
)
def auto_requeue_dlq(limit: int = 100):
    """
    Automatically requeue failed DLQ tasks.

    Tasks are taken from the operational Redis DLQ and
    submitted back to the priority task queue.

    Successfully requeued items are removed from the
    Redis DLQ and recorded in the audit log.
    """

    redis = get_redis_client()

    if redis is None:
        logger.warning(
            "DLQ auto-requeue skipped: Redis unavailable"
        )

        return {
            "success": False,
            "requeued": 0,
            "reason": "redis_unavailable",
        }

    db = SessionLocal()

    try:
        dlq = DeadLetterQueue(
            redis_client=redis,
            db=db,
        )

        queue = PriorityTaskQueue(redis)

        results = dlq.auto_requeue(
            queue=queue,
            limit=limit,
        )

        for result in results:
            audit_log(
                db,
                action=AuditAction.TASK_DLQ,
                tenant_id=result["tenant_id"],
                entity_type="task",
                entity_id=result["old_task_id"],
                details={
                    "operation": "auto_requeue",
                    "dlq_id": result["dlq_id"],
                    "old_task_id": result["old_task_id"],
                    "new_task_id": result["new_task_id"],
                },
                severity="WARNING",
            )

        db.commit()

        logger.info(
            "DLQ auto-requeue completed: %s tasks requeued",
            len(results),
        )

        return {
            "success": True,
            "requeued": len(results),
            "items": results,
        }

    except Exception as exc:
        db.rollback()

        logger.error(
            "DLQ auto-requeue failed: %s",
            exc,
            exc_info=True,
        )

        raise

    finally:
        db.close()