from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timezone, timedelta
from sqlalchemy import func, or_
import asyncio
import uuid
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from .services.ai.FieldOpsAI.agents.dispatcher_agent.dispatcher_runtime import (
    get_dispatcher_runtime,
)

from .database import SessionLocal
from .models import Technician, DispatcherNotification, InAppNotification, Job, JobAssignment, SLAEscalation
from .redis_client import get_redis_client
from .logger import logger
from .services.timer_service import TimerService
from .services.dispatch_agent import DispatchAgent
from .services.distributed_lock_service import with_job_lock
from .services.dispatch_scheduling import dispatch_due_at
from .services.re_dispatch_trigger import ReDispatchTriggerService
from .services.re_dispatch_queue import ReDispatchQueueService
from .services.sla_escalation_service import SLAEscalationService
from fastapi import HTTPException

scheduler = BackgroundScheduler()

# Dispatcher planning/force-assignment can take longer than a scheduler tick.
# Run those operations outside the timeout-checker thread so APScheduler can
# continue expiring other offers. One resume task per job is allowed at a time.
_dispatch_resume_executor = ThreadPoolExecutor(
    max_workers=4,
    thread_name_prefix="fieldops-dispatch-resume",
)
_dispatch_resume_guard = threading.Lock()
_dispatch_resume_jobs: set[int] = set()

def _run_dispatch_resume(job_id: int, event: str, technician_id: int | None = None):
    try:
        asyncio.run(
            get_dispatcher_runtime().resume_dispatch(
                job_id=int(job_id),
                event=event,
                technician_id=technician_id,
            )
        )
        logger.info(
            "dispatcher_resume_background_completed job_id=%s event=%s",
            job_id, event,
        )
    except Exception:
        logger.exception(
            "dispatcher_resume_background_failed job_id=%s event=%s",
            job_id, event,
        )
    finally:
        with _dispatch_resume_guard:
            _dispatch_resume_jobs.discard(int(job_id))

def _schedule_dispatch_resume(
    job_id: int,
    event: str,
    technician_id: int | None = None,
) -> bool:
    """Queue one dispatcher resume per job without blocking the scheduler."""
    normalized_job_id = int(job_id)
    with _dispatch_resume_guard:
        if normalized_job_id in _dispatch_resume_jobs:
            logger.info(
                "dispatcher_resume_already_queued job_id=%s event=%s",
                normalized_job_id, event,
            )
            return False
        _dispatch_resume_jobs.add(normalized_job_id)

    try:
        _dispatch_resume_executor.submit(
            _run_dispatch_resume, normalized_job_id, event, technician_id
        )
        logger.info(
            "dispatcher_resume_queued job_id=%s event=%s",
            normalized_job_id, event,
        )
        return True
    except Exception:
        with _dispatch_resume_guard:
            _dispatch_resume_jobs.discard(normalized_job_id)
        logger.exception(
            "dispatcher_resume_queue_failed job_id=%s event=%s",
            normalized_job_id, event,
        )
        return False

def check_technician_heartbeats():
    """Deprecated: heartbeat freshness no longer changes explicit availability."""
    return 0

def cleanup_old_notifications():
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        threshold = now - timedelta(days=30)
        
        updated = db.query(InAppNotification).filter(
            InAppNotification.created_at < threshold,
            InAppNotification.status != 'DISMISSED'
        ).update({
            "status": "DISMISSED",
            "dismissed_at": now
        }, synchronize_session=False)
        
        db.commit()
        if updated > 0:
            logger.info(f"Cleaned up {updated} old in-app notifications (soft deleted).")
    except Exception as e:
        logger.error(f"Error in background notification cleanup job: {e}")
        db.rollback()
    finally:
        db.close()

