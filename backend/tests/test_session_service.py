import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.auth.session_service import (
    create_session,
    delete_session,
    get_session,
    touch_session,
    validate_session,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_session(
    user_id="user-1",
    tenant_id="tenant-1",
    last_activity=None,
    max_expires_at=None,
):
    now = datetime.now(timezone.utc)

    if last_activity is None:
        last_activity = now

    if max_expires_at is None:
        max_expires_at = now + timedelta(hours=8)

    return {
        "session_id": "session-123",
        "user_id": user_id,
        "tenant_id": tenant_id,
        "created_at": now.isoformat(),
        "last_activity": last_activity.isoformat(),
        "max_expires_at": max_expires_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# create_session
# ---------------------------------------------------------------------------

@patch("app.auth.session_service.get_redis_client")
def test_create_session(mock_get_redis):
    redis = MagicMock()
    mock_get_redis.return_value = redis

    session = create_session(
        user_id="user-1",
        tenant_id="tenant-1",
    )

    assert session["session_id"]
    assert session["user_id"] == "user-1"
    assert session["tenant_id"] == "tenant-1"
    assert session["created_at"]
    assert session["last_activity"]
    assert session["max_expires_at"]

    redis.setex.assert_called_once()


# ---------------------------------------------------------------------------
# get_session
# ---------------------------------------------------------------------------

@patch("app.auth.session_service.get_redis_client")
def test_get_session_returns_session(mock_get_redis):
    redis = MagicMock()
    mock_get_redis.return_value = redis

    session = make_session()

    redis.get.return_value = json.dumps(session)

    result = get_session("session-123")

    assert result is not None
    assert result["session_id"] == "session-123"
    assert result["user_id"] == "user-1"


@patch("app.auth.session_service.get_redis_client")
def test_get_session_returns_none_when_missing(mock_get_redis):
    redis = MagicMock()
    mock_get_redis.return_value = redis

    redis.get.return_value = None

    result = get_session("missing-session")

    assert result is None


# ---------------------------------------------------------------------------
# Idle timeout
# ---------------------------------------------------------------------------

@patch("app.auth.session_service.get_redis_client")
@patch("app.auth.session_service.get_session")
def test_idle_timeout_expires_session(mock_get_session, mock_get_redis):
    now = datetime.now(timezone.utc)

    session = make_session(
        last_activity=now - timedelta(minutes=31),
        max_expires_at=now + timedelta(hours=7),
    )

    mock_get_session.return_value = session

    redis = MagicMock()
    mock_get_redis.return_value = redis

    with patch(
        "app.auth.session_service.SESSION_IDLE_TIMEOUT_MINUTES",
        30,
    ):
        result = validate_session(
            session_id="session-123",
            user_id="user-1",
            tenant_id="tenant-1",
        )

    assert result is None
    redis.delete.assert_called_once()


# ---------------------------------------------------------------------------
# Active session should remain valid
# ---------------------------------------------------------------------------

@patch("app.auth.session_service.get_session")
def test_active_session_is_valid(mock_get_session):
    now = datetime.now(timezone.utc)

    session = make_session(
        last_activity=now - timedelta(minutes=5),
        max_expires_at=now + timedelta(hours=7),
    )

    mock_get_session.return_value = session

    with patch(
        "app.auth.session_service.SESSION_IDLE_TIMEOUT_MINUTES",
        30,
    ):
        result = validate_session(
            session_id="session-123",
            user_id="user-1",
            tenant_id="tenant-1",
        )

    assert result == session


# ---------------------------------------------------------------------------
# Maximum lifetime
# ---------------------------------------------------------------------------

@patch("app.auth.session_service.get_redis_client")
@patch("app.auth.session_service.get_session")
def test_max_lifetime_expires_session(
    mock_get_session,
    mock_get_redis,
):
    now = datetime.now(timezone.utc)

    session = make_session(
        last_activity=now - timedelta(minutes=1),
        max_expires_at=now - timedelta(seconds=1),
    )

    mock_get_session.return_value = session

    redis = MagicMock()
    mock_get_redis.return_value = redis

    result = validate_session(
        session_id="session-123",
        user_id="user-1",
        tenant_id="tenant-1",
    )

    assert result is None
    redis.delete.assert_called_once()


# ---------------------------------------------------------------------------
# touch_session
# ---------------------------------------------------------------------------

@patch("app.auth.session_service.get_redis_client")
@patch("app.auth.session_service.get_session")
def test_touch_session_updates_last_activity(
    mock_get_session,
    mock_get_redis,
):
    now = datetime.now(timezone.utc)

    old_activity = now - timedelta(minutes=10)

    session = make_session(
        last_activity=old_activity,
        max_expires_at=now + timedelta(hours=7),
    )

    mock_get_session.return_value = session

    redis = MagicMock()
    mock_get_redis.return_value = redis

    result = touch_session("session-123")

    assert result is not None

    updated_activity = datetime.fromisoformat(
        result["last_activity"]
    )

    assert updated_activity > old_activity
    redis.setex.assert_called_once()


# ---------------------------------------------------------------------------
# touch_session must not extend maximum lifetime
# ---------------------------------------------------------------------------

@patch("app.auth.session_service.get_redis_client")
@patch("app.auth.session_service.get_session")
def test_touch_session_does_not_extend_max_lifetime(
    mock_get_session,
    mock_get_redis,
):
    now = datetime.now(timezone.utc)

    max_expires_at = now + timedelta(seconds=30)

    session = make_session(
        last_activity=now - timedelta(minutes=1),
        max_expires_at=max_expires_at,
    )

    mock_get_session.return_value = session

    redis = MagicMock()
    mock_get_redis.return_value = redis

    result = touch_session("session-123")

    assert result is not None

    updated_max_expires = datetime.fromisoformat(
        result["max_expires_at"]
    )

    assert updated_max_expires == max_expires_at


# ---------------------------------------------------------------------------
# Expired session cannot be touched
# ---------------------------------------------------------------------------

@patch("app.auth.session_service.get_redis_client")
@patch("app.auth.session_service.get_session")
def test_touch_session_rejects_expired_max_lifetime(
    mock_get_session,
    mock_get_redis,
):
    now = datetime.now(timezone.utc)

    session = make_session(
        last_activity=now - timedelta(minutes=1),
        max_expires_at=now - timedelta(seconds=1),
    )

    mock_get_session.return_value = session

    redis = MagicMock()
    mock_get_redis.return_value = redis

    result = touch_session("session-123")

    assert result is None
    redis.delete.assert_called_once()


# ---------------------------------------------------------------------------
# Wrong user cannot use session
# ---------------------------------------------------------------------------

@patch("app.auth.session_service.get_session")
def test_session_rejects_wrong_user(mock_get_session):
    session = make_session(user_id="user-1")

    mock_get_session.return_value = session

    result = validate_session(
        session_id="session-123",
        user_id="user-2",
        tenant_id="tenant-1",
    )

    assert result is None


# ---------------------------------------------------------------------------
# Wrong tenant cannot use session
# ---------------------------------------------------------------------------

@patch("app.auth.session_service.get_session")
def test_session_rejects_wrong_tenant(mock_get_session):
    session = make_session(tenant_id="tenant-1")

    mock_get_session.return_value = session

    result = validate_session(
        session_id="session-123",
        user_id="user-1",
        tenant_id="tenant-2",
    )

    assert result is None


# ---------------------------------------------------------------------------
# Concurrent sessions
# ---------------------------------------------------------------------------

@patch("app.auth.session_service.get_redis_client")
def test_concurrent_sessions_are_independent(mock_get_redis):
    redis = MagicMock()
    mock_get_redis.return_value = redis

    session_1 = create_session(
        user_id="user-1",
        tenant_id="tenant-1",
    )

    session_2 = create_session(
        user_id="user-1",
        tenant_id="tenant-1",
    )

    assert session_1["session_id"] != session_2["session_id"]

    # Both sessions should be stored independently.
    assert redis.setex.call_count == 2


# ---------------------------------------------------------------------------
# Logout/delete
# ---------------------------------------------------------------------------

@patch("app.auth.session_service.get_redis_client")
def test_delete_session(mock_get_redis):
    redis = MagicMock()
    mock_get_redis.return_value = redis

    delete_session("session-123")

    redis.delete.assert_called_once_with(
        "auth:session:session-123"
    )