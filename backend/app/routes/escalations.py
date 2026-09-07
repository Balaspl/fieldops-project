from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
import logging
import uuid

from app.database import get_db
from app.models import Job, SLAEscalation, AuditEvent, Technician,InAppNotification
from app.redis_client import get_redis_client
from app.auth.dependencies import AuthenticatedUser, require_role
from app.auth.rbac import UserRole
from app.services.timer_service import TimerService
from app.services.socket_manager import sio, emit_notification
logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/escalations",
    tags=["Escalations"]
)

class ExtendSLARequest(BaseModel):
    minutes: int

class CancelJobRequest(BaseModel):
    reason: str

class ForceAssignRequest(BaseModel):
    tech_id: str
    reason: str

def get_job_for_user(
    db: Session,
    job_id: int,
    current_user: AuthenticatedUser,
) -> Job:
    """Find a job that the authenticated user is allowed to access."""

    query = db.query(Job).filter(
        Job.id == job_id
    )

    if not current_user.is_super_admin:
        query = query.filter(
            Job.tenant_id == current_user.tenant_id
        )

    job = query.first()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    return job

def get_active_escalation(db: Session, job_id: int, current_user: Optional[AuthenticatedUser] = None):
    query = db.query(SLAEscalation).filter(
        SLAEscalation.job_id == job_id,
        SLAEscalation.manager_responded_at.is_(None)
    )
    if current_user and not current_user.is_super_admin:
        query = query.filter(SLAEscalation.tenant_id == current_user.tenant_id)
    esc = query.first()
    if not esc:
        raise HTTPException(status_code=404, detail="Active escalation not found for this job")
    return esc

def mark_responded(db: Session, esc: SLAEscalation, action: str):
    esc.manager_responded_at = datetime.now(timezone.utc)
    esc.action_taken = action


@router.post("/{job_id}/extend-sla")
def extend_sla(
    job_id: int,
    payload: ExtendSLARequest,
    current_user: AuthenticatedUser = Depends(
        require_role(
            UserRole.SUPER_ADMIN,
            UserRole.DISPATCHER,
        )
    ),
    db: Session = Depends(get_db),
):
    if payload.minutes <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Minutes must be greater than zero",
        )

    job = get_job_for_user(
        db,
        job_id,
        current_user,
    )

    esc = get_active_escalation(
        db,
        job_id,
        current_user,
    )

    if job.sla_deadline:
        if job.sla_deadline.tzinfo is None:
            sla_datetime = job.sla_deadline.replace(
                tzinfo=timezone.utc
            )
        else:
            sla_datetime = job.sla_deadline

        job.sla_deadline = (
            sla_datetime
            + timedelta(minutes=payload.minutes)
        )

    old_status = job.status
    job.status = "QUEUED"

    audit = AuditEvent(
        tech_id=str(current_user.user_id),
        tenant_id=job.tenant_id,
        event_type="ESCALATION_ACTION",
        old_status=old_status,
        new_status="QUEUED",
        reason=(
            f"SLA extended by {payload.minutes} minutes"
        ),
    )
    db.add(audit)

    mark_responded(db,esc,f"Extended SLA by {payload.minutes} min",)

    try:
        db.commit()
        db.refresh(job)
    except Exception:
        db.rollback()
        logger.exception(
            "Failed to extend SLA for job %s",
            job_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to extend SLA",
        )

    logger.info(
        "Escalation resolved: SLA extended for job %s",
        job_id,
    )

    return {
        "message": "SLA extended",
        "new_deadline": job.sla_deadline,
    }

@router.post("/{job_id}/cancel")
def cancel_job(
    job_id: int,
    payload: CancelJobRequest,
    current_user: AuthenticatedUser = Depends(
        require_role(
            UserRole.SUPER_ADMIN,
            UserRole.DISPATCHER,
        )
    ),
    db: Session = Depends(get_db),
):
    job = get_job_for_user(
        db,
        job_id,
        current_user,
    )

    esc = get_active_escalation(
        db,
        job_id,
        current_user,
    )

    old_status = job.status
    job.status = "CANCELLED"

    audit = AuditEvent(
        tech_id=str(current_user.user_id),
        tenant_id=job.tenant_id,
        event_type="ESCALATION_ACTION",
        old_status=old_status,
        new_status="CANCELLED",
        reason=f"Job cancelled: {payload.reason}",
    )
    db.add(audit)

    mark_responded(
        db,
        esc,
        "Cancelled Job",
    )

    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception(
            "Failed to cancel escalated job %s",
            job_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to cancel job",
        )

    logger.info(
        "Escalation resolved: Job %s cancelled",
        job_id,
    )

    return {
        "message": "Job cancelled successfully"
    }

