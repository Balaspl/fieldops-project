import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.services.consumer_health_checks import (
    ConsumeReceipt,
    ConsumerHealthChecks,
    ConsumerHealthCheckService,
    AddHealthChecksConsumer,
    Add_health_checks,
    ConsumerHealthMonitor,
)
from app.services.ai.FieldOpsAI.schemas.agent_messages import (
    AgentAddress,
    MessageEnvelope,
    MessageType,
)
from app.tasks import (
    _process_health_checks_event_once,
    process_health_checks_event_task,
)


@pytest.fixture
def fake_redis():
    class FakeRedis:
        def __init__(self):
            self.store = {}
            self.lists = {}

        def get(self, key):
            return self.store.get(key)

        def set(self, key, value, ex=None):
            self.store[key] = value

        def setex(self, key, time, value):
            self.store[key] = value

        def rpush(self, key, value):
            if key not in self.lists:
                self.lists[key] = []
            self.lists[key].append(value)
            return len(self.lists[key])

        def lrange(self, key, start, stop):
            items = self.lists.get(key, [])
            if stop == -1:
                return items[start:]
            return items[start : stop + 1]

        def delete(self, *keys):
            for k in keys:
                self.store.pop(k, None)
                self.lists.pop(k, None)

        def publish(self, channel, message):
            return 1

    return FakeRedis()


@pytest.fixture
def fake_consumer_manager():
    manager = MagicMock()
    manager.start = AsyncMock()
    manager.stop = AsyncMock()
    consumer_mock = MagicMock()
    consumer_mock.assignment.return_value = set()
    manager.consumer = consumer_mock
    return manager


# ============================================================================
# 1. ConsumeReceipt tests
# ============================================================================

def test_consume_receipt_behavior():
    success_receipt = ConsumeReceipt(
        {"status": "PROCESSED", "consumer": "Add_health_checks", "event_id": "evt_1", "attempt": 1}
    )
    assert success_receipt.is_success is True
    assert bool(success_receipt) is True
    assert success_receipt["consumer"] == "Add_health_checks"
    assert success_receipt["status"] == "PROCESSED"

    failed_receipt = ConsumeReceipt(
        {"status": "FAILED", "consumer": "Add_health_checks", "event_id": "evt_2", "attempt": 1, "error": "test"}
    )
    assert failed_receipt.is_success is False
    assert bool(failed_receipt) is False
    assert failed_receipt["status"] == "FAILED"


# ============================================================================
# 2. Aliases and Default Configuration
# ============================================================================

def test_aliases_and_defaults(fake_redis):
    consumer = ConsumerHealthChecks(redis_client=fake_redis)
    assert consumer.CONSUMER_NAME == "Add_health_checks"
    assert consumer.topic == "fieldops.events"
    assert consumer.group_id == "fieldops-health-checks"
    assert consumer.dlq_key == "consumer:dlq"
    assert consumer.max_consecutive_errors == 5
    assert consumer.max_lag == 1000

    assert ConsumerHealthCheckService is ConsumerHealthChecks
    assert AddHealthChecksConsumer is ConsumerHealthChecks
    assert Add_health_checks is ConsumerHealthChecks
    assert ConsumerHealthMonitor is ConsumerHealthChecks


# ============================================================================
# 3. Connectivity and Readiness Tracking
# ============================================================================

@pytest.mark.asyncio
async def test_connectivity_and_readiness_lifecycle(fake_redis, fake_consumer_manager):
    consumer = ConsumerHealthChecks(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )

    # Initial state: stopped
    assert consumer.is_connected() is False
    assert consumer.is_ready() is False
    assert consumer.is_healthy() is False

    # Start consumer
    await consumer.start()
    assert consumer.is_connected() is True
    assert consumer.is_ready() is True
    assert consumer.is_healthy() is True

    # Health snapshot has connected status
    snapshot = consumer.get_health_snapshot()
    assert snapshot["connected"] is True
    assert snapshot["status"] == "healthy"
    assert snapshot["ready"] is True

    # Stop consumer
    await consumer.stop()
    assert consumer.is_connected() is False
    assert consumer.is_ready() is False
    assert consumer.get_health_snapshot()["status"] == "unhealthy"


