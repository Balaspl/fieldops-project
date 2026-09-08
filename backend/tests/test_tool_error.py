"""
Comprehensive pytest suite for the tool error-handling implementation.

Expected production module:
    app.tools.error_handler

If your implementation lives elsewhere, change MODULE_IMPORT below.
"""

import builtins
import json
import urllib.request

import pytest

from app.tools.errors import (
    CircuitBreaker,
    ErrorRateTracker,
    ErrorResult,
    PermanentError,
    StructuredToolError,
    TimeoutError,
    ToolError,
    ToolErrorHandler,
    TransientError,
    ValidationError,
)


# ============================================================================
# Helpers / fakes
# ============================================================================


class FakeClock:
    def __init__(self, value=0.0):
        self.value = float(value)

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += float(seconds)


class FakeRedis:
    """Small Redis fake covering the commands used by this implementation."""

    def __init__(self):
        self.values = {}
        self.expirations = {}
        self.zsets = {}

    def get(self, key):
        value = self.values.get(key)
        return value

    def set(self, key, value, ex=None, nx=False):
        if nx and key in self.values:
            return False
        self.values[key] = value
        if ex is not None:
            self.expirations[key] = ex
        return True

    def incr(self, key):
        current = self.values.get(key, 0)
        if isinstance(current, bytes):
            current = current.decode()
        current = int(current) + 1
        self.values[key] = current
        return current

    def expire(self, key, seconds):
        self.expirations[key] = seconds
        return True

    def delete(self, *keys):
        for key in keys:
            self.values.pop(key, None)
            self.expirations.pop(key, None)
            self.zsets.pop(key, None)
        return len(keys)

    def zadd(self, key, mapping):
        zset = self.zsets.setdefault(key, {})
        zset.update(mapping)
        return len(mapping)

    def zremrangebyscore(self, key, minimum, maximum):
        zset = self.zsets.get(key, {})
        max_value = float(maximum)
        to_delete = [
            member
            for member, score in zset.items()
            if score <= max_value
        ]
        for member in to_delete:
            del zset[member]
        return len(to_delete)

    def zcard(self, key):
        return len(self.zsets.get(key, {}))


class BrokenRedis:
    """Redis fake that raises so fallback-to-memory paths can be tested."""

    def __getattr__(self, name):
        def broken(*args, **kwargs):
            raise RuntimeError(f"Redis operation failed: {name}")

        return broken


class FakeHTTPResponse:
    def __init__(self):
        self.entered = False
        self.exited = False

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, exc_type, exc, tb):
        self.exited = True
        return False


# ============================================================================
# ToolError hierarchy
# ============================================================================


def test_tool_error_defaults_and_to_dict():
    error = ToolError(
        "boom",
        tool_id="email.send",
        parameters={"to": "x@example.com"},
    )

    assert str(error) == "boom"
    assert error.message == "boom"
    assert error.code == "TOOL_ERROR"
    assert error.retryable is False
    assert error.tool_id == "email.send"
    assert error.parameters == {"to": "x@example.com"}

    assert error.to_dict() == {
        "code": "TOOL_ERROR",
        "message": "boom",
        "tool_id": "email.send",
        "parameters": {"to": "x@example.com"},
        "retryable": False,
    }


def test_tool_error_copies_parameters():
    original = {"x": 1}
    error = ToolError("boom", parameters=original)

    original["x"] = 2

    assert error.parameters == {"x": 1}


@pytest.mark.parametrize(
    ("error_cls", "code", "retryable"),
    [
        (TransientError, "TRANSIENT_ERROR", True),
        (PermanentError, "PERMANENT_ERROR", False),
        (ValidationError, "VALIDATION_ERROR", False),
        (TimeoutError, "TIMEOUT", True),
    ],
)
def test_error_subclasses(error_cls, code, retryable):
    error = error_cls("failure")

    assert isinstance(error, ToolError)
    assert error.code == code
    assert error.retryable is retryable


def test_custom_error_code_overrides_class_code():
    error = ToolError("bad", code="CUSTOM")

    assert error.code == "CUSTOM"


# ============================================================================
# StructuredToolError / ErrorResult
# ============================================================================


def test_structured_tool_error_to_dict():
    error = StructuredToolError(
        code="TIMEOUT",
        message="timed out",
        tool_id="tool-1",
        parameters={"x": 1},
        retry_count=3,
        fallback_used=True,
    )

    assert error.to_dict() == {
        "code": "TIMEOUT",
        "message": "timed out",
        "tool_id": "tool-1",
        "parameters": {"x": 1},
        "retry_count": 3,
        "fallback_used": True,
    }


