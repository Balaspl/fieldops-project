"""
dispatcher_agent.py

Dispatcher Agent for FieldOps Commander AI.

Responsibilities:
- Sequentially offer a job to technicians.
- Wait for technician ACCEPT / REJECT / TIMEOUT.
- Stop immediately when a technician accepts.
- Track every attempted technician.
- Request a fresh Planning batch after the current Top-3 is exhausted.
- Keep operational side effects outside LangGraph.
- Use LangGraph only for orchestration and state progression.

IMPORTANT:
- Dispatcher candidates may belong to different organizations/tenants.
- The Dispatcher does NOT filter candidates by tenant.
- Tenant/organization-specific operational data is handled by the
  backend runtime when the actual offer is created.
"""

from __future__ import annotations

import inspect
import json
import logging
from typing import Any, Awaitable, Callable, cast

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from typing_extensions import TypedDict


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

TechnicianEvent = str

TECHNICIAN_ACCEPTED = "TECHNICIAN_ACCEPTED"
TECHNICIAN_REJECTED = "TECHNICIAN_REJECTED"
TECHNICIAN_TIMEOUT = "TECHNICIAN_TIMEOUT"

ALLOWED_EVENTS = {
    TECHNICIAN_ACCEPTED,
    TECHNICIAN_REJECTED,
    TECHNICIAN_TIMEOUT,
}


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class DispatcherState(TypedDict, total=False):
    """
    State owned by the Dispatcher LangGraph.

    The graph stores orchestration state only.

    Backend operational state such as:
    - Job status
    - assigned technician
    - notifications
    - timers
    - technician workload

    remains owned by DispatcherRuntime / backend services.
    """

    job_id: int

    job: dict[str, Any]

    # Stable identity for recovering a dispatch after process restart.
    dispatch_attempt_id: str

    # The full ranked list from Planning, retained separately from the active
    # batch so runtime handoff and recovery preserve the original ranking.
    all_candidates: list[dict[str, Any]]

    # Current Planning batch.
    candidates: list[dict[str, Any]]

    # Planning batch number.
    batch_number: int

    # Position inside current candidate batch.
    current_index: int

    # Technician currently being offered the job.
    current_technician_id: int | None

    # Retry and outcome state retained across LangGraph transitions.
    batch_exhausted: bool
    offer_status: str | None
    last_offer_outcome: str | None
    pending_retry: bool
    dispatch_exhausted: bool

    # Every technician that has been attempted.
    #
    # Both REJECT and TIMEOUT are recorded here.
    attempted_technician_ids: list[int]

    # Technicians rejected or timed out.
    rejected_technician_ids: list[int]

    # Event received from technician/backend.
    event: TechnicianEvent | None

    # Operational instruction returned by graph.
    next_action: str | None

    # Technician that accepted.
    assigned_technician_id: int | None

    # Planning flags.
    planning_required: bool
    replanning_required: bool

    # Error information.
    error: str | None


# ---------------------------------------------------------------------------
# Dispatcher Graph
# ---------------------------------------------------------------------------

def print_batch(job_id, batch_number, candidates, attempted):
    label = "PLANNING BATCH 1" if batch_number == 1 else f"REPLANNING BATCH {batch_number}"
    print("\n" + "=" * 50, flush=True)
    print(label, flush=True)
    print("=" * 14, flush=True)
    print(f"Job ID: {job_id}", flush=True)
    print(f"Technicians in this batch: {len(candidates)}", flush=True)
    print(f"Already attempted: {sorted(attempted)}", flush=True)
    print(flush=True)

    for i, t in enumerate(candidates, start=1):
        print(f"Rank {i}:", flush=True)
        print(f"Technician ID: {t.get('technician_id')}", flush=True)
        print(f"Organization ID: {t.get('organization_id')}", flush=True)
        print(f"Organization Distance: {t.get('organization_distance')} km", flush=True)
        print(f"Technician Distance: {t.get('technician_distance')} km", flush=True)
        print(f"Confidence: {t.get('confidence')}", flush=True)
        print(f"Estimated ETA: {t.get('estimated_eta')} mins", flush=True)
        print(f"Workload: {t.get('workload')}", flush=True)
        print(flush=True)

    if not candidates:
        print("No eligible technicians remain.\n", flush=True)

    print("=" * 50 + "\n", flush=True)
