"""
test_gps_processing_queue.py

Comprehensive test suite for Story: Create GPS processing queue (Celery Queue Management).
Validates dedicated Celery queue and routing configuration for high-volume GPS workloads:
- Route GPS processing/purge and ETA calculation workloads to a dedicated 'gps_processing' queue.
- Prevent GPS workload spikes from starving notification, billing, or AI queues.
- Contract validation:
    {
        "status": "CONFIGURED",
        "queue": "gps_processing",
        "routing_key": "gps"
    }
- Preservation of tenant_id, job_id, and correlation_id without exposing secrets.
"""

from celery import Celery
from kombu import Queue
import pytest

from app.celery_app import (
    celery_app,
    GPS_QUEUE,
    GPS_ROUTING_KEY,
    NOTIFICATION_QUEUE,
    NOTIFICATION_ROUTING_KEY,
    DEFAULT_QUEUE,
    DEFAULT_ROUTING_KEY,
    GPS_TASK_ROUTES,
    get_gps_processing_queue_config,
    create_gps_processing_queue,
    CreateGPSProcessingQueue,
    Create_gps_processing_queue,
    CreateGpsProcessingQueue,
    Create_gps_queue,
    create_gps_queue,
)
from app.routes.gps import (
    GPS_QUEUE as ROUTE_GPS_QUEUE,
    GPS_ROUTING_KEY as ROUTE_GPS_ROUTING_KEY,
    get_gps_processing_queue_config as route_get_config,
    create_gps_processing_queue as route_create_queue,
    get_gps_queue_status_route,
)
from app.services.eta_service import (
    GPS_QUEUE as ETA_GPS_QUEUE,
    GPS_ROUTING_KEY as ETA_GPS_ROUTING_KEY,
    get_gps_processing_queue_config as eta_get_config,
    create_gps_processing_queue as eta_create_queue,
)
from app.tasks import (
    create_gps_processing_queue_task,
    daily_gps_purge_task,
    purge_job_gps_data,
    update_eta_task,
    process_gps_tracking_event_task,
)


# =============================================================================
# 1. Output Contract & Basic Configuration Tests
# =============================================================================

def test_gps_processing_queue_expected_contract():
    """Verify create_gps_processing_queue returns the exact expected output contract."""
    result = create_gps_processing_queue()

    assert result == {
        "status": "CONFIGURED",
        "queue": "gps_processing",
        "routing_key": "gps",
    }
    assert result["status"] == "CONFIGURED"
    assert result["queue"] == "gps_processing"
    assert result["routing_key"] == "gps"


def test_get_gps_processing_queue_config():
    """Verify get_gps_processing_queue_config returns the canonical contract dictionary."""
    config = get_gps_processing_queue_config()

    assert config["status"] == "CONFIGURED"
    assert config["queue"] == "gps_processing"
    assert config["routing_key"] == "gps"


# =============================================================================
# 2. Authoritative Aliases & Re-exports
# =============================================================================

def test_gps_queue_aliases_and_imports():
    """Verify all function/class aliases and cross-module re-exports resolve cleanly."""
    assert CreateGPSProcessingQueue is create_gps_processing_queue
    assert Create_gps_processing_queue is create_gps_processing_queue
    assert CreateGpsProcessingQueue is create_gps_processing_queue
    assert Create_gps_queue is create_gps_processing_queue
    assert create_gps_queue is create_gps_processing_queue

    assert route_get_config is get_gps_processing_queue_config
    assert route_create_queue is create_gps_processing_queue
    assert ROUTE_GPS_QUEUE == "gps_processing"
    assert ROUTE_GPS_ROUTING_KEY == "gps"

    assert eta_get_config is get_gps_processing_queue_config
    assert eta_create_queue is create_gps_processing_queue
    assert ETA_GPS_QUEUE == "gps_processing"
    assert ETA_GPS_ROUTING_KEY == "gps"


# =============================================================================
# 3. Celery Task Queues & Task Routes Verification
# =============================================================================

def test_celery_task_queues_registered_gps():
    """Verify celery_app.conf.task_queues contains gps_processing queue with routing key 'gps'."""
    queues = celery_app.conf.task_queues
    assert queues is not None

    queue_names = [q.name for q in queues if hasattr(q, "name")]
    assert "gps_processing" in queue_names
    assert "notifications" in queue_names
    assert "default" in queue_names

    gps_q = next(q for q in queues if getattr(q, "name", None) == "gps_processing")
    assert gps_q.routing_key == "gps"


