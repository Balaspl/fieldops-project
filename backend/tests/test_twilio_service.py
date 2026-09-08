import pytest
from unittest.mock import MagicMock, patch
import os
from app.services.sms.twilio_service import TwilioSMSService, SMSResult
import json
from twilio.base.exceptions import TwilioRestException


def test_service_handles_redis_initialization_failure():
    original_import = __import__

    def failing_import(name, *args, **kwargs):
        if name == "app.redis_client":
            raise Exception("Redis unavailable")
        return original_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=failing_import):
        service = TwilioSMSService()

    assert service.redis is None


def test_service_initializes_twilio_client_when_enabled():
    with patch.dict(
        os.environ,
        {
            "TWILIO_DRY_RUN": "false",
            "TWILIO_TEST_MODE": "false",
            "TWILIO_ACCOUNT_SID": "test_sid",
            "TWILIO_AUTH_TOKEN": "test_token",
            "TWILIO_PHONE_NUMBER": "+919876543210",
        },
    ), patch(
        "app.services.sms.twilio_service.Client"
    ) as mock_client:
        service = TwilioSMSService()

    mock_client.assert_called_once_with(
        "test_sid",
        "test_token",
    )
    assert service.client == mock_client.return_value


def create_service():
    # Provide a sender number for mocked real-send tests.
    with patch.dict(
        "os.environ",
        {"TWILIO_PHONE_NUMBER": "+15005550006"},
    ):
        # Prevent real Twilio client creation during unit tests.
        with patch(
            "app.services.sms.twilio_service.Client"
        ) as mock_client:
            service = TwilioSMSService()

    service.client = mock_client.return_value
    service.redis = None
    return service


def test_validate_phone_number_accepts_indian_local_number():
    service = create_service()

    result = service.validate_phone_number("9876543210")

    assert result == "+919876543210"


def test_validate_phone_number_returns_e164():
    service = create_service()

    result = service.validate_phone_number("+919876543210")

    assert result == "+919876543210"


def test_validate_phone_number_rejects_malformed_number():
    service = create_service()

    with pytest.raises(ValueError, match="Invalid phone number"):
        service.validate_phone_number("not-a-phone-number")


def test_invalid_phone_number_raises_error():
    service = create_service()

    with pytest.raises(ValueError, match="Invalid phone number"):
        service.validate_phone_number("12345")


def test_empty_body_raises_error():
    service = create_service()

    with pytest.raises(ValueError, match="SMS body cannot be empty"):
        service.send_sms(
            to_number="+919876543210",
            body="",
        )


def test_send_sms_accepts_exactly_160_characters():
    service = create_service()

    body = "x" * 160

    result = service.send_sms(
        to_number="+919876543210",
        body=body,
    )

    assert result.success is True


def test_body_over_160_characters_raises_error():
    service = create_service()

    with pytest.raises(
        ValueError,
        match="SMS body cannot exceed 160 characters",
    ):
        service.send_sms(
            to_number="+919876543210",
            body="A" * 161,
        )


@patch.dict(
    "os.environ",
    {
        "TWILIO_TEST_MODE": "true",
        "TWILIO_ACCOUNT_SID": "test_sid",
        "TWILIO_AUTH_TOKEN": "test_token",
        "TWILIO_PHONE_NUMBER": "+15005550006",
    },
)

def test_send_sms_returns_test_status():
    service = create_service()

    service.test_mode = True
    service.dry_run = False

    result = service.send_sms(
        to_number="+919876543210",
        body="Test status",
    )

    assert result.success is True
    assert result.status == "test"
    assert result.sid is None


def test_test_mode_does_not_send_sms():
    service = create_service()

    # Disable dry-run so this test specifically verifies test mode.
    service.dry_run = False
    service.test_mode = True

    result = service.send_sms(
        to_number="+919876543210",
        body="Test message",
    )

    assert result.success is True
    assert result.status == "test"
    assert result.sid is None

    # Test mode must never call Twilio.
    service.client.messages.create.assert_not_called()


def test_send_sms_rejects_whitespace_body():
    service = create_service()

    with pytest.raises(ValueError, match="SMS body cannot be empty"):
        service.send_sms(
            to_number="+919876543210",
            body="   ",
        )


def test_send_sms_rejects_empty_body():
    service = create_service()

    with pytest.raises(ValueError, match="SMS body cannot be empty"):
        service.send_sms(
            to_number="+919876543210",
            body="",
        )


def test_send_sms_does_not_call_twilio_in_test_mode():
    service = create_service()

    service.test_mode = True
    service.dry_run = False

    result = service.send_sms(
        to_number="+919876543210",
        body="Test mode SMS",
    )

    assert result.success is True
    assert result.status == "test"
    service.client.messages.create.assert_not_called()


