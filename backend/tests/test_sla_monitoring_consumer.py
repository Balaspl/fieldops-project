from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.services.sla_monitoring_consumer import (
    ConsumeReceipt,
    SLAMonitoringConsumer,
    SLAConsumer,
    SLAEventConsumer,
)
from app.services.ai.FieldOpsAI.schemas.agent_messages import (
    AgentAddress,
    MessageEnvelope,
    MessageType,
    SLAEventMessage,
)
from app.tasks import (
    _process_sla_monitoring_event_once,
    process_sla_monitoring_event_task,
)


@pytest.fixture
def fake_redis():
    class FakeRedis:
        def __init__(self):
            self.store = {}

        def get(self, key):
            return self.store.get(key)

        def set(self, key, value, ex=None):
            self.store[key] = value

        def setex(self, key, time, value):
            self.store[key] = value

        def delete(self, *keys):
            for k in keys:
                self.store.pop(k, None)

        def publish(self, channel, message):
            return 1

    return FakeRedis()


@pytest.fixture
def fake_consumer_manager():
    manager = MagicMock()
    manager.start = AsyncMock()
    manager.stop = AsyncMock()
    return manager


@pytest.fixture
def fake_sla_service():
    service = MagicMock()
    service.start_sla_timer = MagicMock()
    service.pause_sla_timer = MagicMock()
    service.resume_sla_timer = MagicMock()
    service.clear_sla_timer = MagicMock()
    service.get_sla_state = MagicMock(return_value={
        "job_id": "job_101",
        "status": "active",
        "remaining_seconds": 1800,
        "elapsed_percentage": 50.0,
        "is_breached": False,
        "is_critical": False,
    })
    return service


@pytest.mark.parametrize(
    "event_type",
    [
        "SLA_CREATED",
        "sla_created",
        "SLA_NEAR_BREACH",
        "SLA_BREACHED",
        "SLA_PAUSED",
        "SLA_RESUMED",
        "SLA_CLEARED",
        "SLA_MILESTONE",
    ],
)
@pytest.mark.asyncio
async def test_sla_monitoring_consumer_primary_success_path(
    event_type,
    fake_redis,
    fake_consumer_manager,
    fake_sla_service,
):
    consumer = SLAMonitoringConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        sla_service=fake_sla_service,
    )

    event_id = f"evt_sla_{event_type.lower()}_101"
    payload = {
        "event_type": event_type,
        "event_id": event_id,
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "deadline": "2026-10-16T18:00:00Z",
        "sla_state": "active",
        "schema_version": 1,
    }

    with patch("app.services.sla_monitoring_consumer.publish_sla_event") as mock_pub:
        receipt = await consumer.process_event(payload, attempt=1)

        assert isinstance(receipt, ConsumeReceipt)
        assert receipt.is_success is True
        assert bool(receipt) is True
        assert receipt["status"] == "PROCESSED"
        assert receipt["consumer"] == "SLA_monitoring"
        assert receipt["event_id"] == event_id
        assert receipt["attempt"] == 1

        mock_pub.assert_called_once()
        assert fake_redis.get(f"sla:event_processed:{event_id}") == "1"


@pytest.mark.asyncio
async def test_sla_monitoring_consumer_validates_deadline_and_state(
    fake_redis,
    fake_consumer_manager,
    fake_sla_service,
):
    consumer = SLAMonitoringConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        sla_service=fake_sla_service,
    )

    # 1. Invalid deadline format
    bad_deadline_payload = {
        "event_type": "SLA_CREATED",
        "event_id": "evt_bad_deadline",
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "deadline": "invalid_date_not_iso",
        "schema_version": 1,
    }
    res1 = await consumer.process_event(bad_deadline_payload)
    assert res1["status"] == "FAILED"
    assert res1["consumer"] == "SLA_monitoring"
    assert "Invalid SLA deadline" in res1["error"]

    # 2. Invalid SLA state
    bad_state_payload = {
        "event_type": "SLA_CREATED",
        "event_id": "evt_bad_state",
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "sla_state": "invalid_sla_status_xyz",
        "schema_version": 1,
    }
    res2 = await consumer.process_event(bad_state_payload)
    assert res2["status"] == "FAILED"
    assert res2["consumer"] == "SLA_monitoring"
    assert "Invalid SLA state" in res2["error"]

    # 3. Blank job context
    blank_job_payload = {
        "event_type": "SLA_CREATED",
        "event_id": "evt_blank_job",
        "job_id": "   ",
        "tenant_id": "tenant-1",
        "schema_version": 1,
    }
    res3 = await consumer.process_event(blank_job_payload)
    assert res3["status"] == "FAILED"
    assert "Invalid job context" in res3["error"]


