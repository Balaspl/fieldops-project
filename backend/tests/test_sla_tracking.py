import pytest
import json
from datetime import datetime, timedelta, timezone, date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from unittest.mock import patch, MagicMock

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
from app.models import Job, AuditEvent
from app.services.sla_service import SLAService
from app.tasks import process_job_status_transition_task, broadcast_sla_countdown

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    fake_redis.flushall()
    
    def run_sync(
        job_id,
        old_status,
        new_status,
        actor_id,
        actor_role,
        reason=None,
        correlation_id=None,
        event_version=None,
        technician_id=None,
    ):
        process_job_status_transition_task(
            job_id,
            old_status,
            new_status,
            actor_id,
            actor_role,
            reason,
            correlation_id,
            event_version,
            technician_id,
        )

    async def fake_route(*args, **kwargs):
        pass

    with patch("app.tasks.process_job_status_transition_task.delay", side_effect=run_sync) as mock_delay, \
         patch("app.services.notification_services.NotificationRouter.route", new=fake_route):
        yield
        fake_redis.flushall()

def test_sla_timer_lifecycle_starts_pauses_resumes_clears(setup_db):
    db = TestingSessionLocal()
    
    # Create job with 1 hour deadline
    deadline = datetime.now(timezone.utc) + timedelta(hours=1)
    job = Job(
        id=101,
        customer_name="John Doe",
        location="123 Main St",
        issue_description="Leak repair",
        priority="P2",
        service_type="Plumbing",
        contact_number="+15555555555",
        preferred_service_date=date.today(),
        status="ASSIGNED",
        sla_deadline=deadline,
        tenant_id="tenant-1",
        assigned_technician_id=88,
        gps_active=True
    )
    db.add(job)
    db.commit()
    
    sla = SLAService()
    
    # 1. Transition to EN_ROUTE -> Should start SLA timer
    job.transition("EN_ROUTE", actor_id="tech-1", actor_role="technician")
    db.commit()
    
    # Verify SLA timer started in Redis
    state = sla.get_sla_state("101")
    assert state is not None
    assert state["status"] == "active"
    assert state["remaining_seconds"] > 0
    assert state["remaining_seconds"] <= 3600
    
    # 2. Transition to ON_SITE -> Should pause SLA timer
    job.transition("ON_SITE", actor_id="tech-1", actor_role="technician")
    db.commit()
    
    state = sla.get_sla_state("101")
    assert state is not None
    assert state["status"] == "paused"
    assert state["paused_at"] is not None
    
    # Save frozen remaining time
    paused_remaining = state["remaining_seconds"]
    
    # 3. Transition back to EN_ROUTE (resumes timer, shifts deadline)
    # Mock delay so time passes
    import time
    time.sleep(1) # sleep 1 second to verify pause shift
    
    job.transition("EN_ROUTE", actor_id="tech-1", actor_role="technician")
    db.commit()
    
    state = sla.get_sla_state("101")
    assert state is not None
    assert state["status"] == "active"
    assert state["paused_at"] is None
    
    # 4. Transition to COMPLETED -> Should clear SLA timer
    # First arrive on site again
    job.transition("ON_SITE", actor_id="tech-1", actor_role="technician")
    db.commit()
    job.work_report = "Fixed leakage"
    db.commit()
    job.transition("COMPLETED", actor_id="tech-1", actor_role="technician")
    db.commit()
    
    state = sla.get_sla_state("101")
    assert state is None
    db.close()

def test_sla_urgency_indicators_critical_and_breached(setup_db):
    sla = SLAService()
    
    # 1. Critical Warning: less than 15 minutes (900 seconds) remaining
    deadline_critical = datetime.now(timezone.utc) + timedelta(minutes=10)
    sla.start_sla_timer("102", deadline_critical)
    
    state = sla.get_sla_state("102")
    assert state["is_critical"] is True
    assert state["is_breached"] is False
    
    # 2. Breach Alert: deadline < now
    deadline_breached = datetime.now(timezone.utc) - timedelta(minutes=5)
    sla.start_sla_timer("103", deadline_breached)
    
    state = sla.get_sla_state("103")
    assert state["is_critical"] is False
    assert state["is_breached"] is True

def test_sla_milestone_logging_to_audit_events(setup_db):
    db = TestingSessionLocal()
    
    # Pre-populate job for milestone lookup
    job = Job(
        id=105,
        customer_name="Milestone Job",
        location="123 Road",
        issue_description="Problem",
        priority="P2",
        service_type="HVAC",
        contact_number="+15555555555",
        preferred_service_date=date.today(),
        status="ASSIGNED",
        tenant_id="tenant-1"
    )
    db.add(job)
    db.commit()
    
    sla = SLAService()
    
    # Set SLA start such that 60% of SLA duration is elapsed
    started_at = datetime.now(timezone.utc) - timedelta(minutes=60)
    deadline = datetime.now(timezone.utc) + timedelta(minutes=40)
    
    # Manually populate Redis state with 60% elapsed time
    state = {
        "job_id": "105",
        "sla_deadline": deadline.isoformat(),
        "status": "active",
        "started_at": started_at.isoformat(),
        "paused_at": None,
        "remaining_seconds": 2400,
        "elapsed_percentage": 60.0,
        "is_breached": False,
        "is_critical": False,
        "milestone_reached": None
    }
    fake_redis.setex("sla:105", 3600, json.dumps(state))
    
    # Retrieve state which should trigger 50% milestone event
    state_updated = sla.get_sla_state("105")
    assert state_updated["milestone_reached"] == "50%"
    
    # Check AuditEvent created for milestone
    audit = db.query(AuditEvent).filter(AuditEvent.job_id == "105", AuditEvent.event_type == "SLA_MILESTONE").first()
    assert audit is not None
    assert "50% SLA milestone elapsed" in audit.reason
    db.close()
