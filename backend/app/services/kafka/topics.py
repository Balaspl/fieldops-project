import os
from typing import Final


DEFAULT_KAFKA_TOPICS: Final[tuple[str, ...]] = (
    "fieldops.job.events",
    "fieldops.gps.events",
    "fieldops.sla.events",
    "fieldops.notification.events",
    "fieldops.billing.events",
    "fieldops.payment.events",
    "fieldops.audit.events",
)


DEFAULT_KAFKA_PARTITIONS: Final[dict[str, int]] = {
    "fieldops.job.events": 6,
    "fieldops.gps.events": 12,
    "fieldops.sla.events": 6,
    "fieldops.notification.events": 6,
    "fieldops.billing.events": 3,
    "fieldops.payment.events": 3,
    "fieldops.audit.events": 6,
}


def get_kafka_topics() -> tuple[str, ...]:
    configured_topics = os.getenv("KAFKA_TOPICS")

    if not configured_topics:
        return DEFAULT_KAFKA_TOPICS

    topics = tuple(
        topic.strip()
        for topic in configured_topics.split(",")
        if topic.strip()
    )

    if not topics:
        raise ValueError("KAFKA_TOPICS must contain at least one topic.")

    if len(topics) != len(set(topics)):
        raise ValueError("KAFKA_TOPICS contains duplicate topic names.")

    return topics


def get_kafka_partition_count(topic: str) -> int:
    if topic not in DEFAULT_KAFKA_PARTITIONS:
        raise ValueError(f"Unknown Kafka topic: {topic}")

    env_name = (
        "KAFKA_"
        + topic.removeprefix("fieldops.")
        .replace(".", "_")
        .upper()
        + "_PARTITIONS"
    )

    configured = os.getenv(env_name)

    if configured is None:
        return DEFAULT_KAFKA_PARTITIONS[topic]

    try:
        partitions = int(configured)
    except ValueError as exc:
        raise ValueError(
            f"{env_name} must be a positive integer."
        ) from exc

    if partitions < 1:
        raise ValueError(
            f"{env_name} must be a positive integer."
        )

    return partitions