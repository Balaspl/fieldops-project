"""Increase job location length

Revision ID: e177c0152bca
Revises: f671024ecf4b
Create Date: 2026-09-09 00:22:58.260546

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e177c0152bca"
down_revision: Union[str, Sequence[str], None] = "f671024ecf4b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        "jobs",
        "location",
        existing_type=sa.VARCHAR(length=150),
        type_=sa.String(length=500),
        existing_nullable=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "jobs",
        "location",
        existing_type=sa.String(length=500),
        type_=sa.VARCHAR(length=150),
        existing_nullable=False,
    )