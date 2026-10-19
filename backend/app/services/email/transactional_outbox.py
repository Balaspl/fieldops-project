"""Durable email delivery that has no Communication Agent or Kafka dependency."""

import asyncio
import hashlib
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, or_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.models import CustomerProfile, Job
from app.models.job_closure import JobClosure
from app.models.customer_signature import CustomerSignature
from app.models.transactional_email_outbox import TransactionalEmailOutbox
from app.models.user import User
from app.services.email.smtp_email import SMTPEmailService
from app.services.invoice_service import invoice_summary, render_invoice_pdf
from app.logger import logger

BOOKING = "booking_confirmation"
INVOICE = "invoice_finalized"
MAX_ATTEMPTS = 8
CLAIM_LEASE = timedelta(minutes=2)


def persist_booking_email(db, job: Job, *, customer_id: str | None = None,
                          tenant_id: str | None = None,
                          recipient_email: str | None = None) -> None:
    """Add one booking email obligation to the caller's job transaction."""
    customer_tenant = str(tenant_id or getattr(job, "customer_tenant_id", None) or job.tenant_id)
    version = int(getattr(job, "notification_event_version", None) or 1)
    _persist(db, TransactionalEmailOutbox(
        tenant_id=customer_tenant,
        job_id=int(job.id),
        customer_id=str(customer_id or getattr(job, "customer_id", "") or "") or None,
        recipient_email=(recipient_email or getattr(job, "customer_email", None)),
        event_type=BOOKING,
        event_version=version,
        idempotency_key=f"{BOOKING}:{customer_tenant}:{job.id}:{version}",
    ))


def persist_invoice_email(db, job: Job, closure: JobClosure) -> None:
    """Add an invoice email obligation in the persisted closure transaction."""
    customer_tenant = str(getattr(job, "customer_tenant_id", None) or job.tenant_id)
    version = int(getattr(job, "notification_event_version", None) or 1)
    _persist(db, TransactionalEmailOutbox(
        tenant_id=customer_tenant,
        job_id=int(job.id),
        customer_id=str(getattr(job, "customer_id", "") or "") or None,
        recipient_email=getattr(job, "customer_email", None),
        event_type=INVOICE,
        event_version=version,
        idempotency_key=f"{INVOICE}:{customer_tenant}:{job.id}:{closure.id}",
    ))


def _persist(db, row: TransactionalEmailOutbox) -> None:
    dialect = db.get_bind().dialect.name
    insert = pg_insert if dialect == "postgresql" else sqlite_insert if dialect == "sqlite" else None
    if insert is None:
        raise NotImplementedError(f"Transactional email outbox does not support {dialect}")
    db.execute(
        insert(TransactionalEmailOutbox)
        .values(
            tenant_id=row.tenant_id,
            job_id=row.job_id,
            customer_id=row.customer_id,
            recipient_email=row.recipient_email,
            event_type=row.event_type,
            event_version=row.event_version,
            idempotency_key=row.idempotency_key,
            status="pending",
            attempts=0,
        )
        .on_conflict_do_nothing(index_elements=["idempotency_key"])
    )


