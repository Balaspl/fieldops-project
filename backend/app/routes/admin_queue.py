from fastapi import APIRouter, Depends

from app.services.task_queue import PriorityTaskQueue
from app.redis_client import get_redis_client

from app.auth.dependencies import (
    AuthenticatedUser,
    get_current_user,
    require_permission,
)
from app.auth.rbac import Permission


router = APIRouter(
    prefix="/admin/queue",
    tags=["Admin Queue"],
)


def get_task_queue() -> PriorityTaskQueue:
    redis = get_redis_client()
    return PriorityTaskQueue(redis)


@router.get(
    "/stats",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def get_queue_stats(
    queue: PriorityTaskQueue = Depends(get_task_queue),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Return queue statistics for the authenticated user's tenant.
    """

    return queue.stats(
        tenant_id=current_user.tenant_id
    )

@router.get(
    "/notifications",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def get_notification_queue_status() -> dict:
    """Return the configuration and status of the dedicated notification Celery queue."""
    from app.celery_app import get_notification_queue_config
    return get_notification_queue_config()


@router.post(
    "/notifications/configure",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def configure_notification_queue_endpoint() -> dict:
    """Ensure the notification queue is configured on the Celery application."""
    from app.celery_app import create_notification_queue
    return create_notification_queue()

@router.get(
    "/gps",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def get_gps_queue_status() -> dict:
    """Return the configuration and status of the dedicated GPS processing Celery queue."""
    from app.celery_app import get_gps_processing_queue_config
    return get_gps_processing_queue_config()


@router.post(
    "/gps/configure",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def configure_gps_queue_endpoint() -> dict:
    """Ensure the GPS processing queue is configured on the Celery application."""
    from app.celery_app import create_gps_processing_queue
    return create_gps_processing_queue()

@router.get(
    "/billing",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def get_billing_queue_status() -> dict:
    """Return the configuration and status of the dedicated billing Celery queue."""
    from app.celery_app import get_billing_queue_config
    return get_billing_queue_config()


@router.post(
    "/billing/configure",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def configure_billing_queue_endpoint() -> dict:
    """Ensure the billing queue is configured on the Celery application."""
    from app.celery_app import create_billing_queue
    return create_billing_queue()

@router.get(
    "/ai",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def get_ai_queue_status() -> dict:
    """Return the configuration and status of the dedicated AI processing Celery queue."""
    from app.celery_app import get_ai_processing_queue_config
    return get_ai_processing_queue_config()


@router.post(
    "/ai/configure",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def configure_ai_queue_endpoint() -> dict:
    """Ensure the AI processing queue is configured on the Celery application."""
    from app.celery_app import create_ai_processing_queue
    return create_ai_processing_queue()

@router.get(
    "/high-priority",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def get_high_priority_queue_status() -> dict:
    """Return the configuration and status of the dedicated high-priority Celery queue."""
    from app.celery_app import get_high_priority_queue_config
    return get_high_priority_queue_config()


@router.post(
    "/high-priority/configure",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def configure_high_priority_queue_endpoint() -> dict:
    """Ensure the high-priority queue is configured on the Celery application."""
    from app.celery_app import create_high_priority_queue
    return create_high_priority_queue()


# Aliases for /priority
@router.get(
    "/priority",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def get_priority_queue_status_alias() -> dict:
    return get_high_priority_queue_status()


@router.post(
    "/priority/configure",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def configure_priority_queue_endpoint_alias() -> dict:
    return configure_high_priority_queue_endpoint()

@router.get(
    "/reports",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def get_report_queue_status() -> dict:
    """Return the configuration and status of the dedicated report-generation Celery queue."""
    from app.celery_app import get_report_generation_queue_config
    return get_report_generation_queue_config()


@router.post(
    "/reports/configure",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def configure_report_queue_endpoint() -> dict:
    """Ensure the report-generation queue is configured on the Celery application."""
    from app.celery_app import create_report_generation_queue
    return create_report_generation_queue()


# Aliases for /report-generation
@router.get(
    "/report-generation",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def get_report_generation_status_alias() -> dict:
    return get_report_queue_status()


@router.post(
    "/report-generation/configure",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def configure_report_generation_endpoint_alias() -> dict:
    return configure_report_queue_endpoint()

