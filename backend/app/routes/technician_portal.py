"""
Technician Portal API routes.

All endpoints are scoped to the authenticated technician.

Technicians can only access their own profile, their own assigned jobs,

and their own notifications.

Cross-tenant jobs:

    A job may belong to one organization (Job.tenant_id) and be offered to,

    accepted by, and worked by a technician from a different organization.

    Authorization for job actions is therefore the ASSIGNMENT itself

    (Job.assigned_technician_id == the caller's technician record), never

    Job.tenant_id == caller's tenant. The technician record is always resolved

    from the caller's own user_id + tenant_id, so a technician can still only

    act on jobs assigned to them.

"""

import uuid

import logging

import base64

from datetime import datetime, timezone, date, timedelta

from io import BytesIO



from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status, Query

from fastapi.responses import StreamingResponse

from sqlalchemy.orm import Session

from sqlalchemy import func

from typing import Optional

from ..database import get_db

from ..auth.dependencies import AuthenticatedUser, require_permission

from ..auth.rbac import Permission

from ..auth.password import hash_password, verify_password

from ..models import (

    Job, Technician, InAppNotification,

    TechnicianProfile,

)

from ..models_legacy import(
    RedispatchAttempt,
)

from app.services.ai.FieldOpsAI.agents.dispatcher_agent.dispatcher_runtime import (
    get_dispatcher_runtime,
)

import asyncio
from app.services.timer_service import TimerService
from app.redis_client import get_redis_client

from ..models.user import User
from ..models import ServiceRequest
from ..models.job_closure import JobClosure
from ..models.customer_signature import CustomerSignature
from ..portal_schemas import (
    TechnicianProfileCreate, TechnicianProfileUpdate, TechnicianProfileResponse,
    TechnicianJobResponse, TechnicianJobRejectRequest, TechnicianJobCompleteRequest,
    TechnicianDashboardResponse, ChangePasswordRequest,
)

from ..schemas import TechnicianAvailabilityUpdate, JobExpenseCreate, JobExpenseResponse

from ..services.job_expense_service import create_job_expense

from ..services.enterprise_audit import audit_log, AuditAction

from ..services.customer_notification_services import (
    create_customer_job_status_notification,
)

logger = logging.getLogger(__name__)

# Keep this aligned with the acceptance window in routes/jobs.py.

ACCEPTANCE_WINDOW_SECONDS = 600

router = APIRouter(

    prefix="/api/technician",

    tags=["Technician Portal"],

)

def _json_safe(value):

    if isinstance(value, (date, datetime)):

        return value.isoformat()

    return value

def _get_tech_for_user(

    db: Session,

    user_id: str,

    tenant_id: str,

) -> Optional[Technician]:

    """Find the technician record belonging to this user and organization."""

    logger.warning(

        "TECH LOOKUP: user_id=%s tenant_id=%s",

        user_id,

        tenant_id,

    )

    query = db.query(Technician).filter(

        Technician.tenant_id == tenant_id

    )

    # 1. Direct match by tech_id or integer technician_id

    numeric_user_id = int(user_id) if str(user_id).isdigit() else -1

    tech = query.filter(

        (Technician.tech_id == str(user_id))

        | (Technician.technician_id == numeric_user_id)

    ).first()

    if tech:

        return tech

    # 2. Find tenant-scoped profile and user

    profile = db.query(TechnicianProfile).filter(

        TechnicianProfile.user_id == str(user_id),

        TechnicianProfile.tenant_id == tenant_id,

    ).first()

    user = db.query(User).filter(User.id == str(user_id), User.tenant_id == tenant_id,).first()

    target_name = (

        profile.full_name

        if profile and profile.full_name

        else user.full_name if user else None

    )

    target_phone = (

        profile.mobile_number

        if profile and profile.mobile_number

        else user.phone_number if user else None

    )

    # query is already restricted by Technician.tenant_id

    if target_name:

        tech_by_name = query.filter(

            func.lower(Technician.technician_name)

            == target_name.lower().strip()

        ).first()

        if tech_by_name:

            tech_by_name.tech_id = str(user_id)

            try:

                db.commit()

            except Exception:

                db.rollback()

                raise

            return tech_by_name

    if target_phone:

        tech_by_phone = query.filter(

            Technician.phone_number == target_phone.strip()

        ).first()

        if tech_by_phone:

            tech_by_phone.tech_id = str(user_id)

            try:

                db.commit()

            except Exception:

                db.rollback()

                raise

            return tech_by_phone

    return None

def _get_my_job(

    db: Session,

    job_id: int,

    tech: Technician,

) -> Optional[Job]:

    """

    Return the job only if it is assigned to this technician.

    Deliberately NOT scoped by Job.tenant_id: a job may belong to one

    organization and be offered to a technician from another. Authorization is

    the assignment itself, and `tech` was resolved from the caller's own

    user_id + tenant_id.

    """

    return (

        db.query(Job)

        .filter(

            Job.id == job_id,

            Job.assigned_technician_id == tech.technician_id,

        )

        .first()

    )

def _get_notification_recipient_ids(

    user_id: str,

    tech: Optional[Technician],

) -> list[str]:

    """Return every valid notification recipient ID for this technician."""

    recipient_ids = {str(user_id)}

    if tech:

        recipient_ids.add(str(tech.technician_id))

        if tech.tech_id:

            recipient_ids.add(str(tech.tech_id))

    return list(recipient_ids)

# ──────────────────────────────────────────────────

# Profile Endpoints

# ──────────────────────────────────────────────────

@router.get("/profile", response_model=TechnicianProfileResponse)

async def get_technician_profile(

    current_user: AuthenticatedUser = Depends(require_permission(Permission.TECHNICIANS_VIEW_OWN)),

    db: Session = Depends(get_db),

):

    """Get the current technician's profile."""

    profile = db.query(TechnicianProfile).filter(

        TechnicianProfile.user_id == current_user.user_id,

        TechnicianProfile.tenant_id == current_user.tenant_id,

    ).first()

    user = db.query(User).filter(User.id == current_user.user_id, User.tenant_id == current_user.tenant_id,).first()

    if not profile:

        # Return a minimal response indicating profile not completed

        return TechnicianProfileResponse(

            id="",

            user_id=current_user.user_id,

            tenant_id=current_user.tenant_id,

            full_name=user.full_name if user else "",

            mobile_number=(user.phone_number if user and user.phone_number else ""),

            profile_completed=False,

            email=user.email if user else "",

            created_at=datetime.now(timezone.utc),

            updated_at=datetime.now(timezone.utc),

        )

    # Calculate age

    age = None

    if profile.date_of_birth:

        today = date.today()

        age = today.year - profile.date_of_birth.year - (

            (today.month, today.day) < (profile.date_of_birth.month, profile.date_of_birth.day)

        )

    return TechnicianProfileResponse(

        id=profile.id,

        user_id=profile.user_id,

        tenant_id=profile.tenant_id,

        full_name=profile.full_name,

        profile_photo=profile.profile_photo,

        mobile_number=profile.mobile_number,

        date_of_birth=profile.date_of_birth,

        age=age,

        gender=profile.gender,

        address=profile.address,

        city=profile.city,

        state=profile.state,

        pincode=profile.pincode,

        emergency_contact=profile.emergency_contact,

        skills=profile.skills,

        experience=profile.experience,

        certifications=profile.certifications,

        profile_completed=profile.profile_completed,

        email=user.email if user else None,

        created_at=profile.created_at,

        updated_at=profile.updated_at,

    )

@router.post("/profile", response_model=TechnicianProfileResponse, status_code=201)

