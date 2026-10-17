"""
audit_consumer.py

Kafka consumer service for approved audit events, secondary storage, analytics, and monitoring.

Responsibilities:
- Consume audit events from 'fieldops.audit.events' and 'fieldops.events'.
- Validate event schema, tenant context, and preserve event immutability.
- Enforce strict idempotency via Redis markers to avoid duplicate analytics ingestion and preserve audit trail integrity.
- Coordinate with secondary storage / analytics workflows and Redis pub/sub ('audit_events')
  without weakening the authoritative audit trail.
- Support safe retry and recovery with bounded failure reporting.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional, Union

from app.redis_client import get_redis_client
from app.services.event_publisher import publish_audit_event
from app.services.kafka.consumer import KafkaConsumerManager
from app.services.ai.FieldOpsAI.schemas.agent_messages import (
    MessageEnvelope,
    AuditEventMessage,
    _FORBIDDEN_KEYS,
)

logger = logging.getLogger(__name__)


class ConsumeReceipt(dict):
    """
    Structured dictionary receipt returned after consuming/processing an audit event.
    Evaluates to True if status is 'PROCESSED'.
    """

    @property
    def is_success(self) -> bool:
        return self.get("status") == "PROCESSED"

    def __bool__(self) -> bool:
        return self.is_success


class AuditConsumer:
    """
    Audit event consumer for centralized analytics, secondary storage, and monitoring.
    """

    DEFAULT_TOPIC = "fieldops.audit.events"
    DEFAULT_GROUP = "fieldops-audit"
    SCHEMA_VERSION = 1

    ALLOWED_TOPICS = frozenset({
        "fieldops.audit.events",
        "fieldops.events",
    })

    ALLOWED_EVENT_TYPES = frozenset({
        "audit",
        "audit-event",
        "audit_event",
        "audit-logged",
        "audit_logged",
        "manual-override",
        "manual_override",
        "status-transition",
        "status_transition",
        "security-event",
        "security_event",
        "access-revoked",
        "access_revoked",
    })

    VALID_SEVERITIES = frozenset({
        "debug",
        "info",
        "warning",
        "error",
        "critical",
    })

    def __init__(
        self,
        topic: Optional[str] = None,
        group_id: Optional[str] = None,
        consumer_manager: Optional[KafkaConsumerManager] = None,
        redis_client: Optional[Any] = None,
        analytics_client: Optional[Any] = None,
        audit_service: Optional[Any] = None,
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

        self.analytics_client = analytics_client
        self.audit_service = audit_service
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

    async def __aenter__(self) -> "AuditConsumer":
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
        message: Union[dict[str, Any], str, MessageEnvelope, AuditEventMessage],
        attempt: int = 1,
    ) -> ConsumeReceipt:
        """
        Validate event schema and tenant context, preserve event immutability,
        enforce idempotency, and update downstream secondary storage/analytics.
        """
        # 1. Parse / unpack message payload and metadata
        try:
            if isinstance(message, str):
                message = json.loads(message)

            if isinstance(message, (MessageEnvelope, AuditEventMessage)):
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
                        "consumer": "audit",
                        "event_id": "unknown",
                        "attempt": attempt,
                        "error": f"Unsupported message type: {type(message).__name__}",
                    }
                )

        except Exception as parse_err:
            logger.error("Failed to parse audit event: %s", parse_err)
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "audit",
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
        user_id = payload.get("user_id") or payload.get("userId")
        action = payload.get("action")
        severity_raw = payload.get("severity")
        entity_type = payload.get("entity_type") or payload.get("entityType")
        entity_id = payload.get("entity_id") or payload.get("entityId")

        # 2. Topic check
        if topic and topic not in self.ALLOWED_TOPICS:
            logger.warning(
                "Audit event rejected: topic '%s' not in allowed topics %s",
                topic,
                sorted(self.ALLOWED_TOPICS),
            )
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "audit",
                    "event_id": event_id or "unknown",
                    "attempt": attempt,
                    "error": f"Topic '{topic}' is not authorized for audit consumer",
                }
            )

        # 3. Schema & contract validation (Requirement 1: Validate event schema & tenant context)
        missing_fields = []
        if not event_id or not str(event_id).strip():
            missing_fields.append("event_id")
        if not tenant_id or not str(tenant_id).strip():
            missing_fields.append("tenant_id")
        if schema_version is None:
            missing_fields.append("schema_version")

        if missing_fields:
            logger.warning(
                "Audit event missing required fields: %s",
                missing_fields,
            )
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "audit",
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
                    "consumer": "audit",
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
                    "consumer": "audit",
                    "event_id": event_id,
                    "attempt": attempt,
                    "error": f"Invalid event_type: '{raw_event_type}'",
                }
            )

        # 5. Severity validation (if provided)
        if severity_raw is not None:
            norm_severity = str(severity_raw).strip().lower()
            if norm_severity not in self.VALID_SEVERITIES:
                return ConsumeReceipt(
                    {
                        "status": "FAILED",
                        "consumer": "audit",
                        "event_id": event_id,
                        "attempt": attempt,
                        "error": f"Invalid audit severity: '{severity_raw}'",
                    }
                )

        # 6. Security & forbidden secrets check
        lowered_keys = {str(k).lower() for k in payload.keys()}
        found_forbidden = lowered_keys.intersection(_FORBIDDEN_KEYS)
        if found_forbidden:
            logger.warning(
                "Audit event rejected due to sensitive keys: %s",
                found_forbidden,
            )
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "audit",
                    "event_id": event_id,
                    "attempt": attempt,
                    "error": f"Payload contains forbidden sensitive keys: {', '.join(sorted(found_forbidden))}",
                }
            )

        # 7. Database tenant validation & immutability preservation check (Requirement 1)
        if self.db_session_factory:
            try:
                db = self.db_session_factory()
                try:
                    from app.models.enterprise_audit import EnterpriseAuditLog

                    # Check existing audit log immutability
                    existing_entry = (
                        db.query(EnterpriseAuditLog)
                        .filter(EnterpriseAuditLog.id == str(event_id))
                        .first()
                    )
                    if existing_entry:
                        if str(existing_entry.tenant_id) != str(tenant_id):
                            return ConsumeReceipt(
                                {
                                    "status": "FAILED",
                                    "consumer": "audit",
                                    "event_id": event_id,
                                    "attempt": attempt,
                                    "error": "Tenant mismatch for immutable audit record",
                                }
                            )
                        # If record exists and tenant matches, immutability is preserved; treat as duplicate
                        logger.info(
                            "Audit event %s already stored in immutable log; skipping duplicate.",
                            event_id,
                        )
                        return ConsumeReceipt(
                            {
                                "status": "PROCESSED",
                                "consumer": "audit",
                                "event_id": event_id,
                                "attempt": attempt,
                                "idempotent_duplicate": True,
                            }
                        )

                    # Tenant consistency check with job entity if job_id provided
                    if job_id and str(job_id).isdigit():
                        from app.models_legacy import Job
                        job = db.query(Job).filter(Job.id == int(job_id)).first()
                        if job and str(job.tenant_id) != str(tenant_id):
                            return ConsumeReceipt(
                                {
                                    "status": "FAILED",
                                    "consumer": "audit",
                                    "event_id": event_id,
                                    "attempt": attempt,
                                    "error": "Tenant mismatch between audit event and persisted job entity",
                                }
                            )

                    # Append-only immutable insertion into EnterpriseAuditLog
                    new_entry = EnterpriseAuditLog(
                        id=str(event_id),
                        tenant_id=str(tenant_id),
                        user_id=str(user_id) if user_id else None,
                        action=str(action or raw_event_type),
                        entity_type=str(entity_type) if entity_type else ("job" if job_id else "system"),
                        entity_id=str(entity_id or job_id) if (entity_id or job_id) else None,
                        details=payload,
                        severity=str(severity_raw).upper() if severity_raw else "INFO",
                        correlation_id=str(correlation_id) if correlation_id else None,
                    )
                    db.add(new_entry)
                    db.commit()

                finally:
                    db.close()
            except Exception as db_err:
                logger.warning(
                    "DB validation/storage check failed for audit event %s: %s",
                    event_id,
                    db_err,
                )

        # 8. Idempotency verification via Redis
        idempotency_key = f"audit:event_processed:{event_id}"
        if self.redis_client:
            try:
                if self.redis_client.get(idempotency_key):
                    logger.info(
                        "Audit event %s already processed; skipping duplicate.",
                        event_id,
                    )
                    return ConsumeReceipt(
                        {
                            "status": "PROCESSED",
                            "consumer": "audit",
                            "event_id": event_id,
                            "attempt": attempt,
                            "idempotent_duplicate": True,
                        }
                    )
            except Exception as redis_check_err:
                logger.warning(
                    "Redis error checking idempotency for audit event %s: %s",
                    event_id,
                    redis_check_err,
                )

        # 9. Invoke downstream secondary storage & analytics workflows
        try:
            tenant_id_str = str(tenant_id)
            job_id_str = str(job_id) if job_id is not None else None
            user_id_str = str(user_id) if user_id is not None else None

            # Invoke analytics client if provided
            if self.analytics_client:
                import inspect
                analytics_fn = (
                    getattr(self.analytics_client, "ingest_event", None)
                    or getattr(self.analytics_client, "record_metric", None)
                    or getattr(self.analytics_client, "track_audit", None)
                )
                if analytics_fn:
                    if inspect.iscoroutinefunction(analytics_fn):
                        await analytics_fn(
                            event_id=str(event_id),
                            tenant_id=tenant_id_str,
                            event_type=str(raw_event_type),
                            job_id=job_id_str,
                            user_id=user_id_str,
                            severity=str(severity_raw).upper() if severity_raw else "INFO",
                            payload=payload,
                        )
                    else:
                        analytics_fn(
                            event_id=str(event_id),
                            tenant_id=tenant_id_str,
                            event_type=str(raw_event_type),
                            job_id=job_id_str,
                            user_id=user_id_str,
                            severity=str(severity_raw).upper() if severity_raw else "INFO",
                            payload=payload,
                        )

            # Invoke external audit service if provided
            if self.audit_service:
                import inspect
                audit_fn = (
                    getattr(self.audit_service, "record_audit_event", None)
                    or getattr(self.audit_service, "store_audit_log", None)
                    or getattr(self.audit_service, "process_audit_event", None)
                )
                if audit_fn:
                    if inspect.iscoroutinefunction(audit_fn):
                        await audit_fn(
                            event_id=str(event_id),
                            tenant_id=tenant_id_str,
                            event_type=str(raw_event_type),
                            job_id=job_id_str,
                            user_id=user_id_str,
                            payload=payload,
                        )
                    else:
                        audit_fn(
                            event_id=str(event_id),
                            tenant_id=tenant_id_str,
                            event_type=str(raw_event_type),
                            job_id=job_id_str,
                            user_id=user_id_str,
                            payload=payload,
                        )

            # Publish canonical audit event to Redis channel for real-time WebSocket / monitoring coordination
            publish_audit_event(
                redis_client=self.redis_client,
                event_type=raw_event_type,
                tenant_id=tenant_id_str,
                job_id=job_id_str,
                user_id=user_id_str,
                correlation_id=correlation_id,
                event_id=str(event_id),
                payload=payload,
            )

        except Exception as domain_err:
            logger.error(
                "Secondary storage / analytics invocation failed for audit event %s: %s",
                event_id,
                domain_err,
            )
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "audit",
                    "event_id": event_id,
                    "attempt": attempt,
                    "error": f"Secondary storage / analytics failure: {domain_err}",
                }
            )

        # 10. Enforce idempotency after successful processing
        if self.redis_client:
            try:
                self.redis_client.set(idempotency_key, "1", ex=7 * 24 * 60 * 60)
            except Exception as redis_set_err:
                logger.warning(
                    "Redis error saving idempotency marker for audit event %s: %s",
                    event_id,
                    redis_set_err,
                )

        logger.info(
            "Successfully processed audit event %s for tenant %s (type: %s)",
            event_id,
            tenant_id,
            raw_event_type,
        )

        return ConsumeReceipt(
            {
                "status": "PROCESSED",
                "consumer": "audit",
                "event_id": event_id,
                "attempt": attempt,
            }
        )


# Aliases for flexible integration
AuditEventConsumer = AuditConsumer
EnterpriseAuditConsumer = AuditConsumer

