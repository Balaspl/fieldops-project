"""support customer chat sentiment source records

Revision ID: d17a93c1be42
Revises: c6f09c8d3210
Create Date: 2026-11-03
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d17a93c1be42"
down_revision: Union[str, Sequence[str], None] = "c6f09c8d3210"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("sentiment_thread_messages", "job_id", existing_type=sa.Integer(), nullable=True)
    op.alter_column("sentiment_escalations", "job_id", existing_type=sa.Integer(), nullable=True)
    op.add_column("sentiment_thread_messages", sa.Column("source_type", sa.String(length=30), nullable=True))
    op.add_column("sentiment_thread_messages", sa.Column("source_id", sa.String(length=64), nullable=True))
    op.execute("UPDATE sentiment_thread_messages SET source_type = 'JOB_CHAT', source_id = source_message_id WHERE source_message_id IS NOT NULL")
    op.create_index("uq_sentiment_thread_source", "sentiment_thread_messages", ["source_type", "source_id"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_sentiment_thread_source", table_name="sentiment_thread_messages")
    op.drop_column("sentiment_thread_messages", "source_id")
    op.drop_column("sentiment_thread_messages", "source_type")
    op.alter_column("sentiment_escalations", "job_id", existing_type=sa.Integer(), nullable=False)
    op.alter_column("sentiment_thread_messages", "job_id", existing_type=sa.Integer(), nullable=False)
