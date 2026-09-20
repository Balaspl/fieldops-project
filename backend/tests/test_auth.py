"""
Authentication and registration tests.

These tests verify:
1. Public registration creates a CUSTOMER.
2. The client cannot choose an internal role during registration.
3. The registered customer belongs to the supplied active organization.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.auth.rbac import UserRole
from app.database import SessionLocal
from app.main import app
from app.models.organization import Organization
from app.models.user import User


client = TestClient(app)


# ============================================================================
# Database fixture
# ============================================================================


@pytest.fixture
def db():
    """
    Database session used for test setup and verification.
    """
    session = SessionLocal()

    try:
        yield session
    finally:
        session.close()


# ============================================================================
# Test helpers
# ============================================================================


def create_test_organization(db):
    """
    Create an active organization for registration tests.
    """
    organization = Organization(
        id=f"org-{uuid.uuid4().hex[:12]}",
        name=f"Registration Test Organization {uuid.uuid4().hex[:8]}",
        slug=f"registration-test-{uuid.uuid4().hex[:12]}",
        status="ACTIVE",
        subscription_plan="FREE",
        max_users=10,
        max_technicians=50,
        max_jobs_per_month=500,
        settings={},
    )

    db.add(organization)
    db.commit()
    db.refresh(organization)

    return organization


# ============================================================================
# Customer registration
# ============================================================================


def test_public_registration_creates_customer(db):
    """
    Public registration must always create a CUSTOMER.

    The role must come from the server-side registration logic,
    not from the client request.
    """

    organization = create_test_organization(db)

    email = f"customer-{uuid.uuid4().hex[:8]}@example.com"

    response = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "Customer@123",
            "first_name": "Test",
            "last_name": "Customer",
            "tenant_id": organization.id,
        },
    )

    assert response.status_code == 201

    user = (
        db.query(User)
        .filter(
            User.email == email,
            User.tenant_id == organization.id,
        )
        .first()
    )

    assert user is not None
    assert user.role == UserRole.CUSTOMER.value
    assert user.tenant_id == organization.id


# ============================================================================
# Client cannot select an internal role
# ============================================================================


def test_public_registration_ignores_requested_internal_role(db):
    """
    Public registration must not allow the client to register as
    an internal FieldOps role such as DISPATCHER or TECHNICIAN.

    The registration endpoint must force the role to CUSTOMER.
    """

    organization = create_test_organization(db)

    email = f"customer-{uuid.uuid4().hex[:8]}@example.com"

    response = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "Customer@123",
            "first_name": "Test",
            "last_name": "Customer",
            "tenant_id": organization.id,
            "role": UserRole.DISPATCHER.value,
        },
    )

    assert response.status_code == 201

    user = (
        db.query(User)
        .filter(
            User.email == email,
            User.tenant_id == organization.id,
        )
        .first()
    )

    assert user is not None

    # The client-provided role must not override the server-side role.
    assert user.role == UserRole.CUSTOMER.value
    assert user.role != UserRole.DISPATCHER.value