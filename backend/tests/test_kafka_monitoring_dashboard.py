"""
test_kafka_monitoring_dashboard.py

Comprehensive test suite for Kafka monitoring dashboard:
- Operational visibility for broker status, topic throughput, consumer lag,
  failures, DLQ volume, and recovery state.
- Exact output contract verification on recovery:
    {
        "status": "RECOVERED",
        "event_id": "evt_01JEXAMPLE",
        "retries": 1,
        "idempotent": True,
        "dlq": False
    }
- Strict credential redaction across dashboard telemetry.
- Tenant-safe filtering.
- End-to-end integration with Celery tasks and FastAPI admin endpoints.
"""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.redis_client import get_redis_client
from app.services.kafka_monitoring_dashboard import (
    KafkaMonitoringDashboard,
    DashboardReceipt,
    AddKafkaMonitoringDashboard,
    Add_kafka_monitoring_dashboard,
    ConsumerKafkaMonitoringDashboard,
    KafkaDashboardService,
)
from app.services.add_kafka_monitoring_dashboard import (
    KafkaMonitoringDashboard as DirectKafkaMonitoringDashboard,
    AddKafkaMonitoringDashboard as DirectAddKafkaMonitoringDashboard,
)
from app.services.failed_event_storage import FailedEventStorage
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
# 1. Output Contract & DashboardReceipt Tests
# =============================================================================

