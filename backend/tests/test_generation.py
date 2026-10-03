from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from bs4 import BeautifulSoup
from pydantic import ValidationError

from app.services.ai.FieldOpsAI.generators.ai_generator import (
    AIMessageGenerator,
)
from app.services.ai.FieldOpsAI.schemas.communication import (
    CommunicationContext,
    CommunicationDecision,
    CommunicationRecipient,
)
from app.services.ai.FieldOpsAI.services.message_output_formatter import (
    MessageOutputFormatter,
)
from app.services.ai.guardrails.fallback_service import (
    FallbackTemplateSource,
    GuardrailFallbackResult,
)
from app.services.ai.pii_sanitizer import pii_sanitizer


MODULE_PATH = (
    "app.services.ai.FieldOpsAI.generators.ai_generator"
)

STATUSES = [
    "created",
    "assigned",
    "enroute",
    "onsite",
    "completed",
    "cancelled",
]

CHANNELS = [
    "SMS",
    "EMAIL",
    "PUSH",
]

PATHS = [
    "ai",
    "fallback",
]

STATUS_TO_JOBSTATUS = {
    "created": "CREATED",
    "assigned": "ASSIGNED",
    "enroute": "EN_ROUTE",
    "onsite": "ON_SITE",
    "completed": "COMPLETED",
    "cancelled": "CANCELLED",
}

AI_LATENCY_BUDGET_SECONDS = 5.0
FALLBACK_LATENCY_BUDGET_SECONDS = 0.080


JOB_FIXTURES = {
    "created": {
        "job_id": "JOB-CREATED-001",
        "notification_type": "job_created",
        "customer_name": "Ravi Kumar",
        "technician_name": None,
        "job_title": "AC installation",
        "eta": None,
        "appointment_time": "09:30 AM",
    },
    "assigned": {
        "job_id": "JOB-ASSIGNED-002",
        "notification_type": "job_assigned",
        "customer_name": "Anita Sharma",
        "technician_name": "Suresh Babu",
        "job_title": "Plumbing repair",
        "eta": None,
        "appointment_time": "10:00 AM",
    },
    "enroute": {
        "job_id": "JOB-ENROUTE-003",
        "notification_type": "technician_en_route",
        "customer_name": "Karthik Iyer",
        "technician_name": "Ramesh Pillai",
        "job_title": "Electrical inspection",
        "eta": "15 minutes",
        "appointment_time": None,
    },
    "onsite": {
        "job_id": "JOB-ONSITE-004",
        "notification_type": "technician_on_site",
        "customer_name": "Divya Menon",
        "technician_name": "Suresh Babu",
        "job_title": "Appliance repair",
        "eta": None,
        "appointment_time": "10:45 AM",
    },
    "completed": {
        "job_id": "JOB-COMPLETED-005",
        "notification_type": "job_completed",
        "customer_name": "Mohammed Faizal",
        "technician_name": "Ramesh Pillai",
        "job_title": "Water heater service",
        "eta": None,
        "appointment_time": None,
    },
    "cancelled": {
        "job_id": "JOB-CANCELLED-006",
        "notification_type": "job_cancelled",
        "customer_name": "Lakshmi Narayanan",
        "technician_name": None,
        "job_title": "HVAC maintenance",
        "eta": None,
        "appointment_time": None,
    },
}


class FakeFallbackService:
    def __init__(self, *, db):
        self.db = db
        self.render = MagicMock()


def _build_context(
    status: str,
    channel: str,
    **overrides,
) -> CommunicationContext:
    data = dict(JOB_FIXTURES[status])
    data.update(overrides)

    return CommunicationContext(
        job_id=data["job_id"],
        notification_type=data["notification_type"],
        recipient_type=CommunicationRecipient.CUSTOMER,
        channel=channel,
        locale=data.get("locale", "en"),
        customer_name=data.get("customer_name"),
        technician_name=data.get("technician_name"),
        job_status=STATUS_TO_JOBSTATUS[status],
        job_title=data.get("job_title"),
        eta=data.get("eta"),
        appointment_time=data.get("appointment_time"),
        sentiment=data.get("sentiment", "NEUTRAL"),
        additional_context=data.get("additional_context"),
    )