def test_send_sms_passes_e164_number_to_twilio():
    service = create_service()

    service.dry_run = False
    service.test_mode = False

    mock_message = MagicMock()
    mock_message.sid = "SM_E164"
    mock_message.status = "queued"
    service.client.messages.create.return_value = mock_message

    result = service.send_sms(
        to_number="9876543210",
        body="E164 test",
    )

    assert result.success is True
    service.client.messages.create.assert_called_once_with(
        body="E164 test",
        from_="+15005550006",
        to="+919876543210",
    )


def test_send_sms_returns_twilio_sid():
    service = create_service()

    # Force the test through the mocked Twilio send path.
    service.dry_run = False
    service.test_mode = False

    # Mock the Twilio response so no real SMS is sent.
    mock_message = MagicMock()
    mock_message.sid = "SM123456789"
    mock_message.status = "queued"

    service.client.messages.create.return_value = mock_message

    result = service.send_sms(
        to_number="+919876543210",
        body="Test SMS",
    )

    assert result.success is True
    assert result.sid == "SM123456789"
    assert result.to_number == "+919876543210"
    assert result.status == "queued"

    # Verify Twilio was called with the formatted E.164 number.
    service.client.messages.create.assert_called_once_with(
        body="Test SMS",
        from_=service.from_number,
        to="+919876543210",
    )



def test_send_sms_uses_default_sender_when_custom_sender_not_provided():
    service = create_service()

    service.dry_run = False
    service.test_mode = False

    mock_message = MagicMock()
    mock_message.sid = "SM_DEFAULT_2"
    mock_message.status = "queued"
    service.client.messages.create.return_value = mock_message

    result = service.send_sms(
        to_number="+919876543210",
        body="Default sender",
    )

    assert result.success is True
    assert result.sid == "SM_DEFAULT_2"


def test_send_sms_uses_default_sender_number():
    service = create_service()

    service.dry_run = False
    service.test_mode = False

    mock_message = MagicMock()
    mock_message.sid = "SM_DEFAULT"
    mock_message.status = "queued"
    service.client.messages.create.return_value = mock_message

    result = service.send_sms(
        to_number="+919876543210",
        body="Default sender test",
    )

    assert result.success is True
    service.client.messages.create.assert_called_once_with(
        body="Default sender test",
        from_="+15005550006",
        to="+919876543210",
    )


def test_send_sms_uses_custom_sender_number():
    service = create_service()

    service.dry_run = False
    service.test_mode = False

    mock_message = MagicMock()
    mock_message.sid = "SM_CUSTOM_SENDER"
    mock_message.status = "queued"

    service.client.messages.create.return_value = mock_message

    result = service.send_sms(
        to_number="+919876543210",
        body="Custom sender test",
        from_number="+15005550007",
    )

    assert result.success is True
    assert result.sid == "SM_CUSTOM_SENDER"
    assert result.status == "queued"

    service.client.messages.create.assert_called_once_with(
        body="Custom sender test",
        from_="+15005550007",
        to="+919876543210",
    )


def test_send_sms_accepts_valid_custom_sender():
    service = create_service()

    service.dry_run = False
    service.test_mode = False

    mock_message = MagicMock()
    mock_message.sid = "SM_CUSTOM"
    mock_message.status = "queued"
    service.client.messages.create.return_value = mock_message

    result = service.send_sms(
        to_number="+919876543210",
        body="Custom sender test",
        from_number="+14155552671",
    )

    assert result.success is True
    service.client.messages.create.assert_called_once_with(
        body="Custom sender test",
        from_="+14155552671",
        to="+919876543210",
    )


def test_send_sms_rejects_invalid_custom_sender():
    service = create_service()

    service.dry_run = False
    service.test_mode = False

    with pytest.raises(ValueError, match="Invalid phone number"):
        service.send_sms(
            to_number="+919876543210",
            body="Invalid sender test",
            from_number="12345",
        )


def test_send_sms_does_not_store_delivery_status_without_sid():
    service = create_service()

    service.dry_run = True
    service.test_mode = False

    mock_redis = MagicMock()
    service.redis = mock_redis

    result = service.send_sms(
        to_number="+919876543210",
        body="Dry run SMS",
    )

    assert result.success is True
    assert result.sid is None
    mock_redis.set.assert_not_called()


def test_send_sms_stores_delivery_status_with_recipient():
    service = create_service()

    service.dry_run = False
    service.test_mode = False

    mock_redis = MagicMock()
    service.redis = mock_redis

    mock_message = MagicMock()
    mock_message.sid = "SM123456"
    mock_message.status = "queued"
    service.client.messages.create.return_value = mock_message

    result = service.send_sms(
        to_number="+919876543210",
        body="Tracking test",
    )

    assert result.success is True
    assert result.sid == "SM123456"

    stored_data = json.loads(mock_redis.set.call_args.args[1])
    assert stored_data["sid"] == "SM123456"
    assert stored_data["to_number"] == "+919876543210"


