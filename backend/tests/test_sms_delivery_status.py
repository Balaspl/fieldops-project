from app.services.sms.delivery_status import (
    SMSDeliveryStatusService,
)
import pytest


def test_normalize_status():
    service = SMSDeliveryStatusService(None)

    assert service.normalize_status("sent") == "sent"
    assert service.normalize_status("DELIVERED") == "delivered"
    assert service.normalize_status(" failed ") == "failed"
from app.services.sms.delivery_status import SMSDeliveryStatusService

def test_invalid_status():
    service = SMSDeliveryStatusService(None)

    with pytest.raises(ValueError):
        service.normalize_status("unknown")


def test_process_webhook_missing_sid():
    service = SMSDeliveryStatusService(None)

    with pytest.raises(
        ValueError,
        match="missing MessageSid",
    ):
        service.process_webhook(
            {
                "MessageStatus": "delivered",
            }
        )


def test_process_webhook_missing_status():
    service = SMSDeliveryStatusService(None)

    with pytest.raises(
        ValueError,
        match="missing MessageStatus",
    ):
        service.process_webhook(
            {
                "MessageSid": "SM123456",
            }
        )


def test_get_delivery():
    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return "delivery"

    class FakeDB:
        def query(self, model):
            return FakeQuery()

    service = SMSDeliveryStatusService(FakeDB())

    result = service.get_delivery("SM123456")

    assert result == "delivery"

def test_update_delivery_status_delivery_not_found():
    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return None

    class FakeDB:
        def query(self, model):
            return FakeQuery()

    service = SMSDeliveryStatusService(FakeDB())

    result = service.update_delivery_status(
        message_sid="SM123456",
        message_status="delivered",
        payload={
            "MessageSid": "SM123456",
            "MessageStatus": "delivered",
        },
    )

    assert result is None


def test_process_webhook_supports_sms_sid():
    service = SMSDeliveryStatusService(None)

    with pytest.raises(
        AttributeError,
    ):
        service.process_webhook(
            {
                "SmsSid": "SM123456",
                "SmsStatus": "delivered",
            }
        )


@pytest.mark.parametrize(
    "status",
    [
        "queued",
        "sending",
        "sent",
        "delivered",
        "undelivered",
        "failed",
    ],
)


def test_all_valid_statuses(status):
    service = SMSDeliveryStatusService(None)

    assert service.normalize_status(status) == status


def test_sent_status_sets_sent_at():
    from datetime import datetime, timezone

    class FakeDelivery:
        sms_sid = "SM123456"
        status_history = []
        status = None
        sent_at = None
        delivered_at = None
        delivery_latency_ms = None
        last_webhook_at = None
        webhook_payload = None
        error_message = None
        cost = None

    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return FakeDelivery()

    class FakeDB:
        def query(self, model):
            return FakeQuery()

        def commit(self):
            pass

        def refresh(self, obj):
            pass

    service = SMSDeliveryStatusService(FakeDB())

    delivery = service.update_delivery_status(
        message_sid="SM123456",
        message_status="sent",
        payload={
            "MessageSid": "SM123456",
            "MessageStatus": "sent",
        },
    )

    assert delivery.status == "sent"
    assert delivery.sent_at is not None


def test_delivered_status_sets_delivered_at():
    class FakeDelivery:
        sms_sid = "SM123456"
        status_history = []
        status = None
        sent_at = None
        delivered_at = None
        delivery_latency_ms = None
        last_webhook_at = None
        webhook_payload = None
        error_message = None
        cost = None

    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return FakeDelivery()

    class FakeDB:
        def query(self, model):
            return FakeQuery()

        def commit(self):
            pass

        def refresh(self, obj):
            pass

    service = SMSDeliveryStatusService(FakeDB())

    delivery = service.update_delivery_status(
        message_sid="SM123456",
        message_status="delivered",
        payload={
            "MessageSid": "SM123456",
            "MessageStatus": "delivered",
        },
    )

    assert delivery.status == "delivered"
    assert delivery.delivered_at is not None


