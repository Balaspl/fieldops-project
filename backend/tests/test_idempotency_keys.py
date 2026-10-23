"""
test_idempotency_keys.py

Comprehensive test suite for defining and propagating stable idempotency keys across
producer and consumer boundaries for deterministic duplicate prevention.
"""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.redis_client import get_redis_client
from app.services.event_publisher import (
    generate_idempotency_key,
    publish_dispatch_event,
    publish_invoice_event,
    publish_payment_event,
    publish_audit_event,
    publish_gps_event,
    publish_notification_event,
    publish_sla_event,
    publish_analytics_event,
)
from app.services.idempotency_keys import (
    ConsumerIdempotencyKeys,
    IdempotencyKeyReceipt,
    AddIdempotencyKeys,
    Add_idempotency_keys,
    EventIdempotencyKeyManager,
    IdempotencyKeyManager,
    IdempotencyKeyService,
)
from app.services.add_idempotency_keys import (
    ConsumerIdempotencyKeys as AliasConsumerIdempotencyKeys,
    AddIdempotencyKeys as AliasAddIdempotencyKeys,
)
from app.services.consumer_error_handler import ErrorClassification
from app.services.ai.FieldOpsAI.schemas.agent_messages import (
    AgentAddress,
    MessageEnvelope,
    MessageType,
)
from app.tasks import (
    _process_idempotency_keys_event_once,
    process_idempotency_keys_event_task,
    add_idempotency_keys_task,
)


# =============================================================================
# Fake Redis Fixtures & Message Helpers
# =============================================================================

class FakeRedis:
    def __init__(self):
        self.store = {}
        self.lists = {}
        self.published = []

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None, nx=False):
        if nx and key in self.store:
            return None
        self.store[key] = str(value)
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

    def publish(self, channel, message):
        self.published.append((channel, message))
        return 1


@pytest.fixture
def fake_redis():
    return FakeRedis()


def make_test_event(
    event_id: str = "evt_01JEXAMPLE",
    tenant_id: str = "tenant-1",
    correlation_id: str = "corr-101",
    domain: str = "dispatch",
    idempotency_key: str = None,
    payload_extra: dict = None,
    topic: str = "fieldops.events",
) -> dict:
    payload = {
        "event_id": event_id,
        "tenant_id": tenant_id,
        "schema_version": 1,
        "correlation_id": correlation_id,
        "domain": domain,
        "job_id": "job-101",
        "status": "COMPLETED",
    }
    if idempotency_key:
        payload["idempotency_key"] = idempotency_key
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
# 1. Expected Output Contract on Recovery
# =============================================================================

@pytest.mark.asyncio
async def test_expected_output_contract_on_recovery(fake_redis):
    """
    Verify recovery returns the exact expected output contract specified in Story 7.14:
    {
        "status": "RECOVERED",
        "event_id": "evt_01JEXAMPLE",
        "retries": 1,
        "idempotent": True,
        "dlq": False
    }
    """
    consumer = ConsumerIdempotencyKeys(redis_client=fake_redis)
    test_event = make_test_event(event_id="evt_01JEXAMPLE")

    receipt = await consumer.recover_event(test_event)

    assert receipt["status"] == "RECOVERED"
    assert receipt["event_id"] == "evt_01JEXAMPLE"
    assert receipt["retries"] == 1
    assert receipt["idempotent"] is True
    assert receipt["dlq"] is False
    assert receipt.is_success is True
    assert receipt.is_recovered is True
    assert bool(receipt) is True


def test_idempotency_key_receipt_properties():
    """Verify boolean logic and property helpers of IdempotencyKeyReceipt."""
    r_success = IdempotencyKeyReceipt({
        "status": "PROCESSED",
        "event_id": "evt_1",
        "idempotent": True,
        "idempotent_duplicate": False,
        "dlq": False,
    })
    assert r_success.is_success is True
    assert r_success.is_duplicate is False
    assert bool(r_success) is True

    r_duplicate = IdempotencyKeyReceipt({
        "status": "PROCESSED",
        "event_id": "evt_dup",
        "idempotent": True,
        "idempotent_duplicate": True,
        "dlq": False,
    })
    assert r_duplicate.is_success is True
    assert r_duplicate.is_duplicate is True
    assert bool(r_duplicate) is True

    r_failed = IdempotencyKeyReceipt({
        "status": "FAILED",
        "event_id": "evt_fail",
        "dlq": False,
    })
    assert r_failed.is_success is False
    assert r_failed.is_dlq is False
    assert bool(r_failed) is False

    r_dlq = IdempotencyKeyReceipt({
        "status": "FAILED",
        "event_id": "evt_dlq",
        "dlq": True,
    })
    assert r_dlq.is_success is False
    assert r_dlq.is_dlq is True
    assert bool(r_dlq) is True