async def create_technician_profile(

    data: TechnicianProfileCreate,

    request: Request,

    current_user: AuthenticatedUser = Depends(require_permission(Permission.TECHNICIANS_VIEW_OWN)),

    db: Session = Depends(get_db),

):

    """Create technician profile (first-time setup)."""

    existing = db.query(TechnicianProfile).filter(

        TechnicianProfile.user_id == current_user.user_id,

        TechnicianProfile.tenant_id == current_user.tenant_id,

    ).first()

    if existing:

        raise HTTPException(

            status_code=status.HTTP_409_CONFLICT,

            detail="Profile already exists. Use PUT to update.",

        )

    profile = TechnicianProfile(

        id=str(uuid.uuid4()),

        user_id=current_user.user_id,

        tenant_id=current_user.tenant_id,

        full_name=data.full_name,

        profile_photo=data.profile_photo,

        mobile_number=data.mobile_number,

        date_of_birth=data.date_of_birth,

        gender=data.gender,

        address=data.address,

        city=data.city,

        state=data.state,

        pincode=data.pincode,

        emergency_contact=data.emergency_contact,

        skills=data.skills,

        experience=data.experience,

        certifications=data.certifications,

        profile_completed=True,

    )

    db.add(profile)

    # Sync to main technicians table for main app visibility

    try:

        skill_str = ", ".join(profile.skills) if profile.skills else "General Technician"

        loc_str = profile.address or f"{profile.city or ''}, {profile.state or ''}".strip(", ") or "Main Zone"

        tech = db.query(Technician).filter(

            Technician.tenant_id == current_user.tenant_id,

            (

                Technician.tech_id == str(current_user.user_id)

            )

            | (

                Technician.technician_name == profile.full_name

            ),

        ).first()

        if not tech:

            tech = Technician(

                tech_id=str(current_user.user_id),

                tenant_id=current_user.tenant_id,

                technician_name=profile.full_name,

                technician_skill=skill_str,

                technician_location=loc_str,

                phone_number=profile.mobile_number,

                technician_status="OFFLINE",

                current_jobs=0,

                max_jobs=5,

            )

            db.add(tech)

        else:

            tech.tech_id = str(current_user.user_id)

            tech.technician_name = profile.full_name

            if profile.mobile_number:

                tech.phone_number = profile.mobile_number

            tech.technician_skill = skill_str

            tech.technician_location = loc_str

    except Exception as sync_err:

        logger.warning(f"Could not auto-sync technician record: {sync_err}")

    audit_log(

        db,

        action=AuditAction.PROFILE_CREATED,

        tenant_id=current_user.tenant_id,

        user_id=current_user.user_id,

        role=current_user.role.value,

        entity_type="technician_profile",

        entity_id=profile.id,

        new_value={"full_name": data.full_name},

        request=request,

    )

    db.commit()

    db.refresh(profile)

    user = db.query(User).filter(User.id == current_user.user_id, User.tenant_id == current_user.tenant_id,).first()

    age = None

    if profile.date_of_birth:

        today = date.today()

        age = today.year - profile.date_of_birth.year - (

            (today.month, today.day) < (profile.date_of_birth.month, profile.date_of_birth.day)

        )

    return TechnicianProfileResponse(

        id=profile.id,

        user_id=profile.user_id,

        tenant_id=profile.tenant_id,

        full_name=profile.full_name,

        profile_photo=profile.profile_photo,

        mobile_number=profile.mobile_number,

        date_of_birth=profile.date_of_birth,

        age=age,

        gender=profile.gender,

        address=profile.address,

        city=profile.city,

        state=profile.state,

        pincode=profile.pincode,

        emergency_contact=profile.emergency_contact,

        skills=profile.skills,

        experience=profile.experience,

        certifications=profile.certifications,

        profile_completed=profile.profile_completed,

        email=user.email if user else None,

        created_at=profile.created_at,

        updated_at=profile.updated_at,

    )

@router.put("/profile", response_model=TechnicianProfileResponse)

async def update_technician_profile(

    data: TechnicianProfileUpdate,

    request: Request,

    current_user: AuthenticatedUser = Depends(require_permission(Permission.TECHNICIANS_VIEW_OWN)),

    db: Session = Depends(get_db),

):

    """Update technician profile."""

    profile = db.query(TechnicianProfile).filter(

        TechnicianProfile.user_id == current_user.user_id,

        TechnicianProfile.tenant_id == current_user.tenant_id,

    ).first()

    if not profile:

        raise HTTPException(status_code=404, detail="Profile not found. Create it first.")

    update_data = data.model_dump(exclude_unset=True)

    old_values = {}

    for key, value in update_data.items():

        if value is not None:

            old_values[key] = _json_safe(getattr(profile, key, None))

            setattr(profile, key, value)

    profile.profile_completed = True

    # Sync to main technicians table for main app visibility

    try:

        skill_str = ", ".join(profile.skills) if profile.skills else "General Technician"

        loc_str = profile.address or f"{profile.city or ''}, {profile.state or ''}".strip(", ") or "Main Zone"

        tech = db.query(Technician).filter(

            Technician.tenant_id == current_user.tenant_id,

            (

                Technician.tech_id == str(current_user.user_id)

            )

            | (

                Technician.technician_name == profile.full_name

            ),

        ).first()

        if not tech:

            tech = Technician(

                tech_id=str(current_user.user_id),

                tenant_id=current_user.tenant_id,

                technician_name=profile.full_name,

                technician_skill=skill_str,

                technician_location=loc_str,

                phone_number=profile.mobile_number,

                technician_status="OFFLINE",

                current_jobs=0,

                max_jobs=5,

            )

            db.add(tech)

        else:

            tech.technician_name = profile.full_name

            if profile.mobile_number:

                tech.phone_number = profile.mobile_number

            tech.technician_skill = skill_str

            tech.technician_location = loc_str

    except Exception as sync_err:

        logger.warning(f"Could not auto-sync technician record on update: {sync_err}")

    audit_log(

        db,

        action=AuditAction.PROFILE_UPDATED,

        tenant_id=current_user.tenant_id,

        user_id=current_user.user_id,

        role=current_user.role.value,

        entity_type="technician_profile",

        entity_id=profile.id,

        old_value=old_values,

        new_value={k: _json_safe(v) for k, v in update_data.items()},

        request=request,

    )

    db.commit()

    db.refresh(profile)

    user = db.query(User).filter(User.id == current_user.user_id, User.tenant_id == current_user.tenant_id,).first()

    age = None

    if profile.date_of_birth:

        today = date.today()

        age = today.year - profile.date_of_birth.year - (

            (today.month, today.day) < (profile.date_of_birth.month, profile.date_of_birth.day)

        )

    return TechnicianProfileResponse(

        id=profile.id,

        user_id=profile.user_id,

        tenant_id=profile.tenant_id,

        full_name=profile.full_name,

        profile_photo=profile.profile_photo,

        mobile_number=profile.mobile_number,

        date_of_birth=profile.date_of_birth,

        age=age,

        gender=profile.gender,

        address=profile.address,

        city=profile.city,

        state=profile.state,

        pincode=profile.pincode,

        emergency_contact=profile.emergency_contact,

        skills=profile.skills,

        experience=profile.experience,

        certifications=profile.certifications,

        profile_completed=profile.profile_completed,

        email=user.email if user else None,

        created_at=profile.created_at,

        updated_at=profile.updated_at,

    )

# ──────────────────────────────────────────────────

# Change Password

# ──────────────────────────────────────────────────

@router.post("/change-password")

async def change_password(

    data: ChangePasswordRequest,

    request: Request,

    current_user: AuthenticatedUser = Depends(require_permission(Permission.TECHNICIANS_VIEW_OWN)),

    db: Session = Depends(get_db),

):

    """Change technician password."""

    user = db.query(User).filter(User.id == current_user.user_id, User.tenant_id == current_user.tenant_id,).first()

    if not user:

        raise HTTPException(status_code=404, detail="User not found")

    if not verify_password(data.current_password, user.password_hash):

        raise HTTPException(status_code=400, detail="Current password is incorrect")

    user.password_hash = hash_password(data.new_password)

    audit_log(

        db,

        action=AuditAction.PASSWORD_CHANGED,

        tenant_id=current_user.tenant_id,

        user_id=current_user.user_id,

        role=current_user.role.value,

        entity_type="user",

        entity_id=current_user.user_id,

        request=request,

    )

    db.commit()

    return {"message": "Password changed successfully"}

