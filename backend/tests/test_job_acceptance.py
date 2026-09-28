import pytest

from datetime import datetime, timezone, timedelta

from fastapi.testclient import TestClient
from fastapi import Header

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.models import Job, Technician, AuditEvent
from app.database import Base, get_db
from app.redis_client import get_redis_client
from app.auth.dependencies import (
    get_current_user,
    AuthenticatedUser,
)
from app.auth.rbac import UserRole


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


# ============================================================
# DATABASE OVERRIDE
# ============================================================

def override_get_db():
    db = TestingSessionLocal()

    try:
        yield db
    finally:
        db.close()


# ============================================================
# MOCK REDIS
# ============================================================

class MockRedis:

    def __init__(self):
        self.data = {}

    def set(self, key, value, nx=False, ex=None):
        """
        Supports the Redis usage in accept_job():

            redis_client.set(
                lock_key,
                "locked",
                nx=True,
                ex=10,
            )
        """

        if nx and key in self.data:
            return False

        self.data[key] = value
        return True

    def exists(self, key):
        return key in self.data

    def delete(self, *keys):
        deleted = 0

        for key in keys:
            if key in self.data:
                del self.data[key]
                deleted += 1
        return deleted

    def expire(self, key, seconds):
        return key in self.data

    def incr(self, key):
        self.data[key] = int(self.data.get(key, 0)) + 1
        return self.data[key]

    def get(self, key):
        return self.data.get(key)

    def flushall(self):
        self.data.clear()


mock_redis = MockRedis()


def override_get_redis():
    return mock_redis


# ============================================================
# CURRENT USER OVERRIDE
# ============================================================

async def override_current_user(
    authorization: str = Header(None),
):
    token = (
        authorization.replace("Bearer ", "")
        if authorization
        else ""
    )

    return AuthenticatedUser(
        user_id=token,
        tenant_id="tenant-1",
        role=UserRole.TECHNICIAN,
        jti="test-jti",
    )


# ============================================================
# TEST CLIENT
# ============================================================

client = TestClient(app)


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture(autouse=True)
def setup_db():

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()

    # Clean database
    db.query(AuditEvent).delete()
    db.query(Job).delete()
    db.query(Technician).delete()
    db.commit()

    # Reset Redis
    mock_redis.flushall()

    yield db

    db.close()


@pytest.fixture(autouse=True)
def apply_overrides():

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis_client] = override_get_redis
    app.dependency_overrides[get_current_user] = override_current_user

    yield

    app.dependency_overrides.clear()


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def create_technician(
    db,
    tech_id="tech-123",
    status="AVAILABLE",
):
    """
    Create a technician that can be resolved by:

        Authorization: Bearer <tech_id>
    """

    technician = Technician(
        tech_id=tech_id,
        technician_name="John Doe",
        technician_skill="Plumbing",
        technician_location="0,0",
        technician_status=status,
        current_jobs=0,
        tenant_id="tenant-1",
    )

    db.add(technician)
    db.commit()
    db.refresh(technician)

    return technician


def create_assigned_job(
    db,
    technician,
    assigned_at=None,
    status="ASSIGNED",
):
    """
    Create an assigned job.

    The current accept endpoint requires assigned_at
    before it will proceed to the acceptance window.
    """

    if assigned_at is None:
        assigned_at = datetime.now(timezone.utc)

    job = Job(
        customer_name="Alice",
        location="1,1",
        issue_description="Leak",
        priority="HIGH",
        service_type="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now(
            timezone.utc
        ).date(),
        status=status,
        assigned_technician_id=technician.technician_id,
        assigned_at=assigned_at,
        tenant_id="tenant-1",
    )

    db.add(job)
    db.commit()
    db.refresh(job)

    return job


def accept_job(job_id, tech_id="tech-123"):
    return client.post(
        f"/jobs/{job_id}/accept",
        headers={
            "Authorization": f"Bearer {tech_id}",
            "X-Tenant-ID": "tenant-1",
        },
    )


