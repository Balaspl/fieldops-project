import pytest
from fastapi.testclient import TestClient
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.models import (
    Base,
    Job,
    Technician,
    InAppNotification,
)
from app.database import get_db
from app.auth.dependencies import (
    get_current_user,
    get_current_user_or_tenant,
)
from app.auth.dependencies import AuthenticatedUser
from app.routes import planning as planning_route
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

from app.models import Job, Technician
from app.auth.rbac import UserRole
from app.auth.dependencies import get_current_user_or_tenant
from app.routes import planning as planning_route

# ---------------------------------------------------------------------------
# Test database
# ---------------------------------------------------------------------------

SQLALCHEMY_DATABASE_URL = "sqlite://"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={
        "check_same_thread": False,
    },
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# ============================================================
# Database Fixture
# ============================================================

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(
        bind=engine
    )

    Base.metadata.create_all(
        bind=engine
    )

    db = TestingSessionLocal()

    yield db

    db.close()


# ============================================================
# FastAPI Dependency Overrides
# ============================================================

@pytest.fixture(autouse=True)
def apply_overrides():
    app.dependency_overrides[get_db] = override_get_db

    test_user = AuthenticatedUser(
        user_id="dispatcher-1",
        tenant_id="tenant-1",
        role=UserRole.DISPATCHER,
        jti="test-jti",
        session_id="test-session",
    )

    app.dependency_overrides[get_current_user_or_tenant] = (
        lambda: (
            test_user,
            "tenant-1",
        )
    )

    app.dependency_overrides[get_current_user] = (
        lambda: test_user
    )

    yield

    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def mock_audit_log(monkeypatch):
    """
    The route calls audit_log(db, ...).
    Replace it with a no-op so these tests focus on the
    reassign route itself.
    """

    def fake_audit_log(*args, **kwargs):
        return None

    monkeypatch.setattr(
        planning_route,
        "audit_log",
        fake_audit_log,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def create_technician(
    db,
    tech_id,
    name,
    tenant_id="tenant-1",
):
    technician = Technician(
        tech_id=tech_id,
        technician_name=name,
        technician_skill="Plumbing",
        technician_location="0,0",
        technician_status="AVAILABLE",
        current_jobs=0,
        max_jobs=5,
        tenant_id=tenant_id,
    )

    db.add(technician)
    db.commit()
    db.refresh(technician)

    return technician


def create_declined_job(
    db,
    technician_id=None,
    tenant_id="tenant-1",
):
    job = Job(
        customer_name="Alice",
        location="1,1",
        issue_description="Leaking pipe",
        priority="HIGH",
        service_type="Plumbing",
        required_skill="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now().date(),
        status="REJECTED_BY_TECHNICIAN",
        assigned_technician_id=technician_id,
        tenant_id=tenant_id,
        rejection_reason="Technician rejected the job",
        rejected_at=datetime.now(),
        rejected_by_tech_id="old-tech",
    )

    db.add(job)

    db.commit()

    db.refresh(job)

    return job


# ---------------------------------------------------------------------------
# 1. Successful reassignment with tech_id
# ---------------------------------------------------------------------------

def test_reassign_declined_job_success(setup_db):
    db = setup_db

    new_tech = create_technician(
        db,
        tech_id="tech-2",
        name="New Technician",
    )

    job = create_declined_job(db)

    response = client.post(
        f"/planning/declined-jobs/{job.id}/reassign",
        params={
            "new_technician_id": new_tech.technician_id,
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["message"] == "Job reassigned successfully"
    assert data["job_id"] == job.id
    assert data["new_technician"] == "New Technician"
    assert data["status"] == "ASSIGNED"

    db.refresh(job)
    db.refresh(new_tech)

    assert job.status == "ASSIGNED"
    assert job.assigned_technician_id == new_tech.technician_id
    assert job.rejection_reason is None
    assert job.rejected_at is None
    assert job.rejected_by_tech_id is None
    assert job.assigned_by == "dispatcher-1"
    assert job.assigned_at is not None

    assert new_tech.current_jobs == 1

    notification = (
        db.query(InAppNotification)
        .filter(InAppNotification.job_id == str(job.id))
        .first()
    )

    assert notification is not None
    assert notification.tech_id == "tech-2"
    assert notification.type == "JOB_ASSIGNED"
    assert notification.title == "New Job Assigned"
    assert notification.status == "UNREAD"
    assert notification.priority == "HIGH"


# ---------------------------------------------------------------------------
# 2. Successful reassignment when tech_id is None
# ---------------------------------------------------------------------------

def test_reassign_declined_job_uses_technician_id_when_no_tech_id(setup_db):
    db = setup_db

    new_tech = Technician(
        tech_id=None,
        technician_name="Fallback Technician",
        technician_skill="Plumbing",
        technician_location="0,0",
        technician_status="AVAILABLE",
        current_jobs=0,
        max_jobs=5,
        tenant_id="tenant-1",
    )

    db.add(new_tech)
    db.commit()
    db.refresh(new_tech)

    job = create_declined_job(db)

    response = client.post(
        f"/planning/declined-jobs/{job.id}/reassign",
        params={
            "new_technician_id": new_tech.technician_id,
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["message"] == "Job reassigned successfully"
    assert data["job_id"] == job.id
    assert data["new_technician"] == "Fallback Technician"
    assert data["status"] == "ASSIGNED"

    db.refresh(job)
    db.refresh(new_tech)

    assert job.status == "ASSIGNED"
    assert job.assigned_technician_id == new_tech.technician_id
    assert new_tech.current_jobs == 1

    notification = (
        db.query(InAppNotification)
        .filter(InAppNotification.job_id == str(job.id))
        .first()
    )

    assert notification is not None

    # Covers:
    # new_tech.tech_id or str(new_tech.technician_id)
    assert notification.tech_id == str(new_tech.technician_id)


# ---------------------------------------------------------------------------
# 3. Job does not exist
# ---------------------------------------------------------------------------

def test_reassign_declined_job_not_found(setup_db):
    response = client.post(
        "/planning/declined-jobs/99999/reassign",
        params={
            "new_technician_id": 1,
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found"


# ---------------------------------------------------------------------------
# 4. Job exists but is not declined
# ---------------------------------------------------------------------------

def test_reassign_declined_job_wrong_status(setup_db):
    db = setup_db

    new_tech = create_technician(
        db,
        tech_id="tech-2",
        name="New Technician",
    )

    job = Job(
        customer_name="Bob",
        location="2,2",
        issue_description="Electrical issue",
        priority="MEDIUM",
        service_type="Electrical",
        required_skill="Electrical",
        contact_number="9876543210",
        preferred_service_date=datetime.now().date(),
        status="ASSIGNED",
        tenant_id="tenant-1",
    )

    db.add(job)

    db.commit()

    db.refresh(job)

    response = client.post(
        f"/planning/declined-jobs/{job.id}/reassign",
        params={
            "new_technician_id": new_tech.technician_id,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Job is not in declined status"


# ---------------------------------------------------------------------------
# 5. New technician does not exist
# ---------------------------------------------------------------------------

def test_reassign_declined_job_technician_not_found(setup_db):
    db = setup_db

    job = create_declined_job(db)

    response = client.post(
        f"/planning/declined-jobs/{job.id}/reassign",
        params={
            "new_technician_id": 99999,
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Technician not found"


# ---------------------------------------------------------------------------
# 6. Missing required query parameter
# ---------------------------------------------------------------------------

def test_reassign_declined_job_missing_technician_id(setup_db):
    db = setup_db

    job = create_declined_job(db)

    response = client.post(
        f"/planning/declined-jobs/{job.id}/reassign",
    )

    assert response.status_code == 400

# ============================================================
# FULL PLANNING ROUTE COVERAGE
# ============================================================




# ============================================================
# PLANNED ASSIGNMENTS
# ============================================================

def test_planned_assignments_basic(setup_db):
    db = setup_db

    # Make sure there is an assigned job.
    tech = Technician(
        technician_id=101,
        tech_id="coverage-tech-101",
        technician_name="Coverage Technician",
        technician_skill="HVAC Repair",
        technician_location="North Zone",
        technician_status="AVAILABLE",
        current_jobs=1,
        max_jobs=5,
        tenant_id="tenant-1",
    )

    job = Job(
        customer_name="Coverage Customer",
        location="North Zone",
        issue_description="Coverage issue",
        priority="HIGH",
        service_type="HVAC Repair",
        contact_number="9876543210",
        preferred_service_date=datetime.now().date(),
        status="ASSIGNED",
        assigned_technician_id=101,
        tenant_id="tenant-1",
    )

    db.add(tech)
    db.add(job)
    db.commit()

    response = client.get("/planned-assignments")

    assert response.status_code == 200
    assert response.headers["X-Total-Count"] == "1"
    assert response.headers["Access-Control-Expose-Headers"] == "X-Total-Count"

    data = response.json()

    assert len(data) == 1
    assert data[0]["job_id"] == job.id
    assert data[0]["technician"] == "Coverage Technician"
    assert data[0]["skill"] == "HVAC Repair"
    assert data[0]["customer"] == "Coverage Customer"


def test_planned_assignments_numeric_search(setup_db):
    db = setup_db

    tech = Technician(
        technician_id=102,
        tech_id="coverage-tech-102",
        technician_name="Numeric Search Tech",
        technician_skill="HVAC Repair",
        technician_location="North Zone",
        technician_status="AVAILABLE",
        current_jobs=0,
        max_jobs=5,
        tenant_id="tenant-1",
    )

    job = Job(
        customer_name="Numeric Customer",
        location="North Zone",
        issue_description="Numeric search issue",
        priority="HIGH",
        service_type="HVAC Repair",
        contact_number="9876543211",
        preferred_service_date=datetime.now().date(),
        status="ASSIGNED",
        assigned_technician_id=102,
        tenant_id="tenant-1",
    )

    db.add(tech)
    db.add(job)
    db.commit()

    response = client.get(
        "/planned-assignments",
        params={"search": f"#{job.id}"},
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["job_id"] == job.id


def test_planned_assignments_text_search(setup_db):
    db = setup_db

    tech = Technician(
        technician_id=103,
        tech_id="coverage-tech-103",
        technician_name="Unique Search Technician",
        technician_skill="HVAC Repair",
        technician_location="North Zone",
        technician_status="AVAILABLE",
        current_jobs=0,
        max_jobs=5,
        tenant_id="tenant-1",
    )

    job = Job(
        customer_name="Unique Search Customer",
        location="North Zone",
        issue_description="Unique Search Issue",
        priority="HIGH",
        service_type="HVAC Repair",
        contact_number="9876543212",
        preferred_service_date=datetime.now().date(),
        status="ASSIGNED",
        assigned_technician_id=103,
        tenant_id="tenant-1",
    )

    db.add(tech)
    db.add(job)
    db.commit()

    response = client.get(
        "/planned-assignments",
        params={"search": "Unique Search"},
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["job_id"] == job.id


def test_planned_assignments_pagination(setup_db):
    db = setup_db

    tech = Technician(
        technician_id=104,
        tech_id="coverage-tech-104",
        technician_name="Pagination Technician",
        technician_skill="HVAC Repair",
        technician_location="North Zone",
        technician_status="AVAILABLE",
        current_jobs=0,
        max_jobs=5,
        tenant_id="tenant-1",
    )

    jobs = []

    for index in range(3):
        jobs.append(
            Job(
                customer_name=f"Pagination Customer {index}",
                location="North Zone",
                issue_description="Pagination issue",
                priority="HIGH",
                service_type="HVAC Repair",
                contact_number=f"98765432{20 + index}",
                preferred_service_date=datetime.now().date(),
                status="ASSIGNED",
                assigned_technician_id=104,
                tenant_id="tenant-1",
            )
        )

    db.add(tech)
    db.add_all(jobs)
    db.commit()

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
    assert response.headers["X-Total-Count"] == "3"


def test_planned_assignments_super_admin(setup_db):
    db = setup_db

    tech = Technician(
        technician_id=105,
        tech_id="coverage-tech-105",
        technician_name="Other Tenant Technician",
        technician_skill="HVAC Repair",
        technician_location="Other Zone",
        technician_status="AVAILABLE",
        current_jobs=0,
        max_jobs=5,
        tenant_id="tenant-2",
    )

    job = Job(
        customer_name="Other Tenant Customer",
        location="Other Zone",
        issue_description="Other tenant issue",
        priority="HIGH",
        service_type="HVAC Repair",
        contact_number="9876543215",
        preferred_service_date=datetime.now().date(),
        status="ASSIGNED",
        assigned_technician_id=105,
        tenant_id="tenant-2",
    )

    db.add(tech)
    db.add(job)
    db.commit()

    app.dependency_overrides[get_current_user_or_tenant] = (
        lambda: (
            SimpleNamespace(
                user_id="super-admin",
                tenant_id="tenant-1",
                role=UserRole.SUPER_ADMIN,
                is_super_admin=True,
            ),
            "tenant-1",
        )
    )

    response = client.get("/planned-assignments")

    assert response.status_code == 200

    data = response.json()

    assert any(item["job_id"] == job.id for item in data)


# ============================================================
# PLANNING KPI
# ============================================================

def test_planning_kpi_full_metrics(setup_db):
    db = setup_db

    now = datetime.now(timezone.utc)

    tech = Technician(
        technician_id=201,
        tech_id="kpi-tech-201",
        technician_name="KPI Technician",
        technician_skill="HVAC Repair",
        technician_location="North Zone",
        technician_status="AVAILABLE",
        current_jobs=1,
        max_jobs=5,
        tenant_id="tenant-1",
    )

    dispatched = Job(
        customer_name="KPI Dispatched",
        location="North Zone",
        issue_description="Dispatched job",
        priority="HIGH",
        service_type="HVAC Repair",
        contact_number="9876543220",
        preferred_service_date=now.date(),
        status="ASSIGNED",
        assigned_technician_id=201,
        attempt_count=0,
        created_at=now,
        tenant_id="tenant-1",
    )

    pending = Job(
        customer_name="KPI Pending",
        location="North Zone",
        issue_description="Pending job",
        priority="MEDIUM",
        service_type="HVAC Repair",
        contact_number="9876543221",
        preferred_service_date=now.date(),
        status="QUEUED",
        assigned_technician_id=None,
        attempt_count=0,
        created_at=now,
        tenant_id="tenant-1",
    )

    expired = Job(
        customer_name="KPI Expired",
        location="North Zone",
        issue_description="Expired job",
        priority="HIGH",
        service_type="HVAC Repair",
        contact_number="9876543222",
        preferred_service_date=now.date(),
        status="QUEUED",
        assigned_technician_id=None,
        attempt_count=0,
        sla_deadline=now - timedelta(hours=2),
        created_at=now,
        tenant_id="tenant-1",
    )

    redispatched = Job(
        customer_name="KPI Redispatched",
        location="North Zone",
        issue_description="Redispatched job",
        priority="HIGH",
        service_type="HVAC Repair",
        contact_number="9876543223",
        preferred_service_date=now.date(),
        status="QUEUED",
        assigned_technician_id=None,
        attempt_count=2,
        created_at=now,
        tenant_id="tenant-1",
    )

    completed = Job(
        customer_name="KPI Completed",
        location="North Zone",
        issue_description="Completed job",
        priority="LOW",
        service_type="HVAC Repair",
        contact_number="9876543224",
        preferred_service_date=now.date(),
        status="COMPLETED",
        assigned_technician_id=None,
        attempt_count=0,
        created_at=now,
        tenant_id="tenant-1",
    )

    db.add(tech)
    db.add_all(
        [
            dispatched,
            pending,
            expired,
            redispatched,
            completed,
        ]
    )
    db.commit()

    response = client.get("/planning/kpi")

    assert response.status_code == 200

    data = response.json()

    assert "jobs_dispatched" in data
    assert "jobs_pending" in data
    assert "jobs_expired" in data
    assert "jobs_redispatched" in data

    assert "trends" in data
    assert "sparklines" in data
    assert "technicians" in data

    for key in [
        "dispatched",
        "pending",
        "expired",
        "redispatched",
    ]:
        assert len(data["sparklines"][key]) == 7
        assert "today" in data["trends"][key]
        assert "yesterday" in data["trends"][key]
        assert "change_pct" in data["trends"][key]

    assert data["technicians"]["total"] >= 1
    assert data["technicians"]["available"] >= 1
    assert data["technicians"]["utilization_pct"] >= 0


def test_planning_kpi_zero_values(setup_db):
    db = setup_db

    db.query(Job).delete()
    db.query(Technician).delete()
    db.commit()

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


def test_planning_kpi_positive_yesterday_trends(setup_db):
    db = setup_db

    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)

    job = Job(
        customer_name="Trend Customer",
        location="Trend Location",
        issue_description="Trend issue",
        priority="MEDIUM",
        service_type="HVAC Repair",
        contact_number="9876543230",
        preferred_service_date=yesterday.date(),
        status="QUEUED",
        assigned_technician_id=None,
        attempt_count=0,
        created_at=yesterday,
        tenant_id="tenant-1",
    )

    db.add(job)
    db.commit()

    response = client.get("/planning/kpi")

    assert response.status_code == 200

    data = response.json()

    assert data["trends"]["pending"]["yesterday"] >= 1


# ============================================================
# DECLINED JOBS
# ============================================================

def test_get_declined_jobs_with_and_without_technician(setup_db):
    db = setup_db

    now = datetime.now(timezone.utc)

    tech = Technician(
        technician_id=301,
        tech_id="declined-tech",
        technician_name="Declined Technician",
        technician_skill="HVAC Repair",
        technician_location="North Zone",
        technician_status="AVAILABLE",
        current_jobs=0,
        max_jobs=5,
        tenant_id="tenant-1",
    )

    with_tech = Job(
        customer_name="Declined With Tech",
        location="North Zone",
        issue_description="Declined with technician",
        priority="HIGH",
        service_type="HVAC Repair",
        contact_number="9876543240",
        preferred_service_date=now.date(),
        status="REJECTED_BY_TECHNICIAN",
        assigned_technician_id=None,
        rejected_by_tech_id="declined-tech",
        rejection_reason="Technician unavailable",
        rejected_at=now,
        assigned_at=now - timedelta(hours=1),
        sla_deadline=now + timedelta(hours=1),
        tenant_id="tenant-1",
    )

    without_tech = Job(
        customer_name="Declined Without Tech",
        location="South Zone",
        issue_description="Declined without technician",
        priority="MEDIUM",
        service_type="Plumbing Service",
        contact_number="9876543241",
        preferred_service_date=now.date(),
        status="REJECTED_BY_TECHNICIAN",
        assigned_technician_id=None,
        rejected_by_tech_id=None,
        rejection_reason="No technician",
        rejected_at=now,
        tenant_id="tenant-1",
    )

    db.add(tech)
    db.add_all([with_tech, without_tech])
    db.commit()

    current_user = SimpleNamespace(
        user_id="dispatcher-coverage",
        tenant_id="tenant-1",
        role=UserRole.DISPATCHER,
        is_super_admin=False,
    )

    result = planning_route.get_declined_jobs(
        current_user=current_user,
        db=db,
    )

    assert len(result) == 2

    with_tech_result = next(
        item for item in result
        if item["id"] == with_tech.id
    )

    without_tech_result = next(
        item for item in result
        if item["id"] == without_tech.id
    )

    assert (
        with_tech_result["technician_name"]
        == "Declined Technician"
    )

    assert (
        without_tech_result["technician_name"]
        is None
    )

    assert with_tech_result["sla_deadline"] is not None
    assert with_tech_result["assigned_at"] is not None
    assert with_tech_result["rejected_at"] is not None


def test_get_declined_jobs_super_admin(setup_db):
    db = setup_db

    now = datetime.now(timezone.utc)

    other_tenant_job = Job(
        customer_name="Other Tenant Declined",
        location="Other Zone",
        issue_description="Other tenant declined",
        priority="HIGH",
        service_type="HVAC Repair",
        contact_number="9876543250",
        preferred_service_date=now.date(),
        status="REJECTED_BY_TECHNICIAN",
        assigned_technician_id=None,
        rejection_reason="Other tenant reason",
        rejected_at=now,
        tenant_id="tenant-2",
    )

    db.add(other_tenant_job)
    db.commit()

    current_user = SimpleNamespace(
        user_id="super-admin",
        tenant_id="tenant-1",
        role=UserRole.SUPER_ADMIN,
        is_super_admin=True,
    )

    result = planning_route.get_declined_jobs(
        current_user=current_user,
        db=db,
    )

    assert any(
        item["id"] == other_tenant_job.id
        for item in result
    )
