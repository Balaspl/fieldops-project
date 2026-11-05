"""
test_kafka_failure_recovery.py

Comprehensive test suite for Story 7.20: Test Kafka failure recovery.
Simulate broker, network, and downstream failures and verify recovery
without event loss, duplicate business actions, or secret exposure.

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

from app.services.kafka_failure_recovery import (
    KafkaFailureRecoveryCoordinator,
    KafkaFailureRecoveryReceipt,
    TestKafkaFailureRecovery,
    Test_kafka_failure_recovery,
    KafkaFailureRecovery,
    KafkaFailureRecoveryService,
    KafkaFailureRecoveryManager,
    FailureMode,
)
from app.services.test_kafka_failure_recovery import (
    KafkaFailureRecoveryCoordinator as DirectCoordinator,
    TestKafkaFailureRecovery as DirectTestKafkaFailureRecovery,
    Test_kafka_failure_recovery as DirectTest_kafka_failure_recovery,
    KafkaFailureRecoveryReceipt as DirectReceipt,
)


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
        "job_id": 101,
        "status": "ASSIGNED",
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
# 1. Output Contract & Receipt Verification
# =============================================================================

def test_kafka_failure_recovery_receipt_contract():
    """Verify KafkaFailureRecoveryReceipt strictly conforms to Story 7.20 contract."""
    receipt = KafkaFailureRecoveryReceipt(
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


def test_kafka_failure_recovery_receipt_dlq_state():
    """Verify receipt in DLQ state behaves correctly."""
    receipt = KafkaFailureRecoveryReceipt(
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
# 2. Authoritative Class Aliases & Cross-Story Naming Tests
# =============================================================================

def test_kafka_failure_recovery_aliases_and_names():
    """Verify all class aliases and cross-story compatibility links."""
    assert TestKafkaFailureRecovery is KafkaFailureRecoveryCoordinator
    assert Test_kafka_failure_recovery is KafkaFailureRecoveryCoordinator
    assert KafkaFailureRecovery is KafkaFailureRecoveryCoordinator
    assert KafkaFailureRecoveryService is KafkaFailureRecoveryCoordinator
    assert KafkaFailureRecoveryManager is KafkaFailureRecoveryCoordinator
    assert DirectCoordinator is KafkaFailureRecoveryCoordinator
    assert DirectTestKafkaFailureRecovery is KafkaFailureRecoveryCoordinator
    assert DirectTest_kafka_failure_recovery is KafkaFailureRecoveryCoordinator
    assert DirectReceipt is KafkaFailureRecoveryReceipt

    coordinator = KafkaFailureRecoveryCoordinator()
    assert coordinator.CONSUMER_NAME == "Test_kafka_failure_recovery"
    assert coordinator.SCHEMA_VERSION == 1


# =============================================================================
# 3. Broker Failure Simulation & Recovery
# =============================================================================

@pytest.mark.asyncio
async def test_broker_failure_simulation_and_recovery(fake_redis):
    """Verify transient broker disconnection halts commit, and re-attempt recovers safely."""
    KafkaFailureRecoveryCoordinator.reset_metrics()
    coordinator = KafkaFailureRecoveryCoordinator(redis_client=fake_redis, backoff_seconds=0.001)
    event = make_test_event(event_id="evt_broker_fail")
    topic = "fieldops.jobs"
    partition = 0
    offset = 42

    # Attempt 1: Broker failure is simulated
    with pytest.raises(ConnectionResetError):
        await coordinator.process_event(
            message=event,
            topic=topic,
            partition=partition,
            offset=offset,
            attempt=1,
            simulate_failure_mode="broker",
        )

    # Offset must NOT be committed during failure
    assert coordinator.get_committed_offset(topic, partition) == 0
    metrics = coordinator.get_failure_metrics()
    assert metrics["broker_failures_simulated_total"] >= 1

    # Attempt 2: Broker reconnects and recovers
    receipt = await coordinator.process_event(
        message=event,
        topic=topic,
        partition=partition,
        offset=offset,
        attempt=1,
        simulate_failure_mode=None,
    )

    assert receipt["status"] == "RECOVERED"
    assert receipt["event_id"] == "evt_broker_fail"
    assert receipt["dlq"] is False
    # Offset is now committed
    assert coordinator.get_committed_offset(topic, partition) == offset


# =============================================================================
# 4. Network Failure Simulation & Recovery
# =============================================================================

@pytest.mark.asyncio
async def test_network_failure_simulation_and_recovery(fake_redis):
    """Verify transient network socket timeout is handled cleanly."""
    KafkaFailureRecoveryCoordinator.reset_metrics()
    coordinator = KafkaFailureRecoveryCoordinator(redis_client=fake_redis, backoff_seconds=0.001)
    event = make_test_event(event_id="evt_network_fail")
    topic = "fieldops.jobs"
    partition = 1
    offset = 77

    # Attempt 1: Network timeout
    with pytest.raises(Exception):
        await coordinator.process_event(
            message=event,
            topic=topic,
            partition=partition,
            offset=offset,
            attempt=1,
            simulate_failure_mode="network",
        )

    assert coordinator.get_committed_offset(topic, partition) == 0
    metrics = coordinator.get_failure_metrics()
    assert metrics["network_failures_simulated_total"] >= 1

    # Attempt 2: Network restores and resumes
    receipt = await coordinator.process_event(
        message=event,
        topic=topic,
        partition=partition,
        offset=offset,
        attempt=1,
        simulate_failure_mode=None,
    )

    assert receipt["status"] == "RECOVERED"
    assert coordinator.get_committed_offset(topic, partition) == offset


# =============================================================================
# 5. Downstream Dependency Failure Simulation & Recovery
# =============================================================================

@pytest.mark.asyncio
async def test_downstream_failure_simulation_and_recovery(fake_redis):
    """Verify downstream database / HTTP dependency failures trigger bounded retry."""
    KafkaFailureRecoveryCoordinator.reset_metrics()
    coordinator = KafkaFailureRecoveryCoordinator(redis_client=fake_redis, backoff_seconds=0.001)
    event = make_test_event(event_id="evt_downstream_fail")
    topic = "fieldops.jobs"
    partition = 0
    offset = 120

    # Attempt 1: Downstream 500 error
    with pytest.raises(RuntimeError):
        await coordinator.process_event(
            message=event,
            topic=topic,
            partition=partition,
            offset=offset,
            attempt=1,
            simulate_failure_mode="downstream",
        )

    assert coordinator.get_committed_offset(topic, partition) == 0
    metrics = coordinator.get_failure_metrics()
    assert metrics["downstream_failures_simulated_total"] >= 1

    # Attempt 2: Downstream dependency recovers
    receipt = await coordinator.process_event(
        message=event,
        topic=topic,
        partition=partition,
        offset=offset,
        attempt=1,
        simulate_failure_mode=None,
    )

    assert receipt["status"] == "RECOVERED"
    assert coordinator.get_committed_offset(topic, partition) == offset


# =============================================================================
# 6. Idempotency & Duplicate Prevention Post-Recovery
# =============================================================================

@pytest.mark.asyncio
async def test_idempotency_prevents_duplicate_business_actions(fake_redis):
    """Verify redelivered messages post-failure do not duplicate domain side effects."""
    coordinator = KafkaFailureRecoveryCoordinator(redis_client=fake_redis)
    event_id = "evt_idempotency_proof"
    event = make_test_event(event_id=event_id, idempotency_key="key-proof-1")

    domain_actions_run = 0

    async def domain_handler(msg):
        nonlocal domain_actions_run
        domain_actions_run += 1
        return {"action": "dispatched"}

    # Run 1: First successful execution
    receipt1 = await coordinator.process_event(
        message=event,
        topic="fieldops.jobs",
        partition=0,
        offset=88,
        attempt=1,
        handler=domain_handler,
    )
    assert domain_actions_run == 1
    assert receipt1["status"] == "RECOVERED"

    # Run 2: Redelivery after broker/network disruption
    receipt2 = await coordinator.process_event(
        message=event,
        topic="fieldops.jobs",
        partition=0,
        offset=88,
        attempt=1,
        handler=domain_handler,
    )

    # Domain handler must NOT have executed again
    assert domain_actions_run == 1
    assert receipt2["status"] == "RECOVERED"
    assert receipt2["idempotent"] is True
    assert receipt2["dlq"] is False


# =============================================================================
# 7. Audit Evidence Capture & Verification
# =============================================================================

def test_evidence_capture_and_auditing(fake_redis):
    """Verify structured audit evidence records offsets, retries, DLQ, and replay."""
    coordinator = KafkaFailureRecoveryCoordinator(redis_client=fake_redis)
    event_id = "evt_evidence_audit_100"

    evidence = coordinator.record_evidence(
        event_id=event_id,
        failure_mode="network",
        initial_offset=50,
        committed_offset=50,
        retries=2,
        idempotent=True,
        dlq=False,
        replay=True,
    )

    assert evidence["event_id"] == event_id
    assert evidence["failure_mode"] == "network"
    assert evidence["retries"] == 2
    assert evidence["idempotent"] is True
    assert evidence["replay"] is True

    retrieved = coordinator.get_evidence(event_id=event_id)
    assert len(retrieved) == 1
    assert retrieved[0]["event_id"] == event_id


# =============================================================================
# 8. DLQ Routing on Retries Exhaustion
# =============================================================================

@pytest.mark.asyncio
async def test_dlq_routing_on_max_retries_exhaustion(fake_redis):
    """Verify exhausted retries route to DLQ with safe offset commit."""
    mock_producer = MagicMock()
    mock_producer.publish = AsyncMock()

    coordinator = KafkaFailureRecoveryCoordinator(
        redis_client=fake_redis,
        producer=mock_producer,
        max_retries=2,
    )
    event = make_test_event(event_id="evt_poison_exhausted")

    async def fatal_handler(msg):
        raise ValueError("Fatal corrupt payload")

    receipt = await coordinator.process_event(
        message=event,
        topic="fieldops.jobs",
        partition=0,
        offset=999,
        attempt=2,  # reaches max_retries
        handler=fatal_handler,
    )

    assert receipt["status"] == "FAILED"
    assert receipt["dlq"] is True
    assert receipt["retries"] == 2
    # Offset must be committed to prevent endless loop
    assert coordinator.get_committed_offset("fieldops.jobs", 0) == 999


# =============================================================================
# 9. Fail-Closed Security & Forbidden Keys Rejection
# =============================================================================

@pytest.mark.asyncio
async def test_forbidden_keys_rejected(fake_redis):
    """Verify events containing sensitive secrets are rejected immediately to DLQ."""
    coordinator = KafkaFailureRecoveryCoordinator(redis_client=fake_redis)
    event = make_test_event(
        event_id="evt_secret_violation",
        payload_extra={
            "client_secret": "super_secret_credential",
            "password": "unhashed_password",
        },
    )

    receipt = await coordinator.process_event(
        message=event,
        topic="fieldops.jobs",
        partition=0,
        offset=33,
        attempt=1,
    )

    assert receipt["status"] == "FAILED"
    assert receipt["dlq"] is True
    assert "forbidden" in receipt.get("error", "").lower()

    # Verify secrets are redacted from serialized output
    raw_str = json.dumps(dict(receipt))
    assert "super_secret_credential" not in raw_str
    assert "unhashed_password" not in raw_str


def test_metrics_redact_sensitive_keys():
    """Verify metrics never leak secret keys."""
    KafkaFailureRecoveryCoordinator._metrics["api_key_secret"] = "leaked_secret"
    metrics = KafkaFailureRecoveryCoordinator.get_failure_metrics()
    assert "api_key_secret" not in json.dumps(metrics)


# =============================================================================
# 10. End-to-End Simulation of Realistic Failure Recovery
# =============================================================================

@pytest.mark.asyncio
async def test_simulate_kafka_failure_recovery_e2e(fake_redis):
    """Verify full end-to-end failure injection and recovery satisfies contract."""
    coordinator = KafkaFailureRecoveryCoordinator(redis_client=fake_redis, backoff_seconds=0.001)

    receipt = await coordinator.simulate_kafka_failure_recovery(failure_mode="all")

    assert isinstance(receipt, (dict, KafkaFailureRecoveryReceipt))
    assert receipt["status"] == "RECOVERED"
    assert receipt["event_id"].startswith("evt_01J")
    assert receipt["retries"] == 1
    assert receipt["idempotent"] is True
    assert receipt["dlq"] is False

    # Verify audit evidence was captured
    evidence = coordinator.get_evidence(event_id=receipt["event_id"])
    assert len(evidence) >= 1
    assert evidence[0]["status"] if "status" in evidence[0] else True


# =============================================================================
# 11. Celery Background Task Execution
# =============================================================================

def test_celery_kafka_failure_recovery_tasks(fake_redis):
    """Verify Celery task functions execute cleanly with fake redis."""
    from app.tasks import (
        _process_kafka_failure_recovery_once,
        process_kafka_failure_recovery_task,
        test_kafka_failure_recovery_task,
    )

    event = make_test_event(event_id="evt_celery_failure")

    result = _process_kafka_failure_recovery_once(
        event_payload=event,
        topic="fieldops.jobs",
        partition=0,
        offset=15,
        attempt=1,
        redis=fake_redis,
    )

    assert result["status"] == "RECOVERED"
    assert result["event_id"] == "evt_celery_failure"
    assert result["dlq"] is False

    with patch("app.tasks.get_redis_client", return_value=fake_redis):
        res1 = process_kafka_failure_recovery_task(
            event_payload=event,
            topic="fieldops.jobs",
            partition=0,
            offset=15,
            attempt=1,
        )
        assert res1["status"] == "RECOVERED"

        res2 = test_kafka_failure_recovery_task(
            event_payload=event,
            topic="fieldops.jobs",
            partition=0,
            offset=15,
            attempt=1,
        )
        assert res2["status"] == "RECOVERED"


# =============================================================================
# 12. Admin Metrics & Simulation API Routes
# =============================================================================

@pytest.mark.asyncio
async def test_admin_metrics_kafka_failure_recovery_endpoints(fake_redis):
    """Verify admin metrics and simulation endpoints return healthy state and contract."""
    from app.routes.admin_metrics import (
        get_kafka_failure_recovery_metrics,
        simulate_kafka_failure_recovery,
        get_kafka_failure_recovery_evidence,
    )

    with patch("app.services.kafka_failure_recovery.get_redis_client", return_value=fake_redis):
        # 1. Metrics route
        metrics = await get_kafka_failure_recovery_metrics()
        assert metrics["status"] == "HEALTHY"
        assert "recovered_total" in metrics

        # 2. Simulation route
        simulation = await simulate_kafka_failure_recovery(failure_mode="all")
        assert simulation["status"] == "RECOVERED"
        assert simulation["retries"] == 1
        assert simulation["idempotent"] is True
        assert simulation["dlq"] is False

        # 3. Evidence route
        evidence = await get_kafka_failure_recovery_evidence()
        assert isinstance(evidence, list)

