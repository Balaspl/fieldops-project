
"""Live WebSocket push, SMS/email enqueueing, and delivery tracking."""

import asyncio
import logging
import os
import re
import time
from typing import Any, Coroutine

from sqlalchemy import func, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models_legacy import NotificationChannelDelivery

logger = logging.getLogger(__name__)


def _enqueue_task_with_retry(task: Any, *, kwargs: dict[str, Any], task_id: str) -> None:
    """Retry transient broker enqueue errors with a stable delivery identity."""
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            task.apply_async(kwargs=kwargs, task_id=task_id)
            return
        except Exception as exc:
            last_error = exc
            logger.warning(
                "Communication task enqueue attempt failed event_id=%s attempt=%s/3 error_type=%s error=%s",
                task_id, attempt, type(exc).__name__, str(exc)[:300], exc_info=True,
            )
            if attempt < 3:
                time.sleep(0.1 * attempt)
    assert last_error is not None
    raise last_error


# ---------------------------------------------------------------------------
# External channel configuration
# ---------------------------------------------------------------------------

def external_channels_enabled() -> set[str]:
    """Return configured channels; email is enabled for lifecycle notices."""
    raw = os.getenv("COMM_AGENT_CHANNELS", "in_app,email")
    return {
        channel.strip().lower()
        for channel in raw.split(",")
        if channel.strip()
    }


def normalize_phone(raw: str | None) -> str | None:
    """Normalize a phone number to a basic E.164 representation."""
    if not raw:
        return None

    country_code = os.getenv(
        "COMM_AGENT_DEFAULT_COUNTRY_CODE", "+91"
    ).strip()

    if not re.fullmatch(r"\+[0-9]{1,4}", country_code):
        country_code = "+91"

    value = re.sub(r"[^\d+]", "", raw.strip())

    if value.startswith("+"):
        digits = value[1:]
        return value if digits.isdigit() and 8 <= len(digits) <= 15 else None

    if value.startswith("00"):
        digits = value[2:]
        return (
            f"+{digits}"
            if digits.isdigit() and 8 <= len(digits) <= 15
            else None
        )

    if value.isdigit() and len(value) == 10:
        return f"{country_code}{value}"

    if value.isdigit() and len(value) == 11 and value.startswith("0"):
        return f"{country_code}{value[1:]}"

    if value.isdigit() and len(value) == 12 and value.startswith("91"):
        return f"+{value}"

    return None


def idem_key(
    job_id: Any,
    event: Any,
    recipient: Any,
    channel: str,
    event_version: int | None = None,
) -> str:
    """Build a stable delivery key for one persisted business event."""
    event_value = getattr(event, "value", str(event))

    return (
        f"{job_id}:{event_value}:{recipient.role}:"
        f"{recipient.tenant_id}:{recipient.id}:{channel}:"
        f"{event_version if event_version is not None else 0}"
    )


# ---------------------------------------------------------------------------
# Delivery tracking
# ---------------------------------------------------------------------------

def claim_delivery(
    db: Session,
    *,
    tenant_id: str,
    notification_id: str,
    channel: str,
    recipient_id: str,
    key: str,
) -> int | None:
    """Insert a delivery row, returning its ID or None for a duplicate key."""
    dialect = db.get_bind().dialect.name

    if dialect == "postgresql":
        insert = pg_insert
    elif dialect == "sqlite":
        insert = sqlite_insert
    else:
        raise NotImplementedError(
            f"Delivery tracking does not support database dialect: {dialect}"
        )

    stmt = (
        insert(NotificationChannelDelivery)
        .values(
            tenant_id=str(tenant_id),
            notification_id=str(notification_id),
            channel=channel,
            recipient_id=str(recipient_id),
            status="queued",
            attempts=0,
            idempotency_key=key,
        )
        .on_conflict_do_update(
            index_elements=["idempotency_key"],
            set_={
                "status": "queued",
                "error_message": None,
                "updated_at": func.now(),
            },
            where=NotificationChannelDelivery.status.in_(("failed", "pending")),
        )
        .returning(NotificationChannelDelivery.id)
    )

    return db.execute(stmt).scalar_one_or_none()


def mark_delivery(
    db: Session,
    delivery_id: int,
    status: str,
    error: str | None = None,
    provider_id: str | None = None,
    increment_attempt: bool = True,
) -> None:
    """Update delivery status and commit the change."""
    db.execute(
        update(NotificationChannelDelivery)
        .where(NotificationChannelDelivery.id == delivery_id)
        .values(
            status=status,
            error_message=error,
            provider_id=provider_id,
            **(
                {"attempts": NotificationChannelDelivery.attempts + 1}
                if increment_attempt
                else {}
            ),
            updated_at=func.now(),
        )
    )
    db.commit()


def begin_delivery_attempt(db: Session, delivery_id: int) -> bool:
    """Atomically claim one queued delivery; duplicate tasks cannot send it."""
    result = db.execute(
        update(NotificationChannelDelivery)
        .where(
            NotificationChannelDelivery.id == delivery_id,
            NotificationChannelDelivery.status.in_(("queued", "failed", "pending")),
        )
        .values(
            status="sending",
            error_message=None,
            attempts=NotificationChannelDelivery.attempts + 1,
            updated_at=func.now(),
        )
    )
    db.commit()
    return bool(result.rowcount)


