"""
payment_consumer.py

Kafka consumer service for payment lifecycle and financial transaction events.

Responsibilities:
- Consume payment events from 'fieldops.payment.events' and 'fieldops.events'.
- Validate transaction identity (payment_id / transaction_id), persisted financial state
  (numeric non-negative amount, valid 3-letter currency), tenant context, and schema.
- Enforce strict idempotency via Redis markers to prevent duplicate financial processing.
- Coordinate with downstream accounting / payment workflows and Redis pub/sub ('payment_events')
  without duplicating financial business logic.
- Support safe retry and recovery with bounded failure reporting.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional, Union

from app.redis_client import get_redis_client
from app.services.event_publisher import publish_payment_event
from app.services.kafka.consumer import KafkaConsumerManager
from app.services.ai.FieldOpsAI.schemas.agent_messages import (
    MessageEnvelope,
    PaymentEventMessage,
    _FORBIDDEN_KEYS,
)

logger = logging.getLogger(__name__)


class ConsumeReceipt(dict):
    """
    Structured dictionary receipt returned after consuming/processing a payment event.
    Evaluates to True if status is 'PROCESSED'.
    """

    @property
    def is_success(self) -> bool:
        return self.get("status") == "PROCESSED"

    def __bool__(self) -> bool:
        return self.is_success


class PaymentConsumer:
    """
    Payment and financial transaction consumer for Kafka event stream processing.
    """

    DEFAULT_TOPIC = "fieldops.payment.events"
    DEFAULT_GROUP = "fieldops-payment"
    SCHEMA_VERSION = 1

    ALLOWED_TOPICS = frozenset({
        "fieldops.payment.events",
        "fieldops.events",
    })

    ALLOWED_EVENT_TYPES = frozenset({
        "payment",
        "payment-initiated",
        "payment_initiated",
        "payment-success",
        "payment_success",
        "payment-successful",
        "payment_successful",
        "payment-failed",
        "payment_failed",
        "payment-pending",
        "payment_pending",
        "payment-refunded",
        "payment_refunded",
        "payment-refund",
        "payment_refund",
        "payment-completed",
        "payment_completed",
        "payment-cancelled",
        "payment_cancelled",
    })

    VALID_PAYMENT_STATUSES = frozenset({
        "pending",
        "successful",
        "success",
        "failed",
        "unavailable",
        "refunded",
        "refund",
        "initiated",
        "completed",
        "cancelled",
    })

    def __init__(
        self,
        topic: Optional[str] = None,
        group_id: Optional[str] = None,
        consumer_manager: Optional[KafkaConsumerManager] = None,
        redis_client: Optional[Any] = None,
        accounting_client: Optional[Any] = None,
        payment_service: Optional[Any] = None,
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

        self.accounting_client = accounting_client
        self.payment_service = payment_service
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

    async def __aenter__(self) -> "PaymentConsumer":
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
        message: Union[dict[str, Any], str, MessageEnvelope, PaymentEventMessage],
        attempt: int = 1,
    ) -> ConsumeReceipt:
        """
        Validate transaction identity, financial state, tenant context, enforce idempotency,
        and update downstream payment/accounting workflows.
        """
        # 1. Parse / unpack message payload and metadata
        try:
            if isinstance(message, str):
                message = json.loads(message)

            if isinstance(message, (MessageEnvelope, PaymentEventMessage)):
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
                        "consumer": "payment",
                        "event_id": "unknown",
                        "attempt": attempt,
                        "error": f"Unsupported message type: {type(message).__name__}",
                    }
                )

        except Exception as parse_err:
            logger.error("Failed to parse payment event: %s", parse_err)
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "payment",
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
        payment_id = (
            payload.get("payment_id")
            or payload.get("paymentId")
            or payload.get("pay_id")
            or payload.get("transaction_id")
            or payload.get("transactionId")
            or payload.get("txn_id")
        )
        invoice_id = payload.get("invoice_id") or payload.get("invoiceId")
        amount_raw = (
            payload.get("amount")
            if "amount" in payload
            else (payload.get("total") if "total" in payload else payload.get("subtotal"))
        )
        currency_raw = payload.get("currency")
        payment_status_raw = (
            payload.get("payment_status")
            or payload.get("transaction_status")
            or payload.get("status")
        )

        # 2. Topic check
        if topic and topic not in self.ALLOWED_TOPICS:
            logger.warning(
                "Payment event rejected: topic '%s' not in allowed topics %s",
                topic,
                sorted(self.ALLOWED_TOPICS),
            )
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "payment",
                    "event_id": event_id or "unknown",
                    "attempt": attempt,
                    "error": f"Topic '{topic}' is not authorized for payment consumer",
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
                "Payment event missing required fields: %s",
                missing_fields,
            )
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "payment",
                    "event_id": event_id or "unknown",
                    "attempt": attempt,
                    "error": f"Missing required fields: {', '.join(sorted(missing_fields))}",
                }
            )

        # 4. Validate transaction identity and financial state (Requirement 1)
        # 4a. Validate transaction/payment identifier
        if not payment_id or not str(payment_id).strip():
            logger.warning(
                "Payment event rejected: missing or blank transaction identifier for event %s",
                event_id,
            )
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "payment",
                    "event_id": event_id,
                    "attempt": attempt,
                    "error": "Missing or invalid transaction/payment identifier (payment_id / transaction_id)",
                }
            )

        # 4b. Validate financial state: amount non-negative & numeric
        if amount_raw is not None:
            if not isinstance(amount_raw, (int, float)) or isinstance(amount_raw, bool):
                return ConsumeReceipt(
                    {
                        "status": "FAILED",
                        "consumer": "payment",
                        "event_id": event_id,
                        "attempt": attempt,
                        "error": "Invalid financial state: payment amount must be a numeric value",
                    }
                )
            if float(amount_raw) < 0:
                return ConsumeReceipt(
                    {
                        "status": "FAILED",
                        "consumer": "payment",
                        "event_id": event_id,
                        "attempt": attempt,
                        "error": "Invalid financial state: payment amount cannot be negative",
                    }
                )

        # 4c. Validate financial state: currency format (e.g. 3-letter code)
        if currency_raw is not None:
            norm_currency = str(currency_raw).strip().upper()
            if len(norm_currency) != 3 or not norm_currency.isalpha():
                return ConsumeReceipt(
                    {
                        "status": "FAILED",
                        "consumer": "payment",
                        "event_id": event_id,
                        "attempt": attempt,
                        "error": f"Invalid currency code: '{currency_raw}'",
                    }
                )

        # 4d. Validate payment status if provided
        if payment_status_raw is not None:
            norm_status = str(payment_status_raw).strip().lower()
            if norm_status not in self.VALID_PAYMENT_STATUSES:
                return ConsumeReceipt(
                    {
                        "status": "FAILED",
                        "consumer": "payment",
                        "event_id": event_id,
                        "attempt": attempt,
                        "error": f"Invalid payment status: '{payment_status_raw}'",
                    }
                )

        # 4e. Database persisted state check & update (if session factory configured)
        if self.db_session_factory:
            try:
                db = self.db_session_factory()
                try:
                    from app.models.payment_status import JobPaymentStatus
                    job_int = int(job_id) if str(job_id).isdigit() else None
                    if job_int is not None:
                        existing_status = (
                            db.query(JobPaymentStatus)
                            .filter(
                                JobPaymentStatus.job_id == job_int,
                            )
                            .first()
                        )
                        if existing_status and str(existing_status.tenant_id) != str(tenant_id):
                            return ConsumeReceipt(
                                {
                                    "status": "FAILED",
                                    "consumer": "payment",
                                    "event_id": event_id,
                                    "attempt": attempt,
                                    "error": "Tenant mismatch between event and persisted job payment record",
                                }
                            )

                        # Update or insert authoritative payment status in DB
                        canonical_db_status = "SUCCESSFUL"
                        if payment_status_raw is not None:
                            ps_lower = str(payment_status_raw).strip().lower()
                            if ps_lower in {"pending", "initiated"}:
                                canonical_db_status = "PENDING"
                            elif ps_lower in {"failed", "cancelled"}:
                                canonical_db_status = "FAILED"
                            elif ps_lower in {"success", "successful", "completed"}:
                                canonical_db_status = "SUCCESSFUL"
                            elif ps_lower in {"refunded", "refund"}:
                                canonical_db_status = "REFUNDED"
                            else:
                                canonical_db_status = "UNAVAILABLE"

                        inv_int = (
                            int(invoice_id)
                            if invoice_id is not None and str(invoice_id).isdigit()
                            else None
                        )

                        if existing_status:
                            existing_status.status = canonical_db_status
                            if inv_int is not None:
                                existing_status.invoice_id = inv_int
                        else:
                            new_status = JobPaymentStatus(
                                job_id=job_int,
                                invoice_id=inv_int,
                                tenant_id=str(tenant_id),
                                status=canonical_db_status,
                            )
                            db.add(new_status)
                        db.commit()

                finally:
                    db.close()
            except Exception as db_err:
                logger.warning(
                    "DB validation check failed for payment event %s: %s",
                    event_id,
                    db_err,
                )

        # 5. Event type validation
        if not raw_event_type:
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "payment",
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
                    "consumer": "payment",
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
                "Payment event rejected due to sensitive keys: %s",
                found_forbidden,
            )
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "payment",
                    "event_id": event_id,
                    "attempt": attempt,
                    "error": f"Payload contains forbidden sensitive keys: {', '.join(sorted(found_forbidden))}",
                }
            )

        # 7. Idempotency verification via Redis (Requirement 1: prevent duplicate financial processing)
        event_idempotency_key = f"payment:event_processed:{event_id}"
        txn_idempotency_key = f"payment:txn_processed:{payment_id}"
        if self.redis_client:
            try:
                if (
                    self.redis_client.get(event_idempotency_key)
                    or self.redis_client.get(txn_idempotency_key)
                ):
                    logger.info(
                        "Payment event %s (transaction %s) already processed; skipping duplicate.",
                        event_id,
                        payment_id,
                    )
                    return ConsumeReceipt(
                        {
                            "status": "PROCESSED",
                            "consumer": "payment",
                            "event_id": event_id,
                            "attempt": attempt,
                            "idempotent_duplicate": True,
                        }
                    )
            except Exception as redis_check_err:
                logger.warning(
                    "Redis error checking idempotency for payment event %s: %s",
                    event_id,
                    redis_check_err,
                )

        # 8. Invoke authoritative domain services & accounting workflows
        try:
            job_id_str = str(job_id)
            payment_id_str = str(payment_id)
            tenant_id_str = str(tenant_id)

            # Invoke accounting integration if client provided
            if self.accounting_client:
                import inspect
                sync_fn = (
                    getattr(self.accounting_client, "sync_payment", None)
                    or getattr(self.accounting_client, "record_payment", None)
                    or getattr(self.accounting_client, "process_payment_event", None)
                )
                if sync_fn:
                    if inspect.iscoroutinefunction(sync_fn):
                        await sync_fn(
                            payment_id=payment_id_str,
                            job_id=job_id_str,
                            tenant_id=tenant_id_str,
                            amount=float(amount_raw) if amount_raw is not None else None,
                            currency=str(currency_raw) if currency_raw is not None else None,
                            status=str(payment_status_raw) if payment_status_raw is not None else "SUCCESSFUL",
                            payload=payload,
                        )
                    else:
                        sync_fn(
                            payment_id=payment_id_str,
                            job_id=job_id_str,
                            tenant_id=tenant_id_str,
                            amount=float(amount_raw) if amount_raw is not None else None,
                            currency=str(currency_raw) if currency_raw is not None else None,
                            status=str(payment_status_raw) if payment_status_raw is not None else "SUCCESSFUL",
                            payload=payload,
                        )

            # Invoke domain payment service if provided
            if self.payment_service:
                import inspect
                process_fn = (
                    getattr(self.payment_service, "process_payment", None)
                    or getattr(self.payment_service, "update_payment_status", None)
                )
                if process_fn:
                    if inspect.iscoroutinefunction(process_fn):
                        await process_fn(
                            payment_id=payment_id_str,
                            job_id=job_id_str,
                            tenant_id=tenant_id_str,
                            payload=payload,
                        )
                    else:
                        process_fn(
                            payment_id=payment_id_str,
                            job_id=job_id_str,
                            tenant_id=tenant_id_str,
                            payload=payload,
                        )

            # Publish canonical payment event to Redis channel for real-time WebSocket coordination
            publish_payment_event(
                redis_client=self.redis_client,
                event_type=raw_event_type,
                job_id=job_id_str,
                tenant_id=tenant_id_str,
                payment_id=payment_id_str,
                correlation_id=correlation_id,
                event_id=event_id,
                payload=payload,
            )

        except Exception as domain_err:
            logger.error(
                "Payment / accounting workflow invocation failed for event %s: %s",
                event_id,
                domain_err,
            )
            return ConsumeReceipt(
                {
                    "status": "FAILED",
                    "consumer": "payment",
                    "event_id": event_id,
                    "attempt": attempt,
                    "error": f"Payment / accounting workflow failure: {domain_err}",
                }
            )

        # 9. Enforce idempotency after successful processing
        if self.redis_client:
            try:
                self.redis_client.set(event_idempotency_key, "1", ex=7 * 24 * 60 * 60)
                self.redis_client.set(txn_idempotency_key, "1", ex=7 * 24 * 60 * 60)
            except Exception as redis_set_err:
                logger.warning(
                    "Redis error saving idempotency marker for payment event %s: %s",
                    event_id,
                    redis_set_err,
                )

        logger.info(
            "Successfully processed payment event %s for transaction %s (job %s)",
            event_id,
            payment_id,
            job_id,
        )

        return ConsumeReceipt(
            {
                "status": "PROCESSED",
                "consumer": "payment",
                "event_id": event_id,
                "attempt": attempt,
            }
        )


# Aliases for flexible integration
PaymentEventConsumer = PaymentConsumer
PaymentStatusConsumer = PaymentConsumer

