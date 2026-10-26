
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
IDEMPOTENCY_CONSTRAINT = "uq_transactional_email_idempotency"


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


def _ensure_required_columns():
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


def _ensure_idempotency_constraint():
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
        IDEMPOTENCY_CONSTRAINT in unique_constraints
        or IDEMPOTENCY_CONSTRAINT in unique_indexes
    ):
        return

    # Do not create a uniqueness constraint over duplicate keys.
    duplicate = op.get_bind().execute(
        sa.text(
            """
            SELECT idempotency_key
            FROM public.transactional_email_outbox
            GROUP BY idempotency_key
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        )
    ).first()

    if duplicate:
        raise RuntimeError(
            "Cannot add the transactional email idempotency constraint: "
            "duplicate idempotency_key values exist. Resolve the duplicates "
            "before continuing."
        )

    op.create_unique_constraint(
        IDEMPOTENCY_CONSTRAINT,
        TABLE,
        ["idempotency_key"],
        schema=SCHEMA,
    )


def _ensure_due_index():
    existing_indexes = {
        index["name"]
        for index in _inspector().get_indexes(TABLE, schema=SCHEMA)
    }

    if INDEX not in existing_indexes:
        op.create_index(
            INDEX,
            TABLE,
            ["status", "next_attempt_at"],
            schema=SCHEMA,
        )


def upgrade() -> None:
    # Create the outbox only if it does not already exist.
    # Never drop or recreate an existing table or its queued email records.
    if not _table_exists():
        op.create_table(
            TABLE,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(length=50), nullable=False),
            sa.Column("job_id", sa.Integer(), nullable=False),
            sa.Column("customer_id", sa.String(length=50), nullable=True),
            sa.Column(
                "recipient_email",
                sa.String(length=320),
                nullable=True,
            ),
            sa.Column("event_type", sa.String(length=40), nullable=False),
            sa.Column("event_version", sa.Integer(), nullable=False),
            sa.Column(
                "idempotency_key",
                sa.String(length=180),
                nullable=False,
            ),
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
            sa.Column(
                "provider_message_id",
                sa.String(length=255),
                nullable=True,
            ),
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
            sa.Column(
                "sent_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
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
                name=IDEMPOTENCY_CONSTRAINT,
            ),
            schema=SCHEMA,
        )

    # Validate the table whether it was newly created or already existed.
    _ensure_required_columns()

    # Ensure idempotency protection without deleting existing records.
    _ensure_idempotency_constraint()

    # Create the index used to find pending and due email deliveries.
    _ensure_due_index()


def downgrade() -> None:
    # This migration may have adopted an existing table.
    # Do not automatically delete queued email records or schema objects.
    raise RuntimeError(
        "Automatic downgrade is disabled to protect transactional email "
        "records. Use a reviewed rollback migration after verifying that "
        "the table was created exclusively by this revision and backing "
        "up any data that must be retained."
    )
