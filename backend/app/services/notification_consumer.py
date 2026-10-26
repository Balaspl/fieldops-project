"""
notification_consumer.py

Kafka consumer service for notification events.

Responsibilities:
- Consume notification events from 'fieldops.notification.events' and 'fieldops.events'.
- Validate event schema, channel, payload, tenant context, and privacy safety (no secrets).
- Enforce idempotency using Redis markers to prevent duplicate delivery.
- Invoke authoritative source-of-truth delivery services (NotificationRouter, SendGridService,
  TwilioSMSService, event_publisher, etc.) without duplicating business rules.
- Handle failures safely with bounded error propagation and retry metadata.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional, Union

from app.redis_client import get_redis_client
from app.services.event_publisher import publish_notification_event
from app.services.kafka.consumer import KafkaConsumerManager
from app.services.notification_services import (
    JobStatusEvent,
    NotificationRouter,
)
from app.services.ai.FieldOpsAI.schemas.agent_messages import (
    MessageEnvelope,
    NotificationEventMessage,
    _FORBIDDEN_KEYS,
)

logger = logging.getLogger(__name__)


class ConsumeReceipt(dict):
    """
    Structured dictionary receipt returned after consuming/processing an event.
    Evaluates to True if status is 'PROCESSED'.
    """

    @property
    def is_success(self) -> bool:
        return self.get("status") == "PROCESSED"

    def __bool__(self) -> bool:
        return self.is_success


class NotificationConsumer:
    """
    Notification event consumer for Kafka event stream processing.
    """

    DEFAULT_TOPIC = "fieldops.notification.events"
    DEFAULT_GROUP = "fieldops-notifications"
    SCHEMA_VERSION = 1

    ALLOWED_TOPICS = frozenset({
        "fieldops.notification.events",
        "fieldops.events",
    })

    ALLOWED_EVENT_TYPES = frozenset({
        "notification",
        "notification-queued",
        "notification_queued",
        "notification-sent",
        "notification_sent",
        "notification-failed",
        "notification_failed",
        "notification-retried",
        "notification_retried",
        "notification-request",
        "notification_request",
        "notification-delivered",
        "notification_delivered",
        "send-notification",
        "send_notification",
        "job-status-changed",
        "job_status_changed",
    })

    ALLOWED_CHANNELS = frozenset({
        "email",
        "sms",
        "push",
        "in_app",
        "inapp",
        "websocket",
        "ws",
        "all",
    })

    def __init__(
        self,
        topic: Optional[str] = None,
        group_id: Optional[str] = None,
        consumer_manager: Optional[KafkaConsumerManager] = None,
        redis_client: Optional[Any] = None,
        router: Optional[NotificationRouter] = None,
        bootstrap_servers: Optional[str] = None,
    ):
        self.topic = topic or self.DEFAULT_TOPIC
        self.group_id = group_id or self.DEFAULT_GROUP
        self.bootstrap_servers = bootstrap_servers

        self._consumer_manager = consumer_manager

        if redis_client is not None:
            self.redis_client = redis_client
        else:
            try:
                self.redis_client = get_redis_client()
            except Exception:
                self.redis_client = None

        self._router = router

    @property
    def consumer_manager(self) -> Optional[KafkaConsumerManager]:
        if self._consumer_manager is None:
            self._consumer_manager = KafkaConsumerManager(
                topic=self.topic,
                group_id=self.group_id,
                bootstrap_servers=self.bootstrap_servers,
            )
        return self._consumer_manager

    @consumer_manager.setter
    def consumer_manager(self, value: Optional[KafkaConsumerManager]) -> None:
        self._consumer_manager = value

    @property
    def router(self) -> NotificationRouter:
        if self._router is None:
            self._router = NotificationRouter(redis_client=self.redis_client)
        return self._router

    @router.setter
    def router(self, value: Optional[NotificationRouter]) -> None:
        self._router = value

    async def start(self) -> None:
        """Start the underlying Kafka consumer."""
        if self.consumer_manager:
            await self.consumer_manager.start()

    async def stop(self) -> None:
        """Stop the underlying Kafka consumer."""
        if self._consumer_manager:
            await self._consumer_manager.stop()

    async def __aenter__(self) -> "NotificationConsumer":
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: Any,
        exc_value: Any,
        traceback: Any,
    ) -> None:
        await self.stop()

    async def handle_message(
        self,
        message: dict[str, Any],
        attempt: int = 1,
    ) -> ConsumeReceipt:
        """Callback suitable for KafkaConsumerManager.consume(handler)."""
        return await self.process_event(message, attempt=attempt)

    async def process_event(
        self,
        message: Union[dict[str, Any], str, MessageEnvelope, NotificationEventMessage],
        attempt: int = 1,
    ) -> ConsumeReceipt:
        """
        Validate channel, payload, tenant context, enforce idempotency,
        and invoke existing notification delivery services.
        """
        # 1. Parse / unpack message payload and metadata
        try:
            if isinstance(message, str):
                message = json.loads(message)

            if isinstance(message, (MessageEnvelope, NotificationEventMessage)):
                payload = message.payload
                correlation_id = (
                    getattr(message, "correlation_id", None)
                    or payload.get("correlation_id")
                )
                topic = getattr(message, "topic", self.topic)
            elif isinstance(message, dict):
                if "payload" in message and isinstance(message["payload"], dict):
                    payload = message["payload"]
                    correlation_id = (
                        message.get("correlation_id")
                        or payload.get("correlation_id")
                    )
                    topic = message.get("topic", self.topic)
                else:
                    payload = message
                    correlation_id = payload.get("correlation_id")
                    topic = message.get("topic", self.topic)
            else:
                return ConsumeReceipt(
                    {
                        "status": "FAILED",
                        "consumer": "notification",
                        "event_id": "unknown",
                        "attempt": attempt,
                        "error": f"Unsupported message type: {type(message).__name__}",
                    }
                )

        except Exception as parse_err:
            logger.error("Failed to parse notification event: %s", parse_err)
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "notification",
                    "event_id": "unknown",
                    "attempt": attempt,
                    "error": f"Message parse error: {parse_err}",
                }
            )

        event_id = payload.get("event_id")
        job_id = payload.get("job_id") or payload.get("jobId")
        tenant_id = payload.get("tenant_id")
        raw_event_type = payload.get("event_type") or payload.get("event")
        schema_version = payload.get("schema_version")
        channel = payload.get("channel") or payload.get("delivery_channel")

        # 2. Topic check
        if topic and topic not in self.ALLOWED_TOPICS:
            logger.warning(
                "Notification event rejected: topic '%s' not in allowed topics %s",
                topic,
                sorted(self.ALLOWED_TOPICS),
            )
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "notification",
                    "event_id": event_id or "unknown",
                    "attempt": attempt,
                    "error": f"Topic '{topic}' is not authorized for notification consumer",
                }
            )

        # 3. Schema & contract validation
        missing_fields = []
        if not event_id:
            missing_fields.append("event_id")
        if not job_id:
            missing_fields.append("job_id")
        if not tenant_id:
            missing_fields.append("tenant_id")
        if schema_version is None:
            missing_fields.append("schema_version")

        if missing_fields:
            logger.warning(
                "Notification event missing required fields: %s",
                missing_fields,
            )
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "notification",
                    "event_id": event_id or "unknown",
                    "attempt": attempt,
                    "error": f"Missing required fields: {', '.join(sorted(missing_fields))}",
                }
            )

        # 4. Channel validation (Requirement 1: Validate channel/payload)
        if channel:
            normalized_channel = str(channel).strip().lower()
            if normalized_channel not in self.ALLOWED_CHANNELS:
                logger.warning(
                    "Invalid notification channel: '%s' for event %s",
                    channel,
                    event_id,
                )
                return ConsumeReceipt(
                    {
                        "status": "FAILED",
                        "consumer": "notification",
                        "event_id": event_id,
                        "attempt": attempt,
                        "error": f"Invalid notification channel: '{channel}'",
                    }
                )

        # 5. Event type validation
        if not raw_event_type:
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "notification",
                    "event_id": event_id,
                    "attempt": attempt,
                    "error": "Missing event_type",
                }
            )

        norm_event_type = str(raw_event_type).lower().replace("_", "-")
        normalized_allowed = {
            et.lower().replace("_", "-") for et in self.ALLOWED_EVENT_TYPES
        }

        if norm_event_type not in normalized_allowed:
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "notification",
                    "event_id": event_id,
                    "attempt": attempt,
                    "error": f"Invalid event_type: '{raw_event_type}'",
                }
            )

        # 6. Security & forbidden secrets check
        lowered_keys = {str(k).lower() for k in payload.keys()}
        found_forbidden = lowered_keys.intersection(_FORBIDDEN_KEYS)
        if found_forbidden:
            logger.warning(
                "Notification event rejected due to sensitive keys: %s",
                found_forbidden,
            )
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "notification",
                    "event_id": event_id,
                    "attempt": attempt,
                    "error": f"Payload contains forbidden sensitive keys: {', '.join(sorted(found_forbidden))}",
                }
            )

        # 7. Idempotency verification via Redis (avoid duplicate delivery)
        idempotency_key = f"notification:event_processed:{event_id}"
        if self.redis_client:
            try:
                if self.redis_client.get(idempotency_key):
                    logger.info(
                        "Notification event %s already processed; skipping duplicate.",
                        event_id,
                    )
                    return ConsumeReceipt(
                        {
                            "status": "PROCESSED",
                            "consumer": "notification",
                            "event_id": event_id,
                            "attempt": attempt,
                            "idempotent_duplicate": True,
                        }
                    )
            except Exception as redis_check_err:
                logger.warning(
                    "Redis error checking idempotency for event %s: %s",
                    event_id,
                    redis_check_err,
                )

        # 8. Invoke authoritative domain delivery services
        try:
            channel_str = str(channel).lower() if channel else None
            recipient_type = payload.get("recipient_type") or "customer"

            # Execute channel-specific delivery when explicit channel requested
            if channel_str == "email" and hasattr(self.router, "email") and self.router.email:
                to_email = (
                    payload.get("recipient")
                    or payload.get("to_email")
                    or payload.get("customer_email")
                )
                subject = payload.get("subject") or f"Update for job {job_id}"
                content = (
                    payload.get("body")
                    or payload.get("message")
                    or payload.get("html_content")
                    or f"Notification regarding job {job_id}"
                )
                if to_email:
                    import inspect
                    if inspect.iscoroutinefunction(self.router.email.send_email):
                        await self.router.email.send_email(to_email, subject, content)
                    else:
                        self.router.email.send_email(to_email, subject, content)

            elif channel_str == "sms" and hasattr(self.router, "sms") and self.router.sms:
                phone = (
                    payload.get("recipient")
                    or payload.get("to_phone")
                    or payload.get("customer_phone")
                )
                message_text = (
                    payload.get("body")
                    or payload.get("message")
                    or f"Notification regarding job {job_id}"
                )
                if phone:
                    import inspect
                    if inspect.iscoroutinefunction(self.router.sms):
                        await self.router.sms(phone, message_text)
                    else:
                        self.router.sms(phone, message_text)

            elif norm_event_type in ("job-status-changed", "job_status_changed") and hasattr(self.router, "route"):
                to_status = payload.get("new_status") or payload.get("to_status") or "ASSIGNED"
                job_event = JobStatusEvent(
                    job_id=str(job_id),
                    tenant_id=str(tenant_id),
                    from_status=payload.get("old_status") or payload.get("from_status") or "PENDING",
                    to_status=to_status,
                    actor_id=payload.get("actor_id") or "system",
                    actor_role=payload.get("actor_role") or "system",
                    reason=payload.get("reason"),
                    timestamp=datetime.now(timezone.utc),
                    job_title=payload.get("job_title") or f"Job {job_id}",
                    job_location=payload.get("job_location") or "Site",
                    technician_id=payload.get("technician_id"),
                    technician_name=payload.get("technician_name"),
                    customer_id=payload.get("customer_id"),
                    customer_name=payload.get("customer_name"),
                    customer_phone=payload.get("customer_phone"),
                    customer_email=payload.get("customer_email"),
                    eta=payload.get("eta"),
                    notification_channels=[channel_str] if channel_str else ["push", "in_app"],
                    event_type="job_status_changed",
                    correlation_id=correlation_id,
                )
                import inspect
                if inspect.iscoroutinefunction(self.router.route):
                    await self.router.route(job_event)
                else:
                    self.router.route(job_event)

            # Publish notification event to Redis channel for real-time WebSocket coordination
            publish_notification_event(
                redis_client=self.redis_client,
                event_type=raw_event_type,
                job_id=str(job_id),
                tenant_id=str(tenant_id),
                channel=channel_str,
                recipient_type=recipient_type,
                correlation_id=correlation_id,
                event_id=event_id,
                payload=payload,
            )

        except Exception as domain_err:
            logger.error(
                "Domain notification delivery failed for event %s: %s",
                event_id,
                domain_err,
            )
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "notification",
                    "event_id": event_id,
                    "attempt": attempt,
                    "error": f"Delivery failure: {domain_err}",
                }
            )

        # 9. Enforce idempotency after successful delivery (avoid duplicate delivery)
        if self.redis_client:
            try:
                self.redis_client.set(idempotency_key, "1", ex=7 * 24 * 60 * 60)
            except Exception as redis_set_err:
                logger.warning(
                    "Redis error saving idempotency marker for event %s: %s",
                    event_id,
                    redis_set_err,
                )

        logger.info(
            "Successfully processed notification event %s for job %s",
            event_id,
            job_id,
        )

        return ConsumeReceipt(
            {
                "status": "PROCESSED",
                "consumer": "notification",
                "event_id": event_id,
                "attempt": attempt,
            }
        )


# Aliases for flexible integration
NotificationEventConsumer = NotificationConsumer
NotificationDeliveryConsumer = NotificationConsumer

