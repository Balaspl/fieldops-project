import pytest
import httpx

from unittest.mock import AsyncMock, MagicMock, patch

from app.auth.oidc import (
    OIDCConfig,
    OIDCValidationError,
    GoogleOIDCValidator,
    validate_google_id_token,
)


# -------------------------------------------------------------------
# Helper
# -------------------------------------------------------------------

class MockClaims(dict):
    """
    Dictionary-like claims object that behaves similarly to
    Authlib's claims object for unit testing.
    """

    def validate(self):
        pass


def make_valid_config():
    config = MagicMock()

    config.validate.return_value = None
    config.issuer_url = "https://accounts.google.com"
    config.audience = "client-123"
    config.provider = "google"
    config.client_id = "client-123"

    return config


# -------------------------------------------------------------------
# OIDCConfig tests
# -------------------------------------------------------------------

def test_oidc_config_defaults(monkeypatch):
    monkeypatch.delenv("OIDC_ENABLED", raising=False)
    monkeypatch.delenv("OIDC_PROVIDER", raising=False)
    monkeypatch.delenv("OIDC_ISSUER_URL", raising=False)
    monkeypatch.delenv("OIDC_CLIENT_ID", raising=False)
    monkeypatch.delenv("OIDC_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("OIDC_AUDIENCE", raising=False)

    config = OIDCConfig()

    assert config.enabled is False
    assert config.provider == "google"
    assert config.issuer_url == "https://accounts.google.com"
    assert config.client_id == ""
    assert config.client_secret == ""
    assert config.audience == ""


def test_oidc_config_reads_environment(monkeypatch):
    monkeypatch.setenv("OIDC_ENABLED", "true")
    monkeypatch.setenv("OIDC_PROVIDER", "google")
    monkeypatch.setenv(
        "OIDC_ISSUER_URL",
        "https://accounts.google.com/",
    )
    monkeypatch.setenv("OIDC_CLIENT_ID", "client-123")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "secret")
    monkeypatch.setenv("OIDC_AUDIENCE", "audience-123")

    config = OIDCConfig()

    assert config.enabled is True
    assert config.provider == "google"
    assert config.issuer_url == "https://accounts.google.com"
    assert config.client_id == "client-123"
    assert config.client_secret == "secret"
    assert config.audience == "audience-123"


def test_oidc_config_uses_client_id_as_default_audience(monkeypatch):
    monkeypatch.setenv("OIDC_ENABLED", "true")
    monkeypatch.setenv("OIDC_CLIENT_ID", "client-123")
    monkeypatch.delenv("OIDC_AUDIENCE", raising=False)

    config = OIDCConfig()

    assert config.audience == "client-123"


@pytest.mark.parametrize(
    "env, expected_message",
    [
        (
            {
                "OIDC_ENABLED": "false",
            },
            "OIDC authentication is disabled",
        ),
        (
            {
                "OIDC_ENABLED": "true",
                "OIDC_PROVIDER": "microsoft",
                "OIDC_CLIENT_ID": "client",
                "OIDC_AUDIENCE": "client",
            },
            "Unsupported OIDC provider",
        ),
        (
            {
                "OIDC_ENABLED": "true",
                "OIDC_PROVIDER": "google",
                "OIDC_CLIENT_ID": "",
                "OIDC_AUDIENCE": "client",
            },
            "OIDC client ID is not configured",
        ),
        (
            {
                "OIDC_ENABLED": "true",
                "OIDC_PROVIDER": "google",
                "OIDC_CLIENT_ID": "client",
                "OIDC_ISSUER_URL": "",
                "OIDC_AUDIENCE": "client",
            },
            "OIDC issuer is not configured",
        ),
        (
            {
                "OIDC_ENABLED": "true",
                "OIDC_PROVIDER": "google",
                "OIDC_CLIENT_ID": "client",
                "OIDC_AUDIENCE": "",
            },
            "OIDC audience is not configured",
        ),
    ],
)
def test_oidc_config_validation_errors(
    monkeypatch,
    env,
    expected_message,
):
    for key in (
        "OIDC_ENABLED",
        "OIDC_PROVIDER",
        "OIDC_ISSUER_URL",
        "OIDC_CLIENT_ID",
        "OIDC_CLIENT_SECRET",
        "OIDC_AUDIENCE",
    ):
        monkeypatch.delenv(key, raising=False)

    for key, value in env.items():
        monkeypatch.setenv(key, value)

    config = OIDCConfig()

    with pytest.raises(
        OIDCValidationError,
        match=expected_message,
    ):
        config.validate()