# ============================================================================
# 4. Partition Assignment and Lag Tracking
# ============================================================================

def test_partition_assignment_tracking(fake_redis):
    consumer = ConsumerHealthChecks(redis_client=fake_redis)
    consumer.set_assigned_partitions(["fieldops.events-0", "fieldops.events-1"])

    snapshot = consumer.get_health_snapshot()
    assert snapshot["assignment"]["count"] == 2
    assert snapshot["assignment"]["partitions"] == ["fieldops.events-0", "fieldops.events-1"]


def test_status_determination_degraded_and_unhealthy(fake_redis):
    consumer = ConsumerHealthChecks(redis_client=fake_redis, max_consecutive_errors=3, max_lag=500)
    consumer._connected = True

    # Zero errors, normal lag -> healthy
    assert consumer.determine_status(lag_total=10) == "healthy"

    # Single error -> degraded
    consumer.record_failure("Transient timeout")
    assert consumer.determine_status(lag_total=10) == "degraded"

    # Reach max consecutive errors -> unhealthy
    consumer.record_failure("Another timeout")
    consumer.record_failure("Third timeout")
    assert consumer.determine_status(lag_total=10) == "unhealthy"

    # Recovery resets errors
    consumer.record_success("evt_recovery_1")
    assert consumer.determine_status(lag_total=10) == "healthy"

    # Excessive lag -> degraded
    assert consumer.determine_status(lag_total=600) == "degraded"


# ============================================================================
# 5. Primary Success Path
# ============================================================================

@pytest.mark.asyncio
async def test_consumer_primary_success_path_dict(fake_redis, fake_consumer_manager):
    consumer = ConsumerHealthChecks(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )
    await consumer.start()

    event_id = "evt_01JEXAMPLE"
    payload = {
        "event_id": event_id,
        "tenant_id": "tenant-001",
        "schema_version": 1,
        "event_type": "job_created",
        "job_id": "JOB-101",
    }

    receipt = await consumer.process_event(payload, attempt=1)

    assert receipt["status"] == "PROCESSED"
    assert receipt["consumer"] == "Add_health_checks"
    assert receipt["event_id"] == event_id
    assert receipt["attempt"] == 1
    assert bool(receipt) is True

    # Check health snapshot updated
    snapshot = consumer.get_health_snapshot()
    assert snapshot["processing"]["processed_total"] == 1
    assert snapshot["processing"]["last_event_id"] == event_id
    assert snapshot["processing"]["last_processed_at"] is not None
    assert snapshot["error_state"]["consecutive_errors"] == 0

    # Check idempotency marker set in Redis
    assert fake_redis.get(f"consumer_health:event_processed:{event_id}") == "1"


@pytest.mark.asyncio
async def test_consumer_primary_success_path_json_string(fake_redis, fake_consumer_manager):
    consumer = ConsumerHealthChecks(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )
    await consumer.start()

    event_id = "evt_health_json_001"
    raw_json = json.dumps({
        "event_id": event_id,
        "tenant_id": "tenant-002",
        "schema_version": 1,
        "event_type": "health_check_ping",
    })

    receipt = await consumer.process_event(raw_json, attempt=1)

    assert receipt["status"] == "PROCESSED"
    assert receipt["consumer"] == "Add_health_checks"
    assert receipt["event_id"] == event_id
    assert receipt["attempt"] == 1


@pytest.mark.asyncio
async def test_consumer_primary_success_path_envelope(fake_redis, fake_consumer_manager):
    consumer = ConsumerHealthChecks(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )
    await consumer.start()

    event_id = "evt_env_health_001"
    envelope = MessageEnvelope(
        sender=AgentAddress(
            agent_type="monitoring",
            agent_id="health-agent",
            tenant_id="tenant-003",
        ),
        recipient=None,
        message_type=MessageType.EVENT,
        payload={
            "event_id": event_id,
            "tenant_id": "tenant-003",
            "schema_version": 1,
            "event_type": "status_ping",
        },
        topic="fieldops.events",
    )

    receipt = await consumer.process_event(envelope, attempt=1)

    assert receipt["status"] == "PROCESSED"
    assert receipt["consumer"] == "Add_health_checks"
    assert receipt["event_id"] == event_id
    assert receipt["attempt"] == 1