def checkment_timers():
    """Expire broadcast offers in batches and preserve legacy timer behavior.

    Broadcast timeout decisions are based on JobAssignment.assigned_at, not
    Redis key expiry. All expired offers for one job are updated under one
    job lock. The dispatcher is resumed once, after releasing that lock, so
    it can wait for all remaining offers or advance to fresh Planning.

    Diagnostic timing identifies slow Redis, database, lock, or dispatcher work.
    """
    started_at = time.perf_counter()
    run_id = str(uuid.uuid4())[:8]
    logger.info("TIMEOUT_CHECKER: started run_id=%s", run_id)
    db = SessionLocal()
    redis_client = None
    expired_by_job = {}

    try:
        # Redis is useful for timer cleanup and legacy timers. Its health check
        # must not prevent DB-timestamp-based broadcast expiry from running.
        redis_started = time.perf_counter()
        logger.info("TIMEOUT_CHECKER: checking Redis run_id=%s", run_id)
        try:
            candidate_redis = get_redis_client()
            if candidate_redis is not None and candidate_redis.ping():
                redis_client = candidate_redis
            else:
                logger.warning(
                    "TIMEOUT_CHECKER: Redis unavailable; broadcast expiry will "
                    "continue using database timestamps"
                )
        except Exception:
            logger.exception(
                "TIMEOUT_CHECKER: Redis health check failed; continuing "
                "broadcast expiry using database timestamps run_id=%s",
                run_id,
            )

        logger.info(
            "TIMEOUT_CHECKER: Redis check completed duration=%.2fs run_id=%s",
            time.perf_counter() - redis_started,
            run_id,
        )

        now = datetime.now(timezone.utc)
        duration = int(TimerService.ACCEPTANCE_DURATION_SECONDS)
        cutoff = now - timedelta(seconds=duration)

        logger.info("TIMEOUT_CHECKER: started")

        # -------------------------------------------------------------
        # 1. Broadcast offers: find expired PENDING rows from the DB.
        # -------------------------------------------------------------
        query_started = time.perf_counter()
        logger.info(
            "TIMEOUT_CHECKER: querying expired offers cutoff=%s run_id=%s",
            cutoff.isoformat(), run_id,
        )
        pending_offers = (
            db.query(JobAssignment)
            .filter(
                JobAssignment.status == "PENDING",
                JobAssignment.assigned_at.isnot(None),
                JobAssignment.assigned_at <= cutoff,
            )
            .order_by(JobAssignment.job_id.asc(), JobAssignment.id.asc())
            .all()
        )

        logger.info(
            "TIMEOUT_CHECKER: found %s expired pending broadcast offers",
            len(pending_offers),
        )

        logger.info(
            "TIMEOUT_CHECKER: expired offer query completed count=%s duration=%.2fs run_id=%s",
            len(pending_offers), time.perf_counter() - query_started, run_id,
        )

        # Group by job so each job lock and dispatcher coordination run once
        # per scheduler pass, even when several technicians expire together.
        job_ids = sorted({int(row.job_id) for row in pending_offers})
        logger.info("TIMEOUT_CHECKER: expired jobs=%s run_id=%s", job_ids, run_id)

        for job_id in job_ids:
            job_started = time.perf_counter()
            logger.info("TIMEOUT_CHECKER: processing job_id=%s run_id=%s", job_id, run_id)
            timed_out_technicians = []

            try:
                lock_started = time.perf_counter()
                logger.info("TIMEOUT_CHECKER: acquiring job lock job_id=%s run_id=%s", job_id, run_id)
                with with_job_lock(str(job_id)):
                    logger.info(
                        "TIMEOUT_CHECKER: acquired job lock job_id=%s wait=%.2fs run_id=%s",
                        job_id, time.perf_counter() - lock_started, run_id,
                    )
                    locked_job = (
                        db.query(Job)
                        .filter(Job.id == job_id)
                        .with_for_update()
                        .first()
                    )

                    if locked_job is None:
                        logger.warning(
                            "broadcast_timeout_job_missing job_id=%s",
                            job_id,
                        )
                        db.rollback()
                        continue

                    # If a technician has already accepted, do not modify
                    # remaining offers here. The acceptance transaction owns
                    # winner/LOST transitions.
                    if locked_job.assigned_technician_id is not None:
                        logger.info(
                            "broadcast_timeout_skipped_winner_exists job_id=%s "
                            "winner=%s",
                            job_id,
                            locked_job.assigned_technician_id,
                        )
                        db.rollback()
                        continue

                    locked_offers = (
                        db.query(JobAssignment)
                        .filter(
                            JobAssignment.job_id == job_id,
                            JobAssignment.status == "PENDING",
                            JobAssignment.assigned_at.isnot(None),
                            JobAssignment.assigned_at <= cutoff,
                        )
                        .order_by(JobAssignment.id.asc())
                        .with_for_update()
                        .all()
                    )

                    logger.info(
                        "TIMEOUT_CHECKER: locked pending offers job_id=%s count=%s run_id=%s",
                        job_id, len(locked_offers), run_id,
                    )
                    # Recheck each row while holding the database locks.
                    # This also handles databases that return naive datetimes.
                    for locked_offer in locked_offers:
                        assigned_at = locked_offer.assigned_at
                        if assigned_at.tzinfo is None:
                            assigned_at = assigned_at.replace(
                                tzinfo=timezone.utc
                            )
                        else:
                            assigned_at = assigned_at.astimezone(timezone.utc)

                        if datetime.now(timezone.utc) < (
                            assigned_at + timedelta(seconds=duration)
                        ):
                            continue

                        locked_offer.status = "TIMEOUT"
                        locked_offer.responded_at = datetime.now(timezone.utc)
                        locked_offer.is_current = False
                        timed_out_technicians.append(
                            int(locked_offer.technician_id)
                        )

                    if timed_out_technicians:
                        commit_started = time.perf_counter()
                        db.commit()
                        logger.info(
                            "TIMEOUT_CHECKER: committed timeout rows job_id=%s count=%s commit_duration=%.2fs run_id=%s",
                            job_id, len(timed_out_technicians), time.perf_counter() - commit_started, run_id,
                        )
                    else:
                        db.rollback()

                logger.info(
                    "TIMEOUT_CHECKER: released job lock job_id=%s elapsed=%.2fs run_id=%s",
                    job_id, time.perf_counter() - job_started, run_id,
                )
                # The distributed lock has been released before Redis cleanup
                # and dispatcher resume. Never nest resume_dispatch's job lock.
                if timed_out_technicians:
                    expired_by_job[job_id] = sorted(
                        set(timed_out_technicians)
                    )

                    if redis_client is not None:
                        for technician_id in expired_by_job[job_id]:
                            try:
                                TimerService.cancel_timer(
                                    redis_client,
                                    str(job_id),
                                    str(technician_id),
                                )
                            except Exception:
                                logger.exception(
                                    "broadcast_timeout_timer_cleanup_failed "
                                    "job_id=%s technician_id=%s",
                                    job_id,
                                    technician_id,
                                )

                    logger.info(
                        "broadcast_offers_timed_out job_id=%s "
                        "technician_ids=%s count=%s",
                        job_id,
                        expired_by_job[job_id],
                        len(expired_by_job[job_id]),
                    )

            except HTTPException as exc:
                db.rollback()
                if exc.status_code == 409:
                    logger.warning(
                        "TIMEOUT_CHECKER: job lock busy; will retry next run "
                        "job_id=%s",
                        job_id,
                    )
                    continue
                raise
            except Exception:
                db.rollback()
                logger.exception(
                    "broadcast_timeout_processing_failed job_id=%s",
                    job_id,
                )

        # One coordination call per job. Passing technician_id=None is
        # intentional: DispatcherRuntime reconstructs attempted technician
        # identities from the committed JobAssignment history. This prevents
        # seven simultaneous expirations from causing seven replanning runs.
        for job_id, technician_ids in expired_by_job.items():
            resume_started = time.perf_counter()
            try:
                logger.info(
                    "TIMEOUT_CHECKER: resuming dispatcher job_id=%s "
                    "timed_out_technicians=%s",
                    job_id,
                    technician_ids,
                )
                logger.info("TIMEOUT_CHECKER: queueing resume_dispatch job_id=%s run_id=%s", job_id, run_id)
                queued = _schedule_dispatch_resume(
                    job_id=job_id,
                    event="TECHNICIAN_TIMEOUT",
                    technician_id=None,
                )
                logger.info(
                    "broadcast_timeout_coordination_%s job_id=%s queue_duration=%.2fs run_id=%s",
                    "queued" if queued else "already_queued",
                    job_id, time.perf_counter() - resume_started, run_id,
                )
            except Exception:
                logger.exception(
                    "broadcast_timeout_coordination_failed job_id=%s duration=%.2fs run_id=%s",
                    job_id, time.perf_counter() - resume_started, run_id,
                )

        # -------------------------------------------------------------
        # 2. Legacy single-assignee jobs. Keep the existing offline/SLA
        # redispatch behavior for older records using job-scoped timers.
        # -------------------------------------------------------------
        if redis_client is None:
            logger.debug(
                "TIMEOUT_CHECKER: skipping legacy Redis timer scan because "
                "Redis is unavailable"
            )
            return

        legacy_query_started = time.perf_counter()
        logger.info("TIMEOUT_CHECKER: querying legacy assigned jobs run_id=%s", run_id)
        assigned_jobs = (
            db.query(Job)
            .filter(func.upper(Job.status) == "ASSIGNED")
            .all()
        )

        logger.info(
            "TIMEOUT_CHECKER: legacy assigned jobs count=%s duration=%.2fs run_id=%s",
            len(assigned_jobs), time.perf_counter() - legacy_query_started, run_id,
        )
        for job in assigned_jobs:
            legacy_job_started = time.perf_counter()
            timer_key = f"job:timer:{job.id}"
            warning_key = f"job:timer_warning:{job.id}"
            warned_key = f"job:timer_warned:{job.id}"

            timer_exists = bool(redis_client.exists(timer_key))
            timer_ttl = (
                redis_client.ttl(timer_key)
                if hasattr(redis_client, "ttl")
                else 0
            )
            if timer_ttl is None or timer_ttl < 0:
                timer_ttl = 0

            tech = (
                db.query(Technician)
                .filter(
                    Technician.technician_id == job.assigned_technician_id
                )
                .first()
            )

            if not job.tenant_id and tech and tech.tenant_id:
                job.tenant_id = tech.tenant_id
                db.commit()

            trigger = ReDispatchTriggerService.detect_trigger(
                job=job,
                tech=tech,
                timer_exists=timer_exists,
                timer_ttl=timer_ttl,
            )
            if not trigger:
                continue

            legacy_timeout_resume = None

            try:
                with with_job_lock(str(job.id)):
                    db.refresh(job)
                    if str(job.status).upper() != "ASSIGNED":
                        continue

                    current_tech = (
                        db.query(Technician)
                        .filter(
                            Technician.technician_id
                            == job.assigned_technician_id
                        )
                        .first()
                    )
                    reason = trigger.get("reason")

                    if reason == "timeout":
                        current_technician_id = job.assigned_technician_id
                        if current_technician_id is None:
                            TimerService.cancel_timer(
                                redis_client, str(job.id)
                            )
                            continue

                        TimerService.cancel_timer(
                            redis_client, str(job.id)
                        )
                        for key in (warning_key, warned_key):
                            try:
                                redis_client.delete(key)
                            except Exception:
                                logger.warning(
                                    "Legacy timer warning cleanup failed: %s",
                                    key,
                                )

                        assignment = (
                            db.query(JobAssignment)
                            .filter(
                                JobAssignment.job_id == job.id,
                                JobAssignment.technician_id
                                == current_technician_id,
                                JobAssignment.is_current.is_(True),
                            )
                            .with_for_update()
                            .first()
                        )

                        if assignment is not None:
                            assignment.status = "TIMEOUT"
                            assignment.responded_at = datetime.now(timezone.utc)
                            assignment.is_current = False

                        job.assigned_technician_id = None
                        job.status = "QUEUED"

                        if current_tech is not None:
                            current_jobs = int(
                                getattr(current_tech, "current_jobs", 0) or 0
                            )
                            if current_jobs > 0:
                                current_tech.current_jobs = current_jobs - 1

                        db.commit()
                        legacy_timeout_resume = int(current_technician_id)

                    elif reason in {"tech_offline", "sla_risk"}:
                        tenant_id_str = (
                            job.tenant_id
                            or (
                                current_tech.tenant_id
                                if current_tech and current_tech.tenant_id
                                else "system"
                            )
                        )
                        tech_id_str = (
                            current_tech.tech_id
                            if current_tech
                            else str(job.assigned_technician_id)
                        )

                        ReDispatchQueueService.enqueue_failed_job(
                            db=db,
                            redis_client=redis_client,
                            job=job,
                            tenant_id=tenant_id_str,
                            reason=f"Triggered by: {reason}",
                            tech_id=tech_id_str,
                        )

                        if current_tech:
                            db.add(
                                DispatcherNotification(
                                    tech_id=current_tech.tech_id,
                                    tenant_id=tenant_id_str,
                                    message=(
                                        f"Job {job.id} assignment revoked for "
                                        f"{current_tech.technician_name}. "
                                        f"Reason: {reason}."
                                    ),
                                )
                            )
                            db.commit()

                        DispatchAgent.trigger_redispatch(str(job.id))
                        TimerService.cancel_timer(redis_client, str(job.id))

                    else:
                        logger.warning(
                            "Unsupported legacy timer trigger reason=%s "
                            "job_id=%s",
                            reason,
                            job.id,
                        )
                        TimerService.cancel_timer(
                            redis_client, str(job.id)
                        )

                # Resume only after releasing the legacy job lock.
                if legacy_timeout_resume is not None:
                    try:
                        _schedule_dispatch_resume(
                            job_id=int(job.id),
                            event="TECHNICIAN_TIMEOUT",
                            technician_id=legacy_timeout_resume,
                        )
                    except Exception:
                        logger.exception(
                            "Legacy dispatcher timeout resume failed "
                            "job_id=%s",
                            job.id,
                        )

            except HTTPException as exc:
                db.rollback()
                if exc.status_code == 409:
                    continue
                raise
            except Exception:
                db.rollback()
                logger.exception("Legacy assignment timer failed job_id=%s run_id=%s", job.id, run_id)
            finally:
                logger.info(
                    "TIMEOUT_CHECKER: legacy job finished job_id=%s duration=%.2fs run_id=%s",
                    job.id, time.perf_counter() - legacy_job_started, run_id,
                )

    except Exception:
        db.rollback()
        logger.exception("TIMEOUT_CHECKER: execution failed run_id=%s", run_id)
    finally:
        try:
            db.close()
        finally:
            logger.info(
                "TIMEOUT_CHECKER: finished total_duration=%.2fs expired_jobs=%s run_id=%s",
                time.perf_counter() - started_at, len(expired_by_job), run_id,
            )


