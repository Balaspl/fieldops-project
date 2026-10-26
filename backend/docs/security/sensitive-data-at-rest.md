# Sensitive data at rest

## Classification and protection

| Data | Classification | Protection and query behavior |
| --- | --- | --- |
| User password hashes, refresh token hashes, password reset hashes, recovery code hashes, trusted-device token hashes | Authentication secrets | One-way hashes; raw values are not persisted. |
| MFA TOTP seed | Authentication secret | Fernet encryption using the separate externally managed `MFA_ENCRYPTION_KEY`. |
| User email and phone; technician phone; organization contact email and phone | Personal/contact data | Deterministic authenticated encryption, so existing exact-equality lookups and uniqueness checks continue to work. This reveals equality of repeated values. |
| User names and FCM tokens; customer and technician profile text/photo; organization address; captured customer signature | Personal, location, or biometric-like data | Randomized authenticated encryption; ORM reads decrypt these fields after loading an authorized row. |
| User lockout counters, timestamps, role, and tenant identifiers | Operational/auth metadata | Retained as structured values for authentication and tenant queries; these are not credentials. |
| Technician name/location and job customer name, location, contact details, issue description, and site address | Operational personal data | Remain searchable plaintext because current workflows use substring searches, filtering, scheduling, and dispatch. Limit database access and enable managed database/storage encryption. A future searchable-encryption design requires blind indexes or search tokens and corresponding query changes. |
| Technician date of birth and GPS coordinates | Structured personal/location data | Retain native date/numeric representation for existing typed workflows; protect with managed database/storage encryption and strict access controls. |

The field-level component uses independent HKDF-derived AES-256-GCM (randomized fields) and AES-256-SIV (exact-match fields) keys. Associated data binds ciphertext to its model field. Ciphertext has a version prefix; tampering, wrong keys, and missing keys fail closed without including values in errors. Existing plaintext rows remain readable during the migration window, and the Alembic backfill converts the covered fields. Keep application logs free of these fields and never log ciphertext as a substitute for redaction.

## Key setup and migration

Inject `DATA_ENCRYPTION_KEY` from the deployment secret manager into every backend and migration process. Generate 32 random bytes and encode them as URL-safe base64, for example with Python's `secrets.token_bytes(32)` and `base64.urlsafe_b64encode(...)`. Do not commit the generated value or store it in the database. Keep `MFA_ENCRYPTION_KEY` separate.

Before deployment, take and verify a database backup, inject the key, and apply Alembic revision `7ac43d11bf20` while application writers are stopped. The migration expands PostgreSQL varchar columns to text, encrypts existing covered values, and is idempotent for already-encrypted fields. SQLite does not enforce varchar length limits and needs no table rebuild. Do not start application instances without the same key. Missing/wrong keys prevent decryption; restore the matching key from the secret manager's recovery mechanism before restoring database access.

## Rotation

The current ciphertext format has one active key and no key identifiers. Rotation requires a controlled maintenance window: back up the database, stop application writers, inject the current key as `DATA_ENCRYPTION_KEY` and the new key as `NEW_DATA_ENCRYPTION_KEY` into the one-off maintenance process, then run `python scripts/rotate_data_encryption_key.py` from `backend`. The tool reads the field inventory used by the Alembic backfill, checks that every covered non-null value is encrypted, and re-encrypts it in one database transaction without printing keys or row values. After success, replace the deployment's `DATA_ENCRYPTION_KEY` with the new value, restart all application instances, and verify representative profile reads and exact-match lookups before resuming writers. Preserve the old key in the secret manager until verification and backup-retention requirements are met. Do not simply replace the key: existing rows would become unreadable. Key-ID overlap rotation is a future enhancement for zero-downtime rotation.

## Limitations

Deterministic encryption leaks equality. Fields needed for `ILIKE`/substring search or native date/numeric filtering are not field-encrypted in this change; they remain covered by managed disk/database encryption and authorization. The signature service and existing tenant/role checks continue to gate access before decrypted signature data is returned. Review these classifications before adding new fields or query patterns.