def test_send_sms_delivery_status_has_expiration():
    service = create_service()

    service.dry_run = False
    service.test_mode = False

    mock_redis = MagicMock()
    service.redis = mock_redis

    mock_message = MagicMock()
    mock_message.sid = "SM_EXPIRY"
    mock_message.status = "queued"
    service.client.messages.create.return_value = mock_message

    result = service.send_sms(
        to_number="+919876543210",
        body="Expiration test",
    )

    assert result.success is True
    assert mock_redis.set.call_args.kwargs["ex"] == 86400


def test_send_sms_stores_delivery_status_in_redis():
    service = create_service()

    service.dry_run = False
    service.test_mode = False

    mock_message = MagicMock()
    mock_message.sid = "SM_REDIS_TRACKING"
    mock_message.status = "queued"

    service.client.messages.create.return_value = mock_message

    mock_redis = MagicMock()
    service.redis = mock_redis

    result = service.send_sms(
        to_number="+919876543210",
        body="Redis tracking test",
    )

    assert result.success is True
    assert result.sid == "SM_REDIS_TRACKING"

    mock_redis.set.assert_called_once()

    key, payload = mock_redis.set.call_args.args[:2]

    assert key == "sms_delivery:SM_REDIS_TRACKING"
    assert '"sid": "SM_REDIS_TRACKING"' in payload
    assert '"to_number": "+919876543210"' in payload
    assert '"status": "queued"' in payload

    assert mock_redis.set.call_args.kwargs["ex"] == 86400


def test_send_sms_rate_limit_allows_normal_request():
    service = create_service()

    mock_redis = MagicMock()
    mock_redis.get.return_value = None
    service.redis = mock_redis

    result = service.send_sms(
        to_number="+919876543210",
        body="Rate limit test",
    )

    assert result.success is True
    mock_redis.get.assert_called_once()


def test_send_sms_returns_rate_limited_result():
    service = create_service()

    mock_redis = MagicMock()
    mock_redis.get.return_value = 5
    service.redis = mock_redis

    result = service.send_sms(
        to_number="+919876543210",
        body="Rate limit exceeded",
    )

    assert result.success is False
    assert result.status == "rate_limited"
    assert result.error_code == "429"
    assert result.error_message == "SMS rate limit exceeded"


def test_send_sms_uses_redis_rate_limit():
    service = create_service()

    service.dry_run = True
    service.test_mode = False

    mock_redis = MagicMock()
    service.redis = mock_redis

    mock_redis.incr.return_value = 1

    result = service.send_sms(
        to_number="+919876543210",
        body="Rate limit test",
    )

    assert result.success is True
    assert result.status == "dry-run"

    mock_redis.incr.assert_called_once()

    mock_redis.expire.assert_not_called()


def test_send_bulk_sms_rejects_none_recipients():
    service = create_service()

    with pytest.raises(ValueError, match="Recipients list cannot be empty"):
        service.send_bulk_sms(
            recipients=None,
            body="None recipients test",
        )


def test_send_bulk_sms_rejects_empty_body():
    service = create_service()

    with pytest.raises(ValueError, match="SMS body cannot be empty"):
        service.send_bulk_sms(
            recipients=["+919876543210"],
            body="",
        )


def test_send_bulk_sms_rejects_empty_recipient_list():
    service = create_service()

    with pytest.raises(ValueError, match="Recipients list cannot be empty"):
        service.send_bulk_sms(
            recipients=[],
            body="Bulk SMS test",
        )


def test_send_bulk_sms_rejects_body_over_160_characters():
    service = create_service()

    with pytest.raises(
        ValueError,
        match="SMS body cannot exceed 160 characters",
    ):
        service.send_bulk_sms(
            recipients=["+919876543210"],
            body="A" * 161,
        )


def test_send_bulk_sms_rejects_more_than_50_recipients():
    service = create_service()

    recipients = [f"+9198765432{i:02d}" for i in range(51)]

    with pytest.raises(ValueError, match="more than 50 recipients"):
        service.send_bulk_sms(
            recipients=recipients,
            body="Bulk SMS test",
        )


def test_send_bulk_sms_handles_multiple_recipients():
    service = create_service()

    recipients = [
        "+919876543210",
        "+919876543211",
        "+919876543212",
    ]

    results = service.send_bulk_sms(
        recipients=recipients,
        body="Bulk test",
    )

    assert len(results) == 3
    assert all(result.success for result in results)


def test_send_bulk_sms_returns_result_for_each_recipient():
    service = create_service()

    # Force the bulk test through the mocked Twilio send path.
    service.dry_run = False
    service.test_mode = False

    # Return a different SID for every mocked SMS.
    mock_messages = [
        MagicMock(sid=f"SM{i:09d}", status="queued")
        for i in range(10)
    ]

    service.client.messages.create.side_effect = mock_messages

    recipients = [
        f"+91987654321{i}"
        for i in range(10)
    ]

    results = service.send_bulk_sms(
        recipients=recipients,
        body="Bulk test SMS",
    )

    # Every recipient should produce one result.
    assert len(results) == 10

    # Every SMS should succeed and have a Twilio SID.
    assert all(result.success for result in results)
    assert all(result.sid for result in results)

    # Twilio should receive exactly 10 send requests.
    assert service.client.messages.create.call_count == 10

