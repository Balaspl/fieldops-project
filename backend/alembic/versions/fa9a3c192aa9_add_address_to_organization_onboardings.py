"""Add address to organization onboardings

Revision ID: fa9a3c192aa9
Revises: e177c0152bca
Create Date: 2026-09-09 10:21:43.480237
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "fa9a3c192aa9"
down_revision: Union[str, Sequence[str], None] = "e177c0152bca"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "organization_onboardings",
        sa.Column(
            "address",
            sa.String(length=500),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "organization_onboardings",
        "address",
    )