from __future__ import annotations

from dataclasses import dataclass

from fastapi import (
    Depends,
    HTTPException,
    status,
)

from app.auth.dependencies import (
    AuthenticatedUser,
    get_current_user_or_tenant,
)


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


def require_prompt_admin(
    user_tenant: tuple[AuthenticatedUser, str] = Depends(
        get_current_user_or_tenant
    ),
) -> PromptAdminPrincipal:
    """
    Verify the authenticated user and return the trusted
    prompt-admin principal.

    Tenant, actor, and role are taken from the verified
    authentication context.
    """

    user, tenant_id = user_tenant

    actor_id = str(user.user_id).strip()
    role = user.role.value.lower()
    tenant_id = str(tenant_id).strip()

    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Authentication context is missing tenant information.",
        )

    if not actor_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Authentication context is missing user information.",
        )

    if role not in ALLOWED_PROMPT_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions.",
        )

    # Platform templates require super_admin.
    if (
        tenant_id == "**platform**"
        and role != "super_admin"
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Only a super administrator may "
                "manage platform templates."
            ),
        )

    return PromptAdminPrincipal(
        actor_id=actor_id,
        role=role,
        tenant_id=tenant_id,
    )