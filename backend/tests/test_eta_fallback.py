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
from app.services.ola_map_client import MapsAPIException
from app.services.ola_map_client import OlaMapsClient
from app.services.fallback_eta_service import FallbackETAService

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker


# ============================================================
# Setup test DB
# ============================================================

SQLALCHEMY_DATABASE_URL = "sqlite://"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


# ============================================================
# Mock Redis
# ============================================================

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


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(autouse=True)
def setup_db(monkeypatch):
    monkeypatch.setenv(
        "GOOGLE_MAPS_API_KEY",
        "test-api-key",
    )

    monkeypatch.setattr(
        "app.database.SessionLocal",
        TestingSessionLocal,
    )

    monkeypatch.setattr(
        "app.redis_client.redis_manager",
        mock_redis,
    )

    monkeypatch.setattr(
        "app.redis_client.get_redis_client",
        lambda: mock_redis,
    )

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


# ============================================================
# Mock aiohttp response
# ============================================================

class MockResponse:
    def __init__(self, json_data, status=200):
        self._json_data = json_data
        self.status = status

    async def json(self):
        return self._json_data

    async def __aenter__(self):
        return self

    async def __aexit__(
        self,
        exc_type,
        exc_val,
        exc_tb,
    ):
        pass


# ============================================================
# Haversine distance
# ============================================================

def test_haversine_distance_accuracy():
    service = FallbackETAService()

    # Paris -> Lyon
    dist = service.calculate_haversine_distance(
        48.8566,
        2.3522,
        45.7640,
        4.8357,
    )

    assert abs(dist - 392.2) / 392.2 < 0.005


# ============================================================
# Urban / highway route fallback
# ============================================================

def test_urban_vs_highway_routes():
    service = FallbackETAService()

    # Urban
    res_urban = service.calculate_fallback_eta(
        13.0827,
        80.2707,
        13.0732,
        80.2525,
        "test",
    )

    assert res_urban["route_type"] == "urban"
    assert res_urban["average_speed_kmh"] == 30
    assert res_urban["buffer_minutes"] == 5
    assert res_urban["duration_minutes"] > 5.0

    # Highway
    res_highway = service.calculate_fallback_eta(
        13.0827,
        80.2707,
        13.0405,
        80.2337,
        "test",
    )

    assert res_highway["route_type"] == "highway"
    assert res_highway["average_speed_kmh"] == 60
    assert res_highway["buffer_minutes"] == 2
    assert res_highway["duration_minutes"] > 5.0


# ============================================================
# Timeout fallback
# ============================================================

def test_fallback_response_fields_structure(setup_db):
    db = setup_db

    tech = Technician(
        tech_id="tech-fallback",
        technician_name="John Doe",
        technician_skill="HVAC",
        technician_location="13.08,80.27",
        tenant_id="tenant-1",
    )

    db.add(tech)

    job = Job(
        id=102,
        customer_name="Alice",
        location="13.04,80.23",
        site_latitude=13.0405,
        site_longitude=80.2337,
        site_address="123 Road",
        issue_description="AC issue",
        priority="HIGH",
        service_type="HVAC",
        contact_number="12345",
        tenant_id="tenant-1",
        preferred_service_date=datetime.now(
            timezone.utc
        ).date(),
    )

    db.add(job)

    ping = GPSPing(
        id="p-1",
        technician_id="tech-fallback",
        job_id="102",
        latitude=13.0827,
        longitude=80.2707,
        timestamp=datetime.now(timezone.utc),
        tenant_id="tenant-1",
    )

    db.add(ping)
    db.commit()

    with patch(
        "aiohttp.ClientSession.request",
        side_effect=asyncio.TimeoutError(
            "Connection timed out"
        ),
    ):
        response = client.get(
            "/api/v1/eta"
            "?technician_id=tech-fallback"
            "&job_id=102",
            headers={
                "X-Tenant-ID": "tenant-1",
                "Authorization": "Bearer mock-token-admin",
            },
        )

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "estimated"
    assert data["technician_id"] == "tech-fallback"
    assert data["job_id"] == "102"
    assert data["confidence"] == "low"
    assert data["fallback_reason"] == "maps_timeout"

    assert "disclaimer" in data
    assert "calculated_at" in data

    assert data["route_type"] == "highway"
    assert data["average_speed_kmh"] == 60
    assert data["buffer_minutes"] == 2


