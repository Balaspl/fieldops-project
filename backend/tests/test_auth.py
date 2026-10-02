"""
Customer authentication and registration tests.

These tests verify:

1. Public registration creates a CUSTOMER.
2. The client cannot choose an internal role during registration.
3. The registered customer belongs to the supplied active organization.
4. A registered CUSTOMER can authenticate through the normal login contract.
5. Invalid CUSTOMER credentials are rejected.
6. Unknown CUSTOMER credentials are rejected.
7. Inactive CUSTOMER accounts are rejected.
8. Locked CUSTOMER accounts return HTTP 423.
9. Weak registration passwords are rejected.
10. Missing registration tenant IDs are rejected.
11. Missing or inactive organizations are rejected.
12. Duplicate customer registration is rejected.
13. Registration normalizes customer identity fields correctly.
14. Password-strength validation covers all password rules.
"""

import uuid

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.auth.mfa_service import (
    is_mfa_required_for_role,
)
from app.auth.password import (
    PasswordValidationError,
    hash_password,
    validate_password_strength,
    verify_password,
)
from app.auth.rbac import UserRole
from app.database import SessionLocal
from app.main import app
from app.models.organization import Organization
from app.models.user import User
from app.redis_client import get_redis_client
from app.routes import auth as auth_module


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
# Authentication rate-limit isolation
# ============================================================================


@pytest.fixture(autouse=True)
def reset_auth_rate_limits():
    """
    Reset auth rate-limit counters before and after each test.

    The real middleware keys requests by client IP. Starlette's
    TestClient uses the same client identity across tests, so without
    clearing these keys unrelated tests can receive HTTP 429.
    """
    redis = get_redis_client()

    register_key = (
        "rate_limit:testclient:/auth/register"
    )
    login_key = (
        "rate_limit:testclient:/auth/login"
    )

    redis.delete(register_key)
    redis.delete(login_key)

    yield

    redis.delete(register_key)
    redis.delete(login_key)


# ============================================================================
# Test helpers
# ============================================================================


def create_test_organization(
    db,
    *,
    status: str = "ACTIVE",
):
    """
    Create an organization for authentication tests.

    Valid organization statuses are:
        ACTIVE
        SUSPENDED
        DELETED
    """
    organization = Organization(
        id=f"org-{uuid.uuid4().hex[:12]}",
        name=(
            "Registration Test Organization "
            f"{uuid.uuid4().hex[:8]}"
        ),
        slug=(
            "registration-test-"
            f"{uuid.uuid4().hex[:12]}"
        ),
        status=status,
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


def register_customer(
    organization_id: str,
    email: str,
    *,
    password: str = "Customer@123",
    first_name: str = "Test",
    last_name: str = "Customer",
    phone_number: str | None = None,
):
    """
    Register a customer through the same public API contract
    used by the application.
    """
    payload = {
        "email": email,
        "password": password,
        "first_name": first_name,
        "last_name": last_name,
        "tenant_id": organization_id,
    }

    if phone_number is not None:
        payload["phone_number"] = phone_number

    return client.post(
        "/auth/register",
        json=payload,
    )


def make_request(
    *,
    user_agent: str = "pytest",
):
    """
    Create a minimal Starlette Request for direct route-function tests.
    """
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/auth/register",
            "headers": [
                (
                    b"user-agent",
                    user_agent.encode(),
                ),
            ],
            "client": (
                "127.0.0.1",
                50000,
            ),
        }
    )


# ============================================================================
# Customer registration
# ============================================================================


def test_public_registration_creates_customer(db):
    """
    Public registration must always create a CUSTOMER.

    The role must come from server-side registration logic,
    not from the client request.
    """
    organization = create_test_organization(db)

    email = (
        f"customer-{uuid.uuid4().hex[:8]}"
        "@example.com"
    )

    response = register_customer(
        organization.id,
        email,
    )

    assert response.status_code == 201

    body = response.json()

    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0

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
    assert user.is_active is True
    assert user.is_email_verified is False


def test_public_registration_ignores_requested_internal_role(
    db,
):
    """
    Public registration must not allow the client to register
    as an internal FieldOps role.
    """
    organization = create_test_organization(db)

    email = (
        f"customer-{uuid.uuid4().hex[:8]}"
        "@example.com"
    )

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
    assert user.role == UserRole.CUSTOMER.value
    assert user.role != UserRole.DISPATCHER.value


def test_registration_normalizes_identity_fields_and_stores_phone(
    db,
):
    """
    Registration must normalize email/name whitespace and
    preserve the optional phone number.
    """
    organization = create_test_organization(db)

    email = (
        f"CUSTOMER-{uuid.uuid4().hex[:8]}"
        "@EXAMPLE.COM"
    )

    response = register_customer(
        organization.id,
        email,
        first_name="  Test  ",
        last_name="  Customer  ",
        phone_number="+919876543210",
    )

    assert response.status_code == 201

    user = (
        db.query(User)
        .filter(
            User.tenant_id == organization.id,
            User.email == email.lower(),
        )
        .first()
    )

    assert user is not None
    assert user.email == email.lower()
    assert user.first_name == "Test"
    assert user.last_name == "Customer"
    assert user.phone_number == "+919876543210"
    assert user.role == UserRole.CUSTOMER.value


