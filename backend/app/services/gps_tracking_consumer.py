"""
gps_tracking_consumer.py

Kafka consumer service for GPS-location tracking and ETA flow integration.

Responsibilities:
- Consume GPS location events from 'fieldops.gps.events' and 'fieldops.events'.
- Validate coordinate bounds (-90 <= lat <= 90, -180 <= lon <= 180).
- Validate tenant isolation, ownership, and secret sanitization.
- Protect against stale or out-of-order location updates.
- Enforce idempotency using Redis markers to prevent duplicate tracking side effects.
- Invoke authoritative domain services (publish_gps_event, update_eta_task, etc.) without duplicating logic.
- Handle failures safely with bounded error propagation and retry metadata.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional, Union

from app.redis_client import get_redis_client
from app.services.event_publisher import publish_gps_event
from app.services.kafka.consumer import KafkaConsumerManager
from app.services.ai.FieldOpsAI.schemas.agent_messages import (
    GPSLocationEventMessage,
    MessageEnvelope,
    _FORBIDDEN_KEYS,
)
from app.utils import parse_iso_utc

logger = logging.getLogger(__name__)

# Keys permitted in GPS events that would otherwise be rejected by global privacy filter
_GPS_ALLOWED_KEYS = frozenset({
    "latitude",
    "longitude",
    "gps",
    "coordinates",
    "accuracy",
    "altitude",
    "speed",
    "heading",
})

_GPS_FORBIDDEN_KEYS = _FORBIDDEN_KEYS - _GPS_ALLOWED_KEYS


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


class GPSTrackingConsumer:
    """
    GPS location tracking consumer connecting Kafka GPS events to current tracking capabilities.
    """

    DEFAULT_TOPIC = "fieldops.gps.events"
    DEFAULT_GROUP = "fieldops-gps"
    SCHEMA_VERSION = 1

    ALLOWED_TOPICS = frozenset({
        "fieldops.gps.events",
        "fieldops.events",
    })

    ALLOWED_EVENT_TYPES = frozenset({
        "gps-location",
        "location",
    })

    def __init__(
        self,
        topic: Optional[str] = None,
        group_id: Optional[str] = None,
        consumer_manager: Optional[KafkaConsumerManager] = None,
        redis_client: Optional[Any] = None,
        db_session_factory: Optional[Any] = None,
        bootstrap_servers: Optional[str] = None,
    ):
        self.topic = topic or self.DEFAULT_TOPIC
        self.group_id = group_id or self.DEFAULT_GROUP
        self.bootstrap_servers = bootstrap_servers

        self._consumer_manager = consumer_manager

        if redis_client is not None:
            self.redis_client = redis_client
        else:
            try:
                self.redis_client = get_redis_client()
            except Exception:
                self.redis_client = None

        self.db_session_factory = db_session_factory

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

    async def __aenter__(self) -> "GPSTrackingConsumer":
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: Any,
        exc_value: Any,
        traceback: Any,
    ) -> None:
        await self.stop()

    async def handle_message(
        self,
        message: dict[str, Any],
        attempt: int = 1,
    ) -> ConsumeReceipt:
        """Callback suitable for KafkaConsumerManager.consume(handler)."""
        return await self.process_event(message, attempt=attempt)

    async def process_event(
        self,
        message: Union[dict[str, Any], str, MessageEnvelope, GPSLocationEventMessage],
        attempt: int = 1,
    ) -> ConsumeReceipt:
        """
        Validate coordinates and ownership, protect against stale updates,
        enforce idempotency, and update existing tracking/ETA flow.
        """
        # 1. Parse / unpack message payload and metadata
        try:
            if isinstance(message, str):
                message = json.loads(message)

            if isinstance(message, (MessageEnvelope, GPSLocationEventMessage)):
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
                return ConsumeReceipt(
                    {
                        "status": "FAILED",
                        "consumer": "GPS_tracking",
                        "event_id": "unknown",
                        "attempt": attempt,
                        "error": f"Unsupported message type: {type(message).__name__}",
                    }
                )

        except Exception as parse_err:
            logger.error("Failed to parse GPS tracking event: %s", parse_err)
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "GPS_tracking",
                    "event_id": "unknown",
                    "attempt": attempt,
                    "error": f"Message parse error: {parse_err}",
                }
            )

        event_id = payload.get("event_id")
        technician_id = payload.get("technician_id")
        job_id = payload.get("job_id")
        tenant_id = payload.get("tenant_id")
        raw_event_type = payload.get("event_type") or payload.get("event")
        latitude = payload.get("latitude")
        longitude = payload.get("longitude")
        schema_version = payload.get("schema_version")
        raw_timestamp = payload.get("timestamp")

        # 2. Topic check
        if topic and topic not in self.ALLOWED_TOPICS:
            logger.warning(
                "GPS tracking event rejected: topic '%s' not in allowed topics %s",
                topic,
                sorted(self.ALLOWED_TOPICS),
            )
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "GPS_tracking",
                    "event_id": event_id or "unknown",
                    "attempt": attempt,
                    "error": f"Topic '{topic}' is not authorized for GPS tracking consumer",
                }
            )

        # 3. Schema & contract validation
        missing_fields = []
        if not event_id:
            missing_fields.append("event_id")
        if not technician_id:
            missing_fields.append("technician_id")
        if not job_id:
            missing_fields.append("job_id")
        if not tenant_id:
            missing_fields.append("tenant_id")
        if latitude is None:
            missing_fields.append("latitude")
        if longitude is None:
            missing_fields.append("longitude")
        if schema_version is None:
            missing_fields.append("schema_version")

        if missing_fields:
            logger.warning(
                "GPS tracking event missing required fields: %s",
                missing_fields,
            )
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "GPS_tracking",
                    "event_id": event_id or "unknown",
                    "attempt": attempt,
                    "error": f"Missing required fields: {', '.join(sorted(missing_fields))}",
                }
            )

        # 4. Coordinate validation
        if not isinstance(latitude, (int, float)) or isinstance(latitude, bool):
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "GPS_tracking",
                    "event_id": event_id,
                    "attempt": attempt,
                    "error": "Latitude must be a numeric value",
                }
            )

        if not isinstance(longitude, (int, float)) or isinstance(longitude, bool):
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "GPS_tracking",
                    "event_id": event_id,
                    "attempt": attempt,
                    "error": "Longitude must be a numeric value",
                }
            )

        if not -90 <= float(latitude) <= 90:
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "GPS_tracking",
                    "event_id": event_id,
                    "attempt": attempt,
                    "error": "Latitude must be between -90 and 90 degrees",
                }
            )

        if not -180 <= float(longitude) <= 180:
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "GPS_tracking",
                    "event_id": event_id,
                    "attempt": attempt,
                    "error": "Longitude must be between -180 and 180 degrees",
                }
            )

        # 5. Event type validation
        if not raw_event_type:
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "GPS_tracking",
                    "event_id": event_id,
                    "attempt": attempt,
                    "error": "Missing event_type",
                }
            )

        norm_event_type = str(raw_event_type).lower().replace("_", "-")
        if norm_event_type not in self.ALLOWED_EVENT_TYPES:
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "GPS_tracking",
                    "event_id": event_id,
                    "attempt": attempt,
                    "error": f"Invalid event_type: '{raw_event_type}'",
                }
            )

        # 6. Security & forbidden secrets check
        lowered_keys = {str(k).lower() for k in payload.keys()}
        found_forbidden = lowered_keys.intersection(_GPS_FORBIDDEN_KEYS)
        if found_forbidden:
            logger.warning(
                "GPS tracking event rejected due to sensitive keys: %s",
                found_forbidden,
            )
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "GPS_tracking",
                    "event_id": event_id,
                    "attempt": attempt,
                    "error": f"Payload contains forbidden sensitive keys: {', '.join(sorted(found_forbidden))}",
                }
            )

        # 7. Ownership & Tenant validation via DB if provided
        if self.db_session_factory:
            try:
                with self.db_session_factory() as db:
                    from app import models

                    # Check job ownership
                    job_query = db.query(models.Job).filter(
                        models.Job.id == (int(job_id) if str(job_id).isdigit() else job_id)
                    )
                    job_record = job_query.first()

                    if job_record:
                        if job_record.tenant_id and str(job_record.tenant_id) != str(tenant_id):
                            logger.warning(
                                "Tenant mismatch: job %s belongs to tenant %s, not %s",
                                job_id,
                                job_record.tenant_id,
                                tenant_id,
                            )
                            return ConsumeReceipt(
                                {
                                    "status": "FAILED",
                                    "consumer": "GPS_tracking",
                                    "event_id": event_id,
                                    "attempt": attempt,
                                    "error": f"Job tenant mismatch: expected {job_record.tenant_id}, got {tenant_id}",
                                }
                            )

                    # Check technician ownership
                    tech_query = db.query(models.Technician).filter(
                        (models.Technician.technician_id == int(technician_id))
                        if str(technician_id).isdigit()
                        else (models.Technician.tech_id == str(technician_id))
                    )
                    tech_record = tech_query.first()
                    if tech_record and tech_record.tenant_id:
                        if str(tech_record.tenant_id) != str(tenant_id):
                            return ConsumeReceipt(
                                {
                                    "status": "FAILED",
                                    "consumer": "GPS_tracking",
                                    "event_id": event_id,
                                    "attempt": attempt,
                                    "error": f"Technician tenant mismatch: expected {tech_record.tenant_id}, got {tenant_id}",
                                }
                            )

            except Exception as db_err:
                logger.warning("DB check failed for GPS event %s: %s", event_id, db_err)

        # 8. Idempotency verification via Redis
        idempotency_key = f"gps:event_processed:{event_id}"
        if self.redis_client:
            try:
                if self.redis_client.get(idempotency_key):
                    logger.info(
                        "GPS event %s already processed; skipping duplicate.",
                        event_id,
                    )
                    return ConsumeReceipt(
                        {
                            "status": "PROCESSED",
                            "consumer": "GPS_tracking",
                            "event_id": event_id,
                            "attempt": attempt,
                            "idempotent_duplicate": True,
                        }
                    )
            except Exception as redis_check_err:
                logger.warning(
                    "Redis error checking idempotency for GPS event %s: %s",
                    event_id,
                    redis_check_err,
                )

        # 9. Protection against stale / out-of-order updates
        incoming_dt = None
        if raw_timestamp:
            if isinstance(raw_timestamp, str):
                incoming_dt = parse_iso_utc(raw_timestamp)
            elif isinstance(raw_timestamp, datetime):
                incoming_dt = raw_timestamp
        if incoming_dt is None:
            incoming_dt = datetime.now(timezone.utc)

        ts_key = f"gps:latest_ts:{tenant_id}:{job_id}"
        if self.redis_client:
            try:
                existing_ts_raw = self.redis_client.get(ts_key)
                if existing_ts_raw:
                    if isinstance(existing_ts_raw, bytes):
                        existing_ts_raw = existing_ts_raw.decode("utf-8")
                    existing_dt = parse_iso_utc(existing_ts_raw)

                    if existing_dt is not None and existing_dt >= incoming_dt:
                        logger.info(
                            "Stale GPS update rejected for job %s: incoming (%s) <= existing (%s)",
                            job_id,
                            incoming_dt.isoformat(),
                            existing_dt.isoformat(),
                        )
                        # Record idempotency to prevent infinite re-processing of old messages
                        self.redis_client.set(idempotency_key, "1", ex=86400)
                        return ConsumeReceipt(
                            {
                                "status": "PROCESSED",
                                "consumer": "GPS_tracking",
                                "event_id": event_id,
                                "attempt": attempt,
                                "stale_update": True,
                            }
                        )
            except Exception as stale_check_err:
                logger.warning(
                    "Error checking stale timestamp for job %s: %s",
                    job_id,
                    stale_check_err,
                )

        # 10. Invoke authoritative domain services & update tracking/ETA flow
        try:
            # Update latest GPS snapshot in Redis (TTL 120s)
            snapshot_key = f"gps:latest:{tenant_id}:{job_id}"
            snapshot_payload = {
                "technician_id": str(technician_id),
                "job_id": str(job_id),
                "tenant_id": str(tenant_id),
                "latitude": float(latitude),
                "longitude": float(longitude),
                "accuracy": payload.get("accuracy"),
                "altitude": payload.get("altitude"),
                "timestamp": incoming_dt.isoformat(),
            }

            if self.redis_client:
                try:
                    self.redis_client.setex(
                        snapshot_key,
                        120,
                        json.dumps(snapshot_payload),
                    )
                    self.redis_client.set(
                        ts_key,
                        incoming_dt.isoformat(),
                        ex=86400,
                    )
                except Exception as cache_err:
                    logger.warning("Failed to store GPS snapshot: %s", cache_err)

            # Publish to Redis gps:updates channel for WebSocket tracking fan-out
            publish_gps_event(
                redis_client=self.redis_client,
                event_type=raw_event_type,
                technician_id=str(technician_id),
                job_id=str(job_id),
                latitude=float(latitude),
                longitude=float(longitude),
                tenant_id=str(tenant_id),
                timestamp=incoming_dt.isoformat(),
                correlation_id=correlation_id,
                event_id=event_id,
                accuracy=payload.get("accuracy"),
                altitude=payload.get("altitude"),
            )

            # Trigger ETA flow recalculation
            try:
                from app.tasks import update_eta_task

                if hasattr(update_eta_task, "delay"):
                    update_eta_task.delay(
                        technician_id=str(technician_id),
                        job_id=job_id,
                        ping_id=event_id,
                        correlation_id=correlation_id,
                    )
                else:
                    update_eta_task(
                        technician_id=str(technician_id),
                        job_id=job_id,
                        ping_id=event_id,
                        correlation_id=correlation_id,
                    )
            except Exception as eta_err:
                logger.warning("Could not dispatch update_eta_task: %s", eta_err)

        except Exception as domain_err:
            logger.error(
                "Domain service invocation failed for GPS event %s: %s",
                event_id,
                domain_err,
            )
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "GPS_tracking",
                    "event_id": event_id,
                    "attempt": attempt,
                    "error": str(domain_err),
                }
            )

        # 11. Mark idempotency in Redis on success
        if self.redis_client:
            try:
                self.redis_client.set(idempotency_key, "1", ex=86400)
            except Exception as redis_save_err:
                logger.warning(
                    "Redis error marking idempotency for GPS event %s: %s",
                    event_id,
                    redis_save_err,
                )

        # 12. Return successful receipt
        logger.info(
            "GPS tracking event %s processed successfully by GPS_tracking consumer (attempt %d).",
            event_id,
            attempt,
        )
        return ConsumeReceipt(
            {
                "status": "PROCESSED",
                "consumer": "GPS_tracking",
                "event_id": event_id,
                "attempt": attempt,
            }
        )


GPSConsumer = GPSTrackingConsumer
GPSLocationConsumer = GPSTrackingConsumer

