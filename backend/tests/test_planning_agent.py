"""

test_planning_agent.py



Production-hardened unit tests for PlanningAgent, PlanningService, and PlanningIntegration.

"""



from __future__ import annotations



import asyncio
import threading
from datetime import datetime, timezone

from typing import Any, Dict, List

import pytest

from pydantic import ValidationError

from unittest.mock import MagicMock, patch



from app.services.ai.FieldOpsAI.agents.planning_agent import PlanningAgent

from app.services.ai.FieldOpsAI.agents.base import (

    BaseAgent,

    AgentState,

    AgentDisabledError,

    TenantIsolationError,

    AgentLifecycleError,

)

from app.services.ai.FieldOpsAI.services.planning_service import PlanningService

from app.services.ai.integrations.planning_integration import PlanningIntegration

from app.services.ai.FieldOpsAI.schemas.agent_config import AgentConfig

from app.services.ai.FieldOpsAI.schemas.ai_task import AITask

from app.services.ai.FieldOpsAI.schemas.planning import PlanningContext, PlanningDecision, RecommendedTechnician

from app.services.ai.FieldOpsAI.runtime.orchestrator import AIOrchestrator

from app.services.ai.FieldOpsAI.config.agent_config_manager import AgentConfigManager

from app.services.ai.FieldOpsAI.runtime.agent_pool import AgentPool

from app.services.ai.FieldOpsAI.runtime.lifecycle import AgentLifecycle

from app.services.ai.FieldOpsAI.schemas.agent_result import AgentResult, AgentResultStatus





