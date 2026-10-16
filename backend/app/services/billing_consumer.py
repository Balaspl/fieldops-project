"""
billing_consumer.py

Kafka consumer service for invoice and billing events.

Responsibilities:
- Consume invoice and billing events from 'fieldops.billing.events' and 'fieldops.events'.
- Validate invoice identifiers, persisted financial state, tenant context, schema, and privacy safety (no secrets).
- Enforce idempotency using Redis markers to prevent duplicate ERP / billing syncs.
- Invoke authoritative source-of-truth services (ERP integration, event_publisher, DB persistence)
  without duplicating billing calculations.
- Handle failures safely with bounded error propagation and retry metadata.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional, Union

from app.redis_client import get_redis_client
from app.services.event_publisher import publish_invoice_event
from app.services.kafka.consumer import KafkaConsumerManager
from app.services.ai.FieldOpsAI.schemas.agent_messages import (
    MessageEnvelope,
    InvoiceEventMessage,
    _FORBIDDEN_KEYS,
)

logger = logging.getLogger(__name__)


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


class BillingConsumer:
    """
    Billing and invoice event consumer for Kafka event stream processing.
    """

    DEFAULT_TOPIC = "fieldops.billing.events"
    DEFAULT_GROUP = "fieldops-billing"
    SCHEMA_VERSION = 1

    ALLOWED_TOPICS = frozenset({
        "fieldops.billing.events",
        "fieldops.events",
    })

    ALLOWED_EVENT_TYPES = frozenset({
        "invoice",
        "billing",
        "invoice-generated",
        "invoice_generated",
        "invoice-created",
        "invoice_created",
        "invoice-updated",
        "invoice_updated",
        "invoice-paid",
        "invoice_paid",
        "invoice-voided",
        "invoice_voided",
        "invoice-cancelled",
        "invoice_cancelled",
        "invoice-synced",
        "invoice_synced",
        "billing-synced",
        "billing_synced",
        "erp-synced",
        "erp_synced",
    })

    VALID_FINANCIAL_STATUSES = frozenset({
        "draft",
        "pending",
        "issued",
        "paid",
        "partial",
        "voided",
        "cancelled",
        "refunded",
        "overdue",
        "synced",
        "completed",
    })

    def __init__(
        self,
        topic: Optional[str] = None,
        group_id: Optional[str] = None,
        consumer_manager: Optional[KafkaConsumerManager] = None,
        redis_client: Optional[Any] = None,
        erp_client: Optional[Any] = None,
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

        self.erp_client = erp_client
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

    async def __aenter__(self) -> "BillingConsumer":
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
        message: Union[dict[str, Any], str, MessageEnvelope, InvoiceEventMessage],
        attempt: int = 1,
    ) -> ConsumeReceipt:
        """
        Validate invoice identifiers, financial state, tenant metadata, enforce idempotency,
        and connect to billing/ERP workflows.
        """
        # 1. Parse / unpack message payload and metadata
        try:
            if isinstance(message, str):
                message = json.loads(message)

            if isinstance(message, (MessageEnvelope, InvoiceEventMessage)):
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
                        "consumer": "billing",
                        "event_id": "unknown",
                        "attempt": attempt,
                        "error": f"Unsupported message type: {type(message).__name__}",
                    }
                )

        except Exception as parse_err:
            logger.error("Failed to parse billing event: %s", parse_err)
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "billing",
                    "event_id": "unknown",
                    "attempt": attempt,
                    "error": f"Message parse error: {parse_err}",
                }
            )

        event_id = payload.get("event_id")
        job_id = payload.get("job_id") or payload.get("jobId")
        tenant_id = payload.get("tenant_id")
        raw_event_type = payload.get("event_type") or payload.get("event")
        schema_version = payload.get("schema_version")
        invoice_id = (
            payload.get("invoice_id")
            or payload.get("invoiceId")
            or payload.get("inv_id")
        )
        amount_raw = (
            payload.get("amount")
            if "amount" in payload
            else (payload.get("total") if "total" in payload else payload.get("subtotal"))
        )
        currency_raw = payload.get("currency")
        financial_status_raw = (
            payload.get("financial_status")
            or payload.get("payment_status")
            or payload.get("invoice_status")
            or payload.get("status")
        )

        # 2. Topic check
        if topic and topic not in self.ALLOWED_TOPICS:
            logger.warning(
                "Billing event rejected: topic '%s' not in allowed topics %s",
                topic,
                sorted(self.ALLOWED_TOPICS),
            )
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "billing",
                    "event_id": event_id or "unknown",
                    "attempt": attempt,
                    "error": f"Topic '{topic}' is not authorized for billing consumer",
                }
            )

        # 3. Schema & contract validation
        missing_fields = []
        if not event_id:
            missing_fields.append("event_id")
        if not job_id:
            missing_fields.append("job_id")
        if not tenant_id:
            missing_fields.append("tenant_id")
        if schema_version is None:
            missing_fields.append("schema_version")

        if missing_fields:
            logger.warning(
                "Billing event missing required fields: %s",
                missing_fields,
            )
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "billing",
                    "event_id": event_id or "unknown",
                    "attempt": attempt,
                    "error": f"Missing required fields: {', '.join(sorted(missing_fields))}",
                }
            )

        # 4. Validate invoice identifiers and persisted financial state (Requirement 1)
        # 4a. Validate invoice identifier
        if not invoice_id or not str(invoice_id).strip():
            logger.warning(
                "Billing event rejected: missing or blank invoice identifier for event %s",
                event_id,
            )
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "billing",
                    "event_id": event_id,
                    "attempt": attempt,
                    "error": "Missing or invalid invoice identifier (invoice_id)",
                }
            )

        # 4b. Validate financial state: amount non-negative & numeric
        if amount_raw is not None:
            if not isinstance(amount_raw, (int, float)) or isinstance(amount_raw, bool):
                return ConsumeReceipt(
                    {
                        "status": "FAILED",
                        "consumer": "billing",
                        "event_id": event_id,
                        "attempt": attempt,
                        "error": "Invalid financial state: invoice amount must be a numeric value",
                    }
                )
            if float(amount_raw) < 0:
                return ConsumeReceipt(
                    {
                        "status": "FAILED",
                        "consumer": "billing",
                        "event_id": event_id,
                        "attempt": attempt,
                        "error": "Invalid financial state: invoice amount cannot be negative",
                    }
                )

        # 4c. Validate financial state: currency format (e.g. 3-letter code)
        if currency_raw is not None:
            norm_currency = str(currency_raw).strip().upper()
            if len(norm_currency) != 3 or not norm_currency.isalpha():
                return ConsumeReceipt(
                    {
                        "status": "FAILED",
                        "consumer": "billing",
                        "event_id": event_id,
                        "attempt": attempt,
                        "error": f"Invalid currency code: '{currency_raw}'",
                    }
                )

        # 4d. Validate financial status if provided
        if financial_status_raw is not None:
            norm_status = str(financial_status_raw).strip().lower()
            if norm_status not in self.VALID_FINANCIAL_STATUSES:
                return ConsumeReceipt(
                    {
                        "status": "FAILED",
                        "consumer": "billing",
                        "event_id": event_id,
                        "attempt": attempt,
                        "error": f"Invalid financial status: '{financial_status_raw}'",
                    }
                )

        # 4e. Database persisted state check (if session factory configured)
        if self.db_session_factory:
            try:
                db = self.db_session_factory()
                try:
                    from app.models.job_closure import JobClosure
                    job_int = int(job_id) if str(job_id).isdigit() else None
                    if job_int is not None:
                        closure = db.query(JobClosure).filter(JobClosure.job_id == job_int).first()
                        if closure and closure.tenant_id != str(tenant_id):
                            return ConsumeReceipt(
                                {
                                    "status": "FAILED",
                                    "consumer": "billing",
                                    "event_id": event_id,
                                    "attempt": attempt,
                                    "error": "Tenant mismatch between event and persisted job closure",
                                }
                            )
                finally:
                    db.close()
            except Exception as db_err:
                logger.warning("DB validation check failed for billing event %s: %s", event_id, db_err)

        # 5. Event type validation
        if not raw_event_type:
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "billing",
                    "event_id": event_id,
                    "attempt": attempt,
                    "error": "Missing event_type",
                }
            )

        norm_event_type = str(raw_event_type).lower().replace("_", "-")
        normalized_allowed = {
            et.lower().replace("_", "-") for et in self.ALLOWED_EVENT_TYPES
        }

        if norm_event_type not in normalized_allowed:
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "billing",
                    "event_id": event_id,
                    "attempt": attempt,
                    "error": f"Invalid event_type: '{raw_event_type}'",
                }
            )

        # 6. Security & forbidden secrets check
        lowered_keys = {str(k).lower() for k in payload.keys()}
        found_forbidden = lowered_keys.intersection(_FORBIDDEN_KEYS)
        if found_forbidden:
            logger.warning(
                "Billing event rejected due to sensitive keys: %s",
                found_forbidden,
            )
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "billing",
                    "event_id": event_id,
                    "attempt": attempt,
                    "error": f"Payload contains forbidden sensitive keys: {', '.join(sorted(found_forbidden))}",
                }
            )

        # 7. Idempotency verification via Redis
        idempotency_key = f"billing:event_processed:{event_id}"
        if self.redis_client:
            try:
                if self.redis_client.get(idempotency_key):
                    logger.info(
                        "Billing event %s already processed; skipping duplicate.",
                        event_id,
                    )
                    return ConsumeReceipt(
                        {
                            "status": "PROCESSED",
                            "consumer": "billing",
                            "event_id": event_id,
                            "attempt": attempt,
                            "idempotent_duplicate": True,
                        }
                    )
            except Exception as redis_check_err:
                logger.warning(
                    "Redis error checking idempotency for billing event %s: %s",
                    event_id,
                    redis_check_err,
                )

        # 8. Invoke authoritative domain services & ERP workflows
        try:
            job_id_str = str(job_id)
            invoice_id_str = str(invoice_id)

            # Invoke ERP integration if client provided
            if self.erp_client:
                import inspect
                sync_fn = getattr(self.erp_client, "sync_invoice", None) or getattr(self.erp_client, "process_billing_event", None)
                if sync_fn:
                    if inspect.iscoroutinefunction(sync_fn):
                        await sync_fn(
                            invoice_id=invoice_id_str,
                            job_id=job_id_str,
                            tenant_id=str(tenant_id),
                            amount=float(amount_raw) if amount_raw is not None else None,
                            currency=str(currency_raw) if currency_raw is not None else None,
                            payload=payload,
                        )
                    else:
                        sync_fn(
                            invoice_id=invoice_id_str,
                            job_id=job_id_str,
                            tenant_id=str(tenant_id),
                            amount=float(amount_raw) if amount_raw is not None else None,
                            currency=str(currency_raw) if currency_raw is not None else None,
                            payload=payload,
                        )

            # Publish canonical invoice/billing event to Redis channel for real-time WebSocket coordination
            publish_invoice_event(
                redis_client=self.redis_client,
                event_type=raw_event_type,
                job_id=job_id_str,
                tenant_id=str(tenant_id),
                invoice_id=invoice_id_str,
                correlation_id=correlation_id,
                event_id=event_id,
                payload=payload,
            )

        except Exception as domain_err:
            logger.error(
                "Billing / ERP workflow invocation failed for event %s: %s",
                event_id,
                domain_err,
            )
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "billing",
                    "event_id": event_id,
                    "attempt": attempt,
                    "error": f"Billing / ERP workflow failure: {domain_err}",
                }
            )

        # 9. Enforce idempotency after successful processing
        if self.redis_client:
            try:
                self.redis_client.set(idempotency_key, "1", ex=7 * 24 * 60 * 60)
            except Exception as redis_set_err:
                logger.warning(
                    "Redis error saving idempotency marker for billing event %s: %s",
                    event_id,
                    redis_set_err,
                )

        logger.info(
            "Successfully processed billing event %s for invoice %s (job %s)",
            event_id,
            invoice_id,
            job_id,
        )

        return ConsumeReceipt(
            {
                "status": "PROCESSED",
                "consumer": "billing",
                "event_id": event_id,
                "attempt": attempt,
            }
        )


# Aliases for flexible integration
InvoiceConsumer = BillingConsumer
BillingEventConsumer = BillingConsumer

