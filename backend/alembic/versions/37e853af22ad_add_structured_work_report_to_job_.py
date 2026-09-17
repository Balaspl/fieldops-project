"""add structured work report to job closures

Revision ID: 37e853af22ad
Revises: 8c6666f53711
Create Date: 2026-09-15
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "37e853af22ad"
down_revision: Union[str, None] = "8c6666f53711"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add structured work report storage to job closures."""
    op.add_column(
        "job_closures",
        sa.Column(
            "work_report",
            sa.JSON(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Remove structured work report storage from job closures."""
    op.drop_column("job_closures", "work_report")