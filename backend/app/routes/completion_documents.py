"""
Completion document routes.

Handles secure upload, scan-state tracking, download protection,
and deletion of completion documents.

Raw binary data is never stored in PostgreSQL.
"""

import logging
from datetime import datetime, timezone

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    AuthenticatedUser,
    require_permission,
)
from app.auth.rbac import Permission
from app.context import correlation_id_ctx
from app.database import get_db
from app.models import AuditEvent, CompletionDocument, Job
from app.models.job_closure import JobClosure
from app.repositories import CompletionDocumentRepository
from app.routes.jobs import get_technician_for_current_user
from app.services.completion_document_storage import (
    CompletionDocumentStorage,
)
from app.services.completion_document_validation import (
    CompletionDocumentValidator,
)
from app.services.file_scan_service import FileScanService


logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/jobs",
    tags=["Completion Documents"],
)


class CompletionDocumentResponse(BaseModel):
    id: int
    job_id: int
    job_closure_id: int
    tenant_id: str
    category: str
    document_type: str
    original_filename: str
    content_type: str
    file_size: int
    checksum_sha256: str
    storage_key: str
    status: str
    scan_status: str
    scanned_at: datetime | None
    uploaded_by: str

    model_config = ConfigDict(
        from_attributes=True,
    )


# =====================================================================
# UPLOAD
# =====================================================================