def test_delivery_latency_is_calculated():
    from datetime import datetime, timedelta, timezone

    sent_time = datetime.now(timezone.utc) - timedelta(
        seconds=2
    )

    class FakeDelivery:
        sms_sid = "SM123456"
        status_history = []
        status = "sent"
        sent_at = sent_time
        delivered_at = None
        delivery_latency_ms = None
        last_webhook_at = None
        webhook_payload = None
        error_message = None
        cost = None

    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return FakeDelivery()

    class FakeDB:
        def query(self, model):
            return FakeQuery()

        def commit(self):
            pass

        def refresh(self, obj):
            pass

    service = SMSDeliveryStatusService(FakeDB())

    delivery = service.update_delivery_status(
        message_sid="SM123456",
        message_status="delivered",
        payload={
            "MessageSid": "SM123456",
            "MessageStatus": "delivered",
        },
    )

    assert delivery.delivery_latency_ms is not None
    assert delivery.delivery_latency_ms >= 1900


def test_error_code_is_stored():
    class FakeDelivery:
        sms_sid = "SM123456"
        status_history = []
        status = None
        sent_at = None
        delivered_at = None
        delivery_latency_ms = None
        last_webhook_at = None
        webhook_payload = None
        error_message = None
        cost = None

    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return FakeDelivery()

    class FakeDB:
        def query(self, model):
            return FakeQuery()

        def commit(self):
            pass

        def refresh(self, obj):
            pass

    service = SMSDeliveryStatusService(FakeDB())

    delivery = service.update_delivery_status(
        message_sid="SM123456",
        message_status="failed",
        payload={
            "MessageSid": "SM123456",
            "MessageStatus": "failed",
            "ErrorCode": "30003",
        },
    )

    assert delivery.error_message == (
        "Twilio ErrorCode: 30003"
    )


def test_twilio_price_is_stored_as_positive_cost():
    class FakeDelivery:
        sms_sid = "SM123456"
        status_history = []
        status = None
        sent_at = None
        delivered_at = None
        delivery_latency_ms = None
        last_webhook_at = None
        webhook_payload = None
        error_message = None
        cost = None

    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return FakeDelivery()

    class FakeDB:
        def query(self, model):
            return FakeQuery()

        def commit(self):
            pass

        def refresh(self, obj):
            pass

    service = SMSDeliveryStatusService(FakeDB())

    delivery = service.update_delivery_status(
        message_sid="SM123456",
        message_status="sent",
        payload={
            "MessageSid": "SM123456",
            "MessageStatus": "sent",
            "Price": "-0.0075",
        },
    )

    assert delivery.cost == 0.0075


def test_error_message_is_stored():
    class FakeDelivery:
        sms_sid = "SM123456"
        status_history = []
        status = None
        sent_at = None
        delivered_at = None
        delivery_latency_ms = None
        last_webhook_at = None
        webhook_payload = None
        error_message = None
        cost = None

    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return FakeDelivery()

    class FakeDB:
        def query(self, model):
            return FakeQuery()

        def commit(self):
            pass

        def refresh(self, obj):
            pass

    service = SMSDeliveryStatusService(FakeDB())

    delivery = service.update_delivery_status(
        message_sid="SM123456",
        message_status="failed",
        payload={
            "MessageSid": "SM123456",
            "MessageStatus": "failed",
            "ErrorMessage": "Message delivery failed",
        },
    )

    assert delivery.error_message == "Message delivery failed"

def test_webhook_payload_is_stored():
    class FakeDelivery:
        sms_sid = "SM123456"
        status_history = []
        status = None
        sent_at = None
        delivered_at = None
        delivery_latency_ms = None
        last_webhook_at = None
        webhook_payload = None
        error_message = None
        cost = None

    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return FakeDelivery()

    class FakeDB:
        def query(self, model):
            return FakeQuery()

        def commit(self):
            pass

        def refresh(self, obj):
            pass

    service = SMSDeliveryStatusService(FakeDB())

    payload = {
        "MessageSid": "SM123456",
        "MessageStatus": "delivered",
        "To": "+919999999999",
    }

    delivery = service.update_delivery_status(
        message_sid="SM123456",
        message_status="delivered",
        payload=payload,
    )

    assert delivery.webhook_payload == payload


def test_last_webhook_at_is_updated():
    class FakeDelivery:
        sms_sid = "SM123456"
        status_history = []
        status = None
        sent_at = None
        delivered_at = None
        delivery_latency_ms = None
        last_webhook_at = None
        webhook_payload = None
        error_message = None
        cost = None

    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return FakeDelivery()

    class FakeDB:
        def query(self, model):
            return FakeQuery()

        def commit(self):
            pass

        def refresh(self, obj):
            pass

    service = SMSDeliveryStatusService(FakeDB())

    delivery = service.update_delivery_status(
        message_sid="SM123456",
        message_status="sent",
        payload={
            "MessageSid": "SM123456",
            "MessageStatus": "sent",
        },
    )

    assert delivery.last_webhook_at is not None