# =============================================================================
# 2. Aliases and Naming Compatibility
# =============================================================================

def test_aliases_and_naming():
    """Verify story naming and aliases reference ConsumerIdempotencyKeys."""
    assert AddIdempotencyKeys is ConsumerIdempotencyKeys
    assert Add_idempotency_keys is ConsumerIdempotencyKeys
    assert EventIdempotencyKeyManager is ConsumerIdempotencyKeys
    assert IdempotencyKeyManager is ConsumerIdempotencyKeys
    assert IdempotencyKeyService is ConsumerIdempotencyKeys
    assert AliasConsumerIdempotencyKeys is ConsumerIdempotencyKeys
    assert AliasAddIdempotencyKeys is ConsumerIdempotencyKeys
    assert ConsumerIdempotencyKeys.CONSUMER_NAME == "Add_idempotency_keys"


# =============================================================================
# 3. Producer Boundary: Key Generation & Event Publisher Propagation
# =============================================================================

def test_generate_idempotency_key_deterministic():
    """Verify generate_idempotency_key creates stable, deterministic keys."""
    k1 = generate_idempotency_key("dispatch", "tenant-1", "job-101", "completed")
    k2 = generate_idempotency_key("dispatch", "tenant-1", "job-101", "completed")
    assert k1 == k2
    assert k1 == "idem:dispatch:tenant-1:job-101:completed"

    k_qual = generate_idempotency_key("dispatch", "tenant-1", "job-101", "status_change", qualifier="in_progress")
    assert k_qual == "idem:dispatch:tenant-1:job-101:status_change:in_progress"


def test_publish_dispatch_event_propagates_idempotency_key(fake_redis):
    """Verify publish_dispatch_event defines and includes idempotency_key in payload."""
    publish_dispatch_event(
        fake_redis,
        event_type="JOB_COMPLETED",
        job_id="job-999",
        tenant_id="tenant-alpha",
        new_status="COMPLETED",
    )
    assert len(fake_redis.published) == 1
    channel, raw_payload = fake_redis.published[0]
    assert channel == "dispatch_events"
    data = json.loads(raw_payload)
    assert "idempotency_key" in data
    assert data["idempotency_key"] == "idem:dispatch:tenant-alpha:job-999:job_completed:completed"


def test_publish_invoice_event_propagates_idempotency_key(fake_redis):
    """Verify publish_invoice_event includes idempotency_key."""
    publish_invoice_event(
        fake_redis,
        event_type="INVOICE_GENERATED",
        job_id="job-200",
        tenant_id="tenant-beta",
        invoice_id="inv-500",
    )
    assert len(fake_redis.published) == 1
    data = json.loads(fake_redis.published[0][1])
    assert "idempotency_key" in data
    assert data["idempotency_key"] == "idem:billing:tenant-beta:inv-500:invoice_generated"


def test_publish_payment_event_propagates_idempotency_key(fake_redis):
    """Verify publish_payment_event includes idempotency_key."""
    publish_payment_event(
        fake_redis,
        event_type="PAYMENT_RECEIVED",
        job_id="job-300",
        tenant_id="tenant-gamma",
        payment_id="pay-700",
    )
    assert len(fake_redis.published) == 1
    data = json.loads(fake_redis.published[0][1])
    assert "idempotency_key" in data
    assert data["idempotency_key"] == "idem:payment:tenant-gamma:pay-700:payment_received"


