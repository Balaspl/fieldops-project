"""
tests/test_eta_updates.py
─────────────────────────
Integration tests for the real-time ETA update mechanism.

Chain under test:
  GPSPing INSERT → after_insert event listener
      ├─ Redis throttle check (30 s per job)
      ├─ Redis ETA key invalidation
      └─ update_eta_task.delay()
              └─ ETAService.calculate_eta()
                      └─ ws_manager.broadcast_to_job()
                      └─ ETAHistory persisted

All external dependencies (Redis, Google Maps API, Socket.io) are mocked so
that the tests run entirely in memory with SQLite.
"""

import asyncio
import uuid
import pytest
from datetime import datetime, timezone, date
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# ── App internals ─────────────────────────────────────────────────────────────
from app.database import Base, get_db
from app.models import Job, Technician, GPSPing, ETAHistory
from app.main import app
from fastapi.testclient import TestClient


# ── Shared SQLite in-memory database ─────────────────────────────────────────
SQLALCHEMY_DATABASE_URL = "sqlite://"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


# ── Minimal MockRedis ─────────────────────────────────────────────────────────
class MockRedis:
    def __init__(self):
        self.data = {}
        self.ttls = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value, ex=None):
        self.data[key] = str(value)
        if ex:
            self.ttls[key] = ex

    def setex(self, key, seconds, value):
        self.data[key] = str(value)
        self.ttls[key] = seconds

    def delete(self, *keys):
        for key in keys:
            self.data.pop(key, None)
            self.ttls.pop(key, None)

    def exists(self, key):
        return 1 if key in self.data else 0

    def ttl(self, key):
        return self.ttls.get(key, -2)

    def incr(self, key):
        val = int(self.data.get(key, 0)) + 1
        self.data[key] = str(val)
        return val

    def incrbyfloat(self, key, amount):
        val = float(self.data.get(key, 0.0)) + amount
        self.data[key] = str(val)
        return val

    def keys(self, pattern):
        import fnmatch
        return [k for k in self.data if fnmatch.fnmatch(k, pattern)]

    def expire(self, key, seconds):
        self.ttls[key] = seconds


mock_redis = MockRedis()


def get_mock_redis():
    return mock_redis


# ── Fixtures ─────────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def setup_db_and_redis():
    """Create all tables, wire overrides, reset Redis before each test."""
    Base.metadata.create_all(bind=engine)
    mock_redis.data.clear()
    mock_redis.ttls.clear()
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def seed_tech_and_job(db):
    """Insert a Technician + Job into the test database and return their IDs."""
    tech_uuid = str(uuid.uuid4())

    tech = Technician(
        tech_id=tech_uuid,
        tenant_id="tenant-1",
        technician_name="Test Technician",
        technician_skill="Plumbing",
        technician_location="0,0",
    )
    job = Job(
        tenant_id="tenant-1",
        customer_name="Alice",
        location="Nairobi",
        issue_description="Leak",
        priority="HIGH",
        service_type="Plumbing",
        contact_number="0700000001",
        preferred_service_date=date.today(),
        status="ASSIGNED",
        site_latitude=1.2921,
        site_longitude=36.8219,
    )
    db.add_all([tech, job])
    db.commit()
    db.refresh(tech)
    db.refresh(job)
    return tech_uuid, job.id  # job.id is an Integer PK


# ─────────────────────────────────────────────────────────────────────────────
# Helper: build a minimal ETA result dict
# ─────────────────────────────────────────────────────────────────────────────
def _fake_eta_result(eta_iso="2025-01-01T10:15:00+00:00"):
    return {
        "eta": eta_iso,
        "duration_seconds": 900,
        "distance_meters": 5000,
        "traffic_delay_seconds": 120,
        "confidence": "calculated",
        "disclaimer": None,
    }


