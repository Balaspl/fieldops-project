from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.services.audit_consumer import (
    ConsumeReceipt,
    AuditConsumer,
    AuditEventConsumer,
    EnterpriseAuditConsumer,
)
from app.services.ai.FieldOpsAI.schemas.agent_messages import (
    AgentAddress,
    MessageEnvelope,
    MessageType,
    AuditEventMessage,
)
from app.tasks import (
    _process_audit_event_once,
    process_audit_event_task,
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
def fake_analytics_client():
    client = MagicMock()
    client.ingest_event = MagicMock()
    return client


def test_consume_receipt_behavior():
    success_receipt = ConsumeReceipt(
        {"status": "PROCESSED", "consumer": "audit", "event_id": "evt_1", "attempt": 1}
    )
    assert success_receipt.is_success is True
    assert bool(success_receipt) is True
    assert success_receipt["consumer"] == "audit"

    failed_receipt = ConsumeReceipt(
        {"status": "FAILED", "consumer": "audit", "event_id": "evt_2", "attempt": 1, "error": "test"}
    )
    assert failed_receipt.is_success is False
    assert bool(failed_receipt) is False


@pytest.mark.parametrize(
    "event_type",
    [
        "audit",
        "AUDIT",
        "audit_event",
        "AUDIT_EVENT",
        "audit-event",
        "audit_logged",
        "AUDIT_LOGGED",
        "manual_override",
        "MANUAL_OVERRIDE",
        "status_transition",
        "STATUS_TRANSITION",
        "security_event",
        "SECURITY_EVENT",
        "access_revoked",
        "ACCESS_REVOKED",
    ],
)
@pytest.mark.asyncio
async def test_audit_consumer_primary_success_path(
    event_type,
    fake_redis,
    fake_consumer_manager,
    fake_analytics_client,
):
    consumer = AuditConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        analytics_client=fake_analytics_client,
    )

    event_id = f"evt_audit_{event_type.lower()}_101"
    payload = {
        "event_type": event_type,
        "event_id": event_id,
        "tenant_id": "tenant-1",
        "job_id": "job_101",
        "user_id": "user_admin_01",
        "action": "RECORD_AUDIT",
        "severity": "INFO",
        "schema_version": 1,
    }

    with patch("app.services.audit_consumer.publish_audit_event") as mock_pub:
        receipt = await consumer.process_event(payload, attempt=1)

        assert isinstance(receipt, ConsumeReceipt)
        assert receipt.is_success is True
        assert bool(receipt) is True
        assert receipt["status"] == "PROCESSED"
        assert receipt["consumer"] == "audit"
        assert receipt["event_id"] == event_id
        assert receipt["attempt"] == 1

        # Check analytics ingest and event publish
        fake_analytics_client.ingest_event.assert_called_once_with(
            event_id=event_id,
            tenant_id="tenant-1",
            event_type=event_type,
            job_id="job_101",
            user_id="user_admin_01",
            severity="INFO",
            payload=payload,
        )
        mock_pub.assert_called_once()
        assert fake_redis.get(f"audit:event_processed:{event_id}") == "1"


@pytest.mark.asyncio
async def test_audit_consumer_async_analytics_client(
    fake_redis,
    fake_consumer_manager,
):
    async_analytics = MagicMock()
    async_analytics.ingest_event = AsyncMock()

    consumer = AuditConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        analytics_client=async_analytics,
    )

    event_id = "evt_async_audit_001"
    payload = {
        "event_type": "audit",
        "event_id": event_id,
        "tenant_id": "tenant-1",
        "schema_version": 1,
    }

    with patch("app.services.audit_consumer.publish_audit_event"):
        receipt = await consumer.process_event(payload, attempt=1)
        assert receipt["status"] == "PROCESSED"
        async_analytics.ingest_event.assert_awaited_once()


