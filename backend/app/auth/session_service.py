"""
Application session management.

Tracks server-side session state independently from
short-lived JWT access-token expiration.
"""

import json
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from ..redis_client import get_redis_client


# =========================================================
# CONFIGURATION
# =========================================================

SESSION_IDLE_TIMEOUT_MINUTES = int(
    os.getenv("SESSION_IDLE_TIMEOUT_MINUTES", "30")
)

SESSION_MAX_LIFETIME_HOURS = int(
    os.getenv("SESSION_MAX_LIFETIME_HOURS", "8")
)

SESSION_KEY_PREFIX = "auth:session:"


# =========================================================
# INTERNAL HELPERS
# =========================================================

def _session_key(session_id: str) -> str:
    """
    Build the Redis key for a session.
    """
    return f"{SESSION_KEY_PREFIX}{session_id}"


def _now() -> datetime:
    """
    Return the current UTC time.
    """
    return datetime.now(timezone.utc)


# =========================================================
# CREATE SESSION
# =========================================================

def create_session(
    user_id: str,
    tenant_id: str,
) -> dict:
    """
    Create a new server-side application session.

    The session has:

    - an idle timeout
    - an absolute maximum lifetime

    The Redis TTL is limited by the absolute
    maximum lifetime.
    """

    now = _now()

    session_id = str(uuid.uuid4())

    max_expires_at = (
        now
        + timedelta(
            hours=SESSION_MAX_LIFETIME_HOURS
        )
    )

    session = {
        "session_id": session_id,
        "user_id": str(user_id),
        "tenant_id": str(tenant_id),
        "created_at": now.isoformat(),
        "last_activity": now.isoformat(),
        "max_expires_at": max_expires_at.isoformat(),
    }

    redis = get_redis_client()

    if redis is None:
        raise RuntimeError(
            "Redis is required for application session management"
        )

    ttl = max(
        1,
        int(
            (
                max_expires_at - now
            ).total_seconds()
        ),
    )

    redis.setex(
        _session_key(session_id),
        ttl,
        json.dumps(session),
    )

    return session


# =========================================================
# GET SESSION
# =========================================================

def get_session(
    session_id: str,
) -> Optional[dict]:
    """
    Retrieve a session from Redis.

    Returns:
        Session dictionary if found.
        None if the session does not exist.
    """

    if not session_id:
        return None

    redis = get_redis_client()

    if redis is None:
        return None

    raw = redis.get(
        _session_key(session_id)
    )

    if not raw:
        return None

    try:
        return json.loads(raw)

    except (
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ):
        return None


# =========================================================
# VALIDATE SESSION
# =========================================================

def validate_session(
    session_id: str,
    user_id: str,
    tenant_id: str,
) -> Optional[dict]:
    """
    Validate a server-side session.

    Validation includes:

    1. Session exists in Redis.
    2. Session belongs to the authenticated user.
    3. Session belongs to the authenticated tenant.
    4. Session has not exceeded absolute lifetime.
    5. Session has not exceeded idle timeout.

    If the session is valid, last_activity is updated.

    IMPORTANT:
    Updating last_activity NEVER extends max_expires_at.
    """

    if not session_id:
        return None

    session = get_session(
        session_id
    )

    # -----------------------------------------------------
    # Session does not exist
    # -----------------------------------------------------

    if session is None:
        return None

    # -----------------------------------------------------
    # User validation
    # -----------------------------------------------------

    session_user_id = session.get(
        "user_id"
    )

    if str(session_user_id) != str(user_id):
        return None

    # -----------------------------------------------------
    # Tenant validation
    # -----------------------------------------------------

    session_tenant_id = session.get(
        "tenant_id"
    )

    if str(session_tenant_id) != str(tenant_id):
        return None

    # -----------------------------------------------------
    # Parse timestamps
    # -----------------------------------------------------

    now = _now()

    try:
        last_activity = datetime.fromisoformat(
            session["last_activity"]
        )

        max_expires_at = datetime.fromisoformat(
            session["max_expires_at"]
        )

    except (
        KeyError,
        TypeError,
        ValueError,
    ):
        delete_session(
            session_id
        )

        return None

    # -----------------------------------------------------
    # Absolute lifetime
    # -----------------------------------------------------

    if now >= max_expires_at:
        delete_session(
            session_id
        )

        return None

    # -----------------------------------------------------
    # Idle timeout
    # -----------------------------------------------------

    idle_deadline = (
        last_activity
        + timedelta(
            minutes=SESSION_IDLE_TIMEOUT_MINUTES
        )
    )

    if now >= idle_deadline:
        delete_session(
            session_id
        )

        return None

    # -----------------------------------------------------
    # Session is valid
    #
    # Update last activity.
    #
    # DO NOT update max_expires_at.
    # -----------------------------------------------------

    session["last_activity"] = (
        now.isoformat()
    )

    redis = get_redis_client()

    if redis is None:
        return None

    # -----------------------------------------------------
    # Redis TTL
    #
    # The TTL can NEVER go beyond the absolute
    # session expiration.
    # -----------------------------------------------------

    ttl = max(
        1,
        int(
            (
                max_expires_at - now
            ).total_seconds()
        ),
    )

    redis.setex(
        _session_key(session_id),
        ttl,
        json.dumps(session),
    )

    return session


