import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timezone, timedelta

from app.main import app
from app.models import Job, SLAEscalation, AuditEvent
from app.database import Base, get_db
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.auth.dependencies import (
    AuthenticatedUser,
    get_current_user,
    get_current_user_or_tenant,
)
from app.auth.rbac import UserRole


# Setup test DB
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


client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()

    db.query(Job).delete()
    db.query(SLAEscalation).delete()
    db.query(AuditEvent).delete()
    db.commit()

    yield db

    db.close()


@pytest.fixture(autouse=True)
def apply_overrides():
    app.dependency_overrides[get_db] = override_get_db

    test_user = AuthenticatedUser(
        user_id="test-user",
        tenant_id="__platform__",
        role=UserRole.SUPER_ADMIN,
        jti="test-jti",
        session_id="test-session",
    )

    def override_current_user():
        return test_user

    def override_current_user_or_tenant():
        return test_user, test_user.tenant_id

    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[get_current_user_or_tenant] = (
        override_current_user_or_tenant
    )

    yield

    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_user_or_tenant, None)


def test_create_queued_job():
    future_date = (
        datetime.now(timezone.utc) + timedelta(hours=2)
    ).isoformat()

    payload = {
        "customer_name": "Test Customer Queued",
        "location": "Test Location",
        "issue_description": "Test Issue",
        "priority": "HIGH",
        "service_type": "HVAC Repair",
        "contact_number": "9876543210",
        "preferred_service_date": "2026-06-15",
        "status": "QUEUED",
        "tenant_id": "tenant-test",
        "sla_deadline": future_date,
    }

    response = client.post("/jobs/", json=payload)

    assert response.status_code == 201

    data = response.json()

    assert data["status"] == "QUEUED"

    db = TestingSessionLocal()

    job = (
        db.query(Job)
        .filter(Job.id == data["id"])
        .first()
    )

    assert job is not None
    assert job.status == "QUEUED"
    assert job.tenant_id == "tenant-test"
    assert job.sla_deadline is not None

    db.close()


def test_create_escalated_job():
    payload = {
        "customer_name": "Test Customer Escalated",
        "location": "Test Location",
        "issue_description": "Test Issue",
        "priority": "P1",
        "service_type": "Plumbing Service",
        "contact_number": "9876543210",
        "preferred_service_date": "2026-06-15",
        "status": "ESCALATED",
        "tenant_id": "tenant-1",
    }

    response = client.post("/jobs/", json=payload)

    assert response.status_code == 201

    data = response.json()

    assert data["status"] == "ESCALATED"

    db = TestingSessionLocal()

    job = (
        db.query(Job)
        .filter(Job.id == data["id"])
        .first()
    )

    assert job is not None

    escalation = (
        db.query(SLAEscalation)
        .filter(SLAEscalation.job_id == job.id)
        .first()
    )

    assert escalation is not None
    assert escalation.status == "ESCALATED"
    assert escalation.manager_responded_at is None

    audit = (
        db.query(AuditEvent)
        .filter(AuditEvent.event_type == "SLA_ESCALATION")
        .first()
    )

    assert audit is not None
    assert audit.new_status == "ESCALATED"
    assert audit.tenant_id == "tenant-1"

    db.close()


def test_create_job_with_attempt_count():
    payload = {
        "customer_name": "Test Attempt Count",
        "location": "Test Location",
        "issue_description": "Test Issue",
        "priority": "LOW",
        "service_type": "Electrical Service",
        "contact_number": "9876543210",
        "preferred_service_date": "2026-06-15",
        "status": "QUEUED",
        "tenant_id": "tenant-test",
        "attempt_count": 3,
    }

    response = client.post("/jobs/", json=payload)

    assert response.status_code == 201

    data = response.json()

    assert data["attempt_count"] == 3

    # The PUT endpoint is tenant-scoped.
    # The job was created for tenant-test, so use a tenant-test
    # authenticated user for this update request.
    update_user = AuthenticatedUser(
        user_id="test-user",
        tenant_id="tenant-test",
        role=UserRole.DISPATCHER,
        jti="test-jti",
        session_id="test-session",
    )

    def override_update_current_user():
        return update_user

    app.dependency_overrides[get_current_user] = (
        override_update_current_user
    )

    update_payload = payload.copy()
    update_payload["attempt_count"] = 5

    response = client.put(
        f"/jobs/{data['id']}",
        json=update_payload,
    )

    assert response.status_code == 200

    data_up = response.json()

    assert data_up["attempt_count"] == 5
    
def test_create_job_with_required_skill():
    payload = {
        "customer_name": "Test Required Skill",
        "location": "Test Location",
        "issue_description": "Test Issue",
        "priority": "HIGH",
        "service_type": "HVAC Repair",
        "contact_number": "9876543210",
        "preferred_service_date": "2026-06-15",
        "status": "QUEUED",
        "tenant_id": "tenant-skill",
        "required_skill": "HVAC Specialist",
    }

    response = client.post("/jobs/", json=payload)

    assert response.status_code == 201

    data = response.json()

    db = TestingSessionLocal()
    job = (
        db.query(Job)
        .filter(Job.id == data["id"])
        .first()
    )

    assert job is not None
    assert job.required_skill == "HVAC Specialist"

    db.close()
    
