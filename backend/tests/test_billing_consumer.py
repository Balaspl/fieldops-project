from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.services.billing_consumer import (
    ConsumeReceipt,
    BillingConsumer,
    InvoiceConsumer,
    BillingEventConsumer,
)
from app.services.ai.FieldOpsAI.schemas.agent_messages import (
    AgentAddress,
    MessageEnvelope,
    MessageType,
    InvoiceEventMessage,
)
from app.tasks import (
    _process_billing_event_once,
    process_billing_event_task,
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
def fake_erp_client():
    client = MagicMock()
    client.sync_invoice = MagicMock()
    return client


def test_consume_receipt_behavior():
    success_receipt = ConsumeReceipt(
        {"status": "PROCESSED", "consumer": "billing", "event_id": "evt_1", "attempt": 1}
    )
    assert success_receipt.is_success is True
    assert bool(success_receipt) is True
    assert success_receipt["consumer"] == "billing"

    failed_receipt = ConsumeReceipt(
        {"status": "FAILED", "consumer": "billing", "event_id": "evt_2", "attempt": 1, "error": "test"}
    )
    assert failed_receipt.is_success is False
    assert bool(failed_receipt) is False


@pytest.mark.parametrize(
    "event_type",
    [
        "invoice",
        "billing",
        "INVOICE_GENERATED",
        "invoice_created",
        "INVOICE_PAID",
        "invoice_synced",
        "billing_synced",
        "erp_synced",
    ],
)
@pytest.mark.asyncio
async def test_billing_consumer_primary_success_path(
    event_type,
    fake_redis,
    fake_consumer_manager,
    fake_erp_client,
):
    consumer = BillingConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        erp_client=fake_erp_client,
    )

    event_id = f"evt_billing_{event_type.lower()}_101"
    payload = {
        "event_type": event_type,
        "event_id": event_id,
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "invoice_id": "INV-2026-001",
        "amount": 250.75,
        "currency": "USD",
        "financial_status": "ISSUED",
        "schema_version": 1,
    }

    with patch("app.services.billing_consumer.publish_invoice_event") as mock_pub:
        receipt = await consumer.process_event(payload, attempt=1)

        assert isinstance(receipt, ConsumeReceipt)
        assert receipt.is_success is True
        assert bool(receipt) is True
        assert receipt["status"] == "PROCESSED"
        assert receipt["consumer"] == "billing"
        assert receipt["event_id"] == event_id
        assert receipt["attempt"] == 1

        # Check ERP sync and event publish
        fake_erp_client.sync_invoice.assert_called_once_with(
            invoice_id="INV-2026-001",
            job_id="job_101",
            tenant_id="tenant-1",
            amount=250.75,
            currency="USD",
            payload=payload,
        )
        mock_pub.assert_called_once()
        assert fake_redis.get(f"billing:event_processed:{event_id}") == "1"


@pytest.mark.asyncio
async def test_billing_consumer_async_erp_client(
    fake_redis,
    fake_consumer_manager,
):
    async_erp = MagicMock()
    async_erp.sync_invoice = AsyncMock()

    consumer = BillingConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        erp_client=async_erp,
    )

    event_id = "evt_async_erp_001"
    payload = {
        "event_type": "invoice",
        "event_id": event_id,
        "job_id": "job_102",
        "tenant_id": "tenant-1",
        "invoice_id": "INV-2026-002",
        "amount": 100.0,
        "currency": "EUR",
        "schema_version": 1,
    }

    with patch("app.services.billing_consumer.publish_invoice_event"):
        receipt = await consumer.process_event(payload, attempt=1)
        assert receipt["status"] == "PROCESSED"
        async_erp.sync_invoice.assert_awaited_once()


@pytest.mark.asyncio
async def test_billing_consumer_validates_invoice_identifier(
    fake_redis,
    fake_consumer_manager,
    fake_erp_client,
):
    consumer = BillingConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        erp_client=fake_erp_client,
    )

    # 1. Missing invoice identifier
    missing_inv_payload = {
        "event_type": "invoice",
        "event_id": "evt_missing_inv",
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "amount": 150.0,
        "currency": "USD",
        "schema_version": 1,
    }
    res1 = await consumer.process_event(missing_inv_payload)
    assert res1["status"] == "FAILED"
    assert res1["consumer"] == "billing"
    assert "invoice identifier" in res1["error"].lower()

    # 2. Whitespace-only invoice identifier
    blank_inv_payload = {
        "event_type": "invoice",
        "event_id": "evt_blank_inv",
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "invoice_id": "   ",
        "amount": 150.0,
        "currency": "USD",
        "schema_version": 1,
    }
    res2 = await consumer.process_event(blank_inv_payload)
    assert res2["status"] == "FAILED"
    assert res2["consumer"] == "billing"
    assert "invoice identifier" in res2["error"].lower()


