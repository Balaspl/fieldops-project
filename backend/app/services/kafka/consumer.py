import json
import logging
import os
from typing import Any, Awaitable, Callable, Optional

from aiokafka import AIOKafkaConsumer

logger = logging.getLogger(__name__)


class KafkaConsumerManager:
    def __init__(
        self,
        topic: Optional[str] = None,
        group_id: Optional[str] = None,
        bootstrap_servers: Optional[str] = None,
    ):
        self.bootstrap_servers = bootstrap_servers or os.getenv(
            "KAFKA_BOOTSTRAP_SERVERS",
            "localhost:9092",
        )
        self.topic = topic or os.getenv(
            "KAFKA_TOPIC",
            "agent.message",
        )
        self.group_id = group_id or os.getenv(
            "KAFKA_CONSUMER_GROUP",
            "fieldops",
        )

        self.consumer = AIOKafkaConsumer(
            self.topic,
            bootstrap_servers=self.bootstrap_servers,
            group_id=self.group_id,
            enable_auto_commit=True,
            auto_offset_reset="earliest",
            value_deserializer=lambda value: json.loads(
                value.decode("utf-8")
            ),
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
        except Exception:
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