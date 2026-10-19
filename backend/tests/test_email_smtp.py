import asyncio
from email import message_from_bytes
from unittest.mock import MagicMock

import pytest
from types import SimpleNamespace
from types import SimpleNamespace

from app.services.email.smtp_email import SMTPEmailService


class FakeSMTP:
    def __init__(self, host, port, timeout=None):
        self.host, self.port, self.timeout = host, port, timeout
        self.messages = []
        self.calls = []
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def ehlo(self): self.calls.append("ehlo")
    def starttls(self): self.calls.append("starttls")
    def login(self, username, password): self.calls.append(("login", username, password))
    def send_message(self, message): self.messages.append(message)


@pytest.fixture
def smtp_env(monkeypatch):
    for key, value in {
        "SMTP_HOST": "smtp.gmail.com", "SMTP_PORT": "587",
        "SMTP_USERNAME": "smtp-user@example.test", "SMTP_PASSWORD": "test-secret",
        "SMTP_FROM_EMAIL": "notifications@example.test", "SMTP_FROM_NAME": "FieldOps Tests",
    }.items(): monkeypatch.setenv(key, value)


@pytest.mark.asyncio
async def test_smtp_email_uses_starttls_and_configured_sender(smtp_env):
    clients = []
    def factory(*args, **kwargs):
        client = FakeSMTP(*args, **kwargs); clients.append(client); return client
    service = SMTPEmailService(smtp_factory=factory)
    result = await service.send_email(
        "customer@example.com", "Job update", "<p>Ready</p>", "Ready",
        message_id="<delivery-42@fieldops.local>",
    )
    assert result.success
    assert clients[0].calls == ["ehlo", "starttls", "ehlo", ("login", "smtp-user@example.test", "test-secret")]
    message = clients[0].messages[0]
    assert message["Message-ID"] == "<delivery-42@fieldops.local>"
    assert message["To"] == "customer@example.com"
    assert message["From"] == 'FieldOps Tests <notifications@example.test>'
    assert message.get_body(preferencelist=("plain",)).get_content().strip() == "Ready"
    assert message.get_body(preferencelist=("html",)).get_content().strip() == "<p>Ready</p>"


@pytest.mark.asyncio
async def test_smtp_email_uses_implicit_tls_on_465(smtp_env, monkeypatch):
    monkeypatch.setenv("SMTP_PORT", "465")
    client = FakeSMTP("smtp.gmail.com", 465)
    factory = MagicMock(return_value=client)
    service = SMTPEmailService(smtp_factory=factory)
    result = await service.send_email("customer@example.com", "Subject", "<p>Body</p>")
    assert result.success
    assert client.calls == [("login", "smtp-user@example.test", "test-secret")]


@pytest.mark.asyncio
async def test_smtp_failure_does_not_leak_credentials_or_invoice_content(smtp_env, caplog):
    class FailingSMTP(FakeSMTP):
        def send_message(self, message): raise OSError("failure with test-secret and invoice token")
    service = SMTPEmailService(smtp_factory=FailingSMTP)
    result = await service.send_email("customer@example.com", "Invoice", "<p>secret-link</p>")
    assert not result.success
    assert "test-secret" not in caplog.text
    assert "secret-link" not in caplog.text
    assert "invoice token" not in caplog.text


@pytest.mark.asyncio
async def test_smtp_message_can_attach_invoice_pdf(smtp_env):
    clients = []
    def factory(*args, **kwargs):
        client = FakeSMTP(*args, **kwargs); clients.append(client); return client
    service = SMTPEmailService(smtp_factory=factory)
    result = await service.send_email("customer@example.com", "Invoice", "<p>Ready</p>", attachments=[{"filename": "invoice.pdf", "content": b"pdf", "content_type": "application/pdf"}])
    assert result.success
    assert clients[0].messages[0].iter_attachments().__next__().get_filename() == "invoice.pdf"


@pytest.mark.asyncio
async def test_smtp_invalid_recipient_is_rejected_without_connecting(smtp_env):
    factory = MagicMock(side_effect=AssertionError("SMTP must not be opened"))
    service = SMTPEmailService(smtp_factory=factory)
    result = await service.send_email("not-an-email", "Subject", "<p>Body</p>")
    assert not result.success
    assert result.error == "Invalid recipient email address."
    factory.assert_not_called()


@pytest.mark.asyncio
async def test_smtp_recipient_refusal_is_permanent_and_redacted(smtp_env, caplog):
    class RefusingSMTP(FakeSMTP):
        def send_message(self, message):
            raise __import__("smtplib").SMTPRecipientsRefused(
                {"customer@example.com": (550, b"bad recipient customer@example.com")}
            )

    service = SMTPEmailService(smtp_factory=RefusingSMTP)
    result = await service.send_email("customer@example.com", "Subject", "<p>Body</p>")
    assert not result.success
    assert result.status_code == 550
    assert "customer@example.com" not in caplog.text


