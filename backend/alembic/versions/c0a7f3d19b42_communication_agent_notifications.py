"""Communication agent: generic recipients, live-card group_key, channel deliveries,
and event version.

Revision ID: c0a7f3d19b42
Revises: 30cd13a2cc68
Create Date: 2026-10-15
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c0a7f3d19b42"
down_revision = "30cd13a2cc68"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Notifications: generic recipient, live-card key, updated_at,
    #    and event_version.
    with op.batch_alter_table("notifications", schema="public") as batch_op:
        batch_op.add_column(
            sa.Column("recipient_id", sa.String(length=50), nullable=True)
        )
        batch_op.add_column(
            sa.Column("recipient_role", sa.String(length=20), nullable=True)
        )
        batch_op.add_column(
            sa.Column("group_key", sa.String(length=100), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "event_version",
                sa.BigInteger(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )

    # Backfill recipient information for existing notifications.
    op.execute(
        """
        UPDATE public.notifications
        SET
            recipient_id = COALESCE(tech_id, customer_user_id),
            recipient_role = CASE
                WHEN tech_id IS NOT NULL THEN 'technician'
                WHEN customer_user_id IS NOT NULL THEN 'customer'
                ELSE recipient_role
            END,
            updated_at = COALESCE(updated_at, created_at),
            event_version = 0
        """
    )

    # Give existing notifications distinct group keys. This avoids
    # accidentally merging historical records when the unique index changes.
    op.execute(
        """
        UPDATE public.notifications
        SET group_key = 'legacy_' || id::text
        WHERE group_key IS NULL
        """
    )

    # 2. Allow generic recipients and create tenant-aware indexes.
    with op.batch_alter_table("notifications", schema="public") as batch_op:
        batch_op.drop_constraint(
            "notification_has_recipient",
            type_="check",
        )

        batch_op.create_check_constraint(
            "notification_has_recipient",
            """
            tech_id IS NOT NULL
            OR customer_user_id IS NOT NULL
            OR recipient_id IS NOT NULL
            """,
        )

        # Tenant is part of the uniqueness boundary. This matches store.py.
        batch_op.create_index(
            "uq_notifications_recipient_group",
            [
                "tenant_id",
                "recipient_role",
                "recipient_id",
                "group_key",
            ],
            unique=True,
        )

        batch_op.create_index(
            "ix_notifications_recipient_unread",
            ["tenant_id", "recipient_id", "read_at"],
        )

    # 3. Add job notification event version counter.
    op.add_column(
        "jobs",
        sa.Column(
            "notification_event_version",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        schema="public",
    )

    # 4. Generic per-channel delivery tracking.
    op.create_table(
        "notification_channel_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(length=50),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "notification_id",
            sa.String(length=36),
            sa.ForeignKey("notifications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("recipient_id", sa.String(length=50), nullable=False),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'queued'"),
        ),
        sa.Column("provider_id", sa.String(length=255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "attempts",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        schema="public",
    )

    op.create_index(
        "ix_notification_channel_deliveries_tenant_id",
        "notification_channel_deliveries",
        ["tenant_id"],
        schema="public",
    )

    op.create_index(
        "uq_ncd_idempotency",
        "notification_channel_deliveries",
        ["idempotency_key"],
        unique=True,
        schema="public",
    )

    op.create_index(
        "ix_ncd_notification",
        "notification_channel_deliveries",
        ["notification_id"],
        schema="public",
    )


def downgrade():
    # 1. Remove channel-delivery tracking.
    op.drop_index(
        "ix_ncd_notification",
        table_name="notification_channel_deliveries",
        schema="public",
    )
    op.drop_index(
        "uq_ncd_idempotency",
        table_name="notification_channel_deliveries",
        schema="public",
    )
    op.drop_index(
        "ix_notification_channel_deliveries_tenant_id",
        table_name="notification_channel_deliveries",
        schema="public",
    )
    op.drop_table(
        "notification_channel_deliveries",
        schema="public",
    )

    # 2. Remove job notification event version counter.
    op.drop_column(
        "jobs",
        "notification_event_version",
        schema="public",
    )

    # 3. Restore the original notification-recipient constraint.
    # Generic admin-only notifications cannot satisfy it, so remove those rows.
    op.execute(
        """
        DELETE FROM public.notifications
        WHERE tech_id IS NULL
          AND customer_user_id IS NULL
        """
    )

    with op.batch_alter_table("notifications", schema="public") as batch_op:
        batch_op.drop_index("ix_notifications_recipient_unread")
        batch_op.drop_index("uq_notifications_recipient_group")

        batch_op.drop_constraint(
            "notification_has_recipient",
            type_="check",
        )
        batch_op.create_check_constraint(
            "notification_has_recipient",
            "tech_id IS NOT NULL OR customer_user_id IS NOT NULL",
        )

        batch_op.drop_column("event_version")
        batch_op.drop_column("updated_at")
        batch_op.drop_column("group_key")
        batch_op.drop_column("recipient_role")
        batch_op.drop_column("recipient_id")