def test_status_history_is_created():
    class FakeDelivery:
        sms_sid = "SM123456"
        status_history = []
        status = None
        sent_at = None
        delivered_at = None
        delivery_latency_ms = None
        last_webhook_at = None
        webhook_payload = None
        error_message = None
        cost = None

    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return FakeDelivery()

    class FakeDB:
        def query(self, model):
            return FakeQuery()

        def commit(self):
            pass

        def refresh(self, obj):
            pass

    service = SMSDeliveryStatusService(FakeDB())

    delivery = service.update_delivery_status(
        message_sid="SM123456",
        message_status="sent",
        payload={
            "MessageSid": "SM123456",
            "MessageStatus": "sent",
        },
    )

    assert len(delivery.status_history) == 1
    assert delivery.status_history[0]["status"] == "sent"
    assert "timestamp" in delivery.status_history[0]

def test_duplicate_status_is_not_added_to_history():
    class FakeDelivery:
        sms_sid = "SM123456"
        status_history = [
            {
                "status": "sent",
                "timestamp": "2026-09-09T10:00:00+00:00",
            }
        ]
        status = "sent"
        sent_at = None
        delivered_at = None
        delivery_latency_ms = None
        last_webhook_at = None
        webhook_payload = None
        error_message = None
        cost = None

    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return FakeDelivery()

    class FakeDB:
        def query(self, model):
            return FakeQuery()

        def commit(self):
            pass

        def refresh(self, obj):
            pass

    service = SMSDeliveryStatusService(FakeDB())

    delivery = service.update_delivery_status(
        message_sid="SM123456",
        message_status="sent",
        payload={
            "MessageSid": "SM123456",
            "MessageStatus": "sent",
        },
    )

    assert len(delivery.status_history) == 1


def test_status_progression_is_recorded():
    class FakeDelivery:
        sms_sid = "SM123456"
        status_history = []
        status = None
        sent_at = None
        delivered_at = None
        delivery_latency_ms = None
        last_webhook_at = None
        webhook_payload = None
        error_message = None
        cost = None

    delivery = FakeDelivery()

    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return delivery

    class FakeDB:
        def query(self, model):
            return FakeQuery()

        def commit(self):
            pass

        def refresh(self, obj):
            pass

    service = SMSDeliveryStatusService(FakeDB())

    service.update_delivery_status(
        "SM123456",
        "sent",
        {
            "MessageSid": "SM123456",
            "MessageStatus": "sent",
        },
    )

    service.update_delivery_status(
        "SM123456",
        "delivered",
        {
            "MessageSid": "SM123456",
            "MessageStatus": "delivered",
        },
    )

    assert [
        item["status"]
        for item in delivery.status_history
    ] == ["sent", "delivered"]


def test_zero_twilio_price():
    class FakeDelivery:
        sms_sid = "SM123456"
        status_history = []
        status = None
        sent_at = None
        delivered_at = None
        delivery_latency_ms = None
        last_webhook_at = None
        webhook_payload = None
        error_message = None
        cost = None

    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return FakeDelivery()

    class FakeDB:
        def query(self, model):
            return FakeQuery()

        def commit(self):
            pass

        def refresh(self, obj):
            pass

    service = SMSDeliveryStatusService(FakeDB())

    delivery = service.update_delivery_status(
        "SM123456",
        "sent",
        {
            "MessageSid": "SM123456",
            "MessageStatus": "sent",
            "Price": "0",
        },
    )

    assert delivery.cost == 0.0


def test_invalid_twilio_price_does_not_crash():
    class FakeDelivery:
        sms_sid = "SM123456"
        status_history = []
        status = None
        sent_at = None
        delivered_at = None
        delivery_latency_ms = None
        last_webhook_at = None
        webhook_payload = None
        error_message = None
        cost = None

    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return FakeDelivery()

    class FakeDB:
        def query(self, model):
            return FakeQuery()

        def commit(self):
            pass

        def refresh(self, obj):
            pass

    service = SMSDeliveryStatusService(FakeDB())

    delivery = service.update_delivery_status(
        "SM123456",
        "sent",
        {
            "MessageSid": "SM123456",
            "MessageStatus": "sent",
            "Price": "invalid",
        },
    )

    assert delivery.cost is None


