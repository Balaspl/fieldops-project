"""add completion document scan state

Revision ID: e02bd5217c96
Revises: d10d76fc7a78
Create Date: 2026-09-25 15:09:00.708824

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e02bd5217c96"
down_revision: Union[str, Sequence[str], None] = "d10d76fc7a78"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add completion document scan state."""

    # ---------------------------------------------------------
    # Add scan status
    # ---------------------------------------------------------

    op.add_column(
        "completion_documents",
        sa.Column(
            "scan_status",
            sa.String(length=20),
            nullable=False,
            server_default="PENDING",
        ),
    )

    # ---------------------------------------------------------
    # Add scan timestamp
    # ---------------------------------------------------------

    op.add_column(
        "completion_documents",
        sa.Column(
            "scanned_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # ---------------------------------------------------------
    # Backfill existing completion documents
    #
    # Existing AVAILABLE documents were already allowed to
    # download, so preserve them as CLEAN.
    #
    # Existing REJECTED documents remain REJECTED.
    #
    # Everything else remains PENDING until it is scanned.
    # ---------------------------------------------------------

    op.execute(
        """
        UPDATE completion_documents
        SET scan_status = CASE
            WHEN status = 'AVAILABLE' THEN 'CLEAN'
            WHEN status = 'REJECTED' THEN 'REJECTED'
            ELSE 'PENDING'
        END
        """
    )

    # ---------------------------------------------------------
    # Add scan status integrity constraint
    # ---------------------------------------------------------

    op.create_check_constraint(
        "ck_completion_documents_scan_status",
        "completion_documents",
        "scan_status IN ('PENDING', 'CLEAN', 'REJECTED')",
    )


def downgrade() -> None:
    """Remove completion document scan state."""

    # ---------------------------------------------------------
    # Remove scan status integrity constraint
    # ---------------------------------------------------------

    op.drop_constraint(
        "ck_completion_documents_scan_status",
        "completion_documents",
        type_="check",
    )

    # ---------------------------------------------------------
    # Remove scan timestamp
    # ---------------------------------------------------------

    op.drop_column(
        "completion_documents",
        "scanned_at",
    )

    # ---------------------------------------------------------
    # Remove scan status
    # ---------------------------------------------------------

    op.drop_column(
        "completion_documents",
        "scan_status",
    )