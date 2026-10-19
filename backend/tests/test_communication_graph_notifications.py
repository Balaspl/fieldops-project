import asyncio
import logging
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.services.ai.FieldOpsAI.agents.communication_agent_impl import (
    CommunicationAgent,
)
from app.services.ai.FieldOpsAI.agents.communication_agent import graph
from app.services.ai.FieldOpsAI.agents.communication_agent.events import (
    JobEvent,
    event_for_transition,
)
from app.services.ai.FieldOpsAI.agents.communication_agent import service
from app.services.ai.FieldOpsAI.agents.communication_agent.message import build_copy
from app.services.ai.FieldOpsAI.config.agent_config_manager import AgentConfigManager
from app.services.ai.FieldOpsAI.schemas.agent_config import AgentConfig
from app.services.ai.FieldOpsAI.schemas.ai_task import AITask
from app.services.ai.FieldOpsAI.schemas.communication import (
    CommunicationContext,
    CommunicationDecision,
)
from app.services.customer_notification_services import (
    create_customer_job_status_notification,
)
from app.models_legacy import ETAHistory, InAppNotification, Job
from app.services.ai.FieldOpsAI.agents.communication_agent.recipients import Recipient
from app.services.ai.FieldOpsAI.agents.communication_agent.store import (
    upsert_notification,
)
from app.services.ai.FieldOpsAI.agents.communication_agent.channels import (
    claim_delivery,
    idem_key,
)
from app.services.ai.FieldOpsAI.agents.communication_agent.texts import email_content


class FakeSession:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def _dispatch_state(version=2):
    recipient = {
        "role": "customer",
        "id": "customer-user-1",
        "tenant_id": "customer-tenant",
        "channels": ["in_app"],
        "phone": None,
        "email": None,
        "name": "Customer",
    }
    return {
        "event": JobEvent.EN_ROUTE.value,
        "event_version": version,
        "job": {"id": 41, "tenant_id": "provider-tenant"},
        "technician": None,
        "messages": [
            {
                "recipient": recipient,
                "title": "AI title",
                "body": "AI generated status copy",
                "card": {"state": "active"},
                "sms": None,
                "email": None,
            }
        ],
    }


def _patch_agent(monkeypatch, generate):
    monkeypatch.setattr(
        AgentConfigManager,
        "resolve",
        lambda *args, **kwargs: AgentConfig(
            agent_type=AITask.COMMUNICATION,
            tenant_id="customer-tenant",
        ),
    )
    monkeypatch.setattr(CommunicationAgent, "generate", generate)


def test_notification_upsert_index_matches_tenant_aware_conflict_target():
    index = next(
        index
        for index in InAppNotification.__table__.indexes
        if index.name == "uq_notifications_recipient_group"
    )

    assert index.unique is True
    assert [column.name for column in index.columns] == [
        "tenant_id",
        "recipient_role",
        "recipient_id",
        "group_key",
    ]


def test_dispatch_persists_one_customer_card_then_pushes_it(monkeypatch):
    db = FakeSession()
    persisted = []
    pushed = []

    monkeypatch.setattr(graph, "external_channels_enabled", lambda: {"in_app"})
    monkeypatch.setattr(
        graph,
        "upsert_notification",
        lambda *args, **kwargs: persisted.append((args, kwargs)) or "notification-1",
    )
    monkeypatch.setattr(graph, "push_live", lambda *args, **kwargs: pushed.append(args))

    result = graph.dispatch(
        _dispatch_state(),
        {"configurable": {"db": db}},
    )

    assert result["notification_ids"] == ["notification-1"]
    assert len(persisted) == 1
    args, kwargs = persisted[0]
    assert args[1].id == "customer-user-1"
    assert args[1].tenant_id == "customer-tenant"
    assert args[4:6] == ("AI title", "AI generated status copy")
    assert kwargs["version"] == 2
    assert db.commits == 1
    assert len(pushed) == 1
    assert pushed[0][1] == "customer-tenant"
    assert pushed[0][3]["recipient_id"] == "customer-user-1"


