"""add password reset tokens

Revision ID: 17aee238a0df
Revises: 5b9a26aea696
Create Date: 2026-09-16 22:34:10.219594

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "17aee238a0df"
down_revision: Union[str, Sequence[str], None] = "5b9a26aea696"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create password reset token storage."""

    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "used_at",
            sa.DateTime(timezone=True),
            nullable=True,
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
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "token_hash",
            name="uq_password_reset_tokens_token_hash",
        ),
    )

    op.create_index(
        "idx_password_reset_tokens_user",
        "password_reset_tokens",
        ["user_id"],
    )

    op.create_index(
        "idx_password_reset_tokens_tenant",
        "password_reset_tokens",
        ["tenant_id"],
    )

    op.create_index(
        "idx_password_reset_tokens_expires",
        "password_reset_tokens",
        ["expires_at"],
    )


def downgrade() -> None:
    """Remove password reset token storage."""

    op.drop_index(
        "idx_password_reset_tokens_expires",
        table_name="password_reset_tokens",
    )

    op.drop_index(
        "idx_password_reset_tokens_tenant",
        table_name="password_reset_tokens",
    )

    op.drop_index(
        "idx_password_reset_tokens_user",
        table_name="password_reset_tokens",
    )

    op.drop_table("password_reset_tokens")