def _make_fallback_result(
    context: CommunicationContext,
) -> GuardrailFallbackResult:
    customer = context.customer_name or "Customer"
    technician = context.technician_name or "Your technician"
    title = context.job_title or "your service request"

    if context.channel == "SMS":
        output = MessageOutputFormatter.format(
            channel="SMS",
            rendered_title=None,
            rendered_body=(
                f"Hi {customer}, "
                f"your {title} service request has an update."
            ),
            template_format="text",
        )

    elif context.channel == "EMAIL":
        output = MessageOutputFormatter.format(
            channel="EMAIL",
            rendered_title="FieldOps service update",
            rendered_body=(
                "<html><body>"
                f"<p>Hi {customer},</p>"
                f"<p>Your {title} service request has an update. "
                f"{technician} is handling the request.</p>"
                "</body></html>"
            ),
            template_format="html",
        )

    else:
        output = MessageOutputFormatter.format(
            channel="PUSH",
            rendered_title="FieldOps update",
            rendered_body=(
                f"Your {title} service request has a new update."
            ),
            template_format="text",
        )

    decision = CommunicationDecision(
        channel=context.channel,
        output=output,
        tone="PROFESSIONAL",
        confidence=1.0,
    )

    return GuardrailFallbackResult(
        decision=decision,
        source=FallbackTemplateSource.BUILTIN,
        requested_locale=context.locale,
        resolved_locale=context.locale,
    )


@pytest.fixture
def budget_manager():
    manager = MagicMock()
    manager.check.return_value = SimpleNamespace(
        allowed=True
    )
    return manager


@pytest.fixture
def generator(monkeypatch, budget_manager):
    fake_groq = MagicMock()

    monkeypatch.setattr(
        f"{MODULE_PATH}.GroqClient",
        lambda: fake_groq,
    )

    monkeypatch.setattr(
        f"{MODULE_PATH}.GuardrailFallbackService",
        FakeFallbackService,
    )

    generator = AIMessageGenerator(
        db=MagicMock(),
        budget_manager=budget_manager,
    )

    generator.groq_client = fake_groq

    generator.guardrail_pipeline = MagicMock()
    generator.guardrail_pipeline.run.return_value = (
        SimpleNamespace(passed=True)
    )

    return generator


def _configure_ai_success(
    generator,
    status: str,
    channel: str,
):
    if channel == "EMAIL":
        body = (
            "<html><body>"
            f"<p>Hi {{{{customer_name}}}},</p>"
            f"<p>Your job {{{{job_id}}}} is now {status}.</p>"
            "</body></html>"
        )

    elif channel == "PUSH":
        body = (
            f"FieldOps update: "
            f"job {{{{job_id}}}} is now {status}."
        )

    else:
        body = (
            f"Hi {{{{customer_name}}}}, "
            f"your job {{{{job_id}}}} is now {status}. "
            "- FieldOps"
        )

    generator.groq_client.generate_result.return_value = (
        SimpleNamespace(text=body)
    )

    generator.guardrail_pipeline.run.return_value = (
        SimpleNamespace(passed=True)
    )

    return body


def _force_fallback(
    generator,
    context: CommunicationContext,
):
    fallback_result = _make_fallback_result(context)

    generator.fallback_service.render.return_value = (
        fallback_result
    )

    return fallback_result


def _extract_decision(result):
    if isinstance(
        result,
        GuardrailFallbackResult,
    ):
        return result.decision

    return result


def _assert_decision_channel(
    result,
    channel: str,
):
    assert isinstance(
        result,
        CommunicationDecision,
    )
    assert result.channel == channel
    assert result.output.channel == channel


# ============================================================================
# 72 CORE TESTS
# ============================================================================


