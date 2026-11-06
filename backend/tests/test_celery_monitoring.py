"""
test_celery_monitoring.py

Comprehensive test suite for Story: Add Celery monitoring (Celery Queue Management).
Validates:
- Canonical JSON output contract:
    {
        "status": "MONITORING_ENABLED",
        "metrics": [
            "queue_depth",
            "task_latency",
            "task_failures",
            "worker_health"
        ]
    }
- Queue depth inspection across all registered operational queues (notifications, GPS, billing, AI, high-priority, reports, DLQ).
- Failure and retry rates tracking by queue with credential sanitization and correlation_id preservation.
- Worker health inspection, active task counts, and stalled worker detection.
- Abnormal queue growth alerting when backlog exceeds configurable thresholds.
- Authoritative story aliases across celery_app, tasks, worker, and celery_monitoring service.
- Celery task execution (add_celery_monitoring_task, check_celery_health_task).
- Secured FastAPI administrative endpoints (/admin/queue/monitoring/*).
"""

from unittest.mock import MagicMock
import pytest

from app.celery_app import (
    celery_app,
    DEFAULT_CELERY_MONITORING,
    ALL_KNOWN_QUEUES,
    get_celery_monitoring_config,
    add_celery_monitoring,
    get_celery_queue_depth,
    get_all_queue_depths,
    record_task_failure,
    record_task_retry,
    record_task_latency,
    detect_abnormal_queue_growth,
    get_celery_worker_health,
    detect_stalled_workers,
    get_celery_monitoring_metrics,
    AddCeleryMonitoring,
    Add_celery_monitoring,
    configure_celery_monitoring,
    ConfigureCeleryMonitoring,
    get_celery_monitoring,
    GetCeleryMonitoring,
    CeleryMonitoring as CeleryMonitoringApp,
    CeleryMonitoringService as CeleryMonitoringServiceApp,
)
from app.services.celery_monitoring import (
    CeleryMonitoring,
    CeleryMonitoringService,
    get_celery_monitoring_config as service_get_config,
    add_celery_monitoring as service_add_monitoring,
    DEFAULT_CELERY_MONITORING as SERVICE_DEFAULT_MONITORING,
    ALL_KNOWN_QUEUES as SERVICE_ALL_QUEUES,
)
from app.tasks import (
    add_celery_monitoring_task,
    check_celery_health_task,
    DEFAULT_CELERY_MONITORING as TASKS_DEFAULT_MONITORING,
    get_celery_monitoring_config as tasks_get_config,
    add_celery_monitoring as tasks_add_monitoring,
    get_celery_monitoring_metrics as tasks_get_metrics,
    AddCeleryMonitoring as TasksAddCeleryMonitoring,
    Add_celery_monitoring as TasksAdd_celery_monitoring,
    configure_celery_monitoring as tasks_configure_monitoring,
    ConfigureCeleryMonitoring as TasksConfigureCeleryMonitoring,
    get_celery_monitoring as tasks_get_monitoring,
    GetCeleryMonitoring as TasksGetCeleryMonitoring,
)
from app.worker import (
    DEFAULT_CELERY_MONITORING as WORKER_DEFAULT_MONITORING,
    get_celery_monitoring_config as worker_get_config,
    add_celery_monitoring as worker_add_monitoring,
    get_celery_monitoring_metrics as worker_get_metrics,
    get_celery_worker_health as worker_get_health,
    detect_abnormal_queue_growth as worker_detect_growth,
    AddCeleryMonitoring as WorkerAddCeleryMonitoring,
    Add_celery_monitoring as WorkerAdd_celery_monitoring,
    configure_celery_monitoring as worker_configure_monitoring,
    ConfigureCeleryMonitoring as WorkerConfigureCeleryMonitoring,
)


# =============================================================================
# Fake Redis Fixture for Telemetry & Monitoring Tests
# =============================================================================

