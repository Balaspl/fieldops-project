import asyncio
import json
import logging
import os
from typing import Optional

from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError

from .monitoring import KafkaMonitoring
from app.services.ai.FieldOpsAI.schemas.agent_messages import MessageEnvelope

logger = logging.getLogger(__name__)


class KafkaProducer:
    def __init__(
        self,
        monitoring: Optional[KafkaMonitoring] = None,
    ) -> None:
        self.bootstrap_servers = os.getenv(
            "KAFKA_BOOTSTRAP_SERVERS",
            "localhost:9092",
        )
        self._producer: Optional[AIOKafkaProducer] = None
        self.monitoring = monitoring

    @staticmethod
    def _get_partition_key(
        message: MessageEnvelope,
        topic: str,
    ) -> str:
        job_ordered_topics = {
            "fieldops.job.events",
            "fieldops.gps.events",
            "fieldops.sla.events",
        }

        tenant_ordered_topics = {
            "fieldops.notification.events",
            "fieldops.billing.events",
            "fieldops.payment.events",
            "fieldops.audit.events",
        }

        if topic in job_ordered_topics:
            job_id = message.payload.get("job_id")

            if job_id is None or str(job_id).strip() == "":
                raise ValueError(
                    f"job_id is required for ordered Kafka topic: {topic}"
                )

            return str(job_id)

        if topic in tenant_ordered_topics:
            return message.tenant_id

        return str(message.message_id)

    async def start(self) -> None:
        if self._producer is not None:
            return

        security_protocol = os.getenv(
            "KAFKA_SECURITY_PROTOCOL",
            "SASL_PLAINTEXT",
        )
        sasl_mechanism = os.getenv(
            "KAFKA_SASL_MECHANISM",
            "PLAIN",
        )
        sasl_username = os.getenv(
            "KAFKA_PRODUCER_USERNAME"
        ) or os.getenv("KAFKA_SASL_USERNAME")

        sasl_password = os.getenv(
            "KAFKA_PRODUCER_PASSWORD"
        ) or os.getenv("KAFKA_SASL_PASSWORD")

        producer_kwargs = {
            "bootstrap_servers": self.bootstrap_servers,
            "request_timeout_ms": 5000,
            "acks": os.getenv("KAFKA_ACKS", "all"),
        }

        if sasl_username and sasl_password:
            producer_kwargs.update(
                {
                    "security_protocol": security_protocol,
                    "sasl_mechanism": sasl_mechanism,
                    "sasl_plain_username": sasl_username,
                    "sasl_plain_password": sasl_password,
                }
            )

        self._producer = AIOKafkaProducer(
            **producer_kwargs,
        )

        try:
            await self._producer.start()
            logger.info("Kafka producer started.")
        except Exception:
            self._producer = None
            logger.exception("Failed to start Kafka producer.")
            raise

    async def stop(self) -> None:
        if self._producer is None:
            return

        producer = self._producer
        self._producer = None

        try:
            await producer.stop()
            logger.info("Kafka producer stopped.")
        except Exception:
            logger.exception("Failed to stop Kafka producer.")

    async def publish(
        self,
        message: MessageEnvelope,
        topic: Optional[str] = None,
    ) -> bool:
        if self._producer is None:
            raise RuntimeError("Kafka producer is not started.")

        target_topic = topic or message.topic
        partition_key = self._get_partition_key(message, target_topic)

        payload = message.model_dump(mode="json")

        try:
            await asyncio.wait_for(
                self._producer.send_and_wait(
                    target_topic,
                    json.dumps(payload).encode("utf-8"),
                    key=partition_key.encode("utf-8"),
                ),
                timeout=5.0,
            )

            if self.monitoring:
                self.monitoring.record_publish(True, target_topic)

            logger.info(
                "Kafka event published: topic=%s message_id=%s",
                target_topic,
                message.message_id,
            )
            return True

        except (KafkaError, asyncio.TimeoutError):
            if self.monitoring:
                self.monitoring.record_publish(False, target_topic)
                self.monitoring.record_error(
                    "Kafka publication failed"
                )

            logger.exception(
                "Kafka event publication failed: topic=%s message_id=%s",
                target_topic,
                message.message_id,
            )
            return False