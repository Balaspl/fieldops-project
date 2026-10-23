
import asyncio
import os
import uuid

import pytest
from aiokafka.errors import (
    GroupAuthorizationFailedError,
    KafkaConnectionError,
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
    test_id = str(uuid.uuid4())

    producer = KafkaProducer()
    consumer = KafkaConsumerManager(
        topic=topic,
        group_id=group_id,
        bootstrap_servers="localhost:29092",
    )

    received = asyncio.Event()
    messages = []

    async def handler(message):
        # Ignore historical messages and unrelated events on the shared topic.
        if not isinstance(message, dict):
            return

        payload = message.get("payload")
        if not isinstance(payload, dict):
            return

        if (
            payload.get("test") == "kafka-e2e"
            and payload.get("test_id") == test_id
            and payload.get("job_id") == "E2E-TEST-001"
        ):
            messages.append(message)
            received.set()

    consumer_task = None

    try:
        await producer.start()
        await consumer.start()

        consumer_task = asyncio.create_task(consumer.consume(handler))

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
                "test_id": test_id,
                "job_id": "E2E-TEST-001",
            },
            correlation_id=test_id,
            topic=topic,
        )

        result = await producer.publish(message)
        assert result is True

        await asyncio.wait_for(received.wait(), timeout=10)

        assert len(messages) == 1
        received_payload = messages[0]["payload"]
        assert received_payload["test"] == "kafka-e2e"
        assert received_payload["test_id"] == test_id
        assert received_payload["job_id"] == "E2E-TEST-001"

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


@pytest.mark.asyncio
async def test_dispatch_consumer_lifecycle_e2e():
    from app.services.dispatch_consumer import DispatchConsumer

    topic = "fieldops.job.events"
    group_id = f"fieldops-job-assigned-e2e-{uuid.uuid4()}"

    consumer_manager = KafkaConsumerManager(
        topic=topic,
        group_id=group_id,
        bootstrap_servers="localhost:29092",
    )
    kafka_producer = KafkaProducer()

    processed_event = asyncio.Event()
    results = []
    run_id = uuid.uuid4().hex
    job_id = f"E2E-DISPATCH-JOB-{run_id}"
    event_id = f"job-assigned:tenant-e2e:{job_id}"

    consumer = DispatchConsumer(
        topic=topic,
        group_id=group_id,
        consumer_manager=consumer_manager,
    )

    async def handler(message):
        payload = message.get("payload", {})
        if payload.get("event_id") == event_id:
            receipt = await consumer.handle_message(message, attempt=1)
            results.append(receipt)
            processed_event.set()

    consumer_task = None

    try:
        try:
            await kafka_producer.start()
            await consumer_manager.start()
        except KafkaConnectionError:
            pytest.skip(
                "Kafka broker at localhost:29092 is not reachable. "
                "Start Docker / Kafka container to run live broker E2E test."
            )
        except (TopicAuthorizationFailedError, GroupAuthorizationFailedError):
            pytest.skip(
                "Kafka broker does not grant the dispatch identity "
                "read access to fieldops.job.events."
            )

        consumer_task = asyncio.create_task(
            consumer_manager.consume(handler)
        )

        message = MessageEnvelope(
            sender=AgentAddress(
                agent_type="dispatch",
                agent_id="job-assigned-producer",
                tenant_id="tenant-e2e",
            ),
            recipient=None,
            message_type=MessageType.EVENT,
            payload={
                "event_type": "job-assigned",
                "event_id": event_id,
                "job_id": job_id,
                "tenant_id": "tenant-e2e",
                "technician_id": "TECH-E2E-001",
                "old_status": "QUEUED",
                "new_status": "ASSIGNED",
                "schema_version": 1,
            },
            correlation_id=run_id,
            topic=topic,
        )

        published = await kafka_producer.publish(message)
        assert published is True

        await asyncio.wait_for(processed_event.wait(), timeout=10)

        assert len(results) == 1
        receipt = results[0]
        assert receipt["status"] == "PROCESSED"
        assert receipt["consumer"] == "dispatch"
        assert receipt["event_id"] == event_id
        assert receipt["attempt"] == 1

    finally:
        if consumer_task is not None:
            consumer_task.cancel()
            try:
                await consumer_task
            except asyncio.CancelledError:
                pass

        await consumer_manager.stop()
        await kafka_producer.stop()


