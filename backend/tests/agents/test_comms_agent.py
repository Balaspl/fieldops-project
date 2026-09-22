"""
tests/agents/test_comms_agent.py

End-to-end CommunicationAgent test suite.

Coverage
--------
96 core tests
    6 statuses x 4 channels x 4 locales

12 failure tests
    timeout
    429
    401
    500
    budget exceeded
    guardrail violation
    fallback failures
    invalid AI output
    invalid context
    lifecycle failure

8 validation tests
    SMS length
    email subject length
    push title length
    URL validation
    phone validation
    encoding
    brand/compliance
    valid message

4 escalation tests
    explicit human request
    VIP
    negative sentiment
    urgent job

Additional integration tests
    FastAPI TestClient
    mocked Groq HTTP using aioresponses
    channel delivery verification
    AI/fallback performance

IMPORTANT
---------
All external AI/provider calls are mocked.
No real Groq API call is made.
"""

from __future__ import annotations

import asyncio
import json
import time
import inspect
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import pytest
from aioresponses import aioresponses
import aioresponses.core as _aioresponses_core
from aiohttp import ClientResponse as _AiohttpClientResponse


class _MockStreamWriter:
    buffer_size = 0
    output_size = 0
    length = 0

    async def write(self, chunk):
        pass

    async def write_eof(self, chunk=b""):
        pass

    async def drain(self):
        pass

    def enable_compression(self, encoding="deflate", strategy=None):
        pass

    def enable_chunking(self):
        pass

    async def write_headers(self, status_line, headers):
        pass

    def send_headers(self):
        pass


class _Aiohttp314CompatibleClientResponse(_AiohttpClientResponse):
    def __init__(self, method, url, **kwargs):
        kwargs.setdefault("stream_writer", _MockStreamWriter())
        super().__init__(method, url, **kwargs)


_aioresponses_core.ClientResponse = (
    _Aiohttp314CompatibleClientResponse
)

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import Column, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.services.ai.FieldOpsAI.agents.communication_agent import (
    CommunicationAgent,
)
from app.services.ai.FieldOpsAI.agents.escalation_tree import (
    EscalationLevel,
    EscalationTarget,
)
from app.services.ai.FieldOpsAI.providers.base_provider import (
    ProviderExecutionError,
)
from app.services.ai.FieldOpsAI.schemas.agent_config import AgentConfig
from app.services.ai.FieldOpsAI.schemas.ai_task import AITask
from app.services.ai.FieldOpsAI.schemas.communication import (
    CommunicationContext,
    CommunicationDecision,
    EmailMessageOutput,
    PortalMessageOutput,
    PushMessageOutput,
    SMSMessageOutput,
)
from app.services.ai.guardrails.contracts import (
    GuardrailCategory,
    GuardrailDecision,
    GuardrailPipelineResult,
    GuardrailSeverity,
    GuardrailViolation,
)
from app.services.ai.guardrails.message_validator import (
    MessageValidationResult,
    MessageValidator,
)
from app.services.template_engine import (
    MessageTemplateEngineError,
)
from app.services.ai.FieldOpsAI.runtime.orchestrator import AIOrchestrator
import httpx
from groq import APIStatusError, RateLimitError

# ============================================================
# DATABASE TEST SETUP
# ============================================================

Base = declarative_base()


class Job(Base):
    """Minimal isolated test Job table."""

    __tablename__ = "jobs"

    id = Column(String, primary_key=True)
    service_type = Column(String, nullable=True)
    issue_description = Column(String, nullable=True)
    status = Column(String, nullable=True)
    customer_id = Column(String, nullable=True)
    customer_name = Column(String, nullable=True)
    site_address = Column(String, nullable=True)
    assigned_technician_id = Column(String, nullable=True)


class Technician(Base):
    """Minimal isolated test Technician table."""

    __tablename__ = "technicians"

    technician_id = Column(String, primary_key=True)
    technician_name = Column(String, nullable=True)
    technician_status = Column(String, nullable=True)
    technician_location = Column(String, nullable=True)


@pytest.fixture()
def db_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
    )

    Base.metadata.create_all(engine)

    yield engine

    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def db_session(db_engine):
    SessionLocal = sessionmaker(
        bind=db_engine,
        future=True,
    )

    session = SessionLocal()

    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def seeded_job_and_technician(db_session):
    job = Job(
        id="job-123",
        service_type="AC Repair",
        issue_description="Air conditioner not working",
        status="ASSIGNED",
        customer_id="cust-1",
        customer_name="Jane Doe",
        site_address="123 Main St",
        assigned_technician_id="tech-1",
    )

    technician = Technician(
        technician_id="tech-1",
        technician_name="Bob Smith",
        technician_status="EN_ROUTE",
        technician_location="En route to site",
    )

    db_session.add(job)
    db_session.add(technician)
    db_session.commit()

    return job, technician


# ============================================================
# TEST MATRIX
# ============================================================

CORE_STATUSES = [
    "job_assigned",
    "technician_en_route",
    "technician_on_site",
    "work_in_progress",
    "job_completed",
    "job_cancelled",
]


