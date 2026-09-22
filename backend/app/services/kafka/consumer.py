import json
import logging
import os
from typing import Any, Awaitable, Callable, Optional

from aiokafka import AIOKafkaConsumer
from .monitoring import KafkaMonitoring

logger = logging.getLogger(__name__)


DEFAULT_CONSUMER_GROUPS = {
    "fieldops.job.events": "fieldops-dispatch",
    "fieldops.gps.events": "fieldops-gps",
    "fieldops.notification.events": "fieldops-notifications",
    "fieldops.sla.events": "fieldops-sla",
    "fieldops.billing.events": "fieldops-billing",
    "fieldops.payment.events": "fieldops-payment",
    "fieldops.audit.events": "fieldops-audit",
}
CONSUMER_CREDENTIALS = {
    "fieldops.job.events": (
        "KAFKA_DISPATCH_USERNAME",
        "KAFKA_DISPATCH_PASSWORD",
    ),
    "fieldops.gps.events": (
        "KAFKA_GPS_USERNAME",
        "KAFKA_GPS_PASSWORD",
    ),
    "fieldops.sla.events": (
        "KAFKA_SLA_USERNAME",
        "KAFKA_SLA_PASSWORD",
    ),
    "fieldops.notification.events": (
        "KAFKA_NOTIFICATIONS_USERNAME",
        "KAFKA_NOTIFICATIONS_PASSWORD",
    ),
    "fieldops.billing.events": (
        "KAFKA_BILLING_USERNAME",
        "KAFKA_BILLING_PASSWORD",
    ),
    "fieldops.payment.events": (
        "KAFKA_PAYMENT_USERNAME",
        "KAFKA_PAYMENT_PASSWORD",
    ),
    "fieldops.audit.events": (
        "KAFKA_AUDIT_USERNAME",
        "KAFKA_AUDIT_PASSWORD",
    ),
}


class KafkaConsumerManager:
    def __init__(
        self,
        topic: Optional[str] = None,
        group_id: Optional[str] = None,
        bootstrap_servers: Optional[str] = None,
        monitoring: Optional[KafkaMonitoring] = None,
    ):
        self.bootstrap_servers = bootstrap_servers or os.getenv(
            "KAFKA_BOOTSTRAP_SERVERS",
            "localhost:9092",
        )
        self.topic = topic or os.getenv(
            "KAFKA_TOPIC",
            "agent.message",
        )

        default_group_id = DEFAULT_CONSUMER_GROUPS.get(
            self.topic,
            os.getenv("KAFKA_CONSUMER_GROUP", "fieldops"),
        )

        self.group_id = group_id or os.getenv(
            self._group_env_var_name(),
            default_group_id,
        )
        username_env, password_env = CONSUMER_CREDENTIALS.get(
            self.topic,
            ("KAFKA_SASL_USERNAME", "KAFKA_SASL_PASSWORD"),
        )
        
        security_protocol = os.getenv(
            "KAFKA_SECURITY_PROTOCOL",
            "SASL_PLAINTEXT",
        )
        sasl_mechanism = os.getenv(
            "KAFKA_SASL_MECHANISM",
            "PLAIN",
        )
        sasl_username = os.getenv(username_env) or os.getenv(
            "KAFKA_SASL_USERNAME"
        )
        sasl_password = os.getenv(password_env) or os.getenv(
            "KAFKA_SASL_PASSWORD"
        )

        consumer_kwargs = {
            "bootstrap_servers": self.bootstrap_servers,
            "group_id": self.group_id,
            "enable_auto_commit": True,
            "auto_offset_reset": "earliest",
            "value_deserializer": lambda value: json.loads(
                value.decode("utf-8")
            ),
        }

        if sasl_username and sasl_password:
            consumer_kwargs.update(
                {
                    "security_protocol": security_protocol,
                    "sasl_mechanism": sasl_mechanism,
                    "sasl_plain_username": sasl_username,
                    "sasl_plain_password": sasl_password,
                }
            )
        self.monitoring = monitoring

        self.consumer = AIOKafkaConsumer(
            self.topic,
            **consumer_kwargs,
        )

    def _group_env_var_name(self) -> str:
        topic_group_names = {
            "fieldops.job.events": "KAFKA_DISPATCH_CONSUMER_GROUP",
            "fieldops.gps.events": "KAFKA_GPS_CONSUMER_GROUP",
            "fieldops.notification.events": (
                "KAFKA_NOTIFICATIONS_CONSUMER_GROUP"
            ),
            "fieldops.sla.events": "KAFKA_SLA_CONSUMER_GROUP",
            "fieldops.billing.events": "KAFKA_BILLING_CONSUMER_GROUP",
            "fieldops.payment.events": "KAFKA_PAYMENT_CONSUMER_GROUP",
            "fieldops.audit.events": "KAFKA_AUDIT_CONSUMER_GROUP",
        }

        return topic_group_names.get(
            self.topic,
            "KAFKA_CONSUMER_GROUP",
        )

    async def start(self) -> None:
        await self.consumer.start()

    async def stop(self) -> None:
        await self.consumer.stop()

    async def consume(
        self,
        handler: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        try:
            async for message in self.consumer:
                await handler(message.value)

                if self.monitoring:
                    self.monitoring.record_consume(
                        True,
                        self.topic,
                    )

        except Exception as exc:
            if self.monitoring:
                self.monitoring.record_consume(
                    False,
                    self.topic,
                )
                self.monitoring.record_error(exc)

            logger.exception("Kafka consumer processing failed.")
            raise

    async def __aenter__(self) -> "KafkaConsumerManager":
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: Any,
        exc_value: Any,
        traceback: Any,
    ) -> None:
        await self.stop()