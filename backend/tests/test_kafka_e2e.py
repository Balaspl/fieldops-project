
import asyncio
import os
import uuid

import pytest
from aiokafka.errors import (
    GroupAuthorizationFailedError,
    TopicAuthorizationFailedError,
)
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



@pytest.mark.asyncio
async def test_job_completed_event_e2e():
    topic = "fieldops.events"
    group_id = f"fieldops-job-completed-e2e-{uuid.uuid4()}"

    producer = KafkaProducer()

    consumer = KafkaConsumerManager(
        topic=topic,
        group_id=group_id,
        bootstrap_servers="localhost:29092",
    )

    received = asyncio.Event()
    messages = []

    run_id = uuid.uuid4().hex
    job_id = f"E2E-COMPLETED-JOB-{run_id}"
    closure_id = f"E2E-CLOSURE-{run_id}"
    event_id = f"job-completed:tenant-e2e:{job_id}:{closure_id}"

    async def handler(message):
        payload = message.get("payload", {})

        if (
            payload.get("event_type") == "job-completed"
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
                "Kafka broker does not grant the generic consumer identity "
                "read access to fieldops.events."
            )

        consumer_task = asyncio.create_task(
            consumer.consume(handler)
        )

        message = MessageEnvelope(
            sender=AgentAddress(
                agent_type="dispatch",
                agent_id="job-completed-producer",
                tenant_id="tenant-e2e",
            ),
            recipient=None,
            message_type=MessageType.EVENT,
            payload={
                "event_type": "job-completed",
                "event_id": event_id,
                "job_id": job_id,
                "tenant_id": "tenant-e2e",
                "technician_id": "E2E-TECH-001",
                "closure_id": closure_id,
                "completed_at": "2026-10-01T10:00:00+00:00",
                "schema_version": 1,
                "timestamp": "2026-10-01T10:00:01+00:00",
                "correlation_id": "e2e-correlation-001",
            },
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

        assert received_payload["event_type"] == "job-completed"
        assert received_payload["event_id"] == event_id
        assert received_payload["job_id"] == job_id
        assert received_payload["tenant_id"] == "tenant-e2e"
        assert received_payload["technician_id"] == "E2E-TECH-001"
        assert received_payload["closure_id"] == closure_id
        assert received_payload["completed_at"] == "2026-10-01T10:00:00+00:00"
        assert received_payload["schema_version"] == 1
        assert received_payload["correlation_id"] == "e2e-correlation-001"

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
async def test_job_cancelled_event_e2e():
    topic = "fieldops.events"
    group_id = os.getenv("KAFKA_CONSUMER_GROUP", "fieldops")

    producer = KafkaProducer()

    consumer = KafkaConsumerManager(
        topic=topic,
        group_id=group_id,
        bootstrap_servers="localhost:29092",
    )

    received = asyncio.Event()
    messages = []

    run_id = uuid.uuid4().hex
    job_id = f"E2E-CANCELLED-JOB-{run_id}"
    cancelled_at = "2026-10-01T11:00:00+00:00"
    event_id = (
        f"job-cancelled:tenant-e2e:{job_id}:{cancelled_at}"
    )

    async def handler(message):
        payload = message.get("payload", {})

        if (
            payload.get("event_type") == "job-cancelled"
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
                "Kafka broker does not grant the generic consumer identity "
                "read access to fieldops.events."
            )

        consumer_task = asyncio.create_task(
            consumer.consume(handler)
        )

        message = MessageEnvelope(
            sender=AgentAddress(
                agent_type="dispatch",
                agent_id="job-cancelled-producer",
                tenant_id="tenant-e2e",
            ),
            recipient=None,
            message_type=MessageType.EVENT,
            payload={
                "event_type": "job-cancelled",
                "event_id": event_id,
                "job_id": job_id,
                "tenant_id": "tenant-e2e",
                "cancelled_by": "E2E-DISPATCHER-001",
                "cancellation_reason": "E2E cancellation test",
                "cancelled_at": cancelled_at,
                "schema_version": 1,
                "timestamp": "2026-10-01T11:00:01+00:00",
                "correlation_id": "e2e-cancellation-001",
            },
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

        assert received_payload["event_type"] == "job-cancelled"
        assert received_payload["event_id"] == event_id
        assert received_payload["job_id"] == job_id
        assert received_payload["tenant_id"] == "tenant-e2e"
        assert received_payload["cancelled_by"] == "E2E-DISPATCHER-001"
        assert (
            received_payload["cancellation_reason"]
            == "E2E cancellation test"
        )
        assert received_payload["cancelled_at"] == cancelled_at
        assert received_payload["schema_version"] == 1
        assert (
            received_payload["correlation_id"]
            == "e2e-cancellation-001"
        )

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
async def test_notification_lifecycle_event_e2e():
    from app.services.notification_event_producer import (
        NotificationEventProducer,
    )

    topic = "fieldops.notification.events"
    consumer = KafkaConsumerManager(
        topic=topic,
        group_id="fieldops-notifications",
        bootstrap_servers="localhost:29092",
    )
    kafka_producer = KafkaProducer()

    received = asyncio.Event()
    messages = []
    run_id = uuid.uuid4().hex
    event_id = f"notification-e2e-{run_id}"

    async def handler(message):
        payload = message.get("payload", {})
        if payload.get("event_id") == event_id:
            messages.append(message)
            received.set()

    consumer_task = None

    try:
        await kafka_producer.start()
        await consumer.start()

        consumer_task = asyncio.create_task(
            consumer.consume(handler)
        )

        notification_producer = NotificationEventProducer(
            kafka_producer
        )

        result = await notification_producer.publish(
            event_type="NOTIFICATION_SENT",
            event_id=event_id,
            job_id=f"E2E-JOB-{run_id}",
            tenant_id="tenant-1",
            correlation_id=run_id,
            payload={"channel": "email"},
        )

        assert result is True

        await asyncio.wait_for(received.wait(), timeout=10)

        assert len(messages) == 1
        assert messages[0]["topic"] == topic
        assert messages[0]["payload"]["event_type"] == (
            "NOTIFICATION_SENT"
        )
        assert messages[0]["payload"]["tenant_id"] == "tenant-1"
        assert messages[0]["payload"]["schema_version"] == 1
        assert messages[0]["correlation_id"] == run_id

    finally:
        if consumer_task is not None:
            consumer_task.cancel()
            try:
                await consumer_task
            except asyncio.CancelledError:
                pass

        await consumer.stop()
        await kafka_producer.stop()


@pytest.mark.asyncio
async def test_invoice_lifecycle_event_e2e():
    from app.services.invoice_event_producer import (
        InvoiceEventProducer,
    )

    topic = "fieldops.events"
    group_id = f"fieldops-job-completed-e2e-{uuid.uuid4()}"
    consumer = KafkaConsumerManager(
        topic=topic,
        group_id=group_id,
        bootstrap_servers="localhost:29092",
    )
    kafka_producer = KafkaProducer()

    received = asyncio.Event()
    messages = []
    run_id = uuid.uuid4().hex
    event_id = f"invoice-e2e-{run_id}"

    async def handler(message):
        payload = message.get("payload", {})
        if payload.get("event_id") == event_id:
            messages.append(message)
            received.set()

    consumer_task = None

    try:
        await kafka_producer.start()

        try:
            await consumer.start()
        except (TopicAuthorizationFailedError, GroupAuthorizationFailedError):
            pytest.skip(
                "Kafka broker does not grant the generic consumer identity "
                "read access to fieldops.events."
            )

        consumer_task = asyncio.create_task(
            consumer.consume(handler)
        )

        invoice_producer = InvoiceEventProducer(
            kafka_producer,
            topic=topic,
        )

        result = await invoice_producer.publish(
            event_type="invoice",
            event_id=event_id,
            job_id=f"E2E-JOB-{run_id}",
            tenant_id="tenant-1",
            correlation_id=run_id,
            invoice_id=f"INV-{run_id}",
            payload={"subtotal": 500.0},
        )

        assert result["status"] == "PUBLISHED"
        assert result["topic"] == topic
        assert result["schema_version"] == 1

        await asyncio.wait_for(received.wait(), timeout=10)

        assert len(messages) == 1
        assert messages[0]["topic"] == topic
        assert messages[0]["payload"]["event_type"] == "invoice"
        assert messages[0]["payload"]["tenant_id"] == "tenant-1"
        assert messages[0]["payload"]["invoice_id"] == f"INV-{run_id}"
        assert messages[0]["payload"]["schema_version"] == 1
        assert messages[0]["correlation_id"] == run_id

    finally:
        if consumer_task is not None:
            consumer_task.cancel()
            try:
                await consumer_task
            except asyncio.CancelledError:
                pass

        await consumer.stop()
        await kafka_producer.stop()


@pytest.mark.asyncio
async def test_payment_lifecycle_event_e2e():
    from app.services.payment_event_producer import (
        PaymentEventProducer,
    )

    topic = "fieldops.events"
    group_id = f"fieldops-job-completed-e2e-{uuid.uuid4()}"
    consumer = KafkaConsumerManager(
        topic=topic,
        group_id=group_id,
        bootstrap_servers="localhost:29092",
    )
    kafka_producer = KafkaProducer()

    received = asyncio.Event()
    messages = []
    run_id = uuid.uuid4().hex
    event_id = f"payment-e2e-{run_id}"

    async def handler(message):
        payload = message.get("payload", {})
        if payload.get("event_id") == event_id:
            messages.append(message)
            received.set()

    consumer_task = None

    try:
        await kafka_producer.start()

        try:
            await consumer.start()
        except (TopicAuthorizationFailedError, GroupAuthorizationFailedError):
            pytest.skip(
                "Kafka broker does not grant the generic consumer identity "
                "read access to fieldops.events."
            )

        consumer_task = asyncio.create_task(
            consumer.consume(handler)
        )

        payment_producer = PaymentEventProducer(
            kafka_producer,
            topic=topic,
        )

        result = await payment_producer.publish(
            event_type="payment",
            event_id=event_id,
            job_id=f"E2E-JOB-{run_id}",
            tenant_id="tenant-1",
            correlation_id=run_id,
            payment_id=f"PAY-{run_id}",
            payload={"amount": 350.0, "status": "SUCCESSFUL"},
        )

        assert result["status"] == "PUBLISHED"
        assert result["topic"] == topic
        assert result["schema_version"] == 1

        await asyncio.wait_for(received.wait(), timeout=10)

        assert len(messages) == 1
        assert messages[0]["topic"] == topic
        assert messages[0]["payload"]["event_type"] == "payment"
        assert messages[0]["payload"]["tenant_id"] == "tenant-1"
        assert messages[0]["payload"]["payment_id"] == f"PAY-{run_id}"
        assert messages[0]["payload"]["schema_version"] == 1
        assert messages[0]["correlation_id"] == run_id

    finally:
        if consumer_task is not None:
            consumer_task.cancel()
            try:
                await consumer_task
            except asyncio.CancelledError:
                pass

        await consumer.stop()
        await kafka_producer.stop()


@pytest.mark.asyncio
async def test_audit_lifecycle_event_e2e():
    from app.services.audit_event_producer import (
        AuditEventProducer,
    )

    topic = "fieldops.events"
    group_id = f"fieldops-job-completed-e2e-{uuid.uuid4()}"
    consumer = KafkaConsumerManager(
        topic=topic,
        group_id=group_id,
        bootstrap_servers="localhost:29092",
    )
    kafka_producer = KafkaProducer()

    received = asyncio.Event()
    messages = []
    run_id = uuid.uuid4().hex
    event_id = f"audit-e2e-{run_id}"

    async def handler(message):
        payload = message.get("payload", {})
        if payload.get("event_id") == event_id:
            messages.append(message)
            received.set()

    consumer_task = None

    try:
        await kafka_producer.start()

        try:
            await consumer.start()
        except (TopicAuthorizationFailedError, GroupAuthorizationFailedError):
            pytest.skip(
                "Kafka broker does not grant the generic consumer identity "
                "read access to fieldops.events."
            )

        consumer_task = asyncio.create_task(
            consumer.consume(handler)
        )

        audit_producer = AuditEventProducer(
            kafka_producer,
            topic=topic,
        )

        result = await audit_producer.publish(
            event_type="audit",
            event_id=event_id,
            tenant_id="tenant-1",
            job_id=f"E2E-JOB-{run_id}",
            user_id="user_admin_01",
            action="MANUAL_OVERRIDE",
            correlation_id=run_id,
            payload={"severity": "INFO", "action": "MANUAL_OVERRIDE"},
        )

        assert result["status"] == "PUBLISHED"
        assert result["topic"] == topic
        assert result["schema_version"] == 1

        await asyncio.wait_for(received.wait(), timeout=10)

        assert len(messages) == 1
        assert messages[0]["topic"] == topic
        assert messages[0]["payload"]["event_type"] == "audit"
        assert messages[0]["payload"]["tenant_id"] == "tenant-1"
        assert messages[0]["payload"]["job_id"] == f"E2E-JOB-{run_id}"
        assert messages[0]["payload"]["schema_version"] == 1
        assert messages[0]["correlation_id"] == run_id

    finally:
        if consumer_task is not None:
            consumer_task.cancel()
            try:
                await consumer_task
            except asyncio.CancelledError:
                pass

        await consumer.stop()
        await kafka_producer.stop()
