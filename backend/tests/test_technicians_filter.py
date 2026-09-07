import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timezone

from app.main import app
from app.models import Technician
from app.database import Base, get_db
from app.auth.dependencies import (
    get_current_user_or_tenant,
    AuthenticatedUser,
)
from app.redis_client import get_redis_client

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
# Authentication override
# ============================================================

def override_get_current_user_or_tenant():
    user = AuthenticatedUser(
        user_id="test-admin",
        tenant_id="tenant-1",
        role="super_admin",
        jti="test-jti",
    )

    return user, "tenant-1"


# ============================================================
# Redis override
# ============================================================

class FakeRedis:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value):
        self.values[key] = value
        return True

    def setex(self, key, seconds, value):
        self.values[key] = value
        return True

    def incr(self, key):
        self.values[key] = int(self.values.get(key, 0)) + 1
        return self.values[key]

    def expire(self, key, seconds):
        return True

    def ping(self):
        return True

    def delete(self, key):
        return self.values.pop(key, None) is not None


fake_redis = FakeRedis()


# ============================================================
# Test client
# ============================================================

client = TestClient(app)


# ============================================================
# Database setup
# ============================================================

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()

    db.query(Technician).delete()
    db.commit()

    # --------------------------------------------------------
    # Seed tenant-1 technicians
    # --------------------------------------------------------

    techs = [
        Technician(
            technician_id=1,
            tech_id="tech-1",
            technician_name="Alice Smith",
            technician_skill="HVAC Repair",
            technician_location="North Zone",
            technician_status="Available",
            current_jobs=0,
            max_jobs=5,
            tenant_id="tenant-1",
        ),
        Technician(
            technician_id=2,
            tech_id="tech-2",
            technician_name="Bob Jones",
            technician_skill="Electrical",
            technician_location="South Zone",
            technician_status="Busy",
            current_jobs=1,
            max_jobs=5,
            tenant_id="tenant-1",
        ),
        Technician(
            technician_id=3,
            tech_id="tech-3",
            technician_name="Charlie Brown",
            technician_skill="Plumbing",
            technician_location="North Zone",
            technician_status="Offline",
            current_jobs=0,
            max_jobs=5,
            tenant_id="tenant-1",
        ),
        Technician(
            technician_id=4,
            tech_id="tech-4",
            technician_name="Dave Smith",
            technician_skill="Electrical",
            technician_location="East Zone",
            technician_status="Available",
            current_jobs=0,
            max_jobs=5,
            tenant_id="tenant-1",
        ),
    ]

    for technician in techs:
        db.add(technician)

    db.commit()

    yield db

    db.close()


# ============================================================
# Apply FastAPI dependency overrides
# ============================================================

@pytest.fixture(autouse=True)
def apply_overrides():
    app.dependency_overrides[get_db] = override_get_db

    app.dependency_overrides[
        get_current_user_or_tenant
    ] = override_get_current_user_or_tenant

    app.dependency_overrides[
        get_redis_client
    ] = lambda: fake_redis

    yield

    app.dependency_overrides.clear()


# ============================================================
# Tests
# ============================================================

def test_get_all_technicians_no_filters():
    response = client.get("/technicians/")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 4


def test_get_all_technicians_filter_search():

    # Search matches name
    response = client.get(
        "/technicians/?search=Smith"
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 2

    names = [
        technician["technician_name"]
        for technician in data
    ]

    assert "Alice Smith" in names
    assert "Dave Smith" in names

    # Search matches skill
    response = client.get(
        "/technicians/?search=Plumbing"
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1

    assert data[0]["technician_name"] == "Charlie Brown"

    # Search matches location
    response = client.get(
        "/technicians/?search=South"
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1

    assert data[0]["technician_name"] == "Bob Jones"


def test_get_all_technicians_filter_status():

    response = client.get(
        "/technicians/?status=Available"
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 2

    statuses = [
        technician["technician_status"]
        for technician in data
    ]

    assert all(
        technician_status == "Available"
        for technician_status in statuses
    )

    # Status case insensitivity
    response = client.get(
        "/technicians/?status=busy"
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1

    assert data[0]["technician_name"] == "Bob Jones"


def test_get_all_technicians_filter_zone():

    response = client.get(
        "/technicians/?zone=North Zone"
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 2

    locations = [
        technician["technician_location"]
        for technician in data
    ]

    assert all(
        location == "North Zone"
        for location in locations
    )

    # zone filter with ALL ignores it
    response = client.get(
        "/technicians/?zone=ALL"
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 4


def test_get_all_technicians_filter_skill():

    response = client.get(
        "/technicians/?skill=Electrical"
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 2

    skills = [
        technician["technician_skill"]
        for technician in data
    ]

    assert all(
        skill == "Electrical"
        for skill in skills
    )


def test_get_all_technicians_combined_filters():

    response = client.get(
        "/technicians/?search=Smith"
        "&status=Available"
        "&zone=East Zone"
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1

    assert data[0]["technician_name"] == "Dave Smith"


def test_get_all_zones():

    response = client.get(
        "/technicians/zones"
    )

    assert response.status_code == 200

    data = response.json()

    # Unique zones:
    # East Zone, North Zone, South Zone
    assert len(data) == 3

    assert data == [
        "East Zone",
        "North Zone",
        "South Zone",
    ]