from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.services.gps_tracking_consumer import (
    ConsumeReceipt,
    GPSTrackingConsumer,
    GPSConsumer,
    GPSLocationConsumer,
)
from app.services.ai.FieldOpsAI.schemas.agent_messages import (
    AgentAddress,
    GPSLocationEventMessage,
    MessageType,
)
from app.tasks import (
    _process_gps_tracking_event_once,
    process_gps_tracking_event_task,
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


@pytest.mark.parametrize(
    "event_type",
    [
        "GPS-location",
        "gps-location",
        "location",
    ],
)
@pytest.mark.asyncio
async def test_gps_tracking_consumer_primary_success_path(
    event_type,
    fake_redis,
    fake_consumer_manager,
):
    consumer = GPSTrackingConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )

    event_id = f"evt_gps_{event_type.lower()}_123"
    message_payload = {
        "event_type": event_type,
        "event_id": event_id,
        "technician_id": "tech_01",
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "latitude": 13.0827,
        "longitude": 80.2707,
        "accuracy": 5.0,
        "altitude": 10.0,
        "timestamp": "2026-10-16T12:00:00Z",
        "schema_version": 1,
    }

    with patch("app.services.gps_tracking_consumer.publish_gps_event") as mock_pub, \
         patch("app.tasks.update_eta_task.delay") as mock_eta:

        receipt = await consumer.process_event(message_payload, attempt=1)

        assert isinstance(receipt, ConsumeReceipt)
        assert receipt.is_success is True
        assert bool(receipt) is True
        assert receipt["status"] == "PROCESSED"
        assert receipt["consumer"] == "GPS_tracking"
        assert receipt["event_id"] == event_id
        assert receipt["attempt"] == 1

        mock_pub.assert_called_once()
        mock_eta.assert_called_once()
        assert fake_redis.get(f"gps:event_processed:{event_id}") == "1"


@pytest.mark.asyncio
async def test_gps_tracking_consumer_custom_topic(fake_redis, fake_consumer_manager):
    consumer = GPSTrackingConsumer(
        topic="fieldops.events",
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )

    payload = {
        "event_type": "GPS-location",
        "event_id": "evt_gps_custom_01",
        "technician_id": "tech_01",
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "latitude": 12.9716,
        "longitude": 77.5946,
        "schema_version": 1,
        "topic": "fieldops.events",
    }

    with patch("app.services.gps_tracking_consumer.publish_gps_event"), \
         patch("app.tasks.update_eta_task.delay"):
        receipt = await consumer.process_event(payload)
        assert receipt["status"] == "PROCESSED"
        assert receipt["consumer"] == "GPS_tracking"


@pytest.mark.asyncio
async def test_gps_tracking_consumer_rejects_unauthorized_topic(
    fake_redis,
    fake_consumer_manager,
):
    consumer = GPSTrackingConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )

    payload = {
        "event_type": "GPS-location",
        "event_id": "evt_unauth_01",
        "technician_id": "tech_01",
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "latitude": 12.0,
        "longitude": 77.0,
        "schema_version": 1,
        "topic": "unauthorized.topic",
    }

    receipt = await consumer.process_event(payload)
    assert receipt["status"] == "FAILED"
    assert "not authorized" in receipt["error"]


@pytest.mark.asyncio
async def test_gps_tracking_consumer_rejects_invalid_event_type(
    fake_redis,
    fake_consumer_manager,
):
    consumer = GPSTrackingConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )

    payload = {
        "event_type": "INVALID_GPS_EVENT",
        "event_id": "evt_invalid_01",
        "technician_id": "tech_01",
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "latitude": 12.0,
        "longitude": 77.0,
        "schema_version": 1,
    }

    receipt = await consumer.process_event(payload)
    assert receipt["status"] == "FAILED"
    assert "Invalid event_type" in receipt["error"]


