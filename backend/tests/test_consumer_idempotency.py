"""
test_consumer_idempotency.py

Comprehensive test suite for Kafka consumer idempotency management and duplicate event prevention
across dispatch, billing, payment, and notification operations.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.redis_client import get_redis_client
from app.services.consumer_idempotency import (
    ConsumerIdempotency,
    IdempotencyReceipt,
    PreventDuplicateEventProcessing,
    Prevent_duplicate_event_processing,
    ConsumerIdempotencyService,
    EventIdempotencyManager,
    IdempotentConsumer,
)
from app.services.prevent_duplicate_event_processing import (
    ConsumerIdempotency as AliasConsumerIdempotency,
    PreventDuplicateEventProcessing as AliasPreventDuplicateEventProcessing,
)
from app.services.consumer_error_handler import ErrorClassification
from app.services.ai.FieldOpsAI.schemas.agent_messages import (
    AgentAddress,
    MessageEnvelope,
    MessageType,
)
from app.tasks import (
    _process_duplicate_prevention_event_once,
    process_duplicate_prevention_event_task,
    prevent_duplicate_event_processing_task,
)


# =============================================================================
# Fake Redis Fixtures & Message Helpers
# =============================================================================

class FakeRedis:
    def __init__(self):
        self.store = {}
        self.lists = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None, nx=False):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

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

    def rpush(self, key, value):
        if key not in self.lists:
            self.lists[key] = []
        self.lists[key].append(value)
        return len(self.lists[key])

    def llen(self, key):
        return len(self.lists.get(key, []))

    def lrange(self, key, start, stop):
        items = self.lists.get(key, [])
        if stop == -1:
            return items[start:]
        return items[start : stop + 1]


@pytest.fixture
def fake_redis():
    return FakeRedis()


def make_test_event(
    event_id: str = "evt_01JEXAMPLE",
    tenant_id: str = "tenant-1",
    correlation_id: str = "corr-101",
    domain: str = "dispatch",
    event_type: str = "job_assigned",
    payload_extra: dict = None,
    topic: str = "fieldops.job.events",
) -> dict:
    payload = {
        "event_id": event_id,
        "tenant_id": tenant_id,
        "schema_version": 1,
        "correlation_id": correlation_id,
        "domain": domain,
        "event_type": event_type,
        "job_id": "job-101",
    }
    if payload_extra:
        payload.update(payload_extra)
    return {
        "event_id": event_id,
        "tenant_id": tenant_id,
        "correlation_id": correlation_id,
        "topic": topic,
        "payload": payload,
    }


# =============================================================================
# 1. Expected Output Contract Tests
# =============================================================================

@pytest.mark.asyncio
async def test_expected_output_contract_on_recovery(fake_redis):
    """
    Verify recovery returns the exact expected output contract specified in Story 7.10:
    {
        "status": "RECOVERED",
        "event_id": "evt_01JEXAMPLE",
        "retries": 1,
        "idempotent": True,
        "dlq": False
    }
    """
    consumer = ConsumerIdempotency(redis_client=fake_redis)
    test_event = make_test_event(event_id="evt_01JEXAMPLE")

    receipt = await consumer.recover_event(test_event, domain="dispatch")

    # Verify exact required dictionary fields and types
    assert receipt["status"] == "RECOVERED"
    assert receipt["event_id"] == "evt_01JEXAMPLE"
    assert receipt["retries"] == 1
    assert receipt["idempotent"] is True
    assert receipt["dlq"] is False
    assert receipt.is_success is True
    assert receipt.is_recovered is True
    assert bool(receipt) is True


def test_idempotency_receipt_behavior():
    """Verify IdempotencyReceipt boolean evaluation and property helpers."""
    success_receipt = IdempotencyReceipt({
        "status": "PROCESSED",
        "event_id": "evt_1",
        "idempotent": True,
        "idempotent_duplicate": False,
        "dlq": False,
    })
    assert success_receipt.is_success is True
    assert bool(success_receipt) is True
    assert success_receipt.is_duplicate is False

    dup_receipt = IdempotencyReceipt({
        "status": "PROCESSED",
        "event_id": "evt_1",
        "idempotent": True,
        "idempotent_duplicate": True,
        "dlq": False,
    })
    assert dup_receipt.is_success is True
    assert dup_receipt.is_duplicate is True

    failed_receipt = IdempotencyReceipt({
        "status": "FAILED",
        "event_id": "evt_2",
        "idempotent": False,
        "dlq": True,
    })
    assert failed_receipt.is_success is False
    assert failed_receipt.is_dlq is True
    assert bool(failed_receipt) is True  # dlq evaluates to truthy for receipt handling


# =============================================================================
# 2. Aliases and Class Naming Compatibility
# =============================================================================

def test_aliases_and_naming():
    """Verify all story and system aliases correctly point to ConsumerIdempotency."""
    assert PreventDuplicateEventProcessing is ConsumerIdempotency
    assert Prevent_duplicate_event_processing is ConsumerIdempotency
    assert ConsumerIdempotencyService is ConsumerIdempotency
    assert EventIdempotencyManager is ConsumerIdempotency
    assert IdempotentConsumer is ConsumerIdempotency
    assert AliasConsumerIdempotency is ConsumerIdempotency
    assert AliasPreventDuplicateEventProcessing is ConsumerIdempotency
    assert ConsumerIdempotency.CONSUMER_NAME == "Prevent_duplicate_event_processing"


# =============================================================================
# 3. Primary Success Path & Duplicate Rejection
# =============================================================================

@pytest.mark.asyncio
async def test_primary_success_and_duplicate_prevention(fake_redis):
    """
    Verify:
    1. First event execution succeeds and invokes domain handler.
    2. Subsequent duplicate delivery is blocked at the idempotency boundary
       without invoking the domain handler a second time.
    """
    call_count = 0

    def mock_domain_handler(payload):
        nonlocal call_count
        call_count += 1
        return {"status": "SUCCESS", "job_id": payload.get("job_id")}

    consumer = ConsumerIdempotency(redis_client=fake_redis, handler=mock_domain_handler)
    event = make_test_event(event_id="evt_unique_101", domain="dispatch")

    # 1. First execution
    receipt1 = await consumer.process_event(event)
    assert receipt1["status"] == "PROCESSED"
    assert receipt1["event_id"] == "evt_unique_101"
    assert receipt1["idempotent"] is True
    assert receipt1["idempotent_duplicate"] is False
    assert receipt1["dlq"] is False
    assert call_count == 1

    # Verify Redis keys were set
    assert consumer.is_processed("evt_unique_101", domain="dispatch") is True
    assert fake_redis.get("dispatch:event_processed:evt_unique_101") is not None
    assert fake_redis.get("idempotency:dispatch:evt_unique_101") is not None

    # 2. Duplicate delivery (e.g. Kafka re-delivery or consumer restart)
    receipt2 = await consumer.process_event(event)
    assert receipt2["status"] == "PROCESSED"
    assert receipt2["event_id"] == "evt_unique_101"
    assert receipt2["idempotent"] is True
    assert receipt2["idempotent_duplicate"] is True
    assert receipt2["retries"] == 0
    assert receipt2["dlq"] is False
    # Handler must NOT have been called again! Zero business side effect!
    assert call_count == 1


# =============================================================================
# 4. Domain Isolation Tests (Dispatch, Billing, Payment, Notification)
# =============================================================================

@pytest.mark.asyncio
async def test_dispatch_domain_isolation(fake_redis):
    """Verify dispatch domain protection and legacy dispatch key synchronization."""
    consumer = ConsumerIdempotency(redis_client=fake_redis)
    event = make_test_event(
        event_id="evt_disp_1",
        domain="dispatch",
        topic="fieldops.job.events",
        event_type="job-assigned",
    )

    receipt = await consumer.process_event(event)
    assert receipt["status"] == "PROCESSED"
    assert receipt["domain"] == "dispatch"
    assert fake_redis.get("dispatch:event_processed:evt_disp_1") is not None
    assert consumer.is_processed("evt_disp_1", domain="dispatch") is True


@pytest.mark.asyncio
async def test_billing_domain_and_invoice_id_deduplication(fake_redis):
    """
    Verify billing domain deduplication protects both the event_id
    and the invoice_id from repeated billing/ERP sync.
    """
    calls = []

    def mock_billing_sync(payload):
        calls.append(payload["invoice_id"])
        return {"status": "SUCCESS"}

    consumer = ConsumerIdempotency(
        redis_client=fake_redis,
        handler=mock_billing_sync,
        topic="fieldops.billing.events",
    )
    event = make_test_event(
        event_id="evt_bill_001",
        domain="billing",
        topic="fieldops.billing.events",
        event_type="invoice_created",
        payload_extra={"invoice_id": "inv_9988"},
    )

    receipt1 = await consumer.process_event(event)
    assert receipt1["status"] == "PROCESSED"
    assert calls == ["inv_9988"]
    assert fake_redis.get("billing:event_processed:evt_bill_001") is not None
    assert fake_redis.get("billing:invoice_processed:inv_9988") is not None

    # Sending a different event_id but identical invoice_id is recognized as duplicate
    event_dup_invoice = make_test_event(
        event_id="evt_bill_002_new",
        domain="billing",
        topic="fieldops.billing.events",
        event_type="invoice_created",
        payload_extra={"invoice_id": "inv_9988"},
    )
    receipt2 = await consumer.process_event(event_dup_invoice)
    assert receipt2["status"] == "PROCESSED"
    assert receipt2["idempotent_duplicate"] is True
    # Billing sync was not executed twice!
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_payment_domain_and_transaction_id_deduplication(fake_redis):
    """
    Verify payment domain deduplication protects against duplicate charges
    or refunds using payment/transaction identifiers.
    """
    charge_count = 0

    def mock_charge(payload):
        nonlocal charge_count
        charge_count += 1
        return {"status": "SUCCESS"}

    consumer = ConsumerIdempotency(
        redis_client=fake_redis,
        handler=mock_charge,
        topic="fieldops.payment.events",
    )
    event = make_test_event(
        event_id="evt_pay_555",
        domain="payment",
        topic="fieldops.payment.events",
        event_type="payment_processed",
        payload_extra={"payment_id": "txn_card_7777", "amount": 150.00, "currency": "USD"},
    )

    receipt1 = await consumer.process_event(event)
    assert receipt1["status"] == "PROCESSED"
    assert charge_count == 1
    assert fake_redis.get("payment:event_processed:evt_pay_555") is not None
    assert fake_redis.get("payment:txn_processed:txn_card_7777") is not None

    # Resend transaction
    event_retry = make_test_event(
        event_id="evt_pay_555_dup",
        domain="payment",
        topic="fieldops.payment.events",
        event_type="payment_processed",
        payload_extra={"payment_id": "txn_card_7777", "amount": 150.00, "currency": "USD"},
    )
    receipt2 = await consumer.process_event(event_retry)
    assert receipt2["status"] == "PROCESSED"
    assert receipt2["idempotent_duplicate"] is True
    assert charge_count == 1  # No double charge!


@pytest.mark.asyncio
async def test_notification_domain_isolation(fake_redis):
    """Verify notification domain deduplication prevents duplicate SMS/email alerts."""
    sent_notifications = 0

    def mock_send(payload):
        nonlocal sent_notifications
        sent_notifications += 1
        return {"status": "SUCCESS"}

    consumer = ConsumerIdempotency(
        redis_client=fake_redis,
        handler=mock_send,
        topic="fieldops.notification.events",
    )
    event = make_test_event(
        event_id="evt_notif_123",
        domain="notification",
        topic="fieldops.notification.events",
        event_type="customer_alert",
    )

    receipt1 = await consumer.process_event(event)
    assert receipt1["status"] == "PROCESSED"
    assert sent_notifications == 1
    assert fake_redis.get("notification:event_processed:evt_notif_123") is not None

    # Re-delivery of notification event
    receipt2 = await consumer.process_event(event)
    assert receipt2["status"] == "PROCESSED"
    assert receipt2["idempotent_duplicate"] is True
    assert sent_notifications == 1  # Customer not spammed!


# =============================================================================
# 5. Distributed Locking & Concurrency Contention
# =============================================================================

@pytest.mark.asyncio
async def test_distributed_lock_contention(fake_redis):
    """
    Verify distributed locking detects contention when two consumer workers
    attempt to process the same event concurrently.
    """
    consumer = ConsumerIdempotency(redis_client=fake_redis)

    # Simulate Worker A holding the distributed lock
    lock_key = "lock:idempotency:dispatch:evt_concurrent_1"
    fake_redis.set(lock_key, "worker-a-token")

    event = make_test_event(event_id="evt_concurrent_1", domain="dispatch")

    # Worker B tries to process simultaneously
    receipt = await consumer.process_event(event)
    assert receipt["status"] == "LOCKED"
    assert receipt["retryable"] is True
    assert receipt["idempotent"] is True


@pytest.mark.asyncio
async def test_lock_release_on_handler_failure(fake_redis):
    """
    Verify distributed lock is automatically released if the downstream handler fails,
    enabling subsequent retry and recovery attempts.
    """
    attempts = 0

    def flaky_handler(payload):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("Database connection timeout")
        return {"status": "SUCCESS"}

    consumer = ConsumerIdempotency(redis_client=fake_redis, handler=flaky_handler)
    event = make_test_event(event_id="evt_recoverable_1", domain="dispatch")

    # First attempt fails
    receipt1 = await consumer.process_event(event)
    assert receipt1["status"] == "FAILED"
    assert receipt1["retryable"] is True

    # Lock must be released!
    lock_key = "lock:idempotency:dispatch:evt_recoverable_1"
    assert fake_redis.get(lock_key) is None

    # Second attempt succeeds
    receipt2 = await consumer.process_event(event)
    assert receipt2["status"] == "PROCESSED"
    assert receipt2["idempotent_duplicate"] is False
    assert consumer.is_processed("evt_recoverable_1", domain="dispatch") is True


# =============================================================================
# 6. Payload Fingerprinting & Hashing
# =============================================================================

def test_payload_hash_stability():
    """Verify compute_payload_hash produces deterministic fingerprints."""
    payload1 = {"job_id": "job-101", "status": "ASSIGNED", "timestamp": "2026-10-21T10:00:00Z"}
    payload2 = {"status": "ASSIGNED", "job_id": "job-101", "timestamp": "2026-10-21T10:05:00Z"}
    payload_different = {"job_id": "job-102", "status": "ASSIGNED"}

    hash1 = ConsumerIdempotency.compute_payload_hash(payload1)
    hash2 = ConsumerIdempotency.compute_payload_hash(payload2)
    hash3 = ConsumerIdempotency.compute_payload_hash(payload_different)

    # Volatile timestamp difference ignored; hashes match
    assert hash1 == hash2
    # Semantically different payload produces different hash
    assert hash1 != hash3


# =============================================================================
# 7. Security & Credential Redaction
# =============================================================================

@pytest.mark.asyncio
async def test_security_violation_rejection(fake_redis):
    """Verify payloads containing forbidden sensitive keys are rejected immediately."""
    consumer = ConsumerIdempotency(redis_client=fake_redis)

    for bad_key in ["password", "token", "secret", "api_key"]:
        bad_event = make_test_event(
            event_id=f"evt_sec_{bad_key}",
            payload_extra={bad_key: "leaked_secret_val"},
        )
        receipt = await consumer.process_event(bad_event)
        assert receipt["status"] == "FAILED"
        assert receipt["error_type"] == "SecurityPolicyError"
        assert receipt["dlq"] is True
        # Must not be marked as processed
        assert consumer.is_processed(f"evt_sec_{bad_key}", domain="dispatch") is False


# =============================================================================
# 8. Schema & Malformed Message Safety
# =============================================================================

@pytest.mark.asyncio
async def test_malformed_messages_and_validation(fake_redis):
    """Verify malformed JSON, invalid types, and missing fields are handled safely."""
    consumer = ConsumerIdempotency(redis_client=fake_redis)

    # 1. Non-JSON string
    r1 = await consumer.process_event("NOT_VALID_JSON{:::}")
    assert r1["status"] == "FAILED"
    assert r1["error_type"] == "JSONDecodeError"

    # 2. Unsupported type
    r2 = await consumer.process_event(123456)
    assert r2["status"] == "FAILED"
    assert r2["error_type"] == "TypeError"

    # 3. Missing required fields
    r3 = await consumer.process_event({"payload": {"event_id": "evt_x"}})
    assert r3["status"] == "FAILED"
    assert "ValidationError" in r3["error_type"]

    # 4. Unauthorized topic
    bad_topic_event = make_test_event(topic="unauthorized.external.topic")
    r4 = await consumer.process_event(bad_topic_event)
    assert r4["status"] == "FAILED"
    assert r4["error_type"] == "TopicAuthorizationFailedError"


# =============================================================================
# 9. Tenant Context & Correlation ID Preservation
# =============================================================================

@pytest.mark.asyncio
async def test_metadata_preservation(fake_redis):
    """Verify tenant_id and correlation_id are strictly preserved in receipts."""
    consumer = ConsumerIdempotency(redis_client=fake_redis)
    event = make_test_event(
        event_id="evt_meta_1",
        tenant_id="tenant-acme-corp",
        correlation_id="corr-flow-999",
    )

    receipt = await consumer.process_event(event)
    assert receipt["tenant_id"] == "tenant-acme-corp"
    assert receipt["correlation_id"] == "corr-flow-999"


# =============================================================================
# 10. Celery Background Task Integration
# =============================================================================

def test_celery_task_integration(monkeypatch, fake_redis):
    """Verify Celery tasks invoke duplicate prevention once and return receipt."""
    monkeypatch.setattr("app.tasks.get_redis_client", lambda: fake_redis)

    event_payload = make_test_event(event_id="evt_celery_1")["payload"]

    # 1. Primary task
    res1 = _process_duplicate_prevention_event_once(
        redis=fake_redis,
        event_payload=event_payload,
        domain="dispatch",
    )
    assert res1["status"] == "PROCESSED"
    assert res1["event_id"] == "evt_celery_1"
    assert res1["idempotent"] is True

    # 2. Duplicate via Celery
    res2 = _process_duplicate_prevention_event_once(
        redis=fake_redis,
        event_payload=event_payload,
        domain="dispatch",
    )
    assert res2["status"] == "PROCESSED"
    assert res2["idempotent_duplicate"] is True


# =============================================================================
# 11. Operational Metrics & Health Evidence
# =============================================================================

def test_metrics_and_health_snapshot(fake_redis):
    """Verify get_idempotency_metrics snapshots operational evidence."""
    ConsumerIdempotency.reset_metrics()
    metrics_before = ConsumerIdempotency.get_idempotency_metrics()
    assert metrics_before["status"] == "healthy"
    assert metrics_before["consumer"] == "Prevent_duplicate_event_processing"
    assert metrics_before["metrics"]["processed_total"] == 0

    consumer = ConsumerIdempotency(redis_client=fake_redis)
    consumer.acquire_lock("evt_metric_1", "dispatch")
    consumer.release_lock("evt_metric_1", "dispatch")

    metrics_after = ConsumerIdempotency.get_idempotency_metrics()
    assert metrics_after["metrics"]["locks_acquired"] >= 1


# =============================================================================
# 12. MessageEnvelope Support
# =============================================================================

@pytest.mark.asyncio
async def test_message_envelope_support(fake_redis):
    """Verify ConsumerIdempotency seamlessly unwraps MessageEnvelope objects."""
    consumer = ConsumerIdempotency(redis_client=fake_redis)

    envelope = MessageEnvelope(
        sender=AgentAddress(
            agent_id="test-dispatch",
            agent_type="dispatch",
            tenant_id="tenant-envelope",
        ),
        recipient=None,
        message_type=MessageType.EVENT,
        correlation_id="corr-env-100",
        payload={
            "event_id": "evt_envelope_100",
            "tenant_id": "tenant-envelope",
            "schema_version": 1,
            "job_id": "job-env-1",
        },
        topic="fieldops.events",
    )

    receipt = await consumer.process_event(envelope)
    assert receipt["status"] == "PROCESSED"
    assert receipt["event_id"] == "evt_envelope_100"
    assert receipt["tenant_id"] == "tenant-envelope"
    assert receipt["correlation_id"] == "corr-env-100"
    assert receipt["idempotent"] is True


# =============================================================================
# 13. Admin Metrics Endpoint
# =============================================================================

@pytest.mark.asyncio
async def test_admin_metrics_endpoint():
    """Verify get_kafka_idempotency_metrics endpoint returns healthy status and metrics."""
    from app.routes.admin_metrics import get_kafka_idempotency_metrics
    result = await get_kafka_idempotency_metrics()
    assert result["status"] == "healthy"
    assert result["consumer"] == "Prevent_duplicate_event_processing"
    assert "metrics" in result


