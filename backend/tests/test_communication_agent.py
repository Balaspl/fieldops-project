"""
test_communication_agent.py

Unit tests for CommunicationAgent under the BaseAgent framework.
"""

from __future__ import annotations

import asyncio

import pytest
from unittest.mock import MagicMock, patch
from pydantic import ValidationError

from app.services.ai.FieldOpsAI.agents.communication_agent import (
    CommunicationAgent,
)
from app.services.ai.FieldOpsAI.agents.base import (
    BaseAgent,
    AgentState,
    AgentLifecycleError,
    TenantIsolationError,
)
from app.services.ai.FieldOpsAI.schemas.agent_config import AgentConfig
from app.services.ai.FieldOpsAI.schemas.ai_task import AITask
from app.services.ai.FieldOpsAI.schemas.communication import (
    CommunicationContext,
    CommunicationDecision,
)
from app.services.ai.FieldOpsAI.runtime.orchestrator import AIOrchestrator
from app.services.ai.FieldOpsAI.runtime.lifecycle import AgentLifecycle
from app.services.ai.FieldOpsAI.runtime.agent_pool import AgentPool
from app.services.ai.FieldOpsAI.schemas.agent_result import AgentResultStatus


# ============================================================================
# Fixtures / Helpers
# ============================================================================


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def build_config(
    *,
    agent_type: AITask = AITask.COMMUNICATION,
    tenant_id: str = "tenant-abc",
    enabled: bool = True,
) -> AgentConfig:
    return AgentConfig(
        agent_type=agent_type,
        tenant_id=tenant_id,
        enabled=enabled,
        timeout_seconds=5.0,
    )


def build_valid_context() -> dict:
    return {
        "tenant_id": "tenant-abc",
        "job_id": "job-123",
        "notification_type": "job_assigned",
        "recipient_type": "CUSTOMER",
        "channel": "SMS",
        "job_status": "ASSIGNED",
    }


def build_expected_decision(
    *,
    channel: str = "SMS",
    message: str = "Test message",
) -> CommunicationDecision:
    """
    Build a valid CommunicationDecision for the requested channel.

    IMPORTANT:
    The channel returned by the mocked orchestrator must match the
    channel requested by the CommunicationAgent. Otherwise the real
    MessageValidator can correctly reject the response.
    """

    if channel == "SMS":
        return CommunicationDecision(
            channel="SMS",
            output={
                "channel": "SMS",
                "text": message,
            },
            tone="PROFESSIONAL",
            confidence=0.95,
        )

    if channel == "EMAIL":
        return CommunicationDecision(
            channel="EMAIL",
            output={
                "channel": "EMAIL",
                "subject": "Test subject",
                "text_body": message,
            },
            tone="PROFESSIONAL",
            confidence=0.95,
        )

    if channel == "PUSH":
        return CommunicationDecision(
            channel="PUSH",
            output={
                "channel": "PUSH",
                "title": "Test title",
                "body": message,
            },
            tone="PROFESSIONAL",
            confidence=0.95,
        )

    if channel in ("IN_APP", "PORTAL"):
        return CommunicationDecision(
            channel="IN_APP" if channel == "IN_APP" else "PORTAL",
            output={
                "channel": "PORTAL",
                "title": "Test title",
                "body": message,
            },
            tone="PROFESSIONAL",
            confidence=0.95,
        )

    raise ValueError(f"Unsupported test channel: {channel}")


# ============================================================================
# BaseAgent / Configuration
# ============================================================================


def test_subclass_check() -> None:
    config = build_config()

    agent = CommunicationAgent(config=config)

    assert isinstance(agent, BaseAgent)


def test_correct_config_accepted() -> None:
    config = build_config()

    _ = CommunicationAgent(config=config)


def test_non_communication_config_rejected() -> None:
    config = build_config(
        agent_type=AITask.PLANNING,
    )

    with pytest.raises(
        ValueError,
        match="requires an AITask.COMMUNICATION configuration",
    ):
        _ = CommunicationAgent(config=config)


# ============================================================================
# run()
# ============================================================================


@pytest.mark.anyio
async def test_run_validates_context() -> None:
    config = build_config()

    mock_orchestrator = MagicMock(
        spec=AIOrchestrator,
    )

    agent = CommunicationAgent(
        config=config,
        orchestrator=mock_orchestrator,
    )

    invalid_context = {
        "tenant_id": "tenant-abc",
    }

    await agent.setup()

    with pytest.raises(ValidationError):
        await agent.run(invalid_context)

    mock_orchestrator.execute.assert_not_called()