class TechnicianRecord(dict):
    """Test double supporting ORM-style attributes and mapping access."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # A planning candidate must have a fresh heartbeat.
        self.setdefault("last_ping", datetime.now(timezone.utc))

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value

def configure_planning_test_db(db) -> None:
    """Provide the active provider organization required for planning."""
    db.query.return_value.filter.return_value.all.return_value = [
        ("tenant-123", 13.0827, 80.2707),
    ]

class MockOrchestrator:

    """

    Mock orchestrator that can act as a falsey test double if needed.

    """

    def __init__(self, response_decision: PlanningDecision, is_falsey: bool = False) -> None:

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





class BlockingOrchestrator:

    def __init__(self) -> None:

        self.calls_count = 0

        self.event = threading.Event()



    def execute(self, task: AITask, context: dict, response_schema: Any) -> Any:

        self.calls_count += 1

        self.event.wait(timeout=10.0)

        return PlanningDecision(

            action="manual_review",

            job_id=45,

            priority="HIGH",

            reason="Provider execution was blocked.",

            recommended_technicians=[]

        )





class FalseyAgentPool(AgentPool):

    def __bool__(self) -> bool:

        return False





@pytest.fixture

def valid_planning_config() -> AgentConfig:

    return AgentConfig(

        agent_type=AITask.PLANNING,

        tenant_id="tenant-123",

        agent_version="1.0",

        timeout_seconds=30.0,

        max_retries=2,

        enabled=True,

    )





@pytest.fixture

def sample_decision() -> PlanningDecision:

    return PlanningDecision(

        action="assign_technician",

        job_id=45,

        priority="HIGH",

        reason="Technician fits all required skills and location proximity.",

        recommended_technicians=[

            RecommendedTechnician(

                technician_id=12,

                rank=1,

                confidence=0.95,

                estimated_eta=15,

            )

        ]

    )





@pytest.fixture

def sample_context_dict() -> dict[str, Any]:

    return {

        "tenant_id": "tenant-123",

        "job_id": 45,

        "customer_request": {

            "customer_name": "Acme Corp",

            "location": "Downtown",

            "priority": "HIGH",

            "required_skill": "HVAC",

        },

        "available_technicians": [

            {

                "technician_id": 12,

                "technician_name": "John Doe",

                "technician_skill": "HVAC",

                "technician_status": "Available",

                "current_jobs": 0,

                "max_jobs": 3,

                "location": "Downtown",

                "tenant_id": "tenant-123",

            }

        ],

        "rejected_technician_ids": [],

    }





# ==========================================================

# Core PlanningAgent Hardening Tests

# ==========================================================



def test_planning_agent_inherits_from_base_agent(valid_planning_config: AgentConfig) -> None:

    agent = PlanningAgent(config=valid_planning_config)

    assert isinstance(agent, BaseAgent)





def test_constructor_accepts_valid_config(valid_planning_config: AgentConfig) -> None:

    agent = PlanningAgent(config=valid_planning_config)

    assert agent.config == valid_planning_config

    assert agent.tenant_id == "tenant-123"





def test_constructor_rejects_non_planning_task() -> None:

    bad_config = AgentConfig(

        agent_type=AITask.DISPATCH,

        tenant_id="tenant-123",

        enabled=True,

    )

    with pytest.raises(ValueError) as exc_info:

        PlanningAgent(config=bad_config)

    assert "PlanningAgent requires an AITask.PLANNING configuration" in str(exc_info.value)





def test_planning_agent_uses_supplied_falsey_orchestrator(valid_planning_config: AgentConfig) -> None:

    falsey_orch = MockOrchestrator(None, is_falsey=True)  # type: ignore

    assert bool(falsey_orch) is False



    agent = PlanningAgent(config=valid_planning_config, orchestrator=falsey_orch)  # type: ignore

    assert agent.orchestrator is falsey_orch





@pytest.mark.anyio

async def test_invalid_planning_context_raises_normal_pydantic_validation_error(

    valid_planning_config: AgentConfig,

    sample_context_dict: dict[str, Any]

) -> None:

    agent = PlanningAgent(config=valid_planning_config)

    await agent.setup()



    del sample_context_dict["customer_request"]



    with pytest.raises(ValidationError):

        await agent.execute(sample_context_dict)





@pytest.mark.anyio

async def test_planning_agent_orchestration_is_called_exactly_once_per_execution(

    valid_planning_config: AgentConfig,

    sample_decision: PlanningDecision,

    sample_context_dict: dict[str, Any]

) -> None:

    orch = MockOrchestrator(sample_decision)

    agent = PlanningAgent(config=valid_planning_config, orchestrator=orch)  # type: ignore

    await agent.setup()



    await agent.execute(sample_context_dict)

    assert orch.calls_count == 1





@pytest.mark.anyio

async def test_agent_failure_produces_one_provider_orchestrator_call(

    valid_planning_config: AgentConfig,

    sample_context_dict: dict[str, Any]

) -> None:

    failing_orch = FailingOrchestrator()

    agent = PlanningAgent(config=valid_planning_config, orchestrator=failing_orch)  # type: ignore

    await agent.setup()



    with pytest.raises(RuntimeError):

        await agent.execute(sample_context_dict)



    assert failing_orch.calls_count == 1





@pytest.mark.anyio

async def test_blocking_orchestrator_event_loop_responsiveness_and_timeout() -> None:

    """

    1. Blocking orchestrator does not freeze the event loop.

    2. Lifecycle timeout works with blocking orchestrator.

    3. Timeout starts exactly one orchestrator call.

    4. Timeout changes agent to ERROR.

    """

    config = AgentConfig(

        agent_type=AITask.PLANNING,

        tenant_id="tenant-123",

        timeout_seconds=0.1,  # Short timeout

        enabled=True,

    )

    orch = BlockingOrchestrator()

    agent = PlanningAgent(config=config, orchestrator=orch)  # type: ignore



    concurrent_task_run = False

    async def concurrent_task():

        nonlocal concurrent_task_run

        await asyncio.sleep(0.02)

        concurrent_task_run = True



    pool = AgentPool()

    context = {

        "tenant_id": "tenant-123",

        "job_id": 45,

        "customer_request": {

            "customer_name": "Acme",

            "location": "Downtown",

            "priority": "HIGH",

            "required_skill": "HVAC",

        },

        "available_technicians": [],

        "rejected_technician_ids": [],

    }



    result = None

    state_after_execute = None

    async def run_lifecycle():

        nonlocal result, state_after_execute

        async with AgentLifecycle(agent=agent, pool=pool) as lifecycle:

            result = await lifecycle.execute(context)

            state_after_execute = agent.state



    try:

        await asyncio.gather(

            run_lifecycle(),

            concurrent_task()

        )



        assert concurrent_task_run is True

        assert orch.calls_count == 1

        assert result is not None

        assert result.status == AgentResultStatus.TIMEOUT

        assert state_after_execute == AgentState.ERROR

        assert agent.state == AgentState.TERMINATED

    finally:

        orch.event.set()





# ==========================================================

# Compatibility plan() Adapter Hardening Tests

# ==========================================================



def test_compatibility_plan_does_not_create_a_thread(

    valid_planning_config: AgentConfig,

    sample_decision: PlanningDecision,

    sample_context_dict: dict[str, Any]

) -> None:

    orch = MockOrchestrator(sample_decision)

    agent = PlanningAgent(config=valid_planning_config, orchestrator=orch)  # type: ignore



    context = PlanningContext(

        job_id=45,

        customer_request=sample_context_dict["customer_request"],

        available_technicians=sample_context_dict["available_technicians"],

    )



    async def mock_execute(self, context_dict):

        return sample_decision



    with patch.object(PlanningAgent, "execute", new=mock_execute):

        with patch("threading.Thread") as mock_thread:

            agent.plan(context)

            mock_thread.assert_not_called()





@pytest.mark.anyio

async def test_compatibility_plan_rejects_use_from_active_event_loop(

    valid_planning_config: AgentConfig,

    sample_decision: PlanningDecision,

    sample_context_dict: dict[str, Any]

) -> None:

    orch = MockOrchestrator(sample_decision)

    agent = PlanningAgent(config=valid_planning_config, orchestrator=orch)  # type: ignore



    context = PlanningContext(

        job_id=45,

        customer_request=sample_context_dict["customer_request"],

        available_technicians=sample_context_dict["available_technicians"],

    )



    with pytest.raises(RuntimeError) as exc_info:

        agent.plan(context)

    assert "plan() cannot be called from an active event loop" in str(exc_info.value)





# ==========================================================

# PlanningService Hardening Tests

# ==========================================================



class FakeJob:
    def __init__(self, id: int, tenant_id: str, customer_name: str, location: str, priority: str, required_skill: str) -> None:
        self.id = id
        self.tenant_id = tenant_id
        self.customer_name = customer_name
        self.location = location
        self.priority = priority
        self.required_skill = required_skill
        self.service_type = required_skill
        self.issue_description = ""



@pytest.mark.anyio

async def test_planning_service_plan_async_success(

    valid_planning_config: AgentConfig,

    sample_decision: PlanningDecision

) -> None:

    db = MagicMock()
    configure_planning_test_db(db)

    mock_job_repo = MagicMock()

    mock_job_repo.get_by_id.return_value = FakeJob(45, "tenant-123", "Alice", "Downtown", "HIGH", "HVAC")



    mock_tech_repo = MagicMock()

    mock_tech_repo.get_available.return_value = [
        TechnicianRecord(
            technician_id=12,
            technician_name="John Doe",
            technician_skill="HVAC",
            technician_status="Available",
            current_jobs=0,
            max_jobs=3,
            location="Downtown",
            tenant_id="tenant-123",
        )
    ]

    mock_tech_repo.to_ai_dict.return_value = TechnicianRecord(technician_id=12)



    mock_assignment_repo = MagicMock()



    mock_config_manager = MagicMock()

    mock_config_manager.resolve.return_value = valid_planning_config



    orch = MockOrchestrator(sample_decision)

    def agent_factory(config, orchestrator):

        return PlanningAgent(config=config, orchestrator=orch)  # type: ignore



    service = PlanningService(

        db=db,

        config_manager=mock_config_manager,

        agent_factory=agent_factory,

        orchestrator=orch,

    )

    service.job_repository = mock_job_repo

    service.technician_repository = mock_tech_repo

    service.assignment_repository = mock_assignment_repo



    with patch("app.services.ai.FieldOpsAI.agents.planning_agent.PlanningAgent.plan") as mock_agent_plan:

        decision = await service.plan_async(job_id=45)

        assert decision == sample_decision

        mock_agent_plan.assert_not_called()



    # PlanningService.plan_async returns the PlanningDecision after filtering
    # candidates; the current implementation does not persist recommendations
    # through the assignment repository.
    mock_assignment_repo.save_recommendations.assert_not_called()
    mock_assignment_repo.save.assert_not_called()

    assert orch.calls_count == 1





@pytest.mark.anyio

async def test_planning_service_plan_async_failure_guarantees_exactly_one_call(

    valid_planning_config: AgentConfig

) -> None:

    db = MagicMock()
    configure_planning_test_db(db)

    mock_job_repo = MagicMock()

    mock_job_repo.get_by_id.return_value = FakeJob(45, "tenant-123", "Alice", "Downtown", "HIGH", "HVAC")



    mock_tech_repo = MagicMock()

    mock_tech_repo.get_available.return_value = [
        TechnicianRecord(
            technician_id=12,
            technician_name="John Doe",
            technician_skill="HVAC",
            technician_status="Available",
            current_jobs=0,
            max_jobs=3,
            location="Downtown",
            tenant_id="tenant-123",
        )
    ]

    mock_tech_repo.to_ai_dict.return_value = TechnicianRecord(technician_id=12)



    mock_assignment_repo = MagicMock()



    mock_config_manager = MagicMock()

    mock_config_manager.resolve.return_value = valid_planning_config



    failing_orch = FailingOrchestrator()

    def failing_agent_factory(config, orchestrator):

        return PlanningAgent(config=config, orchestrator=failing_orch)  # type: ignore



    service = PlanningService(

        db=db,

        config_manager=mock_config_manager,

        agent_factory=failing_agent_factory,

        orchestrator=failing_orch,

    )

    service.job_repository = mock_job_repo

    service.technician_repository = mock_tech_repo

    service.assignment_repository = mock_assignment_repo



    with pytest.raises(RuntimeError):

        await service.plan_async(job_id=45)



    assert failing_orch.calls_count == 1

    mock_assignment_repo.save_recommendations.assert_not_called()

    mock_assignment_repo.save.assert_not_called()





@pytest.mark.anyio

async def test_planning_service_plan_active_loop_rejection() -> None:

    service = PlanningService(db=MagicMock())

    with pytest.raises(RuntimeError) as exc_info:

        service.plan(job_id=45)

    assert "PlanningService.plan() cannot be called from an active event loop" in str(exc_info.value)





@pytest.mark.anyio

async def test_planning_service_rejects_missing_successful_output(valid_planning_config: AgentConfig) -> None:

    db = MagicMock()
    configure_planning_test_db(db)

    mock_job_repo = MagicMock()

    mock_job_repo.get_by_id.return_value = FakeJob(45, "tenant-123", "Alice", "Downtown", "HIGH", "HVAC")



    mock_tech_repo = MagicMock()

    mock_tech_repo.get_available.return_value = [
        TechnicianRecord(
            technician_id=12,
            technician_name="John Doe",
            technician_skill="HVAC",
            technician_status="Available",
            current_jobs=0,
            max_jobs=3,
            location="Downtown",
            tenant_id="tenant-123",
        )
    ]

    mock_tech_repo.to_ai_dict.return_value = TechnicianRecord(technician_id=12)



    mock_assignment_repo = MagicMock()



    mock_config_manager = MagicMock()

    mock_config_manager.resolve.return_value = valid_planning_config



    orch = MockOrchestrator(None)  # type: ignore



    async def mock_execute(self, context):

        return AgentResult(

            status=AgentResultStatus.SUCCESS,

            output=None,

            latency_ms=1.5,

            agent_id="agent-id-123",

            correlation_id="corr-id-123"

        )



    with patch("app.services.ai.FieldOpsAI.runtime.lifecycle.AgentLifecycle.execute", new=mock_execute):

        service = PlanningService(

            db=db,

            config_manager=mock_config_manager,

            orchestrator=orch,

        )

        service.job_repository = mock_job_repo

        service.technician_repository = mock_tech_repo

        service.assignment_repository = mock_assignment_repo



        with pytest.raises(RuntimeError) as exc_info:

            await service.plan_async(job_id=45)

        assert "Planning Agent returned an invalid decision." in str(exc_info.value)



    mock_assignment_repo.save_recommendations.assert_not_called()

    mock_assignment_repo.save.assert_not_called()





@pytest.mark.anyio

async def test_planning_service_rejects_wrong_successful_output_type(valid_planning_config: AgentConfig) -> None:

    db = MagicMock()
    configure_planning_test_db(db)

    mock_job_repo = MagicMock()

    mock_job_repo.get_by_id.return_value = FakeJob(45, "tenant-123", "Alice", "Downtown", "HIGH", "HVAC")



    mock_tech_repo = MagicMock()

    mock_tech_repo.get_available.return_value = [
        TechnicianRecord(
            technician_id=12,
            technician_name="John Doe",
            technician_skill="HVAC",
            technician_status="Available",
            current_jobs=0,
            max_jobs=3,
            location="Downtown",
            tenant_id="tenant-123",
        )
    ]

    mock_tech_repo.to_ai_dict.return_value = TechnicianRecord(technician_id=12)



    mock_assignment_repo = MagicMock()



    mock_config_manager = MagicMock()

    mock_config_manager.resolve.return_value = valid_planning_config



    orch = MockOrchestrator(None)  # type: ignore



    async def mock_execute(self, context):

        return AgentResult(

            status=AgentResultStatus.SUCCESS,

            output="wrong-type",

            latency_ms=1.5,

            agent_id="agent-id-123",

            correlation_id="corr-id-123"

        )



    with patch("app.services.ai.FieldOpsAI.runtime.lifecycle.AgentLifecycle.execute", new=mock_execute):

        service = PlanningService(

            db=db,

            config_manager=mock_config_manager,

            orchestrator=orch,

        )

        service.job_repository = mock_job_repo

        service.technician_repository = mock_tech_repo

        service.assignment_repository = mock_assignment_repo



        with pytest.raises(RuntimeError) as exc_info:

            await service.plan_async(job_id=45)

        assert "Planning Agent returned an invalid decision." in str(exc_info.value)



    mock_assignment_repo.save_recommendations.assert_not_called()

    mock_assignment_repo.save.assert_not_called()





@pytest.mark.anyio

async def test_planning_service_with_falsey_pool(

    valid_planning_config: AgentConfig,

    sample_decision: PlanningDecision

) -> None:

    db = MagicMock()
    configure_planning_test_db(db)

    mock_job_repo = MagicMock()

    mock_job_repo.get_by_id.return_value = FakeJob(45, "tenant-123", "Alice", "Downtown", "HIGH", "HVAC")



    mock_tech_repo = MagicMock()

    mock_tech_repo.get_available.return_value = [
        TechnicianRecord(
            technician_id=12,
            technician_name="John Doe",
            technician_skill="HVAC",
            technician_status="Available",
            current_jobs=0,
            max_jobs=3,
            location="Downtown",
            tenant_id="tenant-123",
        )
    ]

    mock_tech_repo.to_ai_dict.return_value = TechnicianRecord(technician_id=12)



    mock_assignment_repo = MagicMock()



    mock_config_manager = MagicMock()

    mock_config_manager.resolve.return_value = valid_planning_config



    orch = MockOrchestrator(sample_decision)



    fap = FalseyAgentPool()



    service = PlanningService(

        db=db,

        config_manager=mock_config_manager,

        orchestrator=orch,

        pool=fap,

    )

    service.job_repository = mock_job_repo

    service.technician_repository = mock_tech_repo

    service.assignment_repository = mock_assignment_repo



    assert bool(fap) is False



    decision = await service.plan_async(job_id=45)

    assert decision == sample_decision

    assert service._pool is fap

    assert len(await fap.list_agents(tenant_id="tenant-123")) == 0





def test_agent_config_annotation_is_resolvable() -> None:

    import typing

    hints = typing.get_type_hints(PlanningService.__init__)

    assert hints.get("config_manager") is not None





# ==========================================================

# PlanningIntegration Hardening Tests

# ==========================================================



def test_planning_integration_requires_tenant_id() -> None:

    integration = PlanningIntegration()

    import inspect

    sig = inspect.signature(integration.recommend_async)

    assert "tenant_id" in sig.parameters

    assert sig.parameters["tenant_id"].default is inspect.Parameter.empty





def test_planning_integration_rejects_blank_tenant_id() -> None:

    integration = PlanningIntegration()

    with pytest.raises(ValueError) as exc_info:

        integration.recommend(

            customer_request={},

            candidate_technicians=[],

            tenant_id="  "

        )

    assert "tenant_id must be a non-blank string" in str(exc_info.value)





@pytest.mark.anyio

async def test_planning_integration_recommend_async_lifecycle_success_and_termination(

    sample_decision: PlanningDecision

) -> None:

    integration = PlanningIntegration()

    orch = MockOrchestrator(sample_decision)



    with patch("app.services.ai.FieldOpsAI.config.agent_config_manager.AgentConfigManager.resolve") as mock_resolve:

        config = AgentConfig(agent_type=AITask.PLANNING, tenant_id="tenant-A")

        mock_resolve.return_value = config



        with patch("app.services.ai.FieldOpsAI.agents.planning_agent.ai_orchestrator", new=orch):

            with patch("app.services.ai.integrations.planning_integration.PlanningAgent") as mock_agent_class:

                agent_instance = PlanningAgent(config=config, orchestrator=orch)  # type: ignore

                mock_agent_class.return_value = agent_instance



                with patch.object(PlanningAgent, "plan") as mock_agent_plan:

                    decision = await integration.recommend_async(

                        customer_request={},

                        candidate_technicians=[],

                        tenant_id="tenant-A"

                    )

                    assert decision == sample_decision

                    mock_agent_plan.assert_not_called()



                assert agent_instance.state == AgentState.TERMINATED





@pytest.mark.anyio

async def test_planning_integration_recommend_async_failure_exactly_one_call() -> None:

    integration = PlanningIntegration()

    failing_orch = FailingOrchestrator()



    with patch("app.services.ai.FieldOpsAI.config.agent_config_manager.AgentConfigManager.resolve") as mock_resolve:

        config = AgentConfig(agent_type=AITask.PLANNING, tenant_id="tenant-A")

        mock_resolve.return_value = config



        with patch("app.services.ai.FieldOpsAI.agents.planning_agent.ai_orchestrator", new=failing_orch):

            with pytest.raises(RuntimeError):

                await integration.recommend_async(

                    customer_request={},

                    candidate_technicians=[],

                    tenant_id="tenant-A"

                )

            assert failing_orch.calls_count == 1





@pytest.mark.anyio

async def test_planning_integration_recommend_active_loop_rejection() -> None:

    integration = PlanningIntegration()

    with pytest.raises(RuntimeError) as exc_info:

        integration.recommend(

            customer_request={},

            candidate_technicians=[],

            tenant_id="tenant-A"

        )

    assert "PlanningIntegration.recommend() cannot be called from an active event loop" in str(exc_info.value)





@pytest.mark.anyio

async def test_planning_integration_tenant_isolation_sequential(sample_decision: PlanningDecision) -> None:

    integration = PlanningIntegration()

    orch = MockOrchestrator(sample_decision)



    with patch("app.services.ai.FieldOpsAI.config.agent_config_manager.AgentConfigManager.resolve") as mock_resolve:

        config_a = AgentConfig(agent_type=AITask.PLANNING, tenant_id="tenant-A")

        config_b = AgentConfig(agent_type=AITask.PLANNING, tenant_id="tenant-B")



        def resolve_side_effect(agent_type, tenant_id, overrides=None):

            if tenant_id == "tenant-A":

                return config_a

            elif tenant_id == "tenant-B":

                return config_b

            raise ValueError("Unknown tenant")



        mock_resolve.side_effect = resolve_side_effect



        with patch("app.services.ai.FieldOpsAI.agents.planning_agent.ai_orchestrator", new=orch):

            await integration.recommend_async(customer_request={}, candidate_technicians=[], tenant_id="tenant-A")

            mock_resolve.assert_called_with(agent_type=AITask.PLANNING, tenant_id="tenant-A")



            await integration.recommend_async(customer_request={}, candidate_technicians=[], tenant_id="tenant-B")

            mock_resolve.assert_called_with(agent_type=AITask.PLANNING, tenant_id="tenant-B")





def test_planning_integration_rejects_injected_tenant_mismatch() -> None:

    config_a = AgentConfig(agent_type=AITask.PLANNING, tenant_id="tenant-A")

    agent_a = PlanningAgent(config=config_a)



    integration = PlanningIntegration(agent=agent_a)



    with pytest.raises(TenantIsolationError) as exc_info:

        integration.recommend(

            customer_request={},

            candidate_technicians=[],

            tenant_id="tenant-B"

        )

    assert "The injected PlanningAgent does not belong to the requested tenant." in str(exc_info.value)





@pytest.mark.anyio

async def test_planning_integration_rejects_invalid_successful_output() -> None:

    integration = PlanningIntegration()



    with patch("app.services.ai.FieldOpsAI.config.agent_config_manager.AgentConfigManager.resolve") as mock_resolve:

        config = AgentConfig(agent_type=AITask.PLANNING, tenant_id="tenant-A")

        mock_resolve.return_value = config



        async def mock_execute(self, context):

            return AgentResult(

                status=AgentResultStatus.SUCCESS,

                output="invalid-type",

                latency_ms=1.5,

                agent_id="agent-id-123",

                correlation_id="corr-id-123"

            )



        with patch("app.services.ai.FieldOpsAI.runtime.lifecycle.AgentLifecycle.execute", new=mock_execute):

            with pytest.raises(RuntimeError) as exc_info:

                await integration.recommend_async(

                    customer_request={},

                    candidate_technicians=[],

                    tenant_id="tenant-A"

                )

            assert "Planning Agent returned an invalid decision." in str(exc_info.value)





@pytest.mark.anyio

async def test_injected_agent_lifecycle_reuse_prevention(

    valid_planning_config: AgentConfig,

    sample_decision: PlanningDecision

) -> None:

    """

    12. Injected-agent second-use behavior matches the single-use compatibility design (first succeeds, second fails).

    13. Second use does not call the orchestrator again.

    """

    orch = MockOrchestrator(sample_decision)

    agent = PlanningAgent(config=valid_planning_config, orchestrator=orch)  # type: ignore



    integration = PlanningIntegration(agent=agent)



    decision = await integration.recommend_async(

        customer_request={},

        candidate_technicians=[],

        tenant_id="tenant-123"

    )

    assert decision == sample_decision

    assert orch.calls_count == 1

    assert agent.state == AgentState.TERMINATED



    with pytest.raises(AgentLifecycleError) as exc_info:

        await integration.recommend_async(

            customer_request={},

            candidate_technicians=[],

            tenant_id="tenant-123"

        )

    assert "The injected agent is already terminated." in str(exc_info.value)

    assert orch.calls_count == 1





# ==========================================================

# Dependency Injection Hardening Tests

# ==========================================================



def test_supplied_falsey_config_manager_retained() -> None:

    class FalseyConfigManager:

        def __bool__(self) -> bool:

            return False

        def resolve(self, *args, **kwargs) -> AgentConfig:

            return AgentConfig(agent_type=AITask.PLANNING, tenant_id="tenant-123")



    fcm = FalseyConfigManager()

    service = PlanningService(db=MagicMock(), config_manager=fcm)  # type: ignore

    assert service._config_manager is fcm





def test_supplied_falsey_agent_pool_retained() -> None:

    fap = FalseyAgentPool()

    service = PlanningService(db=MagicMock(), pool=fap)  # type: ignore

    assert service._pool is fap





# ==========================================================

# Legacy Tests Regression Coverage

# ==========================================================



@pytest.mark.anyio

async def test_cross_tenant_base_agent_execution_remains_rejected(valid_planning_config: AgentConfig) -> None:

    agent = PlanningAgent(config=valid_planning_config)

    await agent.setup()



    with pytest.raises(TenantIsolationError):

        await agent.execute({"tenant_id": "tenant-B"})





def test_existing_planning_business_output_remains_unchanged(

    valid_planning_config: AgentConfig,

    sample_decision: PlanningDecision,

    sample_context_dict: dict[str, Any]

) -> None:

    orch = MockOrchestrator(sample_decision)

    agent = PlanningAgent(config=valid_planning_config, orchestrator=orch)  # type: ignore



    context = PlanningContext(

        job_id=45,

        customer_request=sample_context_dict["customer_request"],

        available_technicians=sample_context_dict["available_technicians"],

    )



    decision = agent.plan(context)

    assert decision.action == "assign_technician"

    assert decision.recommended_technicians[0].technician_id == 12

    assert decision.recommended_technicians[0].confidence == 0.95





def test_plan_compatibility_method_when_already_setup(

    valid_planning_config: AgentConfig,

    sample_decision: PlanningDecision,

    sample_context_dict: dict[str, Any]

) -> None:

    orch = MockOrchestrator(sample_decision)

    agent = PlanningAgent(config=valid_planning_config, orchestrator=orch)  # type: ignore

    import asyncio

    asyncio.run(agent.setup())



    context = PlanningContext(

        job_id=45,

        customer_request=sample_context_dict["customer_request"],

        available_technicians=sample_context_dict["available_technicians"],

    )

    decision = agent.plan(context)

    assert decision == sample_decision





def test_planning_service_plan_sync_successful_no_active_loop(

    valid_planning_config: AgentConfig,

    sample_decision: PlanningDecision

) -> None:

    db = MagicMock()
    configure_planning_test_db(db)

    mock_job_repo = MagicMock()

    mock_job_repo.get_by_id.return_value = FakeJob(45, "tenant-123", "Alice", "Downtown", "HIGH", "HVAC")



    mock_tech_repo = MagicMock()

    mock_tech_repo.get_available.return_value = [
        TechnicianRecord(
            technician_id=12,
            technician_name="John Doe",
            technician_skill="HVAC",
            technician_status="Available",
            current_jobs=0,
            max_jobs=3,
            location="Downtown",
            tenant_id="tenant-123",
        )
    ]

    mock_tech_repo.to_ai_dict.return_value = TechnicianRecord(technician_id=12)



    mock_assignment_repo = MagicMock()



    mock_config_manager = MagicMock()

    mock_config_manager.resolve.return_value = valid_planning_config



    orch = MockOrchestrator(sample_decision)

    def agent_factory(config, orchestrator):

        return PlanningAgent(config=config, orchestrator=orch)  # type: ignore



    service = PlanningService(

        db=db,

        config_manager=mock_config_manager,

        agent_factory=agent_factory,

        orchestrator=orch,

    )

    service.job_repository = mock_job_repo

    service.technician_repository = mock_tech_repo

    service.assignment_repository = mock_assignment_repo



    decision = service.plan(job_id=45, rejected_technician_ids=[11])

    assert decision == sample_decision





@pytest.mark.anyio

async def test_planning_service_job_not_found() -> None:

    db = MagicMock()

    mock_job_repo = MagicMock()

    mock_job_repo.get_by_id.return_value = None



    service = PlanningService(db=db)

    service.job_repository = mock_job_repo



    with pytest.raises(ValueError) as exc_info:

        await service.plan_async(job_id=999)

    assert "Job 999 was not found." in str(exc_info.value)





@pytest.mark.anyio

async def test_planning_service_no_technicians() -> None:

    db = MagicMock()

    mock_job_repo = MagicMock()

    mock_job_repo.get_by_id.return_value = FakeJob(45, "tenant-123", "Alice", "Downtown", "HIGH", "HVAC")



    mock_tech_repo = MagicMock()

    mock_tech_repo.get_available.return_value = []



    service = PlanningService(db=db)

    service.job_repository = mock_job_repo

    service.technician_repository = mock_tech_repo



    decision = await service.plan_async(job_id=45)

    assert decision.action == "no_assignment"
    assert decision.job_id == 45
    assert decision.recommended_technicians == []
    assert (
        decision.reason
        == "No technicians met the current planning eligibility requirements."
    )


@pytest.mark.anyio

async def test_planning_service_default_agent_factory(

    valid_planning_config: AgentConfig,

    sample_decision: PlanningDecision

) -> None:

    db = MagicMock()
    configure_planning_test_db(db)

    mock_job_repo = MagicMock()

    mock_job_repo.get_by_id.return_value = FakeJob(45, "tenant-123", "Alice", "Downtown", "HIGH", "HVAC")



    mock_tech_repo = MagicMock()

    mock_tech_repo.get_available.return_value = [
        TechnicianRecord(
            technician_id=12,
            technician_name="John Doe",
            technician_skill="HVAC",
            technician_status="Available",
            current_jobs=0,
            max_jobs=3,
            location="Downtown",
            tenant_id="tenant-123",
        )
    ]

    mock_tech_repo.to_ai_dict.return_value = TechnicianRecord(technician_id=12)



    mock_assignment_repo = MagicMock()



    mock_config_manager = MagicMock()

    mock_config_manager.resolve.return_value = valid_planning_config



    orch = MockOrchestrator(sample_decision)



    service = PlanningService(

        db=db,

        config_manager=mock_config_manager,

        orchestrator=orch,

    )

    service.job_repository = mock_job_repo

    service.technician_repository = mock_tech_repo

    service.assignment_repository = mock_assignment_repo



    decision = await service.plan_async(job_id=45)

    assert decision == sample_decision





def test_planning_integration_recommend_sync_no_active_loop(

    sample_decision: PlanningDecision

) -> None:

    integration = PlanningIntegration()

    orch = MockOrchestrator(sample_decision)



    with patch("app.services.ai.FieldOpsAI.config.agent_config_manager.AgentConfigManager.resolve") as mock_resolve:

        config = AgentConfig(agent_type=AITask.PLANNING, tenant_id="tenant-A")

        mock_resolve.return_value = config



        with patch("app.services.ai.FieldOpsAI.agents.planning_agent.ai_orchestrator", new=orch):

            decision = integration.recommend(

                customer_request={},

                candidate_technicians=[],

                tenant_id="tenant-A"

            )

            assert decision == sample_decision





@pytest.mark.anyio

async def test_planning_integration_injected_tenant_matches(

    sample_decision: PlanningDecision

) -> None:

    config = AgentConfig(agent_type=AITask.PLANNING, tenant_id="tenant-A")

    orch = MockOrchestrator(sample_decision)

    agent = PlanningAgent(config=config, orchestrator=orch)  # type: ignore



    integration = PlanningIntegration(agent=agent)

    decision = await integration.recommend_async(

        customer_request={},

        candidate_technicians=[],

        tenant_id="tenant-A"

    )

    assert decision == sample_decision





@pytest.mark.anyio

async def test_successful_execution_no_technicians(

    valid_planning_config: AgentConfig,

    sample_context_dict: dict[str, Any]

) -> None:

    decision_no_techs = PlanningDecision(

        action="manual_review",

        job_id=45,

        priority="HIGH",

        reason="No technician available in this area.",

        recommended_technicians=[]

    )

    orch = MockOrchestrator(decision_no_techs)

    agent = PlanningAgent(config=valid_planning_config, orchestrator=orch)  # type: ignore

    await agent.setup()



    result = await agent.execute(sample_context_dict)

    assert result.action == "manual_review"

    assert len(result.recommended_technicians) == 0
