"""
test_ai_processing_queue.py

Comprehensive test suite for Story: Create AI processing queue (Celery Queue Management).
Validates dedicated Celery queue and routing configuration for asynchronous LangGraph/AI workloads:
- Route AI background tasks (workflow execution, prompt analytics, agent processing) to 'ai_processing' queue.
- Prevent model processing and LLM inference from blocking operational queues (dispatch, GPS, notifications, billing).
- Contract validation:
    {
        "status": "CONFIGURED",
        "queue": "ai_processing",
        "routing_key": "ai"
    }
- Preservation of tenant_id, correlation_id, and entity metadata.
- Bounded execution time and retry behavior (no indefinite retries for permanent errors).
- Idempotency to prevent duplicate model executions for identical requests.
"""

import json
from unittest.mock import MagicMock, patch
from celery import Celery
from kombu import Queue
import pytest

from app.celery_app import (
    celery_app,
    AI_QUEUE,
    AI_ROUTING_KEY,
    BILLING_QUEUE,
    NOTIFICATION_QUEUE,
    GPS_QUEUE,
    DEFAULT_QUEUE,
    AI_TASK_ROUTES,
    get_ai_processing_queue_config,
    create_ai_processing_queue,
    CreateAiProcessingQueue,
    Create_ai_processing_queue,
    CreateAiQueue,
    create_ai_queue,
)
from app.services.ai.FieldOpsAI import (
    AI_QUEUE as AI_PKG_QUEUE,
    AI_ROUTING_KEY as AI_PKG_ROUTING_KEY,
    get_ai_processing_queue_config as ai_pkg_get_config,
    create_ai_processing_queue as ai_pkg_create_queue,
    CreateAiProcessingQueue as AiPkgCreateAiProcessingQueue,
    Create_ai_processing_queue as AiPkgCreate_ai_processing_queue,
    CreateAiQueue as AiPkgCreateAiQueue,
    create_ai_queue as ai_pkg_create_ai_queue,
)
from app.services.ai.FieldOpsAI.graph import (
    AI_QUEUE as GRAPH_AI_QUEUE,
    AI_ROUTING_KEY as GRAPH_AI_ROUTING_KEY,
    get_ai_processing_queue_config as graph_get_config,
    create_ai_processing_queue as graph_create_queue,
)
from app.tasks import (
    create_ai_processing_queue_task,
    execute_fieldops_workflow_async_task,
    execute_ai_workflow_task,
    aggregate_prompt_analytics_task,
    process_ai_workload_task,
    _execute_ai_workflow_once,
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

def test_ai_processing_queue_expected_contract():
    """Verify create_ai_processing_queue returns the exact expected output contract."""
    result = create_ai_processing_queue()

    assert result == {
        "status": "CONFIGURED",
        "queue": "ai_processing",
        "routing_key": "ai",
    }
    assert result["status"] == "CONFIGURED"
    assert result["queue"] == "ai_processing"
    assert result["routing_key"] == "ai"


def test_get_ai_processing_queue_config():
    """Verify get_ai_processing_queue_config returns the canonical contract."""
    config = get_ai_processing_queue_config()
    assert config == {
        "status": "CONFIGURED",
        "queue": "ai_processing",
        "routing_key": "ai",
    }


def test_ai_queue_aliases_and_imports():
    """Verify story naming aliases and service re-exports point to the same callable."""
    assert CreateAiProcessingQueue is create_ai_processing_queue
    assert Create_ai_processing_queue is create_ai_processing_queue
    assert CreateAiQueue is create_ai_processing_queue
    assert create_ai_queue is create_ai_processing_queue

    # Re-exports from app.services.ai.FieldOpsAI
    assert AI_PKG_QUEUE == "ai_processing"
    assert AI_PKG_ROUTING_KEY == "ai"
    assert ai_pkg_get_config() == {"status": "CONFIGURED", "queue": "ai_processing", "routing_key": "ai"}
    assert ai_pkg_create_queue is create_ai_processing_queue
    assert AiPkgCreateAiProcessingQueue is create_ai_processing_queue
    assert AiPkgCreate_ai_processing_queue is create_ai_processing_queue
    assert AiPkgCreateAiQueue is create_ai_processing_queue
    assert ai_pkg_create_ai_queue is create_ai_processing_queue

    # Re-exports from app.services.ai.FieldOpsAI.graph
    assert GRAPH_AI_QUEUE == "ai_processing"
    assert GRAPH_AI_ROUTING_KEY == "ai"
    assert graph_get_config() == {"status": "CONFIGURED", "queue": "ai_processing", "routing_key": "ai"}
    assert graph_create_queue is create_ai_processing_queue


# =============================================================================
# 2. Celery App Registration Tests
# =============================================================================

def test_celery_task_queues_registered_ai():
    """Verify the ai_processing queue is configured in Celery task_queues."""
    queue_names = {
        q.name if hasattr(q, "name") else str(q)
        for q in celery_app.conf.task_queues
    }
    assert "ai_processing" in queue_names
    assert "notifications" in queue_names
    assert "gps_processing" in queue_names
    assert "billing" in queue_names
    assert "default" in queue_names


def test_celery_task_routes_ai_mapping():
    """Verify all AI and LangGraph tasks are routed to the ai_processing queue."""
    routes = celery_app.conf.task_routes

    assert routes["app.tasks.execute_fieldops_workflow_async_task"] == {
        "queue": "ai_processing",
        "routing_key": "ai",
    }
    assert routes["app.tasks.execute_ai_workflow_task"] == {
        "queue": "ai_processing",
        "routing_key": "ai",
    }
    assert routes["app.tasks.aggregate_prompt_analytics_task"] == {
        "queue": "ai_processing",
        "routing_key": "ai",
    }
    assert routes["app.tasks.process_ai_workload_task"] == {
        "queue": "ai_processing",
        "routing_key": "ai",
    }
    assert routes["app.tasks.create_ai_processing_queue_task"] == {
        "queue": "ai_processing",
        "routing_key": "ai",
    }


# =============================================================================
# 3. Workload Isolation Tests
# =============================================================================

def test_ai_and_other_queues_isolation():
    """Verify AI tasks are not mapped to default, notifications, gps, or billing queues."""
    ai_routes = AI_TASK_ROUTES

    for task_name, route_info in ai_routes.items():
        assert route_info["queue"] == "ai_processing", f"{task_name} should route to ai_processing"
        assert route_info["routing_key"] == "ai", f"{task_name} should use routing_key 'ai'"
        assert route_info["queue"] != DEFAULT_QUEUE
        assert route_info["queue"] != NOTIFICATION_QUEUE
        assert route_info["queue"] != GPS_QUEUE
        assert route_info["queue"] != BILLING_QUEUE


# =============================================================================
# 4. Task Metadata & Context Preservation Tests
# =============================================================================

def test_ai_task_signatures_preserve_metadata():
    """Verify AI task payloads accept and propagate tenant_id and correlation_id."""
    res = create_ai_processing_queue_task(
        tenant_id="tenant-alpha",
        correlation_id="corr-ai-1234",
    )
    assert res["status"] == "CONFIGURED"
    assert res["queue"] == "ai_processing"
    assert res["routing_key"] == "ai"

    workload_res = process_ai_workload_task(
        workload_type="PROMPT_EVALUATION",
        payload={"prompt_id": "p-101", "eval_mode": "strict"},
        tenant_id="tenant-beta",
        correlation_id="corr-ai-5678",
    )
    assert workload_res["status"] == "COMPLETED"
    assert workload_res["queue"] == "ai_processing"
    assert workload_res["routing_key"] == "ai"
    assert workload_res["tenant_id"] == "tenant-beta"
    assert workload_res["correlation_id"] == "corr-ai-5678"


# =============================================================================
# 5. LangGraph Workflow Execution & Idempotency Tests
# =============================================================================

def test_ai_workflow_execution_success(fake_redis):
    """Verify successful asynchronous AI workflow execution using LangGraph."""
    req_data = {
        "service": "Electrical",
        "title": "Circuit Breaker Trip",
        "description": "Main circuit breaker keeps tripping after turning on AC.",
        "location": "Anna Nagar, Chennai",
        "priority": "HIGH",
    }

    mock_workflow_output = {
        "valid": True,
        "job_requirement": {
            "service": "Electrical",
            "job_id": 201,
            "required_skill": "Electrical",
            "location": "Anna Nagar, Chennai",
        },
        "total_eligible_count": 3,
        "top_three_technicians": [
            {"technician_id": 1, "score": 95.0},
        ],
    }

    with patch("app.services.ai.FieldOpsAI.graph.execute_fieldops_workflow", return_value=mock_workflow_output) as mock_exec:
        result = _execute_ai_workflow_once(
            redis=fake_redis,
            request_data=req_data,
            tenant_id="tenant-101",
            job_id=201,
            correlation_id="corr-ai-success-1",
            workflow_id="wf-101",
        )

        assert result["status"] == "COMPLETED"
        assert result["queue"] == "ai_processing"
        assert result["tenant_id"] == "tenant-101"
        assert result["correlation_id"] == "corr-ai-success-1"
        assert result["job_id"] == 201
        assert result["workflow_id"] == "wf-101"
        assert result["output"]["valid"] is True
        assert mock_exec.call_count == 1


def test_ai_workflow_idempotency_prevents_duplicate_execution(fake_redis):
    """Verify duplicate workflow requests are returned from Redis markers without duplicate execution."""
    req_data = {
        "service": "Plumbing",
        "title": "Pipe Leak",
        "description": "Water leaking under kitchen sink.",
        "location": "T Nagar, Chennai",
    }
    workflow_id = "wf_unique_idem_99"

    mock_workflow_output = {
        "valid": True,
        "job_requirement": {"job_id": 305, "service": "Plumbing"},
        "top_three_technicians": [{"technician_id": 10, "score": 90.0}],
    }

    with patch("app.services.ai.FieldOpsAI.graph.execute_fieldops_workflow", return_value=mock_workflow_output) as mock_exec:
        # First execution
        res1 = _execute_ai_workflow_once(
            redis=fake_redis,
            request_data=req_data,
            tenant_id="tenant-demo",
            job_id=305,
            workflow_id=workflow_id,
        )
        assert res1["status"] == "COMPLETED"
        assert res1.get("idempotent_duplicate") is not True
        assert mock_exec.call_count == 1

        # Second execution with identical workflow_id
        res2 = _execute_ai_workflow_once(
            redis=fake_redis,
            request_data=req_data,
            tenant_id="tenant-demo",
            job_id=305,
            workflow_id=workflow_id,
        )
        assert res2["status"] == "COMPLETED"
        assert res2.get("idempotent_duplicate") is True
        assert res2["queue"] == "ai_processing"
        # Must NOT execute model/graph a second time
        assert mock_exec.call_count == 1


# =============================================================================
# 6. Tenant Context & Validation Failure Handling Tests
# =============================================================================

def test_ai_workflow_missing_tenant_id_returns_permanent_failure(fake_redis):
    """Verify missing tenant_id fails boundedly without retrying indefinitely."""
    res = _execute_ai_workflow_once(
        redis=fake_redis,
        request_data={"service": "Electrical"},
        tenant_id="",  # Empty tenant
        correlation_id="corr-invalid-tenant",
    )
    assert res["status"] == "FAILED"
    assert res["permanent_failure"] is True
    assert "tenant_id is required" in res["error"]
    assert res["queue"] == "ai_processing"


def test_ai_workflow_invalid_payload_returns_permanent_failure(fake_redis):
    """Verify non-dictionary request_data fails boundedly as permanent failure."""
    res = _execute_ai_workflow_once(
        redis=fake_redis,
        request_data="invalid-string-not-dict",
        tenant_id="tenant-valid",
        correlation_id="corr-invalid-payload",
    )
    assert res["status"] == "FAILED"
    assert res["permanent_failure"] is True
    assert "must be a dictionary" in res["error"]
    assert res["queue"] == "ai_processing"


# =============================================================================
# 7. Idempotence & Custom Celery App Configuration
# =============================================================================

def test_create_ai_processing_queue_idempotence():
    """Verify calling create_ai_processing_queue multiple times is safe and idempotent."""
    res1 = create_ai_processing_queue()
    res2 = create_ai_processing_queue()

    assert res1 == res2
    assert res1["status"] == "CONFIGURED"

    # Queue should appear exactly once in task_queues
    ai_queues = [
        q for q in celery_app.conf.task_queues
        if (q.name if hasattr(q, "name") else str(q)) == "ai_processing"
    ]
    assert len(ai_queues) == 1


def test_create_ai_processing_queue_custom_celery_instance():
    """Verify create_ai_processing_queue configures any custom Celery instance correctly."""
    custom_app = Celery("test_custom_ai")
    custom_app.conf.task_queues = [Queue("default", routing_key="default")]
    custom_app.conf.task_routes = {}

    result = create_ai_processing_queue(custom_app)

    assert result == {
        "status": "CONFIGURED",
        "queue": "ai_processing",
        "routing_key": "ai",
    }
    custom_queue_names = {
        q.name if hasattr(q, "name") else str(q)
        for q in custom_app.conf.task_queues
    }
    assert "ai_processing" in custom_queue_names
    assert "app.tasks.execute_fieldops_workflow_async_task" in custom_app.conf.task_routes
    assert "app.tasks.execute_ai_workflow_task" in custom_app.conf.task_routes


# =============================================================================
# 8. Admin Queue REST Endpoints Tests
# =============================================================================

def test_admin_queue_ai_endpoints():
    """Verify FastAPI admin queue endpoints return expected AI queue contract."""
    from app.routes.admin_queue import (
        get_ai_queue_status,
        configure_ai_queue_endpoint,
    )

    status_res = get_ai_queue_status()
    assert status_res == {
        "status": "CONFIGURED",
        "queue": "ai_processing",
        "routing_key": "ai",
    }

    config_res = configure_ai_queue_endpoint()
    assert config_res == {
        "status": "CONFIGURED",
        "queue": "ai_processing",
        "routing_key": "ai",
    }