def test_error_result_to_dict_with_error():
    structured = StructuredToolError(
        code="VALIDATION_ERROR",
        message="invalid",
        tool_id="tool-1",
        parameters={},
    )
    result = ErrorResult(
        success=False,
        error=structured,
        fallback_used=False,
    )

    assert result.to_dict() == {
        "success": False,
        "result": None,
        "error": structured.to_dict(),
        "fallback_used": False,
        "fallback_tool_id": None,
    }


def test_error_result_to_dict_without_error():
    result = ErrorResult(
        success=True,
        result="fallback result",
        fallback_used=True,
        fallback_tool_id="backup-tool",
    )

    assert result.to_dict() == {
        "success": True,
        "result": "fallback result",
        "error": None,
        "fallback_used": True,
        "fallback_tool_id": "backup-tool",
    }


# ============================================================================
# CircuitBreaker - memory
# ============================================================================


def test_circuit_starts_closed():
    breaker = CircuitBreaker()

    assert breaker.is_open("tool-a") is False
    assert breaker.failure_count("tool-a") == 0


def test_circuit_opens_at_threshold():
    breaker = CircuitBreaker(failure_threshold=3)

    assert breaker.record_failure("tool-a") is False
    assert breaker.record_failure("tool-a") is False
    assert breaker.record_failure("tool-a") is True

    assert breaker.is_open("tool-a") is True
    assert breaker.failure_count("tool-a") == 3


def test_circuit_stays_open_after_additional_failure():
    breaker = CircuitBreaker(failure_threshold=2)

    assert breaker.record_failure("tool-a") is False
    assert breaker.record_failure("tool-a") is True
    assert breaker.record_failure("tool-a") is True
    assert breaker.is_open("tool-a") is True


def test_circuit_success_resets_failure_state():
    breaker = CircuitBreaker(failure_threshold=5)

    breaker.record_failure("tool-a")
    breaker.record_failure("tool-a")
    assert breaker.failure_count("tool-a") == 2

    breaker.record_success("tool-a")

    assert breaker.failure_count("tool-a") == 0
    assert breaker.is_open("tool-a") is False


def test_circuit_reset_alias_resets_state():
    breaker = CircuitBreaker(failure_threshold=2)

    breaker.record_failure("tool-a")
    breaker.reset("tool-a")

    assert breaker.failure_count("tool-a") == 0
    assert breaker.is_open("tool-a") is False


def test_circuit_auto_closes_after_open_duration():
    clock = FakeClock(100.0)
    breaker = CircuitBreaker(
        failure_threshold=1,
        open_duration_seconds=10,
        clock=clock,
    )

    assert breaker.record_failure("tool-a") is True
    assert breaker.is_open("tool-a") is True

    clock.advance(9.999)
    assert breaker.is_open("tool-a") is True

    clock.advance(0.001)
    assert breaker.is_open("tool-a") is False
    assert breaker.failure_count("tool-a") == 0


def test_circuit_state_is_per_tool():
    breaker = CircuitBreaker(failure_threshold=2)

    breaker.record_failure("tool-a")
    breaker.record_failure("tool-a")

    assert breaker.is_open("tool-a") is True
    assert breaker.is_open("tool-b") is False
    assert breaker.failure_count("tool-b") == 0


def test_circuit_constructor_clamps_invalid_values():
    breaker = CircuitBreaker(
        failure_threshold=0,
        open_duration_seconds=-10,
    )

    assert breaker.failure_threshold == 1
    assert breaker.open_duration_seconds == 0.0


# ============================================================================
# CircuitBreaker - Redis
# ============================================================================


def test_circuit_redis_failure_counter_and_open_state():
    redis = FakeRedis()
    breaker = CircuitBreaker(
        failure_threshold=3,
        open_duration_seconds=60,
        redis_client=redis,
    )

    assert breaker.record_failure("tool-a") is False
    assert breaker.record_failure("tool-a") is False
    assert breaker.record_failure("tool-a") is True

    failure_key = "fieldops:tools:circuit:tool-a:failures"
    open_key = "fieldops:tools:circuit:tool-a:open"

    assert redis.get(failure_key) == 3
    assert redis.get(open_key) == "1"
    assert breaker.is_open("tool-a") is True
    assert breaker.failure_count("tool-a") == 3


def test_circuit_redis_success_deletes_keys():
    redis = FakeRedis()
    breaker = CircuitBreaker(
        failure_threshold=2,
        redis_client=redis,
    )

    breaker.record_failure("tool-a")
    breaker.record_failure("tool-a")
    breaker.record_success("tool-a")

    assert redis.get("fieldops:tools:circuit:tool-a:failures") is None
    assert redis.get("fieldops:tools:circuit:tool-a:open") is None
    assert breaker.failure_count("tool-a") == 0


