import pytest
import time
import json
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from app.main import app
from app.models import Job, Technician, GPSPing, GPSRejectedPingLog, GPSPurgeAuditLog
from app.database import Base, get_db
from app.redis_client import get_redis_client
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from app.celery_app import celery_app

# Force celery tasks to run synchronously in tests
celery_app.conf.update(task_always_eager=True)

# Setup test DB
SQLALCHEMY_DATABASE_URL = "sqlite://"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

# Mock Redis class to control Redis availability and states
class MockRedis:
    def __init__(self):
        self.data = {}
        self.ttls = {}
        self.fail = False
        self.failures_triggered = 0

    def exists(self, key):
        if self.fail:
            self.failures_triggered += 1
            raise Exception("Redis Connection Error")
        return key in self.data

    def get(self, key):
        if self.fail:
            self.failures_triggered += 1
            raise Exception("Redis Connection Error")
        return self.data.get(key)

    def set(self, key, value, ex=None):
        if self.fail:
            self.failures_triggered += 1
            raise Exception("Redis Connection Error")
        self.data[key] = str(value)
        if ex:
            self.ttls[key] = time.time() + ex

    def setex(self, key, seconds, value):
        if self.fail:
            self.failures_triggered += 1
            raise Exception("Redis Connection Error")
        self.data[key] = str(value)
        self.ttls[key] = time.time() + seconds

    def ttl(self, key):
        if self.fail:
            self.failures_triggered += 1
            raise Exception("Redis Connection Error")
        if key not in self.data:
            return -2
        expiration = self.ttls.get(key)
        if not expiration:
            return -1
        remaining = int(expiration - time.time())
        return remaining if remaining > 0 else 0

    def delete(self, key):
        if self.fail:
            self.failures_triggered += 1
            raise Exception("Redis Connection Error")
        if key in self.data:
            del self.data[key]
        if key in self.ttls:
            del self.ttls[key]

    def keys(self, pattern):
        if self.fail:
            self.failures_triggered += 1
            raise Exception("Redis Connection Error")
        import fnmatch
        return [k for k in self.data.keys() if fnmatch.fnmatch(k, pattern)]

    def rpush(self, key, value):
        if self.fail:
            self.failures_triggered += 1
            raise Exception("Redis Connection Error")
        if key not in self.data:
            self.data[key] = []
        if not isinstance(self.data[key], list):
            self.data[key] = [self.data[key]]
        self.data[key].append(value)

    def flushall(self):
        self.data.clear()
        self.ttls.clear()

mock_redis = MockRedis()

def override_get_redis():
    return mock_redis

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db(monkeypatch):
    monkeypatch.setattr("app.database.SessionLocal", TestingSessionLocal)
    monkeypatch.setattr("app.tasks.SessionLocal", TestingSessionLocal)
    monkeypatch.setattr("app.redis_client.redis_manager", mock_redis)
    monkeypatch.setattr("app.redis_client.get_redis_client", lambda: mock_redis)

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    
    # Cleanup tables
    db.query(GPSPing).delete()
    db.query(Job).delete()
    db.query(Technician).delete()
    db.query(GPSRejectedPingLog).delete()
    db.query(GPSPurgeAuditLog).delete()
    db.commit()
    
    # Reset mock redis
    mock_redis.flushall()
    mock_redis.fail = False
    mock_redis.failures_triggered = 0
    
    # Reset global circuit breaker count
    from app.routes import gps
    gps.redis_failures_count = 0
    
    yield db
    db.close()

@pytest.fixture(autouse=True)
def apply_overrides():
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis_client] = override_get_redis
    yield
    app.dependency_overrides.clear()


