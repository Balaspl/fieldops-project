import pytest

from app.auth.rbac import (
    Permission,
    ROLE_PERMISSIONS,
    UserRole,
    can_manage_role,
    get_permissions,
    has_permission,
    is_super_admin,
    role_hierarchy_level,
)


# ============================================================
# Role → Permission Matrix
# ============================================================

EXPECTED_PERMISSIONS = {
    UserRole.HEAD: {
        Permission.ORG_VIEW_ALL,
        Permission.AUDIT_VIEW_SYSTEM,
        Permission.PLATFORM_HEALTH,
        Permission.PLATFORM_ANALYTICS,
    },

    UserRole.SUPER_ADMIN: {
        Permission.USERS_CREATE,
        Permission.USERS_MANAGE,
        Permission.USERS_VIEW,
        Permission.USERS_DELETE,
        Permission.JOBS_CREATE,
        Permission.JOBS_VIEW_ALL,
        Permission.JOBS_EDIT,
        Permission.JOBS_DELETE,
        Permission.JOBS_ASSIGN,
        Permission.JOBS_REASSIGN,
        Permission.JOBS_CANCEL,
        Permission.JOBS_STATUS_UPDATE,
        Permission.TECHNICIANS_CREATE,
        Permission.TECHNICIANS_MANAGE,
        Permission.TECHNICIANS_VIEW_ALL,
        Permission.PLANNING_VIEW,
        Permission.PLANNING_MANAGE,
        Permission.DISPATCH_MANAGE,
        Permission.DISPATCH_QUEUE_VIEW,
        Permission.DASHBOARD_VIEW,
        Permission.NOTIFICATIONS_MANAGE,
        Permission.NOTIFICATIONS_SEND,
        Permission.TEMPLATES_MANAGE,
        Permission.TEMPLATES_VIEW,
        Permission.AUDIT_VIEW,
        Permission.SETTINGS_MANAGE_ORG,
        Permission.GPS_TRACK,
        Permission.GPS_ADMIN,
        Permission.CUSTOMERS_MANAGE,
        Permission.REPORTS_VIEW,
        Permission.REPORTS_DOWNLOAD,
        Permission.ESCALATIONS_VIEW,
        Permission.ESCALATIONS_MANAGE,
    },

    UserRole.DISPATCHER: {
        Permission.JOBS_CREATE,
        Permission.JOBS_VIEW_ALL,
        Permission.JOBS_EDIT,
        Permission.JOBS_ASSIGN,
        Permission.JOBS_REASSIGN,
        Permission.JOBS_CANCEL,
        Permission.JOBS_STATUS_UPDATE,
        Permission.TECHNICIANS_CREATE,
        Permission.TECHNICIANS_MANAGE,
        Permission.TECHNICIANS_VIEW_ALL,
        Permission.PLANNING_VIEW,
        Permission.PLANNING_MANAGE,
        Permission.DISPATCH_MANAGE,
        Permission.DISPATCH_QUEUE_VIEW,
        Permission.DASHBOARD_VIEW,
        Permission.NOTIFICATIONS_MANAGE,
        Permission.NOTIFICATIONS_SEND,
        Permission.TEMPLATES_VIEW,
        Permission.GPS_TRACK,
        Permission.CUSTOMERS_MANAGE,
        Permission.REPORTS_VIEW,
        Permission.ESCALATIONS_VIEW,
        Permission.ESCALATIONS_MANAGE,
        Permission.USERS_VIEW,
        Permission.USERS_CREATE,
    },

    UserRole.TECHNICIAN: {
        Permission.JOBS_VIEW_OWN,
        Permission.JOBS_ACCEPT_REJECT,
        Permission.JOBS_STATUS_UPDATE,
        Permission.JOBS_REASSIGN_OWN,
        Permission.TECHNICIANS_VIEW_OWN,
        Permission.DASHBOARD_TECH_VIEW,
        Permission.NOTIFICATIONS_VIEW_OWN,
        Permission.GPS_TRACK_OWN,
        Permission.COMPLETION_DOCUMENTS_MANAGE,
        Permission.CUSTOMER_SIGNATURES_MANAGE,
        Permission.JOB_EXPENSES_MANAGE,
        Permission.REPORTS_VIEW,
    },

    UserRole.CUSTOMER: {
        Permission.JOBS_VIEW_OWN,
        Permission.CUSTOMERS_CREATE_REQUEST,
        Permission.CUSTOMERS_VIEW_OWN,
        Permission.DASHBOARD_CUSTOMER_VIEW,
        Permission.NOTIFICATIONS_VIEW_OWN,
        Permission.GPS_TRACK_OWN,
        Permission.REPORTS_DOWNLOAD,
    },
}