@pytest.mark.asyncio
async def test_audit_consumer_schema_validation_missing_fields(
    fake_redis,
    fake_consumer_manager,
    fake_analytics_client,
):
    consumer = AuditConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        analytics_client=fake_analytics_client,
    )

    # 1. Missing event_id
    res1 = await consumer.process_event({
        "event_type": "audit",
        "tenant_id": "tenant-1",
        "schema_version": 1,
    })
    assert res1["status"] == "FAILED"
    assert res1["consumer"] == "audit"
    assert "Missing required fields" in res1["error"]
    assert "event_id" in res1["error"]

    # 2. Blank event_id
    res2 = await consumer.process_event({
        "event_type": "audit",
        "event_id": "   ",
        "tenant_id": "tenant-1",
        "schema_version": 1,
    })
    assert res2["status"] == "FAILED"
    assert "event_id" in res2["error"]

    # 3. Missing tenant_id
    res3 = await consumer.process_event({
        "event_type": "audit",
        "event_id": "evt_no_tenant",
        "schema_version": 1,
    })
    assert res3["status"] == "FAILED"
    assert "tenant_id" in res3["error"]

    # 4. Blank tenant_id
    res4 = await consumer.process_event({
        "event_type": "audit",
        "event_id": "evt_blank_tenant",
        "tenant_id": "   ",
        "schema_version": 1,
    })
    assert res4["status"] == "FAILED"
    assert "tenant_id" in res4["error"]

    # 5. Missing schema_version
    res5 = await consumer.process_event({
        "event_type": "audit",
        "event_id": "evt_no_schema",
        "tenant_id": "tenant-1",
    })
    assert res5["status"] == "FAILED"
    assert "schema_version" in res5["error"]


@pytest.mark.asyncio
async def test_audit_consumer_severity_validation(
    fake_redis,
    fake_consumer_manager,
    fake_analytics_client,
):
    consumer = AuditConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        analytics_client=fake_analytics_client,
    )

    payload = {
        "event_type": "audit",
        "event_id": "evt_bad_severity",
        "tenant_id": "tenant-1",
        "severity": "SUPER_CRITICAL_UNKNOWN",
        "schema_version": 1,
    }

    res = await consumer.process_event(payload)
    assert res["status"] == "FAILED"
    assert "Invalid audit severity" in res["error"]


@pytest.mark.asyncio
async def test_audit_consumer_db_session_factory_immutability_and_tenant(
    fake_redis,
    fake_consumer_manager,
    fake_analytics_client,
):
    # 1. Existing immutable audit record with tenant mismatch -> FAILED
    mock_db = MagicMock()
    mock_existing_audit = MagicMock()
    mock_existing_audit.tenant_id = "tenant-other"
    mock_db.query.return_value.filter.return_value.first.return_value = mock_existing_audit
    mock_session_factory = MagicMock(return_value=mock_db)

    consumer = AuditConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        analytics_client=fake_analytics_client,
        db_session_factory=mock_session_factory,
    )

    payload = {
        "event_type": "audit",
        "event_id": "evt_immutable_mismatch",
        "tenant_id": "tenant-expected",
        "schema_version": 1,
    }

    res1 = await consumer.process_event(payload)
    assert res1["status"] == "FAILED"
    assert "Tenant mismatch for immutable audit record" in res1["error"]
    mock_db.close.assert_called_once()

    # 2. Existing immutable audit record with matching tenant -> PROCESSED (idempotent duplicate)
    mock_db_dupe = MagicMock()
    mock_dupe_audit = MagicMock()
    mock_dupe_audit.tenant_id = "tenant-expected"
    mock_db_dupe.query.return_value.filter.return_value.first.return_value = mock_dupe_audit
    mock_session_factory_dupe = MagicMock(return_value=mock_db_dupe)

    consumer_dupe = AuditConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        analytics_client=fake_analytics_client,
        db_session_factory=mock_session_factory_dupe,
    )

    res2 = await consumer_dupe.process_event(payload)
    assert res2["status"] == "PROCESSED"
    assert res2.get("idempotent_duplicate") is True

    # 3. Related Job entity tenant mismatch -> FAILED
    mock_db_job = MagicMock()
    # first query for EnterpriseAuditLog returns None (new record)
    mock_job = MagicMock()
    mock_job.tenant_id = "tenant-different-job"
    mock_db_job.query.return_value.filter.return_value.first.side_effect = [None, mock_job]
    mock_session_factory_job = MagicMock(return_value=mock_db_job)

    consumer_job = AuditConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        analytics_client=fake_analytics_client,
        db_session_factory=mock_session_factory_job,
    )

    payload_job = {
        "event_type": "audit",
        "event_id": "evt_job_tenant_mismatch",
        "tenant_id": "tenant-expected",
        "job_id": 999,
        "schema_version": 1,
    }

    res3 = await consumer_job.process_event(payload_job)
    assert res3["status"] == "FAILED"
    assert "Tenant mismatch between audit event and persisted job entity" in res3["error"]

    # 4. Successful append-only persistence to DB
    mock_db_new = MagicMock()
    mock_db_new.query.return_value.filter.return_value.first.side_effect = [None, None]
    mock_session_factory_new = MagicMock(return_value=mock_db_new)

    consumer_new = AuditConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        analytics_client=fake_analytics_client,
        db_session_factory=mock_session_factory_new,
    )

    with patch("app.services.audit_consumer.publish_audit_event"):
        res4 = await consumer_new.process_event({
            "event_type": "audit",
            "event_id": "evt_db_persist_1",
            "tenant_id": "tenant-new",
            "schema_version": 1,
            "action": "LOGIN",
            "severity": "INFO",
        })
        assert res4["status"] == "PROCESSED"
        mock_db_new.add.assert_called_once()
        mock_db_new.commit.assert_called_once()


