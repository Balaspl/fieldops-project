from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.services.payment_consumer import (
    ConsumeReceipt,
    PaymentConsumer,
    PaymentEventConsumer,
    PaymentStatusConsumer,
)
from app.services.ai.FieldOpsAI.schemas.agent_messages import (
    AgentAddress,
    MessageEnvelope,
    MessageType,
    PaymentEventMessage,
)
from app.tasks import (
    _process_payment_event_once,
    process_payment_event_task,
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
def fake_accounting_client():
    client = MagicMock()
    client.sync_payment = MagicMock()
    return client


def test_consume_receipt_behavior():
    success_receipt = ConsumeReceipt(
        {"status": "PROCESSED", "consumer": "payment", "event_id": "evt_1", "attempt": 1}
    )
    assert success_receipt.is_success is True
    assert bool(success_receipt) is True
    assert success_receipt["consumer"] == "payment"

    failed_receipt = ConsumeReceipt(
        {"status": "FAILED", "consumer": "payment", "event_id": "evt_2", "attempt": 1, "error": "test"}
    )
    assert failed_receipt.is_success is False
    assert bool(failed_receipt) is False


@pytest.mark.parametrize(
    "event_type",
    [
        "payment",
        "PAYMENT",
        "payment_initiated",
        "PAYMENT_SUCCESS",
        "payment_successful",
        "payment_failed",
        "payment_pending",
        "payment_refunded",
        "payment_refund",
        "payment_completed",
        "payment_cancelled",
    ],
)
@pytest.mark.asyncio
async def test_payment_consumer_primary_success_path(
    event_type,
    fake_redis,
    fake_consumer_manager,
    fake_accounting_client,
):
    consumer = PaymentConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        accounting_client=fake_accounting_client,
    )

    event_id = f"evt_pay_{event_type.lower()}_101"
    payload = {
        "event_type": event_type,
        "event_id": event_id,
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "payment_id": "pay_txn_001",
        "amount": 150.50,
        "currency": "USD",
        "payment_status": "SUCCESSFUL",
        "schema_version": 1,
    }

    with patch("app.services.payment_consumer.publish_payment_event") as mock_pub:
        receipt = await consumer.process_event(payload, attempt=1)

        assert isinstance(receipt, ConsumeReceipt)
        assert receipt.is_success is True
        assert bool(receipt) is True
        assert receipt["status"] == "PROCESSED"
        assert receipt["consumer"] == "payment"
        assert receipt["event_id"] == event_id
        assert receipt["attempt"] == 1

        # Check accounting sync and event publish
        fake_accounting_client.sync_payment.assert_called_once_with(
            payment_id="pay_txn_001",
            job_id="job_101",
            tenant_id="tenant-1",
            amount=150.50,
            currency="USD",
            status="SUCCESSFUL",
            payload=payload,
        )
        mock_pub.assert_called_once()
        assert fake_redis.get(f"payment:event_processed:{event_id}") == "1"
        assert fake_redis.get("payment:txn_processed:pay_txn_001") == "1"


@pytest.mark.asyncio
async def test_payment_consumer_async_accounting_client(
    fake_redis,
    fake_consumer_manager,
):
    async_accounting = MagicMock()
    async_accounting.sync_payment = AsyncMock()

    consumer = PaymentConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        accounting_client=async_accounting,
    )

    event_id = "evt_async_pay_001"
    payload = {
        "event_type": "payment",
        "event_id": event_id,
        "job_id": "job_102",
        "tenant_id": "tenant-1",
        "payment_id": "pay_txn_002",
        "amount": 200.0,
        "currency": "EUR",
        "schema_version": 1,
    }

    with patch("app.services.payment_consumer.publish_payment_event"):
        receipt = await consumer.process_event(payload, attempt=1)
        assert receipt["status"] == "PROCESSED"
        async_accounting.sync_payment.assert_awaited_once()


@pytest.mark.asyncio
async def test_payment_consumer_validates_transaction_identity(
    fake_redis,
    fake_consumer_manager,
    fake_accounting_client,
):
    consumer = PaymentConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        accounting_client=fake_accounting_client,
    )

    # 1. Missing transaction / payment identifier
    missing_txn_payload = {
        "event_type": "payment",
        "event_id": "evt_missing_txn",
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "amount": 50.0,
        "currency": "USD",
        "schema_version": 1,
    }
    res1 = await consumer.process_event(missing_txn_payload)
    assert res1["status"] == "FAILED"
    assert res1["consumer"] == "payment"
    assert "transaction/payment identifier" in res1["error"].lower()

    # 2. Whitespace-only transaction / payment identifier
    blank_txn_payload = {
        "event_type": "payment",
        "event_id": "evt_blank_txn",
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "payment_id": "   ",
        "amount": 50.0,
        "currency": "USD",
        "schema_version": 1,
    }
    res2 = await consumer.process_event(blank_txn_payload)
    assert res2["status"] == "FAILED"
    assert res2["consumer"] == "payment"
    assert "transaction/payment identifier" in res2["error"].lower()