# ============================================================================
# Registration validation
# ============================================================================


def test_registration_rejects_weak_password(db):
    """
    Passwords that do not satisfy the configured strength policy
    must be rejected by the registration endpoint.
    """
    organization = create_test_organization(db)

    response = register_customer(
        organization.id,
        (
            f"weak-{uuid.uuid4().hex[:8]}"
            "@example.com"
        ),
        password="customer1!",
    )

    assert response.status_code == 400

    body = response.json()

    assert body["detail"]["error"] == "WEAK_PASSWORD"
    assert body["detail"]["errors"]

    assert any(
        "uppercase" in error.lower()
        for error in body["detail"]["errors"]
    )


def test_registration_rejects_missing_organization(db):
    """
    Registration must reject an organization that does not exist
    or is not active.
    """
    missing_tenant_id = (
        f"missing-org-{uuid.uuid4().hex[:12]}"
    )

    response = register_customer(
        missing_tenant_id,
        (
            f"customer-{uuid.uuid4().hex[:8]}"
            "@example.com"
        ),
    )

    assert response.status_code == 404
    assert (
        response.json()["detail"]
        == "Organization not found or inactive"
    )


def test_registration_rejects_suspended_organization(db):
    """
    Registration must reject suspended organizations.

    SUSPENDED is the valid non-active organization state in the
    current database contract.
    """
    organization = create_test_organization(
        db,
        status="SUSPENDED",
    )

    email = (
        f"suspended-org-{uuid.uuid4().hex[:8]}"
        "@example.com"
    )

    response = register_customer(
        organization.id,
        email,
    )

    assert response.status_code == 404
    assert (
        response.json()["detail"]
        == "Organization not found or inactive"
    )


def test_registration_rejects_deleted_organization(db):
    """
    Registration must reject deleted organizations.
    """
    organization = create_test_organization(
        db,
        status="DELETED",
    )

    email = (
        f"deleted-org-{uuid.uuid4().hex[:8]}"
        "@example.com"
    )

    response = register_customer(
        organization.id,
        email,
    )

    assert response.status_code == 404
    assert (
        response.json()["detail"]
        == "Organization not found or inactive"
    )


def test_registration_rejects_duplicate_email_in_same_tenant(
    db,
):
    """
    Duplicate email registration inside the same organization
    must return HTTP 409.
    """
    organization = create_test_organization(db)

    email = (
        f"duplicate-{uuid.uuid4().hex[:8]}"
        "@example.com"
    )

    first_response = register_customer(
        organization.id,
        email,
    )

    assert first_response.status_code == 201

    second_response = register_customer(
        organization.id,
        email,
    )

    assert second_response.status_code == 409
    assert (
        second_response.json()["detail"]
        == (
            "A user with this email already exists "
            "in this organization"
        )
    )


@pytest.mark.anyio
async def test_registration_rejects_empty_tenant_id_directly(
    db,
):
    """
    Cover the route-level tenant_id guard.

    HTTP requests with an empty tenant_id are rejected by Pydantic
    before the route function executes, so this branch is exercised
    directly.
    """
    payload = auth_module.RegisterRequest.model_construct(
        email=(
            f"direct-{uuid.uuid4().hex[:8]}"
            "@example.com"
        ),
        password="Customer@123",
        first_name="Test",
        last_name="Customer",
        tenant_id="",
        phone_number=None,
    )

    request = make_request()

    with pytest.raises(HTTPException) as exc_info:
        await auth_module.register(
            payload,
            request,
            db,
        )

    assert exc_info.value.status_code == 400
    assert (
        exc_info.value.detail
        == "tenant_id is required"
    )


# ============================================================================
# Password validation coverage
# ============================================================================


def test_password_validation_accepts_strong_password():
    """
    A fully compliant password must pass validation.
    """
    validate_password_strength(
        "StrongPassword123!"
    )


def test_password_validation_accepts_eight_character_password():
    """
    Exactly eight characters is valid when all required character
    categories are present.
    """
    validate_password_strength(
        "Abcdef1!"
    )


@pytest.mark.parametrize(
    "password,expected_fragment",
    [
        (
            "A" * 129,
            "must not exceed 128 characters",
        ),
        (
            "abcdefgh1!",
            "uppercase",
        ),
        (
            "ABCDEFGH1!",
            "lowercase",
        ),
        (
            "Abcdefgh!",
            "digit",
        ),
        (
            "Abcdefgh1",
            "special",
        ),
        (
            "Ab1!",
            "at least 8 characters",
        ),
    ],
)
def test_password_validation_rejects_invalid_passwords(
    password,
    expected_fragment,
):
    """
    Exercise each password-strength failure branch.
    """
    with pytest.raises(
        PasswordValidationError
    ) as exc_info:
        validate_password_strength(password)

    errors = exc_info.value.errors

    assert errors

    assert any(
        expected_fragment.lower()
        in error.lower()
        for error in errors
    )


