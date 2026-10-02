"""Ownership and tenant boundaries for customer portal job reads."""

import asyncio
from datetime import date, datetime, timezone

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from types import SimpleNamespace
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.dependencies import AuthenticatedUser, require_permission, require_role
from app.auth.rbac import Permission, UserRole
from app.database import Base
from app.models import (
    CustomerSupportRequest,
    Job,
    JobClosure,
    JobPaymentStatus,
    CustomerFeedback,
    Organization,
    ServiceRequest,
    Technician,
)
from app.models.technician_profile import TechnicianProfile
from app.models_legacy import GPSPing
from app.portal_schemas import (
    CustomerFeedbackSubmitRequest,
    CustomerSupportRequestCreate,
    ServiceRequestUpdate,
)
from app.services.ai.FieldOpsAI.schemas.customer_profile import (
    CustomerPreferenceResponse,
    CustomerPreferenceUpdate,
)
from app.routes import customer_portal
from app.routes.customer_portal import (
    cancel_service_request,
    create_customer_support_request,
    download_customer_job_report,
    get_customer_feedback,
    get_customer_invoice,
    get_customer_invoices,
    get_customer_job_detail,
    get_customer_payment_history,
    get_customer_payment_status,
    list_customer_support_requests,
    submit_customer_feedback,
    track_customer_jobs,
    update_service_request,
    _customer_eta_payload,
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
            JobPaymentStatus.__table__,
            CustomerFeedback.__table__,
            CustomerSupportRequest.__table__,
            GPSPing.__table__,
            Technician.__table__,
            TechnicianProfile.__table__,
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

    session.add(
        Technician(
            technician_id=1,
            tech_id="tech-user-1",
            tenant_id="provider-tenant",
            technician_name="Technician One",
            technician_skill="HVAC",
            technician_location="Service Zone",
            technician_status="BUSY",
            phone_number="9876543210",
        )
    )

    session.add(
        TechnicianProfile(
            id="profile-tech-1",
            user_id="tech-user-1",
            tenant_id="provider-tenant",
            full_name="Technician One",
            profile_photo="https://example.com/tech1.jpg",
            mobile_number="9876543210",
            date_of_birth=date(1990, 1, 2),
            gender="PRIVATE",
            address="Private Technician Address",
            city="Chennai",
            state="Tamil Nadu",
            pincode="600001",
            emergency_contact="9999999999",
            skills=["HVAC", "Electrical"],
            experience="7 years",
            certifications=["EPA", "NATE"],
            profile_completed=True,
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

    # Job 101 belongs to customer-1 and is assigned to the
    # tenant-scoped technician created above.
    jobs[0].assigned_technician_id = 1
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
                JobPaymentStatus.__table__,
                CustomerSupportRequest.__table__,
                ServiceRequest.__table__,
                Job.__table__,
                TechnicianProfile.__table__,
                Technician.__table__,
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



def test_customer_job_list_includes_permitted_technician_details(customer_db):
    jobs = asyncio.run(
        track_customer_jobs(_customer(), customer_db)
    )

    assert len(jobs) == 1
    job = jobs[0]
    assert job.assigned_technician_id == 1
    assert job.assigned_technician_name == "Technician One"
    assert job.assigned_technician_photo == "https://example.com/tech1.jpg"
    assert job.assigned_technician_phone == "9876543210"
    assert job.assigned_technician_skills == ["HVAC", "Electrical"]
    assert job.assigned_technician_experience == "7 years"
    assert job.assigned_technician_certifications == ["EPA", "NATE"]


def test_customer_job_detail_excludes_private_technician_profile_fields(customer_db):
    job = asyncio.run(
        get_customer_job_detail(101, _customer(), customer_db)
    )

    payload = job.model_dump()
    assert payload["assigned_technician_name"] == "Technician One"
    assert payload["assigned_technician_phone"] == "9876543210"
    assert payload["assigned_technician_skills"] == ["HVAC", "Electrical"]
    assert payload["assigned_technician_experience"] == "7 years"
    assert payload["assigned_technician_certifications"] == ["EPA", "NATE"]

    assert "date_of_birth" not in payload
    assert "gender" not in payload
    assert "address" not in payload
    assert "city" not in payload
    assert "state" not in payload
    assert "pincode" not in payload
    assert "emergency_contact" not in payload
    assert "email" not in payload


def test_customer_job_does_not_expose_cross_tenant_technician(customer_db):
    customer_db.add(
        Technician(
            technician_id=2,
            tech_id="tech-user-2",
            tenant_id="other-tenant",
            technician_name="Other Tenant Technician",
            technician_skill="HVAC",
            technician_location="Other",
            technician_status="AVAILABLE",
            phone_number="9999999999",
        )
    )
    customer_db.commit()

    job = customer_db.query(Job).filter_by(id=101).one()
    job.assigned_technician_id = 2
    customer_db.commit()

    result = asyncio.run(
        get_customer_job_detail(101, _customer(), customer_db)
    )

    assert result.assigned_technician_id == 2
    assert result.assigned_technician_name is None
    assert result.assigned_technician_phone is None
    assert result.assigned_technician_photo is None
    assert result.assigned_technician_skills is None
    assert result.assigned_technician_experience is None
    assert result.assigned_technician_certifications is None


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


def _user_with_role(role: UserRole, user_id="internal-1", tenant_id="provider-tenant"):
    return AuthenticatedUser(
        user_id=user_id,
        tenant_id=tenant_id,
        role=role,
        jti="test-jti",
    )


def test_customer_portal_router_allows_authenticated_customer():
    """
    The customer portal router must accept only an authenticated
    CUSTOMER identity before endpoint-specific permissions are evaluated.
    """
    assert customer_portal.router.dependencies

    customer_guard = (
        customer_portal.router.dependencies[0].dependency
    )

    authenticated = asyncio.run(
        customer_guard(_customer())
    )

    assert authenticated is not None
    assert authenticated.role == UserRole.CUSTOMER
    assert authenticated.user_id == "customer-1"
    assert authenticated.tenant_id == "customer-tenant"


@pytest.mark.parametrize(
    "role",
    [
        UserRole.SUPER_ADMIN,
        UserRole.DISPATCHER,
        UserRole.TECHNICIAN,
    ],
)
def test_customer_portal_router_rejects_non_customer_roles(role):
    """
    Internal roles must not enter the customer portal merely because
    they possess other permissions.
    """
    customer_guard = (
        customer_portal.router.dependencies[0].dependency
    )

    with pytest.raises(HTTPException) as denied:
        asyncio.run(
            customer_guard(
                _user_with_role(role)
            )
        )

    assert denied.value.status_code == 403
    assert "Required role: customer" in str(
        denied.value.detail
    )


def test_customer_role_dependency_remains_customer_only():
    """
    The role dependency used by the customer portal must not accidentally
    broaden to an internal role.
    """
    customer_only_guard = require_role(
        UserRole.CUSTOMER
    )

    authenticated = asyncio.run(
        customer_only_guard(_customer())
    )

    assert authenticated.role == UserRole.CUSTOMER

    with pytest.raises(HTTPException) as denied:
        asyncio.run(
            customer_only_guard(
                _user_with_role(
                    UserRole.TECHNICIAN
                )
            )
        )

    assert denied.value.status_code == 403


def test_customer_invoice_list_returns_only_authenticated_customer_invoices(
    customer_db,
):
    closure = (
        customer_db.query(JobClosure)
        .filter(JobClosure.job_id == 101)
        .one()
    )
    closure.labour_cost = 1500
    closure.material_cost = 2500
    closure.subtotal = 4000
    customer_db.commit()

    invoices = asyncio.run(
        get_customer_invoices(
            _customer(),
            customer_db,
        )
    )

    assert len(invoices) == 1
    invoice = invoices[0]
    assert invoice.id == str(closure.id)
    assert invoice.job_id == 101
    assert invoice.customer_name == "Customer"
    assert invoice.service_type == "Repair"
    assert invoice.location == "Address"
    assert invoice.work_summary == "Completed job 101"
    assert invoice.labour_cost == 1500
    assert invoice.material_cost == 2500
    assert invoice.subtotal == 4000
    assert invoice.gst_rate == 5
    assert invoice.gst_amount == 200
    assert invoice.total_amount == 4200


def test_customer_can_fetch_own_invoice_by_job_id(customer_db):
    closure = (
        customer_db.query(JobClosure)
        .filter(JobClosure.job_id == 101)
        .one()
    )
    closure.labour_cost = 1000
    closure.material_cost = 500
    closure.subtotal = 1500
    customer_db.commit()

    invoice = asyncio.run(
        get_customer_invoice(
            101,
            _customer(),
            customer_db,
        )
    )

    assert invoice.job_id == 101
    assert invoice.id == str(closure.id)
    assert invoice.subtotal == 1500
    assert invoice.gst_amount == 75
    assert invoice.total_amount == 1575


def test_customer_can_fetch_own_authoritative_payment_status(

    customer_db,

):

    payment_status = JobPaymentStatus(

        job_id=101,

        invoice_id=1,

        tenant_id="provider-tenant",

        status="SUCCESSFUL",

    )

    customer_db.add(payment_status)

    customer_db.commit()



    result = asyncio.run(

        get_customer_payment_status(

            101,

            _customer(),

            customer_db,

        )

    )



    assert result["job_id"] == 101

    assert result["invoice_id"] == 1

    assert result["status"] == "SUCCESSFUL"

    assert result["updated_at"] is not None





@pytest.mark.parametrize(
    "job_id, user_id, tenant_id",
    [
        (102, "customer-1", "customer-tenant"),
        (101, "customer-2", "customer-tenant"),
        (103, "customer-1", "customer-tenant"),
    ],
)
def test_customer_invoice_lookup_rejects_cross_customer_or_tenant_access(
    customer_db,
    job_id,
    user_id,
    tenant_id,
):
    with pytest.raises(HTTPException) as denied:
        asyncio.run(
            get_customer_invoice(
                job_id,
                _customer(
                    user_id=user_id,
                    tenant_id=tenant_id,
                ),
                customer_db,
            )
        )

    assert denied.value.status_code == 404
    assert denied.value.detail == "Invoice not found"

def test_customer_payment_status_is_unavailable_when_no_record_exists(
    customer_db,
):
    result = asyncio.run(
        get_customer_payment_status(
            101,
            _customer(),
            customer_db,
        )
    )

    assert result == {
        "job_id": 101,
        "invoice_id": None,
        "status": "UNAVAILABLE",
        "updated_at": None,
    }

def test_customer_payment_status_rejects_cross_customer_or_tenant_access(
    customer_db,
):
    payment_statuses = [
        JobPaymentStatus(
            job_id=102,
            invoice_id=2,
            tenant_id="provider-tenant",
            status="SUCCESSFUL",
        ),

        JobPaymentStatus(
            job_id=103,
            invoice_id=3,
            tenant_id="other-tenant",
            status="SUCCESSFUL",
        ),
    ]
    customer_db.add_all(payment_statuses)
    customer_db.commit()

    with pytest.raises(HTTPException) as other_customer:
        asyncio.run(
            get_customer_payment_status(
                102,
                _customer(),
                customer_db,
            )
        )

    assert other_customer.value.status_code == 404
    assert other_customer.value.detail == "Invoice not found"

    with pytest.raises(HTTPException) as other_tenant:
        asyncio.run(
            get_customer_payment_status(
                103,
                _customer(),
                customer_db,
            )
        )

    assert other_tenant.value.status_code == 404
    assert other_tenant.value.detail == "Invoice not found"

def test_customer_payment_status_does_not_read_a_mismatched_payment_tenant(
    customer_db,
):
    payment_status = JobPaymentStatus(
        job_id=101,
        invoice_id=1,
        tenant_id="other-tenant",
        status="SUCCESSFUL",
    )
    customer_db.add(payment_status)
    customer_db.commit()

    result = asyncio.run(
        get_customer_payment_status(
            101,
            _customer(),
            customer_db,
        )
    )

    assert result == {
        "job_id": 101,
        "invoice_id": None,
        "status": "UNAVAILABLE",
        "updated_at": None,
    }

def test_customer_payment_history_returns_authoritative_invoice_payment_record(
    customer_db,
):
    closure = (
        customer_db.query(JobClosure)
        .filter(JobClosure.job_id == 101)
        .one()
    )

    closure.labour_cost = 1500
    closure.material_cost = 2500
    closure.subtotal = 4000
    customer_db.commit()

    payment_status = JobPaymentStatus(
        job_id=101,
        invoice_id=closure.id,
        tenant_id="provider-tenant",
        status="SUCCESSFUL",
    )
    customer_db.add(payment_status)
    customer_db.commit()

    history = asyncio.run(
        get_customer_payment_history(
            _customer(),
            customer_db,
        )
    )

    assert len(history) == 1

    entry = history[0]

    assert entry.invoice_id == str(closure.id)
    assert entry.job_id == 101
    assert entry.service_type == "Repair"
    assert entry.total_amount == 4200
    assert entry.payment_status == "SUCCESSFUL"
    assert entry.payment_status_updated_at is not None
    assert entry.invoice_created_at == closure.created_at
    assert entry.completed_at == closure.completed_at


def test_customer_payment_history_returns_unavailable_without_payment_record(
    customer_db,
):
    history = asyncio.run(
        get_customer_payment_history(
            _customer(),
            customer_db,
        )
    )

    assert len(history) == 1

    entry = history[0]

    assert entry.job_id == 101
    assert entry.invoice_id == "1"
    assert entry.payment_status == "UNAVAILABLE"
    assert entry.payment_status_updated_at is None


def test_customer_payment_history_rejects_cross_customer_and_tenant_records(
    customer_db,
):
    payment_statuses = [
        JobPaymentStatus(
            job_id=102,
            invoice_id=2,
            tenant_id="provider-tenant",
            status="SUCCESSFUL",
        ),
        JobPaymentStatus(
            job_id=103,
            invoice_id=3,
            tenant_id="other-tenant",
            status="SUCCESSFUL",
        ),
    ]

    customer_db.add_all(payment_statuses)
    customer_db.commit()

    history = asyncio.run(
        get_customer_payment_history(
            _customer(),
            customer_db,
        )
    )

    assert [entry.job_id for entry in history] == [101]

    assert all(
        entry.job_id not in {102, 103}
        for entry in history
    )


def test_customer_payment_history_normalizes_unexpected_payment_status(
    customer_db,
):
    job = customer_db.query(Job).filter(Job.id == 101).one()

    closure = (
        customer_db.query(JobClosure)
        .filter(JobClosure.job_id == 101)
        .one()
    )

    payment_status = SimpleNamespace(
        status="COMPLETED",
        updated_at=None,
    )

    entry = customer_portal._customer_payment_history_response(
        job,
        closure,
        payment_status,
    )

    assert entry.job_id == 101
    assert entry.invoice_id == str(closure.id)
    assert entry.payment_status == "UNAVAILABLE"


def test_customer_invoice_list_excludes_other_customer_invoice(
    customer_db,
):
    customer_1_closure = (
        customer_db.query(JobClosure)
        .filter(JobClosure.job_id == 101)
        .one()
    )
    customer_2_closure = (
        customer_db.query(JobClosure)
        .filter(JobClosure.job_id == 102)
        .one()
    )

    customer_1_closure.subtotal = 1000
    customer_2_closure.subtotal = 2000
    customer_db.commit()

    invoices = asyncio.run(
        get_customer_invoices(
            _customer(),
            customer_db,
        )
    )

    assert [invoice.job_id for invoice in invoices] == [101]
    assert invoices[0].total_amount == 1050


def test_customer_invoice_missing_persisted_record_returns_empty_or_not_found(
    customer_db,
):
    customer_db.query(JobClosure).filter(
        JobClosure.job_id == 101
    ).delete()
    customer_db.commit()

    invoices = asyncio.run(
        get_customer_invoices(
            _customer(),
            customer_db,
        )
    )
    assert invoices == []

    with pytest.raises(HTTPException) as missing:
        asyncio.run(
            get_customer_invoice(
                101,
                _customer(),
                customer_db,
            )
        )
    assert missing.value.status_code == 404
    assert missing.value.detail == "Invoice not found"

def test_customer_payment_status_reflects_persisted_backend_state(
    customer_db,
):
    payment_status = JobPaymentStatus(
        job_id=101,
        invoice_id=1,
        tenant_id="provider-tenant",
        status="PENDING",
    )
    customer_db.add(payment_status)
    customer_db.commit()

    first_result = asyncio.run(
        get_customer_payment_status(
            101,
            _customer(),
            customer_db,
        )
    )

    assert first_result["status"] == "PENDING"

    payment_status.status = "FAILED"
    customer_db.commit()

    second_result = asyncio.run(
        get_customer_payment_status(
            101,
            _customer(),
            customer_db,
        )
    )

    assert second_result["status"] == "FAILED"



class _FakeETAService:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error

    async def calculate_eta(self, technician_id, job_id):
        if self.error is not None:
            raise self.error
        return self.result


def test_customer_eta_payload_maps_calculated_backend_result(customer_db, monkeypatch):
    job = customer_db.query(Job).filter_by(id=101).one()
    job.site_latitude = 13.0827
    job.site_longitude = 80.2707
    customer_db.flush()
    technician = customer_db.query(Technician).filter_by(technician_id=1).one()
    calculated_at = datetime.now(timezone.utc)

    eta_result = {
        "status": "calculated",
        "confidence": "high",
        "message": "Live ETA",
        "eta": calculated_at,
        "duration_minutes": 18.5,
        "distance_km": 7.2,
        "traffic_delay_minutes": 4.0,
        "calculated_at": calculated_at,
    }

    monkeypatch.setattr(
        customer_portal,
        "get_redis_client",
        lambda: object(),
    )
    monkeypatch.setattr(
        customer_portal,
        "OlaMapsClient",
        lambda redis_client: object(),
    )
    monkeypatch.setattr(
        customer_portal,
        "ETAService",
        lambda db, redis_client, maps_client: _FakeETAService(result=eta_result),
    )

    payload = asyncio.run(
        _customer_eta_payload(customer_db, job, technician)
    )

    assert payload == {
        "estimated_arrival": calculated_at,
        "eta_status": "calculated",
        "eta_source": "calculated",
        "eta_confidence": "high",
        "eta_duration_minutes": 18.5,
        "eta_distance_km": 7.2,
        "eta_traffic_delay_minutes": 4.0,
        "eta_message": "Live ETA",
        "eta_updated_at": calculated_at,
    }


def test_customer_eta_payload_maps_estimated_fallback_result(customer_db, monkeypatch):
    job = customer_db.query(Job).filter_by(id=101).one()
    job.site_latitude = 13.0827
    job.site_longitude = 80.2707
    customer_db.flush()
    technician = customer_db.query(Technician).filter_by(technician_id=1).one()
    estimated_at = datetime.now(timezone.utc)

    eta_result = {
        "status": "estimated",
        "confidence": "low",
        "disclaimer": "ETA is estimated because live route data is unavailable.",
        "eta": estimated_at,
        "duration_minutes": 33,
        "distance_km": 12.4,
        "traffic_delay_minutes": None,
        "calculated_at": estimated_at,
    }

    monkeypatch.setattr(customer_portal, "get_redis_client", lambda: object())
    monkeypatch.setattr(customer_portal, "OlaMapsClient", lambda redis_client: object())
    monkeypatch.setattr(
        customer_portal,
        "ETAService",
        lambda db, redis_client, maps_client: _FakeETAService(result=eta_result),
    )

    payload = asyncio.run(
        _customer_eta_payload(customer_db, job, technician)
    )

    assert payload["eta_status"] == "estimated"
    assert payload["eta_source"] == "estimated"
    assert payload["eta_confidence"] == "low"
    assert payload["estimated_arrival"] == estimated_at
    assert payload["eta_duration_minutes"] == 33
    assert payload["eta_distance_km"] == 12.4
    assert payload["eta_traffic_delay_minutes"] is None
    assert payload["eta_message"] == (
        "ETA is estimated because live route data is unavailable."
    )


def test_customer_eta_payload_is_unavailable_without_assignment(customer_db, monkeypatch):
    job = customer_db.query(Job).filter_by(id=101).one()
    result = asyncio.run(
        _customer_eta_payload(customer_db, job, None)
    )

    assert result["eta_status"] == "unavailable"
    assert result["eta_source"] == "unavailable"
    assert result["estimated_arrival"] is None
    assert result["eta_message"] == "ETA is currently unavailable."


def test_customer_eta_payload_is_unavailable_without_job_coordinates(customer_db):
    job = customer_db.query(Job).filter_by(id=101).one()
    technician = customer_db.query(Technician).filter_by(technician_id=1).one()

    result = asyncio.run(
        _customer_eta_payload(customer_db, job, technician)
    )

    assert result["eta_status"] == "unavailable"
    assert result["eta_source"] == "unavailable"
    assert result["estimated_arrival"] is None
    assert result["eta_message"] == (
        "ETA is unavailable because the job location is missing."
    )


def test_customer_eta_payload_hides_forbidden_or_failed_eta_service_result(
    customer_db,
    monkeypatch,
):
    job = customer_db.query(Job).filter_by(id=101).one()
    job.site_latitude = 13.0827
    job.site_longitude = 80.2707
    customer_db.flush()
    technician = customer_db.query(Technician).filter_by(technician_id=1).one()

    monkeypatch.setattr(customer_portal, "get_redis_client", lambda: object())
    monkeypatch.setattr(customer_portal, "OlaMapsClient", lambda redis_client: object())

    forbidden_service = lambda db, redis_client, maps_client: _FakeETAService(
        error=HTTPException(status_code=403, detail="Forbidden")
    )
    monkeypatch.setattr(customer_portal, "ETAService", forbidden_service)

    forbidden_result = asyncio.run(
        _customer_eta_payload(customer_db, job, technician)
    )
    assert forbidden_result["eta_status"] == "unavailable"
    assert forbidden_result["estimated_arrival"] is None

    failed_service = lambda db, redis_client, maps_client: _FakeETAService(
        error=RuntimeError("route unavailable")
    )
    monkeypatch.setattr(customer_portal, "ETAService", failed_service)

    failed_result = asyncio.run(
        _customer_eta_payload(customer_db, job, technician)
    )
    assert failed_result["eta_status"] == "unavailable"
    assert failed_result["eta_source"] == "unavailable"
    assert failed_result["eta_message"] == "ETA is currently unavailable."


def test_customer_eta_payload_unknown_backend_status_is_unavailable(
    customer_db,
    monkeypatch,
):
    job = customer_db.query(Job).filter_by(id=101).one()
    job.site_latitude = 13.0827
    job.site_longitude = 80.2707
    customer_db.flush()
    technician = customer_db.query(Technician).filter_by(technician_id=1).one()

    monkeypatch.setattr(customer_portal, "get_redis_client", lambda: object())
    monkeypatch.setattr(customer_portal, "OlaMapsClient", lambda redis_client: object())
    monkeypatch.setattr(
        customer_portal,
        "ETAService",
        lambda db, redis_client, maps_client: _FakeETAService(
            result={
                "status": "unknown",
                "confidence": "none",
                "message": "ETA unavailable from provider.",
            }
        ),
    )

    result = asyncio.run(
        _customer_eta_payload(customer_db, job, technician)
    )

    assert result["eta_status"] == "unknown"
    assert result["eta_source"] == "unavailable"
    assert result["estimated_arrival"] is None
    assert result["eta_message"] == "ETA unavailable from provider."

def test_customer_feedback_returns_empty_state_for_completed_own_job(
    customer_db,
):
    job = customer_db.query(Job).filter(Job.id == 101).one()
    job.status = "COMPLETED"
    customer_db.commit()

    result = asyncio.run(
        get_customer_feedback(
            101,
            _customer(),
            customer_db,
        )
    )

    assert result == {
        "job_id": 101,
        "has_feedback": False,
        "feedback": None,
    }


def test_customer_can_submit_feedback_for_completed_own_job(
    customer_db,
):
    job = customer_db.query(Job).filter(Job.id == 101).one()
    job.status = "COMPLETED"
    customer_db.commit()

    payload = CustomerFeedbackSubmitRequest(
        rating=5,
        comment="Excellent service and quick resolution.",
    )

    result = asyncio.run(
        submit_customer_feedback(
            101,
            payload,
            _customer(),
            customer_db,
        )
    )

    assert result["job_id"] == 101
    assert result["has_feedback"] is True
    assert result["feedback"]["rating"] == 5
    assert result["feedback"]["comment"] == (
        "Excellent service and quick resolution."
    )

    stored = (
        customer_db.query(CustomerFeedback)
        .filter(
            CustomerFeedback.job_id == 101,
            CustomerFeedback.tenant_id == "provider-tenant",
            CustomerFeedback.customer_id == "customer-1",
        )
        .one()
    )

    assert stored.rating == 5
    assert stored.comment == (
        "Excellent service and quick resolution."
    )


def test_customer_feedback_rejects_incomplete_job(
    customer_db,
):
    job = customer_db.query(Job).filter(Job.id == 101).one()
    job.status = "IN_PROGRESS"
    customer_db.commit()

    with pytest.raises(HTTPException) as denied:
        asyncio.run(
            submit_customer_feedback(
                101,
                CustomerFeedbackSubmitRequest(
                    rating=4,
                    comment="Not completed yet.",
                ),
                _customer(),
                customer_db,
            )
        )

    assert denied.value.status_code == 400
    assert denied.value.detail == (
        "Feedback can only be submitted for completed jobs."
    )


@pytest.mark.parametrize(
    "rating",
    [0, 6],
)
def test_customer_feedback_request_rejects_invalid_rating(
    rating,
):
    with pytest.raises(ValidationError):
        CustomerFeedbackSubmitRequest(
            rating=rating,
            comment="Invalid rating.",
        )


def test_customer_feedback_rejects_duplicate_submission(
    customer_db,
):
    job = customer_db.query(Job).filter(Job.id == 101).one()
    job.status = "COMPLETED"
    customer_db.commit()

    payload = CustomerFeedbackSubmitRequest(
        rating=4,
        comment="Good service.",
    )

    first = asyncio.run(
        submit_customer_feedback(
            101,
            payload,
            _customer(),
            customer_db,
        )
    )

    assert first["has_feedback"] is True

    with pytest.raises(HTTPException) as duplicate:
        asyncio.run(
            submit_customer_feedback(
                101,
                payload,
                _customer(),
                customer_db,
            )
        )

    assert duplicate.value.status_code == 409
    assert duplicate.value.detail == (
        "Feedback has already been submitted for this job."
    )

    assert (
        customer_db.query(CustomerFeedback)
        .filter(
            CustomerFeedback.job_id == 101,
            CustomerFeedback.tenant_id == "provider-tenant",
        )
        .count()
        == 1
    )


def test_customer_cannot_submit_feedback_for_another_customer_job(
    customer_db,
):
    other_customer_job = (
        customer_db.query(Job)
        .filter(Job.id == 102)
        .one()
    )

    other_customer_job.status = "COMPLETED"
    customer_db.commit()

    with pytest.raises(HTTPException) as denied:
        asyncio.run(
            submit_customer_feedback(
                102,
                CustomerFeedbackSubmitRequest(
                    rating=5,
                    comment="Unauthorized submission.",
                ),
                _customer(),
                customer_db,
            )
        )

    assert denied.value.status_code == 404
    assert denied.value.detail == "Job not found"

    assert (
        customer_db.query(CustomerFeedback)
        .filter(CustomerFeedback.job_id == 102)
        .count()
        == 0
    )


def test_customer_cannot_submit_feedback_for_another_tenant_job(
    customer_db,
):
    other_tenant_job = (
        customer_db.query(Job)
        .filter(Job.id == 103)
        .one()
    )

    other_tenant_job.status = "COMPLETED"
    customer_db.commit()

    with pytest.raises(HTTPException) as denied:
        asyncio.run(
            submit_customer_feedback(
                103,
                CustomerFeedbackSubmitRequest(
                    rating=5,
                    comment="Cross-tenant attempt.",
                ),
                _customer(),
                customer_db,
            )
        )

    assert denied.value.status_code == 404
    assert denied.value.detail == "Job not found"

    assert (
        customer_db.query(CustomerFeedback)
        .filter(CustomerFeedback.job_id == 103)
        .count()
        == 0
    )


def test_customer_feedback_read_returns_persisted_feedback(
    customer_db,
):
    job = customer_db.query(Job).filter(Job.id == 101).one()
    job.status = "COMPLETED"

    feedback = CustomerFeedback(
        job_id=101,
        tenant_id="provider-tenant",
        customer_id="customer-1",
        rating=3,
        comment="Service was completed successfully.",
    )

    customer_db.add(feedback)
    customer_db.commit()

    result = asyncio.run(
        get_customer_feedback(
            101,
            _customer(),
            customer_db,
        )
    )

    assert result["job_id"] == 101
    assert result["has_feedback"] is True
    assert result["feedback"]["rating"] == 3
    assert result["feedback"]["comment"] == (
        "Service was completed successfully."
    )


# ──────────────────────────────────────────────────
# Customer Support Request Authorization
# ──────────────────────────────────────────────────


def test_customer_support_request_create_uses_authenticated_identity(
    customer_db,
):
    result = asyncio.run(
        create_customer_support_request(
            CustomerSupportRequestCreate(
                subject="Need help with my account",
                description="Please help me understand my recent service request.",
            ),
            _customer(
                user_id="customer-1",
                tenant_id="customer-tenant",
            ),
            customer_db,
        )
    )

    assert result.request_number.startswith("SUP-")
    assert result.customer_user_id == "customer-1"
    assert result.tenant_id == "customer-tenant"
    assert result.subject == "Need help with my account"
    assert (
        result.description
        == "Please help me understand my recent service request."
    )
    assert result.status == "OPEN"


def test_customer_support_request_list_returns_only_authenticated_customer_requests(
    customer_db,
):
    customer_db.add_all(
        [
            CustomerSupportRequest(
                request_number="SUP-TEST-001",
                customer_user_id="customer-1",
                tenant_id="customer-tenant",
                subject="My request",
                description="This belongs to customer one.",
                status="OPEN",
            ),
            CustomerSupportRequest(
                request_number="SUP-TEST-002",
                customer_user_id="customer-2",
                tenant_id="customer-tenant",
                subject="Other customer",
                description="This belongs to customer two.",
                status="OPEN",
            ),
            CustomerSupportRequest(
                request_number="SUP-TEST-003",
                customer_user_id="customer-1",
                tenant_id="other-tenant",
                subject="Other tenant",
                description="This belongs to another tenant.",
                status="OPEN",
            ),
        ]
    )

    customer_db.commit()

    result = asyncio.run(
        list_customer_support_requests(
            _customer(
                user_id="customer-1",
                tenant_id="customer-tenant",
            ),
            customer_db,
        )
    )

    assert len(result) == 1
    assert result[0].request_number == "SUP-TEST-001"
    assert result[0].customer_user_id == "customer-1"
    assert result[0].tenant_id == "customer-tenant"


def test_customer_support_request_list_excludes_same_customer_from_other_tenant(
    customer_db,
):
    customer_db.add(
        CustomerSupportRequest(
            request_number="SUP-TEST-004",
            customer_user_id="customer-1",
            tenant_id="other-tenant",
            subject="Cross tenant",
            description="This must not be visible to the current tenant.",
            status="OPEN",
        )
    )

    customer_db.commit()

    result = asyncio.run(
        list_customer_support_requests(
            _customer(
                user_id="customer-1",
                tenant_id="customer-tenant",
            ),
            customer_db,
        )
    )

    assert result == []


def test_customer_support_request_schema_rejects_invalid_payloads():
    with pytest.raises(ValidationError):
        CustomerSupportRequestCreate(
            subject="ab",
            description="This description is valid.",
        )

    with pytest.raises(ValidationError):
        CustomerSupportRequestCreate(
            subject="Valid subject",
            description="short",
        )

    with pytest.raises(ValidationError):
        CustomerSupportRequestCreate(
            subject="Valid subject",
            description="This description is valid.",
            customer_user_id="customer-2",
        )


def test_customer_support_request_persists_backend_authoritative_status(
    customer_db,
):
    result = asyncio.run(
        create_customer_support_request(
            CustomerSupportRequestCreate(
                subject="Status verification",
                description="Verify that the backend owns the support status.",
            ),
            _customer(),
            customer_db,
        )
    )

    persisted = (
        customer_db.query(CustomerSupportRequest)
        .filter(CustomerSupportRequest.id == result.id)
        .one()
    )

    assert persisted.status == "OPEN"
    assert persisted.customer_user_id == "customer-1"
    assert persisted.tenant_id == "customer-tenant"
    assert persisted.subject == "Status verification"
    assert (
        persisted.description
        == "Verify that the backend owns the support status."
    )



def test_customer_notification_preferences_get_uses_authenticated_scope(
    monkeypatch,
):
    expected = CustomerPreferenceResponse(
        profile_id=None,
        tenant_id="customer-tenant",
        customer_id="customer-1",
        sms_enabled=True,
        email_enabled=True,
        push_enabled=False,
        portal_enabled=True,
        preferred_locale="en",
        revision=0,
        source="COMPATIBILITY_DEFAULT",
        updated_at=None,
        updated_by=None,
    )

    captured = {}

    class FakePreferenceService:
        def __init__(self, repository):
            captured["repository"] = repository

        def get_preferences(self, tenant_id, customer_id):
            captured["tenant_id"] = tenant_id
            captured["customer_id"] = customer_id
            return expected

    monkeypatch.setattr(
        customer_portal,
        "CustomerPreferenceService",
        FakePreferenceService,
    )

    result = asyncio.run(
        customer_portal.get_customer_notification_preferences(
            _customer(),
            object(),
        )
    )

    assert result == expected
    assert captured["tenant_id"] == "customer-tenant"
    assert captured["customer_id"] == "customer-1"
    assert captured["repository"] is not None


def test_customer_notification_preferences_update_uses_authenticated_identity(
    monkeypatch,
):
    expected = CustomerPreferenceResponse(
        profile_id="profile-1",
        tenant_id="customer-tenant",
        customer_id="customer-1",
        sms_enabled=False,
        email_enabled=True,
        push_enabled=True,
        portal_enabled=True,
        preferred_locale="en",
        revision=1,
        source="PROFILE",
        updated_at=None,
        updated_by="customer-1",
    )

    captured = {}

    class FakePreferenceService:
        def __init__(self, repository):
            captured["repository"] = repository

        def update_preferences(
            self,
            tenant_id,
            customer_id,
            payload,
            actor_id,
            actor_source,
            correlation_id=None,
        ):
            captured["tenant_id"] = tenant_id
            captured["customer_id"] = customer_id
            captured["payload"] = payload
            captured["actor_id"] = actor_id
            captured["actor_source"] = actor_source
            captured["correlation_id"] = correlation_id
            return expected

    monkeypatch.setattr(
        customer_portal,
        "CustomerPreferenceService",
        FakePreferenceService,
    )

    request = SimpleNamespace(
        headers={
            "X-Correlation-ID": "correlation-123",
        }
    )

    payload = CustomerPreferenceUpdate(
        sms_enabled=False,
        push_enabled=True,
    )

    result = asyncio.run(
        customer_portal.update_customer_notification_preferences(
            payload,
            request,
            _customer(),
            object(),
        )
    )

    assert result == expected
    assert captured["tenant_id"] == "customer-tenant"
    assert captured["customer_id"] == "customer-1"
    assert captured["actor_id"] == "customer-1"
    assert captured["actor_source"] == "CUSTOMER"
    assert captured["correlation_id"] == "correlation-123"
    assert captured["payload"].sms_enabled is False
    assert captured["payload"].push_enabled is True


def test_customer_notification_preferences_update_maps_conflict_to_409(
    monkeypatch,
):
    class FakePreferenceService:
        def __init__(self, repository):
            pass

        def update_preferences(
            self,
            tenant_id,
            customer_id,
            payload,
            actor_id,
            actor_source,
            correlation_id=None,
        ):
            raise customer_portal.CustomerPreferenceConflictError(
                "Preference revision conflict."
            )

    monkeypatch.setattr(
        customer_portal,
        "CustomerPreferenceService",
        FakePreferenceService,
    )

    request = SimpleNamespace(headers={})

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            customer_portal.update_customer_notification_preferences(
                CustomerPreferenceUpdate(sms_enabled=False),
                request,
                _customer(),
                object(),
            )
        )

    assert exc.value.status_code == 409
    assert exc.value.detail == "Preference revision conflict."


def test_customer_notification_preferences_get_maps_service_failure_to_500(
    monkeypatch,
):
    class FakePreferenceService:
        def __init__(self, repository):
            pass

        def get_preferences(self, tenant_id, customer_id):
            raise customer_portal.CustomerPreferenceError(
                "Preference service unavailable."
            )

    monkeypatch.setattr(
        customer_portal,
        "CustomerPreferenceService",
        FakePreferenceService,
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            customer_portal.get_customer_notification_preferences(
                _customer(),
                object(),
            )
        )

    assert exc.value.status_code == 500
    assert exc.value.detail == "Preference service unavailable."