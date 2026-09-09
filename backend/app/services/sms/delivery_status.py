from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session
from app.logger import logger
from app.models_legacy import SMSDelivery


class SMSDeliveryStatusService:
    """Process Twilio SMS delivery status callbacks."""

    VALID_STATUSES = {
        "queued",
        "sending",
        "sent",
        "delivered",
        "undelivered",
        "failed",
    }

    def __init__(self, db: Session):
        self.db = db

    def normalize_status(self, status: str) -> str:
        normalized = (status or "").strip().lower()

        if normalized not in self.VALID_STATUSES:
            raise ValueError(
                f"Invalid SMS delivery status: {status}"
            )

        return normalized

    def get_delivery(
        self,
        message_sid: str,
    ) -> SMSDelivery | None:
        return (
            self.db.query(SMSDelivery)
            .filter(
                SMSDelivery.sms_sid == message_sid
            )
            .first()
        )

    def update_delivery_status(
        self,
        message_sid: str,
        message_status: str,
        payload: dict[str, Any],
    ) -> SMSDelivery | None:

        status = self.normalize_status(
            message_status
        )

        delivery = self.get_delivery(
            message_sid
        )

        if delivery is None:
            return None

        now = datetime.now(timezone.utc)

        history = delivery.status_history or []

        last_status = (
            history[-1].get("status")
            if history
            else None
        )

        if last_status != status:
            history.append(
                {
                    "status": status,
                    "timestamp": now.isoformat(),
                }
            )

        delivery.status_history = history
        delivery.status = status
        delivery.last_webhook_at = now
        delivery.webhook_payload = payload

        if status == "sent":
            if delivery.sent_at is None:
                delivery.sent_at = now

        elif status == "delivered":
            if delivery.delivered_at is None:
                delivery.delivered_at = now

            if delivery.sent_at is not None:
                latency_seconds = (
                    delivery.delivered_at
                    - delivery.sent_at
                ).total_seconds()

                delivery.delivery_latency_ms = int(
                    latency_seconds * 1000
                )

        error_code = payload.get("ErrorCode")

        error_message = payload.get(
            "ErrorMessage"
        )
        price = payload.get("Price")

        if price is not None:
            try:
                delivery.cost = abs(float(price))
            except (TypeError, ValueError):
                logger.warning(
                    "Invalid Twilio price received. sid=%s price=%s",
                    message_sid,
                    price,
                )
        if error_code:
            delivery.error_message = (
                f"Twilio ErrorCode: {error_code}"
            )

        elif error_message:
            delivery.error_message = (
                str(error_message)
            )

        if status in {"failed", "undelivered"}:
            logger.error(
                "SMS delivery failed. sid=%s status=%s error=%s",
                message_sid,
                status,
                delivery.error_message,
            )

        self.db.commit()
        self.db.refresh(delivery)

        return delivery


    def process_webhook(
        self,
        payload: dict[str, Any],
    ) -> SMSDelivery | None:

        message_sid = (
            payload.get("MessageSid")
            or payload.get("SmsSid")
        )

        message_status = (
            payload.get("MessageStatus")
            or payload.get("SmsStatus")
        )

        if not message_sid:
            raise ValueError(
                "Twilio webhook missing MessageSid"
            )

        if not message_status:
            raise ValueError(
                "Twilio webhook missing MessageStatus"
            )

        return self.update_delivery_status(
            message_sid=message_sid,
            message_status=message_status,
            payload=payload,
        )