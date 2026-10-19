"""
provider_failover.py

Task 4.4B: Provider Failover Executor.

Responsibilities
----------------
- Validate configured provider fallback order.
- Instantiate providers through ProviderFactory.
- Consult ProviderHealthMonitor before execution.
- Execute providers in configured order.
- Continue failover only for retryable failures.
- Stop immediately for non-retryable failures.
- Preserve CircuitOpenError behavior.
- Return validated execution results.
- Record thread-safe failover metrics.
- Emit privacy-aware structured failure diagnostics without request payloads.
"""

from __future__ import annotations

import logging
import math
import re
import threading
import time
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
)

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.services.ai.FieldOpsAI.config.config_loader import (
    ConfigLoader,
)
from app.services.ai.FieldOpsAI.providers.base_provider import (
    BaseAIProvider,
    ProviderConfigurationError,
    ProviderExecutionError,
)
from app.services.ai.FieldOpsAI.providers.provider_factory import (
    ProviderFactory,
)
from app.services.ai.FieldOpsAI.providers.provider_health import (
    ProviderHealthInfrastructureError,
    ProviderHealthMonitor,
)
from app.services.ai.FieldOpsAI.runtime.circuit_breaker import (
    CircuitOpenError,
)
from app.services.ai.FieldOpsAI.schemas.provider import (
    GenerationResult,
    ProviderHealth,
)


logger = logging.getLogger(__name__)

SAFE_ERROR_CODE_REGEX = re.compile(
    r"^[A-Z][A-Z0-9_]{0,63}$"
)


# Common secret patterns are redacted before exception details are logged.
# Keep these diagnostics short: provider exceptions can contain request data.
_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*)(?:bearer\s+)?[^\s,;]+"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/-]+=*"),
    re.compile(r"(?i)(api[_ -]?key\s*[:=]\s*)[^\s,;]+"),
    re.compile(r"(?i)(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{8,}"),
    # Error bodies sometimes echo request fields; omit their values.
    re.compile(r"(?i)((?:prompt|messages|input|content|request_body|payload)\s*[:=]\s*).*$"),
)


def _safe_diagnostic_value(value: Any, *, limit: int = 240) -> Optional[str]:
    """Return a short, single-line diagnostic value with common secrets redacted."""
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        text_value = str(value)
    else:
        # Avoid repr() because arbitrary objects may expose payloads or secrets.
        text_value = type(value).__name__
    text_value = text_value.replace("\r", " ").replace("\n", " ")
    for pattern in _SECRET_PATTERNS:
        if pattern.groups:
            text_value = pattern.sub(lambda match: (match.group(1) + "[REDACTED]") if len(match.groups()) else "[REDACTED]", text_value)
        else:
            text_value = pattern.sub("[REDACTED]", text_value)
    return text_value[:limit]