# ============================================================
# 1. Permission matrix matches ROLE_PERMISSIONS
# ============================================================

@pytest.mark.parametrize("role", list(UserRole))
def test_role_permission_matrix(role):
    assert ROLE_PERMISSIONS[role] == EXPECTED_PERMISSIONS[role]


# ============================================================
# 2. Every valid role can retrieve its permissions
# ============================================================

@pytest.mark.parametrize("role", list(UserRole))
def test_get_permissions_returns_expected_permissions(role):
    permissions = get_permissions(role)

    assert isinstance(permissions, set)
    assert permissions == EXPECTED_PERMISSIONS[role]


def test_get_permissions_invalid_role_returns_empty_set():
    assert get_permissions("unknown") == set()
    assert get_permissions(None) == set()


# ============================================================
# 3. Super-admin helper
# ============================================================

@pytest.mark.parametrize(
    "role,expected",
    [
        (UserRole.SUPER_ADMIN.value, True),
        (UserRole.HEAD.value, False),
        (UserRole.DISPATCHER.value, False),
        (UserRole.TECHNICIAN.value, False),
        (UserRole.CUSTOMER.value, False),
        ("unknown", False),
        (None, False),
    ],
)
def test_is_super_admin(role, expected):
    assert is_super_admin(role) is expected


# ============================================================
# 4. Role hierarchy
# ============================================================

@pytest.mark.parametrize(
    "role,expected_level",
    [
        (UserRole.CUSTOMER, 1),
        (UserRole.TECHNICIAN, 2),
        (UserRole.DISPATCHER, 3),
        (UserRole.SUPER_ADMIN, 4),
        (UserRole.HEAD, 5),
        ("unknown", 0),
        (None, 0),
    ],
)
def test_role_hierarchy_level(role, expected_level):
    assert role_hierarchy_level(role) == expected_level


# ============================================================
# 5. Explicit permission checks
# ============================================================

@pytest.mark.parametrize(
    "role,permission",
    [
        (UserRole.HEAD, Permission.PLATFORM_HEALTH),
        (UserRole.HEAD, Permission.PLATFORM_ANALYTICS),

        (UserRole.SUPER_ADMIN, Permission.USERS_CREATE),
        (UserRole.SUPER_ADMIN, Permission.USERS_DELETE),
        (UserRole.SUPER_ADMIN, Permission.JOBS_ASSIGN),
        (UserRole.SUPER_ADMIN, Permission.GPS_ADMIN),

        (UserRole.DISPATCHER, Permission.JOBS_ASSIGN),
        (UserRole.DISPATCHER, Permission.DISPATCH_MANAGE),
        (UserRole.DISPATCHER, Permission.USERS_VIEW),
        (UserRole.DISPATCHER, Permission.USERS_CREATE),

        (UserRole.TECHNICIAN, Permission.JOBS_VIEW_OWN),
        (UserRole.TECHNICIAN, Permission.JOBS_ACCEPT_REJECT),
        (UserRole.TECHNICIAN, Permission.GPS_TRACK_OWN),
        (UserRole.TECHNICIAN, Permission.COMPLETION_DOCUMENTS_MANAGE),
        (UserRole.TECHNICIAN, Permission.CUSTOMER_SIGNATURES_MANAGE),
        (UserRole.TECHNICIAN, Permission.REPORTS_VIEW),

        (UserRole.CUSTOMER, Permission.JOBS_VIEW_OWN),
        (UserRole.CUSTOMER, Permission.CUSTOMERS_CREATE_REQUEST),
        (UserRole.CUSTOMER, Permission.DASHBOARD_CUSTOMER_VIEW),
    ],
)
def test_allowed_role_permission_pairs(role, permission):
    assert has_permission(role, permission) is True


