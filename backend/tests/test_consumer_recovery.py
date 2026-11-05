"""
test_consumer_recovery.py

Comprehensive test suite for Story 7.19: Test consumer recovery.
Stop/restart consumers during event processing and verify they resume correctly.
Prove consumer groups recover while maintaining idempotency and ordering guarantees.

Contract / Expected Output:
{
    "status": "RECOVERED",
    "event_id": "evt_01JEXAMPLE",
    "retries": 1,
    "idempotent": true,
    "dlq": false
}
"""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.services.consumer_recovery import (
    ConsumerRecoveryCoordinator,
    ConsumerRecoveryReceipt,
    TestConsumerRecovery,
    Test_consumer_recovery,
    ConsumerRecoveryService,
    ConsumerRecoveryManager,
)
from app.services.test_consumer_recovery import (
    ConsumerRecoveryCoordinator as DirectCoordinator,
    TestConsumerRecovery as DirectTestConsumerRecovery,
    Test_consumer_recovery as DirectTest_consumer_recovery,
    ConsumerRecoveryReceipt as DirectReceipt,
)
from app.services.consumer_error_handler import ErrorClassification


# =============================================================================
# Fake Redis Fixtures & Message Helpers
# =============================================================================

class FakeRedis:
    def __init__(self):
        self.store = {}
        self.lists = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None, nx=False):
        if nx and key in self.store:
            return None
        self.store[key] = str(value)
        return True

    def delete(self, *keys):
        count = 0
        for k in keys:
            if k in self.store:
                del self.store[k]
                count += 1
            if k in self.lists:
                del self.lists[k]
                count += 1
        return count

    def llen(self, key):
        return len(self.lists.get(key, []))

    def rpush(self, key, *values):
        if key not in self.lists:
            self.lists[key] = []
        for val in values:
            self.lists[key].append(str(val))
        return len(self.lists[key])

    def lrange(self, key, start, end):
        lst = self.lists.get(key, [])
        if end == -1:
            return lst[start:]
        return lst[start : end + 1]


@pytest.fixture
def fake_redis():
    return FakeRedis()


def make_test_event(
    event_id: str = "evt_01JEXAMPLE",
    tenant_id: str = "tenant-1",
    correlation_id: str = "corr-101",
    domain: str = "dispatch",
    schema_version: int = 1,
    idempotency_key: str = None,
    payload_extra: dict = None,
    topic: str = "fieldops.jobs",
) -> dict:
    payload = {
        "event_id": event_id,
        "tenant_id": tenant_id,
        "schema_version": schema_version,
        "correlation_id": correlation_id,
        "domain": domain,
        "job_id": "job-101",
        "status": "COMPLETED",
    }
    if idempotency_key:
        payload["idempotency_key"] = idempotency_key
    if payload_extra:
        payload.update(payload_extra)
    return {
        "event_id": event_id,
        "tenant_id": tenant_id,
        "schema_version": schema_version,
        "correlation_id": correlation_id,
        "topic": topic,
        "payload": payload,
    }


# =============================================================================
# 1. Output Contract & ConsumerRecoveryReceipt Tests
# =============================================================================

def test_consumer_recovery_receipt_contract():
    """Verify ConsumerRecoveryReceipt strictly satisfies the Story 7.19 contract."""
    receipt = ConsumerRecoveryReceipt(
        status="RECOVERED",
        event_id="evt_01JEXAMPLE",
        retries=1,
        idempotent=True,
        dlq=False,
    )

    assert receipt["status"] == "RECOVERED"
    assert receipt["event_id"] == "evt_01JEXAMPLE"
    assert receipt["retries"] == 1
    assert receipt["idempotent"] is True
    assert receipt["dlq"] is False
    assert receipt.is_recovered is True
    assert receipt.is_success is True
    assert receipt.is_dlq is False
    assert bool(receipt) is True


def test_consumer_recovery_receipt_failed_dlq_state():
    """Verify receipt in DLQ state behaves correctly."""
    receipt = ConsumerRecoveryReceipt(
        status="FAILED",
        event_id="evt_poison",
        retries=3,
        idempotent=False,
        dlq=True,
    )

    assert receipt["status"] == "FAILED"
    assert receipt["dlq"] is True
    assert receipt.is_dlq is True
    assert receipt.is_recovered is False
    assert receipt.is_success is False


# =============================================================================
# 2. Authoritative Aliases & Cross-Story Naming Tests
# =============================================================================