@pytest.mark.asyncio
async def test_billing_consumer_validates_financial_state(
    fake_redis,
    fake_consumer_manager,
    fake_erp_client,
):
    consumer = BillingConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        erp_client=fake_erp_client,
    )

    # 1. Negative amount
    neg_amount_payload = {
        "event_type": "invoice",
        "event_id": "evt_neg_amount",
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "invoice_id": "INV-001",
        "amount": -50.0,
        "currency": "USD",
        "schema_version": 1,
    }
    res1 = await consumer.process_event(neg_amount_payload)
    assert res1["status"] == "FAILED"
    assert "cannot be negative" in res1["error"].lower()

    # 2. Non-numeric boolean amount
    bool_amount_payload = {
        "event_type": "invoice",
        "event_id": "evt_bool_amount",
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "invoice_id": "INV-001",
        "amount": True,
        "currency": "USD",
        "schema_version": 1,
    }
    res2 = await consumer.process_event(bool_amount_payload)
    assert res2["status"] == "FAILED"
    assert "must be a numeric value" in res2["error"].lower()

    # 3. Invalid currency format
    bad_currency_payload = {
        "event_type": "invoice",
        "event_id": "evt_bad_curr",
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "invoice_id": "INV-001",
        "amount": 100.0,
        "currency": "US-DOLLAR",
        "schema_version": 1,
    }
    res3 = await consumer.process_event(bad_currency_payload)
    assert res3["status"] == "FAILED"
    assert "invalid currency code" in res3["error"].lower()

    # 4. Invalid financial status
    bad_status_payload = {
        "event_type": "invoice",
        "event_id": "evt_bad_status",
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "invoice_id": "INV-001",
        "amount": 100.0,
        "currency": "USD",
        "financial_status": "SUPER_PAID",
        "schema_version": 1,
    }
    res4 = await consumer.process_event(bad_status_payload)
    assert res4["status"] == "FAILED"
    assert "invalid financial status" in res4["error"].lower()


@pytest.mark.asyncio
async def test_billing_consumer_db_session_factory_tenant_mismatch(
    fake_redis,
    fake_consumer_manager,
    fake_erp_client,
):
    mock_db = MagicMock()
    mock_closure = MagicMock()
    mock_closure.tenant_id = "tenant-different"
    mock_db.query.return_value.filter.return_value.first.return_value = mock_closure

    mock_session_factory = MagicMock(return_value=mock_db)

    consumer = BillingConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        erp_client=fake_erp_client,
        db_session_factory=mock_session_factory,
    )

    payload = {
        "event_type": "invoice",
        "event_id": "evt_tenant_mismatch",
        "job_id": 999,
        "tenant_id": "tenant-expected",
        "invoice_id": "INV-001",
        "amount": 100.0,
        "currency": "USD",
        "schema_version": 1,
    }

    res = await consumer.process_event(payload)
    assert res["status"] == "FAILED"
    assert "tenant mismatch" in res["error"].lower()
    mock_db.close.assert_called_once()


@pytest.mark.asyncio
async def test_billing_consumer_schema_validation_missing_fields(
    fake_redis,
    fake_consumer_manager,
):
    consumer = BillingConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )

    # Missing event_id, job_id, tenant_id, schema_version
    res = await consumer.process_event({})
    assert res["status"] == "FAILED"
    assert res["consumer"] == "billing"
    assert "Missing required fields" in res["error"]


@pytest.mark.asyncio
async def test_billing_consumer_unauthorized_topic_rejection(
    fake_redis,
    fake_consumer_manager,
):
    consumer = BillingConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )

    msg = {
        "topic": "fieldops.unauthorized.events",
        "payload": {
            "event_type": "invoice",
            "event_id": "evt_unauth_topic",
            "job_id": "job_1",
            "tenant_id": "tenant-1",
            "invoice_id": "INV-1",
            "schema_version": 1,
        },
    }

    res = await consumer.process_event(msg)
    assert res["status"] == "FAILED"
    assert "is not authorized" in res["error"]


