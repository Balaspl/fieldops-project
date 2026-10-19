"""
budget.py

Task 4.5: Global Token Budget and Rate Limit Manager.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
from functools import lru_cache
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, Tuple
from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = logging.getLogger(__name__)


@lru_cache(maxsize=8)
def _get_token_encoding(model: str = "openai/gpt-oss-120b") -> Any:
    """Return a tokenizer compatible with the configured model family.

    GPT-OSS uses the o200k tokenizer family. Keep this lazy so importing the
    budget module does not require loading tokenizer data until needed.
    """
    try:
        import tiktoken
    except ImportError as exc:  # fail closed: never silently use word counts
        raise BudgetInfrastructureError(
            "Token estimation requires the 'tiktoken' dependency."
        ) from exc

    model_name = (model or "").strip().lower()
    try:
        return tiktoken.encoding_for_model(model_name)
    except (KeyError, ValueError):
        # GPT-OSS model identifiers may not be registered in every tiktoken
        # release. o200k_base is the intended fallback for this model family.
        return tiktoken.get_encoding("o200k_base")


def count_tokens(text: str, model: str = "openai/gpt-oss-120b") -> int:
    """Count text tokens with the configured model's compatible encoding."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    return len(_get_token_encoding(model).encode(text, disallowed_special=()))


# --- Custom Exceptions ---

class BudgetError(Exception):
    """
    Base exception for all token budget and rate limit issues.
    """
    pass


class BudgetExceededError(BudgetError):
    """
    Raised when daily token budget, RPM, or request limits are exceeded.
    """
    pass


class BudgetInfrastructureError(BudgetError):
    """
    Raised when Redis or another database error occurs (fail-closed policy).
    """
    pass


# --- Schemas ---

class TokenBudgetConfig(BaseModel):
    """
    Validated budget and rate limiting configuration.
    """
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    daily_token_limit: int = Field(default=1_400_000, gt=0)
    requests_per_minute: int = Field(default=20, gt=0)
    daily_request_limit: int = Field(default=1_500, gt=0)
    namespace_version: str = Field(default="v1", min_length=1)
    atomic_strategy: str = Field(default="lua")
    reservation_ttl_seconds: int = Field(default=3600, gt=0)
    per_request: Dict[str, int] = Field(
        default_factory=lambda: {
            "sms": 80,
            "email": 500,
            "push": 200,
            "portal": 200,
            "sentiment": 10,
            "general": 4096,
        }
    )

    @field_validator("atomic_strategy")
    @classmethod
    def validate_atomic_strategy(cls, v: str) -> str:
        val = v.strip().lower()
        if val not in {"lua", "transaction"}:
            raise ValueError("atomic_strategy must be either 'lua' or 'transaction'")
        return val

    @field_validator("per_request")
    @classmethod
    def validate_per_request(cls, v: Dict[str, int]) -> Dict[str, int]:
        allowed_categories = {"sms", "email", "push", "portal", "sentiment", "general"}
        for category, limit in v.items():
            if category not in allowed_categories:
                raise ValueError(f"Unsupported request category: '{category}'")
            if limit <= 0:
                raise ValueError(f"Limit for category '{category}' must be greater than zero.")
        return v

    @classmethod
    def from_mapping(cls, mapping: Dict[str, Any]) -> TokenBudgetConfig:
        """
        Build and validate from configuration mapping defensively.
        """
        return cls(**mapping)


class BudgetUsage(BaseModel):
    """
    Snapshot of current token budget and rate limit usage.
    """
    model_config = ConfigDict(frozen=True)

    daily_tokens_used: int = Field(ge=0)
    daily_requests_used: int = Field(ge=0)
    rpm_used: int = Field(ge=0)


class BudgetDecision(BaseModel):
    """
    Result of a budget availability check or reservation.
    """
    model_config = ConfigDict(frozen=True)

    allowed: bool
    reason: Optional[str] = None
    remaining_tokens: int = Field(ge=0)
    remaining_requests: int = Field(ge=0)


# --- Helper functions for key building ---

def _get_tenant_hash(tenant_id: str | None) -> str:
    if tenant_id is None:
        return "global"
    stripped = tenant_id.strip()
    if not stripped:
        raise ValueError("tenant_id must not be blank when supplied.")
    return hashlib.sha256(stripped.encode("utf-8")).hexdigest()


def _get_keys(
    version: str,
    provider: str,
    date_str: str,
    minute_str: str,
) -> Tuple[str, str, str]:
    """
    Build global provider-account keys that are shared across all tenants and models.
    """
    provider_clean = provider.strip().lower()
    if not provider_clean:
        raise ValueError("provider name must be non-blank.")
    base = f"fieldops:budget:{version}:{provider_clean}"
    return (
        f"{base}:tokens:daily:{date_str}",
        f"{base}:requests:daily:{date_str}",
        f"{base}:requests:rpm:{minute_str}",
    )


def _get_ttls() -> Tuple[int, int]:
    now = datetime.now(timezone.utc)
    tomorrow = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), timezone.utc)
    daily_ttl = max(int((tomorrow - now).total_seconds()), 1)
    return daily_ttl, 60


# --- Asynchronous Budget Manager ---

