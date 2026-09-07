"""
JWT token creation, verification, and management.

Security properties:
- Algorithm pinned to HS256 (no algorithm confusion attacks)
- Access tokens are short-lived (configurable, default 30 min)
- Refresh tokens are long-lived (configurable, default 7 days)
- Token blacklisting via Redis for immediate revocation
- JWT contains only: user_id, tenant_id, role, exp (minimal claims)
"""

import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

import jwt

from ..redis_client import get_redis_client


# Configuration from environment
JWT_SECRET = os.getenv("JWT_SECRET", "CHANGE-ME-IN-PRODUCTION-fieldops-secret-key-2026")
JWT_ALGORITHM = "HS256"  # Pinned — never trust from env/request
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7"))


def create_access_token(
    user_id: str,
    tenant_id: str,
    role: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a signed JWT access token.

    Claims:
    - sub: user_id
    - tenant_id: tenant_id
    - role: role name
    - exp: expiration timestamp
    - iat: issued at timestamp
    - jti: unique token identifier (for blacklisting)
    """
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))

    payload = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "role": role,
        "exp": expire,
        "iat": now,
        "jti": str(uuid.uuid4()),
        "type": "access",
    }

    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_refresh_token(
    user_id: str,
    tenant_id: str,
    role: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a signed JWT refresh token.

    Refresh tokens have a longer TTL and are used to obtain new
    access tokens without re-authentication.
    """
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))

    payload = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "role": role,
        "exp": expire,
        "iat": now,
        "jti": str(uuid.uuid4()),
        "type": "refresh",
    }

    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """
    Decode and verify a JWT token.

    Raises:
    - jwt.ExpiredSignatureError: token has expired
    - jwt.InvalidTokenError: token is malformed or signature invalid

    Returns the decoded claims dict.
    """
    return jwt.decode(
        token,
        JWT_SECRET,
        algorithms=[JWT_ALGORITHM],
        options={"require": ["exp", "sub", "tenant_id", "role"]},
    )


def is_token_blacklisted(jti: str) -> bool:
    """Check if a token JTI has been blacklisted (revoked)."""
    redis = get_redis_client()
    if redis:
        return bool(redis.get(f"token:blacklist:{jti}"))
    return False


def blacklist_token(jti: str, expires_in_seconds: int) -> None:
    """
    Add a token JTI to the blacklist.

    The blacklist entry automatically expires when the token would have
    expired, so Redis doesn't accumulate stale entries.
    """
    redis = get_redis_client()
    if redis:
        redis.setex(f"token:blacklist:{jti}", expires_in_seconds, "1")


def verify_access_token(token: str) -> dict:
    """
    Verify an access token is valid, not expired, and not blacklisted.

    Returns the decoded claims.
    Raises jwt.InvalidTokenError on any verification failure.
    """
    claims = decode_token(token)

    if claims.get("type") != "access":
        raise jwt.InvalidTokenError("Not an access token")

    if is_token_blacklisted(claims.get("jti", "")):
        raise jwt.InvalidTokenError("Token has been revoked")

    return claims


def verify_refresh_token(token: str) -> dict:
    """
    Verify a refresh token is valid, not expired, and not blacklisted.

    Returns the decoded claims.
    Raises jwt.InvalidTokenError on any verification failure.
    """
    claims = decode_token(token)

    if claims.get("type") != "refresh":
        raise jwt.InvalidTokenError("Not a refresh token")

    if is_token_blacklisted(claims.get("jti", "")):
        raise jwt.InvalidTokenError("Token has been revoked")

    return claims
