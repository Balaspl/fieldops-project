"""
test_task_result_tracking.py

Comprehensive test suite for Story: Add task result tracking (Celery Queue Management).
Validates:
- Canonical JSON contract:
    {
        "status": "TRACKED",
        "task_id": "example-task-id",
        "state": "SUCCESS",
        "queue": "notifications"
    }
- Lifecycle metadata tracking: task_id, queue, state (QUEUED, RUNNING, SUCCESS, FAILURE, RETRY), correlation_id.
- Prevention of sensitive payload leakage (sanitizing passwords, tokens, API keys in result_data).
- Operational state inspection via Redis and Celery AsyncResult fallback.
- State consistency across retries and failures.
- Celery task execution and module re-exports.
- FastAPI administrative endpoints and aliases.
"""

from unittest.mock import MagicMock
import pytest

from app.celery_app import (
    celery_app,
    DEFAULT_TASK_RESULT_TRACKING,
    get_task_result_tracking_config,
    track_task_result,
    get_task_result,
    add_task_result_tracking,
    AddTaskResultTracking,
    Add_task_result_tracking,
    configure_task_result_tracking,
    ConfigureTaskResultTracking,
    get_task_result_tracking,
    TrackTaskResult,
)
from app.tasks import (
    add_task_result_tracking_task,
    DEFAULT_TASK_RESULT_TRACKING as TASKS_DEFAULT_TRACKING,
    get_task_result_tracking_config as tasks_get_config,
    track_task_result as tasks_track_result,
    get_task_result as tasks_get_result,
    add_task_result_tracking as tasks_add_tracking,
    AddTaskResultTracking as TasksAddTaskResultTracking,
    Add_task_result_tracking as TasksAdd_task_result_tracking,
    configure_task_result_tracking as tasks_configure_tracking,
    ConfigureTaskResultTracking as TasksConfigureTaskResultTracking,
    get_task_result_tracking as tasks_get_tracking_config,
    TrackTaskResult as TasksTrackTaskResult,
)


# =============================================================================
# Fake Redis Fixture
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


@pytest.fixture
def fake_redis():
    return FakeRedis()


# =============================================================================
# 1. Output Contract & Basic Configuration Tests
# =============================================================================

def test_task_result_tracking_contract():
    """Verify exact JSON contract matches specification."""
    config = get_task_result_tracking_config()
    assert config == {
        "status": "TRACKED",
        "task_id": "example-task-id",
        "state": "SUCCESS",
        "queue": "notifications",
    }


def test_add_task_result_tracking_activation():
    """Verify add_task_result_tracking enables Celery result tracking and returns contract."""
    res = add_task_result_tracking()
    assert res == {
        "status": "TRACKED",
        "task_id": "example-task-id",
        "state": "SUCCESS",
        "queue": "notifications",
    }
    assert celery_app.conf.task_track_started is True
    assert celery_app.conf.result_extended is True


def test_task_result_tracking_aliases_and_module_exports():
    """Verify all story aliases across celery_app and tasks are consistent."""
    expected = {
        "status": "TRACKED",
        "task_id": "example-task-id",
        "state": "SUCCESS",
        "queue": "notifications",
    }

    assert AddTaskResultTracking() == expected
    assert Add_task_result_tracking() == expected
    assert configure_task_result_tracking() == expected
    assert ConfigureTaskResultTracking() == expected
    assert get_task_result_tracking() == expected

    # Tasks re-exports
    assert tasks_get_config() == expected
    assert tasks_add_tracking() == expected
    assert TasksAddTaskResultTracking() == expected
    assert TasksAdd_task_result_tracking() == expected
    assert tasks_configure_tracking() == expected
    assert TasksConfigureTaskResultTracking() == expected
    assert tasks_get_tracking_config() == expected
    assert TASKS_DEFAULT_TRACKING == DEFAULT_TASK_RESULT_TRACKING


# =============================================================================
# 2. Lifecycle States & Metadata Tracking Tests
# =============================================================================

