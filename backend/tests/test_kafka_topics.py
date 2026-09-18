import pytest

from app.services.kafka.topics import (
    DEFAULT_KAFKA_TOPICS,
    get_kafka_partition_count,
    get_kafka_topics,
)


def test_default_kafka_topics():
    assert get_kafka_topics() == DEFAULT_KAFKA_TOPICS
    assert len(DEFAULT_KAFKA_TOPICS) == 7
    assert len(DEFAULT_KAFKA_TOPICS) == len(set(DEFAULT_KAFKA_TOPICS))


def test_kafka_topics_from_environment(monkeypatch):
    monkeypatch.setenv(
        "KAFKA_TOPICS",
        "topic.one, topic.two, topic.three",
    )

    assert get_kafka_topics() == (
        "topic.one",
        "topic.two",
        "topic.three",
    )


def test_empty_kafka_topics_rejected(monkeypatch):
    monkeypatch.setenv("KAFKA_TOPICS", " , ")

    with pytest.raises(
        ValueError,
        match="at least one topic",
    ):
        get_kafka_topics()


def test_duplicate_kafka_topics_rejected(monkeypatch):
    monkeypatch.setenv(
        "KAFKA_TOPICS",
        "topic.one,topic.two,topic.one",
    )

    with pytest.raises(
        ValueError,
        match="duplicate topic names",
    ):
        get_kafka_topics()

def test_default_kafka_partition_count():
    assert get_kafka_partition_count("fieldops.job.events") == 6
    assert get_kafka_partition_count("fieldops.gps.events") == 12
    
def test_kafka_partition_count_from_environment(monkeypatch):
    monkeypatch.setenv(
        "KAFKA_JOB_EVENTS_PARTITIONS",
        "10",
    )

    assert get_kafka_partition_count("fieldops.job.events") == 10


def test_unknown_kafka_topic_rejected():
    with pytest.raises(
        ValueError,
        match="Unknown Kafka topic",
    ):
        get_kafka_partition_count("unknown.topic")
        
def test_invalid_kafka_partition_count_rejected(monkeypatch):
    monkeypatch.setenv(
        "KAFKA_JOB_EVENTS_PARTITIONS",
        "abc",
    )

    with pytest.raises(
        ValueError,
        match="must be a positive integer",
    ):
        get_kafka_partition_count("fieldops.job.events")
        
def test_zero_kafka_partition_count_rejected(monkeypatch):
    monkeypatch.setenv(
        "KAFKA_JOB_EVENTS_PARTITIONS",
        "0",
    )

    with pytest.raises(
        ValueError,
        match="must be a positive integer",
    ):
        get_kafka_partition_count("fieldops.job.events")
        
def test_negative_kafka_partition_count_rejected(monkeypatch):
    monkeypatch.setenv(
        "KAFKA_JOB_EVENTS_PARTITIONS",
        "-1",
    )

    with pytest.raises(
        ValueError,
        match="must be a positive integer",
    ):
        get_kafka_partition_count("fieldops.job.events")