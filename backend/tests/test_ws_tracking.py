import pytest
import jwt
import json
import time
import asyncio
import os
import importlib.util
import msgpack
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock, AsyncMock
from types import SimpleNamespace

import app.services.tracking_manager as tm
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
from app.auth.dependencies import get_current_user, AuthenticatedUser
from app.auth.rbac import UserRole
from app.services.tracking_manager import (
    ConnectionManager,
    TenantValidator,
    WS_JWT_SECRET,
    WS_JWT_ALGORITHM,
    connection_manager,
    log_security_event,
    ValidationResult,
    decode_ws_token,
    _as_utc,
    _parse_iso_utc,
)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
    "test-admin", "tenant-1", UserRole.SUPER_ADMIN, "test-session"
)

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

    # Other test modules clear FastAPI's shared dependency overrides. Reinstall
    # the authenticated GPS test actor for every test in this module.
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        "test-admin", "tenant-1", UserRole.SUPER_ADMIN, "test-session"
    )
    
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

def test_handshake_sso_cookie_success(setup_db):
    """
    SSO browsers cannot read the HttpOnly access-token cookie from
    JavaScript, so the WebSocket endpoint must authenticate using
    the fieldops_access_token cookie.
    """
    token = generate_token(
        tenant_id="tenant-1",
        role="dispatcher",
        user_id="user-1",
    )

    client = TestClient(app)

    with client.websocket_connect(
        "/ws/v1/tracking",
        headers={
            "Cookie": f"fieldops_access_token={token}",
        },
    ) as websocket:
        websocket.send_json({
            "type": "subscribe",
            "channel": "tenant:tenant-1:all",
        })

        response = websocket.receive_json()

        assert response["type"] == "subscribed"
        assert response["channel"] == "tenant:tenant-1:all"

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


def test_technician_tracking_subscriptions_are_assignment_scoped(setup_db):
    db = setup_db
    db.add_all([
        Technician(technician_id=1, tech_id="tech-1", tenant_id="tenant-1",
                   technician_name="Alice", technician_skill="Plumber", technician_location="A"),
        Technician(technician_id=2, tech_id="tech-2", tenant_id="tenant-1",
                   technician_name="Bob", technician_skill="Plumber", technician_location="B"),
        Job(id=10, tenant_id="tenant-1", customer_name="Customer", location="A",
            issue_description="Leak", priority="HIGH", service_type="Plumbing",
            contact_number="123", preferred_service_date=datetime.now().date(),
            assigned_technician_id=1, status="ASSIGNED"),
    ])
    db.commit()

    token = generate_token(tenant_id="tenant-1", role="technician", user_id="tech-1")
    client = TestClient(app)
    with client.websocket_connect(f"/ws/v1/tracking?token={token}") as websocket:
        websocket.send_json({"type": "subscribe", "channel": "tenant:tenant-1:technician:tech-1"})
        assert websocket.receive_json()["type"] == "subscribed"
        websocket.send_json({"type": "subscribe", "channel": "tenant:tenant-1:job:10"})
        assert websocket.receive_json()["type"] == "subscribed"
        websocket.send_json({"type": "subscribe", "channel": "tenant:tenant-1:technician:tech-2"})
        assert websocket.receive_json()["code"] == "RESOURCE_ACCESS_DENIED"
        websocket.send_json({"type": "subscribe", "channel": "tenant:tenant-1:all"})
        assert websocket.receive_json()["code"] == "RESOURCE_ACCESS_DENIED"


def test_parent_child_tenant_cross_tenant_subscription_rejected(setup_db):
    db = setup_db

    # Seed parent-child relationship
    parent = Tenant(
        id="parent-tenant",
        name="Parent Inc",
    )
    child = Tenant(
        id="child-tenant",
        name="Child Inc",
        parent_tenant_id="parent-tenant",
    )

    db.add(parent)
    db.add(child)
    db.commit()

    client = TestClient(app)

    # Parent dispatcher must NOT access child tenant
    token_dispatcher = generate_token(
        tenant_id="parent-tenant",
        role="dispatcher",
        user_id="dispatcher-1",
    )

    with client.websocket_connect(
        f"/ws/v1/tracking?token={token_dispatcher}"
    ) as websocket:

        websocket.send_json({
            "type": "subscribe",
            "channel": "tenant:child-tenant:all",
        })

        resp = websocket.receive_json()

        assert resp["type"] == "error"
        assert resp["code"] == "CROSS_TENANT_ACCESS"

    # Verify security audit log
    logs = (
        db.query(SecurityAuditLog)
        .filter(
            SecurityAuditLog.event == "cross_tenant_access_attempt"
        )
        .all()
    )

    assert len(logs) == 1
    assert logs[0].user_tenant == "parent-tenant"
    assert logs[0].attempted_channel == "tenant:child-tenant:all"
    assert logs[0].severity == "warning"
    assert logs[0].action_taken == "subscription_rejected"


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


# ============================================================================
# UNIT COVERAGE FOR DEFENSIVE / FAILURE PATHS
# ============================================================================


class _FakeQuery:
    def __init__(self, first_value=None, scalar_value=None):
        self.first_value = first_value
        self.scalar_value = scalar_value

    def join(self, *args, **kwargs):
        return self

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.first_value

    def scalar(self):
        return self.scalar_value


class _FakeDB:
    def __init__(self, *queries):
        self.queries = list(queries)
        self.added = []
        self.committed = False
        self.closed = False
        self.rolled_back = False

    def query(self, *args, **kwargs):
        if not self.queries:
            raise AssertionError("Unexpected database query")
        return self.queries.pop(0)

    def add(self, value):
        self.added.append(value)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


class _FakeWebSocket:
    def __init__(self, host="testclient"):
        self.client = SimpleNamespace(host=host) if host is not None else None
        self.send_json = AsyncMock()
        self.close = AsyncMock()
        self.accept = AsyncMock()


