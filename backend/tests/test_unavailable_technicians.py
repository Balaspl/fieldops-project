import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timezone
from unittest.mock import patch
from contextlib import contextmanager

from app.main import app
from app.models import (
    Job,
    Technician,
    AuditEvent,
    SLAEscalation,
    AssignmentOverride,
    OverrideAuditEvent,
    User,
    Organization,
)
from app.auth.jwt_handler import create_access_token
from app.database import Base, get_db
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from app.redis_client import get_redis_client
from app.auth.dependencies import (
    get_current_user_or_tenant,
    AuthenticatedUser,
)


# ============================================================
# Setup test DB
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
# Mock Redis
# ============================================================

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

    def incr(self, key):
        self.data[key] = int(self.data.get(key, 0)) + 1
        return self.data[key]

    def expire(self, key, seconds):
        return True

    def ping(self):
        return True

    def flushall(self):
        self.data.clear()
        return True


mock_redis = MockRedis()


# ============================================================
# Test JWT
# ============================================================

def get_test_token():
    return create_access_token(
        user_id="test-admin",
        tenant_id="tenant-1",
        role="super_admin",
    )


# ============================================================
# Authentication override
# ============================================================

def override_auth():
    user = AuthenticatedUser(
        user_id="test-admin",
        tenant_id="tenant-1",
        role="super_admin",
        jti="test-jti",
    )

    return user, "tenant-1"


# ============================================================
# Redis override
# ============================================================

def override_get_redis():
    return mock_redis


# ============================================================
# Job lock mock
# ============================================================

@contextmanager
def mock_job_lock(job_id):
    yield "mock_lock"


@pytest.fixture(autouse=True)
def patch_job_lock():
    with patch(
        "app.routes.jobs.with_job_lock",
        side_effect=mock_job_lock,
    ):
        yield


# ============================================================
# Database setup
# ============================================================

@pytest.fixture(autouse=True)
def setup_db():

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()

    # --------------------------------------------------------
    # Organization
    # --------------------------------------------------------

    organization = Organization(
        id="tenant-1",
        name="Test Organization",
        slug="test-organization",
    )

    db.add(organization)
    db.commit()

    # --------------------------------------------------------
    # Test user
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Cleanup tables
    # --------------------------------------------------------

    db.query(AuditEvent).delete()
    db.query(Job).delete()
    db.query(Technician).delete()
    db.query(SLAEscalation).delete()
    db.query(AssignmentOverride).delete()
    db.query(OverrideAuditEvent).delete()

    db.commit()

    # --------------------------------------------------------
    # Reset Redis
    # --------------------------------------------------------

    mock_redis.flushall()

    yield db

    db.close()


# ============================================================
# FastAPI dependency overrides
# ============================================================

@pytest.fixture(autouse=True)
def apply_overrides():

    app.dependency_overrides[get_db] = override_get_db

    app.dependency_overrides[
        get_redis_client
    ] = override_get_redis

    app.dependency_overrides[
        get_current_user_or_tenant
    ] = override_auth

    yield

    app.dependency_overrides.clear()


# ============================================================
# Test: busy/offline/available technician assignment
# ============================================================