# -------------------------------------------------------------------
# Discovery tests
# -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_discovery_success():
    config = MagicMock()
    config.provider = "google"
    config.issuer_url = "https://accounts.google.com"

    validator = GoogleOIDCValidator(config)

    discovery_data = {
        "issuer": "https://accounts.google.com",
        "jwks_uri": "https://example.com/jwks",
    }

    response = MagicMock()
    response.json.return_value = discovery_data
    response.raise_for_status.return_value = None

    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=response)

    with patch(
        "app.auth.oidc.httpx.AsyncClient"
    ) as client_class:
        client_class.return_value.__aenter__.return_value = mock_client

        result = await validator._get_discovery()

    assert result == discovery_data
    assert validator._discovery == discovery_data

    mock_client.get.assert_awaited_once_with(
        "https://accounts.google.com/.well-known/openid-configuration"
    )


@pytest.mark.asyncio
async def test_get_discovery_uses_cache():
    config = MagicMock()
    config.provider = "google"
    config.issuer_url = "https://accounts.google.com"

    validator = GoogleOIDCValidator(config)

    cached = {
        "issuer": "https://accounts.google.com",
        "jwks_uri": "https://example.com/jwks",
    }

    validator._discovery = cached

    with patch(
        "app.auth.oidc.httpx.AsyncClient"
    ) as client_class:
        result = await validator._get_discovery()

    assert result == cached
    client_class.assert_not_called()


@pytest.mark.asyncio
async def test_get_discovery_http_error():
    config = MagicMock()
    config.provider = "google"
    config.issuer_url = "https://accounts.google.com"

    validator = GoogleOIDCValidator(config)

    with patch(
        "app.auth.oidc.httpx.AsyncClient"
    ) as client_class:
        mock_client = MagicMock()

        mock_client.get = AsyncMock(
            side_effect=httpx.HTTPError("network failure")
        )

        client_class.return_value.__aenter__.return_value = mock_client

        with pytest.raises(
            OIDCValidationError,
            match="Unable to load OIDC provider metadata",
        ):
            await validator._get_discovery()


@pytest.mark.asyncio
async def test_get_discovery_invalid_json():
    config = MagicMock()
    config.provider = "google"
    config.issuer_url = "https://accounts.google.com"

    validator = GoogleOIDCValidator(config)

    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.side_effect = ValueError("invalid json")

    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=response)

    with patch(
        "app.auth.oidc.httpx.AsyncClient"
    ) as client_class:
        client_class.return_value.__aenter__.return_value = mock_client

        with pytest.raises(
            OIDCValidationError,
            match="Unable to load OIDC provider metadata",
        ):
            await validator._get_discovery()


@pytest.mark.asyncio
async def test_get_discovery_issuer_mismatch():
    config = MagicMock()
    config.provider = "google"
    config.issuer_url = "https://accounts.google.com"

    validator = GoogleOIDCValidator(config)

    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "issuer": "https://evil.example.com",
        "jwks_uri": "https://example.com/jwks",
    }

    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=response)

    with patch(
        "app.auth.oidc.httpx.AsyncClient"
    ) as client_class:
        client_class.return_value.__aenter__.return_value = mock_client

        with pytest.raises(
            OIDCValidationError,
            match="OIDC provider issuer does not match configured issuer",
        ):
            await validator._get_discovery()


# -------------------------------------------------------------------
# JWKS tests
# -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_jwks_success():
    config = MagicMock()
    config.provider = "google"
    config.issuer_url = "https://accounts.google.com"

    validator = GoogleOIDCValidator(config)

    discovery = {
        "issuer": "https://accounts.google.com",
        "jwks_uri": "https://example.com/jwks",
    }

    validator._discovery = discovery

    jwks_data = {
        "keys": [
            {
                "kid": "test-key",
                "kty": "RSA",
            }
        ]
    }

    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = jwks_data

    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=response)

    with patch(
        "app.auth.oidc.httpx.AsyncClient"
    ) as client_class:
        client_class.return_value.__aenter__.return_value = mock_client

        result = await validator._get_jwks()

    assert result == jwks_data
    assert validator._jwks == jwks_data

    mock_client.get.assert_awaited_once_with(
        "https://example.com/jwks"
    )


@pytest.mark.asyncio
async def test_get_jwks_uses_cache():
    config = MagicMock()

    validator = GoogleOIDCValidator(config)

    cached = {
        "keys": [
            {
                "kid": "cached-key",
                "kty": "RSA",
            }
        ]
    }

    validator._jwks = cached

    with patch(
        "app.auth.oidc.httpx.AsyncClient"
    ) as client_class:
        result = await validator._get_jwks()

    assert result == cached
    client_class.assert_not_called()


