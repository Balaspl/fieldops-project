"""add job expense submissions

Revision ID: c7a31f4e8d20
Revises: b25cd2562ab8
Create Date: 2026-09-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c7a31f4e8d20"
down_revision: Union[str, Sequence[str], None] = "b25cd2562ab8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "job_expenses"


def upgrade() -> None:
    """
    Create the job_expenses table when it is not already present.

    The application currently calls Base.metadata.create_all() during startup,
    so an existing database can legitimately already contain this table before
    Alembic reaches this revision. In that case, preserve the existing schema
    and let Alembic record this revision as applied.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table(TABLE_NAME):
        return

    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "job_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "technician_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "amount",
            sa.Numeric(12, 2, asdecimal=True),
            nullable=False,
        ),
        sa.Column(
            "description",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
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
        sa.CheckConstraint(
            "amount > 0",
            name="ck_job_expenses_amount_positive",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["technician_id"],
            ["technicians.technician_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_job_expenses_id",
        TABLE_NAME,
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_job_expenses_job_id",
        TABLE_NAME,
        ["job_id"],
        unique=False,
    )
    op.create_index(
        "ix_job_expenses_technician_id",
        TABLE_NAME,
        ["technician_id"],
        unique=False,
    )
    op.create_index(
        "ix_job_expenses_tenant_id",
        TABLE_NAME,
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table(TABLE_NAME):
        return

    op.drop_table(TABLE_NAME)