class TokenBudgetManager:
    """
    Authoritative asynchronous manager for checking, reserving, and tracking AI token budgets.
    Uses Redis as the single source of truth.
    """

    LUA_RESERVE_SCRIPT = """
    local daily_tokens_key = KEYS[1]
    local daily_requests_key = KEYS[2]
    local rpm_key = KEYS[3]
    local res_key = KEYS[4]

    local requested_tokens = tonumber(ARGV[1])
    local daily_token_limit = tonumber(ARGV[2])
    local daily_req_limit = tonumber(ARGV[3])
    local rpm_limit = tonumber(ARGV[4])
    local daily_ttl = tonumber(ARGV[5])
    local rpm_ttl = tonumber(ARGV[6])
    local res_data = ARGV[7]
    local res_ttl = tonumber(ARGV[8])

    -- 1. Check daily requests limit
    local current_daily_reqs = tonumber(redis.call('GET', daily_requests_key) or "0")
    if current_daily_reqs >= daily_req_limit then
        return {0, "DAILY_REQUESTS_EXCEEDED", current_daily_reqs}
    end

    -- 2. Check RPM limit
    local current_rpm = tonumber(redis.call('GET', rpm_key) or "0")
    if current_rpm >= rpm_limit then
        return {0, "RPM_EXCEEDED", current_rpm}
    end

    -- 3. Check daily token budget
    local current_tokens = tonumber(redis.call('GET', daily_tokens_key) or "0")
    if current_tokens + requested_tokens > daily_token_limit then
        return {0, "DAILY_TOKENS_EXCEEDED", current_tokens}
    end

    -- 4. Atomically increment daily requests and set TTL
    local new_daily_reqs = redis.call('INCR', daily_requests_key)
    if tonumber(new_daily_reqs) == 1 then
        redis.call('EXPIRE', daily_requests_key, daily_ttl)
    end

    -- 5. Atomically increment RPM and set TTL
    local new_rpm = redis.call('INCR', rpm_key)
    if tonumber(new_rpm) == 1 then
        redis.call('EXPIRE', rpm_key, rpm_ttl)
    end

    -- 6. Atomically increment daily tokens (reserve estimate)
    local new_tokens = redis.call('INCRBY', daily_tokens_key, requested_tokens)
    if tonumber(new_tokens) == requested_tokens then
        redis.call('EXPIRE', daily_tokens_key, daily_ttl)
    end

    -- 7. Write the reservation record
    redis.call('SET', res_key, res_data, 'EX', res_ttl)

    return {1, "SUCCESS", new_tokens, new_daily_reqs, new_rpm}
    """

    def __init__(
        self,
        redis_client: Any,
        config: TokenBudgetConfig = TokenBudgetConfig(),
    ) -> None:
        self.redis = redis_client
        self.config = config

    async def check(
        self,
        *,
        estimated_input_tokens: int,
        max_output_tokens: int,
        category: str,
        provider: str,
        model: str,
        tenant_id: Optional[str] = None,
    ) -> BudgetDecision:
        """
        Check if budget and rate limits are available globally.
        """
        if estimated_input_tokens < 0:
            raise ValueError("estimated_input_tokens must be non-negative.")
        if max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be greater than zero.")
        if not provider or not provider.strip():
            raise ValueError("provider name must be non-blank.")
        if not model or not model.strip():
            raise ValueError("model name must be non-blank.")
        if tenant_id is not None and not tenant_id.strip():
            raise ValueError("tenant_id must not be blank when supplied.")

        category_clean = category.strip().lower()
        if category_clean not in self.config.per_request:
            raise ValueError(f"Unsupported request category: '{category}'")

        per_req_limit = self.config.per_request[category_clean]
        if max_output_tokens > per_req_limit:
            return BudgetDecision(
                allowed=False,
                reason=f"Per-request limit exceeded for category '{category}' (Requested: {max_output_tokens}, Limit: {per_req_limit})",
                remaining_tokens=0,
                remaining_requests=0,
            )

        tokens_requested = estimated_input_tokens + max_output_tokens

        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y%m%d")
        minute_str = now.strftime("%Y%m%d%H%M")

        daily_tokens_key, daily_requests_key, rpm_key = _get_keys(
            self.config.namespace_version, provider, date_str, minute_str
        )

        try:
            async with self.redis.pipeline(transaction=True) as pipe:
                pipe.get(daily_tokens_key)
                pipe.get(daily_requests_key)
                pipe.get(rpm_key)
                results = await pipe.execute()
        except Exception:
            logger.warning("Redis connection failed during async budget query.")
            raise BudgetInfrastructureError("Budget database lookup failed.") from None

        daily_tokens = int(results[0]) if results[0] else 0
        daily_reqs = int(results[1]) if results[1] else 0
        rpm_reqs = int(results[2]) if results[2] else 0

        if daily_reqs >= self.config.daily_request_limit:
            return BudgetDecision(
                allowed=False,
                reason="Daily request limit exceeded.",
                remaining_tokens=max(self.config.daily_token_limit - daily_tokens, 0),
                remaining_requests=0,
            )

        if rpm_reqs >= self.config.requests_per_minute:
            return BudgetDecision(
                allowed=False,
                reason="Requests per minute limit exceeded.",
                remaining_tokens=max(self.config.daily_token_limit - daily_tokens, 0),
                remaining_requests=max(self.config.daily_request_limit - daily_reqs, 0),
            )

        if daily_tokens + tokens_requested > self.config.daily_token_limit:
            return BudgetDecision(
                allowed=False,
                reason="Daily token limit exceeded.",
                remaining_tokens=max(self.config.daily_token_limit - daily_tokens, 0),
                remaining_requests=max(self.config.daily_request_limit - daily_reqs, 0),
            )

        return BudgetDecision(
            allowed=True,
            remaining_tokens=max(self.config.daily_token_limit - (daily_tokens + tokens_requested), 0),
            remaining_requests=max(self.config.daily_request_limit - (daily_reqs + 1), 0),
        )

    async def reserve(
        self,
        *,
        estimated_input_tokens: int,
        max_output_tokens: int,
        category: str,
        provider: str,
        model: str,
        tenant_id: Optional[str] = None,
    ) -> str:
        """
        Atomically reserve tokens and increment requests budget.
        """
        if estimated_input_tokens < 0:
            raise ValueError("estimated_input_tokens must be non-negative.")
        if max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be greater than zero.")
        if not provider or not provider.strip():
            raise ValueError("provider name must be non-blank.")
        if not model or not model.strip():
            raise ValueError("model name must be non-blank.")
        if tenant_id is not None and not tenant_id.strip():
            raise ValueError("tenant_id must not be blank when supplied.")

        category_clean = category.strip().lower()
        if category_clean not in self.config.per_request:
            raise ValueError(f"Unsupported request category: '{category}'")

        per_req_limit = self.config.per_request[category_clean]
        if max_output_tokens > per_req_limit:
            raise BudgetExceededError(
                f"Per-request limit exceeded for category '{category}' (Requested: {max_output_tokens}, Limit: {per_req_limit})"
            )

        tokens_requested = estimated_input_tokens + max_output_tokens

        reservation_id = secrets.token_hex(16)
        provider_clean = provider.strip().lower()
        model_clean = model.strip().lower()
        scope_str = f"{provider_clean}:{model_clean}"
        scope_hash = hashlib.sha256(scope_str.encode("utf-8")).hexdigest()
        provider_hash = hashlib.sha256(provider_clean.encode("utf-8")).hexdigest()

        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y%m%d")
        minute_str = now.strftime("%Y%m%d%H%M")
        created_at_str = now.isoformat()
        expires_at_str = (now + timedelta(seconds=self.config.reservation_ttl_seconds)).isoformat()

        daily_tokens_key, daily_requests_key, rpm_key = _get_keys(
            self.config.namespace_version, provider, date_str, minute_str
        )
        res_key = f"fieldops:budget:{self.config.namespace_version}:reservation:{reservation_id}"
        daily_ttl, rpm_ttl = _get_ttls()

        res_record = {
            "reservation_id": reservation_id,
            "provider_scope": scope_hash,
            "provider_hash": provider_hash,
            "date_str": date_str,
            "daily_tokens_key": daily_tokens_key,
            "reserved_total": tokens_requested,
            "reserved_tokens": tokens_requested,
            "estimated_input": estimated_input_tokens,
            "maximum_output": max_output_tokens,
            "status": "ACTIVE",
            "created_at": created_at_str,
            "expires_at": expires_at_str,
        }
        res_data = json.dumps(res_record)

        strategy = self.config.atomic_strategy.lower().strip()
        if strategy == "lua":
            try:
                res = await self.redis.eval(
                    self.LUA_RESERVE_SCRIPT,
                    4,
                    daily_tokens_key, daily_requests_key, rpm_key, res_key,
                    tokens_requested, self.config.daily_token_limit,
                    self.config.daily_request_limit, self.config.requests_per_minute,
                    daily_ttl, rpm_ttl, res_data, self.config.reservation_ttl_seconds
                )
            except Exception:
                logger.warning("Redis evaluation failure during async budget reservation.")
                raise BudgetInfrastructureError("Budget database write failed.") from None

            success = res[0] == 1
            reason = res[1] if not success else None
            if not success:
                raise BudgetExceededError(f"Budget request rejected: {reason}")

        elif strategy == "transaction":
            res = await self._reserve_transaction(
                daily_tokens_key, daily_requests_key, rpm_key, res_key,
                tokens_requested, daily_ttl, rpm_ttl, res_data
            )
        else:
            raise BudgetInfrastructureError("Unsupported atomic strategy configured.")

        return reservation_id

    async def _reserve_transaction(
        self,
        daily_tokens_key: str,
        daily_requests_key: str,
        rpm_key: str,
        res_key: str,
        tokens_requested: int,
        daily_ttl: int,
        rpm_ttl: int,
        res_data: str,
    ) -> list[Any]:
        from redis.exceptions import WatchError

        for _ in range(10):
            async with self.redis.pipeline(transaction=True) as pipe:
                try:
                    await pipe.watch(daily_tokens_key, daily_requests_key, rpm_key)

                    daily_tokens_val = await pipe.get(daily_tokens_key)
                    daily_reqs_val = await pipe.get(daily_requests_key)
                    rpm_reqs_val = await pipe.get(rpm_key)

                    daily_tokens = int(daily_tokens_val) if daily_tokens_val else 0
                    daily_reqs = int(daily_reqs_val) if daily_reqs_val else 0
                    rpm_reqs = int(rpm_reqs_val) if rpm_reqs_val else 0

                    if daily_reqs >= self.config.daily_request_limit:
                        raise BudgetExceededError("Budget request rejected: DAILY_REQUESTS_EXCEEDED")
                    if rpm_reqs >= self.config.requests_per_minute:
                        raise BudgetExceededError("Budget request rejected: RPM_EXCEEDED")
                    if daily_tokens + tokens_requested > self.config.daily_token_limit:
                        raise BudgetExceededError("Budget request rejected: DAILY_TOKENS_EXCEEDED")

                    pipe.multi()
                    pipe.incrby(daily_tokens_key, tokens_requested)
                    pipe.incr(daily_requests_key)
                    pipe.incr(rpm_key)

                    if daily_tokens == 0:
                        pipe.expire(daily_tokens_key, daily_ttl)
                    if daily_reqs == 0:
                        pipe.expire(daily_requests_key, daily_ttl)
                    if rpm_reqs == 0:
                        pipe.expire(rpm_key, rpm_ttl)

                    pipe.set(res_key, res_data, ex=self.config.reservation_ttl_seconds)

                    res = await pipe.execute()
                    return [1, "SUCCESS", res[0], res[1], res[2]]
                except WatchError:
                    continue
                except BudgetExceededError:
                    raise
                except Exception:
                    logger.warning("Redis transaction database failure.")
                    raise BudgetInfrastructureError("Budget transaction failed.") from None

        raise BudgetInfrastructureError("Budget reservation timed out due to high concurrency.")

    async def reconcile(
        self,
        *,
        reservation_id: str,
        actual_input_tokens: int,
        actual_output_tokens: int,
        provider: Optional[str] = None,
    ) -> None:
        """
        Atomically reconcile actual tokens used against the reservation.
        """
        if not reservation_id or not reservation_id.strip():
            raise ValueError("reservation_id must be non-blank.")
        if actual_input_tokens < 0 or actual_output_tokens < 0:
            raise ValueError("Actual tokens must be non-negative.")
        if provider is not None and not provider.strip():
            raise ValueError("provider must not be blank when supplied.")

        res_key = f"fieldops:budget:{self.config.namespace_version}:reservation:{reservation_id}"

        from redis.exceptions import WatchError

        for _ in range(10):
            async with self.redis.pipeline(transaction=True) as pipe:
                try:
                    await pipe.watch(res_key)

                    res_val = await pipe.get(res_key)
                    if not res_val:
                        raise ValueError("Reservation not found.")

                    res_record = json.loads(res_val)

                    if provider is not None and provider.strip():
                        prov_clean = provider.strip().lower()
                        prov_hash = hashlib.sha256(prov_clean.encode("utf-8")).hexdigest()
                        stored_hash = res_record.get("provider_hash")
                        if stored_hash and stored_hash != prov_hash:
                            raise ValueError("Provider scope mismatch.")

                    status = res_record.get("status")
                    if status == "RECONCILED":
                        return
                    if status == "CANCELLED":
                        raise ValueError("Cannot reconcile cancelled reservation.")

                    daily_tokens_key = res_record.get("daily_tokens_key")
                    if not daily_tokens_key:
                        raise ValueError("Invalid reservation record: missing daily counter scope.")

                    await pipe.watch(daily_tokens_key)

                    reserved_tokens = res_record.get("reserved_total", res_record.get("reserved_tokens", 0))
                    actual_tokens = actual_input_tokens + actual_output_tokens
                    delta = actual_tokens - reserved_tokens

                    daily_tokens_val = await pipe.get(daily_tokens_key)
                    current_daily = int(daily_tokens_val) if daily_tokens_val else 0

                    if delta < 0 and current_daily + delta < 0:
                        delta = -current_daily

                    now = datetime.now(timezone.utc)
                    res_record["status"] = "RECONCILED"
                    res_record["actual_tokens"] = actual_tokens
                    res_record["actual_input"] = actual_input_tokens
                    res_record["actual_output"] = actual_output_tokens
                    if actual_tokens > reserved_tokens:
                        res_record["overrun"] = True
                    res_record["reconciled_at"] = now.isoformat()

                    pipe.multi()
                    pipe.set(res_key, json.dumps(res_record), ex=self.config.reservation_ttl_seconds)
                    pipe.incrby(daily_tokens_key, delta)

                    await pipe.execute()

                    if actual_tokens > reserved_tokens:
                        raise BudgetExceededError("Actual usage exceeded reserved amount.")
                    return
                except WatchError:
                    continue
                except (ValueError, BudgetExceededError):
                    raise
                except Exception:
                    logger.warning("Redis reconciliation execution failed.")
                    raise BudgetInfrastructureError("Budget reconciliation failed.") from None

        raise BudgetInfrastructureError("Budget reconciliation timed out.")

    async def cancel(
        self,
        *,
        reservation_id: str,
        provider: Optional[str] = None,
    ) -> None:
        """
        Atomically cancel reservation and release reserved tokens.
        """
        if not reservation_id or not reservation_id.strip():
            raise ValueError("reservation_id must be non-blank.")
        if provider is not None and not provider.strip():
            raise ValueError("provider must not be blank when supplied.")

        res_key = f"fieldops:budget:{self.config.namespace_version}:reservation:{reservation_id}"

        from redis.exceptions import WatchError

        for _ in range(10):
            async with self.redis.pipeline(transaction=True) as pipe:
                try:
                    await pipe.watch(res_key)

                    res_val = await pipe.get(res_key)
                    if not res_val:
                        raise ValueError("Reservation not found.")

                    res_record = json.loads(res_val)

                    if provider is not None and provider.strip():
                        prov_clean = provider.strip().lower()
                        prov_hash = hashlib.sha256(prov_clean.encode("utf-8")).hexdigest()
                        stored_hash = res_record.get("provider_hash")
                        if stored_hash and stored_hash != prov_hash:
                            raise ValueError("Provider scope mismatch.")

                    status = res_record.get("status")
                    if status == "RECONCILED":
                        raise ValueError("Cannot cancel reconciled reservation.")
                    if status == "CANCELLED":
                        return

                    daily_tokens_key = res_record.get("daily_tokens_key")
                    if not daily_tokens_key:
                        raise ValueError("Invalid reservation record: missing daily counter scope.")

                    await pipe.watch(daily_tokens_key)

                    reserved_tokens = res_record.get("reserved_total", res_record.get("reserved_tokens", 0))

                    daily_tokens_val = await pipe.get(daily_tokens_key)
                    current_daily = int(daily_tokens_val) if daily_tokens_val else 0
                    release_amount = reserved_tokens
                    if current_daily - release_amount < 0:
                        release_amount = current_daily

                    now = datetime.now(timezone.utc)
                    res_record["status"] = "CANCELLED"
                    res_record["cancelled_at"] = now.isoformat()

                    pipe.multi()
                    pipe.set(res_key, json.dumps(res_record), ex=self.config.reservation_ttl_seconds)
                    pipe.incrby(daily_tokens_key, -release_amount)

                    await pipe.execute()
                    return
                except WatchError:
                    continue
                except ValueError:
                    raise
                except Exception:
                    logger.warning("Redis cancellation execution failed.")
                    raise BudgetInfrastructureError("Budget cancellation failed.") from None

        raise BudgetInfrastructureError("Budget cancellation timed out.")

    async def remaining(
        self,
        provider: str,
        model: str,
        tenant_id: Optional[str] = None,
    ) -> Tuple[int, int]:
        """
        Return remaining daily tokens and daily requests globally.
        """
        if not provider or not provider.strip():
            raise ValueError("provider name must be non-blank.")
        if not model or not model.strip():
            raise ValueError("model name must be non-blank.")
        if tenant_id is not None and not tenant_id.strip():
            raise ValueError("tenant_id must not be blank when supplied.")

        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y%m%d")
        minute_str = now.strftime("%Y%m%d%H%M")
        daily_tokens_key, daily_requests_key, _ = _get_keys(
            self.config.namespace_version, provider, date_str, minute_str
        )

        try:
            async with self.redis.pipeline(transaction=True) as pipe:
                pipe.get(daily_tokens_key)
                pipe.get(daily_requests_key)
                results = await pipe.execute()
        except Exception:
            logger.warning("Redis connection failed during async remaining query.")
            raise BudgetInfrastructureError("Budget remaining lookup failed.") from None

        daily_tokens = int(results[0]) if results[0] else 0
        daily_reqs = int(results[1]) if results[1] else 0

        return (
            max(self.config.daily_token_limit - daily_tokens, 0),
            max(self.config.daily_request_limit - daily_reqs, 0),
        )

    async def usage(
        self,
        provider: str,
        model: str,
        tenant_id: Optional[str] = None,
    ) -> BudgetUsage:
        """
        Return current global usage.
        """
        if not provider or not provider.strip():
            raise ValueError("provider name must be non-blank.")
        if not model or not model.strip():
            raise ValueError("model name must be non-blank.")
        if tenant_id is not None and not tenant_id.strip():
            raise ValueError("tenant_id must not be blank when supplied.")

        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y%m%d")
        minute_str = now.strftime("%Y%m%d%H%M")
        daily_tokens_key, daily_requests_key, rpm_key = _get_keys(
            self.config.namespace_version, provider, date_str, minute_str
        )

        try:
            async with self.redis.pipeline(transaction=True) as pipe:
                pipe.get(daily_tokens_key)
                pipe.get(daily_requests_key)
                pipe.get(rpm_key)
                results = await pipe.execute()
        except Exception:
            logger.warning("Redis connection failed during async usage query.")
            raise BudgetInfrastructureError("Budget usage lookup failed.") from None

        return BudgetUsage(
            daily_tokens_used=int(results[0]) if results[0] else 0,
            daily_requests_used=int(results[1]) if results[1] else 0,
            rpm_used=int(results[2]) if results[2] else 0,
        )

    async def reset(self) -> None:
        """
        Reset all global counters and reservation keys in Redis.
        """
        pattern = f"fieldops:budget:{self.config.namespace_version}:*"
        cursor = 0
        try:
            while True:
                cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)
                if keys:
                    await self.redis.delete(*keys)
                if cursor == 0:
                    break
        except Exception:
            logger.warning("Redis reset operation failed.")