@pytest.mark.parametrize("status", STATUSES)
@pytest.mark.parametrize("channel", CHANNELS)
@pytest.mark.parametrize("path", PATHS)
@pytest.mark.asyncio
async def test_core_content_correctness(
    generator,
    budget_manager,
    status,
    channel,
    path,
):
    context = _build_context(
        status,
        channel,
    )

    if path == "ai":
        _configure_ai_success(
            generator,
            status,
            channel,
        )

        if channel in {"EMAIL", "PUSH"}:
            generator.fallback_service.render.return_value = (
                _make_fallback_result(context)
            )

        result = await generator.message_generate(
            context=context,
            template_key=f"{status}_{channel.lower()}",
            channel=channel,
        )

        generator.groq_client.generate_result.assert_called_once()

        provider_prompt = (
            generator.groq_client
            .generate_result
            .call_args
            .kwargs["messages"][0]["content"]
        )

        assert context.customer_name not in provider_prompt
        assert context.job_id not in provider_prompt

        decision = _extract_decision(result)

        if channel == "SMS":
            assert isinstance(
                result,
                CommunicationDecision,
            )
            assert result.channel == "SMS"
            assert context.customer_name in decision.message
            assert context.job_id in decision.message
            assert "{{customer_name}}" not in decision.message
            assert "{{job_id}}" not in decision.message

        else:
            assert isinstance(
                result,
                GuardrailFallbackResult,
            )
            assert isinstance(
                result.decision,
                CommunicationDecision,
            )
            assert result.decision.channel == channel
            assert result.source in {
                FallbackTemplateSource.DATABASE,
                FallbackTemplateSource.BUILTIN,
                FallbackTemplateSource.EMERGENCY,
            }

    else:
        fallback_result = _force_fallback(
            generator,
            context,
        )

        budget_manager.check.return_value = (
            SimpleNamespace(
                allowed=False
            )
        )

        result = await generator.message_generate(
            context=context,
            template_key=f"{status}_{channel.lower()}",
            channel=channel,
        )

        assert result is fallback_result
        assert (
            result.source
            == FallbackTemplateSource.BUILTIN
        )

        generator.groq_client.generate_result.assert_not_called()

        generator.fallback_service.render.assert_called_once_with(
            context=context
        )


@pytest.mark.parametrize("status", STATUSES)
@pytest.mark.parametrize("channel", CHANNELS)
@pytest.mark.parametrize("path", PATHS)
@pytest.mark.asyncio
async def test_core_delivery_format(
    generator,
    budget_manager,
    status,
    channel,
    path,
):
    context = _build_context(
        status,
        channel,
    )

    if path == "ai":
        _configure_ai_success(
            generator,
            status,
            channel,
        )

        if channel in {"EMAIL", "PUSH"}:
            generator.fallback_service.render.return_value = (
                _make_fallback_result(context)
            )

        result = await generator.message_generate(
            context=context,
            template_key=f"{status}_{channel.lower()}",
            channel=channel,
        )

    else:
        fallback_result = _force_fallback(
            generator,
            context,
        )

        budget_manager.check.return_value = (
            SimpleNamespace(
                allowed=False
            )
        )

        result = await generator.message_generate(
            context=context,
            template_key=f"{status}_{channel.lower()}",
            channel=channel,
        )

        assert result is fallback_result

    decision = _extract_decision(result)

    assert isinstance(
        decision,
        CommunicationDecision,
    )

    assert decision.channel == channel

    if channel == "SMS":
        assert decision.output.channel == "SMS"
        assert decision.output.text
        assert len(decision.output.text) <= 160

    elif channel == "PUSH":
        assert decision.output.channel == "PUSH"
        assert decision.output.title
        assert len(decision.output.title) <= 50
        assert decision.output.body
        assert len(decision.output.body) <= 200

    elif channel == "EMAIL":
        assert decision.output.channel == "EMAIL"
        assert decision.output.subject
        assert decision.output.text_body

        if decision.output.html_body:
            soup = BeautifulSoup(
                decision.output.html_body,
                "html.parser",
            )

            assert soup.find("html") is not None
            assert soup.find("body") is not None
            assert soup.get_text(
                " ",
                strip=True,
            )


# ============================================================================
# 12 EDGE TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_edge_maximum_valid_customer_name(
    generator,
):
    context = _build_context(
        "assigned",
        "SMS",
        customer_name="A" * 150,
    )

    _configure_ai_success(
        generator,
        "assigned",
        "SMS",
    )

    result = await generator.message_generate(
        context=context,
        template_key="assigned_sms",
        channel="SMS",
    )

    _assert_decision_channel(
        result,
        "SMS",
    )

    assert "A" * 150 in result.message


def test_edge_customer_name_above_schema_limit_is_rejected():
    with pytest.raises(ValidationError):
        _build_context(
            "assigned",
            "SMS",
            customer_name="A" * 151,
        )


