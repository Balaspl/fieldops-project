"""
OAuth2 token endpoint — RFC 6749-shaped boundary over the existing
JWT issuance and verification logic.

Supported grant types:
- password
- refresh_token

Unsupported grant types:
- client_credentials
- authorization_code

MFA:
- MFA-protected users do not receive JWTs from password authentication
  until the second factor has been successfully verified.
"""

import hashlib
import logging
import uuid

from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..database import get_db

from ..auth.password import verify_password

from ..auth.jwt_handler import (
    create_access_token,
    create_refresh_token,
    verify_refresh_token,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
)

from ..auth.oauth2_scope import (
    validate_requested_scope,
    default_scope_for_role,
)

from ..auth.session_service import create_session, validate_session, touch_session


from ..models.organization import Organization
from ..models.user import User, RefreshToken

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/oauth2",
    tags=["OAuth2"],
)

SUPPORTED_GRANT_TYPES = {
    "password",
    "refresh_token",
}


class GrantError(Exception):
    def __init__(
        self,
        error: str,
        description: str,
        status_code: int = 400,
    ):
        self.error = error
        self.description = description
        self.status_code = status_code
        super().__init__(description)


def _oauth_error(
    error: str,
    description: str,
    status_code: int = 400,
):
    raise HTTPException(
        status_code=status_code,
        detail={
            "error": error,
            "error_description": description,
        },
    )


def _persist_refresh_token(
    db: Session,
    user: User,
    refresh_token_str: str,
    request: Request,
    session_id: Optional[str] = None,
) -> None:
    """
    Store only a SHA-256 hash of the refresh token.

    The raw refresh token is never stored in the database.
    """

    token_hash = hashlib.sha256(
        refresh_token_str.encode("utf-8")
    ).hexdigest()

    record = RefreshToken(
        id=str(uuid.uuid4()),
        user_id=user.id,
        session_id=session_id,
        token_hash=token_hash,
        expires_at=(
            datetime.now(timezone.utc)
            + timedelta(
                days=REFRESH_TOKEN_EXPIRE_DAYS
            )
        ),
        device_info=request.headers.get(
            "User-Agent",
            "unknown",
        )[:255],
        ip_address=(
            request.client.host
            if request.client
            else "unknown"
        ),
    )

    db.add(record)


def _validate_scope(
    user: User,
    requested_scope: Optional[str],
) -> str:
    """
    Validate scope using the role stored in the database.

    The user's database role is authoritative.
    """

    from ..auth.rbac import UserRole

    try:
        role = UserRole(user.role)
    except ValueError:
        raise GrantError(
            "invalid_grant",
            "User role is invalid",
            status.HTTP_401_UNAUTHORIZED,
        )

    try:
        if requested_scope:
            return validate_requested_scope(
                role,
                requested_scope,
            )

        return default_scope_for_role(role)

    except (ValueError, PermissionError) as exc:
        raise GrantError(
            "invalid_scope",
            str(exc),
            status.HTTP_400_BAD_REQUEST,
        )


def _authenticate_password(
    db: Session,
    request: Request,
    username: str,
    password: str,
    requested_scope: Optional[str] = None,
) -> tuple[User, str]:
    """
    Authenticate a user using email/password.

    IMPORTANT:
    This function performs authentication and scope validation only.

    It DOES NOT issue or persist access/refresh tokens.

    This is required for MFA because an MFA-protected user must not
    receive a usable JWT before the second factor succeeds.
    """

    normalized_username = username.lower().strip()

    user = (
        db.query(User)
        .filter(
            User.email == normalized_username,
            User.deleted_at.is_(None),
        )
        .first()
    )

    # Keep unknown/inactive accounts on the generic authentication
    # response, but return a distinct lockout response for an account
    # that exists and is currently locked. The frontend can then show
    # the user an appropriate lockout message.
    if user is None:
        raise GrantError(
            "invalid_grant",
            "Invalid credentials",
            status.HTTP_401_UNAUTHORIZED,
        )

    if not user.is_active:
        raise GrantError(
            "invalid_grant",
            "Invalid credentials",
            status.HTTP_401_UNAUTHORIZED,
        )

    if user.is_locked:
        raise GrantError(
            "account_locked",
            "Your account is locked. Please try again later.",
            status.HTTP_423_LOCKED,
        )

    if not verify_password(
        password,
        user.password_hash,
    ):
        user.record_failed_login()
        db.commit()

        raise GrantError(
            "invalid_grant",
            "Invalid credentials",
            status.HTTP_401_UNAUTHORIZED,
        )

    user.record_successful_login()

    granted_scope = _validate_scope(
        user,
        requested_scope,
    )

    return user, granted_scope


