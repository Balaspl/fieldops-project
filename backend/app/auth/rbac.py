"""
Role-Based Access Control (RBAC) for FieldOps.

Platform hierarchy:

HEAD
 └── Platform-level owner
     └── Can view organization overview only

Organization hierarchy:

SUPER_ADMIN
 ├── Can create Dispatcher
 ├── Can create Technician
 └── Manages the organization

DISPATCHER
 └── Can create Technician

TECHNICIAN
 └── Field worker

CUSTOMER
 └── End customer

HEAD is NOT part of an organization.
SUPER_ADMIN, DISPATCHER, TECHNICIAN and CUSTOMER belong
to an organization.
"""

from enum import Enum


class UserRole(str, Enum):
    """Roles in the FieldOps platform."""

    # Platform-level owner.
    # HEAD does NOT belong to an organization.
    HEAD = "head"

    # Organization-level administrator.
    SUPER_ADMIN = "super_admin"

    # Operational controller.
    DISPATCHER = "dispatcher"

    # Field worker.
    TECHNICIAN = "technician"

    # End customer.
    CUSTOMER = "customer"


class Permission(str, Enum):
    """Granular permissions for RBAC enforcement."""

    # --------------------------------------------------
    # Organization
    # --------------------------------------------------

    ORG_CREATE = "org:create"
    ORG_MANAGE = "org:manage"
    ORG_VIEW_ALL = "org:view_all"
    ORG_SUSPEND = "org:suspend"
    ORG_DELETE = "org:delete"

    # --------------------------------------------------
    # Users
    # --------------------------------------------------

    USERS_CREATE = "users:create"
    USERS_MANAGE = "users:manage"
    USERS_VIEW = "users:view"
    USERS_DELETE = "users:delete"

    # --------------------------------------------------
    # Jobs
    # --------------------------------------------------

    JOBS_CREATE = "jobs:create"
    JOBS_VIEW_ALL = "jobs:view_all"
    JOBS_VIEW_OWN = "jobs:view_own"
    JOBS_EDIT = "jobs:edit"
    JOBS_DELETE = "jobs:delete"
    JOBS_ASSIGN = "jobs:assign"
    JOBS_REASSIGN = "jobs:reassign"
    JOBS_REASSIGN_OWN = "jobs:reassign_own"
    JOBS_CANCEL = "jobs:cancel"
    JOBS_ACCEPT_REJECT = "jobs:accept_reject"
    JOBS_STATUS_UPDATE = "jobs:status_update"

    # --------------------------------------------------
    # Completion Documents
    # --------------------------------------------------

    COMPLETION_DOCUMENTS_MANAGE = "completion_documents:manage"

    # --------------------------------------------------
    # Technicians
    # --------------------------------------------------

    TECHNICIANS_CREATE = "technicians:create"
    TECHNICIANS_MANAGE = "technicians:manage"
    TECHNICIANS_VIEW_ALL = "technicians:view_all"
    TECHNICIANS_VIEW_OWN = "technicians:view_own"

    # --------------------------------------------------
    # Planning & Dispatch
    # --------------------------------------------------

    PLANNING_VIEW = "planning:view"
    PLANNING_MANAGE = "planning:manage"

    DISPATCH_MANAGE = "dispatch:manage"
    DISPATCH_QUEUE_VIEW = "dispatch:queue_view"

    # --------------------------------------------------
    # Dashboard
    # --------------------------------------------------

    DASHBOARD_VIEW = "dashboard:view"
    DASHBOARD_TECH_VIEW = "dashboard:tech_view"
    DASHBOARD_CUSTOMER_VIEW = "dashboard:customer_view"

    # --------------------------------------------------
    # Notifications
    # --------------------------------------------------

    NOTIFICATIONS_MANAGE = "notifications:manage"
    NOTIFICATIONS_VIEW_OWN = "notifications:view_own"
    NOTIFICATIONS_SEND = "notifications:send"

    # --------------------------------------------------
    # Templates
    # --------------------------------------------------

    TEMPLATES_MANAGE = "templates:manage"
    TEMPLATES_VIEW = "templates:view"

    # --------------------------------------------------
    # Audit
    # --------------------------------------------------

    AUDIT_VIEW = "audit:view"
    AUDIT_VIEW_SYSTEM = "audit:view_system"

    # --------------------------------------------------
    # Settings
    # --------------------------------------------------

    SETTINGS_MANAGE_ORG = "settings:manage_org"
    SETTINGS_MANAGE_GLOBAL = "settings:manage_global"

    # --------------------------------------------------
    # GPS
    # --------------------------------------------------

    GPS_TRACK = "gps:track"
    GPS_TRACK_OWN = "gps:track_own"
    GPS_ADMIN = "gps:admin"

    # --------------------------------------------------
    # Customers
    # --------------------------------------------------

    CUSTOMERS_MANAGE = "customers:manage"
    CUSTOMERS_VIEW_OWN = "customers:view_own"
    CUSTOMERS_CREATE_REQUEST = "customers:create_request"

    # --------------------------------------------------
    # Reports
    # --------------------------------------------------

    REPORTS_VIEW = "reports:view"
    REPORTS_DOWNLOAD = "reports:download"

    # --------------------------------------------------
    # Escalations
    # --------------------------------------------------

    ESCALATIONS_VIEW = "escalations:view"
    ESCALATIONS_MANAGE = "escalations:manage"

    # --------------------------------------------------
    # Platform
    # --------------------------------------------------

    PLATFORM_HEALTH = "platform:health"
    PLATFORM_ANALYTICS = "platform:analytics"