def _resolve_customer(db, row, job):
    expected_tenant = str(getattr(job, "customer_tenant_id", None) or job.tenant_id)
    if str(row.tenant_id) != expected_tenant:
        return None, "tenant_mismatch"
    if row.customer_id:
        if str(job.customer_id or "") != str(row.customer_id):
            return None, "customer_mismatch"
        user = (
            db.query(User)
            .filter(
                User.id == str(row.customer_id),
                User.tenant_id == str(row.tenant_id),
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
            .first()
        )
        if not user or not user.email:
            return None, "registered_customer_email_unavailable"
        profile = (
            db.query(CustomerProfile)
            .filter_by(tenant_id=str(row.tenant_id), customer_id=str(row.customer_id))
            .first()
        )
        if profile and not getattr(profile, "email_enabled", True):
            return None, "customer_email_preference_disabled"
        return user, None
    if not row.recipient_email or row.recipient_email != getattr(job, "customer_email", None):
        return None, "guest_email_unavailable"
    return type("GuestCustomer", (), {"email": row.recipient_email,
                                      "first_name": getattr(job, "customer_name", None),
                                      "last_name": ""})(), None


def process_due_emails(db, *, email_service: SMTPEmailService | None = None,
                       now: datetime | None = None, limit: int = 50) -> int:
    """Claim and send due rows directly via SMTP; retain failures for retry."""
    now = now or datetime.now(timezone.utc)
    service = email_service or SMTPEmailService()
    sent = 0
    processed = 0
    logger.debug("email_outbox_poll_started", extra={"limit": limit})
    while processed < limit:
        eligible = or_(
            and_(
                TransactionalEmailOutbox.status == "pending",
                or_(TransactionalEmailOutbox.next_attempt_at.is_(None),
                    TransactionalEmailOutbox.next_attempt_at <= now),
            ),
            and_(
                TransactionalEmailOutbox.status == "processing",
                TransactionalEmailOutbox.updated_at <= now - CLAIM_LEASE,
            ),
        )
        row = (
            db.query(TransactionalEmailOutbox)
            .filter(eligible)
            .order_by(TransactionalEmailOutbox.id.asc())
            .with_for_update(skip_locked=True)
            .first()
        )
        if row is None:
            db.rollback()
            break

        # Commit the claim before network I/O. Other pollers skip the active
        # lease, and an abandoned processing row becomes eligible after lease.
        row.status = "processing"
        row.attempts = int(row.attempts or 0) + 1
        row.updated_at = now
        row_id = int(row.id)
        event_type = row.event_type
        job_id = int(row.job_id)
        tenant_id = str(row.tenant_id)
        attempt = row.attempts
        key = row.idempotency_key
        db.commit()
        processed += 1
        logger.info(
            "email_delivery_started",
            extra={"outbox_id": row_id, "job_id": job_id,
                   "tenant_id": tenant_id, "attempt": attempt},
        )

        result = None
        failure_reason = None
        try:
            job = (
                db.query(Job)
                .filter(
                    Job.id == job_id,
                    func.coalesce(Job.customer_tenant_id, Job.tenant_id) == tenant_id,
                )
                .first()
            )
            customer, reason = _resolve_customer(db, row, job) if job else (None, "job_or_tenant_not_found")
            if not customer:
                if reason == "customer_email_preference_disabled":
                    db.rollback()
                    row = db.get(TransactionalEmailOutbox, row_id)
                    row.status = "suppressed"
                    row.last_error = reason
                    row.updated_at = now
                    db.commit()
                    logger.info(
                        "customer_email_suppressed",
                        extra={"outbox_id": row_id, "job_id": job_id,
                               "tenant_id": tenant_id, "reason": reason},
                    )
                    continue
                failure_reason = reason
            elif event_type == BOOKING:
                frontend = (os.getenv("FRONTEND_BASE_URL") or
                            os.getenv("FRONTEND_URL") or
                            "http://localhost:5173").rstrip("/")
                result = asyncio.run(service.send_booking_confirmation(
                    to_email=customer.email,
                    customer_name=(f"{getattr(customer, 'first_name', '') or ''} "
                                   f"{getattr(customer, 'last_name', '') or ''}").strip()
                                  or getattr(job, "customer_name", None) or "there",
                    job=job,
                    updates_url=f"{frontend}/?tab=cust_tracking",
                    message_id=_message_id(key),
                ))
            elif event_type == INVOICE:
                closure = (
                    db.query(JobClosure)
                    .filter(JobClosure.job_id == job.id,
                            JobClosure.tenant_id == job.tenant_id)
                    .order_by(JobClosure.completed_at.desc(), JobClosure.id.desc())
                    .first()
                )
                # A persisted closure is the authoritative invoice-finalization
                # record. Job status values vary across workflows; requiring a
                # particular label can strand a valid invoice in the outbox.
                if not closure:
                    failure_reason = "invoice_not_finalized"
                else:
                    invoice = invoice_summary(job, closure)
                    frontend = (os.getenv("FRONTEND_BASE_URL") or
                                os.getenv("FRONTEND_URL") or
                                "http://localhost:5173").rstrip("/")
                    invoice_url = f"{frontend}/?tab=cust_invoices"
                    updates_url = f"{frontend}/?tab=cust_tracking"
                    signature = (
                        db.query(CustomerSignature)
                        .filter(
                            CustomerSignature.job_id == job.id,
                            CustomerSignature.job_closure_id == closure.id,
                            CustomerSignature.tenant_id == job.tenant_id,
                        )
                        .first()
                    )
                    invoice_pdf = render_invoice_pdf(job, closure, signature)
                    result = asyncio.run(service.send_invoice_email(
                        to_email=customer.email,
                        customer_name=(f"{getattr(customer, 'first_name', '') or ''} "
                                       f"{getattr(customer, 'last_name', '') or ''}").strip()
                                      or getattr(job, "customer_name", None) or "there",
                        job_id=int(job.id),
                        invoice_number=invoice["invoice_number"],
                        currency=invoice["currency"],
                        invoice_total=invoice["total_amount"],
                        completed_at=invoice.get("completed_at"),
                        secure_invoice_url=invoice_url,
                        updates_url=updates_url,
                        invoice_pdf=invoice_pdf,
                        message_id=_message_id(key),
                    ))
            else:
                failure_reason = "unsupported_email_event"
        except Exception:
            db.rollback()
            failure_reason = "email_delivery_internal_error"

        if result and result.success:
            row = db.get(TransactionalEmailOutbox, row_id)
            row.status = "sent"
            row.sent_at = now
            row.last_error = None
            row.smtp_status = result.status_code
            row.provider_message_id = result.message_id
            row.updated_at = now
            db.commit()
            sent += 1
            logger.info(
                "email_delivery_sent",
                extra={"outbox_id": row_id, "job_id": job_id,
                       "tenant_id": tenant_id, "attempt": attempt,
                       "smtp_status": result.status_code},
            )
            continue

        reason = failure_reason or (result.error if result else "smtp_delivery_failed")
        status_code = result.status_code if result else None
        permanent = (
            reason in {"Invalid recipient email address.", "Recipient email is required.",
                       "tenant_mismatch", "customer_mismatch", "job_or_tenant_not_found",
                       "registered_customer_email_unavailable", "guest_email_unavailable",
                       "unsupported_email_event"}
            or status_code in {535, 550, 551, 553}
        )
        row = db.get(TransactionalEmailOutbox, row_id)
        row.smtp_status = status_code
        row.last_error = reason
        row.updated_at = now
        if permanent or attempt >= MAX_ATTEMPTS:
            row.status = "failed"
        else:
            row.status = "pending"
            row.next_attempt_at = now + timedelta(
                seconds=min(3600, 30 * (2 ** (attempt - 1)))
            )
        db.commit()
        _log_failure(row, reason)
    return sent


def _log_failure(row, reason: str) -> None:
    logger.warning(
        "email_delivery_failed",
        extra={"outbox_id": row.id, "job_id": row.job_id,
               "tenant_id": row.tenant_id, "attempt": row.attempts,
               "event_type": row.event_type, "reason": reason,
               "smtp_status": row.smtp_status,
               "outbox_status": row.status},
    )


def _message_id(idempotency_key: str) -> str:
    digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
    return f"<transactional-{digest}@fieldops.local>"
