"""add customer support requests

Revision ID: c4d7e19a2b31
Revises: b7e3c1a9d542
Create Date: 2026-10-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c4d7e19a2b31"
down_revision: Union[str, Sequence[str], None] = "b7e3c1a9d542"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "customer_support_requests"


def upgrade() -> None:
    """Create customer support requests table."""

    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table(TABLE_NAME):
        return

    op.create_table(
        TABLE_NAME,
        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "request_number",
            sa.String(length=50),
            nullable=False,
        ),
        sa.Column(
            "customer_user_id",
            sa.String(length=36),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            sa.String(length=50),
            nullable=False,
        ),
        sa.Column(
            "subject",
            sa.String(length=200),
            nullable=False,
        ),
        sa.Column(
            "description",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'OPEN'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["customer_user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "request_number",
            name="uq_customer_support_requests_request_number",
        ),
    )

    op.create_index(
        "ix_customer_support_requests_id",
        TABLE_NAME,
        ["id"],
        unique=False,
    )

    op.create_index(
        "ix_customer_support_requests_request_number",
        TABLE_NAME,
        ["request_number"],
        unique=True,
    )

    op.create_index(
        "ix_customer_support_requests_customer_user_id",
        TABLE_NAME,
        ["customer_user_id"],
        unique=False,
    )

    op.create_index(
        "ix_customer_support_requests_tenant_id",
        TABLE_NAME,
        ["tenant_id"],
        unique=False,
    )

    op.create_index(
        "idx_customer_support_customer",
        TABLE_NAME,
        ["customer_user_id"],
        unique=False,
    )

    op.create_index(
        "idx_customer_support_tenant_status",
        TABLE_NAME,
        ["tenant_id", "status"],
        unique=False,
    )

    op.create_index(
        "idx_customer_support_tenant_customer",
        TABLE_NAME,
        ["tenant_id", "customer_user_id"],
        unique=False,
    )


def downgrade() -> None:
    """Remove customer support requests table."""

    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table(TABLE_NAME):
        return

    op.drop_table(TABLE_NAME)