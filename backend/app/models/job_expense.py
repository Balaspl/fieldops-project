"""
Job expense submission model.

Stores a technician-submitted expense against a tenant-scoped job.
The authenticated technician and tenant are supplied by the backend route/service;
they are not accepted from the client as authoritative identity fields.
"""

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    func,
)

from ..models_legacy import Base, UTCDateTime


class JobExpense(Base):
    __tablename__ = "job_expenses"

    id = Column(Integer, primary_key=True, index=True)

    job_id = Column(
        Integer,
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    technician_id = Column(
        Integer,
        ForeignKey("technicians.technician_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    tenant_id = Column(
        Text,
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Monetary values are stored as fixed-precision decimals rather than floats.
    amount = Column(
        Numeric(12, 2, asdecimal=True),
        nullable=False,
    )

    description = Column(
        Text,
        nullable=False,
    )

    submitted_at = Column(
        UTCDateTime(),
        nullable=False,
        server_default=func.now(),
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "amount > 0",
            name="ck_job_expenses_amount_positive",
        ),
    )