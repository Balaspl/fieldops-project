from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

# notification_consumer currently imports this legacy symbol but does not use
# it. Provide the compatibility name during test collection without changing
# the production notification service module.
import app.services.notification_services as notification_services

if not hasattr(notification_services, "SendGridService"):
    notification_services.SendGridService = type(
        "SendGridService",
        (),
        {},
    )

from app.services.notification_consumer import (
    ConsumeReceipt,
    NotificationConsumer,
    NotificationEventConsumer,
    NotificationDeliveryConsumer,
)
from app.services.ai.FieldOpsAI.schemas.agent_messages import (
    AgentAddress,
    MessageEnvelope,
    MessageType,
    NotificationEventMessage,
)
from app.tasks import (
    _process_notification_event_once,
    process_notification_event_task,
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
def fake_router():
    router = MagicMock()
    router.email = MagicMock()
    router.email.send_email = AsyncMock(return_value=True)
    router.sms = AsyncMock(return_value=True)
    router.route = AsyncMock(return_value=None)
    return router


@pytest.mark.parametrize(
    "event_type",
    [
        "NOTIFICATION_QUEUED",
        "notification_queued",
        "notification",
        "notification-sent",
        "job_status_changed",
    ],
)
@pytest.mark.asyncio
async def test_notification_consumer_primary_success_path(
    event_type,
    fake_redis,
    fake_consumer_manager,
    fake_router,
):
    consumer = NotificationConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        router=fake_router,
    )

    event_id = f"evt_notif_{event_type.lower()}_123"
    message_payload = {
        "event_type": event_type,
        "event_id": event_id,
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "channel": "email",
        "recipient": "user@example.com",
        "subject": "Job Update",
        "message": "Your technician is on the way",
        "schema_version": 1,
    }

    with patch("app.services.notification_consumer.publish_notification_event") as mock_pub:
        receipt = await consumer.process_event(message_payload, attempt=1)

        assert isinstance(receipt, ConsumeReceipt)
        assert receipt.is_success is True
        assert bool(receipt) is True
        assert receipt["status"] == "PROCESSED"
        assert receipt["consumer"] == "notification"
        assert receipt["event_id"] == event_id
        assert receipt["attempt"] == 1

        mock_pub.assert_called_once()
        fake_router.email.send_email.assert_awaited_once_with(
            "user@example.com",
            "Job Update",
            "Your technician is on the way",
        )
        assert fake_redis.get(f"notification:event_processed:{event_id}") == "1"


@pytest.mark.asyncio
async def test_notification_consumer_sms_delivery(
    fake_redis,
    fake_consumer_manager,
    fake_router,
):
    consumer = NotificationConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        router=fake_router,
    )

    event_id = "evt_sms_001"
    payload = {
        "event_type": "notification",
        "event_id": event_id,
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "channel": "sms",
        "recipient": "+15551234567",
        "message": "Technician has arrived",
        "schema_version": 1,
    }

    with patch("app.services.notification_consumer.publish_notification_event"):
        receipt = await consumer.process_event(payload)
        assert receipt["status"] == "PROCESSED"
        assert receipt["consumer"] == "notification"
        fake_router.sms.assert_awaited_once_with(
            "+15551234567",
            "Technician has arrived",
        )


@pytest.mark.asyncio
async def test_notification_consumer_custom_topic(
    fake_redis,
    fake_consumer_manager,
    fake_router,
):
    consumer = NotificationConsumer(
        topic="fieldops.events",
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        router=fake_router,
    )

    payload = {
        "event_type": "notification",
        "event_id": "evt_custom_topic_01",
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "channel": "push",
        "schema_version": 1,
        "topic": "fieldops.events",
    }

    with patch("app.services.notification_consumer.publish_notification_event"):
        receipt = await consumer.process_event(payload)
        assert receipt["status"] == "PROCESSED"
        assert receipt["consumer"] == "notification"


@pytest.mark.asyncio
async def test_notification_consumer_rejects_unauthorized_topic(
    fake_redis,
    fake_consumer_manager,
    fake_router,
):
    consumer = NotificationConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        router=fake_router,
    )

    payload = {
        "event_type": "notification",
        "event_id": "evt_unauth_topic",
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "schema_version": 1,
        "topic": "unauthorized.topic",
    }

    receipt = await consumer.process_event(payload)
    assert receipt["status"] == "FAILED"
    assert receipt["consumer"] == "notification"
    assert "not authorized" in receipt["error"]


