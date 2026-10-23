"""
test_consumer_dead_letter_topics.py

Comprehensive test suite for Kafka Dead-Letter Queue (DLQ) topic lifecycle management,
poison message isolation, credential redaction, and safe event replay.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.redis_client import get_redis_client
from app.services.consumer_dead_letter_topics import (
    ConsumerDeadLetterTopics,
    CreateDeadLetterTopics,
    DLQReceipt,
)
from app.services.consumer_error_handler import ErrorClassification
from app.services.kafka.topics import (
    DEFAULT_DLQ_TOPICS,
    DEFAULT_SHARED_DLQ_TOPIC,
    get_dlq_retention_ms,
    get_dlq_topic,
    is_dlq_topic,
)


# =============================================================================
# Fake Redis and Message Helpers
# =============================================================================

class FakeRedis:
    def __init__(self):
        self.store = {}
        self.lists = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self.store[key] = value
        return True

    def rpush(self, key, value):
        if key not in self.lists:
            self.lists[key] = []
        self.lists[key].append(value)
        return len(self.lists[key])

    def llen(self, key):
        return len(self.lists.get(key, []))

    def lrange(self, key, start, stop):
        items = self.lists.get(key, [])
        if stop == -1:
            return items[start:]
        return items[start : stop + 1]


def make_test_event(
    event_id: str = "evt_01JEXAMPLE",
    tenant_id: str = "tenant-1",
    correlation_id: str = "corr-101",
    payload: dict = None,
    topic: str = "fieldops.job.events",
) -> dict:
    return {
        "event_id": event_id,
        "tenant_id": tenant_id,
        "correlation_id": correlation_id,
        "topic": topic,
        "payload": payload or {"job_id": "job-101", "status": "IN_PROGRESS"},
    }


# =============================================================================
# Topic Helpers and Configuration Tests
# =============================================================================

def test_dlq_topic_naming():
    """Verify standard .dlq suffix mapping."""
    assert get_dlq_topic("fieldops.job.events") == "fieldops.job.events.dlq"
    assert get_dlq_topic("fieldops.events") == "fieldops.events.dlq"
    assert get_dlq_topic("fieldops.gps.events") == "fieldops.gps.events.dlq"
    # Idempotent if already a DLQ topic
    assert get_dlq_topic("fieldops.job.events.dlq") == "fieldops.job.events.dlq"


def test_is_dlq_topic_detection():
    """Verify detection of designated DLQ topics."""
    assert is_dlq_topic("fieldops.job.events.dlq") is True
    assert is_dlq_topic(DEFAULT_SHARED_DLQ_TOPIC) is True
    assert is_dlq_topic("fieldops.job.events") is False
    assert is_dlq_topic("random.topic") is False
    assert is_dlq_topic("") is False
    assert is_dlq_topic(None) is False


def test_dlq_retention_defaults_and_override(monkeypatch):
    """Verify default 14 days retention and environment overrides."""
    # Default is 14 days = 1,209,600,000 ms
    assert get_dlq_retention_ms() == 14 * 24 * 60 * 60 * 1000

    monkeypatch.setenv("KAFKA_DLQ_RETENTION_MS", "86400000")
    assert get_dlq_retention_ms() == 86400000


def test_dlq_topic_environment_override(monkeypatch):
    """Verify per-topic and generic DLQ topic environment overrides."""
    monkeypatch.setenv("KAFKA_JOB_EVENTS_DLQ", "custom.job.dlq")
    assert get_dlq_topic("fieldops.job.events") == "custom.job.dlq"

    monkeypatch.delenv("KAFKA_JOB_EVENTS_DLQ", raising=False)
    monkeypatch.setenv("KAFKA_DLQ_TOPIC", "global.custom.dlq")
    assert get_dlq_topic("fieldops.events") == "global.custom.dlq"


# =============================================================================
# Primary Success Path & Recovery Contract Tests
# =============================================================================

@pytest.mark.asyncio
async def test_primary_recovery_success_contract():
    """
    Verify the primary success path:
    When an event processes successfully, the exact contract dictionary is returned:
    {
      "status": "RECOVERED",
      "event_id": "evt_01JEXAMPLE",
      "retries": 1,
      "idempotent": true,
      "dlq": false
    }
    """
    fake_redis = FakeRedis()
    consumer = ConsumerDeadLetterTopics(redis_client=fake_redis)

    event = make_test_event(event_id="evt_01JEXAMPLE")
    executed = []

    def handler(payload):
        executed.append(payload)
        return True

    result = await consumer.process_event(event, handler=handler)

    assert isinstance(result, DLQReceipt)
    assert result["status"] == "RECOVERED"
    assert result["event_id"] == "evt_01JEXAMPLE"
    assert result["retries"] == 1
    assert result["idempotent"] is True
    assert result["dlq"] is False
    assert len(executed) == 1

    # Verified stored in Redis idempotency marker
    assert fake_redis.get("consumer_dlq:event_processed:evt_01JEXAMPLE") == "1"


@pytest.mark.asyncio
async def test_transient_failure_recovered_within_allowed_retries():
    """
    Verify that an event failing transiently on attempt 1 but succeeding on attempt 2
    is successfully recovered without being sent to DLQ.
    """
    fake_redis = FakeRedis()
    consumer = ConsumerDeadLetterTopics(redis_client=fake_redis, max_retries=3)

    event = make_test_event(event_id="evt_transient_01")
    attempts = 0

    def flaky_handler(payload):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ConnectionError("Temporary connection timeout")
        return {"status": "ok"}

    result = await consumer.process_event(event, handler=flaky_handler)

    assert result["status"] == "RECOVERED"
    assert result["event_id"] == "evt_transient_01"
    assert result["retries"] == 2
    assert result["idempotent"] is True
    assert result["dlq"] is False
    assert attempts == 2
    assert fake_redis.llen(consumer.dlq_key) == 0


# =============================================================================
# Poison Messages & DLQ Isolation Tests
# =============================================================================

@pytest.mark.asyncio
async def test_poison_pill_missing_mandatory_metadata_routes_to_dlq():
    """
    Verify that a poison pill missing event_id or tenant_id is immediately
    isolated to DLQ without crashing the consumer.
    """
    fake_redis = FakeRedis()
    consumer = ConsumerDeadLetterTopics(redis_client=fake_redis)

    poison_event = {
        "corrupted_field": "bad_data",
        # missing event_id and tenant_id
    }

    result = await consumer.process_event(poison_event)

    assert result["status"] == "DEAD_LETTER"
    assert result["dlq"] is True
    assert result["idempotent"] is True
    assert result["retries"] == 0

    # Verified isolated into Redis DLQ queue
    assert fake_redis.llen(consumer.dlq_key) == 1
    dlq_entry = json.loads(fake_redis.lrange(consumer.dlq_key, 0, -1)[0])
    assert "missing mandatory event_id or tenant_id" in dlq_entry["error_message"]
    assert dlq_entry["error_classification"] == ErrorClassification.TERMINAL.value


@pytest.mark.asyncio
async def test_unauthorized_topic_routes_to_dlq():
    """
    Verify that an event received on an untrusted/unauthorized topic is rejected
    and isolated to the DLQ.
    """
    fake_redis = FakeRedis()
    consumer = ConsumerDeadLetterTopics(redis_client=fake_redis)

    untrusted_event = make_test_event(topic="malicious.unauthorized.topic")

    result = await consumer.process_event(untrusted_event)

    assert result["status"] == "DEAD_LETTER"
    assert result["dlq"] is True
    assert fake_redis.llen(consumer.dlq_key) == 1
    dlq_entry = json.loads(fake_redis.lrange(consumer.dlq_key, 0, -1)[0])
    assert "Unauthorized or untrusted Kafka topic" in dlq_entry["error_message"]


@pytest.mark.asyncio
async def test_terminal_error_routes_immediately_to_dlq_without_useless_retries():
    """
    Verify that non-retryable terminal errors (e.g. ValueError, KeyError)
    route immediately to DLQ rather than wasting retry backoff.
    """
    fake_redis = FakeRedis()
    consumer = ConsumerDeadLetterTopics(redis_client=fake_redis, max_retries=5)

    event = make_test_event(event_id="evt_terminal_01")
    attempts = 0

    def bad_logic_handler(payload):
        nonlocal attempts
        attempts += 1
        raise ValueError("Invalid schema: unknown field 'xyz'")

    result = await consumer.process_event(event, handler=bad_logic_handler)

    assert result["status"] == "DEAD_LETTER"
    assert result["dlq"] is True
    assert attempts == 1  # Did not waste 5 retries!
    assert fake_redis.llen(consumer.dlq_key) == 1


@pytest.mark.asyncio
async def test_exhausted_retries_route_to_dlq():
    """
    Verify that when all allowed retries are exhausted on a retryable error,
    the event is safely routed to the DLQ.
    """
    fake_redis = FakeRedis()
    consumer = ConsumerDeadLetterTopics(redis_client=fake_redis, max_retries=3)

    event = make_test_event(event_id="evt_exhausted_01")
    attempts = 0

    def always_failing_handler(payload):
        nonlocal attempts
        attempts += 1
        raise TimeoutError("Database connection permanently unreachable")

    result = await consumer.process_event(event, handler=always_failing_handler)

    assert result["status"] == "DEAD_LETTER"
    assert result["dlq"] is True
    assert result["retries"] == 3
    assert attempts == 3
    assert fake_redis.llen(consumer.dlq_key) == 1


# =============================================================================
# Credential Redaction & Security Tests
# =============================================================================

@pytest.mark.asyncio
async def test_sensitive_credentials_redacted_in_dlq():
    """
    Verify that passwords, tokens, API keys, and authorization secrets are
    redacted with [REDACTED] when stored in the DLQ.
    """
    fake_redis = FakeRedis()
    consumer = ConsumerDeadLetterTopics(redis_client=fake_redis)

    sensitive_event = make_test_event(
        event_id="evt_secret_01",
        payload={
            "job_id": 999,
            "password": "super_secret_password",
            "api_key": "live_sk_1234567890",
            "access_token": "bearer_jwt_token",
            "nested": {
                "secret_key": "private_rsa_key",
                "normal_field": "safe_value",
            },
        },
    )

    def failing_handler(payload):
        raise RuntimeError("Service failure")

    await consumer.process_event(sensitive_event, handler=failing_handler, max_retries=1)

    dlq_raw = fake_redis.lrange(consumer.dlq_key, 0, -1)[0]
    dlq_entry = json.loads(dlq_raw)
    payload = dlq_entry["payload"]

    assert payload["password"] == "[REDACTED]"
    assert payload["api_key"] == "[REDACTED]"
    assert payload["access_token"] == "[REDACTED]"
    assert payload["nested"]["secret_key"] == "[REDACTED]"
    assert payload["nested"]["normal_field"] == "safe_value"
    assert "super_secret_password" not in dlq_raw


# =============================================================================
# Idempotency & Duplicate Prevention Tests
# =============================================================================

@pytest.mark.asyncio
async def test_pre_execution_idempotency_prevents_duplicate_actions():
    """
    Verify that duplicate messages with the same event_id return success
    without re-executing business logic.
    """
    fake_redis = FakeRedis()
    consumer = ConsumerDeadLetterTopics(redis_client=fake_redis)

    event = make_test_event(event_id="evt_duplicate_01")
    call_count = 0

    def business_handler(payload):
        nonlocal call_count
        call_count += 1
        return True

    # First execution
    r1 = await consumer.process_event(event, handler=business_handler)
    assert r1["status"] == "RECOVERED"
    assert r1["dlq"] is False
    assert call_count == 1

    # Second duplicate execution
    r2 = await consumer.process_event(event, handler=business_handler)
    assert r2["status"] == "RECOVERED"
    assert r2["retries"] == 0
    assert r2["idempotent"] is True
    assert r2["dlq"] is False
    assert call_count == 1  # Handler NOT called again!


# =============================================================================
# DLQ Replay Tests
# =============================================================================

@pytest.mark.asyncio
async def test_dlq_replay_success():
    """
    Verify replaying an event from DLQ after fixing the issue.
    """
    fake_redis = FakeRedis()
    consumer = ConsumerDeadLetterTopics(redis_client=fake_redis)

    dlq_record = {
        "event_id": "evt_replay_01",
        "tenant_id": "tenant-1",
        "source_topic": "fieldops.job.events",
        "payload": {"job_id": "job-101", "action": "DISPATCH"},
    }

    replayed = []

    def replay_handler(payload):
        replayed.append(payload)
        return True

    result = await consumer.replay_dlq_event(dlq_record, handler=replay_handler)

    assert result["status"] == "RECOVERED"
    assert result["event_id"] == "evt_replay_01"
    assert result["retries"] == 1
    assert result["idempotent"] is True
    assert result["dlq"] is False
    assert len(replayed) == 1

    # Second replay attempt is idempotent
    result2 = await consumer.replay_dlq_event(dlq_record, handler=replay_handler)
    assert result2["status"] == "RECOVERED"
    assert result2["retries"] == 0
    assert len(replayed) == 1


# =============================================================================
# Kafka Producer & Topic Integration Tests
# =============================================================================

@pytest.mark.asyncio
async def test_kafka_producer_receives_dlq_topic_publication():
    """
    Verify that when KafkaProducer is configured, route_to_dlq publishes
    to the target .dlq topic with structured metadata.
    """
    mock_producer = AsyncMock()
    mock_producer.publish = AsyncMock(return_value=True)

    fake_redis = FakeRedis()
    consumer = ConsumerDeadLetterTopics(
        topic="fieldops.job.events",
        kafka_producer=mock_producer,
        redis_client=fake_redis,
    )

    event = make_test_event(event_id="evt_k_dlq_01", topic="fieldops.job.events")

    def failing_handler(payload):
        raise ValueError("Fatal error")

    result = await consumer.process_event(event, handler=failing_handler, max_retries=1)

    assert result["status"] == "DEAD_LETTER"
    assert result["dlq"] is True
    assert result["dlq_topic"] == "fieldops.job.events.dlq"

    # Producer was called with target topic
    assert mock_producer.publish.called
    call_args = mock_producer.publish.call_args
    assert call_args.kwargs.get("topic") == "fieldops.job.events.dlq"
    envelope = call_args.args[0]
    assert envelope.topic == "fieldops.job.events.dlq"


# =============================================================================
# Celery Tasks & Metrics Tests
# =============================================================================

def test_celery_dead_letter_event_tasks():
    """
    Verify that the Celery tasks execute properly and return the expected contracts.
    """
    from app.tasks import (
        _process_dead_letter_event_once,
        process_dead_letter_event_task,
        replay_dlq_event_task,
    )

    fake_redis = FakeRedis()
    event_payload = make_test_event(event_id="evt_celery_dlq_01")

    # Test single execution helper
    res1 = _process_dead_letter_event_once(
        redis=fake_redis,
        event_payload=event_payload,
        max_retries=1,
    )
    assert res1["status"] == "RECOVERED"
    assert res1["event_id"] == "evt_celery_dlq_01"
    assert res1["dlq"] is False

    # Test replay task
    with patch("app.tasks.get_redis_client", return_value=fake_redis):
        dlq_item = {
            "event_id": "evt_celery_replay_02",
            "tenant_id": "tenant-1",
            "payload": {"job_id": 10},
        }
        res_replay = replay_dlq_event_task(dlq_item)
        assert res_replay["status"] == "RECOVERED"
        assert res_replay["event_id"] == "evt_celery_replay_02"


def test_dlq_metrics():
    """
    Verify that DLQ metrics provide the expected observability snapshot.
    """
    fake_redis = FakeRedis()
    consumer = ConsumerDeadLetterTopics(redis_client=fake_redis)

    metrics = consumer.get_dlq_metrics()
    assert metrics["consumer"] == "Create_dead_letter_topics"
    assert metrics["status"] == "HEALTHY"
    assert "dlq_topics" in metrics
    assert len(metrics["dlq_topics"]) == len(DEFAULT_DLQ_TOPICS)
    assert metrics["default_retention_ms"] == 14 * 24 * 60 * 60 * 1000


def test_admin_metrics_kafka_dlq_endpoint():
    """
    Verify GET /admin/metrics/kafka/dlq returns DLQ observability data.
    """
    from fastapi.testclient import TestClient
    from app.main import app
    from app.auth.dependencies import get_current_user, AuthenticatedUser
    from app.auth.rbac import UserRole

    admin_user = AuthenticatedUser(
        user_id="test-head",
        tenant_id="tenant-1",
        role=UserRole.HEAD,
        jti="test-jti",
        session_id="test-session",
    )
    app.dependency_overrides[get_current_user] = lambda: admin_user

    client = TestClient(app)
    try:
        response = client.get("/admin/metrics/kafka/dlq")
        assert response.status_code == 200
        data = response.json()
        assert data["consumer"] == "Create_dead_letter_topics"
        assert data["status"] == "HEALTHY"
        assert "dlq_topics" in data
        assert "shared_dlq_topic" in data
    finally:
        app.dependency_overrides.pop(get_current_user, None)
