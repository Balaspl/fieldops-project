
"""
job_assignment_repository.py

Repository responsible for JobAssignment database operations.

Responsibilities
----------------
- Store AI technician recommendations.
- Retrieve the current technician.
- Retrieve the next ranked technician.
- Update technician assignment status.

This repository contains NO business logic.
It only communicates with the database.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import JobAssignment


class JobAssignmentRepository:
    """
    Repository for JobAssignment database operations.
    """

    def __init__(self, db: Session):
        self.db = db

    # ---------------------------------------------------------
    # CREATE
    # ---------------------------------------------------------
    def save_recommendations(
        self,
        job_id: int,
        tenant_id: str,
        recommendations: list[dict],
    ) -> None:
        """
        Store all technician recommendations for a job.

        An empty recommendation list creates no records.
        """
        for recommendation in recommendations:
            technician_id = int(recommendation["technician_id"])
            rank = int(recommendation["rank"])

            assignment = JobAssignment(
                job_id=job_id,
                tenant_id=tenant_id,
                technician_id=technician_id,
                rank=rank,
                status="PENDING",
                is_current=(rank == 1),
            )

            # Add every recommendation to the database session.
            self.db.add(assignment)

    # ---------------------------------------------------------
    # READ
    # ---------------------------------------------------------

    def get_current_candidate(
        self,
        job_id: int,
    ) -> Optional[JobAssignment]:
        """
        Return the technician currently being offered the job.

        A current candidate is identified by is_current=True.
        """
        return (
            self.db.query(JobAssignment)
            .filter(
                JobAssignment.job_id == job_id,
                JobAssignment.is_current.is_(True),
            )
            .order_by(JobAssignment.rank.asc())
            .first()
        )

    # ---------------------------------------------------------

    def get_next_candidate(
        self,
        job_id: int,
        *,
        after_rank: int | None = None,
    ) -> Optional[JobAssignment]:
        """
        Return the next pending ranked technician.

        If after_rank is supplied, return the first pending candidate
        whose rank is greater than after_rank.

        If after_rank is not supplied, use the current candidate's rank.
        """
        current = self.get_current_candidate(job_id)

        if current is None and after_rank is None:
            return None

        effective_rank = (
            after_rank
            if after_rank is not None
            else current.rank
        )

        return (
            self.db.query(JobAssignment)
            .filter(
                JobAssignment.job_id == job_id,
                JobAssignment.rank > effective_rank,
                JobAssignment.status == "PENDING",
            )
            .order_by(JobAssignment.rank.asc())
            .first()
        )

    # ---------------------------------------------------------

    def get_remaining_candidates(
        self,
        *,
        job_id: int,
        after_rank: int,
    ) -> List[JobAssignment]:
        """
        Return all pending candidates after the supplied rank.
        """
        return (
            self.db.query(JobAssignment)
            .filter(
                JobAssignment.job_id == job_id,
                JobAssignment.status == "PENDING",
                JobAssignment.rank > after_rank,
            )
            .order_by(JobAssignment.rank.asc())
            .all()
        )

    # ---------------------------------------------------------

    def get_rejected_technician_ids(
        self,
        job_id: int,
    ) -> List[int]:
        """
        Return technicians who have already rejected or timed out.

        TIMEOUT is included because a technician who did not respond
        must also be excluded from future planning batches.
        """
        rows = (
            self.db.query(JobAssignment)
            .filter(
                JobAssignment.job_id == job_id,
                JobAssignment.status.in_(
                    ["REJECTED", "TIMEOUT"]
                ),
            )
            .all()
        )

        return [
            int(row.technician_id)
            for row in rows
        ]

    # ---------------------------------------------------------
    # STATE UPDATES
    # ---------------------------------------------------------

    def mark_assigned(
        self,
        assignment: JobAssignment,
    ) -> None:
        """
        Mark that the technician has been offered the job.

        The assignment remains PENDING until the technician accepts,
        rejects, or times out.
        """
        assignment.assigned_at = datetime.now(timezone.utc)
        assignment.status = "PENDING"
        assignment.is_current = True

    # ---------------------------------------------------------

    def mark_accepted(
        self,
        assignment: JobAssignment,
    ) -> None:
        """
        Mark technician as accepted.
        """
        assignment.status = "ACCEPTED"
        assignment.responded_at = datetime.now(timezone.utc)
        assignment.is_current = False

    # ---------------------------------------------------------

    def mark_rejected(
        self,
        assignment: JobAssignment,
    ) -> None:
        """
        Mark technician as rejected.
        """
        assignment.status = "REJECTED"
        assignment.responded_at = datetime.now(timezone.utc)
        assignment.is_current = False

    # ---------------------------------------------------------

    def mark_timeout(
        self,
        assignment: JobAssignment,
    ) -> None:
        """
        Mark technician as timed out.
        """
        assignment.status = "TIMEOUT"
        assignment.responded_at = datetime.now(timezone.utc)
        assignment.is_current = False

    # ---------------------------------------------------------

    def promote_next_candidate(
        self,
        job_id: int,
        *,
        after_rank: int | None = None,
    ) -> Optional[JobAssignment]:
        """
        Promote the next pending technician to current.

        The previous candidate should already have been marked
        REJECTED or TIMEOUT before this method is called.
        """
        next_candidate = self.get_next_candidate(
            job_id,
            after_rank=after_rank,
        )

        if next_candidate is not None:
            next_candidate.is_current = True

        return next_candidate

    # ---------------------------------------------------------
    # TRANSACTION
    # ---------------------------------------------------------

    def save(self) -> None:
        """
        Commit pending database changes.
        """
        self.db.commit()

    # ---------------------------------------------------------

    def refresh(
        self,
        assignment: JobAssignment,
    ) -> None:
        """
        Refresh an assignment from the database.
        """
        self.db.refresh(assignment)
