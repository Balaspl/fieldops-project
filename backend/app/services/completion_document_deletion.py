"""Secure deletion rules for completion documents."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.auth.rbac import Permission, UserRole
from app.models import AuditEvent, CompletionDocument, Job, Technician
from app.repositories import CompletionDocumentRepository
from app.services.completion_document_storage import CompletionDocumentStorage


PROTECTED_JOB_STATUSES = {"COMPLETED", "CLOSED"}


@dataclass(frozen=True)
class CompletionDocumentDeletionResult:
    """Committed deletion result returned to the API layer."""

    document_id: int
    deletion_mode: str
    audit_id: int


class CompletionDocumentDeletionService:
    """
    Apply lifecycle, RBAC and tenant rules for completion-document deletion.

    Rules:

    * Technicians may hard-delete their own unlinked pre-completion uploads.
    * Once a job is COMPLETED/CLOSED, completion evidence is protected.
    * A SUPER_ADMIN may explicitly override that protection; protected evidence
      is soft-deleted so its audit/database history and storage object remain.
    * Customers, dispatchers and HEAD cannot delete completion documents.
    * Every deletion records actor, reason and timestamp in AuditEvent.
    """

    def __init__(
        self,
        db: Session,
        storage: CompletionDocumentStorage | None = None,
    ):
        self.db = db
        self.storage = storage or CompletionDocumentStorage()
        self.repository = CompletionDocumentRepository(db)

    @staticmethod
    def _normalize_status(job: Job) -> str:
        return str(job.status or "").strip().upper()

    @staticmethod
    def _safe_storage_path(
        storage: CompletionDocumentStorage,
        storage_key: str,
    ):
        root = storage.root_dir.resolve()
        file_path = (storage.root_dir / storage_key).resolve()

        if file_path != root and root not in file_path.parents:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Stored completion document not found",
            )

        return file_path

    def _load_document_and_job(
    self,
    *,
    job_id: int,
    document_id: int,
    tenant_id: str,
) -> tuple[Job, CompletionDocument]:

        # -----------------------------------------------------------
        # Look up the document first using tenant + job scope.
        #
        # This ensures cross-tenant access returns the same generic
        # "Completion document not found" response instead of revealing
        # whether another tenant's job exists.
        # -----------------------------------------------------------

        document = self.repository.get_by_id_for_job(
            document_id=document_id,
            job_id=job_id,
            tenant_id=tenant_id,
        )

        if document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Completion document not found",
            )

        # -----------------------------------------------------------
        # Resolve the tenant-scoped job only after the document has
        # been confirmed to belong to the requested tenant + job.
        # -----------------------------------------------------------

        job = (
            self.db.query(Job)
            .filter(
                Job.id == job_id,
                Job.tenant_id == tenant_id,
            )
            .first()
        )

        if job is None:
            # Keep the response generic so callers cannot infer
            # cross-tenant job existence.
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Completion document not found",
            )

        # -----------------------------------------------------------
        # Final consistency validation.
        # -----------------------------------------------------------

        if (
            document.job_id != job.id
            or document.tenant_id != job.tenant_id
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Completion document not found",
            )

        return job, document

    def _authorize_actor(
        self,
        *,
        current_user,
        job: Job,
    ) -> tuple[bool, bool]:

        role = current_user.role
        tenant_id = str(current_user.tenant_id)

        if tenant_id != str(job.tenant_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Completion document not found",
            )

        if role == UserRole.SUPER_ADMIN:
            if not current_user.has_permission(Permission.JOBS_EDIT):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Permission denied: jobs:edit",
                )

            return True, True

        if role != UserRole.TECHNICIAN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Completion document deletion is not permitted "
                    "for this role"
                ),
            )

        if not current_user.has_permission(
            Permission.COMPLETION_DOCUMENTS_MANAGE
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Permission denied: "
                    "completion_documents:manage"
                ),
            )

        user_id = str(current_user.user_id)

        numeric_user_id = (
            int(user_id)
            if user_id.isdigit()
            else -1
        )

        technician = (
            self.db.query(Technician)
            .filter(
                Technician.tenant_id == tenant_id,
                (
                    (Technician.tech_id == user_id)
                    | (
                        Technician.technician_id
                        == numeric_user_id
                    )
                ),
            )
            .first()
        )

        if technician is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Technician not found",
            )

        if (
            job.assigned_technician_id
            != technician.technician_id
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This job is not assigned to you",
            )

        return True, False

    def delete(
        self,
        *,
        job_id: int,
        document_id: int,
        current_user,
        reason: str,
        override: bool = False,
    ) -> CompletionDocumentDeletionResult:

        clean_reason = (reason or "").strip()

        if len(clean_reason) < 3:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Deletion reason must contain "
                    "at least 3 characters"
                ),
            )

        tenant_id = str(current_user.tenant_id)

        job, document = self._load_document_and_job(
            job_id=job_id,
            document_id=document_id,
            tenant_id=tenant_id,
        )

        self._authorize_actor(
            current_user=current_user,
            job=job,
        )

        job_status = self._normalize_status(job)

        protected = (
            job_status in PROTECTED_JOB_STATUSES
            or document.job_closure_id is not None
        )

        is_super_admin = (
            current_user.role == UserRole.SUPER_ADMIN
        )

        if protected and not is_super_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Completion evidence cannot be "
                    "deleted after completion"
                ),
            )

        if (
            protected
            and is_super_admin
            and not override
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Completion document is protected "
                    "after completion; set override=true "
                    "to authorize audited soft deletion"
                ),
            )

        now = datetime.now(timezone.utc)

        deletion_mode = (
            "SOFT"
            if protected
            else "HARD"
        )

        storage_key = document.storage_key

        audit_event = AuditEvent(
            tech_id=None,
            tenant_id=tenant_id,
            event_type="COMPLETION_DOCUMENT_DELETED",
            old_status=document.status,
            new_status="DELETED",
            reason=clean_reason,
            job_id=str(job.id),
            actor_id=str(current_user.user_id),
            timestamp=now,
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
                "deletion_mode": deletion_mode,
                "override": bool(override),
                "job_status": job_status,
                "deleted_at": now.isoformat(),
            },
        )

        try:
            if deletion_mode == "SOFT":
                self.repository.mark_soft_deleted(
                    document,
                    deleted_at=now,
                    deleted_by=str(current_user.user_id),
                    deletion_reason=clean_reason,
                )

                self.db.add(audit_event)
                self.db.flush()

            else:
                self._safe_storage_path(
                    self.storage,
                    storage_key,
                )

                self.storage.delete(storage_key)

                self.repository.delete(document)

                self.db.add(audit_event)
                self.db.flush()

            audit_id = int(audit_event.id)

            self.db.commit()

        except HTTPException:
            self.db.rollback()
            raise

        except Exception as exc:
            self.db.rollback()

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete completion document",
            ) from exc

        return CompletionDocumentDeletionResult(
            document_id=document_id,
            deletion_mode=deletion_mode,
            audit_id=audit_id,
        )