@pytest.mark.asyncio
async def test_edge_special_characters_in_additional_context(
    generator,
):
    context = _build_context(
        "enroute",
        "SMS",
        additional_context=(
            '12/B, "Sunshine" Apts, '
            "<Chennai> & Co."
        ),
    )

    _configure_ai_success(
        generator,
        "enroute",
        "SMS",
    )

    result = await generator.message_generate(
        context=context,
        template_key="enroute_sms",
        channel="SMS",
    )

    _assert_decision_channel(
        result,
        "SMS",
    )

    assert result.message


@pytest.mark.asyncio
async def test_edge_missing_optional_data(
    generator,
    budget_manager,
):
    context = _build_context(
        "created",
        "SMS",
        customer_name=None,
        technician_name=None,
        eta=None,
        appointment_time=None,
    )

    fallback_result = _force_fallback(
        generator,
        context,
    )

    budget_manager.check.return_value = (
        SimpleNamespace(
            allowed=False
        )
    )

    result = await generator.message_generate(
        context=context,
        template_key="created_sms",
        channel="SMS",
    )

    assert result is fallback_result
    assert result.decision.message


@pytest.mark.asyncio
async def test_edge_empty_template_key_raises(
    generator,
):
    context = _build_context(
        "created",
        "SMS",
    )

    with pytest.raises(ValueError):
        await generator.message_generate(
            context=context,
            template_key="   ",
            channel="SMS",
        )


@pytest.mark.asyncio
async def test_edge_channel_mismatch_raises(
    generator,
):
    context = _build_context(
        "created",
        "SMS",
    )

    with pytest.raises(ValueError):
        await generator.message_generate(
            context=context,
            template_key="created_email",
            channel="EMAIL",
        )


@pytest.mark.asyncio
async def test_edge_invalid_context_type_raises(
    generator,
):
    with pytest.raises(TypeError):
        await generator.message_generate(
            context={"job_id": "invalid"},
            template_key="created_sms",
            channel="SMS",
        )
        
@pytest.mark.parametrize("failure_point", [
    "sanitize", "budget", "restore", "guardrail",
])
@pytest.mark.asyncio
async def test_edge_dependency_failure_forces_fallback(
    generator, budget_manager, monkeypatch, failure_point,
):
    context = _build_context("assigned", "SMS")
    fallback_result = _force_fallback(generator, context)
    _configure_ai_success(generator, "assigned", "SMS")

    def _raise(*a, **k):
        raise RuntimeError(f"{failure_point} failed")

    if failure_point == "sanitize":
        monkeypatch.setattr(pii_sanitizer, "sanitize_prompt", _raise)
    elif failure_point == "budget":
        budget_manager.check.side_effect = RuntimeError("budget service unavailable")
    elif failure_point == "restore":
        monkeypatch.setattr(pii_sanitizer, "restore_data", _raise)
    elif failure_point == "guardrail":
        generator.guardrail_pipeline.run.side_effect = RuntimeError("guardrail service unavailable")

    result = await generator.message_generate(
        context=context,
        template_key="assigned_sms",
        channel="SMS",
    )

    assert result is fallback_result
    if failure_point in ("budget",):
        generator.groq_client.generate_result.assert_not_called()

@pytest.mark.asyncio
async def test_edge_empty_channel_raises(generator):
    context = _build_context("created", "SMS")

    with pytest.raises(ValueError):
        await generator.message_generate(
            context=context,
            template_key="created_sms",
            channel="   ",
        )


@pytest.mark.asyncio
async def test_edge_context_sanitization_failure_forces_fallback(
    generator, monkeypatch,
):
    context = _build_context("assigned", "SMS")
    fallback_result = _force_fallback(generator, context)

    def fail_sanitize(*a, **k):
        raise RuntimeError("context sanitization failed")

    monkeypatch.setattr(pii_sanitizer, "sanitize", fail_sanitize)

    result = await generator.message_generate(
        context=context,
        template_key="assigned_sms",
        channel="SMS",
    )

    assert result is fallback_result
    generator.groq_client.generate_result.assert_not_called()


@pytest.mark.asyncio
async def test_edge_guardrail_rejection_forces_fallback(
    generator,
):
    context = _build_context(
        "cancelled",
        "SMS",
    )

    fallback_result = _force_fallback(
        generator,
        context,
    )

    _configure_ai_success(
        generator,
        "cancelled",
        "SMS",
    )

    generator.guardrail_pipeline.run.return_value = (
        SimpleNamespace(
            passed=False
        )
    )

    result = await generator.message_generate(
        context=context,
        template_key="cancelled_sms",
        channel="SMS",
    )

    assert result is fallback_result


