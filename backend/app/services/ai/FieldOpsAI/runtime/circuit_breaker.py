"""
circuit_breaker.py

Task 3.5: AI Provider Circuit Breaker with CircuitPermit and Compare-and-Delete Lock Release.

Distributed, Redis-backed circuit breaker for AI provider calls.
Supports state transitions (CLOSED, OPEN, HALF_OPEN), sliding-window failure tracking,
cryptographic probe tokens, atomic compare-and-delete lock release, and retryable error classification.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.ai.FieldOpsAI.providers.base_provider import (
    is_retryable_provider_error,
)

logger = logging.getLogger(__name__)


# --- States ---

class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


# --- Custom Exceptions ---

class CircuitError(Exception):
    """
    Base exception for all circuit breaker errors.
    """
    pass


class CircuitOpenError(CircuitError):
    """
    Raised when request is blocked because the circuit breaker is OPEN
    or a HALF_OPEN probe is already in progress.
    """
    pass


class CircuitBreakerInfrastructureError(CircuitError):
    """
    Raised when Redis database failure occurs (fail-closed infrastructure policy).
    """
    pass


# --- Schemas ---

class CircuitPermit(BaseModel):
    """
    Immutable permission token returned by check_permission().
    """
    model_config = ConfigDict(frozen=True)

    provider_scope: str
    is_half_open_probe: bool = False
    probe_token: Optional[str] = None


class CircuitBreakerConfig(BaseModel):
    """
    Validated, immutable circuit breaker configuration.
    """
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    enabled: bool = True
    failure_threshold: int = Field(default=5, gt=0)
    failure_window_seconds: int = Field(default=60, gt=0)
    open_cooldown_seconds: int = Field(default=300, gt=0)
    half_open_success_threshold: int = Field(default=3, gt=0)
    half_open_max_concurrent_probes: int = Field(default=1)
    half_open_probe_ttl_seconds: int = Field(
        default=180,
        gt=0,
    )
    namespace_version: str = Field(
        default="v1",
        min_length=1,
    )

    @field_validator("half_open_max_concurrent_probes")
    @classmethod
    def validate_max_concurrent_probes(cls, v: int) -> int:
        if v != 1:
            raise ValueError("half_open_max_concurrent_probes must be exactly 1.")
        return v

    @classmethod
    def from_mapping(cls, mapping: Dict[str, Any]) -> CircuitBreakerConfig:
        return cls(**mapping)


class CircuitBreakerSnapshot(BaseModel):
    """
    Snapshot of current circuit breaker state for a provider.
    """
    model_config = ConfigDict(frozen=True)

    state: CircuitState
    failure_count: int = Field(ge=0)
    consecutive_successes: int = Field(ge=0)
    last_state_change: Optional[str] = None


# --- Atomic Probe Scripts ---

RELEASE_LOCK_LUA = """
local current_token = redis.call("GET", KEYS[1])

if current_token and tostring(current_token) == tostring(ARGV[1]) then
    return redis.call("DEL", KEYS[1])
end

return 0
"""


HALF_OPEN_SUCCESS_LUA = """
local current_token = redis.call("GET", KEYS[1])

if not current_token or tostring(current_token) ~= tostring(ARGV[1]) then
    return -1
end

local state = redis.call("GET", KEYS[2])

if state ~= "HALF_OPEN" then
    redis.call("DEL", KEYS[1])
    return 0
end

redis.call("DEL", KEYS[1])

local successes = redis.call("INCR", KEYS[3])
local success_threshold = tonumber(ARGV[2])

if successes >= success_threshold then
    redis.call("SET", KEYS[2], "CLOSED")
    redis.call(
        "DEL",
        KEYS[3],
        KEYS[4],
        KEYS[5]
    )

    return 2
end

return 1
"""


HALF_OPEN_FAILURE_LUA = """
local current_token = redis.call("GET", KEYS[1])

if not current_token or tostring(current_token) ~= tostring(ARGV[1]) then
    return -1
end

local state = redis.call("GET", KEYS[2])

if state ~= "HALF_OPEN" then
    redis.call("DEL", KEYS[1])
    return 0
end

