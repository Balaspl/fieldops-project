import pytest
from fastapi.testclient import TestClient
from fastapi import Response
from fastapi import HTTPException
from datetime import datetime, date, timezone, timedelta
from types import SimpleNamespace


from app.main import app
from app.models import Job, Technician
from app.database import Base, get_db
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from app.routes.jobs import update_job
from app.schemas import JobCreate
from app.auth.dependencies import (
    AuthenticatedUser,
    get_current_user,
    get_current_user_or_tenant,
)
from fastapi import Request
from unittest.mock import AsyncMock
from app.routes.jobs import get_job_status_history
from app.models import AuditEvent
import app.services.re_dispatch_queue as re_dispatch_queue
from app.auth.dependencies import get_current_user_or_tenant
from app.routes.jobs import assign_job, JobAssignRequest
from app.auth.rbac import UserRole

import asyncio

from app.routes.jobs import close_job_endpoint
from app.schemas import JobClosureCreate
from app.auth.dependencies import require_permission

# ---------------------------------------------------------------------------
# Test database setup
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()

    db.query(Job).delete()
    db.query(Technician).delete()
    db.commit()

    # Seed technician
    tech = Technician(
        technician_id=1,
        tech_id="tech-1",
        technician_name="Alice Smith",
        technician_skill="HVAC Repair",
        technician_location="North Zone",
        technician_status="Available",
        current_jobs=0,
        max_jobs=5,
        tenant_id="tenant-1",
    )

    db.add(tech)
    db.commit()

    now = datetime.now(timezone.utc)

    # Seed jobs
    jobs = [
        Job(
            id=101,
            tenant_id="tenant-1",
            customer_name="John Doe",
            status="active",
            priority="CRITICAL",
            service_type="HVAC Repair",
            location="North Zone",
            issue_description="AC not cooling",
            contact_number="9876543210",
            preferred_service_date=now,
            assigned_technician_id=None,
            sla_deadline=now + timedelta(minutes=30),
        ),
        Job(
            id=102,
            tenant_id="tenant-1",
            customer_name="Jane Smith",
            status="in progress",
            priority="HIGH",
            service_type="Electrical Service",
            location="South Zone",
            issue_description="Fuse blown",
            contact_number="9876543211",
            preferred_service_date=now,
            assigned_technician_id=1,
            sla_deadline=now + timedelta(minutes=10),
        ),

        Job(
            id=103,
            tenant_id="tenant-1",
            customer_name="Bob Johnson",
            status="completed",
            priority="MEDIUM",
            service_type="Plumbing Service",
            location="East Zone",
            issue_description="Leak in pipe",
            contact_number="9876543212",
            preferred_service_date=now,
            assigned_technician_id=None,
            sla_deadline=now - timedelta(minutes=10),
        ),
        Job(
            id=104,
            tenant_id="tenant-1",
            customer_name="Dave Adams",
            status="cancelled",
            priority="LOW",
            service_type="Network Support",
            location="West Zone",
            issue_description="WiFi offline",
            contact_number="9876543213",
            preferred_service_date=now,
            assigned_technician_id=None,
        ),
    ]

    for job in jobs:
        db.add(job)

    db.commit()

    yield db

    db.close()


@pytest.fixture(autouse=True)
def apply_overrides():
    app.dependency_overrides[get_db] = override_get_db

    test_user = AuthenticatedUser(
        user_id="test-user",
        tenant_id="tenant-1",
        role=UserRole.DISPATCHER,
        jti="test-jti",
        session_id="test-session",
    )

    def override_current_user():
        return test_user

    def override_current_user_or_tenant():
        return (
            AuthenticatedUser(
                user_id="test-user",
                tenant_id="tenant-1",
                role="DISPATCHER",
                jti="test-jti",
                session_id="test-session",
            ),
            "tenant-1",
        )

    app.dependency_overrides[
        get_current_user
    ] = override_current_user

    app.dependency_overrides[
        get_current_user_or_tenant
    ] = override_current_user_or_tenant

    yield

    app.dependency_overrides.pop(get_db, None)

    app.dependency_overrides.pop(
        get_current_user,
        None,
    )

    app.dependency_overrides.pop(
        get_current_user_or_tenant,
        None,
    )


# ---------------------------------------------------------------------------
# Basic jobs endpoint
# ---------------------------------------------------------------------------

def test_get_jobs_no_filters():
    response = client.get("/jobs/")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 4


