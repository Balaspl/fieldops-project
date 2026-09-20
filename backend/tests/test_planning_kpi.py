import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from fastapi import HTTPException

from app.main import app
from app.models import Job, Technician, InAppNotification
from app.database import Base, get_db
from app.auth.dependencies import get_current_user_or_tenant
from app.auth.rbac import UserRole
from app.routes import planning as planning_route

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker


# ============================================================
# TEST DATABASE
# ============================================================

SQLALCHEMY_DATABASE_URL = "sqlite://"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


client = TestClient(app)


# ============================================================
# AUTHENTICATED TEST USER
# ============================================================

TEST_USER = SimpleNamespace(
    user_id="test-user",
    tenant_id="tenant-1",
    role="dispatcher",
    is_super_admin=False,
)


# ============================================================
# DATABASE FIXTURE
# ============================================================

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()

    db.query(Job).delete()
    db.query(Technician).delete()

    db.commit()

    # --------------------------------------------------------
    # Technicians
    # --------------------------------------------------------

    tech1 = Technician(
        technician_id=1,
        tech_id="tech-1",
        technician_name="Alice Smith",
        technician_skill="HVAC Repair",
        technician_location="North Zone",
        technician_status="AVAILABLE",
        current_jobs=1,
        max_jobs=5,
        tenant_id="tenant-1",
    )

    tech2 = Technician(
        technician_id=2,
        tech_id="tech-2",
        technician_name="Bob Jones",
        technician_skill="Plumbing Service",
        technician_location="South Zone",
        technician_status="OFFLINE",
        current_jobs=0,
        max_jobs=3,
        tenant_id="tenant-1",
    )

    tech3 = Technician(
        technician_id=3,
        tech_id="tech-3",
        technician_name="Charlie Brown",
        technician_skill="Electrical Service",
        technician_location="East Zone",
        technician_status="AVAILABLE",
        current_jobs=0,
        max_jobs=4,
        tenant_id="tenant-1",
    )

    db.add_all([tech1, tech2, tech3])
    db.commit()

    # --------------------------------------------------------
    # Jobs
    # --------------------------------------------------------

    now = datetime.now(timezone.utc)

    jobs = [
        # ----------------------------------------------------
        # Job 101 - dispatched
        # ----------------------------------------------------
        Job(
            id=101,
            customer_name="John Doe",
            status="in progress",
            priority="CRITICAL",
            service_type="HVAC Repair",
            location="North Zone",
            issue_description="AC not cooling",
            contact_number="9876543201",
            preferred_service_date=now.date(),
            assigned_technician_id=1,
            attempt_count=0,
            created_at=now,
            tenant_id="tenant-1",
        ),

        # ----------------------------------------------------
        # Job 102 - pending
        # ----------------------------------------------------
        Job(
            id=102,
            customer_name="Jane Smith",
            status="active",
            priority="HIGH",
            service_type="Electrical Service",
            location="South Zone",
            issue_description="Fuse blown",
            contact_number="9876543202",
            preferred_service_date=now.date(),
            assigned_technician_id=None,
            attempt_count=0,
            created_at=now,
            tenant_id="tenant-1",
        ),

        # ----------------------------------------------------
        # Job 103 - expired + pending
        # ----------------------------------------------------
        Job(
            id=103,
            customer_name="Bob Johnson",
            status="queued",
            priority="MEDIUM",
            service_type="Plumbing Service",
            location="East Zone",
            issue_description="Leak in pipe",
            contact_number="9876543203",
            preferred_service_date=now.date(),
            assigned_technician_id=None,
            sla_deadline=now - timedelta(hours=2),
            attempt_count=0,
            created_at=now,
            tenant_id="tenant-1",
        ),

        # ----------------------------------------------------
        # Job 104 - redispatched
        # ----------------------------------------------------
        Job(
            id=104,
            customer_name="Dave Adams",
            status="queued",
            priority="LOW",
            service_type="Network Support",
            location="West Zone",
            issue_description="WiFi offline",
            contact_number="9876543204",
            preferred_service_date=now.date(),
            assigned_technician_id=None,
            attempt_count=2,
            created_at=now,
            tenant_id="tenant-1",
        ),

        # ----------------------------------------------------
        # Job 105 - completed
        # ----------------------------------------------------
        Job(
            id=105,
            customer_name="Sara Lee",
            status="completed",
            priority="LOW",
            service_type="HVAC Repair",
            location="Central Zone",
            issue_description="Done",
            contact_number="9876543205",
            preferred_service_date=now.date(),
            assigned_technician_id=None,
            attempt_count=0,
            created_at=now,
            tenant_id="tenant-1",
        ),

        # ----------------------------------------------------
        # Job 106 - attempt_count=1
        # ----------------------------------------------------
        Job(
            id=106,
            customer_name="Tom Clark",
            status="queued",
            priority="HIGH",
            service_type="Electrical Service",
            location="North Zone",
            issue_description="Breaker tripped",
            contact_number="9876543206",
            preferred_service_date=now.date(),
            assigned_technician_id=None,
            attempt_count=1,
            created_at=now,
            tenant_id="tenant-1",
        ),

        # ----------------------------------------------------
        # Job 107 - declined job
        # ----------------------------------------------------
        Job(
            id=107,
            customer_name="Declined Customer",
            status="REJECTED_BY_TECHNICIAN",
            priority="HIGH",
            service_type="HVAC Repair",
            location="North Zone",
            issue_description="Technician declined",
            contact_number="9876543207",
            preferred_service_date=now.date(),
            assigned_technician_id=1,
            attempt_count=1,
            created_at=now,
            assigned_at=now - timedelta(hours=1),
            rejected_at=now - timedelta(minutes=30),
            rejection_reason="Technician unavailable",
            rejected_by_tech_id="tech-1",
            tenant_id="tenant-1",
        ),

       

        # ----------------------------------------------------
        # Job 109 - other tenant
        # ----------------------------------------------------
        Job(
            id=109,
            customer_name="Other Tenant Customer",
            status="queued",
            priority="LOW",
            service_type="HVAC Repair",
            location="Other Zone",
            issue_description="Other tenant job",
            contact_number="9876543209",
            preferred_service_date=now.date(),
            assigned_technician_id=1,
            attempt_count=0,
            created_at=now,
            tenant_id="tenant-2",
        ),
    ]

    db.add_all(jobs)
    db.commit()

    yield db

    db.close()