# ============================================================
# 1. SUCCESSFUL ACCEPTANCE
# ============================================================

def test_accept_succeeds_for_valid_assigned_job(setup_db):

    db = setup_db

    tech = create_technician(
        db,
        tech_id="tech-123",
    )

    job = create_assigned_job(
        db,
        tech,
        assigned_at=datetime.now(timezone.utc),
    )

    # Acceptance timer exists
    mock_redis.set(
        f"job:timer:{job.id}",
        "1",
    )

    response = accept_job(
        job.id,
        "tech-123",
    )

    print("STATUS:", response.status_code)
    print("RESPONSE:", response.text)

    # --------------------------------------------------------
    # HTTP
    # --------------------------------------------------------

    assert response.status_code == 200

    data = response.json()

    # --------------------------------------------------------
    # Current endpoint behavior
    # --------------------------------------------------------

    assert data["status"] == "ACCEPTED"

    assert data["previous_status"] == "ASSIGNED"

    assert data["technician"]["tech_id"] == "tech-123"

    assert data["technician"]["status"] == "AVAILABLE"

    # Accepting does NOT start tracking.
    assert data["tracking_enabled"] is False

    # --------------------------------------------------------
    # Database
    # --------------------------------------------------------

    db.refresh(job)
    db.refresh(tech)

    assert job.status == "ACCEPTED"

    assert tech.technician_status == "AVAILABLE"

    # Accepting does NOT increment active jobs.
    assert tech.current_jobs == 0

    # --------------------------------------------------------
    # Timer
    # --------------------------------------------------------

    assert (
        mock_redis.exists(
            f"job:timer:{job.id}"
        )
        is False
    )

    # --------------------------------------------------------
    # Audit
    # --------------------------------------------------------

    audit = (
        db.query(AuditEvent)
        .filter(
            AuditEvent.tech_id == "tech-123",
            AuditEvent.event_type == "JOB_ACCEPTED",
        )
        .first()
    )

    assert audit is not None

    assert audit.old_status == "ASSIGNED"

    assert audit.new_status == "ACCEPTED"


# ============================================================
# 2. JOB NOT FOUND
# ============================================================

def test_accept_404_job_not_found(setup_db):

    db = setup_db

    # IMPORTANT:
    #
    # The endpoint resolves the technician BEFORE
    # looking up the job.
    #
    # Therefore a technician must exist even though
    # the job does not exist.

    create_technician(
        db,
        tech_id="tech-123",
    )

    response = accept_job(
        999,
        "tech-123",
    )

    assert response.status_code == 404

    assert response.json()["detail"] == "Job not found"


# ============================================================
# 3. JOB NOT IN ASSIGNED STATUS
# ============================================================

def test_accept_400_not_assigned_status(setup_db):

    db = setup_db

    tech = create_technician(
        db,
        tech_id="tech-123",
    )

    job = Job(
        customer_name="Alice",
        location="1,1",
        issue_description="Leak",
        priority="HIGH",
        service_type="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now(
            timezone.utc
        ).date(),
        status="QUEUED",
        assigned_technician_id=tech.technician_id,
        tenant_id="tenant-1",
    )

    db.add(job)
    db.commit()
    db.refresh(job)

    response = accept_job(
        job.id,
        "tech-123",
    )

    assert response.status_code == 400

    assert (
        response.json()["detail"]
        == "Job is not available for acceptance: QUEUED"
    )


# ============================================================
# 4. WRONG TECHNICIAN
# ============================================================

def test_accept_403_wrong_technician(setup_db):

    db = setup_db

    assigned_tech = create_technician(
        db,
        tech_id="tech-123",
    )

    create_technician(
        db,
        tech_id="wrong-tech",
    )

    job = create_assigned_job(
        db,
        assigned_tech,
        assigned_at=datetime.now(timezone.utc),
    )

    response = accept_job(
        job.id,
        "wrong-tech",
    )

    assert response.status_code == 403

    assert (
        response.json()["detail"]
        == "Technician not assigned to this job"
    )


