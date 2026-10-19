from html import escape


class EmailService:
    """Compatibility wrapper for password reset and other simple emails."""

    def __init__(self):
        from .smtp_email import SMTPEmailService
        self._service = SMTPEmailService()

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

        result = await self._service.send_email(
            to_email=to_email,
            subject=subject,
            html_body=html or "<pre>" + escape(text) + "</pre>",
            plain_text=text,
        )
        return result.success
