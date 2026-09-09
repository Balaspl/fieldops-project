"""
Temporary organization onboarding and OTP verification model.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String
from sqlalchemy.sql import func

from ..database import Base


class OrganizationOnboarding(Base):
    """
    Temporary registration record used while a new organization
    is being onboarded.

    The organization and Super Admin are created only after
    the email OTP is successfully verified and a password is set.
    """

    __tablename__ = "organization_onboardings"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    organization_name = Column(
        String(200),
        nullable=False,
    )

    admin_first_name = Column(
        String(100),
        nullable=False,
    )

    admin_last_name = Column(
        String(100),
        nullable=False,
    )

    admin_email = Column(
        String(255),
        nullable=False,
        index=True,
    )

    address = Column(
        String(500),
        nullable=True,
    )

    site_latitude = Column(
        Float,
        nullable=True,
    )

    site_longitude = Column(
        Float,
        nullable=True,
    )

    # Store the hashed OTP, never the plain OTP.
    otp_hash = Column(
        String(255),
        nullable=False,
    )

    otp_expires_at = Column(
        DateTime(timezone=True),
        nullable=False,
    )

    otp_verified = Column(
        Boolean,
        nullable=False,
        default=False,
    )

    otp_verified_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    otp_attempts = Column(
        Integer,
        nullable=False,
        default=0,
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

    @property
    def is_otp_expired(self) -> bool:
        """Return True when the OTP has expired."""

        now = datetime.now(timezone.utc)

        if self.otp_expires_at.tzinfo is None:
            return self.otp_expires_at < now.replace(tzinfo=None)

        return self.otp_expires_at < now
