"""
Task runtime retry management.

Provides retry classification and exponential backoff for
Celery/Redis task execution.

Retry policy:
    Initial attempt
    Retry 1 -> 1 second
    Retry 2 -> 2 seconds
    Retry 3 -> 4 seconds
    Then -> Dead Letter Queue

Retryable:
    - HTTP 429
    - HTTP 5xx
    - Timeout errors
    - Network/connection errors

Non-retryable:
    - HTTP 400
    - HTTP 401
    - HTTP 403
    - Guardrail violations
    - Unknown/non-transient errors
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class RetryDecision(str, Enum):
    """Possible outcomes after a task failure."""

    RETRY = "retry"
    DLQ = "dlq"


@dataclass(frozen=True)
class RetryResult:
    """Result of evaluating a failed task."""

    decision: RetryDecision
    retry_number: int
    delay_seconds: float
    reason: str


class RetryManager:
    """
    Manage task retry policy.

    Retry numbering starts at 1:

        retry 1 -> 1 second
        retry 2 -> 2 seconds
        retry 3 -> 4 seconds

    After retry 3 has already been scheduled/executed and the task
    fails again, the task is sent to the DLQ.
    """

    MAX_RETRIES = 3

    BACKOFF_DELAYS = (
        1.0,
        2.0,
        4.0,
    )

    RETRYABLE_STATUS_CODES = {
        429,
    }

    NON_RETRYABLE_STATUS_CODES = {
        400,
        401,
        403,
    }

    @classmethod
    def calculate_backoff(cls, retry_number: int) -> float:
        """
        Return the delay for a retry.

        Args:
            retry_number:
                Retry number starting at 1.

        Returns:
            Delay in seconds.

        Raises:
            ValueError:
                If retry_number is outside the configured range.
        """

        if not 1 <= retry_number <= cls.MAX_RETRIES:
            raise ValueError(
                f"retry_number must be between 1 and "
                f"{cls.MAX_RETRIES}"
            )

        return cls.BACKOFF_DELAYS[retry_number - 1]

    @classmethod
    def extract_status_code(
        cls,
        error: BaseException,
    ) -> int | None:
        """
        Extract an HTTP status code from an exception.

        Supports common patterns such as:

            error.status_code
            error.response.status_code
        """

        status_code = getattr(
            error,
            "status_code",
            None,
        )

        if isinstance(status_code, int):
            return status_code

        response = getattr(
            error,
            "response",
            None,
        )

        if response is not None:
            response_status = getattr(
                response,
                "status_code",
                None,
            )

            if isinstance(response_status, int):
                return response_status

        return None

    @classmethod
    def is_guardrail_violation(
        cls,
        error: BaseException,
    ) -> bool:
        """
        Determine whether an exception represents a guardrail
        violation.

        The project contains multiple guardrail implementations,
        so classification intentionally supports common signals
        without importing a specific guardrail class here.
        """

        class_name = error.__class__.__name__.lower()
        error_message = str(error).lower()

        if "guardrail" in class_name:
            return True

        if "guardrail violation" in error_message:
            return True

        return False

    @classmethod
    def is_retryable(
        cls,
        error: BaseException,
    ) -> bool:
        """
        Determine whether a task failure is transient/retryable.
        """

        # Guardrail violations and permanent validation/permission errors must never be retried.
        if cls.is_guardrail_violation(error):
            return False

        if isinstance(
            error,
            (
                ValueError,
                KeyError,
                TypeError,
                PermissionError,
            ),
        ):
            return False

        # Timeout/network/broker failures are retryable.
        if isinstance(
            error,
            (
                TimeoutError,
                ConnectionError,
            ),
        ):
            return True

        err_class = error.__class__.__name__.lower()
        err_msg = str(error).lower()
        if any(term in err_class or term in err_msg for term in ["broker", "network", "transient", "redisconnection", "connectionreset"]):
            return True

        status_code = cls.extract_status_code(error)

        if status_code is not None:
            if status_code in cls.RETRYABLE_STATUS_CODES:
                return True

            if 500 <= status_code <= 599:
                return True

            if status_code in cls.NON_RETRYABLE_STATUS_CODES:
                return False

            # Other explicit HTTP 4xx responses are not considered
            # transient unless explicitly added to the policy.
            if 400 <= status_code <= 499:
                return False

        # Unknown errors are not automatically retried.
        return False

    @classmethod
    def should_retry(
        cls,
        error: BaseException,
        retry_count: int,
    ) -> bool:
        """
        Return True when the failed task should be retried.

        retry_count represents the number of retries that have
        already been performed.
        """

        if retry_count >= cls.MAX_RETRIES:
            return False

        return cls.is_retryable(error)

    @classmethod
    def evaluate(
        cls,
        error: BaseException,
        retry_count: int,
    ) -> RetryResult:
        """
        Evaluate a failed task and return the next action.

        Args:
            error:
                Exception raised by task execution.

            retry_count:
                Number of retries already performed.

        Returns:
            RetryResult describing RETRY or DLQ.
        """

        if not cls.is_retryable(error):
            return RetryResult(
                decision=RetryDecision.DLQ,
                retry_number=retry_count,
                delay_seconds=0.0,
                reason="non_retryable_error",
            )

        if retry_count >= cls.MAX_RETRIES:
            return RetryResult(
                decision=RetryDecision.DLQ,
                retry_number=retry_count,
                delay_seconds=0.0,
                reason="maximum_retries_exceeded",
            )

        retry_number = retry_count + 1

        return RetryResult(
            decision=RetryDecision.RETRY,
            retry_number=retry_number,
            delay_seconds=cls.calculate_backoff(
                retry_number
            ),
            reason="retryable_error",
        )

    @classmethod
    def policy(cls) -> dict[str, Any]:
        """Return the configured retry policy."""

        return {
            "max_retries": cls.MAX_RETRIES,
            "backoff_delays": list(cls.BACKOFF_DELAYS),
            "retryable_status_codes": sorted(
                cls.RETRYABLE_STATUS_CODES
            ),
            "non_retryable_status_codes": sorted(
                cls.NON_RETRYABLE_STATUS_CODES
            ),
        }

    @classmethod
    def calculate_backoff_with_jitter(
        cls,
        retry_number: int,
        jitter: bool = True,
    ) -> float:
        """Calculate bounded exponential backoff with optional random jitter."""
        import random
        base_delay = cls.calculate_backoff(retry_number)
        if jitter:
            return round(base_delay + random.uniform(0.05, 0.25), 3)
        return float(base_delay)

    @classmethod
    def get_retry_policy_contract(cls) -> dict[str, Any]:
        """Return canonical JSON contract for task retry rules."""
        return {
            "status": "CONFIGURED",
            "retry_policy": {
                "max_retries": cls.MAX_RETRIES,
                "backoff": "exponential",
                "jitter": True,
            },
        }


# ---------------------------------------------------------------------------
# Re-exports from app.celery_app
# ---------------------------------------------------------------------------

from app.celery_app import (
    get_task_retry_rules_config,
    configure_task_retry_rules,
    ConfigureTaskRetryRules,
    Configure_task_retry_rules,
    configure_retry_rules,
    ConfigureRetryRules,
    get_retry_rules_config,
)