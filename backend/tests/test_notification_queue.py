"""
test_notification_queue.py

Comprehensive test suite for Story: Create notification queue (Celery Queue Management).
Validates dedicated Celery queue and routing configuration for notification workloads:
- Push, SMS, Email, and related notification tasks are routed to the 'notifications' queue.
- Latency-sensitive dispatch and operational workloads do not compete directly with notifications.
- Contract validation:
    {
        "status": "CONFIGURED",
        "queue": "notifications",
        "routing_key": "notifications"
    }
- Preservation of tenant_id, correlation_id, and entity metadata without exposing secrets.
"""

from celery import Celery
from kombu import Queue
import pytest

from app.celery_app import (
    celery_app,
    NOTIFICATION_QUEUE,
    NOTIFICATION_ROUTING_KEY,
    DEFAULT_QUEUE,
    DEFAULT_ROUTING_KEY,
    NOTIFICATION_TASK_ROUTES,
    get_notification_queue_config,
    create_notification_queue,
    CreateNotificationQueue,
    Create_notification_queue,
)
from app.services.notification_services import (
    NOTIFICATION_QUEUE as SERVICE_NOTIFICATION_QUEUE,
    NOTIFICATION_ROUTING_KEY as SERVICE_NOTIFICATION_ROUTING_KEY,
    get_notification_queue_config as service_get_config,
    create_notification_queue as service_create_queue,
    CreateNotificationQueue as ServiceCreateNotificationQueue,
    Create_notification_queue as ServiceCreate_notification_queue,
)
from app.tasks import (
    create_notification_queue_task,
    send_sms_async,
    send_bulk_sms_async,
    send_email_async,
)


# =============================================================================
# 1. Output Contract & Basic Configuration Tests
# =============================================================================

def test_notification_queue_expected_contract():
    """Verify create_notification_queue returns the exact expected output contract."""
    result = create_notification_queue()

    assert result == {
        "status": "CONFIGURED",
        "queue": "notifications",
        "routing_key": "notifications",
    }
    assert result["status"] == "CONFIGURED"
    assert result["queue"] == "notifications"
    assert result["routing_key"] == "notifications"


def test_get_notification_queue_config():
    """Verify get_notification_queue_config returns the canonical contract dictionary."""
    config = get_notification_queue_config()

    assert config["status"] == "CONFIGURED"
    assert config["queue"] == "notifications"
    assert config["routing_key"] == "notifications"


# =============================================================================
# 2. Authoritative Aliases & Re-exports
# =============================================================================

def test_notification_queue_aliases_and_imports():
    """Verify all class/function aliases and cross-module exports resolve cleanly."""
    assert CreateNotificationQueue is create_notification_queue
    assert Create_notification_queue is create_notification_queue
    assert ServiceCreateNotificationQueue is create_notification_queue
    assert ServiceCreate_notification_queue is create_notification_queue
    assert service_get_config is get_notification_queue_config
    assert service_create_queue is create_notification_queue

    assert SERVICE_NOTIFICATION_QUEUE == "notifications"
    assert SERVICE_NOTIFICATION_ROUTING_KEY == "notifications"


# =============================================================================
# 3. Celery Task Queues & Task Routes Verification
# =============================================================================

def test_celery_task_queues_registered():
    """Verify celery_app.conf.task_queues contains both default and notifications queues."""
    queues = celery_app.conf.task_queues
    assert queues is not None

    queue_names = [q.name for q in queues if hasattr(q, "name")]
    assert "notifications" in queue_names
    assert "default" in queue_names

    notif_queue = next(q for q in queues if getattr(q, "name", None) == "notifications")
    assert notif_queue.routing_key == "notifications"


