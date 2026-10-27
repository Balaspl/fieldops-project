"""Shared validation for secrets supplied by the deployment environment.

This module never generates or supplies secret values. Callers should pass
secret material from an external secret store or environment injection.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from urllib.parse import parse_qs, unquote, urlsplit


PLACEHOLDER_VALUES = frozenset(
    {
        "changeme",
        "change-me",
        "change_me",
        "default",
        "development",
        "dev-secret",
        "dummy",
        "example",
        "password",
        "secret",
        "test",
        "your-secret-here",
        "your_api_key",
        "your_secret",
        "jwt-secret",
        "jwt_secret",
        "secretkey",
        "secret_key",
        "supersecret",
        "testsecret",
        "test_secret",
        "test-jwt-secret",
        "password123",
        "123456",
        "1234567890",
    }
)

SECRET_ENV_NAMES = frozenset(
    {
        "JWT_SECRET",
        "MFA_ENCRYPTION_KEY",
        "DATA_ENCRYPTION_KEY",
        "DATABASE_URL",
        "REDIS_URL",
        "REDIS_ASYNC_URL",
        "CELERY_BROKER_URL",
        "GROQ_API_KEY",
        "TWILIO_ACCOUNT_SID",
        "TWILIO_AUTH_TOKEN",
        "SMTP_PASSWORD",
        "OIDC_CLIENT_SECRET",
        "GOOGLE_MAPS_API_KEY",
        "OLA_MAPS_API_KEY",
        "KAFKA_SASL_PASSWORD",
        "KAFKA_PRODUCER_PASSWORD",
        "KAFKA_DISPATCH_PASSWORD",
        "KAFKA_GPS_PASSWORD",
        "KAFKA_SLA_PASSWORD",
        "KAFKA_NOTIFICATIONS_PASSWORD",
        "KAFKA_BILLING_PASSWORD",
        "KAFKA_PAYMENT_PASSWORD",
        "KAFKA_AUDIT_PASSWORD",
        "KAFKA_ANALYTICS_PASSWORD",
        "KAFKA_MONITOR_PASSWORD",
    }
)

_DATABASE_URL_SCHEMES = frozenset(
    {
        "postgresql",
        "postgresql+psycopg2",
        "sqlite",
        "sqlite+pysqlite",
    }
)
_BROKER_URL_SCHEMES = frozenset({"redis", "rediss"})


def _validate_database_url(value: str) -> str | None:
    """Validate configured SQLAlchemy URLs without exposing their contents."""
    if any(character.isspace() for character in value):
        raise RuntimeError("DATABASE_URL is malformed")
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError:
        raise RuntimeError("DATABASE_URL is malformed") from None

    if parsed.scheme not in _DATABASE_URL_SCHEMES:
        raise RuntimeError("DATABASE_URL is malformed")
    if parsed.fragment:
        raise RuntimeError("DATABASE_URL is malformed")

    if parsed.scheme.startswith("sqlite"):
        # SQLAlchemy's sqlite:// form is a supported in-memory database URL.
        if parsed.netloc:
            raise RuntimeError("DATABASE_URL is malformed")
        if parsed.path == "/":
            raise RuntimeError("DATABASE_URL is incomplete")
        return None

    database_name = parsed.path.lstrip("/")
    if not database_name or "/" in database_name:
        raise RuntimeError("DATABASE_URL is incomplete")
    if parsed.netloc and not parsed.hostname:
        raise RuntimeError("DATABASE_URL is malformed")
    return parsed.password


def _validate_broker_url(name: str, value: str) -> str | None:
    """Validate Redis URLs accepted by the project's Redis and Celery clients."""
    if any(character.isspace() for character in value):
        raise RuntimeError(f"{name} is malformed")
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError:
        raise RuntimeError(f"{name} is malformed") from None

    if (
        parsed.scheme not in _BROKER_URL_SCHEMES
        or not parsed.hostname
        or parsed.fragment
    ):
        raise RuntimeError(f"{name} is malformed")
    if parsed.path and not re.fullmatch(r"/\d+", parsed.path):
        raise RuntimeError(f"{name} is malformed")
    query_db = parse_qs(parsed.query).get("db", [])
    if query_db and any(not database_id.isdigit() for database_id in query_db):
        raise RuntimeError(f"{name} is malformed")
    return parsed.password


