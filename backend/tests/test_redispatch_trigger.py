import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from fakeredis import FakeRedis
from contextlib import contextmanager

from app.auth.jwt_handler import create_access_token
from app.auth.dependencies import (
    AuthenticatedUser,
    get_current_user,
    get_current_user_or_tenant,
)
from app.auth.rbac import UserRole

from app.main import app
from app.models import (
    Job,
    Technician,
    AuditEvent,
    DispatcherNotification,
)
from app.models.user import User
from app.database import Base, get_db
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.redis_client import get_redis_client
from app.services.re_dispatch_trigger import ReDispatchTriggerService
from app.services.re_dispatch_queue import ReDispatchQueueService


# ============================================================
# Test Database
# ============================================================

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_redispatch.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
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
# Fake Redis
# ============================================================

fake_redis = FakeRedis(decode_responses=True)


def override_get_redis():
    return fake_redis


# ============================================================
# Mock Job Lock
# ============================================================

@contextmanager
def dummy_job_lock(*args, **kwargs):
    yield "dummy_lock"


# ============================================================
# Dependency Overrides
# ============================================================

@pytest.fixture(autouse=True)
def apply_overrides():
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis_client] = override_get_redis

    test_user = AuthenticatedUser(
        user_id="tech-123",
        tenant_id="tenant-1",
        role=UserRole.TECHNICIAN,
        jti="test-jti",
        session_id="test-session",
    )

    def override_current_user():
        return test_user

    def override_current_user_or_tenant():
        return test_user, test_user.tenant_id

    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[get_current_user_or_tenant] = (
        override_current_user_or_tenant
    )

    yield

    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_redis_client, None)
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_user_or_tenant, None)


# ============================================================
# Database Setup
# ============================================================

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()

    # --------------------------------------------------------
    # Cleanup
    # --------------------------------------------------------

    db.query(DispatcherNotification).delete()
    db.query(AuditEvent).delete()
    db.query(Job).delete()
    db.query(Technician).delete()
    db.query(User).delete()

    db.commit()

    # --------------------------------------------------------
    # Create test technician user
    # --------------------------------------------------------

    test_user = User(
        id="tech-123",
        email="tech123@test.com",
        password_hash="test-password",
        first_name="John",
        last_name="Technician",
        role="technician",
        tenant_id="tenant-1",
        is_active=True,
        is_email_verified=True,
    )

    db.add(test_user)
    db.commit()

    # --------------------------------------------------------
    # Reset fake Redis
    # --------------------------------------------------------

    fake_redis.flushall()

    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


# ============================================================
# Tests
# ============================================================

@patch(
    "app.routes.jobs.with_job_lock",
    side_effect=dummy_job_lock,
)
def test_rejection_triggers_redispatch(
    mock_lock,
    setup_db,
):
    db = setup_db

    # --------------------------------------------------------
    # Create technician
    # --------------------------------------------------------

    tech = Technician(
        tech_id="tech-123",
        tenant_id="tenant-1",
        technician_name="John",
        technician_status="BUSY",
        current_jobs=1,
        technician_skill="Plumbing",
        technician_location="0,0",
    )

    db.add(tech)
    db.commit()
    db.refresh(tech)

    # --------------------------------------------------------
    # Create assigned job
    # --------------------------------------------------------

    job = Job(
        tenant_id="tenant-1",
        customer_name="Alice",
        location="1,1",
        issue_description="Leak",
        priority="P4",
        service_type="Plumbing",
        contact_number="123",
        preferred_service_date=datetime.now().date(),
        status="ASSIGNED",
        assigned_technician_id=tech.technician_id,
    )

    db.add(job)
    db.commit()
    db.refresh(job)

    # --------------------------------------------------------
    # Create token
    #
    # The route receives AuthenticatedUser through the
    # dependency override above, so this token is only kept
    # for the request format.
    # --------------------------------------------------------

    token = create_access_token(
        user_id="tech-123",
        tenant_id="tenant-1",
        role="technician",
    )

    response = client.post(
        f"/jobs/{job.id}/reject",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-ID": "tenant-1",
        },
        json={
            "reason": "Customer too far",
        },
    )

    assert response.status_code == 200, response.text

    # --------------------------------------------------------
    # Job should return to queue
    # --------------------------------------------------------

    db.refresh(job)

    assert job.status == "QUEUED"

    # --------------------------------------------------------
    # Check Redis dispatch queue
    # --------------------------------------------------------

    queue_key = "dispatch:queue:tenant-1"

    rank = fake_redis.zrank(
        queue_key,
        str(job.id),
    )

    assert rank is not None