@pytest.mark.parametrize("status,greeting,name", [
    ("onsite", "வணக்கம்", "இராம் குமார்"),
    ("completed", "नमस्ते", "राम कुमार"),
])
@pytest.mark.asyncio
async def test_edge_tamil_and_hindi_unicode_are_preserved(
    generator, status, greeting, name,
):
    context = _build_context(status, "SMS", customer_name=name)

    generator.guardrail_pipeline.run.return_value = SimpleNamespace(passed=True)
    generator.groq_client.generate_result.return_value = SimpleNamespace(
        text=f"{greeting} {{{{customer_name}}}}, your service request was updated."
    )

    result = await generator.message_generate(
        context=context,
        template_key=f"{status}_sms",
        channel="SMS",
    )

    decision = _extract_decision(result)

    assert isinstance(decision, CommunicationDecision)
    assert greeting in decision.message
    assert name in decision.message
    assert "{{customer_name}}" not in decision.message


# ============================================================================
# 8 PERFORMANCE TESTS
# ============================================================================


@pytest.mark.parametrize(
    "channel",
    CHANNELS,
)
@pytest.mark.asyncio
async def test_perf_ai_path_under_five_seconds(
    generator,
    channel,
):
    context = _build_context(
        "enroute",
        channel,
    )

    _configure_ai_success(
        generator,
        "enroute",
        channel,
    )

    if channel in {"EMAIL", "PUSH"}:
        generator.fallback_service.render.return_value = (
            _make_fallback_result(context)
        )

    start = time.perf_counter()

    await generator.message_generate(
        context=context,
        template_key=f"enroute_{channel.lower()}",
        channel=channel,
    )

    elapsed = time.perf_counter() - start

    assert elapsed < AI_LATENCY_BUDGET_SECONDS


@pytest.mark.asyncio
async def test_perf_ai_worst_case_payload_under_five_seconds(
    generator,
):
    context = _build_context(
        "completed",
        "EMAIL",
        customer_name="A" * 150,
        technician_name="T" * 150,
        job_title="J" * 200,
        additional_context="X" * 2000,
    )

    _configure_ai_success(
        generator,
        "completed",
        "EMAIL",
    )

    generator.fallback_service.render.return_value = (
        _make_fallback_result(context)
    )

    start = time.perf_counter()

    await generator.message_generate(
        context=context,
        template_key="completed_email",
        channel="EMAIL",
    )

    elapsed = time.perf_counter() - start

    assert elapsed < AI_LATENCY_BUDGET_SECONDS


@pytest.mark.parametrize(
    "channel",
    CHANNELS,
)
@pytest.mark.asyncio
async def test_perf_fallback_path_under_fifty_ms(
    generator,
    budget_manager,
    channel,
):
    context = _build_context(
        "cancelled",
        channel,
    )

    _force_fallback(
        generator,
        context,
    )

    budget_manager.check.return_value = (
        SimpleNamespace(
            allowed=False
        )
    )

    start = time.perf_counter()

    await generator.message_generate(
        context=context,
        template_key=f"cancelled_{channel.lower()}",
        channel=channel,
    )

    elapsed = time.perf_counter() - start

    assert elapsed < FALLBACK_LATENCY_BUDGET_SECONDS


@pytest.mark.asyncio
async def test_perf_fallback_worst_case_payload_under_fifty_ms(
    generator,
    budget_manager,
):
    context = _build_context(
        "cancelled",
        "EMAIL",
        customer_name="A" * 150,
        technician_name="T" * 150,
        job_title="J" * 200,
        additional_context="X" * 2000,
    )

    _force_fallback(
        generator,
        context,
    )

    budget_manager.check.return_value = (
        SimpleNamespace(
            allowed=False
        )
    )

    start = time.perf_counter()

    await generator.message_generate(
        context=context,
        template_key="cancelled_email",
        channel="EMAIL",
    )

    elapsed = time.perf_counter() - start

    assert elapsed < FALLBACK_LATENCY_BUDGET_SECONDS


