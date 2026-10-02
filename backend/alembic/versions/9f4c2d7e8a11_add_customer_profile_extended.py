"""Add customer extended profile table.

Revision ID: 9f4c2d7e8a11
Revises: 836d2d261262
Create Date: 2026-09-29

Creates the canonical customer_profiles_extended table used by the
customer portal profile API.

The migration is intentionally idempotent for environments where the
table may already have been created by the legacy startup schema or
older portal migration.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "9f4c2d7e8a11"
down_revision: Union[str, Sequence[str], None] = "836d2d261262"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "customer_profiles_extended"

TENANT_INDEX_NAME = "idx_cust_profile_tenant"
USER_INDEX_NAME = "idx_cust_profile_user"


def upgrade() -> None:
    """Create the customer extended profile table."""

    bind = op.get_bind()
    inspector = inspect(bind)

    existing_tables = set(inspector.get_table_names())

    if TABLE_NAME not in existing_tables:
        op.create_table(
            TABLE_NAME,
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
                "tenant_id",
                sa.String(length=50),
                nullable=False,
            ),
            sa.Column(
                "full_name",
                sa.String(length=200),
                nullable=False,
            ),
            sa.Column(
                "mobile_number",
                sa.String(length=20),
                nullable=False,
            ),
            sa.Column(
                "address",
                sa.Text(),
                nullable=True,
            ),
            sa.Column(
                "city",
                sa.String(length=100),
                nullable=True,
            ),
            sa.Column(
                "state",
                sa.String(length=100),
                nullable=True,
            ),
            sa.Column(
                "pincode",
                sa.String(length=10),
                nullable=True,
            ),
            sa.Column(
                "company_name",
                sa.String(length=200),
                nullable=True,
            ),
            sa.Column(
                "profile_completed",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.ForeignKeyConstraint(
                ["user_id"],
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
                "user_id",
                name="uq_customer_profiles_extended_user_id",
            ),
        )

    # ------------------------------------------------------------------
    # Ensure the expected indexes exist.
    # ------------------------------------------------------------------

    inspector = inspect(bind)
    existing_indexes = {
        index["name"]
        for index in inspector.get_indexes(TABLE_NAME)
    }

    if TENANT_INDEX_NAME not in existing_indexes:
        op.create_index(
            TENANT_INDEX_NAME,
            TABLE_NAME,
            ["tenant_id"],
            unique=False,
        )

    if USER_INDEX_NAME not in existing_indexes:
        op.create_index(
            USER_INDEX_NAME,
            TABLE_NAME,
            ["user_id"],
            unique=False,
        )


def downgrade() -> None:
    """Remove the customer extended profile table."""

    bind = op.get_bind()
    inspector = inspect(bind)

    existing_tables = set(inspector.get_table_names())

    if TABLE_NAME not in existing_tables:
        return

    existing_indexes = {
        index["name"]
        for index in inspector.get_indexes(TABLE_NAME)
    }

    if TENANT_INDEX_NAME in existing_indexes:
        op.drop_index(
            TENANT_INDEX_NAME,
            table_name=TABLE_NAME,
        )

    if USER_INDEX_NAME in existing_indexes:
        op.drop_index(
            USER_INDEX_NAME,
            table_name=TABLE_NAME,
        )

    op.drop_table(TABLE_NAME)