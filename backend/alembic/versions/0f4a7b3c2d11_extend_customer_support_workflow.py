"""extend customer support workflow

Revision ID: 0f4a7b3c2d11
Revises: c4d7e19a2b31
Create Date: 2026-10-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0f4a7b3c2d11"
down_revision: Union[str, Sequence[str], None] = "c4d7e19a2b31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "customer_support_requests"
INDEX_NAME = "ix_customer_support_requests_related_job_id"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {
        column["name"] for column in inspector.get_columns(TABLE_NAME)
    }
    foreign_keys = {
        fk.get("name") for fk in inspector.get_foreign_keys(TABLE_NAME)
    }
    indexes = {
        index.get("name") for index in inspector.get_indexes(TABLE_NAME)
    }

    if "related_job_id" not in columns:
        op.add_column(
            TABLE_NAME,
            sa.Column("related_job_id", sa.Integer(), nullable=True),
        )

    if "resolution_note" not in columns:
        op.add_column(
            TABLE_NAME,
            sa.Column("resolution_note", sa.Text(), nullable=True),
        )

    if "resolved_at" not in columns:
        op.add_column(
            TABLE_NAME,
            sa.Column(
                "resolved_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )

    if "resolved_by" not in columns:
        op.add_column(
            TABLE_NAME,
            sa.Column(
                "resolved_by",
                sa.String(length=36),
                nullable=True,
            ),
        )

    if INDEX_NAME not in indexes:
        op.create_index(
            INDEX_NAME,
            TABLE_NAME,
            ["related_job_id"],
            unique=False,
        )

    if "fk_customer_support_related_job" not in foreign_keys:
        op.create_foreign_key(
            "fk_customer_support_related_job",
            TABLE_NAME,
            "jobs",
            ["related_job_id"],
            ["id"],
            ondelete="SET NULL",
        )

    if "fk_customer_support_resolved_by" not in foreign_keys:
        op.create_foreign_key(
            "fk_customer_support_resolved_by",
            TABLE_NAME,
            "users",
            ["resolved_by"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    foreign_keys = {
        fk.get("name") for fk in inspector.get_foreign_keys(TABLE_NAME)
    }
    indexes = {
        index.get("name") for index in inspector.get_indexes(TABLE_NAME)
    }
    columns = {
        column["name"] for column in inspector.get_columns(TABLE_NAME)
    }

    if "fk_customer_support_resolved_by" in foreign_keys:
        op.drop_constraint(
            "fk_customer_support_resolved_by",
            TABLE_NAME,
            type_="foreignkey",
        )

    if "fk_customer_support_related_job" in foreign_keys:
        op.drop_constraint(
            "fk_customer_support_related_job",
            TABLE_NAME,
            type_="foreignkey",
        )

    if INDEX_NAME in indexes:
        op.drop_index(INDEX_NAME, table_name=TABLE_NAME)

    for column_name in (
        "resolved_by",
        "resolved_at",
        "resolution_note",
        "related_job_id",
    ):
        if column_name in columns:
            op.drop_column(TABLE_NAME, column_name)