@pytest.mark.asyncio
async def test_audit_consumer_unauthorized_topic_rejection(
    fake_redis,
    fake_consumer_manager,
):
    consumer = AuditConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )

    msg = {
        "topic": "fieldops.unauthorized.events",
        "payload": {
            "event_type": "audit",
            "event_id": "evt_unauth_topic",
            "tenant_id": "tenant-1",
            "schema_version": 1,
        },
    }

    res = await consumer.process_event(msg)
    assert res["status"] == "FAILED"
    assert "is not authorized" in res["error"]


@pytest.mark.asyncio
async def test_audit_consumer_invalid_event_type_rejection(
    fake_redis,
    fake_consumer_manager,
):
    consumer = AuditConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )

    payload = {
        "event_type": "unknown_audit_event_type",
        "event_id": "evt_invalid_type",
        "tenant_id": "tenant-1",
        "schema_version": 1,
    }

    res = await consumer.process_event(payload)
    assert res["status"] == "FAILED"
    assert "Invalid event_type" in res["error"]


@pytest.mark.asyncio
async def test_audit_consumer_sensitive_forbidden_keys_rejection(
    fake_redis,
    fake_consumer_manager,
):
    consumer = AuditConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )

    payload = {
        "event_type": "audit",
        "event_id": "evt_secrets",
        "tenant_id": "tenant-1",
        "schema_version": 1,
        "token": "bearer_secret_token_12345",
    }

    res = await consumer.process_event(payload)
    assert res["status"] == "FAILED"
    assert "Payload contains forbidden sensitive keys" in res["error"]


@pytest.mark.asyncio
async def test_audit_consumer_idempotency_prevents_duplicate_processing(
    fake_redis,
    fake_consumer_manager,
    fake_analytics_client,
):
    consumer = AuditConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        analytics_client=fake_analytics_client,
    )

    event_id = "evt_audit_idempotent_1"
    payload = {
        "event_type": "audit",
        "event_id": event_id,
        "tenant_id": "tenant-1",
        "schema_version": 1,
        "action": "CONFIG_UPDATE",
    }

    with patch("app.services.audit_consumer.publish_audit_event") as mock_pub:
        # First processing -> success
        res1 = await consumer.process_event(payload)
        assert res1["status"] == "PROCESSED"
        assert res1.get("idempotent_duplicate") is not True
        assert fake_analytics_client.ingest_event.call_count == 1
        assert mock_pub.call_count == 1

        # Second processing with same event_id -> idempotent duplicate detected
        res2 = await consumer.process_event(payload)
        assert res2["status"] == "PROCESSED"
        assert res2.get("idempotent_duplicate") is True
        assert fake_analytics_client.ingest_event.call_count == 1
        assert mock_pub.call_count == 1


@pytest.mark.asyncio
async def test_audit_consumer_handles_analytics_failure(
    fake_redis,
    fake_consumer_manager,
    fake_analytics_client,
):
    fake_analytics_client.ingest_event.side_effect = RuntimeError("Analytics service unavailable")

    consumer = AuditConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        analytics_client=fake_analytics_client,
    )

    event_id = "evt_audit_fail_1"
    payload = {
        "event_type": "audit",
        "event_id": event_id,
        "tenant_id": "tenant-1",
        "schema_version": 1,
    }

    res = await consumer.process_event(payload, attempt=2)
    assert res["status"] == "FAILED"
    assert res["consumer"] == "audit"
    assert res["attempt"] == 2
    assert "Analytics service unavailable" in res["error"]
    # Redis idempotency marker must NOT be set on failure
    assert fake_redis.get(f"audit:event_processed:{event_id}") is None


