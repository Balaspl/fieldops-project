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
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Inspect columns already present in the chat messages table.
    existing_columns = {
        column["name"]
        for column in inspector.get_columns(
            "customer_chat_messages",
            schema="public",
        )
    }

    # Add response_components only if it does not exist.
    if "response_components" not in existing_columns:
        op.add_column(
            "customer_chat_messages",
            sa.Column(
                "response_components",
                sa.JSON(),
                nullable=False,
                server_default="[]",
            ),
            schema="public",
        )

    # Add follow_up_suggestions only if it does not exist.
    if "follow_up_suggestions" not in existing_columns:
        op.add_column(
            "customer_chat_messages",
            sa.Column(
                "follow_up_suggestions",
                sa.JSON(),
                nullable=False,
                server_default="[]",
            ),
            schema="public",
        )

    # Update the shared completion-report FAQ answer.
    # This update is safe to run again.
    op.execute(
        sa.text(
            """
            UPDATE public.customer_support_faqs
            SET answer = :answer
            WHERE tenant_id IS NULL
              AND faq_key = 'completion_report'
            """
        ).bindparams(
            answer=(
                "A closure report is a PDF summary of a job's recorded "
                "closure, including service, completion date, location, "
                "and work summary. For a specific job, ask me about its "
                "report and I can show a download button when a closure "
                "record is available. If you cannot access a report, "
                "contact FieldOps Support."
            )
        )
    )


def downgrade() -> None:
    # Some columns may have existed before this migration ran.
    # Do not automatically drop them, because that could destroy
    # existing customer chat data.
    raise RuntimeError(
        "Automatic downgrade is disabled for this migration because "
        "response_components or follow_up_suggestions may have existed "
        "before the migration. Verify column ownership and back up the "
        "database before performing a manual rollback."
    )