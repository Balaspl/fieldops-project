import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timezone
import uuid
from fakeredis import FakeRedis

from app.main import app
from app.models import Job, Technician, GPSPing
from app.database import Base, get_db
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from app.redis_client import get_redis_client

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

fake_redis = FakeRedis(decode_responses=True)

def override_get_redis():
    return fake_redis

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    
    # Cleanup
    db.query(GPSPing).delete()
    db.query(Job).delete()
    db.query(Technician).delete()
    db.commit()
    
    # Reset fake redis
    fake_redis.flushall()
    
    yield db
    db.close()

@pytest.fixture(autouse=True)
def apply_overrides():
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis_client] = override_get_redis
    yield
    app.dependency_overrides.clear()

def test_gps_ping_success_android(setup_db):
    db = setup_db
    # Seed technician
    tech = Technician(
        tech_id="tech-android-123",
        technician_name="Android Tech",
        technician_skill="HVAC",
        technician_location="0,0",
        technician_status="Available",
        tenant_id="tenant-1"
    )
    db.add(tech)
    
    # Seed job (active status)
    job = Job(
        customer_name="Alice",
        location="1,1",
        issue_description="Leak",
        priority="HIGH",
        service_type="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now().date(),
        status="active",
        tenant_id="tenant-1"
    )
    db.add(job)
    db.commit()
    db.refresh(tech)
    db.refresh(job)

    payload = {
        "technician_id": "tech-android-123",
        "job_id": str(job.id),
        "latitude": 13.0827,
        "longitude": 80.2707,
        "timestamp": "2026-06-25T12:00:00Z",
        "accuracy": 4.5,
        "altitude": 15.0
    }

    response = client.post(
        "/api/v1/gps/ping",
        headers={
            "X-Tenant-ID": "tenant-1",
            "Authorization": "Bearer mock-token",
            "User-Agent": "Android Mobile Device"
        },
        json=payload
    )

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "stored"
    assert "ping_id" in data
    assert uuid.UUID(data["ping_id"]) # Validate ping_id is a valid UUID
    assert data["technician_id"] == "tech-android-123"
    assert data["job_id"] == str(job.id)

    # Check database storage
    db_ping = db.query(GPSPing).filter(GPSPing.id == data["ping_id"]).first()
    assert db_ping is not None
    assert db_ping.user_agent == "Android Mobile Device"
    assert db_ping.tenant_id == "tenant-1"
    assert db_ping.latitude == 13.0827

def test_gps_ping_success_ios(setup_db):
    db = setup_db
    # Seed technician
    tech = Technician(
        tech_id="tech-ios-456",
        technician_name="iOS Tech",
        technician_skill="Electrical",
        technician_location="0,0",
        technician_status="Available",
        tenant_id="tenant-1"
    )
    db.add(tech)
    
    # Seed job (active status)
    job = Job(
        customer_name="Bob",
        location="2,2",
        issue_description="Fuse",
        priority="HIGH",
        service_type="Electrical",
        contact_number="1234567890",
        preferred_service_date=datetime.now().date(),
        status="active",
        tenant_id="tenant-1"
    )
    db.add(job)
    db.commit()

    payload = {
        "technician_id": "tech-ios-456",
        "job_id": str(job.id),
        "latitude": -12.3456,
        "longitude": 120.4567,
        "timestamp": "2026-06-25T12:05:00Z",
        "accuracy": 3.0,
        "altitude": 10.0
    }

    response = client.post(
        "/api/v1/gps/ping",
        headers={
            "X-Tenant-ID": "tenant-1",
            "Authorization": "Bearer mock-token",
            "User-Agent": "Apple iOS Device"
        },
        json=payload
    )

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "stored"

    # Check database storage
    db_ping = db.query(GPSPing).filter(GPSPing.id == data["ping_id"]).first()
    assert db_ping is not None
    assert db_ping.user_agent == "Apple iOS Device"
    assert db_ping.tenant_id == "tenant-1"

