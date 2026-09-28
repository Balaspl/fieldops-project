"""
Repository responsible for CompletionDocument database operations.

This repository contains database access only.

Business rules, authorization, file validation and lifecycle
decisions belong to the service/route layer.
"""

from typing import Optional

from sqlalchemy.orm import Session

from app.models import CompletionDocument


class CompletionDocumentRepository:
    """
    Database repository for completion documents.
    """

    def __init__(self, db: Session):
        self.db = db

    # -----------------------------------------------------------------
    # Basic lookup
    # -----------------------------------------------------------------

    def get_by_id(
        self,
        document_id: int,
    ) -> Optional[CompletionDocument]:
        return (
            self.db.query(CompletionDocument)
            .filter(
                CompletionDocument.id == document_id,
            )
            .first()
        )

    # -----------------------------------------------------------------
    # Tenant + job scoped lookup
    # -----------------------------------------------------------------

    def get_by_id_for_job(
        self,
        document_id: int,
        job_id: int,
        tenant_id: str,
    ) -> Optional[CompletionDocument]:
        """
        Return one document only when it belongs to both the
        requested job and tenant.
        """

        return (
            self.db.query(CompletionDocument)
            .filter(
                CompletionDocument.id == document_id,
                CompletionDocument.job_id == job_id,
                CompletionDocument.tenant_id == tenant_id,
            )
            .first()
        )

    # -----------------------------------------------------------------
    # List documents for a job
    # -----------------------------------------------------------------

    def list_for_job(
        self,
        job_id: int,
        tenant_id: str,
    ) -> list[CompletionDocument]:
        """
        Return all completion documents belonging to the
        requested job and tenant.
        """

        return (
            self.db.query(CompletionDocument)
            .filter(
                CompletionDocument.job_id == job_id,
                CompletionDocument.tenant_id == tenant_id,
            )
            .order_by(
                CompletionDocument.created_at.asc()
            )
            .all()
        )

    # -----------------------------------------------------------------
    # Find documents uploaded before a JobClosure existed
    # -----------------------------------------------------------------

    def list_unlinked_for_job(
        self,
        job_id: int,
        tenant_id: str,
    ) -> list[CompletionDocument]:
        """
        Return completion documents that belong to the requested
        job and tenant but are not yet attached to a JobClosure.
        """

        return (
            self.db.query(CompletionDocument)
            .filter(
                CompletionDocument.job_id == job_id,
                CompletionDocument.tenant_id == tenant_id,
                CompletionDocument.job_closure_id.is_(None),
            )
            .order_by(
                CompletionDocument.created_at.asc()
            )
            .all()
        )

    # -----------------------------------------------------------------
    # Checksum lookup
    # -----------------------------------------------------------------

    def get_by_checksum(
        self,
        checksum_sha256: str,
        tenant_id: str,
    ) -> Optional[CompletionDocument]:
        """
        Return an existing document with the same checksum
        inside the same tenant.
        """

        return (
            self.db.query(CompletionDocument)
            .filter(
                CompletionDocument.checksum_sha256
                == checksum_sha256,
                CompletionDocument.tenant_id == tenant_id,
            )
            .first()
        )

    # -----------------------------------------------------------------
    # Link a document to a JobClosure
    # -----------------------------------------------------------------

    def link_to_closure(
        self,
        document: CompletionDocument,
        *,
        job_id: int,
        tenant_id: str,
        job_closure_id: int,
    ) -> CompletionDocument:
        """
        Link a completion document to a JobClosure.

        The document must already belong to the same job and tenant.
        This prevents accidental cross-job or cross-tenant linking.
        """

        if document.job_id != job_id:
            raise ValueError(
                "Completion document does not belong to the requested job"
            )

        if document.tenant_id != tenant_id:
            raise ValueError(
                "Completion document does not belong to the requested tenant"
            )

        document.job_closure_id = job_closure_id

        self.db.flush()

        return document

    # -----------------------------------------------------------------
    # Create
    # -----------------------------------------------------------------

    def create(
        self,
        document: CompletionDocument,
    ) -> CompletionDocument:
        """
        Add a completion document and flush so its ID is available.
        """

        self.db.add(document)
        self.db.flush()

        return document

    # -----------------------------------------------------------------
    # Delete
    # -----------------------------------------------------------------

    def delete(
        self,
        document: CompletionDocument,
    ) -> None:
        """
        Mark a completion document for deletion.
        """

        self.db.delete(document)

    # -----------------------------------------------------------------
    # Save / commit
    # -----------------------------------------------------------------

    def save(self) -> None:
        """
        Commit the current transaction.
        """

        self.db.commit()

    # -----------------------------------------------------------------
    # Refresh
    # -----------------------------------------------------------------

    def refresh(
        self,
        document: CompletionDocument,
    ) -> None:
        """
        Refresh a completion document from the database.
        """

        self.db.refresh(document)