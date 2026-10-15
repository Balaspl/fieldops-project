import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.dispatch_consumer import (
    ConsumeReceipt,
    DispatchConsumer,
    DispatchEventConsumer,
)
from app.services.ai.FieldOpsAI.schemas.agent_messages import (
    AgentAddress,
    DispatchEventMessage,
    JobEventMessage,
    MessageType,
)
from app.tasks import _process_dispatch_event_once, process_dispatch_event_task


@pytest.fixture
def fake_redis():
    class FakeRedis:
        def __init__(self):
            self.store = {}

        def get(self, key):
            return self.store.get(key)

        def set(self, key, value, ex=None):
            self.store[key] = value

        def delete(self, *keys):
            for k in keys:
                self.store.pop(k, None)

    return FakeRedis()


@pytest.fixture
def fake_consumer_manager():
    manager = MagicMock()
    manager.start = AsyncMock()
    manager.stop = AsyncMock()
    return manager


@pytest.mark.parametrize(
    "event_type",
    [
        "job-assigned",
        "JOB_ASSIGNED",
        "job_assigned",
        "job-completed",
        "job-cancelled",
        "job-status",
        "job-created",
        "re-dispatch",
        "technician_timeout",
    ],
)
@pytest.mark.asyncio
async def test_dispatch_consumer_primary_success_path(
    event_type,
    fake_redis,
    fake_consumer_manager,
):
    consumer = DispatchConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )

    event_id = f"evt_dispatch_{event_type.lower()}_123"
    message_payload = {
        "event_type": event_type,
        "event_id": event_id,
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "schema_version": 1,
        "technician_id": "tech_99",
        "technician_name": "John Doe",
        "old_status": "QUEUED",
        "new_status": "ASSIGNED",
    }

    with patch("app.services.dispatch_consumer.publish_dispatch_event") as mock_pub, \
         patch("app.services.dispatch_consumer.DispatchAgent.trigger_redispatch") as mock_redispatch:

        receipt = await consumer.process_event(message_payload, attempt=1)

        assert isinstance(receipt, ConsumeReceipt)
        assert receipt.is_success is True
        assert bool(receipt) is True
        assert receipt["status"] == "PROCESSED"
        assert receipt["consumer"] == "dispatch"
        assert receipt["event_id"] == event_id
        assert receipt["attempt"] == 1

        # Check domain service invocation
        norm_type = event_type.lower().replace("_", "-")
        if norm_type in ("re-dispatch", "technician-timeout"):
            mock_redispatch.assert_called_once_with("job_101")
            mock_pub.assert_not_called()
        else:
            mock_pub.assert_called_once()
            mock_redispatch.assert_not_called()

        # Check idempotency marker saved in Redis
        assert fake_redis.get(f"dispatch:event_processed:{event_id}") == "1"


@pytest.mark.asyncio
async def test_dispatch_consumer_custom_topic(fake_redis, fake_consumer_manager):
    consumer = DispatchConsumer(
        topic="fieldops.events",
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )

    payload = {
        "event_type": "job-status",
        "event_id": "evt_status_01",
        "job_id": "job_55",
        "tenant_id": "tenant-1",
        "schema_version": 1,
        "topic": "fieldops.events",
    }

    with patch("app.services.dispatch_consumer.publish_dispatch_event"):
        receipt = await consumer.process_event(payload)
        assert receipt["status"] == "PROCESSED"


@pytest.mark.asyncio
async def test_dispatch_consumer_rejects_unauthorized_topic(
    fake_redis,
    fake_consumer_manager,
):
    consumer = DispatchConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )

    payload = {
        "event_type": "job-assigned",
        "event_id": "evt_unauth_01",
        "job_id": "job_55",
        "tenant_id": "tenant-1",
        "schema_version": 1,
        "topic": "unauthorized.topic",
    }

    receipt = await consumer.process_event(payload)
    assert receipt["status"] == "FAILED"
    assert "not authorized" in receipt["error"]


@pytest.mark.asyncio
async def test_dispatch_consumer_rejects_invalid_event_type(
    fake_redis,
    fake_consumer_manager,
):
    consumer = DispatchConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )

    payload = {
        "event_type": "UNKNOWN_EVENT_TYPE",
        "event_id": "evt_unknown_01",
        "job_id": "job_55",
        "tenant_id": "tenant-1",
        "schema_version": 1,
    }

    receipt = await consumer.process_event(payload)
    assert receipt["status"] == "FAILED"
    assert "Invalid event_type" in receipt["error"]


@pytest.mark.parametrize(
    "missing_field",
    ["event_id", "job_id", "tenant_id", "schema_version"],
)
@pytest.mark.asyncio
async def test_dispatch_consumer_rejects_missing_required_fields(
    missing_field,
    fake_redis,
    fake_consumer_manager,
):
    consumer = DispatchConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )

    base_payload = {
        "event_type": "job-assigned",
        "event_id": "evt_missing_01",
        "job_id": "job_55",
        "tenant_id": "tenant-1",
        "schema_version": 1,
    }
    del base_payload[missing_field]

    receipt = await consumer.process_event(base_payload)
    assert receipt["status"] == "FAILED"
    assert missing_field in receipt["error"]