def test_circuit_redis_failure_falls_back_to_memory():
    breaker = CircuitBreaker(
        failure_threshold=2,
        redis_client=BrokenRedis(),
    )

    assert breaker.record_failure("tool-a") is False
    assert breaker.record_failure("tool-a") is True
    assert breaker.is_open("tool-a") is True


# ============================================================================
# ErrorRateTracker - memory
# ============================================================================


def test_error_rate_empty_is_zero():
    clock = FakeClock()
    tracker = ErrorRateTracker(window_seconds=10, clock=clock)

    assert tracker.get_rate("tool-a") == 0.0


def test_error_rate_all_successes_is_zero():
    clock = FakeClock()
    tracker = ErrorRateTracker(window_seconds=10, clock=clock)

    tracker.record("tool-a", True)
    tracker.record("tool-a", True)
    tracker.record("tool-a", True)

    assert tracker.get_rate("tool-a") == 0.0


def test_error_rate_counts_failures():
    clock = FakeClock()
    tracker = ErrorRateTracker(window_seconds=10, clock=clock)

    tracker.record("tool-a", False)
    tracker.record("tool-a", True)
    tracker.record("tool-a", False)
    tracker.record("tool-a", True)

    assert tracker.get_rate("tool-a") == pytest.approx(0.5)


def test_error_rate_is_per_tool():
    clock = FakeClock()
    tracker = ErrorRateTracker(window_seconds=10, clock=clock)

    tracker.record("tool-a", False)
    tracker.record("tool-b", True)

    assert tracker.get_rate("tool-a") == 1.0
    assert tracker.get_rate("tool-b") == 0.0


def test_error_rate_expires_old_events():
    clock = FakeClock(100.0)
    tracker = ErrorRateTracker(window_seconds=10, clock=clock)

    tracker.record("tool-a", False)
    tracker.record("tool-a", True)

    assert tracker.get_rate("tool-a") == pytest.approx(0.5)

    clock.advance(10.0)

    # Events exactly at cutoff are retained by the implementation.
    assert tracker.get_rate("tool-a") == pytest.approx(0.5)

    clock.advance(0.001)

    assert tracker.get_rate("tool-a") == 0.0


def test_error_rate_reset_clears_memory():
    clock = FakeClock()
    tracker = ErrorRateTracker(window_seconds=10, clock=clock)

    tracker.record("tool-a", False)
    assert tracker.get_rate("tool-a") == 1.0

    tracker.reset("tool-a")

    assert tracker.get_rate("tool-a") == 0.0


def test_error_rate_constructor_clamps_negative_window():
    tracker = ErrorRateTracker(window_seconds=-5)

    assert tracker.window_seconds == 0.0


# ============================================================================
# ErrorRateTracker - Redis
# ============================================================================


def test_error_rate_redis_records_total_and_failures():
    clock = FakeClock(100.0)
    redis = FakeRedis()
    tracker = ErrorRateTracker(
        window_seconds=60,
        clock=clock,
        redis_client=redis,
    )

    assert tracker.record("tool-a", False) == 1.0
    assert tracker.record("tool-a", True) == pytest.approx(0.5)

    total_key = "fieldops:tools:error-rate:tool-a:total"
    failure_key = "fieldops:tools:error-rate:tool-a:failures"

    assert redis.zcard(total_key) == 2
    assert redis.zcard(failure_key) == 1


def test_error_rate_redis_expires_old_events():
    clock = FakeClock(100.0)
    redis = FakeRedis()
    tracker = ErrorRateTracker(
        window_seconds=10,
        clock=clock,
        redis_client=redis,
    )

    tracker.record("tool-a", False)
    clock.advance(11)

    assert tracker.get_rate("tool-a") == 0.0


def test_error_rate_redis_reset_deletes_keys():
    clock = FakeClock()
    redis = FakeRedis()
    tracker = ErrorRateTracker(
        window_seconds=10,
        clock=clock,
        redis_client=redis,
    )

    tracker.record("tool-a", False)
    tracker.reset("tool-a")

    assert tracker.get_rate("tool-a") == 0.0
    assert redis.zcard("fieldops:tools:error-rate:tool-a:total") == 0
    assert redis.zcard("fieldops:tools:error-rate:tool-a:failures") == 0


def test_error_rate_redis_failure_falls_back_to_memory():
    clock = FakeClock()
    tracker = ErrorRateTracker(
        window_seconds=10,
        clock=clock,
        redis_client=BrokenRedis(),
    )

    tracker.record("tool-a", False)
    tracker.record("tool-a", True)

    assert tracker.get_rate("tool-a") == pytest.approx(0.5)


# ============================================================================
# ToolErrorHandler - classification
# ============================================================================


@pytest.fixture
def handler():
    return ToolErrorHandler(
        max_retries=3,
        backoff_base=0.1,
        sleep=lambda _: None,
    )


