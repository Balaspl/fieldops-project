import pytest

from app.services.kafka.monitoring import KafkaMonitoring


def test_record_operations_and_snapshot():
    monitoring = KafkaMonitoring()

    monitoring.record_publish(True)
    monitoring.record_publish(False)
    monitoring.record_consume(True)
    monitoring.record_consume(False)
    monitoring.record_error("Kafka timeout")

    snapshot = monitoring.snapshot()

    assert snapshot["published_total"] == 2
    assert snapshot["publish_failures"] == 1
    assert snapshot["consumed_total"] == 2
    assert snapshot["consume_failures"] == 1
    assert snapshot["last_error"] == "Kafka timeout"
    assert snapshot["status"] == "degraded"
    assert snapshot["alerts"] == [
        "publish_failures_detected",
        "consume_failures_detected",
    ]


@pytest.mark.asyncio
async def test_broker_health(monkeypatch):
    class FakeBroker:
        def __init__(self, host, port):
            self.host = host
            self.port = port

    class FakeMetadata:
        def brokers(self):
            return [FakeBroker("kafka", 9092)]

    class FakeClient:
        async def bootstrap(self):
            pass

        async def fetch_all_metadata(self):
            return FakeMetadata()

        async def close(self):
            pass

    monkeypatch.setattr(
        "app.services.kafka.monitoring.AIOKafkaClient",
        lambda **kwargs: FakeClient(),
    )

    monitoring = KafkaMonitoring()

    result = await monitoring.broker_health()

    assert result["status"] == "healthy"
    assert result["connected"] is True
    assert result["broker_count"] == 1
    assert result["brokers"] == ["kafka:9092"]


@pytest.mark.asyncio
async def test_broker_health_failure(monkeypatch):
    class FakeClient:
        async def bootstrap(self):
            raise RuntimeError("broker unavailable")

        async def close(self):
            pass

    monkeypatch.setattr(
        "app.services.kafka.monitoring.AIOKafkaClient",
        lambda **kwargs: FakeClient(),
    )

    monitoring = KafkaMonitoring()

    result = await monitoring.broker_health()

    assert result["status"] == "unhealthy"
    assert result["connected"] is False
    assert result["error"] == "RuntimeError"
    assert monitoring.snapshot()["last_error"] == "broker unavailable"
@pytest.mark.asyncio
async def test_topic_health(monkeypatch):
    class FakeMetadata:
        def topics(self):
            return {
                "fieldops.job.events",
                "fieldops.gps.events",
            }

        def partitions_for_topic(self, topic):
            if topic == "fieldops.job.events":
                return {0, 1, 2, 3, 4, 5}
            if topic == "fieldops.gps.events":
                return {0, 1}
            return set()

    class FakeClient:
        async def bootstrap(self):
            pass

        async def fetch_all_metadata(self):
            return FakeMetadata()

        async def close(self):
            pass

    monkeypatch.setattr(
        "app.services.kafka.monitoring.AIOKafkaClient",
        lambda **kwargs: FakeClient(),
    )

    monitoring = KafkaMonitoring(
        topics=(
            "fieldops.job.events",
            "fieldops.gps.events",
        )
    )

    result = await monitoring.topic_health()

    assert result["fieldops.job.events"]["status"] == "healthy"
    assert result["fieldops.job.events"]["partition_count"] == 6
    assert result["fieldops.job.events"]["expected_partition_count"] == 6

    assert result["fieldops.gps.events"]["status"] == "degraded"
    assert result["fieldops.gps.events"]["partition_count"] == 2
    assert result["fieldops.gps.events"]["expected_partition_count"] == 12
@pytest.mark.asyncio
async def test_consumer_lag(monkeypatch):
    from aiokafka.structs import TopicPartition

    class FakeConsumer:
        def __init__(self, *args, **kwargs):
            pass

        async def start(self):
            pass

        async def stop(self):
            pass

        async def partitions_for_topic(self, topic):
            return {0, 1}

        def assignment(self):
            return set()

        async def end_offsets(self, partitions):
            return {
                TopicPartition("fieldops.job.events", 0): 100,
                TopicPartition("fieldops.job.events", 1): 250,
            }

        async def committed(self, partition):
            if partition.partition == 0:
                return 90
            return 200

    monkeypatch.setattr(
        "app.services.kafka.monitoring.AIOKafkaConsumer",
        FakeConsumer,
    )

    monitoring = KafkaMonitoring()

    result = await monitoring.consumer_lag(
        "fieldops.job.events",
        "fieldops-dispatch",
    )

    assert result["status"] == "healthy"
    assert result["lag"] == 60
    assert result["partitions"] == {
        "0": 10,
        "1": 50,
    }


@pytest.mark.asyncio
async def test_consumer_lag_failure(monkeypatch):
    class FakeConsumer:
        def __init__(self, *args, **kwargs):
            pass

        async def start(self):
            raise RuntimeError("consumer unavailable")

        async def stop(self):
            pass

    monkeypatch.setattr(
        "app.services.kafka.monitoring.AIOKafkaConsumer",
        FakeConsumer,
    )

    monitoring = KafkaMonitoring()

    result = await monitoring.consumer_lag(
        "fieldops.job.events",
        "fieldops-dispatch",
    )

    assert result["status"] == "unhealthy"
    assert result["lag"] is None
    assert result["error"] == "RuntimeError"
    assert monitoring.snapshot()["last_error"] == "consumer unavailable"

def test_record_operations_with_topics():
    monitoring = KafkaMonitoring(
        topics=("fieldops.job.events",)
    )

    monitoring.record_publish(True, "fieldops.job.events")
    monitoring.record_consume(True, "fieldops.job.events")

    snapshot = monitoring.snapshot()

    assert snapshot["topics"]["fieldops.job.events"] == {
        "published_total": 1,
        "consumed_total": 1,
    }


@pytest.mark.asyncio
async def test_topic_health_failure(monkeypatch):
    class FakeClient:
        async def bootstrap(self):
            raise RuntimeError("topic metadata unavailable")

        async def close(self):
            pass

    monkeypatch.setattr(
        "app.services.kafka.monitoring.AIOKafkaClient",
        lambda **kwargs: FakeClient(),
    )

    monitoring = KafkaMonitoring(
        topics=("fieldops.job.events",)
    )

    result = await monitoring.topic_health()

    assert result["fieldops.job.events"]["status"] == "unhealthy"
    assert result["fieldops.job.events"]["error"] == "RuntimeError"
    assert monitoring.snapshot()["last_error"] == (
        "topic metadata unavailable"
    )


@pytest.mark.asyncio
async def test_consumer_lag_no_partitions(monkeypatch):
    class FakeConsumer:
        def __init__(self, *args, **kwargs):
            pass

        async def start(self):
            pass

        async def stop(self):
            pass

        async def partitions_for_topic(self, topic):
            return set()

    monkeypatch.setattr(
        "app.services.kafka.monitoring.AIOKafkaConsumer",
        FakeConsumer,
    )

    monitoring = KafkaMonitoring()

    result = await monitoring.consumer_lag(
        "fieldops.job.events",
        "fieldops-dispatch",
    )

    assert result == {
        "topic": "fieldops.job.events",
        "group_id": "fieldops-dispatch",
        "status": "unhealthy",
        "lag": 0,
        "partitions": {},
    }