def test_send_sms_handles_bad_request():
    service = create_service()

    service.dry_run = False
    service.test_mode = False

    error = TwilioRestException(
        status=400,
        uri="/Messages.json",
        msg="Bad request",
    )
    service.client.messages.create.side_effect = error

    result = service.send_sms(
        to_number="+919876543210",
        body="Bad request test",
    )

    assert result.success is False
    assert result.status == "failed"
    assert result.error_code == "400"
    assert result.error_message == "Invalid phone number or SMS request"


def test_send_sms_handles_twilio_service_unavailable():
    service = create_service()

    service.dry_run = False
    service.test_mode = False

    error = TwilioRestException(
        status=503,
        uri="/Messages.json",
        msg="Service unavailable",
    )

    assert error.status == 503

    service.client.messages.create.side_effect = error

    result = service.send_sms(
        to_number="+919876543210",
        body="Service unavailable test",
    )

    assert result.success is False
    assert result.status == "failed"
    assert result.error_code == "503"
    assert result.error_message == "Twilio service unavailable"


def test_send_sms_handles_insufficient_balance():
    service = create_service()

    service.dry_run = False
    service.test_mode = False

    error = TwilioRestException(
        status=402,
        uri="/Messages.json",
        msg="Insufficient balance",
    )
    service.client.messages.create.side_effect = error

    result = service.send_sms(
        to_number="+919876543210",
        body="Balance test",
    )

    assert result.success is False
    assert result.status == "failed"
    assert result.error_code == "402"
    assert result.error_message == "Insufficient Twilio account balance"


def test_twilio_error_maps_to_http_status():
    service = create_service()

    # Force the real Twilio path; the client itself remains mocked.
    service.dry_run = False
    service.test_mode = False

    

    # Simulate Twilio rejecting the SMS request.
    service.client.messages.create.side_effect = TwilioRestException(
        status=400,
        uri="/Messages",
        msg="Invalid phone number",
    )

    result = service.send_sms(
        to_number="+919876543210",
        body="Test SMS",
    )

    assert result.success is False
    assert result.status == "failed"
    assert result.error_code == "400"
    assert result.error_message == "Invalid phone number or SMS request"

def test_send_sms_handles_rate_limit_after_retries():
    service = create_service()

    service.dry_run = False
    service.test_mode = False

    error = TwilioRestException(
        status=429,
        uri="/Messages.json",
        msg="Rate limited",
    )
    service.client.messages.create.side_effect = error

    result = service.send_sms(
        to_number="+919876543210",
        body="Rate limit failure",
    )

    assert result.success is False
    assert result.status == "failed"
    assert result.error_code == "429"
    assert result.error_message == "Twilio rate limit exceeded"


def test_send_sms_handles_invalid_twilio_credentials():
    service = create_service()

    service.dry_run = False
    service.test_mode = False

    error = TwilioRestException(
        status=401,
        uri="/Messages.json",
        msg="Unauthorized",
    )
    service.client.messages.create.side_effect = error

    result = service.send_sms(
        to_number="+919876543210",
        body="Credential test",
    )

    assert result.success is False
    assert result.status == "failed"
    assert result.error_code == "401"
    assert result.error_message == "Invalid Twilio credentials"


def test_twilio_rate_limit_retries_exactly_three_times():
    service = create_service()

    service.dry_run = False
    service.test_mode = False

    error = TwilioRestException(
        status=429,
        uri="/Messages.json",
        msg="Rate limited",
    )

    mock_message = MagicMock()
    mock_message.sid = "SM_RETRY"
    mock_message.status = "queued"

    service.client.messages.create.side_effect = [
        error,
        error,
        mock_message,
    ]

    result = service.send_sms(
        to_number="+919876543210",
        body="Retry count test",
    )

    assert result.success is True
    assert result.sid == "SM_RETRY"
    assert service.client.messages.create.call_count == 3


def test_twilio_rate_limit_retries_then_succeeds():
    service = create_service()

    # Force the real Twilio path; the client is still mocked.
    service.dry_run = False
    service.test_mode = False

    

    mock_message = MagicMock()
    mock_message.sid = "SM_RETRY_SUCCESS"
    mock_message.status = "queued"

    # First attempt gets 429, second attempt succeeds.
    rate_limit_error = TwilioRestException(
        status=429,
        uri="/Messages",
        msg="Too many requests",
    )

    service.client.messages.create.side_effect = [
        rate_limit_error,
        mock_message,
    ]

    # Avoid waiting during the unit test.
    with patch("app.services.sms.twilio_service.time.sleep") as mock_sleep:
        result = service.send_sms(
            to_number="+919876543210",
            body="Retry test SMS",
        )

    assert result.success is True
    assert result.sid == "SM_RETRY_SUCCESS"
    assert result.status == "queued"

    # Verify retry happened exactly once.
    assert service.client.messages.create.call_count == 2
    mock_sleep.assert_called_once_with(1)