def test_assign_busy_offline_technician_blocked(setup_db):

    db = setup_db

    # --------------------------------------------------------
    # 1. Create technicians
    # --------------------------------------------------------

    tech_busy = Technician(
        tech_id="tech-busy",
        tenant_id="tenant-1",
        technician_name="Busy Tech",
        technician_skill="Plumbing",
        technician_location="0,0",
        technician_status="Busy",
        current_jobs=0,
        max_jobs=3,
    )

    tech_offline = Technician(
        tech_id="tech-offline",
        tenant_id="tenant-1",
        technician_name="Offline Tech",
        technician_skill="Plumbing",
        technician_location="0,0",
        technician_status="offline",
        current_jobs=0,
        max_jobs=3,
    )

    tech_available = Technician(
        tech_id="tech-available",
        tenant_id="tenant-1",
        technician_name="Available Tech",
        technician_skill="Plumbing",
        technician_location="0,0",
        technician_status="AVAILABLE",
        current_jobs=0,
        max_jobs=3,
    )

    db.add_all(
        [
            tech_busy,
            tech_offline,
            tech_available,
        ]
    )

    db.commit()

    # --------------------------------------------------------
    # 2. Create jobs
    # --------------------------------------------------------

    job1 = Job(
        tenant_id="tenant-1",
        customer_name="Customer 1",
        location="1,1",
        issue_description="Leaking pipe",
        priority="HIGH",
        service_type="Plumbing",
        required_skill="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now(
            timezone.utc
        ).date(),
        status="QUEUED",
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
        preferred_service_date=datetime.now(
            timezone.utc
        ).date(),
        status="QUEUED",
    )

    db.add_all(
        [
            job1,
            job2,
        ]
    )

    db.commit()

    db.refresh(job1)
    db.refresh(job2)

    headers = {
        "Authorization": f"Bearer {get_test_token()}",
        "X-Tenant-ID": "tenant-1",
    }

    # --------------------------------------------------------
    # Busy technician must fail
    # --------------------------------------------------------

    resp = client.post(
        f"/jobs/{job1.id}/assign",
        headers=headers,
        json={
            "tech_id": "tech-busy",
            "justification": (
                "Force test justification with length limit 20."
            ),
        },
    )

    assert resp.status_code == 400
    assert "unavailable" in resp.json()["detail"].lower()

    # --------------------------------------------------------
    # Offline technician must fail
    # --------------------------------------------------------

    resp = client.post(
        f"/jobs/{job1.id}/assign",
        headers=headers,
        json={
            "tech_id": "tech-offline",
            "justification": (
                "Force test justification with length limit 20."
            ),
        },
    )

    assert resp.status_code == 400
    assert "unavailable" in resp.json()["detail"].lower()

    # --------------------------------------------------------
    # Available technician must succeed
    # --------------------------------------------------------

    resp = client.post(
        f"/jobs/{job1.id}/assign",
        headers=headers,
        json={
            "tech_id": "tech-available",
            "justification": (
                "Force test justification with length limit 20."
            ),
        },
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "ASSIGNED"


# ============================================================
# Test: force assignment of busy/offline technician
# ============================================================

def test_force_assign_busy_offline_blocked(setup_db):

    db = setup_db

    tech_busy = Technician(
        tech_id="tech-busy",
        tenant_id="tenant-1",
        technician_name="Busy Tech",
        technician_skill="Plumbing",
        technician_location="0,0",
        technician_status="Busy",
        current_jobs=0,
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
        preferred_service_date=datetime.now(
            timezone.utc
        ).date(),
        status="ESCALATED",
    )

    db.add(job)
    db.commit()
    db.refresh(job)

    esc = SLAEscalation(
        tenant_id="tenant-1",
        job_id=job.id,
        status="ESCALATED",
        manager_notified_at=datetime.now(
            timezone.utc
        ),
    )

    db.add(esc)
    db.commit()

    headers = {
        "Authorization": f"Bearer {get_test_token()}",
        "X-Tenant-ID": "tenant-1",
    }

    resp = client.post(
        f"/escalations/{job.id}/force-assign",
        headers=headers,
        json={
            "tech_id": "tech-busy",
            "reason": "Expert tech needed immediately",
        },
    )

    assert resp.status_code == 400
    assert "unavailable" in resp.json()["detail"].lower()


# ============================================================
# Test: availability endpoint
# ============================================================

def test_availability_endpoint(setup_db):

    db = setup_db

    tech = Technician(
        tech_id="tech-test",
        technician_name="Test Tech",
        technician_skill="Plumbing",
        technician_location="0,0",
        technician_status="AVAILABLE",
        current_jobs=0,
        max_jobs=3,
        tenant_id="tenant-1",
    )

    db.add(tech)
    db.commit()
    db.refresh(tech)

    headers = {
        "Authorization": f"Bearer {get_test_token()}",
        "X-Tenant-ID": "tenant-1",
    }

    # --------------------------------------------------------
    # Update using string tech_id
    # --------------------------------------------------------

    resp = client.put(
        f"/technicians/{tech.tech_id}/availability",
        headers=headers,
        json={
            "technician_status": "Busy"
        },
    )

    assert resp.status_code == 200
    assert (
        resp.json()["technician"]["technician_status"]
        == "Busy"
    )

    # --------------------------------------------------------
    # Update using numeric technician_id
    # --------------------------------------------------------

    resp = client.put(
        f"/technicians/{tech.technician_id}/availability",
        headers=headers,
        json={
            "technician_status": "Offline"
        },
    )

    assert resp.status_code == 200
    assert (
        resp.json()["technician"]["technician_status"]
        == "Offline"
    )

    # --------------------------------------------------------
    # Invalid status
    # --------------------------------------------------------

    resp = client.put(
        f"/technicians/{tech.technician_id}/availability",
        headers=headers,
        json={
            "technician_status": "InvalidStatus"
        },
    )

    assert resp.status_code in [400, 422]