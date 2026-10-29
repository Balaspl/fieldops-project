from __future__ import annotations

from datetime import date, datetime, time, timezone
from types import SimpleNamespace

import pytest
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import InAppNotification, Job, Organization, Technician
from app.services.ai.FieldOpsAI.agents.dispatcher_agent import dispatcher_runtime


class _Session:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def commit(self):
        # Match the SQLAlchemy Session API for this test double.
        return None


def test_offer_job_id_normalizes_graph_and_legacy_state():
    runtime = dispatcher_runtime.DispatcherRuntime
    assert runtime._job_id_from_offer_state({"id": 158}) == 158
    assert runtime._job_id_from_offer_state({"job_id": 158}) == 158
    assert runtime._job_id_from_offer_state({"id": 158, "job_id": 158}) == 158


def test_offer_missing_job_id_fails_with_available_keys():
    with pytest.raises(ValueError, match="available keys=.*service_type"):
        dispatcher_runtime.DispatcherRuntime._job_id_from_offer_state(
            {"service_type": "Plumbing"}
        )


@pytest.mark.parametrize("status", ["CANCELLED", "CANCELED", "COMPLETED", "CLOSED"])
def test_terminal_jobs_are_never_retreated_as_dispatchable(status):
    job = SimpleNamespace(status=status, assigned_technician_id=None)
    assert dispatcher_runtime.DispatcherRuntime._job_is_already_dispatched(job)


@pytest.mark.parametrize("status", ["CREATED", "QUEUED", "UNASSIGNED"])
def test_unassigned_pending_jobs_remain_dispatchable(status):
    job = SimpleNamespace(status=status, assigned_technician_id=None)
    assert not dispatcher_runtime.DispatcherRuntime._job_is_already_dispatched(job)


@pytest.mark.asyncio
async def test_runtime_hands_planning_ranking_to_dispatcher_without_replanning(monkeypatch):
    candidates = [
        {"technician_id": 17, "technician_name": "Guru Tech", "rank": 1, "eligible": True},
        {"technician_id": 18, "technician_name": "Ajay Tech", "rank": 2, "eligible": True},
    ]
    job = SimpleNamespace(
        id=153,
        tenant_id="provider-tenant",
        service_type="Plumbing",
        location="Chennai",
        priority="HIGH",
        status="CREATED",
        assigned_technician_id=None,
        preferred_service_date=date(2099, 10, 27),
        preferred_service_time=time(9),
        preferred_service_timezone="UTC",
    )
    captured = {}

    class _Graph:
        async def start_dispatch(self, state):
            captured.update(state)
            return {"next_action": "WAIT_FOR_RESPONSE", "current_technician_id": 17}

    runtime = dispatcher_runtime.DispatcherRuntime.__new__(dispatcher_runtime.DispatcherRuntime)
    runtime.graph = _Graph()
    monkeypatch.setattr(dispatcher_runtime, "SessionLocal", _Session)
    monkeypatch.setattr(runtime, "_get_job", lambda _db, _job_id: job)
    monkeypatch.setattr(runtime, "_job_is_already_dispatched", lambda _job: False)
    async def fail_if_replanned(*_args):
        raise AssertionError("initial Planning candidates must be handed off directly")

    monkeypatch.setattr(runtime, "request_planning", fail_if_replanned)

    result = await runtime.start_dispatch(153, initial_candidates=candidates)

    assert result["current_technician_id"] == 17
    assert [candidate["technician_id"] for candidate in captured["all_candidates"]] == [17, 18]
    assert captured["candidates"] == captured["all_candidates"]
    assert captured["dispatch_attempt_id"]
    assert job.dispatch_state["next_action"] == "WAIT_FOR_RESPONSE"
    assert job.dispatch_state["current_technician_id"] == 17


