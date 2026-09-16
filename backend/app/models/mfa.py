"""
Multi-Factor Authentication model.

Stores tenant-scoped MFA configuration for a user.
TOTP secrets are stored encrypted.
Recovery codes are stored as hashes.
"""

import uuid

from sqlalchemy import (
    Column,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..database import Base


class MFA(Base):
    __tablename__ = "user_mfa"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    # User this MFA configuration belongs to
    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Tenant isolation
    tenant_id = Column(
        String(50),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Encrypted TOTP secret.
    # NEVER store the raw TOTP secret.
    secret_encrypted = Column(
        String(512),
        nullable=False,
    )

    # MFA is only enforced when this is True.
    enabled = Column(
        Boolean,
        nullable=False,
        default=False,
    )

    enrolled_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    last_used_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Number of recovery codes generated.
    # Actual recovery codes are stored separately as hashes.
    recovery_codes_generated_at = Column(
        DateTime(timezone=True),
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

    user = relationship(
        "User",
        back_populates="mfa",
    )

    organization = relationship(
        "Organization",
    )
    recovery_codes = relationship(
        "MFARecoveryCode",
        back_populates="mfa",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            name="uq_user_mfa_user_id",
        ),
        Index(
            "idx_user_mfa_tenant_user",
            "tenant_id",
            "user_id",
        ),
    )