"""
Intake Agent schemas for FieldOps Commander AI.

The Intake Agent converts a customer's natural-language job request
into structured information that can be consumed by the Planning Agent.
"""

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class IntakeServiceInfo(BaseModel):
    """Structured service information extracted from the request."""

    name: Optional[str] = Field(
        default=None,
        description="Main service requested by the customer."
    )

    keywords: list[str] = Field(
        default_factory=list,
        description="Important service-related keywords."
    )


class IntakeProblemInfo(BaseModel):
    """Problem information extracted from the customer request."""

    summary: Optional[str] = Field(
        default=None,
        description="Short summary of the actual problem."
    )

    keywords: list[str] = Field(
        default_factory=list,
        description="Important problem-related keywords."
    )


class IntakeScheduleInfo(BaseModel):
    """Requested date and time constraints."""

    requested_date: Optional[date] = Field(
        default=None,
        description="Requested service date when it can be determined."
    )

    time_constraint: Optional[str] = Field(
        default=None,
        description="Customer's requested time constraint, such as 'before 16:00'."
    )


class IntakeLocationInfo(BaseModel):
    """Location information relevant to the job."""

    address: Optional[str] = Field(
        default=None,
        description="Customer/job location address."
    )


class IntakeCustomerInfo(BaseModel):
    """Trusted customer information supplied by the backend."""

    customer_id: Optional[int] = Field(
        default=None,
        description="Existing customer/user ID."
    )

    name: Optional[str] = Field(
        default=None,
        description="Customer name."
    )

    contact_number: Optional[str] = Field(
        default=None,
        description="Customer contact number."
    )


class IntakeDecision(BaseModel):
    """
    Final structured output produced by the Intake Agent.

    The agent extracts the meaning of the customer's request.
    It does not select or assign technicians.
    """

    job_id: Optional[int] = Field(
        default=None,
        description="Existing job ID supplied by the backend."
    )

    customer: IntakeCustomerInfo = Field(
        default_factory=IntakeCustomerInfo
    )

    service: IntakeServiceInfo = Field(
        default_factory=IntakeServiceInfo
    )

    problem: IntakeProblemInfo = Field(
        default_factory=IntakeProblemInfo
    )

    schedule: IntakeScheduleInfo = Field(
        default_factory=IntakeScheduleInfo
    )

    location: Optional[IntakeLocationInfo] = Field(
        default=None,
        description="Location information relevant to the job."
    )

    priority: Optional[str] = Field(
        default=None,
        description="Existing job/request priority supplied by the backend."
    )

    required_skill: Optional[str] = Field(
        default=None,
        description="Required technician skill when already known by the backend."
    )

    original_request: Optional[str] = Field(
        default=None,
        description="Original customer request text."
    )