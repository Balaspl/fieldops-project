"""
Enterprise audit log model.

Immutable, comprehensive audit trail for all platform operations.
Tracks every security-relevant event with full context.
"""

import uuid
from sqlalchemy import (
    Column, DateTime, String, Text, JSON, Index, event, ForeignKey,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from ..database import Base


class EnterpriseAuditLog(Base):
    """
    Enterprise-grade audit log.

    Every security-relevant action creates an immutable record here.
    This table is append-only — updates and deletes are blocked
    by SQLAlchemy event listeners.

    Tracked events include:
    - Authentication (login, logout, failed login)
    - User management (create, update, delete, role change)
    - Job lifecycle (create, assign, reassign, complete)
    - Organization management (create, update, suspend, delete)
    - Settings changes
    - Permission changes
    """
    __tablename__ = "enterprise_audit_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Who
    user_id = Column(String(36), nullable=True, index=True)
    user_email = Column(String(255), nullable=True)
    role = Column(String(30), nullable=True, index=True)
    # Independent customers have no tenant. Organization events retain their tenant FK.
    tenant_id = Column(
        String(50),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    # When
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    # Where
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(Text, nullable=True)

    # What
    action = Column(String(100), nullable=False, index=True)

    # Context
    entity_type = Column(String(50), nullable=True, index=True)
    entity_id = Column(String(100), nullable=True, index=True)

    old_value = Column(JSON, nullable=True)
    new_value = Column(JSON, nullable=True)

    # Additional metadata
    details = Column(JSON, nullable=True)
    correlation_id = Column(String(100), nullable=True, index=True)

    # Severity
    severity = Column(String(20), nullable=False, default="INFO")
    # INFO, WARNING, ERROR, CRITICAL
    organization = relationship("Organization", back_populates="enterprise_audit_logs")

    __table_args__ = (
        Index("idx_enterprise_audit_tenant_time", "tenant_id", "timestamp"),
        Index("idx_enterprise_audit_action_time", "action", "timestamp"),
        Index("idx_enterprise_audit_entity", "entity_type", "entity_id"),
        Index("idx_enterprise_audit_user_time", "user_id", "timestamp"),
    )


# Immutability enforcement
@event.listens_for(EnterpriseAuditLog, "before_update")
def prevent_enterprise_audit_update(mapper, connection, target):
    raise ValueError("EnterpriseAuditLog is immutable — updates are forbidden")


@event.listens_for(EnterpriseAuditLog, "before_delete")
def prevent_enterprise_audit_delete(mapper, connection, target):
    raise ValueError("EnterpriseAuditLog is immutable — deletes are forbidden")
