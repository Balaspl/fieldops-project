from __future__ import annotations

import pytest

from app.services.ai.FieldOpsAI.agents.dispatcher_agent.dispatcher_agent import (
    DispatcherGraph,
)


@pytest.mark.asyncio
async def test_dispatcher_reject_timeout_accept():
    offered = []
    replanning_calls = []

    async def offer_job(job, technician_id):
        offered.append(technician_id)

    async def request_planning(job_id, rejected_ids):
        replanning_calls.append(
            (job_id, rejected_ids)
        )

    dispatcher = DispatcherGraph(
        offer_job=offer_job,
        request_planning=request_planning,
    )

    state = {
        "job_id": 144,
        "job": {
            "id": 144,
            "title": "Test Job",
        },
        "candidates": [
            {
                "technician_id": 21,
                "rank": 1,
            },
            {
                "technician_id": 19,
                "rank": 2,
            },
            {
                "technician_id": 16,
                "rank": 3,
            },
        ],
        "current_index": 0,
        "attempted_technician_ids": [],
        "rejected_technician_ids": [],
        "event": None,
        "next_action": None,
        "assigned_technician_id": None,
        "replanning_required": False,
        "error": None,
    }

    # ---------------------------------------------------------
    # 1. Start dispatch
    # ---------------------------------------------------------

    result = await dispatcher.start_dispatch(state)

    assert offered == [21]

    assert result["next_action"] == "WAIT_FOR_RESPONSE"

    # ---------------------------------------------------------
    # 2. Technician 21 rejects
    # ---------------------------------------------------------

    result = await dispatcher.resume_dispatch(
        job_id=144,
        event="TECHNICIAN_REJECTED",
    )

    assert offered == [21, 19]

    assert result["next_action"] == "WAIT_FOR_RESPONSE"

    assert result["rejected_technician_ids"] == [21]

    # ---------------------------------------------------------
    # 3. Technician 19 times out
    # ---------------------------------------------------------

    result = await dispatcher.resume_dispatch(
        job_id=144,
        event="TECHNICIAN_TIMEOUT",
    )

    assert offered == [21, 19, 16]

    assert result["next_action"] == "WAIT_FOR_RESPONSE"

    assert result["rejected_technician_ids"] == [
        21,
        19,
    ]

    # ---------------------------------------------------------
    # 4. Technician 16 accepts
    # ---------------------------------------------------------

    result = await dispatcher.resume_dispatch(
        job_id=144,
        event="TECHNICIAN_ACCEPTED",
    )

    assert result["assigned_technician_id"] == 16

    assert result["next_action"] == "COMPLETE_ASSIGNMENT"

    assert result["replanning_required"] is False

    # ---------------------------------------------------------
    # 5. Planning should NOT have been requested
    # ---------------------------------------------------------

    assert replanning_calls == []

@pytest.mark.asyncio
async def test_dispatcher_all_candidates_rejected():
    offered = []
    replanning_calls = []

    async def offer_job(job, technician_id):
        offered.append(technician_id)

    async def request_planning(job_id, rejected_ids):
        replanning_calls.append(
            (job_id, rejected_ids)
        )

    dispatcher = DispatcherGraph(
        offer_job=offer_job,
        request_planning=request_planning,
    )

    state = {
        "job_id": 144,
        "job": {
            "id": 144,
            "title": "Test Job",
        },
        "candidates": [
            {"technician_id": 21, "rank": 1},
            {"technician_id": 19, "rank": 2},
            {"technician_id": 16, "rank": 3},
        ],
        "current_index": 0,
        "attempted_technician_ids": [],
        "rejected_technician_ids": [],
        "event": None,
        "next_action": None,
        "assigned_technician_id": None,
        "replanning_required": False,
        "error": None,
    }

    # T21
    result = await dispatcher.start_dispatch(state)

    assert offered == [21]

    # T21 rejects → T19
    result = await dispatcher.resume_dispatch(
        job_id=144,
        event="TECHNICIAN_REJECTED",
    )

    assert offered == [21, 19]

    # T19 rejects → T16
    result = await dispatcher.resume_dispatch(
        job_id=144,
        event="TECHNICIAN_REJECTED",
    )

    assert offered == [21, 19, 16]

    # T16 rejects → re-planning
    result = await dispatcher.resume_dispatch(
        job_id=144,
        event="TECHNICIAN_REJECTED",
    )

    assert result["replanning_required"] is False

    # All candidates in this dispatch were attempted and rejected, so this
    # dispatch is exhausted rather than waiting for a retry.
    assert result["next_action"] == "ALL_TECHNICIANS_REJECTED_OR_TIMED_OUT"
    assert result["pending_retry"] is False
    assert result["dispatch_exhausted"] is True
    assert result["batch_exhausted"] is True

    assert result["assigned_technician_id"] is None

    assert replanning_calls == [
        (144, [21, 19, 16])
    ]