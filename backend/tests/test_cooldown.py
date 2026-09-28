import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
from fakeredis import FakeRedis
from contextlib import contextmanager

from app.main import app
from app.models import Job, Technician, AuditEvent, DispatcherNotification, OverrideAuditEvent
from app.database import Base, get_db
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from app.redis_client import get_redis_client
from app.services.cooldown_service import CooldownService
from app.services.exclusion_service import ExclusionService
from app.auth.dependencies import get_current_user, AuthenticatedUser
from app.auth.rbac import UserRole
from fastapi import HTTPException, Request
from app.auth.dependencies import (
    get_current_user,
    get_current_user_or_tenant,
    AuthenticatedUser,
)
from app.auth.rbac import UserRole

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

fake_redis = FakeRedis(decode_responses=True)

def override_get_redis():
    return fake_redis

async def override_get_current_user_or_tenant():
    return (
        AuthenticatedUser(
            user_id="test-user",
            tenant_id="tenant-1",
            role=UserRole.DISPATCHER,
            jti="test-jti",
        ),
        "tenant-1",
    )


@contextmanager
def dummy_job_lock(*args, **kwargs):
    yield "dummy_lock"

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    
    # Cleanup
    db.query(DispatcherNotification).delete()
    db.query(AuditEvent).delete()
    db.query(Job).delete()
    db.query(Technician).delete()
    db.commit()
    
    # Reset fake redis
    fake_redis.flushall()
    
    yield db
    db.close()

def override_get_current_user_or_tenant(request: Request):
    user = override_get_current_user(request)
    return user, user.tenant_id

def override_get_current_user(request: Request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()

    if token == "tech-123":
        return AuthenticatedUser(
            user_id="tech-123",
            tenant_id="tenant-1",
            role=UserRole.TECHNICIAN,
            jti="test-jti",
        )

    if token == "dispatcher":
        return AuthenticatedUser(
            user_id="dispatcher",
            tenant_id="tenant-1",
            role=UserRole.DISPATCHER,
            jti="test-jti",
        )

    if token == "admin":
        return AuthenticatedUser(
            user_id="admin",
            tenant_id="tenant-1",
            role=UserRole.SUPER_ADMIN,
            jti="test-jti",
        )

    raise HTTPException(
        status_code=401,
        detail="Invalid test token",
    )

@pytest.fixture(autouse=True)
def apply_overrides():
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis_client] = override_get_redis
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_current_user_or_tenant] = (
        override_get_current_user_or_tenant
    )

    yield

    app.dependency_overrides.clear()

