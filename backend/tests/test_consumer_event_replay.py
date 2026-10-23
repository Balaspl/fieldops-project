"""
test_consumer_event_replay.py

Comprehensive test suite for controlled Kafka event replay and state recovery
supporting operators after outages, fixes, and DLQ remediation.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.redis_client import get_redis_client
from app.services.consumer_event_replay import (
    ConsumerEventReplay,
    EventReplayReceipt,
    AddEventReplaySupport,
    Add_event_replay_support,
    EventReplayService,
    ControlledEventReplay,
)
from app.services.add_event_replay_support import (
    ConsumerEventReplay as AliasConsumerEventReplay,
    AddEventReplaySupport as AliasAddEventReplaySupport,
)
from app.services.consumer_error_handler import ErrorClassification
from app.services.ai.FieldOpsAI.schemas.agent_messages import (
    AgentAddress,
    MessageEnvelope,
    MessageType,
)
from app.tasks import (
    _process_event_replay_once,
    process_event_replay_task,
    add_event_replay_support_task,
    replay_batch_events_task,
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
    Verify recovery returns the exact expected output contract specified in Story 7.12:
    {
        "status": "RECOVERED",
        "event_id": "evt_01JEXAMPLE",
        "retries": 1,
        "idempotent": True,
        "dlq": False
    }
    """
    consumer = ConsumerEventReplay(redis_client=fake_redis)
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


def test_event_replay_receipt_properties():
    """Verify boolean logic and property helpers of EventReplayReceipt."""
    r_success = EventReplayReceipt({
        "status": "RECOVERED",
        "event_id": "evt_1",
        "idempotent": True,
        "replayed": True,
        "dlq": False,
    })
    assert r_success.is_success is True
    assert r_success.is_replayed is True
    assert r_success.is_recovered is True
    assert bool(r_success) is True

    r_failed = EventReplayReceipt({
        "status": "FAILED",
        "event_id": "evt_2",
        "dlq": True,
    })
    assert r_failed.is_success is False
    assert r_failed.is_dlq is True


# =============================================================================
# 2. Aliases and Naming Compatibility
# =============================================================================

def test_aliases_and_naming():
    """Verify story naming and aliases reference ConsumerEventReplay."""
    assert AddEventReplaySupport is ConsumerEventReplay
    assert Add_event_replay_support is ConsumerEventReplay
    assert EventReplayService is ConsumerEventReplay
    assert ControlledEventReplay is ConsumerEventReplay
    assert AliasConsumerEventReplay is ConsumerEventReplay
    assert AliasAddEventReplaySupport is ConsumerEventReplay
    assert ConsumerEventReplay.CONSUMER_NAME == "Add_event_replay_support"


# =============================================================================
# 3. Authorized Operator Replay (Primary Success Path)
# =============================================================================

@pytest.mark.asyncio
async def test_authorized_operator_replay_primary_success(fake_redis):
    """
    Verify an authorized operator can safely trigger event replay.
    Replay audit headers are injected and domain handler is invoked.
    """
    executed_payloads = []

    def mock_domain_handler(payload):
        executed_payloads.append(dict(payload))
        return {"status": "SUCCESS"}

    consumer = ConsumerEventReplay(redis_client=fake_redis, handler=mock_domain_handler)
    event = make_test_event(event_id="evt_replay_001")

    receipt = await consumer.replay_event(
        event_or_payload=event,
        operator_role="operator",
        operator_id="op_jane_doe",
        reason="Disaster recovery catch-up",
    )

    assert receipt["status"] == "RECOVERED"
    assert receipt["event_id"] == "evt_replay_001"
    assert receipt["retries"] == 1
    assert receipt["idempotent"] is True
    assert receipt["replayed"] is True
    assert receipt["dlq"] is False

    # Verify audit headers were injected
    assert len(executed_payloads) == 1
    p = executed_payloads[0]
    assert p["replay"] is True
    assert p["replayed_by"] == "op_jane_doe"
    assert p["replay_reason"] == "Disaster recovery catch-up"
    assert "replayed_at" in p

    # Verify Redis processed marker
    assert consumer.is_already_processed("evt_replay_001") is True


# =============================================================================
# 4. Unauthorized Access Rejection (Requirement 1)
# =============================================================================

@pytest.mark.asyncio
async def test_unauthorized_operator_replay_rejected(fake_redis):
    """
    Verify unauthorized roles (e.g. viewer, customer, guest) are rejected immediately.
    """
    handler_called = False

    def mock_handler(payload):
        nonlocal handler_called
        handler_called = True
        return {"status": "SUCCESS"}

    consumer = ConsumerEventReplay(redis_client=fake_redis, handler=mock_handler)
    event = make_test_event(event_id="evt_unauth_1")

    for unauth_role in ["viewer", "guest", "customer", "technician", ""]:
        receipt = await consumer.replay_event(
            event_or_payload=event,
            operator_role=unauth_role,
            operator_id="bad_actor",
        )
        assert receipt["status"] == "UNAUTHORIZED"
        assert receipt.is_success is False
        assert "Permission denied" in receipt["error"]
        assert handler_called is False


