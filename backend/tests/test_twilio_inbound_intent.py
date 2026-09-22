"""
Integration test for Twilio inbound customer intent recognition.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import get_db
from app.models import User, EnterpriseAuditLog, Job
from app.services.enterprise_audit import AuditAction


# ==========================================================
# Test database
# ==========================================================

TestingEngine = create_engine(
    "sqlite://",
    connect_args={
        "check_same_thread": False,
    },
    poolclass=StaticPool,
)

# Only create the tables required by this integration test.
User.__table__.create(
    bind=TestingEngine
)

EnterpriseAuditLog.__table__.create(
    bind=TestingEngine
)

Job.__table__.create(
    bind=TestingEngine
)

TestingSessionLocal = sessionmaker(
    bind=TestingEngine,
    autoflush=False,
    expire_on_commit=False,
)


@pytest.fixture
def db_session() -> Iterator[Session]:
    session = TestingSessionLocal()

    try:
        # Ensure every test starts with a clean audit table.
        session.query(EnterpriseAuditLog).delete()
        session.query(User).delete()
        session.commit()

        yield session

    finally:
        session.rollback()
        session.close()


@pytest.fixture
def client(
    db_session: Session,
) -> Iterator[TestClient]:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = (
        override_get_db
    )

    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# ==========================================================
# Test data
# ==========================================================

TENANT_ID = "tenant-1"
CUSTOMER_ID = "customer-1"


def create_customer(
    db: Session,
) -> User:
    customer = User(
        id=CUSTOMER_ID,
        email="customer@test.com",
        password_hash="test-password-hash",
        first_name="Test",
        last_name="Customer",
        role="customer",
        tenant_id=TENANT_ID,
        phone_number="+15555550101",
        is_active=True,
        is_email_verified=True,
        deleted_at=None,
    )

    db.add(customer)
    db.commit()
    db.refresh(customer)

    return customer


# ==========================================================
# Customer intent recognition
# ==========================================================


def test_twilio_inbound_customer_intent_is_classified_and_audited(
    client: TestClient,
    db_session: Session,
) -> None:
    """
    Verify that an inbound Twilio customer message:

    1. identifies the customer from the phone number
    2. runs intent recognition
    3. creates INTENT_CLASSIFIED audit entry
    4. returns successful webhook response
    """

    customer = create_customer(
        db_session
    )

    response = client.post(
        "/webhooks/twilio-inbound",
        data={
            "MessageSid": "SM-test-message-001",
            "From": customer.phone_number,
            "Body": (
                "I want to cancel "
                "my service request"
            ),
        },
    )

    # ------------------------------------------------------
    # Webhook response
    # ------------------------------------------------------

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "ok"

    # ------------------------------------------------------
    # Audit record
    # ------------------------------------------------------

    audit_entry = (
        db_session.query(
            EnterpriseAuditLog
        )
        .filter(
            EnterpriseAuditLog.action
            == AuditAction.INTENT_CLASSIFIED,
            EnterpriseAuditLog.user_id
            == customer.id,
            EnterpriseAuditLog.tenant_id
            == TENANT_ID,
        )
        .first()
    )

    assert audit_entry is not None

    # ------------------------------------------------------
    # Audit identity
    # ------------------------------------------------------

    assert (
        audit_entry.action
        == AuditAction.INTENT_CLASSIFIED
    )

    assert (
        audit_entry.user_id
        == customer.id
    )

    assert (
        audit_entry.tenant_id
        == TENANT_ID
    )

    assert (
        audit_entry.entity_type
        == "customer_message"
    )

    # ------------------------------------------------------
    # Intent details
    # ------------------------------------------------------

    assert audit_entry.details is not None

    assert (
        "intent"
        in audit_entry.details
    )

    assert (
        "confidence"
        in audit_entry.details
    )

    assert (
        "requires_human"
        in audit_entry.details
    )

    assert (
        "language"
        in audit_entry.details
    )

    # ------------------------------------------------------
    # Expected classification
    # ------------------------------------------------------

    assert (
        audit_entry.details["intent"]
        == "CANCELLATION"
    )

    assert (
        audit_entry.details["language"]
        == "en"
    )


# ==========================================================
# Unknown customer
# ==========================================================


def test_twilio_inbound_unknown_phone_does_not_classify_intent(
    client: TestClient,
    db_session: Session,
) -> None:
    """
    Unknown phone numbers should not be
    treated as customers.
    """

    response = client.post(
        "/webhooks/twilio-inbound",
        data={
            "MessageSid": "SM-test-message-002",
            "From": "+15555559999",
            "Body": (
                "I want to cancel "
                "my service"
            ),
        },
    )

    # ------------------------------------------------------
    # Webhook response
    # ------------------------------------------------------

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "ok"

    # ------------------------------------------------------
    # No intent audit should be created
    # ------------------------------------------------------

    audit_entry = (
        db_session.query(
            EnterpriseAuditLog
        )
        .filter(
            EnterpriseAuditLog.action
            == AuditAction.INTENT_CLASSIFIED
        )
        .first()
    )

    assert audit_entry is None