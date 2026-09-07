import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timezone

from app.main import app
from app.models import Technician
from app.database import Base, get_db
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

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

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    db.query(Technician).delete()
    db.commit()
    
    # Seed mock technicians
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
    for t in techs:
        db.add(t)
    db.commit()
    
    yield db
    db.close()

@pytest.fixture(autouse=True)
def apply_overrides():
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()

def test_get_all_technicians_no_filters():
    response = client.get("/technicians/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 4

def test_get_all_technicians_filter_search():
    # Search matches name
    response = client.get("/technicians/?search=Smith")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    names = [t["technician_name"] for t in data]
    assert "Alice Smith" in names
    assert "Dave Smith" in names

    # Search matches skill
    response = client.get("/technicians/?search=Plumbing")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["technician_name"] == "Charlie Brown"

    # Search matches location
    response = client.get("/technicians/?search=South")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["technician_name"] == "Bob Jones"

def test_get_all_technicians_filter_status():
    response = client.get("/technicians/?status=Available")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    statuses = [t["technician_status"] for t in data]
    assert all(s == "Available" for s in statuses)

    # status case insensitivity
    response = client.get("/technicians/?status=busy")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["technician_name"] == "Bob Jones"

def test_get_all_technicians_filter_zone():
    response = client.get("/technicians/?zone=North Zone")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    locations = [t["technician_location"] for t in data]
    assert all(l == "North Zone" for l in locations)

    # zone filter with "ALL" ignores it
    response = client.get("/technicians/?zone=ALL")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 4

def test_get_all_technicians_filter_skill():
    response = client.get("/technicians/?skill=Electrical")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    skills = [t["technician_skill"] for t in data]
    assert all(s == "Electrical" for s in skills)

def test_get_all_technicians_combined_filters():
    response = client.get("/technicians/?search=Smith&status=Available&zone=East Zone")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["technician_name"] == "Dave Smith"

def test_get_all_zones():
    response = client.get("/technicians/zones")
    assert response.status_code == 200
    data = response.json()
    # Unique zones: North Zone, South Zone, East Zone
    assert len(data) == 3
    assert data == ["East Zone", "North Zone", "South Zone"]
