from __future__ import annotations

from typing import Any, Literal, TypedDict


TechnicianEvent = Literal[
    "TECHNICIAN_ACCEPTED",
    "TECHNICIAN_REJECTED",
    "TECHNICIAN_TIMEOUT",
]


class DispatcherState(TypedDict, total=False):
    # Job
    job_id: int
    job: dict[str, Any]
    dispatch_attempt_id: str

    # Current complete Planning batch and its position
    all_candidates: list[dict[str, Any]]

    # Active Planning batch
    candidates: list[dict[str, Any]]
    batch_number: int
    current_index: int
    current_technician_id: int | None
    batch_exhausted: bool
    offer_status: str | None
    last_offer_outcome: str | None
    pending_retry: bool
    dispatch_exhausted: bool

    # Technician history across all batches
    attempted_technician_ids: list[int]
    rejected_technician_ids: list[int]

    # Technician response
    event: TechnicianEvent | None

    # Dispatcher output
    next_action: str | None
    assigned_technician_id: int | None

    # Planning control
    planning_required: bool
    replanning_required: bool

    # Error
    error: str | None
