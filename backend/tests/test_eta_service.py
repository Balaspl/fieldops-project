import pytest
import asyncio
import json
import time
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from app.main import app
from app.models import Job, Technician, GPSPing
from app.database import Base, get_db
from app.redis_client import get_redis_client
from app.services.google_maps_client import GoogleMapsClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

# Force standard synchronous execution wrapper for async tests
def run_async(func):
    import asyncio
    from functools import wraps
    @wraps(func)
    def wrapper(*args, **kwargs):
        return asyncio.run(func(*args, **kwargs))
    return wrapper

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

# Mock Redis
class MockRedis:
    def __init__(self):
        self.data = {}
        self.ttls = {}

    def get(self, key):
        return self.data.get(key)

    def setex(self, key, seconds, value):
        self.data[key] = str(value)
        self.ttls[key] = seconds

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

    def delete(self, key):
        if key in self.data:
            del self.data[key]
        if key in self.ttls:
            del self.ttls[key]

    def flushall(self):
        self.data.clear()
        self.ttls.clear()

mock_redis = MockRedis()

def override_get_redis():
    return mock_redis

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "test-api-key")
    monkeypatch.setattr("app.database.SessionLocal", TestingSessionLocal)
    monkeypatch.setattr("app.redis_client.redis_manager", mock_redis)
    monkeypatch.setattr("app.redis_client.get_redis_client", lambda: mock_redis)

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    
    db.query(GPSPing).delete()
    db.query(Job).delete()
    db.query(Technician).delete()
    db.commit()

    mock_redis.flushall()
    
    yield db
    db.close()

@pytest.fixture(autouse=True)
def apply_overrides():
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis_client] = override_get_redis
    yield
    app.dependency_overrides.clear()


# Helper to mock aiohttp responses
class MockResponse:
    def __init__(self, json_data, status=200):
        self._json_data = json_data
        self.status = status

    async def json(self):
        return self._json_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


def test_eta_calculation_with_valid_gps_and_job_site(setup_db):
    db = setup_db

    # Seed technician
    tech = Technician(
        tech_id="tech-123",
        technician_name="John Doe",
        technician_skill="HVAC",
        technician_location="13.0827,80.2707",
        tenant_id="tenant-1"
    )
    db.add(tech)

    # Seed job with site coordinates
    job = Job(
        id=101,
        customer_name="Alice",
        location="13.0569,80.2425",
        site_latitude=13.0569,
        site_longitude=80.2425,
        site_address="123 Main St, Chennai",
        issue_description="Leak",
        priority="HIGH",
        service_type="Plumbing",
        contact_number="123456",
        status="ASSIGNED",
        assigned_technician_id=tech.technician_id,
        tenant_id="tenant-1",
        preferred_service_date=datetime.now(timezone.utc).date()
    )
    db.add(job)

    # Seed recent GPS ping (2 minutes ago)
    recent_time = datetime.now(timezone.utc) - timedelta(minutes=2)
    ping = GPSPing(
        id="ping-1",
        technician_id="tech-123",
        job_id="101",
        latitude=13.0827,
        longitude=80.2707,
        timestamp=recent_time,
        tenant_id="tenant-1"
    )
    db.add(ping)
    db.commit()

    # Mock Google Maps response
    mock_maps_response = {
        "status": "OK",
        "rows": [{
            "elements": [{
                "distance": {"value": 12500},
                "duration": {"value": 1680},
                "duration_in_traffic": {"value": 2100},
                "status": "OK"
            }]
        }]
    }

    with patch("aiohttp.ClientSession.get", return_value=MockResponse(mock_maps_response, 200)):
        response = client.get(
            "/api/v1/eta?technician_id=tech-123&job_id=101",
            headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token-admin"}
        )

        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "calculated"
        assert data["technician_id"] == "tech-123"
        assert data["job_id"] == "101"
        assert data["duration_minutes"] == 35.0 # 2100 / 60
        assert data["distance_km"] == 12.5 # 12500 / 1000
        assert data["traffic_delay_minutes"] == 7.0 # (2100 - 1680) / 60

        # Verify ETA is a future timestamp
        eta_time = datetime.fromisoformat(data["eta"].replace("Z", "+00:00"))
        assert eta_time > datetime.now(timezone.utc)