@router.post(
    "/{job_id}/completion-documents/photos",
    response_model=CompletionDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_completion_photo(
    job_id: int,
    category: str = Form(...),
    file: UploadFile = File(...),
    current_user: AuthenticatedUser = Depends(
        require_permission(
            Permission.COMPLETION_DOCUMENTS_MANAGE
        )
    ),
    db: Session = Depends(get_db),
):
    # ---------------------------------------------------------------
    # Repository
    # ---------------------------------------------------------------

    document_repository = CompletionDocumentRepository(db)

    # ---------------------------------------------------------------
    # Resolve authenticated technician
    # ---------------------------------------------------------------

    technician = get_technician_for_current_user(
        db,
        current_user,
    )

    if not technician:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Technician not found",
        )

    # ---------------------------------------------------------------
    # Tenant-scoped job lookup
    # ---------------------------------------------------------------

    job = (
        db.query(Job)
        .filter(
            Job.id == job_id,
            Job.tenant_id == current_user.tenant_id,
        )
        .first()
    )

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    # ---------------------------------------------------------------
    # Technician ownership
    # ---------------------------------------------------------------

    if job.assigned_technician_id != technician.technician_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This job is not assigned to you",
        )

    # ---------------------------------------------------------------
    # Completion record must already exist
    # ---------------------------------------------------------------

    closure = (
        db.query(JobClosure)
        .filter(
            JobClosure.job_id == job.id,
            JobClosure.tenant_id == current_user.tenant_id,
        )
        .first()
    )

    if not closure:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Job must have a completion record "
                "before uploading photos"
            ),
        )

    # ---------------------------------------------------------------
    # Validate uploaded image
    # ---------------------------------------------------------------

    try:
        normalized_category = (
            CompletionDocumentValidator.validate_category(
                category
            )
        )

        (
            content_type,
            safe_filename,
            file_size,
            checksum,
        ) = CompletionDocumentValidator.validate_file(
            file=file.file,
            content_type=file.content_type or "",
            filename=file.filename or "",
            document_type="PHOTO",
            category=normalized_category,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    # ---------------------------------------------------------------
    # Generate unique storage key
    # ---------------------------------------------------------------

    storage = CompletionDocumentStorage()

    storage_key = storage.generate_storage_key(
        tenant_id=str(current_user.tenant_id),
        job_id=job.id,
        job_closure_id=closure.id,
        category=normalized_category,
        original_filename=safe_filename,
    )

    # ---------------------------------------------------------------
    # Store binary outside the database
    # ---------------------------------------------------------------

    try:
        storage.save(
            file=file.file,
            storage_key=storage_key,
        )

    except Exception as exc:
        try:
            storage.delete(storage_key)
        except Exception:
            pass

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store completion photo",
        ) from exc

    # ---------------------------------------------------------------
    # Create completion document metadata
    #
    # New uploads start with PENDING scan state.
    # ---------------------------------------------------------------

    document = CompletionDocument(
        job_closure_id=closure.id,
        job_id=job.id,
        tenant_id=str(current_user.tenant_id),
        uploaded_by=str(current_user.user_id),
        document_type="PHOTO",
        category=normalized_category,
        original_filename=safe_filename,
        content_type=content_type,
        file_size=file_size,
        checksum_sha256=checksum,
        storage_key=storage_key,
        storage_url=None,
        status="PENDING",
        scan_status="PENDING",
        scanned_at=None,
    )

    try:
        # -----------------------------------------------------------
        # Persist document and generate document.id
        # -----------------------------------------------------------

        document_repository.create(document)

        # -----------------------------------------------------------
        # Scan stored completion document
        # -----------------------------------------------------------

        scan_failed = False

        try:
            scan_result = FileScanService(storage).scan(
                document
            )

            document.scan_status = (
                scan_result.scan_status
            )

            document.scanned_at = (
                scan_result.scanned_at
            )

            # A rejected scan also makes the overall document
            # rejected.
            if scan_result.scan_status == "REJECTED":
                document.status = "REJECTED"

        except Exception:
            # Fail closed:
            #
            # - keep scan_status=PENDING
            # - keep status=PENDING
            # - keep scanned_at=NULL
            # - prevent download through the scan gate
            #
            # Scanner internals are logged server-side only.
            scan_failed = True

            document.scan_status = "PENDING"
            document.scanned_at = None
            document.status = "PENDING"

            logger.exception(
                "Completion document scan failed",
                extra={
                    "completion_document_id": document.id,
                    "job_id": job.id,
                    "tenant_id": str(
                        current_user.tenant_id
                    ),
                },
            )

        # -----------------------------------------------------------
        # Upload audit event
        # -----------------------------------------------------------

        upload_audit_event = AuditEvent(
            tech_id=str(technician.tech_id),
            tenant_id=str(current_user.tenant_id),
            event_type="COMPLETION_DOCUMENT_UPLOADED",
            old_status=None,
            new_status="PENDING",
            job_id=str(job.id),
            actor_id=str(current_user.user_id),
            timestamp=datetime.now(timezone.utc),
            correlation_id=correlation_id_ctx.get() or None,
            details={
                "completion_document_id": document.id,
                "job_closure_id": closure.id,
                "document_type": "PHOTO",
                "category": normalized_category,
                "original_filename": safe_filename,
                "content_type": content_type,
                "file_size": file_size,
                "checksum_sha256": checksum,
                "storage_key": storage_key,
            },
        )

        db.add(upload_audit_event)

        # -----------------------------------------------------------
        # Scan audit event
        # -----------------------------------------------------------

        if scan_failed:
            scan_audit_event = AuditEvent(
                tech_id=str(technician.tech_id),
                tenant_id=str(
                    current_user.tenant_id
                ),
                event_type=(
                    "COMPLETION_DOCUMENT_SCAN_FAILED"
                ),
                old_status="PENDING",
                new_status="PENDING",
                job_id=str(job.id),
                actor_id=str(current_user.user_id),
                timestamp=datetime.now(timezone.utc),
                correlation_id=(
                    correlation_id_ctx.get() or None
                ),
                details={
                    "completion_document_id": document.id,
                    "job_closure_id": closure.id,
                    "scan_status": "PENDING",
                },
            )

        else:
            scan_audit_event = AuditEvent(
                tech_id=str(technician.tech_id),
                tenant_id=str(
                    current_user.tenant_id
                ),
                event_type=(
                    "COMPLETION_DOCUMENT_SCANNED"
                ),
                old_status="PENDING",
                new_status=document.scan_status,
                job_id=str(job.id),
                actor_id=str(current_user.user_id),
                timestamp=(
                    document.scanned_at
                    or datetime.now(timezone.utc)
                ),
                correlation_id=(
                    correlation_id_ctx.get() or None
                ),
                details={
                    "completion_document_id": document.id,
                    "job_closure_id": closure.id,
                    "scan_status": document.scan_status,
                    "scanned_at": (
                        document.scanned_at.isoformat()
                        if document.scanned_at
                        else None
                    ),
                },
            )

        db.add(scan_audit_event)

        # -----------------------------------------------------------
        # Document + audit events committed atomically
        # -----------------------------------------------------------

        db.commit()
        db.refresh(document)

    except Exception as exc:
        db.rollback()

        # Remove stored binary if database persistence fails.
        try:
            storage.delete(storage_key)
        except Exception:
            pass

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create completion document",
        ) from exc

    return document


# =====================================================================
# DOWNLOAD
# =====================================================================


