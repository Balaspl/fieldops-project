"""
failed_event_storage.py

Durable failed-event storage and error context persistence for FieldOps Kafka streams.

Responsibilities:
- Persist failed event metadata and processing error context for investigation, auditing, and recovery.
- Provide durable evidence beyond transient logs in Redis and audit stores.
- Store tenant, event, topic, partition, offset, attempt, and error metadata while protecting sensitive payload data.
- Enforce strict credential redaction for sensitive keys (password, secret, token, api_key).
- Provide query, inspection, and resolution lifecycle APIs (store, get, list, mark_resolved).
- Guarantee exact output contract compliance on recovery:
    {
        "status": "RECOVERED",
        "event_id": "evt_01JEXAMPLE",
        "retries": 1,
        "idempotent": true,
        "dlq": false
    }
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from app.redis_client import get_redis_client
from app.services.kafka.producer import KafkaProducer
from app.services.kafka.consumer import KafkaConsumerManager
from app.services.kafka.topics import (
    DEFAULT_KAFKA_TOPICS,
    DEFAULT_DLQ_TOPICS,
    DEFAULT_SHARED_DLQ_TOPIC,
    get_dlq_topic,
    is_dlq_topic,
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


class FailedEventReceipt(dict):
    """
    Structured dictionary receipt returned after failed-event processing or recovery.
    Complies with the required output contract:
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
    def is_recovered(self) -> bool:
        return self.get("status") == "RECOVERED"

    @property
    def is_dlq(self) -> bool:
        return bool(self.get("dlq", False))

    @property
    def is_stored(self) -> bool:
        return bool(self.get("failed_event_stored", False))

    def __bool__(self) -> bool:
        return self.is_success or self.is_dlq