# ============================================================
# 6. Permissions that must be denied
# ============================================================

@pytest.mark.parametrize(
    "role,permission",
    [
        # HEAD cannot perform normal tenant operations
        (UserRole.HEAD, Permission.USERS_CREATE),
        (UserRole.HEAD, Permission.JOBS_CREATE),
        (UserRole.HEAD, Permission.JOBS_DELETE),

        # SUPER_ADMIN does not have platform permissions
        (UserRole.SUPER_ADMIN, Permission.PLATFORM_HEALTH),
        (UserRole.SUPER_ADMIN, Permission.PLATFORM_ANALYTICS),

        # Dispatcher cannot delete users
        (UserRole.DISPATCHER, Permission.USERS_DELETE),

        # Dispatcher cannot access admin GPS controls
        (UserRole.DISPATCHER, Permission.GPS_ADMIN),

        # Technician cannot create jobs
        (UserRole.TECHNICIAN, Permission.JOBS_CREATE),

        # Technician cannot assign jobs
        (UserRole.TECHNICIAN, Permission.JOBS_ASSIGN),

        # Technician cannot manage users
        (UserRole.TECHNICIAN, Permission.USERS_MANAGE),

        # Customer cannot create jobs directly
        (UserRole.CUSTOMER, Permission.JOBS_CREATE),

        # Customer cannot manage users
        (UserRole.CUSTOMER, Permission.USERS_MANAGE),

        # Customer cannot assign jobs
        (UserRole.CUSTOMER, Permission.JOBS_ASSIGN),

        # Customer cannot access admin controls
        (UserRole.CUSTOMER, Permission.GPS_ADMIN),
    ],
)
def test_denied_role_permission_pairs(role, permission):
    assert has_permission(role, permission) is False


# ============================================================
# 7. Unknown role must deny
# ============================================================

@pytest.mark.parametrize(
    "unknown_role",
    [
        "unknown",
        "admin",
        "administrator",
        "superuser",
        "",
        None,
    ],
)
def test_unknown_role_denied(unknown_role):
    assert has_permission(
        unknown_role,
        Permission.JOBS_VIEW_ALL,
    ) is False


# ============================================================
# 8. Unknown permission must deny
# ============================================================

@pytest.mark.parametrize(
    "unknown_permission",
    [
        "unknown_permission",
        "admin:everything",
        "jobs:god_mode",
        "",
        None,
    ],
)
def test_unknown_permission_denied(unknown_permission):
    assert has_permission(
        UserRole.TECHNICIAN,
        unknown_permission,
    ) is False


# ============================================================
# 9. Missing permission must deny
# ============================================================

def test_missing_permission_denied():
    assert has_permission(
        UserRole.TECHNICIAN,
        Permission.USERS_CREATE,
    ) is False


def test_customer_cannot_manage_jobs():
    assert has_permission(
        UserRole.CUSTOMER,
        Permission.JOBS_EDIT,
    ) is False


def test_technician_cannot_manage_dispatch():
    assert has_permission(
        UserRole.TECHNICIAN,
        Permission.DISPATCH_MANAGE,
    ) is False


# ============================================================
# 10. Permission sets must not be accidentally shared/mutable
# ============================================================

def test_get_permissions_returns_copy():
    permissions = get_permissions(UserRole.TECHNICIAN)

    permissions.clear()

    assert Permission.JOBS_VIEW_OWN in ROLE_PERMISSIONS[
        UserRole.TECHNICIAN
    ]


# ============================================================
# 11. Role hierarchy / escalation tests
# ============================================================

@pytest.mark.parametrize(
    "actor,target",
    [
        (UserRole.SUPER_ADMIN, UserRole.DISPATCHER),
        (UserRole.SUPER_ADMIN, UserRole.TECHNICIAN),
        (UserRole.DISPATCHER, UserRole.TECHNICIAN),
    ],
)
def test_allowed_role_management(actor, target):
    assert can_manage_role(actor, target) is True