@pytest.mark.asyncio
async def test_payment_consumer_validates_financial_state(
    fake_redis,
    fake_consumer_manager,
    fake_accounting_client,
):
    consumer = PaymentConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        accounting_client=fake_accounting_client,
    )

    # 1. Negative amount
    neg_amount_payload = {
        "event_type": "payment",
        "event_id": "evt_neg_amount",
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "payment_id": "pay_001",
        "amount": -25.0,
        "currency": "USD",
        "schema_version": 1,
    }
    res1 = await consumer.process_event(neg_amount_payload)
    assert res1["status"] == "FAILED"
    assert "cannot be negative" in res1["error"].lower()

    # 2. Non-numeric boolean amount
    bool_amount_payload = {
        "event_type": "payment",
        "event_id": "evt_bool_amount",
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "payment_id": "pay_001",
        "amount": False,
        "currency": "USD",
        "schema_version": 1,
    }
    res2 = await consumer.process_event(bool_amount_payload)
    assert res2["status"] == "FAILED"
    assert "must be a numeric value" in res2["error"].lower()

    # 3. Invalid currency format
    bad_currency_payload = {
        "event_type": "payment",
        "event_id": "evt_bad_curr",
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "payment_id": "pay_001",
        "amount": 100.0,
        "currency": "US-DOLLARS",
        "schema_version": 1,
    }
    res3 = await consumer.process_event(bad_currency_payload)
    assert res3["status"] == "FAILED"
    assert "invalid currency code" in res3["error"].lower()

    # 4. Invalid payment status
    bad_status_payload = {
        "event_type": "payment",
        "event_id": "evt_bad_status",
        "job_id": "job_101",
        "tenant_id": "tenant-1",
        "payment_id": "pay_001",
        "amount": 100.0,
        "currency": "USD",
        "payment_status": "SUPER_PAID",
        "schema_version": 1,
    }
    res4 = await consumer.process_event(bad_status_payload)
    assert res4["status"] == "FAILED"
    assert "invalid payment status" in res4["error"].lower()


@pytest.mark.asyncio
async def test_payment_consumer_db_session_factory_integration(
    fake_redis,
    fake_consumer_manager,
    fake_accounting_client,
):
    # Test DB tenant mismatch check
    mock_db = MagicMock()
    mock_payment_status = MagicMock()
    mock_payment_status.tenant_id = "tenant-other"
    mock_db.query.return_value.filter.return_value.first.return_value = mock_payment_status

    mock_session_factory = MagicMock(return_value=mock_db)

    consumer = PaymentConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        accounting_client=fake_accounting_client,
        db_session_factory=mock_session_factory,
    )

    payload = {
        "event_type": "payment",
        "event_id": "evt_tenant_mismatch",
        "job_id": 888,
        "tenant_id": "tenant-expected",
        "payment_id": "pay_001",
        "amount": 100.0,
        "currency": "USD",
        "schema_version": 1,
    }

    res = await consumer.process_event(payload)
    assert res["status"] == "FAILED"
    assert "tenant mismatch" in res["error"].lower()
    mock_db.close.assert_called_once()

    # Test DB status update when matching
    mock_db_valid = MagicMock()
    mock_valid_status = MagicMock()
    mock_valid_status.tenant_id = "tenant-expected"
    mock_db_valid.query.return_value.filter.return_value.first.return_value = mock_valid_status
    mock_session_factory_valid = MagicMock(return_value=mock_db_valid)

    consumer_valid = PaymentConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        accounting_client=fake_accounting_client,
        db_session_factory=mock_session_factory_valid,
    )

    with patch("app.services.payment_consumer.publish_payment_event"):
        res_valid = await consumer_valid.process_event(payload)
        assert res_valid["status"] == "PROCESSED"
        assert mock_valid_status.status == "SUCCESSFUL"
        mock_db_valid.commit.assert_called_once()


@pytest.mark.asyncio
async def test_payment_consumer_schema_validation_missing_fields(
    fake_redis,
    fake_consumer_manager,
):
    consumer = PaymentConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )

    res = await consumer.process_event({})
    assert res["status"] == "FAILED"
    assert res["consumer"] == "payment"
    assert "Missing required fields" in res["error"]