def test_gps_ping_boundary_values(setup_db):
    db = setup_db
    tech = Technician(
        tech_id="tech-boundary", technician_name="Bound Tech", technician_skill="HVAC",
        technician_location="0,0", technician_status="Available", tenant_id="tenant-1"
    )
    db.add(tech)
    job = Job(
        customer_name="Alice", location="1,1", issue_description="Leak", priority="HIGH",
        service_type="Plumbing", contact_number="1234567890", preferred_service_date=datetime.now().date(),
        status="active", tenant_id="tenant-1"
    )
    db.add(job)
    db.commit()

    # Boundary cases: lat -90/90, lng -180/180
    boundaries = [
        (-90.0, -180.0),
        (90.0, 180.0),
        (-90.0, 180.0),
        (90.0, -180.0)
    ]

    for lat, lng in boundaries:
        fake_redis.flushall()
        payload = {
            "technician_id": "tech-boundary",
            "job_id": str(job.id),
            "latitude": lat,
            "longitude": lng,
            "timestamp": "2026-06-25T12:00:00Z"
        }
        response = client.post(
            "/api/v1/gps/ping",
            headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token"},
            json=payload
        )
        assert response.status_code == 201

    # Out of bounds cases
    out_of_bounds = [
        (-90.1, 0.0),
        (90.1, 0.0),
        (0.0, -180.1),
        (0.0, 180.1)
    ]

    for lat, lng in out_of_bounds:
        payload = {
            "technician_id": "tech-boundary",
            "job_id": str(job.id),
            "latitude": lat,
            "longitude": lng,
            "timestamp": "2026-06-25T12:00:00Z"
        }
        response = client.post(
            "/api/v1/gps/ping",
            headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token"},
            json=payload
        )
        assert response.status_code == 422

def test_gps_ping_malformed_json(setup_db):
    response = client.post(
        "/api/v1/gps/ping",
        headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token"},
        content="{'malformed': json"
    )
    assert response.status_code == 400
    assert "Malformed JSON" in response.json()["error"]

