import logging
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import hashlib
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
from .services.ola_map_client import OlaMapsClient
from .services.task_queue import PriorityTaskQueue
from .redis_client import get_redis_client
from .services.socket_manager import ws_manager
from .services.task_queue_worker import consume_task_queue
from app.services.sms.twilio_service import TwilioSMSService
from celery import shared_task
from .services.email.smtp_email import SMTPEmailService
import re

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

GPS_PARTITION_NAME_RE = re.compile(
    r"^gps_pings_\d{4}_(0[1-9]|1[0-2])$"
)

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

            # GPS partitions must follow the internally generated
            # gps_pings_YYYY_MM naming convention.
            if not GPS_PARTITION_NAME_RE.fullmatch(partition_name):
                logger.warning(
                    "Skipping unexpected GPS partition name: %r",
                    partition_name,
                )
                continue

            # SQL parameters cannot bind table identifiers.
            # The identifier is therefore allow-listed first and
            # then safely quoted by SQLAlchemy.
            identifier_preparer = (
                db.get_bind().dialect.identifier_preparer
            )
            quoted_partition = identifier_preparer.quote(
                partition_name
            )

            sql_count = text(
                f"SELECT COUNT(*) FROM {quoted_partition}"
            )
            count = db.execute(sql_count).scalar()

            if count == 0:
                logger.info(
                    "Dropping empty GPS partition: %s",
                    partition_name,
                )
                db.execute(
                    text(
                        f"DROP TABLE IF EXISTS "
                        f"{quoted_partition} CASCADE"
                    )
                )

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

    The ETAService is constructed with the task's database session, the shared Redis
    client, and the existing Ola Maps client so the task follows the same authoritative
    ETA path used by the customer portal.

    The task accepts both the current ETAService contract (minutes/km) and the legacy
    seconds/meters contract used by older callers/tests. Broadcasts expose explicit
    status/source/message fields so customers can distinguish live, estimated and
    unavailable ETA states without calculating anything on the client.
    """
    import asyncio

    db = SessionLocal()
    try:
        redis_client = get_redis_client()
        maps_client = OlaMapsClient(redis_client)
        eta_service = ETAService(db, redis_client, maps_client)

        # 1. Compute ETA
        loop = asyncio.new_event_loop()
        try:
            eta_result = loop.run_until_complete(
                eta_service.calculate_eta(
                    technician_id=technician_id,
                    job_id=job_id,
                )
            )
        finally:
            loop.close()

        if eta_result is None:
            logger.warning(
                f"[update_eta_task] ETAService returned None for tech={technician_id} job={job_id}"
            )
            return

        if not isinstance(eta_result, dict):
            raise TypeError("ETAService result must be a dictionary")

        # 2. Normalize the ETA contract for persistence and broadcasting.
        now = datetime.now(timezone.utc)
        eta_raw = eta_result.get("eta")

        if isinstance(eta_raw, str):
            from datetime import datetime as _dt
            try:
                eta_dt = _dt.fromisoformat(eta_raw.replace("Z", "+00:00"))
            except ValueError:
                eta_dt = now
        elif isinstance(eta_raw, datetime):
            eta_dt = eta_raw
        else:
            eta_dt = now

        # Current ETAService returns minutes/km; older task callers used seconds/meters.
        duration_minutes_raw = eta_result.get("duration_minutes")
        if duration_minutes_raw is not None:
            duration_minutes = float(duration_minutes_raw or 0)
        else:
            duration_seconds = float(eta_result.get("duration_seconds") or 0)
            duration_minutes = duration_seconds / 60.0

        distance_km_raw = eta_result.get("distance_km")
        if distance_km_raw is not None:
            distance_km = float(distance_km_raw or 0)
        else:
            distance_meters = float(eta_result.get("distance_meters") or 0)
            distance_km = distance_meters / 1000.0

        traffic_delay_minutes_raw = eta_result.get("traffic_delay_minutes")
        if traffic_delay_minutes_raw is not None:
            traffic_delay_minutes = float(traffic_delay_minutes_raw or 0)
        else:
            traffic_delay_seconds = float(eta_result.get("traffic_delay_seconds") or 0)
            traffic_delay_minutes = traffic_delay_seconds / 60.0

        status_value = str(eta_result.get("status") or "").strip().lower()
        confidence_value = str(eta_result.get("confidence") or "").strip().lower()

        if not status_value:
            if confidence_value in {"estimated", "low"}:
                status_value = "estimated"
            elif eta_raw:
                status_value = "calculated"
            else:
                status_value = "unknown"

        if not confidence_value:
            confidence_value = {
                "calculated": "calculated",
                "estimated": "estimated",
                "unknown": "unknown",
            }.get(status_value, "unknown")

        source_value = str(
            eta_result.get("source")
            or ("estimated" if status_value == "estimated" else status_value)
        ).strip().lower()

        message_value = (
            eta_result.get("message")
            or eta_result.get("disclaimer")
        )

        # Resolve job's tenant_id for the history row.
        job_record = (
            db.query(models.Job)
            .filter(models.Job.id == int(job_id))
            .first()
        )
        tenant_id = (job_record.tenant_id if job_record else None) or "unknown"

        history = models.ETAHistory(
            id=str(uuid.uuid4()),
            job_id=int(job_id),
            tenant_id=tenant_id,
            eta=eta_dt,
            duration_minutes=round(duration_minutes, 2),
            distance_km=round(distance_km, 3),
            traffic_delay_minutes=round(traffic_delay_minutes, 2),
            source_ping_id=ping_id,
        )
        db.add(history)
        db.commit()

        logger.info(
            f"[update_eta_task] Stored ETAHistory for tech={technician_id} job={job_id} "
            f"eta={eta_raw} status={status_value} confidence={confidence_value}"
        )

        # 3. Broadcast a customer-safe, authoritative ETA update.
        broadcast_payload = {
            "type": "eta_update",
            "job_id": str(job_id),
            "technician_id": technician_id,
            "eta": eta_raw if isinstance(eta_raw, str) else (
                eta_dt.isoformat() if eta_raw is not None else None
            ),
            "status": status_value,
            "source": source_value,
            "duration_minutes": round(duration_minutes, 1),
            "distance_km": round(distance_km, 2),
            "traffic_delay_minutes": round(traffic_delay_minutes, 1),
            "confidence": confidence_value,
            "message": message_value,
            "disclaimer": eta_result.get("disclaimer"),
            "updated_at": now.isoformat(),
        }

        ws_loop = asyncio.new_event_loop()
        try:
            ws_loop.run_until_complete(
                ws_manager.broadcast_to_job(
                    str(job_id),
                    broadcast_payload,
                )
            )
        finally:
            ws_loop.close()

    except Exception as exc:
        logger.error(
            f"[update_eta_task] Failed for tech={technician_id} job={job_id}: {exc}",
            exc_info=True,
        )
        db.rollback()
        try:
            raise self.retry(
                exc=exc,
                countdown=5 ** (self.request.retries + 1),
            )
        except Exception:
            logger.error(
                f"[update_eta_task] All retries exhausted for tech={technician_id} job={job_id}"
            )
    finally:
        db.close()

@celery_app.task
def process_job_status_transition_task(
    job_id,
    from_status,
    to_status,
    actor_id,
    actor_role,
    reason,
    correlation_id=None,
    event_version: int | None = None,
    technician_id: int | None = None,
):
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

        job_pk = job.id  # NEW: plain int, safe to use after commits/rollbacks

        notification_technician_id = (
            technician_id or job.assigned_technician_id
        )
        tech = None
        if notification_technician_id:
            tech = db.query(Technician).filter(
                Technician.technician_id == notification_technician_id
            ).first()

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
            technician_id=(
                str(notification_technician_id)
                if notification_technician_id
                else None
            ),
            technician_name=tech.technician_name if tech else None,
            customer_id=job.customer_id,
            customer_name=job.customer_name,
            customer_phone=job.contact_number,
            customer_email=job.customer_email,
            eta=get_cached_eta(str(job.assigned_technician_id), str(job.id)) if job.assigned_technician_id else None,
            notification_channels=[],
            event_version=event_version,
            email_managed_by_communication_graph=True,
        )
        logger.info(
            "Legacy status-event routing started",
            extra={
                "job_id": str(job.id),
                "old_status": str(from_status),
                "new_status": str(to_status),
                "event_version": event_version,
                "correlation_id": correlation_id,
                "pipeline": "EventPublisher+NotificationRouter",
            },
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

        async def route_notifications_with_lifecycle():
            from .services.kafka.producer import KafkaProducer

            kafka_producer = None

            try:
                kafka_producer = KafkaProducer()
                await kafka_producer.start()
            except Exception:
                logger.exception(
                    "Kafka lifecycle publisher unavailable. "
                    "Continuing notification delivery without lifecycle events."
                )
                kafka_producer = None

            try:
                if kafka_producer is None:
                    router = NotificationRouter()
                else:
                    async def publish_lifecycle(**kwargs):
                        return await _publish_notification_lifecycle_event(
                            **kwargs,
                            kafka_producer=kafka_producer,
                        )

                    router = NotificationRouter(
                        lifecycle_event_publisher=publish_lifecycle,
                    )

                await router.route(event)

            finally:
                if kafka_producer is not None:
                    try:
                        await kafka_producer.stop()
                    except Exception:
                        logger.exception(
                            "Kafka lifecycle publisher shutdown failed."
                        )

        try:
            if loop.is_running():
                publisher_task = asyncio.ensure_future(
                    EventPublisher().publish(
                        event
                    )
                )

                # Route through the lifecycle-aware router exactly once.
                # route_notifications_with_lifecycle() owns the Kafka producer
                # lifecycle and invokes NotificationRouter.route(event).
                router_task = asyncio.ensure_future(
                    route_notifications_with_lifecycle()
                )

                def log_route_task_failure(task, pipeline):
                    if task.cancelled():
                        return
                    error = task.exception()
                    if error:
                        logger.error(
                            "Legacy status-event routing task failed",
                            exc_info=(
                                type(error),
                                error,
                                error.__traceback__,
                            ),
                            extra={
                                "job_id": str(job_pk),
                                "old_status": str(from_status),
                                "new_status": str(to_status),
                                "event_version": event_version,
                                "correlation_id": correlation_id,
                                "pipeline": pipeline,
                            },
                        )

                publisher_task.add_done_callback(
                    lambda task: log_route_task_failure(
                        task, "EventPublisher"
                    )
                )
                router_task.add_done_callback(
                    lambda task: log_route_task_failure(
                        task, "NotificationRouter"
                    )
                )

            else:
                loop.run_until_complete(
                    EventPublisher().publish(
                        event
                    )
                )

                loop.run_until_complete(
                    route_notifications_with_lifecycle()
                )

        except Exception:
            logger.error(
                "Job transition notification processing "
                "failed.",
                extra={
                    "job_id": str(job_pk),
                    "old_status": from_status_upper,
                    "new_status": to_status_upper,
                    "event_version": event_version,
                    "correlation_id": correlation_id,
                    "pipeline": "EventPublisher+NotificationRouter",
                },
            )

    except Exception as e:
        logger.error(f"Error in process_job_status_transition_task: {e}", exc_info=True)
    finally:
        db.close()


@celery_app.task(
    bind=True,
    name="app.tasks.send_job_event_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def send_job_event_task(
    self,
    job_id: int,
    event_value: str,
    technician_id: int | None = None,
    event_version: int | None = None,
):
    """Send a non-status-transition Communication Agent event.

    The producer must allocate and persist event_version before enqueueing this
    task. Celery retries must reuse the same version; never generate a version
    inside the task.
    """
    from .services.ai.FieldOpsAI.agents.communication_agent.events import JobEvent
    from .services.ai.FieldOpsAI.agents.communication_agent.service import handle

    if event_version is None or event_version < 1:
        raise ValueError(
            "A persisted positive event_version is required for communication notifications"
        )

    db = SessionLocal()
    try:
        event = JobEvent(event_value)
        handle(
            db,
            int(job_id),
            event,
            technician_id=technician_id,
            version=event_version,
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@celery_app.task(name="app.tasks.process_transactional_email_outbox")
def process_transactional_email_outbox_task(limit: int = 50):
    """Deliver persisted transactional messages directly through Gmail SMTP."""
    from .services.email.transactional_outbox import process_due_emails

    db = SessionLocal()
    try:
        return process_due_emails(db, limit=limit)
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


async def _publish_sla_lifecycle_event(
    *,
    event_type: str,
    event_id: str,
    job_id: str,
    tenant_id: str,
    correlation_id: Optional[str] = None,
    payload: Optional[dict] = None,
) -> bool:
    """Publish an SLA lifecycle event using a worker-local Kafka producer."""
    from .services.kafka.producer import KafkaProducer
    from .services.sla_event_producer import SLAEventProducer

    kafka_producer = KafkaProducer()
    await kafka_producer.start()

    try:
        producer = SLAEventProducer(kafka_producer)
        return await producer.publish(
            event_type=event_type,
            event_id=event_id,
            job_id=job_id,
            tenant_id=tenant_id,
            correlation_id=correlation_id,
            payload=payload,
        )
    finally:
        await kafka_producer.stop()


async def _publish_notification_lifecycle_event(
    *,
    event_type: str,
    event_id: str,
    job_id: str,
    tenant_id: str,
    correlation_id: Optional[str] = None,
    payload: Optional[dict] = None,
    kafka_producer=None,
) -> bool:
    """Publish a notification lifecycle event."""
    from .services.kafka.producer import KafkaProducer
    from .services.notification_event_producer import NotificationEventProducer

    owns_producer = kafka_producer is None

    if owns_producer:
        kafka_producer = KafkaProducer()
        await kafka_producer.start()

    try:
        producer = NotificationEventProducer(kafka_producer)
        return await producer.publish(
            event_type=event_type,
            event_id=event_id,
            job_id=job_id,
            tenant_id=tenant_id,
            correlation_id=correlation_id,
            payload=payload,
        )
    finally:
        if owns_producer:
            await kafka_producer.stop()


async def _publish_invoice_lifecycle_event(
    *,
    event_type: str,
    event_id: str,
    job_id: str,
    tenant_id: str,
    invoice_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    payload: Optional[dict] = None,
    kafka_producer=None,
    topic: Optional[str] = None,
) -> dict:
    """Publish an invoice lifecycle event."""
    from .services.kafka.producer import KafkaProducer
    from .services.invoice_event_producer import InvoiceEventProducer

    owns_producer = kafka_producer is None

    if owns_producer:
        kafka_producer = KafkaProducer()
        await kafka_producer.start()

    try:
        producer = InvoiceEventProducer(kafka_producer, topic=topic)
        return await producer.publish(
            event_type=event_type,
            event_id=event_id,
            job_id=job_id,
            tenant_id=tenant_id,
            invoice_id=invoice_id,
            correlation_id=correlation_id,
            payload=payload,
        )
    finally:
        if owns_producer:
            await kafka_producer.stop()


def _publish_invoice_event_once(
    *,
    redis,
    event_type: str,
    event_id: str,
    job_id: str,
    tenant_id: str,
    invoice_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    payload: Optional[dict] = None,
    topic: Optional[str] = None,
) -> dict:
    """Publish an invoice event once using a stable Redis idempotency marker."""
    import asyncio

    marker_key = f"invoice:event_published:{event_id}"

    if redis and redis.get(marker_key):
        return {
            "status": "PUBLISHED",
            "event_type": event_type,
            "event_id": event_id,
            "topic": topic or "fieldops.events",
            "schema_version": 1,
            "idempotent_duplicate": True,
        }

    try:
        result = asyncio.run(
            _publish_invoice_lifecycle_event(
                event_type=event_type,
                event_id=event_id,
                job_id=job_id,
                tenant_id=tenant_id,
                invoice_id=invoice_id,
                correlation_id=correlation_id,
                payload=payload,
                topic=topic,
            )
        )

        if result and result.get("status") == "PUBLISHED" and redis:
            redis.set(marker_key, "1", ex=86400 * 7)

        return result
    except Exception:
        logger.exception(
            "Failed to publish invoice lifecycle event: "
            "event_type=%s job_id=%s event_id=%s",
            event_type,
            job_id,
            event_id,
        )
        return {
            "status": "FAILED",
            "event_type": event_type,
            "event_id": event_id,
            "topic": topic or "fieldops.events",
            "schema_version": 1,
        }


@celery_app.task
def publish_invoice_event_task(
    event_type: str,
    event_id: str,
    job_id: str,
    tenant_id: str,
    invoice_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    payload: Optional[dict] = None,
    topic: Optional[str] = None,
):
    """Celery background task to publish invoice lifecycle event."""
    redis_client = get_redis_client()
    return _publish_invoice_event_once(
        redis=redis_client,
        event_type=event_type,
        event_id=event_id,
        job_id=job_id,
        tenant_id=tenant_id,
        invoice_id=invoice_id,
        correlation_id=correlation_id,
        payload=payload,
        topic=topic,
    )


async def _publish_payment_lifecycle_event(
    *,
    event_type: str,
    event_id: str,
    job_id: str,
    tenant_id: str,
    payment_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    payload: Optional[dict] = None,
    kafka_producer=None,
    topic: Optional[str] = None,
) -> dict:
    """Publish a payment lifecycle event."""
    from .services.kafka.producer import KafkaProducer
    from .services.payment_event_producer import PaymentEventProducer

    owns_producer = kafka_producer is None

    if owns_producer:
        kafka_producer = KafkaProducer()
        await kafka_producer.start()

    try:
        producer = PaymentEventProducer(kafka_producer, topic=topic)
        return await producer.publish(
            event_type=event_type,
            event_id=event_id,
            job_id=job_id,
            tenant_id=tenant_id,
            payment_id=payment_id,
            correlation_id=correlation_id,
            payload=payload,
        )
    finally:
        if owns_producer:
            await kafka_producer.stop()


def _publish_payment_event_once(
    *,
    redis,
    event_type: str,
    event_id: str,
    job_id: str,
    tenant_id: str,
    payment_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    payload: Optional[dict] = None,
    topic: Optional[str] = None,
) -> dict:
    """Publish a payment event once using a stable Redis idempotency marker."""
    import asyncio

    marker_key = f"payment:event_published:{event_id}"

    if redis and redis.get(marker_key):
        return {
            "status": "PUBLISHED",
            "event_type": event_type,
            "event_id": event_id,
            "topic": topic or "fieldops.events",
            "schema_version": 1,
            "idempotent_duplicate": True,
        }

    try:
        result = asyncio.run(
            _publish_payment_lifecycle_event(
                event_type=event_type,
                event_id=event_id,
                job_id=job_id,
                tenant_id=tenant_id,
                payment_id=payment_id,
                correlation_id=correlation_id,
                payload=payload,
                topic=topic,
            )
        )

        if result and result.get("status") == "PUBLISHED" and redis:
            redis.set(marker_key, "1", ex=86400 * 7)

        return result
    except Exception:
        logger.exception(
            "Failed to publish payment lifecycle event: "
            "event_type=%s job_id=%s event_id=%s",
            event_type,
            job_id,
            event_id,
        )
        return {
            "status": "FAILED",
            "event_type": event_type,
            "event_id": event_id,
            "topic": topic or "fieldops.events",
            "schema_version": 1,
        }


@celery_app.task
def publish_payment_event_task(
    event_type: str,
    event_id: str,
    job_id: str,
    tenant_id: str,
    payment_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    payload: Optional[dict] = None,
    topic: Optional[str] = None,
):
    """Celery background task to publish payment lifecycle event."""
    redis_client = get_redis_client()
    return _publish_payment_event_once(
        redis=redis_client,
        event_type=event_type,
        event_id=event_id,
        job_id=job_id,
        tenant_id=tenant_id,
        payment_id=payment_id,
        correlation_id=correlation_id,
        payload=payload,
        topic=topic,
    )


async def _publish_audit_lifecycle_event(
    *,
    event_type: str,
    event_id: str,
    tenant_id: str,
    job_id: Optional[str] = None,
    user_id: Optional[str] = None,
    action: Optional[str] = None,
    correlation_id: Optional[str] = None,
    payload: Optional[dict] = None,
    kafka_producer=None,
    topic: Optional[str] = None,
) -> dict:
    """Publish an approved audit event to Kafka."""
    from .services.kafka.producer import KafkaProducer
    from .services.audit_event_producer import AuditEventProducer

    owns_producer = kafka_producer is None

    if owns_producer:
        kafka_producer = KafkaProducer()
        await kafka_producer.start()

    try:
        producer = AuditEventProducer(kafka_producer, topic=topic)
        return await producer.publish(
            event_type=event_type,
            event_id=event_id,
            tenant_id=tenant_id,
            job_id=job_id,
            user_id=user_id,
            action=action,
            correlation_id=correlation_id,
            payload=payload,
        )
    finally:
        if owns_producer:
            await kafka_producer.stop()


def _publish_audit_event_once(
    *,
    redis,
    event_type: str,
    event_id: str,
    tenant_id: str,
    job_id: Optional[str] = None,
    user_id: Optional[str] = None,
    action: Optional[str] = None,
    correlation_id: Optional[str] = None,
    payload: Optional[dict] = None,
    topic: Optional[str] = None,
) -> dict:
    """Publish an audit event once using a stable Redis idempotency marker."""
    import asyncio

    marker_key = f"audit:event_published:{event_id}"

    if redis and redis.get(marker_key):
        return {
            "status": "PUBLISHED",
            "event_type": event_type,
            "event_id": event_id,
            "topic": topic or "fieldops.events",
            "schema_version": 1,
            "idempotent_duplicate": True,
        }

    try:
        result = asyncio.run(
            _publish_audit_lifecycle_event(
                event_type=event_type,
                event_id=event_id,
                tenant_id=tenant_id,
                job_id=job_id,
                user_id=user_id,
                action=action,
                correlation_id=correlation_id,
                payload=payload,
                topic=topic,
            )
        )

        if result and result.get("status") == "PUBLISHED" and redis:
            redis.set(marker_key, "1", ex=86400 * 7)

        return result
    except Exception:
        logger.exception(
            "Failed to publish audit event: "
            "event_type=%s tenant_id=%s event_id=%s",
            event_type,
            tenant_id,
            event_id,
        )
        return {
            "status": "FAILED",
            "event_type": event_type,
            "event_id": event_id,
            "topic": topic or "fieldops.events",
            "schema_version": 1,
        }


@celery_app.task
def publish_audit_event_task(
    event_type: str,
    event_id: str,
    tenant_id: str,
    job_id: Optional[str] = None,
    user_id: Optional[str] = None,
    action: Optional[str] = None,
    correlation_id: Optional[str] = None,
    payload: Optional[dict] = None,
    topic: Optional[str] = None,
):
    """Celery background task to publish audit event."""
    redis_client = get_redis_client()
    return _publish_audit_event_once(
        redis=redis_client,
        event_type=event_type,
        event_id=event_id,
        tenant_id=tenant_id,
        job_id=job_id,
        user_id=user_id,
        action=action,
        correlation_id=correlation_id,
        payload=payload,
        topic=topic,
    )


def _process_dispatch_event_once(
    *,
    redis,
    event_payload: dict,
    attempt: int = 1,
) -> dict:
    """Process a dispatch event once using a stable Redis idempotency marker."""
    import asyncio
    from .services.dispatch_consumer import DispatchConsumer

    event_id = event_payload.get("event_id") if isinstance(event_payload, dict) else None
    if not event_id:
        return {
            "status": "FAILED",
            "consumer": "dispatch",
            "event_id": "unknown",
            "attempt": attempt,
            "error": "Missing event_id in event_payload",
        }

    marker_key = f"dispatch:event_processed:{event_id}"
    if redis and redis.get(marker_key):
        logger.info(
            "Dispatch event %s already processed; skipping duplicate.",
            event_id,
        )
        return {
            "status": "PROCESSED",
            "consumer": "dispatch",
            "event_id": event_id,
            "attempt": attempt,
            "idempotent_duplicate": True,
        }

    consumer = DispatchConsumer(redis_client=redis)
    result = asyncio.run(consumer.process_event(event_payload, attempt=attempt))
    return dict(result)


@celery_app.task
def process_dispatch_event_task(
    event_payload: dict,
    attempt: int = 1,
):
    """Celery background task to process consumed dispatch event."""
    redis_client = get_redis_client()
    return _process_dispatch_event_once(
        redis=redis_client,
        event_payload=event_payload,
        attempt=attempt,
    )


def _process_gps_tracking_event_once(
    *,
    redis,
    event_payload: dict,
    attempt: int = 1,
) -> dict:
    """Process a GPS tracking event once using a stable Redis idempotency marker."""
    import asyncio
    from .services.gps_tracking_consumer import GPSTrackingConsumer

    event_id = event_payload.get("event_id") if isinstance(event_payload, dict) else None
    if not event_id:
        return {
            "status": "FAILED",
            "consumer": "GPS_tracking",
            "event_id": "unknown",
            "attempt": attempt,
            "error": "Missing event_id in event_payload",
        }

    marker_key = f"gps:event_processed:{event_id}"
    if redis and redis.get(marker_key):
        logger.info(
            "GPS event %s already processed; skipping duplicate.",
            event_id,
        )
        return {
            "status": "PROCESSED",
            "consumer": "GPS_tracking",
            "event_id": event_id,
            "attempt": attempt,
            "idempotent_duplicate": True,
        }

    consumer = GPSTrackingConsumer(redis_client=redis)
    result = asyncio.run(consumer.process_event(event_payload, attempt=attempt))
    return dict(result)


@celery_app.task
def process_gps_tracking_event_task(
    event_payload: dict,
    attempt: int = 1,
):
    """Celery background task to process consumed GPS tracking event."""
    redis_client = get_redis_client()
    return _process_gps_tracking_event_once(
        redis=redis_client,
        event_payload=event_payload,
        attempt=attempt,
    )


def _process_notification_event_once(
    *,
    redis,
    event_payload: dict,
    attempt: int = 1,
) -> dict:
    """Process a notification event once using a stable Redis idempotency marker."""
    import asyncio
    from .services.notification_consumer import NotificationConsumer

    event_id = event_payload.get("event_id") if isinstance(event_payload, dict) else None
    if not event_id:
        return {
            "status": "FAILED",
            "consumer": "notification",
            "event_id": "unknown",
            "attempt": attempt,
            "error": "Missing event_id in event_payload",
        }

    marker_key = f"notification:event_processed:{event_id}"
    if redis and redis.get(marker_key):
        logger.info(
            "Notification event %s already processed; skipping duplicate.",
            event_id,
        )
        return {
            "status": "PROCESSED",
            "consumer": "notification",
            "event_id": event_id,
            "attempt": attempt,
            "idempotent_duplicate": True,
        }

    consumer = NotificationConsumer(redis_client=redis)
    result = asyncio.run(consumer.process_event(event_payload, attempt=attempt))
    return dict(result)


@celery_app.task
def process_notification_event_task(
    event_payload: dict,
    attempt: int = 1,
):
    """Celery background task to process consumed notification event."""
    redis_client = get_redis_client()
    return _process_notification_event_once(
        redis=redis_client,
        event_payload=event_payload,
        attempt=attempt,
    )


def _process_sla_monitoring_event_once(
    *,
    redis,
    event_payload: dict,
    attempt: int = 1,
) -> dict:
    """Process an SLA monitoring event once using a stable Redis idempotency marker."""
    import asyncio
    from .services.sla_monitoring_consumer import SLAMonitoringConsumer

    event_id = event_payload.get("event_id") if isinstance(event_payload, dict) else None
    if not event_id:
        return {
            "status": "FAILED",
            "consumer": "SLA_monitoring",
            "event_id": "unknown",
            "attempt": attempt,
            "error": "Missing event_id in event_payload",
        }

    marker_key = f"sla:event_processed:{event_id}"
    if redis and redis.get(marker_key):
        logger.info(
            "SLA event %s already processed; skipping duplicate.",
            event_id,
        )
        return {
            "status": "PROCESSED",
            "consumer": "SLA_monitoring",
            "event_id": event_id,
            "attempt": attempt,
            "idempotent_duplicate": True,
        }

    consumer = SLAMonitoringConsumer(redis_client=redis)
    result = asyncio.run(consumer.process_event(event_payload, attempt=attempt))
    return dict(result)


@celery_app.task
def process_sla_monitoring_event_task(
    event_payload: dict,
    attempt: int = 1,
):
    """Celery background task to process consumed SLA monitoring event."""
    redis_client = get_redis_client()
    return _process_sla_monitoring_event_once(
        redis=redis_client,
        event_payload=event_payload,
        attempt=attempt,
    )


def _process_billing_event_once(
    *,
    redis,
    event_payload: dict,
    attempt: int = 1,
) -> dict:
    """Process a billing event once using a stable Redis idempotency marker."""
    import asyncio
    from .services.billing_consumer import BillingConsumer

    event_id = event_payload.get("event_id") if isinstance(event_payload, dict) else None
    if not event_id:
        return {
            "status": "FAILED",
            "consumer": "billing",
            "event_id": "unknown",
            "attempt": attempt,
            "error": "Missing event_id in event_payload",
        }

    marker_key = f"billing:event_processed:{event_id}"
    if redis and redis.get(marker_key):
        logger.info(
            "Billing event %s already processed; skipping duplicate.",
            event_id,
        )
        return {
            "status": "PROCESSED",
            "consumer": "billing",
            "event_id": event_id,
            "attempt": attempt,
            "idempotent_duplicate": True,
        }

    consumer = BillingConsumer(redis_client=redis)
    result = asyncio.run(consumer.process_event(event_payload, attempt=attempt))
    return dict(result)


@celery_app.task
def process_billing_event_task(
    event_payload: dict,
    attempt: int = 1,
):
    """Celery background task to process consumed billing event."""
    redis_client = get_redis_client()
    return _process_billing_event_once(
        redis=redis_client,
        event_payload=event_payload,
        attempt=attempt,
    )


def _process_payment_event_once(
    *,
    redis,
    event_payload: dict,
    attempt: int = 1,
) -> dict:
    """Process a payment event once using a stable Redis idempotency marker."""
    import asyncio
    from .services.payment_consumer import PaymentConsumer

    event_id = event_payload.get("event_id") if isinstance(event_payload, dict) else None
    if not event_id:
        return {
            "status": "FAILED",
            "consumer": "payment",
            "event_id": "unknown",
            "attempt": attempt,
            "error": "Missing event_id in payment event payload",
        }

    marker_key = f"payment:event_processed:{event_id}"
    if redis and redis.get(marker_key):
        logger.info(
            "Payment event %s already processed; skipping duplicate.",
            event_id,
        )
        return {
            "status": "PROCESSED",
            "consumer": "payment",
            "event_id": event_id,
            "attempt": attempt,
            "idempotent_duplicate": True,
        }

    consumer = PaymentConsumer(redis_client=redis)
    result = asyncio.run(consumer.process_event(event_payload, attempt=attempt))
    return dict(result)


@celery_app.task
def process_payment_event_task(
    event_payload: dict,
    attempt: int = 1,
):
    """Celery background task to process consumed payment event."""
    redis_client = get_redis_client()
    return _process_payment_event_once(
        redis=redis_client,
        event_payload=event_payload,
        attempt=attempt,
    )


def _process_audit_event_once(
    *,
    redis,
    event_payload: dict,
    attempt: int = 1,
) -> dict:
    """Process an audit event once using a stable Redis idempotency marker."""
    import asyncio
    from .services.audit_consumer import AuditConsumer

    event_id = event_payload.get("event_id") if isinstance(event_payload, dict) else None
    if not event_id:
        return {
            "status": "FAILED",
            "consumer": "audit",
            "event_id": "unknown",
            "attempt": attempt,
            "error": "Missing event_id in audit event payload",
        }

    marker_key = f"audit:event_processed:{event_id}"
    if redis and redis.get(marker_key):
        logger.info(
            "Audit event %s already processed; skipping duplicate.",
            event_id,
        )
        return {
            "status": "PROCESSED",
            "consumer": "audit",
            "event_id": event_id,
            "attempt": attempt,
            "idempotent_duplicate": True,
        }

    consumer = AuditConsumer(redis_client=redis)
    result = asyncio.run(consumer.process_event(event_payload, attempt=attempt))
    return dict(result)


@celery_app.task
def process_audit_event_task(
    event_payload: dict,
    attempt: int = 1,
):
    """Celery background task to process consumed audit event."""
    redis_client = get_redis_client()
    return _process_audit_event_once(
        redis=redis_client,
        event_payload=event_payload,
        attempt=attempt,
    )


def _process_analytics_event_once(
    *,
    redis,
    event_payload: dict,
    attempt: int = 1,
) -> dict:
    """Process an analytics event once using a stable Redis idempotency marker."""
    import asyncio
    from .services.analytics_consumer import AnalyticsConsumer

    event_id = event_payload.get("event_id") if isinstance(event_payload, dict) else None
    if not event_id:
        return {
            "status": "FAILED",
            "consumer": "analytics",
            "event_id": "unknown",
            "attempt": attempt,
            "error": "Missing event_id in analytics event payload",
        }

    marker_key = f"analytics:event_processed:{event_id}"
    if redis and redis.get(marker_key):
        logger.info(
            "Analytics event %s already processed; skipping duplicate.",
            event_id,
        )
        return {
            "status": "PROCESSED",
            "consumer": "analytics",
            "event_id": event_id,
            "attempt": attempt,
            "idempotent_duplicate": True,
        }

    consumer = AnalyticsConsumer(redis_client=redis)
    result = asyncio.run(consumer.process_event(event_payload, attempt=attempt))
    return dict(result)


@celery_app.task
def process_analytics_event_task(
    event_payload: dict,
    attempt: int = 1,
):
    """Celery background task to process consumed analytics event."""
    redis_client = get_redis_client()
    return _process_analytics_event_once(
        redis=redis_client,
        event_payload=event_payload,
        attempt=attempt,
    )


def _process_error_handling_event_once(
    *,
    redis,
    event_payload: dict,
    attempt: int = 1,
) -> dict:
    """Process an event via the error handling consumer once using a stable Redis idempotency marker."""
    import asyncio
    from .services.consumer_error_handler import ConsumerErrorHandler

    event_id = event_payload.get("event_id") if isinstance(event_payload, dict) else None
    if not event_id:
        return {
            "status": "FAILED",
            "consumer": "Add_error_handling",
            "event_id": "unknown",
            "attempt": attempt,
            "error": "Missing event_id in event payload",
        }

    marker_key = f"consumer_error_handling:event_processed:{event_id}"
    if redis and redis.get(marker_key):
        logger.info(
            "Error handling event %s already processed; skipping duplicate.",
            event_id,
        )
        return {
            "status": "PROCESSED",
            "consumer": "Add_error_handling",
            "event_id": event_id,
            "attempt": attempt,
            "idempotent_duplicate": True,
        }

    consumer = ConsumerErrorHandler(redis_client=redis)
    result = asyncio.run(consumer.process_event(event_payload, attempt=attempt))
    return dict(result)


@celery_app.task
def process_error_handling_event_task(
    event_payload: dict,
    attempt: int = 1,
):
    """Celery background task to process consumed event with error handling."""
    redis_client = get_redis_client()
    return _process_error_handling_event_once(
        redis=redis_client,
        event_payload=event_payload,
        attempt=attempt,
    )


def _process_retry_mechanism_event_once(
    *,
    redis,
    event_payload: dict,
    attempt: int = 1,
) -> dict:
    """Process an event via the retry mechanism consumer once using a stable Redis idempotency marker."""
    import asyncio
    from .services.consumer_retry_mechanism import ConsumerRetryMechanism

    event_id = event_payload.get("event_id") if isinstance(event_payload, dict) else None
    if not event_id:
        return {
            "status": "FAILED",
            "consumer": "Add_retry_mechanism",
            "event_id": "unknown",
            "attempt": attempt,
            "error": "Missing event_id in event payload",
        }

    marker_key = f"consumer_retry:event_processed:{event_id}"
    if redis and redis.get(marker_key):
        logger.info(
            "Retry mechanism event %s already processed; skipping duplicate.",
            event_id,
        )
        return {
            "status": "PROCESSED",
            "consumer": "Add_retry_mechanism",
            "event_id": event_id,
            "attempt": attempt,
            "idempotent_duplicate": True,
        }

    consumer = ConsumerRetryMechanism(redis_client=redis)
    result = asyncio.run(consumer.process_event(event_payload, attempt=attempt))
    return dict(result)


@celery_app.task
def process_retry_mechanism_event_task(
    event_payload: dict,
    attempt: int = 1,
):
    """Celery background task to process consumed event with retry mechanism."""
    redis_client = get_redis_client()
    return _process_retry_mechanism_event_once(
        redis=redis_client,
        event_payload=event_payload,
        attempt=attempt,
    )


def _process_health_checks_event_once(
    *,
    redis,
    event_payload: dict,
    attempt: int = 1,
) -> dict:
    """Process an event via the health checks consumer once using a stable Redis idempotency marker."""
    import asyncio
    from .services.consumer_health_checks import ConsumerHealthChecks

    event_id = event_payload.get("event_id") if isinstance(event_payload, dict) else None
    if not event_id:
        return {
            "status": "FAILED",
            "consumer": "Add_health_checks",
            "event_id": "unknown",
            "attempt": attempt,
            "error": "Missing event_id in event payload",
        }

    marker_key = f"consumer_health:event_processed:{event_id}"
    if redis and redis.get(marker_key):
        logger.info(
            "Health checks event %s already processed; skipping duplicate.",
            event_id,
        )
        return {
            "status": "PROCESSED",
            "consumer": "Add_health_checks",
            "event_id": event_id,
            "attempt": attempt,
            "idempotent_duplicate": True,
        }

    consumer = ConsumerHealthChecks(redis_client=redis)
    result = asyncio.run(consumer.process_event(event_payload, attempt=attempt))
    return dict(result)


@celery_app.task
def process_health_checks_event_task(
    event_payload: dict,
    attempt: int = 1,
):
    """Celery background task to process consumed event with health checks monitoring."""
    redis_client = get_redis_client()
    return _process_health_checks_event_once(
        redis=redis_client,
        event_payload=event_payload,
        attempt=attempt,
    )


def _process_dead_letter_event_once(
    *,
    redis,
    event_payload: dict,
    max_retries: int = 3,
) -> dict:
    """Process an event once through the dead-letter consumer with isolation."""
    import asyncio
    from .services.consumer_dead_letter_topics import ConsumerDeadLetterTopics

    consumer = ConsumerDeadLetterTopics(redis_client=redis, max_retries=max_retries)
    result = asyncio.run(consumer.process_event(event_payload, max_retries=max_retries))
    return dict(result)


@celery_app.task(name="app.tasks.process_dead_letter_event_task")
def process_dead_letter_event_task(
    event_payload: dict,
    max_retries: int = 3,
):
    """Celery background task to process consumed event with dead-letter topic isolation."""
    redis_client = get_redis_client()
    return _process_dead_letter_event_once(
        redis=redis_client,
        event_payload=event_payload,
        max_retries=max_retries,
    )


@celery_app.task(name="app.tasks.replay_dlq_event_task")
def replay_dlq_event_task(
    dlq_record: dict,
    force: bool = False,
):
    """Celery background task to replay an event isolated in the DLQ."""
    import asyncio
    from .services.consumer_dead_letter_topics import ConsumerDeadLetterTopics

    redis_client = get_redis_client()
    consumer = ConsumerDeadLetterTopics(redis_client=redis_client)
    result = asyncio.run(consumer.replay_dlq_event(dlq_record, force=force))
    return dict(result)


def _process_duplicate_prevention_event_once(
    *,
    redis,
    event_payload: dict,
    domain: Optional[str] = None,
    attempt: int = 1,
) -> dict:
    """Process an event once with distributed idempotency and duplicate prevention."""
    import asyncio
    from .services.consumer_idempotency import ConsumerIdempotency

    consumer = ConsumerIdempotency(redis_client=redis)
    result = asyncio.run(consumer.process_event(event_payload, domain=domain, attempt=attempt))
    return dict(result)


@celery_app.task(name="app.tasks.process_duplicate_prevention_event_task")
def process_duplicate_prevention_event_task(
    event_payload: dict,
    domain: Optional[str] = None,
    attempt: int = 1,
):
    """Celery background task to process consumed event with duplicate prevention."""
    redis_client = get_redis_client()
    return _process_duplicate_prevention_event_once(
        redis=redis_client,
        event_payload=event_payload,
        domain=domain,
        attempt=attempt,
    )


@celery_app.task(name="app.tasks.prevent_duplicate_event_processing_task")
def prevent_duplicate_event_processing_task(
    event_payload: dict,
    domain: Optional[str] = None,
    attempt: int = 1,
):
    """Celery task alias conforming to story naming: Prevent duplicate event processing."""
    return process_duplicate_prevention_event_task(
        event_payload=event_payload,
        domain=domain,
        attempt=attempt,
    )


def _process_ordered_event_once(
    *,
    redis,
    event_payload: dict,
    attempt: int = 1,
) -> dict:
    """Process an event once preserving strict aggregate ordering and monotonic progression."""
    import asyncio
    from .services.consumer_event_ordering import ConsumerEventOrdering

    consumer = ConsumerEventOrdering(redis_client=redis)
    result = asyncio.run(consumer.process_event(event_payload, attempt=attempt))
    return dict(result)


@celery_app.task(name="app.tasks.process_ordered_event_task")
def process_ordered_event_task(
    event_payload: dict,
    attempt: int = 1,
):
    """Celery background task to process consumed event with ordering guarantees."""
    redis_client = get_redis_client()
    return _process_ordered_event_once(
        redis=redis_client,
        event_payload=event_payload,
        attempt=attempt,
    )


@celery_app.task(name="app.tasks.maintain_event_ordering_task")
def maintain_event_ordering_task(
    event_payload: dict,
    attempt: int = 1,
):
    """Celery task alias conforming to story naming: Maintain event ordering."""
    return process_ordered_event_task(
        event_payload=event_payload,
        attempt=attempt,
    )


def _process_event_replay_once(
    *,
    redis,
    event_payload: dict,
    operator_role: str = "operator",
    operator_id: Optional[str] = None,
    force: bool = False,
    reason: Optional[str] = None,
) -> dict:
    """Process a controlled event replay once with authorization and idempotency."""
    import asyncio
    from .services.consumer_event_replay import ConsumerEventReplay

    consumer = ConsumerEventReplay(redis_client=redis)
    result = asyncio.run(
        consumer.replay_event(
            event_or_payload=event_payload,
            operator_role=operator_role,
            operator_id=operator_id,
            force=force,
            reason=reason,
        )
    )
    return dict(result)


@celery_app.task(name="app.tasks.process_event_replay_task")
def process_event_replay_task(
    event_payload: dict,
    operator_role: str = "operator",
    operator_id: Optional[str] = None,
    force: bool = False,
    reason: Optional[str] = None,
):
    """Celery background task to safely replay an event."""
    redis_client = get_redis_client()
    return _process_event_replay_once(
        redis=redis_client,
        event_payload=event_payload,
        operator_role=operator_role,
        operator_id=operator_id,
        force=force,
        reason=reason,
    )


@celery_app.task(name="app.tasks.add_event_replay_support_task")
def add_event_replay_support_task(
    event_payload: dict,
    operator_role: str = "operator",
    operator_id: Optional[str] = None,
    force: bool = False,
    reason: Optional[str] = None,
):
    """Celery task alias conforming to story naming: Add event replay support."""
    return process_event_replay_task(
        event_payload=event_payload,
        operator_role=operator_role,
        operator_id=operator_id,
        force=force,
        reason=reason,
    )


@celery_app.task(name="app.tasks.replay_batch_events_task")
def replay_batch_events_task(
    events: list,
    operator_role: str = "operator",
    operator_id: Optional[str] = None,
    force: bool = False,
    reason: Optional[str] = None,
):
    """Celery background task to replay a batch of events."""
    import asyncio
    from .services.consumer_event_replay import ConsumerEventReplay

    redis_client = get_redis_client()
    consumer = ConsumerEventReplay(redis_client=redis_client)
    results = asyncio.run(
        consumer.replay_batch(
            events=events,
            operator_role=operator_role,
            operator_id=operator_id,
            force=force,
            reason=reason,
        )
    )
    return [dict(r) for r in results]




def _publish_sla_event_once(
    *,
    redis,
    event_type: str,
    event_id: str,
    job_id: str,
    tenant_id: str,
    correlation_id: Optional[str] = None,
    payload: Optional[dict] = None,
) -> bool:
    """Publish an SLA event once using a stable Redis idempotency marker."""
    import asyncio

    marker_key = f"sla:event_published:{event_id}"

    if redis and redis.get(marker_key):
        return True

    try:
        published = asyncio.run(
            _publish_sla_lifecycle_event(
                event_type=event_type,
                event_id=event_id,
                job_id=job_id,
                tenant_id=tenant_id,
                correlation_id=correlation_id,
                payload=payload,
            )
        )

        if published and redis:
            redis.set(marker_key, "1", ex=86400 * 7)

        return bool(published)
    except Exception:
        logger.exception(
            "Failed to publish SLA lifecycle event: "
            "event_type=%s job_id=%s event_id=%s",
            event_type,
            job_id,
            event_id,
        )
        return False


@celery_app.task(name="app.tasks.send_customer_daily_engagement")
def send_customer_daily_engagement():
    """Send a useful, opted-in appointment reminder at most once per local day.

    The task intentionally skips customers without a job scheduled for their
    local date. Tenant rollout is controlled by the organization setting
    ``customer_daily_engagement_enabled`` (false unless explicitly enabled).
    """
    from sqlalchemy import func
    from .models import CustomerProfile, Job, Organization
    from .services.ai.FieldOpsAI.agents.communication_agent.store import insert_daily_engagement
    from .services.ai.FieldOpsAI.agents.communication_agent.channels import push_live

    db = SessionLocal()
    sent = 0
    now = datetime.now(timezone.utc)
    try:
        profiles = db.query(CustomerProfile).filter(
            CustomerProfile.daily_engagement_enabled.is_(True),
            CustomerProfile.portal_enabled.is_(True),
        ).all()
        for profile in profiles:
            try:
                organization = db.get(Organization, profile.tenant_id)
                settings = (organization.settings or {}) if organization else {}
                if not organization or organization.status != "ACTIVE" or not settings.get("customer_daily_engagement_enabled", False):
                    continue
                local_now = now.astimezone(ZoneInfo(profile.timezone or "UTC"))
                local_time = local_now.strftime("%H:%M")
                start, end = profile.quiet_hours_start, profile.quiet_hours_end
                in_quiet_hours = (start <= local_time < end) if start < end else (local_time >= start or local_time < end)
                if in_quiet_hours:
                    continue
                scheduled = db.query(Job).filter(
                    Job.customer_id == profile.customer_id,
                    func.coalesce(Job.customer_tenant_id, Job.tenant_id) == profile.tenant_id,
                    Job.preferred_service_date == local_now.date(),
                    ~func.upper(Job.status).in_(("COMPLETED", "CANCELLED", "CANCELED", "CLOSED")),
                ).order_by(Job.id.asc()).first()
                if not scheduled:
                    continue
                day_key = local_now.date().isoformat()
                variants = (
                    f"Your {scheduled.service_type} visit (request #{scheduled.id}) is scheduled for today. Keep this update handy here.",
                    f"A quick heads-up: request #{scheduled.id} for {scheduled.service_type} is booked for today.",
                    f"Today's the day for request #{scheduled.id} ({scheduled.service_type}). You can revisit the details whenever you need.",
                )
                digest = hashlib.sha256(f"{profile.tenant_id}|{profile.customer_id}|{day_key}".encode()).digest()
                body = variants[int.from_bytes(digest[:4], "big") % len(variants)]
                notification_id = insert_daily_engagement(
                    db,
                    tenant_id=profile.tenant_id,
                    recipient_id=profile.customer_id,
                    local_date=day_key,
                    title="Your service visit today",
                    body=body,
                    job_id=scheduled.id,
                )
                if notification_id is None:
                    db.rollback()
                    continue
                db.commit()
                push_live(
                    "customer", profile.tenant_id, scheduled.id,
                    {
                        "type": "notification",
                        "id": notification_id,
                        "group_key": f"daily_engagement_{day_key}",
                        "job_id": str(scheduled.id),
                        "recipient_role": "customer",
                        "recipient_id": profile.customer_id,
                        "event": "engagement_daily",
                        "event_version": 0,
                        "title": "Your service visit today",
                        "body": body,
                        "status": "UNREAD",
                        "created_at": now.isoformat(),
                        "notification_metadata": {"category": "engagement", "purpose": "daily_service_reminder", "local_date": day_key},
                    },
                    correlation_id=f"daily-engagement:{profile.tenant_id}:{profile.customer_id}:{day_key}",
                )
                sent += 1
            except Exception:
                db.rollback()
                logger.exception("Daily customer engagement processing failed", extra={"tenant_id": profile.tenant_id})
        return sent
    finally:
        db.close()
@celery_app.task
def broadcast_sla_countdown():
    from .database import SessionLocal
    from .models import Job
    from .services.sla_service import SLAService
    from .services.socket_manager import ws_manager
    import asyncio

    redis_client = get_redis_client()
    db = SessionLocal()
    try:
        jobs = db.query(Job).filter(Job.status.in_(["ASSIGNED", "EN_ROUTE", "ON_SITE"])).all()
        sla = SLAService()
        
        for job in jobs:
            state = sla.get_sla_state(str(job.id))
            if state:
                # Publish near-breach and breach events only after the
                # authoritative SLA state has been calculated.
                tenant_id = str(job.tenant_id or "tenant-1")
                job_id_str = str(job.id)

                if state.get("is_breached"):
                    breach_event_id = (
                        f"sla-breached:{tenant_id}:{job_id_str}"
                    )
                    _publish_sla_event_once(
                        redis=redis_client,
                        event_type="SLA_BREACHED",
                        event_id=breach_event_id,
                        job_id=job_id_str,
                        tenant_id=tenant_id,
                        payload={
                            "sla_deadline": state.get("sla_deadline"),
                            "remaining_seconds": state.get(
                                "remaining_seconds"
                            ),
                            "status": state.get("status"),
                            "timestamp": datetime.now(
                                timezone.utc
                            ).isoformat(),
                        },
                    )
                elif state.get("is_critical"):
                    near_breach_event_id = (
                        f"sla-near-breach:{tenant_id}:{job_id_str}"
                    )
                    _publish_sla_event_once(
                        redis=redis_client,
                        event_type="SLA_NEAR_BREACH",
                        event_id=near_breach_event_id,
                        job_id=job_id_str,
                        tenant_id=tenant_id,
                        payload={
                            "sla_deadline": state.get("sla_deadline"),
                            "remaining_seconds": state.get(
                                "remaining_seconds"
                            ),
                            "status": state.get("status"),
                            "timestamp": datetime.now(
                                timezone.utc
                            ).isoformat(),
                        },
                    )

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

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def send_sms_async(
    self,
    to_number: str,
    body: str,
    from_number: str | None = None,
):
    # Send SMS in a Celery worker so the API request remains non-blocking.
    service = TwilioSMSService()

    return service.send_sms(
        to_number=to_number,
        body=body,
        from_number=from_number,
    )


def _build_customer_invoice_pdf_attachment(
    delivery_id: int,
    job_id: int,
    closure_id: int,
) -> dict | None:
    """Build the existing PDF only for the customer who owns this invoice."""
    import asyncio
    from types import SimpleNamespace

    from .models import Job
    from .models.job_closure import JobClosure
    from .models_legacy import InAppNotification, NotificationChannelDelivery

    db = SessionLocal()
    try:
        delivery = (
            db.query(NotificationChannelDelivery)
            .filter(NotificationChannelDelivery.id == int(delivery_id))
            .first()
        )
        notification = (
            db.get(InAppNotification, delivery.notification_id)
            if delivery
            else None
        )
        job = db.get(Job, int(job_id))
        closure = (
            db.query(JobClosure)
            .filter(
                JobClosure.id == int(closure_id),
                JobClosure.job_id == int(job_id),
                JobClosure.tenant_id == (job.tenant_id if job else None),
            )
            .first()
        )
        if not (
            delivery
            and notification
            and job
            and closure
            and delivery.channel == "email"
            and str(notification.tenant_id) == str(delivery.tenant_id)
            and str(notification.job_id) == str(job.id)
            and notification.recipient_role == "customer"
            and str(notification.recipient_id) == str(job.customer_id)
            and str(delivery.tenant_id)
            == str(job.customer_tenant_id or job.tenant_id)
            and str(job.status).upper() == "COMPLETED"
        ):
            logger.warning(
                "Invoice PDF attachment skipped by ownership check",
                extra={"delivery_id": int(delivery_id), "job_id": int(job_id)},
            )
            return None

        # Reuse the existing, tenant-scoped PDF generator. Its job tenant is
        # established above, while customer ownership was checked through the
        # committed notification row and the persisted job.
        from .routes.jobs import download_job_invoice_pdf

        response = download_job_invoice_pdf(
            int(job_id),
            current_user=SimpleNamespace(tenant_id=str(job.tenant_id)),
            db=db,
        )

        async def read_body() -> bytes:
            chunks = []
            async for chunk in response.body_iterator:
                chunks.append(chunk)
            return b"".join(chunks)

        pdf_bytes = asyncio.run(read_body())
        if not pdf_bytes.startswith(b"%PDF"):
            raise ValueError("Invoice PDF generator returned invalid content")
        return {
            "filename": f"invoice_job_{job.id}.pdf",
            "content": pdf_bytes,
            "content_type": "application/pdf",
        }
    except Exception:
        logger.warning(
            "Invoice PDF attachment generation failed; email will include secure link",
            extra={"delivery_id": int(delivery_id), "job_id": int(job_id)},
        )
        return None
    finally:
        db.close()


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)


def send_bulk_sms_async(
    self,
    recipients: list[str],
    body: str,
    from_number: str | None = None,
):
    # Process bulk SMS delivery in a Celery worker.
    # Each recipient is handled independently by the SMS service.
    service = TwilioSMSService()

    return service.send_bulk_sms(
        recipients=recipients,
        body=body,
        from_number=from_number,
    )


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)

def send_email_async(
    self,
    to_email: str,
    subject: str,
    html_body: str,
    plain_text: str | None = None,
    attachments: list[dict] | None = None,
    delivery_id: int | None = None,
    invoice_job_id: int | None = None,
    invoice_closure_id: int | None = None,
):
    """
    Send an email asynchronously through the configured SMTP relay.

    The API request only queues this task. The actual SMTP
    delivery happens inside the Celery worker.
    """
    service = SMTPEmailService()
    safe_delivery_id = int(delivery_id) if delivery_id is not None else None
    logger.info(
        "Email delivery attempt started",
        extra={"delivery_id": safe_delivery_id,
               "job_id": str(invoice_job_id) if invoice_job_id is not None else None},
    )

    if (
        delivery_id is not None
        and invoice_job_id is not None
        and invoice_closure_id is not None
    ):
        invoice_attachment = _build_customer_invoice_pdf_attachment(
            int(delivery_id), int(invoice_job_id), int(invoice_closure_id)
        )
        if invoice_attachment:
            attachments = [*(attachments or []), invoice_attachment]

    delivery_db = None
    if delivery_id is not None:
        from .services.ai.FieldOpsAI.agents.communication_agent.channels import begin_delivery_attempt

        delivery_db = SessionLocal()
        try:
            begin_delivery_attempt(delivery_db, int(delivery_id))
        finally:
            delivery_db.close()

    import asyncio

    result = asyncio.run(
        service.send_email(
            to_email=to_email,
            subject=subject,
            html_body=html_body,
            plain_text=plain_text,
            attachments=attachments,
            message_id=(
                f"<delivery-{int(delivery_id)}@fieldops.local>"
                if delivery_id is not None
                else None
            ),
        )
    )

    transient = (
        result.status_code in {421, 450, 451, 452, 500, 502, 503, 504}
        or (
            result.status_code is None
            and "transport" in (result.error or "").lower()
        )
    )
    permanent_recipient_failure = (
        result.status_code in {550, 551, 553}
        or result.error in {
            "Recipient email is required.",
            "Invalid recipient email address.",
        }
    )
    if transient and self.request.retries < self.max_retries:
        logger.warning(
            "Email delivery will retry",
            extra={"delivery_id": safe_delivery_id,
                   "job_id": str(invoice_job_id) if invoice_job_id is not None else None,
                   "smtp_status": result.status_code,
                   "reason": "temporary_provider_failure",
                   "retry_number": self.request.retries + 1},
        )
        raise self.retry(
            exc=RuntimeError("Temporary email provider failure"),
            countdown=2 ** (self.request.retries + 1),
        )

    if delivery_id is not None:
        from .models_legacy import InAppNotification, NotificationChannelDelivery
        from .services.ai.FieldOpsAI.agents.communication_agent.channels import mark_delivery

        delivery_db = SessionLocal()
        try:
            delivery_context = (
                delivery_db.query(
                    InAppNotification.type,
                    InAppNotification.job_id,
                )
                .join(
                    NotificationChannelDelivery,
                    NotificationChannelDelivery.notification_id
                    == InAppNotification.id,
                )
                .filter(NotificationChannelDelivery.id == int(delivery_id))
                .first()
            )
            delivery_status = (
                "accepted" if result.success
                else "permanent_failure" if permanent_recipient_failure
                else "failed"
            )
            mark_delivery(
                delivery_db,
                int(delivery_id),
                delivery_status,
                None if result.success else (result.error or "email provider rejected message")[:500],
                provider_id=result.message_id,
                increment_attempt=False,
            )
            logger.info(
                "Email delivery attempt finished: %s",
                "sent" if result.success else "not sent",
                extra={
                    "delivery_id": int(delivery_id),
                    "job_id": str(delivery_context.job_id) if delivery_context else None,
                    "event_type": delivery_context.type if delivery_context else None,
                    "delivery_status": delivery_status,
                    "provider_message_id": result.message_id,
                    "smtp_status": result.status_code,
                    "reason": None if result.success else (
                        "invalid_or_rejected_recipient" if permanent_recipient_failure
                        else "temporary_provider_failure" if transient
                        else "smtp_delivery_failed"
                    ),
                },
            )
        finally:
            delivery_db.close()
    elif not result.success:
        logger.warning(
            "Email delivery attempt finished: not sent",
            extra={"smtp_status": result.status_code,
                   "reason": "invalid_or_rejected_recipient" if permanent_recipient_failure
                   else "temporary_provider_failure" if transient else "smtp_delivery_failed"},
        )
    else:
        logger.info("Email delivery attempt finished: sent")

    return {
        "success": result.success,
        "message_id": result.message_id,
        "status_code": result.status_code,
        "error": result.error,
        "simulated": result.simulated,
    }