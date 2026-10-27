"""
test_event_schema_versioning.py

Comprehensive test suite for adding explicit schema version metadata and compatibility
rules to Kafka events, allowing independent evolution of producers and consumers.
"""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.redis_client import get_redis_client
from app.services.event_schema_versioning import (
    EventSchemaVersioning,
    SchemaVersioningReceipt,
    CompatibilityMode,
    AddEventSchemaVersioning,
    Add_event_schema_versioning,
    ConsumerEventSchemaVersioning,
    SchemaCompatibilityManager,
    SchemaVersioningService,
    upcast_v1_to_v2,
    downcast_v2_to_v1,
)
from app.services.add_event_schema_versioning import (
    EventSchemaVersioning as AliasEventSchemaVersioning,
    AddEventSchemaVersioning as AliasAddEventSchemaVersioning,
)
from app.services.consumer_error_handler import ErrorClassification
from app.services.ai.FieldOpsAI.schemas.agent_messages import (
    AgentAddress,
    MessageEnvelope,
    MessageType,
)
from app.tasks import (
    _process_schema_versioning_event_once,
    process_schema_versioning_event_task,
    add_event_schema_versioning_task,
)


# =============================================================================
# Fake Redis Fixtures & Message Helpers
# =============================================================================

class FakeRedis:
    def __init__(self):
        self.store = {}

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
        return count


@pytest.fixture
def fake_redis():
    return FakeRedis()


