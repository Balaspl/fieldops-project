from datetime import date, datetime, timezone
from contextlib import nullcontext

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Job, Organization
from app.services.dispatch_scheduling import dispatch_due_at, is_dispatch_due


def test_date_only_visit_uses_one_hour_lead_in_organization_timezone():
    due_at = dispatch_due_at(date(2026, 10, 27), "Asia/Kolkata")
    assert due_at == datetime(2026, 10, 27, 2, 30, tzinfo=timezone.utc)


def test_future_visit_is_not_dispatched_early_and_overdue_visit_is_due():
    due_at = dispatch_due_at(date(2026, 10, 27), "Asia/Kolkata")
    assert not is_dispatch_due(date(2026, 10, 27), "Asia/Kolkata", due_at.replace(hour=1))
    assert is_dispatch_due(date(2026, 10, 27), "Asia/Kolkata", due_at)


def test_online_retry_does_not_dispatch_preexisting_jobs(monkeypatch):
    from app import worker

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as db:
        db.add_all([
            Organization(id="provider-a", name="Provider A", slug="provider-a"),
            Organization(id="provider-b", name="Provider B", slug="provider-b"),
        ])
        db.flush()
        for job_id, tenant_id in ((701, "provider-a"), (702, "provider-b")):
            db.add(Job(
                id=job_id,
                tenant_id=tenant_id,
                customer_tenant_id=tenant_id,
                customer_name="Customer",
                location="Chennai",
                issue_description="Repair",
                priority="HIGH",
                service_type="Plumbing",
                contact_number="0000000000",
                preferred_service_date=date(2099, 10, 27),
                status="CREATED",
            ))
        db.commit()

    started = []

    class _Runtime:
        async def start_dispatch(self, job_id, dispatch_attempt_id):
            started.append((job_id, dispatch_attempt_id))
            return {"status": "PENDING_RETRY"}

    monkeypatch.setattr(worker, "SessionLocal", sessions)
    monkeypatch.setattr(worker, "with_job_lock", lambda _job_id: nullcontext())
    monkeypatch.setattr(worker, "get_dispatcher_runtime", lambda: _Runtime())

    worker.dispatch_pending_jobs_for_tenant("provider-a")

    assert started == []
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