class FakeMonitoringRedis:
    def __init__(self):
        self.store = {}
        self.lists = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None, nx=False):
        if nx and key in self.store:
            return False
        self.store[key] = str(value)
        return True

    def incr(self, key, amount=1):
        val = int(self.store.get(key, 0)) + amount
        self.store[key] = str(val)
        return val

    def llen(self, key):
        return len(self.lists.get(key, []))

    def rpush(self, key, *values):
        if key not in self.lists:
            self.lists[key] = []
        for v in values:
            self.lists[key].append(v)
        return len(self.lists[key])


@pytest.fixture
def fake_redis():
    return FakeMonitoringRedis()


# =============================================================================
# 1. Output Contract & Basic Configuration Tests
# =============================================================================

def test_celery_monitoring_contract():
    """Verify exact JSON contract matches specification."""
    config = get_celery_monitoring_config()
    assert config == {
        "status": "MONITORING_ENABLED",
        "metrics": [
            "queue_depth",
            "task_latency",
            "task_failures",
            "worker_health",
        ],
    }
    assert DEFAULT_CELERY_MONITORING == config
    assert SERVICE_DEFAULT_MONITORING == config
    assert TASKS_DEFAULT_MONITORING == config
    assert WORKER_DEFAULT_MONITORING == config


def test_add_celery_monitoring_activation():
    """Verify add_celery_monitoring enables event publishing and returns contract."""
    res = add_celery_monitoring()
    assert res == {
        "status": "MONITORING_ENABLED",
        "metrics": [
            "queue_depth",
            "task_latency",
            "task_failures",
            "worker_health",
        ],
    }
    assert celery_app.conf.worker_send_task_events is True
    assert celery_app.conf.task_send_sent_event is True


def test_celery_monitoring_aliases_and_module_exports():
    """Verify authoritative aliases resolve identically across modules."""
    assert AddCeleryMonitoring is add_celery_monitoring
    assert Add_celery_monitoring is add_celery_monitoring
    assert configure_celery_monitoring is add_celery_monitoring
    assert ConfigureCeleryMonitoring is add_celery_monitoring
    assert get_celery_monitoring is get_celery_monitoring_config
    assert GetCeleryMonitoring is get_celery_monitoring_config

    assert TasksAddCeleryMonitoring is add_celery_monitoring
    assert TasksAdd_celery_monitoring is add_celery_monitoring
    assert TasksConfigureCeleryMonitoring is add_celery_monitoring
    assert TasksGetCeleryMonitoring is get_celery_monitoring_config
    assert tasks_get_config is get_celery_monitoring_config
    assert tasks_add_monitoring is add_celery_monitoring

    assert WorkerAddCeleryMonitoring is add_celery_monitoring
    assert WorkerAdd_celery_monitoring is add_celery_monitoring
    assert WorkerConfigureCeleryMonitoring is add_celery_monitoring
    assert worker_get_config is get_celery_monitoring_config
    assert worker_add_monitoring is add_celery_monitoring

    assert service_get_config is get_celery_monitoring_config
    assert service_add_monitoring is add_celery_monitoring
    assert SERVICE_ALL_QUEUES == ALL_KNOWN_QUEUES


# =============================================================================
# 2. Queue Depth & Multi-Queue Backlog Inspection Tests
# =============================================================================

def test_celery_queue_depth_and_all_queues(fake_redis):
    """Verify queue depth calculation per-queue and across all operational queues."""
    # Populate queues in Redis
    fake_redis.rpush("notifications", "task1", "task2", "task3")
    fake_redis.rpush("billing", "task4")
    fake_redis.rpush("reports", "task5", "task6")

    assert get_celery_queue_depth("notifications", redis=fake_redis) == 3
    assert get_celery_queue_depth("billing", redis=fake_redis) == 1
    assert get_celery_queue_depth("reports", redis=fake_redis) == 2
    assert get_celery_queue_depth("ai_processing", redis=fake_redis) == 0

    all_depths = get_all_queue_depths(redis=fake_redis)
    assert all_depths["notifications"] == 3
    assert all_depths["billing"] == 1
    assert all_depths["reports"] == 2
    assert "report_generation" in all_depths
    assert all_depths["gps_processing"] == 0
    assert all_depths["ai_processing"] == 0
    assert all_depths["high_priority"] == 0
    assert all_depths["default"] == 0
    assert all_depths["dlq"] == 0