# ============================================================
# DEPENDENCY OVERRIDES
# ============================================================

@pytest.fixture(autouse=True)
def apply_overrides():
    app.dependency_overrides[get_db] = override_get_db

    # IMPORTANT:
    # planning.py uses get_current_user_or_tenant
    # for /planning/kpi and /planned-assignments.
    app.dependency_overrides[get_current_user_or_tenant] = (
        lambda: (
            TEST_USER,
            "tenant-1",
        )
    )

    yield

    app.dependency_overrides.clear()


# ============================================================
# PLANNING KPI TESTS
# ============================================================

def test_get_planning_kpi():
    response = client.get("/planning/kpi")

    assert response.status_code == 200

    data = response.json()

    # --------------------------------------------------------
    # Main KPI values
    # --------------------------------------------------------

    assert data["jobs_dispatched"] == 2

    # 102, 103, 104, 106
    assert data["jobs_pending"] == 4

    # Only 103 has expired SLA
    assert data["jobs_expired"] == 1

    # Only 104 has attempt_count > 1
    assert data["jobs_redispatched"] == 1

    # --------------------------------------------------------
    # Technician statistics
    # --------------------------------------------------------

    assert data["technicians"]["total"] == 3
    assert data["technicians"]["available"] == 2
    assert data["technicians"]["busy"] == 0
    assert data["technicians"]["offline"] == 1

    # Alice = 1/5
    # Charlie = 0/4
    # Total = 1/9 = 11.1%
    assert data["technicians"]["utilization_pct"] == 11.1

    # --------------------------------------------------------
    # Trends
    # --------------------------------------------------------

    assert "trends" in data

    assert "dispatched" in data["trends"]
    assert "pending" in data["trends"]
    assert "expired" in data["trends"]
    assert "redispatched" in data["trends"]

    for key in [
        "dispatched",
        "pending",
        "expired",
        "redispatched",
    ]:
        assert "today" in data["trends"][key]
        assert "yesterday" in data["trends"][key]
        assert "change_pct" in data["trends"][key]

    # --------------------------------------------------------
    # Sparklines
    # --------------------------------------------------------

    assert "sparklines" in data

    assert len(data["sparklines"]["dispatched"]) == 7
    assert len(data["sparklines"]["pending"]) == 7
    assert len(data["sparklines"]["expired"]) == 7
    assert len(data["sparklines"]["redispatched"]) == 7


def test_completed_job_excluded_from_pending():
    response = client.get("/planning/kpi")

    assert response.status_code == 200

    data = response.json()

    # Job 105 is completed.
    assert data["jobs_pending"] == 4


