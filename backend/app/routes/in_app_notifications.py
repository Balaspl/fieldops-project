from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, cast, desc, exists, func, literal, or_, select, String
from sqlalchemy.orm import Session, aliased

from app.auth.dependencies import (
    get_current_user,
    AuthenticatedUser,
    require_permission,
)
from app.auth.rbac import UserRole, Permission, has_permission

from ..database import get_db
from ..models import Technician, InAppNotification
from ..models_legacy import NotificationChannelDelivery
from ..schemas import (
    PaginatedNotificationsResponse,
    BatchReadRequest,
)

router = APIRouter(
    tags=["In-App Notifications"]
)


@router.get("/admin/communication-center")
async def get_admin_communication_center(
    search: Optional[str] = Query(None, max_length=200),
    channel: str = Query("all", pattern="^(all|in_app|sms|email|push)$"),
    status: str = Query("all", pattern="^(all|unread|read|pending|queued|sending|accepted|sent|delivered|failed|permanent_failure)$"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Read-only, tenant-scoped feed for automatic message activity."""
    if not has_permission(current_user.role, Permission.JOBS_VIEW_ALL):
        raise HTTPException(status_code=403, detail="Dispatcher access required")

    tenant_id = str(current_user.tenant_id)

    def matches_current_notification_event(delivery_model):
        """Ignore delivery history for older versions of a rolling job card."""
        return or_(
            InAppNotification.event_version <= 0,
            and_(
                delivery_model.idempotency_key.like(
                    literal("%:")
                    + InAppNotification.type
                    + literal(":%")
                ),
                delivery_model.idempotency_key.like(
                    literal("%:")
                    + cast(InAppNotification.event_version, String)
                ),
            ),
        )

    def latest_delivery_exists(
        *,
        selected_channel: str | None = None,
        selected_status: str | None = None,
    ):
        """Match filters against the newest tracked delivery per channel."""
        latest = aliased(NotificationChannelDelivery)
        newest_id = (
            select(func.max(NotificationChannelDelivery.id))
            .where(
                NotificationChannelDelivery.notification_id
                == InAppNotification.id,
                NotificationChannelDelivery.tenant_id == tenant_id,
                NotificationChannelDelivery.channel == latest.channel,
                matches_current_notification_event(NotificationChannelDelivery),
            )
            .correlate(InAppNotification, latest)
            .scalar_subquery()
        )
        conditions = [
            latest.id == newest_id,
            latest.notification_id == InAppNotification.id,
            latest.tenant_id == tenant_id,
            matches_current_notification_event(latest),
        ]
        if selected_channel:
            conditions.append(latest.channel == selected_channel)
        if selected_status:
            conditions.append(latest.status == selected_status)
        return exists().where(*conditions)

    query = db.query(InAppNotification).filter(
        InAppNotification.tenant_id == tenant_id,
        InAppNotification.status != "DISMISSED",
    )

    if channel in {"sms", "email", "push"}:
        query = query.filter(
            latest_delivery_exists(
                selected_channel=channel,
            )
        )

    normalized_status = status.lower()
    if normalized_status != "all":
        if normalized_status in {"unread", "read"}:
            query = query.filter(InAppNotification.status == normalized_status.upper())
        elif channel == "in_app":
            query = query.filter(False)
        else:
            query = query.filter(
                latest_delivery_exists(
                    selected_channel=(channel if channel in {"sms", "email", "push"} else None),
                    selected_status=normalized_status,
                )
            )

    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                InAppNotification.title.ilike(term),
                InAppNotification.body.ilike(term),
                InAppNotification.type.ilike(term),
                InAppNotification.job_id.ilike(term),
            )
        )

    total = query.count()
    notifications = query.order_by(
        desc(InAppNotification.updated_at),
        desc(InAppNotification.created_at),
        desc(InAppNotification.id),
    ).offset(offset).limit(limit).all()
    notification_ids = [item.id for item in notifications]
    delivery_rows = (
        db.query(NotificationChannelDelivery)
        .filter(
            NotificationChannelDelivery.tenant_id == tenant_id,
            NotificationChannelDelivery.notification_id.in_(notification_ids),
        )
        .order_by(NotificationChannelDelivery.id.asc())
        .all()
        if notification_ids
        else []
    )
    deliveries_by_notification: dict[str, list[NotificationChannelDelivery]] = {}
    for delivery in delivery_rows:
        deliveries_by_notification.setdefault(delivery.notification_id, []).append(delivery)

    messages = []
    for item in notifications:
        channels = [{
            "channel": "in_app",
            "status": str(item.status or "unread").lower(),
            "attempts": 0,
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        }]
        # The in-app card is updated as a job advances. Delivery attempts from
        # prior event versions point to that same card, so show one latest row
        # per external channel rather than repeating historical channel badges
        # beside the current message.
        latest_by_channel: dict[str, NotificationChannelDelivery] = {}
        for delivery in deliveries_by_notification.get(item.id, []):
            if item.event_version and item.event_version > 0:
                event_marker = f":{item.type}:"
                version_marker = f":{item.event_version}"
                if (
                    event_marker not in (delivery.idempotency_key or "")
                    or not (delivery.idempotency_key or "").endswith(version_marker)
                ):
                    continue
            latest_by_channel[delivery.channel] = delivery
        if channel in {"sms", "email", "push"}:
            selected_deliveries = (
                [latest_by_channel[channel]]
                if channel in latest_by_channel
                else []
            )
        elif channel == "in_app":
            selected_deliveries = []
        else:
            selected_deliveries = list(latest_by_channel.values())
        channels.extend({
            "channel": delivery.channel,
            "status": delivery.status,
            "attempts": delivery.attempts,
            "updated_at": delivery.updated_at.isoformat() if delivery.updated_at else None,
        } for delivery in selected_deliveries)
        if channel == "in_app":
            channels = channels[:1]
        messages.append({
            "id": item.id,
            "job_id": item.job_id,
            "type": item.type,
            "title": item.title,
            "message": item.body or "",
            "recipient_role": item.recipient_role or "customer",
            "priority": item.priority or "NORMAL",
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
            "channels": channels,
        })

    channel_counts: dict[str, int] = {}
    delivery_counts: dict[str, int] = {}
    for message in messages:
        for delivery in message["channels"]:
            key = str(delivery["channel"])
            channel_counts[key] = channel_counts.get(key, 0) + 1
            state = str(delivery["status"])
            delivery_counts[state] = delivery_counts.get(state, 0) + 1

    return {
        "messages": messages,
        "total": total,
        "limit": limit,
        "offset": offset,
        "channel_counts": channel_counts,
        "delivery_counts": delivery_counts,
    }


@router.get(
    "/admin/notifications",
    response_model=PaginatedNotificationsResponse,
)
async def get_admin_notifications(
    status: Optional[str] = None,
    type: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List only dispatch notifications addressed to this tenant user."""
    if not has_permission(current_user.role, Permission.JOBS_VIEW_ALL):
        raise HTTPException(status_code=403, detail="Dispatcher access required")

    query = db.query(InAppNotification).filter(
        InAppNotification.tenant_id == current_user.tenant_id,
        InAppNotification.recipient_role.in_(["dispatcher", "org_admin"]),
        InAppNotification.recipient_id == str(current_user.user_id),
        InAppNotification.status != "DISMISSED",
        (InAppNotification.expires_at.is_(None))
        | (InAppNotification.expires_at > datetime.now(timezone.utc)),
    )
    if status:
        query = query.filter(InAppNotification.status == status.upper())
    if type:
        query = query.filter(InAppNotification.type == type)

    total = query.count()
    notifications = query.order_by(
        desc(InAppNotification.created_at)
    ).offset(offset).limit(limit).all()
    unread_count = db.query(InAppNotification).filter(
        InAppNotification.tenant_id == current_user.tenant_id,
        InAppNotification.recipient_role.in_(["dispatcher", "org_admin"]),
        InAppNotification.recipient_id == str(current_user.user_id),
        InAppNotification.status == "UNREAD",
        (InAppNotification.expires_at.is_(None))
        | (InAppNotification.expires_at > datetime.now(timezone.utc)),
    ).count()
    return {
        "notifications": notifications,
        "unread_count": unread_count,
        "total": total,
    }


def get_current_user_notification_ids(
    db: Session,
    current_user: AuthenticatedUser,
) -> list[str]:
    """Return the possible notification recipient IDs for the current user."""

    recipient_ids = {str(current_user.user_id)}

    numeric_user_id = (
        int(current_user.user_id)
        if str(current_user.user_id).isdigit()
        else -1
    )

    technician = db.query(Technician).filter(
        Technician.tenant_id == current_user.tenant_id,
        (
            Technician.tech_id == str(current_user.user_id)
        )
        | (
            Technician.technician_id == numeric_user_id
        ),
    ).first()

    if technician:
        recipient_ids.add(str(technician.technician_id))

        if technician.tech_id:
            recipient_ids.add(str(technician.tech_id))

    return list(recipient_ids)

def notification_query_for_user(
    db: Session,
    current_user: AuthenticatedUser,
):
    """Return notifications accessible to the authenticated user."""

    query = db.query(InAppNotification)

    query = query.filter(
        InAppNotification.tenant_id == current_user.tenant_id
    )

    if current_user.role == UserRole.TECHNICIAN:
        recipient_ids = get_current_user_notification_ids(
            db,
            current_user,
        )

        query = query.filter(
            InAppNotification.tech_id.in_(recipient_ids)
        )
    elif current_user.role == UserRole.CUSTOMER:
        query = query.filter(
            InAppNotification.customer_user_id == str(current_user.user_id)
        )
    elif has_permission(current_user.role, Permission.JOBS_VIEW_ALL):
        query = query.filter(
            InAppNotification.recipient_role.in_(["dispatcher", "org_admin"]),
            InAppNotification.recipient_id == str(current_user.user_id),
        )
    else:
        query = query.filter(False)

    return query

@router.get(
    "/technicians/{id}/notifications",
    response_model=PaginatedNotificationsResponse,
)
async def get_technician_notifications(
    id: str,
    status: Optional[str] = None,
    type: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role == UserRole.TECHNICIAN:
        recipient_ids = get_current_user_notification_ids(
            db,
            current_user,
        )

        if str(id) not in recipient_ids:
            raise HTTPException(
                status_code=403,
                detail="You can only access your own notifications",
            )
    tech_query = db.query(Technician).filter(
        Technician.tech_id == id
    )

    if not current_user.is_super_admin:
        tech_query = tech_query.filter(
            Technician.tenant_id == current_user.tenant_id
        )

    tech = tech_query.first()

    if not tech:
        raise HTTPException(
            status_code=404,
            detail="Technician not found",
        )

    query = notification_query_for_user(
        db,
        current_user,
    ).filter(
        InAppNotification.tech_id == id,
        InAppNotification.status != "DISMISSED",
    )

    now = datetime.now(timezone.utc)

    query = query.filter(
        (InAppNotification.expires_at.is_(None))
        | (InAppNotification.expires_at > now)
    )

    if status:
        query = query.filter(
            InAppNotification.status == status.upper()
        )

    if type:
        query = query.filter(
            InAppNotification.type == type
        )

    total = query.count()

    notifications = (
        query.order_by(
            desc(InAppNotification.created_at)
        )
        .offset(offset)
        .limit(limit)
        .all()
    )

    unread_query = notification_query_for_user(
        db,
        current_user,
    ).filter(
        InAppNotification.tech_id == id,
        InAppNotification.status == "UNREAD",
        (
            InAppNotification.expires_at.is_(None)
        )
        | (
            InAppNotification.expires_at > now
        ),
    )

    unread_count = unread_query.count()

    return {
        "notifications": notifications,
        "unread_count": unread_count,
        "total": total,
    }

@router.patch("/notifications/{id}/read")
async def mark_notification_read(
    id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    notification = notification_query_for_user(
        db,
        current_user,
    ).filter(
        InAppNotification.id == id
    ).first()

    if not notification:
        raise HTTPException(
            status_code=404,
            detail="Notification not found",
        )

    if notification.status == "UNREAD":
        notification.status = "READ"
        notification.read_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(notification)

    return {
        "status": notification.status,
        "read_at": (
            notification.read_at.isoformat()
            if notification.read_at
            else None
        ),
    }

@router.patch("/notifications/batch-read")
async def batch_mark_read(
    payload: BatchReadRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not payload.notification_ids:
        return {"updated": 0}

    query = notification_query_for_user(
        db,
        current_user,
    ).filter(
        InAppNotification.id.in_(
            payload.notification_ids
        ),
        InAppNotification.status == "UNREAD",
    )

    updated = query.update(
        {
            "status": "READ",
            "read_at": datetime.now(timezone.utc),
        },
        synchronize_session=False,
    )

    db.commit()

    return {"updated": updated}

@router.patch("/notifications/{id}/dismiss")
async def dismiss_notification(
    id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    notification = notification_query_for_user(
        db,
        current_user,
    ).filter(
        InAppNotification.id == id
    ).first()

    if not notification:
        raise HTTPException(
            status_code=404,
            detail="Notification not found",
        )

    notification.status = "DISMISSED"
    notification.dismissed_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(notification)

    return {
        "status": notification.status,
        "dismissed_at": (
            notification.dismissed_at.isoformat()
            if notification.dismissed_at
            else None
        ),
    }

@router.delete(
    "/notifications/system/cleanup",
    status_code=204,
)
async def cleanup_notifications(
    current_user: AuthenticatedUser = Depends(
        require_permission(Permission.NOTIFICATIONS_MANAGE)
    ),
    db: Session = Depends(get_db),
):
    threshold = (
        datetime.now(timezone.utc)
        - timedelta(days=30)
    )

    db.query(InAppNotification).filter(
        InAppNotification.created_at < threshold
    ).delete(
        synchronize_session=False
    )

    db.commit()
    return None