@pytest.mark.asyncio
async def test_gps_tracking_consumer_lifecycle_e2e():
    from app.services.gps_tracking_consumer import GPSTrackingConsumer

    topic = "fieldops.gps.events"
    group_id = f"fieldops-gps-e2e-{uuid.uuid4()}"

    consumer_manager = KafkaConsumerManager(
        topic=topic,
        group_id=group_id,
        bootstrap_servers="localhost:29092",
    )
    kafka_producer = KafkaProducer()

    processed_event = asyncio.Event()
    results = []
    run_id = uuid.uuid4().hex
    job_id = f"E2E-GPS-JOB-{run_id}"
    event_id = f"evt_gps_e2e_{run_id}"

    consumer = GPSTrackingConsumer(
        topic=topic,
        group_id=group_id,
        consumer_manager=consumer_manager,
    )

    async def handler(message):
        payload = message.get("payload", {})
        if payload.get("event_id") == event_id:
            receipt = await consumer.handle_message(message, attempt=1)
            results.append(receipt)
            processed_event.set()

    consumer_task = None

    try:
        try:
            await kafka_producer.start()
            await consumer_manager.start()
        except KafkaConnectionError:
            pytest.skip(
                "Kafka broker at localhost:29092 is not reachable. "
                "Start Docker / Kafka container to run live broker E2E test."
            )
        except (TopicAuthorizationFailedError, GroupAuthorizationFailedError):
            pytest.skip(
                "Kafka broker does not grant the gps identity "
                "read access to fieldops.gps.events."
            )

        consumer_task = asyncio.create_task(
            consumer_manager.consume(handler)
        )

        message = MessageEnvelope(
            sender=AgentAddress(
                agent_type="dispatch",
                agent_id="gps-e2e-producer",
                tenant_id="tenant-e2e",
            ),
            recipient=None,
            message_type=MessageType.EVENT,
            payload={
                "event_type": "GPS-location",
                "event_id": event_id,
                "job_id": job_id,
                "tenant_id": "tenant-e2e",
                "technician_id": "TECH-GPS-001",
                "latitude": 13.0827,
                "longitude": 80.2707,
                "accuracy": 4.5,
                "altitude": 12.0,
                "timestamp": "2026-10-16T12:00:00Z",
                "schema_version": 1,
            },
            correlation_id=run_id,
            topic=topic,
        )

        published = await kafka_producer.publish(message)
        assert published is True

        await asyncio.wait_for(processed_event.wait(), timeout=10)

        assert len(results) == 1
        receipt = results[0]
        assert receipt["status"] == "PROCESSED"
        assert receipt["consumer"] == "GPS_tracking"
        assert receipt["event_id"] == event_id
        assert receipt["attempt"] == 1

    finally:
        if consumer_task is not None:
            consumer_task.cancel()
            try:
                await consumer_task
            except asyncio.CancelledError:
                pass

        await consumer_manager.stop()
        await kafka_producer.stop()


