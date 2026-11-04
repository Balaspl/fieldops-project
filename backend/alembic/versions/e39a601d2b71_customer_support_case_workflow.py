"""connect support chat to trackable customer support cases

Revision ID: e39a601d2b71
Revises: d17a93c1be42
Create Date: 2026-11-03
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e39a601d2b71"
down_revision: Union[str, Sequence[str], None] = "d17a93c1be42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    def inspector():
        # Recreate after DDL so cached table/column state cannot cause duplicate operations.
        return sa.inspect(bind)

    request_columns = {column["name"] for column in inspector().get_columns("customer_support_requests")}
    for name, column in (
        ("category", sa.Column("category", sa.String(length=40), nullable=False, server_default="OTHER")),
        ("priority", sa.Column("priority", sa.String(length=20), nullable=False, server_default="MEDIUM")),
        ("assigned_staff_id", sa.Column("assigned_staff_id", sa.String(length=36), nullable=True)),
        ("source_chat_conversation_id", sa.Column("source_chat_conversation_id", sa.String(length=36), nullable=True)),
    ):
        if name not in request_columns:
            op.add_column("customer_support_requests", column)

    current = inspector()
    request_fks = current.get_foreign_keys("customer_support_requests")
    if not any(fk.get("constrained_columns") == ["assigned_staff_id"] for fk in request_fks):
        op.create_foreign_key("fk_customer_support_requests_assigned_staff", "customer_support_requests", "users", ["assigned_staff_id"], ["id"], ondelete="SET NULL")
    request_indexes = {index["name"] for index in inspector().get_indexes("customer_support_requests")}
    if "ix_customer_support_requests_assigned_staff_id" not in request_indexes:
        op.create_index("ix_customer_support_requests_assigned_staff_id", "customer_support_requests", ["assigned_staff_id"])
    if "uq_customer_support_source_chat" not in request_indexes:
        op.create_index("uq_customer_support_source_chat", "customer_support_requests", ["source_chat_conversation_id"], unique=True)

    if not inspector().has_table("customer_support_case_updates"):
        op.create_table(
            "customer_support_case_updates",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("support_request_id", sa.Integer(), nullable=False),
            sa.Column("author_user_id", sa.String(length=36), nullable=True),
            sa.Column("author_role", sa.String(length=20), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["support_request_id"], ["customer_support_requests.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["author_user_id"], ["users.id"], ondelete="SET NULL"),
        )

    current = inspector()
    update_fks = current.get_foreign_keys("customer_support_case_updates")
    if not any(fk.get("constrained_columns") == ["support_request_id"] for fk in update_fks):
        op.create_foreign_key("fk_customer_support_case_updates_request", "customer_support_case_updates", "customer_support_requests", ["support_request_id"], ["id"], ondelete="CASCADE")
    if not any(fk.get("constrained_columns") == ["author_user_id"] for fk in update_fks):
        op.create_foreign_key("fk_customer_support_case_updates_author", "customer_support_case_updates", "users", ["author_user_id"], ["id"], ondelete="SET NULL")
    update_indexes = {index["name"] for index in inspector().get_indexes("customer_support_case_updates")}
    if "ix_customer_support_case_updates_support_request_id" not in update_indexes:
        op.create_index("ix_customer_support_case_updates_support_request_id", "customer_support_case_updates", ["support_request_id"])
    if "ix_customer_support_case_updates_created_at" not in update_indexes:
        op.create_index("ix_customer_support_case_updates_created_at", "customer_support_case_updates", ["created_at"])


def downgrade() -> None:
    raise RuntimeError(
        "Automatic downgrade is disabled because customer_support_case_updates "
        "may have existed before this migration and contain case history. "
        "Verify the database and back up case updates before manually rolling back."
    )