# ═════════════════════════════════════════════════════════════════════════════
# 1. WebSocketManager.broadcast_to_job
# ═════════════════════════════════════════════════════════════════════════════
class TestWebSocketManager:
    def test_broadcast_emits_eta_update_event(self):
        """broadcast_to_job should call sio.emit with the correct room and event."""
        from app.services.socket_manager import WebSocketManager

        manager = WebSocketManager()
        payload = {"type": "eta_update", "job_id": "42", "eta": "2025-01-01T10:00:00Z"}

        with patch("app.services.socket_manager.sio") as mock_sio:
            mock_sio.emit = AsyncMock()
            asyncio.run(
                manager.broadcast_to_job("42", payload)
            )
            mock_sio.emit.assert_called_once_with("eta_update", payload, room="job:42")

    def test_broadcast_handles_emit_failure_gracefully(self):
        """broadcast_to_job should log errors but NOT raise when sio.emit fails."""
        from app.services.socket_manager import WebSocketManager

        manager = WebSocketManager()

        with patch("app.services.socket_manager.sio") as mock_sio:
            mock_sio.emit = AsyncMock(side_effect=RuntimeError("socket error"))
            # Should not raise
            asyncio.run(
                manager.broadcast_to_job("99", {"eta": "x"})
            )


# ═════════════════════════════════════════════════════════════════════════════
# 2. subscribe_to_job Socket.io event
# ═════════════════════════════════════════════════════════════════════════════
class TestSubscribeToJob:
    def test_subscribe_enters_job_room(self):
        """subscribe_to_job event handler should call sio.enter_room with job:<id>."""
        from app.services import socket_manager

        identity = {"user_id": "customer-1", "role": "customer"}
        mock_db = MagicMock()
        with patch.object(
            socket_manager.sio,
            "get_session",
            new=AsyncMock(return_value=identity),
        ), patch.object(
            socket_manager,
            "SessionLocal",
            return_value=mock_db,
        ), patch.object(
            socket_manager,
            "_can_access_job",
            return_value=True,
        ), patch.object(
            socket_manager.sio,
            "enter_room",
            new=AsyncMock(),
        ) as mock_enter:
            asyncio.run(
                socket_manager.subscribe_to_job("sid-abc", {"job_id": "7"})
            )
            mock_enter.assert_called_once_with("sid-abc", "job:7")
        mock_db.close.assert_called_once()

    def test_subscribe_ignores_missing_job_id(self):
        """subscribe_to_job should not call enter_room when job_id is absent."""
        from app.services import socket_manager

        with patch.object(socket_manager.sio, "enter_room", new=AsyncMock()) as mock_enter:
            asyncio.run(
                socket_manager.subscribe_to_job("sid-abc", {})
            )
            mock_enter.assert_not_called()


