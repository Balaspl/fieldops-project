"""
JWT token creation, verification, and management.

Security properties:
- HS256 algorithm is pinned.
- Access and refresh tokens have different token types.
- Required claims are enforced.
- Access-token scopes are included in the token.
- Server-side session ID is included in access and refresh tokens.
- Access and refresh token TTLs are centrally configured and bounded.
- JWT_SECRET must be explicitly configured.
- Refresh tokens can be blacklisted.
- Trusted-device tokens are random opaque tokens and are stored hashed.
"""

import hashlib
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

import jwt

from ..redis_client import get_redis_client


# ============================================================
# SESSION CONFIGURATION
# ============================================================

SESSION_IDLE_TIMEOUT_MINUTES = int(
    os.getenv(
        "SESSION_IDLE_TIMEOUT_MINUTES",
        "30",
    )
)

SESSION_MAX_LIFETIME_HOURS = int(
    os.getenv(
        "SESSION_MAX_LIFETIME_HOURS",
        "8",
    )
)


# ============================================================
# JWT CONFIGURATION
# ============================================================

# IMPORTANT:
# There is intentionally NO unsafe fallback secret.
#
# JWT_SECRET must be explicitly configured through the
# environment.
JWT_SECRET = os.getenv("JWT_SECRET")

# Algorithm is intentionally pinned.
JWT_ALGORITHM = "HS256"


# ============================================================
# JWT TTL CONFIGURATION
# ============================================================

# Current access-token lifetime.
ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv(
        "JWT_ACCESS_TOKEN_EXPIRE_MINUTES",
        "30",
    )
)

# Current refresh-token lifetime.
REFRESH_TOKEN_EXPIRE_DAYS = int(
    os.getenv(
        "JWT_REFRESH_TOKEN_EXPIRE_DAYS",
        "7",
    )
)


# ============================================================
# JWT TTL BOUNDS
# ============================================================

# Access-token TTL must remain between these values.
ACCESS_TOKEN_MIN_EXPIRE_MINUTES = int(
    os.getenv(
        "JWT_ACCESS_TOKEN_MIN_EXPIRE_MINUTES",
        "5",
    )
)

ACCESS_TOKEN_MAX_EXPIRE_MINUTES = int(
    os.getenv(
        "JWT_ACCESS_TOKEN_MAX_EXPIRE_MINUTES",
        "60",
    )
)


# Refresh-token TTL must remain between these values.
REFRESH_TOKEN_MIN_EXPIRE_DAYS = int(
    os.getenv(
        "JWT_REFRESH_TOKEN_MIN_EXPIRE_DAYS",
        "1",
    )
)

REFRESH_TOKEN_MAX_EXPIRE_DAYS = int(
    os.getenv(
        "JWT_REFRESH_TOKEN_MAX_EXPIRE_DAYS",
        "30",
    )
)


# ============================================================
# JWT CONFIGURATION VALIDATION
# ============================================================

def _validate_jwt_configuration() -> None:
    """
    Validate JWT security configuration at application startup.

    This prevents:
    - Missing JWT secrets.
    - Unsupported algorithms.
    - Invalid access-token TTLs.
    - Invalid refresh-token TTLs.
    - TTLs outside the configured security bounds.
    """

    # --------------------------------------------------------
    # JWT secret
    # --------------------------------------------------------

    if not JWT_SECRET:
        raise RuntimeError(
            "JWT_SECRET must be explicitly configured"
        )

    # --------------------------------------------------------
    # Algorithm
    # --------------------------------------------------------

    if JWT_ALGORITHM != "HS256":
        raise RuntimeError(
            "JWT_ALGORITHM must be HS256"
        )

    # --------------------------------------------------------
    # Access-token bounds
    # --------------------------------------------------------

    if ACCESS_TOKEN_MIN_EXPIRE_MINUTES <= 0:
        raise RuntimeError(
            "JWT access-token minimum TTL must be greater than zero"
        )

    if ACCESS_TOKEN_MAX_EXPIRE_MINUTES <= 0:
        raise RuntimeError(
            "JWT access-token maximum TTL must be greater than zero"
        )

    if ACCESS_TOKEN_MAX_EXPIRE_MINUTES < (
        ACCESS_TOKEN_MIN_EXPIRE_MINUTES
    ):
        raise RuntimeError(
            "JWT access-token maximum TTL cannot be "
            "less than minimum TTL"
        )

    if not (
        ACCESS_TOKEN_MIN_EXPIRE_MINUTES
        <= ACCESS_TOKEN_EXPIRE_MINUTES
        <= ACCESS_TOKEN_MAX_EXPIRE_MINUTES
    ):
        raise RuntimeError(
            "JWT_ACCESS_TOKEN_EXPIRE_MINUTES is outside "
            "the allowed configuration bounds"
        )

    # --------------------------------------------------------
    # Refresh-token bounds
    # --------------------------------------------------------

    if REFRESH_TOKEN_MIN_EXPIRE_DAYS <= 0:
        raise RuntimeError(
            "JWT refresh-token minimum TTL must be greater than zero"
        )

    if REFRESH_TOKEN_MAX_EXPIRE_DAYS <= 0:
        raise RuntimeError(
            "JWT refresh-token maximum TTL must be greater than zero"
        )

    if REFRESH_TOKEN_MAX_EXPIRE_DAYS < (
        REFRESH_TOKEN_MIN_EXPIRE_DAYS
    ):
        raise RuntimeError(
            "JWT refresh-token maximum TTL cannot be "
            "less than minimum TTL"
        )

    if not (
        REFRESH_TOKEN_MIN_EXPIRE_DAYS
        <= REFRESH_TOKEN_EXPIRE_DAYS
        <= REFRESH_TOKEN_MAX_EXPIRE_DAYS
    ):
        raise RuntimeError(
            "JWT_REFRESH_TOKEN_EXPIRE_DAYS is outside "
            "the allowed configuration bounds"
        )