# ---------------------------------------------------------------------------
# SMS / email enqueueing
# ---------------------------------------------------------------------------

def enqueue_sms(phone: str, body: str, delivery_id: int) -> None:
    """Queue SMS delivery using the existing Celery task."""
    from app.tasks import send_sms_async

    _enqueue_task_with_retry(
        send_sms_async,
        kwargs={"to_number": phone, "body": body, "delivery_id": int(delivery_id)},
        task_id=f"communication-sms-delivery-{int(delivery_id)}",
    )


def enqueue_email(
    to_email: str,
    subject: str,
    html_body: str,
    plain_text: str,
    delivery_id: int,
    invoice_job_id: int | None = None,
    invoice_closure_id: int | None = None,
) -> None:
    """Queue email delivery using the existing Celery task."""
    from app.tasks import send_email_async

    _enqueue_task_with_retry(
        send_email_async,
        kwargs={
            "to_email": to_email,
            "subject": subject,
            "html_body": html_body,
            "plain_text": plain_text,
            "delivery_id": delivery_id,
            "invoice_job_id": invoice_job_id,
            "invoice_closure_id": invoice_closure_id,
        },
        task_id=f"communication-email-delivery-{int(delivery_id)}",
    )


# ---------------------------------------------------------------------------
# Live Socket.IO delivery
# ---------------------------------------------------------------------------

def _run_async(
    coro: Coroutine[Any, Any, Any],
    *,
    diagnostic_context: dict[str, Any] | None = None,
) -> None:
    """Schedule a live push without making it the source of truth."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        try:
            asyncio.run(coro)
        except Exception:
            logger.exception(
                "Live notification delivery failed",
                extra=diagnostic_context or {},
            )
        return

    task = loop.create_task(coro)

    def log_task_failure(completed_task: asyncio.Task) -> None:
        if completed_task.cancelled():
            return

        error = completed_task.exception()
        if error:
            logger.error(
                "Live notification task failed",
                exc_info=(type(error), error, error.__traceback__),
                extra=diagnostic_context or {},
            )

    task.add_done_callback(log_task_failure)


def push_live(
    role: str,
    tenant_id: str,
    job_id: Any,
    payload: dict,
    correlation_id: str | None = None,
) -> None:
    """Push a persisted notification to its authorized recipient room.

    The notification must be persisted and committed before calling this
    function. The database remains the source of truth.

    Room routing:
    - customer: customer_{customer_user_id}
    - technician: authenticated technician room
    - org_admin: tenant-specific dispatcher room

    Customer and technician notifications must never be broadcast to an
    entire tenant because that could expose private notification content.
    """
    if not isinstance(payload, dict):
        logger.warning(
            "Skipping live notification with invalid payload (job=%s)",
            job_id,
        )
        return

    normalized_role = str(role).strip().lower()
    normalized_tenant = str(tenant_id).strip()

    try:
        from app.services.socket_manager import ws_manager

        if normalized_role == "customer":
            recipient_id = payload.get("recipient_id")

            if recipient_id is None or not str(recipient_id).strip():
                logger.warning(
                    "Skipping customer notification without recipient_id "
                    "(job=%s tenant=%s)",
                    job_id,
                    normalized_tenant,
                )
                return

            _run_async(
                ws_manager.broadcast_to_customer(
                    str(recipient_id),
                    payload,
                ),
                diagnostic_context={
                    "job_id": str(job_id),
                    "recipient_role": normalized_role,
                    "recipient_tenant_id": normalized_tenant,
                    "event_type": payload.get("event"),
                    "event_version": payload.get("event_version"),
                    "correlation_id": correlation_id,
                },
            )
            return

        if normalized_role == "technician":
            recipient_id = payload.get("recipient_id")

            if recipient_id is None or not str(recipient_id).strip():
                logger.warning(
                    "Skipping technician notification without recipient_id "
                    "(job=%s tenant=%s)",
                    job_id,
                    normalized_tenant,
                )
                return

            _run_async(
                ws_manager.broadcast_to_technician(
                    str(recipient_id),
                    payload,
                ),
                diagnostic_context={
                    "job_id": str(job_id),
                    "recipient_role": normalized_role,
                    "recipient_tenant_id": normalized_tenant,
                    "event_type": payload.get("event"),
                    "event_version": payload.get("event_version"),
                    "correlation_id": correlation_id,
                },
            )
            return

        if normalized_role == "org_admin":
            _run_async(
                ws_manager.broadcast(
                    f"tenant:{normalized_tenant}:dispatchers",
                    payload,
                ),
                diagnostic_context={
                    "job_id": str(job_id),
                    "recipient_role": normalized_role,
                    "recipient_tenant_id": normalized_tenant,
                    "event_type": payload.get("event"),
                    "event_version": payload.get("event_version"),
                    "correlation_id": correlation_id,
                },
            )
            return

        logger.debug(
            "No live notification route configured for role=%s job=%s",
            normalized_role,
            job_id,
        )

    except Exception:
        logger.exception(
            "Unable to publish live notification",
            extra={
                "job_id": str(job_id),
                "recipient_role": normalized_role,
                "recipient_tenant_id": normalized_tenant,
                "event_type": payload.get("event"),
                "event_version": payload.get("event_version"),
                "correlation_id": correlation_id,
            },
        )