def test_undelivered_status_is_saved():
    class FakeDelivery:
        sms_sid = "SM123456"
        status_history = []
        status = None
        sent_at = None
        delivered_at = None
        delivery_latency_ms = None
        last_webhook_at = None
        webhook_payload = None
        error_message = None
        cost = None

    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return FakeDelivery()

    class FakeDB:
        def query(self, model):
            return FakeQuery()

        def commit(self):
            pass

        def refresh(self, obj):
            pass

    service = SMSDeliveryStatusService(FakeDB())

    delivery = service.update_delivery_status(
        "SM123456",
        "undelivered",
        {
            "MessageSid": "SM123456",
            "MessageStatus": "undelivered",
            "ErrorCode": "30003",
        },
    )

    assert delivery.status == "undelivered"
    assert delivery.error_message == (
        "Twilio ErrorCode: 30003"
    )


def test_process_webhook_with_message_sid():
    class FakeDelivery:
        sms_sid = "SM123456"
        status_history = []
        status = None
        sent_at = None
        delivered_at = None
        delivery_latency_ms = None
        last_webhook_at = None
        webhook_payload = None
        error_message = None
        cost = None

    delivery = FakeDelivery()

    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return delivery

    class FakeDB:
        def query(self, model):
            return FakeQuery()

        def commit(self):
            pass

        def refresh(self, obj):
            pass

    service = SMSDeliveryStatusService(FakeDB())

    result = service.process_webhook(
        {
            "MessageSid": "SM123456",
            "MessageStatus": "delivered",
        }
    )

    assert result is delivery
    assert result.status == "delivered"

def test_process_webhook_with_sms_sid():
    class FakeDelivery:
        sms_sid = "SM123456"
        status_history = []
        status = None
        sent_at = None
        delivered_at = None
        delivery_latency_ms = None
        last_webhook_at = None
        webhook_payload = None
        error_message = None
        cost = None

    delivery = FakeDelivery()

    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return delivery

    class FakeDB:
        def query(self, model):
            return FakeQuery()

        def commit(self):
            pass

        def refresh(self, obj):
            pass

    service = SMSDeliveryStatusService(FakeDB())

    result = service.process_webhook(
        {
            "SmsSid": "SM123456",
            "SmsStatus": "sent",
        }
    )

    assert result is delivery
    assert result.status == "sent"


def test_process_webhook_creates_history():
    class FakeDelivery:
        sms_sid = "SM123456"
        status_history = []
        status = None
        sent_at = None
        delivered_at = None
        delivery_latency_ms = None
        last_webhook_at = None
        webhook_payload = None
        error_message = None
        cost = None

    delivery = FakeDelivery()

    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return delivery

    class FakeDB:
        def query(self, model):
            return FakeQuery()

        def commit(self):
            pass

        def refresh(self, obj):
            pass

    service = SMSDeliveryStatusService(FakeDB())

    service.process_webhook(
        {
            "MessageSid": "SM123456",
            "MessageStatus": "sent",
        }
    )

    assert len(delivery.status_history) == 1
    assert delivery.status_history[0]["status"] == "sent"


def test_duplicate_webhook_does_not_duplicate_history():
    class FakeDelivery:
        sms_sid = "SM123456"
        status_history = []
        status = None
        sent_at = None
        delivered_at = None
        delivery_latency_ms = None
        last_webhook_at = None
        webhook_payload = None
        error_message = None
        cost = None

    delivery = FakeDelivery()

    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return delivery

    class FakeDB:
        def query(self, model):
            return FakeQuery()

        def commit(self):
            pass

        def refresh(self, obj):
            pass

    service = SMSDeliveryStatusService(FakeDB())

    payload = {
        "MessageSid": "SM123456",
        "MessageStatus": "delivered",
    }

    service.process_webhook(payload)
    service.process_webhook(payload)

    assert len(delivery.status_history) == 1

def test_sent_at_is_not_overwritten():
    from datetime import datetime, timezone

    original_time = datetime.now(timezone.utc)

    class FakeDelivery:
        sms_sid = "SM123456"
        status_history = []
        status = "sent"
        sent_at = original_time
        delivered_at = None
        delivery_latency_ms = None
        last_webhook_at = None
        webhook_payload = None
        error_message = None
        cost = None

    delivery = FakeDelivery()

    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return delivery

    class FakeDB:
        def query(self, model):
            return FakeQuery()

        def commit(self):
            pass

        def refresh(self, obj):
            pass

    service = SMSDeliveryStatusService(FakeDB())

    service.update_delivery_status(
        "SM123456",
        "sent",
        {
            "MessageSid": "SM123456",
            "MessageStatus": "sent",
        },
    )

    assert delivery.sent_at == original_time


