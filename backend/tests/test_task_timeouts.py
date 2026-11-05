"""
test_task_timeouts.py

Comprehensive test suite for Story: Configure task timeouts (Celery Queue Management).
Validates:
- Canonical JSON contract:
    {
        "status": "CONFIGURED",
        "timeouts": {
            "soft": 300,
            "hard": 360
        }
    }
- Queue-specific timeouts (high_priority, notifications, gps, billing, ai, reports).
- Celery worker/broker time limits (task_time_limit, task_soft_time_limit, task_annotations).
- Handling timeout exceptions without leaving partial state (db.rollback).
- Logging timeout, task, and correlation information.
- Re-exports across celery_app, tasks, and worker.
- FastAPI administrative endpoints and aliases.
"""

from unittest.mock import MagicMock, patch
import pytest

from app.celery_app import (
    celery_app,
    DEFAULT_TASK_TIMEOUTS,
    QUEUE_TASK_TIMEOUTS,
    get_task_timeouts_config,
    get_queue_timeout,
    configure_task_timeouts,
    ConfigureTaskTimeouts,
    Configure_task_timeouts,
    configure_timeouts,
    ConfigureTimeouts,
    get_task_timeouts,
    get_timeouts_config,
)
from app.tasks import (
    configure_task_timeouts_task,
    handle_task_timeout,
    DEFAULT_TASK_TIMEOUTS as TASKS_DEFAULT_TIMEOUTS,
    QUEUE_TASK_TIMEOUTS as TASKS_QUEUE_TIMEOUTS,
    get_task_timeouts_config as tasks_get_config,
    get_queue_timeout as tasks_get_queue_timeout,
    configure_task_timeouts as tasks_configure_timeouts,
)
from app.worker import (
    DEFAULT_TASK_TIMEOUTS as WORKER_DEFAULT_TIMEOUTS,
    QUEUE_TASK_TIMEOUTS as WORKER_QUEUE_TIMEOUTS,
    get_task_timeouts_config as worker_get_config,
    get_queue_timeout as worker_get_queue_timeout,
    configure_task_timeouts as worker_configure_timeouts,
    ConfigureTaskTimeouts as WorkerConfigureTaskTimeouts,
    Configure_task_timeouts as WorkerConfigure_task_timeouts,
)


# =============================================================================
# 1. Output Contract & Basic Configuration Tests
# =============================================================================

def test_task_timeouts_contract():
    """Verify exact JSON contract matches specification."""
    config = get_task_timeouts_config()
    assert config == {
        "status": "CONFIGURED",
        "timeouts": {
            "soft": 300,
            "hard": 360,
        },
    }


def test_configure_task_timeouts_activation():
    """Verify configure_task_timeouts sets Celery configurations and returns contract."""
    res = configure_task_timeouts()
    assert res == {
        "status": "CONFIGURED",
        "timeouts": {
            "soft": 300,
            "hard": 360,
        },
    }

    assert celery_app.conf.task_soft_time_limit == 300
    assert celery_app.conf.task_time_limit == 360
    assert celery_app.conf.task_annotations["*"]["soft_time_limit"] == 300
    assert celery_app.conf.task_annotations["*"]["time_limit"] == 360


def test_task_timeouts_aliases_and_module_exports():
    """Verify all story aliases across celery_app, tasks, and worker are consistent."""
    expected = {
        "status": "CONFIGURED",
        "timeouts": {
            "soft": 300,
            "hard": 360,
        },
    }

    assert ConfigureTaskTimeouts() == expected
    assert Configure_task_timeouts() == expected
    assert configure_timeouts() == expected
    assert ConfigureTimeouts() == expected
    assert get_task_timeouts() == expected
    assert get_timeouts_config() == expected

    # Tasks re-exports
    assert tasks_get_config() == expected
    assert tasks_configure_timeouts() == expected
    assert TASKS_DEFAULT_TIMEOUTS == {"soft": 300, "hard": 360}

    # Worker re-exports
    assert worker_get_config() == expected
    assert worker_configure_timeouts() == expected
    assert WorkerConfigureTaskTimeouts() == expected
    assert WorkerConfigure_task_timeouts() == expected
    assert WORKER_DEFAULT_TIMEOUTS == {"soft": 300, "hard": 360}


# =============================================================================
# 2. Queue-Specific Limits Tests
# =============================================================================

def test_queue_specific_timeouts():
    """Verify queue-specific soft and hard timeout limits match workload characteristics."""
    # Urgent tasks (emergency dispatch / SLA)
    high_priority = get_queue_timeout("high_priority")
    assert high_priority == {"soft": 60, "hard": 120}

    # Notifications (email / sms / push)
    notifications = get_queue_timeout("notifications")
    assert notifications == {"soft": 60, "hard": 90}

    # GPS processing (high-frequency telemetry)
    gps = get_queue_timeout("gps_processing")
    assert gps == {"soft": 30, "hard": 60}

    # Billing & invoices (medium duration financial transactions)
    billing = get_queue_timeout("billing")
    assert billing == {"soft": 120, "hard": 180}

    # AI processing (LLM inference & LangGraph agents)
    ai = get_queue_timeout("ai_processing")
    assert ai == {"soft": 300, "hard": 360}

    # Report generation (heavy PDF/CSV exports)
    reports = get_queue_timeout("report_generation")
    assert reports == {"soft": 600, "hard": 720}

    # Unknown queue falls back to safe default
    unknown = get_queue_timeout("unknown_queue")
    assert unknown == {"soft": 300, "hard": 360}