# ============================================================
# 5. ACCEPTANCE WINDOW EXPIRED
# ============================================================

def test_accept_423_expired_window(setup_db):

    db = setup_db

    tech = create_technician(
        db,
        tech_id="tech-123",
    )

    # More than 10 minutes old.
    expired_assignment_time = (
        datetime.now(timezone.utc)
        - timedelta(minutes=11)
    )

    job = create_assigned_job(
        db,
        tech,
        assigned_at=expired_assignment_time,
    )

    # Intentionally DO NOT create the timer.
    #
    # The current endpoint determines expiry from
    # job.assigned_at, not merely from Redis timer existence.

    response = accept_job(
        job.id,
        "tech-123",
    )

    assert response.status_code == 423

    assert (
        response.json()["detail"]
        == "Acceptance window expired"
    )

    # The expired timer should be cancelled if present.
    assert (
        mock_redis.exists(
            f"job:timer:{job.id}"
        )
        is False
    )


# ============================================================
# 6. CONCURRENT MODIFICATION
# ============================================================

def test_accept_409_concurrent_modification(setup_db):

    db = setup_db

    tech = create_technician(
        db,
        tech_id="tech-123",
    )

    # Recent assignment so it is NOT expired.
    job = create_assigned_job(
        db,
        tech,
        assigned_at=datetime.now(timezone.utc),
    )

    # Acceptance timer exists.
    mock_redis.set(
        f"job:timer:{job.id}",
        "1",
    )

    # Simulate another request already holding
    # the acceptance lock.
    lock_key = (
        f"lock:job_accept:"
        f"tenant-1:"
        f"{job.id}"
    )

    mock_redis.set(
        lock_key,
        "locked",
        nx=True,
        ex=10,
    )

    response = accept_job(
        job.id,
        "tech-123",
    )

    assert response.status_code == 409

    assert (
        response.json()["detail"]
        == "Concurrent modification"
    )


# ============================================================
# 7. MISSING ASSIGNMENT TIMESTAMP
# ============================================================

def test_accept_409_missing_assignment_timestamp(
    setup_db,
):

    db = setup_db

    tech = create_technician(
        db,
        tech_id="tech-123",
    )

    job = Job(
        customer_name="Alice",
        location="1,1",
        issue_description="Leak",
        priority="HIGH",
        service_type="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now(
            timezone.utc
        ).date(),
        status="ASSIGNED",
        assigned_technician_id=tech.technician_id,
        tenant_id="tenant-1",

        # Intentionally missing.
        assigned_at=None,
    )

    db.add(job)
    db.commit()
    db.refresh(job)

    response = accept_job(
        job.id,
        "tech-123",
    )

    assert response.status_code == 409

    assert (
        response.json()["detail"]
        == "Assignment timestamp is missing"
    )


# ============================================================
# 8. JOB STATUS IS CASE INSENSITIVE
# ============================================================

def test_accept_rejects_non_assigned_status(
    setup_db,
):

    db = setup_db

    tech = create_technician(
        db,
        tech_id="tech-123",
    )

    job = Job(
        customer_name="Alice",
        location="1,1",
        issue_description="Leak",
        priority="HIGH",
        service_type="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now(
            timezone.utc
        ).date(),
        status="ACCEPTED",
        assigned_technician_id=tech.technician_id,
        tenant_id="tenant-1",
        assigned_at=datetime.now(timezone.utc),
    )

    db.add(job)
    db.commit()
    db.refresh(job)

    response = accept_job(
        job.id,
        "tech-123",
    )

    assert response.status_code == 400

    assert (
        response.json()["detail"]
        == "Job is not available for acceptance: ACCEPTED"
    )