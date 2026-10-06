"""
Enterprise audit service.

Provides a simple function to create audit log entries from
anywhere in the application. Designed for use as a utility
function, not a class-based service, to minimize boilerplate.
"""

import uuid
import logging
from typing import Optional

from fastapi import Request
from sqlalchemy.orm import Session

from ..models.enterprise_audit import EnterpriseAuditLog

logger = logging.getLogger(__name__)


def audit_log(
    db: Session,
    *,
    action: str,
    tenant_id: str,
    user_id: Optional[str] = None,
    user_email: Optional[str] = None,
    role: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    old_value: Optional[dict] = None,
    new_value: Optional[dict] = None,
    details: Optional[dict] = None,
    severity: str = "INFO",
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    correlation_id: Optional[str] = None,
    request: Optional[Request] = None,
) -> EnterpriseAuditLog:
    """
    Create an immutable enterprise audit log entry.

    Args:
        db: Database session
        action: Action name (e.g., "LOGIN", "JOB_CREATED", "ORG_SUSPENDED")
        tenant_id: Tenant/organization ID
        user_id: Acting user ID
        user_email: Acting user email
        role: Acting user role
        entity_type: Type of entity affected (e.g., "user", "job")
        entity_id: ID of entity affected
        old_value: Previous state (for updates)
        new_value: New state (for creates/updates)
        details: Additional context metadata
        severity: INFO, WARNING, ERROR, CRITICAL
        ip_address: Client IP (extracted from request if not provided)
        user_agent: Client User-Agent (extracted from request if not provided)
        correlation_id: Request correlation ID
        request: FastAPI request (for auto-extracting IP, UA, correlation)
    
    Returns:
        The created EnterpriseAuditLog record.
    """
    # Auto-extract from request if available
    if request is not None:
        if ip_address is None:
            ip_address = request.client.host if request.client else "unknown"
        if user_agent is None:
            user_agent = request.headers.get("User-Agent", "unknown")[:500]
        if correlation_id is None:
            correlation_id = request.headers.get("X-Correlation-ID")

    entry = EnterpriseAuditLog(
        id=str(uuid.uuid4()),
        user_id=user_id,
        user_email=user_email,
        role=role,
        tenant_id=tenant_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        old_value=old_value,
        new_value=new_value,
        details=details,
        severity=severity,
        ip_address=ip_address,
        user_agent=user_agent,
        correlation_id=correlation_id,
    )

    db.add(entry)
    # Don't commit — let the caller manage the transaction

    logger.debug(
        "Audit: action=%s user=%s tenant=%s entity=%s:%s",
        action, user_id, tenant_id, entity_type, entity_id,
    )

    return entry


# ──────────────────────────────────────────────────
# Predefined audit actions for type safety
# ──────────────────────────────────────────────────

class AuditAction:
    """Constants for audit action names."""

    # Authentication
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"
    FAILED_LOGIN = "FAILED_LOGIN"
    TOKEN_REFRESHED = "TOKEN_REFRESHED"
    PASSWORD_RESET_REQUESTED = "PASSWORD_RESET_REQUESTED"
    PASSWORD_RESET_COMPLETED = "PASSWORD_RESET_COMPLETED"
    PASSWORD_CHANGED = "PASSWORD_CHANGED"
    CUSTOMER_SUPPORT_UPDATED = "CUSTOMER_SUPPORT_UPDATED"

    # User management
    USER_CREATED = "USER_CREATED"
    USER_UPDATED = "USER_UPDATED"
    USER_DELETED = "USER_DELETED"
    USER_ACTIVATED = "USER_ACTIVATED"
    USER_DEACTIVATED = "USER_DEACTIVATED"
    USER_REGISTERED = "USER_REGISTERED"
    ROLE_CHANGED = "ROLE_CHANGED"
    PERMISSION_CHANGED = "PERMISSION_CHANGED"

    # Organization management
    ORG_CREATED = "ORG_CREATED"
    ORG_UPDATED = "ORG_UPDATED"
    ORG_SUSPENDED = "ORG_SUSPENDED"
    ORG_ACTIVATED = "ORG_ACTIVATED"
    ORG_DELETED = "ORG_DELETED"

    # Job lifecycle
    JOB_CREATED = "JOB_CREATED"
    JOB_UPDATED = "JOB_UPDATED"
    JOB_ASSIGNED = "JOB_ASSIGNED"
    JOB_REASSIGNED = "JOB_REASSIGNED"
    JOB_ACCEPTED = "JOB_ACCEPTED"
    JOB_REJECTED = "JOB_REJECTED"
    JOB_COMPLETED = "JOB_COMPLETED"
    JOB_CANCELLED = "JOB_CANCELLED"
    JOB_CLOSED = "JOB_CLOSED"

    # Customer
    CUSTOMER_CREATED = "CUSTOMER_CREATED"
    CUSTOMER_UPDATED = "CUSTOMER_UPDATED"
    SERVICE_REQUEST_CREATED = "SERVICE_REQUEST_CREATED"
    SERVICE_REQUEST_UPDATED = "SERVICE_REQUEST_UPDATED"
    SERVICE_REQUEST_CANCELLED = "SERVICE_REQUEST_CANCELLED"

    # Technician
    TECHNICIAN_CREATED = "TECHNICIAN_CREATED"
    TECHNICIAN_UPDATED = "TECHNICIAN_UPDATED"
    TECHNICIAN_DELETED = "TECHNICIAN_DELETED"

    # Profile
    PROFILE_CREATED = "PROFILE_CREATED"
    PROFILE_UPDATED = "PROFILE_UPDATED"

    # Extended Job lifecycle
    JOB_STARTED = "JOB_STARTED"
    JOB_PAUSED = "JOB_PAUSED"
    JOB_RESUMED = "JOB_RESUMED"
    JOB_REJECTED_BY_TECHNICIAN = "JOB_REJECTED_BY_TECHNICIAN"
    JOB_REASSIGNED_FROM_DECLINED = "JOB_REASSIGNED_FROM_DECLINED"

    # Settings
    SETTINGS_UPDATED = "SETTINGS_UPDATED"
    NOTIFICATION_SETTINGS_UPDATED = "NOTIFICATION_SETTINGS_UPDATED"
    GPS_SETTINGS_UPDATED = "GPS_SETTINGS_UPDATED"

    # Notifications
    NOTIFICATION_SENT = "NOTIFICATION_SENT"


    # AI / Intent Recognition
    INTENT_CLASSIFIED = "INTENT_CLASSIFIED"
        # Task runtime / reliability
    TASK_RETRY = "TASK_RETRY"
    TASK_DLQ = "TASK_DLQ"

    # Security
    UNAUTHORIZED_ACCESS = "UNAUTHORIZED_ACCESS"
    CROSS_TENANT_ACCESS = "CROSS_TENANT_ACCESS"
    ACCOUNT_LOCKED = "ACCOUNT_LOCKED"
    ACCOUNT_UNLOCKED = "ACCOUNT_UNLOCKED"

        # Message preview / approval
    MESSAGE_PREVIEW_CREATED = "MESSAGE_PREVIEW_CREATED"
    MESSAGE_PREVIEW_EDITED = "MESSAGE_PREVIEW_EDITED"
    MESSAGE_PREVIEW_APPROVED = "MESSAGE_PREVIEW_APPROVED"