"""Fix tenant-aware notification upsert index.

Revision ID: e4c28b7a91f0
Revises: c0a7f3d19b42
Create Date: 2026-10-16
"""

from alembic import op


revision = "e4c28b7a91f0"
down_revision = "c0a7f3d19b42"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Refuse to change the uniqueness boundary if real (non-NULL) group keys
    # already collide. Do not delete or rewrite notification rows in a schema
    # migration.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM public.notifications
                WHERE group_key IS NOT NULL
                GROUP BY tenant_id, recipient_role, recipient_id, group_key
                HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION
                    'Duplicate non-NULL notification recipient/group keys; '
                    'reconcile rows before applying e4c28b7a91f0';
            END IF;
        END $$;
        """
    )

    # The live index has the old three-column definition. Replace it atomically
    # with the exact target emitted by store.upsert_notification(). PostgreSQL
    # allows historical NULL group_key values to coexist under this index.
    op.drop_index(
        "uq_notifications_recipient_group",
        table_name="notifications",
        schema="public",
        if_exists=True,
    )
    op.create_index(
        "uq_notifications_recipient_group",
        "notifications",
        ["tenant_id", "recipient_role", "recipient_id", "group_key"],
        unique=True,
        schema="public",
    )


def downgrade() -> None:
    op.drop_index(
        "uq_notifications_recipient_group",
        table_name="notifications",
        schema="public",
    )
    op.create_index(
        "uq_notifications_recipient_group",
        "notifications",
        ["recipient_role", "recipient_id", "group_key"],
        unique=True,
        schema="public",
    )
