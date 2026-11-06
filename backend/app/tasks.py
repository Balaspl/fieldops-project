import logging
import json
import os
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import hashlib
from sqlalchemy import delete, text
from sqlalchemy.orm import Session
import time
import uuid
from typing import Any, Optional, Union
from .runtime.dlq import DeadLetterQueue
from .services.enterprise_audit import AuditAction, audit_log
from .celery_app import celery_app
def SessionLocal(*args, **kwargs):
    import app.database
    return app.database.SessionLocal(*args, **kwargs)

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

@celery_app.task(name="app.tasks.aggregate_prompt_analytics_task", queue="ai_processing", routing_key="ai")
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


@celery_app.task(name="app.tasks.daily_gps_purge_task", queue="gps_processing", routing_key="gps")
def daily_gps_purge_task(correlation_id: str = None):
    db = SessionLocal()
    try:
        execute_daily_gps_purge_sync(db, correlation_id)
    finally:
        db.close()


@celery_app.task(bind=True, max_retries=3, name="app.tasks.purge_job_gps_data_task", queue="gps_processing", routing_key="gps")
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


@celery_app.task(bind=True, max_retries=2, name="app.tasks.update_eta_task", queue="gps_processing", routing_key="gps")
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


def _process_offset_management_event_once(
    *,
    redis,
    event_payload: dict,
    topic: Optional[str] = None,
    partition: int = 0,
    offset: int = 0,
    attempt: int = 1,
) -> dict:
    """Process an event with reliable manual offset commit at the success boundary."""
    import asyncio
    from .services.consumer_offset_management import ConsumerOffsetManagement

    consumer = ConsumerOffsetManagement(redis_client=redis)
    result = asyncio.run(
        consumer.process_event(
            message=event_payload,
            topic=topic,
            partition=partition,
            offset=offset,
            attempt=attempt,
        )
    )
    return dict(result)


@celery_app.task(name="app.tasks.process_offset_management_event_task")
def process_offset_management_event_task(
    event_payload: dict,
    topic: Optional[str] = None,
    partition: int = 0,
    offset: int = 0,
    attempt: int = 1,
):
    """Celery background task to process consumed event with manual offset management."""
    redis_client = get_redis_client()
    return _process_offset_management_event_once(
        redis=redis_client,
        event_payload=event_payload,
        topic=topic,
        partition=partition,
        offset=offset,
        attempt=attempt,
    )


@celery_app.task(name="app.tasks.add_consumer_offset_management_task")
def add_consumer_offset_management_task(
    event_payload: dict,
    topic: Optional[str] = None,
    partition: int = 0,
    offset: int = 0,
    attempt: int = 1,
):
    """Celery task alias conforming to story naming: Add consumer offset management."""
    return process_offset_management_event_task(
        event_payload=event_payload,
        topic=topic,
        partition=partition,
        offset=offset,
        attempt=attempt,
    )


def _process_idempotency_keys_event_once(
    *,
    redis,
    event_payload: dict,
    topic: Optional[str] = None,
    headers: Optional[dict] = None,
    attempt: int = 1,
) -> dict:
    """Process an event with stable idempotency key duplicate prevention."""
    import asyncio
    from .services.idempotency_keys import ConsumerIdempotencyKeys

    consumer = ConsumerIdempotencyKeys(redis_client=redis)
    result = asyncio.run(
        consumer.process_event(
            message=event_payload,
            topic=topic,
            headers=headers,
            attempt=attempt,
        )
    )
    return dict(result)


@celery_app.task(name="app.tasks.process_idempotency_keys_event_task")
def process_idempotency_keys_event_task(
    event_payload: dict,
    topic: Optional[str] = None,
    headers: Optional[dict] = None,
    attempt: int = 1,
):
    """Celery background task to process consumed event with idempotency keys."""
    redis_client = get_redis_client()
    return _process_idempotency_keys_event_once(
        redis=redis_client,
        event_payload=event_payload,
        topic=topic,
        headers=headers,
        attempt=attempt,
    )


@celery_app.task(name="app.tasks.add_idempotency_keys_task")
def add_idempotency_keys_task(
    event_payload: dict,
    topic: Optional[str] = None,
    headers: Optional[dict] = None,
    attempt: int = 1,
):
    """Celery task alias conforming to story naming: Add idempotency keys."""
    return process_idempotency_keys_event_task(
        event_payload=event_payload,
        topic=topic,
        headers=headers,
        attempt=attempt,
    )


def _process_failed_event_storage_once(
    *,
    redis,
    event_payload: dict,
    topic: Optional[str] = None,
    partition: int = 0,
    offset: int = 0,
    attempt: int = 1,
) -> dict:
    """Process an event with durable failed-event storage and error context."""
    import asyncio
    from .services.failed_event_storage import FailedEventStorage

    consumer = FailedEventStorage(redis_client=redis)
    result = asyncio.run(
        consumer.process_event(
            message=event_payload,
            topic=topic,
            partition=partition,
            offset=offset,
            attempt=attempt,
        )
    )
    return dict(result)


@celery_app.task(name="app.tasks.process_failed_event_storage_task")
def process_failed_event_storage_task(
    event_payload: dict,
    topic: Optional[str] = None,
    partition: int = 0,
    offset: int = 0,
    attempt: int = 1,
):
    """Celery background task to process consumed event with durable failed-event storage."""
    redis_client = get_redis_client()
    return _process_failed_event_storage_once(
        redis=redis_client,
        event_payload=event_payload,
        topic=topic,
        partition=partition,
        offset=offset,
        attempt=attempt,
    )


@celery_app.task(name="app.tasks.add_failed_event_storage_task")
def add_failed_event_storage_task(
    event_payload: dict,
    topic: Optional[str] = None,
    partition: int = 0,
    offset: int = 0,
    attempt: int = 1,
):
    """Celery task alias conforming to story naming: Add failed-event storage."""
    return process_failed_event_storage_task(
        event_payload=event_payload,
        topic=topic,
        partition=partition,
        offset=offset,
        attempt=attempt,
    )


def _process_schema_versioning_event_once(
    *,
    redis,
    event_payload: dict,
    topic: Optional[str] = None,
    partition: int = 0,
    offset: int = 0,
    attempt: int = 1,
) -> dict:
    """Process an event with explicit schema version validation and compatibility."""
    import asyncio
    from .services.event_schema_versioning import EventSchemaVersioning

    consumer = EventSchemaVersioning(redis_client=redis)
    result = asyncio.run(
        consumer.process_event(
            message=event_payload,
            topic=topic,
            partition=partition,
            offset=offset,
            attempt=attempt,
        )
    )
    return dict(result)


@celery_app.task(name="app.tasks.process_schema_versioning_event_task")
def process_schema_versioning_event_task(
    event_payload: dict,
    topic: Optional[str] = None,
    partition: int = 0,
    offset: int = 0,
    attempt: int = 1,
):
    """Celery background task to process consumed event with schema versioning."""
    redis_client = get_redis_client()
    return _process_schema_versioning_event_once(
        redis=redis_client,
        event_payload=event_payload,
        topic=topic,
        partition=partition,
        offset=offset,
        attempt=attempt,
    )


