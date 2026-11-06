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

@router.get(
    "/retry-rules",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def get_retry_rules_status() -> dict:
    """Return the configuration and status of task retry rules."""
    from app.celery_app import get_task_retry_rules_config
    return get_task_retry_rules_config()


@router.post(
    "/retry-rules/configure",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def configure_retry_rules_endpoint() -> dict:
    """Ensure task retry rules are configured on the Celery application."""
    from app.celery_app import configure_task_retry_rules
    return configure_task_retry_rules()


# Aliases for /retry-policy
@router.get(
    "/retry-policy",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def get_retry_policy_status_alias() -> dict:
    return get_retry_rules_status()


@router.post(
    "/retry-policy/configure",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def configure_retry_policy_endpoint_alias() -> dict:
    return configure_retry_rules_endpoint()


# ---------------------------------------------------------------------------
# Failed Task Handling (DLQ & Safe Requeue Support)
# ---------------------------------------------------------------------------

@router.get(
    "/failed-handling",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def get_failed_handling_status() -> dict:
    """Return the configuration and status of failed task handling."""
    from app.celery_app import get_failed_task_handling_config
    return get_failed_task_handling_config()


@router.post(
    "/failed-handling/configure",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def configure_failed_handling_endpoint() -> dict:
    """Ensure failed task handling is configured on Celery."""
    from app.celery_app import configure_failed_task_handling
    return configure_failed_task_handling()


# Aliases for /dlq/config and /failed-tasks
@router.get(
    "/dlq/config",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def get_dlq_config_alias() -> dict:
    return get_failed_handling_status()


@router.post(
    "/dlq/configure",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def configure_dlq_endpoint_alias() -> dict:
    return configure_failed_handling_endpoint()


@router.get(
    "/failed-tasks",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def get_failed_tasks_status_alias() -> dict:
    return get_failed_handling_status()


@router.post(
    "/failed-tasks/configure",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def configure_failed_tasks_endpoint_alias() -> dict:
    return configure_failed_handling_endpoint()


# ---------------------------------------------------------------------------
# Task Timeouts (Bounded Execution & Worker Timeouts)
# ---------------------------------------------------------------------------

@router.get(
    "/timeouts",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def get_task_timeouts_status() -> dict:
    """Return the configuration and status of task timeouts."""
    from app.celery_app import get_task_timeouts_config
    return get_task_timeouts_config()


@router.post(
    "/timeouts/configure",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def configure_task_timeouts_endpoint() -> dict:
    """Ensure task timeouts are configured on Celery."""
    from app.celery_app import configure_task_timeouts
    return configure_task_timeouts()


# Aliases for /task-timeouts
@router.get(
    "/task-timeouts",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def get_task_timeouts_status_alias() -> dict:
    return get_task_timeouts_status()


@router.post(
    "/task-timeouts/configure",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def configure_task_timeouts_endpoint_alias() -> dict:
    return configure_task_timeouts_endpoint()


# ---------------------------------------------------------------------------
# Celery Beat Scheduled Tasks
# ---------------------------------------------------------------------------

@router.get(
    "/schedules",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def get_scheduled_tasks_status() -> dict:
    """Return the configuration and status of Celery Beat scheduled tasks."""
    from app.celery_app import get_scheduled_tasks_config
    return get_scheduled_tasks_config()


@router.post(
    "/schedules/configure",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def configure_scheduled_tasks_endpoint() -> dict:
    """Ensure Celery Beat scheduled tasks are registered and active."""
    from app.celery_app import add_scheduled_tasks
    return add_scheduled_tasks()


# Aliases for /scheduled-tasks
@router.get(
    "/scheduled-tasks",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def get_scheduled_tasks_status_alias() -> dict:
    return get_scheduled_tasks_status()


@router.post(
    "/scheduled-tasks/configure",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def configure_scheduled_tasks_endpoint_alias() -> dict:
    return configure_scheduled_tasks_endpoint()


# ---------------------------------------------------------------------------
# Task Result Tracking Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/tracking/config",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def get_task_result_tracking_config_endpoint() -> dict:
    """Return canonical contract for task result tracking."""
    from app.celery_app import get_task_result_tracking_config
    return get_task_result_tracking_config()


@router.post(
    "/tracking/configure",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def configure_task_result_tracking_endpoint() -> dict:
    """Configure task result tracking on Celery."""
    from app.celery_app import add_task_result_tracking
    return add_task_result_tracking()


@router.get(
    "/tasks/{task_id}/result",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def get_task_result_endpoint(task_id: str) -> dict:
    """Retrieve operational lifecycle/result metadata for a specific task."""
    from app.celery_app import get_task_result
    result = get_task_result(task_id)
    if result is None:
        return {
            "status": "TRACKED",
            "task_id": task_id,
            "state": "PENDING",
            "queue": "default",
        }
    return {
        "status": "TRACKED",
        "task_id": result.get("task_id", task_id),
        "state": result.get("state", "UNKNOWN"),
        "queue": result.get("queue", "default"),
    }


# Aliases for /results/{task_id} and /task-result
@router.get(
    "/results/{task_id}",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def get_task_result_alias(task_id: str) -> dict:
    return get_task_result_endpoint(task_id)


@router.post(
    "/tasks/track",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def track_task_endpoint(payload: dict) -> dict:
    """Explicitly record or update task result tracking."""
    from app.celery_app import track_task_result
    return track_task_result(
        task_id=payload.get("task_id", "example-task-id"),
        state=payload.get("state", "SUCCESS"),
        queue=payload.get("queue", "notifications"),
        tenant_id=payload.get("tenant_id"),
        correlation_id=payload.get("correlation_id"),
        result_data=payload.get("result_data"),
    )


# =============================================================================
# Story: Add Celery Monitoring Endpoints
# =============================================================================

@router.get(
    "/monitoring",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def get_celery_monitoring_status_endpoint() -> dict:
    """Return the configuration and status of Celery operational monitoring."""
    from app.celery_app import get_celery_monitoring_config
    return get_celery_monitoring_config()


@router.get(
    "/monitoring/config",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def get_celery_monitoring_config_endpoint() -> dict:
    """Return canonical Celery monitoring configuration contract."""
    from app.celery_app import get_celery_monitoring_config
    return get_celery_monitoring_config()


@router.post(
    "/monitoring/configure",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def configure_celery_monitoring_endpoint() -> dict:
    """Ensure Celery operational monitoring is active."""
    from app.celery_app import add_celery_monitoring
    return add_celery_monitoring()


@router.get(
    "/monitoring/metrics",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def get_celery_monitoring_metrics_endpoint() -> dict:
    """Return aggregated Celery operational telemetry (queue depth, latency, failures, worker health)."""
    from app.celery_app import get_celery_monitoring_metrics
    return get_celery_monitoring_metrics()


@router.get(
    "/monitoring/health",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def get_celery_worker_health_endpoint() -> dict:
    """Inspect and return Celery worker health and availability."""
    from app.celery_app import get_celery_worker_health
    return get_celery_worker_health()


@router.get(
    "/monitoring/queues",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def get_celery_queues_depth_endpoint() -> dict:
    """Return current queue depths across all registered operational queues."""
    from app.celery_app import get_all_queue_depths
    return get_all_queue_depths()


@router.post(
    "/monitoring/record",
    dependencies=[
        Depends(
            require_permission(
                Permission.DISPATCH_QUEUE_VIEW
            )
        )
    ],
)
def record_celery_metric_endpoint(payload: dict) -> dict:
    """Record a metric event (failure, retry, latency) into Celery monitoring telemetry."""
    from app.celery_app import record_task_failure, record_task_retry, record_task_latency

    metric_type = payload.get("metric", "task_failures")
    queue = payload.get("queue", "default")
    task_id = payload.get("task_id", "unknown")
    tenant_id = payload.get("tenant_id")
    correlation_id = payload.get("correlation_id")

    if metric_type == "task_retries":
        return record_task_retry(
            queue=queue,
            task_id=task_id,
            retry_count=payload.get("retry_count", 1),
            tenant_id=tenant_id,
            correlation_id=correlation_id,
        )
    elif metric_type == "task_latency":
        return record_task_latency(
            queue=queue,
            task_id=task_id,
            latency_seconds=float(payload.get("latency_seconds", 0.0)),
            tenant_id=tenant_id,
            correlation_id=correlation_id,
        )
    else:
        return record_task_failure(
            queue=queue,
            task_id=task_id,
            error=payload.get("error"),
            tenant_id=tenant_id,
            correlation_id=correlation_id,
        )




