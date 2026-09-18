"""
Audit routes.

Provides access to:
- Override audit history
- Security audit logs
- Authentication history
- Sentiment audit logs

Authentication history is backed by the immutable EnterpriseAuditLog.
"""

from datetime import datetime
import logging
import math

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Header,
    Query,
    Request,
)
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    OverrideAuditEvent,
    Job,
    SecurityAuditLog,
    EnterpriseAuditLog,
)
from app.models.sentiment_audit import SentimentAuditRecord
from app.schemas import OverrideAuditResponse
from app.dependencies.override_authorization import verify_jwt_token
from app.sentiment.audit import SentimentAuditLogger
from app.auth.dependencies import get_current_user


logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/audit",
    tags=["Audit"],
)


# ============================================================================
# Authentication history configuration
# ============================================================================

AUTH_HISTORY_ACTIONS = (
    "LOGIN_SUCCESS",
    "LOGIN_FAILURE",
    "ACCOUNT_LOCKED",
    "LOGOUT",
)

AUTH_HISTORY_ALLOWED_ROLES = {
    "super_admin",
    "head",
}

DEFAULT_AUTH_HISTORY_PAGE_SIZE = 50
MAX_AUTH_HISTORY_PAGE_SIZE = 100


# ============================================================================
# Existing override audit endpoint
# ============================================================================

@router.get(
    "/overrides/{job_id}",
    response_model=list[OverrideAuditResponse],
)
def get_override_audits_for_job(
    job_id: str,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    authorization: str = Depends(verify_jwt_token),
    db: Session = Depends(get_db),
):
    try:
        job_db_id = int(job_id)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid job ID format",
        )

    job = (
        db.query(Job)
        .filter(
            Job.id == job_db_id,
            Job.tenant_id == x_tenant_id,
        )
        .first()
    )

    if not job:
        raise HTTPException(
            status_code=404,
            detail="Job not found",
        )

    audits = (
        db.query(OverrideAuditEvent)
        .filter(
            OverrideAuditEvent.job_id == job_db_id,
            OverrideAuditEvent.tenant_id == x_tenant_id,
        )
        .order_by(OverrideAuditEvent.created_at.desc())
        .all()
    )

    return audits


# ============================================================================
# Existing security audit endpoint
# ============================================================================

@router.get("/security")
def get_security_audit_logs(
    tenant_id: str,
    event_type: str = None,
    start_date: str = None,
    end_date: str = None,
    db: Session = Depends(get_db),
):
    query = db.query(SecurityAuditLog).filter(
        SecurityAuditLog.tenant_id == tenant_id
    )

    if event_type:
        query = query.filter(
            SecurityAuditLog.event == event_type
        )

    if start_date:
        try:
            dt = datetime.fromisoformat(start_date)
            query = query.filter(
                SecurityAuditLog.timestamp >= dt
            )
        except ValueError:
            query = query.filter(
                SecurityAuditLog.timestamp >= start_date
            )

    if end_date:
        try:
            dt = datetime.fromisoformat(end_date)
            query = query.filter(
                SecurityAuditLog.timestamp <= dt
            )
        except ValueError:
            query = query.filter(
                SecurityAuditLog.timestamp <= end_date
            )

    logs = (
        query
        .order_by(SecurityAuditLog.timestamp.desc())
        .all()
    )

    return [
        {
            "id": log.id,
            "event": log.event,
            "timestamp": (
                log.timestamp.isoformat()
                if log.timestamp
                else None
            ),
            "severity": log.severity,
            "user_tenant": log.user_tenant,
            "attempted_channel": log.attempted_channel,
            "ip_address": log.ip_address,
            "websocket_id": log.websocket_id,
            "action_taken": log.action_taken,
            "payload_tenant": log.payload_tenant,
            "target_tenant": log.target_tenant,
            "technician_id": log.technician_id,
            "job_id": log.job_id,
            "tenant_id": log.tenant_id,
        }
        for log in logs
    ]


# ============================================================================
# Authentication history helpers
# ============================================================================

def _get_current_user_role(current_user) -> str:
    """
    Normalize the authenticated user's role.

    Supports both Enum and string role values.
    """
    role = getattr(current_user, "role", None)

    if role is None:
        return ""

    value = getattr(role, "value", role)

    return str(value).lower()


def _require_auth_history_access(current_user) -> None:
    """
    Require an authorized administrative role.
    """
    role = _get_current_user_role(current_user)

    if role not in AUTH_HISTORY_ALLOWED_ROLES:
        raise HTTPException(
            status_code=403,
            detail=(
                "You are not authorized to access "
                "authentication history"
            ),
        )


def _parse_auth_history_datetime(
    value: str | None,
    field_name: str,
) -> datetime | None:
    """
    Parse an ISO-8601 datetime.

    Invalid datetime values return HTTP 400.
    """
    if value is None:
        return None

    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid {field_name}. "
                "Expected an ISO-8601 datetime."
            ),
        )


