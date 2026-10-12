
"""
planning.py

Pydantic schema representing the Planning Agent decision.

The Planning Agent ranks eligible technician candidates and returns:
- The first three recommendations for the current dispatch batch.
- The complete ranked technician pool for subsequent batches.
"""

from typing import Literal, Optional, Any, Dict, List

from pydantic import BaseModel, Field


class RecommendedTechnician(BaseModel):
    technician_id: int = Field(
        ...,
        description="Recommended technician identifier.",
    )

    rank: int = Field(
        ...,
        ge=1,
        description="Global rank in the eligible technician pool.",
    )

    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score for this recommendation.",
    )

    estimated_eta: int = Field(
        ...,
        ge=0,
        description="Estimated arrival time in minutes.",
    )


class PlanningDecision(BaseModel):
    """Structured AI decision returned by the Planning Agent."""

    action: Literal[
        "assign_technician",
        "manual_review",
        "no_assignment",
    ] = Field(
        ...,
        description="Planning decision.",
    )

    job_id: Optional[int] = Field(
        default=None,
        description="Job identifier.",
    )

    # First batch: only three technicians.
    recommended_technicians: List[RecommendedTechnician] = Field(
        default_factory=list,
        max_length=3,
        description=(
            "The first three technicians from the complete ranked pool."
        ),
    )

    # Complete pool: includes the first three and all remaining candidates.
    all_ranked_technicians: List[RecommendedTechnician] = Field(
        default_factory=list,
        description=(
            "All eligible technicians in global rank order, "
            "including the first three recommendations."
        ),
    )

    priority: Literal[
        "LOW",
        "MEDIUM",
        "HIGH",
        "CRITICAL",
    ] = Field(
        ...,
        description="Job priority.",
    )

    reason: str = Field(
        ...,
        min_length=10,
        description="Business explanation for the recommendation.",
    )


class PlanningContext(BaseModel):
    job_id: Optional[int] = None
    customer_request: Dict
    available_technicians: List[Dict[str, Any]]
    rejected_technician_ids: List[int] = Field(
        default_factory=list,
        description=(
            "Technicians who have already rejected or timed out "
            "for this job."
        ),
    )