# ======================================================
# ROLE → PERMISSIONS
# ======================================================

ROLE_PERMISSIONS: dict[UserRole, set[Permission]] = {

    # ==================================================
    # HEAD
    # ==================================================
    #
    # HEAD is the platform owner.
    #
    # Important:
    # HEAD can VIEW organizations.
    # HEAD cannot create, modify, suspend or delete them.
    #
    # HEAD also cannot create users.
    #
    UserRole.HEAD: {
        Permission.ORG_VIEW_ALL,
        Permission.AUDIT_VIEW_SYSTEM,
        Permission.PLATFORM_HEALTH,
        Permission.PLATFORM_ANALYTICS,
    },

    # ==================================================
    # SUPER ADMIN
    # ==================================================
    #
    # Organization-level administrator.
    #
    # Can manage users inside their organization.
    #
    # Can create:
    #   - Dispatcher
    #   - Technician
    #
    # Cannot create:
    #   - HEAD
    #   - another SUPER_ADMIN
    #
    UserRole.SUPER_ADMIN: {
        # Users
        Permission.USERS_CREATE,
        Permission.USERS_MANAGE,
        Permission.USERS_VIEW,
        Permission.USERS_DELETE,

        # Jobs
        Permission.JOBS_CREATE,
        Permission.JOBS_VIEW_ALL,
        Permission.JOBS_EDIT,
        Permission.JOBS_DELETE,
        Permission.JOBS_ASSIGN,
        Permission.JOBS_REASSIGN,
        Permission.JOBS_CANCEL,
        Permission.JOBS_STATUS_UPDATE,

        # Technicians
        Permission.TECHNICIANS_CREATE,
        Permission.TECHNICIANS_MANAGE,
        Permission.TECHNICIANS_VIEW_ALL,

        # Planning
        Permission.PLANNING_VIEW,
        Permission.PLANNING_MANAGE,

        # Dispatch
        Permission.DISPATCH_MANAGE,
        Permission.DISPATCH_QUEUE_VIEW,

        # Dashboard
        Permission.DASHBOARD_VIEW,

        # Notifications
        Permission.NOTIFICATIONS_MANAGE,
        Permission.NOTIFICATIONS_SEND,

        # Templates
        Permission.TEMPLATES_MANAGE,
        Permission.TEMPLATES_VIEW,

        # Audit
        Permission.AUDIT_VIEW,

        # Organization settings
        Permission.SETTINGS_MANAGE_ORG,

        # GPS
        Permission.GPS_TRACK,
        Permission.GPS_ADMIN,

        # Customers
        Permission.CUSTOMERS_MANAGE,

        # Reports
        Permission.REPORTS_VIEW,
        Permission.REPORTS_DOWNLOAD,

        # Escalations
        Permission.ESCALATIONS_VIEW,
        Permission.ESCALATIONS_MANAGE,
    },

    # ==================================================
    # DISPATCHER
    # ==================================================
    #
    # Dispatcher can create technicians.
    #
    # Dispatcher cannot create:
    #   - HEAD
    #   - SUPER_ADMIN
    #   - another DISPATCHER
    #
    UserRole.DISPATCHER: {
        # Jobs
        Permission.JOBS_CREATE,
        Permission.JOBS_VIEW_ALL,
        Permission.JOBS_EDIT,
        Permission.JOBS_ASSIGN,
        Permission.JOBS_REASSIGN,
        Permission.JOBS_CANCEL,
        Permission.JOBS_STATUS_UPDATE,

        # Technicians
        Permission.TECHNICIANS_CREATE,
        Permission.TECHNICIANS_MANAGE,
        Permission.TECHNICIANS_VIEW_ALL,

        # Planning
        Permission.PLANNING_VIEW,
        Permission.PLANNING_MANAGE,

        # Dispatch
        Permission.DISPATCH_MANAGE,
        Permission.DISPATCH_QUEUE_VIEW,

        # Dashboard
        Permission.DASHBOARD_VIEW,

        # Notifications
        Permission.NOTIFICATIONS_MANAGE,
        Permission.NOTIFICATIONS_SEND,

        # Templates
        Permission.TEMPLATES_VIEW,

        # GPS
        Permission.GPS_TRACK,

        # Customers
        Permission.CUSTOMERS_MANAGE,

        # Reports
        Permission.REPORTS_VIEW,

        # Escalations
        Permission.ESCALATIONS_VIEW,
        Permission.ESCALATIONS_MANAGE,

        # Users can be viewed but not arbitrarily created.
        Permission.USERS_VIEW,
        Permission.USERS_CREATE,

    },

    # ==================================================
    # TECHNICIAN
    # ==================================================

    UserRole.TECHNICIAN: {
        # Own jobs
        Permission.JOBS_VIEW_OWN,
        Permission.JOBS_ACCEPT_REJECT,
        Permission.JOBS_STATUS_UPDATE,
        Permission.JOBS_REASSIGN_OWN,
        Permission.COMPLETION_DOCUMENTS_MANAGE,
        Permission.REPORTS_VIEW,

        # Own profile
        Permission.TECHNICIANS_VIEW_OWN,

        # Dashboard
        Permission.DASHBOARD_TECH_VIEW,

        # Notifications
        Permission.NOTIFICATIONS_VIEW_OWN,

        # Own GPS
        Permission.GPS_TRACK_OWN,
    },

    # ==================================================
    # CUSTOMER
    # ==================================================

    UserRole.CUSTOMER: {
        # Own jobs
        Permission.JOBS_VIEW_OWN,

        # Service requests
        Permission.CUSTOMERS_CREATE_REQUEST,
        Permission.CUSTOMERS_VIEW_OWN,

        # Dashboard
        Permission.DASHBOARD_CUSTOMER_VIEW,

        # Notifications
        Permission.NOTIFICATIONS_VIEW_OWN,

        # GPS
        Permission.GPS_TRACK_OWN,

        # Reports
        Permission.REPORTS_DOWNLOAD,
    },
}