def check_sla_escalations():
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        threshold = now + timedelta(minutes=30)

        bind_engine = db.get_bind()
        is_sqlite = bind_engine.url.drivername.startswith("sqlite")
        
        query_threshold = threshold
        if is_sqlite:
            query_threshold = threshold.replace(tzinfo=None)

        queued_jobs = db.query(Job).filter(
            func.upper(Job.status) == 'QUEUED',
            Job.priority.in_(['P1', 'P2']),
            Job.sla_deadline <= query_threshold
        ).all()

        for job in queued_jobs:
            SLAEscalationService.trigger_escalation(db, job)

    except Exception as e:
        logger.error(f"Error checking SLA escalations: {e}")
        db.rollback()
    finally:
        db.close()

def check_cto_escalations():
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        threshold = now - timedelta(minutes=15)

        bind_engine = db.get_bind()
        is_sqlite = bind_engine.url.drivername.startswith("sqlite")
        
        query_threshold = threshold
        if is_sqlite:
            query_threshold = threshold.replace(tzinfo=None)

        escalations = db.query(SLAEscalation).filter(
            SLAEscalation.manager_responded_at.is_(None),
            SLAEscalation.cto_notified_at.is_(None),
            SLAEscalation.manager_notified_at <= query_threshold
        ).all()

        for esc in escalations:
            SLAEscalationService.escalate_to_cto(db, esc)

    except Exception as e:
        logger.error(f"Error checking CTO escalations: {e}")
        db.rollback()
    finally:
        db.close()