def test_dispatch_does_not_publish_when_event_is_stale(monkeypatch):
    db = FakeSession()
    pushed = []
    monkeypatch.setattr(graph, "external_channels_enabled", lambda: {"in_app"})
    monkeypatch.setattr(graph, "upsert_notification", lambda *args, **kwargs: None)
    monkeypatch.setattr(graph, "push_live", lambda *args, **kwargs: pushed.append(args))

    result = graph.dispatch(
        _dispatch_state(version=1),
        {"configurable": {"db": db}},
    )

    assert result["notification_ids"] == []
    assert db.rollbacks == 1
    assert not pushed


def test_dispatch_logs_original_upsert_error_with_consistent_correlation(
    monkeypatch, caplog
):
    db = FakeSession()
    original_error = RuntimeError("database upsert failed")
    monkeypatch.setattr(graph, "external_channels_enabled", lambda: {"in_app"})

    def fail_upsert(*args, **kwargs):
        raise original_error

    monkeypatch.setattr(graph, "upsert_notification", fail_upsert)

    result = graph.dispatch(
        _dispatch_state(),
        {"configurable": {"db": db}},
    )

    assert result["notification_ids"] == []
    assert db.rollbacks == 1
    failure = next(
        record
        for record in caplog.records
        if "notification save failed" in record.message
    )
    assert failure.exc_info[1] is original_error
    assert failure.correlation_id
    assert failure.job_id == "41"
    assert failure.event_type == JobEvent.EN_ROUTE.value
    assert failure.event_version == 2
    assert failure.recipient_role == "customer"


def test_store_rejects_older_event_without_overwriting_card():
    engine = create_engine("sqlite://")
    InAppNotification.__table__.create(engine)
    session = sessionmaker(bind=engine)()
    recipient = SimpleNamespace(
        role="customer",
        id="customer-user-1",
        tenant_id="customer-tenant",
    )
    job = SimpleNamespace(id=41)
    try:
        first_id = upsert_notification(
            session,
            recipient,
            job,
            JobEvent.EN_ROUTE,
            "Newer title",
            "Newer body",
            {},
            version=2,
        )
        session.commit()

        stale_id = upsert_notification(
            session,
            recipient,
            job,
            JobEvent.TECHNICIAN_ACCEPTED,
            "Older title",
            "Older body",
            {},
            version=1,
        )
        session.rollback()

        saved = session.get(InAppNotification, first_id)
        assert stale_id is None
        assert saved.title == "Newer title"
        assert saved.body == "Newer body"
        assert saved.event_version == 2
        assert session.query(InAppNotification).count() == 1
    finally:
        session.close()
        engine.dispose()


def test_store_inserts_then_updates_one_card_for_a_newer_event_version():
    engine = create_engine("sqlite://")
    InAppNotification.__table__.create(engine)
    session = sessionmaker(bind=engine)()
    recipient = SimpleNamespace(
        role="customer",
        id="customer-user-1",
        tenant_id="customer-tenant",
    )
    job = SimpleNamespace(id=41)
    try:
        first_id = upsert_notification(
            session,
            recipient,
            job,
            JobEvent.TECHNICIAN_ACCEPTED,
            "Accepted",
            "Your technician accepted.",
            {},
            version=1,
        )
        session.commit()

        updated_id = upsert_notification(
            session,
            recipient,
            job,
            JobEvent.EN_ROUTE,
            "On the way",
            "Your technician is on the way.",
            {},
            version=2,
        )
        session.commit()

        saved = session.get(InAppNotification, first_id)
        assert updated_id == first_id
        assert saved.title == "On the way"
        assert saved.body == "Your technician is on the way."
        assert saved.event_version == 2
        assert session.query(InAppNotification).count() == 1
    finally:
        session.close()
        engine.dispose()


