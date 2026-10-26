
"""Persist scheduled visit time and timezone."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "a27d91c42e60"
down_revision: Union[str, Sequence[str], None] = "f0a4c2d7e911"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)

    existing_columns = {
        column["name"]
        for column in inspector.get_columns("jobs")
    }

    if "preferred_service_time" not in existing_columns:
        op.add_column(
            "jobs",
            sa.Column(
                "preferred_service_time",
                sa.Time(),
                nullable=True,
            ),
        )

    if "preferred_service_timezone" not in existing_columns:
        op.add_column(
            "jobs",
            sa.Column(
                "preferred_service_timezone",
                sa.String(length=64),
                nullable=True,
            ),
        )


def downgrade() -> None:
    # These columns may have existed before this migration ran.
    # Do not drop existing data blindly.
    pass
