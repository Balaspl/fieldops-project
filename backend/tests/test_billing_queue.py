"""
test_billing_queue.py

Comprehensive test suite for Story: Create billing queue (Celery Queue Management).
Validates dedicated Celery queue and routing configuration for Epic 5 billing/invoice workloads:
- Route invoice lifecycle, payment processing, and billing events to a dedicated 'billing' queue.
- Prevent billing workloads from competing with high-frequency GPS or notification spikes.
- Contract validation:
    {
        "status": "CONFIGURED",
        "queue": "billing",
        "routing_key": "billing"
    }
- Source-of-truth preservation from persisted records and prevention of duplicate financial side-effects.
- Preservation of tenant_id, correlation_id, and entity metadata.
"""

from unittest.mock import MagicMock, patch
from celery import Celery
from kombu import Queue
import pytest

from app.celery_app import (
    celery_app,
    BILLING_QUEUE,
    BILLING_ROUTING_KEY,
    NOTIFICATION_QUEUE,
    GPS_QUEUE,
    DEFAULT_QUEUE,
    BILLING_TASK_ROUTES,
    get_billing_queue_config,
    create_billing_queue,
    CreateBillingQueue,
    Create_billing_queue,
)
from app.services.invoice_service import (
    BILLING_QUEUE as INVOICE_BILLING_QUEUE,
    BILLING_ROUTING_KEY as INVOICE_BILLING_ROUTING_KEY,
    get_billing_queue_config as invoice_get_config,
    create_billing_queue as invoice_create_queue,
    CreateBillingQueue as InvoiceCreateBillingQueue,
    Create_billing_queue as InvoiceCreate_billing_queue,
    invoice_totals,
)
from app.tasks import (
    create_billing_queue_task,
    publish_invoice_event_task,
    publish_payment_event_task,
    process_billing_event_task,
    process_payment_event_task,
    _publish_invoice_event_once,
    _publish_payment_event_once,
)


# =============================================================================
# Fake Redis Fixture for Idempotency Tests
# =============================================================================

class FakeRedis:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None, nx=False):
        if nx and key in self.store:
            return False
        self.store[key] = str(value)
        return True

    def delete(self, *keys):
        count = 0
        for k in keys:
            if k in self.store:
                del self.store[k]
                count += 1
        return count


@pytest.fixture
def fake_redis():
    return FakeRedis()


# =============================================================================
# 1. Output Contract & Basic Configuration Tests
# =============================================================================

def test_billing_queue_expected_contract():
    """Verify create_billing_queue returns the exact expected output contract."""
    result = create_billing_queue()

    assert result == {
        "status": "CONFIGURED",
        "queue": "billing",
        "routing_key": "billing",
    }
    assert result["status"] == "CONFIGURED"
    assert result["queue"] == "billing"
    assert result["routing_key"] == "billing"


def test_get_billing_queue_config():
    """Verify get_billing_queue_config returns the canonical contract dictionary."""
    config = get_billing_queue_config()

    assert config["status"] == "CONFIGURED"
    assert config["queue"] == "billing"
    assert config["routing_key"] == "billing"


# =============================================================================
# 2. Authoritative Aliases & Re-exports
# =============================================================================

def test_billing_queue_aliases_and_imports():
    """Verify all class/function aliases and cross-module re-exports resolve cleanly."""
    assert CreateBillingQueue is create_billing_queue
    assert Create_billing_queue is create_billing_queue
    assert InvoiceCreateBillingQueue is create_billing_queue
    assert InvoiceCreate_billing_queue is create_billing_queue

    assert invoice_get_config is get_billing_queue_config
    assert invoice_create_queue is create_billing_queue
    assert INVOICE_BILLING_QUEUE == "billing"
    assert INVOICE_BILLING_ROUTING_KEY == "billing"


# =============================================================================
# 3. Celery Task Queues & Task Routes Verification
# =============================================================================

def test_celery_task_queues_registered_billing():
    """Verify celery_app.conf.task_queues contains the dedicated billing queue."""
    queues = celery_app.conf.task_queues
    assert queues is not None

    queue_names = [q.name for q in queues if hasattr(q, "name")]
    assert "billing" in queue_names
    assert "notifications" in queue_names
    assert "gps_processing" in queue_names
    assert "default" in queue_names

    billing_q = next(q for q in queues if getattr(q, "name", None) == "billing")
    assert billing_q.routing_key == "billing"


def test_celery_task_routes_billing_mapping():
    """Verify all key billing, invoice, and payment tasks are routed to 'billing' queue."""
    routes = celery_app.conf.task_routes
    assert routes is not None

    expected_billing_tasks = [
        "app.tasks.publish_invoice_event_task",
        "app.tasks.publish_payment_event_task",
        "app.tasks.process_billing_event_task",
        "app.tasks.process_payment_event_task",
        "app.tasks.create_billing_queue_task",
    ]

    for task_name in expected_billing_tasks:
        assert task_name in routes, f"Task {task_name} missing from Celery task_routes"
        route_entry = routes[task_name]
        assert route_entry.get("queue") == "billing", f"Task {task_name} queue is not 'billing'"
        assert route_entry.get("routing_key") == "billing", f"Task {task_name} routing_key is not 'billing'"