@pytest.mark.anyio
async def test_tenant_id_removed_before_validation() -> None:
    config = build_config()

    mock_orchestrator = MagicMock(
        spec=AIOrchestrator,
    )

    expected_decision = build_expected_decision()

    mock_orchestrator.execute.return_value = (
        expected_decision
    )

    agent = CommunicationAgent(
        config=config,
        orchestrator=mock_orchestrator,
    )

    await agent.setup()

    valid_context = build_valid_context()

    decision = await agent.run(valid_context)

    assert decision == expected_decision

    mock_orchestrator.execute.assert_called_once()

    called_args = mock_orchestrator.execute.call_args[1]

    assert "tenant_id" not in called_args["context"]


@pytest.mark.anyio
async def test_run_applies_personalization_when_template_exists() -> None:
    config = build_config()

    mock_orchestrator = MagicMock(
        spec=AIOrchestrator,
    )

    expected_decision = build_expected_decision(
        message="Personalized message",
    )

    mock_orchestrator.execute.return_value = (
        expected_decision
    )

    mock_personalization = MagicMock()

    mock_personalization.ai_enhance.return_value = (
        "Hello Test Customer, your technician is on the way."
    )

    agent = CommunicationAgent(
        config=config,
        orchestrator=mock_orchestrator,
        personalization_pipeline=mock_personalization,
    )

    await agent.setup()

    valid_context = {
        "tenant_id": "tenant-abc",
        "job_id": "job-123",
        "notification_type": "job_assigned",
        "recipient_type": "CUSTOMER",
        "channel": "SMS",
        "locale": "en",
        "job_status": "ASSIGNED",
        "template": "Hello {{ customer_name }}",
        "customer_name": "Test Customer",
    }

    decision = await agent.run(valid_context)

    assert decision == expected_decision

    mock_personalization.ai_enhance.assert_called_once()

    mock_orchestrator.execute.assert_called_once()

    called_context = (
        mock_orchestrator
        .execute
        .call_args
        .kwargs["context"]
    )

    assert (
        called_context["additional_context"]
        == "Hello Test Customer, your technician is on the way."
    )


@pytest.mark.anyio
async def test_personalize_uses_personalization_pipeline() -> None:
    config = build_config()

    mock_personalization = MagicMock()

    mock_personalization.apply_template.return_value = (
        "Hello Test Customer"
    )

    agent = CommunicationAgent(
        config=config,
        personalization_pipeline=mock_personalization,
    )

    result = agent.personalize(
        template="Hello {{ customer_name }}",
        context={
            "customer_name": "Test Customer",
        },
    )

    assert result == "Hello Test Customer"

    mock_personalization.apply_template.assert_called_once_with(
        template="Hello {{ customer_name }}",
        variables={
            "customer_name": "Test Customer",
        },
    )


@pytest.mark.anyio
async def test_run_raises_fallback_error_when_validation_requires_fallback() -> None:
    config = build_config()

    mock_orchestrator = MagicMock(
        spec=AIOrchestrator,
    )

    expected_decision = build_expected_decision()

    mock_orchestrator.execute.return_value = (
        expected_decision
    )

    mock_validator = MagicMock()

    mock_validator.validate.return_value = MagicMock(
        passed=False,
        requires_fallback=True,
    )

    agent = CommunicationAgent(
        config=config,
        orchestrator=mock_orchestrator,
        message_validator=mock_validator,
    )

    await agent.setup()

    valid_context = build_valid_context()

    with pytest.raises(
        ValueError,
        match="requires fallback",
    ):
        await agent.run(valid_context)

    mock_validator.validate.assert_called_once()


@pytest.mark.anyio
async def test_run_raises_validation_error_without_fallback() -> None:
    config = build_config()

    mock_orchestrator = MagicMock(
        spec=AIOrchestrator,
    )

    expected_decision = build_expected_decision()

    mock_orchestrator.execute.return_value = (
        expected_decision
    )

    mock_validator = MagicMock()

    mock_validator.validate.return_value = MagicMock(
        passed=False,
        requires_fallback=False,
    )

    agent = CommunicationAgent(
        config=config,
        orchestrator=mock_orchestrator,
        message_validator=mock_validator,
    )

    await agent.setup()

    valid_context = build_valid_context()

    with pytest.raises(
        ValueError,
        match="Generated communication failed message validation.",
    ):
        await agent.run(valid_context)

    mock_validator.validate.assert_called_once()


# ============================================================================
# Tenant isolation / execution
# ============================================================================