@pytest.mark.parametrize(
    ("exception", "expected_type", "expected_code", "retryable"),
    [
        (builtins.TimeoutError("slow"), TimeoutError, "TIMEOUT", True),
        (ConnectionError("network"), TransientError, "TRANSIENT_ERROR", True),
        (ValueError("bad input"), ValidationError, "VALIDATION_ERROR", False),
        (RuntimeError("unknown"), PermanentError, "PERMANENT_ERROR", False),
    ],
)
def test_classify_error(
    handler,
    exception,
    expected_type,
    expected_code,
    retryable,
):
    error = handler.classify_error(exception)

    assert isinstance(error, expected_type)
    assert error.code == expected_code
    assert error.retryable is retryable
    assert error.message == str(exception)


def test_classify_error_preserves_existing_tool_error(handler):
    original = TimeoutError("already classified")

    result = handler.classify_error(original)

    assert result is original


def test_classify_error_empty_exception_message(handler):
    error = handler.classify_error(ValueError())

    assert error.code == "VALIDATION_ERROR"
    assert error.message == "Invalid tool input"


def test_classify_error_does_not_swallow_base_exception(handler):
    # The production execute_with_retry catches Exception, not BaseException.
    class StopNow(BaseException):
        pass

    def operation():
        raise StopNow("stop")

    with pytest.raises(StopNow):
        handler.execute_with_retry(operation, tool_id="tool-a")


# ============================================================================
# ToolErrorHandler - handle_error / fallback
# ============================================================================


def test_handle_error_retryable_returns_structured_failure(handler):
    error = TimeoutError("timed out")

    result = handler.handle_error(
        "tool-a",
        error,
        parameters={"x": 1},
    )

    assert result.success is False
    assert result.result is None
    assert result.fallback_used is False
    assert result.fallback_tool_id is None
    assert isinstance(result.error, StructuredToolError)
    assert result.error.code == "TIMEOUT"
    assert result.error.tool_id == "tool-a"
    assert result.error.parameters == {"x": 1}


def test_handle_error_permanent_prefers_fallback_tool(handler):
    calls = []

    def fallback():
        calls.append("called")
        return "backup"

    result = handler.handle_error(
        "tool-a",
        PermanentError("failed"),
        fallback_tool=fallback,
        fallback_tool_id="backup-tool",
    )

    assert result.success is True
    assert result.result == "backup"
    assert result.error is None
    assert result.fallback_used is True
    assert result.fallback_tool_id == "backup-tool"
    assert calls == ["called"]


def test_handle_error_static_fallback_when_no_fallback_tool(handler):
    result = handler.handle_error(
        "tool-a",
        PermanentError("failed"),
        fallback_value={"status": "fallback"},
        has_fallback_value=True,
    )

    assert result.success is True
    assert result.result == {"status": "fallback"}
    assert result.fallback_used is True
    assert result.fallback_tool_id is None


def test_handle_error_fallback_tool_has_priority_over_static_value(handler):
    result = handler.handle_error(
        "tool-a",
        PermanentError("failed"),
        fallback_value="static",
        has_fallback_value=True,
        fallback_tool=lambda: "dynamic",
        fallback_tool_id="backup",
    )

    assert result.result == "dynamic"
    assert result.fallback_tool_id == "backup"


def test_handle_error_failed_fallback_tool_uses_static_value(handler):
    def failing_fallback():
        raise RuntimeError("backup failed")

    result = handler.handle_error(
        "tool-a",
        PermanentError("failed"),
        fallback_tool=failing_fallback,
        fallback_tool_id="backup",
        fallback_value="static",
        has_fallback_value=True,
    )

    assert result.success is True
    assert result.result == "static"
    assert result.fallback_used is True
    assert result.fallback_tool_id is None


def test_handle_error_no_fallback_returns_structured_error(handler):
    result = handler.handle_error(
        "tool-a",
        ValidationError("invalid"),
        parameters={"field": "x"},
    )

    assert result.success is False
    assert result.result is None
    assert result.fallback_used is False
    assert result.error.code == "VALIDATION_ERROR"
    assert result.error.parameters == {"field": "x"}


def test_handle_error_copies_parameters(handler):
    parameters = {"value": 1}

    result = handler.handle_error(
        "tool-a",
        PermanentError("failed"),
        parameters=parameters,
    )

    parameters["value"] = 2

    assert result.error.parameters == {"value": 1}


# ============================================================================
# ToolErrorHandler - retry
# ============================================================================


def test_execute_success_no_retry():
    sleeps = []
    handler = ToolErrorHandler(
        max_retries=3,
        backoff_base=0.1,
        sleep=sleeps.append,
    )

    calls = []

    def operation():
        calls.append(1)
        return "ok"

    result, error, retry_count = handler.execute_with_retry(
        operation,
        tool_id="tool-a",
    )

    assert result == "ok"
    assert error is None
    assert retry_count == 0
    assert len(calls) == 1
    assert sleeps == []


