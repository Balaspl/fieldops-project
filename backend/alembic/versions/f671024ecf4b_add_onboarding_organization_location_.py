"""add onboarding organization location coordinates

Revision ID: f671024ecf4b
Revises: 2398470ffcbd
Create Date: 2026-09-06 12:46:44.191432

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f671024ecf4b'
down_revision: Union[str, Sequence[str], None] = '2398470ffcbd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "organization_onboardings",
        sa.Column("site_latitude", sa.Float(), nullable=True),
    )
    op.add_column(
        "organization_onboardings",
        sa.Column("site_longitude", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("organization_onboardings", "site_longitude")
    op.drop_column("organization_onboardings", "site_latitude")