"""
consumer_event_replay.py

Controlled Kafka event replay service and state recovery coordinator
for FieldOps distributed event streams.

Responsibilities:
- Provide authorized, operator-controlled replay of retained Kafka events and DLQ failed events.
- Allow operators to recover downstream state after outages, fixes, or poison message remediation.
- Enforce strict role-based authorization for all replay triggers.
- Strictly preserve original event IDs, schema versions, tenant context, and correlation IDs.
- Inject non-destructive audit metadata (replay=True, replayed_by, replayed_at, replay_reason).
- Prevent duplicate business side effects using Redis-backed idempotency (force=False skips duplicates).
- Support forced replay (force=True) for intentional state reconciliation.
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


class EventReplayReceipt(dict):
    """
    Structured dictionary receipt returned after controlled event replay or recovery.
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
    def is_replayed(self) -> bool:
        return bool(self.get("replayed", False))

    @property
    def is_recovered(self) -> bool:
        return self.get("status") == "RECOVERED"

    @property
    def is_dlq(self) -> bool:
        return bool(self.get("dlq", False))

    def __bool__(self) -> bool:
        return self.is_success or self.is_dlq


class ConsumerEventReplay:
    """
    Controlled event replay service for operator-driven downstream state recovery.
    Coordinates authorized replay of retained Kafka events and quarantined DLQ records.
    """

    CONSUMER_NAME = "Add_event_replay_support"
    DEFAULT_TOPIC = "fieldops.events"
    DEFAULT_GROUP = "fieldops-event-replay"
    DEFAULT_DLQ_KEY = "consumer:dlq"
    DEFAULT_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days
    DEFAULT_MAX_RETRIES = 3
    SCHEMA_VERSION = 1

    AUTHORIZED_ROLES = frozenset({
        "admin",
        "platform_admin",
        "system_admin",
        "platform_operator",
        "operator",
        "dispatch_admin",
        "support_lead",
    })

    ALLOWED_TOPICS = frozenset(
        set(DEFAULT_KAFKA_TOPICS)
        | set(DEFAULT_DLQ_TOPICS)
        | {DEFAULT_SHARED_DLQ_TOPIC, "fieldops.analytics.events"}
    )

    # In-memory operational metrics
    _metrics: Dict[str, Any] = {
        "replayed_total": 0,
        "duplicates_skipped": 0,
        "forced_replays": 0,
        "unauthorized_attempts": 0,
        "dlq_replayed_total": 0,
        "recovered_total": 0,
        "errors_total": 0,
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

    async def __aenter__(self) -> "ConsumerEventReplay":
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
    # Authorization & Permission Guard
    # =========================================================================

    @classmethod
    def is_operator_authorized(cls, operator_role: Optional[str]) -> bool:
        """Check whether the given operator role is authorized to execute replay."""
        if not operator_role or not isinstance(operator_role, str):
            return False
        clean_role = operator_role.strip().lower()
        return clean_role in cls.AUTHORIZED_ROLES

    # =========================================================================
    # Idempotency & Marker Management
    # =========================================================================

    def _replay_marker_key(self, event_id: str) -> str:
        return f"replay:event_processed:{event_id}"

    def is_already_processed(self, event_id: str, domain: Optional[str] = None) -> bool:
        """Check whether the event was already processed to avoid duplicate side effects."""
        if not self.redis_client or not event_id:
            return False

        keys_to_check = [
            self._replay_marker_key(event_id),
            f"idempotency:default:{event_id}",
            f"order:event_processed:{event_id}",
            f"dispatch:event_processed:{event_id}",
            f"billing:event_processed:{event_id}",
            f"payment:event_processed:{event_id}",
            f"notification:event_processed:{event_id}",
        ]
        if domain:
            keys_to_check.append(f"idempotency:{domain}:{event_id}")

        try:
            for k in keys_to_check:
                if self.redis_client.get(k):
                    return True
            return False
        except Exception as e:
            logger.warning("Redis error checking idempotency for replay of %s: %s", event_id, e)
            return False

    def mark_processed(self, event_id: str, ttl_seconds: Optional[int] = None) -> None:
        """Record durable completion marker for replayed event."""
        if not self.redis_client or not event_id:
            return
        ttl = ttl_seconds or self.ttl_seconds
        try:
            self.redis_client.set(self._replay_marker_key(event_id), "1", ex=ttl)
        except Exception as e:
            logger.warning("Redis error marking replay processed for %s: %s", event_id, e)

    def clear_processed_marker(self, event_id: str) -> None:
        """Clear previous idempotency markers when force=True is explicitly requested."""
        if not self.redis_client or not event_id:
            return
        keys_to_delete = [
            self._replay_marker_key(event_id),
            f"idempotency:default:{event_id}",
            f"order:event_processed:{event_id}",
        ]
        try:
            if hasattr(self.redis_client, "delete"):
                self.redis_client.delete(*keys_to_delete)
        except Exception as e:
            logger.warning("Redis error clearing markers for %s: %s", event_id, e)

    # =========================================================================
    # Controlled Replay Operations
    # =========================================================================

    async def replay_event(
        self,
        event_or_payload: Any,
        operator_role: str,
        operator_id: Optional[str] = None,
        force: bool = False,
        reason: Optional[str] = None,
        handler: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ) -> EventReplayReceipt:
        """
        Safely replay a single retained or failed event under operator supervision.
        - Enforces operator authorization (Requirement 1).
        - Preserves event_id, schema_version, tenant_id, correlation_id (Requirement 1).
        - Prevents duplicate business side effects if force=False.
        - Conforms to exact expected output contract:
          { "status": "RECOVERED", "event_id": ..., "retries": 1, "idempotent": True, "dlq": False }
        """
        now_iso = datetime.now(timezone.utc).isoformat()

        # 1. Authorization Verification (Requirement 1)
        if not self.is_operator_authorized(operator_role):
            self._metrics["unauthorized_attempts"] += 1
            logger.warning("Unauthorized replay attempt with role '%s' by operator '%s'", operator_role, operator_id)
            return EventReplayReceipt({
                "status": "UNAUTHORIZED",
                "consumer": self.CONSUMER_NAME,
                "event_id": "unknown",
                "error": f"Permission denied: Operator role '{operator_role}' is not authorized for event replay.",
                "error_classification": ErrorClassification.TERMINAL.value,
                "idempotent": False,
                "dlq": False,
            })

        # 2. Parse & Unpack Payload safely
        topic = None
        correlation_id = None
        try:
            if isinstance(event_or_payload, (bytes, bytearray)):
                try:
                    event_or_payload = event_or_payload.decode("utf-8")
                except UnicodeDecodeError as u_err:
                    self._metrics["errors_total"] += 1
                    return EventReplayReceipt({
                        "status": "FAILED",
                        "consumer": self.CONSUMER_NAME,
                        "event_id": "unknown",
                        "error": f"Malformed encoding: {u_err}",
                        "error_type": "UnicodeDecodeError",
                        "idempotent": False,
                        "dlq": True,
                    })

            if isinstance(event_or_payload, str):
                try:
                    event_or_payload = json.loads(event_or_payload)
                except json.JSONDecodeError as j_err:
                    self._metrics["errors_total"] += 1
                    return EventReplayReceipt({
                        "status": "FAILED",
                        "consumer": self.CONSUMER_NAME,
                        "event_id": "unknown",
                        "error": f"Malformed JSON: {j_err}",
                        "error_type": "JSONDecodeError",
                        "idempotent": False,
                        "dlq": True,
                    })

            if isinstance(event_or_payload, MessageEnvelope):
                payload = dict(event_or_payload.payload)
                correlation_id = getattr(event_or_payload, "correlation_id", None) or payload.get("correlation_id")
                topic = getattr(event_or_payload, "topic", self.topic)
            elif isinstance(event_or_payload, dict):
                if "payload" in event_or_payload and isinstance(event_or_payload["payload"], dict):
                    payload = dict(event_or_payload["payload"])
                    correlation_id = event_or_payload.get("correlation_id") or payload.get("correlation_id")
                    topic = event_or_payload.get("topic", self.topic)
                else:
                    payload = dict(event_or_payload)
                    correlation_id = payload.get("correlation_id")
                    topic = payload.get("topic", self.topic)
            else:
                self._metrics["errors_total"] += 1
                return EventReplayReceipt({
                    "status": "FAILED",
                    "consumer": self.CONSUMER_NAME,
                    "event_id": "unknown",
                    "error": f"Unsupported message type: {type(event_or_payload).__name__}",
                    "idempotent": False,
                    "dlq": True,
                })

        except Exception as parse_err:
            self._metrics["errors_total"] += 1
            return EventReplayReceipt({
                "status": "FAILED",
                "consumer": self.CONSUMER_NAME,
                "event_id": "unknown",
                "error": f"Parse error: {parse_err}",
                "idempotent": False,
                "dlq": True,
            })

        # 3. Preserve Core Identity & Schema Invariants (Requirement 1)
        event_id = payload.get("event_id") or "unknown"
        tenant_id = payload.get("tenant_id")
        schema_version = payload.get("schema_version")

        missing_fields = []
        if not payload.get("event_id") or not str(payload.get("event_id")).strip():
            missing_fields.append("event_id")
        if not tenant_id or not str(tenant_id).strip():
            missing_fields.append("tenant_id")
        if schema_version is None:
            missing_fields.append("schema_version")

        if missing_fields:
            self._metrics["errors_total"] += 1
            return EventReplayReceipt({
                "status": "FAILED",
                "consumer": self.CONSUMER_NAME,
                "event_id": event_id,
                "tenant_id": tenant_id,
                "error": f"Schema validation error: Missing required fields: {', '.join(sorted(missing_fields))}",
                "error_type": "ValidationError",
                "idempotent": False,
                "dlq": True,
            })

        # 4. Security Check: Detect & Reject Forbidden Keys
        lowered_keys = {str(k).lower() for k in payload.keys()}
        found_forbidden = lowered_keys.intersection(_FORBIDDEN_KEYS)
        if found_forbidden:
            self._metrics["errors_total"] += 1
            logger.warning("Replay event %s contains forbidden sensitive keys: %s", event_id, found_forbidden)
            return EventReplayReceipt({
                "status": "FAILED",
                "consumer": self.CONSUMER_NAME,
                "event_id": event_id,
                "tenant_id": tenant_id,
                "error": f"Security violation: Payload contains forbidden sensitive keys: {', '.join(sorted(found_forbidden))}",
                "error_type": "SecurityPolicyError",
                "idempotent": False,
                "dlq": True,
            })

        # 5. Prevent Duplicate Business Side Effects (Zero Duplicate Rule)
        domain = payload.get("domain") or "default"
        if not force and self.is_already_processed(event_id, domain=domain):
            self._metrics["duplicates_skipped"] += 1
            logger.info("Event %s already processed; skipping replay to prevent duplicate business side effects.", event_id)
            return EventReplayReceipt({
                "status": "RECOVERED",
                "consumer": self.CONSUMER_NAME,
                "event_id": event_id,
                "tenant_id": tenant_id,
                "correlation_id": correlation_id,
                "retries": 0,
                "idempotent": True,
                "skipped_duplicate": True,
                "dlq": False,
            })

        # If forced replay, clear prior markers
        if force:
            self._metrics["forced_replays"] += 1
            self.clear_processed_marker(event_id)

        # 6. Inject Replay Audit Metadata
        safe_payload = redact_sensitive_data(payload)
        safe_payload["replay"] = True
        safe_payload["replayed_at"] = now_iso
        safe_payload["replayed_by"] = operator_id or "system_operator"
        safe_payload["replay_reason"] = reason or "Operator requested downstream state recovery"

        # 7. Execute Domain Handler
        effective_handler = handler or self.handler
        try:
            if effective_handler:
                import inspect
                if inspect.iscoroutinefunction(effective_handler):
                    handler_result = await effective_handler(safe_payload)
                else:
                    handler_result = effective_handler(safe_payload)

                if isinstance(handler_result, dict) and handler_result.get("status") == "FAILED":
                    err_msg = handler_result.get("error", "Downstream handler returned failure during replay")
                    classification, is_retryable = classify_error(err_msg)
                    return EventReplayReceipt({
                        "status": "FAILED",
                        "consumer": self.CONSUMER_NAME,
                        "event_id": event_id,
                        "tenant_id": tenant_id,
                        "correlation_id": correlation_id,
                        "error": err_msg,
                        "error_type": handler_result.get("error_type", "HandlerError"),
                        "retryable": is_retryable,
                        "idempotent": True,
                        "dlq": not is_retryable,
                    })

            # 8. Mark Processed & Record Metrics
            self.mark_processed(event_id)
            self._metrics["replayed_total"] += 1
            self._metrics["recovered_total"] += 1

            logger.info(
                "Successfully replayed event %s for tenant %s by operator %s (forced=%s)",
                event_id,
                tenant_id,
                operator_id,
                force,
            )

            return EventReplayReceipt({
                "status": "RECOVERED",
                "consumer": self.CONSUMER_NAME,
                "event_id": event_id,
                "tenant_id": tenant_id,
                "correlation_id": correlation_id,
                "retries": 1,
                "idempotent": True,
                "replayed": True,
                "dlq": False,
            })

        except Exception as exec_err:
            self._metrics["errors_total"] += 1
            classification, is_retryable = classify_error(exec_err)
            logger.error("Execution error replaying event %s: %s", event_id, exec_err)
            return EventReplayReceipt({
                "status": "FAILED",
                "consumer": self.CONSUMER_NAME,
                "event_id": event_id,
                "tenant_id": tenant_id,
                "correlation_id": correlation_id,
                "error": str(exec_err),
                "error_type": type(exec_err).__name__,
                "retryable": is_retryable,
                "idempotent": True,
                "dlq": not is_retryable,
            })

    # =========================================================================
    # Batch & DLQ Replay Operations
    # =========================================================================

    async def replay_batch(
        self,
        events: List[Any],
        operator_role: str,
        operator_id: Optional[str] = None,
        force: bool = False,
        reason: Optional[str] = None,
        handler: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ) -> List[EventReplayReceipt]:
        """Replay a batch of retained events in sequence."""
        results = []
        for ev in events:
            receipt = await self.replay_event(
                event_or_payload=ev,
                operator_role=operator_role,
                operator_id=operator_id,
                force=force,
                reason=reason,
                handler=handler,
            )
            results.append(receipt)
        return results

    async def replay_dlq_events(
        self,
        operator_role: str,
        operator_id: Optional[str] = None,
        limit: int = 50,
        force: bool = False,
        handler: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ) -> List[EventReplayReceipt]:
        """
        Replay quarantined events from the DLQ storage into healthy downstream processing.
        """
        if not self.is_operator_authorized(operator_role):
            self._metrics["unauthorized_attempts"] += 1
            return [
                EventReplayReceipt({
                    "status": "UNAUTHORIZED",
                    "consumer": self.CONSUMER_NAME,
                    "event_id": "unknown",
                    "error": "Operator not authorized for DLQ replay",
                    "idempotent": False,
                    "dlq": False,
                })
            ]

        if not self.redis_client:
            return []

        raw_items = []
        try:
            raw_items = self.redis_client.lrange(self.dlq_key, 0, max(0, limit - 1))
        except Exception as e:
            logger.warning("Error fetching DLQ events for replay: %s", e)
            return []

        results = []
        for item in raw_items:
            try:
                record = json.loads(item) if isinstance(item, str) else item
                receipt = await self.replay_event(
                    event_or_payload=record,
                    operator_role=operator_role,
                    operator_id=operator_id,
                    force=force,
                    reason="DLQ poison message resolution and recovery",
                    handler=handler,
                )
                results.append(receipt)
                if receipt.is_success:
                    self._metrics["dlq_replayed_total"] += 1
            except Exception as item_err:
                logger.error("Error processing DLQ replay item: %s", item_err)

        return results

    # =========================================================================
    # Standard Recovery Loop (Contract Compatibility)
    # =========================================================================

    async def recover_event(
        self,
        event_or_payload: Any,
        operator_role: str = "operator",
        operator_id: Optional[str] = "system_recovery",
        retries_limit: Optional[int] = None,
        handler: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ) -> EventReplayReceipt:
        """
        Bounded recovery loop fulfilling the story contract:
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
            receipt = await self.replay_event(
                event_or_payload=event_or_payload,
                operator_role=operator_role,
                operator_id=operator_id,
                force=False,
                handler=handler,
            )
            last_receipt = receipt

            if receipt.get("status") == "RECOVERED":
                event_id = receipt.get("event_id") or "unknown"
                return EventReplayReceipt({
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

        event_id = (last_receipt or {}).get("event_id", "unknown")
        return EventReplayReceipt({
            "status": "FAILED",
            "consumer": self.CONSUMER_NAME,
            "event_id": event_id,
            "retries": retries_attempted,
            "idempotent": True,
            "dlq": True,
            "error": (last_receipt or {}).get("error", "Replay recovery attempts exhausted"),
        })

    # =========================================================================
    # Metrics & Health Snapshot
    # =========================================================================

    @classmethod
    def get_replay_metrics(cls) -> Dict[str, Any]:
        """Return operational metrics for event replay and operator recovery."""
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
            "replayed_total": 0,
            "duplicates_skipped": 0,
            "forced_replays": 0,
            "unauthorized_attempts": 0,
            "dlq_replayed_total": 0,
            "recovered_total": 0,
            "errors_total": 0,
        }


# Authoritative aliases ensuring complete cross-story naming compatibility
AddEventReplaySupport = ConsumerEventReplay
Add_event_replay_support = ConsumerEventReplay
EventReplayService = ConsumerEventReplay
ControlledEventReplay = ConsumerEventReplay

