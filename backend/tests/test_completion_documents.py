import pytest
from datetime import date
import io
from app.models import AuditEvent
from app.services.completion_document_validation import (
    CompletionDocumentValidationError,
    CompletionDocumentValidator,
)
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.auth.dependencies import (
    get_current_user,
    AuthenticatedUser,
)
from app.auth.rbac import UserRole
from app.database import Base, get_db
from app.main import app
from app.models import AuditEvent, CompletionDocument, Job, Technician
from app.redis_client import get_redis_client


# ---------------------------------------------------------------------------
# Test database
# ---------------------------------------------------------------------------

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


# ---------------------------------------------------------------------------
# Dependency overrides
# ---------------------------------------------------------------------------

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
    session_id="test-session",
)


def _set_user(
    user_id="tech-123",
    tenant_id="tenant-1",
    role=UserRole.TECHNICIAN,
):
    global _current_user

    _current_user = AuthenticatedUser(
        user_id=user_id,
        tenant_id=tenant_id,
        role=role,
        jti="test-jti",
        session_id="test-session",
    )


async def override_current_user():
    return _current_user


# ---------------------------------------------------------------------------
# Redis mock
# ---------------------------------------------------------------------------

class MockRedis:
    def publish(self, channel, message):
        return 1


mock_redis = MockRedis()


def override_get_redis():
    return mock_redis


# ---------------------------------------------------------------------------
# Test client
# ---------------------------------------------------------------------------

client = TestClient(app)


# ---------------------------------------------------------------------------
# Test data helpers
# ---------------------------------------------------------------------------

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


def completion_payload():
    return {
        "work_summary": "Replaced faulty capacitor and completed repair.",
        "before_images": ["/uploads/before.jpg"],
        "after_images": ["/uploads/after.jpg"],
        "labour_cost": 150.0,
        "material_cost": 75.5,
    }


def _complete_job(job_id):
    response = client.post(
        f"/jobs/{job_id}/close",
        json=completion_payload(),
    )

    assert response.status_code == 200, response.text


# ---------------------------------------------------------------------------
# Database/test setup
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_assigned_technician_can_upload_completion_photo(
    tmp_path,
    monkeypatch,
):
    from app.services.completion_document_storage import (
        CompletionDocumentStorage,
    )

    def test_storage_init(self):
        self.root_dir = tmp_path

    monkeypatch.setattr(
        CompletionDocumentStorage,
        "__init__",
        test_storage_init,
    )

    db = TestingSessionLocal()

    try:
        _, job = _create_tech_and_job(db)

        _complete_job(job.id)

        response = client.post(
            f"/jobs/{job.id}/completion-documents/photos",
            data={"category": "AFTER"},
            files={
                "file": (
                    "after.jpg",
                    b"test-image-data",
                    "image/jpeg",
                )
            },
        )

        assert response.status_code == 201, response.text

        data = response.json()

        assert data["job_id"] == job.id
        assert data["job_closure_id"] > 0
        assert data["tenant_id"] == "tenant-1"
        assert data["category"] == "AFTER"
        assert data["original_filename"] == "after.jpg"
        assert data["content_type"] == "image/jpeg"
        assert data["file_size"] == len(b"test-image-data")
        assert data["status"] == "AVAILABLE"

        document = (
            db.query(CompletionDocument)
            .filter(CompletionDocument.job_id == job.id)
            .one()
        )

        assert document.category == "AFTER"
        assert document.tenant_id == "tenant-1"
        assert document.storage_key

    finally:
        db.close()