@pytest.mark.anyio
async def test_tenant_mismatch_rejected_by_base_agent() -> None:
    config = build_config(
        tenant_id="tenant-abc",
    )

    mock_orchestrator = MagicMock(
        spec=AIOrchestrator,
    )

    agent = CommunicationAgent(
        config=config,
        orchestrator=mock_orchestrator,
    )

    await agent.setup()

    mismatch_context = {
        "tenant_id": "tenant-xyz",
        "job_id": "job-123",
        "notification_type": "job_assigned",
        "recipient_type": "CUSTOMER",
        "channel": "SMS",
        "job_status": "ASSIGNED",
    }

    with pytest.raises(TenantIsolationError):
        await agent.execute(mismatch_context)


@pytest.mark.anyio
async def test_orchestrator_execute_invoked_exactly_once() -> None:
    config = build_config()

    mock_orchestrator = MagicMock(
        spec=AIOrchestrator,
    )

    expected_decision = build_expected_decision()

    mock_orchestrator.execute.return_value = (
        expected_decision
    )

    agent = CommunicationAgent(
        config=config,
        orchestrator=mock_orchestrator,
    )

    await agent.setup()

    valid_context = build_valid_context()

    decision = await agent.execute(valid_context)

    assert decision == expected_decision

    mock_orchestrator.execute.assert_called_once()


@pytest.mark.anyio
async def test_orchestrator_execution_is_offloaded() -> None:
    config = build_config()

    mock_orchestrator = MagicMock(
        spec=AIOrchestrator,
    )

    with patch(
        "asyncio.to_thread",
        wraps=asyncio.to_thread,
    ) as mock_to_thread:

        expected_decision = build_expected_decision()

        mock_orchestrator.execute.return_value = (
            expected_decision
        )

        agent = CommunicationAgent(
            config=config,
            orchestrator=mock_orchestrator,
        )

        await agent.setup()

        valid_context = build_valid_context()

        decision = await agent.run(valid_context)

        assert decision == expected_decision

        mock_to_thread.assert_called_once()


@pytest.mark.anyio
async def test_invalid_output_type_rejected() -> None:
    config = build_config()

    mock_orchestrator = MagicMock(
        spec=AIOrchestrator,
    )

    mock_orchestrator.execute.return_value = {
        "channel": "SMS",
        "message": "hello",
    }

    agent = CommunicationAgent(
        config=config,
        orchestrator=mock_orchestrator,
    )

    await agent.setup()

    valid_context = build_valid_context()

    with pytest.raises(
        TypeError,
        match="Returned object is not a CommunicationDecision",
    ):
        await agent.execute(valid_context)

    assert agent.state == AgentState.ERROR

    mock_orchestrator.execute.assert_called_once()


@pytest.mark.anyio
async def test_orchestrator_failure_follows_base_agent_error_behavior() -> None:
    config = build_config()

    mock_orchestrator = MagicMock(
        spec=AIOrchestrator,
    )

    mock_orchestrator.execute.side_effect = RuntimeError(
        "API Limit Reached",
    )

    agent = CommunicationAgent(
        config=config,
        orchestrator=mock_orchestrator,
    )

    await agent.setup()

    valid_context = build_valid_context()

    with pytest.raises(
        RuntimeError,
        match="API Limit Reached",
    ):
        await agent.execute(valid_context)

    assert agent.state == AgentState.ERROR

    mock_orchestrator.execute.assert_called_once()


# ============================================================================
# generate()
# ============================================================================


def test_synchronous_generate_works_outside_event_loop() -> None:
    config = build_config()

    mock_orchestrator = MagicMock(
        spec=AIOrchestrator,
    )

    expected_decision = build_expected_decision()

    mock_orchestrator.execute.return_value = (
        expected_decision
    )

    agent = CommunicationAgent(
        config=config,
        orchestrator=mock_orchestrator,
    )

    context = CommunicationContext(
        job_id="job-123",
        notification_type="job_assigned",
        recipient_type="CUSTOMER",
        channel="SMS",
        job_status="ASSIGNED",
    )

    decision = agent.generate(context)

    assert decision == expected_decision

    mock_orchestrator.execute.assert_called_once()

    assert agent.state == AgentState.TERMINATED


@pytest.mark.anyio
async def test_synchronous_generate_rejects_active_event_loop() -> None:
    config = build_config()

    agent = CommunicationAgent(
        config=config,
    )

    context = CommunicationContext(
        job_id="job-123",
        notification_type="job_assigned",
        recipient_type="CUSTOMER",
        channel="SMS",
        job_status="ASSIGNED",
    )

    with pytest.raises(
        RuntimeError,
        match="cannot be called from an active event loop",
    ):
        agent.generate(context)


