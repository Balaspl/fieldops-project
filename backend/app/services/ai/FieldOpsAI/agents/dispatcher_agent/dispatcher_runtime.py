
"""
dispatcher_runtime.py

Runtime integration for the FieldOps Dispatcher Agent.

Responsibilities:
- Load real jobs from the database.
- Preserve the complete ranked technician pool.
- Use the first three candidates for the initial dispatch batch.
- Request fresh planning when the existing candidate pool is exhausted.
- Start the LangGraph dispatcher.
- Offer jobs through the existing technician portal.
- Create real in-app notifications.
- Start the real acceptance timer.
- Resume the graph when technician accepts/rejects/times out.

Important:
- This file does NOT use the manual assignment endpoint.
- LangGraph owns orchestration.
- Database/service layer owns operational side effects.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.redis_client import get_redis_client

from app import models

from app.services.ai.FieldOpsAI.agents.dispatcher_agent.dispatcher_agent import (
    DispatcherGraph,
    DispatcherState,
)
from app.services.ai.FieldOpsAI.graph.planning_graph import planning_graph
from app.services.ai.FieldOpsAI.services.planning_service import PlanningService

from app.services.timer_service import TimerService


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------

def log_planning_top3(job_id, ranked, excluded=None):
    excluded = excluded or set()
    batch = ranked[:3]
    batch_number = len(excluded) // 3 + 1
    remaining_after = max(0, len(ranked) - len(batch))

    print("=" * 50)
    print(f"PLANNING BATCH {batch_number}" if batch_number == 1 else f"REPLANNING BATCH {batch_number}")
    print("=" * 14)
    print(f"Job ID: {job_id}")
    print(f"Technicians in this batch: {len(batch)}")
    print(f"Remaining after this batch: {remaining_after}")
    if excluded:
        print(f"Already attempted: {sorted(excluded)}")
    print()

    for i, t in enumerate(batch, start=1):
        print(f"Rank {i}:")
        print(f"Technician: {t.get('technician_name')} (ID: {t.get('technician_id')})")
        print(f"Organization: {t.get('organization_name')} (ID: {t.get('organization_id')})")
        print(f"Organization Distance: {t.get('organization_distance')} km")
        print(f"Technician Distance: {t.get('technician_distance')} km")
        print(f"Confidence: {t.get('confidence')}")
        print(f"Estimated ETA: {t.get('estimated_eta')} mins")
        print(f"Workload: {t.get('workload')}")
        print()

    if not batch:
        print("No eligible technicians remain.")
        print()

    print("=" * 50)

class DispatcherRuntime:
    """
    Real runtime bridge between LangGraph Dispatcher and FieldOps backend.

    LangGraph:
        - controls candidate sequence
        - waits for technician response
        - handles ACCEPT / REJECT / TIMEOUT
        - requests next planning batch

    Backend:
        - loads DB data
        - assigns technician
        - sends notification
        - starts timer
        - persists job state
    """

    def __init__(self) -> None:
        self.graph = DispatcherGraph(
            offer_job=self.offer_job,
            request_planning=self.request_planning,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start_dispatch(
        self,
        job_id: int,
        initial_candidates: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Start automatic dispatch for a real job.

        initial_candidates should contain the COMPLETE ranked candidate
        pool if the dispatcher must try later candidates before replanning.

        The graph initially offers only the first three candidates.
        """

        with SessionLocal() as db:
            job = self._get_job(db, job_id)

            if job is None:
                raise ValueError(f"Job {job_id} not found")

            # Do not start another automatic dispatch if the job
            # is already assigned / accepted / active.
            if self._job_is_already_dispatched(job):
                logger.info(
                    "Skipping dispatch for job=%s because it is already dispatched",
                    job_id,
                )

                return {
                    "job_id": job_id,
                    "status": "ALREADY_DISPATCHED",
                    "assigned_technician_id": getattr(
                        job,
                        "assigned_technician_id",
                        None,
                    ),
                }

            job_state = self._job_to_state(job)

        # --------------------------------------------------------------
        # Reuse the existing Planning Agent result when supplied.
        #
        # IMPORTANT:
        # To exhaust the original ranking before replanning, the caller
        # must pass all_ranked_technicians, not only top_3.
        # --------------------------------------------------------------

        if initial_candidates:
            all_candidates = self._normalize_candidates(
                initial_candidates,
                excluded_ids=set(),
            )

            logger.info(
                "DISPATCHER USING EXISTING PLANNING RESULT | "
                "job_id=%s | total_candidates=%s",
                job_id,
                len(all_candidates),
            )

        else:
            # Backward-compatible fallback for callers that do not
            # supply an initial Planning Agent result.
            logger.info(
                "DISPATCHER REQUESTING INITIAL PLANNING | job_id=%s",
                job_id,
            )

            all_candidates = await self.request_planning(
                job_id,
                [],
            )

        if not all_candidates:
            logger.warning(
                "No available technicians for job=%s",
                job_id,
            )

            return {
                "job_id": job_id,
                "status": "NO_TECHNICIANS_AVAILABLE",
                "candidates": [],
            }

        # Preserve the complete pool separately from the active batch.
        state: DispatcherState = {
            "job_id": job_id,
            "job": job_state,
            "all_candidates": all_candidates,
            "candidates": all_candidates[:3],
            "batch_number": 1,
            "current_index": 0,
            "current_technician_id": None,
            "attempted_technician_ids": [],
            "rejected_technician_ids": [],
            "event": None,
            "next_action": None,
            "assigned_technician_id": None,
            "planning_required": False,
            "replanning_required": False,
            "error": None,
        }

        logger.info(
            "Starting dispatcher graph job=%s | total_candidates=%s | "
            "initial_batch=%s",
            job_id,
            len(all_candidates),
            [
                candidate["technician_id"]
                for candidate in all_candidates[:3]
            ],
        )

        return await self.graph.start_dispatch(state)

    async def resume_dispatch(
        self,
        *,
        job_id: int,
        event: str,
    ) -> dict[str, Any]:
        """
        Resume a paused DispatcherGraph.

        Called by:
            technician ACCEPT
            technician REJECT
            timeout worker
        """

        allowed_events = {
            "TECHNICIAN_ACCEPTED",
            "TECHNICIAN_REJECTED",
            "TECHNICIAN_TIMEOUT",
        }

        if event not in allowed_events:
            raise ValueError(
                f"Unsupported dispatcher event: {event}"
            )

        logger.info(
            "Resuming dispatcher graph job=%s event=%s",
            job_id,
            event,
        )

        return await self.graph.resume_dispatch(
            job_id=job_id,
            event=event,
        )

    # ------------------------------------------------------------------
    # Planning adapter
    # ------------------------------------------------------------------

    
    async def request_planning(
        self,
        job_id: int,
        excluded_technician_ids: list[int],
    ) -> list[dict[str, Any]]:
        """
        Request a fresh deterministic Planning Graph ranking.

        Previously attempted technicians are excluded.
        Returns the complete fresh ranking; DispatcherGraph selects
        the next batch of at most three candidates.
        """

        excluded = {
            int(technician_id)
            for technician_id in (excluded_technician_ids or [])
        }

        logger.info(
            "PLANNING GRAPH REQUEST | job_id=%s | excluded=%s",
            job_id,
            sorted(excluded),
        )

        with SessionLocal() as db:
            job = self._get_job(db, job_id)

            if job is None:
                raise ValueError(f"Job {job_id} not found")

            job_requirement = {
                "service": getattr(job, "service_type", None),
                "required_skill": getattr(job, "required_skill", None),
                "location": getattr(job, "location", None),
                "priority": getattr(job, "priority", None),
                "title": getattr(job, "title", None),
                "description": getattr(
                    job, "issue_description", None
                ),
                "site_latitude": getattr(
                    job, "site_latitude", None
                ),
                "site_longitude": getattr(
                    job, "site_longitude", None
                ),
                "contact_number": getattr(
                    job, "contact_number", None
                ),
                "customer_name": getattr(
                    job, "customer_name", None
                ),
                "preferred_visit_date": getattr(
                    job, "preferred_service_date", None
                ),
            }

            result = planning_graph.invoke(
                {
                    "job_id": job_id,
                    "job_requirement": job_requirement,
                    "excluded_technician_ids": sorted(excluded),
                }
            )
            ranked_all = result.get("all_ranked_technicians") or []

            ranked = [
                t for t in ranked_all
                if int(t["technician_id"]) not in excluded
            ]

            log_planning_top3(job_id, ranked, excluded)

        recommendations = (
            result.get("all_ranked_technicians")
            or result.get("all_eligible_technicians")
            or result.get("top_3_technicians")
            or result.get("top_3")
            or []
        )

        raw_candidates: list[dict[str, Any]] = []

        for technician in recommendations:
            # Support dictionaries and Pydantic/model objects.
            if isinstance(technician, dict):
                get_value = technician.get
            else:
                model_dump = getattr(technician, "model_dump", None)
                if callable(model_dump):
                    technician = model_dump()
                    get_value = technician.get
                else:
                    get_value = lambda key, default=None: getattr(
                        technician, key, default
                    )

            technician_id = get_value("technician_id")

            if technician_id is None:
                logger.warning(
                    "Skipping planning result without technician_id: %r",
                    technician,
                )
                continue

            raw_candidates.append(
                {
                    "technician_id": technician_id,
                    "rank": get_value("rank"),
                    "confidence": get_value("confidence", 0.0),
                    "estimated_eta": get_value("estimated_eta", 0),
                }
            )

        candidates = self._normalize_candidates(
            raw_candidates,
            excluded_ids=excluded,
        )

        logger.info(
            "PLANNING GRAPH RESULT | job_id=%s | "
            "candidate_count=%s | excluded=%s | candidates=%s",
            job_id,
            len(candidates),
            sorted(excluded),
            [candidate["technician_id"] for candidate in candidates],
        )

        return candidates


    @staticmethod
    def _normalize_candidates(
        candidates: list[dict[str, Any]],
        excluded_ids: set[int],
    ) -> list[dict[str, Any]]:
        """
        Normalize candidate dictionaries and remove excluded/duplicate IDs.

        Candidate order is preserved by rank.
        """

        normalized: list[dict[str, Any]] = []
        seen_ids: set[int] = set()

        for candidate in candidates or []:
            
            if isinstance(candidate, dict):
                candidate_data = candidate
            else:
                model_dump = getattr(candidate, "model_dump", None)

                if callable(model_dump):
                    candidate_data = model_dump()
                elif hasattr(candidate, "technician_id"):
                    candidate_data = {
                        "technician_id": getattr(candidate, "technician_id", None),
                        "rank": getattr(candidate, "rank", None),
                        "confidence": getattr(candidate, "confidence", 0.0),
                        "estimated_eta": getattr(candidate, "estimated_eta", 0),
                    }
                else:
                    logger.warning(
                        "Skipping invalid candidate record: %r",
                        candidate,
                    )
                    continue
                
            candidate = candidate_data


            try:
                technician_id = int(candidate["technician_id"])
            except (KeyError, TypeError, ValueError):
                logger.warning(
                    "Skipping candidate with invalid technician ID: %r",
                    candidate,
                )
                continue

            if technician_id in excluded_ids:
                continue

            if technician_id in seen_ids:
                continue

            try:
                raw_rank = candidate.get(
                    "rank",
                    len(normalized) + 1,
                )
                rank = int(
                    raw_rank
                    if raw_rank is not None
                    else len(normalized) + 1
                )

                confidence = float(
                    candidate.get("confidence", 0.0) or 0.0
                )

                estimated_eta = int(
                    candidate.get("estimated_eta", 0) or 0
                )

            except (TypeError, ValueError):
                logger.warning(
                    "Skipping candidate with invalid ranking data: %r",
                    candidate,
                )
                continue

            normalized.append({
                **candidate,
                "technician_id": technician_id,
                "rank": rank,
                "confidence": confidence,
                "estimated_eta": estimated_eta,
            })

            seen_ids.add(technician_id)

        normalized.sort(key=lambda candidate: candidate["rank"])

        return normalized

    # ------------------------------------------------------------------
    # Offer job
    # ------------------------------------------------------------------

    async def offer_job(
        self,
        job_state: dict[str, Any],
        technician_id: int,
    ) -> None:
        """
        Offer a job to a real technician.

        This retains the existing behavior from the supplied code:
        the job is marked ASSIGNED and committed before acceptance.

        Verify this behavior against the technician portal's acceptance
        and rejection handlers before changing the assignment lifecycle.
        """

        job_id = int(job_state["id"])

        logger.info(
            "=================================================="
        )
        logger.info(
            "AUTOMATIC DISPATCH OFFER | job=%s | technician=%s",
            job_id,
            technician_id,
        )

        with SessionLocal() as db:
            job = self._get_job(db, job_id)

            if job is None:
                raise ValueError(
                    f"Job {job_id} not found while offering"
                )

            logger.info(
                "INITIAL JOB STATE | status=%s | technician=%s",
                getattr(job, "status", None),
                getattr(
                    job,
                    "assigned_technician_id",
                    None,
                ),
            )

            technician = (
                db.query(models.Technician)
                .filter(
                    models.Technician.technician_id
                    == technician_id,
                )
                .first()
            )

            logger.warning(
                "OFFER JOB TECHNICIAN RESOLVED | "
                "job_id=%s technician_id=%s "
                "technician_tenant=%s "
                "job_tenant=%s "
                "technician_user_id=%s",
                job_id,
                technician_id,
                getattr(technician, "tenant_id", None),
                getattr(job, "tenant_id", None),
                getattr(technician, "tech_id", None),
            )

            if technician is None:
                raise ValueError(
                    f"Technician {technician_id} not found "
                    f"for job {job_id}"
                )

            logger.info(
                "TECHNICIAN FOUND | id=%s | name=%s | status=%s",
                technician_id,
                getattr(technician, "name", None),
                getattr(
                    technician,
                    "technician_status",
                    None,
                ),
            )

            # Keep the original availability-status check commented out,
            # as in the supplied implementation.
            #
            # if (
            #     getattr(technician, "technician_status", None)
            #     != "AVAILABLE"
            # ):
            #     raise ValueError(
            #         f"Technician {technician_id} is no longer available"
            #     )

            current_jobs = int(
                getattr(
                    technician,
                    "current_jobs",
                    0,
                )
                or 0
            )

            max_jobs = int(
                getattr(
                    technician,
                    "max_jobs",
                    5,
                )
                or 5
            )

            if current_jobs >= max_jobs:
                raise ValueError(
                    f"Technician {technician_id} is at job capacity"
                )

            # ----------------------------------------------------------
            # Assign job using the existing behavior.
            # ----------------------------------------------------------

            logger.info(
                "ASSIGNING TECHNICIAN IN MEMORY | "
                "job=%s | technician=%s",
                job_id,
                technician_id,
            )

            job.assigned_technician_id = technician.technician_id

            if hasattr(job, "status"):
                job.status = "ASSIGNED"

            if hasattr(job, "assigned_at"):
                job.assigned_at = datetime.now(timezone.utc)

            logger.info(
                "JOB STATUS UPDATED | "
                "job=%s | status=%s | technician=%s",
                job_id,
                getattr(job, "status", None),
                getattr(
                    job,
                    "assigned_technician_id",
                    None,
                ),
            )

            # ----------------------------------------------------------
            # Notification
            # ----------------------------------------------------------

            self._create_assignment_notification(
                db=db,
                job=job,
                technician=technician,
            )

            # ----------------------------------------------------------
            # Flush
            # ----------------------------------------------------------

            try:
                db.flush()

                logger.info(
                    "DB FLUSH SUCCESS | "
                    "job=%s | status=%s | technician=%s",
                    job_id,
                    getattr(job, "status", None),
                    getattr(
                        job,
                        "assigned_technician_id",
                        None,
                    ),
                )

            except Exception:
                logger.exception(
                    "DB FLUSH FAILED | job=%s",
                    job_id,
                )
                raise

            # ----------------------------------------------------------
            # Commit
            # ----------------------------------------------------------

            try:
                db.commit()

                logger.info(
                    "DB COMMIT SUCCESS | job=%s",
                    job_id,
                )

            except Exception:
                logger.exception(
                    "DB COMMIT FAILED | job=%s",
                    job_id,
                )
                raise

            # ----------------------------------------------------------
            # Refresh
            # ----------------------------------------------------------

            try:
                db.refresh(job)

                logger.info(
                    "DB REFRESH RESULT | "
                    "job=%s | status=%s | technician=%s",
                    job_id,
                    getattr(job, "status", None),
                    getattr(
                        job,
                        "assigned_technician_id",
                        None,
                    ),
                )

            except Exception:
                logger.exception(
                    "DB REFRESH FAILED | job=%s",
                    job_id,
                )
                raise

            # ----------------------------------------------------------
            # Fresh DB verification
            # ----------------------------------------------------------

            fresh_job = self._get_job(db, job_id)

            if fresh_job is None:
                raise ValueError(
                    f"Job {job_id} disappeared after assignment"
                )

            logger.info(
                "FRESH DB QUERY | "
                "job=%s | status=%s | technician=%s",
                job_id,
                getattr(fresh_job, "status", None),
                getattr(
                    fresh_job,
                    "assigned_technician_id",
                    None,
                ),
            )

            if (
                getattr(
                    fresh_job,
                    "assigned_technician_id",
                    None,
                )
                != technician_id
            ):
                raise ValueError(
                    f"Assignment verification failed for job {job_id}"
                )

            if (
                str(
                    getattr(
                        fresh_job,
                        "status",
                        "",
                    )
                    or ""
                ).upper()
                != "ASSIGNED"
            ):
                raise ValueError(
                    f"Job {job_id} status verification failed"
                )

            logger.info(
                "ASSIGNMENT VERIFIED SUCCESSFULLY | "
                "job=%s | technician=%s",
                job_id,
                technician_id,
            )
            logger.info(
                "FINAL DISPATCH ASSIGNMENT | job_id=%s | "
                "assigned_technician_id=%s | status=%s",
                fresh_job.id,
                fresh_job.assigned_technician_id,
                fresh_job.status,
            )


            # ----------------------------------------------------------
            # Acceptance timer
            # ----------------------------------------------------------

            try:
                redis_client = get_redis_client()

                timer_started = TimerService.start_timer(
                    redis_client=redis_client,
                    job_id=str(job.id),
                    tech_id=str(technician.tech_id),
                    duration_seconds=(
                        TimerService.ACCEPTANCE_DURATION_SECONDS
                    ),
                )

                logger.info(
                    "ACCEPTANCE TIMER RESULT | "
                    "job=%s | technician=%s | started=%s",
                    job_id,
                    technician_id,
                    timer_started,
                )

            except Exception:
                logger.exception(
                    "ACCEPTANCE TIMER FAILED | "
                    "job=%s | technician=%s",
                    job_id,
                    technician_id,
                )

                # Timer failure does not undo the committed assignment.
                # The application needs another timeout mechanism if
                # timer creation fails.

        logger.info(
            "AUTOMATIC DISPATCH OFFER COMPLETE | "
            "job=%s | technician=%s",
            job_id,
            technician_id,
        )

    # ------------------------------------------------------------------
    # Notification
    # ------------------------------------------------------------------

    @staticmethod
    def _create_assignment_notification(
        *,
        db: Session,
        job: Any,
        technician: Any,
    ) -> None:
        """
        Create the JOB_ASSIGNED notification expected by
        the existing technician portal.
        """

        existing = (
            db.query(models.InAppNotification)
            .filter(
                models.InAppNotification.tech_id
                == technician.tech_id,
                models.InAppNotification.job_id
                == str(job.id),
                models.InAppNotification.type
                == "JOB_ASSIGNED",
                models.InAppNotification.status
                == "UNREAD",
            )
            .first()
        )

        if existing is not None:
            logger.info(
                "Existing unread assignment notification found "
                "job=%s technician=%s",
                job.id,
                technician.technician_id,
            )

            return

        notification = models.InAppNotification(
            id=str(uuid.uuid4()),
            tenant_id=technician.tenant_id,
            tech_id=technician.tech_id,
            job_id=str(job.id),
            type="JOB_ASSIGNED",
            title="New Job Assigned",
            body=(
                f"You have been assigned to Job #{job.id}: "
                f"{getattr(job, 'service_type', None) or 'Service Request'} "
                f"at "
                f"{getattr(job, 'location', None) or 'Customer location'}."
            ),
            status="UNREAD",
            priority=(
                getattr(job, "priority", None)
                or "HIGH"
            ),
            created_at=datetime.now(timezone.utc),
        )

        db.add(notification)

        logger.info(
            "ASSIGNMENT NOTIFICATION CREATED | "
            "job=%s | technician=%s",
            job.id,
            technician.technician_id,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_job(
        db: Session,
        job_id: int,
    ) -> Any | None:
        """Load the real Job model."""

        return (
            db.query(models.Job)
            .filter(
                models.Job.id == job_id
            )
            .first()
        )

    @staticmethod
    def _job_to_state(
        job: Any,
    ) -> dict[str, Any]:
        """
        Convert the SQLAlchemy Job object into the small dictionary
        required by DispatcherGraph.
        """

        return {
            "id": int(job.id),
            "tenant_id": getattr(
                job,
                "tenant_id",
                None,
            ),
            "service_type": getattr(
                job,
                "service_type",
                None,
            ),
            "location": getattr(
                job,
                "location",
                None,
            ),
            "priority": getattr(
                job,
                "priority",
                None,
            ),
            "status": getattr(
                job,
                "status",
                None,
            ),
            "assigned_technician_id": getattr(
                job,
                "assigned_technician_id",
                None,
            ),
        }

    @staticmethod
    def _job_is_already_dispatched(
        job: Any,
    ) -> bool:
        """
        Prevent accidental duplicate automatic dispatch.
        """

        assigned_technician_id = getattr(
            job,
            "assigned_technician_id",
            None,
        )

        status = str(
            getattr(
                job,
                "status",
                "",
            )
            or ""
        ).upper()

        terminal_or_active_statuses = {
            "ASSIGNED",
            "ACCEPTED",
            "EN_ROUTE",
            "ON_SITE",
            "IN_PROGRESS",
            "ACTIVE",
            "COMPLETED",
            "CLOSED",
            "CANCELLED",
        }

        if assigned_technician_id is not None:
            return True

        return status in terminal_or_active_statuses
    


# ---------------------------------------------------------------------------
# Singleton runtime
# ---------------------------------------------------------------------------

_dispatcher_runtime: DispatcherRuntime | None = None


def get_dispatcher_runtime() -> DispatcherRuntime:
    """
    Return the process-wide DispatcherRuntime.

    The same graph instance must be used for start/resume because
    the LangGraph checkpointer belongs to that graph instance.
    """

    global _dispatcher_runtime

    if _dispatcher_runtime is None:
        _dispatcher_runtime = DispatcherRuntime()

    return _dispatcher_runtime


# ---------------------------------------------------------------------------
# Automatic dispatch entry point
# ---------------------------------------------------------------------------

async def start_automatic_dispatch(
    job_id: int,
    initial_candidates: list[dict[str, Any]] | None = None,
) -> None:
    """
    Start automatic Dispatcher after the job has been committed.

    initial_candidates should contain the COMPLETE ranked list.

    If only the top three are passed, the Dispatcher cannot try
    ranks 4 onward from the original planning result.
    """

    try:
        logger.info(
            "🚀 AUTOMATIC DISPATCH START | "
            "job_id=%s | initial_candidates=%s",
            job_id,
            initial_candidates,
        )

        runtime = get_dispatcher_runtime()

        result = await runtime.start_dispatch(
            job_id,
            initial_candidates=initial_candidates,
        )

        logger.info(
            "🚀 AUTOMATIC DISPATCH FINISHED | "
            "job_id=%s | result=%s",
            job_id,
            result,
        )

    except Exception:
        logger.exception(
            "❌ AUTOMATIC DISPATCH FAILED | "
            "job_id=%s",
            job_id,
        )