@pytest.mark.asyncio
async def test_notification_consumer_lifecycle_e2e():
    from app.services.notification_consumer import NotificationConsumer

    topic = "fieldops.notification.events"
    group_id = f"fieldops-notifications-e2e-{uuid.uuid4()}"

    consumer_manager = KafkaConsumerManager(
        topic=topic,
        group_id=group_id,
        bootstrap_servers="localhost:29092",
    )
    kafka_producer = KafkaProducer()

    processed_event = asyncio.Event()
    results = []
    run_id = uuid.uuid4().hex
    job_id = f"E2E-NOTIF-JOB-{run_id}"
    event_id = f"evt_notif_e2e_{run_id}"

    consumer = NotificationConsumer(
        topic=topic,
        group_id=group_id,
        consumer_manager=consumer_manager,
    )

    async def handler(message):
        payload = message.get("payload", {})
        if payload.get("event_id") == event_id:
            receipt = await consumer.handle_message(message, attempt=1)
            results.append(receipt)
            processed_event.set()

    consumer_task = None

    try:
        try:
            await kafka_producer.start()
            await consumer_manager.start()
        except KafkaConnectionError:
            pytest.skip(
                "Kafka broker at localhost:29092 is not reachable. "
                "Start Docker / Kafka container to run live broker E2E test."
            )
        except (TopicAuthorizationFailedError, GroupAuthorizationFailedError):
            pytest.skip(
                "Kafka broker does not grant the notifications identity "
                "read access to fieldops.notification.events."
            )

        consumer_task = asyncio.create_task(
            consumer_manager.consume(handler)
        )

        message = MessageEnvelope(
            sender=AgentAddress(
                agent_type="monitoring",
                agent_id="notification-e2e-producer",
                tenant_id="tenant-e2e",
            ),
            recipient=None,
            message_type=MessageType.EVENT,
            payload={
                "event_type": "notification",
                "event_id": event_id,
                "job_id": job_id,
                "tenant_id": "tenant-e2e",
                "channel": "email",
                "recipient": "customer@example.com",
                "subject": "E2E Notification Test",
                "message": "Notification E2E payload",
                "schema_version": 1,
            },
            correlation_id=run_id,
            topic=topic,
        )

        published = await kafka_producer.publish(message)
        assert published is True

        await asyncio.wait_for(processed_event.wait(), timeout=10)

        assert len(results) == 1
        receipt = results[0]
        assert receipt["status"] == "PROCESSED"
        assert receipt["consumer"] == "notification"
        assert receipt["event_id"] == event_id
        assert receipt["attempt"] == 1

    finally:
        if consumer_task is not None:
            consumer_task.cancel()
            try:
                await consumer_task
            except asyncio.CancelledError:
                pass

        await consumer_manager.stop()
        await kafka_producer.stop()


@pytest.mark.asyncio
async def test_sla_monitoring_consumer_lifecycle_e2e():
    from app.services.sla_monitoring_consumer import SLAMonitoringConsumer

    topic = "fieldops.sla.events"
    group_id = f"fieldops-sla-e2e-{uuid.uuid4()}"

    consumer_manager = KafkaConsumerManager(
        topic=topic,
        group_id=group_id,
        bootstrap_servers="localhost:29092",
    )
    kafka_producer = KafkaProducer()

    processed_event = asyncio.Event()
    results = []
    run_id = uuid.uuid4().hex
    job_id = f"E2E-SLA-JOB-{run_id}"
    event_id = f"evt_sla_e2e_{run_id}"

    consumer = SLAMonitoringConsumer(
        topic=topic,
        group_id=group_id,
        consumer_manager=consumer_manager,
    )

    async def handler(message):
        payload = message.get("payload", {})
        if payload.get("event_id") == event_id:
            receipt = await consumer.handle_message(message, attempt=1)
            results.append(receipt)
            processed_event.set()

    consumer_task = None

    try:
        try:
            await kafka_producer.start()
            await consumer_manager.start()
        except KafkaConnectionError:
            pytest.skip(
                "Kafka broker at localhost:29092 is not reachable. "
                "Start Docker / Kafka container to run live broker E2E test."
            )
        except (TopicAuthorizationFailedError, GroupAuthorizationFailedError):
            pytest.skip(
                "Kafka broker does not grant the sla identity "
                "read access to fieldops.sla.events."
            )

        consumer_task = asyncio.create_task(
            consumer_manager.consume(handler)
        )

        message = MessageEnvelope(
            sender=AgentAddress(
                agent_type="monitoring",
                agent_id="sla-e2e-producer",
                tenant_id="tenant-e2e",
            ),
            recipient=None,
            message_type=MessageType.EVENT,
            payload={
                "event_type": "SLA_CREATED",
                "event_id": event_id,
                "job_id": job_id,
                "tenant_id": "tenant-e2e",
                "deadline": "2026-10-16T18:00:00Z",
                "sla_state": "active",
                "schema_version": 1,
            },
            correlation_id=run_id,
            topic=topic,
        )

        published = await kafka_producer.publish(message)
        assert published is True

        await asyncio.wait_for(processed_event.wait(), timeout=10)

        assert len(results) == 1
        receipt = results[0]
        assert receipt["status"] == "PROCESSED"
        assert receipt["consumer"] == "SLA_monitoring"
        assert receipt["event_id"] == event_id
        assert receipt["attempt"] == 1

    finally:
        if consumer_task is not None:
            consumer_task.cancel()
            try:
                await consumer_task
            except asyncio.CancelledError:
                pass

        await consumer_manager.stop()
        await kafka_producer.stop()


