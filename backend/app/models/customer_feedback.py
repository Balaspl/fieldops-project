"""
Customer feedback model for Job History.

This is an additive model for customer-provided feedback associated with a job.
It intentionally stores only the feedback fields required by the Job History
display contract and avoids duplicating customer PII such as name, email,
phone number, or address.

Authorization and tenant/object access are enforced by the API layer.
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
    UniqueConstraint,
)
from sqlalchemy.sql import func

from ..models_legacy import Base


class CustomerFeedback(Base):
    """Customer feedback associated with one job."""

    __tablename__ = "customer_feedback"

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

    tenant_id = Column(
        String(50),
        ForeignKey(
            "organizations.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    # Authenticated customer identity that submitted the feedback.
    # This is an internal identifier only and is never returned to
    # unauthorized roles by the API.
    customer_id = Column(
        String(50),
        nullable=False,
        index=True,
    )

    # Customer rating on the approved 1–5 scale.
    rating = Column(
        Integer,
        nullable=False,
    )

    # Optional customer-written feedback.
    # No customer name, email, phone, address, or other PII is stored here.
    comment = Column(
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

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "job_id",
            name="uq_customer_feedback_tenant_job",
        ),
        CheckConstraint(
            "rating >= 1 AND rating <= 5",
            name="ck_customer_feedback_rating_range",
        ),
        Index(
            "idx_customer_feedback_tenant_job",
            "tenant_id",
            "job_id",
        ),
        Index(
            "idx_customer_feedback_tenant_customer",
            "tenant_id",
            "customer_id",
        ),
    )