# ──────────────────────────────────────────────────

# Job Endpoints

# ──────────────────────────────────────────────────

def _get_assigned_jobs_query(

    db: Session,

    user_id: str,

    tenant_id: str,

):

    """Base query for jobs assigned to this technician (any job tenant)."""

    tech = _get_tech_for_user(

        db,

        user_id,

        tenant_id,

    )

    if not tech:

        return db.query(Job).filter(Job.id < 0)

    return db.query(Job).filter(

        Job.assigned_technician_id == tech.technician_id,

    )

@router.get("/jobs", response_model=list[TechnicianJobResponse])

async def get_assigned_jobs(

    status_filter: Optional[str] = Query(None, alias="status"),

    current_user: AuthenticatedUser = Depends(require_permission(Permission.JOBS_VIEW_OWN)),

    db: Session = Depends(get_db),

):

    """List jobs assigned to the current technician."""

    query = _get_assigned_jobs_query(db, current_user.user_id, current_user.tenant_id)

    # Exclude rejected and completed for active view

    if status_filter:

        query = query.filter(func.lower(Job.status) == status_filter.lower())

    else:

        query = query.filter(

            ~func.lower(Job.status).in_(["rejected_by_technician", "completed", "closed", "cancelled"])

        )

    return query.order_by(Job.created_at.desc()).all()

@router.get("/jobs/history", response_model=list[TechnicianJobResponse])

async def get_job_history(

    current_user: AuthenticatedUser = Depends(require_permission(Permission.JOBS_VIEW_OWN)),

    db: Session = Depends(get_db),

):

    """List terminal jobs for this technician, including cancelled history."""

    query = _get_assigned_jobs_query(db, current_user.user_id, current_user.tenant_id)

    query = query.filter(

        func.lower(Job.status).in_(["completed", "closed", "cancelled"])

    )

    return query.order_by(Job.completed_at.desc()).all()

@router.get("/jobs/{job_id}", response_model=TechnicianJobResponse)

async def get_job_detail(

    job_id: int,

    current_user: AuthenticatedUser = Depends(require_permission(Permission.JOBS_VIEW_OWN)),

    db: Session = Depends(get_db),

):

    """View a specific job (only if assigned to this technician)."""

    tech = _get_tech_for_user(db, current_user.user_id, current_user.tenant_id)

    if not tech:

        raise HTTPException(status_code=403, detail="Technician record not found")

    job = _get_my_job(db, job_id, tech)

    if not job:

        raise HTTPException(status_code=403, detail="Job not found or not assigned to you")

    return job

@router.post(

    "/jobs/{job_id}/expenses",

    response_model=JobExpenseResponse,

    status_code=status.HTTP_201_CREATED,

)

async def submit_job_expense(

    job_id: int,

    data: JobExpenseCreate,

    current_user: AuthenticatedUser = Depends(

        require_permission(Permission.JOB_EXPENSES_MANAGE)

    ),

    db: Session = Depends(get_db),

):

    """Submit an expense for a job assigned to the authenticated technician.

    NOTE: create_job_expense receives the technician's tenant. If that service

    loads the job with a tenant filter, it must also be updated for cross-tenant

    jobs.

    """

    tech = _get_tech_for_user(

        db,

        current_user.user_id,

        current_user.tenant_id,

    )

    if not tech:

        raise HTTPException(

            status_code=status.HTTP_403_FORBIDDEN,

            detail="Technician record not found",

        )

    return create_job_expense(

        db=db,

        job_id=job_id,

        expense_data=data,

        technician_id=tech.technician_id,

        tenant_id=str(current_user.tenant_id),

    )

@router.post("/jobs/{job_id}/accept")

async def accept_job(

    job_id: int,

    request: Request,

    current_user: AuthenticatedUser = Depends(

        require_permission(Permission.JOBS_ACCEPT_REJECT)

    ),

    db: Session = Depends(get_db),

):

    """Accept an assigned job without starting the journey."""

    tech = _get_tech_for_user(

        db,

        current_user.user_id,

        current_user.tenant_id,

    )

    if not tech:

        raise HTTPException(

            status_code=403,

            detail="Technician record not found",

        )

    # Keep assignment-based authorization for cross-tenant jobs.
    # Lock the row to prevent concurrent duplicate acceptance.
    job = (
        db.query(Job)
        .filter(
            Job.id == job_id,
            Job.assigned_technician_id == tech.technician_id,
        )
        .with_for_update()
        .first()
    )

    if not job:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Job not found or not assigned to you",
        )

    current_status = (
        (job.status or "")
        .strip()
        .upper()
        .replace("-", "_")
        .replace(" ", "_")
    )

    # An accepted retry must not increment workload or resume dispatch again.
    if current_status == "ACCEPTED":
        return {
            "message": "Job already accepted",
            "job_id": job_id,
            "status": "ACCEPTED",
        }

    if current_status not in {
        "ASSIGNED",
        "AWAITING_ACCEPTANCE",
        "ACTIVE",
    }:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Job must be awaiting acceptance before it can be accepted. "
                f"Current status: {job.status}"
            ),
        )

    # Idempotency: repeated clicks / retries must not double-count workload

    # or resume the dispatcher a second time.

    if (job.status or "").upper() == "ACCEPTED":

        return {

            "message": "Job already accepted",

            "job_id": job_id,

            "status": "ACCEPTED",

        }

    # ---------------------------------------------------------

    # Accept the job

    # ---------------------------------------------------------

    job.status = "ACCEPTED"

    # Acceptance is the point at which this job starts counting

    # toward technician workload.

    from ..workload_utils import update_workload_count

    update_workload_count(

        db,

        tech.technician_id,

        1,

    )

    # ---------------------------------------------------------

    # Keep ServiceRequest status synchronized

    # (linked_job_id identifies it; the request belongs to the

    # customer's tenant, which can differ from the technician's)

    # ---------------------------------------------------------

    service_request = (

        db.query(ServiceRequest)

        .filter(

            ServiceRequest.linked_job_id == job.id,

        )

        .first()

    )

    if service_request:

        service_request.status = "ACCEPTED"

    # ---------------------------------------------------------

    # Mark assignment notifications as READ

    # ---------------------------------------------------------

    recipient_ids = _get_notification_recipient_ids(

        current_user.user_id,

        tech,

    )

    db.query(InAppNotification).filter(

        InAppNotification.tenant_id == current_user.tenant_id,

        InAppNotification.job_id == str(job_id),

        InAppNotification.tech_id.in_(recipient_ids),

        InAppNotification.type == "JOB_ASSIGNED",

    ).update(

        {

            "status": "READ",

            "read_at": datetime.now(timezone.utc),

        },

        synchronize_session=False,

    )

    # ---------------------------------------------------------

    # Audit

    # ---------------------------------------------------------

    audit_log(

        db,

        action=AuditAction.JOB_ACCEPTED,

        tenant_id=current_user.tenant_id,

        user_id=current_user.user_id,

        role=current_user.role.value,

        entity_type="job",

        entity_id=str(job_id),

        new_value={"status": "ACCEPTED"},

        request=request,

    )

    offer_notification = (
        db.query(InAppNotification)
        .filter(
            InAppNotification.tenant_id == current_user.tenant_id,
            InAppNotification.job_id == str(job_id),
            InAppNotification.recipient_id == str(tech.tech_id or tech.technician_id),
            InAppNotification.type == "JOB_ASSIGNED",
        )
        .order_by(InAppNotification.created_at.desc())
        .first()
    )
    offer_metadata = getattr(offer_notification, "notification_metadata", None) or {}
    dispatch_attempt_id = offer_metadata.get("dispatch_attempt_id") if isinstance(offer_metadata, dict) else None



    # ---------------------------------------------------------

    # IMPORTANT:

    # Persist the technician's acceptance BEFORE resuming

    # the LangGraph.

    # ---------------------------------------------------------

    db.commit()

    logger.info(
        "assignment_committed job_id=%s technician_id=%s dispatch_attempt_id=%s status=%s outcome=committed",
        job_id,
        tech.technician_id,
        dispatch_attempt_id,
        job.status,
    )



    # ---------------------------------------------------------

    # Cancel acceptance timer

    # ---------------------------------------------------------

    try:

        redis_client = get_redis_client()

        if redis_client:

            TimerService.cancel_timer(

                redis_client,

                str(job_id),

            )

            # Clean warning keys if they exist.

            redis_client.delete(f"job:timer_warning:{job_id}")

            redis_client.delete(f"job:timer_warned:{job_id}")

    except Exception as timer_error:

        # Timer cleanup failure should not turn a successful

        # technician acceptance into an HTTP 500.

        logger.exception(

            "Failed to cancel acceptance timer after technician "

            "accepted job=%s: %s",

            job_id,

            timer_error,

        )

    # ---------------------------------------------------------

    # Resume LangGraph

    # ---------------------------------------------------------

    try:

        runtime = get_dispatcher_runtime()

        await runtime.resume_dispatch(

            job_id=job_id,

            event="TECHNICIAN_ACCEPTED",
            technician_id=tech.technician_id,

        )

        logger.info(

            "Dispatcher resumed after technician acceptance "

            "job=%s technician=%s",

            job_id,

            tech.technician_id,

        )

    except Exception:

        # Acceptance has already been committed.

        # Never convert a successful ACCEPT into HTTP 500 merely

        # because the dispatcher could not resume.

        logger.exception(

            "Failed to resume dispatcher after technician acceptance "

            "job=%s technician=%s",

            job_id,

            tech.technician_id,

        )

    return {

        "message": "Job accepted",

        "job_id": job_id,

        "status": "ACCEPTED",

    }