def test_store_equal_event_replay_returns_card_without_unreading_it():
    engine = create_engine("sqlite://")
    InAppNotification.__table__.create(engine)
    session = sessionmaker(bind=engine)()
    recipient = SimpleNamespace(
        role="customer",
        id="customer-user-1",
        tenant_id="customer-tenant",
    )
    job = SimpleNamespace(id=41)
    try:
        saved_id = upsert_notification(
            session, recipient, job, JobEvent.COMPLETED,
            "Completed", "Finished", {}, version=5,
        )
        session.commit()
        saved = session.get(InAppNotification, saved_id)
        saved.status = "READ"
        session.commit()

        replay_id = upsert_notification(
            session, recipient, job, JobEvent.COMPLETED,
            "Changed title", "Changed body", {}, version=5,
        )

        assert replay_id == saved_id
        assert saved.status == "READ"
        assert saved.title == "Completed"
    finally:
        session.close()
        engine.dispose()


def test_failed_email_delivery_can_be_reclaimed_once():
    engine = create_engine("sqlite://")
    from app.models_legacy import NotificationChannelDelivery

    NotificationChannelDelivery.__table__.create(engine)
    session = sessionmaker(bind=engine)()
    key = "41:completed:customer:tenant-a:user-1:email:5"
    try:
        session.add(NotificationChannelDelivery(
            tenant_id="tenant-a",
            notification_id="notification-1",
            channel="email",
            recipient_id="user-1",
            status="failed",
            attempts=1,
            idempotency_key=key,
        ))
        session.commit()

        reclaimed = claim_delivery(
            session,
            tenant_id="tenant-a",
            notification_id="notification-1",
            channel="email",
            recipient_id="user-1",
            key=key,
        )
        session.commit()
        duplicate = claim_delivery(
            session,
            tenant_id="tenant-a",
            notification_id="notification-1",
            channel="email",
            recipient_id="user-1",
            key=key,
        )

        row = session.query(NotificationChannelDelivery).filter_by(
            idempotency_key=key
        ).one()
        assert reclaimed == row.id
        assert duplicate is None
        assert row.status == "queued"
    finally:
        session.close()
        engine.dispose()


def test_websocket_failure_keeps_committed_notification(monkeypatch):
    db = FakeSession()
    monkeypatch.setattr(graph, "external_channels_enabled", lambda: {"in_app"})
    monkeypatch.setattr(graph, "upsert_notification", lambda *args, **kwargs: "notification-1")

    def fail_push(*args, **kwargs):
        raise RuntimeError("socket unavailable")

    monkeypatch.setattr(graph, "push_live", fail_push)

    result = graph.dispatch(
        _dispatch_state(),
        {"configurable": {"db": db}},
    )

    assert result["notification_ids"] == ["notification-1"]
    assert db.commits == 1
    assert db.rollbacks == 0


def test_generation_failure_fallback_is_persisted_and_published(monkeypatch):
    db = FakeSession()
    persisted = []
    pushed = []
    def fail_generation(self, context):
        raise RuntimeError("provider unavailable")

    _patch_agent(monkeypatch, fail_generation)
    monkeypatch.setattr(graph, "external_channels_enabled", lambda: {"in_app"})
    monkeypatch.setattr(
        graph,
        "upsert_notification",
        lambda *args, **kwargs: persisted.append((args, kwargs)) or "fallback-card",
    )
    monkeypatch.setattr(graph, "push_live", lambda *args, **kwargs: pushed.append(args))

    recipient = _dispatch_state()["messages"][0]["recipient"]
    fallback_title, fallback_body = build_copy(
        JobEvent.EN_ROUTE,
        SimpleNamespace(**recipient),
        SimpleNamespace(id=41, service_type="Plumbing"),
        None,
    )
    message = graph.compose(
        {
            "event": JobEvent.EN_ROUTE.value,
            "job": {"id": 41, "service_type": "Plumbing"},
            "technician": None,
            "recipient": recipient,
        }
    )["messages"][0]
    result = graph.dispatch(
        {
            **_dispatch_state(),
            "messages": [message],
        },
        {"configurable": {"db": db}},
    )

    assert result["notification_ids"] == ["fallback-card"]
    assert len(persisted) == 1
    saved_args, _ = persisted[0]
    assert saved_args[4] == message["title"]
    assert saved_args[5] == message["body"]
    assert (message["title"], message["body"]) == (fallback_title, fallback_body)
    assert db.commits == 1
    assert len(pushed) == 1


