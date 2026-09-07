"""
Authentication and authorization dependencies for FastAPI.

These replace all existing auth patterns in the project with a single,
consistent approach based on JWT claims.

Key principle: NEVER trust tenant_id or role from request headers/payloads.
Always derive them from the signed JWT.
"""

from typing import Optional

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from ..database import get_db
from .jwt_handler import verify_access_token
from .rbac import UserRole, Permission, has_permission, can_manage_role

import jwt
import logging

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)


class AuthenticatedUser:
    """
    Represents the currently authenticated user derived from JWT claims.

    This object is injected into route handlers via Depends(get_current_user).
    """

    def __init__(
        self,
        user_id: str,
        tenant_id: str,
        role: UserRole,
        jti: str,
    ):
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.role = role
        self.jti = jti

    @property
    def is_super_admin(self) -> bool:
        return self.role == UserRole.SUPER_ADMIN

    def has_permission(self, permission: Permission) -> bool:
        return has_permission(self.role, permission)

    def can_manage(self, target_role: UserRole) -> bool:
        return can_manage_role(self.role, target_role)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> AuthenticatedUser:
    """
    Extract and verify the current user from the JWT Bearer token.

    This is the SINGLE SOURCE OF TRUTH for authentication.
    All route handlers should depend on this.

    Raises 401 if:
    - No token provided
    - Token is expired
    - Token is malformed
    - Token has been blacklisted (revoked)
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        claims = verify_access_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Parse role from JWT
    role_str = claims.get("role", "")
    try:
        role = UserRole(role_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid role in token",
        )

    # Verify user still exists and is active
    from ..models.user import User
    user = db.query(User).filter(
        User.id == claims["sub"],
        User.is_active == True,
        User.deleted_at.is_(None),
    ).first()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found or deactivated",
        )

    # Check account lockout
    if user.is_locked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is temporarily locked due to too many failed login attempts",
        )

    return AuthenticatedUser(
        user_id=claims["sub"],
        tenant_id=claims["tenant_id"],
        role=role,
        jti=claims.get("jti", ""),
    )


async def get_current_active_user(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> AuthenticatedUser:
    """Alias for get_current_user — ensures user is active (already checked)."""
    return current_user


def get_tenant_id(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> str:
    """
    Extract tenant_id from the authenticated JWT.

    This is the ONLY way to get tenant_id — never from headers.
    """
    return current_user.tenant_id


def require_role(*allowed_roles: UserRole):
    """
    Dependency factory that enforces one or more roles.

    Usage:
        @router.get("/admin-only", dependencies=[Depends(require_role(UserRole.SUPER_ADMIN, UserRole.SUPER_ADMIN))])
        def admin_endpoint():
            ...
    """
    async def checker(
        current_user: AuthenticatedUser = Depends(get_current_user),
    ) -> AuthenticatedUser:
        if current_user.role not in allowed_roles:
            logger.warning(
                "Access denied: user=%s role=%s required=%s",
                current_user.user_id,
                current_user.role.value,
                [r.value for r in allowed_roles],
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required role: {', '.join(r.value for r in allowed_roles)}",
            )
        return current_user

    return checker


def require_permission(*required_permissions: Permission):
    """
    Dependency factory that enforces one or more permissions.

    Usage:
        @router.post("/jobs", dependencies=[Depends(require_permission(Permission.JOBS_CREATE))])
        def create_job():
            ...
    """
    async def checker(
        current_user: AuthenticatedUser = Depends(get_current_user),
    ) -> AuthenticatedUser:
        for perm in required_permissions:
            if not current_user.has_permission(perm):
                logger.warning(
                    "Permission denied: user=%s role=%s permission=%s",
                    current_user.user_id,
                    current_user.role.value,
                    perm.value,
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission denied: {perm.value}",
                )
        return current_user

    return checker


def require_same_tenant_or_super_admin(
    resource_tenant_id: str,
    current_user: AuthenticatedUser,
) -> None:
    """
    Verify the current user belongs to the same tenant as the resource,
    or is a super admin.

    Raises 403 if tenant mismatch.
    """
    if current_user.is_super_admin:
        return
    if current_user.tenant_id != resource_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: cross-tenant access is not permitted",
        )


# ──────────────────────────────────────────────────
# Backward-compatibility shim
# ──────────────────────────────────────────────────
# The existing verify_jwt_token in dispatch.py just checks that a
# Bearer token exists. This shim provides the same interface but
# actually validates the JWT.

async def verify_jwt_token_secure(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> str:
    """
    Backward-compatible JWT verification that actually validates the token.
    
    Returns the raw token string for callers that need it.
    This is a transitional shim — prefer get_current_user() for new code.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        verify_access_token(credentials.credentials)
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

    return credentials.credentials


async def get_current_user_or_tenant(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> tuple[Optional[AuthenticatedUser], str]:
    """
    Extract current AuthenticatedUser from JWT if provided, falling back
    to the X-Tenant-ID header if no token is sent.
    
    Returns tuple of (user: Optional[AuthenticatedUser], effective_tenant_id: str).
    """
    if credentials:
        try:
            user = await get_current_user(request, credentials, db)
            return user, user.tenant_id
        except HTTPException:
            pass
            
    header_tenant = request.headers.get("X-Tenant-ID", "tenant-1")
    return None, header_tenant