class FailedEventStorage:
    """
    Durable storage and lifecycle manager for failed Kafka events and processing context.
    Persists detailed failure context beyond transient logs while redacting credentials.
    """

    CONSUMER_NAME = "Add_failed_event_storage"
    DEFAULT_TOPIC = "fieldops.events"
    DEFAULT_GROUP = "fieldops-failed-event-storage"
    DEFAULT_DLQ_KEY = "consumer:dlq"
    DEFAULT_STORAGE_PREFIX = "failed_event"
    DEFAULT_INDEX_KEY = "failed_events:list"
    DEFAULT_TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days durable retention
    DEFAULT_MAX_RETRIES = 3
    SCHEMA_VERSION = 1

    ALLOWED_TOPICS = frozenset(
        set(DEFAULT_KAFKA_TOPICS)
        | set(DEFAULT_DLQ_TOPICS)
        | {DEFAULT_SHARED_DLQ_TOPIC, "fieldops.analytics.events"}
    )

    # In-memory operational metrics
    _metrics: Dict[str, Any] = {
        "processed_total": 0,
        "failed_events_stored": 0,
        "failed_events_resolved": 0,
        "recovered_total": 0,
        "errors_total": 0,
        "by_classification": {
            "TERMINAL": 0,
            "RETRYABLE": 0,
        },
    }

    def __init__(
        self,
        topic: Optional[str] = None,
        group_id: Optional[str] = None,
        consumer_manager: Optional[KafkaConsumerManager] = None,
        redis_client: Optional[Any] = None,
        handler: Optional[Callable[[Dict[str, Any]], Any]] = None,
        dlq_key: str = DEFAULT_DLQ_KEY,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        bootstrap_servers: Optional[str] = None,
    ):
        self.topic = topic or self.DEFAULT_TOPIC
        self.group_id = group_id or self.DEFAULT_GROUP
        self.bootstrap_servers = bootstrap_servers
        self.dlq_key = dlq_key
        self.ttl_seconds = max(60, ttl_seconds)
        self.max_retries = max(1, max_retries)
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

    async def __aenter__(self) -> "FailedEventStorage":
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: Any,
        exc_value: Any,
        traceback: Any,
    ) -> None:
        await self.stop()

    # =========================================================================
    # Durable Failed Event Storage & Retrieval
    # =========================================================================

    def _event_key(self, event_id: str) -> str:
        return f"{self.DEFAULT_STORAGE_PREFIX}:{event_id}"

    def _tenant_index_key(self, tenant_id: str) -> str:
        return f"failed_events:tenant:{tenant_id}"

    def store_failed_event(
        self,
        failure_context: Dict[str, Any],
    ) -> Optional[str]:
        """
        Durable storage of failed event metadata and error context.
        Protects sensitive payload data by redacting credentials.
        Returns the stored event key or ID.
        """
        if not self.redis_client:
            logger.warning("Redis client unavailable; failed event not stored in Redis.")
            return None

        event_id = str(failure_context.get("event_id") or f"fail_{uuid.uuid4().hex[:12]}")
        tenant_id = str(failure_context.get("tenant_id") or "default")

        # 1. Sanitize & redact sensitive fields from entire failure context
        safe_context = redact_sensitive_data(dict(failure_context))

        # Ensure standard metadata fields are explicitly present
        record = {
            "event_id": event_id,
            "tenant_id": tenant_id,
            "topic": failure_context.get("topic") or self.topic,
            "partition": failure_context.get("partition", 0),
            "offset": failure_context.get("offset", 0),
            "attempt": failure_context.get("attempt", 1),
            "correlation_id": failure_context.get("correlation_id"),
            "domain": failure_context.get("domain", "default"),
            "error": failure_context.get("error", "Unknown error"),
            "error_type": failure_context.get("error_type", "ProcessingError"),
            "error_classification": failure_context.get("error_classification", ErrorClassification.TERMINAL.value),
            "failed_at": failure_context.get("failed_at") or datetime.now(timezone.utc).isoformat(),
            "resolved": False,
            "resolved_at": None,
            "payload": safe_context.get("payload") if "payload" in safe_context else safe_context,
            "stored_by": self.CONSUMER_NAME,
        }

        try:
            serialized = json.dumps(record, default=str)
            key = self._event_key(event_id)

            # Store individual record with 30-day retention
            self.redis_client.set(key, serialized, ex=self.ttl_seconds)

            # Push to global failed events index
            if hasattr(self.redis_client, "rpush"):
                self.redis_client.rpush(self.DEFAULT_INDEX_KEY, event_id)
                self.redis_client.rpush(self._tenant_index_key(tenant_id), event_id)
                # Keep backward compatibility with legacy DLQ list
                self.redis_client.rpush(self.dlq_key, serialized)

            classification = record["error_classification"]
            if classification in self._metrics["by_classification"]:
                self._metrics["by_classification"][classification] += 1
            self._metrics["failed_events_stored"] += 1

            logger.info("Durable failed event stored: %s (tenant: %s, error: %s)", event_id, tenant_id, record["error"])
            return event_id

        except Exception as e:
            logger.error("Failed to store failed event %s: %s", event_id, e)
            return None

    def get_failed_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve stored failed event record by event_id for diagnosis or recovery."""
        if not self.redis_client or not event_id:
            return None

        try:
            val = self.redis_client.get(self._event_key(event_id))
            if val:
                return json.loads(val)
            return None
        except Exception as e:
            logger.warning("Error fetching failed event %s: %s", event_id, e)
            return None

    def list_failed_events(
        self,
        tenant_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        List recently stored failed events, optionally filtered by tenant_id.
        """
        if not self.redis_client:
            return []

        index_key = self._tenant_index_key(tenant_id) if tenant_id else self.DEFAULT_INDEX_KEY
        results = []

        try:
            if hasattr(self.redis_client, "lrange"):
                event_ids = self.redis_client.lrange(index_key, -limit, -1)
                for eid in reversed(event_ids):
                    eid_str = eid.decode("utf-8") if isinstance(eid, bytes) else str(eid)
                    item = self.get_failed_event(eid_str)
                    if item:
                        results.append(item)
            return results
        except Exception as e:
            logger.warning("Error listing failed events from %s: %s", index_key, e)
            return []

    def mark_resolved(
        self,
        event_id: str,
        resolution_metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Mark a failed event as resolved after successful replay or administrative remediation.
        """
        if not self.redis_client or not event_id:
            return False

        key = self._event_key(event_id)
        try:
            record = self.get_failed_event(event_id)
            if not record:
                return False

            record["resolved"] = True
            record["resolved_at"] = datetime.now(timezone.utc).isoformat()
            if resolution_metadata:
                record["resolution_metadata"] = resolution_metadata

            self.redis_client.set(key, json.dumps(record, default=str), ex=self.ttl_seconds)
            self._metrics["failed_events_resolved"] += 1
            logger.info("Marked failed event %s as resolved", event_id)
            return True
        except Exception as e:
            logger.warning("Error marking failed event %s resolved: %s", event_id, e)
            return False

    # =========================================================================
    # Event Processing with Automatic Durable Failure Storage
    # =========================================================================

    async def handle_message(self, message: Any) -> FailedEventReceipt:
        """Callback suitable for KafkaConsumerManager.consume(handler)."""
        topic = getattr(message, "topic", self.topic)
        partition = getattr(message, "partition", 0)
        offset = getattr(message, "offset", 0)
        val = getattr(message, "value", message)
        return await self.process_event(val, topic=topic, partition=partition, offset=offset)

    async def process_event(
        self,
        message: Any,
        topic: Optional[str] = None,
        partition: int = 0,
        offset: int = 0,
        attempt: int = 1,
        handler: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ) -> FailedEventReceipt:
        """
        Process event and durably store metadata/error context upon any failure.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        current_topic = topic or self.topic

        # 1. Parse & decode message payload safely
        try:
            if isinstance(message, (bytes, bytearray)):
                try:
                    message = message.decode("utf-8")
                except UnicodeDecodeError as u_err:
                    self._metrics["errors_total"] += 1
                    fail_ctx = {
                        "event_id": f"malformed_bytes_{uuid.uuid4().hex[:8]}",
                        "tenant_id": "unknown",
                        "topic": current_topic,
                        "partition": partition,
                        "offset": offset,
                        "attempt": attempt,
                        "error": f"Malformed message encoding: {u_err}",
                        "error_type": "UnicodeDecodeError",
                        "error_classification": ErrorClassification.TERMINAL.value,
                        "failed_at": now_iso,
                        "payload": "<binary decode error>",
                    }
                    self.store_failed_event(fail_ctx)
                    return FailedEventReceipt({
                        "status": "FAILED",
                        "consumer": self.CONSUMER_NAME,
                        "event_id": fail_ctx["event_id"],
                        "error": fail_ctx["error"],
                        "error_type": fail_ctx["error_type"],
                        "error_classification": fail_ctx["error_classification"],
                        "retryable": False,
                        "idempotent": False,
                        "dlq": True,
                        "failed_event_stored": True,
                    })

            if isinstance(message, str):
                try:
                    message = json.loads(message)
                except json.JSONDecodeError as j_err:
                    self._metrics["errors_total"] += 1
                    fail_ctx = {
                        "event_id": f"malformed_json_{uuid.uuid4().hex[:8]}",
                        "tenant_id": "unknown",
                        "topic": current_topic,
                        "partition": partition,
                        "offset": offset,
                        "attempt": attempt,
                        "error": f"Malformed JSON message: {j_err}",
                        "error_type": "JSONDecodeError",
                        "error_classification": ErrorClassification.TERMINAL.value,
                        "failed_at": now_iso,
                        "payload": message[:200] if len(message) > 200 else message,
                    }
                    self.store_failed_event(fail_ctx)
                    return FailedEventReceipt({
                        "status": "FAILED",
                        "consumer": self.CONSUMER_NAME,
                        "event_id": fail_ctx["event_id"],
                        "error": fail_ctx["error"],
                        "error_type": fail_ctx["error_type"],
                        "error_classification": fail_ctx["error_classification"],
                        "retryable": False,
                        "idempotent": False,
                        "dlq": True,
                        "failed_event_stored": True,
                    })

            if isinstance(message, MessageEnvelope):
                payload = message.payload
                correlation_id = getattr(message, "correlation_id", None) or payload.get("correlation_id")
                current_topic = getattr(message, "topic", None) or current_topic
            elif isinstance(message, dict):
                if "payload" in message and isinstance(message["payload"], dict):
                    payload = message["payload"]
                    correlation_id = message.get("correlation_id") or payload.get("correlation_id")
                    current_topic = message.get("topic") or current_topic
                else:
                    payload = message
                    correlation_id = payload.get("correlation_id")
                    current_topic = message.get("topic") or current_topic
            else:
                self._metrics["errors_total"] += 1
                fail_ctx = {
                    "event_id": f"invalid_type_{uuid.uuid4().hex[:8]}",
                    "tenant_id": "unknown",
                    "topic": current_topic,
                    "partition": partition,
                    "offset": offset,
                    "attempt": attempt,
                    "error": f"Unsupported message type: {type(message).__name__}",
                    "error_type": "TypeError",
                    "error_classification": ErrorClassification.TERMINAL.value,
                    "failed_at": now_iso,
                    "payload": str(message),
                }
                self.store_failed_event(fail_ctx)
                return FailedEventReceipt({
                    "status": "FAILED",
                    "consumer": self.CONSUMER_NAME,
                    "event_id": fail_ctx["event_id"],
                    "error": fail_ctx["error"],
                    "error_type": fail_ctx["error_type"],
                    "error_classification": fail_ctx["error_classification"],
                    "retryable": False,
                    "idempotent": False,
                    "dlq": True,
                    "failed_event_stored": True,
                })

        except Exception as parse_exc:
            self._metrics["errors_total"] += 1
            fail_ctx = {
                "event_id": "parse_failure",
                "tenant_id": "unknown",
                "topic": current_topic,
                "partition": partition,
                "offset": offset,
                "attempt": attempt,
                "error": f"Message parse error: {parse_exc}",
                "error_type": type(parse_exc).__name__,
                "failed_at": now_iso,
            }
            self.store_failed_event(fail_ctx)
            return FailedEventReceipt({
                "status": "FAILED",
                "consumer": self.CONSUMER_NAME,
                "event_id": fail_ctx["event_id"],
                "error": fail_ctx["error"],
                "error_type": fail_ctx["error_type"],
                "idempotent": False,
                "dlq": True,
                "failed_event_stored": True,
            })

        event_id = payload.get("event_id") or "unknown"
        tenant_id = payload.get("tenant_id") or "unknown"
        schema_version = payload.get("schema_version")
        domain = payload.get("domain") or "default"

        # 2. Topic authorization check
        if current_topic and current_topic not in self.ALLOWED_TOPICS:
            self._metrics["errors_total"] += 1
            fail_ctx = {
                "event_id": event_id,
                "tenant_id": tenant_id,
                "correlation_id": correlation_id,
                "topic": current_topic,
                "partition": partition,
                "offset": offset,
                "attempt": attempt,
                "domain": domain,
                "error": f"Authorization failure: Topic '{current_topic}' is not authorized",
                "error_type": "TopicAuthorizationFailedError",
                "error_classification": ErrorClassification.TERMINAL.value,
                "failed_at": now_iso,
                "payload": payload,
            }
            self.store_failed_event(fail_ctx)
            return FailedEventReceipt({
                "status": "FAILED",
                "consumer": self.CONSUMER_NAME,
                "event_id": event_id,
                "tenant_id": tenant_id,
                "correlation_id": correlation_id,
                "error": fail_ctx["error"],
                "error_type": fail_ctx["error_type"],
                "error_classification": fail_ctx["error_classification"],
                "retryable": False,
                "idempotent": False,
                "dlq": True,
                "failed_event_stored": True,
            })

        # 3. Schema & contract validation
        missing_fields = []
        if not payload.get("event_id") or not str(payload.get("event_id")).strip():
            missing_fields.append("event_id")
        if not payload.get("tenant_id") or not str(payload.get("tenant_id")).strip():
            missing_fields.append("tenant_id")
        if schema_version is None:
            missing_fields.append("schema_version")

        if missing_fields:
            self._metrics["errors_total"] += 1
            fail_ctx = {
                "event_id": event_id,
                "tenant_id": tenant_id,
                "correlation_id": correlation_id,
                "topic": current_topic,
                "partition": partition,
                "offset": offset,
                "attempt": attempt,
                "domain": domain,
                "error": f"Schema validation error: Missing required fields: {', '.join(sorted(missing_fields))}",
                "error_type": "ValidationError",
                "error_classification": ErrorClassification.TERMINAL.value,
                "failed_at": now_iso,
                "payload": payload,
            }
            self.store_failed_event(fail_ctx)
            return FailedEventReceipt({
                "status": "FAILED",
                "consumer": self.CONSUMER_NAME,
                "event_id": event_id,
                "tenant_id": tenant_id,
                "correlation_id": correlation_id,
                "error": fail_ctx["error"],
                "error_type": fail_ctx["error_type"],
                "error_classification": fail_ctx["error_classification"],
                "retryable": False,
                "idempotent": False,
                "dlq": True,
                "failed_event_stored": True,
            })

        # 4. Security & forbidden keys check
        found_forbidden = set()
        for k in payload.keys():
            k_lower = str(k).lower()
            if k_lower in _FORBIDDEN_KEYS or any(f in k_lower for f in ("password", "secret", "token", "api_key")):
                found_forbidden.add(k)

        if found_forbidden:
            self._metrics["errors_total"] += 1
            logger.warning("Event %s contains forbidden sensitive keys: %s", event_id, found_forbidden)
            fail_ctx = {
                "event_id": event_id,
                "tenant_id": tenant_id,
                "correlation_id": correlation_id,
                "topic": current_topic,
                "partition": partition,
                "offset": offset,
                "attempt": attempt,
                "domain": domain,
                "error": f"Security violation: Payload contains forbidden sensitive keys: {', '.join(sorted(found_forbidden))}",
                "error_type": "SecurityPolicyError",
                "error_classification": ErrorClassification.TERMINAL.value,
                "failed_at": now_iso,
                "payload": payload,
            }
            self.store_failed_event(fail_ctx)
            return FailedEventReceipt({
                "status": "FAILED",
                "consumer": self.CONSUMER_NAME,
                "event_id": event_id,
                "tenant_id": tenant_id,
                "correlation_id": correlation_id,
                "error": fail_ctx["error"],
                "error_type": fail_ctx["error_type"],
                "error_classification": fail_ctx["error_classification"],
                "retryable": False,
                "idempotent": False,
                "dlq": True,
                "failed_event_stored": True,
            })

        # 5. Execute Downstream Domain Business Logic
        effective_handler = handler or self.handler
        try:
            if effective_handler:
                import inspect
                if inspect.iscoroutinefunction(effective_handler):
                    handler_result = await effective_handler(payload)
                else:
                    handler_result = effective_handler(payload)

                if isinstance(handler_result, dict) and handler_result.get("status") == "FAILED":
                    err_msg = handler_result.get("error", "Downstream handler returned failure")
                    classification, is_retryable = classify_error(err_msg)
                    fail_ctx = {
                        "event_id": event_id,
                        "tenant_id": tenant_id,
                        "correlation_id": correlation_id,
                        "topic": current_topic,
                        "partition": partition,
                        "offset": offset,
                        "attempt": attempt,
                        "domain": domain,
                        "error": err_msg,
                        "error_type": handler_result.get("error_type", "HandlerError"),
                        "error_classification": classification,
                        "failed_at": now_iso,
                        "payload": payload,
                    }
                    self.store_failed_event(fail_ctx)
                    return FailedEventReceipt({
                        "status": "FAILED",
                        "consumer": self.CONSUMER_NAME,
                        "event_id": event_id,
                        "tenant_id": tenant_id,
                        "correlation_id": correlation_id,
                        "domain": domain,
                        "error": err_msg,
                        "error_type": fail_ctx["error_type"],
                        "error_classification": classification,
                        "retryable": is_retryable,
                        "idempotent": True,
                        "dlq": not is_retryable,
                        "failed_event_stored": True,
                    })

            self._metrics["processed_total"] += 1
            return FailedEventReceipt({
                "status": "PROCESSED",
                "consumer": self.CONSUMER_NAME,
                "event_id": event_id,
                "tenant_id": tenant_id,
                "correlation_id": correlation_id,
                "domain": domain,
                "idempotent": True,
                "idempotent_duplicate": False,
                "retries": 0,
                "dlq": False,
                "failed_event_stored": False,
            })

        except Exception as exec_err:
            self._metrics["errors_total"] += 1
            classification, is_retryable = classify_error(exec_err)
            fail_ctx = {
                "event_id": event_id,
                "tenant_id": tenant_id,
                "correlation_id": correlation_id,
                "topic": current_topic,
                "partition": partition,
                "offset": offset,
                "attempt": attempt,
                "domain": domain,
                "error": str(exec_err),
                "error_type": type(exec_err).__name__,
                "error_classification": classification,
                "failed_at": now_iso,
                "payload": payload,
            }
            self.store_failed_event(fail_ctx)

            return FailedEventReceipt({
                "status": "FAILED",
                "consumer": self.CONSUMER_NAME,
                "event_id": event_id,
                "tenant_id": tenant_id,
                "correlation_id": correlation_id,
                "domain": domain,
                "error": str(exec_err),
                "error_type": type(exec_err).__name__,
                "error_classification": classification,
                "retryable": is_retryable,
                "idempotent": True,
                "dlq": not is_retryable,
                "failed_event_stored": True,
            })

    # =========================================================================
    # Bounded Recovery & Replay Path
    # =========================================================================

    async def recover_event(
        self,
        event_or_payload: Any,
        topic: Optional[str] = None,
        partition: int = 0,
        offset: int = 0,
        retries_limit: Optional[int] = None,
        handler: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ) -> FailedEventReceipt:
        """
        Bounded recovery loop with failed event resolution on success.
        Conforms strictly to the required output contract:
        {
            "status": "RECOVERED",
            "event_id": "evt_01JEXAMPLE",
            "retries": 1,
            "idempotent": True,
            "dlq": False
        }
        """
        limit = retries_limit or self.max_retries
        retries_attempted = 0
        last_receipt = None

        while retries_attempted < limit:
            retries_attempted += 1
            receipt = await self.process_event(
                message=event_or_payload,
                topic=topic,
                partition=partition,
                offset=offset,
                attempt=retries_attempted,
                handler=handler,
            )
            last_receipt = receipt

            if receipt.get("status") == "PROCESSED":
                self._metrics["recovered_total"] += 1
                event_id = receipt.get("event_id") or "unknown"
                # Mark previously stored failure as resolved!
                self.mark_resolved(event_id, resolution_metadata={"recovered_at_attempt": retries_attempted})
                return FailedEventReceipt({
                    "status": "RECOVERED",
                    "consumer": self.CONSUMER_NAME,
                    "event_id": event_id,
                    "retries": retries_attempted,
                    "idempotent": True,
                    "dlq": False,
                })

            if not receipt.get("retryable", False):
                break

            if retries_attempted < limit:
                await asyncio.sleep(min(0.05 * (2 ** (retries_attempted - 1)), 1.0))

        # Exhausted failures
        event_id = (last_receipt or {}).get("event_id", "unknown")
        return FailedEventReceipt({
            "status": "FAILED",
            "consumer": self.CONSUMER_NAME,
            "event_id": event_id,
            "retries": retries_attempted,
            "idempotent": True,
            "dlq": True,
            "failed_event_stored": True,
            "error": (last_receipt or {}).get("error", "Failed event recovery exhausted"),
        })

    # =========================================================================
    # Observability & Metrics
    # =========================================================================

    @classmethod
    def get_storage_metrics(cls) -> Dict[str, Any]:
        """Return operational metrics for failed event storage."""
        return {
            "status": "healthy",
            "consumer": cls.CONSUMER_NAME,
            "metrics": dict(cls._metrics),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @classmethod
    def reset_metrics(cls) -> None:
        """Reset operational metrics."""
        cls._metrics = {
            "processed_total": 0,
            "failed_events_stored": 0,
            "failed_events_resolved": 0,
            "recovered_total": 0,
            "errors_total": 0,
            "by_classification": {
                "TERMINAL": 0,
                "RETRYABLE": 0,
            },
        }


# Authoritative aliases ensuring complete cross-story naming compatibility
AddFailedEventStorage = FailedEventStorage
Add_failed_event_storage = FailedEventStorage
ConsumerFailedEventStorage = FailedEventStorage
FailedEventStorageService = FailedEventStorage