@pytest.mark.asyncio
async def test_get_jwks_missing_jwks_uri():
    config = MagicMock()
    config.provider = "google"
    config.issuer_url = "https://accounts.google.com"

    validator = GoogleOIDCValidator(config)

    validator._discovery = {
        "issuer": "https://accounts.google.com",
    }

    with pytest.raises(
        OIDCValidationError,
        match="OIDC provider did not publish a JWKS URI",
    ):
        await validator._get_jwks()


@pytest.mark.asyncio
async def test_get_jwks_http_error():
    config = MagicMock()
    config.provider = "google"
    config.issuer_url = "https://accounts.google.com"

    validator = GoogleOIDCValidator(config)

    validator._discovery = {
        "issuer": "https://accounts.google.com",
        "jwks_uri": "https://example.com/jwks",
    }

    with patch(
        "app.auth.oidc.httpx.AsyncClient"
    ) as client_class:
        mock_client = MagicMock()

        mock_client.get = AsyncMock(
            side_effect=httpx.HTTPError("network failure")
        )

        client_class.return_value.__aenter__.return_value = mock_client

        with pytest.raises(
            OIDCValidationError,
            match="Unable to load OIDC provider signing keys",
        ):
            await validator._get_jwks()


@pytest.mark.asyncio
async def test_get_jwks_invalid_json():
    config = MagicMock()
    config.provider = "google"
    config.issuer_url = "https://accounts.google.com"

    validator = GoogleOIDCValidator(config)

    validator._discovery = {
        "issuer": "https://accounts.google.com",
        "jwks_uri": "https://example.com/jwks",
    }

    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.side_effect = ValueError("invalid json")

    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=response)

    with patch(
        "app.auth.oidc.httpx.AsyncClient"
    ) as client_class:
        client_class.return_value.__aenter__.return_value = mock_client

        with pytest.raises(
            OIDCValidationError,
            match="Unable to load OIDC provider signing keys",
        ):
            await validator._get_jwks()


# -------------------------------------------------------------------
# ID token validation tests
# -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_validate_id_token_empty_token():
    config = make_valid_config()
    validator = GoogleOIDCValidator(config)

    with pytest.raises(
        OIDCValidationError,
        match="ID token is required",
    ):
        await validator.validate_id_token("")


@pytest.mark.asyncio
async def test_validate_id_token_config_error():
    config = MagicMock()

    config.validate.side_effect = OIDCValidationError(
        "OIDC authentication is disabled"
    )

    validator = GoogleOIDCValidator(config)

    with pytest.raises(
        OIDCValidationError,
        match="OIDC authentication is disabled",
    ):
        await validator.validate_id_token("fake-token")


@pytest.mark.asyncio
async def test_validate_id_token_invalid_signature_or_claims():
    config = make_valid_config()
    validator = GoogleOIDCValidator(config)

    validator._jwks = {
        "keys": []
    }

    with patch(
        "app.auth.oidc.jwt.decode",
        side_effect=Exception("invalid signature"),
    ):
        with pytest.raises(
            OIDCValidationError,
            match="Invalid OIDC ID token",
        ):
            await validator.validate_id_token("fake-token")


@pytest.mark.asyncio
async def test_validate_id_token_claim_validation_failure():
    config = make_valid_config()
    validator = GoogleOIDCValidator(config)

    validator._jwks = {
        "keys": []
    }

    claims = MockClaims(
        iss="https://accounts.google.com",
        sub="google-user-123",
        aud="client-123",
        exp=9999999999,
    )

    claims.validate = MagicMock(
        side_effect=Exception("expired token")
    )

    with patch(
        "app.auth.oidc.jwt.decode",
        return_value=claims,
    ):
        with pytest.raises(
            OIDCValidationError,
            match="Invalid OIDC ID token",
        ):
            await validator.validate_id_token("fake-token")


@pytest.mark.asyncio
async def test_validate_id_token_issuer_mismatch():
    config = make_valid_config()
    validator = GoogleOIDCValidator(config)

    validator._jwks = {
        "keys": []
    }

    claims = MockClaims(
        iss="https://evil.example.com",
        sub="google-user-123",
        aud="client-123",
        exp=9999999999,
    )

    with patch(
        "app.auth.oidc.jwt.decode",
        return_value=claims,
    ):
        with pytest.raises(
            OIDCValidationError,
            match="Invalid OIDC issuer",
        ):
            await validator.validate_id_token("fake-token")


@pytest.mark.asyncio
async def test_validate_id_token_issuer_trailing_slash():
    config = make_valid_config()
    validator = GoogleOIDCValidator(config)

    validator._jwks = {
        "keys": []
    }

    claims = MockClaims(
        iss="https://accounts.google.com/",
        sub="google-user-123",
        aud="client-123",
        exp=9999999999,
    )

    with patch(
        "app.auth.oidc.jwt.decode",
        return_value=claims,
    ):
        result = await validator.validate_id_token("fake-token")

    assert result["iss"] == "https://accounts.google.com/"