def test_redis_cache_stores_eta_for_30_seconds(setup_db):
    db = setup_db

    tech = Technician(tech_id="tech-123", technician_name="John Doe", technician_skill="HVAC", technician_location="1,1", tenant_id="tenant-1")
    db.add(tech)
    job = Job(id=101, customer_name="Alice", location="2,2", site_latitude=2.0, site_longitude=2.0, site_address="Addr", issue_description="Leak", priority="HIGH", service_type="Plumbing", contact_number="123", tenant_id="tenant-1", preferred_service_date=datetime.now(timezone.utc).date())
    db.add(job)
    ping = GPSPing(id="p1", technician_id="tech-123", job_id="101", latitude=1.0, longitude=1.0, timestamp=datetime.now(timezone.utc), tenant_id="tenant-1")
    db.add(ping)
    db.commit()

    mock_maps_response = {
        "status": "OK",
        "rows": [{"elements": [{"distance": {"value": 1000}, "duration": {"value": 100}, "duration_in_traffic": {"value": 120}, "status": "OK"}]}]
    }

    # Miss call -> sets cache
    with patch("aiohttp.ClientSession.get", return_value=MockResponse(mock_maps_response, 200)):
        response = client.get("/api/v1/eta?technician_id=tech-123&job_id=101", headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token-admin"})
        assert response.status_code == 200

    # Verify key exists in Redis with TTL 30
    cache_key = "eta:tech-123:101"
    assert mock_redis.get(cache_key) is not None
    assert mock_redis.ttl(cache_key) == 30

    # Call again -> should return cached result without hitting API (raise inside patch to confirm)
    with patch("aiohttp.ClientSession.get", side_effect=Exception("API called")):
        response = client.get("/api/v1/eta?technician_id=tech-123&job_id=101", headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token-admin"})
        assert response.status_code == 200
        assert response.json()["status"] == "calculated"


def test_missing_gps_data_returns_unknown_status(setup_db):
    db = setup_db

    tech = Technician(tech_id="tech-123", technician_name="John Doe", technician_skill="HVAC", technician_location="1,1", tenant_id="tenant-1")
    db.add(tech)
    job = Job(id=101, customer_name="Alice", location="2,2", site_latitude=2.0, site_longitude=2.0, site_address="Addr", issue_description="Leak", priority="HIGH", service_type="Plumbing", contact_number="123", tenant_id="tenant-1", preferred_service_date=datetime.now(timezone.utc).date())
    db.add(job)
    db.commit()

    # No GPS pings seeded for this technician
    response = client.get("/api/v1/eta?technician_id=tech-123&job_id=101", headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token-admin"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "unknown"
    assert data["last_known_location"]["latitude"] is None
    assert "No recent GPS data" in data["message"]


def test_stale_gps_returns_unknown_status(setup_db):
    db = setup_db

    tech = Technician(tech_id="tech-123", technician_name="John Doe", technician_skill="HVAC", technician_location="1,1", tenant_id="tenant-1")
    db.add(tech)
    job = Job(id=101, customer_name="Alice", location="2,2", site_latitude=2.0, site_longitude=2.0, site_address="Addr", issue_description="Leak", priority="HIGH", service_type="Plumbing", contact_number="123", tenant_id="tenant-1", preferred_service_date=datetime.now(timezone.utc).date())
    db.add(job)
    
    # Ping 6 minutes ago
    stale_time = datetime.now(timezone.utc) - timedelta(minutes=6)
    ping = GPSPing(id="p1", technician_id="tech-123", job_id="101", latitude=1.0, longitude=1.1, timestamp=stale_time, tenant_id="tenant-1")
    db.add(ping)
    db.commit()

    response = client.get("/api/v1/eta?technician_id=tech-123&job_id=101", headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token-admin"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "unknown"
    assert data["last_known_location"]["latitude"] == 1.0
    assert "No recent GPS data" in data["message"]


def test_missing_job_site_coordinates_returns_404(setup_db):
    db = setup_db

    tech = Technician(tech_id="tech-123", technician_name="John Doe", technician_skill="HVAC", technician_location="1,1", tenant_id="tenant-1")
    db.add(tech)
    # Job site_latitude and site_longitude are NULL
    job = Job(id=101, customer_name="Alice", location="2,2", site_latitude=None, site_longitude=None, site_address="Addr", issue_description="Leak", priority="HIGH", service_type="Plumbing", contact_number="123", tenant_id="tenant-1", preferred_service_date=datetime.now(timezone.utc).date())
    db.add(job)
    db.commit()

    response = client.get("/api/v1/eta?technician_id=tech-123&job_id=101", headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token-admin"})
    assert response.status_code == 404
    assert "coordinates not found" in response.json()["detail"]


def test_maps_api_failure_triggers_straight_line_fallback(setup_db):
    db = setup_db

    tech = Technician(tech_id="tech-123", technician_name="John Doe", technician_skill="HVAC", technician_location="0,0", tenant_id="tenant-1")
    db.add(tech)
    job = Job(id=101, customer_name="Alice", location="0,0", site_latitude=0.0, site_longitude=0.1, site_address="Addr", issue_description="Leak", priority="HIGH", service_type="Plumbing", contact_number="123", tenant_id="tenant-1", preferred_service_date=datetime.now(timezone.utc).date())
    db.add(job)
    ping = GPSPing(id="p1", technician_id="tech-123", job_id="101", latitude=0.0, longitude=0.0, timestamp=datetime.now(timezone.utc), tenant_id="tenant-1")
    db.add(ping)
    db.commit()

    # Maps API throws network exception
    with patch("aiohttp.ClientSession.get", side_effect=Exception("API down")):
        response = client.get("/api/v1/eta?technician_id=tech-123&job_id=101", headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token-admin"})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "estimated"
        assert data["confidence"] == "low"
        assert data["fallback_reason"] == "maps_unavailable"
        assert data["distance_km"] > 0.0
        assert "disclaimer" in data


def test_batch_eta_calculation_for_3_technicians(setup_db):
    db = setup_db

    # Seed 3 technicians
    t1 = Technician(tech_id="tech-1", technician_name="T1", technician_skill="HVAC", technician_location="0,0", tenant_id="tenant-1")
    t2 = Technician(tech_id="tech-2", technician_name="T2", technician_skill="HVAC", technician_location="0,0", tenant_id="tenant-1")
    t3 = Technician(tech_id="tech-3", technician_name="T3", technician_skill="HVAC", technician_location="0,0", tenant_id="tenant-1")
    db.add_all([t1, t2, t3])

    job = Job(id=101, customer_name="Alice", location="0.1,0.1", site_latitude=0.1, site_longitude=0.1, site_address="Addr", issue_description="Leak", priority="HIGH", tenant_id="tenant-1", preferred_service_date=datetime.now(timezone.utc).date(), service_type="Plumbing", contact_number="123")
    db.add(job)

    p1 = GPSPing(id="p1", technician_id="tech-1", job_id="101", latitude=0.0, longitude=0.0, timestamp=datetime.now(timezone.utc), tenant_id="tenant-1")
    p2 = GPSPing(id="p2", technician_id="tech-2", job_id="101", latitude=0.01, longitude=0.01, timestamp=datetime.now(timezone.utc), tenant_id="tenant-1")
    p3 = GPSPing(id="p3", technician_id="tech-3", job_id="101", latitude=0.02, longitude=0.02, timestamp=datetime.now(timezone.utc), tenant_id="tenant-1")
    db.add_all([p1, p2, p3])
    db.commit()

    mock_batch_response = {
        "status": "OK",
        "rows": [
            {"elements": [{"distance": {"value": 10000}, "duration": {"value": 600}, "status": "OK"}]},
            {"elements": [{"distance": {"value": 9000}, "duration": {"value": 540}, "status": "OK"}]},
            {"elements": [{"distance": {"value": 8000}, "duration": {"value": 480}, "status": "OK"}]}
        ]
    }

    with patch("aiohttp.ClientSession.get", return_value=MockResponse(mock_batch_response, 200)):
        payload = {
            "technician_ids": ["tech-1", "tech-2", "tech-3"],
            "job_id": 101
        }
        response = client.post(
            "/api/v1/eta/batch",
            json=payload,
            headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token-admin"}
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        assert data[0]["distance_km"] == 10.0
        assert data[1]["distance_km"] == 9.0
        assert data[2]["distance_km"] == 8.0


def test_multi_tenant_isolation(setup_db):
    db = setup_db

    # Tech 1 belongs to tenant-1
    tech = Technician(tech_id="tech-123", technician_name="John Doe", technician_skill="HVAC", technician_location="1,1", tenant_id="tenant-1")
    db.add(tech)
    
    # Job belongs to tenant-2
    job = Job(id=101, customer_name="Alice", location="2,2", site_latitude=2.0, site_longitude=2.0, site_address="Addr", issue_description="Leak", priority="HIGH", service_type="Plumbing", contact_number="123", tenant_id="tenant-2", preferred_service_date=datetime.now(timezone.utc).date())
    db.add(job)
    db.commit()

    # Call with tenant-1 header. The job lookup should raise Forbidden (403 Access Denied)
    response = client.get("/api/v1/eta?technician_id=tech-123&job_id=101", headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token-admin"})
    assert response.status_code == 403