def test_terminated_agents_not_reused() -> None:
    config = build_config()

    mock_orchestrator = MagicMock(
        spec=AIOrchestrator,
    )

    expected_decision = build_expected_decision()

    mock_orchestrator.execute.return_value = (
        expected_decision
    )

    agent = CommunicationAgent(
        config=config,
        orchestrator=mock_orchestrator,
    )

    context = CommunicationContext(
        job_id="job-123",
        notification_type="job_assigned",
        recipient_type="CUSTOMER",
        channel="SMS",
        job_status="ASSIGNED",
    )

    decision = agent.generate(context)

    assert decision == expected_decision
    assert agent.state == AgentState.TERMINATED

    with pytest.raises(
        AgentLifecycleError,
        match="A terminated agent cannot execute work",
    ):
        agent.generate(context)


@pytest.mark.anyio
async def test_lifecycle_clean_teardown() -> None:
    config = build_config()

    mock_orchestrator = MagicMock(
        spec=AIOrchestrator,
    )

    expected_decision = build_expected_decision()

    mock_orchestrator.execute.return_value = (
        expected_decision
    )

    agent = CommunicationAgent(
        config=config,
        orchestrator=mock_orchestrator,
    )

    pool = AgentPool()

    async with AgentLifecycle(
        agent=agent,
        pool=pool,
    ) as lifecycle:

        assert agent.state == AgentState.IDLE
        assert agent.is_setup

        assert await pool.contains(
            agent_id=agent.agent_id,
            tenant_id=agent.tenant_id,
        )

        valid_context = build_valid_context()

        result = await lifecycle.execute(
            valid_context,
        )

        assert result.status == AgentResultStatus.SUCCESS
        assert result.output == expected_decision

    assert agent.state == AgentState.TERMINATED
    assert not agent.is_setup

    assert not await pool.contains(
        agent_id=agent.agent_id,
        tenant_id=agent.tenant_id,
    )


def test_synchronous_generate_fails_on_unsuccessful_status() -> None:
    config = build_config()

    mock_orchestrator = MagicMock(
        spec=AIOrchestrator,
    )

    mock_orchestrator.execute.side_effect = RuntimeError(
        "API execution failed",
    )

    agent = CommunicationAgent(
        config=config,
        orchestrator=mock_orchestrator,
    )

    context = CommunicationContext(
        job_id="job-123",
        notification_type="job_assigned",
        recipient_type="CUSTOMER",
        channel="SMS",
        job_status="ASSIGNED",
    )

    with pytest.raises(
        RuntimeError,
        match=(
            "Communication agent execution failed with status: "
            "AgentResultStatus.FAILED"
        ),
    ):
        agent.generate(context)

    mock_orchestrator.execute.assert_called_once()

    assert agent.state == AgentState.TERMINATED


def test_synchronous_generate_fails_on_invalid_output_type() -> None:
    config = build_config()

    agent = CommunicationAgent(
        config=config,
    )

    context = CommunicationContext(
        job_id="job-123",
        notification_type="job_assigned",
        recipient_type="CUSTOMER",
        channel="SMS",
        job_status="ASSIGNED",
    )

    from app.services.ai.FieldOpsAI.schemas.agent_result import (
        AgentResult,
    )

    fake_result = AgentResult(
        output="not a decision",
        status=AgentResultStatus.SUCCESS,
        latency_ms=10.0,
        tokens_used=0,
        agent_id=str(agent.agent_id),
        correlation_id="corr-123",
    )

    with patch.object(
        AgentLifecycle,
        "execute",
        return_value=fake_result,
    ):
        with pytest.raises(
            TypeError,
            match="Communication agent returned an invalid output type",
        ):
            agent.generate(context)

    assert agent.state == AgentState.TERMINATED


def test_falsey_injected_orchestrator_is_preserved() -> None:
    config = build_config()

    class FalseyOrchestrator:
        def __bool__(self) -> bool:
            return False

    falsey_orchestrator = FalseyOrchestrator()

    agent = CommunicationAgent(
        config=config,
        orchestrator=falsey_orchestrator,
    )

    assert agent.orchestrator is falsey_orchestrator


def test_communication_timeout_configuration() -> None:
    from app.services.ai.FieldOpsAI.config.agent_config_manager import (
        AgentConfigManager,
    )

    config = AgentConfigManager().resolve(
        agent_type=AITask.COMMUNICATION,
        tenant_id="tenant-abc",
    )

    assert config.timeout_seconds == 5.0


# ============================================================================
# generate_message()
# ============================================================================


