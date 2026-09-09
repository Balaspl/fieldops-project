"""
SendGrid email delivery service.

Provides validated, transactional email delivery with:
- SendGrid API integration
- HTML + plain-text content
- Attachments
- Bulk email support
- Test mode
- Delivery result/message ID
- Transient error handling
"""

import asyncio
import base64
import logging
import os
import re
import uuid
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable

from email_validator import EmailNotValidError, validate_email
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import (
    Attachment,
    Content,
    Disposition,
    FileContent,
    FileName,
    FileType,
    Mail,
)

logger = logging.getLogger(__name__)


@dataclass
class EmailResult:
    """Result returned by an email delivery attempt."""

    success: bool
    message_id: str | None = None
    status_code: int | None = None
    error: str | None = None
    simulated: bool = False


class EmailDeliveryError(Exception):
    """Raised when SendGrid rejects or fails an email delivery."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code


def retry_transient(
    max_attempts: int = 3,
    base_delay: float = 1.0,
):
    """
    Retry only transient delivery failures.

    Transient failures:
    - HTTP 429
    - HTTP 5xx
    - connection/time-out style exceptions
    """

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_error = None

            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)

                except EmailDeliveryError as exc:
                    last_error = exc

                    if exc.status_code not in {429, 500, 502, 503, 504}:
                        raise

                    if attempt == max_attempts - 1:
                        raise

                    delay = base_delay * (2**attempt)

                    logger.warning(
                        "Transient SendGrid error. "
                        "Retrying attempt %s/%s in %.1f seconds.",
                        attempt + 2,
                        max_attempts,
                        delay,
                    )

                    await asyncio.sleep(delay)

                except (TimeoutError, ConnectionError, OSError) as exc:
                    last_error = exc

                    if attempt == max_attempts - 1:
                        raise

                    delay = base_delay * (2**attempt)

                    logger.warning(
                        "Transient email transport error. "
                        "Retrying attempt %s/%s in %.1f seconds.",
                        attempt + 2,
                        max_attempts,
                        delay,
                    )

                    await asyncio.sleep(delay)

            raise RuntimeError("Email delivery failed unexpectedly.")

        return wrapper

    return decorator


class SendGridEmailService:
    """Service responsible for transactional email delivery through SendGrid."""

    def __init__(
        self,
        api_key: str | None = None,
        from_email: str | None = None,
        test_mode: bool | None = None,
    ):
        self.api_key = api_key or os.getenv("SENDGRID_API_KEY")
        self.from_email = (
            from_email
            or os.getenv("SENDGRID_FROM_EMAIL")
            or "no-reply@fieldops.io"
        )

        if test_mode is None:
            self.test_mode = (
                os.getenv("SENDGRID_TEST_MODE", "false").lower()
                in {"true", "1", "yes", "on"}
            )
        else:
            self.test_mode = test_mode

        self._client = None

        if self.api_key and not self.test_mode:
            self._client = SendGridAPIClient(self.api_key)

    @staticmethod
    def validate_recipient(email: str) -> str:
        """Validate and normalize a recipient email address."""

        if not isinstance(email, str) or not email.strip():
            raise ValueError("Recipient email is required.")

        try:
            result = validate_email(
                email.strip(),
                check_deliverability=False,
            )
            return result.normalized

        except EmailNotValidError as exc:
            raise ValueError(
                f"Invalid recipient email address: {email}"
            ) from exc

    @staticmethod
    def _validate_subject(subject: str) -> None:
        if not isinstance(subject, str) or not subject.strip():
            raise ValueError("Email subject is required.")

    @staticmethod
    def _validate_html_body(html_body: str) -> None:
        if not isinstance(html_body, str) or not html_body.strip():
            raise ValueError("HTML email body is required.")

    @staticmethod
    def _prepare_attachment(attachment: dict[str, Any]) -> Attachment:
        """
        Convert an attachment dictionary into a SendGrid Attachment.

        Expected format:

        {
            "filename": "report.pdf",
            "content": b"...",
            "content_type": "application/pdf"
        }
        """

        if not isinstance(attachment, dict):
            raise ValueError("Each attachment must be a dictionary.")

        filename = attachment.get("filename")
        content = attachment.get("content")
        content_type = attachment.get(
            "content_type",
            "application/octet-stream",
        )

        if not filename:
            raise ValueError("Attachment filename is required.")

        if content is None:
            raise ValueError(
                f"Attachment content is required for {filename}."
            )

        if isinstance(content, str):
            encoded_content = content
        elif isinstance(content, bytes):
            encoded_content = base64.b64encode(content).decode("ascii")
        else:
            raise ValueError(
                f"Attachment content for {filename} must be bytes or base64 text."
            )

        attachment_obj = Attachment()
        attachment_obj.file_content = FileContent(encoded_content)
        attachment_obj.file_name = FileName(filename)
        attachment_obj.file_type = FileType(content_type)
        attachment_obj.disposition = Disposition("attachment")

        return attachment_obj

    def _build_message(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        plain_text: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> Mail:
        """Build a SendGrid Mail object."""

        contents = []

        if plain_text:
            contents.append(
                Content(
                    "text/plain",
                    plain_text,
                )
            )

        contents.append(
            Content(
                "text/html",
                html_body,
            )
        )

        message = Mail(
            from_email=self.from_email,
            to_emails=to_email,
            subject=subject,
        )

        for content in contents:
            message.add_content(content)

        for attachment in attachments or []:
            message.add_attachment(
                self._prepare_attachment(attachment)
            )

        return message

    @staticmethod
    def _extract_status_code(exception: Exception) -> int | None:
        """Extract an HTTP status code from a SendGrid exception."""

        response = getattr(exception, "response", None)

        if response is None:
            return None

        status_code = getattr(response, "status_code", None)

        try:
            return int(status_code) if status_code is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _extract_message_id(response: Any) -> str | None:
        """Extract SendGrid's message ID from response headers."""

        headers = getattr(response, "headers", None)

        if not headers:
            return None

        for key, value in headers.items():
            if str(key).lower() == "x-message-id":
                return str(value)

        return None

    @staticmethod
    def _safe_subject_preview(subject: str) -> str:
        """Create a short subject preview for logs."""

        preview = re.sub(r"\s+", " ", subject.strip())

        if len(preview) > 80:
            return preview[:77] + "..."

        return preview

    @retry_transient(max_attempts=3, base_delay=1.0)
    async def _send_with_provider(
        self,
        message: Mail,
    ) -> tuple[int, str | None]:
        """Send a prepared message through SendGrid."""

        if self._client is None:
            raise EmailDeliveryError(
                "SendGrid client is not configured.",
            )

        try:
            response = await asyncio.to_thread(
                self._client.send,
                message,
            )

        except Exception as exc:
            status_code = self._extract_status_code(exc)

            raise EmailDeliveryError(
                f"SendGrid transport error: {exc}",
                status_code=status_code,
            ) from exc

        status_code = int(response.status_code)

        if status_code < 200 or status_code >= 300:
            raise EmailDeliveryError(
                f"SendGrid rejected email with status {status_code}.",
                status_code=status_code,
            )

        message_id = self._extract_message_id(response)

        return status_code, message_id

    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        plain_text: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> EmailResult:
        """
        Send one transactional email.

        Returns:
            EmailResult containing delivery status and SendGrid message ID.
        """

        normalized_email = self.validate_recipient(to_email)
        self._validate_subject(subject)
        self._validate_html_body(html_body)

        timestamp = __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat()

        subject_preview = self._safe_subject_preview(subject)

        logger.info(
            "Email delivery attempt: recipient=%s subject=%s timestamp=%s",
            normalized_email,
            subject_preview,
            timestamp,
        )

        if self.test_mode:
            message_id = f"SGTEST_{uuid.uuid4().hex}"

            logger.info(
                "SendGrid test mode enabled: recipient=%s "
                "subject=%s status=simulated message_id=%s",
                normalized_email,
                subject_preview,
                message_id,
            )

            return EmailResult(
                success=True,
                message_id=message_id,
                status_code=202,
                simulated=True,
            )

        if not self.api_key:
            error = "SENDGRID_API_KEY is not configured."

            logger.error(
                "Email delivery failed: recipient=%s subject=%s error=%s",
                normalized_email,
                subject_preview,
                error,
            )

            return EmailResult(
                success=False,
                error=error,
            )

        try:
            message = self._build_message(
                to_email=normalized_email,
                subject=subject,
                html_body=html_body,
                plain_text=plain_text,
                attachments=attachments,
            )

            status_code, message_id = await self._send_with_provider(
                message
            )

            logger.info(
                "Email delivery accepted: recipient=%s "
                "subject=%s status=%s message_id=%s",
                normalized_email,
                subject_preview,
                status_code,
                message_id,
            )

            return EmailResult(
                success=True,
                message_id=message_id,
                status_code=status_code,
            )

        except EmailDeliveryError as exc:
            logger.error(
                "Email delivery failed: recipient=%s "
                "subject=%s status=%s error=%s",
                normalized_email,
                subject_preview,
                exc.status_code,
                str(exc),
            )

            return EmailResult(
                success=False,
                status_code=exc.status_code,
                error=str(exc),
            )

        except Exception as exc:
            logger.exception(
                "Unexpected email delivery failure: recipient=%s subject=%s",
                normalized_email,
                subject_preview,
            )

            return EmailResult(
                success=False,
                error=str(exc),
            )

    async def send_bulk_email(
        self,
        recipients: list[str],
        subject: str,
        html_body: str,
        plain_text: str | None = None,
    ) -> list[EmailResult]:
        """
        Send the same email independently to multiple recipients.

        Each recipient gets an independent EmailResult.
        """

        if not isinstance(recipients, list) or not recipients:
            raise ValueError("At least one recipient is required.")

        results: list[EmailResult] = []

        for recipient in recipients:
            try:
                result = await self.send_email(
                    to_email=recipient,
                    subject=subject,
                    html_body=html_body,
                    plain_text=plain_text,
                )
            except ValueError as exc:
                result = EmailResult(
                    success=False,
                    error=str(exc),
                )

            results.append(result)

        logger.info(
            "Bulk email completed: total=%s successful=%s failed=%s",
            len(results),
            sum(result.success for result in results),
            sum(not result.success for result in results),
        )

        return results

