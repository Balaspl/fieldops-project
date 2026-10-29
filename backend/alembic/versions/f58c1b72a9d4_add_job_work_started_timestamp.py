"""Add work-start timestamp to jobs.

Revision ID: f58c1b72a9d4
Revises: e4c28b7a91f0
Create Date: 2026-10-16
"""

from alembic import op
import sqlalchemy as sa


revision = "f58c1b72a9d4"
down_revision = "e4c28b7a91f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    inspector = sa.inspect(bind)

    existing_columns = {
        column["name"]
        for column in inspector.get_columns(
            "jobs",
            schema="public",
        )
    }

    if "work_started_at" not in existing_columns:
        op.add_column(
            "jobs",
            sa.Column(
                "work_started_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
            schema="public",
        )


def downgrade() -> None:
    op.drop_column("jobs", "work_started_at", schema="public")