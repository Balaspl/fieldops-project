"""
Tests for User account lockout behavior.

Run:
    pytest -q tests/test_account_lockout.py
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.user import User


# ============================================================
# Helpers
# ============================================================


def create_user(**overrides) -> User:
    """
    Create a User instance without requiring a database.

    Only fields required by the model constructor are supplied.
    """

    defaults = {
        "email": "test@example.com",
        "password_hash": "test-password-hash",
        "first_name": "Test",
        "last_name": "User",
        "role": "technician",
        "tenant_id": "tenant-1",
        "is_active": True,
        "is_email_verified": True,
        "is_on_duty": True,
        "failed_login_attempts": 0,
        "locked_until": None,
    }

    defaults.update(overrides)

    return User(**defaults)


# ============================================================
# Basic failed-login behavior
# ============================================================


def test_failed_login_increments_attempt_count(monkeypatch):
    """A failed login should increment the failure counter."""

    monkeypatch.setenv(
        "ACCOUNT_LOCKOUT_THRESHOLD",
        "5",
    )

    user = create_user()

    assert user.failed_login_attempts == 0
    assert user.is_locked is False

    newly_locked = user.record_failed_login()

    assert newly_locked is False
    assert user.failed_login_attempts == 1
    assert user.is_locked is False


def test_failed_login_increments_until_threshold(monkeypatch):
    """Attempts below the threshold should not lock the account."""

    monkeypatch.setenv(
        "ACCOUNT_LOCKOUT_THRESHOLD",
        "5",
    )

    user = create_user()

    for expected_attempt in range(1, 5):
        newly_locked = user.record_failed_login()

        assert newly_locked is False
        assert user.failed_login_attempts == expected_attempt
        assert user.is_locked is False


# ============================================================
# Lock threshold
# ============================================================


def test_account_locks_at_threshold(monkeypatch):
    """The account should lock exactly at the configured threshold."""

    monkeypatch.setenv(
        "ACCOUNT_LOCKOUT_THRESHOLD",
        "5",
    )

    monkeypatch.setenv(
        "ACCOUNT_LOCKOUT_DURATION_MINUTES",
        "15",
    )

    monkeypatch.setenv(
        "ACCOUNT_LOCKOUT_MIN_DURATION_MINUTES",
        "1",
    )

    monkeypatch.setenv(
        "ACCOUNT_LOCKOUT_MAX_DURATION_MINUTES",
        "60",
    )

    user = create_user()

    for _ in range(4):
        assert user.record_failed_login() is False

    assert user.failed_login_attempts == 4
    assert user.is_locked is False

    newly_locked = user.record_failed_login()

    assert newly_locked is True
    assert user.failed_login_attempts == 5
    assert user.locked_until is not None
    assert user.is_locked is True


def test_lockout_duration_is_applied(monkeypatch):
    """The configured lockout duration should be applied."""

    monkeypatch.setenv(
        "ACCOUNT_LOCKOUT_THRESHOLD",
        "3",
    )

    monkeypatch.setenv(
        "ACCOUNT_LOCKOUT_DURATION_MINUTES",
        "15",
    )

    monkeypatch.setenv(
        "ACCOUNT_LOCKOUT_MIN_DURATION_MINUTES",
        "1",
    )

    monkeypatch.setenv(
        "ACCOUNT_LOCKOUT_MAX_DURATION_MINUTES",
        "60",
    )

    before = datetime.now(timezone.utc)

    user = create_user()

    user.record_failed_login()
    user.record_failed_login()

    newly_locked = user.record_failed_login()

    after = datetime.now(timezone.utc)

    assert newly_locked is True
    assert user.locked_until is not None

    # Allow a small execution-time tolerance.
    expected_min = before + timedelta(minutes=15)
    expected_max = after + timedelta(minutes=15)

    if user.locked_until.tzinfo is None:
        locked_until = user.locked_until.replace(
            tzinfo=timezone.utc
        )
    else:
        locked_until = user.locked_until

    assert locked_until >= expected_min
    assert locked_until <= expected_max


# ============================================================
# Active lock behavior
# ============================================================


def test_locked_account_is_locked(monkeypatch):
    """An account with a future locked_until must be locked."""

    monkeypatch.setenv(
        "ACCOUNT_LOCKOUT_THRESHOLD",
        "5",
    )

    user = create_user(
        failed_login_attempts=5,
        locked_until=datetime.now(timezone.utc)
        + timedelta(minutes=15),
    )

    assert user.is_locked is True


def test_active_lock_is_not_extended(monkeypatch):
    """
    A failed login while already locked must not extend the
    existing lock duration.
    """

    monkeypatch.setenv(
        "ACCOUNT_LOCKOUT_THRESHOLD",
        "5",
    )

    original_lock = datetime.now(timezone.utc) + timedelta(
        minutes=10
    )

    user = create_user(
        failed_login_attempts=5,
        locked_until=original_lock,
    )

    result = user.record_failed_login()

    assert result is False
    assert user.failed_login_attempts == 5
    assert user.locked_until == original_lock
    assert user.is_locked is True


def test_active_lock_does_not_increment_failed_attempts(
    monkeypatch,
):
    """
    Additional attempts during an active lock should not modify
    the failure counter.
    """

    monkeypatch.setenv(
        "ACCOUNT_LOCKOUT_THRESHOLD",
        "5",
    )

    original_lock = datetime.now(timezone.utc) + timedelta(
        minutes=10
    )

    user = create_user(
        failed_login_attempts=5,
        locked_until=original_lock,
    )

    user.record_failed_login()

    assert user.failed_login_attempts == 5
    assert user.locked_until == original_lock


# ============================================================
# Lock expiry
# ============================================================


def test_expired_lock_is_not_active(monkeypatch):
    """An expired lock should no longer be considered active."""

    monkeypatch.setenv(
        "ACCOUNT_LOCKOUT_THRESHOLD",
        "5",
    )

    user = create_user(
        failed_login_attempts=5,
        locked_until=datetime.now(timezone.utc)
        - timedelta(minutes=1),
    )

    assert user.is_locked is False


def test_expired_lock_starts_new_failure_window(monkeypatch):
    """
    After a lock expires, the next failed login should start
    a fresh failure counter.
    """

    monkeypatch.setenv(
        "ACCOUNT_LOCKOUT_THRESHOLD",
        "5",
    )

    user = create_user(
        failed_login_attempts=5,
        locked_until=datetime.now(timezone.utc)
        - timedelta(minutes=1),
    )

    result = user.record_failed_login()

    assert result is False
    assert user.failed_login_attempts == 1
    assert user.locked_until is None
    assert user.is_locked is False


def test_expired_lock_is_cleared_before_counting_failure(
    monkeypatch,
):
    """An expired lock must be removed before counting the new failure."""

    monkeypatch.setenv(
        "ACCOUNT_LOCKOUT_THRESHOLD",
        "3",
    )

    user = create_user(
        failed_login_attempts=3,
        locked_until=datetime.now(timezone.utc)
        - timedelta(seconds=1),
    )

    user.record_failed_login()

    assert user.failed_login_attempts == 1
    assert user.locked_until is None


# ============================================================
# Successful login
# ============================================================


def test_successful_login_resets_failed_attempts(monkeypatch):
    """Successful authentication should reset the failure counter."""

    monkeypatch.setenv(
        "ACCOUNT_LOCKOUT_THRESHOLD",
        "5",
    )

    user = create_user(
        failed_login_attempts=4,
    )

    user.record_successful_login()

    assert user.failed_login_attempts == 0
    assert user.locked_until is None
    assert user.last_login is not None


def test_successful_login_clears_lock(monkeypatch):
    """Successful authentication should clear an existing lock."""

    monkeypatch.setenv(
        "ACCOUNT_LOCKOUT_THRESHOLD",
        "5",
    )

    user = create_user(
        failed_login_attempts=5,
        locked_until=datetime.now(timezone.utc)
        + timedelta(minutes=15),
    )

    user.record_successful_login()

    assert user.failed_login_attempts == 0
    assert user.locked_until is None
    assert user.is_locked is False
    assert user.last_login is not None


# ============================================================
# Configuration
# ============================================================


def test_custom_lockout_threshold(monkeypatch):
    """The lockout threshold should come from configuration."""

    monkeypatch.setenv(
        "ACCOUNT_LOCKOUT_THRESHOLD",
        "3",
    )

    monkeypatch.setenv(
        "ACCOUNT_LOCKOUT_DURATION_MINUTES",
        "15",
    )

    user = create_user()

    user.record_failed_login()
    assert user.is_locked is False

    user.record_failed_login()
    assert user.is_locked is False

    newly_locked = user.record_failed_login()

    assert newly_locked is True
    assert user.failed_login_attempts == 3
    assert user.is_locked is True


def test_invalid_lockout_threshold_is_rejected(monkeypatch):
    """A threshold below 1 should raise an error."""

    monkeypatch.setenv(
        "ACCOUNT_LOCKOUT_THRESHOLD",
        "0",
    )

    user = create_user()

    with pytest.raises(
        ValueError,
        match="ACCOUNT_LOCKOUT_THRESHOLD must be >= 1",
    ):
        user.record_failed_login()


def test_invalid_lockout_duration_is_rejected(monkeypatch):
    """A duration outside the configured bounds should fail."""

    monkeypatch.setenv(
        "ACCOUNT_LOCKOUT_THRESHOLD",
        "1",
    )

    monkeypatch.setenv(
        "ACCOUNT_LOCKOUT_DURATION_MINUTES",
        "120",
    )

    monkeypatch.setenv(
        "ACCOUNT_LOCKOUT_MIN_DURATION_MINUTES",
        "1",
    )

    monkeypatch.setenv(
        "ACCOUNT_LOCKOUT_MAX_DURATION_MINUTES",
        "60",
    )

    user = create_user()

    with pytest.raises(
        ValueError,
        match="ACCOUNT_LOCKOUT_DURATION_MINUTES",
    ):
        user.record_failed_login()


def test_invalid_duration_configuration_is_rejected(
    monkeypatch,
):
    """Invalid minimum/maximum duration configuration should fail."""

    monkeypatch.setenv(
        "ACCOUNT_LOCKOUT_THRESHOLD",
        "1",
    )

    monkeypatch.setenv(
        "ACCOUNT_LOCKOUT_DURATION_MINUTES",
        "15",
    )

    monkeypatch.setenv(
        "ACCOUNT_LOCKOUT_MIN_DURATION_MINUTES",
        "60",
    )

    monkeypatch.setenv(
        "ACCOUNT_LOCKOUT_MAX_DURATION_MINUTES",
        "30",
    )

    user = create_user()

    with pytest.raises(
        ValueError,
        match="MAX_DURATION_MINUTES",
    ):
        user.record_failed_login()


# ============================================================
# Consecutive failure behavior
# ============================================================


def test_successful_login_breaks_failure_sequence(
    monkeypatch,
):
    """
    A successful login should break the consecutive failure
    sequence.
    """

    monkeypatch.setenv(
        "ACCOUNT_LOCKOUT_THRESHOLD",
        "5",
    )

    user = create_user()

    user.record_failed_login()
    user.record_failed_login()
    user.record_failed_login()

    assert user.failed_login_attempts == 3

    user.record_successful_login()

    assert user.failed_login_attempts == 0
    assert user.is_locked is False

    user.record_failed_login()

    assert user.failed_login_attempts == 1
    assert user.is_locked is False


def test_multiple_lockout_cycles(monkeypatch):
    """
    The user should be able to enter a new lockout cycle after
    the previous lock has expired.
    """

    monkeypatch.setenv(
        "ACCOUNT_LOCKOUT_THRESHOLD",
        "2",
    )

    monkeypatch.setenv(
        "ACCOUNT_LOCKOUT_DURATION_MINUTES",
        "15",
    )

    # First lockout.
    user = create_user()

    assert user.record_failed_login() is False
    assert user.record_failed_login() is True

    assert user.failed_login_attempts == 2
    assert user.is_locked is True

    # Simulate lock expiry.
    user.locked_until = (
        datetime.now(timezone.utc)
        - timedelta(seconds=1)
    )

    # New failure window.
    assert user.record_failed_login() is False

    assert user.failed_login_attempts == 1
    assert user.is_locked is False

    # Second lockout.
    assert user.record_failed_login() is True

    assert user.failed_login_attempts == 2
    assert user.is_locked is True