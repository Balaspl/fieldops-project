from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from sqlalchemy.engine import make_url
import os
from pathlib import Path
from dotenv import load_dotenv
from alembic import context
import re

# ============================================================
# Alembic Config
# ============================================================

config = context.config

if config.config_file_name is not None:
    fileConfig(
        config.config_file_name,
        disable_existing_loggers=False,
    )

# ============================================================
# GPS / Manually Managed Tables
# ============================================================

GPS_PARTITION_PATTERN = re.compile(
    r"^gps_pings_\d{4}_\d{2}$"
)

IGNORED_TABLES = {
    "redispatch_attempts",
    "gps_pings",
    "alembic_version",
}


def is_ignored_table(table_name: str | None) -> bool:
    if not table_name:
        return False

    return (
        table_name in IGNORED_TABLES
        or GPS_PARTITION_PATTERN.fullmatch(table_name) is not None
    )


def include_name(
    name: str | None,
    type_: str,
    parent_names: dict,
) -> bool:

    if type_ == "table" and is_ignored_table(name):
        return False

    return True


def include_object(
    obj,
    name: str | None,
    type_: str,
    reflected: bool,
    compare_to,
) -> bool:

    if type_ == "table":
        table_name = name
    else:
        table = getattr(obj, "table", None)
        table_name = getattr(table, "name", None)

    if is_ignored_table(table_name):
        return False

    return True


# ============================================================
# Environment
# ============================================================

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)


# IMPORTANT:
# Do NOT blindly overwrite sqlalchemy.url.
#
# Tests can call:
#
# alembic_cfg.set_main_option("sqlalchemy.url", sqlite_url)
#
# That SQLite URL must remain intact.
#
configured_url = config.get_main_option("sqlalchemy.url")

if not configured_url:
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is not configured."
        )

    config.set_main_option(
        "sqlalchemy.url",
        database_url.replace("%", "%%"),
    )


# ============================================================
# SQLAlchemy Models
# ============================================================

from app.models import Base

target_metadata = Base.metadata


# ============================================================
# Determine Database Dialect
# ============================================================

def get_database_url():
    return config.get_main_option("sqlalchemy.url")


def get_dialect_name() -> str:
    url = make_url(get_database_url())
    return url.get_backend_name()


def get_version_table_schema():
    """
    PostgreSQL supports schemas such as `public`.

    SQLite does NOT support PostgreSQL-style schemas.

    Therefore:
        PostgreSQL -> public
        SQLite     -> None
    """

    dialect = get_dialect_name()

    if dialect == "postgresql":
        return "public"

    return None


# ============================================================
# Alembic Configuration
# ============================================================

def configure_context_common():
    """
    Common Alembic options.
    """

    return {
        "target_metadata": target_metadata,
        "include_name": include_name,
        "include_object": include_object,
        "compare_type": True,
    }


# ============================================================
# Offline Migration
# ============================================================

def run_migrations_offline() -> None:

    url = config.get_main_option("sqlalchemy.url")

    options = configure_context_common()

    version_schema = get_version_table_schema()

    if version_schema is not None:
        options["version_table_schema"] = version_schema

    context.configure(
        url=url,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **options,
    )

    with context.begin_transaction():
        context.run_migrations()


# ============================================================
# Online Migration
# ============================================================

def run_migrations_online() -> None:

    connectable = engine_from_config(
        config.get_section(
            config.config_ini_section,
            {},
        ),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:

        options = configure_context_common()

        version_schema = get_version_table_schema()

        if version_schema is not None:
            options["version_table_schema"] = version_schema

        context.configure(
            connection=connection,
            **options,
        )

        with context.begin_transaction():
            context.run_migrations()


# ============================================================
# Run
# ============================================================

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()