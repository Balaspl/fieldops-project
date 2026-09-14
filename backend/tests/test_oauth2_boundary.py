"""
Authentication boundary tests — covers both the legacy JWT/dependency
layer and the OAuth2 /oauth2/token grant endpoint.

Uses the seeded dev user (customer@fieldops.com / Carl) created by the
app's startup seeding, since these tests run against the real dev DB
rather than an isolated test DB/fixture factory. If you later add a
proper test-DB setup, replace SEEDED_* constants with a fixture that
creates and tears down its own user.
"""

import jwt
import pytest
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.main import app
from app.auth.jwt_handler import (
    JWT_SECRET,
    JWT_ALGORITHM,
    create_access_token,
    create_refresh_token,
)

# --- known-good seeded user (adjust if your seed data differs) ---
SEEDED_EMAIL = "customer@fieldops.com"
SEEDED_PASSWORD = "Customer@123456"
SEEDED_TENANT_ID = "tenant-1"
SEEDED_ROLE = "customer"


@pytest.fixture
def client():
    return TestClient(app)


def make_access_token(
    user_id: str = "test-user",
    tenant_id: str = "tenant-test",
    role: str = "technician",
    expires_delta: timedelta | None = None,
):
    now = datetime.now(timezone.utc)
    if expires_delta is None:
        expires_delta = timedelta(minutes=30)

    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "role": role,
        "exp": now + expires_delta,
        "iat": now,
        "jti": "oauth2-boundary-test-jti",
        "type": "access",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


# ============================================================================
# OAuth2 Token Endpoint — grant behavior
# ============================================================================
# NOTE: There is no /auth/oauth2/contract endpoint anymore — that was a
# hardcoded stub and has been removed. Real OAuth2 behavior is tested
# against /oauth2/token below.


