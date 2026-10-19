"""Add durable independent transactional email outbox."""

from alembic import op
import sqlalchemy as sa


revision = "c9d4e2a71f60"
down_revision = "ba7d2e9c104f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "transactional_email_outbox",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.String(length=50), nullable=True),
        sa.Column("recipient_email", sa.String(length=320), nullable=True),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("event_version", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=180), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("smtp_status", sa.Integer(), nullable=True),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("idempotency_key", name="uq_transactional_email_idempotency"),
        schema="public",
    )
    op.create_index(
        "ix_transactional_email_due",
        "transactional_email_outbox",
        ["status", "next_attempt_at"],
        schema="public",
    )


def downgrade() -> None:
    op.drop_index("ix_transactional_email_due", table_name="transactional_email_outbox", schema="public")
    op.drop_table("transactional_email_outbox", schema="public")
