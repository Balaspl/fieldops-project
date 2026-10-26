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

from ..models import Job, Technician, AuditEvent, ServiceRequest
from ..models.job_closure import JobClosure
from ..models.customer_signature import CustomerSignature
from ..repositories.completion_document_repository import (
    CompletionDocumentRepository,
)
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
                f"Job cannot be closed because its current status is "
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

        service_request = (
            db.query(ServiceRequest)
            .filter(
                ServiceRequest.linked_job_id == job.id,
                ServiceRequest.customer_user_id == str(job.customer_id),
            )
            .with_for_update()
            .first()
        )

        if service_request:
            service_request.status = "COMPLETED"

        completed_at = job.completed_at

        if completed_at is None:
            raise RuntimeError(
                "Completion transition did not set the authoritative "
                "completion timestamp"
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
                {
                    "items": [
                        item.model_dump()
                        for item in closure_data.checklist.items
                    ]
                }
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

        # Save the customer signature in the same transaction as
        # the job closure. If signature persistence fails, the
        # closure and job status transition will roll back together.
        customer_signature = CustomerSignature(
            job_id=job.id,
            job_closure_id=closure_record.id,
            tenant_id=tenant_id,
            signature_data=closure_data.signature_data,
            captured_by=technician_identifier,
            signed_at=datetime.now(timezone.utc),
        )

        db.add(customer_signature)
        db.flush()

        # -----------------------------------------------------------
        # 4.4.7
        # Link completion documents that were uploaded before the
        # JobClosure existed.
        #
        # The repository method validates that each document belongs
        # to the same job and tenant before assigning the closure.
        # -----------------------------------------------------------

        document_repository = CompletionDocumentRepository(db)

        unlinked_documents = (
            document_repository.list_unlinked_for_job(
                job_id=job.id,
                tenant_id=tenant_id,
            )
        )

        for document in unlinked_documents:
            document_repository.link_to_closure(
                document,
                job_id=job.id,
                tenant_id=tenant_id,
                job_closure_id=closure_record.id,
            )

            # Record the relationship change in the same DB transaction.
            db.add(
                AuditEvent(
                    tech_id=str(tech.tech_id),
                    tenant_id=tenant_id,
                    event_type="COMPLETION_DOCUMENT_LINKED",
                    old_status=document.status,
                    new_status=document.status,
                    job_id=str(job.id),
                    actor_id=actor_id,
                    timestamp=datetime.now(timezone.utc),
                    correlation_id=(
                        correlation_id_ctx.get() or None
                    ),
                    details={
                        "completion_document_id": document.id,
                        "job_closure_id": closure_record.id,
                        "document_type": document.document_type,
                        "category": document.category,
                    },
                )
            )

        # -----------------------------------------------------------
        # Existing completion audit event
        # -----------------------------------------------------------

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
                "linked_completion_document_ids": [
                    document.id
                    for document in unlinked_documents
                ],
            },
            timestamp=completed_at,
        )

        db.add(audit_event)

        # The invoice email obligation commits atomically with the finalized
        # closure and job completion, then a standalone SMTP worker delivers it.
        from .email.transactional_outbox import persist_invoice_email
        persist_invoice_email(db, job, closure_record)

        # Completing work updates workload only; availability is user-controlled.
        tech.current_jobs = max(
            0,
            (tech.current_jobs or 1) - 1,
        )

        # -----------------------------------------------------------
        # Commit closure + linked documents + audit records together.
        # -----------------------------------------------------------

        db.commit()
        db.refresh(closure_record)

    except (
        InvalidTransitionError,
        PermissionDeniedError,
        ReasonRequiredError,
    ) as exc:
        db.rollback()

        # Restore the in-memory prerequisite field before exposing
        # the error to callers; rollback already restores DB state.
        job.work_report = previous_work_report

        if isinstance(exc, PermissionDeniedError):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(exc),
            )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                exc.to_dict()
                if isinstance(exc, InvalidTransitionError)
                else str(exc)
            ),
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

        logger.exception(
            "Failed to close job %s",
            job_id,
        )

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
        logger.exception(
            "Failed to publish JOB_COMPLETED event for job %s",
            job.id,
        )

    # Publish canonical invoice event after authoritative closure commitment.
    # Kafka/broker failure must not turn an already committed closure into a failure.
    try:
        from ..redis_client import get_redis_client
        from ..tasks import _publish_invoice_event_once
        from .event_publisher import publish_invoice_event

        invoice_event_id = f"evt_invoice_{closure_record.id}_{job.id}"
        correlation_id = correlation_id_ctx.get() or None

        # Coordinate with Redis for real-time downstream subscribers
        publish_invoice_event(
            redis_client=get_redis_client(),
            event_type="INVOICE_GENERATED",
            job_id=str(job.id),
            tenant_id=tenant_id,
            invoice_id=str(closure_record.id),
            correlation_id=correlation_id,
            event_id=invoice_event_id,
            payload={
                "subtotal": closure_record.subtotal,
                "labour_cost": closure_record.labour_cost,
                "material_cost": closure_record.material_cost,
                "completed_at": (
                    closure_record.completed_at.isoformat()
                    if closure_record.completed_at
                    else None
                ),
            },
        )

        # Publish to Kafka via invoice event producer
        _publish_invoice_event_once(
            redis=get_redis_client(),
            event_type="INVOICE_GENERATED",
            event_id=invoice_event_id,
            job_id=str(job.id),
            tenant_id=tenant_id,
            invoice_id=str(closure_record.id),
            correlation_id=correlation_id,
            payload={
                "invoice_id": str(closure_record.id),
                "subtotal": closure_record.subtotal,
                "labour_cost": closure_record.labour_cost,
                "material_cost": closure_record.material_cost,
                "completed_at": (
                    closure_record.completed_at.isoformat()
                    if closure_record.completed_at
                    else None
                ),
            },
        )
    except Exception:
        logger.exception(
            "Failed to publish INVOICE_GENERATED event for job %s closure %s",
            job.id,
            closure_record.id,
        )

    return closure_record


def get_job_closure(
    db: Session,
    job_id: int,
) -> JobClosure:
    """
    Fetch closure details for a given job.
    """
    job = (
        db.query(Job)
        .filter(Job.id == job_id)
        .first()
    )

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    closure = (
        db.query(JobClosure)
        .filter(
            JobClosure.job_id == job_id,
            JobClosure.tenant_id == job.tenant_id,
        )
        .first()
    )

    if not closure:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job closure details not found for this job",
        )

    return closure
