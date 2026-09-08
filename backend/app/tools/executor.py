from __future__ import annotations

import asyncio
import builtins
import hashlib
import json
import multiprocessing
import queue
import time
from typing import Any

try:
    import resource
except ImportError:  # pragma: no cover - Windows
    resource = None

from jsonschema import Draft202012Validator
from pydantic import BaseModel, Field

from app.runtime.metrics import (
    MetricsCollector,
    runtime_metrics_collector,
)
from app.tools.errors import (
    PermanentError,
    ToolError,
    ToolErrorHandler,
    TransientError,
    TimeoutError as ToolTimeoutError,
)
from app.tools.registry import (
    RegisteredTool,
    ToolRegistry,
)
from app.tools.validation import ToolInputValidator


# ============================================================
# RESULT MODELS
# ============================================================


class ToolExecutionError(BaseModel):
    """
    Structured error returned to callers.
    """

    code: str
    message: str

    tool_id: str | None = None

    parameters: dict[str, Any] = Field(
        default_factory=dict
    )

    retry_count: int = 0

    fallback_used: bool = False


class ToolResult(BaseModel):
    """
    Result of a tool execution.
    """

    success: bool

    tool_id: str

    result: Any | None = None

    error: ToolExecutionError | None = None

    execution_time_ms: float = 0.0

    cached: bool = False


class ToolCall(BaseModel):
    """
    Represents one tool invocation.
    """

    tool_id: str

    parameters: dict[str, Any] = Field(
        default_factory=dict
    )

    tenant_id: str = ""


# ============================================================
# RESOURCE LIMITS
# ============================================================


def _apply_resource_limits(
    max_memory_bytes: int,
    max_cpu_seconds: int,
) -> None:
    """
    Apply OS-level resource limits inside the child process.

    On Windows, resource is unavailable, so this is a no-op.
    """

    if resource is None:
        return

    # --------------------------------------------------------
    # Memory
    # --------------------------------------------------------

    if hasattr(resource, "RLIMIT_AS"):
        try:
            requested = max(
                1,
                int(max_memory_bytes),
            )

            _, current_hard = resource.getrlimit(
                resource.RLIMIT_AS
            )

            if current_hard != resource.RLIM_INFINITY:
                requested = min(
                    requested,
                    current_hard,
                )

            resource.setrlimit(
                resource.RLIMIT_AS,
                (
                    requested,
                    requested,
                ),
            )

        except (
            AttributeError,
            ValueError,
            OSError,
        ):
            pass

    # --------------------------------------------------------
    # CPU
    # --------------------------------------------------------

    if hasattr(resource, "RLIMIT_CPU"):
        try:
            requested = max(
                1,
                int(max_cpu_seconds),
            )

            _, current_hard = resource.getrlimit(
                resource.RLIMIT_CPU
            )

            if current_hard != resource.RLIM_INFINITY:
                requested = min(
                    requested,
                    current_hard,
                )

            resource.setrlimit(
                resource.RLIMIT_CPU,
                (
                    requested,
                    requested,
                ),
            )

        except (
            AttributeError,
            ValueError,
            OSError,
        ):
            pass

    # --------------------------------------------------------
    # Process count
    # --------------------------------------------------------

    if hasattr(resource, "RLIMIT_NPROC"):
        try:
            requested = 32

            _, current_hard = resource.getrlimit(
                resource.RLIMIT_NPROC
            )

            if current_hard != resource.RLIM_INFINITY:
                requested = min(
                    requested,
                    current_hard,
                )

            resource.setrlimit(
                resource.RLIMIT_NPROC,
                (
                    requested,
                    requested,
                ),
            )

        except (
            AttributeError,
            ValueError,
            OSError,
        ):
            pass


# ============================================================
# WORKER
# ============================================================