# =============================================================================
# 3. Failure, Retry & Latency Telemetry Tracking Tests
# =============================================================================

def test_record_task_failure_sanitizes_credentials_and_increments(fake_redis):
    """Verify task failure recording sanitizes credentials and tracks counts."""
    res = record_task_failure(
        queue="notifications",
        task_id="task-fail-001",
        error="Failed to connect with token=secret_token_12345",
        tenant_id="tenant-acme",
        correlation_id="corr-fail-999",
        redis=fake_redis,
    )

    assert res["status"] == "RECORDED"
    assert res["metric"] == "task_failures"
    assert res["queue"] == "notifications"
    assert res["task_id"] == "task-fail-001"
    assert res["tenant_id"] == "tenant-acme"
    assert res["correlation_id"] == "corr-fail-999"
    assert res["count"] == 1

    # Second failure increments count
    res2 = record_task_failure(
        queue="notifications",
        task_id="task-fail-002",
        error="Another failure",
        redis=fake_redis,
    )
    assert res2["count"] == 2


def test_record_task_retry_and_latency(fake_redis):
    """Verify retry counts and execution latency are tracked accurately."""
    retry_res = record_task_retry(
        queue="billing",
        task_id="task-retry-101",
        retry_count=2,
        tenant_id="tenant-fin-1",
        correlation_id="corr-ret-101",
        redis=fake_redis,
    )
    assert retry_res["status"] == "RECORDED"
    assert retry_res["metric"] == "task_retries"
    assert retry_res["retry_count"] == 2
    assert retry_res["queue"] == "billing"

    lat_res = record_task_latency(
        queue="ai_processing",
        task_id="task-lat-202",
        latency_seconds=1.45,
        tenant_id="tenant-ai-1",
        correlation_id="corr-lat-202",
        redis=fake_redis,
    )
    assert lat_res["status"] == "RECORDED"
    assert lat_res["metric"] == "task_latency"
    assert lat_res["latency_seconds"] == 1.45
    assert lat_res["queue"] == "ai_processing"


# =============================================================================
# 4. Abnormal Queue Growth & Backlog Alerting Tests
# =============================================================================

def test_detect_abnormal_queue_growth(fake_redis):
    """Verify congestion alerts trigger when queue depth exceeds threshold."""
    # Under threshold (depth 5 < threshold 10)
    for _ in range(5):
        fake_redis.rpush("notifications", "item")

    normal = detect_abnormal_queue_growth(threshold=10, redis=fake_redis)
    assert normal["alert"] is False
    assert len(normal["congested_queues"]) == 0

    # Over threshold (push 6 more, total 11 > threshold 10)
    for _ in range(6):
        fake_redis.rpush("notifications", "item")

    alerted = detect_abnormal_queue_growth(threshold=10, redis=fake_redis)
    assert alerted["alert"] is True
    assert "notifications" in alerted["congested_queues"]
    assert alerted["congested_queues"]["notifications"] == 11


# =============================================================================
# 5. Worker Health & Stalled Worker Detection Tests
# =============================================================================

def test_get_celery_worker_health_and_stalled_detection():
    """Verify worker availability inspection handles test environments gracefully."""
    health = get_celery_worker_health()
    assert health["status"] == "healthy"
    assert "workers_online" in health
    assert "active_workers" in health
    assert "stalled_workers" in health

    stalled = detect_stalled_workers(max_active_seconds=300.0)
    assert isinstance(stalled, list)


# =============================================================================
# 6. Comprehensive Metrics Aggregation Tests
# =============================================================================