# ============================================================
# Quota fallback
# ============================================================

def test_fallback_reason_mapping_quota(setup_db):
    db = setup_db

    tech = Technician(
        tech_id="tech-quota",
        technician_name="John Doe",
        technician_skill="HVAC",
        technician_location="1,1",
        tenant_id="tenant-1",
    )

    db.add(tech)

    job = Job(
        id=103,
        customer_name="Alice",
        location="2,2",
        site_latitude=2.0,
        site_longitude=2.0,
        site_address="Addr",
        issue_description="AC issue",
        priority="HIGH",
        service_type="HVAC",
        contact_number="123",
        tenant_id="tenant-1",
        preferred_service_date=datetime.now(
            timezone.utc
        ).date(),
    )

    db.add(job)

    ping = GPSPing(
        id="p-2",
        technician_id="tech-quota",
        job_id="103",
        latitude=1.0,
        longitude=1.0,
        timestamp=datetime.now(timezone.utc),
        tenant_id="tenant-1",
    )

    db.add(ping)
    db.commit()

    # Test the ETA service's quota mapping directly.
    #
    # We intentionally raise the exception that the real
    # OLA client would raise for a quota condition.
    with patch(
        "app.services.ola_map_client.OlaMapsClient.get_route_duration",
        side_effect=MapsAPIException(
            "maps_quota",
            "Quota exceeded",
        ),
    ):
        response = client.get(
            "/api/v1/eta"
            "?technician_id=tech-quota"
            "&job_id=103",
            headers={
                "X-Tenant-ID": "tenant-1",
                "Authorization": "Bearer mock-token-admin",
            },
        )

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "estimated"
    assert data["fallback_reason"] == "maps_quota"


# ============================================================
# Invalid maps request
# ============================================================

def test_fallback_reason_mapping_invalid_request(setup_db):
    db = setup_db

    tech = Technician(
        tech_id="tech-invalid",
        technician_name="John Doe",
        technician_skill="HVAC",
        technician_location="1,1",
        tenant_id="tenant-1",
    )

    db.add(tech)

    job = Job(
        id=104,
        customer_name="Alice",
        location="2,2",
        site_latitude=2.0,
        site_longitude=2.0,
        site_address="Addr",
        issue_description="AC issue",
        priority="HIGH",
        service_type="HVAC",
        contact_number="123",
        tenant_id="tenant-1",
        preferred_service_date=datetime.now(
            timezone.utc
        ).date(),
    )

    db.add(job)

    ping = GPSPing(
        id="p-3",
        technician_id="tech-invalid",
        job_id="104",
        latitude=1.0,
        longitude=1.0,
        timestamp=datetime.now(timezone.utc),
        tenant_id="tenant-1",
    )

    db.add(ping)
    db.commit()

    # Test maps error classification directly.
    with patch(
        "app.services.ola_map_client.OlaMapsClient.get_route_duration",
        side_effect=MapsAPIException(
            "maps_error",
            "Invalid API key",
        ),
    ):
        response = client.get(
            "/api/v1/eta"
            "?technician_id=tech-invalid"
            "&job_id=104",
            headers={
                "X-Tenant-ID": "tenant-1",
                "Authorization": "Bearer mock-token-admin",
            },
        )

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "estimated"
    assert data["fallback_reason"] == "maps_error"


# ============================================================
# Cache behavior
# ============================================================

