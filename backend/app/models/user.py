"""
User and RefreshToken models for authentication.

The User model supports all five roles and is tenant-scoped.
Super Admins have a special system tenant.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..database import Base


class User(Base):
    """
    Platform user account.

    Every user belongs to exactly one tenant (organization),
    except Super Admins who belong to the system tenant
    '__platform__'.
    """

    __tablename__ = "users"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    email = Column(
        String(255),
        nullable=False,
        index=True,
    )

    password_hash = Column(
        String(255),
        nullable=False,
    )

    first_name = Column(
        String(100),
        nullable=False,
    )

    last_name = Column(
        String(100),
        nullable=False,
    )

    role = Column(
        String(30),
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

    phone_number = Column(
        String(20),
        nullable=True,
    )

    fcm_token = Column(
        String(255),
        nullable=True,
    )

    device_type = Column(
        String(20),
        nullable=True,
    )

    # ---------------------------------------------------------
    # Account status
    # ---------------------------------------------------------

    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
    )

    is_email_verified = Column(
        Boolean,
        nullable=False,
        default=False,
    )

    is_on_duty = Column(
        Boolean,
        nullable=False,
        default=True,
    )

    # ---------------------------------------------------------
    # Security: account lockout
    # ---------------------------------------------------------

    failed_login_attempts = Column(
        Integer,
        nullable=False,
        default=0,
    )

    locked_until = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ---------------------------------------------------------
    # Timestamps
    # ---------------------------------------------------------

    last_login = Column(
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

    # ---------------------------------------------------------
    # Soft delete
    # ---------------------------------------------------------

    deleted_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    deleted_by = Column(
        String(36),
        nullable=True,
    )

    # ---------------------------------------------------------
    # Relationships
    # ---------------------------------------------------------

    refresh_tokens = relationship(
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    organization = relationship(
        "Organization",
        back_populates="users",
    )

    mfa = relationship(
        "MFA",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )

    trusted_devices = relationship(
        "TrustedDevice",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    # ---------------------------------------------------------
    # Table constraints / indexes
    # ---------------------------------------------------------

    __table_args__ = (
        UniqueConstraint(
            "email",
            "tenant_id",
            name="uq_users_email_tenant",
        ),
        Index(
            "idx_users_tenant_role",
            "tenant_id",
            "role",
        ),
        Index(
            "idx_users_active",
            "is_active",
            "deleted_at",
        ),
    )

    # ---------------------------------------------------------
    # Properties
    # ---------------------------------------------------------

    @property
    def full_name(self) -> str:
        """Return the user's full name."""

        return f"{self.first_name} {self.last_name}"

    @property
    def is_locked(self) -> bool:
        """
        Return True only when the account is currently locked.

        An expired lock is treated as unlocked.

        This property is intentionally side-effect free. It does not
        modify failed_login_attempts or locked_until.
        """

        if self.locked_until is None:
            return False

        now = datetime.now(timezone.utc)

        # SQLite may return naive datetimes even when the SQLAlchemy
        # column is configured with timezone=True.
        if self.locked_until.tzinfo is None:
            return self.locked_until > now.replace(tzinfo=None)

        return self.locked_until > now

    # ---------------------------------------------------------
    # Account lockout configuration
    # ---------------------------------------------------------

    @staticmethod
    def _lockout_threshold() -> int:
        """
        Return the configured number of failed login attempts
        required to lock the account.

        Environment variable:
            ACCOUNT_LOCKOUT_THRESHOLD

        Default:
            5
        """

        raw_value = os.getenv(
            "ACCOUNT_LOCKOUT_THRESHOLD",
            "5",
        )

        try:
            value = int(raw_value)
        except ValueError as exc:
            raise ValueError(
                "ACCOUNT_LOCKOUT_THRESHOLD must be an integer"
            ) from exc

        if value < 1:
            raise ValueError(
                "ACCOUNT_LOCKOUT_THRESHOLD must be >= 1"
            )

        return value

    @staticmethod
    def _lockout_duration_minutes() -> int:
        """
        Return the configured account-lockout duration.

        Environment variables:

            ACCOUNT_LOCKOUT_DURATION_MINUTES
            ACCOUNT_LOCKOUT_MIN_DURATION_MINUTES
            ACCOUNT_LOCKOUT_MAX_DURATION_MINUTES

        Defaults:

            duration = 15 minutes
            minimum = 1 minute
            maximum = 60 minutes
        """

        duration_raw = os.getenv(
            "ACCOUNT_LOCKOUT_DURATION_MINUTES",
            "15",
        )

        minimum_raw = os.getenv(
            "ACCOUNT_LOCKOUT_MIN_DURATION_MINUTES",
            "1",
        )

        maximum_raw = os.getenv(
            "ACCOUNT_LOCKOUT_MAX_DURATION_MINUTES",
            "60",
        )

        try:
            duration = int(duration_raw)
            minimum = int(minimum_raw)
            maximum = int(maximum_raw)
        except ValueError as exc:
            raise ValueError(
                "Account lockout duration configuration "
                "must contain valid integers"
            ) from exc

        if minimum < 1:
            raise ValueError(
                "ACCOUNT_LOCKOUT_MIN_DURATION_MINUTES "
                "must be >= 1"
            )

        if maximum < minimum:
            raise ValueError(
                "ACCOUNT_LOCKOUT_MAX_DURATION_MINUTES "
                "must be >= minimum duration"
            )

        if not minimum <= duration <= maximum:
            raise ValueError(
                "ACCOUNT_LOCKOUT_DURATION_MINUTES must be "
                f"between {minimum} and {maximum}"
            )

        return duration

    # ---------------------------------------------------------
    # Login security helpers
    # ---------------------------------------------------------

    def record_failed_login(self) -> bool:
        """
        Record a failed password authentication attempt.

        Returns:
            True:
                This failed attempt newly locked the account.

            False:
                The account remains unlocked, or the account was
                already actively locked.

        Behavior:
            - Failed attempts are counted.
            - The configured threshold triggers the lock.
            - Expired locks are cleared before starting a new
              failure window.
            - An active lock is never extended.
        """

        now = datetime.now(timezone.utc)

        # -----------------------------------------------------
        # Check whether an existing lock has expired
        # -----------------------------------------------------

        if self.locked_until is not None:

            if self.locked_until.tzinfo is None:
                lock_expired = (
                    self.locked_until
                    <= now.replace(tzinfo=None)
                )
            else:
                lock_expired = self.locked_until <= now

            if lock_expired:
                # The previous lockout period has finished.
                #
                # Start a fresh failure window.
                self.locked_until = None
                self.failed_login_attempts = 0

        # -----------------------------------------------------
        # Do not modify an already active lock
        # -----------------------------------------------------

        if self.is_locked:
            return False

        # -----------------------------------------------------
        # Increment failed login counter
        # -----------------------------------------------------

        self.failed_login_attempts = (
            self.failed_login_attempts or 0
        ) + 1

        threshold = self._lockout_threshold()

        # -----------------------------------------------------
        # Lock account when threshold is reached
        # -----------------------------------------------------

        if self.failed_login_attempts >= threshold:

            duration_minutes = (
                self._lockout_duration_minutes()
            )

            self.locked_until = (
                now
                + timedelta(
                    minutes=duration_minutes
                )
            )

            return True

        return False

    def record_successful_login(self) -> None:
        """
        Reset login failure state after successful authentication.

        A successful login:
            - clears the failed attempt counter
            - removes any lock
            - updates last_login
        """

        self.failed_login_attempts = 0
        self.locked_until = None
        self.last_login = datetime.now(timezone.utc)


