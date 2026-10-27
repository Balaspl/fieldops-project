"""Offline re-encryption for DATA_ENCRYPTION_KEY rotation.

Run from the backend directory during the maintenance window documented in
docs/security/sensitive-data-at-rest.md. No key material or row values are printed.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import sqlalchemy as sa

from app.security.encrypted_fields import is_encrypted, reencrypt_at_rest
from app.secret import validate_secret


def _load_field_inventory() -> tuple[dict, dict]:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "7ac43d11bf20_encrypt_sensitive_personal_fields.py"
    )
    spec = importlib.util.spec_from_file_location("sensitive_fields_migration", migration_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Sensitive field inventory is unavailable")
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration.FIELDS, migration.PRIMARY_KEYS


def rotate_rows(connection, old_key: str, new_key: str) -> int:
    fields, primary_keys = _load_field_inventory()
    inspector = sa.inspect(connection)
    updated = 0
    for table_name, columns in fields.items():
        if not inspector.has_table(table_name):
            continue
        existing = {column["name"] for column in inspector.get_columns(table_name)}
        primary_key = primary_keys[table_name]
        if primary_key not in existing:
            continue
        for column_name, (context, searchable, _length) in columns.items():
            if column_name not in existing:
                continue
            table = sa.table(
                table_name,
                sa.column(primary_key),
                sa.column(column_name, sa.Text()),
            )
            rows = connection.execute(sa.select(table.c[primary_key], table.c[column_name]))
            for row_id, value in rows:
                if value is None:
                    continue
                if not is_encrypted(str(value)):
                    raise RuntimeError("Plaintext sensitive data remains; apply the backfill first")
                rotated = reencrypt_at_rest(
                    str(value),
                    context,
                    searchable=searchable,
                    old_key=old_key,
                    new_key=new_key,
                )
                connection.execute(
                    table.update()
                    .where(table.c[primary_key] == row_id)
                    .values({column_name: rotated})
                )
                updated += 1
    return updated


def main() -> None:
    database_url = os.getenv("DATABASE_URL", "").strip()
    old_key = os.getenv("DATA_ENCRYPTION_KEY", "").strip()
    new_key = os.getenv("NEW_DATA_ENCRYPTION_KEY", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL must be configured")
    validate_secret("DATA_ENCRYPTION_KEY", old_key, required=True, min_length=32, production=True)
    validate_secret("NEW_DATA_ENCRYPTION_KEY", new_key, required=True, min_length=32, production=True)
    if len(old_key.encode("utf-8")) < 32 or len(new_key.encode("utf-8")) < 32:
        raise RuntimeError("Both encryption keys must meet the minimum key length")
    if old_key == new_key:
        raise RuntimeError("The new encryption key must differ from the current key")

    engine = sa.create_engine(database_url, hide_parameters=True)
    with engine.begin() as connection:
        updated = rotate_rows(connection, old_key, new_key)
    engine.dispose()
    print(f"Re-encrypted {updated} sensitive field values.")


if __name__ == "__main__":
    main()
