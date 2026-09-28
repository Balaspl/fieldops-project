"""
CustomerSignature model.

Stores an auditable customer-confirmation signature for a completed job.
The signature is linked to the tenant, job, and closure record.
"""

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)

from ..models_legacy import Base, UTCDateTime


class CustomerSignature(Base):
    """
    Backend-authoritative customer signature record.

    The frontend captures the customer's signature and submits it through
    the dedicated signature API. This record preserves who captured it,
    when it was captured, and which tenant/job/closure it belongs to.
    """

    __tablename__ = "customer_signatures"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    job_id = Column(
        Integer,
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    job_closure_id = Column(
        Integer,
        ForeignKey("job_closures.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    tenant_id = Column(
        String(50),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Canonical serialized signature payload captured from the customer.
    # The API will validate its format before persistence.
    signature_data = Column(
        Text,
        nullable=False,
    )

    # Authenticated technician who captured/submitted the signature.
    captured_by = Column(
        String(50),
        nullable=False,
    )

    # Backend-authoritative signature timestamp.
    signed_at = Column(
        UTCDateTime(),
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

    __table_args__ = (
        UniqueConstraint(
            "job_id",
            name="uq_customer_signatures_job",
        ),
        UniqueConstraint(
            "job_closure_id",
            name="uq_customer_signatures_closure",
        ),
    )

