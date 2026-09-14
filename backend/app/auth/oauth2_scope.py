"""
OAuth2 scope definitions and role-based scope enforcement.
"""

from ..auth.rbac import UserRole


SUPPORTED_SCOPES: set[str] = {
    "jobs:read",
    "jobs:write",
    "dispatch:read",
    "profile:read",
}


ROLE_SCOPES: dict[UserRole, set[str]] = {
    UserRole.HEAD: {
        "profile:read",
        "dispatch:read",
    },

    UserRole.SUPER_ADMIN: {
        "jobs:read",
        "jobs:write",
        "dispatch:read",
        "profile:read",
    },

    UserRole.DISPATCHER: {
        "jobs:read",
        "jobs:write",
        "dispatch:read",
        "profile:read",
    },

    UserRole.TECHNICIAN: {
        "jobs:read",
        "profile:read",
    },

    UserRole.CUSTOMER: {
        "jobs:read",
        "profile:read",
    },
}


def parse_scope(scope: str | None) -> set[str]:
    if not scope:
        return set()

    return {
        item.strip()
        for item in scope.split()
        if item.strip()
    }


def scopes_for_role(role: UserRole) -> set[str]:
    return ROLE_SCOPES.get(role, set()).copy()


def validate_requested_scope(
    role: UserRole,
    requested_scope: str | None,
) -> str:
    """
    Validate and narrow the requested scope.

    The client can only receive scopes that are both supported
    and permitted for its server-side role. Unsupported or
    forbidden scopes are removed rather than trusted.
    """

    if not requested_scope:
        return ""

    requested = parse_scope(requested_scope)
    allowed = scopes_for_role(role)

    # Grant only scopes that are supported and allowed for the role.
    granted = requested & SUPPORTED_SCOPES & allowed

    return " ".join(sorted(granted))


def default_scope_for_role(role: UserRole) -> str:
    return " ".join(sorted(scopes_for_role(role)))