import logging
from typing import Any, Dict, Optional

from app.services.ai.FieldOpsAI.schemas.agent_messages import (
    AgentAddress,
    AuditEventMessage,
)
from app.services.kafka.producer import KafkaProducer

logger = logging.getLogger(__name__)


class PublishReceipt(dict):
    """
    Receipt returned by audit event publish matching canonical output envelope.
    Evaluates to True on success in boolean and equality checks.
    """

    def __bool__(self) -> bool:
        return self.get("status") == "PUBLISHED"

    def __eq__(self, other: Any) -> bool:
        if other is True:
            return self.get("status") == "PUBLISHED"
        if other is False:
            return self.get("status") != "PUBLISHED"
        return super().__eq__(other)


class AuditEventProducer:
    """Publishes approved audit events to Kafka."""

    DEFAULT_TOPIC = "fieldops.events"
    SCHEMA_VERSION = 1

    def __init__(
        self,
        kafka_producer: KafkaProducer,
        topic: Optional[str] = None,
    ):
        self.kafka_producer = kafka_producer
        self.topic = topic or self.DEFAULT_TOPIC

    async def publish(
        self,
        *,
        event_type: str,
        event_id: str,
        tenant_id: str,
        job_id: Optional[str] = None,
        user_id: Optional[str] = None,
        action: Optional[str] = None,
        correlation_id: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> PublishReceipt:
        """
        Publish an approved audit event with canonical event envelope.
        """
        event_payload = {
            **(payload or {}),
            "event_type": event_type,
            "event_id": event_id,
            "tenant_id": tenant_id,
            "schema_version": self.SCHEMA_VERSION,
        }
        if job_id is not None:
            event_payload["job_id"] = str(job_id)
        if user_id is not None:
            event_payload["user_id"] = str(user_id)
        if action is not None:
            event_payload["action"] = str(action)

        msg_kwargs = {
            "sender": AgentAddress(
                agent_type="monitoring",
                agent_id="audit-event-producer",
                tenant_id=tenant_id,
            ),
            "payload": event_payload,
            "contract_version": "1.0",
            "topic": self.topic,
            "metadata": {
                "event_id": event_id,
                "schema_version": self.SCHEMA_VERSION,
            },
        }
        if correlation_id is not None:
            msg_kwargs["correlation_id"] = correlation_id

        try:
            event = AuditEventMessage(**msg_kwargs)
        except Exception:
            logger.exception(
                "Invalid audit event message: event_type=%s event_id=%s tenant_id=%s",
                event_type,
                event_id,
                tenant_id,
            )
            raise

        try:
            published = await self.kafka_producer.publish(event, topic=self.topic)
        except Exception as exc:
            logger.exception(
                "Error publishing audit event to Kafka topic %s: %s",
                self.topic,
                exc,
            )
            published = False

        status_str = "PUBLISHED" if published else "FAILED"
        return PublishReceipt(
            {
                "status": status_str,
                "event_type": event_type,
                "event_id": event_id,
                "topic": self.topic,
                "schema_version": self.SCHEMA_VERSION,
            }
        )