def test_dynamic_fallback_is_stable_per_event_and_varies_across_versions():
    recipient = SimpleNamespace(role="customer", id="cust-7", tenant_id="tenant-1", name=None)
    job = SimpleNamespace(id=41, service_type="Plumbing", eta_min=None)
    first = build_copy(JobEvent.EN_ROUTE, recipient, job, None, version=4)
    retry = build_copy(JobEvent.EN_ROUTE, recipient, job, None, version=4)
    later = build_copy(JobEvent.EN_ROUTE, recipient, job, None, version=5)
    completed = build_copy(JobEvent.COMPLETED, recipient, job, None, version=6)

    assert first == retry
    assert later != first
    assert completed[1].lower().find("complete") >= 0 or "wrapped" in completed[1].lower()
    assert "minutes" not in first[1]
    assert "on the way" in first[1].lower() or "heading" in first[1].lower() or "trip" in first[1].lower()


def test_successful_ai_copy_is_contextual_and_persisted(monkeypatch):
    db = FakeSession()
    persisted = []
    pushed = []
    observed_context = []

    def generate(self, context):
        observed_context.append(context)
        return SimpleNamespace(
            output=SimpleNamespace(
                channel="PORTAL",
                title="Maya is nearly there",
                body="Maya is on the way for your plumbing visit, about 12 minutes away.",
            )
        )

    _patch_agent(monkeypatch, generate)
    monkeypatch.setattr(graph, "external_channels_enabled", lambda: {"in_app"})
    monkeypatch.setattr(
        graph,
        "upsert_notification",
        lambda *args, **kwargs: persisted.append((args, kwargs)) or "ai-card",
    )
    monkeypatch.setattr(graph, "push_live", lambda *args, **kwargs: pushed.append(args))

    recipient = _dispatch_state()["messages"][0]["recipient"]
    message = graph.compose(
        {
            "event": JobEvent.EN_ROUTE.value,
            "job": {
                "id": 41,
                "service_type": "Plumbing",
                "customer_name": "Asha",
                "eta_min": 12,
            },
            "technician": {"technician_name": "Maya"},
            "recipient": recipient,
        }
    )["messages"][0]
    result = graph.dispatch(
        {
            **_dispatch_state(),
            "messages": [message],
        },
        {"configurable": {"db": db}},
    )

    assert result["notification_ids"] == ["ai-card"]
    context = observed_context[0]
    assert context.notification_type == "en_route"
    assert context.customer_name == "Customer"
    assert context.technician_name == "Maya"
    assert context.eta == "about 12 minutes"
    saved_args, _ = persisted[0]
    assert saved_args[4] == "Maya is nearly there"
    assert saved_args[5].startswith(
        "Maya is on the way for your plumbing visit, about 12 minutes away."
    )
    assert "Track live" in saved_args[5]
    assert len(persisted) == 1
    assert len(pushed) == 1


def test_invalid_ai_channel_uses_approved_fallback(monkeypatch):
    def generate(self, context):
        return SimpleNamespace(
            output=SimpleNamespace(
                channel="PUSH",
                title="Wrong channel",
                body="This output is not valid for a portal notification.",
            )
        )

    _patch_agent(monkeypatch, generate)
    recipient = _dispatch_state()["messages"][0]["recipient"]
    expected = build_copy(
        JobEvent.EN_ROUTE,
        SimpleNamespace(**recipient),
        SimpleNamespace(id=41, service_type=None, eta_min=None),
        None,
    )

    message = graph.compose(
        {
            "event": JobEvent.EN_ROUTE.value,
            "job": {"id": 41, "service_type": None},
            "technician": None,
            "recipient": recipient,
        }
    )["messages"][0]

    assert (message["title"], message["body"]) == expected