@pytest.mark.asyncio
async def test_billing_consumer_lifecycle_e2e():
    from app.services.billing_consumer import BillingConsumer

    topic = "fieldops.billing.events"
    group_id = f"fieldops-billing-e2e-{uuid.uuid4()}"

    consumer_manager = KafkaConsumerManager(
        topic=topic,
        group_id=group_id,
        bootstrap_servers="localhost:29092",
    )
    kafka_producer = KafkaProducer()

    processed_event = asyncio.Event()
    results = []
    run_id = uuid.uuid4().hex
    job_id = f"E2E-BILLING-JOB-{run_id}"
    event_id = f"evt_billing_e2e_{run_id}"

    consumer = BillingConsumer(
        topic=topic,
        group_id=group_id,
        consumer_manager=consumer_manager,
    )

    async def handler(message):
        payload = message.get("payload", {})
        if payload.get("event_id") == event_id:
            receipt = await consumer.handle_message(message, attempt=1)
            results.append(receipt)
            processed_event.set()

    consumer_task = None

    try:
        try:
            await kafka_producer.start()
            await consumer_manager.start()
        except KafkaConnectionError:
            pytest.skip(
                "Kafka broker at localhost:29092 is not reachable. "
                "Start Docker / Kafka container to run live broker E2E test."
            )
        except (TopicAuthorizationFailedError, GroupAuthorizationFailedError):
            pytest.skip(
                "Kafka broker does not grant the billing identity "
                "read access to fieldops.billing.events."
            )

        consumer_task = asyncio.create_task(
            consumer_manager.consume(handler)
        )

        message = MessageEnvelope(
            sender=AgentAddress(
                agent_type="closure",
                agent_id="billing-e2e-producer",
                tenant_id="tenant-e2e",
            ),
            recipient=None,
            message_type=MessageType.EVENT,
            payload={
                "event_type": "invoice",
                "event_id": event_id,
                "job_id": job_id,
                "tenant_id": "tenant-e2e",
                "invoice_id": f"INV-E2E-{run_id}",
                "amount": 199.99,
                "currency": "USD",
                "schema_version": 1,
            },
            correlation_id=run_id,
            topic=topic,
        )

        published = await kafka_producer.publish(message)
        assert published is True

        await asyncio.wait_for(processed_event.wait(), timeout=10)

        assert len(results) == 1
        receipt = results[0]
        assert receipt["status"] == "PROCESSED"
        assert receipt["consumer"] == "billing"
        assert receipt["event_id"] == event_id
        assert receipt["attempt"] == 1

    finally:
        if consumer_task is not None:
            consumer_task.cancel()
            try:
                await consumer_task
            except asyncio.CancelledError:
                pass

        await consumer_manager.stop()
        await kafka_producer.stop()


