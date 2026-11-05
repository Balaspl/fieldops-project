"""
test_report_generation_queue.py

Comprehensive test suite for Story: Create report-generation queue (Celery Queue Management).
Validates dedicated Celery queue and routing configuration for long-running report/PDF generation workloads:
- Route PDF and report generation workloads to 'report_generation' queue.
- Prevent CPU-intensive PDF compilation from competing with interactive dispatch, GPS telemetry, and notifications.
- Contract validation:
    {
        "status": "CONFIGURED",
        "queue": "report_generation",
        "routing_key": "reports"
    }
- Preservation of tenant_id, correlation_id, and entity metadata.
- Bounded execution limits and idempotency to prevent duplicate PDF rendering.
"""

from unittest.mock import MagicMock, patch
from celery import Celery
from kombu import Queue
import pytest

from app.celery_app import (
    celery_app,
    REPORT_QUEUE,
    REPORT_ROUTING_KEY,
    REPORT_GENERATION_QUEUE,
    REPORT_GENERATION_ROUTING_KEY,
    DEFAULT_QUEUE,
    NOTIFICATION_QUEUE,
    GPS_QUEUE,
    BILLING_QUEUE,
    AI_QUEUE,
    HIGH_PRIORITY_QUEUE,
    REPORT_TASK_ROUTES,
    get_report_generation_queue_config,
    create_report_generation_queue,
    CreateReportGenerationQueue,
    Create_report_generation_queue,
    CreateReportQueue,
    create_report_queue,
    Create_report_queue,
)
from app.services.report_service import (
    REPORT_QUEUE as SERVICE_REPORT_QUEUE,
    REPORT_ROUTING_KEY as SERVICE_REPORT_ROUTING_KEY,
    REPORT_GENERATION_QUEUE as SERVICE_REPORT_GENERATION_QUEUE,
    REPORT_GENERATION_ROUTING_KEY as SERVICE_REPORT_GENERATION_ROUTING_KEY,
    get_report_generation_queue_config as service_get_config,
    create_report_generation_queue as service_create_queue,
    CreateReportGenerationQueue as ServiceCreateReportGenerationQueue,
    Create_report_generation_queue as ServiceCreate_report_generation_queue,
    CreateReportQueue as ServiceCreateReportQueue,
    create_report_queue as service_create_report_queue,
    Create_report_queue as ServiceCreate_report_queue,
    render_summary_report_pdf,
)
from app.tasks import (
    create_report_generation_queue_task,
    generate_report_task,
    generate_pdf_report_task,
    generate_job_invoice_pdf_task,
    process_report_generation_task,
    _generate_report_once,
)


# =============================================================================
# Fake Redis Fixture for Idempotency Tests
# =============================================================================

class FakeRedis:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None, nx=False):
        if nx and key in self.store:
            return False
        self.store[key] = str(value)
        return True

    def delete(self, *keys):
        count = 0
        for k in keys:
            if k in self.store:
                del self.store[k]
                count += 1
        return count


@pytest.fixture
def fake_redis():
    return FakeRedis()


# =============================================================================
# 1. Output Contract & Basic Configuration Tests
# =============================================================================

def test_report_generation_queue_expected_contract():
    """Verify create_report_generation_queue returns the exact expected output contract."""
    result = create_report_generation_queue()

    assert result == {
        "status": "CONFIGURED",
        "queue": "report_generation",
        "routing_key": "reports",
    }
    assert result["status"] == "CONFIGURED"
    assert result["queue"] == "report_generation"
    assert result["routing_key"] == "reports"


def test_get_report_generation_queue_config():
    """Verify get_report_generation_queue_config returns the canonical contract."""
    config = get_report_generation_queue_config()
    assert config == {
        "status": "CONFIGURED",
        "queue": "report_generation",
        "routing_key": "reports",
    }


def test_report_queue_aliases_and_imports():
    """Verify story naming aliases and service re-exports point to the same callable."""
    assert CreateReportGenerationQueue is create_report_generation_queue
    assert Create_report_generation_queue is create_report_generation_queue
    assert CreateReportQueue is create_report_generation_queue
    assert create_report_queue is create_report_generation_queue
    assert Create_report_queue is create_report_generation_queue

    # Synonymous queue and routing keys
    assert REPORT_QUEUE == "report_generation"
    assert REPORT_ROUTING_KEY == "reports"
    assert REPORT_GENERATION_QUEUE == "report_generation"
    assert REPORT_GENERATION_ROUTING_KEY == "reports"

    # Re-exports from app.services.report_service
    assert SERVICE_REPORT_QUEUE == "report_generation"
    assert SERVICE_REPORT_ROUTING_KEY == "reports"
    assert SERVICE_REPORT_GENERATION_QUEUE == "report_generation"
    assert SERVICE_REPORT_GENERATION_ROUTING_KEY == "reports"
    assert service_get_config() == {"status": "CONFIGURED", "queue": "report_generation", "routing_key": "reports"}
    assert service_create_queue is create_report_generation_queue
    assert ServiceCreateReportGenerationQueue is create_report_generation_queue
    assert ServiceCreate_report_generation_queue is create_report_generation_queue
    assert ServiceCreateReportQueue is create_report_generation_queue
    assert service_create_report_queue is create_report_generation_queue
    assert ServiceCreate_report_queue is create_report_generation_queue


