
"""
Authentication and authorization dependencies for FastAPI.

These provide a single, consistent authentication approach based
on verified JWT claims.

Key principles:
- NEVER trust tenant_id or role from request headers/payloads.
- Always derive tenant and role from the signed JWT/database.
- Bearer authentication remains supported.
- Browser SSO authentication can use the secure HttpOnly cookie.
"""

from typing import Optional

import jwt
import logging

from fastapi import (
    Depends,
    HTTPException,
    Request,
    status,
)
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
    OAuth2PasswordBearer,
)
from sqlalchemy.orm import Session

from ..database import get_db
from .jwt_handler import verify_access_token
from .rbac import (
    Permission,
    UserRole,
    can_manage_role,
    has_permission,
)

from .session_service import validate_session, touch_session

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/oauth2/token",
    auto_error=False,
)

# Cookie used by browser-based SSO.
SSO_ACCESS_COOKIE = "fieldops_access_token"


class AuthenticatedUser:
    """
    Represents the currently authenticated user derived
    from verified JWT claims and the database.

    This object is injected into route handlers via
    Depends(get_current_user).
    """

    def __init__(
        self,
        user_id: str,
        tenant_id: str,
        role: UserRole,
        jti: str,
        session_id: str,
    ):
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.role = role
        self.jti = jti
        self.session_id = session_id

    @property
    def is_super_admin(self) -> bool:
        return self.role == UserRole.SUPER_ADMIN

    def has_permission(
        self,
        permission: Permission,
    ) -> bool:
        return has_permission(
            self.role,
            permission,
        )

    def can_manage(
        self,
        target_role: UserRole,
    ) -> bool:
        return can_manage_role(
            self.role,
            target_role,
        )


def _get_access_token(
    request: Request,
    credentials: Optional[
        HTTPAuthorizationCredentials
    ],
) -> Optional[str]:
    """
    Get the access token from either:

    1. Authorization: Bearer <token>
    2. Secure SSO HttpOnly cookie

    Bearer authentication has priority so existing API clients
    continue working exactly as before.

    The cookie is used for browser-based SSO sessions.
    """

    # ---------------------------------------------------------
    # 1. Existing Bearer token
    # ---------------------------------------------------------
    if credentials is not None:
        return credentials.credentials

    # ---------------------------------------------------------
    # 2. Browser SSO cookie
    # ---------------------------------------------------------
    return request.cookies.get(
        SSO_ACCESS_COOKIE
    )


async def get_current_user(
    request: Request,
    credentials: Optional[
        HTTPAuthorizationCredentials
    ] = Depends(security),
    db: Session = Depends(get_db),
) -> AuthenticatedUser:
    """
    Extract and verify the current user from a JWT.

    Authentication sources:
    - Authorization Bearer token
    - fieldops_access_token HttpOnly cookie

    The JWT is always verified before the user is accepted.

    Raises 401 if:
    - no token is provided
    - token is expired
    - token is malformed
    - token has been blacklisted/revoked
    - user no longer exists
    - user is inactive
    - token role no longer matches database
    - token tenant no longer matches database
    """

    token = _get_access_token(
        request=request,
        credentials=credentials,
    )

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={
                "WWW-Authenticate": "Bearer"
            },
        )

    try:
        claims = verify_access_token(token)

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={
                "WWW-Authenticate": "Bearer"
            },
        )

    except jwt.InvalidTokenError as exc:
        logger.warning(
            "Access token validation failed: %s",
            str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={
                "WWW-Authenticate": "Bearer"
            },
        )

    # ---------------------------------------------------------
    # Parse role from JWT
    # ---------------------------------------------------------
    role_str = claims.get(
        "role",
        "",
    )

    try:
        token_role = UserRole(role_str)

    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid role in token",
            headers={
                "WWW-Authenticate": "Bearer"
            },
        )

    # ---------------------------------------------------------
    # Parse subject/user ID
    # ---------------------------------------------------------
    subject = claims.get("sub")

    if not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token subject is missing",
            headers={
                "WWW-Authenticate": "Bearer"
            },
        )

    # ---------------------------------------------------------
    # Verify user still exists and is active
    # ---------------------------------------------------------
    from ..models.user import User

    user = (
        db.query(User)
        .filter(
            User.id == subject,
            User.is_active == True,
            User.deleted_at.is_(None),
        )
        .first()
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found or deactivated",
        )

    # ---------------------------------------------------------
    # Check account lockout
    # ---------------------------------------------------------
    if user.is_locked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Account is temporarily locked due to "
                "too many failed login attempts"
            ),
        )

    # ---------------------------------------------------------
    # Server-side role is authoritative.
    #
    # This prevents a modified JWT role from granting
    # unauthorized permissions.
    # ---------------------------------------------------------
    try:
        db_role = UserRole(user.role)

    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user role",
            headers={
                "WWW-Authenticate": "Bearer"
            },
        )

    if token_role != db_role:
        logger.warning(
            "Role mismatch: user=%s token_role=%s db_role=%s",
            user.id,
            token_role.value,
            db_role.value,
        )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token role is no longer valid",
            headers={
                "WWW-Authenticate": "Bearer"
            },
        )

    # ---------------------------------------------------------
    # Server-side tenant is authoritative.
    # ---------------------------------------------------------
    token_tenant_id = str(
        claims.get(
            "tenant_id",
            "",
        )
    )

    database_tenant_id = str(
        user.tenant_id
    )

    if token_tenant_id != database_tenant_id:
        logger.warning(
            "Tenant claim mismatch: "
            "user=%s token_tenant=%s db_tenant=%s",
            user.id,
            token_tenant_id,
            database_tenant_id,
        )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token tenant is no longer valid",
            headers={
                "WWW-Authenticate": "Bearer"
            },
        )
    session_id = claims.get("session_id")

    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session is invalid or expired",
            headers={
                "WWW-Authenticate": "Bearer"
            },
        )

    session = validate_session(
        session_id=session_id,
        user_id=str(user.id),
        tenant_id=str(user.tenant_id),
    )

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired due to inactivity or maximum lifetime",
            headers={
                "WWW-Authenticate": "Bearer"
            },
        )

    if touch_session(session_id) is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session is no longer active",
            headers={
                "WWW-Authenticate": "Bearer"
            },
        )

    # ---------------------------------------------------------
    # Return authenticated FieldOps identity.
    # ---------------------------------------------------------
    return AuthenticatedUser(
        user_id=str(claims["sub"]),
        tenant_id=user.tenant_id,
        role=db_role,
        jti=claims.get("jti", ""),
        session_id=str(session_id),
    )