# ============================================================================
# 6. Idempotency & Duplicate Business Side Effects Prevention
# ============================================================================

@pytest.mark.asyncio
async def test_idempotency_prevents_duplicate_processing(fake_redis):
    side_effects = []

    def tracking_handler(msg):
        side_effects.append(msg["event_id"])
        return {"ok": True}

    consumer = ConsumerHealthChecks(
        redis_client=fake_redis,
        handler=tracking_handler,
    )
    await consumer.start()

    payload = {
        "event_id": "evt_idemp_health_001",
        "tenant_id": "tenant-1",
        "schema_version": 1,
    }

    # First attempt: processed normally
    receipt1 = await consumer.process_event(payload, attempt=1)
    assert receipt1["status"] == "PROCESSED"
    assert receipt1.get("idempotent_duplicate") is not True
    assert len(side_effects) == 1

    # Second attempt: duplicate skipped
    receipt2 = await consumer.process_event(payload, attempt=2)
    assert receipt2["status"] == "PROCESSED"
    assert receipt2["idempotent_duplicate"] is True
    # Side effects must NOT be invoked again
    assert len(side_effects) == 1


# ============================================================================
# 7. Malformed Messages & Encodings (Safe Failure & DLQ)
# ============================================================================

@pytest.mark.asyncio
async def test_malformed_json_does_not_crash_and_updates_health(fake_redis):
    consumer = ConsumerHealthChecks(redis_client=fake_redis)
    await consumer.start()

    malformed = "{ broken json: [1, 2, "
    receipt = await consumer.process_event(malformed, attempt=1)

    assert receipt["status"] == "FAILED"
    assert receipt["consumer"] == "Add_health_checks"
    assert receipt["error_type"] == "JSONDecodeError"

    # DLQ received failure record
    dlq_items = fake_redis.lrange("consumer:dlq", 0, -1)
    assert len(dlq_items) == 1
    dlq_data = json.loads(dlq_items[0])
    assert dlq_data["error_type"] == "JSONDecodeError"

    # Health error state updated
    snapshot = consumer.get_health_snapshot()
    assert snapshot["error_state"]["failure_count"] == 1
    assert snapshot["error_state"]["consecutive_errors"] == 1


@pytest.mark.asyncio
async def test_malformed_bytes_encoding_does_not_crash(fake_redis):
    consumer = ConsumerHealthChecks(redis_client=fake_redis)
    await consumer.start()

    bad_bytes = b"\xff\xfe\xfa\x80"
    receipt = await consumer.process_event(bad_bytes, attempt=1)

    assert receipt["status"] == "FAILED"
    assert receipt["error_type"] == "UnicodeDecodeError"


@pytest.mark.asyncio
async def test_unsupported_message_type_does_not_crash(fake_redis):
    consumer = ConsumerHealthChecks(redis_client=fake_redis)
    await consumer.start()

    receipt = await consumer.process_event(55555, attempt=1)

    assert receipt["status"] == "FAILED"
    assert receipt["error_type"] == "TypeError"


# ============================================================================
# 8. Authorization and Schema Preconditions
# ============================================================================

@pytest.mark.asyncio
async def test_unauthorized_topic_rejected(fake_redis):
    consumer = ConsumerHealthChecks(redis_client=fake_redis)
    await consumer.start()

    payload = {
        "event_id": "evt_unauth_h1",
        "tenant_id": "tenant-001",
        "schema_version": 1,
        "topic": "unauthorized.topic.leak",
    }

    receipt = await consumer.process_event(payload, attempt=1)

    assert receipt["status"] == "FAILED"
    assert receipt["error_type"] == "TopicAuthorizationFailedError"