@router.get(
    "/{job_id}/completion-documents/{document_id}/download",
)
def download_completion_photo(
    job_id: int,
    document_id: int,
    current_user: AuthenticatedUser = Depends(
        require_permission(
            Permission.COMPLETION_DOCUMENTS_MANAGE
        )
    ),
    db: Session = Depends(get_db),
):
    # ---------------------------------------------------------------
    # Repository
    # ---------------------------------------------------------------

    document_repository = CompletionDocumentRepository(db)

    # ---------------------------------------------------------------
    # Resolve authenticated technician
    # ---------------------------------------------------------------

    technician = get_technician_for_current_user(
        db,
        current_user,
    )

    if not technician:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Technician not found",
        )

    # ---------------------------------------------------------------
    # Tenant-scoped document lookup
    # ---------------------------------------------------------------

    document = document_repository.get_by_id_for_job(
        document_id=document_id,
        job_id=job_id,
        tenant_id=str(current_user.tenant_id),
    )

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Completion document not found",
        )

    # ---------------------------------------------------------------
    # Tenant-scoped job lookup
    # ---------------------------------------------------------------

    job = (
        db.query(Job)
        .filter(
            Job.id == job_id,
            Job.tenant_id == current_user.tenant_id,
        )
        .first()
    )

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    # ---------------------------------------------------------------
    # Technician ownership
    # ---------------------------------------------------------------

    if job.assigned_technician_id != technician.technician_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This job is not assigned to you",
        )

    # ---------------------------------------------------------------
    # Security scan gate
    #
    # Only CLEAN documents can be downloaded.
    #
    # This blocks:
    #   PENDING
    #   REJECTED
    # ---------------------------------------------------------------

    if (
        document.scan_status != "CLEAN"
        or document.status == "REJECTED"
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Completion document is not available for download",
        )
    

    # ---------------------------------------------------------------
    # Physical storage
    # ---------------------------------------------------------------

    storage = CompletionDocumentStorage()

    file_path = storage.root_dir / document.storage_key

    if not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stored completion document not found",
        )

    return FileResponse(
        path=file_path,
        media_type=document.content_type,
        filename=document.original_filename,
    )


# =====================================================================
# DELETE
# =====================================================================


@router.delete(
    "/{job_id}/completion-documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_completion_photo(
    job_id: int,
    document_id: int,
    current_user: AuthenticatedUser = Depends(
        require_permission(
            Permission.COMPLETION_DOCUMENTS_MANAGE
        )
    ),
    db: Session = Depends(get_db),
):
    # ---------------------------------------------------------------
    # Repository
    # ---------------------------------------------------------------

    document_repository = CompletionDocumentRepository(db)

    # ---------------------------------------------------------------
    # Resolve authenticated technician
    # ---------------------------------------------------------------

    technician = get_technician_for_current_user(
        db,
        current_user,
    )

    if not technician:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Technician not found",
        )

    # ---------------------------------------------------------------
    # Tenant-scoped document lookup
    # ---------------------------------------------------------------

    document = document_repository.get_by_id_for_job(
        document_id=document_id,
        job_id=job_id,
        tenant_id=str(current_user.tenant_id),
    )

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Completion document not found",
        )

    # ---------------------------------------------------------------
    # Tenant-scoped job lookup
    # ---------------------------------------------------------------

    job = (
        db.query(Job)
        .filter(
            Job.id == job_id,
            Job.tenant_id == current_user.tenant_id,
        )
        .first()
    )

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    # ---------------------------------------------------------------
    # Technician ownership
    # ---------------------------------------------------------------

    if job.assigned_technician_id != technician.technician_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This job is not assigned to you",
        )

    storage = CompletionDocumentStorage()

    storage_key = document.storage_key

    try:
        # -----------------------------------------------------------
        # Delete physical storage object first
        # -----------------------------------------------------------

        storage.delete(storage_key)

        # -----------------------------------------------------------
        # Create deletion audit event
        # -----------------------------------------------------------

        audit_event = AuditEvent(
            tech_id=str(technician.tech_id),
            tenant_id=str(current_user.tenant_id),
            event_type="COMPLETION_DOCUMENT_DELETED",
            old_status=document.status,
            new_status=None,
            job_id=str(job.id),
            actor_id=str(current_user.user_id),
            timestamp=datetime.now(timezone.utc),
            correlation_id=correlation_id_ctx.get() or None,
            details={
                "completion_document_id": document.id,
                "job_closure_id": document.job_closure_id,
                "document_type": document.document_type,
                "category": document.category,
                "original_filename": document.original_filename,
                "content_type": document.content_type,
                "file_size": document.file_size,
                "checksum_sha256": document.checksum_sha256,
                "storage_key": storage_key,
            },
        )

        db.add(audit_event)

        # -----------------------------------------------------------
        # Remove database reference through repository
        # -----------------------------------------------------------

        document_repository.delete(document)

        # -----------------------------------------------------------
        # Commit document deletion + audit atomically
        # -----------------------------------------------------------

        db.commit()

    except Exception as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete completion document",
        ) from exc

    return None