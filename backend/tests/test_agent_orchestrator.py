import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio

from app.services.ai.FieldOpsAI.runtime.orchestrator import (
    AgentOrchestrator,
    AgentResult,
    AgentMapping,
    SubTask,
    FinalResult,
    ResolvedResult,
    estimate_chat_input_tokens,
)
from app.services.ai.FieldOpsAI.schemas.ai_task import AITask
from app.services.ai.FieldOpsAI.runtime.engine import (
    TaskStatus,
)


def test_chat_token_estimator_reserves_serialized_roles_and_bounded_margin(monkeypatch):
    import app.services.ai.FieldOpsAI.runtime.orchestrator as orchestrator_module
    monkeypatch.setattr(orchestrator_module, "count_tokens", lambda text, _model: len(text) // 4)
    messages = [
        {"role": "system", "content": "s" * 800},
        {"role": "user", "content": '{"job_id":"158","tenant_id":"t","history":"' + "h" * 1200 + '"}'},
    ]
    estimate = estimate_chat_input_tokens(messages, "llama3")
    base = len(__import__("json").dumps(messages, ensure_ascii=False, separators=(",", ":"))) // 4 + 8
    assert estimate >= base
    assert estimate <= int(base * 1.21) + 16


@pytest.fixture
def orchestrator():
    registry = MagicMock()
    bus = MagicMock()
    engine = MagicMock()
    config_manager = MagicMock()

    return AgentOrchestrator(
        agent_registry=registry,
        agent_bus=bus,
        runtime_engine=engine,
        config_manager=config_manager,
    )


def make_subtask(
    task_id="task-1",
    task="Test task",
    agent_type=AITask.PLANNING,
    dependencies=None,
):
    return SubTask(
        task_id=task_id,
        task=task,
        agent_type=agent_type,
        context={"tenant_id": "tenant-1"},
        dependencies=dependencies or [],
    )


def test_decompose_creates_planning_subtask(orchestrator):
    result = orchestrator.decompose(
        "Create a service plan",
        tenant_id="tenant-1",
        context={"job_id": "job-1"},
    )

    assert len(result) == 1
    assert result[0].agent_type == AITask.PLANNING
    assert result[0].task == "Create a service plan"
    assert result[0].context["tenant_id"] == "tenant-1"
    assert result[0].context["job_id"] == "job-1"


def test_decompose_rejects_empty_task(orchestrator):
    with pytest.raises(ValueError, match="task"):
        orchestrator.decompose(
            "",
            tenant_id="tenant-1",
        )


def test_decompose_rejects_empty_tenant(orchestrator):
    with pytest.raises(ValueError, match="tenant_id"):
        orchestrator.decompose(
            "Create a plan",
            tenant_id="",
        )


@pytest.mark.asyncio
async def test_select_agents_assigns_registered_agent(orchestrator):
    registration = MagicMock()
    registration.enabled = True

    orchestrator.agent_registry.get.return_value = registration

    subtask = make_subtask()

    result = await orchestrator.select_agents([subtask])

    assert isinstance(result, AgentMapping)
    assert result.assignments["task-1"] == AITask.PLANNING
    orchestrator.agent_registry.get.assert_called_once_with(
        AITask.PLANNING
    )


@pytest.mark.asyncio
async def test_select_agents_rejects_disabled_agent(orchestrator):
    registration = MagicMock()
    registration.enabled = False

    orchestrator.agent_registry.get.return_value = registration

    subtask = make_subtask()

    with pytest.raises(RuntimeError, match="disabled"):
        await orchestrator.select_agents([subtask])


@pytest.mark.asyncio
async def test_execute_one_success(orchestrator):
    task_result = MagicMock()
    task_result.status = TaskStatus.SUCCEEDED
    task_result.result = {"assigned": True}

    orchestrator.runtime_engine.execute_task = AsyncMock(
        return_value=task_result
    )

    subtask = make_subtask()
    mapping = AgentMapping(
        assignments={"task-1": AITask.PLANNING}
    )

    result = await orchestrator._execute_one(
        subtask,
        mapping,
    )

    assert isinstance(result, AgentResult)
    assert result.status == "succeeded"
    assert result.result == {"assigned": True}
    assert result.confidence == 1.0


@pytest.mark.asyncio
async def test_execute_one_without_assignment(orchestrator):
    subtask = make_subtask()

    mapping = AgentMapping(assignments={})

    result = await orchestrator._execute_one(
        subtask,
        mapping,
    )

    assert result.status == "failed"
    assert result.confidence == 0.0
    assert result.result is None
    assert "No agent assigned" in result.error


@pytest.mark.asyncio
async def test_execute_one_handles_timeout(orchestrator):
    async def slow_execute(spec):
        raise TimeoutError()

    orchestrator.runtime_engine.execute_task = AsyncMock(
        side_effect=__import__("asyncio").TimeoutError()
    )

    subtask = make_subtask()
    mapping = AgentMapping(
        assignments={"task-1": AITask.PLANNING}
    )

    result = await orchestrator._execute_one(
        subtask,
        mapping,
    )

    assert result.status == "timed_out"
    assert result.confidence == 0.0


@pytest.mark.asyncio
async def test_execute_parallel(orchestrator):
    results = [
        AgentResult(
            task_id="task-1",
            agent_type=AITask.PLANNING,
            result={"value": 1},
        ),
        AgentResult(
            task_id="task-2",
            agent_type=AITask.DISPATCH,
            result={"value": 2},
        ),
    ]

    async def fake_execute_one(subtask, mapping):
        return results[int(subtask.task_id.split("-")[1]) - 1]

    orchestrator._execute_one = fake_execute_one

    subtasks = [
        make_subtask(
            task_id="task-1",
            agent_type=AITask.PLANNING,
        ),
        make_subtask(
            task_id="task-2",
            agent_type=AITask.DISPATCH,
        ),
    ]

    mapping = AgentMapping(
        assignments={
            "task-1": AITask.PLANNING,
            "task-2": AITask.DISPATCH,
        }
    )

    result = await orchestrator.execute_parallel(
        subtasks,
        mapping,
    )

    assert len(result) == 2
    assert result[0].result == {"value": 1}
    assert result[1].result == {"value": 2}


@pytest.mark.asyncio
async def test_execute_sequential_respects_dependencies(orchestrator):
    execution_order = []

    async def fake_execute_one(subtask, mapping):
        execution_order.append(subtask.task_id)

        return AgentResult(
            task_id=subtask.task_id,
            agent_type=subtask.agent_type,
            result=subtask.task_id,
        )

    orchestrator._execute_one = fake_execute_one

    subtasks = [
        make_subtask(
            task_id="task-2",
            dependencies=["task-1"],
        ),
        make_subtask(
            task_id="task-1",
        ),
    ]

    mapping = AgentMapping(
        assignments={
            "task-1": AITask.PLANNING,
            "task-2": AITask.PLANNING,
        }
    )

    result = await orchestrator.execute_sequential(
        subtasks,
        mapping,
    )

    assert execution_order == ["task-1", "task-2"]
    assert len(result) == 2


def test_resolve_conflicts_uses_highest_confidence(orchestrator):
    results = [
        AgentResult(
            task_id="task-1",
            agent_type=AITask.PLANNING,
            result="low",
            confidence=0.4,
        ),
        AgentResult(
            task_id="task-2",
            agent_type=AITask.DISPATCH,
            result="high",
            confidence=0.9,
        ),
    ]

    result = orchestrator.resolve_conflicts(results)

    assert isinstance(result, ResolvedResult)
    assert result.result == "high"
    assert result.confidence == 0.9
    assert result.source_task_id == "task-2"


def test_resolve_conflicts_with_no_success(orchestrator):
    results = [
        AgentResult(
            task_id="task-1",
            agent_type=AITask.PLANNING,
            result=None,
            confidence=0.0,
            status="failed",
        )
    ]

    result = orchestrator.resolve_conflicts(results)

    assert result.result is None
    assert result.confidence == 0.0
    assert result.source_task_id is None


def test_aggregate_success(orchestrator):
    results = [
        AgentResult(
            task_id="task-1",
            agent_type=AITask.PLANNING,
            result={"plan": "ready"},
            confidence=0.95,
        )
    ]

    result = orchestrator.aggregate(results)

    assert isinstance(result, FinalResult)
    assert result.status == "succeeded"
    assert result.result == {"plan": "ready"}
    assert len(result.results) == 1


def test_aggregate_empty_results(orchestrator):
    result = orchestrator.aggregate([])

    assert result.status == "failed"
    assert result.result is None
    assert result.results == []


def test_execution_graph(orchestrator):
    subtasks = [
        make_subtask(
            task_id="task-1",
            agent_type=AITask.PLANNING,
        ),
        make_subtask(
            task_id="task-2",
            agent_type=AITask.DISPATCH,
            dependencies=["task-1"],
        ),
    ]

    graph = orchestrator.execution_graph(subtasks)

    assert "graph TD" in graph
    assert "planning" in graph
    assert "dispatch" in graph
    assert "SUB0 --> SUB1" in graph


@pytest.mark.asyncio
async def test_orchestrate_parallel_flow(orchestrator):
    registration = MagicMock()
    registration.enabled = True

    orchestrator.agent_registry.get.return_value = registration

    task_result = MagicMock()
    task_result.status = TaskStatus.SUCCEEDED
    task_result.result = {"done": True}

    orchestrator.runtime_engine.execute_task = AsyncMock(
        return_value=task_result
    )

    result = await orchestrator.orchestrate(
        "Handle service request",
        tenant_id="tenant-1",
    )

    assert isinstance(result, FinalResult)
    assert result.status == "succeeded"
    assert result.result == {"done": True}


@pytest.mark.asyncio
async def test_orchestrate_sequential_flow(orchestrator):
    registration = MagicMock()
    registration.enabled = True

    orchestrator.agent_registry.get.return_value = registration

    task_result = MagicMock()
    task_result.status = TaskStatus.SUCCEEDED
    task_result.result = {"done": True}

    orchestrator.runtime_engine.execute_task = AsyncMock(
        return_value=task_result
    )

    result = await orchestrator.orchestrate(
        "Handle service request",
        tenant_id="tenant-1",
        sequential=True,
    )

    assert isinstance(result, FinalResult)
    assert result.status == "succeeded"
    assert result.result == {"done": True}


@pytest.mark.asyncio
async def test_execute_one_failed_status(orchestrator):
    """Test when task result has FAILED status"""
    task_result = MagicMock()
    task_result.status = TaskStatus.FAILED
    task_result.error = "Agent error occurred"

    orchestrator.runtime_engine.execute_task = AsyncMock(
        return_value=task_result
    )

    subtask = make_subtask()
    mapping = AgentMapping(
        assignments={"task-1": AITask.PLANNING}
    )

    result = await orchestrator._execute_one(
        subtask,
        mapping,
    )

    assert result.status == str(TaskStatus.FAILED)
    assert result.confidence == 0.0
    assert result.result is None
    assert result.error == "Agent error occurred"


@pytest.mark.asyncio
async def test_execute_one_cancelled_status(orchestrator):
    """Test when task result has CANCELLED status"""
    task_result = MagicMock()
    task_result.status = TaskStatus.CANCELLED
    task_result.error = "Task was cancelled"

    orchestrator.runtime_engine.execute_task = AsyncMock(
        return_value=task_result
    )

    subtask = make_subtask()
    mapping = AgentMapping(
        assignments={"task-1": AITask.PLANNING}
    )

    result = await orchestrator._execute_one(
        subtask,
        mapping,
    )

    assert result.status == str(TaskStatus.CANCELLED)
    assert result.confidence == 0.0
    assert result.error == "Task was cancelled"


@pytest.mark.asyncio
async def test_execute_one_general_exception(orchestrator):
    """Test when task execution raises general exception"""
    orchestrator.runtime_engine.execute_task = AsyncMock(
        side_effect=ValueError("Invalid task configuration")
    )

    subtask = make_subtask()
    mapping = AgentMapping(
        assignments={"task-1": AITask.PLANNING}
    )

    result = await orchestrator._execute_one(
        subtask,
        mapping,
    )

    assert result.status == "failed"
    assert result.confidence == 0.0
    assert "ValueError" in result.error
    assert "Invalid task configuration" in result.error


@pytest.mark.asyncio
async def test_execute_sequential_circular_dependency(orchestrator):
    """Test circular dependency detection"""
    async def fake_execute_one(subtask, mapping):
        return AgentResult(
            task_id=subtask.task_id,
            agent_type=subtask.agent_type,
            result=subtask.task_id,
        )

    orchestrator._execute_one = fake_execute_one

    subtasks = [
        make_subtask(
            task_id="task-1",
            dependencies=["task-2"],
        ),
        make_subtask(
            task_id="task-2",
            dependencies=["task-1"],
        ),
    ]

    mapping = AgentMapping(
        assignments={
            "task-1": AITask.PLANNING,
            "task-2": AITask.PLANNING,
        }
    )

    with pytest.raises(RuntimeError, match="Unable to resolve subtask dependencies"):
        await orchestrator.execute_sequential(
            subtasks,
            mapping,
        )


def test_aggregate_with_failures_but_resolved(orchestrator):
    """Test aggregate with failed results but successful resolution"""
    results = [
        AgentResult(
            task_id="task-1",
            agent_type=AITask.PLANNING,
            result={"plan": "ready"},
            confidence=0.95,
            status="succeeded",
        ),
        AgentResult(
            task_id="task-2",
            agent_type=AITask.DISPATCH,
            result=None,
            confidence=0.0,
            status="failed",
            error="Dispatch failed",
        ),
    ]

    result = orchestrator.aggregate(results)

    assert isinstance(result, FinalResult)
    assert result.status == "succeeded"  # Succeeded because resolved.result exists
    assert result.result == {"plan": "ready"}  # Has resolved result
    assert len(result.results) == 2


def test_aggregate_all_failed_no_resolution(orchestrator):
    """Test aggregate when all tasks fail"""
    results = [
        AgentResult(
            task_id="task-1",
            agent_type=AITask.PLANNING,
            result=None,
            confidence=0.0,
            status="failed",
            error="Error 1",
        ),
        AgentResult(
            task_id="task-2",
            agent_type=AITask.DISPATCH,
            result=None,
            confidence=0.0,
            status="failed",
            error="Error 2",
        ),
    ]

    result = orchestrator.aggregate(results)

    assert result.status == "failed"
    assert result.result is None
    assert len(result.results) == 2


def test_execution_graph_complex_dependencies(orchestrator):
    """Test execution graph with multiple dependencies"""
    subtasks = [
        make_subtask(
            task_id="task-1",
            agent_type=AITask.PLANNING,
        ),
        make_subtask(
            task_id="task-2",
            agent_type=AITask.DISPATCH,
            dependencies=["task-1"],
        ),
        make_subtask(
            task_id="task-3",
            agent_type=AITask.MONITORING,
            dependencies=["task-1", "task-2"],
        ),
    ]

    graph = orchestrator.execution_graph(subtasks)

    assert "graph TD" in graph
    assert "planning" in graph
    assert "dispatch" in graph
    assert "monitoring" in graph
    assert "SUB0 --> SUB1" in graph
    assert "SUB0 --> SUB2" in graph
    assert "SUB1 --> SUB2" in graph


@pytest.mark.asyncio
async def test_execute_parallel_mixed_results(orchestrator):
    """Test parallel execution with mixed success/failure"""
    results = [
        AgentResult(
            task_id="task-1",
            agent_type=AITask.PLANNING,
            result={"value": 1},
            status="succeeded",
        ),
        AgentResult(
            task_id="task-2",
            agent_type=AITask.DISPATCH,
            result=None,
            confidence=0.0,
            status="failed",
            error="Dispatch failed",
        ),
    ]

    async def fake_execute_one(subtask, mapping):
        return results[int(subtask.task_id.split("-")[1]) - 1]

    orchestrator._execute_one = fake_execute_one

    subtasks = [
        make_subtask(
            task_id="task-1",
            agent_type=AITask.PLANNING,
        ),
        make_subtask(
            task_id="task-2",
            agent_type=AITask.DISPATCH,
        ),
    ]

    mapping = AgentMapping(
        assignments={
            "task-1": AITask.PLANNING,
            "task-2": AITask.DISPATCH,
        }
    )

    result = await orchestrator.execute_parallel(
        subtasks,
        mapping,
    )

    assert len(result) == 2
    assert result[0].status == "succeeded"
    assert result[1].status == "failed"


def test_decompose_preserves_extra_context(orchestrator):
    """Test that decompose preserves all context fields"""
    extra_context = {
        "job_id": "job-123",
        "customer_id": "cust-456",
        "priority": "high",
        "metadata": {"key": "value"},
    }

    result = orchestrator.decompose(
        "Complex task",
        tenant_id="tenant-1",
        context=extra_context,
    )

    assert len(result) == 1
    assert result[0].context["tenant_id"] == "tenant-1"
    assert result[0].context["job_id"] == "job-123"
    assert result[0].context["customer_id"] == "cust-456"
    assert result[0].context["priority"] == "high"
    assert result[0].context["metadata"]["key"] == "value"


@pytest.mark.asyncio
async def test_orchestrate_handles_timeout_exception(orchestrator):
    """Test that orchestrate catches TimeoutError from asyncio.wait_for"""
    registration = MagicMock()
    registration.enabled = True
    orchestrator.agent_registry.get.return_value = registration

    task_result = MagicMock()
    task_result.status = TaskStatus.SUCCEEDED
    task_result.result = {"done": True}
    orchestrator.runtime_engine.execute_task = AsyncMock(
        return_value=task_result
    )

    # Mock asyncio.wait_for to raise TimeoutError
    async def mock_wait_for(coro, timeout=None):
        coro.close()
        raise asyncio.TimeoutError()

    with patch("asyncio.wait_for", side_effect=mock_wait_for):
        result = await orchestrator.orchestrate(
            "Handle service request",
            tenant_id="tenant-1",
        )

    assert isinstance(result, FinalResult)
    assert result.status == "timed_out"
    assert result.result is None
    assert result.results == []
    
def test_ai_orchestrator_load_task_prompt():
    from app.services.ai.FieldOpsAI.runtime.orchestrator import AIOrchestrator

    prompt_builder = MagicMock()
    prompt_builder.get_task_prompt.return_value = "test prompt"

    orchestrator = AIOrchestrator(
        prompt_builder=prompt_builder,
        client=MagicMock(),
        provider_health_monitor=MagicMock(),
        failover_executor=MagicMock(),
        budget_manager=MagicMock(),
        provider_cache=MagicMock(),
        circuit_breaker=MagicMock(),
        redis_client=MagicMock(),
    )

    result = orchestrator._load_task_prompt(AITask.PLANNING)

    assert result == "test prompt"
    prompt_builder.get_task_prompt.assert_called_once_with(
        AITask.PLANNING
    )


def test_ai_orchestrator_injected_dependencies():
    from app.services.ai.FieldOpsAI.runtime.orchestrator import AIOrchestrator

    client = MagicMock()
    sanitizer = MagicMock()
    prompt_builder = MagicMock()
    response_parser = MagicMock()
    budget_manager = MagicMock()
    provider_cache = MagicMock()
    circuit_breaker = MagicMock()
    health_monitor = MagicMock()
    failover_executor = MagicMock()
    provider_factory = MagicMock()

    orchestrator = AIOrchestrator(
        client=client,
        sanitizer=sanitizer,
        prompt_builder=prompt_builder,
        response_parser=response_parser,
        budget_manager=budget_manager,
        provider_cache=provider_cache,
        circuit_breaker=circuit_breaker,
        provider_health_monitor=health_monitor,
        failover_executor=failover_executor,
        provider_client_factory=provider_factory,
        redis_client=MagicMock(),
    )

    assert orchestrator.client is client
    assert orchestrator.pii_sanitizer is sanitizer
    assert orchestrator.prompt_builder is prompt_builder
    assert orchestrator.response_parser is response_parser
    assert orchestrator.token_budget_manager is budget_manager
    assert orchestrator.provider_cache is provider_cache
    assert orchestrator.circuit_breaker is circuit_breaker
    assert orchestrator.provider_health_monitor is health_monitor
    assert orchestrator.failover_executor is failover_executor
    assert orchestrator.provider_client_factory is provider_factory
    assert orchestrator.communication_in_app_temperature == 0.7


def test_ai_orchestrator_injected_client_with_provider():
    from app.services.ai.FieldOpsAI.runtime.orchestrator import AIOrchestrator

    provider = MagicMock()
    provider.provider_name.return_value = " OpenAI "
    provider.model_name.return_value = " model-1 "

    client = MagicMock()
    client.provider = provider

    orchestrator = AIOrchestrator(
        client=client,
        provider_health_monitor=MagicMock(),
        failover_executor=MagicMock(),
        budget_manager=MagicMock(),
        provider_cache=MagicMock(),
        circuit_breaker=MagicMock(),
        redis_client=MagicMock(),
    )

    assert orchestrator.client is client

    factory = orchestrator.failover_executor

    assert factory is not None
    
def test_ai_orchestrator_injected_client_provider_exception():
    from app.services.ai.FieldOpsAI.runtime.orchestrator import AIOrchestrator

    provider = MagicMock()
    provider.provider_name.side_effect = Exception("provider error")

    client = MagicMock()
    client.provider = provider

    orchestrator = AIOrchestrator(
        client=client,
        provider_health_monitor=MagicMock(),
        failover_executor=MagicMock(),
        budget_manager=MagicMock(),
        provider_cache=MagicMock(),
        circuit_breaker=MagicMock(),
        redis_client=MagicMock(),
    )

    assert orchestrator.client is client
    
def test_ai_orchestrator_circuit_breaker_vars_type_error():
    from app.services.ai.FieldOpsAI.runtime.orchestrator import AIOrchestrator

    orchestrator = AIOrchestrator(
        client=MagicMock(),
        provider_health_monitor=MagicMock(),
        failover_executor=MagicMock(),
        budget_manager=MagicMock(),
        provider_cache=MagicMock(),
        circuit_breaker=object(),
        redis_client=None,
    )

    assert orchestrator.client is not None
      
@pytest.mark.asyncio
async def test_ai_orchestrator_health_check():
    from app.services.ai.FieldOpsAI.runtime.orchestrator import AIOrchestrator

    health_monitor = MagicMock()
    health_monitor.health_check = MagicMock(return_value=True)

    orchestrator = AIOrchestrator(
        client=MagicMock(),
        provider_health_monitor=health_monitor,
        failover_executor=MagicMock(),
        budget_manager=MagicMock(),
        provider_cache=MagicMock(),
        circuit_breaker=MagicMock(),
        redis_client=MagicMock(),
    )

    result = orchestrator.health_check()

    assert result is not None
    
def test_ai_orchestrator_provider_adapter_methods():
    from app.services.ai.FieldOpsAI.runtime.orchestrator import (
        _LegacyClientProviderAdapter,
    )

    adapter = _LegacyClientProviderAdapter(
        name="test-provider",
        model="test-model",
    )

    assert adapter.provider_name() == "test-provider"
    assert adapter.model_name() == "test-model"
    assert adapter.health_check() is True

def make_ai_orchestrator():
    from app.services.ai.FieldOpsAI.runtime.orchestrator import AIOrchestrator

    prompt_builder = MagicMock()
    prompt_builder.build.return_value = "SYSTEM PROMPT"
    prompt_builder.get_task_prompt.return_value = "TASK PROMPT"

    sanitizer = MagicMock()

    sanitization_result = MagicMock()
    sanitization_result.sanitized_data = {
        "tenant_id": "tenant-1",
        "job_id": "job-1",
    }
    sanitization_result.placeholder_map = {}
    sanitization_result.replacement_count = 0

    sanitizer.sanitize.return_value = sanitization_result
    sanitizer.sanitize_prompt.return_value = (
        "USER PROMPT",
        {},
    )
    sanitizer.restore_data.side_effect = (
    lambda data, placeholder_map, clear_mapping=False: data
    )
    budget = MagicMock()
    budget.config.per_request = {"general": 1000}
    budget.reserve.return_value = "reservation-1"

    cache = MagicMock()
    cache.get.return_value = None

    circuit = MagicMock()
    circuit.check_permission.return_value = MagicMock()

    failover = MagicMock()

    orchestrator = AIOrchestrator(
        client=MagicMock(),
        sanitizer=sanitizer,
        prompt_builder=prompt_builder,
        budget_manager=budget,
        provider_cache=cache,
        circuit_breaker=circuit,
        failover_executor=failover,
        provider_health_monitor=MagicMock(),
    )

    return (
        orchestrator,
        budget,
        cache,
        circuit,
        failover,
    )
def test_ai_orchestrator_execute_success():
    from app.services.ai.FieldOpsAI.runtime.orchestrator import (
        GenerationResult,
        UsageStats,
    )

    (
        orchestrator,
        budget,
        cache,
        circuit,
        failover,
    ) = make_ai_orchestrator()

    provider = MagicMock()
    provider.model_name.return_value = "test-model"

    client = MagicMock()

    result = GenerationResult(
        text="AI RESPONSE",
        provider_name="test-provider",
        model_name="test-model",
        usage=UsageStats(
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            request_count=1,
            latency_ms=1.0,
            cost_usd=0.0,
        ),
    )

    client.generate_result.return_value = result

    orchestrator.provider_client_factory = lambda _: client

    def run_attempt(attempt_runner):
        print("FAILOVER: attempt_runner CALLED")
        return MagicMock(
            generation_result=attempt_runner(
                "test-provider",
                provider
            )
        )

    failover.execute.side_effect = run_attempt

    response = orchestrator.execute(
        AITask.PLANNING,
        {
            "tenant_id": "tenant-1",
            "job_id": "job-1",
        },
    )

    assert response == "AI RESPONSE"


def test_ai_orchestrator_uses_communication_in_app_temperature():
    from app.services.ai.FieldOpsAI.providers.groq_client import GroqClient
    from app.services.ai.FieldOpsAI.runtime.orchestrator import (
        GenerationResult,
        UsageStats,
    )

    orchestrator, _, _, _, failover = make_ai_orchestrator()
    client = MagicMock(spec=GroqClient)
    orchestrator.pii_sanitizer.sanitize.return_value.sanitized_data[
        "channel"
    ] = "IN_APP"
    client.generate_result.return_value = GenerationResult(
        text="validated notification copy",
        provider_name="test-provider",
        model_name="test-model",
        usage=UsageStats(
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            request_count=1,
            latency_ms=1.0,
            cost_usd=0.0,
        ),
    )
    orchestrator.provider_client_factory = lambda _: client

    def run_attempt(attempt_runner):
        provider = MagicMock()
        provider.model_name.return_value = "test-model"
        return MagicMock(
            generation_result=attempt_runner("test-provider", provider)
        )

    failover.execute.side_effect = run_attempt
    orchestrator.execute(
        AITask.COMMUNICATION,
        {
            "tenant_id": "customer-tenant",
            "job_id": "job-1",
            "channel": "IN_APP",
        },
    )

    assert client.generate_result.call_args.kwargs["temperature"] == 0.7
    
def test_ai_orchestrator_execute_cache_hit():
    orchestrator, budget, cache, circuit, failover = make_ai_orchestrator()
    orchestrator.provider_cache = cache
    from app.services.ai.FieldOpsAI.runtime.orchestrator import (
            CachedProviderResponse, 
            UsageStats,
    )

    cache.get.return_value = CachedProviderResponse(
        text="CACHED RESPONSE",
        usage=UsageStats(
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            request_count=0,
            latency_ms=0.0,
            cost_usd=0.0,
        ),
        
    )
    orchestrator.pii_sanitizer.restore_data.return_value = "CACHED RESPONSE"
    orchestrator.pii_sanitizer.restore_data.side_effect = (
        lambda data, placeholder_map, clear_mapping=False: data
    )

    provider = MagicMock()
    provider.model_name.return_value = "test-model"

    def run_attempt(attempt_runner):
        return MagicMock(
            generation_result=attempt_runner(
                "test-provider",
                 provider,
            )
        )

    failover.execute.side_effect = run_attempt

    result = orchestrator.execute(
        AITask.PLANNING,
        {"tenant_id": "tenant-1"},
    )
    print("CACHE GET CALLED:", cache.get.called)
    print("CACHE GET RESULT:", cache.get.return_value)
    print("CACHE GET TEXT:", cache.get.return_value.text)
    print("FAILOVER EXECUTE CALL COUNT:", failover.execute.call_count)
    print("FAILOVER EXECUTE CALL ARGS:", failover.execute.call_args)
    print("RESULT:", result)
    assert result == "CACHED RESPONSE"
    budget.reserve.assert_not_called()
def test_ai_orchestrator_execute_generate_string():
    from app.services.ai.FieldOpsAI.runtime.orchestrator import (
        GenerationResult,
        UsageStats,
    )

    orchestrator, budget, cache, circuit, failover = make_ai_orchestrator()

    provider = MagicMock()
    provider.model_name.return_value = "test-model"

    client = MagicMock()
    client.generate_result = None
    client.generate.return_value = "STRING RESPONSE"

    orchestrator.provider_client_factory = lambda _: client

    def run_attempt(attempt_runner):
        result = attempt_runner("groq", provider)
        return MagicMock(generation_result=result)

    failover.execute.side_effect = run_attempt

    result = orchestrator.execute(
        AITask.PLANNING,
        {"tenant_id": "tenant-1"},
    )

    assert result == "STRING RESPONSE"
    budget.reconcile.assert_called_once()
def test_ai_orchestrator_execute_generate_generation_result():
    from app.services.ai.FieldOpsAI.runtime.orchestrator import (
        GenerationResult,
        UsageStats,
    )

    orchestrator, budget, cache, circuit, failover = make_ai_orchestrator()

    provider = MagicMock()
    provider.model_name.return_value = "test-model"

    generated = GenerationResult(
        text="RESULT",
        provider_name="groq",
        model_name="test-model",
        usage=UsageStats(
            prompt_tokens=5,
            completion_tokens=3,
            total_tokens=8,
            request_count=1,
            latency_ms=1.0,
            cost_usd=0.0,
        ),
    )

    client = MagicMock()
    client.generate_result.return_value = generated

    orchestrator.provider_client_factory = lambda _: client

    def run_attempt(attempt_runner):
        return MagicMock(
            generation_result=attempt_runner("groq", provider)
        )

    failover.execute.side_effect = run_attempt

    result = orchestrator.execute(
        AITask.PLANNING,
        {"tenant_id": "tenant-1"},
    )
    print("CACHE GET:", cache.get.call_count)
    print("FAILOVER EXECUTE:", failover.execute.call_count)
    print("RESULT:", result)

    assert result == "RESULT"
    
def test_legacy_client_provider_adapter_generate_completion():
    from app.services.ai.FieldOpsAI.runtime.orchestrator import (
        _LegacyClientProviderAdapter,
    )

    adapter = _LegacyClientProviderAdapter()

    with pytest.raises(
        NotImplementedError,
        match="Legacy adapter does not perform provider calls.",
    ):
        adapter.generate_completion(
            messages=[],
        )
        
@pytest.mark.parametrize(
    "mode",
    [
        "provider_exception",
        "generate_string",
        "generate_result",
        "failover_exception",
    ],
)
def test_ai_orchestrator_execute_provider_paths(mode):
    from app.services.ai.FieldOpsAI.runtime.orchestrator import (
        AIOrchestrator,
        GenerationResult,
        UsageStats,
    )

    orchestrator, budget, cache, circuit, failover = make_ai_orchestrator()

    provider = MagicMock()
    provider.model_name.return_value = "test-model"

    client = MagicMock()

    generated = GenerationResult(
        text="RESULT",
        provider_name="groq",
        model_name="test-model",
        usage=UsageStats(
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            request_count=1,
            latency_ms=1.0,
            cost_usd=0.0,
        ),
    )

    if mode == "generate_string":
        client.generate_result = None
        client.generate.return_value = "RESULT"

    elif mode == "generate_result":
        client.generate_result.return_value = generated

    elif mode == "provider_exception":
        client.generate_result.side_effect = RuntimeError("provider failed")

    orchestrator.provider_client_factory = lambda _: client

    def run_attempt(attempt_runner):
        if mode == "failover_exception":
            raise RuntimeError("failover failed")

        return MagicMock(
            generation_result=attempt_runner(
                "groq",
                provider,
            )
        )

    failover.execute.side_effect = run_attempt

    if mode == "failover_exception":
        with pytest.raises(RuntimeError, match="AI orchestration failed"):
            orchestrator.execute(
                AITask.PLANNING,
                {"tenant_id": "tenant-1"},
            )
    elif mode == "provider_exception":
        from app.services.ai.FieldOpsAI.providers.base_provider import (
            ProviderExecutionError,
        )

        with pytest.raises(
            ProviderExecutionError,
            match="AI provider execution failed",
        ):
            orchestrator.execute(
                AITask.PLANNING,
                {"tenant_id": "tenant-1"},
            )
        
    else:
        result = orchestrator.execute(
            AITask.PLANNING,
            {"tenant_id": "tenant-1"},
        )
        assert result == "RESULT"
        
def test_ai_orchestrator_budget_manager_vars_type_error():
    from app.services.ai.FieldOpsAI.runtime.orchestrator import AIOrchestrator

    budget_manager = MagicMock()
    circuit_breaker = MagicMock()

    with patch(
        "app.services.ai.FieldOpsAI.runtime.orchestrator.vars",
        side_effect=TypeError("vars failed"),
    ), patch(
        "app.services.ai.FieldOpsAI.runtime.orchestrator.get_redis_client",
        return_value=MagicMock(),
    ):
        orchestrator = AIOrchestrator(
            client=MagicMock(),
            budget_manager=budget_manager,
            circuit_breaker=circuit_breaker,
            redis_client=None,
        )

    assert orchestrator is not None
    
def test_ai_orchestrator_injected_client_internal_factory():
    from app.services.ai.FieldOpsAI.runtime.orchestrator import (
        AIOrchestrator,
    )

    provider = MagicMock()
    provider.provider_name.return_value = " TestProvider "
    provider.model_name.return_value = " test-model "

    client = MagicMock()
    client.provider = provider

    with patch(
        "app.services.ai.FieldOpsAI.runtime.orchestrator.ProviderFailoverExecutor"
    ) as executor_cls:

        AIOrchestrator(
            client=client,
            provider_health_monitor=MagicMock(),
            budget_manager=MagicMock(),
            provider_cache=MagicMock(),
            circuit_breaker=MagicMock(),
            redis_client=MagicMock(),
        )

        kwargs = executor_cls.call_args.kwargs

        factory = kwargs["provider_factory"]
        config = kwargs["config"]

        # Lines 364-377
        assert factory.registered_names() == ["testprovider"]
        assert factory.create_provider(" TESTPROVIDER ") is provider

        with pytest.raises(
            Exception,
            match="Configured AI provider is unsupported",
        ):
            factory.create_provider("unsupported")

        # Lines 403-408
        assert config.provider_fallback_order == ["testprovider"]
        
def test_ai_orchestrator_provider_cache_non_dict_config():
    from app.services.ai.FieldOpsAI.runtime.orchestrator import (
        AIOrchestrator,
    )

    client = MagicMock()

    with patch(
        "app.services.ai.FieldOpsAI.runtime.orchestrator.ProviderCacheConfig"
    ) as cache_config_cls, patch(
        "app.services.ai.FieldOpsAI.runtime.orchestrator.SyncProviderCache"
    ) as cache_cls:

        cache_config_cls.return_value = MagicMock()

        with patch(
            "app.services.ai.FieldOpsAI.runtime.orchestrator.ConfigLoader"
        ) as config_cls:
            config = config_cls.return_value
            config.provider_cache = "not-a-dict"

            AIOrchestrator(
                client=client,
                provider_health_monitor=MagicMock(),
                failover_executor=MagicMock(),
                budget_manager=MagicMock(),
                circuit_breaker=MagicMock(),
                redis_client=MagicMock(),
            )

        cache_config_cls.assert_called_once_with()
        cache_cls.assert_called_once()
        
def test_ai_orchestrator_rejects_non_dict_sanitized_context():
    orchestrator, *_ = make_ai_orchestrator()

    sanitization_result = MagicMock()
    sanitization_result.sanitized_data = "not-a-dict"
    sanitization_result.placeholder_map = {}

    orchestrator.pii_sanitizer.sanitize.return_value = sanitization_result

    with pytest.raises(
        TypeError,
        match="Sanitized AI context must be a dictionary",
    ):
        orchestrator.execute(
            AITask.PLANNING,
            {"tenant_id": "tenant-1"},
        )
        
def test_ai_orchestrator_sentiment_category():
    orchestrator, *_ = make_ai_orchestrator()

    orchestrator.failover_executor.execute.return_value = MagicMock(
        generation_result=MagicMock(text="positive")
    )

    orchestrator.pii_sanitizer.restore_data.return_value = "positive"

    result = orchestrator.execute(
        AITask.SENTIMENT,
        {
            "tenant_id": "tenant-1",
            "text": "This service was excellent",
        },
    )

    assert result == "positive"
    
@pytest.mark.parametrize(
    "channel",
    ["sms", "email", "push", "in_app", "portal"],
)
def test_ai_orchestrator_communication_channel_categories(channel):
    orchestrator, *_ = make_ai_orchestrator()

    # The helper's sanitizer output must contain channel.
    orchestrator.pii_sanitizer.sanitize.return_value.sanitized_data = {
        "tenant_id": "tenant-1",
        "job_id": "job-1",
        "channel": channel,
    }

    orchestrator.failover_executor.execute.return_value = MagicMock(
        generation_result=MagicMock(text="message")
    )

    orchestrator.pii_sanitizer.restore_data.return_value = "message"

    result = orchestrator.execute(
        AITask.COMMUNICATION,
        {
            "tenant_id": "tenant-1",
            "channel": channel,
            "text": "Test communication",
        },
    )

    assert result == "message"
    
def test_ai_orchestrator_invalid_provider_model_metadata():
    orchestrator, *_ = make_ai_orchestrator()

    provider = MagicMock()
    provider.model_name.return_value = None

    client = MagicMock()
    orchestrator.provider_client_factory = lambda _: client

    def run_attempt(attempt_runner):
        return MagicMock(
            generation_result=attempt_runner(
                "test-provider",
                provider,
            )
        )

    orchestrator.failover_executor.execute.side_effect = run_attempt

    with pytest.raises(
        Exception,
        match="Invalid provider metadata",
    ):
        orchestrator.execute(
            AITask.PLANNING,
            {
                "tenant_id": "tenant-1",
                "job_id": "job-1",
            },
        )
        
def test_ai_orchestrator_budget_exceeded():
    from app.services.ai.FieldOpsAI.providers.budget import (
        BudgetExceededError,
    )

    orchestrator, budget, cache, circuit, failover = (
        make_ai_orchestrator()
    )

    provider = MagicMock()
    provider.model_name.return_value = "test-model"

    budget.reserve.side_effect = BudgetExceededError(
        "budget exceeded"
    )

    def run_attempt(attempt_runner):
        return MagicMock(
            generation_result=attempt_runner(
                "test-provider",
                provider,
            )
        )

    failover.execute.side_effect = run_attempt

    with pytest.raises(
        Exception,
        match="Daily AI token budget exceeded",
    ):
        orchestrator.execute(
            AITask.PLANNING,
            {
                "tenant_id": "tenant-1",
                "job_id": "job-1",
            },
        )

    budget.reserve.assert_called_once()
    
def test_ai_orchestrator_budget_infrastructure_error():
    from app.services.ai.FieldOpsAI.providers.budget import (
        BudgetInfrastructureError,
    )

    orchestrator, budget, cache, circuit, failover = (
        make_ai_orchestrator()
    )

    provider = MagicMock()
    provider.model_name.return_value = "test-model"

    budget.reserve.side_effect = BudgetInfrastructureError(
        "redis failure"
    )

    def run_attempt(attempt_runner):
        return MagicMock(
            generation_result=attempt_runner(
                "test-provider",
                provider,
            )
        )

    failover.execute.side_effect = run_attempt

    with pytest.raises(
        Exception,
        match="AI budget infrastructure failure",
    ):
        orchestrator.execute(
            AITask.PLANNING,
            {
                "tenant_id": "tenant-1",
                "job_id": "job-1",
            },
        )

    budget.reserve.assert_called_once()
    
def test_ai_orchestrator_provider_client_construction_failure():
    orchestrator, budget, cache, circuit, failover = (
        make_ai_orchestrator()
    )

    provider = MagicMock()
    provider.model_name.return_value = "test-model"

    orchestrator.provider_client_factory = (
        MagicMock(
            side_effect=RuntimeError(
                "client construction failed"
            )
        )
    )

    def run_attempt(attempt_runner):
        return MagicMock(
            generation_result=attempt_runner(
                "test-provider",
                provider,
            )
        )

    failover.execute.side_effect = run_attempt

    with pytest.raises(
        Exception,
        match="Provider client construction failed",
    ):
        orchestrator.execute(
            AITask.PLANNING,
            {
                "tenant_id": "tenant-1",
                "job_id": "job-1",
            },
        )

    orchestrator.provider_client_factory.assert_called_once()
    
def test_ai_orchestrator_provider_has_no_generation_method():
    orchestrator, budget, cache, circuit, failover = (
        make_ai_orchestrator()
    )

    provider = MagicMock()
    provider.model_name.return_value = "test-model"

    client = MagicMock()
    client.generate_result = None
    client.generate = None

    orchestrator.provider_client_factory = lambda _: client

    def run_attempt(attempt_runner):
        return MagicMock(
            generation_result=attempt_runner(
                "test-provider",
                provider,
            )
        )

    failover.execute.side_effect = run_attempt

    with pytest.raises(
        Exception,
        match="Provider client has no supported generation method",
    ):
        orchestrator.execute(
            AITask.PLANNING,
            {
                "tenant_id": "tenant-1",
                "job_id": "job-1",
            },
        )
        
def test_ai_orchestrator_generate_returns_generation_result():
    from app.services.ai.FieldOpsAI.runtime.orchestrator import (
        GenerationResult,
        UsageStats,
    )

    orchestrator, budget, cache, circuit, failover = (
        make_ai_orchestrator()
    )

    provider = MagicMock()
    provider.model_name.return_value = "test-model"

    generated = GenerationResult(
        text="FALLBACK RESULT",
        provider_name="test-provider",
        model_name="test-model",
        usage=UsageStats(
            prompt_tokens=5,
            completion_tokens=3,
            total_tokens=8,
            request_count=1,
            latency_ms=1.0,
            cost_usd=0.0,
        ),
    )

    client = MagicMock()
    client.generate_result = None
    client.generate.return_value = generated

    orchestrator.provider_client_factory = lambda _: client

    def run_attempt(attempt_runner):
        return MagicMock(
            generation_result=attempt_runner(
                "test-provider",
                provider,
            )
        )

    failover.execute.side_effect = run_attempt

    result = orchestrator.execute(
        AITask.PLANNING,
        {
            "tenant_id": "tenant-1",
            "job_id": "job-1",
        },
    )

    assert result == "FALLBACK RESULT"
    
def test_ai_orchestrator_generate_returns_invalid_output():
    orchestrator, budget, cache, circuit, failover = (
        make_ai_orchestrator()
    )

    provider = MagicMock()
    provider.model_name.return_value = "test-model"

    client = MagicMock()
    client.generate_result = None
    client.generate.return_value = 12345

    orchestrator.provider_client_factory = lambda _: client

    def run_attempt(attempt_runner):
        return MagicMock(
            generation_result=attempt_runner(
                "test-provider",
                provider,
            )
        )

    failover.execute.side_effect = run_attempt

    with pytest.raises(
        Exception,
        match="Provider output must be a string or GenerationResult",
    ):
        orchestrator.execute(
            AITask.PLANNING,
            {
                "tenant_id": "tenant-1",
                "job_id": "job-1",
            },
        )
        
def test_ai_orchestrator_invalid_provider_response_type():
        from app.services.ai.FieldOpsAI.runtime.orchestrator import (
            ProviderExecutionError,
        )

        orchestrator, *_ = make_ai_orchestrator()

        provider = MagicMock()
        provider.model_name.return_value = "test-model"

        client = MagicMock()
        client.generate_result.return_value = object()

        orchestrator.provider_client_factory = lambda _: client

        def run_attempt(attempt_runner):
            return MagicMock(
                generation_result=attempt_runner(
                    "groq",
                    provider,
                )
            )

        orchestrator.failover_executor.execute.side_effect = run_attempt

        with pytest.raises(
            ProviderExecutionError,
            match="Invalid provider response metadata",
        ):
            orchestrator.execute(
                AITask.PLANNING,
                {
                    "tenant_id": "tenant-1",
                    "job_id": "job-1",
                },
            )


def test_ai_orchestrator_invalid_provider_response_text():
        from app.services.ai.FieldOpsAI.runtime.orchestrator import (
            GenerationResult,
            ProviderExecutionError,
            UsageStats,
        )

        orchestrator, *_ = make_ai_orchestrator()

        provider = MagicMock()
        provider.model_name.return_value = "test-model"

        client = MagicMock()
        client.generate_result.return_value = GenerationResult.model_construct(
    text="",
    provider_name="groq",
    model_name="test-model",
    usage=UsageStats(
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        request_count=1,
        latency_ms=1.0,
        cost_usd=0.0,
    ),
)

        orchestrator.provider_client_factory = lambda _: client

        def run_attempt(attempt_runner):
            return MagicMock(
                generation_result=attempt_runner(
                    "groq",
                    provider,
                )
            )

        orchestrator.failover_executor.execute.side_effect = run_attempt

        with pytest.raises(
            ProviderExecutionError,
            match="Invalid provider response metadata",
        ):
            orchestrator.execute(
                AITask.PLANNING,
                {
                    "tenant_id": "tenant-1",
                    "job_id": "job-1",
                },
            )


def test_ai_orchestrator_invalid_provider_response_provider_name():
        from app.services.ai.FieldOpsAI.runtime.orchestrator import (
            GenerationResult,
            ProviderExecutionError,
            UsageStats,
        )

        orchestrator, *_ = make_ai_orchestrator()

        provider = MagicMock()
        provider.model_name.return_value = "test-model"

        client = MagicMock()
        client.generate_result.return_value = GenerationResult(
            text="RESULT",
            provider_name="wrong-provider",
            model_name="test-model",
            usage=UsageStats(
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
                request_count=1,
                latency_ms=1.0,
                cost_usd=0.0,
            ),
        )

        orchestrator.provider_client_factory = lambda _: client

        def run_attempt(attempt_runner):
            return MagicMock(
                generation_result=attempt_runner(
                    "groq",
                    provider,
                )
            )

        orchestrator.failover_executor.execute.side_effect = run_attempt

        with pytest.raises(
            ProviderExecutionError,
            match="Invalid provider response metadata",
        ):
            orchestrator.execute(
                AITask.PLANNING,
                {
                    "tenant_id": "tenant-1",
                    "job_id": "job-1",
                },
            )


def test_ai_orchestrator_invalid_provider_response_model_type():
        from app.services.ai.FieldOpsAI.runtime.orchestrator import (
            GenerationResult,
            ProviderExecutionError,
            UsageStats,
        )

        orchestrator, *_ = make_ai_orchestrator()

        provider = MagicMock()
        provider.model_name.return_value = "test-model"

        client = MagicMock()
        client.generate_result.return_value = GenerationResult.model_construct(
    text="RESULT",
    provider_name="groq",
    model_name=None,
    usage=UsageStats(
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        request_count=1,
        latency_ms=1.0,
        cost_usd=0.0,
    ),
)

        orchestrator.provider_client_factory = lambda _: client

        def run_attempt(attempt_runner):
            return MagicMock(
                generation_result=attempt_runner(
                    "groq",
                    provider,
                )
            )

        orchestrator.failover_executor.execute.side_effect = run_attempt

        with pytest.raises(
            ProviderExecutionError,
            match="Invalid provider response metadata",
        ):
            orchestrator.execute(
                AITask.PLANNING,
                {
                    "tenant_id": "tenant-1",
                    "job_id": "job-1",
                },
            )


def test_ai_orchestrator_provider_response_model_mismatch():
        from app.services.ai.FieldOpsAI.runtime.orchestrator import (
            GenerationResult,
            ProviderExecutionError,
            UsageStats,
        )

        orchestrator, *_ = make_ai_orchestrator()

        provider = MagicMock()
        provider.model_name.return_value = "test-model"

        client = MagicMock()
        client.generate_result.return_value = GenerationResult(
            text="RESULT",
            provider_name="groq",
            model_name="different-model",
            usage=UsageStats(
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
                request_count=1,
                latency_ms=1.0,
                cost_usd=0.0,
            ),
        )

        orchestrator.provider_client_factory = lambda _: client

        def run_attempt(attempt_runner):
            return MagicMock(
                generation_result=attempt_runner(
                    "groq",
                    provider,
                )
            )

        orchestrator.failover_executor.execute.side_effect = run_attempt

        with pytest.raises(
            ProviderExecutionError,
            match="Invalid provider response metadata",
        ):
            orchestrator.execute(
                AITask.PLANNING,
                {
                    "tenant_id": "tenant-1",
                    "job_id": "job-1",
                },
            )


def test_ai_orchestrator_invalid_provider_response_usage():
        from app.services.ai.FieldOpsAI.runtime.orchestrator import (
            GenerationResult,
            ProviderExecutionError,
        )

        orchestrator, *_ = make_ai_orchestrator()

        provider = MagicMock()
        provider.model_name.return_value = "test-model"

        client = MagicMock()
        client.generate_result.return_value = GenerationResult.model_construct(
    text="RESULT",
    provider_name="groq",
    model_name="test-model",
    usage=object(),
)

        orchestrator.provider_client_factory = lambda _: client

        def run_attempt(attempt_runner):
            return MagicMock(
                generation_result=attempt_runner(
                    "groq",
                    provider,
                )
            )

        orchestrator.failover_executor.execute.side_effect = run_attempt

        with pytest.raises(
            ProviderExecutionError,
            match="Invalid provider response metadata",
        ):
            orchestrator.execute(
                AITask.PLANNING,
                {
                    "tenant_id": "tenant-1",
                    "job_id": "job-1",
                },
            )
def test_ai_orchestrator_budget_cancel_failure():
    orchestrator, budget, *_ = make_ai_orchestrator()

    provider = MagicMock()
    provider.model_name.return_value = "test-model"

    client = MagicMock()

    client.generate_result.side_effect = RuntimeError(
        "Provider failed"
    )

    orchestrator.provider_client_factory = lambda _: client

    # Make cleanup cancel() fail after the provider failure.
    budget.cancel.side_effect = RuntimeError(
        "Redis unavailable"
    )

    def run_attempt(attempt_runner):
        return MagicMock(
            generation_result=attempt_runner(
                "groq",
                provider,
            )
        )

    orchestrator.failover_executor.execute.side_effect = run_attempt

    with pytest.raises(
        Exception,
        match="AI budget infrastructure failure",
    ):
        orchestrator.execute(
            AITask.PLANNING,
            {
                "tenant_id": "tenant-1",
                "job_id": "job-1",
            },
        )
        
def test_ai_orchestrator_circuit_breaker_failure():
    orchestrator, budget, cache, circuit, failover = (
        make_ai_orchestrator()
    )

    provider = MagicMock()
    provider.model_name.return_value = "test-model"

    client = MagicMock()

    client.generate_result.side_effect = RuntimeError(
        "Provider failed"
    )

    orchestrator.provider_client_factory = lambda _: client

    circuit.record_failure.side_effect = RuntimeError(
        "Circuit breaker failed"
    )

    def run_attempt(attempt_runner):
        return MagicMock(
            generation_result=attempt_runner(
                "groq",
                provider,
            )
        )

    failover.execute.side_effect = run_attempt

    with pytest.raises(
        Exception,
        match="Circuit breaker infrastructure failure",
    ):
        orchestrator.execute(
            AITask.PLANNING,
            {
                "tenant_id": "tenant-1",
                "job_id": "job-1",
            },
        )

def test_ai_orchestrator_generation_result_missing():
    orchestrator, budget, cache, circuit, failover = (
        make_ai_orchestrator()
    )

    def run_attempt(attempt_runner):
        return MagicMock(
            generation_result=None
        )

    failover.execute.side_effect = run_attempt

    with pytest.raises(
        Exception,
        match="AI provider execution failed",
    ):
        orchestrator.execute(
            AITask.PLANNING,
            {
                "tenant_id": "tenant-1",
                "job_id": "job-1",
            },
        )
        
def test_ai_orchestrator_restore_response_invalid_type():
    orchestrator, budget, cache, circuit, failover = (
        make_ai_orchestrator()
    )

    provider = MagicMock()
    provider.model_name.return_value = "test-model"

    client = MagicMock()

    from app.services.ai.FieldOpsAI.runtime.orchestrator import (
        GenerationResult,
        UsageStats,
    )

    client.generate_result.return_value = GenerationResult(
        text="RESULT",
        provider_name="groq",
        model_name="test-model",
        usage=UsageStats(
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            request_count=1,
            latency_ms=1.0,
            cost_usd=0.0,
        ),
    )

    orchestrator.provider_client_factory = lambda _: client

    # Make the actual restore_data() call return an invalid type.
    orchestrator.pii_sanitizer.restore_data = MagicMock(
        return_value={"invalid": "response"}
    )

    def run_attempt(attempt_runner):
        return MagicMock(
            generation_result=attempt_runner(
                "groq",
                provider,
            )
        )

    failover.execute.side_effect = run_attempt

    with pytest.raises(
        TypeError,
        match="Restored AI response must be a string",
    ):
        orchestrator.execute(
            AITask.PLANNING,
            {
                "tenant_id": "tenant-1",
                "job_id": "job-1",
            },
        )

    orchestrator.pii_sanitizer.restore_data.assert_called_once()
    
def test_ai_orchestrator_runtime_name():
    orchestrator, *_ = make_ai_orchestrator()

    assert orchestrator.runtime_name() == "FieldOps AI Runtime"

def test_ai_orchestrator_health_check_missing_dependency():
    orchestrator, *_ = make_ai_orchestrator()

    orchestrator.pii_sanitizer = None

    assert orchestrator.health_check() is False

def test_ai_orchestrator_budget_reconcile_exceeded():
    from app.services.ai.FieldOpsAI.providers.budget import (
        BudgetExceededError,
    )

    orchestrator, budget, *_ = make_ai_orchestrator()

    provider = MagicMock()
    provider.model_name.return_value = "test-model"

    client = MagicMock()

    from app.services.ai.FieldOpsAI.runtime.orchestrator import (
        GenerationResult,
        UsageStats,
    )

    client.generate_result.return_value = GenerationResult(
        text="RESULT",
        provider_name="groq",
        model_name="test-model",
        usage=UsageStats(
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            request_count=1,
            latency_ms=1.0,
            cost_usd=0.0,
        ),
    )

    orchestrator.provider_client_factory = lambda _: client

    budget.reconcile.side_effect = BudgetExceededError()

    def run_attempt(attempt_runner):
        return MagicMock(
            generation_result=attempt_runner(
                "groq",
                provider,
            )
        )

    orchestrator.failover_executor.execute.side_effect = run_attempt

    with pytest.raises(
        Exception,
        match="AI token budget overrun detected",
    ):
        orchestrator.execute(
            AITask.PLANNING,
            {
                "tenant_id": "tenant-1",
                "job_id": "job-1",
            },
        )
        
def test_ai_orchestrator_budget_reconcile_infrastructure_error():
    orchestrator, budget, *_ = make_ai_orchestrator()

    provider = MagicMock()
    provider.model_name.return_value = "test-model"

    client = MagicMock()

    from app.services.ai.FieldOpsAI.runtime.orchestrator import (
        GenerationResult,
        UsageStats,
    )

    client.generate_result.return_value = GenerationResult(
        text="RESULT",
        provider_name="groq",
        model_name="test-model",
        usage=UsageStats(
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            request_count=1,
            latency_ms=1.0,
            cost_usd=0.0,
        ),
    )

    orchestrator.provider_client_factory = lambda _: client

    budget.reconcile.side_effect = RuntimeError(
        "Redis failed"
    )

    def run_attempt(attempt_runner):
        return MagicMock(
            generation_result=attempt_runner(
                "groq",
                provider,
            )
        )

    orchestrator.failover_executor.execute.side_effect = run_attempt

    with pytest.raises(
        Exception,
        match="AI budget infrastructure failure",
    ):
        orchestrator.execute(
            AITask.PLANNING,
            {
                "tenant_id": "tenant-1",
                "job_id": "job-1",
            },
        )
        
def test_ai_orchestrator_response_schema_parsing():
    orchestrator, budget, cache, circuit, failover = (
        make_ai_orchestrator()
    )

    provider = MagicMock()
    provider.model_name.return_value = "test-model"

    client = MagicMock()

    from app.services.ai.FieldOpsAI.runtime.orchestrator import (
        GenerationResult,
        UsageStats,
    )

    client.generate_result.return_value = GenerationResult(
        text='{"status": "success"}',
        provider_name="groq",
        model_name="test-model",
        usage=UsageStats(
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            request_count=1,
            latency_ms=1.0,
            cost_usd=0.0,
        ),
    )

    orchestrator.provider_client_factory = lambda _: client

    response_schema = MagicMock()
    response_schema.__name__ = "TestResponse"

    def run_attempt(attempt_runner):
        return MagicMock(
            generation_result=attempt_runner(
                "groq",
                provider,
            )
        )

    failover.execute.side_effect = run_attempt

    result = orchestrator.execute(
        AITask.PLANNING,
        {
            "tenant_id": "tenant-1",
            "job_id": "job-1",
        },
        response_schema=response_schema,
    )

    assert result is not None
        
def test_ai_orchestrator_health_check_exception():
    from app.services.ai.FieldOpsAI.runtime.orchestrator import (
        AIOrchestrator,
    )

    class BrokenOrchestrator:
        @property
        def pii_sanitizer(self):
            raise RuntimeError("broken")

        @property
        def failover_executor(self):
            return object()

    assert (
        AIOrchestrator.health_check(
            BrokenOrchestrator()
        )
        is False
    )
    
def test_ai_orchestrator_generation_result_none_fallback():
    orchestrator, budget, cache, circuit, failover = (
        make_ai_orchestrator()
    )

    provider = MagicMock()
    provider.model_name.return_value = "test-model"

    from app.services.ai.FieldOpsAI.runtime.orchestrator import (
        GenerationResult,
        UsageStats,
    )

    client = MagicMock()

    client.generate_result.return_value = GenerationResult(
        text="test response",
        provider_name="groq",
        model_name="test-model",
        usage=UsageStats(
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            request_count=1,
            latency_ms=1.0,
            cost_usd=0.0,
        ),
    )

    orchestrator.provider_client_factory = lambda _: client

    def run_attempt(attempt_runner):
        # This must succeed so execution reaches the
        # failover_result.generation_result check.
        attempt_runner(
            "groq",
            provider,
        )

        # Then deliberately return a failover result
        # without a generation result.
        return MagicMock(
            generation_result=None
        )

    failover.execute.side_effect = run_attempt

    with pytest.raises(
        Exception,
        match="AI provider execution failed",
    ):
        orchestrator.execute(
            AITask.PLANNING,
            {
                "tenant_id": "tenant-1",
                "job_id": "job-1",
            },
        )
