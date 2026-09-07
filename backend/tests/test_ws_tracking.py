import pytest
import jwt
import json
import time
import asyncio
import msgpack
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocketDisconnect
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import fakeredis
import fakeredis.aioredis

# Setup Test DB
SQLALCHEMY_DATABASE_URL = "sqlite://"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Patch app.database.SessionLocal before importing other components
import app.database
app.database.SessionLocal = TestingSessionLocal

from app.main import app
from app.database import Base, get_db
from app.models import Tenant, Technician, Job, GPSPing, SecurityAuditLog
from app.redis_client import get_redis_client
from app.services.tracking_manager import (
    ConnectionManager,
    TenantValidator,
    WS_JWT_SECRET,
    WS_JWT_ALGORITHM,
    connection_manager,
    log_security_event,
)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

# Shared Redis Server for Pub/Sub synchrony
shared_server = fakeredis.FakeServer()
fake_sync_redis = fakeredis.FakeRedis(server=shared_server, decode_responses=True)
fake_async_redis = fakeredis.aioredis.FakeRedis(server=shared_server, decode_responses=True)

app.dependency_overrides[get_redis_client] = lambda: fake_sync_redis

@pytest.fixture(autouse=True, scope="module")
def mock_deps():
    with patch("redis.asyncio.Redis", return_value=fake_async_redis):
        # Explicit module imports of SessionLocal also need to be overridden if they were bound early
        import app.main
        import app.services.tracking_manager
        import app.routes.tracking
        app.main.SessionLocal = TestingSessionLocal
        app.services.tracking_manager.SessionLocal = TestingSessionLocal
        if hasattr(app.routes.tracking, "SessionLocal"):
            app.routes.tracking.SessionLocal = TestingSessionLocal
        yield

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    # Reset ConnectionManager registers between tests
    connection_manager.active_connections.clear()
    connection_manager.channel_subscriptions.clear()
    connection_manager.connection_metadata.clear()
    connection_manager._total_messages_broadcast = 0
    
    fake_sync_redis.flushall()
    
    db = TestingSessionLocal()
    yield db
    db.close()

# Token generator helper
def generate_token(tenant_id="tenant-1", role="dispatcher", user_id="user-1", expired=False):
    payload = {
        "tenant_id": tenant_id,
        "role": role,
        "user_id": user_id,
        "exp": int(time.time()) + (300 if not expired else -300)
    }
    return jwt.encode(payload, WS_JWT_SECRET, algorithm=WS_JWT_ALGORITHM)


def test_handshake_successful(setup_db):
    token = generate_token()
    client = TestClient(app)
    with client.websocket_connect(f"/ws/v1/tracking?token={token}") as websocket:
        # Handshake success, we can subscribe to own tenant channel
        websocket.send_json({"type": "subscribe", "channel": "tenant:tenant-1:all"})
        resp = websocket.receive_json()
        assert resp["type"] == "subscribed"
        assert resp["channel"] == "tenant:tenant-1:all"


def test_handshake_expired_token(setup_db):
    token = generate_token(expired=True)
    client = TestClient(app)
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"/ws/v1/tracking?token={token}"):
            pass
    assert exc.value.code == 1008


def test_handshake_invalid_role(setup_db):
    token = generate_token(role="unauthorized_role")
    client = TestClient(app)
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"/ws/v1/tracking?token={token}"):
            pass
    assert exc.value.code == 1008


def test_handshake_cross_tenant_rejection(setup_db):
    # JWT claims tenant-1, but requested tenant-2
    token = generate_token(tenant_id="tenant-1")
    client = TestClient(app)
    with client.websocket_connect(f"/ws/v1/tracking?token={token}&tenant_id=tenant-2") as websocket:
        with pytest.raises(WebSocketDisconnect) as exc:
            websocket.receive_json()
        assert exc.value.code == 1008

    # Verify security audit log
    db = setup_db
    logs = db.query(SecurityAuditLog).filter(SecurityAuditLog.event == "cross_tenant_handshake_attempt").all()
    assert len(logs) == 1
    assert logs[0].user_tenant == "tenant-1"
    assert logs[0].target_tenant == "tenant-2"
    assert logs[0].severity == "warning"
    assert logs[0].action_taken == "connection_rejected"


