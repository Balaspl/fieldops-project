"""
Enterprise SSO service.

Responsibilities:
- Generate cryptographically secure SSO state and nonce values.
- Store SSO state temporarily in Redis.
- Consume state exactly once during the callback.
- Resolve an external OIDC identity to an existing FieldOps user.
- Enforce FieldOps ownership of tenant and role.
- Reject unknown, disabled, or tenant-invalid identities.

Security model:
- The OIDC provider proves external identity.
- OIDCIdentity maps that identity to an existing FieldOps User.
- FieldOps User remains the source of truth for tenant and role.
- Provider claims must never assign FieldOps permissions.
- No FieldOps user is automatically created during SSO.
"""

import json
import logging
import os
import secrets
from typing import Any, Dict, Optional

import redis.asyncio as redis
from sqlalchemy.orm import Session

from ..models.oidc_identity import OIDCIdentity
from ..models.organization import Organization
from ..models.user import User

logger = logging.getLogger(__name__)


class SSOValidationError(Exception):
    """Raised when SSO state or identity validation fails."""


class SSOService:
    """Business logic for the FieldOps browser-based SSO flow."""

    STATE_TTL_SECONDS = 300
    STATE_KEY_PREFIX = "sso:state:"

    def __init__(self, redis_client: Optional[Any] = None) -> None:
        self._redis = redis_client

    def _get_redis(self):
        """
        Return the Redis client used for SSO state.

        If the application already injects a Redis client, pass it to
        SSOService(redis_client=...).

        Otherwise REDIS_URL is used.
        """
        if self._redis is None:
            redis_url = os.getenv(
                "REDIS_URL",
                "redis://localhost:6379/0",
            )

            self._redis = redis.from_url(
                redis_url,
                decode_responses=True,
            )

        return self._redis

    @classmethod
    def generate_state(cls) -> str:
        """
        Generate a cryptographically secure OAuth/OIDC state value.
        """
        return secrets.token_urlsafe(32)

    @classmethod
    def generate_nonce(cls) -> str:
        """
        Generate a cryptographically secure OIDC nonce.
        """
        return secrets.token_urlsafe(32)

    @classmethod
    def _state_key(cls, state: str) -> str:
        return f"{cls.STATE_KEY_PREFIX}{state}"

    async def store_state(
        self,
        state: str,
        nonce: str,
        redirect_uri: str,
    ) -> None:
        """
        Store state, nonce, and redirect URI temporarily in Redis.

        State is intentionally short-lived and is deleted after successful
        retrieval during the callback.
        """
        if not state:
            raise SSOValidationError(
                "SSO state is required"
            )

        if not nonce:
            raise SSOValidationError(
                "SSO nonce is required"
            )

        if not redirect_uri:
            raise SSOValidationError(
                "SSO redirect URI is required"
            )

        payload = {
            "nonce": nonce,
            "redirect_uri": redirect_uri,
        }

        try:
            redis_client = self._get_redis()

            await redis_client.set(
                self._state_key(state),
                json.dumps(payload),
                ex=self.STATE_TTL_SECONDS,
            )

        except Exception as exc:
            logger.exception(
                "Unable to store SSO state"
            )

            raise SSOValidationError(
                "Unable to initialize SSO session"
            ) from exc

    async def consume_state(
    self,
    state: str,
) -> Dict[str, str]:
      if not state:
          raise SSOValidationError(
              "SSO state is required"
          )
  
      redis_client = self._get_redis()
      key = self._state_key(state)
  
      consume_script = """
      local value = redis.call('GET', KEYS[1])
  
      if value then
          redis.call('DEL', KEYS[1])
      end
  
      return value
      """
  
      try:
          raw_payload = await redis_client.eval(
              consume_script,
              1,
              key,
          )
  
      except Exception as exc:
          logger.exception(
              "Unable to consume SSO state"
          )
  
          raise SSOValidationError(
              "Unable to validate SSO session"
          ) from exc
  
      if not raw_payload:
          raise SSOValidationError(
              "Invalid or expired SSO state"
          )
  
      try:
          payload = json.loads(raw_payload)
  
      except (TypeError, ValueError) as exc:
          raise SSOValidationError(
              "Invalid SSO state data"
          ) from exc
  
      if not isinstance(payload, dict):
          raise SSOValidationError(
              "Invalid SSO state data"
          )
  
      nonce = payload.get("nonce")
      redirect_uri = payload.get("redirect_uri")
  
      if not nonce:
          raise SSOValidationError(
              "SSO nonce is missing"
          )
  
      if not redirect_uri:
          raise SSOValidationError(
              "SSO redirect URI is missing"
          )
  
      return {
          "nonce": str(nonce),
          "redirect_uri": str(redirect_uri),
      }

    @staticmethod
    def resolve_user(
        db: Session,
        *,
        provider: str,
        issuer: str,
        subject: str,
    ) -> User:
        """
        Resolve an external OIDC identity to an existing FieldOps user.

        Provider claims are used only to identify the OIDCIdentity record.
        Tenant and role always come from the FieldOps User record.
        """
        if not provider:
            raise SSOValidationError(
                "SSO provider is missing"
            )

        if not issuer:
            raise SSOValidationError(
                "OIDC issuer is missing"
            )

        if not subject:
            raise SSOValidationError(
                "OIDC subject is missing"
            )

        identity = (
            db.query(OIDCIdentity)
            .filter(
                OIDCIdentity.provider == provider,
                OIDCIdentity.issuer == issuer,
                OIDCIdentity.subject == subject,
            )
            .first()
        )

        if identity is None:
            logger.warning(
                "SSO identity is not mapped "
                "provider=%s issuer=%s",
                provider,
                issuer,
            )

            raise SSOValidationError(
                "SSO identity is not mapped to a FieldOps user"
            )

        user = (
            db.query(User)
            .filter(
                User.id == identity.user_id,
            )
            .first()
        )

        if user is None:
            logger.warning(
                "OIDC identity points to missing user "
                "provider=%s",
                provider,
            )

            raise SSOValidationError(
                "SSO user mapping is invalid"
            )

        if not getattr(user, "is_active", True):
            logger.warning(
                "Disabled user attempted SSO "
                "user_id=%s",
                user.id,
            )

            raise SSOValidationError(
                "FieldOps user account is disabled"
            )

        if not user.tenant_id:
            logger.warning(
                "SSO user has no tenant "
                "user_id=%s",
                user.id,
            )

            raise SSOValidationError(
                "FieldOps user is not assigned to a tenant"
            )

        organization = (
            db.query(Organization)
            .filter(
                Organization.id == user.tenant_id,
            )
            .first()
        )

        if organization is None:
            logger.warning(
                "SSO user tenant does not exist "
                "user_id=%s tenant_id=%s",
                user.id,
                user.tenant_id,
            )

            raise SSOValidationError(
                "FieldOps tenant is invalid"
            )

        if not getattr(organization, "is_active", True):
            logger.warning(
                "SSO user tenant is inactive "
                "user_id=%s tenant_id=%s",
                user.id,
                user.tenant_id,
            )

            raise SSOValidationError(
                "FieldOps tenant is inactive"
            )

        if getattr(organization, "is_deleted", False):
            logger.warning(
                "SSO user tenant is deleted "
                "user_id=%s tenant_id=%s",
                user.id,
                user.tenant_id,
            )

            raise SSOValidationError(
                "FieldOps tenant is deleted"
            )

        return user

    async def close(self) -> None:
        """Close the internally-created Redis client."""
        if self._redis is not None:
            close_method = getattr(
                self._redis,
                "aclose",
                None,
            )

            if close_method is not None:
                await close_method()