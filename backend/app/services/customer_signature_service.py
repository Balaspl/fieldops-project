
"""
customer_signature_service.py

Service for capturing and retrieving customer signatures associated with
an authenticated technician's completed job.

A job and its assigned technician may belong to different tenants.
The job's tenant owns the closure and customer signature records, while
the authenticated technician must independently be verified as assigned.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from ..models import Job, Technician
from ..models.customer_signature import CustomerSignature
from ..models.job_closure import JobClosure
from ..schemas import CustomerSignatureCreate


def _get_assigned_technician(
    db: Session,
    job: Job,
) -> Technician:
    """
    Resolve the technician assigned to the job.

    IMPORTANT:
    This lookup assumes Technician.technician_id is globally unique.
    If technician IDs are tenant-scoped, the assigned technician's tenant
    must also be persisted on the job and included in this query.
    """
    if job.assigned_technician_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job is not assigned to any technician",
        )

    technician = (
        db.query(Technician)
        .filter(
            Technician.technician_id == job.assigned_technician_id,
        )
        .first()
    )

    if technician is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Technician record not found",
        )

    return technician


def _get_job_or_404(
    db: Session,
    job_id: int,
    lock: bool = False,
) -> Job:
    """Fetch a job by its globally unique ID."""
    query = db.query(Job).filter(Job.id == job_id)

    if lock:
        query = query.with_for_update()

    job = query.first()

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    return job


def _verify_technician_assignment(
    technician: Technician,
    technician_identifier: str,
    job: Job,
) -> None:
    """Ensure the authenticated technician is assigned to this job."""
    allowed_identifiers = {
        str(technician.technician_id),
        str(technician.tech_id),
    }

    if str(technician_identifier) not in allowed_identifiers:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Technician identity does not match the assigned technician",
        )

    if (
        technician.technician_id != job.assigned_technician_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Technician not assigned to this job",
        )


def _get_job_closure(
    db: Session,
    job: Job,
) -> Optional[JobClosure]:
    """Find the closure record using the job's owning tenant."""
    return (
        db.query(JobClosure)
        .filter(
            JobClosure.job_id == job.id,
            JobClosure.tenant_id == job.tenant_id,
        )
        .first()
    )


def capture_customer_signature(
    db: Session,
    job_id: int,
    signature_data: CustomerSignatureCreate,
    technician_identifier: str,
    tenant_id: str,
    user_role: str = "TECHNICIAN",
) -> CustomerSignature:
    """
    Persist a customer signature for a completed job.

    The tenant_id argument represents the authenticated technician's tenant.
    The job's own tenant_id is used for job-closure and signature records.
    """
    role_str = str(user_role or "").strip().lower()

    if role_str != "technician":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only technicians can capture customer signatures",
        )

    technician_identifier = str(technician_identifier)
    authenticated_tenant_id = str(tenant_id)

    try:
        job = _get_job_or_404(
            db=db,
            job_id=job_id,
            lock=True,
        )

        technician = _get_assigned_technician(
            db=db,
            job=job,
        )

        # Confirm the request belongs to the authenticated technician.
        if str(technician.tenant_id) != authenticated_tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Technician does not belong to the authenticated tenant",
            )

        _verify_technician_assignment(
            technician=technician,
            technician_identifier=technician_identifier,
            job=job,
        )

        current_status = str(job.status or "").strip().upper()

        if current_status != "COMPLETED":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Customer signature can only be captured "
                    "after job completion"
                ),
            )

        # The job's tenant owns the closure record.
        closure = _get_job_closure(
            db=db,
            job=job,
        )

        if closure is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Job completion record is not available",
            )

        job_tenant_id = str(job.tenant_id)

        # Signature ownership follows the job, not the technician.
        existing_signature = (
            db.query(CustomerSignature)
            .filter(
                CustomerSignature.job_id == job.id,
                CustomerSignature.tenant_id == job_tenant_id,
            )
            .with_for_update()
            .first()
        )

        if existing_signature is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Customer signature already exists for this job",
            )

        signed_at = datetime.now(timezone.utc)

        signature = CustomerSignature(
            job_id=job.id,
            job_closure_id=closure.id,
            tenant_id=job_tenant_id,
            signature_data=signature_data.signature_data,
            captured_by=technician_identifier,
            signed_at=signed_at,
        )

        db.add(signature)
        db.commit()
        db.refresh(signature)

        return signature

    except HTTPException:
        db.rollback()
        raise

    except Exception as exc:
        db.rollback()

        # Keep the internal exception in server logs, not the API response.
        import logging

        logging.getLogger(__name__).exception(
            "Failed to capture customer signature for job_id=%s",
            job_id,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to save customer signature",
        ) from exc


def get_customer_signature(
    db: Session,
    job_id: int,
    tenant_id: str,
    technician_identifier: str,
) -> CustomerSignature:
    """
    Retrieve a customer's signature for a job assigned to the technician.

    The technician must belong to the authenticated tenant and be assigned
    to the job. The signature itself is queried under the job's tenant.
    """
    authenticated_tenant_id = str(tenant_id)
    technician_identifier = str(technician_identifier)

    job = _get_job_or_404(
        db=db,
        job_id=job_id,
    )

    technician = _get_assigned_technician(
        db=db,
        job=job,
    )

    if str(technician.tenant_id) != authenticated_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Technician does not belong to the authenticated tenant",
        )

    _verify_technician_assignment(
        technician=technician,
        technician_identifier=technician_identifier,
        job=job,
    )

    job_tenant_id = str(job.tenant_id)

    signature = (
        db.query(CustomerSignature)
        .filter(
            CustomerSignature.job_id == job.id,
            CustomerSignature.tenant_id == job_tenant_id,
        )
        .first()
    )

    if signature is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer signature not found",
        )

    return signature