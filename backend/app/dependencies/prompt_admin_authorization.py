from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any, Optional

import jwt
from fastapi import (
    Depends,
    Header,
    HTTPException,
    status,
)

from app.routes.dispatch import verify_jwt_token


ALLOWED_PROMPT_ROLES = {
    "admin",
    "manager",
    "tenant_admin",
    "super_admin",
}


@dataclass(frozen=True)
class PromptAdminPrincipal:
    """
    Authenticated administrator allowed to manage prompts.
    """

    actor_id: str
    role: str
    tenant_id: str


def _normalize_roles(
    raw_roles: Any,
) -> set[str]:
    """
    Normalize JWT or header roles.

    Supported formats:

    roles = ["admin", "manager"]
    roles = "admin"
    roles = "admin,manager"
    """

    if isinstance(raw_roles, str):
        role_items = raw_roles.split(",")

    elif isinstance(
        raw_roles,
        (list, tuple, set),
    ):
        role_items = raw_roles

    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token contains invalid roles.",
        )

    normalized_roles: set[str] = set()

    for role in role_items:
        if not isinstance(role, str):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Token contains invalid roles.",
            )

        normalized = role.strip().lower()

        if normalized:
            normalized_roles.add(normalized)

    if not normalized_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token contains no roles.",
        )

    return normalized_roles


def require_prompt_admin(
    x_tenant_id: Optional[str] = Header(
        default=None,
        alias="X-Tenant-ID",
    ),
    x_user_id: Optional[str] = Header(
        default=None,
        alias="X-User-ID",
    ),
    x_permissions: Optional[str] = Header(
        default=None,
        alias="X-Permissions",
    ),
    token: str = Depends(
        verify_jwt_token
    ),
) -> PromptAdminPrincipal:
    """
    Verify the JWT and return the trusted prompt-admin principal.

    Tenant, actor, and roles are taken from signed JWT claims.

    Optional headers are consistency checks only. They cannot
    grant additional access.
    """

    jwt_secret = os.getenv(
        "JWT_SECRET",
        "",
    ).strip()

    jwt_algorithm = os.getenv(
        "JWT_ALGORITHM",
        "HS256",
    ).strip()

    if not jwt_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable.",
        )

    # Only the approved algorithm is accepted.
    if jwt_algorithm != "HS256":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable.",
        )

    try:
        claims = jwt.decode(
            token,
            jwt_secret,
            algorithms=[jwt_algorithm],
            options={
                "require": [
                    "exp",
                ],
            },
        )

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired.",
        ) from None

    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token.",
        ) from None

    claim_tenant = str(
        claims.get(
            "tenant_id",
            "",
        )
    ).strip()

    claim_user = str(
        claims.get(
            "sub",
            claims.get(
                "user_id",
                "",
            ),
        )
    ).strip()

    if not claim_tenant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token is missing tenant information.",
        )

    if not claim_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token is missing user information.",
        )

    claim_roles = _normalize_roles(
        claims.get("roles")
    )

    permitted_roles = (
        claim_roles
        & ALLOWED_PROMPT_ROLES
    )

    if not permitted_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions.",
        )

    # Optional tenant header must match the signed JWT claim.
    if (
        x_tenant_id is not None
        and x_tenant_id.strip()
        != claim_tenant
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant header does not match token.",
        )

    # Optional user header must match the signed JWT claim.
    if (
        x_user_id is not None
        and x_user_id.strip()
        != claim_user
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User header does not match token.",
        )

    # Permissions header cannot grant a role missing from JWT.
    if x_permissions is not None:
        header_roles = _normalize_roles(
            x_permissions
        )

        if not header_roles.issubset(
            claim_roles
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Permission header does not "
                    "match token."
                ),
            )

    # Platform templates require super_admin.
    if (
        claim_tenant == "**platform**"
        and "super_admin"
        not in claim_roles
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Only a super administrator may "
                "manage platform templates."
            ),
        )

    role_priority = (
        "super_admin",
        "tenant_admin",
        "admin",
        "manager",
    )

    selected_role = next(
        role
        for role in role_priority
        if role in permitted_roles
    )

    return PromptAdminPrincipal(
        actor_id=claim_user,
        role=selected_role,
        tenant_id=claim_tenant,
    )