@pytest.mark.asyncio
async def test_billing_consumer_invalid_event_type_rejection(
    fake_redis,
    fake_consumer_manager,
):
    consumer = BillingConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )

    payload = {
        "event_type": "unknown_billing_event",
        "event_id": "evt_invalid_type",
        "job_id": "job_1",
        "tenant_id": "tenant-1",
        "invoice_id": "INV-1",
        "schema_version": 1,
    }

    res = await consumer.process_event(payload)
    assert res["status"] == "FAILED"
    assert "Invalid event_type" in res["error"]


@pytest.mark.asyncio
async def test_billing_consumer_sensitive_forbidden_keys_rejection(
    fake_redis,
    fake_consumer_manager,
):
    consumer = BillingConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )

    payload = {
        "event_type": "invoice",
        "event_id": "evt_secrets",
        "job_id": "job_1",
        "tenant_id": "tenant-1",
        "invoice_id": "INV-1",
        "schema_version": 1,
        "api_key": "secret_api_key_12345",
    }

    res = await consumer.process_event(payload)
    assert res["status"] == "FAILED"
    assert "Payload contains forbidden sensitive keys" in res["error"]


@pytest.mark.asyncio
async def test_billing_consumer_idempotency_prevents_duplicate_processing(
    fake_redis,
    fake_consumer_manager,
    fake_erp_client,
):
    consumer = BillingConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        erp_client=fake_erp_client,
    )

    event_id = "evt_billing_idempotent_1"
    payload = {
        "event_type": "invoice",
        "event_id": event_id,
        "job_id": "job_201",
        "tenant_id": "tenant-1",
        "invoice_id": "INV-201",
        "amount": 75.0,
        "currency": "USD",
        "schema_version": 1,
    }

    with patch("app.services.billing_consumer.publish_invoice_event") as mock_pub:
        # First processing -> success
        res1 = await consumer.process_event(payload)
        assert res1["status"] == "PROCESSED"
        assert res1.get("idempotent_duplicate") is not True
        assert fake_erp_client.sync_invoice.call_count == 1
        assert mock_pub.call_count == 1

        # Second processing -> idempotent duplicate detected, skip ERP sync & publish
        res2 = await consumer.process_event(payload)
        assert res2["status"] == "PROCESSED"
        assert res2.get("idempotent_duplicate") is True
        assert fake_erp_client.sync_invoice.call_count == 1
        assert mock_pub.call_count == 1


@pytest.mark.asyncio
async def test_billing_consumer_handles_domain_failure(
    fake_redis,
    fake_consumer_manager,
    fake_erp_client,
):
    fake_erp_client.sync_invoice.side_effect = RuntimeError("ERP service unavailable")

    consumer = BillingConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        erp_client=fake_erp_client,
    )

    event_id = "evt_billing_fail_1"
    payload = {
        "event_type": "invoice",
        "event_id": event_id,
        "job_id": "job_301",
        "tenant_id": "tenant-1",
        "invoice_id": "INV-301",
        "amount": 500.0,
        "currency": "USD",
        "schema_version": 1,
    }

    res = await consumer.process_event(payload, attempt=2)
    assert res["status"] == "FAILED"
    assert res["consumer"] == "billing"
    assert res["attempt"] == 2
    assert "ERP service unavailable" in res["error"]
    # Redis idempotency marker must NOT be set on failure
    assert fake_redis.get(f"billing:event_processed:{event_id}") is None


@pytest.mark.asyncio
async def test_billing_consumer_retry_after_failure(
    fake_redis,
    fake_consumer_manager,
    fake_erp_client,
):
    consumer = BillingConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        erp_client=fake_erp_client,
    )

    event_id = "evt_billing_retry_1"
    payload = {
        "event_type": "invoice",
        "event_id": event_id,
        "job_id": "job_302",
        "tenant_id": "tenant-1",
        "invoice_id": "INV-302",
        "amount": 350.0,
        "currency": "USD",
        "schema_version": 1,
    }

    # First attempt fails
    fake_erp_client.sync_invoice.side_effect = ConnectionError("ERP timeout")
    res1 = await consumer.process_event(payload, attempt=1)
    assert res1["status"] == "FAILED"
    assert res1["attempt"] == 1

    # Second attempt succeeds
    fake_erp_client.sync_invoice.side_effect = None
    with patch("app.services.billing_consumer.publish_invoice_event"):
        res2 = await consumer.process_event(payload, attempt=2)
        assert res2["status"] == "PROCESSED"
        assert res2["attempt"] == 2
        assert fake_redis.get(f"billing:event_processed:{event_id}") == "1"