async def get_current_active_user(
    current_user: AuthenticatedUser = Depends(
        get_current_user
    ),
) -> AuthenticatedUser:
    """
    Alias for get_current_user.

    User activity is already checked inside get_current_user.
    """

    return current_user


def get_tenant_id(
    current_user: AuthenticatedUser = Depends(
        get_current_user
    ),
) -> str:
    """
    Extract tenant_id from the authenticated identity.

    Never use tenant_id from request headers.
    """

    return current_user.tenant_id


def require_role(
    *allowed_roles: UserRole,
):
    """
    Dependency factory that enforces one or more roles.

    Example:

        @router.get(
            "/admin-only",
            dependencies=[
                Depends(
                    require_role(
                        UserRole.SUPER_ADMIN
                    )
                )
            ],
        )
    """

    async def checker(
        current_user: AuthenticatedUser = Depends(
            get_current_user
        ),
    ) -> AuthenticatedUser:

        if current_user.role not in allowed_roles:
            logger.warning(
                "Access denied: user=%s role=%s required=%s",
                current_user.user_id,
                current_user.role.value,
                [
                    role.value
                    for role in allowed_roles
                ],
            )

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Insufficient permissions. "
                    "Required role: "
                    + ", ".join(
                        role.value
                        for role in allowed_roles
                    )
                ),
            )

        return current_user

    return checker


def require_permission(
    *required_permissions: Permission,
):
    """
    Dependency factory that enforces one or more permissions.

    Example:

        @router.post(
            "/jobs",
            dependencies=[
                Depends(
                    require_permission(
                        Permission.JOBS_CREATE
                    )
                )
            ],
        )
    """

    async def checker(
        current_user: AuthenticatedUser = Depends(
            get_current_user
        ),
    ) -> AuthenticatedUser:

        for permission in required_permissions:

            if not current_user.has_permission(
                permission
            ):
                logger.warning(
                    "Permission denied: "
                    "user=%s role=%s permission=%s",
                    current_user.user_id,
                    current_user.role.value,
                    permission.value,
                )

                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        "Permission denied: "
                        f"{permission.value}"
                    ),
                )

        return current_user

    return checker


def require_same_tenant_or_super_admin(
    resource_tenant_id: str,
    current_user: AuthenticatedUser,
) -> None:
    """
    Verify the current user belongs to the same tenant
    as the resource, or is a super admin.

    Raises 403 on cross-tenant access.
    """

    if current_user.is_super_admin:
        return

    if (
        current_user.tenant_id
        != resource_tenant_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Access denied: "
                "cross-tenant access is not permitted"
            ),
        )


# ──────────────────────────────────────────────────
# Backward-compatibility shim
# ──────────────────────────────────────────────────

async def verify_jwt_token_secure(
    request: Request,
    credentials: Optional[
        HTTPAuthorizationCredentials
    ] = Depends(security),
) -> str:
    """
    Backward-compatible JWT verification.

    Supports:
    - Authorization Bearer token
    - SSO HttpOnly cookie

    Returns the raw verified token.
    """

    token = _get_access_token(
        request=request,
        credentials=credentials,
    )

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization required",
            headers={
                "WWW-Authenticate": "Bearer"
            },
        ) 

    try:
        verify_access_token(token)

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )

    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    return token


async def get_current_user_or_tenant(
    request: Request,
    credentials: Optional[
        HTTPAuthorizationCredentials
    ] = Depends(security),
    db: Session = Depends(get_db),
) -> tuple[AuthenticatedUser, str]:
    """
    Return the authenticated user and their tenant.

    Tenant is ALWAYS derived from the authenticated
    FieldOps identity.

    X-Tenant-ID must never be used as an authentication
    or authorization fallback.
    """

    user = await get_current_user(
        request=request,
        credentials=credentials,
        db=db,
    )

    return user, user.tenant_id