def is_production(env: Mapping[str, str] | None = None) -> bool:
    """Return production mode and reject unknown environment names."""
    source = os.environ if env is None else env
    configured_values = [
        source[name].strip().lower()
        for name in ("APP_ENV", "ENVIRONMENT", "ENV")
        if source.get(name)
    ]
    if not configured_values:
        configured_values = ["development"]

    environment_modes: set[str] = set()
    for value in configured_values:
        if value in {"prod", "production"}:
            environment_modes.add("production")
        elif value in {"stage", "staging"}:
            environment_modes.add("staging")
        elif value in {"dev", "development", "local"}:
            environment_modes.add("development")
        elif value in {"test", "testing"}:
            environment_modes.add("test")
        else:
            raise RuntimeError("Unsupported application environment configuration")

    if len(environment_modes) != 1:
        raise RuntimeError("Conflicting application environment configuration")
    return environment_modes.pop() in {"production", "staging"}


def validate_secret(
    name: str,
    value: str | None,
    *,
    required: bool = False,
    min_length: int = 0,
    production: bool | None = None,
) -> str | None:
    """Validate one externally supplied value without echoing it in errors."""
    environment_production = is_production()
    prod = environment_production if production is None else production
    normalized = value.strip() if isinstance(value, str) else ""
    if not normalized:
        if required:
            if name == "JWT_SECRET":
                raise RuntimeError("JWT_SECRET must be explicitly configured")
            raise RuntimeError(f"{name} must be configured through the environment")
        return None

    normalized_lower = normalized.casefold()
    placeholder = normalized_lower in PLACEHOLDER_VALUES or any(
        marker in normalized_lower
        for marker in (
            "change-me",
            "change_me",
            "changeme",
            "dummy",
            "placeholder",
            "replace-me",
            "replace_me",
            "your_",
        )
    )
    if name == "DATABASE_URL":
        url_password = _validate_database_url(normalized)
        decoded_password = unquote(url_password or "").casefold()
        if decoded_password in PLACEHOLDER_VALUES:
            placeholder = True
    elif name in {"REDIS_URL", "REDIS_ASYNC_URL", "CELERY_BROKER_URL"}:
        url_password = _validate_broker_url(name, normalized)
        decoded_password = unquote(url_password or "").casefold()
        if decoded_password in PLACEHOLDER_VALUES:
            placeholder = True
    if len(normalized) >= 32 and re.fullmatch(r"(.)\1+", normalized):
        placeholder = True
    if prod and placeholder:
        raise RuntimeError(f"{name} contains a known placeholder value")
    if prod and len(normalized) < min_length:
        raise RuntimeError(f"{name} does not meet the minimum production length")
    return normalized


def validate_runtime_secrets(
    env: Mapping[str, str] | None = None,
) -> None:
    """Fail startup for unsafe configured secrets and production JWT settings."""
    source = os.environ if env is None else env
    prod = is_production(source)
    validate_secret(
        "JWT_SECRET",
        source.get("JWT_SECRET"),
        required=True,
        min_length=32 if prod else 0,
        production=prod,
    )
    validate_secret(
        "DATABASE_URL",
        source.get("DATABASE_URL"),
        required=prod,
        production=prod,
    )
    data_encryption_key = validate_secret(
        "DATA_ENCRYPTION_KEY",
        source.get("DATA_ENCRYPTION_KEY"),
        required=True,
        min_length=32,
        production=prod,
    )
    if data_encryption_key is not None and len(data_encryption_key.encode("utf-8")) < 32:
        raise RuntimeError("DATA_ENCRYPTION_KEY does not meet the minimum key length")
    for name in SECRET_ENV_NAMES - {"JWT_SECRET", "DATABASE_URL"}:
        value = source.get(name)
        if value:
            validate_secret(name, value, production=prod)
