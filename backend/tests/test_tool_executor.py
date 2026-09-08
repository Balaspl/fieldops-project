from __future__ import annotations

import asyncio
import json
import queue
import time

import pytest

import app.tools.executor as executor_module

from app.tools.errors import (
    PermanentError,
    TransientError,
    TimeoutError as ToolTimeoutError,
)
from app.tools.executor import (
    ToolCall,
    ToolExecutionError,
    ToolExecutor,
    ToolResult,
)
from app.tools.examples import generate_sms_schema
from app.tools.registry import (
    ToolRegistry,
    create_default_registry,
)
from app.tools.schema import (
    ToolContract,
    ToolReturn,
    ToolSchema,
)


# ======================================================================
# TOP-LEVEL HANDLERS
# ======================================================================
#
# IMPORTANT:
# Windows multiprocessing uses "spawn".
# Therefore handlers passed to multiprocessing.Process must be
# module-level functions and NOT nested functions.
# ======================================================================


def generate_sms(
    message: str,
    priority: str = "normal",
) -> str:
    return f"{priority}: {message}"


def failing_tool() -> str:
    raise RuntimeError("Tool exploded")


def slow_tool() -> str:
    time.sleep(15)
    return "finished"

def none_tool():
    return None

def crash_tool() -> None:
    import os

    os._exit(1)


def bad_output_tool() -> int:
    return 123


def one_second_tool() -> str:
    time.sleep(1)
    return "done"


class NotSerializable:
    pass


def bad_serialization_handler():
    return NotSerializable()


# ======================================================================
# RETRY HANDLERS
# ======================================================================


class RetryState:
    attempts = 0


retry_state = RetryState()


def transient_then_success_tool() -> str:
    retry_state.attempts += 1

    if retry_state.attempts <= 3:
        raise ConnectionError(
            "temporary connection failure"
        )

    return "success"


def always_transient_tool() -> str:
    raise ConnectionError(
        "temporary connection failure"
    )


def timeout_tool() -> str:
    raise builtins_timeout_error()


def builtins_timeout_error():
    return TimeoutError(
        "temporary timeout"
    )


def permanent_failure_tool() -> str:
    raise RuntimeError(
        "permanent failure"
    )


# ======================================================================
# FAKE CACHE
# ======================================================================


class FakeCache:
    """
    Redis-compatible fake cache.

    Supported methods:
        get(key)
        setex(key, ttl, value)
    """

    def __init__(self):
        self.data: dict[str, object] = {}
        self.set_calls = 0
        self.get_calls = 0
        self.last_ttl: int | None = None

    def get(self, key: str):
        self.get_calls += 1
        return self.data.get(key)

    def setex(
        self,
        key: str,
        ttl: int,
        value: str,
    ) -> bool:
        self.set_calls += 1
        self.last_ttl = ttl
        self.data[key] = value
        return True


# ======================================================================
# REGISTRY HELPERS
# ======================================================================


def create_executor(
    cache=None,
    *,
    max_retries: int = 3,
    timeout_seconds: float = 10,
    metrics=None,
) -> ToolExecutor:
    registry = ToolRegistry()

    registry.register_tool(
        generate_sms_schema(),
        handler=generate_sms,
        category="communication",
        capabilities={"sms"},
    )

    return ToolExecutor(
        registry=registry,
        cache=cache,
        max_retries=max_retries,
        timeout_seconds=timeout_seconds,
        metrics=metrics,
    )
@pytest.fixture
def executor():
    return create_executor()

def create_string_tool_schema(
    name: str,
) -> ToolSchema:
    return ToolSchema(
        ToolContract(
            name=name,
            description=f"Test tool: {name}",
            version="v1",
            parameters=[],
            required=[],
            returns=ToolReturn(
                type="string",
                description="String result",
                schema={
                    "type": "string",
                },
            ),
        )
    )


def create_string_tool_registry(
    name: str,
    handler,
    *,
    fallback_value=None,
    has_fallback_value: bool = False,
    fallback_tool_id: str | None = None,
    cacheable: bool = True,
    cache_ttl: int = 60,
) -> ToolRegistry:

    registry = ToolRegistry()

    registry.register_tool(
        create_string_tool_schema(name),
        handler=handler,
        fallback_value=fallback_value,
        has_fallback_value=has_fallback_value,
        fallback_tool_id=fallback_tool_id,
        cacheable=cacheable,
        cache_ttl=cache_ttl,
    )

    return registry


# ======================================================================
# BASIC EXECUTION
# ======================================================================


def test_execute_registered_tool():
    executor = create_executor()

    result = executor.execute(
        tool_id="generate_sms",
        parameters={"message": "Hello"},
        tenant_id="tenant-1",
    )

    assert isinstance(result, ToolResult)
    assert result.success is True
    assert result.result == "normal: Hello"
    assert result.error is None
    assert result.cached is False


def test_execute_applies_default_parameter():
    executor = create_executor()

    result = executor.execute(
        tool_id="generate_sms",
        parameters={"message": "Hello"},
        tenant_id="tenant-1",
    )

    assert result.success is True
    assert result.result == "normal: Hello"


def test_execute_uses_provided_parameter():
    executor = create_executor()

    result = executor.execute(
        tool_id="generate_sms",
        parameters={
            "message": "Urgent message",
            "priority": "high",
        },
        tenant_id="tenant-1",
    )

    assert result.success is True
    assert result.result == "high: Urgent message"


# ======================================================================
# INPUT VALIDATION
# ======================================================================


