import logging
import os
from time import monotonic
from typing import Any, Optional

from aiokafka import AIOKafkaClient, AIOKafkaConsumer

from .topics import get_kafka_partition_count, get_kafka_topics

logger = logging.getLogger(__name__)


class KafkaMonitoring:
    """Operational monitoring for Kafka infrastructure."""

    def __init__(
        self,
        bootstrap_servers: Optional[str] = None,
        topics: Optional[tuple[str, ...]] = None,
    ) -> None:
        self.bootstrap_servers = bootstrap_servers or os.getenv(
            "KAFKA_BOOTSTRAP_SERVERS",
            "localhost:9092",
        )
        self.topics = topics or get_kafka_topics()

        self._published_total = 0
        self._publish_failures = 0
        self._published_by_topic: dict[str, int] = {}
        self._consumed_by_topic: dict[str, int] = {}
        self._consumed_total = 0
        self._consume_failures = 0
        self._last_error: Optional[str] = None
        self._started_at = monotonic()

    @staticmethod
    def _security_config() -> dict[str, Any]:
        return {
            "security_protocol": os.getenv(
                "KAFKA_SECURITY_PROTOCOL",
                "SASL_PLAINTEXT",
            ),
            "sasl_mechanism": os.getenv(
                "KAFKA_SASL_MECHANISM",
                "PLAIN",
            ),
            "sasl_plain_username": os.getenv("KAFKA_MONITOR_USERNAME"),
            "sasl_plain_password": os.getenv("KAFKA_MONITOR_PASSWORD"),
        }

    def record_publish(
        self,
        success: bool,
        topic: Optional[str] = None,
    ) -> None:
        self._published_total += 1

        if topic:
            self._published_by_topic[topic] = (
                self._published_by_topic.get(topic, 0) + 1
            )

        if not success:
            self._publish_failures += 1

    def record_consume(
        self,
        success: bool,
        topic: Optional[str] = None,
    ) -> None:
        self._consumed_total += 1

        if topic:
            self._consumed_by_topic[topic] = (
                self._consumed_by_topic.get(topic, 0) + 1
            )

        if not success:
            self._consume_failures += 1

    def record_error(self, error: Exception | str) -> None:
        self._last_error = str(error)

    async def broker_health(self) -> dict[str, Any]:
        client = AIOKafkaClient(
            bootstrap_servers=self.bootstrap_servers,
            **self._security_config(),
        )

        try:
            await client.bootstrap()
            metadata = await client.fetch_all_metadata()

            brokers = list(metadata.brokers())

            return {
                "status": "healthy",
                "connected": True,
                "broker_count": len(brokers),
                "brokers": sorted(
                    f"{broker.host}:{broker.port}"
                    for broker in brokers
                ),
            }

        except Exception as exc:
            self.record_error(exc)
            logger.exception("Kafka broker health check failed.")

            return {
                "status": "unhealthy",
                "connected": False,
                "broker_count": 0,
                "brokers": [],
                "error": type(exc).__name__,
            }

        finally:
            await client.close()

    async def topic_health(self) -> dict[str, dict[str, Any]]:
        client = AIOKafkaClient(
            bootstrap_servers=self.bootstrap_servers,
            **self._security_config(),
        )

        try:
            await client.bootstrap()
            metadata = await client.fetch_all_metadata()
            available_topics = metadata.topics()

            result: dict[str, dict[str, Any]] = {}

            for topic in self.topics:
                partitions = (
                    metadata.partitions_for_topic(topic) or set()
                )
                expected = get_kafka_partition_count(topic)

                result[topic] = {
                    "status": (
                        "healthy"
                        if topic in available_topics
                        and len(partitions) == expected
                        else "degraded"
                    ),
                    "exists": topic in available_topics,
                    "partition_count": len(partitions),
                    "expected_partition_count": expected,
                }

            return result

        except Exception as exc:
            self.record_error(exc)
            logger.exception("Kafka topic health check failed.")

            return {
                topic: {
                    "status": "unhealthy",
                    "exists": False,
                    "partition_count": 0,
                    "expected_partition_count": (
                        get_kafka_partition_count(topic)
                    ),
                    "error": type(exc).__name__,
                }
                for topic in self.topics
            }

        finally:
            await client.close()

    async def consumer_lag(
        self,
        topic: str,
        group_id: str,
    ) -> dict[str, Any]:
        consumer = AIOKafkaConsumer(
            topic,
            bootstrap_servers=self.bootstrap_servers,
            group_id=group_id,
            **self._security_config(),
        )

        try:
            await consumer.start()

            partitions = await consumer.partitions_for_topic(topic)

            if not partitions:
                return {
                    "topic": topic,
                    "group_id": group_id,
                    "status": "unhealthy",
                    "lag": 0,
                    "partitions": {},
                }

            topic_partitions = {
                tp
                for tp in consumer.assignment()
                if tp.topic == topic
            }

            if not topic_partitions:
                from aiokafka.structs import TopicPartition

                topic_partitions = {
                    TopicPartition(topic, partition)
                    for partition in partitions
                }

            end_offsets = await consumer.end_offsets(
                topic_partitions
            )

            partition_lag: dict[str, int] = {}
            total_lag = 0

            for partition in sorted(
                topic_partitions,
                key=lambda item: item.partition,
            ):
                committed = await consumer.committed(partition)
                end_offset = end_offsets.get(partition, 0)

                lag = max(end_offset - (committed or 0), 0)

                partition_lag[str(partition.partition)] = lag
                total_lag += lag

            return {
                "topic": topic,
                "group_id": group_id,
                "status": "healthy",
                "lag": total_lag,
                "partitions": partition_lag,
            }

        except Exception as exc:
            self.record_error(exc)

            logger.exception(
                "Kafka consumer lag check failed: topic=%s group=%s",
                topic,
                group_id,
            )

            return {
                "topic": topic,
                "group_id": group_id,
                "status": "unhealthy",
                "lag": None,
                "partitions": {},
                "error": type(exc).__name__,
            }

        finally:
            await consumer.stop()

    def snapshot(self) -> dict[str, Any]:
        alerts: list[str] = []

        if self._publish_failures:
            alerts.append("publish_failures_detected")

        if self._consume_failures:
            alerts.append("consume_failures_detected")

        return {
            "status": "degraded" if alerts else "healthy",
            "uptime_seconds": round(
                monotonic() - self._started_at,
                2,
            ),
            "published_total": self._published_total,
            "publish_failures": self._publish_failures,
            "consumed_total": self._consumed_total,
            "consume_failures": self._consume_failures,
            "topics": {
                topic: {
                    "published_total": self._published_by_topic.get(
                        topic,
                        0,
                    ),
                    "consumed_total": self._consumed_by_topic.get(
                        topic,
                        0,
                    ),
                }
                for topic in self.topics
            },
            "last_error": self._last_error,
            "alerts": alerts,
        }


kafka_monitoring = KafkaMonitoring()