def _valid_http_status(value: Any) -> Optional[int]:
    """Return an HTTP status only when it is a valid integer status code."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 100 <= value <= 599 else None


def _exception_diagnostics(error: BaseException) -> Dict[str, Any]:
    """Extract useful structured metadata without logging request payloads."""
    cause = error.__cause__
    context = error.__context__
    source = cause or context
    status_code = _valid_http_status(getattr(error, "status_code", None))
    if status_code is None and source is not None:
        status_code = _valid_http_status(getattr(source, "status_code", None))

    provider_code = None
    provider_error_type = None
    if source is not None:
        provider_code = getattr(source, "code", None)
        provider_error_type = getattr(source, "type", None)
    if provider_code is None:
        provider_code = getattr(error, "code", None)
    if provider_error_type is None:
        provider_error_type = getattr(error, "type", None)

    return {
        "error_type": type(error).__name__,
        "status_code": status_code,
        "retryable": getattr(error, "is_retryable", None),
        "cause_type": type(cause).__name__ if cause is not None else None,
        "context_type": type(context).__name__ if context is not None else None,
        "provider_error_code": _safe_diagnostic_value(provider_code, limit=80),
        "provider_error_type": _safe_diagnostic_value(provider_error_type, limit=80),
        "diagnostic_message": _safe_diagnostic_value(str(source or error)),
    }


# ==========================================================
# Exceptions
# ==========================================================


class ProviderFailoverExhaustedError(
    ProviderExecutionError
):
    """
    Raised when all configured providers fail or are skipped.

    The public message is always fixed and contains no raw
    provider error details.
    """

    def __init__(
        self,
        message: str = (
            "All configured AI providers are unavailable."
        ),
        status_code: Optional[int] = None,
        is_retryable: bool = True,
    ) -> None:
        super().__init__(
            message=(
                "All configured AI providers "
                "are unavailable."
            ),
            status_code=status_code,
            is_retryable=is_retryable,
        )


# ==========================================================
# Schemas
# ==========================================================


class FailoverAttempt(BaseModel):
    """
    Immutable record of one provider attempt or skip.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    provider_name: str
    attempted: bool
    skipped: bool
    succeeded: bool
    retryable: bool
    status_code: Optional[int] = None
    latency_ms: float = Field(
        default=0.0,
        ge=0.0,
    )
    safe_error_code: Optional[str] = None

    @field_validator("provider_name")
    @classmethod
    def validate_provider_name(
        cls,
        value: str,
    ) -> str:
        if (
            not isinstance(value, str)
            or not value.strip()
        ):
            raise ValueError(
                "provider_name must be a "
                "non-blank string."
            )

        return value.strip().lower()

    @field_validator("latency_ms")
    @classmethod
    def validate_latency_ms(
        cls,
        value: float,
    ) -> float:
        if (
            not math.isfinite(value)
            or value < 0.0
        ):
            raise ValueError(
                "latency_ms must be a finite "
                "non-negative float."
            )

        return value

    @field_validator("status_code")
    @classmethod
    def validate_status_code(
        cls,
        value: Optional[int],
    ) -> Optional[int]:
        if value is None:
            return None

        if (
            isinstance(value, bool)
            or not isinstance(value, int)
        ):
            raise ValueError(
                "status_code must be an integer, "
                "not a boolean."
            )

        if not 100 <= value <= 599:
            raise ValueError(
                "status_code must be between "
                "100 and 599."
            )

        return value

    @field_validator("safe_error_code")
    @classmethod
    def validate_safe_error_code(
        cls,
        value: Optional[str],
    ) -> Optional[str]:
        if value is None:
            return None

        cleaned_value = value.strip()

        if not cleaned_value:
            return None

        if not SAFE_ERROR_CODE_REGEX.fullmatch(
            cleaned_value
        ):
            raise ValueError(
                "safe_error_code must be an uppercase "
                "identifier containing only letters, "
                "numbers, and underscores."
            )

        return cleaned_value

    @model_validator(mode="after")
    def validate_attempt_consistency(
        self,
    ) -> "FailoverAttempt":
        if self.attempted and self.skipped:
            raise ValueError(
                "attempted and skipped cannot "
                "both be True."
            )

        if self.succeeded and not self.attempted:
            raise ValueError(
                "succeeded requires attempted=True."
            )

        if self.succeeded and self.skipped:
            raise ValueError(
                "succeeded requires skipped=False."
            )

        return self