def test_create_job_uses_authenticated_tenant_for_non_platform_user():
    test_user = AuthenticatedUser(
        user_id="tenant-user",
        tenant_id="tenant-authenticated",
        role=UserRole.DISPATCHER,
        jti="test-jti",
        session_id="test-session",
    )

    def override_tenant_user():
        return test_user, test_user.tenant_id

    app.dependency_overrides[get_current_user_or_tenant] = (
        override_tenant_user
    )

    payload = {
        "customer_name": "Authenticated Tenant Customer",
        "location": "Test Location",
        "issue_description": "Test Issue",
        "priority": "HIGH",
        "service_type": "HVAC Repair",
        "contact_number": "9876543210",
        "preferred_service_date": "2026-06-15",
        "status": "QUEUED",
        "tenant_id": "different-tenant",
    }

    response = client.post("/jobs/", json=payload)

    assert response.status_code == 201

    data = response.json()

    db = TestingSessionLocal()
    job = (
        db.query(Job)
        .filter(Job.id == data["id"])
        .first()
    )

    assert job is not None
    assert job.tenant_id == "tenant-authenticated"

    db.close()

def test_create_job_uses_authenticated_tenant_when_platform_tenant_id_is_missing():
    payload = {
        "customer_name": "Platform Fallback Customer",
        "location": "Test Location",
        "issue_description": "Test Issue",
        "priority": "HIGH",
        "service_type": "HVAC Repair",
        "contact_number": "9876543210",
        "preferred_service_date": "2026-06-15",
        "status": "QUEUED",
    }

    response = client.post("/jobs/", json=payload)

    assert response.status_code == 201

    data = response.json()

    db = TestingSessionLocal()
    job = (
        db.query(Job)
        .filter(Job.id == data["id"])
        .first()
    )

    assert job is not None
    assert job.tenant_id == "__platform__"

    db.close()

def test_create_job_maps_service_type_when_required_skill_is_blank():
    payload = {
        "customer_name": "Test Skill Mapping",
        "location": "Test Location",
        "issue_description": "Test Issue",
        "priority": "MEDIUM",
        "service_type": "HVAC Repair",
        "contact_number": "9876543210",
        "preferred_service_date": "2026-06-15",
        "status": "QUEUED",
        "tenant_id": "tenant-skill-map",
        "required_skill": "   ",
    }

    response = client.post("/jobs/", json=payload)

    assert response.status_code == 201

    data = response.json()

    db = TestingSessionLocal()
    job = (
        db.query(Job)
        .filter(Job.id == data["id"])
        .first()
    )

    assert job is not None
    assert job.required_skill
    assert job.required_skill != "   "

    db.close()
    
class FakeKafkaProducer:
    def __init__(self, result=True):
        self.result = result
        self.published_messages = []

    async def publish(self, message):
        self.published_messages.append(message)
        return self.result


def test_create_job_publishes_job_created_event():
    fake_producer = FakeKafkaProducer(result=True)
    app.state.kafka_producer = fake_producer

    payload = {
        "customer_name": "Kafka Event Customer",
        "location": "Test Location",
        "issue_description": "Test Issue",
        "priority": "HIGH",
        "service_type": "HVAC Repair",
        "contact_number": "9876543210",
        "preferred_service_date": "2026-06-15",
        "status": "QUEUED",
        "tenant_id": "tenant-kafka",
    }

    response = client.post(
        "/jobs/",
        json=payload,
        headers={"X-Correlation-ID": "corr-job-created-test"},
    )

    assert response.status_code == 201

    data = response.json()

    assert len(fake_producer.published_messages) == 1

    event = fake_producer.published_messages[0]

    assert event.message_type.value == "EVENT"
    assert event.topic == "fieldops.job.events"
    assert event.correlation_id == "corr-job-created-test"

    assert event.payload["event_type"] == "job-created"
    assert event.payload["event_id"] == (
        f"job-created:tenant-kafka:{data['id']}"
    )
    assert event.payload["job_id"] == str(data["id"])
    assert event.payload["tenant_id"] == "tenant-kafka"
    assert event.payload["schema_version"] == 1
    assert event.payload["timestamp"]


def test_create_job_succeeds_when_kafka_publish_fails():
    fake_producer = FakeKafkaProducer(result=False)
    app.state.kafka_producer = fake_producer

    payload = {
        "customer_name": "Kafka Failure Customer",
        "location": "Test Location",
        "issue_description": "Test Issue",
        "priority": "MEDIUM",
        "service_type": "Electrical Service",
        "contact_number": "9876543210",
        "preferred_service_date": "2026-06-15",
        "status": "QUEUED",
        "tenant_id": "tenant-kafka-failure",
    }

    response = client.post(
        "/jobs/",
        json=payload,
    )

    assert response.status_code == 201

    data = response.json()

    db = TestingSessionLocal()

    job = (
        db.query(Job)
        .filter(Job.id == data["id"])
        .first()
    )

    assert job is not None
    assert job.tenant_id == "tenant-kafka-failure"
    assert job.status == "QUEUED"

    assert len(fake_producer.published_messages) == 1

    db.close()
    
def test_create_job_succeeds_when_kafka_publish_raises():
    class FailingKafkaProducer:
        async def publish(self, message):
            raise RuntimeError("Kafka connection failed")

    app.state.kafka_producer = FailingKafkaProducer()

    payload = {
        "customer_name": "Kafka Exception Customer",
        "location": "Test Location",
        "issue_description": "Test Issue",
        "priority": "HIGH",
        "service_type": "HVAC Repair",
        "contact_number": "9876543210",
        "preferred_service_date": "2026-06-15",
        "status": "QUEUED",
        "tenant_id": "tenant-kafka-exception",
    }

    response = client.post("/jobs/", json=payload)

    assert response.status_code == 201

    data = response.json()

    db = TestingSessionLocal()

    job = (
        db.query(Job)
        .filter(Job.id == data["id"])
        .first()
    )

    assert job is not None
    assert job.tenant_id == "tenant-kafka-exception"
    assert job.status == "QUEUED"

    db.close()