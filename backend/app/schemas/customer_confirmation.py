"""
Pydantic schemas for customer completion confirmation.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class CustomerConfirmationDecision(str, Enum):
    """Allowed customer completion decisions."""

    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class CustomerConfirmationCreate(BaseModel):
    """Request body submitted by the authenticated customer."""

    decision: CustomerConfirmationDecision

    comments: str | None = Field(
        default=None,
        max_length=2000,
    )


class CustomerConfirmationResponse(BaseModel):
    """Canonical customer confirmation response."""

    status: CustomerConfirmationDecision
    job_id: int
    confirmation_id: int
    confirmed_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )