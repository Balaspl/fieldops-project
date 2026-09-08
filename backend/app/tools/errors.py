from __future__ import annotations

import builtins
import json
import time
import urllib.request
import uuid

from dataclasses import dataclass
from threading import Lock
from typing import Any, Callable


# ============================================================
# ERROR TYPES
# ============================================================


class ToolError(Exception):
    """
    Base class for all tool execution errors.

    Every ToolError contains:
        - code
        - message
        - tool_id
        - parameters
        - retryable
    """

    code = "TOOL_ERROR"
    retryable = False

    def __init__(
        self,
        message: str,
        *,
        tool_id: str | None = None,
        parameters: dict[str, Any] | None = None,
        code: str | None = None,
    ) -> None:
        super().__init__(message)

        self.message = message
        self.tool_id = tool_id
        self.parameters = (
            parameters.copy()
            if parameters
            else {}
        )

        self.code = (
            code
            if code is not None
            else self.__class__.code
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "tool_id": self.tool_id,
            "parameters": self.parameters,
            "retryable": self.retryable,
        }


class TransientError(ToolError):
    """
    Temporary failure.

    Transient errors are retryable.
    """

    code = "TRANSIENT_ERROR"
    retryable = True


class PermanentError(ToolError):
    """
    Permanent failure.

    Permanent errors are not retryable.
    """

    code = "PERMANENT_ERROR"
    retryable = False


class ValidationError(PermanentError):
    """
    Invalid tool input or parameters.

    Validation failures should not be retried.
    """

    code = "VALIDATION_ERROR"
    retryable = False


class TimeoutError(TransientError):
    """
    Tool execution exceeded the configured timeout.

    Timeouts are retryable.
    """

    code = "TIMEOUT"
    retryable = True


# ============================================================
# STRUCTURED ERROR
# ============================================================


@dataclass(slots=True)
class StructuredToolError:
    """
    Machine-readable tool error.
    """

    code: str
    message: str
    tool_id: str
    parameters: dict[str, Any]

    retry_count: int = 0
    fallback_used: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "tool_id": self.tool_id,
            "parameters": self.parameters,
            "retry_count": self.retry_count,
            "fallback_used": self.fallback_used,
        }


@dataclass(slots=True)
class ErrorResult:
    """
    Result returned by ToolErrorHandler.handle_error().
    """

    success: bool
    result: Any = None

    error: StructuredToolError | None = None

    fallback_used: bool = False
    fallback_tool_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "result": self.result,
            "error": (
                self.error.to_dict()
                if self.error is not None
                else None
            ),
            "fallback_used": self.fallback_used,
            "fallback_tool_id": self.fallback_tool_id,
        }


# ============================================================
# CIRCUIT BREAKER
# ============================================================


@dataclass
class _CircuitState:
    failures: int = 0
    opened_at: float | None = None


class CircuitBreaker:
    """
    Per-tool circuit breaker.

    Default behavior:

        5 final failures
              ↓
        OPEN circuit
              ↓
        5 minutes
              ↓
        automatically closes

    Redis is supported for shared state.

    Without Redis, state is kept in memory.
    """

    FAILURE_THRESHOLD = 5
    OPEN_DURATION_SECONDS = 300

    def __init__(
        self,
        failure_threshold: int = FAILURE_THRESHOLD,
        open_duration_seconds: float = OPEN_DURATION_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        redis_client: Any | None = None,
    ) -> None:
        self.failure_threshold = max(
            1,
            int(failure_threshold),
        )

        self.open_duration_seconds = max(
            0.0,
            float(open_duration_seconds),
        )

        self.clock = clock
        self.redis = redis_client

        self._states: dict[str, _CircuitState] = {}
        self._lock = Lock()

    # --------------------------------------------------------
    # Redis keys
    # --------------------------------------------------------

    def _open_key(
        self,
        tool_id: str,
    ) -> str:
        return (
            f"fieldops:tools:"
            f"circuit:{tool_id}:open"
        )

    def _failure_key(
        self,
        tool_id: str,
    ) -> str:
        return (
            f"fieldops:tools:"
            f"circuit:{tool_id}:failures"
        )

    # --------------------------------------------------------
    # Check
    # --------------------------------------------------------

    def is_open(
        self,
        tool_id: str,
    ) -> bool:
        if self.redis is not None:
            try:
                return (
                    self.redis.get(
                        self._open_key(tool_id)
                    )
                    is not None
                )
            except Exception:
                pass

        with self._lock:
            state = self._states.get(tool_id)

            if state is None:
                return False

            if state.opened_at is None:
                return False

            elapsed = (
                self.clock()
                - state.opened_at
            )

            if elapsed >= self.open_duration_seconds:
                self._states[tool_id] = _CircuitState()
                return False

            return True

    # --------------------------------------------------------
    # Failure
    # --------------------------------------------------------

    def record_failure(
        self,
        tool_id: str,
    ) -> bool:
        """
        Record one final tool failure.

        Returns:
            True  -> circuit is open
            False -> circuit remains closed
        """

        if self.redis is not None:
            try:
                failure_key = (
                    self._failure_key(tool_id)
                )

                open_key = (
                    self._open_key(tool_id)
                )

                failures = self.redis.incr(
                    failure_key
                )

                # Keep failure counter alive for the
                # circuit window.
                self.redis.expire(
                    failure_key,
                    max(
                        1,
                        int(
                            self.open_duration_seconds
                        ),
                    ),
                )

                if failures >= self.failure_threshold:
                    self.redis.set(
                        open_key,
                        "1",
                        ex=max(
                            1,
                            int(
                                self.open_duration_seconds
                            ),
                        ),
                    )

                    return True

                return False

            except Exception:
                # Redis unavailable.
                # Fall back to local state.
                pass

        with self._lock:
            state = self._states.setdefault(
                tool_id,
                _CircuitState(),
            )

            if state.opened_at is not None:
                return True

            state.failures += 1

            if (
                state.failures
                >= self.failure_threshold
            ):
                state.opened_at = self.clock()
                return True

            return False

    # --------------------------------------------------------
    # Success
    # --------------------------------------------------------

    def record_success(
    self,
    tool_id: str,
) -> None:
        if self.redis is not None:
            try:
                self.redis.delete(
                    self._failure_key(tool_id)
                )
            except Exception:
                pass

            try:
                self.redis.delete(
                self._open_key(tool_id)
            )
            except Exception:
                pass

        with self._lock:
            self._states.pop(
            tool_id,
            None,
        )

    # --------------------------------------------------------
    # Reset
    # --------------------------------------------------------

    def reset(
        self,
        tool_id: str,
    ) -> None:
        self.record_success(tool_id)

    # --------------------------------------------------------
    # Failure count
    # --------------------------------------------------------

    def failure_count(
        self,
        tool_id: str,
    ) -> int:
        if self.redis is not None:
            try:
                value = self.redis.get(
                    self._failure_key(tool_id)
                )

                if value is None:
                    return 0

                if isinstance(value, bytes):
                    value = value.decode(
                        "utf-8"
                    )

                return int(value)

            except Exception:
                pass

        with self._lock:
            state = self._states.get(tool_id)

            if state is None:
                return 0

            return state.failures


# ============================================================
# ERROR RATE TRACKER
# ============================================================