class FailoverExecutionResult(BaseModel):
    """
    Immutable result of a successful failover execution.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    generation_result: GenerationResult
    selected_provider: str
    attempts: Tuple[FailoverAttempt, ...]
    failover_occurred: bool
    total_latency_ms: float = Field(
        default=0.0,
        ge=0.0,
    )

    @field_validator("selected_provider")
    @classmethod
    def validate_selected_provider(
        cls,
        value: str,
    ) -> str:
        if (
            not isinstance(value, str)
            or not value.strip()
        ):
            raise ValueError(
                "selected_provider must be a "
                "non-blank string."
            )

        return value.strip().lower()

    @field_validator("total_latency_ms")
    @classmethod
    def validate_total_latency_ms(
        cls,
        value: float,
    ) -> float:
        if (
            not math.isfinite(value)
            or value < 0.0
        ):
            raise ValueError(
                "total_latency_ms must be a "
                "finite non-negative float."
            )

        return value

    @model_validator(mode="after")
    def validate_attempts_consistency(
        self,
    ) -> "FailoverExecutionResult":
        successful_attempts = [
            attempt
            for attempt in self.attempts
            if attempt.succeeded
        ]

        if len(successful_attempts) != 1:
            raise ValueError(
                "FailoverExecutionResult must contain "
                "exactly one successful attempt."
            )

        successful_provider = (
            successful_attempts[0].provider_name
        )

        if (
            successful_provider
            != self.selected_provider
        ):
            raise ValueError(
                "selected_provider must match the "
                "successful attempt provider."
            )

        result_provider = (
            self.generation_result
            .provider_name
            .strip()
            .lower()
        )

        if (
            self.selected_provider
            != result_provider
        ):
            raise ValueError(
                "selected_provider must match "
                "generation_result.provider_name."
            )

        return self


class ProviderFailoverMetrics(BaseModel):
    """
    Thread-safe aggregated failover metrics.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    total_executions: int = Field(
        default=0,
        ge=0,
    )
    primary_successes: int = Field(
        default=0,
        ge=0,
    )
    failover_successes: int = Field(
        default=0,
        ge=0,
    )
    exhausted_executions: int = Field(
        default=0,
        ge=0,
    )
    skipped_unhealthy_providers: int = Field(
        default=0,
        ge=0,
    )
    retryable_failures: int = Field(
        default=0,
        ge=0,
    )
    non_retryable_failures: int = Field(
        default=0,
        ge=0,
    )
    average_attempts: float = Field(
        default=0.0,
        ge=0.0,
    )
    average_latency_ms: float = Field(
        default=0.0,
        ge=0.0,
    )


# ==========================================================
# Failover Executor
# ==========================================================