def test_consumer_recovery_aliases_and_names():
    """Verify all class aliases and cross-story compatibility links."""
    assert TestConsumerRecovery is ConsumerRecoveryCoordinator
    assert Test_consumer_recovery is ConsumerRecoveryCoordinator
    assert ConsumerRecoveryService is ConsumerRecoveryCoordinator
    assert ConsumerRecoveryManager is ConsumerRecoveryCoordinator
    assert DirectCoordinator is ConsumerRecoveryCoordinator
    assert DirectTestConsumerRecovery is ConsumerRecoveryCoordinator
    assert DirectTest_consumer_recovery is ConsumerRecoveryCoordinator
    assert DirectReceipt is ConsumerRecoveryReceipt

    coordinator = ConsumerRecoveryCoordinator()
    assert coordinator.CONSUMER_NAME == "Test_consumer_recovery"
    assert coordinator.SCHEMA_VERSION == 1


# =============================================================================
# 3. Stop / Restart State Transition Tests
# =============================================================================

def test_consumer_stop_and_restart_state_transitions(fake_redis):
    """Verify consumers transition through RUNNING -> STOPPED -> RESTARTING -> RUNNING."""
    ConsumerRecoveryCoordinator.reset_metrics()
    coordinator = ConsumerRecoveryCoordinator(redis_client=fake_redis)
    consumer_id = "cons-001"
    group_id = "grp-dispatch"

    assert coordinator.is_consumer_running(consumer_id, group_id) is True

    # Stop consumer with in-flight uncommitted messages
    coordinator.stop_consumer(
        consumer_id=consumer_id,
        group_id=group_id,
        reason="node_maintenance",
        uncommitted_events=[{"event_id": "evt-uncommitted-1"}],
    )
    assert coordinator.is_consumer_running(consumer_id, group_id) is False

    metrics = coordinator.get_recovery_metrics()
    assert metrics["consumers_stopped_total"] >= 1

    # Restart consumer
    coordinator.restart_consumer(consumer_id=consumer_id, group_id=group_id)
    assert coordinator.is_consumer_running(consumer_id, group_id) is True

    metrics = coordinator.get_recovery_metrics()
    assert metrics["consumers_restarted_total"] >= 1


# =============================================================================
# 4. Offset Recovery & Resume Semantics Tests
# =============================================================================

@pytest.mark.asyncio
async def test_consumer_recovery_resumes_from_committed_offset(fake_redis):
    """Verify consumer restarts resume from last committed offset without loss."""
    coordinator = ConsumerRecoveryCoordinator(redis_client=fake_redis)
    topic = "fieldops.jobs"
    partition = 0
    group_id = "grp-test"
    consumer_id = "cons-01"

    # Commit offset 100
    coordinator.commit_offset(topic, partition, 100, group_id=group_id)
    assert coordinator.get_committed_offset(topic, partition, group_id=group_id) == 100

    # In-flight event at offset 101 arrives
    event = make_test_event(event_id="evt_inflight_101", topic=topic)
    coordinator.record_uncommitted_message(topic, partition, 101, event, consumer_id=consumer_id, group_id=group_id)

    uncommitted = coordinator.get_uncommitted_messages(topic, partition, consumer_id=consumer_id, group_id=group_id)
    assert len(uncommitted) == 1
    assert uncommitted[0]["offset"] == 101

    # Stop consumer mid-processing
    coordinator.stop_consumer(consumer_id=consumer_id, group_id=group_id, reason="interruption")

    # Restart consumer: committed offset is still 100 (never committed early)
    coordinator.restart_consumer(consumer_id=consumer_id, group_id=group_id)
    assert coordinator.get_committed_offset(topic, partition, group_id=group_id) == 100

    # Process redelivered offset 101
    receipt = await coordinator.process_event(
        message=event,
        topic=topic,
        partition=partition,
        offset=101,
        attempt=1,
        consumer_id=consumer_id,
        group_id=group_id,
    )

    assert receipt["status"] == "RECOVERED"
    assert receipt["event_id"] == "evt_inflight_101"
    assert receipt["retries"] == 1
    assert receipt["dlq"] is False
    assert coordinator.get_committed_offset(topic, partition, group_id=group_id) == 101


# =============================================================================
# 5. Idempotency & Duplicate Side Effect Prevention Tests
# =============================================================================