def test_connection_limit_enforced(setup_db):
    token = generate_token(tenant_id="tenant-1")
    
    # Connection manager has limit 100. Let's mock the register size
    # artificially to check the 101st connection rejection.
    fake_websockets = [MagicMock() for _ in range(100)]
    connection_manager.active_connections["tenant-1"] = fake_websockets

    client = TestClient(app)
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"/ws/v1/tracking?token={token}"):
            pass
    assert exc.value.code == 1008
    assert "limit exceeded" in exc.value.reason


def test_cross_tenant_subscription_rejection(setup_db):
    token = generate_token(tenant_id="tenant-1")
    client = TestClient(app)
    with client.websocket_connect(f"/ws/v1/tracking?token={token}") as websocket:
        # Subscribe to tenant-2
        websocket.send_json({"type": "subscribe", "channel": "tenant:tenant-2:all"})
        resp = websocket.receive_json()
        assert resp["type"] == "error"
        assert resp["code"] == "CROSS_TENANT_ACCESS"

    # Verify security audit log
    db = setup_db
    logs = db.query(SecurityAuditLog).filter(SecurityAuditLog.event == "cross_tenant_access_attempt").all()
    assert len(logs) == 1
    assert logs[0].user_tenant == "tenant-1"
    assert logs[0].attempted_channel == "tenant:tenant-2:all"
    assert logs[0].severity == "warning"
    assert logs[0].action_taken == "subscription_rejected"


def test_parent_child_tenant_admin_subscription(setup_db):
    db = setup_db
    # Seed parent-child relationship
    parent = Tenant(id="parent-tenant", name="Parent Inc")
    child = Tenant(id="child-tenant", name="Child Inc", parent_tenant_id="parent-tenant")
    db.add(parent)
    db.add(child)
    db.commit()

    # 1. Parent admin connects and subscribes to child-tenant -> Succeeds
    token_admin = generate_token(tenant_id="parent-tenant", role="tenant_admin")
    client = TestClient(app)
    with client.websocket_connect(f"/ws/v1/tracking?token={token_admin}") as websocket:
        websocket.send_json({"type": "subscribe", "channel": "tenant:child-tenant:all"})
        resp = websocket.receive_json()
        assert resp["type"] == "subscribed"

    # 2. Parent dispatcher connects and subscribes to child-tenant -> Fails
    token_dispatcher = generate_token(tenant_id="parent-tenant", role="dispatcher")
    with client.websocket_connect(f"/ws/v1/tracking?token={token_dispatcher}") as websocket:
        websocket.send_json({"type": "subscribe", "channel": "tenant:child-tenant:all"})
        resp = websocket.receive_json()
        assert resp["type"] == "error"
        assert resp["code"] == "CROSS_TENANT_ACCESS"


def test_broadcast_tenant_mismatch(setup_db):
    db = setup_db
    
    # Register dummy subscription
    ws = MagicMock()
    connection_manager.channel_subscriptions["tenant:tenant-1:all"] = {ws}

    # Attempt to broadcast a payload from tenant-2 into tenant-1 channel
    payload = {
        "tenant_id": "tenant-2",
        "technician_id": "tech-123",
        "job_id": "1",
        "latitude": 1.23,
        "longitude": 4.56
    }
    
    sent = asyncio.run(connection_manager.broadcast("tenant:tenant-1:all", payload))
    assert sent == 0

    # Verify security audit log for mismatch
    logs = db.query(SecurityAuditLog).filter(SecurityAuditLog.event == "broadcast_tenant_mismatch").all()
    assert len(logs) == 1
    assert logs[0].payload_tenant == "tenant-2"
    assert logs[0].target_tenant == "tenant-1"
    assert logs[0].severity == "critical"
    assert logs[0].action_taken == "message_dropped"


