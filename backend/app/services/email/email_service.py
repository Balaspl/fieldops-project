import logging
import os
import smtplib
from email.message import EmailMessage


logger = logging.getLogger(__name__)


class EmailService:
    """Reusable email sender using Gmail SMTP."""

    def __init__(self):
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_username = os.getenv("SMTP_USERNAME")
        self.smtp_password = os.getenv("SMTP_PASSWORD")

    async def send_email(
        self,
        to_email: str,
        subject: str,
        text: str,
        html: str | None = None,
    ) -> bool:
        """
        Send an email using the configured SMTP server.

        Returns:
            True if the email was sent successfully.
            False if SMTP configuration or delivery fails.
        """

        if not self.smtp_username or not self.smtp_password:
            logger.error("SMTP credentials are not configured.")
            return False

        message = EmailMessage()

        message["Subject"] = subject
        message["From"] = self.smtp_username
        message["To"] = to_email

        message.set_content(text)

        if html:
            message.add_alternative(html, subtype="html")

        try:
            with smtplib.SMTP(
                self.smtp_host,
                self.smtp_port,
            ) as server:
                server.starttls()
                server.login(
                    self.smtp_username,
                    self.smtp_password,
                )
                server.send_message(message)

            logger.info("Email sent successfully.")
            return True

        except Exception:
            logger.exception("Failed to send email through SMTP.")
            return False