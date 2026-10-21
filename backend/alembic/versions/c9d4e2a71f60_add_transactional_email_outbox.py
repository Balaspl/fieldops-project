"""Add durable independent transactional email outbox."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "c9d4e2a71f60"
down_revision = "ba7d2e9c104f"
branch_labels = None
depends_on = None

SCHEMA = "public"
TABLE = "transactional_email_outbox"
INDEX = "ix_transactional_email_due"


def _inspector():
    return inspect(op.get_bind())


def _table_exists():
    return _inspector().has_table(TABLE, schema=SCHEMA)


def _column_names():
    if not _table_exists():
        return set()

    return {
        column["name"]
        for column in _inspector().get_columns(TABLE, schema=SCHEMA)
    }


def upgrade() -> None:
    if not _table_exists():
        op.create_table(
            TABLE,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(length=50), nullable=False),
            sa.Column("job_id", sa.Integer(), nullable=False),
            sa.Column("customer_id", sa.String(length=50), nullable=True),
            sa.Column("recipient_email", sa.String(length=320), nullable=True),
            sa.Column("event_type", sa.String(length=40), nullable=False),
            sa.Column("event_version", sa.Integer(), nullable=False),
            sa.Column("idempotency_key", sa.String(length=180), nullable=False),
            sa.Column(
                "status",
                sa.String(length=24),
                server_default=sa.text("'pending'"),
                nullable=False,
            ),
            sa.Column(
                "attempts",
                sa.Integer(),
                server_default=sa.text("0"),
                nullable=False,
            ),
            sa.Column(
                "next_attempt_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("smtp_status", sa.Integer(), nullable=True),
            sa.Column("provider_message_id", sa.String(length=255), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(
                ["tenant_id"],
                ["organizations.id"],
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["job_id"],
                ["jobs.id"],
                ondelete="CASCADE",
            ),
            sa.UniqueConstraint(
                "idempotency_key",
                name="uq_transactional_email_idempotency",
            ),
            schema=SCHEMA,
        )

    # Never silently accept an incompatible pre-existing table.
    required_columns = {
        "id",
        "tenant_id",
        "job_id",
        "customer_id",
        "recipient_email",
        "event_type",
        "event_version",
        "idempotency_key",
        "status",
        "attempts",
        "next_attempt_at",
        "last_error",
        "smtp_status",
        "provider_message_id",
        "created_at",
        "updated_at",
        "sent_at",
    }

    missing = required_columns - _column_names()

    if missing:
        raise RuntimeError(
            f"Existing {TABLE} table is missing columns: "
            f"{sorted(missing)}. Reconcile its schema before continuing."
        )

    # Verify that the idempotency constraint already exists before
    # proceeding with the index creation. Do not delete existing rows.
    inspector = _inspector()

    unique_constraints = {
        constraint.get("name")
        for constraint in inspector.get_unique_constraints(
            TABLE, schema=SCHEMA
        )
    }
    unique_indexes = {
        index.get("name")
        for index in inspector.get_indexes(TABLE, schema=SCHEMA)
        if index.get("unique")
    }

    if (
        "uq_transactional_email_idempotency" not in unique_constraints
        and "uq_transactional_email_idempotency" not in unique_indexes
    ):
        duplicate_keys = op.get_bind().execute(
            sa.text("""
                SELECT idempotency_key
                FROM public.transactional_email_outbox
                GROUP BY idempotency_key
                HAVING COUNT(*) > 1
                LIMIT 1
            """)
        ).first()

        if duplicate_keys:
            raise RuntimeError(
                "Cannot add the idempotency uniqueness constraint: "
                "duplicate idempotency_key values exist. Resolve them "
                "before continuing."
            )

        op.create_unique_constraint(
            "uq_transactional_email_idempotency",
            TABLE,
            ["idempotency_key"],
            schema=SCHEMA,
        )

    indexes = {
        index["name"]
        for index in _inspector().get_indexes(TABLE, schema=SCHEMA)
    }

    if INDEX not in indexes:
        op.create_index(
            INDEX,
            TABLE,
            ["status", "next_attempt_at"],
            schema=SCHEMA,
        )


def downgrade() -> None:
    # This migration may have adopted a table that existed before it ran.
    # Refuse to drop it automatically, protecting queued email records.
    raise RuntimeError(
        "Automatic downgrade is disabled to protect transactional email "
        "records. Use a reviewed rollback migration after verifying that "
        "the table was created exclusively by this revision."
    )