# =============================================================================
# 5. Preservation of Event Identity & Schema Versions (Requirement 1)
# =============================================================================

@pytest.mark.asyncio
async def test_identity_and_schema_version_preservation(fake_redis):
    """
    Verify original event_id, schema_version, tenant_id, and correlation_id are strictly preserved.
    """
    received_payload = None

    def mock_handler(payload):
        nonlocal received_payload
        received_payload = dict(payload)
        return {"status": "SUCCESS"}

    consumer = ConsumerEventReplay(redis_client=fake_redis, handler=mock_handler)
    event = make_test_event(
        event_id="evt_preserve_immutable_1",
        tenant_id="tenant-acme",
        correlation_id="corr-immutable-777",
        payload_extra={"schema_version": 2, "custom_metric": 42},
    )

    receipt = await consumer.replay_event(
        event_or_payload=event,
        operator_role="admin",
        operator_id="admin_1",
    )

    assert receipt["event_id"] == "evt_preserve_immutable_1"
    assert receipt["tenant_id"] == "tenant-acme"
    assert receipt["correlation_id"] == "corr-immutable-777"
    assert received_payload["event_id"] == "evt_preserve_immutable_1"
    assert received_payload["schema_version"] == 2
    assert received_payload["tenant_id"] == "tenant-acme"
    assert received_payload["correlation_id"] == "corr-immutable-777"
    assert received_payload["custom_metric"] == 42


# =============================================================================
# 6. Duplicate Side Effect Prevention (force=False vs force=True)
# =============================================================================

@pytest.mark.asyncio
async def test_duplicate_prevention_force_false_and_force_true(fake_redis):
    """
    Verify:
    1. force=False: Already processed event is acknowledged without running handler (zero side effects).
    2. force=True: Clears marker and forces reconciliation re-execution.
    """
    execution_count = 0

    def mock_handler(payload):
        nonlocal execution_count
        execution_count += 1
        return {"status": "SUCCESS"}

    consumer = ConsumerEventReplay(redis_client=fake_redis, handler=mock_handler)
    event = make_test_event(event_id="evt_dup_check_10")

    # 1. Initial replay
    r1 = await consumer.replay_event(event, operator_role="operator", force=False)
    assert r1["status"] == "RECOVERED"
    assert execution_count == 1

    # 2. Duplicate replay without force (force=False)
    r2 = await consumer.replay_event(event, operator_role="operator", force=False)
    assert r2["status"] == "RECOVERED"
    assert r2.get("skipped_duplicate") is True
    assert r2["retries"] == 0
    # Zero business side effects! Handler was not called again!
    assert execution_count == 1

    # 3. Forced replay (force=True) for deliberate state fix
    r3 = await consumer.replay_event(event, operator_role="operator", force=True)
    assert r3["status"] == "RECOVERED"
    assert r3.get("replayed") is True
    assert execution_count == 2  # Re-executed intentionally!


# =============================================================================
# 7. Batch Replay Support
# =============================================================================

@pytest.mark.asyncio
async def test_batch_replay_execution(fake_redis):
    """Verify replay_batch replays a collection of events."""
    replayed_ids = []

    def mock_handler(payload):
        replayed_ids.append(payload["event_id"])
        return {"status": "SUCCESS"}

    consumer = ConsumerEventReplay(redis_client=fake_redis, handler=mock_handler)
    events = [
        make_test_event(event_id="evt_batch_1"),
        make_test_event(event_id="evt_batch_2"),
        make_test_event(event_id="evt_batch_3"),
    ]

    receipts = await consumer.replay_batch(
        events=events,
        operator_role="platform_operator",
        operator_id="batch_worker",
    )

    assert len(receipts) == 3
    assert all(r.is_success for r in receipts)
    assert replayed_ids == ["evt_batch_1", "evt_batch_2", "evt_batch_3"]


# =============================================================================
# 8. DLQ Failed Event Replay Support
# =============================================================================

@pytest.mark.asyncio
async def test_dlq_failed_event_replay(fake_redis):
    """Verify replay_dlq_events fetches isolated DLQ records and replays them."""
    replayed_ids = []

    def mock_handler(payload):
        replayed_ids.append(payload["event_id"])
        return {"status": "SUCCESS"}

    consumer = ConsumerEventReplay(redis_client=fake_redis, handler=mock_handler)

    # Populate fake DLQ storage
    dlq_record = {
        "event_id": "evt_dlq_poison_1",
        "tenant_id": "tenant-dlq",
        "schema_version": 1,
        "payload": {
            "event_id": "evt_dlq_poison_1",
            "tenant_id": "tenant-dlq",
            "schema_version": 1,
            "job_id": "job-dlq-99",
        },
    }
    fake_redis.rpush("consumer:dlq", json.dumps(dlq_record))

    receipts = await consumer.replay_dlq_events(
        operator_role="admin",
        operator_id="dlq_recovery_op",
    )

    assert len(receipts) == 1
    assert receipts[0]["status"] == "RECOVERED"
    assert receipts[0]["event_id"] == "evt_dlq_poison_1"
    assert replayed_ids == ["evt_dlq_poison_1"]


