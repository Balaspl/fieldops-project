import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from aiokafka.errors import KafkaError

from app.services.kafka.producer import KafkaProducer


def create_message():
    from app.services.ai.FieldOpsAI.schemas.agent_messages import (
        AgentAddress,
        MessageEnvelope,
        MessageType,
    )

    return MessageEnvelope(
        sender=AgentAddress(
            agent_type="planning",
            agent_id="planner-01",
            tenant_id="tenant-001",
        ),
        recipient=None,
        message_type=MessageType.EVENT,
        payload={
            "job_id": "JOB-1001",
            "status": "ASSIGNED",
        },
        correlation_id="correlation-123",
        topic="fieldops.events",
    )


@pytest.mark.asyncio
async def test_start_creates_kafka_producer(monkeypatch):
    mock_producer = AsyncMock()

    monkeypatch.setattr(
        "app.services.kafka.producer.AIOKafkaProducer",
        lambda **kwargs: mock_producer,
    )

    producer = KafkaProducer()

    await producer.start()

    mock_producer.start.assert_awaited_once()
    assert producer._producer is mock_producer


@pytest.mark.asyncio
async def test_start_is_idempotent(monkeypatch):
    mock_producer = AsyncMock()

    monkeypatch.setattr(
        "app.services.kafka.producer.AIOKafkaProducer",
        lambda **kwargs: mock_producer,
    )

    producer = KafkaProducer()

    await producer.start()
    await producer.start()

    mock_producer.start.assert_awaited_once()


@pytest.mark.asyncio
async def test_stop_stops_producer(monkeypatch):
    mock_producer = AsyncMock()

    monkeypatch.setattr(
        "app.services.kafka.producer.AIOKafkaProducer",
        lambda **kwargs: mock_producer,
    )

    producer = KafkaProducer()

    await producer.start()
    await producer.stop()

    mock_producer.stop.assert_awaited_once()
    assert producer._producer is None


@pytest.mark.asyncio
async def test_publish_success(monkeypatch):
    mock_producer = AsyncMock()
    mock_producer.send_and_wait.return_value = None

    monkeypatch.setattr(
        "app.services.kafka.producer.AIOKafkaProducer",
        lambda **kwargs: mock_producer,
    )

    producer = KafkaProducer()
    await producer.start()

    message = create_message()

    result = await producer.publish(message)

    assert result is True

    mock_producer.send_and_wait.assert_awaited_once()

    topic, payload = mock_producer.send_and_wait.call_args.args

    assert topic == "fieldops.events"

    decoded = json.loads(payload.decode("utf-8"))

    assert decoded["correlation_id"] == "correlation-123"
    assert decoded["payload"]["job_id"] == "JOB-1001"


@pytest.mark.asyncio
async def test_publish_uses_explicit_topic(monkeypatch):
    mock_producer = AsyncMock()

    monkeypatch.setattr(
        "app.services.kafka.producer.AIOKafkaProducer",
        lambda **kwargs: mock_producer,
    )

    producer = KafkaProducer()
    await producer.start()

    message = create_message()

    result = await producer.publish(
        message,
        topic="fieldops.custom",
    )

    assert result is True

    topic = mock_producer.send_and_wait.call_args.args[0]

    assert topic == "fieldops.custom"


@pytest.mark.asyncio
async def test_publish_requires_started_producer():
    producer = KafkaProducer()

    message = create_message()

    with pytest.raises(RuntimeError, match="not started"):
        await producer.publish(message)


@pytest.mark.asyncio
async def test_publish_handles_kafka_error(monkeypatch):
    mock_producer = AsyncMock()

    mock_producer.send_and_wait.side_effect = KafkaError(
        "Kafka unavailable"
    )

    monkeypatch.setattr(
        "app.services.kafka.producer.AIOKafkaProducer",
        lambda **kwargs: mock_producer,
    )

    producer = KafkaProducer()
    await producer.start()

    message = create_message()

    result = await producer.publish(message)

    assert result is False


@pytest.mark.asyncio
async def test_start_failure_resets_producer(monkeypatch):
    mock_producer = AsyncMock()
    mock_producer.start.side_effect = KafkaError(
        "Kafka unavailable"
    )

    monkeypatch.setattr(
        "app.services.kafka.producer.AIOKafkaProducer",
        lambda **kwargs: mock_producer,
    )

    producer = KafkaProducer()

    with pytest.raises(KafkaError):
        await producer.start()

    assert producer._producer is None
    
@pytest.mark.asyncio
async def test_stop_when_producer_is_none():
    producer = KafkaProducer()
    producer._producer = None

    await producer.stop()

    assert producer._producer is None


@pytest.mark.asyncio
async def test_stop_handles_producer_failure():
    producer = KafkaProducer()

    class FailingProducer:
        async def stop(self):
            raise RuntimeError("stop failed")

    producer._producer = FailingProducer()

    await producer.stop()

    assert producer._producer is None