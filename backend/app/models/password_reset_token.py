"""
Password reset token model.

Stores only a hash of the reset token.
Plaintext reset tokens must never be stored or logged.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..database import Base


class PasswordResetToken(Base):
    """Single-use, short-lived password reset token."""

    __tablename__ = "password_reset_tokens"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    tenant_id = Column(
        String(50),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    token_hash = Column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
    )

    expires_at = Column(
        DateTime(timezone=True),
        nullable=False,
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

    user = relationship("User")

    @property
    def is_used(self) -> bool:
        return self.used_at is not None

    @property
    def is_expired(self) -> bool:
        now = datetime.now(timezone.utc)

        if self.expires_at.tzinfo is None:
            return self.expires_at <= now.replace(tzinfo=None)

        return self.expires_at <= now

    @property
    def is_valid(self) -> bool:
        return not self.is_used and not self.is_expired


Index(
    "idx_password_reset_tokens_user_active",
    PasswordResetToken.user_id,
    PasswordResetToken.used_at,
)

Index(
    "idx_password_reset_tokens_expires",
    PasswordResetToken.expires_at,
)