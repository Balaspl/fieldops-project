"""Persist the active Dispatcher batch for retry and restart recovery."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "b51c8d0e4a29"
down_revision = "a27d91c42e60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if "dispatch_state" not in {
        column["name"] for column in inspector.get_columns("jobs")
    }:
        op.add_column(
            "jobs",
            sa.Column("dispatch_state", sa.JSON(), nullable=True),
        )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if "dispatch_state" in {
        column["name"] for column in inspector.get_columns("jobs")
    }:
        op.drop_column("jobs", "dispatch_state")
