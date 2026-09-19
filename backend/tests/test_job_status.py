import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Setup test DB
SQLALCHEMY_DATABASE_URL = "sqlite://"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Patch app.database.SessionLocal globally before importing components
import app.database
app.database.SessionLocal = TestingSessionLocal

import fakeredis
fake_redis = fakeredis.FakeRedis(decode_responses=True)
import app.redis_client
app.redis_client.get_redis_client = lambda: fake_redis

from app.database import Base
from app.models import Job, Technician
from app.services.job_status_machine import (
    JobStatus,
    InvalidTransitionError,
    PermissionDeniedError,
    ReasonRequiredError,
    SideEffectError,
    register_side_effect,
    clear_registered_side_effects,
)

from unittest.mock import patch

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    clear_registered_side_effects()
    with patch("app.tasks.purge_job_gps_data_task") as mock_purge:
        db = TestingSessionLocal()
        yield db
        db.close()

def test_transition_created_to_assigned_success(setup_db):
    db = setup_db
    job = Job(
        customer_name="Alice",
        location="Zone A",
        issue_description="Leak",
        priority="HIGH",
        service_type="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now().date(),
        status="CREATED"
    )
    db.add(job)
    db.commit()

    # Create dummy technician to assign to
    tech = Technician(
        tech_id="tech-1",
        technician_name="Tech One",
        technician_skill="Plumbing",
        technician_location="Zone A"
    )
    db.add(tech)
    db.commit()
    job.assigned_technician_id = tech.technician_id
    db.commit()

    job.transition(JobStatus.ASSIGNED, actor_id="dispatcher-1", actor_role="dispatcher")
    db.commit()
    assert job.status == "ASSIGNED"
    assert job.assigned_at is not None
    assert job.assigned_by == "dispatcher-1"

def test_transition_created_to_assigned_unauthorized_role(setup_db):
    db = setup_db
    job = Job(
        customer_name="Alice",
        location="Zone A",
        issue_description="Leak",
        priority="HIGH",
        service_type="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now().date(),
        status="CREATED"
    )
    db.add(job)
    db.commit()

    with pytest.raises(PermissionDeniedError):
        job.transition(JobStatus.ASSIGNED, actor_id="tech-1", actor_role="technician")

def test_transition_assigned_to_en_route_success(setup_db):
    db = setup_db
    tech = Technician(
        tech_id="tech-en-route",
        technician_name="Tech ER",
        technician_skill="Plumbing",
        technician_location="Zone A"
    )
    db.add(tech)
    db.commit()
    job = Job(
        customer_name="Alice",
        location="Zone A",
        issue_description="Leak",
        priority="HIGH",
        service_type="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now().date(),
        status="ASSIGNED",
        assigned_technician_id=tech.technician_id
    )
    db.add(job)
    db.commit()

    job.transition(JobStatus.EN_ROUTE, actor_id="tech-1", actor_role="technician")
    db.commit()
    assert job.status == "EN_ROUTE"
    assert job.en_route_at is not None
    assert job.en_route_by == "tech-1"

def test_transition_en_route_to_on_site_success(setup_db):
    db = setup_db
    job = Job(
        customer_name="Alice",
        location="Zone A",
        issue_description="Leak",
        priority="HIGH",
        service_type="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now().date(),
        status="EN_ROUTE",
        gps_active=True
    )
    db.add(job)
    db.commit()

    job.transition(JobStatus.ON_SITE, actor_id="tech-1", actor_role="technician")
    db.commit()
    assert job.status == "ON_SITE"
    assert job.on_site_at is not None
    assert job.on_site_by == "tech-1"

def test_transition_on_site_to_completed_success(setup_db):
    db = setup_db
    job = Job(
        customer_name="Alice",
        location="Zone A",
        issue_description="Leak",
        priority="HIGH",
        service_type="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now().date(),
        status="ON_SITE",
        work_report="Fixed the leak successfully"
    )
    db.add(job)
    db.commit()

    job.transition(JobStatus.COMPLETED, actor_id="tech-1", actor_role="technician")
    db.commit()
    assert job.status == "COMPLETED"
    assert job.completed_at is not None
    assert job.completed_by == "tech-1"

def test_transition_assigned_to_created_success_with_reason(setup_db):
    db = setup_db
    job = Job(
        customer_name="Alice",
        location="Zone A",
        issue_description="Leak",
        priority="HIGH",
        service_type="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now().date(),
        status="ASSIGNED"
    )
    db.add(job)
    db.commit()

    job.transition(JobStatus.CREATED, actor_id="dispatcher-1", actor_role="dispatcher", reason="Tech was delayed")
    db.commit()
    assert job.status == "CREATED"
    assert job.created_at is not None

def test_transition_assigned_to_created_fails_without_reason(setup_db):
    db = setup_db
    job = Job(
        customer_name="Alice",
        location="Zone A",
        issue_description="Leak",
        priority="HIGH",
        service_type="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now().date(),
        status="ASSIGNED"
    )
    db.add(job)
    db.commit()

    with pytest.raises(ReasonRequiredError):
        job.transition(JobStatus.CREATED, actor_id="dispatcher-1", actor_role="dispatcher")

def test_transition_en_route_to_assigned_success_with_reason(setup_db):
    db = setup_db
    job = Job(
        customer_name="Alice",
        location="Zone A",
        issue_description="Leak",
        priority="HIGH",
        service_type="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now().date(),
        status="EN_ROUTE"
    )
    db.add(job)
    db.commit()

    job.transition(JobStatus.ASSIGNED, actor_id="dispatcher-1", actor_role="dispatcher", reason="Return to shop")
    db.commit()
    assert job.status == "ASSIGNED"