def test_get_jobs_all_filters():
    response = client.get(
        "/jobs/?status=ALL&priority=ALL&service_type=ALL&sla=ALL"
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 4


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def test_get_jobs_filter_search():
    # Customer name
    response = client.get("/jobs/?search=Smith")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["customer_name"] == "Jane Smith"

    # Location
    response = client.get("/jobs/?search=South")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["customer_name"] == "Jane Smith"

    # Issue description
    response = client.get("/jobs/?search=AC")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["customer_name"] == "John Doe"


# ---------------------------------------------------------------------------
# Status filters
# ---------------------------------------------------------------------------

def test_get_jobs_filter_status():
    # Normal status -> else branch
    response = client.get("/jobs/?status=active")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["customer_name"] == "John Doe"

    # inprogress branch
    response = client.get("/jobs/?status=in progress")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["customer_name"] == "Jane Smith"

    # cancelled branch
    response = client.get("/jobs/?status=cancelled")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["customer_name"] == "Dave Adams"

    # canceled branch
    response = client.get("/jobs/?status=canceled")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["customer_name"] == "Dave Adams"

    # Unknown status -> normal else branch
    response = client.get("/jobs/?status=unknown-status")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 0

    # ALL -> outer condition false
    response = client.get("/jobs/?status=ALL")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 4


# ---------------------------------------------------------------------------
# Priority filters
# ---------------------------------------------------------------------------

def test_get_jobs_filter_priority():
    # CRITICAL branch
    response = client.get("/jobs/?priority=CRITICAL")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["customer_name"] == "John Doe"

    # HIGH branch
    response = client.get("/jobs/?priority=HIGH")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["customer_name"] == "Jane Smith"

    # MEDIUM branch
    response = client.get("/jobs/?priority=MEDIUM")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["customer_name"] == "Bob Johnson"

    # LOW branch
    response = client.get("/jobs/?priority=LOW")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["customer_name"] == "Dave Adams"

    # Generic priority branch
    response = client.get("/jobs/?priority=URGENT")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 0

    # ALL -> outer condition false
    response = client.get("/jobs/?priority=ALL")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 4


# ---------------------------------------------------------------------------
# Service type filters
# ---------------------------------------------------------------------------

def test_get_jobs_filter_service_type():
    # Normal service type
    response = client.get("/jobs/?service_type=HVAC Repair")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["customer_name"] == "John Doe"

    # Underscore conversion
    response = client.get("/jobs/?service_type=Electrical_Service")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["customer_name"] == "Jane Smith"

    # ALL -> outer condition false
    response = client.get("/jobs/?service_type=ALL")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 4


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

def test_get_jobs_pagination():
    response = client.get("/jobs/?page=1&limit=2")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 2
    assert response.headers["X-Total-Count"] == "4"

def test_update_job_success_with_required_skill():
    """
    Covers the normal update_job() path where required_skill is supplied.
    """

    db = TestingSessionLocal()

    try:
        current_user = AuthenticatedUser(
            user_id ="test-user",
            tenant_id="tenant-1",
            role="DISPATCHER",
            jti="test-jti",
            session_id="test-session",
        )

        job_data = JobCreate(
            customer_name="Updated Customer",
            location="Updated Location",
            issue_description="Updated issue",
            priority="HIGH",
            service_type="HVAC Repair",
            contact_number="9999999999",
            preferred_service_date=date.today(),
            status="ACTIVE",
            required_skill="HVAC Repair",
            sla_deadline=datetime.now(timezone.utc) + timedelta(minutes=60),
            attempt_count=3,
        )

        result = update_job(
            job_id=101,
            job=job_data,
            current_user=current_user,
            db=db,
        )

        assert result.id == 101
        assert result.customer_name == "Updated Customer"
        assert result.location == "Updated Location"
        assert result.issue_description == "Updated issue"
        assert result.priority == "HIGH"
        assert result.service_type == "HVAC Repair"
        assert result.contact_number == "9999999999"
        assert result.status == "ACTIVE"
        assert result.required_skill == "HVAC Repair"
        assert result.attempt_count == 3
        assert result.tenant_id == "tenant-1"

    finally:
        db.close()

def test_plan_job_not_found():
    from app.routes.jobs import plan_job_assignment

    db = TestingSessionLocal()

    try:
        current_user = AuthenticatedUser(
            user_id="test-user",
            tenant_id="tenant-1",
            role="DISPATCHER",
            jti="test-jti",
            session_id="test-session",
        )

        class FakeRedis:
            pass

        request = Request(
            scope={
                "type": "http",
                "method": "POST",
                "path": "/jobs/999999/plan",
                "headers": [],
            }
        )

        with pytest.raises(HTTPException) as exc_info:
            

            asyncio.run(
                plan_job_assignment(
                    job_id=999999,
                    request=request,
                    admin_override=False,
                    current_user=current_user,
                    db=db,
                    redis_client=FakeRedis(),
                )
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Job not found"

    finally:
        db.close()


def test_plan_job_invalid_status():
    from app.routes.jobs import plan_job_assignment

    db = TestingSessionLocal()

    try:
        job = db.query(Job).filter(Job.id == 101).first()
        assert job is not None

        job.status = "COMPLETED"
        db.commit()

        current_user = AuthenticatedUser(
            user_id="test-user",
            tenant_id="tenant-1",
            role="DISPATCHER",
            jti="test-jti",
            session_id="test-session",
        )

        request = Request(
            scope={
                "type": "http",
                "method": "POST",
                "path": "/jobs/101/plan",
                "headers": [],
            }
        )

        with pytest.raises(HTTPException) as exc_info:
            

            asyncio.run(
                plan_job_assignment(
                    job_id=101,
                    request=request,
                    admin_override=False,
                    current_user=current_user,
                    db=db,
                    redis_client=None,
                )
            )

        assert exc_info.value.status_code == 400
        assert "QUEUED or ACTIVE" in exc_info.value.detail

    finally:
        db.close()

def test_plan_job_redis_rate_limit_none():
    """
    Covers req_count is None -> skip the inner rate-limit checks.
    """
    from app.routes.jobs import plan_job_assignment

    db = TestingSessionLocal()

    try:
        current_user = AuthenticatedUser(
            user_id="test-user",
            tenant_id="tenant-1",
            role="DISPATCHER",
            jti="test-jti",
            session_id="test-session",
        )

        class FakeRedis:
            def incr(self, key):
                return None

            def get(self, key):
                return None

            def exists(self, *args, **kwargs):
                return False

        request = Request(
            scope={
                "type": "http",
                "method": "POST",
                "path": "/jobs/101/plan",
                "headers": [],
            }
        )

        # Remove technicians so execution stops after the Redis section.
        db.query(Technician).delete()
        db.commit()

        

        result = asyncio.run(
            plan_job_assignment(
                job_id=101,
                request=request,
                admin_override=False,
                current_user=current_user,
                db=db,
                redis_client=FakeRedis(),
            )
        )

        assert result.job_id == "101"
        assert result.ranked_technicians == []

    finally:
        db.close()


def test_plan_job_rate_limit_exceeded():
    """
    Covers req_count > 10 -> HTTP 429.
    """
    from app.routes.jobs import plan_job_assignment

    db = TestingSessionLocal()

    try:
        current_user = AuthenticatedUser(
            user_id="test-user",
            tenant_id="tenant-1",
            role="DISPATCHER",
            jti="test-jti",
            session_id="test-session",
        )

        class FakeRedis:
            def incr(self, key):
                return 11

            def get(self, key):
                return None
            
            def exists(self, *args, **kwargs):
                return False

        request = Request(
            scope={
                "type": "http",
                "method": "POST",
                "path": "/jobs/101/plan",
                "headers": [],
            }
        )

        

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                plan_job_assignment(
                    job_id=101,
                    request=request,
                    admin_override=False,
                    current_user=current_user,
                    db=db,
                    redis_client=FakeRedis(),
                )
            )

        assert exc_info.value.status_code == 429
        assert exc_info.value.detail == "Rate limit exceeded"

    finally:
        db.close()


def test_plan_job_cache_hit():
    """
    Covers cached_data truthy -> JSON cache response.
    """
    from app.routes.jobs import plan_job_assignment
    import json

    db = TestingSessionLocal()

    try:
        current_user = AuthenticatedUser(
            user_id="test-user",
            tenant_id="tenant-1",
            role="DISPATCHER",
            jti="test-jti",
            session_id="test-session",
        )

        cached_plan = {
            "job_id": "101",
            "job_title": "HVAC Repair - North Zone",
            "status": "ACTIVE",
            "ranked_technicians": [],
            "disqualified_technicians": [],
            "scoring_weights": {
                "proximity": 0.4,
                "skill": 0.4,
                "workload": 0.2,
            },
            "generated_at": "2026-01-01T00:00:00Z",
            "cache_ttl_seconds": 30,
        }

        class FakeRedis:
            def incr(self, key):
                return 2

            def get(self, key):
                return json.dumps(cached_plan)

            def setex(self, key, ttl, value):
                return True

            def exists(self, *args, **kwargs):
                return False

        request = Request(
            scope={
                "type": "http",
                "method": "POST",
                "path": "/jobs/101/plan",
                "headers": [],
            }
        )

        

        result = asyncio.run(
            plan_job_assignment(
                job_id=101,
                request=request,
                admin_override=False,
                current_user=current_user,
                db=db,
                redis_client=FakeRedis(),
            )
        )

        assert result == cached_plan

    finally:
        db.close()

def test_plan_job_no_available_technicians(monkeypatch):
    from app.routes.jobs import plan_job_assignment

    db = TestingSessionLocal()

    try:
        db.query(Technician).delete()
        db.commit()

        current_user = AuthenticatedUser(
            user_id="test-user",
            tenant_id="tenant-1",
            role="DISPATCHER",
            jti="test-jti",
            session_id="test-session",
        )

        class FakeRedis:
            def incr(self, key):
                return 1

            def expire(self, key, seconds):
                return True

            def get(self, key):
                return None

            def exists(self, *args, **kwargs):
                return False

        request = Request(
            scope={
                "type": "http",
                "method": "POST",
                "path": "/jobs/101/plan",
                "headers": [],
            }
        )

        

        result = asyncio.run(
            plan_job_assignment(
                job_id=101,
                request=request,
                admin_override=False,
                current_user=current_user,
                db=db,
                redis_client=FakeRedis(),
            )
        )

        assert result.job_id == "101"
        assert result.ranked_technicians == []
        assert result.disqualified_technicians == []
        assert result.cache_ttl_seconds == 30

    finally:
        db.close()


def test_update_job_required_skill_fallback(monkeypatch):
    """
    Covers:

        if not req_skill or not req_skill.strip():
            req_skill = map_service_type_to_skill(job.service_type)
    """
   

    monkeypatch.setattr(
        "app.routes.jobs.map_service_type_to_skill",
        lambda service_type: "Mapped HVAC Skill",
    )

    db = TestingSessionLocal()

    try:
        current_user = AuthenticatedUser(
            user_id="test-user",
            tenant_id="tenant-1",
            role="DISPATCHER",
            jti="test-jti",
            session_id="test-session",
        )

        job_data = JobCreate(
            customer_name="Fallback Customer",
            location="Fallback Location",
            issue_description="Fallback issue",
            priority="MEDIUM",
            service_type="HVAC Repair",
            contact_number="8888888888",
            preferred_service_date=date.today(),
            status="ACTIVE",
            required_skill="",
            sla_deadline=datetime.now(timezone.utc) + timedelta(minutes=45),
            attempt_count=None,
        )

        result = update_job(
            job_id=101,
            job=job_data,
            current_user=current_user,
            db=db,
        )

        assert result.id == 101
        assert result.required_skill == "Mapped HVAC Skill"
        assert result.attempt_count == 0

    finally:
        db.close()

def test_plan_job_admin_override_success(monkeypatch):
    """
    Covers the admin_override path and the full successful technician flow.
    """
    from app.routes.jobs import plan_job_assignment

    db = TestingSessionLocal()

    try:
        current_user = AuthenticatedUser(
            user_id="test-user",
            tenant_id="tenant-1",
            role="DISPATCHER",
            jti="test-jti",
            session_id="test-session",
        )

        job = db.query(Job).filter(Job.id == 101).first()
        tech = db.query(Technician).filter(
            Technician.technician_id == 1
        ).first()

        assert job is not None
        assert tech is not None

        # Exercise coordinate parsing.
        job.location = "12.30,45.60"
        tech.technician_location = "10.10,20.20"
        db.commit()

        class FakeRedis:
            def incr(self, key):
                return 2

            def get(self, key):
                return None

            def setex(self, key, ttl, value):
                return True

            def exists(self, *args, **kwargs):
                return False

        monkeypatch.setattr(
            "app.routes.jobs.CooldownService.check_cooldown",
            lambda *args: False,
        )

        monkeypatch.setattr(
            "app.routes.jobs.ExclusionService.is_excluded",
            lambda *args: {"excluded": False},
        )

        monkeypatch.setattr(
            "app.routes.jobs.SkillScoringService.calculate_skill_score",
            lambda *args: {
                "qualified": True,
                "score": 0.9,
            },
        )

        monkeypatch.setattr(
            "app.routes.jobs.WorkloadScoringService.calculate_workload_score",
            lambda *args: {
                "score": 0.8,
                "active_jobs": 1,
            },
        )

        monkeypatch.setattr(
            "app.routes.jobs.DistanceScoringService.calculate_distance_score",
            AsyncMock(
                return_value=[
                    {
                        "score": 0.95,
                        "distance_km": 4.2,
                    }
                ]
            ),
        )

        monkeypatch.setattr(
            "app.routes.jobs.CompositeScoringService.get_weights",
            lambda *args: {
                "proximity": 0.4,
                "skill": 0.4,
                "workload": 0.2,
            },
        )

        monkeypatch.setattr(
            "app.routes.jobs.CompositeScoringService.composite_score",
            lambda *args: {
                "composite_score": 0.9,
                "breakdown": {
                    "proximity": 0.38,
                    "skill": 0.36,
                    "workload": 0.16,
                },
            },
        )

        monkeypatch.setattr(
            "app.routes.jobs.CompositeScoringService.rank_technicians",
            lambda self, qualified: qualified,
        )

        request = Request(
            scope={
                "type": "http",
                "method": "POST",
                "path": "/jobs/101/plan",
                "headers": [],
            }
        )

        

        result = asyncio.run(
            plan_job_assignment(
                job_id=101,
                request=request,
                admin_override=True,
                current_user=current_user,
                db=db,
                redis_client=FakeRedis(),
            )
        )

        assert result.job_id == "101"
        assert len(result.ranked_technicians) == 1
        assert result.ranked_technicians[0].tech_id == "tech-1"
        assert result.ranked_technicians[0].distance_km == 4.2
        assert result.ranked_technicians[0].is_top_3 is True
        assert result.ranked_technicians[0].is_recommended is True

    finally:
        db.close()

def test_plan_job_invalid_technician_location(monkeypatch):
    """
    Covers the ValueError path when technician location
    cannot be converted to float coordinates.
    """
    from app.routes.jobs import plan_job_assignment

    db = TestingSessionLocal()

    try:
        current_user = AuthenticatedUser(
            user_id="test-user",
            tenant_id="tenant-1",
            role="DISPATCHER",
            jti="test-jti",
            session_id="test-session",
        )

        tech = db.query(Technician).filter(
            Technician.technician_id == 1
        ).first()

        assert tech is not None

        tech.technician_location = "invalid,location"
        db.commit()

        class FakeRedis:
            def incr(self, key):
                return 2

            def get(self, key):
                return None

            def setex(self, key, ttl, value):
                return True

            def exists(self, *args, **kwargs):
                return False

        validator = type(
            "FakeValidator",
            (),
            {
                "validate_certifications": lambda self, job, tech, db: {
                    "qualified": True,
                },
                "log_disqualification": lambda self, *args: None,
            },
        )

        monkeypatch.setattr(
            "app.routes.jobs.CertificationValidator",
            validator,
        )

        monkeypatch.setattr(
            "app.routes.jobs.CooldownService.check_cooldown",
            lambda *args: False,
        )

        monkeypatch.setattr(
            "app.routes.jobs.ExclusionService.is_excluded",
            lambda *args: {"excluded": False},
        )

        monkeypatch.setattr(
            "app.routes.jobs.SkillScoringService.calculate_skill_score",
            lambda *args: {
                "qualified": True,
                "score": 0.9,
            },
        )

        monkeypatch.setattr(
            "app.routes.jobs.WorkloadScoringService.calculate_workload_score",
            lambda *args: {
                "score": 0.8,
                "active_jobs": 1,
            },
        )

        monkeypatch.setattr(
            "app.routes.jobs.DistanceScoringService.calculate_distance_score",
            AsyncMock(
                return_value=[]
            ),
        )

        request = Request(
            scope={
                "type": "http",
                "method": "POST",
                "path": "/jobs/101/plan",
                "headers": [],
            }
        )

        

        result = asyncio.run(
            plan_job_assignment(
                job_id=101,
                request=request,
                admin_override=False,
                current_user=current_user,
                db=db,
                redis_client=FakeRedis(),
            )
        )

        assert len(result.ranked_technicians) == 1
        assert result.ranked_technicians[0].tech_id == "tech-1"
        assert result.ranked_technicians[0].distance_km is None

    finally:
        db.close()


def test_plan_job_technician_location_without_coordinates(monkeypatch):
    """
    Covers the false branch of:
        if "," in tech.technician_location
    """
    from app.routes.jobs import plan_job_assignment

    db = TestingSessionLocal()

    try:
        current_user = AuthenticatedUser(
            user_id="test-user",
            tenant_id="tenant-1",
            role="DISPATCHER",
            jti="test-jti",
            session_id="test-session",
        )

        tech = db.query(Technician).filter(
            Technician.technician_id == 1
        ).first()

        assert tech is not None

        tech.technician_location = "North Zone"
        db.commit()

        class FakeRedis:
            def incr(self, key):
                return 2

            def get(self, key):
                return None

            def setex(self, key, ttl, value):
                return True

            def exists(self, *args, **kwargs):
                return False

        validator = type(
            "FakeValidator",
            (),
            {
                "validate_certifications": lambda self, job, tech, db: {
                    "qualified": True,
                },
                "log_disqualification": lambda self, *args: None,
            },
        )

        monkeypatch.setattr(
            "app.routes.jobs.CertificationValidator",
            validator,
        )

        monkeypatch.setattr(
            "app.routes.jobs.CooldownService.check_cooldown",
            lambda *args: False,
        )

        monkeypatch.setattr(
            "app.routes.jobs.ExclusionService.is_excluded",
            lambda *args: {"excluded": False},
        )

        monkeypatch.setattr(
            "app.routes.jobs.SkillScoringService.calculate_skill_score",
            lambda *args: {
                "qualified": True,
                "score": 0.9,
            },
        )

        monkeypatch.setattr(
            "app.routes.jobs.WorkloadScoringService.calculate_workload_score",
            lambda *args: {
                "score": 0.8,
                "active_jobs": 1,
            },
        )

        monkeypatch.setattr(
            "app.routes.jobs.DistanceScoringService.calculate_distance_score",
            AsyncMock(return_value=[]),
        )

        request = Request(
            scope={
                "type": "http",
                "method": "POST",
                "path": "/jobs/101/plan",
                "headers": [],
            }
        )

        

        result = asyncio.run(
            plan_job_assignment(
                job_id=101,
                request=request,
                admin_override=False,
                current_user=current_user,
                db=db,
                redis_client=FakeRedis(),
            )
        )

        assert len(result.ranked_technicians) == 1
        assert result.ranked_technicians[0].tech_id == "tech-1"
        assert result.ranked_technicians[0].distance_km is None

    finally:
        db.close()


def test_plan_job_certification_disqualified(monkeypatch):
    """
    Covers the certification-disqualified branch and continue.
    """
    from app.routes.jobs import plan_job_assignment

    db = TestingSessionLocal()

    try:
        current_user = AuthenticatedUser(
            user_id="test-user",
            tenant_id="tenant-1",
            role="DISPATCHER",
            jti="test-jti",
            session_id="test-session",
        )

        class FakeRedis:
            def incr(self, key):
                return 2

            def get(self, key):
                return None

            def setex(self, key, ttl, value):
                return True

            def exists(self, *args, **kwargs):
                return False

        validator = type(
            "FakeValidator",
            (),
            {
                "validate_certifications": lambda self, job, tech, db: {
                    "qualified": False,
                    "reason": "Missing certification",
                    "details": ["Required HVAC certificate"],
                    "message": "Technician certification invalid",
                },
                "log_disqualification": lambda self, *args: None,
            },
        )

        monkeypatch.setattr(
            "app.routes.jobs.CertificationValidator",
            validator,
        )

        request = Request(
            scope={
                "type": "http",
                "method": "POST",
                "path": "/jobs/101/plan",
                "headers": [],
            }
        )

        

        result = asyncio.run(
            plan_job_assignment(
                job_id=101,
                request=request,
                admin_override=False,
                current_user=current_user,
                db=db,
                redis_client=FakeRedis(),
            )
        )

        assert result.job_id == "101"
        assert len(result.ranked_technicians) == 0
        assert len(result.disqualified_technicians) == 1

        disqualified = result.disqualified_technicians[0]

        assert disqualified.tech_id == "tech-1"
        assert disqualified.name == "Alice Smith"
        assert disqualified.reason == "Missing certification"

    finally:
        db.close()


def test_plan_job_cooldown_disqualified(monkeypatch):
    """
    Covers the cooldown-active branch.
    """
    from app.routes.jobs import plan_job_assignment

    db = TestingSessionLocal()

    try:
        current_user = AuthenticatedUser(
            user_id="test-user",
            tenant_id="tenant-1",
            role="DISPATCHER",
            jti="test-jti",
            session_id="test-session",
        )

        class FakeRedis:
            def incr(self, key):
                return 2

            def get(self, key):
                return None

            def setex(self, key, ttl, value):
                return True
            def exists(self, *args, **kwargs):
                return False

        # Certification must pass so execution reaches cooldown.
        validator = type(
            "FakeValidator",
            (),
            {
                "validate_certifications": lambda self, job, tech, db: {
                    "qualified": True,
                },
                "log_disqualification": lambda self, *args: None,
            },
        )

        monkeypatch.setattr(
            "app.routes.jobs.CertificationValidator",
            validator,
        )

        monkeypatch.setattr(
            "app.routes.jobs.CooldownService.check_cooldown",
            lambda *args: True,
        )

        request = Request(
            scope={
                "type": "http",
                "method": "POST",
                "path": "/jobs/101/plan",
                "headers": [],
            }
        )

        

        result = asyncio.run(
            plan_job_assignment(
                job_id=101,
                request=request,
                admin_override=False,
                current_user=current_user,
                db=db,
                redis_client=FakeRedis(),
            )
        )

        assert result.job_id == "101"
        assert len(result.ranked_technicians) == 0
        assert len(result.disqualified_technicians) == 1

        disqualified = result.disqualified_technicians[0]

        assert disqualified.tech_id == "tech-1"
        assert disqualified.reason == "cooldown_active"
        assert disqualified.message == "Technician is in cooldown period"

    finally:
        db.close()

def test_plan_job_certification_warnings(monkeypatch):
    """
    Covers cert_res.get("warnings") == True.
    """
    from app.routes.jobs import plan_job_assignment

    db = TestingSessionLocal()

    try:
        current_user = AuthenticatedUser(
            user_id="test-user",
            tenant_id="tenant-1",
            role="DISPATCHER",
            jti="test-jti",
            session_id="test-session",
        )

        class FakeRedis:
            def incr(self, key):
                return 2

            def get(self, key):
                return None

            def setex(self, key, ttl, value):
                return True

            def exists(self, *args, **kwargs):
                return False

        validator = type(
            "FakeValidator",
            (),
            {
                "validate_certifications": lambda self, job, tech, db: {
                    "qualified": True,
                    "warnings": ["Certification expires soon"],
                },
                "log_disqualification": lambda self, *args: None,
            },
        )

        monkeypatch.setattr(
            "app.routes.jobs.CertificationValidator",
            validator,
        )

        monkeypatch.setattr(
            "app.routes.jobs.CooldownService.check_cooldown",
            lambda *args: True,
        )

        request = Request(
            scope={
                "type": "http",
                "method": "POST",
                "path": "/jobs/101/plan",
                "headers": [],
            }
        )

        

        result = asyncio.run(
            plan_job_assignment(
                job_id=101,
                request=request,
                admin_override=False,
                current_user=current_user,
                db=db,
                redis_client=FakeRedis(),
            )
        )

        assert len(result.disqualified_technicians) == 1
        assert result.disqualified_technicians[0].reason == "cooldown_active"

    finally:
        db.close()


def test_plan_job_exclusion_disqualified(monkeypatch):
    """
    Covers ExclusionService.is_excluded() returning excluded=True.
    """
    from app.routes.jobs import plan_job_assignment

    db = TestingSessionLocal()

    try:
        current_user = AuthenticatedUser(
            user_id="test-user",
            tenant_id="tenant-1",
            role="DISPATCHER",
            jti="test-jti",
            session_id="test-session",
        )

        class FakeRedis:
            def incr(self, key):
                return 2

            def get(self, key):
                return None
            def setex(self, key, ttl, value):
                return True
            def exists(self, *args, **kwargs):
                return False

        validator = type(
            "FakeValidator",
            (),
            {
                "validate_certifications": lambda self, job, tech, db: {
                    "qualified": True,
                },
                "log_disqualification": lambda self, *args: None,
            },
        )

        monkeypatch.setattr(
            "app.routes.jobs.CertificationValidator",
            validator,
        )

        monkeypatch.setattr(
            "app.routes.jobs.CooldownService.check_cooldown",
            lambda *args: False,
        )

        monkeypatch.setattr(
            "app.routes.jobs.ExclusionService.is_excluded",
            lambda *args: {
                "excluded": True,
                "reason": "customer_requested_exclusion",
            },
        )

        request = Request(
            scope={
                "type": "http",
                "method": "POST",
                "path": "/jobs/101/plan",
                "headers": [],
            }
        )

        

        result = asyncio.run(
            plan_job_assignment(
                job_id=101,
                request=request,
                admin_override=False,
                current_user=current_user,
                db=db,
                redis_client=FakeRedis(),
            )
        )

        assert len(result.ranked_technicians) == 0
        assert len(result.disqualified_technicians) == 1

        item = result.disqualified_technicians[0]

        assert item.tech_id == "tech-1"
        assert item.name == "Alice Smith"
        assert item.reason == "customer_requested_exclusion"
        assert item.message == "Technician is excluded"

    finally:
        db.close()


def test_plan_job_missing_prerequisite(monkeypatch):
    """
    Covers skill scoring returning qualified=False.
    """
    from app.routes.jobs import plan_job_assignment

    db = TestingSessionLocal()

    try:
        current_user = AuthenticatedUser(
            user_id="test-user",
            tenant_id="tenant-1",
            role="DISPATCHER",
            jti="test-jti",
            session_id="test-session",
        )

        class FakeRedis:
            def incr(self, key):
                return 2

            def get(self, key):
                return None
            def setex(self, key, ttl, value):
                return True
            def exists(self, *args, **kwargs):
                return False

        validator = type(
            "FakeValidator",
            (),
            {
                "validate_certifications": lambda self, job, tech, db: {
                    "qualified": True,
                },
                "log_disqualification": lambda self, *args: None,
            },
        )

        monkeypatch.setattr(
            "app.routes.jobs.CertificationValidator",
            validator,
        )

        monkeypatch.setattr(
            "app.routes.jobs.CooldownService.check_cooldown",
            lambda *args: False,
        )

        monkeypatch.setattr(
            "app.routes.jobs.ExclusionService.is_excluded",
            lambda *args: {"excluded": False},
        )

        monkeypatch.setattr(
            "app.routes.jobs.SkillScoringService.calculate_skill_score",
            lambda *args: {
                "qualified": False,
                "reason": "Required skill not found",
            },
        )

        request = Request(
            scope={
                "type": "http",
                "method": "POST",
                "path": "/jobs/101/plan",
                "headers": [],
            }
        )

        

        result = asyncio.run(
            plan_job_assignment(
                job_id=101,
                request=request,
                admin_override=False,
                current_user=current_user,
                db=db,
                redis_client=FakeRedis(),
            )
        )

        assert len(result.ranked_technicians) == 0
        assert len(result.disqualified_technicians) == 1

        item = result.disqualified_technicians[0]

        assert item.tech_id == "tech-1"
        assert item.name == "Alice Smith"
        assert item.reason == "missing_prerequisite"
        assert item.message == "Required skill not found"

    finally:
        db.close()


def test_plan_job_max_capacity_disqualified(monkeypatch):
    """
    Covers workload scoring returning score=0.0 with active_jobs >= 3.
    """
    from app.routes.jobs import plan_job_assignment

    db = TestingSessionLocal()

    try:
        current_user = AuthenticatedUser(
            user_id="test-user",
            tenant_id="tenant-1",
            role="DISPATCHER",
            jti="test-jti",
            session_id="test-session",
        )

        class FakeRedis:
            def incr(self, key):
                return 2

            def get(self, key):
                return None

            def setex(self, key, ttl, value):
                return True

            def exists(self, *args, **kwargs):
                return False

        validator = type(
            "FakeValidator",
            (),
            {
                "validate_certifications": lambda self, job, tech, db: {
                    "qualified": True,
                },
                "log_disqualification": lambda self, *args: None,
            },
        )

        monkeypatch.setattr(
            "app.routes.jobs.CertificationValidator",
            validator,
        )

        monkeypatch.setattr(
            "app.routes.jobs.CooldownService.check_cooldown",
            lambda *args: False,
        )

        monkeypatch.setattr(
            "app.routes.jobs.ExclusionService.is_excluded",
            lambda *args: {"excluded": False},
        )

        monkeypatch.setattr(
            "app.routes.jobs.SkillScoringService.calculate_skill_score",
            lambda *args: {
                "qualified": True,
                "score": 0.9,
            },
        )

        monkeypatch.setattr(
            "app.routes.jobs.WorkloadScoringService.calculate_workload_score",
            lambda *args: {
                "score": 0.0,
                "active_jobs": 3,
            },
        )

        request = Request(
            scope={
                "type": "http",
                "method": "POST",
                "path": "/jobs/101/plan",
                "headers": [],
            }
        )

        

        result = asyncio.run(
            plan_job_assignment(
                job_id=101,
                request=request,
                admin_override=False,
                current_user=current_user,
                db=db,
                redis_client=FakeRedis(),
            )
        )

        assert len(result.ranked_technicians) == 0
        assert len(result.disqualified_technicians) == 1

        item = result.disqualified_technicians[0]

        assert item.tech_id == "tech-1"
        assert item.name == "Alice Smith"
        assert item.reason == "max_capacity_reached"
        assert item.message == (
            "Technician has reached maximum active jobs (3/3)"
        )

    finally:
        db.close()


def test_update_job_required_skill_whitespace_fallback(monkeypatch):
    """
    Covers the .strip() side of the required_skill condition.
    """


    monkeypatch.setattr(
        "app.routes.jobs.map_service_type_to_skill",
        lambda service_type: "Mapped Electrical Skill",
    )

    db = TestingSessionLocal()

    try:
        current_user = AuthenticatedUser(
            user_id="test-user",
            tenant_id="tenant-1",
            role="DISPATCHER",
            jti="test-jti",
            session_id="test-session",
        )

        job_data = JobCreate(
            customer_name="Whitespace Customer",
            location="Whitespace Location",
            issue_description="Whitespace issue",
            priority="LOW",
            service_type="Electrical Service",
            contact_number="7777777777",
            preferred_service_date=date.today(),
            status="ACTIVE",
            required_skill="   ",
            sla_deadline=None,
            attempt_count=0,
        )

        result = update_job(
            job_id=101,
            job=job_data,
            current_user=current_user,
            db=db,
        )

        assert result.id == 101
        assert result.required_skill == "Mapped Electrical Skill"

    finally:
        db.close()


def test_update_job_not_found():
    """
    Covers:

        if not existing_job:
            raise HTTPException(404, ...)
    """

    db = TestingSessionLocal()

    try:
        current_user = AuthenticatedUser(
            user_id="test-user",
            tenant_id="tenant-1",
            role="DISPATCHER",
            jti="test-jti",
            session_id="test-session",
        )

        job_data = JobCreate(
            customer_name="Missing Customer",
            location="Missing Location",
            issue_description="Missing issue",
            priority="LOW",
            service_type="HVAC Repair",
            contact_number="6666666666",
            preferred_service_date=date.today(),
            status="ACTIVE",
            required_skill="HVAC Repair",
            sla_deadline=None,
            attempt_count=0,
        )

        with pytest.raises(HTTPException) as exc_info:
            update_job(
                job_id=999999,
                job=job_data,
                current_user=current_user,
                db=db,
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Job not found"

    finally:
        db.close()


def test_get_job_by_id_success():
    from app.routes.jobs import get_job_by_id

    db = TestingSessionLocal()

    try:
        current_user = AuthenticatedUser(
            user_id="test-user",
            tenant_id="tenant-1",
            role="DISPATCHER",
            jti="test-jti",
            session_id="test-session",
        )

        result = get_job_by_id(
            job_id=101,
            current_user=current_user,
            db=db,
        )

        assert result.id == 101
        assert result.customer_name == "John Doe"
        assert result.tenant_id == "tenant-1"

    finally:
        db.close()


def test_get_job_by_id_not_found():
    from app.routes.jobs import get_job_by_id

    db = TestingSessionLocal()

    try:
        current_user = AuthenticatedUser(
            user_id="test-user",
            tenant_id="tenant-1",
            role="DISPATCHER",
            jti="test-jti",
            session_id="test-session",
        )

        with pytest.raises(HTTPException) as exc_info:
            get_job_by_id(
                job_id=999999,
                current_user=current_user,
                db=db,
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Job not found"

    finally:
        db.close()

def test_get_redispatch_history_job_not_found():
    from app.routes.jobs import get_redispatch_history

    db = TestingSessionLocal()

    try:
        current_user = AuthenticatedUser(
            user_id="test-user",
            tenant_id="tenant-1",
            role="DISPATCHER",
            jti="test-jti",
            session_id="test-session",
        )

        with pytest.raises(HTTPException) as exc_info:
            get_redispatch_history(
                job_id=999999,
                current_user=current_user,
                db=db,
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Job not found"

    finally:
        db.close()


def test_get_redispatch_history_with_attempts():
    from app.routes.jobs import get_redispatch_history
    from app.models import DispatcherAlert

    db = TestingSessionLocal()

    try:
        current_user = AuthenticatedUser(
            user_id="test-user",
            tenant_id="tenant-1",
            role="DISPATCHER",
            jti="test-jti",
            session_id="test-session",
        )

        job = db.query(Job).filter(Job.id == 101).first()
        assert job is not None

        job.attempt_count = 1

        alert = DispatcherAlert(
            id="alert-test-1",
            tenant_id="tenant-1",
            type="REDISPATCH",
            severity="WARNING",
            job_id=101,
            attempt_count=1,
            max_attempts=3,
            excluded_technicians=[
                {
                    "name": "Alice Smith",
                    "reason": "Technician timeout",
                }
            ],
        )

        db.add(alert)
        db.commit()
        db.refresh(alert)

        result = get_redispatch_history(
            job_id=101,
            current_user=current_user,
            db=db,
        )

        assert len(result) == 1
        assert result[0]["job_id"] == 101
        assert result[0]["technician_name"] == "Alice Smith"
        assert result[0]["event_type"] == "timeout"
        assert result[0]["reason"] == "Technician timeout"

    finally:
        db.close()

def test_get_redispatch_history_generates_fallback_attempts():
    from app.routes.jobs import get_redispatch_history

    db = TestingSessionLocal()

    try:
        current_user = AuthenticatedUser(
            user_id="test-user",
            tenant_id="tenant-1",
            role="DISPATCHER",
            jti="test-jti",
            session_id="test-session",
        )

        job = db.query(Job).filter(Job.id == 101).first()
        assert job is not None

        # No DispatcherAlert records.
        # Force the endpoint to generate fallback attempts.
        job.attempt_count = 3
        db.commit()

        result = get_redispatch_history(
            job_id=101,
            current_user=current_user,
            db=db,
        )

        assert len(result) == 3

        assert result[0]["attempt_number"] == 3
        assert result[1]["attempt_number"] == 2
        assert result[2]["attempt_number"] == 1

        assert result[0]["event_type"] in {
            "rejection",
            "timeout",
            "offline",
        }

        assert all(
            item["job_id"] == 101
            for item in result
        )

    finally:
        db.close()

def test_get_override_history_not_found():
    from app.routes.jobs import get_override_history

    db = TestingSessionLocal()

    try:
        current_user = AuthenticatedUser(
            user_id="test-user",
            tenant_id="tenant-1",
            role="DISPATCHER",
            jti="test-jti",
            session_id="test-session",
        )

        with pytest.raises(HTTPException) as exc_info:
            get_override_history(
                job_id=999999,
                current_user=current_user,
                db=db,
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Job not found"

    finally:
        db.close()


def test_get_override_history_success():
    from app.routes.jobs import get_override_history
    from app.models import AssignmentOverride

    db = TestingSessionLocal()

    try:
        current_user = AuthenticatedUser(
            user_id="test-user",
            tenant_id="tenant-1",
            role="DISPATCHER",
            jti="test-jti",
            session_id="test-session",
        )

        override = AssignmentOverride(
            tenant_id="tenant-1",
            job_id=101,
            actor_name="test-user",
            actor_role="DISPATCHER",
            justification="Force assignment for coverage test",
            previous_technician_id=None,
            previous_technician_name="Unassigned",
            new_technician_id=1,
            new_technician_name="Alice Smith",
        )

        db.add(override)
        db.commit()

        result = get_override_history(
            job_id=101,
            current_user=current_user,
            db=db,
        )

        assert len(result) == 1
        assert result[0]["job_id"] == 101
        assert result[0]["actor_name"] == "test-user"
        assert result[0]["actor_role"] == "DISPATCHER"
        assert result[0]["justification"] == "Force assignment for coverage test"
        assert result[0]["previous_technician_name"] == "Unassigned"
        assert result[0]["new_technician_name"] == "Alice Smith"

    finally:
        db.close()

def test_get_job_status_history_not_found():
    from app.routes.jobs import get_job_status_history

    db = TestingSessionLocal()

    try:
        current_user = AuthenticatedUser(
            user_id="test-user",
            tenant_id="tenant-1",
            role="DISPATCHER",
            jti="test-jti",
            session_id="test-session",
        )

        with pytest.raises(HTTPException) as exc_info:
            get_job_status_history(
                job_id=999999,
                current_user=current_user,
                db=db,
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Job not found"

    finally:
        db.close()


def test_get_job_status_history_no_events():
    from app.routes.jobs import get_job_status_history

    db = TestingSessionLocal()

    try:
        current_user = AuthenticatedUser(
            user_id="test-user",
            tenant_id="tenant-1",
            role="DISPATCHER",
            jti="test-jti",
            session_id="test-session",
        )

        result = get_job_status_history(
            job_id=101,
            current_user=current_user,
            db=db,
        )

        assert len(result) == 1

        item = result[0]

        assert item["id"] == 0
        assert item["job_id"] == 101
        assert item["from_status"] is None
        assert item["to_status"] == "CREATED"
        assert item["changed_by_name"] == "System"
        assert item["changed_by_role"] == "SYSTEM"
        assert item["transition_reason"] == "Job initialized"
        assert item["duration_seconds"] is None
        assert item["sla_limit_seconds"] == 600

    finally:
        db.close()

def test_get_job_status_history_with_event(monkeypatch):
    

    db = TestingSessionLocal()

    try:
        current_user = AuthenticatedUser(
            user_id="test-user",
            tenant_id="tenant-1",
            role="DISPATCHER",
            jti="test-jti",
            session_id="test-session",
        )

        job = db.query(Job).filter(Job.id == 101).first()
        assert job is not None

        event = AuditEvent(
            id=1,
            job_id="101",
            tenant_id="tenant-1",
            event_type="job_status_transition",
            old_status="ACTIVE",
            new_status="EN_ROUTE",
            tech_id="system",
            actor_id="dispatcher_1",
            reason="Technician accepted job",
        )

        # Use an aware datetime directly on the Python object.
        event.created_at = datetime.now(timezone.utc) - timedelta(minutes=5)

        class FakeQuery:
            def filter(self, *args, **kwargs):
                return self

            def order_by(self, *args, **kwargs):
                return self

            def all(self):
                return [event]

            def first(self):
                return job

        class FakeDB:
            def query(self, model):
                if model is Job:
                    return FakeQuery()
                if model is AuditEvent:
                    return FakeQuery()
                return FakeQuery()

        result = get_job_status_history(
            job_id=101,
            current_user=current_user,
            db=FakeDB(),
        )

        assert len(result) == 1

        item = result[0]

        assert item["id"] == 1
        assert item["job_id"] == 101
        assert item["from_status"] == "ACTIVE"
        assert item["to_status"] == "EN_ROUTE"
        assert item["changed_by_name"] == "Dispatcher 1"
        assert item["changed_by_role"] == "Admin"
        assert item["transition_reason"] == "Technician accepted job"
        assert item["duration_seconds"] is not None
        assert item["sla_limit_seconds"] == 600

    finally:
        db.close()
                        

def test_get_job_status_history_with_technician_actor():
    from app.routes.jobs import get_job_status_history

    db = TestingSessionLocal()

    try:
        current_user = AuthenticatedUser(
            user_id="test-user",
            tenant_id="tenant-1",
            role="DISPATCHER",
            jti="test-jti",
            session_id="test-session",
        )

        job = db.query(Job).filter(Job.id == 101).first()
        tech = db.query(Technician).filter(
            Technician.technician_id == 1
        ).first()

        assert job is not None
        assert tech is not None

        tech.name = tech.technician_name

        class FakeEvent:
            id = 2
            job_id = "101"
            event_type = "job_status_transition"
            old_status = "ACTIVE"
            new_status = "ON_SITE"
            tech_id = 1
            actor_id = None
            reason = "Technician arrived"
            created_at = datetime.now(timezone.utc) - timedelta(minutes=2)

        event = FakeEvent()

        class FakeQuery:
            def __init__(self, result):
                self.result = result

            def filter(self, *args, **kwargs):
                return self

            def order_by(self, *args, **kwargs):
                return self

            def all(self):
                return self.result

            def first(self):
                return self.result

        class FakeDB:
            def query(self, model):
                if model is Job:
                    return FakeQuery(job)

                if model.__name__ == "AuditEvent":
                    return FakeQuery([event])

                if model.__name__ == "Technician":
                    return FakeQuery(tech)

                return FakeQuery(None)

        result = get_job_status_history(
            job_id=101,
            current_user=current_user,
            db=FakeDB(),
        )

        assert len(result) == 1
        assert result[0]["changed_by_name"] == tech.name
        assert result[0]["changed_by_role"] == "Technician"
        assert result[0]["to_status"] == "ON_SITE"
        assert result[0]["transition_reason"] == "Technician arrived"

    finally:
        db.close()


def test_get_jobs_page_without_limit():
    response = client.get("/jobs/?page=1")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 4


def test_get_jobs_limit_without_page():
    response = client.get("/jobs/?limit=2")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 4


def test_get_jobs_second_page():
    response = client.get("/jobs/?page=2&limit=2")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 2


# ---------------------------------------------------------------------------
# SLA filter
# ---------------------------------------------------------------------------

def test_get_jobs_filter_sla(monkeypatch):
    from app.routes.jobs import SLAService

    def mocked_get_sla_state(self, job_id):
        job_id = str(job_id)

        states = {
            "101": {
                "job_id": "101",
                "remaining_seconds": 1800,  # 30 min -> WITHIN_SLA
            },
            "102": {
                "job_id": "102",
                "remaining_seconds": 600,   # 10 min -> APPROACHING_BREACH
            },
            "103": {
                "job_id": "103",
                "remaining_seconds": -600,  # -10 min -> BREACHED
            },
            "104": None,                     # no SLA state
        }

        return states.get(job_id)

    monkeypatch.setattr(
        SLAService,
        "get_sla_state",
        mocked_get_sla_state,
    )

    # ---------------------------------------------------------
    # 1. No SLA filter
    # ---------------------------------------------------------
    response = client.get("/jobs/")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 4

    # ---------------------------------------------------------
    # 2. SLA = ALL
    # ---------------------------------------------------------
    response = client.get("/jobs/?sla=ALL")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 4

    # ---------------------------------------------------------
    # 3. Invalid SLA
    # ---------------------------------------------------------
    response = client.get("/jobs/?sla=INVALID")

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid SLA filter"

    # ---------------------------------------------------------
    # 4. WITHIN_SLA
    # Job 101 -> 1800 seconds
    # ---------------------------------------------------------
    response = client.get("/jobs/?sla=WITHIN_SLA")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["id"] == 101

    # ---------------------------------------------------------
    # 5. APPROACHING_BREACH
    # Job 102 -> 600 seconds
    # ---------------------------------------------------------
    response = client.get("/jobs/?sla=APPROACHING_BREACH")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["id"] == 102

    # ---------------------------------------------------------
    # 6. BREACHED
    # Job 103 -> -600 seconds but is COMPLETED.
    # Completed jobs must be excluded from SLA filters.
    # ---------------------------------------------------------
    def mocked_breached_state(self, job_id):
        if str(job_id) == "103":
            return {
                "job_id": "103",
                "remaining_seconds": -600,
            }

        return None


    monkeypatch.setattr(
        SLAService,
        "get_sla_state",
        mocked_breached_state,
    )

    response = client.get("/jobs/?sla=BREACHED")

    assert response.status_code == 200

    data = response.json()

    assert data == []

    # ---------------------------------------------------------
    # 7. Missing SLA state
    # Job 104 -> None
    # Exercises:
    #     if not state:
    #         continue
    # ---------------------------------------------------------
    response = client.get("/jobs/?sla=WITHIN_SLA")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["id"] == 101

    # ---------------------------------------------------------
    # 8. Exactly 900 seconds
    # 900 belongs to WITHIN_SLA
    # ---------------------------------------------------------
    def mocked_900_state(self, job_id):
        if str(job_id) == "101":
            return {
                "job_id": "101",
                "remaining_seconds": 900,
            }

        return None

    monkeypatch.setattr(
        SLAService,
        "get_sla_state",
        mocked_900_state,
    )

    response = client.get("/jobs/?sla=WITHIN_SLA")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["id"] == 101

    # ---------------------------------------------------------
    # 9. Exactly 0 seconds
    # 0 belongs to BREACHED
    # ---------------------------------------------------------
    db = TestingSessionLocal()

    try:
        job = db.query(Job).filter(Job.id == 101).first()
        assert job is not None

        job.sla_deadline = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()

    response = client.get("/jobs/?sla=BREACHED")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["id"] == 101

    # ---------------------------------------------------------
    # 10. Exactly 899 seconds
    # 899 belongs to APPROACHING_BREACH
    # ---------------------------------------------------------
    db = TestingSessionLocal()

    try:
        job_101 = db.query(Job).filter(Job.id == 101).first()
        job_102 = db.query(Job).filter(Job.id == 102).first()

        assert job_101 is not None
        assert job_102 is not None

        now_utc = datetime.now(timezone.utc)

        # Job 101 -> 899 seconds -> APPROACHING_BREACH
        job_101.sla_deadline = now_utc + timedelta(seconds=899)

        # Move Job 102 outside the approaching window so this test
        # isolates the 899-second boundary for Job 101.
        job_102.sla_deadline = now_utc + timedelta(minutes=30)

        db.commit()
    finally:
        db.close()

    response = client.get("/jobs/?sla=APPROACHING_BREACH")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["id"] == 101

# ---------------------------------------------------------------------------
# Combined filtering
# ---------------------------------------------------------------------------

def test_get_jobs_combined_filters():
    response = client.get(
        "/jobs/?search=John&status=active&priority=CRITICAL"
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["id"] == 101


def test_get_jobs_combined_sla_and_priority(monkeypatch):
    from app.routes.jobs import SLAService

    def mocked_get_sla_state(self, job_id):
        states = {
            "101": {
                "job_id": "101",
                "remaining_seconds": 1800,
            },
            "102": {
                "job_id": "102",
                "remaining_seconds": 600,
            },
            "103": {
                "job_id": "103",
                "remaining_seconds": -600,
            },
            "104": None,
        }

        return states.get(str(job_id))

    monkeypatch.setattr(
        SLAService,
        "get_sla_state",
        mocked_get_sla_state,
    )

    response = client.get(
        "/jobs/?priority=CRITICAL&sla=WITHIN_SLA"
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["id"] == 101
    assert data[0]["priority"] == "CRITICAL"

# ---------------------------------------------------------------------------
# Generic exception path
# ---------------------------------------------------------------------------

def test_get_jobs_generic_exception(monkeypatch):
    from app.routes.jobs import SLAService

    def raise_error(self):
        raise RuntimeError("forced test failure")

    monkeypatch.setattr(
        SLAService,
        "__init__",
        raise_error,
    )

    response = client.get("/jobs/")

    assert response.status_code == 500

    data = response.json()

    assert "Failed to fetch jobs" in data["detail"]

# ---------------------------------------------------------------------------
# Additional get_jobs branch coverage
# ---------------------------------------------------------------------------

def test_get_jobs_status_and_priority_case_normalization():
    """
    Covers uppercase/lowercase normalization paths for status and priority.
    """

    response = client.get(
        "/jobs/?status=IN PROGRESS&priority=critical"
    )

    assert response.status_code == 200

    data = response.json()

    # IN PROGRESS -> normalized to inprogress
    # CRITICAL -> normalized to CRITICAL
    assert len(data) == 0


def test_get_jobs_status_normal_else_branch():
    """
    Explicitly exercises the normal status equality branch.
    """

    response = client.get("/jobs/?status=ACTIVE")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["id"] == 101


def test_get_jobs_priority_generic_else_branch():
    """
    Explicitly exercises the generic priority equality branch.
    """

    response = client.get("/jobs/?priority=URGENT")

    assert response.status_code == 200
    assert response.json() == []


def test_get_jobs_service_type_normalization():
    """
    Exercises underscore replacement, strip, and lowercase normalization.
    """

    response = client.get(
        "/jobs/?service_type=%20HVAC_Repair%20"
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["id"] == 101


def test_get_jobs_sla_lowercase_normalization(monkeypatch):
    """
    Exercises SLA upper()/strip() normalization.
    """
    from app.routes.jobs import SLAService

    def mocked_get_sla_state(self, job_id):
        states = {
            "101": {"remaining_seconds": 1800},
            "102": {"remaining_seconds": 600},
            "103": {"remaining_seconds": -600},
            "104": None,
        }

        return states.get(str(job_id))

    monkeypatch.setattr(
        SLAService,
        "get_sla_state",
        mocked_get_sla_state,
    )

    response = client.get(
        "/jobs/?sla=%20within_sla%20"
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["id"] == 101


def test_get_jobs_sla_returns_empty_when_no_jobs_match(monkeypatch):
    """
    Exercises the Job.id.in_([]) path.
    """
    from app.routes.jobs import SLAService

    def mocked_get_sla_state(self, job_id):
        return {
            "remaining_seconds": 1000
        }

    monkeypatch.setattr(
        SLAService,
        "get_sla_state",
        mocked_get_sla_state,
    )

    response = client.get(
        "/jobs/?sla=BREACHED"
    )

    assert response.status_code == 200
    assert response.json() == []


def test_get_jobs_pagination_with_filter(monkeypatch):
    """
    Exercises pagination after filtering.
    """
    from app.routes.jobs import SLAService

    def mocked_get_sla_state(self, job_id):
        states = {
            "101": {"remaining_seconds": 1800},
            "102": {"remaining_seconds": 600},
            "103": {"remaining_seconds": -600},
            "104": None,
        }

        return states.get(str(job_id))

    monkeypatch.setattr(
        SLAService,
        "get_sla_state",
        mocked_get_sla_state,
    )

    response = client.get(
        "/jobs/?sla=WITHIN_SLA&page=1&limit=1"
    )

    assert response.status_code == 200
    assert response.headers["X-Total-Count"] == "1"

    data = response.json()

    assert len(data) == 1
    assert data[0]["id"] == 101


def test_get_jobs_invalid_sla_preserves_http_exception():
    """
    Confirms the explicit HTTPException re-raise path is preserved.
    """
    response = client.get("/jobs/?sla=NOT_A_REAL_SLA")

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid SLA filter"


def test_get_jobs_response_total_count():
    """
    Covers the response header assignment explicitly.
    """
    response = client.get("/jobs/?status=active")

    assert response.status_code == 200
    assert response.headers["X-Total-Count"] == "1"
    assert response.headers["Access-Control-Expose-Headers"] == "X-Total-Count"

    
# ---------------------------------------------------------------------------
# Pending jobs
# ---------------------------------------------------------------------------

def test_get_pending_jobs():
    response = client.get("/jobs/pending")

    assert response.status_code == 200

    data = response.json()

    # Only John Doe (101) is pending.
    assert len(data) == 1

    names = [job["customer_name"] for job in data]

    assert "John Doe" in names
    assert "Bob Johnson" not in names
    assert "Dave Adams" not in names

    # Search filter
    response = client.get("/jobs/pending?search=John")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["customer_name"] == "John Doe"

def test_get_pending_jobs_numeric_search():
    """
    Covers the numeric search branch:

        id_val = int(search.replace("#", "").strip())
        id_filter = (Job.id == id_val)

    Job 101 is an unassigned active job.
    """
    response = client.get("/jobs/pending?search=101")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["id"] == 101
    assert data[0]["customer_name"] == "John Doe"


def test_get_pending_jobs_hash_numeric_search():
    """
    Covers search values such as '#101'.
    """
    response = client.get("/jobs/pending?search=%23101")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["id"] == 101


def test_get_pending_jobs_non_numeric_search():
    """
    Covers the ValueError -> pass branch when search cannot be converted
    to an integer.
    """
    response = client.get("/jobs/pending?search=John")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["id"] == 101


def test_get_pending_jobs_priority_text_search():
    """
    Covers priority inside text_filters.
    """
    response = client.get("/jobs/pending?search=CRITICAL")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["id"] == 101


def test_get_pending_jobs_expired_filter():
    """
    Covers:

        if active_filter == "expired":
            now_utc = ...
            query = query.filter(
                Job.sla_deadline.isnot(None),
                Job.sla_deadline < now_utc
            )

    Make the pending job expired first.
    """
    db = TestingSessionLocal()

    try:
        job = db.query(Job).filter(Job.id == 101).first()

        assert job is not None

        job.sla_deadline = datetime.now(timezone.utc) - timedelta(minutes=5)

        db.commit()
    finally:
        db.close()

    response = client.get("/jobs/pending?active_filter=expired")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["id"] == 101


def test_get_pending_jobs_redispatched_filter():
    """
    Covers:

        elif active_filter == "redispatched":
            query = query.filter(Job.attempt_count > 1)
    """
    db = TestingSessionLocal()

    try:
        job = db.query(Job).filter(Job.id == 101).first()

        assert job is not None

        job.attempt_count = 2

        db.commit()
    finally:
        db.close()

    response = client.get("/jobs/pending?active_filter=redispatched")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["id"] == 101


def test_get_pending_jobs_empty_result():
    """
    Covers the valid empty-result path.
    """
    response = client.get(
        "/jobs/pending?search=THIS_DOES_NOT_EXIST"
    )

    assert response.status_code == 200

    assert response.json() == []

    assert response.headers["X-Total-Count"] == "0"


def test_get_pending_jobs_pagination():
    """
    Covers:

        if page and limit:
            query = query.offset(...).limit(...)
    """
    response = client.get(
        "/jobs/pending?page=1&limit=1"
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert response.headers["X-Total-Count"] == "1"


def test_get_pending_jobs_page_without_limit():
    """
    Covers the false side of:

        if page and limit
    """
    response = client.get(
        "/jobs/pending?page=1"
    )

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_get_pending_jobs_limit_without_page():
    """
    Covers the other false side of:

        if page and limit
    """
    response = client.get(
        "/jobs/pending?limit=1"
    )

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_get_pending_jobs_unknown_active_filter():
    """
    Covers the path where neither 'expired' nor 'redispatched' matches.
    """
    response = client.get(
        "/jobs/pending?active_filter=unknown"
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["id"] == 101


def test_get_pending_jobs_exception(monkeypatch):
    """
    Covers the generic exception handler:

        except Exception as error:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to fetch pending jobs: {str(error)}"
            )
    """
    from app.routes import jobs as jobs_module

    class BrokenQuery:
        def count(self):
            raise RuntimeError("forced pending jobs failure")

    class BrokenDB:
        def query(self, *args, **kwargs):
            return BrokenQuery()

    def fake_get_db():
        return BrokenDB()

    # Call the route function directly so we can inject a broken DB object.
    response_obj = Response()

    # Get the route function from the module.
    route = jobs_module.get_pending_jobs

    with pytest.raises(Exception) as exc_info:
        route(
            response=response_obj,
            search=None,
            active_filter=None,
            page=None,
            limit=None,
            user_tenant=(None, "tenant-1"),
            db=BrokenDB(),
        )

    assert "Failed to fetch pending jobs" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Service types
# ---------------------------------------------------------------------------

def test_get_service_types():
    response = client.get("/jobs/service-types")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 4

    assert data == [
        "Electrical Service",
        "HVAC Repair",
        "Network Support",
        "Plumbing Service",
    ]


# ---------------------------------------------------------------------------
# Planned assignments
# ---------------------------------------------------------------------------

def test_get_planned_assignments():
    response = client.get("/planned-assignments")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["job_id"] == 102
    assert data[0]["technician"] == "Alice Smith"

    # Search matches technician name
    response = client.get("/planned-assignments?search=Alice")

    assert response.status_code == 200
    assert len(response.json()) == 1

    # Search doesn't match
    response = client.get("/planned-assignments?search=NonExistent")

    assert response.status_code == 200
    assert len(response.json()) == 0


@pytest.fixture(autouse=True)
def reset_rate_limit():
    """Reset this TestClient's Redis rate-limit keys around every test."""
    try:
        from app.redis_client import get_redis_client

        redis_manager = get_redis_client()
        redis_client = redis_manager.client
        keys = list(redis_client.scan_iter(match="rate_limit:testclient:*") )

        if keys:
            redis_client.delete(*keys)
    except Exception:
        pass

    yield

    try:
        from app.redis_client import get_redis_client

        redis_manager = get_redis_client()
        redis_client = redis_manager.client
        keys = list(redis_client.scan_iter(match="rate_limit:testclient:*") )

        if keys:
            redis_client.delete(*keys)
    except Exception:
        pass

# ---------------------------------------------------------------------------
# get_jobs_stats coverage
# ---------------------------------------------------------------------------

def test_get_jobs_stats_default():
    from app.routes.jobs import get_jobs_stats

    db = TestingSessionLocal()

    try:
        user = AuthenticatedUser(
            user_id="test-user",
            tenant_id="tenant-1",
            role="DISPATCHER",
            jti="test-jti",
            session_id="test-session",
        )

        result = get_jobs_stats(
            time_range=None,
            user_tenant=(user, "tenant-1"),
            db=db,
        )

        assert result["jobs"]["total"] == 4
        assert result["jobs"]["completed"] == 1
        assert result["jobs"]["in_progress"] == 1
        assert result["jobs"]["active"] == 0
        assert result["jobs"]["pending"] == 1

        assert result["technicians"]["available"] == 1
        assert result["technicians"]["busy"] == 0
        assert result["technicians"]["break"] == 0
        assert result["technicians"]["offline"] == 0

        assert result["categories"]["other"] == 4

    finally:
        db.close()


@pytest.mark.parametrize("time_range", ["week", "month"])
def test_get_jobs_stats_time_range(time_range):
    from app.routes.jobs import get_jobs_stats

    db = TestingSessionLocal()

    try:
        user = AuthenticatedUser(
            user_id="test-user",
            tenant_id="tenant-1",
            role="DISPATCHER",
            jti="test-jti",
            session_id="test-session",
        )

        result = get_jobs_stats(
            time_range=time_range,
            user_tenant=(user, "tenant-1"),
            db=db,
        )

        assert result["jobs"]["total"] == 4

    finally:
        db.close()


def test_get_jobs_stats_exception():
    from app.routes.jobs import get_jobs_stats

    class BrokenDB:
        def query(self, *args, **kwargs):
            raise RuntimeError("stats database failure")

    user = AuthenticatedUser(
        user_id="test-user",
        tenant_id="tenant-1",
        role="DISPATCHER",
        jti="test-jti",
        session_id="test-session",
    )

    with pytest.raises(HTTPException) as exc_info:
        get_jobs_stats(
            time_range=None,
            user_tenant=(user, "tenant-1"),
            db=BrokenDB(),
        )

    assert exc_info.value.status_code == 500
    assert "Failed to fetch dashboard stats" in exc_info.value.detail

# ---------------------------------------------------------------------------
# get_service_types coverage
# ---------------------------------------------------------------------------

def test_get_service_types_exception():
    from app.routes.jobs import get_service_types

    class BrokenQuery:
        def filter(self, *args, **kwargs):
            return self

        def distinct(self):
            raise RuntimeError("service type query failure")

    class BrokenDB:
        def query(self, *args, **kwargs):
            return BrokenQuery()

    user = AuthenticatedUser(
        user_id="test-user",
        tenant_id="tenant-1",
        role="DISPATCHER",
        jti="test-jti",
        session_id="test-session",
    )

    with pytest.raises(HTTPException) as exc_info:
        get_service_types(
            user_tenant=(user, "tenant-1"),
            db=BrokenDB(),
        )

    assert exc_info.value.status_code == 500
    assert "Failed to fetch unique service types" in exc_info.value.detail

# ---------------------------------------------------------------------------
# create_job coverage
# ---------------------------------------------------------------------------

def test_create_job_required_skill_fallback(monkeypatch):
    from app.routes.jobs import create_job

    monkeypatch.setattr(
        "app.routes.jobs.map_service_type_to_skill",
        lambda service_type: "Mapped HVAC Skill",
    )

    db = TestingSessionLocal()

    try:
        job_data = JobCreate(
            customer_name="Created Customer",
            location="North Zone",
            issue_description="AC issue",
            priority="HIGH",
            service_type="HVAC Repair",
            contact_number="9000000001",
            preferred_service_date=date.today(),
            status="ACTIVE",
            required_skill="",
            sla_deadline=None,
            attempt_count=None,
        )

        result = create_job(
            job=job_data,
            user_tenant=(None, "tenant-1"),
            db=db,
        )

        assert result.customer_name == "Created Customer"
        assert result.required_skill == "Mapped HVAC Skill"
        assert result.tenant_id == "tenant-1"
        assert result.attempt_count == 0

    finally:
        db.close()


def test_create_job_platform_super_admin():
    from app.routes.jobs import create_job

    class FakeUser:
        is_super_admin = True
        tenant_id = "__platform__"

    db = TestingSessionLocal()

    try:
        job_data = JobCreate(
            customer_name="Platform Customer",
            location="Platform Zone",
            issue_description="Platform issue",
            priority="LOW",
            service_type="Network Support",
            contact_number="9000000002",
            preferred_service_date=date.today(),
            status="ACTIVE",
            required_skill="Network Support",
            tenant_id="tenant-platform-target",
            sla_deadline=None,
            attempt_count=0,
        )

        result = create_job(
            job=job_data,
            user_tenant=(FakeUser(), "__platform__"),
            db=db,
        )

        assert result.tenant_id == "tenant-platform-target"

    finally:
        db.close()


def test_create_job_platform_super_admin_without_requested_tenant():
    from app.routes.jobs import create_job

    class FakeUser:
        is_super_admin = True
        tenant_id = "__platform__"

    db = TestingSessionLocal()

    try:
        job_data = JobCreate(
            customer_name="Platform Default Customer",
            location="Platform Zone",
            issue_description="Platform issue",
            priority="LOW",
            service_type="Network Support",
            contact_number="9000000003",
            preferred_service_date=date.today(),
            status="ACTIVE",
            required_skill="Network Support",
            tenant_id=None,
            sla_deadline=None,
            attempt_count=0,
        )

        result = create_job(
            job=job_data,
            user_tenant=(FakeUser(), "__platform__"),
            db=db,
        )

        assert result.tenant_id == "__platform__"

    finally:
        db.close()


def test_create_job_exception():
    from app.routes.jobs import create_job

    class BrokenDB:
        def add(self, value):
            raise RuntimeError("create job failure")

        def rollback(self):
            return None

        def commit(self):
            return None

        def refresh(self, value):
            return None

    job_data = JobCreate(
        customer_name="Broken Customer",
        location="Broken Zone",
        issue_description="Broken issue",
        priority="LOW",
        service_type="HVAC Repair",
        contact_number="9000000004",
        preferred_service_date=date.today(),
        status="ACTIVE",
        required_skill="HVAC Repair",
        sla_deadline=None,
        attempt_count=0,
    )

    with pytest.raises(HTTPException) as exc_info:
        create_job(
            job=job_data,
            user_tenant=(None, "tenant-1"),
            db=BrokenDB(),
        )

    assert exc_info.value.status_code == 500
    assert "Failed to create job" in exc_info.value.detail

# ---------------------------------------------------------------------------
# accept_job coverage
# ---------------------------------------------------------------------------

def _technician_user():
    return AuthenticatedUser(
        user_id="1",
        tenant_id="tenant-1",
        role="TECHNICIAN",
        jti="test-jti",
        session_id="test-session",
    )


class FakeAcceptRedis:
    def __init__(self, lock_result=True, timer_exists=True):
        self.lock_result = lock_result
        self.timer_exists = timer_exists
        self.deleted_keys = []

    def set(self, key, value, nx=True, ex=10):
        return self.lock_result

    def exists(self, key):
        return self.timer_exists

    

    def delete(self, key):
        self.deleted_keys.append(key)
        return 1


def test_accept_job_success(monkeypatch):
    from app.routes.jobs import accept_job

    db = TestingSessionLocal()

    try:
        job = db.query(Job).filter(Job.id == 102).first()
        tech = db.query(Technician).filter(
            Technician.technician_id == 1
        ).first()

        assert job is not None
        assert tech is not None

        job.status = "ASSIGNED"
        job.assigned_technician_id = tech.technician_id
        tech.current_jobs = 0

        db.commit = lambda: None

        redis_client = FakeAcceptRedis(
            lock_result=True,
            timer_exists=True,
        )

        result = accept_job(
            job_id=102,
            current_user=_technician_user(),
            db=db,
            redis_client=redis_client,
        )

        assert result["status"] == "EN_ROUTE"
        assert result["previous_status"] == "ASSIGNED"
        assert result["technician"]["tech_id"] == "tech-1"
        assert result["technician"]["status"] == "EN_ROUTE"
        assert result["tracking_enabled"] is True

        assert job.status == "EN_ROUTE"
        assert tech.technician_status == "EN_ROUTE"
        assert tech.current_jobs == 1

        assert "job:timer:102" in redis_client.deleted_keys
        assert any(
            key == "lock:job_accept:tenant-1:102"
            for key in redis_client.deleted_keys
        )

    finally:
        db.close()


def test_accept_job_validation_branches():
    from app.routes.jobs import accept_job

    # Job not found
    db = TestingSessionLocal()
    try:
        with pytest.raises(HTTPException) as exc_info:
            accept_job(
                job_id=999999,
                current_user=_technician_user(),
                db=db,
                redis_client=FakeAcceptRedis(),
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Job not found"
    finally:
        db.close()

    # Wrong job status
    db = TestingSessionLocal()
    try:
        job = db.query(Job).filter(Job.id == 101).first()
        assert job is not None

        with pytest.raises(HTTPException) as exc_info:
            accept_job(
                job_id=101,
                current_user=_technician_user(),
                db=db,
                redis_client=FakeAcceptRedis(),
            )

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Job is not in ASSIGNED status"
    finally:
        db.close()

    # Technician not assigned
    db = TestingSessionLocal()
    try:
        job = db.query(Job).filter(Job.id == 101).first()
        assert job is not None

        job.status = "ASSIGNED"
        job.assigned_technician_id = 999
        db.commit = lambda: None

        with pytest.raises(HTTPException) as exc_info:
            accept_job(
                job_id=101,
                current_user=_technician_user(),
                db=db,
                redis_client=FakeAcceptRedis(),
            )

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "Technician not assigned to this job"
    finally:
        db.close()


def test_accept_job_lock_and_timer_branches(monkeypatch):
    from app.routes.jobs import accept_job

    # Redis lock conflict
    db = TestingSessionLocal()
    try:
        job = db.query(Job).filter(Job.id == 101).first()
        assert job is not None

        tech = db.query(Technician).filter(
            Technician.technician_id == 1
        ).first()
        assert tech is not None

        job.status = "ASSIGNED"
        job.assigned_technician_id = tech.technician_id
        db.commit = lambda: None

        with pytest.raises(HTTPException) as exc_info:
            accept_job(
                job_id=101,
                current_user=_technician_user(),
                db=db,
                redis_client=FakeAcceptRedis(
                    lock_result=False,
                    timer_exists=True,
                ),
            )

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail == "Concurrent modification"
    finally:
        db.close()

    # Acceptance timer expired
    db = TestingSessionLocal()
    try:
        job = db.query(Job).filter(Job.id == 101).first()
        assert job is not None

        tech = db.query(Technician).filter(
            Technician.technician_id == 1
        ).first()
        assert tech is not None

        job.status = "ASSIGNED"
        job.assigned_technician_id = tech.technician_id
        db.commit = lambda: None

        redis_client = FakeAcceptRedis(
            lock_result=True,
            timer_exists=False,
        )

        with pytest.raises(HTTPException) as exc_info:
            accept_job(
                job_id=101,
                current_user=_technician_user(),
                db=db,
                redis_client=redis_client,
            )

        assert exc_info.value.status_code == 423
        assert exc_info.value.detail == "Acceptance window expired"

        assert "lock:job_accept:tenant-1:101" in redis_client.deleted_keys
    finally:
        db.close()

    # Commit failure
    db = TestingSessionLocal()
    try:
        job = db.query(Job).filter(Job.id == 101).first()
        assert job is not None

        tech = db.query(Technician).filter(
            Technician.technician_id == 1
        ).first()
        assert tech is not None

        job.status = "ASSIGNED"
        job.assigned_technician_id = tech.technician_id

        def broken_commit():
            raise RuntimeError("forced accept commit failure")

        db.commit = broken_commit
        db.rollback = lambda: None

        with pytest.raises(HTTPException) as exc_info:
            accept_job(
                job_id=101,
                current_user=_technician_user(),
                db=db,
                redis_client=FakeAcceptRedis(
                    lock_result=True,
                    timer_exists=True,
                ),
            )

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "Unable to accept job"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# reject_job coverage
# ---------------------------------------------------------------------------

def test_reject_job_success(monkeypatch):
    from app.routes.jobs import reject_job, JobRejectRequest

    monkeypatch.setattr(
        re_dispatch_queue.ReDispatchQueueService,
        "enqueue_failed_job",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        "app.routes.jobs.CooldownService.set_cooldown",
        lambda *args, **kwargs: None,
    )

    db = TestingSessionLocal()

    try:
        job = db.query(Job).filter(Job.id == 102).first()
        tech = db.query(Technician).filter(
            Technician.technician_id == 1
        ).first()

        assert job is not None
        assert tech is not None

        job.status = "ASSIGNED"
        job.assigned_technician_id = tech.technician_id
        tech.current_jobs = 1
        tech.technician_status = "EN_ROUTE"

        db.commit = lambda: None

        req = JobRejectRequest(
            reason="Customer timing no longer works",
        )

        result = reject_job(
            job_id=102,
            req=req,
            current_user=_technician_user(),
            db=db,
            redis_client=FakeAcceptRedis(),
        )

        assert result["status"] == "QUEUED"
        assert result["rejection"]["reason"] == (
            "Customer timing no longer works"
        )
        assert result["cooldown"]["duration_seconds"] == 120
        assert result["re_dispatch"]["triggered"] is True

        assert tech.technician_status == "AVAILABLE"
        assert tech.current_jobs == 0

    finally:
        db.close()


def test_reject_job_validation_branches(monkeypatch):
    from app.routes.jobs import reject_job, JobRejectRequest

    req = JobRejectRequest(
        reason="This rejection reason is long enough",
    )

    # Technician without tech_id
    db = TestingSessionLocal()
    try:
        tech = db.query(Technician).filter(
            Technician.technician_id == 1
        ).first()
        assert tech is not None

        tech.tech_id = None

        with pytest.raises(HTTPException) as exc_info:
            reject_job(
                job_id=102,
                req=req,
                current_user=_technician_user(),
                db=db,
                redis_client=FakeAcceptRedis(),
            )

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail == (
            "Technician is not linked with a tech_id"
        )
    finally:
        db.close()

    # Job not found
    db = TestingSessionLocal()
    try:
        with pytest.raises(HTTPException) as exc_info:
            reject_job(
                job_id=999999,
                req=req,
                current_user=_technician_user(),
                db=db,
                redis_client=FakeAcceptRedis(),
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Job not found"
    finally:
        db.close()

    # Wrong status
    db = TestingSessionLocal()
    try:
        with pytest.raises(HTTPException) as exc_info:
            reject_job(
                job_id=102,
                req=req,
                current_user=_technician_user(),
                db=db,
                redis_client=FakeAcceptRedis(),
            )

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == (
            "Only an assigned job can be rejected"
        )
    finally:
        db.close()

    # Assignment mismatch
    db = TestingSessionLocal()
    try:
        job = db.query(Job).filter(Job.id == 102).first()
        assert job is not None

        job.status = "ASSIGNED"
        job.assigned_technician_id = 999
        db.commit = lambda: None

        with pytest.raises(HTTPException) as exc_info:
            reject_job(
                job_id=102,
                req=req,
                current_user=_technician_user(),
                db=db,
                redis_client=FakeAcceptRedis(),
            )

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == (
            "Technician not assigned to this job"
        )
    finally:
        db.close()


def test_reject_job_commit_failure(monkeypatch):
    from app.routes.jobs import reject_job, JobRejectRequest

    monkeypatch.setattr(
        re_dispatch_queue.ReDispatchQueueService,
        "enqueue_failed_job",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        "app.routes.jobs.CooldownService.set_cooldown",
        lambda *args, **kwargs: None,
    )

    db = TestingSessionLocal()

    try:
        job = db.query(Job).filter(Job.id == 102).first()
        tech = db.query(Technician).filter(
            Technician.technician_id == 1
        ).first()

        assert job is not None
        assert tech is not None

        job.status = "ASSIGNED"
        job.assigned_technician_id = tech.technician_id

        def broken_commit():
            raise RuntimeError("forced reject commit failure")

        db.commit = broken_commit
        db.rollback = lambda: None

        req = JobRejectRequest(
            reason="This rejection reason is long enough",
        )

        with pytest.raises(HTTPException) as exc_info:
            reject_job(
                job_id=102,
                req=req,
                current_user=_technician_user(),
                db=db,
                redis_client=FakeAcceptRedis(),
            )

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "Unable to reject job"

    finally:
        db.close()


# ---------------------------------------------------------------------------
# reassign_job coverage
# ---------------------------------------------------------------------------

def test_reassign_job_success(monkeypatch):
    from app.routes.jobs import reassign_job, JobReassignRequest

    db = TestingSessionLocal()

    try:
        old_tech = db.query(Technician).filter(
            Technician.technician_id == 1
        ).first()
        assert old_tech is not None

        new_tech = Technician(
            technician_id=999,
            tech_id="tech-2",
            technician_name="Bob Wilson",
            technician_skill="HVAC Repair",
            technician_location="South Zone",
            technician_status="Available",
            current_jobs=0,
            max_jobs=5,
            tenant_id="tenant-1",
        )
        db.add(new_tech)
        db.commit()
        db.refresh(new_tech)

        job = db.query(Job).filter(Job.id == 102).first()
        assert job is not None

        job.status = "ASSIGNED"
        job.assigned_technician_id = old_tech.technician_id
        old_tech.current_jobs = 1
        new_tech.current_jobs = 0

        db.commit = lambda: None

        monkeypatch.setattr(
            "app.routes.jobs.is_skill_matching",
            lambda *args, **kwargs: True,
        )

        redis_client = FakeAcceptRedis()

        req = JobReassignRequest(
            new_tech_id="tech-2",
            reason="Reassigning for better field coverage",
        )

        result = reassign_job(
            job_id=102,
            req=req,
            current_user=_technician_user(),
            db=db,
            redis_client=redis_client,
        )

        assert result["status"] == "ASSIGNED"
        assert result["previous_technician"]["tech_id"] == "tech-1"
        assert result["new_technician"]["tech_id"] == "tech-2"

        assert job.assigned_technician_id == 999
        assert job.status == "ASSIGNED"
        assert old_tech.current_jobs == 0
        assert new_tech.current_jobs == 1

    finally:
        db.close()


def test_reassign_job_validation_branches(monkeypatch):
    from app.routes.jobs import reassign_job, JobReassignRequest

    req = JobReassignRequest(
        new_tech_id="tech-2",
        reason="Reassignment required for coverage",
    )

    # Job not found
    db = TestingSessionLocal()
    try:
        with pytest.raises(HTTPException) as exc_info:
            reassign_job(
                job_id=999999,
                req=req,
                current_user=_technician_user(),
                db=db,
                redis_client=FakeAcceptRedis(),
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Job not found"
    finally:
        db.close()

    # Current technician does not own the job
    db = TestingSessionLocal()
    try:
        job = db.query(Job).filter(Job.id == 102).first()
        assert job is not None

        job.assigned_technician_id = 999
        db.commit = lambda: None

        with pytest.raises(HTTPException) as exc_info:
            reassign_job(
                job_id=102,
                req=req,
                current_user=_technician_user(),
                db=db,
                redis_client=FakeAcceptRedis(),
            )

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == (
            "Technician not assigned to this job"
        )
    finally:
        db.close()

    # New technician not found
    db = TestingSessionLocal()
    try:
        job = db.query(Job).filter(Job.id == 102).first()
        tech = db.query(Technician).filter(
            Technician.technician_id == 1
        ).first()

        assert job is not None
        assert tech is not None

        job.assigned_technician_id = tech.technician_id
        db.commit = lambda: None

        with pytest.raises(HTTPException) as exc_info:
            reassign_job(
                job_id=102,
                req=req,
                current_user=_technician_user(),
                db=db,
                redis_client=FakeAcceptRedis(),
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "New technician not found"
    finally:
        db.close()

    # New technician offline
    db = TestingSessionLocal()
    try:
        old_tech = db.query(Technician).filter(
            Technician.technician_id == 1
        ).first()
        assert old_tech is not None

        new_tech = Technician(
            technician_id=998,
            tech_id="tech-2",
            technician_name="Bob Wilson",
            technician_skill="HVAC Repair",
            technician_location="South Zone",
            technician_status="OFFLINE",
            current_jobs=0,
            max_jobs=5,
            tenant_id="tenant-1",
        )
        db.add(new_tech)
        db.commit()

        job = db.query(Job).filter(Job.id == 102).first()
        assert job is not None
        job.assigned_technician_id = old_tech.technician_id
        db.commit = lambda: None

        with pytest.raises(HTTPException) as exc_info:
            reassign_job(
                job_id=102,
                req=req,
                current_user=_technician_user(),
                db=db,
                redis_client=FakeAcceptRedis(),
            )

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "New technician is OFFLINE"
    finally:
        db.close()


def test_reassign_job_skill_and_workload_branches(monkeypatch):
    from app.routes.jobs import reassign_job, JobReassignRequest

    # ---------------------------------------------------------
    # 1. Skill mismatch
    # ---------------------------------------------------------
    skill_req = JobReassignRequest(
        new_tech_id="tech-2",
        reason="Reassignment required for coverage",
    )

    db = TestingSessionLocal()

    try:
        old_tech = db.query(Technician).filter(
            Technician.technician_id == 1
        ).first()
        assert old_tech is not None

        new_tech = Technician(
            technician_id=999,
            tech_id="tech-2",
            technician_name="Bob Wilson",
            technician_skill="Electrical Repair",
            technician_location="South Zone",
            technician_status="Available",
            current_jobs=0,
            max_jobs=5,
            tenant_id="tenant-1",
        )

        db.add(new_tech)
        db.commit()

        job = db.query(Job).filter(Job.id == 102).first()
        assert job is not None
        job.assigned_technician_id = old_tech.technician_id
        db.commit = lambda: None

        monkeypatch.setattr(
            "app.routes.jobs.is_skill_matching",
            lambda *args, **kwargs: False,
        )

        with pytest.raises(HTTPException) as exc_info:
            reassign_job(
                job_id=102,
                req=skill_req,
                current_user=_technician_user(),
                db=db,
                redis_client=FakeAcceptRedis(),
            )

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == (
            "New technician missing required skills"
        )

    finally:
        db.close()

    # ---------------------------------------------------------
    # 2. Maximum workload
    # ---------------------------------------------------------
    workload_req = JobReassignRequest(
        new_tech_id="tech-3",
        reason="Reassignment required for capacity coverage",
    )

    db = TestingSessionLocal()

    try:
        old_tech = db.query(Technician).filter(
            Technician.technician_id == 1
        ).first()
        assert old_tech is not None

        new_tech = Technician(
            technician_id=998,
            tech_id="tech-3",
            technician_name="Charlie Brown",
            technician_skill="HVAC Repair",
            technician_location="South Zone",
            technician_status="Available",
            current_jobs=5,
            max_jobs=5,
            tenant_id="tenant-1",
        )

        db.add(new_tech)
        db.commit()

        job = db.query(Job).filter(Job.id == 102).first()
        assert job is not None
        job.assigned_technician_id = old_tech.technician_id
        db.commit = lambda: None

        monkeypatch.setattr(
            "app.routes.jobs.is_skill_matching",
            lambda *args, **kwargs: True,
        )

        with pytest.raises(HTTPException) as exc_info:
            reassign_job(
                job_id=102,
                req=workload_req,
                current_user=_technician_user(),
                db=db,
                redis_client=FakeAcceptRedis(),
            )

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == (
            "New technician is at maximum workload capacity"
        )

    finally:
        db.close()


def test_reassign_job_commit_failure(monkeypatch):
    from app.routes.jobs import reassign_job, JobReassignRequest

    db = TestingSessionLocal()

    try:
        old_tech = db.query(Technician).filter(
            Technician.technician_id == 1
        ).first()
        assert old_tech is not None

        new_tech = Technician(
            technician_id=999,
            tech_id="tech-2",
            technician_name="Bob Wilson",
            technician_skill="HVAC Repair",
            technician_location="South Zone",
            technician_status="Available",
            current_jobs=0,
            max_jobs=5,
            tenant_id="tenant-1",
        )
        db.add(new_tech)
        db.commit()
        db.refresh(new_tech)

        job = db.query(Job).filter(Job.id == 102).first()
        assert job is not None

        job.assigned_technician_id = old_tech.technician_id

        monkeypatch.setattr(
            "app.routes.jobs.is_skill_matching",
            lambda *args, **kwargs: True,
        )

        def broken_commit():
            raise RuntimeError("forced reassign commit failure")

        db.commit = broken_commit
        db.rollback = lambda: None

        req = JobReassignRequest(
            new_tech_id="tech-2",
            reason="Reassignment required for coverage",
        )

        with pytest.raises(HTTPException) as exc_info:
            reassign_job(
                job_id=102,
                req=req,
                current_user=_technician_user(),
                db=db,
                redis_client=FakeAcceptRedis(),
            )

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "Unable to reassign job"

    finally:
        db.close()

# ---------------------------------------------------------------------------
# assign_job coverage
# ---------------------------------------------------------------------------

def test_assign_job_success(monkeypatch):
    from app.routes.jobs import assign_job, JobAssignRequest

    db = TestingSessionLocal()

    try:
        job = db.query(Job).filter(Job.id == 101).first()
        tech = db.query(Technician).filter(
            Technician.technician_id == 1
        ).first()

        assert job is not None
        assert tech is not None

        class FakeRedis:
            def setex(self, *args, **kwargs):
                return True

            def delete(self, *args, **kwargs):
                return True

            def get(self, *args, **kwargs):
                return None

            def set(self, *args, **kwargs):
                return True
            def exists(self, *args, **kwargs):
                return False

            def ttl(self, *args, **kwargs):
                return 600

        monkeypatch.setattr(
            "app.routes.jobs.is_skill_matching",
            lambda *args, **kwargs: True,
        )

        req = JobAssignRequest(
            tech_id="tech-1",
            justification="Assign technician for HVAC service coverage",
        )

        result = __import__("asyncio").run(
            assign_job(
                job_id=101,
                req=req,
                current_user=AuthenticatedUser(
                    user_id="test-user",
                    tenant_id="tenant-1",
                    role=UserRole.DISPATCHER,
                    jti="test-jti",
                    session_id="test-session",
                ),
                db=db,
                redis_client=FakeRedis(),
            )
        )

        assert result["status"] == "ASSIGNED"
        assert result["job_id"] == 101
        assert result["technician_id"] == "tech-1"
        assert result["tenant_id"] == "tenant-1"
        assert result["override"]["cooldown_bypassed"] is True
        assert result["override"]["exclusion_bypassed"] is True

        db.refresh(job)
        db.refresh(tech)

        assert job.assigned_technician_id == 1
        assert job.status == "ASSIGNED"
        assert tech.current_jobs == 1

    finally:
        db.close()


def test_assign_job_job_not_found():
    from app.routes.jobs import assign_job, JobAssignRequest

    db = TestingSessionLocal()

    try:
        req = JobAssignRequest(
            tech_id="tech-1",
            justification="Coverage validation for missing job",
        )

        with pytest.raises(HTTPException) as exc_info:
            __import__("asyncio").run(
                assign_job(
                    job_id=999999,
                    req=req,
                    current_user=AuthenticatedUser(
                        user_id="test-user",
                        tenant_id="tenant-1",
                        role="DISPATCHER",
                        jti="test-jti",
                        session_id="test-session",
                    ),
                    db=db,
                    redis_client=None,
                )
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Job not found"

    finally:
        db.close()


def test_assign_job_invalid_status():
    from app.routes.jobs import assign_job, JobAssignRequest

    db = TestingSessionLocal()

    try:
        job = db.query(Job).filter(Job.id == 101).first()
        assert job is not None

        job.status = "COMPLETED"
        db.commit()

        req = JobAssignRequest(
            tech_id="tech-1",
            justification="Coverage validation for invalid status",
        )

        class FakeRedis:
            def __init__(self):
                self.client = self

            def setex(self, *args, **kwargs):
                return True

            def delete(self, *args, **kwargs):
                return True

            def get(self, *args, **kwargs):
                return None

            def set(self, *args, **kwargs):
                return True
            def exists(self, *args, **kwargs):
                return False

        with pytest.raises(HTTPException) as exc_info:
            __import__("asyncio").run(
                assign_job(
                    job_id=101,
                    req=req,
                    current_user=AuthenticatedUser(
                        user_id="test-user",
                        tenant_id="tenant-1",
                        role="DISPATCHER",
                        jti="test-jti",
                        session_id="test-session",
                    ),
                    db=db,
                    redis_client=FakeRedis(),
                )
            )

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == (
            "Job must be in QUEUED or ACTIVE status to be assigned"
        )

    finally:
        db.close()


def test_assign_job_already_assigned():
    from app.routes.jobs import assign_job, JobAssignRequest

    db = TestingSessionLocal()

    try:
        job = db.query(Job).filter(Job.id == 101).first()
        assert job is not None

        job.assigned_technician_id = 1
        db.commit()

        req = JobAssignRequest(
            tech_id="tech-1",
            justification="Coverage validation for assigned job",
        )

        class FakeRedis:
            def __init__(self):
                self.client = self

            def setex(self, *args, **kwargs):
                return True

            def delete(self, *args, **kwargs):
                return True

            def get(self, *args, **kwargs):
                return None

            def set(self, *args, **kwargs):
                return True

        with pytest.raises(HTTPException) as exc_info:
            __import__("asyncio").run(
                assign_job(
                    job_id=101,
                    req=req,
                    current_user=AuthenticatedUser(
                        user_id="test-user",
                        tenant_id="tenant-1",
                        role="DISPATCHER",
                        jti="test-jti",
                        session_id="test-session",
                    ),
                    db=db,
                    redis_client=FakeRedis(),
                )
            )

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == (
            "Job is already assigned to a technician"
        )

    finally:
        db.close()


def test_assign_job_technician_not_found():
    from app.routes.jobs import assign_job, JobAssignRequest

    db = TestingSessionLocal()

    try:
        req = JobAssignRequest(
            tech_id="missing-tech",
            justification="Coverage validation for missing technician",
        )

        class FakeRedis:
            def __init__(self):
                self.client = self

            def setex(self, *args, **kwargs):
                return True

            def delete(self, *args, **kwargs):
                return True

            def get(self, *args, **kwargs):
                return None

            def set(self, *args, **kwargs):
                return True

        with pytest.raises(HTTPException) as exc_info:
            __import__("asyncio").run(
                assign_job(
                    job_id=101,
                    req=req,
                    current_user=AuthenticatedUser(
                        user_id="test-user",
                        tenant_id="tenant-1",
                        role="DISPATCHER",
                        jti="test-jti",
                        session_id="test-session",
                    ),
                    db=db,
                    redis_client=FakeRedis(),
                )
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Technician not found"

    finally:
        db.close()


def test_assign_job_offline_technician():
    from app.routes.jobs import assign_job, JobAssignRequest

    db = TestingSessionLocal()

    try:
        tech = db.query(Technician).filter(
            Technician.technician_id == 1
        ).first()
        assert tech is not None

        tech.technician_status = "OFFLINE"
        db.commit()

        req = JobAssignRequest(
            tech_id="tech-1",
            justification="Coverage validation for offline technician",
        )

        class FakeRedis:
            def __init__(self):
                self.client = self

            def setex(self, *args, **kwargs):
                return True

            def delete(self, *args, **kwargs):
                return True

            def get(self, *args, **kwargs):
                return None

            def set(self, *args, **kwargs):
                return True

        with pytest.raises(HTTPException) as exc_info:
            __import__("asyncio").run(
                assign_job(
                    job_id=101,
                    req=req,
                    current_user=AuthenticatedUser(
                        user_id="test-user",
                        tenant_id="tenant-1",
                        role="DISPATCHER",
                        jti="test-jti",
                        session_id="test-session",
                    ),
                    db=db,
                    redis_client=FakeRedis(),
                )
            )

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == (
            "Technician is unavailable. Busy or offline technicians "
            "cannot be assigned jobs."
        )

    finally:
        db.close()


def test_assign_job_skill_mismatch(monkeypatch):
    from app.routes.jobs import assign_job, JobAssignRequest

    db = TestingSessionLocal()

    try:
        monkeypatch.setattr(
            "app.routes.jobs.is_skill_matching",
            lambda *args, **kwargs: False,
        )

        req = JobAssignRequest(
            tech_id="tech-1",
            justification="Coverage validation for skill mismatch",
        )

        with pytest.raises(HTTPException) as exc_info:
            __import__("asyncio").run(
                assign_job(
                    job_id=101,
                    req=req,
                    current_user=AuthenticatedUser(
                        user_id="test-user",
                        tenant_id="tenant-1",
                        role="DISPATCHER",
                        jti="test-jti",
                        session_id="test-session",
                    ),
                    db=db,
                    redis_client=None,
                )
            )

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == (
            "Technician missing required skills"
        )

    finally:
        db.close()


def test_assign_job_workload_capacity(monkeypatch):
    from app.routes.jobs import assign_job, JobAssignRequest

    db = TestingSessionLocal()

    try:
        tech = db.query(Technician).filter(
            Technician.technician_id == 1
        ).first()
        assert tech is not None

        tech.current_jobs = 5
        tech.max_jobs = 5
        db.commit()

        monkeypatch.setattr(
            "app.routes.jobs.is_skill_matching",
            lambda *args, **kwargs: True,
        )

        req = JobAssignRequest(
            tech_id="tech-1",
            justification="Coverage validation for maximum workload",
        )

        with pytest.raises(HTTPException) as exc_info:
            __import__("asyncio").run(
                assign_job(
                    job_id=101,
                    req=req,
                    current_user=AuthenticatedUser(
                        user_id="test-user",
                        tenant_id="tenant-1",
                        role="DISPATCHER",
                        jti="test-jti",
                        session_id="test-session",
                    ),
                    db=db,
                    redis_client=None,
                )
            )

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == (
            "Technician at maximum workload capacity"
        )

    finally:
        db.close()


def test_assign_job_commit_failure(monkeypatch):
    from app.routes.jobs import assign_job, JobAssignRequest

    db = TestingSessionLocal()

    try:
        monkeypatch.setattr(
            "app.routes.jobs.is_skill_matching",
            lambda *args, **kwargs: True,
        )

        req = JobAssignRequest(
            tech_id="tech-1",
            justification="Coverage validation for database commit failure",
        )

        def broken_refresh(instance):
            raise RuntimeError("forced assign refresh failure")

        db.refresh = broken_refresh
        db.rollback = lambda: None

        with pytest.raises(HTTPException) as exc_info:
            __import__("asyncio").run(
                assign_job(
                    job_id=101,
                    req=req,
                    current_user=AuthenticatedUser(
                        user_id="test-user",
                        tenant_id="tenant-1",
                        role=UserRole.DISPATCHER,
                        jti="test-jti",
                        session_id="test-session",
                    ),
                    db=db,
                    redis_client=None,
                )
            )

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "Unable to assign job"

    finally:
        db.close()


# ---------------------------------------------------------------------------
# get_jobs_stats coverage
# ---------------------------------------------------------------------------

def test_get_jobs_stats_all_time():
    from app.routes.jobs import get_jobs_stats

    db = TestingSessionLocal()

    try:
        result = get_jobs_stats(
            time_range=None,
            user_tenant=(
                AuthenticatedUser(
                    user_id="test-user",
                    tenant_id="tenant-1",
                    role="DISPATCHER",
                    jti="test-jti",
                    session_id="test-session",
                ),
                "tenant-1",
            ),
            db=db,
        )

        assert result["jobs"]["total"] == 4
        assert result["jobs"]["active"] == 0
        assert result["jobs"]["in_progress"] == 1
        assert result["jobs"]["completed"] == 1
        assert result["jobs"]["pending"] == 1

        assert result["technicians"]["available"] == 1
        assert result["technicians"]["busy"] == 0
        assert result["technicians"]["break"] == 0
        assert result["technicians"]["offline"] == 0

        assert result["categories"]["other"] == 4

    finally:
        db.close()


def test_get_jobs_stats_time_ranges():
    from app.routes.jobs import get_jobs_stats

    db = TestingSessionLocal()

    try:
        tech = db.query(Technician).filter(
            Technician.technician_id == 1
        ).first()
        assert tech is not None

        tech.technician_status = "BUSY"
        db.commit()

        current_user = AuthenticatedUser(
            user_id="test-user",
            tenant_id="tenant-1",
            role="DISPATCHER",
            jti="test-jti",
            session_id="test-session",
        )

        week_result = get_jobs_stats(
            time_range="week",
            user_tenant=(current_user, "tenant-1"),
            db=db,
        )

        assert week_result["jobs"]["total"] == 4
        assert week_result["technicians"]["busy"] == 1
        assert week_result["technicians"]["available"] == 0

        month_result = get_jobs_stats(
            time_range="month",
            user_tenant=(current_user, "tenant-1"),
            db=db,
        )

        assert month_result["jobs"]["total"] == 4
        assert month_result["technicians"]["busy"] == 1

    finally:
        db.close()


def test_get_jobs_stats_exception():
    from app.routes.jobs import get_jobs_stats

    class BrokenQuery:
        def filter(self, *args, **kwargs):
            raise RuntimeError("forced stats failure")

    class BrokenDB:
        def query(self, *args, **kwargs):
            return BrokenQuery()

    current_user = AuthenticatedUser(
        user_id="test-user",
        tenant_id="tenant-1",
        role="DISPATCHER",
        jti="test-jti",
        session_id="test-session",
    )

    with pytest.raises(HTTPException) as exc_info:
        get_jobs_stats(
            time_range=None,
            user_tenant=(current_user, "tenant-1"),
            db=BrokenDB(),
        )

    assert exc_info.value.status_code == 500
    assert "Failed to fetch dashboard stats" in exc_info.value.detail


def _dispatcher_user():
    return AuthenticatedUser(
        user_id="test-user",
        tenant_id="tenant-1",
        role=UserRole.DISPATCHER,
        jti="test-jti",
        session_id="test-session",
    )


def _technician_enum_user():
    return AuthenticatedUser(
        user_id="1",
        tenant_id="tenant-1",
        role=UserRole.TECHNICIAN,
        jti="test-jti",
        session_id="test-session",
    )


# -----------------------------------------------------------------------------
# get_technician_for_current_user
# -----------------------------------------------------------------------------

def test_get_technician_for_current_user_not_found():
    from app.routes.jobs import get_technician_for_current_user

    db = TestingSessionLocal()

    try:
        user = AuthenticatedUser(
            user_id="999999",
            tenant_id="tenant-1",
            role=UserRole.TECHNICIAN,
            jti="test-jti",
            session_id="test-session",
        )

        with pytest.raises(HTTPException) as exc_info:
            get_technician_for_current_user(db, user)

        assert exc_info.value.status_code == 404

    finally:
        db.close()


# -----------------------------------------------------------------------------
# get_service_types exception
# -----------------------------------------------------------------------------

def test_get_service_types_exception():
    from app.routes.jobs import get_service_types

    class BrokenQuery:
        def filter(self, *args, **kwargs):
            raise RuntimeError("forced service type failure")

    class BrokenDB:
        def query(self, *args, **kwargs):
            return BrokenQuery()

    with pytest.raises(HTTPException) as exc_info:
        get_service_types(
            user_tenant=(_dispatcher_user(), "tenant-1"),
            db=BrokenDB(),
        )

    assert exc_info.value.status_code == 500
    assert "Failed to fetch unique service types" in exc_info.value.detail


# -----------------------------------------------------------------------------
# create_job branches
# -----------------------------------------------------------------------------

def test_create_job_super_admin_platform_tenant():
    from app.routes.jobs import create_job

    db = TestingSessionLocal()

    try:
        user = AuthenticatedUser(
            user_id="platform-admin",
            tenant_id="__platform__",
            role=UserRole.SUPER_ADMIN,
            jti="test-jti",
            session_id="test-session",
        )

        job_data = JobCreate(
            customer_name="Platform Customer",
            location="Chennai",
            issue_description="Platform created job",
            priority="HIGH",
            service_type="HVAC Repair",
            contact_number="9999999999",
            preferred_service_date=date.today(),
            status="ACTIVE",
            required_skill="HVAC Repair",
            tenant_id="tenant-2",
            sla_deadline=None,
            attempt_count=0,
        )

        result = create_job(
            job=job_data,
            user_tenant=(user, "__platform__"),
            db=db,
        )

        assert result.tenant_id == "tenant-2"

    finally:
        db.close()


def test_create_job_escalated():
    from app.routes.jobs import create_job
    from app.models import SLAEscalation, AuditEvent

    db = TestingSessionLocal()

    try:
        job_data = JobCreate(
            customer_name="Escalated Customer",
            location="Chennai",
            issue_description="Urgent SLA issue",
            priority="CRITICAL",
            service_type="HVAC Repair",
            contact_number="9999999998",
            preferred_service_date=date.today(),
            status="ESCALATED",
            required_skill="HVAC Repair",
            sla_deadline=None,
            attempt_count=0,
        )

        result = create_job(
            job=job_data,
            user_tenant=(_dispatcher_user(), "tenant-1"),
            db=db,
        )

        assert result.status == "ESCALATED"

        escalation = db.query(SLAEscalation).filter(
            SLAEscalation.job_id == result.id
        ).first()

        assert escalation is not None
        assert escalation.status == "ESCALATED"

    finally:
        db.close()


# -----------------------------------------------------------------------------
# Redispatch history branches
# -----------------------------------------------------------------------------

def test_get_redispatch_history_event_types():
    from app.routes.jobs import get_redispatch_history
    from app.models import DispatcherAlert

    db = TestingSessionLocal()

    try:
        alert = DispatcherAlert(
            id="alert-branches",
            tenant_id="tenant-1",
            type="REDISPATCH",
            severity="WARNING",
            job_id=101,
            attempt_count=3,
            max_attempts=3,
            excluded_technicians=[
                {"name": "Tech Timeout", "reason": "timeout occurred"},
                {"name": "Tech Offline", "reason": "technician offline"},
                {"name": "Tech Reject", "reason": "manual rejection"},
                {"name": "Tech Timeout", "reason": "no response"},
            ],
        )

        db.add(alert)
        db.commit()

        result = get_redispatch_history(
            job_id=101,
            current_user=_dispatcher_user(),
            db=db,
        )

        event_types = {item["event_type"] for item in result}

        assert "timeout" in event_types
        assert "offline" in event_types
        assert "rejection" in event_types

    finally:
        db.close()


# -----------------------------------------------------------------------------
# Status history actor branches
# -----------------------------------------------------------------------------

def test_get_job_status_history_actor_id():
    from app.routes.jobs import get_job_status_history

    current_user = _dispatcher_user()

    class FakeEvent:
        id = 77
        job_id = "101"
        event_type = "job_status_transition"
        old_status = "ACTIVE"
        new_status = "IN_PROGRESS"
        tech_id = None
        actor_id = "dispatch_admin"
        reason = "Dispatcher changed status"
        created_at = datetime.now(timezone.utc) - timedelta(minutes=2)

    class FakeJob:
        id = 101
        tenant_id = "tenant-1"
        created_at = datetime.now(timezone.utc)

    event = FakeEvent()
    job = FakeJob()

    class FakeQuery:
        def __init__(self, result):
            self.result = result

        def filter(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def all(self):
            return self.result

        def first(self):
            return self.result

    class FakeDB:
        def query(self, model):
            if model is Job:
                return FakeQuery(job)

            if model is AuditEvent:
                return FakeQuery([event])

            if model is Technician:
                return FakeQuery(None)

            return FakeQuery(None)

    result = get_job_status_history(
        job_id=101,
        current_user=current_user,
        db=FakeDB(),
    )

    assert len(result) == 1
    assert result[0]["changed_by_name"] == "Dispatch Admin"
    assert result[0]["changed_by_role"] == "Admin"


# -----------------------------------------------------------------------------
# Valid transitions
# -----------------------------------------------------------------------------

def test_get_job_valid_transitions_invalid_id():
    from app.routes.jobs import get_job_valid_transitions

    db = TestingSessionLocal()

    try:
        with pytest.raises(HTTPException) as exc_info:
            get_job_valid_transitions(
                id="abc",
                current_user=_dispatcher_user(),
                db=db,
            )

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Invalid job ID"

    finally:
        db.close()


def test_get_job_valid_transitions_job_not_found():
    from app.routes.jobs import get_job_valid_transitions

    db = TestingSessionLocal()

    try:
        with pytest.raises(HTTPException) as exc_info:
            get_job_valid_transitions(
                id="999999",
                current_user=_dispatcher_user(),
                db=db,
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Job not found"

    finally:
        db.close()


def test_get_job_valid_transitions_success(monkeypatch):
    from app.routes.jobs import get_job_valid_transitions

    class FakeValidator:
        def get_valid_transitions(self, job, role):
            assert job.id == 101
            assert role == UserRole.DISPATCHER.value
            return ["IN_PROGRESS", "CANCELLED"]

    monkeypatch.setattr(
        "app.services.job_status_machine.TransitionValidator",
        FakeValidator,
    )

    db = TestingSessionLocal()

    try:
        result = get_job_valid_transitions(
            id="101",
            current_user=_dispatcher_user(),
            db=db,
        )

        assert result == ["IN_PROGRESS", "CANCELLED"]

    finally:
        db.close()


# -----------------------------------------------------------------------------
# Transition endpoint
# -----------------------------------------------------------------------------

def test_transition_job_invalid_id():
    from app.routes.jobs import transition_job_endpoint, TransitionRequest

    db = TestingSessionLocal()

    try:
        payload = TransitionRequest(
            status="IN_PROGRESS",
            reason="Valid transition reason",
        )

        request = Request(
            scope={
                "type": "http",
                "method": "POST",
                "path": "/api/v1/jobs/abc/transition",
                "headers": [],
            }
        )

        with pytest.raises(HTTPException) as exc_info:
            transition_job_endpoint(
                id="abc",
                payload=payload,
                request=request,
                current_user=_dispatcher_user(),
                db=db,
            )

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Invalid job ID"

    finally:
        db.close()


def test_transition_job_not_found():
    from app.routes.jobs import transition_job_endpoint, TransitionRequest

    db = TestingSessionLocal()

    try:
        payload = TransitionRequest(
            status="IN_PROGRESS",
            reason="Valid transition reason",
        )

        request = Request(
            scope={
                "type": "http",
                "method": "POST",
                "path": "/api/v1/jobs/999999/transition",
                "headers": [],
            }
        )

        with pytest.raises(HTTPException) as exc_info:
            transition_job_endpoint(
                id="999999",
                payload=payload,
                request=request,
                current_user=_dispatcher_user(),
                db=db,
            )

        assert exc_info.value.status_code == 404

    finally:
        db.close()


def test_transition_job_invalid_transition(monkeypatch):
    from app.routes.jobs import transition_job_endpoint, TransitionRequest
    from app.services.job_status_machine import InvalidTransitionError

    def raise_invalid(*args, **kwargs):
        raise InvalidTransitionError(
            "Invalid status transition",
            current="ACTIVE",
            target="INVALID",
        )

    monkeypatch.setattr(
        Job,
        "transition",
        raise_invalid,
    )

    db = TestingSessionLocal()

    try:
        payload = TransitionRequest(
            status="INVALID",
            reason="Transition validation",
        )

        request = Request(
            scope={
                "type": "http",
                "method": "POST",
                "path": "/api/v1/jobs/101/transition",
                "headers": [],
            }
        )

        with pytest.raises(HTTPException) as exc_info:
            transition_job_endpoint(
                id="101",
                payload=payload,
                request=request,
                current_user=_dispatcher_user(),
                db=db,
            )

        assert exc_info.value.status_code == 400

    finally:
        db.close()


def test_transition_job_permission_denied(monkeypatch):
    from app.routes.jobs import transition_job_endpoint, TransitionRequest
    from app.services.job_status_machine import PermissionDeniedError

    monkeypatch.setattr(
        Job,
        "transition",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            PermissionDeniedError(
                "Permission denied",
                required="DISPATCHER",
                actual="TECHNICIAN",
            )
        ),
    )

    db = TestingSessionLocal()

    try:
        payload = TransitionRequest(
            status="IN_PROGRESS",
            reason="Permission test reason",
        )

        request = Request(
            scope={
                "type": "http",
                "method": "POST",
                "path": "/api/v1/jobs/101/transition",
                "headers": [],
            }
        )

        with pytest.raises(HTTPException) as exc_info:
            transition_job_endpoint(
                id="101",
                payload=payload,
                request=request,
                current_user=_dispatcher_user(),
                db=db,
            )

        assert exc_info.value.status_code == 403

    finally:
        db.close()


def test_transition_job_reason_required(monkeypatch):
    from app.routes.jobs import transition_job_endpoint, TransitionRequest
    from app.services.job_status_machine import ReasonRequiredError

    monkeypatch.setattr(
        Job,
        "transition",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            ReasonRequiredError("A reason is required")
        ),
    )

    db = TestingSessionLocal()

    try:
        payload = TransitionRequest(
            status="IN_PROGRESS",
            reason=None,
        )

        request = Request(
            scope={
                "type": "http",
                "method": "POST",
                "path": "/api/v1/jobs/101/transition",
                "headers": [],
            }
        )

        with pytest.raises(HTTPException) as exc_info:
            transition_job_endpoint(
                id="101",
                payload=payload,
                request=request,
                current_user=_dispatcher_user(),
                db=db,
            )

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail["error"] == "REASON_REQUIRED"

    finally:
        db.close()


# -----------------------------------------------------------------------------
# SLA endpoint
# -----------------------------------------------------------------------------

def test_get_job_sla_invalid_id():
    from app.routes.jobs import get_job_sla

    db = TestingSessionLocal()

    try:
        with pytest.raises(HTTPException) as exc_info:
            get_job_sla(
                id="abc",
                current_user=_dispatcher_user(),
                db=db,
            )

        assert exc_info.value.status_code == 400

    finally:
        db.close()


def test_get_job_sla_not_found():
    from app.routes.jobs import get_job_sla

    db = TestingSessionLocal()

    try:
        with pytest.raises(HTTPException) as exc_info:
            get_job_sla(
                id="999999",
                current_user=_dispatcher_user(),
                db=db,
            )

        assert exc_info.value.status_code == 404

    finally:
        db.close()


def test_get_job_sla_no_state(monkeypatch):
    from app.routes.jobs import get_job_sla

    monkeypatch.setattr(
        "app.routes.jobs.SLAService.get_sla_state",
        lambda *args, **kwargs: None,
    )

    db = TestingSessionLocal()

    try:
        with pytest.raises(HTTPException) as exc_info:
            get_job_sla(
                id="101",
                current_user=_dispatcher_user(),
                db=db,
            )

        assert exc_info.value.status_code == 404
        assert "SLA state not found" in exc_info.value.detail

    finally:
        db.close()


def test_get_job_sla_success(monkeypatch):
    from app.routes.jobs import get_job_sla

    monkeypatch.setattr(
        "app.routes.jobs.SLAService.get_sla_state",
        lambda *args, **kwargs: {
            "job_id": "101",
            "sla_deadline": "2026-09-14T15:00:00+00:00",
            "remaining_seconds": 900,
            "status": "APPROACHING_BREACH",
            "is_critical": True,
            "is_breached": False,
        },
    )

    db = TestingSessionLocal()

    try:
        result = get_job_sla(
            id="101",
            current_user=_dispatcher_user(),
            db=db,
        )

        assert result["job_id"] == "101"
        assert result["remaining_minutes"] == 15
        assert result["is_critical"] is True
        assert result["is_breached"] is False

    finally:
        db.close()


# -----------------------------------------------------------------------------
# SLA dashboard
# -----------------------------------------------------------------------------

def test_get_sla_dashboard_branches(monkeypatch):
    from app.routes.jobs import get_sla_dashboard

    db = TestingSessionLocal()

    try:
        job = db.query(Job).filter(
            Job.id == 101
        ).first()

        assert job is not None

        job.status = "ASSIGNED"
        db.commit()

        states = {
            "101": {
                "remaining_seconds": 1200,
                "is_breached": False,
                "is_critical": True,
            }
        }

        monkeypatch.setattr(
            "app.routes.jobs.SLAService.get_sla_state",
            lambda self, job_id: states.get(str(job_id)),
        )

        result = get_sla_dashboard(
            current_user=_dispatcher_user(),
            db=db,
        )

        assert result["active_slas"] == 1
        assert result["critical"] == 1
        assert result["breached"] == 0
        assert result["avg_remaining_minutes"] == 20

    finally:
        db.close()


# -----------------------------------------------------------------------------
# Share tracking
# -----------------------------------------------------------------------------

def test_share_job_tracking_invalid_id():
    from app.routes.jobs import share_job_tracking

    db = TestingSessionLocal()

    try:
        with pytest.raises(HTTPException) as exc_info:
            share_job_tracking(
                id="abc",
                current_user=_dispatcher_user(),
                db=db,
            )

        assert exc_info.value.status_code == 400

    finally:
        db.close()


def test_share_job_tracking_not_found():
    from app.routes.jobs import share_job_tracking

    db = TestingSessionLocal()

    try:
        with pytest.raises(HTTPException) as exc_info:
            share_job_tracking(
                id="999999",
                current_user=_dispatcher_user(),
                db=db,
            )

        assert exc_info.value.status_code == 404

    finally:
        db.close()


def test_share_job_tracking_success(monkeypatch):
    from app.routes.jobs import share_job_tracking

    monkeypatch.setenv(
        "FRONTEND_URL",
        "http://test-frontend",
    )

    db = TestingSessionLocal()

    try:
        result = share_job_tracking(
            id="101",
            current_user=_dispatcher_user(),
            db=db,
        )

        assert result["token"]
        assert result["share_url"].startswith(
            "http://test-frontend/track/"
        )

    finally:
        db.close()


def test_share_job_tracking_commit_failure():
    from app.routes.jobs import share_job_tracking

    db = TestingSessionLocal()

    try:
        def broken_commit():
            raise RuntimeError("forced share commit failure")

        db.commit = broken_commit
        db.rollback = lambda: None

        with pytest.raises(HTTPException) as exc_info:
            share_job_tracking(
                id="101",
                current_user=_dispatcher_user(),
                db=db,
            )

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "Unable to create tracking link"

    finally:
        db.close()


# -----------------------------------------------------------------------------
# Public tracking
# -----------------------------------------------------------------------------

def test_get_public_tracking_info_not_found():
    from app.routes.jobs import get_public_tracking_info

    db = TestingSessionLocal()

    try:
        with pytest.raises(HTTPException) as exc_info:
            get_public_tracking_info(
                token="missing-token",
                db=db,
            )

        assert exc_info.value.status_code == 404

    finally:
        db.close()


def test_get_public_tracking_info_expired():
    from app.routes.jobs import get_public_tracking_info

    db = TestingSessionLocal()

    try:
        job = db.query(Job).filter(Job.id == 101).first()
        assert job is not None

        job.share_token = "expired-token"
        job.share_token_expires_at = (
            datetime.now(timezone.utc) - timedelta(hours=1)
        )
        db.commit()

        result = get_public_tracking_info(
            token="expired-token",
            db=db,
        )

        assert result["expired"] is True
        assert result["status"] == job.status

    finally:
        db.close()


def test_get_public_tracking_info_without_technician():
    from app.routes.jobs import get_public_tracking_info

    db = TestingSessionLocal()

    try:
        job = db.query(Job).filter(Job.id == 101).first()
        assert job is not None

        job.share_token = "active-no-tech"
        job.share_token_expires_at = (
            datetime.now(timezone.utc) + timedelta(hours=1)
        )
        job.assigned_technician_id = None
        db.commit()

        result = get_public_tracking_info(
            token="active-no-tech",
            db=db,
        )

        assert result["expired"] is False
        assert result["technician"] is None
        assert result["eta"] is None

    finally:
        db.close()


def test_get_public_tracking_info_eta_duration(monkeypatch):
    from app.routes.jobs import get_public_tracking_info

    class FakeETAService:
        async def calculate_eta(self, technician_id, job_id):
            return {"duration": 900}

    monkeypatch.setattr(
        "app.services.eta_service.ETAService",
        FakeETAService,
    )

    db = TestingSessionLocal()

    try:
        job = db.query(Job).filter(Job.id == 101).first()
        assert job is not None

        job.share_token = "active-with-tech"
        job.share_token_expires_at = (
            datetime.now(timezone.utc) + timedelta(hours=1)
        )
        job.assigned_technician_id = 1
        db.commit()

        result = get_public_tracking_info(
            token="active-with-tech",
            db=db,
        )

        assert result["expired"] is False
        assert result["technician"]["name"] == "Alice"
        assert result["eta"] == 15

    finally:
        db.close()


def test_get_public_tracking_info_eta_last_known(monkeypatch):
    from app.routes.jobs import get_public_tracking_info

    class FakeETAService:
        async def calculate_eta(self, technician_id, job_id):
            return {"last_known_location": True}

    monkeypatch.setattr(
        "app.services.eta_service.ETAService",
        FakeETAService,
    )

    db = TestingSessionLocal()

    try:
        job = db.query(Job).filter(Job.id == 101).first()
        assert job is not None

        job.share_token = "eta-last-known"
        job.share_token_expires_at = (
            datetime.now(timezone.utc) + timedelta(hours=1)
        )
        job.assigned_technician_id = 1
        db.commit()

        result = get_public_tracking_info(
            token="eta-last-known",
            db=db,
        )

        assert result["eta"] == 25

    finally:
        db.close()


def test_get_public_tracking_info_eta_exception(monkeypatch):
    from app.routes.jobs import get_public_tracking_info

    class FakeETAService:
        async def calculate_eta(self, technician_id, job_id):
            raise RuntimeError("ETA unavailable")

    monkeypatch.setattr(
        "app.services.eta_service.ETAService",
        FakeETAService,
    )

    db = TestingSessionLocal()

    try:
        job = db.query(Job).filter(Job.id == 101).first()
        assert job is not None

        job.share_token = "eta-error"
        job.share_token_expires_at = (
            datetime.now(timezone.utc) + timedelta(hours=1)
        )
        job.assigned_technician_id = 1
        db.commit()

        result = get_public_tracking_info(
            token="eta-error",
            db=db,
        )

        assert result["eta"] == 30

    finally:
        db.close()


# -----------------------------------------------------------------------------
# Closure endpoint validation
# -----------------------------------------------------------------------------

def test_close_job_endpoint_not_found():

    db = TestingSessionLocal()

    try:
        payload = JobClosureCreate(
            work_summary="Completed successfully",
            after_images=["after.jpg"],
            labour_cost=100.0,
            material_cost=50.0,
        )

        with pytest.raises(HTTPException) as exc_info:
            close_job_endpoint(
                job_id=999999,
                payload=payload,
                current_user=_technician_enum_user(),
                db=db,
            )

        assert exc_info.value.status_code == 404

    finally:
        db.close()


def test_close_job_endpoint_wrong_technician():
    from app.routes.jobs import close_job_endpoint

    db = TestingSessionLocal()

    try:
        job = db.query(Job).filter(Job.id == 101).first()
        assert job is not None

        job.assigned_technician_id = 999
        db.commit()

        payload = JobClosureCreate(
            work_summary="Completed successfully",
            after_images=["after.jpg"],
            labour_cost=100.0,
            material_cost=50.0,
        )

        with pytest.raises(HTTPException) as exc_info:
            close_job_endpoint(
                job_id=101,
                payload=payload,
                current_user=_technician_enum_user(),
                db=db,
            )

        assert exc_info.value.status_code == 403

    finally:
        db.close()


def test_close_job_endpoint_terminal_status():
    from app.routes.jobs import close_job_endpoint

    db = TestingSessionLocal()

    try:
        job = db.query(Job).filter(Job.id == 101).first()
        assert job is not None

        job.assigned_technician_id = 1
        job.status = "COMPLETED"
        db.commit()

        payload = JobClosureCreate(
            work_summary="Already completed",
            after_images=["after.jpg"],
            labour_cost=100.0,
            material_cost=50.0,
        )

        with pytest.raises(HTTPException) as exc_info:
            close_job_endpoint(
                job_id=101,
                payload=payload,
                current_user=_technician_enum_user(),
                db=db,
            )

        assert exc_info.value.status_code == 400
        assert "COMPLETED" in exc_info.value.detail

    finally:
        db.close()


# -----------------------------------------------------------------------------
# Get closure
# -----------------------------------------------------------------------------

def test_get_job_closure_endpoint_not_found():
    from app.routes.jobs import get_job_closure_endpoint

    db = TestingSessionLocal()

    try:
        with pytest.raises(HTTPException) as exc_info:
            get_job_closure_endpoint(
                job_id=999999,
                current_user=_dispatcher_user(),
                db=db,
            )

        assert exc_info.value.status_code == 404

    finally:
        db.close()


def test_get_job_closure_endpoint_dispatcher(monkeypatch):
    from app.routes.jobs import get_job_closure_endpoint

    monkeypatch.setattr(
        "app.routes.jobs.get_job_closure",
        lambda db, job_id: {
            "job_id": job_id,
            "status": "CLOSED",
        },
    )

    db = TestingSessionLocal()

    try:
        result = get_job_closure_endpoint(
            job_id=101,
            current_user=_dispatcher_user(),
            db=db,
        )

        assert result["job_id"] == 101
        assert result["status"] == "CLOSED"

    finally:
        db.close()

def test_plan_job_normal_certification_success(monkeypatch):
    from app.routes.jobs import plan_job_assignment

    db = TestingSessionLocal()

    try:
        current_user = _dispatcher_user()

        class FakeRedis:
            def incr(self, key):
                return 2

            def get(self, key):
                return None

            def setex(self, key, ttl, value):
                return True

            def expire(self, key, seconds):
                return True

        monkeypatch.setattr(
            "app.routes.jobs.CertificationValidator.validate_certifications",
            lambda *args, **kwargs: {
                "qualified": True,
                "warnings": [],
            },
        )

        monkeypatch.setattr(
            "app.routes.jobs.CooldownService.check_cooldown",
            lambda *args: False,
        )

        monkeypatch.setattr(
            "app.routes.jobs.ExclusionService.is_excluded",
            lambda *args: {"excluded": False},
        )

        monkeypatch.setattr(
            "app.routes.jobs.SkillScoringService.calculate_skill_score",
            lambda *args: {
                "qualified": True,
                "score": 0.9,
            },
        )

        monkeypatch.setattr(
            "app.routes.jobs.WorkloadScoringService.calculate_workload_score",
            lambda *args: {
                "score": 0.8,
                "active_jobs": 1,
            },
        )

        monkeypatch.setattr(
            "app.routes.jobs.DistanceScoringService.calculate_distance_score",
            AsyncMock(
                return_value=[
                    {
                        "score": 0.95,
                        "distance_km": 3.5,
                    }
                ]
            ),
        )

        monkeypatch.setattr(
            "app.routes.jobs.CompositeScoringService.get_weights",
            lambda *args: {
                "proximity": 0.4,
                "skill": 0.4,
                "workload": 0.2,
            },
        )

        monkeypatch.setattr(
            "app.routes.jobs.CompositeScoringService.composite_score",
            lambda *args: {
                "composite_score": 0.9,
                "breakdown": {
                    "proximity": 0.38,
                    "skill": 0.36,
                    "workload": 0.16,
                },
            },
        )

        monkeypatch.setattr(
            "app.routes.jobs.CompositeScoringService.rank_technicians",
            lambda self, qualified: qualified,
        )

        request = Request(
            scope={
                "type": "http",
                "method": "POST",
                "path": "/jobs/101/plan",
                "headers": [],
            }
        )

        

        result = asyncio.run(
            plan_job_assignment(
                job_id=101,
                request=request,
                admin_override=False,
                current_user=current_user,
                db=db,
                redis_client=FakeRedis(),
            )
        )

        assert result.job_id == "101"
        assert len(result.ranked_technicians) == 1
        assert result.ranked_technicians[0].tech_id == "tech-1"

    finally:
        db.close()


def test_assign_job_numeric_technician_fallback(monkeypatch):
    from app.routes.jobs import assign_job, JobAssignRequest
    from app.auth.rbac import UserRole

    db = TestingSessionLocal()

    try:
        job = db.query(Job).filter(Job.id == 101).first()
        assert job is not None
        job.status = "ACTIVE"
        job.assigned_technician_id = None

        tech = Technician(
            technician_id=2,
            tech_id="numeric-tech",
            technician_name="Numeric Tech",
            technician_skill="HVAC Repair",
            technician_location="North Zone",
            technician_status="Available",
            current_jobs=0,
            max_jobs=5,
            tenant_id="tenant-1",
        )

        db.add(tech)
        db.commit()

        user = AuthenticatedUser(
            user_id="dispatcher-1",
            tenant_id="tenant-1",
            role=UserRole.DISPATCHER,
            jti="test-jti",
            session_id="test-session",
        )

        req = JobAssignRequest(
            tech_id="2",
            justification="Assign numeric technician for coverage",
        )

        class FakeRedis:
            def setex(self, *args, **kwargs):
                return True

            def delete(self, *args, **kwargs):
                return True

            def get(self, *args, **kwargs):
                return None

            def set(self, *args, **kwargs):
                return True

            def exists(self, *args, **kwargs):
                return False

            def ttl(self, *args, **kwargs):
                return 600

        async def fake_emit(*args, **kwargs):
            return None

        monkeypatch.setattr(
            "app.services.socket_manager.sio.emit",
            fake_emit,
        )

        monkeypatch.setattr(
            "app.services.socket_manager.emit_notification",
            fake_emit,
        )

        monkeypatch.setattr(
            "app.services.timer_service.TimerService.start_timer",
            lambda *args, **kwargs: None,
        )

        monkeypatch.setattr(
            "app.services.cooldown_service.CooldownService.clear_cooldown",
            lambda *args, **kwargs: None,
        )

        

        result = asyncio.run(
            assign_job(
                job_id=101,
                req=req,
                current_user=user,
                db=db,
                redis_client=FakeRedis(),
            )
        )

        assert result["status"] == "ASSIGNED"
        assert result["technician_id"] == "numeric-tech"

    finally:
        db.close()


def test_get_technician_current_user_not_found():
    from app.routes.jobs import get_technician_for_current_user

    db = TestingSessionLocal()

    try:
        user = AuthenticatedUser(
            user_id="missing-user",
            tenant_id="tenant-1",
            role="DISPATCHER",
            jti="test-jti",
            session_id="test-session",
        )

        with pytest.raises(HTTPException) as exc_info:
            get_technician_for_current_user(db, user)

        assert exc_info.value.status_code == 404

    finally:
        db.close()


def test_get_job_status_history_edge_branches():
    from app.routes.jobs import get_job_status_history

    current_user = _dispatcher_user()

    class FakeJob:
        id = 101
        tenant_id = "tenant-1"
        created_at = datetime.now(timezone.utc)

    base_time = datetime.now(timezone.utc)

    class FakeEvent:
        def __init__(
            self,
            event_id,
            created_at,
            tech_id=None,
            actor_id=None,
        ):
            self.id = event_id
            self.job_id = "101"
            self.event_type = "job_status_transition"
            self.old_status = "ACTIVE"
            self.new_status = "IN_PROGRESS"
            self.tech_id = tech_id
            self.actor_id = actor_id
            self.reason = "Coverage test"
            self.created_at = created_at

    events = [
        FakeEvent(
            1,
            None,
            tech_id=None,
            actor_id=None,
        ),
        FakeEvent(
            2,
            base_time,
            tech_id="system",
            actor_id="system_admin",
        ),
    ]

    class FakeQuery:
        def __init__(self, value):
            self.value = value

        def filter(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def all(self):
            return self.value

        def first(self):
            return self.value

    class FakeDB:
        def query(self, model):
            if model is Job:
                return FakeQuery(FakeJob())
            if model is AuditEvent:
                return FakeQuery(events)
            if model is Technician:
                return FakeQuery(None)
            return FakeQuery(None)

    result = get_job_status_history(
        job_id=101,
        current_user=current_user,
        db=FakeDB(),
    )

    assert len(result) == 2
    assert result[0]["changed_by_name"] == "System"
    assert result[0]["changed_by_role"] == "SYSTEM"
    assert result[0]["duration_seconds"] is None

    assert result[1]["changed_by_name"] == "System Admin"
    assert result[1]["changed_by_role"] == "Admin"


def test_transition_job_reason_required(monkeypatch):
    from app.routes.jobs import transition_job_endpoint, TransitionRequest
    from app.services.job_status_machine import ReasonRequiredError

    def raise_reason(*args, **kwargs):
        raise ReasonRequiredError("Reason is required")

    monkeypatch.setattr(
        Job,
        "transition",
        raise_reason,
    )

    db = TestingSessionLocal()

    try:
        payload = TransitionRequest(
            status="IN_PROGRESS",
            reason=None,
        )

        request = Request(
            scope={
                "type": "http",
                "method": "POST",
                "path": "/api/v1/jobs/101/transition",
                "headers": [],
            }
        )

        with pytest.raises(HTTPException) as exc_info:
            transition_job_endpoint(
                id="101",
                payload=payload,
                request=request,
                current_user=_dispatcher_user(),
                db=db,
            )

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail["error"] == "REASON_REQUIRED"

    finally:
        db.close()


def test_transition_job_generic_exception(monkeypatch):
    from app.routes.jobs import transition_job_endpoint, TransitionRequest

    monkeypatch.setattr(
        Job,
        "transition",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("unexpected")
        ),
    )

    db = TestingSessionLocal()

    try:
        payload = TransitionRequest(
            status="IN_PROGRESS",
            reason="Generic exception coverage",
        )

        request = Request(
            scope={
                "type": "http",
                "method": "POST",
                "path": "/api/v1/jobs/101/transition",
                "headers": [],
            }
        )

        with pytest.raises(HTTPException) as exc_info:
            transition_job_endpoint(
                id="101",
                payload=payload,
                request=request,
                current_user=_dispatcher_user(),
                db=db,
            )

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "Unable to transition job"

    finally:
        db.close()


def test_get_sla_dashboard_empty_and_mixed(monkeypatch):
    from app.routes.jobs import get_sla_dashboard

    db = TestingSessionLocal()

    try:
        job1 = db.query(Job).filter(Job.id == 101).first()
        job2 = db.query(Job).filter(Job.id == 102).first()

        assert job1 is not None
        assert job2 is not None

        job1.status = "ASSIGNED"
        job2.status = "EN_ROUTE"
        db.commit()

        states = {
            "101": {
                "remaining_seconds": 600,
                "is_breached": False,
                "is_critical": True,
            },
            "102": {
                "remaining_seconds": -60,
                "is_breached": True,
                "is_critical": True,
            },
        }

        monkeypatch.setattr(
            "app.services.sla_service.SLAService.get_sla_state",
            lambda self, job_id: states.get(str(job_id)),
        )

        result = get_sla_dashboard(
            current_user=_dispatcher_user(),
            db=db,
        )

        assert result["active_slas"] == 2
        assert result["critical"] == 1
        assert result["breached"] == 1
        assert result["avg_remaining_minutes"] == 4

    finally:
        db.close()


def test_share_job_tracking_commit_failure(monkeypatch):
    from app.routes.jobs import share_job_tracking

    db = TestingSessionLocal()

    try:
        monkeypatch.setattr(
            db,
            "commit",
            lambda: (_ for _ in ()).throw(
                RuntimeError("commit failed")
            ),
        )

        with pytest.raises(HTTPException) as exc_info:
            share_job_tracking(
                id="101",
                current_user=_dispatcher_user(),
                db=db,
            )

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "Unable to create tracking link"

    finally:
        db.close()




def test_public_tracking_expired_and_not_found():
    from app.routes.jobs import get_public_tracking_info

    db = TestingSessionLocal()

    try:
        with pytest.raises(HTTPException) as exc_info:
            get_public_tracking_info(
                token="missing-token",
                db=db,
            )

        assert exc_info.value.status_code == 404

        job = db.query(Job).filter(Job.id == 101).first()
        assert job is not None

        job.share_token = "expired-token"
        job.share_token_expires_at = (
            datetime.now(timezone.utc) - timedelta(hours=1)
        )
        db.commit()

        result = get_public_tracking_info(
            token="expired-token",
            db=db,
        )

        assert result["expired"] is True

    finally:
        db.close()


def test_get_override_history_empty():
    from app.routes.jobs import get_override_history

    db = TestingSessionLocal()

    try:
        result = get_override_history(
            job_id=101,
            current_user=_dispatcher_user(),
            db=db,
        )

        assert result == []

    finally:
        db.close()


def test_get_job_closure_endpoint_dispatcher_success(monkeypatch):
    from app.routes.jobs import get_job_closure_endpoint

    expected = {
        "job_id": 101,
        "status": "OPEN",
    }

    monkeypatch.setattr(
        "app.routes.jobs.get_job_closure",
        lambda **kwargs: expected,
    )

    db = TestingSessionLocal()

    try:
        result = get_job_closure_endpoint(
            job_id=101,
            current_user=_dispatcher_user(),
            db=db,
        )

        assert result == expected

    finally:
        db.close()


def test_get_job_closure_endpoint_technician_wrong_job():
    from app.routes.jobs import get_job_closure_endpoint
    from app.auth.rbac import UserRole

    db = TestingSessionLocal()

    try:
        technician_user = AuthenticatedUser(
            user_id="tech-1",
            tenant_id="tenant-1",
            role=UserRole.TECHNICIAN,
            jti="test-jti",
            session_id="test-session",
        )

        job = db.query(Job).filter(Job.id == 101).first()
        assert job is not None

        job.assigned_technician_id = 999
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            get_job_closure_endpoint(
                job_id=101,
                current_user=technician_user,
                db=db,
            )

        assert exc_info.value.status_code == 403

    finally:
        db.close()


def test_close_job_endpoint_success(monkeypatch):
    from app.routes.jobs import close_job_endpoint
    from app.auth.rbac import UserRole

    expected = {
        "job_id": 101,
        "status": "COMPLETED",
    }

    monkeypatch.setattr(
        "app.services.job_closure_service.close_job",
        lambda **kwargs: expected,
    )

    db = TestingSessionLocal()

    try:
        job = db.query(Job).filter(Job.id == 101).first()
        assert job is not None

        job.assigned_technician_id = 1
        job.status = "ON_SITE"
        db.commit()

        technician_user = AuthenticatedUser(
            user_id="tech-1",
            tenant_id="tenant-1",
            role=UserRole.TECHNICIAN,
            jti="test-jti",
            session_id="test-session",
        )

        payload = JobClosureCreate(
            work_summary="Completed successfully",
            after_images=["after.jpg"],
            labour_cost=100.0,
            material_cost=50.0,
        )

        result = close_job_endpoint(
            job_id=101,
            payload=payload,
            current_user=technician_user,
            db=db,
        )
        assert result is not None
        assert result.job_id == 101

    finally:
        db.close()


def test_plan_job_job_location_parse_value_error(monkeypatch):
    from app.routes.jobs import plan_job_assignment

    db = TestingSessionLocal()

    try:
        job = db.query(Job).filter(Job.id == 101).first()
        assert job is not None
        job.location = "invalid,location"
        db.commit()

        class FakeRedis:
            def incr(self, key):
                return 2

            def get(self, key):
                return None

            def setex(self, *args, **kwargs):
                return True

        monkeypatch.setattr(
            "app.routes.jobs.CertificationValidator.validate_certifications",
            lambda *args, **kwargs: {"qualified": True},
        )
        monkeypatch.setattr(
            "app.routes.jobs.CooldownService.check_cooldown",
            lambda *args: False,
        )
        monkeypatch.setattr(
            "app.routes.jobs.ExclusionService.is_excluded",
            lambda *args: {"excluded": False},
        )
        monkeypatch.setattr(
            "app.routes.jobs.SkillScoringService.calculate_skill_score",
            lambda *args: {"qualified": True, "score": 0.9},
        )
        monkeypatch.setattr(
            "app.routes.jobs.WorkloadScoringService.calculate_workload_score",
            lambda *args: {"score": 0.8, "active_jobs": 1},
        )
        monkeypatch.setattr(
            "app.routes.jobs.DistanceScoringService.calculate_distance_score",
            AsyncMock(
                return_value=[
                    {"score": 0.9, "distance_km": 4.0}
                ]
            ),
        )
        monkeypatch.setattr(
            "app.routes.jobs.CompositeScoringService.get_weights",
            lambda *args: {
                "proximity": 0.4,
                "skill": 0.4,
                "workload": 0.2,
            },
        )
        monkeypatch.setattr(
            "app.routes.jobs.CompositeScoringService.composite_score",
            lambda *args: {
                "composite_score": 0.9,
                "breakdown": {},
            },
        )
        monkeypatch.setattr(
            "app.routes.jobs.CompositeScoringService.rank_technicians",
            lambda self, items: items,
        )

        request = Request(
            scope={
                "type": "http",
                "method": "POST",
                "path": "/jobs/101/plan",
                "headers": [],
            }
        )

        

        result = asyncio.run(
            plan_job_assignment(
                job_id=101,
                request=request,
                admin_override=False,
                current_user=_dispatcher_user(),
                db=db,
                redis_client=FakeRedis(),
            )
        )

        assert result.job_id == "101"

    finally:
        db.close()


def test_get_technician_for_current_user_numeric_id_not_found():
    from app.routes.jobs import get_technician_for_current_user

    db = TestingSessionLocal()

    try:
        user = AuthenticatedUser(
            user_id="999999",
            tenant_id="tenant-1",
            role="DISPATCHER",
            jti="test-jti",
            session_id="test-session",
        )

        with pytest.raises(HTTPException) as exc_info:
            get_technician_for_current_user(db, user)

        assert exc_info.value.status_code == 404

    finally:
        db.close()


def test_accept_job_missing_tech_id(monkeypatch):
    from app.routes.jobs import accept_job

    db = TestingSessionLocal()

    try:
        job = db.query(Job).filter(Job.id == 101).first()
        assert job is not None
        job.status = "ASSIGNED"
        job.assigned_technician_id = 1

        tech = db.query(Technician).filter(
            Technician.technician_id == 1
        ).first()
        assert tech is not None

        tech.tech_id = None
        db.commit()

        class FakeRedis:
            def set(self, *args, **kwargs):
                return True

            def delete(self, *args, **kwargs):
                return True

            def exists(self, *args, **kwargs):
                return True

        user = AuthenticatedUser(
            user_id="1",
            tenant_id="tenant-1",
            role="TECHNICIAN",
            jti="test-jti",
            session_id="test-session",
        )

        with pytest.raises(HTTPException) as exc_info:
            accept_job(
                job_id=101,
                current_user=user,
                db=db,
                redis_client=FakeRedis(),
            )

        assert exc_info.value.status_code == 409

    finally:
        db.close()


def test_assign_job_numeric_lookup_direct(monkeypatch):
    from app.routes.jobs import assign_job, JobAssignRequest
    from app.auth.rbac import UserRole

    db = TestingSessionLocal()

    try:
        job = db.query(Job).filter(Job.id == 101).first()
        assert job is not None
        job.status = "ACTIVE"
        job.assigned_technician_id = None

        tech = db.query(Technician).filter(
            Technician.technician_id == 1
        ).first()
        assert tech is not None

        request_data = JobAssignRequest(
            tech_id="1",
            justification="Numeric technician lookup coverage test",
        )

        user = AuthenticatedUser(
            user_id="dispatcher-1",
            tenant_id="tenant-1",
            role=UserRole.DISPATCHER,
            jti="test-jti",
            session_id="test-session",
        )

        monkeypatch.setattr(
            "app.services.socket_manager.sio.emit",
            AsyncMock(),
        )
        monkeypatch.setattr(
            "app.services.socket_manager.emit_notification",
            AsyncMock(),
        )
        monkeypatch.setattr(
            "app.services.timer_service.TimerService.start_timer",
            lambda *args, **kwargs: None,
        )
        monkeypatch.setattr(
            "app.services.cooldown_service.CooldownService.clear_cooldown",
            lambda *args, **kwargs: None,
        )

        class FakeRedis:
            def delete(self, *args, **kwargs):
                return True

            def setex(self, *args, **kwargs):
                return True

            def exists(self, *args, **kwargs):
                return False

            def ttl(self, *args, **kwargs):
                return 600

            def get(self, *args, **kwargs):
                return None

        

        result = asyncio.run(
            assign_job(
                job_id=101,
                req=request_data,
                current_user=user,
                db=db,
                redis_client=FakeRedis(),
            )
        )

        assert result["status"] == "ASSIGNED"

    finally:
        db.close()


def test_get_job_status_history_event_without_created_at():
    from app.routes.jobs import get_job_status_history

    current_user = _dispatcher_user()

    class FakeJob:
        id = 101
        tenant_id = "tenant-1"
        created_at = datetime.now(timezone.utc)

    class FakeEvent:
        id = 500
        job_id = "101"
        event_type = "job_status_transition"
        old_status = None
        new_status = "ACTIVE"
        tech_id = None
        actor_id = None
        reason = None
        created_at = None

    class FakeQuery:
        def __init__(self, value):
            self.value = value

        def filter(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def first(self):
            return self.value

        def all(self):
            return self.value

    class FakeDB:
        def query(self, model):
            if model is Job:
                return FakeQuery(FakeJob())
            if model is AuditEvent:
                return FakeQuery([FakeEvent()])
            if model is Technician:
                return FakeQuery(None)
            return FakeQuery(None)

    result = get_job_status_history(
        job_id=101,
        current_user=current_user,
        db=FakeDB(),
    )

    assert len(result) == 1
    assert result[0]["changed_by_name"] == "System"
    assert result[0]["changed_by_role"] == "SYSTEM"
    assert result[0]["duration_seconds"] is None


def test_transition_job_success(monkeypatch):
    from app.routes.jobs import transition_job_endpoint, TransitionRequest

    def fake_transition(self, *args, **kwargs):
        self.status = "IN_PROGRESS"

    monkeypatch.setattr(
        Job,
        "transition",
        fake_transition,
    )

    db = TestingSessionLocal()

    try:
        payload = TransitionRequest(
            status="IN_PROGRESS",
            reason="Successful transition coverage",
        )

        request = Request(
            scope={
                "type": "http",
                "method": "POST",
                "path": "/api/v1/jobs/101/transition",
                "headers": [],
            }
        )

        result = transition_job_endpoint(
            id="101",
            payload=payload,
            request=request,
            current_user=_dispatcher_user(),
            db=db,
        )

        assert result["status"] == "success"
        assert result["new_status"] == "IN_PROGRESS"

    finally:
        db.close()


def test_get_sla_dashboard_no_active_slas(monkeypatch):
    from app.routes.jobs import get_sla_dashboard

    db = TestingSessionLocal()

    try:
        job1 = db.query(Job).filter(Job.id == 101).first()
        job2 = db.query(Job).filter(Job.id == 102).first()

        assert job1 is not None
        assert job2 is not None

        job1.status = "ASSIGNED"
        job2.status = "EN_ROUTE"
        db.commit()

        monkeypatch.setattr(
            "app.services.sla_service.SLAService.get_sla_state",
            lambda self, job_id: None,
        )

        result = get_sla_dashboard(
            current_user=_dispatcher_user(),
            db=db,
        )

        assert result["active_slas"] == 0
        assert result["critical"] == 0
        assert result["breached"] == 0
        assert result["avg_remaining_minutes"] == 0

    finally:
        db.close()


def test_redispatch_history_generates_missing_attempts():
    from app.routes.jobs import get_redispatch_history

    db = TestingSessionLocal()

    try:
        job = db.query(Job).filter(Job.id == 101).first()
        assert job is not None

        job.attempt_count = 5
        db.commit()

        result = get_redispatch_history(
            job_id=101,
            current_user=_dispatcher_user(),
            db=db,
        )

        assert len(result) == 5
        assert result[0]["attempt_number"] == 5
        assert result[-1]["attempt_number"] == 1

    finally:
        db.close()


def test_override_history_empty():
    from app.routes.jobs import get_override_history

    db = TestingSessionLocal()

    try:
        result = get_override_history(
            job_id=101,
            current_user=_dispatcher_user(),
            db=db,
        )

        assert result == []

    finally:
        db.close()


def test_close_job_terminal_status_lowercase():
    from app.routes.jobs import close_job_endpoint

    db = TestingSessionLocal()

    try:
        job = db.query(Job).filter(Job.id == 101).first()
        assert job is not None

        job.assigned_technician_id = 1
        job.status = "closed"
        db.commit()

        payload = JobClosureCreate(
            work_summary="Already closed",
            after_images=["after.jpg"],
            labour_cost=100.0,
            material_cost=50.0,
        )

        with pytest.raises(HTTPException) as exc_info:
            close_job_endpoint(
                job_id=101,
                payload=payload,
                current_user=_technician_enum_user(),
                db=db,
            )

        assert exc_info.value.status_code == 400

    finally:
        db.close()


def test_get_job_closure_endpoint_technician_success(monkeypatch):
    from app.routes.jobs import get_job_closure_endpoint

    expected = {
        "job_id": 101,
        "status": "OPEN",
    }

    monkeypatch.setattr(
        "app.routes.jobs.get_job_closure",
        lambda **kwargs: expected,
    )

    db = TestingSessionLocal()

    try:
        job = db.query(Job).filter(Job.id == 101).first()
        assert job is not None

        job.assigned_technician_id = 1
        db.commit()

        result = get_job_closure_endpoint(
            job_id=101,
            current_user=_technician_enum_user(),
            db=db,
        )

        assert result == expected

    finally:
        db.close()


def test_get_jobs_stats_other_count_clamped_to_zero():
    from app.routes.jobs import get_jobs_stats

    class FakeQuery:
        def __init__(self):
            self.count_index = 0
            self.count_values = [
                0,  # total_jobs
                0,  # completed
                0,  # cancelled
                0,  # in_progress
                0,  # active
                0,  # pending
                0, 0, 0, 0,  # available, busy, break, offline
                1, 1, 1, 1,  # hvac, electrical, plumbing, mechanical
            ]

        def filter(self, *args, **kwargs):
            return self

        def count(self):
            value = self.count_values[self.count_index]
            self.count_index += 1
            return value

    query = FakeQuery()

    class FakeDB:
        def query(self, model):
            return query

    result = get_jobs_stats(
        time_range=None,
        user_tenant=(None, "tenant-1"),
        db=FakeDB(),
    )

    assert result["jobs"]["total"] == 0


def test_assign_job_numeric_technician_with_missing_tech_id(monkeypatch):
    from app.routes.jobs import assign_job, JobAssignRequest

    db = TestingSessionLocal()

    try:
        job = db.query(Job).filter(Job.id == 101).first()
        tech = db.query(Technician).filter(
            Technician.technician_id == 1
        ).first()

        assert job is not None
        assert tech is not None

        job.status = "ACTIVE"
        job.assigned_technician_id = None
        tech.tech_id = None
        tech.technician_status = "AVAILABLE"
        tech.current_jobs = 0
        db.commit()

        request = Request(
            scope={
                "type": "http",
                "method": "POST",
                "path": "/jobs/101/assign",
                "headers": [],
            }
        )

        payload = JobAssignRequest(
            tech_id="1",
            justification="Coverage test for numeric technician",
            skip_skill_check=True,
            skip_workload_check=True,
        )

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                assign_job(
                    job_id=101,
                    req=payload,
                    current_user=_dispatcher_user(),
                    db=db,
                    redis_client=None,
                )
            )

        assert exc_info.value.status_code == 409
        assert "not linked with a tech_id" in exc_info.value.detail

    finally:
        db.close()


def test_get_job_status_history_technician_not_found():
    from app.routes.jobs import get_job_status_history

    class FakeEvent:
        id = 999
        job_id = "101"
        old_status = "ACTIVE"
        new_status = "ON_SITE"
        tech_id = "missing-tech"
        actor_id = None
        reason = "Technician arrived"
        created_at = datetime.now(timezone.utc)

    event = FakeEvent()

    class FakeJob:
        id = 101

    class FakeQuery:
        def __init__(self, result):
            self.result = result

        def filter(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def all(self):
            return self.result

        def first(self):
            return self.result

    class FakeDB:
        def query(self, model):
            if model is Job:
                return FakeQuery(FakeJob())

            if model.__name__ == "AuditEvent":
                return FakeQuery([event])

            if model.__name__ == "Technician":
                return FakeQuery(None)

            return FakeQuery(None)

    result = get_job_status_history(
        job_id=101,
        current_user=_dispatcher_user(),
        db=FakeDB(),
    )

    assert len(result) == 1
    assert result[0]["changed_by_name"] == "System"
    assert result[0]["changed_by_role"] == "SYSTEM"


def test_get_sla_dashboard_non_breached_non_critical(monkeypatch):
    from app.routes.jobs import get_sla_dashboard

    class FakeSLAService:
        def get_sla_state(self, job_id):
            return {
                "is_breached": False,
                "is_critical": False,
                "remaining_seconds": 120,
            }

    monkeypatch.setattr(
        "app.services.sla_service.SLAService",
        FakeSLAService,
    )

    db = TestingSessionLocal()

    try:
        job = db.query(Job).filter(Job.id == 101).first()
        assert job is not None

        job.status = "ASSIGNED"
        job.tenant_id = "tenant-1"
        db.commit()

        result = get_sla_dashboard(
            current_user=_dispatcher_user(),
            db=db,
        )

        assert result["active_slas"] >= 1
        assert result["breached"] == 0
        assert result["critical"] == 0

    finally:
        db.close()


def test_public_tracking_naive_expiry(monkeypatch):
    from app.routes.jobs import get_public_tracking_info

    class FakeJob:
        share_token = "naive-token"
        share_token_expires_at = datetime.now() + timedelta(minutes=30)
        status = "ACTIVE"
        assigned_technician_id = None
        tenant_id = "tenant-1"
        id = 101
        customer_name = "Customer"
        issue_description = "Issue"
        service_type = "HVAC Repair"
        site_latitude = None
        site_longitude = None
        site_address = "Test Address"
        location = "Test Location"

    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def first(self):
            return FakeJob()

    class FakeDB:
        def query(self, model):
            return FakeQuery()

    result = get_public_tracking_info(
        token="naive-token",
        db=FakeDB(),
    )

    assert result["expired"] is False


def test_public_tracking_technician_not_found(monkeypatch):
    from app.routes.jobs import get_public_tracking_info

    class FakeJob:
        share_token = "missing-tech-token"
        share_token_expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
        status = "ACTIVE"
        assigned_technician_id = 999
        tenant_id = "tenant-1"
        id = 101
        customer_name = "Customer"
        issue_description = "Issue"
        service_type = "HVAC Repair"
        site_latitude = None
        site_longitude = None
        site_address = "Test Address"
        location = "Test Location"

    class FakeQuery:
        def __init__(self, result=None):
            self.result = result

        def filter(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def first(self):
            return self.result

    class FakeDB:
        def query(self, model):
            if model is Job:
                return FakeQuery(FakeJob())

            return FakeQuery(None)

    result = get_public_tracking_info(
        token="missing-tech-token",
        db=FakeDB(),
    )

    assert result["expired"] is False
    assert result["technician"] is None
    assert result["eta"] is None


def test_public_tracking_with_gps_ping_and_empty_eta(monkeypatch):
    from app.routes.jobs import get_public_tracking_info

    class FakeTechnician:
        technician_id = 1
        tech_id = "tech-1"
        tenant_id = "tenant-1"
        technician_name = "Alice Smith"

    class FakePing:
        latitude = 13.0827
        longitude = 80.2707
        timestamp = datetime.now(timezone.utc)

    class FakeJob:
        share_token = "gps-token"
        share_token_expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
        status = "ACTIVE"
        assigned_technician_id = 1
        tenant_id = "tenant-1"
        id = 101
        customer_name = "Customer"
        issue_description = "Issue"
        service_type = "HVAC Repair"
        site_latitude = None
        site_longitude = None
        site_address = "Test Address"
        location = "Test Location"

    class FakeQuery:
        def __init__(self, result=None):
            self.result = result

        def filter(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def first(self):
            return self.result

    class FakeDB:
        def query(self, model):
            name = getattr(model, "__name__", "")

            if model is Job:
                return FakeQuery(FakeJob())

            if name == "Technician":
                return FakeQuery(FakeTechnician())

            if name == "GPSPing":
                return FakeQuery(FakePing())

            return FakeQuery(None)

    class FakeETAService:
        async def calculate_eta(self, technician_id, job_id):
            return {}

    monkeypatch.setattr(
        "app.services.eta_service.ETAService",
        FakeETAService,
    )

    result = get_public_tracking_info(
        token="gps-token",
        db=FakeDB(),
    )

    assert result["expired"] is False
    assert result["technician"]["name"] == "Alice"
    assert result["technician"]["rating"] == 4.8
    assert result["eta"] is None
    assert result["latest_gps"]["latitude"] == 13.0827
    assert result["latest_gps"]["longitude"] == 80.2707

def test_get_jobs_location_filter():
    response = client.get("/jobs/?location=North%20Zone")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["id"] == 101
    assert data[0]["location"] == "North Zone"


def test_get_jobs_technician_id_filter():
    response = client.get("/jobs/?technician_id=1")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["id"] == 102
    assert data[0]["assigned_technician_id"] == 1


# ---------------------------------------------------------------------------
# 100% coverage - bulk cancellation
# ---------------------------------------------------------------------------

def _bulk_cancel_test_user(role="dispatcher", tenant_id="tenant-1"):
    

    return SimpleNamespace(
        user_id="test-user",
        tenant_id=tenant_id,
        role=UserRole.DISPATCHER if role == "dispatcher" else UserRole.SUPER_ADMIN,
        is_super_admin=(role == "admin"),
    )


def test_bulk_cancel_forbidden_role():
    from app.routes.jobs import (
        bulk_cancel_jobs,
        BulkJobCancellationRequest,
    )

    user = AuthenticatedUser(
        user_id="test-user",
        tenant_id="tenant-1",
        role=UserRole.TECHNICIAN,
        jti="test-jti",
        session_id="test-session",
    )

    payload = BulkJobCancellationRequest(
        job_ids=[101],
        reason="Test cancellation",
    )

    with pytest.raises(HTTPException) as exc_info:
        bulk_cancel_jobs(
            payload=payload,
            request=None,
            current_user=user,
            db=TestingSessionLocal(),
        )

    assert exc_info.value.status_code == 403


def test_bulk_cancel_missing_job():
    from app.routes.jobs import (
        bulk_cancel_jobs,
        BulkJobCancellationRequest,
    )

    db = TestingSessionLocal()

    try:
        user = AuthenticatedUser(
            user_id="test-user",
            tenant_id="tenant-1",
            role=UserRole.DISPATCHER,
            jti="test-jti",
            session_id="test-session",
        )

        payload = BulkJobCancellationRequest(
            job_ids=[999999],
            reason="Missing job test",
        )

        with pytest.raises(HTTPException) as exc_info:
            bulk_cancel_jobs(
                payload=payload,
                request=None,
                current_user=user,
                db=db,
            )

        assert exc_info.value.status_code == 404

        detail = exc_info.value.detail
        assert detail["error"] == "JOB_NOT_FOUND"
        assert 999999 in detail["job_ids"]

    finally:
        db.close()


def test_bulk_cancel_requires_reason():
    from app.routes.jobs import (
        bulk_cancel_jobs,
        BulkJobCancellationRequest,
    )

    db = TestingSessionLocal()

    try:
        user = AuthenticatedUser(
            user_id="test-user",
            tenant_id="tenant-1",
            role=UserRole.DISPATCHER,
            jti="test-jti",
            session_id="test-session",
        )

        payload = BulkJobCancellationRequest(
            job_ids=[101],
            reason="   ",
        )

        with pytest.raises(HTTPException) as exc_info:
            bulk_cancel_jobs(
                payload=payload,
                request=None,
                current_user=user,
                db=db,
            )

        assert exc_info.value.status_code == 400

        detail = exc_info.value.detail

        assert detail["error"] == "BULK_CANCELLATION_VALIDATION_FAILED"
        assert detail["errors"][0]["error"] == "REASON_REQUIRED"

    finally:
        db.close()


def test_bulk_cancel_success():
    from app.routes.jobs import (
        bulk_cancel_jobs,
        BulkJobCancellationRequest,
    )

    db = TestingSessionLocal()

    try:
        job1 = db.query(Job).filter(Job.id == 101).first()
        job2 = db.query(Job).filter(Job.id == 102).first()

        assert job1 is not None
        assert job2 is not None

        job1.status = "CREATED"
        job2.status = "CREATED"

        db.commit()

        user = AuthenticatedUser(
            user_id="test-dispatcher",
            tenant_id="tenant-1",
            role=UserRole.DISPATCHER,
            jti="test-jti",
            session_id="test-session",
        )

        payload = BulkJobCancellationRequest(
            job_ids=[101, 102, 101],
            reason="Dispatcher cancelled selected jobs",
        )

        result = bulk_cancel_jobs(
            payload=payload,
            request=None,
            current_user=user,
            db=db,
        )

        assert result.status == "success"
        assert result.total_requested == 2
        assert result.total_cancelled == 2
        assert len(result.results) == 2

        db.refresh(job1)
        db.refresh(job2)

        assert job1.status == "CANCELLED"
        assert job2.status == "CANCELLED"

    finally:
        db.close()


def test_bulk_cancel_invalid_transition():
    from app.routes.jobs import (
        bulk_cancel_jobs,
        BulkJobCancellationRequest,
    )

    db = TestingSessionLocal()

    try:
        job = db.query(Job).filter(Job.id == 101).first()
        assert job is not None

        job.status = "COMPLETED"
        db.commit()

        user = AuthenticatedUser(
            user_id="test-dispatcher",
            tenant_id="tenant-1",
            role=UserRole.DISPATCHER,
            jti="test-jti",
            session_id="test-session",
        )

        payload = BulkJobCancellationRequest(
            job_ids=[101],
            reason="Invalid transition test",
        )

        with pytest.raises(HTTPException) as exc_info:
            bulk_cancel_jobs(
                payload=payload,
                request=None,
                current_user=user,
                db=db,
            )

        assert exc_info.value.status_code == 400

        detail = exc_info.value.detail
        assert detail["error"] == "BULK_CANCELLATION_VALIDATION_FAILED"
        assert detail["errors"][0]["error"] == "INVALID_TRANSITION"

    finally:
        db.close()


def test_bulk_cancel_permission_denied_validation(monkeypatch):
    from app.routes.jobs import (
        bulk_cancel_jobs,
        BulkJobCancellationRequest,
    )
    from app.services.job_status_machine import PermissionDeniedError

    class FakeValidator:
        def validate(self, *args, **kwargs):
            raise PermissionDeniedError(
                "Permission denied",
                required=["dispatcher"],
                actual="dispatcher",
            )

    monkeypatch.setattr(
        "app.services.job_status_machine.TransitionValidator",
        FakeValidator,
    )

    db = TestingSessionLocal()

    try:
        user = AuthenticatedUser(
            user_id="test-dispatcher",
            tenant_id="tenant-1",
            role=UserRole.DISPATCHER,
            jti="test-jti",
            session_id="test-session",
        )

        payload = BulkJobCancellationRequest(
            job_ids=[101],
            reason="Permission validation test",
        )

        with pytest.raises(HTTPException) as exc_info:
            bulk_cancel_jobs(
                payload=payload,
                request=None,
                current_user=user,
                db=db,
            )

        assert exc_info.value.status_code == 400

        detail = exc_info.value.detail
        assert detail["error"] == "BULK_CANCELLATION_VALIDATION_FAILED"
        assert detail["errors"][0]["error"] == "PERMISSION_DENIED"

    finally:
        db.close()


def test_bulk_cancel_generic_validation_failure(monkeypatch):
    from app.routes.jobs import (
        bulk_cancel_jobs,
        BulkJobCancellationRequest,
    )

    class FakeValidator:
        def validate(self, *args, **kwargs):
            raise RuntimeError("forced validation failure")

    monkeypatch.setattr(
        "app.services.job_status_machine.TransitionValidator",
        FakeValidator,
    )

    db = TestingSessionLocal()

    try:
        user = AuthenticatedUser(
            user_id="test-dispatcher",
            tenant_id="tenant-1",
            role=UserRole.DISPATCHER,
            jti="test-jti",
            session_id="test-session",
        )

        payload = BulkJobCancellationRequest(
            job_ids=[101],
            reason="Generic validation test",
        )

        with pytest.raises(HTTPException) as exc_info:
            bulk_cancel_jobs(
                payload=payload,
                request=None,
                current_user=user,
                db=db,
            )

        assert exc_info.value.status_code == 400

        detail = exc_info.value.detail
        assert detail["errors"][0]["error"] == "VALIDATION_FAILED"

    finally:
        db.close()


def _bulk_cancel_fake_user():
    from app.auth.rbac import UserRole

    return AuthenticatedUser(
        user_id="bulk-test-user",
        tenant_id="tenant-1",
        role=UserRole.DISPATCHER,
        jti="bulk-test-jti",
        session_id="bulk-test-session",
    )


class _BulkCancelFakeQuery:
    def __init__(self, jobs=None, first_result=None):
        self.jobs = jobs or []
        self.first_result = first_result

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return self.jobs

    def with_for_update(self):
        return self

    def first(self):
        return self.first_result


class _BulkCancelFakeDB:
    def __init__(self, jobs, locked_results=None, commit_error=None):
        self.jobs = jobs
        self.locked_results = list(locked_results or [])
        self.commit_error = commit_error
        self.query_count = 0
        self.rollback_count = 0

    def query(self, model):
        self.query_count += 1

        # First query = initial tenant-scoped .all()
        if self.query_count == 1:
            return _BulkCancelFakeQuery(jobs=self.jobs)

        # Following queries = .with_for_update().first()
        index = self.query_count - 2

        result = (
            self.locked_results[index]
            if index < len(self.locked_results)
            else None
        )

        return _BulkCancelFakeQuery(first_result=result)

    def commit(self):
        if self.commit_error:
            raise self.commit_error

    def rollback(self):
        self.rollback_count += 1


class _BulkCancelFakeJob:
    def __init__(self, job_id=1):
        self.id = job_id
        self.tenant_id = "tenant-1"
        self.status = "CREATED"
        self.transition_called = False

    def transition(
        self,
        target_status,
        actor_id,
        actor_role,
        reason,
        is_override,
    ):
        self.transition_called = True
        self.status = target_status


def test_bulk_cancel_empty_job_ids():
    
    from app.routes.jobs import bulk_cancel_jobs

    user = _bulk_cancel_fake_user()
    db = _BulkCancelFakeDB([])

    payload = SimpleNamespace(
        job_ids=[],
        reason="Bulk cancellation test",
    )

    with pytest.raises(HTTPException) as exc_info:
        bulk_cancel_jobs(
            payload=payload,
            request=None,
            current_user=user,
            db=db,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "At least one job ID is required"


def test_bulk_cancel_locked_job_missing():
    from app.routes.jobs import bulk_cancel_jobs

    job = _BulkCancelFakeJob(101)

    class PassingValidator:
        def validate(self, *args, **kwargs):
            return None

    monkeypatch_target = "app.services.job_status_machine.TransitionValidator"

    # Patch the class used by the function.
    from unittest.mock import patch

    user = _bulk_cancel_fake_user()

    db = _BulkCancelFakeDB(
        jobs=[job],
        locked_results=[None],
    )

    payload = SimpleNamespace(
        job_ids=[101],
        reason="Duplicate request",
    )

    with patch(monkeypatch_target, PassingValidator):
        with pytest.raises(HTTPException) as exc_info:
            bulk_cancel_jobs(
                payload=payload,
                request=None,
                current_user=user,
                db=db,
            )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Job 101 not found"
    assert db.rollback_count == 1


def test_bulk_cancel_mutation_invalid_transition():
    from app.routes.jobs import bulk_cancel_jobs
    from app.services.job_status_machine import InvalidTransitionError
    from unittest.mock import patch

    job = _BulkCancelFakeJob(101)

    class MutationInvalidValidator:
        def __init__(self):
            self.calls = 0

        def validate(self, *args, **kwargs):
            self.calls += 1

            # First call = initial validation.
            # Second call = locked mutation validation.
            if self.calls == 2:
                raise InvalidTransitionError(
                    "Job cannot be cancelled from current status",
                    "EN_ROUTE",
                    "CANCELLED",
                )

    user = _bulk_cancel_fake_user()

    db = _BulkCancelFakeDB(
        jobs=[job],
        locked_results=[job],
    )

    payload = SimpleNamespace(
        job_ids=[101],
        reason="Cancellation requested",
    )

    with patch(
        "app.services.job_status_machine.TransitionValidator",
        MutationInvalidValidator,
    ):
        with pytest.raises(HTTPException) as exc_info:
            bulk_cancel_jobs(
                payload=payload,
                request=None,
                current_user=user,
                db=db,
            )

    assert exc_info.value.status_code == 400
    assert db.rollback_count == 1


def test_bulk_cancel_mutation_permission_denied():
    from app.routes.jobs import bulk_cancel_jobs
    from app.services.job_status_machine import PermissionDeniedError
    from unittest.mock import patch

    job = _BulkCancelFakeJob(101)

    class MutationPermissionValidator:
        def __init__(self):
            self.calls = 0

        def validate(self, *args, **kwargs):
            self.calls += 1

            if self.calls == 2:
                raise PermissionDeniedError(
                    "Dispatcher is not allowed to cancel this job",
                    required=["admin"],
                    actual="dispatcher",
                )

    user = _bulk_cancel_fake_user()

    db = _BulkCancelFakeDB(
        jobs=[job],
        locked_results=[job],
    )

    payload = SimpleNamespace(
        job_ids=[101],
        reason="Permission test",
    )

    with patch(
        "app.services.job_status_machine.TransitionValidator",
        MutationPermissionValidator,
    ):
        with pytest.raises(HTTPException) as exc_info:
            bulk_cancel_jobs(
                payload=payload,
                request=None,
                current_user=user,
                db=db,
            )

    assert exc_info.value.status_code == 403
    assert db.rollback_count == 1


def test_bulk_cancel_mutation_http_exception():
    from app.routes.jobs import bulk_cancel_jobs
    from unittest.mock import patch

    job = _BulkCancelFakeJob(101)

    class PassingValidator:
        def validate(self, *args, **kwargs):
            return None

    user = _bulk_cancel_fake_user()

    # Initial validation sees the job.
    # Mutation phase cannot find it.
    db = _BulkCancelFakeDB(
        jobs=[job],
        locked_results=[None],
    )

    payload = SimpleNamespace(
        job_ids=[101],
        reason="Job disappeared",
    )

    with patch(
        "app.services.job_status_machine.TransitionValidator",
        PassingValidator,
    ):
        with pytest.raises(HTTPException) as exc_info:
            bulk_cancel_jobs(
                payload=payload,
                request=None,
                current_user=user,
                db=db,
            )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Job 101 not found"
    assert db.rollback_count == 1


def test_bulk_cancel_mutation_generic_exception():
    from app.routes.jobs import bulk_cancel_jobs
    from unittest.mock import patch

    class GenericFailJob(_BulkCancelFakeJob):
        def transition(
            self,
            target_status,
            actor_id,
            actor_role,
            reason,
            is_override,
        ):
            raise RuntimeError("Unexpected transition failure")

    job = GenericFailJob(101)

    class PassingValidator:
        def validate(self, *args, **kwargs):
            return None

    user = _bulk_cancel_fake_user()

    db = _BulkCancelFakeDB(
        jobs=[job],
        locked_results=[job],
    )

    payload = SimpleNamespace(
        job_ids=[101],
        reason="Generic failure test",
    )

    with patch(
        "app.services.job_status_machine.TransitionValidator",
        PassingValidator,
    ):
        with pytest.raises(HTTPException) as exc_info:
            bulk_cancel_jobs(
                payload=payload,
                request=None,
                current_user=user,
                db=db,
            )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Bulk cancellation failed"
    assert db.rollback_count == 1