def test_missing_optional_customer_context_does_not_crash(monkeypatch):
    observed_context = []

    def generate(self, context):
        observed_context.append(context)
        return SimpleNamespace(
            output=SimpleNamespace(
                channel="PORTAL",
                title=None,
                body="Your technician is on the way.",
            )
        )

    _patch_agent(monkeypatch, generate)
    recipient = _dispatch_state()["messages"][0]["recipient"]
    message = graph.compose(
        {
            "event": JobEvent.EN_ROUTE.value,
            "job": {"id": 41, "service_type": None},
            "technician": None,
            "recipient": recipient,
        }
    )["messages"][0]

    assert observed_context[0].technician_name is None
    assert observed_context[0].eta is None
    assert observed_context[0].job_title is None
    assert message["body"].startswith("Your technician is on the way.")
    assert "Track live" in message["body"]


def test_communication_agent_template_fallback_is_not_logged_as_ai(
    monkeypatch, caplog
):
    caplog.set_level(logging.INFO, logger=graph.logger.name)
    def generate(self, context):
        self.last_generation_used_fallback = True
        return SimpleNamespace(
            output=SimpleNamespace(
                channel="PORTAL",
                title="Validated fallback title",
                body="Validated fallback body.",
            )
        )

    _patch_agent(monkeypatch, generate)
    recipient = _dispatch_state()["messages"][0]["recipient"]
    message = graph.compose(
        {
            "event": JobEvent.EN_ROUTE.value,
            "event_version": 9,
            "correlation_id": "corr-9",
            "job": {"id": 41, "service_type": "Plumbing"},
            "technician": None,
            "recipient": recipient,
        }
    )["messages"][0]

    assert message["title"] == "Validated fallback title"
    records = [
        record
        for record in caplog.records
        if record.message == "Communication Agent produced customer copy"
    ]
    assert records
    assert records[-1].generation_source == "approved_fallback"
    assert records[-1].used_fallback is True
    assert records[-1].event_version == 9
    assert records[-1].correlation_id == "corr-9"


def test_legacy_customer_helper_cannot_stage_or_publish_a_card():
    class MustNotBeUsed:
        def __getattr__(self, name):
            raise AssertionError(f"legacy helper accessed db.{name}")

    assert (
        create_customer_job_status_notification(
            MustNotBeUsed(),
            SimpleNamespace(id=41),
            "EN_ROUTE",
        )
        is None
    )


def test_prompt_legacy_in_app_shape_validates_to_portal_output():
    decision = CommunicationDecision.model_validate(
        {
            "channel": "IN_APP",
            "title": "Technician is on the way",
            "subject": None,
            "message": "Maya is travelling to your plumbing visit.",
            "tone": "FRIENDLY",
            "confidence": 0.9,
        }
    )

    assert decision.channel == "IN_APP"
    assert decision.output.channel == "PORTAL"
    assert decision.output.title == "Technician is on the way"
    assert decision.output.body == "Maya is travelling to your plumbing visit."

    with pytest.raises(ValueError):
        CommunicationDecision.model_validate(
            {
                "channel": "PORTAL",
                "title": "Unsupported outer channel",
                "subject": None,
                "message": "Body",
                "tone": "FRIENDLY",
                "confidence": 0.9,
            }
        )


def test_communication_generation_calls_orchestrator_with_decision_schema():
    orchestrator = MagicMock()
    orchestrator.execute.return_value = CommunicationDecision.model_validate(
        {
            "channel": "IN_APP",
            "title": "A fresh update",
            "subject": None,
            "message": "Your technician is on the way.",
            "tone": "FRIENDLY",
            "confidence": 0.9,
        }
    )
    agent = CommunicationAgent(
        config=AgentConfig(
            agent_type=AITask.COMMUNICATION,
            tenant_id="customer-tenant",
        ),
        orchestrator=orchestrator,
    )

    result = asyncio.run(
        agent._generate_with_ai(
            CommunicationContext(
                job_id="41",
                notification_type="en_route",
                recipient_type="CUSTOMER",
                channel="IN_APP",
                job_status="EN_ROUTE",
            )
        )
    )

    assert result.output.body == "Your technician is on the way."
    orchestrator.execute.assert_called_once()
    call_kwargs = orchestrator.execute.call_args.kwargs
    assert call_kwargs["task"] == AITask.COMMUNICATION
    assert call_kwargs["response_schema"] is CommunicationDecision


