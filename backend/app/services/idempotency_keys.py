"""
idempotency_keys.py

Authoritative Kafka idempotency keys management and deterministic duplicate
prevention across producer and consumer boundaries for FieldOps distributed events.

Responsibilities:
- Define and propagate stable idempotency keys across producer and consumer boundaries.
- Give every business-significant event a deterministic duplicate-prevention mechanism.
- Enforce consistent aggregate-based key derivation (domain, tenant, aggregate ID, action/qualifier).
- Coordinate multi-tier key verification with Redis distributed locking (SET NX EX) and durable completion markers.
- Protect domain business logic from duplicate execution during retries, rebalances, and replays.
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
from app.services.event_publisher import generate_idempotency_key

logger = logging.getLogger(__name__)


class IdempotencyKeyReceipt(dict):
    """
    Structured dictionary receipt returned after idempotency-key checked event processing or recovery.
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


class ConsumerIdempotencyKeys:
    """
    Distributed idempotency key coordinator and consumer duplicate protection service.
    Defines, persists, and validates deterministic idempotency keys across producer and consumer boundaries.
    """

    CONSUMER_NAME = "Add_idempotency_keys"
    DEFAULT_TOPIC = "fieldops.events"
    DEFAULT_GROUP = "fieldops-idempotency-keys"
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
        "keys_generated": 0,
        "keys_checked": 0,
        "duplicates_prevented": 0,
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
        max_retries: int = DEFAULT_MAX_RETRIES,
        bootstrap_servers: Optional[str] = None,
    ):
        self.topic = topic or self.DEFAULT_TOPIC
        self.group_id = group_id or self.DEFAULT_GROUP
        self.bootstrap_servers = bootstrap_servers
        self.lock_timeout = max(5, lock_timeout)
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

    async def __aenter__(self) -> "ConsumerIdempotencyKeys":
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
    # Idempotency Key Generation & Extraction
    # =========================================================================

    @staticmethod
    def derive_idempotency_key(
        payload: Dict[str, Any],
        headers: Optional[Dict[str, Any]] = None,
        domain: Optional[str] = None,
    ) -> str:
        """
        Deterministically derive or extract a stable idempotency key across producer/consumer boundaries.
        Priority:
        1. Explicit header 'idempotency_key' / 'x-idempotency-key'
        2. Explicit payload 'idempotency_key'
        3. Stable 'event_id'
        4. Deterministic aggregate computation (domain + tenant + aggregate ID)
        5. Payload SHA256 fingerprint fallback
        """
        # 1. Headers check
        if headers:
            for k in ("idempotency_key", "idempotency-key", "x-idempotency-key", "Idempotency-Key"):
                if k in headers and headers[k]:
                    val = headers[k]
                    if isinstance(val, (bytes, bytearray)):
                        val = val.decode("utf-8")
                    return str(val).strip()

        # 2. Payload explicit key
        if payload.get("idempotency_key"):
            return str(payload["idempotency_key"]).strip()

        # 3. Stable event_id
        if payload.get("event_id"):
            return str(payload["event_id"]).strip()

        # 4. Deterministic aggregate derivation
        tenant_id = str(payload.get("tenant_id") or "default").strip()
        event_type = str(payload.get("event_type") or payload.get("event") or "event").strip().lower()
        effective_domain = (domain or payload.get("domain") or "default").lower().strip()

        # Check domain aggregate IDs
        aggregate_id = None
        for id_field in ("job_id", "invoice_id", "payment_id", "technician_id", "user_id"):
            if payload.get(id_field):
                aggregate_id = str(payload[id_field]).strip()
                break

        if aggregate_id:
            qualifier = payload.get("new_status") or payload.get("status")
            return generate_idempotency_key(
                domain=effective_domain,
                tenant_id=tenant_id,
                aggregate_id=aggregate_id,
                event_type=event_type,
                qualifier=str(qualifier) if qualifier else None,
            )

        # 5. Deterministic payload hashing fallback
        payload_copy = {k: v for k, v in payload.items() if k not in ("timestamp", "created_at")}
        serialized = json.dumps(payload_copy, sort_keys=True, default=str)
        digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
        return f"idem:{effective_domain}:{tenant_id}:{digest}"

    # =========================================================================
    # Distributed Locking & Key Persistence (Redis)
    # =========================================================================

    def _lock_key(self, idempotency_key: str, domain: str) -> str:
        norm_domain = domain.lower().strip() if domain else "default"
        return f"lock:idempotency_key:{norm_domain}:{idempotency_key}"

    def _completed_key(self, idempotency_key: str, domain: str) -> str:
        norm_domain = domain.lower().strip() if domain else "default"
        return f"idempotency_key:completed:{norm_domain}:{idempotency_key}"

    def acquire_lock(
        self,
        idempotency_key: str,
        domain: str = "default",
        timeout_seconds: Optional[int] = None,
        worker_token: Optional[str] = None,
    ) -> bool:
        """
        Acquire distributed lock using Redis SET NX EX to prevent concurrent duplicate execution.
        """
        if not self.redis_client or not idempotency_key:
            return True

        timeout = timeout_seconds or self.lock_timeout
        token = worker_token or str(uuid.uuid4())
        lock_key = self._lock_key(idempotency_key, domain)

        try:
            result = self.redis_client.set(lock_key, token, nx=True, ex=timeout)
            if result:
                self._metrics["locks_acquired"] += 1
                return True
            else:
                self._metrics["locks_rejected"] += 1
                return False
        except TypeError:
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
            logger.warning("Redis error acquiring lock %s: %s", lock_key, e)
            return True

    def release_lock(
        self,
        idempotency_key: str,
        domain: str = "default",
    ) -> bool:
        """Release the distributed idempotency lock."""
        if not self.redis_client or not idempotency_key:
            return True

        lock_key = self._lock_key(idempotency_key, domain)
        try:
            if hasattr(self.redis_client, "delete"):
                self.redis_client.delete(lock_key)
            return True
        except Exception as e:
            logger.warning("Redis error releasing lock %s: %s", lock_key, e)
            return False

    def is_processed(
        self,
        idempotency_key: str,
        domain: Optional[str] = None,
        event_id: Optional[str] = None,
    ) -> bool:
        """
        Check whether this idempotency key has already been completed.
        Checks both the primary idempotency-keys keys and Story 7.10 / legacy domain keys.
        """
        if not self.redis_client or not idempotency_key:
            return False

        norm_domain = domain.lower().strip() if domain else "default"
        self._metrics["keys_checked"] += 1

        keys_to_check = [
            self._completed_key(idempotency_key, norm_domain),
            f"idempotency_key:completed:default:{idempotency_key}",
            f"idempotency:{norm_domain}:{idempotency_key}",
            f"idempotency:default:{idempotency_key}",
        ]

        # Check event_id variants if different from idempotency_key
        if event_id and event_id != idempotency_key:
            keys_to_check.append(self._completed_key(event_id, norm_domain))
            keys_to_check.append(f"idempotency:{norm_domain}:{event_id}")

        # Domain-specific legacy keys for backward and cross-consumer compatibility
        domain_key_map = {
            "dispatch": [f"dispatch:event_processed:{idempotency_key}"],
            "billing": [f"billing:event_processed:{idempotency_key}"],
            "payment": [f"payment:event_processed:{idempotency_key}"],
            "notification": [f"notification:event_processed:{idempotency_key}"],
            "sla": [f"sla:event_processed:{idempotency_key}"],
            "audit": [f"audit:event_processed:{idempotency_key}"],
            "analytics": [f"analytics:event_processed:{idempotency_key}"],
        }

        if norm_domain in domain_key_map:
            keys_to_check.extend(domain_key_map[norm_domain])
        else:
            for k_list in domain_key_map.values():
                keys_to_check.extend(k_list)

        try:
            for k in keys_to_check:
                val = self.redis_client.get(k)
                if val:
                    return True
            return False
        except Exception as e:
            logger.warning("Redis error checking idempotency key %s: %s", idempotency_key, e)
            return False

    def mark_processed(
        self,
        idempotency_key: str,
        domain: str = "default",
        event_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Record durable completion marker for this idempotency key in Redis.
        Ensures cross-compatibility with Story 7.10 idempotency keys.
        """
        if not self.redis_client or not idempotency_key:
            return True

        norm_domain = domain.lower().strip() if domain else "default"
        payload_record = {
            "idempotency_key": idempotency_key,
            "event_id": event_id or idempotency_key,
            "domain": norm_domain,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        if metadata:
            payload_record["metadata"] = metadata

        try:
            val_str = json.dumps(payload_record)
            # 1. Primary completed key
            self.redis_client.set(self._completed_key(idempotency_key, norm_domain), val_str, ex=self.ttl_seconds)
            # 2. Cross-compatible unified key for Story 7.10
            self.redis_client.set(f"idempotency:{norm_domain}:{idempotency_key}", val_str, ex=self.ttl_seconds)

            if event_id and event_id != idempotency_key:
                self.redis_client.set(self._completed_key(event_id, norm_domain), val_str, ex=self.ttl_seconds)
                self.redis_client.set(f"idempotency:{norm_domain}:{event_id}", val_str, ex=self.ttl_seconds)

            logger.info("Persisted idempotency key %s (domain: %s)", idempotency_key, norm_domain)
            return True
        except Exception as e:
            logger.warning("Redis error persisting idempotency key %s: %s", idempotency_key, e)
            return False

    # =========================================================================
    # Event Processing with Idempotency Key Validation
    # =========================================================================

    async def handle_message(self, message: Any) -> IdempotencyKeyReceipt:
        """Callback suitable for KafkaConsumerManager.consume(handler)."""
        topic = getattr(message, "topic", self.topic)
        val = getattr(message, "value", message)
        headers = dict(getattr(message, "headers", [])) if hasattr(message, "headers") else None
        return await self.process_event(val, topic=topic, headers=headers)

    async def process_event(
        self,
        message: Any,
        topic: Optional[str] = None,
        headers: Optional[Dict[str, Any]] = None,
        attempt: int = 1,
        handler: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ) -> IdempotencyKeyReceipt:
        """
        Process event with strict idempotency key check.
        Bypasses business side effects on duplicate deliveries.
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
                    return IdempotencyKeyReceipt({
                        "status": "FAILED",
                        "consumer": self.CONSUMER_NAME,
                        "event_id": "unknown",
                        "error": f"Malformed message encoding: {u_err}",
                        "error_type": "UnicodeDecodeError",
                        "error_classification": ErrorClassification.TERMINAL.value,
                        "retryable": False,
                        "idempotent": False,
                        "dlq": True,
                    })

            if isinstance(message, str):
                try:
                    message = json.loads(message)
                except json.JSONDecodeError as j_err:
                    self._metrics["errors_total"] += 1
                    return IdempotencyKeyReceipt({
                        "status": "FAILED",
                        "consumer": self.CONSUMER_NAME,
                        "event_id": "unknown",
                        "error": f"Malformed JSON message: {j_err}",
                        "error_type": "JSONDecodeError",
                        "error_classification": ErrorClassification.TERMINAL.value,
                        "retryable": False,
                        "idempotent": False,
                        "dlq": True,
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
                return IdempotencyKeyReceipt({
                    "status": "FAILED",
                    "consumer": self.CONSUMER_NAME,
                    "event_id": "unknown",
                    "error": f"Unsupported message type: {type(message).__name__}",
                    "error_type": "TypeError",
                    "error_classification": ErrorClassification.TERMINAL.value,
                    "retryable": False,
                    "idempotent": False,
                    "dlq": True,
                })

        except Exception as parse_exc:
            self._metrics["errors_total"] += 1
            return IdempotencyKeyReceipt({
                "status": "FAILED",
                "consumer": self.CONSUMER_NAME,
                "event_id": "unknown",
                "error": f"Message parse error: {parse_exc}",
                "error_type": type(parse_exc).__name__,
                "idempotent": False,
                "dlq": True,
            })

        event_id = payload.get("event_id") or "unknown"
        tenant_id = payload.get("tenant_id")
        schema_version = payload.get("schema_version")
        domain = payload.get("domain") or "default"

        # 2. Topic authorization check
        if current_topic and current_topic not in self.ALLOWED_TOPICS:
            self._metrics["errors_total"] += 1
            return IdempotencyKeyReceipt({
                "status": "FAILED",
                "consumer": self.CONSUMER_NAME,
                "event_id": event_id,
                "tenant_id": tenant_id,
                "correlation_id": correlation_id,
                "error": f"Authorization failure: Topic '{current_topic}' is not authorized",
                "error_type": "TopicAuthorizationFailedError",
                "error_classification": ErrorClassification.TERMINAL.value,
                "retryable": False,
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
            return IdempotencyKeyReceipt({
                "status": "FAILED",
                "consumer": self.CONSUMER_NAME,
                "event_id": event_id,
                "tenant_id": tenant_id,
                "correlation_id": correlation_id,
                "error": f"Schema validation error: Missing required fields: {', '.join(sorted(missing_fields))}",
                "error_type": "ValidationError",
                "error_classification": ErrorClassification.TERMINAL.value,
                "retryable": False,
                "idempotent": False,
                "dlq": True,
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
            return IdempotencyKeyReceipt({
                "status": "FAILED",
                "consumer": self.CONSUMER_NAME,
                "event_id": event_id,
                "tenant_id": tenant_id,
                "correlation_id": correlation_id,
                "error": f"Security violation: Payload contains forbidden sensitive keys: {', '.join(sorted(found_forbidden))}",
                "error_type": "SecurityPolicyError",
                "error_classification": ErrorClassification.TERMINAL.value,
                "retryable": False,
                "idempotent": False,
                "dlq": True,
            })

        # 5. Deterministic Idempotency Key Resolution
        idempotency_key = self.derive_idempotency_key(payload, headers=headers, domain=domain)
        self._metrics["keys_generated"] += 1

        # 6. Check if idempotency key was ALREADY PROCESSED (Duplicate Detection)
        if self.is_processed(idempotency_key, domain=domain, event_id=event_id):
            self._metrics["duplicates_prevented"] += 1
            logger.info(
                "Duplicate event detected via idempotency key: %s (domain: %s). Bypassing domain execution.",
                idempotency_key,
                domain,
            )
            return IdempotencyKeyReceipt({
                "status": "PROCESSED",
                "consumer": self.CONSUMER_NAME,
                "event_id": event_id,
                "idempotency_key": idempotency_key,
                "tenant_id": tenant_id,
                "correlation_id": correlation_id,
                "domain": domain,
                "idempotent": True,
                "idempotent_duplicate": True,
                "retries": 0,
                "dlq": False,
            })

        # 7. Acquire Distributed Lock against Concurrent In-Flight Execution
        lock_acquired = self.acquire_lock(idempotency_key, domain=domain)
        if not lock_acquired:
            self._metrics["locks_rejected"] += 1
            logger.warning(
                "Concurrent duplicate execution prevented by lock contention on key %s. Skipping duplicate side effect.",
                idempotency_key,
            )
            return IdempotencyKeyReceipt({
                "status": "PROCESSED",
                "consumer": self.CONSUMER_NAME,
                "event_id": event_id,
                "idempotency_key": idempotency_key,
                "tenant_id": tenant_id,
                "correlation_id": correlation_id,
                "domain": domain,
                "idempotent": True,
                "idempotent_duplicate": True,
                "retries": 0,
                "dlq": False,
            })

        # 8. Execute Downstream Domain Business Logic
        effective_handler = handler or self.handler
        try:
            if effective_handler:
                import inspect
                if inspect.iscoroutinefunction(effective_handler):
                    handler_result = await effective_handler(payload)
                else:
                    handler_result = effective_handler(payload)

                if isinstance(handler_result, dict) and handler_result.get("status") == "FAILED":
                    self.release_lock(idempotency_key, domain=domain)
                    err_msg = handler_result.get("error", "Downstream handler returned failure")
                    classification, is_retryable = classify_error(err_msg)
                    return IdempotencyKeyReceipt({
                        "status": "FAILED",
                        "consumer": self.CONSUMER_NAME,
                        "event_id": event_id,
                        "idempotency_key": idempotency_key,
                        "tenant_id": tenant_id,
                        "correlation_id": correlation_id,
                        "domain": domain,
                        "error": err_msg,
                        "error_type": handler_result.get("error_type", "HandlerError"),
                        "error_classification": classification,
                        "retryable": is_retryable,
                        "idempotent": True,
                        "dlq": not is_retryable,
                    })

            # 9. PRIMARY SUCCESS PATH: Persist Idempotency Key & Release Lock
            self.mark_processed(
                idempotency_key=idempotency_key,
                domain=domain,
                event_id=event_id,
                metadata={"tenant_id": tenant_id, "correlation_id": correlation_id},
            )
            self.release_lock(idempotency_key, domain=domain)

            # Record domain metrics
            norm_dom = domain if domain in self._metrics["domains"] else "other"
            self._metrics["domains"][norm_dom] += 1
            self._metrics["processed_total"] += 1

            return IdempotencyKeyReceipt({
                "status": "PROCESSED",
                "consumer": self.CONSUMER_NAME,
                "event_id": event_id,
                "idempotency_key": idempotency_key,
                "tenant_id": tenant_id,
                "correlation_id": correlation_id,
                "domain": domain,
                "idempotent": True,
                "idempotent_duplicate": False,
                "retries": 0,
                "dlq": False,
            })

        except Exception as exec_err:
            self.release_lock(idempotency_key, domain=domain)
            self._metrics["errors_total"] += 1
            classification, is_retryable = classify_error(exec_err)

            logger.error("Execution error for event %s (key: %s): %s", event_id, idempotency_key, exec_err)

            return IdempotencyKeyReceipt({
                "status": "FAILED",
                "consumer": self.CONSUMER_NAME,
                "event_id": event_id,
                "idempotency_key": idempotency_key,
                "tenant_id": tenant_id,
                "correlation_id": correlation_id,
                "domain": domain,
                "error": str(exec_err),
                "error_type": type(exec_err).__name__,
                "error_classification": classification,
                "retryable": is_retryable,
                "idempotent": True,
                "dlq": not is_retryable,
            })

    # =========================================================================
    # Bounded Recovery & Replay Path
    # =========================================================================

    async def recover_event(
        self,
        event_or_payload: Any,
        topic: Optional[str] = None,
        headers: Optional[Dict[str, Any]] = None,
        retries_limit: Optional[int] = None,
        handler: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ) -> IdempotencyKeyReceipt:
        """
        Bounded recovery loop with deterministic duplicate prevention.
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
                headers=headers,
                attempt=retries_attempted,
                handler=handler,
            )
            last_receipt = receipt

            if receipt.get("status") == "PROCESSED":
                self._metrics["recovered_total"] += 1
                event_id = receipt.get("event_id") or "unknown"
                return IdempotencyKeyReceipt({
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

        # Recovery exhausted
        event_id = (last_receipt or {}).get("event_id", "unknown")
        return IdempotencyKeyReceipt({
            "status": "FAILED",
            "consumer": self.CONSUMER_NAME,
            "event_id": event_id,
            "retries": retries_attempted,
            "idempotent": True,
            "dlq": True,
            "error": (last_receipt or {}).get("error", "Idempotency key recovery exhausted"),
        })

    # =========================================================================
    # Metrics & Observability
    # =========================================================================

    @classmethod
    def get_idempotency_metrics(cls) -> Dict[str, Any]:
        """Return operational metrics for idempotency keys and duplicate prevention."""
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
            "keys_generated": 0,
            "keys_checked": 0,
            "duplicates_prevented": 0,
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
AddIdempotencyKeys = ConsumerIdempotencyKeys
Add_idempotency_keys = ConsumerIdempotencyKeys
EventIdempotencyKeyManager = ConsumerIdempotencyKeys
IdempotencyKeyManager = ConsumerIdempotencyKeys
IdempotencyKeyService = ConsumerIdempotencyKeys

