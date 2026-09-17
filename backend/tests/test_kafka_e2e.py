import asyncio
import uuid

import pytest

from app.services.kafka.consumer import KafkaConsumerManager
from app.services.kafka.producer import KafkaProducer
from app.services.ai.FieldOpsAI.schemas.agent_messages import (
    AgentAddress,
    MessageEnvelope,
    MessageType,
)


@pytest.mark.asyncio
async def test_kafka_producer_to_consumer_e2e():
    topic = "fieldops.audit.events"
    group_id = f"fieldops-e2e-{uuid.uuid4()}"

    producer = KafkaProducer()

    consumer = KafkaConsumerManager(
        topic=topic,
        group_id=group_id,
        bootstrap_servers="localhost:29092",
    )

    received = asyncio.Event()
    messages = []

    async def handler(message):
        messages.append(message)
        received.set()

    try:
        await producer.start()
        await consumer.start()

        consumer_task = asyncio.create_task(
            consumer.consume(handler)
        )

        message = MessageEnvelope(
            sender=AgentAddress(
                agent_type="planning",
                agent_id="e2e-test",
                tenant_id="tenant-001",
            ),
            recipient=None,
            message_type=MessageType.EVENT,
            payload={
                "test": "kafka-e2e",
                "job_id": "E2E-TEST-001",
            },
            correlation_id=str(uuid.uuid4()),
            topic=topic,
        )

        result = await producer.publish(message)

        assert result is True

        await asyncio.wait_for(
            received.wait(),
            timeout=10,
        )

        assert len(messages) == 1
        assert messages[0]["payload"]["test"] == "kafka-e2e"
        assert messages[0]["payload"]["job_id"] == "E2E-TEST-001"

        consumer_task.cancel()

        try:
            await consumer_task
        except asyncio.CancelledError:
            pass

    finally:
        await consumer.stop()
        await producer.stop()