def make_test_event(
    event_id: str = "evt_01JEXAMPLE",
    tenant_id: str = "tenant-1",
    correlation_id: str = "corr-101",
    domain: str = "dispatch",
    schema_version: int = 1,
    payload_extra: dict = None,
    topic: str = "fieldops.events",
) -> dict:
    payload = {
        "event_id": event_id,
        "tenant_id": tenant_id,
        "schema_version": schema_version,
        "correlation_id": correlation_id,
        "domain": domain,
        "job_id": "job-101",
        "old_status": "ASSIGNED",
        "new_status": "COMPLETED",
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
    Verify recovery returns the exact expected output contract specified in Story 7.16:
    {
        "status": "RECOVERED",
        "event_id": "evt_01JEXAMPLE",
        "retries": 1,
        "idempotent": True,
        "dlq": False
    }
    """
    consumer = EventSchemaVersioning(redis_client=fake_redis)
    test_event = make_test_event(event_id="evt_01JEXAMPLE")

    receipt = await consumer.recover_event(test_event, partition=0, offset=15)

    assert receipt["status"] == "RECOVERED"
    assert receipt["event_id"] == "evt_01JEXAMPLE"
    assert receipt["retries"] == 1
    assert receipt["idempotent"] is True
    assert receipt["dlq"] is False
    assert receipt.is_success is True
    assert receipt.is_recovered is True
    assert bool(receipt) is True


def test_schema_versioning_receipt_properties():
    """Verify boolean logic and property helpers of SchemaVersioningReceipt."""
    r_success = SchemaVersioningReceipt({
        "status": "PROCESSED",
        "event_id": "evt_1",
        "dlq": False,
    })
    assert r_success.is_success is True
    assert bool(r_success) is True

    r_recovered = SchemaVersioningReceipt({
        "status": "RECOVERED",
        "event_id": "evt_rec",
        "dlq": False,
    })
    assert r_recovered.is_success is True
    assert r_recovered.is_recovered is True
    assert bool(r_recovered) is True

    r_failed = SchemaVersioningReceipt({
        "status": "FAILED",
        "event_id": "evt_fail",
        "dlq": False,
    })
    assert r_failed.is_success is False
    assert bool(r_failed) is False

    r_dlq = SchemaVersioningReceipt({
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
    """Verify story naming and aliases reference EventSchemaVersioning."""
    assert AddEventSchemaVersioning is EventSchemaVersioning
    assert Add_event_schema_versioning is EventSchemaVersioning
    assert ConsumerEventSchemaVersioning is EventSchemaVersioning
    assert SchemaCompatibilityManager is EventSchemaVersioning
    assert SchemaVersioningService is EventSchemaVersioning
    assert AliasEventSchemaVersioning is EventSchemaVersioning
    assert AliasAddEventSchemaVersioning is EventSchemaVersioning
    assert EventSchemaVersioning.CONSUMER_NAME == "Add_event_schema_versioning"


# =============================================================================
# 3. Explicit Schema Version Validation
# =============================================================================

def test_validate_schema_version_supported():
    """Verify supported schema versions 1 and 2 pass validation."""
    consumer = EventSchemaVersioning()

    valid_1, _, _ = consumer.validate_schema_version({"schema_version": 1})
    assert valid_1 is True

    valid_2, _, _ = consumer.validate_schema_version({"schema_version": 2})
    assert valid_2 is True


def test_validate_schema_version_missing():
    """Verify missing schema_version fails with ValidationError."""
    consumer = EventSchemaVersioning()

    valid, err_type, err_msg = consumer.validate_schema_version({})
    assert valid is False
    assert err_type == "ValidationError"
    assert "Missing required field: schema_version" in err_msg


def test_validate_schema_version_invalid_type_or_value():
    """Verify boolean, non-int, or non-positive schema_version is rejected."""
    consumer = EventSchemaVersioning()

    for invalid_ver in [True, False, "1", 0, -1, 1.5, None]:
        valid, err_type, err_msg = consumer.validate_schema_version({"schema_version": invalid_ver})
        assert valid is False
        assert err_type in ("ValidationError", "UnsupportedSchemaVersionError")


def test_validate_schema_version_unsupported_future_version():
    """Verify future unsupported schema version (e.g. 99) is rejected."""
    consumer = EventSchemaVersioning()

    valid, err_type, err_msg = consumer.validate_schema_version({"schema_version": 99})
    assert valid is False
    assert err_type == "UnsupportedSchemaVersionError"
    assert "Unsupported schema_version 99" in err_msg


# =============================================================================
# 4. Schema Migration & Upcasting Rules
# =============================================================================

def test_upcast_v1_to_v2():
    """
    Verify upcaster transforms v1 flat status fields into v2 structured transition.
    """
    v1_payload = {
        "event_id": "evt_v1",
        "schema_version": 1,
        "old_status": "PENDING",
        "new_status": "IN_PROGRESS",
    }

    v2_payload = upcast_v1_to_v2(v1_payload)
    assert v2_payload["schema_version"] == 2
    assert v2_payload["status_transition"] == {
        "from_status": "PENDING",
        "to_status": "IN_PROGRESS",
    }
    assert v2_payload["_migrated_from"] == 1


def test_downcast_v2_to_v1():
    """
    Verify downcaster adapts v2 structured transition into v1 flat status fields.
    """
    v2_payload = {
        "event_id": "evt_v2",
        "schema_version": 2,
        "status_transition": {
            "from_status": "IN_PROGRESS",
            "to_status": "COMPLETED",
        },
    }

    v1_payload = downcast_v2_to_v1(v2_payload)
    assert v1_payload["schema_version"] == 1
    assert v1_payload["old_status"] == "IN_PROGRESS"
    assert v1_payload["new_status"] == "COMPLETED"


# =============================================================================
# 5. Independent Producer & Consumer Evolution (Primary Success Path)
# =============================================================================

@pytest.mark.asyncio
async def test_v1_event_consumed_by_v2_consumer_with_upcast(fake_redis):
    """
    Primary requirement: Producers emitting older v1 events can be processed
    by newer v2 consumers via automated upcasting without breaking.
    """
    received_payloads = []

    def mock_domain_handler(payload):
        received_payloads.append(dict(payload))
        return {"status": "SUCCESS"}

    # Consumer expects target_version=2
    consumer = EventSchemaVersioning(redis_client=fake_redis, target_version=2, handler=mock_domain_handler)
    event_v1 = make_test_event(event_id="evt_evolve_001", schema_version=1)

    receipt = await consumer.process_event(event_v1)

    assert receipt["status"] == "PROCESSED"
    assert receipt["schema_version"] == 2
    assert len(received_payloads) == 1
    # Domain handler received upcasted payload
    assert received_payloads[0]["schema_version"] == 2
    assert received_payloads[0]["status_transition"]["from_status"] == "ASSIGNED"
    assert received_payloads[0]["status_transition"]["to_status"] == "COMPLETED"


@pytest.mark.asyncio
async def test_v2_event_consumed_directly(fake_redis):
    """Verify v2 events are processed directly by v2 consumer without modification."""
    received = []

    def mock_handler(payload):
        received.append(dict(payload))
        return {"status": "SUCCESS"}

    consumer = EventSchemaVersioning(redis_client=fake_redis, target_version=2, handler=mock_handler)
    event_v2 = make_test_event(
        event_id="evt_v2_direct",
        schema_version=2,
        payload_extra={
            "status_transition": {"from_status": "DISPATCHED", "to_status": "ON_SITE"}
        },
    )

    receipt = await consumer.process_event(event_v2)

    assert receipt["status"] == "PROCESSED"
    assert receipt["schema_version"] == 2
    assert received[0]["status_transition"]["from_status"] == "DISPATCHED"


# =============================================================================
# 6. Compatibility Modes: STRICT vs FULL
# =============================================================================

@pytest.mark.asyncio
async def test_strict_compatibility_mode_rejects_version_mismatch(fake_redis):
    """
    In STRICT mode, an event with version != target_version is rejected.
    """
    consumer = EventSchemaVersioning(
        redis_client=fake_redis,
        target_version=2,
        compatibility_mode=CompatibilityMode.STRICT,
    )
    event_v1 = make_test_event(event_id="evt_strict_fail", schema_version=1)

    receipt = await consumer.process_event(event_v1)

    assert receipt["status"] == "FAILED"
    assert receipt["error_type"] == "SchemaCompatibilityError"
    assert receipt["dlq"] is True


# =============================================================================
# 7. Terminal Poison Messages & Unsupported Schema Versions to DLQ
# =============================================================================

@pytest.mark.asyncio
async def test_unsupported_schema_version_routes_to_dlq(fake_redis):
    """Events with unknown schema versions are rejected to DLQ immediately."""
    consumer = EventSchemaVersioning(redis_client=fake_redis)
    bad_version_event = make_test_event(event_id="evt_unsupported_ver", schema_version=99)

    receipt = await consumer.process_event(bad_version_event)

    assert receipt["status"] == "FAILED"
    assert receipt["dlq"] is True
    assert receipt["error_type"] == "UnsupportedSchemaVersionError"


@pytest.mark.asyncio
async def test_missing_schema_version_routes_to_dlq(fake_redis):
    """Events missing schema_version are rejected to DLQ."""
    consumer = EventSchemaVersioning(redis_client=fake_redis)
    broken_event = {
        "event_id": "evt_no_version",
        "tenant_id": "tenant-1",
    }

    receipt = await consumer.process_event(broken_event)

    assert receipt["status"] == "FAILED"
    assert receipt["dlq"] is True
    assert receipt["error_type"] == "ValidationError"


@pytest.mark.asyncio
async def test_malformed_json_routes_to_dlq(fake_redis):
    """Unparseable JSON string routes to DLQ."""
    consumer = EventSchemaVersioning(redis_client=fake_redis)
    receipt = await consumer.process_event("{bad_json_string")

    assert receipt["status"] == "FAILED"
    assert receipt["dlq"] is True
    assert receipt["error_type"] == "JSONDecodeError"


@pytest.mark.asyncio
async def test_malformed_bytes_routes_to_dlq(fake_redis):
    """Invalid UTF-8 bytes payload routes to DLQ."""
    consumer = EventSchemaVersioning(redis_client=fake_redis)
    receipt = await consumer.process_event(b"\xff\xfe\xfd")

    assert receipt["status"] == "FAILED"
    assert receipt["dlq"] is True
    assert receipt["error_type"] == "UnicodeDecodeError"


@pytest.mark.asyncio
async def test_unsupported_type_routes_to_dlq(fake_redis):
    """Unsupported data type routes to DLQ."""
    consumer = EventSchemaVersioning(redis_client=fake_redis)
    receipt = await consumer.process_event(55555)

    assert receipt["status"] == "FAILED"
    assert receipt["dlq"] is True
    assert receipt["error_type"] == "TypeError"


# =============================================================================
# 8. Security & Credential Protection
# =============================================================================

@pytest.mark.asyncio
async def test_forbidden_sensitive_keys_rejected(fake_redis):
    """Payloads containing sensitive credentials are quarantined."""
    consumer = EventSchemaVersioning(redis_client=fake_redis)

    for bad_key in ("password", "secret", "token", "api_key"):
        event = make_test_event(
            event_id=f"evt_sec_{bad_key}",
            payload_extra={bad_key: "exposed_sensitive_value"},
        )
        receipt = await consumer.process_event(event)
        assert receipt["status"] == "FAILED"
        assert receipt["dlq"] is True
        assert "Security violation" in receipt["error"]


# =============================================================================
# 9. Topic Authorization
# =============================================================================

@pytest.mark.asyncio
async def test_unauthorized_topic_rejected(fake_redis):
    """Events received on untrusted topics are rejected to DLQ."""
    consumer = EventSchemaVersioning(redis_client=fake_redis)
    event = make_test_event(event_id="evt_unauth_001", topic="unauthorized.rogue.topic")

    receipt = await consumer.process_event(event, topic="unauthorized.rogue.topic")

    assert receipt["status"] == "FAILED"
    assert receipt["dlq"] is True
    assert "Authorization failure" in receipt["error"]


# =============================================================================
# 10. MessageEnvelope Support
# =============================================================================

@pytest.mark.asyncio
async def test_message_envelope_with_schema_version(fake_redis):
    """Verify MessageEnvelope objects are unwrapped and schema validated."""
    consumer = EventSchemaVersioning(redis_client=fake_redis, target_version=2)
    envelope = MessageEnvelope(
        message_id=uuid.uuid4(),
        sender=AgentAddress(
            agent_id="test-agent",
            agent_type="dispatch",
            tenant_id="tenant-env",
        ),
        recipient=None,
        message_type=MessageType.EVENT,
        payload={
            "event_id": "evt_envelope_schema_1",
            "tenant_id": "tenant-env",
            "schema_version": 1,
            "correlation_id": "corr-env-1",
            "old_status": "CREATED",
            "new_status": "ASSIGNED",
        },
        correlation_id="corr-env-1",
        topic="fieldops.events",
    )

    receipt = await consumer.process_event(envelope)

    assert receipt["status"] == "PROCESSED"
    assert receipt["schema_version"] == 2
    assert receipt["event_id"] == "evt_envelope_schema_1"


# =============================================================================
# 11. Bounded Recovery Path
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

    consumer = EventSchemaVersioning(redis_client=fake_redis, handler=flaky_handler, max_retries=3)
    event = make_test_event(event_id="evt_flaky_schema_001")

    receipt = await consumer.recover_event(event)

    assert receipt["status"] == "RECOVERED"
    assert receipt["retries"] == 2
    assert receipt["idempotent"] is True
    assert receipt["dlq"] is False


@pytest.mark.asyncio
async def test_recover_event_exhaustion_routes_to_dlq(fake_redis):
    """Verify retry exhaustion quarantines event to DLQ."""
    def always_fail(payload):
        raise TimeoutError("Persistent database timeout")

    consumer = EventSchemaVersioning(redis_client=fake_redis, handler=always_fail, max_retries=2)
    event = make_test_event(event_id="evt_exhaust_schema")

    receipt = await consumer.recover_event(event)

    assert receipt["status"] == "FAILED"
    assert receipt["dlq"] is True
    assert receipt["retries"] == 2


# =============================================================================
# 12. Celery Tasks Integration
# =============================================================================

def test_celery_task_success(fake_redis):
    """Verify process_schema_versioning_event_task runs cleanly."""
    event = make_test_event(event_id="evt_celery_schema_001")

    result = _process_schema_versioning_event_once(
        redis=fake_redis,
        event_payload=event,
        topic="fieldops.events",
    )

    assert result["status"] == "PROCESSED"
    assert result["event_id"] == "evt_celery_schema_001"


def test_celery_task_alias(fake_redis):
    """Verify add_event_schema_versioning_task delegates to main task."""
    event = make_test_event(event_id="evt_celery_alias_001")

    with patch("app.tasks.get_redis_client", return_value=fake_redis):
        result = add_event_schema_versioning_task(event_payload=event)

    assert result["status"] == "PROCESSED"


# =============================================================================
# 13. Operational Metrics
# =============================================================================

@pytest.mark.asyncio
async def test_admin_metrics_schema_reporting():
    """Verify get_schema_metrics returns accurate operational metrics."""
    EventSchemaVersioning.reset_metrics()

    m = EventSchemaVersioning.get_schema_metrics()
    assert m["status"] == "healthy"
    assert m["consumer"] == "Add_event_schema_versioning"
    assert m["current_version"] == 2
    assert 1 in m["supported_versions"]
    assert 2 in m["supported_versions"]
    assert m["metrics"]["processed_total"] == 0