@pytest.mark.anyio
async def test_generate_message_returns_communication_decision() -> None:
    config = build_config()

    mock_orchestrator = MagicMock(
        spec=AIOrchestrator,
    )

    expected_decision = build_expected_decision()

    mock_orchestrator.execute.return_value = (
        expected_decision
    )

    agent = CommunicationAgent(
        config=config,
        orchestrator=mock_orchestrator,
    )

    result = await agent.generate_message(
        build_valid_context(),
    )

    assert isinstance(
        result,
        CommunicationDecision,
    )

    assert result == expected_decision

    mock_orchestrator.execute.assert_called_once()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("channel", "expected_channel"),
    [
        ("sms", "SMS"),
        ("SMS", "SMS"),
        ("email", "EMAIL"),
        ("push", "PUSH"),
        ("portal", "IN_APP"),
    ],
)
async def test_generate_message_channel_routing(
    channel: str,
    expected_channel: str,
) -> None:
    config = build_config()

    mock_orchestrator = MagicMock(
        spec=AIOrchestrator,
    )

    # IMPORTANT:
    # The mocked AI response must match the requested channel.
    expected_decision = build_expected_decision(
        channel=expected_channel,
    )

    mock_orchestrator.execute.return_value = (
        expected_decision
    )

    agent = CommunicationAgent(
        config=config,
        orchestrator=mock_orchestrator,
    )

    await agent.generate_message(
        build_valid_context(),
        channel=channel,
    )

    call = mock_orchestrator.execute.call_args

    assert call is not None

    generated_context = call.kwargs["context"]

    assert generated_context["channel"] == expected_channel


@pytest.mark.anyio
async def test_generate_message_uses_template_key() -> None:
    config = build_config()

    mock_orchestrator = MagicMock(
        spec=AIOrchestrator,
    )

    expected_decision = build_expected_decision()

    mock_orchestrator.execute.return_value = (
        expected_decision
    )

    agent = CommunicationAgent(
        config=config,
        orchestrator=mock_orchestrator,
    )

    context = build_valid_context()

    context["notification_type"] = "old_template"

    await agent.generate_message(
        context,
        template_key="job_assigned",
    )

    call = mock_orchestrator.execute.call_args

    assert call is not None

    generated_context = call.kwargs["context"]

    assert (
        generated_context["notification_type"]
        == "job_assigned"
    )


@pytest.mark.anyio
async def test_generate_message_rejects_invalid_channel() -> None:
    config = build_config()

    agent = CommunicationAgent(
        config=config,
    )

    with pytest.raises(
        ValueError,
        match="Unsupported communication channel",
    ):
        await agent.generate_message(
            build_valid_context(),
            channel="whatsapp",
        )


@pytest.mark.anyio
async def test_generate_message_rejects_empty_template_key() -> None:
    config = build_config()

    agent = CommunicationAgent(
        config=config,
    )

    with pytest.raises(
        ValueError,
        match="template_key cannot be empty",
    ):
        await agent.generate_message(
            build_valid_context(),
            template_key="   ",
        )

# ============================================================================
# Additional coverage: AI timeout + managed Jinja2 fallback
# ============================================================================


@pytest.mark.anyio
async def test_ai_timeout_uses_jinja2_fallback() -> None:
    config = build_config()

    mock_orchestrator = MagicMock(spec=AIOrchestrator)

    agent = CommunicationAgent(
        config=config,
        orchestrator=mock_orchestrator,
        db=MagicMock(),
    )

    await agent.setup()

    fallback_decision = build_expected_decision(
        channel="SMS",
        message="Fallback message",
    )

    with patch.object(
        agent,
        "_generate_with_ai",
        side_effect=TimeoutError("AI timed out"),
    ), patch(
        "app.services.ai.FieldOpsAI.agents.communication_agent_impl.render_managed_template"
    ) as mock_render:

        mock_render.return_value = MagicMock(
            body="Fallback message",
            title=None,
            template_id=10,
            template_version=1,
            source="managed",
            template_format="text",
        )

        with patch.object(
            agent.message_validator,
            "validate",
        ) as mock_validate:

            mock_validate.return_value = MagicMock(
                passed=True,
                requires_fallback=False,
                quality_score=1.0,
            )

            result = await agent.run(build_valid_context())

    assert isinstance(result, CommunicationDecision)
    assert result.channel == "SMS"

    mock_render.assert_called_once()


@pytest.mark.anyio
async def test_ai_timeout_without_database_fails_fallback() -> None:
    config = build_config()

    agent = CommunicationAgent(
        config=config,
        orchestrator=MagicMock(spec=AIOrchestrator),
        db=None,
    )

    await agent.setup()

    with patch.object(
        agent,
        "_generate_with_ai",
        side_effect=TimeoutError("AI timed out"),
    ):

        with pytest.raises(
            ValueError,
            match="fallback is unavailable",
        ):
            await agent.run(build_valid_context())


