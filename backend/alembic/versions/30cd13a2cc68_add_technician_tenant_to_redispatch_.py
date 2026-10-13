"""add technician tenant to redispatch attempts

Revision ID: 30cd13a2cc68
Revises: 628e63a9b7e8
Create Date: 2026-10-13 12:05:29.413466

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# Revision identifiers, used by Alembic.
revision: str = "30cd13a2cc68"
down_revision: Union[str, Sequence[str], None] = "628e63a9b7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the rejecting technician's tenant ID to redispatch attempts."""
    op.add_column(
        "redispatch_attempts",
        sa.Column("technician_tenant_id", sa.String(length=50), nullable=True),
    )
    op.create_index(
        "ix_redispatch_attempts_technician_tenant_id",
        "redispatch_attempts",
        ["technician_tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    """Remove the rejecting technician's tenant ID from redispatch attempts."""
    op.drop_index(
        "ix_redispatch_attempts_technician_tenant_id",
        table_name="redispatch_attempts",
    )
    op.drop_column("redispatch_attempts", "technician_tenant_id")