@router.post("/jobs/{job_id}/reject")
async def reject_job(
    job_id: int,
    data: TechnicianJobRejectRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(
        require_permission(Permission.JOBS_ACCEPT_REJECT)
    ),
    db: Session = Depends(get_db),
):
    """
    Reject a job offered to the authenticated technician.

    Cross-tenant rules:
    - A technician can reject a job assigned to them, even if the
      job belongs to another organization.
    - Rejection history records the technician's organization.
    - The technician rejection notification is scoped to that
      technician's organization.
    - The dispatcher graph resumes after the rejection is committed.
    """

    # ---------------------------------------------------------
    # 1. Resolve the authenticated technician
    # ---------------------------------------------------------
    tech = _get_tech_for_user(
        db,
        current_user.user_id,
        current_user.tenant_id,
    )

    if not tech:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Technician record not found",
        )

    # ---------------------------------------------------------
    # 2. Verify that this job is assigned to this technician.
    # Do not filter by job.tenant_id: cross-tenant dispatch is valid.
    # ---------------------------------------------------------
    job = _get_my_job(db, job_id, tech)

    if not job:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Job not found or not assigned to you",
        )

    current_status = (
        (job.status or "")
        .strip()
        .upper()
        .replace("-", "_")
        .replace(" ", "_")
    )

    if current_status not in {
        "ASSIGNED",
        "AWAITING_ACCEPTANCE",
        "ACTIVE",
    }:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Job can only be rejected before acceptance. "
                f"Current status: {job.status}"
            ),
        )

    # Prevent duplicate rejection processing.
    if (
        (job.status or "").upper()
        == "REJECTED_BY_TECHNICIAN"
        and job.assigned_technician_id is None
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This job offer has already been rejected.",
        )

    old_status = job.status
    old_technician_id = job.assigned_technician_id
    rejected_at = datetime.now(timezone.utc)
    technician_recipient_id = str(
        tech.tech_id or tech.technician_id
    )

    try:
        # -----------------------------------------------------
        # 3. Persist the rejection
        # -----------------------------------------------------
        # This is one offer's rejection. Keep the job retryable while the
        # remaining technicians from Planning receive their offers.
        job.status = "QUEUED"
        job.rejection_reason = data.reason
        job.rejected_at = rejected_at
        job.rejected_by_tech_id = technician_recipient_id

        # Count prior attempts for this job.
        # Preserve technician_tenant_id for organization-specific
        # rejection history.
        attempt_number = (
            db.query(RedispatchAttempt)
            .filter(RedispatchAttempt.job_id == job.id)
            .count()
            + 1
        )

        db.add(
            RedispatchAttempt(
                job_id=job.id,
                attempt_number=attempt_number,
                technician_id=tech.technician_id,
                technician_name=tech.technician_name,
                technician_tenant_id=tech.tenant_id,
                event_type="rejection",
                reason=data.reason,
            )
        )

        # Release the previous technician so the dispatcher can
        # offer the job to another candidate.
        job.assigned_technician_id = None

        # -----------------------------------------------------
        # 4. Create a rejection notification in the technician's
        # own organization, not the job owner's organization.
        # -----------------------------------------------------
        notification = InAppNotification(
            id=str(uuid.uuid4()),
            tenant_id=tech.tenant_id,
            tech_id=technician_recipient_id,
            recipient_role="technician",
            recipient_id=technician_recipient_id,
            group_key=f"job_{job.id}_JOB_REJECTED",
            job_id=str(job.id),
            type="JOB_REJECTED",
            title="Job Rejection Recorded",
            body=(
                f"You rejected Job #{job.id}. "
                f"Reason: {data.reason}"
            ),
            status="UNREAD",
            priority="HIGH",
            created_at=rejected_at,
        )
        db.add(notification)

        # -----------------------------------------------------
        # 5. Audit the rejection in the acting technician's org
        # -----------------------------------------------------
        audit_log(
            db,
            action=AuditAction.JOB_REJECTED_BY_TECHNICIAN,
            tenant_id=current_user.tenant_id,
            user_id=current_user.user_id,
            role=current_user.role.value,
            entity_type="job",
            entity_id=str(job.id),
            old_value={
                "status": old_status,
                "assigned_technician_id": old_technician_id,
            },
            new_value={
                "status": "QUEUED",
                "offer_outcome": "REJECTED_BY_TECHNICIAN",
                "rejection_reason": data.reason,
                "technician_tenant_id": tech.tenant_id,
            },
            request=request,
        )

        # Commit rejection, attempt history, and notification together.
        db.commit()

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        logger.exception(
            "Failed to persist job rejection: job=%s technician=%s",
            job_id,
            tech.technician_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to process job rejection",
        )

    # ---------------------------------------------------------
    # 6. Cancel the acceptance timer.
    # A timer cleanup failure must not undo the committed rejection.
    # ---------------------------------------------------------
    try:
        redis_client = get_redis_client()

        if redis_client:
            TimerService.cancel_timer(
                redis_client,
                str(job_id),
            )
            redis_client.delete(
                f"job:timer_warning:{job_id}"
            )
            redis_client.delete(
                f"job:timer_warned:{job_id}"
            )

    except Exception:
        logger.exception(
            "Failed to cancel acceptance timer after rejection: "
            "job=%s technician=%s",
            job_id,
            tech.technician_id,
        )

    # ---------------------------------------------------------
    # 7. Resume the dispatcher so it can try the next candidate.
    # ---------------------------------------------------------
    try:
        runtime = get_dispatcher_runtime()

        await runtime.resume_dispatch(
            job_id=job_id,
            event="TECHNICIAN_REJECTED",
            technician_id=tech.technician_id,
        )

        logger.info(
            "Dispatcher resumed after rejection: job=%s technician=%s",
            job_id,
            tech.technician_id,
        )

    except Exception:
        # The rejection has already been committed. Do not report
        # that the rejection failed simply because graph resumption
        # failed. Investigate and retry graph recovery separately.
        logger.exception(
            "Failed to resume dispatcher after rejection: "
            "job=%s technician=%s",
            job_id,
            tech.technician_id,
        )

    return {
        "message": "Job rejected",
        "job_id": job_id,
        "status": "QUEUED",
        "offer_outcome": "REJECTED_BY_TECHNICIAN",
        "rejection_reason": data.reason,
    }