class _AwaitableTask:
    def __init__(self, exc=None):
        self.exc = exc
        self.cancelled = False

    def cancel(self):
        self.cancelled = True

    def __await__(self):
        async def _run():
            if self.exc is not None:
                raise self.exc
            return None
        return _run().__await__()


def _install_connection_metadata(manager, websocket, **overrides):
    values = {
        "tenant_id": "tenant-1",
        "user_id": "user-1",
        "role": "dispatcher",
        "connected_at": datetime.now(timezone.utc).isoformat(),
    }
    values.update(overrides)
    manager.connection_metadata[id(websocket)] = values


def test_time_helpers_and_token_helpers():
    naive = datetime(2026, 1, 2, 3, 4, 5)
    aware = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

    assert _as_utc(naive).tzinfo == timezone.utc
    assert _as_utc(aware).tzinfo == timezone.utc
    assert _parse_iso_utc(None) is None
    assert _parse_iso_utc(aware) == aware
    assert _parse_iso_utc("2026-01-02T03:04:05Z").tzinfo == timezone.utc
    assert _parse_iso_utc("not-a-date") is None

    with pytest.raises(jwt.InvalidTokenError):
        decode_ws_token("")

    claims = {"tenant_id": "tenant-1", "role": "dispatcher", "user_id": "u"}
    with patch.object(tm.jwt, "decode", return_value=claims) as decode:
        assert decode_ws_token("token") == claims
        decode.assert_called_once_with(
            "token",
            tm.WS_JWT_SECRET,
            algorithms=[tm.WS_JWT_ALGORITHM],
        )


def test_log_security_event_all_fields_and_persistence_failure(setup_db):
    db = setup_db
    log_security_event(
        db=db,
        event_type="full_event",
        severity="error",
        user_tenant="tenant-1",
        attempted_channel="tenant:tenant-1:job:1",
        ip_address="127.0.0.1",
        websocket_id="ws-1",
        action_taken="dropped",
        payload_tenant="tenant-1",
        target_tenant="tenant-1",
        technician_id="tech-1",
        job_id=10,
    )
    saved = db.query(SecurityAuditLog).filter(SecurityAuditLog.event == "full_event").one()
    assert saved.technician_id == "tech-1"
    assert saved.job_id == "10"

    failing_db = MagicMock()
    failing_db.add.return_value = None
    failing_db.commit.side_effect = RuntimeError("commit failed")
    log_security_event(
        db=failing_db,
        event_type="failure_event",
        severity="warning",
        user_tenant=None,
        attempted_channel=None,
        ip_address=None,
        websocket_id=None,
        action_taken="ignored",
    )
    failing_db.commit.assert_called_once()


def test_tenant_validator_invalid_and_customer_paths():
    validator = TenantValidator(_FakeDB())

    invalid = validator.validate_channel_sync("job:10", "tenant-1", "dispatcher", "u")
    assert invalid.code == "INVALID_CHANNEL_FORMAT"

    invalid_customer = validator.validate_channel_sync(
        "tenant:tenant-1:all", "tenant-1", "customer", "customer-1"
    )
    assert invalid_customer.code == "RESOURCE_ACCESS_DENIED"

    denied_customer = TenantValidator(
        _FakeDB(_FakeQuery(first_value=None))
    ).validate_channel_sync(
        "tenant:provider:job:10", "customer-tenant", "customer", "customer-1"
    )
    assert denied_customer.code == "RESOURCE_ACCESS_DENIED"

    owned_mismatch = TenantValidator(
        _FakeDB(
            _FakeQuery(first_value=(10,)),
            _FakeQuery(scalar_value="provider-tenant"),
        )
    ).validate_channel_sync(
        "tenant:customer-tenant:job:10",
        "customer-tenant",
        "customer",
        "customer-1",
    )
    assert owned_mismatch.code == "INVALID_JOB_CHANNEL"

    owned = TenantValidator(
        _FakeDB(
            _FakeQuery(first_value=(10,)),
            _FakeQuery(scalar_value="provider-tenant"),
        )
    ).validate_channel_sync(
        "tenant:provider-tenant:job:10",
        "customer-tenant",
        "customer",
        "customer-1",
    )
    assert owned.allowed is True


def test_tenant_validator_technician_and_cross_tenant_paths():
    validator = TenantValidator(_FakeDB())
    invalid_tech = validator.validate_channel_sync(
        "tenant:other:job:1", "tenant-1", "technician", "tech-1"
    )
    assert invalid_tech.code == "RESOURCE_ACCESS_DENIED"

    missing_tech = TenantValidator(
        _FakeDB(_FakeQuery(first_value=None))
    ).validate_channel_sync(
        "tenant:tenant-1:technician:tech-1",
        "tenant-1",
        "technician",
        "tech-1",
    )
    assert missing_tech.allowed is False

    tech = SimpleNamespace(tech_id="tech-1", technician_id=1)

    matching_tech = TenantValidator(
        _FakeDB(_FakeQuery(first_value=tech))
    ).validate_channel_sync(
        "tenant:tenant-1:technician:tech-1",
        "tenant-1",
        "technician",
        "tech-1",
    )
    assert matching_tech.allowed is True

    wrong_tech_resource = TenantValidator(
        _FakeDB(_FakeQuery(first_value=tech))
    ).validate_channel_sync(
        "tenant:tenant-1:technician:tech-2",
        "tenant-1",
        "technician",
        "tech-1",
    )
    assert wrong_tech_resource.allowed is False

    valid_job = TenantValidator(
        _FakeDB(
            _FakeQuery(first_value=tech),
            _FakeQuery(first_value=(10,)),
        )
    ).validate_channel_sync(
        "tenant:tenant-1:job:10",
        "tenant-1",
        "technician",
        "tech-1",
    )
    assert valid_job.allowed is True

    invalid_job_type = TenantValidator(
        _FakeDB(_FakeQuery(first_value=tech))
    ).validate_channel_sync(
        "tenant:tenant-1:job:not-a-number",
        "tenant-1",
        "technician",
        "tech-1",
    )
    assert invalid_job_type.allowed is False

    invalid_resource = TenantValidator(
        _FakeDB(_FakeQuery(first_value=tech))
    ).validate_channel_sync(
        "tenant:tenant-1:all:stream",
        "tenant-1",
        "technician",
        "tech-1",
    )
    assert invalid_resource.allowed is False

    same_tenant = TenantValidator(_FakeDB()).validate_channel_sync(
        "tenant:tenant-1:all", "tenant-1", "dispatcher", "u"
    )
    assert same_tenant.allowed is True

    child_allowed = TenantValidator(
        _FakeDB(_FakeQuery(first_value=object()))
    ).validate_channel_sync(
        "tenant:child:all", "parent", "tenant_admin", "admin"
    )
    assert child_allowed.allowed is True

    child_denied = TenantValidator(
        _FakeDB(_FakeQuery(first_value=None))
    ).validate_channel_sync(
        "tenant:child:all", "parent", "tenant_admin", "admin"
    )
    assert child_denied.code == "CROSS_TENANT_ACCESS"


