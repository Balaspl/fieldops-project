"""
test_failed_task_handling.py

Comprehensive test suite for Story: Configure failed task handling (Celery Queue Management).
Validates:
- Canonical JSON contract:
    {
        "status": "FAILED_HANDLED",
        "failure_action": "DLQ",
        "requeue_supported": true
    }
- Metadata capture: task name, queue, arguments metadata, exception category, correlation_id, tenant_id.
- Dual-persistence to existing DLQ (Redis + PostgreSQL).
- Prevention of sensitive payload leakage (redaction of passwords, api keys, tokens, secrets, credit cards).
- Support for safe requeue and replay (requeue_supported=True).
- Tenant isolation and validation.
- FastAPI administrative endpoints and aliases.
"""

from unittest.mock import MagicMock, patch
import uuid
import pytest

from app.celery_app import (
    FAILED_TASK_HANDLING_CONFIG,
    get_failed_task_handling_config,
    configure_failed_task_handling,
    ConfigureFailedTaskHandling,
    Configure_failed_task_handling,
    configure_failed_tasks,
    ConfigureFailedTasks,
    get_failed_tasks_config,
)
from app.runtime.dlq import (
    DeadLetterQueue,
    handle_failed_task,
    sanitize_payload,
    get_failed_task_handling_config as runtime_get_config,
    configure_failed_task_handling as runtime_configure,
    ConfigureFailedTaskHandling as RuntimeConfigureFailedTaskHandling,
    Configure_failed_task_handling as RuntimeConfigure_failed_task_handling,
    configure_failed_tasks as runtime_configure_failed_tasks,
    ConfigureFailedTasks as RuntimeConfigureFailedTasks,
    get_failed_tasks_config as runtime_get_failed_tasks_config,
)
from app.tasks import (
    configure_failed_task_handling_task,
    handle_failed_task as task_handle_failed,
    handle_task_failure_with_retry_policy,
)


# =============================================================================
# Fake Redis Fixture
# =============================================================================

class FakeRedis:
    def __init__(self):
        self.store = {}
        self.lists = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None, nx=False):
        if nx and key in self.store:
            return False
        self.store[key] = str(value)
        return True

    def rpush(self, key, *values):
        if key not in self.lists:
            self.lists[key] = []
        for val in values:
            self.lists[key].append(val)
        return len(self.lists[key])

    def llen(self, key):
        return len(self.lists.get(key, []))

    def lrange(self, key, start, end):
        items = self.lists.get(key, [])
        if end == -1:
            return items[start:]
        return items[start:end + 1]

    def pipeline(self):
        return FakePipeline(self)


class FakePipeline:
    def __init__(self, redis):
        self.redis = redis
        self.ops = []

    def delete(self, key):
        self.ops.append(("delete", key))

    def rpush(self, key, *values):
        self.ops.append(("rpush", key, values))

    def execute(self):
        for op in self.ops:
            if op[0] == "delete":
                if op[1] in self.redis.lists:
                    del self.redis.lists[op[1]]
                if op[1] in self.redis.store:
                    del self.redis.store[op[1]]
            elif op[0] == "rpush":
                self.redis.rpush(op[1], *op[2])
        self.ops.clear()


@pytest.fixture
def fake_redis():
    return FakeRedis()


# =============================================================================
# 1. Output Contract & Basic Configuration Tests
# =============================================================================

def test_failed_task_handling_contract():
    """Verify exact JSON contract format matches specification."""
    config = get_failed_task_handling_config()
    assert config == {
        "status": "FAILED_HANDLED",
        "failure_action": "DLQ",
        "requeue_supported": True,
    }


def test_failed_task_handling_configuration():
    """Verify configure_failed_task_handling activates DLQ and returns contract."""
    res = configure_failed_task_handling()
    assert res == {
        "status": "FAILED_HANDLED",
        "failure_action": "DLQ",
        "requeue_supported": True,
    }


