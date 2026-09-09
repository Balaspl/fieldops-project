import pytest
import pytest
from unittest.mock import AsyncMock, MagicMock, patch,Mock

from app.tasks import send_email_async
from app.services.email.sendgrid_email import (
    EmailDeliveryError,
    EmailResult,
    SendGridEmailService,
    retry_transient,
)

@pytest.mark.asyncio
async def test_send_email_test_mode():
    service = SendGridEmailService(test_mode=True)

    result = await service.send_email(
        to_email="test@example.com",
        subject="FieldOps Test",
        html_body="<h1>Hello</h1>",
        plain_text="Hello",
    )

    assert isinstance(result, EmailResult)
    assert result.success is True
    assert result.status_code == 202
    assert result.simulated is True
    assert result.message_id is not None
    assert result.message_id.startswith("SGTEST_")


@pytest.mark.asyncio
async def test_send_email_rejects_invalid_recipient():
    service = SendGridEmailService(test_mode=True)

    with pytest.raises(ValueError, match="Invalid recipient email"):
        await service.send_email(
            to_email="not-an-email",
            subject="FieldOps Test",
            html_body="<h1>Hello</h1>",
        )


@pytest.mark.asyncio
async def test_send_email_requires_subject():
    service = SendGridEmailService(test_mode=True)

    with pytest.raises(ValueError, match="Email subject is required"):
        await service.send_email(
            to_email="test@example.com",
            subject="",
            html_body="<h1>Hello</h1>",
        )


@pytest.mark.asyncio
async def test_send_email_requires_html_body():
    service = SendGridEmailService(test_mode=True)

    with pytest.raises(ValueError, match="HTML email body is required"):
        await service.send_email(
            to_email="test@example.com",
            subject="FieldOps Test",
            html_body="",
        )


@pytest.mark.asyncio
async def test_send_bulk_email():
    service = SendGridEmailService(test_mode=True)

    results = await service.send_bulk_email(
        recipients=[
            "one@example.com",
            "two@example.com",
            "three@example.com",
        ],
        subject="Bulk Test",
        html_body="<h1>Hello</h1>",
        plain_text="Hello",
    )

    assert len(results) == 3

    for result in results:
        assert isinstance(result, EmailResult)
        assert result.success is True
        assert result.status_code == 202
        assert result.simulated is True
        assert result.message_id is not None

@pytest.mark.asyncio
async def test_send_email_success_from_sendgrid():
    service = SendGridEmailService(
        api_key="test-api-key",
        test_mode=False,
    )

    mock_response = MagicMock()
    mock_response.status_code = 202
    mock_response.headers = {
        "X-Message-Id": "sendgrid-message-123"
    }

    with patch.object(
        service._client,
        "send",
        return_value=mock_response,
    ) as mock_send:
        result = await service.send_email(
            to_email="customer@example.com",
            subject="Job Confirmation",
            html_body="<h1>Your job is confirmed</h1>",
            plain_text="Your job is confirmed",
        )

    assert result.success is True
    assert result.status_code == 202
    assert result.message_id == "sendgrid-message-123"
    assert result.error is None
    assert result.simulated is False

    mock_send.assert_called_once()


@pytest.mark.asyncio
async def test_send_email_without_api_key():
    service = SendGridEmailService(
        api_key=None,
        test_mode=False,
    )

    result = await service.send_email(
        to_email="customer@example.com",
        subject="Test",
        html_body="<p>Hello</p>",
    )

    assert result.success is False
    assert result.error == "SENDGRID_API_KEY is not configured."


@pytest.mark.asyncio
async def test_send_email_builds_plain_text_and_html():
    service = SendGridEmailService(
        api_key="test-api-key",
        test_mode=False,
    )

    message = service._build_message(
        to_email="customer@example.com",
        subject="Multipart Test",
        html_body="<h1>Hello</h1>",
        plain_text="Hello",
    )

    message_data = message.get()

    assert message_data["subject"] == "Multipart Test"
    assert len(message_data["content"]) == 2

    content_types = {
        item["type"]
        for item in message_data["content"]
    }

    assert "text/plain" in content_types
    assert "text/html" in content_types