def test_publish_audit_and_gps_events_propagate_keys(fake_redis):
    """Verify publish_audit_event and publish_gps_event include idempotency_key."""
    publish_audit_event(
        fake_redis,
        event_type="USER_LOGIN",
        tenant_id="tenant-audit",
        user_id="user-123",
    )
    data_audit = json.loads(fake_redis.published[0][1])
    assert "idempotency_key" in data_audit

    publish_gps_event(
        fake_redis,
        event_type="LOCATION_UPDATE",
        technician_id="tech-42",
        job_id="job-88",
        latitude=13.0827,
        longitude=80.2707,
        tenant_id="tenant-gps",
    )
    data_gps = json.loads(fake_redis.published[1][1])
    assert "idempotency_key" in data_gps


# =============================================================================
# 4. Consumer Boundary: Primary Success Path & Key Persistence
# =============================================================================

@pytest.mark.asyncio
async def test_consumer_primary_success_path(fake_redis):
    """
    Verify first-time event execution succeeds, invokes handler, persists idempotency key
    to Redis, and releases the distributed lock.
    """
    executed = []

    def mock_domain_handler(payload):
        executed.append(payload["job_id"])
        return {"status": "SUCCESS"}

    consumer = ConsumerIdempotencyKeys(redis_client=fake_redis, handler=mock_domain_handler)
    event = make_test_event(event_id="evt_succ_001")

    receipt = await consumer.process_event(event)

    assert receipt["status"] == "PROCESSED"
    assert receipt["idempotent"] is True
    assert receipt["idempotent_duplicate"] is False
    assert receipt["event_id"] == "evt_succ_001"
    assert executed == ["job-101"]

    # Verify key was marked completed in Redis
    idem_key = receipt["idempotency_key"]
    assert consumer.is_processed(idem_key, domain="dispatch") is True
    # Verify lock was released
    assert fake_redis.get(f"lock:idempotency_key:dispatch:{idem_key}") is None


# =============================================================================
# 5. Deterministic Duplicate Prevention (Zero Duplicate Side Effects)
# =============================================================================

@pytest.mark.asyncio
async def test_duplicate_prevention_skips_handler(fake_redis):
    """
    Critical requirement: When the same event/idempotency_key is redelivered,
    downstream business logic is NOT executed a second time.
    """
    call_count = 0

    def mock_handler(payload):
        nonlocal call_count
        call_count += 1
        return {"status": "SUCCESS"}

    consumer = ConsumerIdempotencyKeys(redis_client=fake_redis, handler=mock_handler)
    event = make_test_event(event_id="evt_dup_001", idempotency_key="idem:custom:key:001")

    # Pass 1: Initial delivery
    r1 = await consumer.process_event(event)
    assert r1["status"] == "PROCESSED"
    assert r1["idempotent_duplicate"] is False
    assert call_count == 1

    # Pass 2: Duplicate delivery
    r2 = await consumer.process_event(event)
    assert r2["status"] == "PROCESSED"
    assert r2["idempotent_duplicate"] is True
    assert r2["idempotency_key"] == "idem:custom:key:001"
    assert call_count == 1  # Domain handler was NOT called again!


# =============================================================================
# 6. Cross-Compatibility with Story 7.10 Idempotency Keys
# =============================================================================

@pytest.mark.asyncio
async def test_cross_compatibility_with_story_7_10_keys(fake_redis):
    """
    Verify keys completed under Story 7.10 (e.g. idempotency:dispatch:{key})
    are recognized by ConsumerIdempotencyKeys, preventing double execution.
    """
    consumer = ConsumerIdempotencyKeys(redis_client=fake_redis)
    event_id = "evt_story_7_10_prior"

    # Pre-populate Story 7.10 Redis key
    fake_redis.set(f"idempotency:dispatch:{event_id}", '{"completed": true}')

    assert consumer.is_processed(event_id, domain="dispatch") is True

    receipt = await consumer.process_event(make_test_event(event_id=event_id, domain="dispatch"))
    assert receipt["status"] == "PROCESSED"
    assert receipt["idempotent_duplicate"] is True


# =============================================================================
# 7. Distributed Locking & Concurrent In-Flight Execution Protection
# =============================================================================

@pytest.mark.asyncio
async def test_concurrent_execution_lock_rejection(fake_redis):
    """
    When a lock is already held on the idempotency key (concurrent in-flight delivery),
    duplicate execution is prevented.
    """
    consumer = ConsumerIdempotencyKeys(redis_client=fake_redis)
    event = make_test_event(event_id="evt_lock_contention", idempotency_key="idem:lock:test")

    # Manually hold lock
    consumer.acquire_lock("idem:lock:test", domain="dispatch")

    # Processing in parallel detects active lock
    receipt = await consumer.process_event(event)
    assert receipt["status"] == "PROCESSED"
    assert receipt["idempotent_duplicate"] is True


