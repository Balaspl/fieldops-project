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
