from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timezone, timedelta
from sqlalchemy import func, or_
import asyncio
import uuid
from .services.ai.FieldOpsAI.agents.dispatcher_agent.dispatcher_runtime import (
    get_dispatcher_runtime,
)

from .database import SessionLocal
from .models import Technician, DispatcherNotification, InAppNotification, Job, SLAEscalation
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
    """
    Check automatic technician-assignment timers.

    Responsibilities:
    - Detect imminent timeout and send pre-alerts.
    - Preserve existing legacy redispatch behaviour for:
        * technician offline
        * SLA risk
    - For normal acceptance timeout, resume the LangGraph
      DispatcherRuntime with TECHNICIAN_TIMEOUT.
    - Never run both the legacy redispatch flow and the
      LangGraph timeout flow for the same timeout.
    """

    db = SessionLocal()
    redis_client = get_redis_client()

    if not redis_client:
        db.close()
        return

    try:
        # Redis connectivity check.
        try:
            if redis_client.ping() is None:
                db.close()
                return
        except Exception as redis_error:
            logger.error(
                "Assignment timer checker: Redis unavailable: %s",
                redis_error,
            )
            db.close()
            return

        assigned_jobs = (
            db.query(Job)
            .filter(func.upper(Job.status) == "ASSIGNED")
            .all()
        )

        for job in assigned_jobs:
            timer_key = f"job:timer:{job.id}"
            warning_key = f"job:timer_warning:{job.id}"
            warned_key = f"job:timer_warned:{job.id}"

            timer_exists = bool(redis_client.exists(timer_key))
            warning_exists = bool(redis_client.exists(warning_key))
            has_warned = bool(redis_client.exists(warned_key))

            timer_ttl = (
                redis_client.ttl(timer_key)
                if hasattr(redis_client, "ttl")
                else 0
            )

            # Redis returns:
            #   -1 = key exists without expiry
            #   -2 = key does not exist
            #
            # Treat either as expired/missing for the trigger detector.
            if timer_ttl is None or timer_ttl < 0:
                timer_ttl = 0

            tech = (
                db.query(Technician)
                .filter(
                    Technician.technician_id
                    == job.assigned_technician_id
                )
                .first()
            )

            if not tech:
                logger.warning(
                    "Assignment timer: technician not found "
                    "for job=%s technician_id=%s",
                    job.id,
                    job.assigned_technician_id,
                )

            # ---------------------------------------------------------
            # Legacy compatibility:
            # Some old jobs may not have tenant_id populated.
            # ---------------------------------------------------------
            if (
                not job.tenant_id
                and tech
                and tech.tenant_id
            ):
                job.tenant_id = tech.tenant_id
                db.commit()

            # ---------------------------------------------------------
            # Ask the existing trigger service what happened.
            # ---------------------------------------------------------
            trigger = ReDispatchTriggerService.detect_trigger(
                job=job,
                tech=tech,
                timer_exists=timer_exists,
                timer_ttl=timer_ttl,
            )

            if not trigger:
                continue

            try:
                with with_job_lock(str(job.id)):

                    # -------------------------------------------------
                    # Re-load the job after acquiring the distributed
                    # lock. Another worker/process may have handled it.
                    # -------------------------------------------------
                    db.refresh(job)

                    if str(job.status).upper() != "ASSIGNED":
                        logger.info(
                            "Assignment timer: job=%s is no longer "
                            "ASSIGNED; skipping.",
                            job.id,
                        )
                        continue

                    # Re-resolve the current technician after refresh.
                    current_tech = (
                        db.query(Technician)
                        .filter(
                            Technician.technician_id
                            == job.assigned_technician_id
                        )
                        .first()
                    )

                    reason = trigger.get("reason")

                    # =================================================
                    # 1. NORMAL ACCEPTANCE TIMEOUT
                    #
                    # This is now handled by LangGraph DispatcherRuntime.
                    # =================================================
                    if reason == "timeout":
                        current_technician_id = (
                            job.assigned_technician_id
                        )

                        if current_technician_id is None:
                            logger.warning(
                                "Timeout detected for job=%s but "
                                "assigned_technician_id is already NULL. "
                                "Skipping.",
                                job.id,
                            )
                            TimerService.cancel_timer(
                                redis_client,
                                str(job.id),
                            )
                            continue

                        logger.info(
                            "Dispatcher timeout: job=%s "
                            "technician=%s",
                            job.id,
                            current_technician_id,
                        )

                        # -------------------------------------------------
                        # Cancel the Redis timer first.
                        #
                        # DB state remains authoritative.
                        # -------------------------------------------------
                        TimerService.cancel_timer(
                            redis_client,
                            str(job.id),
                        )

                        # -------------------------------------------------
                        # Clear the Redis warning state as well.
                        # -------------------------------------------------
                        try:
                            redis_client.delete(
                                warning_key,
                                warned_key,
                            )
                        except Exception as redis_cleanup_error:
                            logger.warning(
                                "Failed to clean timeout warning keys "
                                "for job=%s: %s",
                                job.id,
                                redis_cleanup_error,
                            )

                        # -------------------------------------------------
                        # Important:
                        #
                        # Do NOT call:
                        #
                        #   DispatchAgent.trigger_redispatch(...)
                        #
                        # here.
                        #
                        # LangGraph owns the candidate sequence.
                        # -------------------------------------------------

                        # Persist the old assignment as a timeout if the
                        # JobAssignment model is available.
                        #
                        # We intentionally do this defensively because
                        # existing deployments may contain jobs that were
                        # created before JobAssignment was introduced.
                        try:
                            from .models import JobAssignment

                            assignment = (
                                db.query(JobAssignment)
                                .filter(
                                    JobAssignment.job_id == job.id,
                                    JobAssignment.technician_id
                                    == current_technician_id,
                                    JobAssignment.is_current.is_(True),
                                )
                                .first()
                            )

                            if assignment is not None:
                                assignment.status = "TIMEOUT"
                                assignment.responded_at = (
                                    datetime.now(timezone.utc)
                                )
                                assignment.is_current = False

                        except Exception as assignment_error:
                            logger.warning(
                                "Could not mark JobAssignment timeout "
                                "for job=%s: %s",
                                job.id,
                                assignment_error,
                            )

                        # -------------------------------------------------
                        # Clear current assignment before resuming graph.
                        #
                        # The next graph candidate must be allowed to
                        # become the current assignment.
                        # -------------------------------------------------
                        job.assigned_technician_id = None

                        # Keep the job dispatchable.
                        #
                        # Do NOT mark it COMPLETED/CANCELLED.
                        # The dispatcher will offer the next candidate.
                        if hasattr(job, "status"):
                            job.status = "QUEUED"

                        # If the current technician has been counted as
                        # having an active assignment, release that count.
                        if current_tech is not None:
                            current_jobs = int(
                                getattr(
                                    current_tech,
                                    "current_jobs",
                                    0,
                                )
                                or 0
                            )

                            if current_jobs > 0:
                                current_tech.current_jobs = (
                                    current_jobs - 1
                                )

                        db.commit()

                        # -------------------------------------------------
                        # Resume LangGraph.
                        #
                        # DispatcherRuntime.resume_dispatch() is async,
                        # while APScheduler BackgroundScheduler invokes
                        # this worker synchronously.
                        # -------------------------------------------------
                        runtime = get_dispatcher_runtime()

                        try:
                            asyncio.run(
                                runtime.resume_dispatch(
                                    job_id=int(job.id),
                                    event="TECHNICIAN_TIMEOUT",
                                    technician_id=int(current_tech.technician_id) if current_tech is not None else None,
                                )
                            )

                            logger.info(
                                "Dispatcher graph resumed after timeout "
                                "for job=%s",
                                job.id,
                            )

                        except Exception as dispatch_error:
                            logger.exception(
                                "Failed to resume DispatcherGraph after "
                                "timeout for job=%s: %s",
                                job.id,
                                dispatch_error,
                            )

                            # The old assignment has already been safely
                            # cleared and the timer cancelled.
                            #
                            # Do not call the legacy DispatchAgent here,
                            # otherwise both dispatch systems can compete.
                            #
                            # Leave the job queued for the next explicit
                            # recovery/retry mechanism.

                        continue

                    # =================================================
                    # 2. LEGACY OFFLINE / SLA REDISPATCH
                    #
                    # Keep existing behaviour for now.
                    # =================================================
                    if reason in {"tech_offline", "sla_risk"}:
                        logger.info(
                            "ReDispatch: Triggering legacy re-dispatch "
                            "for job=%s (Reason: %s)",
                            job.id,
                            reason,
                        )

                        tech_id_str = (
                            current_tech.tech_id
                            if current_tech
                            else str(job.assigned_technician_id)
                        )

                        tenant_id_str = (
                            job.tenant_id
                            or (
                                current_tech.tenant_id
                                if current_tech
                                and current_tech.tenant_id
                                else "system"
                            )
                        )

                        queue_result = (
                            ReDispatchQueueService.enqueue_failed_job(
                                db=db,
                                redis_client=redis_client,
                                job=job,
                                tenant_id=tenant_id_str,
                                reason=f"Triggered by: {reason}",
                                tech_id=tech_id_str,
                            )
                        )

                        if current_tech:
                            notif = DispatcherNotification(
                                tech_id=current_tech.tech_id,
                                tenant_id=tenant_id_str,
                                message=(
                                    f"Job {job.id} assignment revoked "
                                    f"for {current_tech.technician_name}. "
                                    f"Reason: {reason}."
                                ),
                            )
                            db.add(notif)
                            db.commit()

                        DispatchAgent.trigger_redispatch(
                            str(job.id)
                        )

                        TimerService.cancel_timer(
                            redis_client,
                            str(job.id),
                        )

                        continue

                    # =================================================
                    # 3. UNKNOWN TRIGGER
                    # =================================================
                    logger.warning(
                        "Assignment timer: unsupported trigger "
                        "reason=%s for job=%s",
                        reason,
                        job.id,
                    )

                    # Avoid leaving a stale timer around for an unknown
                    # trigger, but do not mutate the job automatically.
                    TimerService.cancel_timer(
                        redis_client,
                        str(job.id),
                    )

            except HTTPException as e:
                if e.status_code == 409:
                    logger.warning(
                        "ReDispatch: concurrency conflict handling "
                        "job=%s, skipping.",
                        job.id,
                    )
                    db.rollback()
                    continue

                raise

            except Exception as job_error:
                logger.exception(
                    "Error processing assignment timer for job=%s: %s",
                    job.id,
                    job_error,
                )
                db.rollback()

    except Exception as e:
        logger.exception(
            "Error checking assignment timers: %s",
            e,
        )
        db.rollback()

    finally:
        db.close()

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
        scheduler.add_job(checkment_timers, 'interval', seconds=5, id='timer_checker')
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

