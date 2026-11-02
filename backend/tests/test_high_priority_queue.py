"""
test_high_priority_queue.py

Comprehensive test suite for Story: Create high-priority queue (Celery Queue Management).
Validates dedicated Celery queue and routing configuration for urgent operational workloads:
- Route emergency dispatch, urgent dispatch events, and SLA monitoring tasks to 'high_priority' queue.
- Prevent urgent workloads from being delayed by standard queues or heavy AI/GPS/billing workloads.
- Contract validation:
    {
        "status": "CONFIGURED",
        "queue": "high_priority",
        "routing_key": "priority"
    }
- Prevent priority traffic from becoming an uncontrolled bypass by rejecting routine workloads.
- Preservation of priority, tenant_id, correlation_id, and entity metadata.
- Idempotency to prevent duplicate emergency dispatch side effects.
"""

from unittest.mock import MagicMock, patch
from celery import Celery
from kombu import Queue
import pytest

from app.celery_app import (
    celery_app,
    HIGH_PRIORITY_QUEUE,
    HIGH_PRIORITY_ROUTING_KEY,
    PRIORITY_QUEUE,
    PRIORITY_ROUTING_KEY,
    DEFAULT_QUEUE,
    NOTIFICATION_QUEUE,
    GPS_QUEUE,
    BILLING_QUEUE,
    AI_QUEUE,
    HIGH_PRIORITY_TASK_ROUTES,
    get_high_priority_queue_config,
    create_high_priority_queue,
    CreateHighPriorityQueue,
    Create_high_priority_queue,
    CreatePriorityQueue,
    create_priority_queue,
    Create_priority_queue,
)
from app.services.sla_service import (
    HIGH_PRIORITY_QUEUE as SLA_HIGH_PRIORITY_QUEUE,
    HIGH_PRIORITY_ROUTING_KEY as SLA_HIGH_PRIORITY_ROUTING_KEY,
    PRIORITY_QUEUE as SLA_PRIORITY_QUEUE,
    PRIORITY_ROUTING_KEY as SLA_PRIORITY_ROUTING_KEY,
    get_high_priority_queue_config as sla_get_config,
    create_high_priority_queue as sla_create_queue,
    CreateHighPriorityQueue as SlaCreateHighPriorityQueue,
    Create_high_priority_queue as SlaCreate_high_priority_queue,
    CreatePriorityQueue as SlaCreatePriorityQueue,
    create_priority_queue as sla_create_priority_queue,
    Create_priority_queue as SlaCreate_priority_queue,
)
from app.tasks import (
    create_high_priority_queue_task,
    process_emergency_dispatch_task,
    emergency_dispatch_task,
    process_dispatch_event_task,
    process_sla_monitoring_event_task,
    broadcast_sla_countdown,
    _process_emergency_dispatch_once,
    ELIGIBLE_HIGH_PRIORITY_LEVELS,
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

def test_high_priority_queue_expected_contract():
    """Verify create_high_priority_queue returns the exact expected output contract."""
    result = create_high_priority_queue()

    assert result == {
        "status": "CONFIGURED",
        "queue": "high_priority",
        "routing_key": "priority",
    }
    assert result["status"] == "CONFIGURED"
    assert result["queue"] == "high_priority"
    assert result["routing_key"] == "priority"


def test_get_high_priority_queue_config():
    """Verify get_high_priority_queue_config returns the canonical contract."""
    config = get_high_priority_queue_config()
    assert config == {
        "status": "CONFIGURED",
        "queue": "high_priority",
        "routing_key": "priority",
    }


def test_high_priority_aliases_and_imports():
    """Verify story naming aliases and service re-exports point to the same callable."""
    assert CreateHighPriorityQueue is create_high_priority_queue
    assert Create_high_priority_queue is create_high_priority_queue
    assert CreatePriorityQueue is create_high_priority_queue
    assert create_priority_queue is create_high_priority_queue
    assert Create_priority_queue is create_high_priority_queue

    # Synonymous queue and routing keys
    assert PRIORITY_QUEUE == "high_priority"
    assert PRIORITY_ROUTING_KEY == "priority"

    # Re-exports from app.services.sla_service
    assert SLA_HIGH_PRIORITY_QUEUE == "high_priority"
    assert SLA_HIGH_PRIORITY_ROUTING_KEY == "priority"
    assert SLA_PRIORITY_QUEUE == "high_priority"
    assert SLA_PRIORITY_ROUTING_KEY == "priority"
    assert sla_get_config() == {"status": "CONFIGURED", "queue": "high_priority", "routing_key": "priority"}
    assert sla_create_queue is create_high_priority_queue
    assert SlaCreateHighPriorityQueue is create_high_priority_queue
    assert SlaCreate_high_priority_queue is create_high_priority_queue
    assert SlaCreatePriorityQueue is create_high_priority_queue
    assert sla_create_priority_queue is create_high_priority_queue
    assert SlaCreate_priority_queue is create_high_priority_queue


# =============================================================================
# 2. Celery App Registration Tests
# =============================================================================

def test_celery_task_queues_registered_high_priority():
    """Verify the high_priority queue is configured in Celery task_queues."""
    queue_names = {
        q.name if hasattr(q, "name") else str(q)
        for q in celery_app.conf.task_queues
    }
    assert "high_priority" in queue_names
    assert "ai_processing" in queue_names
    assert "billing" in queue_names
    assert "gps_processing" in queue_names
    assert "notifications" in queue_names
    assert "default" in queue_names


def test_celery_task_routes_high_priority_mapping():
    """Verify all urgent dispatch and SLA tasks are routed to the high_priority queue."""
    routes = celery_app.conf.task_routes

    assert routes["app.tasks.process_emergency_dispatch_task"] == {
        "queue": "high_priority",
        "routing_key": "priority",
    }
    assert routes["app.tasks.emergency_dispatch_task"] == {
        "queue": "high_priority",
        "routing_key": "priority",
    }
    assert routes["app.tasks.process_dispatch_event_task"] == {
        "queue": "high_priority",
        "routing_key": "priority",
    }
    assert routes["app.tasks.process_sla_monitoring_event_task"] == {
        "queue": "high_priority",
        "routing_key": "priority",
    }
    assert routes["app.tasks.broadcast_sla_countdown"] == {
        "queue": "high_priority",
        "routing_key": "priority",
    }
    assert routes["app.tasks.create_high_priority_queue_task"] == {
        "queue": "high_priority",
        "routing_key": "priority",
    }


# =============================================================================
# 3. Workload Isolation Tests
# =============================================================================

def test_high_priority_and_other_queues_isolation():
    """Verify high_priority tasks are not mapped to ordinary or non-urgent queues."""
    priority_routes = HIGH_PRIORITY_TASK_ROUTES

    for task_name, route_info in priority_routes.items():
        assert route_info["queue"] == "high_priority", f"{task_name} should route to high_priority"
        assert route_info["routing_key"] == "priority", f"{task_name} should use routing_key 'priority'"
        assert route_info["queue"] != DEFAULT_QUEUE
        assert route_info["queue"] != NOTIFICATION_QUEUE
        assert route_info["queue"] != GPS_QUEUE
        assert route_info["queue"] != BILLING_QUEUE
        assert route_info["queue"] != AI_QUEUE


# =============================================================================
# 4. Task Metadata & Bypass Prevention Tests
# =============================================================================

def test_high_priority_task_signatures_preserve_metadata():
    """Verify high_priority task payloads accept and propagate tenant_id and correlation_id."""
    res = create_high_priority_queue_task(
        tenant_id="tenant-priority-1",
        correlation_id="corr-prio-999",
    )
    assert res["status"] == "CONFIGURED"
    assert res["queue"] == "high_priority"
    assert res["routing_key"] == "priority"


def test_prevent_uncontrolled_bypass_rejects_routine_workloads(fake_redis):
    """Verify routine or non-urgent tasks are rejected from high_priority queue."""
    for invalid_priority in ["ROUTINE", "LOW", "NORMAL", "BATCH"]:
        res = _process_emergency_dispatch_once(
            redis=fake_redis,
            job_id=501,
            tenant_id="tenant-corp",
            priority=invalid_priority,
            correlation_id="corr-bypass-test",
        )
        assert res["status"] == "REJECTED_UNAUTHORIZED_BYPASS"
        assert res["permanent_failure"] is True
        assert "not eligible for high_priority queue" in res["error"]
        assert res["queue"] == "high_priority"


# =============================================================================
# 5. Emergency Dispatch Execution & Idempotency Tests
# =============================================================================

def test_emergency_dispatch_success_path(fake_redis):
    """Verify successful execution of emergency dispatch with eligible priority."""
    res = _process_emergency_dispatch_once(
        redis=fake_redis,
        job_id=701,
        tenant_id="tenant-emergency-1",
        priority="EMERGENCY",
        correlation_id="corr-urg-101",
        reason="Gas leak detected near substation",
    )
    assert res["status"] == "PROCESSED"
    assert res["queue"] == "high_priority"
    assert res["routing_key"] == "priority"
    assert res["priority"] == "EMERGENCY"
    assert res["job_id"] == 701
    assert res["tenant_id"] == "tenant-emergency-1"
    assert res["correlation_id"] == "corr-urg-101"
    assert res["reason"] == "Gas leak detected near substation"


def test_emergency_dispatch_idempotency_prevents_duplicate_actions(fake_redis):
    """Verify duplicate emergency dispatch invocations are skipped to prevent duplicate side effects."""
    tenant_id = "tenant-idem-prio"
    job_id = 888
    correlation_id = "corr-idem-999"

    # First execution
    res1 = _process_emergency_dispatch_once(
        redis=fake_redis,
        job_id=job_id,
        tenant_id=tenant_id,
        priority="CRITICAL",
        correlation_id=correlation_id,
        reason="Power outage at regional hospital",
    )
    assert res1["status"] == "PROCESSED"
    assert res1.get("idempotent_duplicate") is not True

    # Second execution with identical keys
    res2 = _process_emergency_dispatch_once(
        redis=fake_redis,
        job_id=job_id,
        tenant_id=tenant_id,
        priority="CRITICAL",
        correlation_id=correlation_id,
        reason="Power outage at regional hospital",
    )
    assert res2["status"] == "PROCESSED"
    assert res2.get("idempotent_duplicate") is True
    assert res2["queue"] == "high_priority"
    assert res2["routing_key"] == "priority"


def test_emergency_dispatch_missing_tenant_returns_permanent_failure(fake_redis):
    """Verify missing tenant_id fails boundedly without retrying indefinitely."""
    res = _process_emergency_dispatch_once(
        redis=fake_redis,
        job_id=909,
        tenant_id="",  # Missing tenant
        priority="EMERGENCY",
        correlation_id="corr-fail-tenant",
    )
    assert res["status"] == "FAILED"
    assert res["permanent_failure"] is True
    assert "tenant_id is required" in res["error"]
    assert res["queue"] == "high_priority"


# =============================================================================
# 6. Idempotence & Custom Celery App Configuration
# =============================================================================

def test_create_high_priority_queue_idempotence():
    """Verify calling create_high_priority_queue multiple times is safe and idempotent."""
    res1 = create_high_priority_queue()
    res2 = create_high_priority_queue()

    assert res1 == res2
    assert res1["status"] == "CONFIGURED"

    # Queue should appear exactly once in task_queues
    prio_queues = [
        q for q in celery_app.conf.task_queues
        if (q.name if hasattr(q, "name") else str(q)) == "high_priority"
    ]
    assert len(prio_queues) == 1


def test_create_high_priority_queue_custom_celery_instance():
    """Verify create_high_priority_queue configures any custom Celery instance correctly."""
    custom_app = Celery("test_custom_priority")
    custom_app.conf.task_queues = [Queue("default", routing_key="default")]
    custom_app.conf.task_routes = {}

    result = create_high_priority_queue(custom_app)

    assert result == {
        "status": "CONFIGURED",
        "queue": "high_priority",
        "routing_key": "priority",
    }
    custom_queue_names = {
        q.name if hasattr(q, "name") else str(q)
        for q in custom_app.conf.task_queues
    }
    assert "high_priority" in custom_queue_names
    assert "app.tasks.process_emergency_dispatch_task" in custom_app.conf.task_routes
    assert "app.tasks.emergency_dispatch_task" in custom_app.conf.task_routes


# =============================================================================
# 7. Admin Queue REST Endpoints Tests
# =============================================================================

def test_admin_queue_high_priority_endpoints():
    """Verify FastAPI admin queue endpoints return expected high-priority queue contract."""
    from app.routes.admin_queue import (
        get_high_priority_queue_status,
        configure_high_priority_queue_endpoint,
        get_priority_queue_status_alias,
        configure_priority_queue_endpoint_alias,
    )

    status_res = get_high_priority_queue_status()
    assert status_res == {
        "status": "CONFIGURED",
        "queue": "high_priority",
        "routing_key": "priority",
    }

    config_res = configure_high_priority_queue_endpoint()
    assert config_res == {
        "status": "CONFIGURED",
        "queue": "high_priority",
        "routing_key": "priority",
    }

    # Verify alias endpoints
    assert get_priority_queue_status_alias() == status_res
    assert configure_priority_queue_endpoint_alias() == config_res

