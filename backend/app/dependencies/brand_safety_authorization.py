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
    Header,
    HTTPException,
    status,
)

from app.routes.dispatch import verify_jwt_token


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
    x_tenant_id: Annotated[
        str,
        Header(
            alias="X-Tenant-ID",
            min_length=1,
            max_length=50,
        ),
    ],
) -> str:
    """
    Read and normalize the trusted tenant header.
    """

    tenant_id = x_tenant_id.strip()

    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Tenant-ID must not be empty.",
        )

    return tenant_id


def require_brand_safety_admin(
    authorization: Annotated[
        str,
        Depends(verify_jwt_token),
    ],
    x_user_id: Annotated[
        str,
        Header(
            alias="X-User-ID",
            min_length=1,
            max_length=100,
        ),
    ],
    x_permissions: Annotated[
        str,
        Header(
            alias="X-Permissions",
            min_length=1,
            max_length=50,
        ),
    ],
) -> BrandSafetyAdminPrincipal:
    """
    Require an authenticated administrator or manager.

    The bearer token is validated by the existing FieldOps
    verify_jwt_token dependency.

    The raw bearer token is deliberately not stored as the actor
    ID because authentication tokens are secrets.
    """

    _ = authorization

    actor_id = x_user_id.strip()
    role = x_permissions.strip().lower()

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