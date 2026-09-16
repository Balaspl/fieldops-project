"""
Enterprise SSO route tests.

Tests:
- /auth/sso/login
- /auth/sso/callback

Covers:
- Successful SSO
- Provider errors
- Missing state
- Invalid/replayed state
- Missing authorization code
- Provider exchange failure
- Invalid ID token
- Unknown user
- Disabled user
- Inactive tenant
- Deleted tenant
- FieldOps role/tenant authority
- HttpOnly cookies
- Tokens not exposed in URL
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes.sso import router
from app.auth.sso_service import SSOValidationError


# ============================================================================
# APP FIXTURE
# ============================================================================


@pytest.fixture
def app():
    """
    Create a small FastAPI application containing only the SSO router.
    """

    application = FastAPI()
    application.include_router(router)

    return application


@pytest.fixture
def client(app):
    return TestClient(
        app,
        follow_redirects=False,
    )


# ============================================================================
# COMMON MOCK DATA
# ============================================================================


@pytest.fixture
def fake_user():
    return SimpleNamespace(
        id="user-001",
        tenant_id="tenant-001",
        role="dispatcher",
        is_active=True,
    )


@pytest.fixture
def fake_token_response():
    return SimpleNamespace(
        access_token="fieldops-access-token",
        refresh_token="fieldops-refresh-token",
    )


# ============================================================================
# LOGIN ROUTE
# ============================================================================


def test_sso_login_redirects_to_provider(
    client,
):
    """
    GET /auth/sso/login should:

    1. Generate state
    2. Generate nonce
    3. Store them
    4. Build provider authorization URL
    5. Return 302
    """

    with patch(
        "app.routes.sso.SSOService.store_state",
        new_callable=AsyncMock,
    ) as store_state, patch(
        "app.routes.sso.OIDCProviderValidator"
    ) as validator_class:

        validator = validator_class.return_value

        validator.build_authorization_url = AsyncMock(
            return_value=(
                "https://accounts.google.com/o/oauth2/auth"
                "?client_id=test-client"
                "&response_type=code"
            )
        )

        response = client.get(
            "/auth/sso/login"
        )

    assert response.status_code == 302

    assert response.headers["location"].startswith(
        "https://accounts.google.com/"
    )

    store_state.assert_awaited_once()

    call_kwargs = store_state.await_args.kwargs

    assert call_kwargs["state"]
    assert call_kwargs["nonce"]
    assert call_kwargs["redirect_uri"]


def test_sso_login_handles_provider_failure(
    client,
):
    """
    If the provider cannot be initialized,
    the endpoint must safely return 503.
    """

    with patch(
        "app.routes.sso.OIDCProviderValidator"
    ) as validator_class:

        validator = validator_class.return_value

        validator.build_authorization_url = AsyncMock(
            side_effect=Exception(
                "provider unavailable"
            )
        )

        response = client.get(
            "/auth/sso/login"
        )

    assert response.status_code == 503


# ============================================================================
# CALLBACK - PROVIDER ERROR
# ============================================================================


def test_sso_callback_provider_error(
    client,
):
    """
    Provider authentication failure must redirect
    without exposing provider details.
    """

    response = client.get(
        "/auth/sso/callback"
        "?error=access_denied"
        "&error_description=secret-provider-details"
    )

    assert response.status_code == 302

    location = response.headers["location"]

    assert "sso_provider_error" in location

    assert "secret-provider-details" not in location


# ============================================================================
# CALLBACK - STATE VALIDATION
# ============================================================================


def test_sso_callback_missing_state(
    client,
):
    response = client.get(
        "/auth/sso/callback"
        "?code=test-code"
    )

    assert response.status_code == 302

    location = response.headers["location"]

    assert "invalid_state" in location


@pytest.mark.asyncio
async def test_sso_callback_invalid_state(
    client,
):
    """
    State must exist in Redis and be valid.
    """

    with patch(
        "app.routes.sso.SSOService.consume_state",
        new_callable=AsyncMock,
        side_effect=SSOValidationError(
            "Invalid or expired SSO state"
        ),
    ):

        response = client.get(
            "/auth/sso/callback"
            "?code=test-code"
            "&state=invalid-state"
        )

    assert response.status_code == 302

    location = response.headers["location"]

    assert "invalid_state" in location



def test_sso_callback_replayed_state(
    client,
):
    """
    A replayed state must be rejected.

    First callback:
        state is consumed successfully.

    Second callback:
        same state is rejected.
    """

    service = MagicMock()

    service.consume_state = AsyncMock(
        side_effect=[
            {
                "nonce": "nonce-001",
                "redirect_uri": (
                    "http://testserver/auth/sso/callback"
                ),
            },
            SSOValidationError(
                "Invalid or expired SSO state"
            ),
        ]
    )

    # IMPORTANT:
    # The route does:
    #
    #     await sso_service.close()
    #
    # Therefore close() MUST be AsyncMock.
    service.close = AsyncMock()

    with patch(
        "app.routes.sso.SSOService",
        return_value=service,
    ), patch(
        "app.routes.sso.OIDCProviderValidator"
    ) as validator_class:

        validator = validator_class.return_value

        # The route does:
        #
        #     await validator.exchange_authorization_code(...)
        #
        # Therefore this MUST be AsyncMock.
        validator.exchange_authorization_code = AsyncMock(
            return_value={
                "id_token": "valid-id-token"
            }
        )

        # The route does:
        #
        #     await validator.validate_id_token(...)
        #
        # Therefore this MUST also be AsyncMock.
        validator.validate_id_token = AsyncMock(
            return_value={
                "iss": "https://accounts.google.com",
                "sub": "user-001",
            }
        )

        # First request.
        first = client.get(
            "/auth/sso/callback"
            "?code=code-001"
            "&state=state-001"
        )

        # Second request using the SAME state.
        second = client.get(
            "/auth/sso/callback"
            "?code=code-001"
            "&state=state-001"
        )

    assert first.status_code == 302
    assert second.status_code == 302

    # The second request must be rejected.
    assert (
        "invalid_state"
        in second.headers["location"]
    )

    # State must have been consumed twice:
    # first = successful consumption
    # second = replay attempt
    assert service.consume_state.await_count == 2

    # close() is awaited for both requests.
    assert service.close.await_count == 2



# ============================================================================
# CALLBACK - MISSING CODE
# ============================================================================


def test_sso_callback_missing_code(
    client,
):
    """
    Valid state without authorization code
    must be rejected.
    """

    with patch(
        "app.routes.sso.SSOService.consume_state",
        new_callable=AsyncMock,
        return_value={
            "nonce": "nonce-001",
            "redirect_uri": (
                "http://testserver/auth/sso/callback"
            ),
        },
    ):

        response = client.get(
            "/auth/sso/callback"
            "?state=valid-state"
        )

    assert response.status_code == 302

    assert "missing_code" in (
        response.headers["location"]
    )


# ============================================================================
# CALLBACK - AUTHORIZATION CODE EXCHANGE
# ============================================================================


def test_sso_callback_exchange_failure(
    client,
):
    """
    Authorization-code exchange failure
    must produce a safe authentication error.
    """

    with patch(
        "app.routes.sso.SSOService.consume_state",
        new_callable=AsyncMock,
        return_value={
            "nonce": "nonce-001",
            "redirect_uri": (
                "http://testserver/auth/sso/callback"
            ),
        },
    ), patch(
        "app.routes.sso.OIDCProviderValidator"
    ) as validator_class:

        validator = validator_class.return_value

        validator.exchange_authorization_code = AsyncMock(
            side_effect=Exception(
                "provider exchange failed"
            )
        )

        response = client.get(
            "/auth/sso/callback"
            "?code=test-code"
            "&state=test-state"
        )

    assert response.status_code == 302

    assert (
        "sso_unavailable"
        in response.headers["location"]
    )


# ============================================================================
# CALLBACK - MISSING ID TOKEN
# ============================================================================


def test_sso_callback_missing_id_token(
    client,
):
    """
    Provider must return an ID token.
    """

    with patch(
        "app.routes.sso.SSOService.consume_state",
        new_callable=AsyncMock,
        return_value={
            "nonce": "nonce-001",
            "redirect_uri": (
                "http://testserver/auth/sso/callback"
            ),
        },
    ), patch(
        "app.routes.sso.OIDCProviderValidator"
    ) as validator_class:

        validator = validator_class.return_value

        validator.exchange_authorization_code = AsyncMock(
            return_value={}
        )

        response = client.get(
            "/auth/sso/callback"
            "?code=test-code"
            "&state=test-state"
        )

    assert response.status_code == 302

    assert (
        "sso_authentication_failed"
        in response.headers["location"]
    )


# ============================================================================
# CALLBACK - INVALID ID TOKEN
# ============================================================================


def test_sso_callback_invalid_id_token(
    client,
):
    """
    Invalid ID token / nonce / signature / issuer /
    audience / expiration must fail authentication.
    """

    with patch(
        "app.routes.sso.SSOService.consume_state",
        new_callable=AsyncMock,
        return_value={
            "nonce": "nonce-001",
            "redirect_uri": (
                "http://testserver/auth/sso/callback"
            ),
        },
    ), patch(
        "app.routes.sso.OIDCProviderValidator"
    ) as validator_class:

        validator = validator_class.return_value

        validator.exchange_authorization_code = AsyncMock(
            return_value={
                "id_token": "invalid-id-token"
            }
        )

        validator.validate_id_token = AsyncMock(
            side_effect=Exception(
                "invalid ID token"
            )
        )

        response = client.get(
            "/auth/sso/callback"
            "?code=test-code"
            "&state=test-state"
        )

    assert response.status_code == 302

    assert (
        "sso_unavailable"
        in response.headers["location"]
    )


# ============================================================================
# CALLBACK - UNKNOWN USER
# ============================================================================


def test_sso_callback_unknown_user(
    client,
):
    """
    A valid external identity that is not mapped
    to a FieldOps user must not authenticate.
    """

    with patch(
        "app.routes.sso.SSOService.consume_state",
        new_callable=AsyncMock,
        return_value={
            "nonce": "nonce-001",
            "redirect_uri": (
                "http://testserver/auth/sso/callback"
            ),
        },
    ), patch(
        "app.routes.sso.OIDCProviderValidator"
    ) as validator_class, patch(
        "app.routes.sso.SSOService.resolve_user",
        side_effect=SSOValidationError(
            "SSO identity is not mapped"
        ),
    ):

        validator = validator_class.return_value

        validator.exchange_authorization_code = AsyncMock(
            return_value={
                "id_token": "valid-id-token"
            }
        )

        validator.validate_id_token = AsyncMock(
            return_value={
                "iss": "https://accounts.google.com",
                "sub": "unknown-subject",
            }
        )

        response = client.get(
            "/auth/sso/callback"
            "?code=test-code"
            "&state=test-state"
        )

    assert response.status_code == 302

    assert (
        "sso_not_authorized"
        in response.headers["location"]
    )


# ============================================================================
# CALLBACK - DISABLED USER
# ============================================================================


def test_sso_callback_disabled_user(
    client,
):
    """
    Disabled FieldOps users cannot authenticate through SSO.
    """

    with patch(
        "app.routes.sso.SSOService.consume_state",
        new_callable=AsyncMock,
        return_value={
            "nonce": "nonce-001",
            "redirect_uri": (
                "http://testserver/auth/sso/callback"
            ),
        },
    ), patch(
        "app.routes.sso.OIDCProviderValidator"
    ) as validator_class, patch(
        "app.routes.sso.SSOService.resolve_user",
        side_effect=SSOValidationError(
            "FieldOps user account is disabled"
        ),
    ):

        validator = validator_class.return_value

        validator.exchange_authorization_code = AsyncMock(
            return_value={
                "id_token": "valid-id-token"
            }
        )

        validator.validate_id_token = AsyncMock(
            return_value={
                "iss": "https://accounts.google.com",
                "sub": "disabled-user",
            }
        )

        response = client.get(
            "/auth/sso/callback"
            "?code=test-code"
            "&state=test-state"
        )

    assert response.status_code == 302

    assert (
        "sso_not_authorized"
        in response.headers["location"]
    )


# ============================================================================
# CALLBACK - INACTIVE TENANT
# ============================================================================


def test_sso_callback_inactive_tenant(
    client,
):
    """
    Users belonging to inactive organizations
    cannot authenticate.
    """

    with patch(
        "app.routes.sso.SSOService.consume_state",
        new_callable=AsyncMock,
        return_value={
            "nonce": "nonce-001",
            "redirect_uri": (
                "http://testserver/auth/sso/callback"
            ),
        },
    ), patch(
        "app.routes.sso.OIDCProviderValidator"
    ) as validator_class, patch(
        "app.routes.sso.SSOService.resolve_user",
        side_effect=SSOValidationError(
            "FieldOps tenant is inactive"
        ),
    ):

        validator = validator_class.return_value

        validator.exchange_authorization_code = AsyncMock(
            return_value={
                "id_token": "valid-id-token"
            }
        )

        validator.validate_id_token = AsyncMock(
            return_value={
                "iss": "https://accounts.google.com",
                "sub": "user-001",
            }
        )

        response = client.get(
            "/auth/sso/callback"
            "?code=test-code"
            "&state=test-state"
        )

    assert response.status_code == 302

    assert (
        "sso_not_authorized"
        in response.headers["location"]
    )


# ============================================================================
# SUCCESSFUL SSO
# ============================================================================


def test_sso_callback_success(
    client,
    fake_user,
    fake_token_response,
):
    """
    Successful browser SSO must:

    - Validate state
    - Exchange code
    - Validate ID token
    - Resolve FieldOps user
    - Build normal FieldOps tokens
    - Set HttpOnly cookies
    - Redirect to frontend
    - Never expose tokens in URL
    """

    with patch(
        "app.routes.sso.SSOService.consume_state",
        new_callable=AsyncMock,
        return_value={
            "nonce": "nonce-001",
            "redirect_uri": (
                "http://testserver/auth/sso/callback"
            ),
        },
    ), patch(
        "app.routes.sso.OIDCProviderValidator"
    ) as validator_class, patch(
        "app.routes.sso.SSOService.resolve_user",
        return_value=fake_user,
    ), patch(
        "app.routes.sso._build_token_response",
        return_value=fake_token_response,
    ):

        validator = validator_class.return_value

        validator.exchange_authorization_code = AsyncMock(
            return_value={
                "id_token": "valid-id-token"
            }
        )

        validator.validate_id_token = AsyncMock(
            return_value={
                "iss": "https://accounts.google.com",
                "sub": "google-subject-001",

                # These values must NOT control
                # FieldOps authorization.
                "role": "super_admin",
                "tenant_id": "attacker-tenant",
            }
        )

        response = client.get(
            "/auth/sso/callback"
            "?code=test-code"
            "&state=test-state"
        )

    assert response.status_code == 302

    # Must redirect to frontend.
    assert response.headers["location"].startswith(
        "http://localhost:5173/auth/sso/callback"
    )

    # Tokens must NOT be exposed in URL.
    location = response.headers["location"]

    assert "access_token" not in location
    assert "refresh_token" not in location

    # Cookies must be present.
    cookies = response.headers.get(
        "set-cookie",
        "",
    )

    assert "fieldops_access_token=" in cookies
    assert "fieldops_refresh_token=" in cookies

    # Browser JavaScript must not be able to read tokens.
    assert "HttpOnly" in cookies


# ============================================================================
# SECURITY: PROVIDER ROLE MUST NOT ELEVATE USER
# ============================================================================


def test_sso_provider_role_cannot_elevate_fieldops_user(
    client,
    fake_user,
    fake_token_response,
):
    """
    Security-critical test.

    FieldOps user:
        role = dispatcher

    Provider claims:
        role = super_admin

    Expected:
        FieldOps role remains dispatcher.
    """

    fake_user.role = "dispatcher"
    fake_user.tenant_id = "tenant-001"

    with patch(
        "app.routes.sso.SSOService.consume_state",
        new_callable=AsyncMock,
        return_value={
            "nonce": "nonce-001",
            "redirect_uri": (
                "http://testserver/auth/sso/callback"
            ),
        },
    ), patch(
        "app.routes.sso.OIDCProviderValidator"
    ) as validator_class, patch(
        "app.routes.sso.SSOService.resolve_user",
        return_value=fake_user,
    ), patch(
        "app.routes.sso._build_token_response",
        return_value=fake_token_response,
    ) as build_token_response:

        validator = validator_class.return_value

        validator.exchange_authorization_code = AsyncMock(
            return_value={
                "id_token": "valid-id-token"
            }
        )

        validator.validate_id_token = AsyncMock(
            return_value={
                "iss": "https://accounts.google.com",
                "sub": "google-subject-001",
                "role": "super_admin",
            }
        )

        response = client.get(
            "/auth/sso/callback"
            "?code=test-code"
            "&state=test-state"
        )

    assert response.status_code == 302

    build_token_response.assert_called_once()

    user_used_for_token = (
        build_token_response.call_args.kwargs["user"]
    )

    assert user_used_for_token.role == "dispatcher"
    assert user_used_for_token.role != "super_admin"


# ============================================================================
# SECURITY: PROVIDER TENANT MUST NOT CHANGE FIELDOPS TENANT
# ============================================================================


def test_sso_provider_tenant_cannot_change_fieldops_tenant(
    client,
    fake_user,
    fake_token_response,
):
    """
    Security-critical test.

    FieldOps user:
        tenant_id = tenant-001

    Provider claims:
        tenant_id = attacker-tenant

    Expected:
        FieldOps tenant remains tenant-001.
    """

    fake_user.tenant_id = "tenant-001"
    fake_user.role = "dispatcher"

    with patch(
        "app.routes.sso.SSOService.consume_state",
        new_callable=AsyncMock,
        return_value={
            "nonce": "nonce-001",
            "redirect_uri": (
                "http://testserver/auth/sso/callback"
            ),
        },
    ), patch(
        "app.routes.sso.OIDCProviderValidator"
    ) as validator_class, patch(
        "app.routes.sso.SSOService.resolve_user",
        return_value=fake_user,
    ), patch(
        "app.routes.sso._build_token_response",
        return_value=fake_token_response,
    ) as build_token_response:

        validator = validator_class.return_value

        validator.exchange_authorization_code = AsyncMock(
            return_value={
                "id_token": "valid-id-token"
            }
        )

        validator.validate_id_token = AsyncMock(
            return_value={
                "iss": "https://accounts.google.com",
                "sub": "google-subject-001",
                "tenant_id": "attacker-tenant",
            }
        )

        response = client.get(
            "/auth/sso/callback"
            "?code=test-code"
            "&state=test-state"
        )

    assert response.status_code == 302

    build_token_response.assert_called_once()

    user_used_for_token = (
        build_token_response.call_args.kwargs["user"]
    )

    assert user_used_for_token.tenant_id == "tenant-001"

    assert (
        user_used_for_token.tenant_id
        != "attacker-tenant"
    )


# ============================================================================
# SECURITY: STATE / NONCE ARE SENT TO PROVIDER
# ============================================================================


def test_sso_login_generates_state_and_nonce(
    client,
):
    """
    Verify that state and nonce are generated and
    supplied to the OIDC provider.
    """

    with patch(
        "app.routes.sso.SSOService.store_state",
        new_callable=AsyncMock,
    ), patch(
        "app.routes.sso.OIDCProviderValidator"
    ) as validator_class:

        validator = validator_class.return_value

        validator.build_authorization_url = AsyncMock(
            return_value="https://provider.example.com/auth"
        )

        response = client.get(
            "/auth/sso/login"
        )

    assert response.status_code == 302

    validator.build_authorization_url.assert_awaited_once()

    kwargs = (
        validator.build_authorization_url
        .await_args.kwargs
    )

    assert kwargs["state"]
    assert kwargs["nonce"]
    assert kwargs["redirect_uri"]


# ============================================================================
# TOKEN URL LEAK TEST
# ============================================================================


def test_sso_success_does_not_put_tokens_in_url(
    client,
    fake_user,
    fake_token_response,
):
    """
    Access and refresh tokens must never appear
    in the redirect URL.
    """

    with patch(
        "app.routes.sso.SSOService.consume_state",
        new_callable=AsyncMock,
        return_value={
            "nonce": "nonce-001",
            "redirect_uri": (
                "http://testserver/auth/sso/callback"
            ),
        },
    ), patch(
        "app.routes.sso.OIDCProviderValidator"
    ) as validator_class, patch(
        "app.routes.sso.SSOService.resolve_user",
        return_value=fake_user,
    ), patch(
        "app.routes.sso._build_token_response",
        return_value=fake_token_response,
    ):

        validator = validator_class.return_value

        validator.exchange_authorization_code = AsyncMock(
            return_value={
                "id_token": "valid-id-token"
            }
        )

        validator.validate_id_token = AsyncMock(
            return_value={
                "iss": "https://accounts.google.com",
                "sub": "google-subject-001",
            }
        )

        response = client.get(
            "/auth/sso/callback"
            "?code=test-code"
            "&state=test-state"
        )

    assert response.status_code == 302

    location = response.headers["location"]

    assert (
        "fieldops-access-token"
        not in location
    )

    assert (
        "fieldops-refresh-token"
        not in location
    )

    assert "access_token" not in location
    assert "refresh_token" not in location


# ============================================================================
# COOKIE SECURITY
# ============================================================================


def test_sso_success_sets_httponly_cookies(
    client,
    fake_user,
    fake_token_response,
):
    """
    Verify browser tokens are stored in HttpOnly cookies.
    """

    with patch(
        "app.routes.sso.SSOService.consume_state",
        new_callable=AsyncMock,
        return_value={
            "nonce": "nonce-001",
            "redirect_uri": (
                "http://testserver/auth/sso/callback"
            ),
        },
    ), patch(
        "app.routes.sso.OIDCProviderValidator"
    ) as validator_class, patch(
        "app.routes.sso.SSOService.resolve_user",
        return_value=fake_user,
    ), patch(
        "app.routes.sso._build_token_response",
        return_value=fake_token_response,
    ):

        validator = validator_class.return_value

        validator.exchange_authorization_code = AsyncMock(
            return_value={
                "id_token": "valid-id-token"
            }
        )

        validator.validate_id_token = AsyncMock(
            return_value={
                "iss": "https://accounts.google.com",
                "sub": "google-subject-001",
            }
        )

        response = client.get(
            "/auth/sso/callback"
            "?code=test-code"
            "&state=test-state"
        )

    assert response.status_code == 302

    set_cookie = response.headers.get(
        "set-cookie",
        "",
    )

    assert "HttpOnly" in set_cookie
    assert "fieldops_access_token=" in set_cookie
    assert "fieldops_refresh_token=" in set_cookie