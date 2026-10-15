import asyncio
from unittest.mock import MagicMock, patch

import pytest

from app.services.payment_event_producer import PaymentEventProducer, PublishReceipt
from app.tasks import _publish_payment_event_once


class FakeKafkaProducer:
    def __init__(self, should_succeed=True, should_raise=False):
        self.events = []
        self.should_succeed = should_succeed
        self.should_raise = should_raise

    async def publish(self, event, topic=None):
        if self.should_raise:
            raise RuntimeError("Kafka connection error")
        if not self.should_succeed:
            return False
        self.events.append((event, topic))
        return True


@pytest.mark.parametrize(
    "event_type",
    [
        "payment",
        "PAYMENT",
        "PAYMENT_INITIATED",
        "PAYMENT_SUCCESS",
        "PAYMENT_SUCCESSFUL",
        "PAYMENT_FAILED",
        "PAYMENT_PENDING",
        "PAYMENT_REFUNDED",
        "PAYMENT_REFUND",
    ],
)
def test_payment_event_producer_primary_success_path(event_type):
    kafka = FakeKafkaProducer()
    producer = PaymentEventProducer(kafka)

    event_id = "evt_01JEXAMPLE"
    job_id = "job_101"
    tenant_id = "tenant-1"
    correlation_id = "corr-101"

    result = asyncio.run(
        producer.publish(
            event_type=event_type,
            event_id=event_id,
            job_id=job_id,
            tenant_id=tenant_id,
            payment_id="pay_500",
            correlation_id=correlation_id,
            payload={"amount": 350.0, "currency": "USD"},
        )
    )

    # 1. Expected output contract
    assert result["status"] == "PUBLISHED"
    assert result["event_type"] == event_type
    assert result["event_id"] == event_id
    assert result["topic"] == "fieldops.events"
    assert result["schema_version"] == 1

    # 2. Boolean and dictionary compatibility
    assert bool(result) is True
    assert result == True
    assert isinstance(result, dict)

    # 3. Verify event placed on mock Kafka
    assert len(kafka.events) == 1
    event, published_topic = kafka.events[0]
    assert published_topic == "fieldops.events"
    assert event.topic == "fieldops.events"
    assert event.correlation_id == correlation_id
    assert event.payload["event_type"] == event_type
    assert event.payload["event_id"] == event_id
    assert event.payload["job_id"] == job_id
    assert event.payload["tenant_id"] == tenant_id
    assert event.payload["payment_id"] == "pay_500"
    assert event.payload["amount"] == 350.0
    assert event.payload["schema_version"] == 1


def test_payment_event_producer_custom_topic():
    kafka = FakeKafkaProducer()
    producer = PaymentEventProducer(kafka, topic="fieldops.payment.events")

    result = asyncio.run(
        producer.publish(
            event_type="PAYMENT_SUCCESS",
            event_id="evt_paid_123",
            job_id="job_002",
            tenant_id="tenant-1",
            payment_id="pay_002",
        )
    )

    assert result["status"] == "PUBLISHED"
    assert result["topic"] == "fieldops.payment.events"
    assert len(kafka.events) == 1
    event, published_topic = kafka.events[0]
    assert published_topic == "fieldops.payment.events"
    assert event.topic == "fieldops.payment.events"


def test_payment_event_producer_rejects_unauthorized_topic():
    kafka = FakeKafkaProducer()
    producer = PaymentEventProducer(kafka, topic="fieldops.unauthorized.topic")

    with pytest.raises(ValueError, match="Payment events must use one of"):
        asyncio.run(
            producer.publish(
                event_type="payment",
                event_id="evt_01",
                job_id="job_01",
                tenant_id="tenant-1",
            )
        )


def test_payment_event_producer_rejects_invalid_event_type():
    kafka = FakeKafkaProducer()
    producer = PaymentEventProducer(kafka)

    with pytest.raises(ValueError, match="valid payment event_type"):
        asyncio.run(
            producer.publish(
                event_type="INVALID_PAYMENT_EVENT",
                event_id="evt_01",
                job_id="job_01",
                tenant_id="tenant-1",
            )
        )