@pytest.mark.asyncio
async def test_idempotency_deduplication_post_recovery(fake_redis):
    """Verify redelivered events during recovery do not re-execute business logic."""
    coordinator = ConsumerRecoveryCoordinator(redis_client=fake_redis)
    event_id = "evt_idempotent_test"
    event = make_test_event(event_id=event_id, idempotency_key="idem-key-999")

    handler_call_count = 0

    async def sample_handler(msg):
        nonlocal handler_call_count
        handler_call_count += 1
        return {"processed": True}

    # Initial processing
    receipt1 = await coordinator.process_event(
        message=event,
        topic="fieldops.jobs",
        partition=0,
        offset=50,
        attempt=0,
        handler=sample_handler,
    )
    assert handler_call_count == 1
    assert receipt1["status"] in ("PROCESSED", "RECOVERED")

    # Consumer crashes and restarts
    coordinator.stop_consumer(reason="crash")
    coordinator.restart_consumer()

    # Redelivered event after restart
    receipt2 = await coordinator.process_event(
        message=event,
        topic="fieldops.jobs",
        partition=0,
        offset=50,
        attempt=1,
        handler=sample_handler,
    )

    # Handler must NOT have been called a second time
    assert handler_call_count == 1
    assert receipt2["status"] == "RECOVERED"
    assert receipt2["idempotent"] is True
    assert receipt2["dlq"] is False


# =============================================================================
# 6. Event Ordering Guarantee Tests
# =============================================================================

@pytest.mark.asyncio
async def test_partition_event_ordering_guarantee(fake_redis):
    """Verify ordered sequence numbers are enforced per partition."""
    ConsumerRecoveryCoordinator.reset_metrics()
    coordinator = ConsumerRecoveryCoordinator(redis_client=fake_redis)
    topic = "fieldops.jobs"

    # Sequential events
    evt1 = make_test_event(event_id="evt_seq_1", payload_extra={"sequence_number": 1})
    evt2 = make_test_event(event_id="evt_seq_2", payload_extra={"sequence_number": 2})
    evt3 = make_test_event(event_id="evt_seq_3", payload_extra={"sequence_number": 3})

    await coordinator.process_event(evt1, topic=topic, partition=0, offset=1)
    await coordinator.process_event(evt2, topic=topic, partition=0, offset=2)
    await coordinator.process_event(evt3, topic=topic, partition=0, offset=3)

    metrics = coordinator.get_recovery_metrics()
    assert metrics["out_of_order_total"] == 0

    # Gap/out-of-order event: sequence 5 arrives when expecting 4
    evt5 = make_test_event(event_id="evt_seq_5", payload_extra={"sequence_number": 5})
    await coordinator.process_event(evt5, topic=topic, partition=0, offset=4)

    metrics = coordinator.get_recovery_metrics()
    assert metrics["out_of_order_total"] >= 1


# =============================================================================
# 7. DLQ Routing on Terminal / Poison Pill Failures
# =============================================================================

@pytest.mark.asyncio
async def test_dlq_routing_on_max_retries_exhaustion(fake_redis):
    """Verify exhausted retries route to DLQ with dlq=True."""
    mock_producer = MagicMock()
    mock_producer.publish = AsyncMock()
    coordinator = ConsumerRecoveryCoordinator(
        redis_client=fake_redis,
        producer=mock_producer,
        max_retries=2,
    )
    event = make_test_event(event_id="evt_poison_pill")

    async def failing_handler(msg):
        raise ValueError("Fatal payload corruption")

    receipt = await coordinator.process_event(
        message=event,
        topic="fieldops.jobs",
        partition=0,
        offset=99,
        attempt=2,  # reaches max_retries
        handler=failing_handler,
    )

    assert receipt["status"] == "FAILED"
    assert receipt["dlq"] is True
    assert receipt["retries"] == 2


# =============================================================================
# 8. Zero-Leak Security & Forbidden Keys Redaction
# =============================================================================

@pytest.mark.asyncio
async def test_forbidden_keys_rejected(fake_redis):
    """Verify payloads with forbidden sensitive keys are rejected to DLQ."""
    coordinator = ConsumerRecoveryCoordinator(redis_client=fake_redis)
    event = make_test_event(
        event_id="evt_secret_test",
        payload_extra={
            "client_secret": "super_secret_key_12345",
            "password": "tech_password_abc",
        },
    )

    receipt = await coordinator.process_event(
        message=event,
        topic="fieldops.jobs",
        partition=0,
        offset=12,
        attempt=1,
    )

    assert receipt["status"] == "FAILED"
    assert receipt["dlq"] is True
    assert "forbidden" in receipt.get("error", "").lower()
    receipt_str = json.dumps(dict(receipt))
    assert "super_secret_key_12345" not in receipt_str
    assert "tech_password_abc" not in receipt_str