@pytest.mark.asyncio
async def test_payment_consumer_lifecycle_e2e():
    from app.services.payment_consumer import PaymentConsumer

    topic = "fieldops.payment.events"
    group_id = f"fieldops-payment-e2e-{uuid.uuid4()}"

    consumer_manager = KafkaConsumerManager(
        topic=topic,
        group_id=group_id,
        bootstrap_servers="localhost:29092",
    )
    kafka_producer = KafkaProducer()

    processed_event = asyncio.Event()
    results = []
    run_id = uuid.uuid4().hex
    job_id = f"E2E-PAYMENT-JOB-{run_id}"
    event_id = f"evt_payment_e2e_{run_id}"

    consumer = PaymentConsumer(
        topic=topic,
        group_id=group_id,
        consumer_manager=consumer_manager,
    )

    async def handler(message):
        payload = message.get("payload", {})
        if payload.get("event_id") == event_id:
            receipt = await consumer.handle_message(message, attempt=1)
            results.append(receipt)
            processed_event.set()

    consumer_task = None

    try:
        try:
            await kafka_producer.start()
            await consumer_manager.start()
        except KafkaConnectionError:
            pytest.skip(
                "Kafka broker at localhost:29092 is not reachable. "
                "Start Docker / Kafka container to run live broker E2E test."
            )
        except (TopicAuthorizationFailedError, GroupAuthorizationFailedError):
            pytest.skip(
                "Kafka broker does not grant the payment identity "
                "read access to fieldops.payment.events."
            )

        consumer_task = asyncio.create_task(
            consumer_manager.consume(handler)
        )

        message = MessageEnvelope(
            sender=AgentAddress(
                agent_type="closure",
                agent_id="payment-e2e-producer",
                tenant_id="tenant-e2e",
            ),
            recipient=None,
            message_type=MessageType.EVENT,
            payload={
                "event_type": "payment",
                "event_id": event_id,
                "job_id": job_id,
                "tenant_id": "tenant-e2e",
                "payment_id": f"PAY-E2E-{run_id}",
                "amount": 249.99,
                "currency": "USD",
                "payment_status": "SUCCESSFUL",
                "schema_version": 1,
            },
            correlation_id=run_id,
            topic=topic,
        )

        published = await kafka_producer.publish(message)
        assert published is True

        await asyncio.wait_for(processed_event.wait(), timeout=10)

        assert len(results) == 1
        receipt = results[0]
        assert receipt["status"] == "PROCESSED"
        assert receipt["consumer"] == "payment"
        assert receipt["event_id"] == event_id
        assert receipt["attempt"] == 1

    finally:
        if consumer_task is not None:
            consumer_task.cancel()
            try:
                await consumer_task
            except asyncio.CancelledError:
                pass

        await consumer_manager.stop()
        await kafka_producer.stop()


@pytest.mark.asyncio
async def test_audit_consumer_lifecycle_e2e():
    from app.services.audit_consumer import AuditConsumer

    topic = "fieldops.audit.events"
    group_id = f"fieldops-audit-e2e-{uuid.uuid4()}"

    consumer_manager = KafkaConsumerManager(
        topic=topic,
        group_id=group_id,
        bootstrap_servers="localhost:29092",
    )
    kafka_producer = KafkaProducer()

    processed_event = asyncio.Event()
    results = []
    run_id = uuid.uuid4().hex
    event_id = f"evt_audit_e2e_{run_id}"

    consumer = AuditConsumer(
        topic=topic,
        group_id=group_id,
        consumer_manager=consumer_manager,
    )

    async def handler(message):
        payload = message.get("payload", {})
        if payload.get("event_id") == event_id:
            receipt = await consumer.handle_message(message, attempt=1)
            results.append(receipt)
            processed_event.set()

    consumer_task = None

    try:
        try:
            await kafka_producer.start()
            await consumer_manager.start()
        except KafkaConnectionError:
            pytest.skip(
                "Kafka broker at localhost:29092 is not reachable. "
                "Start Docker / Kafka container to run live broker E2E test."
            )
        except (TopicAuthorizationFailedError, GroupAuthorizationFailedError):
            pytest.skip(
                "Kafka broker does not grant the audit identity "
                "read access to fieldops.audit.events."
            )

        consumer_task = asyncio.create_task(
            consumer_manager.consume(handler)
        )

        message = MessageEnvelope(
            sender=AgentAddress(
                agent_type="monitoring",
                agent_id="audit-e2e-producer",
                tenant_id="tenant-e2e",
            ),
            recipient=None,
            message_type=MessageType.EVENT,
            payload={
                "event_type": "AUDIT_LOGGED",
                "event_id": event_id,
                "tenant_id": "tenant-e2e",
                "action": "SECURITY_POLICY_UPDATE",
                "severity": "INFO",
                "schema_version": 1,
            },
            correlation_id=run_id,
            topic=topic,
        )

        published = await kafka_producer.publish(message)
        assert published is True

        await asyncio.wait_for(processed_event.wait(), timeout=10)

        assert len(results) == 1
        receipt = results[0]
        assert receipt["status"] == "PROCESSED"
        assert receipt["consumer"] == "audit"
        assert receipt["event_id"] == event_id
        assert receipt["attempt"] == 1

    finally:
        if consumer_task is not None:
            consumer_task.cancel()
            try:
                await consumer_task
            except asyncio.CancelledError:
                pass

        await consumer_manager.stop()
        await kafka_producer.stop()


