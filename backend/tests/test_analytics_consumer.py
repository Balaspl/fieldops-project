from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.services.analytics_consumer import (
    ConsumeReceipt,
    AnalyticsConsumer,
    MetricsConsumer,
    AnalyticsEventConsumer,
)
from app.services.ai.FieldOpsAI.schemas.agent_messages import (
    AgentAddress,
    MessageEnvelope,
    MessageType,
    AnalyticsEventMessage,
)
from app.tasks import (
    _process_analytics_event_once,
    process_analytics_event_task,
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
def fake_analytics_pipeline():
    pipeline = MagicMock()
    pipeline.ingest_event = MagicMock()
    return pipeline


def test_consume_receipt_behavior():
    success_receipt = ConsumeReceipt(
        {"status": "PROCESSED", "consumer": "analytics", "event_id": "evt_1", "attempt": 1}
    )
    assert success_receipt.is_success is True
    assert bool(success_receipt) is True
    assert success_receipt["consumer"] == "analytics"

    failed_receipt = ConsumeReceipt(
        {"status": "FAILED", "consumer": "analytics", "event_id": "evt_2", "attempt": 1, "error": "test"}
    )
    assert failed_receipt.is_success is False
    assert bool(failed_receipt) is False


@pytest.mark.parametrize(
    "event_type",
    [
        "analytics",
        "metrics",
        "kpi_update",
        "business_metric",
        "job_metrics",
        "sla_metrics",
        "operational_telemetry",
        "performance_metric",
        "job_created",
        "job_completed",
        "payment_completed",
    ],
)
@pytest.mark.asyncio
async def test_analytics_consumer_primary_success_path(
    event_type,
    fake_redis,
    fake_consumer_manager,
    fake_analytics_pipeline,
):
    consumer = AnalyticsConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        analytics_pipeline=fake_analytics_pipeline,
    )

    event_id = f"evt_analytics_{event_type.lower()}_101"
    payload = {
        "event_type": event_type,
        "event_id": event_id,
        "tenant_id": "tenant-1",
        "job_id": "job_101",
        "schema_version": 1,
        "metric_name": "turnaround_time",
        "metric_value": 42.5,
    }

    with patch("app.services.analytics_consumer.publish_analytics_event") as mock_pub:
        receipt = await consumer.process_event(payload, attempt=1)

        assert isinstance(receipt, ConsumeReceipt)
        assert receipt.is_success is True
        assert bool(receipt) is True
        assert receipt["status"] == "PROCESSED"
        assert receipt["consumer"] == "analytics"
        assert receipt["event_id"] == event_id
        assert receipt["attempt"] == 1

        # Check analytics pipeline ingest and Redis event publish
        fake_analytics_pipeline.ingest_event.assert_called_once_with(
            event_id=event_id,
            tenant_id="tenant-1",
            event_type=event_type,
            schema_version=1,
            job_id="job_101",
            payload=payload,
        )
        mock_pub.assert_called_once()
        assert fake_redis.get(f"analytics:event_processed:{event_id}") == "1"


@pytest.mark.asyncio
async def test_analytics_consumer_async_pipeline(
    fake_redis,
    fake_consumer_manager,
):
    async_pipeline = MagicMock()
    async_pipeline.ingest_event = AsyncMock()

    consumer = AnalyticsConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        analytics_pipeline=async_pipeline,
    )

    event_id = "evt_async_analytics_001"
    payload = {
        "event_type": "analytics",
        "event_id": event_id,
        "tenant_id": "tenant-1",
        "schema_version": 1,
    }

    with patch("app.services.analytics_consumer.publish_analytics_event"):
        receipt = await consumer.process_event(payload, attempt=1)
        assert receipt["status"] == "PROCESSED"
        async_pipeline.ingest_event.assert_awaited_once()


