"""Persisted customer and technician messages scoped to a FieldOps job."""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.sql import func

from ..database import Base


class JobMessage(Base):
    __tablename__ = "job_messages"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    # This is the service-provider job tenant. Customer tenant is determined
    # independently through ServiceRequest ownership (jobs can be cross-tenant).
    tenant_id = Column(String(50), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False)
    sender_user_id = Column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    sender_role = Column(String(20), nullable=False)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    read_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_job_messages_job_created", "job_id", "created_at"),
        Index("ix_job_messages_tenant_job", "tenant_id", "job_id"),
        Index("ix_job_messages_sender", "sender_user_id"),
    )
