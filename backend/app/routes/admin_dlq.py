from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    AuthenticatedUser,
    get_current_user,
    require_permission,
)
from app.auth.rbac import Permission
from app.database import get_db
from app.models.dead_letter_task import DeadLetterTask
from app.redis_client import get_redis_client
from app.runtime.dlq import DeadLetterQueue
from app.services.enterprise_audit import AuditAction, audit_log
from app.services.task_queue import PriorityTaskQueue, TaskPriority


router = APIRouter(
    prefix="/admin/dlq",
    tags=["Admin DLQ"],
)


@router.get(
    "/config",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def get_dlq_config() -> dict:
    """Return failed task handling configuration."""
    from app.celery_app import get_failed_task_handling_config
    return get_failed_task_handling_config()


@router.post(
    "/configure",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def configure_dlq_endpoint() -> dict:
    """Configure failed task handling."""
    from app.celery_app import configure_failed_task_handling
    return configure_failed_task_handling()


@router.get(
    "",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def list_dlq_items(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items = (
        db.query(DeadLetterTask)
        .filter(
            DeadLetterTask.tenant_id == current_user.tenant_id,
            DeadLetterTask.status == "FAILED",
            DeadLetterTask.deleted_at.is_(None),
        )
        .order_by(DeadLetterTask.created_at.desc())
        .all()
    )

    return {
        "count": len(items),
        "items": [
            {
                "id": item.id,
                "task_id": item.task_id,
                "celery_task_id": item.celery_task_id,
                "task_type": item.task_type,
                "tenant_id": item.tenant_id,
                "payload": item.payload,
                "context": item.context,
                "reason": item.reason,
                "error_type": item.error_type,
                "error_message": item.error_message,
                "retry_count": item.retry_count,
                "status": item.status,
                "created_at": item.created_at,
                "failed_at": item.failed_at,
                "requeued_at": item.requeued_at,
                "deleted_at": item.deleted_at,
            }
            for item in items
        ],
    }


@router.post(
    "/{dlq_id}/requeue",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def requeue_dlq_item(
    dlq_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = (
        db.query(DeadLetterTask)
        .filter(
            DeadLetterTask.id == dlq_id,
            DeadLetterTask.tenant_id == current_user.tenant_id,
            DeadLetterTask.status == "FAILED",
            DeadLetterTask.deleted_at.is_(None),
        )
        .first()
    )

    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="DLQ item not found",
        )

    redis = get_redis_client()

    if redis is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis is unavailable",
        )

    queue = PriorityTaskQueue(redis)

    task = {
        "task_id": item.task_id,
        "tenant_id": item.tenant_id,
        "payload": item.payload,
    }

    priority_name = (
        item.payload.get("priority", "NORMAL")
        if isinstance(item.payload, dict)
        else "NORMAL"
    )

    try:
        priority = TaskPriority[priority_name]
    except KeyError:
        priority = TaskPriority.NORMAL

    new_task_id = queue.enqueue(
        task=item.payload,
        priority=priority,
        tenant_id=item.tenant_id,
    )

    item.status = "REQUEUED"
    item.requeued_at = datetime.now(timezone.utc)

    audit_log(
        db,
        action=AuditAction.TASK_DLQ,
        tenant_id=current_user.tenant_id,
        user_id=current_user.user_id,
        role=current_user.role.value,
        entity_type="task",
        entity_id=item.task_id,
        details={
            "operation": "requeue",
            "dlq_id": item.id,
            "new_task_id": new_task_id,
        },
        severity="WARNING",
    )

    db.commit()

    return {
        "success": True,
        "dlq_id": item.id,
        "task_id": item.task_id,
        "new_task_id": new_task_id,
        "status": item.status,
    }


@router.delete(
    "/{dlq_id}",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def delete_dlq_item(
    dlq_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = (
        db.query(DeadLetterTask)
        .filter(
            DeadLetterTask.id == dlq_id,
            DeadLetterTask.tenant_id == current_user.tenant_id,
            DeadLetterTask.deleted_at.is_(None),
        )
        .first()
    )

    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="DLQ item not found",
        )

    redis = get_redis_client()

    if redis is not None:
        dlq = DeadLetterQueue(redis)
        dlq.delete(dlq_id)

    item.status = "DELETED"
    item.deleted_at = datetime.now(timezone.utc)

    audit_log(
        db,
        action=AuditAction.TASK_DLQ,
        tenant_id=current_user.tenant_id,
        user_id=current_user.user_id,
        role=current_user.role.value,
        entity_type="task",
        entity_id=item.task_id,
        details={
            "operation": "delete",
            "dlq_id": item.id,
        },
        severity="WARNING",
    )

    db.commit()

    return {
        "success": True,
        "dlq_id": item.id,
        "status": item.status,
    }