@pytest.mark.asyncio
async def test_send_email_handles_bad_request_without_retry():
    service = SendGridEmailService(
        api_key="test-api-key",
        test_mode=False,
    )

    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.headers = {}

    with patch.object(
        service._client,
        "send",
        return_value=mock_response,
    ) as mock_send:
        result = await service.send_email(
            to_email="customer@example.com",
            subject="Bad Request Test",
            html_body="<p>Hello</p>",
        )

    assert result.success is False
    assert result.status_code == 400
    assert result.error is not None

    # 400 is not transient, so SendGrid must be called only once.
    mock_send.assert_called_once()


@pytest.mark.asyncio
async def test_send_email_retries_rate_limit_then_succeeds():
    service = SendGridEmailService(
        api_key="test-api-key",
        test_mode=False,
    )

    rate_limit_response = MagicMock()
    rate_limit_response.status_code = 429
    rate_limit_response.headers = {}

    success_response = MagicMock()
    success_response.status_code = 202
    success_response.headers = {
        "X-Message-Id": "retry-success-123"
    }

    with patch.object(
        service._client,
        "send",
        side_effect=[
            rate_limit_response,
            success_response,
        ],
    ) as mock_send, patch(
        "app.services.email.sendgrid_email.asyncio.sleep",
        new_callable=AsyncMock,
    ) as mock_sleep:

        result = await service.send_email(
            to_email="customer@example.com",
            subject="Retry Test",
            html_body="<p>Hello</p>",
        )

    assert result.success is True
    assert result.status_code == 202
    assert result.message_id == "retry-success-123"

    assert mock_send.call_count == 2
    mock_sleep.assert_awaited_once_with(1.0)


@pytest.mark.asyncio
async def test_send_email_retries_server_error_then_succeeds():
    service = SendGridEmailService(
        api_key="test-api-key",
        test_mode=False,
    )

    server_error_response = MagicMock()
    server_error_response.status_code = 503
    server_error_response.headers = {}

    success_response = MagicMock()
    success_response.status_code = 202
    success_response.headers = {
        "X-Message-Id": "server-retry-success"
    }

    with patch.object(
        service._client,
        "send",
        side_effect=[
            server_error_response,
            success_response,
        ],
    ) as mock_send, patch(
        "app.services.email.sendgrid_email.asyncio.sleep",
        new_callable=AsyncMock,
    ) as mock_sleep:

        result = await service.send_email(
            to_email="customer@example.com",
            subject="Server Retry Test",
            html_body="<p>Hello</p>",
        )

    assert result.success is True
    assert result.status_code == 202
    assert result.message_id == "server-retry-success"

    assert mock_send.call_count == 2
    mock_sleep.assert_awaited_once_with(1.0)


@pytest.mark.asyncio
async def test_send_email_exhausts_transient_retries():
    service = SendGridEmailService(
        api_key="test-api-key",
        test_mode=False,
    )

    server_error_response = MagicMock()
    server_error_response.status_code = 500
    server_error_response.headers = {}

    with patch.object(
        service._client,
        "send",
        return_value=server_error_response,
    ) as mock_send, patch(
        "app.services.email.sendgrid_email.asyncio.sleep",
        new_callable=AsyncMock,
    ) as mock_sleep:

        result = await service.send_email(
            to_email="customer@example.com",
            subject="Retry Exhaustion Test",
            html_body="<p>Hello</p>",
        )

    assert result.success is False
    assert result.status_code == 500
    assert result.error is not None

    # Three attempts: original + two retries.
    assert mock_send.call_count == 3

    assert mock_sleep.await_count == 2
    mock_sleep.assert_any_await(1.0)
    mock_sleep.assert_any_await(2.0)


@pytest.mark.asyncio
async def test_send_email_with_attachment():
    service = SendGridEmailService(
        api_key="test-api-key",
        test_mode=False,
    )

    mock_response = MagicMock()
    mock_response.status_code = 202
    mock_response.headers = {
        "X-Message-Id": "attachment-message-123"
    }

    pdf_content = b"%PDF-1.4 test pdf content"

    with patch.object(
        service._client,
        "send",
        return_value=mock_response,
    ) as mock_send:
        result = await service.send_email(
            to_email="customer@example.com",
            subject="Job Report",
            html_body="<h1>Job Report</h1>",
            plain_text="Job Report",
            attachments=[
                {
                    "filename": "job-report.pdf",
                    "content": pdf_content,
                    "content_type": "application/pdf",
                }
            ],
        )

    assert result.success is True
    assert result.status_code == 202
    assert result.message_id == "attachment-message-123"

    mock_send.assert_called_once()

    sent_message = mock_send.call_args.args[0]
    message_data = sent_message.get()

    assert "attachments" in message_data
    assert len(message_data["attachments"]) == 1
    assert message_data["attachments"][0]["filename"] == "job-report.pdf"
    assert message_data["attachments"][0]["type"] == "application/pdf"

