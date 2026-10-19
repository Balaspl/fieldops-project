"""Transactional email delivery over standard SMTP (Gmail compatible)."""

import asyncio
import logging
import os
import smtplib
import uuid
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from html import escape

from email_validator import EmailNotValidError, validate_email

logger = logging.getLogger(__name__)


@dataclass
class EmailResult:
    success: bool
    message_id: str | None = None
    status_code: int | None = None
    error: str | None = None
    simulated: bool = False


class EmailDeliveryError(Exception):
    """SMTP delivery failure with an optional SMTP response status."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class SMTPEmailService:
    """Send one recipient per message so tenant and privacy rules stay clear."""

    def __init__(self, *, smtp_factory=None, timeout: float = 20.0):
        self.host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.port = int(os.getenv("SMTP_PORT", "587"))
        self.username = (os.getenv("SMTP_USERNAME") or "").strip()
        # Gmail displays app passwords in four-character groups; spaces are
        # formatting and must be removed before SMTP AUTH.
        self.password = "".join((os.getenv("SMTP_PASSWORD") or "").split())
        self.from_email = (os.getenv("SMTP_FROM_EMAIL") or self.username).strip()
        self.from_name = os.getenv("SMTP_FROM_NAME", "FieldOps")
        self.timeout = timeout
        self._smtp_factory = smtp_factory

    @staticmethod
    def validate_recipient(email: str) -> str:
        if not isinstance(email, str) or not email.strip():
            raise ValueError("Recipient email is required.")
        try:
            return validate_email(email.strip(), check_deliverability=False).normalized
        except EmailNotValidError as exc:
            raise ValueError("Invalid recipient email address.") from exc

    @staticmethod
    def _message_id(message: EmailMessage) -> str:
        return message.get("Message-ID", "").strip("<>") or uuid.uuid4().hex

    def _send_sync(self, message: EmailMessage) -> str:
        factory = self._smtp_factory or smtplib.SMTP
        # Port 465 uses implicit TLS; 587/2525 use STARTTLS.
        if self.port == 465:
            client = (self._smtp_factory or smtplib.SMTP_SSL)(
                self.host, self.port, timeout=self.timeout
            )
        else:
            client = factory(self.host, self.port, timeout=self.timeout)
        try:
            with client as server:
                if self.port != 465:
                    server.ehlo()
                    server.starttls()
                    server.ehlo()
                server.login(self.username, self.password)
                server.send_message(message)
        finally:
            # SMTP context manager closes the socket.
            pass
        return self._message_id(message)

    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        plain_text: str | None = None,
        attachments: list[dict] | None = None,
        message_id: str | None = None,
    ) -> EmailResult:
        try:
            recipient = self.validate_recipient(to_email)
            if not isinstance(subject, str) or not subject.strip():
                raise ValueError("Email subject is required.")
            if not isinstance(html_body, str) or not html_body.strip():
                raise ValueError("HTML email body is required.")
            if not all((self.username, self.password, self.from_email)):
                logger.warning("SMTP email not sent: configuration incomplete")
                return EmailResult(False, error="SMTP email configuration is incomplete.")

            message = EmailMessage()
            message["Subject"] = subject
            message["From"] = formataddr((self.from_name, self.from_email))
            message["To"] = recipient
            message["Message-ID"] = (
                message_id or f"<{uuid.uuid4().hex}@fieldops>"
            )
            message.set_content(plain_text or "This message is best viewed as HTML.")
            message.add_alternative(html_body, subtype="html")
            for attachment in attachments or []:
                if not isinstance(attachment, dict):
                    raise ValueError("Each attachment must be a dictionary.")
                filename = attachment.get("filename")
                content = attachment.get("content")
                if not filename or not isinstance(content, bytes):
                    raise ValueError("Attachment requires a filename and bytes content.")
                maintype, _, subtype = attachment.get("content_type", "application/octet-stream").partition("/")
                message.add_attachment(content, maintype=maintype, subtype=subtype or "octet-stream", filename=filename)

            message_id = await asyncio.to_thread(self._send_sync, message)
            logger.info("SMTP email accepted by relay", extra={"message_id": message_id})
            return EmailResult(True, message_id=message_id, status_code=250)
        except ValueError as exc:
            reason = str(exc)
            if reason == "Invalid recipient email address.":
                logger.warning("SMTP email not sent: invalid recipient")
            else:
                logger.warning("SMTP email not sent: invalid message data")
            return EmailResult(False, error=str(exc))
        except smtplib.SMTPRecipientsRefused as exc:
            # A single-recipient transaction is permanent when the relay
            # rejects that address. Do not log SMTP's recipient-keyed map.
            status_code = next(
                (
                    int(response[0])
                    for response in exc.recipients.values()
                    if response and response[0] is not None
                ),
                550,
            )
            logger.warning(
                "SMTP relay rejected recipient",
                extra={"smtp_status": status_code},
            )
            return EmailResult(
                False,
                status_code=status_code,
                error="SMTP relay rejected the recipient.",
            )
        except smtplib.SMTPResponseException as exc:
            # Do not include SMTP response text; relays may echo addresses or data.
            code = int(exc.smtp_code)
            logger.warning("SMTP relay rejected email", extra={"smtp_status": code})
            return EmailResult(False, status_code=code, error="SMTP relay rejected the message.")
        except (TimeoutError, ConnectionError, OSError, smtplib.SMTPException):
            logger.warning("SMTP email transport failed")
            return EmailResult(False, error="SMTP transport failed.")
        except Exception:
            logger.error("Unexpected SMTP email failure")
            return EmailResult(False, error="Email delivery failed.")

    async def send_bulk_email(self, recipients, subject, html_body, plain_text=None):
        if not isinstance(recipients, list) or not recipients:
            raise ValueError("At least one recipient is required.")
        return [await self.send_email(r, subject, html_body, plain_text) for r in recipients]

    async def send_booking_confirmation(
        self, *, to_email: str, customer_name: str, job,
        updates_url: str | None = None,
        message_id: str | None = None,
    ) -> EmailResult:
        """Send a deterministic booking confirmation without AI dependencies."""
        name = (customer_name or "there").strip() or "there"
        subject = "Your FieldOps service booking is confirmed"
        details = [f"Booking ID: #{job.id}"]
        if getattr(job, "service_type", None):
            details.append(f"Service: {job.service_type}")
        if getattr(job, "location", None):
            details.append(f"Service location: {job.location}")
        visit = " ".join(str(v) for v in (
            getattr(job, "preferred_service_date", None),
            getattr(job, "preferred_time", None),
        ) if v)
        if visit:
            details.append(f"Preferred visit: {visit}")
        if getattr(job, "status", None):
            details.append(f"Current status: {job.status}")
        plain = (
            f"Hi {name},\n\nThank you for choosing FieldOps! We have received your service booking.\n\n"
            + "\n".join(details)
            + "\n\nWe will keep you updated about your service request.\n\nThank you,\nFieldOps Team"
        )
        detail_rows = "".join(
            "<tr><td style='padding:10px 12px;color:#64748b;border-bottom:1px solid #e2e8f0'>"
            f"{escape(item.partition(':')[0])}</td><td style='padding:10px 12px;color:#0f172a;"
            f"font-weight:600;border-bottom:1px solid #e2e8f0'>{escape(item.partition(':')[2].strip())}</td></tr>"
            for item in details
        )
        button = ""
        if updates_url:
            safe_url = escape(updates_url, quote=True)
            button = (f"<a href='{safe_url}' style='display:inline-block;background:#0f766e;"
                      "color:#ffffff;text-decoration:none;padding:13px 20px;border-radius:8px;"
                      "font-weight:700'>Check service updates</a>")
            plain += f"\n\nCheck service updates: {updates_url}"
        html = (
            "<div style='margin:0;background:#f1f5f9;padding:32px 12px;font-family:Arial,Helvetica,sans-serif;color:#0f172a'>"
            "<div style='max-width:600px;margin:0 auto;background:#ffffff;border-radius:14px;overflow:hidden;"
            "box-shadow:0 8px 28px rgba(15,23,42,.08)'>"
            "<div style='background:#0f766e;padding:25px 30px;color:#ffffff'>"
            "<div style='font-size:13px;letter-spacing:1.5px;text-transform:uppercase;opacity:.85'>FieldOps</div>"
            "<h1 style='font-size:24px;line-height:1.3;margin:10px 0 0'>Booking confirmed</h1></div>"
            "<div style='padding:28px 30px'><p style='font-size:16px'>Hi " + escape(name) + ",</p>"
            "<p style='color:#475569;line-height:1.6'>Thanks for choosing FieldOps. Your service booking is confirmed, and our team will keep you updated.</p>"
            "<table role='presentation' style='width:100%;border-collapse:collapse;background:#f8fafc;border-radius:8px'>"
            + detail_rows + "</table><div style='margin:26px 0'>" + button + "</div>"
            "<p style='color:#64748b;font-size:13px;line-height:1.6'>If the button does not work, copy the service updates link into your browser.</p>"
            "<p style='margin-top:26px'>Thank you,<br><strong>FieldOps Team</strong></p></div>"
            "<div style='background:#f8fafc;padding:16px 30px;color:#94a3b8;font-size:12px'>FieldOps service notifications</div>"
            "</div></div>"
        )
        return await self.send_email(to_email, subject, html, plain, message_id=message_id)

    async def send_invoice_email(
        self, *, to_email: str, customer_name: str, job_id: int,
        invoice_number: str, currency: str, invoice_total: float,
        completed_at, secure_invoice_url: str | None,
        updates_url: str | None = None,
        invoice_pdf: bytes | None = None,
        message_id: str | None = None,
    ) -> EmailResult:
        """Send authoritative finalized invoice details through SMTP."""
        name = (customer_name or "there").strip() or "there"
        subject = f"Your FieldOps service is complete — invoice #{invoice_number}"
        details = [
            f"Booking ID: #{job_id}",
            f"Invoice number: {invoice_number}",
            f"Total amount: {currency} {invoice_total:.2f}",
        ]
        if completed_at:
            # Show the completion date without a time-of-day timestamp.
            if hasattr(completed_at, "date"):
                completed_date = completed_at.date().isoformat()
            else:
                completed_date = str(completed_at).split("T", 1)[0].split(" ", 1)[0]
            details.append(f"Completed on: {completed_date}")
        plain = (
            f"Hi {name},\n\nYour FieldOps service has been completed successfully.\n\n"
            + "\n".join(details)
        )
        rows = "".join(
            "<tr><td style='padding:11px 12px;color:#64748b;border-bottom:1px solid #e2e8f0'>"
            f"{escape(item.partition(':')[0])}</td><td style='padding:11px 12px;color:#0f172a;"
            f"font-weight:600;text-align:right;border-bottom:1px solid #e2e8f0'>{escape(item.partition(':')[2].strip())}</td></tr>"
            for item in details
        )
        invoice_button = ""
        if secure_invoice_url:
            safe_url = escape(secure_invoice_url, quote=True)
            invoice_button = (f"<a href='{safe_url}' style='display:inline-block;background:#0f766e;"
                              "color:#ffffff;text-decoration:none;padding:13px 20px;border-radius:8px;"
                              "font-weight:700'>View secure invoice</a>")
            plain += f"\n\nView your invoice securely: {secure_invoice_url}"
        updates_button = ""
        if updates_url:
            safe_updates_url = escape(updates_url, quote=True)
            updates_button = (f"<a href='{safe_updates_url}' style='display:inline-block;background:#ffffff;"
                              "color:#0f766e;text-decoration:none;padding:12px 18px;border-radius:8px;"
                              "font-weight:700;border:1px solid #0f766e'>Check service updates</a>")
            plain += f"\n\nCheck service updates: {updates_url}"
        if invoice_pdf:
            plain += "\n\nA PDF copy of your invoice is attached for download."
        plain += "\n\nThank you for choosing FieldOps.\n\nBest regards,\nFieldOps Team"
        html = (
            "<div style='margin:0;background:#f1f5f9;padding:32px 12px;font-family:Arial,Helvetica,sans-serif;color:#0f172a'>"
            "<div style='max-width:600px;margin:0 auto;background:#ffffff;border-radius:14px;overflow:hidden;"
            "box-shadow:0 8px 28px rgba(15,23,42,.08)'>"
            "<div style='background:#0f766e;padding:25px 30px;color:#ffffff'>"
            "<div style='font-size:13px;letter-spacing:1.5px;text-transform:uppercase;opacity:.85'>FieldOps</div>"
            "<h1 style='font-size:24px;line-height:1.3;margin:10px 0 0'>Service complete</h1></div>"
            "<div style='padding:28px 30px'><p style='font-size:16px'>Hi " + escape(name) + ",</p>"
            "<p style='color:#475569;line-height:1.6'>Your FieldOps service is complete. Here is your finalized invoice summary.</p>"
            "<table role='presentation' style='width:100%;border-collapse:collapse;background:#f8fafc;border-radius:8px'>"
            + rows + "</table><div style='margin:26px 0;display:flex;gap:10px;flex-wrap:wrap'>"
            + invoice_button + updates_button + "</div>"
            "<p style='color:#475569;line-height:1.6'>A PDF copy of your invoice is attached for download.</p>"
            "<p style='color:#64748b;font-size:13px;line-height:1.6'>Your invoice link opens the customer invoice area. Sign in if prompted.</p>"
            "<p style='margin-top:26px'>Thank you for choosing FieldOps.<br><strong>FieldOps Team</strong></p></div>"
            "<div style='background:#f8fafc;padding:16px 30px;color:#94a3b8;font-size:12px'>FieldOps service notifications</div>"
            "</div></div>"
        )
        attachments = ([{
            "filename": f"invoice_{invoice_number}.pdf",
            "content": invoice_pdf,
            "content_type": "application/pdf",
        }] if invoice_pdf else None)
        return await self.send_email(
            to_email, subject, html, plain,
            attachments=attachments,
            message_id=message_id,
        )