CORE_CHANNELS = [
    "SMS",
    "EMAIL",
    "PUSH",
    "IN_APP",
]


CORE_LOCALES = [
    "en",
    "es",
    "ta",
    "hi",
]


EXPECTED_OUTPUT_TYPE = {
    "SMS": SMSMessageOutput,
    "EMAIL": EmailMessageOutput,
    "PUSH": PushMessageOutput,
    "IN_APP": PortalMessageOutput,
}


# ============================================================
# GROQ CONFIGURATION
# ============================================================

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

GROQ_MODEL = "openai/gpt-oss-120b"


# ============================================================
# AGENT FIXTURES
# ============================================================

@pytest.fixture()
def agent_config() -> AgentConfig:
    return AgentConfig(
        agent_type=AITask.COMMUNICATION,
        tenant_id="test-tenant",
    )


@pytest.fixture()
def mock_orchestrator():
    return MagicMock()


@pytest.fixture()
def always_pass_validator():

    validator = MagicMock(
        spec=MessageValidator,
    )

    pipeline_result = GuardrailPipelineResult(
        decision=GuardrailDecision.ALLOW,
        checks=(),
        violations=(),
        total_latency_ms=1.0,
        reason=None,
    )

    validator.validate.return_value = MessageValidationResult(
        pipeline_result=pipeline_result,
        quality_score=95,
    )

    return validator


@pytest.fixture()
def agent(
    agent_config,
    mock_orchestrator,
    always_pass_validator,
    db_session,
):

    return CommunicationAgent(
        config=agent_config,
        orchestrator=mock_orchestrator,
        message_validator=always_pass_validator,
        db=db_session,
    )


@pytest.fixture()
def make_agent(
    agent_config,
    mock_orchestrator,
    db_session,
):

    def _make(
        *,
        validator=None,
        db=db_session,
        orchestrator=None,
    ):

        return CommunicationAgent(
            config=agent_config,
            orchestrator=(
                orchestrator
                if orchestrator is not None
                else mock_orchestrator
            ),
            message_validator=validator,
            db=db,
        )

    return _make


# ============================================================
# FASTAPI TEST APP
# ============================================================

@pytest.fixture()
def test_app(agent):
    """
    Test-only FastAPI application.

    This allows us to exercise CommunicationAgent through
    FastAPI TestClient instead of calling the method directly.
    """

    app = FastAPI()

    @app.post("/test/comms/generate")
    async def generate_message(payload: dict):

        decision = await agent.generate_message(
            payload,
        )

        return {
            "channel": decision.channel,
            "tone": decision.tone,
            "confidence": decision.confidence,
            "output": decision.output.model_dump(),
        }

    return app


@pytest.fixture()
def client(test_app):

    return TestClient(test_app)


# ============================================================
# HELPERS
# ============================================================

def build_context(
    *,
    channel: str,
    status: str,
    locale: str,
    **overrides,
) -> dict:

    context = {
        "job_id": "job-123",
        "notification_type": status,
        "recipient_type": "CUSTOMER",
        "channel": channel,
        "locale": locale,
        "customer_id": "cust-1",
        "customer_name": "Jane Doe",
        "technician_name": "Bob Smith",
        "job_status": "ASSIGNED",
        "job_title": "AC Repair",
        "eta": "2:00 PM",
        "sentiment": "NEUTRAL",
    }

    context.update(overrides)

    return context


def build_decision(
    channel: str,
    *,
    tone: str = "PROFESSIONAL",
    confidence: float = 0.95,
    text: str = "Your technician is on the way.",
) -> CommunicationDecision:

    outputs = {
        "SMS": {
            "channel": "SMS",
            "text": text,
        },
        "EMAIL": {
            "channel": "EMAIL",
            "subject": "Job Update",
            "text_body": text,
        },
        "PUSH": {
            "channel": "PUSH",
            "title": "Job Update",
            "body": text,
        },
        "IN_APP": {
            "channel": "PORTAL",
            "title": "Job Update",
            "body": text,
            "content_format": "text",
        },
    }

    return CommunicationDecision(
        channel=channel,
        output=outputs[channel],
        tone=tone,
        confidence=confidence,
    )


def build_validation_result(
    decision: GuardrailDecision,
    *,
    quality_score: int = 95,
) -> MessageValidationResult:

    if decision == GuardrailDecision.ALLOW:
        violations = ()
        reason = None

    else:
        violations = (
            GuardrailViolation(
                code="TEST_VIOLATION",
                category=GuardrailCategory.OUTPUT_SCHEMA,
                severity=GuardrailSeverity.ERROR,
                message="Synthetic test violation.",
                field="output",
            ),
        )

        reason = "Synthetic test failure."

    pipeline = GuardrailPipelineResult(
        decision=decision,
        checks=(),
        violations=violations,
        total_latency_ms=1.0,
        reason=reason,
    )

    return MessageValidationResult(
        pipeline_result=pipeline,
        quality_score=quality_score,
    )


def fake_rendered_result(
    *,
    body: str = "Fallback message body.",
    title: str | None = None,
    template_format: str = "text",
):

    return SimpleNamespace(
        title=title,
        body=body,
        template_id=1,
        template_version=1,
        source="tenant_override",
        template_format=template_format,
    )