@pytest.mark.anyio
async def test_ai_timeout_fallback_template_engine_error() -> None:
    config = build_config()

    agent = CommunicationAgent(
        config=config,
        orchestrator=MagicMock(spec=AIOrchestrator),
        db=MagicMock(),
    )

    await agent.setup()

    with patch.object(
        agent,
        "_generate_with_ai",
        side_effect=TimeoutError("AI timed out"),
    ), patch(
        "app.services.ai.FieldOpsAI.agents.communication_agent_impl.render_managed_template",
        side_effect=Exception("template failure"),
    ):

        with pytest.raises(
          Exception,
          match="template failure",
        ):
            await agent.run(build_valid_context())


# ============================================================================
# Additional coverage: fallback channels
# ============================================================================


@pytest.mark.anyio
@pytest.mark.parametrize(
    "channel",
    ["SMS", "EMAIL", "PUSH", "IN_APP"],
)
async def test_fallback_renders_all_supported_channels(
    channel: str,
) -> None:
    config = build_config()

    agent = CommunicationAgent(
        config=config,
        orchestrator=MagicMock(spec=AIOrchestrator),
        db=MagicMock(),
    )

    await agent.setup()

    context = build_valid_context()
    context.pop("tenant_id", None)
    context["channel"] = channel

    rendered = MagicMock(
        body="Fallback body",
        title="Fallback title",
        template_id=1,
        template_version=1,
        source="managed",
        template_format="text",
    )

    with patch(
        "app.services.ai.FieldOpsAI.agents.communication_agent_impl.render_managed_template",
        return_value=rendered,
    ):

        result = agent._render_fallback(
            context=CommunicationContext.model_validate(
                context
            )
        )

    assert isinstance(result, CommunicationDecision)
    assert result.channel == channel


@pytest.mark.anyio
async def test_email_html_fallback_contains_html_body() -> None:
    config = build_config()

    agent = CommunicationAgent(
        config=config,
        orchestrator=MagicMock(spec=AIOrchestrator),
        db=MagicMock(),
    )

    context = build_valid_context()
    context.pop("tenant_id", None)
    context["channel"] = "EMAIL"

    rendered = MagicMock(
        body="<p>Hello customer</p>",
        title="Job update",
        template_id=1,
        template_version=2,
        source="managed",
        template_format="html",
    )

    with patch(
        "app.services.ai.FieldOpsAI.agents.communication_agent_impl.render_managed_template",
        return_value=rendered,
    ):

        result = agent._render_fallback(
            context=CommunicationContext.model_validate(
                context
            )
        )

    assert result.channel == "EMAIL"
    assert result.output.subject == "Job update"
    assert result.output.text_body == "<p>Hello customer</p>"
    assert result.output.html_body == "<p>Hello customer</p>"


# ============================================================================
# Additional coverage: guardrail fallback
# ============================================================================


@pytest.mark.anyio
async def test_guardrail_can_trigger_jinja2_fallback() -> None:
    config = build_config()

    mock_orchestrator = MagicMock(spec=AIOrchestrator)

    ai_decision = build_expected_decision(
        channel="SMS",
        message="Bad AI message",
    )

    mock_orchestrator.execute.return_value = ai_decision

    mock_validator = MagicMock()

    # First validation = AI failed and requires fallback.
    # Second validation = fallback passed.
    mock_validator.validate.side_effect = [
        MagicMock(
            passed=False,
            requires_fallback=True,
            quality_score=0.2,
        ),
        MagicMock(
            passed=True,
            requires_fallback=False,
            quality_score=1.0,
        ),
    ]

    agent = CommunicationAgent(
        config=config,
        orchestrator=mock_orchestrator,
        message_validator=mock_validator,
        db=MagicMock(),
    )

    await agent.setup()

    rendered = MagicMock(
        body="Safe fallback",
        title=None,
        template_id=2,
        template_version=1,
        source="managed",
        template_format="text",
    )

    with patch(
        "app.services.ai.FieldOpsAI.agents.communication_agent_impl.render_managed_template",
        return_value=rendered,
    ):

        result = await agent.run(build_valid_context())

    assert isinstance(result, CommunicationDecision)
    assert result.channel == "SMS"

    assert mock_validator.validate.call_count == 2