def _safe_authentication_event(
    log: EnterpriseAuditLog,
) -> dict:
    """
    Serialize an authentication audit record safely.

    The following are intentionally never returned:
    - password
    - password_hash
    - access token
    - refresh token
    - MFA code
    - trusted-device token
    - password-reset token
    - old_value
    - new_value
    - complete details object
    """

    if log.action == "LOGIN_SUCCESS":
        outcome = "success"

    elif log.action == "LOGIN_FAILURE":
        outcome = "failure"

    elif log.action == "ACCOUNT_LOCKED":
        outcome = "blocked"

    elif log.action == "LOGOUT":
        outcome = "success"

    else:
        outcome = "unknown"

    authentication_method = None

    # authentication_method is currently stored in `details`
    # by auth.py. Only allow known non-secret values through.
    if isinstance(log.details, dict):
        candidate = log.details.get(
            "authentication_method"
        )

        allowed_methods = {
            "password",
            "password_plus_totp",
            "mfa_recovery_code",
            "trusted_device",
            "oidc",
        }

        if candidate in allowed_methods:
            authentication_method = candidate

    return {
        "id": log.id,
        "event_type": log.action,
        "user_id": log.user_id,
        "user_email": log.user_email,
        "role": log.role,
        "tenant_id": log.tenant_id,
        "timestamp": (
            log.timestamp.isoformat()
            if log.timestamp
            else None
        ),
        "outcome": outcome,
        "severity": log.severity,
        "ip_address": log.ip_address,
        "user_agent": log.user_agent,
        "correlation_id": log.correlation_id,
        "authentication_method": authentication_method,
    }


# ============================================================================
# Authentication history endpoint
# ============================================================================

@router.get("/authentication-history")
def get_authentication_history(
    request: Request,

    event_type: str | None = Query(
        default=None,
        description=(
            "Authentication event type. "
            "Allowed values: LOGIN_SUCCESS, LOGIN_FAILURE, "
            "ACCOUNT_LOCKED, LOGOUT."
        ),
    ),

    user_id: str | None = Query(
        default=None,
        description="Filter authentication events by user ID.",
    ),

    start_date: str | None = Query(
        default=None,
        description="ISO-8601 start datetime.",
    ),

    end_date: str | None = Query(
        default=None,
        description="ISO-8601 end datetime.",
    ),

    page: int = Query(
        default=1,
        ge=1,
        description="Page number.",
    ),

    page_size: int = Query(
        default=DEFAULT_AUTH_HISTORY_PAGE_SIZE,
        ge=1,
        le=MAX_AUTH_HISTORY_PAGE_SIZE,
        description="Number of records per page.",
    ),

    current_user=Depends(get_current_user),

    db: Session = Depends(get_db),
):
    """
    Retrieve durable authentication history for the
    authenticated user's tenant.

    Only SUPER_ADMIN and HEAD roles can access this endpoint.

    Tenant isolation is enforced using the authenticated
    user's tenant_id. The client cannot choose the tenant.

    Returned events:
        LOGIN_SUCCESS
        LOGIN_FAILURE
        ACCOUNT_LOCKED
        LOGOUT
    """

    # ------------------------------------------------------------------
    # Authorization
    # ------------------------------------------------------------------

    _require_auth_history_access(current_user)

    current_tenant_id = getattr(
        current_user,
        "tenant_id",
        None,
    )

    if not current_tenant_id:
        raise HTTPException(
            status_code=403,
            detail="Authenticated user has no tenant",
        )

    # ------------------------------------------------------------------
    # Validate event type
    # ------------------------------------------------------------------

    normalized_event_type = None

    if event_type:
        normalized_event_type = (
            event_type.strip().upper()
        )

        if normalized_event_type not in AUTH_HISTORY_ACTIONS:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Invalid event_type. Allowed values: "
                    "LOGIN_SUCCESS, LOGIN_FAILURE, "
                    "ACCOUNT_LOCKED, LOGOUT"
                ),
            )

    # ------------------------------------------------------------------
    # Validate date filters
    # ------------------------------------------------------------------

    start_dt = _parse_auth_history_datetime(
        start_date,
        "start_date",
    )

    end_dt = _parse_auth_history_datetime(
        end_date,
        "end_date",
    )

    if start_dt and end_dt and start_dt > end_dt:
        raise HTTPException(
            status_code=400,
            detail=(
                "start_date cannot be later than end_date"
            ),
        )

    # ------------------------------------------------------------------
    # Tenant-scoped query
    # ------------------------------------------------------------------
    #
    # IMPORTANT:
    # tenant_id comes ONLY from current_user.
    #
    # There is intentionally no tenant_id query parameter.
    #
    # ------------------------------------------------------------------

    query = (
        db.query(EnterpriseAuditLog)
        .filter(
            EnterpriseAuditLog.tenant_id
            == current_tenant_id,

            EnterpriseAuditLog.action.in_(
                AUTH_HISTORY_ACTIONS
            ),
        )
    )

    # ------------------------------------------------------------------
    # Event filter
    # ------------------------------------------------------------------

    if normalized_event_type:
        query = query.filter(
            EnterpriseAuditLog.action
            == normalized_event_type
        )

    # ------------------------------------------------------------------
    # User filter
    # ------------------------------------------------------------------

    if user_id:
        query = query.filter(
            EnterpriseAuditLog.user_id == user_id
        )

    # ------------------------------------------------------------------
    # Start date
    # ------------------------------------------------------------------

    if start_dt:
        query = query.filter(
            EnterpriseAuditLog.timestamp >= start_dt
        )

    # ------------------------------------------------------------------
    # End date
    # ------------------------------------------------------------------

    if end_dt:
        query = query.filter(
            EnterpriseAuditLog.timestamp <= end_dt
        )

    # ------------------------------------------------------------------
    # Total count
    # ------------------------------------------------------------------

    total = query.count()

    total_pages = (
        math.ceil(total / page_size)
        if total > 0
        else 0
    )

    # ------------------------------------------------------------------
    # Pagination
    # ------------------------------------------------------------------

    offset = (page - 1) * page_size

    logs = (
        query
        .order_by(
            EnterpriseAuditLog.timestamp.desc(),
            EnterpriseAuditLog.id.desc(),
        )
        .offset(offset)
        .limit(page_size)
        .all()
    )

    # ------------------------------------------------------------------
    # Record that authentication history was accessed.
    #
    # This action is NOT included in AUTH_HISTORY_ACTIONS,
    # therefore it does not recursively appear in the history.
    # ------------------------------------------------------------------

    access_audit = EnterpriseAuditLog(
        user_id=getattr(
            current_user,
            "user_id",
            None,
        ),

        user_email=getattr(
            current_user,
            "email",
            None,
        ),

        role=_get_current_user_role(
            current_user
        ),

        tenant_id=current_tenant_id,

        ip_address=(
            request.client.host
            if request.client
            else None
        ),

        user_agent=(
            request.headers.get(
                "User-Agent",
                "",
            )[:500]
        ),

        action="AUTH_HISTORY_ACCESSED",

        entity_type="authentication_history",

        details={
            "outcome": "success",
            "page": page,
            "page_size": page_size,
            "event_type": normalized_event_type,
            "filtered_user_id": user_id,
            "has_start_date": start_dt is not None,
            "has_end_date": end_dt is not None,
        },

        correlation_id=request.headers.get(
            "X-Correlation-ID"
        ),

        severity="INFO",
    )

    db.add(access_audit)

    db.commit()

    # ------------------------------------------------------------------
    # Safe response
    # ------------------------------------------------------------------

    return {
        "items": [
            _safe_authentication_event(log)
            for log in logs
        ],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
    }


