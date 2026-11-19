"""Allow independent customer password reset tokens.

Revision ID: e7a91c4d62b8
Revises: d4e8b71c9a20
Create Date: 2026-11-18
"""

from alembic import op
import sqlalchemy as sa


revision = "e7a91c4d62b8"
down_revision = "d4e8b71c9a20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Independent customers have users.tenant_id = NULL, so their
    # password-reset records must also permit tenant_id = NULL.
    # Keep the organization foreign key and index unchanged.
    op.alter_column(
        "password_reset_tokens",
        "tenant_id",
        existing_type=sa.String(length=50),
        nullable=True,
    )


def downgrade() -> None:
    # Do not silently discard independent-customer reset-token rows.
    bind = op.get_bind()
    null_count = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM password_reset_tokens "
            "WHERE tenant_id IS NULL"
        )
    ).scalar_one()

    if null_count:
        raise RuntimeError(
            "Cannot make password_reset_tokens.tenant_id NOT NULL: "
            f"{null_count} tenantless password reset token(s) exist. "
            "Expire or remove those tokens before retrying the downgrade."
        )

    op.alter_column(
        "password_reset_tokens",
        "tenant_id",
        existing_type=sa.String(length=50),
        nullable=False,
    )
