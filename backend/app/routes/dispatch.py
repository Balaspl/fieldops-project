from fastapi import APIRouter, Depends, HTTPException, status, Request, Body
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from typing import Optional
import uuid
import json

from ..database import get_db
from ..models import (
    Technician,
    Job,
    AuditEvent,
    InAppNotification,
    AssignmentOverride,
)
from ..redis_client import get_redis_client
from ..logger import logger
from ..schemas import HeartbeatPayload, AvailabilityResponse
from ..services.timer_service import TimerService
from ..services.cooldown_service import CooldownService
from ..services.socket_manager import sio, emit_notification
from ..auth.dependencies import (
    AuthenticatedUser,
    require_role,
    require_permission,
)
from ..auth.rbac import UserRole, Permission


class OverrideRequest(BaseModel):
    technician_id: str
    justification: str
    actor_name: Optional[str] = None


router = APIRouter(
    prefix="/technicians",
    tags=["Dispatch"],
)

security = HTTPBearer()


# ------------------------------------------------------------------
# Compatibility helper
# ------------------------------------------------------------------
# notifications.py imports this helper from dispatch.py.
# Keep it here for backward compatibility.
#
# Dispatcher operational endpoints below do NOT use this helper
# for authorization. They use require_permission(...) instead.
# ------------------------------------------------------------------
def verify_jwt_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
        )

    if credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
        )

    return credentials.credentials


# ------------------------------------------------------------------
# Technician heartbeat
# ------------------------------------------------------------------
# Dispatcher must NOT be allowed to send technician heartbeats.
# This endpoint remains restricted to the technician themselves
# and SUPER_ADMIN.
# ------------------------------------------------------------------
@router.post("/{id}/heartbeat")
def technician_heartbeat(
    id: str,
    request: Request,
    payload: HeartbeatPayload = Body(default_factory=HeartbeatPayload),
    current_user: AuthenticatedUser = Depends(
        require_role(
            UserRole.TECHNICIAN,
            UserRole.SUPER_ADMIN,
        )
    ),
    db: Session = Depends(get_db),
    redis_client=Depends(get_redis_client),
):
    tenant_id = current_user.tenant_id

    correlation_id = request.headers.get(
        "X-Correlation-ID",
        str(uuid.uuid4()),
    )

    log_extra = {
        "correlation_id": correlation_id,
        "tenant_id": tenant_id,
        "tech_id": id,
        "user_id": current_user.user_id,
    }

    try:
        # Validate technician ID
        if not id or not id.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid tech ID",
            )

        # Rate limiting
        rate_limit_key = f"rate_limit:{tenant_id}:{id}"

        try:
            if not redis_client.set(
                rate_limit_key,
                "1",
                ex=30,
                nx=True,
            ):
                logger.warning(
                    "Rate limit exceeded for heartbeat",
                    extra=log_extra,
                )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too Many Requests",
                )

        except Exception as e:
            if isinstance(e, HTTPException):
                raise

            logger.warning(
                f"Redis error checking rate limit: {e}",
                extra=log_extra,
            )

        # ------------------------------------------------------------------
        # Tenant-scoped technician lookup
        # ------------------------------------------------------------------
        tech_query = db.query(Technician).filter(
            Technician.tenant_id == tenant_id
        )

        if id.isdigit():
            tech_query = tech_query.filter(
                (Technician.tech_id == id)
                | (Technician.technician_id == int(id))
            )
        else:
            tech_query = tech_query.filter(
                Technician.tech_id == id
            )

        tech = tech_query.first()

        if not tech:
            logger.error(
                "Technician not found",
                extra=log_extra,
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Technician not found",
            )

        # Update database
        now = datetime.now(timezone.utc)

        tech.last_ping = now

        db.commit()

        # Redis cache payload
        cache_data = {
            "tech_id": id,
            "status": tech.technician_status,
            "last_ping": now.isoformat(),
            "active_jobs": tech.current_jobs,
            "last_lat": payload.last_lat,
            "last_lng": payload.last_lng,
        }

        heartbeat_key = (
            f"tech:availability:{tenant_id}:{id}"
        )

        try:
            redis_client.setex(
                heartbeat_key,
                60,
                json.dumps(cache_data),
            )

        except Exception as e:
            logger.warning(
                f"Redis error caching heartbeat: {e}",
                extra=log_extra,
            )

        logger.info(
            "Heartbeat processed and cached successfully",
            extra=log_extra,
        )

        return cache_data

    except Exception as e:
        if isinstance(e, HTTPException):
            raise

        import traceback

        return {
            "debug_crash": str(e),
            "traceback": traceback.format_exc(),
        }


