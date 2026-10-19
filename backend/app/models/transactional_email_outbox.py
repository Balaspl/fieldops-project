"""Durable, tenant-scoped outbox for customer transactional email."""

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func

from ..models_legacy import Base


class TransactionalEmailOutbox(Base):
    __tablename__ = "transactional_email_outbox"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(String(50), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    customer_id = Column(String(50), nullable=True)
    recipient_email = Column(String(320), nullable=True)
    event_type = Column(String(40), nullable=False)
    event_version = Column(Integer, nullable=False)
    idempotency_key = Column(String(180), nullable=False)
    status = Column(String(24), nullable=False, default="pending", server_default="pending")
    attempts = Column(Integer, nullable=False, default=0, server_default="0")
    next_attempt_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_error = Column(Text, nullable=True)
    smtp_status = Column(Integer, nullable=True)
    provider_message_id = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    sent_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_transactional_email_idempotency"),
        Index("ix_transactional_email_due", "status", "next_attempt_at"),
    )
