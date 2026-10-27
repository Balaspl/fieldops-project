import pytest

from app.secret import is_production, validate_runtime_secrets, validate_secret

TEST_DATA_ENCRYPTION_KEY = "fieldops-test-only-data-encryption-key-not-for-production-2026"


def test_missing_required_jwt_secret_is_rejected():
    with pytest.raises(RuntimeError, match="JWT_SECRET must be explicitly configured"):
        validate_runtime_secrets({"APP_ENV": "development"})


def test_placeholder_secret_is_rejected():
    value = "change-me"
    with pytest.raises(RuntimeError, match="known placeholder") as error:
        validate_secret(
            "JWT_SECRET", value, required=True, production=True
        )
    assert value not in str(error.value)


def test_development_can_use_explicit_local_placeholder_value():
    assert validate_secret(
        "JWT_SECRET", "local-change-me-secret", required=True, production=False
    ) == "local-change-me-secret"


def test_production_requires_a_strong_jwt_secret():
    with pytest.raises(RuntimeError, match="minimum production length"):
        validate_runtime_secrets(
            {"APP_ENV": "production", "JWT_SECRET": "Jv8!qP2xR7#nL4$wT9@bC6^mF3&kH5*z"[:31]}
        )


def test_production_accepts_injected_jwt_and_rejects_placeholder_integrations():
    with pytest.raises(RuntimeError, match="known placeholder"):
        validate_runtime_secrets(
            {
                "APP_ENV": "production",
                "JWT_SECRET": "Jv8!qP2xR7#nL4$wT9@bC6^mF3&kH5*z",
                "DATA_ENCRYPTION_KEY": TEST_DATA_ENCRYPTION_KEY,
                "DATABASE_URL": "postgresql://operator:secure-value@db.example/fieldops",
                "GROQ_API_KEY": "your_api_key",
            }
        )


def test_production_requires_database_url():
    with pytest.raises(RuntimeError, match="DATABASE_URL must be configured"):
        validate_runtime_secrets(
            {
                "APP_ENV": "production",
                "JWT_SECRET": "Jv8!qP2xR7#nL4$wT9@bC6^mF3&kH5*z",
                "DATA_ENCRYPTION_KEY": TEST_DATA_ENCRYPTION_KEY,
            }
        )


def test_development_mode_allows_short_explicit_test_secret():
    assert validate_secret(
        "JWT_SECRET", "local-test-value", required=True, production=False
    ) == "local-test-value"


def test_environment_mode_is_explicitly_detected():
    assert is_production({"ENVIRONMENT": "production"})
    assert not is_production({"APP_ENV": "test"})
    assert not is_production({"ENV": "local"})
    assert is_production({"APP_ENV": "staging"})
    assert is_production({"APP_ENV": "prod", "ENV": "production"})


def test_unknown_environment_is_rejected():
    with pytest.raises(RuntimeError, match="Unsupported application environment"):
        is_production({"APP_ENV": "prodution"})


def test_conflicting_environment_settings_are_rejected():
    for env in (
        {"APP_ENV": "development", "ENV": "production"},
        {"APP_ENV": "dev", "ENVIRONMENT": "test"},
        {"APP_ENV": "staging", "ENV": "production"},
    ):
        with pytest.raises(RuntimeError, match="Conflicting application environment"):
            is_production(env)