def test_delivered_at_is_not_overwritten():
    from datetime import datetime, timezone

    original_time = datetime.now(timezone.utc)

    class FakeDelivery:
        sms_sid = "SM123456"
        status_history = []
        status = "delivered"
        sent_at = None
        delivered_at = original_time
        delivery_latency_ms = None
        last_webhook_at = None
        webhook_payload = None
        error_message = None
        cost = None

    delivery = FakeDelivery()

    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return delivery

    class FakeDB:
        def query(self, model):
            return FakeQuery()

        def commit(self):
            pass

        def refresh(self, obj):
            pass

    service = SMSDeliveryStatusService(FakeDB())

    service.update_delivery_status(
        "SM123456",
        "delivered",
        {
            "MessageSid": "SM123456",
            "MessageStatus": "delivered",
        },
    )

    assert delivery.delivered_at == original_time


def test_status_history_preserves_order():
    class FakeDelivery:
        sms_sid = "SM123456"
        status_history = []
        status = None
        sent_at = None
        delivered_at = None
        delivery_latency_ms = None
        last_webhook_at = None
        webhook_payload = None
        error_message = None
        cost = None

    delivery = FakeDelivery()

    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return delivery

    class FakeDB:
        def query(self, model):
            return FakeQuery()

        def commit(self):
            pass

        def refresh(self, obj):
            pass

    service = SMSDeliveryStatusService(FakeDB())

    for status in ["queued", "sending", "sent", "delivered"]:
        service.update_delivery_status(
            "SM123456",
            status,
            {
                "MessageSid": "SM123456",
                "MessageStatus": status,
            },
        )

    assert [
        item["status"]
        for item in delivery.status_history
    ] == [
        "queued",
        "sending",
        "sent",
        "delivered",
    ]


def test_failed_webhook_stores_error_details():
    class FakeDelivery:
        sms_sid = "SM123456"
        status_history = []
        status = None
        sent_at = None
        delivered_at = None
        delivery_latency_ms = None
        last_webhook_at = None
        webhook_payload = None
        error_message = None
        cost = None

    delivery = FakeDelivery()

    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return delivery

    class FakeDB:
        def query(self, model):
            return FakeQuery()

        def commit(self):
            pass

        def refresh(self, obj):
            pass

    service = SMSDeliveryStatusService(FakeDB())

    service.process_webhook(
        {
            "MessageSid": "SM123456",
            "MessageStatus": "failed",
            "ErrorCode": "30003",
            "ErrorMessage": "Unreachable destination",
        }
    )

    assert delivery.status == "failed"
    assert delivery.error_message == (
        "Twilio ErrorCode: 30003"
    )


def test_webhook_stores_price():
    class FakeDelivery:
        sms_sid = "SM123456"
        status_history = []
        status = None
        sent_at = None
        delivered_at = None
        delivery_latency_ms = None
        last_webhook_at = None
        webhook_payload = None
        error_message = None
        cost = None

    delivery = FakeDelivery()

    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return delivery

    class FakeDB:
        def query(self, model):
            return FakeQuery()

        def commit(self):
            pass

        def refresh(self, obj):
            pass

    service = SMSDeliveryStatusService(FakeDB())

    service.process_webhook(
        {
            "MessageSid": "SM123456",
            "MessageStatus": "delivered",
            "Price": "-0.0075",
        }
    )

    assert delivery.cost == 0.0075


def test_webhook_preserves_callback_information():
    class FakeDelivery:
        sms_sid = "SM123456"
        status_history = []
        status = None
        sent_at = None
        delivered_at = None
        delivery_latency_ms = None
        last_webhook_at = None
        webhook_payload = None
        error_message = None
        cost = None

    delivery = FakeDelivery()

    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return delivery

    class FakeDB:
        def query(self, model):
            return FakeQuery()

        def commit(self):
            pass

        def refresh(self, obj):
            pass

    service = SMSDeliveryStatusService(FakeDB())

    payload = {
        "MessageSid": "SM123456",
        "MessageStatus": "delivered",
        "To": "+919999999999",
        "Price": "-0.0075",
    }

    service.process_webhook(payload)

    assert delivery.webhook_payload == payload
    assert delivery.webhook_payload["To"] == (
        "+919999999999"
    )