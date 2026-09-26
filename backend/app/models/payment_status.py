"""
Backend-authoritative payment status model for Job History.

This is intentionally additive. It does not change the existing Job,
JobClosure, invoice, dispatch, completion, or payment workflows.

A row represents the latest known payment state for a job/invoice.
When no row exists, the read API will report UNAVAILABLE.
"""

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from ..models_legacy import Base


PAYMENT_STATUSES = (
    "PENDING",
    "SUCCESSFUL",
    "FAILED",
    "UNAVAILABLE",
)


class JobPaymentStatus(Base):
    """Latest authoritative payment state associated with one job/invoice."""

    __tablename__ = "job_payment_status"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    job_id = Column(
        Integer,
        ForeignKey(
            "jobs.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    invoice_id = Column(
        Integer,
        ForeignKey(
            "job_closures.id",
            ondelete="SET NULL",
        ),
        nullable=True,
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

    status = Column(
        String(20),
        nullable=False,
        default="UNAVAILABLE",
        server_default="UNAVAILABLE",
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "job_id",
            name="uq_job_payment_status_tenant_job",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'SUCCESSFUL', 'FAILED', 'UNAVAILABLE')",
            name="ck_job_payment_status_valid_status",
        ),
        Index(
            "idx_job_payment_status_tenant_updated",
            "tenant_id",
            "updated_at",
        ),
        Index(
            "idx_job_payment_status_job_invoice",
            "job_id",
            "invoice_id",
        ),
    )