def create_monthly_partitions():
    from sqlalchemy import text
    db = SessionLocal()
    try:
        bind_engine = db.get_bind()
        is_postgres = bind_engine.url.drivername.startswith("postgresql")
        if is_postgres:
            db.execute(text("""
                CREATE OR REPLACE FUNCTION create_gps_ping_partition(target_date TIMESTAMPTZ)
                RETURNS VOID AS $$
                DECLARE
                    partition_start DATE;
                    partition_end DATE;
                    partition_name TEXT;
                    sql TEXT;
                BEGIN
                    partition_start := DATE_TRUNC('month', target_date)::DATE;
                    partition_end := (partition_start + INTERVAL '1 month')::DATE;
                    partition_name := 'gps_pings_' || TO_CHAR(partition_start, 'YYYY_MM');
                    
                    IF NOT EXISTS (
                        SELECT 1 
                        FROM pg_class c 
                        JOIN pg_namespace n ON n.oid = c.relnamespace 
                        WHERE c.relname = partition_name
                    ) THEN
                        BEGIN
                            sql := 'CREATE TABLE ' || partition_name || ' PARTITION OF gps_pings ' ||
                                   'FOR VALUES FROM (' || quote_literal(partition_start) || ') TO (' || quote_literal(partition_end) || ')';
                            EXECUTE sql;
                        EXCEPTION WHEN OTHERS THEN
                            NULL;
                        END;
                    END IF;
                END;
                $$ LANGUAGE plpgsql;
            """))
            db.execute(text("SELECT create_gps_ping_partition(NOW());"))
            db.execute(text("SELECT create_gps_ping_partition(NOW() + INTERVAL '1 month');"))
            db.commit()
            logger.info("Checked and auto-created GPS ping database partitions.")
    except Exception as e:
        logger.error(f"Error in background monthly partition creator: {e}")
        db.rollback()
    finally:
        db.close()