def test_execute_retries_transient_error_then_succeeds():
    sleeps = []
    handler = ToolErrorHandler(
        max_retries=3,
        backoff_base=0.1,
        sleep=sleeps.append,
    )

    calls = []

    def operation():
        calls.append(1)
        if len(calls) < 3:
            raise ConnectionError("temporary")
        return "ok"

    result, error, retry_count = handler.execute_with_retry(
        operation,
        tool_id="tool-a",
    )

    assert result == "ok"
    assert error is None
    assert retry_count == 2
    assert len(calls) == 3
    assert sleeps == pytest.approx([0.1, 0.2])


def test_execute_retries_three_times_then_returns_final_error():
    sleeps = []
    handler = ToolErrorHandler(
        max_retries=3,
        backoff_base=0.1,
        sleep=sleeps.append,
    )

    calls = []

    def operation():
        calls.append(1)
        raise TimeoutError("still failing")

    result, error, retry_count = handler.execute_with_retry(
        operation,
        tool_id="tool-a",
        parameters={"id": 7},
    )

    assert result is None
    assert isinstance(error, TimeoutError)
    assert error.tool_id == "tool-a"
    assert error.parameters == {"id": 7}
    assert retry_count == 3
    assert len(calls) == 4
    assert sleeps == pytest.approx([0.1, 0.2, 0.4])


def test_execute_does_not_retry_permanent_error():
    sleeps = []
    handler = ToolErrorHandler(
        max_retries=3,
        sleep=sleeps.append,
    )

    calls = []

    def operation():
        calls.append(1)
        raise ValueError("invalid")

    result, error, retry_count = handler.execute_with_retry(
        operation,
        tool_id="tool-a",
    )

    assert result is None
    assert isinstance(error, ValidationError)
    assert retry_count == 0
    assert len(calls) == 1
    assert sleeps == []


def test_execute_max_retries_zero():
    handler = ToolErrorHandler(
        max_retries=0,
        sleep=lambda _: pytest.fail("sleep must not be called"),
    )

    calls = []

    def operation():
        calls.append(1)
        raise ConnectionError("temporary")

    result, error, retry_count = handler.execute_with_retry(
        operation,
        tool_id="tool-a",
    )

    assert result is None
    assert isinstance(error, TransientError)
    assert retry_count == 0
    assert len(calls) == 1


def test_execute_backoff_zero_does_not_sleep():
    sleeps = []
    handler = ToolErrorHandler(
        max_retries=3,
        backoff_base=0,
        sleep=sleeps.append,
    )

    calls = []

    def operation():
        calls.append(1)
        if len(calls) == 1:
            raise ConnectionError("temporary")
        return "ok"

    result, error, retry_count = handler.execute_with_retry(
        operation,
        tool_id="tool-a",
    )

    assert result == "ok"
    assert error is None
    assert retry_count == 1
    assert sleeps == []


# ============================================================================
# Retry + circuit breaker integration
# ============================================================================


def test_final_failures_increment_circuit_breaker_only_once_per_execution():
    breaker = CircuitBreaker(failure_threshold=2)
    handler = ToolErrorHandler(
        max_retries=3,
        circuit_breaker=breaker,
        sleep=lambda _: None,
    )

    def operation():
        raise ConnectionError("failure")

    result, error, retry_count = handler.execute_with_retry(
        operation,
        tool_id="tool-a",
    )

    assert result is None
    assert isinstance(error, TransientError)
    assert retry_count == 3

    # One final failed execution = one circuit failure.
    assert breaker.failure_count("tool-a") == 1


def test_second_final_failure_opens_circuit():
    breaker = CircuitBreaker(failure_threshold=2)
    handler = ToolErrorHandler(
        max_retries=0,
        circuit_breaker=breaker,
        sleep=lambda _: None,
    )

    def operation():
        raise RuntimeError("failure")

    handler.execute_with_retry(operation, tool_id="tool-a")
    assert breaker.is_open("tool-a") is False

    handler.execute_with_retry(operation, tool_id="tool-a")
    assert breaker.is_open("tool-a") is True


def test_open_circuit_prevents_operation():
    breaker = CircuitBreaker(failure_threshold=1)
    handler = ToolErrorHandler(
        max_retries=3,
        circuit_breaker=breaker,
        sleep=lambda _: None,
    )

    breaker.record_failure("tool-a")

    calls = []

    def operation():
        calls.append(1)
        return "should not run"

    result, error, retry_count = handler.execute_with_retry(
        operation,
        tool_id="tool-a",
    )

    assert result is None
    assert isinstance(error, PermanentError)
    assert error.code == "CIRCUIT_OPEN"
    assert retry_count == 0
    assert calls == []


