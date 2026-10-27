"""Add generated closure reports and generation state.

Revision ID: d24c6ef10871
Revises: 7ac43d11bf20, 219895425dee, d10d76fc7a78
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d24c6ef10871"
down_revision: Union[str, Sequence[str], None] = (
    "7ac43d11bf20",
    "219895425dee",
    "d10d76fc7a78",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("job_closures", sa.Column("closure_report", sa.JSON(), nullable=True))
    op.add_column(
        "job_closures",
        sa.Column("closure_report_status", sa.String(length=20), nullable=False, server_default="PENDING"),
    )
    op.create_check_constraint(
        "ck_job_closures_report_status",
        "job_closures",
        "closure_report_status IN ('PENDING', 'GENERATING', 'SUCCEEDED', 'FAILED')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_job_closures_report_status", "job_closures", type_="check")
    op.drop_column("job_closures", "closure_report_status")
    op.drop_column("job_closures", "closure_report")
