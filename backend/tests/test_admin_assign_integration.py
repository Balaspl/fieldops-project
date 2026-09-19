import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timezone, timedelta
import json
import uuid
from contextlib import contextmanager
from unittest.mock import patch
from app.auth.jwt_handler import create_access_token
from app.main import app
from app.models import (
    Job,
    Technician,
    User,
    Organization,
    AuditEvent,
    SLAEscalation,
    AssignmentOverride,
    OverrideAuditEvent,
)
from app.database import Base, get_db
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from app.redis_client import get_redis_client
from app.auth.rbac import UserRole
from app.auth.dependencies import (
    get_current_user,
    get_current_user_or_tenant,
)

from types import SimpleNamespace

# Setup test DB
SQLALCHEMY_DATABASE_URL = "sqlite://"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

client = TestClient(app)

class MockRedis:
    def __init__(self):
        self.data = {}

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.data:
            return False
        self.data[key] = value
        return True

    def setex(self, key, time, value):
        self.data[key] = value
        return True

    def get(self, key):
        return self.data.get(key)

    def exists(self, key):
        return key in self.data

    def delete(self, key):
        if key in self.data:
            del self.data[key]
            return 1
        return 0

    def incr(self, key, amount=1):
        current = self.data.get(key, 0)

        try:
            current = int(current)
        except (TypeError, ValueError):
            current = 0

        current += amount
        self.data[key] = current
        return current
    def expire(self, key, time):
        return key in self.data

mock_redis = MockRedis()

def get_test_token():
    return create_access_token(
        user_id="test-admin",
        tenant_id="tenant-1",
        #role=UserRole.SUPER_ADMIN.value,
        role="super_admin"
    )

def override_get_redis():
    return mock_redis

@contextmanager
def mock_job_lock(job_id):
    yield "mock_lock"

@pytest.fixture(autouse=True)
def patch_job_lock():
    with patch("app.routes.jobs.with_job_lock", side_effect=mock_job_lock):
        yield

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    organization = Organization(
        id="tenant-1",
        name="Test Organization",
        slug="test-organization",
    )
    
    db.add(organization)
    db.commit()

    test_user = User(
        id="test-admin",
        email="test-admin@example.com",
        password_hash="test-password",
        first_name="Test",
        last_name="Admin",
        role="super_admin",
        tenant_id="tenant-1",
        is_active=True,
        is_email_verified=True,
    )

    db.add(test_user)
    db.commit()

    
    db.query(AuditEvent).delete()
    db.query(Job).delete()
    db.query(Technician).delete()
    db.query(SLAEscalation).delete()
    db.query(AssignmentOverride).delete()
    db.query(OverrideAuditEvent).delete()
    db.commit()
    
    mock_redis.data = {}
    
    yield db
    db.close()

@pytest.fixture(autouse=True)
def apply_overrides():
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis_client] = override_get_redis

    app.dependency_overrides[get_current_user] = (
        lambda: SimpleNamespace(
            user_id="test-admin",
            tenant_id="tenant-1",
            role=UserRole.SUPER_ADMIN,
            is_super_admin=True,
        )
    )

    app.dependency_overrides[get_current_user_or_tenant] = (
        lambda: (
            SimpleNamespace(
                user_id="test-admin",
                tenant_id="tenant-1",
                role="super_admin",
                is_super_admin=True,
            ),
            "tenant-1",
        )
    )

    yield
    app.dependency_overrides.clear()

def test_technicians_metrics_routing(setup_db):
    # Verify that requesting metrics does not match /technicians/{id} routing (FastAPI routing fix validation)
    mock_redis.set("metrics:offline_events:" + datetime.now(timezone.utc).strftime("%Y-%m-%d-%H"), "5")
    
    response = client.get(
        "/technicians/metrics",
        headers={"Authorization": f"Bearer {get_test_token()}", "X-Tenant-ID": "tenant-1"}
    )
    
    assert response.status_code == 200
    assert response.json()["offline_events_current_hour"] == 5

