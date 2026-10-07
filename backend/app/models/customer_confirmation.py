"""
CustomerConfirmation model.

Stores an auditable customer approval or rejection for a completed job.
The confirmation is linked to the tenant, customer, job, and closure record.
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


class CustomerConfirmation(Base):
    """
    Backend-authoritative customer completion confirmation.

    The authenticated customer can approve or reject a completed service.
    The decision is preserved independently from technician completion data.
    """

    __tablename__ = "customer_confirmations"

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

    customer_id = Column(
        String(50),
        nullable=False,
        index=True,
    )

    decision = Column(
        String(30),
        nullable=False,
        index=True,
    )

    comments = Column(
        Text,
        nullable=True,
    )

    confirmed_at = Column(
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
            name="uq_customer_confirmations_job",
        ),
    )