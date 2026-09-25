"""Ownership and tenant boundaries for customer portal job reads."""

import asyncio
from datetime import date, datetime, timezone

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.dependencies import AuthenticatedUser, require_permission
from app.auth.rbac import Permission, UserRole
from app.database import Base
from app.models import Job, JobClosure, Organization, ServiceRequest
from app.portal_schemas import ServiceRequestUpdate
from app.routes import customer_portal
from app.routes.customer_portal import (
    cancel_service_request,
    download_customer_job_report,
    get_customer_job_detail,
    update_service_request,
    track_customer_jobs,
)


@pytest.fixture
def customer_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[
            Organization.__table__,
            Job.__table__,
            ServiceRequest.__table__,
            JobClosure.__table__,
        ],
    )
    session = sessionmaker(bind=engine)()

    for tenant_id in ("customer-tenant", "provider-tenant", "other-tenant"):
        session.add(
            Organization(
                id=tenant_id,
                name=tenant_id,
                slug=tenant_id,
            )
        )
    session.flush()

    jobs = [
        Job(
            id=job_id,
            tenant_id=provider_tenant,
            customer_name="Customer",
            location="Address",
            issue_description="Repair",
            priority="MEDIUM",
            service_type="Repair",
            contact_number="123",
            preferred_service_date=date.today(),
            customer_id=customer_id,
            status="CREATED",
        )
        for job_id, customer_id, provider_tenant in (
            (101, "customer-1", "provider-tenant"),
            (102, "customer-2", "provider-tenant"),
            (103, "customer-1", "other-tenant"),
        )
    ]
    session.add_all(jobs)
    session.flush()

    session.add_all(
        [
            ServiceRequest(
                id=job.id - 100,
                request_number=f"SR-{job.id}",
                customer_user_id=customer_id,
                tenant_id=tenant_id,
                title="Repair request",
                description="Please repair this item",
                status="ASSIGNED",
                linked_job_id=job.id,
            )
            for job, customer_id, tenant_id in (
                (jobs[0], "customer-1", "customer-tenant"),
                (jobs[1], "customer-2", "customer-tenant"),
                (jobs[2], "customer-1", "other-tenant"),
            )
        ]
    )
    session.add_all(
        [
            JobClosure(
                job_id=job_id,
                tenant_id=tenant_id,
                work_summary=f"Completed job {job_id}",
                after_images=[],
                completed_at=datetime.now(timezone.utc),
            )
            for job_id, tenant_id in (
                (101, "provider-tenant"),
                (102, "provider-tenant"),
                (103, "other-tenant"),
            )
        ]
    )
    session.commit()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(
            bind=engine,
            tables=[
                JobClosure.__table__,
                ServiceRequest.__table__,
                Job.__table__,
                Organization.__table__,
            ],
        )
        engine.dispose()


def _customer(user_id="customer-1", tenant_id="customer-tenant"):
    return AuthenticatedUser(
        user_id=user_id,
        tenant_id=tenant_id,
        role=UserRole.CUSTOMER,
        jti="test-jti",
    )


def test_customer_job_list_contains_only_own_tenant_scoped_requests(customer_db):
    jobs = asyncio.run(
        track_customer_jobs(_customer(), customer_db)
    )

    assert [job.id for job in jobs] == [101]


def test_customer_cannot_fetch_other_customer_or_tenant_job(customer_db):
    with pytest.raises(HTTPException) as other_customer:
        asyncio.run(
            get_customer_job_detail(102, _customer(), customer_db)
        )
    assert other_customer.value.status_code == 404

    with pytest.raises(HTTPException) as other_tenant:
        asyncio.run(
            get_customer_job_detail(
                103,
                _customer(tenant_id="customer-tenant"),
                customer_db,
            )
        )
    assert other_tenant.value.status_code == 404

    # Changing the authenticated customer identity changes ownership scope;
    # a caller cannot select another identity in request data.
    with pytest.raises(HTTPException) as modified_identity:
        asyncio.run(
            get_customer_job_detail(101, _customer(user_id="customer-2"), customer_db)
        )
    assert modified_identity.value.status_code == 404


