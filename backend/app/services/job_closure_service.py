"""
job_closure_service.py
Service for processing job completion and fetching job closure details.
"""

from datetime import datetime, timezone
from typing import Optional
import logging
from ..context import correlation_id_ctx
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from ..models import Job, Technician, AuditEvent
from ..models.job_closure import JobClosure
from ..schemas import JobClosureCreate, CompletionChecklist
from .job_status_machine import (
    JobStatus,
    InvalidTransitionError,
    PermissionDeniedError,
    ReasonRequiredError,
    SideEffectError,
    transition_job,
)

logger = logging.getLogger(__name__)


def validate_completion_checklist(
    checklist: Optional[CompletionChecklist],
) -> None:
    """
    Validate required completion checklist items before job mutation.

    Optional checklists remain backward compatible. When a checklist is
    submitted, every required item must be COMPLETED.
    """
    if checklist is None:
        return

    incomplete_required = [
        item
        for item in checklist.items
        if item.required and item.status != "COMPLETED"
    ]

    if incomplete_required:
        incomplete_items = [
            {
                "id": item.id,
                "label": item.label,
            }
            for item in incomplete_required
        ]

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "INCOMPLETE_CHECKLIST",
                "message": "Required checklist items are incomplete",
                "incomplete_items": incomplete_items,
            },
        )