def _tool_worker(
    handler: Any,
    parameters: dict[str, Any],
    result_queue: Any,
    max_memory_bytes: int,
    max_cpu_seconds: int,
) -> None:
    """
    Execute a registered handler inside a separate process.

    Only Exception is caught intentionally. System-level
    BaseException subclasses such as KeyboardInterrupt and
    SystemExit should not be converted into tool failures.
    """

    _apply_resource_limits(
        max_memory_bytes=max_memory_bytes,
        max_cpu_seconds=max_cpu_seconds,
    )

    try:
        result = handler(
            **parameters
        )

        result_queue.put(
            {
                "success": True,
                "result": result,
            }
        )

    except Exception as exc:
        try:
            if isinstance(
                exc,
                (
                    builtins.TimeoutError,
                    ToolTimeoutError,
                ),
            ):
                code = "TIMEOUT"

            elif isinstance(
                exc,
                ConnectionError,
            ):
                code = "TRANSIENT_ERROR"

            elif isinstance(
                exc,
                ValueError,
            ):
                code = "VALIDATION_ERROR"

            else:
                code = "TOOL_EXECUTION_ERROR"

            result_queue.put(
                {
                    "success": False,
                    "error": {
                        "code": code,
                        "message": (
                            str(exc)
                            or "Tool execution failed"
                        ),
                    },
                }
            )

        except Exception:
            # The worker must never crash while trying
            # to report an error.
            pass


# ============================================================
# TOOL EXECUTOR
# ============================================================