def test_twilio_server_error_retries():
    service = create_service()

    service.dry_run = False
    service.test_mode = False

    error = TwilioRestException(
        status=500,
        uri="/Messages.json",
        msg="Server error",
    )

    service.client.messages.create.side_effect = error

    result = service.send_sms(
        to_number="+919876543210",
        body="Server retry test",
    )

    assert result.success is False
    assert result.error_code == "503"
    assert service.client.messages.create.call_count == 3


def test_twilio_rate_limit_fails_after_retries():
    service = create_service()

    # Force the real Twilio path; the client is still mocked.
    service.dry_run = False
    service.test_mode = False

    

    rate_limit_error = TwilioRestException(
        status=429,
        uri="/Messages",
        msg="Too many requests",
    )

    # Every attempt fails with a rate-limit error.
    service.client.messages.create.side_effect = rate_limit_error

    # Avoid real retry delays during the unit test.
    with patch("app.services.sms.twilio_service.time.sleep") as mock_sleep:
        result = service.send_sms(
            to_number="+919876543210",
            body="Retry failure test",
        )

    assert result.success is False
    assert result.status == "failed"
    assert result.error_code == "429"
    assert result.error_message == "Twilio rate limit exceeded"

    # Initial attempt + 2 retries = 3 Twilio calls.
    assert service.client.messages.create.call_count == 3
    assert mock_sleep.call_count == 2

def test_dry_run_returns_recipient_without_sid():
    service = create_service()

    service.dry_run = True
    service.test_mode = False

    result = service.send_sms(
        to_number="+919876543210",
        body="Dry run recipient test",
    )

    assert result.success is True
    assert result.to_number == "+919876543210"
    assert result.sid is None
    assert result.status == "dry-run"


def test_dry_run_does_not_send_sms():
    service = create_service()

    # Enable dry-run and disable test mode for this specific test.
    service.dry_run = True
    service.test_mode = False

    result = service.send_sms(
        to_number="+919876543210",
        body="Dry-run test SMS",
    )

    assert result.success is True
    assert result.sid is None
    assert result.to_number == "+919876543210"
    assert result.status == "dry-run"

    # Dry-run must never call Twilio.
    service.client.messages.create.assert_not_called()


def test_preview_sms_does_not_call_twilio():
    service = create_service()

    result = service.preview_sms(
        to_number="+919876543210",
        body="Preview test",
    )

    assert result.success is True
    assert result.status == "preview"
    service.client.messages.create.assert_not_called()


def test_preview_sms_returns_e164_recipient():
    service = create_service()

    result = service.preview_sms(
        to_number="9876543210",
        body="Preview E164",
    )

    assert result.success is True
    assert result.to_number == "+919876543210"
    assert result.status == "preview"


def test_preview_sms_returns_validated_result():
    service = create_service()

    result = service.preview_sms(
        to_number="+919876543210",
        body="Preview service test",
    )

    assert result.success is True
    assert result.sid is None
    assert result.to_number == "+919876543210"
    assert result.status == "preview"


def test_preview_sms_rejects_empty_body_directly():
    service = create_service()

    with pytest.raises(ValueError, match="SMS body cannot be empty"):
        service.preview_sms(
            to_number="+919876543210",
            body="",
        )


def test_preview_sms_rejects_body_over_160_characters_directly():
    service = create_service()

    with pytest.raises(ValueError, match="160"):
        service.preview_sms(
            to_number="+919876543210",
            body="x" * 161,
        )


def test_preview_sms_rejects_invalid_phone():
    service = create_service()

    with pytest.raises(ValueError, match="Invalid phone number"):
        service.preview_sms(
            to_number="12345",
            body="Preview service test",
        )


def test_send_bulk_sms_accepts_exactly_50_recipients():
    service = create_service()

    recipients = [
        f"+91987654{i:04d}"
        for i in range(50)
    ]

    results = service.send_bulk_sms(
        recipients=recipients,
        body="Exactly fifty recipients",
    )

    assert len(results) == 50


def test_send_bulk_sms_preserves_recipient_order():
    service = create_service()

    recipients = [
        "+919876543210",
        "+919876543211",
        "+919876543212",
    ]

    results = service.send_bulk_sms(
        recipients=recipients,
        body="Order test",
    )

    assert len(results) == 3
    assert [result.to_number for result in results] == recipients


def test_bulk_sms_returns_failed_result_for_invalid_recipient():
    service = create_service()

    results = service.send_bulk_sms(
        recipients=["invalid-number"],
        body="Invalid recipient test",
    )

    assert len(results) == 1
    assert results[0].success is False
    assert results[0].status == "failed"