def test_email_task_retries_temporary_failures_without_real_smtp(monkeypatch):
    import app.tasks as tasks
    from celery.exceptions import Retry

    results = [
        SimpleNamespace(
            success=False, status_code=451,
            error="SMTP relay rejected the message.", message_id=None,
            simulated=False,
        ),
        SimpleNamespace(
            success=True, status_code=250, error=None,
            message_id="test-message-id", simulated=False,
        ),
    ]
    send_calls = []

    class FakeEmailService:
        async def send_email(self, **kwargs):
            send_calls.append(kwargs)
            return results.pop(0)

    original_service = tasks.SMTPEmailService
    original_retry = tasks.send_email_async.retry
    original_retries = tasks.send_email_async.request.retries
    retries = []

    def retry(*, exc, countdown):
        retries.append((str(exc), countdown))
        tasks.send_email_async.request.retries += 1
        raise Retry("celery retry requested")

    monkeypatch.setattr(tasks, "SMTPEmailService", FakeEmailService)
    tasks.send_email_async.retry = retry
    tasks.send_email_async.request.retries = 0
    try:
        with pytest.raises(Retry, match="celery retry requested"):
            tasks.send_email_async.run(
                "customer@example.com", "Subject", "<p>Body</p>"
            )

        result = tasks.send_email_async.run(
            "customer@example.com", "Subject", "<p>Body</p>"
        )
        assert result["success"] is True
        assert len(retries) == 1
        assert "Temporary email provider failure" in retries[0][0]
        assert retries[0][1] == 2
        assert len(send_calls) == 2
    finally:
        tasks.SMTPEmailService = original_service
        tasks.send_email_async.retry = original_retry
        tasks.send_email_async.request.retries = original_retries


def test_invoice_pdf_attachment_checks_customer_and_tenant_ownership(monkeypatch):
    import app.tasks as tasks
    from app.models.job_closure import JobClosure
    from app.models_legacy import InAppNotification, NotificationChannelDelivery
    from app.models import Job
    from app.routes import jobs as jobs_route

    delivery = SimpleNamespace(
        id=7, notification_id="notification-1", tenant_id="customer-tenant",
        channel="email",
    )
    notification = SimpleNamespace(
        tenant_id="customer-tenant", job_id="41",
        recipient_role="customer", recipient_id="customer-user",
    )
    job = SimpleNamespace(
        id=41, customer_id="customer-user", customer_tenant_id="customer-tenant",
        tenant_id="provider-tenant", status="COMPLETED",
    )
    closure = SimpleNamespace(id=12, job_id=41, tenant_id="provider-tenant")

    class Query:
        def __init__(self, result): self.result = result
        def filter(self, *args, **kwargs): return self
        def first(self): return self.result

    class DB:
        def query(self, model):
            if model is NotificationChannelDelivery: return Query(delivery)
            if model is JobClosure: return Query(closure)
            raise AssertionError(f"Unexpected query model: {model}")
        def get(self, model, key):
            if model is InAppNotification: return notification
            if model is Job: return job
            return None
        def close(self): pass

    async def pdf_chunks():
        yield b"%PDF-mocked-invoice"

    route_mock = MagicMock(
        return_value=SimpleNamespace(body_iterator=pdf_chunks())
    )
    monkeypatch.setattr(tasks, "SessionLocal", DB)
    monkeypatch.setattr(jobs_route, "download_job_invoice_pdf", route_mock)

    attachment = tasks._build_customer_invoice_pdf_attachment(7, 41, 12)
    assert attachment == {
        "filename": "invoice_job_41.pdf",
        "content": b"%PDF-mocked-invoice",
        "content_type": "application/pdf",
    }
    route_mock.assert_called_once()

    notification.recipient_id = "another-customer"
    route_mock.reset_mock()
    assert tasks._build_customer_invoice_pdf_attachment(7, 41, 12) is None
    route_mock.assert_not_called()


def test_email_task_retries_temporary_failures_without_real_smtp(monkeypatch):
    import app.tasks as tasks
    from celery.exceptions import Retry

    results = [
        SimpleNamespace(
            success=False, status_code=451,
            error="SMTP relay rejected the message.", message_id=None,
            simulated=False,
        ),
        SimpleNamespace(
            success=True, status_code=250, error=None,
            message_id="test-message-id", simulated=False,
        ),
    ]
    send_calls = []

    class FakeEmailService:
        async def send_email(self, **kwargs):
            send_calls.append(kwargs)
            return results.pop(0)

    original_service = tasks.SMTPEmailService
    original_retry = tasks.send_email_async.retry
    original_retries = tasks.send_email_async.request.retries
    retries = []

    def retry(*, exc, countdown):
        retries.append((str(exc), countdown))
        tasks.send_email_async.request.retries += 1
        raise Retry("celery retry requested")

    monkeypatch.setattr(tasks, "SMTPEmailService", FakeEmailService)
    tasks.send_email_async.retry = retry
    tasks.send_email_async.request.retries = 0
    try:
        with pytest.raises(Retry, match="celery retry requested"):
            tasks.send_email_async.run(
                "customer@example.com", "Subject", "<p>Body</p>"
            )

        result = tasks.send_email_async.run(
            "customer@example.com", "Subject", "<p>Body</p>"
        )
        assert result["success"] is True
        assert len(retries) == 1
        assert "Temporary email provider failure" in retries[0][0]
        assert retries[0][1] == 2
        assert len(send_calls) == 2
    finally:
        tasks.SMTPEmailService = original_service
        tasks.send_email_async.retry = original_retry
        tasks.send_email_async.request.retries = original_retries