@pytest.mark.parametrize(
    "forbidden_payload",
    [
        {"password": "secret_password"},
        {"secret": "client_secret"},
        {"token": "auth_token_xyz"},
    ],
)
@pytest.mark.asyncio
async def test_dispatch_consumer_rejects_forbidden_secrets(
    forbidden_payload,
    fake_redis,
    fake_consumer_manager,
):
    consumer = DispatchConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )

    payload = {
        "event_type": "job-assigned",
        "event_id": "evt_secret_01",
        "job_id": "job_55",
        "tenant_id": "tenant-1",
        "schema_version": 1,
        **forbidden_payload,
    }

    receipt = await consumer.process_event(payload)
    assert receipt["status"] == "FAILED"
    assert "forbidden" in receipt["error"]


@pytest.mark.asyncio
async def test_dispatch_consumer_handles_domain_exception_safely(
    fake_redis,
    fake_consumer_manager,
):
    consumer = DispatchConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )

    payload = {
        "event_type": "job-assigned",
        "event_id": "evt_err_01",
        "job_id": "job_55",
        "tenant_id": "tenant-1",
        "schema_version": 1,
    }

    with patch(
        "app.services.dispatch_consumer.publish_dispatch_event",
        side_effect=RuntimeError("Redis connection lost"),
    ):
        receipt = await consumer.process_event(payload)

        assert receipt["status"] == "FAILED"
        assert "Redis connection lost" in receipt["error"]
        assert fake_redis.get("dispatch:event_processed:evt_err_01") is None


@pytest.mark.asyncio
async def test_dispatch_consumer_idempotency(fake_redis, fake_consumer_manager):
    consumer = DispatchConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )

    payload = {
        "event_type": "job-assigned",
        "event_id": "evt_idem_101",
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "schema_version": 1,
    }

    with patch("app.services.dispatch_consumer.publish_dispatch_event") as mock_pub:
        # First call processes successfully
        res1 = await consumer.process_event(payload, attempt=1)
        assert res1["status"] == "PROCESSED"
        assert mock_pub.call_count == 1
        assert fake_redis.get("dispatch:event_processed:evt_idem_101") == "1"

        # Second call hits idempotency key and does not re-invoke domain service
        res2 = await consumer.process_event(payload, attempt=2)
        assert res2["status"] == "PROCESSED"
        assert res2.get("idempotent_duplicate") is True
        assert mock_pub.call_count == 1


@pytest.mark.asyncio
async def test_dispatch_consumer_retries_after_failure(
    fake_redis,
    fake_consumer_manager,
):
    consumer = DispatchConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )

    payload = {
        "event_type": "job-assigned",
        "event_id": "evt_retry_01",
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "schema_version": 1,
    }

    with patch("app.services.dispatch_consumer.publish_dispatch_event") as mock_pub:
        # Fail first attempt
        mock_pub.side_effect = RuntimeError("Temporary outage")
        res1 = await consumer.process_event(payload, attempt=1)
        assert res1["status"] == "FAILED"
        assert fake_redis.get("dispatch:event_processed:evt_retry_01") is None

        # Succeed second attempt
        mock_pub.side_effect = None
        res2 = await consumer.process_event(payload, attempt=2)
        assert res2["status"] == "PROCESSED"
        assert res2["attempt"] == 2
        assert fake_redis.get("dispatch:event_processed:evt_retry_01") == "1"


def test_process_dispatch_event_task_and_once(fake_redis):
    payload = {
        "event_type": "job-assigned",
        "event_id": "evt_task_01",
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "schema_version": 1,
    }

    with patch("app.services.dispatch_consumer.publish_dispatch_event"):
        # First call
        res1 = _process_dispatch_event_once(
            redis=fake_redis,
            event_payload=payload,
            attempt=1,
        )
        assert res1["status"] == "PROCESSED"
        assert fake_redis.get("dispatch:event_processed:evt_task_01") == "1"

        # Duplicate call
        res2 = _process_dispatch_event_once(
            redis=fake_redis,
            event_payload=payload,
            attempt=2,
        )
        assert res2["status"] == "PROCESSED"
        assert res2.get("idempotent_duplicate") is True


@pytest.mark.asyncio
async def test_dispatch_consumer_context_manager(fake_consumer_manager):
    consumer = DispatchConsumer(consumer_manager=fake_consumer_manager)

    async with consumer as c:
        assert c is consumer
        fake_consumer_manager.start.assert_awaited_once()

    fake_consumer_manager.stop.assert_awaited_once()


def test_dispatch_event_message_schema():
    sender = AgentAddress(
        agent_type="dispatch",
        agent_id="dispatcher-01",
        tenant_id="tenant-1",
    )

    msg = DispatchEventMessage(
        sender=sender,
        topic="fieldops.job.events",
        message_type=MessageType.EVENT,
        payload={
            "event_type": "job-assigned",
            "event_id": "evt_schema_01",
            "job_id": "job_777",
            "tenant_id": "tenant-1",
            "schema_version": 1,
        },
    )

    assert msg.topic == "fieldops.job.events"
    assert msg.payload["event_type"] == "job-assigned"
    assert msg.payload["schema_version"] == 1

    # Alias check
    assert JobEventMessage is DispatchEventMessage
    assert DispatchEventConsumer is DispatchConsumer