def test_success_resets_circuit_failure_count():
    breaker = CircuitBreaker(failure_threshold=3)
    handler = ToolErrorHandler(
        max_retries=0,
        circuit_breaker=breaker,
        sleep=lambda _: None,
    )

    def fail():
        raise RuntimeError("failure")

    handler.execute_with_retry(fail, tool_id="tool-a")
    handler.execute_with_retry(fail, tool_id="tool-a")

    assert breaker.failure_count("tool-a") == 2

    result, error, retry_count = handler.execute_with_retry(
        lambda: "success",
        tool_id="tool-a",
    )

    assert result == "success"
    assert error is None
    assert retry_count == 0
    assert breaker.failure_count("tool-a") == 0


# ============================================================================
# Error-rate tracking / alerting
# ============================================================================


def test_error_rate_records_success_and_failure():
    class SpyTracker:
        def __init__(self):
            self.calls = []
            self.window_seconds = 300

        def record(self, tool_id, success):
            self.calls.append((tool_id, success))
            return 0.0

    tracker = SpyTracker()
    handler = ToolErrorHandler(
        error_rate_tracker=tracker,
        sleep=lambda _: None,
    )

    handler._record_error_rate("tool-a", success=True)
    handler._record_error_rate("tool-a", success=False)

    assert tracker.calls == [
        ("tool-a", True),
        ("tool-a", False),
    ]


def test_error_rate_alert_not_triggered_at_exactly_ten_percent():
    alerts = []

    class Tracker:
        window_seconds = 300

        def record(self, tool_id, success):
            return 0.10

    handler = ToolErrorHandler(
        error_rate_tracker=Tracker(),
        alert_callback=alerts.append,
    )

    handler._record_error_rate("tool-a", success=False)

    assert alerts == []


def test_error_rate_alert_triggered_above_ten_percent():
    alerts = []

    class Tracker:
        window_seconds = 300

        def record(self, tool_id, success):
            return 0.11

    handler = ToolErrorHandler(
        error_rate_tracker=Tracker(),
        alert_callback=alerts.append,
    )

    handler._record_error_rate("tool-a", success=False)

    assert len(alerts) == 1
    payload = alerts[0]
    assert payload["type"] == "tool_error_rate_alert"
    assert payload["tool_id"] == "tool-a"
    assert payload["error_rate"] == 0.11
    assert payload["threshold"] == 0.10
    assert payload["window_seconds"] == 300


def test_error_rate_alert_is_deduplicated_locally():
    alerts = []

    class Tracker:
        window_seconds = 300

        def record(self, tool_id, success):
            return 0.50

    handler = ToolErrorHandler(
        error_rate_tracker=Tracker(),
        alert_callback=alerts.append,
    )

    handler._record_error_rate("tool-a", success=False)
    handler._record_error_rate("tool-a", success=False)

    assert len(alerts) == 1


def test_error_rate_alert_is_independent_per_tool():
    alerts = []

    class Tracker:
        window_seconds = 300

        def record(self, tool_id, success):
            return 0.50

    handler = ToolErrorHandler(
        error_rate_tracker=Tracker(),
        alert_callback=alerts.append,
    )

    handler._record_error_rate("tool-a", success=False)
    handler._record_error_rate("tool-b", success=False)

    assert len(alerts) == 2
    assert {alert["tool_id"] for alert in alerts} == {"tool-a", "tool-b"}


def test_reset_alert_allows_alert_again():
    alerts = []

    class Tracker:
        window_seconds = 300

        def record(self, tool_id, success):
            return 0.50

    handler = ToolErrorHandler(
        error_rate_tracker=Tracker(),
        alert_callback=alerts.append,
    )

    handler._record_error_rate("tool-a", success=False)
    handler.reset_alert("tool-a")
    handler._record_error_rate("tool-a", success=False)

    assert len(alerts) == 2


def test_alert_callback_exception_is_swallowed():
    class Tracker:
        window_seconds = 300

        def record(self, tool_id, success):
            return 0.50

    def bad_callback(_payload):
        raise RuntimeError("alert system unavailable")

    handler = ToolErrorHandler(
        error_rate_tracker=Tracker(),
        alert_callback=bad_callback,
    )

    # Must not raise.
    handler._record_error_rate("tool-a", success=False)


def test_error_rate_alert_uses_redis_deduplication():
    alerts = []
    redis = FakeRedis()

    class Tracker:
        window_seconds = 300

        def record(self, tool_id, success):
            return 0.50

    handler = ToolErrorHandler(
        error_rate_tracker=Tracker(),
        alert_callback=alerts.append,
        redis_client=redis,
    )

    handler._record_error_rate("tool-a", success=False)
    handler._record_error_rate("tool-a", success=False)

    assert len(alerts) == 1
    assert redis.get("fieldops:tools:error-rate:tool-a:alerted") == "1"