@pytest.mark.asyncio
async def test_analytics_consumer_lifecycle_e2e():
    from app.services.analytics_consumer import AnalyticsConsumer

    topic = "fieldops.analytics.events"
    group_id = f"fieldops-analytics-e2e-{uuid.uuid4()}"

    consumer_manager = KafkaConsumerManager(
        topic=topic,
        group_id=group_id,
        bootstrap_servers="localhost:29092",
    )
    kafka_producer = KafkaProducer()

    processed_event = asyncio.Event()
    results = []
    run_id = uuid.uuid4().hex
    event_id = f"evt_analytics_e2e_{run_id}"

    consumer = AnalyticsConsumer(
        topic=topic,
        group_id=group_id,
        consumer_manager=consumer_manager,
    )

    async def handler(message):
        payload = message.get("payload", {})
        if payload.get("event_id") == event_id:
            receipt = await consumer.handle_message(message, attempt=1)
            results.append(receipt)
            processed_event.set()

    consumer_task = None

    try:
        try:
            await kafka_producer.start()
            await consumer_manager.start()
        except KafkaConnectionError:
            pytest.skip(
                "Kafka broker at localhost:29092 is not reachable. "
                "Start Docker / Kafka container to run live broker E2E test."
            )
        except (TopicAuthorizationFailedError, GroupAuthorizationFailedError):
            pytest.skip(
                "Kafka broker does not grant the analytics identity "
                "read access to fieldops.analytics.events."
            )

        consumer_task = asyncio.create_task(
            consumer_manager.consume(handler)
        )

        message = MessageEnvelope(
            sender=AgentAddress(
                agent_type="monitoring",
                agent_id="analytics-e2e-producer",
                tenant_id="tenant-e2e",
            ),
            recipient=None,
            message_type=MessageType.EVENT,
            payload={
                "event_type": "kpi_update",
                "event_id": event_id,
                "tenant_id": "tenant-e2e",
                "schema_version": 1,
                "metric_name": "jobs_completed_rate",
                "metric_value": 98.5,
            },
            correlation_id=run_id,
            topic=topic,
        )

        published = await kafka_producer.publish(message)
        assert published is True

        await asyncio.wait_for(processed_event.wait(), timeout=10)

        assert len(results) == 1
        receipt = results[0]
        assert receipt["status"] == "PROCESSED"
        assert receipt["consumer"] == "analytics"
        assert receipt["event_id"] == event_id
        assert receipt["attempt"] == 1

    finally:
        if consumer_task is not None:
            consumer_task.cancel()
            try:
                await consumer_task
            except asyncio.CancelledError:
                pass

        await consumer_manager.stop()
        await kafka_producer.stop()


@pytest.mark.asyncio
async def test_error_handling_consumer_lifecycle_e2e():
    from app.services.consumer_error_handler import ConsumerErrorHandler

    topic = "fieldops.events"
    group_id = f"fieldops-error-handling-e2e-{uuid.uuid4()}"

    consumer_manager = KafkaConsumerManager(
        topic=topic,
        group_id=group_id,
        bootstrap_servers="localhost:29092",
    )
    kafka_producer = KafkaProducer()

    processed_event = asyncio.Event()
    results = []
    run_id = uuid.uuid4().hex
    event_id = f"evt_err_handling_e2e_{run_id}"

    consumer = ConsumerErrorHandler(
        topic=topic,
        group_id=group_id,
        consumer_manager=consumer_manager,
    )

    async def handler(message):
        payload = message.get("payload", {})
        if payload.get("event_id") == event_id:
            receipt = await consumer.handle_message(message, attempt=1)
            results.append(receipt)
            processed_event.set()

    consumer_task = None

    try:
        try:
            await kafka_producer.start()
            await consumer_manager.start()
        except KafkaConnectionError:
            pytest.skip(
                "Kafka broker at localhost:29092 is not reachable. "
                "Start Docker / Kafka container to run live broker E2E test."
            )
        except (TopicAuthorizationFailedError, GroupAuthorizationFailedError):
            pytest.skip(
                "Kafka broker does not grant the identity "
                "read access to fieldops.events."
            )

        consumer_task = asyncio.create_task(
            consumer_manager.consume(handler)
        )

        message = MessageEnvelope(
            sender=AgentAddress(
                agent_type="monitoring",
                agent_id="error-handling-e2e-producer",
                tenant_id="tenant-e2e",
            ),
            recipient=None,
            message_type=MessageType.EVENT,
            payload={
                "event_type": "job_created",
                "event_id": event_id,
                "tenant_id": "tenant-e2e",
                "schema_version": 1,
            },
            correlation_id=run_id,
            topic=topic,
        )

        published = await kafka_producer.publish(message)
        assert published is True

        await asyncio.wait_for(processed_event.wait(), timeout=10)

        assert len(results) == 1
        receipt = results[0]
        assert receipt["status"] == "PROCESSED"
        assert receipt["consumer"] == "Add_error_handling"
        assert receipt["event_id"] == event_id
        assert receipt["attempt"] == 1

    finally:
        if consumer_task is not None:
            consumer_task.cancel()
            try:
                await consumer_task
            except asyncio.CancelledError:
                pass

        await consumer_manager.stop()
        await kafka_producer.stop()