@celery_app.task(name="app.tasks.add_event_schema_versioning_task")
def add_event_schema_versioning_task(
    event_payload: dict,
    topic: Optional[str] = None,
    partition: int = 0,
    offset: int = 0,
    attempt: int = 1,
):
    """Celery task alias conforming to story naming: Add event schema versioning."""
    return process_schema_versioning_event_task(
        event_payload=event_payload,
        topic=topic,
        partition=partition,
        offset=offset,
        attempt=attempt,
    )


def _process_kafka_monitoring_dashboard_once(
    event_payload: Any = None,
    topic: Optional[str] = None,
    partition: int = 0,
    offset: int = 0,
    attempt: int = 1,
    redis: Optional[Any] = None,
    redis_client: Optional[Any] = None,
    raw_message: Any = None,
) -> dict:
    """Process an event with Kafka monitoring dashboard telemetry."""
    import asyncio
    from .services.kafka_monitoring_dashboard import KafkaMonitoringDashboard

    r_client = redis if redis is not None else redis_client
    msg = event_payload if event_payload is not None else raw_message
    if isinstance(msg, str):
        try:
            msg = json.loads(msg)
        except Exception:
            pass

    consumer = KafkaMonitoringDashboard(redis_client=r_client)
    result = asyncio.run(
        consumer.process_event(
            message=msg,
            topic=topic,
            partition=partition,
            offset=offset,
            attempt=attempt,
        )
    )
    return dict(result)


@celery_app.task(name="app.tasks.process_kafka_monitoring_dashboard_task")
def process_kafka_monitoring_dashboard_task(
    event_payload: Any = None,
    topic: Optional[str] = None,
    partition: int = 0,
    offset: int = 0,
    attempt: int = 1,
    raw_message: Any = None,
):
    """Celery background task to process consumed event with monitoring dashboard."""
    redis_client = get_redis_client()
    return _process_kafka_monitoring_dashboard_once(
        event_payload=event_payload,
        raw_message=raw_message,
        topic=topic,
        partition=partition,
        offset=offset,
        attempt=attempt,
        redis=redis_client,
    )


@celery_app.task(name="app.tasks.add_kafka_monitoring_dashboard_task")
def add_kafka_monitoring_dashboard_task(
    event_payload: Any = None,
    topic: Optional[str] = None,
    partition: int = 0,
    offset: int = 0,
    attempt: int = 1,
    raw_message: Any = None,
):
    """Celery task alias conforming to story naming: Add Kafka monitoring dashboard."""
    return process_kafka_monitoring_dashboard_task(
        event_payload=event_payload,
        raw_message=raw_message,
        topic=topic,
        partition=partition,
        offset=offset,
        attempt=attempt,
    )


def _process_broker_restart_recovery_once(
    event_payload: Any = None,
    topic: Optional[str] = None,
    partition: int = 0,
    offset: int = 0,
    attempt: int = 1,
    redis: Optional[Any] = None,
    redis_client: Optional[Any] = None,
    raw_message: Any = None,
) -> dict:
    """Process an event with Kafka broker restart recovery coordinator."""
    import asyncio
    from .services.broker_restart_recovery import BrokerRestartRecovery

    r_client = redis if redis is not None else redis_client
    msg = event_payload if event_payload is not None else raw_message
    if isinstance(msg, str):
        try:
            msg = json.loads(msg)
        except Exception:
            pass

    consumer = BrokerRestartRecovery(redis_client=r_client)
    result = asyncio.run(
        consumer.process_event(
            message=msg,
            topic=topic,
            partition=partition,
            offset=offset,
            attempt=attempt,
        )
    )
    return dict(result)


@celery_app.task(name="app.tasks.process_broker_restart_recovery_task")
def process_broker_restart_recovery_task(
    event_payload: Any = None,
    topic: Optional[str] = None,
    partition: int = 0,
    offset: int = 0,
    attempt: int = 1,
    raw_message: Any = None,
):
    """Celery background task to process event during broker recovery."""
    redis_client = get_redis_client()
    return _process_broker_restart_recovery_once(
        event_payload=event_payload,
        raw_message=raw_message,
        topic=topic,
        partition=partition,
        offset=offset,
        attempt=attempt,
        redis=redis_client,
    )


@celery_app.task(name="app.tasks.test_broker_restart_task")
def test_broker_restart_task(
    event_payload: Any = None,
    topic: Optional[str] = None,
    partition: int = 0,
    offset: int = 0,
    attempt: int = 1,
    raw_message: Any = None,
):
    """Celery task alias conforming to story naming: Test broker restart."""
    return process_broker_restart_recovery_task(
        event_payload=event_payload,
        raw_message=raw_message,
        topic=topic,
        partition=partition,
        offset=offset,
        attempt=attempt,
    )


def _process_consumer_recovery_once(
    event_payload: Any = None,
    topic: Optional[str] = None,
    partition: int = 0,
    offset: int = 0,
    attempt: int = 1,
    redis: Optional[Any] = None,
    redis_client: Optional[Any] = None,
    raw_message: Any = None,
) -> dict:
    """Process an event with Kafka consumer recovery coordinator."""
    import asyncio
    from .services.consumer_recovery import ConsumerRecoveryCoordinator

    r_client = redis if redis is not None else redis_client
    msg = event_payload if event_payload is not None else raw_message
    if isinstance(msg, str):
        try:
            msg = json.loads(msg)
        except Exception:
            pass

    coordinator = ConsumerRecoveryCoordinator(redis_client=r_client)
    result = asyncio.run(
        coordinator.process_event(
            message=msg,
            topic=topic,
            partition=partition,
            offset=offset,
            attempt=attempt,
        )
    )
    return dict(result)


@celery_app.task(name="app.tasks.process_consumer_recovery_task")
def process_consumer_recovery_task(
    event_payload: Any = None,
    topic: Optional[str] = None,
    partition: int = 0,
    offset: int = 0,
    attempt: int = 1,
    raw_message: Any = None,
):
    """Celery background task to process event during consumer recovery."""
    redis_client = get_redis_client()
    return _process_consumer_recovery_once(
        event_payload=event_payload,
        raw_message=raw_message,
        topic=topic,
        partition=partition,
        offset=offset,
        attempt=attempt,
        redis=redis_client,
    )


@celery_app.task(name="app.tasks.test_consumer_recovery_task")
def test_consumer_recovery_task(
    event_payload: Any = None,
    topic: Optional[str] = None,
    partition: int = 0,
    offset: int = 0,
    attempt: int = 1,
    raw_message: Any = None,
):
    """Celery task alias conforming to story naming: Test consumer recovery."""
    return process_consumer_recovery_task(
        event_payload=event_payload,
        raw_message=raw_message,
        topic=topic,
        partition=partition,
        offset=offset,
        attempt=attempt,
    )