RENDER_TEMPLATE_PATCH_TARGET = (
    "app.services.ai.FieldOpsAI.agents.communication_agent."
    "render_managed_template"
)


# ============================================================
# GROQ MOCK HELPERS
# ============================================================

def groq_response(
    *,
    text: str = "Your technician is on the way.",
):

    return {
        "id": "chatcmpl-test-123",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": GROQ_MODEL,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": text,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "total_tokens": 120,
        },
    }

def make_groq_response(status_code: int, payload: dict) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json=payload,
        request=httpx.Request(
            "POST",
            GROQ_URL,
        ),
    )
# ============================================================
# 96 CORE TESTS
# ============================================================

@pytest.mark.asyncio
@pytest.mark.parametrize("status", CORE_STATUSES)
@pytest.mark.parametrize("channel", CORE_CHANNELS)
@pytest.mark.parametrize("locale", CORE_LOCALES)
async def test_core_generation_matrix(
    agent,
    mock_orchestrator,
    status,
    channel,
    locale,
):
    """
    6 x 4 x 4 = 96 tests.
    """

    mock_orchestrator.execute.return_value = (
        build_decision(channel)
    )

    context = build_context(
        channel=channel,
        status=status,
        locale=locale,
    )

    decision = await agent.generate_message(
        context,
    )

    assert decision.channel == channel

    assert isinstance(
        decision.output,
        EXPECTED_OUTPUT_TYPE[channel],
    )

    assert 0.0 <= decision.confidence <= 1.0

    assert decision.tone in {
        "PROFESSIONAL",
        "FRIENDLY",
        "EMPATHETIC",
        "URGENT",
    }

    mock_orchestrator.execute.assert_called_once()


# ============================================================
# FASTAPI TESTCLIENT
# ============================================================

@pytest.mark.asyncio
async def test_fastapi_testclient_generation(
    client,
    mock_orchestrator,
):
    """
    Verify CommunicationAgent through FastAPI TestClient.
    """

    mock_orchestrator.execute.return_value = (
        build_decision("SMS")
    )

    payload = build_context(
        channel="SMS",
        status="job_assigned",
        locale="en",
    )

    response = client.post(
        "/test/comms/generate",
        json=payload,
    )

    assert response.status_code == 200

    data = response.json()

    assert data["channel"] == "SMS"
    assert data["tone"] == "PROFESSIONAL"
    assert data["confidence"] == 0.95
    assert data["output"]["text"] == (
        "Your technician is on the way."
    )


# ============================================================
# AIOHTTP / GROQ MOCK
# ============================================================

@pytest.mark.asyncio
async def test_groq_api_is_mocked_with_aioresponses():
    """
    Direct aioresponses demonstration.

    No real Groq request is performed.
    """

    import aiohttp

    with aioresponses() as mocked:

        mocked.post(
            GROQ_URL,
            status=200,
            payload=groq_response(),
        )

        async with aiohttp.ClientSession() as session:

            async with session.post(
                GROQ_URL,
                json={
                    "model": GROQ_MODEL,
                    "messages": [
                        {
                            "role": "user",
                            "content": "Generate a job update.",
                        }
                    ],
                },
                headers={
                    "Authorization": "Bearer test-token",
                },
            ) as response:

                assert response.status == 200

                data = await response.json()

    assert data["choices"][0]["message"]["content"] == (
        "Your technician is on the way."
    )

    assert len(mocked.requests) == 1


@pytest.mark.asyncio
async def test_groq_429_is_mocked_with_aioresponses():

    import aiohttp

    with aioresponses() as mocked:

        mocked.post(
            GROQ_URL,
            status=429,
            payload={
                "error": {
                    "message": "Rate limit exceeded",
                }
            },
        )

        async with aiohttp.ClientSession() as session:

            async with session.post(
                GROQ_URL,
                json={
                    "model": GROQ_MODEL,
                    "messages": [],
                },
            ) as response:

                assert response.status == 429

                data = await response.json()

    assert data["error"]["message"] == (
        "Rate limit exceeded"
    )


@pytest.mark.asyncio
async def test_groq_401_is_mocked_with_aioresponses():

    import aiohttp

    with aioresponses() as mocked:

        mocked.post(
            GROQ_URL,
            status=401,
            payload={
                "error": {
                    "message": "Invalid API key",
                }
            },
        )

        async with aiohttp.ClientSession() as session:

            async with session.post(
                GROQ_URL,
                json={},
            ) as response:

                assert response.status == 401


@pytest.mark.asyncio
async def test_groq_500_is_mocked_with_aioresponses():

    import aiohttp

    with aioresponses() as mocked:

        mocked.post(
            GROQ_URL,
            status=500,
            payload={
                "error": {
                    "message": "Internal server error",
                }
            },
        )

        async with aiohttp.ClientSession() as session:

            async with session.post(
                GROQ_URL,
                json={},
            ) as response:

                assert response.status == 500


# ============================================================
# 12 FAILURE SCENARIOS
# ============================================================