@router.post("/{job_id}/force-assign")
async def force_assign(
    job_id: int,
    payload: ForceAssignRequest,
    current_user: AuthenticatedUser = Depends(
        require_role(
            UserRole.SUPER_ADMIN,
            UserRole.DISPATCHER,
        )
    ),
    db: Session = Depends(get_db),
    redis_client=Depends(get_redis_client),
):
    job = get_job_for_user(
        db,
        job_id,
        current_user,
    )

    tech = db.query(Technician).filter(
        Technician.tech_id == payload.tech_id,
        Technician.tenant_id == job.tenant_id,
    ).first()

    if not tech and payload.tech_id.isdigit():
        tech = db.query(Technician).filter(
            Technician.technician_id
            == int(payload.tech_id),
            Technician.tenant_id == job.tenant_id,
        ).first()

    if not tech:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Technician not found",
        )

    if not tech.tech_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Technician is not linked with a tech_id. "
                "Complete the technician-user linkage first."
            ),
        )

    recipient_tech_id = tech.tech_id

    technician_status = (
        tech.technician_status or ""
    ).upper().strip()

    if technician_status in {"OFFLINE", "BUSY"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Technician is unavailable. "
                "Busy or offline technicians cannot be assigned jobs."
            ),
        )

    escalation = get_active_escalation(
        db,
        job_id,
        current_user,
    )

    old_status = job.status
    job.status = "ASSIGNED"
    job.assigned_technician_id = tech.technician_id

    audit = AuditEvent(
        tech_id=recipient_tech_id,
        tenant_id=job.tenant_id,
        event_type="ESCALATION_ACTION",
        old_status=old_status,
        new_status="ASSIGNED",
        reason=(
            f"Force-assigned by {current_user.role.value}: "
            f"{payload.reason}"
        ),
    )
    db.add(audit)

    notification_id = str(uuid.uuid4())

    notification_body = (
        f"You have been manually assigned to an escalated job: "
        f"{job.service_type} at {job.location}. "
        f"Reason: {payload.reason}"
    )

    db_notification = InAppNotification(
        id=notification_id,
        tenant_id=job.tenant_id,
        tech_id=recipient_tech_id,
        job_id=str(job.id),
        type="JOB_ASSIGNED",
        title="Escalated Job Assignment",
        body=notification_body,
        status="UNREAD",
        priority="HIGH",
        created_at=datetime.now(timezone.utc),
    )
    db.add(db_notification)

    mark_responded(
        db,
        escalation,
        f"Force Assigned to {recipient_tech_id}",
    )

    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception(
            "Failed to force-assign escalated job %s",
            job_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to force-assign job",
        )

    notification_payload = {
        "id": notification_id,
        "tenant_id": job.tenant_id,
        "tech_id": recipient_tech_id,
        "job_id": str(job.id),
        "type": "JOB_ASSIGNED",
        "title": "Escalated Job Assignment",
        "body": notification_body,
        "status": "UNREAD",
        "priority": "HIGH",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "job": {
            "id": job.id,
            "title": f"{job.service_type} - {job.location}",
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

    TimerService.start_timer(
        redis_client,
        str(job.id),
        recipient_tech_id,
    )

    await sio.emit(
        "redispatch:dismiss",
        {
            "job_id": job.id,
            "tenant_id": job.tenant_id,
        },
    )

    logger.info(
        "Escalation resolved: Job %s force-assigned to tech %s",
        job_id,
        recipient_tech_id,
    )

    return {
        "message": "Job force-assigned successfully",
        "job_id": job.id,
        "technician_id": recipient_tech_id,
    }
