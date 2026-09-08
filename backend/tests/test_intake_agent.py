import asyncio
import pytest
from app.services.ai.FieldOpsAI.config.agent_config_manager import AgentConfigManager
from app.services.ai.FieldOpsAI.schemas.ai_task import AITask
from app.services.ai.FieldOpsAI.schemas.intake import IntakeDecision
from app.services.ai.FieldOpsAI.agents.intake_agent import IntakeAgent


def test_intake_agent_real_execution():
    tenant_id = "test-tenant"

    config = AgentConfigManager().resolve(
        agent_type=AITask.INTAKE,
        tenant_id=tenant_id,
    )

    agent = IntakeAgent(config=config)

    context = {
        "tenant_id": tenant_id,
        "job_id": 1001,
        "customer": {
            "name": "Test Customer",
        },
        "request": "My AC is not cooling",
        "location": {
            "address": "Chennai",
        },
        "priority": "HIGH",
        "required_skill": "AC Technician",
    }

    async def run_test():
        await agent.setup()
        return await agent.execute(context)

    decision = asyncio.run(run_test())

    assert decision is not None
    assert isinstance(decision, IntakeDecision)

    assert decision.problem.summary is not None
    assert decision.problem.summary.strip()
    assert any(
        keyword.lower() in decision.problem.summary.lower()
        for keyword in ["cooling", "not cooling"]
    )


    assert decision.job_id == 1001
    assert decision.customer.name == "Test Customer"
    assert decision.location is not None
    assert decision.location.address == "Chennai"
    assert decision.priority == "HIGH"
    assert decision.required_skill == "AC Technician"

def test_intake_agent_returns_structured_decision(monkeypatch):
    tenant_id = "test-tenant"

    config = AgentConfigManager().resolve(
        agent_type=AITask.INTAKE,
        tenant_id=tenant_id,
    )

    agent = IntakeAgent(config=config)

    expected_decision = IntakeDecision(
        job_id=1001,
        customer={
            "name": "Test Customer",
        },
        service={
            "name": "Air Conditioning",
            "keywords": ["AC"],
        },
        problem={
            "summary": "AC is not cooling",
            "keywords": ["AC", "cooling"],
        },
        schedule={
            "requested_date": None,
            "time_constraint": None,
        },
        location={
            "address": "Chennai",
        },
        priority="HIGH",
        required_skill="AC Technician",
        original_request="My AC is not cooling",
    )

    def fake_execute(*args, **kwargs):
        return expected_decision

    monkeypatch.setattr(
        agent.orchestrator,
        "execute",
        fake_execute,
    )

    context = {
        "tenant_id": tenant_id,
        "job_id": 1001,
        "customer": {
            "name": "Test Customer",
        },
        "request": "My AC is not cooling",
        "location": {
            "address": "Chennai",
        },
        "priority": "HIGH",
        "required_skill": "AC Technician",
    }

    async def run_test():
        await agent.setup()
        return await agent.execute(context)

    decision = asyncio.run(run_test())

    assert isinstance(decision, IntakeDecision)
    assert decision.job_id == 1001
    assert decision.customer.name == "Test Customer"
    assert decision.service.name == "Air Conditioning"
    assert decision.problem.summary == "AC is not cooling"
    assert decision.location.address == "Chennai"
    assert decision.priority == "HIGH"
    assert decision.required_skill == "AC Technician"


def test_intake_agent_rejects_missing_tenant_id():
    tenant_id = "test-tenant"

    config = AgentConfigManager().resolve(
        agent_type=AITask.INTAKE,
        tenant_id=tenant_id,
    )

    agent = IntakeAgent(config=config)

    context = {
        "job_id": 1001,
        "customer": {
            "name": "Test Customer",
        },
        "request": "My AC is not cooling",
    }

    async def run_test():
        await agent.setup()
        return await agent.execute(context)

    with pytest.raises(Exception):
        asyncio.run(run_test())


def test_intake_agent_rejects_wrong_tenant():
    agent_tenant = "tenant-A"
    request_tenant = "tenant-B"

    config = AgentConfigManager().resolve(
        agent_type=AITask.INTAKE,
        tenant_id=agent_tenant,
    )

    agent = IntakeAgent(config=config)

    context = {
        "tenant_id": request_tenant,
        "job_id": 1001,
        "customer": {
            "name": "Test Customer",
        },
        "request": "My AC is not cooling",
    }

    async def run_test():
        await agent.setup()
        return await agent.execute(context)

    with pytest.raises(Exception):
        asyncio.run(run_test())


def test_intake_agent_rejects_terminated_agent():
    tenant_id = "test-tenant"

    config = AgentConfigManager().resolve(
        agent_type=AITask.INTAKE,
        tenant_id=tenant_id,
    )

    agent = IntakeAgent(config=config)

    async def run_test():
        await agent.setup()

        # Move the agent to terminated state.
        await agent.terminate()

        context = {
            "tenant_id": tenant_id,
            "job_id": 1001,
            "customer": {
                "name": "Test Customer",
            },
            "request": "My AC is not cooling",
        }

        return await agent.execute(context)

    with pytest.raises(Exception):
        asyncio.run(run_test())