def test_assigned_technician_can_upload_completion_photo(
    tmp_path,
    monkeypatch,
):
    from app.services.completion_document_storage import (
        CompletionDocumentStorage,
    )

    def test_storage_init(self):
        self.root_dir = tmp_path

    monkeypatch.setattr(
        CompletionDocumentStorage,
        "__init__",
        test_storage_init,
    )

    db = TestingSessionLocal()

    try:
        _, job = _create_tech_and_job(db)

        _complete_job(job.id)

        response = client.post(
            f"/jobs/{job.id}/completion-documents/photos",
            data={"category": "AFTER"},
            files={
                "file": (
                    "after.jpg",
                    b"test-image-data",
                    "image/jpeg",
                )
            },
        )

        assert response.status_code == 201, response.text

        data = response.json()

        assert data["job_id"] == job.id
        assert data["job_closure_id"] > 0
        assert data["tenant_id"] == "tenant-1"
        assert data["category"] == "AFTER"
        assert data["original_filename"] == "after.jpg"
        assert data["content_type"] == "image/jpeg"
        assert data["file_size"] == len(b"test-image-data")

        # Newly uploaded completion photos must remain PENDING
        # until an approval/scanning process marks them AVAILABLE.
        assert data["status"] == "PENDING"

        document = (
            db.query(CompletionDocument)
            .filter(CompletionDocument.job_id == job.id)
            .one()
        )

        assert document.category == "AFTER"
        assert document.tenant_id == "tenant-1"
        assert document.storage_key
        assert document.status == "PENDING"

    finally:
        db.close()