# ═════════════════════════════════════════════════════════════════════════════
# 3. GPSPing after_insert event listener (throttle + task dispatch)
# ═════════════════════════════════════════════════════════════════════════════
class TestGPSPingEventListener:
    def test_first_ping_dispatches_task(self, db, seed_tech_and_job):
        """First GPS ping for a job should always dispatch update_eta_task."""
        tech_uuid, job_id = seed_tech_and_job

        with patch("app.redis_client.get_redis_client", return_value=mock_redis), \
             patch("app.tasks.update_eta_task.delay") as mock_delay:

            ping = GPSPing(
                id=str(uuid.uuid4()),
                technician_id=tech_uuid,
                job_id=str(job_id),  # GPSPing.job_id is String
                tenant_id="tenant-1",
                latitude=1.290,
                longitude=36.817,
                accuracy=5.0,
                timestamp=datetime.now(timezone.utc),
            )
            db.add(ping)
            db.commit()

            mock_delay.assert_called_once()

    def test_second_ping_within_30s_is_throttled(self, db, seed_tech_and_job):
        """A second ping within 30 s should NOT dispatch another task (throttle)."""
        tech_uuid, job_id = seed_tech_and_job

        # Pre-populate the throttle key to simulate a recent dispatch
        throttle_key = f"eta:throttle:{job_id}"
        mock_redis.data[throttle_key] = "1"
        mock_redis.ttls[throttle_key] = 29  # 29 s remaining

        with patch("app.redis_client.get_redis_client", return_value=mock_redis), \
             patch("app.tasks.update_eta_task.delay") as mock_delay:

            ping = GPSPing(
                id=str(uuid.uuid4()),
                technician_id=tech_uuid,
                job_id=str(job_id),
                tenant_id="tenant-1",
                latitude=1.291,
                longitude=36.818,
                accuracy=5.0,
                timestamp=datetime.now(timezone.utc),
            )
            db.add(ping)
            db.commit()

            mock_delay.assert_not_called()

    def test_eta_redis_key_invalidated_on_new_ping(self, db, seed_tech_and_job):
        """Inserting a new ping should delete the cached ETA key from Redis."""
        tech_uuid, job_id = seed_tech_and_job

        eta_key = f"eta:{tech_uuid}:{job_id}"
        mock_redis.data[eta_key] = '{"eta": "stale"}'

        with patch("app.redis_client.get_redis_client", return_value=mock_redis), \
             patch("app.tasks.update_eta_task.delay"):

            ping = GPSPing(
                id=str(uuid.uuid4()),
                technician_id=tech_uuid,
                job_id=str(job_id),
                tenant_id="tenant-1",
                latitude=1.292,
                longitude=36.819,
                accuracy=5.0,
                timestamp=datetime.now(timezone.utc),
            )
            db.add(ping)
            db.commit()

            assert eta_key not in mock_redis.data, "Stale ETA cache key should have been evicted"

    def test_listener_skips_dispatch_for_non_active_job_status(self, db):
        """update_eta_task should NOT be dispatched for COMPLETED jobs."""
        tech_uuid = str(uuid.uuid4())

        tech = Technician(
            tech_id=tech_uuid,
            tenant_id="tenant-1",
            technician_name="T",
            technician_skill="Electrical",
            technician_location="0,0",
        )
        job = Job(
            tenant_id="tenant-1",
            customer_name="Bob",
            location="Mombasa",
            issue_description="Wiring",
            priority="LOW",
            service_type="Electrical",
            contact_number="0700000002",
            preferred_service_date=date.today(),
            status="completed",  # non-active — listener should skip
            site_latitude=4.0,
            site_longitude=39.0,
        )
        db.add_all([tech, job])
        db.commit()
        db.refresh(job)

        with patch("app.redis_client.get_redis_client", return_value=mock_redis), \
             patch("app.tasks.update_eta_task.delay") as mock_delay:

            ping = GPSPing(
                id=str(uuid.uuid4()),
                technician_id=tech_uuid,
                job_id=str(job.id),
                tenant_id="tenant-1",
                latitude=4.0,
                longitude=39.0,
                accuracy=5.0,
                timestamp=datetime.now(timezone.utc),
            )
            db.add(ping)
            db.commit()

            mock_delay.assert_not_called()


