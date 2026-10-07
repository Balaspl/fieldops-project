"""
Customer completion confirmation routes.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.customer_confirmation import (
    CustomerConfirmationCreate,
    CustomerConfirmationResponse,
)
from ..services.customer_confirmation_service import (
    CustomerConfirmationService,
)

router = APIRouter(
    prefix="/customer",
    tags=["Customer Confirmation"],
)


@router.post(
    "/jobs/{job_id}/confirmation",
    response_model=CustomerConfirmationResponse,
)
def create_customer_confirmation(
    job_id: int,
    confirmation_data: CustomerConfirmationCreate,
    db: Session = Depends(get_db),
):
    """
    Create a customer approval/rejection for a completed job.

    Authentication/authorization will be connected to the
    project's existing customer identity dependency.
    """

    # Temporary placeholder.
    # We will connect the real authenticated customer identity
    # after checking the project's existing auth dependency.
    raise NotImplementedError(
        "Customer identity dependency must be connected."
    )