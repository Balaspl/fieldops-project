"""Fix customer extended profile constraints.

Revision ID: b7e3c1a9d542
Revises: 9f4c2d7e8a11
Create Date: 2026-09-29

Ensures that an existing customer_profiles_extended table has the
required uniqueness and foreign-key constraints expected by the
customer profile model and migration tests.

This migration is intentionally idempotent so it can safely handle
databases where the table already existed before the canonical
customer profile migration was introduced.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision: str = "b7e3c1a9d542"
down_revision: Union[str, Sequence[str], None] = "9f4c2d7e8a11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "customer_profiles_extended"

UNIQUE_CONSTRAINT_NAME = (
    "uq_customer_profiles_extended_user_id"
)

USER_FK_NAME = (
    "fk_customer_profiles_extended_user_id_users"
)

TENANT_FK_NAME = (
    "fk_customer_profiles_extended_tenant_id_organizations"
)


def _get_table_constraints(bind):
    inspector = inspect(bind)

    unique_constraints = inspector.get_unique_constraints(
        TABLE_NAME
    )

    foreign_keys = inspector.get_foreign_keys(
        TABLE_NAME
    )

    return unique_constraints, foreign_keys


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    existing_tables = set(inspector.get_table_names())

    if TABLE_NAME not in existing_tables:
        # The canonical table should normally already exist from
        # revision 9f4c2d7e8a11. This defensive branch allows the
        # migration to recover cleanly on a database where it does not.
        op.create_table(
            TABLE_NAME,
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
                "full_name",
                sa.String(length=200),
                nullable=False,
            ),
            sa.Column(
                "mobile_number",
                sa.String(length=20),
                nullable=False,
            ),
            sa.Column(
                "address",
                sa.Text(),
                nullable=True,
            ),
            sa.Column(
                "city",
                sa.String(length=100),
                nullable=True,
            ),
            sa.Column(
                "state",
                sa.String(length=100),
                nullable=True,
            ),
            sa.Column(
                "pincode",
                sa.String(length=10),
                nullable=True,
            ),
            sa.Column(
                "company_name",
                sa.String(length=200),
                nullable=True,
            ),
            sa.Column(
                "profile_completed",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.ForeignKeyConstraint(
                ["user_id"],
                ["users.id"],
                name=USER_FK_NAME,
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["tenant_id"],
                ["organizations.id"],
                name=TENANT_FK_NAME,
                ondelete="RESTRICT",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "user_id",
                name=UNIQUE_CONSTRAINT_NAME,
            ),
        )

        return

    # ------------------------------------------------------------
    # Refresh inspector after confirming the table exists
    # ------------------------------------------------------------

    inspector = inspect(bind)

    unique_constraints = inspector.get_unique_constraints(
        TABLE_NAME
    )

    foreign_keys = inspector.get_foreign_keys(
        TABLE_NAME
    )

    # ------------------------------------------------------------
    # 1. Ensure user_id uniqueness
    # ------------------------------------------------------------

    has_expected_unique = any(
        constraint.get("name") == UNIQUE_CONSTRAINT_NAME
        and constraint.get("column_names") == ["user_id"]
        for constraint in unique_constraints
    )

    has_user_unique = any(
        constraint.get("column_names") == ["user_id"]
        for constraint in unique_constraints
    )

    if not has_expected_unique and not has_user_unique:
        op.create_unique_constraint(
            UNIQUE_CONSTRAINT_NAME,
            TABLE_NAME,
            ["user_id"],
        )

    elif has_user_unique and not has_expected_unique:
        existing_constraint = next(
            constraint
            for constraint in unique_constraints
            if constraint.get("column_names") == ["user_id"]
        )

        existing_name = existing_constraint.get("name")

        if existing_name:
            op.execute(
                sa.text(
                    f'''
                    ALTER TABLE "{TABLE_NAME}"
                    RENAME CONSTRAINT "{existing_name}"
                    TO "{UNIQUE_CONSTRAINT_NAME}"
                    '''
                )
            )

    # ------------------------------------------------------------
    # 2. Ensure user_id -> users.id foreign key
    # ------------------------------------------------------------

    has_user_fk = any(
        fk.get("constrained_columns") == ["user_id"]
        and fk.get("referred_table") == "users"
        and fk.get("referred_columns") == ["id"]
        for fk in foreign_keys
    )

    if not has_user_fk:
        op.create_foreign_key(
            USER_FK_NAME,
            TABLE_NAME,
            "users",
            ["user_id"],
            ["id"],
            ondelete="CASCADE",
        )

    # ------------------------------------------------------------
    # 3. Ensure tenant_id -> organizations.id foreign key
    # ------------------------------------------------------------

    has_tenant_fk = any(
        fk.get("constrained_columns") == ["tenant_id"]
        and fk.get("referred_table") == "organizations"
        and fk.get("referred_columns") == ["id"]
        for fk in foreign_keys
    )

    if not has_tenant_fk:
        op.create_foreign_key(
            TENANT_FK_NAME,
            TABLE_NAME,
            "organizations",
            ["tenant_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    existing_tables = set(inspector.get_table_names())

    if TABLE_NAME not in existing_tables:
        return

    # ------------------------------------------------------------
    # Remove tenant foreign key
    # ------------------------------------------------------------

    foreign_keys = inspector.get_foreign_keys(
        TABLE_NAME
    )

    tenant_fk = next(
        (
            fk
            for fk in foreign_keys
            if fk.get("name") == TENANT_FK_NAME
        ),
        None,
    )

    if tenant_fk:
        op.drop_constraint(
            TENANT_FK_NAME,
            TABLE_NAME,
            type_="foreignkey",
        )

    # ------------------------------------------------------------
    # Remove user foreign key
    # ------------------------------------------------------------

    inspector = inspect(bind)

    foreign_keys = inspector.get_foreign_keys(
        TABLE_NAME
    )

    user_fk = next(
        (
            fk
            for fk in foreign_keys
            if fk.get("name") == USER_FK_NAME
        ),
        None,
    )

    if user_fk:
        op.drop_constraint(
            USER_FK_NAME,
            TABLE_NAME,
            type_="foreignkey",
        )

    # ------------------------------------------------------------
    # Remove named user uniqueness constraint
    # ------------------------------------------------------------

    inspector = inspect(bind)

    unique_constraints = inspector.get_unique_constraints(
        TABLE_NAME
    )

    expected_unique = next(
        (
            constraint
            for constraint in unique_constraints
            if constraint.get("name") == UNIQUE_CONSTRAINT_NAME
        ),
        None,
    )

    if expected_unique:
        op.drop_constraint(
            UNIQUE_CONSTRAINT_NAME,
            TABLE_NAME,
            type_="unique",
        )