@pytest.mark.asyncio
async def test_retry_mechanism_consumer_lifecycle_e2e():
    from app.services.consumer_retry_mechanism import ConsumerRetryMechanism

    topic = "fieldops.events"
    group_id = f"fieldops-retry-mechanism-e2e-{uuid.uuid4()}"

    consumer_manager = KafkaConsumerManager(
        topic=topic,
        group_id=group_id,
        bootstrap_servers="localhost:29092",
    )
    kafka_producer = KafkaProducer()

    processed_event = asyncio.Event()
    results = []
    run_id = uuid.uuid4().hex
    event_id = f"evt_retry_e2e_{run_id}"

    consumer = ConsumerRetryMechanism(
        topic=topic,
        group_id=group_id,
        consumer_manager=consumer_manager,
    )

    async def handler(message):
        payload = message.get("payload", {})
        if payload.get("event_id") == event_id:
            receipt = await consumer.handle_message(message, attempt=1)
            results.append(receipt)
            processed_event.set()

    consumer_task = None

    try:
        try:
            await kafka_producer.start()
            await consumer_manager.start()
        except KafkaConnectionError:
            pytest.skip(
                "Kafka broker at localhost:29092 is not reachable. "
                "Start Docker / Kafka container to run live broker E2E test."
            )
        except (TopicAuthorizationFailedError, GroupAuthorizationFailedError):
            pytest.skip(
                "Kafka broker does not grant the identity "
                "read access to fieldops.events."
            )

        consumer_task = asyncio.create_task(
            consumer_manager.consume(handler)
        )

        message = MessageEnvelope(
            sender=AgentAddress(
                agent_type="monitoring",
                agent_id="retry-mechanism-e2e-producer",
                tenant_id="tenant-e2e",
            ),
            recipient=None,
            message_type=MessageType.EVENT,
            payload={
                "event_type": "job_created",
                "event_id": event_id,
                "tenant_id": "tenant-e2e",
                "schema_version": 1,
            },
            correlation_id=run_id,
            topic=topic,
        )

        published = await kafka_producer.publish(message)
        assert published is True

        await asyncio.wait_for(processed_event.wait(), timeout=10)

        assert len(results) == 1
        receipt = results[0]
        assert receipt["status"] == "PROCESSED"
        assert receipt["consumer"] == "Add_retry_mechanism"
        assert receipt["event_id"] == event_id
        assert receipt["attempt"] == 1

    finally:
        if consumer_task is not None:
            consumer_task.cancel()
            try:
                await consumer_task
            except asyncio.CancelledError:
                pass

        await consumer_manager.stop()
        await kafka_producer.stop()



