"""Enforce unique email addresses for independent customer accounts.

Revision ID: d4e8b71c9a20
Revises: c8f5a2d91e74
Create Date: 2026-11-18
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d4e8b71c9a20"
down_revision = "c8f5a2d91e74"
branch_labels = None
depends_on = None

INDEX_NAME = "uq_users_independent_customer_email"


def upgrade() -> None:
    """Create a case-insensitive unique index for tenantless customers.

    The predicate intentionally matches User.__table_args__:
    tenant_id IS NULL, role = 'customer', and deleted_at IS NULL.
    Existing duplicate groups are reported before index creation so the
    migration fails without silently deleting or modifying user records.
    """
    bind = op.get_bind()
    duplicates = bind.execute(
        sa.text(
            """
            SELECT lower(email) AS normalized_email, COUNT(*) AS row_count
            FROM users
            WHERE tenant_id IS NULL
              AND role = 'customer'
              AND deleted_at IS NULL
            GROUP BY lower(email)
            HAVING COUNT(*) > 1
            ORDER BY lower(email)
            LIMIT 20
            """
        )
    ).all()

    if duplicates:
        details = ", ".join(
            f"{row.normalized_email} ({row.row_count} records)"
            for row in duplicates
        )
        raise RuntimeError(
            "Cannot create independent-customer email unique index. "
            "Resolve duplicate case-insensitive emails first. "
            f"Examples: {details}"
        )

    op.create_index(
        INDEX_NAME,
        "users",
        [sa.text("lower(email)")],
        unique=True,
        postgresql_where=sa.text(
            "tenant_id IS NULL AND role = 'customer' AND deleted_at IS NULL"
        ),
        sqlite_where=sa.text(
            "tenant_id IS NULL AND role = 'customer' AND deleted_at IS NULL"
        ),
    )


def downgrade() -> None:
    """Remove the independent-customer email unique index."""
    op.drop_index(INDEX_NAME, table_name="users")