# Validate immediately when this module is loaded.
_validate_jwt_configuration()


# ============================================================
# JWT REQUIRED CLAIMS
# ============================================================

REQUIRED_CLAIMS = [
    "exp",
    "sub",
    "tenant_id",
    "role",
    "iat",
    "jti",
    "type",
]


# ============================================================
# TRUSTED DEVICE CONFIGURATION
# ============================================================

TRUSTED_DEVICE_EXPIRE_DAYS = int(
    os.getenv(
        "TRUSTED_DEVICE_EXPIRE_DAYS",
        "30",
    )
)


# ============================================================
# SCOPE HELPERS
# ============================================================

def _normalise_scopes(
    scopes: Optional[Iterable[str]],
) -> list[str]:
    """
    Normalize and clean access-token scopes.
    """

    if not scopes:
        return []

    return sorted(
        {
            str(scope).strip()
            for scope in scopes
            if str(scope).strip()
        }
    )


# ============================================================
# ACCESS TOKEN TTL VALIDATION
# ============================================================

def _validate_access_token_ttl(
    expires_delta: timedelta,
) -> None:
    """
    Validate a custom access-token lifetime.

    Any explicitly supplied expires_delta must remain within
    the centrally configured access-token bounds.
    """

    if not isinstance(
        expires_delta,
        timedelta,
    ):
        raise TypeError(
            "expires_delta must be a timedelta"
        )

    seconds = expires_delta.total_seconds()

    minimum_seconds = (
        ACCESS_TOKEN_MIN_EXPIRE_MINUTES
        * 60
    )

    maximum_seconds = (
        ACCESS_TOKEN_MAX_EXPIRE_MINUTES
        * 60
    )

    if seconds < minimum_seconds:
        raise ValueError(
            "Access-token TTL is below the configured minimum"
        )

    if seconds > maximum_seconds:
        raise ValueError(
            "Access-token TTL exceeds the configured maximum"
        )


# ============================================================
# REFRESH TOKEN TTL VALIDATION
# ============================================================

def _validate_refresh_token_ttl(
    expires_delta: timedelta,
) -> None:
    """
    Validate a custom refresh-token lifetime.

    Any explicitly supplied expires_delta must remain within
    the centrally configured refresh-token bounds.
    """

    if not isinstance(
        expires_delta,
        timedelta,
    ):
        raise TypeError(
            "expires_delta must be a timedelta"
        )

    seconds = expires_delta.total_seconds()

    minimum_seconds = (
        REFRESH_TOKEN_MIN_EXPIRE_DAYS
        * 24
        * 60
        * 60
    )

    maximum_seconds = (
        REFRESH_TOKEN_MAX_EXPIRE_DAYS
        * 24
        * 60
        * 60
    )

    if seconds < minimum_seconds:
        raise ValueError(
            "Refresh-token TTL is below the configured minimum"
        )

    if seconds > maximum_seconds:
        raise ValueError(
            "Refresh-token TTL exceeds the configured maximum"
        )


# ============================================================
# ACCESS TOKEN
# ============================================================

