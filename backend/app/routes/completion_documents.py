from datetime import datetime, timezone
from pathlib import Path

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
    get_current_user,
    require_permission
)
from app.auth.rbac import UserRole,Permission
from app.context import correlation_id_ctx
from app.database import get_db
from app.models import AuditEvent, CompletionDocument, Job
from app.models.job_closure import JobClosure
from app.routes.jobs import get_technician_for_current_user
from app.services.completion_document_storage import (
    CompletionDocumentStorage,
)
from app.services.completion_document_validation import (
    CompletionDocumentValidator,
)


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
    original_filename: str
    content_type: str
    file_size: int
    checksum_sha256: str
    storage_key: str
    status: str
    uploaded_by: str

    model_config = ConfigDict(from_attributes=True)


@router.post(
    "/{job_id}/completion-documents/photos",
    response_model=CompletionDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_completion_photo(
    job_id: int,
    category: str = Form(...),
    file: UploadFile = File(...),
    current_user: AuthenticatedUser = Depends(require_permission(Permission.COMPLETION_DOCUMENTS_MANAGE)),
    db: Session = Depends(get_db),
):
    # ---------------------------------------------------------------
    # Technician role check
    # ---------------------------------------------------------------
 

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
            CompletionDocumentValidator.validate_category(category)
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
    # New uploads remain PENDING until they are approved/scanned.
    # ---------------------------------------------------------------
    document = CompletionDocument(
        job_closure_id=closure.id,
        job_id=job.id,
        tenant_id=str(current_user.tenant_id),
        category=normalized_category,
        original_filename=safe_filename,
        content_type=content_type,
        file_size=file_size,
        checksum_sha256=checksum,
        storage_key=storage_key,
        storage_url=None,
        status="PENDING",
        uploaded_by=str(current_user.user_id),
    )

    try:
        # -----------------------------------------------------------
        # Add document and flush to generate document.id
        # -----------------------------------------------------------
        db.add(document)
        db.flush()

        # -----------------------------------------------------------
        # Create audit event
        # -----------------------------------------------------------
        audit_event = AuditEvent(
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
                "category": normalized_category,
                "original_filename": safe_filename,
                "content_type": content_type,
                "file_size": file_size,
                "checksum_sha256": checksum,
                "storage_key": storage_key,
            },
        )

        db.add(audit_event)

        # -----------------------------------------------------------
        # Document + audit committed atomically
        # -----------------------------------------------------------
        db.commit()
        db.refresh(document)

    except Exception as exc:
        db.rollback()

        # Remove stored binary if database persistence failed.
        try:
            storage.delete(storage_key)
        except Exception:
            pass

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create completion document",
        ) from exc

    return document


@router.get(
    "/{job_id}/completion-documents/{document_id}/download",
)
def download_completion_photo(
    job_id: int,
    document_id: int,
    current_user: AuthenticatedUser = Depends(require_permission(Permission.COMPLETION_DOCUMENTS_MANAGE)),
    db: Session = Depends(get_db),
):
    # ---------------------------------------------------------------
    # Technician role check
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
    document = (
        db.query(CompletionDocument)
        .filter(
            CompletionDocument.id == document_id,
            CompletionDocument.job_id == job_id,
            CompletionDocument.tenant_id == current_user.tenant_id,
        )
        .first()
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
    # Only approved/available documents can be downloaded
    # ---------------------------------------------------------------
    if document.status != "AVAILABLE":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Completion document is not available for download",
        )

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


@router.delete(
    "/{job_id}/completion-documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_completion_photo(
    job_id: int,
    document_id: int,
    current_user: AuthenticatedUser = Depends(require_permission(Permission.COMPLETION_DOCUMENTS_MANAGE)),
    db: Session = Depends(get_db),
):
    # ---------------------------------------------------------------
    # Technician role check
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
    document = (
        db.query(CompletionDocument)
        .filter(
            CompletionDocument.id == document_id,
            CompletionDocument.job_id == job_id,
            CompletionDocument.tenant_id == current_user.tenant_id,
        )
        .first()
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
        # Remove database reference
        # -----------------------------------------------------------
        db.delete(document)
        db.commit()

    except Exception as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete completion document",
        ) from exc

    return None