# ═════════════════════════════════════════════════════════════════════════════
# 4. update_eta_task Celery task (unit)
# ═════════════════════════════════════════════════════════════════════════════
class TestUpdateETATask:
    """
    Unit-test the Celery task body by calling the underlying function directly
    (bypassing Celery worker infrastructure) and mocking all external calls.
    """

    def _run_task(self, tech_uuid, job_id, ping_id=None):
        """Invoke update_eta_task synchronously via Celery eager execution."""
        from app.tasks import update_eta_task
        from app.celery_app import celery_app
        celery_app.conf.task_always_eager = True
        result = update_eta_task.apply(
            args=[tech_uuid, job_id],
            kwargs={"ping_id": ping_id},
        )
        # In eager mode, exceptions are re-raised; return the result value
        return result.get(propagate=False)

    def test_task_persists_eta_history(self, db, seed_tech_and_job):
        """Successful ETA calculation should write an ETAHistory row."""
        tech_uuid, job_id = seed_tech_and_job
        ping_id = str(uuid.uuid4())
        fake_eta = _fake_eta_result()

        with patch("app.tasks.ETAService") as MockETAService, \
             patch("app.tasks.ws_manager") as mock_ws, \
             patch("app.tasks.SessionLocal", return_value=db):

            instance = MockETAService.return_value
            instance.calculate_eta = AsyncMock(return_value=fake_eta)
            mock_ws.broadcast_to_job = AsyncMock()

            self._run_task(tech_uuid, job_id, ping_id=ping_id)

        row = db.query(ETAHistory).filter_by(job_id=job_id).first()
        assert row is not None, "ETAHistory row should have been persisted"
        # Verify unit conversions: 900s → 15.0 min, 5000m → 5.0 km
        assert row.duration_minutes == pytest.approx(15.0, rel=0.01)
        assert row.distance_km == pytest.approx(5.0, rel=0.01)
        assert row.source_ping_id == ping_id

    def test_task_broadcasts_correct_payload(self, db, seed_tech_and_job):
        """Task should broadcast the correctly shaped payload to the job room."""
        tech_uuid, job_id = seed_tech_and_job
        fake_eta = _fake_eta_result("2025-06-25T12:00:00+00:00")
        ping_id = str(uuid.uuid4())

        with patch("app.tasks.ETAService") as MockETAService, \
             patch("app.tasks.ws_manager") as mock_ws, \
             patch("app.tasks.SessionLocal", return_value=db):

            instance = MockETAService.return_value
            instance.calculate_eta = AsyncMock(return_value=fake_eta)
            mock_ws.broadcast_to_job = AsyncMock()

            self._run_task(tech_uuid, job_id, ping_id=ping_id)

        mock_ws.broadcast_to_job.assert_called_once()
        call_args = mock_ws.broadcast_to_job.call_args
        room_job_id = call_args[0][0]   # first positional arg (job_id for room)
        payload = call_args[0][1]        # second positional arg

        assert room_job_id == str(job_id)
        assert payload["type"] == "eta_update"
        assert payload["job_id"] == str(job_id)
        assert payload["technician_id"] == tech_uuid
        assert payload["eta"] == "2025-06-25T12:00:00+00:00"
        assert payload["duration_minutes"] == pytest.approx(15.0, rel=0.01)
        assert payload["distance_km"] == pytest.approx(5.0, rel=0.01)
        assert payload["traffic_delay_minutes"] == pytest.approx(2.0, rel=0.01)
        assert "updated_at" in payload

    def test_task_handles_none_eta_result(self, db, seed_tech_and_job):
        """If ETAService returns None, no history row or broadcast should occur."""
        tech_uuid, job_id = seed_tech_and_job

        with patch("app.tasks.ETAService") as MockETAService, \
             patch("app.tasks.ws_manager") as mock_ws, \
             patch("app.tasks.SessionLocal", return_value=db):

            instance = MockETAService.return_value
            instance.calculate_eta = AsyncMock(return_value=None)
            mock_ws.broadcast_to_job = AsyncMock()

            self._run_task(tech_uuid, job_id)

        rows = db.query(ETAHistory).all()
        assert len(rows) == 0
        mock_ws.broadcast_to_job.assert_not_called()

    def test_task_retries_on_exception(self, db, seed_tech_and_job):
        """Task should log the error when ETAService raises (retry logic present)."""
        tech_uuid, job_id = seed_tech_and_job
        from app.tasks import update_eta_task
        from app.celery_app import celery_app
        celery_app.conf.task_always_eager = True

        with patch("app.tasks.ETAService") as MockETAService, \
             patch("app.tasks.ws_manager"), \
             patch("app.tasks.SessionLocal", return_value=db):

            instance = MockETAService.return_value
            instance.calculate_eta = AsyncMock(side_effect=RuntimeError("maps down"))

            # In eager mode with max_retries=2, the task will retry and eventually
            # exhaust retries. We verify no ETAHistory was persisted.
            result = update_eta_task.apply(args=[tech_uuid, job_id])
            result.get(propagate=False)  # Don't re-raise; just drain

        rows = db.query(ETAHistory).all()
        assert len(rows) == 0, "No ETAHistory should be persisted when task fails"

    def test_task_with_fallback_confidence(self, db, seed_tech_and_job):
        """Task should persist ETAHistory with correct unit conversions for fallback results."""
        tech_uuid, job_id = seed_tech_and_job
        ping_id = str(uuid.uuid4())
        fallback_eta = {
            "eta": "2025-01-01T10:30:00+00:00",
            "duration_seconds": 1200,
            "distance_meters": 8000,
            "traffic_delay_seconds": 0,
            "confidence": "estimated",
            "disclaimer": "ETA is an estimate. Google Maps API is currently unavailable.",
        }

        with patch("app.tasks.ETAService") as MockETAService, \
             patch("app.tasks.ws_manager") as mock_ws, \
             patch("app.tasks.SessionLocal", return_value=db):

            instance = MockETAService.return_value
            instance.calculate_eta = AsyncMock(return_value=fallback_eta)
            mock_ws.broadcast_to_job = AsyncMock()

            self._run_task(tech_uuid, job_id, ping_id=ping_id)

        row = db.query(ETAHistory).filter_by(job_id=job_id).first()
        assert row is not None
        assert row.duration_minutes == pytest.approx(20.0, rel=0.01)   # 1200 / 60
        assert row.distance_km == pytest.approx(8.0, rel=0.01)          # 8000 / 1000

        call_args = mock_ws.broadcast_to_job.call_args
        payload = call_args[0][1]
        assert payload["confidence"] == "estimated"
        assert "unavailable" in (payload["disclaimer"] or "").lower()


