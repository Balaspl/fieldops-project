"""allow completion documents before closure

Revision ID: 386da2907626
Revises: b25cd2562ab8
Create Date: 2026-09-28 15:20:50.509262

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "386da2907626"
down_revision: Union[str, Sequence[str], None] = "b25cd2562ab8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Allow completion documents to exist before JobClosure."""
    op.alter_column(
        "completion_documents",
        "job_closure_id",
        existing_type=sa.INTEGER(),
        nullable=True,
    )


def downgrade() -> None:
    """Restore JobClosure as mandatory for completion documents."""
    op.alter_column(
        "completion_documents",
        "job_closure_id",
        existing_type=sa.INTEGER(),
        nullable=False,
    )