@pytest.mark.parametrize(
    ("old_status", "new_status", "expected"),
    [
        ("ASSIGNED", "ACCEPTED", JobEvent.TECHNICIAN_ACCEPTED),
        ("ACCEPTED", "EN_ROUTE", JobEvent.EN_ROUTE),
        ("EN_ROUTE", "IN_PROGRESS", JobEvent.SERVICE_STARTED),
        ("IN_PROGRESS", "COMPLETED", JobEvent.COMPLETED),
    ],
)
def test_technician_portal_statuses_map_to_customer_events(
    old_status, new_status, expected
):
    assert event_for_transition(old_status, new_status) is expected


def test_service_passes_correlation_id_through_graph(monkeypatch):
    invoke = MagicMock(return_value={"notification_ids": ["card-1"]})
    monkeypatch.setattr(
        service,
        "communication_graph",
        SimpleNamespace(invoke=invoke),
    )
    result = service.handle(
        FakeSession(),
        job_id=41,
        event=JobEvent.EN_ROUTE,
        version=8,
        correlation_id="corr-status-8",
    )

    assert result == ["card-1"]
    graph_state = invoke.call_args.args[0]
    assert graph_state["event_version"] == 8
    assert graph_state["correlation_id"] == "corr-status-8"


def test_booking_and_assignment_events_map_to_email_lifecycle():
    assert event_for_transition("CREATED", "ASSIGNED") is JobEvent.TECHNICIAN_ASSIGNED
    assert event_for_transition("ASSIGNED", "ACCEPTED") is JobEvent.TECHNICIAN_ACCEPTED


def test_email_delivery_key_is_stable_for_event_retries():
    recipient = Recipient(
        role="customer",
        id="customer-1",
        tenant_id="tenant-a",
    )
    first = idem_key(41, JobEvent.COMPLETED, recipient, "email", 8)
    retry = idem_key(41, JobEvent.COMPLETED, recipient, "email", 8)
    later_event = idem_key(41, JobEvent.COMPLETED, recipient, "email", 9)

    assert first == retry
    assert first != later_event


def test_invoice_email_uses_persisted_values_and_escapes_html():
    job = SimpleNamespace(
        id=41,
        service_type="<script>bad()</script>",
        customer_name="<img src=x onerror=alert(1)>",
        location="<svg onload=alert(1)>",
        completed_at="2026-10-17T10:00:00+00:00",
        closure_id=12,
        invoice_number="12",
        invoice_total=105.0,
        currency="INR",
        invoice_link="https://fieldops.example/?tab=cust_invoices",
    )

    message = email_content(
        "Invoice ready",
        "Your invoice is ready.",
        job,
        None,
        JobEvent.INVOICE_READY,
    )

    assert "Invoice number: 12" in message["plain_text"]
    assert "Total amount: INR 105.00" in message["plain_text"]
    assert "Invoice number: 12" in message["plain_text"]
    assert job.invoice_link in message["html_body"]
    assert "<script>" not in message["html_body"]
    assert "<img" not in message["html_body"]
    assert "<svg" not in message["html_body"]
    assert "&lt;script&gt;" in message["html_body"]


def test_booking_email_has_persisted_details_and_escapes_html():
    job = SimpleNamespace(
        id=42,
        customer_name="Ava <script>alert(1)</script>",
        service_type="Repair & service",
        location="12 <b>Main Street</b>",
        preferred_service_date="2026-10-17",
        status="CREATED",
    )

    message = email_content(
        "Booked",
        "Request received.",
        job,
        None,
        JobEvent.JOB_CREATED,
    )

    assert message["subject"] == "Your FieldOps service is booked!"
    assert "Booking ID: #42" in message["plain_text"]
    assert "Location: 12 <b>Main Street</b>" in message["plain_text"]
    assert "Preferred visit: 2026-10-17" in message["plain_text"]
    assert "<script>" not in message["html_body"]
    assert "<b>Main Street</b>" not in message["html_body"]


