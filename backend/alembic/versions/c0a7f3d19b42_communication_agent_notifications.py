
"""Communication agent: generic recipients, live-card group_key, channel deliveries,
and event version.

Revision ID: c0a7f3d19b42
Revises: 30cd13a2cc68
Create Date: 2026-10-15
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "c0a7f3d19b42"
down_revision = "30cd13a2cc68"
branch_labels = None
depends_on = None

SCHEMA = "public"


def _inspector():
    return inspect(op.get_bind())


def _has_table(table_name):
    return _inspector().has_table(table_name, schema=SCHEMA)


def _columns(table_name):
    if not _has_table(table_name):
        return set()
    return {
        column["name"]
        for column in _inspector().get_columns(table_name, schema=SCHEMA)
    }


def _indexes(table_name):
    if not _has_table(table_name):
        return set()
    return {
        index["name"]
        for index in _inspector().get_indexes(table_name, schema=SCHEMA)
    }


def _checks(table_name):
    if not _has_table(table_name):
        return set()
    return {
        constraint["name"]
        for constraint in _inspector().get_check_constraints(
            table_name, schema=SCHEMA
        )
    }


def _add_column_if_missing(table_name, column):
    if column.name not in _columns(table_name):
        op.add_column(table_name, column, schema=SCHEMA)


def _create_index_if_missing(name, table_name, columns, unique=False):
    if name not in _indexes(table_name):
        op.create_index(
            name,
            table_name,
            columns,
            unique=unique,
            schema=SCHEMA,
        )


def _create_delivery_table_if_missing():
    """Create the channel-delivery table only when absent; preserve existing rows."""
    table_name = "notification_channel_deliveries"

    if _has_table(table_name):
        required = {
            "id",
            "tenant_id",
            "notification_id",
            "channel",
            "recipient_id",
            "status",
            "provider_id",
            "error_message",
            "attempts",
            "idempotency_key",
            "created_at",
            "updated_at",
        }
        missing = required - _columns(table_name)
        if missing:
            raise RuntimeError(
                "Existing notification_channel_deliveries table is missing "
                f"columns: {sorted(missing)}. Reconcile the schema before "
                "continuing this migration."
            )

        # Preserve existing records and ensure expected defaults.
        op.alter_column(
            table_name,
            "status",
            schema=SCHEMA,
            existing_type=sa.String(length=30),
            existing_nullable=False,
            server_default=sa.text("'queued'"),
        )
        op.alter_column(
            table_name,
            "attempts",
            schema=SCHEMA,
            existing_type=sa.Integer(),
            existing_nullable=False,
            server_default=sa.text("0"),
        )
        return

    op.create_table(
        table_name,
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
        schema=SCHEMA,
    )


def upgrade():
    # 1. Add generic-recipient and event-version fields if absent.
    notification_columns = [
        sa.Column("recipient_id", sa.String(50), nullable=True),
        sa.Column("recipient_role", sa.String(20), nullable=True),
        sa.Column("group_key", sa.String(100), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.Column(
            "event_version",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    ]

    for column in notification_columns:
        _add_column_if_missing("notifications", column)

    # 2. Backfill existing notifications without overwriting values
    # that are already populated.
    op.execute(
        """
        UPDATE public.notifications
        SET
            recipient_id = COALESCE(
                recipient_id, tech_id, customer_user_id
            ),
            recipient_role = COALESCE(
                recipient_role,
                CASE
                    WHEN tech_id IS NOT NULL THEN 'technician'
                    WHEN customer_user_id IS NOT NULL THEN 'customer'
                    ELSE NULL
                END
            ),
            updated_at = COALESCE(updated_at, created_at),
            event_version = COALESCE(event_version, 0)
        WHERE recipient_id IS NULL
           OR recipient_role IS NULL
           OR updated_at IS NULL
           OR event_version IS NULL
        """
    )

    # Assign distinct group keys to historical notifications.
    op.execute(
        """
        UPDATE public.notifications
        SET group_key = 'legacy_' || id::text
        WHERE group_key IS NULL
        """
    )

    # 3. Allow generic recipients while preserving compatibility with
    # existing technician/customer recipient columns.
    if "notification_has_recipient" in _checks("notifications"):
        op.drop_constraint(
            "notification_has_recipient",
            "notifications",
            type_="check",
            schema=SCHEMA,
        )

    op.create_check_constraint(
        "notification_has_recipient",
        "notifications",
        """
        tech_id IS NOT NULL
        OR customer_user_id IS NOT NULL
        OR recipient_id IS NOT NULL
        """,
        schema=SCHEMA,
    )

    # 4. Create tenant-aware notification indexes if missing.
    _create_index_if_missing(
        "uq_notifications_recipient_group",
        "notifications",
        ["tenant_id", "recipient_role", "recipient_id", "group_key"],
        unique=True,
    )
    _create_index_if_missing(
        "ix_notifications_recipient_unread",
        "notifications",
        ["tenant_id", "recipient_id", "read_at"],
    )

    # 5. Add the job notification event counter if absent.
    _add_column_if_missing(
        "jobs",
        sa.Column(
            "notification_event_version",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )

    # 6. Create or adopt the per-channel delivery table.
    # Existing delivery records are never dropped or recreated.
    _create_delivery_table_if_missing()

    # 7. Create delivery indexes if missing.
    _create_index_if_missing(
        "ix_notification_channel_deliveries_tenant_id",
        "notification_channel_deliveries",
        ["tenant_id"],
    )
    _create_index_if_missing(
        "uq_ncd_idempotency",
        "notification_channel_deliveries",
        ["idempotency_key"],
        unique=True,
    )
    _create_index_if_missing(
        "ix_ncd_notification",
        "notification_channel_deliveries",
        ["notification_id"],
    )


def downgrade():
    # This migration may adopt a delivery table that existed before it ran.
    # A blind downgrade could delete existing data or remove schema objects
    # owned by another migration. Require a reviewed rollback instead.
    raise RuntimeError(
        "Automatic downgrade is disabled to protect existing notification "
        "and channel-delivery data. Create a reviewed rollback migration "
        "after verifying schema ownership and backing up required data."
    )
