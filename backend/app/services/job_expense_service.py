"""
Service for technician-submitted job expenses.

The authenticated technician and tenant are resolved by the route. This
service repeats the tenant/object-access checks before persistence so expense
records cannot be created against another technician's job or another tenant.
"""

from decimal import Decimal
from typing import Union

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from ..models import Job, Technician
from ..models.job_expense import JobExpense
from ..schemas import JobExpenseCreate


MONEY_QUANTUM = Decimal("0.01")
JOB_EXPENSE_MAX_DIGITS = 12
JOB_EXPENSE_MAX_DESCRIPTION_LENGTH = 2_000


def _validate_amount(amount: Union[Decimal, str, int, float]) -> Decimal:
    """Validate and normalize a monetary amount without silently changing it."""
    try:
        canonical = amount if isinstance(amount, Decimal) else Decimal(str(amount))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Expense amount must be a valid decimal number",
        ) from exc

    if not canonical.is_finite():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Expense amount must be finite",
        )

    if canonical <= Decimal("0"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Expense amount must be greater than zero",
        )

    if canonical != canonical.quantize(MONEY_QUANTUM):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Expense amount cannot have more than 2 decimal places",
        )

    digits = len(canonical.as_tuple().digits)
    if digits > JOB_EXPENSE_MAX_DIGITS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Expense amount exceeds the supported precision",
        )

    return canonical


def _validate_description(description: str) -> str:
    """Validate and canonicalize the technician-entered description."""
    if not isinstance(description, str):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Expense description must be text",
        )

    canonical = description.strip()

    if not canonical:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Expense description is required",
        )

    if len(canonical) > JOB_EXPENSE_MAX_DESCRIPTION_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Expense description is too long",
        )

    return canonical


def create_job_expense(
    db: Session,
    job_id: int,
    expense_data: JobExpenseCreate,
    technician_id: int,
    tenant_id: str,
) -> JobExpense:
    """
    Persist one expense submitted by the authenticated technician.

    Tenant isolation and job ownership are enforced against database state;
    technician_id and tenant_id are never taken from the client payload.
    """
    tenant_id = str(tenant_id)

    amount = _validate_amount(expense_data.amount)
    description = _validate_description(expense_data.description)

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

    if job.assigned_technician_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job is not assigned to any technician",
        )

    if job.assigned_technician_id != technician_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Technician is not assigned to this job",
        )

    technician = (
        db.query(Technician)
        .filter(
            Technician.tenant_id == tenant_id,
            Technician.technician_id == technician_id,
        )
        .first()
    )

    if technician is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Technician record not found",
        )

    expense = JobExpense(
        job_id=job.id,
        technician_id=technician.technician_id,
        tenant_id=tenant_id,
        amount=amount,
        description=description,
    )

    db.add(expense)

    try:
        db.commit()
        db.refresh(expense)
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to save job expense",
        ) from exc

    return expense
