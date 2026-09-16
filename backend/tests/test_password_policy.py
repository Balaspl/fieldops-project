"""
Regression tests for centralized password policy.

Password policy:
- Minimum 8 characters
- At least one uppercase letter
- At least one lowercase letter
- At least one digit
- At least one special character

These tests verify that the reusable validator behaves consistently
for all password-setting requirements.
"""

import pytest

from app.auth.password import (
    PasswordValidationError,
    hash_password,
    validate_password_strength,
    verify_password,
)


# ============================================================
# Weak password tests
# ============================================================


def test_weak_registration_password():
    """Weak password must be rejected for registration."""
    password = "password"

    with pytest.raises(PasswordValidationError):
        validate_password_strength(password)


def test_weak_reset_password():
    """Weak password must be rejected for password reset."""
    password = "Password"

    with pytest.raises(PasswordValidationError):
        validate_password_strength(password)


def test_weak_changed_password():
    """Weak password must be rejected for password change."""
    password = "Password1"

    with pytest.raises(PasswordValidationError):
        validate_password_strength(password)


# ============================================================
# Strong password
# ============================================================


def test_valid_strong_password():
    """A password satisfying every rule must be accepted."""
    password = "Strong@123"

    # Should not raise an exception.
    validate_password_strength(password)


# ============================================================
# Boundary length
# ============================================================


def test_boundary_length_password():
    """An 8-character password is the minimum valid length."""
    password = "Abcd@123"

    assert len(password) == 8

    # Should pass because it contains:
    # uppercase -> A
    # lowercase -> bcd
    # digit -> 123
    # special -> @
    validate_password_strength(password)


def test_below_boundary_length_password():
    """A 7-character password must be rejected."""
    password = "Abc@123"

    assert len(password) == 7

    with pytest.raises(PasswordValidationError):
        validate_password_strength(password)


# ============================================================
# Individual complexity rules
# ============================================================


@pytest.mark.parametrize(
    "password",
    [
        "abcdefg1@",       # missing uppercase
        "ABCDEFG1@",       # missing lowercase
        "Abcdefgh@",       # missing digit
        "Abcdefg1",        # missing special character
        "Ab1@",            # too short
    ],
)
def test_password_complexity_rules(password):
    """Each password violating a policy rule must be rejected."""
    with pytest.raises(PasswordValidationError):
        validate_password_strength(password)


# ============================================================
# Error safety
# ============================================================


def test_validation_error_does_not_expose_password():
    """Validation errors must not contain the submitted password."""
    password = "weakpassword123"

    with pytest.raises(PasswordValidationError) as exc_info:
        validate_password_strength(password)

    assert password not in str(exc_info.value)


# ============================================================
# Bcrypt hashing
# ============================================================


def test_password_is_hashed_with_bcrypt():
    """Passwords must be stored as bcrypt hashes, not plaintext."""
    password = "Strong@123"

    hashed_password = hash_password(password)

    assert hashed_password != password
    assert hashed_password.startswith("$2")

    assert verify_password(password, hashed_password) is True
    assert verify_password("Wrong@123", hashed_password) is False


def test_bcrypt_generates_different_hashes_for_same_password():
    """Bcrypt should generate a unique salted hash for each password."""
    password = "Strong@123"

    hash_one = hash_password(password)
    hash_two = hash_password(password)

    assert hash_one != hash_two

    assert verify_password(password, hash_one) is True
    assert verify_password(password, hash_two) is True