class RefreshToken(Base):
    """
    Persistent refresh token for token rotation.

    Each refresh token belongs to one application session.

    Each refresh token can only be used once.
    On use, it is revoked and a new token is issued
    for the same application session.
    """

    __tablename__ = "refresh_tokens"

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

    # ---------------------------------------------------------
    # Application session
    # ---------------------------------------------------------
    #
    # This connects the refresh token to the server-side
    # application session stored in Redis.
    #
    # nullable=True keeps existing refresh-token rows
    # compatible until the Alembic migration/backfill
    # is completed.
    #
    session_id = Column(
        String(36),
        nullable=True,
        index=True,
    )

    token_hash = Column(
        String(255),
        nullable=False,
        unique=True,
    )

    expires_at = Column(
        DateTime(timezone=True),
        nullable=False,
    )

    revoked_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    device_info = Column(
        String(255),
        nullable=True,
    )

    ip_address = Column(
        String(50),
        nullable=True,
    )

    created_at = Column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )

    # ---------------------------------------------------------
    # Relationships
    # ---------------------------------------------------------

    user = relationship(
        "User",
        back_populates="refresh_tokens",
    )

    # ---------------------------------------------------------
    # Indexes
    # ---------------------------------------------------------

    __table_args__ = (
        Index(
            "idx_refresh_tokens_user_active",
            "user_id",
            "revoked_at",
        ),
        Index(
            "idx_refresh_tokens_session",
            "session_id",
            "revoked_at",
        ),
        Index(
            "idx_refresh_tokens_expires",
            "expires_at",
        ),
    )

    # ---------------------------------------------------------
    # Properties
    # ---------------------------------------------------------

    @property
    def is_expired(self) -> bool:
        """Return True when the refresh token has expired."""

        now = datetime.now(timezone.utc)

        if self.expires_at.tzinfo is None:
            return self.expires_at < now.replace(
                tzinfo=None
            )

        return self.expires_at < now

    @property
    def is_revoked(self) -> bool:
        """Return True when the refresh token has been revoked."""

        return self.revoked_at is not None

    @property
    def is_valid(self) -> bool:
        """Return True only when the refresh token is usable."""

        return (
            not self.is_expired
            and not self.is_revoked
        )