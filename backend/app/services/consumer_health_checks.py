"""
consumer_health_checks.py

Kafka consumer health, readiness, and processing state monitoring service.

Responsibilities:
- Expose health and readiness probes for Kafka consumer connections, consumer groups,
  partition assignments, lag metrics, and processing throughput.
- Track connectivity, assignment, lag/error state, and last successful processing.
- Maintain real-time operational status (healthy, degraded, unhealthy) in Redis for deployment
  and monitoring systems.
- Safely handle malformed messages and dependency failures without exposing secrets.
- Enforce strict idempotency and tenant-awareness to prevent duplicate business side effects.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Union

from app.redis_client import get_redis_client
from app.services.kafka.consumer import (
    DEFAULT_CONSUMER_GROUPS,
    KafkaConsumerManager,
)
from app.services.kafka.monitoring import kafka_monitoring
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


class ConsumerHealthChecks:
    """
    Consumer health and readiness monitoring service.
    Tracks Kafka connectivity, partition assignment, consumer lag, error state,
    and processing activity.
    """

    CONSUMER_NAME = "Add_health_checks"
    DEFAULT_TOPIC = "fieldops.events"
    DEFAULT_GROUP = "fieldops-health-checks"
    DEFAULT_DLQ_KEY = "consumer:dlq"
    DEFAULT_HEALTH_KEY_PREFIX = "consumer_health"
    MAX_CONSECUTIVE_ERRORS_FOR_HEALTHY = 5
    MAX_LAG_FOR_HEALTHY = 1000
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
        dlq_key: str = DEFAULT_DLQ_KEY,
        bootstrap_servers: Optional[str] = None,
        max_consecutive_errors: int = MAX_CONSECUTIVE_ERRORS_FOR_HEALTHY,
        max_lag: int = MAX_LAG_FOR_HEALTHY,
    ):
        self.topic = topic or self.DEFAULT_TOPIC
        self.group_id = group_id or self.DEFAULT_GROUP
        self.bootstrap_servers = bootstrap_servers
        self.dlq_key = dlq_key
        self.handler = handler
        self.max_consecutive_errors = max_consecutive_errors
        self.max_lag = max_lag

        self._consumer_manager = consumer_manager

        # Health and readiness tracking attributes
        self._connected: bool = False
        self._started_at: Optional[float] = None
        self._processed_count: int = 0
        self._failure_count: int = 0
        self._consecutive_errors: int = 0
        self._last_processed_at: Optional[str] = None
        self._last_event_id: Optional[str] = None
        self._last_error: Optional[str] = None
        self._last_error_at: Optional[str] = None
        self._assigned_partitions: List[str] = []
        self._last_lag_check: Optional[Dict[str, Any]] = None

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
        """Start the underlying Kafka consumer and update health connection state."""
        self._connected = True
        self._started_at = time.monotonic()
        if self._consumer_manager:
            await self._consumer_manager.start()
            self._update_assignment_from_consumer()
        self._persist_health_snapshot()

    async def stop(self) -> None:
        """Stop the consumer and record disconnected state."""
        self._connected = False
        if self._consumer_manager:
            await self._consumer_manager.stop()
        self._persist_health_snapshot()

    async def __aenter__(self) -> "ConsumerHealthChecks":
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: Any,
        exc_value: Any,
        traceback: Any,
    ) -> None:
        await self.stop()

    def _update_assignment_from_consumer(self) -> None:
        """Read partition assignment from underlying AIOKafkaConsumer if available."""
        if not self._consumer_manager or not hasattr(self._consumer_manager, "consumer"):
            return

        try:
            raw_consumer = self._consumer_manager.consumer
            if hasattr(raw_consumer, "assignment"):
                assignment = raw_consumer.assignment()
                if assignment:
                    self._assigned_partitions = [
                        f"{tp.topic}-{tp.partition}" if hasattr(tp, "topic") else str(tp)
                        for tp in sorted(assignment, key=lambda x: getattr(x, "partition", 0))
                    ]
        except Exception as exc:
            logger.debug("Could not inspect consumer partition assignment: %s", exc)

    def set_assigned_partitions(self, partitions: List[str]) -> None:
        """Explicitly set assigned partitions (useful in callbacks or testing)."""
        self._assigned_partitions = list(partitions)
        self._persist_health_snapshot()

    def record_success(self, event_id: str) -> None:
        """Record successful event processing."""
        self._processed_count += 1
        self._consecutive_errors = 0
        self._last_event_id = event_id
        self._last_processed_at = datetime.now(timezone.utc).isoformat()
        self._persist_health_snapshot()

    def record_failure(self, error: Any, event_id: Optional[str] = None) -> None:
        """Record an error in consumer processing."""
        self._failure_count += 1
        self._consecutive_errors += 1
        safe_msg = str(error)
        self._last_error = safe_msg
        self._last_error_at = datetime.now(timezone.utc).isoformat()
        if event_id:
            self._last_event_id = event_id
        self._persist_health_snapshot()

    def is_connected(self) -> bool:
        """Return True if the consumer is connected and active."""
        return self._connected

    def is_ready(self) -> bool:
        """
        Readiness probe:
        Consumer is ready if it is connected and not overwhelmed by consecutive fatal errors.
        """
        return self._connected and (self._consecutive_errors < (self.max_consecutive_errors * 2))

    def is_healthy(self) -> bool:
        """
        Liveness / health probe:
        Consumer is healthy if connected and consecutive errors are below threshold.
        """
        return self._connected and (self._consecutive_errors < self.max_consecutive_errors)

    def determine_status(self, lag_total: Optional[int] = None) -> str:
        """Determine aggregate status: healthy, degraded, or unhealthy."""
        if not self._connected:
            return "unhealthy"

        if self._consecutive_errors >= self.max_consecutive_errors:
            return "unhealthy"

        if self._consecutive_errors > 0:
            return "degraded"

        if lag_total is not None and lag_total > self.max_lag:
            return "degraded"

        return "healthy"

    def record_dlq(self, failure_context: Dict[str, Any]) -> None:
        """Record terminal failure context to DLQ without exposing secrets."""
        if not self.redis_client:
            return

        try:
            safe_payload = redact_sensitive_data(failure_context)
            self.redis_client.rpush(self.dlq_key, json.dumps(safe_payload))
            logger.info(
                "Consumer health check pushed failed event %s to DLQ '%s'",
                failure_context.get("event_id"),
                self.dlq_key,
            )
        except Exception as dlq_err:
            logger.error("Failed to push to DLQ '%s': %s", self.dlq_key, dlq_err)

    def _persist_health_snapshot(self) -> None:
        """Persist current health status snapshot to Redis for external monitoring."""
        if not self.redis_client:
            return

        try:
            key = f"{self.DEFAULT_HEALTH_KEY_PREFIX}:{self.CONSUMER_NAME}:{self.group_id}"
            snapshot = self.get_health_snapshot()
            self.redis_client.set(key, json.dumps(snapshot), ex=300)
        except Exception as exc:
            logger.debug("Failed to persist health snapshot to Redis: %s", exc)

    def get_health_snapshot(self) -> Dict[str, Any]:
        """
        Generate synchronous health snapshot of the consumer state.
        Includes connectivity, assignment, lag/error state, and last processing info.
        """
        uptime = round(time.monotonic() - self._started_at, 2) if self._started_at else 0.0
        status = self.determine_status()

        return {
            "status": status,
            "ready": self.is_ready(),
            "healthy": self.is_healthy(),
            "consumer": self.CONSUMER_NAME,
            "topic": self.topic,
            "group_id": self.group_id,
            "connected": self._connected,
            "assignment": {
                "partitions": list(self._assigned_partitions),
                "count": len(self._assigned_partitions),
            },
            "error_state": {
                "has_errors": self._consecutive_errors > 0 or self._failure_count > 0,
                "consecutive_errors": self._consecutive_errors,
                "failure_count": self._failure_count,
                "last_error": self._last_error,
                "last_error_at": self._last_error_at,
            },
            "processing": {
                "processed_total": self._processed_count,
                "failure_total": self._failure_count,
                "last_event_id": self._last_event_id,
                "last_processed_at": self._last_processed_at,
            },
            "uptime_seconds": uptime,
        }

    async def get_health(self) -> Dict[str, Any]:
        """
        Asynchronously evaluate full health, including real-time partition lag check
        from Kafka monitoring infrastructure.
        """
        self._update_assignment_from_consumer()
        base_snapshot = self.get_health_snapshot()

        lag_info: Dict[str, Any] = {
            "total_lag": 0,
            "partitions": {},
            "status": "healthy",
        }

        try:
            live_lag = await kafka_monitoring.consumer_lag(self.topic, self.group_id)
            if live_lag:
                lag_info = {
                    "total_lag": live_lag.get("lag", 0),
                    "partitions": live_lag.get("partitions", {}),
                    "status": live_lag.get("status", "healthy"),
                }
                self._last_lag_check = lag_info
        except Exception as exc:
            logger.debug("Could not inspect live Kafka lag for %s: %s", self.topic, exc)
            if self._last_lag_check:
                lag_info = self._last_lag_check

        total_lag = lag_info.get("total_lag")
        base_snapshot["lag"] = lag_info
        base_snapshot["status"] = self.determine_status(
            lag_total=total_lag if isinstance(total_lag, int) else None
        )

        return base_snapshot

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
        Process a consumed event with boundary protection, health recording,
        and strict idempotency.
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
                        "error": f"Malformed message encoding: {u_err}",
                        "error_type": "UnicodeDecodeError",
                        "error_classification": ErrorClassification.TERMINAL.value,
                        "retryable": False,
                        "failed_at": now_iso,
                    }
                    self.record_failure(u_err, event_id="unknown")
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
                    self.record_failure(j_err, event_id="unknown")
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
                self.record_failure(f"TypeError: {type(message).__name__}", event_id="unknown")
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
            self.record_failure(parse_exc, event_id="unknown")
            if not retryable:
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
                "error": f"Authorization failure: Topic '{topic}' is not authorized",
                "error_type": "TopicAuthorizationFailedError",
                "error_classification": ErrorClassification.TERMINAL.value,
                "retryable": False,
                "failed_at": now_iso,
            }
            logger.warning(
                "Consumer health checks rejected unauthorized topic '%s' for event %s",
                topic,
                event_id,
            )
            self.record_failure(f"Unauthorized topic '{topic}'", event_id=event_id)
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
                "Consumer health checks schema error for event %s: missing %s",
                event_id,
                missing_fields,
            )
            self.record_failure(f"Validation error: missing {missing_fields}", event_id=event_id)
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
                "Consumer health checks rejected sensitive keys in event %s",
                event_id,
            )
            self.record_failure("Security policy violation: forbidden keys", event_id=event_id)
            self.record_dlq(fail_ctx)
            return ConsumeReceipt(fail_ctx)

        # 5. Idempotency verification via Redis
        idempotency_key = f"consumer_health:event_processed:{event_id}"
        if self.redis_client:
            try:
                if self.redis_client.get(idempotency_key):
                    logger.info(
                        "Event %s already processed; skipping duplicate to prevent duplicate effects.",
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

        # 6. Execute downstream handler if registered
        if self.handler:
            try:
                import inspect
                if inspect.iscoroutinefunction(self.handler):
                    handler_result = await self.handler(payload)
                else:
                    handler_result = self.handler(payload)

                if isinstance(handler_result, dict) and handler_result.get("status") == "FAILED":
                    err_msg = handler_result.get("error", "Downstream handler returned failure")
                    classification, is_retryable = classify_error(err_msg)
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
                    self.record_failure(err_msg, event_id=event_id)
                    if not is_retryable:
                        self.record_dlq(fail_ctx)
                    return ConsumeReceipt(fail_ctx)

            except Exception as handler_exc:
                classification, is_retryable = classify_error(handler_exc)
                fail_ctx = {
                    "status": "FAILED",
                    "consumer": self.CONSUMER_NAME,
                    "event_id": event_id,
                    "tenant_id": tenant_id,
                    "correlation_id": correlation_id,
                    "attempt": attempt,
                    "error": str(handler_exc),
                    "error_type": type(handler_exc).__name__,
                    "error_classification": classification,
                    "retryable": is_retryable,
                    "failed_at": now_iso,
                }
                logger.warning(
                    "Downstream execution failed for event %s: %s",
                    event_id,
                    handler_exc,
                )
                self.record_failure(handler_exc, event_id=event_id)
                if not is_retryable:
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

        # 8. Record health success metrics
        self.record_success(event_id)

        logger.info(
            "Consumer health checks successfully processed event %s (consumer: %s)",
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

    @classmethod
    async def get_all_consumers_health_summary(
        cls,
        redis_client: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Aggregate health snapshot across all standard Kafka consumer groups.
        """
        r = redis_client
        if r is None:
            try:
                r = get_redis_client()
            except Exception:
                r = None

        all_consumers = {}
        for topic, group_id in DEFAULT_CONSUMER_GROUPS.items():
            lag_info = {"lag": None, "status": "unknown"}
            try:
                live_lag = await kafka_monitoring.consumer_lag(topic, group_id)
                if live_lag:
                    lag_info = live_lag
            except Exception:
                pass

            all_consumers[topic] = {
                "topic": topic,
                "group_id": group_id,
                "lag": lag_info.get("lag"),
                "status": lag_info.get("status", "healthy"),
            }

        return {
            "status": "healthy",
            "consumer_count": len(DEFAULT_CONSUMER_GROUPS),
            "consumers": all_consumers,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }


# Aliases for architectural compatibility
ConsumerHealthCheckService = ConsumerHealthChecks
AddHealthChecksConsumer = ConsumerHealthChecks
Add_health_checks = ConsumerHealthChecks
ConsumerHealthMonitor = ConsumerHealthChecks
