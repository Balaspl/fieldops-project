"""Persist notification cards with tenant-aware idempotency."""

import uuid
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from ......models_legacy import InAppNotification
from .events import JobEvent


def insert_daily_engagement(db: Session, *, tenant_id: str, recipient_id: str,
                            local_date: str, title: str, body: str,
                            job_id: int) -> str | None:
    """Insert one opt-in daily engagement card; duplicate runs are a no-op."""
    if not tenant_id or not recipient_id or not local_date:
        raise ValueError("tenant, recipient, and local date are required")
    dialect = db.get_bind().dialect.name
    insert = pg_insert if dialect == "postgresql" else sqlite_insert if dialect == "sqlite" else None
    if insert is None:
        raise NotImplementedError(f"Notification upsert does not support dialect: {dialect}")
    notification_id = str(uuid.uuid4())
    stmt = insert(InAppNotification).values(
        id=notification_id,
        tenant_id=str(tenant_id),
        recipient_id=str(recipient_id),
        recipient_role="customer",
        customer_user_id=str(recipient_id),
        job_id=str(job_id),
        group_key=f"daily_engagement_{local_date}",
        type="engagement_daily",
        title=title,
        body=body,
        status="UNREAD",
        priority="NORMAL",
        action_url=f"/jobs/{job_id}",
        action_type="NAVIGATE",
        notification_metadata={"category": "engagement", "purpose": "daily_service_reminder", "local_date": local_date},
        event_version=0,
    ).on_conflict_do_nothing(
        index_elements=["tenant_id", "recipient_role", "recipient_id", "group_key"]
    ).returning(InAppNotification.id)
    persisted_id = db.execute(stmt).scalar_one_or_none()
    return str(persisted_id) if persisted_id is not None else None


def upsert_notification(
    db: Session,
    recipient: Any,
    job: Any,
    event: JobEvent,
    title: str,
    body: str,
    meta: dict | None,
    version: int,
) -> str | None:
    """Insert or update a recipient's job notification.

    Returns:
        The persisted notification ID if inserted or updated.
        None if a newer or equal event version already exists.

    The caller is responsible for committing or rolling back the session.
    """

    if (
        not isinstance(version, int)
        or isinstance(version, bool)
        or version < 1
    ):
        raise ValueError("event_version must be a positive integer")

    tenant_id = str(getattr(recipient, "tenant_id", "") or "").strip()
    recipient_id = str(getattr(recipient, "id", "") or "").strip()
    recipient_role = str(getattr(recipient, "role", "") or "").strip().lower()

    if not tenant_id:
        raise ValueError("Notification recipient tenant_id is required")

    if not recipient_id:
        raise ValueError("Notification recipient id is required")

    if not recipient_role:
        raise ValueError("Notification recipient role is required")

    job_id = getattr(job, "id", None)
    if job_id is None:
        raise ValueError("A persisted job is required for a notification")

    dialect = db.get_bind().dialect.name

    if dialect == "postgresql":
        insert = pg_insert
    elif dialect == "sqlite":
        insert = sqlite_insert
    else:
        raise NotImplementedError(
            f"Notification upsert does not support dialect: {dialect}"
        )

    metadata = dict(meta or {})
    actions = metadata.get("actions") or []

    primary = next(
        (
            action
            for action in actions
            if isinstance(action, dict)
            and action.get("primary")
            and action.get("route")
        ),
        None,
    )

    notification_id = str(uuid.uuid4())
    is_cancelled = str(metadata.get("state", "")).strip().lower() in {
        "cancelled",
        "canceled",
    }

    stmt = insert(InAppNotification).values(
        id=notification_id,
        tenant_id=tenant_id,
        recipient_id=recipient_id,
        recipient_role=recipient_role,
        tech_id=(
            recipient_id if recipient_role == "technician" else None
        ),
        customer_user_id=(
            recipient_id if recipient_role == "customer" else None
        ),
        job_id=str(job_id),
        group_key=(
            f"invoice_{job_id}"
            if event == JobEvent.INVOICE_READY
            else f"job_{job_id}"
        ),
        type=event.value,
        title=title,
        body=body,
        status="UNREAD",
        priority="HIGH" if is_cancelled else "NORMAL",
        action_url=primary.get("route") if primary else None,
        action_type="NAVIGATE" if primary else None,
        notification_metadata=metadata,
        event_version=version,
    )

    excluded = stmt.excluded

    stmt = stmt.on_conflict_do_update(
        index_elements=[
            "tenant_id",
            "recipient_role",
            "recipient_id",
            "group_key",
        ],
        set_={
            "type": excluded.type,
            "title": excluded.title,
            "body": excluded.body,
            "status": "UNREAD",
            "read_at": None,
            "dismissed_at": None,
            "priority": excluded.priority,
            "action_url": excluded.action_url,
            "action_type": excluded.action_type,
            "notification_metadata": excluded.notification_metadata,
            "event_version": excluded.event_version,
            "updated_at": func.now(),
        },
        where=or_(
            InAppNotification.event_version.is_(None),
            InAppNotification.event_version < excluded.event_version,
        ),
    ).returning(InAppNotification.id)

    result = db.execute(stmt)
    persisted_id = result.scalar_one_or_none()

    if persisted_id is None:
        # Equal versions are safe replays. Return the existing card so a
        # failed external channel delivery can be retried independently of
        # the already completed job operation. Older versions remain stale.
        existing = (
            db.query(InAppNotification)
            .filter(
                InAppNotification.tenant_id == tenant_id,
                InAppNotification.recipient_role == recipient_role,
                InAppNotification.recipient_id == recipient_id,
                InAppNotification.group_key == (
                    f"invoice_{job_id}"
                    if event == JobEvent.INVOICE_READY
                    else f"job_{job_id}"
                ),
                InAppNotification.event_version == version,
            )
            .first()
        )
        if existing is not None:
            return str(existing.id)

    return str(persisted_id) if persisted_id is not None else None