def daily_gps_purge_scheduler_job():
    from .tasks import execute_daily_gps_purge_sync
    db = SessionLocal()
    try:
        execute_daily_gps_purge_sync(db)
    except Exception as e:
        logger.error(f"Error in background daily GPS purge job: {e}")
    finally:
        db.close()

def sentiment_audit_archive_scheduler_job():
    from .tasks import archive_old_sentiment_audits

    db = SessionLocal()

    try:
        archive_old_sentiment_audits(db)
    except Exception as e:
        logger.error(
            f"Error in background sentiment audit archive job: {e}"
        )
    finally:
        db.close()


def process_transactional_email_outbox_job():
    """Poll the durable SMTP outbox independently of AI and Kafka work."""
    from .services.email.transactional_outbox import process_due_emails

    db = SessionLocal()
    try:
        process_due_emails(db, limit=50)
    except Exception:
        db.rollback()
        logger.exception("email_outbox_poll_failed")
    finally:
        db.close()


def dispatch_pending_jobs(tenant_id: str | None = None):
    """Deprecated: broad pending-job sweeps are disabled; dispatch is job-scoped."""
    logger.info(
        "pending_dispatch_sweep_skipped tenant_id=%s reason=job_scoped_dispatch",
        str(tenant_id) if tenant_id is not None else "all",
    )