@pytest.mark.asyncio
async def test_analytics_consumer_validates_event_version(
    fake_redis,
    fake_consumer_manager,
    fake_analytics_pipeline,
):
    consumer = AnalyticsConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        analytics_pipeline=fake_analytics_pipeline,
    )

    # 1. Missing schema_version
    res1 = await consumer.process_event({
        "event_type": "analytics",
        "event_id": "evt_no_ver",
        "tenant_id": "tenant-1",
    })
    assert res1["status"] == "FAILED"
    assert res1["consumer"] == "analytics"
    assert "schema_version" in res1["error"]

    # 2. Non-integer schema_version (string)
    res2 = await consumer.process_event({
        "event_type": "analytics",
        "event_id": "evt_str_ver",
        "tenant_id": "tenant-1",
        "schema_version": "v1.0",
    })
    assert res2["status"] == "FAILED"
    assert "Invalid or unsupported event version" in res2["error"]

    # 3. Boolean schema_version
    res3 = await consumer.process_event({
        "event_type": "analytics",
        "event_id": "evt_bool_ver",
        "tenant_id": "tenant-1",
        "schema_version": True,
    })
    assert res3["status"] == "FAILED"
    assert "Invalid or unsupported event version" in res3["error"]

    # 4. Zero or negative schema_version
    res4 = await consumer.process_event({
        "event_type": "analytics",
        "event_id": "evt_zero_ver",
        "tenant_id": "tenant-1",
        "schema_version": 0,
    })
    assert res4["status"] == "FAILED"
    assert "Must be a positive integer" in res4["error"]


@pytest.mark.asyncio
async def test_analytics_consumer_avoids_changing_transactional_source_of_truth(
    fake_redis,
    fake_consumer_manager,
    fake_analytics_pipeline,
):
    # Setup mock transactional Job entity
    mock_db = MagicMock()
    mock_job = MagicMock()
    mock_job.id = 101
    mock_job.tenant_id = "tenant-1"
    mock_job.status = "IN_PROGRESS"

    mock_db.query.return_value.filter.return_value.first.return_value = mock_job
    mock_session_factory = MagicMock(return_value=mock_db)

    consumer = AnalyticsConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        analytics_pipeline=fake_analytics_pipeline,
        db_session_factory=mock_session_factory,
    )

    # Event comes in with status="COMPLETED" attempting to report analytics
    payload = {
        "event_type": "job_completed",
        "event_id": "evt_immutable_sot_1",
        "tenant_id": "tenant-1",
        "job_id": 101,
        "status": "COMPLETED",
        "schema_version": 1,
    }

    with patch("app.services.analytics_consumer.publish_analytics_event"):
        receipt = await consumer.process_event(payload)
        assert receipt["status"] == "PROCESSED"

        # Requirement 1 verification: The transactional Job record must NOT be mutated!
        assert mock_job.status == "IN_PROGRESS"
        # db.commit() must not be called to mutate transactional source-of-truth records
        mock_db.commit.assert_not_called()
        mock_db.close.assert_called_once()


@pytest.mark.asyncio
async def test_analytics_consumer_db_tenant_mismatch_rejection(
    fake_redis,
    fake_consumer_manager,
    fake_analytics_pipeline,
):
    mock_db = MagicMock()
    mock_job = MagicMock()
    mock_job.tenant_id = "tenant-other"

    mock_db.query.return_value.filter.return_value.first.return_value = mock_job
    mock_session_factory = MagicMock(return_value=mock_db)

    consumer = AnalyticsConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        analytics_pipeline=fake_analytics_pipeline,
        db_session_factory=mock_session_factory,
    )

    payload = {
        "event_type": "analytics",
        "event_id": "evt_tenant_mismatch",
        "tenant_id": "tenant-expected",
        "job_id": 202,
        "schema_version": 1,
    }

    res = await consumer.process_event(payload)
    assert res["status"] == "FAILED"
    assert "Tenant mismatch" in res["error"]
    mock_db.close.assert_called_once()


@pytest.mark.asyncio
async def test_analytics_consumer_schema_validation_missing_fields(
    fake_redis,
    fake_consumer_manager,
):
    consumer = AnalyticsConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )

    # Missing event_id and tenant_id
    res = await consumer.process_event({"schema_version": 1})
    assert res["status"] == "FAILED"
    assert res["consumer"] == "analytics"
    assert "Missing required fields" in res["error"]


