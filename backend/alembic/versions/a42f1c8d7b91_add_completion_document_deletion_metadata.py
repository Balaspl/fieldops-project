"""add audited completion document deletion metadata

Revision ID: a42f1c8d7b91
Revises: 53b9591ae602
Create Date: 2026-09-29 12:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a42f1c8d7b91"
down_revision: Union[str, Sequence[str], None] = "53b9591ae602"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add audited soft-deletion metadata to completion documents."""

    op.add_column(
        "completion_documents",
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    op.add_column(
        "completion_documents",
        sa.Column(
            "deleted_by",
            sa.String(length=50),
            nullable=True,
        ),
    )

    op.add_column(
        "completion_documents",
        sa.Column(
            "deletion_reason",
            sa.Text(),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_completion_documents_deleted_at",
        "completion_documents",
        ["deleted_at"],
    )


def downgrade() -> None:
    """Remove audited completion-document deletion metadata."""

    op.drop_index(
        "ix_completion_documents_deleted_at",
        table_name="completion_documents",
    )

    op.drop_column(
        "completion_documents",
        "deletion_reason",
    )

    op.drop_column(
        "completion_documents",
        "deleted_by",
    )

    op.drop_column(
        "completion_documents",
        "deleted_at",
    )