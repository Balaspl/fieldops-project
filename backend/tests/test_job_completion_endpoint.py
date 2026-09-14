import pytest
from datetime import date
from unittest.mock import patch
from app.services.job_status_machine import SideEffectError
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.dependencies import get_current_user, AuthenticatedUser
from app.auth.rbac import UserRole
from app.database import Base, get_db
from app.main import app
from app.models import AuditEvent, Job, JobClosure, Technician
from app.redis_client import get_redis_client


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


_current_user = AuthenticatedUser(
    user_id="tech-123",
    tenant_id="tenant-1",
    role=UserRole.TECHNICIAN,
    jti="test-jti",
)


async def override_current_user():
    return _current_user


class MockRedis:
    def publish(self, channel, message):
        return 1


mock_redis = MockRedis()


def override_get_redis():
    return mock_redis


client = TestClient(app)


def _set_user(user_id="tech-123", tenant_id="tenant-1", role=UserRole.TECHNICIAN):
    global _current_user
    _current_user = AuthenticatedUser(
        user_id=user_id,
        tenant_id=tenant_id,
        role=role,
        jti="test-jti",
    )


def _create_tech_and_job(
    db,
    *,
    tech_id="tech-123",
    tenant_id="tenant-1",
    status="ON_SITE",
):
    tech = Technician(
        tech_id=tech_id,
        technician_name="John Tech",
        technician_skill="HVAC",
        technician_location="Zone 1",
        technician_status="BUSY",
        current_jobs=1,
        tenant_id=tenant_id,
    )
    db.add(tech)
    db.commit()
    db.refresh(tech)

    job = Job(
        customer_name="Test Customer",
        location="123 Test St",
        issue_description="AC Breakdown",
        priority="HIGH",
        service_type="HVAC_REPAIR",
        contact_number="1234567890",
        preferred_service_date=date.today(),
        status=status,
        assigned_technician_id=tech.technician_id,
        tenant_id=tenant_id,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return tech, job


@pytest.fixture(autouse=True)
def setup_db_and_overrides():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    _set_user()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[get_redis_client] = override_get_redis

    yield

    app.dependency_overrides.clear()


def completion_payload():
    return {
        "work_summary": "Replaced faulty capacitor and completed repair.",
        "before_images": ["/uploads/before.jpg"],
        "after_images": ["/uploads/after.jpg"],
        "labour_cost": 150.0,
        "material_cost": 75.5,
    }


def test_close_endpoint_succeeds_for_assigned_technician():
    db = TestingSessionLocal()
    tech, job = _create_tech_and_job(db)
    tech_id = tech.tech_id
    job_id = job.id
    db.close()

    with patch("app.services.event_publisher.publish_dispatch_event") as publish_event:
        response = client.post(
            f"/jobs/{job_id}/close",
            json=completion_payload(),
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == job_id
    assert data["technician_id"] == tech_id
    assert data["work_summary"] == completion_payload()["work_summary"]
    assert data["subtotal"] == 225.5
    assert data["completed_at"]
    assert publish_event.called

    db = TestingSessionLocal()
    updated_job = db.query(Job).filter(Job.id == job_id).one()
    closure = db.query(JobClosure).filter(JobClosure.job_id == job_id).one()
    audit = db.query(AuditEvent).filter(
        AuditEvent.job_id == str(job_id),
        AuditEvent.event_type == "JOB_COMPLETED",
    ).one()

    assert updated_job.status == "COMPLETED"
    assert updated_job.completed_by == tech_id
    assert closure.id == data["id"]
    assert audit.old_status == "ON_SITE"
    assert audit.new_status == "COMPLETED"
    assert audit.tech_id == tech_id
    db.close()


def test_close_endpoint_rejects_wrong_technician_with_403():
    db = TestingSessionLocal()
    _, job = _create_tech_and_job(db)
    job_id = job.id

    wrong_tech = Technician(
        tech_id="wrong-tech",
        technician_name="Wrong Tech",
        technician_skill="HVAC",
        technician_location="Zone 2",
        technician_status="AVAILABLE",
        current_jobs=0,
        tenant_id="tenant-1",
    )
    db.add(wrong_tech)
    db.commit()
    db.close()

    _set_user(user_id="wrong-tech")
    response = client.post(
        f"/jobs/{job_id}/close",
        json=completion_payload(),
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "This job is not assigned to you"


def test_close_endpoint_returns_404_for_unknown_job():
    response = client.post(
        "/jobs/999999/close",
        json=completion_payload(),
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found"


def test_close_endpoint_returns_404_for_cross_tenant_job():
    db = TestingSessionLocal()
    _, job = _create_tech_and_job(db, tenant_id="tenant-2")
    job_id = job.id

    user_tech = Technician(
        tech_id="tenant-1-tech",
        technician_name="Tenant One Tech",
        technician_skill="HVAC",
        technician_location="Zone 1",
        technician_status="AVAILABLE",
        current_jobs=0,
        tenant_id="tenant-1",
    )
    db.add(user_tech)
    db.commit()
    db.close()

    _set_user(user_id="tenant-1-tech", tenant_id="tenant-1")
    response = client.post(
        f"/jobs/{job_id}/close",
        json=completion_payload(),
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found"


def test_close_endpoint_rejects_non_technician_with_403():
    db = TestingSessionLocal()
    _, job = _create_tech_and_job(db)
    db.close()

    _set_user(user_id="dispatcher-1", role=UserRole.DISPATCHER)
    response = client.post(
        f"/jobs/{job.id}/close",
        json=completion_payload(),
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 403


def test_close_endpoint_rejects_duplicate_completion():
    db = TestingSessionLocal()
    _, job = _create_tech_and_job(db)
    job_id = job.id
    db.close()

    with patch("app.services.event_publisher.publish_dispatch_event"):
        first = client.post(
            f"/jobs/{job_id}/close",
            json=completion_payload(),
            headers={"Authorization": "Bearer test-token"},
        )
    assert first.status_code == 200

    second = client.post(
        f"/jobs/{job.id}/close",
        json=completion_payload(),
        headers={"Authorization": "Bearer test-token"},
    )

    assert second.status_code == 400


def test_close_endpoint_validates_payload_before_mutation():
    db = TestingSessionLocal()
    _, job = _create_tech_and_job(db)
    job_id = job.id
    db.close()

    bad_payload = completion_payload()
    bad_payload["after_images"] = []

    response = client.post(
        f"/jobs/{job_id}/close",
        json=bad_payload,
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 400

    db = TestingSessionLocal()
    unchanged_job = db.query(Job).filter(Job.id == job_id).one()
    assert unchanged_job.status == "ON_SITE"
    assert db.query(JobClosure).filter(JobClosure.job_id == job_id).count() == 0
    db.close()


def test_close_endpoint_rejects_invalid_lifecycle_state():
    db = TestingSessionLocal()
    _, job = _create_tech_and_job(db, status="ASSIGNED")
    db.close()

    response = client.post(
        f"/jobs/{job.id}/close",
        json=completion_payload(),
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "INVALID_TRANSITION"
    assert response.json()["detail"]["error_code"] == "FORBIDDEN_JUMP"


def test_close_endpoint_rolls_back_on_database_failure():
    db = TestingSessionLocal()
    tech, job = _create_tech_and_job(db)
    tech_pk = tech.technician_id
    job_id = job.id
    db.close()

    with patch.object(__import__("sqlalchemy.orm", fromlist=["Session"]).Session, "commit", side_effect=Exception("db failure")):
        response = client.post(
            f"/jobs/{job.id}/close",
            json=completion_payload(),
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 500

    db = TestingSessionLocal()
    unchanged_job = db.query(Job).filter(Job.id == job_id).one()
    unchanged_tech = db.query(Technician).filter(Technician.technician_id == tech_pk).one()
    assert unchanged_job.status == "ON_SITE"
    assert unchanged_job.completed_at is None
    assert unchanged_job.completed_by is None
    assert unchanged_tech.current_jobs == 1
    assert unchanged_tech.technician_status == "BUSY"
    assert db.query(JobClosure).filter(JobClosure.job_id == job_id).count() == 0
    assert db.query(AuditEvent).filter(AuditEvent.job_id == str(job_id)).count() == 0
    db.close()


def test_close_endpoint_returns_401_without_authentication():
    app.dependency_overrides.pop(get_current_user, None)

    response = client.post(
        "/jobs/999999/close",
        json=completion_payload(),
    )

    assert response.status_code == 401







def test_close_endpoint_succeeds_when_redis_publish_fails():
    db = TestingSessionLocal()
    _, job = _create_tech_and_job(db)

    job_id = job.id
    db.close()

    with patch(
        "app.services.event_publisher.publish_dispatch_event",
        side_effect=Exception("redis unavailable"),
    ):
        response = client.post(
            f"/jobs/{job_id}/close",
            json=completion_payload(),
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 200

    db = TestingSessionLocal()
    updated_job = db.query(Job).filter(Job.id == job_id).one()
    assert updated_job.status == "COMPLETED"
    assert db.query(JobClosure).filter(
        JobClosure.job_id == job_id
    ).count() == 1
    db.close()


def test_close_endpoint_rolls_back_on_status_side_effect_failure():
    db = TestingSessionLocal()
    _, job = _create_tech_and_job(db)

    job_id = job.id
    db.close()

    with patch(
        "app.services.job_closure_service.transition_job",
        side_effect=SideEffectError("side effect failed"),
    ):
        response = client.post(
            f"/jobs/{job_id}/close",
            json=completion_payload(),
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 400

    db = TestingSessionLocal()
    unchanged_job = db.query(Job).filter(Job.id == job_id).one()
    assert unchanged_job.status == "ON_SITE"
    assert unchanged_job.completed_at is None
    assert unchanged_job.completed_by is None
    assert db.query(JobClosure).filter(
        JobClosure.job_id == job_id
    ).count() == 0
    db.close()