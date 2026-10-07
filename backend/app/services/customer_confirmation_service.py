"""
Service layer for customer completion confirmation.
"""

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from ..models.customer_confirmation import CustomerConfirmation
from ..models_legacy import Job
from ..models.service_request import ServiceRequest
from ..models.job_closure import JobClosure
from ..schemas.customer_confirmation import (
    CustomerConfirmationCreate,
)


class CustomerConfirmationService:
    """
    Handles customer approval/rejection of completed jobs.

    This service:
    - verifies tenant ownership
    - verifies customer ownership
    - requires the job to be completed
    - requires a job closure record
    - prevents conflicting duplicate decisions
    - keeps technician completion data unchanged
    """

    @staticmethod
    def create_confirmation(
        db: Session,
        job_id: int,
        confirmation_data: CustomerConfirmationCreate,
        customer_id: str,
        tenant_id: str,
    ) -> CustomerConfirmation:

        # --------------------------------------------------
        # 1. Find the job inside the customer's tenant
        # --------------------------------------------------
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
                detail="Job not found.",
            )

        # --------------------------------------------------
        # 2. Verify customer ownership
        # --------------------------------------------------
        if str(job.customer_id) != str(customer_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to confirm this job.",
            )

        # --------------------------------------------------
        # 3. Customer confirmation is allowed only after
        #    technician completion
        # --------------------------------------------------
        if str(job.status).upper() != "COMPLETED":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Customer confirmation is allowed only for completed jobs.",
            )

        # --------------------------------------------------
        # 4. Job closure must exist
        # --------------------------------------------------
        closure = (
            db.query(JobClosure)
            .filter(
                JobClosure.job_id == job.id,
            )
            .first()
        )

        if closure is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Job closure is required before customer confirmation.",
            )

        # --------------------------------------------------
        # 5. Check for an existing confirmation
        # --------------------------------------------------
        existing = (
            db.query(CustomerConfirmation)
            .filter(
                CustomerConfirmation.job_id == job.id,
                CustomerConfirmation.tenant_id == tenant_id,
                CustomerConfirmation.customer_id == str(customer_id),
            )
            .first()
        )

        requested_decision = confirmation_data.decision.value

        # --------------------------------------------------
        # 6. Idempotent duplicate approval/rejection
        # --------------------------------------------------
        if existing is not None:

            if existing.decision == requested_decision:
                return existing

            # A customer cannot change an existing decision
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A different customer confirmation decision already exists for this job.",
            )

        # --------------------------------------------------
        # 7. Persist the customer decision
        # --------------------------------------------------
        confirmation = CustomerConfirmation(
            job_id=job.id,
            job_closure_id=closure.id,
            tenant_id=tenant_id,
            customer_id=str(customer_id),
            decision=requested_decision,
            comments=confirmation_data.comments,
            confirmed_at=datetime.now(timezone.utc),
        )

        db.add(confirmation)
        db.commit()
        db.refresh(confirmation)

        return confirmation