def test_cross_tenant_job_is_not_accessible():
    db = TestingSessionLocal()

    try:
        _, job = _create_tech_and_job(
            db,
            tech_id="tenant-2-tech",
            tenant_id="tenant-2",
        )

        # Create a technician record for the authenticated tenant/user.
        # The job still belongs to tenant-2, so the route must reject it
        # at the tenant-scoped job lookup.
        _create_tech_and_job(
            db,
            tech_id="tenant-1-tech",
            tenant_id="tenant-1",
        )

        _set_user(
            user_id="tenant-1-tech",
            tenant_id="tenant-1",
            role=UserRole.TECHNICIAN,
        )

        response = client.post(
            f"/jobs/{job.id}/completion-documents/photos",
            data={"category": "AFTER"},
            files={
                "file": (
                    "after.jpg",
                    b"test-image-data",
                    "image/jpeg",
                )
            },
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Job not found"

    finally:
        db.close()


def test_non_technician_cannot_upload_completion_photo():
    db = TestingSessionLocal()

    try:
        _, job = _create_tech_and_job(db)

        _set_user(
            user_id="tech-123",
            tenant_id="tenant-1",
            role=UserRole.DISPATCHER,
        )

        response = client.post(
            f"/jobs/{job.id}/completion-documents/photos",
            data={"category": "AFTER"},
            files={
                "file": (
                    "after.jpg",
                    b"test-image-data",
                    "image/jpeg",
                )
            },
        )

        assert response.status_code == 403

    finally:
        db.close()


def test_storage_failure_does_not_create_database_reference(
    tmp_path,
    monkeypatch,
):
    from app.services.completion_document_storage import (
        CompletionDocumentStorage,
    )

    def test_storage_init(self):
        self.root_dir = tmp_path

    monkeypatch.setattr(
        CompletionDocumentStorage,
        "__init__",
        test_storage_init,
    )

    def failing_save(self, file, storage_key):
        raise RuntimeError("Simulated storage failure")

    monkeypatch.setattr(
        CompletionDocumentStorage,
        "save",
        failing_save,
    )

    db = TestingSessionLocal()

    try:
        _, job = _create_tech_and_job(db)

        _complete_job(job.id)

        response = client.post(
            f"/jobs/{job.id}/completion-documents/photos",
            data={"category": "AFTER"},
            files={
                "file": (
                    "after.jpg",
                    b"test-image-data",
                    "image/jpeg",
                )
            },
        )

        assert response.status_code == 500
        assert response.json()["detail"] == "Failed to store completion photo"

        document_count = (
            db.query(CompletionDocument)
            .filter(CompletionDocument.job_id == job.id)
            .count()
        )

        assert document_count == 0

    finally:
        db.close()


def test_duplicate_filenames_generate_unique_storage_keys(
    tmp_path,
    monkeypatch,
):
    from app.services.completion_document_storage import (
        CompletionDocumentStorage,
    )

    def test_storage_init(self):
        self.root_dir = tmp_path

    monkeypatch.setattr(
        CompletionDocumentStorage,
        "__init__",
        test_storage_init,
    )

    db = TestingSessionLocal()

    try:
        _, job = _create_tech_and_job(db)

        _complete_job(job.id)

        first_response = client.post(
            f"/jobs/{job.id}/completion-documents/photos",
            data={"category": "AFTER"},
            files={
                "file": (
                    "after.jpg",
                    b"first-image-data",
                    "image/jpeg",
                )
            },
        )

        assert first_response.status_code == 201, first_response.text

        second_response = client.post(
            f"/jobs/{job.id}/completion-documents/photos",
            data={"category": "AFTER"},
            files={
                "file": (
                    "after.jpg",
                    b"second-image-data",
                    "image/jpeg",
                )
            },
        )

        assert second_response.status_code == 201, second_response.text

        first_data = first_response.json()
        second_data = second_response.json()

        assert first_data["original_filename"] == "after.jpg"
        assert second_data["original_filename"] == "after.jpg"

        assert first_data["storage_key"] != second_data["storage_key"]

        documents = (
            db.query(CompletionDocument)
            .filter(CompletionDocument.job_id == job.id)
            .all()
        )

        assert len(documents) == 2

        storage_keys = {document.storage_key for document in documents}

        assert len(storage_keys) == 2

    finally:
        db.close()



def test_invalid_image_type_is_rejected():
    db = TestingSessionLocal()

    try:
        _, job = _create_tech_and_job(db)

        _complete_job(job.id)

        response = client.post(
            f"/jobs/{job.id}/completion-documents/photos",
            data={"category": "AFTER"},
            files={
                "file": (
                    "malicious.exe",
                    b"not-an-image",
                    "application/octet-stream",
                )
            },
        )

        assert response.status_code == 422
        assert "Unsupported image type" in response.json()["detail"]

        document_count = (
            db.query(CompletionDocument)
            .filter(CompletionDocument.job_id == job.id)
            .count()
        )

        assert document_count == 0

    finally:
        db.close()


def test_oversized_image_is_rejected():
    db = TestingSessionLocal()

    try:
        _, job = _create_tech_and_job(db)

        _complete_job(job.id)

        # Test the validator directly so the test verifies the
        # completion-document size rule without depending on the
        # application's global HTTP request-size middleware.
        oversized_image = b"x" * (
            CompletionDocumentValidator.MAX_FILE_SIZE + 1
        )

        with pytest.raises(
            CompletionDocumentValidationError,
            match="must not exceed 10 MB",
        ):
            CompletionDocumentValidator.validate_file(
                file=io.BytesIO(oversized_image),
                content_type="image/jpeg",
                filename="large.jpg",
            )

        document_count = (
            db.query(CompletionDocument)
            .filter(CompletionDocument.job_id == job.id)
            .count()
        )

        assert document_count == 0

    finally:
        db.close()


def test_successful_upload_creates_audit_event(tmp_path, monkeypatch):
    from app.services.completion_document_storage import (
        CompletionDocumentStorage,
    )

    def test_storage_init(self):
        self.root_dir = tmp_path

    monkeypatch.setattr(
        CompletionDocumentStorage,
        "__init__",
        test_storage_init,
    )

    db = TestingSessionLocal()

    try:
        technician, job = _create_tech_and_job(db)

        _complete_job(job.id)

        response = client.post(
            f"/jobs/{job.id}/completion-documents/photos",
            data={"category": "AFTER"},
            files={
                "file": (
                    "after.jpg",
                    b"test-image-data",
                    "image/jpeg",
                )
            },
        )

        assert response.status_code == 201, response.text

        document_data = response.json()

        audit_event = (
            db.query(AuditEvent)
            .filter(
                AuditEvent.job_id == str(job.id),
                AuditEvent.event_type
                == "COMPLETION_DOCUMENT_UPLOADED",
            )
            .order_by(AuditEvent.id.desc())
            .first()
        )

        assert audit_event is not None
        assert audit_event.tenant_id == "tenant-1"
        assert audit_event.tech_id == technician.tech_id
        assert audit_event.actor_id == "tech-123"

        assert audit_event.details is not None
        assert (
            audit_event.details["completion_document_id"]
            == document_data["id"]
        )
        assert (
            audit_event.details["job_closure_id"]
            == document_data["job_closure_id"]
        )
        assert audit_event.details["category"] == "AFTER"
        assert audit_event.details["original_filename"] == "after.jpg"
        assert audit_event.details["content_type"] == "image/jpeg"
        assert audit_event.details["file_size"] == len(b"test-image-data")
        assert (
            audit_event.details["checksum_sha256"]
            == document_data["checksum_sha256"]
        )
        assert (
            audit_event.details["storage_key"]
            == document_data["storage_key"]
        )

    finally:
        db.close()

def test_assigned_technician_can_download_available_photo(
    tmp_path,
    monkeypatch,
):
    from app.services.completion_document_storage import (
        CompletionDocumentStorage,
    )

    def test_storage_init(self):
        self.root_dir = tmp_path

    monkeypatch.setattr(
        CompletionDocumentStorage,
        "__init__",
        test_storage_init,
    )

    db = TestingSessionLocal()

    try:
        _, job = _create_tech_and_job(db)

        _complete_job(job.id)

        upload_response = client.post(
            f"/jobs/{job.id}/completion-documents/photos",
            data={"category": "AFTER"},
            files={
                "file": (
                    "after.jpg",
                    b"download-test-image",
                    "image/jpeg",
                )
            },
        )

        assert upload_response.status_code == 201

        document_data = upload_response.json()
        document_id = document_data["id"]

        # Every new upload starts as PENDING.
        assert document_data["status"] == "PENDING"

        # Simulate the approval/scanning process.
        # Only AVAILABLE documents may be downloaded.
        document = (
            db.query(CompletionDocument)
            .filter(CompletionDocument.id == document_id)
            .first()
        )

        assert document is not None
        assert document.status == "PENDING"

        document.status = "AVAILABLE"
        db.commit()
        db.refresh(document)

        assert document.status == "AVAILABLE"

        download_response = client.get(
            f"/jobs/{job.id}/completion-documents/"
            f"{document_id}/download"
        )

        assert download_response.status_code == 200
        assert download_response.content == b"download-test-image"
        assert download_response.headers["content-type"].startswith(
            "image/jpeg"
        )

    finally:
        db.close()

def test_wrong_technician_cannot_download_photo(
    tmp_path,
    monkeypatch,
):
    from app.services.completion_document_storage import (
        CompletionDocumentStorage,
    )

    def test_storage_init(self):
        self.root_dir = tmp_path

    monkeypatch.setattr(
        CompletionDocumentStorage,
        "__init__",
        test_storage_init,
    )

    db = TestingSessionLocal()

    try:
        technician, job = _create_tech_and_job(db)

        _complete_job(job.id)

        upload_response = client.post(
            f"/jobs/{job.id}/completion-documents/photos",
            data={"category": "AFTER"},
            files={
                "file": (
                    "after.jpg",
                    b"private-image",
                    "image/jpeg",
                )
            },
        )

        assert upload_response.status_code == 201

        document_id = upload_response.json()["id"]

        wrong_technician, _ = _create_tech_and_job(
            db,
            tech_id="wrong-download-tech",
            tenant_id="tenant-1",
        )

        _set_user(
            user_id="wrong-download-tech",
            tenant_id="tenant-1",
            role=UserRole.TECHNICIAN,
        )

        response = client.get(
            f"/jobs/{job.id}/completion-documents/"
            f"{document_id}/download"
        )

        assert response.status_code == 403
        assert response.json()["detail"] == (
            "This job is not assigned to you"
        )

    finally:
        db.close()


def test_cross_tenant_document_cannot_be_downloaded(
    tmp_path,
    monkeypatch,
):
    from app.services.completion_document_storage import (
        CompletionDocumentStorage,
    )

    def test_storage_init(self):
        self.root_dir = tmp_path

    monkeypatch.setattr(
        CompletionDocumentStorage,
        "__init__",
        test_storage_init,
    )

    db = TestingSessionLocal()

    try:
        # Create the job in tenant-2.
        _, job = _create_tech_and_job(
            db,
            tech_id="tenant-2-tech",
            tenant_id="tenant-2",
        )

        # Authenticate as the tenant-2 technician so the job can
        # legitimately be completed.
        _set_user(
            user_id="tenant-2-tech",
            tenant_id="tenant-2",
            role=UserRole.TECHNICIAN,
        )

        _complete_job(job.id)

        # Upload the document while authenticated as tenant-2.
        upload_response = client.post(
            f"/jobs/{job.id}/completion-documents/photos",
            data={"category": "AFTER"},
            files={
                "file": (
                    "after.jpg",
                    b"tenant-two-image",
                    "image/jpeg",
                )
            },
        )

        assert upload_response.status_code == 201, upload_response.text

        document_id = upload_response.json()["id"]

        # Now authenticate as a technician from tenant-1.
        _create_tech_and_job(
            db,
            tech_id="tenant-1-tech",
            tenant_id="tenant-1",
        )

        _set_user(
            user_id="tenant-1-tech",
            tenant_id="tenant-1",
            role=UserRole.TECHNICIAN,
        )

        # Tenant-1 must not be able to access tenant-2's document.
        response = client.get(
            f"/jobs/{job.id}/completion-documents/"
            f"{document_id}/download"
        )

        assert response.status_code == 404
        assert response.json()["detail"] == (
            "Completion document not found"
        )

    finally:
        db.close()


def test_pending_document_cannot_be_downloaded(
    tmp_path,
    monkeypatch,
):
    from app.services.completion_document_storage import (
        CompletionDocumentStorage,
    )

    def test_storage_init(self):
        self.root_dir = tmp_path

    monkeypatch.setattr(
        CompletionDocumentStorage,
        "__init__",
        test_storage_init,
    )

    db = TestingSessionLocal()

    try:
        technician, job = _create_tech_and_job(db)

        _complete_job(job.id)

        upload_response = client.post(
            f"/jobs/{job.id}/completion-documents/photos",
            data={"category": "AFTER"},
            files={
                "file": (
                    "pending.jpg",
                    b"pending-image",
                    "image/jpeg",
                )
            },
        )

        assert upload_response.status_code == 201

        document_id = upload_response.json()["id"]

        document = db.query(CompletionDocument).filter(
            CompletionDocument.id == document_id
        ).first()

        assert document is not None

        document.status = "PENDING"
        db.commit()

        _set_user(
            user_id="tech-123",
            tenant_id="tenant-1",
            role=UserRole.TECHNICIAN,
        )

        response = client.get(
            f"/jobs/{job.id}/completion-documents/"
            f"{document_id}/download"
        )

        assert response.status_code == 403
        assert response.json()["detail"] == (
            "Completion document is not available for download"
        )

    finally:
        db.close()


def test_rejected_document_cannot_be_downloaded(
    tmp_path,
    monkeypatch,
):
    from app.services.completion_document_storage import (
        CompletionDocumentStorage,
    )

    def test_storage_init(self):
        self.root_dir = tmp_path

    monkeypatch.setattr(
        CompletionDocumentStorage,
        "__init__",
        test_storage_init,
    )

    db = TestingSessionLocal()

    try:
        _, job = _create_tech_and_job(db)

        _complete_job(job.id)

        upload_response = client.post(
            f"/jobs/{job.id}/completion-documents/photos",
            data={"category": "AFTER"},
            files={
                "file": (
                    "rejected.jpg",
                    b"rejected-image",
                    "image/jpeg",
                )
            },
        )

        assert upload_response.status_code == 201

        document_id = upload_response.json()["id"]

        document = db.query(CompletionDocument).filter(
            CompletionDocument.id == document_id
        ).first()

        assert document is not None

        document.status = "REJECTED"
        db.commit()

        _set_user(
            user_id="tech-123",
            tenant_id="tenant-1",
            role=UserRole.TECHNICIAN,
        )

        response = client.get(
            f"/jobs/{job.id}/completion-documents/"
            f"{document_id}/download"
        )

        assert response.status_code == 403
        assert response.json()["detail"] == (
            "Completion document is not available for download"
        )

    finally:
        db.close()


def test_missing_storage_file_returns_404(
    tmp_path,
    monkeypatch,
):
    from app.services.completion_document_storage import (
        CompletionDocumentStorage,
    )

    def test_storage_init(self):
        self.root_dir = tmp_path

    monkeypatch.setattr(
        CompletionDocumentStorage,
        "__init__",
        test_storage_init,
    )

    db = TestingSessionLocal()

    try:
        _, job = _create_tech_and_job(db)

        _complete_job(job.id)

        upload_response = client.post(
            f"/jobs/{job.id}/completion-documents/photos",
            data={"category": "AFTER"},
            files={
                "file": (
                    "missing.jpg",
                    b"missing-file-image",
                    "image/jpeg",
                )
            },
        )

        assert upload_response.status_code == 201

        document_id = upload_response.json()["id"]

        document = (
            db.query(CompletionDocument)
            .filter(CompletionDocument.id == document_id)
            .first()
        )

        assert document is not None

        # Simulate successful approval/scanning.
        document.status = "AVAILABLE"
        db.commit()
        db.refresh(document)

        assert document.status == "AVAILABLE"

        storage_path = tmp_path / document.storage_key

        assert storage_path.exists()

        # Simulate the physical storage file being deleted/missing.
        storage_path.unlink()

        response = client.get(
            f"/jobs/{job.id}/completion-documents/"
            f"{document_id}/download"
        )

        assert response.status_code == 404
        assert response.json()["detail"] == (
            "Stored completion document not found"
        )

    finally:
        db.close()

def test_assigned_technician_can_delete_completion_photo(
    tmp_path,
    monkeypatch,
):
    from app.services.completion_document_storage import (
        CompletionDocumentStorage,
    )

    def test_storage_init(self):
        self.root_dir = tmp_path

    monkeypatch.setattr(
        CompletionDocumentStorage,
        "__init__",
        test_storage_init,
    )

    db = TestingSessionLocal()

    try:
        _, job = _create_tech_and_job(
            db,
            tech_id="delete-tech",
            tenant_id="tenant-1",
        )

        _set_user(
            user_id="delete-tech",
            tenant_id="tenant-1",
            role=UserRole.TECHNICIAN,
        )

        _complete_job(job.id)

        upload_response = client.post(
            f"/jobs/{job.id}/completion-documents/photos",
            data={"category": "AFTER"},
            files={
                "file": (
                    "delete.jpg",
                    b"image-to-delete",
                    "image/jpeg",
                )
            },
        )

        assert upload_response.status_code == 201

        document_id = upload_response.json()["id"]
        storage_key = upload_response.json()["storage_key"]

        stored_file = tmp_path / storage_key

        assert stored_file.is_file()

        delete_response = client.delete(
            f"/jobs/{job.id}/completion-documents/{document_id}"
        )

        assert delete_response.status_code == 204

        assert not stored_file.exists()

        document = (
            db.query(CompletionDocument)
            .filter(CompletionDocument.id == document_id)
            .first()
        )

        assert document is None

    finally:
        db.close()


def test_wrong_technician_cannot_delete_completion_photo(
    tmp_path,
    monkeypatch,
):
    from app.services.completion_document_storage import (
        CompletionDocumentStorage,
    )

    def test_storage_init(self):
        self.root_dir = tmp_path

    monkeypatch.setattr(
        CompletionDocumentStorage,
        "__init__",
        test_storage_init,
    )

    db = TestingSessionLocal()

    try:
        _, job = _create_tech_and_job(
            db,
            tech_id="owner-tech",
            tenant_id="tenant-1",
        )

        _set_user(
            user_id="owner-tech",
            tenant_id="tenant-1",
            role=UserRole.TECHNICIAN,
        )

        _complete_job(job.id)

        upload_response = client.post(
            f"/jobs/{job.id}/completion-documents/photos",
            data={"category": "AFTER"},
            files={
                "file": (
                    "protected.jpg",
                    b"protected-image",
                    "image/jpeg",
                )
            },
        )

        assert upload_response.status_code == 201

        document_id = upload_response.json()["id"]

        _create_tech_and_job(
            db,
            tech_id="other-tech",
            tenant_id="tenant-1",
        )

        _set_user(
            user_id="other-tech",
            tenant_id="tenant-1",
            role=UserRole.TECHNICIAN,
        )

        response = client.delete(
            f"/jobs/{job.id}/completion-documents/{document_id}"
        )

        assert response.status_code == 403
        assert response.json()["detail"] == (
            "This job is not assigned to you"
        )

    finally:
        db.close()


def test_cross_tenant_technician_cannot_delete_completion_photo(
    tmp_path,
    monkeypatch,
):
    from app.services.completion_document_storage import (
        CompletionDocumentStorage,
    )

    def test_storage_init(self):
        self.root_dir = tmp_path

    monkeypatch.setattr(
        CompletionDocumentStorage,
        "__init__",
        test_storage_init,
    )

    db = TestingSessionLocal()

    try:
        _, job = _create_tech_and_job(
            db,
            tech_id="tenant-two-owner",
            tenant_id="tenant-2",
        )

        _set_user(
            user_id="tenant-two-owner",
            tenant_id="tenant-2",
            role=UserRole.TECHNICIAN,
        )

        _complete_job(job.id)

        upload_response = client.post(
            f"/jobs/{job.id}/completion-documents/photos",
            data={"category": "AFTER"},
            files={
                "file": (
                    "tenant-two.jpg",
                    b"tenant-two-image",
                    "image/jpeg",
                )
            },
        )

        assert upload_response.status_code == 201

        document_id = upload_response.json()["id"]

        _create_tech_and_job(
            db,
            tech_id="tenant-one-user",
            tenant_id="tenant-1",
        )

        _set_user(
            user_id="tenant-one-user",
            tenant_id="tenant-1",
            role=UserRole.TECHNICIAN,
        )

        response = client.delete(
            f"/jobs/{job.id}/completion-documents/{document_id}"
        )

        assert response.status_code == 404
        assert response.json()["detail"] == (
            "Completion document not found"
        )

    finally:
        db.close()


def test_upload_audit_event_has_timestamp_and_correlation_id(
    tmp_path,
    monkeypatch,
):
    from app.services.completion_document_storage import (
        CompletionDocumentStorage,
    )

    def test_storage_init(self):
        self.root_dir = tmp_path

    monkeypatch.setattr(
        CompletionDocumentStorage,
        "__init__",
        test_storage_init,
    )

    db = TestingSessionLocal()

    try:
        _, job = _create_tech_and_job(db)

        _complete_job(job.id)

        response = client.post(
            f"/jobs/{job.id}/completion-documents/photos",
            data={"category": "AFTER"},
            files={
                "file": (
                    "audit.jpg",
                    b"audit-image",
                    "image/jpeg",
                )
            },
        )

        assert response.status_code == 201

        audit_event = (
            db.query(AuditEvent)
            .filter(
                AuditEvent.job_id == str(job.id),
                AuditEvent.event_type
                == "COMPLETION_DOCUMENT_UPLOADED",
            )
            .order_by(AuditEvent.id.desc())
            .first()
        )

        assert audit_event is not None

        # The application generates the request correlation ID.
        # Verify that the audit event received one.
        assert audit_event.timestamp is not None
        assert audit_event.correlation_id is not None
        assert len(audit_event.correlation_id) > 0

    finally:
        db.close()