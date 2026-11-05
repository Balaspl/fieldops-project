"""
Customer support request model.

Stores support requests submitted by authenticated customers.
Support requests are intentionally separate from service requests/jobs
so they do not enter the operational dispatch workflow.
"""

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.sql import func

from ..models_legacy import Base


class CustomerSupportRequest(Base):
    """Support request submitted by one customer."""

    __tablename__ = "customer_support_requests"

    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
        index=True,
    )

    request_number = Column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )

    customer_user_id = Column(
        String(36),
        ForeignKey(
            "users.id",
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

    subject = Column(
        String(200),
        nullable=False,
    )

    description = Column(
        Text,
        nullable=False,
    )

    status = Column(
        String(30),
        nullable=False,
        default="OPEN",
    )

    # Optional link to the customer's service job.
    related_job_id = Column(
        Integer,
        ForeignKey(
            "jobs.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    # Staff-entered resolution information.
    resolution_note = Column(
        Text,
        nullable=True,
    )

    resolved_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    resolved_by = Column(
        String(36),
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    category = Column(String(40), nullable=False, default="OTHER", server_default="OTHER")
    priority = Column(String(20), nullable=False, default="MEDIUM", server_default="MEDIUM")
    assigned_staff_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    source_chat_conversation_id = Column(String(36), nullable=True)

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
        Index(
            "idx_customer_support_customer",
            "customer_user_id",
        ),
        Index(
            "idx_customer_support_tenant_status",
            "tenant_id",
            "status",
        ),
        Index(
            "idx_customer_support_tenant_customer",
            "tenant_id",
            "customer_user_id",
        ),
        Index(
            "ix_customer_support_requests_related_job_id",
            "related_job_id",
        ),
        Index("uq_customer_support_source_chat", "source_chat_conversation_id", unique=True),
    )


class CustomerSupportCaseUpdate(Base):
    """Customer-visible progress update within a support case."""

    __tablename__ = "customer_support_case_updates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    support_request_id = Column(Integer, ForeignKey("customer_support_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    author_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    author_role = Column(String(20), nullable=False)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