@pytest.mark.asyncio
async def test_notification_consumer_validates_channel(
    fake_redis,
    fake_consumer_manager,
    fake_router,
):
    consumer = NotificationConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        router=fake_router,
    )

    payload = {
        "event_type": "notification",
        "event_id": "evt_invalid_channel",
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "channel": "telepathy",
        "schema_version": 1,
    }

    receipt = await consumer.process_event(payload)
    assert receipt["status"] == "FAILED"
    assert receipt["consumer"] == "notification"
    assert "Invalid notification channel" in receipt["error"]


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
async def test_notification_consumer_rejects_missing_required_fields(
    missing_field,
    fake_redis,
    fake_consumer_manager,
    fake_router,
):
    consumer = NotificationConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        router=fake_router,
    )

    payload = {
        "event_type": "notification",
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
async def test_notification_consumer_rejects_invalid_event_type(
    fake_redis,
    fake_consumer_manager,
    fake_router,
):
    consumer = NotificationConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        router=fake_router,
    )

    payload = {
        "event_type": "INVALID_NOTIFICATION_EVENT",
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
async def test_notification_consumer_rejects_forbidden_secrets(
    forbidden_payload,
    fake_redis,
    fake_consumer_manager,
    fake_router,
):
    consumer = NotificationConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        router=fake_router,
    )

    payload = {
        "event_type": "notification",
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
async def test_notification_consumer_idempotency_prevents_duplicate_delivery(
    fake_redis,
    fake_consumer_manager,
    fake_router,
):
    consumer = NotificationConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        router=fake_router,
    )

    event_id = "evt_idem_notif_01"
    payload = {
        "event_type": "notification",
        "event_id": event_id,
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "channel": "email",
        "recipient": "user@example.com",
        "subject": "Status",
        "message": "Job dispatched",
        "schema_version": 1,
    }

    with patch("app.services.notification_consumer.publish_notification_event") as mock_pub:
        # First call: successfully processed & delivered
        res1 = await consumer.process_event(payload, attempt=1)
        assert res1["status"] == "PROCESSED"
        assert res1["consumer"] == "notification"
        assert mock_pub.call_count == 1
        assert fake_router.email.send_email.call_count == 1
        assert fake_redis.get(f"notification:event_processed:{event_id}") == "1"

        # Second call: duplicate event_id must NOT invoke delivery services again
        res2 = await consumer.process_event(payload, attempt=2)
        assert res2["status"] == "PROCESSED"
        assert res2["consumer"] == "notification"
        assert res2.get("idempotent_duplicate") is True
        # Delivery service call count remains 1
        assert fake_router.email.send_email.call_count == 1
        assert mock_pub.call_count == 1


@pytest.mark.asyncio
async def test_notification_consumer_retries_after_failure(
    fake_redis,
    fake_consumer_manager,
    fake_router,
):
    consumer = NotificationConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        router=fake_router,
    )

    event_id = "evt_retry_notif_01"
    payload = {
        "event_type": "notification",
        "event_id": event_id,
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "channel": "email",
        "recipient": "user@example.com",
        "schema_version": 1,
    }

    with patch("app.services.notification_consumer.publish_notification_event") as mock_pub:
        # 1. Delivery failure on attempt 1
        fake_router.email.send_email.side_effect = RuntimeError("SMTP connection timeout")
        res1 = await consumer.process_event(payload, attempt=1)
        assert res1["status"] == "FAILED"
        assert fake_redis.get(f"notification:event_processed:{event_id}") is None

        # 2. Recovery on attempt 2
        fake_router.email.send_email.side_effect = None
        fake_router.email.send_email.return_value = True
        res2 = await consumer.process_event(payload, attempt=2)
        assert res2["status"] == "PROCESSED"
        assert res2["attempt"] == 2
        assert fake_redis.get(f"notification:event_processed:{event_id}") == "1"


def test_process_notification_event_task_and_once(fake_redis):
    event_id = "evt_task_notif_01"
    payload = {
        "event_type": "notification",
        "event_id": event_id,
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "schema_version": 1,
    }

    with patch("app.services.notification_consumer.publish_notification_event"):
        # First call
        res1 = _process_notification_event_once(
            redis=fake_redis,
            event_payload=payload,
            attempt=1,
        )
        assert res1["status"] == "PROCESSED"
        assert res1["consumer"] == "notification"
        assert fake_redis.get(f"notification:event_processed:{event_id}") == "1"

        # Duplicate call
        res2 = _process_notification_event_once(
            redis=fake_redis,
            event_payload=payload,
            attempt=2,
        )
        assert res2["status"] == "PROCESSED"
        assert res2.get("idempotent_duplicate") is True


@pytest.mark.asyncio
async def test_notification_consumer_context_manager(fake_consumer_manager):
    consumer = NotificationConsumer(consumer_manager=fake_consumer_manager)

    async with consumer as c:
        assert c is consumer
        fake_consumer_manager.start.assert_awaited_once()

    fake_consumer_manager.stop.assert_awaited_once()


def test_notification_consumer_aliases():
    assert NotificationEventConsumer is NotificationConsumer
    assert NotificationDeliveryConsumer is NotificationConsumer


def test_notification_event_message_schema():
    sender = AgentAddress(
        agent_type="monitoring",
        agent_id="notif-producer-01",
        tenant_id="tenant-1",
    )

    msg = NotificationEventMessage(
        sender=sender,
        topic="fieldops.notification.events",
        message_type=MessageType.EVENT,
        payload={
            "event_type": "NOTIFICATION_QUEUED",
            "event_id": "evt_schema_notif_01",
            "job_id": "job_101",
            "tenant_id": "tenant-1",
            "schema_version": 1,
        },
    )

    assert msg.topic == "fieldops.notification.events"
    assert msg.payload["event_id"] == "evt_schema_notif_01"