class ToolExecutor:
    """
    Executes registered tools safely.

    Execution flow:

        Tool lookup
             |
             v
        Input validation
             |
             v
        Cache lookup
             |
             v
        Circuit breaker
             |
             v
        Subprocess execution
             |
             +---- success ------> Output validation
             |                         |
             |                         v
             |                    Serialization
             |                         |
             |                         v
             |                       Cache
             |                         |
             |                         v
             |                       Result
             |
             +---- transient ----> Retry
             |
             +---- permanent ----> Fallback
                                      |
                                      +--> Alternative tool
                                      |
                                      +--> Static value
                                      |
                                      +--> Structured error
    """

    MAX_TIMEOUT_SECONDS = 10

    DEFAULT_CACHE_TTL = 60

    DEFAULT_MAX_MEMORY_BYTES = (
        256 * 1024 * 1024
    )

    DEFAULT_MAX_CPU_SECONDS = 10

    def __init__(
        self,
        registry: ToolRegistry,
        validator: ToolInputValidator | None = None,
        cache: Any | None = None,
        timeout_seconds: float = MAX_TIMEOUT_SECONDS,
        metrics: MetricsCollector | None = None,
        max_memory_bytes: int = DEFAULT_MAX_MEMORY_BYTES,
        max_cpu_seconds: int = DEFAULT_MAX_CPU_SECONDS,
        error_handler: ToolErrorHandler | None = None,
        max_retries: int = 3,
    ) -> None:

        self.registry = registry

        self.validator = (
            validator
            if validator is not None
            else ToolInputValidator()
        )

        self.cache = cache

        self.metrics = (
            metrics
            if metrics is not None
            else runtime_metrics_collector
        )

        self.timeout_seconds = max(
            0.1,
            min(
                float(timeout_seconds),
                float(self.MAX_TIMEOUT_SECONDS),
            ),
        )

        self.max_memory_bytes = max(
            1,
            int(max_memory_bytes),
        )

        self.max_cpu_seconds = max(
            1,
            min(
                int(max_cpu_seconds),
                self.MAX_TIMEOUT_SECONDS,
            ),
        )

        self.max_retries = max(
            0,
            int(max_retries),
        )

        # ----------------------------------------------------
        # Redis
        # ----------------------------------------------------
        #
        # Different registry implementations may expose
        # Redis publicly as `redis` or internally as `_redis`.
        #

        redis_client = getattr(
            registry,
            "redis",
            None,
        )

        if redis_client is None:
            redis_client = getattr(
                registry,
                "_redis",
                None,
            )

        self.error_handler = (
            error_handler
            if error_handler is not None
            else ToolErrorHandler(
                redis_client=redis_client,
                max_retries=self.max_retries,
            )
        )

    # ========================================================
    # PUBLIC API
    # ========================================================

    def execute(
        self,
        tool_id: str,
        parameters: dict[str, Any],
        tenant_id: str = "",
    ) -> ToolResult:

        start_time = time.perf_counter()

        try:
            result = self._execute_sync(
                tool_id=tool_id,
                parameters=parameters,
                tenant_id=tenant_id,
                start_time=start_time,
            )

        except Exception as exc:
            result = self._error_result(
                tool_id=tool_id,
                code="EXECUTOR_ERROR",
                message=str(exc),
                start_time=start_time,
                parameters=parameters,
            )

        self._record_metric(
            result=result,
            start_time=start_time,
            tenant_id=tenant_id,
        )

        return result

    async def execute_async(
        self,
        tool_id: str,
        parameters: dict[str, Any],
        tenant_id: str = "",
    ) -> ToolResult:

        return await asyncio.to_thread(
            self.execute,
            tool_id,
            parameters,
            tenant_id,
        )

    async def execute_many(
        self,
        calls: list[ToolCall],
    ) -> list[ToolResult]:

        if not calls:
            return []

        return await asyncio.gather(
            *(
                self.execute_async(
                    tool_id=call.tool_id,
                    parameters=call.parameters,
                    tenant_id=call.tenant_id,
                )
                for call in calls
            )
        )

    # ========================================================
    # MAIN EXECUTION
    # ========================================================

    def _execute_sync(
        self,
        tool_id: str,
        parameters: dict[str, Any],
        tenant_id: str,
        start_time: float,
    ) -> ToolResult:

        # ----------------------------------------------------
        # Tool lookup
        # ----------------------------------------------------

        registered_tool = self.registry.get_tool(
            tool_id
        )

        if registered_tool is None:
            return self._error_result(
                tool_id=tool_id,
                code="TOOL_NOT_FOUND",
                message=(
                    f"Tool '{tool_id}' not found"
                ),
                start_time=start_time,
                parameters=parameters,
            )

        # ----------------------------------------------------
        # Handler lookup
        # ----------------------------------------------------

        if registered_tool.handler is None:
            return self._error_result(
                tool_id=tool_id,
                code="TOOL_HANDLER_NOT_FOUND",
                message=(
                    f"Tool '{tool_id}' "
                    "has no executable handler"
                ),
                start_time=start_time,
                parameters=parameters,
            )

        # ----------------------------------------------------
        # Input validation
        # ----------------------------------------------------

        validation_result = self._validate_input(
            registered_tool=registered_tool,
            parameters=parameters,
            tenant_id=tenant_id,
        )

        if not validation_result.valid:
            return self._error_result(
                tool_id=tool_id,
                code="INVALID_INPUT",
                message="; ".join(
                    validation_result.errors
                ),
                start_time=start_time,
                parameters=parameters,
            )

        validated_parameters = (
            validation_result.data or {}
        )

        # ----------------------------------------------------
        # Cache lookup
        # ----------------------------------------------------

        if registered_tool.cacheable:

            cached_result = self._cache_get(
                tool_id=tool_id,
                parameters=validated_parameters,
                tenant_id=tenant_id,
            )

            if cached_result is not None:
                return ToolResult(
                    success=True,
                    tool_id=tool_id,
                    result=cached_result,
                    execution_time_ms=(
                        self._elapsed_ms(
                            start_time
                        )
                    ),
                    cached=True,
                )

        # ----------------------------------------------------
        # Circuit breaker
        # ----------------------------------------------------

        if self.error_handler.circuit_breaker.is_open(
            tool_id
        ):
            return self._error_result(
                tool_id=tool_id,
                code="CIRCUIT_OPEN",
                message=(
                    f"Circuit breaker is open "
                    f"for tool '{tool_id}'"
                ),
                start_time=start_time,
                parameters=validated_parameters,
            )

        # ----------------------------------------------------
        # Execute with retry + fallback
        # ----------------------------------------------------

        (
            execution_result,
            execution_error,
            retry_count,
            fallback_used,
        ) = self._execute_with_error_handling(
            registered_tool=registered_tool,
            tool_id=tool_id,
            parameters=validated_parameters,
        )

        # ----------------------------------------------------
        # Final execution error
        # ----------------------------------------------------

        if execution_error is not None:
            return self._error_result(
                tool_id=tool_id,
                code=self._map_tool_error_code(
                    execution_error
                ),
                message=execution_error.message,
                start_time=start_time,
                parameters=validated_parameters,
                retry_count=retry_count,
                fallback_used=fallback_used,
            )

        # ----------------------------------------------------
        # Successful result
        # ----------------------------------------------------

        #
        # IMPORTANT:
        #
        # Do not check:
        #
        #     if result is not None
        #
        # because None is a valid Python return value.
        #

        if not isinstance(
            execution_result,
            dict,
        ):
            return self._error_result(
                tool_id=tool_id,
                code="SANDBOX_PROCESS_ERROR",
                message=(
                    "Tool execution returned "
                    "an invalid result envelope"
                ),
                start_time=start_time,
                parameters=validated_parameters,
                retry_count=retry_count,
                fallback_used=fallback_used,
            )

        if "result" not in execution_result:
            return self._error_result(
                tool_id=tool_id,
                code="SANDBOX_PROCESS_ERROR",
                message=(
                    "Tool execution returned "
                    "no result"
                ),
                start_time=start_time,
                parameters=validated_parameters,
                retry_count=retry_count,
                fallback_used=fallback_used,
            )

        result = execution_result["result"]

        # ----------------------------------------------------
        # Cache
        # ----------------------------------------------------

        if registered_tool.cacheable:
            self._cache_set(
                tool_id=tool_id,
                parameters=validated_parameters,
                result=result,
                ttl=registered_tool.cache_ttl,
                tenant_id=tenant_id,
            )

        # ----------------------------------------------------
        # Success
        # ----------------------------------------------------

        return ToolResult(
            success=True,
            tool_id=tool_id,
            result=result,
            execution_time_ms=(
                self._elapsed_ms(
                    start_time
                )
            ),
            cached=False,
        )

    # ========================================================
    # ERROR HANDLING
    # ========================================================

    def _execute_with_error_handling(
        self,
        registered_tool: RegisteredTool,
        tool_id: str,
        parameters: dict[str, Any],
    ) -> tuple[
        dict[str, Any] | None,
        ToolError | None,
        int,
        bool,
    ]:

        # ----------------------------------------------------
        # Primary operation
        # ----------------------------------------------------

        def operation() -> dict[str, Any]:

            sandbox_result = (
                self._run_in_subprocess(
                    tool_id=tool_id,
                    handler=registered_tool.handler,
                    parameters=parameters,
                )
            )

            if not isinstance(
                sandbox_result,
                dict,
            ):
                raise PermanentError(
                    "Invalid sandbox response",
                    tool_id=tool_id,
                    parameters=parameters,
                    code="SANDBOX_PROCESS_ERROR",
                )

            # ------------------------------------------------
            # Successful subprocess
            # ------------------------------------------------

            if sandbox_result.get(
                "success",
                False,
            ):
                if "result" not in sandbox_result:
                    raise PermanentError(
                        "Tool subprocess returned "
                        "no result",
                        tool_id=tool_id,
                        parameters=parameters,
                        code="SANDBOX_PROCESS_ERROR",
                    )

                result = sandbox_result["result"]

                # --------------------------------------------
                # Output validation
                # --------------------------------------------

                output_valid, output_error = (
                    self._validate_output(
                        registered_tool=registered_tool,
                        result=result,
                    )
                )

                if not output_valid:
                    raise PermanentError(
                        output_error,
                        tool_id=tool_id,
                        parameters=parameters,
                        code="OUTPUT_VALIDATION_ERROR",
                    )

                # --------------------------------------------
                # JSON serialization
                # --------------------------------------------

                try:
                    json.dumps(
                        result,
                        ensure_ascii=False,
                    )

                except (
                    TypeError,
                    ValueError,
                ) as exc:
                    raise PermanentError(
                        str(exc),
                        tool_id=tool_id,
                        parameters=parameters,
                        code="OUTPUT_SERIALIZATION_ERROR",
                    ) from exc

                return sandbox_result

            # ------------------------------------------------
            # Failed subprocess
            # ------------------------------------------------

            error_data = sandbox_result.get(
                "error"
            )

            if not isinstance(
                error_data,
                dict,
            ):
                raise PermanentError(
                    "Invalid sandbox response",
                    tool_id=tool_id,
                    parameters=parameters,
                    code="SANDBOX_PROCESS_ERROR",
                )

            code = str(
                error_data.get(
                    "code",
                    "SANDBOX_PROCESS_ERROR",
                )
            )

            message = str(
                error_data.get(
                    "message",
                    "Tool subprocess failed",
                )
            )

            # ------------------------------------------------
            # Timeout
            # ------------------------------------------------

            if code == "TIMEOUT":
                raise ToolTimeoutError(
                    message,
                    tool_id=tool_id,
                    parameters=parameters,
                    code="TIMEOUT",
                )

            # ------------------------------------------------
            # Transient errors
            # ------------------------------------------------

            if code in {
                "TRANSIENT_ERROR",
                "CONNECTION_ERROR",
                "NETWORK_ERROR",
                "RATE_LIMITED",
                "SERVICE_UNAVAILABLE",
            }:
                raise TransientError(
                    message,
                    tool_id=tool_id,
                    parameters=parameters,
                    code=code,
                )

            # ------------------------------------------------
            # Validation errors
            # ------------------------------------------------

            if code in {
                "VALIDATION_ERROR",
                "INVALID_INPUT",
            }:
                raise PermanentError(
                    message,
                    tool_id=tool_id,
                    parameters=parameters,
                    code=code,
                )

            # ------------------------------------------------
            # Sandbox start errors
            # ------------------------------------------------
            #
            # IMPORTANT:
            #
            # Process startup/pickling failures are generally
            # configuration/programming failures and should
            # NOT be retried.
            #

            if code == "SANDBOX_START_ERROR":
                raise PermanentError(
                    message,
                    tool_id=tool_id,
                    parameters=parameters,
                    code=code,
                )

            # ------------------------------------------------
            # Resource/process errors
            # ------------------------------------------------

            if code in {
                "SANDBOX_RESOURCE_LIMIT_EXCEEDED",
                "SANDBOX_PROCESS_ERROR",
            }:
                raise PermanentError(
                    message,
                    tool_id=tool_id,
                    parameters=parameters,
                    code=code,
                )

            # ------------------------------------------------
            # Tool execution errors
            # ------------------------------------------------

            if code == "TOOL_EXECUTION_ERROR":
                raise PermanentError(
                    message,
                    tool_id=tool_id,
                    parameters=parameters,
                    code=code,
                )

            # ------------------------------------------------
            # Unknown errors
            # ------------------------------------------------

            raise PermanentError(
                message,
                tool_id=tool_id,
                parameters=parameters,
                code=code,
            )

        # ----------------------------------------------------
        # Retry transient failures
        # ----------------------------------------------------

        (
            result,
            error,
            retry_count,
        ) = self.error_handler.execute_with_retry(
            operation,
            tool_id=tool_id,
            parameters=parameters,
        )

        # ----------------------------------------------------
        # Primary success
        # ----------------------------------------------------

        if error is None:
            return (
                result,
                None,
                retry_count,
                False,
            )

        # ----------------------------------------------------
        # Defensive error
        # ----------------------------------------------------

        if error is None:
            error = PermanentError(
                "Tool execution failed",
                tool_id=tool_id,
                parameters=parameters,
            )

        # ----------------------------------------------------
        # IMPORTANT:
        #
        # Fallback is only used for permanent failures.
        #
        # Transient failures have already exhausted their
        # retries. We do not automatically hide a retryable
        # failure behind a fallback.
        # ----------------------------------------------------

        if error.retryable:
            return (
                None,
                error,
                retry_count,
                False,
            )

        # ----------------------------------------------------
        # Alternative tool
        # ----------------------------------------------------

        fallback_tool_id = (
            registered_tool.fallback_tool_id
        )

        if fallback_tool_id:

            # Prevent direct self-reference.
            if fallback_tool_id != tool_id:

                fallback_tool = (
                    self.registry.get_tool(
                        fallback_tool_id
                    )
                )

                if (
                    fallback_tool is not None
                    and fallback_tool.handler is not None
                ):

                    def alternative_tool() -> Any:

                        fallback_result = (
                            self._run_in_subprocess(
                                tool_id=fallback_tool_id,
                                handler=fallback_tool.handler,
                                parameters=parameters,
                            )
                        )

                        if not isinstance(
                            fallback_result,
                            dict,
                        ):
                            raise PermanentError(
                                "Invalid fallback response",
                                tool_id=fallback_tool_id,
                                parameters=parameters,
                            )

                        if not fallback_result.get(
                            "success",
                            False,
                        ):
                            fallback_error = (
                                fallback_result.get(
                                    "error"
                                )
                            )

                            if isinstance(
                                fallback_error,
                                dict,
                            ):
                                raise PermanentError(
                                    str(
                                        fallback_error.get(
                                            "message",
                                            "Fallback tool failed",
                                        )
                                    ),
                                    tool_id=fallback_tool_id,
                                    parameters=parameters,
                                )

                            raise PermanentError(
                                "Fallback tool failed",
                                tool_id=fallback_tool_id,
                                parameters=parameters,
                            )

                        if "result" not in fallback_result:
                            raise PermanentError(
                                "Fallback tool returned "
                                "no result",
                                tool_id=fallback_tool_id,
                                parameters=parameters,
                            )

                        fallback_value = (
                            fallback_result["result"]
                        )

                        # Validate fallback output too.
                        output_valid, output_error = (
                            self._validate_output(
                                registered_tool=fallback_tool,
                                result=fallback_value,
                            )
                        )

                        if not output_valid:
                            raise PermanentError(
                                output_error,
                                tool_id=fallback_tool_id,
                                parameters=parameters,
                                code="OUTPUT_VALIDATION_ERROR",
                            )

                        # Validate serialization too.
                        try:
                            json.dumps(
                                fallback_value,
                                ensure_ascii=False,
                            )
                        except (
                            TypeError,
                            ValueError,
                        ) as exc:
                            raise PermanentError(
                                str(exc),
                                tool_id=fallback_tool_id,
                                parameters=parameters,
                                code="OUTPUT_SERIALIZATION_ERROR",
                            ) from exc

                        return fallback_value

                    (
                        fallback_success,
                        fallback_result,
                    ) = self._run_fallback(
                        error=error,
                        tool_id=tool_id,
                        parameters=parameters,
                        fallback_tool=alternative_tool,
                        fallback_tool_id=fallback_tool_id,
                        retry_count=retry_count,
                    )

                    if fallback_success:
                        return (
                            {
                                "success": True,
                                "result": fallback_result,
                            },
                            None,
                            retry_count,
                            True,
                        )

        # ----------------------------------------------------
        # Static fallback
        # ----------------------------------------------------

        (
            fallback_success,
            fallback_result,
        ) = self._run_fallback(
            error=error,
            tool_id=tool_id,
            parameters=parameters,
            fallback_value=(
                registered_tool.fallback_value
            ),
            has_fallback_value=(
                registered_tool.has_fallback_value
            ),
            retry_count=retry_count,
        )

        if fallback_success:
            return (
                {
                    "success": True,
                    "result": fallback_result,
                },
                None,
                retry_count,
                True,
            )

        # ----------------------------------------------------
        # Final failure
        # ----------------------------------------------------

        return (
            None,
            error,
            retry_count,
            False,
        )

    # ========================================================
    # FALLBACK
    # ========================================================

    def _run_fallback(
        self,
        error: ToolError,
        tool_id: str,
        parameters: dict[str, Any],
        fallback_tool: Any | None = None,
        fallback_tool_id: str | None = None,
        fallback_value: Any = None,
        has_fallback_value: bool = False,
        retry_count: int = 0,
    ) -> tuple[bool, Any]:

        try:

            result = self.error_handler.handle_error(
                tool_id=tool_id,
                error=error,
                parameters=parameters,
                fallback_tool=fallback_tool,
                fallback_tool_id=fallback_tool_id,
                fallback_value=fallback_value,
                has_fallback_value=has_fallback_value,
                retry_count=retry_count,
            )

            if result.success:
                return (
                    True,
                    result.result,
                )

            return (
                False,
                None,
            )

        except Exception:
            return (
                False,
                None,
            )

    # ========================================================
    # ERROR MAPPING
    # ========================================================

    @staticmethod
    def _map_tool_error_code(
        error: ToolError,
    ) -> str:

        code = getattr(
            error,
            "code",
            None,
        )

        if code:
            return str(code)

        if isinstance(
            error,
            ToolTimeoutError,
        ):
            return "TIMEOUT"

        if isinstance(
            error,
            TransientError,
        ):
            return "TRANSIENT_ERROR"

        if isinstance(
            error,
            PermanentError,
        ):
            return "PERMANENT_ERROR"

        return "TOOL_EXECUTION_ERROR"

    # ========================================================
    # INPUT VALIDATION
    # ========================================================

    def _validate_input(
        self,
        registered_tool: RegisteredTool,
        parameters: dict[str, Any],
        tenant_id: str,
    ):

        schema = (
            registered_tool
            .schema
            .generate_json_schema()
            [
                "parameters"
            ]
        )

        return self.validator.validate(
            parameters=parameters,
            schema=schema,
            tenant_id=tenant_id,
        )

    # ========================================================
    # OUTPUT VALIDATION
    # ========================================================

    def _validate_output(
        self,
        registered_tool: RegisteredTool,
        result: Any,
    ) -> tuple[bool, str]:

        return_schema = (
            registered_tool
            .schema
            .contract
            .returns
            .return_schema
        )

        try:

            validator = Draft202012Validator(
                return_schema
            )

            errors = sorted(
                validator.iter_errors(
                    result
                ),
                key=lambda error: list(
                    error.path
                ),
            )

            if errors:
                return (
                    False,
                    "; ".join(
                        error.message
                        for error in errors
                    ),
                )

        except Exception as exc:
            return (
                False,
                (
                    "Output schema validation "
                    f"failed: {exc}"
                ),
            )

        return True, ""

    # ========================================================
    # SUBPROCESS EXECUTION
    # ========================================================

    def _run_in_subprocess(
        self,
        tool_id: str,
        handler: Any,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:

        context = multiprocessing.get_context(
            "spawn"
        )

        result_queue = context.Queue(
            maxsize=1
        )

        process = context.Process(
            target=_tool_worker,
            args=(
                handler,
                parameters,
                result_queue,
                self.max_memory_bytes,
                self.max_cpu_seconds,
            ),
            daemon=True,
        )

        # ----------------------------------------------------
        # Start
        # ----------------------------------------------------

        try:
            process.start()

        except Exception as exc:

            self._close_queue(
                result_queue
            )

            return {
                "success": False,
                "error": {
                    "code": "SANDBOX_START_ERROR",
                    "message": str(exc),
                },
            }

        deadline = (
            time.monotonic()
            + self.timeout_seconds
        )

        child_result: dict[
            str,
            Any,
        ] | None = None

        # ----------------------------------------------------
        # Wait
        # ----------------------------------------------------

        while True:

            remaining = (
                deadline
                - time.monotonic()
            )

            if remaining <= 0:
                break

            try:

                received = result_queue.get(
                    timeout=remaining
                )

                if isinstance(
                    received,
                    dict,
                ):
                    child_result = received

                break

            except queue.Empty:

                if not process.is_alive():
                    break

        # ----------------------------------------------------
        # Timeout
        # ----------------------------------------------------

        if (
            child_result is None
            and process.is_alive()
        ):

            try:
                process.terminate()

            finally:

                process.join(2.0)

                if process.is_alive():

                    try:
                        process.kill()

                    finally:
                        process.join()

            self._close_queue(
                result_queue
            )

            return {
                "success": False,
                "error": {
                    "code": "TIMEOUT",
                    "message": (
                        f"Tool '{tool_id}' "
                        f"exceeded "
                        f"{self.timeout_seconds:g} "
                        "second timeout"
                    ),
                },
            }

        # ----------------------------------------------------
        # Reap child
        # ----------------------------------------------------

        if process.is_alive():

            process.join(1.0)

            if process.is_alive():

                try:
                    process.terminate()

                finally:

                    process.join(1.0)

                    if process.is_alive():

                        try:
                            process.kill()

                        finally:
                            process.join()

        exit_code = process.exitcode

        self._close_queue(
            result_queue
        )

        # ----------------------------------------------------
        # No result
        # ----------------------------------------------------

        if child_result is None:

            if (
                exit_code is not None
                and exit_code < 0
            ):
                return {
                    "success": False,
                    "error": {
                        "code": (
                            "SANDBOX_RESOURCE_LIMIT_EXCEEDED"
                        ),
                        "message": (
                            f"Tool '{tool_id}' "
                            "subprocess was "
                            "terminated by a "
                            "signal or resource "
                            "limit"
                        ),
                    },
                }

            return {
                "success": False,
                "error": {
                    "code": (
                        "SANDBOX_PROCESS_ERROR"
                    ),
                    "message": (
                        f"Tool '{tool_id}' "
                        "subprocess exited "
                        f"(code={exit_code}) "
                        "without returning "
                        "a result"
                    ),
                },
            }

        return child_result

    # ========================================================
    # QUEUE CLEANUP
    # ========================================================

    @staticmethod
    def _close_queue(
        result_queue: Any,
    ) -> None:

        try:
            result_queue.close()

        except Exception:
            pass

        try:
            result_queue.join_thread()

        except Exception:
            pass

    # ========================================================
    # CACHE
    # ========================================================

    def _cache_key(
        self,
        tool_id: str,
        parameters: dict[str, Any],
        tenant_id: str,
    ) -> str:

        serialized = json.dumps(
            parameters,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        )

        digest = hashlib.sha256(
            serialized.encode("utf-8")
        ).hexdigest()

        tenant_part = (
            tenant_id
            if tenant_id
            else "__notenant__"
        )

        return (
            "fieldops:tool:result:"
            f"{tenant_part}:"
            f"{tool_id}:"
            f"{digest}"
        )

    def _cache_get(
        self,
        tool_id: str,
        parameters: dict[str, Any],
        tenant_id: str,
    ) -> Any | None:

        if self.cache is None:
            return None

        try:

            key = self._cache_key(
                tool_id,
                parameters,
                tenant_id,
            )

            cached = self.cache.get(
                key
            )

            if cached is None:
                return None

            if isinstance(
                cached,
                bytes,
            ):
                cached = cached.decode(
                    "utf-8"
                )

            if isinstance(
                cached,
                str,
            ):
                return json.loads(
                    cached
                )

            return cached

        except Exception:
            return None

    def _cache_set(
        self,
        tool_id: str,
        parameters: dict[str, Any],
        result: Any,
        ttl: int,
        tenant_id: str,
    ) -> None:

        if self.cache is None:
            return

        effective_ttl = (
            ttl
            if ttl and ttl > 0
            else self.DEFAULT_CACHE_TTL
        )

        effective_ttl = min(
            effective_ttl,
            self.DEFAULT_CACHE_TTL,
        )

        try:

            key = self._cache_key(
                tool_id,
                parameters,
                tenant_id,
            )

            payload = json.dumps(
                result,
                ensure_ascii=False,
            )

            self.cache.setex(
                key,
                effective_ttl,
                payload,
            )

        except Exception:
            return

    # ========================================================
    # METRICS
    # ========================================================

    def _record_metric(
        self,
        result: ToolResult,
        start_time: float,
        tenant_id: str,
    ) -> None:

        try:

            status = (
                "success"
                if result.success
                else "failure"
            )

            if (
                result.error is not None
                and result.error.code
                == "TIMEOUT"
            ):
                status = "timeout"

            latency = (
                time.perf_counter()
                - start_time
            )

            self.metrics.record_task(
                latency=latency,
                status=status,
                tenant_id=tenant_id,
                sla_met=result.success,
            )

        except Exception:
            pass

    # ========================================================
    # HELPERS
    # ========================================================

    @staticmethod
    def _elapsed_ms(
        start_time: float,
    ) -> float:

        return (
            time.perf_counter()
            - start_time
        ) * 1000

    def _error_result(
        self,
        tool_id: str,
        code: str,
        message: str,
        start_time: float,
        parameters: dict[str, Any] | None = None,
        retry_count: int = 0,
        fallback_used: bool = False,
    ) -> ToolResult:

        return ToolResult(
            success=False,
            tool_id=tool_id,
            result=None,
            error=ToolExecutionError(
                code=code,
                message=message,
                tool_id=tool_id,
                parameters=(
                    parameters or {}
                ),
                retry_count=retry_count,
                fallback_used=fallback_used,
            ),
            execution_time_ms=(
                self._elapsed_ms(
                    start_time
                )
            ),
            cached=False,
        )