@pytest.mark.asyncio
async def test_missing_required_fields_fails_validation(fake_redis):
    consumer = ConsumerHealthChecks(redis_client=fake_redis)
    await consumer.start()

    invalid_payload = {
        "event_type": "job_created",
    }

    receipt = await consumer.process_event(invalid_payload, attempt=1)

    assert receipt["status"] == "FAILED"
    assert receipt["error_type"] == "ValidationError"


@pytest.mark.asyncio
async def test_forbidden_sensitive_keys_rejected_and_redacted(fake_redis):
    consumer = ConsumerHealthChecks(redis_client=fake_redis)
    await consumer.start()

    payload = {
        "event_id": "evt_sensitive_h1",
        "tenant_id": "tenant-001",
        "schema_version": 1,
        "password": "my-plain-password",
    }

    receipt = await consumer.process_event(payload, attempt=1)

    assert receipt["status"] == "FAILED"
    assert receipt["error_type"] == "SecurityPolicyError"

    dlq_items = fake_redis.lrange("consumer:dlq", 0, -1)
    assert len(dlq_items) == 1
    assert "my-plain-password" not in dlq_items[0]


# ============================================================================
# 9. Asynchronous get_health and Multi-Consumer Summary
# ============================================================================

@pytest.mark.asyncio
async def test_get_health_with_live_lag(fake_redis, fake_consumer_manager):
    consumer = ConsumerHealthChecks(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )
    await consumer.start()

    with patch("app.services.kafka.monitoring.kafka_monitoring.consumer_lag") as mock_lag:
        mock_lag.return_value = {
            "topic": "fieldops.events",
            "group_id": "fieldops-health-checks",
            "status": "healthy",
            "lag": 42,
            "partitions": {"0": 42},
        }

        health = await consumer.get_health()

        assert health["status"] == "healthy"
        assert health["connected"] is True
        assert health["ready"] is True
        assert health["lag"]["total_lag"] == 42
        assert health["lag"]["partitions"] == {"0": 42}


@pytest.mark.asyncio
async def test_get_all_consumers_health_summary(fake_redis):
    with patch("app.services.kafka.monitoring.kafka_monitoring.consumer_lag") as mock_lag:
        mock_lag.return_value = {"lag": 0, "status": "healthy"}

        summary = await ConsumerHealthChecks.get_all_consumers_health_summary(redis_client=fake_redis)

        assert summary["status"] == "healthy"
        assert summary["consumer_count"] > 0
        assert "fieldops.job.events" in summary["consumers"]
        assert "fieldops.sla.events" in summary["consumers"]


# ============================================================================
# 10. Celery Tasks and Helpers
# ============================================================================

def test_process_health_checks_event_once_helper(fake_redis):
    # Missing event_id
    bad_res = _process_health_checks_event_once(
        redis=fake_redis,
        event_payload={"tenant_id": "t1"},
        attempt=1,
    )
    assert bad_res["status"] == "FAILED"
    assert bad_res["consumer"] == "Add_health_checks"

    # Valid payload
    payload = {
        "event_id": "evt_celery_health_001",
        "tenant_id": "tenant-celery",
        "schema_version": 1,
    }
    good_res = _process_health_checks_event_once(
        redis=fake_redis,
        event_payload=payload,
        attempt=1,
    )
    assert good_res["status"] == "PROCESSED"
    assert good_res["consumer"] == "Add_health_checks"
    assert good_res["event_id"] == "evt_celery_health_001"

    # Duplicate call
    dup_res = _process_health_checks_event_once(
        redis=fake_redis,
        event_payload=payload,
        attempt=1,
    )
    assert dup_res["status"] == "PROCESSED"
    assert dup_res["idempotent_duplicate"] is True


def test_process_health_checks_event_task(fake_redis):
    with patch("app.tasks.get_redis_client", return_value=fake_redis):
        payload = {
            "event_id": "evt_celery_task_health_001",
            "tenant_id": "tenant-celery",
            "schema_version": 1,
        }
        res = process_health_checks_event_task(payload, attempt=1)
        assert res["status"] == "PROCESSED"
        assert res["consumer"] == "Add_health_checks"

