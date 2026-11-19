"""Allow independent customer accounts without tenant IDs.

Revision ID: b7e4c91a2d63
Revises: 9c17b441eaf2
Create Date: 2026-11-18

Only the database columns become nullable here. Role-specific tenant
validation must remain enforced in the application:
- customer: tenant_id may be NULL
- technician, dispatcher, organization admin: tenant_id required
- super admin: retain the existing system-tenant behavior
"""

from alembic import op
import sqlalchemy as sa


revision = "b7e4c91a2d63"
down_revision = "9c17b441eaf2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "tenant_id",
        existing_type=sa.String(length=50),
        nullable=True,
    )

    op.alter_column(
        "customer_profiles_extended",
        "tenant_id",
        existing_type=sa.String(length=50),
        nullable=True,
    )


def downgrade() -> None:
    # This downgrade is only safe after every independent customer has
    # been assigned a valid tenant. Otherwise PostgreSQL will reject it.
    op.alter_column(
        "customer_profiles_extended",
        "tenant_id",
        existing_type=sa.String(length=50),
        nullable=False,
    )

    op.alter_column(
        "users",
        "tenant_id",
        existing_type=sa.String(length=50),
        nullable=False,
    )
