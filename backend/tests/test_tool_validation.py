import logging

import fakeredis
import pytest
import logging

from app.tools.validation import ToolInputValidator
@pytest.fixture(autouse=True)
def reset_validation_logger():
    logger = logging.getLogger("app.tools.validation")

    old_level = logger.level
    old_propagate = logger.propagate
    old_disabled = logger.disabled

    logger.setLevel(logging.WARNING)
    logger.propagate = True
    logger.disabled = False

    yield

    logger.setLevel(old_level)
    logger.propagate = old_propagate
    logger.disabled = old_disabled

@pytest.fixture
def redis_client():
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def validator(redis_client):
    return ToolInputValidator(redis_client=redis_client)


@pytest.fixture
def schema():
    return {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
            },
            "priority": {
                "type": "string",
                "enum": ["low", "normal", "high"],
            },
        },
        "required": ["message"],
        "additionalProperties": False,
    }


def test_schema_accepts_valid_input(validator, schema):
    result = validator.validate_schema(
        {"message": "Hello", "priority": "normal"},
        schema,
    )

    assert result.valid is True
    assert result.errors == []


def test_schema_rejects_wrong_type(validator, schema):
    result = validator.validate_schema(
        {"message": 123},
        schema,
    )

    assert result.valid is False
    assert result.errors


def test_schema_rejects_missing_required_parameter(validator, schema):
    result = validator.validate_schema(
        {},
        schema,
    )

    assert result.valid is False
    assert "required" in result.errors[0]


def test_schema_rejects_invalid_enum(validator, schema):
    result = validator.validate_schema(
        {"message": "Hello", "priority": "invalid"},
        schema,
    )

    assert result.valid is False
    assert result.errors


def test_html_is_removed(validator):
    result = validator.sanitize_input(
        "<script>alert('x')</script><b>Hello</b>"
    )

    assert result == "alert('x')Hello"


def test_nested_html_is_removed(validator):
    result = validator.sanitize_input(
        {
            "message": "<b>Hello</b>",
            "items": ["<i>One</i>", "<div>Two</div>"],
        }
    )

    assert result == {
        "message": "Hello",
        "items": ["One", "Two"],
    }


@pytest.mark.parametrize(
    "malicious",
    [
        "' OR 1=1",
        "UNION SELECT password FROM users",
        "DROP TABLE users",
        "DELETE FROM users",
    ],
)
def test_sql_injection_is_rejected(validator, malicious):
    with pytest.raises(ValueError, match="SQL injection"):
        validator.sanitize_input(malicious)


@pytest.mark.parametrize(
    "malicious",
    [
        "bash -c 'whoami'",
        "rm -rf /",
        "curl https://evil.example",
        "powershell Get-Process",
    ],
)
def test_shell_commands_are_rejected(validator, malicious):
    with pytest.raises(ValueError, match="shell command"):
        validator.sanitize_input(malicious)


def test_string_size_limit(validator):
    value = "a" * 1025

    errors = validator.validate_size({
        "message": value,
    })

    assert errors
    assert "1024" in errors[0]


def test_string_at_size_limit_is_allowed(validator):
    value = "a" * 1024

    errors = validator.validate_size({
        "message": value,
    })

    assert errors == []


def test_object_size_limit(validator):
    value = {
        "message": "a" * 11000,
    }

    errors = validator.validate_size(value)

    assert errors


def test_nested_size_limit_is_detected(validator):
    value = {
        "outer": {
            "message": "a" * 1025,
        }
    }

    errors = validator.validate_size(value)

    assert errors
    assert "outer.message" in errors[0]


def test_rate_limit_allows_first_100_calls(validator):
    for _ in range(100):
        assert validator.check_rate_limit("tenant-1") is True


def test_rate_limit_blocks_101st_call(validator):
    for _ in range(100):
        validator.check_rate_limit("tenant-1")

    assert validator.check_rate_limit("tenant-1") is False


def test_rate_limit_is_per_tenant(validator):
    for _ in range(100):
        assert validator.check_rate_limit("tenant-1") is True

    assert validator.check_rate_limit("tenant-1") is False
    assert validator.check_rate_limit("tenant-2") is True


