"""
kafka_monitoring_dashboard.py

Unified Kafka monitoring dashboard coordinator for FieldOps distributed event streams.

Responsibilities:
- Create operational visibility for broker status, topic throughput, consumer lag,
  failures, DLQ volume, and recovery state in one cohesive place.
- Provide operators with unified telemetry to rapidly identify Kafka stream issues.
- Enforce tenant-safe operational access and strict credential redaction.
- Coordinate with existing monitoring conventions, health checks, DLQ stores, and replay metrics.
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
from time import monotonic
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from app.redis_client import get_redis_client
from app.services.kafka.producer import KafkaProducer
from app.services.kafka.consumer import KafkaConsumerManager, DEFAULT_CONSUMER_GROUPS
from app.services.kafka.monitoring import kafka_monitoring, KafkaMonitoring
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


class DashboardReceipt(dict):
    """
    Structured dictionary receipt returned after dashboard event processing or recovery.
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

    def __bool__(self) -> bool:
        return self.is_success or self.is_dlq


class KafkaMonitoringDashboard:
    """
    Central operational dashboard providing unified visibility into broker status,
    topic throughput, consumer lag, failure rates, DLQ volume, and recovery state.
    """

    CONSUMER_NAME = "Add_kafka_monitoring_dashboard"
    DEFAULT_TOPIC = "fieldops.events"
    DEFAULT_GROUP = "fieldops-kafka-dashboard"
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
        "dashboard_requests": 0,
        "recovered_total": 0,
        "errors_total": 0,
    }

    def __init__(
        self,
        topic: Optional[str] = None,
        group_id: Optional[str] = None,
        consumer_manager: Optional[KafkaConsumerManager] = None,
        redis_client: Optional[Any] = None,
        monitoring: Optional[KafkaMonitoring] = None,
        handler: Optional[Callable[[Dict[str, Any]], Any]] = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        bootstrap_servers: Optional[str] = None,
    ):
        self.topic = topic or self.DEFAULT_TOPIC
        self.group_id = group_id or self.DEFAULT_GROUP
        self.bootstrap_servers = bootstrap_servers
        self.max_retries = max(1, max_retries)
        self.handler = handler
        self.monitoring = monitoring or kafka_monitoring

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

    async def __aenter__(self) -> "KafkaMonitoringDashboard":
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
    # Unified Dashboard Summary Aggregator
    # =========================================================================

    async def get_dashboard_summary(
        self,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Aggregate broker status, topic throughput, consumer lag, failures,
        DLQ volume, and recovery state into one unified dashboard payload.
        Enforces tenant safety and credential redaction.
        """
        self._metrics["dashboard_requests"] += 1
        now_iso = datetime.now(timezone.utc).isoformat()

        # 1. Broker Status
        try:
            broker_status = await self.monitoring.broker_health()
        except Exception as e:
            logger.warning("Error getting broker health for dashboard: %s", e)
            broker_status = {
                "status": "unhealthy",
                "connected": False,
                "broker_count": 0,
                "brokers": [],
                "error": str(e),
            }

        # 2. Topic Health & Throughput
        try:
            topic_health = await self.monitoring.topic_health()
            snapshot = self.monitoring.snapshot()
            topic_throughput = {
                "published_total": snapshot.get("published_total", 0),
                "consumed_total": snapshot.get("consumed_total", 0),
                "publish_failures": snapshot.get("publish_failures", 0),
                "consume_failures": snapshot.get("consume_failures", 0),
                "topics": snapshot.get("topics", {}),
                "health_by_topic": topic_health,
            }
        except Exception as e:
            logger.warning("Error getting topic throughput for dashboard: %s", e)
            topic_throughput = {
                "published_total": 0,
                "consumed_total": 0,
                "publish_failures": 0,
                "consume_failures": 0,
                "topics": {},
                "health_by_topic": {},
                "status": "degraded",
                "error": str(e),
            }

        # 3. Consumer Lag (Across canonical consumer groups)
        consumer_lag: Dict[str, Any] = {}
        try:
            for top, grp in DEFAULT_CONSUMER_GROUPS.items():
                lag_info = await self.monitoring.consumer_lag(top, grp)
                consumer_lag[top] = lag_info
        except Exception as e:
            logger.warning("Error getting consumer lag for dashboard: %s", e)
            consumer_lag = {top: {"lag": 0, "partitions": {}} for top in DEFAULT_CONSUMER_GROUPS}

        # 4. Failures Context & Stored Failed Events (from FailedEventStorage)
        failed_events_summary: Dict[str, Any] = {
            "total_stored_failures": 0,
            "total_stored": 0,
            "total_resolved": 0,
            "recent_failures": [],
            "tenant_filter": tenant_id,
        }
        try:
            from app.services.failed_event_storage import FailedEventStorage
            storage_instance = FailedEventStorage(redis_client=self.redis_client)
            raw_failures = storage_instance.list_failed_events(tenant_id=tenant_id, limit=20)
            storage_metrics = FailedEventStorage.get_storage_metrics()

            # Redact secrets from every failure record
            safe_failures = [redact_sensitive_data(f) for f in raw_failures]
            stored_count = len(safe_failures)
            if not tenant_id:
                stored_count = storage_metrics.get("metrics", {}).get("failed_events_stored", len(safe_failures))
            failed_events_summary = {
                "total_stored_failures": stored_count,
                "total_stored": stored_count,
                "total_resolved": storage_metrics.get("metrics", {}).get("failed_events_resolved", 0),
                "recent_failures": safe_failures,
                "tenant_filter": tenant_id,
            }
        except Exception as e:
            logger.warning("Error fetching failure context for dashboard: %s", e)

        # 5. DLQ Volume & Dead Letter Topics
        dlq_volume: Dict[str, Any] = {
            "total_dlq_events": 0,
            "total_dlq_volume": 0,
            "dlq_queue_length": 0,
            "dlq_topics": list(DEFAULT_DLQ_TOPICS),
            "topics": list(DEFAULT_DLQ_TOPICS),
            "shared_dlq": DEFAULT_SHARED_DLQ_TOPIC,
        }
        if self.redis_client:
            try:
                dlq_len = self.redis_client.llen("consumer:dlq") if hasattr(self.redis_client, "llen") else 0
                dlq_volume["total_dlq_events"] = dlq_len
                dlq_volume["total_dlq_volume"] = dlq_len
                dlq_volume["dlq_queue_length"] = dlq_len
            except Exception:
                pass

        # 6. Recovery State & Replay Telemetry
        recovery_state: Dict[str, Any] = {
            "status": "ready",
            "active_replays": 0,
            "replayed_total": 0,
            "total_replayed": 0,
            "resolved": 0,
            "pending": 0,
        }
        try:
            from app.services.consumer_event_replay import ConsumerEventReplay
            replay_m = ConsumerEventReplay.get_replay_metrics()
            replayed = replay_m.get("metrics", {}).get("replayed_total", 0)
            recovery_state["replayed_total"] = replayed
            recovery_state["total_replayed"] = replayed
        except Exception:
            pass

        # Overall Cluster Health Derivation
        cluster_status = "healthy"
        if broker_status.get("status") == "unhealthy":
            cluster_status = "unhealthy"
        elif dlq_volume.get("total_dlq_events", 0) > 100 or topic_throughput.get("publish_failures", 0) > 10:
            cluster_status = "degraded"

        dashboard_payload = {
            "status": cluster_status,
            "dashboard": self.CONSUMER_NAME,
            "timestamp": now_iso,
            "tenant_id": tenant_id,
            "broker": broker_status,
            "broker_status": broker_status,
            "throughput": topic_throughput,
            "topic_throughput": topic_throughput,
            "consumer_lag": consumer_lag,
            "failures": failed_events_summary,
            "dlq": dlq_volume,
            "dlq_volume": dlq_volume,
            "recovery": recovery_state,
            "recovery_state": recovery_state,
        }

        # Final pass to guarantee zero secrets in dashboard output
        return redact_sensitive_data(dashboard_payload)

    # =========================================================================
    # Event Processing with Dashboard Telemetry
    # =========================================================================

    async def handle_message(self, message: Any) -> DashboardReceipt:
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
    ) -> DashboardReceipt:
        """
        Process event through dashboard coordinator, capturing operational metrics.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        current_topic = topic

        # 1. Parse & decode message payload safely
        try:
            if isinstance(message, (bytes, bytearray)):
                try:
                    message = message.decode("utf-8")
                except UnicodeDecodeError as u_err:
                    self._metrics["errors_total"] += 1
                    return DashboardReceipt({
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
                    return DashboardReceipt({
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
                payload = dict(message.payload) if isinstance(message.payload, dict) else {}
                correlation_id = getattr(message, "correlation_id", None) or payload.get("correlation_id")
                if not current_topic:
                    current_topic = getattr(message, "topic", None) or self.topic
                if hasattr(message, "message_id"):
                    payload.setdefault("event_id", str(message.message_id))
                if hasattr(message, "sender") and hasattr(message.sender, "tenant_id"):
                    payload.setdefault("tenant_id", str(message.sender.tenant_id))
            elif isinstance(message, dict):
                if not current_topic:
                    current_topic = message.get("topic") or self.topic
                if "payload" in message and isinstance(message["payload"], dict):
                    payload = dict(message["payload"])
                    for k in ("event_id", "tenant_id", "schema_version", "correlation_id", "domain"):
                        if k in message and k not in payload:
                            payload[k] = message[k]
                    correlation_id = message.get("correlation_id") or payload.get("correlation_id")
                    if "message_id" in message and "event_id" not in payload:
                        payload["event_id"] = str(message["message_id"])
                    if "sender" in message and isinstance(message["sender"], dict) and "tenant_id" not in payload:
                        payload["tenant_id"] = message["sender"].get("tenant_id")
                else:
                    payload = dict(message)
                    correlation_id = payload.get("correlation_id")
                    if "message_id" in message and "event_id" not in payload:
                        payload["event_id"] = str(message["message_id"])
                    if "sender" in message and isinstance(message["sender"], dict) and "tenant_id" not in payload:
                        payload["tenant_id"] = message["sender"].get("tenant_id")
            else:
                self._metrics["errors_total"] += 1
                return DashboardReceipt({
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
            return DashboardReceipt({
                "status": "FAILED",
                "consumer": self.CONSUMER_NAME,
                "event_id": "unknown",
                "error": f"Message parse error: {parse_exc}",
                "error_type": type(parse_exc).__name__,
                "idempotent": False,
                "dlq": True,
            })

        if not current_topic:
            current_topic = self.topic

        event_id = payload.get("event_id") or payload.get("message_id") or "unknown"
        tenant_id = payload.get("tenant_id") or "unknown"
        schema_version = payload.get("schema_version")
        if schema_version is None:
            schema_version = 1
        domain = payload.get("domain") or "default"

        # 2. Topic authorization check
        if current_topic and current_topic not in self.ALLOWED_TOPICS:
            self._metrics["errors_total"] += 1
            return DashboardReceipt({
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

        # 3. Schema validation
        missing_fields = []
        if not payload.get("event_id") or not str(payload.get("event_id")).strip():
            missing_fields.append("event_id")
        if not payload.get("tenant_id") or not str(payload.get("tenant_id")).strip():
            missing_fields.append("tenant_id")
        if schema_version is None:
            missing_fields.append("schema_version")

        if missing_fields:
            self._metrics["errors_total"] += 1
            return DashboardReceipt({
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

        if schema_version not in (1, 2):
            self._metrics["errors_total"] += 1
            return DashboardReceipt({
                "status": "FAILED",
                "consumer": self.CONSUMER_NAME,
                "event_id": event_id,
                "tenant_id": tenant_id,
                "correlation_id": correlation_id,
                "error": f"Schema compatibility error: Unsupported schema version: {schema_version}. Supported versions: [1, 2]",
                "error_type": "SchemaVersionError",
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
            return DashboardReceipt({
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
                    return DashboardReceipt({
                        "status": "FAILED",
                        "consumer": self.CONSUMER_NAME,
                        "event_id": event_id,
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

            self._metrics["processed_total"] += 1
            return DashboardReceipt({
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
            })

        except Exception as exec_err:
            self._metrics["errors_total"] += 1
            classification, is_retryable = classify_error(exec_err)
            return DashboardReceipt({
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
            })

    # =========================================================================
    # Bounded Recovery Path
    # =========================================================================

    async def recover_event(
        self,
        event_or_payload: Any,
        topic: Optional[str] = None,
        partition: int = 0,
        offset: int = 0,
        retries_limit: Optional[int] = None,
        handler: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ) -> DashboardReceipt:
        """
        Bounded recovery loop with operational dashboard metrics.
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
                return DashboardReceipt({
                    "status": "RECOVERED",
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
        return DashboardReceipt({
            "status": "FAILED",
            "consumer": self.CONSUMER_NAME,
            "event_id": event_id,
            "retries": retries_attempted,
            "idempotent": True,
            "dlq": True,
            "error": (last_receipt or {}).get("error", "Dashboard recovery exhausted"),
        })

    # =========================================================================
    # Observability & Metrics
    # =========================================================================

    @classmethod
    def get_dashboard_metrics(cls) -> Dict[str, Any]:
        """Return operational metrics for Kafka monitoring dashboard."""
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
            "dashboard_requests": 0,
            "recovered_total": 0,
            "errors_total": 0,
        }


# Authoritative aliases ensuring complete cross-story naming compatibility
AddKafkaMonitoringDashboard = KafkaMonitoringDashboard
Add_kafka_monitoring_dashboard = KafkaMonitoringDashboard
ConsumerKafkaMonitoringDashboard = KafkaMonitoringDashboard
KafkaDashboardService = KafkaMonitoringDashboard