def test_fallback_cache_and_hit_behavior(setup_db):
    db = setup_db

    tech = Technician(
        tech_id="tech-cache",
        technician_name="John Doe",
        technician_skill="HVAC",
        technician_location="1,1",
        tenant_id="tenant-1",
    )

    db.add(tech)

    job = Job(
        id=105,
        customer_name="Alice",
        location="2,2",
        site_latitude=2.0,
        site_longitude=2.0,
        site_address="Addr",
        issue_description="AC issue",
        priority="HIGH",
        service_type="HVAC",
        contact_number="123",
        tenant_id="tenant-1",
        preferred_service_date=datetime.now(
            timezone.utc
        ).date(),
    )

    db.add(job)

    ping = GPSPing(
        id="p-4",
        technician_id="tech-cache",
        job_id="105",
        latitude=1.0,
        longitude=1.0,
        timestamp=datetime.now(timezone.utc),
        tenant_id="tenant-1",
    )

    db.add(ping)
    db.commit()

    mock_redis.flushall()

    # First request -> timeout -> fallback -> cache
    with patch(
        "aiohttp.ClientSession.request",
        side_effect=asyncio.TimeoutError("Timeout"),
    ):
        response = client.get(
            "/api/v1/eta"
            "?technician_id=tech-cache"
            "&job_id=105",
            headers={
                "X-Tenant-ID": "tenant-1",
                "Authorization": "Bearer mock-token-admin",
            },
        )

    assert response.status_code == 200

    first_resp = response.json()

    fallback_key = "eta:fallback:tech-cache:105"

    assert mock_redis.get(fallback_key) is not None
    assert mock_redis.ttl(fallback_key) == 60

    # Second request should use cached fallback.
    with patch(
        "aiohttp.ClientSession.request",
        side_effect=Exception(
            "Should not call API!"
        ),
    ):
        response2 = client.get(
            "/api/v1/eta"
            "?technician_id=tech-cache"
            "&job_id=105",
            headers={
                "X-Tenant-ID": "tenant-1",
                "Authorization": "Bearer mock-token-admin",
            },
        )

    assert response2.status_code == 200

    second_resp = response2.json()

    assert second_resp["status"] == "estimated"
    assert second_resp["eta"] == first_resp["eta"]


# ============================================================
# Fallback metrics
# ============================================================

def test_fallback_metrics_increments(setup_db):
    db = setup_db

    tech = Technician(
        tech_id="tech-metrics",
        technician_name="John Doe",
        technician_skill="HVAC",
        technician_location="1,1",
        tenant_id="tenant-1",
    )

    db.add(tech)

    job = Job(
        id=106,
        customer_name="Alice",
        location="2,2",
        site_latitude=2.0,
        site_longitude=2.0,
        site_address="Addr",
        issue_description="AC issue",
        priority="HIGH",
        service_type="HVAC",
        contact_number="123",
        tenant_id="tenant-1",
        preferred_service_date=datetime.now(
            timezone.utc
        ).date(),
    )

    db.add(job)

    ping = GPSPing(
        id="p-5",
        technician_id="tech-metrics",
        job_id="106",
        latitude=1.0,
        longitude=1.0,
        timestamp=datetime.now(timezone.utc),
        tenant_id="tenant-1",
    )

    db.add(ping)
    db.commit()

    mock_redis.flushall()

    # Timeout fallback.
    with patch(
        "aiohttp.ClientSession.request",
        side_effect=asyncio.TimeoutError("Timeout"),
    ):
        response = client.get(
            "/api/v1/eta"
            "?technician_id=tech-metrics"
            "&job_id=106",
            headers={
                "X-Tenant-ID": "tenant-1",
                "Authorization": "Bearer mock-token-admin",
            },
        )

    assert response.status_code == 200

    metrics_resp = client.get(
        "/api/v1/dispatch/metrics/fallback"
    )

    assert metrics_resp.status_code == 200

    metrics = metrics_resp.json()

    assert metrics["fallback_eta_total"]["timeout"] == 1
    assert metrics["fallback_eta_total"]["quota"] == 0
    assert metrics["fallback_eta_total"]["error"] == 0