from __future__ import annotations

from typing import Any

import pytest

from app.services.ai.FieldOpsAI.agents.dispatcher_agent.dispatcher_agent import (
    DispatcherGraph,
)
from app.services.ai.FieldOpsAI.agents.dispatcher_agent.dispatcher_state import (
    DispatcherState,
)


@pytest.mark.asyncio
async def test_dispatcher_uses_planning_order_without_rechecking_eligibility():
    offered: list[int] = []
    planning_calls: list[tuple[int, list[int]]] = []

    async def offer_job(job: dict[str, Any], technician_id: int) -> None:
        offered.append(technician_id)

    async def request_planning(job_id: int, excluded: list[int]) -> list[dict[str, Any]]:
        planning_calls.append((job_id, excluded))
        return []

    graph = DispatcherGraph(offer_job=offer_job, request_planning=request_planning)
    planning_result = {
        "top_3": [
            {"technician_id": 21, "rank": 1, "eligible": True, "location_age_seconds": 4},
            {"technician_id": 19, "rank": 2, "eligible": True, "location_age_seconds": 6},
        ],
        "all_ranked_technicians": [
            {"technician_id": 21, "rank": 1, "eligible": True, "location_age_seconds": 4},
            {"technician_id": 19, "rank": 2, "eligible": True, "location_age_seconds": 6},
        ],
    }
    state = make_state(candidates=planning_result["all_ranked_technicians"])
    result = await graph.start_dispatch(state)

    assert offered == [21]
    assert planning_calls == []
    assert result["current_technician_id"] == 21
    assert result["next_action"] == "WAIT_FOR_RESPONSE"


@pytest.mark.parametrize(
    "response",
    ["TECHNICIAN_REJECTED", "TECHNICIAN_TIMEOUT"],
)
@pytest.mark.asyncio
async def test_job_154_rejection_or_timeout_offers_rank_two_once(response):
    offered: list[int] = []
    offer_payloads: list[dict[str, Any]] = []

    async def offer_job(job: dict[str, Any], technician_id: int) -> None:
        offered.append(technician_id)
        offer_payloads.append(job)

    async def request_planning(job_id: int, excluded: list[int]) -> list[dict[str, Any]]:
        raise AssertionError("ranked candidates should be exhausted before replanning")

    graph = DispatcherGraph(offer_job=offer_job, request_planning=request_planning)
    state = make_state(
        job_id=154,
        candidates=[
            {"technician_id": 17, "technician_name": "Guru Tech", "rank": 1},
            {"technician_id": 18, "technician_name": "Ajay Tech", "rank": 2},
        ],
    )

    first = await graph.start_dispatch(state)
    assert first["current_technician_id"] == 17
    second = await graph.resume_dispatch(job_id=154, event=response)

    assert second["current_technician_id"] == 18
    assert offered == [17, 18]
    assert [payload["id"] for payload in offer_payloads] == [154, 154]
    assert [payload["job_id"] for payload in offer_payloads] == [154, 154]
    assert offer_payloads[1]["_dispatch_state"]["candidates"] == state["candidates"]
    assert offer_payloads[1]["_dispatch_state"]["attempted_technician_ids"] == [17]
    assert offer_payloads[1]["_dispatch_state"]["current_index"] == 1


@pytest.mark.asyncio
async def test_restart_recovery_advances_persisted_batch_without_duplicate_offer():
    offered: list[int] = []
    planning_calls: list[list[int]] = []

    async def offer_job(job: dict[str, Any], technician_id: int) -> None:
        offered.append(technician_id)

    async def request_planning(job_id: int, excluded: list[int]) -> list[dict[str, Any]]:
        planning_calls.append(excluded)
        return []

    graph = DispatcherGraph(offer_job=offer_job, request_planning=request_planning)
    persisted = {
        "job_id": 156,
        "dispatch_attempt_id": "attempt-156",
        "job": make_job(156),
        "candidates": make_candidates(18, 17),
        "all_candidates": make_candidates(18, 17),
        "batch_number": 1,
        "current_index": 0,
        "current_technician_id": 18,
        "attempted_technician_ids": [],
        "rejected_technician_ids": [],
        "next_action": "WAIT_FOR_RESPONSE",
    }

    recovered = await graph.resume_from_persisted_state(persisted, "TECHNICIAN_REJECTED")
    assert recovered["current_technician_id"] == 17
    assert offered == [17]
    assert planning_calls == []

    # A delayed duplicate from technician 18 is rejected by the runtime's
    # technician-id guard; the recovered next candidate stays active.
    duplicate = dict(recovered)
    assert duplicate["current_technician_id"] == 17



