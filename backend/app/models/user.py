"""
User and RefreshToken models for authentication.

The User model supports all five roles and is tenant-scoped.
Super Admins have a special system tenant.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, Integer, String, Text,
    ForeignKey, Index, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..database import Base


class User(Base):
    """
    Platform user account.

    Every user belongs to exactly one tenant (organization),
    except Super Admins who belong to the system tenant '__platform__'.
    """
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    role = Column(String(30), nullable=False, index=True)  # UserRole enum value
    tenant_id = Column(String(50),ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True)
    phone_number = Column(String(20), nullable=True)
    fcm_token = Column(String(255), nullable=True)
    device_type = Column(String(20), nullable=True)
    

    # Account status
    is_active = Column(Boolean, nullable=False, default=True)
    is_email_verified = Column(Boolean, nullable=False, default=False)
    is_on_duty = Column(Boolean, nullable=False, default=True)
    is_email_verified = Column(Boolean, nullable=False, default=False)

    # Security: account lockout
    failed_login_attempts = Column(Integer, nullable=False, default=0)
    locked_until = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    last_login = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Soft delete
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    deleted_by = Column(String(36), nullable=True)

    # Relationships
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
    organization=relationship("Organization",back_populates="users")
    mfa = relationship(
    "MFA",
    back_populates="user",
    uselist=False,
    cascade="all, delete-orphan",
)

    __table_args__ = (
        UniqueConstraint("email", "tenant_id", name="uq_users_email_tenant"),
        Index("idx_users_tenant_role", "tenant_id", "role"),
        Index("idx_users_active", "is_active", "deleted_at"),
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def is_locked(self) -> bool:
        """Check if the account is currently locked."""
        if self.locked_until is None:
            return False
        now = datetime.now(timezone.utc)
        if self.locked_until.tzinfo is None:
            # Handle naive datetimes from SQLite
            return self.locked_until > now.replace(tzinfo=None)
        return self.locked_until > now

    def record_failed_login(self) -> None:
        """Increment failed login counter and lock if threshold reached."""
        from datetime import timedelta
        self.failed_login_attempts = (self.failed_login_attempts or 0) + 1
        if self.failed_login_attempts >= 5:
            self.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)

    def record_successful_login(self) -> None:
        """Reset failed login counter on successful auth."""
        self.failed_login_attempts = 0
        self.locked_until = None
        self.last_login = datetime.now(timezone.utc)


class RefreshToken(Base):
    """
    Persistent refresh token for token rotation.

    Each refresh token can only be used once. On use, it is revoked
    and a new one is issued.
    """
    __tablename__ = "refresh_tokens"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(255), nullable=False, unique=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    device_info = Column(String(255), nullable=True)
    ip_address = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    user = relationship("User", back_populates="refresh_tokens")

    __table_args__ = (
        Index("idx_refresh_tokens_user_active", "user_id", "revoked_at"),
        Index("idx_refresh_tokens_expires", "expires_at"),
    )

    @property
    def is_expired(self) -> bool:
        now = datetime.now(timezone.utc)
        if self.expires_at.tzinfo is None:
            return self.expires_at < now.replace(tzinfo=None)
        return self.expires_at < now

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    @property
    def is_valid(self) -> bool:
        return not self.is_expired and not self.is_revoked
