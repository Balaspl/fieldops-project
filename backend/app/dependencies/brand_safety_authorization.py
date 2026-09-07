"""
brand_safety_authorization.py

Authentication and authorization dependencies for AI
brand-safety administration routes.

Current FieldOps authentication model
-------------------------------------
- Authorization: Bearer <token>
- X-User-ID: trusted actor identifier
- X-Permissions: trusted actor role
- X-Tenant-ID: trusted tenant identifier

In production, X-User-ID, role, and tenant information should
eventually come from verified JWT claims or a trusted API
gateway.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import (
    Depends,
    HTTPException,
    status,
)

from app.auth.dependencies import (
    AuthenticatedUser,
    get_current_user_or_tenant,
)


ALLOWED_BRAND_SAFETY_ROLES = frozenset(
    {
        "admin",
        "manager",
        "tenant_admin",
        "super_admin",
    }
)


@dataclass(
    frozen=True,
    slots=True,
)
class BrandSafetyAdminPrincipal:
    """
    Authenticated administrator performing the operation.
    """

    actor_id: str
    role: str


def get_trusted_tenant_id(
    user_tenant: tuple[AuthenticatedUser, str] = Depends(
        get_current_user_or_tenant
    ),
) -> str:
    """
    Get the tenant ID from the verified JWT/current user.
    """

    _, tenant_id = user_tenant

    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant ID must not be empty.",
        )

    return tenant_id


def require_brand_safety_admin(
    user_tenant: tuple[AuthenticatedUser, str] = Depends(
        get_current_user_or_tenant
    ),
) -> BrandSafetyAdminPrincipal:
    """
    Require an authenticated administrator or manager.

    The bearer token is validated by the existing FieldOps
    verify_jwt_token dependency.

    The raw bearer token is deliberately not stored as the actor
    ID because authentication tokens are secrets.
    """

    user, _ = user_tenant

    actor_id = user.user_id
    role = user.role.value.lower()

    if not actor_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-User-ID must not be empty.",
        )

    if role not in ALLOWED_BRAND_SAFETY_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Brand-safety administration requires an "
                "admin, manager, tenant_admin, or super_admin "
                "role."
            ),
        )

    return BrandSafetyAdminPrincipal(
        actor_id=actor_id,
        role=role,
    )