def test_jobs_assign_skill_and_workload_validation(setup_db):
    db = setup_db
    
    # 1. Create a tech with skill Plumbing and workload 3/3
    tech = Technician(
        tech_id="tech-xyz",
        tenant_id="tenant-1",
        technician_name="John Plumber",
        technician_skill="Plumbing",
        technician_location="0,0",
        technician_status="AVAILABLE",
        current_jobs=3,
        max_jobs=3
    )
    db.add(tech)
    db.commit()
    db.refresh(tech)
    
    # 2. Create a job requiring HVAC
    job = Job(
        tenant_id="tenant-1",
        customer_name="Alice",
        location="1,1",
        issue_description="AC leak",
        priority="HIGH",
        service_type="HVAC",
        required_skill="HVAC",
        contact_number="1234567890",
        preferred_service_date=datetime.now(timezone.utc).date(),
        status="QUEUED"
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    
    # Check 1: Should fail skill verification if skip_skill_check is False
    resp1 = client.post(
        f"/jobs/{job.id}/assign",
        headers={"Authorization": f"Bearer {get_test_token()}", "X-Tenant-ID": "tenant-1"},
        json={
            "tech_id": "tech-xyz",
            "justification": "This is a dummy justification with at least 20 chars.",
            "skip_skill_check": False,
            "skip_workload_check": True
        }
    )
    assert resp1.status_code == 400
    assert "missing required skills" in resp1.json()["detail"]
    
    # Check 2: Should fail workload check if skip_workload_check is False
    resp2 = client.post(
        f"/jobs/{job.id}/assign",
        headers={"Authorization": f"Bearer {get_test_token()}", "X-Tenant-ID": "tenant-1"},
        json={
            "tech_id": "tech-xyz",
            "justification": "This is a dummy justification with at least 20 chars.",
            "skip_skill_check": True,
            "skip_workload_check": False
        }
    )
    assert resp2.status_code == 400
    assert "maximum workload capacity" in resp2.json()["detail"]

    # Check 3: Should succeed if both checks are bypassed or skipped
    resp3 = client.post(
        f"/jobs/{job.id}/assign",
        headers={"Authorization": f"Bearer {get_test_token()}", "X-Tenant-ID": "tenant-1"},
        json={
            "tech_id": "tech-xyz",
            "justification": "This is a dummy justification with at least 20 chars.",
            "skip_skill_check": True,
            "skip_workload_check": True
        }
    )
    assert resp3.status_code == 200
    assert resp3.json()["status"] == "ASSIGNED"
    
    # Verify Redis timer is started
    assert mock_redis.exists(f"job:timer:{job.id}") == True

def test_escalation_force_assign_timer(setup_db):
    db = setup_db
    
    tech = Technician(


        tech_id="tech-abc",
        tenant_id="tenant-1",
        technician_name="Bob Mechanic",
        technician_skill="Plumbing",
        technician_location="0,0",
        technician_status="AVAILABLE",
        current_jobs=0
    )
    db.add(tech)
    
    job = Job(
        tenant_id="tenant-1",
        customer_name="Charlie",
        location="1,1",
        issue_description="Leak",
        priority="P1",
        service_type="Plumbing",
        contact_number="123",
        preferred_service_date=datetime.now(timezone.utc).date(),
        status="ESCALATED"
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    
    esc = SLAEscalation(
        tenant_id="tenant-1",
        job_id=job.id,
        status="ESCALATED",
        manager_notified_at=datetime.now(timezone.utc)
    )
    db.add(esc)
    db.commit()
    
    response = client.post(
        f"/escalations/{job.id}/force-assign",
        headers={"Authorization": f"Bearer {get_test_token()}", "X-Tenant-ID": "tenant-1"},
        json={
            "tech_id": "tech-abc",
            "reason": "Expert tech needed immediately"
        }
    )
    print("STATUS:", response.status_code)
    print("RESPONSE:", response.text)

    
    assert response.status_code == 200
    assert response.json()["message"] == "Job force-assigned successfully"
    
    db.refresh(job)
    db.refresh(esc)
    assert job.status == "ASSIGNED"
    assert job.assigned_technician_id == tech.technician_id
    assert esc.manager_responded_at is not None
    assert esc.action_taken == "Force Assigned to tech-abc"
    
    # Verify Redis timer is started
    assert mock_redis.exists(f"job:timer:{job.id}") == True


def test_bulk_job_assignment_success(setup_db):
    db = setup_db

    tech = Technician(
        tech_id="bulk-tech-001",
        tenant_id="tenant-1",
        technician_name="Bulk Technician",
        technician_skill="Plumbing",
        technician_location="0,0",
        technician_status="AVAILABLE",
        current_jobs=0,
        max_jobs=10,
    )
    db.add(tech)

    jobs = []
    for customer_name in ["Customer One", "Customer Two", "Customer Three"]:
        job = Job(
            tenant_id="tenant-1",
            customer_name=customer_name,
            location="1,1",
            issue_description="Plumbing issue",
            priority="HIGH",
            service_type="Plumbing",
            required_skill="Plumbing",
            contact_number="1234567890",
            preferred_service_date=datetime.now(timezone.utc).date(),
            status="QUEUED",
        )
        db.add(job)
        jobs.append(job)

    db.commit()

    for job in jobs:
        db.refresh(job)

    response = client.post(
        "/assign-jobs-bulk",
        headers={
            "Authorization": f"Bearer {get_test_token()}",
            "X-Tenant-ID": "tenant-1",
        },
        json={
            "job_ids": [job.id for job in jobs],
            "technician_id": tech.tech_id,
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["total_requested"] == 3
    assert data["total_assigned"] == 3
    assert len(data["results"]) == 3

    db.refresh(tech)

    assert tech.current_jobs == 3

    for job in jobs:
        db.refresh(job)
        assert job.assigned_technician_id == tech.technician_id
        assert job.status == "ASSIGNED"

        service_request = None
        if hasattr(job, "service_request"):
            service_request = job.service_request

        result = next(
            item for item in data["results"]
            if item["job_id"] == job.id
        )

        assert result["status"] == "ASSIGNED"
        assert result["technician_id"] == tech.technician_id


def test_bulk_job_assignment_rejects_empty_selection(setup_db):
    response = client.post(
        "/assign-jobs-bulk",
        headers={
            "Authorization": f"Bearer {get_test_token()}",
            "X-Tenant-ID": "tenant-1",
        },
        json={
            "job_ids": [],
            "technician_id": "bulk-tech-001",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "At least one job must be selected"


def test_bulk_job_assignment_rejects_invalid_job_id(setup_db):
    db = setup_db

    tech = Technician(
        tech_id="bulk-tech-002",
        tenant_id="tenant-1",
        technician_name="Bulk Technician",
        technician_skill="Plumbing",
        technician_location="0,0",
        technician_status="AVAILABLE",
        current_jobs=0,
        max_jobs=10,
    )
    db.add(tech)
    db.commit()

    response = client.post(
        "/assign-jobs-bulk",
        headers={
            "Authorization": f"Bearer {get_test_token()}",
            "X-Tenant-ID": "tenant-1",
        },
        json={
            "job_ids": ["INVALID"],
            "technician_id": tech.tech_id,
        },
    )

    assert response.status_code == 400
    assert "Invalid job ID" in response.json()["detail"]


def test_bulk_job_assignment_is_atomic_when_one_job_is_already_assigned(setup_db):
    db = setup_db

    tech = Technician(
        tech_id="bulk-tech-003",
        tenant_id="tenant-1",
        technician_name="Bulk Technician",
        technician_skill="Plumbing",
        technician_location="0,0",
        technician_status="AVAILABLE",
        current_jobs=0,
        max_jobs=10,
    )
    existing_tech = Technician(
        tech_id="existing-tech-001",
        tenant_id="tenant-1",
        technician_name="Existing Technician",
        technician_skill="Plumbing",
        technician_location="0,0",
        technician_status="ASSIGNED",
        current_jobs=1,
        max_jobs=10,
    )

    db.add_all([tech, existing_tech])
    db.commit()

    db.refresh(tech)
    db.refresh(existing_tech)

    job1 = Job(
        tenant_id="tenant-1",
        customer_name="Customer One",
        location="1,1",
        issue_description="Plumbing issue",
        priority="HIGH",
        service_type="Plumbing",
        required_skill="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now(timezone.utc).date(),
        status="QUEUED",
    )

    job2 = Job(
        tenant_id="tenant-1",
        customer_name="Customer Two",
        location="1,1",
        issue_description="Plumbing issue",
        priority="HIGH",
        service_type="Plumbing",
        required_skill="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now(timezone.utc).date(),
        status="ASSIGNED",
        assigned_technician_id=existing_tech.technician_id,
    )

    db.add_all([job1, job2])
    db.commit()

    db.refresh(job1)
    db.refresh(job2)
    db.refresh(tech)

    response = client.post(
        "/assign-jobs-bulk",
        headers={
            "Authorization": f"Bearer {get_test_token()}",
            "X-Tenant-ID": "tenant-1",
        },
        json={
            "job_ids": [job1.id, job2.id],
            "technician_id": tech.tech_id,
        },
    )

    assert response.status_code == 400
    assert "already assigned" in response.json()["detail"]

    db.refresh(job1)
    db.refresh(job2)
    db.refresh(tech)

    # Atomicity: job1 must NOT have been partially assigned.
    assert job1.assigned_technician_id is None
    assert job1.status == "QUEUED"

    assert job2.assigned_technician_id == existing_tech.technician_id

    # Technician workload must also remain unchanged.
    assert tech.current_jobs == 0


def test_bulk_job_assignment_rejects_workload_overflow(setup_db):
    db = setup_db

    tech = Technician(
        tech_id="bulk-tech-004",
        tenant_id="tenant-1",
        technician_name="Limited Technician",
        technician_skill="Plumbing",
        technician_location="0,0",
        technician_status="AVAILABLE",
        current_jobs=2,
        max_jobs=3,
    )
    db.add(tech)

    jobs = []

    for customer_name in ["Customer One", "Customer Two"]:
        job = Job(
            tenant_id="tenant-1",
            customer_name=customer_name,
            location="1,1",
            issue_description="Plumbing issue",
            priority="HIGH",
            service_type="Plumbing",
            required_skill="Plumbing",
            contact_number="1234567890",
            preferred_service_date=datetime.now(timezone.utc).date(),
            status="QUEUED",
        )
        db.add(job)
        jobs.append(job)

    db.commit()

    for job in jobs:
        db.refresh(job)

    response = client.post(
        "/assign-jobs-bulk",
        headers={
            "Authorization": f"Bearer {get_test_token()}",
            "X-Tenant-ID": "tenant-1",
        },
        json={
            "job_ids": [job.id for job in jobs],
            "technician_id": tech.tech_id,
        },
    )

    detail = response.json()["detail"].lower()

    assert response.status_code == 400
    assert "cannot assign" in detail
    assert "workload" in detail

    db.refresh(tech)

    assert tech.current_jobs == 2

    for job in jobs:
        db.refresh(job)
        assert job.assigned_technician_id is None
        assert job.status == "QUEUED"


def test_bulk_job_assignment_accepts_job_prefix_and_duplicate_ids(setup_db):
    db = setup_db

    tech = Technician(
        tech_id="bulk-tech-prefix",
        tenant_id="tenant-1",
        technician_name="Prefix Technician",
        technician_skill="Plumbing",
        technician_location="0,0",
        technician_status="AVAILABLE",
        current_jobs=0,
        max_jobs=10,
    )
    db.add(tech)

    job = Job(
        tenant_id="tenant-1",
        customer_name="Prefix Customer",
        location="1,1",
        issue_description="Plumbing issue",
        priority="HIGH",
        service_type="Plumbing",
        required_skill="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now(timezone.utc).date(),
        status="QUEUED",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    db.refresh(tech)

    response = client.post(
        "/assign-jobs-bulk",
        headers={
            "Authorization": f"Bearer {get_test_token()}",
            "X-Tenant-ID": "tenant-1",
        },
        json={
            "job_ids": [f"JOB{job.id}", job.id, str(job.id)],
            "technician_id": tech.tech_id,
        },
    )

    assert response.status_code == 200

    data = response.json()

    # Duplicate IDs must be removed while preserving the first occurrence.
    assert data["total_requested"] == 1
    assert data["total_assigned"] == 1
    assert data["results"][0]["job_id"] == job.id

    db.refresh(job)
    db.refresh(tech)

    assert job.assigned_technician_id == tech.technician_id
    assert job.status == "ASSIGNED"
    assert tech.current_jobs == 1


def test_bulk_job_assignment_rejects_non_positive_job_id(setup_db):
    response = client.post(
        "/assign-jobs-bulk",
        headers={
            "Authorization": f"Bearer {get_test_token()}",
            "X-Tenant-ID": "tenant-1",
        },
        json={
            "job_ids": [0],
            "technician_id": "bulk-tech-001",
        },
    )

    assert response.status_code == 400
    assert "Invalid job ID" in response.json()["detail"]


def test_bulk_job_assignment_rejects_missing_technician(setup_db):
    db = setup_db

    job = Job(
        tenant_id="tenant-1",
        customer_name="Missing Tech Customer",
        location="1,1",
        issue_description="Plumbing issue",
        priority="HIGH",
        service_type="Plumbing",
        required_skill="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now(timezone.utc).date(),
        status="QUEUED",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    response = client.post(
        "/assign-jobs-bulk",
        headers={
            "Authorization": f"Bearer {get_test_token()}",
            "X-Tenant-ID": "tenant-1",
        },
        json={
            "job_ids": [job.id],
            "technician_id": "does-not-exist",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Technician not found"


def test_bulk_job_assignment_rejects_missing_job(setup_db):
    db = setup_db

    tech = Technician(
        tech_id="bulk-tech-missing-job",
        tenant_id="tenant-1",
        technician_name="Missing Job Technician",
        technician_skill="Plumbing",
        technician_location="0,0",
        technician_status="AVAILABLE",
        current_jobs=0,
        max_jobs=10,
    )
    db.add(tech)
    db.commit()
    db.refresh(tech)

    response = client.post(
        "/assign-jobs-bulk",
        headers={
            "Authorization": f"Bearer {get_test_token()}",
            "X-Tenant-ID": "tenant-1",
        },
        json={
            "job_ids": [999999],
            "technician_id": tech.tech_id,
        },
    )

    assert response.status_code == 404
    assert "not found or not accessible" in response.json()["detail"]





def test_bulk_job_assignment_rejects_no_valid_jobs_after_parsing(setup_db):
    # Pydantic accepts strings for the Union[int, str] field,
    # but the endpoint still validates the parsed IDs.
    response = client.post(
        "/assign-jobs-bulk",
        headers={
            "Authorization": f"Bearer {get_test_token()}",
            "X-Tenant-ID": "tenant-1",
        },
        json={
            "job_ids": ["   "],
            "technician_id": "bulk-tech-001",
        },
    )

    assert response.status_code == 400
    assert "Invalid job ID" in response.json()["detail"]


def _normal_user_token():
    return create_access_token(
        user_id="normal-user",
        tenant_id="tenant-1",
        role="dispatcher",
    )


def _create_normal_user(db):
    user = User(
        id="normal-user",
        email="normal@example.com",
        password_hash="test-password",
        first_name="Normal",
        last_name="User",
        role="dispatcher",
        tenant_id="tenant-1",
        is_active=True,
        is_email_verified=True,
    )
    db.add(user)
    db.commit()
    return user


def test_match_skill_returns_matching_technicians(setup_db):
    db = setup_db

    tech = Technician(
        tech_id="skill-tech-001",
        tenant_id="tenant-1",
        technician_name="Plumbing Technician",
        technician_skill="Plumbing",
        technician_location="0,0",
        technician_status="AVAILABLE",
        current_jobs=0,
        max_jobs=5,
    )

    db.add(tech)
    db.commit()

    response = client.get(
        "/technicians/match-skill",
        params={"job_type": "Plumbing"},
        headers={
            "Authorization": f"Bearer {get_test_token()}",
            "X-Tenant-ID": "tenant-1",
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert len(data) == 1
    assert data[0]["tech_id"] == "skill-tech-001"


def test_match_skill_falls_back_when_no_exact_match(setup_db):
    db = setup_db

    tech = Technician(
        tech_id="fallback-tech-001",
        tenant_id="tenant-1",
        technician_name="Fallback Technician",
        technician_skill="Electrical",
        technician_location="0,0",
        technician_status="AVAILABLE",
        current_jobs=0,
        max_jobs=5,
    )

    db.add(tech)
    db.commit()

    response = client.get(
        "/technicians/match-skill",
        params={"job_type": "HVAC"},
        headers={
            "Authorization": f"Bearer {get_test_token()}",
            "X-Tenant-ID": "tenant-1",
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert len(data) == 1
    assert data[0]["tech_id"] == "fallback-tech-001"


def test_match_skill_applies_tenant_filter_for_normal_user(setup_db):
    db = setup_db

    _create_normal_user(db)

    own_tech = Technician(
        tech_id="own-tech",
        tenant_id="tenant-1",
        technician_name="Own Technician",
        technician_skill="Plumbing",
        technician_location="0,0",
        technician_status="AVAILABLE",
        current_jobs=0,
        max_jobs=5,
    )

    other_tech = Technician(
        tech_id="other-tech",
        tenant_id="tenant-2",
        technician_name="Other Technician",
        technician_skill="Plumbing",
        technician_location="0,0",
        technician_status="AVAILABLE",
        current_jobs=0,
        max_jobs=5,
    )

    db.add_all([own_tech, other_tech])
    db.commit()

    app.dependency_overrides[get_current_user_or_tenant] = (
        lambda: (
            type(
                "TestUser",
                (),
                {
                    "is_super_admin": False,
                    "user_id": "normal-user",
                },
            )(),
            "tenant-1",
        )
    )

    try:
        response = client.get(
            "/technicians/match-skill",
            params={"job_type": "Plumbing"},
            headers={
                "Authorization": f"Bearer {_normal_user_token()}",
                "X-Tenant-ID": "tenant-1",
            },
        )
    finally:
        app.dependency_overrides.pop(get_current_user_or_tenant, None)

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["tech_id"] == "own-tech"


def test_nearest_technician_returns_nearest(setup_db):
    db = setup_db

    job = Job(
        tenant_id="tenant-1",
        customer_name="Nearest Customer",
        location="0,0",
        issue_description="Plumbing issue",
        priority="HIGH",
        service_type="Plumbing",
        required_skill="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now(timezone.utc).date(),
        status="QUEUED",
    )

    near = Technician(
        tech_id="near-tech",
        tenant_id="tenant-1",
        technician_name="Near Technician",
        technician_skill="Plumbing",
        technician_location="0.1,0.1",
        technician_status="AVAILABLE",
        current_jobs=0,
        max_jobs=5,
    )

    far = Technician(
        tech_id="far-tech",
        tenant_id="tenant-1",
        technician_name="Far Technician",
        technician_skill="Plumbing",
        technician_location="10,10",
        technician_status="AVAILABLE",
        current_jobs=0,
        max_jobs=5,
    )

    db.add_all([job, near, far])
    db.commit()
    db.refresh(job)

    response = client.get(
        "/technicians/nearest",
        params={"job_id": job.id},
        headers={
            "Authorization": f"Bearer {get_test_token()}",
            "X-Tenant-ID": "tenant-1",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["technician"]["tech_id"] == "near-tech"
    assert data["distance"] >= 0


def test_nearest_technician_rejects_missing_job(setup_db):
    response = client.get(
        "/technicians/nearest",
        params={"job_id": 999999},
        headers={
            "Authorization": f"Bearer {get_test_token()}",
            "X-Tenant-ID": "tenant-1",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found"


def test_nearest_technician_rejects_when_no_available_technician(setup_db):
    db = setup_db

    job = Job(
        tenant_id="tenant-1",
        customer_name="No Tech Customer",
        location="0,0",
        issue_description="Plumbing issue",
        priority="HIGH",
        service_type="Plumbing",
        required_skill="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now(timezone.utc).date(),
        status="QUEUED",
    )

    db.add(job)
    db.commit()
    db.refresh(job)

    response = client.get(
        "/technicians/nearest",
        params={"job_id": job.id},
        headers={
            "Authorization": f"Bearer {get_test_token()}",
            "X-Tenant-ID": "tenant-1",
        },
    )

    assert response.status_code == 404
    assert "No available technicians found" in response.json()["detail"]


def test_assign_job_by_numeric_technician_id(setup_db):
    db = setup_db

    tech = Technician(
        tech_id="numeric-tech",
        tenant_id="tenant-1",
        technician_name="Numeric Technician",
        technician_skill="Plumbing",
        technician_location="0,0",
        technician_status="AVAILABLE",
        current_jobs=0,
        max_jobs=10,
    )

    job = Job(
        tenant_id="tenant-1",
        customer_name="Assignment Customer",
        location="1,1",
        issue_description="Plumbing issue",
        priority="HIGH",
        service_type="Plumbing",
        required_skill="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now(timezone.utc).date(),
        status="QUEUED",
    )

    db.add_all([tech, job])
    db.commit()
    db.refresh(tech)
    db.refresh(job)

    response = client.post(
        "/assign-job",
        headers={
            "Authorization": f"Bearer {get_test_token()}",
            "X-Tenant-ID": "tenant-1",
        },
        json={
            "job_id": job.id,
            "technician_id": tech.technician_id,
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert data["job_id"] == job.id
    assert data["job_status"] == "ASSIGNED"
    assert data["assigned_technician"]["id"] == tech.technician_id


def test_assign_job_by_job_prefix(setup_db):
    db = setup_db

    tech = Technician(
        tech_id="prefix-assignment-tech",
        tenant_id="tenant-1",
        technician_name="Prefix Technician",
        technician_skill="Plumbing",
        technician_location="0,0",
        technician_status="AVAILABLE",
        current_jobs=0,
        max_jobs=10,
    )

    job = Job(
        tenant_id="tenant-1",
        customer_name="Prefix Assignment Customer",
        location="1,1",
        issue_description="Plumbing issue",
        priority="HIGH",
        service_type="Plumbing",
        required_skill="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now(timezone.utc).date(),
        status="QUEUED",
    )

    db.add_all([tech, job])
    db.commit()
    db.refresh(tech)
    db.refresh(job)

    response = client.post(
        "/assign-job",
        headers={
            "Authorization": f"Bearer {get_test_token()}",
            "X-Tenant-ID": "tenant-1",
        },
        json={
            "job_id": f"JOB{job.id}",
            "technician_id": tech.tech_id,
        },
    )

    assert response.status_code == 200
    assert response.json()["job_status"] == "ASSIGNED"


def test_assign_job_rejects_missing_job(setup_db):
    response = client.post(
        "/assign-job",
        headers={
            "Authorization": f"Bearer {get_test_token()}",
            "X-Tenant-ID": "tenant-1",
        },
        json={
            "job_id": 999999,
            "technician_id": "missing-tech",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found"


def test_assign_job_rejects_duplicate_assignment(setup_db):
    db = setup_db

    tech = Technician(
        tech_id="duplicate-tech",
        tenant_id="tenant-1",
        technician_name="Duplicate Technician",
        technician_skill="Plumbing",
        technician_location="0,0",
        technician_status="AVAILABLE",
        current_jobs=0,
        max_jobs=10,
    )

    job = Job(
        tenant_id="tenant-1",
        customer_name="Duplicate Customer",
        location="1,1",
        issue_description="Plumbing issue",
        priority="HIGH",
        service_type="Plumbing",
        required_skill="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now(timezone.utc).date(),
        status="ASSIGNED",
        assigned_technician_id=999,
    )

    db.add_all([tech, job])
    db.commit()
    db.refresh(job)

    response = client.post(
        "/assign-job",
        headers={
            "Authorization": f"Bearer {get_test_token()}",
            "X-Tenant-ID": "tenant-1",
        },
        json={
            "job_id": job.id,
            "technician_id": tech.tech_id,
        },
    )

    assert response.status_code == 400
    assert "already assigned" in response.json()["detail"]


def test_assign_job_rejects_missing_technician(setup_db):
    db = setup_db

    job = Job(
        tenant_id="tenant-1",
        customer_name="Missing Technician Customer",
        location="1,1",
        issue_description="Plumbing issue",
        priority="HIGH",
        service_type="Plumbing",
        required_skill="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now(timezone.utc).date(),
        status="QUEUED",
    )

    db.add(job)
    db.commit()
    db.refresh(job)

    response = client.post(
        "/assign-job",
        headers={
            "Authorization": f"Bearer {get_test_token()}",
            "X-Tenant-ID": "tenant-1",
        },
        json={
            "job_id": job.id,
            "technician_id": "does-not-exist",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Technician not found"


def test_assign_job_rejects_without_technician_or_job_type(setup_db):
    db = setup_db

    job = Job(
        tenant_id="tenant-1",
        customer_name="No Assignment Method Customer",
        location="1,1",
        issue_description="Plumbing issue",
        priority="HIGH",
        service_type="Plumbing",
        required_skill="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now(timezone.utc).date(),
        status="QUEUED",
    )

    db.add(job)
    db.commit()
    db.refresh(job)

    response = client.post(
        "/assign-job",
        headers={
            "Authorization": f"Bearer {get_test_token()}",
            "X-Tenant-ID": "tenant-1",
        },
        json={
            "job_id": job.id,
        },
    )

    assert response.status_code == 400
    assert "Either technician_id or job_type must be provided" in response.json()["detail"]


def test_assign_job_auto_assigns_by_job_type(setup_db):
    db = setup_db

    tech1 = Technician(
        tech_id="auto-tech-1",
        tenant_id="tenant-1",
        technician_name="Busy Technician",
        technician_skill="Plumbing",
        technician_location="0,0",
        technician_status="AVAILABLE",
        current_jobs=2,
        max_jobs=10,
    )

    tech2 = Technician(
        tech_id="auto-tech-2",
        tenant_id="tenant-1",
        technician_name="Available Technician",
        technician_skill="Plumbing",
        technician_location="0,0",
        technician_status="AVAILABLE",
        current_jobs=0,
        max_jobs=10,
    )

    job = Job(
        tenant_id="tenant-1",
        customer_name="Auto Assignment Customer",
        location="1,1",
        issue_description="Plumbing issue",
        priority="HIGH",
        service_type="Plumbing",
        required_skill="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now(timezone.utc).date(),
        status="QUEUED",
    )

    db.add_all([tech1, tech2, job])
    db.commit()
    db.refresh(job)

    response = client.post(
        "/assign-job",
        headers={
            "Authorization": f"Bearer {get_test_token()}",
            "X-Tenant-ID": "tenant-1",
        },
        json={
            "job_id": job.id,
            "job_type": "Plumbing",
        },
    )

    assert response.status_code == 200
    assert response.json()["assigned_technician"]["id"] == tech2.technician_id


def test_assign_job_auto_assignment_rejects_no_available_technician(setup_db):
    db = setup_db

    job = Job(
        tenant_id="tenant-1",
        customer_name="Auto Assignment Failure Customer",
        location="1,1",
        issue_description="Plumbing issue",
        priority="HIGH",
        service_type="Plumbing",
        required_skill="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now(timezone.utc).date(),
        status="QUEUED",
    )

    db.add(job)
    db.commit()
    db.refresh(job)

    response = client.post(
        "/assign-job",
        headers={
            "Authorization": f"Bearer {get_test_token()}",
            "X-Tenant-ID": "tenant-1",
        },
        json={
            "job_id": job.id,
            "job_type": "Plumbing",
        },
    )

    assert response.status_code == 400
    assert "No available technicians found" in response.json()["detail"]


def test_assign_job_updates_existing_service_request(setup_db):
    db = setup_db

    tech = Technician(
        tech_id="service-request-tech",
        tenant_id="tenant-1",
        technician_name="Service Request Technician",
        technician_skill="Plumbing",
        technician_location="0,0",
        technician_status="AVAILABLE",
        current_jobs=0,
        max_jobs=10,
    )

    job = Job(
        tenant_id="tenant-1",
        customer_name="Service Request Customer",
        location="1,1",
        issue_description="Plumbing issue",
        priority="HIGH",
        service_type="Plumbing",
        required_skill="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now(timezone.utc).date(),
        status="QUEUED",
    )

    db.add_all([tech, job])
    db.commit()
    db.refresh(job)

    from app import models

    service_request = models.ServiceRequest(
        request_number=f"REQ-{uuid.uuid4().hex[:8].upper()}",
        customer_user_id="test-admin",
        tenant_id="tenant-1",
        title="Plumbing Service Request",
        description="Plumbing issue",
        linked_job_id=job.id,
        status="UNASSIGNED",
    )

    db.add(service_request)
    db.commit()

    response = client.post(
        "/assign-job",
        headers={
            "Authorization": f"Bearer {get_test_token()}",
            "X-Tenant-ID": "tenant-1",
        },
        json={
            "job_id": job.id,
            "technician_id": tech.tech_id,
        },
    )

    assert response.status_code == 200

    db.refresh(service_request)
    assert service_request.status == "ASSIGNED"


def test_assign_job_handles_sqlalchemy_error(setup_db):
    db = setup_db

    tech = Technician(
        tech_id="sql-error-tech",
        tenant_id="tenant-1",
        technician_name="SQL Error Technician",
        technician_skill="Plumbing",
        technician_location="0,0",
        technician_status="AVAILABLE",
        current_jobs=0,
        max_jobs=10,
    )

    job = Job(
        tenant_id="tenant-1",
        customer_name="SQL Error Customer",
        location="1,1",
        issue_description="Plumbing issue",
        priority="HIGH",
        service_type="Plumbing",
        required_skill="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now(timezone.utc).date(),
        status="QUEUED",
    )

    db.add_all([tech, job])
    db.commit()
    db.refresh(job)

    with patch(
        "app.workload_utils.update_workload_count",
        side_effect=SQLAlchemyError("forced database error"),
    ):
        response = client.post(
            "/assign-job",
            headers={
                "Authorization": f"Bearer {get_test_token()}",
                "X-Tenant-ID": "tenant-1",
            },
            json={
                "job_id": job.id,
                "technician_id": tech.tech_id,
            },
        )

    assert response.status_code == 500
    assert response.json()["detail"] == "Database connection error occurred"


def test_assign_job_handles_unexpected_error(setup_db):
    db = setup_db

    tech = Technician(
        tech_id="unexpected-error-tech",
        tenant_id="tenant-1",
        technician_name="Unexpected Error Technician",
        technician_skill="Plumbing",
        technician_location="0,0",
        technician_status="AVAILABLE",
        current_jobs=0,
        max_jobs=10,
    )

    job = Job(
        tenant_id="tenant-1",
        customer_name="Unexpected Error Customer",
        location="1,1",
        issue_description="Plumbing issue",
        priority="HIGH",
        service_type="Plumbing",
        required_skill="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now(timezone.utc).date(),
        status="QUEUED",
    )

    db.add_all([tech, job])
    db.commit()
    db.refresh(job)

    with patch(
        "app.workload_utils.update_workload_count",
        side_effect=RuntimeError("forced unexpected error"),
    ):
        response = client.post(
            "/assign-job",
            headers={
                "Authorization": f"Bearer {get_test_token()}",
                "X-Tenant-ID": "tenant-1",
            },
            json={
                "job_id": job.id,
                "technician_id": tech.tech_id,
            },
        )

    assert response.status_code == 500
    assert response.json()["detail"] == "An unexpected error occurred"


def test_bulk_job_assignment_uses_numeric_technician_id(setup_db):
    db = setup_db

    tech = Technician(
        tech_id="numeric-bulk-tech",
        tenant_id="tenant-1",
        technician_name="Numeric Bulk Technician",
        technician_skill="Plumbing",
        technician_location="0,0",
        technician_status="AVAILABLE",
        current_jobs=0,
        max_jobs=10,
    )

    job = Job(
        tenant_id="tenant-1",
        customer_name="Numeric Bulk Customer",
        location="1,1",
        issue_description="Plumbing issue",
        priority="HIGH",
        service_type="Plumbing",
        required_skill="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now(timezone.utc).date(),
        status="QUEUED",
    )

    db.add_all([tech, job])
    db.commit()
    db.refresh(tech)
    db.refresh(job)

    response = client.post(
        "/assign-jobs-bulk",
        headers={
            "Authorization": f"Bearer {get_test_token()}",
            "X-Tenant-ID": "tenant-1",
        },
        json={
            "job_ids": [job.id],
            "technician_id": tech.technician_id,
        },
    )

    assert response.status_code == 200
    assert response.json()["total_assigned"] == 1


def test_bulk_job_assignment_updates_existing_service_request(setup_db):
    db = setup_db

    tech = Technician(
        tech_id="bulk-service-tech",
        tenant_id="tenant-1",
        technician_name="Bulk Service Technician",
        technician_skill="Plumbing",
        technician_location="0,0",
        technician_status="AVAILABLE",
        current_jobs=0,
        max_jobs=10,
    )

    job = Job(
        tenant_id="tenant-1",
        customer_name="Bulk Service Customer",
        location="1,1",
        issue_description="Plumbing issue",
        priority="HIGH",
        service_type="Plumbing",
        required_skill="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now(timezone.utc).date(),
        status="QUEUED",
    )

    db.add_all([tech, job])
    db.commit()
    db.refresh(job)

    from app import models

    service_request = models.ServiceRequest(
        request_number=f"REQ-{uuid.uuid4().hex[:8].upper()}",
        customer_user_id="test-admin",
        tenant_id="tenant-1",
        title="Plumbing Service Request",
        description="Plumbing issue",
        linked_job_id=job.id,
        status="UNASSIGNED",
    )

    db.add(service_request)
    db.commit()

    response = client.post(
        "/assign-jobs-bulk",
        headers={
            "Authorization": f"Bearer {get_test_token()}",
            "X-Tenant-ID": "tenant-1",
        },
        json={
            "job_ids": [job.id],
            "technician_id": tech.tech_id,
        },
    )

    assert response.status_code == 200

    db.refresh(service_request)
    assert service_request.status == "ASSIGNED"


def test_bulk_job_assignment_handles_sqlalchemy_error(setup_db):
    db = setup_db

    tech = Technician(
        tech_id="bulk-sql-error-tech",
        tenant_id="tenant-1",
        technician_name="Bulk SQL Error Technician",
        technician_skill="Plumbing",
        technician_location="0,0",
        technician_status="AVAILABLE",
        current_jobs=0,
        max_jobs=10,
    )

    job = Job(
        tenant_id="tenant-1",
        customer_name="Bulk SQL Error Customer",
        location="1,1",
        issue_description="Plumbing issue",
        priority="HIGH",
        service_type="Plumbing",
        required_skill="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now(timezone.utc).date(),
        status="QUEUED",
    )

    db.add_all([tech, job])
    db.commit()
    db.refresh(job)

    with patch(
        "app.workload_utils.update_workload_count",
        side_effect=SQLAlchemyError("forced database error"),
    ):
        response = client.post(
            "/assign-jobs-bulk",
            headers={
                "Authorization": f"Bearer {get_test_token()}",
                "X-Tenant-ID": "tenant-1",
            },
            json={
                "job_ids": [job.id],
                "technician_id": tech.tech_id,
            },
        )

    assert response.status_code == 500
    assert response.json()["detail"] == "Database connection error occurred"


def test_bulk_job_assignment_handles_unexpected_error(setup_db):
    db = setup_db

    tech = Technician(
        tech_id="bulk-unexpected-tech",
        tenant_id="tenant-1",
        technician_name="Bulk Unexpected Technician",
        technician_skill="Plumbing",
        technician_location="0,0",
        technician_status="AVAILABLE",
        current_jobs=0,
        max_jobs=10,
    )

    job = Job(
        tenant_id="tenant-1",
        customer_name="Bulk Unexpected Customer",
        location="1,1",
        issue_description="Plumbing issue",
        priority="HIGH",
        service_type="Plumbing",
        required_skill="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now(timezone.utc).date(),
        status="QUEUED",
    )

    db.add_all([tech, job])
    db.commit()
    db.refresh(job)

    with patch(
        "app.workload_utils.update_workload_count",
        side_effect=RuntimeError("forced unexpected error"),
    ):
        response = client.post(
            "/assign-jobs-bulk",
            headers={
                "Authorization": f"Bearer {get_test_token()}",
                "X-Tenant-ID": "tenant-1",
            },
            json={
                "job_ids": [job.id],
                "technician_id": tech.tech_id,
            },
        )

    assert response.status_code == 500
    assert response.json()["detail"] == "An unexpected error occurred"


def test_match_skill_applies_tenant_filter_for_normal_user_fallback(setup_db):
    db = setup_db

    _create_normal_user(db)

    own_tech = Technician(
        tech_id="fallback-own-tech",
        tenant_id="tenant-1",
        technician_name="Own Fallback Technician",
        technician_skill="Electrical",
        technician_location="0,0",
        technician_status="AVAILABLE",
        current_jobs=0,
        max_jobs=5,
    )

    other_tech = Technician(
        tech_id="fallback-other-tech",
        tenant_id="tenant-2",
        technician_name="Other Fallback Technician",
        technician_skill="Electrical",
        technician_location="0,0",
        technician_status="AVAILABLE",
        current_jobs=0,
        max_jobs=5,
    )

    db.add_all([own_tech, other_tech])
    db.commit()

    app.dependency_overrides[get_current_user_or_tenant] = (
        lambda: (
            type(
                "TestUser",
                (),
                {
                    "is_super_admin": False,
                    "user_id": "normal-user",
                },
            )(),
            "tenant-1",
        )
    )

    try:
        response = client.get(
            "/technicians/match-skill",
            params={"job_type": "HVAC"},
            headers={
                "Authorization": f"Bearer {_normal_user_token()}",
                "X-Tenant-ID": "tenant-1",
            },
        )
    finally:
        app.dependency_overrides.pop(get_current_user_or_tenant, None)

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["tech_id"] == "fallback-own-tech"
def test_nearest_technician_applies_tenant_filter_for_normal_user(setup_db):
    db = setup_db

    _create_normal_user(db)

    job = Job(
        tenant_id="tenant-1",
        customer_name="Tenant Test Customer",
        location="0,0",
        issue_description="Plumbing issue",
        priority="HIGH",
        service_type="Plumbing",
        required_skill="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now(timezone.utc).date(),
        status="QUEUED",
    )

    own_tech = Technician(
        tech_id="tenant-own-tech",
        tenant_id="tenant-1",
        technician_name="Own Technician",
        technician_skill="Plumbing",
        technician_location="0.1,0.1",
        technician_status="AVAILABLE",
        current_jobs=0,
        max_jobs=5,
    )

    other_tech = Technician(
        tech_id="tenant-other-tech",
        tenant_id="tenant-2",
        technician_name="Other Technician",
        technician_skill="Plumbing",
        technician_location="0.01,0.01",
        technician_status="AVAILABLE",
        current_jobs=0,
        max_jobs=5,
    )

    db.add_all([job, own_tech, other_tech])
    db.commit()
    db.refresh(job)

    app.dependency_overrides[get_current_user_or_tenant] = (
        lambda: (
            type(
                "TestUser",
                (),
                {
                    "is_super_admin": False,
                    "user_id": "normal-user",
                },
            )(),
            "tenant-1",
        )
    )

    try:
        response = client.get(
            "/technicians/nearest",
            params={"job_id": job.id},
            headers={
                "Authorization": f"Bearer {_normal_user_token()}",
                "X-Tenant-ID": "tenant-1",
            },
        )
    finally:
        app.dependency_overrides.pop(get_current_user_or_tenant, None)

    assert response.status_code == 200

    data = response.json()

    assert data["technician"]["tech_id"] == "tenant-own-tech"
    assert data["distance"] >= 0


def test_assign_job_rejects_job_from_other_tenant_for_normal_user(setup_db):
    db = setup_db

    _create_normal_user(db)

    tech = Technician(
        tech_id="tenant-assign-tech",
        tenant_id="tenant-1",
        technician_name="Tenant Assignment Technician",
        technician_skill="Plumbing",
        technician_location="0,0",
        technician_status="AVAILABLE",
        current_jobs=0,
        max_jobs=10,
    )

    other_job = Job(
        tenant_id="tenant-2",
        customer_name="Other Tenant Customer",
        location="1,1",
        issue_description="Plumbing issue",
        priority="HIGH",
        service_type="Plumbing",
        required_skill="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now(timezone.utc).date(),
        status="QUEUED",
    )

    db.add_all([tech, other_job])
    db.commit()
    db.refresh(other_job)

    app.dependency_overrides[get_current_user_or_tenant] = (
        lambda: (
            type(
                "TestUser",
                (),
                {
                    "is_super_admin": False,
                    "user_id": "normal-user",
                },
            )(),
            "tenant-1",
        )
    )

    try:
        response = client.post(
            "/assign-job",
            headers={
                "Authorization": f"Bearer {_normal_user_token()}",
                "X-Tenant-ID": "tenant-1",
            },
            json={
                "job_id": other_job.id,
                "technician_id": tech.tech_id,
            },
        )
    finally:
        app.dependency_overrides.pop(get_current_user_or_tenant, None)

    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found"


def test_assign_job_rejects_other_tenant_numeric_technician_for_normal_user(setup_db):
    db = setup_db

    _create_normal_user(db)

    tech = Technician(
        tech_id="other-numeric-tech",
        tenant_id="tenant-2",
        technician_name="Other Tenant Technician",
        technician_skill="Plumbing",
        technician_location="0,0",
        technician_status="AVAILABLE",
        current_jobs=0,
        max_jobs=10,
    )

    job = Job(
        tenant_id="tenant-1",
        customer_name="Tenant Customer",
        location="1,1",
        issue_description="Plumbing issue",
        priority="HIGH",
        service_type="Plumbing",
        required_skill="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now(timezone.utc).date(),
        status="QUEUED",
    )

    db.add_all([tech, job])
    db.commit()
    db.refresh(tech)
    db.refresh(job)

    app.dependency_overrides[get_current_user_or_tenant] = (
        lambda: (
            type(
                "TestUser",
                (),
                {
                    "is_super_admin": False,
                    "user_id": "normal-user",
                },
            )(),
            "tenant-1",
        )
    )

    try:
        response = client.post(
            "/assign-job",
            headers={
                "Authorization": f"Bearer {_normal_user_token()}",
                "X-Tenant-ID": "tenant-1",
            },
            json={
                "job_id": job.id,
                "technician_id": tech.technician_id,
            },
        )
    finally:
        app.dependency_overrides.pop(get_current_user_or_tenant, None)

    assert response.status_code == 404
    assert response.json()["detail"] == "Technician not found"


def test_assign_job_rejects_other_tenant_string_technician_for_normal_user(setup_db):
    db = setup_db

    _create_normal_user(db)

    tech = Technician(
        tech_id="other-string-tech",
        tenant_id="tenant-2",
        technician_name="Other Tenant String Technician",
        technician_skill="Plumbing",
        technician_location="0,0",
        technician_status="AVAILABLE",
        current_jobs=0,
        max_jobs=10,
    )

    job = Job(
        tenant_id="tenant-1",
        customer_name="Tenant Customer",
        location="1,1",
        issue_description="Plumbing issue",
        priority="HIGH",
        service_type="Plumbing",
        required_skill="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now(timezone.utc).date(),
        status="QUEUED",
    )

    db.add_all([tech, job])
    db.commit()
    db.refresh(job)

    app.dependency_overrides[get_current_user_or_tenant] = (
        lambda: (
            type(
                "TestUser",
                (),
                {
                    "is_super_admin": False,
                    "user_id": "normal-user",
                },
            )(),
            "tenant-1",
        )
    )

    try:
        response = client.post(
            "/assign-job",
            headers={
                "Authorization": f"Bearer {_normal_user_token()}",
                "X-Tenant-ID": "tenant-1",
            },
            json={
                "job_id": job.id,
                "technician_id": tech.tech_id,
            },
        )
    finally:
        app.dependency_overrides.pop(get_current_user_or_tenant, None)

    assert response.status_code == 404
    assert response.json()["detail"] == "Technician not found"


def test_assign_job_auto_assignment_enforces_tenant_for_normal_user(setup_db):
    db = setup_db

    _create_normal_user(db)

    job = Job(
        tenant_id="tenant-1",
        customer_name="Auto Tenant Customer",
        location="1,1",
        issue_description="Plumbing issue",
        priority="HIGH",
        service_type="Plumbing",
        required_skill="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now(timezone.utc).date(),
        status="QUEUED",
    )

    other_tech = Technician(
        tech_id="other-auto-tech",
        tenant_id="tenant-2",
        technician_name="Other Tenant Auto Technician",
        technician_skill="Plumbing",
        technician_location="0,0",
        technician_status="AVAILABLE",
        current_jobs=0,
        max_jobs=10,
    )

    db.add_all([job, other_tech])
    db.commit()
    db.refresh(job)

    app.dependency_overrides[get_current_user_or_tenant] = (
        lambda: (
            type(
                "TestUser",
                (),
                {
                    "is_super_admin": False,
                    "user_id": "normal-user",
                },
            )(),
            "tenant-1",
        )
    )

    try:
        response = client.post(
            "/assign-job",
            headers={
                "Authorization": f"Bearer {_normal_user_token()}",
                "X-Tenant-ID": "tenant-1",
            },
            json={
                "job_id": job.id,
                "job_type": "Plumbing",
            },
        )
    finally:
        app.dependency_overrides.pop(get_current_user_or_tenant, None)

    assert response.status_code == 400
    assert "No available technicians found" in response.json()["detail"]


def test_bulk_assignment_rejects_other_tenant_numeric_technician_for_normal_user(setup_db):
    db = setup_db

    _create_normal_user(db)

    job = Job(
        tenant_id="tenant-1",
        customer_name="Bulk Tenant Customer",
        location="1,1",
        issue_description="Plumbing issue",
        priority="HIGH",
        service_type="Plumbing",
        required_skill="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now(timezone.utc).date(),
        status="QUEUED",
    )

    other_tech = Technician(
        tech_id="other-bulk-numeric-tech",
        tenant_id="tenant-2",
        technician_name="Other Bulk Technician",
        technician_skill="Plumbing",
        technician_location="0,0",
        technician_status="AVAILABLE",
        current_jobs=0,
        max_jobs=10,
    )

    db.add_all([job, other_tech])
    db.commit()
    db.refresh(job)
    db.refresh(other_tech)

    app.dependency_overrides[get_current_user_or_tenant] = (
        lambda: (
            type(
                "TestUser",
                (),
                {
                    "is_super_admin": False,
                    "user_id": "normal-user",
                },
            )(),
            "tenant-1",
        )
    )

    try:
        response = client.post(
            "/assign-jobs-bulk",
            headers={
                "Authorization": f"Bearer {_normal_user_token()}",
                "X-Tenant-ID": "tenant-1",
            },
            json={
                "job_ids": [job.id],
                "technician_id": other_tech.technician_id,
            },
        )
    finally:
        app.dependency_overrides.pop(get_current_user_or_tenant, None)

    assert response.status_code == 404
    assert response.json()["detail"] == "Technician not found"


def test_bulk_assignment_rejects_other_tenant_string_technician_for_normal_user(setup_db):
    db = setup_db

    _create_normal_user(db)

    job = Job(
        tenant_id="tenant-1",
        customer_name="Bulk String Tenant Customer",
        location="1,1",
        issue_description="Plumbing issue",
        priority="HIGH",
        service_type="Plumbing",
        required_skill="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now(timezone.utc).date(),
        status="QUEUED",
    )

    other_tech = Technician(
        tech_id="other-bulk-string-tech",
        tenant_id="tenant-2",
        technician_name="Other Bulk String Technician",
        technician_skill="Plumbing",
        technician_location="0,0",
        technician_status="AVAILABLE",
        current_jobs=0,
        max_jobs=10,
    )

    db.add_all([job, other_tech])
    db.commit()
    db.refresh(job)

    app.dependency_overrides[get_current_user_or_tenant] = (
        lambda: (
            type(
                "TestUser",
                (),
                {
                    "is_super_admin": False,
                    "user_id": "normal-user",
                },
            )(),
            "tenant-1",
        )
    )

    try:
        response = client.post(
            "/assign-jobs-bulk",
            headers={
                "Authorization": f"Bearer {_normal_user_token()}",
                "X-Tenant-ID": "tenant-1",
            },
            json={
                "job_ids": [job.id],
                "technician_id": other_tech.tech_id,
            },
        )
    finally:
        app.dependency_overrides.pop(get_current_user_or_tenant, None)

    assert response.status_code == 404
    assert response.json()["detail"] == "Technician not found"


def test_bulk_assignment_rejects_other_tenant_job_for_normal_user(setup_db):
    db = setup_db

    _create_normal_user(db)

    tech = Technician(
        tech_id="bulk-own-tech",
        tenant_id="tenant-1",
        technician_name="Own Bulk Technician",
        technician_skill="Plumbing",
        technician_location="0,0",
        technician_status="AVAILABLE",
        current_jobs=0,
        max_jobs=10,
    )

    other_job = Job(
        tenant_id="tenant-2",
        customer_name="Other Tenant Bulk Customer",
        location="1,1",
        issue_description="Plumbing issue",
        priority="HIGH",
        service_type="Plumbing",
        required_skill="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now(timezone.utc).date(),
        status="QUEUED",
    )

    db.add_all([tech, other_job])
    db.commit()
    db.refresh(other_job)

    app.dependency_overrides[get_current_user_or_tenant] = (
        lambda: (
            type(
                "TestUser",
                (),
                {
                    "is_super_admin": False,
                    "user_id": "normal-user",
                },
            )(),
            "tenant-1",
        )
    )

    try:
        response = client.post(
            "/assign-jobs-bulk",
            headers={
                "Authorization": f"Bearer {_normal_user_token()}",
                "X-Tenant-ID": "tenant-1",
            },
            json={
                "job_ids": [other_job.id],
                "technician_id": tech.tech_id,
            },
        )
    finally:
        app.dependency_overrides.pop(get_current_user_or_tenant, None)

    assert response.status_code == 404
    assert "not found or not accessible" in response.json()["detail"]


def test_bulk_assignment_covers_empty_parsed_job_ids_branch(setup_db):
    db = setup_db

    from app.routes.assignment import assign_jobs_bulk

    class TruthyEmptyJobIds:
        def __bool__(self):
            return True

        def __iter__(self):
            return iter([])

    assignment = SimpleNamespace(
        job_ids=TruthyEmptyJobIds(),
        technician_id="unused-tech",
    )

    user = type(
        "TestUser",
        (),
        {
            "is_super_admin": False,
            "user_id": "normal-user",
        },
    )()

    with pytest.raises(Exception) as exc_info:
        assign_jobs_bulk(
            assignment=assignment,
            user_tenant=(user, "tenant-1"),
            db=db,
        )

    assert "No valid jobs were provided" in str(exc_info.value)





def _bulk_cancel_user(role="dispatcher", tenant_id="tenant-1"):
    return SimpleNamespace(
        user_id=f"bulk-cancel-{role}",
        tenant_id=tenant_id,
        role=SimpleNamespace(value=role),
    )


def _bulk_cancel_headers():
    return {
        "Authorization": f"Bearer {get_test_token()}",
        "X-Tenant-ID": "tenant-1",
    }


def _create_bulk_cancel_job(db, status="CREATED", tenant_id="tenant-1"):
    job = Job(
        tenant_id=tenant_id,
        customer_name="Bulk Cancel Customer",
        location="1,1",
        issue_description="Plumbing issue",
        priority="HIGH",
        service_type="Plumbing",
        required_skill="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now(timezone.utc).date(),
        status=status,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def test_bulk_job_cancellation_success(setup_db):
    db = setup_db

    job1 = _create_bulk_cancel_job(db, status="CREATED")
    job2 = _create_bulk_cancel_job(db, status="CREATED")

    app.dependency_overrides[get_current_user] = (
        lambda: _bulk_cancel_user("dispatcher", "tenant-1")
    )

    try:
        response = client.post(
            "/api/v1/jobs/bulk-cancel",
            headers=_bulk_cancel_headers(),
            json={
                "job_ids": [job1.id, job2.id],
                "reason": "Dispatcher cancelled selected jobs",
            },
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "success"
    assert data["total_requested"] == 2
    assert data["total_cancelled"] == 2
    assert len(data["results"]) == 2

    db.refresh(job1)
    db.refresh(job2)

    assert job1.status == "CANCELLED"
    assert job2.status == "CANCELLED"
    assert job1.cancellation_reason == "Dispatcher cancelled selected jobs"
    assert job2.cancellation_reason == "Dispatcher cancelled selected jobs"


def test_bulk_job_cancellation_rejects_mixed_eligible_and_ineligible_jobs(
    setup_db,
):
    db = setup_db

    eligible_job = _create_bulk_cancel_job(
        db,
        status="CREATED",
    )

    ineligible_job = _create_bulk_cancel_job(
        db,
        status="COMPLETED",
    )

    app.dependency_overrides[get_current_user] = (
        lambda: _bulk_cancel_user("dispatcher", "tenant-1")
    )

    try:
        response = client.post(
            "/api/v1/jobs/bulk-cancel",
            headers=_bulk_cancel_headers(),
            json={
                "job_ids": [
                    eligible_job.id,
                    ineligible_job.id,
                ],
                "reason": "Bulk cancellation validation test",
            },
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 400

    detail = response.json()["detail"]

    assert detail["error"] == "BULK_CANCELLATION_VALIDATION_FAILED"
    assert any(
        error["job_id"] == ineligible_job.id
        and error["error"] == "INVALID_TRANSITION"
        for error in detail["errors"]
    )

    db.refresh(eligible_job)
    db.refresh(ineligible_job)

    # Atomic validation: eligible job must not be cancelled
    # when another selected job fails validation.
    assert eligible_job.status == "CREATED"
    assert ineligible_job.status == "COMPLETED"


def test_bulk_job_cancellation_requires_reason(setup_db):
    db = setup_db

    job = _create_bulk_cancel_job(
        db,
        status="CREATED",
    )

    app.dependency_overrides[get_current_user] = (
        lambda: _bulk_cancel_user("dispatcher", "tenant-1")
    )

    try:
        response = client.post(
            "/api/v1/jobs/bulk-cancel",
            headers=_bulk_cancel_headers(),
            json={
                "job_ids": [job.id],
                "reason": "   ",
            },
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 400

    detail = response.json()["detail"]

    assert detail["error"] == "BULK_CANCELLATION_VALIDATION_FAILED"
    assert detail["errors"][0]["job_id"] == job.id
    assert detail["errors"][0]["error"] == "REASON_REQUIRED"

    db.refresh(job)
    assert job.status == "CREATED"


def test_bulk_job_cancellation_enforces_tenant_isolation(setup_db):
    db = setup_db

    other_tenant_job = _create_bulk_cancel_job(
        db,
        status="CREATED",
        tenant_id="tenant-2",
    )

    app.dependency_overrides[get_current_user] = (
        lambda: _bulk_cancel_user("dispatcher", "tenant-1")
    )

    try:
        response = client.post(
            "/api/v1/jobs/bulk-cancel",
            headers=_bulk_cancel_headers(),
            json={
                "job_ids": [other_tenant_job.id],
                "reason": "Cross tenant cancellation attempt",
            },
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 404

    detail = response.json()["detail"]

    assert detail["error"] == "JOB_NOT_FOUND"
    assert other_tenant_job.id in detail["job_ids"]

    db.refresh(other_tenant_job)

    assert other_tenant_job.status == "CREATED"


def test_bulk_job_cancellation_rejects_unauthorized_role(setup_db):
    db = setup_db

    job = _create_bulk_cancel_job(
        db,
        status="CREATED",
    )

    app.dependency_overrides[get_current_user] = (
        lambda: _bulk_cancel_user("technician", "tenant-1")
    )

    try:
        response = client.post(
            "/api/v1/jobs/bulk-cancel",
            headers=_bulk_cancel_headers(),
            json={
                "job_ids": [job.id],
                "reason": "Unauthorized cancellation attempt",
            },
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 403
    assert (
        response.json()["detail"]
        == "Only dispatcher or admin can perform bulk cancellation"
    )

    db.refresh(job)

    assert job.status == "CREATED"