@pytest.mark.asyncio
async def test_payment_consumer_unauthorized_topic_rejection(
    fake_redis,
    fake_consumer_manager,
):
    consumer = PaymentConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )

    msg = {
        "topic": "fieldops.unauthorized.events",
        "payload": {
            "event_type": "payment",
            "event_id": "evt_unauth_topic",
            "job_id": "job_1",
            "tenant_id": "tenant-1",
            "payment_id": "pay_1",
            "schema_version": 1,
        },
    }

    res = await consumer.process_event(msg)
    assert res["status"] == "FAILED"
    assert "is not authorized" in res["error"]


@pytest.mark.asyncio
async def test_payment_consumer_invalid_event_type_rejection(
    fake_redis,
    fake_consumer_manager,
):
    consumer = PaymentConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )

    payload = {
        "event_type": "unknown_payment_event",
        "event_id": "evt_invalid_type",
        "job_id": "job_1",
        "tenant_id": "tenant-1",
        "payment_id": "pay_1",
        "schema_version": 1,
    }

    res = await consumer.process_event(payload)
    assert res["status"] == "FAILED"
    assert "Invalid event_type" in res["error"]


@pytest.mark.asyncio
async def test_payment_consumer_sensitive_forbidden_keys_rejection(
    fake_redis,
    fake_consumer_manager,
):
    consumer = PaymentConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )

    payload = {
        "event_type": "payment",
        "event_id": "evt_secrets",
        "job_id": "job_1",
        "tenant_id": "tenant-1",
        "payment_id": "pay_1",
        "schema_version": 1,
        "password": "super_secret_password",
    }

    res = await consumer.process_event(payload)
    assert res["status"] == "FAILED"
    assert "Payload contains forbidden sensitive keys" in res["error"]


@pytest.mark.asyncio
async def test_payment_consumer_idempotency_prevents_duplicate_processing(
    fake_redis,
    fake_consumer_manager,
    fake_accounting_client,
):
    consumer = PaymentConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        accounting_client=fake_accounting_client,
    )

    event_id = "evt_payment_idempotent_1"
    txn_id = "pay_txn_idempotent_1"
    payload = {
        "event_type": "payment",
        "event_id": event_id,
        "job_id": "job_201",
        "tenant_id": "tenant-1",
        "payment_id": txn_id,
        "amount": 80.0,
        "currency": "USD",
        "schema_version": 1,
    }

    with patch("app.services.payment_consumer.publish_payment_event") as mock_pub:
        # First processing -> success
        res1 = await consumer.process_event(payload)
        assert res1["status"] == "PROCESSED"
        assert res1.get("idempotent_duplicate") is not True
        assert fake_accounting_client.sync_payment.call_count == 1
        assert mock_pub.call_count == 1

        # Second processing with same event_id -> idempotent duplicate detected
        res2 = await consumer.process_event(payload)
        assert res2["status"] == "PROCESSED"
        assert res2.get("idempotent_duplicate") is True
        assert fake_accounting_client.sync_payment.call_count == 1
        assert mock_pub.call_count == 1

        # Third processing with same transaction_id but new event_id -> prevents duplicate financial processing
        payload3 = dict(payload)
        payload3["event_id"] = "evt_payment_idempotent_2"
        res3 = await consumer.process_event(payload3)
        assert res3["status"] == "PROCESSED"
        assert res3.get("idempotent_duplicate") is True
        assert fake_accounting_client.sync_payment.call_count == 1
        assert mock_pub.call_count == 1


@pytest.mark.asyncio
async def test_payment_consumer_handles_accounting_failure(
    fake_redis,
    fake_consumer_manager,
    fake_accounting_client,
):
    fake_accounting_client.sync_payment.side_effect = RuntimeError("Accounting system timeout")

    consumer = PaymentConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        accounting_client=fake_accounting_client,
    )

    event_id = "evt_payment_fail_1"
    payload = {
        "event_type": "payment",
        "event_id": event_id,
        "job_id": "job_301",
        "tenant_id": "tenant-1",
        "payment_id": "pay_301",
        "amount": 250.0,
        "currency": "USD",
        "schema_version": 1,
    }

    res = await consumer.process_event(payload, attempt=2)
    assert res["status"] == "FAILED"
    assert res["consumer"] == "payment"
    assert res["attempt"] == 2
    assert "Accounting system timeout" in res["error"]
    # Redis idempotency marker must NOT be set on failure
    assert fake_redis.get(f"payment:event_processed:{event_id}") is None


