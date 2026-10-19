"""
Tests for technician SMS/push and dispatcher in-app delivery
through the production-safe communication workflow.
"""

from __future__ import annotations

from datetime import (
    datetime,
    timezone,
)
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import app.services.notification_services as notification_module

from app.services.ai.FieldOpsAI.schemas.communication import (
    CommunicationDecision,
)
from app.services.ai.FieldOpsAI.services.communication_service import (
    CommunicationServiceResult,
)
from app.services.ai.guardrails.contracts import (
    GuardrailPipelineResult,
)
from app.services.notification_services import (
    JobStatusEvent,
    NotificationRouter,
)
from app.services.ai.FieldOpsAI.schemas.communication_configuration import (
    CommunicationMessageCategory,
)


class FakeCommunicationIntegration:
    """
    Return controlled safe communication decisions.
    """

    def __init__(
        self,
    ) -> None:
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
                "recipient_type": recipient_type,
                "channel": channel,
                "notification_type": (
                    notification_type
                ),
                "locale": locale,
            }
        )

        normalized_channel = (
            channel.upper()
        )

        if normalized_channel == "PUSH":
            decision = CommunicationDecision(
                channel="PUSH",
                title="Safe technician update",
                subject=None,
                message=(
                    "Open FieldOps for job details."
                ),
                tone="PROFESSIONAL",
                confidence=1.0,
            )

        elif normalized_channel == "IN_APP":
            decision = CommunicationDecision(
                channel="IN_APP",
                title="Safe dispatcher update",
                subject=None,
                message=(
                    "The job status has changed safely."
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
                    "A FieldOps job has an update. "
                    "Open the app for details."
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


class FakeRedis:
    """
    Record dispatcher digest entries.
    """

    def __init__(
        self,
    ) -> None:
        self.values: dict[
            str,
            list[str],
        ] = {}

    def lpush(
        self,
        key: str,
        value: str,
    ) -> int:
        self.values.setdefault(
            key,
            [],
        ).insert(
            0,
            value,
        )

        return len(
            self.values[key]
        )


class FakeWebSocketManager:
    """
    Record dispatcher broadcasts.
    """

    def __init__(
        self,
    ) -> None:
        self.calls: list[
            tuple[
                str,
                dict,
            ]
        ] = []

    async def broadcast(
        self,
        channel: str,
        payload: dict,
    ) -> bool:
        self.calls.append(
            (
                channel,
                payload,
            )
        )

        return True


def _patch_dispatcher_notification_db(monkeypatch):
    """Provide one dispatcher recipient for the persistence/broadcast path."""
    db = MagicMock()
    dispatcher = SimpleNamespace(id="dispatcher-1")

    def query(model):
        result = MagicMock()
        if model.__name__ == "User":
            result.filter.return_value.all.return_value = [dispatcher]
        else:
            result.filter.return_value.first.return_value = None
        return result

    db.query.side_effect = query
    monkeypatch.setattr(
        notification_module,
        "SessionLocal",
        lambda: db,
    )
    return db


class FakeEmailService:
    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
    ) -> bool:
        _ = to_email
        _ = subject
        _ = html_content

        return True


def build_event(
    *,
    status: str = "ASSIGNED",
) -> JobStatusEvent:
    return JobStatusEvent(
        job_id="101",
        tenant_id="tenant-123",
        from_status="CREATED",
        to_status=status,
        actor_id="dispatcher-1",
        actor_role="dispatcher",
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
async def test_technician_push_uses_safe_title_and_body(
    monkeypatch,
) -> None:
    """
    Firebase receives only CommunicationService output.
    """

    technician = MagicMock()
    technician.fcm_token = "test-fcm-token"

    db = MagicMock()

    (
        db.query.return_value
        .filter.return_value
        .first.return_value
    ) = technician

    monkeypatch.setattr(
        notification_module,
        "SessionLocal",
        lambda: db,
    )

    fcm_calls: list[dict] = []

    async def fake_fcm(
        *args,
        **kwargs,
    ):
        _ = args

        fcm_calls.append(
            kwargs
        )

        return {
            "sent": 1,
            "failed": 0,
            "delivery_ids": [],
        }

    integration = (
        FakeCommunicationIntegration()
    )

    router = NotificationRouter(
        fcm_service=fake_fcm,
        sms_service=MagicMock(),
        email_service=FakeEmailService(),
        ws_manager=FakeWebSocketManager(),
        redis_client=FakeRedis(),
        communication_integration=(
            integration
        ),
    )

    delivered = await router._send_push(
        build_event(),
        "technician",
        {},
        "high",
        "technician_job_assigned",
    )

    assert delivered is True
    assert len(fcm_calls) == 1

    assert (
        fcm_calls[0]["notification_title"]
        == "Safe technician update"
    )

    assert (
        fcm_calls[0]["notification_body"]
        == "Open FieldOps for job details."
    )

    assert (
        fcm_calls[0]["notification_type"]
        == "technician_job_assigned"
    )

    assert integration.calls[0][
        "recipient_type"
    ] == "technician"

    assert integration.calls[0][
        "channel"
    ] == "push"

    db.close.assert_called_once()


@pytest.mark.anyio
async def test_technician_sms_uses_safe_message(
    monkeypatch,
) -> None:
    """
    Twilio technician service receives safe generated text.
    """

    db = MagicMock()

    monkeypatch.setattr(
        notification_module,
        "SessionLocal",
        lambda: db,
    )

    sms_calls: list[dict] = []

    async def fake_sms(
        *args,
        **kwargs,
    ):
        _ = args

        sms_calls.append(
            kwargs
        )

        return {
            "sent": 1,
            "failed": 0,
            "delivery_ids": [],
        }

    integration = (
        FakeCommunicationIntegration()
    )

    router = NotificationRouter(
        fcm_service=MagicMock(),
        sms_service=fake_sms,
        email_service=FakeEmailService(),
        ws_manager=FakeWebSocketManager(),
        redis_client=FakeRedis(),
        communication_integration=(
            integration
        ),
    )

    delivered = await router._send_sms(
        build_event(),
        "technician",
        {},
        "technician_job_assigned",
    )

    assert delivered is True
    assert len(sms_calls) == 1

    assert sms_calls[0]["effective_message"] == (
        "A FieldOps job has an update. "
        "Open the app for details."
    )

    assert sms_calls[0]["category"] == (
        CommunicationMessageCategory.STANDARD
    )
    assert "message_body" not in sms_calls[0]

    assert integration.calls[0][
        "recipient_type"
    ] == "technician"

    assert integration.calls[0][
        "channel"
    ] == "sms"

    db.close.assert_called_once()


@pytest.mark.anyio
async def test_dispatcher_digest_contains_safe_content(
    monkeypatch,
) -> None:
    """
    Batched dispatcher delivery persists and broadcasts safe in-app content.
    """

    redis = FakeRedis()
    websocket = FakeWebSocketManager()
    _patch_dispatcher_notification_db(monkeypatch)

    integration = (
        FakeCommunicationIntegration()
    )

    router = NotificationRouter(
        fcm_service=MagicMock(),
        sms_service=MagicMock(),
        email_service=FakeEmailService(),
        ws_manager=websocket,
        redis_client=redis,
        communication_integration=(
            integration
        ),
    )

    delivered = await router._send_in_app(
        build_event(),
        "dispatcher",
        {
            "job_id": "101",
            "status": "ASSIGNED",
        },
        True,
        "dispatcher_job_assigned",
    )

    assert delivered is True

    assert redis.values == {}
    assert len(websocket.calls) == 1
    _, envelope = websocket.calls[0]
    assert envelope["payload"]["title"] == "Safe dispatcher update"
    assert envelope["payload"]["body"].startswith(
        "The job status has changed safely."
    )
    assert "Technician: John Tech." in envelope["payload"]["body"]
    assert envelope["payload"]["type"] == "dispatcher_job_assigned"


@pytest.mark.anyio
async def test_dispatcher_immediate_broadcast_uses_safe_content(
    monkeypatch,
) -> None:
    """
    WebSocket receives safe in-app content.
    """

    websocket = (
        FakeWebSocketManager()
    )
    _patch_dispatcher_notification_db(monkeypatch)

    router = NotificationRouter(
        fcm_service=MagicMock(),
        sms_service=MagicMock(),
        email_service=FakeEmailService(),
        ws_manager=websocket,
        redis_client=FakeRedis(),
        communication_integration=(
            FakeCommunicationIntegration()
        ),
    )

    delivered = await router._send_in_app(
        build_event(
            status="CANCELLED"
        ),
        "dispatcher",
        {
            "job_id": "101",
            "status": "CANCELLED",
        },
        False,
        "dispatcher_cancelled",
    )

    assert delivered is True
    assert len(websocket.calls) == 1

    channel, envelope = (
        websocket.calls[0]
    )

    assert channel == (
        "tenant:tenant-123:dispatchers"
    )

    assert envelope["type"] == "new_notification"

    assert envelope["payload"]["title"] == (
        "Safe dispatcher update"
    )

    assert envelope["payload"]["body"].startswith(
        "The job status has changed safely."
    )
    assert "Technician: John Tech." in envelope["payload"]["body"]


def test_routing_uses_recipient_specific_templates(
) -> None:
    """
    Technician and dispatcher routing no longer reuse customer
    fallback names.
    """

    assert (
        NotificationRouter
        .STATUS_NOTIFICATIONS[
            "ASSIGNED"
        ]["technician"]["template"]
        == "technician_job_assigned"
    )

    assert (
        NotificationRouter
        .STATUS_NOTIFICATIONS[
            "EN_ROUTE"
        ]["technician"]["template"]
        == "technician_journey_started"
    )

    assert (
        NotificationRouter
        .STATUS_NOTIFICATIONS[
            "ASSIGNED"
        ]["dispatcher"]["template"]
        == "dispatcher_job_assigned"
    )


@pytest.mark.anyio
@pytest.mark.parametrize("invalid_subject", [
    None,
    12345,
    [],
    "",
    "   ",
    "A" * 79
])
async def test_email_rejects_invalid_subjects(invalid_subject) -> None:
    """
    Invalid subjects must be rejected before delivery.
    """
    from unittest.mock import AsyncMock
    email_service = FakeEmailService()
    email_service.send_email = AsyncMock(return_value=True)

    class SubjectCommunicationIntegration:
        async def generate(self, *args, **kwargs):
            import types
            decision = types.SimpleNamespace(
                channel="EMAIL",
                title=None,
                subject=invalid_subject,
                message="Test Message",
                output=types.SimpleNamespace(
                    subject=invalid_subject,
                    text="Test Message",
                    title=None,
                    body="Test Message",
                    html_body="Test Message",
                    text_body="Test Message"
                )
            )
            return types.SimpleNamespace(decision=decision)

    router = NotificationRouter(
        fcm_service=MagicMock(),
        sms_service=MagicMock(),
        email_service=email_service,
        ws_manager=FakeWebSocketManager(),
        redis_client=FakeRedis(),
        communication_integration=SubjectCommunicationIntegration(),
    )

    delivered = await router._send_email(
        build_event(status="COMPLETED"),
        "customer",
        {},
        {"include_survey_link": False},
        "job_done_survey"
    )

    assert delivered is False
    email_service.send_email.assert_not_called()


@pytest.mark.anyio
@pytest.mark.parametrize("valid_subject", [
    "A" * 78,
    "Normal subject"
])
async def test_email_accepts_valid_subjects(valid_subject) -> None:
    """
    Valid subjects up to 78 characters must be accepted.
    """
    from unittest.mock import AsyncMock
    email_service = FakeEmailService()
    email_service.send_email = AsyncMock(return_value=True)

    class SubjectCommunicationIntegration:
        async def generate(self, *args, **kwargs) -> CommunicationServiceResult:
            decision = CommunicationDecision(
                channel="EMAIL",
                title=None,
                subject=valid_subject,
                message="Test Message",
                tone="PROFESSIONAL",
                confidence=1.0,
            )
            return CommunicationServiceResult(
                decision=decision,
                used_fallback=False,
                fallback_source=None,
                fallback_template_id=None,
                fallback_template_version=None,
                guardrail_result=GuardrailPipelineResult.from_checks(checks=(), total_latency_ms=0.0),
                audit_record_count=0,
            )

    router = NotificationRouter(
        fcm_service=MagicMock(),
        sms_service=MagicMock(),
        email_service=email_service,
        ws_manager=FakeWebSocketManager(),
        redis_client=FakeRedis(),
        communication_integration=SubjectCommunicationIntegration(),
    )

    delivered = await router._send_email(
        build_event(status="COMPLETED"),
        "customer",
        {},
        {"include_survey_link": False},
        "job_done_survey"
    )

    assert delivered is True
    email_service.send_email.assert_called_once()

@pytest.mark.anyio
async def test_route_publishes_notification_lifecycle_events(
    monkeypatch,
) -> None:
    lifecycle_events = []
    mock_redis = MagicMock()
    mock_redis.get.return_value = None
    mock_redis.set.return_value = True

    async def publish_lifecycle(**kwargs):
        lifecycle_events.append(kwargs)
        return True

    router = NotificationRouter(
        fcm_service=MagicMock(),
        sms_service=MagicMock(),
        email_service=FakeEmailService(),
        ws_manager=MagicMock(),
        redis_client=mock_redis,
        communication_integration=FakeCommunicationIntegration(),
        lifecycle_event_publisher=publish_lifecycle,
    )

    async def fake_send_push(*args, **kwargs):
        return True

    monkeypatch.setattr(
        router,
        "_send_push",
        fake_send_push,
    )

    await router.route(
        build_event(status="ASSIGNED"),
    )

    push_events = [
        item
        for item in lifecycle_events
        if item["payload"]["channel"] == "push"
    ]

    assert len(push_events) == 2
    assert [
        item["event_type"]
        for item in push_events
    ] == [
        "NOTIFICATION_QUEUED",
        "NOTIFICATION_SENT",
    ]

    assert all(
        item["job_id"] == "101"
        for item in push_events
    )

    assert all(
        item["tenant_id"] == "tenant-123"
        for item in push_events
    )


@pytest.mark.anyio
async def test_duplicate_notification_lifecycle_event_is_not_published(
) -> None:
    lifecycle_events = []
    mock_redis = MagicMock()
    mock_redis.get.return_value = "1"

    async def publish_lifecycle(**kwargs):
        lifecycle_events.append(kwargs)
        return True

    router = NotificationRouter(
        fcm_service=MagicMock(),
        sms_service=MagicMock(),
        email_service=FakeEmailService(),
        ws_manager=MagicMock(),
        redis_client=mock_redis,
        communication_integration=FakeCommunicationIntegration(),
        lifecycle_event_publisher=publish_lifecycle,
    )

    await router._publish_notification_lifecycle(
        event=build_event(status="ASSIGNED"),
        event_type="NOTIFICATION_QUEUED",
        event_id="notification:tenant-123:101:technician:push:job_assigned:queued",
        recipient_type="technician",
        channel="push",
        notification_type="job_assigned",
    )

    assert lifecycle_events == []

@pytest.mark.anyio
async def test_notification_failed_lifecycle_event_is_published():
    lifecycle_events = []
    mock_redis = MagicMock()
    mock_redis.get.return_value = None
    mock_redis.set.return_value = True

    async def publish_lifecycle(**kwargs):
        lifecycle_events.append(kwargs)
        return True

    router = NotificationRouter(
        fcm_service=MagicMock(),
        sms_service=MagicMock(),
        email_service=FakeEmailService(),
        ws_manager=MagicMock(),
        redis_client=mock_redis,
        communication_integration=FakeCommunicationIntegration(),
        lifecycle_event_publisher=publish_lifecycle,
    )

    async def fake_send_push(*args, **kwargs):
        return False

    router._send_push = fake_send_push

    await router.route(build_event(status="ASSIGNED"))

    failed_events = [
        event for event in lifecycle_events
        if event["event_type"] == "NOTIFICATION_FAILED"
        and event["payload"]["channel"] == "push"
    ]

    assert failed_events
    assert failed_events[0]["job_id"] == "101"
    assert failed_events[0]["tenant_id"] == "tenant-123"

@pytest.mark.anyio
async def test_notification_retried_lifecycle_event_is_published():
    lifecycle_events = []
    mock_redis = MagicMock()
    mock_redis.get.return_value = None
    mock_redis.set.return_value = True

    async def publish_lifecycle(**kwargs):
        lifecycle_events.append(kwargs)
        return True

    router = NotificationRouter(
        fcm_service=MagicMock(),
        sms_service=MagicMock(),
        email_service=FakeEmailService(),
        ws_manager=MagicMock(),
        redis_client=mock_redis,
        communication_integration=FakeCommunicationIntegration(),
        lifecycle_event_publisher=publish_lifecycle,
    )

    async def fake_send_sms(
        db,
        job_id,
        job_title,
        location,
        priority,
        tech_ids,
        correlation_id,
        **kwargs,
    ):
        await kwargs["on_retry"](attempt=2, delivery_id=123)
        return {"sent": 1, "failed": 0}

    router.sms = fake_send_sms

    delivered = await router._send_sms(
        event=build_event(status="ASSIGNED"),
        recipient_type="technician",
        payload={},
        notification_type="job_assigned",
    )

    retry_events = [
        event for event in lifecycle_events
        if event["event_type"] == "NOTIFICATION_RETRIED"
    ]

    assert delivered is True
    assert len(retry_events) == 1
    assert retry_events[0]["payload"]["attempt"] == 2
    assert retry_events[0]["job_id"] == "101"
    assert retry_events[0]["tenant_id"] == "tenant-123"
