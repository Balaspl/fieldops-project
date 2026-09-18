"""add trusted devices

Revision ID: 22c3907b165a
Revises: afade4213334
Create Date: 2026-09-18 12:49:51.164809

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '22c3907b165a'
down_revision: Union[str, Sequence[str], None] = 'afade4213334'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "trusted_devices",

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
            "token_hash",
            sa.String(length=64),
            nullable=False,
        ),

        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),

        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),

        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_trusted_devices_user_id",
        "trusted_devices",
        ["user_id"],
    )

    op.create_index(
        "ix_trusted_devices_token_hash",
        "trusted_devices",
        ["token_hash"],
        unique=True,
    )

    op.create_index(
        "idx_trusted_devices_expires",
        "trusted_devices",
        ["expires_at"],
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(
        "idx_trusted_devices_expires",
        table_name="trusted_devices",
    )

    op.drop_index(
        "ix_trusted_devices_token_hash",
        table_name="trusted_devices",
    )

    op.drop_index(
        "ix_trusted_devices_user_id",
        table_name="trusted_devices",
    )

    op.drop_table("trusted_devices")