@pytest.mark.parametrize(
    "missing_field",
    [
        "event_id",
        "technician_id",
        "job_id",
        "tenant_id",
        "latitude",
        "longitude",
        "schema_version",
    ],
)
@pytest.mark.asyncio
async def test_gps_tracking_consumer_rejects_missing_required_fields(
    missing_field,
    fake_redis,
    fake_consumer_manager,
):
    consumer = GPSTrackingConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )

    base_payload = {
        "event_type": "GPS-location",
        "event_id": "evt_missing_01",
        "technician_id": "tech_01",
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "latitude": 12.0,
        "longitude": 77.0,
        "schema_version": 1,
    }
    del base_payload[missing_field]

    receipt = await consumer.process_event(base_payload)
    assert receipt["status"] == "FAILED"
    assert missing_field in receipt["error"]


@pytest.mark.parametrize(
    ("lat", "lon", "expected_err"),
    [
        (95.0, 77.0, "Latitude must be between -90 and 90"),
        (-95.0, 77.0, "Latitude must be between -90 and 90"),
        (12.0, 185.0, "Longitude must be between -180 and 180"),
        (12.0, -185.0, "Longitude must be between -180 and 180"),
        ("invalid_lat", 77.0, "Latitude must be a numeric value"),
        (12.0, True, "Longitude must be a numeric value"),
    ],
)
@pytest.mark.asyncio
async def test_gps_tracking_consumer_validates_coordinate_bounds(
    lat,
    lon,
    expected_err,
    fake_redis,
    fake_consumer_manager,
):
    consumer = GPSTrackingConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )

    payload = {
        "event_type": "GPS-location",
        "event_id": "evt_bounds_01",
        "technician_id": "tech_01",
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "latitude": lat,
        "longitude": lon,
        "schema_version": 1,
    }

    receipt = await consumer.process_event(payload)
    assert receipt["status"] == "FAILED"
    assert expected_err in receipt["error"]


@pytest.mark.parametrize(
    "forbidden_payload",
    [
        {"password": "secret_password"},
        {"secret": "client_secret"},
        {"token": "auth_token_xyz"},
    ],
)
@pytest.mark.asyncio
async def test_gps_tracking_consumer_rejects_forbidden_secrets(
    forbidden_payload,
    fake_redis,
    fake_consumer_manager,
):
    consumer = GPSTrackingConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )

    payload = {
        "event_type": "GPS-location",
        "event_id": "evt_sec_01",
        "technician_id": "tech_01",
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "latitude": 12.0,
        "longitude": 77.0,
        "schema_version": 1,
        **forbidden_payload,
    }

    receipt = await consumer.process_event(payload)
    assert receipt["status"] == "FAILED"
    assert "forbidden" in receipt["error"]


@pytest.mark.asyncio
async def test_gps_tracking_consumer_protects_against_stale_updates(
    fake_redis,
    fake_consumer_manager,
):
    consumer = GPSTrackingConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )

    payload_new = {
        "event_type": "GPS-location",
        "event_id": "evt_gps_new",
        "technician_id": "tech_01",
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "latitude": 12.0,
        "longitude": 77.0,
        "timestamp": "2026-10-16T12:00:00Z",
        "schema_version": 1,
    }

    payload_stale = {
        "event_type": "GPS-location",
        "event_id": "evt_gps_old",
        "technician_id": "tech_01",
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "latitude": 11.0,
        "longitude": 76.0,
        "timestamp": "2026-10-16T11:50:00Z",
        "schema_version": 1,
    }

    with patch("app.services.gps_tracking_consumer.publish_gps_event") as mock_pub, \
         patch("app.tasks.update_eta_task.delay") as mock_eta:

        # 1. Process newer update
        res1 = await consumer.process_event(payload_new)
        assert res1["status"] == "PROCESSED"
        assert mock_pub.call_count == 1
        assert mock_eta.call_count == 1

        # 2. Process older update (out-of-order)
        res2 = await consumer.process_event(payload_stale)
        assert res2["status"] == "PROCESSED"
        assert res2.get("stale_update") is True
        # Domain services must NOT be called again for stale update
        assert mock_pub.call_count == 1
        assert mock_eta.call_count == 1


