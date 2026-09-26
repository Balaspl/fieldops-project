import pytest
from datetime import datetime, date, timezone
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi import HTTPException
from fastapi.testclient import TestClient

# Setup SQLite in-memory test DB
SQLALCHEMY_DATABASE_URL = "sqlite://"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

import app.database
app.database.SessionLocal = TestingSessionLocal

import fakeredis
fake_redis = fakeredis.FakeRedis(decode_responses=True)
import app.redis_client
app.redis_client.get_redis_client = lambda: fake_redis

from app.database import Base, get_db
from app.models import (
    Job,
    Technician,
    JobClosure,
    JobPaymentStatus,
    CustomerFeedback,
)
from app.schemas import JobClosureCreate
from app.services.job_closure_service import close_job, get_job_closure
from app.auth.dependencies import get_current_user, AuthenticatedUser
from app.auth.rbac import UserRole
from app.database import get_db
from app.routes.jobs import get_job_payment_status
from app.main import app

client = TestClient(app)

def _authenticated_user(
    *,
    user_id: str = "dispatcher-100",
    tenant_id: str = "tenant-1",
    role: UserRole = UserRole.DISPATCHER,
) -> AuthenticatedUser:
    return AuthenticatedUser(
        user_id=user_id,
        tenant_id=tenant_id,
        role=role,
        jti="test-job-history-jti",
    )


def _override_payment_status_dependencies(db, user: AuthenticatedUser):
    def override_get_db():
        yield db

    def override_get_current_user():
        return user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = (
        override_get_current_user
    )


def _clear_payment_status_dependencies():
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    yield db
    db.close()