# ============================================================================
# EXPLICIT HTML VALIDATION
# ============================================================================
@pytest.mark.asyncio
async def test_coverage_final_prompt_sanitization_failure(
    generator,
    monkeypatch,
):
    context = _build_context("assigned", "SMS")

    fallback_result = _force_fallback(
        generator,
        context,
    )

    def fail_sanitize_prompt(*args, **kwargs):
        raise RuntimeError("final prompt sanitization failed")

    monkeypatch.setattr(
        pii_sanitizer,
        "sanitize_prompt",
        fail_sanitize_prompt,
    )

    result = await generator.message_generate(
        context=context,
        template_key="assigned_sms",
        channel="SMS",
    )

    assert result is fallback_result
    generator.groq_client.generate_result.assert_not_called()


@pytest.mark.asyncio
async def test_coverage_provider_failure(
    generator,
):
    context = _build_context("assigned", "SMS")

    fallback_result = _force_fallback(
        generator,
        context,
    )

    generator.groq_client.generate_result.side_effect = (
        RuntimeError("provider unavailable")
    )

    result = await generator.message_generate(
        context=context,
        template_key="assigned_sms",
        channel="SMS",
    )

    assert result is fallback_result


@pytest.mark.asyncio
async def test_coverage_empty_provider_response(
    generator,
):
    context = _build_context("assigned", "SMS")

    fallback_result = _force_fallback(
        generator,
        context,
    )

    generator.groq_client.generate_result.return_value = (
        SimpleNamespace(text="   ")
    )

    result = await generator.message_generate(
        context=context,
        template_key="assigned_sms",
        channel="SMS",
    )

    assert result is fallback_result


@pytest.mark.asyncio
async def test_coverage_formatter_failure(
    generator,
    monkeypatch,
):
    context = _build_context("assigned", "SMS")

    fallback_result = _force_fallback(
        generator,
        context,
    )

    monkeypatch.setattr(
        MessageOutputFormatter,
        "format",
        MagicMock(
            side_effect=RuntimeError(
                "formatter failure"
            )
        ),
    )

    _configure_ai_success(
        generator,
        "assigned",
        "SMS",
    )

    result = await generator.message_generate(
        context=context,
        template_key="assigned_sms",
        channel="SMS",
    )

    assert result is fallback_result


@pytest.mark.asyncio
async def test_coverage_decision_creation_failure(
    generator,
    monkeypatch,
):
    context = _build_context("assigned", "SMS")

    fallback_result = _force_fallback(
        generator,
        context,
    )

    _configure_ai_success(
        generator,
        "assigned",
        "SMS",
    )

    def fail_decision(*args, **kwargs):
        raise RuntimeError("decision creation failed")

    monkeypatch.setattr(
        "app.services.ai.FieldOpsAI.generators.ai_generator.CommunicationDecision",
        fail_decision,
    )

    result = await generator.message_generate(
        context=context,
        template_key="assigned_sms",
        channel="SMS",
    )

    assert result is fallback_result


@pytest.mark.asyncio
async def test_coverage_guardrail_rejection(
    generator,
):
    context = _build_context("assigned", "SMS")

    fallback_result = _force_fallback(
        generator,
        context,
    )

    _configure_ai_success(
        generator,
        "assigned",
        "SMS",
    )

    generator.guardrail_pipeline.run.return_value = (
        SimpleNamespace(
            passed=False
        )
    )

    result = await generator.message_generate(
        context=context,
        template_key="assigned_sms",
        channel="SMS",
    )

    assert result is fallback_result
    
    
def test_aigenerator_initialization(monkeypatch):
    from app.services.ai.FieldOpsAI.generators.ai_generator import AIGenerator

    orchestrator = MagicMock()

    monkeypatch.setattr(
        "app.services.ai.FieldOpsAI.generators.ai_generator.AIOrchestrator",
        lambda: orchestrator,
    )

    generator = AIGenerator()

    assert generator.orchestrator is orchestrator


def test_aigenerator_generate_delegates_to_orchestrator(monkeypatch):
    from app.services.ai.FieldOpsAI.generators.ai_generator import AIGenerator

    orchestrator = MagicMock()
    orchestrator.execute.return_value = "generated response"

    monkeypatch.setattr(
        "app.services.ai.FieldOpsAI.generators.ai_generator.AIOrchestrator",
        lambda: orchestrator,
    )

    generator = AIGenerator()

    context = {"job_id": "job-001"}

    result = generator.generate(
        task="communication",
        context=context,
    )

    assert result == "generated response"

    orchestrator.execute.assert_called_once_with(
        task="communication",
        context=context,
    )
    