def test_celery_task_routes_gps_mapping():
    """Verify all key GPS, purge, and ETA tasks are routed to the dedicated gps_processing queue."""
    routes = celery_app.conf.task_routes
    assert routes is not None

    expected_gps_tasks = [
        "app.tasks.daily_gps_purge_task",
        "app.tasks.purge_job_gps_data",
        "app.tasks.purge_job_gps_data_task",
        "app.tasks.update_eta_task",
        "app.tasks.process_gps_tracking_event_task",
        "app.tasks.create_gps_processing_queue_task",
    ]

    for task_name in expected_gps_tasks:
        assert task_name in routes, f"Task {task_name} missing from Celery task_routes"
        route_entry = routes[task_name]
        assert route_entry.get("queue") == "gps_processing", f"Task {task_name} queue is not 'gps_processing'"
        assert route_entry.get("routing_key") == "gps", f"Task {task_name} routing_key is not 'gps'"


# =============================================================================
# 4. Workload Isolation & Non-Starvation
# =============================================================================

def test_gps_and_notification_queue_isolation():
    """Verify GPS tasks and Notification tasks are strictly isolated into distinct queues."""
    routes = celery_app.conf.task_routes

    # GPS tasks must NOT route to notifications or default
    assert routes["app.tasks.daily_gps_purge_task"]["queue"] == "gps_processing"
    assert routes["app.tasks.purge_job_gps_data"]["queue"] == "gps_processing"
    assert routes["app.tasks.update_eta_task"]["queue"] == "gps_processing"

    # Notification tasks must NOT route to gps_processing
    assert routes["app.tasks.send_sms_async"]["queue"] == "notifications"
    assert routes["app.tasks.send_email_async"]["queue"] == "notifications"

    # Default queue remains default
    assert celery_app.conf.task_default_queue == "default"


# =============================================================================
# 5. Metadata Preservation (tenant_id, job_id, correlation_id)
# =============================================================================

def test_gps_task_signatures_preserve_metadata():
    """Verify GPS task wrappers accept tenant_id, job_id, and correlation_id without error."""
    assert callable(create_gps_processing_queue_task)

    result = create_gps_processing_queue_task(
        tenant_id="tenant-gps-42",
        correlation_id="corr-gps-100",
    )
    assert result["status"] == "CONFIGURED"
    assert result["queue"] == "gps_processing"
    assert result["routing_key"] == "gps"


# =============================================================================
# 6. Idempotence & Custom App Configuration
# =============================================================================

def test_create_gps_queue_idempotence():
    """Verify calling create_gps_processing_queue repeatedly is idempotent and does not duplicate queues."""
    res1 = create_gps_processing_queue()
    res2 = create_gps_processing_queue()
    res3 = create_gps_processing_queue()

    assert res1 == res2 == res3

    gps_queues = [q for q in celery_app.conf.task_queues if getattr(q, "name", None) == "gps_processing"]
    assert len(gps_queues) == 1


def test_create_gps_queue_custom_celery_instance():
    """Verify create_gps_processing_queue works on a fresh isolated Celery instance."""
    custom_app = Celery("test_isolated_gps_celery")
    custom_app.conf.task_queues = (Queue("default", routing_key="default"),)
    custom_app.conf.task_routes = {}

    result = create_gps_processing_queue(app=custom_app)
    assert result["status"] == "CONFIGURED"
    assert result["queue"] == "gps_processing"
    assert result["routing_key"] == "gps"

    queue_names = [q.name for q in custom_app.conf.task_queues]
    assert "gps_processing" in queue_names
    assert "app.tasks.update_eta_task" in custom_app.conf.task_routes


# =============================================================================
# 7. Route Endpoints Verification
# =============================================================================

def test_admin_queue_gps_endpoints():
    """Verify FastAPI admin queue endpoints return the canonical GPS queue contract."""
    from app.routes.admin_queue import (
        get_gps_queue_status,
        configure_gps_queue_endpoint,
    )

    status_resp = get_gps_queue_status()
    assert status_resp["status"] == "CONFIGURED"
    assert status_resp["queue"] == "gps_processing"
    assert status_resp["routing_key"] == "gps"

    config_resp = configure_gps_queue_endpoint()
    assert config_resp["status"] == "CONFIGURED"
    assert config_resp["queue"] == "gps_processing"
    assert config_resp["routing_key"] == "gps"


def test_gps_route_queue_status():
    """Verify GET /gps/queue/status returns the canonical GPS queue contract."""
    resp = get_gps_queue_status_route()
    assert resp["status"] == "CONFIGURED"
    assert resp["queue"] == "gps_processing"
    assert resp["routing_key"] == "gps"

