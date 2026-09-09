"""add organization location coordinates

Revision ID: 2398470ffcbd
Revises: aba59f63cb44
Create Date: 2026-09-06 12:29:00.848612

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '2398470ffcbd'
down_revision: Union[str, Sequence[str], None] = 'aba59f63cb44'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("site_latitude", sa.Float(), nullable=True),
    )
    op.add_column(
        "organizations",
        sa.Column("site_longitude", sa.Float(), nullable=True),
    )

def downgrade() -> None:
    op.drop_column("organizations", "site_longitude")
    op.drop_column("organizations", "site_latitude")