@pytest.mark.parametrize(
    "forbidden_payload",
    [
        {"password": "secret-password"},
        {"secret": "api-secret-key"},
        {"token": "auth-bearer-token"},
    ],
)
def test_payment_event_producer_rejects_forbidden_secrets(forbidden_payload):
    kafka = FakeKafkaProducer()
    producer = PaymentEventProducer(kafka)

    with pytest.raises(ValueError, match="Forbidden sensitive key"):
        asyncio.run(
            producer.publish(
                event_type="payment",
                event_id="evt_01",
                job_id="job_01",
                tenant_id="tenant-1",
                payload=forbidden_payload,
            )
        )


def test_payment_event_producer_handles_kafka_failure_safely():
    kafka = FakeKafkaProducer(should_succeed=False)
    producer = PaymentEventProducer(kafka)

    result = asyncio.run(
        producer.publish(
            event_type="payment",
            event_id="evt_fail_01",
            job_id="job_01",
            tenant_id="tenant-1",
        )
    )

    assert result["status"] == "FAILED"
    assert bool(result) is False
    assert result == False


def test_payment_event_producer_handles_kafka_exception_safely():
    kafka = FakeKafkaProducer(should_raise=True)
    producer = PaymentEventProducer(kafka)

    result = asyncio.run(
        producer.publish(
            event_type="payment",
            event_id="evt_fail_02",
            job_id="job_01",
            tenant_id="tenant-1",
        )
    )

    assert result["status"] == "FAILED"
    assert bool(result) is False
    assert result == False


def test_publish_payment_event_once_idempotency():
    redis_store = {}

    class FakeRedis:
        def get(self, key):
            return redis_store.get(key)

        def set(self, key, value, ex=None):
            redis_store[key] = value
            return True

    fake_redis = FakeRedis()
    event_id = "evt_idem_201"

    with patch(
        "app.tasks._publish_payment_lifecycle_event",
        return_value={
            "status": "PUBLISHED",
            "event_type": "PAYMENT_SUCCESS",
            "event_id": event_id,
            "topic": "fieldops.events",
            "schema_version": 1,
        },
    ) as mock_publish:
        # First call publishes to Kafka and sets idempotency marker in Redis
        res1 = _publish_payment_event_once(
            redis=fake_redis,
            event_type="PAYMENT_SUCCESS",
            event_id=event_id,
            job_id="job_201",
            tenant_id="tenant-1",
            payment_id="pay_201",
        )
        assert res1["status"] == "PUBLISHED"
        assert mock_publish.call_count == 1
        assert redis_store.get(f"payment:event_published:{event_id}") == "1"

        # Second call hits idempotency marker and does NOT re-publish
        res2 = _publish_payment_event_once(
            redis=fake_redis,
            event_type="PAYMENT_SUCCESS",
            event_id=event_id,
            job_id="job_201",
            tenant_id="tenant-1",
            payment_id="pay_201",
        )
        assert res2["status"] == "PUBLISHED"
        assert res2.get("idempotent_duplicate") is True
        assert mock_publish.call_count == 1


def test_publish_payment_event_once_retries_after_failure():
    redis_store = {}

    class FakeRedis:
        def get(self, key):
            return redis_store.get(key)

        def set(self, key, value, ex=None):
            redis_store[key] = value
            return True

    fake_redis = FakeRedis()
    event_id = "evt_retry_201"

    with patch(
        "app.tasks._publish_payment_lifecycle_event",
        side_effect=[
            {"status": "FAILED", "event_id": event_id},
            {
                "status": "PUBLISHED",
                "event_type": "PAYMENT_SUCCESS",
                "event_id": event_id,
                "topic": "fieldops.events",
                "schema_version": 1,
            },
        ],
    ) as mock_publish:
        first = _publish_payment_event_once(
            redis=fake_redis,
            event_type="PAYMENT_SUCCESS",
            event_id=event_id,
            job_id="job_201",
            tenant_id="tenant-1",
        )

        assert first["status"] == "FAILED"
        assert fake_redis.get(f"payment:event_published:{event_id}") is None

        second = _publish_payment_event_once(
            redis=fake_redis,
            event_type="PAYMENT_SUCCESS",
            event_id=event_id,
            job_id="job_201",
            tenant_id="tenant-1",
        )

        assert second["status"] == "PUBLISHED"
        assert mock_publish.call_count == 2
        assert fake_redis.get(f"payment:event_published:{event_id}") == "1"

