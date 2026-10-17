"""
analytics_consumer.py

Kafka consumer service for operational and business analytics, telemetry, and metrics pipelines.

Responsibilities:
- Consume relevant business events from 'fieldops.analytics.events', 'fieldops.events', and domain topics.
- Validate event version (schema_version) and tenant context.
- Strictly preserve transactional source-of-truth records without changing transactional entities (Jobs, Invoices, Payments).
- Enforce strict idempotency via Redis markers to avoid duplicate metrics aggregation.
- Ingest into downstream analytics/metrics pipelines and publish canonical events to Redis ('analytics_events').
- Support safe retry and recovery with bounded failure reporting.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional, Union

from app.redis_client import get_redis_client
from app.services.event_publisher import publish_analytics_event
from app.services.kafka.consumer import KafkaConsumerManager
from app.services.ai.FieldOpsAI.schemas.agent_messages import (
    MessageEnvelope,
    AnalyticsEventMessage,
    _FORBIDDEN_KEYS,
)

logger = logging.getLogger(__name__)


class ConsumeReceipt(dict):
    """
    Structured dictionary receipt returned after consuming/processing an analytics event.
    Evaluates to True if status is 'PROCESSED'.
    """

    @property
    def is_success(self) -> bool:
        return self.get("status") == "PROCESSED"

    def __bool__(self) -> bool:
        return self.is_success


class AnalyticsConsumer:
    """
    Analytics and metrics event consumer for decoupled operational/business analytics.
    """

    DEFAULT_TOPIC = "fieldops.analytics.events"
    DEFAULT_GROUP = "fieldops-analytics"
    SCHEMA_VERSION = 1

    ALLOWED_TOPICS = frozenset({
        "fieldops.analytics.events",
        "fieldops.events",
        "fieldops.job.events",
        "fieldops.gps.events",
        "fieldops.notification.events",
        "fieldops.sla.events",
        "fieldops.billing.events",
        "fieldops.payment.events",
        "fieldops.audit.events",
    })

    ALLOWED_EVENT_TYPES = frozenset({
        "analytics",
        "metrics",
        "kpi-update",
        "kpi_update",
        "business-metric",
        "business_metric",
        "job-metrics",
        "job_metrics",
        "sla-metrics",
        "sla_metrics",
        "operational-telemetry",
        "operational_telemetry",
        "performance-metric",
        "performance_metric",
        "job-created",
        "job_created",
        "job-completed",
        "job_completed",
        "job-assigned",
        "job_assigned",
        "status-transition",
        "status_transition",
        "payment-completed",
        "payment_completed",
        "invoice-generated",
        "invoice_generated",
        "audit-logged",
        "audit_logged",
    })

    def __init__(
        self,
        topic: Optional[str] = None,
        group_id: Optional[str] = None,
        consumer_manager: Optional[KafkaConsumerManager] = None,
        redis_client: Optional[Any] = None,
        analytics_pipeline: Optional[Any] = None,
        metrics_service: Optional[Any] = None,
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

        self.analytics_pipeline = analytics_pipeline
        self.metrics_service = metrics_service
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

    async def __aenter__(self) -> "AnalyticsConsumer":
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
        message: Union[dict[str, Any], str, MessageEnvelope, AnalyticsEventMessage],
        attempt: int = 1,
    ) -> ConsumeReceipt:
        """
        Validate event version and tenant context, preserve transactional source-of-truth
        without modification, enforce idempotency, and route to analytics pipelines.
        """
        # 1. Parse / unpack message payload and metadata
        try:
            if isinstance(message, str):
                message = json.loads(message)

            if isinstance(message, (MessageEnvelope, AnalyticsEventMessage)):
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
                        "consumer": "analytics",
                        "event_id": "unknown",
                        "attempt": attempt,
                        "error": f"Unsupported message type: {type(message).__name__}",
                    }
                )

        except Exception as parse_err:
            logger.error("Failed to parse analytics event: %s", parse_err)
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "analytics",
                    "event_id": "unknown",
                    "attempt": attempt,
                    "error": f"Message parse error: {parse_err}",
                }
            )

        event_id = payload.get("event_id")
        tenant_id = payload.get("tenant_id")
        raw_event_type = payload.get("event_type") or payload.get("event")
        schema_version = payload.get("schema_version")
        job_id = payload.get("job_id") or payload.get("jobId")

        # 2. Topic check
        if topic and topic not in self.ALLOWED_TOPICS:
            logger.warning(
                "Analytics event rejected: topic '%s' not in allowed topics %s",
                topic,
                sorted(self.ALLOWED_TOPICS),
            )
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "analytics",
                    "event_id": event_id or "unknown",
                    "attempt": attempt,
                    "error": f"Topic '{topic}' is not authorized for analytics consumer",
                }
            )

        # 3. Schema & contract validation (Requirement 1: Validate event version)
        missing_fields = []
        if not event_id or not str(event_id).strip():
            missing_fields.append("event_id")
        if not tenant_id or not str(tenant_id).strip():
            missing_fields.append("tenant_id")
        if schema_version is None:
            missing_fields.append("schema_version")

        if missing_fields:
            logger.warning(
                "Analytics event missing required fields: %s",
                missing_fields,
            )
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "analytics",
                    "event_id": event_id or "unknown",
                    "attempt": attempt,
                    "error": f"Missing required fields: {', '.join(sorted(missing_fields))}",
                }
            )

        # Validate event version (schema_version must be positive integer)
        if (
            not isinstance(schema_version, int)
            or isinstance(schema_version, bool)
            or schema_version < 1
        ):
            logger.warning(
                "Analytics event rejected due to invalid schema_version: %s",
                schema_version,
            )
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "analytics",
                    "event_id": event_id,
                    "attempt": attempt,
                    "error": f"Invalid or unsupported event version: {schema_version}. Must be a positive integer.",
                }
            )

        # 4. Event type validation
        if not raw_event_type:
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "analytics",
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
                    "consumer": "analytics",
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
                "Analytics event rejected due to sensitive keys: %s",
                found_forbidden,
            )
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "analytics",
                    "event_id": event_id,
                    "attempt": attempt,
                    "error": f"Payload contains forbidden sensitive keys: {', '.join(sorted(found_forbidden))}",
                }
            )

        # 6. Database context check (Requirement 1: Avoid changing transactional source-of-truth records)
        if self.db_session_factory:
            try:
                db = self.db_session_factory()
                try:
                    if job_id and str(job_id).isdigit():
                        from app.models_legacy import Job
                        job = db.query(Job).filter(Job.id == int(job_id)).first()
                        if job and str(job.tenant_id) != str(tenant_id):
                            return ConsumeReceipt(
                                {
                                    "status": "FAILED",
                                    "consumer": "analytics",
                                    "event_id": event_id,
                                    "attempt": attempt,
                                    "error": "Tenant mismatch between analytics event and persisted entity",
                                }
                            )

                    # Note: The analytics consumer strictly avoids changing transactional source-of-truth records.
                    # It NEVER updates or commits changes to Job, Invoice, or Payment tables.
                finally:
                    db.close()
            except Exception as db_err:
                logger.warning(
                    "DB check failed for analytics event %s: %s",
                    event_id,
                    db_err,
                )

        # 7. Idempotency verification via Redis
        idempotency_key = f"analytics:event_processed:{event_id}"
        if self.redis_client:
            try:
                if self.redis_client.get(idempotency_key):
                    logger.info(
                        "Analytics event %s already processed; skipping duplicate.",
                        event_id,
                    )
                    return ConsumeReceipt(
                        {
                            "status": "PROCESSED",
                            "consumer": "analytics",
                            "event_id": event_id,
                            "attempt": attempt,
                            "idempotent_duplicate": True,
                        }
                    )
            except Exception as redis_check_err:
                logger.warning(
                    "Redis error checking idempotency for analytics event %s: %s",
                    event_id,
                    redis_check_err,
                )

        # 8. Invoke downstream analytics pipeline / metrics service
        try:
            tenant_id_str = str(tenant_id)
            job_id_str = str(job_id) if job_id is not None else None

            # Route to analytics pipeline if configured
            if self.analytics_pipeline:
                import inspect
                pipe_fn = (
                    getattr(self.analytics_pipeline, "ingest_event", None)
                    or getattr(self.analytics_pipeline, "process_event", None)
                    or getattr(self.analytics_pipeline, "record_metric", None)
                )
                if pipe_fn:
                    if inspect.iscoroutinefunction(pipe_fn):
                        await pipe_fn(
                            event_id=str(event_id),
                            tenant_id=tenant_id_str,
                            event_type=str(raw_event_type),
                            schema_version=schema_version,
                            job_id=job_id_str,
                            payload=payload,
                        )
                    else:
                        pipe_fn(
                            event_id=str(event_id),
                            tenant_id=tenant_id_str,
                            event_type=str(raw_event_type),
                            schema_version=schema_version,
                            job_id=job_id_str,
                            payload=payload,
                        )

            # Route to metrics service if configured
            if self.metrics_service:
                import inspect
                metrics_fn = (
                    getattr(self.metrics_service, "track_event", None)
                    or getattr(self.metrics_service, "record_metric", None)
                    or getattr(self.metrics_service, "increment_counter", None)
                )
                if metrics_fn:
                    if inspect.iscoroutinefunction(metrics_fn):
                        await metrics_fn(
                            event_id=str(event_id),
                            tenant_id=tenant_id_str,
                            event_type=str(raw_event_type),
                            payload=payload,
                        )
                    else:
                        metrics_fn(
                            event_id=str(event_id),
                            tenant_id=tenant_id_str,
                            event_type=str(raw_event_type),
                            payload=payload,
                        )

            # Publish canonical analytics event to Redis channel for real-time subscribers
            publish_analytics_event(
                redis_client=self.redis_client,
                event_type=raw_event_type,
                tenant_id=tenant_id_str,
                job_id=job_id_str,
                correlation_id=correlation_id,
                event_id=str(event_id),
                payload=payload,
            )

        except Exception as domain_err:
            logger.error(
                "Analytics pipeline invocation failed for event %s: %s",
                event_id,
                domain_err,
            )
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "analytics",
                    "event_id": event_id,
                    "attempt": attempt,
                    "error": f"Analytics pipeline failure: {domain_err}",
                }
            )

        # 9. Enforce idempotency after successful processing
        if self.redis_client:
            try:
                self.redis_client.set(idempotency_key, "1", ex=7 * 24 * 60 * 60)
            except Exception as redis_set_err:
                logger.warning(
                    "Redis error saving idempotency marker for analytics event %s: %s",
                    event_id,
                    redis_set_err,
                )

        logger.info(
            "Successfully processed analytics event %s for tenant %s (type: %s)",
            event_id,
            tenant_id,
            raw_event_type,
        )

        return ConsumeReceipt(
            {
                "status": "PROCESSED",
                "consumer": "analytics",
                "event_id": event_id,
                "attempt": attempt,
            }
        )


# Aliases for flexible integration
MetricsConsumer = AnalyticsConsumer
AnalyticsEventConsumer = AnalyticsConsumer

