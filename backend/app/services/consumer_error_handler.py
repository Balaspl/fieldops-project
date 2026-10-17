"""
consumer_error_handler.py

Kafka consumer boundary error handler and resilient consumer service.

Responsibilities:
- Intercept and handle malformed messages, unavailable dependencies, authorization failures,
  and domain validation errors at consumer boundaries.
- Prevent one bad event from crashing the entire consumer process.
- Classify errors into RETRYABLE and TERMINAL categories while preserving complete failure context.
- Safely redact sensitive keys (password, token, secret, api_key) in operational logs and DLQs.
- Enforce idempotency using Redis markers and route permanently failed / terminal messages to DLQ.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, Optional, Union

from app.redis_client import get_redis_client
from app.services.kafka.consumer import KafkaConsumerManager
from app.services.ai.FieldOpsAI.schemas.agent_messages import (
    MessageEnvelope,
    _FORBIDDEN_KEYS,
)

logger = logging.getLogger(__name__)


class ErrorClassification(str, Enum):
    """Classification of errors occurring at consumer boundaries."""

    RETRYABLE = "RETRYABLE"
    TERMINAL = "TERMINAL"


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


def redact_sensitive_data(data: Any) -> Any:
    """
    Recursively redact sensitive keys from payloads so secrets are never logged or stored in DLQs.
    """
    if isinstance(data, dict):
        cleaned = {}
        for k, v in data.items():
            k_lower = str(k).lower()
            if any(forbidden in k_lower for forbidden in _FORBIDDEN_KEYS):
                cleaned[k] = "[REDACTED]"
            elif isinstance(v, (dict, list)):
                cleaned[k] = redact_sensitive_data(v)
            else:
                cleaned[k] = v
        return cleaned
    elif isinstance(data, list):
        return [redact_sensitive_data(item) for item in data]
    return data


def classify_error(exc: Union[BaseException, str, dict]) -> tuple[str, bool]:
    """
    Classify an error as RETRYABLE (transient) or TERMINAL (fatal).

    Returns:
        tuple of (classification_string, is_retryable_bool)
    """
    if isinstance(exc, (str, dict)):
        msg = str(exc).lower()
        if any(
            pattern in msg
            for pattern in (
                "timeout",
                "timed out",
                "connection refused",
                "network",
                "temporary",
                "unavailable",
                "503",
                "504",
                "429",
                "retry",
            )
        ):
            return ErrorClassification.RETRYABLE.value, True
        return ErrorClassification.TERMINAL.value, False

    exc_name = type(exc).__name__.lower()
    exc_msg = str(exc).lower()

    # Retryable transient failure patterns
    retryable_type_names = (
        "connectionerror",
        "timeouterror",
        "operationalerror",
        "disconnectionerror",
        "kafkaconnectionerror",
        "redistimeouterror",
        "redisconnectionerror",
        "networkerror",
        "clientconnectorerror",
    )
    if any(rt in exc_name for rt in retryable_type_names):
        return ErrorClassification.RETRYABLE.value, True

    if any(
        kw in exc_msg
        for kw in (
            "timeout",
            "timed out",
            "connection refused",
            "temporary failure",
            "service unavailable",
            "rate limit",
            "broker not available",
            "network down",
        )
    ):
        return ErrorClassification.RETRYABLE.value, True

    # Terminal failure patterns
    return ErrorClassification.TERMINAL.value, False


class ConsumerErrorHandler:
    """
    Consumer boundary error handler and resilient consumer.
    Ensures that bad messages, dependency timeouts, or validation errors do not crash the consumer process.
    """

    CONSUMER_NAME = "Add_error_handling"
    DEFAULT_TOPIC = "fieldops.events"
    DEFAULT_GROUP = "fieldops-error-handling"
    DEFAULT_DLQ_KEY = "consumer:dlq"
    DEFAULT_MAX_RETRIES = 3
    SCHEMA_VERSION = 1

    ALLOWED_TOPICS = frozenset({
        "fieldops.events",
        "fieldops.job.events",
        "fieldops.gps.events",
        "fieldops.notification.events",
        "fieldops.sla.events",
        "fieldops.billing.events",
        "fieldops.payment.events",
        "fieldops.audit.events",
        "fieldops.analytics.events",
    })

    def __init__(
        self,
        topic: Optional[str] = None,
        group_id: Optional[str] = None,
        consumer_manager: Optional[KafkaConsumerManager] = None,
        redis_client: Optional[Any] = None,
        handler: Optional[Callable[[Dict[str, Any]], Any]] = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        dlq_key: str = DEFAULT_DLQ_KEY,
        bootstrap_servers: Optional[str] = None,
    ):
        self.topic = topic or self.DEFAULT_TOPIC
        self.group_id = group_id or self.DEFAULT_GROUP
        self.bootstrap_servers = bootstrap_servers
        self.max_retries = max_retries
        self.dlq_key = dlq_key
        self.handler = handler

        self._consumer_manager = consumer_manager

        if redis_client is not None:
            self.redis_client = redis_client
        else:
            try:
                self.redis_client = get_redis_client()
            except Exception:
                self.redis_client = None

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

    async def __aenter__(self) -> "ConsumerErrorHandler":
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: Any,
        exc_value: Any,
        traceback: Any,
    ) -> None:
        await self.stop()

    def record_dlq(self, failure_context: Dict[str, Any]) -> None:
        """
        Record permanent or exhausted failure context to DLQ without exposing secrets.
        """
        if not self.redis_client:
            return

        try:
            safe_payload = redact_sensitive_data(failure_context)
            self.redis_client.rpush(self.dlq_key, json.dumps(safe_payload))
            logger.info(
                "Pushed failed event %s to DLQ '%s' (classification: %s)",
                failure_context.get("event_id"),
                self.dlq_key,
                failure_context.get("error_classification"),
            )
        except Exception as dlq_err:
            logger.error("Failed to push to DLQ '%s': %s", self.dlq_key, dlq_err)

    async def handle_message(
        self,
        message: Any,
        attempt: int = 1,
    ) -> ConsumeReceipt:
        """Callback suitable for KafkaConsumerManager.consume(handler)."""
        return await self.process_event(message, attempt=attempt)

    async def process_event(
        self,
        message: Any,
        attempt: int = 1,
    ) -> ConsumeReceipt:
        """
        Boundary event processor that intercepts malformed messages, authorization errors,
        validation errors, and dependency failures without crashing.
        """
        now_iso = datetime.now(timezone.utc).isoformat()

        # 1. Parse / unpack message payload and metadata safely
        try:
            if isinstance(message, (bytes, bytearray)):
                try:
                    message = message.decode("utf-8")
                except UnicodeDecodeError as u_err:
                    fail_ctx = {
                        "status": "FAILED",
                        "consumer": self.CONSUMER_NAME,
                        "event_id": "unknown",
                        "attempt": attempt,
                        "error": f"Malformed message encoding: {u_err}",
                        "error_type": "UnicodeDecodeError",
                        "error_classification": ErrorClassification.TERMINAL.value,
                        "retryable": False,
                        "failed_at": now_iso,
                    }
                    self.record_dlq(fail_ctx)
                    return ConsumeReceipt(fail_ctx)

            if isinstance(message, str):
                try:
                    message = json.loads(message)
                except json.JSONDecodeError as j_err:
                    fail_ctx = {
                        "status": "FAILED",
                        "consumer": self.CONSUMER_NAME,
                        "event_id": "unknown",
                        "attempt": attempt,
                        "error": f"Malformed JSON message: {j_err}",
                        "error_type": "JSONDecodeError",
                        "error_classification": ErrorClassification.TERMINAL.value,
                        "retryable": False,
                        "failed_at": now_iso,
                    }
                    self.record_dlq(fail_ctx)
                    return ConsumeReceipt(fail_ctx)

            if isinstance(message, MessageEnvelope):
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
                fail_ctx = {
                    "status": "FAILED",
                    "consumer": self.CONSUMER_NAME,
                    "event_id": "unknown",
                    "attempt": attempt,
                    "error": f"Unsupported message type: {type(message).__name__}",
                    "error_type": "TypeError",
                    "error_classification": ErrorClassification.TERMINAL.value,
                    "retryable": False,
                    "failed_at": now_iso,
                }
                self.record_dlq(fail_ctx)
                return ConsumeReceipt(fail_ctx)

        except Exception as parse_exc:
            classification, retryable = classify_error(parse_exc)
            fail_ctx = {
                "status": "FAILED",
                "consumer": self.CONSUMER_NAME,
                "event_id": "unknown",
                "attempt": attempt,
                "error": f"Message parse error: {parse_exc}",
                "error_type": type(parse_exc).__name__,
                "error_classification": classification,
                "retryable": retryable,
                "failed_at": now_iso,
            }
            if not retryable:
                self.record_dlq(fail_ctx)
            return ConsumeReceipt(fail_ctx)

        event_id = payload.get("event_id") or "unknown"
        tenant_id = payload.get("tenant_id")
        schema_version = payload.get("schema_version")
        raw_event_type = payload.get("event_type") or payload.get("event")

        # 2. Topic authorization check
        if topic and topic not in self.ALLOWED_TOPICS:
            fail_ctx = {
                "status": "FAILED",
                "consumer": self.CONSUMER_NAME,
                "event_id": event_id,
                "tenant_id": tenant_id,
                "correlation_id": correlation_id,
                "attempt": attempt,
                "error": f"Authorization failure: Topic '{topic}' is not authorized",
                "error_type": "TopicAuthorizationFailedError",
                "error_classification": ErrorClassification.TERMINAL.value,
                "retryable": False,
                "failed_at": now_iso,
            }
            logger.warning(
                "Consumer boundary rejected unauthorized topic '%s' for event %s",
                topic,
                event_id,
            )
            self.record_dlq(fail_ctx)
            return ConsumeReceipt(fail_ctx)

        # 3. Schema & contract validation
        missing_fields = []
        if not payload.get("event_id") or not str(payload.get("event_id")).strip():
            missing_fields.append("event_id")
        if not tenant_id or not str(tenant_id).strip():
            missing_fields.append("tenant_id")
        if schema_version is None:
            missing_fields.append("schema_version")

        if missing_fields:
            fail_ctx = {
                "status": "FAILED",
                "consumer": self.CONSUMER_NAME,
                "event_id": event_id,
                "tenant_id": tenant_id,
                "correlation_id": correlation_id,
                "attempt": attempt,
                "error": f"Schema validation error: Missing required fields: {', '.join(sorted(missing_fields))}",
                "error_type": "ValidationError",
                "error_classification": ErrorClassification.TERMINAL.value,
                "retryable": False,
                "failed_at": now_iso,
            }
            logger.warning(
                "Consumer boundary schema error for event %s: missing %s",
                event_id,
                missing_fields,
            )
            self.record_dlq(fail_ctx)
            return ConsumeReceipt(fail_ctx)

        # 4. Security & forbidden keys check
        lowered_keys = {str(k).lower() for k in payload.keys()}
        found_forbidden = lowered_keys.intersection(_FORBIDDEN_KEYS)
        if found_forbidden:
            fail_ctx = {
                "status": "FAILED",
                "consumer": self.CONSUMER_NAME,
                "event_id": event_id,
                "tenant_id": tenant_id,
                "correlation_id": correlation_id,
                "attempt": attempt,
                "error": f"Security violation: Payload contains forbidden sensitive keys: {', '.join(sorted(found_forbidden))}",
                "error_type": "SecurityPolicyError",
                "error_classification": ErrorClassification.TERMINAL.value,
                "retryable": False,
                "failed_at": now_iso,
            }
            logger.warning(
                "Consumer boundary rejected sensitive keys in event %s",
                event_id,
            )
            self.record_dlq(fail_ctx)
            return ConsumeReceipt(fail_ctx)

        # 5. Idempotency verification via Redis
        idempotency_key = f"consumer_error_handling:event_processed:{event_id}"
        if self.redis_client:
            try:
                if self.redis_client.get(idempotency_key):
                    logger.info(
                        "Event %s already processed; skipping duplicate.",
                        event_id,
                    )
                    return ConsumeReceipt(
                        {
                            "status": "PROCESSED",
                            "consumer": self.CONSUMER_NAME,
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

        # 6. Execute downstream / wrapped handler with bounded failure recovery
        if self.handler:
            try:
                import inspect
                if inspect.iscoroutinefunction(self.handler):
                    handler_result = await self.handler(payload)
                else:
                    handler_result = self.handler(payload)

                # If handler returns a dict receipt that failed, respect its status
                if isinstance(handler_result, dict) and handler_result.get("status") == "FAILED":
                    err_msg = handler_result.get("error", "Downstream handler returned failure")
                    classification, is_retryable = classify_error(err_msg)
                    is_retryable = is_retryable and (attempt < self.max_retries)
                    fail_ctx = {
                        "status": "FAILED",
                        "consumer": self.CONSUMER_NAME,
                        "event_id": event_id,
                        "tenant_id": tenant_id,
                        "correlation_id": correlation_id,
                        "attempt": attempt,
                        "error": err_msg,
                        "error_type": handler_result.get("error_type", "DomainFailure"),
                        "error_classification": classification,
                        "retryable": is_retryable,
                        "failed_at": now_iso,
                    }
                    if not is_retryable:
                        self.record_dlq(fail_ctx)
                    return ConsumeReceipt(fail_ctx)

            except Exception as handler_exc:
                classification, is_retryable = classify_error(handler_exc)
                effective_retryable = is_retryable and (attempt < self.max_retries)
                fail_ctx = {
                    "status": "FAILED",
                    "consumer": self.CONSUMER_NAME,
                    "event_id": event_id,
                    "tenant_id": tenant_id,
                    "correlation_id": correlation_id,
                    "attempt": attempt,
                    "max_retries": self.max_retries,
                    "error": str(handler_exc),
                    "error_type": type(handler_exc).__name__,
                    "error_classification": classification,
                    "retryable": effective_retryable,
                    "failed_at": now_iso,
                }
                logger.error(
                    "Downstream handler failed for event %s (attempt %d/%d, classification: %s): %s",
                    event_id,
                    attempt,
                    self.max_retries,
                    classification,
                    handler_exc,
                )
                if not effective_retryable:
                    self.record_dlq(fail_ctx)
                return ConsumeReceipt(fail_ctx)

        # 7. Enforce idempotency on successful processing
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
            "Consumer boundary successfully processed event %s (consumer: %s)",
            event_id,
            self.CONSUMER_NAME,
        )

        return ConsumeReceipt(
            {
                "status": "PROCESSED",
                "consumer": self.CONSUMER_NAME,
                "event_id": event_id,
                "attempt": attempt,
            }
        )

    def wrap_handler(
        self,
        handler: Callable[[Dict[str, Any]], Any],
    ) -> Callable[[Any], Any]:
        """
        Wrap any existing consumer callback in the boundary error handler.
        Prevents raw exceptions from crashing the consumer loop.
        """
        async def safe_handler(message: Any, attempt: int = 1) -> ConsumeReceipt:
            # Temporarily configure handler and process safely
            old_handler = self.handler
            self.handler = handler
            try:
                return await self.process_event(message, attempt=attempt)
            finally:
                self.handler = old_handler

        return safe_handler


# Aliases for flexible integration
AddErrorHandlingConsumer = ConsumerErrorHandler
ConsumerBoundaryHandler = ConsumerErrorHandler
Add_error_handling = ConsumerErrorHandler

