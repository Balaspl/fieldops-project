"""
test_task_retry_rules.py

Comprehensive test suite for Story: Configure task retry rules (Celery Queue Management).
Validates bounded, task-appropriate retry policies for transient worker, broker, provider, and network failures:
- Contract validation:
    {
        "status": "CONFIGURED",
        "retry_policy": {
            "max_retries": 3,
            "backoff": "exponential",
            "jitter": true
        }
    }
- Failure classification: retryable (transient, 429, 5xx, timeouts) vs non-retryable (validation, auth, 4xx).
- Bounded retry counts and exponential backoff with jitter.
- Avoid retrying validation, authorization, or permanent business-rule failures.
- Preserve idempotency and correlation information on retries.
- Moving exhausted or permanent failures to Dead Letter Queue (DLQ).
"""

from unittest.mock import MagicMock, patch
import pytest

from app.celery_app import (
    celery_app,
    TASK_RETRY_POLICY,
    get_task_retry_rules_config,
    configure_task_retry_rules,
    ConfigureTaskRetryRules,
    Configure_task_retry_rules,
    configure_retry_rules,
    ConfigureRetryRules,
    get_retry_rules_config,
)
from app.runtime.retry import (
    RetryDecision,
    RetryManager,
    get_task_retry_rules_config as runtime_get_config,
    configure_task_retry_rules as runtime_configure_rules,
    ConfigureTaskRetryRules as RuntimeConfigureTaskRetryRules,
    Configure_task_retry_rules as RuntimeConfigure_task_retry_rules,
    configure_retry_rules as runtime_configure_retry_rules,
    ConfigureRetryRules as RuntimeConfigureRetryRules,
    get_retry_rules_config as runtime_get_retry_rules_config,
)
from app.services.task_queue import (
    get_task_retry_rules_config as tq_get_config,
    configure_task_retry_rules as tq_configure_rules,
    ConfigureTaskRetryRules as TqConfigureTaskRetryRules,
)
from app.tasks import (
    configure_task_retry_rules_task,
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

    def rpush(self, key, value):
        if key not in self.lists:
            self.lists[key] = []
        self.lists[key].append(value)
        return len(self.lists[key])

    def delete(self, *keys):
        count = 0
        for k in keys:
            if k in self.store:
                del self.store[k]
                count += 1
            if k in self.lists:
                del self.lists[k]
                count += 1
        return count


@pytest.fixture
def fake_redis():
    return FakeRedis()


# =============================================================================
# 1. Output Contract & Basic Configuration Tests
# =============================================================================

def test_task_retry_rules_expected_contract():
    """Verify configure_task_retry_rules returns the exact expected output contract."""
    result = configure_task_retry_rules()

    assert result == {
        "status": "CONFIGURED",
        "retry_policy": {
            "max_retries": 3,
            "backoff": "exponential",
            "jitter": True,
        },
    }
    assert result["status"] == "CONFIGURED"
    assert result["retry_policy"]["max_retries"] == 3
    assert result["retry_policy"]["backoff"] == "exponential"
    assert result["retry_policy"]["jitter"] is True


def test_get_task_retry_rules_config():
    """Verify get_task_retry_rules_config returns the canonical contract."""
    config = get_task_retry_rules_config()
    assert config == {
        "status": "CONFIGURED",
        "retry_policy": {
            "max_retries": 3,
            "backoff": "exponential",
            "jitter": True,
        },
    }


def test_retry_rules_aliases_and_imports():
    """Verify story naming aliases and service re-exports point to the same callable."""
    assert ConfigureTaskRetryRules is configure_task_retry_rules
    assert Configure_task_retry_rules is configure_task_retry_rules
    assert configure_retry_rules is configure_task_retry_rules
    assert ConfigureRetryRules is configure_task_retry_rules
    assert get_retry_rules_config is get_task_retry_rules_config

    # Re-exports from app.runtime.retry
    assert runtime_get_config() == get_task_retry_rules_config()
    assert runtime_configure_rules is configure_task_retry_rules
    assert RuntimeConfigureTaskRetryRules is configure_task_retry_rules
    assert RuntimeConfigure_task_retry_rules is configure_task_retry_rules
    assert runtime_configure_retry_rules is configure_task_retry_rules
    assert RuntimeConfigureRetryRules is configure_task_retry_rules
    assert runtime_get_retry_rules_config is get_task_retry_rules_config

    # Re-exports from app.services.task_queue
    assert tq_get_config() == get_task_retry_rules_config()
    assert tq_configure_rules is configure_task_retry_rules
    assert TqConfigureTaskRetryRules is configure_task_retry_rules

    # RetryManager contract helper
    assert RetryManager.get_retry_policy_contract() == get_task_retry_rules_config()


# =============================================================================
# 2. Failure Classification Tests (Retryable vs Non-Retryable)
# =============================================================================

def test_failure_classification_transient_vs_permanent():
    """Verify classification of transient failures vs non-retryable errors."""
    # Transient / Retryable
    assert RetryManager.is_retryable(TimeoutError("Gateway connection timed out")) is True
    assert RetryManager.is_retryable(ConnectionError("Broker disconnect")) is True

    http_429 = Exception("Rate limit exceeded")
    http_429.status_code = 429
    assert RetryManager.is_retryable(http_429) is True

    http_503 = Exception("Service Unavailable")
    http_503.status_code = 503
    assert RetryManager.is_retryable(http_503) is True

    network_err = RuntimeError("Temporary broker network glitch")
    assert RetryManager.is_retryable(network_err) is True

    # Non-retryable / Permanent
    assert RetryManager.is_retryable(ValueError("Invalid payload schema")) is False
    assert RetryManager.is_retryable(KeyError("Missing tenant_id")) is False
    assert RetryManager.is_retryable(TypeError("Unexpected type")) is False
    assert RetryManager.is_retryable(PermissionError("Unauthorized tenant access")) is False

    http_400 = Exception("Bad Request")
    http_400.status_code = 400
    assert RetryManager.is_retryable(http_400) is False

    http_403 = Exception("Forbidden")
    http_403.status_code = 403
    assert RetryManager.is_retryable(http_403) is False

    guardrail_err = Exception("Guardrail violation: profanity detected")
    assert RetryManager.is_retryable(guardrail_err) is False


# =============================================================================
# 3. Bounded Backoff & Jitter Tests
# =============================================================================

def test_bounded_backoff_and_jitter():
    """Verify exponential backoff calculation and bounded jitter inclusion."""
    assert RetryManager.calculate_backoff(1) == 1.0
    assert RetryManager.calculate_backoff(2) == 2.0
    assert RetryManager.calculate_backoff(3) == 4.0

    # With jitter enabled
    delay1 = RetryManager.calculate_backoff_with_jitter(1, jitter=True)
    assert 1.0 < delay1 <= 1.3  # base 1.0 + jitter between 0.05 and 0.25

    delay2 = RetryManager.calculate_backoff_with_jitter(2, jitter=True)
    assert 2.0 < delay2 <= 2.3  # base 2.0 + jitter between 0.05 and 0.25

    delay3 = RetryManager.calculate_backoff_with_jitter(3, jitter=True)
    assert 4.0 < delay3 <= 4.3  # base 4.0 + jitter between 0.05 and 0.25

    # Out of range retry_number raises ValueError
    with pytest.raises(ValueError):
        RetryManager.calculate_backoff(0)

    with pytest.raises(ValueError):
        RetryManager.calculate_backoff(4)


# =============================================================================
# 4. Evaluation and DLQ Handoff Tests
# =============================================================================

def test_avoid_retrying_validation_authorization_failures():
    """Verify validation and authorization failures are routed directly to DLQ without retries."""
    eval_val = RetryManager.evaluate(ValueError("Malformed request body"), retry_count=0)
    assert eval_val.decision == RetryDecision.DLQ
    assert eval_val.reason == "non_retryable_error"

    eval_perm = RetryManager.evaluate(PermissionError("Access denied"), retry_count=0)
    assert eval_perm.decision == RetryDecision.DLQ
    assert eval_perm.reason == "non_retryable_error"


def test_retry_count_exhaustion_moves_to_dlq():
    """Verify retry exhaustion triggers DLQ decision after 3 attempts."""
    transient_error = TimeoutError("Connection timed out")

    # Retries 0, 1, 2 schedule retries 1, 2, 3
    eval_0 = RetryManager.evaluate(transient_error, retry_count=0)
    assert eval_0.decision == RetryDecision.RETRY
    assert eval_0.retry_number == 1
    assert eval_0.delay_seconds == 1.0

    eval_1 = RetryManager.evaluate(transient_error, retry_count=1)
    assert eval_1.decision == RetryDecision.RETRY
    assert eval_1.retry_number == 2
    assert eval_1.delay_seconds == 2.0

    eval_2 = RetryManager.evaluate(transient_error, retry_count=2)
    assert eval_2.decision == RetryDecision.RETRY
    assert eval_2.retry_number == 3
    assert eval_2.delay_seconds == 4.0

    # Retry count 3 means 3 retries have already happened -> DLQ
    eval_3 = RetryManager.evaluate(transient_error, retry_count=3)
    assert eval_3.decision == RetryDecision.DLQ
    assert eval_3.reason == "maximum_retries_exceeded"


# =============================================================================
# 5. End-to-End Task Failure Handling & Metadata Preservation
# =============================================================================

def test_handle_task_failure_with_retry_policy_retries_transient_error():
    """Verify handle_task_failure_with_retry_policy schedules bounded retry for transient errors."""
    mock_celery_task = MagicMock()
    mock_celery_task.retry.side_effect = RuntimeError("RetryRaised")

    with pytest.raises(RuntimeError, match="RetryRaised"):
        handle_task_failure_with_retry_policy(
            celery_task=mock_celery_task,
            error=TimeoutError("Transient provider outage"),
            task_payload={"task_type": "invoice_generation", "job_id": 101},
            tenant_id="tenant-123",
            retry_count=1,
            correlation_id="corr-abc-1",
        )

    assert mock_celery_task.retry.called
    kwargs = mock_celery_task.retry.call_args[1]
    assert 2.0 < kwargs["countdown"] <= 2.3  # Exponential delay + jitter


def test_handle_task_failure_with_retry_policy_dlq_on_exhaustion(fake_redis):
    """Verify handle_task_failure_with_retry_policy sends exhausted failure to DLQ."""
    result = handle_task_failure_with_retry_policy(
        celery_task=None,
        error=TimeoutError("Connection timed out permanently"),
        task_payload={"task_type": "report_generation", "report_id": "r-1"},
        tenant_id="tenant-dlq-test",
        retry_count=3,  # Max retries exhausted
        correlation_id="corr-dlq-exhaust",
        redis=fake_redis,
    )

    assert result["status"] == "MOVED_TO_DLQ"
    assert result["reason"] == "maximum_retries_exceeded"
    assert result["retry_count"] == 3
    assert result["tenant_id"] == "tenant-dlq-test"
    assert result["correlation_id"] == "corr-dlq-exhaust"


def test_configure_task_retry_rules_task_preserves_metadata():
    """Verify configure_task_retry_rules_task returns expected contract."""
    res = configure_task_retry_rules_task(
        tenant_id="tenant-retry-1",
        correlation_id="corr-retry-test",
    )
    assert res == {
        "status": "CONFIGURED",
        "retry_policy": {
            "max_retries": 3,
            "backoff": "exponential",
            "jitter": True,
        },
    }


# =============================================================================
# 6. Admin Queue REST Endpoints Tests
# =============================================================================

def test_admin_queue_retry_rules_endpoints():
    """Verify FastAPI admin queue endpoints return expected retry rules contract."""
    from app.routes.admin_queue import (
        get_retry_rules_status,
        configure_retry_rules_endpoint,
        get_retry_policy_status_alias,
        configure_retry_policy_endpoint_alias,
    )

    expected = {
        "status": "CONFIGURED",
        "retry_policy": {
            "max_retries": 3,
            "backoff": "exponential",
            "jitter": True,
        },
    }

    assert get_retry_rules_status() == expected
    assert configure_retry_rules_endpoint() == expected
    assert get_retry_policy_status_alias() == expected
    assert configure_retry_policy_endpoint_alias() == expected

