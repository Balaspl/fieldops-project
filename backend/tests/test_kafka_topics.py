import pytest

from app.services.kafka.topics import (
    DEFAULT_KAFKA_TOPICS,
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
