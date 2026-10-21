"""
consumer_dead_letter_topics.py

Kafka dead-letter queue (DLQ) topic lifecycle management and poison message isolation
for FieldOps event streams.

Responsibilities:
- Define canonical DLQ naming, retention, metadata, and access rules.
- Isolate poison and unrecoverable messages without blocking healthy event processing.
- Route exhausted failures and fatal payloads to designated Kafka DLQ topics.
- Enrich dead-letter messages with diagnostic headers/metadata (original topic, partition,
  offset, failure reason, stack trace/error type, retry count, timestamp).
- Prevent duplicate business actions with strict Redis-backed pre-execution idempotency.
- Redact sensitive keys (password, token, secret, api_key) in DLQ payloads and logs.
- Provide safe re-processing and replay capabilities for isolated DLQ events.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Union

from app.redis_client import get_redis_client
from app.services.kafka.producer import KafkaProducer
from app.services.kafka.consumer import KafkaConsumerManager
from app.services.kafka.topics import (
    DEFAULT_KAFKA_TOPICS,
    DEFAULT_DLQ_TOPICS,
    DEFAULT_SHARED_DLQ_TOPIC,
    DEFAULT_DLQ_RETENTION_MS,
    get_dlq_topic,
    is_dlq_topic,
    get_dlq_retention_ms,
)
from app.services.ai.FieldOpsAI.schemas.agent_messages import (
    AgentAddress,
    MessageEnvelope,
    _FORBIDDEN_KEYS,
)
from app.services.consumer_error_handler import (
    ConsumeReceipt,
    ErrorClassification,
    classify_error,
    redact_sensitive_data,
)

logger = logging.getLogger(__name__)


class DLQReceipt(dict):
    """
    Structured dictionary receipt returned after DLQ processing or event recovery.
    Complies with the expected output contract:
    {
        "status": "RECOVERED",
        "event_id": "evt_01JEXAMPLE",
        "retries": 1,
        "idempotent": True,
        "dlq": False
    }
    """

    @property
    def is_success(self) -> bool:
        return self.get("status") in ("RECOVERED", "PROCESSED") and not self.get("dlq", False)

    @property
    def is_dlq(self) -> bool:
        return bool(self.get("dlq", False))

    def __bool__(self) -> bool:
        return self.is_success or self.is_dlq


class ConsumerDeadLetterTopics:
    """
    Manages Dead-Letter Queue (DLQ) topics, poison message isolation,
    and safe event replay for Kafka consumer pipelines.
    """

    CONSUMER_NAME = "Create_dead_letter_topics"
    DEFAULT_TOPIC = "fieldops.events"
    DEFAULT_GROUP = "fieldops-dead-letter-topics"
    DEFAULT_DLQ_KEY = "consumer:dlq"
    DEFAULT_IDEMPOTENCY_PREFIX = "consumer_dlq:event_processed:"
    DEFAULT_MAX_RETRIES = 3
    SCHEMA_VERSION = 1

    ALLOWED_TOPICS = frozenset(
        set(DEFAULT_KAFKA_TOPICS)
        | set(DEFAULT_DLQ_TOPICS)
        | {DEFAULT_SHARED_DLQ_TOPIC}
    )

    def __init__(
        self,
        topic: str = DEFAULT_TOPIC,
        group_id: str = DEFAULT_GROUP,
        kafka_producer: Optional[KafkaProducer] = None,
        kafka_consumer: Optional[KafkaConsumerManager] = None,
        redis_client: Optional[Any] = None,
        dlq_key: str = DEFAULT_DLQ_KEY,
        max_retries: int = DEFAULT_MAX_RETRIES,
        idempotency_prefix: str = DEFAULT_IDEMPOTENCY_PREFIX,
        idempotency_ttl_seconds: int = 7 * 24 * 60 * 60,
    ) -> None:
        self.topic = topic
        self.group_id = group_id
        self.producer = kafka_producer
        self.consumer = kafka_consumer
        self.redis_client = redis_client or get_redis_client()
        self.dlq_key = dlq_key
        self.max_retries = max_retries
        self.idempotency_prefix = idempotency_prefix
        self.idempotency_ttl = idempotency_ttl_seconds

        # In-memory diagnostic counters
        self._dlq_routed_count: int = 0
        self._recovered_count: int = 0
        self._replayed_count: int = 0
        self._last_dlq_event_id: Optional[str] = None
        self._last_dlq_timestamp: Optional[str] = None

    # =========================================================================
    # Metadata & Helpers
    # =========================================================================

    def resolve_dlq_topic(self, topic: Optional[str] = None) -> str:
        """Resolve the target DLQ topic for a given source topic."""
        source = topic or self.topic
        return get_dlq_topic(source)

    def _get_idempotency_key(self, event_id: str) -> str:
        return f"{self.idempotency_prefix}{event_id}"

    def is_event_processed(self, event_id: str) -> bool:
        """Check if an event was already successfully processed."""
        if not self.redis_client or not event_id:
            return False
        try:
            return bool(self.redis_client.get(self._get_idempotency_key(event_id)))
        except Exception as exc:
            logger.warning("Redis error checking DLQ idempotency for %s: %s", event_id, exc)
            return False

    def mark_event_processed(self, event_id: str) -> None:
        """Mark an event as successfully processed in Redis."""
        if not self.redis_client or not event_id:
            return
        try:
            self.redis_client.set(
                self._get_idempotency_key(event_id),
                "1",
                ex=self.idempotency_ttl,
            )
        except Exception as exc:
            logger.warning("Redis error saving DLQ idempotency for %s: %s", event_id, exc)

    # =========================================================================
    # Parsing & Normalization
    # =========================================================================

    def parse_message(
        self,
        raw_message: Any,
    ) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str], Dict[str, Any]]:
        """
        Safely extract topic, event_id, tenant_id, correlation_id, and payload
        from raw Kafka records, dictionaries, bytes, or strings.
        """
        topic = getattr(raw_message, "topic", None)
        if topic is None and isinstance(raw_message, dict):
            topic = raw_message.get("topic")
        if topic is None:
            topic = self.topic
        value = getattr(raw_message, "value", raw_message)

        if isinstance(value, bytes):
            try:
                decoded_str = value.decode("utf-8")
                value = json.loads(decoded_str)
            except Exception as exc:
                logger.error("Malformed bytes payload: %s", exc)
                return topic, None, None, None, {"raw_bytes": str(value), "parse_error": str(exc)}

        if isinstance(value, str):
            try:
                value = json.loads(value)
            except Exception as exc:
                logger.error("Malformed string payload: %s", exc)
                return topic, None, None, None, {"raw_str": value, "parse_error": str(exc)}

        if not isinstance(value, dict):
            return topic, None, None, None, {"raw_value": str(value)}

        # Extract envelope fields
        tenant_id = (
            value.get("tenant_id")
            or (value.get("sender") or {}).get("tenant_id")
            or (value.get("payload") or {}).get("tenant_id")
        )
        correlation_id = value.get("correlation_id") or (value.get("metadata") or {}).get("correlation_id")

        payload = value.get("payload")
        if not isinstance(payload, dict):
            payload = value

        event_id = (
            payload.get("event_id")
            or value.get("event_id")
            or (value.get("metadata") or {}).get("event_id")
            or value.get("message_id")
        )

        return topic, event_id, tenant_id, correlation_id, payload

    # =========================================================================
    # DLQ Routing (Poison Message Isolation)
    # =========================================================================

    async def route_to_dlq(
        self,
        *,
        payload: Any,
        error: Union[Exception, str],
        topic: Optional[str] = None,
        event_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        partition: Optional[int] = None,
        offset: Optional[int] = None,
        retries: int = 0,
        classification: Optional[ErrorClassification] = None,
    ) -> DLQReceipt:
        """
        Isolate a poison or unrecoverable event by routing it to the appropriate DLQ topic.
        Adds rich diagnostic context and redacts sensitive credentials.
        """
        source_topic = topic or self.topic
        target_dlq_topic = self.resolve_dlq_topic(source_topic)
        now_iso = datetime.now(timezone.utc).isoformat()
        resolved_event_id = event_id or f"evt_dlq_{int(datetime.now(timezone.utc).timestamp())}"
        resolved_tenant_id = tenant_id or "unknown-tenant"
        error_msg = str(error)
        error_type = type(error).__name__ if isinstance(error, Exception) else "DownstreamError"
        if classification:
            if isinstance(classification, tuple):
                resolved_classification_str = str(classification[0])
            elif isinstance(classification, ErrorClassification):
                resolved_classification_str = classification.value
            else:
                resolved_classification_str = str(classification)
        else:
            cls_res = classify_error(error if isinstance(error, Exception) else Exception(error_msg))
            resolved_classification_str = cls_res[0] if isinstance(cls_res, tuple) else str(cls_res)

        # Safe redacted payload
        safe_payload = redact_sensitive_data(payload if isinstance(payload, dict) else {"content": str(payload)})

        dlq_envelope = {
            "event_id": resolved_event_id,
            "tenant_id": resolved_tenant_id,
            "correlation_id": correlation_id,
            "source_topic": source_topic,
            "dlq_topic": target_dlq_topic,
            "failed_at": now_iso,
            "retries": retries,
            "max_retries": self.max_retries,
            "error_type": error_type,
            "error_message": error_msg,
            "error_classification": resolved_classification_str,
            "original_partition": partition,
            "original_offset": offset,
            "payload": safe_payload,
        }

        # 1. Dual persistence: Push to Redis DLQ queue
        if self.redis_client:
            try:
                self.redis_client.rpush(self.dlq_key, json.dumps(dlq_envelope))
                logger.info(
                    "Pushed dead-letter event %s to Redis DLQ '%s' (retries: %d, reason: %s)",
                    resolved_event_id,
                    self.dlq_key,
                    retries,
                    error_msg,
                )
            except Exception as redis_err:
                logger.error("Failed to push to Redis DLQ '%s': %s", self.dlq_key, redis_err)

        # 2. Publish to Kafka DLQ Topic if producer is available
        kafka_published = False
        if self.producer:
            try:
                envelope = MessageEnvelope(
                    sender=AgentAddress(
                        agent_type="monitoring",
                        agent_id="consumer-dlq-service",
                        tenant_id=resolved_tenant_id,
                    ),
                    message_type="EVENT",
                    topic=target_dlq_topic,
                    correlation_id=correlation_id,
                    payload=dlq_envelope,
                )
                kafka_published = await self.producer.publish(envelope, topic=target_dlq_topic)
                logger.info(
                    "Published dead-letter event %s to Kafka DLQ topic '%s' (success=%s)",
                    resolved_event_id,
                    target_dlq_topic,
                    kafka_published,
                )
            except Exception as k_err:
                logger.error("Failed to publish dead-letter event to Kafka topic '%s': %s", target_dlq_topic, k_err)

        self._dlq_routed_count += 1
        self._last_dlq_event_id = resolved_event_id
        self._last_dlq_timestamp = now_iso

        return DLQReceipt({
            "status": "DEAD_LETTER",
            "consumer": self.CONSUMER_NAME,
            "event_id": resolved_event_id,
            "retries": retries,
            "idempotent": True,
            "dlq": True,
            "dlq_topic": target_dlq_topic,
            "kafka_published": kafka_published,
        })

    # =========================================================================
    # Main Event Processing with Recovery Path and DLQ Fallback
    # =========================================================================

    async def process_event(
        self,
        message: Any,
        handler: Optional[Callable[[Dict[str, Any]], Any]] = None,
        max_retries: Optional[int] = None,
        allow_unauthorized_topics: bool = False,
    ) -> DLQReceipt:
        """
        Process a consumer event through the allowed recovery path.
        If recovery fails or a poison message is encountered, safely routes to DLQ.
        Complies with the expected output contract upon recovery or DLQ isolation.
        """
        retries_limit = max_retries if max_retries is not None else self.max_retries
        topic, event_id, tenant_id, correlation_id, payload = self.parse_message(message)
        partition = getattr(message, "partition", None)
        offset = getattr(message, "offset", None)

        # 1. Topic authorization check
        if not allow_unauthorized_topics and topic and topic not in self.ALLOWED_TOPICS:
            err_msg = f"Unauthorized or untrusted Kafka topic: {topic}"
            logger.warning("Rejecting message on untrusted topic %s", topic)
            return await self.route_to_dlq(
                payload=payload,
                error=err_msg,
                topic=topic,
                event_id=event_id,
                tenant_id=tenant_id,
                correlation_id=correlation_id,
                partition=partition,
                offset=offset,
                retries=0,
                classification=ErrorClassification.TERMINAL,
            )

        # 2. Poison pill / malformed message validation
        if not event_id or not tenant_id:
            err_msg = "Malformed event envelope: missing mandatory event_id or tenant_id"
            logger.error("Poison pill detected on topic %s: %s", topic, err_msg)
            return await self.route_to_dlq(
                payload=payload,
                error=err_msg,
                topic=topic,
                event_id=event_id,
                tenant_id=tenant_id,
                correlation_id=correlation_id,
                partition=partition,
                offset=offset,
                retries=0,
                classification=ErrorClassification.TERMINAL,
            )

        # 3. Pre-execution idempotency check
        if self.is_event_processed(event_id):
            logger.info("Event %s already processed. Returning idempotent success.", event_id)
            return DLQReceipt({
                "status": "RECOVERED",
                "consumer": self.CONSUMER_NAME,
                "event_id": event_id,
                "retries": 0,
                "idempotent": True,
                "dlq": False,
            })

        # Redact any sensitive credentials from payload
        safe_payload = redact_sensitive_data(payload)

        # 4. Allowed Recovery Loop
        retries_attempted = 0
        last_error = None

        while retries_attempted < retries_limit:
            retries_attempted += 1
            try:
                if handler:
                    result = handler(safe_payload)
                    if asyncio.iscoroutine(result):
                        await result

                # Success! Record idempotency marker
                self.mark_event_processed(event_id)
                self._recovered_count += 1

                logger.info(
                    "Consumer successfully processed/recovered event %s (attempt %d/%d, dlq=False)",
                    event_id,
                    retries_attempted,
                    retries_limit,
                )

                return DLQReceipt({
                    "status": "RECOVERED",
                    "consumer": self.CONSUMER_NAME,
                    "event_id": event_id,
                    "retries": retries_attempted,
                    "idempotent": True,
                    "dlq": False,
                })

            except Exception as exc:
                last_error = exc
                cls_res = classify_error(exc)
                if isinstance(cls_res, tuple):
                    classification_str, is_retryable = cls_res
                else:
                    classification_str = str(cls_res)
                    is_retryable = (classification_str == ErrorClassification.RETRYABLE.value)

                logger.warning(
                    "Downstream processing error on event %s (attempt %d/%d, classification: %s): %s",
                    event_id,
                    retries_attempted,
                    retries_limit,
                    classification_str,
                    exc,
                )

                # Non-retryable / fatal error -> isolate immediately to DLQ
                if not is_retryable or classification_str == ErrorClassification.TERMINAL.value:
                    logger.error("Terminal/poison error encountered. Routing event %s directly to DLQ.", event_id)
                    return await self.route_to_dlq(
                        payload=safe_payload,
                        error=exc,
                        topic=topic,
                        event_id=event_id,
                        tenant_id=tenant_id,
                        correlation_id=correlation_id,
                        partition=partition,
                        offset=offset,
                        retries=retries_attempted,
                        classification=classification_str,
                    )

                # Retryable failure: brief bounded backoff if retries remain
                if retries_attempted < retries_limit:
                    delay = min(0.05 * (2 ** (retries_attempted - 1)), 1.0)
                    await asyncio.sleep(delay)

        # 5. Recovery path exhausted -> Route to DLQ
        logger.error(
            "Event %s exhausted all allowed recovery attempts (%d/%d). Moving to DLQ.",
            event_id,
            retries_attempted,
            retries_limit,
        )
        return await self.route_to_dlq(
            payload=safe_payload,
            error=last_error or "Exhausted all recovery attempts",
            topic=topic,
            event_id=event_id,
            tenant_id=tenant_id,
            correlation_id=correlation_id,
            partition=partition,
            offset=offset,
            retries=retries_attempted,
            classification=ErrorClassification.RETRYABLE,
        )

    # =========================================================================
    # Replay & Reprocessing
    # =========================================================================

    async def replay_dlq_event(
        self,
        dlq_record: Union[Dict[str, Any], str],
        handler: Optional[Callable[[Dict[str, Any]], Any]] = None,
        force: bool = False,
    ) -> DLQReceipt:
        """
        Safely replay an isolated event from DLQ.
        Validates tenant context, prevents duplicate actions via idempotency,
        and routes back into healthy domain processing.
        """
        if isinstance(dlq_record, str):
            try:
                dlq_record = json.loads(dlq_record)
            except Exception as exc:
                raise ValueError(f"Invalid JSON string in DLQ replay: {exc}")

        if not isinstance(dlq_record, dict):
            raise ValueError("DLQ record must be a dictionary")

        event_id = dlq_record.get("event_id")
        tenant_id = dlq_record.get("tenant_id")
        payload = dlq_record.get("payload") or {}

        if not event_id or not tenant_id:
            raise ValueError("DLQ record missing mandatory event_id or tenant_id")

        # Idempotency check unless forced
        if not force and self.is_event_processed(event_id):
            logger.info("DLQ replay skipped: event %s was already processed.", event_id)
            return DLQReceipt({
                "status": "RECOVERED",
                "consumer": self.CONSUMER_NAME,
                "event_id": event_id,
                "retries": 0,
                "idempotent": True,
                "dlq": False,
            })

        safe_payload = redact_sensitive_data(payload)

        if handler:
            result = handler(safe_payload)
            if asyncio.iscoroutine(result):
                await result

        # Mark processed
        self.mark_event_processed(event_id)
        self._replayed_count += 1
        self._recovered_count += 1

        logger.info("Successfully replayed DLQ event %s for tenant %s", event_id, tenant_id)

        return DLQReceipt({
            "status": "RECOVERED",
            "consumer": self.CONSUMER_NAME,
            "event_id": event_id,
            "retries": 1,
            "idempotent": True,
            "dlq": False,
        })

    # =========================================================================
    # Observability & Metrics
    # =========================================================================

    def get_dlq_metrics(self) -> Dict[str, Any]:
        """Return operational metrics for monitoring systems and HTTP admin endpoints."""
        redis_dlq_count = 0
        if self.redis_client:
            try:
                redis_dlq_count = self.redis_client.llen(self.dlq_key)
            except Exception:
                pass

        return {
            "consumer": self.CONSUMER_NAME,
            "status": "HEALTHY",
            "dlq_routed_total": self._dlq_routed_count,
            "recovered_total": self._recovered_count,
            "replayed_total": self._replayed_count,
            "redis_dlq_backlog": redis_dlq_count,
            "last_dlq_event_id": self._last_dlq_event_id,
            "last_dlq_timestamp": self._last_dlq_timestamp,
            "dlq_topics": list(DEFAULT_DLQ_TOPICS),
            "shared_dlq_topic": DEFAULT_SHARED_DLQ_TOPIC,
            "default_retention_ms": DEFAULT_DLQ_RETENTION_MS,
        }


# =============================================================================
# Aliases for Architectural Compatibility
# =============================================================================

CreateDeadLetterTopics = ConsumerDeadLetterTopics
Create_dead_letter_topics = ConsumerDeadLetterTopics
DeadLetterTopicService = ConsumerDeadLetterTopics
KafkaDeadLetterManager = ConsumerDeadLetterTopics
DLQTopicManager = ConsumerDeadLetterTopics
ConsumerDLQService = ConsumerDeadLetterTopics