def test_tenant_validator_numeric_technician_user_id():
    tech = SimpleNamespace(tech_id="tech-1", technician_id=123)
    result = TenantValidator(
        _FakeDB(_FakeQuery(first_value=tech))
    ).validate_channel_sync(
        "tenant:tenant-1:technician:123",
        "tenant-1",
        "technician",
        "123",
    )
    assert result.allowed is True


def test_tenant_validator_backward_compat_wrapper():
    ws = _FakeWebSocket()
    validator = TenantValidator(_FakeDB())

    assert asyncio.run(
        validator.validate_channel(
            ws,
            "tenant:tenant-1:all",
            "tenant-1",
            "dispatcher",
            "u",
        )
    ) is True

    denied_ws = _FakeWebSocket()
    denied = asyncio.run(
        validator.validate_channel(
            denied_ws,
            "tenant:tenant-2:all",
            "tenant-1",
            "dispatcher",
            "u",
        )
    )
    assert denied is False
    denied_ws.send_json.assert_awaited_once()

    failing_ws = _FakeWebSocket()
    failing_ws.send_json.side_effect = RuntimeError("send failed")
    assert asyncio.run(
        validator.validate_channel(
            failing_ws,
            "tenant:tenant-2:all",
            "tenant-1",
            "dispatcher",
            "u",
        )
    ) is False


def test_manager_redis_and_safe_send_paths():
    manager = ConnectionManager()

    with patch.object(tm, "redis", None):
        assert asyncio.run(manager._get_redis()) is None

    fake_redis = MagicMock()
    with patch.object(tm, "redis", fake_redis):
        fake_redis.from_url.return_value = "redis-client"
        assert asyncio.run(manager._get_redis()) == "redis-client"
        assert asyncio.run(manager._get_redis()) == "redis-client"
        fake_redis.from_url.assert_called_once()

    with patch.object(tm, "redis", fake_redis):
        manager._redis = None
        fake_redis.from_url.side_effect = RuntimeError("redis unavailable")
        assert asyncio.run(manager._get_redis()) is None
        fake_redis.from_url.side_effect = None

    ws = _FakeWebSocket()
    assert asyncio.run(manager._send_json(ws, {"ok": True})) is True
    ws.send_json.assert_awaited_once_with({"ok": True})

    bad_ws = _FakeWebSocket()
    bad_ws.send_json.side_effect = RuntimeError("socket failed")
    assert asyncio.run(manager._send_json(bad_ws, {"ok": False})) is False

    manager._send_locks.clear()
    cancelled_ws = _FakeWebSocket()
    with patch.object(
        tm.asyncio,
        "wait_for",
        new=AsyncMock(side_effect=asyncio.CancelledError()),
    ):
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(manager._send_json(cancelled_ws, {"cancel": True}))

    error_ws = _FakeWebSocket()
    asyncio.run(manager._send_error(error_ws, "CODE", "message"))
    assert error_ws.send_json.await_args.args[0]["code"] == "CODE"


def test_manager_drop_and_connect_failure_paths():
    manager = ConnectionManager()
    ws = _FakeWebSocket()
    _install_connection_metadata(manager, ws)
    manager.active_connections["tenant-1"] = [ws]
    manager.channel_subscriptions["tenant:tenant-1:all"] = {ws}
    manager._send_locks[id(ws)] = asyncio.Lock()

    asyncio.run(manager._drop_connection(ws, code=1000, reason="test"))
    ws.close.assert_awaited_once()
    assert manager._total_dropped_connections == 1
    assert id(ws) not in manager.connection_metadata

    close_fail_ws = _FakeWebSocket()
    close_fail_ws.close.side_effect = RuntimeError("close failed")
    asyncio.run(manager._drop_connection(close_fail_ws))

    bad_token_ws = _FakeWebSocket()
    with patch.object(tm, "decode_ws_token", side_effect=jwt.PyJWTError("bad")):
        assert asyncio.run(manager.connect(bad_token_ws, "token")) is None
    bad_token_ws.close.assert_awaited_once()

    missing_claim_ws = _FakeWebSocket()
    with patch.object(
        tm,
        "decode_ws_token",
        return_value={"tenant_id": "tenant-1", "role": "dispatcher"},
    ):
        assert asyncio.run(manager.connect(missing_claim_ws, "token")) is None
    missing_claim_ws.close.assert_awaited_once()