def test_error_rate_redis_dedup_failure_falls_back_to_local():
    alerts = []

    class Tracker:
        window_seconds = 300

        def record(self, tool_id, success):
            return 0.50

    handler = ToolErrorHandler(
        error_rate_tracker=Tracker(),
        alert_callback=alerts.append,
        redis_client=BrokenRedis(),
    )

    handler._record_error_rate("tool-a", success=False)
    handler._record_error_rate("tool-a", success=False)

    assert len(alerts) == 1


# ============================================================================
# End-to-end handler behavior
# ============================================================================


def test_end_to_end_transient_failures_then_success():
    alerts = []
    sleeps = []
    breaker = CircuitBreaker(failure_threshold=5)
    tracker = ErrorRateTracker(window_seconds=300)

    handler = ToolErrorHandler(
        max_retries=3,
        backoff_base=0.01,
        circuit_breaker=breaker,
        error_rate_tracker=tracker,
        alert_callback=alerts.append,
        sleep=sleeps.append,
    )

    attempts = []

    def operation():
        attempts.append(1)
        if len(attempts) < 3:
            raise TimeoutError("temporary timeout")
        return {"status": "ok"}

    result, error, retry_count = handler.execute_with_retry(
        operation,
        tool_id="sync-tool",
        parameters={"job_id": 123},
    )

    assert result == {"status": "ok"}
    assert error is None
    assert retry_count == 2
    assert len(attempts) == 3
    assert breaker.failure_count("sync-tool") == 0
    assert tracker.get_rate("sync-tool") == 0.0


def test_end_to_end_permanent_error_can_use_fallback():
    handler = ToolErrorHandler(
        max_retries=3,
        sleep=lambda _: None,
    )

    result, error, retry_count = handler.execute_with_retry(
        lambda: (_ for _ in ()).throw(ValueError("bad request")),
        tool_id="primary",
    )

    assert result is None
    assert isinstance(error, ValidationError)
    assert retry_count == 0

    fallback_result = handler.handle_error(
        "primary",
        error,
        fallback_tool=lambda: "fallback-ok",
        fallback_tool_id="secondary",
        parameters={"request": 1},
        retry_count=retry_count,
    )

    assert fallback_result.success is True
    assert fallback_result.result == "fallback-ok"
    assert fallback_result.fallback_used is True
    assert fallback_result.fallback_tool_id == "secondary"


# ============================================================================
# Webhook
# ============================================================================


def test_webhook_alert_builds_json_post(monkeypatch):
    captured = {}
    response = FakeHTTPResponse()

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return response

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    payload = {
        "type": "tool_error_rate_alert",
        "tool_id": "tool-a",
        "error_rate": 0.5,
    }

    ToolErrorHandler.webhook_alert(
        "https://example.test/webhook",
        payload,
        timeout=7.5,
    )

    request = captured["request"]

    assert request.full_url == "https://example.test/webhook"
    assert request.get_method() == "POST"
    assert request.get_header("Content-type") == "application/json"
    assert json.loads(request.data.decode("utf-8")) == payload
    assert captured["timeout"] == 7.5
    assert response.entered is True
    assert response.exited is True


def test_webhook_alert_preserves_unicode(monkeypatch):
    captured = {}
    response = FakeHTTPResponse()

    def fake_urlopen(request, timeout):
        captured["request"] = request
        return response

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    payload = {"message": "தமிழ் / español / 日本語"}

    ToolErrorHandler.webhook_alert(
        "https://example.test/webhook",
        payload,
    )

    decoded = json.loads(captured["request"].data.decode("utf-8"))
    assert decoded == payload


def test_webhook_alert_propagates_urlopen_error(monkeypatch):
    def fake_urlopen(request, timeout):
        raise urllib.error.URLError("network down")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(urllib.error.URLError):
        ToolErrorHandler.webhook_alert(
            "https://example.test/webhook",
            {"x": 1},
        )


# ============================================================================
# Redis + handler integration
# ============================================================================


def test_handler_uses_same_redis_client_for_breaker_and_tracker():
    redis = FakeRedis()

    handler = ToolErrorHandler(
        redis_client=redis,
        sleep=lambda _: None,
    )

    assert handler.redis is redis
    assert handler.circuit_breaker.redis is redis
    assert handler.error_rate_tracker.redis is redis