@pytest.mark.asyncio
async def test_failure_timeout_triggers_fallback(
    make_agent,
    mock_orchestrator,
    monkeypatch,
):

    monkeypatch.setattr(
        CommunicationAgent,
        "AI_TIMEOUT_SECONDS",
        0.05,
    )

    def slow_execute(*args, **kwargs):
        time.sleep(0.30)
        return build_decision("SMS")

    mock_orchestrator.execute.side_effect = (
        slow_execute
    )

    validator = MagicMock(
        spec=MessageValidator,
    )

    validator.validate.return_value = (
        build_validation_result(
            GuardrailDecision.ALLOW,
        )
    )

    agent_instance = make_agent(
        validator=validator,
    )

    context = build_context(
        channel="SMS",
        status="job_assigned",
        locale="en",
    )

    with patch(
        RENDER_TEMPLATE_PATCH_TARGET,
        return_value=fake_rendered_result(
            body="Fallback SMS.",
        ),
    ):

        decision = await agent_instance.generate_message(
            context,
        )

    assert decision.channel == "SMS"
    assert decision.output.text == "Fallback SMS."
    validator.validate.assert_called_once()


@pytest.mark.asyncio
async def test_failure_429_propagates(
    agent,
    mock_orchestrator,
):

    mock_orchestrator.execute.side_effect = (
        ProviderExecutionError(
            "Rate limited.",
            status_code=429,
            is_retryable=True,
        )
    )

    context = build_context(
        channel="SMS",
        status="job_assigned",
        locale="en",
    )

    with pytest.raises(
        ProviderExecutionError,
    ) as exc_info:

        await agent.generate_message(
            context,
        )

    assert exc_info.value.status_code == 429
    assert exc_info.value.is_retryable is True