def test_send_email_async_celery_task():
    with patch(
        "app.tasks.SendGridEmailService"
    ) as mock_service_class:

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        mock_service.send_email = AsyncMock(
            return_value=EmailResult(
                success=True,
                message_id="SGTEST_CELERY_123",
                status_code=202,
                error=None,
                simulated=True,
            )
        )

        result = send_email_async.apply(
            args=[
                "customer@example.com",
                "Celery Job Confirmation",
                "<h1>Job Confirmed</h1>",
                "Job Confirmed",
                None,
            ]
        )

        output = result.get()

    assert output["success"] is True
    assert output["message_id"] == "SGTEST_CELERY_123"
    assert output["status_code"] == 202
    assert output["error"] is None
    assert output["simulated"] is True

    mock_service.send_email.assert_awaited_once_with(
        to_email="customer@example.com",
        subject="Celery Job Confirmation",
        html_body="<h1>Job Confirmed</h1>",
        plain_text="Job Confirmed",
        attachments=None,
    )

def test_prepare_attachment_requires_filename():
    service = SendGridEmailService(test_mode=True)

    with pytest.raises(ValueError, match="Attachment filename is required"):
        service._prepare_attachment(
            {
                "content": b"test",
                "content_type": "text/plain",
            }
        )


def test_prepare_attachment_requires_content():
    service = SendGridEmailService(test_mode=True)

    with pytest.raises(
        ValueError,
        match="Attachment content is required",
    ):
        service._prepare_attachment(
            {
                "filename": "test.txt",
                "content_type": "text/plain",
            }
        )


def test_prepare_attachment_rejects_invalid_attachment_type():
    service = SendGridEmailService(test_mode=True)

    with pytest.raises(
        ValueError,
        match="Each attachment must be a dictionary",
    ):
        service._prepare_attachment("invalid")


def test_prepare_attachment_accepts_base64_string():
    service = SendGridEmailService(test_mode=True)

    attachment = service._prepare_attachment(
        {
            "filename": "test.txt",
            "content": "SGVsbG8=",
            "content_type": "text/plain",
        }
    )

    assert attachment is not None


def test_test_mode_from_environment(monkeypatch):
    monkeypatch.setenv("SENDGRID_TEST_MODE", "true")

    service = SendGridEmailService(
        api_key="test-key",
        test_mode=None,
    )

    assert service.test_mode is True
    assert service._client is None


def test_validate_recipient_required():
    with pytest.raises(ValueError, match="Recipient email is required"):
        SendGridEmailService.validate_recipient("")


def test_validate_recipient_non_string():
    with pytest.raises(ValueError, match="Recipient email is required"):
        SendGridEmailService.validate_recipient(None)


def test_prepare_attachment_invalid_content_type():
    with pytest.raises(ValueError, match="must be bytes or base64 text"):
        SendGridEmailService._prepare_attachment(
            {
                "filename": "report.pdf",
                "content": 12345,
            }
        )


def test_extract_status_code_no_response():
    exception = Exception("test error")

    assert SendGridEmailService._extract_status_code(exception) is None


def test_extract_status_code_invalid_value():
    exception = Exception("test error")
    exception.response = type("Response", (), {"status_code": "invalid"})()

    assert SendGridEmailService._extract_status_code(exception) is None


def test_extract_status_code_valid_value():
    exception = Exception("test error")
    exception.response = type("Response", (), {"status_code": "429"})()

    assert SendGridEmailService._extract_status_code(exception) == 429


def test_extract_message_id_no_headers():
    response = type("Response", (), {"headers": None})()

    assert SendGridEmailService._extract_message_id(response) is None


