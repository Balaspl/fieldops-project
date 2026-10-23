"""
consumer_event_ordering.py

Kafka event ordering manager and monotonic state progression coordinator
for FieldOps distributed event streams.

Responsibilities:
- Preserve strict event ordering for events belonging to the same aggregate (job, technician, invoice, payment).
- Prevent later status, assignment, or location events from being incorrectly applied before earlier events.
- Enforce Kafka partition key strategies ensuring single-partition FIFO routing per aggregate.
- Detect and safely ignore stale or out-of-order sequence numbers, status ranks, and timestamps.
- Guard against database state regressions without replacing authoritative domain source-of-truth services.
- Coordinate with distributed locking and durable idempotency markers.
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


class EventOrderingReceipt(dict):
    """
    Structured dictionary receipt returned after ordered event processing or recovery.
    Complies with the required output contract:
    {
        "status": "RECOVERED",
        "event_id": "evt_01JEXAMPLE",
        "retries": 1,
        "idempotent": True,
        "dlq": False
    }
    Or for standard ordered executions:
    {
        "status": "PROCESSED",
        "consumer": "Maintain_event_ordering",
        "event_id": "evt_01JEXAMPLE",
        "aggregate_id": "job-101",
        "out_of_order": False,
        "stale": False,
        "idempotent": True,
        "retries": 0,
        "dlq": False
    }
    """

    @property
    def is_success(self) -> bool:
        return self.get("status") in ("RECOVERED", "PROCESSED", "STALE_IGNORED") and not self.get("dlq", False)

    @property
    def is_stale(self) -> bool:
        return bool(self.get("stale", False))

    @property
    def is_out_of_order(self) -> bool:
        return bool(self.get("out_of_order", False))

    @property
    def is_recovered(self) -> bool:
        return self.get("status") == "RECOVERED"

    @property
    def is_dlq(self) -> bool:
        return bool(self.get("dlq", False))

    def __bool__(self) -> bool:
        return self.is_success or self.is_dlq


class ConsumerEventOrdering:
    """
    Monotonic event ordering coordinator and consumer state progression guard.
    Prevents out-of-order status/assignment/location delivery from corrupting domain state.
    """

    CONSUMER_NAME = "Maintain_event_ordering"
    DEFAULT_TOPIC = "fieldops.job.events"
    DEFAULT_GROUP = "fieldops-ordering"
    DEFAULT_LOCK_TIMEOUT_SECONDS = 30
    DEFAULT_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days
    DEFAULT_MAX_RETRIES = 3
    SCHEMA_VERSION = 1

    # Monotonic status progression rank map
    STATUS_RANK: Dict[str, int] = {
        "CREATED": 1,
        "ASSIGNED": 2,
        "RE-DISPATCH": 2,
        "REDISPATCH": 2,
        "EN_ROUTE": 3,
        "EN-ROUTE": 3,
        "ON_SITE": 4,
        "ON-SITE": 4,
        "IN_PROGRESS": 4,
        "IN-PROGRESS": 4,
        "COMPLETED": 5,
        "CANCELLED": 6,
        "CLOSED": 6,
    }

    ALLOWED_TOPICS = frozenset(
        set(DEFAULT_KAFKA_TOPICS)
        | set(DEFAULT_DLQ_TOPICS)
        | {DEFAULT_SHARED_DLQ_TOPIC, "fieldops.analytics.events"}
    )

    # In-memory operational metrics
    _metrics: Dict[str, Any] = {
        "processed_total": 0,
        "stale_events_ignored": 0,
        "out_of_order_detected": 0,
        "locks_acquired": 0,
        "locks_rejected": 0,
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
        lock_timeout: int = DEFAULT_LOCK_TIMEOUT_SECONDS,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        bootstrap_servers: Optional[str] = None,
    ):
        self.topic = topic or self.DEFAULT_TOPIC
        self.group_id = group_id or self.DEFAULT_GROUP
        self.bootstrap_servers = bootstrap_servers
        self.lock_timeout = max(1, lock_timeout)
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

    async def __aenter__(self) -> "ConsumerEventOrdering":
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
    # Partition Key Resolution (Producer & Ordering Stream Boundary)
    # =========================================================================

    @classmethod
    def compute_partition_key(
        cls,
        message_or_payload: Any,
        topic: Optional[str] = None,
    ) -> str:
        """
        Derive the canonical Kafka partition key ensuring all events for the same
        job or aggregate are routed to the exact same Kafka partition (FIFO).
        """
        topic_name = str(topic or "").strip()
        payload = message_or_payload
        tenant_id = None

        if isinstance(message_or_payload, MessageEnvelope):
            payload = message_or_payload.payload
            tenant_id = message_or_payload.tenant_id
            topic_name = getattr(message_or_payload, "topic", topic_name)
        elif isinstance(message_or_payload, dict):
            if "payload" in message_or_payload and isinstance(message_or_payload["payload"], dict):
                payload = message_or_payload["payload"]
                tenant_id = message_or_payload.get("tenant_id")
                topic_name = message_or_payload.get("topic", topic_name)
            else:
                tenant_id = message_or_payload.get("tenant_id")

        if not isinstance(payload, dict):
            return str(payload)

        job_id = payload.get("job_id")
        technician_id = payload.get("technician_id") or payload.get("tech_id")
        invoice_id = payload.get("invoice_id")
        payment_id = payload.get("payment_id") or payload.get("transaction_id")
        aggregate_id = payload.get("aggregate_id")

        # 1. Job-ordered streams (Job events, GPS tracking, SLA monitoring)
        job_topics = {"fieldops.job.events", "fieldops.gps.events", "fieldops.sla.events"}
        if topic_name in job_topics or job_id is not None:
            if job_id is not None and str(job_id).strip() != "":
                return str(job_id).strip()

        # 2. Technician tracking streams
        if technician_id is not None and str(technician_id).strip() != "":
            return f"tech:{str(technician_id).strip()}"

        # 3. Financial aggregates
        if invoice_id is not None and str(invoice_id).strip() != "":
            return f"inv:{str(invoice_id).strip()}"
        if payment_id is not None and str(payment_id).strip() != "":
            return f"pay:{str(payment_id).strip()}"

        # 4. Explicit aggregate identifier
        if aggregate_id is not None and str(aggregate_id).strip() != "":
            return str(aggregate_id).strip()

        # 5. Tenant-ordered streams
        if tenant_id and str(tenant_id).strip() != "":
            return str(tenant_id).strip()

        # Fallback to event_id or message_id
        return str(payload.get("event_id") or payload.get("message_id") or uuid.uuid4())

    # =========================================================================
    # Aggregate Extraction & Monotonicity State Keys
    # =========================================================================

    @classmethod
    def extract_aggregate_context(cls, payload: Dict[str, Any]) -> Tuple[str, str]:
        """Return (aggregate_type, aggregate_id) for state progression tracking."""
        if payload.get("job_id"):
            return "job", str(payload["job_id"]).strip()
        if payload.get("invoice_id"):
            return "invoice", str(payload["invoice_id"]).strip()
        if payload.get("payment_id") or payload.get("transaction_id"):
            pid = payload.get("payment_id") or payload.get("transaction_id")
            return "payment", str(pid).strip()
        if payload.get("technician_id") or payload.get("tech_id"):
            tid = payload.get("technician_id") or payload.get("tech_id")
            return "technician", str(tid).strip()
        if payload.get("aggregate_id"):
            agg_type = str(payload.get("aggregate_type") or "aggregate").strip().lower()
            return agg_type, str(payload["aggregate_id"]).strip()
        return "generic", str(payload.get("event_id") or "unknown")

    def _seq_key(self, agg_type: str, agg_id: str) -> str:
        return f"order:last_seq:{agg_type}:{agg_id}"

    def _rank_key(self, agg_type: str, agg_id: str) -> str:
        return f"order:last_rank:{agg_type}:{agg_id}"

    def _ts_key(self, agg_type: str, agg_id: str) -> str:
        return f"order:last_ts:{agg_type}:{agg_id}"

    def _lock_key(self, agg_type: str, agg_id: str) -> str:
        return f"lock:ordering:{agg_type}:{agg_id}"

    def _processed_key(self, event_id: str) -> str:
        return f"order:event_processed:{event_id}"

    # =========================================================================
    # Distributed Aggregate Locking
    # =========================================================================

    def acquire_lock(
        self,
        agg_type: str,
        agg_id: str,
        timeout_seconds: Optional[int] = None,
        worker_token: Optional[str] = None,
    ) -> bool:
        """
        Acquire distributed lock per aggregate to serialize processing and prevent race conditions.
        """
        if not self.redis_client or not agg_id:
            return True

        timeout = timeout_seconds or self.lock_timeout
        token = worker_token or str(uuid.uuid4())
        lock_key = self._lock_key(agg_type, agg_id)

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
            logger.warning("Redis error acquiring ordering lock %s: %s", lock_key, e)
            return True

    def release_lock(self, agg_type: str, agg_id: str, worker_token: Optional[str] = None) -> bool:
        """Release the aggregate lock."""
        if not self.redis_client or not agg_id:
            return True
        lock_key = self._lock_key(agg_type, agg_id)
        try:
            if hasattr(self.redis_client, "delete"):
                self.redis_client.delete(lock_key)
            return True
        except Exception as e:
            logger.warning("Redis error releasing ordering lock %s: %s", lock_key, e)
            return False

    # =========================================================================
    # Monotonic Ordering Validation
    # =========================================================================

    @classmethod
    def normalize_status_rank(cls, raw_status: Optional[str]) -> Optional[int]:
        """Convert status string to canonical progression rank."""
        if not raw_status:
            return None
        norm = str(raw_status).strip().upper().replace(" ", "_")
        return cls.STATUS_RANK.get(norm)

    @staticmethod
    def parse_iso_timestamp(raw_ts: Optional[Union[str, datetime]]) -> Optional[float]:
        """Parse ISO timestamp or datetime into epoch seconds for comparison."""
        if raw_ts is None:
            return None
        if isinstance(raw_ts, datetime):
            if raw_ts.tzinfo is None:
                raw_ts = raw_ts.replace(tzinfo=timezone.utc)
            return raw_ts.timestamp()
        if isinstance(raw_ts, str):
            try:
                cleaned = raw_ts.replace("Z", "+00:00")
                dt = datetime.fromisoformat(cleaned)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.timestamp()
            except Exception:
                return None
        return None

    def is_stale_or_out_of_order(
        self,
        payload: Dict[str, Any],
        agg_type: str,
        agg_id: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        Determine if the incoming event is stale or arrives out-of-order relative
        to the highest processed state for the aggregate.
        Returns: (is_stale, reason)
        """
        if not self.redis_client or not agg_id:
            return False, None

        # 1. Monotonic Sequence Number Check
        seq_num = payload.get("sequence_number") or payload.get("sequence") or payload.get("seq")
        if seq_num is not None:
            try:
                curr_seq = int(seq_num)
                last_seq_raw = self.redis_client.get(self._seq_key(agg_type, agg_id))
                if last_seq_raw is not None:
                    last_seq = int(last_seq_raw)
                    if curr_seq <= last_seq:
                        return True, f"Stale sequence: incoming {curr_seq} <= last_processed {last_seq}"
            except (ValueError, TypeError):
                pass

        # 2. Monotonic Status Rank Check (prevents status regression like COMPLETED -> EN_ROUTE)
        status_candidate = (
            payload.get("new_status")
            or payload.get("status")
            or payload.get("event_type")
            or payload.get("event")
        )
        curr_rank = self.normalize_status_rank(status_candidate)
        if curr_rank is not None:
            try:
                last_rank_raw = self.redis_client.get(self._rank_key(agg_type, agg_id))
                if last_rank_raw is not None:
                    last_rank = int(last_rank_raw)
                    if curr_rank < last_rank:
                        return True, f"Out-of-order status regression: incoming '{status_candidate}' (rank {curr_rank}) < highest_processed (rank {last_rank})"
            except (ValueError, TypeError):
                pass

        # 3. Monotonic Timestamp Check (prevents stale location / ping overwrite)
        ts_candidate = (
            payload.get("timestamp")
            or payload.get("recorded_at")
            or payload.get("completed_at")
            or payload.get("created_at")
        )
        curr_ts = self.parse_iso_timestamp(ts_candidate)
        if curr_ts is not None:
            try:
                last_ts_raw = self.redis_client.get(self._ts_key(agg_type, agg_id))
                if last_ts_raw is not None:
                    last_ts = float(last_ts_raw)
                    if curr_ts < last_ts:
                        return True, f"Stale timestamp: incoming {curr_ts} < highest_processed {last_ts}"
            except (ValueError, TypeError):
                pass

        return False, None

    def record_processed_state(
        self,
        event_id: str,
        payload: Dict[str, Any],
        agg_type: str,
        agg_id: str,
    ) -> None:
        """Update monotonic sequence, rank, timestamp markers, and idempotency key on success."""
        if not self.redis_client:
            return

        ttl = self.ttl_seconds

        # Update sequence number
        seq_num = payload.get("sequence_number") or payload.get("sequence") or payload.get("seq")
        if seq_num is not None:
            try:
                self.redis_client.set(self._seq_key(agg_type, agg_id), str(int(seq_num)), ex=ttl)
            except Exception:
                pass

        # Update status rank (only advance to higher rank)
        status_candidate = (
            payload.get("new_status")
            or payload.get("status")
            or payload.get("event_type")
            or payload.get("event")
        )
        curr_rank = self.normalize_status_rank(status_candidate)
        if curr_rank is not None:
            try:
                last_rank_raw = self.redis_client.get(self._rank_key(agg_type, agg_id))
                last_rank = int(last_rank_raw) if last_rank_raw is not None else 0
                if curr_rank > last_rank:
                    self.redis_client.set(self._rank_key(agg_type, agg_id), str(curr_rank), ex=ttl)
            except Exception:
                pass

        # Update timestamp (only advance to higher timestamp)
        ts_candidate = (
            payload.get("timestamp")
            or payload.get("recorded_at")
            or payload.get("completed_at")
            or payload.get("created_at")
        )
        curr_ts = self.parse_iso_timestamp(ts_candidate)
        if curr_ts is not None:
            try:
                last_ts_raw = self.redis_client.get(self._ts_key(agg_type, agg_id))
                last_ts = float(last_ts_raw) if last_ts_raw is not None else 0.0
                if curr_ts > last_ts:
                    self.redis_client.set(self._ts_key(agg_type, agg_id), str(curr_ts), ex=ttl)
            except Exception:
                pass

        # Mark event processed
        if event_id:
            try:
                self.redis_client.set(self._processed_key(event_id), "1", ex=ttl)
            except Exception:
                pass

    # =========================================================================
    # Event Processing Pipeline
    # =========================================================================

    async def handle_message(self, message: Any) -> EventOrderingReceipt:
        """Callback suitable for KafkaConsumerManager.consume(handler)."""
        return await self.process_event(message)

    async def process_event(
        self,
        message: Any,
        attempt: int = 1,
        handler: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ) -> EventOrderingReceipt:
        """
        Process event with partition key validation, distributed aggregate lock,
        monotonic ordering enforcement, and zero database state regression.
        """
        now_iso = datetime.now(timezone.utc).isoformat()

        # 1. Parse & decode message payload safely
        try:
            if isinstance(message, (bytes, bytearray)):
                try:
                    message = message.decode("utf-8")
                except UnicodeDecodeError as u_err:
                    self._metrics["errors_total"] += 1
                    return EventOrderingReceipt({
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
                    return EventOrderingReceipt({
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
                return EventOrderingReceipt({
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
            return EventOrderingReceipt({
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
            return EventOrderingReceipt({
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
            return EventOrderingReceipt({
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
            return EventOrderingReceipt({
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

        # 5. Extract aggregate context
        agg_type, agg_id = self.extract_aggregate_context(payload)
        partition_key = self.compute_partition_key(payload, topic)

        # 6. Idempotency Check: Already processed?
        if self.redis_client and self.redis_client.get(self._processed_key(event_id)):
            logger.info("Event %s already processed; skipping duplicate.", event_id)
            return EventOrderingReceipt({
                "status": "PROCESSED",
                "consumer": self.CONSUMER_NAME,
                "event_id": event_id,
                "aggregate_id": agg_id,
                "aggregate_type": agg_type,
                "partition_key": partition_key,
                "tenant_id": tenant_id,
                "correlation_id": correlation_id,
                "attempt": attempt,
                "idempotent": True,
                "idempotent_duplicate": True,
                "out_of_order": False,
                "stale": False,
                "retries": 0,
                "dlq": False,
            })

        # 7. Acquire Aggregate Distributed Lock (prevents concurrent race conditions)
        worker_token = str(uuid.uuid4())
        locked = self.acquire_lock(agg_type, agg_id, timeout_seconds=self.lock_timeout, worker_token=worker_token)
        if not locked:
            logger.warning("Contention detected on aggregate %s:%s. Another worker holds lock.", agg_type, agg_id)
            return EventOrderingReceipt({
                "status": "LOCKED",
                "consumer": self.CONSUMER_NAME,
                "event_id": event_id,
                "aggregate_id": agg_id,
                "aggregate_type": agg_type,
                "error": f"Concurrent processing locked for aggregate '{agg_type}:{agg_id}'",
                "retryable": True,
                "idempotent": True,
                "dlq": False,
            })

        # 8. Check Monotonicity: Stale or Out-of-Order?
        is_stale, stale_reason = self.is_stale_or_out_of_order(payload, agg_type, agg_id)
        if is_stale:
            self._metrics["stale_events_ignored"] += 1
            self._metrics["out_of_order_detected"] += 1
            logger.warning(
                "Stale/out-of-order event %s for %s:%s safely ignored: %s",
                event_id,
                agg_type,
                agg_id,
                stale_reason,
            )
            # Acknowledge without running downstream handler; zero state regression!
            self.release_lock(agg_type, agg_id, worker_token)
            return EventOrderingReceipt({
                "status": "STALE_IGNORED",
                "consumer": self.CONSUMER_NAME,
                "event_id": event_id,
                "aggregate_id": agg_id,
                "aggregate_type": agg_type,
                "partition_key": partition_key,
                "tenant_id": tenant_id,
                "correlation_id": correlation_id,
                "out_of_order": True,
                "stale": True,
                "reason": stale_reason,
                "idempotent": True,
                "retries": 0,
                "dlq": False,
            })

        # 9. Execute Downstream Domain Handler
        effective_handler = handler or self.handler
        try:
            if effective_handler:
                import inspect
                if inspect.iscoroutinefunction(effective_handler):
                    handler_result = await effective_handler(payload)
                else:
                    handler_result = effective_handler(payload)

                if isinstance(handler_result, dict) and handler_result.get("status") == "FAILED":
                    self.release_lock(agg_type, agg_id, worker_token)
                    err_msg = handler_result.get("error", "Downstream handler returned failure")
                    classification, is_retryable = classify_error(err_msg)
                    return EventOrderingReceipt({
                        "status": "FAILED",
                        "consumer": self.CONSUMER_NAME,
                        "event_id": event_id,
                        "aggregate_id": agg_id,
                        "tenant_id": tenant_id,
                        "correlation_id": correlation_id,
                        "error": err_msg,
                        "error_type": handler_result.get("error_type", "HandlerError"),
                        "error_classification": classification,
                        "retryable": is_retryable,
                        "idempotent": True,
                        "dlq": not is_retryable,
                    })

            # 10. Record State Progression & Processed Marker
            self.record_processed_state(event_id, payload, agg_type, agg_id)
            self._metrics["processed_total"] += 1

            logger.info(
                "Successfully applied ordered event %s for %s:%s (partition_key: %s)",
                event_id,
                agg_type,
                agg_id,
                partition_key,
            )

            return EventOrderingReceipt({
                "status": "PROCESSED",
                "consumer": self.CONSUMER_NAME,
                "event_id": event_id,
                "aggregate_id": agg_id,
                "aggregate_type": agg_type,
                "partition_key": partition_key,
                "tenant_id": tenant_id,
                "correlation_id": correlation_id,
                "attempt": attempt,
                "out_of_order": False,
                "stale": False,
                "idempotent": True,
                "retries": 0,
                "dlq": False,
            })

        except Exception as exec_err:
            self.release_lock(agg_type, agg_id, worker_token)
            self._metrics["errors_total"] += 1
            classification, is_retryable = classify_error(exec_err)
            logger.error("Execution error processing ordered event %s: %s", event_id, exec_err)
            return EventOrderingReceipt({
                "status": "FAILED",
                "consumer": self.CONSUMER_NAME,
                "event_id": event_id,
                "aggregate_id": agg_id,
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
            self.release_lock(agg_type, agg_id, worker_token)

    # =========================================================================
    # Allowed Recovery & Replay Path
    # =========================================================================

    async def recover_event(
        self,
        event_or_payload: Any,
        retries_limit: Optional[int] = None,
        handler: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ) -> EventOrderingReceipt:
        """
        Execute bounded recovery loop for transient failures with ordering guarantees.
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
                attempt=retries_attempted,
                handler=handler,
            )
            last_receipt = receipt

            if receipt.get("status") in ("PROCESSED", "STALE_IGNORED"):
                self._metrics["recovered_total"] += 1
                event_id = receipt.get("event_id") or "unknown"
                return EventOrderingReceipt({
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
        return EventOrderingReceipt({
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
    def get_ordering_metrics(cls) -> Dict[str, Any]:
        """Return operational metrics for event ordering and stale event detection."""
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
            "stale_events_ignored": 0,
            "out_of_order_detected": 0,
            "locks_acquired": 0,
            "locks_rejected": 0,
            "recovered_total": 0,
            "errors_total": 0,
        }


# Authoritative aliases ensuring complete cross-story naming compatibility
MaintainEventOrdering = ConsumerEventOrdering
Maintain_event_ordering = ConsumerEventOrdering
ConsumerEventOrderingService = ConsumerEventOrdering
EventOrderingManager = ConsumerEventOrdering