def test_timeout_triggers_redispatch(setup_db):
    db = setup_db

    # --------------------------------------------------------
    # Create technician
    # --------------------------------------------------------

    tech = Technician(
        tech_id="tech-123",
        tenant_id="tenant-1",
        technician_name="John",
        technician_status="AVAILABLE",
        technician_skill="Plumbing",
        technician_location="0,0",
    )

    db.add(tech)
    db.commit()
    db.refresh(tech)

    # --------------------------------------------------------
    # Create assigned job.
    #
    # Make updated_at sufficiently old so it is definitely
    # past the timeout threshold.
    # --------------------------------------------------------

    job = Job(
        tenant_id="tenant-1",
        customer_name="Alice",
        location="1,1",
        issue_description="Leak",
        priority="P4",
        service_type="Plumbing",
        contact_number="123",
        preferred_service_date=datetime.now().date(),
        status="ASSIGNED",
        assigned_technician_id=tech.technician_id,
        updated_at=datetime.now(timezone.utc) - timedelta(seconds=60),
    )

    db.add(job)
    db.commit()
    db.refresh(job)

    # --------------------------------------------------------
    # Simulate missing timer.
    # --------------------------------------------------------

    trigger = ReDispatchTriggerService.detect_trigger(
        job,
        tech,
        timer_exists=False,
        timer_ttl=0,
    )

    assert trigger is not None
    assert trigger["type"] == "trigger"
    assert trigger["reason"] == "timeout"

    # --------------------------------------------------------
    # Simulate valid timer.
    # --------------------------------------------------------

    trigger2 = ReDispatchTriggerService.detect_trigger(
        job,
        tech,
        timer_exists=True,
        timer_ttl=300,
    )

    assert trigger2 is None


def test_offline_triggers_redispatch(setup_db):
    db = setup_db

    # --------------------------------------------------------
    # Create offline technician
    # --------------------------------------------------------

    tech = Technician(
        tech_id="tech-123",
        tenant_id="tenant-1",
        technician_name="John",
        technician_status="OFFLINE",
        technician_skill="Plumbing",
        technician_location="0,0",
    )

    db.add(tech)
    db.commit()
    db.refresh(tech)

    # --------------------------------------------------------
    # Create assigned job
    # --------------------------------------------------------

    job = Job(
        tenant_id="tenant-1",
        customer_name="Alice",
        location="1,1",
        issue_description="Leak",
        priority="P1",
        service_type="Plumbing",
        contact_number="123",
        preferred_service_date=datetime.now().date(),
        status="ASSIGNED",
        assigned_technician_id=tech.technician_id,
    )

    db.add(job)
    db.commit()
    db.refresh(job)

    # --------------------------------------------------------
    # Offline trigger
    # --------------------------------------------------------

    trigger = ReDispatchTriggerService.detect_trigger(
        job,
        tech,
        timer_exists=True,
        timer_ttl=300,
    )

    assert trigger is not None
    assert trigger["type"] == "trigger"
    assert trigger["reason"] == "tech_offline"


def test_status_assigned_to_queued(setup_db):
    db = setup_db

    job = Job(
        tenant_id="tenant-1",
        customer_name="Alice",
        location="1,1",
        issue_description="Leak",
        priority="P4",
        service_type="Plumbing",
        contact_number="123",
        preferred_service_date=datetime.now().date(),
        status="ASSIGNED",
    )

    db.add(job)
    db.commit()
    db.refresh(job)

    ReDispatchQueueService.enqueue_failed_job(
        db,
        fake_redis,
        job,
        "tenant-1",
        "Test",
    )

    db.refresh(job)

    assert job.status == "QUEUED"