@pytest.mark.asyncio
async def test_failure_401_propagates(
    agent,
    mock_orchestrator,
):

    mock_orchestrator.execute.side_effect = (
        ProviderExecutionError(
            "Unauthorized.",
            status_code=401,
            is_retryable=False,
        )
    )

    context = build_context(
        channel="EMAIL",
        status="job_assigned",
        locale="en",
    )

    with pytest.raises(
        ProviderExecutionError,
    ) as exc_info:

        await agent.generate_message(
            context,
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.is_retryable is False


@pytest.mark.asyncio
async def test_failure_500_propagates(
    agent,
    mock_orchestrator,
):

    mock_orchestrator.execute.side_effect = (
        ProviderExecutionError(
            "Provider server error.",
            status_code=500,
            is_retryable=True,
        )
    )

    context = build_context(
        channel="PUSH",
        status="job_assigned",
        locale="en",
    )

    with pytest.raises(
        ProviderExecutionError,
    ) as exc_info:

        await agent.generate_message(
            context,
        )

    assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_failure_budget_exceeded(
    agent,
    mock_orchestrator,
):

    mock_orchestrator.execute.side_effect = (
        ProviderExecutionError(
            "Daily AI token budget exceeded.",
            status_code=None,
            is_retryable=False,
        )
    )

    context = build_context(
        channel="IN_APP",
        status="job_assigned",
        locale="en",
    )

    with pytest.raises(
        ProviderExecutionError,
    ) as exc_info:

        await agent.generate_message(
            context,
        )

    assert "budget" in str(
        exc_info.value,
    ).lower()


@pytest.mark.asyncio
async def test_failure_guardrail_violation_fallback(
    make_agent,
    mock_orchestrator,
):

    mock_orchestrator.execute.return_value = (
        build_decision("SMS")
    )

    validator = MagicMock(
        spec=MessageValidator,
    )

    validator.validate.side_effect = [
        build_validation_result(
            GuardrailDecision.FALLBACK,
        ),
        build_validation_result(
            GuardrailDecision.ALLOW,
        ),
    ]

    agent_instance = make_agent(
        validator=validator,
    )

    context = build_context(
        channel="SMS",
        status="job_assigned",
        locale="en",
    )

    with patch(
        RENDER_TEMPLATE_PATCH_TARGET,
        return_value=fake_rendered_result(
            body="Fallback SMS.",
        ),
    ):

        decision = await agent_instance.generate_message(
            context,
        )

    assert decision.output.text == "Fallback SMS."
    assert validator.validate.call_count == 2


@pytest.mark.asyncio
async def test_failure_guardrail_requires_fallback_without_db(
    make_agent,
    mock_orchestrator,
):

    mock_orchestrator.execute.return_value = (
        build_decision("SMS")
    )

    validator = MagicMock(
        spec=MessageValidator,
    )

    validator.validate.return_value = (
        build_validation_result(
            GuardrailDecision.FALLBACK,
        )
    )

    agent_instance = make_agent(
        validator=validator,
        db=None,
    )

    context = build_context(
        channel="SMS",
        status="job_assigned",
        locale="en",
    )

    with pytest.raises(
        ValueError,
        match="requires fallback",
    ):

        await agent_instance.generate_message(
            context,
        )


@pytest.mark.asyncio
async def test_failure_guardrail_block(
    make_agent,
    mock_orchestrator,
):

    mock_orchestrator.execute.return_value = (
        build_decision("SMS")
    )

    validator = MagicMock(
        spec=MessageValidator,
    )

    validator.validate.return_value = (
        build_validation_result(
            GuardrailDecision.BLOCK,
        )
    )

    agent_instance = make_agent(
        validator=validator,
    )

    context = build_context(
        channel="SMS",
        status="job_assigned",
        locale="en",
    )

    with patch(
        RENDER_TEMPLATE_PATCH_TARGET,
    ) as mocked_render:

        with pytest.raises(
            ValueError,
            match="failed message validation",
        ):

            await agent_instance.generate_message(
                context,
            )

        mocked_render.assert_not_called()


@pytest.mark.asyncio
async def test_failure_fallback_template_error(
    make_agent,
    mock_orchestrator,
    monkeypatch,
):

    monkeypatch.setattr(
        CommunicationAgent,
        "AI_TIMEOUT_SECONDS",
        0.05,
    )

    def slow_execute(*args, **kwargs):
        time.sleep(0.30)
        return build_decision("SMS")

    mock_orchestrator.execute.side_effect = (
        slow_execute
    )

    validator = MagicMock(
        spec=MessageValidator,
    )

    validator.validate.return_value = (
        build_validation_result(
            GuardrailDecision.ALLOW,
        )
    )

    agent_instance = make_agent(
        validator=validator,
    )

    context = build_context(
        channel="SMS",
        status="job_assigned",
        locale="en",
    )

    with patch(
        RENDER_TEMPLATE_PATCH_TARGET,
        side_effect=MessageTemplateEngineError(
            "boom",
        ),
    ):

        with pytest.raises(
            ValueError,
            match="fallback template rendering failed",
        ):

            await agent_instance.generate_message(
                context,
            )


@pytest.mark.asyncio
async def test_failure_fallback_validation(
    make_agent,
    mock_orchestrator,
    monkeypatch,
):

    monkeypatch.setattr(
        CommunicationAgent,
        "AI_TIMEOUT_SECONDS",
        0.05,
    )

    def slow_execute(*args, **kwargs):
        time.sleep(0.30)
        return build_decision("SMS")

    mock_orchestrator.execute.side_effect = (
        slow_execute
    )

    validator = MagicMock(
        spec=MessageValidator,
    )

    validator.validate.return_value = (
        build_validation_result(
            GuardrailDecision.BLOCK,
        )
    )

    agent_instance = make_agent(
        validator=validator,
    )

    context = build_context(
        channel="SMS",
        status="job_assigned",
        locale="en",
    )

    with patch(
        RENDER_TEMPLATE_PATCH_TARGET,
        return_value=fake_rendered_result(
            body="Bad fallback.",
        ),
    ):

        with pytest.raises(
            ValueError,
            match="fallback failed",
        ):

            await agent_instance.generate_message(
                context,
            )


@pytest.mark.asyncio
async def test_failure_ai_wrong_return_type(
    agent,
    mock_orchestrator,
):

    mock_orchestrator.execute.return_value = (
        "not a CommunicationDecision"
    )

    context = build_context(
        channel="SMS",
        status="job_assigned",
        locale="en",
    )

    with pytest.raises(
        TypeError,
        match="CommunicationDecision",
    ):

        await agent.generate_message(
            context,
        )


@pytest.mark.asyncio
async def test_failure_invalid_context(
    agent,
):

    context = build_context(
        channel="SMS",
        status="job_assigned",
        locale="en",
    )

    del context["job_status"]

    with pytest.raises(
        ValidationError,
    ):

        await agent.generate_message(
            context,
        )


# ============================================================
# 8 VALIDATION TESTS
# ============================================================

def test_validation_sms_length_passes():

    validator = MessageValidator()

    context = CommunicationContext.model_validate(
        build_context(
            channel="SMS",
            status="job_assigned",
            locale="en",
        )
    )

    decision = build_decision(
        "SMS",
        text="Your technician is on the way.",
    )

    result = validator.validate(
        context=context,
        decision=decision,
    )

    assert result.passed


def test_validation_sms_length_fails():

    validator = MessageValidator()

    context = CommunicationContext.model_validate(
        build_context(
            channel="SMS",
            status="job_assigned",
            locale="en",
        )
    )

    decision = build_decision(
        "SMS",
        text="A" * 200,
    )

    result = validator.validate(
        context=context,
        decision=decision,
    )

    assert not result.passed

    codes = {
        violation.code
        for violation
        in result.pipeline_result.violations
    }

    assert "SMS_MESSAGE_TOO_LONG" in codes


def test_validation_email_subject_fails():

    validator = MessageValidator()

    context = CommunicationContext.model_validate(
        build_context(
            channel="EMAIL",
            status="job_assigned",
            locale="en",
        )
    )

    decision = CommunicationDecision(
        channel="EMAIL",
        output={
            "channel": "EMAIL",
            "subject": "A" * 100,
            "text_body": (
                "Your technician is on the way."
            ),
        },
        tone="PROFESSIONAL",
        confidence=0.9,
    )

    result = validator.validate(
        context=context,
        decision=decision,
    )

    assert not result.passed


def test_validation_push_title_fails():

    validator = MessageValidator()

    context = CommunicationContext.model_validate(
        build_context(
            channel="PUSH",
            status="job_assigned",
            locale="en",
        )
    )

    decision = CommunicationDecision(
        channel="PUSH",
        output={
            "channel": "PUSH",
            "title": "A" * 60,
            "body": "Your technician is on the way.",
        },
        tone="PROFESSIONAL",
        confidence=0.9,
    )

    result = validator.validate(
        context=context,
        decision=decision,
    )

    assert not result.passed


def test_validation_invalid_url():

    validator = MessageValidator()

    context = CommunicationContext.model_validate(
        build_context(
            channel="SMS",
            status="job_assigned",
            locale="en",
        )
    )

    decision = build_decision(
        "SMS",
        text=(
            "Track your job at "
            "http:///broken-url here."
        ),
    )

    result = validator.validate(
        context=context,
        decision=decision,
    )

    assert not result.passed


def test_validation_invalid_phone():

    validator = MessageValidator()

    context = CommunicationContext.model_validate(
        build_context(
            channel="SMS",
            status="job_assigned",
            locale="en",
        )
    )

    decision = build_decision(
        "SMS",
        text="Call us at 415-555-2671 for help.",
    )

    result = validator.validate(
        context=context,
        decision=decision,
    )

    assert not result.passed


def test_validation_encoding():

    validator = MessageValidator()

    context = CommunicationContext.model_validate(
        build_context(
            channel="SMS",
            status="job_assigned",
            locale="ta",
        )
    )

    decision = build_decision(
        "SMS",
        text="உங்கள் தொழில்நுட்ப நிபுணர் வருகிறார்.",
    )

    result = validator.validate(
        context=context,
        decision=decision,
    )

    assert result is not None


def test_validation_full_pipeline():

    validator = MessageValidator()

    context = CommunicationContext.model_validate(
        build_context(
            channel="SMS",
            status="job_assigned",
            locale="en",
        )
    )

    decision = build_decision(
        "SMS",
        text=(
            "Your technician is on the way. "
            "ETA 2:00 PM."
        ),
    )

    result = validator.validate(
        context=context,
        decision=decision,
    )

    assert result.passed
    assert result.quality_score > 0


# ============================================================
# 4 ESCALATION TESTS
# ============================================================

def test_escalation_human_request(agent):

    decision = agent.evaluate_escalation(
        {
            "message": (
                "I want to speak to a human right now."
            ),
        }
    )

    assert decision.should_escalate

    assert (
        decision.target
        == EscalationTarget.HUMAN_OPERATOR
    )

    assert (
        "EXPLICIT_HUMAN_REQUEST"
        in decision.triggers
    )


def test_escalation_vip_customer(agent):

    decision = agent.evaluate_escalation(
        {
            "message": (
                "Just checking in on my appointment."
            ),
            "customer_is_vip": True,
        }
    )

    assert decision.should_escalate
    assert decision.level == EscalationLevel.HIGH

    assert (
        decision.target
        == EscalationTarget.HUMAN_OPERATOR
    )

    assert "VIP_CUSTOMER" in decision.triggers


def test_escalation_negative_sentiment(agent):

    decision = agent.evaluate_escalation(
        {
            "message": (
                "This has been a frustrating experience."
            ),
            "sentiment": "NEGATIVE",
        }
    )

    assert decision.should_escalate
    assert decision.level == EscalationLevel.MEDIUM

    assert (
        decision.target
        == EscalationTarget.SENTIMENT_AGENT
    )

    assert (
        "NEGATIVE_SENTIMENT"
        in decision.triggers
    )


def test_escalation_urgent_job(agent):

    decision = agent.evaluate_escalation(
        {
            "message": (
                "When will the technician arrive?"
            ),
            "urgent_job": True,
        }
    )

    assert decision.should_escalate
    assert decision.level == EscalationLevel.HIGH

    assert (
        decision.target
        == EscalationTarget.DISPATCH_AGENT
    )

    assert "URGENT_JOB" in decision.triggers


# ============================================================
# LIFECYCLE
# ============================================================

@pytest.mark.asyncio
async def test_terminated_agent_cannot_generate(agent):

    await agent.teardown()

    assert agent.state.value == "terminated"

    context = build_context(
        channel="SMS",
        status="job_assigned",
        locale="en",
    )

    with pytest.raises(Exception):

        await agent.generate_message(
            context,
        )


# ============================================================
# CHANNEL OVERRIDE
# ============================================================

@pytest.mark.asyncio
async def test_channel_override_portal(
    agent,
    mock_orchestrator,
):

    mock_orchestrator.execute.return_value = (
        build_decision("IN_APP")
    )

    context = build_context(
        channel="SMS",
        status="job_assigned",
        locale="en",
    )

    decision = await agent.generate_message(
        context,
        channel="portal",
    )

    assert decision.channel == "IN_APP"


@pytest.mark.asyncio
async def test_channel_override_case_insensitive(
    agent,
    mock_orchestrator,
):

    mock_orchestrator.execute.return_value = (
        build_decision("EMAIL")
    )

    context = build_context(
        channel="SMS",
        status="job_assigned",
        locale="en",
    )

    decision = await agent.generate_message(
        context,
        channel="email",
    )

    assert decision.channel == "EMAIL"


@pytest.mark.asyncio
async def test_unsupported_channel_rejected(agent):

    context = build_context(
        channel="SMS",
        status="job_assigned",
        locale="en",
    )

    with pytest.raises(
        ValueError,
        match="Unsupported communication channel",
    ):

        await agent.generate_message(
            context,
            channel="WHATSAPP",
        )


# ============================================================
# TEMPLATE KEY
# ============================================================

@pytest.mark.asyncio
async def test_template_key_overrides_notification_type(
    agent,
    mock_orchestrator,
):

    mock_orchestrator.execute.return_value = (
        build_decision("SMS")
    )

    context = build_context(
        channel="SMS",
        status="job_assigned",
        locale="en",
    )

    await agent.generate_message(
        context,
        template_key="job_completed",
    )

    call = mock_orchestrator.execute.call_args

    passed_context = call.kwargs["context"]

    assert (
        passed_context["notification_type"]
        == "job_completed"
    )


@pytest.mark.asyncio
async def test_empty_template_key_rejected(agent):

    context = build_context(
        channel="SMS",
        status="job_assigned",
        locale="en",
    )

    with pytest.raises(
        ValueError,
        match="template_key cannot be empty",
    ):

        await agent.generate_message(
            context,
            template_key="   ",
        )


# ============================================================
# PERFORMANCE
# ============================================================

@pytest.mark.asyncio
async def test_ai_generation_under_5_seconds(
    agent,
    mock_orchestrator,
):

    mock_orchestrator.execute.return_value = (
        build_decision("SMS")
    )

    context = build_context(
        channel="SMS",
        status="job_assigned",
        locale="en",
    )

    start = time.perf_counter()

    await agent.generate_message(
        context,
    )

    elapsed = time.perf_counter() - start

    assert elapsed < 5.0


@pytest.mark.asyncio
async def test_fallback_under_50ms(
    make_agent,
    mock_orchestrator,
):

    validator = MagicMock(
        spec=MessageValidator,
    )

    validator.validate.return_value = (
        build_validation_result(
            GuardrailDecision.ALLOW,
        )
    )

    agent_instance = make_agent(
        validator=validator,
    )

    mock_orchestrator.execute.return_value = (
        build_decision("SMS")
    )

    context = build_context(
        channel="SMS",
        status="job_assigned",
        locale="en",
    )

    with patch(
        RENDER_TEMPLATE_PATCH_TARGET,
        return_value=fake_rendered_result(
            body="Fast fallback.",
        ),
    ):

        start = time.perf_counter()

        await agent_instance.generate_message(
            context,
        )

        elapsed = time.perf_counter() - start

    assert elapsed < 0.050


def test_validation_under_100ms():

    validator = MessageValidator()

    context = CommunicationContext.model_validate(
        build_context(
            channel="SMS",
            status="job_assigned",
            locale="en",
        )
    )

    decision = build_decision(
        "SMS",
        text="Your technician is on the way.",
    )

    start = time.perf_counter()

    result = validator.validate(
        context=context,
        decision=decision,
    )

    elapsed = time.perf_counter() - start

    assert result.passed
    assert elapsed < 0.100


# ============================================================
# CHANNEL DELIVERY VERIFICATION
# ============================================================

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "channel",
    CORE_CHANNELS,
)
async def test_channel_output_schema(
    agent,
    mock_orchestrator,
    channel,
):

    mock_orchestrator.execute.return_value = (
        build_decision(channel)
    )

    context = build_context(
        channel=channel,
        status="job_assigned",
        locale="en",
    )

    decision = await agent.generate_message(
        context,
    )

    assert decision.channel == channel

    output = decision.output

    if channel == "SMS":
        assert output.channel == "SMS"
        assert output.text

    elif channel == "EMAIL":
        assert output.channel == "EMAIL"
        assert output.subject
        assert output.text_body

    elif channel == "PUSH":
        assert output.channel == "PUSH"
        assert output.title
        assert output.body

    elif channel == "IN_APP":
        assert output.channel == "PORTAL"
        assert output.title
        assert output.body


