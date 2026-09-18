"""add session id to refresh tokens

Revision ID: afade4213334
Revises: 17aee238a0df
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "afade4213334"
down_revision: Union[str, Sequence[str], None] = "17aee238a0df"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "refresh_tokens",
        sa.Column(
            "session_id",
            sa.String(length=36),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_refresh_tokens_session_id",
        "refresh_tokens",
        ["session_id"],
        unique=False,
    )

    op.create_index(
        "idx_refresh_tokens_session",
        "refresh_tokens",
        ["session_id", "revoked_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_refresh_tokens_session",
        table_name="refresh_tokens",
    )

    op.drop_index(
        "ix_refresh_tokens_session_id",
        table_name="refresh_tokens",
    )

    op.drop_column(
        "refresh_tokens",
        "session_id",
    )