def test_direct_secret_validation_still_rejects_environment_conflicts(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("ENV", "production")
    with pytest.raises(RuntimeError, match="Conflicting application environment"):
        validate_secret("JWT_SECRET", "private-value", production=True)


def test_production_database_url_rejects_placeholder_password_without_echoing_url():
    value = "postgresql://operator:password@db.example/fieldops"
    with pytest.raises(RuntimeError, match="known placeholder") as error:
        validate_secret("DATABASE_URL", value, production=True)
    assert value not in str(error.value)


@pytest.mark.parametrize(
    "value",
    [
        "not-a-url",
        "postgresql://db:bad-port/db",
        "postgresql://db.example/fieldops#fragment",
        "postgresql://db host/fieldops",
    ],
)
def test_malformed_database_url_is_rejected_without_echoing_value(value):
    with pytest.raises(RuntimeError, match="DATABASE_URL is malformed") as error:
        validate_secret("DATABASE_URL", value)
    assert value not in str(error.value)


def test_valid_sqlite_database_urls_remain_accepted():
    assert validate_secret("DATABASE_URL", "sqlite://") == "sqlite://"
    assert validate_secret("DATABASE_URL", "sqlite:///./local.db") == "sqlite:///./local.db"
    assert validate_secret("DATABASE_URL", "sqlite+pysqlite://") == "sqlite+pysqlite://"
    assert validate_secret("DATABASE_URL", "sqlite+pysqlite:///:memory:") == "sqlite+pysqlite:///:memory:"
    assert validate_secret("DATABASE_URL", "postgresql:///fieldops") == "postgresql:///fieldops"


@pytest.mark.parametrize(
    "value",
    [
        "postgresql://operator:private@db.example:5432/fieldops",
        "postgresql+psycopg2://operator:private@db.example/fieldops",
        "postgresql:///fieldops",
        "sqlite://",
        "sqlite:///./fieldops.db",
    ],
)
def test_supported_database_driver_urls_are_accepted(value):
    assert validate_secret("DATABASE_URL", value) == value


@pytest.mark.parametrize(
    "value",
    [
        "postgresql://db.example",
        "postgresql:///",
        "postgresql://operator@/fieldops",
        "postgresql+asyncpg://db.example/fieldops",
    ],
)
def test_incomplete_or_unsupported_database_urls_are_rejected(value):
    with pytest.raises(RuntimeError, match="DATABASE_URL") as error:
        validate_secret("DATABASE_URL", value)
    assert value not in str(error.value)


@pytest.mark.parametrize(
    "name,value",
    [
        ("REDIS_URL", "redis://localhost:6379/0"),
        ("REDIS_ASYNC_URL", "rediss://user:strong-pass@cache.example/2"),
        ("CELERY_BROKER_URL", "redis://localhost"),
    ],
)
def test_supported_redis_and_celery_urls_are_accepted(name, value):
    assert validate_secret(name, value) == value


@pytest.mark.parametrize(
    "name,value",
    [
        ("REDIS_URL", "http://cache.example:6379/0"),
        ("REDIS_ASYNC_URL", "redis://"),
        ("REDIS_URL", "redis://cache.example:bad-port/0"),
        ("CELERY_BROKER_URL", "redis://cache.example/not-a-db"),
        ("REDIS_URL", "redis://cache.example/0?db=invalid"),
        ("REDIS_URL", "redis://cache.example/0#fragment"),
    ],
)
def test_malformed_redis_and_celery_urls_are_rejected_without_echoing(name, value):
    with pytest.raises(RuntimeError, match=f"{name} is malformed") as error:
        validate_secret(name, value)
    assert value not in str(error.value)


def test_production_does_not_require_optional_integration_credentials():
    validate_runtime_secrets(
        {
            "APP_ENV": "production",
            "JWT_SECRET": "Jv8!qP2xR7#nL4$wT9@bC6^mF3&kH5*z",
            "DATA_ENCRYPTION_KEY": TEST_DATA_ENCRYPTION_KEY,
            "DATABASE_URL": "postgresql://operator:strong-db-password@db.example/fieldops",
        }
    )


def test_runtime_requires_external_data_encryption_key_in_development():
    with pytest.raises(RuntimeError, match="DATA_ENCRYPTION_KEY must be configured"):
        validate_runtime_secrets(
            {"APP_ENV": "development", "JWT_SECRET": "explicit-local-jwt-secret"}
        )


def test_runtime_rejects_short_data_encryption_key_in_development():
    with pytest.raises(RuntimeError, match="minimum key length"):
        validate_runtime_secrets(
            {
                "APP_ENV": "development",
                "JWT_SECRET": "explicit-local-jwt-secret",
                "DATA_ENCRYPTION_KEY": "too-short",
            }
        )
