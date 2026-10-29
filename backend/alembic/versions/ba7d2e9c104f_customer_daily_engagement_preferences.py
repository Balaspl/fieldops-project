"""Add opt-in and quiet-hour settings for daily customer engagement.

Revision ID: ba7d2e9c104f
Revises: f58c1b72a9d4
"""

from alembic import op
import sqlalchemy as sa


revision = "ba7d2e9c104f"
down_revision = "f58c1b72a9d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    inspector = sa.inspect(bind)

    existing_columns = {
        column["name"]
        for column in inspector.get_columns(
            "customer_profiles",
            schema="public",
        )
    }

    # Add daily engagement preference only if it does not exist.
    if "daily_engagement_enabled" not in existing_columns:
        op.add_column(
            "customer_profiles",
            sa.Column(
                "daily_engagement_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            schema="public",
        )

    # Add timezone preference only if it does not exist.
    if "timezone" not in existing_columns:
        op.add_column(
            "customer_profiles",
            sa.Column(
                "timezone",
                sa.String(length=64),
                nullable=False,
                server_default="UTC",
            ),
            schema="public",
        )

    # Add quiet-hours start only if it does not exist.
    if "quiet_hours_start" not in existing_columns:
        op.add_column(
            "customer_profiles",
            sa.Column(
                "quiet_hours_start",
                sa.String(length=5),
                nullable=False,
                server_default="21:00",
            ),
            schema="public",
        )

    # Add quiet-hours end only if it does not exist.
    if "quiet_hours_end" not in existing_columns:
        op.add_column(
            "customer_profiles",
            sa.Column(
                "quiet_hours_end",
                sa.String(length=5),
                nullable=False,
                server_default="08:00",
            ),
            schema="public",
        )


def downgrade() -> None:
    op.drop_column(
        "customer_profiles",
        "quiet_hours_end",
        schema="public",
    )
    op.drop_column(
        "customer_profiles",
        "quiet_hours_start",
        schema="public",
    )
    op.drop_column(
        "customer_profiles",
        "timezone",
        schema="public",
    )
    op.drop_column(
        "customer_profiles",
        "daily_engagement_enabled",
        schema="public",
    )