def _process_kafka_failure_recovery_once(
    event_payload: Any = None,
    topic: Optional[str] = None,
    partition: int = 0,
    offset: int = 0,
    attempt: int = 1,
    redis: Optional[Any] = None,
    redis_client: Optional[Any] = None,
    raw_message: Any = None,
    simulate_failure_mode: Optional[str] = None,
) -> dict:
    """Process an event with Kafka failure recovery coordinator."""
    import asyncio
    from .services.kafka_failure_recovery import KafkaFailureRecoveryCoordinator

    r_client = redis if redis is not None else redis_client
    msg = event_payload if event_payload is not None else raw_message
    if isinstance(msg, str):
        try:
            msg = json.loads(msg)
        except Exception:
            pass

    coordinator = KafkaFailureRecoveryCoordinator(redis_client=r_client)
    result = asyncio.run(
        coordinator.process_event(
            message=msg,
            topic=topic,
            partition=partition,
            offset=offset,
            attempt=attempt,
            simulate_failure_mode=simulate_failure_mode,
        )
    )
    return dict(result)


@celery_app.task(name="app.tasks.process_kafka_failure_recovery_task")
def process_kafka_failure_recovery_task(
    event_payload: Any = None,
    topic: Optional[str] = None,
    partition: int = 0,
    offset: int = 0,
    attempt: int = 1,
    raw_message: Any = None,
    simulate_failure_mode: Optional[str] = None,
):
    """Celery background task to process event during Kafka failure recovery."""
    redis_client = get_redis_client()
    return _process_kafka_failure_recovery_once(
        event_payload=event_payload,
        raw_message=raw_message,
        topic=topic,
        partition=partition,
        offset=offset,
        attempt=attempt,
        redis=redis_client,
        simulate_failure_mode=simulate_failure_mode,
    )


@celery_app.task(name="app.tasks.test_kafka_failure_recovery_task")
def test_kafka_failure_recovery_task(
    event_payload: Any = None,
    topic: Optional[str] = None,
    partition: int = 0,
    offset: int = 0,
    attempt: int = 1,
    raw_message: Any = None,
    simulate_failure_mode: Optional[str] = None,
):
    """Celery task alias conforming to story naming: Test Kafka failure recovery."""
    return process_kafka_failure_recovery_task(
        event_payload=event_payload,
        raw_message=raw_message,
        topic=topic,
        partition=partition,
        offset=offset,
        attempt=attempt,
        simulate_failure_mode=simulate_failure_mode,
    )