def test_invoice_event_loads_finalized_closure_and_authenticated_portal_link(
    monkeypatch,
):
    from datetime import datetime, timezone

    from app.models.job_closure import JobClosure
    from app.models.payment_status import JobPaymentStatus

    job = SimpleNamespace(
        id=41,
        tenant_id="provider-tenant",
        status="COMPLETED",
        service_type="Repair",
        customer_name="Customer",
        assigned_technician_id=None,
        created_at=None,
        preferred_service_date=None,
        preferred_time=None,
        completed_at=None,
        cancellation_reason=None,
        work_report="Fixed",
        share_token=None,
        share_token_expires_at=None,
        location="Chennai",
    )
    closure = SimpleNamespace(
        id=12,
        job_id=41,
        tenant_id="provider-tenant",
        subtotal=100.0,
        completed_at=datetime(2026, 10, 17, tzinfo=timezone.utc),
    )

    class Query:
        def __init__(self, result):
            self.result = result
        def filter(self, *args, **kwargs): return self
        def order_by(self, *args, **kwargs): return self
        def first(self): return self.result

    class DB:
        def get(self, model, key):
            return job if model is Job else None
        def query(self, model):
            return Query({
                ETAHistory: None,
                JobClosure: closure,
                JobPaymentStatus: None,
            }[model])

    monkeypatch.setenv("FRONTEND_BASE_URL", "https://fieldops.example")
    monkeypatch.setattr(
        graph,
        "resolve_recipients",
        lambda *args: [Recipient(
            role="customer", id="customer-1", tenant_id="customer-tenant",
            channels=["in_app", "email"], email="customer@example.test",
            name="Customer",
        )],
    )

    state = graph.load(
        {"job_id": 41, "event": JobEvent.INVOICE_READY.value, "event_version": 9},
        {"configurable": {"db": DB()}},
    )

    assert state["job"]["invoice_number"] == "12"
    assert state["job"]["invoice_total"] == 105.0
    assert state["job"]["currency"] == "INR"
    assert state["job"]["completed_at"] == closure.completed_at.isoformat()
    assert state["job"]["invoice_link"] == (
        "https://fieldops.example/?tab=cust_invoices"
    )
    assert state["recipients"][0]["email"] == "customer@example.test"


def test_invoice_event_without_finalized_closure_has_no_recipients(monkeypatch):
    from app.models.job_closure import JobClosure

    job = SimpleNamespace(
        id=41,
        tenant_id="provider-tenant",
        status="COMPLETED",
        service_type="Repair",
        customer_name="Customer",
        assigned_technician_id=None,
        created_at=None,
        preferred_service_date=None,
        preferred_time=None,
        completed_at=None,
        cancellation_reason=None,
        work_report=None,
        share_token=None,
        share_token_expires_at=None,
        location="Chennai",
    )

    class Query:
        def filter(self, *args, **kwargs): return self
        def order_by(self, *args, **kwargs): return self
        def first(self): return None

    class DB:
        def get(self, model, key): return job if model is Job else None
        def query(self, model): return Query()

    monkeypatch.setattr(graph, "resolve_recipients", lambda *args: [])
    state = graph.load(
        {"job_id": 41, "event": JobEvent.INVOICE_READY.value, "event_version": 9},
        {"configurable": {"db": DB()}},
    )
    assert state["recipients"] == []
    assert state["job"]["closure_id"] is None