def test_bulk_sms_continues_after_invalid_recipient():
    service = create_service()

    # Force the real mocked Twilio send path.
    service.dry_run = False
    service.test_mode = False

    mock_messages = [
        MagicMock(sid="SM_VALID_1", status="queued"),
        MagicMock(sid="SM_VALID_2", status="queued"),
    ]

    service.client.messages.create.side_effect = mock_messages

    recipients = [
        "+919876543210",
        "12345",  # Invalid recipient
        "+919876543211",
    ]

    results = service.send_bulk_sms(
        recipients=recipients,
        body="Bulk validation test",
    )

    assert len(results) == 3

    # First valid recipient succeeds.
    assert results[0].success is True
    assert results[0].sid == "SM_VALID_1"

    # Invalid recipient fails independently.
    assert results[1].success is False
    assert results[1].status == "failed"

    # Third recipient is still processed.
    assert results[2].success is True
    assert results[2].sid == "SM_VALID_2"

    # Only the two valid recipients reached Twilio.
    assert service.client.messages.create.call_count == 2

def test_twilio_error_maps_unknown_status_to_500():
    service = create_service()

    error = TwilioRestException(
        status=418,
        uri="/Messages",
        msg="Unexpected Twilio error",
    )

    status_code, message = service._map_twilio_error(error)

    assert status_code == 500
    assert message == "Unexpected Twilio error"


@pytest.mark.parametrize(
    "twilio_status, expected_code",
    [
        (401, "401"),
        (402, "402"),
        (500, "503"),
        (503, "503"),
    ],
)

def test_twilio_errors_map_to_expected_http_codes(
    twilio_status,
    expected_code,
):
    service = create_service()

    # Force the real mocked Twilio send path.
    service.dry_run = False
    service.test_mode = False

    

    service.client.messages.create.side_effect = TwilioRestException(
        status=twilio_status,
        uri="/Messages",
        msg="Twilio error",
    )

    # Avoid retry delays for 500/503.
    with patch("app.services.sms.twilio_service.time.sleep"):
        result = service.send_sms(
            to_number="+919876543210",
            body="Error mapping test",
        )

    assert result.success is False
    assert result.status == "failed"
    assert result.error_code == expected_code

def test_sms_endpoint_response_time_under_500ms():
    from time import perf_counter
    from fastapi.testclient import TestClient
    from app.main import app

    with patch("app.routes.notifications.TwilioSMSService") as mock_service_class, \
         patch("app.routes.notifications.send_sms_async") as mock_task:

        mock_service = mock_service_class.return_value
        mock_service.preview_sms.return_value = MagicMock()
        mock_task.delay.return_value.id = "performance-task-123"

        client = TestClient(app)

        # Warm up the application/client before measuring the request.
        client.post(
            "/sms/send",
            json={
                "to_number": "+919876543210",
                "body": "Warm up",
            },
        )

        start = perf_counter()

        response = client.post(
            "/sms/send",
            json={
                "to_number": "+919876543210",
                "body": "Performance test SMS",
            },
        )

        elapsed = perf_counter() - start

    assert response.status_code == 200
    assert response.json()["status"] == "queued"
    assert elapsed < 0.5

@patch("app.routes.notifications.send_sms_async")
@patch("app.routes.notifications.TwilioSMSService")
def test_sms_endpoint_queues_async_task(mock_service_class, mock_task):
    # Mock validation so no real Twilio setup is required.
    mock_service = mock_service_class.return_value
    mock_service.preview_sms.return_value = MagicMock()

    # Mock the Celery task returned by .delay().
    mock_task.delay.return_value.id = "celery-task-123"

    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    response = client.post(
        "/sms/send",
        json={
            "to_number": "+919876543210",
            "body": "Async test SMS",
        },
    )

    assert response.status_code == 200

    data = response.json()
    assert data["success"] is True
    assert data["status"] == "queued"
    assert data["task_id"] == "celery-task-123"

    # Verify the SMS was queued instead of sent inside the API request.
    mock_task.delay.assert_called_once_with(
        to_number="+919876543210",
        body="Async test SMS",
        from_number=None,
    )


@patch("app.routes.notifications.send_bulk_sms_async")
@patch("app.routes.notifications.TwilioSMSService")
def test_bulk_sms_endpoint_queues_async_task(
    mock_service_class,
    mock_task,
):
    # Mock validation so no real Twilio setup is required.
    mock_service = mock_service_class.return_value

    # Mock the Celery task returned by .delay().
    mock_task.delay.return_value.id = "bulk-celery-task-123"

    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    response = client.post(
        "/sms/send-bulk",
        json={
            "recipients": [
                "+919876543210",
                "+919876543211",
                "+919876543212",
            ],
            "body": "Bulk async test SMS",
        },
    )

    assert response.status_code == 200

    data = response.json()
    assert data["success"] is True
    assert data["status"] == "queued"
    assert data["recipient_count"] == 3
    assert data["task_id"] == "bulk-celery-task-123"

    # Verify bulk SMS was queued asynchronously.
    mock_task.delay.assert_called_once_with(
        recipients=[
            "+919876543210",
            "+919876543211",
            "+919876543212",
        ],
        body="Bulk async test SMS",
        from_number=None,
    )

