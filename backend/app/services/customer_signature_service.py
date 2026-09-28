"""
customer_signature_service.py

Service for capturing and retrieving customer signatures associated with
an authenticated technician's completed job.
"""

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from ..models import Job, Technician
from ..models.customer_signature import CustomerSignature
from ..models.job_closure import JobClosure
from ..schemas import CustomerSignatureCreate


def _get_assigned_technician(
    db: Session,
    job: Job,
    tenant_id: str,
) -> Technician:
    """Resolve the job's assigned technician inside the authenticated tenant."""
    if job.assigned_technician_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job is not assigned to any technician",
        )

    technician = (
        db.query(Technician)
        .filter(
            Technician.tenant_id == tenant_id,
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


def capture_customer_signature(
    db: Session,
    job_id: int,
    signature_data: CustomerSignatureCreate,
    technician_identifier: str,
    tenant_id: str,
    user_role: str = "TECHNICIAN",
) -> CustomerSignature:
    """
    Persist one customer signature for a completed job.

    Authorization and tenant/object checks are repeated here so the service
    cannot be safely reused in a way that bypasses the authenticated
    technician boundary.
    """
    role_str = (user_role or "").strip().lower()
    if role_str != "technician":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only technicians can capture customer signatures",
        )

    tenant_id = str(tenant_id)
    technician_identifier = str(technician_identifier)

    job = (
        db.query(Job)
        .filter(
            Job.id == job_id,
            Job.tenant_id == tenant_id,
        )
        .with_for_update()
        .first()
    )

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    technician = _get_assigned_technician(
        db=db,
        job=job,
        tenant_id=tenant_id,
    )

    identifier_matches = {
        str(technician.technician_id),
        str(technician.tech_id),
    }

    if technician_identifier not in identifier_matches:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Technician not assigned to this job",
        )

    current_status = (job.status or "").strip().upper()

    if current_status != "COMPLETED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Customer signature can only be captured after job completion",
        )

    closure = (
        db.query(JobClosure)
        .filter(
            JobClosure.job_id == job_id,
            JobClosure.tenant_id == tenant_id,
        )
        .first()
    )

    if closure is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Job completion record is not available",
        )

    existing_signature = (
        db.query(CustomerSignature)
        .filter(
            CustomerSignature.job_id == job_id,
            CustomerSignature.tenant_id == tenant_id,
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
        job_id=job_id,
        job_closure_id=closure.id,
        tenant_id=tenant_id,
        signature_data=signature_data.signature_data,
        captured_by=technician_identifier,
        signed_at=signed_at,
    )

    db.add(signature)

    try:
        db.commit()
        db.refresh(signature)
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to save customer signature",
        )

    return signature


def get_customer_signature(
    db: Session,
    job_id: int,
    tenant_id: str,
    technician_identifier: str,
) -> CustomerSignature:
    """
    Retrieve the existing customer signature for a job.

    Access is tenant-scoped and limited to the technician assigned to the job.
    """
    tenant_id = str(tenant_id)
    technician_identifier = str(technician_identifier)

    job = (
        db.query(Job)
        .filter(
            Job.id == job_id,
            Job.tenant_id == tenant_id,
        )
        .first()
    )

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    technician = _get_assigned_technician(
        db=db,
        job=job,
        tenant_id=tenant_id,
    )

    if technician_identifier not in {
        str(technician.technician_id),
        str(technician.tech_id),
    }:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Technician not assigned to this job",
        )

    signature = (
        db.query(CustomerSignature)
        .filter(
            CustomerSignature.job_id == job_id,
            CustomerSignature.tenant_id == tenant_id,
        )
        .first()
    )

    if signature is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer signature not found",
        )

    return signature