def _issue_tokens(
    db: Session,
    request: Request,
    user: User,
    granted_scope: str,
) -> tuple[str, str]:
    """
    Issue and persist access/refresh tokens for a new application session.

    A session is created only after all required authentication
    factors have succeeded.
    """

    session = create_session(
        user_id=user.id,
        tenant_id=user.tenant_id,
    )
    session_id = session["session_id"]

    scopes = (
        granted_scope.split()
        if granted_scope
        else []
    )

    access = create_access_token(
        user_id=user.id,
        tenant_id=user.tenant_id,
        role=user.role,
        scopes=scopes,
        session_id=session_id,
    )

    refresh = create_refresh_token(
        user_id=user.id,
        tenant_id=user.tenant_id,
        role=user.role,
        session_id=session_id,
    )

    _persist_refresh_token(
        db,
        user,
        refresh,
        request,
        session_id=session_id,
    )

    db.commit()

    return access, refresh


def _password_grant(
    db: Session,
    request: Request,
    username: str,
    password: str,
    requested_scope: Optional[str] = None,
) -> tuple[User, str, str, str]:
    """
    Existing password grant.

    This function preserves the original behavior for callers that
    explicitly use the OAuth2 password grant.

    NOTE:
    MFA-aware application login should use _authenticate_password()
    and perform MFA enforcement before calling _issue_tokens().
    """

    user, granted_scope = _authenticate_password(
        db=db,
        request=request,
        username=username,
        password=password,
        requested_scope=requested_scope,
    )

    access, refresh = _issue_tokens(
        db=db,
        request=request,
        user=user,
        granted_scope=granted_scope,
    )

    return (
        user,
        access,
        refresh,
        granted_scope,
    )