# ============================================================
# Helpers
# ============================================================


def make_job(job_id: int = 144) -> dict[str, Any]:
    return {
        "id": job_id,
        "service_type": "AC Repair",
        "location": "Chennai",
        "issue_description": "AC is not cooling",
        "priority": "HIGH",
    }


def make_candidates(
    *technician_ids: int,
) -> list[dict[str, Any]]:
    return [
        {
            "technician_id": technician_id,
            "rank": index,
        }
        for index, technician_id in enumerate(
            technician_ids,
            start=1,
        )
    ]


def make_state(
    *,
    job_id: int = 144,
    candidates: list[dict[str, Any]] | None = None,
) -> DispatcherState:
    return {
        "job_id": job_id,
        "job": make_job(job_id),
        "candidates": candidates or make_candidates(
            21,
            19,
            16,
        ),
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


# ============================================================
# Test 1
# ============================================================


@pytest.mark.asyncio
async def test_dispatcher_reject_timeout_reject_then_replans_and_accepts():
    """
    Batch 1:

        21 -> REJECT
        19 -> TIMEOUT
        16 -> REJECT

    All 3 fail.

    Dispatcher must call Planning again with:

        [21, 19, 16]

    Planning returns Batch 2:

        25
        30
        42

    Batch 2:

        25 -> REJECT
        30 -> ACCEPT

    Dispatcher must stop immediately after 30 accepts.

    Expected:

        assigned_technician_id = 30
        planning_calls = 1
    """

    offered: list[int] = []
    planning_calls: list[tuple[int, list[int]]] = []

    first_batch = make_candidates(
        21,
        19,
        16,
    )

    second_batch = make_candidates(
        25,
        30,
        42,
    )

    async def offer_job(
        job: dict[str, Any],
        technician_id: int,
    ) -> None:
        offered.append(technician_id)

    async def request_planning(
        job_id: int,
        excluded_technician_ids: list[int],
    ) -> list[dict[str, Any]]:
        planning_calls.append(
            (
                job_id,
                list(excluded_technician_ids),
            )
        )

        return second_batch

    dispatcher = DispatcherGraph(
        offer_job=offer_job,
        request_planning=request_planning,
    )

    state = make_state(
        candidates=first_batch,
    )

    # --------------------------------------------------------
    # Batch 1 - Technician 21
    # --------------------------------------------------------

    result = await dispatcher.start_dispatch(state)

    assert result["current_technician_id"] == 21
    assert result["next_action"] == "WAIT_FOR_RESPONSE"

    assert offered == [21]

    # --------------------------------------------------------
    # 21 REJECT
    # --------------------------------------------------------

    result = await dispatcher.resume_dispatch(
        job_id=144,
        event="TECHNICIAN_REJECTED",
    )

    assert result["current_technician_id"] == 19
    assert result["next_action"] == "WAIT_FOR_RESPONSE"

    assert offered == [
        21,
        19,
    ]

    # --------------------------------------------------------
    # 19 TIMEOUT
    # --------------------------------------------------------

    result = await dispatcher.resume_dispatch(
        job_id=144,
        event="TECHNICIAN_TIMEOUT",
    )

    assert result["current_technician_id"] == 16
    assert result["next_action"] == "WAIT_FOR_RESPONSE"

    assert offered == [
        21,
        19,
        16,
    ]

    # --------------------------------------------------------
    # 16 REJECT
    # --------------------------------------------------------

    result = await dispatcher.resume_dispatch(
        job_id=144,
        event="TECHNICIAN_REJECTED",
    )

    # Planning must have been called.
    assert len(planning_calls) == 1

    job_id, excluded = planning_calls[0]

    assert job_id == 144

    assert set(excluded) == {
        21,
        19,
        16,
    }

    # --------------------------------------------------------
    # New Planning Batch
    #
    # 25 should now be offered.
    # --------------------------------------------------------

    assert result["batch_number"] == 2
    assert result["current_technician_id"] == 25
    assert result["current_index"] == 0
    assert result["next_action"] == "WAIT_FOR_RESPONSE"

    assert offered == [
        21,
        19,
        16,
        25,
    ]

    # --------------------------------------------------------
    # 25 REJECT
    # --------------------------------------------------------

    result = await dispatcher.resume_dispatch(
        job_id=144,
        event="TECHNICIAN_REJECTED",
    )

    assert result["current_technician_id"] == 30
    assert result["next_action"] == "WAIT_FOR_RESPONSE"

    assert offered == [
        21,
        19,
        16,
        25,
        30,
    ]

    # --------------------------------------------------------
    # 30 ACCEPT
    # --------------------------------------------------------

    result = await dispatcher.resume_dispatch(
        job_id=144,
        event="TECHNICIAN_ACCEPTED",
    )

    assert result["assigned_technician_id"] == 30
    assert result["next_action"] == "COMPLETE_ASSIGNMENT"

    # No third candidate should be offered.
    assert 42 not in offered

    # Planning must NOT be called again.
    assert len(planning_calls) == 1

    # All attempted technicians should be preserved.
    assert set(
        result["attempted_technician_ids"]
    ) == {
        21,
        19,
        16,
        25,
        30,
    }


# ============================================================
# Test 2
# ============================================================


@pytest.mark.asyncio
async def test_dispatcher_accepts_second_candidate_without_replanning():
    """
    Batch 1:

        21 -> REJECT
        19 -> ACCEPT

    Dispatcher must stop immediately.

    Planning must NOT be called again.
    """

    offered: list[int] = []
    planning_calls: list[tuple[int, list[int]]] = []

    async def offer_job(
        job: dict[str, Any],
        technician_id: int,
    ) -> None:
        offered.append(technician_id)

    async def request_planning(
        job_id: int,
        excluded_technician_ids: list[int],
    ) -> list[dict[str, Any]]:
        planning_calls.append(
            (
                job_id,
                list(excluded_technician_ids),
            )
        )

        return make_candidates(
            25,
            30,
            42,
        )

    dispatcher = DispatcherGraph(
        offer_job=offer_job,
        request_planning=request_planning,
    )

    state = make_state(
        candidates=make_candidates(
            21,
            19,
            16,
        )
    )

    # 21 offered
    result = await dispatcher.start_dispatch(state)

    assert result["current_technician_id"] == 21

    # 21 rejects -> 19 offered
    result = await dispatcher.resume_dispatch(
        job_id=144,
        event="TECHNICIAN_REJECTED",
    )

    assert result["current_technician_id"] == 19

    # 19 accepts
    result = await dispatcher.resume_dispatch(
        job_id=144,
        event="TECHNICIAN_ACCEPTED",
    )

    assert result["assigned_technician_id"] == 19
    assert result["next_action"] == "COMPLETE_ASSIGNMENT"

    # 16 must never be offered.
    assert offered == [
        21,
        19,
    ]

    # Planning must never be called.
    assert planning_calls == []


# ============================================================
# Test 3
# ============================================================


@pytest.mark.asyncio
async def test_dispatcher_three_timeouts_trigger_replanning():
    """
    Batch 1:

        21 -> TIMEOUT
        19 -> TIMEOUT
        16 -> TIMEOUT

    All candidates timeout.

    Dispatcher must request fresh Planning.
    """

    offered: list[int] = []
    planning_calls: list[tuple[int, list[int]]] = []

    async def offer_job(
        job: dict[str, Any],
        technician_id: int,
    ) -> None:
        offered.append(technician_id)

    async def request_planning(
        job_id: int,
        excluded_technician_ids: list[int],
    ) -> list[dict[str, Any]]:
        planning_calls.append(
            (
                job_id,
                list(excluded_technician_ids),
            )
        )

        return make_candidates(
            25,
            30,
            42,
        )

    dispatcher = DispatcherGraph(
        offer_job=offer_job,
        request_planning=request_planning,
    )

    state = make_state(
        candidates=make_candidates(
            21,
            19,
            16,
        )
    )

    # 21
    result = await dispatcher.start_dispatch(state)

    assert result["current_technician_id"] == 21

    # 21 timeout -> 19
    result = await dispatcher.resume_dispatch(
        job_id=144,
        event="TECHNICIAN_TIMEOUT",
    )

    assert result["current_technician_id"] == 19

    # 19 timeout -> 16
    result = await dispatcher.resume_dispatch(
        job_id=144,
        event="TECHNICIAN_TIMEOUT",
    )

    assert result["current_technician_id"] == 16

    # 16 timeout -> Planning
    result = await dispatcher.resume_dispatch(
        job_id=144,
        event="TECHNICIAN_TIMEOUT",
    )

    assert len(planning_calls) == 1

    assert planning_calls[0][0] == 144

    assert set(
        planning_calls[0][1]
    ) == {
        21,
        19,
        16,
    }

    # New batch should start.
    assert result["batch_number"] == 2
    assert result["current_technician_id"] == 25

    assert offered == [
        21,
        19,
        16,
        25,
    ]


# ============================================================
# Test 4
# ============================================================


@pytest.mark.asyncio
async def test_replanning_excludes_all_attempted_technicians():
    """
    Verify that REJECT and TIMEOUT technicians are both included
    in the exclusion list sent to Planning.
    """

    planning_calls: list[tuple[int, list[int]]] = []

    async def offer_job(
        job: dict[str, Any],
        technician_id: int,
    ) -> None:
        pass

    async def request_planning(
        job_id: int,
        excluded_technician_ids: list[int],
    ) -> list[dict[str, Any]]:
        planning_calls.append(
            (
                job_id,
                list(excluded_technician_ids),
            )
        )

        return make_candidates(
            25,
            30,
            42,
        )

    dispatcher = DispatcherGraph(
        offer_job=offer_job,
        request_planning=request_planning,
    )

    state = make_state(
        candidates=make_candidates(
            21,
            19,
            16,
        )
    )

    await dispatcher.start_dispatch(state)

    # 21 rejected
    await dispatcher.resume_dispatch(
        job_id=144,
        event="TECHNICIAN_REJECTED",
    )

    # 19 timeout
    await dispatcher.resume_dispatch(
        job_id=144,
        event="TECHNICIAN_TIMEOUT",
    )

    # 16 rejected -> replan
    await dispatcher.resume_dispatch(
        job_id=144,
        event="TECHNICIAN_REJECTED",
    )

    assert len(planning_calls) == 1

    excluded = planning_calls[0][1]

    assert set(excluded) == {
        21,
        19,
        16,
    }


# ============================================================
# Test 5
# ============================================================


@pytest.mark.asyncio
async def test_accepted_candidate_stops_before_rank_three():
    """
    Verify that ACCEPT stops the current batch immediately.

    21 -> REJECT
    19 -> ACCEPT

    16 must never be offered.
    Planning must not be called.
    """

    offered: list[int] = []
    planning_call_count = 0

    async def offer_job(
        job: dict[str, Any],
        technician_id: int,
    ) -> None:
        offered.append(technician_id)

    async def request_planning(
        job_id: int,
        excluded_technician_ids: list[int],
    ) -> list[dict[str, Any]]:
        nonlocal planning_call_count

        planning_call_count += 1

        return make_candidates(
            25,
            30,
            42,
        )

    dispatcher = DispatcherGraph(
        offer_job=offer_job,
        request_planning=request_planning,
    )

    state = make_state(
        candidates=make_candidates(
            21,
            19,
            16,
        )
    )

    await dispatcher.start_dispatch(state)

    await dispatcher.resume_dispatch(
        job_id=144,
        event="TECHNICIAN_REJECTED",
    )

    result = await dispatcher.resume_dispatch(
        job_id=144,
        event="TECHNICIAN_ACCEPTED",
    )

    assert result["assigned_technician_id"] == 19

    assert offered == [
        21,
        19,
    ]

    assert 16 not in offered

    assert planning_call_count == 0


# ============================================================
# Test 6
# ============================================================


@pytest.mark.asyncio
async def test_fresh_planning_batch_preserves_attempt_history():
    """
    Verify that the second Planning batch does not reset
    attempted technician history.
    """

    async def offer_job(
        job: dict[str, Any],
        technician_id: int,
    ) -> None:
        pass

    planning_calls: list[list[int]] = []

    async def request_planning(
        job_id: int,
        excluded_technician_ids: list[int],
    ) -> list[dict[str, Any]]:
        planning_calls.append(
            list(excluded_technician_ids)
        )

        return make_candidates(
            25,
            30,
            42,
        )

    dispatcher = DispatcherGraph(
        offer_job=offer_job,
        request_planning=request_planning,
    )

    state = make_state(
        candidates=make_candidates(
            21,
            19,
            16,
        )
    )

    await dispatcher.start_dispatch(state)

    await dispatcher.resume_dispatch(
        job_id=144,
        event="TECHNICIAN_REJECTED",
    )

    await dispatcher.resume_dispatch(
        job_id=144,
        event="TECHNICIAN_REJECTED",
    )

    result = await dispatcher.resume_dispatch(
        job_id=144,
        event="TECHNICIAN_REJECTED",
    )

    assert result["batch_number"] == 2

    assert result["current_technician_id"] == 25

    assert set(
        result["attempted_technician_ids"]
    ) == {
        21,
        19,
        16,
    }

    assert planning_calls == [
        [
            21,
            19,
            16,
        ]
    ]


# ============================================================
# Test 7
# ============================================================


@pytest.mark.asyncio
async def test_replanning_returns_fresh_top_three():
    """
    Verify that the result returned by Planning actually becomes
    the active candidate batch.
    """

    offered: list[int] = []

    async def offer_job(
        job: dict[str, Any],
        technician_id: int,
    ) -> None:
        offered.append(technician_id)

    async def request_planning(
        job_id: int,
        excluded_technician_ids: list[int],
    ) -> list[dict[str, Any]]:
        return [
            {
                "technician_id": 101,
                "rank": 1,
            },
            {
                "technician_id": 102,
                "rank": 2,
            },
            {
                "technician_id": 103,
                "rank": 3,
            },
        ]

    dispatcher = DispatcherGraph(
        offer_job=offer_job,
        request_planning=request_planning,
    )

    state = make_state(
        candidates=make_candidates(
            21,
            19,
            16,
        )
    )

    await dispatcher.start_dispatch(state)

    # Exhaust first batch.
    await dispatcher.resume_dispatch(
        job_id=144,
        event="TECHNICIAN_REJECTED",
    )

    await dispatcher.resume_dispatch(
        job_id=144,
        event="TECHNICIAN_REJECTED",
    )

    result = await dispatcher.resume_dispatch(
        job_id=144,
        event="TECHNICIAN_REJECTED",
    )

    # First candidate from new Top-3 must be offered.
    assert result["current_technician_id"] == 101

    assert result["candidates"] == [
        {
            "technician_id": 101,
            "rank": 1,
        },
        {
            "technician_id": 102,
            "rank": 2,
        },
        {
            "technician_id": 103,
            "rank": 3,
        },
    ]

    assert result["batch_number"] == 2

    assert offered == [
        21,
        19,
        16,
        101,
    ]


# ============================================================
# Test 8
# ============================================================


@pytest.mark.asyncio
async def test_replanning_preserves_entire_ranked_batch():
    """The whole Planning batch remains active until it is exhausted."""

    offered: list[int] = []

    async def offer_job(
        job: dict[str, Any],
        technician_id: int,
    ) -> None:
        offered.append(technician_id)

    async def request_planning(
        job_id: int,
        excluded_technician_ids: list[int],
    ) -> list[dict[str, Any]]:
        return [
            {"technician_id": 25, "rank": 1},
            {"technician_id": 30, "rank": 2},
            {"technician_id": 42, "rank": 3},
            {"technician_id": 55, "rank": 4},
            {"technician_id": 60, "rank": 5},
        ]

    dispatcher = DispatcherGraph(
        offer_job=offer_job,
        request_planning=request_planning,
    )

    state = make_state(
        candidates=make_candidates(
            21,
            19,
            16,
        )
    )

    await dispatcher.start_dispatch(state)

    # Exhaust first batch.
    await dispatcher.resume_dispatch(
        job_id=144,
        event="TECHNICIAN_REJECTED",
    )

    await dispatcher.resume_dispatch(
        job_id=144,
        event="TECHNICIAN_REJECTED",
    )

    result = await dispatcher.resume_dispatch(
        job_id=144,
        event="TECHNICIAN_REJECTED",
    )

    assert result["candidates"] == [
        {
            "technician_id": 25,
            "rank": 1,
        },
        {
            "technician_id": 30,
            "rank": 2,
        },
        {
            "technician_id": 42,
            "rank": 3,
        },
        {"technician_id": 55, "rank": 4},
        {"technician_id": 60, "rank": 5},
    ]

    assert result["current_technician_id"] == 25

    assert offered[-1] == 25


# ============================================================
# Test 9
# ============================================================


@pytest.mark.asyncio
async def test_no_candidates_from_replanning_is_handled():
    """
    If Planning returns an empty list, Dispatcher should not
    invent candidates.
    """

    planning_calls = 0

    async def offer_job(
        job: dict[str, Any],
        technician_id: int,
    ) -> None:
        pass

    async def request_planning(
        job_id: int,
        excluded_technician_ids: list[int],
    ) -> list[dict[str, Any]]:
        nonlocal planning_calls

        planning_calls += 1

        return []

    dispatcher = DispatcherGraph(
        offer_job=offer_job,
        request_planning=request_planning,
    )

    state = make_state(
        candidates=make_candidates(
            21,
            19,
            16,
        )
    )

    await dispatcher.start_dispatch(state)

    await dispatcher.resume_dispatch(
        job_id=144,
        event="TECHNICIAN_REJECTED",
    )

    await dispatcher.resume_dispatch(
        job_id=144,
        event="TECHNICIAN_REJECTED",
    )

    result = await dispatcher.resume_dispatch(
        job_id=144,
        event="TECHNICIAN_REJECTED",
    )

    assert planning_calls == 1

    assert result["candidates"] == []

    assert result["current_technician_id"] is None

    assert result["planning_required"] is False

    assert result["replanning_required"] is False

    assert result["next_action"] == "ALL_TECHNICIANS_REJECTED_OR_TIMED_OUT"
    assert result["pending_retry"] is False
    assert result["dispatch_exhausted"] is True
    assert result["batch_exhausted"] is True
    assert result["error"] is None


# ============================================================
# Test 10
# ============================================================


@pytest.mark.asyncio
async def test_timeout_and_reject_are_both_excluded_from_replanning():
    """
    Explicitly verify:

        REJECT -> excluded
        TIMEOUT -> excluded
        REJECT -> excluded

    """

    excluded_received: list[int] = []

    async def offer_job(
        job: dict[str, Any],
        technician_id: int,
    ) -> None:
        pass

    async def request_planning(
        job_id: int,
        excluded_technician_ids: list[int],
    ) -> list[dict[str, Any]]:
        excluded_received.extend(
            excluded_technician_ids
        )

        return make_candidates(
            25,
            30,
            42,
        )

    dispatcher = DispatcherGraph(
        offer_job=offer_job,
        request_planning=request_planning,
    )

    state = make_state(
        candidates=make_candidates(
            21,
            19,
            16,
        )
    )

    await dispatcher.start_dispatch(state)

    # 21 REJECT
    await dispatcher.resume_dispatch(
        job_id=144,
        event="TECHNICIAN_REJECTED",
    )

    # 19 TIMEOUT
    await dispatcher.resume_dispatch(
        job_id=144,
        event="TECHNICIAN_TIMEOUT",
    )

    # 16 REJECT
    await dispatcher.resume_dispatch(
        job_id=144,
        event="TECHNICIAN_REJECTED",
    )

    assert set(excluded_received) == {
        21,
        19,
        16,
    }


# ============================================================
# Test 11
# ============================================================


@pytest.mark.asyncio
async def test_multiple_planning_batches_until_acceptance():
    """
    Verify that Dispatcher can continue through multiple
    Planning batches.

    Batch 1:
        21 -> REJECT
        19 -> REJECT
        16 -> REJECT

    Batch 2:
        25 -> REJECT
        30 -> REJECT
        42 -> REJECT

    Batch 3:
        50 -> ACCEPT

    Planning should be called twice.
    """

    offered: list[int] = []
    planning_calls: list[list[int]] = []

    async def offer_job(
        job: dict[str, Any],
        technician_id: int,
    ) -> None:
        offered.append(technician_id)

    async def request_planning(
        job_id: int,
        excluded_technician_ids: list[int],
    ) -> list[dict[str, Any]]:
        planning_calls.append(
            list(excluded_technician_ids)
        )

        if len(planning_calls) == 1:
            return make_candidates(
                25,
                30,
                42,
            )

        return make_candidates(
            50,
            60,
            70,
        )

    dispatcher = DispatcherGraph(
        offer_job=offer_job,
        request_planning=request_planning,
    )

    state = make_state(
        candidates=make_candidates(
            21,
            19,
            16,
        )
    )

    # --------------------------------------------------------
    # Batch 1
    # --------------------------------------------------------

    await dispatcher.start_dispatch(state)

    await dispatcher.resume_dispatch(
        job_id=144,
        event="TECHNICIAN_REJECTED",
    )

    await dispatcher.resume_dispatch(
        job_id=144,
        event="TECHNICIAN_REJECTED",
    )

    result = await dispatcher.resume_dispatch(
        job_id=144,
        event="TECHNICIAN_REJECTED",
    )

    # Batch 2 started.
    assert result["batch_number"] == 2
    assert result["current_technician_id"] == 25

    # --------------------------------------------------------
    # Batch 2
    # --------------------------------------------------------

    await dispatcher.resume_dispatch(
        job_id=144,
        event="TECHNICIAN_REJECTED",
    )

    await dispatcher.resume_dispatch(
        job_id=144,
        event="TECHNICIAN_REJECTED",
    )

    result = await dispatcher.resume_dispatch(
        job_id=144,
        event="TECHNICIAN_REJECTED",
    )

    # Batch 3 started.
    assert result["batch_number"] == 3
    assert result["current_technician_id"] == 50

    # --------------------------------------------------------
    # Batch 3
    # --------------------------------------------------------

    result = await dispatcher.resume_dispatch(
        job_id=144,
        event="TECHNICIAN_ACCEPTED",
    )

    assert result["assigned_technician_id"] == 50

    assert result["next_action"] == "COMPLETE_ASSIGNMENT"

    # Planning called twice:
    #
    # Batch 1 -> Batch 2
    # Batch 2 -> Batch 3
    #
    assert len(planning_calls) == 2

    # Verify Batch 2 excluded Batch 1 technicians.
    assert set(
        planning_calls[0]
    ) == {
        21,
        19,
        16,
    }

    # Verify Batch 3 excluded all previous attempts.
    assert set(
        planning_calls[1]
    ) == {
        21,
        19,
        16,
        25,
        30,
        42,
    }

    assert offered == [
        21,
        19,
        16,
        25,
        30,
        42,
        50,
    ]


# ============================================================
# Test 12
# ============================================================


@pytest.mark.asyncio
async def test_invalid_event_is_rejected():
    """
    Dispatcher should reject unsupported external events.
    """

    async def offer_job(
        job: dict[str, Any],
        technician_id: int,
    ) -> None:
        pass

    async def request_planning(
        job_id: int,
        excluded_technician_ids: list[int],
    ) -> list[dict[str, Any]]:
        return make_candidates(
            25,
            30,
            42,
        )

    dispatcher = DispatcherGraph(
        offer_job=offer_job,
        request_planning=request_planning,
    )

    with pytest.raises(ValueError):
        await dispatcher.resume_dispatch(
            job_id=144,
            event="INVALID_EVENT",
        )
