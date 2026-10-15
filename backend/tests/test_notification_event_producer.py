import asyncio

import pytest

from app.services.notification_event_producer import NotificationEventProducer


class FakeKafkaProducer:
    def __init__(self):
        self.events = []

    async def publish(self, event):
        self.events.append(event)
        return True


@pytest.mark.parametrize(
    "event_type",
    [
        "NOTIFICATION_QUEUED",
        "NOTIFICATION_SENT",
        "NOTIFICATION_FAILED",
        "NOTIFICATION_RETRIED",
    ],
)
def test_notification_event_producer_supports_lifecycle_events(event_type):
    kafka = FakeKafkaProducer()
    producer = NotificationEventProducer(kafka)

    result = asyncio.run(
        producer.publish(
            event_type=event_type,
            event_id=f"evt_{event_type.lower()}",
            job_id="job_001",
            tenant_id="tenant-1",
            correlation_id="corr-001",
            payload={"channel": "email"},
        )
    )

    assert result is True
    assert len(kafka.events) == 1

    event = kafka.events[0]

    assert event.topic == "fieldops.notification.events"
    assert event.payload["event_type"] == event_type
    assert event.payload["event_id"] == f"evt_{event_type.lower()}"
    assert event.payload["job_id"] == "job_001"
    assert event.payload["tenant_id"] == "tenant-1"
    assert event.payload["schema_version"] == 1
    assert event.correlation_id == "corr-001"
