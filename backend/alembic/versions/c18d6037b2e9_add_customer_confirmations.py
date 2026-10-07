"""add customer confirmations

Revision ID: c18d6037b2e9
Revises: 20bf78cca4ac
Create Date: 2026-10-01 14:57:15.520849

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c18d6037b2e9'
down_revision: Union[str, Sequence[str], None] = '20bf78cca4ac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create customer confirmations table."""

    op.create_table(
        "customer_confirmations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("job_closure_id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("customer_id", sa.String(length=50), nullable=False),
        sa.Column("decision", sa.String(length=30), nullable=False),
        sa.Column("comments", sa.Text(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
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

    op.create_index(
        "ix_customer_confirmations_id",
        "customer_confirmations",
        ["id"],
        unique=False,
    )

    op.create_index(
        "ix_customer_confirmations_job_id",
        "customer_confirmations",
        ["job_id"],
        unique=False,
    )

    op.create_index(
        "ix_customer_confirmations_job_closure_id",
        "customer_confirmations",
        ["job_closure_id"],
        unique=False,
    )

    op.create_index(
        "ix_customer_confirmations_tenant_id",
        "customer_confirmations",
        ["tenant_id"],
        unique=False,
    )

    op.create_index(
        "ix_customer_confirmations_customer_id",
        "customer_confirmations",
        ["customer_id"],
        unique=False,
    )

    op.create_index(
        "ix_customer_confirmations_decision",
        "customer_confirmations",
        ["decision"],
        unique=False,
    )


def downgrade() -> None:
    """Drop customer confirmations table."""

    op.drop_index(
        "ix_customer_confirmations_decision",
        table_name="customer_confirmations",
    )
    op.drop_index(
        "ix_customer_confirmations_customer_id",
        table_name="customer_confirmations",
    )
    op.drop_index(
        "ix_customer_confirmations_tenant_id",
        table_name="customer_confirmations",
    )
    op.drop_index(
        "ix_customer_confirmations_job_closure_id",
        table_name="customer_confirmations",
    )
    op.drop_index(
        "ix_customer_confirmations_job_id",
        table_name="customer_confirmations",
    )
    op.drop_index(
        "ix_customer_confirmations_id",
        table_name="customer_confirmations",
    )

    op.drop_table("customer_confirmations")