def test_failed_task_handling_aliases_and_imports():
    """Verify all story aliases across celery_app, runtime, and tasks are identical."""
    expected = {
        "status": "FAILED_HANDLED",
        "failure_action": "DLQ",
        "requeue_supported": True,
    }

    assert ConfigureFailedTaskHandling() == expected
    assert Configure_failed_task_handling() == expected
    assert configure_failed_tasks() == expected
    assert ConfigureFailedTasks() == expected
    assert get_failed_tasks_config() == expected

    assert runtime_get_config() == expected
    assert runtime_configure() == expected
    assert RuntimeConfigureFailedTaskHandling() == expected
    assert RuntimeConfigure_failed_task_handling() == expected
    assert runtime_configure_failed_tasks() == expected
    assert RuntimeConfigureFailedTasks() == expected
    assert runtime_get_failed_tasks_config() == expected


# =============================================================================
# 2. Sensitive Payload Redaction Tests
# =============================================================================

def test_sanitize_payload_redacts_credentials():
    """Verify sanitize_payload scrubs passwords, tokens, API keys, and credit cards."""
    dirty_data = {
        "password": "SuperSecretPassword123!",
        "client_secret": "sec-abc-987",
        "api_key": "live_key_xyz12345",
        "auth_token": "eyJhbGciOiJIUzI1NiIsIn...",
        "credit_card": "4111 1111 1111 1111",
        "nested": {
            "token": "refresh-token-here",
            "safe_field": "dispatched",
            "prompt_tokens": 150,  # AI token metrics must NOT be redacted
            "total_tokens": 300,
        },
        "tags": ["urgent", "Bearer secret-token-xyz"],
    }

    sanitized = sanitize_payload(dirty_data)

    assert sanitized["password"] == "[REDACTED]"
    assert sanitized["client_secret"] == "[REDACTED]"
    assert sanitized["api_key"] == "[REDACTED]"
    assert sanitized["auth_token"] == "[REDACTED]"
    assert sanitized["credit_card"] == "[REDACTED]"
    assert sanitized["nested"]["token"] == "[REDACTED]"
    assert sanitized["nested"]["safe_field"] == "dispatched"
    assert sanitized["nested"]["prompt_tokens"] == 150
    assert sanitized["nested"]["total_tokens"] == 300
    assert sanitized["tags"][0] == "urgent"
    assert sanitized["tags"][1] == "Bearer [REDACTED]"


# =============================================================================
# 3. Metadata Capture & DLQ Routing Tests
# =============================================================================

def test_handle_failed_task_captures_metadata_and_stores_dlq(fake_redis):
    """Verify handle_failed_task captures metadata and enqueues to Redis DLQ."""
    result = handle_failed_task(
        task_name="app.tasks.send_invoice_notification",
        queue="billing",
        args=[101, "customer_inv"],
        kwargs={"notify_email": "test@example.com", "api_key": "secret_key_123"},
        payload={"invoice_id": "INV-2026-001", "amount": 250.0},
        error=ValueError("Invalid invoice format"),
        exception_category="validation_error",
        tenant_id="tenant-alpha",
        correlation_id="corr-inv-999",
        task_id="task-custom-123",
        retry_count=3,
        redis=fake_redis,
    )

    assert result["status"] == "FAILED_HANDLED"
    assert result["failure_action"] == "DLQ"
    assert result["requeue_supported"] is True
    assert result["task_name"] == "app.tasks.send_invoice_notification"
    assert result["queue"] == "billing"
    assert result["tenant_id"] == "tenant-alpha"
    assert result["correlation_id"] == "corr-inv-999"
    assert result["exception_category"] == "validation_error"
    assert result["task_id"] == "task-custom-123"

    # Verify item stored in Redis DLQ
    dlq = DeadLetterQueue(fake_redis)
    assert dlq.count() == 1
    items = dlq.list()
    assert len(items) == 1
    stored_item = items[0]

    assert stored_item["id"] == result["dlq_id"]
    assert stored_item["task_name"] == "app.tasks.send_invoice_notification"
    assert stored_item["queue"] == "billing"
    assert stored_item["correlation_id"] == "corr-inv-999"
    assert stored_item["exception_category"] == "validation_error"
    assert stored_item["error_type"] == "ValueError"

    # Ensure sensitive kwargs was sanitized in the DLQ entry
    stored_payload = stored_item["task"]["payload"]
    assert stored_payload["kwargs"]["api_key"] == "[REDACTED]"
    assert stored_payload["kwargs"]["notify_email"] == "test@example.com"