def test_gps_ping_missing_technician(setup_db):
    db = setup_db
    job = Job(
        customer_name="Alice", location="1,1", issue_description="Leak", priority="HIGH",
        service_type="Plumbing", contact_number="1234567890", preferred_service_date=datetime.now().date(),
        status="active", tenant_id="tenant-1"
    )
    db.add(job)
    db.commit()

    payload = {
        "technician_id": "tech-non-existent",
        "job_id": str(job.id),
        "latitude": 10.0,
        "longitude": 20.0,
        "timestamp": "2026-06-25T12:00:00Z"
    }

    response = client.post(
        "/api/v1/gps/ping",
        headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token"},
        json=payload
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Technician not found"

def test_gps_ping_missing_job(setup_db):
    db = setup_db
    tech = Technician(
        tech_id="tech-123", technician_name="Bound Tech", technician_skill="HVAC",
        technician_location="0,0", technician_status="Available", tenant_id="tenant-1"
    )
    db.add(tech)
    db.commit()

    payload = {
        "technician_id": "tech-123",
        "job_id": "99999", # Non-existent job
        "latitude": 10.0,
        "longitude": 20.0,
        "timestamp": "2026-06-25T12:00:00Z"
    }

    response = client.post(
        "/api/v1/gps/ping",
        headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token"},
        json=payload
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found"

def test_gps_ping_job_not_active(setup_db):
    db = setup_db
    tech = Technician(
        tech_id="tech-123", technician_name="Bound Tech", technician_skill="HVAC",
        technician_location="0,0", technician_status="Available", tenant_id="tenant-1"
    )
    db.add(tech)
    
    # Completed job (not active)
    job = Job(
        customer_name="Alice", location="1,1", issue_description="Leak", priority="HIGH",
        service_type="Plumbing", contact_number="1234567890", preferred_service_date=datetime.now().date(),
        status="completed", tenant_id="tenant-1"
    )
    db.add(job)
    db.commit()

    payload = {
        "technician_id": "tech-123",
        "job_id": str(job.id),
        "latitude": 10.0,
        "longitude": 20.0,
        "timestamp": "2026-06-25T12:00:00Z"
    }

    response = client.post(
        "/api/v1/gps/ping",
        headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token"},
        json=payload
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "Job status is not active"

def test_gps_ping_rate_limit(setup_db):
    db = setup_db
    tech = Technician(
        tech_id="tech-rate", technician_name="Bound Tech", technician_skill="HVAC",
        technician_location="0,0", technician_status="Available", tenant_id="tenant-1"
    )
    db.add(tech)
    job = Job(
        customer_name="Alice", location="1,1", issue_description="Leak", priority="HIGH",
        service_type="Plumbing", contact_number="1234567890", preferred_service_date=datetime.now().date(),
        status="active", tenant_id="tenant-1"
    )
    db.add(job)
    db.commit()

    payload = {
        "technician_id": "tech-rate",
        "job_id": str(job.id),
        "latitude": 10.0,
        "longitude": 20.0,
        "timestamp": "2026-06-25T12:00:00Z"
    }

    # First request - should succeed
    response1 = client.post(
        "/api/v1/gps/ping",
        headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token"},
        json=payload
    )
    assert response1.status_code == 201

    # Second request within 30s - should fail
    response2 = client.post(
        "/api/v1/gps/ping",
        headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token"},
        json=payload
    )
    assert response2.status_code == 429
    assert response2.json()["detail"] == "Too Many Requests"

def test_gps_ping_audit_trail_logging_and_correlation_id(setup_db):
    db = setup_db
    tech = Technician(
        tech_id="tech-audit", technician_name="Bound Tech", technician_skill="HVAC",
        technician_location="0,0", technician_status="Available", tenant_id="tenant-1"
    )
    db.add(tech)
    job = Job(
        customer_name="Alice", location="1,1", issue_description="Leak", priority="HIGH",
        service_type="Plumbing", contact_number="1234567890", preferred_service_date=datetime.now().date(),
        status="active", tenant_id="tenant-1"
    )
    db.add(job)
    db.commit()

    payload = {
        "technician_id": "tech-audit",
        "job_id": str(job.id),
        "latitude": 10.0,
        "longitude": 20.0,
        "timestamp": "2026-06-25T12:00:00Z"
    }

    response = client.post(
        "/api/v1/gps/ping",
        headers={
            "X-Tenant-ID": "tenant-1",
            "Authorization": "Bearer mock-token",
            "X-Correlation-ID": "correlation-uuid-999"
        },
        json=payload
    )
    assert response.status_code == 201
    ping_id = response.json()["ping_id"]

    db_ping = db.query(GPSPing).filter(GPSPing.id == ping_id).first()
    assert db_ping is not None
    assert db_ping.correlation_id == "correlation-uuid-999"


def test_gps_strict_validations(setup_db):
    db = setup_db
    tech = Technician(
        tech_id="tech-val", technician_name="Val Tech", technician_skill="HVAC",
        technician_location="0,0", technician_status="Available", tenant_id="tenant-1"
    )
    db.add(tech)
    job = Job(
        customer_name="Alice", location="1,1", issue_description="Leak", priority="HIGH",
        service_type="Plumbing", contact_number="1234567890", preferred_service_date=datetime.now().date(),
        status="active", tenant_id="tenant-1"
    )
    db.add(job)
    db.commit()

    base_payload = {
        "technician_id": "tech-val",
        "job_id": str(job.id),
        "timestamp": "2026-06-25T12:00:00Z"
    }

    # 1. Test valid coordinate cases
    valid_coords = [
        (-90.0, 0.0),       # latitude = -90 (valid, boundary)
        (-89.9, 0.0),     # latitude = -89.9 (valid)
        (0.0, 0.0),         # latitude = 0 (valid)
        (89.9, 0.0),      # latitude = 89.9 (valid)
        (90.0, 0.0),        # latitude = 90 (valid, boundary)
        (0.0, -180.0),      # longitude = -180 (valid, boundary)
        (0.0, -179.9),    # longitude = -179.9 (valid)
        (0.0, 0.0),         # longitude = 0 (valid)
        (0.0, 179.9),     # longitude = 179.9 (valid)
        (0.0, 180.0)        # longitude = 180 (valid, boundary)
    ]

    for lat, lng in valid_coords:
        fake_redis.flushall()
        payload = base_payload.copy()
        payload["latitude"] = lat
        payload["longitude"] = lng
        
        response = client.post(
            "/api/v1/gps/ping",
            headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token"},
            json=payload
        )
        assert response.status_code == 201

    # 2. Test invalid coordinate range cases (reject with 422)
    invalid_coords = [
        (-90.1, 0.0, "latitude", "Latitude must be between -90 and 90"),
        (90.1, 0.0, "latitude", "Latitude must be between -90 and 90"),
        (0.0, -180.1, "longitude", "Longitude must be between -180 and 180"),
        (0.0, 180.1, "longitude", "Longitude must be between -180 and 180")
    ]

    for lat, lng, field, error_msg in invalid_coords:
        payload = base_payload.copy()
        payload["latitude"] = lat
        payload["longitude"] = lng
        
        response = client.post(
            "/api/v1/gps/ping",
            headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token"},
            json=payload
        )
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert len(detail) == 1
        assert detail[0]["loc"] == ["body", field]
        assert detail[0]["msg"] == error_msg

    # 3. Test missing or null values (reject with 422)
    # Null latitude
    payload = base_payload.copy()
    payload["latitude"] = None
    payload["longitude"] = 0.0
    response = client.post(
        "/api/v1/gps/ping",
        headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token"},
        json=payload
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "latitude"]
    assert response.json()["detail"][0]["msg"] == "Coordinates are required"

    # Null longitude
    payload = base_payload.copy()
    payload["latitude"] = 0.0
    payload["longitude"] = None
    response = client.post(
        "/api/v1/gps/ping",
        headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token"},
        json=payload
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "longitude"]
    assert response.json()["detail"][0]["msg"] == "Coordinates are required"

    # Missing coordinates fields entirely
    payload = base_payload.copy()
    response = client.post(
        "/api/v1/gps/ping",
        headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token"},
        json=payload
    )
    assert response.status_code == 422
    details = response.json()["detail"]
    assert len(details) == 2
    locs = [d["loc"] for d in details]
    msgs = [d["msg"] for d in details]
    assert ["body", "latitude"] in locs
    assert ["body", "longitude"] in locs
    assert all(m == "Coordinates are required" for m in msgs)

    # 4. Test non-numeric values (reject with 422)
    # String "abc" as latitude
    payload = base_payload.copy()
    payload["latitude"] = "abc"
    payload["longitude"] = 0.0
    response = client.post(
        "/api/v1/gps/ping",
        headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token"},
        json=payload
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "latitude"]
    assert response.json()["detail"][0]["msg"] == "Coordinates must be numeric"

    # String "abc" as longitude
    payload = base_payload.copy()
    payload["latitude"] = 0.0
    payload["longitude"] = "abc"
    response = client.post(
        "/api/v1/gps/ping",
        headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token"},
        json=payload
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "longitude"]
    assert response.json()["detail"][0]["msg"] == "Coordinates must be numeric"

    # Empty string as coordinate
    payload = base_payload.copy()
    payload["latitude"] = ""
    payload["longitude"] = 0.0
    response = client.post(
        "/api/v1/gps/ping",
        headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token"},
        json=payload
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "latitude"]
    assert response.json()["detail"][0]["msg"] == "Coordinates must be numeric"

    # Boolean true as latitude
    payload = base_payload.copy()
    payload["latitude"] = True
    payload["longitude"] = 0.0
    response = client.post(
        "/api/v1/gps/ping",
        headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token"},
        json=payload
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "latitude"]
    assert response.json()["detail"][0]["msg"] == "Coordinates must be numeric"

    # Array [1,2] as longitude
    payload = base_payload.copy()
    payload["latitude"] = 0.0
    payload["longitude"] = [1, 2]
    response = client.post(
        "/api/v1/gps/ping",
        headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token"},
        json=payload
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "longitude"]
    assert response.json()["detail"][0]["msg"] == "Coordinates must be numeric"

    payload["latitude"] = {"lat": 1}
    payload["longitude"] = 0.0
    response = client.post(
        "/api/v1/gps/ping",
        headers={"X-Tenant-ID": "tenant-1", "Authorization": "Bearer mock-token"},
        json=payload
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "latitude"]
    assert response.json()["detail"][0]["msg"] == "Coordinates must be numeric"


def test_gps_batch_success_100(setup_db):
    db = setup_db
    # Seed technician
    tech = Technician(
        tech_id="tech-batch-100",
        technician_name="Batch Tech",
        technician_skill="HVAC",
        technician_location="0,0",
        technician_status="Available",
        tenant_id="tenant-1"
    )
    db.add(tech)
    # Seed job
    job = Job(
        customer_name="Customer 100",
        location="1,1",
        issue_description="Problem",
        priority="HIGH",
        service_type="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now().date(),
        status="active",
        tenant_id="tenant-1"
    )
    db.add(job)
    db.commit()
    db.refresh(tech)
    db.refresh(job)

    pings = []
    for i in range(100):
        # Unique timestamp for each
        ts = datetime(2026, 6, 25, 12, i // 60, i % 60, tzinfo=timezone.utc).isoformat()
        pings.append({
            "technician_id": "tech-batch-100",
            "job_id": str(job.id),
            "latitude": 13.0827,
            "longitude": 80.2707,
            "timestamp": ts,
            "accuracy": 4.5,
            "altitude": 15.0
        })

    response = client.post(
        "/api/v1/gps/batch",
        headers={
            "X-Tenant-ID": "tenant-1",
            "Authorization": "Bearer mock-token"
        },
        json={"pings": pings}
    )

    assert response.status_code == 207
    data = response.json()
    assert data["total"] == 100
    assert data["succeeded"] == 100
    assert data["failed"] == 0
    assert len(data["errors"]) == 0

    # Verify all 100 pings are in the DB
    count = db.query(GPSPing).filter(GPSPing.technician_id == "tech-batch-100").count()
    assert count == 100


def test_gps_batch_success_1(setup_db):
    db = setup_db
    # Seed technician
    tech = Technician(
        tech_id="tech-batch-1",
        technician_name="Batch Tech",
        technician_skill="HVAC",
        technician_location="0,0",
        technician_status="Available",
        tenant_id="tenant-1"
    )
    db.add(tech)
    # Seed job
    job = Job(
        customer_name="Customer 1",
        location="1,1",
        issue_description="Problem",
        priority="HIGH",
        service_type="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now().date(),
        status="active",
        tenant_id="tenant-1"
    )
    db.add(job)
    db.commit()

    pings = [{
        "technician_id": "tech-batch-1",
        "job_id": str(job.id),
        "latitude": 13.0827,
        "longitude": 80.2707,
        "timestamp": "2026-06-25T12:00:00Z"
    }]

    response = client.post(
        "/api/v1/gps/batch",
        headers={
            "X-Tenant-ID": "tenant-1",
            "Authorization": "Bearer mock-token"
        },
        json={"pings": pings}
    )

    assert response.status_code == 207
    data = response.json()
    assert data["total"] == 1
    assert data["succeeded"] == 1
    assert data["failed"] == 0
    assert len(data["errors"]) == 0

    assert db.query(GPSPing).filter(GPSPing.technician_id == "tech-batch-1").count() == 1


def test_gps_batch_too_large(setup_db):
    pings = []
    for i in range(101):
        pings.append({
            "technician_id": "tech-batch",
            "job_id": "1",
            "latitude": 13.0827,
            "longitude": 80.2707,
            "timestamp": "2026-06-25T12:00:00Z"
        })

    response = client.post(
        "/api/v1/gps/batch",
        headers={
            "X-Tenant-ID": "tenant-1",
            "Authorization": "Bearer mock-token"
        },
        json={"pings": pings}
    )
    assert response.status_code == 413
    assert "Maximum 100 pings per batch" in response.json()["detail"]


def test_gps_batch_empty(setup_db):
    response = client.post(
        "/api/v1/gps/batch",
        headers={
            "X-Tenant-ID": "tenant-1",
            "Authorization": "Bearer mock-token"
        },
        json={"pings": []}
    )
    assert response.status_code == 400
    assert "Pings array cannot be empty" in response.json()["detail"]


def test_gps_batch_duplicate_timestamps(setup_db):
    db = setup_db
    # Seed technician
    tech = Technician(
        tech_id="tech-batch-dup",
        technician_name="Batch Tech",
        technician_skill="HVAC",
        technician_location="0,0",
        technician_status="Available",
        tenant_id="tenant-1"
    )
    db.add(tech)
    # Seed job
    job = Job(
        customer_name="Customer",
        location="1,1",
        issue_description="Problem",
        priority="HIGH",
        service_type="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now().date(),
        status="active",
        tenant_id="tenant-1"
    )
    db.add(job)
    db.commit()

    pings = [
        {
            "technician_id": "tech-batch-dup",
            "job_id": str(job.id),
            "latitude": 13.0827,
            "longitude": 80.2707,
            "timestamp": "2026-06-25T12:00:00Z"
        },
        {
            "technician_id": "tech-batch-dup",
            "job_id": str(job.id),
            "latitude": 13.0830,
            "longitude": 80.2710,
            "timestamp": "2026-06-25T12:00:00Z" # Duplicate
        }
    ]

    response = client.post(
        "/api/v1/gps/batch",
        headers={
            "X-Tenant-ID": "tenant-1",
            "Authorization": "Bearer mock-token"
        },
        json={"pings": pings}
    )

    assert response.status_code == 207
    data = response.json()
    assert data["total"] == 2
    assert data["succeeded"] == 1
    assert data["failed"] == 1
    assert len(data["errors"]) == 1
    assert data["errors"][0]["index"] == 1
    assert "Duplicate timestamp" in data["errors"][0]["reason"]

    # Verify no database write (all-or-nothing rollback)
    assert db.query(GPSPing).filter(GPSPing.technician_id == "tech-batch-dup").count() == 0


def test_gps_batch_mixed_validation_failure(setup_db):
    db = setup_db
    # Seed technician
    tech = Technician(
        tech_id="tech-batch-mixed",
        technician_name="Batch Tech",
        technician_skill="HVAC",
        technician_location="0,0",
        technician_status="Available",
        tenant_id="tenant-1"
    )
    db.add(tech)
    # Seed job
    job = Job(
        customer_name="Customer",
        location="1,1",
        issue_description="Problem",
        priority="HIGH",
        service_type="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now().date(),
        status="active",
        tenant_id="tenant-1"
    )
    db.add(job)
    db.commit()

    pings = [
        {
            "technician_id": "tech-batch-mixed",
            "job_id": str(job.id),
            "latitude": 13.0827,
            "longitude": 80.2707,
            "timestamp": "2026-06-25T12:00:00Z"
        },
        {
            "technician_id": "tech-batch-mixed",
            "job_id": str(job.id),
            "latitude": 95.0, # Invalid latitude
            "longitude": 80.2710,
            "timestamp": "2026-06-25T12:01:00Z"
        }
    ]

    response = client.post(
        "/api/v1/gps/batch",
        headers={
            "X-Tenant-ID": "tenant-1",
            "Authorization": "Bearer mock-token"
        },
        json={"pings": pings}
    )

    assert response.status_code == 207
    data = response.json()
    assert data["total"] == 2
    assert data["succeeded"] == 1
    assert data["failed"] == 1
    assert len(data["errors"]) == 1
    assert data["errors"][0]["index"] == 1
    assert "Latitude must be between -90 and 90" in data["errors"][0]["reason"]

    # Verify no database write (all-or-nothing rollback)
    assert db.query(GPSPing).filter(GPSPing.technician_id == "tech-batch-mixed").count() == 0


def test_gps_batch_non_existent_technician(setup_db):
    db = setup_db
    job = Job(
        customer_name="Customer",
        location="1,1",
        issue_description="Problem",
        priority="HIGH",
        service_type="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now().date(),
        status="active",
        tenant_id="tenant-1"
    )
    db.add(job)
    db.commit()

    pings = [
        {
            "technician_id": "non-existent-tech",
            "job_id": str(job.id),
            "latitude": 13.0827,
            "longitude": 80.2707,
            "timestamp": "2026-06-25T12:00:00Z"
        }
    ]

    response = client.post(
        "/api/v1/gps/batch",
        headers={
            "X-Tenant-ID": "tenant-1",
            "Authorization": "Bearer mock-token"
        },
        json={"pings": pings}
    )

    assert response.status_code == 207
    data = response.json()
    assert data["total"] == 1
    assert data["succeeded"] == 0
    assert data["failed"] == 1
    assert len(data["errors"]) == 1
    assert data["errors"][0]["index"] == 0
    assert data["errors"][0]["reason"] == "Technician not found"

    # Verify no database write
    assert db.query(GPSPing).count() == 0


def test_gps_batch_non_existent_job(setup_db):
    db = setup_db
    # Seed technician
    tech = Technician(
        tech_id="tech-batch-no-job",
        technician_name="Batch Tech",
        technician_skill="HVAC",
        technician_location="0,0",
        technician_status="Available",
        tenant_id="tenant-1"
    )
    db.add(tech)
    db.commit()

    pings = [
        {
            "technician_id": "tech-batch-no-job",
            "job_id": "999999", # Non-existent job
            "latitude": 13.0827,
            "longitude": 80.2707,
            "timestamp": "2026-06-25T12:00:00Z"
        }
    ]

    response = client.post(
        "/api/v1/gps/batch",
        headers={
            "X-Tenant-ID": "tenant-1",
            "Authorization": "Bearer mock-token"
        },
        json={"pings": pings}
    )

    assert response.status_code == 207
    data = response.json()
    assert data["total"] == 1
    assert data["succeeded"] == 0
    assert data["failed"] == 1
    assert len(data["errors"]) == 1
    assert data["errors"][0]["index"] == 0
    assert data["errors"][0]["reason"] == "Job not found"

    assert db.query(GPSPing).count() == 0


def test_gps_batch_rate_limiting(setup_db):
    db = setup_db
    # Seed technician
    tech = Technician(
        tech_id="tech-batch-rate",
        technician_name="Batch Tech",
        technician_skill="HVAC",
        technician_location="0,0",
        technician_status="Available",
        tenant_id="tenant-1"
    )
    db.add(tech)
    # Seed job
    job = Job(
        customer_name="Customer",
        location="1,1",
        issue_description="Problem",
        priority="HIGH",
        service_type="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now().date(),
        status="active",
        tenant_id="tenant-1"
    )
    db.add(job)
    db.commit()

    pings = [
        {
            "technician_id": "tech-batch-rate",
            "job_id": str(job.id),
            "latitude": 13.0827,
            "longitude": 80.2707,
            "timestamp": "2026-06-25T12:00:00Z"
        }
    ]

    # First request: should succeed
    response1 = client.post(
        "/api/v1/gps/batch",
        headers={
            "X-Tenant-ID": "tenant-1",
            "Authorization": "Bearer mock-token"
        },
        json={"pings": pings}
    )
    assert response1.status_code == 207

    # Second request within 5s: should fail with 429
    response2 = client.post(
        "/api/v1/gps/batch",
        headers={
            "X-Tenant-ID": "tenant-1",
            "Authorization": "Bearer mock-token"
        },
        json={"pings": pings}
    )
    assert response2.status_code == 429
    assert response2.json()["detail"] == "Too Many Requests"


def test_gps_batch_performance_under_500ms(setup_db):
    import time
    db = setup_db
    # Seed technician
    tech = Technician(
        tech_id="tech-batch-perf",
        technician_name="Batch Tech",
        technician_skill="HVAC",
        technician_location="0,0",
        technician_status="Available",
        tenant_id="tenant-1"
    )
    db.add(tech)
    # Seed job
    job = Job(
        customer_name="Customer",
        location="1,1",
        issue_description="Problem",
        priority="HIGH",
        service_type="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now().date(),
        status="active",
        tenant_id="tenant-1"
    )
    db.add(job)
    db.commit()

    pings = []
    for i in range(100):
        ts = datetime(2026, 6, 25, 12, i // 60, i % 60, tzinfo=timezone.utc).isoformat()
        pings.append({
            "technician_id": "tech-batch-perf",
            "job_id": str(job.id),
            "latitude": 13.0827,
            "longitude": 80.2707,
            "timestamp": ts,
            "accuracy": 4.5,
            "altitude": 15.0
        })

    start_time = time.perf_counter()
    response = client.post(
        "/api/v1/gps/batch",
        headers={
            "X-Tenant-ID": "tenant-1",
            "Authorization": "Bearer mock-token"
        },
        json={"pings": pings}
    )
    end_time = time.perf_counter()
    duration_ms = (end_time - start_time) * 1000

    assert response.status_code == 207
    assert duration_ms < 500.0


def test_gps_batch_transaction_rollback_mid_batch_failure(setup_db):
    db = setup_db
    # Seed technician
    tech = Technician(
        tech_id="tech-batch-rollback",
        technician_name="Batch Tech",
        technician_skill="HVAC",
        technician_location="0,0",
        technician_status="Available",
        tenant_id="tenant-1"
    )
    db.add(tech)
    # Seed job
    job = Job(
        customer_name="Customer",
        location="1,1",
        issue_description="Problem",
        priority="HIGH",
        service_type="Plumbing",
        contact_number="1234567890",
        preferred_service_date=datetime.now().date(),
        status="active",
        tenant_id="tenant-1"
    )
    db.add(job)
    db.commit()

    pings = [
        {
            "technician_id": "tech-batch-rollback",
            "job_id": str(job.id),
            "latitude": 13.0827,
            "longitude": 80.2707,
            "timestamp": "2026-06-25T12:00:00Z"
        },
        {
            "technician_id": "tech-batch-rollback",
            "job_id": "999999",  # Invalid/non-existent job_id
            "latitude": 13.0830,
            "longitude": 80.2710,
            "timestamp": "2026-06-25T12:01:00Z"
        }
    ]

    response = client.post(
        "/api/v1/gps/batch",
        headers={
            "X-Tenant-ID": "tenant-1",
            "Authorization": "Bearer mock-token"
        },
        json={"pings": pings}
    )

    assert response.status_code == 207
    data = response.json()
    assert data["failed"] == 1
    assert data["succeeded"] == 1

    # Verify no database write (both rolled back)
    assert db.query(GPSPing).filter(GPSPing.technician_id == "tech-batch-rollback").count() == 0