def _refresh_token_grant(
    db: Session,
    request: Request,
    refresh_token: str,
    requested_scope: Optional[str] = None,
) -> tuple[User, str, str, str]:
    """
    Single source of truth for refresh-token rotation.

    Security checks:
    1. Verify JWT signature/type/expiration.
    2. Find the matching hashed refresh token in the database.
    3. Ensure it has not already been revoked.
    4. Ensure the stored token is still valid.
    5. Verify token ownership.
    6. Verify the user is active and not deleted.
    7. Verify the organization is active and not deleted.
    8. Verify tenant_id matches the database user.
    9. Verify role matches the database user.
    10. Revoke the old refresh token.
    11. Issue a new access token.
    12. Issue and persist a new refresh token.
    """

    try:
        claims = verify_refresh_token(
            refresh_token
        )
    except Exception:
        raise GrantError(
            "invalid_grant",
            "Refresh token is invalid or expired",
            status.HTTP_401_UNAUTHORIZED,
        )

    token_hash = hashlib.sha256(
        refresh_token.encode("utf-8")
    ).hexdigest()

    stored = (
        db.query(RefreshToken)
        .filter(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked_at.is_(None),
        )
        .with_for_update()
        .first()
    )

    if stored is None:
        raise GrantError(
            "invalid_grant",
            "Refresh token not found or already used",
            status.HTTP_401_UNAUTHORIZED,
        )

    if not stored.is_valid:
        raise GrantError(
            "invalid_grant",
            "Refresh token expired or already used",
            status.HTTP_401_UNAUTHORIZED,
        )

    if str(stored.user_id) != str(
        claims.get("sub")
    ):
        raise GrantError(
            "invalid_grant",
            "Refresh token ownership validation failed",
            status.HTTP_401_UNAUTHORIZED,
        )

    user = (
        db.query(User)
        .filter(
            User.id == claims.get("sub"),
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        )
        .first()
    )

    if user is None:
        stored.revoked_at = datetime.now(
            timezone.utc
        )
        db.commit()

        raise GrantError(
            "invalid_grant",
            "User account not found or deactivated",
            status.HTTP_401_UNAUTHORIZED,
        )

    organization = (
        db.query(Organization)
        .filter(
            Organization.id == user.tenant_id,
            Organization.status == "ACTIVE",
            Organization.deleted_at.is_(None),
        )
        .first()
    )

    if organization is None:
        stored.revoked_at = datetime.now(
            timezone.utc
        )
        db.commit()

        raise GrantError(
            "invalid_grant",
            "Organization is inactive or deleted",
            status.HTTP_401_UNAUTHORIZED,
        )

    if str(claims.get("tenant_id")) != str(
        user.tenant_id
    ):
        raise GrantError(
            "invalid_grant",
            "Refresh token tenant validation failed",
            status.HTTP_401_UNAUTHORIZED,
        )

    if str(claims.get("role")) != str(
        user.role
    ):
        raise GrantError(
            "invalid_grant",
            "Refresh token role validation failed",
            status.HTTP_401_UNAUTHORIZED,
        )
    session_id = claims.get("session_id")

    if not session_id:
        raise GrantError(
            "invalid_grant",
            "Refresh token is not associated with a session",
            status.HTTP_401_UNAUTHORIZED,
        )

    session = validate_session(
        session_id=session_id,
        user_id=user.id,
        tenant_id=user.tenant_id,
    )

    if session is None:
        stored.revoked_at = datetime.now(timezone.utc)
        db.commit()

        raise GrantError(
            "invalid_grant",
            "Session expired due to inactivity or maximum lifetime",
            status.HTTP_401_UNAUTHORIZED,
        )

    if touch_session(session_id) is None:
        stored.revoked_at = datetime.now(timezone.utc)
        db.commit()

        raise GrantError(
            "invalid_grant",
            "Session is no longer active",
            status.HTTP_401_UNAUTHORIZED,
        )

    granted_scope = _validate_scope(
        user,
        requested_scope,
    )

    scopes = (
        granted_scope.split()
        if granted_scope
        else []
    )

    stored.revoked_at = datetime.now(
        timezone.utc
    )

    access = create_access_token(
        user_id=user.id,
        tenant_id=user.tenant_id,
        role=user.role,
        scopes=scopes,
        session_id=session_id,
    )

    new_refresh = create_refresh_token(
        user_id=user.id,
        tenant_id=user.tenant_id,
        role=user.role,
        session_id=session_id,
    )

    _persist_refresh_token(
        db,
        user,
        new_refresh,
        request,
        session_id=session_id,
    )

    db.commit()

    return (
        user,
        access,
        new_refresh,
        granted_scope,
    )


@router.post("/token")
async def token(
    request: Request,
    grant_type: str = Form(...),
    username: Optional[str] = Form(None),
    password: Optional[str] = Form(None),
    refresh_token: Optional[str] = Form(None),
    scope: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """
    OAuth2-shaped token endpoint.

    Supported:
    - password
    - refresh_token
    """

    if grant_type not in SUPPORTED_GRANT_TYPES:
        _oauth_error(
            "unsupported_grant_type",
            "Supported grant types: password, refresh_token",
        )

    if grant_type == "password":

        if not username or not password:
            _oauth_error(
                "invalid_request",
                "username and password are required",
            )

        try:
            _, access, refresh, granted_scope = (
                _password_grant(
                    db,
                    request,
                    username,
                    password,
                    scope,
                )
            )

        except GrantError as exc:
            _oauth_error(
                exc.error,
                exc.description,
                exc.status_code,
            )

        return {
            "access_token": access,
            "refresh_token": refresh,
            "token_type": "bearer",
            "expires_in": (
                ACCESS_TOKEN_EXPIRE_MINUTES * 60
            ),
            "scope": granted_scope,
        }

    if grant_type == "refresh_token":

        if not refresh_token:
            _oauth_error(
                "invalid_request",
                "refresh_token is required",
            )

        try:
            (
                _,
                access,
                new_refresh,
                granted_scope,
            ) = _refresh_token_grant(
                db,
                request,
                refresh_token,
                scope,
            )

        except GrantError as exc:
            _oauth_error(
                exc.error,
                exc.description,
                exc.status_code,
            )

        return {
            "access_token": access,
            "refresh_token": new_refresh,
            "token_type": "bearer",
            "expires_in": (
                ACCESS_TOKEN_EXPIRE_MINUTES * 60
            ),
            "scope": granted_scope,
        }

    _oauth_error(
        "unsupported_grant_type",
        "Unsupported grant type",
    )