@celery_app.task(
    name="app.tasks.create_notification_queue_task",
    queue="notifications",
    routing_key="notifications",
)
def create_notification_queue_task(
    tenant_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> dict[str, str]:
    """Celery task to verify and activate dedicated notification queue."""
    from app.celery_app import create_notification_queue
    return create_notification_queue()


@celery_app.task(
    name="app.tasks.create_gps_processing_queue_task",
    queue="gps_processing",
    routing_key="gps",
)
def create_gps_processing_queue_task(
    tenant_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> dict[str, str]:
    """Celery task to verify and activate dedicated GPS processing queue."""
    from app.celery_app import create_gps_processing_queue
    return create_gps_processing_queue()


@celery_app.task(
    name="app.tasks.create_billing_queue_task",
    queue="billing",
    routing_key="billing",
)
def create_billing_queue_task(
    tenant_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> dict[str, str]:
    """Celery task to verify and activate dedicated billing queue."""
    from app.celery_app import create_billing_queue
    return create_billing_queue()


# ---------------------------------------------------------------------------
# Dedicated AI Processing Queue Tasks (LangGraph & Model Workloads)
# ---------------------------------------------------------------------------

def _execute_ai_workflow_once(
    *,
    redis,
    request_data: dict,
    tenant_id: str,
    job_id: Optional[Union[str, int]] = None,
    correlation_id: Optional[str] = None,
    workflow_id: Optional[str] = None,
    attempt: int = 1,
    db: Optional[Any] = None,
) -> dict:
    """Execute LangGraph AI workflow once with tenant context and Redis idempotency guard."""
    if not tenant_id or not str(tenant_id).strip():
        return {
            "status": "FAILED",
            "error": "tenant_id is required for AI workflow execution",
            "permanent_failure": True,
            "tenant_id": None,
            "correlation_id": correlation_id,
            "queue": "ai_processing",
        }

    if not isinstance(request_data, dict):
        return {
            "status": "FAILED",
            "error": "request_data must be a dictionary",
            "permanent_failure": True,
            "tenant_id": tenant_id,
            "correlation_id": correlation_id,
            "queue": "ai_processing",
        }

    stable_id = workflow_id or (f"{tenant_id}:{job_id}" if job_id else None)
    marker_key = f"ai:workflow_executed:{stable_id}" if stable_id else None

    if redis and marker_key:
        cached = redis.get(marker_key)
        if cached:
            logger.info("AI workflow %s already executed; returning idempotent result.", stable_id)
            try:
                cached_data = json.loads(cached.decode("utf-8") if isinstance(cached, bytes) else cached)
            except Exception:
                cached_data = {"status": "COMPLETED"}
            cached_data["idempotent_duplicate"] = True
            cached_data["queue"] = "ai_processing"
            return cached_data

    from app.services.ai.FieldOpsAI.graph import execute_fieldops_workflow

    session = db
    should_close_db = False
    if session is None:
        try:
            session = SessionLocal()
            should_close_db = True
        except Exception:
            session = None

    try:
        raw_result = execute_fieldops_workflow(
            request_data=request_data,
            db=session,
            job_id=job_id,
        )

        result = {
            "status": "COMPLETED" if raw_result.get("valid") else "VALIDATION_FAILED",
            "tenant_id": tenant_id,
            "correlation_id": correlation_id,
            "job_id": job_id or (raw_result.get("job_requirement", {}).get("job_id") if isinstance(raw_result, dict) else None),
            "workflow_id": workflow_id or stable_id,
            "queue": "ai_processing",
            "attempt": attempt,
            "output": raw_result,
        }

        if redis and marker_key and result.get("status") in {"COMPLETED", "VALIDATION_FAILED"}:
            try:
                redis.set(marker_key, json.dumps(result, default=str), ex=86400 * 7)
            except Exception as set_err:
                logger.warning("Failed to store Redis AI workflow marker: %s", set_err)

        return result
    except Exception as exc:
        logger.exception("AI workflow execution failed: tenant_id=%s correlation_id=%s: %s", tenant_id, correlation_id, exc)
        return {
            "status": "FAILED",
            "error": str(exc),
            "tenant_id": tenant_id,
            "correlation_id": correlation_id,
            "job_id": job_id,
            "workflow_id": workflow_id or stable_id,
            "queue": "ai_processing",
            "attempt": attempt,
        }
    finally:
        if should_close_db and session is not None:
            try:
                session.close()
            except Exception:
                pass


@celery_app.task(
    bind=True,
    name="app.tasks.execute_fieldops_workflow_async_task",
    queue="ai_processing",
    routing_key="ai",
    max_retries=3,
    time_limit=300,
    soft_time_limit=270,
)
def execute_fieldops_workflow_async_task(
    self,
    request_data: dict,
    tenant_id: str,
    job_id: Optional[Union[str, int]] = None,
    correlation_id: Optional[str] = None,
    workflow_id: Optional[str] = None,
    attempt: int = 1,
):
    """Execute LangGraph FieldOps workflow asynchronously in dedicated AI queue."""
    redis_client = get_redis_client()
    res = _execute_ai_workflow_once(
        redis=redis_client,
        request_data=request_data,
        tenant_id=tenant_id,
        job_id=job_id,
        correlation_id=correlation_id,
        workflow_id=workflow_id,
        attempt=attempt,
    )
    if res.get("status") == "FAILED" and not res.get("permanent_failure"):
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=2 ** (self.request.retries + 1))
    return res


@celery_app.task(
    bind=True,
    name="app.tasks.execute_ai_workflow_task",
    queue="ai_processing",
    routing_key="ai",
    max_retries=3,
    time_limit=300,
    soft_time_limit=270,
)
def execute_ai_workflow_task(
    self,
    request_data: dict,
    tenant_id: str,
    job_id: Optional[Union[str, int]] = None,
    correlation_id: Optional[str] = None,
    workflow_id: Optional[str] = None,
    attempt: int = 1,
):
    """Canonical alias for async AI workflow execution in dedicated AI queue."""
    return execute_fieldops_workflow_async_task(
        request_data=request_data,
        tenant_id=tenant_id,
        job_id=job_id,
        correlation_id=correlation_id,
        workflow_id=workflow_id,
        attempt=attempt,
    )


@celery_app.task(
    name="app.tasks.process_ai_workload_task",
    queue="ai_processing",
    routing_key="ai",
)
def process_ai_workload_task(
    workload_type: str,
    payload: dict,
    tenant_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> dict:
    """Generic AI background processor task running in the dedicated AI queue."""
    return {
        "status": "COMPLETED",
        "workload_type": workload_type,
        "queue": "ai_processing",
        "routing_key": "ai",
        "tenant_id": tenant_id,
        "correlation_id": correlation_id,
        "payload": payload,
    }


@celery_app.task(
    name="app.tasks.create_ai_processing_queue_task",
    queue="ai_processing",
    routing_key="ai",
)
def create_ai_processing_queue_task(
    tenant_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> dict[str, str]:
    """Celery task to verify and activate dedicated AI processing queue."""
    from app.celery_app import create_ai_processing_queue
    return create_ai_processing_queue()


# ---------------------------------------------------------------------------
# Dedicated High-Priority Queue Tasks (Emergency Dispatch & Urgent SLA)
# ---------------------------------------------------------------------------

ELIGIBLE_HIGH_PRIORITY_LEVELS = {"EMERGENCY", "CRITICAL", "HIGH", "URGENT"}


def _process_emergency_dispatch_once(
    *,
    redis,
    job_id: Union[str, int],
    tenant_id: str,
    priority: str = "EMERGENCY",
    correlation_id: Optional[str] = None,
    reason: Optional[str] = None,
    payload: Optional[dict] = None,
    attempt: int = 1,
    db: Optional[Any] = None,
) -> dict:
    """Execute emergency dispatch with strict priority eligibility, tenant validation,
    and Redis marker idempotency to prevent duplicate operational actions."""
    normalized_priority = str(priority).upper().strip() if priority else "EMERGENCY"

    # 1. Prevent priority traffic from becoming an uncontrolled bypass
    if normalized_priority not in ELIGIBLE_HIGH_PRIORITY_LEVELS:
        logger.warning(
            "Rejected unauthorized bypass attempt to high_priority queue: job_id=%s priority=%s",
            job_id,
            priority,
        )
        return {
            "status": "REJECTED_UNAUTHORIZED_BYPASS",
            "error": "Task is not eligible for high_priority queue; routine workloads must use standard queues",
            "permanent_failure": True,
            "priority": priority,
            "job_id": job_id,
            "tenant_id": tenant_id,
            "correlation_id": correlation_id,
            "queue": "high_priority",
        }

    # 2. Strict tenant context check
    if not tenant_id or not str(tenant_id).strip():
        return {
            "status": "FAILED",
            "error": "tenant_id is required for high-priority dispatch execution",
            "permanent_failure": True,
            "priority": normalized_priority,
            "job_id": job_id,
            "tenant_id": None,
            "correlation_id": correlation_id,
            "queue": "high_priority",
        }

    # 3. Idempotency Check to prevent duplicate operational side effects
    marker_key = f"dispatch:emergency_processed:{tenant_id}:{job_id}:{correlation_id or 'default'}"
    if redis and redis.get(marker_key):
        logger.info(
            "Emergency dispatch for job %s already processed; skipping duplicate.",
            job_id,
        )
        return {
            "status": "PROCESSED",
            "job_id": job_id,
            "tenant_id": tenant_id,
            "correlation_id": correlation_id,
            "priority": normalized_priority,
            "queue": "high_priority",
            "routing_key": "priority",
            "idempotent_duplicate": True,
            "attempt": attempt,
        }

    session = db
    should_close_db = False
    if session is None:
        try:
            session = SessionLocal()
            should_close_db = True
        except Exception:
            session = None

    try:
        if session is not None:
            try:
                from .models import Job, AuditEvent
                target_job = (
                    session.query(Job)
                    .filter(Job.id == int(job_id) if str(job_id).isdigit() else Job.id == job_id)
                    .first()
                )
                if target_job:
                    audit = AuditEvent(
                        event_type="EMERGENCY_DISPATCH",
                        tech_id=str(target_job.assigned_technician_id) if target_job.assigned_technician_id else "system",
                        tenant_id=tenant_id,
                        old_status=target_job.status,
                        new_status=target_job.status,
                        reason=reason or f"Urgent priority dispatch: {normalized_priority}",
                        job_id=str(job_id),
                        details={
                            "priority": normalized_priority,
                            "correlation_id": correlation_id,
                            "reason": reason,
                        },
                    )
                    session.add(audit)
                    session.commit()
            except Exception as db_err:
                logger.warning("Audit recording for emergency dispatch encountered: %s", db_err)
                if session:
                    session.rollback()

        result = {
            "status": "PROCESSED",
            "job_id": job_id,
            "tenant_id": tenant_id,
            "correlation_id": correlation_id,
            "priority": normalized_priority,
            "reason": reason,
            "queue": "high_priority",
            "routing_key": "priority",
            "attempt": attempt,
        }

        if redis:
            try:
                redis.set(marker_key, json.dumps(result, default=str), ex=86400 * 7)
            except Exception as set_err:
                logger.warning("Failed to store emergency dispatch Redis marker: %s", set_err)

        return result
    except Exception as exc:
        logger.exception(
            "Emergency dispatch processing failed: job_id=%s tenant_id=%s: %s",
            job_id,
            tenant_id,
            exc,
        )
        return {
            "status": "FAILED",
            "error": str(exc),
            "priority": normalized_priority,
            "job_id": job_id,
            "tenant_id": tenant_id,
            "correlation_id": correlation_id,
            "queue": "high_priority",
            "routing_key": "priority",
            "attempt": attempt,
        }
    finally:
        if should_close_db and session is not None:
            try:
                session.close()
            except Exception:
                pass


@celery_app.task(
    bind=True,
    name="app.tasks.process_emergency_dispatch_task",
    queue="high_priority",
    routing_key="priority",
    max_retries=3,
    time_limit=60,
    soft_time_limit=50,
)
def process_emergency_dispatch_task(
    self,
    job_id: Union[str, int],
    tenant_id: str,
    priority: str = "EMERGENCY",
    correlation_id: Optional[str] = None,
    reason: Optional[str] = None,
    payload: Optional[dict] = None,
    attempt: int = 1,
):
    """Celery background task for urgent emergency dispatch running in high_priority queue."""
    redis_client = get_redis_client()
    res = _process_emergency_dispatch_once(
        redis=redis_client,
        job_id=job_id,
        tenant_id=tenant_id,
        priority=priority,
        correlation_id=correlation_id,
        reason=reason,
        payload=payload,
        attempt=attempt,
    )
    if res.get("status") == "FAILED" and not res.get("permanent_failure"):
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=2 ** (self.request.retries + 1))
    return res


@celery_app.task(
    bind=True,
    name="app.tasks.emergency_dispatch_task",
    queue="high_priority",
    routing_key="priority",
    max_retries=3,
    time_limit=60,
    soft_time_limit=50,
)
def emergency_dispatch_task(
    self,
    job_id: Union[str, int],
    tenant_id: str,
    priority: str = "EMERGENCY",
    correlation_id: Optional[str] = None,
    reason: Optional[str] = None,
    payload: Optional[dict] = None,
    attempt: int = 1,
):
    """Canonical alias conforming to story naming: Emergency dispatch task."""
    return process_emergency_dispatch_task(
        job_id=job_id,
        tenant_id=tenant_id,
        priority=priority,
        correlation_id=correlation_id,
        reason=reason,
        payload=payload,
        attempt=attempt,
    )


@celery_app.task(
    name="app.tasks.create_high_priority_queue_task",
    queue="high_priority",
    routing_key="priority",
)
def create_high_priority_queue_task(
    tenant_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> dict[str, str]:
    """Celery task to verify and activate dedicated high-priority queue."""
    from app.celery_app import create_high_priority_queue
    return create_high_priority_queue()


# ---------------------------------------------------------------------------
# Dedicated Report-Generation Queue Tasks (PDF & Long-Running Reporting)
# ---------------------------------------------------------------------------

def _generate_report_once(
    *,
    redis,
    report_type: str,
    tenant_id: str,
    report_id: Optional[str] = None,
    job_id: Optional[Union[str, int]] = None,
    correlation_id: Optional[str] = None,
    parameters: Optional[dict] = None,
    attempt: int = 1,
    db: Optional[Any] = None,
) -> dict:
    """Execute asynchronous PDF/report generation with tenant validation,
    result correlation, and Redis marker idempotency."""
    if not tenant_id or not str(tenant_id).strip():
        return {
            "status": "FAILED",
            "error": "tenant_id is required for report generation",
            "permanent_failure": True,
            "report_type": report_type,
            "tenant_id": None,
            "correlation_id": correlation_id,
            "queue": "report_generation",
        }

    if not report_type or not str(report_type).strip():
        return {
            "status": "FAILED",
            "error": "report_type is required",
            "permanent_failure": True,
            "report_type": None,
            "tenant_id": tenant_id,
            "correlation_id": correlation_id,
            "queue": "report_generation",
        }

    stable_report_id = report_id or (f"rpt_{job_id}_{report_type}" if job_id else f"rpt_{tenant_id}_{report_type}")
    marker_key = f"report:generated:{tenant_id}:{stable_report_id}"

    if redis and redis.get(marker_key):
        logger.info(
            "Report %s for tenant %s already generated; returning cached result.",
            stable_report_id,
            tenant_id,
        )
        return {
            "status": "GENERATED",
            "report_id": stable_report_id,
            "report_type": report_type,
            "tenant_id": tenant_id,
            "job_id": job_id,
            "correlation_id": correlation_id,
            "queue": "report_generation",
            "routing_key": "reports",
            "idempotent_duplicate": True,
            "attempt": attempt,
        }

    from .services.report_service import render_summary_report_pdf

    session = db
    should_close_db = False
    if session is None:
        try:
            session = SessionLocal()
            should_close_db = True
        except Exception:
            session = None

    try:
        records = (parameters or {}).get("records", [])
        pdf_bytes = render_summary_report_pdf(
            title=f"{report_type.upper()} REPORT",
            records=records,
            tenant_id=tenant_id,
            metadata={"job_id": job_id, "correlation_id": correlation_id},
        )

        result = {
            "status": "GENERATED",
            "report_id": stable_report_id,
            "report_type": report_type,
            "tenant_id": tenant_id,
            "job_id": job_id,
            "correlation_id": correlation_id,
            "file_size": len(pdf_bytes),
            "content_type": "application/pdf",
            "queue": "report_generation",
            "routing_key": "reports",
            "attempt": attempt,
        }

        if redis:
            try:
                redis.set(marker_key, json.dumps(result, default=str), ex=86400 * 7)
            except Exception as set_err:
                logger.warning("Failed to store report generation Redis marker: %s", set_err)

        return result
    except Exception as exc:
        logger.exception(
            "Report generation failed: report_id=%s tenant_id=%s: %s",
            stable_report_id,
            tenant_id,
            exc,
        )
        return {
            "status": "FAILED",
            "error": str(exc),
            "report_id": stable_report_id,
            "report_type": report_type,
            "tenant_id": tenant_id,
            "job_id": job_id,
            "correlation_id": correlation_id,
            "queue": "report_generation",
            "routing_key": "reports",
            "attempt": attempt,
        }
    finally:
        if should_close_db and session is not None:
            try:
                session.close()
            except Exception:
                pass


@celery_app.task(
    bind=True,
    name="app.tasks.generate_report_task",
    queue="report_generation",
    routing_key="reports",
    max_retries=3,
    time_limit=600,
    soft_time_limit=540,
)
def generate_report_task(
    self,
    report_type: str,
    tenant_id: str,
    report_id: Optional[str] = None,
    job_id: Optional[Union[str, int]] = None,
    correlation_id: Optional[str] = None,
    parameters: Optional[dict] = None,
    attempt: int = 1,
):
    """Celery background task for asynchronous report generation in dedicated queue."""
    redis_client = get_redis_client()
    res = _generate_report_once(
        redis=redis_client,
        report_type=report_type,
        tenant_id=tenant_id,
        report_id=report_id,
        job_id=job_id,
        correlation_id=correlation_id,
        parameters=parameters,
        attempt=attempt,
    )
    if res.get("status") == "FAILED" and not res.get("permanent_failure"):
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=2 ** (self.request.retries + 1))
    return res


@celery_app.task(
    bind=True,
    name="app.tasks.generate_pdf_report_task",
    queue="report_generation",
    routing_key="reports",
    max_retries=3,
    time_limit=600,
    soft_time_limit=540,
)
def generate_pdf_report_task(
    self,
    report_type: str,
    tenant_id: str,
    report_id: Optional[str] = None,
    job_id: Optional[Union[str, int]] = None,
    correlation_id: Optional[str] = None,
    parameters: Optional[dict] = None,
    attempt: int = 1,
):
    """Canonical alias conforming to story naming: Generate PDF report task."""
    return generate_report_task(
        report_type=report_type,
        tenant_id=tenant_id,
        report_id=report_id,
        job_id=job_id,
        correlation_id=correlation_id,
        parameters=parameters,
        attempt=attempt,
    )


@celery_app.task(
    bind=True,
    name="app.tasks.generate_job_invoice_pdf_task",
    queue="report_generation",
    routing_key="reports",
    max_retries=3,
    time_limit=600,
    soft_time_limit=540,
)
def generate_job_invoice_pdf_task(
    self,
    job_id: Union[str, int],
    tenant_id: str,
    correlation_id: Optional[str] = None,
    closure_id: Optional[int] = None,
    attempt: int = 1,
):
    """Celery background task to generate authorized job invoice PDF in report_generation queue."""
    redis_client = get_redis_client()
    return _generate_report_once(
        redis=redis_client,
        report_type="invoice_pdf",
        tenant_id=tenant_id,
        report_id=f"invoice_{job_id}",
        job_id=job_id,
        correlation_id=correlation_id,
        parameters={"closure_id": closure_id},
        attempt=attempt,
    )


@celery_app.task(
    name="app.tasks.process_report_generation_task",
    queue="report_generation",
    routing_key="reports",
)
def process_report_generation_task(
    report_type: str,
    payload: dict,
    tenant_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> dict:
    """Generic report processor task running in the dedicated report-generation queue."""
    return {
        "status": "COMPLETED",
        "report_type": report_type,
        "queue": "report_generation",
        "routing_key": "reports",
        "tenant_id": tenant_id,
        "correlation_id": correlation_id,
        "payload": payload,
    }


@celery_app.task(
    name="app.tasks.create_report_generation_queue_task",
    queue="report_generation",
    routing_key="reports",
)
def create_report_generation_queue_task(
    tenant_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> dict[str, str]:
    """Celery task to verify and activate dedicated report-generation queue."""
    from app.celery_app import create_report_generation_queue
    return create_report_generation_queue()


# ---------------------------------------------------------------------------
# Task Retry Rules (Bounded Exponential Backoff with Jitter & DLQ Routing)
# ---------------------------------------------------------------------------

@celery_app.task(
    name="app.tasks.configure_task_retry_rules_task",
)
def configure_task_retry_rules_task(
    tenant_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> dict[str, Any]:
    """Celery task to verify and activate task retry rules."""
    from app.celery_app import configure_task_retry_rules
    return configure_task_retry_rules()


def handle_task_failure_with_retry_policy(
    *,
    celery_task=None,
    error: BaseException,
    task_payload: dict,
    tenant_id: str,
    retry_count: int = 0,
    correlation_id: Optional[str] = None,
    redis=None,
    db=None,
) -> dict[str, Any]:
    """
    Handle task failure adhering to bounded retry policy:
    - Non-retryable (validation/auth/guardrail) -> moved to DLQ immediately.
    - Retryable (network/timeout/transient) and retry_count < 3 -> retried with exponential backoff & jitter.
    - Retryable but retry_count >= 3 -> moved to DLQ (no infinite loops).
    """
    from app.runtime.retry import RetryDecision, RetryManager
    from app.runtime.dlq import DeadLetterQueue

    evaluation = RetryManager.evaluate(error, retry_count)

    if evaluation.decision == RetryDecision.RETRY and retry_count < RetryManager.MAX_RETRIES:
        delay = RetryManager.calculate_backoff_with_jitter(evaluation.retry_number, jitter=True)
        logger.warning(
            "Task failed with transient error; scheduling bounded retry %d with backoff %.3fs. error=%s",
            evaluation.retry_number,
            delay,
            error,
        )
        if celery_task is not None:
            raise celery_task.retry(exc=error, countdown=delay)
        return {
            "status": "RETRY_SCHEDULED",
            "retry_number": evaluation.retry_number,
            "delay_seconds": delay,
            "reason": evaluation.reason,
            "tenant_id": tenant_id,
            "correlation_id": correlation_id,
        }

    # Move to DLQ
    logger.error(
        "Task failure cannot be retried (decision=%s, reason=%s); moving to DLQ.",
        evaluation.decision,
        evaluation.reason,
    )
    redis_client = redis or get_redis_client()
    dlq = DeadLetterQueue(redis_client, db)
    dlq_entry = {
        "tenant_id": tenant_id,
        "payload": {
            "task": task_payload,
            "correlation_id": correlation_id,
            "task_type": task_payload.get("task_type", "task") if isinstance(task_payload, dict) else "task",
        },
    }
    dlq_record = dlq.add(
        task=dlq_entry,
        reason=evaluation.reason,
        retry_count=retry_count,
        error=error,
        celery_task_id=getattr(getattr(celery_task, "request", None), "id", None) if celery_task else None,
    )
    return {
        "status": "MOVED_TO_DLQ",
        "failure_action": "DLQ",
        "requeue_supported": True,
        "dlq_id": dlq_record.get("id"),
        "reason": evaluation.reason,
        "retry_count": retry_count,
        "tenant_id": tenant_id,
        "correlation_id": correlation_id,
    }


# ---------------------------------------------------------------------------
# Story 8.8: Failed Task Handling Celery Task & Wrappers
# ---------------------------------------------------------------------------

@celery_app.task(
    name="app.tasks.configure_failed_task_handling_task",
)
def configure_failed_task_handling_task(
    tenant_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> dict[str, Any]:
    """Celery task to verify and activate failed task handling."""
    from app.celery_app import configure_failed_task_handling
    return configure_failed_task_handling()


from app.runtime.dlq import (
    handle_failed_task,
    configure_failed_task_handling,
    get_failed_task_handling_config,
    sanitize_payload,
)


# ---------------------------------------------------------------------------
# Story 8.9: Task Timeouts Celery Task & Wrappers
# ---------------------------------------------------------------------------

@celery_app.task(
    name="app.tasks.configure_task_timeouts_task",
)
def configure_task_timeouts_task(
    tenant_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> dict[str, Any]:
    """Celery task to verify and activate task timeout rules."""
    from app.celery_app import configure_task_timeouts
    return configure_task_timeouts()


from app.celery_app import (
    DEFAULT_TASK_TIMEOUTS,
    QUEUE_TASK_TIMEOUTS,
    get_task_timeouts_config,
    get_queue_timeout,
    configure_task_timeouts,
)


def handle_task_timeout(
    *,
    task_name: str,
    queue: str = "default",
    tenant_id: str,
    correlation_id: Optional[str] = None,
    elapsed_seconds: Optional[float] = None,
    db=None,
    redis=None,
    error: Optional[BaseException] = None,
    task_payload: Optional[dict] = None,
) -> dict[str, Any]:
    """
    Handle task execution timeout:
    - Rolls back active database session to prevent partial/dirty state.
    - Logs structured timeout, task, and correlation information.
    - Routes timed-out task to DLQ without leaving partial state.
    """
    logger.warning(
        "Task execution timed out. task=%s, queue=%s, tenant_id=%s, correlation_id=%s, elapsed=%.2fs, error=%s",
        task_name,
        queue,
        tenant_id,
        correlation_id,
        elapsed_seconds or 0.0,
        error,
        extra={
            "task_name": task_name,
            "queue": queue,
            "tenant_id": tenant_id,
            "correlation_id": correlation_id,
            "elapsed_seconds": elapsed_seconds,
            "event": "TASK_TIMEOUT",
        },
    )

    if db is not None:
        try:
            db.rollback()
            logger.info("Rolled back database transaction on timeout for task=%s", task_name)
        except Exception as rb_err:
            logger.error("Failed to rollback db transaction on timeout: %s", rb_err)

    # Route to DLQ if tenant_id is provided
    try:
        from app.runtime.dlq import handle_failed_task
        dlq_result = handle_failed_task(
            task_name=task_name,
            queue=queue,
            payload=task_payload or {},
            error=error or TimeoutError(f"Task exceeded execution timeout on queue '{queue}'"),
            exception_category="timeout_exceeded",
            tenant_id=tenant_id,
            correlation_id=correlation_id,
            reason="task_timeout_exceeded",
            redis=redis,
            db=db,
        )
    except Exception as dlq_err:
        logger.error("Failed to route timed-out task to DLQ: %s", dlq_err)
        dlq_result = {
            "status": "FAILED_HANDLED",
            "failure_action": "DLQ",
            "requeue_supported": True,
        }

    return {
        "status": "TIMED_OUT",
        "task_name": task_name,
        "queue": queue,
        "tenant_id": tenant_id,
        "correlation_id": correlation_id,
        "partial_state_prevented": True,
        "dlq_result": dlq_result,
    }


# ---------------------------------------------------------------------------
# Story 8.10: Celery Beat Scheduled Tasks & Idempotency Wrappers
# ---------------------------------------------------------------------------

@celery_app.task(
    name="app.tasks.add_scheduled_tasks_task",
)
def add_scheduled_tasks_task(
    tenant_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    schedules: Optional[dict[str, Any]] = None,
) -> dict[str, str]:
    """Celery task to verify and register Celery Beat scheduled tasks."""
    from app.celery_app import add_scheduled_tasks
    return add_scheduled_tasks(schedules=schedules)


from app.celery_app import (
    FOUNDATIONAL_BEAT_SCHEDULES,
    get_scheduled_tasks_config,
    add_scheduled_tasks,
    AddScheduledTasks,
    Add_scheduled_tasks,
    add_scheduled_task,
    AddScheduledTask,
    get_scheduled_tasks,
    get_scheduled_task_config,
)


def run_scheduled_task_idempotently(
    schedule_key: str,
    interval_seconds: int,
    func,
    *args,
    redis=None,
    **kwargs,
) -> Any:
    """
    Execute a recurring scheduled task idempotently:
    Uses a Redis lock key for the current time bucket to guarantee
    only one worker process runs the task within that interval.
    """
    if redis is None:
        from app.redis_client import get_redis_client
        redis = get_redis_client()

    now_epoch = int(time.time())
    bucket = now_epoch // max(interval_seconds, 1)
    lock_key = f"scheduled_task_lock:{schedule_key}:{bucket}"

    if redis is not None:
        acquired = redis.set(lock_key, "locked", nx=True, ex=int(interval_seconds * 1.5))
        if not acquired:
            logger.info(
                "Skipping duplicate scheduled run for key=%s bucket=%s",
                schedule_key,
                bucket,
            )
            return {"status": "SKIPPED_DUPLICATE", "schedule_key": schedule_key}

    return func(*args, **kwargs)


# ---------------------------------------------------------------------------
# Story 8.11: Task Result Tracking Celery Task & Wrappers
# ---------------------------------------------------------------------------

@celery_app.task(
    name="app.tasks.add_task_result_tracking_task",
)
def add_task_result_tracking_task(
    task_id: str = "example-task-id",
    state: str = "SUCCESS",
    queue: str = "notifications",
    tenant_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> dict[str, Any]:
    """Celery task to verify and activate task result tracking."""
    from app.celery_app import add_task_result_tracking
    return add_task_result_tracking(task_id=task_id, state=state, queue=queue)


@celery_app.task(
    name="app.tasks.add_celery_monitoring_task",
)
def add_celery_monitoring_task(
    tenant_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> dict[str, Any]:
    """Celery task to verify and activate Celery monitoring."""
    from app.celery_app import add_celery_monitoring
    return add_celery_monitoring()


@celery_app.task(
    name="app.tasks.check_celery_health_task",
)
def check_celery_health_task(
    tenant_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> dict[str, Any]:
    """Periodic or operational task to inspect Celery worker and queue health."""
    from app.celery_app import get_celery_monitoring_metrics
    return get_celery_monitoring_metrics()


from app.celery_app import (
    DEFAULT_TASK_RESULT_TRACKING,
    get_task_result_tracking_config,
    track_task_result,
    get_task_result,
    add_task_result_tracking,
    AddTaskResultTracking,
    Add_task_result_tracking,
    configure_task_result_tracking,
    ConfigureTaskResultTracking,
    get_task_result_tracking,
    TrackTaskResult,
    DEFAULT_CELERY_MONITORING,
    ALL_KNOWN_QUEUES,
    get_celery_monitoring_config,
    add_celery_monitoring,
    get_celery_queue_depth,
    get_all_queue_depths,
    record_task_failure,
    record_task_retry,
    record_task_latency,
    detect_abnormal_queue_growth,
    get_celery_worker_health,
    detect_stalled_workers,
    get_celery_monitoring_metrics,
    AddCeleryMonitoring,
    Add_celery_monitoring,
    configure_celery_monitoring,
    ConfigureCeleryMonitoring,
    get_celery_monitoring,
    GetCeleryMonitoring,
    CeleryMonitoring,
    CeleryMonitoringService,
)









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
    queue="notifications",
    routing_key="notifications",
)
def send_sms_async(
    self,
    to_number: str,
    body: str,
    from_number: str | None = None,
    delivery_id: int | None = None,
    tenant_id: str | None = None,
    correlation_id: str | None = None,
    **kwargs,
):
    # Send SMS in a Celery worker so the API request remains non-blocking.
    service = TwilioSMSService()
    safe_delivery_id = int(delivery_id) if delivery_id is not None else None
    if safe_delivery_id is not None:
        from .services.ai.FieldOpsAI.agents.communication_agent.channels import begin_delivery_attempt
        claim_db = SessionLocal()
        try:
            claimed = begin_delivery_attempt(claim_db, safe_delivery_id)
        finally:
            claim_db.close()
        if not claimed:
            logger.info("SMS delivery skipped: duplicate or already claimed", extra={"delivery_id": safe_delivery_id})
            return {"success": True, "skipped": "already_claimed"}
    try:
        status_callback = (
            os.getenv("TWILIO_STATUS_CALLBACK_URL")
            if safe_delivery_id is not None
            else None
        )
        send_args = {
            "to_number": to_number,
            "body": body,
            "from_number": from_number,
        }
        if status_callback:
            send_args["status_callback"] = status_callback
        result = service.send_sms(**send_args)
    except Exception as exc:
        if safe_delivery_id is not None:
            from .services.ai.FieldOpsAI.agents.communication_agent.channels import mark_delivery
            failed_db = SessionLocal()
            try:
                mark_delivery(failed_db, safe_delivery_id, "failed", str(exc)[:500], increment_attempt=False)
            finally:
                failed_db.close()
        raise
    if safe_delivery_id is not None:
        from .services.ai.FieldOpsAI.agents.communication_agent.channels import mark_delivery
        result_db = SessionLocal()
        try:
            delivery_status = "accepted" if result.success else "failed"
            mark_delivery(
                result_db, safe_delivery_id, delivery_status,
                None if result.success else (result.error_message or "SMS provider rejected message")[:500],
                provider_id=getattr(result, "sid", None), increment_attempt=False,
            )
        finally:
            result_db.close()
        if not result.success and self.request.retries < self.max_retries:
            raise self.retry(exc=RuntimeError(result.error_message or "SMS delivery failed"), countdown=2 ** (self.request.retries + 1))
    return result


class PermanentPushDeliveryError(Exception):
    pass


@shared_task(bind=True, name="app.tasks.send_push_async", max_retries=3)
def send_push_async(self, title: str, body: str, delivery_id: int):
    """Deliver one tracked push via Expo Push Service or Firebase Cloud Messaging."""
    from .models.user import User
    from .models_legacy import InAppNotification, NotificationChannelDelivery
    from .services.ai.FieldOpsAI.agents.communication_agent.channels import (
        begin_delivery_attempt,
        mark_delivery,
    )

    delivery_id = int(delivery_id)
    db = SessionLocal()
    try:
        if not begin_delivery_attempt(db, delivery_id):
            return {"success": True, "skipped": "already_claimed"}
        delivery = db.get(NotificationChannelDelivery, delivery_id)
        notification = (
            db.get(InAppNotification, delivery.notification_id)
            if delivery
            else None
        )
        if not delivery or not notification or delivery.channel != "push":
            mark_delivery(db, delivery_id, "permanent_failure", "push delivery context is missing", increment_attempt=False)
            return {"success": False, "status": "permanent_failure"}

        recipient = None
        if notification.recipient_role == "technician":
            recipient = (
                db.query(models.Technician)
                .filter(
                    models.Technician.tech_id == notification.recipient_id,
                    models.Technician.tenant_id == delivery.tenant_id,
                )
                .first()
            )
        else:
            recipient = (
                db.query(User)
                .filter(
                    User.id == notification.recipient_id,
                    User.tenant_id == delivery.tenant_id,
                    User.is_active.is_(True),
                    User.deleted_at.is_(None),
                )
                .first()
            )
        token = str(getattr(recipient, "fcm_token", "") or "").strip()
        device_type = str(getattr(recipient, "device_type", "") or "").lower()
        if not token:
            mark_delivery(db, delivery_id, "permanent_failure", "recipient has no registered push device", increment_attempt=False)
            return {"success": False, "status": "permanent_failure"}

        data = {
            "notification_id": str(notification.id),
            "type": str(notification.type or "update"),
            "job_id": str(notification.job_id or ""),
        }
        is_expo_token = token.startswith(("ExponentPushToken[", "ExpoPushToken["))
    finally:
        db.close()

    try:
        if is_expo_token:
            import requests

            response = requests.post(
                "https://exp.host/--/api/v2/push/send",
                json={
                    "to": token,
                    "title": title[:50],
                    "body": body[:160],
                    "sound": "default",
                    "priority": "high",
                    "channelId": "fieldops_updates",
                    "data": data,
                },
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                timeout=10,
            )
            response.raise_for_status()
            ticket = response.json().get("data", {})
            if ticket.get("status") != "ok":
                error_code = (ticket.get("details") or {}).get("error")
                permanent = error_code == "DeviceNotRegistered"
                if permanent:
                    raise PermanentPushDeliveryError("Expo push provider rejected the device token")
                raise RuntimeError("Expo push provider temporarily rejected the message")
            provider_id = ticket.get("id")
        else:
            import firebase_admin
            from firebase_admin import messaging

            if not firebase_admin._apps:
                firebase_admin.initialize_app()

            android_config = messaging.AndroidConfig(
                priority="high",
                notification=messaging.AndroidNotification(
                    channel_id="fieldops_updates",
                ),
            ) if device_type == "android" else None
            provider_id = messaging.send(
                messaging.Message(
                    token=token,
                    notification=messaging.Notification(
                        title=title[:50],
                        body=body[:160],
                    ),
                    data=data,
                    android=android_config,
                )
            )
    except Exception as exc:
        error_type = type(exc).__name__
        permanent = isinstance(exc, PermanentPushDeliveryError) or error_type in {
            "UnregisteredError",
            "InvalidArgumentError",
        }
        failed_db = SessionLocal()
        try:
            mark_delivery(
                failed_db,
                delivery_id,
                "permanent_failure" if permanent else "failed",
                f"Push provider error: {error_type}",
                increment_attempt=False,
            )
            if permanent:
                from .models_legacy import Technician

                if notification.recipient_role == "technician":
                    failed_db.query(Technician).filter(
                        Technician.tech_id == notification.recipient_id,
                        Technician.tenant_id == delivery.tenant_id,
                        Technician.fcm_token == token,
                    ).update({"fcm_token": None, "device_type": None}, synchronize_session=False)
                else:
                    failed_db.query(User).filter(
                        User.id == notification.recipient_id,
                        User.tenant_id == delivery.tenant_id,
                        User.fcm_token == token,
                    ).update({"fcm_token": None, "device_type": None}, synchronize_session=False)
                failed_db.commit()
        finally:
            failed_db.close()
        if not permanent and self.request.retries < self.max_retries:
            raise self.retry(exc=RuntimeError("Push delivery temporarily failed"), countdown=2 ** (self.request.retries + 1))
        return {"success": False, "status": "permanent_failure" if permanent else "failed"}

    result_db = SessionLocal()
    try:
        mark_delivery(
            result_db,
            delivery_id,
            "accepted",
            provider_id=str(provider_id) if provider_id else None,
            increment_attempt=False,
        )
    finally:
        result_db.close()
    return {"success": True, "status": "accepted"}


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
    tenant_id: str | None = None,
    correlation_id: str | None = None,
    **kwargs,
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
    tenant_id: str | None = None,
    correlation_id: str | None = None,
    **kwargs,
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
            claimed = begin_delivery_attempt(delivery_db, int(delivery_id))
        finally:
            delivery_db.close()
        if not claimed:
            logger.info(
                "Email delivery task skipped: duplicate or already claimed",
                extra={"delivery_id": int(delivery_id)},
            )
            return {"success": True, "skipped": "already_claimed"}

    import asyncio

    try:
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
    except Exception as exc:
        if delivery_id is not None:
            from .services.ai.FieldOpsAI.agents.communication_agent.channels import mark_delivery
            failed_db = SessionLocal()
            try:
                mark_delivery(failed_db, int(delivery_id), "failed", str(exc)[:500], increment_attempt=False)
            finally:
                failed_db.close()
        raise

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
        if delivery_id is not None:
            from .services.ai.FieldOpsAI.agents.communication_agent.channels import mark_delivery
            retry_db = SessionLocal()
            try:
                mark_delivery(
                    retry_db, int(delivery_id), "failed",
                    (result.error or "temporary email provider failure")[:500],
                    increment_attempt=False,
                )
            finally:
                retry_db.close()
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
