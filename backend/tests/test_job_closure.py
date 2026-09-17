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

from app.database import Base
from app.models import Job, Technician, JobClosure
from app.schemas import JobClosureCreate
from app.services.job_closure_service import close_job, get_job_closure
from app.main import app

client = TestClient(app)


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
    assert "already completed" in exc_info.value.detail


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