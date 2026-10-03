
"""
Resource-level object authorization for FieldOps.

This module provides reusable authorization checks that must be
performed AFTER authentication and RBAC permission checks.

Authorization order:

    1. Authenticate user
    2. Check RBAC permission
    3. Load resource
    4. Verify resource is active
    5. Verify tenant ownership
    6. Verify resource ownership / assignment
    7. Allow or deny

Security goals:

- Prevent IDOR (Insecure Direct Object Reference).
- Prevent cross-tenant access.
- Prevent horizontal privilege escalation.
- Prevent vertical privilege escalation.
- Never trust tenant IDs supplied by clients.
- Do not reveal whether another tenant's resource exists.
- Fail closed when ownership cannot be established.

IMPORTANT:

These functions do NOT replace RBAC.

Example:

    require_permission(Permission.JOBS_VIEW_ALL)

must still be applied to the route.

Then:

    authorize_job_access(current_user, job)

performs resource-level authorization.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import HTTPException, status

from .dependencies import AuthenticatedUser
from .rbac import UserRole


logger = logging.getLogger(__name__)


# ============================================================
# Authorization errors
# ============================================================

def _access_denied(resource: str) -> HTTPException:
    """
    Generic authorization error.

    Do not reveal whether the requested resource exists in
    another tenant or belongs to another user.
    """

    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Access denied to {resource}.",
    )


def _not_found(resource: str) -> HTTPException:
    """
    Generic not-found response.

    Used when exposing the existence of a resource would create
    an information leak.
    """

    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"{resource.capitalize()} not found.",
    )


# ============================================================
# Generic helpers
# ============================================================

def _get_value(
    resource: Any,
    *field_names: str,
) -> Any:
    """
    Return the first existing attribute from a resource.

    Works with SQLAlchemy models and simple test doubles.
    """

    if resource is None:
        return None

    for field_name in field_names:
        if hasattr(resource, field_name):
            value = getattr(resource, field_name)

            if value is not None:
                return value

    return None


def _is_deleted(resource: Any) -> bool:
    """
    Determine whether a resource has been soft deleted.

    Resources without deleted_at are considered active.
    """

    if resource is None:
        return False

    deleted_at = _get_value(
        resource,
        "deleted_at",
    )

    return deleted_at is not None


def _tenant_id(resource: Any) -> Optional[str]:
    """
    Extract the tenant/organization ID from a resource.

    Supported names:

        tenant_id
        organization_id
    """

    value = _get_value(
        resource,
        "tenant_id",
        "organization_id",
    )

    if value is None:
        return None

    return str(value)


def _belongs_to_current_tenant(
    resource: Any,
    current_user: AuthenticatedUser,
) -> bool:
    """
    Verify that the resource belongs to the authenticated
    user's tenant.

    The tenant comes ONLY from AuthenticatedUser.

    Never use:

        request.headers["X-Tenant-ID"]

    or:

        request body tenant_id
    """

    resource_tenant = _tenant_id(resource)

    if resource_tenant is None:
        return False

    return resource_tenant == str(
        current_user.tenant_id
    )


def _require_active_resource(
    resource: Any,
    resource_name: str,
) -> None:
    """
    Require that a resource exists and is not soft deleted.
    """

    if resource is None:
        raise _not_found(resource_name)

    if _is_deleted(resource):
        raise _not_found(resource_name)


def _require_same_tenant(
    resource: Any,
    current_user: AuthenticatedUser,
    resource_name: str,
) -> None:
    """
    Require the resource to belong to the authenticated tenant.
    """

    if _belongs_to_current_tenant(
        resource,
        current_user,
    ):
        return

    logger.warning(
        "Cross-tenant object access denied: "
        "user=%s role=%s tenant=%s resource=%s",
        current_user.user_id,
        current_user.role.value,
        current_user.tenant_id,
        resource_name,
    )

    raise _access_denied(resource_name)


# ============================================================
# Organization authorization
# ============================================================

def authorize_organization_access(
    current_user: AuthenticatedUser,
    organization: Any,
    *,
    allow_head: bool = False,
) -> Any:
    """
    Authorize access to an organization.

    Rules:

    HEAD:
        Can access organization only when allow_head=True.

    SUPER_ADMIN:
        Only their own organization.

    DISPATCHER:
        Only their own organization.

    TECHNICIAN:
        Only their own organization.

    CUSTOMER:
        Only their own organization.

    IMPORTANT:

    This function does NOT grant management permission.

    RBAC permission must be checked separately.
    """

    _require_active_resource(
        organization,
        "organization",
    )

    # HEAD is outside organization tenancy.
    if current_user.role == UserRole.HEAD:

        if allow_head:
            return organization

        raise _access_denied("organization")

    _require_same_tenant(
        organization,
        current_user,
        "organization",
    )

    return organization


# ============================================================
# User authorization
# ============================================================

def authorize_user_access(
    current_user: AuthenticatedUser,
    user: Any,
    *,
    allow_self: bool = True,
) -> Any:
    """
    Authorize access to a user account.

    Rules:

    - User must belong to the authenticated tenant.
    - A user may access their own account when allow_self=True.
    - HEAD does not automatically gain organization-user access.
    """

    _require_active_resource(
        user,
        "user",
    )

    if current_user.role == UserRole.HEAD:
        raise _access_denied("user")

    _require_same_tenant(
        user,
        current_user,
        "user",
    )

    user_id = _get_value(
        user,
        "id",
        "user_id",
    )

    if user_id is None:
        raise _access_denied("user")

    if (
        not allow_self
        and str(user_id) == str(current_user.user_id)
    ):
        raise _access_denied("user")

    return user


# ============================================================
# Job authorization
# ============================================================

def authorize_job_access(
    current_user: AuthenticatedUser,
    job: Any,
    *,
    allow_assigned_technician: bool = True,
    allow_customer: bool = True,
) -> Any:
    """
    Authorize access to a job.

    Rules:

    HEAD:
        Denied.

    SUPER_ADMIN:
        Same tenant.

    DISPATCHER:
        Same tenant.

    TECHNICIAN:
        Same tenant AND assigned to the job.

    CUSTOMER:
        Same tenant AND associated with the job.

    NOTE:

    RBAC permission must already have been checked.
    """

    _require_active_resource(
        job,
        "job",
    )

    if current_user.role == UserRole.HEAD:
        raise _access_denied("job")

    _require_same_tenant(
        job,
        current_user,
        "job",
    )

    # --------------------------------------------------------
    # Organization managers
    # --------------------------------------------------------

    if current_user.role in {
        UserRole.SUPER_ADMIN,
        UserRole.DISPATCHER,
    }:
        return job

    # --------------------------------------------------------
    # Technician
    # --------------------------------------------------------

    if current_user.role == UserRole.TECHNICIAN:

        if not allow_assigned_technician:
            raise _access_denied("job")

        assigned_technician_id = _get_value(
            job,
            "assigned_technician_id",
            "technician_id",
            "technician_user_id",
            "assigned_user_id",
        )

        if assigned_technician_id is None:
            raise _access_denied("job")

        # The job model uses assigned_technician_id as the
        # Technician table primary key. Therefore, if the
        # authenticated user ID is a User UUID, the route
        # should preferably resolve the Technician record
        # before calling this function.
        #
        # This comparison is retained for projects where
        # technician/user IDs are intentionally identical.
        if str(assigned_technician_id) != str(
            current_user.user_id
        ):
            raise _access_denied("job")

        return job

    # --------------------------------------------------------
    # Customer
    # --------------------------------------------------------

    if current_user.role == UserRole.CUSTOMER:

        if not allow_customer:
            raise _access_denied("job")

        customer_id = _get_value(
            job,
            "customer_id",
            "customer_user_id",
            "created_by_customer_id",
        )

        if customer_id is None:
            raise _access_denied("job")

        if str(customer_id) != str(
            current_user.user_id
        ):
            raise _access_denied("job")

        return job

    raise _access_denied("job")


# ============================================================
# Technician authorization
# ============================================================

def authorize_technician_access(
    current_user: AuthenticatedUser,
    technician: Any,
) -> Any:
    """
    Authorize access to a technician.

    Rules:

    SUPER_ADMIN:
        Same tenant.

    DISPATCHER:
        Same tenant.

    TECHNICIAN:
        Only their own technician record.

    CUSTOMER:
        Denied.

    HEAD:
        Denied.

    IMPORTANT:

    Technician model:

        technician_id -> integer database PK
        tech_id       -> UUID/string identifier

    technician_id MUST NOT automatically be treated as the
    authenticated User ID.

    The preferred ownership fields are:

        tech_id
        user_id

    """

    _require_active_resource(
        technician,
        "technician",
    )

    if current_user.role in {
        UserRole.HEAD,
        UserRole.CUSTOMER,
    }:
        raise _access_denied("technician")

    _require_same_tenant(
        technician,
        current_user,
        "technician",
    )

    # --------------------------------------------------------
    # Technician's own record
    # --------------------------------------------------------

    if current_user.role == UserRole.TECHNICIAN:

        # IMPORTANT:
        #
        # Your Technician model has:
        #
        # technician_id = Integer primary key
        # tech_id = String UUID
        #
        # Therefore prefer tech_id/user_id.
        technician_user_id = _get_value(
            technician,
            "tech_id",
            "user_id",
        )

        if technician_user_id is None:
            raise _access_denied("technician")

        if str(technician_user_id) != str(
            current_user.user_id
        ):
            raise _access_denied("technician")

    return technician


# ============================================================
# Customer authorization
# ============================================================

def authorize_customer_access(
    current_user: AuthenticatedUser,
    customer: Any,
) -> Any:
    """
    Authorize access to a customer resource.

    Rules:

    SUPER_ADMIN:
        Same tenant.

    DISPATCHER:
        Same tenant.

    CUSTOMER:
        Own customer record only.

    TECHNICIAN:
        Denied by default.

    HEAD:
        Denied.
    """

    _require_active_resource(
        customer,
        "customer",
    )

    if current_user.role in {
        UserRole.HEAD,
        UserRole.TECHNICIAN,
    }:
        raise _access_denied("customer")

    _require_same_tenant(
        customer,
        current_user,
        "customer",
    )

    if current_user.role == UserRole.CUSTOMER:

        customer_id = _get_value(
            customer,
            "user_id",
            "customer_id",
            "id",
        )

        if customer_id is None:
            raise _access_denied("customer")

        if str(customer_id) != str(
            current_user.user_id
        ):
            raise _access_denied("customer")

    return customer


# ============================================================
# Invoice authorization
# ============================================================

def authorize_invoice_access(
    current_user: AuthenticatedUser,
    invoice: Any,
) -> Any:
    """
    Authorize access to an invoice.

    Rules:

    SUPER_ADMIN:
        Same tenant.

    DISPATCHER:
        Same tenant.

    CUSTOMER:
        Only their own invoice.

    TECHNICIAN:
        Denied.

    HEAD:
        Denied.
    """

    _require_active_resource(
        invoice,
        "invoice",
    )

    if current_user.role in {
        UserRole.HEAD,
        UserRole.TECHNICIAN,
    }:
        raise _access_denied("invoice")

    _require_same_tenant(
        invoice,
        current_user,
        "invoice",
    )

    if current_user.role == UserRole.CUSTOMER:

        customer_id = _get_value(
            invoice,
            "customer_id",
            "customer_user_id",
            "user_id",
        )

        if customer_id is None:
            raise _access_denied("invoice")

        if str(customer_id) != str(
            current_user.user_id
        ):
            raise _access_denied("invoice")

    return invoice


# ============================================================
# Generic resource authorization
# ============================================================

def authorize_resource_access(
    current_user: AuthenticatedUser,
    resource: Any,
    resource_name: str,
    *,
    owner_fields: tuple[str, ...] = (
        "user_id",
        "owner_id",
        "customer_id",
    ),
    allow_roles: Optional[set[UserRole]] = None,
) -> Any:
    """
    Generic fail-closed resource authorization.

    Rules:

    1. Resource must exist.
    2. Resource must not be deleted.
    3. HEAD is denied unless explicitly allowed.
    4. Resource must belong to authenticated tenant.
    5. Manager roles can access tenant resources.
    6. Other roles must own the resource.
    7. Missing ownership information means DENY.
    """

    _require_active_resource(
        resource,
        resource_name,
    )

    # --------------------------------------------------------
    # Explicitly allowed tenant-level roles
    # --------------------------------------------------------

    if allow_roles is not None:

        if current_user.role in allow_roles:

            if current_user.role == UserRole.HEAD:
                raise _access_denied(resource_name)

            _require_same_tenant(
                resource,
                current_user,
                resource_name,
            )

            return resource

    # --------------------------------------------------------
    # HEAD cannot access organization resources implicitly
    # --------------------------------------------------------

    if current_user.role == UserRole.HEAD:
        raise _access_denied(resource_name)

    # --------------------------------------------------------
    # Tenant isolation
    # --------------------------------------------------------

    _require_same_tenant(
        resource,
        current_user,
        resource_name,
    )

    # --------------------------------------------------------
    # Ownership
    # --------------------------------------------------------

    owner_id = _get_value(
        resource,
        *owner_fields,
    )

    if owner_id is None:
        raise _access_denied(resource_name)

    if str(owner_id) != str(
        current_user.user_id
    ):
        raise _access_denied(resource_name)

    return resource


# ============================================================
# Resource mutation authorization
# ============================================================

def authorize_resource_mutation(
    current_user: AuthenticatedUser,
    resource: Any,
    resource_name: str,
    *,
    owner_fields: tuple[str, ...] = (
        "user_id",
        "owner_id",
        "customer_id",
    ),
    manager_roles: Optional[set[UserRole]] = None,
) -> Any:
    """
    Authorize a mutation against an existing resource.

    Default manager roles:

        SUPER_ADMIN
        DISPATCHER

    Managers:

        tenant-level mutation

    Other users:

        owner-only mutation

    HEAD:

        denied
    """

    if manager_roles is None:
        manager_roles = {
            UserRole.SUPER_ADMIN,
            UserRole.DISPATCHER,
        }

    return authorize_resource_access(
        current_user=current_user,
        resource=resource,
        resource_name=resource_name,
        owner_fields=owner_fields,
        allow_roles=manager_roles,
    )


# ============================================================
# Ownership predicate
# ============================================================

def is_resource_owner(
    current_user: AuthenticatedUser,
    resource: Any,
    *,
    owner_fields: tuple[str, ...] = (
        "user_id",
        "owner_id",
        "customer_id",
    ),
) -> bool:
    """
    Return True only when the current user owns the resource.

    This function never raises.

    Returns False when:

    - resource does not exist
    - resource is deleted
    - tenant does not match
    - owner field does not exist
    - owner ID does not match
    """

    if resource is None:
        return False

    if _is_deleted(resource):
        return False

    if not _belongs_to_current_tenant(
        resource,
        current_user,
    ):
        return False

    owner_id = _get_value(
        resource,
        *owner_fields,
    )

    if owner_id is None:
        return False

    return str(owner_id) == str(
        current_user.user_id
    )


# ============================================================
# Tenant predicate
# ============================================================

def is_same_tenant(
    current_user: AuthenticatedUser,
    resource: Any,
) -> bool:
    """
    Return True when the resource belongs to the authenticated
    user's tenant.

    Deleted or tenant-less resources return False.
    """

    if resource is None:
        return False

    if _is_deleted(resource):
        return False

    return _belongs_to_current_tenant(
        resource,
        current_user,
    )


# ============================================================
# Explicit technician ownership predicate
# ============================================================

def is_technician_owner(
    current_user: AuthenticatedUser,
    technician: Any,
) -> bool:
    """
    Determine whether the authenticated user owns the
    Technician record.

    IMPORTANT:

    Do NOT compare:

        technician.technician_id

    to:

        current_user.user_id

    unless your application explicitly guarantees that they
    represent the same identifier.

    The Technician model supplied by the project contains:

        technician_id -> integer DB primary key
        tech_id       -> UUID/string identifier

    Therefore tech_id/user_id is preferred.
    """

    if technician is None:
        return False

    if _is_deleted(technician):
        return False

    if not _belongs_to_current_tenant(
        technician,
        current_user,
    ):
        return False

    technician_user_id = _get_value(
        technician,
        "tech_id",
        "user_id",
    )

    if technician_user_id is None:
        return False

    return str(technician_user_id) == str(
        current_user.user_id
    )


# ============================================================
# Explicit job assignment predicate
# ============================================================

def is_job_assigned_to_user(
    current_user: AuthenticatedUser,
    job: Any,
) -> bool:
    """
    Determine whether a job is assigned to the current user.

    NOTE:

    If Job.assigned_technician_id is the Technician table's
    integer primary key, this function cannot safely compare
    it directly with current_user.user_id.

    In that case the route/service should resolve the Technician
    record first and compare its tech_id/user_id.

    This function supports projects where the job assignment
    field itself stores the authenticated user's ID.
    """

    if job is None:
        return False

    if _is_deleted(job):
        return False

    if not _belongs_to_current_tenant(
        job,
        current_user,
    ):
        return False

    assigned_id = _get_value(
        job,
        "technician_user_id",
        "assigned_user_id",
        "assigned_technician_user_id",
    )

    if assigned_id is None:
        return False

    return str(assigned_id) == str(
        current_user.user_id
    )


# ============================================================
# Cross-tenant protection helper
# ============================================================

def require_resource_tenant(
    current_user: AuthenticatedUser,
    resource: Any,
    resource_name: str,
) -> Any:
    """
    Explicitly require tenant isolation.

    Useful for routes where only tenant membership is required.
    """

    _require_active_resource(
        resource,
        resource_name,
    )

    if current_user.role == UserRole.HEAD:
        raise _access_denied(resource_name)

    _require_same_tenant(
        resource,
        current_user,
        resource_name,
    )

    return resource


# ============================================================
# Exports
# ============================================================

__all__ = [
    "authorize_organization_access",
    "authorize_user_access",
    "authorize_job_access",
    "authorize_technician_access",
    "authorize_customer_access",
    "authorize_invoice_access",
    "authorize_resource_access",
    "authorize_resource_mutation",
    "is_resource_owner",
    "is_same_tenant",
    "is_technician_owner",
    "is_job_assigned_to_user",
    "require_resource_tenant",
]