@router.post("/jobs/{job_id}/start")
async def start_job(
    job_id: int,
    request: Request,
    current_user: AuthenticatedUser = Depends(
        require_permission(Permission.JOBS_STATUS_UPDATE)
    ),
    db: Session = Depends(get_db),
):
    """Start travel for an accepted job assigned to this technician."""

    tech = _get_tech_for_user(
        db,
        current_user.user_id,
        current_user.tenant_id,
    )

    if not tech:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Technician record not found",
        )

    # Lock the assigned job while validating and applying the transition.
    # Authorization remains based on assignment, including cross-tenant jobs.
    job = (
        db.query(Job)
        .filter(
            Job.id == job_id,
            Job.assigned_technician_id == tech.technician_id,
        )
        .with_for_update()
        .first()
    )

    if not job:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Job not found or not assigned to you",
        )

    current_status = (
        (job.status or "")
        .strip()
        .upper()
        .replace("-", "_")
        .replace(" ", "_")
    )

    # An idempotent retry must not repeat notifications or audit events.
    if current_status == "EN_ROUTE":
        return {
            "message": "Job is already en-route",
            "job_id": job_id,
            "status": "EN_ROUTE",
        }

    if current_status != "ACCEPTED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Job must be ACCEPTED before starting travel. "
                f"Current status: {job.status}"
            ),
        )

    old_status = job.status
    job.status = "EN_ROUTE"

    create_customer_job_status_notification(
        db=db,
        job=job,
        new_status="EN_ROUTE",
    )

    # Keep the linked customer service request synchronized.
    service_request = (
        db.query(ServiceRequest)
        .filter(ServiceRequest.linked_job_id == job.id)
        .first()
    )

    if service_request:
        service_request.status = "EN_ROUTE"

    audit_log(
        db,
        action=AuditAction.JOB_STARTED,
        tenant_id=current_user.tenant_id,
        user_id=current_user.user_id,
        role=current_user.role.value,
        entity_type="job",
        entity_id=str(job_id),
        old_value={"status": old_status},
        new_value={"status": "EN_ROUTE"},
        request=request,
    )

    db.commit()

    return {
        "message": "Job started and en-route",
        "job_id": job_id,
        "status": "EN_ROUTE",
    }

@router.post("/jobs/{job_id}/on-site")

async def on_site_job(

    job_id: int,

    request: Request,

    current_user: AuthenticatedUser = Depends(require_permission(Permission.JOBS_STATUS_UPDATE)),

    db: Session = Depends(get_db),

):

    """Mark an en-route job as on-site.

    The persisted job state becomes ON_SITE. The technician portal displays

    this stage as "In Progress" and exposes the Complete action.

    """

    tech = _get_tech_for_user(db, current_user.user_id, current_user.tenant_id)

    if not tech:

        raise HTTPException(status_code=403, detail="Technician record not found")

    # Lock the assigned job while checking its current state.
    # Assignment authorization supports cross-tenant jobs.
    job = (
        db.query(Job)
        .filter(
            Job.id == job_id,
            Job.assigned_technician_id == tech.technician_id,
        )
        .with_for_update()
        .first()
    )

    if not job:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Job not found or not assigned to you",
        )

    current_status = (
        (job.status or "")
        .strip()
        .upper()
        .replace("-", "_")
        .replace(" ", "_")
    )

    # Repeated requests must not create duplicate notifications or audit events.
    if current_status == "IN_PROGRESS":
        return {
            "message": "Technician is already on site",
            "job_id": job_id,
            "status": "IN_PROGRESS",
        }

    if current_status != "EN_ROUTE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Job must be EN_ROUTE before going on-site. "
                f"Current status: {job.status}"
            ),
        )

    old_status = job.status

    job.status = "IN_PROGRESS"

    transition_time = datetime.now(timezone.utc)
    job.on_site_at = job.on_site_at or transition_time

    job.on_site_by = current_user.user_id

    service_request = db.query(ServiceRequest).filter(

        ServiceRequest.linked_job_id == job.id,

    ).first()

    if service_request:

        service_request.status = "IN_PROGRESS"

    audit_log(

        db,

        action=AuditAction.JOB_UPDATED,

        tenant_id=current_user.tenant_id,

        user_id=current_user.user_id,

        role=current_user.role.value,

        entity_type="job",

        entity_id=str(job_id),

        old_value={"status": old_status},

        new_value={"status": "IN_PROGRESS"},

        request=request,

    )

    db.commit()

    db.refresh(job)

    return {

        "message": "Technician is now on site",

        "job_id": job_id,

        "status": "IN_PROGRESS",

    }

@router.post("/jobs/{job_id}/pause")
async def pause_job(
    job_id: int,
    request: Request,
    current_user: AuthenticatedUser = Depends(
        require_permission(Permission.JOBS_STATUS_UPDATE)
    ),
    db: Session = Depends(get_db),
):
    """Pause a job that is currently in progress."""

    tech = _get_tech_for_user(
        db,
        current_user.user_id,
        current_user.tenant_id,
    )

    if not tech:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Technician record not found",
        )

    # Lock the assigned job while validating the transition.
    job = (
        db.query(Job)
        .filter(
            Job.id == job_id,
            Job.assigned_technician_id == tech.technician_id,
        )
        .with_for_update()
        .first()
    )

    if not job:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Job not found or not assigned to you",
        )

    current_status = (
        (job.status or "")
        .strip()
        .upper()
        .replace("-", "_")
        .replace(" ", "_")
    )

    # Idempotent retry: do not create another audit event.
    if current_status == "PAUSED":
        return {
            "message": "Job is already paused",
            "job_id": job_id,
            "status": "PAUSED",
        }

    if current_status != "IN_PROGRESS":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Job must be IN_PROGRESS before it can be paused. "
                f"Current status: {job.status}"
            ),
        )

    old_status = job.status
    job.status = "PAUSED"

    audit_log(
        db,
        action=AuditAction.JOB_PAUSED,
        tenant_id=current_user.tenant_id,
        user_id=current_user.user_id,
        role=current_user.role.value,
        entity_type="job",
        entity_id=str(job_id),
        old_value={"status": old_status},
        new_value={"status": "PAUSED"},
        request=request,
    )

    db.commit()

    return {
        "message": "Job paused",
        "job_id": job_id,
        "status": "PAUSED",
    }

@router.post("/jobs/{job_id}/resume")
async def resume_job(
    job_id: int,
    request: Request,
    current_user: AuthenticatedUser = Depends(
        require_permission(Permission.JOBS_STATUS_UPDATE)
    ),
    db: Session = Depends(get_db),
):
    """Resume a paused job assigned to this technician."""

    tech = _get_tech_for_user(
        db,
        current_user.user_id,
        current_user.tenant_id,
    )

    if not tech:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Technician record not found",
        )

    # Preserve assignment authorization, including cross-tenant jobs.
    # Lock the row while checking and applying the transition.
    job = (
        db.query(Job)
        .filter(
            Job.id == job_id,
            Job.assigned_technician_id == tech.technician_id,
        )
        .with_for_update()
        .first()
    )

    if not job:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Job not found or not assigned to you",
        )

    current_status = (
        (job.status or "")
        .strip()
        .upper()
        .replace("-", "_")
        .replace(" ", "_")
    )

    # An identical retry must not create another audit event.
    if current_status == "IN_PROGRESS":
        return {
            "message": "Job is already in progress",
            "job_id": job_id,
            "status": "IN_PROGRESS",
        }

    if current_status != "PAUSED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Job must be PAUSED before it can be resumed. "
                f"Current status: {job.status}"
            ),
        )

    old_status = job.status
    job.status = "IN_PROGRESS"

    audit_log(
        db,
        action=AuditAction.JOB_RESUMED,
        tenant_id=current_user.tenant_id,
        user_id=current_user.user_id,
        role=current_user.role.value,
        entity_type="job",
        entity_id=str(job_id),
        old_value={"status": old_status},
        new_value={"status": "IN_PROGRESS"},
        request=request,
    )

    db.commit()

    return {
        "message": "Job resumed",
        "job_id": job_id,
        "status": "IN_PROGRESS",
    }