def dispatch_due_pending_jobs():
    """Deprecated: periodic scans must not dispatch unrelated existing jobs."""
    return None


def dispatch_pending_jobs_for_tenant(tenant_id: str):
    """Availability changes do not trigger assignment of pre-existing jobs."""
    logger.info(
        "availability_dispatch_retry_skipped tenant_id=%s reason=job_scoped_dispatch",
        str(tenant_id),
    )


def _run_registered_dispatch(job_id: int, dispatch_attempt_id: str):
    """Execute an explicitly registered per-job date trigger."""
    try:
        with with_job_lock(str(job_id)):
            asyncio.run(
                get_dispatcher_runtime().start_dispatch(
                    int(job_id),
                    dispatch_attempt_id=dispatch_attempt_id,
                )
            )
    except HTTPException as exc:
        if exc.status_code != 409:
            logger.exception(
                "dispatch_failed job_id=%s technician_id=none dispatch_attempt_id=%s phase=scheduled_trigger outcome=failed",
                job_id,
                dispatch_attempt_id,
            )
    except Exception:
        logger.exception(
            "dispatch_failed job_id=%s technician_id=none dispatch_attempt_id=%s phase=scheduled_trigger outcome=failed",
            job_id,
            dispatch_attempt_id,
        )


def register_scheduled_dispatch(job_id: int, dispatch_attempt_id: str):
    """Register the exact one-hour-before-visit date trigger for a committed job."""
    with SessionLocal() as db:
        job = db.query(Job).filter(Job.id == int(job_id)).first()
        if job is None:
            raise ValueError(f"Job {job_id} not found while scheduling dispatch")
        if (
            str(job.status or "").strip().upper() not in {
                "CREATED", "QUEUED", "UNASSIGNED"
            }
            or job.assigned_technician_id is not None
        ):
            logger.info(
                "dispatch_schedule_skipped job_id=%s status=%s outcome=not_unassigned",
                job_id,
                job.status,
            )
            return None
        organization = None
        if job.tenant_id:
            from .models import Organization
            organization = db.query(Organization).filter(Organization.id == job.tenant_id).first()
        settings = getattr(organization, "settings", None) or {}
        timezone_name = getattr(job, "preferred_service_timezone", None) or (
            settings.get("timezone") if isinstance(settings, dict) else None
        )
        due_at = dispatch_due_at(
            job.preferred_service_date,
            timezone_name,
            getattr(job, "preferred_service_time", None),
        )

    schedule_job_id = f"dispatch_due_job_{int(job_id)}"
    scheduler.add_job(
        _run_registered_dispatch,
        trigger="date",
        run_date=due_at,
        args=[int(job_id), dispatch_attempt_id],
        id=schedule_job_id,
        replace_existing=True,
        misfire_grace_time=24 * 60 * 60,
    )
    logger.info(
        "dispatch_scheduled job_id=%s technician_id=none dispatch_attempt_id=%s dispatch_due_at=%s schedule_job_id=%s outcome=registered",
        job_id,
        dispatch_attempt_id,
        due_at.isoformat(),
        schedule_job_id,
    )
    return due_at


