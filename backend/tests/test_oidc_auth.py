"""
OIDC authentication and Google account-linking tests.

These tests verify:

1. Linked Google identity can log in.
2. Unlinked Google identity cannot log in.
3. Invalid Google tokens are rejected.
4. Disabled FieldOps users cannot log in.
5. Suspended organizations cannot log in.
6. Authenticated FieldOps users can link Google.
7. Linking the same Google identity again returns ALREADY_LINKED.
8. A Google identity cannot be linked to another FieldOps user.
9. Google linking does not create a new FieldOps user.
10. Unlinked Google login does not create a new FieldOps user.
11. Google claims cannot override the FieldOps role.
12. Google claims cannot override the FieldOps tenant.
13. Unknown OIDC identities do not produce a 500.
14. issuer + subject uniqueness is enforced by the database.
15. Missing id_token is rejected.
16. Empty id_token is rejected.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.auth.jwt_handler import create_access_token
from app.auth.oidc import OIDCValidationError
from app.database import SessionLocal
from app.main import app
from app.models.organization import Organization
from app.models.oidc_identity import OIDCIdentity
from app.models.user import User


client = TestClient(app)


# ============================================================================
# Database fixture
# ============================================================================


@pytest.fixture
def db():
    """
    Database session used for test setup and verification.

    The FastAPI application uses its own DB session, so test setup data
    is committed before API calls.
    """
    session = SessionLocal()

    try:
        yield session
    finally:
        session.close()


# ============================================================================
# Unique test-data helpers
# ============================================================================


def unique_subject(prefix="google"):
    """
    Generate a unique OIDC subject.

    Normal tests should never reuse the same issuer + subject pair.
    """
    return f"{prefix}-{uuid.uuid4().hex}"


def unique_email(prefix="test"):
    """Generate a unique email address."""
    return f"{prefix}-{uuid.uuid4().hex[:12]}@example.com"


# ============================================================================
# Google claims helper
# ============================================================================


def make_google_claims(
    subject=None,
    email=None,
    issuer="https://accounts.google.com",
):
    """
    Create fake validated Google OIDC claims.

    Google token validation itself is mocked. These claims represent the
    output that validate_google_id_token() would return after successful
    validation.
    """
    return {
        "iss": issuer,
        "sub": subject or unique_subject(),
        "email": email or unique_email("google"),
        "email_verified": True,
        "name": "Google Test User",
        "given_name": "Google",
        "family_name": "Test",
        "aud": "test-client-id",
    }


# ============================================================================
# Organization helper
# ============================================================================


def create_organization(
    db,
    name=None,
    status="ACTIVE",
):
    """
    Create a valid test organization.

    Organization.status is constrained to:
        ACTIVE
        SUSPENDED
        DELETED
    """

    organization = Organization(
        id=f"org-{uuid.uuid4().hex[:12]}",
        name=name or f"OIDC Test Organization {uuid.uuid4().hex[:8]}",
        slug=f"oidc-test-{uuid.uuid4().hex[:16]}",
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


# ============================================================================
# User helper
# ============================================================================


def create_user(
    db,
    organization,
    email=None,
    role="technician",
    is_active=True,
):
    """
    Create a valid FieldOps user.

    password_hash is required by the User database schema. The actual
    password is irrelevant for these OIDC tests because password login
    is never performed.
    """

    user = User(
        id=str(uuid.uuid4()),
        email=email or unique_email("fieldops"),

        # Required by users.password_hash.
        # This is intentionally a test-only placeholder because these
        # tests authenticate through OIDC/JWT, not password authentication.
        password_hash="test-password-hash",

        first_name="Test",
        last_name="Technician",
        role=role,
        tenant_id=organization.id,

        phone_number=None,
        fcm_token=None,
        device_type=None,

        is_active=is_active,
        is_email_verified=True,
        is_on_duty=True,

        failed_login_attempts=0,
        locked_until=None,
        last_login=None,

        deleted_at=None,
        deleted_by=None,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


# ============================================================================
# OIDC identity helper
# ============================================================================


def create_oidc_identity(
    db,
    user,
    subject=None,
    issuer="https://accounts.google.com",
):
    """
    Create an OIDC identity.

    A unique subject is generated unless a test explicitly needs to verify
    duplicate identity behavior.
    """

    identity = OIDCIdentity(
        id=str(uuid.uuid4()),
        user_id=user.id,
        provider="google",
        issuer=issuer,
        subject=subject or unique_subject(),
    )

    db.add(identity)
    db.commit()
    db.refresh(identity)

    return identity


# ============================================================================
# FieldOps JWT helpers
# ============================================================================


def create_fieldops_token(user):
    """
    Create a FieldOps access token for authenticated link requests.
    """

    return create_access_token(
        user_id=user.id,
        tenant_id=user.tenant_id,
        role=user.role,
    )


def auth_headers(user):
    """
    Authorization headers for authenticated FieldOps API requests.
    """

    token = create_fieldops_token(user)

    return {
        "Authorization": f"Bearer {token}",
    }


# ============================================================================
# 1. Linked Google account can log in
# ============================================================================


def test_google_oidc_login_linked_account(db):
    organization = create_organization(db)

    user = create_user(
        db,
        organization,
        email=unique_email("linked"),
        role="technician",
    )

    identity = create_oidc_identity(
        db,
        user,
    )

    claims = make_google_claims(
        subject=identity.subject,
        email=unique_email("google-linked"),
    )

    with patch(
        "app.routes.auth.validate_google_id_token",
        new=AsyncMock(return_value=claims),
    ):
        response = client.post(
            "/auth/oidc/google",
            json={
                "id_token": "fake-google-id-token",
            },
        )

    assert response.status_code == 200

    body = response.json()

    assert "access_token" in body
    assert "refresh_token" in body

    assert body["user"]["id"] == user.id
    assert body["user"]["email"] == user.email
    assert body["user"]["role"] == "technician"
    assert body["user"]["tenant_id"] == organization.id


# ============================================================================
# 2. Unlinked Google account rejected
# ============================================================================


def test_google_oidc_login_unlinked_account(db):
    """
    A Google identity that has never been linked must not automatically
    create a FieldOps user.
    """

    claims = make_google_claims(
        email=unique_email("unlinked"),
    )

    with patch(
        "app.routes.auth.validate_google_id_token",
        new=AsyncMock(return_value=claims),
    ):
        response = client.post(
            "/auth/oidc/google",
            json={
                "id_token": "fake-unlinked-google-token",
            },
        )

    assert response.status_code == 401

    body = response.json()

    assert "not linked" in body["detail"].lower()


# ============================================================================
# 3. Invalid Google token rejected
# ============================================================================


def test_google_oidc_login_invalid_token(db):
    with patch(
        "app.routes.auth.validate_google_id_token",
        new=AsyncMock(
            side_effect=OIDCValidationError(
                "Invalid Google ID token"
            )
        ),
    ):
        response = client.post(
            "/auth/oidc/google",
            json={
                "id_token": "invalid-google-token",
            },
        )

    assert response.status_code == 401


# ============================================================================
# 4. Disabled user rejected
# ============================================================================


def test_google_oidc_login_disabled_user(db):
    organization = create_organization(db)

    user = create_user(
        db,
        organization,
        email=unique_email("disabled"),
        is_active=False,
    )

    identity = create_oidc_identity(
        db,
        user,
    )

    claims = make_google_claims(
        subject=identity.subject,
        email=unique_email("google-disabled"),
    )

    with patch(
        "app.routes.auth.validate_google_id_token",
        new=AsyncMock(return_value=claims),
    ):
        response = client.post(
            "/auth/oidc/google",
            json={
                "id_token": "fake-disabled-user-token",
            },
        )

    assert response.status_code == 403


# ============================================================================
# 5. Suspended organization rejected
# ============================================================================


def test_google_oidc_login_inactive_organization(db):
    """
    The Organization model allows:
        ACTIVE
        SUSPENDED
        DELETED

    Therefore SUSPENDED is used to test inactive organization behavior.
    """

    organization = create_organization(
        db,
        status="SUSPENDED",
    )

    user = create_user(
        db,
        organization,
        email=unique_email("suspended-org"),
    )

    identity = create_oidc_identity(
        db,
        user,
    )

    claims = make_google_claims(
        subject=identity.subject,
        email=unique_email("google-suspended"),
    )

    with patch(
        "app.routes.auth.validate_google_id_token",
        new=AsyncMock(return_value=claims),
    ):
        response = client.post(
            "/auth/oidc/google",
            json={
                "id_token": "fake-suspended-org-token",
            },
        )

    assert response.status_code == 403


# ============================================================================
# 6. Link Google account
# ============================================================================


def test_google_oidc_link_account(db):
    organization = create_organization(db)

    user = create_user(
        db,
        organization,
        email=unique_email("link-user"),
    )

    claims = make_google_claims(
        email=unique_email("google-link"),
    )

    with patch(
        "app.routes.auth.validate_google_id_token",
        new=AsyncMock(return_value=claims),
    ):
        response = client.post(
            "/auth/oidc/google/link",
            headers=auth_headers(user),
            json={
                "id_token": "fake-google-link-token",
            },
        )

    assert response.status_code == 200

    body = response.json()

    assert body["status"] == "LINKED"
    assert body["provider"] == "google"

    identity = (
        db.query(OIDCIdentity)
        .filter(
            OIDCIdentity.user_id == user.id,
            OIDCIdentity.issuer == claims["iss"],
            OIDCIdentity.subject == claims["sub"],
        )
        .first()
    )

    assert identity is not None
    assert identity.user_id == user.id
    assert identity.provider == "google"


# ============================================================================
# 7. Same Google account linked again to same user
# ============================================================================


def test_google_oidc_link_same_account_again(db):
    organization = create_organization(db)

    user = create_user(
        db,
        organization,
        email=unique_email("same-link"),
    )

    identity = create_oidc_identity(
        db,
        user,
    )

    claims = make_google_claims(
        subject=identity.subject,
        email=unique_email("google-same-link"),
    )

    with patch(
        "app.routes.auth.validate_google_id_token",
        new=AsyncMock(return_value=claims),
    ):
        response = client.post(
            "/auth/oidc/google/link",
            headers=auth_headers(user),
            json={
                "id_token": "fake-google-token",
            },
        )

    assert response.status_code == 200

    body = response.json()

    assert body["status"] == "ALREADY_LINKED"
    assert body["provider"] == "google"


# ============================================================================
# 8. Google account already owned by another FieldOps user
# ============================================================================


def test_google_oidc_link_account_already_owned(db):
    organization = create_organization(db)

    owner = create_user(
        db,
        organization,
        email=unique_email("google-owner"),
    )

    second_user = create_user(
        db,
        organization,
        email=unique_email("second-user"),
    )

    # Deliberately use ONE Google subject for the existing owner.
    subject = unique_subject("already-owned")

    create_oidc_identity(
        db,
        owner,
        subject=subject,
    )

    claims = make_google_claims(
        subject=subject,
        email=unique_email("google-owned"),
    )

    with patch(
        "app.routes.auth.validate_google_id_token",
        new=AsyncMock(return_value=claims),
    ):
        response = client.post(
            "/auth/oidc/google/link",
            headers=auth_headers(second_user),
            json={
                "id_token": "fake-google-token",
            },
        )

    assert response.status_code == 409

    body = response.json()

    assert "already linked" in body["detail"].lower()


# ============================================================================
# 9. Linking Google does not create FieldOps user
# ============================================================================


def test_google_oidc_link_does_not_create_user(db):
    organization = create_organization(db)

    fieldops_user = create_user(
        db,
        organization,
        email=unique_email("existing-fieldops"),
    )

    google_email = unique_email("new-google")

    before_count = db.query(User).count()

    claims = make_google_claims(
        email=google_email,
    )

    with patch(
        "app.routes.auth.validate_google_id_token",
        new=AsyncMock(return_value=claims),
    ):
        response = client.post(
            "/auth/oidc/google/link",
            headers=auth_headers(fieldops_user),
            json={
                "id_token": "fresh-google-link-token",
            },
        )

    assert response.status_code == 200

    after_count = db.query(User).count()

    assert after_count == before_count

    # Google email must NOT become a new FieldOps user.
    google_user = (
        db.query(User)
        .filter(User.email == google_email)
        .first()
    )

    assert google_user is None

    # But an OIDC identity must exist and point to the existing user.
    identity = (
        db.query(OIDCIdentity)
        .filter(
            OIDCIdentity.issuer == claims["iss"],
            OIDCIdentity.subject == claims["sub"],
        )
        .first()
    )

    assert identity is not None
    assert identity.user_id == fieldops_user.id


# ============================================================================
# 10. Unlinked Google login does not create FieldOps user
# ============================================================================


def test_google_oidc_login_unlinked_does_not_create_user(db):
    before_count = db.query(User).count()

    claims = make_google_claims(
        email=unique_email("unlinked-no-create"),
    )

    with patch(
        "app.routes.auth.validate_google_id_token",
        new=AsyncMock(return_value=claims),
    ):
        response = client.post(
            "/auth/oidc/google",
            json={
                "id_token": "fresh-unlinked-token",
            },
        )

    assert response.status_code == 401

    after_count = db.query(User).count()

    assert after_count == before_count

    google_user = (
        db.query(User)
        .filter(User.email == claims["email"])
        .first()
    )

    assert google_user is None


# ============================================================================
# 11. Google cannot override FieldOps role
# ============================================================================


def test_google_oidc_login_uses_fieldops_role(db):
    organization = create_organization(db)

    user = create_user(
        db,
        organization,
        email=unique_email("role"),
        role="technician",
    )

    identity = create_oidc_identity(
        db,
        user,
    )

    claims = make_google_claims(
        subject=identity.subject,
        email=unique_email("google-role"),
    )

    # Attempt to inject a privileged role into Google claims.
    claims["role"] = "admin"

    with patch(
        "app.routes.auth.validate_google_id_token",
        new=AsyncMock(return_value=claims),
    ):
        response = client.post(
            "/auth/oidc/google",
            json={
                "id_token": "fake-role-token",
            },
        )

    assert response.status_code == 200

    body = response.json()

    assert body["user"]["role"] == "technician"
    assert body["user"]["role"] != "admin"


# ============================================================================
# 12. Google cannot override FieldOps tenant
# ============================================================================


def test_google_oidc_login_uses_fieldops_tenant(db):
    organization = create_organization(db)

    user = create_user(
        db,
        organization,
        email=unique_email("tenant"),
    )

    identity = create_oidc_identity(
        db,
        user,
    )

    claims = make_google_claims(
        subject=identity.subject,
        email=unique_email("google-tenant"),
    )

    # Attempt to inject an attacker-controlled tenant.
    claims["tenant_id"] = "attacker-tenant"

    with patch(
        "app.routes.auth.validate_google_id_token",
        new=AsyncMock(return_value=claims),
    ):
        response = client.post(
            "/auth/oidc/google",
            json={
                "id_token": "fake-tenant-token",
            },
        )

    assert response.status_code == 200

    body = response.json()

    assert body["user"]["tenant_id"] == organization.id
    assert body["user"]["tenant_id"] != "attacker-tenant"


# ============================================================================
# 13. Unknown OIDC identity does not produce 500
# ============================================================================


def test_google_oidc_unknown_identity_does_not_return_500(db):
    claims = make_google_claims(
        email=unique_email("unknown"),
    )

    with patch(
        "app.routes.auth.validate_google_id_token",
        new=AsyncMock(return_value=claims),
    ):
        response = client.post(
            "/auth/oidc/google",
            json={
                "id_token": "fake-unknown-token",
            },
        )

    assert response.status_code == 401
    assert response.status_code != 500

    body = response.json()

    assert "not linked" in body["detail"].lower()


# ============================================================================
# 14. issuer + subject uniqueness
# ============================================================================


def test_google_oidc_identity_unique_for_same_google_account(db):
    organization = create_organization(db)

    user_one = create_user(
        db,
        organization,
        email=unique_email("unique-one"),
    )

    user_two = create_user(
        db,
        organization,
        email=unique_email("unique-two"),
    )

    issuer = "https://accounts.google.com"
    subject = unique_subject("duplicate-test")

    first_identity = OIDCIdentity(
        id=str(uuid.uuid4()),
        user_id=user_one.id,
        provider="google",
        issuer=issuer,
        subject=subject,
    )

    db.add(first_identity)
    db.commit()

    second_identity = OIDCIdentity(
        id=str(uuid.uuid4()),
        user_id=user_two.id,
        provider="google",
        issuer=issuer,
        subject=subject,
    )

    db.add(second_identity)

    with pytest.raises(IntegrityError):
        db.commit()

    db.rollback()

    identities = (
        db.query(OIDCIdentity)
        .filter(
            OIDCIdentity.issuer == issuer,
            OIDCIdentity.subject == subject,
        )
        .all()
    )

    assert len(identities) == 1
    assert identities[0].user_id == user_one.id


# ============================================================================
# 15. Missing id_token
# ============================================================================


def test_google_oidc_login_missing_id_token():
    response = client.post(
        "/auth/oidc/google",
        json={},
    )

    # Your current application returns 400 for this malformed request.
    assert response.status_code == 400


# ============================================================================
# 16. Empty id_token
# ============================================================================


def test_google_oidc_login_empty_id_token():
    response = client.post(
        "/auth/oidc/google",
        json={
            "id_token": "",
        },
    )

    # Your current application returns 400 for this malformed request.
    assert response.status_code == 400