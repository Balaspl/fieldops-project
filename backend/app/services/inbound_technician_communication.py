"""Route technician SMS into the existing authenticated job chat history."""

from __future__ import annotations

import re
import uuid

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Job, JobMessage, ServiceRequest, TechnicianProfile
from app.models.user import User
from app.models_legacy import Technician

CHAT_ENABLED_STATUSES = {
    "ACCEPTED", "EN_ROUTE", "ENROUTE", "ON_SITE", "ONSITE",
    "IN_PROGRESS", "IN PROGRESS",
}


def _technician_user(db: Session, technician: Technician) -> User | None:
    if technician.tech_id:
        user = db.query(User).filter(
            User.id == str(technician.tech_id),
            User.tenant_id == str(technician.tenant_id),
            func.lower(User.role) == "technician",
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        ).first()
        if user:
            return user

    profile = db.query(TechnicianProfile).filter(
        TechnicianProfile.tenant_id == str(technician.tenant_id),
        func.lower(TechnicianProfile.full_name)
        == (technician.technician_name or "").strip().lower(),
    ).all()
    if len(profile) != 1:
        return None
    return db.query(User).filter(
        User.id == profile[0].user_id,
        User.tenant_id == str(technician.tenant_id),
        func.lower(User.role) == "technician",
        User.is_active.is_(True),
        User.deleted_at.is_(None),
    ).first()


def _requested_job_id(body: str) -> int | None:
    match = re.search(r"\b(?:job\s*#?|#)\s*(\d+)\b", body, re.IGNORECASE)
    return int(match.group(1)) if match else None


def handle_technician_sms(
    db: Session,
    *,
    technician: Technician,
    body: str,
    message_sid: str,
) -> dict[str, int | str | bool]:
    """Persist one technician SMS only when its job is unambiguous and valid."""
    if technician.sms_opt_out:
        return {"status": "opted_out", "stored": False}

    technician_user = _technician_user(db, technician)
    if technician_user is None:
        return {"status": "technician_account_not_found", "stored": False}
    technician_user_id = str(technician_user.id)

    message_id = str(
        uuid.uuid5(uuid.NAMESPACE_URL, f"fieldops:twilio:{message_sid}")
    )
    prior_message = db.query(JobMessage.job_id).filter(
        JobMessage.id == message_id,
        JobMessage.tenant_id == str(technician.tenant_id),
    ).first()
    if prior_message:
        return {
            "status": "duplicate",
            "job_id": prior_message.job_id,
            "technician_user_id": technician_user_id,
            "stored": False,
        }

    jobs = db.query(Job).filter(
        Job.tenant_id == str(technician.tenant_id),
        Job.assigned_technician_id == technician.technician_id,
        func.upper(Job.status).in_(CHAT_ENABLED_STATUSES),
    ).all()
    requested_id = _requested_job_id(body)
    if requested_id is not None:
        job = next((item for item in jobs if item.id == requested_id), None)
        if job is None:
            return {"status": "job_not_assigned_or_chat_unavailable", "technician_user_id": technician_user_id, "stored": False}
    elif len(jobs) == 1:
        job = jobs[0]
    elif not jobs:
        return {"status": "no_active_chat_job", "technician_user_id": technician_user_id, "stored": False}
    else:
        return {"status": "job_selection_required", "technician_user_id": technician_user_id, "stored": False}

    message_body = re.sub(
        r"^\s*(?:job\s*#?\s*\d+|#\s*\d+)[\s:,-]*",
        "",
        body,
        count=1,
        flags=re.IGNORECASE,
    ).strip() or body.strip()
    message = JobMessage(
        id=message_id,
        job_id=job.id,
        tenant_id=job.tenant_id,
        sender_user_id=technician_user_id,
        sender_role="TECHNICIAN",
        body=message_body[:4000],
    )
    db.add(message)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return {"status": "duplicate", "job_id": job.id, "stored": False}
    db.refresh(message)

    requests = db.query(ServiceRequest).filter(
        ServiceRequest.linked_job_id == job.id,
    ).all()
    if len(requests) != 1 or not requests[0].customer_user_id:
        # Keep the durable technician message; the job still appears in the
        # technician portal, while customer delivery needs a unique owner.
        return {"status": "stored_customer_owner_ambiguous", "job_id": job.id, "technician_user_id": technician_user_id, "stored": True}

    return {
        "status": "stored",
        "job_id": job.id,
        "message_id": message.id,
        "customer_user_id": str(requests[0].customer_user_id),
        "sender_user_id": technician_user_id,
        "sender_role": "TECHNICIAN",
        "body": message.body,
        "created_at": message.created_at.isoformat() if message.created_at else None,
        "stored": True,
    }
