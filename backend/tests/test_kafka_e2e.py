
import asyncio
import os
import uuid

import pytest
from aiokafka.errors import TopicAuthorizationFailedError
from dotenv import load_dotenv

from app.services.kafka.consumer import KafkaConsumerManager
from app.services.kafka.producer import KafkaProducer
from app.services.ai.FieldOpsAI.schemas.agent_messages import (
    AgentAddress,
    MessageEnvelope,
    MessageType,
)

load_dotenv()


@pytest.mark.asyncio
async def test_kafka_producer_to_consumer_e2e():
    topic = "fieldops.audit.events"
    group_id = f"fieldops-audit-e2e-{uuid.uuid4()}"

    producer = KafkaProducer()

    consumer = KafkaConsumerManager(
        topic=topic,
        group_id=group_id,
        bootstrap_servers="localhost:29092",
    )

    received = asyncio.Event()
    messages = []

    async def handler(message):
        if not received.is_set():
            messages.append(message)
            received.set()

    consumer_task = None

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

    finally:
        if consumer_task is not None:
            consumer_task.cancel()

            try:
                await consumer_task
            except asyncio.CancelledError:
                pass

        await consumer.stop()
        await producer.stop()


@pytest.mark.asyncio
async def test_kafka_unauthorized_consumer_group_rejected():
    consumer = KafkaConsumerManager(
        topic="fieldops.job.events",
        group_id="fieldops-gps",
        bootstrap_servers="localhost:29092",
    )

    try:
        try:
            await consumer.start()
        except Exception:
            # Authorization is enforced by the broker.
            return

        pytest.skip(
            "Kafka broker does not have authorization enabled; "
            "unauthorized consumer-group rejection cannot be tested."
        )
    finally:
        await consumer.stop()


@pytest.mark.asyncio
async def test_job_assigned_event_e2e():
    topic = "fieldops.job.events"

    group_id = (
        f"fieldops-job-assigned-e2e-{uuid.uuid4()}"
    )

    # Make sure the E2E test uses the dispatch Kafka identity.
    #
    # KafkaConsumerManager selects credentials for
    # fieldops.job.events from:
    #
    # KAFKA_DISPATCH_USERNAME
    # KAFKA_DISPATCH_PASSWORD
    #
    dispatch_username = os.getenv(
        "KAFKA_DISPATCH_USERNAME"
    )
    dispatch_password = os.getenv(
        "KAFKA_DISPATCH_PASSWORD"
    )

    assert dispatch_username, (
        "KAFKA_DISPATCH_USERNAME is not configured"
    )

    assert dispatch_password, (
        "KAFKA_DISPATCH_PASSWORD is not configured"
    )

    assert dispatch_username == "fieldops-dispatch", (
        "fieldops.job.events E2E test must use "
        "fieldops-dispatch credentials"
    )

    producer = KafkaProducer()

    consumer = KafkaConsumerManager(
        topic=topic,
        group_id=group_id,
        bootstrap_servers="localhost:29092",
    )

    received = asyncio.Event()
    messages = []

    run_id = uuid.uuid4().hex
    job_id = f"E2E-JOB-{run_id}"
    event_id = f"job-assigned:tenant-1:{job_id}"

    async def handler(message):
        payload = message.get("payload", {})

        if (
            payload.get("event_type") == "job-assigned"
            and payload.get("event_id") == event_id
        ):
            messages.append(message)
            received.set()

    consumer_task = None

    try:
        await producer.start()
        try:
            await consumer.start()
        except TopicAuthorizationFailedError:
            pytest.skip(
                "Kafka broker does not grant the dispatch identity "
                "read access to fieldops.job.events."
            )

        consumer_task = asyncio.create_task(
            consumer.consume(handler)
        )

        message = MessageEnvelope(
            sender=AgentAddress(
                agent_type="dispatch",
                agent_id="job-assigned-producer",
                tenant_id="tenant-1",
            ),
            recipient=None,
            message_type=MessageType.EVENT,
            payload={
                "event_type": "job-assigned",
                "event_id": event_id,
                "job_id": job_id,
                "tenant_id": "tenant-1",
                "technician_id": "E2E-TECH-001",
                "schema_version": 1,
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

        received_payload = messages[0]["payload"]

        assert received_payload["event_type"] == "job-assigned"
        assert received_payload["event_id"] == event_id
        assert received_payload["job_id"] == job_id
        assert received_payload["tenant_id"] == "tenant-1"
        assert received_payload["technician_id"] == "E2E-TECH-001"
        assert received_payload["schema_version"] == 1

    finally:
        if consumer_task is not None:
            consumer_task.cancel()

            try:
                await consumer_task
            except asyncio.CancelledError:
                pass

        await consumer.stop()
        await producer.stop()