def test_handle_failed_task_requires_tenant_id():
    """Verify handle_failed_task enforces multi-tenant boundary."""
    with pytest.raises(ValueError, match="tenant_id is required"):
        handle_failed_task(
            task_name="test_task",
            tenant_id="",
        )


def test_handle_failed_task_persists_to_db_session(fake_redis):
    """Verify handle_failed_task integrates with PostgreSQL Session."""
    mock_db = MagicMock()
    result = handle_failed_task(
        task_name="app.tasks.dispatch_job",
        queue="high_priority",
        payload={"job_id": "job-101"},
        tenant_id="tenant-db-test",
        correlation_id="corr-db-456",
        error=RuntimeError("Worker segfault"),
        redis=fake_redis,
        db=mock_db,
    )

    assert result["status"] == "FAILED_HANDLED"
    assert result["failure_action"] == "DLQ"
    assert mock_db.add.called
    assert mock_db.flush.called

    saved_entity = mock_db.add.call_args[0][0]
    assert saved_entity.task_type == "app.tasks.dispatch_job"
    assert saved_entity.tenant_id == "tenant-db-test"
    assert saved_entity.context["correlation_id"] == "corr-db-456"
    assert saved_entity.context["queue"] == "high_priority"


# =============================================================================
# 4. Safe Requeue Support Tests
# =============================================================================

def test_requeue_support_from_dlq(fake_redis):
    """Verify tasks persisted to DLQ can be extracted for safe requeue."""
    result = handle_failed_task(
        task_name="app.tasks.generate_pdf_report",
        queue="report_generation",
        payload={"report_id": "rep-777", "secret_pass": "12345"},
        tenant_id="tenant-requeue-test",
        redis=fake_redis,
    )
    assert result["requeue_supported"] is True

    dlq = DeadLetterQueue(fake_redis)
    requeue_payload = dlq.requeue_payload(result["dlq_id"])
    assert requeue_payload is not None
    assert requeue_payload["tenant_id"] == "tenant-requeue-test"
    assert requeue_payload["payload"]["report_id"] == "rep-777"
    assert requeue_payload["payload"]["secret_pass"] == "[REDACTED]"


# =============================================================================
# 5. Celery Task & Failure Integration Tests
# =============================================================================

def test_configure_failed_task_handling_celery_task():
    """Verify Celery task returns canonical contract and preserves metadata."""
    res = configure_failed_task_handling_task(
        tenant_id="tenant-celery",
        correlation_id="corr-celery-123",
    )
    assert res == {
        "status": "FAILED_HANDLED",
        "failure_action": "DLQ",
        "requeue_supported": True,
    }


def test_handle_task_failure_with_retry_policy_includes_dlq_action(fake_redis):
    """Verify handle_task_failure_with_retry_policy attaches failure_action and requeue_supported."""
    res = handle_task_failure_with_retry_policy(
        error=ValueError("Fatal schema validation error"),
        task_payload={"task_type": "report_gen"},
        tenant_id="tenant-exhaust",
        retry_count=3,
        correlation_id="corr-exhaust-1",
        redis=fake_redis,
    )
    assert res["status"] == "MOVED_TO_DLQ"
    assert res["failure_action"] == "DLQ"
    assert res["requeue_supported"] is True


# =============================================================================
# 6. Admin REST Endpoints Tests
# =============================================================================

def test_admin_queue_failed_handling_endpoints():
    """Verify admin queue endpoints return expected failed handling contract."""
    from app.routes.admin_queue import (
        get_failed_handling_status,
        configure_failed_handling_endpoint,
        get_dlq_config_alias,
        configure_dlq_endpoint_alias,
        get_failed_tasks_status_alias,
        configure_failed_tasks_endpoint_alias,
    )
    from app.routes.admin_dlq import (
        get_dlq_config,
        configure_dlq_endpoint,
    )

    expected = {
        "status": "FAILED_HANDLED",
        "failure_action": "DLQ",
        "requeue_supported": True,
    }

    assert get_failed_handling_status() == expected
    assert configure_failed_handling_endpoint() == expected
    assert get_dlq_config_alias() == expected
    assert configure_dlq_endpoint_alias() == expected
    assert get_failed_tasks_status_alias() == expected
    assert configure_failed_tasks_endpoint_alias() == expected

    assert get_dlq_config() == expected
    assert configure_dlq_endpoint() == expected