def test_celery_task_annotations_queue_mapping():
    """Verify Celery task annotations map queue-specific time limits."""
    configure_task_timeouts()
    annotations = celery_app.conf.task_annotations

    assert annotations["app.tasks.*notification*"]["soft_time_limit"] == 60
    assert annotations["app.tasks.*notification*"]["time_limit"] == 90

    assert annotations["app.tasks.*gps*"]["soft_time_limit"] == 30
    assert annotations["app.tasks.*gps*"]["time_limit"] == 60

    assert annotations["app.tasks.*billing*"]["soft_time_limit"] == 120
    assert annotations["app.tasks.*billing*"]["time_limit"] == 180

    assert annotations["app.tasks.*ai*"]["soft_time_limit"] == 300
    assert annotations["app.tasks.*ai*"]["time_limit"] == 360

    assert annotations["app.tasks.*priority*"]["soft_time_limit"] == 60
    assert annotations["app.tasks.*priority*"]["time_limit"] == 120

    assert annotations["app.tasks.*report*"]["soft_time_limit"] == 600
    assert annotations["app.tasks.*report*"]["time_limit"] == 720


# =============================================================================
# 3. Timeout Handling & Partial State Prevention Tests
# =============================================================================

def test_handle_task_timeout_rolls_back_database_session():
    """Verify handle_task_timeout rolls back db transaction to prevent partial state."""
    mock_db = MagicMock()
    mock_redis = MagicMock()

    result = handle_task_timeout(
        task_name="app.tasks.generate_pdf_report",
        queue="report_generation",
        tenant_id="tenant-timeout-1",
        correlation_id="corr-timeout-123",
        elapsed_seconds=605.2,
        db=mock_db,
        redis=mock_redis,
        error=TimeoutError("Report rendering exceeded soft limit"),
        task_payload={"report_id": "rep-999"},
    )

    assert result["status"] == "TIMED_OUT"
    assert result["partial_state_prevented"] is True
    assert result["tenant_id"] == "tenant-timeout-1"
    assert result["correlation_id"] == "corr-timeout-123"

    # Verify db transaction rollback was called
    assert mock_db.rollback.called


def test_handle_task_timeout_routes_to_dlq():
    """Verify timed-out task routes cleanly to DLQ without duplicate side effects."""
    mock_db = MagicMock()
    mock_redis = MagicMock()

    with patch("app.runtime.dlq.handle_failed_task") as mock_handle_failed:
        mock_handle_failed.return_value = {
            "status": "FAILED_HANDLED",
            "failure_action": "DLQ",
            "requeue_supported": True,
            "dlq_id": "dlq-timeout-test",
        }

        result = handle_task_timeout(
            task_name="app.tasks.process_billing_invoice",
            queue="billing",
            tenant_id="tenant-dlq-to",
            correlation_id="corr-dlq-to-1",
            elapsed_seconds=185.0,
            db=mock_db,
            redis=mock_redis,
        )

        assert mock_handle_failed.called
        call_kwargs = mock_handle_failed.call_args[1]
        assert call_kwargs["task_name"] == "app.tasks.process_billing_invoice"
        assert call_kwargs["queue"] == "billing"
        assert call_kwargs["tenant_id"] == "tenant-dlq-to"
        assert call_kwargs["correlation_id"] == "corr-dlq-to-1"
        assert call_kwargs["reason"] == "task_timeout_exceeded"
        assert result["dlq_result"]["dlq_id"] == "dlq-timeout-test"


# =============================================================================
# 4. Celery Task Execution Tests
# =============================================================================

def test_configure_task_timeouts_celery_task():
    """Verify Celery task executes and returns canonical contract."""
    res = configure_task_timeouts_task(
        tenant_id="tenant-timeout-celery",
        correlation_id="corr-timeout-celery",
    )
    assert res == {
        "status": "CONFIGURED",
        "timeouts": {
            "soft": 300,
            "hard": 360,
        },
    }


# =============================================================================
# 5. Admin Queue REST Endpoints Tests
# =============================================================================

def test_admin_queue_timeouts_endpoints():
    """Verify FastAPI admin queue endpoints return expected task timeouts contract."""
    from app.routes.admin_queue import (
        get_task_timeouts_status,
        configure_task_timeouts_endpoint,
        get_task_timeouts_status_alias,
        configure_task_timeouts_endpoint_alias,
    )

    expected = {
        "status": "CONFIGURED",
        "timeouts": {
            "soft": 300,
            "hard": 360,
        },
    }

    assert get_task_timeouts_status() == expected
    assert configure_task_timeouts_endpoint() == expected
    assert get_task_timeouts_status_alias() == expected
    assert configure_task_timeouts_endpoint_alias() == expected

