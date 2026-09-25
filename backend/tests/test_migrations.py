import os

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text


# ============================================================
# ALEMBIC HELPERS
# ============================================================

def get_current_alembic_heads(alembic_config):
    """
    Return the current Alembic migration heads from the
    repository migration graph.

    This is intentionally dynamic so that when a new migration
    becomes the latest HEAD, these tests do not need to be
    manually updated with the new revision ID.
    """
    script = ScriptDirectory.from_config(alembic_config)
    return sorted(script.get_heads())


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

    The expected migration HEAD is obtained dynamically from
    the Alembic migration graph, so this test does not need
    to be changed whenever a new migration becomes HEAD.

    This test verifies that:

    1. PostgreSQL is reachable.
    2. Alembic has a valid current HEAD.
    3. The database is at that HEAD.
    4. notification_templates exists.
    5. template_versions exists.
    6. Required template_versions columns exist.
    7. Required notification_templates columns exist.
    8. Only one Alembic revision is present.
    """

    # --------------------------------------------------------
    # 1. Verify PostgreSQL connection
    # --------------------------------------------------------

    with engine.connect() as conn:
        database_name = conn.execute(
            text("SELECT current_database()")
        ).scalar()

    assert database_name is not None, (
        "Unable to determine PostgreSQL database name"
    )

    # --------------------------------------------------------
    # 2. Determine current Alembic HEAD dynamically
    # --------------------------------------------------------

    expected_heads = get_current_alembic_heads(
        alembic_config
    )

    assert expected_heads, (
        "No Alembic HEAD found in the migration graph"
    )

    # --------------------------------------------------------
    # 3. Verify Alembic migration graph
    # --------------------------------------------------------

    script = ScriptDirectory.from_config(
        alembic_config
    )

    heads = sorted(script.get_heads())

    assert heads == expected_heads, (
        f"Expected Alembic heads "
        f"{expected_heads}, got {heads}"
    )

    # This project expects a single migration head.
    assert len(expected_heads) == 1, (
        f"Expected exactly one Alembic HEAD, "
        f"got {expected_heads}"
    )

    current_head = expected_heads[0]

    # --------------------------------------------------------
    # 4. Verify database Alembic revision
    # --------------------------------------------------------

    with engine.connect() as conn:
        revisions = conn.execute(
            text(
                """
                SELECT version_num
                FROM public.alembic_version
                """
            )
        ).scalars().all()

    assert len(revisions) == 1, (
        "Expected exactly one Alembic revision in "
        "public.alembic_version"
    )

    revision = revisions[0]

    assert revision == current_head, (
        f"Expected database Alembic revision "
        f"{current_head}, got {revision}"
    )

    # --------------------------------------------------------
    # 5. Verify notification_templates table
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
    # 6. Verify template_versions table
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
    # 7. Verify template_versions columns
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
        "Missing template_versions columns: "
        f"{sorted(missing_columns)}"
    )

    # --------------------------------------------------------
    # 8. Verify notification_templates columns
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
        "Missing notification_templates columns: "
        f"{sorted(missing_columns)}"
    )

    # --------------------------------------------------------
    # 9. Verify only one Alembic revision
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
    Verify that the database can be upgraded to the current
    Alembic HEAD and that a second upgrade is idempotent.

    The migration HEAD is discovered dynamically, so this
    test does not need to be modified when a new migration
    becomes HEAD.
    """

    # --------------------------------------------------------
    # 1. Determine current Alembic HEAD dynamically
    # --------------------------------------------------------

    expected_heads = get_current_alembic_heads(
        alembic_config
    )

    assert expected_heads, (
        "No Alembic HEAD found in the migration graph"
    )

    # This project expects a single HEAD.
    assert len(expected_heads) == 1, (
        f"Expected exactly one Alembic HEAD, "
        f"got {expected_heads}"
    )

    current_head = expected_heads[0]

    # --------------------------------------------------------
    # 2. Verify migration graph
    # --------------------------------------------------------

    script = ScriptDirectory.from_config(
        alembic_config
    )

    heads = sorted(script.get_heads())

    assert heads == expected_heads, (
        f"Expected Alembic heads "
        f"{expected_heads}, got {heads}"
    )

    # --------------------------------------------------------
    # 3. Upgrade database to current HEAD
    # --------------------------------------------------------

    command.upgrade(
        alembic_config,
        "head",
    )

    # --------------------------------------------------------
    # 4. Verify database is at current HEAD
    # --------------------------------------------------------

    with engine.connect() as conn:
        revisions = conn.execute(
            text(
                """
                SELECT version_num
                FROM public.alembic_version
                """
            )
        ).scalars().all()

    assert len(revisions) == 1, (
        "Expected exactly one Alembic revision after upgrade"
    )

    revision = revisions[0]

    assert revision == current_head, (
        f"Expected Alembic revision "
        f"{current_head}, got {revision}"
    )

    # --------------------------------------------------------
    # 5. Upgrade again - must remain idempotent
    # --------------------------------------------------------

    command.upgrade(
        alembic_config,
        "head",
    )

    # --------------------------------------------------------
    # 6. Verify revision remains unchanged
    # --------------------------------------------------------

    with engine.connect() as conn:
        revisions_after = conn.execute(
            text(
                """
                SELECT version_num
                FROM public.alembic_version
                """
            )
        ).scalars().all()

    assert len(revisions_after) == 1, (
        "Expected exactly one Alembic revision after "
        "second upgrade"
    )

    revision_after = revisions_after[0]

    assert revision_after == current_head, (
        f"Expected Alembic revision "
        f"{current_head} after second upgrade, "
        f"got {revision_after}"
    )