"""
OpenID Connect provider validation.

Google is currently the supported OIDC provider.

Security model:
- Google proves the external identity.
- FieldOps maps that identity to an existing User.
- FieldOps remains the source of truth for tenant and role.
- No FieldOps user is automatically created from an OIDC login.
"""

import logging
import os
from typing import Any, Dict, Optional

import httpx
from authlib.jose import JsonWebKey, jwt

logger = logging.getLogger(__name__)


class OIDCValidationError(Exception):
    """Raised when an OIDC identity cannot be trusted."""


class OIDCConfig:
    """OIDC configuration loaded from environment variables."""

    def __init__(self) -> None:
        self.enabled = (
            os.getenv("OIDC_ENABLED", "false").strip().lower() == "true"
        )

        self.provider = os.getenv(
            "OIDC_PROVIDER",
            "google",
        ).strip().lower()

        self.issuer_url = os.getenv(
            "OIDC_ISSUER_URL",
            "https://accounts.google.com",
        ).rstrip("/")

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
        if not self.enabled:
            raise OIDCValidationError(
                "OIDC authentication is disabled"
            )

        if self.provider != "google":
            raise OIDCValidationError(
                "Unsupported OIDC provider"
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


class GoogleOIDCValidator:
    """Validate Google OIDC ID tokens."""

    DISCOVERY_PATH = "/.well-known/openid-configuration"

    def __init__(self, config: Optional[OIDCConfig] = None) -> None:
        self.config = config or OIDCConfig()

        self._discovery: Optional[Dict[str, Any]] = None
        self._jwks: Optional[Dict[str, Any]] = None

    async def _get_discovery(self) -> Dict[str, Any]:
        if self._discovery is not None:
            return self._discovery

        url = (
            f"{self.config.issuer_url}"
            f"{self.DISCOVERY_PATH}"
        )

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
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

        discovered_issuer = str(
            discovery.get("issuer", "")
        ).rstrip("/")

        if discovered_issuer != self.config.issuer_url:
            raise OIDCValidationError(
                "OIDC provider issuer does not match configured issuer"
            )

        self._discovery = discovery
        return discovery

    async def _get_jwks(self) -> Dict[str, Any]:
        if self._jwks is not None:
            return self._jwks

        discovery = await self._get_discovery()

        jwks_uri = discovery.get("jwks_uri")
        if not jwks_uri:
            raise OIDCValidationError(
                "OIDC provider did not publish a JWKS URI"
            )

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
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

        self._jwks = jwks
        return jwks

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
        - nonce when supplied
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

            # Explicitly validate standard registered claims.
            claims.validate()

        except Exception as exc:
            logger.warning(
                "OIDC ID token validation failed "
                "provider=%s",
                self.config.provider,
            )
            raise OIDCValidationError(
                "Invalid OIDC ID token"
            ) from exc

        issuer = str(claims.get("iss", "")).rstrip("/")

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

            if not token_nonce or token_nonce != expected_nonce:
                raise OIDCValidationError(
                    "OIDC nonce validation failed"
                )

        return dict(claims)


async def validate_google_id_token(
    id_token: str,
    expected_nonce: Optional[str] = None,
) -> Dict[str, Any]:
    """Convenience function for Google ID-token validation."""

    validator = GoogleOIDCValidator()

    return await validator.validate_id_token(
        id_token=id_token,
        expected_nonce=expected_nonce,
    )