def test_transition_any_to_cancelled_success_with_reason(setup_db):
    db = setup_db
    job = Job(
        customer_name="Alice",
        location="Zone A",
        issue_description="Leak",
        priority="HIGH",
        service_type="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now().date(),
        status="ON_SITE"
    )
    db.add(job)
    db.commit()

    job.transition(JobStatus.CANCELLED, actor_id="dispatcher-1", actor_role="dispatcher", reason="Customer cancelled")
    db.commit()
    assert job.status == "CANCELLED"
    assert job.cancelled_at is not None
    assert job.cancellation_reason == "Customer cancelled"

def test_customer_can_cancel_created_job(setup_db):
    db = setup_db

    job = Job(
        customer_name="Alice",
        location="Zone A",
        issue_description="Leak",
        priority="HIGH",
        service_type="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now().date(),
        status="CREATED",
    )

    db.add(job)
    db.commit()

    job.transition(
        JobStatus.CANCELLED,
        actor_id="customer-1",
        actor_role="customer",
        reason="Customer no longer needs the service",
    )
    db.commit()

    assert job.status == "CANCELLED"
    assert job.cancellation_reason == "Customer no longer needs the service"


def test_customer_can_cancel_assigned_job(setup_db):
    db = setup_db

    job = Job(
        customer_name="Alice",
        location="Zone A",
        issue_description="Leak",
        priority="HIGH",
        service_type="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now().date(),
        status="ASSIGNED",
    )

    db.add(job)
    db.commit()

    job.transition(
        JobStatus.CANCELLED,
        actor_id="customer-1",
        actor_role="customer",
        reason="Customer no longer needs the service",
    )
    db.commit()

    assert job.status == "CANCELLED"
    assert job.cancellation_reason == "Customer no longer needs the service"


def test_customer_cannot_cancel_en_route_job(setup_db):
    db = setup_db

    job = Job(
        customer_name="Alice",
        location="Zone A",
        issue_description="Leak",
        priority="HIGH",
        service_type="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now().date(),
        status="EN_ROUTE",
    )

    db.add(job)
    db.commit()

    with pytest.raises(PermissionDeniedError):
        job.transition(
            JobStatus.CANCELLED,
            actor_id="customer-1",
            actor_role="customer",
            reason="Customer wants to cancel",
        )

    assert job.status == "EN_ROUTE"

def test_transition_completed_to_closed_success(setup_db):
    db = setup_db
    job = Job(
        customer_name="Alice",
        location="Zone A",
        issue_description="Leak",
        priority="HIGH",
        service_type="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now().date(),
        status="COMPLETED"
    )
    db.add(job)
    db.commit()

    job.transition(JobStatus.CLOSED, actor_id="system", actor_role="system", reason="Job finished and paid")
    db.commit()
    assert job.status == "CLOSED"
    assert job.closed_at is not None
    assert job.closure_reason == "Job finished and paid"

def test_transition_invalid_jumps(setup_db):
    db = setup_db
    job = Job(
        customer_name="Alice",
        location="Zone A",
        issue_description="Leak",
        priority="HIGH",
        service_type="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now().date(),
        status="CREATED"
    )
    db.add(job)
    db.commit()

    # CREATED -> COMPLETED is invalid jump
    with pytest.raises(InvalidTransitionError) as exc:
        job.transition(JobStatus.COMPLETED, actor_id="tech-1", actor_role="technician")
    assert exc.value.current == "CREATED"
    assert exc.value.target == "COMPLETED"

    # EN_ROUTE -> CREATED is invalid backward transition
    job.status = "EN_ROUTE"
    db.commit()
    with pytest.raises(InvalidTransitionError):
        job.transition(JobStatus.CREATED, actor_id="dispatcher-1", actor_role="dispatcher", reason="reset")

    # COMPLETED -> EN_ROUTE is invalid
    job.status = "COMPLETED"
    db.commit()
    with pytest.raises(InvalidTransitionError):
        job.transition(JobStatus.EN_ROUTE, actor_id="tech-1", actor_role="technician")

    # CANCELLED -> ASSIGNED is invalid (terminal)
    job.status = "CANCELLED"
    db.commit()
    with pytest.raises(InvalidTransitionError):
        job.transition(JobStatus.ASSIGNED, actor_id="dispatcher-1", actor_role="dispatcher")

def test_side_effects_execute_on_transition(setup_db):
    db = setup_db
    job = Job(
        customer_name="Alice",
        location="Zone A",
        issue_description="Leak",
        priority="HIGH",
        service_type="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now().date(),
        status="CREATED"
    )
    db.add(job)
    db.commit()

    calls = []
    def side_effect_mock(j, actor_id, reason):
        calls.append((j.id, actor_id, reason))

    register_side_effect("notify_technician", side_effect_mock)

    job.transition(JobStatus.ASSIGNED, actor_id="dispatcher-1", actor_role="dispatcher")
    db.commit()

    assert len(calls) == 1
    assert calls[0][0] == job.id
    assert calls[0][1] == "dispatcher-1"

def test_side_effect_failure_rolls_back_status_change(setup_db):
    db = setup_db
    job = Job(
        customer_name="Alice",
        location="Zone A",
        issue_description="Leak",
        priority="HIGH",
        service_type="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now().date(),
        status="CREATED"
    )
    db.add(job)
    db.commit()

    def failing_side_effect(j, actor_id, reason):
        raise ValueError("Failed to notify")

    register_side_effect("notify_technician", failing_side_effect)

    with pytest.raises(SideEffectError):
        try:
            job.transition(JobStatus.ASSIGNED, actor_id="dispatcher-1", actor_role="dispatcher")
            db.commit()
        except Exception:
            db.rollback()
            raise

    assert job.status == "CREATED"
    assert job.assigned_at is None


