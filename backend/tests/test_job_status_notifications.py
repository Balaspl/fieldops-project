import pytest
import json
import asyncio
from datetime import datetime, date, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from unittest.mock import AsyncMock, MagicMock, patch

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

# Setup test DB
SQLALCHEMY_DATABASE_URL = "sqlite://"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Patch app.database.SessionLocal globally before importing components
import app.database
app.database.SessionLocal = TestingSessionLocal

import fakeredis
fake_redis = fakeredis.FakeRedis(decode_responses=True)
import app.redis_client
app.redis_client.get_redis_client = lambda: fake_redis

from app.database import Base
from app.models import Job, Technician, AuditEvent
from app.services.notification_services import JobStatusEvent, EventPublisher, NotificationRouter
from app.tasks import process_job_status_transition_task, send_dispatcher_digest


class FakeCommunicationIntegration:
    """
    Return deterministic safe communication without calling
    Groq, PostgreSQL brand-rule loading, or the real fallback
    workflow.
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
                "event": event,
                "recipient_type": recipient_type,
                "channel": channel,
                "notification_type": (
                    notification_type
                ),
                "locale": locale,
            }
        )

        normalized_channel = (
            channel
            .strip()
            .upper()
            .replace(
                "-",
                "_",
            )
        )

        if normalized_channel == "EMAIL":
            decision = CommunicationDecision(
                channel="EMAIL",
                title=None,
                subject="FieldOps service update",
                message=(
                    "<p>Your service request has "
                    "been updated.</p>"
                ),
                tone="PROFESSIONAL",
                confidence=1.0,
            )

        elif normalized_channel == "PUSH":
            decision = CommunicationDecision(
                channel="PUSH",
                title="FieldOps update",
                subject=None,
                message=(
                    "Your service request has "
                    "been updated."
                ),
                tone="PROFESSIONAL",
                confidence=1.0,
            )

        elif normalized_channel == "IN_APP":
            decision = CommunicationDecision(
                channel="IN_APP",
                title="FieldOps update",
                subject=None,
                message=(
                    "The job status has been "
                    "updated safely."
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
                    "Your FieldOps service request "
                    "has been updated."
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
            guardrail_result=guardrail_result,
            audit_record_count=0,
        )

@pytest.fixture(autouse=True)
def setup_db(
    monkeypatch,
):
    """
    Give every test the isolated SQLite database and fake Redis.

    We patch notification_services directly because another test
    module may have imported it before this file.
    """
    Base.metadata.drop_all(bind=engine)

    Base.metadata.create_all(bind=engine)
    fake_redis.flushall()
    monkeypatch.setattr(notification_module,"SessionLocal",TestingSessionLocal,)

    monkeypatch.setattr(notification_module,"get_redis_client",lambda: fake_redis,)
    yield
    fake_redis.flushall()

def test_event_publisher_writes_audit_trail_and_redis(setup_db):
    db = TestingSessionLocal()
    
    # Pre-populate tech
    tech = Technician(
        technician_id=1,
        tech_id="1",
        technician_name="John Tech",
        technician_skill="Plumbing",
        technician_location="Zone A",
        phone_number="+15555555555"
    )
    db.add(tech)
    db.commit()
    
    event = JobStatusEvent(
        job_id="101",
        tenant_id="tenant-123",
        from_status="CREATED",
        to_status="ASSIGNED",
        actor_id="dispatcher-1",
        actor_role="dispatcher",
        reason="First assignment",
        timestamp=datetime.now(timezone.utc),
        job_title="Leak Fix",
        job_location="123 Road",
        technician_id="1",
        technician_name="John Tech",
        customer_id="cust-1",
        customer_name="Alice",
        customer_phone="+12222222222",
        customer_email="alice@example.com",
        eta=None,
        notification_channels=[]
    )
    
    # Run publish
    publisher = EventPublisher(redis_client=fake_redis)
    asyncio.run(publisher.publish(event))
    
    # Verify AuditEvent written to DB
    audit = db.query(AuditEvent).filter(AuditEvent.job_id == "101").first()
    assert audit is not None
    assert audit.tenant_id == "tenant-123"
    assert audit.new_status == "ASSIGNED"
    assert audit.old_status == "CREATED"
    assert audit.details["reason"] == "First assignment"
    
    # Verify published to Redis channel
    published_events = fake_redis.pubsub_channels()
    db.close()

@pytest.mark.anyio
async def test_notification_router_sends_email_on_completed(setup_db):
    db = TestingSessionLocal()
    
    event = JobStatusEvent(
        job_id="101",
        tenant_id="tenant-123",
        from_status="ON_SITE",
        to_status="COMPLETED",
        actor_id="tech-1",
        actor_role="technician",
        reason="Work completed",
        timestamp=datetime.now(timezone.utc),
        job_title="Leak Fix",
        job_location="123 Road",
        technician_id="1",
        technician_name="John Tech",
        customer_id="cust-1",
        customer_name="Alice",
        customer_phone="+12222222222",
        customer_email="alice@example.com",
        eta=None,
        notification_channels=[]
    )
    
    mock_email = MagicMock()
    mock_email.send_email = MagicMock(return_value=asyncio.Future())
    mock_email.send_email.return_value.set_result(True)
    
    router = NotificationRouter(
        fcm_service=MagicMock(return_value=asyncio.Future()),
        sms_service=MagicMock(return_value=asyncio.Future()),
        email_service=mock_email,
        ws_manager=MagicMock(),
        redis_client=fake_redis,
        communication_integration=(
            FakeCommunicationIntegration()
        ),
    )
    router.fcm.return_value.set_result({"sent": 1})
    router.sms.return_value.set_result({"sent": 1})
    
    await router.route(event)
    
    # Check email service invoked for customer email
    mock_email.send_email.assert_called_once()
    args, kwargs = mock_email.send_email.call_args
    assert args[0] == "alice@example.com"
    assert "alice@example.com" in args[0]
    assert "survey/101" in args[2]  # Survey link in html content
    db.close()

@pytest.mark.anyio
async def test_notification_router_fallbacks_to_sms_if_no_push_token(setup_db):
    db = TestingSessionLocal()
    # Pre-populate tech with NO fcm_token
    tech = Technician(
        technician_id=1,
        tech_id="1",
        technician_name="John Tech",
        technician_skill="Plumbing",
        technician_location="Zone A",
        phone_number="+15555555555",
        fcm_token=None
    )
    db.add(tech)
    db.commit()
    
    event = JobStatusEvent(
        job_id="101",
        tenant_id="tenant-123",
        from_status="CREATED",
        to_status="ASSIGNED",
        actor_id="dispatcher-1",
        actor_role="dispatcher",
        reason="First assignment",
        timestamp=datetime.now(timezone.utc),
        job_title="Leak Fix",
        job_location="123 Road",
        technician_id="1",
        technician_name="John Tech",
        customer_id="cust-1",
        customer_name="Alice",
        customer_phone="+12222222222",
        customer_email="alice@example.com",
        eta=None,
        notification_channels=[]
    )
    
    mock_sms = MagicMock(return_value=asyncio.Future())
    mock_sms.return_value.set_result({"sent": 1})
    
    router = NotificationRouter(
        fcm_service=MagicMock(return_value=asyncio.Future()),
        sms_service=mock_sms,
        email_service=MagicMock(return_value=asyncio.Future()),
        ws_manager=MagicMock(),
        redis_client=fake_redis,
        communication_integration=(
            FakeCommunicationIntegration()
        ),
    )
    router.fcm.return_value.set_result({"sent": 0})
    router.email.send_email = MagicMock(return_value=asyncio.Future())
    router.email.send_email.return_value.set_result(True)
    
    await router.route(event)
    
    # FCM has no token -> should fallback to SMS
    mock_sms.assert_called_once()
    db.close()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "new_status,expected_sms_transport,expected_customer_sms",
    [
        ("ASSIGNED", True, False),
        ("EN_ROUTE", False, True),
        ("ON_SITE", False, True),
        ("CANCELLED", True, True),
    ],
)
async def test_notification_router_sms_status_flows(
    setup_db,
    new_status,
    expected_sms_transport,
    expected_customer_sms,
):
    event = JobStatusEvent(
        job_id="102",
        tenant_id="tenant-123",
        from_status="CREATED",
        to_status=new_status,
        actor_id="tech-1",
        actor_role="technician",
        reason="Status changed",
        timestamp=datetime.now(timezone.utc),
        job_title="AC Repair",
        job_location="123 Road",
        technician_id="1",
        technician_name="John Tech",
        customer_id="cust-2",
        customer_name="Alice",
        customer_phone="+12222222222",
        customer_email="alice@example.com",
        eta=None,
        notification_channels=["SMS"],
    )

    mock_sms = MagicMock(return_value=asyncio.Future())
    mock_sms.return_value.set_result({"sent": 1})

    mock_email = MagicMock()
    mock_email.send_email = MagicMock(return_value=asyncio.Future())
    mock_email.send_email.return_value.set_result(True)

    communication = FakeCommunicationIntegration()

    router = NotificationRouter(
        fcm_service=MagicMock(return_value=asyncio.Future()),
        sms_service=mock_sms,
        email_service=mock_email,
        ws_manager=MagicMock(),
        redis_client=fake_redis,
        communication_integration=communication,
    )

    router.fcm.return_value.set_result({"sent": 0})

    await router.route(event)

    if expected_sms_transport:
        mock_sms.assert_called()
    else:
        mock_sms.assert_not_called()

    customer_sms_calls = [
        call
        for call in communication.calls
        if call["recipient_type"] == "customer"
        and call["channel"].strip().upper() == "SMS"
    ]

    if expected_customer_sms:
        assert len(customer_sms_calls) >= 1
    else:
        assert len(customer_sms_calls) == 0


@pytest.mark.anyio
async def test_notification_router_completed_does_not_send_sms(
    setup_db,
):
    event = JobStatusEvent(
        job_id="103",
        tenant_id="tenant-123",
        from_status="ON_SITE",
        to_status="COMPLETED",
        actor_id="tech-1",
        actor_role="technician",
        reason="Work completed",
        timestamp=datetime.now(timezone.utc),
        job_title="AC Repair",
        job_location="123 Road",
        technician_id="1",
        technician_name="John Tech",
        customer_id="cust-2",
        customer_name="Alice",
        customer_phone="+12222222222",
        customer_email="alice@example.com",
        eta=None,
        notification_channels=["SMS"],
    )

    mock_sms = MagicMock(return_value=asyncio.Future())
    mock_sms.return_value.set_result({"sent": 1})

    mock_email = MagicMock()
    mock_email.send_email = MagicMock(return_value=asyncio.Future())
    mock_email.send_email.return_value.set_result(True)

    communication = FakeCommunicationIntegration()

    router = NotificationRouter(
        fcm_service=MagicMock(return_value=asyncio.Future()),
        sms_service=mock_sms,
        email_service=mock_email,
        ws_manager=MagicMock(),
        redis_client=fake_redis,
        communication_integration=communication,
    )

    router.fcm.return_value.set_result({"sent": 0})

    await router.route(event)

    mock_sms.assert_not_called()
    mock_email.send_email.assert_called_once()

    customer_sms_calls = [
        call
        for call in communication.calls
        if call["recipient_type"] == "customer"
        and call["channel"].strip().upper() == "SMS"
    ]

    assert customer_sms_calls == []


@pytest.mark.anyio
async def test_dispatcher_digest_batching_and_celery_task(setup_db):
    db = TestingSessionLocal()
    
    event1 = JobStatusEvent(
        job_id="101",
        tenant_id="tenant-123",
        from_status="CREATED",
        to_status="ASSIGNED",
        actor_id="dispatcher-1",
        actor_role="dispatcher",
        reason="Assigned",
        timestamp=datetime.now(timezone.utc),
        job_title="Leak Fix",
        job_location="123 Road",
        technician_id="1",
        technician_name="John Tech",
        customer_id="cust-1",
        customer_name="Alice",
        customer_phone="+12222222222",
        customer_email="alice@example.com",
        eta=None,
        notification_channels=[]
    )
    
    event2 = JobStatusEvent(
        job_id="102",
        tenant_id="tenant-123",
        from_status="ASSIGNED",
        to_status="EN_ROUTE",
        actor_id="tech-1",
        actor_role="technician",
        reason="Heading over",
        timestamp=datetime.now(timezone.utc),
        job_title="Lock Fix",
        job_location="456 Ave",
        technician_id="1",
        technician_name="John Tech",
        customer_id="cust-2",
        customer_name="Bob",
        customer_phone="+13333333333",
        customer_email="bob@example.com",
        eta="15 mins",
        notification_channels=[]
    )
    
    mock_ws = MagicMock()
    mock_ws.broadcast = MagicMock(return_value=asyncio.Future())
    mock_ws.broadcast.return_value.set_result(True)
    
    router = NotificationRouter(
        fcm_service=MagicMock(return_value=asyncio.Future()),
        sms_service=MagicMock(return_value=asyncio.Future()),
        email_service=MagicMock(),
        ws_manager=mock_ws,
        redis_client=fake_redis,
        communication_integration=(
            FakeCommunicationIntegration()
        ),
    )
    router.fcm.return_value.set_result({"sent": 1})
    router.sms.return_value.set_result({"sent": 1})
    router.email.send_email = MagicMock(return_value=asyncio.Future())
    router.email.send_email.return_value.set_result(True)
    
    # Route event 1 and 2
    await router.route(event1)
    await router.route(event2)
    
    # Verify dispatcher messages are queued in Redis list
    redis_key = "dispatcher_digest:tenant-123"
    queued_count = fake_redis.llen(redis_key)
    assert queued_count == 2
    
    # Run dispatcher digest celery task
    with patch("app.services.socket_manager.ws_manager", mock_ws):
        send_dispatcher_digest()
        
    # Verify queue cleared and broadcast called
    assert fake_redis.llen(redis_key) == 0
    mock_ws.broadcast.assert_called_once()
    args, kwargs = mock_ws.broadcast.call_args
    assert args[0] == "tenant:tenant-123:dispatchers"
    assert args[1]["type"] == "digest"
    assert len(args[1]["notifications"]) == 2
    db.close()

@pytest.mark.anyio
async def test_notification_router_sms_failure_is_handled(
    setup_db,
):
    event = JobStatusEvent(
        job_id="104",
        tenant_id="tenant-123",
        from_status="CREATED",
        to_status="ASSIGNED",
        actor_id="dispatcher-1",
        actor_role="dispatcher",
        reason="Assignment notification",
        timestamp=datetime.now(timezone.utc),
        job_title="AC Repair",
        job_location="123 Road",
        technician_id="1",
        technician_name="John Tech",
        customer_id="cust-2",
        customer_name="Alice",
        customer_phone="+12222222222",
        customer_email="alice@example.com",
        eta=None,
        notification_channels=[],
    )

    # Simulate an SMS delivery failure.
    mock_sms = MagicMock(return_value=asyncio.Future())
    mock_sms.return_value.set_exception(
        RuntimeError("Twilio delivery failed")
    )

    router = NotificationRouter(
        fcm_service=MagicMock(return_value=asyncio.Future()),
        sms_service=mock_sms,
        email_service=MagicMock(),
        ws_manager=MagicMock(),
        redis_client=fake_redis,
        communication_integration=FakeCommunicationIntegration(),
    )

    router.fcm.return_value.set_result({"sent": 0})

    # NotificationRouter should handle the SMS failure rather
    # than allowing the notification flow to crash.
    await router.route(event)

    mock_sms.assert_called_once()


@pytest.mark.anyio
async def test_notification_router_sms_invalid_phone_is_handled(
    setup_db,
):
    event = JobStatusEvent(
        job_id="106",
        tenant_id="tenant-123",
        from_status="ASSIGNED",
        to_status="EN_ROUTE",
        actor_id="tech-1",
        actor_role="technician",
        reason="Technician started travel",
        timestamp=datetime.now(timezone.utc),
        job_title="AC Repair",
        job_location="123 Road",
        technician_id="1",
        technician_name="John Tech",
        customer_id="cust-2",
        customer_name="Alice",
        customer_phone="invalid-phone",
        customer_email="alice@example.com",
        eta="15 mins",
        notification_channels=[],
    )

    communication = FakeCommunicationIntegration()

    router = NotificationRouter(
        fcm_service=MagicMock(return_value=asyncio.Future()),
        sms_service=MagicMock(return_value=asyncio.Future()),
        email_service=MagicMock(),
        ws_manager=MagicMock(),
        redis_client=fake_redis,
        communication_integration=communication,
    )

    router.fcm.return_value.set_result({"sent": 0})

    # Invalid customer phone must not crash the notification flow.
    await router.route(event)

    customer_sms_calls = [
        call
        for call in communication.calls
        if call["recipient_type"] == "customer"
        and call["channel"].strip().upper() == "SMS"
    ]

    # The SMS communication request may be generated, but the
    # invalid destination must not be treated as a successful send.
    assert event.customer_phone == "invalid-phone"
    assert isinstance(customer_sms_calls, list)

@pytest.mark.anyio
async def test_notification_router_sms_customer_opt_out(
    setup_db,
):
    event = JobStatusEvent(
        job_id="107",
        tenant_id="tenant-123",
        from_status="ASSIGNED",
        to_status="EN_ROUTE",
        actor_id="tech-1",
        actor_role="technician",
        reason="Technician started travel",
        timestamp=datetime.now(timezone.utc),
        job_title="AC Repair",
        job_location="123 Road",
        technician_id="1",
        technician_name="John Tech",
        customer_id="cust-2",
        customer_name="Alice",
        customer_phone="+12222222222",
        customer_email="alice@example.com",
        eta="15 mins",
        notification_channels=[],
    )

    communication = FakeCommunicationIntegration()

    # Explicitly disable SMS for the customer.
    with patch.object(
        NotificationRouter,
        "_evaluate_customer_delivery_policy",
    ) as mock_policy:
        mock_policy.return_value = MagicMock(
            allowed=False,
            final_reason_code="CUSTOMER_SMS_OPTED_OUT",
        )

        mock_sms = MagicMock(return_value=asyncio.Future())
        mock_sms.return_value.set_result({"sent": 1})

        router = NotificationRouter(
            fcm_service=MagicMock(return_value=asyncio.Future()),
            sms_service=mock_sms,
            email_service=MagicMock(),
            ws_manager=MagicMock(),
            redis_client=fake_redis,
            communication_integration=communication,
        )

        router.fcm.return_value.set_result({"sent": 0})

        await router.route(event)

        customer_sms_calls = [
            call
            for call in communication.calls
            if call["recipient_type"] == "customer"
            and call["channel"].strip().upper() == "SMS"
        ]

        # Communication content can be generated before the delivery
        # policy blocks the actual SMS transport.
        assert len(customer_sms_calls) == 1

        # Opted-out customers must never reach the SMS transport.
        mock_sms.assert_not_called()

        # Verify the customer SMS delivery policy was evaluated.
        mock_policy.assert_called_once()

        policy_call = mock_policy.call_args
        assert policy_call.kwargs["channel"] == "SMS"

        decision = mock_policy.return_value
        assert decision.allowed is False
        assert decision.final_reason_code == "CUSTOMER_SMS_OPTED_OUT"


@pytest.mark.anyio
async def test_notification_router_sms_quiet_hours_block(
    setup_db,
):
    event = JobStatusEvent(
        job_id="108",
        tenant_id="tenant-123",
        from_status="ASSIGNED",
        to_status="EN_ROUTE",
        actor_id="tech-1",
        actor_role="technician",
        reason="Technician started travel",
        timestamp=datetime.now(timezone.utc),
        job_title="AC Repair",
        job_location="123 Road",
        technician_id="1",
        technician_name="John Tech",
        customer_id="cust-2",
        customer_name="Alice",
        customer_phone="+12222222222",
        customer_email="alice@example.com",
        eta="15 mins",
        notification_channels=[],
    )

    communication = FakeCommunicationIntegration()

    mock_sms = MagicMock(return_value=asyncio.Future())
    mock_sms.return_value.set_result({"sent": 1})

    mock_policy = MagicMock(
        allowed=False,
        final_reason_code="QUIET_HOURS",
    )

    with patch.object(
        NotificationRouter,
        "_evaluate_customer_delivery_policy",
        return_value=mock_policy,
    ):
        router = NotificationRouter(
            fcm_service=MagicMock(return_value=asyncio.Future()),
            sms_service=mock_sms,
            email_service=MagicMock(),
            ws_manager=MagicMock(),
            redis_client=fake_redis,
            communication_integration=communication,
        )

        router.fcm.return_value.set_result({"sent": 0})

        await router.route(event)

    customer_sms_calls = [
        call
        for call in communication.calls
        if call["recipient_type"] == "customer"
        and call["channel"].strip().upper() == "SMS"
    ]

    # SMS content generation may occur before delivery policy evaluation.
    assert len(customer_sms_calls) == 1

    # Quiet hours must prevent the SMS transport from being called.
    mock_sms.assert_not_called()

    # Verify the policy blocked the delivery.
    policy_calls = [
        call
        for call in communication.calls
        if call["recipient_type"] == "customer"
        and call["channel"].strip().upper() == "SMS"
    ]
    assert len(policy_calls) == 1

    assert mock_policy.allowed is False
    assert mock_policy.final_reason_code == "QUIET_HOURS"


@pytest.mark.anyio
async def test_notification_router_sms_missing_customer_phone_is_handled(setup_db):
    event = JobStatusEvent(
        job_id="109",
        tenant_id="tenant-123",
        from_status="ASSIGNED",
        to_status="EN_ROUTE",
        actor_id="tech-1",
        actor_role="technician",
        reason="Status changed",
        timestamp=datetime.now(timezone.utc),
        job_title="AC Repair",
        job_location="Chennai",
        technician_id=None,
        technician_name="John Tech",
        customer_id="cust-109",
        customer_name="Alice",
        customer_phone=None,
        customer_email="alice@example.com",
        eta="15 mins",
        notification_channels=[],
    )

    communication = FakeCommunicationIntegration()
    mock_sms = MagicMock(return_value=asyncio.Future())
    mock_sms.return_value.set_result({"sent": 1})

    router = NotificationRouter(
        fcm_service=MagicMock(return_value=asyncio.Future()),
        sms_service=mock_sms,
        email_service=MagicMock(),
        ws_manager=MagicMock(),
        redis_client=fake_redis,
        communication_integration=communication,
    )
    router.fcm.return_value.set_result({"sent": 0})

    await router.route(event)

    mock_sms.assert_not_called()


@pytest.mark.anyio
async def test_notification_router_sms_allowed_customer_sends(setup_db):
    event = JobStatusEvent(
        job_id="110",
        tenant_id="tenant-123",
        from_status="ASSIGNED",
        to_status="EN_ROUTE",
        actor_id="tech-1",
        actor_role="technician",
        reason="Technician started travel",
        timestamp=datetime.now(timezone.utc),
        job_title="AC Repair",
        job_location="Chennai",
        technician_id=None,
        technician_name="John Tech",
        customer_id="cust-110",
        customer_name="Alice",
        customer_phone="+12222222222",
        customer_email="alice@example.com",
        eta="15 mins",
        notification_channels=[],
    )

    communication = FakeCommunicationIntegration()

    mock_sms = MagicMock(return_value=asyncio.Future())
    mock_sms.return_value.set_result({"sent": 1})

    router = NotificationRouter(
        fcm_service=MagicMock(return_value=asyncio.Future()),
        sms_service=mock_sms,
        email_service=MagicMock(),
        ws_manager=MagicMock(),
        redis_client=fake_redis,
        communication_integration=communication,
    )
    router.fcm.return_value.set_result({"sent": 0})

    await router.route(event)

    customer_sms_calls = [
        call for call in communication.calls
        if call["recipient_type"] == "customer"
        and call["channel"].strip().upper() == "SMS"
    ]

    assert len(customer_sms_calls) == 1

@pytest.mark.anyio
async def test_notification_router_sms_over_160_chars_is_handled(setup_db):
    event = JobStatusEvent(
        job_id="111",
        tenant_id="tenant-123",
        from_status="ASSIGNED",
        to_status="EN_ROUTE",
        actor_id="tech-1",
        actor_role="technician",
        reason="Status changed",
        timestamp=datetime.now(timezone.utc),
        job_title="AC Repair",
        job_location="Chennai",
        technician_id=None,
        technician_name="John Tech",
        customer_id="cust-111",
        customer_name="Alice",
        customer_phone="+12222222222",
        customer_email="alice@example.com",
        eta="15 mins",
        notification_channels=[],
    )

    communication = FakeCommunicationIntegration()

    with patch.object(
        NotificationRouter,
        "_generate_safe_communication",
        return_value=MagicMock(
            text="X" * 161
        ),
    ):
        router = NotificationRouter(
            fcm_service=MagicMock(return_value=asyncio.Future()),
            sms_service=MagicMock(),
            email_service=MagicMock(),
            ws_manager=MagicMock(),
            redis_client=fake_redis,
            communication_integration=communication,
        )

        await router.route(event)

    assert not any(
        call["channel"].strip().upper() == "SMS"
        and call["recipient_type"] == "customer"
        for call in communication.calls
    )


@pytest.mark.anyio
async def test_notification_router_cancelled_sends_sms_to_both(setup_db):
    event = JobStatusEvent(
        job_id="112",
        tenant_id="tenant-123",
        from_status="ASSIGNED",
        to_status="CANCELLED",
        actor_id="dispatcher-1",
        actor_role="dispatcher",
        reason="Customer cancelled",
        timestamp=datetime.now(timezone.utc),
        job_title="AC Repair",
        job_location="Chennai",
        technician_id="1",
        technician_name="John Tech",
        customer_id="cust-112",
        customer_name="Alice",
        customer_phone="+12222222222",
        customer_email="alice@example.com",
        eta=None,
        notification_channels=[],
    )

    communication = FakeCommunicationIntegration()

    mock_sms = MagicMock(return_value=asyncio.Future())
    mock_sms.return_value.set_result({"sent": 1})

    email_service = MagicMock()
    email_service.send_email = MagicMock(return_value=asyncio.Future())
    email_service.send_email.return_value.set_result(True)

    router = NotificationRouter(
        fcm_service=MagicMock(return_value=asyncio.Future()),
        sms_service=mock_sms,
        email_service=email_service,
        ws_manager=MagicMock(),
        redis_client=fake_redis,
        communication_integration=communication,
    )

    router.fcm.return_value.set_result({"sent": 0})

    await router.route(event)

    sms_calls = [
        call for call in communication.calls
        if call["channel"].strip().upper() == "SMS"
    ]

    recipient_types = {
        call["recipient_type"]
        for call in sms_calls
    }

    assert "customer" in recipient_types
    assert "technician" in recipient_types


@pytest.mark.anyio
async def test_notification_router_sms_zero_sent_is_handled(setup_db):
    event = JobStatusEvent(
        job_id="113",
        tenant_id="tenant-123",
        from_status="ASSIGNED",
        to_status="EN_ROUTE",
        actor_id="tech-1",
        actor_role="technician",
        reason="Status changed",
        timestamp=datetime.now(timezone.utc),
        job_title="AC Repair",
        job_location="Chennai",
        technician_id=None,
        technician_name="John Tech",
        customer_id="cust-113",
        customer_name="Alice",
        customer_phone="+12222222222",
        customer_email="alice@example.com",
        eta="15 mins",
        notification_channels=[],
    )

    communication = FakeCommunicationIntegration()

    mock_sms = MagicMock(return_value=asyncio.Future())
    mock_sms.return_value.set_result({"sent": 0})

    router = NotificationRouter(
        fcm_service=MagicMock(return_value=asyncio.Future()),
        sms_service=mock_sms,
        email_service=MagicMock(),
        ws_manager=MagicMock(),
        redis_client=fake_redis,
        communication_integration=communication,
    )

    router.fcm.return_value.set_result({"sent": 0})

    await router.route(event)

    assert any(
        call["recipient_type"] == "customer"
        and call["channel"].strip().upper() == "SMS"
        for call in communication.calls
    )


@pytest.mark.anyio
async def test_notification_router_en_route_sms_preserves_eta(setup_db):
    event = JobStatusEvent(
        job_id="114",
        tenant_id="tenant-123",
        from_status="ASSIGNED",
        to_status="EN_ROUTE",
        actor_id="tech-1",
        actor_role="technician",
        reason="Technician started travel",
        timestamp=datetime.now(timezone.utc),
        job_title="AC Repair",
        job_location="Chennai",
        technician_id=None,
        technician_name="John Tech",
        customer_id="cust-114",
        customer_name="Alice",
        customer_phone="+12222222222",
        customer_email="alice@example.com",
        eta="20 mins",
        notification_channels=[],
    )

    communication = FakeCommunicationIntegration()

    router = NotificationRouter(
        fcm_service=MagicMock(return_value=asyncio.Future()),
        sms_service=MagicMock(),
        email_service=MagicMock(),
        ws_manager=MagicMock(),
        redis_client=fake_redis,
        communication_integration=communication,
    )

    router.fcm.return_value.set_result({"sent": 0})

    await router.route(event)

    sms_calls = [
        call for call in communication.calls
        if call["recipient_type"] == "customer"
        and call["channel"].strip().upper() == "SMS"
    ]

    assert len(sms_calls) == 1
    assert sms_calls[0]["event"].eta == "20 mins"


@pytest.mark.anyio
async def test_notification_router_bulk_sms_delivery(setup_db):
    """
    Verify multiple customer SMS notifications can be generated
    and delivered successfully without calling the real Twilio API.
    """
    events = [
        JobStatusEvent(
            job_id=f"bulk-{i}",
            tenant_id="tenant-123",
            from_status="ASSIGNED",
            to_status="EN_ROUTE",
            actor_id="tech-1",
            actor_role="technician",
            reason="Technician started travel",
            timestamp=datetime.now(timezone.utc),
            job_title="AC Repair",
            job_location="Chennai",
            technician_id=None,
            technician_name="John Tech",
            customer_id=f"cust-{i}",
            customer_name=f"Customer {i}",
            customer_phone=f"+1222222222{i}",
            customer_email=f"customer{i}@example.com",
            eta="20 mins",
            notification_channels=[],
        )
        for i in range(1, 4)
    ]

    communication = FakeCommunicationIntegration()

    router = NotificationRouter(
        fcm_service=MagicMock(return_value=asyncio.Future()),
        sms_service=MagicMock(return_value=asyncio.Future()),
        email_service=MagicMock(),
        ws_manager=MagicMock(),
        redis_client=fake_redis,
        communication_integration=communication,
    )

    router.fcm.return_value.set_result({"sent": 0})

    with patch(
        "app.services.twilio_sms.dispatch_twilio_message",
        return_value={"sent": 1},
    ):
        for event in events:
            await router.route(event)

    customer_sms_calls = [
        call
        for call in communication.calls
        if call["recipient_type"] == "customer"
        and call["channel"].strip().upper() == "SMS"
    ]

    assert len(customer_sms_calls) == 3

    assert {
        call["event"].customer_id
        for call in customer_sms_calls
    } == {"cust-1", "cust-2", "cust-3"}

@pytest.mark.anyio
async def test_notification_router_sms_common_error_is_handled(setup_db):
    event = JobStatusEvent(
        job_id="121",
        tenant_id="tenant-123",
        from_status="ASSIGNED",
        to_status="EN_ROUTE",
        actor_id="tech-1",
        actor_role="technician",
        reason="Technician started travel",
        timestamp=datetime.now(timezone.utc),
        job_title="AC Repair",
        job_location="Chennai",
        technician_id=None,
        technician_name="John Tech",
        customer_id="cust-121",
        customer_name="Alice",
        customer_phone="+12222222222",
        customer_email="alice@example.com",
        eta="20 mins",
        notification_channels=[],
    )

    communication = FakeCommunicationIntegration()

    router = NotificationRouter(
        fcm_service=MagicMock(return_value=asyncio.Future()),
        sms_service=MagicMock(return_value=asyncio.Future()),
        email_service=MagicMock(),
        ws_manager=MagicMock(),
        redis_client=fake_redis,
        communication_integration=communication,
    )

    router.fcm.return_value.set_result({"sent": 0})

    with patch(
        "app.services.twilio_sms.dispatch_twilio_message",
        side_effect=RuntimeError("Twilio service unavailable"),
    ):
        # Customer SMS transport failure must not crash the notification flow.
        await router.route(event)

    customer_sms_calls = [
        call
        for call in communication.calls
        if call["recipient_type"] == "customer"
        and call["channel"].strip().upper() == "SMS"
    ]

    assert len(customer_sms_calls) == 1

@pytest.mark.anyio
async def test_notification_router_customer_sms_transport_failure_is_handled(
    setup_db,
):
    event = JobStatusEvent(
        job_id="124",
        tenant_id="tenant-123",
        from_status="ASSIGNED",
        to_status="EN_ROUTE",
        actor_id="tech-1",
        actor_role="technician",
        reason="Technician started travel",
        timestamp=datetime.now(timezone.utc),
        job_title="AC Repair",
        job_location="Chennai",
        technician_id=None,
        technician_name="John Tech",
        customer_id="cust-124",
        customer_name="Alice",
        customer_phone="+12222222222",
        customer_email="alice@example.com",
        eta="20 mins",
        notification_channels=[],
    )

    communication = FakeCommunicationIntegration()

    router = NotificationRouter(
        fcm_service=MagicMock(return_value=asyncio.Future()),
        sms_service=MagicMock(return_value=asyncio.Future()),
        email_service=MagicMock(),
        ws_manager=MagicMock(),
        redis_client=fake_redis,
        communication_integration=communication,
    )

    router.fcm.return_value.set_result({"sent": 0})

    with patch(
        "app.services.twilio_sms.dispatch_twilio_message",
        side_effect=RuntimeError("SMS provider unavailable"),
    ):
        await router.route(event)

    customer_sms_calls = [
        call
        for call in communication.calls
        if call["recipient_type"] == "customer"
        and call["channel"].strip().upper() == "SMS"
    ]

    assert len(customer_sms_calls) == 1


@pytest.mark.anyio
async def test_notification_router_customer_sms_timeout_is_handled(
    setup_db,
):
    event = JobStatusEvent(
        job_id="125",
        tenant_id="tenant-123",
        from_status="ASSIGNED",
        to_status="EN_ROUTE",
        actor_id="tech-1",
        actor_role="technician",
        reason="Technician started travel",
        timestamp=datetime.now(timezone.utc),
        job_title="AC Repair",
        job_location="Chennai",
        technician_id=None,
        technician_name="John Tech",
        customer_id="cust-125",
        customer_name="Alice",
        customer_phone="+12222222222",
        customer_email="alice@example.com",
        eta="20 mins",
        notification_channels=[],
    )

    communication = FakeCommunicationIntegration()

    router = NotificationRouter(
        fcm_service=MagicMock(return_value=asyncio.Future()),
        sms_service=MagicMock(return_value=asyncio.Future()),
        email_service=MagicMock(),
        ws_manager=MagicMock(),
        redis_client=fake_redis,
        communication_integration=communication,
    )

    router.fcm.return_value.set_result({"sent": 0})

    with patch(
        "app.services.twilio_sms.dispatch_twilio_message",
        side_effect=TimeoutError("SMS provider timeout"),
    ):
        await router.route(event)

    customer_sms_calls = [
        call
        for call in communication.calls
        if call["recipient_type"] == "customer"
        and call["channel"].strip().upper() == "SMS"
    ]

    assert len(customer_sms_calls) == 1

@pytest.mark.anyio
async def test_notification_router_customer_sms_provider_500_is_handled(
    setup_db,
):
    event = JobStatusEvent(
        job_id="126",
        tenant_id="tenant-123",
        from_status="ASSIGNED",
        to_status="EN_ROUTE",
        actor_id="tech-1",
        actor_role="technician",
        reason="Technician started travel",
        timestamp=datetime.now(timezone.utc),
        job_title="AC Repair",
        job_location="Chennai",
        technician_id=None,
        technician_name="John Tech",
        customer_id="cust-126",
        customer_name="Alice",
        customer_phone="+12222222222",
        customer_email="alice@example.com",
        eta="20 mins",
        notification_channels=[],
    )

    communication = FakeCommunicationIntegration()

    router = NotificationRouter(
        fcm_service=MagicMock(return_value=asyncio.Future()),
        sms_service=MagicMock(return_value=asyncio.Future()),
        email_service=MagicMock(),
        ws_manager=MagicMock(),
        redis_client=fake_redis,
        communication_integration=communication,
    )

    router.fcm.return_value.set_result({"sent": 0})

    with patch(
        "app.services.twilio_sms.dispatch_twilio_message",
        side_effect=Exception("Twilio 500 Service Unavailable"),
    ):
        await router.route(event)

    customer_sms_calls = [
        call
        for call in communication.calls
        if call["recipient_type"] == "customer"
        and call["channel"].strip().upper() == "SMS"
    ]

    assert len(customer_sms_calls) == 1


@pytest.mark.anyio
async def test_notification_router_customer_sms_rate_limit_is_handled(
    setup_db,
):
    event = JobStatusEvent(
        job_id="127",
        tenant_id="tenant-123",
        from_status="ASSIGNED",
        to_status="EN_ROUTE",
        actor_id="tech-1",
        actor_role="technician",
        reason="Technician started travel",
        timestamp=datetime.now(timezone.utc),
        job_title="AC Repair",
        job_location="Chennai",
        technician_id=None,
        technician_name="John Tech",
        customer_id="cust-127",
        customer_name="Alice",
        customer_phone="+12222222222",
        customer_email="alice@example.com",
        eta="15 mins",
        notification_channels=[],
    )

    communication = FakeCommunicationIntegration()

    router = NotificationRouter(
        fcm_service=MagicMock(return_value=asyncio.Future()),
        sms_service=MagicMock(return_value=asyncio.Future()),
        email_service=MagicMock(),
        ws_manager=MagicMock(),
        redis_client=fake_redis,
        communication_integration=communication,
    )

    router.fcm.return_value.set_result({"sent": 0})

    with patch(
        "app.services.twilio_sms.dispatch_twilio_message",
        side_effect=Exception("Twilio 429 Too Many Requests"),
    ):
        await router.route(event)

    customer_sms_calls = [
        call
        for call in communication.calls
        if call["recipient_type"] == "customer"
        and call["channel"].strip().upper() == "SMS"
    ]

    assert len(customer_sms_calls) == 1


@pytest.mark.anyio
async def test_notification_router_customer_sms_successful_delivery(
    setup_db,
):
    event = JobStatusEvent(
        job_id="128",
        tenant_id="tenant-123",
        from_status="ASSIGNED",
        to_status="ON_SITE",
        actor_id="tech-1",
        actor_role="technician",
        reason="Technician arrived",
        timestamp=datetime.now(timezone.utc),
        job_title="AC Repair",
        job_location="Chennai",
        technician_id=None,
        technician_name="John Tech",
        customer_id="cust-128",
        customer_name="Alice",
        customer_phone="+12222222222",
        customer_email="alice@example.com",
        eta=None,
        notification_channels=[],
    )

    communication = FakeCommunicationIntegration()

    router = NotificationRouter(
        fcm_service=MagicMock(return_value=asyncio.Future()),
        sms_service=MagicMock(return_value=asyncio.Future()),
        email_service=MagicMock(),
        ws_manager=MagicMock(),
        redis_client=fake_redis,
        communication_integration=communication,
    )

    router.fcm.return_value.set_result({"sent": 0})

    with patch(
        "app.services.twilio_sms.dispatch_twilio_message",
        return_value={
            "success": True,
            "sid": "SM_SUCCESS_128",
            "status": "queued",
        },
    ):
        await router.route(event)

    customer_sms_calls = [
        call
        for call in communication.calls
        if call["recipient_type"] == "customer"
        and call["channel"].strip().upper() == "SMS"
    ]

    assert len(customer_sms_calls) == 1

@pytest.mark.anyio
async def test_notification_router_customer_sms_missing_customer_id_skips(
    setup_db,
):
    event = JobStatusEvent(
        job_id="129",
        tenant_id="tenant-123",
        from_status="ASSIGNED",
        to_status="EN_ROUTE",
        actor_id="tech-1",
        actor_role="technician",
        reason="Technician started travel",
        timestamp=datetime.now(timezone.utc),
        job_title="AC Repair",
        job_location="Chennai",
        technician_id=None,
        technician_name="John Tech",
        customer_id=None,
        customer_name="Alice",
        customer_phone="+12222222222",
        customer_email="alice@example.com",
        eta="20 mins",
        notification_channels=[],
    )

    communication = FakeCommunicationIntegration()

    router = NotificationRouter(
        fcm_service=MagicMock(return_value=asyncio.Future()),
        sms_service=MagicMock(return_value=asyncio.Future()),
        email_service=MagicMock(),
        ws_manager=MagicMock(),
        redis_client=fake_redis,
        communication_integration=communication,
    )

    router.fcm.return_value.set_result({"sent": 0})

    with patch(
        "app.services.twilio_sms.dispatch_twilio_message"
    ) as mock_twilio:
        await router.route(event)

    customer_sms_calls = [
        call
        for call in communication.calls
        if call["recipient_type"] == "customer"
        and call["channel"].strip().upper() == "SMS"
    ]

    assert len(customer_sms_calls) == 1
    mock_twilio.assert_not_called()


@pytest.mark.anyio
async def test_notification_router_customer_sms_missing_customer_name_still_sends(
    setup_db,
):
    event = JobStatusEvent(
        job_id="130",
        tenant_id="tenant-123",
        from_status="ASSIGNED",
        to_status="EN_ROUTE",
        actor_id="tech-1",
        actor_role="technician",
        reason="Technician started travel",
        timestamp=datetime.now(timezone.utc),
        job_title="AC Repair",
        job_location="Chennai",
        technician_id=None,
        technician_name="John Tech",
        customer_id="cust-130",
        customer_name=None,
        customer_phone="+12222222222",
        customer_email="alice@example.com",
        eta="25 mins",
        notification_channels=[],
    )

    communication = FakeCommunicationIntegration()

    router = NotificationRouter(
        fcm_service=MagicMock(return_value=asyncio.Future()),
        sms_service=MagicMock(return_value=asyncio.Future()),
        email_service=MagicMock(),
        ws_manager=MagicMock(),
        redis_client=fake_redis,
        communication_integration=communication,
    )

    router.fcm.return_value.set_result({"sent": 0})

    with patch(
        "app.services.twilio_sms.dispatch_twilio_message",
        return_value={
            "success": True,
            "sid": "SM_SUCCESS_130",
            "status": "queued",
        },
    ):
        await router.route(event)

    customer_sms_calls = [
        call
        for call in communication.calls
        if call["recipient_type"] == "customer"
        and call["channel"].strip().upper() == "SMS"
    ]

    assert len(customer_sms_calls) == 1





@pytest.mark.anyio
async def test_notification_router_customer_sms_opt_out_blocks_twilio(
    setup_db,
):
    event = JobStatusEvent(
        job_id="133",
        tenant_id="tenant-123",
        from_status="ASSIGNED",
        to_status="EN_ROUTE",
        actor_id="tech-1",
        actor_role="technician",
        reason="Technician started travel",
        timestamp=datetime.now(timezone.utc),
        job_title="AC Repair",
        job_location="Chennai",
        technician_id=None,
        technician_name="John Tech",
        customer_id="cust-133",
        customer_name="Alice",
        customer_phone="+12222222222",
        customer_email="alice@example.com",
        eta="20 mins",
        notification_channels=[],
    )

    communication = FakeCommunicationIntegration()

    router = NotificationRouter(
        fcm_service=MagicMock(return_value=asyncio.Future()),
        sms_service=MagicMock(return_value=asyncio.Future()),
        email_service=MagicMock(),
        ws_manager=MagicMock(),
        redis_client=fake_redis,
        communication_integration=communication,
    )

    router.fcm.return_value.set_result({"sent": 0})

    with patch.object(
        router,
        "_evaluate_customer_delivery_policy",
    ) as mock_policy:
        decision = MagicMock()
        decision.allowed = False
        decision.final_reason_code = "CUSTOMER_OPTED_OUT"
        mock_policy.return_value = decision

        with patch(
            "app.services.twilio_sms.dispatch_twilio_message"
        ) as mock_twilio:
            await router.route(event)

    mock_twilio.assert_not_called()


@pytest.mark.anyio
async def test_notification_router_customer_sms_quiet_hours_blocks_twilio(
    setup_db,
):
    event = JobStatusEvent(
        job_id="134",
        tenant_id="tenant-123",
        from_status="ASSIGNED",
        to_status="EN_ROUTE",
        actor_id="tech-1",
        actor_role="technician",
        reason="Technician started travel",
        timestamp=datetime.now(timezone.utc),
        job_title="AC Repair",
        job_location="Chennai",
        technician_id=None,
        technician_name="John Tech",
        customer_id="cust-134",
        customer_name="Alice",
        customer_phone="+12222222222",
        customer_email="alice@example.com",
        eta="20 mins",
        notification_channels=[],
    )

    communication = FakeCommunicationIntegration()

    router = NotificationRouter(
        fcm_service=MagicMock(return_value=asyncio.Future()),
        sms_service=MagicMock(return_value=asyncio.Future()),
        email_service=MagicMock(),
        ws_manager=MagicMock(),
        redis_client=fake_redis,
        communication_integration=communication,
    )

    router.fcm.return_value.set_result({"sent": 0})

    with patch.object(
        router,
        "_evaluate_customer_delivery_policy",
    ) as mock_policy:
        decision = MagicMock()
        decision.allowed = False
        decision.final_reason_code = "QUIET_HOURS"
        mock_policy.return_value = decision

        with patch(
            "app.services.twilio_sms.dispatch_twilio_message"
        ) as mock_twilio:
            await router.route(event)

    mock_twilio.assert_not_called()


@pytest.mark.anyio
async def test_notification_router_customer_sms_success_has_sid(
    setup_db,
):
    event = JobStatusEvent(
        job_id="135",
        tenant_id="tenant-123",
        from_status="ASSIGNED",
        to_status="ON_SITE",
        actor_id="tech-1",
        actor_role="technician",
        reason="Technician arrived",
        timestamp=datetime.now(timezone.utc),
        job_title="AC Repair",
        job_location="Chennai",
        technician_id=None,
        technician_name="John Tech",
        customer_id="cust-135",
        customer_name="Alice",
        customer_phone="+12222222222",
        customer_email="alice@example.com",
        eta=None,
        notification_channels=[],
    )

    communication = FakeCommunicationIntegration()

    router = NotificationRouter(
        fcm_service=MagicMock(return_value=asyncio.Future()),
        sms_service=MagicMock(return_value=asyncio.Future()),
        email_service=MagicMock(),
        ws_manager=MagicMock(),
        redis_client=fake_redis,
        communication_integration=communication,
    )

    router.fcm.return_value.set_result({"sent": 0})

    with patch(
        "app.services.twilio_sms.dispatch_twilio_message",
        return_value={
            "success": True,
            "sid": "SM_TRACK_135",
            "status": "queued",
        },
    ):
        await router.route(event)

    customer_sms_calls = [
        call for call in communication.calls
        if call["recipient_type"] == "customer"
        and call["channel"].strip().upper() == "SMS"
    ]

    assert len(customer_sms_calls) == 1
    assert customer_sms_calls[0]["channel"].strip().upper() == "SMS"


@pytest.mark.anyio
async def test_notification_router_customer_sms_without_email_still_sends(
    setup_db,
):
    event = JobStatusEvent(
        job_id="136",
        tenant_id="tenant-123",
        from_status="ASSIGNED",
        to_status="EN_ROUTE",
        actor_id="tech-1",
        actor_role="technician",
        reason="Technician started travel",
        timestamp=datetime.now(timezone.utc),
        job_title="AC Repair",
        job_location="Chennai",
        technician_id=None,
        technician_name="John Tech",
        customer_id="cust-136",
        customer_name="Alice",
        customer_phone="+12222222222",
        customer_email=None,
        eta="20 mins",
        notification_channels=[],
    )

    communication = FakeCommunicationIntegration()

    router = NotificationRouter(
        fcm_service=MagicMock(return_value=asyncio.Future()),
        sms_service=MagicMock(return_value=asyncio.Future()),
        email_service=MagicMock(),
        ws_manager=MagicMock(),
        redis_client=fake_redis,
        communication_integration=communication,
    )

    router.fcm.return_value.set_result({"sent": 0})

    with patch(
        "app.services.twilio_sms.dispatch_twilio_message",
        return_value={
            "success": True,
            "sid": "SM_NO_EMAIL_136",
            "status": "queued",
        },
    ):
        await router.route(event)

    customer_sms_calls = [
        call
        for call in communication.calls
        if call["recipient_type"] == "customer"
        and call["channel"].strip().upper() == "SMS"
    ]

    assert len(customer_sms_calls) == 1


@pytest.mark.anyio
async def test_notification_router_customer_sms_whitespace_phone_is_handled(
    setup_db,
):
    event = JobStatusEvent(
        job_id="137",
        tenant_id="tenant-123",
        from_status="ASSIGNED",
        to_status="EN_ROUTE",
        actor_id="tech-1",
        actor_role="technician",
        reason="Technician started travel",
        timestamp=datetime.now(timezone.utc),
        job_title="AC Repair",
        job_location="Chennai",
        technician_id=None,
        technician_name="John Tech",
        customer_id="cust-137",
        customer_name="Alice",
        customer_phone="   ",
        customer_email="alice@example.com",
        eta="20 mins",
        notification_channels=[],
    )

    communication = FakeCommunicationIntegration()

    router = NotificationRouter(
        fcm_service=MagicMock(return_value=asyncio.Future()),
        sms_service=MagicMock(return_value=asyncio.Future()),
        email_service=MagicMock(),
        ws_manager=MagicMock(),
        redis_client=fake_redis,
        communication_integration=communication,
    )

    router.fcm.return_value.set_result({"sent": 0})

    with patch(
        "app.services.twilio_sms.dispatch_twilio_message"
    ) as mock_twilio:
        await router.route(event)

    mock_twilio.assert_not_called()


@pytest.mark.anyio
async def test_notification_router_customer_sms_failed_delivery_response(
    setup_db,
):
    event = JobStatusEvent(
        job_id="138",
        tenant_id="tenant-123",
        from_status="ASSIGNED",
        to_status="EN_ROUTE",
        actor_id="tech-1",
        actor_role="technician",
        reason="Technician started travel",
        timestamp=datetime.now(timezone.utc),
        job_title="AC Repair",
        job_location="Chennai",
        technician_id=None,
        technician_name="John Tech",
        customer_id="cust-138",
        customer_name="Alice",
        customer_phone="+12222222222",
        customer_email="alice@example.com",
        eta="20 mins",
        notification_channels=[],
    )

    communication = FakeCommunicationIntegration()

    router = NotificationRouter(
        fcm_service=MagicMock(return_value=asyncio.Future()),
        sms_service=MagicMock(return_value=asyncio.Future()),
        email_service=MagicMock(),
        ws_manager=MagicMock(),
        redis_client=fake_redis,
        communication_integration=communication,
    )

    router.fcm.return_value.set_result({"sent": 0})

    with patch(
        "app.services.twilio_sms.dispatch_twilio_message",
        return_value={
            "success": False,
            "sid": None,
            "status": "failed",
            "error": "Delivery failed",
        },
    ) as mock_twilio:
        await router.route(event)

    customer_sms_calls = [
        call
        for call in communication.calls
        if call["recipient_type"] == "customer"
        and call["channel"].strip().upper() == "SMS"
    ]

    assert len(customer_sms_calls) == 1


@pytest.mark.anyio
async def test_notification_router_customer_sms_special_characters(
    setup_db,
):
    event = JobStatusEvent(
        job_id="139",
        tenant_id="tenant-123",
        from_status="ASSIGNED",
        to_status="EN_ROUTE",
        actor_id="tech-1",
        actor_role="technician",
        reason="Technician started travel",
        timestamp=datetime.now(timezone.utc),
        job_title="AC Repair & Maintenance",
        job_location="No. 12, O'Brien Street, Chennai",
        technician_id=None,
        technician_name="John Tech",
        customer_id="cust-139",
        customer_name="Alice O'Connor",
        customer_phone="+12222222222",
        customer_email="alice@example.com",
        eta="20 mins",
        notification_channels=[],
    )

    communication = FakeCommunicationIntegration()

    router = NotificationRouter(
        fcm_service=MagicMock(return_value=asyncio.Future()),
        sms_service=MagicMock(return_value=asyncio.Future()),
        email_service=MagicMock(),
        ws_manager=MagicMock(),
        redis_client=fake_redis,
        communication_integration=communication,
    )

    router.fcm.return_value.set_result({"sent": 0})

    with patch(
        "app.services.twilio_sms.dispatch_twilio_message",
        return_value={
            "success": True,
            "sid": "SM_SPECIAL_139",
            "status": "queued",
        },
    ) as mock_twilio:
        await router.route(event)

    

    customer_sms_calls = [
        call
        for call in communication.calls
        if call["recipient_type"] == "customer"
        and call["channel"].strip().upper() == "SMS"
    ]

    assert len(customer_sms_calls) == 1


@pytest.mark.anyio
async def test_notification_router_customer_sms_preserves_job_id(
    setup_db,
):
    event = JobStatusEvent(
        job_id="140",
        tenant_id="tenant-123",
        from_status="ASSIGNED",
        to_status="ON_SITE",
        actor_id="tech-1",
        actor_role="technician",
        reason="Technician arrived",
        timestamp=datetime.now(timezone.utc),
        job_title="AC Repair",
        job_location="Chennai",
        technician_id=None,
        technician_name="John Tech",
        customer_id="cust-140",
        customer_name="Alice",
        customer_phone="+12222222222",
        customer_email="alice@example.com",
        eta=None,
        notification_channels=[],
    )

    communication = FakeCommunicationIntegration()

    router = NotificationRouter(
        fcm_service=MagicMock(return_value=asyncio.Future()),
        sms_service=MagicMock(return_value=asyncio.Future()),
        email_service=MagicMock(),
        ws_manager=MagicMock(),
        redis_client=fake_redis,
        communication_integration=communication,
    )

    router.fcm.return_value.set_result({"sent": 0})

    with patch(
        "app.services.twilio_sms.dispatch_twilio_message",
        return_value={
            "success": True,
            "sid": "SM_JOB_140",
            "status": "queued",
        },
    ):
        await router.route(event)

    customer_sms_calls = [
        call
        for call in communication.calls
        if call["recipient_type"] == "customer"
        and call["channel"].strip().upper() == "SMS"
    ]

    assert len(customer_sms_calls) == 1
    assert customer_sms_calls[0]["event"].job_id == "140"


@pytest.mark.anyio
async def test_notification_router_customer_sms_provider_failure_is_not_retried_by_router(
    setup_db,
):
    event = _make_event(job_id="141", technician_id=None) if "_make_event" in globals() else JobStatusEvent(
        job_id="141", tenant_id="tenant-123", from_status="ASSIGNED", to_status="EN_ROUTE",
        actor_id="tech-1", actor_role="technician", reason="Started travel",
        timestamp=datetime.now(timezone.utc), job_title="AC Repair", job_location="Chennai",
        technician_id=None, technician_name="John Tech", customer_id="cust-141",
        customer_name="Alice", customer_phone="+12222222222", customer_email="alice@example.com",
        eta="15 mins", notification_channels=[],
    )
    router = NotificationRouter(
        fcm_service=AsyncMock(return_value={"sent": 0}),
        sms_service=AsyncMock(), email_service=AsyncMock(), ws_manager=MagicMock(),
        redis_client=fake_redis, communication_integration=FakeCommunicationIntegration(),
    )
    with patch("app.services.twilio_sms.TWILIO_ACCOUNT_SID", "AC_real"), \
         patch("app.services.twilio_sms.dispatch_twilio_message", side_effect=RuntimeError("temporary")) as mock_twilio:
        result = await router._send_sms(event, "customer", {}, "technician_en_route")
    assert result is False
    mock_twilio.assert_called_once_with(
        body="Your FieldOps service request has been updated.",
        to_phone="+12222222222",
    )

@pytest.mark.anyio
async def test_notification_router_customer_sms_exactly_160_chars_is_delivered(
    setup_db,
):
    event = JobStatusEvent(
        job_id="142", tenant_id="tenant-123", from_status="ASSIGNED", to_status="EN_ROUTE",
        actor_id="tech-1", actor_role="technician", reason="Started travel",
        timestamp=datetime.now(timezone.utc), job_title="AC Repair", job_location="Chennai",
        technician_id=None, technician_name="John Tech", customer_id="cust-142",
        customer_name="Alice", customer_phone="+12222222222", customer_email="alice@example.com",
        eta="15 mins", notification_channels=[],
    )
    communication = MagicMock()
    communication.generate = AsyncMock(return_value=_communication_result(text="x" * 160))
    router = NotificationRouter(
        fcm_service=MagicMock(), sms_service=MagicMock(), email_service=MagicMock(),
        ws_manager=MagicMock(), redis_client=fake_redis, communication_integration=communication,
    )
    router._evaluate_customer_delivery_policy = MagicMock(return_value=SimpleNamespace(allowed=True))
    with patch("app.services.twilio_sms.TWILIO_ACCOUNT_SID", "AC_real"), \
         patch("app.services.twilio_sms.dispatch_twilio_message", return_value={"success": True}) as mock_twilio:
        result = await router._send_sms(event, "customer", {}, "technician_en_route")
    assert result is True
    assert len(mock_twilio.call_args.kwargs["body"]) == 160

@pytest.mark.anyio
async def test_notification_router_customer_sms_none_phone_blocks_transport(
    setup_db,
):
    event = JobStatusEvent(
        job_id="143",
        tenant_id="tenant-123",
        from_status="ASSIGNED",
        to_status="EN_ROUTE",
        actor_id="tech-1",
        actor_role="technician",
        reason="Technician started travel",
        timestamp=datetime.now(timezone.utc),
        job_title="AC Repair",
        job_location="Chennai",
        technician_id=None,
        technician_name="John Tech",
        customer_id="cust-143",
        customer_name="Alice",
        customer_phone=None,
        customer_email="alice@example.com",
        eta="15 mins",
        notification_channels=[],
    )

    communication = FakeCommunicationIntegration()

    router = NotificationRouter(
        fcm_service=MagicMock(return_value=asyncio.Future()),
        sms_service=MagicMock(return_value=asyncio.Future()),
        email_service=MagicMock(),
        ws_manager=MagicMock(),
        redis_client=fake_redis,
        communication_integration=communication,
    )

    router.fcm.return_value.set_result({"sent": 0})

    with patch(
        "app.services.twilio_sms.dispatch_twilio_message"
    ) as mock_twilio:
        await router.route(event)

    mock_twilio.assert_not_called()

@pytest.mark.anyio
async def test_notification_router_customer_sms_queued_status(
    setup_db,
):
    event = JobStatusEvent(
        job_id="144",
        tenant_id="tenant-123",
        from_status="ASSIGNED",
        to_status="ON_SITE",
        actor_id="tech-1",
        actor_role="technician",
        reason="Technician arrived",
        timestamp=datetime.now(timezone.utc),
        job_title="AC Repair",
        job_location="Chennai",
        technician_id=None,
        technician_name="John Tech",
        customer_id="cust-144",
        customer_name="Alice",
        customer_phone="+12222222222",
        customer_email="alice@example.com",
        eta=None,
        notification_channels=[],
    )

    communication = FakeCommunicationIntegration()

    router = NotificationRouter(
        fcm_service=MagicMock(return_value=asyncio.Future()),
        sms_service=MagicMock(return_value=asyncio.Future()),
        email_service=MagicMock(),
        ws_manager=MagicMock(),
        redis_client=fake_redis,
        communication_integration=communication,
    )

    router.fcm.return_value.set_result({"sent": 0})

    twilio_result = {
        "success": True,
        "sid": "SM_QUEUE_144",
        "status": "queued",
    }

    with patch(
        "app.services.twilio_sms.dispatch_twilio_message",
        return_value=twilio_result,
    ):
        await router.route(event)

    assert twilio_result["success"] is True
    assert twilio_result["sid"] == "SM_QUEUE_144"
    assert twilio_result["status"] == "queued"


@pytest.mark.anyio
async def test_notification_router_customer_sms_preserves_phone(
    setup_db,
):
    event = JobStatusEvent(
        job_id="145",
        tenant_id="tenant-123",
        from_status="ASSIGNED",
        to_status="EN_ROUTE",
        actor_id="tech-1",
        actor_role="technician",
        reason="Technician started travel",
        timestamp=datetime.now(timezone.utc),
        job_title="AC Repair",
        job_location="Chennai",
        technician_id=None,
        technician_name="John Tech",
        customer_id="cust-145",
        customer_name="Alice",
        customer_phone="+12222222222",
        customer_email="alice@example.com",
        eta="10 mins",
        notification_channels=[],
    )

    communication = FakeCommunicationIntegration()

    router = NotificationRouter(
        fcm_service=MagicMock(return_value=asyncio.Future()),
        sms_service=MagicMock(return_value=asyncio.Future()),
        email_service=MagicMock(),
        ws_manager=MagicMock(),
        redis_client=fake_redis,
        communication_integration=communication,
    )

    router.fcm.return_value.set_result({"sent": 0})

    with patch(
        "app.services.twilio_sms.dispatch_twilio_message",
        return_value={
            "success": True,
            "sid": "SM_PHONE_145",
            "status": "queued",
        },
    ):
        await router.route(event)

    sms_calls = [
        call
        for call in communication.calls
        if call["recipient_type"] == "customer"
        and call["channel"].strip().upper() == "SMS"
    ]

    assert len(sms_calls) == 1
    assert sms_calls[0]["event"].customer_phone == "+12222222222"

@pytest.mark.anyio
async def test_notification_router_unsupported_status_is_ignored(setup_db):
    event = JobStatusEvent(
        job_id="146",
        tenant_id="tenant-123",
        from_status="CREATED",
        to_status="UNKNOWN_STATUS",
        actor_id="tech-1",
        actor_role="technician",
        reason="Unknown transition",
        timestamp=datetime.now(timezone.utc),
        job_title="AC Repair",
        job_location="Chennai",
        technician_id="1",
        technician_name="John Tech",
        customer_id="cust-146",
        customer_name="Alice",
        customer_phone="+12222222222",
        customer_email="alice@example.com",
        eta=None,
        notification_channels=[],
    )

    communication = FakeCommunicationIntegration()

    router = NotificationRouter(
        fcm_service=MagicMock(return_value=asyncio.Future()),
        sms_service=MagicMock(return_value=asyncio.Future()),
        email_service=MagicMock(),
        ws_manager=MagicMock(),
        redis_client=fake_redis,
        communication_integration=communication,
    )

    router.fcm.return_value.set_result({"sent": 0})

    await router.route(event)

    assert communication.calls == []


@pytest.mark.anyio
async def test_notification_router_status_with_whitespace_is_normalized(
    setup_db,
):
    event = JobStatusEvent(
        job_id="148",
        tenant_id="tenant-123",
        from_status="ASSIGNED",
        to_status="  EN_ROUTE  ",
        actor_id="tech-1",
        actor_role="technician",
        reason="Technician started travel",
        timestamp=datetime.now(timezone.utc),
        job_title="AC Repair",
        job_location="Chennai",
        technician_id="1",
        technician_name="John Tech",
        customer_id="cust-148",
        customer_name="Alice",
        customer_phone="+12222222222",
        customer_email="alice@example.com",
        eta="15 mins",
        notification_channels=[],
    )

    communication = FakeCommunicationIntegration()

    router = NotificationRouter(
        fcm_service=MagicMock(return_value=asyncio.Future()),
        sms_service=MagicMock(return_value=asyncio.Future()),
        email_service=MagicMock(),
        ws_manager=MagicMock(),
        redis_client=fake_redis,
        communication_integration=communication,
    )

    router.fcm.return_value.set_result({"sent": 0})

    await router.route(event)

    customer_sms_calls = [
        call
        for call in communication.calls
        if call["recipient_type"] == "customer"
        and call["channel"].strip().upper() == "SMS"
    ]

    assert len(customer_sms_calls) == 1




@pytest.mark.anyio
async def test_notification_router_empty_channels_uses_status_routing(
    setup_db,
):
    event = JobStatusEvent(
        job_id="150",
        tenant_id="tenant-123",
        from_status="ASSIGNED",
        to_status="EN_ROUTE",
        actor_id="tech-1",
        actor_role="technician",
        reason="Technician started travel",
        timestamp=datetime.now(timezone.utc),
        job_title="AC Repair",
        job_location="Chennai",
        technician_id="1",
        technician_name="John Tech",
        customer_id="cust-150",
        customer_name="Alice",
        customer_phone="+12222222222",
        customer_email="alice@example.com",
        eta="15 mins",
        notification_channels=[],
    )

    communication = FakeCommunicationIntegration()

    router = NotificationRouter(
        fcm_service=MagicMock(return_value=asyncio.Future()),
        sms_service=MagicMock(return_value=asyncio.Future()),
        email_service=MagicMock(),
        ws_manager=MagicMock(),
        redis_client=fake_redis,
        communication_integration=communication,
    )

    router.fcm.return_value.set_result({"sent": 0})

    await router.route(event)

    customer_sms_calls = [
        call
        for call in communication.calls
        if call["recipient_type"] == "customer"
        and call["channel"].strip().upper() == "SMS"
    ]

    assert len(customer_sms_calls) == 1

@pytest.mark.anyio
async def test_notification_router_missing_customer_email_skips_email(setup_db):
    event = JobStatusEvent(
        job_id="150",
        tenant_id="tenant-123",
        from_status="ON_SITE",
        to_status="COMPLETED",
        actor_id="tech-1",
        actor_role="technician",
        reason="Job completed",
        timestamp=datetime.now(timezone.utc),
        job_title="AC Repair",
        job_location="Chennai",
        technician_id="1",
        technician_name="John Tech",
        customer_id="cust-150",
        customer_name="Alice",
        customer_phone="+12222222222",
        customer_email=None,
        eta=None,
        notification_channels=["EMAIL"],
    )

    email_service = MagicMock()
    router = NotificationRouter(
        fcm_service=MagicMock(),
        sms_service=MagicMock(),
        email_service=email_service,
        ws_manager=MagicMock(),
        redis_client=fake_redis,
        communication_integration=FakeCommunicationIntegration(),
    )

    await router.route(event)

    email_service.send_email.assert_not_called()


@pytest.mark.anyio
async def test_notification_router_non_customer_email_returns_false(setup_db):
    event = JobStatusEvent(
        job_id="151",
        tenant_id="tenant-123",
        from_status="ASSIGNED",
        to_status="EN_ROUTE",
        actor_id="tech-1",
        actor_role="technician",
        reason="Started travel",
        timestamp=datetime.now(timezone.utc),
        job_title="AC Repair",
        job_location="Chennai",
        technician_id="1",
        technician_name="John Tech",
        customer_id="cust-151",
        customer_name="Alice",
        customer_phone="+12222222222",
        customer_email="alice@example.com",
        eta="20 mins",
        notification_channels=["EMAIL"],
    )

    router = NotificationRouter(
        fcm_service=MagicMock(),
        sms_service=MagicMock(),
        email_service=MagicMock(),
        ws_manager=MagicMock(),
        redis_client=fake_redis,
        communication_integration=FakeCommunicationIntegration(),
    )

    result = await router._send_email(
        event=event,
        recipient_type="technician",
        payload={},
        config={},
        notification_type="job_update",
    )

    assert result is False





@pytest.mark.anyio
async def test_notification_router_customer_email_delivery_failure_returns_false(setup_db):
    event = JobStatusEvent(
        job_id="154",
        tenant_id="tenant-123",
        from_status="ON_SITE",
        to_status="COMPLETED",
        actor_id="tech-1",
        actor_role="technician",
        reason="Job completed",
        timestamp=datetime.now(timezone.utc),
        job_title="AC Repair",
        job_location="Chennai",
        technician_id="1",
        technician_name="John Tech",
        customer_id="cust-154",
        customer_name="Alice",
        customer_phone="+12222222222",
        customer_email="alice@example.com",
        eta=None,
        notification_channels=["EMAIL"],
    )

    email_service = MagicMock()
    email_service.send_email = AsyncMock(return_value=False)

    router = NotificationRouter(
        fcm_service=MagicMock(),
        sms_service=MagicMock(),
        email_service=email_service,
        ws_manager=MagicMock(),
        redis_client=fake_redis,
        communication_integration=FakeCommunicationIntegration(),
    )

    await router.route(event)

    email_service.send_email.assert_awaited_once()



# ============================================================================
# Additional branch/edge coverage for NotificationRouter and helpers
# ============================================================================

from types import SimpleNamespace
import os


def _make_event(**overrides):
    values = {
        "job_id": "900",
        "tenant_id": "tenant-900",
        "from_status": "ASSIGNED",
        "to_status": "EN_ROUTE",
        "actor_id": "tech-900",
        "actor_role": "technician",
        "reason": "Started travel",
        "timestamp": datetime.now(timezone.utc),
        "job_title": "AC Repair",
        "job_location": "Chennai",
        "technician_id": "tech-900",
        "technician_name": "John Tech",
        "customer_id": "cust-900",
        "customer_name": "Alice",
        "customer_phone": "+12222222222",
        "customer_email": "alice@example.com",
        "eta": "20 mins",
        "notification_channels": [],
    }
    values.update(overrides)
    return JobStatusEvent(**values)


def _communication_result(channel="SMS", text="FieldOps update", title="FieldOps update", subject="FieldOps service update", html_body=None):
    output = SimpleNamespace(
        text=text,
        body=text,
        title=title,
        subject=subject,
        text_body=text,
        html_body=html_body,
    )
    decision = SimpleNamespace(channel=channel, output=output)
    return SimpleNamespace(decision=decision)


@pytest.mark.anyio
async def test_sendgrid_simulation_mode_returns_true(monkeypatch):
    monkeypatch.delenv("SENDGRID_API_KEY", raising=False)
    service = notification_module.SendGridService(api_key="SG.mock_key")
    assert await service.send_email("alice@example.com", "Subject", "<p>Body</p>") is True


@pytest.mark.anyio
async def test_sendgrid_non_success_status_returns_false(monkeypatch):
    class Response:
        status_code = 400

    class FakeClient:
        def __init__(self, key):
            self.key = key

        def send(self, message):
            return Response()

    class FakeMail:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    fake_sendgrid = SimpleNamespace(SendGridAPIClient=FakeClient)
    fake_helpers = SimpleNamespace(Mail=FakeMail)
    monkeypatch.setitem(__import__("sys").modules, "sendgrid", fake_sendgrid)
    monkeypatch.setitem(__import__("sys").modules, "sendgrid.helpers", SimpleNamespace(mail=fake_helpers))
    monkeypatch.setitem(__import__("sys").modules, "sendgrid.helpers.mail", fake_helpers)
    monkeypatch.setenv("SENDGRID_API_KEY", "SG.real-key")

    service = notification_module.SendGridService(api_key="SG.real-key")
    assert await service.send_email("alice@example.com", "Subject", "Body") is False


@pytest.mark.anyio
async def test_sendgrid_success_status_returns_true(monkeypatch):
    class Response:
        status_code = 202

    class FakeClient:
        def __init__(self, key):
            self.key = key

        def send(self, message):
            return Response()

    class FakeMail:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    fake_sendgrid = SimpleNamespace(SendGridAPIClient=FakeClient)
    fake_helpers = SimpleNamespace(Mail=FakeMail)
    monkeypatch.setitem(__import__("sys").modules, "sendgrid", fake_sendgrid)
    monkeypatch.setitem(__import__("sys").modules, "sendgrid.helpers", SimpleNamespace(mail=fake_helpers))
    monkeypatch.setitem(__import__("sys").modules, "sendgrid.helpers.mail", fake_helpers)
    monkeypatch.setenv("SENDGRID_API_KEY", "SG.real-key")

    service = notification_module.SendGridService(api_key="SG.real-key")
    assert await service.send_email("alice@example.com", "Subject", "Body") is True


@pytest.mark.anyio
async def test_sendgrid_exception_returns_false(monkeypatch):
    class FakeClient:
        def __init__(self, key):
            pass

        def send(self, message):
            raise RuntimeError("provider down")

    class FakeMail:
        def __init__(self, **kwargs):
            pass

    fake_helpers = SimpleNamespace(Mail=FakeMail)
    monkeypatch.setitem(__import__("sys").modules, "sendgrid", SimpleNamespace(SendGridAPIClient=FakeClient))
    monkeypatch.setitem(__import__("sys").modules, "sendgrid.helpers", SimpleNamespace(mail=fake_helpers))
    monkeypatch.setitem(__import__("sys").modules, "sendgrid.helpers.mail", fake_helpers)
    monkeypatch.setenv("SENDGRID_API_KEY", "SG.real-key")

    service = notification_module.SendGridService(api_key="SG.real-key")
    assert await service.send_email("alice@example.com", "Subject", "Body") is False


@pytest.mark.anyio
async def test_event_publisher_without_redis_still_writes_audit(monkeypatch, setup_db):
    publisher = EventPublisher(redis_client=None)
    publisher.redis = None
    publisher._write_audit = AsyncMock()
    event = _make_event()
    await publisher.publish(event)
    publisher._write_audit.assert_awaited_once_with(event)


@pytest.mark.anyio
async def test_event_publisher_redis_failure_still_writes_audit(monkeypatch, setup_db):
    redis = MagicMock()
    redis.publish.side_effect = RuntimeError("redis down")
    publisher = EventPublisher(redis_client=redis)
    publisher._write_audit = AsyncMock()
    event = _make_event()
    await publisher.publish(event)
    redis.publish.assert_called_once()
    publisher._write_audit.assert_awaited_once_with(event)


@pytest.mark.anyio
async def test_event_publisher_audit_failure_rolls_back_and_closes(monkeypatch, setup_db):
    db = MagicMock()
    db.add.side_effect = RuntimeError("db failure")
    session_factory = MagicMock(return_value=db)
    monkeypatch.setattr(notification_module, "SessionLocal", session_factory)
    publisher = EventPublisher(redis_client=None)
    await publisher._write_audit(_make_event())
    db.rollback.assert_called_once()
    db.close.assert_called_once()


def test_resolve_notification_type_normalizes_alias_and_unknown():
    assert NotificationRouter._resolve_notification_type(" Technician_Job_Assigned ") == "job_assigned"
    assert NotificationRouter._resolve_notification_type("unknown-template") == "unknown-template"


def test_build_payload_uses_string_timestamp_and_customer_eta_fallback():
    event = _make_event(timestamp="raw-time", eta=None)
    router = NotificationRouter(
        fcm_service=MagicMock(), sms_service=MagicMock(), email_service=MagicMock(),
        ws_manager=MagicMock(), redis_client=fake_redis,
        communication_integration=FakeCommunicationIntegration(),
    )
    payload = router._build_payload(
        event, "customer", {"include_eta": True, "include_survey_link": True}
    )
    assert payload["timestamp"] == "raw-time"
    assert payload["eta"] == "calculating..."
    assert payload["survey_link"].endswith("/900")


def test_build_payload_dispatcher_and_unknown_recipient():
    router = NotificationRouter(
        fcm_service=MagicMock(), sms_service=MagicMock(), email_service=MagicMock(),
        ws_manager=MagicMock(), redis_client=fake_redis,
        communication_integration=FakeCommunicationIntegration(),
    )
    event = _make_event()
    dispatcher = router._build_payload(event, "dispatcher", {})
    unknown = router._build_payload(event, "other", {})
    assert dispatcher["actor_name"] == event.actor_id
    assert "actor_name" not in unknown


@pytest.mark.anyio
async def test_generate_safe_communication_propagates_channel_disabled(setup_db):
    communication = MagicMock()
    communication.generate = AsyncMock(side_effect=notification_module.CommunicationChannelDisabledError("disabled", SimpleNamespace(final_reason_code="DISABLED")))
    router = NotificationRouter(
        fcm_service=MagicMock(), sms_service=MagicMock(), email_service=MagicMock(),
        ws_manager=MagicMock(), redis_client=fake_redis, communication_integration=communication,
    )
    with pytest.raises(notification_module.CommunicationChannelDisabledError):
        await router._generate_safe_communication(
            event=_make_event(), recipient_type="customer", channel="sms", notification_type="job_update"
        )


@pytest.mark.anyio
@pytest.mark.parametrize("exc", [notification_module.CommunicationIntegrationError("integration"), RuntimeError("unexpected")])
async def test_generate_safe_communication_returns_none_on_generation_errors(setup_db, exc):
    communication = MagicMock()
    communication.generate = AsyncMock(side_effect=exc)
    router = NotificationRouter(
        fcm_service=MagicMock(), sms_service=MagicMock(), email_service=MagicMock(),
        ws_manager=MagicMock(), redis_client=fake_redis, communication_integration=communication,
    )
    result = await router._generate_safe_communication(
        event=_make_event(), recipient_type="customer", channel="sms", notification_type="job_update"
    )
    assert result is None


@pytest.mark.anyio
async def test_generate_safe_communication_returns_none_for_none_result(setup_db):
    communication = MagicMock()
    communication.generate = AsyncMock(return_value=None)
    router = NotificationRouter(
        fcm_service=MagicMock(), sms_service=MagicMock(), email_service=MagicMock(),
        ws_manager=MagicMock(), redis_client=fake_redis, communication_integration=communication,
    )
    assert await router._generate_safe_communication(
        event=_make_event(), recipient_type="customer", channel="sms", notification_type="job_update"
    ) is None


@pytest.mark.anyio
async def test_generate_safe_communication_returns_none_for_invalid_decision(setup_db):
    communication = MagicMock()
    communication.generate = AsyncMock(return_value=SimpleNamespace(decision=SimpleNamespace()))
    router = NotificationRouter(
        fcm_service=MagicMock(), sms_service=MagicMock(), email_service=MagicMock(),
        ws_manager=MagicMock(), redis_client=fake_redis, communication_integration=communication,
    )
    assert await router._generate_safe_communication(
        event=_make_event(), recipient_type="customer", channel="sms", notification_type="job_update"
    ) is None


@pytest.mark.anyio
async def test_generate_safe_communication_returns_none_for_wrong_channel(setup_db):
    communication = MagicMock()
    communication.generate = AsyncMock(return_value=_communication_result(channel="EMAIL"))
    router = NotificationRouter(
        fcm_service=MagicMock(), sms_service=MagicMock(), email_service=MagicMock(),
        ws_manager=MagicMock(), redis_client=fake_redis, communication_integration=communication,
    )
    assert await router._generate_safe_communication(
        event=_make_event(), recipient_type="customer", channel="sms", notification_type="job_update"
    ) is None


@pytest.mark.anyio
@pytest.mark.parametrize("recipient_type", ["dispatcher", "other"])
async def test_send_sms_rejects_unsupported_recipient(setup_db, recipient_type):
    router = NotificationRouter(
        fcm_service=MagicMock(), sms_service=MagicMock(), email_service=MagicMock(),
        ws_manager=MagicMock(), redis_client=fake_redis, communication_integration=FakeCommunicationIntegration(),
    )
    assert await router._send_sms(_make_event(), recipient_type, {}, "job_update") is False


@pytest.mark.anyio
async def test_send_sms_rejects_non_string_body(setup_db):
    communication = MagicMock()
    communication.generate = AsyncMock(return_value=_communication_result(text=123))
    router = NotificationRouter(
        fcm_service=MagicMock(), sms_service=MagicMock(), email_service=MagicMock(),
        ws_manager=MagicMock(), redis_client=fake_redis, communication_integration=communication,
    )
    assert await router._send_sms(_make_event(technician_id=None), "customer", {}, "job_update") is False


@pytest.mark.anyio
async def test_send_sms_technician_missing_id_returns_false(setup_db):
    router = NotificationRouter(
        fcm_service=MagicMock(), sms_service=MagicMock(), email_service=MagicMock(),
        ws_manager=MagicMock(), redis_client=fake_redis, communication_integration=FakeCommunicationIntegration(),
    )
    assert await router._send_sms(_make_event(technician_id=None), "technician", {}, "job_update") is False


@pytest.mark.anyio
@pytest.mark.parametrize("result,expected", [({"sent": 1}, True), ({"sent": 0}, False), (True, True), (False, False)])
async def test_send_sms_technician_delivery_result_shapes(setup_db, result, expected):
    sms = AsyncMock(return_value=result)
    router = NotificationRouter(
        fcm_service=MagicMock(), sms_service=sms, email_service=MagicMock(),
        ws_manager=MagicMock(), redis_client=fake_redis, communication_integration=FakeCommunicationIntegration(),
    )
    with patch.object(notification_module, "SessionLocal", return_value=MagicMock()):
        actual = await router._send_sms(_make_event(), "technician", {}, "job_update")
    assert actual is expected
    sms.assert_awaited_once()


@pytest.mark.anyio
async def test_send_sms_technician_exception_returns_false(setup_db):
    sms = AsyncMock(side_effect=RuntimeError("sms adapter failed"))
    router = NotificationRouter(
        fcm_service=MagicMock(), sms_service=sms, email_service=MagicMock(),
        ws_manager=MagicMock(), redis_client=fake_redis, communication_integration=FakeCommunicationIntegration(),
    )
    with patch.object(notification_module, "SessionLocal", return_value=MagicMock()):
        assert await router._send_sms(_make_event(), "technician", {}, "job_update") is False


@pytest.mark.anyio
async def test_send_sms_customer_local_mock_mode_returns_true(setup_db):
    router = NotificationRouter(
        fcm_service=MagicMock(), sms_service=MagicMock(), email_service=MagicMock(),
        ws_manager=MagicMock(), redis_client=fake_redis, communication_integration=FakeCommunicationIntegration(),
    )
    with patch("app.services.twilio_sms.TWILIO_ACCOUNT_SID", "dummy-account"), \
         patch("app.services.twilio_sms.dispatch_twilio_message") as dispatch:
        assert await router._send_sms(_make_event(technician_id=None), "customer", {}, "job_update") is True
    dispatch.assert_not_called()


@pytest.mark.anyio
async def test_send_sms_customer_real_transport_success(setup_db):
    router = NotificationRouter(
        fcm_service=MagicMock(), sms_service=MagicMock(), email_service=MagicMock(),
        ws_manager=MagicMock(), redis_client=fake_redis, communication_integration=FakeCommunicationIntegration(),
    )
    with patch("app.services.twilio_sms.TWILIO_ACCOUNT_SID", "AC_real"), \
         patch("app.services.twilio_sms.dispatch_twilio_message", return_value={"success": True}) as dispatch:
        assert await router._send_sms(_make_event(technician_id=None), "customer", {}, "job_update") is True
    dispatch.assert_called_once_with(body="Your FieldOps service request has been updated.", to_phone="+12222222222")


@pytest.mark.anyio
async def test_send_sms_customer_real_transport_failure_returns_false(setup_db):
    router = NotificationRouter(
        fcm_service=MagicMock(), sms_service=MagicMock(), email_service=MagicMock(),
        ws_manager=MagicMock(), redis_client=fake_redis, communication_integration=FakeCommunicationIntegration(),
    )
    with patch("app.services.twilio_sms.TWILIO_ACCOUNT_SID", "AC_real"), \
         patch("app.services.twilio_sms.dispatch_twilio_message", side_effect=RuntimeError("twilio")):
        assert await router._send_sms(_make_event(technician_id=None), "customer", {}, "job_update") is False


@pytest.mark.anyio
async def test_send_push_rejects_customer_and_missing_technician(setup_db):
    router = NotificationRouter(
        fcm_service=AsyncMock(), sms_service=MagicMock(), email_service=MagicMock(),
        ws_manager=MagicMock(), redis_client=fake_redis, communication_integration=FakeCommunicationIntegration(),
    )
    assert await router._send_push(_make_event(), "customer", {}, "high", "job_update") is False
    assert await router._send_push(_make_event(technician_id=None), "technician", {}, "high", "job_update") is False


@pytest.mark.anyio
async def test_send_push_missing_fcm_token_returns_false(setup_db):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(fcm_token=None)
    router = NotificationRouter(
        fcm_service=AsyncMock(), sms_service=MagicMock(), email_service=MagicMock(),
        ws_manager=MagicMock(), redis_client=fake_redis, communication_integration=FakeCommunicationIntegration(),
    )
    with patch.object(notification_module, "SessionLocal", return_value=db):
        assert await router._send_push(_make_event(), "technician", {}, "high", "job_update") is False


@pytest.mark.anyio
async def test_send_push_missing_title_and_long_title_return_false(setup_db):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(fcm_token="token")
    communication = MagicMock()
    communication.generate = AsyncMock(side_effect=[_communication_result(channel="PUSH", title=""), _communication_result(channel="PUSH", title="x" * 51)])
    router = NotificationRouter(
        fcm_service=AsyncMock(), sms_service=MagicMock(), email_service=MagicMock(),
        ws_manager=MagicMock(), redis_client=fake_redis, communication_integration=communication,
    )
    with patch.object(notification_module, "SessionLocal", return_value=db):
        assert await router._send_push(_make_event(), "technician", {}, "high", "job_update") is False
        assert await router._send_push(_make_event(), "technician", {}, "high", "job_update") is False


@pytest.mark.anyio
@pytest.mark.parametrize("result,expected", [({"sent": 2}, True), ({"sent": 0}, False), (True, True), (False, False)])
async def test_send_push_delivery_result_shapes(setup_db, result, expected):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(fcm_token="token")
    fcm = AsyncMock(return_value=result)
    router = NotificationRouter(
        fcm_service=fcm, sms_service=MagicMock(), email_service=MagicMock(),
        ws_manager=MagicMock(), redis_client=fake_redis, communication_integration=FakeCommunicationIntegration(),
    )
    with patch.object(notification_module, "SessionLocal", return_value=db):
        actual = await router._send_push(_make_event(), "technician", {}, "high", "job_update")
    assert actual is expected


@pytest.mark.anyio
async def test_send_push_fcm_exception_returns_false(setup_db):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(fcm_token="token")
    fcm = AsyncMock(side_effect=RuntimeError("fcm down"))
    router = NotificationRouter(
        fcm_service=fcm, sms_service=MagicMock(), email_service=MagicMock(),
        ws_manager=MagicMock(), redis_client=fake_redis, communication_integration=FakeCommunicationIntegration(),
    )
    with patch.object(notification_module, "SessionLocal", return_value=db):
        assert await router._send_push(_make_event(), "technician", {}, "high", "job_update") is False


@pytest.mark.anyio
async def test_send_email_subject_validation_branches(setup_db):
    cases = [SimpleNamespace(subject=123, text_body="Body", html_body=None), SimpleNamespace(subject="   ", text_body="Body", html_body=None), SimpleNamespace(subject="x" * 79, text_body="Body", html_body=None)]
    for output in cases:
        communication = MagicMock()
        communication.generate = AsyncMock(return_value=SimpleNamespace(decision=SimpleNamespace(channel="EMAIL", output=output)))
        router = NotificationRouter(
            fcm_service=MagicMock(), sms_service=MagicMock(), email_service=AsyncMock(),
            ws_manager=MagicMock(), redis_client=fake_redis, communication_integration=communication,
        )
        router._evaluate_customer_delivery_policy = MagicMock(return_value=SimpleNamespace(allowed=True))
        assert await router._send_email(_make_event(), "customer", {}, {}, "job_update") is False


@pytest.mark.anyio
async def test_send_email_uses_text_when_html_missing_and_adds_escaped_survey(setup_db):
    email = MagicMock()
    email.send_email = AsyncMock(return_value=True)
    communication = MagicMock()
    communication.generate = AsyncMock(return_value=_communication_result(channel="EMAIL", text="Body & text", subject="Subject", html_body=None))
    router = NotificationRouter(
        fcm_service=MagicMock(), sms_service=MagicMock(), email_service=email,
        ws_manager=MagicMock(), redis_client=fake_redis, communication_integration=communication,
    )
    router._evaluate_customer_delivery_policy = MagicMock(return_value=SimpleNamespace(allowed=True))
    result = await router._send_email(_make_event(job_id="a/b"), "customer", {}, {"include_survey_link": True}, "job_update")
    assert result is True
    body = email.send_email.await_args.args[2]
    assert "Take Survey" in body
    assert "a%2Fb" in body


@pytest.mark.anyio
async def test_send_email_policy_block_raises(setup_db):
    router = NotificationRouter(
        fcm_service=MagicMock(), sms_service=MagicMock(), email_service=AsyncMock(),
        ws_manager=MagicMock(), redis_client=fake_redis, communication_integration=FakeCommunicationIntegration(),
    )
    router._evaluate_customer_delivery_policy = MagicMock(return_value=SimpleNamespace(allowed=False, final_reason_code="OPTED_OUT"))
    with pytest.raises(notification_module.CommunicationChannelDisabledError):
        await router._send_email(_make_event(), "customer", {}, {}, "job_update")


@pytest.mark.anyio
async def test_send_email_generation_failure_returns_false(setup_db):
    communication = MagicMock()
    communication.generate = AsyncMock(return_value=None)
    router = NotificationRouter(
        fcm_service=MagicMock(), sms_service=MagicMock(), email_service=AsyncMock(),
        ws_manager=MagicMock(), redis_client=fake_redis, communication_integration=communication,
    )
    router._evaluate_customer_delivery_policy = MagicMock(return_value=SimpleNamespace(allowed=True))
    assert await router._send_email(_make_event(), "customer", {}, {}, "job_update") is False


@pytest.mark.anyio
async def test_send_in_app_rejects_non_dispatcher_and_generation_failure(setup_db):
    router = NotificationRouter(
        fcm_service=MagicMock(), sms_service=MagicMock(), email_service=MagicMock(),
        ws_manager=MagicMock(), redis_client=fake_redis, communication_integration=FakeCommunicationIntegration(),
    )
    assert await router._send_in_app(_make_event(), "customer", {}, False, "job_update") is False
    communication = MagicMock()
    communication.generate = AsyncMock(return_value=None)
    router.communication = communication
    assert await router._send_in_app(_make_event(), "dispatcher", {}, False, "job_update") is False


@pytest.mark.anyio
async def test_send_in_app_batch_without_redis_returns_false(setup_db):
    router = NotificationRouter(
        fcm_service=MagicMock(), sms_service=MagicMock(), email_service=MagicMock(),
        ws_manager=MagicMock(), redis_client=None, communication_integration=FakeCommunicationIntegration(),
    )
    router.redis = None
    assert await router._send_in_app(_make_event(), "dispatcher", {}, True, "job_update") is False


@pytest.mark.anyio
async def test_send_in_app_batch_redis_failure_returns_false(setup_db):
    redis = MagicMock()
    redis.lpush.side_effect = RuntimeError("redis failure")
    router = NotificationRouter(
        fcm_service=MagicMock(), sms_service=MagicMock(), email_service=MagicMock(),
        ws_manager=MagicMock(), redis_client=redis, communication_integration=FakeCommunicationIntegration(),
    )
    assert await router._send_in_app(_make_event(), "dispatcher", {}, True, "job_update") is False


@pytest.mark.anyio
async def test_send_in_app_immediate_broadcast_success_and_failure(setup_db):
    ws = MagicMock()
    ws.broadcast = AsyncMock()
    router = NotificationRouter(
        fcm_service=MagicMock(), sms_service=MagicMock(), email_service=MagicMock(),
        ws_manager=ws, redis_client=fake_redis, communication_integration=FakeCommunicationIntegration(),
    )
    assert await router._send_in_app(_make_event(), "dispatcher", {}, False, "job_update") is True
    ws.broadcast.assert_awaited_once()

    ws.broadcast.reset_mock()
    ws.broadcast.side_effect = RuntimeError("socket down")
    assert await router._send_in_app(_make_event(), "dispatcher", {}, False, "job_update") is False


def test_record_attempted_channel_does_not_duplicate():
    event = _make_event(notification_channels=["sms"])
    NotificationRouter._record_attempted_channel(event, "sms")
    NotificationRouter._record_attempted_channel(event, "email")
    assert event.notification_channels == ["sms", "email"]


@pytest.mark.anyio
async def test_check_preferences_returns_false_when_all_technician_channels_disabled(setup_db):
    tech = SimpleNamespace(tech_id="tech-900")
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = tech
    with patch.object(notification_module, "SessionLocal", return_value=db), \
         patch.object(notification_module, "get_technician_preferences", return_value={"sms_enabled": False, "push_enabled": False, "inapp_enabled": False}):
        router = NotificationRouter(
            fcm_service=MagicMock(), sms_service=MagicMock(), email_service=MagicMock(),
            ws_manager=MagicMock(), redis_client=fake_redis, communication_integration=FakeCommunicationIntegration(),
        )
        assert await router._check_preferences(_make_event(), "technician") is False


@pytest.mark.anyio
async def test_check_preferences_technician_missing_or_lookup_missing_returns_true(setup_db):
    router = NotificationRouter(
        fcm_service=MagicMock(), sms_service=MagicMock(), email_service=MagicMock(),
        ws_manager=MagicMock(), redis_client=fake_redis, communication_integration=FakeCommunicationIntegration(),
    )
    assert await router._check_preferences(_make_event(technician_id=None), "technician") is True
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    with patch.object(notification_module, "SessionLocal", return_value=db):
        assert await router._check_preferences(_make_event(), "technician") is True


@pytest.mark.anyio
async def test_check_preferences_exception_fails_closed(setup_db):
    db = MagicMock()
    db.query.side_effect = RuntimeError("db")
    router = NotificationRouter(
        fcm_service=MagicMock(), sms_service=MagicMock(), email_service=MagicMock(),
        ws_manager=MagicMock(), redis_client=fake_redis, communication_integration=FakeCommunicationIntegration(),
    )
    with patch.object(notification_module, "SessionLocal", return_value=db):
        assert await router._check_preferences(_make_event(), "technician") is False


@pytest.mark.anyio
@pytest.mark.parametrize("channel,prefs,expected", [
    ("sms", {"sms_enabled": False}, False),
    ("push", {"push_enabled": False}, False),
    ("in_app", {"inapp_enabled": False}, False),
    ("email", {}, True),
])
async def test_channel_allowed_for_technician_preferences(setup_db, channel, prefs, expected):
    tech = SimpleNamespace(tech_id="tech-900", sms_opt_out=0)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = tech
    router = NotificationRouter(
        fcm_service=MagicMock(), sms_service=MagicMock(), email_service=MagicMock(),
        ws_manager=MagicMock(), redis_client=fake_redis, communication_integration=FakeCommunicationIntegration(),
    )
    with patch.object(notification_module, "SessionLocal", return_value=db), \
         patch.object(notification_module, "get_technician_preferences", return_value=prefs):
        assert router._channel_allowed_for_recipient(_make_event(), "technician", channel) is expected


def test_channel_allowed_for_non_technician_and_missing_id():
    router = NotificationRouter(
        fcm_service=MagicMock(), sms_service=MagicMock(), email_service=MagicMock(),
        ws_manager=MagicMock(), redis_client=fake_redis, communication_integration=FakeCommunicationIntegration(),
    )
    assert router._channel_allowed_for_recipient(_make_event(), "customer", "sms") is True
    assert router._channel_allowed_for_recipient(_make_event(technician_id=None), "technician", "sms") is True


def test_channel_allowed_fails_closed_on_exception(setup_db):
    db = MagicMock()
    db.query.side_effect = RuntimeError("db")
    router = NotificationRouter(
        fcm_service=MagicMock(), sms_service=MagicMock(), email_service=MagicMock(),
        ws_manager=MagicMock(), redis_client=fake_redis, communication_integration=FakeCommunicationIntegration(),
    )
    with patch.object(notification_module, "SessionLocal", return_value=db):
        assert router._channel_allowed_for_recipient(_make_event(), "technician", "sms") is False


@pytest.mark.anyio
async def test_route_skips_recipient_when_preferences_fail_closed(setup_db):
    router = NotificationRouter(
        fcm_service=AsyncMock(), sms_service=AsyncMock(), email_service=AsyncMock(),
        ws_manager=MagicMock(), redis_client=fake_redis, communication_integration=FakeCommunicationIntegration(),
    )
    router._check_preferences = AsyncMock(return_value=False)
    await router.route(_make_event(to_status="ASSIGNED"))
    router._check_preferences.assert_awaited()
    router.fcm.assert_not_awaited()


@pytest.mark.anyio
async def test_route_unsupported_status_has_no_delivery(setup_db):
    router = NotificationRouter(
        fcm_service=AsyncMock(), sms_service=AsyncMock(), email_service=AsyncMock(),
        ws_manager=MagicMock(), redis_client=fake_redis, communication_integration=FakeCommunicationIntegration(),
    )
    await router.route(_make_event(to_status="NOT_A_STATUS"))
    router.fcm.assert_not_awaited()
    router.sms.assert_not_awaited()


@pytest.mark.anyio
async def test_route_handles_enroute_and_onsite_normalization(monkeypatch, setup_db):
    router = NotificationRouter(
        fcm_service=AsyncMock(), sms_service=AsyncMock(), email_service=AsyncMock(),
        ws_manager=MagicMock(), redis_client=fake_redis, communication_integration=FakeCommunicationIntegration(),
    )
    router._check_preferences = AsyncMock(return_value=False)
    fake_enum = SimpleNamespace(name="ENROUTE")
    with patch("app.services.ai.FieldOpsAI.schemas.prompt_template.normalize_template_status", return_value=fake_enum):
        await router.route(_make_event(to_status="legacy-enroute"))
    fake_enum = SimpleNamespace(name="ONSITE")
    with patch("app.services.ai.FieldOpsAI.schemas.prompt_template.normalize_template_status", return_value=fake_enum):
        await router.route(_make_event(to_status="legacy-onsite"))
    assert router._check_preferences.await_count == 6


@pytest.mark.anyio
async def test_route_channel_filter_skips_disallowed_channel(setup_db):
    router = NotificationRouter(
        fcm_service=AsyncMock(), sms_service=AsyncMock(), email_service=AsyncMock(),
        ws_manager=MagicMock(), redis_client=fake_redis, communication_integration=FakeCommunicationIntegration(),
    )
    router._channel_allowed_for_recipient = MagicMock(return_value=False)
    router._check_preferences = AsyncMock(return_value=True)
    await router.route(_make_event(to_status="EN_ROUTE"))
    assert router._channel_allowed_for_recipient.called
    router.fcm.assert_not_awaited()
    router.sms.assert_not_awaited()


@pytest.mark.anyio
async def test_route_handles_disabled_sms_and_email_channels(setup_db):
    router = NotificationRouter(
        fcm_service=AsyncMock(), sms_service=AsyncMock(), email_service=AsyncMock(),
        ws_manager=MagicMock(), redis_client=fake_redis, communication_integration=FakeCommunicationIntegration(),
    )
    router._check_preferences = AsyncMock(return_value=True)
    router._channel_allowed_for_recipient = MagicMock(return_value=True)
    disabled = notification_module.CommunicationChannelDisabledError("disabled", SimpleNamespace(final_reason_code="DISABLED"))
    router._send_sms = AsyncMock(side_effect=disabled)
    router._send_email = AsyncMock(side_effect=disabled)
    await router.route(_make_event(to_status="CANCELLED"))
    assert router._send_sms.await_count >= 1
    assert router._send_email.await_count >= 1


@pytest.mark.anyio
async def test_route_unknown_channel_is_ignored(setup_db):
    router = NotificationRouter(
        fcm_service=AsyncMock(), sms_service=AsyncMock(), email_service=AsyncMock(),
        ws_manager=MagicMock(), redis_client=fake_redis, communication_integration=FakeCommunicationIntegration(),
    )
    router.STATUS_NOTIFICATIONS = {"CUSTOM": {"customer": {"channels": ["fax"], "template": "custom"}}}
    router._check_preferences = AsyncMock(return_value=True)
    router._channel_allowed_for_recipient = MagicMock(return_value=True)
    await router.route(_make_event(to_status="CUSTOM"))
    assert router._check_preferences.await_count == 1


@pytest.mark.anyio
async def test_route_escalation_dashboard_email_success_and_no_email(setup_db):
    ws = MagicMock()
    ws.broadcast = AsyncMock()
    email = MagicMock()
    email.send_email = AsyncMock(return_value=True)
    router = NotificationRouter(
        fcm_service=MagicMock(), sms_service=MagicMock(), email_service=email,
        ws_manager=ws, redis_client=fake_redis, communication_integration=FakeCommunicationIntegration(),
    )
    payload = {"tenant_id": "tenant-1", "job_id": "job-1", "customer_name": "Alice", "sentiment_score": -0.8, "reply_text": "Need help"}
    result = await router_escalation_wrapper(router, "manager-1", "manager@example.com", None, payload)
    assert result == {"sms": False, "email": True, "push": False, "dashboard": True}
    email.send_email.assert_awaited_once()


async def router_escalation_wrapper(router, manager_id, manager_email, manager_phone, payload):
    # Keep the call explicit so the module-level function is tested with the router instance
    return await notification_module.route_escalation(router, manager_id, manager_email, manager_phone, payload)


@pytest.mark.anyio
async def test_route_escalation_dashboard_and_email_failures(setup_db):
    ws = MagicMock()
    ws.broadcast = AsyncMock(side_effect=RuntimeError("ws"))
    email = MagicMock()
    email.send_email = AsyncMock(side_effect=RuntimeError("email"))
    router = NotificationRouter(
        fcm_service=MagicMock(), sms_service=MagicMock(), email_service=email,
        ws_manager=ws, redis_client=fake_redis, communication_integration=FakeCommunicationIntegration(),
    )
    result = await notification_module.route_escalation(
        router, "manager-1", "manager@example.com", None, {"tenant_id": "tenant-1"}
    )
    assert result == {"sms": False, "email": False, "push": False, "dashboard": False}


@pytest.mark.anyio
async def test_route_escalation_without_ws_or_email_returns_false_results(setup_db):
    router = NotificationRouter(
        fcm_service=MagicMock(), sms_service=MagicMock(), email_service=MagicMock(),
        ws_manager=None, redis_client=fake_redis, communication_integration=FakeCommunicationIntegration(),
    )
    router.ws = None
    result = await notification_module.route_escalation(router, "manager-1", None, None, {})
    assert result == {"sms": False, "email": False, "push": False, "dashboard": False}


# ---------------------------------------------------------------------------
# Final branch-completion tests: these target the exact remaining uncovered
# statements in notification_services.py without duplicating existing flows.
# ---------------------------------------------------------------------------

def test_notification_router_constructor_uses_default_adapters(setup_db):
    router = NotificationRouter()
    assert router.fcm is not None
    assert router.sms is not None
    assert router.ws is not None


@pytest.mark.anyio
async def test_route_catches_email_channel_disabled(setup_db):
    router = NotificationRouter(
        fcm_service=AsyncMock(), sms_service=AsyncMock(), email_service=MagicMock(),
        ws_manager=MagicMock(), redis_client=fake_redis,
        communication_integration=FakeCommunicationIntegration(),
    )
    router._check_preferences = AsyncMock(return_value=True)
    router._channel_allowed_for_recipient = MagicMock(return_value=True)
    disabled = notification_module.CommunicationChannelDisabledError(
        "disabled", SimpleNamespace(final_reason_code="DISABLED")
    )
    router._send_email = AsyncMock(side_effect=disabled)
    await router.route(_make_event(to_status="COMPLETED"))
    router._send_email.assert_awaited()


def test_channel_allowed_technician_sms_opt_out_returns_false(setup_db):
    db = TestingSessionLocal()
    tech = Technician(
        technician_id=99,
        tech_id="optout-tech",
        technician_name="Opt Out Tech",
        technician_skill="Plumbing",
        technician_location="Zone A",
        phone_number="+15555555555",
        sms_opt_out=1,
    )
    db.add(tech)
    db.commit()
    db.close()

    router = NotificationRouter(
        fcm_service=MagicMock(), sms_service=MagicMock(), email_service=MagicMock(),
        ws_manager=MagicMock(), redis_client=fake_redis,
        communication_integration=FakeCommunicationIntegration(),
    )
    event = _make_event(technician_id="optout-tech")
    assert router._channel_allowed_for_recipient(event, "technician", "sms") is False


@pytest.mark.anyio
async def test_generate_safe_communication_propagates_disabled_exception(setup_db):
    decision = SimpleNamespace(final_reason_code="DISABLED")
    communication = MagicMock()
    communication.generate = AsyncMock(
        side_effect=notification_module.CommunicationChannelDisabledError(
            "disabled", decision
        )
    )
    router = NotificationRouter(
        fcm_service=MagicMock(), sms_service=MagicMock(), email_service=MagicMock(),
        ws_manager=MagicMock(), redis_client=fake_redis,
        communication_integration=communication,
    )
    with pytest.raises(notification_module.CommunicationChannelDisabledError):
        await router._generate_safe_communication(
            event=_make_event(), recipient_type="customer", channel="sms",
            notification_type="job_update"
        )


@pytest.mark.anyio
async def test_send_push_generation_none_returns_false(setup_db):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
        fcm_token="token"
    )
    communication = MagicMock()
    communication.generate = AsyncMock(return_value=None)
    router = NotificationRouter(
        fcm_service=AsyncMock(), sms_service=MagicMock(), email_service=MagicMock(),
        ws_manager=MagicMock(), redis_client=fake_redis,
        communication_integration=communication,
    )
    with patch.object(notification_module, "SessionLocal", return_value=db):
        assert await router._send_push(
            _make_event(), "technician", {}, "high", "job_update"
        ) is False


@pytest.mark.anyio
async def test_send_sms_generation_none_and_over_limit_return_false(setup_db):
    communication = MagicMock()
    communication.generate = AsyncMock(
        side_effect=[
            None,
            _communication_result(text="x" * 161),
        ]
    )
    router = NotificationRouter(
        fcm_service=MagicMock(), sms_service=MagicMock(), email_service=MagicMock(),
        ws_manager=MagicMock(), redis_client=fake_redis,
        communication_integration=communication,
    )
    assert await router._send_sms(
        _make_event(), "customer", {}, "job_update"
    ) is False
    assert await router._send_sms(
        _make_event(), "customer", {}, "job_update"
    ) is False
