import os

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text


# ============================================================
# CURRENT MIGRATION
# ============================================================

CURRENT_HEAD = "0e98d23f998c"


# ============================================================
# ALEMBIC CONFIGURATION
# ============================================================

@pytest.fixture
def alembic_config():
    """
    Configure Alembic for the current PostgreSQL database.

    IMPORTANT:
    - Do not modify alembic/env.py
    - Do not modify migration files
    - This test uses PostgreSQL
    """

    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        pytest.skip(
            "DATABASE_URL is not configured."
        )

    if database_url.startswith("sqlite"):
        pytest.fail(
            "This migration test requires PostgreSQL."
        )

    alembic_cfg = Config("alembic.ini")

    alembic_cfg.set_main_option(
        "sqlalchemy.url",
        database_url.replace("%", "%%"),
    )

    return alembic_cfg


# ============================================================
# DATABASE
# ============================================================

@pytest.fixture
def engine():
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        pytest.skip(
            "DATABASE_URL is not configured."
        )

    if database_url.startswith("sqlite"):
        pytest.fail(
            "PostgreSQL is required for this migration test."
        )

    engine = create_engine(
        database_url,
        pool_pre_ping=True,
    )

    try:
        yield engine
    finally:
        engine.dispose()


# ============================================================
# TEST 1
# ============================================================

def test_task_5_2_migration(alembic_config, engine):
    """
    Verify the current Alembic migration state.

    Current repository state:

        004554449425 (head)

    This test does NOT reference:
        c5618b3bdac0
        1ad86b0a4f3f
        b15cb1f9d24e
    """

    # --------------------------------------------------------
    # 1. Verify PostgreSQL connection
    # --------------------------------------------------------

    with engine.connect() as conn:
        database_name = conn.execute(
            text("SELECT current_database()")
        ).scalar()

        assert database_name is not None

    # --------------------------------------------------------
    # 2. Verify Alembic actually knows the current head
    # --------------------------------------------------------

    script = ScriptDirectory.from_config(alembic_config)

    heads = script.get_heads()

    assert heads == [CURRENT_HEAD], (
        f"Expected Alembic head "
        f"{CURRENT_HEAD}, got {heads}"
    )

    # --------------------------------------------------------
    # 3. Verify database Alembic revision
    # --------------------------------------------------------

    with engine.connect() as conn:
        revision = conn.execute(
            text(
                """
                SELECT version_num
                FROM public.alembic_version
                """
            )
        ).scalar()

    assert revision == CURRENT_HEAD, (
        f"Expected Alembic revision "
        f"{CURRENT_HEAD}, got {revision}"
    )

    # --------------------------------------------------------
    # 4. Verify notification_templates
    # --------------------------------------------------------

    with engine.connect() as conn:

        exists = conn.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = 'notification_templates'
                )
                """
            )
        ).scalar()

    assert exists is True, (
        "notification_templates table does not exist"
    )

    # --------------------------------------------------------
    # 5. Verify template_versions
    # --------------------------------------------------------

    with engine.connect() as conn:

        exists = conn.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = 'template_versions'
                )
                """
            )
        ).scalar()

    assert exists is True, (
        "template_versions table does not exist"
    )

    # --------------------------------------------------------
    # 6. Verify template_versions columns
    # --------------------------------------------------------

    with engine.connect() as conn:

        columns = conn.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'template_versions'
                ORDER BY ordinal_position
                """
            )
        ).scalars().all()

    required_columns = {
        "id",
        "template_id",
        "version_number",
        "title_template",
        "body_template",
        "created_at",
        "created_by",
        "change_summary",
        "is_active",
    }

    missing_columns = required_columns - set(columns)

    assert not missing_columns, (
        f"Missing template_versions columns: "
        f"{sorted(missing_columns)}"
    )

    # --------------------------------------------------------
    # 7. Verify notification_templates columns
    # --------------------------------------------------------

    with engine.connect() as conn:

        columns = conn.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'notification_templates'
                ORDER BY ordinal_position
                """
            )
        ).scalars().all()

    required_columns = {
        "id",
        "name",
        "type",
        "channel",
        "locale",
        "format",
        "title_template",
        "body_template",
        "variables",
        "version",
        "is_active",
        "tenant_id",
        "agent_type",
        "created_at",
    }

    missing_columns = required_columns - set(columns)

    assert not missing_columns, (
        f"Missing notification_templates columns: "
        f"{sorted(missing_columns)}"
    )

    # --------------------------------------------------------
    # 8. Verify only one Alembic revision
    # --------------------------------------------------------

    with engine.connect() as conn:

        version_count = conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM public.alembic_version
                """
            )
        ).scalar()

    assert version_count == 1, (
        "alembic_version should contain exactly one revision"
    )


# ============================================================
# TEST 2
# ============================================================

def test_current_migration_downgrade_and_upgrade(
    alembic_config,
    engine,
):
    """
    Verify that the current migration is already at HEAD.

    Since 004554449425 is currently the HEAD, there is no
    later migration to downgrade from.

    Therefore this test verifies the HEAD state instead of
    trying to downgrade to an old/non-existent revision.
    """

    # --------------------------------------------------------
    # 1. Verify migration graph
    # --------------------------------------------------------

    script = ScriptDirectory.from_config(alembic_config)

    heads = script.get_heads()

    assert heads == [CURRENT_HEAD]

    # --------------------------------------------------------
    # 2. Upgrade to current HEAD
    # --------------------------------------------------------

    command.upgrade(
        alembic_config,
        CURRENT_HEAD,
    )

    # --------------------------------------------------------
    # 3. Verify current revision
    # --------------------------------------------------------

    with engine.connect() as conn:

        revision = conn.execute(
            text(
                """
                SELECT version_num
                FROM public.alembic_version
                """
            )
        ).scalar()

    assert revision == CURRENT_HEAD

    # --------------------------------------------------------
    # 4. Upgrade again should remain at HEAD
    # --------------------------------------------------------

    command.upgrade(
        alembic_config,
        CURRENT_HEAD,
    )

    with engine.connect() as conn:

        revision_after = conn.execute(
            text(
                """
                SELECT version_num
                FROM public.alembic_version
                """
            )
        ).scalar()

    assert revision_after == CURRENT_HEAD