@router.post("/jobs/{job_id}/complete")

async def complete_job(

    job_id: int,

    data: TechnicianJobCompleteRequest,

    request: Request,

    current_user: AuthenticatedUser = Depends(require_permission(Permission.JOBS_STATUS_UPDATE)),

    db: Session = Depends(get_db),

):

    """Complete a job with notes, photos, and optional signature."""

    tech = _get_tech_for_user(db, current_user.user_id, current_user.tenant_id)

    if not tech:

        raise HTTPException(status_code=403, detail="Technician record not found")

    # Lock the assigned job while validating and applying completion.
    # Assignment authorization is preserved for cross-tenant jobs.
    job = (
        db.query(Job)
        .filter(
            Job.id == job_id,
            Job.assigned_technician_id == tech.technician_id,
        )
        .with_for_update()
        .first()
    )

    if not job:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Job not found or not assigned to you",
        )

    current_status = (
        (job.status or "")
        .strip()
        .upper()
        .replace("-", "_")
        .replace(" ", "_")
    )

    # Make retries safe: do not create another closure or audit event.
    if current_status == "COMPLETED":
        return {
            "message": "Job is already completed",
            "job_id": job_id,
            "status": "COMPLETED",
        }

    if current_status != "IN_PROGRESS":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Job must be IN_PROGRESS before it can be completed. "
                f"Current status: {job.status}"
            ),
        )

    old_status = job.status

    job.status = "COMPLETED"

    # Keep the customer's service request status in sync.

    # A routed Job may belong to the service organization's tenant while

    # ServiceRequest belongs to the customer's tenant. Test doubles may not

    # expose customer_tenant_id, so fall back safely to the job tenant.

    service_request_query = db.query(ServiceRequest).filter(

        ServiceRequest.linked_job_id == job.id,

    )

    customer_tenant_id = getattr(job, "customer_tenant_id", None)

    if customer_tenant_id:

        service_request_query = service_request_query.filter(

            ServiceRequest.tenant_id == customer_tenant_id,

        )

    else:

        service_request_query = service_request_query.filter(

            ServiceRequest.tenant_id == job.tenant_id,

        )

    service_request = service_request_query.first()

    if service_request:

        service_request.status = "COMPLETED"

    job.completed_at = datetime.now(timezone.utc)

    job.completed_by = current_user.user_id

    if data.completion_notes:

        job.work_report = data.completion_notes

    # The fallback completion route receives labour/material costs in the

    # request payload, but TechnicianJobCompleteRequest keeps its existing

    # contract. Read those optional values from the original request body so

    # the billing report can persist the same costs without changing the schema.

    try:

        request_payload = await request.json()

    except Exception:

        request_payload = {}

    labour_cost = round(float(request_payload.get("labour_cost") or 0), 2)

    material_cost = round(float(request_payload.get("material_cost") or 0), 2)

    subtotal = round(labour_cost + material_cost, 2)

    # The Billing Report is backed by JobClosure records. The compatibility

    # completion route must therefore create the closure record as part of the

    # same transaction.

    existing_closure = (

        db.query(JobClosure)

        .filter(

            JobClosure.job_id == job.id,

            JobClosure.tenant_id == job.tenant_id,

        )

        .first()

    )

    if not existing_closure:

        closure_record = JobClosure(

            job_id=job.id,

            tenant_id=job.tenant_id,

            work_summary=data.completion_notes or "Job completed",

            before_images=[],

            after_images=list(data.photos or []),

            labour_cost=labour_cost,

            material_cost=material_cost,

            subtotal=subtotal,

            completed_at=job.completed_at,

        )

        db.add(closure_record)

        db.flush()

    else:
        closure_record = existing_closure

    # Persist the customer signature in the same transaction as the closure.
    # Older callers that omit the optional signature remain compatible.
    signature_data = request_payload.get("signature_data")

    if signature_data is not None:
        if (
            not isinstance(signature_data, str)
            or not signature_data.strip()
            or len(signature_data) > 2_000_000
            or not signature_data.strip().startswith(
                (
                    "data:image/png;base64,",
                    "data:image/jpeg;base64,",
                )
            )
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid customer signature data",
            )

        existing_signature = (
            db.query(CustomerSignature)
            .filter(CustomerSignature.job_id == job.id)
            .first()
        )

        if existing_signature is None:
            customer_signature = CustomerSignature(
                job_id=job.id,
                job_closure_id=closure_record.id,
                tenant_id=str(job.tenant_id),
                signature_data=signature_data.strip(),
                captured_by=str(tech.tech_id),
                signed_at=datetime.now(timezone.utc),
            )

            db.add(customer_signature)
            db.flush()

    # Keep invoice delivery in the same transaction as the completed job.
    from ..services.email.transactional_outbox import persist_invoice_email
    persist_invoice_email(db, job, closure_record)

    audit_log(

        db, action=AuditAction.JOB_COMPLETED,

        tenant_id=current_user.tenant_id, user_id=current_user.user_id,

        role=current_user.role.value, entity_type="job", entity_id=str(job_id),

        old_value={"status": old_status},

        new_value={"status": "COMPLETED", "completion_notes": data.completion_notes},

        request=request,

    )

    db.commit()

    return {"message": "Job completed", "job_id": job_id, "status": "COMPLETED"}

# ──────────────────────────────────────────────────

# Notifications

# ──────────────────────────────────────────────────

@router.get("/notifications")