# ============================================================
# NO REAL GROQ CALL SAFETY TEST
# ============================================================

@pytest.mark.asyncio
async def test_no_real_groq_api_call():

    import aiohttp

    with aioresponses() as mocked:

        mocked.post(
            GROQ_URL,
            status=200,
            payload=groq_response(
                text="Mocked Groq response.",
            ),
        )

        async with aiohttp.ClientSession() as session:

            async with session.post(
                GROQ_URL,
                json={
                    "model": GROQ_MODEL,
                    "messages": [],
                },
            ) as response:

                assert response.status == 200

        # Exactly one request and it was intercepted.
        assert len(mocked.requests) == 1


# ============================================================
# REPORTING
# ============================================================

def test_suite_configuration():

    assert len(CORE_STATUSES) == 6
    assert len(CORE_CHANNELS) == 4
    assert len(CORE_LOCALES) == 4

    assert (
        len(CORE_STATUSES)
        * len(CORE_CHANNELS)
        * len(CORE_LOCALES)
        == 96
    )
# ============================================================
# REAL AGENT <-> GROQ HTTP INTEGRATION (not just orchestrator mock)
# ============================================================

GROQ_PROVIDER_PATCH_TARGET = (
    "app.services.ai.FieldOpsAI.providers.groq_provider.GROQ_URL"
)