@patch("app.routes.notifications.TwilioSMSService")
def test_bulk_sms_rejects_more_than_50_recipients(mock_service_class):
    from fastapi.testclient import TestClient
    from app.main import app

    # Mock service creation because this test only checks API validation.
    mock_service_class.return_value = MagicMock()

    client = TestClient(app)

    # 51 recipients must be rejected before Celery queueing.
    recipients = [
        f"+9198765432{i:02d}"
        for i in range(51)
    ]

    response = client.post(
        "/sms/send-bulk",
        json={
            "recipients": recipients,
            "body": "Too many recipients",
        },
    )

    assert response.status_code == 422
    assert "50" in response.json()["detail"]

def test_send_sms_async_task_calls_service():
    from app.tasks import send_sms_async

    mock_service = MagicMock()
    mock_service.send_sms.return_value = SMSResult(
        success=True,
        sid="SM_ASYNC_123",
        to_number="+919876543210",
        status="queued",
    )

    with patch(
        "app.tasks.TwilioSMSService",
        return_value=mock_service,
    ):
        result = send_sms_async.run(
            to_number="+919876543210",
            body="Async worker test",
            from_number=None,
        )

    mock_service.send_sms.assert_called_once_with(
        to_number="+919876543210",
        body="Async worker test",
        from_number=None,
    )

    assert result.success is True
    assert result.sid == "SM_ASYNC_123"
    assert result.status == "queued"

@patch("app.routes.notifications.TwilioSMSService")
def test_sms_preview_validates_without_sending(mock_service_class):
    from fastapi.testclient import TestClient
    from app.main import app

    # Mock the service because this test only checks preview validation.
    mock_service = MagicMock()
    mock_service.preview_sms.return_value = {
        "success": True,
        "status": "preview",
        "to_number": "+919876543210",
        "body": "Preview message",
    }
    mock_service_class.return_value = mock_service

    client = TestClient(app)

    response = client.post(
        "/sms/preview",
        json={
            "to_number": "+919876543210",
            "body": "Preview message",
        },
    )

    assert response.status_code == 200
    data = response.json()

    # Preview should return the normalized number and message.
    assert data["to_number"] == "+919876543210"
    assert data["body"] == "Preview message"
    assert data["status"] == "preview"


def test_sms_preview_rejects_invalid_phone_number():
    from fastapi.testclient import TestClient
    from app.main import app

    # Mock service creation; validation behavior is tested separately.
    mock_service = MagicMock()
    mock_service.preview_sms.side_effect = ValueError("Invalid phone number")

    with patch("app.routes.notifications.TwilioSMSService", return_value=mock_service):
        client = TestClient(app)

        response = client.post(
            "/sms/preview",
            json={
                "to_number": "12345",
                "body": "Preview message",
            },
        )

    assert response.status_code == 422
    assert "Invalid phone number" in response.json()["detail"]


def test_sms_preview_rejects_body_over_160_characters():
    from fastapi.testclient import TestClient
    from app.main import app

    # Mock service creation; validation behavior is tested separately.
    mock_service = MagicMock()
    mock_service.preview_sms.side_effect = ValueError(
        "SMS body cannot exceed 160 characters"
    )

    with patch("app.routes.notifications.TwilioSMSService", return_value=mock_service):
        client = TestClient(app)

        response = client.post(
            "/sms/preview",
            json={
                "to_number": "+919876543210",
                "body": "A" * 161,
            },
        )

    assert response.status_code == 422
    assert "160" in response.json()["detail"]

def test_sms_preview_rejects_empty_body():
    from fastapi.testclient import TestClient
    from app.main import app

    # Mock service because this test checks API validation only.
    mock_service = MagicMock()
    mock_service.preview_sms.side_effect = ValueError("SMS body cannot be empty")

    with patch("app.routes.notifications.TwilioSMSService", return_value=mock_service):
        client = TestClient(app)

        response = client.post(
            "/sms/preview",
            json={
                "to_number": "+919876543210",
                "body": "",
            },
        )

    assert response.status_code == 422
    assert "empty" in response.json()["detail"].lower()


def test_sms_preview_rejects_whitespace_body():
    from fastapi.testclient import TestClient
    from app.main import app

    # Whitespace-only messages must not be accepted.
    mock_service = MagicMock()
    mock_service.preview_sms.side_effect = ValueError("SMS body cannot be empty")

    with patch("app.routes.notifications.TwilioSMSService", return_value=mock_service):
        client = TestClient(app)

        response = client.post(
            "/sms/preview",
            json={
                "to_number": "+919876543210",
                "body": "   ",
            },
        )

    assert response.status_code == 422
    assert "empty" in response.json()["detail"].lower()

