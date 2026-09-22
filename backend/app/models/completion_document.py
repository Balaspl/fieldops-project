"""
CompletionDocument model.

Stores metadata and secure storage references for completion photos.
Raw image binary data is never stored in the database.
"""

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    CheckConstraint,
    func,
)
from sqlalchemy.orm import relationship
from ..models_legacy import Base


class CompletionDocument(Base):
    """
    Metadata/reference record for a completion document.

    The actual image is stored through the storage layer.
    This table stores only metadata and the storage reference.
    """

    __tablename__ = "completion_documents"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    # Completion record this document belongs to.
    job_closure_id = Column(
        Integer,
        ForeignKey(
            "job_closures.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    # Denormalized job reference for efficient tenant/job filtering.
    job_id = Column(
        Integer,
        ForeignKey(
            "jobs.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    # Tenant isolation.
    tenant_id = Column(
        String(50),
        ForeignKey(
            "organizations.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    # BEFORE = evidence before service.
    # AFTER = evidence after service.
    category = Column(
        String(20),
        nullable=False,
    )

    # Original filename supplied by the client.
    # This is metadata only and is never used as the storage path.
    original_filename = Column(
        String(255),
        nullable=False,
    )

    # MIME type, for example image/jpeg.
    content_type = Column(
        String(100),
        nullable=False,
    )

    # Size of the uploaded file in bytes.
    file_size = Column(
        Integer,
        nullable=False,
    )

    # SHA-256 checksum of the stored file.
    checksum_sha256 = Column(
        String(64),
        nullable=False,
    )

    # Unique opaque storage reference.
    # Never expose a raw filesystem path here.
    storage_key = Column(
        String(500),
        nullable=False,
        unique=True,
    )

    # Optional externally accessible storage reference/URL.
    storage_url = Column(
        Text,
        nullable=True,
    )

    # Storage/security processing state.
    #
    # PENDING   -> uploaded but not approved for download
    # AVAILABLE -> approved and available through the document API
    # REJECTED  -> rejected and must not be exposed
    status = Column(
        String(20),
        nullable=False,
        default="PENDING",
        server_default="PENDING",
    )

    # Actor responsible for the upload.
    uploaded_by = Column(
        String(50),
        nullable=False,
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    job_closure = relationship(
        "JobClosure",
        back_populates="completion_documents",
    )

    __table_args__ = (
        CheckConstraint(
            "category IN ('BEFORE', 'AFTER')",
            name="ck_completion_documents_category",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'AVAILABLE', 'REJECTED')",
            name="ck_completion_documents_status",
        ),
        CheckConstraint(
            "file_size > 0",
            name="ck_completion_documents_file_size_positive",
        ),
        Index(
            "idx_completion_documents_tenant_job",
            "tenant_id",
            "job_id",
        ),
        Index(
            "idx_completion_documents_closure_category",
            "job_closure_id",
            "category",
        ),
    )