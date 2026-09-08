from dataclasses import dataclass
import os
import time
import logging
from datetime import datetime, timezone
import phonenumbers
from phonenumbers import NumberParseException
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client
import json


logger = logging.getLogger(__name__)



@dataclass
class SMSResult:
    success: bool
    sid: str | None = None
    to_number: str | None = None
    status: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class TwilioSMSService:
    def __init__(self):
        self.account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        self.auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        self.from_number = os.getenv("TWILIO_PHONE_NUMBER")
        self.test_mode = os.getenv("TWILIO_TEST_MODE", "false").lower() == "true"
        self.dry_run = os.getenv("TWILIO_DRY_RUN", "false").lower() == "true"

        # Redis is used to track the current SMS delivery state.
        try:
            from app.redis_client import get_redis_client

            self.redis = get_redis_client()
        except Exception:
            self.redis = None

        # Create the Twilio client only when a real API call may be made.
        self.client = None

        if not self.dry_run and not self.test_mode:
            self.client = Client(
                self.account_sid,
                self.auth_token,
    )

    def validate_phone_number(self, phone_number: str) -> str:
        try:
            parsed_number = phonenumbers.parse(phone_number, "IN")

            if not phonenumbers.is_valid_number(parsed_number):
                raise ValueError("Invalid phone number")

            return phonenumbers.format_number(
                parsed_number,
                phonenumbers.PhoneNumberFormat.E164,
            )

        except NumberParseException:
            raise ValueError("Invalid phone number")

    def send_sms(
        self,
        to_number: str,
        body: str,
        from_number: str | None = None,
    ) -> SMSResult:
        if not body or not body.strip():
            raise ValueError("SMS body cannot be empty")

        if len(body) > 160:
            raise ValueError("SMS body cannot exceed 160 characters")

        formatted_number = self.validate_phone_number(to_number)
        sender = from_number or self.from_number

        # Sender is required only when an actual Twilio SMS is being sent.
        if not self.dry_run and not self.test_mode:
            if not sender:
                raise ValueError("Twilio sender phone number is not configured")

            sender = self.validate_phone_number(sender)

        # Prevent excessive SMS requests using a short Redis-based rate limit.
        if self.redis:
            rate_limit_key = f"sms_rate_limit:{formatted_number}"

            current_count = self.redis.get(rate_limit_key)

            if current_count and int(current_count) >= 5:
                logger.warning(
                    "SMS rate limit exceeded | recipient=%s",
                    formatted_number,
                )

                return SMSResult(
                    success=False,
                    to_number=formatted_number,
                    status="rate_limited",
                    error_code="429",
                    error_message="SMS rate limit exceeded",
                )

            self.redis.incr(rate_limit_key)

            # Keep the rate-limit counter for one minute.
            if current_count is None:
                self.redis.expire(rate_limit_key, 60)

        try:
            if self.dry_run:
                logger.info(
                    "SMS dry-run | recipient=%s | body_preview=%s | timestamp=%s",
                    formatted_number,
                    body[:50],
                    datetime.now(timezone.utc).isoformat(),
                )

                return SMSResult(
                    success=True,
                    sid=None,
                    to_number=formatted_number,
                    status="dry-run",
                )
    
            if self.test_mode:
                logger.info(
                    "SMS test mode | recipient=%s | body_preview=%s | timestamp=%s",
                    formatted_number,
                    body[:50],
                    datetime.now(timezone.utc).isoformat(),
                )

                return SMSResult(
                    success=True,
                    sid=None,
                    to_number=formatted_number,
                    status="test",
                )

            message = self._send_with_retry(
                body=body,
                from_number=sender,
                to_number=formatted_number,
            )

            logger.info(
                "SMS sent | recipient=%s | body_preview=%s | status=%s | sid=%s | timestamp=%s",
                formatted_number,
                body[:50],
                message.status,
                message.sid,
                datetime.now(timezone.utc).isoformat(),
            )

            # Store the initial delivery status using the Twilio SID as the Redis key.
            if self.redis and message.sid:
                self.redis.set(
                    f"sms_delivery:{message.sid}",
                    json.dumps(
                        {
                            "sid": message.sid,
                            "to_number": formatted_number,
                            "status": message.status,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                    ),
                    ex=86400,
                )

            return SMSResult(
                success=True,
                sid=message.sid,
                to_number=formatted_number,
                status=message.status,
            )

        except (TwilioRestException, TimeoutError) as exc:
            status_code, error_message = self._map_twilio_error(exc)

            logger.error(
                "SMS failed | recipient=%s | body_preview=%s | status=failed | error_code=%s | timestamp=%s",
                formatted_number,
                body[:50],
                getattr(exc, "code", None),
                datetime.now(timezone.utc).isoformat(),
            )

            return SMSResult(
                success=False,
                to_number=formatted_number,
                status="failed",
                error_code=str(status_code),
                error_message=error_message,
            )

    def send_bulk_sms(
        self,
        recipients: list[str],
        body: str,
        from_number: str | None = None,
    ) -> list[SMSResult]:
        # Validate the shared SMS body once before processing recipients.
        if not body or not body.strip():
            raise ValueError("SMS body cannot be empty")

        if len(body) > 160:
            raise ValueError("SMS body cannot exceed 160 characters")

        if not recipients:
            raise ValueError("Recipients list cannot be empty")

        if len(recipients) > 50:
            raise ValueError("Cannot send SMS to more than 50 recipients")

        results = []

        # Each recipient is processed independently so one failure
        # does not stop the remaining SMS deliveries.
        for recipient in recipients:
            try:
                result = self.send_sms(
                    to_number=recipient,
                    body=body,
                    from_number=from_number,
                )
                results.append(result)

            except Exception as exc:
                results.append(
                    SMSResult(
                        success=False,
                        to_number=recipient,
                        status="failed",
                        error_message=str(exc),
                    )
                )

        return results

    def preview_sms(
        self,
        to_number: str,
        body: str,
    ) -> SMSResult:
        # Dry-run preview validates the SMS without sending it to Twilio.
        if not body or not body.strip():
            raise ValueError("SMS body cannot be empty")

        if len(body) > 160:
            raise ValueError("SMS body cannot exceed 160 characters")

        # Validate and normalize the recipient to E.164 format.
        formatted_number = self.validate_phone_number(to_number)

        logger.info(
            "SMS preview | recipient=%s | body_preview=%s | timestamp=%s",
            formatted_number,
            body[:50],
            datetime.now(timezone.utc).isoformat(),
        )

        return SMSResult(
            success=True,
            sid=None,
            to_number=formatted_number,
            status="preview",
        )


    def _map_twilio_error(
        self,
        error: TwilioRestException | TimeoutError,
    ) -> tuple[int, str]:
        if isinstance(error, TimeoutError):
            return 503, "Twilio request timed out"

        if error.status == 400:
            return 400, "Invalid phone number or SMS request"

        if error.status == 401:
            return 401, "Invalid Twilio credentials"

        if error.status == 402:
            return 402, "Insufficient Twilio account balance"

        if error.status == 429:
            return 429, "Twilio rate limit exceeded"

        if error.status and error.status >= 500:
            return 503, "Twilio service unavailable"

        return 500, str(error.msg)

    def _send_with_retry(
        self,
        body: str,
        from_number: str,
        to_number: str,
        max_retries: int = 3,
    ):
        for attempt in range(max_retries):
            try:
                return self.client.messages.create(
                    body=body,
                    from_=from_number,
                    to=to_number,
                )

            except (TwilioRestException, TimeoutError) as exc:
                if isinstance(exc, TwilioRestException):
                    if exc.status not in (429, 500, 502, 503, 504):
                        raise

                if attempt == max_retries - 1:
                    raise

                time.sleep(2 ** attempt)