def test_metrics_redact_sensitive_data():
    """Verify recovery metrics never leak secrets."""
    ConsumerRecoveryCoordinator._metrics["test_secret_key"] = 999
    metrics = ConsumerRecoveryCoordinator.get_recovery_metrics()
    raw_str = json.dumps(metrics)
    assert "test_secret_key" not in raw_str


# =============================================================================
# 9. End-to-End Consumer Recovery Simulation
# =============================================================================

@pytest.mark.asyncio
async def test_simulate_consumer_recovery_e2e(fake_redis):
    """Verify the full stop/restart simulation executes cleanly and returns contract."""
    coordinator = ConsumerRecoveryCoordinator(redis_client=fake_redis)
    receipt = await coordinator.simulate_consumer_recovery(
        consumer_id="cons-sim-1",
        group_id="grp-sim-1",
        topic="fieldops.jobs",
        num_events=3,
    )

    assert isinstance(receipt, (dict, ConsumerRecoveryReceipt))
    assert receipt["status"] == "RECOVERED"
    assert receipt["event_id"].startswith("evt_")
    assert receipt["retries"] == 1
    assert receipt["idempotent"] is True
    assert receipt["dlq"] is False


# =============================================================================
# 10. Operational Visibility & Group State
# =============================================================================

def test_consumer_group_state_and_metrics(fake_redis):
    """Verify operational health and metrics reporting."""
    coordinator = ConsumerRecoveryCoordinator(redis_client=fake_redis)
    state = coordinator.get_consumer_group_state(group_id="grp-ops", topic="job.events")

    assert state["group_id"] == "grp-ops"
    assert state["topic"] == "job.events"
    assert state["status"] == "HEALTHY"
    assert "committed_offset" in state
    assert "lag" in state

    metrics = ConsumerRecoveryCoordinator.get_recovery_metrics()
    assert metrics["status"] == "HEALTHY"
    assert "consumers_stopped_total" in metrics
    assert "consumers_restarted_total" in metrics
    assert "events_recovered_total" in metrics


# =============================================================================
# 11. Celery Task Execution
# =============================================================================

def test_celery_consumer_recovery_tasks(fake_redis):
    """Verify Celery task wrappers execute correctly and return recovery receipt."""
    from app.tasks import (
        _process_consumer_recovery_once,
        process_consumer_recovery_task,
        test_consumer_recovery_task,
    )

    event = make_test_event(event_id="evt_celery_rec")

    # Direct function invocation with fake redis
    result = _process_consumer_recovery_once(
        event_payload=event,
        topic="fieldops.jobs",
        partition=0,
        offset=25,
        attempt=1,
        redis=fake_redis,
    )

    assert result["status"] == "RECOVERED"
    assert result["event_id"] == "evt_celery_rec"
    assert result["retries"] == 1
    assert result["dlq"] is False

    with patch("app.tasks.get_redis_client", return_value=fake_redis):
        res1 = process_consumer_recovery_task(
            event_payload=event,
            topic="fieldops.jobs",
            partition=0,
            offset=25,
            attempt=1,
        )
        assert res1["status"] == "RECOVERED"

        res2 = test_consumer_recovery_task(
            event_payload=event,
            topic="fieldops.jobs",
            partition=0,
            offset=25,
            attempt=1,
        )
        assert res2["status"] == "RECOVERED"


# =============================================================================
# 12. Admin Metrics API Routes
# =============================================================================

@pytest.mark.asyncio
async def test_admin_metrics_consumer_recovery_endpoints(fake_redis):
    """Verify admin metrics endpoints return healthy metrics and recovery contract."""
    from app.routes.admin_metrics import (
        get_kafka_consumer_recovery_metrics,
        simulate_kafka_consumer_recovery,
    )

    with patch("app.services.consumer_recovery.get_redis_client", return_value=fake_redis):
        metrics = await get_kafka_consumer_recovery_metrics()
        assert metrics["status"] == "HEALTHY"
        assert "consumers_stopped_total" in metrics
        assert "events_recovered_total" in metrics

        simulation = await simulate_kafka_consumer_recovery()
        assert simulation["status"] == "RECOVERED"
        assert simulation["retries"] == 1
        assert simulation["idempotent"] is True
        assert simulation["dlq"] is False