@pytest.mark.asyncio
async def test_offer_is_persisted_and_realtime_notification_is_sent(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    db = sessions()
    db.add(Organization(id="provider", name="Provider", slug="provider"))
    db.flush()
    technician = Technician(
        technician_id=17,
        tech_id="tech-17",
        tenant_id="provider",
        technician_name="Guru Tech",
        technician_skill="Plumbing",
        technician_location="Chennai",
        technician_status="AVAILABLE",
        last_ping=datetime.now(timezone.utc),
    )
    job = Job(
        id=153,
        tenant_id="provider",
        customer_tenant_id="provider",
        customer_name="Customer",
        location="Chennai",
        issue_description="Leaking tap",
        priority="HIGH",
        service_type="Plumbing",
        contact_number="0000000000",
        preferred_service_date=date.today(),
        status="CREATED",
    )
    db.add_all([technician, job])
    db.commit()
    db.close()

    monkeypatch.setattr(dispatcher_runtime, "SessionLocal", sessions)
    class _FreshAvailability:
        def get(self, _key):
            return json.dumps({
                "tenant_id": "provider",
                "latitude": 13.08,
                "longitude": 80.27,
                "accuracy": 10,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

    monkeypatch.setattr(dispatcher_runtime, "get_redis_client", lambda: _FreshAvailability())
    sent = []

    async def emit_notification(tech_id, payload):
        sent.append((tech_id, payload))
        return True

    from app.services import socket_manager

    monkeypatch.setattr(socket_manager, "emit_notification", emit_notification)
    runtime = dispatcher_runtime.DispatcherRuntime.__new__(dispatcher_runtime.DispatcherRuntime)

    await runtime.offer_job(
        {"id": 153, "service_type": "Plumbing", "dispatch_attempt_id": "attempt-153"},
        17,
    )
    with pytest.raises(RuntimeError, match="job_already_assigned"):
        await runtime.offer_job(
            {"id": 153, "service_type": "Plumbing", "dispatch_attempt_id": "attempt-153"},
            17,
        )

    with sessions() as verify_db:
        persisted_job = verify_db.query(Job).filter_by(id=153).one()
        persisted_offer = verify_db.query(InAppNotification).filter_by(
            job_id="153",
            recipient_id="tech-17",
            type="JOB_ASSIGNED",
        ).one()
        assert verify_db.query(InAppNotification).filter_by(job_id="153").count() == 1

        assert persisted_job.assigned_technician_id == 17
        assert persisted_job.status == "ASSIGNED"
        assert persisted_offer.tenant_id == "provider"
        assert persisted_offer.status == "UNREAD"
        assert persisted_offer.notification_metadata["dispatch_attempt_id"] == "attempt-153"

    assert len(sent) == 1
    assert sent[0][0] == "tech-17"
    assert sent[0][1]["jobId"] == "153"
    assert sent[0][1]["notification_metadata"]["dispatch_attempt_id"] == "attempt-153"

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_future_job_registers_dispatch_at_one_hour_before_visit(monkeypatch):
    from app import worker

    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as db:
        db.add(Organization(id="provider", name="Provider", slug="provider"))
        db.flush()
        db.add(Job(
            id=154,
            tenant_id="provider",
            customer_tenant_id="provider",
            customer_name="Customer",
            location="Chennai",
            issue_description="Repair",
            priority="HIGH",
            service_type="Plumbing",
            contact_number="0000000000",
            preferred_service_date=date(2026, 10, 27),
            preferred_service_time=time(9),
            preferred_service_timezone="Asia/Kolkata",
            status="CREATED",
        ))
        db.commit()

    class _Scheduler:
        def __init__(self):
            self.job = None

        def add_job(self, func, **kwargs):
            self.job = (func, kwargs)

    test_scheduler = _Scheduler()
    monkeypatch.setattr(worker, "SessionLocal", sessions)
    monkeypatch.setattr(worker, "scheduler", test_scheduler)

    due_at = worker.register_scheduled_dispatch(154, "attempt-154")

    assert due_at.isoformat() == "2026-10-27T02:30:00+00:00"
    assert test_scheduler.job[1]["run_date"] == due_at
    assert test_scheduler.job[1]["id"] == "dispatch_due_job_154"
    assert test_scheduler.job[1]["args"] == [154, "attempt-154"]

    Base.metadata.drop_all(bind=engine)
    engine.dispose()
