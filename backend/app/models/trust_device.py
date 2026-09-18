"""
Trusted device model for MFA bypass on recognized devices.

A trusted device allows a user to skip MFA for a limited period
after successfully completing MFA once.
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


class TrustedDevice(Base):
    """
    A device that has been trusted after successful MFA verification.
    """

    __tablename__ = "trusted_devices"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    user_id = Column(
        String(36),
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
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

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user = relationship(
        "User",
        back_populates="trusted_devices",
    )

    __table_args__ = (
        Index(
            "idx_trusted_devices_user",
            "user_id",
        ),
        Index(
            "idx_trusted_devices_expires",
            "expires_at",
        ),
    )

    @property
    def is_expired(self) -> bool:
        now = datetime.now(timezone.utc)

        if self.expires_at.tzinfo is None:
            return self.expires_at < now.replace(
                tzinfo=None
            )

        return self.expires_at < now