def test_manager_connect_success_and_helpers():
    manager = ConnectionManager()
    ws = _FakeWebSocket()
    fake_task = MagicMock()
    claims = {
        "tenant_id": "tenant-1",
        "sub": "user-from-sub",
        "role": "dispatcher",
    }
    with patch.object(tm, "decode_ws_token", return_value=claims), patch.object(
        tm.asyncio, "create_task", return_value=fake_task
    ):
        result = asyncio.run(manager.connect(ws, "token"))

    assert result == claims
    assert ws.accept.await_count == 1
    assert manager.active_connections["tenant-1"] == [ws]
    assert manager.connection_metadata[id(ws)]["user_id"] == "user-from-sub"
    assert manager._heartbeat_tasks[id(ws)] is fake_task
    assert manager._subscription_count(ws) == 0
    assert manager._same_connection_tenant(id(ws), "tenant-1") is True
    assert manager._same_connection_tenant(id(ws), "tenant-2") is False
    assert manager._same_connection_tenant(999999, "tenant-1") is False


def test_manager_subscribe_failure_and_success_paths():
    manager = ConnectionManager()
    ws = _FakeWebSocket()
    _install_connection_metadata(manager, ws)

    manager.channel_subscriptions.clear()

    unregistered = _FakeWebSocket()
    assert asyncio.run(manager.subscribe(unregistered, "tenant:tenant-1:all", "tenant-1")) is False

    mismatch = _FakeWebSocket()
    _install_connection_metadata(manager, mismatch)
    assert asyncio.run(manager.subscribe(mismatch, "tenant:tenant-1:all", "tenant-2")) is False
    assert mismatch.send_json.await_args.args[0]["code"] == "CROSS_TENANT_ACCESS"

    capped = _FakeWebSocket()
    _install_connection_metadata(manager, capped)
    for index in range(tm.MAX_SUBSCRIPTIONS_PER_CONNECTION):
        manager.channel_subscriptions[f"tenant:tenant-1:job:{index + 1}"] = {capped}
    assert asyncio.run(manager.subscribe(capped, "tenant:tenant-1:all", "tenant-1")) is False
    assert capped.send_json.await_args.args[0]["code"] == "SUBSCRIPTION_LIMIT"

    valid_result = ValidationResult(True)
    success = _FakeWebSocket()
    _install_connection_metadata(manager, success)
    validator = MagicMock()
    validator.validate_channel_sync.return_value = valid_result
    manager.channel_subscriptions.clear()
    with patch.object(tm, "SessionLocal", return_value=_FakeDB()), patch.object(
        tm, "TenantValidator", return_value=validator
    ), patch.object(
        manager, "_send_latest_job_position", new=AsyncMock()
    ) as latest:
        assert asyncio.run(
            manager.subscribe(success, "tenant:tenant-1:job:10", "tenant-1")
        ) is True
    assert success.send_json.await_args.args[0]["type"] == "subscribed"
    latest.assert_awaited_once()

    limit_send_fail = _FakeWebSocket()
    _install_connection_metadata(manager, limit_send_fail)
    validator.validate_channel_sync.return_value = ValidationResult(True)
    drop = AsyncMock()
    with patch.object(tm, "SessionLocal", return_value=_FakeDB()), patch.object(
        tm, "TenantValidator", return_value=validator
    ), patch.object(
        manager, "_send_json", new=AsyncMock(return_value=False)
    ), patch.object(manager, "_drop_connection", new=drop), patch.object(
        manager, "_send_latest_job_position", new=AsyncMock()
    ):
        assert asyncio.run(
            manager.subscribe(limit_send_fail, "tenant:tenant-1:job:11", "tenant-1")
        ) is False
    drop.assert_awaited_once()


def test_manager_subscribe_post_validation_disconnect_and_audit_branches():
    manager = ConnectionManager()
    ws = _FakeWebSocket()
    _install_connection_metadata(manager, ws)

    validator = MagicMock()

    def disconnect_during_validation(*args, **kwargs):
        manager.connection_metadata.pop(id(ws), None)
        return ValidationResult(True)

    validator.validate_channel_sync.side_effect = disconnect_during_validation
    with patch.object(tm, "SessionLocal", return_value=_FakeDB()), patch.object(
        tm, "TenantValidator", return_value=validator
    ):
        assert asyncio.run(
            manager.subscribe(ws, "tenant:tenant-1:all", "tenant-1")
        ) is False

    cross = _FakeWebSocket(host="10.0.0.1")
    _install_connection_metadata(manager, cross)

    with patch.object(
        tm, "SessionLocal", return_value=_FakeDB()
    ), patch.object(
        manager, "_audit_subscription_security", new=AsyncMock()
    ) as audit:
        assert asyncio.run(
            manager.subscribe(cross, "tenant:tenant-2:all", "tenant-1")
        ) is False

    audit.assert_awaited_once()

    generic = _FakeWebSocket()
    _install_connection_metadata(manager, generic)

    validator.validate_channel_sync.side_effect = None
    validator.validate_channel_sync.return_value = ValidationResult(False)

    with patch.object(
        tm, "SessionLocal", return_value=_FakeDB()
    ), patch.object(
        tm, "TenantValidator", return_value=validator
    ):
        assert asyncio.run(
            manager.subscribe(
                generic,
                "tenant:tenant-1:job:1",
                "tenant-1",
            )
        ) is False