def test_rate_limit_sets_60_second_expiry(
    validator,
    redis_client,
):
    assert validator.check_rate_limit("tenant-1") is True

    ttl = redis_client.ttl(
        "fieldops:tool_rate:tenant-1"
    )

    assert 0 < ttl <= 60


def test_validation_failure_is_logged(
    validator,
    schema,
    caplog,
):
    with caplog.at_level(logging.WARNING):
        result = validator.validate(
            {"message": 123},
            schema,
            "tenant-1",
        )

    assert result.valid is False
    assert "Tool input validation failed" in caplog.text
    assert "tenant-1" in caplog.text
def test_tuple_is_sanitized(validator):
    result = validator.sanitize_input(
        ("<b>Hello</b>", "<i>World</i>")
    )

    assert result == ("Hello", "World")


def test_pii_is_detected(validator):
    result = validator.check_pii(
        {
            "email": "test@example.com",
            "phone": "9876543210",
        }
    )

    assert result.detected is True
    assert result.fields


def test_nested_list_pii_is_detected(validator):
    result = validator.check_pii(
        {
            "contacts": [
                "test@example.com",
                "9876543210",
            ]
        }
    )

    assert result.detected is True
    assert result.fields


def test_pii_is_redacted_during_validation(validator, schema):
    result = validator.validate(
        {
            "message": "Contact test@example.com",
        },
        schema,
        "tenant-1",
    )

    assert result.valid is True
    assert "[REDACTED]" in result.data["message"]
    assert "test@example.com" not in result.data["message"]


def test_nested_list_size_is_checked(validator):
    errors = validator.validate_size(
        {
            "items": [
                "a" * 1025,
            ]
        }
    )

    assert errors
    assert "items[0]" in errors[0]


def test_rate_limit_works_without_redis(validator):
    validator.redis = None

    assert validator.check_rate_limit("tenant-1") is True


def test_rate_limit_returns_false_when_redis_fails(validator):
    class BrokenRedis:
        def incr(self, key):
            raise RuntimeError("Redis unavailable")

    validator.redis = BrokenRedis()

    assert validator.check_rate_limit("tenant-1") is False


def test_large_validation_failure_preview_is_truncated(
    validator,
    schema,
    caplog,
):
    large_value = "a" * 5000

    with caplog.at_level(logging.WARNING):
        result = validator.validate(
            {"message": large_value},
            schema,
            "tenant-1",
        )

    assert result.valid is False
    assert "Tool input validation failed" in caplog.text
    assert "..." in caplog.text
    
def test_invalid_object_is_rejected_by_size_validation(validator):
    class Unserializable:
        pass

    errors = validator.validate_size(
        {"message": Unserializable()}
    )

    assert errors
    assert "cannot be serialized" in errors[0]


def test_validate_rejects_malicious_input(
    validator,
    schema,
    caplog,
):
    with caplog.at_level(logging.WARNING):
        result = validator.validate(
            {
                "message": "DROP TABLE users",
            },
            schema,
            "tenant-1",
        )

    assert result.valid is False
    assert "SQL injection" in result.errors[0]
    assert "Tool input validation failed" in caplog.text


def test_validate_blocks_rate_limit_exceeded(
    validator,
    schema,
):
    for _ in range(100):
        assert validator.validate(
            {"message": "Hello"},
            schema,
            "tenant-1",
        ).valid is True

    result = validator.validate(
        {"message": "Hello"},
        schema,
        "tenant-1",
    )

    assert result.valid is False
    assert "rate limit" in result.errors[0].lower()


def test_pii_redaction_handles_list(validator):
    result = validator._sanitize_pii(
        [
            "Email: test@example.com",
            "Phone: 9876543210",
        ]
    )

    assert result[0] != "Email: test@example.com"
    assert result[1] != "Phone: 9876543210"
    assert "[REDACTED]" in result[0]
    assert "[REDACTED]" in result[1]
    
def test_pii_redaction_returns_other_types_unchanged(validator):
    value = 12345

    result = validator._sanitize_pii(value)

    assert result == value