# =============================================================================
# 9. Security & Forbidden Keys Rejection
# =============================================================================

@pytest.mark.asyncio
async def test_security_violation_rejection(fake_redis):
    """Verify payloads containing forbidden sensitive keys are rejected immediately."""
    consumer = ConsumerEventReplay(redis_client=fake_redis)

    for bad_key in ["password", "token", "secret", "api_key"]:
        bad_event = make_test_event(
            event_id=f"evt_replay_bad_{bad_key}",
            payload_extra={bad_key: "exposed_secret_val"},
        )
        receipt = await consumer.replay_event(bad_event, operator_role="admin")
        assert receipt["status"] == "FAILED"
        assert receipt["error_type"] == "SecurityPolicyError"
        assert receipt["dlq"] is True


# =============================================================================
# 10. Malformed Messages & Schema Validation
# =============================================================================

@pytest.mark.asyncio
async def test_malformed_messages_and_validation(fake_redis):
    """Verify malformed JSON, invalid types, and missing fields fail safely."""
    consumer = ConsumerEventReplay(redis_client=fake_redis)

    # 1. Malformed JSON
    r1 = await consumer.replay_event("NOT_A_VALID_JSON{:::}", operator_role="admin")
    assert r1["status"] == "FAILED"
    assert r1["error_type"] == "JSONDecodeError"

    # 2. Unsupported type
    r2 = await consumer.replay_event(12345, operator_role="admin")
    assert r2["status"] == "FAILED"
    assert r2.is_success is False

    # 3. Missing fields
    r3 = await consumer.replay_event({"payload": {"event_id": "missing_others"}}, operator_role="admin")
    assert r3["status"] == "FAILED"
    assert "ValidationError" in r3["error_type"]


# =============================================================================
# 11. MessageEnvelope Support
# =============================================================================

@pytest.mark.asyncio
async def test_message_envelope_support(fake_redis):
    """Verify ConsumerEventReplay seamlessly unwraps MessageEnvelope objects."""
    consumer = ConsumerEventReplay(redis_client=fake_redis)

    envelope = MessageEnvelope(
        sender=AgentAddress(
            agent_id="test-dispatch",
            agent_type="dispatch",
            tenant_id="tenant-envelope",
        ),
        recipient=None,
        message_type=MessageType.EVENT,
        correlation_id="corr-replay-env-1",
        payload={
            "event_id": "evt_env_replay_1",
            "tenant_id": "tenant-envelope",
            "schema_version": 1,
            "job_id": "job-env-1",
        },
        topic="fieldops.events",
    )

    receipt = await consumer.replay_event(envelope, operator_role="admin")
    assert receipt["status"] == "RECOVERED"
    assert receipt["event_id"] == "evt_env_replay_1"
    assert receipt["tenant_id"] == "tenant-envelope"
    assert receipt["correlation_id"] == "corr-replay-env-1"


# =============================================================================
# 12. Celery Background Tasks Integration
# =============================================================================

def test_celery_task_integration(monkeypatch, fake_redis):
    """Verify Celery task executes event replay and returns receipt."""
    monkeypatch.setattr("app.tasks.get_redis_client", lambda: fake_redis)

    payload = make_test_event(event_id="evt_celery_replay_1")["payload"]

    res1 = _process_event_replay_once(
        redis=fake_redis,
        event_payload=payload,
        operator_role="operator",
    )
    assert res1["status"] == "RECOVERED"
    assert res1["event_id"] == "evt_celery_replay_1"

    # Second execution skips duplicate
    res2 = _process_event_replay_once(
        redis=fake_redis,
        event_payload=payload,
        operator_role="operator",
        force=False,
    )
    assert res2["status"] == "RECOVERED"
    assert res2.get("skipped_duplicate") is True


# =============================================================================
# 13. Admin Replay & Metrics Endpoints
# =============================================================================

@pytest.mark.asyncio
async def test_admin_metrics_and_trigger_endpoints():
    """Verify get_kafka_replay_metrics and trigger_kafka_event_replay endpoints."""
    from app.routes.admin_metrics import get_kafka_replay_metrics, trigger_kafka_event_replay

    metrics = await get_kafka_replay_metrics()
    assert metrics["status"] == "healthy"
    assert metrics["consumer"] == "Add_event_replay_support"
    assert "metrics" in metrics

    # Test trigger API
    request_data = {
        "event": {
            "event_id": "evt_api_replay_1",
            "tenant_id": "tenant-api",
            "schema_version": 1,
            "job_id": "job-api-101",
        },
        "operator_role": "admin",
        "operator_id": "admin_api_user",
        "reason": "Test admin API replay",
    }
    result = await trigger_kafka_event_replay(request_data)
    assert result["status"] == "RECOVERED"
    assert result["event_id"] == "evt_api_replay_1"