@pytest.mark.anyio
async def test_guardrail_fallback_without_database_raises_expected_error() -> None:
    config = build_config()

    mock_orchestrator = MagicMock(spec=AIOrchestrator)

    mock_orchestrator.execute.return_value = (
        build_expected_decision()
    )

    mock_validator = MagicMock()

    mock_validator.validate.return_value = MagicMock(
        passed=False,
        requires_fallback=True,
        quality_score=0.1,
    )

    agent = CommunicationAgent(
        config=config,
        orchestrator=mock_orchestrator,
        message_validator=mock_validator,
        db=None,
    )

    await agent.setup()

    with pytest.raises(
        ValueError,
        match="requires fallback",
    ):
        await agent.run(build_valid_context())


@pytest.mark.anyio
async def test_guardrail_fallback_that_fails_validation_raises() -> None:
    config = build_config()

    mock_orchestrator = MagicMock(spec=AIOrchestrator)

    mock_orchestrator.execute.return_value = (
        build_expected_decision()
    )

    mock_validator = MagicMock()

    mock_validator.validate.side_effect = [
        MagicMock(
            passed=False,
            requires_fallback=True,
            quality_score=0.1,
        ),
        MagicMock(
            passed=False,
            requires_fallback=False,
            quality_score=0.1,
        ),
    ]

    agent = CommunicationAgent(
        config=config,
        orchestrator=mock_orchestrator,
        message_validator=mock_validator,
        db=MagicMock(),
    )

    await agent.setup()

    rendered = MagicMock(
        body="Fallback body",
        title=None,
        template_id=1,
        template_version=1,
        source="managed",
        template_format="text",
    )

    with patch(
        "app.services.ai.FieldOpsAI.agents.communication_agent_impl.render_managed_template",
        return_value=rendered,
    ):

        with pytest.raises(
            ValueError,
            match="fallback failed",
        ):
            await agent.run(build_valid_context())


# ============================================================================
# Additional coverage: generate_message validation
# ============================================================================


@pytest.mark.anyio
async def test_generate_message_rejects_non_string_channel() -> None:
    config = build_config()

    agent = CommunicationAgent(config=config)

    with pytest.raises(
        TypeError,
        match="channel must be a string",
    ):
        await agent.generate_message(
            build_valid_context(),
            channel=123,
        )


@pytest.mark.anyio
async def test_generate_message_rejects_non_string_template_key() -> None:
    config = build_config()

    agent = CommunicationAgent(config=config)

    with pytest.raises(
        TypeError,
        match="template_key must be a string",
    ):
        await agent.generate_message(
            build_valid_context(),
            template_key=123,
        )


@pytest.mark.anyio
async def test_generate_message_accepts_communication_context() -> None:
    config = build_config()

    mock_orchestrator = MagicMock(
        spec=AIOrchestrator
    )

    expected = build_expected_decision()

    mock_orchestrator.execute.return_value = expected

    agent = CommunicationAgent(
        config=config,
        orchestrator=mock_orchestrator,
    )

    context_data = build_valid_context()
    context_data.pop("tenant_id", None)

    context = CommunicationContext.model_validate(
        context_data
    )

    result = await agent.generate_message(
        context
    )

    assert result == expected


@pytest.mark.anyio
async def test_generate_message_rejects_invalid_context_type() -> None:
    config = build_config()

    agent = CommunicationAgent(config=config)

    with pytest.raises(
        TypeError,
        match="context must be a CommunicationContext or dict",
    ):
        await agent.generate_message(
            "invalid-context"
        )


@pytest.mark.anyio
async def test_generate_with_ai_timeout() -> None:
    config = build_config()

    agent = CommunicationAgent(
        config=config,
        orchestrator=MagicMock(spec=AIOrchestrator),
    )

    context_data = build_valid_context()
    context_data.pop("tenant_id", None)

    context = CommunicationContext.model_validate(
      context_data
    )

    async def fake_wait_for(*args, **kwargs):
        raise asyncio.TimeoutError()

    with patch(
        "app.services.ai.FieldOpsAI.agents.communication_agent_impl.asyncio.wait_for",
        side_effect=fake_wait_for,
    ):
        with pytest.raises(
            TimeoutError,
            match="Communication AI generation timed out",
        ):
            await agent._generate_with_ai(context)


@pytest.mark.anyio
async def test_generate_with_ai_failure() -> None:
    config = build_config()

    orchestrator = MagicMock(spec=AIOrchestrator)
    orchestrator.execute.side_effect = RuntimeError("AI failed")

    agent = CommunicationAgent(
        config=config,
        orchestrator=orchestrator,
    )

    context_data = build_valid_context()
    context_data.pop("tenant_id", None)

    context = CommunicationContext.model_validate(
      context_data
    )

    with pytest.raises(
       RuntimeError,
       match="AI failed",
    ):
        await agent._generate_with_ai(context)

# ============================================================================
# Final branch coverage tests
# ============================================================================

