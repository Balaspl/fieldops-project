"""add customer recipients to notifications

Revision ID: 1b0e1c93d5ab
Revises: 1a02f91166b3
Create Date: 2026-09-25 10:53:39.433169

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1b0e1c93d5ab"
down_revision: Union[str, Sequence[str], None] = "1a02f91166b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        "notifications",
        "tech_id",
        existing_type=sa.String(length=36),
        nullable=True,
    )

    op.add_column(
        "notifications",
        sa.Column(
            "customer_user_id",
            sa.String(length=50),
            nullable=True,
        ),
    )

    op.create_index(
        "idx_notifications_customer_status",
        "notifications",
        ["customer_user_id", "status"],
        unique=False,
    )

    op.create_check_constraint(
        "notification_has_recipient",
        "notifications",
        "tech_id IS NOT NULL OR customer_user_id IS NOT NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "notification_has_recipient",
        "notifications",
        type_="check",
    )

    op.drop_index(
        "idx_notifications_customer_status",
        table_name="notifications",
    )

    op.drop_column(
        "notifications",
        "customer_user_id",
    )

    op.alter_column(
        "notifications",
        "tech_id",
        existing_type=sa.String(length=36),
        nullable=False,
    )