def test_send_latest_job_position_all_paths():
    manager = ConnectionManager()
    ws = _FakeWebSocket()

    asyncio.run(manager._send_latest_job_position(ws, "tenant:tenant-1:all"))

    with patch.object(manager, "_get_redis", new=AsyncMock(return_value=None)):
        asyncio.run(manager._send_latest_job_position(ws, "tenant:tenant-1:job:1"))

    redis_client = MagicMock()
    redis_client.get = AsyncMock(return_value=None)
    with patch.object(manager, "_get_redis", new=AsyncMock(return_value=redis_client)):
        asyncio.run(manager._send_latest_job_position(ws, "tenant:tenant-1:job:1"))

    redis_client.get = AsyncMock(return_value=b"bad-data")
    with patch.object(manager, "_get_redis", new=AsyncMock(return_value=redis_client)):
        with patch.object(manager, "_decode_latest_location", return_value=None):
            asyncio.run(manager._send_latest_job_position(ws, "tenant:tenant-1:job:1"))

    redis_client.get = AsyncMock(return_value=b"anything")
    mismatch = {
        "tenant_id": "tenant-2",
        "latitude": 1.0,
        "longitude": 2.0,
    }
    with patch.object(manager, "_get_redis", new=AsyncMock(return_value=redis_client)), patch.object(
        manager, "_decode_latest_location", return_value=mismatch
    ):
        asyncio.run(manager._send_latest_job_position(ws, "tenant:tenant-1:job:1"))

    latest = {
        "tenant_id": "tenant-1",
        "latitude": 1.0,
        "longitude": 2.0,
        "server_ts": (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat(),
    }
    redis_client.get = AsyncMock(return_value=b"anything")
    with patch.object(manager, "_get_redis", new=AsyncMock(return_value=redis_client)), patch.object(
        manager, "_decode_latest_location", return_value=latest.copy()
    ), patch.object(manager, "_send_json", new=AsyncMock(return_value=True)) as send:
        asyncio.run(manager._send_latest_job_position(ws, "tenant:tenant-1:job:1"))
    assert send.await_args.args[1]["source"] == "latest_cache"
    assert send.await_args.args[1]["age_seconds"] >= 0

    no_timestamp = {"tenant_id": "tenant-1", "latitude": 1.0, "longitude": 2.0}
    with patch.object(manager, "_get_redis", new=AsyncMock(return_value=redis_client)), patch.object(
        manager, "_decode_latest_location", return_value=no_timestamp
    ), patch.object(manager, "_send_json", new=AsyncMock(return_value=True)) as send:
        asyncio.run(manager._send_latest_job_position(ws, "tenant:tenant-1:job:1"))
    assert send.await_args.args[1]["age_seconds"] is None

    with patch.object(manager, "_get_redis", new=AsyncMock(return_value=redis_client)), patch.object(
        manager, "_decode_latest_location", return_value=latest.copy()
    ), patch.object(manager, "_send_json", new=AsyncMock(return_value=False)), patch.object(
        manager, "_drop_connection", new=AsyncMock()
    ) as drop:
        asyncio.run(manager._send_latest_job_position(ws, "tenant:tenant-1:job:1"))
    drop.assert_awaited_once()

    redis_client.get = AsyncMock(side_effect=RuntimeError("get failed"))
    with patch.object(manager, "_get_redis", new=AsyncMock(return_value=redis_client)):
        asyncio.run(manager._send_latest_job_position(ws, "tenant:tenant-1:job:1"))


def test_decode_latest_location_all_encodings():
    assert ConnectionManager._decode_latest_location({"a": 1}) == {"a": 1}
    assert ConnectionManager._decode_latest_location('{"a": 1}') == {"a": 1}
    assert ConnectionManager._decode_latest_location("[]") is None
    assert ConnectionManager._decode_latest_location("not-json") is None
    assert ConnectionManager._decode_latest_location(123) is None

    packed_envelope = msgpack.packb(
        {"updates": [{"a": 1}, {"a": 2}]},
        use_bin_type=True,
    )
    assert ConnectionManager._decode_latest_location(packed_envelope) == {"a": 2}

    packed_direct = msgpack.packb({"a": 3}, use_bin_type=True)
    assert ConnectionManager._decode_latest_location(packed_direct) == {"a": 3}

    assert ConnectionManager._decode_latest_location(b'{"a": 4}') == {"a": 4}
    assert ConnectionManager._decode_latest_location(b"not-json") is None


def test_manager_unsubscribe_paths():
    manager = ConnectionManager()
    ws = _FakeWebSocket()

    assert asyncio.run(
        manager.unsubscribe(ws, "tenant:tenant-1:all", "tenant-1")
    ) is False

    _install_connection_metadata(manager, ws)
    assert asyncio.run(
        manager.unsubscribe(ws, "tenant:tenant-1:all", "tenant-2")
    ) is False

    validator = MagicMock()
    validator.validate_channel_sync.return_value = ValidationResult(False)
    with patch.object(tm, "SessionLocal", return_value=_FakeDB()), patch.object(
        tm, "TenantValidator", return_value=validator
    ):
        assert asyncio.run(
            manager.unsubscribe(ws, "tenant:tenant-1:all", "tenant-1")
        ) is False

    validator.validate_channel_sync.return_value = ValidationResult(True)
    other = _FakeWebSocket()
    manager.channel_subscriptions["tenant:tenant-1:all"] = {ws, other}
    with patch.object(tm, "SessionLocal", return_value=_FakeDB()), patch.object(
        tm, "TenantValidator", return_value=validator
    ):
        assert asyncio.run(
            manager.unsubscribe(ws, "tenant:tenant-1:all", "tenant-1")
        ) is True
    assert other in manager.channel_subscriptions["tenant:tenant-1:all"]

    manager.channel_subscriptions["tenant:tenant-1:job:1"] = {ws}
    with patch.object(tm, "SessionLocal", return_value=_FakeDB()), patch.object(
        tm, "TenantValidator", return_value=validator
    ):
        assert asyncio.run(
            manager.unsubscribe(ws, "tenant:tenant-1:job:1", "tenant-1")
        ) is True
    assert "tenant:tenant-1:job:1" not in manager.channel_subscriptions

    fail_ws = _FakeWebSocket()
    _install_connection_metadata(manager, fail_ws)
    with patch.object(tm, "SessionLocal", return_value=_FakeDB()), patch.object(
        tm, "TenantValidator", return_value=validator
    ), patch.object(manager, "_send_json", new=AsyncMock(return_value=False)), patch.object(
        manager, "_drop_connection", new=AsyncMock()
    ) as drop:
        assert asyncio.run(
            manager.unsubscribe(fail_ws, "tenant:tenant-1:all", "tenant-1")
        ) is False
    drop.assert_awaited_once()


def test_prune_valid_cache_paths():
    manager = ConnectionManager()
    now = 100.0
    manager._valid_cache = {
        ("t", "tech", "expired"): (99.0, False),
        ("t", "tech", "live"): (120.0, True),
    }
    manager._prune_valid_cache(now)
    assert ("t", "tech", "expired") not in manager._valid_cache

    manager._valid_cache = {
        ("t", "tech", "live"): (120.0, True),
    }
    manager._prune_valid_cache(now)
    assert len(manager._valid_cache) == 1

    manager._valid_cache = {
        ("t", "tech", str(i)): (101.0 + i, True)
        for i in range(tm.VALID_CACHE_MAX_ENTRIES)
    }
    manager._prune_valid_cache(now)
    assert len(manager._valid_cache) == tm.VALID_CACHE_MAX_ENTRIES - 1


def test_security_audit_helpers_success_and_failure():
    manager = ConnectionManager()

    with patch.object(tm, "SessionLocal", return_value=_FakeDB()), patch.object(
        tm, "log_security_event"
    ) as log_event:
        asyncio.run(
            manager._audit_subscription_security(
                event_type="event",
                severity="warning",
                user_tenant="tenant-1",
                attempted_channel="tenant:tenant-2:all",
                ip_address="127.0.0.1",
                websocket_id="ws-1",
                action_taken="rejected",
                target_tenant="tenant-2",
            )
        )
    log_event.assert_called_once()

    with patch.object(tm, "SessionLocal", return_value=_FakeDB()), patch.object(
        tm, "log_security_event", side_effect=RuntimeError("write failed")
    ):
        asyncio.run(
            manager._audit_subscription_security(
                event_type="event",
                severity="warning",
                user_tenant="tenant-1",
                attempted_channel="tenant:tenant-2:all",
                ip_address=None,
                websocket_id="ws-1",
                action_taken="rejected",
            )
        )

    with patch.object(
        tm.asyncio,
        "to_thread",
        new=AsyncMock(side_effect=RuntimeError("thread failed")),
    ):
        asyncio.run(
            manager._audit_subscription_security(
                event_type="event",
                severity="warning",
                user_tenant="tenant-1",
                attempted_channel=None,
                ip_address=None,
                websocket_id=None,
                action_taken="rejected",
            )
        )

    with patch.object(tm, "SessionLocal", return_value=_FakeDB()), patch.object(
        tm, "log_security_event"
    ) as log_event:
        asyncio.run(
            manager._audit_broadcast_security(
                event_type="event",
                severity="critical",
                payload_tenant="tenant-1",
                target_tenant="tenant-1",
                technician_id="tech-1",
                job_id="10",
            )
        )
    log_event.assert_called_once()

    with patch.object(tm, "SessionLocal", return_value=_FakeDB()), patch.object(
        tm, "log_security_event", side_effect=RuntimeError("write failed")
    ):
        asyncio.run(
            manager._audit_broadcast_security(
                event_type="event",
                severity="critical",
                payload_tenant="tenant-1",
                target_tenant="tenant-1",
            )
        )

    with patch.object(
        tm.asyncio,
        "to_thread",
        new=AsyncMock(side_effect=RuntimeError("thread failed")),
    ):
        asyncio.run(
            manager._audit_broadcast_security(
                event_type="event",
                severity="critical",
                payload_tenant=None,
                target_tenant="tenant-1",
            )
        )


def test_validate_broadcast_all_validation_paths(setup_db):
    manager = ConnectionManager()

    # Shared technician object used by the DB-validation test cases below.
    validator = SimpleNamespace(
        tech_id="tech-1",
        technician_id=1,
    )

    # Non-tenant channel is always allowed.
    assert asyncio.run(
        manager._validate_broadcast(
            "job:10",
            {"tenant_id": "tenant-1"},
        )
    ) is True

    # Missing tenant_id must be rejected and audited.
    with patch.object(
        manager,
        "_audit_broadcast_security",
        new=AsyncMock(),
    ) as audit:
        assert asyncio.run(
            manager._validate_broadcast(
                "tenant:tenant-1:job:1",
                {},
            )
        ) is False

        audit.assert_awaited_once()

    # Payload tenant must match target tenant.
    with patch.object(
        manager,
        "_audit_broadcast_security",
        new=AsyncMock(),
    ) as audit:
        assert asyncio.run(
            manager._validate_broadcast(
                "tenant:tenant-1:job:1",
                {"tenant_id": "tenant-2"},
            )
        ) is False

        audit.assert_awaited_once()

    # Valid-cache hit.
    cache_key = ("tenant-1", "tech-1", "1")

    manager._valid_cache[cache_key] = (
        time.monotonic() + 30,
        True,
    )

    assert asyncio.run(
        manager._validate_broadcast(
            "tenant:tenant-1:job:1",
            {
                "tenant_id": "tenant-1",
                "technician_id": "tech-1",
                "job_id": "1",
            },
        )
    ) is True

    manager._valid_cache.clear()

    # Expired cache -> validation must run again.
    manager._valid_cache[cache_key] = (
        time.monotonic() - 1,
        True,
    )

    with patch.object(
        tm.asyncio,
        "to_thread",
        new=AsyncMock(return_value="valid"),
    ):
        assert asyncio.run(
            manager._validate_broadcast(
                "tenant:tenant-1:job:1",
                {
                    "tenant_id": "tenant-1",
                    "technician_id": "tech-1",
                    "job_id": "1",
                },
            )
        ) is True

    manager._valid_cache.clear()
    manager._validation_inflight.clear()

    # In-flight validation: completed future.
    loop_future = asyncio.new_event_loop()

    try:
        future = loop_future.create_future()
        future.set_result(True)

        manager._validation_inflight[cache_key] = future

        with patch.object(
            manager,
            "_audit_broadcast_security",
            new=AsyncMock(),
        ):
            assert asyncio.run(
                manager._validate_broadcast(
                    "tenant:tenant-1:job:1",
                    {
                        "tenant_id": "tenant-1",
                        "technician_id": "tech-1",
                        "job_id": "1",
                    },
                )
            ) is True

    finally:
        loop_future.close()
        manager._validation_inflight.clear()

    # In-flight validation: cancelled future.
    async def cancelled_future_case():
        key = (
            "tenant-1",
            "tech-cancel",
            "2",
        )

        future = asyncio.get_running_loop().create_future()
        future.cancel()

        manager._validation_inflight[key] = future

        with pytest.raises(asyncio.CancelledError):
            await manager._validate_broadcast(
                "tenant:tenant-1:job:2",
                {
                    "tenant_id": "tenant-1",
                    "technician_id": "tech-cancel",
                    "job_id": "2",
                },
            )

        manager._validation_inflight.clear()

    asyncio.run(cancelled_future_case())

    # In-flight validation: failed future.
    async def failed_future_case():
        key = (
            "tenant-1",
            "tech-fail",
            "3",
        )

        future = asyncio.get_running_loop().create_future()
        future.set_exception(
            RuntimeError("future failed")
        )

        manager._validation_inflight[key] = future

        result = await manager._validate_broadcast(
            "tenant:tenant-1:job:3",
            {
                "tenant_id": "tenant-1",
                "technician_id": "tech-fail",
                "job_id": "3",
            },
        )

        assert result is False

        manager._validation_inflight.clear()

    asyncio.run(failed_future_case())

    # Numeric technician id path.
    # Use the real test database so the SQLAlchemy OR condition
    # (tech_id OR technician_id) is actually executed.
    setup_db.add(
        Technician(
            technician_id=123,
            tech_id="123",
            tenant_id="tenant-1",
            technician_name="Numeric Technician",
            technician_skill="Plumber",
            technician_location="Zone A",
        )
    )

    setup_db.add(
        Job(
            id=10,
            tenant_id="tenant-1",
            customer_name="Numeric Customer",
            location="Zone B",
            issue_description="Numeric technician test",
            priority="HIGH",
            service_type="Plumbing",
            contact_number="123",
            preferred_service_date=datetime.now().date(),
            assigned_technician_id=123,
            status="ASSIGNED",
        )
    )

    setup_db.commit()

    numeric_key = (
        "tenant-1",
        "123",
        "10",
    )

    manager._valid_cache.pop(
        numeric_key,
        None,
    )

    with patch.object(
        manager,
        "_audit_broadcast_security",
        new=AsyncMock(),
    ):
        assert asyncio.run(
            manager._validate_broadcast(
                "tenant:tenant-1:job:10",
                {
                    "tenant_id": "tenant-1",
                    "technician_id": "123",
                    "job_id": "10",
                },
            )
        ) is True

    manager._valid_cache.pop(
        numeric_key,
        None,
    )

    # Remaining invalid validation paths.
    cases = [
        (
            "technician missing",
            _FakeDB(
                _FakeQuery(
                    first_value=None
                )
            ),
            "tech-x",
            "1",
        ),
        (
            "job nonnumeric",
            _FakeDB(
                _FakeQuery(
                    first_value=validator
                )
            ),
            "tech-1",
            "x",
        ),
        (
            "job missing",
            _FakeDB(
                _FakeQuery(
                    first_value=validator
                ),
                _FakeQuery(
                    first_value=None
                ),
            ),
            "tech-1",
            "99",
        ),
        (
            "assignment mismatch",
            _FakeDB(
                _FakeQuery(
                    first_value=validator
                ),
                _FakeQuery(
                    first_value=SimpleNamespace(
                        assigned_technician_id=99
                    )
                ),
            ),
            "tech-1",
            "98",
        ),
    ]

    # IMPORTANT:
    # This must be a normal synchronous function because asyncio.to_thread()
    # expects a regular callable. Using async def here would only return a
    # coroutine and would not execute the nested validate_db() function.
    def run_validate(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    for _name, db, technician_id, job_id in cases:
        manager._valid_cache.clear()
        manager._validation_inflight.clear()

        with (
            patch.object(
                tm,
                "SessionLocal",
                return_value=db,
            ),
            patch.object(
                tm.asyncio,
                "to_thread",
                new=run_validate,
            ),
            patch.object(
                manager,
                "_audit_broadcast_security",
                new=AsyncMock(),
            ),
        ):
            assert (
                asyncio.run(
                    manager._validate_broadcast(
                        f"tenant:tenant-1:job:{job_id}",
                        {
                            "tenant_id": "tenant-1",
                            "technician_id": technician_id,
                            "job_id": job_id,
                        },
                    )
                )
                is False
            )

    # Database/thread validation failure.
    # Use a unique cache key so this test cannot accidentally hit an earlier
    # cached result.
    manager._valid_cache.clear()
    manager._validation_inflight.clear()

    with (
        patch.object(
            tm.asyncio,
            "to_thread",
            new=AsyncMock(
                side_effect=RuntimeError("db down")
            ),
        ),
        patch.object(
            manager,
            "_audit_broadcast_security",
            new=AsyncMock(),
        ) as audit,
    ):
        assert asyncio.run(
            manager._validate_broadcast(
                "tenant:tenant-1:job:20",
                {
                    "tenant_id": "tenant-1",
                    "technician_id": "tech-db-error",
                    "job_id": "20",
                },
            )
        ) is False

    audit.assert_not_awaited()


def test_manager_broadcast_no_subscribers_disappearing_and_stale():
    manager = ConnectionManager()

    validator = SimpleNamespace(
        tech_id="tech-1",
        technician_id=1,
    )

    payload = {"tenant_id": "tenant-1", "technician_id": "tech-1", "job_id": "10"}

    assert asyncio.run(manager.broadcast("tenant:tenant-1:job:10", payload)) == 0

    ws = _FakeWebSocket()
    manager.channel_subscriptions["tenant:tenant-1:job:10"] = {ws}

    async def clear_then_true(channel, message):
        manager.channel_subscriptions.clear()
        return True

    with patch.object(manager, "_validate_broadcast", side_effect=clear_then_true):
        assert asyncio.run(manager.broadcast("tenant:tenant-1:job:10", payload)) == 0

    good = _FakeWebSocket()
    bad = _FakeWebSocket()
    manager.channel_subscriptions["tenant:tenant-1:job:10"] = {good, bad}
    results = [True, False]

    async def send_result(*args, **kwargs):
        return results.pop(0)

    with patch.object(
        manager,
        "_validate_broadcast",
        return_value=True,
    ), patch.object(
        manager,
        "_send_json",
        side_effect=send_result,
    ), patch.object(
        manager,
        "_drop_connection",
        new=AsyncMock(),
    ) as drop:
        sent = asyncio.run(
            manager.broadcast(
                "tenant:tenant-1:job:10",
                payload,
            )
        )

    assert sent == 1
    drop.assert_awaited_once()

    dropped_socket = drop.await_args.args[0]
    assert dropped_socket in {good, bad}
    assert drop.await_args.kwargs["reason"] == "send failed"
    assert manager._total_messages_broadcast == 1


def test_manager_cleanup_all_branches():
    manager = ConnectionManager()
    ws = _FakeWebSocket()
    _install_connection_metadata(manager, ws)
    manager.active_connections["tenant-1"] = [ws]
    manager.channel_subscriptions["tenant:tenant-1:all"] = {ws}
    manager._send_locks[id(ws)] = asyncio.Lock()
    manager._heartbeat_tasks[id(ws)] = _AwaitableTask(asyncio.CancelledError())
    asyncio.run(manager._cleanup_connection(ws, ""))
    assert "tenant-1" not in manager.active_connections
    assert "tenant:tenant-1:all" not in manager.channel_subscriptions
    assert id(ws) not in manager.connection_metadata

    missing = _FakeWebSocket()
    manager.active_connections["tenant-1"] = [_FakeWebSocket()]
    manager.connection_metadata[id(missing)] = {"tenant_id": "tenant-1"}
    manager._heartbeat_tasks[id(missing)] = _AwaitableTask(RuntimeError("task failed"))

    asyncio.run(
        manager._cleanup_connection(missing, "tenant-1")
    )

    assert "tenant-1" in manager.active_connections

    not_registered = _FakeWebSocket()
    manager.active_connections["tenant-2"] = [_FakeWebSocket()]
    manager.channel_subscriptions["tenant:tenant-2:all"] = set()
    asyncio.run(manager._cleanup_connection(not_registered, "tenant-2"))
    assert "tenant:tenant-2:all" not in manager.channel_subscriptions


def test_manager_disconnect_public_and_heartbeat_paths():
    manager = ConnectionManager()
    ws = _FakeWebSocket()
    _install_connection_metadata(manager, ws)
    manager.active_connections["tenant-1"] = [ws]
    manager._send_locks[id(ws)] = asyncio.Lock()
    asyncio.run(manager.disconnect(ws, "tenant-1"))
    assert id(ws) not in manager.connection_metadata

    heartbeat_ok = _FakeWebSocket()
    with patch.object(tm.asyncio, "sleep", new=AsyncMock(side_effect=[None, asyncio.CancelledError()])), patch.object(
        manager, "_send_json", new=AsyncMock(return_value=True)
    ) as send:
        asyncio.run(manager._heartbeat(heartbeat_ok, "tenant-1", "user-1"))
    assert send.await_count == 1

    heartbeat_fail = _FakeWebSocket()
    with patch.object(tm.asyncio, "sleep", new=AsyncMock(return_value=None)), patch.object(
        manager, "_send_json", new=AsyncMock(return_value=False)
    ), patch.object(manager, "_drop_connection", new=AsyncMock()) as drop:
        asyncio.run(manager._heartbeat(heartbeat_fail, "tenant-1", "user-1"))
    drop.assert_awaited_once()

    heartbeat_error = _FakeWebSocket()
    with patch.object(tm.asyncio, "sleep", new=AsyncMock(side_effect=RuntimeError("boom"))):
        asyncio.run(manager._heartbeat(heartbeat_error, "tenant-1", "user-1"))


def test_manager_metrics():
    manager = ConnectionManager()
    ws = _FakeWebSocket()
    manager.active_connections["tenant-1"] = [ws, _FakeWebSocket()]
    manager.channel_subscriptions["tenant:tenant-1:all"] = {ws}
    manager._total_messages_broadcast = 7
    manager._total_dropped_connections = 3
    manager._valid_cache[("tenant-1", "tech-1", "1")] = (time.monotonic() + 10, True)

    metrics = manager.get_metrics()
    assert metrics["active_connections_by_tenant"]["tenant-1"] == 2
    assert metrics["total_active_connections"] == 2
    assert metrics["total_messages_broadcast"] == 7
    assert metrics["total_dropped_connections"] == 3
    assert metrics["validation_cache_entries"] == 1
    assert metrics["subscriptions"] == 1
    assert metrics["heartbeat_interval_s"] == tm.HEARTBEAT_INTERVAL_S
    assert metrics["max_subscriptions_per_connection"] == tm.MAX_SUBSCRIPTIONS_PER_CONNECTION


def test_tracking_manager_rejects_missing_jwt_secret_at_import():
    """Cover the import-time configuration guard without mutating the live module."""
    source_path = tm.__file__
    probe_name = "app.services._tracking_manager_missing_secret_probe"
    original_secret = os.environ.get("JWT_SECRET")

    os.environ["JWT_SECRET"] = ""
    try:
        spec = importlib.util.spec_from_file_location(probe_name, source_path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        with pytest.raises(RuntimeError, match="JWT_SECRET must be explicitly configured"):
            spec.loader.exec_module(module)
    finally:
        if original_secret is None:
            os.environ.pop("JWT_SECRET", None)
        else:
            os.environ["JWT_SECRET"] = original_secret