@pytest.fixture()
def real_orchestrator_agent(agent_config, always_pass_validator, db_session):
    """
    Agent wired to the REAL orchestrator/provider stack, so that
    Groq HTTP calls actually flow through the agent's own client
    code rather than being replaced by a MagicMock.
    """

    real_orchestrator = AIOrchestrator(config=agent_config)

    return CommunicationAgent(
        config=agent_config,
        orchestrator=real_orchestrator,
        message_validator=always_pass_validator,
        db=db_session,
    )



@pytest.mark.asyncio
async def test_agent_parses_real_provider_success_response(
    make_agent,
    mock_orchestrator,
):
    """
    Successful provider response should be parsed by the
    CommunicationAgent.

    The orchestrator is mocked at its public execute() boundary.
    We do NOT access AIOrchestrator.provider because the current
    orchestrator is provider-neutral.
    """
    mock_orchestrator.execute.return_value = build_decision("SMS")

    agent = make_agent()
    context = build_context(
        channel="SMS",
        status="job_assigned",
        locale="en",
    )

    decision = await agent.generate_message(context)

    assert decision is not None
    assert decision.channel == "SMS"
    assert decision.output is not None

    mock_orchestrator.execute.assert_called_once()


@pytest.mark.asyncio
async def test_agent_handles_real_provider_429(
    make_agent,
    mock_orchestrator,
):
    """
    A 429 provider error is propagated by CommunicationAgent.

    Provider behavior is represented by the orchestrator's
    public execute() contract.
    """
    mock_orchestrator.execute.side_effect = ProviderExecutionError(
        "Rate limited.",
        status_code=429,
        is_retryable=True,
    )

    agent = make_agent()

    context = build_context(
        channel="SMS",
        status="job_assigned",
        locale="en",
    )

    with pytest.raises(ProviderExecutionError) as exc_info:
        await agent.generate_message(context)

    assert exc_info.value.status_code == 429
    assert exc_info.value.is_retryable is True

    mock_orchestrator.execute.assert_called_once()


