"""
MFA recovery codes.

Recovery codes are stored only as password-style hashes.
Each code can be used exactly once.
"""

import uuid

from sqlalchemy import (
    Column,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from ..database import Base


class MFARecoveryCode(Base):
    __tablename__ = "mfa_recovery_codes"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    mfa_id = Column(
        String(36),
        ForeignKey("user_mfa.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    tenant_id = Column(
        String(50),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Never store the actual recovery code.
    code_hash = Column(
        String(255),
        nullable=False,
    )

    used = Column(
        Boolean,
        nullable=False,
        default=False,
    )

    used_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    mfa = relationship(
        "MFA",
        back_populates="recovery_codes",
    )

    __table_args__ = (
        Index(
            "idx_mfa_recovery_tenant_mfa",
            "tenant_id",
            "mfa_id",
        ),
    )