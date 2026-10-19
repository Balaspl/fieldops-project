"""Independent transactional SMTP email tests; all SMTP clients are mocked."""

import asyncio
import builtins
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.services.email.smtp_email import SMTPEmailService
from app.models.transactional_email_outbox import TransactionalEmailOutbox


@pytest.fixture
def smtp_service(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USERNAME", "sender@example.test")
    monkeypatch.setenv("SMTP_PASSWORD", "test-only-secret")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "sender@example.test")
    monkeypatch.setenv("SMTP_FROM_NAME", "FieldOps Test")
    client = Mock()
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    client.send_message = Mock()
    return SMTPEmailService(smtp_factory=lambda *args, **kwargs: client), client


def test_direct_booking_confirmation_sends_authoritative_job_data(smtp_service):
    service, client = smtp_service
    job = Mock(
        id=42,
        service_type="Electrical repair",
        location="12 Test Road",
        preferred_service_date=date(2026, 11, 3),
        preferred_time="10:00",
        status="CREATED",
    )

    result = asyncio.run(service.send_booking_confirmation(
        to_email="customer@example.com", customer_name="Test Customer", job=job,
        updates_url="https://fieldops.example/?tab=cust_tracking",
    ))

    assert result.success
    client.send_message.assert_called_once()
    message = client.send_message.call_args.args[0]
    assert message["Subject"] == "Your FieldOps service booking is confirmed"
    assert "#42" in message.get_body(preferencelist=("plain",)).get_content()
    assert "Electrical repair" in message.get_body(preferencelist=("plain",)).get_content()
    plain = message.get_body(preferencelist=("plain",)).get_content()
    assert "https://fieldops.example/?tab=cust_tracking" in plain
    html = message.get_body(preferencelist=("html",)).get_content()
    assert "Booking confirmed" in html
    assert "Check service updates" in html


def test_direct_invoice_email_includes_finalized_values_and_secure_url(smtp_service):
    service, client = smtp_service
    result = asyncio.run(service.send_invoice_email(
        to_email="customer@example.com",
        customer_name="Test Customer",
        job_id=42,
        invoice_number="INV-42",
        currency="INR",
        invoice_total=1234.5,
        completed_at=datetime(2026, 10, 17, 16, 41, 53, tzinfo=timezone.utc),
        secure_invoice_url="https://fieldops.example/?tab=cust_invoices",
        updates_url="https://fieldops.example/?tab=cust_tracking",
        invoice_pdf=b"%PDF-1.4\nmock invoice pdf",
    ))

    assert result.success
    client.send_message.assert_called_once()
    message = client.send_message.call_args.args[0]
    plain = message.get_body(preferencelist=("plain",)).get_content()
    assert "INV-42" in plain
    assert "INR 1234.50" in plain
    assert "Completed on: 2026-10-17" in plain
    assert "16:41:53" not in plain
    assert "https://fieldops.example/?tab=cust_invoices" in plain
    assert "https://fieldops.example/?tab=cust_tracking" in plain
    html = message.get_body(preferencelist=("html",)).get_content()
    assert "View secure invoice" in html
    assert "Check service updates" in html
    assert "<table" in html
    attachment = next(message.iter_attachments())
    assert attachment.get_filename() == "invoice_INV-42.pdf"
    assert attachment.get_content_type() == "application/pdf"
    assert attachment.get_payload(decode=True).startswith(b"%PDF")


