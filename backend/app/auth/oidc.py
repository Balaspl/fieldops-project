
"""
OpenID Connect provider validation.

The configured OIDC provider is responsible for proving the
external identity.

FieldOps remains responsible for:
- user mapping
- tenant membership
- role
- permissions

No FieldOps user is automatically created from an OIDC login.
"""

import logging
import os
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import httpx
from authlib.jose import JsonWebKey, jwt

logger = logging.getLogger(__name__)


class OIDCValidationError(Exception):
    """Raised when an OIDC identity cannot be trusted."""


class OIDCConfig:
    """OIDC configuration loaded from environment variables."""

    def __init__(self) -> None:
        self.enabled = (
            os.getenv(
                "OIDC_ENABLED",
                "false",
            )
            .strip()
            .lower()
            == "true"
        )

        self.provider = os.getenv(
            "OIDC_PROVIDER",
            "google",
        ).strip().lower()

        self.issuer_url = os.getenv(
            "OIDC_ISSUER_URL",
            "https://accounts.google.com",
        ).strip().rstrip("/")

        self.client_id = os.getenv(
            "OIDC_CLIENT_ID",
            "",
        ).strip()

        self.client_secret = os.getenv(
            "OIDC_CLIENT_SECRET",
            "",
        ).strip()

        self.audience = os.getenv(
            "OIDC_AUDIENCE",
            self.client_id,
        ).strip()

    def validate(self) -> None:
        """Validate configured OIDC settings."""

        if not self.enabled:
            raise OIDCValidationError(
                "OIDC authentication is disabled"
            )

        if not self.provider:
            raise OIDCValidationError(
                "OIDC provider is not configured"
            )

        if not self.client_id:
            raise OIDCValidationError(
                "OIDC client ID is not configured"
            )

        if not self.issuer_url:
            raise OIDCValidationError(
                "OIDC issuer is not configured"
            )

        if not self.audience:
            raise OIDCValidationError(
                "OIDC audience is not configured"
            )