class ProviderFailoverExecutor:
    """
    Execute providers in configured fallback order.

    The attempt_runner callback owns the actual provider
    execution, circuit breaker, budget, cache, and cleanup
    behavior.
    """

    def __init__(
        self,
        provider_factory: Any = ProviderFactory,
        health_monitor: (
            Optional[
                ProviderHealthMonitor | Any
            ]
        ) = None,
        config: (
            Optional[ConfigLoader | Any]
        ) = None,
        clock: (
            Optional[
                Callable[[], Any] | Any
            ]
        ) = None,
        alert_callback: (
            Optional[
                Callable[
                    [Dict[str, Any]],
                    None,
                ]
            ]
        ) = None,
    ) -> None:
        self.provider_factory = (
            provider_factory
        )
        self.health_monitor = (
            health_monitor
        )
        self.config = config
        self._clock = clock
        self.alert_callback = (
            alert_callback
        )

        self._lock = threading.RLock()

        self._total_executions = 0
        self._primary_successes = 0
        self._failover_successes = 0
        self._exhausted_executions = 0
        self._skipped_unhealthy_providers = 0
        self._retryable_failures = 0
        self._non_retryable_failures = 0
        self._total_attempts = 0
        self._total_execution_latency_ms = 0.0

    # ------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------

    def _record_completed_execution(
        self,
        attempts: List[FailoverAttempt],
        total_latency_ms: float,
        outcome: str,
    ) -> None:
        """
        Record terminal execution metrics exactly once.

        Supported outcomes:

        - primary_success
        - failover_success
        - exhausted
        - non_retryable_failure
        """

        with self._lock:
            self._total_executions += 1
            self._total_attempts += len(
                attempts
            )
            self._total_execution_latency_ms += (
                total_latency_ms
            )

            if outcome == "primary_success":
                self._primary_successes += 1

            elif outcome == "failover_success":
                self._failover_successes += 1

            elif outcome == "exhausted":
                self._exhausted_executions += 1

    @staticmethod
    def _normalize_fallback_order(
        raw_fallback_order: Any,
    ) -> List[str]:
        """
        Validate and normalize provider fallback order.
        """

        if not isinstance(
            raw_fallback_order,
            (list, tuple),
        ):
            raise ProviderConfigurationError(
                "provider.fallback_order must be "
                "a list or tuple."
            )

        fallback_chain: List[str] = []

        for item in raw_fallback_order:
            if (
                isinstance(item, bool)
                or not isinstance(item, str)
                or not item.strip()
            ):
                raise ProviderConfigurationError(
                    "provider.fallback_order elements "
                    "must be non-blank strings."
                )

            normalized_name = (
                item.strip().lower()
            )

            if (
                normalized_name
                not in fallback_chain
            ):
                fallback_chain.append(
                    normalized_name
                )

        return fallback_chain

    def _send_alert(
        self,
        payload: Dict[str, Any],
    ) -> None:
        """
        Send an optional alert without allowing alert failures
        to affect provider execution.
        """

        if self.alert_callback is None:
            return

        try:
            self.alert_callback(payload)

        except Exception:
            logger.warning(
                "Provider failover alert callback failed."
            )

    # ------------------------------------------------------
    # Execution
    # ------------------------------------------------------

    def execute(
        self,
        attempt_runner: Callable[
            [str, BaseAIProvider],
            GenerationResult,
        ],
        *,
        provider_kwargs_by_name: (
            Optional[
                Dict[
                    str,
                    Dict[str, Any],
                ]
            ]
        ) = None,
    ) -> FailoverExecutionResult:
        """
        Execute providers until one succeeds, a non-retryable
        failure occurs, or all candidates are exhausted.
        """

        config = (
            self.config
            if self.config is not None
            else ConfigLoader()
        )

        try:
            raw_fallback_order = (
                config.provider_fallback_order
            )

        except ProviderConfigurationError:
            raise

        except Exception:
            raise ProviderConfigurationError(
                "Invalid fallback order configuration."
            ) from None

        fallback_chain = (
            self._normalize_fallback_order(
                raw_fallback_order
            )
        )

        if not fallback_chain:
            raise ProviderFailoverExhaustedError()

        attempts: List[
            FailoverAttempt
        ] = []

        execution_started_at = (
            time.perf_counter()
        )

        last_circuit_open_error: (
            Optional[CircuitOpenError]
        ) = None

        for provider_name in fallback_chain:
            provider_kwargs = (
                provider_kwargs_by_name
                or {}
            ).get(
                provider_name,
                {},
            )

            # ----------------------------------------------
            # 1. Instantiate provider
            # ----------------------------------------------

            try:
                provider = (
                    self.provider_factory
                    .create_provider(
                        name=provider_name,
                        config=config,
                        provider_kwargs=(
                            provider_kwargs
                        ),
                    )
                )

            except ProviderConfigurationError:
                logger.warning(
                    "Provider '%s' configuration "
                    "failed during fallback.",
                    provider_name,
                )

                attempts.append(
                    FailoverAttempt(
                        provider_name=(
                            provider_name
                        ),
                        attempted=False,
                        skipped=True,
                        succeeded=False,
                        retryable=False,
                        latency_ms=0.0,
                        safe_error_code=(
                            "PROVIDER_CONFIGURATION_FAILED"
                        ),
                    )
                )

                continue

            except Exception:
                logger.warning(
                    "Provider '%s' initialization "
                    "failed during fallback.",
                    provider_name,
                )

                attempts.append(
                    FailoverAttempt(
                        provider_name=(
                            provider_name
                        ),
                        attempted=False,
                        skipped=True,
                        succeeded=False,
                        retryable=False,
                        latency_ms=0.0,
                        safe_error_code=(
                            "PROVIDER_INITIALIZATION_FAILED"
                        ),
                    )
                )

                continue

            # ----------------------------------------------
            # 2. Health eligibility
            # ----------------------------------------------

            if self.health_monitor is not None:
                try:
                    snapshot = (
                        self.health_monitor
                        .get_snapshot(
                            provider_name
                        )
                    )

                    if snapshot is None:
                        snapshot = (
                            self.health_monitor
                            .check_provider(
                                provider_name,
                                provider=provider,
                            )
                        )

                    if snapshot.status in (
                        ProviderHealth.HEALTHY,
                        ProviderHealth.DEGRADED,
                    ):
                        pass

                    elif (
                        snapshot.status
                        == ProviderHealth.UNHEALTHY
                    ):
                        should_probe = (
                            self.health_monitor
                            .should_probe(
                                provider_name
                            )
                        )

                        if not should_probe:
                            logger.info(
                                "Provider '%s' is unhealthy "
                                "and recovery probe is not due.",
                                provider_name,
                            )

                            attempts.append(
                                FailoverAttempt(
                                    provider_name=(
                                        provider_name
                                    ),
                                    attempted=False,
                                    skipped=True,
                                    succeeded=False,
                                    retryable=False,
                                    latency_ms=0.0,
                                    safe_error_code=(
                                        "PROVIDER_UNHEALTHY"
                                    ),
                                )
                            )

                            with self._lock:
                                (
                                    self
                                    ._skipped_unhealthy_providers
                                ) += 1

                            continue

                        snapshot = (
                            self.health_monitor
                            .check_provider(
                                provider_name,
                                provider=provider,
                            )
                        )

                        if snapshot.status not in (
                            ProviderHealth.HEALTHY,
                            ProviderHealth.DEGRADED,
                        ):
                            logger.info(
                                "Provider '%s' recovery "
                                "probe failed.",
                                provider_name,
                            )

                            attempts.append(
                                FailoverAttempt(
                                    provider_name=(
                                        provider_name
                                    ),
                                    attempted=False,
                                    skipped=True,
                                    succeeded=False,
                                    retryable=False,
                                    latency_ms=0.0,
                                    safe_error_code=(
                                        "PROVIDER_UNHEALTHY"
                                    ),
                                )
                            )

                            with self._lock:
                                (
                                    self
                                    ._skipped_unhealthy_providers
                                ) += 1

                            continue

                except ProviderHealthInfrastructureError:
                    logger.warning(
                        "Provider health infrastructure "
                        "failed during failover."
                    )

                    raise

            # ----------------------------------------------
            # 3. Execute provider attempt
            # ----------------------------------------------

            attempt_started_at = (
                time.perf_counter()
            )

            try:
                result = attempt_runner(
                    provider_name,
                    provider,
                )

                attempt_latency_ms = max(
                    0.0,
                    (
                        time.perf_counter()
                        - attempt_started_at
                    )
                    * 1000.0,
                )

                if not isinstance(
                    result,
                    GenerationResult,
                ):
                    raise ProviderExecutionError(
                        "Attempt runner returned "
                        "an invalid result.",
                        is_retryable=False,
                    )

                if (
                    not isinstance(
                        result.text,
                        str,
                    )
                    or not result.text.strip()
                ):
                    raise ProviderExecutionError(
                        "Attempt runner returned "
                        "blank text.",
                        is_retryable=False,
                    )

                attempts.append(
                    FailoverAttempt(
                        provider_name=(
                            provider_name
                        ),
                        attempted=True,
                        skipped=False,
                        succeeded=True,
                        retryable=False,
                        status_code=None,
                        latency_ms=(
                            attempt_latency_ms
                        ),
                        safe_error_code=None,
                    )
                )

                total_latency_ms = max(
                    0.0,
                    (
                        time.perf_counter()
                        - execution_started_at
                    )
                    * 1000.0,
                )

                failover_occurred = (
                    len(attempts) > 1
                )

                execution_result = (
                    FailoverExecutionResult(
                        generation_result=result,
                        selected_provider=(
                            provider_name
                        ),
                        attempts=tuple(
                            attempts
                        ),
                        failover_occurred=(
                            failover_occurred
                        ),
                        total_latency_ms=(
                            total_latency_ms
                        ),
                    )
                )

                outcome = (
                    "failover_success"
                    if failover_occurred
                    else "primary_success"
                )

                self._record_completed_execution(
                    attempts,
                    total_latency_ms,
                    outcome,
                )

                if failover_occurred:
                    self._send_alert(
                        {
                            "event_type": (
                                "failover_success"
                            ),
                            "selected_provider": (
                                provider_name
                            ),
                            "attempts_count": len(
                                attempts
                            ),
                            "total_latency_ms": (
                                total_latency_ms
                            ),
                        }
                    )

                return execution_result

            except ProviderHealthInfrastructureError:
                raise

            except CircuitOpenError as error:
                attempt_latency_ms = max(
                    0.0,
                    (
                        time.perf_counter()
                        - attempt_started_at
                    )
                    * 1000.0,
                )

                last_circuit_open_error = error

                attempts.append(
                    FailoverAttempt(
                        provider_name=(
                            provider_name
                        ),
                        attempted=True,
                        skipped=False,
                        succeeded=False,
                        retryable=True,
                        status_code=None,
                        latency_ms=(
                            attempt_latency_ms
                        ),
                        safe_error_code=(
                            "CIRCUIT_OPEN"
                        ),
                    )
                )

                with self._lock:
                    self._retryable_failures += 1

                logger.info(
                    "Circuit is open for provider '%s'. "
                    "Trying the next candidate.",
                    provider_name,
                )

                continue

            except ProviderExecutionError as error:
                attempt_latency_ms = max(
                    0.0,
                    (
                        time.perf_counter()
                        - attempt_started_at
                    )
                    * 1000.0,
                )

                status_code = (
                    error.status_code
                    if (
                        isinstance(
                            error.status_code,
                            int,
                        )
                        and not isinstance(
                            error.status_code,
                            bool,
                        )
                        and 100
                        <= error.status_code
                        <= 599
                    )
                    else None
                )

                attempts.append(
                    FailoverAttempt(
                        provider_name=(
                            provider_name
                        ),
                        attempted=True,
                        skipped=False,
                        succeeded=False,
                        retryable=(
                            error.is_retryable
                        ),
                        status_code=status_code,
                        latency_ms=(
                            attempt_latency_ms
                        ),
                        safe_error_code=(
                            "PROVIDER_EXECUTION_FAILED"
                        ),
                    )
                )

                if error.is_retryable:
                    with self._lock:
                        self._retryable_failures += 1

                    diagnostic = _exception_diagnostics(error)
                    logger.warning(
                        "AI_PROVIDER_RETRYABLE_FAILURE "
                        "provider=%s status_code=%s error_type=%s "
                        "cause_type=%s context_type=%s "
                        "provider_error_code=%s provider_error_type=%s "
                        "diagnostic_message=%s",
                        provider_name,
                        diagnostic["status_code"] or "none",
                        diagnostic["error_type"],
                        diagnostic["cause_type"] or "none",
                        diagnostic["context_type"] or "none",
                        diagnostic["provider_error_code"] or "none",
                        diagnostic["provider_error_type"] or "none",
                        diagnostic["diagnostic_message"] or "none",
                        extra={"provider": provider_name, **diagnostic},
                    )

                    continue

                total_latency_ms = max(
                    0.0,
                    (
                        time.perf_counter()
                        - execution_started_at
                    )
                    * 1000.0,
                )

                self._record_completed_execution(
                    attempts,
                    total_latency_ms,
                    "non_retryable_failure",
                )

                with self._lock:
                    self._non_retryable_failures += 1

                failure_reason = (
                    f"http_{status_code}"
                    if status_code is not None
                    else "non_retryable_provider_failure"
                )
                # Capture the cause AND implicit context before the public
                # exception is sanitized. A provider adapter may use ``raise
                # ... from None``; in that case __cause__ is empty while the
                # original exception may still be available as __context__.
                diagnostic = _exception_diagnostics(error)
                failure_reason = (
                    f"http_{status_code}"
                    if status_code is not None
                    else "non_retryable_provider_failure"
                )

                logger.error(
                    "AI_PROVIDER_FAILURE_DIAGNOSTIC "
                    "provider=%s stage=attempt_runner reason=%s "
                    "error_type=%s status_code=%s retryable=%s "
                    "cause_type=%s context_type=%s "
                    "provider_error_code=%s provider_error_type=%s "
                    "diagnostic_message=%s",
                    provider_name,
                    failure_reason,
                    diagnostic["error_type"],
                    diagnostic["status_code"] or "none",
                    diagnostic["retryable"],
                    diagnostic["cause_type"] or "none",
                    diagnostic["context_type"] or "none",
                    diagnostic["provider_error_code"] or "none",
                    diagnostic["provider_error_type"] or "none",
                    diagnostic["diagnostic_message"] or "none",
                    extra={
                        "provider": provider_name,
                        "failure_reason": failure_reason,
                        **diagnostic,
                        "safe_error_code": "PROVIDER_EXECUTION_FAILED",
                    },
                )

                # Keep the public error sanitized and suppress exception
                # chaining so raw provider messages cannot leak in tracebacks.
                raise ProviderExecutionError(
                    "AI provider execution failed.",
                    status_code=status_code,
                    is_retryable=False,
                ) from None

            except Exception as unexpected_error:
                attempt_latency_ms = max(
                    0.0,
                    (
                        time.perf_counter()
                        - attempt_started_at
                    )
                    * 1000.0,
                )

                attempts.append(
                    FailoverAttempt(
                        provider_name=(
                            provider_name
                        ),
                        attempted=True,
                        skipped=False,
                        succeeded=False,
                        retryable=False,
                        status_code=None,
                        latency_ms=(
                            attempt_latency_ms
                        ),
                        safe_error_code=(
                            "UNEXPECTED_PROVIDER_ERROR"
                        ),
                    )
                )

                total_latency_ms = max(
                    0.0,
                    (
                        time.perf_counter()
                        - execution_started_at
                    )
                    * 1000.0,
                )

                self._record_completed_execution(
                    attempts,
                    total_latency_ms,
                    "non_retryable_failure",
                )

                with self._lock:
                    self._non_retryable_failures += 1

                diagnostic = _exception_diagnostics(unexpected_error)
                logger.error(
                    "AI_PROVIDER_UNEXPECTED_EXCEPTION "
                    "provider=%s stage=attempt_runner error_type=%s "
                    "status_code=%s cause_type=%s context_type=%s "
                    "provider_error_code=%s provider_error_type=%s "
                    "diagnostic_message=%s",
                    provider_name,
                    diagnostic["error_type"],
                    diagnostic["status_code"] or "none",
                    diagnostic["cause_type"] or "none",
                    diagnostic["context_type"] or "none",
                    diagnostic["provider_error_code"] or "none",
                    diagnostic["provider_error_type"] or "none",
                    diagnostic["diagnostic_message"] or "none",
                    extra={
                        "provider": provider_name,
                        **diagnostic,
                        "safe_error_code": "UNEXPECTED_PROVIDER_ERROR",
                    },
                )

                raise ProviderExecutionError(
                    "AI provider execution failed.",
                    status_code=None,
                    is_retryable=False,
                ) from None

        # ----------------------------------------------
        # All providers exhausted
        # ----------------------------------------------

        total_latency_ms = max(
            0.0,
            (
                time.perf_counter()
                - execution_started_at
            )
            * 1000.0,
        )

        self._record_completed_execution(
            attempts,
            total_latency_ms,
            "exhausted",
        )

        self._send_alert(
            {
                "event_type": (
                    "failover_exhausted"
                ),
                "attempts_count": len(
                    attempts
                ),
                "total_latency_ms": (
                    total_latency_ms
                ),
            }
        )

        # Preserve the original CircuitOpenError when there
        # is exactly one configured provider.
        if (
            len(fallback_chain) == 1
            and last_circuit_open_error
            is not None
        ):
            raise last_circuit_open_error

        raise ProviderFailoverExhaustedError()

    # ------------------------------------------------------
    # Metrics
    # ------------------------------------------------------

    def get_metrics(
        self,
    ) -> ProviderFailoverMetrics:
        """
        Return a thread-safe metrics snapshot.
        """

        with self._lock:
            if self._total_executions > 0:
                average_attempts = (
                    self._total_attempts
                    / self._total_executions
                )

                average_latency_ms = (
                    self
                    ._total_execution_latency_ms
                    / self._total_executions
                )

            else:
                average_attempts = 0.0
                average_latency_ms = 0.0

            return ProviderFailoverMetrics(
                total_executions=(
                    self._total_executions
                ),
                primary_successes=(
                    self._primary_successes
                ),
                failover_successes=(
                    self._failover_successes
                ),
                exhausted_executions=(
                    self._exhausted_executions
                ),
                skipped_unhealthy_providers=(
                    self
                    ._skipped_unhealthy_providers
                ),
                retryable_failures=(
                    self._retryable_failures
                ),
                non_retryable_failures=(
                    self._non_retryable_failures
                ),
                average_attempts=(
                    average_attempts
                ),
                average_latency_ms=(
                    average_latency_ms
                ),
            )