def test_smtp_failure_is_returned_without_marking_success(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USERNAME", "sender@example.test")
    monkeypatch.setenv("SMTP_PASSWORD", "test-only-secret")
    client = Mock()
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    client.send_message.side_effect = TimeoutError()
    service = SMTPEmailService(smtp_factory=lambda *args, **kwargs: client)

    result = asyncio.run(service.send_booking_confirmation(
        to_email="customer@example.com", customer_name="Test", job=Mock(id=1),
    ))

    assert not result.success
    assert result.error == "SMTP transport failed."


def test_outbox_key_prevents_duplicate_logical_booking_emails():
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session

    from app.services.email.transactional_outbox import persist_booking_email

    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE transactional_email_outbox (
                id INTEGER PRIMARY KEY,
                tenant_id VARCHAR(50) NOT NULL,
                job_id INTEGER NOT NULL,
                customer_id VARCHAR(50),
                recipient_email VARCHAR(320),
                event_type VARCHAR(40) NOT NULL,
                event_version INTEGER NOT NULL,
                idempotency_key VARCHAR(180) NOT NULL UNIQUE,
                status VARCHAR(24) NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0
            )
        """))
    job = Mock(
        id=42, tenant_id="tenant-1", customer_tenant_id="tenant-1",
        customer_id="customer-1", customer_email="customer@example.test",
        notification_event_version=1,
    )

    with Session(engine) as db:
        persist_booking_email(db, job)
        persist_booking_email(db, job)
        db.commit()
        assert db.execute(text("SELECT count(*) FROM transactional_email_outbox")).scalar_one() == 1


class _FakeQuery:
    def __init__(self, model, values):
        self.model = model
        self.values = values

    def filter(self, *args, **kwargs):
        return self

    def filter_by(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def with_for_update(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def all(self):
        return self.values.get(self.model, [])

    def first(self):
        values = self.values.get(self.model, [])
        if self.model is TransactionalEmailOutbox:
            values = [
                row for row in values
                if row.status == "pending"
                and (row.next_attempt_at is None
                     or row.next_attempt_at <= datetime.now(timezone.utc))
            ]
        return values[0] if values else None


class _FakeSession:
    def __init__(self, values):
        self.values = values

    def query(self, model):
        return _FakeQuery(model, self.values)

    def flush(self):
        pass

    def commit(self):
        pass

    def rollback(self):
        pass

    def get(self, model, row_id):
        return next(
            (row for row in self.values.get(model, []) if row.id == row_id),
            None,
        )


@pytest.mark.parametrize("unavailable_dependency", ["agent", "Groq", "Kafka"])
def test_booking_outbox_sends_independently_of_ai_and_kafka(monkeypatch, unavailable_dependency):
    """Outbox worker needs only persisted job data and the SMTP service."""
    from app.models import Job
    from app.models.user import User
    from app.services.email.transactional_outbox import process_due_emails
    from app.services.email.smtp_email import EmailResult

    row = SimpleNamespace(
        id=1, tenant_id="tenant-1", job_id=42, customer_id="customer-1",
        recipient_email=None, event_type="booking_confirmation", event_version=1,
        idempotency_key="booking:tenant-1:42:1", status="pending", attempts=0,
        next_attempt_at=datetime.now(timezone.utc), last_error=None, smtp_status=None,
        provider_message_id=None, updated_at=None, sent_at=None,
    )
    job = SimpleNamespace(
        id=42, tenant_id="tenant-1", customer_tenant_id="tenant-1",
        customer_id="customer-1", customer_name="Test Customer",
        customer_email="customer@example.com", service_type="Repair",
        location="Test Road", preferred_service_date=date(2026, 11, 3),
        status="CREATED",
    )
    customer = SimpleNamespace(
        id="customer-1", tenant_id="tenant-1", email="customer@example.com",
        first_name="Test", last_name="Customer", is_active=True, deleted_at=None,
    )
    values = {TransactionalEmailOutbox: [row], Job: [job], User: [customer]}

    class DirectSMTP:
        async def send_booking_confirmation(self, **kwargs):
            assert kwargs["to_email"] == "customer@example.com"
            return EmailResult(True, message_id="mock-accepted", status_code=250)

    db = _FakeSession(values)
    original_import = builtins.__import__

    def block_ai_and_kafka_imports(name, *args, **kwargs):
        if name.startswith("app.services.ai") or name.startswith("langgraph") or name.startswith("kafka"):
            raise RuntimeError(f"{unavailable_dependency} unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", block_ai_and_kafka_imports)
    assert process_due_emails(db, email_service=DirectSMTP()) == 1
    assert row.status == "sent"
    assert row.provider_message_id == "mock-accepted"


def test_transient_smtp_failure_is_persisted_for_later_retry():
    from app.models import Job
    from app.models.user import User
    from app.services.email.transactional_outbox import process_due_emails
    from app.services.email.smtp_email import EmailResult

    row = SimpleNamespace(
        id=2, tenant_id="tenant-1", job_id=42, customer_id="customer-1",
        recipient_email=None, event_type="booking_confirmation", event_version=1,
        idempotency_key="booking:tenant-1:42:1", status="pending", attempts=0,
        next_attempt_at=datetime.now(timezone.utc), last_error=None, smtp_status=None,
        provider_message_id=None, updated_at=None, sent_at=None,
    )
    job = SimpleNamespace(
        id=42, tenant_id="tenant-1", customer_tenant_id="tenant-1",
        customer_id="customer-1", customer_name="Test Customer",
        customer_email="customer@example.com", service_type="Repair", location=None,
        preferred_service_date=date(2026, 11, 3), status="CREATED",
    )
    customer = SimpleNamespace(
        id="customer-1", tenant_id="tenant-1", email="customer@example.com",
        first_name="Test", last_name="Customer", is_active=True, deleted_at=None,
    )
    values = {TransactionalEmailOutbox: [row], Job: [job], User: [customer]}

    class TemporarilyUnavailableSMTP:
        async def send_booking_confirmation(self, **kwargs):
            return EmailResult(False, status_code=451, error="SMTP relay rejected the message.")

    assert process_due_emails(_FakeSession(values), email_service=TemporarilyUnavailableSMTP()) == 0
    assert row.status == "pending"
    assert row.attempts == 1
    assert row.next_attempt_at > datetime.now(timezone.utc)


def test_concurrent_outbox_pollers_do_not_send_same_claim(monkeypatch):
    from app.models import Job
    from app.models.user import User
    from app.services.email.transactional_outbox import process_due_emails
    from app.services.email.smtp_email import EmailResult

    row = SimpleNamespace(
        id=12, tenant_id="tenant-1", job_id=42, customer_id="customer-1",
        recipient_email=None, event_type="booking_confirmation", event_version=1,
        idempotency_key="booking:tenant-1:42:1", status="pending", attempts=0,
        next_attempt_at=datetime.now(timezone.utc), last_error=None, smtp_status=None,
        provider_message_id=None, updated_at=None, sent_at=None,
    )
    job = SimpleNamespace(
        id=42, tenant_id="tenant-1", customer_tenant_id="tenant-1",
        customer_id="customer-1", customer_name="Test Customer",
        customer_email="customer@example.com", service_type="Repair", location=None,
        preferred_service_date=date(2026, 11, 3), status="CREATED",
    )
    customer = SimpleNamespace(
        id="customer-1", tenant_id="tenant-1", email="customer@example.com",
        first_name="Test", last_name="Customer", is_active=True, deleted_at=None,
    )
    values = {TransactionalEmailOutbox: [row], Job: [job], User: [customer]}
    second_worker = _FakeSession(values)

    class SMTPWithConcurrentPoll:
        async def send_booking_confirmation(self, **kwargs):
            # The first poller has committed status=processing before SMTP.
            assert process_due_emails(second_worker, email_service=self) == 0
            return EmailResult(True, message_id="accepted-once", status_code=250)

    assert process_due_emails(_FakeSession(values), email_service=SMTPWithConcurrentPoll()) == 1
    assert row.status == "sent"
    assert row.attempts == 1


def test_invoice_outbox_refuses_cross_tenant_job():
    from app.models import Job
    from app.models.user import User
    from app.services.email.transactional_outbox import process_due_emails

    row = SimpleNamespace(
        id=3, tenant_id="tenant-other", job_id=42, customer_id="customer-1",
        recipient_email=None, event_type="invoice_finalized", event_version=2,
        idempotency_key="invoice:tenant-other:42:9", status="pending", attempts=0,
        next_attempt_at=datetime.now(timezone.utc), last_error=None, smtp_status=None,
        provider_message_id=None, updated_at=None, sent_at=None,
    )
    job = SimpleNamespace(
        id=42, tenant_id="tenant-1", customer_tenant_id="tenant-1",
        customer_id="customer-1", status="COMPLETED",
    )

    class MustNotSendSMTP:
        async def send_invoice_email(self, **kwargs):
            pytest.fail("Cross-tenant invoice must not be sent")

    values = {TransactionalEmailOutbox: [row], Job: [job], User: []}
    assert process_due_emails(_FakeSession(values), email_service=MustNotSendSMTP()) == 0
    assert row.status == "failed"
    assert row.last_error == "tenant_mismatch"


@pytest.mark.parametrize("finalized", [True, False])
def test_invoice_outbox_sends_only_for_persisted_finalized_invoice(finalized, monkeypatch):
    from app.models import Job
    from app.models.job_closure import JobClosure
    from app.models.user import User
    from app.services.email.transactional_outbox import process_due_emails
    from app.services.email.smtp_email import EmailResult

    row = SimpleNamespace(
        id=4, tenant_id="tenant-1", job_id=42, customer_id="customer-1",
        recipient_email=None, event_type="invoice_finalized", event_version=2,
        idempotency_key="invoice:tenant-1:42:9", status="pending", attempts=0,
        next_attempt_at=datetime.now(timezone.utc), last_error=None, smtp_status=None,
        provider_message_id=None, updated_at=None, sent_at=None,
    )
    job = SimpleNamespace(
        id=42, tenant_id="tenant-1", customer_tenant_id="tenant-1",
        customer_id="customer-1", customer_name="Test Customer",
        # The persisted closure is authoritative even if this workflow uses a
        # different job status label.
        customer_email="customer@example.com", status="CLOSED",
    )
    customer = SimpleNamespace(
        id="customer-1", tenant_id="tenant-1", email="customer@example.com",
        first_name="Test", last_name="Customer", is_active=True, deleted_at=None,
    )
    closure = SimpleNamespace(id=9, job_id=42, tenant_id="tenant-1", subtotal=100.0,
                              completed_at="2026-10-17")
    values = {TransactionalEmailOutbox: [row], Job: [job], User: [customer],
              JobClosure: [closure] if finalized else []}

    class InvoiceSMTP:
        async def send_invoice_email(self, **kwargs):
            assert kwargs["invoice_number"] == "9"
            assert kwargs["invoice_total"] == 105.0
            assert kwargs["updates_url"].endswith("/?tab=cust_tracking")
            assert kwargs["invoice_pdf"].startswith(b"%PDF")
            return EmailResult(True, message_id="invoice-accepted", status_code=250)

    service = InvoiceSMTP()
    if finalized:
        assert process_due_emails(_FakeSession(values), email_service=service) == 1
        assert row.status == "sent"
    else:
        assert process_due_emails(_FakeSession(values), email_service=service) == 0
        assert row.status == "pending"
        assert row.last_error == "invoice_not_finalized"