# --- Synchronous Budget Manager ---

class SyncTokenBudgetManager:
    """
    Authoritative synchronous manager for checking, reserving, and tracking AI token budgets.
    Uses the project's synchronous Redis client.
    """

    def __init__(
        self,
        redis_client: Any,
        config: TokenBudgetConfig = TokenBudgetConfig(),
    ) -> None:
        self.redis = redis_client
        self.config = config

    def check(
        self,
        *,
        estimated_input_tokens: int,
        max_output_tokens: int,
        category: str,
        provider: str,
        model: str,
        tenant_id: Optional[str] = None,
    ) -> BudgetDecision:
        """
        Check if budget and rate limits are available globally.
        """
        if estimated_input_tokens < 0:
            raise ValueError("estimated_input_tokens must be non-negative.")
        if max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be greater than zero.")
        if not provider or not provider.strip():
            raise ValueError("provider name must be non-blank.")
        if not model or not model.strip():
            raise ValueError("model name must be non-blank.")
        if tenant_id is not None and not tenant_id.strip():
            raise ValueError("tenant_id must not be blank when supplied.")

        category_clean = category.strip().lower()
        if category_clean not in self.config.per_request:
            raise ValueError(f"Unsupported request category: '{category}'")

        per_req_limit = self.config.per_request[category_clean]
        if max_output_tokens > per_req_limit:
            return BudgetDecision(
                allowed=False,
                reason=f"Per-request limit exceeded for category '{category}' (Requested: {max_output_tokens}, Limit: {per_req_limit})",
                remaining_tokens=0,
                remaining_requests=0,
            )

        tokens_requested = estimated_input_tokens + max_output_tokens

        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y%m%d")
        minute_str = now.strftime("%Y%m%d%H%M")

        daily_tokens_key, daily_requests_key, rpm_key = _get_keys(
            self.config.namespace_version, provider, date_str, minute_str
        )

        try:
            with self.redis.pipeline(transaction=True) as pipe:
                pipe.get(daily_tokens_key)
                pipe.get(daily_requests_key)
                pipe.get(rpm_key)
                results = pipe.execute()
        except Exception:
            logger.warning("Redis connection failed during sync budget query.")
            raise BudgetInfrastructureError("Budget database lookup failed.") from None

        daily_tokens = int(results[0]) if results[0] else 0
        daily_reqs = int(results[1]) if results[1] else 0
        rpm_reqs = int(results[2]) if results[2] else 0

        if daily_reqs >= self.config.daily_request_limit:
            return BudgetDecision(
                allowed=False,
                reason="Daily request limit exceeded.",
                remaining_tokens=max(self.config.daily_token_limit - daily_tokens, 0),
                remaining_requests=0,
            )

        if rpm_reqs >= self.config.requests_per_minute:
            return BudgetDecision(
                allowed=False,
                reason="Requests per minute limit exceeded.",
                remaining_tokens=max(self.config.daily_token_limit - daily_tokens, 0),
                remaining_requests=max(self.config.daily_request_limit - daily_reqs, 0),
            )

        if daily_tokens + tokens_requested > self.config.daily_token_limit:
            return BudgetDecision(
                allowed=False,
                reason="Daily token limit exceeded.",
                remaining_tokens=max(self.config.daily_token_limit - daily_tokens, 0),
                remaining_requests=max(self.config.daily_request_limit - daily_reqs, 0),
            )

        return BudgetDecision(
            allowed=True,
            remaining_tokens=max(self.config.daily_token_limit - (daily_tokens + tokens_requested), 0),
            remaining_requests=max(self.config.daily_request_limit - (daily_reqs + 1), 0),
        )

    def reserve(
        self,
        *,
        estimated_input_tokens: int,
        max_output_tokens: int,
        category: str,
        provider: str,
        model: str,
        tenant_id: Optional[str] = None,
    ) -> str:
        """
        Atomically reserve tokens and increment requests budget.
        """
        if estimated_input_tokens < 0:
            raise ValueError("estimated_input_tokens must be non-negative.")
        if max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be greater than zero.")
        if not provider or not provider.strip():
            raise ValueError("provider name must be non-blank.")
        if not model or not model.strip():
            raise ValueError("model name must be non-blank.")
        if tenant_id is not None and not tenant_id.strip():
            raise ValueError("tenant_id must not be blank when supplied.")

        category_clean = category.strip().lower()
        if category_clean not in self.config.per_request:
            raise ValueError(f"Unsupported request category: '{category}'")

        per_req_limit = self.config.per_request[category_clean]
        if max_output_tokens > per_req_limit:
            raise BudgetExceededError(
                f"Per-request limit exceeded for category '{category}' (Requested: {max_output_tokens}, Limit: {per_req_limit})"
            )

        tokens_requested = estimated_input_tokens + max_output_tokens

        reservation_id = secrets.token_hex(16)
        provider_clean = provider.strip().lower()
        model_clean = model.strip().lower()
        scope_str = f"{provider_clean}:{model_clean}"
        scope_hash = hashlib.sha256(scope_str.encode("utf-8")).hexdigest()
        provider_hash = hashlib.sha256(provider_clean.encode("utf-8")).hexdigest()

        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y%m%d")
        minute_str = now.strftime("%Y%m%d%H%M")
        created_at_str = now.isoformat()
        expires_at_str = (now + timedelta(seconds=self.config.reservation_ttl_seconds)).isoformat()

        daily_tokens_key, daily_requests_key, rpm_key = _get_keys(
            self.config.namespace_version, provider, date_str, minute_str
        )
        res_key = f"fieldops:budget:{self.config.namespace_version}:reservation:{reservation_id}"
        daily_ttl, rpm_ttl = _get_ttls()

        res_record = {
            "reservation_id": reservation_id,
            "provider_scope": scope_hash,
            "provider_hash": provider_hash,
            "date_str": date_str,
            "daily_tokens_key": daily_tokens_key,
            "reserved_total": tokens_requested,
            "reserved_tokens": tokens_requested,
            "estimated_input": estimated_input_tokens,
            "maximum_output": max_output_tokens,
            "status": "ACTIVE",
            "created_at": created_at_str,
            "expires_at": expires_at_str,
        }
        res_data = json.dumps(res_record)

        strategy = self.config.atomic_strategy.lower().strip()
        if strategy == "lua":
            try:
                res = self.redis.eval(
                    TokenBudgetManager.LUA_RESERVE_SCRIPT,
                    4,
                    daily_tokens_key, daily_requests_key, rpm_key, res_key,
                    tokens_requested, self.config.daily_token_limit,
                    self.config.daily_request_limit, self.config.requests_per_minute,
                    daily_ttl, rpm_ttl, res_data, self.config.reservation_ttl_seconds
                )
            except Exception:
                logger.warning("Redis evaluation failure during sync budget reservation.")
                raise BudgetInfrastructureError("Budget database write failed.") from None

            success = res[0] == 1
            reason = res[1] if not success else None
            if not success:
                raise BudgetExceededError(f"Budget request rejected: {reason}")

        elif strategy == "transaction":
            res = self._reserve_transaction(
                daily_tokens_key, daily_requests_key, rpm_key, res_key,
                tokens_requested, daily_ttl, rpm_ttl, res_data
            )
        else:
            raise BudgetInfrastructureError("Unsupported atomic strategy configured.")

        return reservation_id

    def _reserve_transaction(
        self,
        daily_tokens_key: str,
        daily_requests_key: str,
        rpm_key: str,
        res_key: str,
        tokens_requested: int,
        daily_ttl: int,
        rpm_ttl: int,
        res_data: str,
    ) -> list[Any]:
        from redis.exceptions import WatchError

        for _ in range(10):
            with self.redis.pipeline(transaction=True) as pipe:
                try:
                    pipe.watch(daily_tokens_key, daily_requests_key, rpm_key)

                    daily_tokens_val = pipe.get(daily_tokens_key)
                    daily_reqs_val = pipe.get(daily_requests_key)
                    rpm_reqs_val = pipe.get(rpm_key)

                    daily_tokens = int(daily_tokens_val) if daily_tokens_val else 0
                    daily_reqs = int(daily_reqs_val) if daily_reqs_val else 0
                    rpm_reqs = int(rpm_reqs_val) if rpm_reqs_val else 0

                    if daily_reqs >= self.config.daily_request_limit:
                        raise BudgetExceededError("Budget request rejected: DAILY_REQUESTS_EXCEEDED")
                    if rpm_reqs >= self.config.requests_per_minute:
                        raise BudgetExceededError("Budget request rejected: RPM_EXCEEDED")
                    if daily_tokens + tokens_requested > self.config.daily_token_limit:
                        raise BudgetExceededError("Budget request rejected: DAILY_TOKENS_EXCEEDED")

                    pipe.multi()
                    pipe.incrby(daily_tokens_key, tokens_requested)
                    pipe.incr(daily_requests_key)
                    pipe.incr(rpm_key)

                    if daily_tokens == 0:
                        pipe.expire(daily_tokens_key, daily_ttl)
                    if daily_reqs == 0:
                        pipe.expire(daily_requests_key, daily_ttl)
                    if rpm_reqs == 0:
                        pipe.expire(rpm_key, rpm_ttl)

                    pipe.set(res_key, res_data, ex=self.config.reservation_ttl_seconds)

                    res = pipe.execute()
                    return [1, "SUCCESS", res[0], res[1], res[2]]
                except WatchError:
                    continue
                except BudgetExceededError:
                    raise
                except Exception:
                    logger.warning("Redis transaction database failure.")
                    raise BudgetInfrastructureError("Budget transaction failed.") from None

        raise BudgetInfrastructureError("Budget reservation timed out due to high concurrency.")

    def reconcile(
        self,
        *,
        reservation_id: str,
        actual_input_tokens: int,
        actual_output_tokens: int,
        provider: Optional[str] = None,
    ) -> None:
        """
        Atomically reconcile actual tokens used against the reservation.
        """
        if not reservation_id or not reservation_id.strip():
            raise ValueError("reservation_id must be non-blank.")
        if actual_input_tokens < 0 or actual_output_tokens < 0:
            raise ValueError("Actual tokens must be non-negative.")
        if provider is not None and not provider.strip():
            raise ValueError("provider must not be blank when supplied.")

        res_key = f"fieldops:budget:{self.config.namespace_version}:reservation:{reservation_id}"

        from redis.exceptions import WatchError

        for _ in range(10):
            with self.redis.pipeline(transaction=True) as pipe:
                try:
                    pipe.watch(res_key)

                    res_val = pipe.get(res_key)
                    if not res_val:
                        raise ValueError("Reservation not found.")

                    res_record = json.loads(res_val)

                    if provider is not None and provider.strip():
                        prov_clean = provider.strip().lower()
                        prov_hash = hashlib.sha256(prov_clean.encode("utf-8")).hexdigest()
                        stored_hash = res_record.get("provider_hash")
                        if stored_hash and stored_hash != prov_hash:
                            raise ValueError("Provider scope mismatch.")

                    status = res_record.get("status")
                    if status == "RECONCILED":
                        return
                    if status == "CANCELLED":
                        raise ValueError("Cannot reconcile cancelled reservation.")

                    daily_tokens_key = res_record.get("daily_tokens_key")
                    if not daily_tokens_key:
                        raise ValueError("Invalid reservation record: missing daily counter scope.")

                    pipe.watch(daily_tokens_key)

                    reserved_tokens = res_record.get("reserved_total", res_record.get("reserved_tokens", 0))
                    actual_tokens = actual_input_tokens + actual_output_tokens
                    delta = actual_tokens - reserved_tokens

                    daily_tokens_val = pipe.get(daily_tokens_key)
                    current_daily = int(daily_tokens_val) if daily_tokens_val else 0

                    if delta < 0 and current_daily + delta < 0:
                        delta = -current_daily

                    now = datetime.now(timezone.utc)
                    res_record["status"] = "RECONCILED"
                    res_record["actual_tokens"] = actual_tokens
                    res_record["actual_input"] = actual_input_tokens
                    res_record["actual_output"] = actual_output_tokens
                    if actual_tokens > reserved_tokens:
                        res_record["overrun"] = True
                    res_record["reconciled_at"] = now.isoformat()

                    pipe.multi()
                    pipe.set(res_key, json.dumps(res_record), ex=self.config.reservation_ttl_seconds)
                    pipe.incrby(daily_tokens_key, delta)

                    pipe.execute()

                    if actual_tokens > reserved_tokens:
                        raise BudgetExceededError("Actual usage exceeded reserved amount.")
                    return
                except WatchError:
                    continue
                except (ValueError, BudgetExceededError):
                    raise
                except Exception:
                    logger.warning("Redis reconciliation execution failed.")
                    raise BudgetInfrastructureError("Budget reconciliation failed.") from None

        raise BudgetInfrastructureError("Budget reconciliation timed out.")

    def cancel(
        self,
        *,
        reservation_id: str,
        provider: Optional[str] = None,
    ) -> None:
        """
        Atomically cancel reservation and release reserved tokens.
        """
        if not reservation_id or not reservation_id.strip():
            raise ValueError("reservation_id must be non-blank.")
        if provider is not None and not provider.strip():
            raise ValueError("provider must not be blank when supplied.")

        res_key = f"fieldops:budget:{self.config.namespace_version}:reservation:{reservation_id}"

        from redis.exceptions import WatchError

        for _ in range(10):
            with self.redis.pipeline(transaction=True) as pipe:
                try:
                    pipe.watch(res_key)

                    res_val = pipe.get(res_key)
                    if not res_val:
                        raise ValueError("Reservation not found.")

                    res_record = json.loads(res_val)

                    if provider is not None and provider.strip():
                        prov_clean = provider.strip().lower()
                        prov_hash = hashlib.sha256(prov_clean.encode("utf-8")).hexdigest()
                        stored_hash = res_record.get("provider_hash")
                        if stored_hash and stored_hash != prov_hash:
                            raise ValueError("Provider scope mismatch.")

                    status = res_record.get("status")
                    if status == "RECONCILED":
                        raise ValueError("Cannot cancel reconciled reservation.")
                    if status == "CANCELLED":
                        return

                    daily_tokens_key = res_record.get("daily_tokens_key")
                    if not daily_tokens_key:
                        raise ValueError("Invalid reservation record: missing daily counter scope.")

                    pipe.watch(daily_tokens_key)

                    reserved_tokens = res_record.get("reserved_total", res_record.get("reserved_tokens", 0))

                    daily_tokens_val = pipe.get(daily_tokens_key)
                    current_daily = int(daily_tokens_val) if daily_tokens_val else 0
                    release_amount = reserved_tokens
                    if current_daily - release_amount < 0:
                        release_amount = current_daily

                    now = datetime.now(timezone.utc)
                    res_record["status"] = "CANCELLED"
                    res_record["cancelled_at"] = now.isoformat()

                    pipe.multi()
                    pipe.set(res_key, json.dumps(res_record), ex=self.config.reservation_ttl_seconds)
                    pipe.incrby(daily_tokens_key, -release_amount)

                    pipe.execute()
                    return
                except WatchError:
                    continue
                except ValueError:
                    raise
                except Exception:
                    logger.warning("Redis cancellation execution failed.")
                    raise BudgetInfrastructureError("Budget cancellation failed.") from None

        raise BudgetInfrastructureError("Budget cancellation timed out.")

    def remaining(
        self,
        provider: str,
        model: str,
        tenant_id: Optional[str] = None,
    ) -> Tuple[int, int]:
        """
        Return remaining daily tokens and daily requests globally.
        """
        if not provider or not provider.strip():
            raise ValueError("provider name must be non-blank.")
        if not model or not model.strip():
            raise ValueError("model name must be non-blank.")
        if tenant_id is not None and not tenant_id.strip():
            raise ValueError("tenant_id must not be blank when supplied.")

        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y%m%d")
        minute_str = now.strftime("%Y%m%d%H%M")
        daily_tokens_key, daily_requests_key, _ = _get_keys(
            self.config.namespace_version, provider, date_str, minute_str
        )

        try:
            with self.redis.pipeline(transaction=True) as pipe:
                pipe.get(daily_tokens_key)
                pipe.get(daily_requests_key)
                results = pipe.execute()
        except Exception:
            logger.warning("Redis connection failed during sync remaining query.")
            raise BudgetInfrastructureError("Budget remaining lookup failed.") from None

        daily_tokens = int(results[0]) if results[0] else 0
        daily_reqs = int(results[1]) if results[1] else 0

        return (
            max(self.config.daily_token_limit - daily_tokens, 0),
            max(self.config.daily_request_limit - daily_reqs, 0),
        )

    def usage(
        self,
        provider: str,
        model: str,
        tenant_id: Optional[str] = None,
    ) -> BudgetUsage:
        """
        Return current global usage.
        """
        if not provider or not provider.strip():
            raise ValueError("provider name must be non-blank.")
        if not model or not model.strip():
            raise ValueError("model name must be non-blank.")
        if tenant_id is not None and not tenant_id.strip():
            raise ValueError("tenant_id must not be blank when supplied.")

        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y%m%d")
        minute_str = now.strftime("%Y%m%d%H%M")
        daily_tokens_key, daily_requests_key, rpm_key = _get_keys(
            self.config.namespace_version, provider, date_str, minute_str
        )

        try:
            with self.redis.pipeline(transaction=True) as pipe:
                pipe.get(daily_tokens_key)
                pipe.get(daily_requests_key)
                pipe.get(rpm_key)
                results = pipe.execute()
        except Exception:
            logger.warning("Redis connection failed during sync usage query.")
            raise BudgetInfrastructureError("Budget usage lookup failed.") from None

        return BudgetUsage(
            daily_tokens_used=int(results[0]) if results[0] else 0,
            daily_requests_used=int(results[1]) if results[1] else 0,
            rpm_used=int(results[2]) if results[2] else 0,
        )

    def reset(self) -> None:
        """
        Reset all global counters and reservation keys in Redis.
        """
        pattern = f"fieldops:budget:{self.config.namespace_version}:*"
        cursor = 0
        try:
            while True:
                cursor, keys = self.redis.scan(cursor, match=pattern, count=100)
                if keys:
                    self.redis.delete(*keys)
                if cursor == 0:
                    break
        except Exception:
            logger.warning("Redis reset operation failed.")
