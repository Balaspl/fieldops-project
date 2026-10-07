"""
Authorization service for completion-document access.

Access rules:

- TECHNICIAN:
    Can access documents belonging to jobs assigned to that technician.

- DISPATCHER:
    Can access documents belonging to jobs in their organization.

- SUPER_ADMIN:
    Can access documents belonging to jobs in their organization.

- CUSTOMER:
    Can access documents belonging to their own job.
    Customer ownership is checked using Job.customer_id and
    Job.customer_tenant_id, with ServiceRequest as a safe fallback
    for legacy/routed jobs.

- HEAD:
    Cannot access organization completion documents.

Additional protection:

- Cross-tenant access is denied.
- Soft-deleted documents are inaccessible.
- Rejected documents are inaccessible.
- Unscanned/non-CLEAN documents are inaccessible.
- Storage access must only happen after this authorization succeeds.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth.rbac import Permission, UserRole
from app.models import (
    CompletionDocument,
    Job,
    ServiceRequest,
)
from app.repositories import CompletionDocumentRepository


@dataclass(frozen=True)
class CompletionDocumentAccessResult:
    """
    Result of an authorization check.

    This object deliberately contains no storage URL or storage path.
    Storage access must only occur after authorization succeeds.
    """

    allowed: bool
    job_id: int
    document_id: int
    actor_role: str


class CompletionDocumentAccessService:
    """Authorize access to completion documents."""

    def __init__(self, db: Session):
        self.db = db
        self.repository = CompletionDocumentRepository(db)

    # ------------------------------------------------------------------
    # Generic not-found response
    # ------------------------------------------------------------------

    @staticmethod
    def _not_found() -> HTTPException:
        """
        Return a generic 404 response.

        A generic response prevents callers from learning whether
        another tenant owns the requested job/document.
        """

        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Completion document not found",
        )

    # ------------------------------------------------------------------
    # Role normalization
    # ------------------------------------------------------------------

    @staticmethod
    def _role(current_user) -> UserRole:
        """Normalize the authenticated user's role to UserRole."""

        role = current_user.role

        if isinstance(role, UserRole):
            return role

        try:
            return UserRole(str(role))
        except ValueError:
            raise CompletionDocumentAccessService._not_found()

    # ------------------------------------------------------------------
    # Document + job lookup
    # ------------------------------------------------------------------

    def _load_document(
        self,
        *,
        job_id: int,
        document_id: int,
        tenant_id: str,
        role: UserRole,
    ) -> tuple[Job, CompletionDocument]:

        document = None
        job = None

        # --------------------------------------------------------------
        # Organization roles
        #
        # For organization users, the job tenant is the organization
        # they belong to.
        # --------------------------------------------------------------

        if role in {
            UserRole.SUPER_ADMIN,
            UserRole.DISPATCHER,
            UserRole.TECHNICIAN,
        }:
            document = self.repository.get_by_id_for_job(
                document_id=document_id,
                job_id=job_id,
                tenant_id=tenant_id,
            )

            if document is None:
                raise self._not_found()

            job = (
                self.db.query(Job)
                .filter(
                    Job.id == job_id,
                    Job.tenant_id == tenant_id,
                )
                .first()
            )

            if job is None:
                raise self._not_found()

        # --------------------------------------------------------------
        # Customer
        #
        # Customer tenant is not necessarily the same as the service
        # organization's Job.tenant_id.
        #
        # Therefore customer ownership uses:
        #
        #   Job.customer_id
        #   Job.customer_tenant_id
        #
        # ServiceRequest provides a fallback for legacy/routed jobs.
        # --------------------------------------------------------------

        elif role == UserRole.CUSTOMER:
            job = (
                self.db.query(Job)
                .filter(
                    Job.id == job_id,
                    Job.customer_tenant_id == tenant_id,
                    Job.customer_id == str(
                        current_user.user_id
                    ),
                )
                .first()
            )

        else:
            raise self._not_found()

        # --------------------------------------------------------------
        # Customer fallback
        # --------------------------------------------------------------

        if role == UserRole.CUSTOMER and job is None:
            job = (
                self.db.query(Job)
                .join(
                    ServiceRequest,
                    ServiceRequest.linked_job_id == Job.id,
                )
                .filter(
                    Job.id == job_id,
                    ServiceRequest.linked_job_id == job_id,
                    ServiceRequest.customer_user_id
                    == current_user.user_id,
                    ServiceRequest.tenant_id == tenant_id,
                    or_(
                        Job.customer_id
                        == str(current_user.user_id),
                        Job.customer_id.is_(None),
                    ),
                )
                .first()
            )

            if job is None:
                raise self._not_found()

        # --------------------------------------------------------------
        # Document lookup for customer
        # --------------------------------------------------------------

        if role == UserRole.CUSTOMER:
            document = (
                self.db.query(CompletionDocument)
                .filter(
                    CompletionDocument.id == document_id,
                    CompletionDocument.job_id == job.id,
                    CompletionDocument.deleted_at.is_(None),
                )
                .first()
            )

            if document is None:
                raise self._not_found()

        # --------------------------------------------------------------
        # Final tenant/job consistency check
        # --------------------------------------------------------------

        if document is None or job is None:
            raise self._not_found()

        if document.job_id != job.id:
            raise self._not_found()

        # Organization roles use the service-provider tenant.
        if role != UserRole.CUSTOMER:
            if str(document.tenant_id) != tenant_id:
                raise self._not_found()

            if str(job.tenant_id) != tenant_id:
                raise self._not_found()

        # Customers use customer ownership tenant.
        else:
            if str(job.customer_tenant_id) != tenant_id:
                raise self._not_found()

        if str(document.tenant_id) != str(job.tenant_id):
            # CompletionDocument is stored under the service
            # organization's tenant.
            raise self._not_found()

        return job, document

    # ------------------------------------------------------------------
    # Role-specific ownership
    # ------------------------------------------------------------------

    def _authorize_role(
        self,
        *,
        current_user,
        job: Job,
        role: UserRole,
    ) -> None:

        # --------------------------------------------------------------
        # HEAD
        # --------------------------------------------------------------

        if role == UserRole.HEAD:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Completion document access is not permitted",
            )

        # --------------------------------------------------------------
        # SUPER ADMIN
        # --------------------------------------------------------------

        if role == UserRole.SUPER_ADMIN:
            if not has_user_permission(
                current_user,
                Permission.COMPLETION_DOCUMENTS_VIEW,
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Permission denied",
                )

            return

        # --------------------------------------------------------------
        # DISPATCHER
        # --------------------------------------------------------------

        if role == UserRole.DISPATCHER:
            if not has_user_permission(
                current_user,
                Permission.COMPLETION_DOCUMENTS_VIEW,
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Permission denied",
                )

            return

        # --------------------------------------------------------------
        # TECHNICIAN
        # --------------------------------------------------------------

        if role == UserRole.TECHNICIAN:
            if not has_user_permission(
                current_user,
                Permission.COMPLETION_DOCUMENTS_VIEW,
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Permission denied",
                )

            # Technician may only access assigned jobs.
            technician_id = getattr(
                current_user,
                "user_id",
                None,
            )

            # Job stores assigned technician as its integer PK.
            # The route/model layer already uses the technician lookup,
            # so ownership is checked using the technician record below.
            from app.models import Technician

            numeric_user_id = (
                int(technician_id)
                if technician_id is not None
                and str(technician_id).isdigit()
                else -1
            )

            technician = (
                self.db.query(Technician)
                .filter(
                    Technician.tenant_id
                    == current_user.tenant_id,
                    or_(
                        Technician.tech_id
                        == str(technician_id),
                        Technician.technician_id
                        == numeric_user_id,
                    ),
                )
                .first()
            )

            if technician is None:
                raise self._not_found()

            if (
                job.assigned_technician_id
                != technician.technician_id
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="This job is not assigned to you",
                )

            return

        # --------------------------------------------------------------
        # CUSTOMER
        # --------------------------------------------------------------

        if role == UserRole.CUSTOMER:
            if not has_user_permission(
                current_user,
                Permission.COMPLETION_DOCUMENTS_VIEW,
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Permission denied",
                )

            if (
                str(job.customer_tenant_id)
                != str(current_user.tenant_id)
            ):
                raise self._not_found()

            if (
                job.customer_id is not None
                and str(job.customer_id)
                != str(current_user.user_id)
            ):
                raise self._not_found()

            return

        raise self._not_found()

    # ------------------------------------------------------------------
    # Document lifecycle protection
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_document_state(
        document: CompletionDocument,
    ) -> None:

        # Soft-deleted documents are inaccessible.
        if document.deleted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Completion document not found",
            )

        # Rejected documents are inaccessible.
        if document.status == "REJECTED":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Completion document is not available "
                    "for download"
                ),
            )

        # Only CLEAN documents may reach storage.
        if document.scan_status != "CLEAN":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Completion document is not available "
                    "for download"
                ),
            )

    # ------------------------------------------------------------------
    # Public authorization API
    # ------------------------------------------------------------------

    def authorize(
        self,
        *,
        job_id: int,
        document_id: int,
        current_user,
    ) -> tuple[Job, CompletionDocument, CompletionDocumentAccessResult]:

        role = self._role(current_user)

        tenant_id = str(
            current_user.tenant_id
        )

        job, document = self._load_document(
            job_id=job_id,
            document_id=document_id,
            tenant_id=tenant_id,
            role=role,
        )

        # IMPORTANT:
        # Authorization happens before any storage access.
        self._authorize_role(
            current_user=current_user,
            job=job,
            role=role,
        )

        # IMPORTANT:
        # Scan/deletion state is checked before storage URL/path generation.
        self._validate_document_state(document)

        result = CompletionDocumentAccessResult(
            allowed=True,
            job_id=job.id,
            document_id=document.id,
            actor_role=role.value,
        )

        return job, document, result


def has_user_permission(
    current_user,
    permission: Permission,
) -> bool:
    """
    Check whether the authenticated user has the requested
    RBAC permission.

    AuthenticatedUser.has_permission() is the canonical
    permission-checking implementation for FieldOps.
    """

    try:
        return current_user.has_permission(permission)
    except (AttributeError, TypeError):
        return False