@pytest.mark.asyncio
async def test_sla_monitoring_consumer_custom_topic(
    fake_redis,
    fake_consumer_manager,
    fake_sla_service,
):
    consumer = SLAMonitoringConsumer(
        topic="fieldops.events",
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        sla_service=fake_sla_service,
    )

    payload = {
        "event_type": "SLA_CREATED",
        "event_id": "evt_custom_topic_01",
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "schema_version": 1,
        "topic": "fieldops.events",
    }

    with patch("app.services.sla_monitoring_consumer.publish_sla_event"):
        receipt = await consumer.process_event(payload)
        assert receipt["status"] == "PROCESSED"
        assert receipt["consumer"] == "SLA_monitoring"


@pytest.mark.asyncio
async def test_sla_monitoring_consumer_rejects_unauthorized_topic(
    fake_redis,
    fake_consumer_manager,
    fake_sla_service,
):
    consumer = SLAMonitoringConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        sla_service=fake_sla_service,
    )

    payload = {
        "event_type": "SLA_CREATED",
        "event_id": "evt_unauth_topic",
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "schema_version": 1,
        "topic": "unauthorized.topic",
    }

    receipt = await consumer.process_event(payload)
    assert receipt["status"] == "FAILED"
    assert "not authorized" in receipt["error"]


@pytest.mark.parametrize(
    "missing_field",
    [
        "event_id",
        "job_id",
        "tenant_id",
        "schema_version",
    ],
)
@pytest.mark.asyncio
async def test_sla_monitoring_consumer_rejects_missing_required_fields(
    missing_field,
    fake_redis,
    fake_consumer_manager,
    fake_sla_service,
):
    consumer = SLAMonitoringConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        sla_service=fake_sla_service,
    )

    payload = {
        "event_type": "SLA_CREATED",
        "event_id": "evt_missing_test",
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "schema_version": 1,
    }
    del payload[missing_field]

    receipt = await consumer.process_event(payload)
    assert receipt["status"] == "FAILED"
    assert missing_field in receipt["error"]


@pytest.mark.asyncio
async def test_sla_monitoring_consumer_rejects_invalid_event_type(
    fake_redis,
    fake_consumer_manager,
    fake_sla_service,
):
    consumer = SLAMonitoringConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        sla_service=fake_sla_service,
    )

    payload = {
        "event_type": "INVALID_SLA_EVENT",
        "event_id": "evt_invalid_type",
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "schema_version": 1,
    }

    receipt = await consumer.process_event(payload)
    assert receipt["status"] == "FAILED"
    assert "Invalid event_type" in receipt["error"]


@pytest.mark.parametrize(
    "forbidden_payload",
    [
        {"password": "plain_password_123"},
        {"secret": "api_secret_abc"},
        {"token": "bearer_jwt_token_xyz"},
    ],
)
@pytest.mark.asyncio
async def test_sla_monitoring_consumer_rejects_forbidden_secrets(
    forbidden_payload,
    fake_redis,
    fake_consumer_manager,
    fake_sla_service,
):
    consumer = SLAMonitoringConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        sla_service=fake_sla_service,
    )

    payload = {
        "event_type": "SLA_CREATED",
        "event_id": "evt_forbidden_test",
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "schema_version": 1,
        **forbidden_payload,
    }

    receipt = await consumer.process_event(payload)
    assert receipt["status"] == "FAILED"
    assert "forbidden sensitive keys" in receipt["error"]


