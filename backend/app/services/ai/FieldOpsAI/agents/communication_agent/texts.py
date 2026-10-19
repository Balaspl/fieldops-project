"""Text helpers: emoji stripping, tracking link, SMS/email bodies, validation."""
import os
import re
from datetime import datetime, timezone
from html import escape

_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002300-\U000023FF\U00002600-\U000027BF\U0000FE0F\U0000200D]+"
)


def strip_emoji(text: str) -> str:
    """Emojis in SMS force expensive UCS-2 encoding, so SMS/email subjects drop them."""
    return re.sub(r"\s{2,}", " ", _EMOJI_RE.sub("", text or "")).strip()


def tracking_link(job) -> str | None:
    """Public tracking link built from Job.share_token. Needs FRONTEND_BASE_URL in .env."""
    base = os.getenv("FRONTEND_BASE_URL", "").rstrip("/")
    token = getattr(job, "share_token", None)
    if not base or not token:
        return None
    expires = getattr(job, "share_expires", None)
    if expires:
        try:
            dt = datetime.fromisoformat(expires)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt < datetime.now(timezone.utc):
                return None
        except ValueError:
            return None
    return f"{base}/track/{token}"          # placeholder route: match your frontend


def sms_text(title: str, body: str, link: str | None) -> str:
    text = f"FieldOps: {strip_emoji(title)} {strip_emoji(body)}".strip()[:200]
    return f"{text} Track: {link}" if link else text


def email_content(title: str, body: str, job, link: str | None, event=None) -> dict:
    event_value = getattr(event, "value", event)
    customer_name = (getattr(job, "customer_name", None) or "there").strip()
    if event_value == "job_created":
        subject = "Your FieldOps service is booked!"
        plain_body = (
            f"Hi {customer_name},\n\n"
            "Thank you for booking with FieldOps. We've received your service "
            "request and are getting things ready. We'll keep you updated as "
            "your service progresses.\n\nThank you for choosing FieldOps.\n"
            "FieldOps Team"
        )
    elif event_value == "invoice_ready":
        invoice_number = getattr(job, "invoice_number", None) or getattr(job, "closure_id", None)
        subject = f"Your FieldOps service is complete — invoice #{invoice_number}"
        plain_body = (
            f"Hi {customer_name},\n\n"
            "Good news! Your FieldOps service has been completed successfully. "
            "Your finalized invoice is ready. Thank you for choosing FieldOps.\n\n"
            "FieldOps Team"
        )
    else:
        subject = strip_emoji(title)
        plain_body = strip_emoji(body)
    button = (
        f'<p><a href="{escape(link)}" style="background:#f97316;color:#fff;'
        f'padding:10px 18px;border-radius:8px;text-decoration:none">Track your job</a></p>'
        if link else ""
    )
    details = []
    if event_value == "job_created":
        details.extend((
            f"Booking ID: #{job.id}",
            f"Service: {getattr(job, 'service_type', None) or 'Not specified'}",
            f"Location: {getattr(job, 'location', None) or 'Not specified'}",
            f"Preferred visit: {getattr(job, 'preferred_service_date', None) or 'Not specified'}",
            f"Current status: {getattr(job, 'status', None) or 'Not specified'}",
        ))
    elif event_value == "completed":
        details.extend((
            f"Completed: {getattr(job, 'completed_at', None) or 'Not available'}",
            f"Summary: {getattr(job, 'work_report', None) or 'Service completed.'}",
        ))
    elif event_value in {"technician_assigned", "technician_accepted", "en_route", "on_site", "service_started"}:
        technician = getattr(job, "technician_name", None)
        if technician:
            details.append(f"Technician: {technician}")
    elif event_value == "cancelled":
        reason = getattr(job, "cancellation_reason", None)
        if reason:
            details.append(f"Cancellation reason: {reason}")
    elif event_value == "invoice_ready":
        total = getattr(job, "invoice_total", None)
        currency = getattr(job, "currency", None)
        details.extend((
            f"Booking ID: #{job.id}",
            f"Service: {getattr(job, 'service_type', None) or 'Not specified'}",
            f"Completed on: {getattr(job, 'completed_at', None) or 'Not available'}",
            f"Invoice number: {getattr(job, 'invoice_number', None) or getattr(job, 'closure_id', None)}",
            f"Total amount: {currency} {total:.2f}" if currency and isinstance(total, (int, float)) else "Total amount: Not available",
        ))
    details_html = "".join(f"<li>{escape(str(item))}</li>" for item in details)
    invoice_link = getattr(job, "invoice_link", None)
    invoice_button = (
        f'<p><a href="{escape(invoice_link, quote=True)}">View invoice</a></p>'
        if event_value == "invoice_ready" and invoice_link
        else ""
    )
    html = (
        '<div style="font-family:Arial,sans-serif;max-width:480px;margin:auto">'
        f"<h2>{escape(subject)}</h2><p>{escape(plain_body)}</p>"
        f'<p style="color:#666">Job #{job.id} &middot; {escape(job.service_type or "")}</p>'
        f"<ul>{details_html}</ul>{invoice_button}"
        f"{button}</div>"
    )
    plain = f"{subject}\n\n{plain_body}\n\nJob #{job.id}"
    if details:
        plain += "\n" + "\n".join(details)
    if event_value == "invoice_ready" and invoice_link:
        plain += f"\nView invoice: {invoice_link}"
    plain += f"\nTrack: {link}" if link else ""
    # keys match send_email_async(...) arguments
    return {"subject": subject, "html_body": html, "plain_text": plain}


def validate_text(title: str, body: str) -> tuple[bool, str]:
    """Basic checks. This is where your BrandSafetyValidator / guardrails plug in."""
    if not title or not title.strip():
        return False, "empty title"
    if len(title) > 200:
        return False, "title too long"
    if body is not None and len(body) > 1000:
        return False, "body too long"
    for text in (title, body or ""):
        if "None" in text or "{" in text or "}" in text:
            return False, "unresolved placeholder"
    return True, ""
