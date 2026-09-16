"""
Browser-based enterprise SSO routes.

Flow:
    GET /auth/sso/login
        -> generate state + nonce
        -> store them in Redis
        -> redirect to configured OIDC provider

    GET /auth/sso/callback
        -> validate state
        -> exchange authorization code
        -> validate OIDC ID token + nonce
        -> resolve mapped FieldOps user
        -> issue normal FieldOps JWT
        -> store access + refresh tokens in HttpOnly cookies
        -> redirect to frontend

Security:
    - Provider proves external identity.
    - FieldOps maps that identity to an existing User.
    - FieldOps remains the source of truth for tenant and role.
    - Provider claims cannot assign FieldOps permissions.
    - No automatic FieldOps user creation.
    - State and nonce protect the browser OIDC flow.
    - Tokens are never placed in the frontend URL.
    - Browser session tokens are stored in HttpOnly cookies.
"""

import logging
import os
from typing import Optional
from urllib.parse import urlencode

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    status,
)
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..auth.oidc import (
    OIDCProviderValidator,
    OIDCValidationError,
)
from ..auth.sso_service import (
    SSOService,
    SSOValidationError,
)
from ..database import get_db
from .auth import (
    _build_token_response,
    _set_sso_cookies,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/auth/sso",
    tags=["SSO"],
)


def _get_oidc_provider() -> str:
    """
    Return the configured OIDC provider.
    """

    provider = os.getenv(
        "OIDC_PROVIDER",
        "google",
    ).strip().lower()

    if not provider:
        raise OIDCValidationError(
            "OIDC provider is not configured"
        )

    return provider


def _get_sso_redirect_uri(
    request: Request,
) -> str:
    """
    Build the server-controlled OIDC callback URI.

    The redirect URI is never accepted from the browser.
    """

    configured_uri = os.getenv(
        "OIDC_REDIRECT_URI",
        "",
    ).strip()

    if configured_uri:
        return configured_uri

    return str(
        request.url_for("sso_callback")
    )


def _get_frontend_success_url() -> str:
    """
    URL used after successful SSO.

    Tokens must never be placed in this URL.
    """

    return os.getenv(
        "SSO_FRONTEND_SUCCESS_URL",
        "http://localhost:5173/auth/sso/callback",
    ).strip()


def _get_frontend_error_url() -> str:
    """
    URL used after an SSO failure.
    """

    return os.getenv(
        "SSO_FRONTEND_ERROR_URL",
        "http://localhost:5173/login",
    ).strip()


def _frontend_error_redirect(
    error_code: str,
) -> RedirectResponse:
    """
    Redirect to the frontend using only a safe error code.

    Do not expose:
        - tokens
        - provider claims
        - exception messages
        - secrets
    """

    url = (
        _get_frontend_error_url()
        + "?"
        + urlencode(
            {
                "error": error_code,
            }
        )
    )

    return RedirectResponse(
        url=url,
        status_code=status.HTTP_302_FOUND,
    )


@router.get(
    "/login",
    name="sso_login",
)
async def sso_login(
    request: Request,
):
    """
    Start the OIDC authorization-code flow.
    """

    sso_service = SSOService()

    try:
        provider = _get_oidc_provider()

        # -----------------------------------------------------
        # Generate browser-flow security values.
        #
        # state -> protects against CSRF / authorization
        #          response injection.
        #
        # nonce -> binds the ID token to this login attempt.
        # -----------------------------------------------------

        state = sso_service.generate_state()
        nonce = sso_service.generate_nonce()

        redirect_uri = _get_sso_redirect_uri(
            request
        )

        # -----------------------------------------------------
        # Store state + nonce server-side.
        #
        # SSOService should make this:
        #   - short-lived
        #   - single-use
        # -----------------------------------------------------

        await sso_service.store_state(
            state=state,
            nonce=nonce,
            redirect_uri=redirect_uri,
        )

        # -----------------------------------------------------
        # Build provider authorization URL.
        # -----------------------------------------------------

        validator = OIDCProviderValidator()

        authorization_url = (
            await validator.build_authorization_url(
                state=state,
                nonce=nonce,
                redirect_uri=redirect_uri,
            )
        )

        logger.info(
            "Starting OIDC SSO flow "
            "provider=%s",
            provider,
        )

        return RedirectResponse(
            url=authorization_url,
            status_code=status.HTTP_302_FOUND,
        )

    except OIDCValidationError as exc:
        logger.warning(
            "Unable to start SSO: %s",
            str(exc),
        )

        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail="SSO provider is unavailable",
        ) from exc

    except SSOValidationError as exc:
        logger.warning(
            "Unable to initialize SSO: %s",
            str(exc),
        )

        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail="Unable to initialize SSO",
        ) from exc

    except Exception as exc:
        logger.exception(
            "Unexpected SSO initialization failure"
        )

        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail="Unable to initialize SSO",
        ) from exc

    finally:
        await sso_service.close()


