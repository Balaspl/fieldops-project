import asyncio
from datetime import date

import pytest
from fastapi import Request, Response
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.dependencies import AuthenticatedUser
from app.auth.rbac import UserRole
from app.database import Base
from app.models import Job, Organization, ServiceRequest, Technician, User
from app.portal_schemas import ServiceRequestCreate
from app.routes import customer_portal
from app.routes.jobs import get_jobs, get_pending_jobs


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(bind=engine)

    session = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )()

    try:
        session.add_all(
            [
                Organization(
                    id="customer-tenant",
                    name="Customer",
                    slug="customer",
                ),
                Organization(
                    id="provider-tenant",
                    name="Provider",
                    slug="provider",
                    site_latitude=13.08,
                    site_longitude=80.27,
                ),
            ]
        )

        session.flush()

        session.add_all(
            [
                User(
                    id="customer-user",
                    email="customer@example.test",
                    password_hash="hash",
                    first_name="Test",
                    last_name="Customer",
                    role="customer",
                    tenant_id="customer-tenant",
                ),
                Technician(
                    technician_id=1,
                    tech_id="provider-tech",
                    tenant_id="provider-tenant",
                    technician_name="Provider Tech",
                    technician_skill="Plumbing",
                    technician_location="Chennai",
                    technician_status="AVAILABLE",
                ),
            ]
        )

        session.commit()

        yield session

    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/customer/service-requests",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
            "scheme": "http",
        }
    )


def _customer() -> AuthenticatedUser:
    return AuthenticatedUser(
        user_id="customer-user",
        tenant_id="customer-tenant",
        role=UserRole.CUSTOMER,
        jti="test-jti",
        session_id="test-session",
    )


def _payload() -> ServiceRequestCreate:
    return ServiceRequestCreate(
        title="Plumbing repair request",
        description="There is a leak under the kitchen sink.",
        service_type="Plumbing",
        priority="HIGH",
        preferred_visit_date=date.today(),
        location="12 Anna Nagar Main Road, Chennai",
        contact_number="9876543210",
        site_latitude=13.085,
        site_longitude=80.2101,
    )


def test_service_request_creation_commits_one_canonical_provider_job(
    db_session,
):
    response = asyncio.run(
        customer_portal.create_service_request(
            _payload(),
            _request(),
            _customer(),
            db_session,
        )
    )

    job = (
        db_session.query(Job)
        .filter_by(id=response["created_job"]["id"])
        .one()
    )

    service_request = (
        db_session.query(ServiceRequest)
        .filter_by(id=response["id"])
        .one()
    )

    assert response["created_job"]["service_request_id"] == service_request.id
    assert service_request.linked_job_id == job.id
    assert job.tenant_id == "provider-tenant"
    assert job.customer_tenant_id == "customer-tenant"
    assert job.customer_id == "customer-user"
    assert job.site_latitude == pytest.approx(13.085)
    assert job.site_longitude == pytest.approx(80.2101)
    assert job.status == "CREATED"

    assert (
        db_session.query(Job)
        .filter_by(customer_id="customer-user")
        .count()
        == 1
    )


def test_customer_job_is_visible_to_provider_dispatch_and_stays_unassigned(
    db_session,
):
    response = asyncio.run(
        customer_portal.create_service_request(
            _payload(),
            _request(),
            _customer(),
            db_session,
        )
    )

    job_id = response["created_job"]["id"]

    def dispatcher(tenant_id: str) -> AuthenticatedUser:
        return AuthenticatedUser(
            user_id=f"dispatcher-{tenant_id}",
            tenant_id=tenant_id,
            role=UserRole.DISPATCHER,
            jti="test-jti",
            session_id="test-session",
        )

    # ---------------------------------------------------------
    # Provider dispatcher
    # ---------------------------------------------------------
    provider = dispatcher("provider-tenant")

    provider_jobs = get_jobs(
        response=Response(),
        search=None,
        status=None,
        priority=None,
        service_type=None,
        sla=None,
        location=None,
        technician_id=None,
        page=None,
        limit=None,
        user_tenant=(provider, provider.tenant_id),
        current_user=provider,
        db=db_session,
    )

    # ---------------------------------------------------------
    # Provider pending jobs
    # ---------------------------------------------------------
    pending_jobs = get_pending_jobs(
    response=Response(),
    search=None,
    active_filter=None,
    page=None,
    limit=None,
    user_tenant=(provider, provider.tenant_id),
    current_user=provider,
    db=db_session)

    # ---------------------------------------------------------
    # Different tenant
    # ---------------------------------------------------------
    other_tenant = dispatcher("other-tenant")

    other_tenant_jobs = get_jobs(
        response=Response(),
        search=None,
        status=None,
        priority=None,
        service_type=None,
        sla=None,
        location=None,
        technician_id=None,
        page=None,
        limit=None,
        user_tenant=(other_tenant, other_tenant.tenant_id),
        current_user=other_tenant,
        db=db_session,
    )

    # ---------------------------------------------------------
    # Assertions
    # ---------------------------------------------------------
    assert any(job.id == job_id for job in provider_jobs)

    assert any(job.id == job_id for job in pending_jobs)

    assert all(
        job.id != job_id
        for job in other_tenant_jobs
    )

    job = (
        db_session.query(Job)
        .filter_by(id=job_id)
        .one()
    )

    assert job.status == "CREATED"
    assert job.assigned_technician_id is None


def test_service_request_creation_rolls_back_job_and_request_if_audit_fails(
    db_session,
    monkeypatch,
):
    def fail_audit(*args, **kwargs):
        raise RuntimeError("audit storage unavailable")

    monkeypatch.setattr(
        customer_portal,
        "audit_log",
        fail_audit,
    )

    with pytest.raises(
        RuntimeError,
        match="audit storage unavailable",
    ):
        asyncio.run(
            customer_portal.create_service_request(
                _payload(),
                _request(),
                _customer(),
                db_session,
            )
        )

    assert db_session.query(Job).count() == 0
    assert db_session.query(ServiceRequest).count() == 0


@pytest.mark.parametrize(
    "latitude,longitude",
    [
        (0, 0),
        (91, 10),
        (10, 181),
    ],
)
def test_service_request_rejects_invalid_location_coordinates(
    latitude,
    longitude,
):
    with pytest.raises(ValidationError):
        ServiceRequestCreate(
            title="Plumbing repair request",
            description="There is a leak under the kitchen sink.",
            location="12 Anna Nagar Main Road, Chennai",
            site_latitude=latitude,
            site_longitude=longitude,
        )