@pytest.mark.asyncio
async def test_billing_consumer_supports_message_envelope(
    fake_redis,
    fake_consumer_manager,
    fake_erp_client,
):
    consumer = BillingConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        erp_client=fake_erp_client,
    )

    event_id = "evt_envelope_billing_1"
    envelope = MessageEnvelope(
        sender=AgentAddress(
            agent_type="closure",
            agent_id="billing-service-1",
            tenant_id="tenant-env",
        ),
        recipient=None,
        message_type=MessageType.EVENT,
        payload={
            "event_type": "invoice",
            "event_id": event_id,
            "job_id": "job_401",
            "tenant_id": "tenant-env",
            "invoice_id": "INV-ENV-1",
            "amount": 120.0,
            "currency": "USD",
            "schema_version": 1,
        },
        correlation_id="corr-envelope-1",
        topic="fieldops.billing.events",
    )

    with patch("app.services.billing_consumer.publish_invoice_event"):
        res = await consumer.process_event(envelope)
        assert res["status"] == "PROCESSED"
        assert res["consumer"] == "billing"
        assert res["event_id"] == event_id


@pytest.mark.asyncio
async def test_billing_consumer_supports_invoice_event_message(
    fake_redis,
    fake_consumer_manager,
    fake_erp_client,
):
    consumer = BillingConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        erp_client=fake_erp_client,
    )

    event_id = "evt_invoice_msg_1"
    invoice_msg = InvoiceEventMessage(
        sender=AgentAddress(
            agent_type="closure",
            agent_id="billing-service-1",
            tenant_id="tenant-msg",
        ),
        payload={
            "event_type": "invoice",
            "event_id": event_id,
            "job_id": "job_501",
            "tenant_id": "tenant-msg",
            "invoice_id": "INV-MSG-1",
            "amount": 420.0,
            "currency": "USD",
            "schema_version": 1,
        },
        correlation_id="corr-inv-msg-1",
        topic="fieldops.billing.events",
    )

    with patch("app.services.billing_consumer.publish_invoice_event"):
        res = await consumer.process_event(invoice_msg)
        assert res["status"] == "PROCESSED"
        assert res["consumer"] == "billing"
        assert res["event_id"] == event_id


@pytest.mark.asyncio
async def test_billing_consumer_async_context_manager(
    fake_redis,
    fake_consumer_manager,
):
    consumer = BillingConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )

    async with consumer as c:
        assert c is consumer
        fake_consumer_manager.start.assert_awaited_once()

    fake_consumer_manager.stop.assert_awaited_once()


def test_billing_consumer_aliases():
    assert InvoiceConsumer is BillingConsumer
    assert BillingEventConsumer is BillingConsumer


def test_process_billing_event_once_task_integration(fake_redis):
    event_id = "evt_celery_task_1"
    payload = {
        "event_type": "invoice",
        "event_id": event_id,
        "job_id": "job_celery_1",
        "tenant_id": "tenant-1",
        "invoice_id": "INV-CELERY-1",
        "amount": 99.99,
        "currency": "USD",
        "schema_version": 1,
    }

    with patch("app.services.billing_consumer.publish_invoice_event"):
        res = _process_billing_event_once(
            redis=fake_redis,
            event_payload=payload,
            attempt=1,
        )
        assert res["status"] == "PROCESSED"
        assert res["consumer"] == "billing"
        assert res["event_id"] == event_id
        assert fake_redis.get(f"billing:event_processed:{event_id}") == "1"

        # Celery task wrapper
        with patch("app.tasks.get_redis_client", return_value=fake_redis):
            task_res = process_billing_event_task(event_payload=payload, attempt=1)
            assert task_res["status"] == "PROCESSED"
            assert task_res["consumer"] == "billing"