def test_priority_bump_applied(setup_db):
    db = setup_db

    job = Job(
        tenant_id="tenant-1",
        customer_name="Alice",
        location="1,1",
        issue_description="Leak",
        priority="P4",
        service_type="Plumbing",
        contact_number="123",
        preferred_service_date=datetime.now().date(),
        status="ASSIGNED",
    )

    db.add(job)
    db.commit()
    db.refresh(job)

    ReDispatchQueueService.enqueue_failed_job(
        db,
        fake_redis,
        job,
        "tenant-1",
        "Test failure",
    )

    db.refresh(job)

    assert job.status == "QUEUED"
    assert job.priority == "P3"
    assert job.previous_priority == "P4"
    assert job.bumped_at is not None


def test_attempt_count_incremented(setup_db):
    db = setup_db

    job = Job(
        tenant_id="tenant-1",
        customer_name="Alice",
        location="1,1",
        issue_description="Leak",
        priority="P4",
        service_type="Plumbing",
        contact_number="123",
        preferred_service_date=datetime.now().date(),
        status="ASSIGNED",
        attempt_count=2,
    )

    db.add(job)
    db.commit()
    db.refresh(job)

    ReDispatchQueueService.enqueue_failed_job(
        db,
        fake_redis,
        job,
        "tenant-1",
        "Failure",
    )

    db.refresh(job)

    assert job.attempt_count == 3


def test_queue_position_by_priority(setup_db):
    db = setup_db

    # --------------------------------------------------------
    # Create jobs with identical timestamps but different
    # priorities.
    # --------------------------------------------------------

    base_time = datetime(
        2026,
        1,
        1,
        12,
        0,
        0,
        tzinfo=timezone.utc,
    )

    jobs = [
        Job(
            tenant_id="tenant-1",
            priority="P3",
            status="ASSIGNED",
            created_at=base_time,
            customer_name="N",
            location="L",
            issue_description="I",
            service_type="T",
            contact_number="1",
            preferred_service_date=base_time.date(),
        ),
        Job(
            tenant_id="tenant-1",
            priority="P1",
            status="ASSIGNED",
            created_at=base_time,
            customer_name="N",
            location="L",
            issue_description="I",
            service_type="T",
            contact_number="1",
            preferred_service_date=base_time.date(),
        ),
        Job(
            tenant_id="tenant-1",
            priority="P2",
            status="ASSIGNED",
            created_at=base_time,
            customer_name="N",
            location="L",
            issue_description="I",
            service_type="T",
            contact_number="1",
            preferred_service_date=base_time.date(),
        ),
    ]

    db.add_all(jobs)
    db.commit()

    for job in jobs:
        ReDispatchQueueService.enqueue_failed_job(
            db,
            fake_redis,
            job,
            "tenant-1",
            "Reason",
        )

    queue_key = "dispatch:queue:tenant-1"

    queued_ids = fake_redis.zrevrange(
        queue_key,
        0,
        -1,
    )

    db.refresh(jobs[0])
    db.refresh(jobs[1])
    db.refresh(jobs[2])

    assert str(jobs[1].id) == queued_ids[0]


def test_no_trigger_for_accepted(setup_db):
    db = setup_db

    # --------------------------------------------------------
    # Create technician who is already en route.
    # --------------------------------------------------------

    tech = Technician(
        tech_id="tech-123",
        tenant_id="tenant-1",
        technician_name="John",
        technician_status="EN_ROUTE",
        technician_skill="Plumbing",
        technician_location="0,0",
    )

    db.add(tech)
    db.commit()
    db.refresh(tech)

    # --------------------------------------------------------
    # Create EN_ROUTE job
    # --------------------------------------------------------

    job = Job(
        tenant_id="tenant-1",
        customer_name="Alice",
        location="1,1",
        issue_description="Leak",
        priority="P4",
        service_type="Plumbing",
        contact_number="123",
        preferred_service_date=datetime.now().date(),
        status="EN_ROUTE",
        assigned_technician_id=tech.technician_id,
    )

    db.add(job)
    db.commit()
    db.refresh(job)

    # --------------------------------------------------------
    # No redispatch trigger should occur.
    # --------------------------------------------------------

    trigger = ReDispatchTriggerService.detect_trigger(
        job,
        tech,
        timer_exists=False,
        timer_ttl=0,
    )

    assert trigger is None