def test_broadcast_technician_and_job_tenant_validation(setup_db):
    db = setup_db

    # Seed technician belonging to tenant-1
    tech = Technician(
        technician_id=1,
        tech_id="tech-1",
        tenant_id="tenant-1",
        technician_name="Alice",
        technician_skill="Plumber",
        technician_location="Zone A"
    )
    # Seed job belonging to tenant-1
    job = Job(
        id=10,
        tenant_id="tenant-1",
        customer_name="Bob",
        location="Zone B",
        issue_description="Leak",
        priority="HIGH",
        service_type="Plumbing",
        contact_number="123",
        preferred_service_date=datetime.now().date(),
        assigned_technician_id=1
    )
    db.add(tech)
    db.add(job)
    db.commit()

    # Register subscription
    ws = MagicMock()
    ws.send_json = AsyncMock()
    connection_manager.channel_subscriptions["tenant:tenant-1:all"] = {ws}

    # 1. Matching technician and job -> Succeeds
    payload_valid = {
        "tenant_id": "tenant-1",
        "technician_id": "tech-1",
        "job_id": "10",
        "latitude": 1.23,
        "longitude": 4.56
    }
    sent = asyncio.run(connection_manager.broadcast("tenant:tenant-1:all", payload_valid))
    assert sent == 1

    # 2. Technician from different tenant -> Mismatched tech logs
    payload_bad_tech = {
        "tenant_id": "tenant-1",
        "technician_id": "tech-nonexistent",  # non-existent tech behaves as mismatched
        "job_id": "10",
        "latitude": 1.23,
        "longitude": 4.56
    }
    sent = asyncio.run(connection_manager.broadcast("tenant:tenant-1:all", payload_bad_tech))
    assert sent == 0
    logs = db.query(SecurityAuditLog).filter(SecurityAuditLog.event == "broadcast_technician_tenant_mismatch").all()
    assert len(logs) == 1

    # 3. Job from different tenant -> Mismatched job logs
    payload_bad_job = {
        "tenant_id": "tenant-1",
        "technician_id": "tech-1",
        "job_id": "999",  # nonexistent job
        "latitude": 1.23,
        "longitude": 4.56
    }
    sent = asyncio.run(connection_manager.broadcast("tenant:tenant-1:all", payload_bad_job))
    assert sent == 0
    logs = db.query(SecurityAuditLog).filter(SecurityAuditLog.event == "broadcast_job_tenant_mismatch").all()
    assert len(logs) == 1


def test_gps_ping_to_broadcast_pipeline_publish(setup_db):
    db = setup_db
    # Seed technician and job
    tech = Technician(
        technician_id=1,
        tech_id="tech-1",
        tenant_id="tenant-1",
        technician_name="Alice",
        technician_skill="Plumber",
        technician_location="Zone A"
    )
    job = Job(
        id=10,
        tenant_id="tenant-1",
        customer_name="Bob",
        location="Zone B",
        issue_description="Leak",
        priority="HIGH",
        service_type="Plumbing",
        contact_number="123",
        preferred_service_date=datetime.now().date(),
        assigned_technician_id=1,
        status="ASSIGNED"
    )
    db.add(tech)
    db.add(job)
    db.commit()

    # Clear fake redis pub/sub before pinging
    fake_sync_redis.flushall()

    # Call GPS ping
    client = TestClient(app)
    ping_payload = {
        "technician_id": "tech-1",
        "job_id": "10",
        "latitude": 1.234,
        "longitude": 5.678,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "accuracy": 10.0,
        "altitude": 100.0
    }
    headers = {
        "X-Tenant-ID": "tenant-1",
        "Authorization": "Bearer mock-token-value"
    }
    
    with patch("app.tasks.update_eta_task") as mock_task:
        with patch("app.routes.gps.verify_jwt_token", return_value="mock-token-value"):
            response = client.post("/api/v1/gps/ping", json=ping_payload, headers=headers)
            assert response.status_code == 201


def test_query_security_audit_logs_endpoint(setup_db):
    db = setup_db
    # Log a dummy security audit event
    log_security_event(
        db=db,
        event_type="cross_tenant_access_attempt",
        severity="warning",
        user_tenant="tenant-1",
        attempted_channel="tenant:tenant-2:all",
        ip_address="127.0.0.1",
        websocket_id="ws-12345",
        action_taken="subscription_rejected"
    )

    client = TestClient(app)
    with patch("app.routes.audit.verify_jwt_token", return_value="mock-token-value"):
        # Query logs via endpoint
        response = client.get("/audit/security?tenant_id=tenant-1")
        assert response.status_code == 200
        logs = response.json()
        assert len(logs) == 1
        assert logs[0]["event"] == "cross_tenant_access_attempt"
        assert logs[0]["user_tenant"] == "tenant-1"
        assert logs[0]["attempted_channel"] == "tenant:tenant-2:all"
        assert logs[0]["action_taken"] == "subscription_rejected"
