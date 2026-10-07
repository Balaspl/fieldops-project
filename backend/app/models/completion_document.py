"""
CompletionDocument model.

Stores metadata and secure storage references for completion
photos and service documents.

Raw binary data is never stored in PostgreSQL.
"""

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from ..models_legacy import Base


class CompletionDocument(Base):
    """
    Metadata/reference record for a completion attachment.

    Actual binary file content is stored through the configured
    storage layer.

    document_type:
        PHOTO
        DOCUMENT

    PHOTO categories:
        BEFORE
        AFTER

    DOCUMENT categories:
        MANUAL
        SERVICE_REPORT
        CERTIFICATE
        OTHER

    status:
        PENDING
        AVAILABLE
        REJECTED

    scan_status:
        PENDING
        CLEAN
        REJECTED
    """

    __tablename__ = "completion_documents"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    job_closure_id = Column(
        Integer,
        ForeignKey(
            "job_closures.id",
            ondelete="CASCADE",
        ),
        nullable=True,
        index=True,
    )

    job_id = Column(
        Integer,
        ForeignKey(
            "jobs.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    tenant_id = Column(
        String(50),
        ForeignKey(
            "organizations.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    uploaded_by = Column(
        String(50),
        nullable=False,
    )

    document_type = Column(
        String(20),
        nullable=False,
    )

    category = Column(
        String(20),
        nullable=False,
    )

    original_filename = Column(
        String(255),
        nullable=False,
    )

    content_type = Column(
        String(100),
        nullable=False,
    )

    file_size = Column(
        Integer,
        nullable=False,
    )

    checksum_sha256 = Column(
        String(64),
        nullable=False,
    )

    storage_key = Column(
        String(500),
        nullable=False,
        unique=True,
    )

    storage_url = Column(
        Text,
        nullable=True,
    )

    # Overall document state
    status = Column(
        String(20),
        nullable=False,
        default="PENDING",
        server_default="PENDING",
    )

    # Security scanning state
    scan_status = Column(
        String(20),
        nullable=False,
        default="PENDING",
        server_default="PENDING",
    )

    # Timestamp of the most recent completed scan
    scanned_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Audited deletion metadata.
    # Soft-deleted completion documents retain their database metadata
    # so evidence cannot disappear silently from the audit trail.
    deleted_at = Column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    deleted_by = Column(
        String(50),
        nullable=True,
    )

    deletion_reason = Column(
        Text,
        nullable=True,
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
            "document_type IN ('PHOTO', 'DOCUMENT')",
            name="ck_completion_documents_document_type",
        ),
        CheckConstraint(
            """
            (
                document_type = 'PHOTO'
                AND category IN ('BEFORE', 'AFTER')
            )
            OR
            (
                document_type = 'DOCUMENT'
                AND category IN (
                    'MANUAL',
                    'SERVICE_REPORT',
                    'CERTIFICATE',
                    'OTHER'
                )
            )
            """,
            name="ck_completion_documents_category",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'AVAILABLE', 'REJECTED')",
            name="ck_completion_documents_status",
        ),
        CheckConstraint(
            "scan_status IN ('PENDING', 'CLEAN', 'REJECTED')",
            name="ck_completion_documents_scan_status",
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
        Index(
            "idx_completion_documents_job_type",
            "job_id",
            "document_type",
        ),
    )