# =============================================================================
# 4. Workload Isolation & Non-Interference
# =============================================================================

def test_billing_and_other_queues_isolation():
    """Verify billing tasks are strictly isolated from notification and GPS queues."""
    routes = celery_app.conf.task_routes

    # Billing tasks route to 'billing'
    assert routes["app.tasks.publish_invoice_event_task"]["queue"] == "billing"
    assert routes["app.tasks.publish_payment_event_task"]["queue"] == "billing"

    # Notification tasks route to 'notifications'
    assert routes["app.tasks.send_sms_async"]["queue"] == "notifications"

    # GPS tasks route to 'gps_processing'
    assert routes["app.tasks.daily_gps_purge_task"]["queue"] == "gps_processing"

    # Default queue remains 'default'
    assert celery_app.conf.task_default_queue == "default"


# =============================================================================
# 5. Metadata Preservation (tenant_id & correlation_id)
# =============================================================================

def test_billing_task_signatures_preserve_metadata():
    """Verify billing task wrappers accept tenant_id and correlation_id without error."""
    assert callable(create_billing_queue_task)

    result = create_billing_queue_task(
        tenant_id="tenant-fin-1",
        correlation_id="corr-inv-999",
    )
    assert result["status"] == "CONFIGURED"
    assert result["queue"] == "billing"
    assert result["routing_key"] == "billing"


# =============================================================================
# 6. Idempotency & Prevention of Duplicate Financial Side Effects
# =============================================================================

def test_invoice_and_payment_idempotency_prevents_duplicate_side_effects(fake_redis):
    """Verify duplicate invoice/payment event publishing is intercepted by Redis markers."""
    event_id = "evt_inv_idem_101"

    # Mock the internal lifecycle publishing function
    with patch("app.tasks._publish_invoice_lifecycle_event", return_value={"status": "PUBLISHED"}) as mock_pub:
        # First execution publishes event
        res1 = _publish_invoice_event_once(
            event_id=event_id,
            event_type="INVOICE_GENERATED",
            tenant_id="tenant-1",
            invoice_id="inv-101",
            job_id="job-101",
            redis=fake_redis,
        )
        assert res1["status"] == "PUBLISHED"
        assert res1.get("idempotent_duplicate") is not True
        assert mock_pub.call_count == 1

        # Second execution with same event_id is skipped as duplicate
        res2 = _publish_invoice_event_once(
            event_id=event_id,
            event_type="INVOICE_GENERATED",
            tenant_id="tenant-1",
            invoice_id="inv-101",
            job_id="job-101",
            redis=fake_redis,
        )
        assert res2["status"] == "PUBLISHED"
        assert res2.get("idempotent_duplicate") is True
        # Handler must NOT have been called a second time
        assert mock_pub.call_count == 1


# =============================================================================
# 7. Source of Truth Calculations Verification
# =============================================================================

def test_invoice_totals_source_of_truth():
    """Verify backend-authoritative calculation of subtotal, GST, and total amount."""
    totals = invoice_totals(1000.0)
    assert totals["subtotal"] == 1000.0
    assert totals["gst_rate"] == 5.0
    assert totals["gst_amount"] == 50.0
    assert totals["total_amount"] == 1050.0
    assert totals["currency"] == "INR"


# =============================================================================
# 8. Idempotence & Custom Celery App Configuration
# =============================================================================

def test_create_billing_queue_idempotence():
    """Verify calling create_billing_queue repeatedly is idempotent and does not duplicate queues."""
    res1 = create_billing_queue()
    res2 = create_billing_queue()
    res3 = create_billing_queue()

    assert res1 == res2 == res3

    billing_queues = [q for q in celery_app.conf.task_queues if getattr(q, "name", None) == "billing"]
    assert len(billing_queues) == 1


def test_create_billing_queue_custom_celery_instance():
    """Verify create_billing_queue works on a fresh isolated Celery instance."""
    custom_app = Celery("test_isolated_billing_celery")
    custom_app.conf.task_queues = (Queue("default", routing_key="default"),)
    custom_app.conf.task_routes = {}

    result = create_billing_queue(app=custom_app)
    assert result["status"] == "CONFIGURED"
    assert result["queue"] == "billing"
    assert result["routing_key"] == "billing"

    queue_names = [q.name for q in custom_app.conf.task_queues]
    assert "billing" in queue_names
    assert "app.tasks.publish_invoice_event_task" in custom_app.conf.task_routes


# =============================================================================
# 9. Admin Endpoint Route Verification
# =============================================================================

def test_admin_queue_billing_endpoints():
    """Verify FastAPI admin queue endpoints return the canonical billing queue contract."""
    from app.routes.admin_queue import (
        get_billing_queue_status,
        configure_billing_queue_endpoint,
    )

    status_resp = get_billing_queue_status()
    assert status_resp["status"] == "CONFIGURED"
    assert status_resp["queue"] == "billing"
    assert status_resp["routing_key"] == "billing"

    config_resp = configure_billing_queue_endpoint()
    assert config_resp["status"] == "CONFIGURED"
    assert config_resp["queue"] == "billing"
    assert config_resp["routing_key"] == "billing"