# ═════════════════════════════════════════════════════════════════════════════
# 5. ETAHistory model
# ═════════════════════════════════════════════════════════════════════════════
class TestETAHistoryModel:
    def test_eta_history_can_be_stored_and_queried(self, db, seed_tech_and_job):
        """ETAHistory rows can be inserted and queried correctly."""
        _, job_id = seed_tech_and_job
        now = datetime.now(timezone.utc)
        ping_id = str(uuid.uuid4())

        # Insert a GPSPing first to satisfy source_ping_id FK
        tech_uuid = db.query(Technician).first().tech_id
        ping = GPSPing(
            id=ping_id,
            technician_id=tech_uuid,
            job_id=str(job_id),
            tenant_id="tenant-1",
            latitude=1.290,
            longitude=36.817,
            accuracy=5.0,
            timestamp=now,
        )
        with patch("app.redis_client.get_redis_client", return_value=mock_redis), \
             patch("app.tasks.update_eta_task.delay"):
            db.add(ping)
            db.commit()

        row = ETAHistory(
            id=str(uuid.uuid4()),
            job_id=job_id,
            tenant_id="tenant-1",
            eta=now,
            duration_minutes=10.0,
            distance_km=3.0,
            traffic_delay_minutes=1.0,
            source_ping_id=ping_id,
        )
        db.add(row)
        db.commit()

        fetched = db.query(ETAHistory).filter_by(job_id=job_id).first()
        assert fetched is not None
        assert fetched.duration_minutes == pytest.approx(10.0)
        assert fetched.distance_km == pytest.approx(3.0)

    def test_multiple_eta_history_rows_per_job(self, db, seed_tech_and_job):
        """Multiple ETAHistory rows for the same job should all be stored."""
        tech_uuid, job_id = seed_tech_and_job
        now = datetime.now(timezone.utc)

        # Create 3 GPS pings and 3 history rows
        for i in range(3):
            ping_id = str(uuid.uuid4())
            ping = GPSPing(
                id=ping_id,
                technician_id=tech_uuid,
                job_id=str(job_id),
                tenant_id="tenant-1",
                latitude=1.29 + i * 0.001,
                longitude=36.817,
                accuracy=5.0,
                timestamp=now,
            )
            with patch("app.redis_client.get_redis_client", return_value=mock_redis), \
                 patch("app.tasks.update_eta_task.delay"):
                db.add(ping)
                db.commit()

            history_row = ETAHistory(
                id=str(uuid.uuid4()),
                job_id=job_id,
                tenant_id="tenant-1",
                eta=now,
                duration_minutes=float(5 * (i + 1)),
                distance_km=float(1 * (i + 1)),
                traffic_delay_minutes=0.5,
                source_ping_id=ping_id,
            )
            db.add(history_row)
            db.commit()

        rows = db.query(ETAHistory).filter_by(job_id=job_id).all()
        assert len(rows) == 3