# ============================================================================
# Existing sentiment audit endpoint
# ============================================================================
#
# IMPORTANT:
# Your uploaded file does NOT contain the original implementation here.
# It contains only a placeholder returning [].
#
# Keep your original sentiment implementation in this section.
# ============================================================================

@router.get("/sentiment")
def get_sentiment_audit_logs(
    tenant_id: str,
    customer_id: str | None = None,
    job_id: int | None = None,
    manager_id: str | None = None,
    sentiment_label: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
):
    """
    Existing sentiment audit endpoint.

    NOTE:
    The uploaded audit.py contained only a placeholder implementation
    for this endpoint. The original implementation should remain here.
    """

    query = db.query(
        SentimentAuditRecord
    ).filter(
        SentimentAuditRecord.tenant_id == tenant_id
    )

    if customer_id:
        query = query.filter(
            SentimentAuditRecord.customer_id
            == customer_id
        )

    if job_id is not None:
        query = query.filter(
            SentimentAuditRecord.job_id == job_id
        )

    if manager_id:
        query = query.filter(
            SentimentAuditRecord.manager_id
            == manager_id
        )

    if sentiment_label:
        query = query.filter(
            SentimentAuditRecord.sentiment_label
            == sentiment_label
        )

    if start_date:
        try:
            start_dt = datetime.fromisoformat(
                start_date
            )
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Invalid start_date. "
                    "Expected an ISO-8601 datetime."
                ),
            )

        query = query.filter(
            SentimentAuditRecord.timestamp
            >= start_dt
        )

    if end_date:
        try:
            end_dt = datetime.fromisoformat(
                end_date
            )
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Invalid end_date. "
                    "Expected an ISO-8601 datetime."
                ),
            )

        query = query.filter(
            SentimentAuditRecord.timestamp
            <= end_dt
        )

    records = (
        query
        .order_by(
            SentimentAuditRecord.timestamp.desc()
        )
        .all()
    )

    return [
        {
            "id": record.id,
            "tenant_id": record.tenant_id,
            "customer_id": record.customer_id,
            "job_id": record.job_id,
            "manager_id": record.manager_id,
            "sentiment_label": record.sentiment_label,
            "timestamp": (
                record.timestamp.isoformat()
                if record.timestamp
                else None
            ),
        }
        for record in records
    ]