def test_first_ping_accepted(setup_db):
    db = setup_db
    tech = Technician(tech_id="tech-1", technician_name="Tech 1", technician_skill="HVAC", technician_location="0,0", tenant_id="tenant-1")
    db.add(tech)
    db.commit()
    db.refresh(tech)

    job = Job(id=101, customer_name="Alice", location="1,1", issue_description="Leak", priority="HIGH", service_type="Plumbing", contact_number="123456", status="ASSIGNED", assigned_technician_id=tech.technician_id, tenant_id="tenant-1", preferred_service_date=datetime.now().date())
    db.add(job)
    db.commit()
    db.refresh(job)

    payload = {
        "technician_id": "tech-1",
        "job_id": "101",
        "latitude": 12.34,
        "longitude": 56.78,
        "timestamp": "2026-06-25T12:00:00Z"
    }

    response = client.post("/api/v1/gps/ping", headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token-admin"}, json=payload)
    assert response.status_code == 201
    assert response.json()["status"] == "stored"


def test_second_ping_within_30s_rejected(setup_db):
    db = setup_db
    tech = Technician(tech_id="tech-1", technician_name="Tech 1", technician_skill="HVAC", technician_location="0,0", tenant_id="tenant-1")
    db.add(tech)
    db.commit()
    db.refresh(tech)

    job = Job(id=101, customer_name="Alice", location="1,1", issue_description="Leak", priority="HIGH", service_type="Plumbing", contact_number="123456", status="ASSIGNED", assigned_technician_id=tech.technician_id, tenant_id="tenant-1", preferred_service_date=datetime.now().date())
    db.add(job)
    db.commit()
    db.refresh(job)

    payload = {
        "technician_id": "tech-1",
        "job_id": "101",
        "latitude": 12.34,
        "longitude": 56.78,
        "timestamp": "2026-06-25T12:00:00Z"
    }

    # Ping 1
    response = client.post("/api/v1/gps/ping", headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token-admin"}, json=payload)
    assert response.status_code == 201

    # Ping 2 (within 30s)
    response = client.post("/api/v1/gps/ping", headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token-admin"}, json=payload)
    assert response.status_code == 429
    data = response.json()
    assert data["detail"] == "GPS ping interval minimum 30 seconds"
    assert data["status"] == 429
    assert response.headers.get("Retry-After") is not None

    # Check rejected logs
    logs = db.query(GPSRejectedPingLog).all()
    assert len(logs) == 1
    assert logs[0].reason == "GPS ping interval minimum 30 seconds"


def test_second_ping_after_30s_accepted(setup_db):
    db = setup_db
    tech = Technician(tech_id="tech-1", technician_name="Tech 1", technician_skill="HVAC", technician_location="0,0", tenant_id="tenant-1")
    db.add(tech)
    db.commit()
    db.refresh(tech)

    job = Job(id=101, customer_name="Alice", location="1,1", issue_description="Leak", priority="HIGH", service_type="Plumbing", contact_number="123456", status="ASSIGNED", assigned_technician_id=tech.technician_id, tenant_id="tenant-1", preferred_service_date=datetime.now().date())
    db.add(job)
    db.commit()
    db.refresh(job)

    payload = {
        "technician_id": "tech-1",
        "job_id": "101",
        "latitude": 12.34,
        "longitude": 56.78,
        "timestamp": "2026-06-25T12:00:00Z"
    }

    # Ping 1
    response = client.post("/api/v1/gps/ping", headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token-admin"}, json=payload)
    assert response.status_code == 201

    # Simulate 30s expiry by deleting the Redis key
    mock_redis.delete("gps:interval:tenant-1:tech-1:101")

    # Ping 2 (allowed now)
    response = client.post("/api/v1/gps/ping", headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token-admin"}, json=payload)
    assert response.status_code == 201


def test_redis_failure_triggers_db_fallback(setup_db):
    db = setup_db
    tech = Technician(tech_id="tech-1", technician_name="Tech 1", technician_skill="HVAC", technician_location="0,0", tenant_id="tenant-1")
    db.add(tech)
    db.commit()
    db.refresh(tech)

    job = Job(id=101, customer_name="Alice", location="1,1", issue_description="Leak", priority="HIGH", service_type="Plumbing", contact_number="123456", status="ASSIGNED", assigned_technician_id=tech.technician_id, tenant_id="tenant-1", preferred_service_date=datetime.now().date())
    db.add(job)
    db.commit()
    db.refresh(job)

    payload = {
        "technician_id": "tech-1",
        "job_id": "101",
        "latitude": 12.34,
        "longitude": 56.78,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    # Ping 1 (normal success, writes to DB)
    response = client.post("/api/v1/gps/ping", headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token-admin"}, json=payload)
    assert response.status_code == 201

    # Force Redis failure
    mock_redis.fail = True

    # Ping 2 (within 30s) -> Should query DB, find last ping <30s, reject with fallback mode
    response = client.post("/api/v1/gps/ping", headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token-admin"}, json=payload)
    assert response.status_code == 429
    data = response.json()
    assert data["detail"] == "GPS ping interval minimum 30 seconds (fallback mode)"
    assert data["status"] == 429
    assert response.headers.get("Retry-After") is not None


def test_db_fallback_accepts_after_30s(setup_db):
    db = setup_db
    tech = Technician(tech_id="tech-1", technician_name="Tech 1", technician_skill="HVAC", technician_location="0,0", tenant_id="tenant-1")
    db.add(tech)
    db.commit()
    db.refresh(tech)

    job = Job(id=101, customer_name="Alice", location="1,1", issue_description="Leak", priority="HIGH", service_type="Plumbing", contact_number="123456", status="ASSIGNED", assigned_technician_id=tech.technician_id, tenant_id="tenant-1", preferred_service_date=datetime.now().date())
    db.add(job)
    db.commit()
    db.refresh(job)
    
    # Store old ping in DB (35s ago)
    old_time = datetime.now(timezone.utc) - timedelta(seconds=35)
    db_ping = GPSPing(
        id="ping-old-123",
        technician_id="tech-1",
        job_id="101",
        latitude=12.34,
        longitude=56.78,
        timestamp=old_time,
        tenant_id="tenant-1"
    )
    db.add(db_ping)
    db.commit()

    # Force Redis failure
    mock_redis.fail = True

    payload = {
        "technician_id": "tech-1",
        "job_id": "101",
        "latitude": 12.34,
        "longitude": 56.78,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    # Ping should be accepted since last ping was > 30s ago
    response = client.post("/api/v1/gps/ping", headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token-admin"}, json=payload)
    assert response.status_code == 201


def test_circuit_breaker_after_3_redis_failures(setup_db):
    from app.routes import gps
    gps.redis_failures_count = 0
    mock_redis.fail = True

    db = setup_db
    tech = Technician(tech_id="tech-1", technician_name="Tech 1", technician_skill="HVAC", technician_location="0,0", tenant_id="tenant-1")
    db.add(tech)
    db.commit()
    db.refresh(tech)

    job = Job(id=101, customer_name="Alice", location="1,1", issue_description="Leak", priority="HIGH", service_type="Plumbing", contact_number="123456", status="ASSIGNED", assigned_technician_id=tech.technician_id, tenant_id="tenant-1", preferred_service_date=datetime.now().date())
    db.add(job)
    db.commit()
    db.refresh(job)

    payload = {
        "technician_id": "tech-1",
        "job_id": "101",
        "latitude": 12.34,
        "longitude": 56.78,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    # Execute 3 calls, each should fail Redis connection and increment failure counter
    client.post("/api/v1/gps/ping", headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token-admin"}, json=payload)
    client.post("/api/v1/gps/ping", headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token-admin"}, json=payload)
    client.post("/api/v1/gps/ping", headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token-admin"}, json=payload)

    assert gps.redis_failures_count >= 3

    # Reset trigger tracker
    mock_redis.failures_triggered = 0

    # 4th call should immediately fall back without invoking Redis operations again
    client.post("/api/v1/gps/ping", headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token-admin"}, json=payload)
    
    assert mock_redis.failures_triggered == 0


def test_interval_reset_on_job_status_transition(setup_db):
    db = setup_db
    tech = Technician(tech_id="tech-1", technician_name="Tech 1", technician_skill="HVAC", technician_location="0,0", tenant_id="tenant-1")
    db.add(tech)
    db.commit()
    db.refresh(tech)

    job = Job(id=101, customer_name="Alice", location="1,1", issue_description="Leak", priority="HIGH", service_type="Plumbing", contact_number="123456", status="ASSIGNED", assigned_technician_id=tech.technician_id, tenant_id="tenant-1", preferred_service_date=datetime.now().date())
    db.add(job)
    db.commit()
    db.refresh(job)

    payload = {
        "technician_id": "tech-1",
        "job_id": "101",
        "latitude": 12.34,
        "longitude": 56.78,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    # Ping 1 (ASSIGNED status) -> succeeds
    response = client.post("/api/v1/gps/ping", headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token-admin"}, json=payload)
    assert response.status_code == 201

    # Transition status to EN_ROUTE
    job.status = "EN_ROUTE"
    db.commit()

    # Ping 2 (EN_ROUTE status) -> succeeds immediately (interval reset!)
    response = client.post("/api/v1/gps/ping", headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token-admin"}, json=payload)
    assert response.status_code == 201

    # Ping 3 (still EN_ROUTE) within 30s -> rejected
    response = client.post("/api/v1/gps/ping", headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token-admin"}, json=payload)
    assert response.status_code == 429


def test_cross_tenant_isolation(setup_db):
    db = setup_db
    tech = Technician(tech_id="tech-1", technician_name="Tech 1", technician_skill="HVAC", technician_location="0,0", tenant_id="tenant-1")
    db.add(tech)
    db.commit()
    db.refresh(tech)

    # 2 separate jobs
    job1 = Job(id=101, customer_name="Alice", location="1,1", issue_description="Leak", priority="HIGH", service_type="Plumbing", contact_number="123456", status="ASSIGNED", assigned_technician_id=tech.technician_id, tenant_id="tenant-1", preferred_service_date=datetime.now().date())
    job2 = Job(id=102, customer_name="Bob", location="2,2", issue_description="Fuse", priority="HIGH", service_type="Electrical", contact_number="123456", status="ASSIGNED", assigned_technician_id=tech.technician_id, tenant_id="tenant-1", preferred_service_date=datetime.now().date())
    db.add(job1)
    db.add(job2)
    db.commit()
    db.refresh(job1)
    db.refresh(job2)

    payload1 = {
        "technician_id": "tech-1",
        "job_id": "101",
        "latitude": 12.34,
        "longitude": 56.78,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    payload2 = {
        "technician_id": "tech-1",
        "job_id": "102",
        "latitude": 12.34,
        "longitude": 56.78,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    # Ping job 1 -> success
    response1 = client.post("/api/v1/gps/ping", headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token-admin"}, json=payload1)
    assert response1.status_code == 201

    # Ping job 2 immediately -> success (separate intervals per job assignment)
    response2 = client.post("/api/v1/gps/ping", headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token-admin"}, json=payload2)
    assert response2.status_code == 201


def test_immediate_purge_on_job_closed(setup_db):
    db = setup_db
    tech = Technician(tech_id="tech-1", technician_name="Tech 1", technician_skill="HVAC", technician_location="0,0", tenant_id="tenant-1")
    db.add(tech)
    db.commit()
    db.refresh(tech)

    job = Job(id=101, customer_name="Alice", location="1,1", issue_description="Leak", priority="HIGH", service_type="Plumbing", contact_number="123456", status="ASSIGNED", assigned_technician_id=tech.technician_id, tenant_id="tenant-1", preferred_service_date=datetime.now().date())
    db.add(job)
    db.commit()
    db.refresh(job)

    # Insert a ping
    ping = GPSPing(
        id="ping-to-purge",
        technician_id="tech-1",
        job_id="101",
        latitude=12.34,
        longitude=56.78,
        timestamp=datetime.now(timezone.utc),
        tenant_id="tenant-1"
    )
    db.add(ping)
    db.commit()

    assert db.query(GPSPing).filter(GPSPing.job_id == "101").count() == 1

    # Trigger purge by changing status to CLOSED
    job.status = "CLOSED"
    db.commit()

    # Allow eager sync/thread execution to complete
    time.sleep(0.1)

    # Verify SQL deleted (hard delete)
    assert db.query(GPSPing).filter(GPSPing.job_id == "101").count() == 0

    # Verify audit logs in DB
    audit = db.query(GPSPurgeAuditLog).filter(GPSPurgeAuditLog.job_id == "101").first()
    assert audit is not None
    assert audit.deleted_count == 1


def test_race_condition_ping_during_status_change(setup_db):
    db = setup_db
    tech = Technician(tech_id="tech-1", technician_name="Tech 1", technician_skill="HVAC", technician_location="0,0", tenant_id="tenant-1")
    db.add(tech)
    db.commit()
    db.refresh(tech)

    job = Job(id=101, customer_name="Alice", location="1,1", issue_description="Leak", priority="HIGH", service_type="Plumbing", contact_number="123456", status="ASSIGNED", assigned_technician_id=tech.technician_id, tenant_id="tenant-1", preferred_service_date=datetime.now().date())
    db.add(job)
    db.commit()
    db.refresh(job)

    payload = {
        "technician_id": "tech-1",
        "job_id": "101",
        "latitude": 12.34,
        "longitude": 56.78,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    # Override database session for the router to change job status right before commit
    original_refresh = TestingSessionLocal().refresh
    def mock_refresh(instance):
        if isinstance(instance, Job) and instance.id == 101:
            instance.status = "CLOSED"
        else:
            original_refresh(instance)

    def override_db_session_with_mock():
        s = TestingSessionLocal()
        s.refresh = mock_refresh
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_db_session_with_mock

    # Ping should be rejected with 409
    response = client.post("/api/v1/gps/ping", headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token-admin"}, json=payload)
    assert response.status_code == 409
    data = response.json()
    assert data["detail"] == "Job status changed during processing"
    assert data["status"] == 409


def test_admin_purge_status_endpoint(setup_db):
    db = setup_db
    job = Job(id=101, customer_name="Alice", location="1,1", issue_description="Leak", priority="HIGH", service_type="Plumbing", contact_number="123456", status="ASSIGNED", tenant_id="tenant-1", preferred_service_date=datetime.now().date())
    db.add(job)
    db.commit()
    
    # Check status when not started
    response = client.get(
        "/api/v1/admin/gps/purge-status/101",
        headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token-admin"}
    )
    assert response.status_code == 200
    assert response.json()["purge_status"] == "not_started"

    # Set status directly in Redis
    mock_redis.set("gps_purge_status:101", json.dumps({
        "job_id": "101",
        "purge_status": "completed",
        "purged_at": "2026-06-25T12:00:00Z",
        "deleted_count": 5
    }))

    response = client.get(
        "/api/v1/admin/gps/purge-status/101",
        headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token-admin"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["purge_status"] == "completed"
    assert data["deleted_count"] == 5


def test_admin_rejected_pings_endpoint(setup_db):
    db = setup_db
    # Seed rejected ping log
    rejected_log = GPSRejectedPingLog(
        technician_id="tech-1",
        job_id="101",
        reason="Test rejection reason",
        tenant_id="tenant-1"
    )
    db.add(rejected_log)
    db.commit()

    response = client.get(
        "/api/v1/admin/gps/rejected-pings",
        headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token-admin"}
    )
    assert response.status_code == 200
    logs = response.json()
    assert len(logs) == 1
    assert logs[0]["reason"] == "Test rejection reason"
    assert logs[0]["technician_id"] == "tech-1"


def test_admin_bypass_interval(setup_db):
    db = setup_db
    tech = Technician(tech_id="tech-1", technician_name="Tech 1", technician_skill="HVAC", technician_location="0,0", tenant_id="tenant-1")
    db.add(tech)
    db.commit()
    db.refresh(tech)

    job = Job(id=101, customer_name="Alice", location="1,1", issue_description="Leak", priority="HIGH", service_type="Plumbing", contact_number="123456", status="ASSIGNED", assigned_technician_id=tech.technician_id, tenant_id="tenant-1", preferred_service_date=datetime.now().date())
    db.add(job)
    db.commit()
    db.refresh(job)

    payload = {
        "technician_id": "tech-1",
        "job_id": "101",
        "latitude": 12.34,
        "longitude": 56.78,
        "timestamp": "2026-06-25T12:00:00Z"
    }

    # Ping 1
    response = client.post("/api/v1/gps/ping", headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token-admin"}, json=payload)
    assert response.status_code == 201

    # Ping 2 immediately with bypass_interval query parameter -> Should succeed!
    response = client.post(
        "/api/v1/gps/ping?bypass_interval=true",
        headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token-admin"},
        json=payload
    )
    assert response.status_code == 201


def test_celery_task_retries_and_dlq(setup_db):
    from app.tasks import purge_job_gps_data
    from celery.exceptions import MaxRetriesExceededError
    import app.tasks as tasks_module

    db = setup_db

    # Mock execute_job_gps_purge_sync to simulate DB failures
    original_execute = tasks_module.execute_job_gps_purge_sync
    tasks_module.execute_job_gps_purge_sync = MagicMock(side_effect=Exception("Database connection failure"))

    # Mock the celery task retry on the task instance itself
    original_retry = purge_job_gps_data.retry
    mock_retry = MagicMock()
    purge_job_gps_data.retry = mock_retry

    # We manually simulate the celery retry counter on purge_job_gps_data.request.retries
    purge_job_gps_data.request.retries = 0

    def mock_retry_func(exc, countdown):
        purge_job_gps_data.request.retries += 1
        if purge_job_gps_data.request.retries > 3:
            raise MaxRetriesExceededError()
        raise Exception("Celery retry")
        
    mock_retry.side_effect = mock_retry_func

    try:
        # First call (retries=0) -> raises Exception("Celery retry")
        with pytest.raises(Exception, match="Celery retry"):
            purge_job_gps_data.run(101, "tenant-1")

        # Second call (retries=1) -> raises Exception("Celery retry")
        with pytest.raises(Exception, match="Celery retry"):
            purge_job_gps_data.run(101, "tenant-1")

        # Third call (retries=2) -> raises Exception("Celery retry")
        with pytest.raises(Exception, match="Celery retry"):
            purge_job_gps_data.run(101, "tenant-1")

        # Fourth call (retries=3) -> mock_retry raises MaxRetriesExceededError.
        # Task catches it, sets to failed in Redis, pushes to DLQ list in Redis, and raises original exception.
        with pytest.raises(Exception, match="Database connection failure"):
            purge_job_gps_data.run(101, "tenant-1")
            
        # Assert status is set to failed in Redis
        status_raw = mock_redis.get("gps_purge_status:101")
        assert status_raw is not None
        status_data = json.loads(status_raw)
        assert status_data["purge_status"] == "failed"

        # Assert pushed to DLQ
        dlq_list = mock_redis.data.get("gps_purge_dlq")
        assert dlq_list is not None
        assert len(dlq_list) == 1
        dlq_item = json.loads(dlq_list[0])
        assert dlq_item["job_id"] == 101
        assert dlq_item["error"] == "Database connection failure"

    finally:
        # Restore mocks
        tasks_module.execute_job_gps_purge_sync = original_execute
        purge_job_gps_data.retry = original_retry
        purge_job_gps_data.request.retries = 0