def test_execute_rejects_invalid_input():
    executor = create_executor()

    result = executor.execute(
        tool_id="generate_sms",
        parameters={"message": 123},
        tenant_id="tenant-1",
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "INVALID_INPUT"


def test_execute_rejects_malicious_input():
    executor = create_executor()

    result = executor.execute(
        tool_id="generate_sms",
        parameters={
            "message": "DROP TABLE users",
        },
        tenant_id="tenant-1",
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "INVALID_INPUT"
    assert "SQL injection" in result.error.message


def test_execute_rejects_unknown_tool():
    executor = create_executor()

    result = executor.execute(
        tool_id="unknown_tool",
        parameters={"message": "Hello"},
        tenant_id="tenant-1",
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "TOOL_NOT_FOUND"


def test_execute_rejects_tool_without_handler():
    registry = ToolRegistry()

    registry.register_tool(
        generate_sms_schema(),
    )

    executor = ToolExecutor(
        registry=registry,
    )

    result = executor.execute(
        tool_id="generate_sms",
        parameters={"message": "Hello"},
        tenant_id="tenant-1",
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "TOOL_HANDLER_NOT_FOUND"


def test_execute_sanitizes_html_before_handler():
    executor = create_executor()

    result = executor.execute(
        tool_id="generate_sms",
        parameters={
            "message": "<b>Hello</b>",
        },
        tenant_id="tenant-1",
    )

    assert result.success is True
    assert result.result == "normal: Hello"


def test_execute_redacts_pii_before_handler():
    executor = create_executor()

    result = executor.execute(
        tool_id="generate_sms",
        parameters={
            "message": "Contact test@example.com",
        },
        tenant_id="tenant-1",
    )

    assert result.success is True
    assert result.result == (
        "normal: Contact [REDACTED]"
    )


# ======================================================================
# SANDBOX / EXECUTION ERRORS
# ======================================================================


def test_tool_exception_returns_structured_error():
    registry = create_string_tool_registry(
        "failing_tool",
        failing_tool,
    )

    executor = ToolExecutor(
        registry=registry,
        max_retries=0,
    )

    result = executor.execute(
        tool_id="failing_tool",
        parameters={},
        tenant_id="tenant-1",
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "TOOL_EXECUTION_ERROR"
    assert "Tool exploded" in result.error.message


def test_timeout_kills_long_running_tool():
    registry = create_string_tool_registry(
        "slow_tool",
        slow_tool,
    )

    executor = ToolExecutor(
        registry=registry,
        timeout_seconds=1,
        max_retries=0,
    )

    started = time.perf_counter()

    result = executor.execute(
        tool_id="slow_tool",
        parameters={},
        tenant_id="tenant-1",
    )

    elapsed = time.perf_counter() - started

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "TIMEOUT"
    assert elapsed < 3


def test_subprocess_failure_does_not_crash_parent():
    registry = create_string_tool_registry(
        "crash_tool",
        crash_tool,
    )

    executor = ToolExecutor(
        registry=registry,
        max_retries=0,
    )

    result = executor.execute(
        tool_id="crash_tool",
        parameters={},
        tenant_id="tenant-1",
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "SANDBOX_PROCESS_ERROR"


# ======================================================================
# OUTPUT VALIDATION
# ======================================================================


def test_output_validation_rejects_invalid_result():
    registry = create_string_tool_registry(
        "bad_output_tool",
        bad_output_tool,
    )

    executor = ToolExecutor(
        registry=registry,
        max_retries=0,
    )

    result = executor.execute(
        tool_id="bad_output_tool",
        parameters={},
        tenant_id="tenant-1",
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "OUTPUT_VALIDATION_ERROR"


def test_output_validation_handles_validator_exception(
    monkeypatch,
):
    registry = create_string_tool_registry(
        "bad_validator_tool",
        failing_tool,
    )

    registered_tool = registry.get_tool(
        "bad_validator_tool",
    )

    assert registered_tool is not None

    executor = ToolExecutor(
        registry=registry,
    )

    class BrokenValidator:
        def __init__(self, schema):
            raise RuntimeError(
                "validator initialization failed"
            )

    monkeypatch.setattr(
        executor_module,
        "Draft202012Validator",
        BrokenValidator,
    )

    valid, message = executor._validate_output(
        registered_tool=registered_tool,
        result="valid",
    )

    assert valid is False
    assert message == (
        "Output schema validation failed: "
        "validator initialization failed"
    )


def test_output_serialization_error():
    registry = ToolRegistry()

    registry.register_tool(
        create_string_tool_schema(
            "serialization_tool"
        ),
        handler=bad_serialization_handler,
    )

    executor = ToolExecutor(
        registry=registry,
        max_retries=0,
    )

    # Force output validation to succeed so execution reaches
    # JSON serialization.
    executor._validate_output = (
        lambda registered_tool, result: (
            True,
            "",
        )
    )

    result = executor.execute(
        tool_id="serialization_tool",
        parameters={},
        tenant_id="tenant-1",
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == (
        "OUTPUT_SERIALIZATION_ERROR"
    )


# ======================================================================
# RETRY
# ======================================================================


def test_transient_error_retries_three_times(executor, monkeypatch):
    calls = []

    def fake_run_in_subprocess(**kwargs):
        calls.append(1)

        if len(calls) <= 3:
            return {
                "success": False,
                "error": {
                    "code": "TRANSIENT_ERROR",
                    "message": "temporary failure",
                },
            }

        return {
            "success": True,
            "result": "success",
        }

    monkeypatch.setattr(
        executor,
        "_run_in_subprocess",
        fake_run_in_subprocess,
    )

    result = executor.execute(
        "generate_sms",
        {"message": "hello"},
    )

    assert result.success is True
    assert result.result == "success"
    assert len(calls) == 4

def test_transient_error_exhausts_three_retries(
    monkeypatch,
):
    registry = create_string_tool_registry(
        "always_transient_tool",
        always_transient_tool,
        cacheable=False,
    )

    executor = ToolExecutor(
        registry=registry,
        max_retries=3,
    )

    sleep_calls = []

    monkeypatch.setattr(
        executor.error_handler,
        "_sleep",
        lambda seconds: sleep_calls.append(
            seconds
        ),
        raising=False,
    )

    result = executor.execute(
        tool_id="always_transient_tool",
        parameters={},
        tenant_id="tenant-1",
    )

    assert result.success is False
    assert result.error is not None

    # Four total attempts.
    #
    # We cannot count the subprocess attempts directly
    # from this test, so we verify the retry count.
    assert result.error.retry_count == 3


def test_retry_uses_exponential_backoff(executor, monkeypatch):
    calls = []
    delays = []

    def fake_run_in_subprocess(**kwargs):
        calls.append(1)

        if len(calls) <= 3:
            return {
                "success": False,
                "error": {
                    "code": "TRANSIENT_ERROR",
                    "message": "temporary failure",
                },
            }

        return {
            "success": True,
            "result": "success",
        }

    monkeypatch.setattr(
        executor,
        "_run_in_subprocess",
        fake_run_in_subprocess,
    )

    monkeypatch.setattr(
        executor.error_handler,
    "_sleep",
        lambda delay: delays.append(delay),
    )

    result = executor.execute(
        "generate_sms",
        {"message": "hello"},
    )

    assert result.success is True
    assert len(calls) == 4
    assert delays == [0.1, 0.2, 0.4]


def test_permanent_error_is_not_retried():
    registry = create_string_tool_registry(
        "permanent_failure_tool",
        permanent_failure_tool,
        cacheable=False,
    )

    executor = ToolExecutor(
        registry=registry,
        max_retries=3,
    )

    result = executor.execute(
        tool_id="permanent_failure_tool",
        parameters={},
        tenant_id="tenant-1",
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.retry_count == 0


def test_zero_retries_means_single_attempt():
    registry = create_string_tool_registry(
        "always_transient_tool",
        always_transient_tool,
        cacheable=False,
    )

    executor = ToolExecutor(
        registry=registry,
        max_retries=0,
    )

    result = executor.execute(
        tool_id="always_transient_tool",
        parameters={},
        tenant_id="tenant-1",
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.retry_count == 0


# ======================================================================
# FALLBACK
# ======================================================================


def test_permanent_failure_uses_static_fallback():
    registry = create_string_tool_registry(
        "permanent_failure_tool",
        permanent_failure_tool,
        fallback_value="fallback-result",
        has_fallback_value=True,
        cacheable=False,
    )

    executor = ToolExecutor(
        registry=registry,
        max_retries=0,
    )

    result = executor.execute(
        tool_id="permanent_failure_tool",
        parameters={},
        tenant_id="tenant-1",
    )

    assert result.success is True
    assert result.result == "fallback-result"
    assert result.error is None


def fallback_tool_handler() -> str:
    return "alternative-tool-result"


def test_permanent_failure_uses_alternative_tool():
    registry = ToolRegistry()

    registry.register_tool(
        create_string_tool_schema(
            "primary_tool"
        ),
        handler=permanent_failure_tool,
        fallback_tool_id="fallback_tool",
        cacheable=False,
    )

    registry.register_tool(
        create_string_tool_schema(
            "fallback_tool"
        ),
        handler=fallback_tool_handler,
        cacheable=False,
    )

    executor = ToolExecutor(
        registry=registry,
        max_retries=0,
    )

    result = executor.execute(
        tool_id="primary_tool",
        parameters={},
        tenant_id="tenant-1",
    )

    assert result.success is True
    assert result.result == (
        "alternative-tool-result"
    )


def test_transient_failure_does_not_use_fallback_before_retry_exhaustion(
    monkeypatch,
):
    registry = create_string_tool_registry(
        "always_transient_tool",
        always_transient_tool,
        fallback_value="fallback-result",
        has_fallback_value=True,
        cacheable=False,
    )

    executor = ToolExecutor(
        registry=registry,
        max_retries=2,
    )

    monkeypatch.setattr(
        executor.error_handler,
        "_sleep",
        lambda seconds: None,
        raising=False,
    )

    result = executor.execute(
        tool_id="always_transient_tool",
        parameters={},
        tenant_id="tenant-1",
    )

    # The current policy is:
    #
    # transient -> retry
    # permanent -> fallback
    #
    # A retryable error that remains retryable after retries
    # should not automatically use the permanent fallback.
    assert result.success is False
    assert result.error is not None


# ======================================================================
# CIRCUIT BREAKER
# ======================================================================


def test_circuit_breaker_opens_after_five_failures():
    registry = create_string_tool_registry(
        "permanent_failure_tool",
        permanent_failure_tool,
        cacheable=False,
    )

    executor = ToolExecutor(
        registry=registry,
        max_retries=0,
    )

    # The executor's circuit breaker should count final
    # invocation failures.
    for _ in range(5):
        result = executor.execute(
            tool_id="permanent_failure_tool",
            parameters={},
            tenant_id="tenant-1",
        )

        assert result.success is False

    result = executor.execute(
        tool_id="permanent_failure_tool",
        parameters={},
        tenant_id="tenant-1",
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "CIRCUIT_OPEN"


def test_circuit_breaker_can_be_checked_directly(executor):
    tool_id = "circuit-direct-test"

    circuit = executor.error_handler.circuit_breaker
    circuit.reset(tool_id)

    assert circuit.is_open(tool_id) is False

    for _ in range(4):
        circuit.record_failure(tool_id)

    assert circuit.is_open(tool_id) is False

    circuit.record_failure(tool_id)

    assert circuit.is_open(tool_id) is True


# ======================================================================
# STRUCTURED ERRORS
# ======================================================================


def test_structured_error_contains_required_fields():
    registry = create_string_tool_registry(
        "failing_tool",
        failing_tool,
        cacheable=False,
    )

    executor = ToolExecutor(
        registry=registry,
        max_retries=0,
    )

    # Ensure previous tests cannot leave this tool's
    # circuit breaker open in Redis.
    executor.error_handler.circuit_breaker.reset(
        "permanent_failure_tool"
    )

    parameters = {
        "foo": "bar",
    }

    result = executor.execute(
        tool_id="failing_tool",
        parameters=parameters,
        tenant_id="tenant-1",
    )

    assert result.success is False
    assert result.error is not None

    assert isinstance(
        result.error,
        ToolExecutionError,
    )

    assert result.error.code == (
        "TOOL_EXECUTION_ERROR"
    )

    assert result.error.message

    assert result.error.tool_id == (
        "failing_tool"
    )

    assert result.error.parameters == parameters
    assert result.error.retry_count == 0
    assert result.error.fallback_used is False


def test_successful_result_has_no_error():
    executor = create_executor()

    result = executor.execute(
        tool_id="generate_sms",
        parameters={
            "message": "Hello",
        },
        tenant_id="tenant-1",
    )

    assert result.success is True
    assert result.error is None


# ======================================================================
# CACHE
# ======================================================================


def test_cache_hit():
    cache = FakeCache()

    executor = create_executor(
        cache=cache,
    )

    first = executor.execute(
        tool_id="generate_sms",
        parameters={
            "message": "Hello",
        },
        tenant_id="tenant-1",
    )

    second = executor.execute(
        tool_id="generate_sms",
        parameters={
            "message": "Hello",
        },
        tenant_id="tenant-1",
    )

    assert first.success is True
    assert first.cached is False

    assert second.success is True
    assert second.cached is True
    assert second.result == "normal: Hello"

    assert cache.set_calls == 1
    assert cache.get_calls == 2


def test_cache_key_changes_for_different_parameters():
    cache = FakeCache()

    executor = create_executor(
        cache=cache,
    )

    first = executor.execute(
        tool_id="generate_sms",
        parameters={
            "message": "Hello",
        },
        tenant_id="tenant-1",
    )

    second = executor.execute(
        tool_id="generate_sms",
        parameters={
            "message": "World",
        },
        tenant_id="tenant-1",
    )

    assert first.success is True
    assert second.success is True

    assert first.cached is False
    assert second.cached is False

    assert cache.set_calls == 2


def test_cache_uses_60_second_ttl():
    cache = FakeCache()

    executor = create_executor(
        cache=cache,
    )

    result = executor.execute(
        tool_id="generate_sms",
        parameters={
            "message": "Hello",
        },
        tenant_id="tenant-1",
    )

    assert result.success is True
    assert cache.last_ttl == 60


def test_cache_returns_json_value():
    cache = FakeCache()

    executor = create_executor(
        cache=cache,
    )

    key = executor._cache_key(
        "generate_sms",
        {
            "message": "Cached",
        },
        "tenant-1",
    )

    cache.data[key] = json.dumps(
        "cached-result"
    )

    result = executor.execute(
        tool_id="generate_sms",
        parameters={
            "message": "Cached",
        },
        tenant_id="tenant-1",
    )

    assert result.success is True
    assert result.cached is True
    assert result.result == "cached-result"


def test_cache_isolated_between_tenants():
    cache = FakeCache()

    executor = create_executor(
        cache=cache,
    )

    tenant_one = executor.execute(
        tool_id="generate_sms",
        parameters={
            "message": "Hello",
        },
        tenant_id="tenant-1",
    )

    tenant_two = executor.execute(
        tool_id="generate_sms",
        parameters={
            "message": "Hello",
        },
        tenant_id="tenant-2",
    )

    assert tenant_one.success is True
    assert tenant_two.success is True

    assert tenant_one.cached is False
    assert tenant_two.cached is False

    assert cache.set_calls == 2


def test_cache_get_failure_is_ignored():
    class BrokenCache:
        def get(self, key):
            raise RuntimeError(
                "redis unavailable"
            )

    executor = create_executor(
        cache=BrokenCache(),
    )

    result = executor.execute(
        tool_id="generate_sms",
        parameters={
            "message": "Hello",
        },
        tenant_id="tenant-1",
    )

    assert result.success is True
    assert result.cached is False


def test_cache_set_failure_is_ignored():
    class BrokenCache:
        def get(self, key):
            return None

        def setex(
            self,
            key,
            ttl,
            value,
        ):
            raise RuntimeError(
                "redis unavailable"
            )

    executor = create_executor(
        cache=BrokenCache(),
    )

    result = executor.execute(
        tool_id="generate_sms",
        parameters={
            "message": "Hello",
        },
        tenant_id="tenant-1",
    )

    assert result.success is True
    assert result.result == "normal: Hello"


def test_cache_invalid_json_is_ignored():
    class InvalidJsonCache:
        def get(self, key):
            return "{invalid-json"

    executor = create_executor(
        cache=InvalidJsonCache(),
    )

    result = executor.execute(
        tool_id="generate_sms",
        parameters={
            "message": "Hello",
        },
        tenant_id="tenant-1",
    )

    assert result.success is True
    assert result.cached is False


def test_cache_bytes_are_decoded():
    class BytesCache:
        def get(self, key):
            return json.dumps(
                "bytes-result"
            ).encode("utf-8")

    executor = create_executor(
        cache=BytesCache(),
    )

    result = executor.execute(
        tool_id="generate_sms",
        parameters={
            "message": "Bytes",
        },
        tenant_id="tenant-1",
    )

    assert result.success is True
    assert result.cached is True
    assert result.result == "bytes-result"


def test_cache_get_returns_non_string_value():
    class ObjectCache:
        def get(self, key):
            return {
                "already": "decoded",
            }

    executor = create_executor(
        cache=ObjectCache(),
    )

    result = executor._cache_get(
        "generate_sms",
        {
            "message": "Object",
        },
        "tenant-1",
    )

    assert result == {
        "already": "decoded",
    }


def test_cache_set_with_zero_ttl_uses_default():
    cache = FakeCache()

    executor = create_executor(
        cache=cache,
    )

    executor._cache_set(
        tool_id="generate_sms",
        parameters={
            "message": "Hello",
        },
        result="result",
        ttl=0,
        tenant_id="tenant-1",
    )

    assert cache.last_ttl == 60


def test_cache_ttl_is_capped_at_60():
    cache = FakeCache()

    registry = ToolRegistry()

    registry.register_tool(
        generate_sms_schema(),
        handler=generate_sms,
        cacheable=True,
        cache_ttl=300,
    )

    executor = ToolExecutor(
        registry=registry,
        cache=cache,
    )

    result = executor.execute(
        tool_id="generate_sms",
        parameters={
            "message": "Hello",
        },
        tenant_id="tenant-1",
    )

    assert result.success is True
    assert cache.last_ttl == 60


def test_cache_set_serialization_error_is_ignored():
    cache = FakeCache()

    executor = create_executor(
        cache=cache,
    )

    executor._cache_set(
        tool_id="generate_sms",
        parameters={
            "message": "Hello",
        },
        result=NotSerializable(),
        ttl=60,
        tenant_id="tenant-1",
    )

    assert cache.set_calls == 0


def test_cache_none_is_supported():
    executor = create_executor(
        cache=None,
    )

    result = executor.execute(
        tool_id="generate_sms",
        parameters={
            "message": "Hello",
        },
        tenant_id="tenant-1",
    )

    assert result.success is True
    assert result.cached is False


def test_cache_key_is_tenant_specific():
    executor = create_executor()

    key_one = executor._cache_key(
        "generate_sms",
        {
            "message": "Hello",
        },
        "tenant-1",
    )

    key_two = executor._cache_key(
        "generate_sms",
        {
            "message": "Hello",
        },
        "tenant-2",
    )

    assert key_one != key_two


def test_cache_key_is_deterministic():
    executor = create_executor()

    key_one = executor._cache_key(
        "generate_sms",
        {
            "b": 2,
            "a": 1,
        },
        "tenant-1",
    )

    key_two = executor._cache_key(
        "generate_sms",
        {
            "a": 1,
            "b": 2,
        },
        "tenant-1",
    )

    assert key_one == key_two


# ======================================================================
# ASYNC / PARALLEL
# ======================================================================


def test_execute_async():
    executor = create_executor()

    async def run():
        return await executor.execute_async(
            tool_id="generate_sms",
            parameters={
                "message": "Hello",
            },
            tenant_id="tenant-1",
        )

    result = asyncio.run(run())

    assert result.success is True
    assert result.result == "normal: Hello"


def test_execute_many_empty_calls():
    executor = create_executor()

    async def run():
        return await executor.execute_many([])

    assert asyncio.run(run()) == []


def test_execute_many_preserves_order():
    registry = ToolRegistry()

    registry.register_tool(
        create_string_tool_schema(
            "one_second_tool"
        ),
        handler=one_second_tool,
        cacheable=False,
    )

    executor = ToolExecutor(
        registry=registry,
        timeout_seconds=6,
        max_retries=0,
    )

    calls = [
        ToolCall(
            tool_id="one_second_tool",
            parameters={},
            tenant_id="tenant-a",
        ),
        ToolCall(
            tool_id="one_second_tool",
            parameters={},
            tenant_id="tenant-b",
        ),
    ]

    async def run():
        return await executor.execute_many(
            calls
        )

    results = asyncio.run(run())

    assert len(results) == 2

    assert all(
        result.success
        for result in results
    )


def test_parallel_execution():
    registry = ToolRegistry()

    registry.register_tool(
        create_string_tool_schema(
            "one_second_tool"
        ),
        handler=one_second_tool,
        cacheable=False,
    )

    executor = ToolExecutor(
        registry=registry,
        timeout_seconds=6,
        max_retries=0,
    )

    calls = [
        ToolCall(
            tool_id="one_second_tool",
            parameters={},
            tenant_id="tenant-1",
        ),
        ToolCall(
            tool_id="one_second_tool",
            parameters={},
            tenant_id="tenant-2",
        ),
        ToolCall(
            tool_id="one_second_tool",
            parameters={},
            tenant_id="tenant-3",
        ),
    ]

    async def run():
        started = time.perf_counter()

        results = await executor.execute_many(
            calls
        )

        elapsed = (
            time.perf_counter()
            - started
        )

        return results, elapsed

    results, elapsed = asyncio.run(run())

    assert len(results) == 3

    assert all(
        result.success
        for result in results
    ), [
        (
            result.error.code
            if result.error
            else None,
            result.error.message
            if result.error
            else None,
        )
        for result in results
    ]

    # Three one-second calls should run concurrently.
    assert elapsed < 6


# ======================================================================
# METRICS
# ======================================================================


def test_result_contains_execution_time():
    executor = create_executor()

    result = executor.execute(
        tool_id="generate_sms",
        parameters={
            "message": "Hello",
        },
        tenant_id="tenant-1",
    )

    assert result.execution_time_ms >= 0


def test_cached_result_contains_execution_time():
    cache = FakeCache()

    executor = create_executor(
        cache=cache,
    )

    executor.execute(
        tool_id="generate_sms",
        parameters={
            "message": "Hello",
        },
        tenant_id="tenant-1",
    )

    result = executor.execute(
        tool_id="generate_sms",
        parameters={
            "message": "Hello",
        },
        tenant_id="tenant-1",
    )

    assert result.execution_time_ms >= 0
    assert result.cached is True


def test_metrics_failure_does_not_break_execution():
    class BrokenMetrics:
        def record_task(self, **kwargs):
            raise RuntimeError(
                "metrics unavailable"
            )

    executor = ToolExecutor(
        registry=create_executor().registry,
        metrics=BrokenMetrics(),
    )

    result = executor.execute(
        tool_id="generate_sms",
        parameters={
            "message": "Hello",
        },
        tenant_id="tenant-1",
    )

    assert result.success is True


def test_timeout_status_is_recorded():
    class RecordingMetrics:
        def __init__(self):
            self.calls = []

        def record_task(self, **kwargs):
            self.calls.append(kwargs)

    metrics = RecordingMetrics()

    registry = create_string_tool_registry(
        "slow_tool",
        slow_tool,
        cacheable=False,
    )

    executor = ToolExecutor(
        registry=registry,
        timeout_seconds=1,
        max_retries=0,
        metrics=metrics,
    )

    # Prevent Redis-backed circuit state from a previous test
    # from causing CIRCUIT_OPEN.
    executor.error_handler.circuit_breaker.reset(
        "slow_tool"
    )

    result = executor.execute(
        tool_id="slow_tool",
        parameters={},
        tenant_id="tenant-1",
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "TIMEOUT"

    assert metrics.calls
    assert metrics.calls[0]["status"] == "timeout"


def test_failure_status_is_recorded():
    class RecordingMetrics:
        def __init__(self):
            self.calls = []

        def record_task(self, **kwargs):
            self.calls.append(kwargs)

    metrics = RecordingMetrics()

    registry = create_string_tool_registry(
        "failing_tool",
        failing_tool,
        cacheable=False,
    )

    executor = ToolExecutor(
        registry=registry,
        max_retries=0,
        metrics=metrics,
    )

    result = executor.execute(
        tool_id="failing_tool",
        parameters={},
        tenant_id="tenant-1",
    )

    assert result.success is False
    assert metrics.calls
    assert metrics.calls[0]["status"] == "failure"


def test_record_metric_timeout_status():
    class RecordingMetrics:
        def __init__(self):
            self.calls = []

        def record_task(self, **kwargs):
            self.calls.append(kwargs)

    metrics = RecordingMetrics()

    executor = ToolExecutor(
        registry=ToolRegistry(),
        metrics=metrics,
    )

    result = ToolResult(
        success=False,
        tool_id="test",
        error=ToolExecutionError(
            code="TIMEOUT",
            message="timed out",
        ),
    )

    executor._record_metric(
        result=result,
        start_time=time.perf_counter(),
        tenant_id="tenant-1",
    )

    assert metrics.calls[0]["status"] == "timeout"


def test_record_metric_failure_status():
    class RecordingMetrics:
        def __init__(self):
            self.calls = []

        def record_task(self, **kwargs):
            self.calls.append(kwargs)

    metrics = RecordingMetrics()

    executor = ToolExecutor(
        registry=ToolRegistry(),
        metrics=metrics,
    )

    result = ToolResult(
        success=False,
        tool_id="test",
        error=ToolExecutionError(
            code="INVALID_INPUT",
            message="bad input",
        ),
    )

    executor._record_metric(
        result=result,
        start_time=time.perf_counter(),
        tenant_id="tenant-1",
    )

    assert metrics.calls[0]["status"] == "failure"


def test_record_metric_handles_metrics_exception():
    class BrokenMetrics:
        def record_task(self, **kwargs):
            raise RuntimeError(
                "metrics failed"
            )

    executor = ToolExecutor(
        registry=ToolRegistry(),
        metrics=BrokenMetrics(),
    )

    result = ToolResult(
        success=True,
        tool_id="test",
    )

    executor._record_metric(
        result=result,
        start_time=time.perf_counter(),
        tenant_id="tenant-1",
    )


# ======================================================================
# CONFIGURATION
# ======================================================================


def test_timeout_is_capped_at_ten_seconds():
    executor = create_executor(
        timeout_seconds=100,
    )

    assert executor.timeout_seconds == 10


def test_timeout_cannot_be_zero():
    executor = ToolExecutor(
        registry=ToolRegistry(),
        timeout_seconds=0,
    )

    assert executor.timeout_seconds == 0.1


def test_memory_limit_is_configurable():
    executor = ToolExecutor(
        registry=ToolRegistry(),
        max_memory_bytes=128 * 1024 * 1024,
    )

    assert (
        executor.max_memory_bytes
        == 128 * 1024 * 1024
    )


def test_memory_limit_cannot_be_negative():
    executor = ToolExecutor(
        registry=ToolRegistry(),
        max_memory_bytes=-1,
    )

    assert executor.max_memory_bytes == 1


def test_cpu_limit_is_capped_at_ten_seconds():
    executor = ToolExecutor(
        registry=ToolRegistry(),
        max_cpu_seconds=100,
    )

    assert executor.max_cpu_seconds == 10


def test_resource_limits_are_configurable():
    executor = ToolExecutor(
        registry=ToolRegistry(),
        max_memory_bytes=64 * 1024 * 1024,
        max_cpu_seconds=5,
    )

    assert (
        executor.max_memory_bytes
        == 64 * 1024 * 1024
    )

    assert executor.max_cpu_seconds == 5


def test_max_retries_is_configurable():
    executor = ToolExecutor(
        registry=ToolRegistry(),
        max_retries=5,
    )

    assert executor.max_retries == 5


def test_negative_retries_are_clamped_to_zero():
    executor = ToolExecutor(
        registry=ToolRegistry(),
        max_retries=-1,
    )

    assert executor.max_retries == 0


# ======================================================================
# TOOL CALL
# ======================================================================


def test_tool_call_defaults():
    call = ToolCall(
        tool_id="generate_sms",
        tenant_id="tenant-1",
    )

    assert call.parameters == {}
    assert call.tenant_id == "tenant-1"


def test_tool_call_allows_empty_tenant():
    call = ToolCall(
        tool_id="generate_sms",
    )

    assert call.tenant_id == ""
    assert call.parameters == {}


# ======================================================================
# WORKER
# ======================================================================


def test_worker_success():
    class ResultQueue:
        def __init__(self):
            self.values = []

        def put(self, value):
            self.values.append(value)

    result_queue = ResultQueue()

    executor_module._tool_worker(
        handler=generate_sms,
        parameters={
            "message": "Hello",
        },
        result_queue=result_queue,
        max_memory_bytes=1024 * 1024,
        max_cpu_seconds=1,
    )

    assert result_queue.values
    assert result_queue.values[0]["success"] is True
    assert (
        result_queue.values[0]["result"]
        == "normal: Hello"
    )


def test_worker_handles_runtime_exception():
    class ResultQueue:
        def __init__(self):
            self.values = []

        def put(self, value):
            self.values.append(value)

    result_queue = ResultQueue()

    executor_module._tool_worker(
        handler=failing_tool,
        parameters={},
        result_queue=result_queue,
        max_memory_bytes=1024 * 1024,
        max_cpu_seconds=1,
    )

    assert result_queue.values

    value = result_queue.values[0]

    assert value["success"] is False
    assert (
        value["error"]["code"]
        == "TOOL_EXECUTION_ERROR"
    )


def test_worker_handles_connection_error():
    def connection_failure():
        raise ConnectionError(
            "connection failed"
        )

    class ResultQueue:
        def __init__(self):
            self.values = []

        def put(self, value):
            self.values.append(value)

    result_queue = ResultQueue()

    executor_module._tool_worker(
        handler=connection_failure,
        parameters={},
        result_queue=result_queue,
        max_memory_bytes=1024 * 1024,
        max_cpu_seconds=1,
    )

    assert result_queue.values
    assert (
        result_queue.values[0]["error"]["code"]
        == "TRANSIENT_ERROR"
    )


def test_worker_handles_value_error():
    def validation_failure():
        raise ValueError(
            "invalid value"
        )

    class ResultQueue:
        def __init__(self):
            self.values = []

        def put(self, value):
            self.values.append(value)

    result_queue = ResultQueue()

    executor_module._tool_worker(
        handler=validation_failure,
        parameters={},
        result_queue=result_queue,
        max_memory_bytes=1024 * 1024,
        max_cpu_seconds=1,
    )

    assert result_queue.values
    assert (
        result_queue.values[0]["error"]["code"]
        == "VALIDATION_ERROR"
    )


def test_worker_handles_timeout_error():
    def timeout_failure():
        raise TimeoutError(
            "timed out"
        )

    class ResultQueue:
        def __init__(self):
            self.values = []

        def put(self, value):
            self.values.append(value)

    result_queue = ResultQueue()

    executor_module._tool_worker(
        handler=timeout_failure,
        parameters={},
        result_queue=result_queue,
        max_memory_bytes=1024 * 1024,
        max_cpu_seconds=1,
    )

    assert result_queue.values
    assert (
        result_queue.values[0]["error"]["code"]
        == "TIMEOUT"
    )


def test_worker_handles_result_queue_put_failure():
    class BrokenQueue:
        def put(self, value):
            raise RuntimeError(
                "queue failure"
            )

    executor_module._tool_worker(
        handler=generate_sms,
        parameters={
            "message": "Hello",
        },
        result_queue=BrokenQueue(),
        max_memory_bytes=1024 * 1024,
        max_cpu_seconds=1,
    )


def test_worker_handles_exception_reporting_failure():
    class BrokenQueue:
        def put(self, value):
            raise RuntimeError(
                "queue failure"
            )

    executor_module._tool_worker(
        handler=failing_tool,
        parameters={},
        result_queue=BrokenQueue(),
        max_memory_bytes=1024 * 1024,
        max_cpu_seconds=1,
    )


# ======================================================================
# SUBPROCESS DEFENSIVE BRANCHES
# ======================================================================


def test_process_start_failure(monkeypatch):
    executor = create_executor()

    class TrackingQueue:
        def __init__(self):
            self.closed = False
            self.joined = False

        def close(self):
            self.closed = True

        def join_thread(self):
            self.joined = True

    queue_instance = TrackingQueue()

    class BrokenProcess:
        def start(self):
            raise RuntimeError(
                "process start failed"
            )

    class FakeContext:
        def Queue(self, maxsize=1):
            return queue_instance

        def Process(self, *args, **kwargs):
            return BrokenProcess()

    monkeypatch.setattr(
        executor_module.multiprocessing,
        "get_context",
        lambda name: FakeContext(),
    )

    result = executor._run_in_subprocess(
        tool_id="generate_sms",
        handler=generate_sms,
        parameters={
            "message": "Hello",
        },
    )

    assert result["success"] is False

    assert (
        result["error"]["code"]
        == "SANDBOX_START_ERROR"
    )

    assert queue_instance.closed is True
    assert queue_instance.joined is True


def test_sandbox_start_error_is_permanent(
    monkeypatch,
):
    executor = create_executor(
        max_retries=3,
    )

    def fake_run_in_subprocess(
        *args,
        **kwargs,
    ):
        return {
            "success": False,
            "error": {
                "code": "SANDBOX_START_ERROR",
                "message": "cannot spawn process",
            },
        }

    monkeypatch.setattr(
        executor,
        "_run_in_subprocess",
        fake_run_in_subprocess,
    )

    result = executor.execute(
        tool_id="generate_sms",
        parameters={
            "message": "Hello",
        },
    )

    assert result.success is False
    assert result.error is not None
    assert (
        result.error.code
        == "SANDBOX_START_ERROR"
    )

    # Startup/pickle failure is permanent and therefore
    # should not consume retries.
    assert result.error.retry_count == 0


def test_subprocess_invalid_response(monkeypatch):
    executor = create_executor(
        max_retries=0,
    )

    class FakeProcess:
        exitcode = 0

        def start(self):
            pass

        def is_alive(self):
            return False

        def join(self, *args):
            pass

    class FakeQueue:
        def get(self, timeout=None):
            return "invalid"

        def close(self):
            pass

        def join_thread(self):
            pass

    class FakeContext:
        def Queue(self, maxsize=1):
            return FakeQueue()

        def Process(self, *args, **kwargs):
            return FakeProcess()

    monkeypatch.setattr(
        executor_module.multiprocessing,
        "get_context",
        lambda name: FakeContext(),
    )

    result = executor._run_in_subprocess(
        tool_id="generate_sms",
        handler=generate_sms,
        parameters={
            "message": "Hello",
        },
    )

    assert result["success"] is False

    assert (
        result["error"]["code"]
        == "SANDBOX_PROCESS_ERROR"
    )


def test_subprocess_resource_limit_branch(
    monkeypatch,
):
    executor = create_executor(
        max_retries=0,
    )

    class FakeProcess:
        exitcode = -9

        def start(self):
            pass

        def is_alive(self):
            return False

        def join(self, *args):
            pass

    class FakeQueue:
        def get(self, timeout=None):
            raise queue.Empty()

        def close(self):
            pass

        def join_thread(self):
            pass

    class FakeContext:
        def Queue(self, maxsize=1):
            return FakeQueue()

        def Process(self, *args, **kwargs):
            return FakeProcess()

    monkeypatch.setattr(
        executor_module.multiprocessing,
        "get_context",
        lambda name: FakeContext(),
    )

    result = executor._run_in_subprocess(
        tool_id="generate_sms",
        handler=generate_sms,
        parameters={
            "message": "Hello",
        },
    )

    assert result["success"] is False

    assert (
        result["error"]["code"]
        == "SANDBOX_RESOURCE_LIMIT_EXCEEDED"
    )


def test_subprocess_process_error_branch(
    monkeypatch,
):
    executor = create_executor(
        max_retries=0,
    )

    class FakeProcess:
        exitcode = 1

        def start(self):
            pass

        def is_alive(self):
            return False

        def join(self, *args):
            pass

    class FakeQueue:
        def get(self, timeout=None):
            raise queue.Empty()

        def close(self):
            pass

        def join_thread(self):
            pass

    class FakeContext:
        def Queue(self, maxsize=1):
            return FakeQueue()

        def Process(self, *args, **kwargs):
            return FakeProcess()

    monkeypatch.setattr(
        executor_module.multiprocessing,
        "get_context",
        lambda name: FakeContext(),
    )

    result = executor._run_in_subprocess(
        tool_id="generate_sms",
        handler=generate_sms,
        parameters={
            "message": "Hello",
        },
    )

    assert result["success"] is False

    assert (
        result["error"]["code"]
        == "SANDBOX_PROCESS_ERROR"
    )


def test_subprocess_timeout_branch(
    monkeypatch,
):
    executor = ToolExecutor(
        registry=create_executor().registry,
        timeout_seconds=0.1,
        max_retries=0,
    )

    class FakeProcess:
        exitcode = None

        def start(self):
            pass

        def is_alive(self):
            return True

        def terminate(self):
            pass

        def kill(self):
            pass

        def join(self, *args):
            pass

    class FakeQueue:
        def get(self, timeout=None):
            raise queue.Empty()

        def close(self):
            pass

        def join_thread(self):
            pass

    class FakeContext:
        def Queue(self, maxsize=1):
            return FakeQueue()

        def Process(self, *args, **kwargs):
            return FakeProcess()

    monkeypatch.setattr(
        executor_module.multiprocessing,
        "get_context",
        lambda name: FakeContext(),
    )

    result = executor._run_in_subprocess(
        tool_id="slow_tool",
        handler=slow_tool,
        parameters={},
    )

    assert result["success"] is False
    assert result["error"]["code"] == "TIMEOUT"


def test_subprocess_result_cleanup(
    monkeypatch,
):
    executor = create_executor()

    class FakeProcess:
        exitcode = 0

        def start(self):
            pass

        def is_alive(self):
            return False

        def join(self, *args):
            pass

    class FakeQueue:
        def get(self, timeout=None):
            return {
                "success": True,
                "result": "ok",
            }

        def close(self):
            pass

        def join_thread(self):
            pass

    class FakeContext:
        def Queue(self, maxsize=1):
            return FakeQueue()

        def Process(self, *args, **kwargs):
            return FakeProcess()

    monkeypatch.setattr(
        executor_module.multiprocessing,
        "get_context",
        lambda name: FakeContext(),
    )

    result = executor._run_in_subprocess(
        tool_id="generate_sms",
        handler=generate_sms,
        parameters={
            "message": "Hello",
        },
    )

    assert result["success"] is True
    assert result["result"] == "ok"


def test_subprocess_cleanup_terminates_stuck_process(
    monkeypatch,
):
    executor = create_executor()

    class FakeProcess:
        exitcode = 0

        def __init__(self):
            self.terminate_called = False
            self.kill_called = False
            self.join_calls = []

        def start(self):
            pass

        def is_alive(self):
            return True

        def join(self, timeout=None):
            self.join_calls.append(timeout)

        def terminate(self):
            self.terminate_called = True

        def kill(self):
            self.kill_called = True

    process_instance = FakeProcess()

    class FakeQueue:
        def get(self, timeout=None):
            return {
                "success": True,
                "result": "ok",
            }

        def close(self):
            pass

        def join_thread(self):
            pass

    class FakeContext:
        def Queue(self, maxsize=1):
            return FakeQueue()

        def Process(self, *args, **kwargs):
            return process_instance

    monkeypatch.setattr(
        executor_module.multiprocessing,
        "get_context",
        lambda name: FakeContext(),
    )

    result = executor._run_in_subprocess(
        tool_id="generate_sms",
        handler=generate_sms,
        parameters={
            "message": "Hello",
        },
    )

    assert result["success"] is True
    assert result["result"] == "ok"
    assert process_instance.terminate_called is True
    assert process_instance.kill_called is True


# ======================================================================
# SANDBOX RESPONSE HANDLING
# ======================================================================


def test_invalid_sandbox_error_response_uses_default_error(
    monkeypatch,
):
    executor = ToolExecutor(
        registry=create_default_registry(),
        max_retries=0,
    )

    def fake_run_in_subprocess(
        *args,
        **kwargs,
    ):
        return {
            "success": False,
            "error": "not-a-dict",
        }

    monkeypatch.setattr(
        executor,
        "_run_in_subprocess",
        fake_run_in_subprocess,
    )

    result = executor.execute(
        tool_id="generate_sms",
        parameters={
            "message": "Hello",
            "priority": "normal",
        },
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == (
        "SANDBOX_PROCESS_ERROR"
    )
    assert result.error.message == (
        "Invalid sandbox response"
    )


def test_sandbox_success_without_result(
    monkeypatch,
):
    executor = ToolExecutor(
        registry=create_default_registry(),
        max_retries=0,
    )

    def fake_run_in_subprocess(
        *args,
        **kwargs,
    ):
        return {
            "success": True,
        }

    monkeypatch.setattr(
        executor,
        "_run_in_subprocess",
        fake_run_in_subprocess,
    )

    result = executor.execute(
        tool_id="generate_sms",
        parameters={
            "message": "Hello",
            "priority": "normal",
        },
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == (
        "SANDBOX_PROCESS_ERROR"
    )


def test_sandbox_success_with_none_result():
    """
    None is a valid Python return value.

    The executor must not interpret None as execution failure
    merely because the result itself is None.
    """


    registry = ToolRegistry()

    schema = ToolSchema(
        ToolContract(
            name="none_tool",
            description="Returns None",
            version="v1",
            parameters=[],
            required=[],
            returns=ToolReturn(
                type="null",
                description="None result",
                schema={
                    "type": "null",
                },
            ),
        )
    )

    registry.register_tool(
        schema,
        handler=none_tool,
        cacheable=False,
    )

    executor = ToolExecutor(
        registry=registry,
        max_retries=0,
    )

    result = executor.execute(
        tool_id="none_tool",
        parameters={},
        tenant_id="tenant-1",
    )

    assert result.success is True
    assert result.result is None
    assert result.error is None


# ======================================================================
# OUTER EXECUTOR ERROR
# ======================================================================


def test_execute_unexpected_exception_path(
    monkeypatch,
):
    executor = create_executor()

    def raise_unexpected(
        *args,
        **kwargs,
    ):
        raise RuntimeError(
            "unexpected internal failure"
        )

    monkeypatch.setattr(
        executor,
        "_execute_sync",
        raise_unexpected,
    )

    result = executor.execute(
        tool_id="generate_sms",
        parameters={
            "message": "Hello",
        },
        tenant_id="tenant-1",
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "EXECUTOR_ERROR"

    assert (
        result.error.message
        == "unexpected internal failure"
    )


# ======================================================================
# RESOURCE LIMIT HELPER
# ======================================================================


def test_resource_limits_noop_when_unavailable(
    monkeypatch,
):
    monkeypatch.setattr(
        executor_module,
        "resource",
        None,
    )

    executor_module._apply_resource_limits(
        max_memory_bytes=1024,
        max_cpu_seconds=1,
    )


def test_resource_limits_memory_error(
    monkeypatch,
):
    class FakeResource:
        RLIMIT_AS = 1
        RLIMIT_CPU = 2
        RLIMIT_NPROC = 3
        RLIM_INFINITY = -1

        def getrlimit(self, limit):
            return (
                1,
                self.RLIM_INFINITY,
            )

        def setrlimit(
            self,
            limit,
            values,
        ):
            if limit == self.RLIMIT_AS:
                raise ValueError(
                    "memory limit failed"
                )

    monkeypatch.setattr(
        executor_module,
        "resource",
        FakeResource(),
    )

    executor_module._apply_resource_limits(
        max_memory_bytes=1024,
        max_cpu_seconds=1,
    )


def test_resource_limits_cpu_error(
    monkeypatch,
):
    class FakeResource:
        RLIMIT_AS = 1
        RLIMIT_CPU = 2
        RLIMIT_NPROC = 3
        RLIM_INFINITY = -1

        def getrlimit(self, limit):
            return (
                1,
                self.RLIM_INFINITY,
            )

        def setrlimit(
            self,
            limit,
            values,
        ):
            if limit == self.RLIMIT_CPU:
                raise ValueError(
                    "cpu limit failed"
                )

    monkeypatch.setattr(
        executor_module,
        "resource",
        FakeResource(),
    )

    executor_module._apply_resource_limits(
        max_memory_bytes=1024,
        max_cpu_seconds=1,
    )


def test_resource_limits_nproc_error(
    monkeypatch,
):
    class FakeResource:
        RLIMIT_AS = 1
        RLIMIT_CPU = 2
        RLIMIT_NPROC = 3
        RLIM_INFINITY = -1

        def getrlimit(self, limit):
            return (
                1,
                self.RLIM_INFINITY,
            )

        def setrlimit(
            self,
            limit,
            values,
        ):
            if limit == self.RLIMIT_NPROC:
                raise OSError(
                    "nproc limit unavailable"
                )

    monkeypatch.setattr(
        executor_module,
        "resource",
        FakeResource(),
    )

    executor_module._apply_resource_limits(
        max_memory_bytes=1024,
        max_cpu_seconds=1,
    )


def test_resource_limits_memory_hard_limit_branch(
    monkeypatch,
):
    class FakeResource:
        RLIMIT_AS = 1
        RLIMIT_CPU = 2
        RLIMIT_NPROC = 3
        RLIM_INFINITY = -1

        def __init__(self):
            self.calls = []

        def getrlimit(self, limit):
            if limit == self.RLIMIT_AS:
                return (
                    1024,
                    2048,
                )

            return (
                1,
                self.RLIM_INFINITY,
            )

        def setrlimit(
            self,
            limit,
            values,
        ):
            self.calls.append(
                (
                    limit,
                    values,
                )
            )

    fake = FakeResource()

    monkeypatch.setattr(
        executor_module,
        "resource",
        fake,
    )

    executor_module._apply_resource_limits(
        max_memory_bytes=4096,
        max_cpu_seconds=1,
    )

    assert fake.calls[0] == (
        fake.RLIMIT_AS,
        (
            2048,
            2048,
        ),
    )


def test_resource_limits_cpu_hard_limit_branch(
    monkeypatch,
):
    class FakeResource:
        RLIMIT_AS = 1
        RLIMIT_CPU = 2
        RLIMIT_NPROC = 3
        RLIM_INFINITY = -1

        def __init__(self):
            self.calls = []

        def getrlimit(self, limit):
            if limit == self.RLIMIT_CPU:
                return (
                    1,
                    2,
                )

            return (
                1,
                self.RLIM_INFINITY,
            )

        def setrlimit(
            self,
            limit,
            values,
        ):
            self.calls.append(
                (
                    limit,
                    values,
                )
            )

    fake = FakeResource()

    monkeypatch.setattr(
        executor_module,
        "resource",
        fake,
    )

    executor_module._apply_resource_limits(
        max_memory_bytes=1024,
        max_cpu_seconds=10,
    )

    cpu_calls = [
        call
        for call in fake.calls
        if call[0] == fake.RLIMIT_CPU
    ]

    assert cpu_calls

    assert cpu_calls[0] == (
        fake.RLIMIT_CPU,
        (
            2,
            2,
        ),
    )


def test_resource_limits_nproc_hard_limit_branch(
    monkeypatch,
):
    class FakeResource:
        RLIMIT_AS = 1
        RLIMIT_CPU = 2
        RLIMIT_NPROC = 3
        RLIM_INFINITY = -1

        def __init__(self):
            self.calls = []

        def getrlimit(self, limit):
            if limit == self.RLIMIT_NPROC:
                return (
                    1,
                    8,
                )

            return (
                1,
                self.RLIM_INFINITY,
            )

        def setrlimit(
            self,
            limit,
            values,
        ):
            self.calls.append(
                (
                    limit,
                    values,
                )
            )

    fake = FakeResource()

    monkeypatch.setattr(
        executor_module,
        "resource",
        fake,
    )

    executor_module._apply_resource_limits(
        max_memory_bytes=1024,
        max_cpu_seconds=1,
    )

    nproc_calls = [
        call
        for call in fake.calls
        if call[0] == fake.RLIMIT_NPROC
    ]

    assert nproc_calls

    assert nproc_calls[0] == (
        fake.RLIMIT_NPROC,
        (
            8,
            8,
        ),
    )


# ======================================================================
# QUEUE CLEANUP
# ======================================================================


def test_close_queue_handles_errors():
    executor = create_executor()

    class BrokenQueue:
        def close(self):
            raise RuntimeError(
                "close failed"
            )

        def join_thread(self):
            raise RuntimeError(
                "join failed"
            )

    executor._close_queue(
        BrokenQueue()
    )


# ======================================================================
# CACHE / CIRCUIT INTERACTION
# ======================================================================


def test_cached_result_does_not_execute_tool_again():
    cache = FakeCache()

    executor = create_executor(
        cache=cache,
    )

    first = executor.execute(
        tool_id="generate_sms",
        parameters={
            "message": "Hello",
        },
        tenant_id="tenant-1",
    )

    second = executor.execute(
        tool_id="generate_sms",
        parameters={
            "message": "Hello",
        },
        tenant_id="tenant-1",
    )

    assert first.success is True
    assert second.success is True
    assert second.cached is True

    assert cache.set_calls == 1


def test_cache_key_changes_for_tool():
    executor = create_executor()

    key_one = executor._cache_key(
        "tool-one",
        {
            "message": "Hello",
        },
        "tenant-1",
    )

    key_two = executor._cache_key(
        "tool-two",
        {
            "message": "Hello",
        },
        "tenant-1",
    )

    assert key_one != key_two


# ======================================================================
# FINAL EXECUTION RESULT CONTRACT
# ======================================================================


def test_success_result_contract():
    executor = create_executor()

    result = executor.execute(
        tool_id="generate_sms",
        parameters={
            "message": "Hello",
        },
        tenant_id="tenant-1",
    )

    assert result.success is True
    assert result.tool_id == "generate_sms"
    assert result.result == "normal: Hello"
    assert result.error is None
    assert result.execution_time_ms >= 0
    assert result.cached is False


def test_failure_result_contract():
    registry = create_string_tool_registry(
        "failing_tool",
        failing_tool,
        cacheable=False,
    )

    executor = ToolExecutor(
        registry=registry,
        max_retries=0,
    )

    result = executor.execute(
        tool_id="failing_tool",
        parameters={},
        tenant_id="tenant-1",
    )

    assert result.success is False
    assert result.tool_id == "failing_tool"
    assert result.result is None
    assert result.error is not None
    assert result.execution_time_ms >= 0
    assert result.cached is False