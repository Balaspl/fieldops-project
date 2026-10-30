"""
test_broker_restart.py

Comprehensive test suite for Story 7.18: Test broker restart during active producer and consumer processing.

Verifies:
- Automated reconnect and retry behavior during broker interruption.
- Offset safety: offsets are never committed prior to successful domain processing.
- Duplicate prevention: idempotency keys prevent duplicate business side effects after redelivery.
- Strict credential redaction across operational telemetry.
- Exact recovery output contract:
    {
        "status": "RECOVERED",
        "event_id": "evt_01JEXAMPLE",
        "retries": 1,
        "idempotent": true,
        "dlq": false
    }
- Celery task integration and FastAPI admin routes.
"""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.services.broker_restart_recovery import (
    BrokerRestartRecovery,
    BrokerRestartReceipt,
    TestBrokerRestart,
    Test_broker_restart,
    ConsumerBrokerRestart,
    BrokerRestartService,
    RestartKafkaBroker,
    BROKER_INTERRUPTION_ERRORS,
)
from app.services.test_broker_restart import (
    BrokerRestartRecovery as DirectBrokerRestartRecovery,
    TestBrokerRestart as DirectTestBrokerRestart,
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
    topic: str = "fieldops.events",
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
# 1. Output Contract & BrokerRestartReceipt Tests
# =============================================================================

def test_broker_restart_receipt_contract():
    """Verify BrokerRestartReceipt complies with required recovery output contract."""
    receipt = BrokerRestartReceipt({
        "status": "RECOVERED",
        "event_id": "evt_01JEXAMPLE",
        "retries": 1,
        "idempotent": True,
        "dlq": False,
    })

    assert receipt["status"] == "RECOVERED"
    assert receipt["event_id"] == "evt_01JEXAMPLE"
    assert receipt["retries"] == 1
    assert receipt["idempotent"] is True
    assert receipt["dlq"] is False
    assert receipt.is_recovered is True
    assert receipt.is_success is True
    assert receipt.is_dlq is False
    assert bool(receipt) is True


def test_broker_restart_receipt_dlq_state():
    """Verify BrokerRestartReceipt dlq state and boolean properties."""
    receipt = BrokerRestartReceipt({
        "status": "FAILED",
        "event_id": "evt_fail",
        "retries": 3,
        "idempotent": False,
        "dlq": True,
    })

    assert receipt.is_success is False
    assert receipt.is_recovered is False
    assert receipt.is_dlq is True
    assert bool(receipt) is True


# =============================================================================
# 2. Authoritative Aliases & Cross-Story Naming Tests
# =============================================================================

def test_broker_restart_aliases_and_names():
    """Verify all class names and canonical aliases are correctly linked."""
    assert TestBrokerRestart is BrokerRestartRecovery
    assert Test_broker_restart is BrokerRestartRecovery
    assert ConsumerBrokerRestart is BrokerRestartRecovery
    assert BrokerRestartService is BrokerRestartRecovery
    assert RestartKafkaBroker is BrokerRestartRecovery
    assert DirectBrokerRestartRecovery is BrokerRestartRecovery
    assert DirectTestBrokerRestart is BrokerRestartRecovery

    coordinator = BrokerRestartRecovery()
    assert coordinator.CONSUMER_NAME == "Test_broker_restart"
    assert coordinator.SCHEMA_VERSION == 1


# =============================================================================
# 3. Producer Interruption & Reconnection Tests
# =============================================================================

@pytest.mark.asyncio
async def test_producer_reconnect_success():
    """Verify producer recovers from transient broker disconnect during restart."""
    BrokerRestartRecovery.reset_metrics()
    coordinator = BrokerRestartRecovery()
    event = make_test_event(event_id="evt_01JEXAMPLE")

    # Mock producer that fails once with connection drop, then succeeds on reconnect
    call_count = 0

    class TransientFailingProducer:
        async def publish(self, msg, topic=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionResetError("Broker restarted - connection dropped")
            return True

    receipt = await coordinator.publish_with_reconnect(
        message=event,
        topic="fieldops.events",
        producer=TransientFailingProducer(),
        max_retries=3,
        retry_delay=0.01,
    )

    # Output contract on recovery
    assert receipt == {
        "status": "RECOVERED",
        "event_id": "evt_01JEXAMPLE",
        "retries": 1,
        "idempotent": True,
        "dlq": False,
    }
    assert receipt.is_recovered is True
    assert receipt.is_success is True

    metrics = BrokerRestartRecovery.get_restart_metrics()
    assert metrics["metrics"]["reconnect_attempts"] == 1
    assert metrics["metrics"]["reconnect_successes"] == 1
    assert metrics["metrics"]["recovered_total"] == 1


@pytest.mark.asyncio
async def test_producer_reconnect_exhaustion():
    """Verify producer exhausts retries and routes to DLQ if broker does not recover."""
    coordinator = BrokerRestartRecovery()
    event = make_test_event(event_id="evt_fail_prod")

    class AlwaysFailingProducer:
        async def publish(self, msg, topic=None):
            raise ConnectionRefusedError("Broker offline indefinitely")

    receipt = await coordinator.publish_with_reconnect(
        message=event,
        topic="fieldops.events",
        producer=AlwaysFailingProducer(),
        max_retries=2,
        retry_delay=0.01,
    )

    assert receipt["status"] == "FAILED"
    assert receipt["dlq"] is True
    assert receipt["retries"] == 3
    assert "exhausted" in receipt["error"].lower()


# =============================================================================
# 4. Consumer Offset Safety & Interruption Recovery Tests
# =============================================================================

@pytest.mark.asyncio
async def test_consumer_offset_committed_only_on_success(fake_redis):
    """Verify consumer manual offset commit is strictly executed ONLY after successful domain processing."""
    mock_consumer_mgr = MagicMock()
    mock_consumer_mgr.commit = AsyncMock()

    coordinator = BrokerRestartRecovery(
        consumer_manager=mock_consumer_mgr,
        redis_client=fake_redis,
    )
    event = make_test_event()

    # Success case: commit is called
    receipt = await coordinator.process_event(event, topic="fieldops.events")
    assert receipt["status"] == "PROCESSED"
    mock_consumer_mgr.commit.assert_awaited_once()

    # Failure case: commit must NOT be called if domain handler fails
    mock_consumer_mgr.commit.reset_mock()
    event_fail = make_test_event(event_id="evt_fail_handler")

    def failing_handler(payload):
        raise ValueError("Domain service interrupted during broker bounce")

    fail_receipt = await coordinator.process_event(
        event_fail,
        topic="fieldops.events",
        handler=failing_handler,
    )
    assert fail_receipt["status"] == "FAILED"
    mock_consumer_mgr.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_recover_event_exact_contract(fake_redis):
    """Verify recover_event returns exact required output contract on recovery."""
    coordinator = BrokerRestartRecovery(redis_client=fake_redis)
    event = make_test_event(event_id="evt_01JEXAMPLE")

    receipt = await coordinator.recover_event(event, topic="fieldops.events", retries_limit=2)

    assert receipt == {
        "status": "RECOVERED",
        "event_id": "evt_01JEXAMPLE",
        "retries": 1,
        "idempotent": True,
        "dlq": False,
    }
    assert receipt.is_recovered is True
    assert receipt.is_success is True


# =============================================================================
# 5. Deduplication & Idempotency Key Across Reconnection
# =============================================================================

@pytest.mark.asyncio
async def test_deduplication_on_redelivery_post_restart(fake_redis):
    """Verify idempotency key prevents duplicate side effects when event is redelivered after broker restart."""
    coordinator = BrokerRestartRecovery(redis_client=fake_redis)
    event = make_test_event(idempotency_key="idem:dispatch:t1:job-101:completed")

    handler_calls = 0

    def domain_handler(payload):
        nonlocal handler_calls
        handler_calls += 1
        return {"status": "SUCCESS"}

    # First delivery succeeds
    receipt1 = await coordinator.process_event(event, topic="fieldops.events", handler=domain_handler)
    assert receipt1["status"] == "PROCESSED"
    assert receipt1["idempotent_duplicate"] is False
    assert handler_calls == 1

    # Second delivery (simulating broker crash right before offset commit ack)
    receipt2 = await coordinator.process_event(event, topic="fieldops.events", handler=domain_handler)
    assert receipt2["status"] == "PROCESSED"
    assert receipt2["idempotent_duplicate"] is True
    # Handler must NOT have run a second time!
    assert handler_calls == 1


# =============================================================================
# 6. Security & Credential Redaction Tests
# =============================================================================

@pytest.mark.asyncio
async def test_forbidden_keys_rejected(fake_redis):
    """Verify payloads with forbidden sensitive keys are rejected to DLQ."""
    coordinator = BrokerRestartRecovery(redis_client=fake_redis)
    event = make_test_event(payload_extra={"password": "raw_insecure_password"})

    receipt = await coordinator.process_event(event, topic="fieldops.events")

    assert receipt["status"] == "FAILED"
    assert receipt["dlq"] is True
    assert "forbidden" in receipt["error"].lower()


def test_metrics_redact_sensitive_data():
    """Verify restart metrics never leak secrets."""
    BrokerRestartRecovery._metrics["test_secret"] = "secret_api_key_value"
    metrics = BrokerRestartRecovery.get_restart_metrics()
    raw_str = json.dumps(metrics)

    assert "secret_api_key_value" not in raw_str


# =============================================================================
# 7. Broker Restart Simulator Verification
# =============================================================================

@pytest.mark.asyncio
async def test_simulate_broker_restart():
    """Verify simulate_broker_restart executes full active disconnect and recovery cycle."""
    coordinator = BrokerRestartRecovery()
    result = await coordinator.simulate_broker_restart(interruption_duration=0.01, fail_attempts=1)

    assert result["status"] == "PASSED"
    assert result["simulation"] == "broker_restart"
    assert result["reconnect_verified"] is True
    assert result["offset_safe"] is True
    assert result["attempts_tracked"] == 2


# =============================================================================
# 8. Celery Task Execution Tests
# =============================================================================

def test_celery_task_execution(fake_redis):
    """Verify Celery tasks invoke BrokerRestartRecovery correctly."""
    from app.tasks import (
        _process_broker_restart_recovery_once,
        process_broker_restart_recovery_task,
        test_broker_restart_task,
    )
    event = make_test_event(event_id="evt_celery_restart")

    with patch("app.services.broker_restart_recovery.get_redis_client", return_value=fake_redis):
        result_once = _process_broker_restart_recovery_once(
            raw_message=json.dumps(event),
            topic="fieldops.events",
            redis_client=fake_redis,
        )
        assert result_once["status"] == "PROCESSED"
        assert result_once["event_id"] == "evt_celery_restart"

        with patch("app.tasks.get_redis_client", return_value=fake_redis):
            res1 = process_broker_restart_recovery_task(
                raw_message=json.dumps(event),
                topic="fieldops.events",
            )
            assert res1["status"] == "PROCESSED"

            res2 = test_broker_restart_task(
                raw_message=json.dumps(event),
                topic="fieldops.events",
            )
            assert res2["status"] == "PROCESSED"


# =============================================================================
# 9. FastAPI Admin Metrics Route Integration
# =============================================================================

@pytest.mark.asyncio
async def test_admin_metrics_broker_restart_routes(fake_redis):
    """Verify /admin/metrics/kafka/broker-restart endpoints return metrics and simulation results."""
    from app.routes.admin_metrics import (
        get_kafka_broker_restart_metrics,
        simulate_kafka_broker_restart,
    )

    with patch("app.services.broker_restart_recovery.get_redis_client", return_value=fake_redis):
        metrics = await get_kafka_broker_restart_metrics()
        assert metrics["status"] == "healthy"
        assert metrics["coordinator"] == "Test_broker_restart"
        assert "reconnect_attempts" in metrics["metrics"]

        simulation = await simulate_kafka_broker_restart()
        assert simulation["status"] == "PASSED"
        assert simulation["reconnect_verified"] is True