@pytest.mark.parametrize(
    "actor,target",
    [
        (UserRole.HEAD, UserRole.TECHNICIAN),
        (UserRole.HEAD, UserRole.DISPATCHER),

        (UserRole.DISPATCHER, UserRole.DISPATCHER),
        (UserRole.DISPATCHER, UserRole.SUPER_ADMIN),

        (UserRole.TECHNICIAN, UserRole.TECHNICIAN),
        (UserRole.TECHNICIAN, UserRole.DISPATCHER),
        (UserRole.TECHNICIAN, UserRole.SUPER_ADMIN),

        (UserRole.CUSTOMER, UserRole.TECHNICIAN),
        (UserRole.CUSTOMER, UserRole.DISPATCHER),
        (UserRole.CUSTOMER, UserRole.SUPER_ADMIN),
    ],
)
def test_role_escalation_denied(actor, target):
    assert can_manage_role(actor, target) is False


# ============================================================
# 12. Role management must not allow HEAD/SUPER_ADMIN creation
# ============================================================

@pytest.mark.parametrize(
    "actor",
    [
        UserRole.SUPER_ADMIN,
        UserRole.DISPATCHER,
        UserRole.TECHNICIAN,
        UserRole.CUSTOMER,
        UserRole.HEAD,
    ],
)
def test_cannot_create_head_or_super_admin(actor):
    assert can_manage_role(actor, UserRole.HEAD) is False
    assert can_manage_role(actor, UserRole.SUPER_ADMIN) is False


# ============================================================
# 13. Complete matrix sanity check
# ============================================================

def test_every_role_has_defined_permission_set():
    for role in UserRole:
        assert role in ROLE_PERMISSIONS
        assert isinstance(ROLE_PERMISSIONS[role], set)


def test_no_unknown_roles_in_permission_matrix():
    assert set(ROLE_PERMISSIONS.keys()) == set(UserRole)


# ============================================================
# 14. Every permission is represented in the matrix
# ============================================================

def test_all_permissions_are_known():
    assigned_permissions = set()

    for permissions in ROLE_PERMISSIONS.values():
        assigned_permissions.update(permissions)

    for permission in assigned_permissions:
        assert isinstance(permission, Permission)



# ============================================================
# 9. Manager role is not part of the supported role taxonomy
# ============================================================

@pytest.mark.parametrize(
    "manager_role",
    [
        "manager",
        "Manager",
        "MANAGER",
        "org_manager",
        "organization_manager",
    ],
)
def test_unsupported_manager_role_denied(manager_role):
    """
    MANAGER is not an authoritative FieldOps role.

    An arbitrary manager-labelled role must never receive
    privileged permissions.
    """
    assert has_permission(
        manager_role,
        Permission.ORG_MANAGE,
    ) is False

    assert has_permission(
        manager_role,
        Permission.ORG_CREATE,
    ) is False


# ============================================================
# 10. SUPER_ADMIN cannot create organizations
# ============================================================

def test_super_admin_cannot_create_organization():
    """
    SUPER_ADMIN manages an existing organization but cannot
    create a new organization.

    Organization creation is performed through the onboarding
    flow, which creates the initial SUPER_ADMIN.
    """
    assert has_permission(
        UserRole.SUPER_ADMIN,
        Permission.ORG_CREATE,
    ) is False


# ============================================================
# 11. SUPER_ADMIN can manage the organization
# ============================================================

@pytest.mark.parametrize(
    "role",
    [
        "manager",
        "admin",
        "administrator",
        "superuser",
        "organization_manager",
        "unknown",
    ],
)

def test_unsupported_roles_cannot_manage_organizations(role):
    """
    Privileged organization access must come from the
    authoritative RBAC role/permission mapping only.
    """
    assert has_permission(
        role,
        Permission.ORG_MANAGE,
    ) is False

    assert has_permission(
        role,
        Permission.ORG_CREATE,
    ) is False