def test_handler_redis_fallback_does_not_break_execution():
    handler = ToolErrorHandler(
        redis_client=BrokenRedis(),
        max_retries=1,
        sleep=lambda _: None,
    )

    calls = []

    def operation():
        calls.append(1)
        if len(calls) == 1:
            raise ConnectionError("temporary")
        return "ok"

    result, error, retry_count = handler.execute_with_retry(
        operation,
        tool_id="tool-a",
    )

    assert result == "ok"
    assert error is None
    assert retry_count == 1


# ============================================================================
# Parameter / configuration edge cases
# ============================================================================


def test_handler_clamps_negative_max_retries_and_backoff():
    handler = ToolErrorHandler(
        max_retries=-5,
        backoff_base=-1,
        sleep=lambda _: None,
    )

    assert handler.max_retries == 0
    assert handler.backoff_base == 0.0


def test_handler_default_components_are_created():
    handler = ToolErrorHandler(sleep=lambda _: None)

    assert isinstance(handler.circuit_breaker, CircuitBreaker)
    assert isinstance(handler.error_rate_tracker, ErrorRateTracker)


def test_execute_parameters_are_copied_into_error():
    handler = ToolErrorHandler(
        max_retries=0,
        sleep=lambda _: None,
    )
    parameters = {"id": 1}

    _, error, _ = handler.execute_with_retry(
        lambda: (_ for _ in ()).throw(ValueError("bad")),
        tool_id="tool-a",
        parameters=parameters,
    )

    parameters["id"] = 999

    assert error.parameters == {"id": 1}


def test_execute_success_records_no_circuit_failure():
    breaker = CircuitBreaker(failure_threshold=2)
    handler = ToolErrorHandler(
        max_retries=0,
        circuit_breaker=breaker,
        sleep=lambda _: None,
    )

    result, error, retry_count = handler.execute_with_retry(
        lambda: "ok",
        tool_id="tool-a",
    )

    assert result == "ok"
    assert error is None
    assert retry_count == 0
    assert breaker.failure_count("tool-a") == 0


# ============================================================================
# Test-suite contract / smoke
# ============================================================================


def test_public_constants_are_expected():
    assert ToolErrorHandler.MAX_RETRIES == 3
    assert ToolErrorHandler.ERROR_RATE_THRESHOLD == 0.10
    assert ToolErrorHandler.CIRCUIT_FAILURE_THRESHOLD == 5
    assert ToolErrorHandler.CIRCUIT_OPEN_DURATION == 300
    assert CircuitBreaker.FAILURE_THRESHOLD == 5
    assert CircuitBreaker.OPEN_DURATION_SECONDS == 300
    assert ErrorRateTracker.WINDOW_SECONDS == 300

def test_circuit_breaker_failure_count_decodes_redis_bytes():
    class BytesRedis(FakeRedis):
        def get(self, key):
            return b"3"

    redis = BytesRedis()

    breaker = CircuitBreaker(
        failure_threshold=5,
        redis_client=redis,
    )

    assert breaker.failure_count("tool-1") == 3


def test_circuit_breaker_failure_count_falls_back_when_redis_fails():
    redis = BrokenRedis()
    breaker = CircuitBreaker(
        failure_threshold=5,
        redis_client=redis,
    )

    # Populate local fallback state.
    breaker.record_failure("tool-1")

    assert breaker.failure_count("tool-1") == 1


def test_error_rate_tracker_redis_zero_total_returns_zero():
    redis = FakeRedis()
    tracker = ErrorRateTracker(redis_client=redis)

    # No events have been recorded.
    assert tracker.record("tool-1", success=True) == 0.0


def test_error_rate_tracker_redis_get_rate_returns_failure_ratio():
    redis = FakeRedis()
    tracker = ErrorRateTracker(redis_client=redis)

    tracker.record("tool-1", success=False)
    tracker.record("tool-1", success=True)

    assert tracker.get_rate("tool-1") == 0.5


def test_error_rate_tracker_reset_redis_exception_falls_back_to_memory():
    redis = BrokenRedis()
    tracker = ErrorRateTracker(redis_client=redis)

    tracker.record("tool-1", success=False)

    assert tracker.get_rate("tool-1") == 1.0

    tracker.reset("tool-1")

    assert tracker.get_rate("tool-1") == 0.0


def test_tool_error_handler_reset_alert_with_redis():
    redis = FakeRedis()

    handler = ToolErrorHandler(
        redis_client=redis,
    )

    handler._alerted_tools.add("tool-1")

    handler.reset_alert("tool-1")

    assert "tool-1" not in handler._alerted_tools


def test_tool_error_handler_reset_alert_redis_exception_falls_back():
    redis = BrokenRedis()

    handler = ToolErrorHandler(
        redis_client=redis,
    )

    handler._alerted_tools.add("tool-1")

    handler.reset_alert("tool-1")

    assert "tool-1" not in handler._alerted_tools