class ErrorRateTracker:
    """
    Rolling error-rate tracker.

    Default window:

        5 minutes

    Error rate:

        failures / total executions
    """

    WINDOW_SECONDS = 300

    def __init__(
        self,
        window_seconds: float = WINDOW_SECONDS,
        clock: Callable[[], float] = time.time,
        redis_client: Any | None = None,
    ) -> None:
        self.window_seconds = max(
            0.0,
            float(window_seconds),
        )

        self.clock = clock
        self.redis = redis_client

        self._events: dict[
            str,
            list[tuple[float, bool]],
        ] = {}

        self._lock = Lock()

    # --------------------------------------------------------
    # Redis keys
    # --------------------------------------------------------

    def _total_key(
        self,
        tool_id: str,
    ) -> str:
        return (
            f"fieldops:tools:"
            f"error-rate:{tool_id}:total"
        )

    def _failure_key(
        self,
        tool_id: str,
    ) -> str:
        return (
            f"fieldops:tools:"
            f"error-rate:{tool_id}:failures"
        )

    # --------------------------------------------------------
    # Cleanup
    # --------------------------------------------------------

    def _cleanup(
        self,
        tool_id: str,
        now: float,
    ) -> list[tuple[float, bool]]:
        events = self._events.setdefault(
            tool_id,
            [],
        )

        cutoff = (
            now
            - self.window_seconds
        )

        events[:] = [
            event
            for event in events
            if event[0] >= cutoff
        ]

        return events

    # --------------------------------------------------------
    # Record
    # --------------------------------------------------------

    def record(
        self,
        tool_id: str,
        success: bool,
    ) -> float:
        now = self.clock()

        if self.redis is not None:
            try:
                total_key = (
                    self._total_key(tool_id)
                )

                failure_key = (
                    self._failure_key(tool_id)
                )

                cutoff = (
                    now
                    - self.window_seconds
                )

                member = (
                    f"{now:.6f}:"
                    f"{uuid.uuid4().hex}"
                )

                # Every invocation goes into total.
                self.redis.zadd(
                    total_key,
                    {
                        member: now,
                    },
                )

                # Only failures go into failures.
                if not success:
                    self.redis.zadd(
                        failure_key,
                        {
                            member: now,
                        },
                    )

                # Remove old events.
                self.redis.zremrangebyscore(
                    total_key,
                    "-inf",
                    cutoff,
                )

                self.redis.zremrangebyscore(
                    failure_key,
                    "-inf",
                    cutoff,
                )

                total = self.redis.zcard(
                    total_key
                )

                failures = self.redis.zcard(
                    failure_key
                )

                # Keep keys around slightly longer than
                # the rolling window.
                ttl = max(
                    1,
                    int(
                        self.window_seconds
                    ) + 1,
                )

                self.redis.expire(
                    total_key,
                    ttl,
                )

                self.redis.expire(
                    failure_key,
                    ttl,
                )

                if total == 0:
                    return 0.0

                return failures / total

            except Exception:
                pass

        # ----------------------------------------------------
        # In-memory implementation
        # ----------------------------------------------------

        with self._lock:
            events = self._cleanup(
                tool_id,
                now,
            )

            events.append(
                (
                    now,
                    success,
                )
            )

            failures = sum(
                1
                for _, event_success in events
                if not event_success
            )

            return (
                failures / len(events)
                if events
                else 0.0
            )

    # --------------------------------------------------------
    # Get rate
    # --------------------------------------------------------

    def get_rate(
        self,
        tool_id: str,
    ) -> float:
        now = self.clock()

        if self.redis is not None:
            try:
                total_key = (
                    self._total_key(tool_id)
                )

                failure_key = (
                    self._failure_key(tool_id)
                )

                cutoff = (
                    now
                    - self.window_seconds
                )

                self.redis.zremrangebyscore(
                    total_key,
                    "-inf",
                    cutoff,
                )

                self.redis.zremrangebyscore(
                    failure_key,
                    "-inf",
                    cutoff,
                )

                total = self.redis.zcard(
                    total_key
                )

                failures = self.redis.zcard(
                    failure_key
                )

                if total == 0:
                    return 0.0

                return failures / total

            except Exception:
                pass

        with self._lock:
            events = self._cleanup(
                tool_id,
                now,
            )

            if not events:
                return 0.0

            failures = sum(
                1
                for _, event_success in events
                if not event_success
            )

            return failures / len(events)

    # --------------------------------------------------------
    # Reset
    # --------------------------------------------------------

    def reset(
        self,
        tool_id: str,
    ) -> None:
        if self.redis is not None:
            try:
                self.redis.delete(
                    self._total_key(tool_id),
                    self._failure_key(tool_id),
                )
            except Exception:
                pass

        with self._lock:
            self._events.pop(
                tool_id,
                None,
            )


# ============================================================
# TOOL ERROR HANDLER
# ============================================================