# =============================================================================
# 8. Failure Boundary: Lock Release without Completion Marker
# =============================================================================

@pytest.mark.asyncio
async def test_failure_releases_lock_and_allows_retry(fake_redis):
    """
    When domain execution fails, lock is released and key is NOT marked completed,
    allowing subsequent retries to proceed.
    """
    def failing_handler(payload):
        raise ConnectionError("Temporary database timeout")

    consumer = ConsumerIdempotencyKeys(redis_client=fake_redis, handler=failing_handler)
    event = make_test_event(event_id="evt_fail_retry_001")

    receipt = await consumer.process_event(event)

    assert receipt["status"] == "FAILED"
    assert receipt["retryable"] is True

    # Lock must be released
    idem_key = receipt["idempotency_key"]
    assert fake_redis.get(f"lock:idempotency_key:dispatch:{idem_key}") is None
    # Key must NOT be marked completed
    assert consumer.is_processed(idem_key, domain="dispatch") is False


# =============================================================================
# 9. Terminal Poison Payloads & DLQ Isolation
# =============================================================================

@pytest.mark.asyncio
async def test_poison_malformed_json_quarantined(fake_redis):
    """Malformed JSON string is rejected and isolated to DLQ."""
    consumer = ConsumerIdempotencyKeys(redis_client=fake_redis)
    receipt = await consumer.process_event("{bad_json: missing_quote")

    assert receipt["status"] == "FAILED"
    assert receipt["dlq"] is True
    assert receipt["error_type"] == "JSONDecodeError"


@pytest.mark.asyncio
async def test_poison_malformed_bytes_quarantined(fake_redis):
    """Invalid UTF-8 bytes payload is rejected and isolated to DLQ."""
    consumer = ConsumerIdempotencyKeys(redis_client=fake_redis)
    receipt = await consumer.process_event(b"\xff\xfe\xfd")

    assert receipt["status"] == "FAILED"
    assert receipt["dlq"] is True
    assert receipt["error_type"] == "UnicodeDecodeError"


@pytest.mark.asyncio
async def test_unsupported_type_quarantined(fake_redis):
    """Unsupported data type is rejected and quarantined."""
    consumer = ConsumerIdempotencyKeys(redis_client=fake_redis)
    receipt = await consumer.process_event(99999)

    assert receipt["status"] == "FAILED"
    assert receipt["dlq"] is True
    assert receipt["error_type"] == "TypeError"


# =============================================================================
# 10. Security & Credential Protection
# =============================================================================

@pytest.mark.asyncio
async def test_forbidden_sensitive_keys_rejected(fake_redis):
    """Payloads containing sensitive credentials (password, secret, token) are quarantined."""
    consumer = ConsumerIdempotencyKeys(redis_client=fake_redis)

    for bad_key in ("password", "secret", "client_secret", "api_key", "token"):
        bad_payload = make_test_event(
            event_id=f"evt_sec_{bad_key}",
            payload_extra={bad_key: "exposed_sensitive_value"},
        )
        receipt = await consumer.process_event(bad_payload)
        assert receipt["status"] == "FAILED"
        assert receipt["dlq"] is True
        assert "Security violation" in receipt["error"]


# =============================================================================
# 11. Topic Authorization & Schema Validation
# =============================================================================

@pytest.mark.asyncio
async def test_unauthorized_topic_rejected(fake_redis):
    """Events on untrusted topics are rejected."""
    consumer = ConsumerIdempotencyKeys(redis_client=fake_redis)
    event = make_test_event(event_id="evt_unauth_001", topic="unauthorized.rogue.topic")

    receipt = await consumer.process_event(event, topic="unauthorized.rogue.topic")

    assert receipt["status"] == "FAILED"
    assert receipt["dlq"] is True
    assert "Authorization failure" in receipt["error"]