def test_celery_task_routes_mapping():
    """Verify all key notification tasks are routed to the dedicated notifications queue."""
    routes = celery_app.conf.task_routes
    assert routes is not None

    expected_tasks = [
        "app.tasks.send_sms_async",
        "app.tasks.send_bulk_sms_async",
        "app.tasks.send_email_async",
        "app.tasks.process_transactional_email_outbox",
        "app.tasks.process_transactional_email_outbox_task",
        "app.tasks.send_dispatcher_digest",
        "app.tasks.send_customer_daily_engagement",
        "app.tasks.process_notification_event_task",
        "app.tasks.create_notification_queue_task",
    ]

    for task_name in expected_tasks:
        assert task_name in routes, f"Task {task_name} missing from Celery task_routes"
        route_entry = routes[task_name]
        assert route_entry.get("queue") == "notifications", f"Task {task_name} queue is not 'notifications'"
        assert route_entry.get("routing_key") == "notifications", f"Task {task_name} routing_key is not 'notifications'"


# =============================================================================
# 4. Workload Isolation & Non-Interference
# =============================================================================

def test_notification_and_default_queue_isolation():
    """Verify notification queue does not interfere with default queue routing."""
    assert celery_app.conf.task_default_queue == "default"
    assert celery_app.conf.task_default_routing_key == "default"

    # Tasks not in NOTIFICATION_TASK_ROUTES default to default queue
    routes = celery_app.conf.task_routes
    assert "app.tasks.process_broker_restart_recovery_task" not in routes
    assert "app.tasks.process_kafka_failure_recovery_task" not in routes
    assert "app.tasks.auto_requeue_dlq" not in routes


# =============================================================================
# 5. Metadata Preservation (tenant_id & correlation_id)
# =============================================================================

def test_notification_task_signatures_preserve_metadata():
    """Verify notification task functions accept tenant_id and correlation_id without TypeError."""
    # Celery task wrappers retain function signature
    assert callable(create_notification_queue_task)

    # Calling create_notification_queue_task with tenant/correlation metadata
    result = create_notification_queue_task(
        tenant_id="tenant-acme-1",
        correlation_id="corr-xyz-99",
    )
    assert result["status"] == "CONFIGURED"
    assert result["queue"] == "notifications"
    assert result["routing_key"] == "notifications"


# =============================================================================
# 6. Idempotence & Custom App Configuration
# =============================================================================

def test_create_notification_queue_idempotence():
    """Verify calling create_notification_queue repeatedly is idempotent and does not duplicate queues."""
    res1 = create_notification_queue()
    res2 = create_notification_queue()
    res3 = create_notification_queue()

    assert res1 == res2 == res3

    # Check no duplicate queues in task_queues tuple
    notif_queues = [q for q in celery_app.conf.task_queues if getattr(q, "name", None) == "notifications"]
    assert len(notif_queues) == 1


def test_create_notification_queue_custom_celery_instance():
    """Verify create_notification_queue works on a fresh isolated Celery instance."""
    custom_app = Celery("test_isolated_celery")
    custom_app.conf.task_queues = (Queue("default", routing_key="default"),)
    custom_app.conf.task_routes = {}

    result = create_notification_queue(app=custom_app)
    assert result["status"] == "CONFIGURED"
    assert result["queue"] == "notifications"
    assert result["routing_key"] == "notifications"

    queue_names = [q.name for q in custom_app.conf.task_queues]
    assert "notifications" in queue_names
    assert "app.tasks.send_sms_async" in custom_app.conf.task_routes


# =============================================================================
# 7. Admin Endpoint Route Verification
# =============================================================================

def test_admin_queue_notifications_endpoints():
    """Verify FastAPI admin queue endpoints return the canonical notification queue contract."""
    from app.routes.admin_queue import (
        get_notification_queue_status,
        configure_notification_queue_endpoint,
    )

    status_resp = get_notification_queue_status()
    assert status_resp["status"] == "CONFIGURED"
    assert status_resp["queue"] == "notifications"
    assert status_resp["routing_key"] == "notifications"

    config_resp = configure_notification_queue_endpoint()
    assert config_resp["status"] == "CONFIGURED"
    assert config_resp["queue"] == "notifications"
    assert config_resp["routing_key"] == "notifications"

