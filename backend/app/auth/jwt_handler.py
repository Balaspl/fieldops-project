"""
JWT token creation, verification, and management.

Security properties:
- HS256 algorithm is pinned.
- Access and refresh tokens have different token types.
- Required claims are enforced.
- Access-token scopes are included in the token.
- Refresh tokens can be blacklisted.
"""

import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Iterable

import jwt

from ..redis_client import get_redis_client


JWT_SECRET = os.getenv(
    "JWT_SECRET",
    "CHANGE-ME-IN-PRODUCTION-fieldops-secret-key-2026",
)

JWT_ALGORITHM = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30")
)

REFRESH_TOKEN_EXPIRE_DAYS = int(
    os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7")
)


REQUIRED_CLAIMS = [
    "exp",
    "sub",
    "tenant_id",
    "role",
    "iat",
    "jti",
    "type",
]


def _normalise_scopes(scopes: Optional[Iterable[str]]) -> list[str]:
    if not scopes:
        return []

    return sorted({
        str(scope).strip()
        for scope in scopes
        if str(scope).strip()
    })


def create_access_token(
    user_id: str,
    tenant_id: str,
    role: str,
    expires_delta: Optional[timedelta] = None,
    scopes: Optional[Iterable[str]] = None,
) -> str:
    """
    Create a signed access JWT.

    Tenant and role are issued from the server-side User record.
    """

    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta
        or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    payload = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "role": str(role),
        "exp": expire,
        "iat": now,
        "jti": str(uuid.uuid4()),
        "type": "access",
        "scope": " ".join(_normalise_scopes(scopes)),
    }

    return jwt.encode(
        payload,
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


def create_refresh_token(
    user_id: str,
    tenant_id: str,
    role: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a signed refresh JWT.

    Refresh tokens do not carry authorization scopes.
    """

    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta
        or timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    )

    payload = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "role": str(role),
        "exp": expire,
        "iat": now,
        "jti": str(uuid.uuid4()),
        "type": "refresh",
    }

    return jwt.encode(
        payload,
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


def decode_token(token: str) -> dict:
    """
    Decode and cryptographically verify a JWT.

    The algorithm is explicitly pinned to HS256.
    """

    return jwt.decode(
        token,
        JWT_SECRET,
        algorithms=[JWT_ALGORITHM],
        options={
            "require": REQUIRED_CLAIMS,
        },
    )


def is_token_blacklisted(jti: str) -> bool:
    """Return True when the token JTI is revoked."""

    if not jti:
        return True

    redis = get_redis_client()

    if redis is None:
        # Current project policy: Redis unavailable means no blacklist
        # lookup can be performed. This can be changed to fail-closed
        # in production if required.
        return False

    return bool(redis.get(f"token:blacklist:{jti}"))


def blacklist_token(
    jti: str,
    expires_in_seconds: int,
) -> None:
    """Blacklist a token until its natural expiration."""

    if not jti:
        return

    redis = get_redis_client()

    if redis is not None:
        redis.setex(
            f"token:blacklist:{jti}",
            max(1, int(expires_in_seconds)),
            "1",
        )


def verify_access_token(token: str) -> dict:
    """Verify a valid, non-revoked access token."""

    claims = decode_token(token)

    if claims.get("type") != "access":
        raise jwt.InvalidTokenError("Not an access token")

    if is_token_blacklisted(claims.get("jti", "")):
        raise jwt.InvalidTokenError("Token has been revoked")

    return claims


def verify_refresh_token(token: str) -> dict:
    """Verify a valid, non-revoked refresh token."""

    claims = decode_token(token)

    if claims.get("type") != "refresh":
        raise jwt.InvalidTokenError("Not a refresh token")

    if is_token_blacklisted(claims.get("jti", "")):
        raise jwt.InvalidTokenError("Token has been revoked")

    return claims