@pytest.mark.asyncio
async def test_analytics_consumer_unauthorized_topic_rejection(
    fake_redis,
    fake_consumer_manager,
):
    consumer = AnalyticsConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )

    msg = {
        "topic": "fieldops.unauthorized.events",
        "payload": {
            "event_type": "analytics",
            "event_id": "evt_unauth_topic",
            "tenant_id": "tenant-1",
            "schema_version": 1,
        },
    }

    res = await consumer.process_event(msg)
    assert res["status"] == "FAILED"
    assert "is not authorized" in res["error"]


@pytest.mark.asyncio
async def test_analytics_consumer_invalid_event_type_rejection(
    fake_redis,
    fake_consumer_manager,
):
    consumer = AnalyticsConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )

    payload = {
        "event_type": "unknown_analytics_type",
        "event_id": "evt_invalid_type",
        "tenant_id": "tenant-1",
        "schema_version": 1,
    }

    res = await consumer.process_event(payload)
    assert res["status"] == "FAILED"
    assert "Invalid event_type" in res["error"]


@pytest.mark.asyncio
async def test_analytics_consumer_sensitive_forbidden_keys_rejection(
    fake_redis,
    fake_consumer_manager,
):
    consumer = AnalyticsConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )

    payload = {
        "event_type": "analytics",
        "event_id": "evt_secrets",
        "tenant_id": "tenant-1",
        "schema_version": 1,
        "password": "unauthorized_password_leak",
    }

    res = await consumer.process_event(payload)
    assert res["status"] == "FAILED"
    assert "Payload contains forbidden sensitive keys" in res["error"]


@pytest.mark.asyncio
async def test_analytics_consumer_idempotency_prevents_duplicate_processing(
    fake_redis,
    fake_consumer_manager,
    fake_analytics_pipeline,
):
    consumer = AnalyticsConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        analytics_pipeline=fake_analytics_pipeline,
    )

    event_id = "evt_analytics_idempotent_1"
    payload = {
        "event_type": "metrics",
        "event_id": event_id,
        "tenant_id": "tenant-1",
        "schema_version": 1,
        "metric_name": "jobs_dispatched",
        "metric_value": 1,
    }

    with patch("app.services.analytics_consumer.publish_analytics_event") as mock_pub:
        # First processing -> success
        res1 = await consumer.process_event(payload)
        assert res1["status"] == "PROCESSED"
        assert res1.get("idempotent_duplicate") is not True
        assert fake_analytics_pipeline.ingest_event.call_count == 1
        assert mock_pub.call_count == 1

        # Second processing with same event_id -> idempotent duplicate detected
        res2 = await consumer.process_event(payload)
        assert res2["status"] == "PROCESSED"
        assert res2.get("idempotent_duplicate") is True
        assert fake_analytics_pipeline.ingest_event.call_count == 1
        assert mock_pub.call_count == 1


@pytest.mark.asyncio
async def test_analytics_consumer_handles_pipeline_failure(
    fake_redis,
    fake_consumer_manager,
    fake_analytics_pipeline,
):
    fake_analytics_pipeline.ingest_event.side_effect = RuntimeError("Warehouse connection down")

    consumer = AnalyticsConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        analytics_pipeline=fake_analytics_pipeline,
    )

    event_id = "evt_analytics_fail_1"
    payload = {
        "event_type": "analytics",
        "event_id": event_id,
        "tenant_id": "tenant-1",
        "schema_version": 1,
    }

    res = await consumer.process_event(payload, attempt=2)
    assert res["status"] == "FAILED"
    assert res["consumer"] == "analytics"
    assert res["attempt"] == 2
    assert "Warehouse connection down" in res["error"]
    # Redis idempotency marker must NOT be set on failure
    assert fake_redis.get(f"analytics:event_processed:{event_id}") is None


@pytest.mark.asyncio
async def test_analytics_consumer_retry_after_failure(
    fake_redis,
    fake_consumer_manager,
    fake_analytics_pipeline,
):
    consumer = AnalyticsConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        analytics_pipeline=fake_analytics_pipeline,
    )

    event_id = "evt_analytics_retry_1"
    payload = {
        "event_type": "analytics",
        "event_id": event_id,
        "tenant_id": "tenant-1",
        "schema_version": 1,
    }

    # First attempt fails
    fake_analytics_pipeline.ingest_event.side_effect = ConnectionError("Pipeline buffer full")
    res1 = await consumer.process_event(payload, attempt=1)
    assert res1["status"] == "FAILED"
    assert res1["attempt"] == 1

    # Second attempt succeeds
    fake_analytics_pipeline.ingest_event.side_effect = None
    with patch("app.services.analytics_consumer.publish_analytics_event"):
        res2 = await consumer.process_event(payload, attempt=2)
        assert res2["status"] == "PROCESSED"
        assert res2["attempt"] == 2
        assert fake_redis.get(f"analytics:event_processed:{event_id}") == "1"