class ToolErrorHandler:
    """
    Centralized tool error handling.

    Responsibilities:

        - Error classification
        - 3 retries for transient errors
        - Exponential backoff
        - Permanent-error fallback
        - Circuit breaker
        - Error-rate tracking
        - Alerting
        - Webhook support
    """

    MAX_RETRIES = 3

    ERROR_RATE_THRESHOLD = 0.10

    CIRCUIT_FAILURE_THRESHOLD = 5

    CIRCUIT_OPEN_DURATION = 300

    def __init__(
        self,
        *,
        max_retries: int = MAX_RETRIES,
        backoff_base: float = 0.1,
        circuit_breaker: CircuitBreaker | None = None,
        
        error_rate_tracker: ErrorRateTracker | None = None,
        alert_callback: Callable[
            [dict[str, Any]],
            None,
        ] | None = None,
        sleep: Callable[
            [float],
            None,
        ] = time.sleep,
        redis_client: Any | None = None,
    ) -> None:
        self.redis = redis_client

        self.max_retries = max(
            0,
            int(max_retries),
        )

        self.backoff_base = max(
            0.0,
            float(backoff_base),
        )

        self.circuit_breaker = (
            circuit_breaker
            if circuit_breaker is not None
            else CircuitBreaker(
                failure_threshold=(
                    self.CIRCUIT_FAILURE_THRESHOLD
                ),
                open_duration_seconds=(
                    self.CIRCUIT_OPEN_DURATION
                ),
                redis_client=redis_client,
            )
        )

        self.error_rate_tracker = (
            error_rate_tracker
            if error_rate_tracker is not None
            else ErrorRateTracker(
                window_seconds=(
                    self.CIRCUIT_OPEN_DURATION
                ),
                redis_client=redis_client,
            )
        )

        self.alert_callback = alert_callback
        self.sleep = sleep
        self._sleep = sleep

        self._alerted_tools: set[str] = set()
        self._alert_lock = Lock()

    # ========================================================
    # CLASSIFY ERROR
    # ========================================================

    def classify_error(
        self,
        exception: BaseException,
    ) -> ToolError:
        """
        Classify arbitrary exceptions.

        Rules:

            builtins.TimeoutError
                -> TimeoutError

            ConnectionError
                -> TransientError

            ValueError
                -> ValidationError

            everything else
                -> PermanentError
        """

        # Already classified.
        if isinstance(
            exception,
            ToolError,
        ):
            return exception

        # ----------------------------------------------------
        # Timeout
        # ----------------------------------------------------

        if isinstance(
            exception,
            builtins.TimeoutError,
        ):
            return TimeoutError(
                str(exception)
                or "Tool execution timed out"
            )

        # ----------------------------------------------------
        # Network connection failure
        # ----------------------------------------------------

        if isinstance(
            exception,
            ConnectionError,
        ):
            return TransientError(
                str(exception)
                or "Temporary connection failure"
            )

        # ----------------------------------------------------
        # Invalid input
        # ----------------------------------------------------

        if isinstance(
            exception,
            ValueError,
        ):
            return ValidationError(
                str(exception)
                or "Invalid tool input"
            )

        # ----------------------------------------------------
        # Unknown exception
        # ----------------------------------------------------

        return PermanentError(
            str(exception)
            or "Tool execution failed"
        )

    # ========================================================
    # HANDLE ERROR
    # ========================================================

    def handle_error(
        self,
        tool_id: str,
        error: ToolError,
        *,
        parameters: dict[str, Any] | None = None,
        fallback_value: Any = None,
        has_fallback_value: bool = False,
        fallback_tool: Callable[[], Any] | None = None,
        fallback_tool_id: str | None = None,
        retry_count: int = 0,
    ) -> ErrorResult:
        """
        Handle final tool error.

        Fallback is intentionally used only for
        non-retryable/permanent errors.

        Priority:

            1. Alternative tool
            2. Static fallback
            3. Structured error
        """

        parameters = (
            parameters.copy()
            if parameters
            else {}
        )

        structured_error = StructuredToolError(
            code=error.code,
            message=error.message,
            tool_id=tool_id,
            parameters=parameters,
            retry_count=retry_count,
        )

        # ----------------------------------------------------
        # IMPORTANT:
        #
        # Do not use fallback while an error is still
        # retryable.
        # ----------------------------------------------------

        if error.retryable:
            return ErrorResult(
                success=False,
                result=None,
                error=structured_error,
                fallback_used=False,
                fallback_tool_id=None,
            )

        # ----------------------------------------------------
        # Alternative tool
        # ----------------------------------------------------

        if fallback_tool is not None:
            try:
                result = fallback_tool()

                return ErrorResult(
                    success=True,
                    result=result,
                    error=None,
                    fallback_used=True,
                    fallback_tool_id=fallback_tool_id,
                )

            except Exception:
                # Continue to static fallback.
                pass

        # ----------------------------------------------------
        # Static fallback
        # ----------------------------------------------------

        if has_fallback_value:
            return ErrorResult(
                success=True,
                result=fallback_value,
                error=None,
                fallback_used=True,
                fallback_tool_id=None,
            )

        # ----------------------------------------------------
        # No fallback
        # ----------------------------------------------------

        return ErrorResult(
            success=False,
            result=None,
            error=structured_error,
            fallback_used=False,
            fallback_tool_id=None,
        )

    # ========================================================
    # RETRY
    # ========================================================

    def execute_with_retry(
        self,
        operation: Callable[[], Any],
        *,
        tool_id: str,
        parameters: dict[str, Any] | None = None,
    ) -> tuple[
        Any | None,
        ToolError | None,
        int,
    ]:
        """
        Execute operation with transient retry.

        max_retries = 3 means:

            attempt 1
            retry 1
            retry 2
            retry 3

        Maximum total attempts = 4.

        Backoff:

            retry 1 -> base
            retry 2 -> base * 2
            retry 3 -> base * 4
        """

        parameters = (
            parameters.copy()
            if parameters
            else {}
        )

        # ----------------------------------------------------
        # Circuit breaker
        # ----------------------------------------------------

        if self.circuit_breaker.is_open(
            tool_id
        ):
            return (
                None,
                PermanentError(
                    "Circuit breaker is open",
                    tool_id=tool_id,
                    parameters=parameters,
                    code="CIRCUIT_OPEN",
                ),
                0,
            )

        retry_count = 0

        while True:
            try:
                result = operation()

                # Successful invocation resets
                # consecutive circuit failures.
                self.circuit_breaker.record_success(
                    tool_id
                )

                self._record_error_rate(
                    tool_id,
                    success=True,
                )

                return (
                    result,
                    None,
                    retry_count,
                )

            except Exception as exc:
                # IMPORTANT:
                # Exception, not BaseException.
                #
                # KeyboardInterrupt/SystemExit/etc.
                # must not be swallowed.
                error = self.classify_error(
                    exc
                )

                error.tool_id = tool_id
                error.parameters = parameters

                # ------------------------------------------------
                # Retry transient error
                # ------------------------------------------------

                if (
                    error.retryable
                    and retry_count
                    < self.max_retries
                ):
                    delay = (
                        self.backoff_base
                        * (
                            2
                            ** retry_count
                        )
                    )

                    retry_count += 1

                    if delay > 0:
                        self._sleep(delay)

                    continue

                # ------------------------------------------------
                # Final failure
                # ------------------------------------------------

                self.circuit_breaker.record_failure(
                    tool_id
                )

                self._record_error_rate(
                    tool_id,
                    success=False,
                )

                return (
                    None,
                    error,
                    retry_count,
                )

    # ========================================================
    # ERROR RATE
    # ========================================================

    def _record_error_rate(
        self,
        tool_id: str,
        *,
        success: bool,
    ) -> None:
        rate = self.error_rate_tracker.record(
            tool_id,
            success,
        )

        # Requirement:
        # alert when rate is > 10%.
        if rate <= self.ERROR_RATE_THRESHOLD:
            return

        # ----------------------------------------------------
        # Distributed Redis alert deduplication
        # ----------------------------------------------------

        if self.redis is not None:
            try:
                alert_key = (
                    f"fieldops:tools:"
                    f"error-rate:{tool_id}:alerted"
                )

                should_alert = self.redis.set(
                    alert_key,
                    "1",
                    ex=max(
                        1,
                        int(
                            self.error_rate_tracker
                            .window_seconds
                        ),
                    ),
                    nx=True,
                )

                if not should_alert:
                    return

            except Exception:
                # Redis failure:
                # use local deduplication.
                pass

        # ----------------------------------------------------
        # Local deduplication
        # ----------------------------------------------------

        with self._alert_lock:
            if tool_id in self._alerted_tools:
                return

            self._alerted_tools.add(
                tool_id
            )

        # ----------------------------------------------------
        # Alert payload
        # ----------------------------------------------------

        payload = {
            "type": "tool_error_rate_alert",
            "tool_id": tool_id,
            "error_rate": rate,
            "threshold": (
                self.ERROR_RATE_THRESHOLD
            ),
            "window_seconds": (
                self.error_rate_tracker
                .window_seconds
            ),
            "timestamp": time.time(),
        }

        # ----------------------------------------------------
        # Callback
        # ----------------------------------------------------

        if self.alert_callback is not None:
            try:
                self.alert_callback(
                    payload
                )
            except Exception:
                # Alert failures must never break
                # the tool execution.
                pass

    # ========================================================
    # RESET ALERT
    # ========================================================

    def reset_alert(
        self,
        tool_id: str,
    ) -> None:
        """
        Reset alert deduplication state.
        """

        if self.redis is not None:
            try:
                self.redis.delete(
                    f"fieldops:tools:"
                    f"error-rate:{tool_id}:alerted"
                )
            except Exception:
                pass

        with self._alert_lock:
            self._alerted_tools.discard(
                tool_id
            )

    # ========================================================
    # WEBHOOK
    # ========================================================

    @staticmethod
    def webhook_alert(
        webhook_url: str,
        payload: dict[str, Any],
        timeout: float = 5.0,
    ) -> None:
        """
        Send an alert payload to a webhook.
        """

        body = json.dumps(
            payload,
            ensure_ascii=False,
        ).encode("utf-8")

        request = urllib.request.Request(
            webhook_url,
            data=body,
            headers={
                "Content-Type": "application/json",
            },
            method="POST",
        )

        with urllib.request.urlopen(
            request,
            timeout=timeout,
        ):
            pass