# =========================================================
# TOUCH SESSION
# =========================================================

def touch_session(
    session_id: str,
) -> Optional[dict]:
    """
    Update last_activity for an active session.

    This extends the idle timeout but NEVER extends
    the absolute maximum lifetime.
    """

    if not session_id:
        return None

    session = get_session(
        session_id
    )

    if session is None:
        return None

    now = _now()

    try:
        max_expires_at = datetime.fromisoformat(
            session["max_expires_at"]
        )

    except (
        KeyError,
        TypeError,
        ValueError,
    ):
        delete_session(
            session_id
        )

        return None

    # -----------------------------------------------------
    # Absolute lifetime
    # -----------------------------------------------------

    if now >= max_expires_at:
        delete_session(
            session_id
        )

        return None

    # -----------------------------------------------------
    # Update activity
    # -----------------------------------------------------

    session["last_activity"] = (
        now.isoformat()
    )

    redis = get_redis_client()

    if redis is None:
        return None

    # -----------------------------------------------------
    # Redis TTL remains limited by max lifetime
    # -----------------------------------------------------

    ttl = max(
        1,
        int(
            (
                max_expires_at - now
            ).total_seconds()
        ),
    )

    redis.setex(
        _session_key(session_id),
        ttl,
        json.dumps(session),
    )

    return session


# =========================================================
# DELETE SESSION
# =========================================================

def delete_session(
    session_id: str,
) -> None:
    """
    Delete a server-side session from Redis.
    """

    if not session_id:
        return

    redis = get_redis_client()

    if redis is not None:
        redis.delete(
            _session_key(session_id)
        )


# =========================================================
# SESSION EXISTS
# =========================================================

def session_exists(
    session_id: str,
) -> bool:
    """
    Check whether a session currently exists
    in Redis.

    This does not validate user/tenant ownership.
    """

    if not session_id:
        return False

    redis = get_redis_client()

    if redis is None:
        return False

    return bool(
        redis.exists(
            _session_key(session_id)
        )
    )


# =========================================================
# GET SESSION TTL
# =========================================================

def get_session_ttl(
    session_id: str,
) -> int:
    """
    Return the remaining Redis TTL for a session.

    Returns:
        Positive integer = seconds remaining.
        -1 = key exists without expiration.
        -2 = key does not exist.
        -1/-2 follow Redis TTL semantics.
    """

    if not session_id:
        return -2

    redis = get_redis_client()

    if redis is None:
        return -2

    return int(
        redis.ttl(
            _session_key(session_id)
        )
    )


# =========================================================
# REVOKE SESSION
# =========================================================

def revoke_session(
    session_id: str,
) -> None:
    """
    Explicitly revoke a session.

    This is an alias around delete_session()
    for clearer authentication terminology.
    """

    delete_session(
        session_id
    )