# ======================================================
# PERMISSION HELPERS
# ======================================================

def has_permission(role: UserRole, permission: Permission) -> bool:
    if not isinstance(role, UserRole):
        return False

    if not isinstance(permission, Permission):
        return False

    return permission in ROLE_PERMISSIONS.get(role, set())


def get_permissions(role: UserRole) -> set[Permission]:
    if not isinstance(role, UserRole):
        return set()

    return set(ROLE_PERMISSIONS.get(role, set()))


def is_super_admin(role: str) -> bool:
    """Check whether the role is an organization Super Admin."""

    return role == UserRole.SUPER_ADMIN.value


# ======================================================
# ROLE HIERARCHY
# ======================================================

def role_hierarchy_level(role: UserRole) -> int:
    """
    Return the hierarchy level of a role.

    Higher number = more authority.

    HEAD is the platform-level owner.
    """

    hierarchy = {
        UserRole.CUSTOMER: 1,
        UserRole.TECHNICIAN: 2,
        UserRole.DISPATCHER: 3,
        UserRole.SUPER_ADMIN: 4,
        UserRole.HEAD: 5,
    }

    return hierarchy.get(role, 0)


# ======================================================
# ROLE CREATION RULES
# ======================================================

def can_manage_role(
    actor_role: UserRole,
    target_role: UserRole,
) -> bool:
    """
    Determine whether one role can create/manage another role.

    Rules:

    HEAD:
        Can manage no users.

    SUPER_ADMIN:
        Can create/manage Dispatcher and Technician.

    DISPATCHER:
        Can create/manage Technician only.

    TECHNICIAN:
        Cannot create users.

    CUSTOMER:
        Cannot create users.

    Nobody can create HEAD or SUPER_ADMIN
    through normal user-management APIs.
    """

    if actor_role == UserRole.HEAD:
        return False

    if actor_role == UserRole.SUPER_ADMIN:
        return target_role in {
            UserRole.DISPATCHER,
            UserRole.TECHNICIAN,
        }

    if actor_role == UserRole.DISPATCHER:
        return target_role == UserRole.TECHNICIAN

    return False