# ------------------------------------------------------------------
# Technician metrics
# ------------------------------------------------------------------
# Dispatcher is allowed to view operational dispatch metrics.
# ------------------------------------------------------------------
@router.get("/metrics")
def get_metrics(
    current_user: AuthenticatedUser = Depends(
        require_permission(Permission.DISPATCH_MANAGE)
    ),
    redis_client=Depends(get_redis_client),
):
    now = datetime.now(timezone.utc)

    hour_str = now.strftime("%Y-%m-%d-%H")

    metric_key = f"metrics:offline_events:{hour_str}"

    val = redis_client.get(metric_key)

    offline_events = int(val) if val else 0

    return {
        "offline_events_current_hour": offline_events,
    }


# ------------------------------------------------------------------
# Technician availability
# ------------------------------------------------------------------
# Dispatcher can VIEW technician availability.
#
# IMPORTANT:
# Tenant is taken from the authenticated user.
# Client supplied X-Tenant-ID is intentionally not trusted.
# ------------------------------------------------------------------
@router.get(
    "/{id}/availability",
    response_model=AvailabilityResponse,
)
def get_technician_availability(
    id: str,
    request: Request,
    current_user: AuthenticatedUser = Depends(
        require_permission(Permission.TECHNICIANS_VIEW_ALL)
    ),
    db: Session = Depends(get_db),
    redis_client=Depends(get_redis_client),
):
    tenant_id = current_user.tenant_id

    correlation_id = request.headers.get(
        "X-Correlation-ID",
        str(uuid.uuid4()),
    )

    log_extra = {
        "correlation_id": correlation_id,
        "tenant_id": tenant_id,
        "tech_id": id,
        "user_id": current_user.user_id,
    }

    heartbeat_key = (
        f"tech:availability:{tenant_id}:{id}"
    )

    # ------------------------------------------------------------------
    # Redis lookup
    # ------------------------------------------------------------------
    try:
        cached_data = redis_client.get(heartbeat_key)

        if cached_data:
            logger.info(
                "Cache hit for availability",
                extra=log_extra,
            )

            return json.loads(cached_data)

    except Exception as e:
        logger.warning(
            f"Redis error checking availability cache: {e}",
            extra=log_extra,
        )

    # ------------------------------------------------------------------
    # Database fallback
    # ------------------------------------------------------------------
    tech_query = db.query(Technician).filter(
        Technician.tenant_id == tenant_id
    )

    if id.isdigit():
        tech_query = tech_query.filter(
            (Technician.tech_id == id)
            | (Technician.technician_id == int(id))
        )
    else:
        tech_query = tech_query.filter(
            Technician.tech_id == id
        )

    tech = tech_query.first()

    if not tech:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Technician not found",
        )

    return {
        "tech_id": id,
        "status": tech.technician_status,
        "last_ping": (
            tech.last_ping.isoformat()
            if tech.last_ping
            else datetime.now(timezone.utc).isoformat()
        ),
        "active_jobs": tech.current_jobs,
        "last_lat": None,
        "last_lng": None,
    }