# =============================================================================
# 2. Celery App Registration Tests
# =============================================================================

def test_celery_task_queues_registered_report_generation():
    """Verify the report_generation queue is configured in Celery task_queues."""
    queue_names = {
        q.name if hasattr(q, "name") else str(q)
        for q in celery_app.conf.task_queues
    }
    assert "report_generation" in queue_names
    assert "high_priority" in queue_names
    assert "ai_processing" in queue_names
    assert "billing" in queue_names
    assert "gps_processing" in queue_names
    assert "notifications" in queue_names
    assert "default" in queue_names


def test_celery_task_routes_report_mapping():
    """Verify all report and PDF generation tasks are routed to the report_generation queue."""
    routes = celery_app.conf.task_routes

    assert routes["app.tasks.generate_report_task"] == {
        "queue": "report_generation",
        "routing_key": "reports",
    }
    assert routes["app.tasks.generate_pdf_report_task"] == {
        "queue": "report_generation",
        "routing_key": "reports",
    }
    assert routes["app.tasks.generate_job_invoice_pdf_task"] == {
        "queue": "report_generation",
        "routing_key": "reports",
    }
    assert routes["app.tasks.process_report_generation_task"] == {
        "queue": "report_generation",
        "routing_key": "reports",
    }
    assert routes["app.tasks.create_report_generation_queue_task"] == {
        "queue": "report_generation",
        "routing_key": "reports",
    }


# =============================================================================
# 3. Workload Isolation Tests
# =============================================================================

def test_report_generation_and_other_queues_isolation():
    """Verify report_generation tasks are not mapped to ordinary, GPS, or priority queues."""
    report_routes = REPORT_TASK_ROUTES

    for task_name, route_info in report_routes.items():
        assert route_info["queue"] == "report_generation", f"{task_name} should route to report_generation"
        assert route_info["routing_key"] == "reports", f"{task_name} should use routing_key 'reports'"
        assert route_info["queue"] != DEFAULT_QUEUE
        assert route_info["queue"] != NOTIFICATION_QUEUE
        assert route_info["queue"] != GPS_QUEUE
        assert route_info["queue"] != BILLING_QUEUE
        assert route_info["queue"] != AI_QUEUE
        assert route_info["queue"] != HIGH_PRIORITY_QUEUE


# =============================================================================
# 4. Task Metadata & Observability Tests
# =============================================================================

def test_report_task_signatures_preserve_metadata():
    """Verify report task payloads accept and propagate tenant_id and correlation_id."""
    res = create_report_generation_queue_task(
        tenant_id="tenant-report-1",
        correlation_id="corr-rpt-1234",
    )
    assert res["status"] == "CONFIGURED"
    assert res["queue"] == "report_generation"
    assert res["routing_key"] == "reports"

    proc_res = process_report_generation_task(
        report_type="MONTHLY_SUMMARY",
        payload={"period": "2026-10"},
        tenant_id="tenant-report-2",
        correlation_id="corr-rpt-5678",
    )
    assert proc_res["status"] == "COMPLETED"
    assert proc_res["queue"] == "report_generation"
    assert proc_res["routing_key"] == "reports"
    assert proc_res["tenant_id"] == "tenant-report-2"
    assert proc_res["correlation_id"] == "corr-rpt-5678"


# =============================================================================
# 5. PDF / Report Generation & Idempotency Tests
# =============================================================================

def test_report_generation_success_path(fake_redis):
    """Verify successful generation of PDF report with valid parameters."""
    res = _generate_report_once(
        redis=fake_redis,
        report_type="service_summary",
        tenant_id="tenant-tech-1",
        report_id="rpt_001",
        job_id=404,
        correlation_id="corr-rpt-success",
        parameters={"records": [{"job_id": 404, "status": "COMPLETED", "technician": "Rajesh"}]},
    )
    assert res["status"] == "GENERATED"
    assert res["queue"] == "report_generation"
    assert res["routing_key"] == "reports"
    assert res["report_id"] == "rpt_001"
    assert res["report_type"] == "service_summary"
    assert res["tenant_id"] == "tenant-tech-1"
    assert res["job_id"] == 404
    assert res["correlation_id"] == "corr-rpt-success"
    assert res["content_type"] == "application/pdf"
    assert res["file_size"] > 0