def create_access_token(
    user_id: str,
    tenant_id: str,
    role: str,
    expires_delta: Optional[timedelta] = None,
    scopes: Optional[Iterable[str]] = None,
    session_id: Optional[str] = None,
) -> str:
    """
    Create a signed access JWT.

    Tenant ID and role are issued from the server-side
    authenticated User record.

    session_id is included in the access token so that
    protected endpoints can validate the server-side
    Redis session.

    The token always receives an expiration timestamp.
    """

    now = datetime.now(timezone.utc)

    # --------------------------------------------------------
    # Determine token lifetime
    # --------------------------------------------------------

    if expires_delta is not None:
        _validate_access_token_ttl(
            expires_delta
        )

        lifetime = expires_delta

    else:
        lifetime = timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        )

    expire = now + lifetime

    # --------------------------------------------------------
    # Token payload
    # --------------------------------------------------------

    payload = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "role": str(role),
        "exp": expire,
        "iat": now,
        "jti": str(uuid.uuid4()),
        "type": "access",
        "scope": " ".join(
            _normalise_scopes(scopes)
        ),
    }

    # IMPORTANT:
    # The access token MUST contain the same session_id
    # that was created in Redis during login.
    if session_id:
        payload["session_id"] = str(session_id)

    # --------------------------------------------------------
    # Encode
    # --------------------------------------------------------

    return jwt.encode(
        payload,
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


# ============================================================
# REFRESH TOKEN
# ============================================================

def create_refresh_token(
    user_id: str,
    tenant_id: str,
    role: str,
    expires_delta: Optional[timedelta] = None,
    session_id: Optional[str] = None,
) -> str:
    """
    Create a signed refresh JWT.

    Refresh tokens do not carry authorization scopes.

    The server-side session ID is preserved so that a refresh
    operation can create a new access token belonging to the
    same server-side session.

    The token always receives an expiration timestamp.
    """

    now = datetime.now(timezone.utc)

    # --------------------------------------------------------
    # Determine token lifetime
    # --------------------------------------------------------

    if expires_delta is not None:
        _validate_refresh_token_ttl(
            expires_delta
        )

        lifetime = expires_delta

    else:
        lifetime = timedelta(
            days=REFRESH_TOKEN_EXPIRE_DAYS
        )

    expire = now + lifetime

    # --------------------------------------------------------
    # Token payload
    # --------------------------------------------------------

    payload = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "role": str(role),
        "exp": expire,
        "iat": now,
        "jti": str(uuid.uuid4()),
        "type": "refresh",
    }

    # Preserve the server-side session.
    if session_id:
        payload["session_id"] = str(session_id)

    # --------------------------------------------------------
    # Encode
    # --------------------------------------------------------

    return jwt.encode(
        payload,
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


# ============================================================
# DECODE TOKEN
# ============================================================

def decode_token(
    token: str,
) -> dict:
    """
    Decode and cryptographically verify a JWT.

    Security properties:
    - HS256 is explicitly pinned.
    - Required claims are enforced.
    - exp is required and automatically validated.
    - iat is required.
    - Token signature is verified.
    """

    if not token:
        raise jwt.InvalidTokenError(
            "Token is required"
        )

    return jwt.decode(
        token,
        JWT_SECRET,
        algorithms=[JWT_ALGORITHM],
        options={
            "require": REQUIRED_CLAIMS,
        },
    )


# ============================================================
# BLACKLIST
# ============================================================

def is_token_blacklisted(
    jti: str,
) -> bool:
    """
    Return True when the token JTI is revoked.
    """

    if not jti:
        return True

    redis = get_redis_client()

    if redis is None:
        # Existing project policy:
        # Redis unavailable means blacklist lookup
        # cannot be performed.
        #
        # NOTE:
        # JWT signature and expiry validation still happen.
        #
        # Production deployments should ensure Redis
        # availability when blacklist enforcement is required.
        return False

    return bool(
        redis.get(
            f"token:blacklist:{jti}"
        )
    )


def blacklist_token(
    jti: str,
    expires_in_seconds: int,
) -> None:
    """
    Blacklist a token until its natural expiration.
    """

    if not jti:
        return

    redis = get_redis_client()

    if redis is None:
        return

    redis.setex(
        f"token:blacklist:{jti}",
        max(
            1,
            int(expires_in_seconds),
        ),
        "1",
    )


# ============================================================
# ACCESS TOKEN VERIFICATION
# ============================================================

def verify_access_token(
    token: str,
) -> dict:
    """
    Verify a valid, non-revoked access token.

    Returns the decoded JWT claims.

    Expired tokens are rejected by decode_token().
    """

    claims = decode_token(token)

    if claims.get("type") != "access":
        raise jwt.InvalidTokenError(
            "Not an access token"
        )

    if is_token_blacklisted(
        claims.get("jti", "")
    ):
        raise jwt.InvalidTokenError(
            "Token has been revoked"
        )

    return claims


# ============================================================
# REFRESH TOKEN VERIFICATION
# ============================================================

def verify_refresh_token(
    token: str,
) -> dict:
    """
    Verify a valid, non-revoked refresh token.

    Returns the decoded JWT claims.

    Expired refresh JWTs are rejected by decode_token().
    The refresh-token database record expiration must also
    be validated by the refresh-token service/route.
    """

    claims = decode_token(token)

    if claims.get("type") != "refresh":
        raise jwt.InvalidTokenError(
            "Not a refresh token"
        )

    if is_token_blacklisted(
        claims.get("jti", "")
    ):
        raise jwt.InvalidTokenError(
            "Token has been revoked"
        )

    return claims


# ============================================================
# TRUSTED DEVICE TOKEN
# ============================================================

def create_trusted_device_token() -> str:
    """
    Create a random opaque token used to remember
    a trusted device.

    This is NOT a JWT.

    The raw token should be returned to the client.
    Only its SHA-256 hash should be stored in the database.
    """

    return (
        uuid.uuid4().hex
        + uuid.uuid4().hex
    )


# ============================================================
# TRUSTED DEVICE TOKEN HASH
# ============================================================

def hash_trusted_device_token(
    token: str,
) -> str:
    """
    Hash a trusted-device token before storing it
    or looking it up in the database.
    """

    if not token:
        raise ValueError(
            "Trusted device token cannot be empty"
        )

    return hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()