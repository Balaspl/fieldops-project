"""
Portal schemas for Technician and Customer portals.

Pydantic models for request/response validation on portal-specific endpoints.
"""

from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator, ConfigDict


# ──────────────────────────────────────────────────
# Technician Profile Schemas
# ──────────────────────────────────────────────────

class TechnicianProfileCreate(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=200)
    mobile_number: str = Field(..., min_length=10, max_length=20)
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    emergency_contact: Optional[str] = None
    skills: Optional[List[str]] = Field(default_factory=list)
    experience: Optional[str] = None
    certifications: Optional[List[str]] = Field(default_factory=list)
    profile_photo: Optional[str] = None

    @field_validator("mobile_number")
    @classmethod
    def validate_mobile(cls, v):
        digits = "".join(c for c in v if c.isdigit())
        if len(digits) < 10:
            raise ValueError("Mobile number must have at least 10 digits")
        return v

    @field_validator("date_of_birth")
    @classmethod
    def validate_age(cls, v):
        if v is None:
            return v
        today = date.today()
        age = today.year - v.year - ((today.month, today.day) < (v.month, v.day))
        if age < 18:
            raise ValueError("Technician must be at least 18 years old")
        return v


class TechnicianProfileUpdate(TechnicianProfileCreate):
    """Same fields as create — all optional for partial updates."""
    full_name: Optional[str] = Field(None, min_length=2, max_length=200)
    mobile_number: Optional[str] = Field(None, min_length=10, max_length=20)


class TechnicianProfileResponse(BaseModel):
    id: str
    user_id: str
    tenant_id: str
    full_name: str
    profile_photo: Optional[str] = None
    mobile_number: str
    date_of_birth: Optional[date] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    emergency_contact: Optional[str] = None
    skills: Optional[List[str]] = None
    experience: Optional[str] = None
    certifications: Optional[List[str]] = None
    profile_completed: bool
    created_at: datetime
    updated_at: datetime

    # Email from the User model (joined)
    email: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ──────────────────────────────────────────────────
# Customer Profile Schemas
# ──────────────────────────────────────────────────

class CustomerProfileCreate(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=200)
    mobile_number: str = Field(..., min_length=10, max_length=20)
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    company_name: Optional[str] = None

    @field_validator("mobile_number")
    @classmethod
    def validate_mobile(cls, v):
        digits = "".join(c for c in v if c.isdigit())
        if len(digits) < 10:
            raise ValueError("Mobile number must have at least 10 digits")
        return v


class CustomerProfileUpdate(CustomerProfileCreate):
    full_name: Optional[str] = Field(None, min_length=2, max_length=200)
    mobile_number: Optional[str] = Field(None, min_length=10, max_length=20)


class CustomerProfileResponse(BaseModel):
    id: str
    user_id: str
    tenant_id: str
    full_name: str
    mobile_number: str
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    company_name: Optional[str] = None
    profile_completed: bool
    email: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ──────────────────────────────────────────────────
# Service Request Schemas
# ──────────────────────────────────────────────────

class ServiceRequestCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    description: str = Field(..., min_length=10)
    service_type: Optional[str] = None
    priority: str = Field(default="MEDIUM")
    preferred_visit_date: Optional[date] = None
    images: Optional[List[str]] = Field(default_factory=list)
    location: Optional[str] = None
    contact_number: Optional[str] = None
    site_latitude: Optional[float] = None
    site_longitude: Optional[float] = None

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v):
        valid = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
        if v.upper() not in valid:
            raise ValueError(f"Priority must be one of {valid}")
        return v.upper()


class ServiceRequestUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=10, max_length=200)
    description: Optional[str] = Field(None, min_length=25)
    service_type: Optional[str] = None
    priority: Optional[str] = None
    preferred_visit_date: Optional[date] = None
    images: Optional[List[str]] = None
    location: Optional[str] = None
    contact_number: Optional[str] = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, v):
        if v is None:
            return v

        v = v.strip()

        if len(v) < 10:
            raise ValueError("Title minimum 10 characters required")

        if not any(c.isalpha() for c in v):
            raise ValueError("Title must contain characters")

        return v

    @field_validator("description")
    @classmethod
    def validate_description(cls, v):
        if v is None:
            return v

        v = v.strip()

        if len(v) < 25:
            raise ValueError("Description minimum 25 characters required")

        return v

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v):
        if v is None:
            return v

        valid = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}

        value = v.upper()

        if value not in valid:
            raise ValueError(
                "Priority must be LOW, MEDIUM, HIGH or CRITICAL"
            )

        return value

    @field_validator("preferred_visit_date")
    @classmethod
    def validate_preferred_visit_date(cls, v):
        if v is None:
            return v

        if v < date.today():
            raise ValueError(
                "Preferred date cannot be before today"
            )

        return v

    @field_validator("contact_number")
    @classmethod
    def validate_contact_number(cls, v):
        if v is None:
            return v

        v = v.strip()

        if not v.isdigit():
            raise ValueError("Contact number must contain numbers only")

        if len(v) != 10:
            raise ValueError(
                "Contact number must be exactly 10 digits"
            )

        return v

    @field_validator("location")
    @classmethod
    def validate_location(cls, v):
        if v is None:
            return v

        v = v.strip()

        if not v:
            raise ValueError("Location is required")

        return v

class ServiceRequestResponse(BaseModel):
    id: int
    request_number: str
    customer_user_id: str
    tenant_id: str
    title: str
    description: str
    service_type: Optional[str] = None
    priority: str
    preferred_visit_date: Optional[date] = None
    images: Optional[List[str]] = None
    location: Optional[str] = None
    contact_number: Optional[str] = None
    status: str
    linked_job_id: Optional[int] = None
    cancellation_reason: Optional[str] = None
    cancelled_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ──────────────────────────────────────────────────
# Technician Job View Schemas
# ──────────────────────────────────────────────────

class TechnicianJobResponse(BaseModel):
    id: int
    customer_name: Optional[str] = None
    location: Optional[str] = None
    issue_description: Optional[str] = None
    priority: Optional[str] = None
    service_type: Optional[str] = None
    contact_number: Optional[str] = None
    preferred_service_date: Optional[date] = None
    status: Optional[str] = None
    required_skill: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    sla_deadline: Optional[datetime] = None
    assigned_at: Optional[datetime] = None
    site_address: Optional[str] = None
    site_latitude: Optional[float] = None
    site_longitude: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


class TechnicianJobActionRequest(BaseModel):
    notes: Optional[str] = None


class TechnicianJobRejectRequest(BaseModel):
    reason: str = Field(..., min_length=10, max_length=1000)


class TechnicianJobCompleteRequest(BaseModel):
    completion_notes: Optional[str] = None
    photos: Optional[List[str]] = Field(default_factory=list)
    signature: Optional[str] = None


# ──────────────────────────────────────────────────
# Declined Jobs Schemas
# ──────────────────────────────────────────────────

class DeclinedJobResponse(BaseModel):
    id: int
    customer_name: Optional[str] = None
    technician_name: Optional[str] = None
    rejection_reason: Optional[str] = None
    priority: Optional[str] = None
    sla_deadline: Optional[datetime] = None
    assigned_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None
    status: Optional[str] = None
    location: Optional[str] = None
    service_type: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class DeclinedJobReassignRequest(BaseModel):
    new_technician_id: int


# ──────────────────────────────────────────────────
# Portal Dashboard Schemas
# ──────────────────────────────────────────────────

class TechnicianDashboardResponse(BaseModel):
    total_assigned: int = 0
    active_jobs: int = 0
    completed_today: int = 0
    pending_acceptance: int = 0
    total_completed: int = 0
    rejected_jobs: int = 0


class CustomerDashboardResponse(BaseModel):
    total_requests: int = 0
    pending_requests: int = 0
    active_jobs: int = 0
    completed_jobs: int = 0


# ──────────────────────────────────────────────────
# Change Password Schema
# ──────────────────────────────────────────────────

class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, v, info):
        if "new_password" in info.data and v != info.data["new_password"]:
            raise ValueError("Passwords do not match")
        return v


# ──────────────────────────────────────────────────
# Customer Job Tracking Schema
# ──────────────────────────────────────────────────

class CustomerJobTrackingResponse(BaseModel):
    id: int
    customer_name: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    service_type: Optional[str] = None
    location: Optional[str] = None
    assigned_technician_name: Optional[str] = None
    assigned_technician_photo: Optional[str] = None
    assigned_technician_phone: Optional[str] = None
    estimated_arrival: Optional[datetime] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
