import os
from typing import Final, Optional


DEFAULT_KAFKA_TOPICS: Final[tuple[str, ...]] = (
    "fieldops.events",
    "fieldops.job.events",
    "fieldops.gps.events",
    "fieldops.sla.events",
    "fieldops.notification.events",
    "fieldops.billing.events",
    "fieldops.payment.events",
    "fieldops.audit.events",
)


DEFAULT_KAFKA_PARTITIONS: Final[dict[str, int]] = {
    "fieldops.events": 3,
    "fieldops.job.events": 6,
    "fieldops.gps.events": 12,
    "fieldops.sla.events": 6,
    "fieldops.notification.events": 6,
    "fieldops.billing.events": 3,
    "fieldops.payment.events": 3,
    "fieldops.audit.events": 6,
}


DEFAULT_DLQ_TOPICS: Final[tuple[str, ...]] = tuple(
    f"{topic}.dlq" for topic in DEFAULT_KAFKA_TOPICS
)
DEFAULT_SHARED_DLQ_TOPIC: Final[str] = "fieldops.dlq.events"
DEFAULT_DLQ_RETENTION_MS: Final[int] = 14 * 24 * 60 * 60 * 1000  # 14 days (1,209,600,000 ms)
DEFAULT_TOPIC_RETENTION_MS: Final[int] = 7 * 24 * 60 * 60 * 1000  # 7 days (604,800,000 ms)


def is_dlq_topic(topic: str) -> bool:
    """Return True if the given topic is a designated DLQ topic."""
    if not topic or not isinstance(topic, str):
        return False
    return (
        topic.endswith(".dlq")
        or topic == DEFAULT_SHARED_DLQ_TOPIC
        or ".dlq." in topic
    )


def get_dlq_topic(topic: str) -> str:
    """
    Return the corresponding DLQ topic name for a given Kafka topic.
    If the topic is already a DLQ topic, return it unchanged.
    Allows environment override via KAFKA_DLQ_TOPIC or per-topic KAFKA_<TOPIC>_DLQ.
    """
    if is_dlq_topic(topic):
        return topic

    # Per-topic env override e.g. KAFKA_JOB_EVENTS_DLQ
    env_name = (
        "KAFKA_"
        + topic.removeprefix("fieldops.")
        .replace(".", "_")
        .upper()
        + "_DLQ"
    )
    configured = os.getenv(env_name)
    if configured and configured.strip():
        return configured.strip()

    # Generic DLQ topic override or default suffix
    generic_override = os.getenv("KAFKA_DLQ_TOPIC")
    if generic_override and generic_override.strip():
        return generic_override.strip()

    return f"{topic}.dlq"


def get_dlq_retention_ms(topic: Optional[str] = None) -> int:
    """
    Return the retention period in milliseconds for a DLQ topic.
    Defaults to 14 days (1,209,600,000 ms) to ensure sufficient time for diagnosis and manual replay.
    """
    if topic:
        env_name = (
            "KAFKA_"
            + topic.removeprefix("fieldops.")
            .replace(".", "_")
            .upper()
            + "_RETENTION_MS"
        )
        configured = os.getenv(env_name)
        if configured:
            try:
                retention = int(configured)
                if retention > 0:
                    return retention
            except ValueError:
                pass

    env_val = os.getenv("KAFKA_DLQ_RETENTION_MS")
    if env_val:
        try:
            retention = int(env_val)
            if retention > 0:
                return retention
        except ValueError:
            pass

    return DEFAULT_DLQ_RETENTION_MS


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
    base_topic = topic.removesuffix(".dlq") if topic.endswith(".dlq") else topic
    if topic == DEFAULT_SHARED_DLQ_TOPIC:
        base_topic = "fieldops.events"

    if base_topic not in DEFAULT_KAFKA_PARTITIONS:
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
        return DEFAULT_KAFKA_PARTITIONS[base_topic]

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