def test_report_generation_idempotency_prevents_duplicate_renders(fake_redis):
    """Verify duplicate report generation calls return cached result without re-rendering."""
    report_id = "rpt_unique_invoice_99"
    tenant_id = "tenant-idem-report"

    # First execution renders PDF and stores marker
    res1 = _generate_report_once(
        redis=fake_redis,
        report_type="invoice_pdf",
        tenant_id=tenant_id,
        report_id=report_id,
        job_id=505,
    )
    assert res1["status"] == "GENERATED"
    assert res1.get("idempotent_duplicate") is not True

    # Second execution returns cached marker
    res2 = _generate_report_once(
        redis=fake_redis,
        report_type="invoice_pdf",
        tenant_id=tenant_id,
        report_id=report_id,
        job_id=505,
    )
    assert res2["status"] == "GENERATED"
    assert res2.get("idempotent_duplicate") is True
    assert res2["queue"] == "report_generation"
    assert res2["routing_key"] == "reports"


def test_report_generation_missing_tenant_returns_permanent_failure(fake_redis):
    """Verify missing tenant_id fails boundedly without retrying indefinitely."""
    res = _generate_report_once(
        redis=fake_redis,
        report_type="monthly_kpi",
        tenant_id="",  # Missing tenant
        correlation_id="corr-fail-tenant",
    )
    assert res["status"] == "FAILED"
    assert res["permanent_failure"] is True
    assert "tenant_id is required" in res["error"]
    assert res["queue"] == "report_generation"


def test_report_generation_missing_report_type_returns_permanent_failure(fake_redis):
    """Verify missing report_type fails boundedly without retrying indefinitely."""
    res = _generate_report_once(
        redis=fake_redis,
        report_type="",  # Missing report_type
        tenant_id="tenant-valid",
        correlation_id="corr-fail-type",
    )
    assert res["status"] == "FAILED"
    assert res["permanent_failure"] is True
    assert "report_type is required" in res["error"]
    assert res["queue"] == "report_generation"


def test_render_summary_report_pdf_creates_valid_pdf():
    """Verify direct ReportLab PDF helper generates valid PDF binary."""
    pdf_bytes = render_summary_report_pdf(
        title="EXECUTIVE SUMMARY",
        records=[{"metric": "completion_rate", "value": "98.5%"}],
        tenant_id="tenant-kpi",
    )
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 500


# =============================================================================
# 6. Idempotence & Custom Celery App Configuration
# =============================================================================

def test_create_report_generation_queue_idempotence():
    """Verify calling create_report_generation_queue multiple times is safe and idempotent."""
    res1 = create_report_generation_queue()
    res2 = create_report_generation_queue()

    assert res1 == res2
    assert res1["status"] == "CONFIGURED"

    # Queue should appear exactly once in task_queues
    rpt_queues = [
        q for q in celery_app.conf.task_queues
        if (q.name if hasattr(q, "name") else str(q)) == "report_generation"
    ]
    assert len(rpt_queues) == 1


def test_create_report_generation_queue_custom_celery_instance():
    """Verify create_report_generation_queue configures any custom Celery instance correctly."""
    custom_app = Celery("test_custom_report")
    custom_app.conf.task_queues = [Queue("default", routing_key="default")]
    custom_app.conf.task_routes = {}

    result = create_report_generation_queue(custom_app)

    assert result == {
        "status": "CONFIGURED",
        "queue": "report_generation",
        "routing_key": "reports",
    }
    custom_queue_names = {
        q.name if hasattr(q, "name") else str(q)
        for q in custom_app.conf.task_queues
    }
    assert "report_generation" in custom_queue_names
    assert "app.tasks.generate_report_task" in custom_app.conf.task_routes
    assert "app.tasks.generate_pdf_report_task" in custom_app.conf.task_routes


# =============================================================================
# 7. Admin Queue REST Endpoints Tests
# =============================================================================

def test_admin_queue_report_endpoints():
    """Verify FastAPI admin queue endpoints return expected report-generation queue contract."""
    from app.routes.admin_queue import (
        get_report_queue_status,
        configure_report_queue_endpoint,
        get_report_generation_status_alias,
        configure_report_generation_endpoint_alias,
    )

    status_res = get_report_queue_status()
    assert status_res == {
        "status": "CONFIGURED",
        "queue": "report_generation",
        "routing_key": "reports",
    }

    config_res = configure_report_queue_endpoint()
    assert config_res == {
        "status": "CONFIGURED",
        "queue": "report_generation",
        "routing_key": "reports",
    }

    # Verify aliases
    assert get_report_generation_status_alias() == status_res
    assert configure_report_generation_endpoint_alias() == config_res