@pytest.mark.asyncio
async def test_payment_consumer_retry_after_failure(
    fake_redis,
    fake_consumer_manager,
    fake_accounting_client,
):
    consumer = PaymentConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        accounting_client=fake_accounting_client,
    )

    event_id = "evt_payment_retry_1"
    payload = {
        "event_type": "payment",
        "event_id": event_id,
        "job_id": "job_302",
        "tenant_id": "tenant-1",
        "payment_id": "pay_302",
        "amount": 175.0,
        "currency": "USD",
        "schema_version": 1,
    }

    # First attempt fails
    fake_accounting_client.sync_payment.side_effect = ConnectionError("Network drop")
    res1 = await consumer.process_event(payload, attempt=1)
    assert res1["status"] == "FAILED"
    assert res1["attempt"] == 1

    # Second attempt succeeds
    fake_accounting_client.sync_payment.side_effect = None
    with patch("app.services.payment_consumer.publish_payment_event"):
        res2 = await consumer.process_event(payload, attempt=2)
        assert res2["status"] == "PROCESSED"
        assert res2["attempt"] == 2
        assert fake_redis.get(f"payment:event_processed:{event_id}") == "1"


@pytest.mark.asyncio
async def test_payment_consumer_supports_message_envelope(
    fake_redis,
    fake_consumer_manager,
    fake_accounting_client,
):
    consumer = PaymentConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        accounting_client=fake_accounting_client,
    )

    event_id = "evt_envelope_pay_1"
    envelope = MessageEnvelope(
        sender=AgentAddress(
            agent_type="closure",
            agent_id="payment-service-1",
            tenant_id="tenant-env",
        ),
        recipient=None,
        message_type=MessageType.EVENT,
        payload={
            "event_type": "payment",
            "event_id": event_id,
            "job_id": "job_401",
            "tenant_id": "tenant-env",
            "payment_id": "pay_env_1",
            "amount": 120.0,
            "currency": "USD",
            "schema_version": 1,
        },
        correlation_id="corr-envelope-1",
        topic="fieldops.payment.events",
    )

    with patch("app.services.payment_consumer.publish_payment_event"):
        res = await consumer.process_event(envelope)
        assert res["status"] == "PROCESSED"
        assert res["consumer"] == "payment"
        assert res["event_id"] == event_id


@pytest.mark.asyncio
async def test_payment_consumer_supports_payment_event_message(
    fake_redis,
    fake_consumer_manager,
    fake_accounting_client,
):
    consumer = PaymentConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
        accounting_client=fake_accounting_client,
    )

    event_id = "evt_payment_msg_1"
    pay_msg = PaymentEventMessage(
        sender=AgentAddress(
            agent_type="closure",
            agent_id="payment-service-1",
            tenant_id="tenant-msg",
        ),
        payload={
            "event_type": "payment",
            "event_id": event_id,
            "job_id": "job_501",
            "tenant_id": "tenant-msg",
            "payment_id": "pay_msg_1",
            "amount": 320.0,
            "currency": "USD",
            "schema_version": 1,
        },
        correlation_id="corr-pay-msg-1",
        topic="fieldops.payment.events",
    )

    with patch("app.services.payment_consumer.publish_payment_event"):
        res = await consumer.process_event(pay_msg)
        assert res["status"] == "PROCESSED"
        assert res["consumer"] == "payment"
        assert res["event_id"] == event_id


@pytest.mark.asyncio
async def test_payment_consumer_async_context_manager(
    fake_redis,
    fake_consumer_manager,
):
    consumer = PaymentConsumer(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )

    async with consumer as c:
        assert c is consumer
        fake_consumer_manager.start.assert_awaited_once()

    fake_consumer_manager.stop.assert_awaited_once()


def test_payment_consumer_aliases():
    assert PaymentEventConsumer is PaymentConsumer
    assert PaymentStatusConsumer is PaymentConsumer


def test_process_payment_event_once_task_integration(fake_redis):
    event_id = "evt_celery_pay_1"
    payload = {
        "event_type": "payment",
        "event_id": event_id,
        "job_id": "job_celery_1",
        "tenant_id": "tenant-1",
        "payment_id": "pay_celery_1",
        "amount": 89.95,
        "currency": "USD",
        "schema_version": 1,
    }

    with patch("app.services.payment_consumer.publish_payment_event"):
        res = _process_payment_event_once(
            redis=fake_redis,
            event_payload=payload,
            attempt=1,
        )
        assert res["status"] == "PROCESSED"
        assert res["consumer"] == "payment"
        assert res["event_id"] == event_id
        assert fake_redis.get(f"payment:event_processed:{event_id}") == "1"

        # Celery task wrapper
        with patch("app.tasks.get_redis_client", return_value=fake_redis):
            task_res = process_payment_event_task(event_payload=payload, attempt=1)
            assert task_res["status"] == "PROCESSED"
            assert task_res["consumer"] == "payment"

