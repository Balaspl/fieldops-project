
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
import json
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

from app.services.timer_service import TimerService
from app.services.planning_output_log import write_planning_output


logger = logging.getLogger(__name__)

DISPATCHABLE_UNASSIGNED_STATUSES = frozenset({
    "CREATED", "QUEUED", "UNASSIGNED",
})
OFFERABLE_JOB_STATUSES = DISPATCHABLE_UNASSIGNED_STATUSES | {
    "REJECTED_BY_TECHNICIAN",
}
NON_DISPATCHABLE_STATUSES = frozenset({
    "ASSIGNED", "ACCEPTED", "EN_ROUTE", "ON_SITE", "IN_PROGRESS",
    "COMPLETED", "CLOSED", "CANCELLED", "CANCELED",
})


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
        print(f"Technician ID: {t.get('technician_id')}")
        print(f"Organization ID: {t.get('organization_id')}")
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
        dispatch_attempt_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Start automatic dispatch for a real job.

        Use the already-ranked Planning result when the caller has one. The
        scheduled recovery path may omit it, in which case Planning is queried
        once at dispatch time. Dispatcher does not re-evaluate eligibility.
        """

        dispatch_attempt_id = dispatch_attempt_id or str(uuid.uuid4())

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

            current_status = str(getattr(job, "status", "") or "").strip().upper()
            if current_status not in DISPATCHABLE_UNASSIGNED_STATUSES:
                logger.info(
                    "dispatch_skipped job_id=%s status=%s outcome=not_unassigned",
                    job_id,
                    current_status or "unknown",
                )
                return {"job_id": job_id, "status": "NOT_UNASSIGNED", "candidates": []}

            job_state = self._job_to_state(job)
            job_state["dispatch_attempt_id"] = dispatch_attempt_id
            previous_dispatch_state = getattr(job, "dispatch_state", None) or {}
            attempted_ids = [
                int(value)
                for value in previous_dispatch_state.get("attempted_technician_ids", [])
                if str(value).isdigit()
            ]
            if previous_dispatch_state.get("dispatch_attempt_id"):
                dispatch_attempt_id = str(previous_dispatch_state["dispatch_attempt_id"])
                job_state["dispatch_attempt_id"] = dispatch_attempt_id

        logger.info(
            "dispatcher_started job_id=%s technician_id=none dispatch_attempt_id=%s outcome=started candidate_source=%s",
            job_id,
            dispatch_attempt_id,
            "planning_handoff" if initial_candidates is not None else "planning_refresh",
        )

        if initial_candidates is not None:
            all_candidates = self._normalize_candidates(
                initial_candidates,
                excluded_ids=set(attempted_ids),
            )
        else:
            logger.info("DISPATCHER REQUESTING INITIAL PLANNING | job_id=%s", job_id)
            all_candidates = await self.request_planning(job_id, attempted_ids)

        if all_candidates:
            for candidate in all_candidates:
                logger.info(
                    "candidates_received job_id=%s technician_id=%s dispatch_attempt_id=%s rank=%s outcome=eligible_from_planning",
                    job_id,
                    candidate["technician_id"],
                    dispatch_attempt_id,
                    candidate.get("rank"),
                )
        else:
            logger.info(
                "candidates_received job_id=%s technician_id=none dispatch_attempt_id=%s outcome=empty",
                job_id,
                dispatch_attempt_id,
            )

        write_planning_output(
            "DISPATCHER_CANDIDATES_RECEIVED",
            job_id=job_id,
            dispatch_attempt_id=dispatch_attempt_id,
            candidate_count=len(all_candidates),
            candidates=[
                {
                    "rank": candidate.get("rank"),
                    "technician_id": candidate.get("technician_id"),
                    "technician_name": candidate.get("technician_name"),
                    "organization_id": candidate.get("organization_id"),
                }
                for candidate in all_candidates
            ],
        )

        if not all_candidates:
            write_planning_output(
                "DISPATCH_PENDING_NO_CANDIDATES",
                job_id=job_id,
                dispatch_attempt_id=dispatch_attempt_id,
                attempted_technician_ids=attempted_ids,
            )
            print(
                f"PLANNING ASSIGNMENT | Job ID: {job_id} | "
                "Technician: none | Status: pending_no_candidates",
                flush=True,
            )
            exhausted_state = {
                "job_id": job_id,
                "dispatch_attempt_id": dispatch_attempt_id,
                "all_candidates": [],
                "candidates": [],
                "batch_number": int(previous_dispatch_state.get("batch_number", 0)) + 1,
                "current_index": 0,
                "current_technician_id": None,
                "attempted_technician_ids": attempted_ids,
                "rejected_technician_ids": previous_dispatch_state.get("rejected_technician_ids", []),
                "batch_exhausted": True,
                "offer_status": None,
                "last_offer_outcome": "NO_CANDIDATES",
                "dispatch_exhausted": True,
                "pending_retry": False,
                "next_action": "DISPATCH_EXHAUSTED",
            }
            rejected = self._mark_dispatch_exhausted(job_id, exhausted_state)
            logger.warning(
                "dispatch_exhausted_no_candidates job_id=%s technician_id=none dispatch_attempt_id=%s status=%s",
                job_id,
                dispatch_attempt_id,
                "REJECTED_BY_TECHNICIAN" if rejected else "UNCHANGED",
            )

            return {
                "job_id": job_id,
                "status": "REJECTED_BY_TECHNICIAN" if rejected else "NOT_RETRYABLE",
                "candidates": [],
                "dispatch_exhausted": rejected,
            }

        # Preserve the complete pool separately from the active batch.
        state: DispatcherState = {
            "job_id": job_id,
            "dispatch_attempt_id": dispatch_attempt_id,
            "job": job_state,
            "all_candidates": all_candidates,
            "candidates": all_candidates,
            "batch_number": int(previous_dispatch_state.get("batch_number", 0)) + 1,
            "current_index": 0,
            "current_technician_id": None,
            "attempted_technician_ids": attempted_ids,
            "rejected_technician_ids": previous_dispatch_state.get("rejected_technician_ids", []),
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
                for candidate in all_candidates
            ],
        )

        result = await self.graph.start_dispatch(state)
        self._persist_dispatch_state(job_id, result)
        if result.get("error"):
            logger.error(
                "dispatch_failed job_id=%s technician_id=%s dispatch_attempt_id=%s outcome=failed reason=%s",
                job_id,
                result.get("current_technician_id"),
                dispatch_attempt_id,
                result.get("error"),
            )
        return result

    async def resume_dispatch(
        self,
        *,
        job_id: int,
        event: str,
        technician_id: int | None = None,
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
        with SessionLocal() as db:
            job = self._get_job(db, job_id)
            persisted = getattr(job, "dispatch_state", None) if job else None
        if isinstance(persisted, dict) and persisted:
            current_id = persisted.get("current_technician_id")
            if technician_id is not None and current_id != int(technician_id):
                logger.info(
                    "Ignoring stale/duplicate dispatcher response job_id=%s technician_id=%s current_technician_id=%s outcome=ignored",
                    job_id, technician_id, current_id,
                )
                return persisted
            result = await self.graph.resume_from_persisted_state(persisted, event)
        else:
            result = await self.graph.resume_dispatch(job_id=job_id, event=event)
        self._persist_dispatch_state(job_id, result)
        if result.get("dispatch_exhausted"):
            self._mark_dispatch_exhausted(job_id, result)
        if result.get("pending_retry"):
            self._mark_pending_for_dispatch_retry(job_id, result)
        return result

    def _persist_dispatch_state(self, job_id: int, state: dict[str, Any]) -> None:
        """Commit JSON-safe dispatch progress so worker restarts can recover."""
        if not state:
            return

        payload = DispatcherGraph._persistable_state(state)

        with SessionLocal() as db:
            job = self._get_job(db, job_id)

            if job is not None:
                job.dispatch_state = payload
                db.commit()

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
                candidate_data = technician
            else:
                model_dump = getattr(technician, "model_dump", None)
                if callable(model_dump):
                    candidate_data = model_dump()
                else:
                    candidate_data = vars(technician) if hasattr(technician, "__dict__") else {}

            technician_id = candidate_data.get("technician_id")

            if technician_id is None:
                logger.warning(
                    "Skipping planning result without technician_id: %r",
                    technician,
                )
                continue

            raw_candidates.append(
                {
                    **candidate_data,
                    "technician_id": technician_id,
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
            [
                {
                    "rank": candidate.get("rank"),
                    "technician_name": candidate.get("technician_name") or "Unknown",
                    "technician_id": candidate["technician_id"],
                }
                for candidate in candidates
            ],
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

        job_id = self._job_id_from_offer_state(job_state)

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

            # Reject duplicate assignment before checking job status.
            if getattr(job, "assigned_technician_id", None) is not None:
                raise RuntimeError("job_already_assigned")

            current_status = str(getattr(job, "status", "") or "").strip().upper()
            if current_status not in OFFERABLE_JOB_STATUSES:
                raise RuntimeError(
                    f"job_not_dispatchable:{getattr(job, 'status', None)}"
                )

            dispatch_state = job_state.get("_dispatch_state")
            if isinstance(dispatch_state, dict):
                job.dispatch_state = dispatch_state

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
                .with_for_update()
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
                raise RuntimeError(
                    f"Planning returned unknown technician {technician_id} "
                    f"for job {job_id}"
                )

            if str(getattr(technician, "tenant_id", None)) != str(getattr(job, "tenant_id", None)):
                raise RuntimeError("planning_candidate_tenant_mismatch")

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

            notification = self._create_assignment_notification(
                db=db,
                job=job,
                technician=technician,
                dispatch_attempt_id=str(job_state.get("dispatch_attempt_id") or ""),
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

                write_planning_output(
                    "PLANNING_ASSIGNMENT_COMMITTED",
                    job_id=job_id,
                    technician_id=technician.technician_id,
                    technician_name=technician.technician_name,
                    status="ASSIGNED",
                    dispatch_attempt_id=job_state.get("dispatch_attempt_id"),
                )

                print(
                    f"PLANNING ASSIGNMENT | Job ID: {job_id} | "
                    f"Technician: {technician.technician_name or 'Unknown'} "
                    f"(ID: {technician.technician_id}) | Status: ASSIGNED",
                    flush=True,
                )

                logger.info(
                    "OFFER DB COMMIT SUCCESS | job_id=%s technician_id=%s",
                    job_id,
                    technician_id,
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
                if notification is not None:
                    db.refresh(notification)

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
                "offer_created job_id=%s technician_id=%s dispatch_attempt_id=%s notification_id=%s outcome=persisted",
                job_id,
                technician_id,
                job_state.get("dispatch_attempt_id"),
                getattr(notification, "id", None),
            )

            logger.info(
                "offer_assignment_reservation_verified job_id=%s "
                "technician_id=%s status=%s",
                job_id,
                technician_id,
                getattr(fresh_job, "status", None),
            )
            logger.info(
                "OFFER RESERVATION PERSISTED | job_id=%s | "
                "technician_id=%s | status=%s",
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

        if notification is not None:
            try:
                from app.services.socket_manager import emit_notification

                sent = await emit_notification(
                    str(technician.tech_id or technician.technician_id),
                    {
                        "id": notification.id,
                        "type": notification.type,
                        "title": notification.title,
                        "message": notification.body,
                        "jobId": notification.job_id,
                        "createdAt": notification.created_at.isoformat(),
                        "status": notification.status,
                        "tenant_id": str(notification.tenant_id),
                        "notification_metadata": notification.notification_metadata,
                    },
                )
                if sent:
                    logger.info(
                        "offer_sent job_id=%s technician_id=%s dispatch_attempt_id=%s channel=socket_notification outcome=sent",
                        job_id,
                        technician_id,
                        job_state.get("dispatch_attempt_id"),
                    )
                else:
                    logger.error(
                        "dispatch_failed job_id=%s technician_id=%s dispatch_attempt_id=%s phase=notification_delivery outcome=failed",
                        job_id,
                        technician_id,
                        job_state.get("dispatch_attempt_id"),
                    )
            except Exception:
                logger.exception(
                    "dispatch_failed job_id=%s technician_id=%s dispatch_attempt_id=%s phase=notification_delivery outcome=failed",
                    job_id,
                    technician_id,
                    job_state.get("dispatch_attempt_id"),
                )

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
    def _job_id_from_offer_state(job_state: dict[str, Any]) -> int:
        """Validate legacy Job-shaped and current graph-shaped offer payloads."""
        if not isinstance(job_state, dict):
            raise ValueError(f"Offer state must be a mapping, got {type(job_state).__name__}")
        raw_id = job_state.get("id")
        raw_job_id = job_state.get("job_id")
        try:
            normalized = int(raw_id if raw_id is not None else raw_job_id)
            if raw_id is not None and raw_job_id is not None and int(raw_job_id) != normalized:
                raise ValueError("id and job_id disagree")
        except (TypeError, ValueError) as exc:
            logger.error(
                "Dispatcher offer rejected: missing/invalid job identifier keys=%s reason=%s",
                sorted(job_state.keys()), str(exc),
            )
            raise ValueError(
                f"Offer state requires a consistent id/job_id; available keys={sorted(job_state.keys())}"
            ) from exc
        return normalized

    @staticmethod
    def _create_assignment_notification(
        *,
        db: Session,
        job: Any,
        technician: Any,
        dispatch_attempt_id: str = "",
    ) -> Any | None:
        """
        Create the JOB_ASSIGNED notification expected by
        the existing technician portal.
        """

        # Notifications belong to the recipient technician's organization,
        # not necessarily the organization that owns the job. A job may be
        # dispatched across organizations, but notification reads remain
        # tenant-scoped in the technician portal.
        technician_tenant_id = getattr(technician, "tenant_id", None)
        technician_recipient_id = str(
            getattr(technician, "tech_id", None)
            or getattr(technician, "technician_id", "")
        )

        if not technician_tenant_id:
            raise ValueError(
                "Cannot create assignment notification: technician has no tenant_id"
            )

        # Use the same tenant-aware recipient/group identity as the
        # Communication Agent. Check read and unread cards so that a read
        # notification does not cause a duplicate-key error on reassignment.
        assignment_group_key = f"job_{job.id}"

        existing = (
            db.query(models.InAppNotification)
            .filter(
                models.InAppNotification.tenant_id == technician_tenant_id,
                models.InAppNotification.recipient_role == "technician",
                models.InAppNotification.recipient_id == technician_recipient_id,
                models.InAppNotification.group_key == assignment_group_key,
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

            return None

        notification = models.InAppNotification(
            id=str(uuid.uuid4()),
            # IMPORTANT: tenant_id is the recipient's organization. The job's
            # tenant_id may be different for a cross-organization assignment.
            tenant_id=technician_tenant_id,
            tech_id=technician.tech_id,
            recipient_role="technician",
            recipient_id=technician_recipient_id,
            group_key=assignment_group_key,
            notification_metadata={"dispatch_attempt_id": dispatch_attempt_id},
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
        return notification

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
            .with_for_update()
            .first()
        )

    @classmethod
    def _mark_pending_for_dispatch_retry(cls, job_id: int, dispatch_state: dict[str, Any] | None = None) -> bool:
        """Persist an unassigned, nonterminal job in the recovery queue."""
        with SessionLocal() as db:
            job = cls._get_job(db, job_id)
            if job is None:
                return False
            status = str(getattr(job, "status", "") or "").strip().upper()
            if status not in DISPATCHABLE_UNASSIGNED_STATUSES:
                return False
            if getattr(job, "assigned_technician_id", None) is not None:
                return False
            job.status = "QUEUED"
            if dispatch_state is not None:
                job.dispatch_state = DispatcherGraph._persistable_state(dispatch_state)
            db.commit()
            return True

    @classmethod
    def _mark_dispatch_exhausted(cls, job_id: int, dispatch_state: dict[str, Any]) -> bool:
        """Persist the final rejected status after every planned offer fails."""
        with SessionLocal() as db:
            job = cls._get_job(db, job_id)
            if job is None:
                return False
            status = str(getattr(job, "status", "") or "").strip().upper()
            if status in NON_DISPATCHABLE_STATUSES and status not in {
                "REJECTED_BY_TECHNICIAN"
            }:
                return False
            if getattr(job, "assigned_technician_id", None) is not None:
                return False
            job.status = "REJECTED_BY_TECHNICIAN"
            job.assigned_technician_id = None
            job.dispatch_state = DispatcherGraph._persistable_state(dispatch_state)
            db.commit()
            logger.info(
                "dispatch_exhausted job_id=%s status=REJECTED_BY_TECHNICIAN attempted_technician_ids=%s",
                job_id,
                dispatch_state.get("attempted_technician_ids", []),
            )
            return True

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

        if assigned_technician_id is not None:
            return True

        return status in NON_DISPATCHABLE_STATUSES
    


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

    dispatch_attempt_id = str(uuid.uuid4())
    try:
        logger.info(
            "🚀 AUTOMATIC DISPATCH START | "
            "job_id=%s | initial_candidates=%s",
            job_id,
            initial_candidates,
        )

        runtime = get_dispatcher_runtime()
        from app.services.distributed_lock_service import with_job_lock

        with with_job_lock(str(job_id)):
            result = await runtime.start_dispatch(
                job_id,
                initial_candidates=initial_candidates,
                dispatch_attempt_id=dispatch_attempt_id,
            )

        logger.info(
            "🚀 AUTOMATIC DISPATCH FINISHED | "
            "job_id=%s | result=%s",
            job_id,
            result,
        )
        if result.get("status") == "SCHEDULED":
            from app.worker import register_scheduled_dispatch

            register_scheduled_dispatch(job_id, dispatch_attempt_id)

    except Exception:
        logger.exception(
            "dispatch_failed job_id=%s technician_id=none dispatch_attempt_id=%s phase=dispatcher_start outcome=failed",
            job_id,
            dispatch_attempt_id,
        )

