import json

import pytest

from app.services.kafka.consumer import KafkaConsumerManager


class FakeMessage:
    def __init__(self, value):
        self.value = value


@pytest.mark.asyncio
async def test_consumer_uses_environment_configuration(monkeypatch):
    monkeypatch.setattr(
        "app.services.kafka.consumer.AIOKafkaConsumer",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "test-kafka:9092")
    monkeypatch.setenv("KAFKA_TOPIC", "test.topic")
    monkeypatch.setenv("KAFKA_CONSUMER_GROUP", "test-group")

    manager = KafkaConsumerManager()

    try:
        assert manager.bootstrap_servers == "test-kafka:9092"
        assert manager.topic == "test.topic"
        assert manager.group_id == "test-group"
    finally:
        pass


@pytest.mark.asyncio
async def test_consumer_accepts_explicit_configuration():
    manager = KafkaConsumerManager(
        topic="custom.topic",
        group_id="custom-group",
        bootstrap_servers="custom-kafka:9092",
    )

    try:
        assert manager.topic == "custom.topic"
        assert manager.group_id == "custom-group"
        assert manager.bootstrap_servers == "custom-kafka:9092"
    finally:
        await manager.consumer.stop()


@pytest.mark.asyncio
async def test_consumer_handler_receives_message(monkeypatch):
    manager = KafkaConsumerManager()
    real_consumer = manager.consumer

    payload = {
        "message_id": "msg-1",
        "tenant_id": "tenant-001",
        "correlation_id": "corr-001",
    }

    class FakeConsumer:
        def __aiter__(self):
            return self

        async def __anext__(self):
            if not hasattr(self, "sent"):
                self.sent = True
                return FakeMessage(payload)
            raise StopAsyncIteration

    manager.consumer = FakeConsumer()

    received = []

    async def handler(message):
        received.append(message)

    await manager.consume(handler)

    assert received == [payload]
    
    await real_consumer.stop()


@pytest.mark.asyncio
async def test_consumer_propagates_handler_failure():
    manager = KafkaConsumerManager()
    real_consumer = manager.consumer

    class FakeConsumer:
        def __aiter__(self):
            return self

        async def __anext__(self):
            if not hasattr(self, "sent"):
                self.sent = True
                return FakeMessage({"event": "test"})
            raise StopAsyncIteration

    manager.consumer = FakeConsumer()

    async def handler(message):
        raise RuntimeError("handler failure")

    with pytest.raises(RuntimeError, match="handler failure"):
        await manager.consume(handler)
        
    await real_consumer.stop()


@pytest.mark.asyncio
async def test_consumer_start_and_stop(monkeypatch):
    manager = KafkaConsumerManager()
    real_consumer = manager.consumer

    started = False
    stopped = False

    async def fake_start():
        nonlocal started
        started = True

    async def fake_stop():
        nonlocal stopped
        stopped = True

    monkeypatch.setattr(manager.consumer, "start", fake_start)
    monkeypatch.setattr(manager.consumer, "stop", fake_stop)

    await manager.start()
    await manager.stop()

    assert started is True
    assert stopped is True
    
    await real_consumer.stop()


@pytest.mark.asyncio
async def test_consumer_context_manager(monkeypatch):
    manager = KafkaConsumerManager()
    real_consumer = manager.consumer

    started = False
    stopped = False

    async def fake_start():
        nonlocal started
        started = True

    async def fake_stop():
        nonlocal stopped
        stopped = True

    monkeypatch.setattr(manager.consumer, "start", fake_start)
    monkeypatch.setattr(manager.consumer, "stop", fake_stop)

    async with manager:
        assert started is True

    assert stopped is True
    
    await real_consumer.stop()