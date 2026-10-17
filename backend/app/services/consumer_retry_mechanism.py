"""
consumer_retry_mechanism.py

Kafka consumer retry mechanism with bounded exponential backoff, attempt tracking,
and idempotent handling for FieldOps event streams.

Responsibilities:
- Retry transient consumer processing failures with bounded exponential backoff.
- Recover from temporary downstream failures without duplicate business actions.
- Distinguish between retryable (transient) and non-retryable (terminal) errors.
- Track attempt counts and route exhausted failures to reliability DLQ paths.
- Ensure strict idempotency using Redis markers to prevent duplicate business side effects.
- Redact sensitive keys (password, token, secret, api_key) in logs and DLQ payloads.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, Union

from app.redis_client import get_redis_client
from app.services.kafka.consumer import KafkaConsumerManager
from app.services.ai.FieldOpsAI.schemas.agent_messages import (
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


class ConsumerRetryMechanism:
    """
    Resilient consumer retry manager with bounded backoff and idempotency protection.
    Ensures safe, bounded retry for transient failures without duplicate business actions.
    """

    CONSUMER_NAME = "Add_retry_mechanism"
    DEFAULT_TOPIC = "fieldops.events"
    DEFAULT_GROUP = "fieldops-retry-mechanism"
    DEFAULT_DLQ_KEY = "consumer:dlq"
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_BASE_DELAY = 1.0
    DEFAULT_MAX_DELAY = 30.0
    DEFAULT_BACKOFF_FACTOR = 2.0
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
        base_delay: float = DEFAULT_BASE_DELAY,
        max_delay: float = DEFAULT_MAX_DELAY,
        backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
        jitter: bool = False,
        dlq_key: str = DEFAULT_DLQ_KEY,
        bootstrap_servers: Optional[str] = None,
    ):
        self.topic = topic or self.DEFAULT_TOPIC
        self.group_id = group_id or self.DEFAULT_GROUP
        self.bootstrap_servers = bootstrap_servers
        self.max_retries = max(1, max_retries)
        self.base_delay = max(0.0, base_delay)
        self.max_delay = max(self.base_delay, max_delay)
        self.backoff_factor = max(1.0, backoff_factor)
        self.jitter = jitter
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

    async def __aenter__(self) -> "ConsumerRetryMechanism":
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: Any,
        exc_value: Any,
        traceback: Any,
    ) -> None:
        await self.stop()

    def calculate_backoff(self, attempt: int) -> float:
        """
        Calculate bounded exponential backoff delay for the given attempt number.

        Formula:
            delay = min(max_delay, base_delay * (backoff_factor ** (attempt - 1)))
        """
        if attempt <= 1:
            delay = self.base_delay
        else:
            delay = min(
                self.max_delay,
                self.base_delay * (self.backoff_factor ** (attempt - 1)),
            )

        if self.jitter and delay > 0:
            delay += random.uniform(0, delay * 0.1)

        return round(delay, 4)

    def record_dlq(self, failure_context: Dict[str, Any]) -> None:
        """
        Route exhausted or terminal failure context to DLQ safely with redacted secrets.
        """
        if not self.redis_client:
            return

        try:
            safe_payload = redact_sensitive_data(failure_context)
            self.redis_client.rpush(self.dlq_key, json.dumps(safe_payload))
            logger.info(
                "Pushed failed event %s to DLQ '%s' (exhausted/terminal: %s, attempt %s/%s)",
                failure_context.get("event_id"),
                self.dlq_key,
                failure_context.get("error_classification"),
                failure_context.get("attempt"),
                failure_context.get("max_retries"),
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
        Process a single attempt for a message with strict idempotency and bounded failure handling.
        """
        now_iso = datetime.now(timezone.utc).isoformat()

        # 1. Parse / unpack message payload safely
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
                        "max_retries": self.max_retries,
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
                        "max_retries": self.max_retries,
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
                    "max_retries": self.max_retries,
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
                "max_retries": self.max_retries,
                "error": f"Message parse error: {parse_exc}",
                "error_type": type(parse_exc).__name__,
                "error_classification": classification,
                "retryable": retryable and (attempt < self.max_retries),
                "failed_at": now_iso,
            }
            if not fail_ctx["retryable"]:
                self.record_dlq(fail_ctx)
            return ConsumeReceipt(fail_ctx)

        event_id = payload.get("event_id") or "unknown"
        tenant_id = payload.get("tenant_id")
        schema_version = payload.get("schema_version")

        # 2. Topic authorization check
        if topic and topic not in self.ALLOWED_TOPICS:
            fail_ctx = {
                "status": "FAILED",
                "consumer": self.CONSUMER_NAME,
                "event_id": event_id,
                "tenant_id": tenant_id,
                "correlation_id": correlation_id,
                "attempt": attempt,
                "max_retries": self.max_retries,
                "error": f"Authorization failure: Topic '{topic}' is not authorized",
                "error_type": "TopicAuthorizationFailedError",
                "error_classification": ErrorClassification.TERMINAL.value,
                "retryable": False,
                "failed_at": now_iso,
            }
            logger.warning(
                "Consumer retry mechanism rejected unauthorized topic '%s' for event %s",
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
                "max_retries": self.max_retries,
                "error": f"Schema validation error: Missing required fields: {', '.join(sorted(missing_fields))}",
                "error_type": "ValidationError",
                "error_classification": ErrorClassification.TERMINAL.value,
                "retryable": False,
                "failed_at": now_iso,
            }
            logger.warning(
                "Consumer retry mechanism schema error for event %s: missing %s",
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
                "max_retries": self.max_retries,
                "error": f"Security violation: Payload contains forbidden sensitive keys: {', '.join(sorted(found_forbidden))}",
                "error_type": "SecurityPolicyError",
                "error_classification": ErrorClassification.TERMINAL.value,
                "retryable": False,
                "failed_at": now_iso,
            }
            logger.warning(
                "Consumer retry mechanism rejected sensitive keys in event %s",
                event_id,
            )
            self.record_dlq(fail_ctx)
            return ConsumeReceipt(fail_ctx)

        # 5. Idempotency verification via Redis
        # Pre-execution check prevents duplicate business actions across retries.
        idempotency_key = f"consumer_retry:event_processed:{event_id}"
        if self.redis_client:
            try:
                if self.redis_client.get(idempotency_key):
                    logger.info(
                        "Event %s already processed; skipping duplicate to prevent duplicate business side effects.",
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

        # 6. Execute downstream handler with transient failure detection & bounded retry accounting
        if self.handler:
            try:
                import inspect
                if inspect.iscoroutinefunction(self.handler):
                    handler_result = await self.handler(payload)
                else:
                    handler_result = self.handler(payload)

                # Check if handler explicitly returned a failed status dict
                if isinstance(handler_result, dict) and handler_result.get("status") == "FAILED":
                    err_msg = handler_result.get("error", "Downstream handler returned failure")
                    classification, is_retryable = classify_error(err_msg)
                    can_retry = is_retryable and (attempt < self.max_retries)
                    backoff = self.calculate_backoff(attempt) if can_retry else 0.0

                    fail_ctx = {
                        "status": "FAILED",
                        "consumer": self.CONSUMER_NAME,
                        "event_id": event_id,
                        "tenant_id": tenant_id,
                        "correlation_id": correlation_id,
                        "attempt": attempt,
                        "max_retries": self.max_retries,
                        "error": err_msg,
                        "error_type": handler_result.get("error_type", "DomainFailure"),
                        "error_classification": classification,
                        "retryable": can_retry,
                        "exhausted": is_retryable and (attempt >= self.max_retries),
                        "backoff_delay": backoff,
                        "next_attempt": (attempt + 1) if can_retry else None,
                        "failed_at": now_iso,
                    }
                    if not can_retry:
                        self.record_dlq(fail_ctx)
                    return ConsumeReceipt(fail_ctx)

            except Exception as handler_exc:
                classification, is_retryable = classify_error(handler_exc)
                can_retry = is_retryable and (attempt < self.max_retries)
                exhausted = is_retryable and (attempt >= self.max_retries)
                backoff = self.calculate_backoff(attempt) if can_retry else 0.0

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
                    "retryable": can_retry,
                    "exhausted": exhausted,
                    "backoff_delay": backoff,
                    "next_attempt": (attempt + 1) if can_retry else None,
                    "failed_at": now_iso,
                }
                logger.warning(
                    "Downstream execution failed for event %s (attempt %d/%d, classification: %s, can_retry: %s): %s",
                    event_id,
                    attempt,
                    self.max_retries,
                    classification,
                    can_retry,
                    handler_exc,
                )
                if not can_retry:
                    self.record_dlq(fail_ctx)
                return ConsumeReceipt(fail_ctx)

        # 7. Record idempotency marker upon successful processing
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
            "Consumer retry mechanism successfully processed event %s (attempt %d/%d, consumer: %s)",
            event_id,
            attempt,
            self.max_retries,
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

    async def process_with_retry(
        self,
        message: Any,
        max_retries: Optional[int] = None,
    ) -> ConsumeReceipt:
        """
        Execute event processing with automated bounded exponential backoff until success
        or until retries are exhausted.
        """
        limit = max_retries or self.max_retries
        last_receipt = None

        for attempt in range(1, limit + 1):
            receipt = await self.process_event(message, attempt=attempt)
            last_receipt = receipt

            if receipt.get("status") == "PROCESSED":
                return receipt

            # If failure is not retryable (terminal or exhausted), stop immediately
            if not receipt.get("retryable"):
                logger.error(
                    "Event %s processing terminated without retry (attempt %d/%d, classification: %s)",
                    receipt.get("event_id"),
                    attempt,
                    limit,
                    receipt.get("error_classification"),
                )
                return receipt

            # Bounded backoff delay before next attempt
            delay = receipt.get("backoff_delay", self.calculate_backoff(attempt))
            logger.info(
                "Transient failure on event %s (attempt %d/%d). Retrying in %.2fs...",
                receipt.get("event_id"),
                attempt,
                limit,
                delay,
            )
            await asyncio.sleep(delay)

        return last_receipt or ConsumeReceipt({
            "status": "FAILED",
            "consumer": self.CONSUMER_NAME,
            "event_id": "unknown",
            "attempt": limit,
            "max_retries": limit,
            "error": "Exhausted retries in process_with_retry",
            "retryable": False,
            "exhausted": True,
        })

    def wrap_with_retry(
        self,
        handler: Callable[[Dict[str, Any]], Any],
    ) -> Callable[[Any], Any]:
        """
        Wrap an arbitrary downstream handler with automated bounded retry backoff.
        """
        async def resilient_handler(message: Any, attempt: int = 1) -> ConsumeReceipt:
            old_handler = self.handler
            self.handler = handler
            try:
                return await self.process_with_retry(message)
            finally:
                self.handler = old_handler

        return resilient_handler


# Aliases for architectural flexibility
ConsumerRetryManager = ConsumerRetryMechanism
AddRetryMechanismConsumer = ConsumerRetryMechanism
Add_retry_mechanism = ConsumerRetryMechanism
RetryConsumer = ConsumerRetryMechanism