def test_get_fallback_db_uses_personalization_pipeline_db() -> None:
    config = build_config()

    pipeline = MagicMock()
    pipeline.db = MagicMock()

    agent = CommunicationAgent(
        config=config,
        personalization_pipeline=pipeline,
        db=None,
    )

    assert agent._get_fallback_db() is pipeline.db


@pytest.mark.anyio
async def test_generate_with_ai_rejects_invalid_decision_type() -> None:
    config = build_config()

    orchestrator = MagicMock(spec=AIOrchestrator)
    orchestrator.execute.return_value = "invalid-ai-output"

    agent = CommunicationAgent(
        config=config,
        orchestrator=orchestrator,
    )

    context_data = build_valid_context()
    context_data.pop("tenant_id", None)

    context = CommunicationContext.model_validate(
      context_data
    )

    with pytest.raises(
        TypeError,
        match="Returned object is not a CommunicationDecision",
    ):
        await agent._generate_with_ai(context)


def test_render_fallback_converts_template_engine_error() -> None:
    from app.services.template_engine import MessageTemplateEngineError

    config = build_config()

    agent = CommunicationAgent(
        config=config,
        orchestrator=MagicMock(spec=AIOrchestrator),
        db=MagicMock(),
    )

    context_data = build_valid_context()
    context_data.pop("tenant_id", None)

    context = CommunicationContext.model_validate(
    context_data
    )

    with patch(
        "app.services.ai.FieldOpsAI.agents.communication_agent_impl.render_managed_template",
        side_effect=MessageTemplateEngineError("template failed"),
    ):
        with pytest.raises(
            ValueError,
            match="Communication fallback template rendering failed",
        ):
            agent._render_fallback(context=context)


def test_render_fallback_rejects_unsupported_channel() -> None:
    config = build_config()

    agent = CommunicationAgent(
        config=config,
        orchestrator=MagicMock(spec=AIOrchestrator),
        db=MagicMock(),
    )

    # model_construct intentionally bypasses Pydantic's channel Literal
    # because this test targets the defensive branch inside _render_fallback.
    context = CommunicationContext.model_construct(
        job_id="job-123",
        notification_type="job_assigned",
        recipient_type="CUSTOMER",
        channel="WHATSAPP",
        locale="en",
        job_status="ASSIGNED",
        correlation_id=None,
        customer_id=None,
        customer_name=None,
        technician_name=None,
        job_title=None,
        eta=None,
        appointment_time=None,
        sentiment="NEUTRAL",
        additional_context=None,
        template=None,
        personalization_data={},
    )

    rendered = MagicMock(
        body="Fallback body",
        title="Fallback title",
        template_id=1,
        template_version=1,
        source="managed",
        template_format="text",
    )

    with patch(
        "app.services.ai.FieldOpsAI.agents.communication_agent_impl.render_managed_template",
        return_value=rendered,
    ):
        with pytest.raises(
            ValueError,
            match="Unsupported fallback channel",
        ):
            agent._render_fallback(context=context)


@pytest.mark.anyio
async def test_ai_failure_fallback_validation_failure_raises() -> None:
    config = build_config()

    agent = CommunicationAgent(
        config=config,
        orchestrator=MagicMock(spec=AIOrchestrator),
        db=MagicMock(),
    )

    await agent.setup()

    rendered = MagicMock(
        body="Fallback body",
        title=None,
        template_id=1,
        template_version=1,
        source="managed",
        template_format="text",
    )

    with patch.object(
        agent,
        "_generate_with_ai",
        side_effect=TimeoutError("AI timed out"),
    ), patch(
        "app.services.ai.FieldOpsAI.agents.communication_agent_impl.render_managed_template",
        return_value=rendered,
    ), patch.object(
        agent.message_validator,
        "validate",
        return_value=MagicMock(
            passed=False,
            requires_fallback=False,
            quality_score=20,
        ),
    ):
        with pytest.raises(
            ValueError,
            match="Communication fallback failed message validation",
        ):
            await agent.run(build_valid_context())


@pytest.mark.anyio
async def test_generate_message_uses_portal_mapping() -> None:
    config = build_config()

    orchestrator = MagicMock(spec=AIOrchestrator)
    orchestrator.execute.return_value = build_expected_decision(
        channel="IN_APP",
    )

    agent = CommunicationAgent(
        config=config,
        orchestrator=orchestrator,
    )

    await agent.generate_message(
        build_valid_context(),
        channel="portal",
    )

    generated_context = (
        orchestrator.execute.call_args.kwargs["context"]
    )

    assert generated_context["channel"] == "IN_APP"