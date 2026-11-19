
"""
dispatcher_runtime.py

Runtime integration for the FieldOps Dispatcher Agent.

Responsibilities:
- Load real jobs from the database.
- Preserve the complete ranked technician pool.
- Preserve the complete ranked eligible technician pool.
- Broadcast an offer to every eligible technician concurrently.
- Let the database atomically select the first accepting technician.
- Wait for every offer to become terminal before replanning.

Important:
- This file does NOT use the manual assignment endpoint.
- Broadcast offer coordination is persisted in Job.dispatch_state.
- Database/service layer owns operational side effects.
"""

from __future__ import annotations

import asyncio
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

from app.services.force_assignment_service import (
    try_force_assign_job,
)



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


class WorkloadLimitReached(RuntimeError):
    """Candidate is intentionally excluded because stored workload is at limit."""



# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------

def log_planning_top3(job_id, ranked, excluded=None):
    excluded = excluded or set()
    batch = ranked
    batch_number = 1 if not excluded else 2
    remaining_after = 0

    print("=" * 50)
    print(f"PLANNING BATCH {batch_number}" if batch_number == 1 else f"REPLANNING BATCH {batch_number}")
    print("=" * 14)
    print(f"Job ID: {job_id}")
    print(f"Eligible technicians in broadcast: {len(batch)}")
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

    @staticmethod
    def _candidate_identity(candidate: dict[str, Any]) -> tuple[str, int] | None:
        """Return a tenant-scoped technician identity."""
        if not isinstance(candidate, dict):
            return None
        tenant_id = candidate.get("tenant_id") or candidate.get("organization_id")
        technician_id = candidate.get("technician_id")
        if tenant_id is None or technician_id is None:
            return None
        try:
            return str(tenant_id), int(technician_id)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _identity_payload(identity: tuple[str, int]) -> dict[str, Any]:
        return {"tenant_id": identity[0], "technician_id": identity[1]}

    @classmethod
    def _identity_set(cls, values: list[Any] | None) -> set[tuple[str, int]]:
        result: set[tuple[str, int]] = set()
        for value in values or []:
            if isinstance(value, dict):
                identity = cls._candidate_identity(value)
                if identity is not None:
                    result.add(identity)
        return result

    @staticmethod
    def _pending_offer_identities(job_id: int) -> set[tuple[str, int]]:
        """Read persisted PENDING offers; DB state wins over delivery errors."""
        with SessionLocal() as db:
            rows = (
                db.query(models.JobAssignment.tenant_id, models.JobAssignment.technician_id)
                .filter(
                    models.JobAssignment.job_id == int(job_id),
                    models.JobAssignment.status == "PENDING",
                    models.JobAssignment.assigned_at.isnot(None),
                )
                .all()
            )
        return {
            (str(tenant_id), int(technician_id))
            for tenant_id, technician_id in rows
            if tenant_id is not None and technician_id is not None
        }

    async def start_dispatch(
        self,
        job_id: int,
        initial_candidates: list[dict[str, Any]] | None = None,
        dispatch_attempt_id: str | None = None,
    ) -> dict[str, Any]:
        """Broadcast to every eligible technician returned by Planning."""
        dispatch_attempt_id = dispatch_attempt_id or str(uuid.uuid4())

        with SessionLocal() as db:
            job = self._get_job(db, job_id)
            if job is None:
                raise ValueError(f"Job {job_id} not found")
            if self._job_is_already_dispatched(job):
                return {
                    "job_id": job_id,
                    "status": "ALREADY_DISPATCHED",
                    "assigned_technician_id": getattr(job, "assigned_technician_id", None),
                }
            status = str(getattr(job, "status", "") or "").strip().upper()
            if status not in OFFERABLE_JOB_STATUSES:
                return {"job_id": job_id, "status": "NOT_UNASSIGNED", "candidates": []}
            job_state = self._job_to_state(job)
            previous = getattr(job, "dispatch_state", None) or {}
            # JobAssignment is authoritative for who has already received an
            # offer. A technician ID is only unique inside its organization.
            attempted_identities = {
                (str(row.tenant_id), int(row.technician_id))
                for row in db.query(models.JobAssignment).filter(
                    models.JobAssignment.job_id == job_id,
                    models.JobAssignment.assigned_at.isnot(None),
                ).all()
                if row.tenant_id is not None and row.technician_id is not None
            }
            attempted_identities.update(self._identity_set(previous.get("attempted_technicians")))
            workload_excluded_identities = self._identity_set(
                previous.get("workload_excluded_technicians")
            )
            excluded_identities = attempted_identities | workload_excluded_identities
            if previous.get("dispatch_attempt_id"):
                dispatch_attempt_id = str(previous["dispatch_attempt_id"])

        candidates = (
            self._normalize_candidates(initial_candidates, excluded_identities=excluded_identities)
            if initial_candidates is not None
            else await self.request_planning(
                job_id,
                [self._identity_payload(item) for item in sorted(excluded_identities)],
            )
        )
        if not candidates:
            # Keep the previous ranked pool: Planning may now return no new
            # technicians, but previously offered technicians remain eligible
            # for the force-assignment fallback unless they explicitly rejected.
            previous_candidates = list(previous.get("all_candidates") or [])
            previous_rejected = list(previous.get("rejected_technicians") or [])

            exhausted = {
                "job_id": job_id,
                "dispatch_attempt_id": dispatch_attempt_id,
                "all_candidates": previous_candidates,
                "attempted_technicians": [
                    self._identity_payload(item) for item in sorted(attempted_identities)
                ],
                "workload_excluded_technicians": [
                    self._identity_payload(item) for item in sorted(workload_excluded_identities)
                ],
                "rejected_technicians": previous_rejected,
                "offers_broadcast": True,
                "dispatch_exhausted": True,
                "next_action": "FORCE_ASSIGNMENT",
            }

            force_result = await self._try_force_assignment(job_id, exhausted)
            if force_result is not None:
                return force_result

            exhausted["next_action"] = "DISPATCH_EXHAUSTED"
            changed = self._mark_dispatch_exhausted(job_id, exhausted)
            return {
                "job_id": job_id,
                "status": "DISPATCH_EXHAUSTED" if changed else "NOT_RETRYABLE",
                "candidates": [],
                "dispatch_exhausted": changed,
            }

        # Retain the complete candidate history across planning batches.
        # Tenant-scoped identity is used so equal numeric IDs in different
        # organizations are not collapsed.
        candidate_history: dict[tuple[str, int], dict[str, Any]] = {}
        for old_candidate in list(previous.get("all_candidates") or []) + list(candidates):
            identity = self._candidate_identity(old_candidate)
            if identity is not None:
                candidate_history[identity] = old_candidate

        state = {
            "job_id": job_id,
            "dispatch_attempt_id": dispatch_attempt_id,
            "job": job_state,
            "all_candidates": list(candidate_history.values()),
            "candidates": candidates,
            "attempted_technicians": [
                self._identity_payload(item) for item in sorted(attempted_identities)
            ],
            "workload_excluded_technicians": [
                self._identity_payload(item) for item in sorted(workload_excluded_identities)
            ],
            "rejected_technicians": list(previous.get("rejected_technicians") or []),
            "offers_broadcast": True,
            "current_technician_id": None,
            "current_batch_technicians": [],
            "next_action": "CREATING_OFFERS",
        }
        prepared = dict(job_state)
        prepared["dispatch_attempt_id"] = dispatch_attempt_id
        prepared["_dispatch_state"] = DispatcherGraph._persistable_state(state)

        # Do not limit this list: every eligible candidate is offered concurrently.
        outcomes = await asyncio.gather(
            *(
                self.offer_job(
                    {**prepared, "_candidate": candidate, "_candidate_rank": candidate.get("rank")},
                    int(candidate["technician_id"]),
                )
                for candidate in candidates
            ),
            return_exceptions=True,
        )
        # A notification/timer can fail after the PENDING offer has committed.
        # Treat the persisted database row as the source of truth so this
        # candidate is not misclassified as an uncreated offer.
        pending_identities = self._pending_offer_identities(job_id)
        successful = [
            candidate for candidate, outcome in zip(candidates, outcomes)
            if (
                not isinstance(outcome, Exception)
                or self._candidate_identity(candidate) in pending_identities
            )
        ]
        workload_skipped = [
            candidate for candidate, outcome in zip(candidates, outcomes)
            if isinstance(outcome, WorkloadLimitReached)
        ]
        failed = [
            {
                "tenant_id": candidate.get("tenant_id") or candidate.get("organization_id"),
                "technician_id": candidate.get("technician_id"),
                "error": str(outcome),
            }
            for candidate, outcome in zip(candidates, outcomes)
            if isinstance(outcome, Exception) and not isinstance(outcome, WorkloadLimitReached)
        ]
        workload_excluded_identities.update(
            identity
            for identity in (self._candidate_identity(candidate) for candidate in workload_skipped)
            if identity is not None
        )
        state["workload_excluded_technicians"] = [
            self._identity_payload(item)
            for item in sorted(workload_excluded_identities)
        ]
        state["current_batch_technicians"] = [
            self._identity_payload(identity)
            for identity in (self._candidate_identity(c) for c in successful)
            if identity is not None
        ]
        state["failed_offer_attempts"] = failed
        state["workload_skipped_count"] = len(workload_skipped)
        state["next_action"] = "WAITING_FOR_ALL_OFFERS" if successful else "REPLAN_AFTER_WORKLOAD_FILTER" if workload_skipped and not failed else "NO_OFFERS_CREATED"
        state["status"] = "OFFERS_BROADCAST" if successful else "NO_ELIGIBLE_TECHNICIANS" if workload_skipped and not failed else "OFFER_CREATION_FAILED"
        self._persist_dispatch_state(job_id, state)

        logger.info(
            "broadcast_complete job_id=%s eligible=%s offers_created=%s offers_failed=%s",
            job_id, len(candidates), len(successful), len(failed),
        )
        if not successful:
            # Defensive second check: a post-commit exception may have left a
            # PENDING offer even if its candidate could not be matched above.
            pending_identities = self._pending_offer_identities(job_id)
            if pending_identities:
                state["current_batch_technicians"] = [
                    self._identity_payload(identity)
                    for identity in sorted(pending_identities)
                ]
                state["next_action"] = "WAIT_FOR_ALL_OFFERS_TERMINAL"
                state["status"] = "OFFERS_BROADCAST"
                state["pending_offer_count"] = len(pending_identities)
                self._persist_dispatch_state(job_id, state)
                logger.warning(
                    "dispatch_waiting_for_persisted_offers job_id=%s pending=%s",
                    job_id, len(pending_identities),
                )
                return state

            # A workload-excluded technician was never offered. Ask Planning for
            # the next eligible pool instead of treating that candidate as a
            # rejected/timed-out offer. Tenant-scoped identities avoid excluding
            # another organization's technician with the same numeric ID.
            if workload_skipped and not failed:
                next_candidates = await self.request_planning(
                    job_id,
                    [
                        self._identity_payload(item)
                        for item in sorted(attempted_identities | workload_excluded_identities)
                    ],
                )
                if next_candidates:
                    return await self.start_dispatch(
                        job_id,
                        initial_candidates=next_candidates,
                        dispatch_attempt_id=dispatch_attempt_id,
                    )

            # No offer was persisted and no additional Planning candidates
            # were found. Re-check/attempt force assignment before cancellation.
            state["dispatch_exhausted"] = True
            state["next_action"] = "FORCE_ASSIGNMENT"

            force_result = await self._try_force_assignment(job_id, state)
            if force_result is not None:
                return force_result

            state["next_action"] = "DISPATCH_EXHAUSTED"
            with SessionLocal() as db:
                fresh = self._get_job(db, job_id)
                if fresh and getattr(fresh, "assigned_technician_id", None) is None:
                    self._mark_dispatch_exhausted(job_id, state)
        return state

    async def resume_dispatch(
        self,
        *,
        job_id: int,
        event: str,
        technician_id: int | None = None,
        technician_tenant_id: str | None = None,
    ) -> dict[str, Any]:
        """Serialize broadcast coordination so simultaneous responses cannot advance twice."""
        from app.services.distributed_lock_service import with_job_lock

        with with_job_lock(str(job_id)):
            return await self._resume_dispatch_locked(
                job_id=job_id,
                event=event,
                technician_id=technician_id,
                technician_tenant_id=technician_tenant_id,
            )

    async def _resume_dispatch_locked(
        self,
        *,
        job_id: int,
        event: str,
        technician_id: int | None = None,
        technician_tenant_id: str | None = None,
    ) -> dict[str, Any]:
        """Coordinate broadcast responses while holding the job-scoped lock."""
        allowed = {"TECHNICIAN_ACCEPTED", "TECHNICIAN_REJECTED", "TECHNICIAN_TIMEOUT"}
        if event not in allowed:
            raise ValueError(f"Unsupported dispatcher event: {event}")

        with SessionLocal() as db:
            job = self._get_job(db, job_id)
            if job is None:
                return {"job_id": job_id, "status": "JOB_NOT_FOUND"}
            persisted = dict(getattr(job, "dispatch_state", None) or {})
            assigned_id = getattr(job, "assigned_technician_id", None)
            job_status = str(getattr(job, "status", "") or "").upper()

            if assigned_id is not None or job_status in NON_DISPATCHABLE_STATUSES:
                persisted.update({"status": "ASSIGNED", "assigned_technician_id": assigned_id, "next_action": "END"})
                db.commit()
                return persisted

            if technician_id is not None:
                tenant_id = technician_tenant_id
                if tenant_id is None:
                    matching_tenants = (
                        db.query(models.JobAssignment.tenant_id)
                        .filter(
                            models.JobAssignment.job_id == job_id,
                            models.JobAssignment.technician_id == int(technician_id),
                            models.JobAssignment.assigned_at.isnot(None),
                        )
                        .distinct()
                        .all()
                    )
                    if len(matching_tenants) == 1:
                        tenant_id = matching_tenants[0][0]

                if tenant_id is not None:
                    identity = (str(tenant_id), int(technician_id))
                    attempted = self._identity_set(persisted.get("attempted_technicians"))
                    attempted.add(identity)
                    persisted["attempted_technicians"] = [
                        self._identity_payload(item) for item in sorted(attempted)
                    ]
                    if event == "TECHNICIAN_REJECTED":
                        rejected = self._identity_set(persisted.get("rejected_technicians"))
                        rejected.add(identity)
                        persisted["rejected_technicians"] = [
                            self._identity_payload(item) for item in sorted(rejected)
                        ]
                    job.dispatch_state = DispatcherGraph._persistable_state(persisted)
                    db.flush()
                else:
                    logger.warning(
                        "dispatch_event_identity_ambiguous job_id=%s technician_id=%s",
                        job_id, technician_id,
                    )

            # The Job row is locked first, matching acceptance/rejection/timeout lock order.
            pending_count = (
                db.query(models.JobAssignment)
                .filter(
                    models.JobAssignment.job_id == job_id,
                    models.JobAssignment.status == "PENDING",
                    models.JobAssignment.assigned_at.isnot(None),
                )
                .count()
            )
            db.commit()

        if pending_count:
            persisted.update({
                "status": "WAITING_FOR_OTHER_OFFERS",
                "pending_offer_count": pending_count,
                "next_action": "WAIT_FOR_ALL_OFFERS_TERMINAL",
            })
            self._persist_dispatch_state(job_id, persisted)
            return persisted

        # All offers in this broadcast are terminal. Ask Planning for a fresh
        # ranking excluding every technician already offered this job.
        attempted_identities = persisted.get("attempted_technicians", [])
        workload_excluded = persisted.get("workload_excluded_technicians", [])
        fresh_candidates = await self.request_planning(
            job_id,
            list(attempted_identities) + list(workload_excluded),
        )
        if not fresh_candidates:
            # Every offer in the current broadcast is terminal and Planning
            # has no new candidates. Try the previously ranked/attempted pool
            # using fresh GPS and appointment checks before cancelling.
            persisted.update({
                "dispatch_exhausted": True,
                "next_action": "FORCE_ASSIGNMENT",
            })

            force_result = await self._try_force_assignment(
                job_id,
                persisted,
            )
            if force_result is not None:
                return force_result

            persisted["next_action"] = "DISPATCH_EXHAUSTED"
            changed = self._mark_dispatch_exhausted(job_id, persisted)
            persisted["status"] = (
                "DISPATCH_EXHAUSTED" if changed else "NOT_RETRYABLE"
            )
            return persisted

        # Start the next complete eligible pool. Keep the same dispatch attempt.
        result = await self.start_dispatch(
            job_id,
            initial_candidates=fresh_candidates,
            dispatch_attempt_id=persisted.get("dispatch_attempt_id"),
        )
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
                if hasattr(db, "commit"):
                    db.commit()


    async def _try_force_assignment(
        self,
        job_id: int,
        dispatch_state: dict[str, Any],
    ) -> dict[str, Any] | None:
        """
        Try direct assignment after normal broadcast offers are exhausted.

        Returns updated dispatch state on success.
        Returns None when no candidate qualifies.
        """

        try:
            result = await asyncio.to_thread(
                try_force_assign_job,
                job_id=job_id,
                dispatch_state=dispatch_state,
            )
        except Exception:
            logger.exception(
                "force_assignment_failed job_id=%s",
                job_id,
            )
            return None

        if not result.get("assigned"):
            logger.warning(
                "force_assignment_unavailable job_id=%s reason=%s",
                job_id,
                result.get("reason"),
            )
            return None

        state = result["dispatch_state"]

        # The Communication Agent publishes assignment and acceptance
        # notifications after the status transaction commits. Broadcast the
        # persisted customer chat message here, matching normal acceptance.
        chat_message = result.get("chat_message")
        chat_customer_user_id = result.get("chat_customer_user_id")
        if chat_message and chat_customer_user_id:
            try:
                from app.services.socket_manager import sio

                await sio.emit(
                    "job_message",
                    {
                        "job_id": job_id,
                        "message": chat_message,
                    },
                    room=f"user_{chat_customer_user_id}",
                )
            except Exception:
                logger.exception(
                    "force_assignment_chat_broadcast_failed "
                    "job_id=%s customer_user_id=%s",
                    job_id,
                    chat_customer_user_id,
                )

        logger.warning(
            "dispatcher_force_assignment_completed job_id=%s "
            "technician_id=%s technician_tenant_id=%s",
            job_id,
            result["technician_id"],
            result["technician_tenant_id"],
        )

        return state


    # ------------------------------------------------------------------
    # Planning adapter
    # ------------------------------------------------------------------

    
    async def request_planning(
        self,
        job_id: int,
        excluded_technician_ids: list[Any],
    ) -> list[dict[str, Any]]:
        """
        Request a fresh deterministic Planning Graph ranking.

        Previously attempted technicians are excluded.
        Returns the complete fresh ranking; DispatcherGraph selects
        the next batch of at most three candidates.
        """

        excluded_identities = self._identity_set(excluded_technician_ids)

        logger.info(
            "PLANNING GRAPH REQUEST | job_id=%s | excluded_tenant_technicians=%s",
            job_id,
            [self._identity_payload(item) for item in sorted(excluded_identities)],
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
                "preferred_visit_time": getattr(
                    job, "preferred_service_time", None
                ),
            }

            # Copy primitive job fields above, then release the SQLAlchemy
            # session before running the synchronous LangGraph invocation.
            planning_input = {
                "job_id": job_id,
                "job_requirement": job_requirement,
                # Planning's current exclusion input is numeric-only. Do
                # not pass IDs here: that would exclude another tenant's
                # technician if numeric IDs overlap. Filter below instead.
                "excluded_technician_ids": [],
            }

        result = await asyncio.to_thread(planning_graph.invoke, planning_input)
        ranked_all = result.get("all_ranked_technicians") or []
        log_planning_top3(job_id, ranked_all, excluded_identities)

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
            excluded_identities=excluded_identities,
        )

        logger.info(
            "PLANNING GRAPH RESULT | job_id=%s | "
            "candidate_count=%s | excluded_tenant_technicians=%s | candidates=%s",
            job_id,
            len(candidates),
            [self._identity_payload(item) for item in sorted(excluded_identities)],
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
        excluded_identities: set[tuple[str, int]],
    ) -> list[dict[str, Any]]:
        """
        Normalize candidate dictionaries and remove tenant-scoped duplicates.

        Candidate order is preserved by rank.
        """

        normalized: list[dict[str, Any]] = []
        seen_identities: set[tuple[str, int]] = set()

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
                        "tenant_id": getattr(candidate, "tenant_id", None),
                        "organization_id": getattr(candidate, "organization_id", None),
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

            tenant_id = candidate.get("tenant_id") or candidate.get("organization_id")
            if tenant_id is None:
                logger.warning(
                    "Skipping planning candidate without tenant/organization identity: %r",
                    candidate,
                )
                continue
            identity = (str(tenant_id), technician_id)
            if identity in excluded_identities:
                continue

            if identity in seen_identities:
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

            seen_identities.add(identity)

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

        Create one technician-scoped PENDING offer. This does not assign the Job.
        The acceptance service atomically selects the first winner.
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

            if getattr(job, "assigned_technician_id", None) is not None:
                raise RuntimeError("job_already_assigned")
            current_status = str(getattr(job, "status", "") or "").strip().upper()
            if current_status not in OFFERABLE_JOB_STATUSES:
                raise RuntimeError(f"job_not_dispatchable:{getattr(job, 'status', None)}")

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

            candidate = job_state.get("_candidate") or {}
            candidate_tenant_id = candidate.get("organization_id") or candidate.get("tenant_id")
            technician_query = db.query(models.Technician).filter(
                models.Technician.technician_id == technician_id,
            )
            if candidate_tenant_id is not None:
                technician_query = technician_query.filter(
                    models.Technician.tenant_id == str(candidate_tenant_id)
                )
            technician = technician_query.with_for_update().first()

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

            # The technician row is locked above. Use the persisted workload
            # column as the dispatch source of truth. This is deliberately the
            # same value administrators can inspect/update in technicians.current_jobs.
            technician_tenant_id = str(technician.tenant_id)
            active_workload = max(0, int(getattr(technician, "current_jobs", 0) or 0))
            if active_workload >= 5:
                logger.info(
                    "dispatch_candidate_skipped job_id=%s technician_id=%s "
                    "tenant_id=%s active_workload=%s limit=5 reason=workload_limit",
                    job_id,
                    technician.technician_id,
                    technician_tenant_id,
                    active_workload,
                )
                raise WorkloadLimitReached(
                    f"technician_workload_limit_reached:{active_workload}/5"
                )

            logger.info(
                "dispatch_candidate_eligible job_id=%s technician_id=%s "
                "tenant_id=%s active_workload=%s limit=5",
                job_id,
                technician.technician_id,
                technician_tenant_id,
                active_workload,
            )

            # Persist an active offer without reserving the job. PostgreSQL
            # selects the winner later in accept_broadcast_offer.
            offer = (
                db.query(models.JobAssignment)
                .filter(
                    models.JobAssignment.job_id == job_id,
                    models.JobAssignment.technician_id == technician.technician_id,
                    models.JobAssignment.tenant_id == technician.tenant_id,
                    models.JobAssignment.status == "PENDING",
                    models.JobAssignment.assigned_at.isnot(None),
                )
                .first()
            )
            if offer is None:
                db.add(models.JobAssignment(
                    job_id=job_id,
                    tenant_id=str(technician.tenant_id),
                    technician_id=technician.technician_id,
                    rank=int(job_state.get("_candidate_rank") or candidate.get("rank") or 1),
                    status="PENDING",
                    assigned_at=datetime.now(timezone.utc),
                    is_current=True,
                ))

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
                    status="OFFERED",
                    dispatch_attempt_id=job_state.get("dispatch_attempt_id"),
                )

                print(
                    f"PLANNING ASSIGNMENT | Job ID: {job_id} | "
                    f"Technician: {technician.technician_name or 'Unknown'} "
                    f"(ID: {technician.technician_id}) | Status: OFFERED",
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

            # Timer and push delivery are post-commit side effects. Their
            # failure must not make gather() believe the DB offer was not made.
            try:
                redis_client = get_redis_client()
                if redis_client is not None:
                    TimerService.start_timer(
                        redis_client,
                        str(job_id),
                        str(technician.technician_id),
                    )
                else:
                    logger.error(
                        "offer_timer_not_started job_id=%s technician_id=%s reason=redis_unavailable",
                        job_id, technician_id,
                    )
            except Exception:
                logger.exception(
                    "offer_timer_start_failed_after_commit job_id=%s technician_id=%s",
                    job_id, technician_id,
                )

            try:
                from app.services.assignment_push import send_assignment_push

                await send_assignment_push(
                    job_id=job.id,
                    tenant_id=str(technician.tenant_id),
                    technician_id=str(technician.tech_id),
                    job_title=getattr(job, "service_type", None),
                    location=getattr(job, "location", None),
                )
            except Exception:
                logger.exception(
                    "offer_push_failed_after_commit job_id=%s technician_id=%s",
                    job_id, technician_id,
                )

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

            logger.info(
                "offer_created job_id=%s technician_id=%s dispatch_attempt_id=%s notification_id=%s outcome=persisted",
                job_id,
                technician_id,
                job_state.get("dispatch_attempt_id"),
                getattr(notification, "id", None),
            )

            logger.info(
                "BROADCAST OFFER PERSISTED | job_id=%s | "
                "technician_id=%s | job_status=%s",
                fresh_job.id,
                fresh_job.assigned_technician_id,
                fresh_job.status,
            )


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
        Create the active job offer notification expected by
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
            type="JOB_OFFERED",
            title="New Job Offer",
            body=(
                f"A service request is available: Job #{job.id}: "
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
        if not hasattr(db, "query"):
            return None

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
        """Persist the final cancelled status after every ranked offer fails or times out."""
        with SessionLocal() as db:
            job = cls._get_job(db, job_id)
            if job is None:
                return False
            status = str(getattr(job, "status", "") or "").strip().upper()
            if status in NON_DISPATCHABLE_STATUSES and status not in {
                "REJECTED_BY_TECHNICIAN", "CANCELLED", "QUEUED"
            }:
                return False
            if getattr(job, "assigned_technician_id", None) is not None:
                return False

            # Database state is authoritative. A post-commit timer/push/socket
            # failure must never cause a persisted pending offer to be treated
            # as if offer creation failed.
            pending_offer_exists = (
                db.query(models.JobAssignment.id)
                .filter(
                    models.JobAssignment.job_id == job_id,
                    models.JobAssignment.status == "PENDING",
                    models.JobAssignment.assigned_at.isnot(None),
                )
                .first()
                is not None
            )
            if pending_offer_exists:
                logger.info(
                    "dispatch_exhaustion_deferred job_id=%s reason=pending_offers_exist",
                    job_id,
                )
                return False

            job.status = "CANCELLED"
            job.cancellation_reason = "All ranked eligible technicians exhausted / timed out / rejected offer"
            job.cancelled_at = datetime.now(timezone.utc)
            job.assigned_technician_id = None
            job.dispatch_state = DispatcherGraph._persistable_state(dispatch_state)

            try:
                from app.models_legacy import ServiceRequest
                sr = db.query(ServiceRequest).filter(ServiceRequest.linked_job_id == job.id).first()
                if sr:
                    sr.status = "CANCELLED"
            except Exception as sr_err:
                logger.warning("Failed to set linked ServiceRequest to CANCELLED: %s", sr_err)

            db.commit()
            logger.info(
                "dispatch_exhausted job_id=%s status=CANCELLED attempted_technician_ids=%s",
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