@pytest.mark.asyncio
async def test_missing_schema_fields_rejected(fake_redis):
    """Events missing required fields fail validation."""
    consumer = ConsumerIdempotencyKeys(redis_client=fake_redis)
    broken_event = {"event_id": "evt_broken"}

    receipt = await consumer.process_event(broken_event)

    assert receipt["status"] == "FAILED"
    assert receipt["dlq"] is True
    assert "Schema validation error" in receipt["error"]


# =============================================================================
# 12. MessageEnvelope Support & Header Propagation
# =============================================================================

@pytest.mark.asyncio
async def test_message_envelope_with_idempotency_key(fake_redis):
    """Verify standard MessageEnvelope objects are handled and key derived."""
    consumer = ConsumerIdempotencyKeys(redis_client=fake_redis)
    envelope = MessageEnvelope(
        message_id=uuid.uuid4(),
        sender=AgentAddress(
            agent_id="dispatch_agent",
            agent_type="dispatch",
            tenant_id="tenant-env",
        ),
        recipient=None,
        message_type=MessageType.EVENT,
        payload={
            "event_id": "evt_env_101",
            "idempotency_key": "idem:dispatch:tenant-env:job-env-1:completed",
            "tenant_id": "tenant-env",
            "schema_version": 1,
            "correlation_id": "corr-env-1",
        },
        correlation_id="corr-env-1",
        topic="fieldops.events",
    )

    receipt = await consumer.process_event(envelope)

    assert receipt["status"] == "PROCESSED"
    assert receipt["idempotency_key"] == "idem:dispatch:tenant-env:job-env-1:completed"
    assert receipt["event_id"] == "evt_env_101"


# =============================================================================
# 13. Bounded Recovery Loop & DLQ Exhaustion
# =============================================================================

@pytest.mark.asyncio
async def test_recover_event_transient_success(fake_redis):
    """Verify recover_event succeeds after transient failures."""
    attempts = 0

    def flaky_handler(payload):
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise TimeoutError("Temporary network glitch")
        return {"status": "SUCCESS"}

    consumer = ConsumerIdempotencyKeys(redis_client=fake_redis, handler=flaky_handler, max_retries=3)
    event = make_test_event(event_id="evt_flaky_rec_001")

    receipt = await consumer.recover_event(event)

    assert receipt["status"] == "RECOVERED"
    assert receipt["retries"] == 2
    assert receipt["idempotent"] is True
    assert receipt["dlq"] is False


@pytest.mark.asyncio
async def test_recover_event_exhaustion(fake_redis):
    """Verify retry exhaustion quarantines event to DLQ."""
    def always_fail(payload):
        raise TimeoutError("Persistent timeout")

    consumer = ConsumerIdempotencyKeys(redis_client=fake_redis, handler=always_fail, max_retries=2)
    event = make_test_event(event_id="evt_exhaust_001")

    receipt = await consumer.recover_event(event)

    assert receipt["status"] == "FAILED"
    assert receipt["dlq"] is True
    assert receipt["retries"] == 2


# =============================================================================
# 14. Celery Tasks Integration
# =============================================================================

def test_celery_task_success(fake_redis):
    """Verify process_idempotency_keys_event_task runs cleanly."""
    event = make_test_event(event_id="evt_celery_001")

    result = _process_idempotency_keys_event_once(
        redis=fake_redis,
        event_payload=event,
        topic="fieldops.events",
    )

    assert result["status"] == "PROCESSED"
    assert result["idempotent"] is True
    assert result["event_id"] == "evt_celery_001"


def test_celery_task_alias(fake_redis):
    """Verify add_idempotency_keys_task delegates to main task."""
    event = make_test_event(event_id="evt_celery_alias_001")

    with patch("app.tasks.get_redis_client", return_value=fake_redis):
        result = add_idempotency_keys_task(event_payload=event)

    assert result["status"] == "PROCESSED"
    assert result["idempotent"] is True


# =============================================================================
# 15. Operational Metrics & Observability
# =============================================================================

@pytest.mark.asyncio
async def test_admin_metrics_reporting():
    """Verify get_idempotency_metrics returns accurate operational metrics."""
    ConsumerIdempotencyKeys.reset_metrics()

    m1 = ConsumerIdempotencyKeys.get_idempotency_metrics()
    assert m1["status"] == "healthy"
    assert m1["consumer"] == "Add_idempotency_keys"
    assert m1["metrics"]["processed_total"] == 0

