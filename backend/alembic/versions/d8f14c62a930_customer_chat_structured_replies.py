"""Persist typed customer chat reply components and follow-ups.

Revision ID: d8f14c62a930
Revises: c714a2f8d391
"""
from alembic import op
import sqlalchemy as sa

revision = "d8f14c62a930"
down_revision = "c714a2f8d391"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("customer_chat_messages", sa.Column("response_components", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("customer_chat_messages", sa.Column("follow_up_suggestions", sa.JSON(), nullable=False, server_default="[]"))
    op.execute(sa.text("""UPDATE customer_support_faqs
        SET answer = :answer
        WHERE tenant_id IS NULL AND faq_key = 'completion_report'""").bindparams(answer=(
        "A closure report is a PDF summary of a job's recorded closure, including service, completion date, location, and work summary. For a specific job, ask me about its report and I can show a download button when a closure record is available. If you cannot access a report, contact FieldOps Support."
    )))


def downgrade() -> None:
    op.drop_column("customer_chat_messages", "follow_up_suggestions")
    op.drop_column("customer_chat_messages", "response_components")
