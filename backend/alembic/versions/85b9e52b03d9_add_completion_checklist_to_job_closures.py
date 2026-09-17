"""add completion checklist to job closures

Revision ID: 85b9e52b03d9
Revises: e5c61e512040
Create Date: 2026-09-15
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "85b9e52b03d9"
down_revision: Union[str, Sequence[str], None] = "e5c61e512040"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "job_closures",
        sa.Column("completion_checklist", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("job_closures", "completion_checklist")