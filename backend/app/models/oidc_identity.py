import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.sql import func

from ..database import Base


class OIDCIdentity(Base):
    """
    External OIDC identity linked to an existing FieldOps User.

    One FieldOps user may have multiple authentication methods,
    but a single OIDC identity can belong to only one FieldOps user.
    """

    __tablename__ = "oidc_identities"

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

    provider = Column(
        String(50),
        nullable=False,
    )

    issuer = Column(
        String(255),
        nullable=False,
    )

    subject = Column(
        String(255),
        nullable=False,
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    __table_args__ = (
    # One Google/OIDC identity can belong to only one FieldOps user.
    UniqueConstraint(
        "issuer",
        "subject",
        name="uq_oidc_identity_issuer_subject",
    ),

    # One FieldOps user can link only one OIDC identity.
    UniqueConstraint(
        "user_id",
        name="uq_oidc_identity_user_id",
    ),
)