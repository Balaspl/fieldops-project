
"""Keep personal fields in plaintext.

Revision ID: 7ac43d11bf20
Revises: c9d4e2a71f60

NOTE:
This migration is intentionally a no-op for data transformation.
It does not encrypt or decrypt existing values.
"""

from alembic import op
import sqlalchemy as sa

revision = "7ac43d11bf20"
down_revision = "c9d4e2a71f60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Do not encrypt personal data.
    # Keep the existing schema unchanged.
    pass


def downgrade() -> None:
    # No data transformation to reverse.
    pass