@patch("app.routes.jobs.with_job_lock", side_effect=dummy_job_lock)
def test_cooldown_set_on_rejection(mock_lock, setup_db):
    db = setup_db
    tech = Technician(
        tech_id="tech-123", technician_name="John Doe", technician_skill="Plumbing",
        technician_location="0,0", technician_status="BUSY", current_jobs=1,tenant_id="tenant-1"
    )
    db.add(tech)
    db.commit()
    db.refresh(tech)
    
    job = Job(
        customer_name="Alice", location="1,1", issue_description="Leak",
        priority="HIGH", service_type="Plumbing", contact_number="1234567890",
        preferred_service_date=datetime.now().date(), status="ASSIGNED",
        assigned_technician_id=tech.technician_id,tenant_id="tenant-1"
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    
    reason_text = "Customer is way too far away from me"
    response = client.post(
        f"/jobs/{job.id}/reject",
        headers={"Authorization": "Bearer tech-123", "X-Tenant-ID": "tenant-1"},
        json={"reason": reason_text}
    )
    
    assert response.status_code == 200, response.text
    
    # Verify Cooldown Service
    cooldown = CooldownService.check_cooldown(fake_redis, str(job.id), "tech-123")
    assert cooldown is not None
    assert cooldown["remaining_seconds"] <= 120
    assert cooldown["remaining_seconds"] > 115 # Roughly 120

def test_technician_excluded_during_cooldown(setup_db):
    job_id = "job-2"
    tech_id = "tech-2"
    
    # Manually set cooldown
    CooldownService.set_cooldown(fake_redis, job_id, tech_id, 120)
    
    # Check exclusion
    exclusion = ExclusionService.is_excluded(fake_redis, job_id, tech_id)
    assert exclusion["excluded"] is True
    assert exclusion["reason"] == "cooldown_active"

def test_cooldown_checked_in_planning(setup_db):
    db = setup_db
    tech = Technician(
        tech_id="tech-123", technician_name="John Doe", technician_skill="Plumbing",
        technician_location="0,0", technician_status="AVAILABLE", current_jobs=0,tenant_id="tenant-1"
    )
    db.add(tech)
    
    job = Job(
        customer_name="Alice", location="1,1", issue_description="Leak",
        priority="HIGH", service_type="Plumbing", contact_number="1234567890",
        preferred_service_date=datetime.now().date(), status="QUEUED",tenant_id="tenant-1"
    )
    db.add(job)
    db.commit()
    db.refresh(tech)
    db.refresh(job)
    
    # Manually set cooldown
    CooldownService.set_cooldown(fake_redis, str(job.id), tech.tech_id, 120)
    
    # Call planning
    response = client.post(
        f"/jobs/{job.id}/plan",
        headers={"Authorization": "Bearer dispatcher", "X-Tenant-ID": "tenant-1"}
    )
    assert response.status_code == 200, response.text
    data = response.json()
    
    assert len(data["disqualified_technicians"]) >= 1
    disqualified = [d for d in data["disqualified_technicians"] if d["tech_id"] == "tech-123"]
    assert len(disqualified) == 1
    assert disqualified[0]["reason"] == "cooldown_active"

def test_technician_available_after_120s(setup_db):
    db = setup_db
    tech = Technician(
        tech_id="tech-123", technician_name="John Doe", technician_skill="Plumbing",
        technician_location="13.0,80.0", technician_status="AVAILABLE", current_jobs=0,tenant_id="tenant-1"
    )
    db.add(tech)
    
    job = Job(
        customer_name="Alice", location="13.01,80.01", issue_description="Leak",
        priority="HIGH", service_type="Plumbing", contact_number="1234567890",
        preferred_service_date=datetime.now().date(), status="QUEUED",tenant_id="tenant-1"
    )
    db.add(job)
    db.commit()
    db.refresh(tech)
    db.refresh(job)
    
    # Freeze time and set cooldown
    initial_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    
    with patch("app.services.cooldown_service.datetime") as mock_dt, \
         patch("app.routes.jobs.datetime") as mock_jobs_dt:
         
        mock_dt.now.return_value = initial_time
        mock_dt.fromisoformat = datetime.fromisoformat
        mock_jobs_dt.now.return_value = initial_time
        mock_jobs_dt.fromisoformat = datetime.fromisoformat
        
        CooldownService.set_cooldown(fake_redis, str(job.id), tech.tech_id, 120)
        
        # Check exclusion while frozen
        exclusion = ExclusionService.is_excluded(fake_redis, str(job.id), tech.tech_id)
        assert exclusion["excluded"] is True
    
    # Advance time by 121 seconds
    future_time = initial_time + timedelta(seconds=121)
    
    with patch("app.services.cooldown_service.datetime") as mock_dt, \
         patch("app.routes.jobs.datetime") as mock_jobs_dt:
         
        mock_dt.now.return_value = future_time
        mock_dt.fromisoformat = datetime.fromisoformat
        mock_jobs_dt.now.return_value = future_time
        mock_jobs_dt.fromisoformat = datetime.fromisoformat
        
        # Simulate FakeRedis TTL expiration since it checks system time
        fake_redis.delete(f"job:cooldown:{job.id}:{tech.tech_id}")
        
        # Now the cooldown should be expired
        cooldown = CooldownService.check_cooldown(fake_redis, str(job.id), tech.tech_id)
        assert cooldown is None
        
        # Let's call planning
        response = client.post(
            f"/jobs/{job.id}/plan",
            headers={"Authorization": "Bearer dispatcher", "X-Tenant-ID": "tenant-1"}
        )
        assert response.status_code == 200, response.text
        data = response.json()
        
        disqualified = [d for d in data["disqualified_technicians"] if d["tech_id"] == "tech-123"]
        assert len(disqualified) == 0  # Should NOT be disqualified due to cooldown

@patch("app.routes.jobs.with_job_lock", side_effect=dummy_job_lock)
def test_manual_override_bypasses(mock_lock, setup_db):
    db = setup_db
    tech = Technician(
        tech_id="tech-123", technician_name="John Doe", technician_skill="Plumbing",
        technician_location="0,0", technician_status="AVAILABLE", current_jobs=0, tenant_id="tenant-1"
    )
    db.add(tech)
    
    job = Job(
        customer_name="Alice", location="1,1", issue_description="Leak",
        priority="HIGH", service_type="Plumbing", contact_number="1234567890",
        preferred_service_date=datetime.now().date(), status="QUEUED", tenant_id="tenant-1"
    )
    db.add(job)
    db.commit()
    db.refresh(tech)
    db.refresh(job)
    
    # Set cooldown
    CooldownService.set_cooldown(fake_redis, str(job.id), tech.tech_id, 120)
    
    # Direct assign via override
    response = client.post(
        f"/jobs/{job.id}/assign",
        headers={"Authorization": "Bearer admin", "X-Tenant-ID": "tenant-1", "X-Permissions": "dispatcher"},
        json={
            "tech_id": "tech-123",
            "justification": "Urgent P1 VIP customer who has been waiting for more than 4 hours for this job to be completed.",
            "skip_skill_check": False,
            "skip_workload_check": False
        }
    )
    
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "ASSIGNED"
    assert data["override"]["cooldown_bypassed"] is True
    
    db.refresh(job)
    assert job.assigned_technician_id == tech.technician_id

@patch("app.routes.jobs.with_job_lock", side_effect=dummy_job_lock)
def test_override_logged_to_audit(mock_lock, setup_db):
    db = setup_db
    tech = Technician(
        tech_id="tech-123", technician_name="John Doe", technician_skill="Plumbing",
        technician_location="0,0", technician_status="AVAILABLE", current_jobs=0, tenant_id="tenant-1"
    )
    db.add(tech)
    
    job = Job(
        customer_name="Alice", location="1,1", issue_description="Leak",
        priority="HIGH", service_type="Plumbing", contact_number="1234567890",
        preferred_service_date=datetime.now().date(), status="QUEUED", tenant_id="tenant-1"
    )
    db.add(job)
    db.commit()
    db.refresh(tech)
    db.refresh(job)
    
    # Direct assign via override
    response = client.post(
        f"/jobs/{job.id}/assign",
        headers={"Authorization": "Bearer admin", "X-Tenant-ID": "tenant-1", "X-Permissions": "dispatcher"},
        json={
            "tech_id": "tech-123",
            "justification": "Urgent P1 VIP customer who has been waiting for more than 4 hours for this job to be completed.",
            "skip_skill_check": False,
            "skip_workload_check": False
        }
    )
    assert response.status_code == 200, response.text
    
    # Check Audit
    audit = db.query(OverrideAuditEvent).filter(OverrideAuditEvent.action == "force_assign").first()
    assert audit is not None
    assert audit.justification == "Urgent P1 VIP customer who has been waiting for more than 4 hours for this job to be completed."
    assert "force_assign bypassing PlanningAgent" in audit.reason
