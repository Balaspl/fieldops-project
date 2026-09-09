"""add sms delivery status tracking fields

Revision ID: 5358f7c95b71
Revises: aba59f63cb44
Create Date: 2026-09-09 13:33:06.209658

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5358f7c95b71"
down_revision: Union[str, Sequence[str], None] = "aba59f63cb44"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.add_column(
        "sms_deliveries",
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    op.add_column(
        "sms_deliveries",
        sa.Column(
            "delivered_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    op.add_column(
        "sms_deliveries",
        sa.Column(
            "delivery_latency_ms",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.add_column(
        "sms_deliveries",
        sa.Column(
            "webhook_payload",
            sa.JSON(),
            nullable=True,
        ),
    )

    op.add_column(
        "sms_deliveries",
        sa.Column(
            "last_webhook_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    op.add_column(
        "sms_deliveries",
        sa.Column(
            "status_history",
            sa.JSON(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_column(
        "sms_deliveries",
        "status_history",
    )

    op.drop_column(
        "sms_deliveries",
        "last_webhook_at",
    )

    op.drop_column(
        "sms_deliveries",
        "webhook_payload",
    )

    op.drop_column(
        "sms_deliveries",
        "delivery_latency_ms",
    )

    op.drop_column(
        "sms_deliveries",
        "delivered_at",
    )

    op.drop_column(
        "sms_deliveries",
        "sent_at",
    )