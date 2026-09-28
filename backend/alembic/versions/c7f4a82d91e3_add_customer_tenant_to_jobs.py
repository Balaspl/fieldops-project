"""Track the customer tenant that originated a routed service job.

Revision ID: c7f4a82d91e3
Revises: 1b0e1c93d5ab
Create Date: 2026-09-26
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c7f4a82d91e3"
down_revision: Union[str, Sequence[str], None] = "1b0e1c93d5ab"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.add_column(sa.Column("customer_tenant_id", sa.String(length=50), nullable=True))
        batch_op.create_foreign_key(
            "fk_jobs_customer_tenant_id_organizations",
            "organizations",
            ["customer_tenant_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_index("ix_jobs_customer_tenant_id", ["customer_tenant_id"], unique=False)

    # Preserve existing admin visibility for jobs created before provenance was tracked.
    op.execute("UPDATE jobs SET customer_tenant_id = tenant_id WHERE customer_tenant_id IS NULL")


def downgrade() -> None:
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.drop_index("ix_jobs_customer_tenant_id")
        batch_op.drop_constraint("fk_jobs_customer_tenant_id_organizations", type_="foreignkey")
        batch_op.drop_column("customer_tenant_id")