def test_extract_message_id_missing_header():
    response = type(
        "Response",
        (),
        {"headers": {"content-type": "application/json"}},
    )()

    assert SendGridEmailService._extract_message_id(response) is None


def test_safe_subject_preview_long_subject():
    subject = "A" * 100

    preview = SendGridEmailService._safe_subject_preview(subject)

    assert len(preview) == 80
    assert preview.endswith("...")


@pytest.mark.asyncio
async def test_send_with_provider_without_client():
    service = SendGridEmailService(
        api_key=None,
        test_mode=False,
    )

    message = service._build_message(
        to_email="user@example.com",
        subject="Test",
        html_body="<p>Hello</p>",
    )

    with pytest.raises(EmailDeliveryError, match="client is not configured"):
        await service._send_with_provider(message)


@pytest.mark.asyncio
async def test_send_with_provider_generic_exception():
    service = SendGridEmailService(
        api_key="test-key",
        test_mode=False,
    )

    service._client.send = Mock(
        side_effect=RuntimeError("provider failure")
    )

    message = service._build_message(
        to_email="user@example.com",
        subject="Test",
        html_body="<p>Hello</p>",
    )

    with pytest.raises(EmailDeliveryError, match="provider failure"):
        await service._send_with_provider(message)


@pytest.mark.asyncio
async def test_send_email_unexpected_exception(monkeypatch):
    service = SendGridEmailService(
        api_key="test-key",
        test_mode=False,
    )

    monkeypatch.setattr(
        service,
        "_build_message",
        Mock(side_effect=RuntimeError("unexpected failure")),
    )

    result = await service.send_email(
        to_email="user@example.com",
        subject="Test",
        html_body="<p>Hello</p>",
    )

    assert result.success is False
    assert result.error == "unexpected failure"


@pytest.mark.asyncio
async def test_send_bulk_email_requires_recipients():
    service = SendGridEmailService(
        api_key="test-key",
        test_mode=True,
    )

    with pytest.raises(ValueError, match="At least one recipient"):
        await service.send_bulk_email(
            recipients=[],
            subject="Test",
            html_body="<p>Hello</p>",
        )


@pytest.mark.asyncio
async def test_send_bulk_email_handles_invalid_recipient():
    service = SendGridEmailService(
        api_key="test-key",
        test_mode=True,
    )

    results = await service.send_bulk_email(
        recipients=[
            "valid@example.com",
            "not-an-email",
        ],
        subject="Test",
        html_body="<p>Hello</p>",
    )

    assert len(results) == 2
    assert results[0].success is True
    assert results[1].success is False
    assert "Invalid recipient email address" in results[1].error


@pytest.mark.asyncio
async def test_retry_transient_timeout_then_success():
    calls = 0

    @retry_transient(max_attempts=3, base_delay=0)
    async def flaky_operation():
        nonlocal calls
        calls += 1

        if calls == 1:
            raise TimeoutError("connection timed out")

        return "success"

    result = await flaky_operation()

    assert result == "success"
    assert calls == 2


@pytest.mark.asyncio
async def test_retry_transient_connection_error_then_success():
    calls = 0

    @retry_transient(max_attempts=3, base_delay=0)
    async def flaky_operation():
        nonlocal calls
        calls += 1

        if calls == 1:
            raise ConnectionError("connection failed")

        return "success"

    result = await flaky_operation()

    assert result == "success"
    assert calls == 2


@pytest.mark.asyncio
async def test_retry_transient_os_error_exhausts_retries():
    calls = 0

    @retry_transient(max_attempts=3, base_delay=0)
    async def failing_operation():
        nonlocal calls
        calls += 1

        raise OSError("network failure")

    with pytest.raises(OSError, match="network failure"):
        await failing_operation()

    assert calls == 3

@pytest.mark.asyncio
async def test_retry_transient_unexpected_fallback():
    @retry_transient(max_attempts=0, base_delay=0)
    async def operation():
        return "success"

    with pytest.raises(RuntimeError, match="Email delivery failed unexpectedly"):
        await operation()

@pytest.mark.asyncio
async def test_retry_transient_raises_last_error_after_zero_attempt_path():
    @retry_transient(max_attempts=1, base_delay=0)
    async def operation():
        raise TimeoutError("final timeout")

    with pytest.raises(TimeoutError, match="final timeout"):
        await operation()