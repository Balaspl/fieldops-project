from typing import Any, Dict, Optional

from app.services.ai.FieldOpsAI.schemas.agent_messages import (
    AgentAddress,
    SLAEventMessage,
)
from app.services.kafka.producer import KafkaProducer


class SLAEventProducer:
    """Publishes SLA lifecycle events to Kafka."""

    TOPIC = "fieldops.sla.events"
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
            "event_type": event_type,
            "event_id": event_id,
            "job_id": job_id,
            "tenant_id": tenant_id,
            "schema_version": self.SCHEMA_VERSION,
            **(payload or {}),
        }

        event = SLAEventMessage(
            sender=AgentAddress(
                agent_type="monitoring",
                agent_id="sla-event-producer",
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