class DispatcherGraph:
    """
    LangGraph orchestration for automatic technician dispatch.

    Flow:

        START
          |
          v
      validate_input
          |
          v
      select_candidate
          |
          v
        offer_job
          |
          v
    wait_for_response
       /    |     \
      /     |      \
 ACCEPT  REJECT  TIMEOUT
   |       |        |
   v       v        v
accepted rejected timeout
   |       |        |
   |       +----+---+
   |            |
   |            v
   |      check_candidates
   |         /       \
   |        /         \
   |   candidate    no candidate
   |      |             |
   |      v             v
   | select_candidate request_replanning
   |                    |
   |                    v
   |              fresh Planning batch
   |                    |
   |             +------+------+
   |             |             |
   |        candidates      no candidates
   |             |             |
   |             v             v
   |       select_candidate   END
   |
   v
  END

    IMPORTANT:
    Candidates may belong to different organizations/tenants.

    Example:

        Rank 1 -> tenant A
        Rank 2 -> tenant B
        Rank 3 -> tenant B

    This graph intentionally does not perform tenant filtering.
    """

    def __init__(
        self,
        *,
        offer_job: Callable[[dict[str, Any], int], Any],
        request_planning: Callable[[int, list[int]], Any],
        checkpointer: Any | None = None,
    ) -> None:
        self.offer_job = offer_job
        self.request_planning = request_planning

        self.checkpointer = checkpointer or MemorySaver()

        self.graph = self._build_graph()

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    async def _maybe_await(self, value: Any) -> Any:
        """
        Support both async and sync callbacks.
        """
        if inspect.isawaitable(value):
            return await cast(Awaitable[Any], value)

        return value

    @staticmethod
    def _unique_ints(values: list[Any]) -> list[int]:
        """
        Convert values to integers and remove duplicates while
        preserving order.
        """
        result: list[int] = []
        seen: set[int] = set()

        for value in values:
            try:
                technician_id = int(value)
            except (TypeError, ValueError):
                continue

            if technician_id not in seen:
                seen.add(technician_id)
                result.append(technician_id)

        return result

    @staticmethod
    def _candidate_technician_id(
        candidate: dict[str, Any],
    ) -> int | None:
        """
        Extract technician_id from a Planning candidate.
        """
        value = candidate.get("technician_id")

        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _persistable_state(state: DispatcherState) -> dict[str, Any]:
        """Return JSON-safe orchestration state for durable recovery."""
        keys = (
            "job_id", "dispatch_attempt_id", "all_candidates", "candidates",
            "batch_number", "current_index", "current_technician_id",
            "attempted_technician_ids", "rejected_technician_ids", "event",
            "next_action", "assigned_technician_id", "planning_required",
            "replanning_required", "batch_exhausted", "offer_status",
            "last_offer_outcome", "pending_retry", "dispatch_exhausted", "error",
        )
        payload = {key: state[key] for key in keys if key in state}
        return json.loads(json.dumps(payload, default=str))

    async def resume_from_persisted_state(
        self, state: DispatcherState, event: str
    ) -> DispatcherState:
        """Recover a paused dispatch without depending on process memory."""
        if event not in ALLOWED_EVENTS:
            raise ValueError(f"Unsupported dispatcher event: {event!r}")
        current_id = state.get("current_technician_id")
        attempted = self._unique_ints(state.get("attempted_technician_ids") or [])
        if current_id is None or int(current_id) in attempted:
            # Duplicate delivery: return the current durable state unchanged.
            return state
        state = dict(state)
        state["event"] = event
        handler = {
            TECHNICIAN_ACCEPTED: self.handle_accepted,
            TECHNICIAN_REJECTED: self.handle_rejected,
            TECHNICIAN_TIMEOUT: self.handle_timeout,
        }[event]
        state.update(await handler(state))
        if event == TECHNICIAN_ACCEPTED:
            state.update({"pending_retry": False, "batch_exhausted": False})
            return state
        state.update(await self.check_candidates(state))
        if state.get("next_action") == "SELECT_CANDIDATE":
            state.update(await self.select_candidate(state))
            state.update(await self.offer_job_node(state))
            return state
        state.update(await self.request_replanning_node(state))
        if state.get("candidates"):
            state.update(await self.select_candidate(state))
            state.update(await self.offer_job_node(state))
        return state

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def _build_graph(self):
        builder = StateGraph(DispatcherState)

        # Nodes
        builder.add_node(
            "validate_input",
            self.validate_input,
        )

        builder.add_node(
            "select_candidate",
            self.select_candidate,
        )

        builder.add_node(
            "offer_job",
            self.offer_job_node,
        )

        builder.add_node(
            "wait_for_response",
            self.wait_for_response,
        )

        builder.add_node(
            "handle_accepted",
            self.handle_accepted,
        )

        builder.add_node(
            "handle_rejected",
            self.handle_rejected,
        )

        builder.add_node(
            "handle_timeout",
            self.handle_timeout,
        )

        builder.add_node(
            "check_candidates",
            self.check_candidates,
        )

        builder.add_node(
            "request_replanning",
            self.request_replanning_node,
        )

        # START -> validation
        builder.add_edge(
            START,
            "validate_input",
        )

        # Validation -> candidate selection or replanning.
        builder.add_conditional_edges(
            "validate_input",
            self.route_after_validation,
            {
                "select_candidate": "select_candidate",
                "request_replanning": "request_replanning",
                "end": END,
            },
        )

        # Candidate selection -> offer or replanning.
        builder.add_conditional_edges(
            "select_candidate",
            self.route_selection,
            {
                "offer_job": "offer_job",
                "request_replanning": "request_replanning",
                "end": END,
            },
        )

        # Offer -> wait, or skip a candidate rejected by runtime validation.
        builder.add_conditional_edges(
            "offer_job",
            self.route_after_offer,
            {"wait_for_response": "wait_for_response", "check_candidates": "check_candidates", "end": END},
        )

        # Wait -> event handler.
        builder.add_conditional_edges(
            "wait_for_response",
            self.route_event,
            {
                "handle_accepted": "handle_accepted",
                "handle_rejected": "handle_rejected",
                "handle_timeout": "handle_timeout",
                "end": END,
            },
        )

        # Accepted -> END.
        builder.add_edge(
            "handle_accepted",
            END,
        )

        # Rejected / timeout -> candidate check.
        builder.add_edge(
            "handle_rejected",
            "check_candidates",
        )

        builder.add_edge(
            "handle_timeout",
            "check_candidates",
        )

        # Candidate check -> next candidate or replanning.
        builder.add_conditional_edges(
            "check_candidates",
            self.route_after_candidate_check,
            {
                "select_candidate": "select_candidate",
                "request_replanning": "request_replanning",
                "end": END,
            },
        )

        # Replanning -> either candidate selection or END.
        builder.add_conditional_edges(
            "request_replanning",
            self.route_after_replanning,
            {
                "select_candidate": "select_candidate",
                "end": END,
            },
        )

        return builder.compile(
            checkpointer=self.checkpointer,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start_dispatch(
        self,
        state: DispatcherState,
    ) -> Any:
        """
        Start a new dispatch graph.
        """
        job_id = state.get("job_id")

        if job_id is None:
            raise ValueError("job_id is required")

        config = self._thread_config(job_id)

        logger.info(
            "Starting dispatcher graph for job_id=%s",
            job_id,
        )

        return await self.graph.ainvoke(
            state,
            config=config,
        )

    async def resume_dispatch(
        self,
        *,
        job_id: int,
        event: str,
    ) -> Any:
        """
        Resume an interrupted dispatch graph.
        """
        if event not in ALLOWED_EVENTS:
            raise ValueError(
                f"Unsupported dispatcher event: {event!r}. "
                f"Expected one of: {sorted(ALLOWED_EVENTS)}"
            )

        config = self._thread_config(job_id)

        logger.info(
            "Resuming dispatcher graph: job_id=%s event=%s",
            job_id,
            event,
        )

        return await self.graph.ainvoke(
            Command(resume=event),
            config=config,
        )

    @staticmethod
    def _thread_config(
        job_id: int,
    ) -> dict[str, Any]:
        """
        Return persistent LangGraph thread configuration.

        The same thread ID MUST be used for:
        start -> interrupt -> resume.
        """
        return {
            "configurable": {
                "thread_id": f"dispatcher-job-{job_id}",
            }
        }

    # ------------------------------------------------------------------
    # Nodes
    # ------------------------------------------------------------------

   
    async def validate_input(
        self,
        state: DispatcherState,
    ) -> dict[str, Any]:
        """
        Validate initial dispatcher state while preserving
        the complete ranked technician pool.
        """
        job_id = state.get("job_id")

        if job_id is None:
            return {
                "error": "job_id is required",
                "next_action": "END",
            }

        # Prefer the full ranked pool; fall back to candidates
        # for backward compatibility.
        all_candidates = (
            state.get("all_candidates")
            or state.get("candidates")
            or []
        )

        attempted = self._unique_ints(
            state.get("attempted_technician_ids") or []
        )

        rejected = self._unique_ints(
            state.get("rejected_technician_ids") or []
        )

        attempted_set = set(attempted)
        seen_ids: set[int] = set()
        filtered_candidates: list[dict[str, Any]] = []

        for candidate in all_candidates:
            if not isinstance(candidate, dict):
                continue

            try:
                technician_id = int(candidate["technician_id"])
            except (KeyError, TypeError, ValueError):
                continue

            if (
                technician_id in attempted_set
                or technician_id in seen_ids
            ):
                continue

            filtered_candidates.append({
                **candidate,
                "technician_id": technician_id,
            })
            seen_ids.add(technician_id)

        # A Planning response is one dispatch batch. Keep the full ranked
        # response active until every candidate reaches a terminal outcome.
        candidates = filtered_candidates

        updates: dict[str, Any] = {
            "job_id": int(job_id),
            "all_candidates": filtered_candidates,
            "candidates": candidates,
            "attempted_technician_ids": attempted,
            "rejected_technician_ids": rejected,
            "batch_number": int(state.get("batch_number") or 1),
            "current_index": int(state.get("current_index") or 0),
            "current_technician_id": state.get(
                "current_technician_id"
            ),
            "event": None,
            "assigned_technician_id": state.get(
                "assigned_technician_id"
            ),
            "planning_required": False,
            "replanning_required": False,
            "batch_exhausted": False,
            "offer_status": state.get("offer_status"),
            "last_offer_outcome": state.get("last_offer_outcome"),
            "pending_retry": bool(state.get("pending_retry", False)),
            "error": state.get("error"),
        }

        if not candidates:
            updates["planning_required"] = True
            updates["replanning_required"] = True
            updates["next_action"] = "REQUEST_PLANNING"

            logger.info(
                "No unattempted candidates supplied for job_id=%s; "
                "planning required",
                job_id,
            )

        logger.info(
            "DISPATCH_VALIDATE_INPUT | job_id=%s | "
            "candidate_count=%s | top_3_ids=%s | "
            "planning_required=%s",
            job_id,
            len(candidates),
            [
                (
                    self._candidate_technician_id(c),
                    c.get("rank"),
                )
                for c in candidates
            ],
            updates.get("planning_required", False),
        )

        return updates


    async def select_candidate(
        self,
        state: DispatcherState,
    ) -> dict[str, Any]:
        """
        Select the next valid technician from the current batch.

        IMPORTANT:
        No tenant/organization filtering is performed here.

        A candidate from another organization is valid if Planning
        returned that candidate.

        A technician already attempted in an earlier batch is skipped.
        """

        logger.warning(
            "DISPATCH SELECT | job_id=%s "
            "current_index=%s "
            "attempted=%s "
            "candidates=%s",
            state.get("job_id"),
            state.get("current_index"),
            state.get("attempted_technician_ids"),
            state.get("candidates"),
        )

        candidates = state.get("candidates") or []

        attempted = set(
            self._unique_ints(
                state.get("attempted_technician_ids") or []
            )
        )

        index = int(
            state.get("current_index") or 0
        )

        while index < len(candidates):
            candidate = candidates[index]

            technician_id = self._candidate_technician_id(
                candidate
            )

            if technician_id is None:
                logger.warning(
                    "Skipping invalid dispatcher candidate "
                    "for job_id=%s: %r",
                    state.get("job_id"),
                    candidate,
                )

                index += 1
                continue

            if technician_id in attempted:
                logger.info(
                    "Skipping already attempted technician "
                    "technician_id=%s job_id=%s",
                    technician_id,
                    state.get("job_id"),
                )

                index += 1
                continue

            logger.info(
                "Selected technician_id=%s for job_id=%s "
                "(candidate_index=%s batch=%s)",
                technician_id,
                state.get("job_id"),
                index,
                state.get("batch_number", 1),
            )

            return {
                "current_index": index,
                "current_technician_id": technician_id,
                "next_action": "OFFER_JOB",
                "replanning_required": False,
            "batch_exhausted": False,
            "pending_retry": False,
            }

        logger.info(
            "Current candidate batch exhausted for job_id=%s",
            state.get("job_id"),
        )

        return {
            "current_index": index,
            "current_technician_id": None,
            "planning_required": True,
            "replanning_required": True,
            "batch_exhausted": True,
            "next_action": "REQUEST_PLANNING",
        }

    async def offer_job_node(
        self,
        state: DispatcherState,
    ) -> dict[str, Any]:
        """
        Ask the backend runtime to make the real job offer.

        Tenant/organization matching is intentionally NOT performed
        by the graph.

        The runtime receives the selected technician ID and is
        responsible for resolving the technician and creating the
        correct tenant-specific notification.
        """

        technician_id = state.get(
            "current_technician_id"
        )

        logger.warning(
            "DISPATCH OFFER | job_id=%s "
            "technician_id=%s "
            "current_index=%s",
            state.get("job_id"),
            technician_id,
            state.get("current_index"),
        )

        if technician_id is None:
            return {
                "error": "No current technician selected",
                "next_action": "END",
            }

        job = dict(state.get("job") or {})
        state_job_id = state.get("job_id")
        nested_job_id = job.get("id", job.get("job_id"))
        if state_job_id is None:
            logger.error(
                "Dispatcher cannot offer without canonical job_id; state_keys=%s",
                sorted(state.keys()),
            )
            return {"error": "Missing job_id in Dispatcher state", "next_action": "END"}
        try:
            normalized_job_id = int(state_job_id)
            if nested_job_id is not None and int(nested_job_id) != normalized_job_id:
                raise ValueError("job_id mismatch between job and Dispatcher state")
        except (TypeError, ValueError) as exc:
            logger.error(
                "Invalid Dispatcher job identifier; state_keys=%s job_keys=%s reason=%s",
                sorted(state.keys()), sorted(job.keys()), str(exc),
            )
            return {"error": f"Invalid Dispatcher job identifier: {exc}", "next_action": "END"}

        # Graph state has one canonical key (job_id); runtime callbacks and
        # legacy callers consume the Job-shaped `id` field. Normalize here.
        job["id"] = normalized_job_id
        job["job_id"] = normalized_job_id
        job["_dispatch_state"] = self._persistable_state(state)

        try:
            await self._maybe_await(
                self.offer_job(
                    job,
                    technician_id,
                )
            )

        except Exception as exc:
            logger.exception(
                "dispatch_failed job_id=%s technician_id=%s dispatch_attempt_id=%s phase=offer_creation outcome=failed",
                state.get("job_id"), technician_id, state.get("dispatch_attempt_id"),
            )
            return {
                "error": f"Failed to offer job to technician {technician_id}: {exc}",
                "next_action": "END",
            }

        logger.info(
            "Job offer successfully created "
            "job_id=%s technician_id=%s",
            state.get("job_id"),
            technician_id,
        )

        return {
            "next_action": "WAIT_FOR_RESPONSE",
            "offer_status": "OFFERED",
            "last_offer_outcome": None,
            "batch_exhausted": False,
            "pending_retry": False,
        }

    @staticmethod
    def route_after_offer(state: DispatcherState) -> str:
        if state.get("error"):
            return "end"
        if state.get("current_technician_id") is None:
            return "check_candidates"
        return "wait_for_response"

    async def wait_for_response(
        self,
        state: DispatcherState,
    ) -> dict[str, Any]:
        """
        Pause graph until an external technician event arrives.
        """

        technician_id = state.get(
            "current_technician_id"
        )

        job_id = state.get("job_id")

        response = interrupt(
            {
                "type": "TECHNICIAN_JOB_RESPONSE",
                "job_id": job_id,
                "technician_id": technician_id,
                "allowed_events": sorted(ALLOWED_EVENTS),
                "message": "Waiting for technician response.",
            }
        )

        if response not in ALLOWED_EVENTS:
            raise ValueError(
                f"Invalid dispatcher resume event: {response!r}"
            )

        logger.info(
            "technician_response job_id=%s technician_id=%s dispatch_attempt_id=%s event=%s outcome=received",
            job_id,
            technician_id,
            state.get("dispatch_attempt_id"),
            response,
        )

        return {
            "event": response,
            "next_action": response,
        }

    async def handle_accepted(
        self,
        state: DispatcherState,
    ) -> dict[str, Any]:
        """
        Handle technician acceptance.
        """

        technician_id = state.get(
            "current_technician_id"
        )

        attempted = self._unique_ints(
            state.get("attempted_technician_ids") or []
        )
        if (
            technician_id is not None
            and technician_id not in attempted
        ):
            attempted.append(technician_id)

        logger.info(
            "technician_accepted job_id=%s technician_id=%s dispatch_attempt_id=%s outcome=accepted",
            state.get("job_id"),
            technician_id,
            state.get("dispatch_attempt_id"),
        )

        return {
            "attempted_technician_ids": attempted,
            "assigned_technician_id": technician_id,
            "next_action": "COMPLETE_ASSIGNMENT",
            "planning_required": False,
            "replanning_required": False,
            "error": None,
        }

    async def handle_rejected(
        self,
        state: DispatcherState,
    ) -> dict[str, Any]:
        """
        Handle technician rejection.

        The rejected technician is permanently excluded from the
        current dispatch workflow.
        """

        technician_id = state.get(
            "current_technician_id"
        )

        attempted = self._unique_ints(
            state.get("attempted_technician_ids") or []
        )

        rejected = self._unique_ints(
            state.get("rejected_technician_ids") or []
        )

        if technician_id is not None:

            if technician_id not in attempted:
                attempted.append(technician_id)

            if technician_id not in rejected:
                rejected.append(technician_id)

        next_index = (
            int(
                state.get("current_index") or 0
            )
            + 1
        )

        candidates = state.get("candidates") or []
        attempted_before = list(
            self._unique_ints(
                state.get("attempted_technician_ids") or []
            )
        )
        remaining_in_batch = max(
            0,
            len(candidates) - (int(state.get("current_index") or 0) + 1),
        )

        logger.info(
            "technician_rejected job_id=%s technician_id=%s dispatch_attempt_id=%s attempted_before=%s remaining_in_batch=%s outcome=next_candidate",
            state.get("job_id"),
            technician_id,
            state.get("dispatch_attempt_id"),
            attempted_before,
            remaining_in_batch,
        )

        logger.warning(
            "DISPATCH REJECTED | job_id=%s "
            "rejected_technician_id=%s "
            "next_index=%s "
            "attempted=%s "
            "rejected=%s "
            "candidates=%s",
            state.get("job_id"),
            technician_id,
            next_index,
            attempted,
            rejected,
            state.get("candidates"),
        )

        return {
            "attempted_technician_ids": attempted,
            "rejected_technician_ids": rejected,
            "current_index": next_index,
            "current_technician_id": None,
            "event": None,
            "next_action": "CHECK_CANDIDATES",
        }

    async def handle_timeout(
        self,
        state: DispatcherState,
    ) -> dict[str, Any]:
        """
        Handle technician timeout.

        Timeout is treated as an attempted technician.
        """

        technician_id = state.get(
            "current_technician_id"
        )

        attempted = self._unique_ints(
            state.get("attempted_technician_ids") or []
        )

        rejected = self._unique_ints(
            state.get("rejected_technician_ids") or []
        )

        if technician_id is not None:

            if technician_id not in attempted:
                attempted.append(technician_id)

            if technician_id not in rejected:
                rejected.append(technician_id)

        next_index = (
            int(
                state.get("current_index") or 0
            )
            + 1
        )

        candidates_in_batch = state.get("candidates") or []
        attempted_before_timeout = list(
            self._unique_ints(
                state.get("attempted_technician_ids") or []
            )
        )
        remaining_after_timeout = max(
            0,
            len(candidates_in_batch) - (int(state.get("current_index") or 0) + 1),
        )

        logger.info(
            "offer_timed_out job_id=%s technician_id=%s dispatch_attempt_id=%s attempted_before=%s remaining_in_batch=%s outcome=next_candidate",
            state.get("job_id"),
            technician_id,
            state.get("dispatch_attempt_id"),
            attempted_before_timeout,
            remaining_after_timeout,
        )

        logger.warning(
            "DISPATCH TIMEOUT | job_id=%s "
            "technician_id=%s "
            "next_index=%s "
            "attempted=%s",
            state.get("job_id"),
            technician_id,
            next_index,
            attempted,
        )

        return {
            "attempted_technician_ids": attempted,
            "rejected_technician_ids": rejected,
            "current_index": next_index,
            "current_technician_id": None,
            "event": None,
            "next_action": "CHECK_CANDIDATES",
        }

   
    
    async def check_candidates(
        self,
        state: DispatcherState,
    ) -> dict[str, Any]:
        """Continue the current batch before moving to the next batch."""
    
        attempted = set(
            self._unique_ints(
                state.get("attempted_technician_ids") or []
            )
        )
    
        candidates = state.get("candidates") or []
        current_index = int(state.get("current_index") or 0)
        batch_number = int(state.get("batch_number") or 1)
    
        # FIRST: Check the remaining candidates in the current batch.
        remaining_current_batch = [
            candidate
            for candidate in candidates[current_index:]
            if self._candidate_technician_id(candidate) is not None
            and self._candidate_technician_id(candidate) not in attempted
        ]
    
        if remaining_current_batch:
            logger.info(
                "CURRENT_BATCH_CONTINUES | job_id=%s | batch=%s | "
                "remaining_ids=%s",
                state.get("job_id"),
                batch_number,
                [
                    self._candidate_technician_id(candidate)
                    for candidate in remaining_current_batch
                ],
            )
    
            return {
                "current_technician_id": None,
                "planning_required": False,
                "replanning_required": False,
                "next_action": "SELECT_CANDIDATE",
                "error": None,
            }
    
        # Current Planning batch exhausted — fresh Planning required.
        logger.info(
            "BATCH_EXHAUSTED_REPLANNING_REQUIRED | job_id=%s | "
            "batch=%s | exhausted_ids=%s | attempted_count=%s | "
            "original_batch_fully_offered=True",
            state.get("job_id"),
            batch_number,
            sorted(attempted),
            len(attempted),
        )

        return {
            "candidates": [],
            "current_index": 0,
            "current_technician_id": None,
            "planning_required": True,
            "replanning_required": True,
            "batch_exhausted": True,
            "next_action": "REQUEST_REPLANNING",
            "error": None,
        }


    async def request_replanning_node(
        self,
        state: DispatcherState,
    ) -> dict[str, Any]:
        job_id = state.get("job_id")
        

        if job_id is None:
            return {
                "error": "job_id is required for replanning",
                "next_action": "END",
                "planning_required": False,
                "replanning_required": False,
            }

        attempted = self._unique_ints(
            state.get("attempted_technician_ids") or []
        )
        planning_exclusions = attempted

        batch_number = int(state.get("batch_number") or 1)
        next_batch_number = batch_number + 1

        logger.info(
            "REQUEST_REPLANNING | job_id=%s | next_batch=%s | "
            "prev_batch=%s | excluded_technicians=%s | "
            "excluded_count=%s | prev_batch_exhausted=True",
            job_id,
            next_batch_number,
            batch_number,
            planning_exclusions,
            len(planning_exclusions),
        )

        # Call the Planning integration.
        try:
            planning_result = await self._maybe_await(
                self.request_planning(
                    int(job_id),
                    planning_exclusions,
                )
            )
        except ValueError as exc:
            logger.warning(
                "PLANNING_NO_ELIGIBLE_TECHNICIANS | job_id=%s | "
                "batch=%s | reason=%s",
                job_id,
                next_batch_number,
                str(exc),
            )

            return {
                "candidates": [],
                "batch_number": next_batch_number,
                "current_index": 0,
                "current_technician_id": None,
                "planning_required": False,
                "replanning_required": False,
                "next_action": "NO_ELIGIBLE_TECHNICIAN",
                "error": str(exc),
            }

        except Exception as exc:
            logger.exception(
                "PLANNING_REQUEST_FAILED | job_id=%s | batch=%s",
                job_id,
                next_batch_number,
            )

            return {
                "candidates": [],
                "batch_number": next_batch_number,
                "current_index": 0,
                "current_technician_id": None,
                "planning_required": False,
                "replanning_required": False,
                "next_action": "PLANNING_FAILED",
                "error": f"Planning request failed: {exc}",
            }

        # Normalize the response to a candidate list.
        #
        # PlanningService.plan_async() returns a PlanningDecision
        # whose recommended_technicians contains the candidates.
        try:
            if planning_result is None:
                candidates = []

            elif isinstance(planning_result, list):
                candidates = planning_result

            elif isinstance(planning_result, dict):
                candidates = (
                    planning_result.get("recommended_technicians")
                    or planning_result.get("candidates")
                    or []
                )

            else:
                recommendations = getattr(
                    planning_result,
                    "recommended_technicians",
                    None,
                )

                if recommendations is None:
                    raise TypeError(
                        "Planning callback must return a list, "
                        "dictionary, or object with "
                        "'recommended_technicians'. "
                        f"Received: {type(planning_result).__name__}"
                    )

                candidates = recommendations

            # Convert recommendation models to dictionaries.
            normalized_candidates = []

            for candidate in candidates:
                if isinstance(candidate, dict):
                    candidate_data = candidate
                elif hasattr(candidate, "model_dump"):
                    candidate_data = candidate.model_dump(
                        mode="json"
                    )
                elif hasattr(candidate, "__dict__"):
                    candidate_data = vars(candidate)
                else:
                    logger.warning(
                        "Skipping invalid planning candidate | "
                        "job_id=%s | candidate=%r",
                        job_id,
                        candidate,
                    )
                    continue
                
                technician_id = self._candidate_technician_id(
                    candidate_data
                )

                if technician_id is None:
                    logger.warning(
                        "Skipping candidate without a valid "
                        "technician_id | job_id=%s | candidate=%s",
                        job_id,
                        candidate_data,
                    )
                    continue
                
                # Final safety check: never offer a technician twice.
                if technician_id in attempted:
                    logger.warning(
                        "Skipping previously attempted technician "
                        "| job_id=%s | technician_id=%s",
                        job_id,
                        technician_id,
                    )
                    continue
                
                normalized_candidates.append(candidate_data)

            # Planning owns ranking and batch membership. Preserve its batch.
            candidates = normalized_candidates

        except Exception as exc:
            logger.exception(
                "INVALID_PLANNING_RESPONSE | job_id=%s",
                job_id,
            )

            return {
                "candidates": [],
                "batch_number": next_batch_number,
                "current_index": 0,
                "current_technician_id": None,
                "planning_required": False,
                "replanning_required": False,
                "next_action": "PLANNING_FAILED",
                "error": f"Invalid Planning response: {exc}",
            }

        # If planning previously offered candidates and every one rejected or
        # timed out, finish this dispatch as rejected. Only a job that never
        # had an eligible candidate remains retryable.
        if not candidates:
            exhausted = bool(attempted)
            decision_reason = getattr(
                planning_result,
                "reason",
                None,
            )

            logger.warning(
                "NO_ELIGIBLE_TECHNICIANS | job_id=%s | "
                "batch=%s | attempted=%s | reason=%s | "
                "dispatching_stopped=True | exhausted=%s",
                job_id,
                next_batch_number,
                attempted,
                decision_reason,
                exhausted,
            )

            return {
                "candidates": [],
                "batch_number": next_batch_number,
                "current_index": 0,
                "current_technician_id": None,
                "planning_required": False,
                "replanning_required": False,
                "pending_retry": not exhausted,
                "dispatch_exhausted": exhausted,
                "batch_exhausted": True,
                "next_action": "ALL_TECHNICIANS_REJECTED_OR_TIMED_OUT" if exhausted else "NO_ELIGIBLE_TECHNICIAN",
                "error": None,
            }

        logger.info(
            "PLANNING_BATCH_READY | job_id=%s | batch=%s | "
            "candidate_count=%s | technician_ids=%s",
            job_id,
            next_batch_number,
            len(candidates),
            [
                self._candidate_technician_id(candidate)
                for candidate in candidates
            ],
        )

        return {
            "candidates": candidates,
            "batch_number": next_batch_number,
            "current_index": 0,
            "current_technician_id": None,
            "planning_required": False,
            "replanning_required": False,
            "next_action": "SELECT_CANDIDATE",
            "error": None,
        }



    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    @staticmethod
    def route_after_validation(
        state: DispatcherState,
    ) -> str:

        if state.get("error"):
            return "end"

        if state.get("pending_retry"):
            return "end"

        candidates = state.get("candidates") or []

        if candidates:
            return "select_candidate"

        if state.get("replanning_required"):
            return "request_replanning"

        return "end"

    @staticmethod
    def route_selection(
        state: DispatcherState,
    ) -> str:

        if state.get("error"):
            return "end"

        if state.get("current_technician_id") is not None:
            return "offer_job"

        if state.get("replanning_required"):
            return "request_replanning"

        return "end"

    @staticmethod
    def route_event(
        state: DispatcherState,
    ) -> str:

        event = state.get("event")

        if event == TECHNICIAN_ACCEPTED:
            return "handle_accepted"

        if event == TECHNICIAN_REJECTED:
            return "handle_rejected"

        if event == TECHNICIAN_TIMEOUT:
            return "handle_timeout"

        logger.error(
            "Dispatcher graph reached invalid event: %r",
            event,
        )

        return "end"

    @staticmethod
    def route_after_candidate_check(
        state: DispatcherState,
    ) -> str:
        """
        After REJECT/TIMEOUT:

        - Continue with another candidate if available.
        - Otherwise request another Planning batch.

        No tenant filtering occurs here.
        """

        logger.warning(
            "ROUTE_AFTER_CHECK | job_id=%s "
            "current_index=%s "
            "candidates=%s "
            "attempted=%s "
            "rejected=%s "
            "planning_required=%s "
            "replanning_required=%s "
            "next_action=%s",
            state.get("job_id"),
            state.get("current_index"),
            state.get("candidates"),
            state.get("attempted_technician_ids"),
            state.get("rejected_technician_ids"),
            state.get("planning_required"),
            state.get("replanning_required"),
            state.get("next_action"),
        )

        if state.get("error"):
            return "end"

        if state.get("replanning_required"):
            logger.info(
                "ROUTE_AFTER_CHECK | job_id=%s "
                "-> request_replanning",
                state.get("job_id"),
            )

            return "request_replanning"

        candidates = state.get("candidates") or []

        attempted = set(
            DispatcherGraph._unique_ints(
                state.get(
                    "attempted_technician_ids"
                ) or []
            )
        )

        index = int(
            state.get("current_index") or 0
        )

        while index < len(candidates):

            technician_id = (
                DispatcherGraph._candidate_technician_id(
                    candidates[index]
                )
            )

            logger.info(
                "ROUTE_AFTER_CHECK checking "
                "job_id=%s index=%s technician_id=%s "
                "attempted=%s",
                state.get("job_id"),
                index,
                technician_id,
                (
                    technician_id in attempted
                    if technician_id is not None
                    else None
                ),
            )

            if (
                technician_id is not None
                and technician_id not in attempted
            ):

                logger.warning(
                    "ROUTE_AFTER_CHECK | job_id=%s "
                    "-> select_candidate "
                    "index=%s technician_id=%s",
                    state.get("job_id"),
                    index,
                    technician_id,
                )

                return "select_candidate"

            index += 1

        logger.info(
            "ROUTE_AFTER_CHECK | job_id=%s "
            "-> request_replanning",
            state.get("job_id"),
        )

        return "request_replanning"

    @staticmethod
    def route_after_replanning(
        state: DispatcherState,
    ) -> str:

        if state.get("error"):
            logger.info(
                "ROUTE_AFTER_REPLANNING | job_id=%s | route=end | "
                "reason=error | error=%s",
                state.get("job_id"),
                state.get("error"),
            )
            return "end"

        candidates = state.get("candidates") or []

        if candidates:
            logger.info(
                "ROUTE_AFTER_REPLANNING | job_id=%s | route=select_candidate | "
                "reason=fresh_candidates_returned | candidate_count=%s",
                state.get("job_id"),
                len(candidates),
            )
            return "select_candidate"

        logger.info(
            "ROUTE_AFTER_REPLANNING | job_id=%s | route=end | "
            "reason=no_eligible_technicians | retryable=True",
            state.get("job_id"),
        )
        return "end"


__all__ = [
    "DispatcherGraph",
    "DispatcherState",
    "TECHNICIAN_ACCEPTED",
    "TECHNICIAN_REJECTED",
    "TECHNICIAN_TIMEOUT",
]
