"""
state.py

LangGraph state definitions for the automated FieldOps workflow.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from typing_extensions import TypedDict


class ValidationErrorDetail(TypedDict, total=False):
    error_type: str  # "mismatch" | "unclear"
    field: str       # "service" | "location" | etc.
    message: str
    detected_value: Optional[str]
    expected_value: Optional[str]


class ValidatedJobRequirement(TypedDict, total=False):
    service: str
    required_skill: str
    location: str
    priority: str
    title: str
    description: str
    site_latitude: Optional[float]
    site_longitude: Optional[float]
    contact_number: Optional[str]
    customer_name: Optional[str]
    preferred_visit_date: Optional[str]


class IntakeGraphState(TypedDict, total=False):
    # Raw input request data
    raw_request: Dict[str, Any]

    # Extracted fields
    service: Optional[str]
    service_type: Optional[str]
    title: Optional[str]
    description: Optional[str]
    location: Optional[str]
    priority: Optional[str]
    site_latitude: Optional[float]
    site_longitude: Optional[float]
    contact_number: Optional[str]
    customer_name: Optional[str]
    preferred_visit_date: Optional[str]

    # Classification / Detection
    detected_service: Optional[str]
    detected_skill: Optional[str]

    # Validation outcome
    valid: bool
    error_type: Optional[str]
    field: Optional[str]
    message: Optional[str]
    detected_value: Optional[str]
    expected_value: Optional[str]
    validation_errors: List[ValidationErrorDetail]

    # Structured validated job requirement (only populated when valid is True)
    job_requirement: Optional[ValidatedJobRequirement]


class TopTechnicianRecommendation(TypedDict, total=False):
    rank: int
    technician_id: int | str
    technician_name: str
    organization_id: Optional[str | int]
    organization_name: str
    confidence: float
    estimated_eta: int
    organization_distance: float
    technician_distance: float
    distance_km: float
    workload: int


class PlanningGraphState(TypedDict, total=False):
    # Input: ONLY the validated job requirement produced by Intake Agent
    job_requirement: ValidatedJobRequirement

    # Optional database session or context
    db: Any

    # Candidate evaluation steps
    customer_coordinates: Optional[tuple[float, float]]
    eligible_organizations: List[Dict[str, Any]]
    all_eligible_technicians: List[TopTechnicianRecommendation]

    # Planning output
    job_id: Optional[str | int]
    total_eligible_technicians: int
    top_3: List[TopTechnicianRecommendation]
    top_3_technicians: List[TopTechnicianRecommendation]
    planning_response: Optional[Dict[str, Any]]
