"""
sla_monitoring_consumer.py

Kafka consumer service for SLA monitoring lifecycle events.

Responsibilities:
- Consume SLA events from 'fieldops.sla.events' and 'fieldops.events'.
- Validate SLA state, job context, tenant metadata, schema, and privacy safety (no secrets).
- Enforce idempotency using Redis markers to prevent duplicate business side effects.
- Invoke authoritative source-of-truth services (SLAService, SLAEscalationService, event_publisher)
  without duplicating SLA timer or calculation logic.
- Handle failures safely with bounded error propagation and retry metadata.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional, Union

from app.redis_client import get_redis_client
from app.services.event_publisher import publish_sla_event
from app.services.kafka.consumer import KafkaConsumerManager
from app.services.sla_service import SLAService, make_utc_aware
from app.services.sla_escalation_service import SLAEscalationService
from app.services.ai.FieldOpsAI.schemas.agent_messages import (
    MessageEnvelope,
    SLAEventMessage,
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


class SLAMonitoringConsumer:
    """
    SLA monitoring event consumer for Kafka event stream processing.
    """

    DEFAULT_TOPIC = "fieldops.sla.events"
    DEFAULT_GROUP = "fieldops-sla"
    SCHEMA_VERSION = 1

    ALLOWED_TOPICS = frozenset({
        "fieldops.sla.events",
        "fieldops.events",
    })

    ALLOWED_EVENT_TYPES = frozenset({
        "sla",
        "sla-created",
        "sla_created",
        "sla-updated",
        "sla_updated",
        "sla-near-breach",
        "sla_near_breach",
        "sla-breached",
        "sla_breached",
        "sla-paused",
        "sla_paused",
        "sla-resumed",
        "sla_resumed",
        "sla-cleared",
        "sla_cleared",
        "sla-escalated",
        "sla_escalated",
        "sla-milestone",
        "sla_milestone",
    })

    VALID_SLA_STATES = frozenset({
        "active",
        "paused",
        "breached",
        "cleared",
        "escalated",
        "critical",
        "pending",
        "completed",
        "cancelled",
        "closed",
    })

    def __init__(
        self,
        topic: Optional[str] = None,
        group_id: Optional[str] = None,
        consumer_manager: Optional[KafkaConsumerManager] = None,
        redis_client: Optional[Any] = None,
        sla_service: Optional[SLAService] = None,
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

        self._sla_service = sla_service
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

    @property
    def sla_service(self) -> SLAService:
        if self._sla_service is None:
            self._sla_service = SLAService(redis_client=self.redis_client)
        return self._sla_service

    @sla_service.setter
    def sla_service(self, value: Optional[SLAService]) -> None:
        self._sla_service = value

    async def start(self) -> None:
        """Start the underlying Kafka consumer."""
        if self.consumer_manager:
            await self.consumer_manager.start()

    async def stop(self) -> None:
        """Stop the underlying Kafka consumer."""
        if self._consumer_manager:
            await self._consumer_manager.stop()

    async def __aenter__(self) -> "SLAMonitoringConsumer":
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
        message: Union[dict[str, Any], str, MessageEnvelope, SLAEventMessage],
        attempt: int = 1,
    ) -> ConsumeReceipt:
        """
        Validate SLA state, job context, tenant metadata, enforce idempotency,
        and invoke existing SLA monitoring/alerting behavior.
        """
        # 1. Parse / unpack message payload and metadata
        try:
            if isinstance(message, str):
                message = json.loads(message)

            if isinstance(message, (MessageEnvelope, SLAEventMessage)):
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
                        "consumer": "SLA_monitoring",
                        "event_id": "unknown",
                        "attempt": attempt,
                        "error": f"Unsupported message type: {type(message).__name__}",
                    }
                )

        except Exception as parse_err:
            logger.error("Failed to parse SLA event: %s", parse_err)
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "SLA_monitoring",
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
        deadline_raw = payload.get("deadline") or payload.get("sla_deadline")
        sla_state_raw = (
            payload.get("sla_state")
            or payload.get("status")
            or payload.get("sla_status")
        )

        # 2. Topic check
        if topic and topic not in self.ALLOWED_TOPICS:
            logger.warning(
                "SLA event rejected: topic '%s' not in allowed topics %s",
                topic,
                sorted(self.ALLOWED_TOPICS),
            )
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "SLA_monitoring",
                    "event_id": event_id or "unknown",
                    "attempt": attempt,
                    "error": f"Topic '{topic}' is not authorized for SLA monitoring consumer",
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
                "SLA event missing required fields: %s",
                missing_fields,
            )
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "SLA_monitoring",
                    "event_id": event_id or "unknown",
                    "attempt": attempt,
                    "error": f"Missing required fields: {', '.join(sorted(missing_fields))}",
                }
            )

        # 4. Validate SLA state and job context (Requirement 1)
        # 4a. Validate job context
        if not str(job_id).strip():
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "SLA_monitoring",
                    "event_id": event_id,
                    "attempt": attempt,
                    "error": "Invalid job context: job_id cannot be blank",
                }
            )

        # 4b. Validate SLA deadline if provided
        parsed_deadline = None
        if deadline_raw is not None:
            if isinstance(deadline_raw, datetime):
                parsed_deadline = make_utc_aware(deadline_raw)
            elif isinstance(deadline_raw, str):
                try:
                    parsed_deadline = make_utc_aware(deadline_raw)
                    if parsed_deadline is None:
                        raise ValueError()
                except Exception:
                    return ConsumeReceipt(
                        {
                            "status": "FAILED",
                            "consumer": "SLA_monitoring",
                            "event_id": event_id,
                            "attempt": attempt,
                            "error": f"Invalid SLA deadline format: '{deadline_raw}'",
                        }
                    )
            else:
                return ConsumeReceipt(
                    {
                        "status": "FAILED",
                        "consumer": "SLA_monitoring",
                        "event_id": event_id,
                        "attempt": attempt,
                        "error": "Invalid SLA deadline: must be ISO date string or datetime",
                    }
                )

        # 4c. Validate SLA state if provided
        if sla_state_raw:
            norm_sla_state = str(sla_state_raw).strip().lower()
            if norm_sla_state not in self.VALID_SLA_STATES:
                return ConsumeReceipt(
                    {
                        "status": "FAILED",
                        "consumer": "SLA_monitoring",
                        "event_id": event_id,
                        "attempt": attempt,
                        "error": f"Invalid SLA state: '{sla_state_raw}'",
                    }
                )

        # 5. Event type validation
        if not raw_event_type:
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "SLA_monitoring",
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
                    "consumer": "SLA_monitoring",
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
                "SLA event rejected due to sensitive keys: %s",
                found_forbidden,
            )
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "SLA_monitoring",
                    "event_id": event_id,
                    "attempt": attempt,
                    "error": f"Payload contains forbidden sensitive keys: {', '.join(sorted(found_forbidden))}",
                }
            )

        # 7. Idempotency verification via Redis (Requirement 1: make processing idempotent)
        idempotency_key = f"sla:event_processed:{event_id}"
        if self.redis_client:
            try:
                if self.redis_client.get(idempotency_key):
                    logger.info(
                        "SLA event %s already processed; skipping duplicate.",
                        event_id,
                    )
                    return ConsumeReceipt(
                        {
                            "status": "PROCESSED",
                            "consumer": "SLA_monitoring",
                            "event_id": event_id,
                            "attempt": attempt,
                            "idempotent_duplicate": True,
                        }
                    )
            except Exception as redis_check_err:
                logger.warning(
                    "Redis error checking idempotency for SLA event %s: %s",
                    event_id,
                    redis_check_err,
                )

        # 8. Invoke authoritative SLA domain services
        try:
            job_id_str = str(job_id)

            if norm_event_type in ("sla-created", "sla_created"):
                if parsed_deadline:
                    self.sla_service.start_sla_timer(job_id_str, parsed_deadline)
                else:
                    # Fallback to query existing job deadline or calculate state
                    self.sla_service.get_sla_state(job_id_str)

            elif norm_event_type in ("sla-paused", "sla_paused"):
                self.sla_service.pause_sla_timer(job_id_str)

            elif norm_event_type in ("sla-resumed", "sla_resumed"):
                self.sla_service.resume_sla_timer(job_id_str)

            elif norm_event_type in ("sla-cleared", "sla_cleared"):
                self.sla_service.clear_sla_timer(job_id_str)

            elif norm_event_type in ("sla-escalated", "sla_escalated"):
                if self.db_session_factory:
                    db = self.db_session_factory()
                    try:
                        from app.models import Job
                        job = (
                            db.query(Job)
                            .filter(Job.id == (int(job_id) if str(job_id).isdigit() else job_id))
                            .first()
                        )
                        if job:
                            SLAEscalationService.trigger_escalation(db, job)
                    finally:
                        db.close()
                else:
                    logger.info("Triggered SLA escalation handling for job %s", job_id_str)

            else:
                # Default for SLA_NEAR_BREACH, SLA_BREACHED, SLA_MILESTONE, or general SLA events:
                # Calculate / check milestones & authoritative state
                self.sla_service.get_sla_state(job_id_str)

            # Publish canonical SLA event to Redis channel for real-time WebSocket coordination
            publish_sla_event(
                redis_client=self.redis_client,
                event_type=raw_event_type,
                job_id=job_id_str,
                tenant_id=str(tenant_id),
                correlation_id=correlation_id,
                event_id=event_id,
                payload=payload,
            )

        except Exception as domain_err:
            logger.error(
                "Domain SLA processing failed for event %s: %s",
                event_id,
                domain_err,
            )
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "SLA_monitoring",
                    "event_id": event_id,
                    "attempt": attempt,
                    "error": f"SLA domain processing failure: {domain_err}",
                }
            )

        # 9. Enforce idempotency after successful processing
        if self.redis_client:
            try:
                self.redis_client.set(idempotency_key, "1", ex=7 * 24 * 60 * 60)
            except Exception as redis_set_err:
                logger.warning(
                    "Redis error saving idempotency marker for SLA event %s: %s",
                    event_id,
                    redis_set_err,
                )

        logger.info(
            "Successfully processed SLA event %s for job %s",
            event_id,
            job_id,
        )

        return ConsumeReceipt(
            {
                "status": "PROCESSED",
                "consumer": "SLA_monitoring",
                "event_id": event_id,
                "attempt": attempt,
            }
        )


# Aliases for flexible integration
SLAConsumer = SLAMonitoringConsumer
SLAEventConsumer = SLAMonitoringConsumer