def test_dashboard_receipt_contract():
    """Verify DashboardReceipt complies with required recovery output contract."""
    receipt = DashboardReceipt({
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


def test_dashboard_receipt_dlq_state():
    """Verify DashboardReceipt dlq properties."""
    receipt = DashboardReceipt({
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

def test_dashboard_aliases_and_names():
    """Verify all class names and canonical aliases are correctly linked."""
    assert AddKafkaMonitoringDashboard is KafkaMonitoringDashboard
    assert Add_kafka_monitoring_dashboard is KafkaMonitoringDashboard
    assert ConsumerKafkaMonitoringDashboard is KafkaMonitoringDashboard
    assert KafkaDashboardService is KafkaMonitoringDashboard
    assert DirectKafkaMonitoringDashboard is KafkaMonitoringDashboard
    assert DirectAddKafkaMonitoringDashboard is KafkaMonitoringDashboard

    dashboard = KafkaMonitoringDashboard()
    assert dashboard.CONSUMER_NAME == "Add_kafka_monitoring_dashboard"
    assert dashboard.SCHEMA_VERSION == 1


# =============================================================================
# 3. Operational Dashboard Summary & Telemetry Aggregation
# =============================================================================

@pytest.mark.asyncio
async def test_get_dashboard_summary_aggregation(fake_redis):
    """Verify get_dashboard_summary aggregates broker, throughput, lag, dlq, and recovery."""
    dashboard = KafkaMonitoringDashboard(redis_client=fake_redis)

    # Populate some DLQ volume in fake redis
    fake_redis.rpush("consumer:dlq", json.dumps({"event_id": "evt-dlq-1"}))
    fake_redis.rpush("consumer:dlq", json.dumps({"event_id": "evt-dlq-2"}))

    summary = await dashboard.get_dashboard_summary()

    assert "status" in summary
    assert "broker" in summary
    assert "throughput" in summary
    assert "consumer_lag" in summary
    assert "failures" in summary
    assert "dlq" in summary
    assert "recovery" in summary
    assert "timestamp" in summary

    # Check broker section
    assert "status" in summary["broker"]
    assert "connected" in summary["broker"]
    assert "broker_count" in summary["broker"]

    # Check throughput section
    assert "published_total" in summary["throughput"]
    assert "consumed_total" in summary["throughput"]

    # Check dlq section
    assert summary["dlq"]["dlq_queue_length"] == 2
    assert summary["dlq"]["total_dlq_volume"] >= 2

    # Check recovery section
    assert "total_replayed" in summary["recovery"]
    assert "resolved" in summary["recovery"]
    assert "pending" in summary["recovery"]


@pytest.mark.asyncio
async def test_dashboard_summary_tenant_isolation(fake_redis):
    """Verify get_dashboard_summary filters failure and recovery data safely by tenant_id."""
    dashboard = KafkaMonitoringDashboard(redis_client=fake_redis)

    # Store a failed event for tenant-1 and another for tenant-2
    storage = FailedEventStorage(redis_client=fake_redis)
    storage.store_failed_event({
        "event_id": "evt_t1",
        "tenant_id": "tenant-1",
        "error": "Tenant 1 failure",
        "error_classification": ErrorClassification.TERMINAL.value,
        "topic": "fieldops.events",
        "consumer": "Add_kafka_monitoring_dashboard",
    })
    storage.store_failed_event({
        "event_id": "evt_t2",
        "tenant_id": "tenant-2",
        "error": "Tenant 2 failure",
        "error_classification": ErrorClassification.TERMINAL.value,
        "topic": "fieldops.events",
        "consumer": "Add_kafka_monitoring_dashboard",
    })

    summary_t1 = await dashboard.get_dashboard_summary(tenant_id="tenant-1")
    assert summary_t1["failures"]["tenant_filter"] == "tenant-1"
    assert summary_t1["failures"]["total_stored_failures"] == 1
    assert summary_t1["failures"]["recent_failures"][0]["tenant_id"] == "tenant-1"

    summary_t2 = await dashboard.get_dashboard_summary(tenant_id="tenant-2")
    assert summary_t2["failures"]["tenant_filter"] == "tenant-2"
    assert summary_t2["failures"]["total_stored_failures"] == 1
    assert summary_t2["failures"]["recent_failures"][0]["tenant_id"] == "tenant-2"


@pytest.mark.asyncio
async def test_dashboard_summary_credential_redaction(fake_redis):
    """Verify sensitive keys (secret, token, password, api_key) are strictly redacted in dashboard summary."""
    dashboard = KafkaMonitoringDashboard(redis_client=fake_redis)

    storage = FailedEventStorage(redis_client=fake_redis)
    storage.store_failed_event({
        "event_id": "evt_secret",
        "error": "Secret failed",
        "password": "super-secret-password",
        "api_key": "raw-key-12345",
        "client_secret": "my-secret-token",
        "topic": "fieldops.events",
        "consumer": "Add_kafka_monitoring_dashboard",
        "tenant_id": "tenant-secure",
    })

    summary = await dashboard.get_dashboard_summary(tenant_id="tenant-secure")
    raw_summary_str = json.dumps(summary)

    assert "super-secret-password" not in raw_summary_str
    assert "raw-key-12345" not in raw_summary_str
    assert "my-secret-token" not in raw_summary_str
    assert "[REDACTED]" in raw_summary_str


# =============================================================================
# 4. Event Processing Tests (process_event)
# =============================================================================

@pytest.mark.asyncio
async def test_process_event_success(fake_redis):
    """Verify processing a valid event returns success receipt and updates metrics."""
    KafkaMonitoringDashboard.reset_metrics()
    dashboard = KafkaMonitoringDashboard(redis_client=fake_redis)
    event = make_test_event()

    receipt = await dashboard.process_event(event, topic="fieldops.events")

    assert receipt["status"] == "PROCESSED"
    assert receipt["consumer"] == "Add_kafka_monitoring_dashboard"
    assert receipt["event_id"] == event["event_id"]
    assert receipt["retries"] == 0
    assert receipt["idempotent"] is True
    assert receipt["dlq"] is False

    metrics = KafkaMonitoringDashboard.get_dashboard_metrics()
    assert metrics["metrics"]["processed_total"] == 1


@pytest.mark.asyncio
async def test_process_event_forbidden_keys(fake_redis):
    """Verify events containing forbidden sensitive keys are rejected to DLQ."""
    dashboard = KafkaMonitoringDashboard(redis_client=fake_redis)
    bad_event = make_test_event(payload_extra={"password": "insecure_plaintext"})

    receipt = await dashboard.process_event(bad_event, topic="fieldops.events")

    assert receipt["status"] in ("FAILED", "DLQ")
    assert receipt["dlq"] is True
    assert "forbidden" in receipt["error"].lower()


@pytest.mark.asyncio
async def test_process_event_unsupported_schema_version(fake_redis):
    """Verify events with unsupported schema versions are routed to DLQ."""
    dashboard = KafkaMonitoringDashboard(redis_client=fake_redis)
    event = make_test_event(schema_version=99)

    receipt = await dashboard.process_event(event, topic="fieldops.events")

    assert receipt["status"] in ("FAILED", "DLQ")
    assert receipt["dlq"] is True
    assert "schema" in receipt["error"].lower()


@pytest.mark.asyncio
async def test_process_event_unsupported_topic(fake_redis):
    """Verify events destined for non-whitelisted topics are rejected."""
    dashboard = KafkaMonitoringDashboard(redis_client=fake_redis)
    event = make_test_event()

    receipt = await dashboard.process_event(event, topic="unauthorized.random.topic")

    assert receipt["status"] in ("FAILED", "DLQ")
    assert receipt["dlq"] is True
    assert "topic" in receipt["error"].lower()


# =============================================================================
# 5. Recovery Contract Verification (recover_event)
# =============================================================================

@pytest.mark.asyncio
async def test_recover_event_exact_contract(fake_redis):
    """Verify recover_event satisfies the exact required output contract on recovery."""
    dashboard = KafkaMonitoringDashboard(redis_client=fake_redis)
    event = make_test_event(event_id="evt_01JEXAMPLE")

    receipt = await dashboard.recover_event(event, topic="fieldops.events", retries_limit=2)

    # Exact contract check
    assert receipt == {
        "status": "RECOVERED",
        "event_id": "evt_01JEXAMPLE",
        "retries": 1,
        "idempotent": True,
        "dlq": False,
    }
    assert receipt.is_recovered is True
    assert receipt.is_success is True


@pytest.mark.asyncio
async def test_recover_event_exhaustion(fake_redis):
    """Verify non-retryable poison event fails recovery with dlq=True."""
    dashboard = KafkaMonitoringDashboard(redis_client=fake_redis)

    poison_msg = "{invalid json string"
    receipt = await dashboard.recover_event(poison_msg, topic="fieldops.events")

    assert receipt["status"] == "FAILED"
    assert receipt["dlq"] is True


# =============================================================================
# 6. Celery Task Execution
# =============================================================================

def test_celery_task_execution(fake_redis):
    """Verify Celery tasks invoke KafkaMonitoringDashboard correctly."""
    from app.tasks import (
        _process_kafka_monitoring_dashboard_once,
        process_kafka_monitoring_dashboard_task,
        add_kafka_monitoring_dashboard_task,
    )
    event = make_test_event(event_id="evt_celery_dash")

    with patch("app.services.kafka_monitoring_dashboard.get_redis_client", return_value=fake_redis):
        result_once = _process_kafka_monitoring_dashboard_once(
            raw_message=json.dumps(event),
            topic="fieldops.events",
            redis_client=fake_redis,
        )
        assert result_once["status"] == "PROCESSED"
        assert result_once["event_id"] == "evt_celery_dash"

        # Test process_kafka_monitoring_dashboard_task
        with patch("app.tasks.get_redis_client", return_value=fake_redis):
            res1 = process_kafka_monitoring_dashboard_task(
                raw_message=json.dumps(event),
                topic="fieldops.events",
            )
            assert res1["status"] == "PROCESSED"

            # Test add_kafka_monitoring_dashboard_task alias
            res2 = add_kafka_monitoring_dashboard_task(
                raw_message=json.dumps(event),
                topic="fieldops.events",
            )
            assert res2["status"] == "PROCESSED"


# =============================================================================
# 7. FastAPI Admin Metrics Route Integration
# =============================================================================

@pytest.mark.asyncio
async def test_admin_metrics_kafka_dashboard_route(fake_redis):
    """Verify /admin/metrics/kafka/dashboard endpoint returns complete operational summary."""
    from app.routes.admin_metrics import get_kafka_dashboard, get_kafka_dashboard_metrics

    with patch("app.services.kafka_monitoring_dashboard.get_redis_client", return_value=fake_redis):
        summary = await get_kafka_dashboard(tenant_id=None)
        assert "status" in summary
        assert "broker" in summary
        assert "throughput" in summary
        assert "consumer_lag" in summary
        assert "dlq" in summary
        assert "recovery" in summary

        metrics = await get_kafka_dashboard_metrics()
        assert metrics["status"] == "healthy"
        assert metrics["consumer"] == "Add_kafka_monitoring_dashboard"
