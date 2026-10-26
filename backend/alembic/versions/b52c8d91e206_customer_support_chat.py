"""Create customer support chat and FAQ tables.

Revision ID: b52c8d91e206
Revises: f58c1b72a9d4, d24c6ef10871
"""
from alembic import op
import sqlalchemy as sa

revision = "b52c8d91e206"
down_revision = ("f58c1b72a9d4", "d24c6ef10871")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customer_chat_conversations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(50), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("customer_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(120)),
        sa.Column("status", sa.String(20), nullable=False, server_default="OPEN"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('OPEN', 'CLOSED')", name="ck_customer_chat_conversation_status"),
    )
    op.create_index("ix_customer_chat_conversations_owner_updated", "customer_chat_conversations", ["tenant_id", "customer_user_id", "updated_at"])
    op.create_table(
        "customer_chat_messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("customer_chat_conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reply_to_message_id", sa.Integer(), sa.ForeignKey("customer_chat_messages.id", ondelete="CASCADE"), unique=True),
        sa.Column("tenant_id", sa.String(50), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sender_type", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("client_message_id", sa.String(36)),
        sa.Column("intent", sa.String(40)),
        sa.Column("needs_escalation", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="SUCCEEDED"),
        sa.Column("source_references", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("sender_type IN ('customer', 'assistant')", name="ck_customer_chat_message_sender"),
        sa.CheckConstraint("status IN ('PENDING', 'SUCCEEDED', 'FAILED')", name="ck_customer_chat_message_status"),
        sa.CheckConstraint("needs_escalation IN (0, 1)", name="ck_customer_chat_message_escalation"),
        sa.CheckConstraint("length(content) BETWEEN 1 AND 4000", name="ck_customer_chat_message_content_length"),
        sa.UniqueConstraint("conversation_id", "client_message_id", name="uq_customer_chat_client_message"),
    )
    op.create_index("ix_customer_chat_messages_conversation_created", "customer_chat_messages", ["conversation_id", "created_at", "id"])
    op.create_index("ix_customer_chat_messages_tenant_conversation", "customer_chat_messages", ["tenant_id", "conversation_id"])
    op.create_table(
        "customer_support_faqs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(50), sa.ForeignKey("organizations.id", ondelete="CASCADE")),
        sa.Column("question", sa.String(500), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("category", sa.String(60), nullable=False),
        sa.Column("language", sa.String(12), nullable=False, server_default="en"),
        sa.Column("is_published", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("is_published IN (0, 1)", name="ck_customer_support_faq_published"),
    )
    op.create_index("ix_customer_support_faq_scope", "customer_support_faqs", ["tenant_id", "is_published", "category"])


def downgrade() -> None:
    op.drop_table("customer_support_faqs")
    op.drop_table("customer_chat_messages")
    op.drop_table("customer_chat_conversations")