redis.call("DEL", KEYS[1])
redis.call("SET", KEYS[3], 0)

local is_retryable = tonumber(ARGV[2])

if is_retryable == 1 then
    redis.call("SET", KEYS[2], "OPEN")
    redis.call("SET", KEYS[4], ARGV[3])

    return 2
end

return 1
"""

# --- Circuit Breaker ---

class CircuitBreaker:
    """
    Distributed circuit breaker backed by synchronous Redis.
    Uses Redis as the single source of truth across workers and servers.
    """

    def __init__(
        self,
        redis_client: Any,
        config: CircuitBreakerConfig = CircuitBreakerConfig(),
        clock: Optional[Callable[[], float] | Any] = None,
    ) -> None:
        self.redis = redis_client
        self.config = config
        self._clock = clock

    def _now(self) -> float:
        """
        Return current Unix timestamp in seconds using injected clock or UTC time.
        """
        if self._clock is not None:
            if callable(self._clock):
                val = self._clock()
                if isinstance(val, (int, float)):
                    return float(val)
                if isinstance(val, datetime):
                    return val.timestamp()
            elif hasattr(self._clock, "now"):
                dt = self._clock.now()
                if isinstance(dt, datetime):
                    return dt.timestamp()
                return float(dt)
        return time.time()

    def _get_provider_hash(self, provider: str) -> str:
        if not isinstance(provider, str):
            provider_str = str(provider)
        else:
            provider_str = provider
        provider_clean = provider_str.strip().lower()
        if not provider_clean:
            raise ValueError("provider name must be non-blank.")
        return hashlib.sha256(provider_clean.encode("utf-8")).hexdigest()

    def _get_keys(self, provider_scope: str) -> tuple[str, str, str, str, str]:
        if len(provider_scope) == 64 and all(c in "0123456789abcdefABCDEF" for c in provider_scope):
            p_hash = provider_scope.lower()
        else:
            p_hash = self._get_provider_hash(provider_scope)

        base = f"fieldops:circuit:{self.config.namespace_version}:{p_hash}"
        return (
            f"{base}:state",
            f"{base}:failures",
            f"{base}:successes",
            f"{base}:opened_at",
            f"{base}:probe_lock",
        )

    def check_permission(self, provider: str) -> CircuitPermit:
        """
        Check if request is permitted for the given provider.
        Returns a CircuitPermit on success.
        Raises CircuitOpenError if blocked, or CircuitBreakerInfrastructureError on Redis failure.
        """
        provider_hash = self._get_provider_hash(provider)
        if not self.config.enabled:
            return CircuitPermit(provider_scope=provider_hash, is_half_open_probe=False, probe_token=None)

        state_key, failures_key, successes_key, opened_at_key, probe_lock_key = self._get_keys(provider_hash)
        now_ts = self._now()

        try:
            state_val = self.redis.get(state_key)
            state = CircuitState(state_val) if state_val else CircuitState.CLOSED
            print(f"[DEBUG CIRCUIT] namespace={self.config.namespace_version} state={state}")
            if state == CircuitState.OPEN:
                opened_at_val = self.redis.get(opened_at_key)
                opened_at = float(opened_at_val) if opened_at_val else 0.0

                if now_ts - opened_at >= self.config.open_cooldown_seconds:
                    # Cooldown expired -> transition to HALF_OPEN
                    with self.redis.pipeline(transaction=True) as pipe:
                        pipe.set(state_key, CircuitState.HALF_OPEN.value)
                        pipe.set(successes_key, 0)
                        pipe.execute()
                    state = CircuitState.HALF_OPEN
                else:
                    logger.warning("Circuit breaker is OPEN. Requests blocked for provider.")
                    raise CircuitOpenError("AI circuit breaker is OPEN.")

            if state == CircuitState.HALF_OPEN:
                # Acquire probe lock with cryptographically random token
                token = secrets.token_hex(16)
                acquired = self.redis.set(
                    probe_lock_key,
                    token,
                    nx=True,
                    ex=self.config.half_open_probe_ttl_seconds,
                )
                if acquired:
                    logger.info("Probe lock acquired for HALF_OPEN circuit breaker.")
                    return CircuitPermit(
                        provider_scope=provider_hash,
                        is_half_open_probe=True,
                        probe_token=token,
                    )
                else:
                    logger.warning("Circuit breaker is HALF_OPEN and probe lock is held.")
                    raise CircuitOpenError("AI circuit breaker is HALF_OPEN and probe is in progress.")

            if state == CircuitState.CLOSED:
                # Prune failures older than sliding window
                min_score = 0.0
                max_score = now_ts - self.config.failure_window_seconds
                with self.redis.pipeline(transaction=True) as pipe:
                    pipe.zremrangebyscore(failures_key, min_score, max_score)
                    pipe.zcard(failures_key)
                    results = pipe.execute()

                failure_count = results[1]
                if failure_count >= self.config.failure_threshold:
                    with self.redis.pipeline(transaction=True) as pipe:
                        pipe.set(state_key, CircuitState.OPEN.value)
                        pipe.set(opened_at_key, str(now_ts))
                        pipe.execute()
                    logger.warning("Circuit breaker failure threshold met. Transitioned to OPEN.")
                    raise CircuitOpenError("AI circuit breaker is OPEN.")

                return CircuitPermit(
                    provider_scope=provider_hash,
                    is_half_open_probe=False,
                    probe_token=None,
                )

        except CircuitOpenError:
            raise
        except Exception:
            logger.warning("Redis failure during circuit breaker check_permission.")
            raise CircuitBreakerInfrastructureError("Circuit breaker database lookup failed.") from None

    def release_probe_lock(
        self,
        permit: CircuitPermit,
    ) -> bool:
        """
        Release a HALF_OPEN probe lock only when the permit
        still owns the current Redis lock.
        """

        if (
            not self.config.enabled
            or not permit.is_half_open_probe
            or not permit.probe_token
        ):
            return False

        _, _, _, _, probe_lock_key = self._get_keys(
            permit.provider_scope
        )

        try:
            result = self.redis.eval(
                RELEASE_LOCK_LUA,
                1,
                probe_lock_key,
                permit.probe_token,
            )

            return bool(result)

        except Exception:
            logger.warning(
                "Redis failure during circuit breaker "
                "probe lock release."
            )

            raise CircuitBreakerInfrastructureError(
                "Circuit breaker probe lock release failed."
            ) from None

    def record_success(
        self,
        permit: CircuitPermit,
    ) -> None:
        """
        Record a successful provider completion.

        A HALF_OPEN result is counted only when the permit
        still owns the current probe lock.
        """

        if not self.config.enabled:
            return

        (
            state_key,
            failures_key,
            successes_key,
            opened_at_key,
            probe_lock_key,
        ) = self._get_keys(
            permit.provider_scope
        )

        try:
            if permit.is_half_open_probe:
                if not permit.probe_token:
                    raise ValueError(
                        "HALF_OPEN permit requires a probe token."
                    )

                result = self.redis.eval(
                    HALF_OPEN_SUCCESS_LUA,
                    5,
                    probe_lock_key,
                    state_key,
                    successes_key,
                    failures_key,
                    opened_at_key,
                    permit.probe_token,
                    self.config.half_open_success_threshold,
                )

                status = int(result)

                if status == -1:
                    logger.warning(
                        "Stale HALF_OPEN success permit ignored."
                    )
                    return

                if status == 2:
                    logger.info(
                        "Circuit breaker recovered and "
                        "transitioned to CLOSED."
                    )

                return

            state_value = self.redis.get(state_key)

            state = (
                CircuitState(state_value)
                if state_value
                else CircuitState.CLOSED
            )

            if state == CircuitState.CLOSED:
                now_timestamp = self._now()

                cutoff = (
                    now_timestamp
                    - self.config.failure_window_seconds
                )

                self.redis.zremrangebyscore(
                    failures_key,
                    0.0,
                    cutoff,
                )

        except ValueError:
            raise

        except Exception:
            logger.warning(
                "Redis failure during circuit breaker "
                "success recording."
            )

            raise CircuitBreakerInfrastructureError(
                "Circuit breaker success recording failed."
            ) from None
    def record_failure(
        self,
        permit: CircuitPermit,
        error: BaseException,
    ) -> None:
        """
        Record a provider failure.

        A HALF_OPEN permit may change circuit state only when
        it still owns the current probe lock.
        """

        if not self.config.enabled:
            return

        (
            state_key,
            failures_key,
            successes_key,
            opened_at_key,
            probe_lock_key,
        ) = self._get_keys(
            permit.provider_scope
        )

        now_timestamp = self._now()

        retryable = is_retryable_provider_error(
            error
        )

        try:
            if permit.is_half_open_probe:
                if not permit.probe_token:
                    raise ValueError(
                        "HALF_OPEN permit requires a probe token."
                    )

                result = self.redis.eval(
                    HALF_OPEN_FAILURE_LUA,
                    4,
                    probe_lock_key,
                    state_key,
                    successes_key,
                    opened_at_key,
                    permit.probe_token,
                    1 if retryable else 0,
                    str(now_timestamp),
                )

                status = int(result)

                if status == -1:
                    logger.warning(
                        "Stale HALF_OPEN failure permit ignored."
                    )
                    return

                if status == 2:
                    logger.warning(
                        "HALF_OPEN probe failed and circuit "
                        "transitioned to OPEN."
                    )

                return

            if not retryable:
                return

            state_value = self.redis.get(
                state_key
            )

            state = (
                CircuitState(state_value)
                if state_value
                else CircuitState.CLOSED
            )

            if state != CircuitState.CLOSED:
                return

            member_id = (
                f"{now_timestamp}:"
                f"{uuid.uuid4().hex}"
            )

            cutoff = (
                now_timestamp
                - self.config.failure_window_seconds
            )

            with self.redis.pipeline(
                transaction=True
            ) as pipe:
                pipe.zremrangebyscore(
                    failures_key,
                    0.0,
                    cutoff,
                )

                pipe.zadd(
                    failures_key,
                    {
                        member_id: now_timestamp,
                    },
                )

                pipe.zcard(
                    failures_key
                )

                pipe.expire(
                    failures_key,
                    self.config.failure_window_seconds * 2,
                )

                results = pipe.execute()

            failure_count = int(
                results[2]
            )

            if (
                failure_count
                >= self.config.failure_threshold
            ):
                with self.redis.pipeline(
                    transaction=True
                ) as pipe:
                    pipe.set(
                        state_key,
                        CircuitState.OPEN.value,
                    )

                    pipe.set(
                        opened_at_key,
                        str(now_timestamp),
                    )

                    pipe.execute()

                logger.warning(
                    "Retryable provider failure threshold "
                    "reached and circuit transitioned to OPEN."
                )

        except ValueError:
            raise

        except Exception:
            logger.warning(
                "Redis failure during circuit breaker "
                "failure recording."
            )

            raise CircuitBreakerInfrastructureError(
                "Circuit breaker failure recording failed."
            ) from None

    def snapshot(self, provider: str) -> CircuitBreakerSnapshot:
        """
        Return a current state snapshot without mutating circuit breaker state.
        """
        state_key, failures_key, successes_key, opened_at_key, _ = self._get_keys(provider)
        now_ts = self._now()

        try:
            state_val = self.redis.get(state_key)
            state = CircuitState(state_val) if state_val else CircuitState.CLOSED

            min_score = 0.0
            max_score = now_ts - self.config.failure_window_seconds
            self.redis.zremrangebyscore(failures_key, min_score, max_score)

            failures_count = self.redis.zcard(failures_key) or 0
            successes_val = self.redis.get(successes_key)
            successes_count = int(successes_val) if successes_val else 0

            opened_at_val = self.redis.get(opened_at_key)
            last_change = None
            if opened_at_val:
                try:
                    dt = datetime.fromtimestamp(float(opened_at_val), tz=timezone.utc)
                    last_change = dt.isoformat()
                except Exception:
                    last_change = str(opened_at_val)

            return CircuitBreakerSnapshot(
                state=state,
                failure_count=failures_count,
                consecutive_successes=successes_count,
                last_state_change=last_change,
            )
        except Exception:
            logger.warning("Redis failure during circuit breaker snapshot.")
            raise CircuitBreakerInfrastructureError("Circuit breaker snapshot failed.") from None