def test_redispatch_threshold_is_greater_than_one():
    response = client.get("/planning/kpi")

    assert response.status_code == 200

    data = response.json()

    # Job 104 -> attempt_count=2 -> included
    # Job 106 -> attempt_count=1 -> excluded
    assert data["jobs_redispatched"] == 1


# ============================================================
# KPI EDGE CASES
# ============================================================

def test_planning_kpi_zero_previous_day_values():
    """
    Covers safe_change_pct() when yesterday == 0.
    """

    db = TestingSessionLocal()

    db.query(Job).delete()
    db.query(Technician).delete()
    db.commit()

    tech = Technician(
        technician_id=1,
        tech_id="zero-tech",
        technician_name="Zero Tech",
        technician_skill="HVAC",
        technician_location="Zone",
        technician_status="OFFLINE",
        current_jobs=0,
        max_jobs=5,
        tenant_id="tenant-1",
    )

    db.add(tech)

    now = datetime.now(timezone.utc)

    job = Job(
        id=201,
        customer_name="Today Customer",
        status="queued",
        priority="HIGH",
        service_type="HVAC Repair",
        location="Zone",
        issue_description="Issue",
        contact_number="9876543210",
        preferred_service_date=now.date(),
        assigned_technician_id=None,
        attempt_count=0,
        created_at=now,
        tenant_id="tenant-1",
    )

    db.add(job)
    db.commit()
    db.close()

    response = client.get("/planning/kpi")

    assert response.status_code == 200

    data = response.json()

    assert data["trends"]["pending"]["yesterday"] == 0
    assert data["trends"]["pending"]["change_pct"] is None


def test_planning_kpi_zero_current_and_previous_values():
    """
    Covers safe_change_pct() when both values are zero.
    """

    db = TestingSessionLocal()

    db.query(Job).delete()
    db.query(Technician).delete()
    db.commit()

    db.close()

    response = client.get("/planning/kpi")

    assert response.status_code == 200

    data = response.json()

    assert data["jobs_dispatched"] == 0
    assert data["jobs_pending"] == 0
    assert data["jobs_expired"] == 0
    assert data["jobs_redispatched"] == 0

    assert data["trends"]["dispatched"]["change_pct"] is None
    assert data["trends"]["pending"]["change_pct"] is None
    assert data["trends"]["expired"]["change_pct"] is None
    assert data["trends"]["redispatched"]["change_pct"] is None

    assert data["sparklines"]["dispatched"] == [0] * 7
    assert data["sparklines"]["pending"] == [0] * 7
    assert data["sparklines"]["expired"] == [0] * 7
    assert data["sparklines"]["redispatched"] == [0] * 7


# ============================================================
# PLANNED ASSIGNMENTS
# ============================================================

def test_get_planned_assignments_basic():
    response = client.get("/planned-assignments")

    assert response.status_code == 200

    data = response.json()

    # Tenant 1 assigned jobs:
    # 101 -> tech 1
    # 107 -> tech 1
    assert len(data) == 2

    assert response.headers["X-Total-Count"] == "2"
    assert "Access-Control-Expose-Headers" in response.headers

    assert data[0]["job_id"] == 107
    assert data[1]["job_id"] == 101