def test_customer_cannot_call_admin_permission_dependency():
    admin_only = require_permission(Permission.JOBS_VIEW_ALL)
    with pytest.raises(HTTPException) as denied:
        asyncio.run(admin_only(_customer()))

    assert denied.value.status_code == 403


def test_service_request_update_rejects_control_fields():
    with pytest.raises(ValidationError):
        ServiceRequestUpdate.model_validate(
            {
                "priority": "HIGH",
                "linked_job_id": 102,
                "status": "CANCELLED",
            }
        )


def test_update_uses_job_state_and_updates_linked_job(customer_db, monkeypatch):
    monkeypatch.setattr(customer_portal, "audit_log", lambda *args, **kwargs: None)
    service_request = customer_db.query(ServiceRequest).filter_by(id=1).one()
    service_request.status = "ASSIGNED"  # stale; linked Job is authoritative
    customer_db.commit()

    result = asyncio.run(
        update_service_request(
            1,
            ServiceRequestUpdate(
                title="Updated repair request",
                description="Please update this repair request details",
                priority="HIGH",
                location="New address",
            ),
            None,
            _customer(),
            customer_db,
        )
    )

    job = customer_db.query(Job).filter_by(id=101).one()
    assert result.title == "Updated repair request"
    assert job.priority == "HIGH"
    assert job.location == "New address"
    assert job.site_address == "New address"
    assert job.issue_description.startswith("Updated repair request:")


def test_customer_cannot_edit_another_customers_request(customer_db, monkeypatch):
    monkeypatch.setattr(customer_portal, "audit_log", lambda *args, **kwargs: None)
    other_request = customer_db.query(ServiceRequest).filter_by(id=2).one()
    original_title = other_request.title

    with pytest.raises(HTTPException) as denied:
        asyncio.run(
            update_service_request(
                2,
                ServiceRequestUpdate(title="Changed other request"),
                None,
                _customer(),
                customer_db,
            )
        )

    assert denied.value.status_code == 404
    customer_db.refresh(other_request)
    assert other_request.title == original_title


def test_cancel_propagates_to_linked_job_using_job_state(customer_db, monkeypatch):
    monkeypatch.setattr(customer_portal, "audit_log", lambda *args, **kwargs: None)

    def cancel_transition(job, new_status, actor_id, actor_role, reason, is_override=False):
        assert actor_role == "customer"
        job.status = new_status
        job.cancellation_reason = reason

    monkeypatch.setattr(Job, "transition", cancel_transition)

    result = asyncio.run(
        cancel_service_request(1, None, _customer(), customer_db)
    )

    service_request = customer_db.query(ServiceRequest).filter_by(id=1).one()
    job = customer_db.query(Job).filter_by(id=101).one()
    assert result["id"] == 1
    assert service_request.status == "CANCELLED"
    assert job.status == "CANCELLED"
    assert service_request.cancellation_reason == job.cancellation_reason


def test_cancel_denies_when_linked_job_has_progressed(customer_db, monkeypatch):
    monkeypatch.setattr(customer_portal, "audit_log", lambda *args, **kwargs: None)
    job = customer_db.query(Job).filter_by(id=101).one()
    service_request = customer_db.query(ServiceRequest).filter_by(id=1).one()
    job.status = "EN_ROUTE"
    service_request.status = "UNASSIGNED"  # stale; should not allow cancellation
    customer_db.commit()

    with pytest.raises(HTTPException) as denied:
        asyncio.run(cancel_service_request(1, None, _customer(), customer_db))

    assert denied.value.status_code == 400
    customer_db.refresh(job)
    customer_db.refresh(service_request)
    assert job.status == "EN_ROUTE"
    assert service_request.status == "UNASSIGNED"


def test_customer_report_download_is_owner_and_tenant_scoped(customer_db):
    own_report = asyncio.run(
        download_customer_job_report(101, _customer(), customer_db)
    )
    assert own_report.media_type == "application/pdf"

    with pytest.raises(HTTPException) as other_customer:
        asyncio.run(
            download_customer_job_report(102, _customer(), customer_db)
        )
    assert other_customer.value.status_code == 404

    with pytest.raises(HTTPException) as other_tenant:
        asyncio.run(
            download_customer_job_report(103, _customer(), customer_db)
        )
    assert other_tenant.value.status_code == 404
