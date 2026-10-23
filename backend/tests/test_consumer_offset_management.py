"""
test_consumer_offset_management.py

Comprehensive test suite for Kafka consumer offset management, ensuring reliable
commit behavior strictly at the success boundary to prevent data loss.
"""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.redis_client import get_redis_client
from app.services.consumer_offset_management import (
    ConsumerOffsetManagement,
    OffsetCommitReceipt,
    AddConsumerOffsetManagement,
    Add_consumer_offset_management,
    ConsumerOffsetManager,
    OffsetManagementService,
)
from app.services.add_consumer_offset_management import (
    ConsumerOffsetManagement as AliasConsumerOffsetManagement,
    AddConsumerOffsetManagement as AliasAddConsumerOffsetManagement,
)
from app.services.consumer_error_handler import ErrorClassification
from app.services.ai.FieldOpsAI.schemas.agent_messages import (
    AgentAddress,
    MessageEnvelope,
    MessageType,
)
from app.tasks import (
    _process_offset_management_event_once,
    process_offset_management_event_task,
    add_consumer_offset_management_task,
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

    def rpush(self, key, value):
        if key not in self.lists:
            self.lists[key] = []
        self.lists[key].append(value)
        return len(self.lists[key])

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
    Verify recovery returns the exact expected output contract specified in Story 7.13:
    {
        "status": "RECOVERED",
        "event_id": "evt_01JEXAMPLE",
        "retries": 1,
        "idempotent": True,
        "dlq": False
    }
    """
    consumer = ConsumerOffsetManagement(redis_client=fake_redis)
    test_event = make_test_event(event_id="evt_01JEXAMPLE")

    receipt = await consumer.recover_event(test_event, partition=1, offset=42)

    assert receipt["status"] == "RECOVERED"
    assert receipt["event_id"] == "evt_01JEXAMPLE"
    assert receipt["retries"] == 1
    assert receipt["idempotent"] is True
    assert receipt["dlq"] is False
    assert receipt.is_success is True
    assert receipt.is_recovered is True
    assert receipt.is_committed is True
    assert bool(receipt) is True


def test_offset_commit_receipt_properties():
    """Verify boolean logic and property helpers of OffsetCommitReceipt."""
    r_success = OffsetCommitReceipt({
        "status": "PROCESSED",
        "event_id": "evt_1",
        "offset_committed": True,
        "dlq": False,
    })
    assert r_success.is_success is True
    assert r_success.is_committed is True
    assert bool(r_success) is True

    r_recovered = OffsetCommitReceipt({
        "status": "RECOVERED",
        "event_id": "evt_rec",
        "offset_committed": True,
        "dlq": False,
    })
    assert r_recovered.is_success is True
    assert r_recovered.is_recovered is True
    assert r_recovered.is_committed is True
    assert bool(r_recovered) is True

    r_failed = OffsetCommitReceipt({
        "status": "FAILED",
        "event_id": "evt_fail",
        "offset_committed": False,
        "dlq": False,
    })
    assert r_failed.is_success is False
    assert r_failed.is_committed is False
    assert r_failed.is_dlq is False
    assert bool(r_failed) is False

    r_dlq = OffsetCommitReceipt({
        "status": "FAILED",
        "event_id": "evt_dlq",
        "offset_committed": True,
        "dlq": True,
    })
    assert r_dlq.is_success is False
    assert r_dlq.is_committed is True
    assert r_dlq.is_dlq is True
    assert bool(r_dlq) is True  # DLQ isolation counts as resolved in bool context


# =============================================================================
# 2. Aliases and Naming Compatibility
# =============================================================================

def test_aliases_and_naming():
    """Verify story naming and aliases reference ConsumerOffsetManagement."""
    assert AddConsumerOffsetManagement is ConsumerOffsetManagement
    assert Add_consumer_offset_management is ConsumerOffsetManagement
    assert ConsumerOffsetManager is ConsumerOffsetManagement
    assert OffsetManagementService is ConsumerOffsetManagement
    assert AliasConsumerOffsetManagement is ConsumerOffsetManagement
    assert AliasAddConsumerOffsetManagement is ConsumerOffsetManagement
    assert ConsumerOffsetManagement.CONSUMER_NAME == "Add_consumer_offset_management"


# =============================================================================
# 3. Success Boundary Commit Behavior (Primary Success Path)
# =============================================================================

@pytest.mark.asyncio
async def test_commit_at_success_boundary(fake_redis):
    """
    Verify offset is committed ONLY after downstream domain processing succeeds.
    """
    executed = []

    def mock_domain_handler(payload):
        executed.append(payload["job_id"])
        return {"status": "SUCCESS"}

    consumer = ConsumerOffsetManagement(redis_client=fake_redis, handler=mock_domain_handler)
    event = make_test_event(event_id="evt_succ_001")

    receipt = await consumer.process_event(
        message=event,
        topic="fieldops.events",
        partition=0,
        offset=10,
    )

    assert receipt["status"] == "PROCESSED"
    assert receipt["offset_committed"] is True
    assert receipt["topic"] == "fieldops.events"
    assert receipt["partition"] == 0
    assert receipt["offset"] == 10
    assert executed == ["job-101"]

    # Offset 10 + 1 = 11 should be recorded as the committed next-offset / high-water mark
    committed = consumer.get_committed_offset("fieldops.events", 0)
    assert committed == 11
    assert fake_redis.get("offset:committed:fieldops-offset-management:fieldops.events:0") == "11"


@pytest.mark.asyncio
async def test_async_domain_handler_success_boundary(fake_redis):
    """Verify async domain handlers are properly awaited and committed."""
    executed = []

    async def async_handler(payload):
        executed.append(payload["event_id"])
        return {"status": "SUCCESS"}

    consumer = ConsumerOffsetManagement(redis_client=fake_redis, handler=async_handler)
    event = make_test_event(event_id="evt_async_001")

    receipt = await consumer.process_event(
        message=event,
        topic="fieldops.events",
        partition=2,
        offset=50,
    )

    assert receipt["status"] == "PROCESSED"
    assert receipt["offset_committed"] is True
    assert executed == ["evt_async_001"]
    assert consumer.get_committed_offset("fieldops.events", 2) == 51


# =============================================================================
# 4. Failure Boundary: Prevent Data Loss on Processing Failures
# =============================================================================

@pytest.mark.asyncio
async def test_transient_failure_defers_commit(fake_redis):
    """
    Critical requirement: When domain handler raises an exception, offset must NOT
    be committed, so Kafka redelivers the event without data loss.
    """
    def flaky_handler(payload):
        raise ConnectionError("Database connection lost")

    consumer = ConsumerOffsetManagement(redis_client=fake_redis, handler=flaky_handler)
    event = make_test_event(event_id="evt_flaky_001")

    receipt = await consumer.process_event(
        message=event,
        topic="fieldops.events",
        partition=1,
        offset=99,
    )

    assert receipt["status"] == "FAILED"
    assert receipt["offset_committed"] is False  # Must NOT be committed!
    assert receipt["retryable"] is True
    assert "Database connection lost" in receipt["error"]

    # Redis high-water mark must NOT be set
    assert consumer.get_committed_offset("fieldops.events", 1) is None
    assert fake_redis.get("offset:committed:fieldops-offset-management:fieldops.events:1") is None


@pytest.mark.asyncio
async def test_handler_returned_failure_defers_commit(fake_redis):
    """
    When domain handler explicitly returns status='FAILED', offset must NOT be committed.
    """
    def failing_handler(payload):
        return {"status": "FAILED", "error": "External service timeout", "error_type": "TimeoutError"}

    consumer = ConsumerOffsetManagement(redis_client=fake_redis, handler=failing_handler)
    event = make_test_event(event_id="evt_handler_fail_001")

    receipt = await consumer.process_event(
        message=event,
        topic="fieldops.events",
        partition=0,
        offset=25,
    )

    assert receipt["status"] == "FAILED"
    assert receipt["offset_committed"] is False  # Must NOT be committed!
    assert receipt["retryable"] is True
    assert consumer.get_committed_offset("fieldops.events", 0) is None


# =============================================================================
# 5. Terminal Poison Payloads & DLQ Commit Isolation
# =============================================================================

@pytest.mark.asyncio
async def test_poison_malformed_json_commits_to_unblock_partition(fake_redis):
    """
    Unrecoverable poison message (malformed JSON) should be quarantined and
    offset committed to unblock other healthy messages on the partition.
    """
    consumer = ConsumerOffsetManagement(redis_client=fake_redis)
    malformed_json = "{bad_json: missing_quotes"

    receipt = await consumer.process_event(
        message=malformed_json,
        topic="fieldops.events",
        partition=3,
        offset=77,
    )

    assert receipt["status"] == "FAILED"
    assert receipt["offset_committed"] is True  # Committed so stream unblocks
    assert receipt["dlq"] is True
    assert receipt["retryable"] is False
    assert receipt["error_type"] == "JSONDecodeError"
    assert consumer.get_committed_offset("fieldops.events", 3) == 78


@pytest.mark.asyncio
async def test_poison_malformed_bytes_commits_to_unblock_partition(fake_redis):
    """Invalid UTF-8 bytes payload is quarantined and offset committed."""
    consumer = ConsumerOffsetManagement(redis_client=fake_redis)
    bad_bytes = b"\xff\xfe\xfd"

    receipt = await consumer.process_event(
        message=bad_bytes,
        topic="fieldops.events",
        partition=0,
        offset=12,
    )

    assert receipt["status"] == "FAILED"
    assert receipt["offset_committed"] is True
    assert receipt["dlq"] is True
    assert receipt["error_type"] == "UnicodeDecodeError"
    assert consumer.get_committed_offset("fieldops.events", 0) == 13


@pytest.mark.asyncio
async def test_unsupported_message_type_commits_offset(fake_redis):
    """Unsupported data type (e.g. integer) is rejected, quarantined, and committed."""
    consumer = ConsumerOffsetManagement(redis_client=fake_redis)

    receipt = await consumer.process_event(
        message=123456,
        topic="fieldops.events",
        partition=0,
        offset=5,
    )

    assert receipt["status"] == "FAILED"
    assert receipt["offset_committed"] is True
    assert receipt["dlq"] is True
    assert receipt["error_type"] == "TypeError"


# =============================================================================
# 6. Security & Credential Protection
# =============================================================================

@pytest.mark.asyncio
async def test_forbidden_sensitive_keys_rejected_and_isolated(fake_redis):
    """Payloads with sensitive credentials (password, secret, token) are quarantined."""
    consumer = ConsumerOffsetManagement(redis_client=fake_redis)
    bad_payload = make_test_event(
        event_id="evt_sec_001",
        payload_extra={"client_secret": "super_secret_key"},
    )

    receipt = await consumer.process_event(
        message=bad_payload,
        topic="fieldops.events",
        partition=0,
        offset=88,
    )

    assert receipt["status"] == "FAILED"
    assert receipt["offset_committed"] is True  # Quarantined, partition unblocked
    assert receipt["dlq"] is True
    assert "Security violation" in receipt["error"]


# =============================================================================
# 7. Topic Authorization & Schema Validation
# =============================================================================

@pytest.mark.asyncio
async def test_unauthorized_topic_rejected_and_committed(fake_redis):
    """Events on untrusted topics are rejected, quarantined, and offset committed."""
    consumer = ConsumerOffsetManagement(redis_client=fake_redis)
    event = make_test_event(event_id="evt_unauth_001", topic="unauthorized.rogue.topic")

    receipt = await consumer.process_event(
        message=event,
        topic="unauthorized.rogue.topic",
        partition=0,
        offset=100,
    )

    assert receipt["status"] == "FAILED"
    assert receipt["offset_committed"] is True
    assert receipt["dlq"] is True
    assert "Authorization failure" in receipt["error"]


@pytest.mark.asyncio
async def test_missing_schema_fields_rejected_and_committed(fake_redis):
    """Events missing schema_version or tenant_id are quarantined and committed."""
    consumer = ConsumerOffsetManagement(redis_client=fake_redis)
    broken_event = {
        "event_id": "evt_broken_schema",
        # Missing tenant_id and schema_version
    }

    receipt = await consumer.process_event(
        message=broken_event,
        topic="fieldops.events",
        partition=0,
        offset=15,
    )

    assert receipt["status"] == "FAILED"
    assert receipt["offset_committed"] is True
    assert receipt["dlq"] is True
    assert "Schema validation error" in receipt["error"]


# =============================================================================
# 8. Idempotency & Duplicate Handling
# =============================================================================

@pytest.mark.asyncio
async def test_duplicate_event_commits_offset_without_reprocessing(fake_redis):
    """
    If an event was already processed, committing offset advances partition
    without invoking the domain handler a second time.
    """
    call_count = 0

    def mock_domain_handler(payload):
        nonlocal call_count
        call_count += 1
        return {"status": "SUCCESS"}

    consumer = ConsumerOffsetManagement(redis_client=fake_redis, handler=mock_domain_handler)
    event = make_test_event(event_id="evt_dup_001")

    # First pass: Domain handler executed
    r1 = await consumer.process_event(event, partition=0, offset=1)
    assert r1["status"] == "PROCESSED"
    assert r1["offset_committed"] is True
    assert call_count == 1

    # Second pass: Duplicate detected via Redis idempotency key
    r2 = await consumer.process_event(event, partition=0, offset=2)
    assert r2["status"] == "PROCESSED"
    assert r2["offset_committed"] is True
    assert r2["idempotent_duplicate"] is True
    assert call_count == 1  # Domain handler was NOT called again!
    assert consumer.get_committed_offset("fieldops.events", 0) == 3


# =============================================================================
# 9. MessageEnvelope Support
# =============================================================================

@pytest.mark.asyncio
async def test_message_envelope_processing_and_commit(fake_redis):
    """Verify standard MessageEnvelope objects are handled and committed."""
    consumer = ConsumerOffsetManagement(redis_client=fake_redis)
    envelope = MessageEnvelope(
        message_id=uuid.uuid4(),
        sender=AgentAddress(
            agent_id="test-dispatch",
            agent_type="dispatch",
            tenant_id="tenant-envelope",
        ),
        recipient=None,
        message_type=MessageType.EVENT,
        payload={
            "event_id": "evt_envelope_101",
            "tenant_id": "tenant-1",
            "schema_version": 1,
            "correlation_id": "corr-env-1",
        },
        correlation_id="corr-env-1",
        topic="fieldops.events",
    )

    receipt = await consumer.process_event(
        message=envelope,
        topic="fieldops.events",
        partition=0,
        offset=30,
    )

    assert receipt["status"] == "PROCESSED"
    assert receipt["offset_committed"] is True
    assert receipt["event_id"] == "evt_envelope_101"
    assert consumer.get_committed_offset("fieldops.events", 0) == 31


# =============================================================================
# 10. Bounded Recovery Loop & DLQ Exhaustion
# =============================================================================

@pytest.mark.asyncio
async def test_recover_event_eventual_success(fake_redis):
    """
    Verify recover_event succeeds after transient failures and commits offset.
    """
    attempts = 0

    def flaky_handler(payload):
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise ConnectionError("Transient network glitch")
        return {"status": "SUCCESS"}

    consumer = ConsumerOffsetManagement(redis_client=fake_redis, handler=flaky_handler, max_retries=3)
    event = make_test_event(event_id="evt_flaky_rec_001")

    receipt = await consumer.recover_event(event, partition=1, offset=50)

    assert receipt["status"] == "RECOVERED"
    assert receipt["retries"] == 2
    assert receipt["offset_committed"] is True
    assert receipt["dlq"] is False
    assert consumer.get_committed_offset("fieldops.events", 1) == 51


@pytest.mark.asyncio
async def test_recover_event_exhaustion_quarantines_and_commits(fake_redis):
    """
    Verify exhausted retries quarantine event to DLQ and commit offset so partition moves on.
    """
    def always_fail(payload):
        raise TimeoutError("Temporary network timeout")

    consumer = ConsumerOffsetManagement(redis_client=fake_redis, handler=always_fail, max_retries=2)
    event = make_test_event(event_id="evt_exhaust_001")

    receipt = await consumer.recover_event(event, partition=1, offset=60)

    assert receipt["status"] == "FAILED"
    assert receipt["offset_committed"] is True
    assert receipt["dlq"] is True
    assert receipt["retries"] == 2
    assert consumer.get_committed_offset("fieldops.events", 1) == 61


# =============================================================================
# 11. Consumer Lifecycle & Auto-Commit Setting
# =============================================================================

@pytest.mark.asyncio
async def test_consumer_manager_auto_commit_disabled():
    """Verify KafkaConsumerManager instantiated by default has auto_commit=False."""
    consumer = ConsumerOffsetManagement()
    mgr = consumer.consumer_manager
    assert mgr.enable_auto_commit is False
    assert mgr.topic == "fieldops.events"


@pytest.mark.asyncio
async def test_handle_message_callback(fake_redis):
    """Verify handle_message callback unpacks Kafka consumer message object."""
    consumer = ConsumerOffsetManagement(redis_client=fake_redis)

    class MockKafkaMessage:
        topic = "fieldops.events"
        partition = 4
        offset = 90
        value = make_test_event(event_id="evt_kafka_msg_001")

    receipt = await consumer.handle_message(MockKafkaMessage())
    assert receipt["status"] == "PROCESSED"
    assert receipt["offset_committed"] is True
    assert receipt["partition"] == 4
    assert receipt["offset"] == 90
    assert consumer.get_committed_offset("fieldops.events", 4) == 91


# =============================================================================
# 12. Celery Tasks Integration
# =============================================================================

def test_celery_task_success(fake_redis):
    """Verify process_offset_management_event_task runs cleanly."""
    event = make_test_event(event_id="evt_celery_001")

    result = _process_offset_management_event_once(
        redis=fake_redis,
        event_payload=event,
        topic="fieldops.events",
        partition=0,
        offset=10,
    )

    assert result["status"] == "PROCESSED"
    assert result["offset_committed"] is True
    assert result["event_id"] == "evt_celery_001"


def test_celery_task_aliases(fake_redis):
    """Verify add_consumer_offset_management_task delegates to main task."""
    event = make_test_event(event_id="evt_celery_alias_001")

    with patch("app.tasks.get_redis_client", return_value=fake_redis):
        result = add_consumer_offset_management_task(
            event_payload=event,
            topic="fieldops.events",
            partition=0,
            offset=15,
        )

    assert result["status"] == "PROCESSED"
    assert result["offset_committed"] is True


# =============================================================================
# 13. Admin Metrics Endpoint
# =============================================================================

@pytest.mark.asyncio
async def test_admin_metrics_offset_reporting():
    """Verify get_offset_metrics returns accurate operational metrics."""
    ConsumerOffsetManagement.reset_metrics()

    # Initial state
    m1 = ConsumerOffsetManagement.get_offset_metrics()
    assert m1["status"] == "healthy"
    assert m1["consumer"] == "Add_consumer_offset_management"
    assert m1["metrics"]["offsets_committed"] == 0

    # Simulate commit
    consumer = ConsumerOffsetManagement()
    await consumer.commit_offset("fieldops.events", 0, 10)

    m2 = ConsumerOffsetManagement.get_offset_metrics()
    assert m2["metrics"]["offsets_committed"] == 1