@pytest.mark.asyncio
async def test_audit_consumer_retry_after_failure(
    fake_redis,
    fake_consumer_manager,
    fake_analytics_client,
):
    consumer = AuditConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        analytics_client=fake_analytics_client,
    )

    event_id = "evt_audit_retry_1"
    payload = {
        "event_type": "audit",
        "event_id": event_id,
        "tenant_id": "tenant-1",
        "schema_version": 1,
    }

    # First attempt fails
    fake_analytics_client.ingest_event.side_effect = ConnectionError("Storage endpoint timeout")
    res1 = await consumer.process_event(payload, attempt=1)
    assert res1["status"] == "FAILED"
    assert res1["attempt"] == 1

    # Second attempt succeeds
    fake_analytics_client.ingest_event.side_effect = None
    with patch("app.services.audit_consumer.publish_audit_event"):
        res2 = await consumer.process_event(payload, attempt=2)
        assert res2["status"] == "PROCESSED"
        assert res2["attempt"] == 2
        assert fake_redis.get(f"audit:event_processed:{event_id}") == "1"


@pytest.mark.asyncio
async def test_audit_consumer_supports_message_envelope(
    fake_redis,
    fake_consumer_manager,
    fake_analytics_client,
):
    consumer = AuditConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        analytics_client=fake_analytics_client,
    )

    event_id = "evt_envelope_audit_1"
    envelope = MessageEnvelope(
        sender=AgentAddress(
            agent_type="monitoring",
            agent_id="audit-service-1",
            tenant_id="tenant-env",
        ),
        recipient=None,
        message_type=MessageType.EVENT,
        payload={
            "event_type": "audit",
            "event_id": event_id,
            "tenant_id": "tenant-env",
            "action": "ACCESS_CHECK",
            "schema_version": 1,
        },
        correlation_id="corr-envelope-audit-1",
        topic="fieldops.audit.events",
    )

    with patch("app.services.audit_consumer.publish_audit_event"):
        res = await consumer.process_event(envelope)
        assert res["status"] == "PROCESSED"
        assert res["consumer"] == "audit"
        assert res["event_id"] == event_id


@pytest.mark.asyncio
async def test_audit_consumer_supports_audit_event_message(
    fake_redis,
    fake_consumer_manager,
    fake_analytics_client,
):
    consumer = AuditConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        analytics_client=fake_analytics_client,
    )

    event_id = "evt_audit_msg_1"
    audit_msg = AuditEventMessage(
        sender=AgentAddress(
            agent_type="monitoring",
            agent_id="audit-service-1",
            tenant_id="tenant-msg",
        ),
        payload={
            "event_type": "audit",
            "event_id": event_id,
            "tenant_id": "tenant-msg",
            "action": "POLICY_EVALUATION",
            "schema_version": 1,
        },
        correlation_id="corr-audit-msg-1",
        topic="fieldops.audit.events",
    )

    with patch("app.services.audit_consumer.publish_audit_event"):
        res = await consumer.process_event(audit_msg)
        assert res["status"] == "PROCESSED"
        assert res["consumer"] == "audit"
        assert res["event_id"] == event_id


@pytest.mark.asyncio
async def test_audit_consumer_async_context_manager(
    fake_redis,
    fake_consumer_manager,
):
    consumer = AuditConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )

    async with consumer as c:
        assert c is consumer
        fake_consumer_manager.start.assert_awaited_once()

    fake_consumer_manager.stop.assert_awaited_once()


def test_audit_consumer_aliases():
    assert AuditEventConsumer is AuditConsumer
    assert EnterpriseAuditConsumer is AuditConsumer


def test_process_audit_event_once_task_integration(fake_redis):
    event_id = "evt_celery_audit_1"
    payload = {
        "event_type": "audit",
        "event_id": event_id,
        "tenant_id": "tenant-1",
        "action": "CELERY_TASK_EXECUTION",
        "schema_version": 1,
    }

    with patch("app.services.audit_consumer.publish_audit_event"):
        res = _process_audit_event_once(
            redis=fake_redis,
            event_payload=payload,
            attempt=1,
        )
        assert res["status"] == "PROCESSED"
        assert res["consumer"] == "audit"
        assert res["event_id"] == event_id
        assert fake_redis.get(f"audit:event_processed:{event_id}") == "1"

        # Celery task wrapper
        with patch("app.tasks.get_redis_client", return_value=fake_redis):
            task_res = process_audit_event_task(event_payload=payload, attempt=1)
            assert task_res["status"] == "PROCESSED"
            assert task_res["consumer"] == "audit"

