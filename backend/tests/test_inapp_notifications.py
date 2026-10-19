import pytest
import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from fastapi import Depends
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
import factory
import os
import sys

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.main import app
from app.database import Base, get_db
from app import models
from app.services import socket_manager
from app.auth.dependencies import get_current_user
from app.auth.rbac import UserRole
from app.auth.dependencies import AuthenticatedUser


# 1. Test database setup
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
test_db_session = TestingSessionLocal()

# 2. Factories
class TechnicianFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = models.Technician
        sqlalchemy_session = test_db_session
        sqlalchemy_session_persistence = "commit"

    tech_id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    tenant_id = "tenant-123"
    technician_name = factory.Faker('name')
    technician_skill = "HVAC"
    technician_location = "13.0,80.0"

class JobFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = models.Job
        sqlalchemy_session = test_db_session
        sqlalchemy_session_persistence = "commit"

    customer_name = factory.Faker('name')
    location = "13.0,80.0"
    issue_description = "Issue"
    priority = "HIGH"
    service_type = "HVAC"
    contact_number = "+1234567890"
    preferred_service_date = factory.LazyFunction(lambda: datetime.now(timezone.utc).date())

class InAppNotificationFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = models.InAppNotification
        sqlalchemy_session = test_db_session
        sqlalchemy_session_persistence = "commit"

    id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    tech_id = ""
    tenant_id = "tenant-123"
    job_id = ""
    type = "job_assignment"
    title = "New Job"
    body = "New Job Assignment"
    status = "UNREAD"
    action_type = "deep_link"
    priority = "NORMAL"
    created_at = factory.LazyFunction(lambda: datetime.now(timezone.utc))
    expires_at = None

# 3. Fixtures
@pytest.fixture(scope="function")
def db_session():
    Base.metadata.create_all(bind=engine)
    try:
        yield test_db_session
    finally:
        test_db_session.rollback()
        Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    test_user = AuthenticatedUser(
        user_id="test-user",
        tenant_id="tenant-123",
        role=UserRole.SUPER_ADMIN,
        jti="test-jti",
    )

    def override_get_current_user():
        return test_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    yield TestClient(app)

    app.dependency_overrides.clear()


def authenticate_as_technician(tech):
    user = AuthenticatedUser(
        user_id=str(tech.tech_id),
        tenant_id=str(tech.tenant_id),
        role=UserRole.TECHNICIAN,
        jti="technician-test-jti",
    )
    app.dependency_overrides[get_current_user] = lambda: user

@pytest.fixture
def auth_headers():
    def _headers(tenant_id="tenant-123", token="sample_token"):
        return {
            "X-Tenant-ID": tenant_id,
            "Authorization": f"Bearer {token}"
        }
    return _headers

# 4. Tests

def test_create_notification(db_session):
    tech = TechnicianFactory()
    job = JobFactory()
    
    notification = InAppNotificationFactory(tech_id=tech.tech_id, job_id=str(job.id))
    
    db_session.refresh(notification)
    assert notification.status == "UNREAD"
    assert notification.created_at is not None

def test_mark_as_read(client, db_session, auth_headers):
    tech = TechnicianFactory()
    authenticate_as_technician(tech)
    notification = InAppNotificationFactory(tech_id=tech.tech_id, status="UNREAD")
    
    response = client.patch(f"/notifications/{notification.id}/read", headers=auth_headers())
    
    assert response.status_code == 200
    assert response.json()["status"] == "READ"
    assert response.json()["read_at"] is not None
    
    db_session.refresh(notification)
    assert notification.status == "READ"
    assert notification.read_at is not None

def test_mark_as_dismissed(client, db_session, auth_headers):
    tech = TechnicianFactory()
    authenticate_as_technician(tech)
    notification = InAppNotificationFactory(tech_id=tech.tech_id, status="UNREAD")
    
    response = client.patch(f"/notifications/{notification.id}/dismiss", headers=auth_headers())
    
    assert response.status_code == 200
    assert response.json()["status"] == "DISMISSED"
    
    db_session.refresh(notification)
    assert notification.status == "DISMISSED"
    assert notification.dismissed_at is not None

def test_unread_count(client, db_session, auth_headers):
    tech = TechnicianFactory()
    authenticate_as_technician(tech)
    
    for _ in range(5):
        InAppNotificationFactory(tech_id=tech.tech_id, status="UNREAD")
        
    for _ in range(3):
        InAppNotificationFactory(tech_id=tech.tech_id, status="READ")
        
    response = client.get(f"/technicians/{tech.tech_id}/notifications", headers=auth_headers())
    
    assert response.status_code == 200
    assert response.json()["unread_count"] == 5


def test_admin_notification_feed_is_authenticated_and_tenant_scoped(client, db_session):
    from app.models import InAppNotification

    own = InAppNotification(
        id=str(uuid.uuid4()), tenant_id="tenant-123", recipient_id="test-user",
        recipient_role="dispatcher", group_key="job_42:EN_ROUTE:2",
        job_id="42", type="dispatcher_en_route", title="Tech en route",
        body="The technician is travelling.", status="UNREAD", priority="NORMAL",
    )
    other_tenant = InAppNotification(
        id=str(uuid.uuid4()), tenant_id="tenant-other", recipient_id="test-user",
        recipient_role="dispatcher", group_key="job_43:EN_ROUTE:2",
        job_id="43", type="dispatcher_en_route", title="Other tenant",
        body="Must not be visible.", status="UNREAD", priority="NORMAL",
    )
    communication_agent_notification = InAppNotification(
        id=str(uuid.uuid4()), tenant_id="tenant-123", recipient_id="test-user",
        recipient_role="org_admin", group_key="job_44",
        job_id="44", type="en_route", title="Job #44 technician en route",
        body="Repair · Technician One", status="UNREAD", priority="NORMAL",
        event_version=3,
    )
    db_session.add_all([own, other_tenant, communication_agent_notification])
    db_session.commit()

    response = client.get("/admin/notifications")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert data["unread_count"] == 2
    assert {item["id"] for item in data["notifications"]} == {
        own.id,
        communication_agent_notification.id,
    }


