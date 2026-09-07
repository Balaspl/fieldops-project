import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timezone

from app.main import app
from app.models import Job, Technician
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
    db.query(Job).delete()
    db.query(Technician).delete()
    db.commit()
    
    # Seed mock technician
    tech = Technician(
        technician_id=1,
        tech_id="tech-1",
        technician_name="Alice Smith",
        technician_skill="HVAC Repair",
        technician_location="North Zone",
        technician_status="Available",
        current_jobs=0,
        max_jobs=5,
        tenant_id="tenant-1"
    )
    db.add(tech)
    db.commit()

    # Seed mock jobs
    jobs = [
        Job(
            id=101,
            tenant_id="tenant-1",
            customer_name="John Doe",
            status="active",
            priority="CRITICAL",
            service_type="HVAC Repair",
            location="North Zone",
            issue_description="AC not cooling",
            contact_number="9876543210",
            preferred_service_date=datetime.now(timezone.utc),
            assigned_technician_id=None
        ),
        Job(
            id=102,
            tenant_id="tenant-1",
            customer_name="Jane Smith",
            status="in progress",
            priority="HIGH",
            service_type="Electrical Service",
            location="South Zone",
            issue_description="Fuse blown",
            contact_number="9876543211",
            preferred_service_date=datetime.now(timezone.utc),
            assigned_technician_id=1
        ),
        Job(
            id=103,
            tenant_id="tenant-1",
            customer_name="Bob Johnson",
            status="completed",
            priority="MEDIUM",
            service_type="Plumbing Service",
            location="East Zone",
            issue_description="Leak in pipe",
            contact_number="9876543212",
            preferred_service_date=datetime.now(timezone.utc),
            assigned_technician_id=None
        ),
        Job(
            id=104,
            tenant_id="tenant-1",
            customer_name="Dave Adams",
            status="cancelled",
            priority="LOW",
            service_type="Network Support",
            location="West Zone",
            issue_description="WiFi offline",
            contact_number="9876543213",
            preferred_service_date=datetime.now(timezone.utc),
            assigned_technician_id=None
        ),
    ]
    for j in jobs:
        db.add(j)
    db.commit()
    
    yield db
    db.close()

@pytest.fixture(autouse=True)
def apply_overrides():
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()

def test_get_jobs_no_filters():
    response = client.get("/jobs/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 4

def test_get_jobs_filter_search():
    # Search matches customer name
    response = client.get("/jobs/?search=Smith")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["customer_name"] == "Jane Smith"

    # Search matches location
    response = client.get("/jobs/?search=South")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["customer_name"] == "Jane Smith"

    # Search matches issue description
    response = client.get("/jobs/?search=AC")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["customer_name"] == "John Doe"

def test_get_jobs_filter_status():
    response = client.get("/jobs/?status=active")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["customer_name"] == "John Doe"

    # Test "inprogress" mapping
    response = client.get("/jobs/?status=in progress")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["customer_name"] == "Jane Smith"

    # Test cancelled/canceled mapping
    response = client.get("/jobs/?status=cancelled")
    assert response.status_code == 200
    data1 = response.json()
    assert len(data1) == 1
    
    response = client.get("/jobs/?status=canceled")
    assert response.status_code == 200
    data2 = response.json()
    assert len(data2) == 1
    assert data1[0]["id"] == data2[0]["id"]

def test_get_jobs_filter_priority():
    response = client.get("/jobs/?priority=CRITICAL")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["customer_name"] == "John Doe"

    response = client.get("/jobs/?priority=HIGH")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["customer_name"] == "Jane Smith"

def test_get_jobs_filter_service_type():
    response = client.get("/jobs/?service_type=HVAC Repair")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["customer_name"] == "John Doe"

    # Test underscore conversion
    response = client.get("/jobs/?service_type=Electrical_Service")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["customer_name"] == "Jane Smith"

def test_get_pending_jobs():
    response = client.get("/jobs/pending")
    assert response.status_code == 200
    data = response.json()
    # Only John Doe (101) is pending; Bob Johnson (103 - completed) and Dave Adams (104 - cancelled) are excluded
    assert len(data) == 1
    names = [j["customer_name"] for j in data]
    assert "John Doe" in names
    assert "Bob Johnson" not in names
    assert "Dave Adams" not in names

    # Filtered pending jobs
    response = client.get("/jobs/pending?search=John")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["customer_name"] == "John Doe"

def test_get_service_types():
    response = client.get("/jobs/service-types")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 4
    assert data == ["Electrical Service", "HVAC Repair", "Network Support", "Plumbing Service"]

def test_get_planned_assignments():
    response = client.get("/planned-assignments")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["job_id"] == 102
    assert data[0]["technician"] == "Alice Smith"

    # Search matches technician name
    response = client.get("/planned-assignments?search=Alice")
    assert response.status_code == 200
    assert len(response.json()) == 1

    # Search doesn't match
    response = client.get("/planned-assignments?search=NonExistent")
    assert response.status_code == 200
    assert len(response.json()) == 0
