"""add MFA tables

Revision ID: 5b9a26aea696
Revises: 57218f56acf
Create Date: 2026-09-15
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "5b9a26aea696"
down_revision: Union[str, Sequence[str], None] = "57218f56acf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create MFA configuration and recovery-code tables."""

    op.create_table(
        "user_mfa",
        sa.Column(
            "id",
            sa.String(length=36),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.String(length=36),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            sa.String(length=50),
            nullable=False,
        ),
        sa.Column(
            "secret_encrypted",
            sa.String(length=512),
            nullable=False,
        ),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "enrolled_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "recovery_codes_generated_at",
            sa.DateTime(timezone=True),
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
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            name="uq_user_mfa_user_id",
        ),
    )

    op.create_index(
        "ix_user_mfa_user_id",
        "user_mfa",
        ["user_id"],
    )

    op.create_index(
        "ix_user_mfa_tenant_id",
        "user_mfa",
        ["tenant_id"],
    )

    op.create_index(
        "idx_user_mfa_tenant_user",
        "user_mfa",
        ["tenant_id", "user_id"],
    )

    op.create_table(
        "mfa_recovery_codes",
        sa.Column(
            "id",
            sa.String(length=36),
            nullable=False,
        ),
        sa.Column(
            "mfa_id",
            sa.String(length=36),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            sa.String(length=50),
            nullable=False,
        ),
        sa.Column(
            "code_hash",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "used",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "used_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["mfa_id"],
            ["user_mfa.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_mfa_recovery_codes_mfa_id",
        "mfa_recovery_codes",
        ["mfa_id"],
    )

    op.create_index(
        "ix_mfa_recovery_codes_tenant_id",
        "mfa_recovery_codes",
        ["tenant_id"],
    )

    op.create_index(
        "idx_mfa_recovery_tenant_mfa",
        "mfa_recovery_codes",
        ["tenant_id", "mfa_id"],
    )


def downgrade() -> None:
    """Remove MFA tables."""

    op.drop_index(
        "idx_mfa_recovery_tenant_mfa",
        table_name="mfa_recovery_codes",
    )

    op.drop_index(
        "ix_mfa_recovery_codes_tenant_id",
        table_name="mfa_recovery_codes",
    )

    op.drop_index(
        "ix_mfa_recovery_codes_mfa_id",
        table_name="mfa_recovery_codes",
    )

    op.drop_table("mfa_recovery_codes")

    op.drop_index(
        "idx_user_mfa_tenant_user",
        table_name="user_mfa",
    )

    op.drop_index(
        "ix_user_mfa_tenant_id",
        table_name="user_mfa",
    )

    op.drop_index(
        "ix_user_mfa_user_id",
        table_name="user_mfa",
    )

    op.drop_table("user_mfa")