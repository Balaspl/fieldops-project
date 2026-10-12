
"""add customer confirmations

Revision ID: c18d6037b2e9
Revises: 20bf78cca4ac
Create Date: 2026-10-01 14:57:15.520849
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c18d6037b2e9"
down_revision: Union[str, Sequence[str], None] = "20bf78cca4ac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "customer_confirmations"

INDEX_DEFINITIONS = {
    "ix_customer_confirmations_id": ["id"],
    "ix_customer_confirmations_job_id": ["job_id"],
    "ix_customer_confirmations_job_closure_id": ["job_closure_id"],
    "ix_customer_confirmations_tenant_id": ["tenant_id"],
    "ix_customer_confirmations_customer_id": ["customer_id"],
    "ix_customer_confirmations_decision": ["decision"],
}


def _validate_existing_table(inspector) -> None:
    """Fail rather than silently accepting an incompatible existing table."""
    columns = {
        column["name"]: column
        for column in inspector.get_columns(TABLE_NAME)
    }

    expected_columns = {
        "id",
        "job_id",
        "job_closure_id",
        "tenant_id",
        "customer_id",
        "decision",
        "comments",
        "confirmed_at",
        "created_at",
        "updated_at",
    }

    missing_columns = expected_columns - columns.keys()
    if missing_columns:
        raise RuntimeError(
            f"{TABLE_NAME} is missing columns: {sorted(missing_columns)}"
        )

    expected_foreign_keys = {
        "customer_confirmations_job_id_fkey": (
            "job_id",
            "jobs",
            "CASCADE",
        ),
        "customer_confirmations_job_closure_id_fkey": (
            "job_closure_id",
            "job_closures",
            "CASCADE",
        ),
        "customer_confirmations_tenant_id_fkey": (
            "tenant_id",
            "organizations",
            "RESTRICT",
        ),
    }

    actual_foreign_keys = {
        fk["name"]: fk
        for fk in inspector.get_foreign_keys(TABLE_NAME)
    }

    for name, (column, referred_table, ondelete) in (
        expected_foreign_keys.items()
    ):
        fk = actual_foreign_keys.get(name)
        if fk is None:
            raise RuntimeError(
                f"{TABLE_NAME} is missing foreign key {name}"
            )

        options = fk.get("options") or {}
        actual_ondelete = (options.get("ondelete") or "").upper()

        if (
            fk.get("constrained_columns") != [column]
            or fk.get("referred_table") != referred_table
            or actual_ondelete != ondelete
        ):
            raise RuntimeError(
                f"{TABLE_NAME} foreign key {name} does not match "
                "the migration definition"
            )

    unique_constraints = {
        constraint.get("name"): constraint
        for constraint in inspector.get_unique_constraints(TABLE_NAME)
    }
    unique_constraint = unique_constraints.get(
        "uq_customer_confirmations_job"
    )

    if (
        unique_constraint is None
        or unique_constraint.get("column_names") != ["job_id"]
    ):
        raise RuntimeError(
            f"{TABLE_NAME} is missing the expected unique constraint "
            "uq_customer_confirmations_job"
        )

    indexes = {
        index["name"]: index
        for index in inspector.get_indexes(TABLE_NAME)
    }

    for name, expected_columns_for_index in INDEX_DEFINITIONS.items():
        index = indexes.get(name)
        if (
            index is None
            or index.get("column_names") != expected_columns_for_index
            or index.get("unique", False)
        ):
            raise RuntimeError(
                f"{TABLE_NAME} index {name} is missing or incompatible"
            )


def upgrade() -> None:
    """Create the table, or verify it if it already exists."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table(TABLE_NAME):
        _validate_existing_table(inspector)
        return

    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("job_closure_id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("customer_id", sa.String(length=50), nullable=False),
        sa.Column("decision", sa.String(length=30), nullable=False),
        sa.Column("comments", sa.Text(), nullable=True),
        sa.Column(
            "confirmed_at",
            sa.DateTime(timezone=True),
            nullable=False,
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
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["job_closure_id"],
            ["job_closures.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "job_id",
            name="uq_customer_confirmations_job",
        ),
    )

    for index_name, columns in INDEX_DEFINITIONS.items():
        op.create_index(
            index_name,
            TABLE_NAME,
            columns,
            unique=False,
        )


def downgrade() -> None:
    """Drop the table created by this migration.

    This downgrade is intentionally conservative: because the table may
    have existed before this revision was recorded, it is not safe to
    drop it automatically. Handle downgrade through a reviewed,
    environment-specific database recovery procedure instead.
    """
    raise RuntimeError(
        "Automatic downgrade of customer_confirmations is disabled "
        "because the table may predate this migration. Review the "
        "database state and back up data before performing a manual "
        "rollback."
    )