@pytest.mark.asyncio
async def test_validate_id_token_missing_subject():
    config = make_valid_config()
    validator = GoogleOIDCValidator(config)

    validator._jwks = {
        "keys": []
    }

    claims = MockClaims(
        iss="https://accounts.google.com",
        aud="client-123",
        exp=9999999999,
    )

    with patch(
        "app.auth.oidc.jwt.decode",
        return_value=claims,
    ):
        with pytest.raises(
            OIDCValidationError,
            match="OIDC subject is missing",
        ):
            await validator.validate_id_token("fake-token")


@pytest.mark.asyncio
async def test_validate_id_token_valid_claims():
    config = make_valid_config()
    validator = GoogleOIDCValidator(config)

    validator._jwks = {
        "keys": []
    }

    claims = MockClaims(
        iss="https://accounts.google.com",
        sub="google-user-123",
        aud="client-123",
        exp=9999999999,
    )

    with patch(
        "app.auth.oidc.jwt.decode",
        return_value=claims,
    ):
        result = await validator.validate_id_token(
            "fake-token"
        )

    assert result["iss"] == "https://accounts.google.com"
    assert result["sub"] == "google-user-123"


@pytest.mark.asyncio
async def test_validate_id_token_nonce_success():
    config = make_valid_config()
    validator = GoogleOIDCValidator(config)

    validator._jwks = {
        "keys": []
    }

    claims = MockClaims(
        iss="https://accounts.google.com",
        sub="google-user-123",
        aud="client-123",
        exp=9999999999,
        nonce="nonce-123",
    )

    with patch(
        "app.auth.oidc.jwt.decode",
        return_value=claims,
    ):
        result = await validator.validate_id_token(
            "fake-token",
            expected_nonce="nonce-123",
        )

    assert result["sub"] == "google-user-123"
    assert result["nonce"] == "nonce-123"


@pytest.mark.asyncio
async def test_validate_id_token_nonce_missing():
    config = make_valid_config()
    validator = GoogleOIDCValidator(config)

    validator._jwks = {
        "keys": []
    }

    claims = MockClaims(
        iss="https://accounts.google.com",
        sub="google-user-123",
        aud="client-123",
        exp=9999999999,
    )

    with patch(
        "app.auth.oidc.jwt.decode",
        return_value=claims,
    ):
        with pytest.raises(
            OIDCValidationError,
            match="OIDC nonce validation failed",
        ):
            await validator.validate_id_token(
                "fake-token",
                expected_nonce="nonce-123",
            )


@pytest.mark.asyncio
async def test_validate_id_token_nonce_mismatch():
    config = make_valid_config()
    validator = GoogleOIDCValidator(config)

    validator._jwks = {
        "keys": []
    }

    claims = MockClaims(
        iss="https://accounts.google.com",
        sub="google-user-123",
        aud="client-123",
        exp=9999999999,
        nonce="wrong-nonce",
    )

    with patch(
        "app.auth.oidc.jwt.decode",
        return_value=claims,
    ):
        with pytest.raises(
            OIDCValidationError,
            match="OIDC nonce validation failed",
        ):
            await validator.validate_id_token(
                "fake-token",
                expected_nonce="nonce-123",
            )


@pytest.mark.asyncio
async def test_validate_id_token_no_nonce_check_when_expected_nonce_not_supplied():
    config = make_valid_config()
    validator = GoogleOIDCValidator(config)

    validator._jwks = {
        "keys": []
    }

    claims = MockClaims(
        iss="https://accounts.google.com",
        sub="google-user-123",
        aud="client-123",
        exp=9999999999,
    )

    with patch(
        "app.auth.oidc.jwt.decode",
        return_value=claims,
    ):
        result = await validator.validate_id_token(
            "fake-token"
        )

    assert result["sub"] == "google-user-123"


# -------------------------------------------------------------------
# Convenience function
# -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_validate_google_id_token():
    expected_claims = {
        "iss": "https://accounts.google.com",
        "sub": "google-user-123",
    }

    mock_validator = MagicMock()

    mock_validator.validate_id_token = AsyncMock(
        return_value=expected_claims
    )

    with patch(
        "app.auth.oidc.GoogleOIDCValidator",
        return_value=mock_validator,
    ):
        result = await validate_google_id_token(
            "fake-token",
            expected_nonce="nonce-123",
        )

    assert result == expected_claims

    mock_validator.validate_id_token.assert_awaited_once_with(
        id_token="fake-token",
        expected_nonce="nonce-123",
    )