"""Authenticated, per-job customer/technician messaging API."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..auth.dependencies import AuthenticatedUser, get_current_user
from ..database import get_db
from ..models import Job, JobMessage, ServiceRequest, Technician
from ..models.technician_profile import TechnicianProfile
from ..models.user import User
from ..services.socket_manager import sio


router = APIRouter(prefix="/api/v1/job-messages", tags=["Job Messages"])
TERMINAL_READ_ONLY = {"COMPLETED", "CLOSED", "CANCELLED", "CANCELED"}
CHAT_ENABLED_STATUSES = {
    # ASSIGNED means the technician has been selected but has not accepted yet.
    # Customer/technician messaging becomes available only after acceptance.
    "ACCEPTED",
    "EN_ROUTE",
    "ENROUTE",
    "ON_SITE",
    "ONSITE",
    "IN_PROGRESS",
    "IN PROGRESS",
}


class MessageCreate(BaseModel):
    model_config = {"extra": "forbid"}
    body: str = Field(min_length=1, max_length=4000)


def _role(user: AuthenticatedUser) -> str:
    return str(getattr(user.role, "value", user.role)).upper()


def _technician_for_user(db: Session, user: AuthenticatedUser):
    numeric_id = int(user.user_id) if str(user.user_id).isdigit() else -1
    tech = db.query(Technician).filter(
        Technician.tenant_id == user.tenant_id,
        or_(Technician.tech_id == user.user_id, Technician.technician_id == numeric_id),
    ).first()
    if tech:
        return tech
    profile = db.query(TechnicianProfile).filter(
        TechnicianProfile.user_id == user.user_id,
        TechnicianProfile.tenant_id == user.tenant_id,
    ).first()
    if not profile:
        return None
    matches = db.query(Technician).filter(
        Technician.tenant_id == user.tenant_id,
        func.lower(Technician.technician_name) == profile.full_name.strip().lower(),
    ).all()
    return matches[0] if len(matches) == 1 else None


def _context(db: Session, job_id: int, user: AuthenticatedUser):
    role = _role(user)
    job = db.query(Job).filter(Job.id == job_id).first()
    if job is None:
        raise HTTPException(404, "Job not found")
    customer_requests = db.query(ServiceRequest).filter(
        ServiceRequest.linked_job_id == job_id,
    ).all()
    owner_request = db.query(ServiceRequest).filter(
        ServiceRequest.linked_job_id == job_id,
        ServiceRequest.customer_user_id == user.user_id,
        ServiceRequest.tenant_id == user.tenant_id,
    ).first()
    tech = _technician_for_user(db, user) if role == "TECHNICIAN" else None
    is_customer = role == "CUSTOMER" and owner_request is not None
    is_current_tech = tech is not None and job.assigned_technician_id == tech.technician_id
    if not (is_customer or is_current_tech):
        # Same 404 for missing and unauthorized jobs prevents job enumeration.
        raise HTTPException(404, "Job not found")
    status = str(job.status or "").strip().upper()
    can_send = (
        job.assigned_technician_id is not None
        and status in CHAT_ENABLED_STATUSES
    )
    customer_user_id = user.user_id if is_customer else (
        customer_requests[0].customer_user_id if len(customer_requests) == 1 else None
    )
    assigned_tech = db.query(Technician).filter(
        Technician.technician_id == job.assigned_technician_id
    ).first() if job.assigned_technician_id is not None else None
    technician_user_id = str(assigned_tech.tech_id) if assigned_tech and assigned_tech.tech_id else None
    technician_profile = db.query(TechnicianProfile).filter(
        TechnicianProfile.user_id == technician_user_id
    ).first() if technician_user_id else None
    if technician_profile:
        technician_name = technician_profile.full_name
    else:
        technician_name = assigned_tech.technician_name if assigned_tech else None
    if not technician_user_id and assigned_tech:
        numeric_id = str(assigned_tech.technician_id)
        linked_profile = db.query(TechnicianProfile).filter(
            TechnicianProfile.tenant_id == assigned_tech.tenant_id,
            func.lower(TechnicianProfile.full_name) == assigned_tech.technician_name.strip().lower(),
        ).first()
        technician_user_id = linked_profile.user_id if linked_profile else None
    if not technician_user_id:
        # A job may have a legacy technician record without an authenticated
        # account. Keep history readable but do not create a dead-end chat.
        can_send = False
    if not customer_user_id:
        can_send = False
    elif assigned_tech:
        technician_account = db.query(User).filter(
            User.id == technician_user_id,
            User.tenant_id == assigned_tech.tenant_id,
            User.role == "technician",
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        ).first()
        if technician_account is None:
            technician_user_id = None
            can_send = False
    return job, owner_request, tech, customer_user_id, technician_user_id, technician_name, can_send


def _message_json(message: JobMessage, current_user_id: str) -> dict:
    return {
        "id": message.id,
        "job_id": message.job_id,
        "sender_user_id": message.sender_user_id,
        "sender_role": message.sender_role,
        "body": message.body,
        "created_at": message.created_at.isoformat() if message.created_at else None,
        "delivered_at": message.delivered_at.isoformat() if message.delivered_at else None,
        "read_at": message.read_at.isoformat() if message.read_at else None,
        "is_mine": message.sender_user_id == current_user_id,
    }


@router.get("/jobs/{job_id}")
async def get_job_messages(job_id: int, user: AuthenticatedUser = Depends(get_current_user), db: Session = Depends(get_db)):
    job, owner_request, tech, customer_id, technician_id, technician_name, can_send = _context(db, job_id, user)
    now = datetime.now(timezone.utc)
    incoming = db.query(JobMessage).filter(
        JobMessage.job_id == job_id,
        JobMessage.tenant_id == job.tenant_id,
        JobMessage.sender_user_id != user.user_id,
        JobMessage.read_at.is_(None),
    )
    incoming.update({JobMessage.read_at: now}, synchronize_session=False)
    db.commit()
    messages = db.query(JobMessage).filter(
        JobMessage.job_id == job_id,
        JobMessage.tenant_id == job.tenant_id,
    ).order_by(JobMessage.created_at.asc(), JobMessage.id.asc()).all()
    # Notify the other participant that their messages have been read.
    if messages and customer_id and technician_id:
        other_id = technician_id if user.user_id == customer_id else customer_id
        try:
            await sio.emit("job_message_read", {"job_id": job_id, "reader_user_id": user.user_id, "read_at": now.isoformat()}, room=f"user_{other_id}")
        except Exception:
            pass
    status = str(job.status or "").strip().upper()
    if status in TERMINAL_READ_ONLY:
        read_only_reason = "Messaging is read-only after job completion or cancellation."
    elif not job.assigned_technician_id:
        read_only_reason = "Chat is available after technician assignment."
    elif status not in CHAT_ENABLED_STATUSES:
        read_only_reason = "Chat is available after the assigned technician accepts the job."
    elif technician_id is None:
        read_only_reason = "The assigned technician does not have an active portal account."
    else:
        read_only_reason = None

    return {
        "job_id": job_id,
        "job_reference": f"JOB-{job_id}",
        "status": job.status,
        "technician_name": technician_name,
        "participant_name": job.customer_name if _role(user) == "TECHNICIAN" else technician_name,
        "assigned": job.assigned_technician_id is not None,
        "can_send": can_send,
        "read_only_reason": read_only_reason,
        "unread_count": 0,
        "messages": [_message_json(item, user.user_id) for item in messages],
    }


@router.get("/jobs/{job_id}/unread-count")
def get_unread_count(job_id: int, user: AuthenticatedUser = Depends(get_current_user), db: Session = Depends(get_db)):
    job, *_ = _context(db, job_id, user)
    count = db.query(func.count(JobMessage.id)).filter(
        JobMessage.job_id == job_id,
        JobMessage.tenant_id == job.tenant_id,
        JobMessage.sender_user_id != user.user_id,
        JobMessage.read_at.is_(None),
    ).scalar() or 0
    return {"job_id": job_id, "unread_count": int(count)}


@router.post("/jobs/{job_id}", status_code=201)
async def send_job_message(job_id: int, payload: MessageCreate, user: AuthenticatedUser = Depends(get_current_user), db: Session = Depends(get_db)):
    job, owner_request, tech, customer_id, technician_id, technician_name, can_send = _context(db, job_id, user)
    if not can_send:
        raise HTTPException(409, "Messaging is unavailable for this job.")
    body = payload.body.strip()
    if not body:
        raise HTTPException(422, "Message cannot be blank")
    role = _role(user)
    message = JobMessage(
        job_id=job.id,
        tenant_id=job.tenant_id,
        sender_user_id=user.user_id,
        sender_role=role,
        body=body,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    event = _message_json(message, user.user_id)
    event["is_mine"] = False
    recipient_id = technician_id if role == "CUSTOMER" else customer_id
    try:
        await sio.emit("job_message", {"job_id": job_id, "message": event}, room=f"user_{recipient_id}")
    except Exception:
        # Message is durable; clients recover it through history on reconnect.
        pass
    result = _message_json(message, user.user_id)
    result["delivery_status"] = "sent"
    return result


@router.post("/jobs/{job_id}/messages/{message_id}/delivered")
async def acknowledge_delivery(job_id: int, message_id: str, user: AuthenticatedUser = Depends(get_current_user), db: Session = Depends(get_db)):
    job, owner_request, tech, customer_id, technician_id, _, _ = _context(db, job_id, user)
    message = db.query(JobMessage).filter(
        JobMessage.id == message_id,
        JobMessage.job_id == job_id,
        JobMessage.tenant_id == job.tenant_id,
        JobMessage.sender_user_id != user.user_id,
    ).first()
    if message is None:
        raise HTTPException(404, "Message not found")
    now = datetime.now(timezone.utc)
    if message.delivered_at is None:
        message.delivered_at = now
        db.commit()
    sender_id = message.sender_user_id
    try:
        await sio.emit("job_message_delivered", {"job_id": job_id, "message_id": message_id, "delivered_at": now.isoformat()}, room=f"user_{sender_id}")
    except Exception:
        pass
    return {"message_id": message_id, "delivered_at": message.delivered_at.isoformat()}