def test_password_hash_and_verification():
    """
    Password hashing must produce a verifiable bcrypt hash.
    """
    password = "Customer@123"

    password_hash = hash_password(password)

    assert password_hash
    assert password_hash != password

    assert verify_password(
        password,
        password_hash,
    ) is True

    assert verify_password(
        "WrongPassword@123",
        password_hash,
    ) is False


# ============================================================================
# Customer login
# ============================================================================


def test_customer_can_login_with_registered_credentials(db):
    """
    A registered CUSTOMER must be able to use the normal
    email/password authentication endpoint.
    """
    organization = create_test_organization(db)

    email = (
        f"customer-login-{uuid.uuid4().hex[:8]}"
        "@example.com"
    )

    registration = register_customer(
        organization.id,
        email,
    )

    assert registration.status_code == 201

    response = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": "Customer@123",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0

    assert body["user"]["email"] == email
    assert body["user"]["role"] == UserRole.CUSTOMER.value
    assert body["user"]["tenant_id"] == organization.id
    assert body["user"]["organization_name"] == organization.name


def test_customer_login_rejects_invalid_password(db):
    """
    Invalid passwords must be rejected.
    """
    organization = create_test_organization(db)

    email = (
        f"customer-login-{uuid.uuid4().hex[:8]}"
        "@example.com"
    )

    registration = register_customer(
        organization.id,
        email,
    )

    assert registration.status_code == 201

    response = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": "WrongPassword@123",
        },
    )

    assert response.status_code == 401
    assert (
        response.json()["detail"]
        == "Invalid email or password"
    )

    assert (
        db.query(User)
        .filter(
            User.email == email,
            User.tenant_id == organization.id,
        )
        .count()
        == 1
    )


def test_customer_login_rejects_unknown_email(db):
    """
    Unknown accounts must receive the same generic authentication
    failure as invalid passwords.
    """
    response = client.post(
        "/auth/login",
        json={
            "email": (
                f"unknown-{uuid.uuid4().hex[:8]}"
                "@example.com"
            ),
            "password": "Customer@123",
        },
    )

    assert response.status_code == 401
    assert (
        response.json()["detail"]
        == "Invalid email or password"
    )


def test_inactive_customer_cannot_login(db):
    """
    Inactive customer accounts must be rejected.
    """
    organization = create_test_organization(db)

    email = (
        f"inactive-{uuid.uuid4().hex[:8]}"
        "@example.com"
    )

    user = User(
        id=str(uuid.uuid4()),
        email=email,
        password_hash=hash_password(
            "Customer@123"
        ),
        first_name="Inactive",
        last_name="Customer",
        role=UserRole.CUSTOMER.value,
        tenant_id=organization.id,
        phone_number=None,
        is_active=False,
        is_email_verified=False,
    )

    db.add(user)
    db.commit()

    response = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": "Customer@123",
        },
    )

    assert response.status_code == 401
    assert (
        response.json()["detail"]
        == "Invalid email or password"
    )


def test_locked_customer_cannot_login(db):
    """
    Currently locked customer accounts must return HTTP 423.
    """
    from datetime import (
        datetime,
        timedelta,
        timezone,
    )

    organization = create_test_organization(db)

    email = (
        f"locked-{uuid.uuid4().hex[:8]}"
        "@example.com"
    )

    user = User(
        id=str(uuid.uuid4()),
        email=email,
        password_hash=hash_password(
            "Customer@123"
        ),
        first_name="Locked",
        last_name="Customer",
        role=UserRole.CUSTOMER.value,
        tenant_id=organization.id,
        phone_number=None,
        is_active=True,
        is_email_verified=False,
        locked_until=(
            datetime.now(timezone.utc)
            + timedelta(minutes=15)
        ),
        failed_login_attempts=5,
    )

    db.add(user)
    db.commit()

    response = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": "Customer@123",
        },
    )

    assert response.status_code == 423
    assert (
        response.json()["detail"]
        == (
            "Your account is locked. "
            "Please try again later."
        )
    )


# ============================================================================
# MFA role policy sanity check
# ============================================================================


@pytest.mark.parametrize(
    "role,expected",
    [
        (UserRole.CUSTOMER, False),
        (UserRole.TECHNICIAN, True),
        (UserRole.DISPATCHER, True),
        (UserRole.SUPER_ADMIN, True),
    ],
)
def test_mfa_role_policy(role, expected):
    """
    Customer login must not accidentally inherit internal-role MFA policy.
    """
    assert (
        is_mfa_required_for_role(role)
        is expected
    )