def test_track_task_result_lifecycle_states(fake_redis):
    """Verify tracking various lifecycle states (QUEUED, RUNNING, SUCCESS, FAILURE, RETRY)."""
    states = ["QUEUED", "RUNNING", "RETRY", "FAILURE", "SUCCESS"]

    for state in states:
        res = track_task_result(
            task_id="task-lifecycle-101",
            state=state,
            queue="billing",
            tenant_id="tenant-tracking-1",
            correlation_id="corr-lifecycle-101",
            redis=fake_redis,
        )

        assert res == {
            "status": "TRACKED",
            "task_id": "task-lifecycle-101",
            "state": state,
            "queue": "billing",
        }

        stored = get_task_result("task-lifecycle-101", redis=fake_redis)
        assert stored is not None
        assert stored["state"] == state
        assert stored["queue"] == "billing"
        assert stored["tenant_id"] == "tenant-tracking-1"
        assert stored["correlation_id"] == "corr-lifecycle-101"


# =============================================================================
# 3. Sensitive Payload Redaction Tests
# =============================================================================

def test_track_task_result_sanitizes_credentials(fake_redis):
    """Verify track_task_result redacts passwords, tokens, API keys in result_data."""
    res = track_task_result(
        task_id="task-sensitive-202",
        state="SUCCESS",
        queue="notifications",
        result_data={
            "recipient": "customer@example.com",
            "api_key": "secret-provider-key-999",
            "nested": {
                "password": "Password123!",
                "auth_token": "token-xyz",
                "safe_status": "DELIVERED",
            },
        },
        redis=fake_redis,
    )

    assert res["status"] == "TRACKED"
    stored = get_task_result("task-sensitive-202", redis=fake_redis)
    assert stored is not None

    sanitized_result = stored["result"]
    assert sanitized_result["recipient"] == "customer@example.com"
    assert sanitized_result["api_key"] == "[REDACTED]"
    assert sanitized_result["nested"]["password"] == "[REDACTED]"
    assert sanitized_result["nested"]["auth_token"] == "[REDACTED]"
    assert sanitized_result["nested"]["safe_status"] == "DELIVERED"


# =============================================================================
# 4. Consistency Across Retries & Errors
# =============================================================================

def test_track_task_result_preserves_error_details_on_failure(fake_redis):
    """Verify error messages are recorded when task fails or retries."""
    track_task_result(
        task_id="task-err-303",
        state="FAILURE",
        queue="ai_processing",
        error=RuntimeError("GPU cluster connection refused"),
        redis=fake_redis,
    )

    stored = get_task_result("task-err-303", redis=fake_redis)
    assert stored is not None
    assert stored["state"] == "FAILURE"
    assert "GPU cluster connection refused" in stored["error"]


# =============================================================================
# 5. Celery Task Execution Tests
# =============================================================================

def test_add_task_result_tracking_celery_task():
    """Verify Celery task executes and returns canonical contract."""
    res = add_task_result_tracking_task(
        task_id="task-celery-tracked-1",
        state="SUCCESS",
        queue="notifications",
        tenant_id="tenant-celery-1",
        correlation_id="corr-celery-1",
    )
    assert res == {
        "status": "TRACKED",
        "task_id": "task-celery-tracked-1",
        "state": "SUCCESS",
        "queue": "notifications",
    }


# =============================================================================
# 6. Admin Queue REST Endpoints Tests
# =============================================================================

def test_admin_queue_tracking_endpoints():
    """Verify FastAPI admin queue endpoints return expected task tracking contract."""
    from app.routes.admin_queue import (
        get_task_result_tracking_config_endpoint,
        configure_task_result_tracking_endpoint,
        get_task_result_endpoint,
        get_task_result_alias,
        track_task_endpoint,
    )

    expected = {
        "status": "TRACKED",
        "task_id": "example-task-id",
        "state": "SUCCESS",
        "queue": "notifications",
    }

    assert get_task_result_tracking_config_endpoint() == expected
    assert configure_task_result_tracking_endpoint() == expected
    assert get_task_result_endpoint("example-task-id") == {
        "status": "TRACKED",
        "task_id": "example-task-id",
        "state": "PENDING",
        "queue": "default",
    }
    assert get_task_result_alias("example-task-id") == {
        "status": "TRACKED",
        "task_id": "example-task-id",
        "state": "PENDING",
        "queue": "default",
    }
    assert track_task_endpoint({
        "task_id": "example-task-id",
        "state": "SUCCESS",
        "queue": "notifications",
    }) == expected