@patch("app.routes.notifications.TwilioSMSService")
def test_sms_endpoint_rejects_invalid_phone_number(mock_service_class):
    from fastapi.testclient import TestClient
    from app.main import app

    # Validation must happen before the SMS is queued.
    mock_service = MagicMock()
    mock_service.preview_sms.side_effect = ValueError("Invalid phone number")
    mock_service_class.return_value = mock_service

    client = TestClient(app)

    response = client.post(
        "/sms/send",
        json={
            "to_number": "12345",
            "body": "Test message",
        },
    )

    assert response.status_code == 422
    assert "Invalid phone number" in response.json()["detail"]


@patch("app.routes.notifications.TwilioSMSService")
def test_sms_endpoint_rejects_body_over_160_characters(mock_service_class):
    from fastapi.testclient import TestClient
    from app.main import app

    # Message length must be validated before Celery queueing.
    mock_service = MagicMock()
    mock_service.preview_sms.side_effect = ValueError(
        "SMS body cannot exceed 160 characters"
    )
    mock_service_class.return_value = mock_service

    client = TestClient(app)

    response = client.post(
        "/sms/send",
        json={
            "to_number": "+919876543210",
            "body": "A" * 161,
        },
    )

    assert response.status_code == 422
    assert "160" in response.json()["detail"]


def test_real_send_requires_sender_phone_number():
    service = create_service()

    service.dry_run = False
    service.test_mode = False
    service.from_number = None

    with pytest.raises(
        ValueError,
        match="Twilio sender phone number is not configured",
    ):
        service.send_sms(
            to_number="+919876543210",
            body="Sender validation test",
        )


def test_send_sms_handles_timeout_without_status_attribute():
    service = create_service()

    service.dry_run = False
    service.test_mode = False

    service.client.messages.create.side_effect = TimeoutError("Request timeout")

    result = service.send_sms(
        to_number="+919876543210",
        body="Timeout status test",
    )

    assert result.success is False
    assert result.error_code == "503"
    assert result.error_message == "Twilio request timed out"


def test_send_sms_handles_timeout_as_service_unavailable():
    service = create_service()

    service.dry_run = False
    service.test_mode = False

    service.client.messages.create.side_effect = TimeoutError("timeout")

    result = service.send_sms(
        to_number="+919876543210",
        body="Timeout test",
    )

    assert result.success is False
    assert result.status == "failed"
    assert result.error_code == "503"
    assert result.error_message == "Twilio request timed out"


def test_twilio_timeout_retries_then_succeeds():
    service = create_service()

    service.dry_run = False
    service.test_mode = False

    mock_message = MagicMock()
    mock_message.sid = "SM_TIMEOUT_SUCCESS"
    mock_message.status = "queued"

    service.client.messages.create.side_effect = [
        TimeoutError("Twilio request timed out"),
        mock_message,
    ]

    with patch("app.services.sms.twilio_service.time.sleep") as mock_sleep:
        result = service.send_sms(
            to_number="+919876543210",
            body="Timeout retry test",
        )

    assert result.success is True
    assert result.sid == "SM_TIMEOUT_SUCCESS"
    assert result.status == "queued"

    assert service.client.messages.create.call_count == 2
    mock_sleep.assert_called_once_with(1)


def test_logging_captures_required_sms_fields(caplog):
    service = create_service()

    service.dry_run = True

    with caplog.at_level("INFO"):
        result = service.send_sms(
            to_number="+919876543210",
            body="Logging verification test",
        )

    assert result.success is True

    log_text = caplog.text

    assert "+919876543210" in log_text
    assert "Logging verification test" in log_text
    assert "dry-run" in log_text
    assert "timestamp=" in log_text


def test_twilio_timeout_fails_after_retries():
    service = create_service()

    service.dry_run = False
    service.test_mode = False

    service.client.messages.create.side_effect = TimeoutError(
        "Twilio request timed out"
    )

    with patch("app.services.sms.twilio_service.time.sleep") as mock_sleep:
        result = service.send_sms(
            to_number="+919876543210",
            body="Timeout failure test",
        )

    assert result.success is False
    assert result.status == "failed"
    assert result.error_code == "503"
    assert result.error_message == "Twilio request timed out"

    assert service.client.messages.create.call_count == 3
    assert mock_sleep.call_count == 2


def test_twilio_test_credential_integration():
    """
    Real Twilio integration test.

    This test is skipped unless Twilio test credentials are configured.
    Twilio's test credentials simulate the API and do not deliver a real SMS.
    """
    account_sid = os.getenv("TWILIO_TEST_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_TEST_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_TEST_FROM_NUMBER")
    to_number = os.getenv("TWILIO_TEST_TO_NUMBER")

    if not all([account_sid, auth_token, from_number, to_number]):
        pytest.skip("Twilio test credentials are not configured")

    service = TwilioSMSService()

    service.account_sid = account_sid
    service.auth_token = auth_token
    service.from_number = from_number
    service.test_mode = False
    service.dry_run = False

    from twilio.rest import Client

    service.client = Client(account_sid, auth_token)

    result = service.send_sms(
        to_number=to_number,
        body="FieldOps Twilio integration test",
        from_number=from_number,
    )

    assert result.success is True
    assert result.sid is not None
    assert result.to_number == to_number