@pytest.mark.asyncio
async def test_gps_tracking_consumer_idempotency(fake_redis, fake_consumer_manager):
    consumer = GPSTrackingConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )

    payload = {
        "event_type": "GPS-location",
        "event_id": "evt_gps_idem_01",
        "technician_id": "tech_01",
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "latitude": 12.0,
        "longitude": 77.0,
        "schema_version": 1,
    }

    with patch("app.services.gps_tracking_consumer.publish_gps_event") as mock_pub:
        # First call
        res1 = await consumer.process_event(payload, attempt=1)
        assert res1["status"] == "PROCESSED"
        assert mock_pub.call_count == 1
        assert fake_redis.get("gps:event_processed:evt_gps_idem_01") == "1"

        # Second call hits idempotency key
        res2 = await consumer.process_event(payload, attempt=2)
        assert res2["status"] == "PROCESSED"
        assert res2.get("idempotent_duplicate") is True
        assert mock_pub.call_count == 1


@pytest.mark.asyncio
async def test_gps_tracking_consumer_retries_after_failure(
    fake_redis,
    fake_consumer_manager,
):
    consumer = GPSTrackingConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )

    payload = {
        "event_type": "GPS-location",
        "event_id": "evt_gps_retry_01",
        "technician_id": "tech_01",
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "latitude": 12.0,
        "longitude": 77.0,
        "schema_version": 1,
    }

    with patch("app.services.gps_tracking_consumer.publish_gps_event") as mock_pub:
        # Fail first attempt
        mock_pub.side_effect = RuntimeError("Network error")
        res1 = await consumer.process_event(payload, attempt=1)
        assert res1["status"] == "FAILED"
        assert fake_redis.get("gps:event_processed:evt_gps_retry_01") is None

        # Succeed second attempt
        mock_pub.side_effect = None
        res2 = await consumer.process_event(payload, attempt=2)
        assert res2["status"] == "PROCESSED"
        assert res2["attempt"] == 2
        assert fake_redis.get("gps:event_processed:evt_gps_retry_01") == "1"


def test_process_gps_tracking_event_task_and_once(fake_redis):
    payload = {
        "event_type": "GPS-location",
        "event_id": "evt_task_gps_01",
        "technician_id": "tech_01",
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "latitude": 12.0,
        "longitude": 77.0,
        "schema_version": 1,
    }

    with patch("app.services.gps_tracking_consumer.publish_gps_event"):
        # First call
        res1 = _process_gps_tracking_event_once(
            redis=fake_redis,
            event_payload=payload,
            attempt=1,
        )
        assert res1["status"] == "PROCESSED"
        assert res1["consumer"] == "GPS_tracking"
        assert fake_redis.get("gps:event_processed:evt_task_gps_01") == "1"

        # Duplicate call
        res2 = _process_gps_tracking_event_once(
            redis=fake_redis,
            event_payload=payload,
            attempt=2,
        )
        assert res2["status"] == "PROCESSED"
        assert res2.get("idempotent_duplicate") is True


@pytest.mark.asyncio
async def test_gps_tracking_consumer_context_manager(fake_consumer_manager):
    consumer = GPSTrackingConsumer(consumer_manager=fake_consumer_manager)

    async with consumer as c:
        assert c is consumer
        fake_consumer_manager.start.assert_awaited_once()

    fake_consumer_manager.stop.assert_awaited_once()


def test_gps_location_event_message_schema():
    sender = AgentAddress(
        agent_type="dispatch",
        agent_id="gps-producer-01",
        tenant_id="tenant-1",
    )

    msg = GPSLocationEventMessage(
        sender=sender,
        topic="fieldops.gps.events",
        message_type=MessageType.EVENT,
        payload={
            "event_type": "GPS-location",
            "event_id": "evt_schema_gps_01",
            "technician_id": "tech_01",
            "job_id": "job_777",
            "tenant_id": "tenant-1",
            "latitude": 12.9716,
            "longitude": 77.5946,
            "schema_version": 1,
        },
    )

    assert msg.topic == "fieldops.gps.events"
    assert msg.payload["event_type"] == "GPS-location"
    assert msg.payload["latitude"] == 12.9716
    assert msg.payload["longitude"] == 77.5946

    # Alias check
    assert GPSConsumer is GPSTrackingConsumer
    assert GPSLocationConsumer is GPSTrackingConsumer

