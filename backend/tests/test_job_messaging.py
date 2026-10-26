import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi import HTTPException

from app.auth.dependencies import AuthenticatedUser
from app.auth.rbac import UserRole
from app.database import Base
from app.models import Job, Organization, ServiceRequest, Technician
from app.models.job_message import JobMessage
from app.models.technician_profile import TechnicianProfile
from app.models.user import User
from app.routes import job_messaging


@pytest.fixture
def messaging_db(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    tables = [Organization.__table__, User.__table__, Technician.__table__, Job.__table__, ServiceRequest.__table__, TechnicianProfile.__table__, JobMessage.__table__]
    Base.metadata.create_all(engine, tables=tables)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    db = factory()
    monkeypatch.setattr(job_messaging.sio, "emit", AsyncMock())
    yield db
    db.close()
    Base.metadata.drop_all(engine, tables=list(reversed(tables)))
    engine.dispose()


def _user(user_id, tenant_id, role):
    return AuthenticatedUser(user_id=user_id, tenant_id=tenant_id, role=UserRole(role), jti="test", session_id="session")


def _seed(db, *, job_status="IN_PROGRESS", assigned=True, customer_tenant="customer-tenant", job_tenant="provider-tenant", technician_id=11):
    for tenant_id, name in (("customer-tenant", "Customer tenant"), ("provider-tenant", "Provider tenant")):
        if not db.query(Organization).filter(Organization.id == tenant_id).first():
            db.add(Organization(id=tenant_id, name=name, slug=tenant_id))
    db.flush()
    if not db.query(User).filter(User.id == "customer-1").first():
        db.add(User(id="customer-1", tenant_id=customer_tenant, role="customer", email="customer@example.test", password_hash="x", first_name="Casey", last_name="Customer", is_active=True, is_email_verified=True))
    if not db.query(User).filter(User.id == "tech-1").first():
        db.add(User(id="tech-1", tenant_id="provider-tenant", role="technician", email="tech@example.test", password_hash="x", first_name="Terry", last_name="Tech", is_active=True, is_email_verified=True))
    db.flush()
    if not db.query(Technician).filter(Technician.technician_id == technician_id).first():
        technician = Technician(technician_id=technician_id, tech_id="tech-1", tenant_id="provider-tenant", technician_name="Terry Tech", technician_skill="HVAC", technician_location="Austin")
        db.add(technician)
    previous_job = db.query(Job.id).order_by(Job.id.desc()).first()
    job_id = (previous_job[0] + 1) if previous_job else 100
    job = Job(id=job_id, tenant_id=job_tenant, customer_tenant_id=customer_tenant, customer_name="Casey Customer", location="1 Main Street", issue_description="Repair", priority="MEDIUM", service_type="HVAC", contact_number="555", preferred_service_date=date(2026, 10, 23), status=job_status, assigned_technician_id=technician_id if assigned else None, customer_id="customer-1")
    db.add(job)
    db.add(ServiceRequest(request_number=f"REQ-{job_id}", customer_user_id="customer-1", tenant_id=customer_tenant, title="Repair", description="Repair", status=job_status, linked_job_id=job.id))
    db.commit()
    return job


def test_customer_and_current_technician_exchange_persisted_messages(messaging_db):
    job = _seed(messaging_db)
    customer = _user("customer-1", "customer-tenant", "customer")
    tech = _user("tech-1", "provider-tenant", "technician")
    sent = asyncio.run(job_messaging.send_job_message(job.id, job_messaging.MessageCreate(body="I am on my way"), tech, messaging_db))
    assert sent["body"] == "I am on my way"
    delivered = asyncio.run(job_messaging.acknowledge_delivery(job.id, sent["id"], customer, messaging_db))
    assert delivered["delivered_at"]
    reply = asyncio.run(job_messaging.send_job_message(job.id, job_messaging.MessageCreate(body="Thank you"), customer, messaging_db))
    assert reply["body"] == "Thank you"
    assert messaging_db.query(JobMessage).filter(JobMessage.job_id == job.id).count() == 2
    assert job_messaging.sio.emit.await_count == 3


def test_history_is_separate_per_job_and_offline_unread_is_confirmed(messaging_db):
    first = _seed(messaging_db, technician_id=11)
    second = _seed(messaging_db, technician_id=11)
    tech = _user("tech-1", "provider-tenant", "technician")
    customer = _user("customer-1", "customer-tenant", "customer")
    asyncio.run(job_messaging.send_job_message(first.id, job_messaging.MessageCreate(body="For first job"), tech, messaging_db))
    asyncio.run(job_messaging.send_job_message(second.id, job_messaging.MessageCreate(body="For second job"), tech, messaging_db))
    counts = job_messaging.get_unread_count(first.id, customer, messaging_db)
    assert counts["unread_count"] == 1
    history = asyncio.run(job_messaging.get_job_messages(first.id, customer, messaging_db))
    assert [message["body"] for message in history["messages"]] == ["For first job"]
    assert job_messaging.get_unread_count(first.id, customer, messaging_db)["unread_count"] == 0


def test_unassigned_job_does_not_create_chat_and_terminal_jobs_are_read_only(messaging_db):
    queued = _seed(messaging_db, job_status="QUEUED", assigned=False, technician_id=11)
    customer = _user("customer-1", "customer-tenant", "customer")
    history = asyncio.run(job_messaging.get_job_messages(queued.id, customer, messaging_db))
    assert history["can_send"] is False
    assert "assignment" in history["read_only_reason"].lower()
    with pytest.raises(HTTPException) as queued_error:
        asyncio.run(job_messaging.send_job_message(queued.id, job_messaging.MessageCreate(body="Hi"), customer, messaging_db))
    assert queued_error.value.status_code == 409
    assert messaging_db.query(JobMessage).count() == 0

    completed = _seed(messaging_db, job_status="COMPLETED", technician_id=11)
    messaging_db.add(JobMessage(job_id=completed.id, tenant_id=completed.tenant_id, sender_user_id="customer-1", sender_role="CUSTOMER", body="Saved before completion"))
    messaging_db.commit()
    with pytest.raises(HTTPException) as completed_error:
        asyncio.run(job_messaging.send_job_message(completed.id, job_messaging.MessageCreate(body="Hi"), customer, messaging_db))
    assert completed_error.value.status_code == 409
    completed_history = asyncio.run(job_messaging.get_job_messages(completed.id, customer, messaging_db))
    assert completed_history["can_send"] is False
    assert [message["body"] for message in completed_history["messages"]] == ["Saved before completion"]

    cancelled = _seed(messaging_db, job_status="CANCELLED", technician_id=11)
    messaging_db.add(JobMessage(job_id=cancelled.id, tenant_id=cancelled.tenant_id, sender_user_id="customer-1", sender_role="CUSTOMER", body="Saved before cancellation"))
    messaging_db.commit()
    with pytest.raises(HTTPException):
        asyncio.run(job_messaging.send_job_message(cancelled.id, job_messaging.MessageCreate(body="Hi"), customer, messaging_db))
    cancelled_history = asyncio.run(job_messaging.get_job_messages(cancelled.id, customer, messaging_db))
    assert [message["body"] for message in cancelled_history["messages"]] == ["Saved before cancellation"]


def test_reassignment_revokes_previous_technician_and_cross_tenant_access(messaging_db):
    job = _seed(messaging_db, technician_id=11)
    previous = _user("tech-1", "provider-tenant", "technician")
    customer = _user("customer-1", "customer-tenant", "customer")
    asyncio.run(job_messaging.send_job_message(job.id, job_messaging.MessageCreate(body="Assignment context"), customer, messaging_db))
    second_user = User(id="tech-2", tenant_id="provider-tenant", role="technician", email="tech2@example.test", password_hash="x", first_name="New", last_name="Tech", is_active=True, is_email_verified=True)
    second_tech = Technician(technician_id=22, tech_id="tech-2", tenant_id="provider-tenant", technician_name="New Tech", technician_skill="HVAC", technician_location="Austin")
    messaging_db.add_all([second_user, second_tech]); messaging_db.commit()
    job.assigned_technician_id = 22; messaging_db.commit()
    with pytest.raises(HTTPException) as reassigned:
        asyncio.run(job_messaging.get_job_messages(job.id, previous, messaging_db))
    assert reassigned.value.status_code == 404
    current = _user("tech-2", "provider-tenant", "technician")
    reassigned_history = asyncio.run(job_messaging.get_job_messages(job.id, current, messaging_db))
    assert [message["body"] for message in reassigned_history["messages"]] == ["Assignment context"]

    attacker = _user("other-customer", "customer-tenant", "customer")
    with pytest.raises(HTTPException) as denied:
        asyncio.run(job_messaging.get_job_messages(job.id, attacker, messaging_db))
    assert denied.value.status_code == 404
    wrong_tenant = _user("customer-1", "other-tenant", "customer")
    with pytest.raises(HTTPException):
        asyncio.run(job_messaging.get_job_messages(job.id, wrong_tenant, messaging_db))