# ------------------------------------------------------------------
# Invalidate technician cache
# ------------------------------------------------------------------
# This is a management operation, therefore dispatcher needs
# TECHNICIANS_MANAGE permission.
#
# Tenant is always obtained from authenticated user.
# ------------------------------------------------------------------
@router.post("/{id}/invalidate-cache")
def invalidate_technician_cache(
    id: str,
    request: Request,
    current_user: AuthenticatedUser = Depends(
        require_permission(Permission.TECHNICIANS_MANAGE)
    ),
    db: Session = Depends(get_db),
    redis_client=Depends(get_redis_client),
):
    tenant_id = current_user.tenant_id

    correlation_id = request.headers.get(
        "X-Correlation-ID",
        str(uuid.uuid4()),
    )

    log_extra = {
        "correlation_id": correlation_id,
        "tenant_id": tenant_id,
        "tech_id": id,
        "user_id": current_user.user_id,
    }

    # ------------------------------------------------------------------
    # Verify technician belongs to authenticated tenant
    # ------------------------------------------------------------------
    tech_query = db.query(Technician).filter(
        Technician.tenant_id == tenant_id
    )

    if id.isdigit():
        tech_query = tech_query.filter(
            (Technician.tech_id == id)
            | (Technician.technician_id == int(id))
        )
    else:
        tech_query = tech_query.filter(
            Technician.tech_id == id
        )

    tech = tech_query.first()

    if not tech:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Technician not found",
        )

    heartbeat_key = (
        f"tech:availability:{tenant_id}:{id}"
    )

    if redis_client.delete(heartbeat_key):
        logger.info(
            "Cache invalidated successfully",
            extra=log_extra,
        )

        return {
            "message": "Cache invalidated successfully"
        }

    logger.info(
        "Cache invalidation attempted but key not found",
        extra=log_extra,
    )

    return {
        "message": "Cache key not found"
    }


