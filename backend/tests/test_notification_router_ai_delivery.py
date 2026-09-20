"""
Tests for production-safe customer SMS and email delivery
through NotificationRouter.
"""

from __future__ import annotations

from datetime import (
    datetime,
    timezone,
)

import pytest

from app.services.ai.FieldOpsAI.schemas.communication import (
    CommunicationDecision,
)
from app.services.ai.FieldOpsAI.services.communication_service import (
    CommunicationServiceResult,
)
from app.services.ai.guardrails.contracts import (
    GuardrailPipelineResult,
)
from app.services.ai.integrations.communication_integration import (
    CommunicationIntegrationError,
)
from app.services.notification_services import (
    JobStatusEvent,
    NotificationRouter,
)


class FakeCommunicationIntegration:
    """
    Controlled production-integration replacement.
    """

    def __init__(
        self,
        *,
        fail: bool = False,
    ) -> None:
        self.fail = fail
        self.calls: list[dict] = []

    async def generate(
        self,
        *,
        event,
        recipient_type: str,
        channel: str,
        notification_type: str,
        locale: str = "en",
    ) -> CommunicationServiceResult:
        self.calls.append(
            {
                "recipient_type": (
                    recipient_type
                ),
                "channel": channel,
                "notification_type": (
                    notification_type
                ),
                "locale": locale,
            }
        )

        if self.fail:
            raise CommunicationIntegrationError(
                "Simulated safe generation failure."
            )

        normalized_channel = (
            channel.upper()
        )

        if normalized_channel == "EMAIL":
            decision = CommunicationDecision(
                channel="EMAIL",
                title=None,
                subject="Your service is complete",
                message=(
                    "<p>Your FieldOps service "
                    "has been completed.</p>"
                ),
                tone="PROFESSIONAL",
                confidence=1.0,
            )

        else:
            decision = CommunicationDecision(
                channel="SMS",
                title=None,
                subject=None,
                message=(
                    "Your technician is on the way."
                ),
                tone="PROFESSIONAL",
                confidence=1.0,
            )

        guardrail_result = (
            GuardrailPipelineResult.from_checks(
                checks=(),
                total_latency_ms=0.0,
            )
        )

        return CommunicationServiceResult(
            decision=decision,
            used_fallback=False,
            fallback_source=None,
            fallback_template_id=None,
            fallback_template_version=None,
            guardrail_result=(
                guardrail_result
            ),
            audit_record_count=0,
        )


class FakeEmailService:
    """
    Record email delivery calls.
    """

    def __init__(
        self,
    ) -> None:
        self.calls: list[
            tuple[
                str,
                str,
                str,
            ]
        ] = []

    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
    ) -> bool:
        self.calls.append(
            (
                to_email,
                subject,
                html_content,
            )
        )

        return True


def build_event(
    *,
    status: str = "EN_ROUTE",
) -> JobStatusEvent:
    """
    Build a customer job-status event.
    """

    return JobStatusEvent(
        job_id="101",
        tenant_id="tenant-123",
        from_status="ASSIGNED",
        to_status=status,
        actor_id="tech-1",
        actor_role="technician",
        reason="Status changed",
        timestamp=datetime.now(
            timezone.utc
        ),
        job_title="Leak Repair",
        job_location="123 Main Street",
        technician_id="tech-1",
        technician_name="John Tech",
        customer_id="customer-1",
        customer_name="Alice",
        customer_phone="+15555550101",
        customer_email="alice@example.com",
        eta="15 minutes",
        notification_channels=[],
    )


@pytest.mark.anyio
async def test_customer_sms_uses_safe_communication(
    monkeypatch,
) -> None:
    """
    Customer SMS body comes from CommunicationService output,
    not from a hardcoded status message.
    """

    integration = (
        FakeCommunicationIntegration()
    )

    router = NotificationRouter(
        fcm_service=lambda *args, **kwargs: None,
        sms_service=lambda *args, **kwargs: None,
        email_service=FakeEmailService(),
        ws_manager=object(),
        redis_client=None,
        communication_integration=(
            integration
        ),
    )

    # The configured local Twilio account is already treated as
    # mock mode, so no network request is made.
    monkeypatch.setattr(
        "app.services.twilio_sms.TWILIO_ACCOUNT_SID",
        "mock",
    )

    delivered = await router._send_sms(
        build_event(),
        "customer",
        {},
        "technician_en_route",
    )

    assert delivered is True

    assert len(
        integration.calls
    ) == 1

    assert integration.calls[0] == {
        "recipient_type": "customer",
        "channel": "sms",
        "notification_type": (
            "technician_en_route"
        ),
        "locale": "en",
    }


@pytest.mark.anyio
async def test_customer_email_uses_safe_subject_and_body(
) -> None:
    """
    SendGrid receives the validated CommunicationDecision.
    """

    integration = (
        FakeCommunicationIntegration()
    )

    email = FakeEmailService()

    router = NotificationRouter(
        fcm_service=lambda *args, **kwargs: None,
        sms_service=lambda *args, **kwargs: None,
        email_service=email,
        ws_manager=object(),
        redis_client=None,
        communication_integration=(
            integration
        ),
    )

    delivered = await router._send_email(
        build_event(
            status="COMPLETED"
        ),
        "customer",
        {},
        {
            "include_survey_link": True,
        },
        "job_completed",
    )

    assert delivered is True
    assert len(email.calls) == 1

    (
        recipient,
        subject,
        body,
    ) = email.calls[0]

    assert recipient == (
        "alice@example.com"
    )

    assert subject == (
        "Your service is complete"
    )

    assert (
        "Your FieldOps service "
        "has been completed."
        in body
    )

    assert (
        "https://fieldops.io/survey/101"
        in body
    )


@pytest.mark.anyio
async def test_generation_failure_skips_sms_delivery(
) -> None:
    """
    Unsafe hardcoded content is not sent when production
    generation fails.
    """

    integration = (
        FakeCommunicationIntegration(
            fail=True
        )
    )

    router = NotificationRouter(
        fcm_service=lambda *args, **kwargs: None,
        sms_service=lambda *args, **kwargs: None,
        email_service=FakeEmailService(),
        ws_manager=object(),
        redis_client=None,
        communication_integration=(
            integration
        ),
    )

    delivered = await router._send_sms(
        build_event(),
        "customer",
        {},
        "technician_en_route",
    )

    assert delivered is False


@pytest.mark.anyio
async def test_generation_failure_skips_email_delivery(
) -> None:
    """
    Email is not sent when no safe communication is available.
    """

    integration = (
        FakeCommunicationIntegration(
            fail=True
        )
    )

    email = FakeEmailService()

    router = NotificationRouter(
        fcm_service=lambda *args, **kwargs: None,
        sms_service=lambda *args, **kwargs: None,
        email_service=email,
        ws_manager=object(),
        redis_client=None,
        communication_integration=(
            integration
        ),
    )

    delivered = await router._send_email(
        build_event(
            status="COMPLETED"
        ),
        "customer",
        {},
        {
            "include_survey_link": True,
        },
        "job_completed",
    )

    assert delivered is False
    assert email.calls == []


def test_legacy_template_names_are_normalized(
) -> None:
    """
    Existing routing names resolve to approved fallback event
    types.
    """

    assert (
        NotificationRouter
        ._resolve_notification_type(
            "job_done_survey"
        )
        == "job_completed"
    )

    assert (
        NotificationRouter
        ._resolve_notification_type(
            "job_cancelled_customer"
        )
        == "job_cancelled"
    )

    assert (
        NotificationRouter
        ._resolve_notification_type(
            "journey_started"
        )
        == "technician_en_route"
    )