def create_sample_tech_and_job(db, tech_id_str="tech-100", tech_pk=100, status="ON_SITE"):
    tech = Technician(
        technician_id=tech_pk,
        tech_id=tech_id_str,
        technician_name="John Tech",
        technician_skill="HVAC",
        technician_location="Zone 1",
        technician_status="BUSY",
        current_jobs=1,
        tenant_id="tenant-1"
    )
    db.add(tech)
    db.commit()

    job = Job(
        customer_name="Test Customer",
        location="123 Test St",
        issue_description="AC Breakdown",
        priority="HIGH",
        service_type="HVAC_REPAIR",
        contact_number="1234567890",
        preferred_service_date=date.today(),
        status=status,
        assigned_technician_id=tech_pk,
        tenant_id="tenant-1"
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return tech, job


def test_successful_job_closure(setup_db):
    db = setup_db
    tech, job = create_sample_tech_and_job(db)

    payload = JobClosureCreate(
        work_summary="Replaced faulty capacitor and recharged refrigerant.",
        before_images=["/uploads/before1.jpg"],
        after_images=["/uploads/after1.jpg", "/uploads/after2.jpg"],
        labour_cost=150.00,
        material_cost=75.50
    )

    closure = close_job(
        db=db,
        job_id=job.id,
        closure_data=payload,
        technician_identifier=str(tech.technician_id),
        tenant_id=tech.tenant_id,
        user_role="TECHNICIAN"
    )

    assert closure is not None
    assert closure.job_id == job.id
    assert closure.work_summary == payload.work_summary
    assert closure.before_images == ["/uploads/before1.jpg"]
    assert closure.after_images == ["/uploads/after1.jpg", "/uploads/after2.jpg"]
    assert closure.labour_cost == 150.00
    assert closure.material_cost == 75.50
    assert closure.subtotal == 225.50

    # Verify Job state update
    updated_job = db.query(Job).filter(Job.id == job.id).first()
    assert updated_job.status == "COMPLETED"
    assert updated_job.completed_at is not None
    assert updated_job.completed_by == str(tech.technician_id)


def test_subtotal_calculated(setup_db):
    db = setup_db
    tech, job = create_sample_tech_and_job(db)

    payload = JobClosureCreate(
        work_summary="Completed repair work.",
        after_images=["/uploads/after.jpg"],
        labour_cost=125.25,
        material_cost=44.75
    )

    closure = close_job(
        db=db,
        job_id=job.id,
        closure_data=payload,
        technician_identifier=str(tech.technician_id),
        tenant_id=tech.tenant_id,
        user_role="TECHNICIAN"
    )

    assert closure.subtotal == 170.00


def test_completed_at_and_by_stored(setup_db):
    db = setup_db
    tech, job = create_sample_tech_and_job(db)

    payload = JobClosureCreate(
        work_summary="Fixed issue completely.",
        after_images=["/uploads/after.jpg"],
        labour_cost=50.0,
        material_cost=20.0,
    )

    before_time = datetime.now(timezone.utc)

    closure = close_job(
        db=db,
        job_id=job.id,
        closure_data=payload,
        technician_identifier="tech-100",
        tenant_id=tech.tenant_id,
        user_role="TECHNICIAN",
    )

    after_time = datetime.now(timezone.utc)

    assert closure.completed_at is not None
    assert closure.completed_at.tzinfo is not None
    assert closure.completed_at.utcoffset() == timezone.utc.utcoffset(closure.completed_at)

    db_job = db.query(Job).filter(Job.id == job.id).first()

    assert db_job.completed_at is not None
    assert db_job.completed_at.tzinfo is not None
    assert db_job.completed_at.utcoffset() == timezone.utc.utcoffset(db_job.completed_at)

    # Job and JobClosure must use the exact same authoritative timestamp.
    assert db_job.completed_at == closure.completed_at

    # The timestamp must be generated by the backend during completion.
    assert before_time <= closure.completed_at <= after_time

    assert closure.technician_id == "tech-100"
    assert db_job.completed_by == "tech-100"


def test_duplicate_completion_rejected(setup_db):
    db = setup_db
    tech, job = create_sample_tech_and_job(db)

    payload = JobClosureCreate(
        work_summary="First completion.",
        after_images=["/uploads/after.jpg"],
        labour_cost=50.0,
        material_cost=20.0
    )

    close_job(
        db=db,
        job_id=job.id,
        closure_data=payload,
        technician_identifier=str(tech.technician_id),
        tenant_id=tech.tenant_id,
        user_role="TECHNICIAN"
    )

    # Attempt second closure
    with pytest.raises(HTTPException) as exc_info:
        close_job(
            db=db,
            job_id=job.id,
            closure_data=payload,
            technician_identifier=str(tech.technician_id),
            tenant_id=tech.tenant_id,
            user_role="TECHNICIAN"
        )
    assert exc_info.value.status_code == 400
    assert "cannot be closed" in exc_info.value.detail.lower()


def test_unauthorized_user_rejected(setup_db):
    db = setup_db
    tech, job = create_sample_tech_and_job(db)

    payload = JobClosureCreate(
        work_summary="Unauthorized attempt.",
        after_images=["/uploads/after.jpg"],
        labour_cost=100.0,
        material_cost=0.0
    )

    # User role DISPATCHER should be rejected with 403
    with pytest.raises(HTTPException) as exc_info:
        close_job(
            db=db,
            job_id=job.id,
            closure_data=payload,
            technician_identifier=str(tech.technician_id),
            tenant_id=tech.tenant_id,
            user_role="DISPATCHER"
        )
    assert exc_info.value.status_code == 403
    assert "Only technicians can close jobs" in exc_info.value.detail


def test_invalid_job(setup_db):
    db = setup_db

    payload = JobClosureCreate(
        work_summary="Closing non-existent job.",
        after_images=["/uploads/after.jpg"],
        labour_cost=10.0,
        material_cost=5.0
    )

    with pytest.raises(HTTPException) as exc_info:
        close_job(
            db=db,
            job_id=99999,
            closure_data=payload,
            technician_identifier="tech-100",
            tenant_id="tenant-1",
            user_role="TECHNICIAN"
        )
    assert exc_info.value.status_code == 404
    assert "Job not found" in exc_info.value.detail


def test_validation_failures():
    # Empty work summary
    with pytest.raises(ValueError):
        JobClosureCreate(
            work_summary="",
            after_images=["/uploads/after.jpg"],
            labour_cost=10.0,
            material_cost=5.0
        )

    # Missing after images
    with pytest.raises(ValueError):
        JobClosureCreate(
            work_summary="Summary",
            after_images=[],
            labour_cost=10.0,
            material_cost=5.0
        )

    # Negative costs
    with pytest.raises(ValueError):
        JobClosureCreate(
            work_summary="Summary",
            after_images=["/uploads/after.jpg"],
            labour_cost=-50.0,
            material_cost=5.0
        )


def test_rollback_on_failure(setup_db):
    db = setup_db
    tech, job = create_sample_tech_and_job(db)

    payload = JobClosureCreate(
        work_summary="Rollback test.",
        after_images=["/uploads/after.jpg"],
        labour_cost=100.0,
        material_cost=50.0
    )

    with patch.object(db, "commit", side_effect=Exception("Database commit error")):
        with pytest.raises(HTTPException) as exc_info:
            close_job(
                db=db,
                job_id=job.id,
                closure_data=payload,
                technician_identifier=str(tech.technician_id),
                tenant_id=tech.tenant_id,
                user_role="TECHNICIAN"
            )
        assert exc_info.value.status_code == 500

    # Verify job status remained ON_SITE and not changed to COMPLETED
    reloaded_job = db.query(Job).filter(Job.id == job.id).first()
    assert reloaded_job.status == "ON_SITE"
    assert reloaded_job.completed_at is None


def test_get_job_closure_api(setup_db):
    db = setup_db
    tech, job = create_sample_tech_and_job(db)

    payload = JobClosureCreate(
        work_summary="API test summary.",
        before_images=["/uploads/before.jpg"],
        after_images=["/uploads/after.jpg"],
        labour_cost=80.0,
        material_cost=20.0
    )

    close_job(
        db=db,
        job_id=job.id,
        closure_data=payload,
        technician_identifier=str(tech.technician_id),
        tenant_id=tech.tenant_id,
        user_role="TECHNICIAN"
    )

    closure = get_job_closure(db=db, job_id=job.id)
    assert closure.work_summary == "API test summary."
    assert closure.subtotal == 100.0

def test_structured_work_report_stored(setup_db):
    db = setup_db
    tech, job = create_sample_tech_and_job(db)

    payload = JobClosureCreate(
        work_summary="Legacy summary",
        work_report={
            "summary": "Valve replaced",
            "parts_used": ["Valve", "Seal"],
            "duration_minutes": 90
        },
        after_images=["/uploads/after.jpg"],
        labour_cost=100.0,
        material_cost=50.0
    )

    closure = close_job(
        db=db,
        job_id=job.id,
        closure_data=payload,
        technician_identifier=str(tech.technician_id),
        tenant_id=tech.tenant_id,
        user_role="TECHNICIAN"
    )

    assert closure.work_report is not None
    assert closure.work_report["summary"] == "Valve replaced"
    assert closure.work_report["parts_used"] == ["Valve", "Seal"]
    assert closure.work_report["duration_minutes"] == 90


def test_structured_work_report_syncs_job_work_report(setup_db):
    db = setup_db
    tech, job = create_sample_tech_and_job(db)

    payload = JobClosureCreate(
        work_summary="Old summary",
        work_report={
            "summary": "Compressor repaired",
            "parts_used": ["Compressor"],
            "duration_minutes": 120
        },
        after_images=["/uploads/after.jpg"],
        labour_cost=100.0,
        material_cost=50.0
    )

    close_job(
        db=db,
        job_id=job.id,
        closure_data=payload,
        technician_identifier=str(tech.technician_id),
        tenant_id=tech.tenant_id,
        user_role="TECHNICIAN"
    )

    db.refresh(job)

    assert job.work_report == "Compressor repaired"


def test_structured_work_report_validation(setup_db):
    # Blank summary must fail
    with pytest.raises(ValueError):
        JobClosureCreate(
            work_summary="Valid summary",
            work_report={
                "summary": "   ",
                "parts_used": ["Valve"],
                "duration_minutes": 60
            },
            after_images=["/uploads/after.jpg"],
            labour_cost=100.0,
            material_cost=50.0
        )

    # Blank part must fail
    with pytest.raises(ValueError):
        JobClosureCreate(
            work_summary="Valid summary",
            work_report={
                "summary": "Valve replaced",
                "parts_used": ["Valve", "   "],
                "duration_minutes": 60
            },
            after_images=["/uploads/after.jpg"],
            labour_cost=100.0,
            material_cost=50.0
        )

    # Negative duration must fail
    with pytest.raises(ValueError):
        JobClosureCreate(
            work_summary="Valid summary",
            work_report={
                "summary": "Valve replaced",
                "parts_used": ["Valve"],
                "duration_minutes": -10
            },
            after_images=["/uploads/after.jpg"],
            labour_cost=100.0,
            material_cost=50.0
        )


def test_legacy_work_summary_creates_compatible_work_report(setup_db):
    db = setup_db
    tech, job = create_sample_tech_and_job(db)

    payload = JobClosureCreate(
        work_summary="Completed AC repair.",
        after_images=["/uploads/after.jpg"],
        labour_cost=100.0,
        material_cost=50.0
    )

    closure = close_job(
        db=db,
        job_id=job.id,
        closure_data=payload,
        technician_identifier=str(tech.technician_id),
        tenant_id=tech.tenant_id,
        user_role="TECHNICIAN"
    )

    assert closure.work_report is not None
    assert closure.work_report["summary"] == "Completed AC repair."
    assert closure.work_report["parts_used"] == []
    assert closure.work_report["duration_minutes"] is None

def test_required_checklist_must_be_completed(setup_db):
    db = setup_db
    tech, job = create_sample_tech_and_job(db)

    payload = JobClosureCreate(
        work_summary="Completed repair.",
        checklist={
            "items": [
                {
                    "id": "power",
                    "label": "Power checked",
                    "status": "COMPLETED",
                    "required": True,
                },
                {
                    "id": "safety",
                    "label": "Safety inspection",
                    "status": "INCOMPLETE",
                    "required": True,
                },
            ]
        },
        after_images=["/uploads/after.jpg"],
        labour_cost=100.0,
        material_cost=50.0,
    )

    with pytest.raises(HTTPException) as exc_info:
        close_job(
            db=db,
            job_id=job.id,
            closure_data=payload,
            technician_identifier=str(tech.technician_id),
            tenant_id=tech.tenant_id,
            user_role="TECHNICIAN",
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["error"] == "INCOMPLETE_CHECKLIST"
    assert exc_info.value.detail["incomplete_items"] == [
        {
            "id": "safety",
            "label": "Safety inspection",
        }
    ]

    db.refresh(job)
    assert job.status == "ON_SITE"
    assert job.completed_at is None


def test_optional_incomplete_checklist_item_allows_completion(setup_db):
    db = setup_db
    tech, job = create_sample_tech_and_job(db)

    payload = JobClosureCreate(
        work_summary="Completed repair.",
        checklist={
            "items": [
                {
                    "id": "power",
                    "label": "Power checked",
                    "status": "COMPLETED",
                    "required": True,
                },
                {
                    "id": "cleanup",
                    "label": "Work area cleaned",
                    "status": "INCOMPLETE",
                    "required": False,
                },
            ]
        },
        after_images=["/uploads/after.jpg"],
        labour_cost=100.0,
        material_cost=50.0,
    )

    closure = close_job(
        db=db,
        job_id=job.id,
        closure_data=payload,
        technician_identifier=str(tech.technician_id),
        tenant_id=tech.tenant_id,
        user_role="TECHNICIAN",
    )

    assert closure is not None
    assert closure.completion_checklist["items"][1]["status"] == "INCOMPLETE"

    db.refresh(job)
    assert job.status == "COMPLETED"


def test_completed_checklist_is_persisted(setup_db):
    db = setup_db
    tech, job = create_sample_tech_and_job(db)

    payload = JobClosureCreate(
        work_summary="Completed repair.",
        checklist={
            "items": [
                {
                    "id": "power",
                    "label": "Power checked",
                    "status": "COMPLETED",
                    "required": True,
                },
                {
                    "id": "safety",
                    "label": "Safety inspection",
                    "status": "COMPLETED",
                    "required": True,
                },
            ]
        },
        after_images=["/uploads/after.jpg"],
        labour_cost=100.0,
        material_cost=50.0,
    )

    closure = close_job(
        db=db,
        job_id=job.id,
        closure_data=payload,
        technician_identifier=str(tech.technician_id),
        tenant_id=tech.tenant_id,
        user_role="TECHNICIAN",
    )

    db.refresh(closure)

    assert closure.completion_checklist == {
        "items": [
            {
                "id": "power",
                "label": "Power checked",
                "status": "COMPLETED",
                "required": True,
            },
            {
                "id": "safety",
                "label": "Safety inspection",
                "status": "COMPLETED",
                "required": True,
            },
        ]
    }

@pytest.mark.parametrize(
    "payment_state",
    [
        "PENDING",
        "SUCCESSFUL",
        "FAILED",
        "UNAVAILABLE",
    ],
)
def test_payment_status_returns_backend_authoritative_state(
    setup_db,
    payment_state,
):
    db = setup_db
    tech, job = create_sample_tech_and_job(db)

    closure = close_job(
        db=db,
        job_id=job.id,
        closure_data=JobClosureCreate(
            work_summary="Completed repair.",
            after_images=["/uploads/after.jpg"],
            labour_cost=100.0,
            material_cost=50.0,
        ),
        technician_identifier=str(tech.technician_id),
        tenant_id=tech.tenant_id,
        user_role="TECHNICIAN",
    )

    payment = JobPaymentStatus(
        job_id=job.id,
        invoice_id=closure.id,
        tenant_id=job.tenant_id,
        status=payment_state,
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)

    user = _authenticated_user()

    _override_payment_status_dependencies(db, user)

    try:
        response = client.get(
            f"/api/v1/jobs/{job.id}/payment-status"
        )
    finally:
        _clear_payment_status_dependencies()

    assert response.status_code == 200

    data = response.json()

    assert data["job_id"] == job.id
    assert data["invoice_id"] == closure.id
    assert data["status"] == payment_state
    assert data["updated_at"] is not None


def test_payment_status_returns_unavailable_when_record_does_not_exist(
    setup_db,
):
    db = setup_db
    _, job = create_sample_tech_and_job(db)

    user = _authenticated_user()

    _override_payment_status_dependencies(db, user)

    try:
        response = client.get(
            f"/api/v1/jobs/{job.id}/payment-status"
        )
    finally:
        _clear_payment_status_dependencies()

    assert response.status_code == 200

    data = response.json()

    assert data == {
        "job_id": job.id,
        "invoice_id": None,
        "status": "UNAVAILABLE",
        "updated_at": None,
    }


def test_payment_status_enforces_tenant_isolation(
    setup_db,
):
    db = setup_db
    tech, job = create_sample_tech_and_job(db)

    payment = JobPaymentStatus(
        job_id=job.id,
        invoice_id=None,
        tenant_id="tenant-1",
        status="SUCCESSFUL",
    )
    db.add(payment)
    db.commit()

    user = _authenticated_user(
        tenant_id="tenant-2",
    )

    _override_payment_status_dependencies(db, user)

    try:
        response = client.get(
            f"/api/v1/jobs/{job.id}/payment-status"
        )
    finally:
        _clear_payment_status_dependencies()

    assert response.status_code == 404

    assert response.json()["detail"] == "Job not found"


def test_payment_status_enforces_technician_object_access(
    setup_db,
):
    db = setup_db

    assigned_tech, job = create_sample_tech_and_job(
        db,
        tech_id_str="tech-100",
        tech_pk=100,
    )

    payment = JobPaymentStatus(
        job_id=job.id,
        invoice_id=None,
        tenant_id=job.tenant_id,
        status="PENDING",
    )
    db.add(payment)
    db.commit()

    other_tech = Technician(
        technician_id=200,
        tech_id="tech-200",
        technician_name="Other Technician",
        technician_skill="HVAC",
        technician_location="Zone 2",
        technician_status="AVAILABLE",
        current_jobs=0,
        tenant_id="tenant-1",
    )
    db.add(other_tech)
    db.commit()

    user = _authenticated_user(
        user_id="tech-200",
        tenant_id="tenant-1",
        role=UserRole.TECHNICIAN,
    )

    _override_payment_status_dependencies(db, user)

    try:
        response = client.get(
            f"/api/v1/jobs/{job.id}/payment-status"
        )
    finally:
        _clear_payment_status_dependencies()

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "This job is not assigned to you"
    )


def test_payment_status_does_not_mutate_payment_record(
    setup_db,
):
    db = setup_db
    tech, job = create_sample_tech_and_job(db)

    payment = JobPaymentStatus(
        job_id=job.id,
        invoice_id=None,
        tenant_id=job.tenant_id,
        status="PENDING",
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)

    original_id = payment.id
    original_status = payment.status
    original_updated_at = payment.updated_at

    user = _authenticated_user()

    _override_payment_status_dependencies(db, user)

    try:
        response = client.get(
            f"/api/v1/jobs/{job.id}/payment-status"
        )
    finally:
        _clear_payment_status_dependencies()

    assert response.status_code == 200

    db.refresh(payment)

    assert payment.id == original_id
    assert payment.status == original_status
    assert payment.updated_at == original_updated_at

# ---------------------------------------------------------------------------
# Task 9: Customer Feedback
# ---------------------------------------------------------------------------

def test_customer_feedback_returns_backend_authoritative_sanitized_record(
    setup_db,
):
    db = setup_db
    _, job = create_sample_tech_and_job(db, status="COMPLETED")

    feedback = CustomerFeedback(
        job_id=job.id,
        tenant_id=job.tenant_id,
        customer_id="customer-internal-001",
        rating=5,
        comment="Excellent service. The technician resolved the issue quickly.",
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)

    user = _authenticated_user()
    _override_payment_status_dependencies(db, user)

    try:
        response = client.get(
            f"/api/v1/jobs/{job.id}/customer-feedback"
        )
    finally:
        _clear_payment_status_dependencies()

    assert response.status_code == 200

    data = response.json()

    assert data["job_id"] == job.id
    assert data["has_feedback"] is True
    assert data["feedback"]["id"] == feedback.id
    assert data["feedback"]["rating"] == 5
    assert (
        data["feedback"]["comment"]
        == "Excellent service. The technician resolved the issue quickly."
    )
    assert data["feedback"]["created_at"] is not None
    assert data["feedback"]["updated_at"] is not None

    # Customer-sensitive internal identifiers must never be exposed.
    assert "customer_id" not in data
    assert "customer_id" not in data["feedback"]


def test_customer_feedback_returns_empty_state_when_no_record_exists(
    setup_db,
):
    db = setup_db
    _, job = create_sample_tech_and_job(db, status="COMPLETED")

    user = _authenticated_user()
    _override_payment_status_dependencies(db, user)

    try:
        response = client.get(
            f"/api/v1/jobs/{job.id}/customer-feedback"
        )
    finally:
        _clear_payment_status_dependencies()

    assert response.status_code == 200
    assert response.json() == {
        "job_id": job.id,
        "has_feedback": False,
        "feedback": None,
    }


def test_customer_feedback_enforces_tenant_isolation(
    setup_db,
):
    db = setup_db
    _, job = create_sample_tech_and_job(db, status="COMPLETED")

    feedback = CustomerFeedback(
        job_id=job.id,
        tenant_id=job.tenant_id,
        customer_id="customer-internal-002",
        rating=4,
        comment="Good service.",
    )
    db.add(feedback)
    db.commit()

    user = _authenticated_user(
        tenant_id="tenant-2",
    )
    _override_payment_status_dependencies(db, user)

    try:
        response = client.get(
            f"/api/v1/jobs/{job.id}/customer-feedback"
        )
    finally:
        _clear_payment_status_dependencies()

    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found"


def test_customer_feedback_returns_not_found_for_unknown_job(
    setup_db,
):
    db = setup_db

    user = _authenticated_user()
    _override_payment_status_dependencies(db, user)

    try:
        response = client.get(
            "/api/v1/jobs/99999/customer-feedback"
        )
    finally:
        _clear_payment_status_dependencies()

    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found"


def test_customer_feedback_rejects_unauthorized_permission(
    setup_db,
    monkeypatch,
):
    db = setup_db
    _, job = create_sample_tech_and_job(db, status="COMPLETED")

    # The endpoint is protected by the existing JOBS_VIEW_ALL permission
    # dependency. Force the shared permission check to deny access so the
    # test verifies the route cannot bypass RBAC.
    import app.auth.dependencies as auth_dependencies

    monkeypatch.setattr(
        auth_dependencies,
        "has_permission",
        lambda *args, **kwargs: False,
    )

    user = _authenticated_user()
    _override_payment_status_dependencies(db, user)

    try:
        response = client.get(
            f"/api/v1/jobs/{job.id}/customer-feedback"
        )
    finally:
        _clear_payment_status_dependencies()

    assert response.status_code == 403


def test_customer_feedback_does_not_mutate_feedback_record(
    setup_db,
):
    db = setup_db
    _, job = create_sample_tech_and_job(db, status="COMPLETED")

    feedback = CustomerFeedback(
        job_id=job.id,
        tenant_id=job.tenant_id,
        customer_id="customer-internal-003",
        rating=3,
        comment="Service was completed.",
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)

    original_id = feedback.id
    original_customer_id = feedback.customer_id
    original_rating = feedback.rating
    original_comment = feedback.comment
    original_created_at = feedback.created_at
    original_updated_at = feedback.updated_at

    user = _authenticated_user()
    _override_payment_status_dependencies(db, user)

    try:
        response = client.get(
            f"/api/v1/jobs/{job.id}/customer-feedback"
        )
    finally:
        _clear_payment_status_dependencies()

    assert response.status_code == 200

    db.refresh(feedback)

    assert feedback.id == original_id
    assert feedback.customer_id == original_customer_id
    assert feedback.rating == original_rating
    assert feedback.comment == original_comment
    assert feedback.created_at == original_created_at
    assert feedback.updated_at == original_updated_at


def test_customer_feedback_returns_latest_backend_record_without_pii(
    setup_db,
):
    db = setup_db
    _, job = create_sample_tech_and_job(db, status="COMPLETED")

    feedback = CustomerFeedback(
        job_id=job.id,
        tenant_id=job.tenant_id,
        customer_id="customer-internal-004",
        rating=1,
        comment=None,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)

    user = _authenticated_user()
    _override_payment_status_dependencies(db, user)

    try:
        response = client.get(
            f"/api/v1/jobs/{job.id}/customer-feedback"
        )
    finally:
        _clear_payment_status_dependencies()

    assert response.status_code == 200

    data = response.json()

    assert data["has_feedback"] is True
    assert data["feedback"]["rating"] == 1
    assert data["feedback"]["comment"] is None
    assert "customer_id" not in data["feedback"]