def test_admin_notification_feed_allows_empty_list(client):
    response = client.get("/admin/notifications")
    assert response.status_code == 200
    assert response.json() == {"notifications": [], "unread_count": 0, "total": 0}

def test_pagination(client, db_session, auth_headers):
    tech = TechnicianFactory()
    authenticate_as_technician(tech)
    
    for _ in range(25):
        InAppNotificationFactory(tech_id=tech.tech_id)
        
    response = client.get(f"/technicians/{tech.tech_id}/notifications?limit=10&offset=0", headers=auth_headers())
    
    assert response.status_code == 200
    data = response.json()
    assert len(data["notifications"]) == 10
    assert data["total"] == 25
    
    response2 = client.get(f"/technicians/{tech.tech_id}/notifications?limit=10&offset=10", headers=auth_headers())
    assert len(response2.json()["notifications"]) == 10
    
    response3 = client.get(f"/technicians/{tech.tech_id}/notifications?limit=10&offset=20", headers=auth_headers())
    assert len(response3.json()["notifications"]) == 5

@pytest.mark.anyio
async def test_websocket_realtime(monkeypatch):
    captured_payloads = []
    
    async def mock_emit(event, data, room=None):
        captured_payloads.append((event, data, room))
        
    monkeypatch.setattr(socket_manager.sio, "emit", mock_emit)
    
    tech_id = str(uuid.uuid4())
    payload = {"title": "Test WS", "body": "Realtime notification"}
    
    # Simulate realtime delivery
    await socket_manager.emit_notification(tech_id, payload)
    
    assert len(captured_payloads) == 1
    event, data, room = captured_payloads[0]
    assert event == 'new_notification'
    assert data == payload
    assert room == tech_id

def test_batch_mark_read(client, db_session, auth_headers):
    tech = TechnicianFactory()
    authenticate_as_technician(tech)
    
    notifs = []
    for _ in range(5):
        notif = InAppNotificationFactory(tech_id=tech.tech_id, status="UNREAD")
        notifs.append(notif.id)
        
    payload = {"notification_ids": notifs}
    
    response = client.patch("/notifications/batch-read", json=payload, headers=auth_headers())
    
    assert response.status_code == 200
    assert response.json()["updated"] == 5
    
    for nid in notifs:
        n = db_session.query(models.InAppNotification).filter_by(id=nid).first()
        assert n.status == "READ"
        assert n.read_at is not None

def test_auto_delete(client, db_session, auth_headers):
    tech = TechnicianFactory()
    
    old_notif = InAppNotificationFactory(tech_id=tech.tech_id)
    # Manually backdate created_at to 31 days ago
    old_notif.created_at = datetime.now(timezone.utc) - timedelta(days=31)
    db_session.commit()
    
    recent_notif = InAppNotificationFactory(tech_id=tech.tech_id)
    recent_notif.created_at = datetime.now(timezone.utc) - timedelta(days=10)
    db_session.commit()
    
    response = client.delete("/notifications/system/cleanup", headers=auth_headers())
    assert response.status_code == 204
    
    remaining = db_session.query(models.InAppNotification).count()
    assert remaining == 1
    
    r_notif = db_session.query(models.InAppNotification).first()
    assert r_notif.id == recent_notif.id

def test_filter_by_type(client, db_session, auth_headers):
    tech = TechnicianFactory()
    authenticate_as_technician(tech)
    
    for _ in range(3):
        InAppNotificationFactory(tech_id=tech.tech_id, type="job_assignment")
        
    for _ in range(2):
        InAppNotificationFactory(tech_id=tech.tech_id, type="reminder")
        
    response = client.get(f"/technicians/{tech.tech_id}/notifications?type=job_assignment", headers=auth_headers())
    
    assert response.status_code == 200
    data = response.json()
    assert len(data["notifications"]) == 3
    assert data["total"] == 3
    
    response2 = client.get(f"/technicians/{tech.tech_id}/notifications?type=reminder", headers=auth_headers())
    assert len(response2.json()["notifications"]) == 2

def test_expired_notification(client, db_session, auth_headers):
    tech = TechnicianFactory()
    authenticate_as_technician(tech)
    
    # Active notification
    InAppNotificationFactory(
        tech_id=tech.tech_id, 
        expires_at=datetime.now(timezone.utc) + timedelta(days=1)
    )
    
    # Expired notification
    InAppNotificationFactory(
        tech_id=tech.tech_id, 
        expires_at=datetime.now(timezone.utc) - timedelta(days=1)
    )
    
    response = client.get(f"/technicians/{tech.tech_id}/notifications", headers=auth_headers())
    
    assert response.status_code == 200
    data = response.json()
    assert len(data["notifications"]) == 1
    assert data["total"] == 1