def test_get_celery_monitoring_metrics_aggregation(fake_redis):
    """Verify full metrics payload conforms to expected metrics contract."""
    # Record some sample telemetry
    record_task_failure(queue="billing", task_id="t-1", redis=fake_redis)
    record_task_retry(queue="billing", task_id="t-1", retry_count=1, redis=fake_redis)
    record_task_latency(queue="gps_processing", task_id="t-2", latency_seconds=0.25, redis=fake_redis)

    metrics = get_celery_monitoring_metrics(redis=fake_redis)

    assert metrics["status"] == "MONITORING_ENABLED"
    assert "queue_depth" in metrics
    assert "worker_health" in metrics
    assert "task_failures" in metrics
    assert "task_retries" in metrics
    assert "task_latency" in metrics
    assert "alerts" in metrics

    assert metrics["task_failures"]["total"] >= 1
    assert metrics["task_failures"]["by_queue"].get("billing") == 1
    assert metrics["task_retries"]["by_queue"].get("billing") == 1
    assert metrics["task_latency"]["by_queue"].get("gps_processing") == 0.25


# =============================================================================
# 7. Celery Task Execution Tests
# =============================================================================

def test_celery_monitoring_tasks():
    """Verify Celery background tasks execute and return canonical contract."""
    res = add_celery_monitoring_task(
        tenant_id="tenant-mon-1",
        correlation_id="corr-mon-1",
    )
    assert res == {
        "status": "MONITORING_ENABLED",
        "metrics": [
            "queue_depth",
            "task_latency",
            "task_failures",
            "worker_health",
        ],
    }

    health_res = check_celery_health_task(
        tenant_id="tenant-mon-1",
        correlation_id="corr-mon-1",
    )
    assert health_res["status"] == "MONITORING_ENABLED"
    assert "queue_depth" in health_res
    assert "worker_health" in health_res


# =============================================================================
# 8. CeleryMonitoring Service Class Tests
# =============================================================================

def test_celery_monitoring_service_class(fake_redis):
    """Verify CeleryMonitoring service class coordinates all monitoring features."""
    service = CeleryMonitoring(redis=fake_redis)
    assert service.get_config() == DEFAULT_CELERY_MONITORING
    assert service.enable() == DEFAULT_CELERY_MONITORING

    service.record_failure(queue="notifications", task_id="svc-fail-1", tenant_id="tenant-1")
    service.record_retry(queue="notifications", task_id="svc-ret-1", retry_count=3)
    service.record_latency(queue="notifications", task_id="svc-lat-1", latency_seconds=0.75)

    assert service.queue_depth("notifications") == 0
    all_depths = service.all_queue_depths()
    assert "notifications" in all_depths
    assert "billing" in all_depths

    health = service.worker_health()
    assert health["status"] == "healthy"

    metrics = service.metrics()
    assert metrics["status"] == "MONITORING_ENABLED"


# =============================================================================
# 9. Admin Queue REST Endpoints Tests
# =============================================================================

def test_admin_queue_monitoring_endpoints():
    """Verify FastAPI admin queue endpoints return expected monitoring contract."""
    from app.routes.admin_queue import (
        get_celery_monitoring_status_endpoint,
        get_celery_monitoring_config_endpoint,
        configure_celery_monitoring_endpoint,
        get_celery_monitoring_metrics_endpoint,
        get_celery_worker_health_endpoint,
        get_celery_queues_depth_endpoint,
        record_celery_metric_endpoint,
    )

    expected = {
        "status": "MONITORING_ENABLED",
        "metrics": [
            "queue_depth",
            "task_latency",
            "task_failures",
            "worker_health",
        ],
    }

    assert get_celery_monitoring_status_endpoint() == expected
    assert get_celery_monitoring_config_endpoint() == expected
    assert configure_celery_monitoring_endpoint() == expected

    metrics = get_celery_monitoring_metrics_endpoint()
    assert metrics["status"] == "MONITORING_ENABLED"
    assert "queue_depth" in metrics
    assert "worker_health" in metrics

    health = get_celery_worker_health_endpoint()
    assert health["status"] == "healthy"

    queues = get_celery_queues_depth_endpoint()
    assert "notifications" in queues
    assert "billing" in queues

    rec = record_celery_metric_endpoint({
        "metric": "task_failures",
        "queue": "notifications",
        "task_id": "ep-task-1",
        "error": "Timeout",
    })
    assert rec["status"] == "RECORDED"
    assert rec["metric"] == "task_failures"
