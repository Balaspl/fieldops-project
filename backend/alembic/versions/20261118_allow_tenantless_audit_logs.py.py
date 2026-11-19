"""Allow tenantless customer audit records.

Revision ID: c8f5a2d91e74
Revises: b7e4c91a2d63
Create Date: 2026-11-18
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c8f5a2d91e74"
down_revision = "b7e4c91a2d63"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "enterprise_audit_logs",
        "tenant_id",
        existing_type=sa.String(length=50),
        existing_nullable=False,
        nullable=True,
    )


def downgrade() -> None:
    # A nullable tenant_id may now contain NULL values for independent
    # customer audit records. Do not invent an organization for those rows.
    connection = op.get_bind()
    null_count = connection.execute(
        sa.text(
            "SELECT COUNT(*) FROM enterprise_audit_logs "
            "WHERE tenant_id IS NULL"
        )
    ).scalar_one()

    if null_count:
        raise RuntimeError(
            "Cannot downgrade: enterprise_audit_logs contains "
            f"{null_count} tenantless audit record(s). Resolve or archive "
            "these records before making tenant_id NOT NULL."
        )

    op.alter_column(
        "enterprise_audit_logs",
        "tenant_id",
        existing_type=sa.String(length=50),
        existing_nullable=True,
        nullable=False,
    )
