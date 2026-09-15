"""add oidc identities

Revision ID: bcbb1bcc4e59
Revises: 8c6666f53711
Create Date: 2026-09-14 14:18:04.150915

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "bcbb1bcc4e59"
down_revision: Union[str, Sequence[str], None] = "8c6666f53711"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the OIDC identity mapping table."""

    op.create_table(
        "oidc_identities",
        sa.Column(
            "id",
            sa.String(length=36),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.String(length=36),
            nullable=False,
        ),
        sa.Column(
            "provider",
            sa.String(length=50),
            nullable=False,
        ),
        sa.Column(
            "issuer",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "subject",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "issuer",
            "subject",
            name="uq_oidc_identity_issuer_subject",
        ),
    )

    op.create_index(
        "ix_oidc_identities_user_id",
        "oidc_identities",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    """Remove the OIDC identity mapping table."""

    op.drop_index(
        "ix_oidc_identities_user_id",
        table_name="oidc_identities",
    )

    op.drop_table("oidc_identities")