async def get_notifications(

    current_user: AuthenticatedUser = Depends(

        require_permission(Permission.NOTIFICATIONS_VIEW_OWN)

    ),

    db: Session = Depends(get_db),

):

    """Get technician notifications and sync missing assignment notifications."""

    tech = _get_tech_for_user(

        db,

        current_user.user_id,

        current_user.tenant_id,

    )

    search_ids = _get_notification_recipient_ids(

        current_user.user_id,

        tech,

    )

    notifications = db.query(InAppNotification).filter(

        InAppNotification.tenant_id == current_user.tenant_id,

        InAppNotification.tech_id.in_(search_ids),

    ).order_by(

        InAppNotification.created_at.desc()

    ).limit(100).all()

    # Create missing notifications for pending jobs.

    if tech:

        # Not tenant-scoped: the job may belong to another organization.

        pending_jobs = (
            db.query(Job)
            .filter(
                Job.assigned_technician_id == tech.technician_id,
                func.upper(
                    func.replace(
                        func.replace(func.trim(Job.status), "-", "_"),
                        " ",
                        "_",
                    )
                ).in_(
                    [
                        "ASSIGNED",
                        "AWAITING_ACCEPTANCE",
                        "ACTIVE",
                        "PLANNED",
                        "QUEUED",
                    ]
                ),
            )
            .all()
        )

        pending_job_ids = [

            str(job.id)

            for job in pending_jobs

        ]

        existing_notification_rows = []

        if pending_job_ids:

            existing_notification_rows = db.query(

                InAppNotification.job_id

            ).filter(

                InAppNotification.tenant_id

                == current_user.tenant_id,

                InAppNotification.tech_id.in_(search_ids),

                InAppNotification.type == "JOB_ASSIGNED",

                InAppNotification.job_id.in_(pending_job_ids),

            ).all()

        existing_job_ids = {

            str(row.job_id)

            for row in existing_notification_rows

            if row.job_id

        }

        new_added = False

        for job in pending_jobs:

            if str(job.id) not in existing_job_ids:

                new_notification = InAppNotification(

                    id=str(uuid.uuid4()),

                    # Notifications are scoped to the technician's tenant.

                    # The job itself may belong to a different tenant.

                    tenant_id=current_user.tenant_id,

                    tech_id=tech.tech_id or str(current_user.user_id),

                    job_id=str(job.id),

                    type="JOB_ASSIGNED",

                    title="New Job Assigned",

                    body=(

                        f"You have been assigned to Job #{job.id}: "

                        f"{job.service_type or 'Service Request'} at "

                        f"{job.location or 'Customer location'}."

                    ),

                    status="UNREAD",

                    priority=job.priority or "HIGH",

                    created_at=(

                        job.created_at

                        or datetime.now(timezone.utc)

                    ),

                )

                db.add(new_notification)

                existing_job_ids.add(str(job.id))

                new_added = True

        if new_added:

            try:

                db.commit()

                notifications = db.query(InAppNotification).filter(

                    InAppNotification.tenant_id

                    == current_user.tenant_id,

                    InAppNotification.tech_id.in_(search_ids),

                ).order_by(

                    InAppNotification.created_at.desc()

                ).limit(100).all()

            except Exception as exc:

                db.rollback()

                logger.exception(

                    "Unable to sync technician notifications: %s",

                    exc,

                )

                raise HTTPException(

                    status_code=500,

                    detail="Unable to synchronize notifications",

                )

    job_ids = [

        int(notification.job_id)

        for notification in notifications

        if notification.job_id

        and str(notification.job_id).isdigit()

    ]

    job_status_map = {}

    if job_ids:

        job_rows = db.query(

            Job.id,

            Job.status,

        ).filter(

            Job.id.in_(job_ids),

        ).all()

        job_status_map = {

            job.id: (job.status or "").upper()

            for job in job_rows

        }

    # hidden_job_statuses = {

    #     "EN_ROUTE",

    #     "ACCEPTED",

    #     "IN_PROGRESS",

    #     "PAUSED",

    #     "COMPLETED",

    #     "CLOSED",

    #     "REJECTED_BY_TECHNICIAN",

    # }

    # filtered_notifications = []

    # for notification in notifications:

    #     job_id = (

    #         int(notification.job_id)

    #         if notification.job_id

    #         and str(notification.job_id).isdigit()

    #         else None

    #     )

    #     job_status = (

    #         job_status_map.get(job_id, "")

    #         if job_id is not None

    #         else ""

    #     )

    #     if (

    #         notification.type == "JOB_ASSIGNED"

    #         and job_status in hidden_job_statuses

    #     ):

    #         continue

    #     filtered_notifications.append(notification)

    filtered_notifications = notifications

    unread_count = sum(

        1

        for notification in filtered_notifications

        if notification.status == "UNREAD"

    )

    return {

        "notifications": [

            {

                "id": str(notification.id),

                "type": notification.type,

                "title": notification.title,

                "message": notification.body,

                "isRead": notification.status != "UNREAD",

                "createdAt": (

                    notification.created_at.isoformat()

                    if notification.created_at

                    else None

                ),

                "jobId": notification.job_id,

                "jobStatus": (

                    job_status_map.get(int(notification.job_id))

                    if notification.job_id

                    and str(notification.job_id).isdigit()

                    else None

                ),

            }

            for notification in filtered_notifications

        ],

        "unread_count": unread_count,

    }

@router.put("/notifications/{notification_id}/read")

async def mark_notification_read(

    notification_id: str,

    current_user: AuthenticatedUser = Depends(

        require_permission(Permission.NOTIFICATIONS_VIEW_OWN)

    ),

    db: Session = Depends(get_db),

):

    """Mark one of the current technician's notifications as read."""

    tech = _get_tech_for_user(

        db,

        current_user.user_id,

        current_user.tenant_id,

    )

    recipient_ids = _get_notification_recipient_ids(

        current_user.user_id,

        tech,

    )

    notification = db.query(InAppNotification).filter(

        InAppNotification.id == notification_id,

        InAppNotification.tenant_id == current_user.tenant_id,

        InAppNotification.tech_id.in_(recipient_ids),

    ).first()

    if not notification:

        raise HTTPException(

            status_code=404,

            detail="Notification not found",

        )

    if notification.status == "UNREAD":

        notification.status = "READ"

        notification.read_at = datetime.now(timezone.utc)

        db.commit()

        db.refresh(notification)

    return {

        "message": "Marked as read",

        "notification_id": notification.id,

        "status": notification.status,

    }

@router.put("/notifications/read-all")

async def mark_all_notifications_read(

    current_user: AuthenticatedUser = Depends(

        require_permission(Permission.NOTIFICATIONS_VIEW_OWN)

    ),

    db: Session = Depends(get_db),

):

    """Mark all current technician notifications as read."""

    tech = _get_tech_for_user(

        db,

        current_user.user_id,

        current_user.tenant_id,

    )

    recipient_ids = _get_notification_recipient_ids(

        current_user.user_id,

        tech,

    )

    updated_count = db.query(InAppNotification).filter(

        InAppNotification.tenant_id == current_user.tenant_id,

        InAppNotification.tech_id.in_(recipient_ids),

        InAppNotification.status == "UNREAD",

    ).update(

        {

            "status": "READ",

            "read_at": datetime.now(timezone.utc),

        },

        synchronize_session=False,

    )

    db.commit()

    return {

        "message": "All notifications marked as read",

        "updated": updated_count,

    }

# ──────────────────────────────────────────────────

# Technician Status

# ──────────────────────────────────────────────────

@router.put("/status")

async def update_my_technician_status(

    data: TechnicianAvailabilityUpdate,

    background_tasks: BackgroundTasks = None,

    current_user: AuthenticatedUser = Depends(

        require_permission(Permission.TECHNICIANS_VIEW_OWN)

    ),

    db: Session = Depends(get_db),
    redis_client=Depends(get_redis_client),

):

    profile = db.query(TechnicianProfile).filter(

        TechnicianProfile.user_id == current_user.user_id,

        TechnicianProfile.tenant_id == current_user.tenant_id,

    ).first()

    if not profile or not profile.profile_completed:

        raise HTTPException(

            status_code=403,

            detail="Please complete your profile to change technician status.",

        )

    tech = _get_tech_for_user(

        db,

        current_user.user_id,

        current_user.tenant_id,

    )

    if not tech:

        raise HTTPException(

            status_code=404,

            detail="Technician record not found",

        )



    tech = db.query(Technician).filter(
        Technician.technician_id == tech.technician_id,
        Technician.tenant_id == current_user.tenant_id,
    ).with_for_update().first()

    requested = str(data.technician_status or "").strip().upper()
    if requested not in {"AVAILABLE", "OFFLINE"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Technician availability must be Available or Offline",
        )
    if requested == "AVAILABLE":
        if (tech.current_jobs or 0) >= (tech.max_jobs or 0):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No assignment capacity is available",
            )
        gps_key = f"gps:availability:{current_user.tenant_id}:{current_user.user_id}"
        try:
            if not redis_client or not redis_client.exists(gps_key):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A current GPS location is required to go online",
                )
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("Could not verify technician GPS before online transition: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Availability is temporarily unavailable",
            )

    tech.technician_status = requested

    db.commit()

    db.refresh(tech)

    return {

        "technician_id": tech.technician_id,

        "technician_status": tech.technician_status,

    }

# ──────────────────────────────────────────────────

# Dashboard

# ──────────────────────────────────────────────────

@router.get("/billing-reports")

async def get_billing_reports(

    current_user: AuthenticatedUser = Depends(require_permission(Permission.REPORTS_VIEW)),

    db: Session = Depends(get_db),

):

    """Return billing reports submitted by the authenticated technician."""

    tech = _get_tech_for_user(db, current_user.user_id, current_user.tenant_id)

    if not tech:

        raise HTTPException(status_code=403, detail="Technician record not found")

    rows = (

        db.query(JobClosure, Job)

        .join(Job, Job.id == JobClosure.job_id)

        .filter(

            Job.assigned_technician_id == tech.technician_id,

        )

        .order_by(JobClosure.completed_at.desc())

        .all()

    )

    reports = []

    for closure, job in rows:

        subtotal = round(float(closure.subtotal or 0), 2)

        gst = round(subtotal * 0.05, 2)

        total = round(subtotal + gst, 2)

        reports.append({

            "id": closure.id,

            "job_id": job.id,

            "customer_name": job.customer_name or "N/A",

            "service_type": job.service_type or "Service",

            "location": job.location or job.site_address or "N/A",

            "work_summary": closure.work_summary,

            "labour_cost": float(closure.labour_cost or 0),

            "material_cost": float(closure.material_cost or 0),

            "subtotal": subtotal,

            "gst_rate": 5,

            "gst_amount": gst,

            "total_amount": total,

            "completed_at": _json_safe(closure.completed_at),

            "created_at": _json_safe(closure.created_at),

        })

    return {"reports": reports, "count": len(reports)}