# ------------------------------------------------------------------
# Assignment override
# ------------------------------------------------------------------
# Dispatcher has DISPATCH_MANAGE permission, so this operational
# dispatch action is allowed.
#
# Tenant isolation is enforced on:
#   - Job
#   - New technician
#   - Previous technician
#   - Notification
#   - Audit event
# ------------------------------------------------------------------
@router.post("/assignments/{job_id}/override")
async def admin_override_assignment(
    job_id: int,
    payload: OverrideRequest,
    req: Request,
    current_user: AuthenticatedUser = Depends(
        require_permission(Permission.DISPATCH_MANAGE)
    ),
    db: Session = Depends(get_db),
):
    correlation_id = req.headers.get(
        "X-Correlation-ID",
        str(uuid.uuid4()),
    )

    log_extra = {
        "correlation_id": correlation_id,
        "user_id": current_user.user_id,
        "tenant_id": current_user.tenant_id,
        "job_id": job_id,
    }

    # ------------------------------------------------------------------
    # Job lookup
    # ------------------------------------------------------------------
    job_query = db.query(Job).filter(
        Job.id == job_id
    )

    # Super Admin may access any organization.
    # Dispatcher and all other non-super-admin users are restricted
    # to their authenticated tenant.
    if not current_user.is_super_admin:
        job_query = job_query.filter(
            Job.tenant_id == current_user.tenant_id
        )

    job = job_query.first()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    effective_tenant_id = job.tenant_id

    # ------------------------------------------------------------------
    # Technician must belong to the same tenant as the job
    # ------------------------------------------------------------------
    tech = db.query(Technician).filter(
        Technician.tech_id == payload.technician_id,
        Technician.tenant_id == effective_tenant_id,
    ).first()

    if not tech and payload.technician_id.isdigit():
        tech = db.query(Technician).filter(
            Technician.technician_id == int(
                payload.technician_id
            ),
            Technician.tenant_id == effective_tenant_id,
        ).first()

    if not tech:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Technician not found",
        )

    # notifications.tech_id references technicians.tech_id.
    if not tech.tech_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Technician is not linked with a tech_id. "
                "Complete the technician-user linkage first."
            ),
        )

    recipient_tech_id = tech.tech_id

    # ------------------------------------------------------------------
    # Previous technician
    # ------------------------------------------------------------------
    prev_id = None
    prev_name = "Unassigned"

    if job.assigned_technician_id:
        previous_tech = db.query(Technician).filter(
            Technician.technician_id
            == job.assigned_technician_id,
            Technician.tenant_id == effective_tenant_id,
        ).first()

        if previous_tech:
            prev_id = previous_tech.technician_id
            prev_name = previous_tech.technician_name

    # ------------------------------------------------------------------
    # Actor information comes from authenticated JWT
    # ------------------------------------------------------------------
    actor_role = current_user.role.value

    actor_name = (
        payload.actor_name
        or current_user.user_id
    )

    # ------------------------------------------------------------------
    # Audit event
    # ------------------------------------------------------------------
    audit = AuditEvent(
        tech_id=recipient_tech_id,
        tenant_id=effective_tenant_id,
        event_type="ADMIN_OVERRIDE",
        old_status=payload.justification[:30],
        new_status="OVERRIDDEN",
    )

    db.add(audit)

    # ------------------------------------------------------------------
    # Update job
    # ------------------------------------------------------------------
    job.assigned_technician_id = tech.technician_id
    job.status = "ASSIGNED"

    # ------------------------------------------------------------------
    # Assignment override record
    # ------------------------------------------------------------------
    override_log = AssignmentOverride(
        job_id=job.id,
        actor_name=actor_name,
        actor_role=actor_role,
        justification=payload.justification,
        previous_technician_id=prev_id,
        previous_technician_name=prev_name,
        new_technician_id=tech.technician_id,
        new_technician_name=tech.technician_name,
    )

    db.add(override_log)

    # ------------------------------------------------------------------
    # In-app notification
    # ------------------------------------------------------------------
    notif_id = str(uuid.uuid4())

    notification_body = (
        f"You have been manually force-assigned to job: "
        f"{job.service_type} at {job.location}. "
        f"Reason: {payload.justification}"
    )

    db_notification = InAppNotification(
        id=notif_id,
        tenant_id=effective_tenant_id,
        tech_id=recipient_tech_id,
        job_id=str(job.id),
        type="JOB_ASSIGNED",
        title="Forced Job Assignment",
        body=notification_body,
        status="UNREAD",
        priority="HIGH",
        created_at=datetime.now(timezone.utc),
    )

    db.add(db_notification)

    # ------------------------------------------------------------------
    # Commit
    # ------------------------------------------------------------------
    try:
        db.commit()

        db.refresh(override_log)

    except Exception:
        db.rollback()

        logger.exception(
            "Failed to save assignment override",
            extra=log_extra,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to apply assignment override",
        )

    # ------------------------------------------------------------------
    # Override response data
    # ------------------------------------------------------------------
    override_data = {
        "id": override_log.id,
        "job_id": override_log.job_id,
        "actor_name": override_log.actor_name,
        "actor_role": override_log.actor_role,
        "justification": override_log.justification,
        "previous_technician_id": (
            override_log.previous_technician_id
        ),
        "previous_technician_name": (
            override_log.previous_technician_name
        ),
        "new_technician_id": (
            override_log.new_technician_id
        ),
        "new_technician_name": (
            override_log.new_technician_name
        ),
        "created_at": (
            override_log.created_at.isoformat()
            if override_log.created_at
            else datetime.now(timezone.utc).isoformat()
        ),
    }

    await sio.emit(
        "override:new",
        override_data,
    )

    # ------------------------------------------------------------------
    # Notification payload
    # ------------------------------------------------------------------
    notification_payload = {
        "id": notif_id,
        "tenant_id": effective_tenant_id,
        "tech_id": recipient_tech_id,
        "job_id": str(job.id),
        "type": "JOB_ASSIGNED",
        "title": "Forced Job Assignment",
        "body": notification_body,
        "status": "UNREAD",
        "priority": "HIGH",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "job": {
            "id": job.id,
            "title": (
                f"{job.service_type} - {job.location}"
            ),
            "description": job.issue_description,
            "location": job.location,
            "priority": job.priority,
            "status": job.status,
        },
    }

    await emit_notification(
        recipient_tech_id,
        notification_payload,
    )

    # ------------------------------------------------------------------
    # Dismiss redispatch UI
    # ------------------------------------------------------------------
    await sio.emit(
        "redispatch:dismiss",
        {
            "job_id": job.id
        },
    )

    # ------------------------------------------------------------------
    # Timer / cooldown handling
    # ------------------------------------------------------------------
    redis_client = get_redis_client()

    TimerService.start_timer(
        redis_client,
        str(job.id),
        recipient_tech_id,
    )

    CooldownService.clear_cooldown(
        redis_client,
        str(job.id),
        recipient_tech_id,
    )

    logger.info(
        "Admin override applied",
        extra=log_extra,
    )

    return {
        "message": "Override applied successfully",
        "job_id": job_id,
        "technician_id": payload.technician_id,
    }