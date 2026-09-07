import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timezone
from unittest.mock import patch
from app.main import app
from app.models import Job, Technician, AuditEvent, SLAEscalation, AssignmentOverride, OverrideAuditEvent,User, Organization
from app.auth.jwt_handler import create_access_token
from app.database import Base, get_db
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from app.redis_client import get_redis_client

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
        self.data.pop(key, None)
        return 1

mock_redis = MockRedis()
def get_test_token():
    return create_access_token(
        user_id="test-admin",
        tenant_id="tenant-1",
        role="super_admin",
    )

def override_get_redis():
    return mock_redis

from contextlib import contextmanager
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

    organization = Organization(id="tenant-1", name="Test Organization", slug="test-organization")
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

    yield db
    db.close()

@pytest.fixture(autouse=True)
def apply_overrides():
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis_client] = override_get_redis
    yield
    app.dependency_overrides.clear()

def test_assign_busy_offline_technician_blocked(setup_db):
    db = setup_db
    
    # 1. Create Busy, Offline, and Available technicians
    tech_busy = Technician(
        tech_id="tech-busy",
        tenant_id="tenant-1",
        technician_name="Busy Tech",
        technician_skill="Plumbing",
        technician_location="0,0",
        technician_status="Busy",
        current_jobs=0,
        max_jobs=3
    )
    tech_offline = Technician(
        tech_id="tech-offline",
        tenant_id="tenant-1", 
        technician_name="Offline Tech",
        technician_skill="Plumbing",
        technician_location="0,0",
        technician_status="offline",
        current_jobs=0,
        max_jobs=3
    )
    tech_available = Technician(
        tech_id="tech-available",
        tenant_id="tenant-1", 
        technician_name="Available Tech",
        technician_skill="Plumbing",
        technician_location="0,0",
        technician_status="AVAILABLE",
        current_jobs=0,
        max_jobs=3
    )
    db.add_all([tech_busy, tech_offline, tech_available])
    db.commit()

    # Create jobs
    job1 = Job(
        tenant_id="tenant-1", 
        customer_name="Customer 1",
        location="1,1",
        issue_description="Leaking pipe",
        priority="HIGH",
        service_type="Plumbing",
        required_skill="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now(timezone.utc).date(),
        status="QUEUED"
    )
    job2 = Job(
        tenant_id="tenant-1", 
        customer_name="Customer 2",
        location="1,1",
        issue_description="Leaking pipe",
        priority="HIGH",
        service_type="Plumbing",
        required_skill="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now(timezone.utc).date(),
        status="QUEUED"
    )
    db.add_all([job1, job2])
    db.commit()
    db.refresh(job1)
    db.refresh(job2)

    # Assignment check: Try assigning Busy technician (should fail)
    resp = client.post(
        f"/jobs/{job1.id}/assign",
        headers={"Authorization": f"Bearer {get_test_token()}", "X-Tenant-ID": "tenant-1"},
        json={
            "tech_id": "tech-busy",
            "justification": "Force test justification with length limit 20."
        }
    )
    assert resp.status_code == 400
    assert "unavailable" in resp.json()["detail"].lower()

    # Assignment check: Try assigning Offline technician (should fail)
    resp = client.post(
        f"/jobs/{job1.id}/assign",
        headers={"Authorization": f"Bearer {get_test_token()}", "X-Tenant-ID": "tenant-1"},
        json={
            "tech_id": "tech-offline",
            "justification": "Force test justification with length limit 20."
        }
    )
    assert resp.status_code == 400
    assert "unavailable" in resp.json()["detail"].lower()

    # Assignment check: Assign Available technician (should succeed)
    resp = client.post(
        f"/jobs/{job1.id}/assign",
        headers={"Authorization": f"Bearer {get_test_token()}", "X-Tenant-ID": "tenant-1"},
        json={
            "tech_id": "tech-available",
            "justification": "Force test justification with length limit 20."
        }
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ASSIGNED"

def test_force_assign_busy_offline_blocked(setup_db):
    db = setup_db
    
    tech_busy = Technician(
        tech_id="tech-busy",
        tenant_id="tenant-1",
        technician_name="Busy Tech",
        technician_skill="Plumbing",
        technician_location="0,0",
        technician_status="Busy",
        current_jobs=0
    )
    db.add(tech_busy)
    
    job = Job(
        tenant_id="tenant-1", 
        customer_name="Customer 1",
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

    # Try force-assigning Busy technician
    resp = client.post(
        f"/escalations/{job.id}/force-assign",
        headers={"Authorization": f"Bearer {get_test_token()}", "X-Tenant-ID": "tenant-1"},
        json={
            "tech_id": "tech-busy",
            "reason": "Expert tech needed immediately"
        }
    )
    assert resp.status_code == 400
    assert "unavailable" in resp.json()["detail"].lower()

def test_availability_endpoint(setup_db):
    db = setup_db
    tech = Technician(
        tech_id="tech-test",
        technician_name="Test Tech",
        technician_skill="Plumbing",
        technician_location="0,0",
        technician_status="AVAILABLE",
        current_jobs=0,
        max_jobs=3
    )
    db.add(tech)
    db.commit()
    db.refresh(tech)

    # Test update availability status via PUT /technicians/{id}/availability using string tech_id
    resp = client.put(
        f"/technicians/{tech.tech_id}/availability",
        json={"technician_status": "Busy"}
    )
    assert resp.status_code == 200
    assert resp.json()["technician"]["technician_status"] == "Busy"

    # Test update availability status via PUT /technicians/{id}/availability using numeric technician_id
    resp = client.put(
        f"/technicians/{tech.technician_id}/availability",
        json={"technician_status": "Offline"}
    )
    assert resp.status_code == 200
    assert resp.json()["technician"]["technician_status"] == "Offline"
    # Test with invalid status value
    resp = client.put(
        f"/technicians/{tech.technician_id}/availability",
        json={"technician_status": "InvalidStatus"}
    )
    assert resp.status_code in [400, 422]