class OIDCProviderValidator:
    """
    Validate OIDC discovery metadata, authorization responses,
    token exchange, and ID tokens.

    The provider is selected through OIDC configuration.
    """

    DISCOVERY_PATH = "/.well-known/openid-configuration"

    def __init__(
        self,
        config: Optional[OIDCConfig] = None,
    ) -> None:
        self.config = config or OIDCConfig()

        self._discovery: Optional[Dict[str, Any]] = None
        self._jwks: Optional[Dict[str, Any]] = None

    async def _get_discovery(self) -> Dict[str, Any]:
        """
        Load and validate OIDC provider discovery metadata.

        The discovered issuer must exactly match the configured
        issuer.
        """

        if self._discovery is not None:
            return self._discovery

        url = (
            f"{self.config.issuer_url}"
            f"{self.DISCOVERY_PATH}"
        )

        try:
            async with httpx.AsyncClient(
                timeout=5.0
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
                discovery = response.json()

        except (httpx.HTTPError, ValueError) as exc:
            logger.warning(
                "OIDC discovery failed for provider=%s",
                self.config.provider,
            )

            raise OIDCValidationError(
                "Unable to load OIDC provider metadata"
            ) from exc

        if not isinstance(discovery, dict):
            raise OIDCValidationError(
                "Invalid OIDC provider metadata"
            )

        discovered_issuer = str(
            discovery.get("issuer", "")
        ).rstrip("/")

        if discovered_issuer != self.config.issuer_url:
            raise OIDCValidationError(
                "OIDC provider issuer does not match configured issuer"
            )

        self._discovery = discovery

        return discovery

    async def get_discovery(self) -> Dict[str, Any]:
        """
        Return validated OIDC provider discovery metadata.
        """

        self.config.validate()

        return await self._get_discovery()

    async def _get_jwks(self) -> Dict[str, Any]:
        """Load the provider's JSON Web Key Set."""

        if self._jwks is not None:
            return self._jwks

        discovery = await self._get_discovery()

        jwks_uri = discovery.get("jwks_uri")

        if not jwks_uri:
            raise OIDCValidationError(
                "OIDC provider did not publish a JWKS URI"
            )

        try:
            async with httpx.AsyncClient(
                timeout=5.0
            ) as client:
                response = await client.get(jwks_uri)
                response.raise_for_status()
                jwks = response.json()

        except (httpx.HTTPError, ValueError) as exc:
            logger.warning(
                "OIDC JWKS retrieval failed for provider=%s",
                self.config.provider,
            )

            raise OIDCValidationError(
                "Unable to load OIDC provider signing keys"
            ) from exc

        if not isinstance(jwks, dict):
            raise OIDCValidationError(
                "Invalid OIDC JWKS response"
            )

        self._jwks = jwks

        return jwks

    async def build_authorization_url(
        self,
        state: str,
        nonce: str,
        redirect_uri: str,
    ) -> str:
        """
        Build the OIDC authorization-code request URL.

        State and nonce are generated by the SSO service.
        The redirect URI is supplied by the server.
        """

        self.config.validate()

        if not state:
            raise OIDCValidationError(
                "OIDC state is required"
            )

        if not nonce:
            raise OIDCValidationError(
                "OIDC nonce is required"
            )

        if not redirect_uri:
            raise OIDCValidationError(
                "OIDC redirect URI is required"
            )

        discovery = await self._get_discovery()

        authorization_endpoint = discovery.get(
            "authorization_endpoint"
        )

        if not authorization_endpoint:
            raise OIDCValidationError(
                "OIDC provider did not publish authorization endpoint"
            )

        params = {
            "client_id": self.config.client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": "openid email profile",
            "state": state,
            "nonce": nonce,
        }

        return (
            f"{authorization_endpoint}"
            f"?{urlencode(params)}"
        )

    async def exchange_authorization_code(
        self,
        code: str,
        redirect_uri: str,
    ) -> Dict[str, Any]:
        """
        Exchange an authorization code for OIDC tokens.
        """

        self.config.validate()

        if not code:
            raise OIDCValidationError(
                "Authorization code is required"
            )

        if not redirect_uri:
            raise OIDCValidationError(
                "OIDC redirect URI is required"
            )

        if not self.config.client_secret:
            raise OIDCValidationError(
                "OIDC client secret is not configured"
            )

        discovery = await self._get_discovery()

        token_endpoint = discovery.get(
            "token_endpoint"
        )

        if not token_endpoint:
            raise OIDCValidationError(
                "OIDC provider did not publish token endpoint"
            )

        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
        }

        try:
            async with httpx.AsyncClient(
                timeout=5.0
            ) as client:
                response = await client.post(
                    token_endpoint,
                    data=data,
                )

                response.raise_for_status()
                token_response = response.json()

        except (httpx.HTTPError, ValueError) as exc:
            logger.warning(
                "OIDC authorization-code exchange failed "
                "provider=%s",
                self.config.provider,
            )

            raise OIDCValidationError(
                "Unable to exchange OIDC authorization code"
            ) from exc

        if not isinstance(token_response, dict):
            raise OIDCValidationError(
                "Invalid OIDC token response"
            )

        if token_response.get("error"):
            logger.warning(
                "OIDC provider returned token error "
                "provider=%s error=%s",
                self.config.provider,
                token_response.get("error"),
            )

            raise OIDCValidationError(
                "OIDC authorization code exchange failed"
            )

        if not token_response.get("id_token"):
            raise OIDCValidationError(
                "OIDC provider did not return an ID token"
            )

        return token_response

    async def validate_id_token(
        self,
        id_token: str,
        expected_nonce: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Validate an OIDC ID token and return trusted claims.

        Validates:
        - provider configuration
        - issuer
        - signature
        - audience
        - expiration
        - subject
        - nonce
        """

        self.config.validate()

        if not id_token:
            raise OIDCValidationError(
                "ID token is required"
            )

        jwks = await self._get_jwks()

        try:
            claims = jwt.decode(
                id_token,
                JsonWebKey.import_key_set(jwks),
                claims_options={
                    "iss": {
                        "essential": True,
                        "value": self.config.issuer_url,
                    },
                    "aud": {
                        "essential": True,
                        "value": self.config.audience,
                    },
                    "exp": {
                        "essential": True,
                    },
                    "sub": {
                        "essential": True,
                    },
                },
            )

            claims.validate()

        except Exception as exc:
            logger.exception(
                "OIDC ID token validation failed provider=%s: %s",
                self.config.provider,
                str(exc),
            )
            raise OIDCValidationError(
                "Invalid OIDC ID token"
            ) from exc

        issuer = str(
            claims.get("iss", "")
        ).rstrip("/")

        if issuer != self.config.issuer_url:
            raise OIDCValidationError(
                "Invalid OIDC issuer"
            )

        subject = claims.get("sub")

        if not subject:
            raise OIDCValidationError(
                "OIDC subject is missing"
            )

        if expected_nonce is not None:
            token_nonce = claims.get("nonce")

            if (
                not token_nonce
                or token_nonce != expected_nonce
            ):
                raise OIDCValidationError(
                    "OIDC nonce validation failed"
                )

        return dict(claims)


async def validate_google_id_token(
    id_token: str,
    expected_nonce: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Backward-compatible helper for the existing
    /auth/oidc/google endpoint.

    Existing code can continue importing this function.
    """

    validator = OIDCProviderValidator()

    return await validator.validate_id_token(
        id_token=id_token,
        expected_nonce=expected_nonce,
    )


# Backward-compatible alias.
#
# Existing code that still imports GoogleOIDCValidator
# will continue to work while the SSO route uses the
# provider-neutral OIDCProviderValidator name.
GoogleOIDCValidator = OIDCProviderValidator

