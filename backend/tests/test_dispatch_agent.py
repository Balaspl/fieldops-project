"""
test_dispatch_agent.py

Production-hardened unit and integration tests for DispatchAgent and DispatchService.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Dict, List, Optional
import pytest
from pydantic import ValidationError
from unittest.mock import MagicMock, patch

from app.services.ai.FieldOpsAI.agents.dispatch_agent import DispatchAgent
from app.services.ai.FieldOpsAI.agents.base import (
    BaseAgent,
    AgentState,
    AgentDisabledError,
    TenantIsolationError,
    AgentLifecycleError,
)
from app.services.ai.FieldOpsAI.services.dispatch_service import DispatchService
from app.services.ai.FieldOpsAI.repositories.job_assignment_repository import JobAssignmentRepository
from app.services.ai.FieldOpsAI.schemas.agent_config import AgentConfig
from app.services.ai.FieldOpsAI.schemas.ai_task import AITask
from app.services.ai.FieldOpsAI.schemas.dispatch import DispatchContext, DispatchDecision
from app.services.ai.FieldOpsAI.runtime.orchestrator import AIOrchestrator
from app.services.ai.FieldOpsAI.config.agent_config_manager import AgentConfigManager
from app.services.ai.FieldOpsAI.runtime.agent_pool import AgentPool
from app.services.ai.FieldOpsAI.runtime.lifecycle import AgentLifecycle
from app.services.ai.FieldOpsAI.schemas.agent_result import AgentResult, AgentResultStatus
from app.models import JobAssignment


class MockOrchestrator:
    """
    Mock orchestrator that can act as a falsey test double if needed.
    """
    def __init__(self, response_decision: Any, is_falsey: bool = False) -> None:
        self.response_decision = response_decision
        self.is_falsey = is_falsey
        self.calls_count = 0
        self.last_task = None
        self.last_context = None

    def __bool__(self) -> bool:
        return not self.is_falsey

    def execute(self, task: AITask, context: dict, response_schema: Any) -> Any:
        self.calls_count += 1
        self.last_task = task
        self.last_context = context
        return self.response_decision


class FailingOrchestrator:
    def __init__(self) -> None:
        self.calls_count = 0

    def execute(self, task: AITask, context: dict, response_schema: Any) -> Any:
        self.calls_count += 1
        raise RuntimeError("API failure")


class FalseyAgentPool(AgentPool):
    def __bool__(self) -> bool:
        return False


@pytest.fixture
def valid_dispatch_config() -> AgentConfig:
    return AgentConfig(
        agent_type=AITask.DISPATCH,
        tenant_id="tenant-123",
        agent_version="1.0",
        timeout_seconds=30.0,
        max_retries=2,
        enabled=True,
    )


@pytest.fixture
def sample_decision() -> DispatchDecision:
    return DispatchDecision(
        action="complete_assignment",
        job_id=101,
        technician_id=12,
        status="ACCEPTED",
        confidence=0.98,
        reason="Technician accepted assignment, complete workflow."
    )


@pytest.fixture
def sample_context_dict() -> dict[str, Any]:
    return {
        "tenant_id": "tenant-123",
        "job": {
            "id": 101,
            "customer_name": "Acme Corp",
            "location": "Downtown",
            "priority": "HIGH",
            "service_type": "HVAC",
            "required_skill": "HVAC",
            "status": "QUEUED"
        },
        "current_technician": {
            "technician_id": 12,
            "technician_name": "John Doe",
            "skills": "HVAC",
            "location": "Downtown",
            "status": "Available",
            "current_jobs": 0,
            "max_jobs": 3,
            "tenant_id": "tenant-123"
        },
        "event": "TECHNICIAN_ACCEPTED",
        "remaining_candidates": [],
        "rejected_technician_ids": []
    }


class FakeJob:
    def __init__(self, id: int, tenant_id: str, customer_name: str, location: str, priority: str, service_type: str, required_skill: str, status: str) -> None:
        self.id = id
        self.tenant_id = tenant_id
        self.customer_name = customer_name
        self.location = location
        self.priority = priority
        self.service_type = service_type
        self.required_skill = required_skill
        self.status = status


class FakeTechnician:
    def __init__(self, technician_id: int, technician_name: str, technician_skill: str, technician_location: str, technician_status: str, current_jobs: int, max_jobs: int, tenant_id: str = "tenant-123") -> None:
        self.technician_id = technician_id
        self.technician_name = technician_name
        self.technician_skill = technician_skill
        self.technician_location = technician_location
        self.technician_status = technician_status
        self.current_jobs = current_jobs
        self.max_jobs = max_jobs
        self.tenant_id = tenant_id


def assert_zero_side_effects(mock_job_repo: Any, mock_tech_repo: Any, mock_assign_repo: Any) -> None:
    """
    Assert that all database mutation and save methods are not called.
    """
    mock_assign_repo.mark_accepted.assert_not_called()
    mock_assign_repo.mark_rejected.assert_not_called()
    mock_assign_repo.mark_timeout.assert_not_called()
    mock_assign_repo.promote_next_candidate.assert_not_called()
    mock_job_repo.assign_technician.assert_not_called()
    mock_job_repo.update_status.assert_not_called()
    mock_tech_repo.update_status.assert_not_called()
    mock_tech_repo.increment_jobs.assert_not_called()
    mock_assign_repo.save.assert_not_called()


# ==========================================================
# DispatchAgent Migration Tests
# ==========================================================

def test_dispatch_agent_inherits_from_base_agent(valid_dispatch_config: AgentConfig) -> None:
    agent = DispatchAgent(config=valid_dispatch_config)
    assert isinstance(agent, BaseAgent)


def test_constructor_accepts_valid_dispatch_config(valid_dispatch_config: AgentConfig) -> None:
    agent = DispatchAgent(config=valid_dispatch_config)
    assert agent.config == valid_dispatch_config
    assert agent.tenant_id == "tenant-123"


def test_constructor_rejects_non_dispatch_config() -> None:
    bad_config = AgentConfig(
        agent_type=AITask.PLANNING,
        tenant_id="tenant-123",
        enabled=True,
    )
    with pytest.raises(ValueError) as exc_info:
        DispatchAgent(config=bad_config)
    assert "DispatchAgent requires an AITask.DISPATCH configuration" in str(exc_info.value)


def test_dispatch_agent_preserves_supplied_falsey_orchestrator(valid_dispatch_config: AgentConfig) -> None:
    falsey_orch = MockOrchestrator(None, is_falsey=True)  # type: ignore
    assert bool(falsey_orch) is False

    agent = DispatchAgent(config=valid_dispatch_config, orchestrator=falsey_orch)  # type: ignore
    assert agent.orchestrator is falsey_orch


def test_dispatch_agent_creates_default_orchestrator_when_omitted(valid_dispatch_config: AgentConfig) -> None:
    agent = DispatchAgent(config=valid_dispatch_config)
    assert agent.orchestrator is not None


@pytest.mark.anyio
async def test_setup_works_through_base_agent(valid_dispatch_config: AgentConfig) -> None:
    agent = DispatchAgent(config=valid_dispatch_config)
    assert agent.state == AgentState.IDLE
    await agent.setup()
    assert agent.state == AgentState.IDLE


@pytest.mark.anyio
async def test_valid_context_returns_dispatch_decision(
    valid_dispatch_config: AgentConfig,
    sample_decision: DispatchDecision,
    sample_context_dict: dict[str, Any]
) -> None:
    orch = MockOrchestrator(sample_decision)
    agent = DispatchAgent(config=valid_dispatch_config, orchestrator=orch)  # type: ignore
    await agent.setup()

    decision = await agent.run(sample_context_dict)
    assert decision == sample_decision
    assert orch.calls_count == 1
    assert orch.last_task == AITask.DISPATCH
    assert orch.last_context == DispatchContext.model_validate(sample_context_dict).model_dump(mode="json")


@pytest.mark.anyio
async def test_invalid_context_raises_pydantic_validation_error(
    valid_dispatch_config: AgentConfig,
    sample_context_dict: dict[str, Any]
) -> None:
    agent = DispatchAgent(config=valid_dispatch_config)
    await agent.setup()

    # invalidate context
    del sample_context_dict["event"]

    with pytest.raises(ValidationError):
        await agent.run(sample_context_dict)


@pytest.mark.anyio
async def test_missing_tenant_id_is_rejected(
    valid_dispatch_config: AgentConfig,
    sample_context_dict: dict[str, Any]
) -> None:
    agent = DispatchAgent(config=valid_dispatch_config)
    await agent.setup()

    # remove tenant_id
    del sample_context_dict["tenant_id"]

    with pytest.raises(TenantIsolationError):
        await agent.execute(sample_context_dict)


@pytest.mark.anyio
async def test_cross_tenant_context_is_rejected(
    valid_dispatch_config: AgentConfig,
    sample_context_dict: dict[str, Any]
) -> None:
    agent = DispatchAgent(config=valid_dispatch_config)
    await agent.setup()

    sample_context_dict["tenant_id"] = "tenant-different"

    with pytest.raises(TenantIsolationError):
        await agent.execute(sample_context_dict)


@pytest.mark.anyio
async def test_disabled_configuration_cannot_execute(sample_context_dict: dict[str, Any]) -> None:
    disabled_config = AgentConfig(
        agent_type=AITask.DISPATCH,
        tenant_id="tenant-123",
        enabled=False,
    )
    agent = DispatchAgent(disabled_config)
    await agent.setup()

    with pytest.raises(AgentDisabledError):
        await agent.execute(sample_context_dict)


@pytest.mark.anyio
async def test_successful_execution_returns_state_to_idle_before_teardown(
    valid_dispatch_config: AgentConfig,
    sample_decision: DispatchDecision,
    sample_context_dict: dict[str, Any]
) -> None:
    orch = MockOrchestrator(sample_decision)
    agent = DispatchAgent(config=valid_dispatch_config, orchestrator=orch)  # type: ignore
    await agent.setup()

    pool = AgentPool()
    async with AgentLifecycle(agent=agent, pool=pool) as lifecycle:
        assert agent.state == AgentState.IDLE
        result = await lifecycle.execute(sample_context_dict)
        assert result.status == AgentResultStatus.SUCCESS
        assert agent.state == AgentState.IDLE

    assert agent.state == AgentState.TERMINATED


@pytest.mark.anyio
async def test_orchestrator_failure_changes_state_to_error_and_calls_once(
    valid_dispatch_config: AgentConfig,
    sample_context_dict: dict[str, Any]
) -> None:
    orch = FailingOrchestrator()
    agent = DispatchAgent(config=valid_dispatch_config, orchestrator=orch)  # type: ignore
    await agent.setup()

    pool = AgentPool()
    async with AgentLifecycle(agent=agent, pool=pool) as lifecycle:
        result = await lifecycle.execute(sample_context_dict)
        assert result.status == AgentResultStatus.FAILED
        assert agent.state == AgentState.ERROR
        assert orch.calls_count == 1


@pytest.mark.anyio
async def test_repeated_execution_does_not_mutate_input(
    valid_dispatch_config: AgentConfig,
    sample_decision: DispatchDecision,
    sample_context_dict: dict[str, Any]
) -> None:
    orch = MockOrchestrator(sample_decision)
    agent = DispatchAgent(config=valid_dispatch_config, orchestrator=orch)  # type: ignore
    await agent.setup()

    context_copy = dict(sample_context_dict)
    await agent.execute(sample_context_dict)
    assert sample_context_dict == context_copy


@pytest.mark.anyio
async def test_terminated_agent_cannot_execute(
    valid_dispatch_config: AgentConfig,
    sample_context_dict: dict[str, Any]
) -> None:
    agent = DispatchAgent(config=valid_dispatch_config)
    await agent.setup()
    await agent.teardown()
    assert agent.state == AgentState.TERMINATED

    with pytest.raises(AgentLifecycleError):
        await agent.execute(sample_context_dict)


# ==========================================================
# Deterministic Timeout Tests (Correction 7 & 8)
# ==========================================================

@pytest.mark.anyio
async def test_lifecycle_timeout_deterministic(sample_context_dict: dict[str, Any]) -> None:
    started_event = threading.Event()
    release_event = threading.Event()

    class DeterministicBlockingOrchestrator:
        def __init__(self) -> None:
            self.calls_count = 0

        def execute(self, task: AITask, context: dict, response_schema: Any) -> Any:
            self.calls_count += 1
            started_event.set()
            if not release_event.wait(timeout=5.0):
                pass
            return DispatchDecision(
                action="complete_assignment",
                job_id=101,
                technician_id=12,
                status="ACCEPTED",
                confidence=0.9,
                reason="Done successfully"
            )

    timeout_config = AgentConfig(
        agent_type=AITask.DISPATCH,
        tenant_id="tenant-123",
        timeout_seconds=0.01,
        enabled=True,
    )
    orch = DeterministicBlockingOrchestrator()
    agent = DispatchAgent(config=timeout_config, orchestrator=orch)  # type: ignore
    await agent.setup()

    pool = AgentPool()
    try:
        async with AgentLifecycle(agent=agent, pool=pool) as lifecycle:
            task = asyncio.create_task(lifecycle.execute(sample_context_dict))
            
            # Bounded wait instead of loops (Correction 7)
            started = await asyncio.wait_for(
                asyncio.to_thread(started_event.wait),
                timeout=1.0,
            )
            assert started is True

            result = await task
            assert result.status == AgentResultStatus.TIMEOUT
            assert agent.state == AgentState.ERROR
            assert orch.calls_count == 1
    finally:
        release_event.set()

    assert agent.state == AgentState.TERMINATED
    assert await pool.count() == 0


@pytest.mark.anyio
async def test_blocking_orchestrator_event_loop_responsiveness(sample_context_dict: dict[str, Any], valid_dispatch_config: AgentConfig) -> None:
    started_event = threading.Event()
    release_event = threading.Event()

    class ResponsiveOrchestrator:
        def __init__(self) -> None:
            self.calls_count = 0

        def execute(self, task: AITask, context: dict, response_schema: Any) -> Any:
            self.calls_count += 1
            started_event.set()
            if not release_event.wait(timeout=5.0):
                pass
            return DispatchDecision(
                action="complete_assignment",
                job_id=101,
                technician_id=12,
                status="ACCEPTED",
                confidence=0.9,
                reason="Done successfully"
            )

    orch = ResponsiveOrchestrator()
    agent = DispatchAgent(config=valid_dispatch_config, orchestrator=orch)  # type: ignore
    await agent.setup()

    try:
        task = asyncio.create_task(agent.execute(sample_context_dict))
        
        # Bounded wait instead of loop (Correction 7)
        started = await asyncio.wait_for(
            asyncio.to_thread(started_event.wait),
            timeout=1.0,
        )
        assert started is True

        # Verify loop responsiveness deterministically (Correction 8)
        loop_event = asyncio.Event()
        async def trigger_event():
            await asyncio.sleep(0.01)
            loop_event.set()

        asyncio.create_task(trigger_event())
        await asyncio.wait_for(loop_event.wait(), timeout=0.5)
        assert loop_event.is_set()

        release_event.set()
        await task
    finally:
        release_event.set()


# ==========================================================
# DispatchAgent Database Construct tests (Correction 8)
# ==========================================================

def test_dispatch_agent_no_database_involvement(valid_dispatch_config: AgentConfig, sample_decision: DispatchDecision) -> None:
    with patch("app.services.ai.FieldOpsAI.repositories.job_repository.JobRepository") as mock_job_repo_cls, \
         patch("app.services.ai.FieldOpsAI.repositories.technician_repository.TechnicianRepository") as mock_tech_repo_cls, \
         patch("app.services.ai.FieldOpsAI.repositories.job_assignment_repository.JobAssignmentRepository") as mock_assign_repo_cls:

        orch = MockOrchestrator(sample_decision)
        agent = DispatchAgent(config=valid_dispatch_config, orchestrator=orch)  # type: ignore

        assert not hasattr(agent, "job_repository")
        assert not hasattr(agent, "technician_repository")
        assert not hasattr(agent, "assignment_repository")

        agent.dispatch(DispatchContext.model_validate({
            "tenant_id": "tenant-123",
            "job": {"id": 101, "customer_name": "Acme", "location": "D", "priority": "H", "service_type": "HVAC", "required_skill": "HVAC", "status": "QUEUED"},
            "current_technician": {"technician_id": 12, "technician_name": "John", "skills": "HVAC", "location": "D", "status": "A", "current_jobs": 0, "max_jobs": 3, "tenant_id": "tenant-123"},
            "event": "TECHNICIAN_ACCEPTED"
        }))

        mock_job_repo_cls.assert_not_called()
        mock_tech_repo_cls.assert_not_called()
        mock_assign_repo_cls.assert_not_called()
        assert orch.calls_count == 1


# ==========================================================
# Hardened Sync Adapter Compatibility Tests (Correction 10)
# ==========================================================

def test_dispatch_agent_sync_dispatch_outside_event_loop(valid_dispatch_config: AgentConfig, sample_decision: DispatchDecision, sample_context_dict: dict[str, Any]) -> None:
    orch = MockOrchestrator(sample_decision)
    agent = DispatchAgent(config=valid_dispatch_config, orchestrator=orch)  # type: ignore

    context = DispatchContext.model_validate(sample_context_dict)
    res = agent.dispatch(context)
    assert res == sample_decision
    assert orch.calls_count == 1


def test_dispatch_agent_sync_dispatch_already_setup(valid_dispatch_config: AgentConfig, sample_decision: DispatchDecision, sample_context_dict: dict[str, Any]) -> None:
    orch = MockOrchestrator(sample_decision)
    agent = DispatchAgent(config=valid_dispatch_config, orchestrator=orch)  # type: ignore
    asyncio.run(agent.setup())

    context = DispatchContext.model_validate(sample_context_dict)
    res = agent.dispatch(context)
    assert res == sample_decision
    assert orch.calls_count == 1


@pytest.mark.anyio
async def test_dispatch_agent_sync_dispatch_rejects_active_loop(valid_dispatch_config: AgentConfig, sample_context_dict: dict[str, Any]) -> None:
    agent = DispatchAgent(config=valid_dispatch_config)
    context = DispatchContext.model_validate(sample_context_dict)

    with pytest.raises(RuntimeError) as exc:
        agent.dispatch(context)
    assert "dispatch() cannot be called from an active event loop" in str(exc.value)


def test_dispatch_service_sync_dispatch_outside_event_loop(valid_dispatch_config: AgentConfig, sample_decision: DispatchDecision) -> None:
    db = MagicMock()
    mock_job_repo = MagicMock()
    mock_job_repo.get_by_id.return_value = FakeJob(101, "tenant-123", "Acme", "D", "H", "HVAC", "HVAC", "QUEUED")

    mock_tech_repo = MagicMock()
    mock_tech = FakeTechnician(12, "John", "HVAC", "D", "AVAILABLE", 0, 3)
    mock_tech_repo.get_by_id.return_value = mock_tech
    mock_tech_repo.to_ai_dict.return_value = {"technician_id": 12}

    mock_assignment_repo = MagicMock()
    mock_assignment = JobAssignment(job_id=101, technician_id=12, rank=1, status="PENDING", is_current=True)
    mock_assignment_repo.get_current_candidate.return_value = mock_assignment
    mock_assignment_repo.get_rejected_technician_ids.return_value = []
    mock_assignment_repo.get_remaining_candidates.return_value = []

    mock_config_manager = MagicMock()
    mock_config_manager.resolve.return_value = valid_dispatch_config

    orch = MockOrchestrator(sample_decision)

    def agent_factory(config, orchestrator):
        return DispatchAgent(config=config, orchestrator=orch)  # type: ignore

    service = DispatchService(
        db=db,
        config_manager=mock_config_manager,
        agent_factory=agent_factory,
    )
    service.job_repository = mock_job_repo
    service.technician_repository = mock_tech_repo
    service.assignment_repository = mock_assignment_repo

    res = service.dispatch(101, "TECHNICIAN_ACCEPTED")
    assert res == sample_decision
    assert orch.calls_count == 1


@pytest.mark.anyio
async def test_dispatch_service_sync_dispatch_rejects_active_loop() -> None:
    service = DispatchService(db=MagicMock())
    with pytest.raises(RuntimeError) as exc:
        service.dispatch(101, "TECHNICIAN_ACCEPTED")
    assert "DispatchService.dispatch() cannot be called from an active event loop" in str(exc.value)


# ==========================================================
# DispatchService Hardening & Binding Tests
# ==========================================================

@pytest.mark.anyio
async def test_dispatch_service_binds_job_and_technician_identities(valid_dispatch_config: AgentConfig, sample_decision: DispatchDecision) -> None:
    db = MagicMock()
    mock_job_repo = MagicMock()
    mock_job = FakeJob(101, "tenant-123", "Acme", "D", "H", "HVAC", "HVAC", "QUEUED")
    mock_job_repo.get_by_id.return_value = mock_job

    mock_tech_repo = MagicMock()
    mock_tech = FakeTechnician(12, "John", "HVAC", "D", "AVAILABLE", 0, 3)
    mock_tech_repo.get_by_id.return_value = mock_tech
    mock_tech_repo.to_ai_dict.return_value = {"technician_id": 12}

    mock_assignment_repo = MagicMock()
    mock_assignment = JobAssignment(job_id=101, technician_id=12, rank=1, status="PENDING", is_current=True)
    mock_assignment_repo.get_current_candidate.return_value = mock_assignment
    mock_assignment_repo.get_rejected_technician_ids.return_value = []
    mock_assignment_repo.get_remaining_candidates.return_value = []

    mock_config_manager = MagicMock()
    mock_config_manager.resolve.return_value = valid_dispatch_config

    orch = MockOrchestrator(sample_decision)
    service = DispatchService(
        db=db,
        config_manager=mock_config_manager,
        agent_factory=lambda config, orchestrator: DispatchAgent(config=config, orchestrator=orch),  # type: ignore
    )
    service.job_repository = mock_job_repo
    service.technician_repository = mock_tech_repo
    service.assignment_repository = mock_assignment_repo

    # 1. Wrong Job ID from AI
    bad_job_decision = DispatchDecision(
        action="complete_assignment",
        job_id=999,  # Mismatched job ID
        technician_id=12,
        status="ACCEPTED",
        confidence=0.9,
        reason="Mismatched job ID"
    )
    orch.response_decision = bad_job_decision
    with pytest.raises(RuntimeError) as exc:
        await service.dispatch_async(101, "TECHNICIAN_ACCEPTED")
    assert "different job" in str(exc.value)
    assert_zero_side_effects(mock_job_repo, mock_tech_repo, mock_assignment_repo)

    # 2. Wrong Technician ID from AI
    bad_tech_decision = DispatchDecision(
        action="complete_assignment",
        job_id=101,
        technician_id=999,  # Mismatched technician ID
        status="ACCEPTED",
        confidence=0.9,
        reason="Mismatched tech ID"
    )
    orch.response_decision = bad_tech_decision
    with pytest.raises(RuntimeError) as exc:
        await service.dispatch_async(101, "TECHNICIAN_ACCEPTED")
    assert "different technician" in str(exc.value)
    assert_zero_side_effects(mock_job_repo, mock_tech_repo, mock_assignment_repo)

    assert orch.calls_count == 2


@pytest.mark.anyio
async def test_dispatch_service_cross_tenant_isolation_hardened() -> None:
    db = MagicMock()
    mock_job_repo = MagicMock()
    mock_tech_repo = MagicMock()
    mock_assignment_repo = MagicMock()

    # Job A (Tenant A, job 101)
    job_a = FakeJob(101, "tenant-a", "Acme", "0,0", "HIGH", "HVAC", "HVAC", "QUEUED")
    # Job B (Tenant B, job 102)
    job_b = FakeJob(102, "tenant-b", "Corp", "0,0", "HIGH", "HVAC", "HVAC", "QUEUED")

    mock_tech = FakeTechnician(12, "John Doe", "HVAC", "0,0", "AVAILABLE", 0, 3)
    mock_tech.tenant_id = "tenant-a"
    mock_tech_repo.get_by_id.side_effect = lambda tid: mock_tech if tid == 12 else None
    mock_tech_repo.to_ai_dict.return_value = {
        "technician_id": 12, "technician_name": "John Doe", "skills": "HVAC", "location": "0,0", "status": "AVAILABLE", "current_jobs": 0, "max_jobs": 3
    }

    assignment_a = JobAssignment(job_id=101, technician_id=12, rank=1, status="PENDING", is_current=True)
    assignment_b = JobAssignment(job_id=102, technician_id=12, rank=1, status="PENDING", is_current=True)

    mock_assignment_repo.get_current_candidate.side_effect = lambda jid: assignment_a if jid == 101 else assignment_b
    mock_assignment_repo.get_rejected_technician_ids.return_value = []
    mock_assignment_repo.get_remaining_candidates.return_value = []

    mock_config_manager = MagicMock()
    mock_config_manager.resolve.side_effect = lambda agent_type, tenant_id: AgentConfig(
        agent_type=AITask.DISPATCH, tenant_id=tenant_id, enabled=True
    )

    decision_a = DispatchDecision(
        action="complete_assignment",
        job_id=101,
        technician_id=12,
        status="ACCEPTED",
        confidence=0.9,
        reason="Accept job 101"
    )
    decision_b = DispatchDecision(
        action="complete_assignment",
        job_id=102,
        technician_id=12,
        status="ACCEPTED",
        confidence=0.9,
        reason="Accept job 102"
    )

    # Dictionary mapping config tenant to MockOrchestrator
    orch_dict = {
        "tenant-a": MockOrchestrator(decision_a),
        "tenant-b": MockOrchestrator(decision_b),
    }

    fresh_agents = []
    def agent_factory(config, orchestrator):
        orch = orch_dict.get(config.tenant_id)
        a = DispatchAgent(config=config, orchestrator=orch)  # type: ignore
        fresh_agents.append(a)
        return a

    service = DispatchService(
        db=db,
        config_manager=mock_config_manager,
        agent_factory=agent_factory,
    )
    service.job_repository = mock_job_repo
    service.technician_repository = mock_tech_repo
    service.assignment_repository = mock_assignment_repo

    # 1. Run for Tenant A
    mock_job_repo.get_by_id.return_value = job_a
    res_a = await service.dispatch_async(job_id=101, event="TECHNICIAN_ACCEPTED")
    assert res_a == decision_a

    # 2. Run for Tenant B (reconfigure tech tenant identity)
    mock_tech.tenant_id = "tenant-b"
    mock_job_repo.get_by_id.return_value = job_b
    res_b = await service.dispatch_async(job_id=102, event="TECHNICIAN_ACCEPTED")
    assert res_b == decision_b

    assert len(fresh_agents) == 2
    mock_config_manager.resolve.assert_any_call(agent_type=AITask.DISPATCH, tenant_id="tenant-a")
    mock_config_manager.resolve.assert_any_call(agent_type=AITask.DISPATCH, tenant_id="tenant-b")

    # 3. Decision for job 101 during job 102 execution must be rejected
    mock_tech.tenant_id = "tenant-b"
    orch_dict["tenant-b"] = MockOrchestrator(decision_a)
    mock_job_repo.reset_mock()
    mock_tech_repo.reset_mock()
    mock_assignment_repo.reset_mock()
    with pytest.raises(RuntimeError) as exc:
        await service.dispatch_async(job_id=102, event="TECHNICIAN_ACCEPTED")
    assert "different job" in str(exc.value)
    assert_zero_side_effects(mock_job_repo, mock_tech_repo, mock_assignment_repo)


@pytest.mark.anyio
async def test_dispatch_service_cross_tenant_mismatch_rejected(valid_dispatch_config: AgentConfig) -> None:
    db = MagicMock()
    mock_job_repo = MagicMock()
    mock_job = FakeJob(101, "tenant-123", "Acme", "D", "H", "HVAC", "HVAC", "QUEUED")
    mock_job_repo.get_by_id.return_value = mock_job

    mock_tech_repo = MagicMock()
    mock_tech = FakeTechnician(12, "John", "HVAC", "D", "AVAILABLE", 0, 3, tenant_id="tenant-different")
    mock_tech_repo.get_by_id.return_value = mock_tech

    mock_assignment_repo = MagicMock()
    mock_assignment = JobAssignment(job_id=101, technician_id=12, rank=1, status="PENDING", is_current=True)
    mock_assignment_repo.get_current_candidate.return_value = mock_assignment

    service = DispatchService(
        db=db,
        config_manager=MagicMock(),
    )
    service.job_repository = mock_job_repo
    service.technician_repository = mock_tech_repo
    service.assignment_repository = mock_assignment_repo

    with pytest.raises(ValueError) as exc:
        await service.dispatch_async(101, "TECHNICIAN_ACCEPTED")
    assert "Cross-tenant" in str(exc.value)
    assert_zero_side_effects(mock_job_repo, mock_tech_repo, mock_assignment_repo)


@pytest.mark.anyio
async def test_dispatch_service_cross_tenant_candidate_mismatch_rejected(valid_dispatch_config: AgentConfig) -> None:
    db = MagicMock()
    mock_job_repo = MagicMock()
    mock_job = FakeJob(101, "tenant-123", "Acme", "D", "H", "HVAC", "HVAC", "QUEUED")
    mock_job_repo.get_by_id.return_value = mock_job

    mock_tech_repo = MagicMock()
    mock_tech = FakeTechnician(12, "John", "HVAC", "D", "AVAILABLE", 0, 3, tenant_id="tenant-123")
    mock_tech_b = FakeTechnician(13, "Bob", "HVAC", "D", "AVAILABLE", 0, 3, tenant_id="tenant-different")
    mock_tech_repo.get_by_id.side_effect = lambda tid: mock_tech if tid == 12 else mock_tech_b

    mock_assignment_repo = MagicMock()
    mock_assignment = JobAssignment(job_id=101, technician_id=12, rank=1, status="PENDING", is_current=True)
    mock_assignment_repo.get_current_candidate.return_value = mock_assignment

    mock_candidate_assign = MagicMock()
    mock_candidate_assign.job_id = 101
    mock_candidate_assign.technician_id = 13
    mock_assignment_repo.get_remaining_candidates.return_value = [mock_candidate_assign]

    service = DispatchService(
        db=db,
        config_manager=MagicMock(),
    )
    service.job_repository = mock_job_repo
    service.technician_repository = mock_tech_repo
    service.assignment_repository = mock_assignment_repo

    with pytest.raises(ValueError) as exc:
        await service.dispatch_async(101, "TECHNICIAN_ACCEPTED")
    assert "Cross-tenant" in str(exc.value)
    assert_zero_side_effects(mock_job_repo, mock_tech_repo, mock_assignment_repo)


@pytest.mark.anyio
async def test_dispatch_service_assignment_job_mismatch_rejected() -> None:
    db = MagicMock()
    mock_job_repo = MagicMock()
    mock_job = FakeJob(101, "tenant-123", "Acme", "D", "H", "HVAC", "HVAC", "QUEUED")
    mock_job_repo.get_by_id.return_value = mock_job

    mock_assignment_repo = MagicMock()
    # Assignment belongs to job 999
    mock_assignment = JobAssignment(job_id=999, technician_id=12, rank=1, status="PENDING", is_current=True)
    mock_assignment_repo.get_current_candidate.return_value = mock_assignment

    service = DispatchService(db=db)
    service.job_repository = mock_job_repo
    service.assignment_repository = mock_assignment_repo

    with pytest.raises(ValueError) as exc:
        await service.dispatch_async(101, "TECHNICIAN_ACCEPTED")
    assert "Mismatched job ID in assignment record" in str(exc.value)
    assert_zero_side_effects(mock_job_repo, MagicMock(), mock_assignment_repo)


# ==========================================================
# Consistency Validation Tests (Correction 2 & 3)
# ==========================================================

@pytest.mark.anyio
async def test_dispatch_service_decision_contract_validator(valid_dispatch_config: AgentConfig) -> None:
    db = MagicMock()
    mock_job_repo = MagicMock()
    mock_job = FakeJob(101, "tenant-123", "Acme", "D", "H", "HVAC", "HVAC", "QUEUED")
    mock_job_repo.get_by_id.return_value = mock_job

    mock_tech_repo = MagicMock()
    mock_tech = FakeTechnician(12, "John", "HVAC", "D", "AVAILABLE", 0, 3)
    mock_tech_repo.get_by_id.return_value = mock_tech
    mock_tech_repo.to_ai_dict.return_value = {"technician_id": 12}

    mock_assignment_repo = MagicMock()
    mock_assignment = JobAssignment(job_id=101, technician_id=12, rank=1, status="PENDING", is_current=True)
    mock_assignment_repo.get_current_candidate.return_value = mock_assignment
    mock_assignment_repo.get_rejected_technician_ids.return_value = []
    mock_assignment_repo.get_remaining_candidates.return_value = []

    mock_config_manager = MagicMock()
    mock_config_manager.resolve.return_value = valid_dispatch_config

    decision = DispatchDecision(
        action="complete_assignment",
        job_id=101,
        technician_id=12,
        status="ACCEPTED",
        confidence=0.9,
        reason="Accepted event successfully"
    )
    orch = MockOrchestrator(decision)
    service = DispatchService(
        db=db,
        config_manager=mock_config_manager,
        agent_factory=lambda config, orchestrator: DispatchAgent(config=config, orchestrator=orch),  # type: ignore
    )
    service.job_repository = mock_job_repo
    service.technician_repository = mock_tech_repo
    service.assignment_repository = mock_assignment_repo

    # 1. accepted event with rejected status -> reject
    orch.response_decision = DispatchDecision(
        action="complete_assignment",
        job_id=101,
        technician_id=12,
        status="REJECTED",
        confidence=0.9,
        reason="Mismatched status reasons"
    )
    with pytest.raises(RuntimeError) as exc:
        await service.dispatch_async(101, "TECHNICIAN_ACCEPTED")
    assert "status must be ACCEPTED" in str(exc.value)
    assert_zero_side_effects(mock_job_repo, mock_tech_repo, mock_assignment_repo)

    # 2. rejected event with accepted status -> reject
    orch.response_decision = DispatchDecision(
        action="assign_next_candidate",
        job_id=101,
        technician_id=12,
        status="ACCEPTED",
        confidence=0.9,
        reason="Mismatched status reasons"
    )
    with pytest.raises(RuntimeError) as exc:
        await service.dispatch_async(101, "TECHNICIAN_REJECTED")
    assert "status must be REJECTED" in str(exc.value)
    assert_zero_side_effects(mock_job_repo, mock_tech_repo, mock_assignment_repo)

    # 3. timeout event with accepted status -> reject
    orch.response_decision = DispatchDecision(
        action="assign_next_candidate",
        job_id=101,
        technician_id=12,
        status="ACCEPTED",
        confidence=0.9,
        reason="Mismatched status reasons"
    )
    with pytest.raises(RuntimeError) as exc:
        await service.dispatch_async(101, "TECHNICIAN_TIMEOUT")
    assert "status must be TIMEOUT" in str(exc.value)
    assert_zero_side_effects(mock_job_repo, mock_tech_repo, mock_assignment_repo)

    # 4. assign_next_candidate incompatible status -> reject
    orch.response_decision = DispatchDecision(
        action="assign_next_candidate",
        job_id=101,
        technician_id=12,
        status="ACCEPTED",
        confidence=0.9,
        reason="Wrong action status reasons"
    )
    with pytest.raises(RuntimeError) as exc:
        await service.dispatch_async(101, "TECHNICIAN_ACCEPTED")
    assert_zero_side_effects(mock_job_repo, mock_tech_repo, mock_assignment_repo)

    # 5. assign_next_candidate when NO remaining candidates exist -> reject
    orch.response_decision = DispatchDecision(
        action="assign_next_candidate",
        job_id=101,
        technician_id=12,
        status="REJECTED",
        confidence=0.9,
        reason="Wrong action rank reasons"
    )
    mock_assignment_repo.get_remaining_candidates.return_value = []
    with pytest.raises(RuntimeError) as exc:
        await service.dispatch_async(101, "TECHNICIAN_REJECTED")
    assert "no remaining candidates exist" in str(exc.value)
    assert_zero_side_effects(mock_job_repo, mock_tech_repo, mock_assignment_repo)

    # 6. request_replanning when remaining candidates DO exist -> reject
    orch.response_decision = DispatchDecision(
        action="request_replanning",
        job_id=101,
        technician_id=12,
        status="REJECTED",
        confidence=0.9,
        reason="Wrong replan action reasons"
    )
    mock_candidate = JobAssignment(job_id=101, technician_id=13, rank=2, status="PENDING")
    mock_assignment_repo.get_remaining_candidates.return_value = [mock_candidate]
    with pytest.raises(RuntimeError) as exc:
        await service.dispatch_async(101, "TECHNICIAN_REJECTED")
    assert "remaining candidates exist" in str(exc.value)
    assert_zero_side_effects(mock_job_repo, mock_tech_repo, mock_assignment_repo)


@pytest.mark.anyio
async def test_dispatch_service_manual_review_performs_no_side_effects(valid_dispatch_config: AgentConfig) -> None:
    db = MagicMock()
    mock_job_repo = MagicMock()
    mock_job = FakeJob(101, "tenant-123", "Acme", "D", "H", "HVAC", "HVAC", "QUEUED")
    mock_job_repo.get_by_id.return_value = mock_job

    mock_tech_repo = MagicMock()
    mock_tech = FakeTechnician(12, "John", "HVAC", "D", "AVAILABLE", 0, 3)
    mock_tech_repo.get_by_id.return_value = mock_tech
    mock_tech_repo.to_ai_dict.return_value = {"technician_id": 12}

    mock_assignment_repo = MagicMock()
    mock_assignment = JobAssignment(job_id=101, technician_id=12, rank=1, status="PENDING", is_current=True)
    mock_assignment_repo.get_current_candidate.return_value = mock_assignment
    mock_assignment_repo.get_rejected_technician_ids.return_value = []
    mock_assignment_repo.get_remaining_candidates.return_value = []

    mock_config_manager = MagicMock()
    mock_config_manager.resolve.return_value = valid_dispatch_config

    decision = DispatchDecision(
        action="manual_review",
        job_id=101,
        technician_id=12,
        status="ACCEPTED",
        confidence=0.9,
        reason="Manual review requested successfully"
    )
    orch = MockOrchestrator(decision)
    service = DispatchService(
        db=db,
        config_manager=mock_config_manager,
        agent_factory=lambda config, orchestrator: DispatchAgent(config=config, orchestrator=orch),  # type: ignore
    )
    service.job_repository = mock_job_repo
    service.technician_repository = mock_tech_repo
    service.assignment_repository = mock_assignment_repo

    res = await service.dispatch_async(101, "TECHNICIAN_ACCEPTED")
    assert res == decision

    # Verify no side effects or commits ran (Correction 6)
    assert_zero_side_effects(mock_job_repo, mock_tech_repo, mock_assignment_repo)


@pytest.mark.anyio
async def test_dispatch_service_remaining_candidates_called_via_repo(valid_dispatch_config: AgentConfig, sample_decision: DispatchDecision) -> None:
    db = MagicMock()
    mock_job_repo = MagicMock()
    mock_job = FakeJob(101, "tenant-123", "Acme", "D", "H", "HVAC", "HVAC", "QUEUED")
    mock_job_repo.get_by_id.return_value = mock_job

    mock_tech_repo = MagicMock()
    mock_tech = FakeTechnician(12, "John", "HVAC", "D", "AVAILABLE", 0, 3)
    mock_tech_repo.get_by_id.return_value = mock_tech
    mock_tech_repo.to_ai_dict.return_value = {"technician_id": 12}

    mock_assignment_repo = MagicMock()
    mock_assignment = JobAssignment(job_id=101, technician_id=12, rank=1, status="PENDING", is_current=True)
    mock_assignment_repo.get_current_candidate.return_value = mock_assignment
    mock_assignment_repo.get_rejected_technician_ids.return_value = []
    
    mock_config_manager = MagicMock()
    mock_config_manager.resolve.return_value = valid_dispatch_config

    orch = MockOrchestrator(sample_decision)
    service = DispatchService(
        db=db,
        config_manager=mock_config_manager,
        agent_factory=lambda config, orchestrator: DispatchAgent(config=config, orchestrator=orch),  # type: ignore
    )
    service.job_repository = mock_job_repo
    service.technician_repository = mock_tech_repo
    service.assignment_repository = mock_assignment_repo

    await service.dispatch_async(101, "TECHNICIAN_ACCEPTED")

    # Assert get_remaining_candidates was called
    mock_assignment_repo.get_remaining_candidates.assert_called_once_with(job_id=101, after_rank=1)
    # Assert db.query was not called directly in the service
    db.query.assert_not_called()


# ==========================================================
# Legacy direct helper tests (Correction 11)
# ==========================================================

def test_redispatch_helper_works() -> None:
    from app.services.dispatch_agent import DispatchAgent as HelperDispatchAgent
    res = HelperDispatchAgent.trigger_redispatch("101")
    assert res["triggered"] is True




def test_job_assignment_repository_get_remaining_candidates() -> None:
    db = MagicMock()
    repo = JobAssignmentRepository(db)

    mock_query = db.query.return_value
    mock_filter = mock_query.filter.return_value
    mock_order = mock_filter.order_by.return_value
    mock_order.all.return_value = ["dummy_assignment"]

    result = repo.get_remaining_candidates(job_id=101, after_rank=2)

    assert result == ["dummy_assignment"]

    db.query.assert_called_once_with(JobAssignment)
    mock_query.filter.assert_called_once()
    mock_filter.order_by.assert_called_once()

    # Verify ordering by JobAssignment.rank in descending order.
    order_by_args = mock_filter.order_by.call_args.args
    assert len(order_by_args) == 1
    assert order_by_args[0].element == JobAssignment.rank
    assert order_by_args[0].modifier.__name__ == "asc_op"

    db.commit.assert_not_called()



# ==========================================================
# Additional Path and Error Handling Tests
# ==========================================================

@pytest.mark.anyio
async def test_dispatch_service_job_not_found_raises_value_error() -> None:
    service = DispatchService(db=MagicMock())
    service.job_repository = MagicMock()
    service.job_repository.get_by_id.return_value = None

    with pytest.raises(ValueError) as exc:
        await service.dispatch_async(999, "TECHNICIAN_ACCEPTED")
    assert "was not found" in str(exc.value)


@pytest.mark.anyio
async def test_dispatch_service_job_missing_tenant_id_raises_value_error() -> None:
    service = DispatchService(db=MagicMock())
    service.job_repository = MagicMock()
    service.job_repository.get_by_id.return_value = FakeJob(101, "", "Acme", "D", "H", "HVAC", "HVAC", "QUEUED")

    with pytest.raises(ValueError) as exc:
        await service.dispatch_async(101, "TECHNICIAN_ACCEPTED")
    assert "does not have a tenant_id" in str(exc.value)


@pytest.mark.anyio
async def test_dispatch_service_assignment_not_found_raises_value_error() -> None:
    service = DispatchService(db=MagicMock())
    service.job_repository = MagicMock()
    service.job_repository.get_by_id.return_value = FakeJob(101, "tenant-123", "Acme", "D", "H", "HVAC", "HVAC", "QUEUED")
    service.assignment_repository = MagicMock()
    service.assignment_repository.get_current_candidate.return_value = None

    with pytest.raises(ValueError) as exc:
        await service.dispatch_async(101, "TECHNICIAN_ACCEPTED")
    assert "No current technician assignment found" in str(exc.value)


@pytest.mark.anyio
async def test_dispatch_service_tech_not_found_raises_value_error() -> None:
    service = DispatchService(db=MagicMock())
    service.job_repository = MagicMock()
    service.job_repository.get_by_id.return_value = FakeJob(101, "tenant-123", "Acme", "D", "H", "HVAC", "HVAC", "QUEUED")
    service.assignment_repository = MagicMock()
    service.assignment_repository.get_current_candidate.return_value = JobAssignment(job_id=101, technician_id=12, rank=1, status="PENDING")
    service.technician_repository = MagicMock()
    service.technician_repository.get_by_id.return_value = None

    with pytest.raises(ValueError) as exc:
        await service.dispatch_async(101, "TECHNICIAN_ACCEPTED")
    assert "was not found" in str(exc.value)


@pytest.mark.anyio
async def test_dispatch_service_default_dependencies(valid_dispatch_config: AgentConfig, sample_decision: DispatchDecision) -> None:
    db = MagicMock()
    # Mock repositories
    mock_job_repo = MagicMock()
    mock_job_repo.get_by_id.return_value = FakeJob(101, "tenant-123", "Acme", "D", "H", "HVAC", "HVAC", "QUEUED")
    
    mock_tech_repo = MagicMock()
    mock_tech_repo.get_by_id.return_value = FakeTechnician(12, "John", "HVAC", "D", "AVAILABLE", 0, 3)
    mock_tech_repo.to_ai_dict.return_value = {"technician_id": 12}
    
    mock_assign_repo = MagicMock()
    mock_assign_repo.get_current_candidate.return_value = JobAssignment(job_id=101, technician_id=12, rank=1, status="PENDING")
    mock_assign_repo.get_rejected_technician_ids.return_value = []
    mock_assign_repo.get_remaining_candidates.return_value = []

    # ConfigManager setup
    mock_manager = MagicMock()
    mock_manager.resolve.return_value = valid_dispatch_config

    orch = MockOrchestrator(sample_decision)

    # Use patch to substitute config manager resolve inside resolution block
    with patch("app.services.ai.FieldOpsAI.config.agent_config_manager.AgentConfigManager.resolve", return_value=valid_dispatch_config), \
         patch("app.services.ai.FieldOpsAI.agents.dispatch_agent.DispatchAgent.run", return_value=sample_decision):
        
        service = DispatchService(db=db, orchestrator=orch) # type: ignore
        service.job_repository = mock_job_repo
        service.technician_repository = mock_tech_repo
        service.assignment_repository = mock_assign_repo
        
        res = await service.dispatch_async(101, "TECHNICIAN_ACCEPTED")
        assert res == sample_decision


@pytest.mark.anyio
async def test_dispatch_service_agent_failure_raises_runtime_error(valid_dispatch_config: AgentConfig) -> None:
    db = MagicMock()
    mock_job_repo = MagicMock()
    mock_job_repo.get_by_id.return_value = FakeJob(101, "tenant-123", "Acme", "D", "H", "HVAC", "HVAC", "QUEUED")
    
    mock_tech_repo = MagicMock()
    mock_tech_repo.get_by_id.return_value = FakeTechnician(12, "John", "HVAC", "D", "AVAILABLE", 0, 3)
    mock_tech_repo.to_ai_dict.return_value = {"technician_id": 12}
    
    mock_assign_repo = MagicMock()
    mock_assign_repo.get_current_candidate.return_value = JobAssignment(job_id=101, technician_id=12, rank=1, status="PENDING")
    mock_assign_repo.get_rejected_technician_ids.return_value = []
    mock_assign_repo.get_remaining_candidates.return_value = []

    mock_config_manager = MagicMock()
    mock_config_manager.resolve.return_value = valid_dispatch_config

    orch = FailingOrchestrator()
    service = DispatchService(
        db=db,
        config_manager=mock_config_manager,
        agent_factory=lambda config, orchestrator: DispatchAgent(config=config, orchestrator=orch), # type: ignore
    )
    service.job_repository = mock_job_repo
    service.technician_repository = mock_tech_repo
    service.assignment_repository = mock_assign_repo

    with pytest.raises(RuntimeError) as exc:
        await service.dispatch_async(101, "TECHNICIAN_ACCEPTED")
    assert "failed while generating a recommendation" in str(exc.value)
    assert_zero_side_effects(mock_job_repo, mock_tech_repo, mock_assign_repo)


@pytest.mark.anyio
async def test_dispatch_service_invalid_decision_type_raises_runtime_error(valid_dispatch_config: AgentConfig) -> None:
    db = MagicMock()
    mock_job_repo = MagicMock()
    mock_job_repo.get_by_id.return_value = FakeJob(101, "tenant-123", "Acme", "D", "H", "HVAC", "HVAC", "QUEUED")
    
    mock_tech_repo = MagicMock()
    mock_tech_repo.get_by_id.return_value = FakeTechnician(12, "John", "HVAC", "D", "AVAILABLE", 0, 3)
    mock_tech_repo.to_ai_dict.return_value = {"technician_id": 12}
    
    mock_assign_repo = MagicMock()
    mock_assign_repo.get_current_candidate.return_value = JobAssignment(job_id=101, technician_id=12, rank=1, status="PENDING")
    mock_assign_repo.get_rejected_technician_ids.return_value = []
    mock_assign_repo.get_remaining_candidates.return_value = []

    mock_config_manager = MagicMock()
    mock_config_manager.resolve.return_value = valid_dispatch_config

    class DummyDecision:
        def __init__(self) -> None:
            self.job_id = 101
            self.technician_id = 12
            self.action = "complete_assignment"
            self.status = "ACCEPTED"

    orch = MockOrchestrator(DummyDecision())
    service = DispatchService(
        db=db,
        config_manager=mock_config_manager,
        agent_factory=lambda config, orchestrator: DispatchAgent(config=config, orchestrator=orch), # type: ignore
    )
    service.job_repository = mock_job_repo
    service.technician_repository = mock_tech_repo
    service.assignment_repository = mock_assign_repo

    with pytest.raises(RuntimeError) as exc:
        await service.dispatch_async(101, "TECHNICIAN_ACCEPTED")
    assert "returned an invalid decision" in str(exc.value)
    assert_zero_side_effects(mock_job_repo, mock_tech_repo, mock_assign_repo)


# ==========================================================
# Side Effect Integration Tests
# ==========================================================

@pytest.mark.anyio
async def test_dispatch_service_side_effects_assign_next_candidate_rejected(valid_dispatch_config: AgentConfig) -> None:
    db = MagicMock()
    mock_job_repo = MagicMock()
    mock_job_repo.get_by_id.return_value = FakeJob(101, "tenant-123", "Acme", "D", "H", "HVAC", "HVAC", "QUEUED")
    mock_tech_repo = MagicMock()
    mock_tech_repo.get_by_id.return_value = FakeTechnician(12, "John", "HVAC", "D", "AVAILABLE", 0, 3)
    mock_tech_repo.to_ai_dict.return_value = {"technician_id": 12}
    
    mock_assign_repo = MagicMock()
    current_assignment = JobAssignment(job_id=101, technician_id=12, rank=1, status="PENDING")
    mock_assign_repo.get_current_candidate.return_value = current_assignment
    mock_assign_repo.get_rejected_technician_ids.return_value = []
    
    mock_candidate = JobAssignment(job_id=101, technician_id=13, rank=2, status="PENDING")
    mock_assign_repo.get_remaining_candidates.return_value = [mock_candidate]
    mock_assign_repo.promote_next_candidate.return_value = mock_candidate
    
    mock_config_manager = MagicMock()
    mock_config_manager.resolve.return_value = valid_dispatch_config

    decision = DispatchDecision(
        action="assign_next_candidate",
        job_id=101,
        technician_id=12,
        status="REJECTED",
        confidence=0.9,
        reason="Technician rejected successfully"
    )
    orch = MockOrchestrator(decision)
    service = DispatchService(
        db=db,
        config_manager=mock_config_manager,
        agent_factory=lambda config, orchestrator: DispatchAgent(config=config, orchestrator=orch), # type: ignore
    )
    service.job_repository = mock_job_repo
    service.technician_repository = mock_tech_repo
    service.assignment_repository = mock_assign_repo

    res = await service.dispatch_async(101, "TECHNICIAN_REJECTED")
    assert res == decision

    mock_assign_repo.mark_rejected.assert_called_once_with(current_assignment)
    mock_assign_repo.promote_next_candidate.assert_called_once_with(
        101,
        after_rank=1,
    )
    mock_assign_repo.save.assert_called_once()


@pytest.mark.anyio
async def test_dispatch_service_side_effects_assign_next_candidate_timeout(valid_dispatch_config: AgentConfig) -> None:
    db = MagicMock()
    mock_job_repo = MagicMock()
    mock_job_repo.get_by_id.return_value = FakeJob(101, "tenant-123", "Acme", "D", "H", "HVAC", "HVAC", "QUEUED")
    mock_tech_repo = MagicMock()
    mock_tech_repo.get_by_id.return_value = FakeTechnician(12, "John", "HVAC", "D", "AVAILABLE", 0, 3)
    mock_tech_repo.to_ai_dict.return_value = {"technician_id": 12}
    
    mock_assign_repo = MagicMock()
    current_assignment = JobAssignment(job_id=101, technician_id=12, rank=1, status="PENDING")
    mock_assign_repo.get_current_candidate.return_value = current_assignment
    mock_assign_repo.get_rejected_technician_ids.return_value = []
    
    mock_candidate = JobAssignment(job_id=101, technician_id=13, rank=2, status="PENDING")
    mock_assign_repo.get_remaining_candidates.return_value = [mock_candidate]
    mock_assign_repo.promote_next_candidate.return_value = mock_candidate
    
    mock_config_manager = MagicMock()
    mock_config_manager.resolve.return_value = valid_dispatch_config

    decision = DispatchDecision(
        action="assign_next_candidate",
        job_id=101,
        technician_id=12,
        status="TIMEOUT",
        confidence=0.9,
        reason="Technician timeout successfully"
    )
    orch = MockOrchestrator(decision)
    service = DispatchService(
        db=db,
        config_manager=mock_config_manager,
        agent_factory=lambda config, orchestrator: DispatchAgent(config=config, orchestrator=orch), # type: ignore
    )
    service.job_repository = mock_job_repo
    service.technician_repository = mock_tech_repo
    service.assignment_repository = mock_assign_repo

    res = await service.dispatch_async(101, "TECHNICIAN_TIMEOUT")
    assert res == decision

    mock_assign_repo.mark_timeout.assert_called_once_with(current_assignment)
    mock_assign_repo.promote_next_candidate.assert_called_once_with(
        101,
        after_rank=1,
    )
    mock_assign_repo.save.assert_called_once()


@pytest.mark.anyio
async def test_dispatch_service_side_effects_request_replanning_rejected(valid_dispatch_config: AgentConfig) -> None:
    db = MagicMock()
    mock_job_repo = MagicMock()
    mock_job_repo.get_by_id.return_value = FakeJob(101, "tenant-123", "Acme", "D", "H", "HVAC", "HVAC", "QUEUED")
    mock_tech_repo = MagicMock()
    mock_tech_repo.get_by_id.return_value = FakeTechnician(12, "John", "HVAC", "D", "AVAILABLE", 0, 3)
    mock_tech_repo.to_ai_dict.return_value = {"technician_id": 12}
    
    mock_assign_repo = MagicMock()
    current_assignment = JobAssignment(job_id=101, technician_id=12, rank=1, status="PENDING")
    mock_assign_repo.get_current_candidate.return_value = current_assignment
    mock_assign_repo.get_rejected_technician_ids.return_value = []
    mock_assign_repo.get_remaining_candidates.return_value = []
    
    mock_config_manager = MagicMock()
    mock_config_manager.resolve.return_value = valid_dispatch_config

    decision = DispatchDecision(
        action="request_replanning",
        job_id=101,
        technician_id=12,
        status="REJECTED",
        confidence=0.9,
        reason="Technician rejected successfully"
    )
    orch = MockOrchestrator(decision)
    service = DispatchService(
        db=db,
        config_manager=mock_config_manager,
        agent_factory=lambda config, orchestrator: DispatchAgent(config=config, orchestrator=orch), # type: ignore
    )
    service.job_repository = mock_job_repo
    service.technician_repository = mock_tech_repo
    service.assignment_repository = mock_assign_repo

    res = await service.dispatch_async(101, "TECHNICIAN_REJECTED")
    assert res == decision

    mock_assign_repo.mark_rejected.assert_called_once_with(current_assignment)
    mock_assign_repo.save.assert_called_once()


@pytest.mark.anyio
async def test_dispatch_service_side_effects_request_replanning_timeout(valid_dispatch_config: AgentConfig) -> None:
    db = MagicMock()
    mock_job_repo = MagicMock()
    mock_job_repo.get_by_id.return_value = FakeJob(101, "tenant-123", "Acme", "D", "H", "HVAC", "HVAC", "QUEUED")
    mock_tech_repo = MagicMock()
    mock_tech_repo.get_by_id.return_value = FakeTechnician(12, "John", "HVAC", "D", "AVAILABLE", 0, 3)
    mock_tech_repo.to_ai_dict.return_value = {"technician_id": 12}
    
    mock_assign_repo = MagicMock()
    current_assignment = JobAssignment(job_id=101, technician_id=12, rank=1, status="PENDING")
    mock_assign_repo.get_current_candidate.return_value = current_assignment
    mock_assign_repo.get_rejected_technician_ids.return_value = []
    mock_assign_repo.get_remaining_candidates.return_value = []
    
    mock_config_manager = MagicMock()
    mock_config_manager.resolve.return_value = valid_dispatch_config

    decision = DispatchDecision(
        action="request_replanning",
        job_id=101,
        technician_id=12,
        status="TIMEOUT",
        confidence=0.9,
        reason="Technician timeout successfully"
    )
    orch = MockOrchestrator(decision)
    service = DispatchService(
        db=db,
        config_manager=mock_config_manager,
        agent_factory=lambda config, orchestrator: DispatchAgent(config=config, orchestrator=orch), # type: ignore
    )
    service.job_repository = mock_job_repo
    service.technician_repository = mock_tech_repo
    service.assignment_repository = mock_assign_repo

    res = await service.dispatch_async(101, "TECHNICIAN_TIMEOUT")
    assert res == decision

    mock_assign_repo.mark_timeout.assert_called_once_with(current_assignment)
    mock_assign_repo.save.assert_called_once()


# ==========================================================
# New Hardening Tests (Corrections 2, 3, 4, 5, 6, 9)
# ==========================================================

@pytest.mark.anyio
async def test_dispatch_service_timeout(sample_context_dict: dict[str, Any]) -> None:
    started_event = threading.Event()
    release_event = threading.Event()

    class BlockingOrchestrator:
        def __init__(self) -> None:
            self.calls_count = 0

        def execute(self, task: AITask, context: dict, response_schema: Any) -> Any:
            self.calls_count += 1
            started_event.set()
            if not release_event.wait(timeout=5.0):
                pass
            return DispatchDecision(
                action="complete_assignment",
                job_id=101,
                technician_id=12,
                status="ACCEPTED",
                confidence=0.9,
                reason="Done successfully"
            )

    db = MagicMock()
    mock_job_repo = MagicMock()
    mock_job_repo.get_by_id.return_value = FakeJob(101, "tenant-123", "Acme", "D", "H", "HVAC", "HVAC", "QUEUED")
    mock_tech_repo = MagicMock()
    mock_tech_repo.get_by_id.return_value = FakeTechnician(12, "John", "HVAC", "D", "AVAILABLE", 0, 3)
    mock_tech_repo.to_ai_dict.return_value = {"technician_id": 12}
    mock_assign_repo = MagicMock()
    mock_assign_repo.get_current_candidate.return_value = JobAssignment(job_id=101, technician_id=12, rank=1, status="PENDING")
    mock_assign_repo.get_rejected_technician_ids.return_value = []
    mock_assign_repo.get_remaining_candidates.return_value = []

    timeout_config = AgentConfig(
        agent_type=AITask.DISPATCH,
        tenant_id="tenant-123",
        timeout_seconds=0.01,
        enabled=True,
    )
    
    mock_config_manager = MagicMock()
    mock_config_manager.resolve.return_value = timeout_config

    orch = BlockingOrchestrator()
    pool = AgentPool()
    
    service = DispatchService(
        db=db,
        config_manager=mock_config_manager,
        pool=pool,
        agent_factory=lambda config, orchestrator: DispatchAgent(config=config, orchestrator=orch), # type: ignore
    )
    service.job_repository = mock_job_repo
    service.technician_repository = mock_tech_repo
    service.assignment_repository = mock_assign_repo

    try:
        task = asyncio.create_task(service.dispatch_async(101, "TECHNICIAN_ACCEPTED"))
        started = await asyncio.wait_for(
            asyncio.to_thread(started_event.wait),
            timeout=1.0,
        )
        assert started is True

        with pytest.raises(RuntimeError) as exc:
            await task
        assert "failed while generating a recommendation" in str(exc.value)
        assert orch.calls_count == 1
    finally:
        release_event.set()

    assert service.agent.state == AgentState.TERMINATED
    assert await pool.count() == 0
    assert_zero_side_effects(mock_job_repo, mock_tech_repo, mock_assign_repo)


@pytest.mark.anyio
async def test_dispatch_service_technician_missing_tenant_id_raises_value_error() -> None:
    db = MagicMock()
    mock_job_repo = MagicMock()
    mock_job_repo.get_by_id.return_value = FakeJob(101, "tenant-123", "Acme", "D", "H", "HVAC", "HVAC", "QUEUED")
    mock_tech_repo = MagicMock()
    mock_tech = FakeTechnician(12, "John", "HVAC", "D", "AVAILABLE", 0, 3, tenant_id="")
    mock_tech_repo.get_by_id.return_value = mock_tech
    mock_assignment_repo = MagicMock()
    mock_assignment = JobAssignment(job_id=101, technician_id=12, rank=1, status="PENDING", is_current=True)
    mock_assignment_repo.get_current_candidate.return_value = mock_assignment

    service = DispatchService(db=db)
    service.job_repository = mock_job_repo
    service.technician_repository = mock_tech_repo
    service.assignment_repository = mock_assignment_repo

    with pytest.raises(ValueError) as exc:
        await service.dispatch_async(101, "TECHNICIAN_ACCEPTED")
    assert "missing a tenant ID" in str(exc.value)
    assert_zero_side_effects(mock_job_repo, mock_tech_repo, mock_assignment_repo)


@pytest.mark.anyio
async def test_dispatch_service_remaining_assignment_wrong_job_raises_value_error() -> None:
    db = MagicMock()
    mock_job_repo = MagicMock()
    mock_job_repo.get_by_id.return_value = FakeJob(101, "tenant-123", "Acme", "D", "H", "HVAC", "HVAC", "QUEUED")
    mock_tech_repo = MagicMock()
    mock_tech_repo.get_by_id.return_value = FakeTechnician(12, "John", "HVAC", "D", "AVAILABLE", 0, 3, tenant_id="tenant-123")
    
    mock_assignment_repo = MagicMock()
    mock_assignment = JobAssignment(job_id=101, technician_id=12, rank=1, status="PENDING", is_current=True)
    mock_assignment_repo.get_current_candidate.return_value = mock_assignment
    
    bad_candidate = JobAssignment(job_id=999, technician_id=13, rank=2, status="PENDING")
    mock_assignment_repo.get_remaining_candidates.return_value = [bad_candidate]

    service = DispatchService(db=db)
    service.job_repository = mock_job_repo
    service.technician_repository = mock_tech_repo
    service.assignment_repository = mock_assignment_repo

    with pytest.raises(ValueError) as exc:
        await service.dispatch_async(101, "TECHNICIAN_ACCEPTED")
    assert "belongs to another job" in str(exc.value)
    assert_zero_side_effects(mock_job_repo, mock_tech_repo, mock_assignment_repo)


@pytest.mark.anyio
async def test_dispatch_service_remaining_assignment_technician_missing_raises_value_error() -> None:
    db = MagicMock()
    mock_job_repo = MagicMock()
    mock_job_repo.get_by_id.return_value = FakeJob(101, "tenant-123", "Acme", "D", "H", "HVAC", "HVAC", "QUEUED")
    mock_tech_repo = MagicMock()
    mock_tech = FakeTechnician(12, "John", "HVAC", "D", "AVAILABLE", 0, 3, tenant_id="tenant-123")
    mock_tech_repo.get_by_id.side_effect = lambda tid: mock_tech if tid == 12 else None
    
    mock_assignment_repo = MagicMock()
    mock_assignment = JobAssignment(job_id=101, technician_id=12, rank=1, status="PENDING", is_current=True)
    mock_assignment_repo.get_current_candidate.return_value = mock_assignment
    
    candidate = JobAssignment(job_id=101, technician_id=13, rank=2, status="PENDING")
    mock_assignment_repo.get_remaining_candidates.return_value = [candidate]

    service = DispatchService(db=db)
    service.job_repository = mock_job_repo
    service.technician_repository = mock_tech_repo
    service.assignment_repository = mock_assignment_repo

    with pytest.raises(ValueError) as exc:
        await service.dispatch_async(101, "TECHNICIAN_ACCEPTED")
    assert "references an unavailable technician" in str(exc.value)
    assert_zero_side_effects(mock_job_repo, mock_tech_repo, mock_assignment_repo)


@pytest.mark.anyio
async def test_dispatch_service_manual_review_bypass_contract_check(valid_dispatch_config: AgentConfig) -> None:
    db = MagicMock()
    mock_job_repo = MagicMock()
    mock_job = FakeJob(101, "tenant-123", "Acme", "D", "H", "HVAC", "HVAC", "QUEUED")
    mock_job_repo.get_by_id.return_value = mock_job

    mock_tech_repo = MagicMock()
    mock_tech = FakeTechnician(12, "John", "HVAC", "D", "AVAILABLE", 0, 3)
    mock_tech_repo.get_by_id.return_value = mock_tech
    mock_tech_repo.to_ai_dict.return_value = {"technician_id": 12}

    mock_assignment_repo = MagicMock()
    mock_assignment = JobAssignment(job_id=101, technician_id=12, rank=1, status="PENDING", is_current=True)
    mock_assignment_repo.get_current_candidate.return_value = mock_assignment
    mock_assignment_repo.get_rejected_technician_ids.return_value = []
    mock_assignment_repo.get_remaining_candidates.return_value = []

    mock_config_manager = MagicMock()
    mock_config_manager.resolve.return_value = valid_dispatch_config

    # Manual review decision with status REJECTED on ACCEPTED event (inconsistent, but allowed to bypass)
    decision = DispatchDecision(
        action="manual_review",
        job_id=101,
        technician_id=12,
        status="REJECTED",
        confidence=0.9,
        reason="Manual review bypass test"
    )
    orch = MockOrchestrator(decision)
    service = DispatchService(
        db=db,
        config_manager=mock_config_manager,
        agent_factory=lambda config, orchestrator: DispatchAgent(config=config, orchestrator=orch), # type: ignore
    )
    service.job_repository = mock_job_repo
    service.technician_repository = mock_tech_repo
    service.assignment_repository = mock_assignment_repo

    res = await service.dispatch_async(101, "TECHNICIAN_ACCEPTED")
    assert res == decision
    assert_zero_side_effects(mock_job_repo, mock_tech_repo, mock_assignment_repo)


@pytest.mark.anyio
async def test_dispatch_service_unsupported_action_raises_runtime_error(valid_dispatch_config: AgentConfig) -> None:
    db = MagicMock()
    mock_job_repo = MagicMock()
    mock_job = FakeJob(101, "tenant-123", "Acme", "D", "H", "HVAC", "HVAC", "QUEUED")
    mock_job_repo.get_by_id.return_value = mock_job

    mock_tech_repo = MagicMock()
    mock_tech = FakeTechnician(12, "John", "HVAC", "D", "AVAILABLE", 0, 3)
    mock_tech_repo.get_by_id.return_value = mock_tech
    mock_tech_repo.to_ai_dict.return_value = {"technician_id": 12}

    mock_assignment_repo = MagicMock()
    mock_assignment = JobAssignment(job_id=101, technician_id=12, rank=1, status="PENDING", is_current=True)
    mock_assignment_repo.get_current_candidate.return_value = mock_assignment
    mock_assignment_repo.get_rejected_technician_ids.return_value = []
    mock_assignment_repo.get_remaining_candidates.return_value = []

    mock_config_manager = MagicMock()
    mock_config_manager.resolve.return_value = valid_dispatch_config

    decision = DispatchDecision(
        action="complete_assignment",
        job_id=101,
        technician_id=12,
        status="REJECTED",
        confidence=0.9,
        reason="Test unsupported action reasons"
    )
    decision.__dict__["action"] = "unsupported_action"

    orch = MockOrchestrator(decision)
    service = DispatchService(
        db=db,
        config_manager=mock_config_manager,
        agent_factory=lambda config, orchestrator: DispatchAgent(config=config, orchestrator=orch), # type: ignore
    )
    service.job_repository = mock_job_repo
    service.technician_repository = mock_tech_repo
    service.assignment_repository = mock_assignment_repo

    with pytest.raises(RuntimeError) as exc:
        await service.dispatch_async(101, "TECHNICIAN_REJECTED")
    assert "unsupported action" in str(exc.value)
    assert_zero_side_effects(mock_job_repo, mock_tech_repo, mock_assignment_repo)


@pytest.mark.anyio
async def test_dispatch_service_falsey_pool(valid_dispatch_config: AgentConfig, sample_decision: DispatchDecision) -> None:
    db = MagicMock()
    mock_job_repo = MagicMock()
    mock_job_repo.get_by_id.return_value = FakeJob(101, "tenant-123", "Acme", "D", "H", "HVAC", "HVAC", "QUEUED")
    mock_tech_repo = MagicMock()
    mock_tech_repo.get_by_id.return_value = FakeTechnician(12, "John", "HVAC", "D", "AVAILABLE", 0, 3)
    mock_tech_repo.to_ai_dict.return_value = {"technician_id": 12}
    mock_assign_repo = MagicMock()
    mock_assign_repo.get_current_candidate.return_value = JobAssignment(job_id=101, technician_id=12, rank=1, status="PENDING")
    mock_assign_repo.get_rejected_technician_ids.return_value = []
    mock_assign_repo.get_remaining_candidates.return_value = []
    
    mock_config_manager = MagicMock()
    mock_config_manager.resolve.return_value = valid_dispatch_config

    orch = MockOrchestrator(sample_decision)
    falsey_pool = FalseyAgentPool()

    service = DispatchService(
        db=db,
        config_manager=mock_config_manager,
        pool=falsey_pool,
        agent_factory=lambda config, orchestrator: DispatchAgent(config=config, orchestrator=orch), # type: ignore
    )
    service.job_repository = mock_job_repo
    service.technician_repository = mock_tech_repo
    service.assignment_repository = mock_assign_repo

    res = await service.dispatch_async(101, "TECHNICIAN_ACCEPTED")
    assert res == sample_decision
    assert service._pool is falsey_pool
    assert await falsey_pool.count() == 0


@pytest.mark.anyio
async def test_dispatch_service_falsey_config_manager(valid_dispatch_config: AgentConfig, sample_decision: DispatchDecision) -> None:
    class FalseyConfigManager(AgentConfigManager):
        def __bool__(self) -> bool:
            return False

    db = MagicMock()
    mock_job_repo = MagicMock()
    mock_job_repo.get_by_id.return_value = FakeJob(101, "tenant-123", "Acme", "D", "H", "HVAC", "HVAC", "QUEUED")
    mock_tech_repo = MagicMock()
    mock_tech_repo.get_by_id.return_value = FakeTechnician(12, "John", "HVAC", "D", "AVAILABLE", 0, 3)
    mock_tech_repo.to_ai_dict.return_value = {"technician_id": 12}
    mock_assign_repo = MagicMock()
    mock_assign_repo.get_current_candidate.return_value = JobAssignment(job_id=101, technician_id=12, rank=1, status="PENDING")
    mock_assign_repo.get_rejected_technician_ids.return_value = []
    mock_assign_repo.get_remaining_candidates.return_value = []

    falsey_mgr = FalseyConfigManager()
    falsey_mgr.resolve = MagicMock(return_value=valid_dispatch_config)

    orch = MockOrchestrator(sample_decision)

    service = DispatchService(
        db=db,
        config_manager=falsey_mgr,
        agent_factory=lambda config, orchestrator: DispatchAgent(config=config, orchestrator=orch), # type: ignore
    )
    service.job_repository = mock_job_repo
    service.technician_repository = mock_tech_repo
    service.assignment_repository = mock_assign_repo

    res = await service.dispatch_async(101, "TECHNICIAN_ACCEPTED")
    assert res == sample_decision
    assert service._config_manager is falsey_mgr
    falsey_mgr.resolve.assert_called_once_with(agent_type=AITask.DISPATCH, tenant_id="tenant-123")


@pytest.mark.anyio
async def test_dispatch_service_candidate_technician_missing_tenant_id_raises_value_error() -> None:
    db = MagicMock()
    mock_job_repo = MagicMock()
    mock_job_repo.get_by_id.return_value = FakeJob(101, "tenant-123", "Acme", "D", "H", "HVAC", "HVAC", "QUEUED")
    mock_tech_repo = MagicMock()
    mock_tech = FakeTechnician(12, "John", "HVAC", "D", "AVAILABLE", 0, 3, tenant_id="tenant-123")
    mock_tech_candidate = FakeTechnician(13, "Bob", "HVAC", "D", "AVAILABLE", 0, 3, tenant_id="")
    mock_tech_repo.get_by_id.side_effect = lambda tid: mock_tech if tid == 12 else mock_tech_candidate
    
    mock_assignment_repo = MagicMock()
    mock_assignment = JobAssignment(job_id=101, technician_id=12, rank=1, status="PENDING", is_current=True)
    mock_assignment_repo.get_current_candidate.return_value = mock_assignment
    
    candidate = JobAssignment(job_id=101, technician_id=13, rank=2, status="PENDING")
    mock_assignment_repo.get_remaining_candidates.return_value = [candidate]

    service = DispatchService(db=db)
    service.job_repository = mock_job_repo
    service.technician_repository = mock_tech_repo
    service.assignment_repository = mock_assignment_repo

    with pytest.raises(ValueError) as exc:
        await service.dispatch_async(101, "TECHNICIAN_ACCEPTED")
    assert "Technician in candidate pool is missing a tenant ID" in str(exc.value)
    assert_zero_side_effects(mock_job_repo, mock_tech_repo, mock_assignment_repo)

@pytest.mark.anyio
async def test_dispatch_service_rejected_event_cannot_complete_assignment(valid_dispatch_config: AgentConfig) -> None:
    db = MagicMock()
    mock_job_repo = MagicMock()
    mock_job_repo.get_by_id.return_value = FakeJob(101, "tenant-123", "Acme", "D", "H", "HVAC", "HVAC", "QUEUED")
    mock_tech_repo = MagicMock()
    mock_tech_repo.get_by_id.return_value = FakeTechnician(12, "John", "HVAC", "D", "AVAILABLE", 0, 3)
    mock_tech_repo.to_ai_dict.return_value = {"technician_id": 12}
    mock_assign_repo = MagicMock()
    mock_assign_repo.get_current_candidate.return_value = JobAssignment(job_id=101, technician_id=12, rank=1, status="PENDING")
    mock_assign_repo.get_rejected_technician_ids.return_value = []
    mock_assign_repo.get_remaining_candidates.return_value = []
    mock_config_manager = MagicMock()
    mock_config_manager.resolve.return_value = valid_dispatch_config

    decision = DispatchDecision(
        action="complete_assignment",
        job_id=101,
        technician_id=12,
        status="REJECTED",
        confidence=0.9,
        reason="Rejected but trying to complete assignment."
    )
    orch = MockOrchestrator(decision)
    service = DispatchService(
        db=db,
        config_manager=mock_config_manager,
        agent_factory=lambda config, orchestrator: DispatchAgent(config=config, orchestrator=orch), # type: ignore
    )
    service.job_repository = mock_job_repo
    service.technician_repository = mock_tech_repo
    service.assignment_repository = mock_assign_repo

    with pytest.raises(RuntimeError) as exc:
        await service.dispatch_async(101, "TECHNICIAN_REJECTED")
    assert "action must be assign_next_candidate or request_replanning" in str(exc.value)

    assert orch.calls_count == 1
    assert_zero_side_effects(mock_job_repo, mock_tech_repo, mock_assign_repo)


@pytest.mark.anyio
async def test_dispatch_service_timeout_event_cannot_complete_assignment(valid_dispatch_config: AgentConfig) -> None:
    db = MagicMock()
    mock_job_repo = MagicMock()
    mock_job_repo.get_by_id.return_value = FakeJob(101, "tenant-123", "Acme", "D", "H", "HVAC", "HVAC", "QUEUED")
    mock_tech_repo = MagicMock()
    mock_tech_repo.get_by_id.return_value = FakeTechnician(12, "John", "HVAC", "D", "AVAILABLE", 0, 3)
    mock_tech_repo.to_ai_dict.return_value = {"technician_id": 12}
    mock_assign_repo = MagicMock()
    mock_assign_repo.get_current_candidate.return_value = JobAssignment(job_id=101, technician_id=12, rank=1, status="PENDING")
    mock_assign_repo.get_rejected_technician_ids.return_value = []
    mock_assign_repo.get_remaining_candidates.return_value = []
    mock_config_manager = MagicMock()
    mock_config_manager.resolve.return_value = valid_dispatch_config

    decision = DispatchDecision(
        action="complete_assignment",
        job_id=101,
        technician_id=12,
        status="TIMEOUT",
        confidence=0.9,
        reason="Timeout but trying to complete assignment."
    )
    orch = MockOrchestrator(decision)
    service = DispatchService(
        db=db,
        config_manager=mock_config_manager,
        agent_factory=lambda config, orchestrator: DispatchAgent(config=config, orchestrator=orch), # type: ignore
    )
    service.job_repository = mock_job_repo
    service.technician_repository = mock_tech_repo
    service.assignment_repository = mock_assign_repo

    with pytest.raises(RuntimeError) as exc:
        await service.dispatch_async(101, "TECHNICIAN_TIMEOUT")
    assert "action must be assign_next_candidate or request_replanning" in str(exc.value)

    assert orch.calls_count == 1
    assert_zero_side_effects(mock_job_repo, mock_tech_repo, mock_assign_repo)


@pytest.mark.anyio
async def test_dispatch_service_non_string_technician_tenant_id_rejected_safely() -> None:
    db = MagicMock()
    mock_job_repo = MagicMock()
    mock_job_repo.get_by_id.return_value = FakeJob(101, "tenant-123", "Acme", "D", "H", "HVAC", "HVAC", "QUEUED")
    mock_tech_repo = MagicMock()
    mock_tech = FakeTechnician(12, "John", "HVAC", "D", "AVAILABLE", 0, 3, tenant_id=12345) # type: ignore
    mock_tech_repo.get_by_id.return_value = mock_tech
    mock_assign_repo = MagicMock()
    mock_assign = JobAssignment(job_id=101, technician_id=12, rank=1, status="PENDING", is_current=True)
    mock_assign_repo.get_current_candidate.return_value = mock_assign

    service = DispatchService(db=db)
    service.job_repository = mock_job_repo
    service.technician_repository = mock_tech_repo
    service.assignment_repository = mock_assign_repo

    with pytest.raises(ValueError) as exc:
        await service.dispatch_async(101, "TECHNICIAN_ACCEPTED")
    assert "missing a tenant ID" in str(exc.value)
    assert_zero_side_effects(mock_job_repo, mock_tech_repo, mock_assign_repo)


@pytest.mark.anyio
async def test_dispatch_service_blank_job_tenant_id_rejected_safely() -> None:
    db = MagicMock()
    mock_job_repo = MagicMock()
    mock_job_repo.get_by_id.return_value = FakeJob(101, "   ", "Acme", "D", "H", "HVAC", "HVAC", "QUEUED")

    service = DispatchService(db=db)
    service.job_repository = mock_job_repo

    with pytest.raises(ValueError) as exc:
        await service.dispatch_async(101, "TECHNICIAN_ACCEPTED")
    assert "does not have a tenant_id" in str(exc.value)