@router.get("/billing-reports/{closure_id}/pdf")

async def download_billing_report_pdf(

    closure_id: int,

    current_user: AuthenticatedUser = Depends(require_permission(Permission.REPORTS_VIEW)),

    db: Session = Depends(get_db),

):

    """Generate and download a PDF billing report for the authenticated technician."""

    tech = _get_tech_for_user(db, current_user.user_id, current_user.tenant_id)

    if not tech:

        raise HTTPException(status_code=403, detail="Technician record not found")

    row = (

        db.query(JobClosure, Job)

        .join(Job, Job.id == JobClosure.job_id)

        .filter(

            JobClosure.id == closure_id,

            Job.assigned_technician_id == tech.technician_id,

        )

        .first()

    )

    if not row:

        raise HTTPException(status_code=404, detail="Billing report not found")

    closure, job = row

    from reportlab.lib.pagesizes import A4

    from reportlab.lib.utils import ImageReader

    from reportlab.pdfgen import canvas

    subtotal = round(float(closure.subtotal or 0), 2)

    gst = round(subtotal * 0.05, 2)

    total = round(subtotal + gst, 2)

    buffer = BytesIO()

    pdf = canvas.Canvas(buffer, pagesize=A4)

    width, height = A4

    pdf.setTitle(f"Billing Report - Job #{job.id}")

    pdf.setFont("Helvetica-Bold", 18)

    pdf.drawString(50, height - 55, "FieldOps - Billing Report")

    pdf.setFont("Helvetica", 10)

    pdf.drawString(50, height - 75, f"Report #{closure.id}  |  Job #{job.id}")

    y = height - 115
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(50, y, "Job Details")
    y -= 22
    pdf.setFont("Helvetica", 10)
    details = [
        ("Customer", job.customer_name or "N/A"),
        ("Service", job.service_type or "N/A"),
        ("Location", job.location or job.site_address or "N/A"),
        ("Technician", tech.technician_name or "N/A"),
        ("Completed", str(closure.completed_at or "N/A")),
    ]
    for label, value in details:
        pdf.drawString(50, y, f"{label}: {value}")
        y -= 18

    y -= 8
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(50, y, "Work Summary")
    y -= 20
    pdf.setFont("Helvetica", 10)
    words = (closure.work_summary or "").replace("\n", " ").split()
    line = ""
    for word in words:
        test = f"{line} {word}".strip()
        if len(test) > 90:
            pdf.drawString(50, y, line)
            y -= 15
            line = word
        else:
            line = test

    if line:
        pdf.drawString(50, y, line)
        y -= 25

    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(50, y, "Cost Details")
    y -= 22
    pdf.setFont("Helvetica", 10)
    for label, amount in [
        ("Service / Labour Cost", closure.labour_cost or 0),
        ("Material Cost", closure.material_cost or 0),
        ("Subtotal", subtotal),
        ("GST (5%)", gst),
        ("Total Amount", total),
    ]:
        pdf.drawString(50, y, label)
        pdf.drawRightString(width - 50, y, f"INR {float(amount):,.2f}")
        y -= 20

    # Include the backend-authoritative customer signature captured for this job
    # Looked up by job_id only: the signature is stored under the job's
    # (or customer's) tenant, which can differ from the technician's tenant.
    signature = (
        db.query(CustomerSignature)
        .filter(
            CustomerSignature.job_id == job.id,
        )
        .first()
    )

    y -= 8
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(50, y, "Customer Signature")
    y -= 18

    if signature and signature.signature_data:
        try:
            encoded = signature.signature_data.split(",", 1)[1]
            signature_bytes = base64.b64decode(encoded, validate=True)
            signature_image = ImageReader(BytesIO(signature_bytes))
            image_width, image_height = signature_image.getSize()

            max_width = 240
            max_height = 100
            scale = min(
                max_width / float(image_width or 1),
                max_height / float(image_height or 1),
                1.0,
            )

            draw_width = image_width * scale
            draw_height = image_height * scale

            if y - draw_height - 35 < 55:
                pdf.showPage()
                y = height - 60

            pdf.setFont("Helvetica", 9)
            pdf.setStrokeColorRGB(0.75, 0.75, 0.75)
            pdf.rect(50, y - draw_height - 8, max_width, draw_height + 16, stroke=1, fill=0)
            pdf.drawImage(
                signature_image,
                50,
                y - draw_height,
                width=draw_width,
                height=draw_height,
                preserveAspectRatio=True,
                mask="auto",
            )
            y -= draw_height + 22

            pdf.setFillColorRGB(0.35, 0.35, 0.35)
            pdf.drawString(50, y, f"Signed at: {signature.signed_at.isoformat()}")
            pdf.setFillColorRGB(0, 0, 0)
        except Exception:
            pdf.setFont("Helvetica", 9)
            pdf.drawString(50, y, "Customer signature is unavailable for this report.")
    else:
        pdf.setFont("Helvetica", 9)
        pdf.drawString(50, y, "No customer signature was recorded for this report.")

    pdf.setFont("Helvetica-Oblique", 9)
    pdf.drawString(50, 45, "Generated from the FieldOps technician billing report.")
    pdf.save()
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="billing_report_job_{job.id}.pdf"'},
    )

@router.get("/dashboard", response_model=TechnicianDashboardResponse)
async def get_technician_dashboard(
    current_user: AuthenticatedUser = Depends(
        require_permission(Permission.DASHBOARD_TECH_VIEW)
    ),
    db: Session = Depends(get_db),
):

    """Get technician dashboard statistics."""
    tech = _get_tech_for_user(
        db,
        current_user.user_id,
        current_user.tenant_id,
    )

    profile = db.query(TechnicianProfile).filter(
        TechnicianProfile.user_id == current_user.user_id,
        TechnicianProfile.tenant_id == current_user.tenant_id,
    ).first()

    profile_completed = bool(
        profile and profile.profile_completed
    )

    if not tech:
        return TechnicianDashboardResponse(
            profile_completed=profile_completed,
            technician_status=None,
        )

    # Not tenant-scoped: jobs may belong to another organization.
    base = db.query(Job).filter(
        Job.assigned_technician_id == tech.technician_id,
    )

    today = datetime.now(timezone.utc).date()
    total_assigned = base.count()

    active = base.filter(
        func.lower(Job.status).in_(
            ["accepted", "en_route", "in_progress", "paused"]
        )
    ).count()

    completed_today = base.filter(
        Job.status == "COMPLETED",
        func.date(Job.completed_at) == today,
    ).count()

    pending = base.filter(
        func.lower(Job.status).in_(
            ["assigned", "active"]
        )
    ).count()

    rejected_jobs = db.query(Job).filter(
        Job.rejected_by_tech_id
        == (tech.tech_id or str(tech.technician_id)),
        func.lower(Job.status)
        == "rejected_by_technician",
    ).count()

    total_completed = base.filter(
        func.lower(Job.status).in_(
            ["completed", "closed"]
        )
    ).count()

    return TechnicianDashboardResponse(
        total_assigned=total_assigned,
        active_jobs=active,
        completed_today=completed_today,
        pending_acceptance=pending,
        total_completed=total_completed,
        rejected_jobs=rejected_jobs,
        technician_status=tech.technician_status,
        profile_completed=profile_completed,

    )
