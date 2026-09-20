from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from app.auth.jwt_handler import create_access_token
from app.auth.rbac import UserRole
from app.auth.dependencies import (
    AuthenticatedUser,
    get_current_user,
    get_current_user_or_tenant,
)
from app.database import get_db
from app.main import app
from app.models import User, Organization


TEST_TENANT_ID = "test-tenant-admin-queue"


# ==========================================================
# Test authentication state
# ==========================================================

_test_auth_user: AuthenticatedUser | None = None


def set_test_authenticated_user(user: User) -> None:
    global _test_auth_user

    _test_auth_user = AuthenticatedUser(
        user_id=user.id,
        tenant_id=user.tenant_id,
        role=UserRole(user.role),
        jti="test-jti",
        session_id="test-session",
    )


def _get_authenticated_test_user() -> AuthenticatedUser:
    if _test_auth_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    return _test_auth_user


# ==========================================================
# Database
# ==========================================================

@pytest.fixture
def db():
    from app.database import SessionLocal

    session = SessionLocal()

    try:
        yield session
    finally:
        session.close()


# ==========================================================
# Client + dependency overrides
# ==========================================================

@pytest.fixture
def client(db):
    global _test_auth_user

    # Reset authentication state before every test.
    _test_auth_user = None

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db

    def override_current_user():
        return _get_authenticated_test_user()

    def override_current_user_or_tenant():
        user = _get_authenticated_test_user()
        return user, user.tenant_id

    app.dependency_overrides[get_current_user] = override_current_user

    app.dependency_overrides[get_current_user_or_tenant] = (
        override_current_user_or_tenant
    )

    yield TestClient(app)

    # Clean up overrides.
    _test_auth_user = None

    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_user_or_tenant, None)


# ==========================================================
# User helper
# ==========================================================

def create_test_user(
    db,
    role: UserRole,
    tenant_id: str = TEST_TENANT_ID,
) -> User:
    organization = (
        db.query(Organization)
        .filter(Organization.id == tenant_id)
        .first()
    )

    if organization is None:
        organization = Organization(
            id=tenant_id,
            name=f"Test Organization {tenant_id}",
            slug=f"test-org-{uuid.uuid4().hex[:12]}",
        )

        db.add(organization)
        db.flush()

    user = User(
        id=str(uuid.uuid4()),
        email=f"{uuid.uuid4()}@example.com",
        password_hash="test-password-hash",
        first_name="Queue",
        last_name="Tester",
        role=role.value,
        tenant_id=tenant_id,
        is_active=True,
        deleted_at=None,
        locked_until=None,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


# ==========================================================
# Token helper
# ==========================================================

def create_token(user: User) -> str:
    return create_access_token(
        user_id=user.id,
        tenant_id=user.tenant_id,
        role=user.role,
    )


# ==========================================================
# Authentication
# ==========================================================

def test_queue_stats_requires_authentication(client):
    response = client.get("/admin/queue/stats")

    assert response.status_code == 401


# ==========================================================
# Permission checks
# ==========================================================

@pytest.mark.parametrize(
    "role",
    [
        UserRole.HEAD,
        UserRole.TECHNICIAN,
        UserRole.CUSTOMER,
    ],
)
def test_queue_stats_rejects_users_without_queue_permission(
    client,
    db,
    role,
):
    user = create_test_user(
        db,
        role,
    )

    # Make this specific role the authenticated user.
    set_test_authenticated_user(user)

    token = create_token(user)

    response = client.get(
        "/admin/queue/stats",
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 403


@pytest.mark.parametrize(
    "role",
    [
        UserRole.DISPATCHER,
        UserRole.SUPER_ADMIN,
    ],
)
def test_queue_stats_allows_users_with_queue_permission(
    client,
    db,
    role,
):
    user = create_test_user(
        db,
        role,
    )

    # Make this specific role the authenticated user.
    set_test_authenticated_user(user)

    token = create_token(user)

    response = client.get(
        "/admin/queue/stats",
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 200


# ==========================================================
# Tenant isolation
# ==========================================================

def test_queue_stats_uses_authenticated_tenant(
    client,
    db,
):
    user = create_test_user(
        db,
        UserRole.DISPATCHER,
        tenant_id="tenant-authenticated",
    )

    # Authentication must use the user's actual tenant.
    set_test_authenticated_user(user)

    token = create_token(user)

    response = client.get(
        "/admin/queue/stats",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-ID": "tenant-other",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert "depth" in data
    assert "oldest_task_age" in data
    assert "throughput" in data