def test_password_grant_success(client):
    response = client.post(
        "/oauth2/token",
        data={
            "grant_type": "password",
            "username": SEEDED_EMAIL,
            "password": SEEDED_PASSWORD,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["expires_in"] > 0


def test_password_grant_wrong_password(client):
    response = client.post(
        "/oauth2/token",
        data={
            "grant_type": "password",
            "username": SEEDED_EMAIL,
            "password": "definitely-wrong",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "invalid_grant"


def test_password_grant_unknown_user_same_error_as_wrong_password(client):
    """No account-enumeration signal: unknown email and wrong password
    for a real email must return an identical error shape/status."""
    unknown = client.post(
        "/oauth2/token",
        data={"grant_type": "password", "username": "nobody@nowhere.com", "password": "x"},
    )
    wrong = client.post(
        "/oauth2/token",
        data={"grant_type": "password", "username": SEEDED_EMAIL, "password": "wrong"},
    )

    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"]["error"] == wrong.json()["detail"]["error"] == "invalid_grant"


def test_unsupported_grant_type_rejected(client):
    response = client.post("/oauth2/token", data={"grant_type": "client_credentials"})

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "unsupported_grant_type"


def test_missing_credentials_is_invalid_request(client):
    response = client.post("/oauth2/token", data={"grant_type": "password"})

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "invalid_request"


def test_refresh_token_grant_rotates_and_old_token_is_rejected(client):
    login = client.post(
        "/oauth2/token",
        data={"grant_type": "password", "username": SEEDED_EMAIL, "password": SEEDED_PASSWORD},
    ).json()

    refreshed = client.post(
        "/oauth2/token",
        data={"grant_type": "refresh_token", "refresh_token": login["refresh_token"]},
    )
    assert refreshed.status_code == 200
    new_body = refreshed.json()
    assert new_body["refresh_token"] != login["refresh_token"]

    # Replaying the old refresh token must now fail — single use enforced.
    replay = client.post(
        "/oauth2/token",
        data={"grant_type": "refresh_token", "refresh_token": login["refresh_token"]},
    )
    assert replay.status_code == 401
    assert replay.json()["detail"]["error"] == "invalid_grant"


def test_expired_refresh_token_rejected(client):
    expired = create_refresh_token(
        user_id="some-user-id",
        tenant_id=SEEDED_TENANT_ID,
        role=SEEDED_ROLE,
        expires_delta=timedelta(seconds=-1),
    )
    response = client.post(
        "/oauth2/token",
        data={"grant_type": "refresh_token", "refresh_token": expired},
    )
    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "invalid_grant"


def test_scope_is_narrowed_not_trusted(client):
    response = client.post(
        "/oauth2/token",
        data={
            "grant_type": "password",
            "username": SEEDED_EMAIL,
            "password": SEEDED_PASSWORD,
            "scope": "jobs:read admin:god-mode",
        },
    )
    assert response.status_code == 200
    granted = response.json()["scope"].split()
    assert "admin:god-mode" not in granted
@pytest.fixture(autouse=True)
def reset_seeded_user_lockout():
    from app.database import SessionLocal
    from app.models.user import User
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == SEEDED_EMAIL).first()
        if user:
            user.failed_login_attempts = 0
            user.locked_until = None
            db.commit()
    finally:
        db.close()
    yield

def test_parse_scope_empty_returns_empty_set():
    from app.auth.oauth2_scope import parse_scope

    assert parse_scope(None) == set()
    assert parse_scope("") == set()

def test_validate_requested_scope_empty_returns_empty():
    from app.auth.oauth2_scope import validate_requested_scope
    from app.auth.rbac import UserRole

    assert validate_requested_scope(UserRole.CUSTOMER, None) == ""
    assert validate_requested_scope(UserRole.CUSTOMER, "") == ""

def test_password_grant_invalid_user_role(client):
    from app.database import SessionLocal
    from app.models.user import User

    db = SessionLocal()

    try:
        user = (
            db.query(User)
            .filter(User.email == SEEDED_EMAIL)
            .first()
        )

        assert user is not None

        original_role = user.role
        user.role = "invalid_role"
        db.commit()

        response = client.post(
            "/oauth2/token",
            data={
                "grant_type": "password",
                "username": SEEDED_EMAIL,
                "password": SEEDED_PASSWORD,
            },
        )

        assert response.status_code == 401

        body = response.json()
        assert body["detail"]["error"] == "invalid_grant"
        assert body["detail"]["error_description"] == "User role is invalid"

    finally:
        user.role = original_role
        db.commit()
        db.close()
def test_validate_scope_converts_scope_error_to_grant_error():
    from unittest.mock import patch

    from app.routes.oauth2 import _validate_scope, GrantError
    from app.auth.rbac import UserRole

    class FakeUser:
        role = UserRole.CUSTOMER.value

    with patch(
        "app.routes.oauth2.validate_requested_scope",
        side_effect=ValueError("invalid scope"),
    ):
        with pytest.raises(GrantError) as exc_info:
            _validate_scope(FakeUser(), "jobs:read")

    assert exc_info.value.error == "invalid_scope"
    assert exc_info.value.description == "invalid scope"
    assert exc_info.value.status_code == 400


def test_refresh_token_stored_record_invalid_returns_401(client):
    import hashlib
    from datetime import datetime, timedelta, timezone

    from app.database import SessionLocal
    from app.models.user import RefreshToken

    db = SessionLocal()

    try:
        # 1. Obtain a valid refresh token.
        response = client.post(
            "/oauth2/token",
            data={
                "grant_type": "password",
                "username": SEEDED_EMAIL,
                "password": SEEDED_PASSWORD,
            },
        )

        assert response.status_code == 200

        refresh_token = response.json()["refresh_token"]

        # 2. Find the persisted refresh-token record.
        token_hash = hashlib.sha256(
            refresh_token.encode("utf-8")
        ).hexdigest()

        stored = (
            db.query(RefreshToken)
            .filter(
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked_at.is_(None),
            )
            .first()
        )

        assert stored is not None

        # 3. Make the stored token expired.
        # Do NOT set revoked_at because the OAuth2 query filters
        # revoked tokens out before reaching the is_valid check.
        stored.expires_at = (
            datetime.now(timezone.utc) - timedelta(minutes=1)
        )
        stored.revoked_at = None
        db.commit()

        # 4. Try to use the expired stored refresh token.
        response = client.post(
            "/oauth2/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )

        # 5. The stored token reaches:
        #     if not stored.is_valid:
        # and returns 401.
        assert response.status_code == 401

        body = response.json()

        assert body["detail"]["error"] == "invalid_grant"
        assert (
            body["detail"]["error_description"]
            == "Refresh token expired or already used"
        )

    finally:
        db.close()

def test_refresh_token_ownership_mismatch_returns_401(client):
    import hashlib

    from app.database import SessionLocal
    from app.models.user import RefreshToken
    from app.auth.jwt_handler import create_refresh_token

    db = SessionLocal()

    try:
        # 1. Obtain a valid refresh token for the seeded user.
        response = client.post(
            "/oauth2/token",
            data={
                "grant_type": "password",
                "username": SEEDED_EMAIL,
                "password": SEEDED_PASSWORD,
            },
        )

        assert response.status_code == 200

        original_refresh_token = response.json()["refresh_token"]

        # 2. Find the persisted database refresh-token record.
        token_hash = hashlib.sha256(
            original_refresh_token.encode("utf-8")
        ).hexdigest()

        stored = (
            db.query(RefreshToken)
            .filter(
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked_at.is_(None),
            )
            .first()
        )

        assert stored is not None

        # 3. Create a valid JWT refresh token belonging to
        # a DIFFERENT user.
        mismatched_refresh_token = create_refresh_token(
            user_id="different-user-id",
            tenant_id=SEEDED_TENANT_ID,
            role=SEEDED_ROLE,
        )

        # 4. Replace the stored token hash with the mismatched JWT hash.
        # This ensures the database lookup finds the record.
        mismatched_hash = hashlib.sha256(
            mismatched_refresh_token.encode("utf-8")
        ).hexdigest()

        stored.token_hash = mismatched_hash
        db.commit()

        # 5. Use the mismatched refresh token.
        response = client.post(
            "/oauth2/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": mismatched_refresh_token,
            },
        )

        # 6. Ownership validation must reject it.
        assert response.status_code == 401

        body = response.json()

        assert body["detail"]["error"] == "invalid_grant"
        assert (
            body["detail"]["error_description"]
            == "Refresh token ownership validation failed"
        )

    finally:
        db.close()

def test_refresh_token_user_deactivated_returns_401(client):
    from app.database import SessionLocal
    from app.models.user import User

    db = SessionLocal()

    try:
        response = client.post(
            "/oauth2/token",
            data={
                "grant_type": "password",
                "username": SEEDED_EMAIL,
                "password": SEEDED_PASSWORD,
            },
        )

        assert response.status_code == 200
        refresh_token = response.json()["refresh_token"]

        user = (
            db.query(User)
            .filter(User.email == SEEDED_EMAIL)
            .first()
        )

        assert user is not None

        original_active = user.is_active

        user.is_active = False
        db.commit()

        response = client.post(
            "/oauth2/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )

        assert response.status_code == 401

        body = response.json()
        assert body["detail"]["error"] == "invalid_grant"
        assert (
            body["detail"]["error_description"]
            == "User account not found or deactivated"
        )

    finally:
        user.is_active = original_active
        db.commit()
        db.close()
    
def test_refresh_token_tenant_mismatch_returns_401(client):
    import hashlib

    from app.database import SessionLocal
    from app.models.user import RefreshToken
    from app.auth.jwt_handler import create_refresh_token

    db = SessionLocal()

    try:
        response = client.post(
            "/oauth2/token",
            data={
                "grant_type": "password",
                "username": SEEDED_EMAIL,
                "password": SEEDED_PASSWORD,
            },
        )

        assert response.status_code == 200

        original_token = response.json()["refresh_token"]

        stored = (
            db.query(RefreshToken)
            .filter(
                RefreshToken.token_hash
                == hashlib.sha256(
                    original_token.encode("utf-8")
                ).hexdigest(),
                RefreshToken.revoked_at.is_(None),
            )
            .first()
        )

        assert stored is not None

        mismatched_token = create_refresh_token(
            user_id=str(stored.user_id),
            tenant_id="different-tenant",
            role=SEEDED_ROLE,
        )

        original_hash = stored.token_hash

        stored.token_hash = hashlib.sha256(
            mismatched_token.encode("utf-8")
        ).hexdigest()
        db.commit()

        response = client.post(
            "/oauth2/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": mismatched_token,
            },
        )

        assert response.status_code == 401

        body = response.json()
        assert body["detail"]["error"] == "invalid_grant"
        assert (
            body["detail"]["error_description"]
            == "Refresh token tenant validation failed"
        )

    finally:
        if stored is not None:
            stored.token_hash = original_hash
            db.commit()
        db.close()
def test_refresh_token_role_mismatch_returns_401(client):
    import hashlib

    from app.database import SessionLocal
    from app.models.user import RefreshToken
    from app.auth.jwt_handler import create_refresh_token

    db = SessionLocal()

    try:
        response = client.post(
            "/oauth2/token",
            data={
                "grant_type": "password",
                "username": SEEDED_EMAIL,
                "password": SEEDED_PASSWORD,
            },
        )

        assert response.status_code == 200

        original_token = response.json()["refresh_token"]

        original_hash = hashlib.sha256(
            original_token.encode("utf-8")
        ).hexdigest()

        stored = (
            db.query(RefreshToken)
            .filter(
                RefreshToken.token_hash == original_hash,
                RefreshToken.revoked_at.is_(None),
            )
            .first()
        )

        assert stored is not None

        mismatched_token = create_refresh_token(
            user_id=str(stored.user_id),
            tenant_id=SEEDED_TENANT_ID,
            role="technician",
        )

        mismatched_hash = hashlib.sha256(
            mismatched_token.encode("utf-8")
        ).hexdigest()

        stored.token_hash = mismatched_hash
        db.commit()

        response = client.post(
            "/oauth2/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": mismatched_token,
            },
        )

        assert response.status_code == 401

        body = response.json()
        assert body["detail"]["error"] == "invalid_grant"
        assert (
            body["detail"]["error_description"]
            == "Refresh token role validation failed"
        )

    finally:
        if stored is not None:
            stored.token_hash = original_hash
            db.commit()
        db.close()


def test_refresh_token_scope_is_narrowed(client):
    response = client.post(
        "/oauth2/token",
        data={
            "grant_type": "password",
            "username": SEEDED_EMAIL,
            "password": SEEDED_PASSWORD,
            "scope": "jobs:read admin:god-mode",
        },
    )

    assert response.status_code == 200

    refresh_token = response.json()["refresh_token"]

    response = client.post(
        "/oauth2/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": "jobs:read admin:god-mode",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["scope"] == "jobs:read"
    assert "admin:god-mode" not in body["scope"]


def test_missing_refresh_token_is_invalid_request(client):
    response = client.post(
        "/oauth2/token",
        data={
            "grant_type": "refresh_token",
        },
    )

    assert response.status_code == 400

    body = response.json()

    assert body["detail"]["error"] == "invalid_request"
    assert (
        body["detail"]["error_description"]
        == "refresh_token is required"
    )

def test_token_final_unsupported_grant_branch(client, monkeypatch):
    import app.routes.oauth2 as oauth2

    monkeypatch.setattr(
        oauth2,
        "SUPPORTED_GRANT_TYPES",
        {
            "password",
            "refresh_token",
            "test_fallback",
        },
    )

    response = client.post(
        "/oauth2/token",
        data={
            "grant_type": "test_fallback",
        },
    )

    assert response.status_code == 400

    body = response.json()

    assert body["detail"]["error"] == "unsupported_grant_type"
    assert (
        body["detail"]["error_description"]
        == "Unsupported grant type"
    )
# ==================================================================