"""add oidc identity user constraint

Revision ID: 57218f56acf
Revises: bcbb1bcc4e59
Create Date: 2026-09-15
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "57218f56acf"
down_revision: Union[str, Sequence[str], None] = "bcbb1bcc4e59"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add unique constraint for one OIDC identity per FieldOps user."""

    op.create_unique_constraint(
        "uq_oidc_identity_user_id",
        "oidc_identities",
        ["user_id"],
    )


def downgrade() -> None:
    """Remove unique constraint for OIDC identity user."""

    op.drop_constraint(
        "uq_oidc_identity_user_id",
        "oidc_identities",
        type_="unique",
    )