def close_job(
    db: Session,
    job_id: int,
    closure_data: JobClosureCreate,
    technician_identifier: str,
    tenant_id: str,
    user_role: Optional[str] = "TECHNICIAN",
) -> JobClosure:
    """
    Atomically complete a job for the authenticated technician.

    The service is intentionally tenant-aware so it cannot be reused in a
    way that bypasses tenant isolation. Completion must also pass through the
    existing JobStatusMachine so lifecycle prerequisites and transition rules
    remain authoritative.
    """
    role_str = (user_role or "").strip().lower()
    if role_str != "technician":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only technicians can close jobs",
        )

    tenant_id = str(tenant_id)
    technician_identifier = str(technician_identifier)

    # Keep the lookup tenant-scoped from the start. A job from another tenant
    # must be indistinguishable from an unknown job to this service.
    job = (
        db.query(Job)
        .filter(
            Job.id == job_id,
            Job.tenant_id == tenant_id,
        )
        .with_for_update()
        .first()
    )
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    if job.assigned_technician_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job is not assigned to any technician",
        )

    # Resolve only against the assigned technician inside the same tenant.
    # Name/phone matching is deliberately not allowed for an authoritative
    # technician completion path.
    tech = (
        db.query(Technician)
        .filter(
            Technician.tenant_id == tenant_id,
            Technician.technician_id == job.assigned_technician_id,
        )
        .first()
    )
    if not tech:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Technician record not found",
        )

    identifier_matches = {
        str(tech.technician_id),
        str(tech.tech_id),
    }
    if technician_identifier not in identifier_matches:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Job is not assigned to this technician",
        )

    current_status = (job.status or "").upper().strip()
    if current_status == "COMPLETED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Job cannot be closed because its current status is "
                f"{current_status}"
            ),
        )
    if current_status in {"CANCELLED", "CANCELED", "CLOSED"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Job cannot be closed because its current status is "
                f"{current_status}"
            ),
        )

    existing_closure = (
        db.query(JobClosure)
        .filter(
            JobClosure.job_id == job_id,
            JobClosure.tenant_id == tenant_id,
        )
        .first()
    )
    if existing_closure:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job closure record already exists for this job",
        )
            # Validate the completion checklist before any job state mutation.
    validate_completion_checklist(closure_data.checklist)

    # Pydantic has already validated the completion payload before this
    # service is entered. The existing lifecycle prerequisite requires a work
    # report, and the closure's work_summary is the authoritative report for
    # this completion flow.
    # Pydantic has already validated the completion payload before this
    # service is entered.

    previous_work_report = job.work_report

    # Build the canonical structured work report.
    #
    # Backward compatibility:
    # - Older callers may provide only work_summary.
    # - New callers may provide work_report.
    #
    # The structured report's summary is kept synchronized with the existing
    # Job.work_report field so older consumers continue to work.
    if closure_data.work_report is not None:
        canonical_work_report = {
            "summary": closure_data.work_report.summary,
            "parts_used": closure_data.work_report.parts_used,
            "duration_minutes": closure_data.work_report.duration_minutes,
        }

        job.work_report = closure_data.work_report.summary
    else:
        canonical_work_report = {
            "summary": closure_data.work_summary,
            "parts_used": [],
            "duration_minutes": None,
        }

        job.work_report = closure_data.work_summary

    old_status = current_status or "CREATED"
    actor_id = technician_identifier

    try:
        # Preserve the existing lifecycle authority rather than assigning
        # COMPLETED directly.
        transition_job(
            job,
            JobStatus.COMPLETED,
            actor_id=actor_id,
            actor_role="technician",
        )

        completed_at = job.completed_at
        if completed_at is None:
            raise RuntimeError(
                "Completion transition did not set the authoritative completion timestamp"
            )

        subtotal = round(
            closure_data.labour_cost + closure_data.material_cost,
            2,
        )

        closure_record = JobClosure(
        job_id=job.id,
        tenant_id=tenant_id,
        work_summary=closure_data.work_summary,
        work_report=canonical_work_report,
        completion_checklist=(
            {"items": [item.model_dump() for item in closure_data.checklist.items]}
            if closure_data.checklist is not None
            else None
        ),
        before_images=closure_data.before_images or [],
        after_images=closure_data.after_images,
        labour_cost=closure_data.labour_cost,
        material_cost=closure_data.material_cost,
        subtotal=subtotal,
        completed_at=completed_at,
        )
        db.add(closure_record)
        db.flush()

        # Persist the domain audit record in the same DB transaction.
        audit_event = AuditEvent(
            tech_id=str(tech.tech_id),
            tenant_id=tenant_id,
            event_type="JOB_COMPLETED",
            old_status=old_status,
            new_status="COMPLETED",
            job_id=str(job.id),
            actor_id=actor_id,
            details={
                "closure_id": closure_record.id,
                "subtotal": subtotal,
            },
            timestamp=completed_at,
        )
        db.add(audit_event)

        # Keep the technician available after the final completion is staged.
        tech.technician_status = "AVAILABLE"
        tech.current_jobs = max(0, (tech.current_jobs or 1) - 1)

        db.commit()
        db.refresh(closure_record)

    except (InvalidTransitionError, PermissionDeniedError, ReasonRequiredError) as exc:
        db.rollback()
        # Restore the in-memory prerequisite field before exposing the error to
        # callers; the rollback already restores the DB state.
        job.work_report = previous_work_report
        if isinstance(exc, PermissionDeniedError):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(exc),
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=exc.to_dict() if isinstance(exc, InvalidTransitionError) else str(exc),
        )
    except SideEffectError as exc:
        db.rollback()
        job.work_report = previous_work_report
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Exception as exc:
        db.rollback()
        job.work_report = previous_work_report
        logger.exception("Failed to close job %s", job_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to close job due to database error",
        ) from exc

    # Redis is intentionally published only after the DB transaction commits.
    # A broker failure must not turn an already committed completion into a
    # false HTTP failure.
    try:
        from ..redis_client import get_redis_client
        from .event_publisher import publish_dispatch_event

        publish_dispatch_event(
        get_redis_client(),
        event_type="JOB_COMPLETED",
        job_id=str(job.id),
        old_status=old_status,
        new_status="COMPLETED",
        tenant_id=tenant_id,
        technician_id=str(tech.tech_id),
        technician_name=tech.technician_name,
        completed_at=closure_record.completed_at,
        correlation_id=correlation_id_ctx.get() or None,
        event_id=(
            f"JOB_COMPLETED:"
            f"{tenant_id}:"
            f"{job.id}:"
            f"{closure_record.id}"
        ),
    )
    except Exception:
        logger.exception("Failed to publish JOB_COMPLETED event for job %s", job.id)

    return closure_record


def get_job_closure(db: Session, job_id: int) -> JobClosure:
    """
    Fetch closure details for a given job.
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    closure = db.query(JobClosure).filter(
        JobClosure.job_id == job_id,
        JobClosure.tenant_id == job.tenant_id,
    ).first()
    if not closure:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job closure details not found for this job",
        )

    return closure
