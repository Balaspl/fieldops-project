"""
test_token_budget_manager.py

Unit tests for TokenBudgetManager and SyncTokenBudgetManager.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock
import pytest
from pydantic import ValidationError
import fakeredis
import fakeredis.aioredis

from app.services.ai.FieldOpsAI.providers.budget import (
    BudgetDecision,
    BudgetExceededError,
    BudgetInfrastructureError,
    TokenBudgetConfig,
    TokenBudgetManager,
    SyncTokenBudgetManager,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def fake_redis():
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.flushall()


@pytest.fixture
def fake_sync_redis():
    client = fakeredis.FakeRedis(decode_responses=True)
    yield client
    client.flushall()


# 1. Config Validation

def test_budget_config_validation() -> None:
    # Valid config
    config = TokenBudgetConfig(
        daily_token_limit=1000,
        requests_per_minute=5,
        daily_request_limit=10,
        per_request={"sms": 10, "email": 100}
    )
    assert config.daily_token_limit == 1000
    customer_support_config = TokenBudgetConfig(
        per_request={"customer_support": 1200}
    )
    assert customer_support_config.per_request["customer_support"] == 1200

    # Invalid limits
    with pytest.raises(ValidationError):
        TokenBudgetConfig(daily_token_limit=-1)

    with pytest.raises(ValidationError):
        TokenBudgetConfig(requests_per_minute=0)

    # Invalid strategy
    with pytest.raises(ValidationError):
        TokenBudgetConfig(atomic_strategy="invalid_strat")

    # Invalid category
    with pytest.raises(ValidationError):
        TokenBudgetConfig(per_request={"invalid_category": 10})

    # Non-positive per_request limit
    with pytest.raises(ValidationError):
        TokenBudgetConfig(per_request={"sms": 0})


# 2. Key Hashing & PII prevention

@pytest.mark.anyio
async def test_keys_contain_no_pii_or_raw_tenant_ids(fake_redis) -> None:
    config = TokenBudgetConfig(atomic_strategy="transaction")
    manager = TokenBudgetManager(fake_redis, config=config)
    raw_tenant = "tenant-xyz-12345"

    res_id = await manager.reserve(
        estimated_input_tokens=0,
        max_output_tokens=10,
        category="sms",
        provider="groq",
        model="llama3",
        tenant_id=raw_tenant
    )
    assert isinstance(res_id, str)
    assert len(res_id) == 32

    keys = await fake_redis.keys("*")
    assert len(keys) > 0
    for key in keys:
        assert raw_tenant not in key
        if "reservation" not in key:
            assert "groq" in key


# 3. Global Budget Sharing across Tenants

@pytest.mark.anyio
async def test_global_budget_sharing_across_tenants(fake_redis) -> None:
    config = TokenBudgetConfig(
        daily_token_limit=100,
        requests_per_minute=10,
        daily_request_limit=10,
        per_request={"sms": 50},
        atomic_strategy="transaction"
    )
    manager = TokenBudgetManager(fake_redis, config=config)

    # Reserve 50 tokens for tenant A
    await manager.reserve(estimated_input_tokens=0, max_output_tokens=50, category="sms", provider="groq", model="llama3", tenant_id="tenantA")

    # Reserve another 50 tokens for tenant B (succeeds, reaching exactly 100 limit)
    await manager.reserve(estimated_input_tokens=0, max_output_tokens=50, category="sms", provider="groq", model="llama3", tenant_id="tenantB")

    # Over budget by 1 token for tenant C
    with pytest.raises(BudgetExceededError):
        await manager.reserve(estimated_input_tokens=0, max_output_tokens=1, category="sms", provider="groq", model="llama3", tenant_id="tenantC")


# 4. Exact Token Limit Boundary

@pytest.mark.anyio
async def test_token_limit_boundary(fake_redis) -> None:
    config = TokenBudgetConfig(
        daily_token_limit=100,
        requests_per_minute=10,
        daily_request_limit=10,
        per_request={"sms": 50},
        atomic_strategy="transaction"
    )
    manager = TokenBudgetManager(fake_redis, config=config)

    # Reserve exactly 50 tokens
    await manager.reserve(estimated_input_tokens=0, max_output_tokens=50, category="sms", provider="groq", model="llama3")

    # Reserve another 50 tokens (exact limit)
    await manager.reserve(estimated_input_tokens=0, max_output_tokens=50, category="sms", provider="groq", model="llama3")

    # Over budget by 1 token
    with pytest.raises(BudgetExceededError):
        await manager.reserve(estimated_input_tokens=0, max_output_tokens=1, category="sms", provider="groq", model="llama3")


# 5. Exact RPM Boundary

@pytest.mark.anyio
async def test_rpm_boundary(fake_redis) -> None:
    config = TokenBudgetConfig(
        daily_token_limit=1000,
        requests_per_minute=2,
        daily_request_limit=10,
        per_request={"sms": 50},
        atomic_strategy="transaction"
    )
    manager = TokenBudgetManager(fake_redis, config=config)

    # 1st request in minute
    await manager.reserve(estimated_input_tokens=0, max_output_tokens=10, category="sms", provider="groq", model="llama3")
    # 2nd request in minute
    await manager.reserve(estimated_input_tokens=0, max_output_tokens=10, category="sms", provider="groq", model="llama3")

    # 3rd request in minute (RPM exceeded)
    with pytest.raises(BudgetExceededError):
        await manager.reserve(estimated_input_tokens=0, max_output_tokens=10, category="sms", provider="groq", model="llama3")


# 6. Exact Daily Requests Boundary

@pytest.mark.anyio
async def test_daily_requests_boundary(fake_redis) -> None:
    config = TokenBudgetConfig(
        daily_token_limit=1000,
        requests_per_minute=10,
        daily_request_limit=2,
        per_request={"sms": 50},
        atomic_strategy="transaction"
    )
    manager = TokenBudgetManager(fake_redis, config=config)

    # 1st request
    await manager.reserve(estimated_input_tokens=0, max_output_tokens=10, category="sms", provider="groq", model="llama3")
    # 2nd request
    await manager.reserve(estimated_input_tokens=0, max_output_tokens=10, category="sms", provider="groq", model="llama3")

    # 3rd request (daily requests exceeded)
    with pytest.raises(BudgetExceededError):
        await manager.reserve(estimated_input_tokens=0, max_output_tokens=10, category="sms", provider="groq", model="llama3")


# 7. Per-request category limit validation

@pytest.mark.anyio
async def test_per_request_categories(fake_redis) -> None:
    config = TokenBudgetConfig(
        per_request={"sms": 10, "email": 100},
        atomic_strategy="transaction"
    )
    manager = TokenBudgetManager(fake_redis, config=config)

    # Within limits
    await manager.reserve(estimated_input_tokens=0, max_output_tokens=10, category="sms", provider="groq", model="llama3")
    await manager.reserve(estimated_input_tokens=0, max_output_tokens=100, category="email", provider="groq", model="llama3")

    # Exceeding SMS per-request limit
    with pytest.raises(BudgetExceededError, match="Per-request limit exceeded"):
        await manager.reserve(estimated_input_tokens=0, max_output_tokens=11, category="sms", provider="groq", model="llama3")

    # Unsupported category
    with pytest.raises(ValueError, match="Unsupported request category"):
        await manager.reserve(estimated_input_tokens=0, max_output_tokens=5, category="push", provider="groq", model="llama3")


# 8. Validation of invalid parameters

@pytest.mark.anyio
async def test_invalid_parameters_rejected(fake_redis) -> None:
    config = TokenBudgetConfig(atomic_strategy="transaction")
    manager = TokenBudgetManager(fake_redis, config=config)

    with pytest.raises(ValueError, match="estimated_input_tokens must be non-negative"):
        await manager.reserve(estimated_input_tokens=-1, max_output_tokens=5, category="sms", provider="groq", model="llama3")

    with pytest.raises(ValueError, match="max_output_tokens must be greater than zero"):
        await manager.reserve(estimated_input_tokens=0, max_output_tokens=0, category="sms", provider="groq", model="llama3")

    with pytest.raises(ValueError, match="provider name must be non-blank"):
        await manager.reserve(estimated_input_tokens=0, max_output_tokens=5, category="sms", provider="", model="llama3")

    with pytest.raises(ValueError, match="model name must be non-blank"):
        await manager.reserve(estimated_input_tokens=0, max_output_tokens=5, category="sms", provider="groq", model="  ")

    with pytest.raises(ValueError, match="must not be blank when supplied"):
        await manager.reserve(estimated_input_tokens=0, max_output_tokens=5, category="sms", provider="groq", model="llama3", tenant_id="  ")


# 9. Key Expirations

@pytest.mark.anyio
async def test_key_expirations(fake_redis) -> None:
    config = TokenBudgetConfig(atomic_strategy="transaction")
    manager = TokenBudgetManager(fake_redis, config=config)
    await manager.reserve(estimated_input_tokens=0, max_output_tokens=10, category="sms", provider="groq", model="llama3")

    keys = await fake_redis.keys("*")
    assert len(keys) > 0
    for key in keys:
        ttl = await fake_redis.ttl(key)
        assert ttl > 0
        if "rpm" in key:
            assert ttl <= 60
        else:
            assert ttl <= 86400


# 10. Concurrency and Atomicity tests

@pytest.mark.anyio
async def test_concurrent_calls_cannot_overspend(fake_redis) -> None:
    config = TokenBudgetConfig(
        daily_token_limit=100,
        requests_per_minute=20,
        daily_request_limit=20,
        per_request={"sms": 20},
        atomic_strategy="transaction"
    )
    manager = TokenBudgetManager(fake_redis, config=config)

    tasks = []
    for _ in range(10):
        tasks.append(manager.reserve(estimated_input_tokens=0, max_output_tokens=15, category="sms", provider="groq", model="llama3"))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    success_count = sum(1 for r in results if isinstance(r, str))
    failed_count = sum(1 for r in results if isinstance(r, BudgetExceededError))

    # Exactly 6 requests (6 * 15 = 90 tokens) should succeed, 4 should fail (since 7th would exceed 100)
    assert success_count == 6
    assert failed_count == 4


# 11. Reservation Reconciliation & Cancellation (Async)

@pytest.mark.anyio
async def test_reconciliation_lifecycle_async(fake_redis) -> None:
    config = TokenBudgetConfig(
        daily_token_limit=100,
        requests_per_minute=10,
        daily_request_limit=10,
        per_request={"sms": 50},
        atomic_strategy="transaction"
    )
    manager = TokenBudgetManager(fake_redis, config=config)

    # 1. Reserve 40 estimated tokens
    res_id = await manager.reserve(estimated_input_tokens=10, max_output_tokens=30, category="sms", provider="groq", model="llama3")

    # 2. Reconcile: actual was only 20 tokens
    await manager.reconcile(reservation_id=res_id, actual_input_tokens=10, actual_output_tokens=10, provider="groq")

    rem_tokens, _ = await manager.remaining(provider="groq", model="llama3")
    assert rem_tokens == 80  # 100 - 20 actual = 80

    # 3. Duplicate reconciliation is ignored/idempotent
    await manager.reconcile(reservation_id=res_id, actual_input_tokens=10, actual_output_tokens=10, provider="groq")
    rem_tokens_dup, _ = await manager.remaining(provider="groq", model="llama3")
    assert rem_tokens_dup == 80

    # 4. Cannot cancel a reconciled reservation
    with pytest.raises(ValueError, match="Cannot cancel reconciled reservation"):
        await manager.cancel(reservation_id=res_id, provider="groq")


@pytest.mark.anyio
async def test_reconciliation_overspend_async(fake_redis) -> None:
    config = TokenBudgetConfig(
        daily_token_limit=100,
        requests_per_minute=10,
        daily_request_limit=10,
        per_request={"sms": 50},
        atomic_strategy="transaction"
    )
    manager = TokenBudgetManager(fake_redis, config=config)

    res_id = await manager.reserve(estimated_input_tokens=10, max_output_tokens=30, category="sms", provider="groq", model="llama3")

    # Actual (50) is greater than reserved (40)
    with pytest.raises(BudgetExceededError):
        await manager.reconcile(reservation_id=res_id, actual_input_tokens=30, actual_output_tokens=20, provider="groq")

    # Verify correct accounting: delta was added to the counters
    rem_tokens, _ = await manager.remaining(provider="groq", model="llama3")
    assert rem_tokens == 50  # 100 - 50 actual = 50


@pytest.mark.anyio
async def test_cancellation_lifecycle_async(fake_redis) -> None:
    config = TokenBudgetConfig(
        daily_token_limit=100,
        requests_per_minute=10,
        daily_request_limit=10,
        per_request={"sms": 50},
        atomic_strategy="transaction"
    )
    manager = TokenBudgetManager(fake_redis, config=config)

    res_id = await manager.reserve(estimated_input_tokens=10, max_output_tokens=30, category="sms", provider="groq", model="llama3")
    await manager.cancel(reservation_id=res_id, provider="groq")

    rem_tokens, _ = await manager.remaining(provider="groq", model="llama3")
    assert rem_tokens == 100  # released 40 tokens

    # Duplicate cancellation is idempotent
    await manager.cancel(reservation_id=res_id, provider="groq")
    rem_tokens_dup, _ = await manager.remaining(provider="groq", model="llama3")
    assert rem_tokens_dup == 100


# 12. Synchronous Manager Tests

def test_sync_manager_flow(fake_sync_redis) -> None:
    config = TokenBudgetConfig(
        daily_token_limit=100,
        requests_per_minute=10,
        daily_request_limit=10,
        per_request={"sms": 50},
        atomic_strategy="transaction"
    )
    manager = SyncTokenBudgetManager(fake_sync_redis, config=config)

    # Check limits
    dec = manager.check(estimated_input_tokens=10, max_output_tokens=20, category="sms", provider="groq", model="llama3")
    assert dec.allowed is True

    # Reserve
    res_id = manager.reserve(estimated_input_tokens=10, max_output_tokens=30, category="sms", provider="groq", model="llama3")
    assert isinstance(res_id, str)

    # Reconcile
    manager.reconcile(reservation_id=res_id, actual_input_tokens=10, actual_output_tokens=15, provider="groq")
    rem_tokens, _ = manager.remaining(provider="groq", model="llama3")
    assert rem_tokens == 75

    # Cancel a new reservation
    res_id2 = manager.reserve(estimated_input_tokens=10, max_output_tokens=20, category="sms", provider="groq", model="llama3")
    manager.cancel(reservation_id=res_id2, provider="groq")
    rem_tokens2, _ = manager.remaining(provider="groq", model="llama3")
    assert rem_tokens2 == 75


# 13. Redis failure uses typed fail-closed behavior

@pytest.mark.anyio
async def test_redis_failure_uses_fail_closed_async() -> None:
    mock_redis = MagicMock()
    mock_redis.eval = AsyncMock(side_effect=Exception("Redis connection lost"))
    manager = TokenBudgetManager(mock_redis)

    with pytest.raises(BudgetInfrastructureError):
        await manager.reserve(estimated_input_tokens=0, max_output_tokens=10, category="sms", provider="groq", model="llama3")


def test_redis_failure_uses_fail_closed_sync() -> None:
    mock_redis = MagicMock()
    mock_redis.eval = MagicMock(side_effect=Exception("Redis connection lost"))
    manager = SyncTokenBudgetManager(mock_redis)

    with pytest.raises(BudgetInfrastructureError):
        manager.reserve(estimated_input_tokens=0, max_output_tokens=10, category="sms", provider="groq", model="llama3")


@pytest.mark.anyio
async def test_unexpected_exception_in_transaction_raises_infra_error() -> None:
    manager = TokenBudgetManager(MagicMock())
    manager.redis.eval = AsyncMock(side_effect=Exception("unknown command 'eval'"))
    manager._reserve_transaction = AsyncMock(side_effect=Exception("unexpected connection drop"))
    with pytest.raises(BudgetInfrastructureError):
        await manager.reserve(estimated_input_tokens=0, max_output_tokens=10, category="sms", provider="groq", model="llama3")


@pytest.mark.anyio
async def test_check_limits(fake_redis) -> None:
    config = TokenBudgetConfig(
        daily_token_limit=100,
        requests_per_minute=10,
        daily_request_limit=10,
        per_request={"sms": 50},
        atomic_strategy="transaction"
    )
    manager = TokenBudgetManager(fake_redis, config=config)

    dec = await manager.check(estimated_input_tokens=10, max_output_tokens=20, category="sms", provider="groq", model="llama3")
    assert dec.allowed is True

    await manager.reserve(estimated_input_tokens=10, max_output_tokens=20, category="sms", provider="groq", model="llama3")
    await manager.reserve(estimated_input_tokens=10, max_output_tokens=20, category="sms", provider="groq", model="llama3")

    dec_fail = await manager.check(estimated_input_tokens=10, max_output_tokens=40, category="sms", provider="groq", model="llama3")
    assert dec_fail.allowed is False
    assert "token limit exceeded" in dec_fail.reason.lower()


@pytest.mark.anyio
async def test_sms_and_sentiment_categories_accepted(fake_redis) -> None:
    config = TokenBudgetConfig(atomic_strategy="transaction")
    manager = TokenBudgetManager(fake_redis, config=config)

    res1 = await manager.reserve(
        estimated_input_tokens=20, max_output_tokens=80, category="sms", provider="groq", model="llama3"
    )
    assert isinstance(res1, str)

    res2 = await manager.reserve(
        estimated_input_tokens=15, max_output_tokens=10, category="sentiment", provider="groq", model="llama3"
    )
    assert isinstance(res2, str)
    assert res1 != res2


@pytest.mark.anyio
async def test_global_budget_shared_across_models(fake_redis) -> None:
    config = TokenBudgetConfig(
        daily_token_limit=100,
        requests_per_minute=10,
        daily_request_limit=10,
        per_request={"sms": 50},
        atomic_strategy="transaction"
    )
    manager = TokenBudgetManager(fake_redis, config=config)

    await manager.reserve(estimated_input_tokens=10, max_output_tokens=40, category="sms", provider="groq", model="model-a")
    await manager.reserve(estimated_input_tokens=10, max_output_tokens=40, category="sms", provider="groq", model="model-b")

    with pytest.raises(BudgetExceededError):
        await manager.reserve(estimated_input_tokens=0, max_output_tokens=1, category="sms", provider="groq", model="model-c")


@pytest.mark.anyio
async def test_wrong_provider_scope_rejected(fake_redis) -> None:
    config = TokenBudgetConfig(atomic_strategy="transaction")
    manager = TokenBudgetManager(fake_redis, config=config)
    res_id = await manager.reserve(estimated_input_tokens=10, max_output_tokens=20, category="sms", provider="groq", model="llama3")

    with pytest.raises(ValueError, match="Provider scope mismatch"):
        await manager.reconcile(reservation_id=res_id, actual_input_tokens=5, actual_output_tokens=5, provider="openai")

    with pytest.raises(ValueError, match="Provider scope mismatch"):
        await manager.cancel(reservation_id=res_id, provider="openai")


@pytest.mark.anyio
async def test_midnight_crossing_reconciliation(fake_redis) -> None:
    config = TokenBudgetConfig(
        daily_token_limit=1000,
        requests_per_minute=10,
        daily_request_limit=10,
        per_request={"sms": 50},
        atomic_strategy="transaction"
    )
    manager = TokenBudgetManager(fake_redis, config=config)
    res_id = await manager.reserve(estimated_input_tokens=10, max_output_tokens=30, category="sms", provider="groq", model="llama3")

    import json
    res_key = f"fieldops:budget:{config.namespace_version}:reservation:{res_id}"
    res_val = await fake_redis.get(res_key)
    res_record = json.loads(res_val)
    stored_daily_key = res_record["daily_tokens_key"]

    await manager.reconcile(reservation_id=res_id, actual_input_tokens=10, actual_output_tokens=10)

    used = await fake_redis.get(stored_daily_key)
    assert int(used) == 20