@pytest.mark.asyncio
async def test_health_checks_consumer_lifecycle_e2e():
    from app.services.consumer_health_checks import ConsumerHealthChecks

    topic = "fieldops.events"
    group_id = f"fieldops-health-checks-e2e-{uuid.uuid4()}"

    consumer_manager = KafkaConsumerManager(
        topic=topic,
        group_id=group_id,
        bootstrap_servers="localhost:29092",
    )
    kafka_producer = KafkaProducer()

    processed_event = asyncio.Event()
    results = []
    run_id = uuid.uuid4().hex
    event_id = f"evt_health_e2e_{run_id}"

    consumer = ConsumerHealthChecks(
        topic=topic,
        group_id=group_id,
        consumer_manager=consumer_manager,
    )

    async def handler(message):
        payload = message.get("payload", {})
        if payload.get("event_id") == event_id:
            receipt = await consumer.handle_message(message, attempt=1)
            results.append(receipt)
            processed_event.set()

    consumer_task = None

    try:
        try:
            await kafka_producer.start()
            await consumer.start()
        except KafkaConnectionError:
            pytest.skip(
                "Kafka broker at localhost:29092 is not reachable. "
                "Start Docker / Kafka container to run live broker E2E test."
            )
        except (TopicAuthorizationFailedError, GroupAuthorizationFailedError):
            pytest.skip(
                "Kafka broker does not grant the identity "
                "read access to fieldops.events."
            )

        assert consumer.is_connected() is True
        assert consumer.is_ready() is True

        consumer_task = asyncio.create_task(
            consumer_manager.consume(handler)
        )

        message = MessageEnvelope(
            sender=AgentAddress(
                agent_type="monitoring",
                agent_id="health-checks-e2e-producer",
                tenant_id="tenant-e2e",
            ),
            recipient=None,
            message_type=MessageType.EVENT,
            payload={
                "event_type": "job_created",
                "event_id": event_id,
                "tenant_id": "tenant-e2e",
                "schema_version": 1,
            },
            correlation_id=run_id,
            topic=topic,
        )

        published = await kafka_producer.publish(message)
        assert published is True

        await asyncio.wait_for(processed_event.wait(), timeout=10)

        assert len(results) == 1
        receipt = results[0]
        assert receipt["status"] == "PROCESSED"
        assert receipt["consumer"] == "Add_health_checks"
        assert receipt["event_id"] == event_id
        assert receipt["attempt"] == 1

        health_snapshot = await consumer.get_health()
        assert health_snapshot["connected"] is True
        assert health_snapshot["ready"] is True
        assert health_snapshot["consumer"] == "Add_health_checks"
        assert health_snapshot["processing"]["last_event_id"] == event_id
        assert health_snapshot["processing"]["processed_total"] >= 1

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
async def test_dead_letter_topics_consumer_lifecycle_e2e():
    """
    End-to-end verification of Kafka dead-letter topics lifecycle,
    poison message isolation, and recovery output contract.
    """
    from app.services.consumer_dead_letter_topics import ConsumerDeadLetterTopics

    topic = "fieldops.job.events"
    run_id = str(uuid.uuid4())
    event_id = f"evt_dlq_e2e_{run_id[:8]}"

    kafka_producer = KafkaProducer()
    try:
        await kafka_producer.start()
    except Exception as exc:
        pytest.skip(f"Kafka unavailable for dead-letter topics E2E test: {exc}")

    consumer = ConsumerDeadLetterTopics(
        topic=topic,
        kafka_producer=kafka_producer,
    )

    try:
        # 1. Verify healthy processing returns recovery contract
        healthy_msg = {
            "event_id": event_id,
            "tenant_id": "tenant-e2e",
            "topic": topic,
            "payload": {"job_id": "JOB-E2E-DLQ", "status": "ASSIGNED"},
        }

        def handler(p):
            return True

        res_healthy = await consumer.process_event(healthy_msg, handler=handler)
        assert res_healthy["status"] == "RECOVERED"
        assert res_healthy["event_id"] == event_id
        assert res_healthy["retries"] == 1
        assert res_healthy["idempotent"] is True
        assert res_healthy["dlq"] is False

        # 2. Verify poison pill isolates to DLQ topic
        poison_msg = {
            "event_id": f"evt_poison_{run_id[:8]}",
            "tenant_id": "tenant-e2e",
            "topic": topic,
            "payload": {"job_id": "JOB-E2E-POISON", "corrupted": True},
        }

        def poison_handler(p):
            raise ValueError("Poison pill schema validation error")

        res_poison = await consumer.process_event(poison_msg, handler=poison_handler, max_retries=1)
        assert res_poison["status"] == "DEAD_LETTER"
        assert res_poison["dlq"] is True
        assert res_poison["dlq_topic"] == "fieldops.job.events.dlq"
        assert res_poison["idempotent"] is True

        # 3. Verify metrics
        metrics = consumer.get_dlq_metrics()
        assert metrics["dlq_routed_total"] >= 1
        assert metrics["recovered_total"] >= 1

    finally:
        await kafka_producer.stop()