@pytest.mark.asyncio
async def test_analytics_consumer_supports_message_envelope(
    fake_redis,
    fake_consumer_manager,
    fake_analytics_pipeline,
):
    consumer = AnalyticsConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        analytics_pipeline=fake_analytics_pipeline,
    )

    event_id = "evt_envelope_analytics_1"
    envelope = MessageEnvelope(
        sender=AgentAddress(
            agent_type="monitoring",
            agent_id="analytics-service-1",
            tenant_id="tenant-env",
        ),
        recipient=None,
        message_type=MessageType.EVENT,
        payload={
            "event_type": "analytics",
            "event_id": event_id,
            "tenant_id": "tenant-env",
            "schema_version": 1,
            "metric_name": "latency_ms",
            "metric_value": 12.4,
        },
        correlation_id="corr-envelope-analytics-1",
        topic="fieldops.analytics.events",
    )

    with patch("app.services.analytics_consumer.publish_analytics_event"):
        res = await consumer.process_event(envelope)
        assert res["status"] == "PROCESSED"
        assert res["consumer"] == "analytics"
        assert res["event_id"] == event_id


@pytest.mark.asyncio
async def test_analytics_consumer_supports_analytics_event_message(
    fake_redis,
    fake_consumer_manager,
    fake_analytics_pipeline,
):
    consumer = AnalyticsConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        analytics_pipeline=fake_analytics_pipeline,
    )

    event_id = "evt_analytics_msg_1"
    msg = AnalyticsEventMessage(
        sender=AgentAddress(
            agent_type="monitoring",
            agent_id="analytics-service-1",
            tenant_id="tenant-msg",
        ),
        payload={
            "event_type": "kpi_update",
            "event_id": event_id,
            "tenant_id": "tenant-msg",
            "schema_version": 1,
            "metric_name": "jobs_completed_rate",
            "metric_value": 98.7,
        },
        correlation_id="corr-analytics-msg-1",
        topic="fieldops.analytics.events",
    )

    with patch("app.services.analytics_consumer.publish_analytics_event"):
        res = await consumer.process_event(msg)
        assert res["status"] == "PROCESSED"
        assert res["consumer"] == "analytics"
        assert res["event_id"] == event_id


@pytest.mark.asyncio
async def test_analytics_consumer_async_context_manager(
    fake_redis,
    fake_consumer_manager,
):
    consumer = AnalyticsConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )

    async with consumer as c:
        assert c is consumer
        fake_consumer_manager.start.assert_awaited_once()

    fake_consumer_manager.stop.assert_awaited_once()


def test_analytics_consumer_aliases():
    assert MetricsConsumer is AnalyticsConsumer
    assert AnalyticsEventConsumer is AnalyticsConsumer


def test_process_analytics_event_once_task_integration(fake_redis):
    event_id = "evt_celery_analytics_1"
    payload = {
        "event_type": "analytics",
        "event_id": event_id,
        "tenant_id": "tenant-1",
        "schema_version": 1,
        "metric_name": "active_users",
        "metric_value": 150,
    }

    with patch("app.services.analytics_consumer.publish_analytics_event"):
        res = _process_analytics_event_once(
            redis=fake_redis,
            event_payload=payload,
            attempt=1,
        )
        assert res["status"] == "PROCESSED"
        assert res["consumer"] == "analytics"
        assert res["event_id"] == event_id
        assert fake_redis.get(f"analytics:event_processed:{event_id}") == "1"

        # Celery task wrapper
        with patch("app.tasks.get_redis_client", return_value=fake_redis):
            task_res = process_analytics_event_task(event_payload=payload, attempt=1)
            assert task_res["status"] == "PROCESSED"
            assert task_res["consumer"] == "analytics"