def test_get_planned_assignments_search_by_text():
    response = client.get(
        "/planned-assignments",
        params={"search": "John"},
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["job_id"] == 101
    assert response.headers["X-Total-Count"] == "1"


def test_get_planned_assignments_search_by_id():
    response = client.get(
        "/planned-assignments",
        params={"search": "#101"},
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["job_id"] == 101


def test_get_planned_assignments_search_invalid_id():
    response = client.get(
        "/planned-assignments",
        params={"search": "Alice"},
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 2


def test_get_planned_assignments_pagination():
    response = client.get(
        "/planned-assignments",
        params={
            "page": 1,
            "limit": 1,
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["job_id"] == 107

    # Header still reports the complete count.
    assert response.headers["X-Total-Count"] == "2"


def test_get_planned_assignments_super_admin():
    """
    Covers the super-admin branch where tenant filtering
    is skipped.
    """

    app.dependency_overrides[get_current_user_or_tenant] = (
        lambda: (
            SimpleNamespace(
                user_id="super-admin",
                tenant_id="tenant-1",
                role="super_admin",
                is_super_admin=True,
            ),
            "tenant-1",
        )
    )

    response = client.get("/planned-assignments")

    assert response.status_code == 200

    data = response.json()

    # Tenant 2 job 109 is now visible.
    assert len(data) == 3

    assert any(item["job_id"] == 109 for item in data)


# ============================================================
# DECLINED JOBS
# ============================================================

def test_get_declined_jobs():
    db = TestingSessionLocal()

    now = datetime.now(timezone.utc)

    job_108 = Job(
        id=108,
        customer_name="Declined Without Tech",
        status="REJECTED_BY_TECHNICIAN",
        priority="MEDIUM",
        service_type="Plumbing Service",
        location="South Zone",
        issue_description="No technician",
        contact_number="9876543208",
        preferred_service_date=now.date(),
        assigned_technician_id=None,
        attempt_count=1,
        created_at=now,
        rejected_at=now - timedelta(minutes=20),
        rejection_reason="No technician available",
        rejected_by_tech_id=None,
        tenant_id="tenant-1",
    )

    db.add(job_108)
    db.commit()

    current_user = SimpleNamespace(
        user_id="dispatcher-1",
        tenant_id="tenant-1",
        is_super_admin=False,
        role=UserRole.DISPATCHER,
    )

    result = planning_route.get_declined_jobs(
        current_user=current_user,
        db=db,
    )

    db.close()

    assert len(result) == 2

    first = next(item for item in result if item["id"] == 107)

    assert first["customer_name"] == "Declined Customer"
    assert first["technician_name"] == "Alice Smith"
    assert first["rejection_reason"] == "Technician unavailable"
    assert first["priority"] == "HIGH"
    assert first["status"] == "REJECTED_BY_TECHNICIAN"
    assert first["location"] == "North Zone"
    assert first["service_type"] == "HVAC Repair"

    second = next(item for item in result if item["id"] == 108)

    assert second["technician_name"] is None
    assert second["rejection_reason"] == "No technician available"


def test_get_declined_jobs_super_admin():
    """
    Covers the branch where tenant filtering is skipped.
    """

    db = TestingSessionLocal()

    now = datetime.now(timezone.utc)

    job_108 = Job(
        id=108,
        customer_name="Declined Without Tech",
        status="REJECTED_BY_TECHNICIAN",
        priority="MEDIUM",
        service_type="Plumbing Service",
        location="South Zone",
        issue_description="No technician",
        contact_number="9876543208",
        preferred_service_date=now.date(),
        assigned_technician_id=None,
        attempt_count=1,
        created_at=now,
        rejected_at=now - timedelta(minutes=20),
        rejection_reason="No technician available",
        rejected_by_tech_id=None,
        tenant_id="tenant-1",
    )

    db.add(job_108)
    db.commit()

    current_user = SimpleNamespace(
        user_id="super-admin",
        tenant_id="tenant-1",
        is_super_admin=True,
        role=UserRole.SUPER_ADMIN,
    )

    result = planning_route.get_declined_jobs(
        current_user=current_user,
        db=db,
    )

    db.close()

    assert len(result) == 2


# ============================================================
# REASSIGN DECLINED JOB
# ============================================================

def test_reassign_declined_job_success(monkeypatch):
    db = TestingSessionLocal()

    current_user = SimpleNamespace(
        user_id="dispatcher-1",
        tenant_id="tenant-1",
        is_super_admin=False,
        role=UserRole.DISPATCHER,
    )

    audit_called = {}

    def fake_audit_log(
        db,
        action,
        tenant_id,
        user_id,
        role,
        entity_type,
        entity_id,
        old_value,
        new_value,
        request,
    ):
        audit_called["called"] = True
        audit_called["action"] = action
        audit_called["job_id"] = entity_id
        audit_called["new_value"] = new_value

    monkeypatch.setattr(
        planning_route,
        "audit_log",
        fake_audit_log,
    )

    request = SimpleNamespace(
        client=SimpleNamespace(
            host="test-client",
        )
    )

    result = planning_route.reassign_declined_job(
        job_id=107,
        request=request,
        new_technician_id=2,
        current_user=current_user,
        db=db,
    )

    assert result["message"] == "Job reassigned successfully"
    assert result["job_id"] == 107
    assert result["new_technician"] == "Bob Jones"
    assert result["status"] == "ASSIGNED"

    db.expire_all()

    job = db.query(Job).filter(Job.id == 107).first()
    tech = (
        db.query(Technician)
        .filter(Technician.technician_id == 2)
        .first()
    )

    assert job.assigned_technician_id == 2
    assert job.status == "ASSIGNED"
    assert job.assigned_by == "dispatcher-1"
    assert job.rejection_reason is None
    assert job.rejected_at is None
    assert job.rejected_by_tech_id is None

    assert tech.current_jobs == 1

    notification = (
        db.query(InAppNotification)
        .filter(InAppNotification.job_id == "107")
        .first()
    )

    assert notification is not None
    assert notification.tech_id == "tech-2"
    assert notification.type == "JOB_ASSIGNED"
    assert notification.status == "UNREAD"
    assert notification.priority == "HIGH"

    assert audit_called["called"] is True
    assert audit_called["job_id"] == "107"

    db.close()


# ============================================================
# REASSIGN ERROR CASES
# ============================================================

def test_reassign_declined_job_not_found():
    db = TestingSessionLocal()

    current_user = SimpleNamespace(
        user_id="dispatcher-1",
        tenant_id="tenant-1",
        is_super_admin=False,
        role=UserRole.DISPATCHER,
    )

    request = SimpleNamespace()

    with pytest.raises(HTTPException) as exc_info:
        planning_route.reassign_declined_job(
            job_id=99999,
            request=request,
            new_technician_id=2,
            current_user=current_user,
            db=db,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Job not found"

    db.close()


def test_reassign_declined_job_wrong_status():
    db = TestingSessionLocal()

    current_user = SimpleNamespace(
        user_id="dispatcher-1",
        tenant_id="tenant-1",
        is_super_admin=False,
        role=UserRole.DISPATCHER,
    )

    request = SimpleNamespace()

    with pytest.raises(HTTPException) as exc_info:
        planning_route.reassign_declined_job(
            job_id=101,
            request=request,
            new_technician_id=2,
            current_user=current_user,
            db=db,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Job is not in declined status"

    db.close()


def test_reassign_declined_job_technician_not_found():
    db = TestingSessionLocal()

    current_user = SimpleNamespace(
        user_id="dispatcher-1",
        tenant_id="tenant-1",
        is_super_admin=False,
        role=UserRole.DISPATCHER,
    )

    request = SimpleNamespace()

    with pytest.raises(HTTPException) as exc_info:
        planning_route.reassign_declined_job(
            job_id=107,
            request=request,
            new_technician_id=99999,
            current_user=current_user,
            db=db,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Technician not found"

    db.close()


# ============================================================
# REASSIGN WITH TECHNICIAN WITHOUT TECH_ID
# ============================================================

def test_reassign_declined_job_uses_technician_id_when_no_tech_id(
    monkeypatch,
):
    db = TestingSessionLocal()

    # Create another declined job.
    now = datetime.now(timezone.utc)

    job = Job(
        id=110,
        customer_name="Fallback Notification Customer",
        status="REJECTED_BY_TECHNICIAN",
        priority="HIGH",
        service_type="HVAC Repair",
        location="North Zone",
        issue_description="Fallback test",
        contact_number="9876543211",
        preferred_service_date=now.date(),
        assigned_technician_id=1,
        attempt_count=1,
        created_at=now,
        assigned_at=now - timedelta(hours=1),
        rejected_at=now - timedelta(minutes=30),
        rejection_reason="Declined",
        rejected_by_tech_id="tech-1",
        tenant_id="tenant-1",
    )

    db.add(job)
    db.commit()

    current_user = SimpleNamespace(
        user_id="dispatcher-1",
        tenant_id="tenant-1",
        is_super_admin=False,
        role=UserRole.DISPATCHER,
    )

    monkeypatch.setattr(
        planning_route,
        "audit_log",
        lambda *args, **kwargs: None,
    )

    request = SimpleNamespace()

    result = planning_route.reassign_declined_job(
        job_id=110,
        request=request,
        new_technician_id=2,
        current_user=current_user,
        db=db,
    )

    assert result["status"] == "ASSIGNED"

    db.close()


def test_planning_kpi_positive_trend_percentage():
    db = TestingSessionLocal()

    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)

    yesterday_job = Job(
        id=120,
        tenant_id="tenant-1",
        customer_name="Trend Test Customer",
        location="Test Location",
        issue_description="Trend test job",
        priority="medium",
        service_type="HVAC Repair",
        contact_number="9876543210",
        preferred_service_date=yesterday.date(),
        status="queued",
        assigned_technician_id=None,
        attempt_count=1,
        created_at=yesterday,
    )

    db.add(yesterday_job)
    db.commit()
    db.close()

    response = client.get("/planning/kpi")

    assert response.status_code == 200

    data = response.json()

    assert data["trends"]["pending"]["yesterday"] == 1
    assert data["trends"]["pending"]["today"] == 4
    assert data["trends"]["pending"]["change_pct"] == 300.0