def register_pending_scheduled_dispatches():
    """Rebuild in-memory date triggers after process start/restart."""
    db = SessionLocal()
    try:
        pending_ids = [
            row.id
            for row in db.query(Job.id)
            .filter(
                func.upper(func.trim(Job.status)).in_(
                    ["CREATED", "QUEUED", "UNASSIGNED"]
                ),
                Job.assigned_technician_id.is_(None),
            )
            .order_by(Job.id.asc())
            .all()
        ]
    finally:
        db.close()

    registered = 0
    for job_id in pending_ids:
        attempt_id = str(uuid.uuid4())
        try:
            register_scheduled_dispatch(int(job_id), attempt_id)
            registered += 1
        except Exception:
            logger.exception(
                "dispatch_failed job_id=%s technician_id=none dispatch_attempt_id=%s phase=scheduler_recovery_registration outcome=failed",
                job_id,
                attempt_id,
            )

    logger.info(
        "pending_dispatch_schedules_recovered count=%s outcome=complete",
        registered,
    )


def start_scheduler():
    if not scheduler.running:
        scheduler.add_job(cleanup_old_notifications, 'cron', hour=0, minute=0, id='notification_cleanup')
        scheduler.add_job(
            checkment_timers,
            'interval',
            seconds=10,
            id='timer_checker',
            max_instances=1,
            coalesce=True,
            misfire_grace_time=30,
            replace_existing=True,
        )
        scheduler.add_job(check_sla_escalations, 'interval', seconds=10, id='sla_escalation_checker')
        scheduler.add_job(check_cto_escalations, 'interval', seconds=30, id='cto_escalation_checker')
        # Run monthly partition check on the 1st of every month
        scheduler.add_job(create_monthly_partitions, 'cron', day=1, hour=0, minute=0, id='gps_partition_creator')
        # Run daily GPS purge at 2 AM UTC
        scheduler.add_job(daily_gps_purge_scheduler_job, 'cron', hour=2, minute=0, timezone='UTC', id='gps_daily_purger')
        scheduler.add_job(
         sentiment_audit_archive_scheduler_job,
         'cron',
         hour=3,
         minute=0,
         timezone='UTC',
         id='sentiment_audit_archiver'
        )
        scheduler.add_job(
            process_transactional_email_outbox_job,
            'interval',
            seconds=15,
            id='transactional_email_outbox_poller',
            max_instances=1,
            coalesce=True,
            misfire_grace_time=60,
            replace_existing=True,
        )
        scheduler.start()
        logger.info("Background heartbeat scheduler started.")
        logger.info(
            "email_outbox_worker_started",
            extra={"poll_interval_seconds": 15},
        )
        # Run once immediately on startup
        create_monthly_partitions()

def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Background heartbeat scheduler stopped.")

# ---------------------------------------------------------------------------
# Celery Queue Management: Task Timeout Configuration & Worker Helpers
# ---------------------------------------------------------------------------

from .celery_app import (
    DEFAULT_TASK_TIMEOUTS,
    QUEUE_TASK_TIMEOUTS,
    get_task_timeouts_config,
    get_queue_timeout,
    configure_task_timeouts,
    ConfigureTaskTimeouts,
    Configure_task_timeouts,
    DEFAULT_CELERY_MONITORING,
    get_celery_monitoring_config,
    add_celery_monitoring,
    get_celery_monitoring_metrics,
    get_celery_worker_health,
    get_celery_queue_depth,
    get_all_queue_depths,
    record_task_failure,
    record_task_retry,
    record_task_latency,
    detect_abnormal_queue_growth,
    detect_stalled_workers,
    AddCeleryMonitoring,
    Add_celery_monitoring,
    configure_celery_monitoring,
    ConfigureCeleryMonitoring,
    get_celery_monitoring,
    GetCeleryMonitoring,
    CeleryMonitoring,
    CeleryMonitoringService,
)


