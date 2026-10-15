"""
dispatch_consumer.py

Kafka consumer service for dispatch lifecycle events.

Responsibilities:
- Consume dispatch events from 'fieldops.job.events' and 'fieldops.events'.
- Validate event schema, tenant context, correlation IDs, and privacy safety (no secrets).
- Enforce idempotency using Redis markers to prevent duplicate business reactions.
- Invoke authoritative domain services (DispatchAgent, event_publisher, etc.) without duplicating logic.
- Handle failures safely with bounded error propagation and retry metadata.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional, Union

from app.redis_client import get_redis_client
from app.services.dispatch_agent import DispatchAgent
from app.services.event_publisher import publish_dispatch_event
from app.services.kafka.consumer import KafkaConsumerManager
from app.services.ai.FieldOpsAI.schemas.agent_messages import (
    DispatchEventMessage,
    MessageEnvelope,
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


class DispatchConsumer:
    """
    Dispatch event consumer for Kafka event stream reactions.
    """

    DEFAULT_TOPIC = "fieldops.job.events"
    DEFAULT_GROUP = "fieldops-dispatch"
    SCHEMA_VERSION = 1

    ALLOWED_TOPICS = frozenset({
        "fieldops.job.events",
        "fieldops.events",
    })

    ALLOWED_EVENT_TYPES = frozenset({
        "job-assigned",
        "job_assigned",
        "job-completed",
        "job_completed",
        "job-cancelled",
        "job_cancelled",
        "job-created",
        "job_created",
        "job-status",
        "job_status",
        "job-status-transition",
        "status_transition",
        "status-transition",
        "dispatch",
        "re-dispatch",
        "redispatch",
        "re_dispatch",
        "technician_timeout",
        "technician-timeout",
        "timeout",
    })

    def __init__(
        self,
        topic: Optional[str] = None,
        group_id: Optional[str] = None,
        consumer_manager: Optional[KafkaConsumerManager] = None,
        redis_client: Optional[Any] = None,
        db_session_factory: Optional[Any] = None,
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

        self.db_session_factory = db_session_factory

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

    async def start(self) -> None:
        """Start the underlying Kafka consumer."""
        if self.consumer_manager:
            await self.consumer_manager.start()

    async def stop(self) -> None:
        """Stop the underlying Kafka consumer."""
        if self._consumer_manager:
            await self._consumer_manager.stop()

    async def __aenter__(self) -> "DispatchConsumer":
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
        message: Union[dict[str, Any], str, MessageEnvelope, DispatchEventMessage],
        attempt: int = 1,
    ) -> ConsumeReceipt:
        """
        Validate, deduplicate, and process a dispatch event.
        """
        # 1. Parse / unpack message payload and metadata
        try:
            if isinstance(message, str):
                message = json.loads(message)

            if isinstance(message, (MessageEnvelope, DispatchEventMessage)):
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
                        "consumer": "dispatch",
                        "event_id": "unknown",
                        "attempt": attempt,
                        "error": f"Unsupported message type: {type(message).__name__}",
                    }
                )

        except Exception as parse_err:
            logger.error("Failed to parse dispatch event: %s", parse_err)
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "dispatch",
                    "event_id": "unknown",
                    "attempt": attempt,
                    "error": f"Message parse error: {parse_err}",
                }
            )

        event_id = payload.get("event_id")
        job_id = payload.get("job_id")
        tenant_id = payload.get("tenant_id")
        raw_event_type = payload.get("event_type") or payload.get("event")
        schema_version = payload.get("schema_version")

        # 2. Topic check
        if topic and topic not in self.ALLOWED_TOPICS:
            logger.warning(
                "Dispatch event rejected: topic '%s' not in allowed topics %s",
                topic,
                sorted(self.ALLOWED_TOPICS),
            )
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "dispatch",
                    "event_id": event_id or "unknown",
                    "attempt": attempt,
                    "error": f"Topic '{topic}' is not authorized for dispatch consumer",
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
                "Dispatch event missing required fields: %s",
                missing_fields,
            )
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "dispatch",
                    "event_id": event_id or "unknown",
                    "attempt": attempt,
                    "error": f"Missing required fields: {', '.join(sorted(missing_fields))}",
                }
            )

        # 4. Event type validation
        if not raw_event_type:
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "dispatch",
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
                    "consumer": "dispatch",
                    "event_id": event_id,
                    "attempt": attempt,
                    "error": f"Invalid event_type: '{raw_event_type}'",
                }
            )

        # 5. Security & forbidden secrets check
        lowered_keys = {str(k).lower() for k in payload.keys()}
        found_forbidden = lowered_keys.intersection(_FORBIDDEN_KEYS)
        if found_forbidden:
            logger.warning(
                "Dispatch event rejected due to sensitive keys: %s",
                found_forbidden,
            )
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "dispatch",
                    "event_id": event_id,
                    "attempt": attempt,
                    "error": f"Payload contains forbidden sensitive keys: {', '.join(sorted(found_forbidden))}",
                }
            )

        # 6. Idempotency verification via Redis
        idempotency_key = f"dispatch:event_processed:{event_id}"
        if self.redis_client:
            try:
                if self.redis_client.get(idempotency_key):
                    logger.info(
                        "Dispatch event %s already processed; skipping duplicate.",
                        event_id,
                    )
                    return ConsumeReceipt(
                        {
                            "status": "PROCESSED",
                            "consumer": "dispatch",
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

        # 7. Invoke authoritative domain services
        try:
            if norm_event_type in ("re-dispatch", "redispatch", "technician-timeout"):
                DispatchAgent.trigger_redispatch(str(job_id))
            else:
                # Status / assignment / lifecycle events coordinate with event_publisher
                completed_at_dt = None
                raw_completed_at = payload.get("completed_at")
                if raw_completed_at:
                    if isinstance(raw_completed_at, str):
                        try:
                            completed_at_dt = datetime.fromisoformat(
                                raw_completed_at.replace("Z", "+00:00")
                            )
                        except Exception:
                            completed_at_dt = None
                    elif isinstance(raw_completed_at, datetime):
                        completed_at_dt = raw_completed_at

                publish_dispatch_event(
                    redis_client=self.redis_client,
                    event_type=raw_event_type,
                    job_id=str(job_id),
                    old_status=payload.get("old_status", "UNKNOWN"),
                    new_status=payload.get("new_status", "UNKNOWN"),
                    tenant_id=str(tenant_id),
                    technician_id=(
                        str(payload.get("technician_id"))
                        if payload.get("technician_id") is not None
                        else None
                    ),
                    technician_name=payload.get("technician_name"),
                    completed_at=completed_at_dt,
                    correlation_id=correlation_id,
                    event_id=event_id,
                )

        except Exception as domain_err:
            logger.error(
                "Domain service invocation failed for event %s: %s",
                event_id,
                domain_err,
            )
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "dispatch",
                    "event_id": event_id,
                    "attempt": attempt,
                    "error": str(domain_err),
                }
            )

        # 8. Mark idempotency in Redis on success
        if self.redis_client:
            try:
                self.redis_client.set(idempotency_key, "1", ex=86400)
            except Exception as redis_save_err:
                logger.warning(
                    "Redis error marking idempotency for event %s: %s",
                    event_id,
                    redis_save_err,
                )

        # 9. Return successful receipt
        logger.info(
            "Dispatch event %s processed successfully by dispatch consumer (attempt %d).",
            event_id,
            attempt,
        )
        return ConsumeReceipt(
            {
                "status": "PROCESSED",
                "consumer": "dispatch",
                "event_id": event_id,
                "attempt": attempt,
            }
        )


DispatchEventConsumer = DispatchConsumer
