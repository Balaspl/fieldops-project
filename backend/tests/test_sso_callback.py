"""
Browser-based SSO callback tests.

Tests the /auth/sso/login → /auth/sso/callback flow end-to-end
using mocked OIDC calls and Redis state.

Scenarios:
 1.  Provider returns ?error → redirect with sso_provider_error
 2.  Callback missing state param → redirect with invalid_state
 3.  State not in Redis (expired / replayed) → redirect with invalid_state
 4.  Missing code param (state valid) → redirect with missing_code
 5.  Google token exchange fails (provider outage) → redirect with sso_authentication_failed
 6.  Google ID token invalid (bad nonce / signature) → redirect with sso_authentication_failed
 7.  Unknown OIDCIdentity (no user mapping) → redirect with sso_not_authorized
 8.  Disabled FieldOps user → redirect with sso_not_authorized
 9.  Inactive tenant → redirect with sso_not_authorized
10.  Successful SSO → 200 with access_token + refresh_token; role and
     tenant_id come from FieldOps DB, not from Google claims.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth.oidc import OIDCValidationError
from app.auth.sso_service import SSOValidationError
from app.database import SessionLocal
from app.main import app
from app.models.oidc_identity import OIDCIdentity
from app.models.organization import Organization
from app.models.user import User


# follow_redirects=False so we can inspect the redirect target
client = TestClient(app, follow_redirects=False)


# ──────────────────────────────────────────────────────────────────────────────
# Shared fixtures and helpers
# ──────────────────────────────────────────────────────────────────────────────


def _uid() -> str:
    return uuid.uuid4().hex[:12]


def _email(prefix: str = "sso") -> str:
    return f"{prefix}-{_uid()}@example.com"


@pytest.fixture
def db():
    """Raw DB session for test setup only."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _make_org(db, status: str = "ACTIVE") -> Organization:
    org = Organization(
        id=f"org-{_uid()}",
        name=f"SSO Test Org {_uid()}",
        slug=f"sso-{_uid()}",
        status=status,
        subscription_plan="FREE",
        max_users=10,
        max_technicians=50,
        max_jobs_per_month=500,
        settings={},
    )
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_user(
    db,
    organization: Organization,
    role: str = "technician",
    is_active: bool = True,
) -> User:
    user = User(
        id=str(uuid.uuid4()),
        email=_email("sso-user"),
        password_hash="test-hash",
        first_name="SSO",
        last_name="TestUser",
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


# ──────────────────────────────────────────────────────────────────────────────
# Shared mock payloads
# ──────────────────────────────────────────────────────────────────────────────

# Represents a successfully consumed Redis state entry.
_VALID_STATE_DATA: dict = {
    "nonce": "test-nonce-secure-abc123",
    "redirect_uri": "http://localhost:8000/auth/sso/callback",
}

# Represents validated Google ID token claims (nonce already matches).
_VALID_ID_TOKEN_CLAIMS: dict = {
    "iss": "https://accounts.google.com",
    "sub": f"google-{_uid()}",
    "email": "ssouser@example.com",
    "email_verified": True,
    "aud": "test-client-id",
    "nonce": _VALID_STATE_DATA["nonce"],
}

# Represents the raw Google token endpoint response.
_GOOGLE_TOKEN_RESPONSE: dict = {"id_token": "fake-google-id-token"}


# ──────────────────────────────────────────────────────────────────────────────
# Scenario 1 — Provider returns ?error param
# ──────────────────────────────────────────────────────────────────────────────


def test_sso_callback_provider_error_redirects_to_frontend():
    """
    When the OIDC provider returns an error query parameter the callback
    must immediately redirect to the frontend error URL.

    No Redis or token-exchange calls are made.
    """
    response = client.get(
        "/auth/sso/callback",
        params={
            "error": "access_denied",
            "error_description": "The user denied the request.",
        },
    )

    assert response.status_code == 302
    location = response.headers["location"]
    assert "sso_provider_error" in location


# ──────────────────────────────────────────────────────────────────────────────
# Scenario 2 — Missing state param
# ──────────────────────────────────────────────────────────────────────────────


def test_sso_callback_missing_state_redirects_with_invalid_state():
    """
    A callback received without a state parameter cannot be linked to an
    initiation request and must be rejected.
    """
    response = client.get(
        "/auth/sso/callback",
        params={"code": "some-auth-code"},
        # no state
    )

    assert response.status_code == 302
    location = response.headers["location"]
    assert "invalid_state" in location


# ──────────────────────────────────────────────────────────────────────────────
# Scenario 3 — State not found in Redis (expired or replayed)
# ──────────────────────────────────────────────────────────────────────────────


def test_sso_callback_expired_or_replayed_state_redirects_with_invalid_state():
    """
    A state value that is not present in Redis has either expired (TTL elapsed)
    or already been consumed (replay attempt).  Both cases must redirect with
    invalid_state.  Redis state is single-use.
    """
    with patch(
        "app.routes.sso.SSOService.consume_state",
        new=AsyncMock(
            side_effect=SSOValidationError("Invalid or expired SSO state")
        ),
    ):
        response = client.get(
            "/auth/sso/callback",
            params={
                "code": "some-auth-code",
                "state": "expired-or-forged-state-value",
            },
        )

    assert response.status_code == 302
    location = response.headers["location"]
    assert "invalid_state" in location


# ──────────────────────────────────────────────────────────────────────────────
# Scenario 4 — State valid but authorization code absent
# ──────────────────────────────────────────────────────────────────────────────


def test_sso_callback_missing_code_redirects_with_missing_code():
    """
    When state is valid (retrieved from Redis) but no authorization code is
    present in the callback, the flow cannot proceed.
    """
    with patch(
        "app.routes.sso.SSOService.consume_state",
        new=AsyncMock(return_value=_VALID_STATE_DATA),
    ):
        response = client.get(
            "/auth/sso/callback",
            params={"state": "valid-state-value"},
            # no code
        )

    assert response.status_code == 302
    location = response.headers["location"]
    assert "missing_code" in location


# ──────────────────────────────────────────────────────────────────────────────
# Scenario 5 — Token exchange fails (provider outage / network error)
# ──────────────────────────────────────────────────────────────────────────────


def test_sso_callback_token_exchange_failure_redirects_with_sso_authentication_failed():
    """
    When the call to exchange the authorization code with the OIDC provider
    fails (provider outage, network timeout, bad client secret), the callback
    must redirect with sso_authentication_failed — not expose the underlying
    error to the browser.
    """
    with patch(
        "app.routes.sso.SSOService.consume_state",
        new=AsyncMock(return_value=_VALID_STATE_DATA),
    ), patch(
        "app.routes.sso.GoogleOIDCValidator.exchange_authorization_code",
        new=AsyncMock(
            side_effect=OIDCValidationError(
                "Unable to exchange OIDC authorization code"
            )
        ),
    ):
        response = client.get(
            "/auth/sso/callback",
            params={
                "code": "provider-issued-code",
                "state": "valid-state-value",
            },
        )

    assert response.status_code == 302
    location = response.headers["location"]
    assert "sso_authentication_failed" in location


# ──────────────────────────────────────────────────────────────────────────────
# Scenario 6 — Invalid ID token (bad nonce / bad signature / expired)
# ──────────────────────────────────────────────────────────────────────────────


def test_sso_callback_invalid_id_token_redirects_with_sso_authentication_failed():
    """
    When the ID token returned by the provider fails cryptographic validation
    — wrong nonce, expired, tampered signature, wrong issuer — the callback
    must redirect with sso_authentication_failed.
    """
    with patch(
        "app.routes.sso.SSOService.consume_state",
        new=AsyncMock(return_value=_VALID_STATE_DATA),
    ), patch(
        "app.routes.sso.GoogleOIDCValidator.exchange_authorization_code",
        new=AsyncMock(return_value=_GOOGLE_TOKEN_RESPONSE),
    ), patch(
        "app.routes.sso.GoogleOIDCValidator.validate_id_token",
        new=AsyncMock(
            side_effect=OIDCValidationError("OIDC nonce validation failed")
        ),
    ):
        response = client.get(
            "/auth/sso/callback",
            params={
                "code": "provider-issued-code",
                "state": "valid-state-value",
            },
        )

    assert response.status_code == 302
    location = response.headers["location"]
    assert "sso_authentication_failed" in location


# ──────────────────────────────────────────────────────────────────────────────
# Scenario 7 — Google identity not mapped to any FieldOps user
# ──────────────────────────────────────────────────────────────────────────────


def test_sso_callback_unknown_identity_redirects_with_sso_not_authorized():
    """
    An external identity that has never been linked to a FieldOps user via
    POST /auth/oidc/google/link must be rejected.

    SSO must NEVER auto-create FieldOps user accounts.
    """
    with patch(
        "app.routes.sso.SSOService.consume_state",
        new=AsyncMock(return_value=_VALID_STATE_DATA),
    ), patch(
        "app.routes.sso.GoogleOIDCValidator.exchange_authorization_code",
        new=AsyncMock(return_value=_GOOGLE_TOKEN_RESPONSE),
    ), patch(
        "app.routes.sso.GoogleOIDCValidator.validate_id_token",
        new=AsyncMock(return_value=_VALID_ID_TOKEN_CLAIMS),
    ), patch(
        "app.routes.sso.SSOService.resolve_user",
        side_effect=SSOValidationError(
            "SSO identity is not mapped to a FieldOps user"
        ),
    ):
        response = client.get(
            "/auth/sso/callback",
            params={
                "code": "provider-issued-code",
                "state": "valid-state-value",
            },
        )

    assert response.status_code == 302
    location = response.headers["location"]
    assert "sso_not_authorized" in location


# ──────────────────────────────────────────────────────────────────────────────
# Scenario 8 — Mapped user account is disabled
# ──────────────────────────────────────────────────────────────────────────────


def test_sso_callback_disabled_user_redirects_with_sso_not_authorized():
    """
    When SSOService.resolve_user raises SSOValidationError because the
    FieldOps user is disabled (is_active=False), the callback must redirect
    with sso_not_authorized and must not issue tokens.
    """
    with patch(
        "app.routes.sso.SSOService.consume_state",
        new=AsyncMock(return_value=_VALID_STATE_DATA),
    ), patch(
        "app.routes.sso.GoogleOIDCValidator.exchange_authorization_code",
        new=AsyncMock(return_value=_GOOGLE_TOKEN_RESPONSE),
    ), patch(
        "app.routes.sso.GoogleOIDCValidator.validate_id_token",
        new=AsyncMock(return_value=_VALID_ID_TOKEN_CLAIMS),
    ), patch(
        "app.routes.sso.SSOService.resolve_user",
        side_effect=SSOValidationError("FieldOps user account is disabled"),
    ):
        response = client.get(
            "/auth/sso/callback",
            params={
                "code": "provider-issued-code",
                "state": "valid-state-value",
            },
        )

    assert response.status_code == 302
    location = response.headers["location"]
    assert "sso_not_authorized" in location


# ──────────────────────────────────────────────────────────────────────────────
# Scenario 9 — Mapped user's tenant is inactive / suspended / deleted
# ──────────────────────────────────────────────────────────────────────────────


def test_sso_callback_inactive_tenant_redirects_with_sso_not_authorized():
    """
    Tenant isolation is checked by SSOService.resolve_user.  When the user's
    organization is SUSPENDED or DELETED the service raises SSOValidationError
    and the callback must redirect with sso_not_authorized.
    """
    with patch(
        "app.routes.sso.SSOService.consume_state",
        new=AsyncMock(return_value=_VALID_STATE_DATA),
    ), patch(
        "app.routes.sso.GoogleOIDCValidator.exchange_authorization_code",
        new=AsyncMock(return_value=_GOOGLE_TOKEN_RESPONSE),
    ), patch(
        "app.routes.sso.GoogleOIDCValidator.validate_id_token",
        new=AsyncMock(return_value=_VALID_ID_TOKEN_CLAIMS),
    ), patch(
        "app.routes.sso.SSOService.resolve_user",
        side_effect=SSOValidationError("FieldOps tenant is inactive"),
    ):
        response = client.get(
            "/auth/sso/callback",
            params={
                "code": "provider-issued-code",
                "state": "valid-state-value",
            },
        )

    assert response.status_code == 302
    location = response.headers["location"]
    assert "sso_not_authorized" in location


# ──────────────────────────────────────────────────────────────────────────────
# Scenario 10 — Successful SSO login
# ──────────────────────────────────────────────────────────────────────────────


def test_sso_callback_success_issues_fieldops_tokens(db):
    """
    A fully valid SSO callback must:

    a) Return 200 with FieldOps access_token + refresh_token.
    b) Set token_type = "bearer".
    c) Derive role and tenant_id from the FieldOps User record, NOT from
       Google ID token claims.

    The test deliberately injects a fake role ("super_admin") and
    tenant_id ("attacker-tenant") into the mocked Google claims to prove
    that the FieldOps DB values are used instead.
    """
    organization = _make_org(db)
    user = _make_user(db, organization, role="technician")

    # Inject attacker-controlled values into Google claims — must be ignored.
    google_claims_with_injected_values = {
        **_VALID_ID_TOKEN_CLAIMS,
        "role": "super_admin",        # must be overridden
        "tenant_id": "attacker-tenant",  # must be overridden
    }

    with patch(
        "app.routes.sso.SSOService.consume_state",
        new=AsyncMock(return_value=_VALID_STATE_DATA),
    ), patch(
        "app.routes.sso.GoogleOIDCValidator.exchange_authorization_code",
        new=AsyncMock(return_value=_GOOGLE_TOKEN_RESPONSE),
    ), patch(
        "app.routes.sso.GoogleOIDCValidator.validate_id_token",
        new=AsyncMock(return_value=google_claims_with_injected_values),
    ), patch(
        "app.routes.sso.SSOService.resolve_user",
        return_value=user,
    ):
        response = client.get(
            "/auth/sso/callback",
            params={
                "code": "valid-google-code",
                "state": "valid-state-value",
            },
        )

    assert response.status_code == 200

    body = response.json()

    # Tokens must be present and well-formed.
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0

    # User identity must reflect FieldOps DB values, never Google claims.
    assert body["user"]["id"] == user.id
    assert body["user"]["role"] == "technician"         # not "super_admin"
    assert body["user"]["tenant_id"] == organization.id  # not "attacker-tenant"

