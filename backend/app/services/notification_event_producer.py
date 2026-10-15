from typing import Any, Dict, Optional

from app.services.ai.FieldOpsAI.schemas.agent_messages import (
    AgentAddress,
    NotificationEventMessage,
)
from app.services.kafka.producer import KafkaProducer


class NotificationEventProducer:
    """Publishes notification lifecycle events to Kafka."""

    TOPIC = "fieldops.notification.events"
    SCHEMA_VERSION = 1

    def __init__(self, kafka_producer: KafkaProducer):
        self.kafka_producer = kafka_producer

    async def publish(
        self,
        *,
        event_type: str,
        event_id: str,
        job_id: str,
        tenant_id: str,
        correlation_id: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> bool:
        event_payload = {
            **(payload or {}),
            "event_type": event_type,
            "event_id": event_id,
            "job_id": job_id,
            "tenant_id": tenant_id,
            "schema_version": self.SCHEMA_VERSION,
        }

        event = NotificationEventMessage(
            sender=AgentAddress(
                agent_type="monitoring",
                agent_id="notification-event-producer",
                tenant_id=tenant_id,
            ),
            payload=event_payload,
            correlation_id=correlation_id,
            contract_version="1.0",
            topic=self.TOPIC,
            metadata={
                "event_id": event_id,
                "schema_version": self.SCHEMA_VERSION,
            },
        )

        return await self.kafka_producer.publish(event)
