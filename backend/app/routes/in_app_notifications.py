from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    get_current_user,
    AuthenticatedUser,
    require_role,
)
from app.auth.rbac import UserRole

from ..database import get_db
from ..models import Technician, InAppNotification
from ..schemas import (
    PaginatedNotificationsResponse,
    BatchReadRequest,
)

router = APIRouter(
    tags=["In-App Notifications"]
)
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

    if current_user.is_super_admin:
        return query

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
        require_role(UserRole.SUPER_ADMIN)
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