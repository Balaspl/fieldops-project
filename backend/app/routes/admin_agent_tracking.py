"""Read-only job and AI-agent workflow tracking for super admins."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload

from ..auth.dependencies import AuthenticatedUser, get_current_user
from ..auth.rbac import UserRole
from ..database import get_db
from ..models import AuditEvent, Job, JobMessage, SentimentThreadMessage


router = APIRouter(
    prefix="/api/admin/agent-tracking",
    tags=["Agent Tracking"],
)

ACCEPTED_STATUSES = {
    "ACCEPTED",
    "EN_ROUTE",
    "ON_SITE",
    "IN_PROGRESS",
    "COMPLETED",
    "CLOSED",
}
TERMINAL_STATUSES = {"COMPLETED", "CLOSED", "CANCELLED", "CANCELED"}


def _utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.isoformat() + "Z"
    return value.isoformat()


def _stage(
    key: str,
    label: str,
    state: str,
    detail: str,
    timestamp: datetime | None = None,
) -> dict:
    return {
        "key": key,
        "label": label,
        "state": state,
        "detail": detail,
        "timestamp": _utc_iso(timestamp),
    }


def _track_job(job: Job) -> dict:
    status = str(job.status or "CREATED").strip().upper().replace(" ", "_")
    is_closed = status in {"CLOSED", "CANCELLED", "CANCELED"} or bool(
        job.closed_at or job.cancelled_at
    )
    is_completed = status == "COMPLETED" or bool(job.completed_at)
    is_accepted = (
        status in ACCEPTED_STATUSES
        or bool(job.en_route_at or job.on_site_at or job.work_started_at)
    )
    is_assigned = job.assigned_technician_id is not None or job.assigned_at is not None
    waiting_for_acceptance = is_assigned and not is_accepted and not is_closed

    if is_closed:
        current_agent = "Workflow complete" if job.closed_at or status == "CLOSED" else "Workflow cancelled"
        current_detail = "The job has reached a terminal state."
    elif is_completed:
        current_agent = "Closure Agent"
        current_detail = "The job is completed and awaiting final closure."
    elif waiting_for_acceptance:
        current_agent = "Dispatcher"
        current_detail = "Waiting for the assigned technician to accept."
    elif is_accepted and status in {"EN_ROUTE", "ON_SITE", "IN_PROGRESS"}:
        current_agent = "Technician Work"
        current_detail = "The technician is carrying out the assigned service."
    elif is_accepted:
        current_agent = "Communication Agent"
        current_detail = "The assignment was accepted; service updates are event-driven."
    else:
        current_agent = "Planning Agent"
        current_detail = "Preparing the job for technician dispatch."

    assigned_time = job.assigned_at
    stages = [
        _stage(
            "intake",
            "Request Received",
            "complete",
            "Job request was accepted into the workflow.",
            job.created_at,
        ),
        _stage(
            "planning",
            "Plan Job",
            "complete" if is_assigned or is_accepted or is_closed else "active",
            "Technician assignment is recorded." if is_assigned or is_accepted else "Preparing technician options.",
            assigned_time if is_assigned else None,
        ),
        _stage(
            "dispatch",
            "Assign Technician",
            "complete" if is_accepted or is_closed else "waiting" if waiting_for_acceptance else "active",
            "Technician accepted the assignment." if is_accepted else "Waiting for technician acceptance." if waiting_for_acceptance else "Finding and assigning a technician.",
            assigned_time,
        ),
        _stage(
            "communication",
            "Communicate",
            "event_driven" if is_accepted else "locked",
            "Runs on assignment and job updates." if is_accepted else "Available after technician acceptance.",
            job.updated_at if is_accepted else None,
        ),
        _stage(
            "technician_work",
            "Track Work",
            "complete" if is_completed else "active" if status in {"EN_ROUTE", "ON_SITE", "IN_PROGRESS"} else "locked",
            "Technician completed the service." if is_completed else "Technician is working on the service." if status in {"EN_ROUTE", "ON_SITE", "IN_PROGRESS"} else "Starts after the technician accepts and begins the visit.",
            job.work_started_at or job.on_site_at or job.en_route_at,
        ),
        _stage(
            "sentiment",
            "Check Customer Mood",
            "event_driven" if is_accepted else "locked",
            "Runs when customer messages need analysis." if is_accepted else "Available after technician acceptance.",
        ),
        _stage(
            "closure",
            "Close Job",
            "complete" if is_closed and status not in {"CANCELLED", "CANCELED"} else "active" if is_completed else "locked",
            "Job closure is complete." if is_closed and status not in {"CANCELLED", "CANCELED"} else "Preparing final closure." if is_completed else "Starts when service is completed.",
            job.closed_at or job.completed_at,
        ),
    ]

    technician = getattr(job, "technician", None)
    return {
        "job_id": job.id,
        "job_number": getattr(job, "job_number", None) or job.id,
        "service_type": job.service_type,
        "status": status,
        "priority": job.priority,
        "technician_name": getattr(technician, "technician_name", None),
        "created_at": _utc_iso(job.created_at),
        "updated_at": _utc_iso(job.updated_at),
        "assigned_at": _utc_iso(job.assigned_at),
        "accepted": is_accepted,
        "current_agent": current_agent,
        "current_detail": current_detail,
        "stages": stages,
    }


def _event(timestamp: datetime | None, agent: str, title: str, detail: str, kind: str, **extra) -> dict:
    return {
        "timestamp": _utc_iso(timestamp),
        "agent": agent,
        "title": title,
        "detail": detail,
        "kind": kind,
        **extra,
    }


@router.get("/{job_id}")
def get_agent_tracking_job(
    job_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    from fastapi import HTTPException, status

    if current_user.role not in {UserRole.HEAD, UserRole.SUPER_ADMIN}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Agent tracking is restricted to Super Admin.")

    query = db.query(Job).options(joinedload(Job.technician)).filter(Job.id == job_id)
    if current_user.role == UserRole.SUPER_ADMIN:
        query = query.filter(Job.tenant_id == current_user.tenant_id)
    job = query.first()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")

    tracked = _track_job(job)
    events = [
        _event(job.created_at, "Intake Agent", "Request received", f"Service request received for {job.service_type or 'service'}.", "intake"),
        _event(job.assigned_at or job.created_at, "Planning Agent", "Job prepared for dispatch", "Request details were prepared for technician assignment.", "planning"),
    ]
    if job.assigned_at:
        events.append(_event(job.assigned_at, "Dispatcher Agent", "Technician assigned", f"{tracked['technician_name'] or 'A technician'} was assigned to the job.", "dispatch"))
    if job.en_route_at:
        events.append(_event(job.en_route_at, "Technician", "Travel started", "Technician started travelling to the service location.", "work"))
    if job.on_site_at:
        events.append(_event(job.on_site_at, "Technician", "Arrived on site", "Technician arrived at the service location.", "work"))
    if job.work_started_at:
        events.append(_event(job.work_started_at, "Technician", "Work started", "Technician started the service work.", "work"))
    if job.completed_at:
        events.append(_event(job.completed_at, "Technician", "Service completed", "Technician marked the service as complete.", "work"))
    if job.closed_at:
        events.append(_event(job.closed_at, "Closure Agent", "Job closed", job.closure_reason or "The job was closed.", "closure"))
    if job.cancelled_at:
        events.append(_event(job.cancelled_at, "Dispatcher Agent", "Job cancelled", job.cancellation_reason or "The job was cancelled.", "dispatch"))

    audit_query = db.query(AuditEvent).filter(AuditEvent.job_id == str(job.id))
    if current_user.role == UserRole.SUPER_ADMIN:
        audit_query = audit_query.filter(AuditEvent.tenant_id == current_user.tenant_id)
    for record in audit_query.order_by(AuditEvent.timestamp.asc(), AuditEvent.id.asc()).all():
        events.append(_event(record.timestamp or record.created_at, "Workflow Log", record.event_type.replace("_", " ").title(), record.reason or str(record.details or "Job status updated."), "audit"))

    message_query = db.query(JobMessage).filter(JobMessage.job_id == job.id)
    if current_user.role == UserRole.SUPER_ADMIN:
        message_query = message_query.filter(JobMessage.tenant_id == current_user.tenant_id)
    for message in message_query.order_by(JobMessage.created_at.asc()).all():
        events.append(_event(message.created_at, "Communication Agent", f"{message.sender_role.title()} message", message.body, "communication", message_id=message.id, sender_role=message.sender_role))

    sentiment_query = db.query(SentimentThreadMessage).filter(SentimentThreadMessage.job_id == job.id)
    if current_user.role == UserRole.SUPER_ADMIN:
        sentiment_query = sentiment_query.filter(SentimentThreadMessage.tenant_id == current_user.tenant_id)
    for record in sentiment_query.order_by(SentimentThreadMessage.created_at.asc()).all():
        mood = record.sentiment or "Analyzed"
        detail = record.summary or record.message
        events.append(_event(record.created_at, "Sentiment Agent", f"Customer mood: {mood}", detail, "sentiment", source_message_id=record.source_message_id, emotion=record.emotion, confidence=record.confidence))

    events.sort(key=lambda item: item["timestamp"] or "")
    return {
        **tracked,
        "customer_name": job.customer_name,
        "location": job.site_address or job.location,
        "preferred_service_date": str(job.preferred_service_date) if job.preferred_service_date else None,
        "preferred_service_time": str(job.preferred_service_time) if job.preferred_service_time else None,
        "events": events,
    }


@router.get("")
def get_agent_tracking(
    limit: int = Query(100, ge=1, le=250),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    # The platform HEAD role is allowed to inspect jobs across organizations;
    # organization Super Admins remain scoped to their own tenant.
    if current_user.role not in {UserRole.HEAD, UserRole.SUPER_ADMIN}:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Agent tracking is restricted to Super Admin.",
        )

    query = db.query(Job).options(joinedload(Job.technician))
    if current_user.role == UserRole.SUPER_ADMIN:
        query = query.filter(Job.tenant_id == current_user.tenant_id)
    jobs = query.order_by(Job.updated_at.desc(), Job.id.desc()).limit(limit).all()
    tracked_jobs = [_track_job(job) for job in jobs]

    return {
        "jobs": tracked_jobs,
        "total": len(tracked_jobs),
        "active": sum(
            1
            for job in tracked_jobs
            if job["status"] not in TERMINAL_STATUSES
        ),
        "waiting_acceptance": sum(
            1
            for job in tracked_jobs
            if job["current_agent"] == "Dispatcher"
        ),
        "generated_at": _utc_iso(datetime.now(timezone.utc)),
    }
