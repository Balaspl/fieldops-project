"""
test_failed_event_storage.py

Comprehensive test suite for persisting failed event metadata and processing error context
for durable evidence, investigation, and recovery.
"""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.redis_client import get_redis_client
from app.services.failed_event_storage import (
    FailedEventStorage,
    FailedEventReceipt,
    AddFailedEventStorage,
    Add_failed_event_storage,
    ConsumerFailedEventStorage,
    FailedEventStorageService,
)
from app.services.add_failed_event_storage import (
    FailedEventStorage as AliasFailedEventStorage,
    AddFailedEventStorage as AliasAddFailedEventStorage,
)
from app.services.consumer_error_handler import ErrorClassification
from app.services.ai.FieldOpsAI.schemas.agent_messages import (
    AgentAddress,
    MessageEnvelope,
    MessageType,
)
from app.tasks import (
    _process_failed_event_storage_once,
    process_failed_event_storage_task,
    add_failed_event_storage_task,
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
# 1. Expected Output Contract on Recovery
# =============================================================================

@pytest.mark.asyncio
async def test_expected_output_contract_on_recovery(fake_redis):
    """
    Verify recovery returns the exact expected output contract specified in Story 7.15:
    {
        "status": "RECOVERED",
        "event_id": "evt_01JEXAMPLE",
        "retries": 1,
        "idempotent": True,
        "dlq": False
    }
    """
    consumer = FailedEventStorage(redis_client=fake_redis)
    test_event = make_test_event(event_id="evt_01JEXAMPLE")

    receipt = await consumer.recover_event(test_event, partition=1, offset=10)

    assert receipt["status"] == "RECOVERED"
    assert receipt["event_id"] == "evt_01JEXAMPLE"
    assert receipt["retries"] == 1
    assert receipt["idempotent"] is True
    assert receipt["dlq"] is False
    assert receipt.is_success is True
    assert receipt.is_recovered is True
    assert bool(receipt) is True


def test_failed_event_receipt_properties():
    """Verify boolean logic and property helpers of FailedEventReceipt."""
    r_success = FailedEventReceipt({
        "status": "PROCESSED",
        "event_id": "evt_1",
        "dlq": False,
        "failed_event_stored": False,
    })
    assert r_success.is_success is True
    assert r_success.is_stored is False
    assert bool(r_success) is True

    r_recovered = FailedEventReceipt({
        "status": "RECOVERED",
        "event_id": "evt_rec",
        "dlq": False,
    })
    assert r_recovered.is_success is True
    assert r_recovered.is_recovered is True
    assert bool(r_recovered) is True

    r_failed = FailedEventReceipt({
        "status": "FAILED",
        "event_id": "evt_fail",
        "dlq": False,
        "failed_event_stored": True,
    })
    assert r_failed.is_success is False
    assert r_failed.is_stored is True
    assert bool(r_failed) is False

    r_dlq = FailedEventReceipt({
        "status": "FAILED",
        "event_id": "evt_dlq",
        "dlq": True,
        "failed_event_stored": True,
    })
    assert r_dlq.is_success is False
    assert r_dlq.is_dlq is True
    assert r_dlq.is_stored is True
    assert bool(r_dlq) is True


# =============================================================================
# 2. Aliases and Naming Compatibility
# =============================================================================

def test_aliases_and_naming():
    """Verify story naming and aliases reference FailedEventStorage."""
    assert AddFailedEventStorage is FailedEventStorage
    assert Add_failed_event_storage is FailedEventStorage
    assert ConsumerFailedEventStorage is FailedEventStorage
    assert FailedEventStorageService is FailedEventStorage
    assert AliasFailedEventStorage is FailedEventStorage
    assert AliasAddFailedEventStorage is FailedEventStorage
    assert FailedEventStorage.CONSUMER_NAME == "Add_failed_event_storage"


# =============================================================================
# 3. Durable Failed Event Storage & Metadata Persistence
# =============================================================================

def test_store_and_get_failed_event_metadata(fake_redis):
    """
    Verify failure context is persisted with full metadata:
    tenant, event, topic, partition, offset, attempt, and error.
    """
    storage = FailedEventStorage(redis_client=fake_redis)

    failure_ctx = {
        "event_id": "evt_fail_101",
        "tenant_id": "tenant-corp",
        "topic": "fieldops.events",
        "partition": 2,
        "offset": 450,
        "attempt": 3,
        "correlation_id": "corr-xyz",
        "domain": "billing",
        "error": "Payment gateway timeout after 5000ms",
        "error_type": "GatewayTimeout",
        "error_classification": "RETRYABLE",
        "payload": {
            "invoice_id": "inv_999",
            "amount": 250.00,
        },
    }

    stored_id = storage.store_failed_event(failure_ctx)
    assert stored_id == "evt_fail_101"

    # Retrieve stored record
    record = storage.get_failed_event("evt_fail_101")
    assert record is not None
    assert record["event_id"] == "evt_fail_101"
    assert record["tenant_id"] == "tenant-corp"
    assert record["topic"] == "fieldops.events"
    assert record["partition"] == 2
    assert record["offset"] == 450
    assert record["attempt"] == 3
    assert record["correlation_id"] == "corr-xyz"
    assert record["domain"] == "billing"
    assert record["error"] == "Payment gateway timeout after 5000ms"
    assert record["error_type"] == "GatewayTimeout"
    assert record["resolved"] is False
    assert record["stored_by"] == "Add_failed_event_storage"


def test_list_failed_events_with_tenant_filtering(fake_redis):
    """Verify failed events can be queried globally or filtered by tenant."""
    storage = FailedEventStorage(redis_client=fake_redis)

    storage.store_failed_event({"event_id": "evt_t1_1", "tenant_id": "tenant-1", "error": "Err 1"})
    storage.store_failed_event({"event_id": "evt_t2_1", "tenant_id": "tenant-2", "error": "Err 2"})
    storage.store_failed_event({"event_id": "evt_t1_2", "tenant_id": "tenant-1", "error": "Err 3"})

    all_events = storage.list_failed_events()
    assert len(all_events) == 3

    t1_events = storage.list_failed_events(tenant_id="tenant-1")
    assert len(t1_events) == 2
    t1_ids = {e["event_id"] for e in t1_events}
    assert t1_ids == {"evt_t1_1", "evt_t1_2"}


# =============================================================================
# 4. Sensitive Credential Redaction in Stored Payloads
# =============================================================================

def test_sensitive_credentials_redacted_in_storage(fake_redis):
    """
    Requirement: Store metadata while protecting sensitive payload data
    (password, token, secret, api_key).
    """
    storage = FailedEventStorage(redis_client=fake_redis)

    failure_ctx = {
        "event_id": "evt_secret_001",
        "tenant_id": "tenant-sec",
        "error": "Failed during auth check",
        "payload": {
            "user_id": "usr-100",
            "password": "plain_secret_password",
            "api_key": "secret_api_key_12345",
            "auth_token": "bearer_jwt_token_abcdef",
            "credit_card": "4111111111111111",
        },
    }

    storage.store_failed_event(failure_ctx)
    record = storage.get_failed_event("evt_secret_001")
    assert record is not None

    payload = record["payload"]
    assert payload["user_id"] == "usr-100"
    assert payload["password"] == "[REDACTED]"
    assert payload["api_key"] == "[REDACTED]"
    assert payload["auth_token"] == "[REDACTED]"


# =============================================================================
# 5. Failed Event Resolution Lifecycle
# =============================================================================

def test_mark_resolved_lifecycle(fake_redis):
    """Verify failed events can be marked resolved after operator recovery."""
    storage = FailedEventStorage(redis_client=fake_redis)

    storage.store_failed_event({"event_id": "evt_res_001", "tenant_id": "t1", "error": "DB deadlock"})

    before = storage.get_failed_event("evt_res_001")
    assert before["resolved"] is False
    assert before["resolved_at"] is None

    success = storage.mark_resolved("evt_res_001", resolution_metadata={"resolved_by": "operator_admin"})
    assert success is True

    after = storage.get_failed_event("evt_res_001")
    assert after["resolved"] is True
    assert after["resolved_at"] is not None
    assert after["resolution_metadata"]["resolved_by"] == "operator_admin"


# =============================================================================
# 6. Primary Processing Success Path
# =============================================================================

@pytest.mark.asyncio
async def test_successful_processing_does_not_store_failure(fake_redis):
    """Verify successful event processing executes handler without storing failure."""
    executed = []

    def mock_domain_handler(payload):
        executed.append(payload["job_id"])
        return {"status": "SUCCESS"}

    consumer = FailedEventStorage(redis_client=fake_redis, handler=mock_domain_handler)
    event = make_test_event(event_id="evt_succ_001")

    receipt = await consumer.process_event(event, partition=0, offset=10)

    assert receipt["status"] == "PROCESSED"
    assert receipt["failed_event_stored"] is False
    assert executed == ["job-101"]
    assert consumer.get_failed_event("evt_succ_001") is None


# =============================================================================
# 7. Processing Failure Automatically Stores Failed Event
# =============================================================================

@pytest.mark.asyncio
async def test_domain_handler_failure_stores_failed_event(fake_redis):
    """Verify that domain execution failure automatically stores failure context."""
    def failing_handler(payload):
        raise ConnectionResetError("Remote server closed connection unexpectedly")

    consumer = FailedEventStorage(redis_client=fake_redis, handler=failing_handler)
    event = make_test_event(event_id="evt_fail_auto_001")

    receipt = await consumer.process_event(event, partition=3, offset=88)

    assert receipt["status"] == "FAILED"
    assert receipt["failed_event_stored"] is True
    assert receipt["event_id"] == "evt_fail_auto_001"

    # Verify record was stored in Redis
    record = consumer.get_failed_event("evt_fail_auto_001")
    assert record is not None
    assert record["partition"] == 3
    assert record["offset"] == 88
    assert "Remote server closed connection" in record["error"]


# =============================================================================
# 8. Terminal Poison Messages Automatically Stored
# =============================================================================

@pytest.mark.asyncio
async def test_malformed_json_stored_durably(fake_redis):
    """Verify unparseable JSON string is quarantined and stored durably."""
    consumer = FailedEventStorage(redis_client=fake_redis)
    bad_json = "{\"unclosed_string: 123"

    receipt = await consumer.process_event(bad_json, partition=1, offset=12)

    assert receipt["status"] == "FAILED"
    assert receipt["failed_event_stored"] is True
    assert receipt["dlq"] is True
    assert receipt["error_type"] == "JSONDecodeError"

    stored = consumer.get_failed_event(receipt["event_id"])
    assert stored is not None
    assert stored["error_type"] == "JSONDecodeError"


@pytest.mark.asyncio
async def test_malformed_bytes_stored_durably(fake_redis):
    """Verify invalid UTF-8 bytes payload is stored durably."""
    consumer = FailedEventStorage(redis_client=fake_redis)
    bad_bytes = b"\xff\xfe\xfd"

    receipt = await consumer.process_event(bad_bytes, partition=0, offset=5)

    assert receipt["status"] == "FAILED"
    assert receipt["failed_event_stored"] is True
    assert receipt["dlq"] is True
    assert receipt["error_type"] == "UnicodeDecodeError"


@pytest.mark.asyncio
async def test_unsupported_type_stored_durably(fake_redis):
    """Verify unsupported data type is stored durably."""
    consumer = FailedEventStorage(redis_client=fake_redis)

    receipt = await consumer.process_event(123456)

    assert receipt["status"] == "FAILED"
    assert receipt["failed_event_stored"] is True
    assert receipt["dlq"] is True
    assert receipt["error_type"] == "TypeError"


# =============================================================================
# 9. Topic Authorization & Schema Errors Stored Durably
# =============================================================================

@pytest.mark.asyncio
async def test_unauthorized_topic_stored_durably(fake_redis):
    """Verify unauthorized topic errors are persisted to failed-event storage."""
    consumer = FailedEventStorage(redis_client=fake_redis)
    event = make_test_event(event_id="evt_unauth_storage", topic="unauthorized.bad.topic")

    receipt = await consumer.process_event(event, topic="unauthorized.bad.topic")

    assert receipt["status"] == "FAILED"
    assert receipt["failed_event_stored"] is True
    assert receipt["dlq"] is True

    record = consumer.get_failed_event("evt_unauth_storage")
    assert record is not None
    assert "Authorization failure" in record["error"]


@pytest.mark.asyncio
async def test_missing_schema_fields_stored_durably(fake_redis):
    """Verify schema validation failures are persisted to failed-event storage."""
    consumer = FailedEventStorage(redis_client=fake_redis)
    broken_event = {"event_id": "evt_missing_fields"}

    receipt = await consumer.process_event(broken_event)

    assert receipt["status"] == "FAILED"
    assert receipt["failed_event_stored"] is True
    assert receipt["dlq"] is True

    record = consumer.get_failed_event("evt_missing_fields")
    assert record is not None
    assert "Schema validation error" in record["error"]


# =============================================================================
# 10. MessageEnvelope Support
# =============================================================================

@pytest.mark.asyncio
async def test_message_envelope_processing_and_storage(fake_redis):
    """Verify MessageEnvelope objects work seamlessly."""
    def fail_env(p):
        raise ValueError("Invalid envelope payload value")

    consumer = FailedEventStorage(redis_client=fake_redis, handler=fail_env)
    envelope = MessageEnvelope(
        message_id=uuid.uuid4(),
        sender=AgentAddress(
            agent_id="test-agent",
            agent_type="dispatch",
            tenant_id="tenant-envelope",
        ),
        recipient=None,
        message_type=MessageType.EVENT,
        payload={
            "event_id": "evt_envelope_stored_1",
            "tenant_id": "tenant-envelope",
            "schema_version": 1,
            "correlation_id": "corr-env-fail",
        },
        correlation_id="corr-env-fail",
        topic="fieldops.events",
    )

    receipt = await consumer.process_event(envelope)

    assert receipt["status"] == "FAILED"
    assert receipt["failed_event_stored"] is True

    record = consumer.get_failed_event("evt_envelope_stored_1")
    assert record is not None
    assert record["event_id"] == "evt_envelope_stored_1"
    assert record["correlation_id"] == "corr-env-fail"


# =============================================================================
# 11. Bounded Recovery Loop & Automatic Resolution
# =============================================================================

@pytest.mark.asyncio
async def test_recover_event_marks_record_resolved(fake_redis):
    """
    Verify recover_event succeeds on retry, marks the stored failed event as resolved,
    and returns the required output contract.
    """
    attempts = 0

    def flaky_handler(payload):
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise ConnectionError("Transient network glitch")
        return {"status": "SUCCESS"}

    consumer = FailedEventStorage(redis_client=fake_redis, handler=flaky_handler, max_retries=3)
    event = make_test_event(event_id="evt_flaky_rec_001")

    # Simulate prior stored failure
    consumer.store_failed_event({"event_id": "evt_flaky_rec_001", "tenant_id": "tenant-1", "error": "Transient glitch"})
    assert consumer.get_failed_event("evt_flaky_rec_001")["resolved"] is False

    # Execute recovery
    receipt = await consumer.recover_event(event)

    assert receipt["status"] == "RECOVERED"
    assert receipt["retries"] == 2
    assert receipt["idempotent"] is True
    assert receipt["dlq"] is False

    # Stored record must now be marked resolved!
    assert consumer.get_failed_event("evt_flaky_rec_001")["resolved"] is True


@pytest.mark.asyncio
async def test_recover_event_exhaustion_quarantines(fake_redis):
    """Verify exhausted retries quarantine event and update failed-event storage."""
    def always_fail(payload):
        raise TimeoutError("Permanent timeout")

    consumer = FailedEventStorage(redis_client=fake_redis, handler=always_fail, max_retries=2)
    event = make_test_event(event_id="evt_exhaust_fail")

    receipt = await consumer.recover_event(event)

    assert receipt["status"] == "FAILED"
    assert receipt["dlq"] is True
    assert receipt["failed_event_stored"] is True
    assert receipt["retries"] == 2


# =============================================================================
# 12. Celery Tasks Integration
# =============================================================================

def test_celery_task_success(fake_redis):
    """Verify process_failed_event_storage_task runs cleanly."""
    event = make_test_event(event_id="evt_celery_storage_001")

    result = _process_failed_event_storage_once(
        redis=fake_redis,
        event_payload=event,
        topic="fieldops.events",
    )

    assert result["status"] == "PROCESSED"
    assert result["event_id"] == "evt_celery_storage_001"


def test_celery_task_alias(fake_redis):
    """Verify add_failed_event_storage_task delegates to main task."""
    event = make_test_event(event_id="evt_celery_alias_001")

    with patch("app.tasks.get_redis_client", return_value=fake_redis):
        result = add_failed_event_storage_task(event_payload=event)

    assert result["status"] == "PROCESSED"


# =============================================================================
# 13. Operational Metrics
# =============================================================================

@pytest.mark.asyncio
async def test_admin_metrics_storage_reporting():
    """Verify get_storage_metrics returns accurate operational metrics."""
    FailedEventStorage.reset_metrics()

    m1 = FailedEventStorage.get_storage_metrics()
    assert m1["status"] == "healthy"
    assert m1["consumer"] == "Add_failed_event_storage"
    assert m1["metrics"]["failed_events_stored"] == 0

