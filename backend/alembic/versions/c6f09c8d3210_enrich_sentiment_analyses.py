"""enrich sentiment analyses for customer job chat

Revision ID: c6f09c8d3210
Revises: b51c8d0e4a29
Create Date: 2026-11-03
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c6f09c8d3210"
down_revision: Union[str, Sequence[str], None] = "b51c8d0e4a29"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sentiment_thread_messages", sa.Column("severity", sa.String(length=20), nullable=True))
    op.add_column("sentiment_thread_messages", sa.Column("issue_categories", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("sentiment_thread_messages", sa.Column("recommended_action", sa.Text(), nullable=True))
    op.add_column("sentiment_thread_messages", sa.Column("source_message_id", sa.String(length=36), nullable=True))
    op.create_foreign_key(
        "fk_sentiment_thread_source_job_message",
        "sentiment_thread_messages",
        "job_messages",
        ["source_message_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_sentiment_thread_messages_source_message_id",
        "sentiment_thread_messages",
        ["source_message_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_sentiment_thread_messages_source_message_id", table_name="sentiment_thread_messages")
    op.drop_constraint("fk_sentiment_thread_source_job_message", "sentiment_thread_messages", type_="foreignkey")
    op.drop_column("sentiment_thread_messages", "source_message_id")
    op.drop_column("sentiment_thread_messages", "recommended_action")
    op.drop_column("sentiment_thread_messages", "issue_categories")
    op.drop_column("sentiment_thread_messages", "severity")
