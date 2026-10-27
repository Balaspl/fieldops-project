
"""Persist customer and technician conversations per job.

Revision ID: f0a4c2d7e911
Revises: e32ad70f6b8c
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "f0a4c2d7e911"
down_revision = "e32ad70f6b8c"
branch_labels = None
depends_on = None


TABLE_NAME = "job_messages"

INDEXES = {
    "ix_job_messages_job_created": ["job_id", "created_at"],
    "ix_job_messages_tenant_job": ["tenant_id", "job_id"],
    "ix_job_messages_sender": ["sender_user_id"],
}


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)

    # Create the table only when it does not already exist.
    if not inspector.has_table(TABLE_NAME, schema="public"):
        op.create_table(
            TABLE_NAME,
            sa.Column(
                "id",
                sa.String(length=36),
                primary_key=True,
                nullable=False,
            ),
            sa.Column(
                "job_id",
                sa.Integer(),
                sa.ForeignKey("jobs.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "tenant_id",
                sa.String(length=50),
                sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column(
                "sender_user_id",
                sa.String(length=36),
                sa.ForeignKey("users.id", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column(
                "sender_role",
                sa.String(length=20),
                nullable=False,
            ),
            sa.Column(
                "body",
                sa.Text(),
                nullable=False,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "delivered_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
            sa.Column(
                "read_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
            schema="public",
        )

    # Refresh metadata after table creation.
    inspector = inspect(conn)

    # Create only indexes that are missing.
    existing_indexes = {
        index["name"]
        for index in inspector.get_indexes(TABLE_NAME, schema="public")
    }

    for index_name, columns in INDEXES.items():
        if index_name not in existing_indexes:
            op.create_index(
                index_name,
                TABLE_NAME,
                columns,
                schema="public",
            )


def downgrade() -> None:
    """Remove messaging objects created by this migration.

    Do not drop the table automatically: it may have existed before
    this migration and may already contain real messages.
    """
    conn = op.get_bind()
    inspector = inspect(conn)

    if not inspector.has_table(TABLE_NAME, schema="public"):
        return

    existing_indexes = {
        index["name"]
        for index in inspector.get_indexes(TABLE_NAME, schema="public")
    }

    for index_name in reversed(list(INDEXES.keys())):
        if index_name in existing_indexes:
            op.drop_index(
                index_name,
                table_name=TABLE_NAME,
                schema="public",
            )