@pytest.mark.asyncio
async def test_sla_monitoring_consumer_idempotency_prevents_duplicate_effects(
    fake_redis,
    fake_consumer_manager,
    fake_sla_service,
):
    consumer = SLAMonitoringConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        sla_service=fake_sla_service,
    )

    event_id = "evt_idem_sla_01"
    payload = {
        "event_type": "SLA_CREATED",
        "event_id": event_id,
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "deadline": "2026-10-16T18:00:00Z",
        "schema_version": 1,
    }

    with patch("app.services.sla_monitoring_consumer.publish_sla_event") as mock_pub:
        # First call: successfully processed
        res1 = await consumer.process_event(payload, attempt=1)
        assert res1["status"] == "PROCESSED"
        assert res1["consumer"] == "SLA_monitoring"
        assert mock_pub.call_count == 1
        assert fake_sla_service.start_sla_timer.call_count == 1
        assert fake_redis.get(f"sla:event_processed:{event_id}") == "1"

        # Second call: duplicate event_id must NOT invoke domain services again
        res2 = await consumer.process_event(payload, attempt=2)
        assert res2["status"] == "PROCESSED"
        assert res2["consumer"] == "SLA_monitoring"
        assert res2.get("idempotent_duplicate") is True
        assert fake_sla_service.start_sla_timer.call_count == 1
        assert mock_pub.call_count == 1


@pytest.mark.asyncio
async def test_sla_monitoring_consumer_retries_after_failure(
    fake_redis,
    fake_consumer_manager,
    fake_sla_service,
):
    consumer = SLAMonitoringConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        sla_service=fake_sla_service,
    )

    event_id = "evt_retry_sla_01"
    payload = {
        "event_type": "SLA_PAUSED",
        "event_id": event_id,
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "schema_version": 1,
    }

    with patch("app.services.sla_monitoring_consumer.publish_sla_event") as mock_pub:
        # 1. Failure on attempt 1
        mock_pub.side_effect = RuntimeError("Redis connection error")
        res1 = await consumer.process_event(payload, attempt=1)
        assert res1["status"] == "FAILED"
        assert fake_redis.get(f"sla:event_processed:{event_id}") is None

        # 2. Recovery on attempt 2
        mock_pub.side_effect = None
        res2 = await consumer.process_event(payload, attempt=2)
        assert res2["status"] == "PROCESSED"
        assert res2["attempt"] == 2
        assert fake_redis.get(f"sla:event_processed:{event_id}") == "1"


def test_process_sla_monitoring_event_task_and_once(fake_redis):
    event_id = "evt_task_sla_01"
    payload = {
        "event_type": "SLA_RESUMED",
        "event_id": event_id,
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "schema_version": 1,
    }

    with patch("app.services.sla_monitoring_consumer.publish_sla_event"):
        # First call
        res1 = _process_sla_monitoring_event_once(
            redis=fake_redis,
            event_payload=payload,
            attempt=1,
        )
        assert res1["status"] == "PROCESSED"
        assert res1["consumer"] == "SLA_monitoring"
        assert fake_redis.get(f"sla:event_processed:{event_id}") == "1"

        # Duplicate call
        res2 = _process_sla_monitoring_event_once(
            redis=fake_redis,
            event_payload=payload,
            attempt=2,
        )
        assert res2["status"] == "PROCESSED"
        assert res2.get("idempotent_duplicate") is True


@pytest.mark.asyncio
async def test_sla_monitoring_consumer_context_manager(fake_consumer_manager):
    consumer = SLAMonitoringConsumer(consumer_manager=fake_consumer_manager)

    async with consumer as c:
        assert c is consumer
        fake_consumer_manager.start.assert_awaited_once()

    fake_consumer_manager.stop.assert_awaited_once()


def test_sla_monitoring_consumer_aliases():
    assert SLAConsumer is SLAMonitoringConsumer
    assert SLAEventConsumer is SLAMonitoringConsumer


def test_sla_event_message_schema():
    sender = AgentAddress(
        agent_type="monitoring",
        agent_id="sla-producer-01",
        tenant_id="tenant-1",
    )

    msg = SLAEventMessage(
        sender=sender,
        topic="fieldops.sla.events",
        message_type=MessageType.EVENT,
        payload={
            "event_type": "SLA_CREATED",
            "event_id": "evt_schema_sla_01",
            "job_id": "job_101",
            "tenant_id": "tenant-1",
            "schema_version": 1,
        },
    )

    assert msg.topic == "fieldops.sla.events"
    assert msg.payload["event_id"] == "evt_schema_sla_01"

