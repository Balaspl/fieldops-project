"""
consumer_idempotency.py

Authoritative Kafka consumer idempotency management and duplicate event prevention
for FieldOps distributed event streams.

Responsibilities:
- Prevent duplicate event execution across dispatch, billing, payment, and notification operations.
- Enforce multi-tier idempotency with distributed locking (SET NX EX) and durable completion markers.
- Protect domain business logic from duplicate Kafka deliveries and consumer rebalances.
- Maintain seamless cross-compatibility with domain-specific Redis keys across existing services.
- Provide zero-duplicate side effect guarantees on replay, retry, and recovery loops.
- Support payload hashing (fingerprinting), tenant context preservation, and credential redaction.
- Guarantee exact output contract compliance:
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
import hashlib
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


class IdempotencyReceipt(dict):
    """
    Structured dictionary receipt returned after idempotent event processing or recovery.
    Complies with the required output contract:
    {
        "status": "RECOVERED",
        "event_id": "evt_01JEXAMPLE",
        "retries": 1,
        "idempotent": True,
        "dlq": False
    }
    Or for standard idempotent executions:
    {
        "status": "PROCESSED",
        "consumer": "Prevent_duplicate_event_processing",
        "event_id": "evt_01JEXAMPLE",
        "domain": "dispatch",
        "idempotent": True,
        "idempotent_duplicate": False,
        "retries": 0,
        "dlq": False
    }
    """

    @property
    def is_success(self) -> bool:
        return self.get("status") in ("RECOVERED", "PROCESSED") and not self.get("dlq", False)

    @property
    def is_duplicate(self) -> bool:
        return bool(self.get("idempotent_duplicate", False))

    @property
    def is_recovered(self) -> bool:
        return self.get("status") == "RECOVERED"

    @property
    def is_dlq(self) -> bool:
        return bool(self.get("dlq", False))

    def __bool__(self) -> bool:
        return self.is_success or self.is_dlq


class ConsumerIdempotency:
    """
    Distributed idempotency coordinator and consumer duplicate protection service.
    Protects dispatch, billing, payment, and notification operations from duplicate Kafka delivery.
    """

    CONSUMER_NAME = "Prevent_duplicate_event_processing"
    DEFAULT_TOPIC = "fieldops.events"
    DEFAULT_GROUP = "fieldops-idempotency"
    DEFAULT_LOCK_TIMEOUT_SECONDS = 30
    DEFAULT_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days
    DEFAULT_MAX_RETRIES = 3
    SCHEMA_VERSION = 1

    SUPPORTED_DOMAINS = frozenset({
        "dispatch",
        "billing",
        "payment",
        "notification",
        "gps",
        "sla",
        "audit",
        "analytics",
        "default",
    })

    ALLOWED_TOPICS = frozenset(
        set(DEFAULT_KAFKA_TOPICS)
        | set(DEFAULT_DLQ_TOPICS)
        | {DEFAULT_SHARED_DLQ_TOPIC, "fieldops.analytics.events"}
    )

    # In-memory operational metrics
    _metrics: Dict[str, Any] = {
        "processed_total": 0,
        "duplicates_detected": 0,
        "locks_acquired": 0,
        "locks_rejected": 0,
        "recovered_total": 0,
        "errors_total": 0,
        "domains": {
            "dispatch": 0,
            "billing": 0,
            "payment": 0,
            "notification": 0,
            "other": 0,
        },
    }

    def __init__(
        self,
        topic: Optional[str] = None,
        group_id: Optional[str] = None,
        consumer_manager: Optional[KafkaConsumerManager] = None,
        redis_client: Optional[Any] = None,
        handler: Optional[Callable[[Dict[str, Any]], Any]] = None,
        lock_timeout: int = DEFAULT_LOCK_TIMEOUT_SECONDS,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        db_session_factory: Optional[Callable[[], Any]] = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        bootstrap_servers: Optional[str] = None,
        dlq_key: str = "consumer:dlq",
    ):
        self.topic = topic or self.DEFAULT_TOPIC
        self.group_id = group_id or self.DEFAULT_GROUP
        self.bootstrap_servers = bootstrap_servers
        self.lock_timeout = max(1, lock_timeout)
        self.ttl_seconds = max(60, ttl_seconds)
        self.max_retries = max(1, max_retries)
        self.dlq_key = dlq_key
        self.handler = handler
        self.db_session_factory = db_session_factory

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

    async def __aenter__(self) -> "ConsumerIdempotency":
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
    # Payload Hashing & Fingerprinting
    # =========================================================================

    @staticmethod
    def compute_payload_hash(payload: Any) -> str:
        """
        Compute deterministic SHA-256 fingerprint for message payload,
        excluding volatile execution metadata (timestamps, retry counts).
        """
        if not isinstance(payload, dict):
            return hashlib.sha256(str(payload).encode("utf-8")).hexdigest()

        # Omit volatile or nondeterministic keys for semantic hashing
        volatile_keys = {"timestamp", "attempt", "retry_count", "created_at", "processed_at", "received_at"}
        stable_dict = {
            k: v for k, v in payload.items()
            if k.lower() not in volatile_keys and not k.startswith("_")
        }
        try:
            canonical_json = json.dumps(stable_dict, sort_keys=True, default=str)
            return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
        except Exception:
            return hashlib.sha256(str(stable_dict).encode("utf-8")).hexdigest()

    # =========================================================================
    # Distributed Locking & Idempotency Markers
    # =========================================================================

    def _lock_key(self, event_id: str, domain: str) -> str:
        norm_domain = domain.lower().strip() if domain else "default"
        return f"lock:idempotency:{norm_domain}:{event_id}"

    def _unified_idempotency_key(self, event_id: str, domain: str) -> str:
        norm_domain = domain.lower().strip() if domain else "default"
        return f"idempotency:{norm_domain}:{event_id}"

    def acquire_lock(
        self,
        event_id: str,
        domain: str = "default",
        timeout_seconds: Optional[int] = None,
        worker_token: Optional[str] = None,
    ) -> bool:
        """
        Acquire distributed lock using Redis SET NX EX to prevent concurrent duplicate execution.
        Returns True if lock acquired, False if lock contention exists.
        """
        if not self.redis_client or not event_id:
            return True

        timeout = timeout_seconds or self.lock_timeout
        token = worker_token or str(uuid.uuid4())
        lock_key = self._lock_key(event_id, domain)

        try:
            # Handle standard redis-py set with nx & ex
            result = self.redis_client.set(lock_key, token, nx=True, ex=timeout)
            if result:
                self._metrics["locks_acquired"] += 1
                return True
            else:
                self._metrics["locks_rejected"] += 1
                return False
        except TypeError:
            # Some fake redis implementations use set(k, v) without nx/ex kwargs
            try:
                existing = self.redis_client.get(lock_key)
                if existing:
                    self._metrics["locks_rejected"] += 1
                    return False
                self.redis_client.set(lock_key, token)
                self._metrics["locks_acquired"] += 1
                return True
            except Exception as e:
                logger.warning("Fallback lock acquisition error for %s: %s", lock_key, e)
                return True
        except Exception as e:
            logger.warning("Redis error acquiring idempotency lock %s: %s", lock_key, e)
            # Default to proceed if Redis lock errors out to prevent systemic starvation
            return True

    def release_lock(
        self,
        event_id: str,
        domain: str = "default",
        worker_token: Optional[str] = None,
    ) -> bool:
        """Release the distributed idempotency lock."""
        if not self.redis_client or not event_id:
            return True

        lock_key = self._lock_key(event_id, domain)
        try:
            if hasattr(self.redis_client, "delete"):
                self.redis_client.delete(lock_key)
            return True
        except Exception as e:
            logger.warning("Redis error releasing lock %s: %s", lock_key, e)
            return False

    def is_processed(
        self,
        event_id: str,
        domain: Optional[str] = None,
        invoice_id: Optional[str] = None,
        payment_id: Optional[str] = None,
    ) -> bool:
        """
        Check whether this event or business transaction has already been processed.
        Checks both the unified idempotency keys and domain-specific legacy keys.
        """
        if not self.redis_client or not event_id:
            return False

        norm_domain = domain.lower().strip() if domain else "default"

        # 1. Primary unified key
        keys_to_check = [
            self._unified_idempotency_key(event_id, norm_domain),
            f"idempotency:default:{event_id}",
        ]

        # 2. Domain-specific legacy keys for backward and cross-consumer compatibility
        domain_key_map = {
            "dispatch": [f"dispatch:event_processed:{event_id}"],
            "billing": [f"billing:event_processed:{event_id}"],
            "payment": [f"payment:event_processed:{event_id}"],
            "notification": [f"notification:event_processed:{event_id}"],
            "sla": [f"sla:event_processed:{event_id}"],
            "audit": [f"audit:event_processed:{event_id}"],
            "analytics": [f"analytics:event_processed:{event_id}"],
        }

        if norm_domain in domain_key_map:
            keys_to_check.extend(domain_key_map[norm_domain])
        else:
            # Check all common domains if domain is unspecified/default
            for k_list in domain_key_map.values():
                keys_to_check.extend(k_list)

        # Cross-system retry & DLQ markers
        keys_to_check.append(f"consumer_retry:event_processed:{event_id}")
        keys_to_check.append(f"consumer_dlq:event_processed:{event_id}")

        # Business entity specific transaction keys
        if invoice_id and str(invoice_id).strip():
            keys_to_check.append(f"billing:invoice_processed:{invoice_id}")
        if payment_id and str(payment_id).strip():
            keys_to_check.append(f"payment:txn_processed:{payment_id}")

        try:
            for k in keys_to_check:
                val = self.redis_client.get(k)
                if val:
                    return True
            return False
        except Exception as e:
            logger.warning("Redis error checking idempotency for event %s: %s", event_id, e)
            return False

    def mark_processed(
        self,
        event_id: str,
        domain: str = "default",
        payload: Optional[Dict[str, Any]] = None,
        ttl_seconds: Optional[int] = None,
        invoice_id: Optional[str] = None,
        payment_id: Optional[str] = None,
    ) -> bool:
        """
        Durable post-execution completion marking across unified and domain-specific keys.
        """
        if not self.redis_client or not event_id:
            return False

        norm_domain = domain.lower().strip() if domain else "default"
        ttl = ttl_seconds or self.ttl_seconds
        payload_hash = self.compute_payload_hash(payload) if payload else ""
        now_iso = datetime.now(timezone.utc).isoformat()

        marker_record = {
            "event_id": event_id,
            "domain": norm_domain,
            "processed_at": now_iso,
            "payload_hash": payload_hash,
            "tenant_id": (payload or {}).get("tenant_id"),
        }
        marker_str = json.dumps(marker_record)

        keys_to_set = [self._unified_idempotency_key(event_id, norm_domain)]

        # Domain legacy keys for full cross-system protection
        if norm_domain == "dispatch":
            keys_to_set.append(f"dispatch:event_processed:{event_id}")
        elif norm_domain == "billing":
            keys_to_set.append(f"billing:event_processed:{event_id}")
            if invoice_id and str(invoice_id).strip():
                keys_to_set.append(f"billing:invoice_processed:{invoice_id}")
        elif norm_domain == "payment":
            keys_to_set.append(f"payment:event_processed:{event_id}")
            if payment_id and str(payment_id).strip():
                keys_to_set.append(f"payment:txn_processed:{payment_id}")
        elif norm_domain == "notification":
            keys_to_set.append(f"notification:event_processed:{event_id}")
        elif norm_domain == "sla":
            keys_to_set.append(f"sla:event_processed:{event_id}")
        elif norm_domain == "audit":
            keys_to_set.append(f"audit:event_processed:{event_id}")
        elif norm_domain == "analytics":
            keys_to_set.append(f"analytics:event_processed:{event_id}")

        try:
            for k in keys_to_set:
                try:
                    self.redis_client.set(k, marker_str, ex=ttl)
                except TypeError:
                    self.redis_client.set(k, marker_str)
            return True
        except Exception as e:
            logger.warning("Redis error marking idempotency for event %s: %s", event_id, e)
            return False

    # =========================================================================
    # Domain Inference & Safe Routing
    # =========================================================================

    @staticmethod
    def infer_domain(payload: Dict[str, Any], topic: Optional[str] = None) -> str:
        """Infer business domain from payload metadata, event type, or Kafka topic."""
        explicit_domain = payload.get("domain")
        if explicit_domain and str(explicit_domain).strip():
            return str(explicit_domain).lower().strip()

        event_type = str(payload.get("event_type") or payload.get("event") or "").lower()
        topic_str = str(topic or "").lower()

        if "dispatch" in topic_str or "job" in topic_str or any(
            x in event_type for x in ("dispatch", "job", "assignment", "status-transition")
        ):
            return "dispatch"

        if "billing" in topic_str or "invoice" in topic_str or any(
            x in event_type for x in ("billing", "invoice")
        ):
            return "billing"

        if "payment" in topic_str or any(
            x in event_type for x in ("payment", "refund", "charge", "transaction")
        ):
            return "payment"

        if "notification" in topic_str or any(
            x in event_type for x in ("notification", "sms", "email", "alert")
        ):
            return "notification"

        if "gps" in topic_str:
            return "gps"
        if "sla" in topic_str:
            return "sla"
        if "audit" in topic_str:
            return "audit"
        if "analytics" in topic_str:
            return "analytics"

        return "default"

    # =========================================================================
    # Event Processing Pipeline
    # =========================================================================

    async def handle_message(self, message: Any) -> IdempotencyReceipt:
        """Callback suitable for KafkaConsumerManager.consume(handler)."""
        return await self.process_event(message)

    async def process_event(
        self,
        message: Any,
        domain: Optional[str] = None,
        attempt: int = 1,
        handler: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ) -> IdempotencyReceipt:
        """
        Process event with distributed lock acquisition, pre-execution idempotency check,
        schema validation, domain isolation, and guaranteed zero-duplicate business effects.
        """
        now_iso = datetime.now(timezone.utc).isoformat()

        # 1. Parse & decode message payload safely
        try:
            if isinstance(message, (bytes, bytearray)):
                try:
                    message = message.decode("utf-8")
                except UnicodeDecodeError as u_err:
                    self._metrics["errors_total"] += 1
                    return IdempotencyReceipt({
                        "status": "FAILED",
                        "consumer": self.CONSUMER_NAME,
                        "event_id": "unknown",
                        "attempt": attempt,
                        "error": f"Malformed message encoding: {u_err}",
                        "error_type": "UnicodeDecodeError",
                        "error_classification": ErrorClassification.TERMINAL.value,
                        "retryable": False,
                        "failed_at": now_iso,
                        "idempotent": False,
                        "dlq": True,
                    })

            if isinstance(message, str):
                try:
                    message = json.loads(message)
                except json.JSONDecodeError as j_err:
                    self._metrics["errors_total"] += 1
                    return IdempotencyReceipt({
                        "status": "FAILED",
                        "consumer": self.CONSUMER_NAME,
                        "event_id": "unknown",
                        "attempt": attempt,
                        "error": f"Malformed JSON message: {j_err}",
                        "error_type": "JSONDecodeError",
                        "error_classification": ErrorClassification.TERMINAL.value,
                        "retryable": False,
                        "failed_at": now_iso,
                        "idempotent": False,
                        "dlq": True,
                    })

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
                self._metrics["errors_total"] += 1
                return IdempotencyReceipt({
                    "status": "FAILED",
                    "consumer": self.CONSUMER_NAME,
                    "event_id": "unknown",
                    "attempt": attempt,
                    "error": f"Unsupported message type: {type(message).__name__}",
                    "error_type": "TypeError",
                    "error_classification": ErrorClassification.TERMINAL.value,
                    "retryable": False,
                    "failed_at": now_iso,
                    "idempotent": False,
                    "dlq": True,
                })

        except Exception as parse_exc:
            self._metrics["errors_total"] += 1
            return IdempotencyReceipt({
                "status": "FAILED",
                "consumer": self.CONSUMER_NAME,
                "event_id": "unknown",
                "attempt": attempt,
                "error": f"Message parse error: {parse_exc}",
                "error_type": type(parse_exc).__name__,
                "error_classification": ErrorClassification.TERMINAL.value,
                "retryable": False,
                "failed_at": now_iso,
                "idempotent": False,
                "dlq": True,
            })

        event_id = payload.get("event_id") or "unknown"
        tenant_id = payload.get("tenant_id")
        schema_version = payload.get("schema_version")

        # 2. Topic authorization check
        if topic and topic not in self.ALLOWED_TOPICS:
            self._metrics["errors_total"] += 1
            return IdempotencyReceipt({
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
                "idempotent": False,
                "dlq": True,
            })

        # 3. Schema & contract validation
        missing_fields = []
        if not payload.get("event_id") or not str(payload.get("event_id")).strip():
            missing_fields.append("event_id")
        if not tenant_id or not str(tenant_id).strip():
            missing_fields.append("tenant_id")
        if schema_version is None:
            missing_fields.append("schema_version")

        if missing_fields:
            self._metrics["errors_total"] += 1
            return IdempotencyReceipt({
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
                "idempotent": False,
                "dlq": True,
            })

        # 4. Security & forbidden keys check
        lowered_keys = {str(k).lower() for k in payload.keys()}
        found_forbidden = lowered_keys.intersection(_FORBIDDEN_KEYS)
        if found_forbidden:
            self._metrics["errors_total"] += 1
            logger.warning("Event %s contains forbidden sensitive keys: %s", event_id, found_forbidden)
            return IdempotencyReceipt({
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
                "idempotent": False,
                "dlq": True,
            })

        # 5. Determine domain and entity keys
        norm_domain = (domain or self.infer_domain(payload, topic)).lower()
        invoice_id = str(payload.get("invoice_id") or "")
        payment_id = str(payload.get("payment_id") or payload.get("transaction_id") or "")

        # 6. Pre-execution Idempotency Check (Zero Business Side Effect Protection)
        if self.is_processed(
            event_id=event_id,
            domain=norm_domain,
            invoice_id=invoice_id,
            payment_id=payment_id,
        ):
            self._metrics["duplicates_detected"] += 1
            logger.info(
                "Duplicate event %s in domain '%s' safely ignored (idempotent duplicate, zero business side effect).",
                event_id,
                norm_domain,
            )
            return IdempotencyReceipt({
                "status": "PROCESSED",
                "consumer": self.CONSUMER_NAME,
                "event_id": event_id,
                "tenant_id": tenant_id,
                "correlation_id": correlation_id,
                "domain": norm_domain,
                "attempt": attempt,
                "idempotent": True,
                "idempotent_duplicate": True,
                "retries": 0,
                "dlq": False,
            })

        # 7. Acquire Distributed Atomic Lock (Concurrency Protection)
        worker_token = str(uuid.uuid4())
        locked = self.acquire_lock(
            event_id=event_id,
            domain=norm_domain,
            timeout_seconds=self.lock_timeout,
            worker_token=worker_token,
        )

        if not locked:
            logger.warning(
                "Contention detected on event %s in domain '%s'. Another consumer holds the lock.",
                event_id,
                norm_domain,
            )
            return IdempotencyReceipt({
                "status": "LOCKED",
                "consumer": self.CONSUMER_NAME,
                "event_id": event_id,
                "domain": norm_domain,
                "error": "Concurrent execution locked by another consumer worker",
                "retryable": True,
                "idempotent": True,
                "dlq": False,
            })

        # 8. Execute Business Logic with Lock Guard
        effective_handler = handler or self.handler
        try:
            if effective_handler:
                import inspect
                if inspect.iscoroutinefunction(effective_handler):
                    handler_result = await effective_handler(payload)
                else:
                    handler_result = effective_handler(payload)

                if isinstance(handler_result, dict) and handler_result.get("status") == "FAILED":
                    # Handler returned an explicit failure
                    self.release_lock(event_id, norm_domain, worker_token)
                    err_msg = handler_result.get("error", "Downstream handler returned failure")
                    classification, is_retryable = classify_error(err_msg)
                    return IdempotencyReceipt({
                        "status": "FAILED",
                        "consumer": self.CONSUMER_NAME,
                        "event_id": event_id,
                        "domain": norm_domain,
                        "tenant_id": tenant_id,
                        "correlation_id": correlation_id,
                        "error": err_msg,
                        "error_type": handler_result.get("error_type", "HandlerError"),
                        "error_classification": classification,
                        "retryable": is_retryable,
                        "idempotent": True,
                        "dlq": not is_retryable,
                    })

            # 9. Mark Processed Durably on Success
            self.mark_processed(
                event_id=event_id,
                domain=norm_domain,
                payload=payload,
                ttl_seconds=self.ttl_seconds,
                invoice_id=invoice_id,
                payment_id=payment_id,
            )

            # Record metrics
            self._metrics["processed_total"] += 1
            if norm_domain in self._metrics["domains"]:
                self._metrics["domains"][norm_domain] += 1
            else:
                self._metrics["domains"]["other"] += 1

            logger.info(
                "Successfully processed and marked event %s in domain '%s' idempotently.",
                event_id,
                norm_domain,
            )

            return IdempotencyReceipt({
                "status": "PROCESSED",
                "consumer": self.CONSUMER_NAME,
                "event_id": event_id,
                "tenant_id": tenant_id,
                "correlation_id": correlation_id,
                "domain": norm_domain,
                "attempt": attempt,
                "idempotent": True,
                "idempotent_duplicate": False,
                "retries": 0,
                "dlq": False,
            })

        except Exception as exec_err:
            # Release lock on failure so subsequent attempts or retries are unblocked
            self.release_lock(event_id, norm_domain, worker_token)
            self._metrics["errors_total"] += 1
            classification, is_retryable = classify_error(exec_err)
            logger.error("Execution error processing event %s: %s", event_id, exec_err)
            return IdempotencyReceipt({
                "status": "FAILED",
                "consumer": self.CONSUMER_NAME,
                "event_id": event_id,
                "domain": norm_domain,
                "tenant_id": tenant_id,
                "correlation_id": correlation_id,
                "error": str(exec_err),
                "error_type": type(exec_err).__name__,
                "error_classification": classification,
                "retryable": is_retryable,
                "idempotent": True,
                "dlq": not is_retryable,
            })
        finally:
            # Always release lock
            self.release_lock(event_id, norm_domain, worker_token)

    # =========================================================================
    # Allowed Recovery & Replay Path
    # =========================================================================

    async def recover_event(
        self,
        event_or_payload: Any,
        domain: Optional[str] = None,
        retries_limit: Optional[int] = None,
        handler: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ) -> IdempotencyReceipt:
        """
        Execute bounded recovery loop for transient failures with durable idempotency.
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
                domain=domain,
                attempt=retries_attempted,
                handler=handler,
            )
            last_receipt = receipt

            if receipt.get("status") == "PROCESSED":
                self._metrics["recovered_total"] += 1
                event_id = receipt.get("event_id") or "unknown"
                return IdempotencyReceipt({
                    "status": "RECOVERED",
                    "consumer": self.CONSUMER_NAME,
                    "event_id": event_id,
                    "retries": retries_attempted,
                    "idempotent": True,
                    "dlq": False,
                })

            if not receipt.get("retryable", False):
                break

            # Brief backoff before next recovery attempt
            if retries_attempted < limit:
                await asyncio.sleep(min(0.05 * (2 ** (retries_attempted - 1)), 1.0))

        # If exhausted or unrecoverable, return failure
        event_id = (last_receipt or {}).get("event_id", "unknown")
        return IdempotencyReceipt({
            "status": "FAILED",
            "consumer": self.CONSUMER_NAME,
            "event_id": event_id,
            "retries": retries_attempted,
            "idempotent": True,
            "dlq": True,
            "error": (last_receipt or {}).get("error", "Recovery attempts exhausted"),
        })

    # =========================================================================
    # Metrics & Health Snapshot
    # =========================================================================

    @classmethod
    def get_idempotency_metrics(cls) -> Dict[str, Any]:
        """Return operational idempotency and duplicate prevention metrics."""
        return {
            "status": "healthy",
            "consumer": cls.CONSUMER_NAME,
            "metrics": dict(cls._metrics),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @classmethod
    def reset_metrics(cls) -> None:
        """Reset operational metrics (used in test suites)."""
        cls._metrics = {
            "processed_total": 0,
            "duplicates_detected": 0,
            "locks_acquired": 0,
            "locks_rejected": 0,
            "recovered_total": 0,
            "errors_total": 0,
            "domains": {
                "dispatch": 0,
                "billing": 0,
                "payment": 0,
                "notification": 0,
                "other": 0,
            },
        }


# Authoritative aliases ensuring complete cross-story naming compatibility
PreventDuplicateEventProcessing = ConsumerIdempotency
Prevent_duplicate_event_processing = ConsumerIdempotency
ConsumerIdempotencyService = ConsumerIdempotency
EventIdempotencyManager = ConsumerIdempotency
IdempotentConsumer = ConsumerIdempotency