@router.get(
    "/callback",
    name="sso_callback",
)
async def sso_callback(
    request: Request,
    code: Optional[str] = Query(
        default=None
    ),
    state: Optional[str] = Query(
        default=None
    ),
    error: Optional[str] = Query(
        default=None
    ),
    error_description: Optional[str] = Query(
        default=None
    ),
    db: Session = Depends(get_db),
):
    """
    Complete the OIDC authorization-code flow.

    The provider authenticates the user.

    FieldOps decides:
        - which user
        - which tenant
        - which role
        - which permissions
    """

    # ---------------------------------------------------------
    # 1. Provider-side authentication failure
    # ---------------------------------------------------------

    if error:
        logger.warning(
            "OIDC provider returned an error: %s",
            error,
        )

        # Intentionally do not expose error_description
        # to the frontend because it may contain provider
        # implementation details.

        return _frontend_error_redirect(
            "sso_provider_error"
        )

    # ---------------------------------------------------------
    # 2. State is mandatory
    # ---------------------------------------------------------

    if not state:
        logger.warning(
            "SSO callback received without state"
        )

        return _frontend_error_redirect(
            "invalid_state"
        )

    sso_service = SSOService()

    try:
        # -----------------------------------------------------
        # 3. Consume state from Redis.
        #
        # consume_state() must:
        #   - verify state
        #   - verify TTL
        #   - delete state
        #
        # Therefore the state becomes single-use.
        # -----------------------------------------------------

        try:
            state_data = (
                await sso_service.consume_state(
                    state=state,
                )
            )

        except SSOValidationError:
            logger.warning(
                "Invalid or expired SSO state"
            )

            return _frontend_error_redirect(
                "invalid_state"
            )

        nonce = state_data["nonce"]
        redirect_uri = state_data["redirect_uri"]

        # -----------------------------------------------------
        # 4. Authorization code is mandatory.
        # -----------------------------------------------------

        if not code:
            logger.warning(
                "SSO callback received without "
                "authorization code"
            )

            return _frontend_error_redirect(
                "missing_code"
            )

        # -----------------------------------------------------
        # 5. Get configured provider.
        # -----------------------------------------------------

        provider = _get_oidc_provider()

        # -----------------------------------------------------
        # 6. Exchange authorization code.
        #
        # Server talks directly to the OIDC provider.
        # Client secret stays on the backend.
        # -----------------------------------------------------

        validator = OIDCProviderValidator()

        token_response = (
            await validator.exchange_authorization_code(
                code=code,
                redirect_uri=redirect_uri,
            )
        )

        id_token = token_response.get(
            "id_token"
        )

        if not id_token:
            raise OIDCValidationError(
                "OIDC provider did not return an ID token"
            )

        # -----------------------------------------------------
        # 7. Validate ID token.
        #
        # The validator must verify:
        #
        #   - cryptographic signature
        #   - issuer
        #   - audience
        #   - expiration
        #   - subject
        #   - nonce
        # -----------------------------------------------------

        claims = await validator.validate_id_token(
            id_token=id_token,
            expected_nonce=nonce,
        )

        issuer = str(
            claims.get("iss", "")
        ).rstrip("/")

        subject = str(
            claims.get("sub", "")
        )

        if not issuer or not subject:
            raise OIDCValidationError(
                "OIDC identity is incomplete"
            )

        # -----------------------------------------------------
        # 8. Resolve external identity to an EXISTING
        #    FieldOps user.
        #
        # Important:
        #
        # Provider claims do NOT determine:
        #   - tenant
        #   - organization
        #   - role
        #   - permissions
        #
        # The database remains authoritative.
        # -----------------------------------------------------

        user = SSOService.resolve_user(
            db=db,
            provider=provider,
            issuer=issuer,
            subject=subject,
        )

        # -----------------------------------------------------
        # 9. Issue normal FieldOps JWT tokens.
        #
        # _build_token_response() uses:
        #
        #   user.id
        #   user.tenant_id
        #   user.role
        #
        # Therefore SSO does not bypass the existing
        # FieldOps authorization model.
        # -----------------------------------------------------

        fieldops_token_response = (
            _build_token_response(
                user=user,
                request=request,
                db=db,
            )
        )

        logger.info(
            "SSO authentication successful "
            "user_id=%s tenant_id=%s provider=%s",
            user.id,
            user.tenant_id,
            provider,
        )

        # -----------------------------------------------------
        # 10. Create secure browser session.
        #
        # IMPORTANT:
        #
        # We do NOT return the JWT directly to the browser
        # as JSON.
        #
        # We do NOT put the JWT into:
        #
        #     ?access_token=...
        #
        # Instead:
        #
        #     access token  -> HttpOnly cookie
        #     refresh token -> HttpOnly cookie
        #
        # JavaScript cannot directly read these cookies.
        # -----------------------------------------------------

        response = RedirectResponse(
            url=_get_frontend_success_url(),
            status_code=status.HTTP_302_FOUND,
        )

        _set_sso_cookies(
            response=response,
            access_token=(
                fieldops_token_response.access_token
            ),
            refresh_token=(
                fieldops_token_response.refresh_token
            ),
        )

        return response

    except OIDCValidationError as exc:
        logger.warning(
            "OIDC SSO validation failed: %s",
            str(exc),
        )

        return _frontend_error_redirect(
            "sso_authentication_failed"
        )

    except SSOValidationError as exc:
        logger.warning(
            "FieldOps SSO validation failed: %s",
            str(exc),
        )

        return _frontend_error_redirect(
            "sso_not_authorized"
        )

    except Exception:
        logger.exception(
            "Unexpected SSO callback failure"
        )

        return _frontend_error_redirect(
            "sso_unavailable"
        )

    finally:
        await sso_service.close()