def test_committed_technician_status_changes_upsert_one_customer_card(
    monkeypatch,
):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Job.__table__.create(engine)
    ETAHistory.__table__.create(engine)
    InAppNotification.__table__.create(engine)
    SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)
    db = SessionFactory()
    pushes = []
    generated_contexts = []
    generation = {"fail": False}

    class InertThread:
        def __init__(self, *, target, **kwargs):
            self.target = target

        def start(self):
            # This test invokes the communication service explicitly below.
            # Keep the model listener's unrelated background dispatch inert.
            return None

    monkeypatch.setattr("threading.Thread", InertThread)

    monkeypatch.setattr(
        graph,
        "resolve_recipients",
        lambda *args: [
            Recipient(
                role="customer",
                id="customer-user-1",
                tenant_id="customer-tenant",
                channels=["in_app"],
                name="Asha",
            )
        ],
    )
    monkeypatch.setattr(graph, "external_channels_enabled", lambda: {"in_app"})
    monkeypatch.setattr(graph, "push_live", lambda *args, **kwargs: pushes.append(args))
    monkeypatch.setattr(
        AgentConfigManager,
        "resolve",
        lambda *args, **kwargs: AgentConfig(
            agent_type=AITask.COMMUNICATION,
            tenant_id="customer-tenant",
        ),
    )
    monkeypatch.setattr(
        "app.tasks.process_job_status_transition_task.delay",
        lambda *args, **kwargs: None,
    )

    def generate(self, context):
        generated_contexts.append(context)
        if generation["fail"]:
            raise RuntimeError("simulated provider outage")
        self.last_generation_used_fallback = False
        return SimpleNamespace(
            output=SimpleNamespace(
                channel="PORTAL",
                title="Asha, Maya has accepted your repair",
                body="Maya has accepted your plumbing repair. We’ll keep you posted.",
            )
        )

    monkeypatch.setattr(CommunicationAgent, "generate", generate)

    from app.context import correlation_id_ctx

    correlation_token = correlation_id_ctx.set("corr-live-job-41")
    try:
        db.add(
            Job(
                id=41,
                tenant_id="provider-tenant",
                customer_tenant_id="customer-tenant",
                customer_id="customer-user-1",
                customer_name="Asha",
                location="Chennai",
                issue_description="Leaking tap",
                priority="MEDIUM",
                service_type="Plumbing",
                contact_number="9876543210",
                preferred_service_date=date.today(),
                status="ASSIGNED",
            )
        )
        db.commit()

        job = db.get(Job, 41)
        job.status = "ACCEPTED"
        db.commit()
        service.handle(
            db,
            41,
            JobEvent.TECHNICIAN_ACCEPTED,
            version=1,
            correlation_id="corr-live-job-41",
        )

        saved = db.query(InAppNotification).all()
        assert len(saved) == 1
        assert saved[0].title == "Asha, Maya has accepted your repair"
        assert saved[0].body.startswith("Maya has accepted your plumbing repair")
        assert saved[0].customer_user_id == "customer-user-1"
        assert saved[0].tenant_id == "customer-tenant"
        assert saved[0].event_version == 1
        assert len(pushes) == 1
        assert generated_contexts[0].correlation_id == "corr-live-job-41"

        generation["fail"] = True
        job.status = "EN_ROUTE"
        db.commit()
        service.handle(
            db,
            41,
            JobEvent.EN_ROUTE,
            version=2,
            correlation_id="corr-live-job-41",
        )

        # The upsert is a Core statement, so expire the ORM identity-map copy
        # before asserting that the persisted row reflects the newer version.
        db.expire_all()
        saved = db.query(InAppNotification).all()
        assert len(saved) == 1
        assert saved[0].event_version == 2
        expected_fallback = build_copy(
            JobEvent.EN_ROUTE,
            SimpleNamespace(
                role="customer",
                id="customer-user-1",
                tenant_id="customer-tenant",
                channels=["in_app"],
                name="Asha",
                phone=None,
                email=None,
            ),
            SimpleNamespace(
                id=41,
                service_type="Plumbing",
                customer_name="Asha",
                eta_min=None,
            ),
            None,
        )
        assert (saved[0].title, saved[0].body) == (
            "Your technician is on the way 📍",
            (
                "Your technician is heading to your service visit. "
                "The toolbox is officially en route! "
                "Tap Track live to follow the visit 👀"
            ),
        )
        assert len(pushes) == 2
    finally:
        correlation_id_ctx.reset(correlation_token)
        db.close()
        engine.dispose()