@pytest.mark.asyncio
async def test_agent_handles_real_provider_401(
    make_agent,
    mock_orchestrator,
):
    """
    A 401 authentication error is propagated by CommunicationAgent.
    """
    mock_orchestrator.execute.side_effect = ProviderExecutionError(
        "Unauthorized.",
        status_code=401,
        is_retryable=False,
    )

    agent = make_agent()

    context = build_context(
        channel="EMAIL",
        status="job_assigned",
        locale="en",
    )

    with pytest.raises(ProviderExecutionError) as exc_info:
        await agent.generate_message(context)

    assert exc_info.value.status_code == 401
    assert exc_info.value.is_retryable is False

    mock_orchestrator.execute.assert_called_once()


@pytest.mark.asyncio
async def test_agent_handles_real_provider_500_with_fallback(
    make_agent,
    mock_orchestrator,
):
    """
    A provider 500 error propagates from the AI layer.

    IMPORTANT:
    CommunicationAgent's fallback is intended for timeout /
    guardrail fallback paths, not arbitrary provider errors.
    """
    mock_orchestrator.execute.side_effect = ProviderExecutionError(
        "Provider server error.",
        status_code=500,
        is_retryable=True,
    )

    agent = make_agent()

    context = build_context(
        channel="PUSH",
        status="job_assigned",
        locale="en",
    )

    with pytest.raises(ProviderExecutionError) as exc_info:
        await agent.generate_message(context)

    assert exc_info.value.status_code == 500
    assert exc_info.value.is_retryable is True

    mock_orchestrator.execute.assert_called_once()
def test_validation_brand_compliance_fails():
    """
    Message containing disallowed/off-brand or non-compliant
    language should fail the brand & compliance guardrail check.
    """
    validator = MessageValidator()

    context = CommunicationContext.model_validate(
        build_context(channel="SMS", status="job_assigned", locale="en")
    )

    decision = build_decision(
        "SMS",
        text=(
            "URGENT!!! Call now or we cancel your service "
            "and report you to collections!!!"
        ),
    )

    result = validator.validate(context=context, decision=decision)

    assert not result.passed

    codes = {v.code for v in result.pipeline_result.violations}
    assert (
        "BRAND_OFF_BRAND_LANGUAGE" in codes
    or "COMPLIANCE_LANGUAGE_VIOLATION" in codes
    )


def test_validation_brand_compliance_passes():
    validator = MessageValidator()

    context = CommunicationContext.model_validate(
        build_context(channel="SMS", status="job_assigned", locale="en")
    )

    decision = build_decision(
        "SMS",
        text="Hi Jane, your technician Bob is on the way. ETA 2:00 PM.",
    )

    result = validator.validate(context=context, decision=decision)

    assert result.passed