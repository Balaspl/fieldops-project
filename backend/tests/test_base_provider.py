"""
test_base_provider.py

Unit tests for BaseAIProvider and provider schemas.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional, Sequence
from unittest.mock import MagicMock, patch
import pytest
from pydantic import ValidationError

from app.services.ai.FieldOpsAI.providers.base_provider import (
    BaseAIProvider,
    ProviderCapabilityError,
    ProviderConfigurationError,
    ProviderExecutionError,
)
from app.services.ai.FieldOpsAI.schemas.provider import (
    GenerationResult,
    ProviderConfig,
    ProviderHealth,
    UsageStats,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# --- Abstract Class / Subclass Instantiation Checks ---

def test_base_provider_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        _ = BaseAIProvider()  # type: ignore


class IncompleteProvider(BaseAIProvider):
    # Missing generate_completion, provider_name, model_name, health_check
    pass


def test_incomplete_subclass_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        _ = IncompleteProvider()  # type: ignore


class CompleteFakeProvider(BaseAIProvider):
    def __init__(self, response: str = "Fake output", healthy: bool = True) -> None:
        self.response = response
        self.healthy = healthy
        self.completion_count = 0
        self.received_messages = None

    def generate_completion(
        self,
        messages: Sequence[Dict[str, Any]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        self.completion_count += 1
        self.received_messages = messages
        return self.response

    def provider_name(self) -> str:
        return "FakeProvider"

    def model_name(self) -> str:
        return "fake-model-1"

    def health_check(self) -> bool:
        return self.healthy


def test_complete_fake_subclass_can_be_instantiated() -> None:
    provider = CompleteFakeProvider()
    assert provider.provider_name() == "FakeProvider"
    assert provider.model_name() == "fake-model-1"
    assert provider.health_check() is True


# --- Compatibility and Async generate adapter tests ---

def test_existing_generate_completion_compatibility() -> None:
    provider = CompleteFakeProvider(response="Direct response")
    res = provider.generate_completion(messages=[{"role": "user", "content": "hi"}])
    assert res == "Direct response"
    assert provider.completion_count == 1


@pytest.mark.anyio
async def test_async_generate_uses_asyncio_to_thread() -> None:
    provider = CompleteFakeProvider(response="Async response")
    with patch("asyncio.to_thread", wraps=asyncio.to_thread) as mock_to_thread:
        res = await provider.generate(messages=[{"role": "user", "content": "hello"}])
        assert res.text == "Async response"
        mock_to_thread.assert_called_once()


@pytest.mark.anyio
async def test_async_generate_returns_generation_result() -> None:
    provider = CompleteFakeProvider(response="Valid output")
    result = await provider.generate(messages=[{"role": "user", "content": "hello"}])
    assert isinstance(result, GenerationResult)
    assert result.text == "Valid output"
    assert result.provider_name == "FakeProvider"
    assert result.model_name == "fake-model-1"
    assert result.usage.latency_ms > 0.0


@pytest.mark.anyio
async def test_blank_and_non_string_provider_output_rejected() -> None:
    provider_blank = CompleteFakeProvider(response="   ")
    with pytest.raises(ProviderExecutionError, match="blank string"):
        await provider_blank.generate(messages=[{"role": "user", "content": "hello"}])

    provider_non_str = CompleteFakeProvider(response=123)  # type: ignore
    with pytest.raises(ProviderExecutionError, match="not a string"):
        await provider_non_str.generate(messages=[{"role": "user", "content": "hello"}])


# --- Health Status adapter checks ---

@pytest.mark.anyio
async def test_get_health_maps_true_to_healthy() -> None:
    provider = CompleteFakeProvider(healthy=True)
    health = await provider.get_health()
    assert health == ProviderHealth.HEALTHY


@pytest.mark.anyio
async def test_get_health_maps_false_to_unhealthy() -> None:
    provider = CompleteFakeProvider(healthy=False)
    health = await provider.get_health()
    assert health == ProviderHealth.UNHEALTHY


# --- Base Default implementations ---

def test_get_models_returns_configured_model() -> None:
    provider = CompleteFakeProvider()
    assert provider.get_models() == ["fake-model-1"]


def test_default_get_usage_returns_validated_zero_usage() -> None:
    provider = CompleteFakeProvider()
    usage = provider.get_usage()
    assert isinstance(usage, UsageStats)
    assert usage.prompt_tokens == 0
    assert usage.completion_tokens == 0
    assert usage.total_tokens == 0
    assert usage.latency_ms == 0.0


@pytest.mark.anyio
async def test_embed_raises_provider_capability_error() -> None:
    provider = CompleteFakeProvider()
    with pytest.raises(ProviderCapabilityError, match="Embeddings are not supported"):
        await provider.embed(["hello"])


# --- ProviderConfig validation checks ---

def test_valid_provider_config_accepted() -> None:
    config = ProviderConfig(
        provider_name="Groq",
        model_name="llama-3.3-70b",
        api_key_env="GROQ_API_KEY",
        timeout_seconds=30.0,
        max_tokens=4096,
        temperature=0.0,
        max_retries=3,
    )
    assert config.provider_name == "Groq"


def test_blank_provider_model_api_key_env_rejected() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(
            provider_name="  ",
            model_name="llama-3.3",
            api_key_env="GROQ_KEY",
            timeout_seconds=30.0,
            max_tokens=100,
            temperature=0.0,
            max_retries=1,
        )

    with pytest.raises(ValidationError):
        ProviderConfig(
            provider_name="Groq",
            model_name="",
            api_key_env="GROQ_KEY",
            timeout_seconds=30.0,
            max_tokens=100,
            temperature=0.0,
            max_retries=1,
        )

    with pytest.raises(ValidationError):
        ProviderConfig(
            provider_name="Groq",
            model_name="llama-3.3",
            api_key_env="  ",
            timeout_seconds=30.0,
            max_tokens=100,
            temperature=0.0,
            max_retries=1,
        )


def test_invalid_timeout_rejected() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(
            provider_name="Groq",
            model_name="llama-3.3",
            api_key_env="KEY",
            timeout_seconds=0.0,
            max_tokens=100,
            temperature=0.0,
            max_retries=1,
        )


def test_invalid_max_tokens_rejected() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(
            provider_name="Groq",
            model_name="llama-3.3",
            api_key_env="KEY",
            timeout_seconds=10.0,
            max_tokens=-5,
            temperature=0.0,
            max_retries=1,
        )


def test_temperature_below_zero_and_above_one_rejected() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(
            provider_name="Groq",
            model_name="llama-3.3",
            api_key_env="KEY",
            timeout_seconds=10.0,
            max_tokens=100,
            temperature=-0.1,
            max_retries=1,
        )

    with pytest.raises(ValidationError):
        ProviderConfig(
            provider_name="Groq",
            model_name="llama-3.3",
            api_key_env="KEY",
            timeout_seconds=10.0,
            max_tokens=100,
            temperature=1.1,
            max_retries=1,
        )


def test_negative_max_retries_rejected() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(
            provider_name="Groq",
            model_name="llama-3.3",
            api_key_env="KEY",
            timeout_seconds=10.0,
            max_tokens=100,
            temperature=0.0,
            max_retries=-1,
        )


def test_actual_secrets_not_part_of_provider_config() -> None:
    _ = ProviderConfig(
        provider_name="Groq",
        model_name="llama-3.3",
        api_key_env="GROQ_API_KEY",
        timeout_seconds=10.0,
        max_tokens=100,
        temperature=0.0,
        max_retries=1,
    )

    with pytest.raises(ValidationError):
        ProviderConfig(
            provider_name="Groq",
            model_name="llama-3.3",
            api_key_env="gsk_real_key_goes_here_and_evaluated",
            timeout_seconds=10.0,
            max_tokens=100,
            temperature=0.0,
            max_retries=1,
        )


# --- UsageStats & GenerationResult validation checks ---

def test_usage_stats_rejects_negative_fields() -> None:
    with pytest.raises(ValidationError):
        UsageStats(
            prompt_tokens=-1,
            completion_tokens=5,
            total_tokens=4,
            request_count=1,
            latency_ms=10.0,
            cost_usd=0.01,
        )


def test_usage_stats_rejects_inconsistent_total_tokens() -> None:
    with pytest.raises(ValidationError):
        UsageStats(
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=35,
            request_count=1,
            latency_ms=10.0,
            cost_usd=0.01,
        )


def test_generation_result_rejects_blank_text() -> None:
    usage = UsageStats(
        prompt_tokens=10,
        completion_tokens=20,
        total_tokens=30,
        request_count=1,
        latency_ms=10.0,
        cost_usd=0.01,
    )
    with pytest.raises(ValidationError):
        GenerationResult(
            text="   ",
            provider_name="Groq",
            model_name="llama-3.3",
            usage=usage,
        )


# --- Retry Classification Checks ---

@pytest.mark.anyio
async def test_retry_classification_errors() -> None:
    from app.services.ai.FieldOpsAI.providers.base_provider import is_retryable_provider_error

    # 1. HTTP 400 is non-retryable
    class Error400(Exception):
        status_code = 400
    assert is_retryable_provider_error(Error400("Bad Request")) is False

    # 2. HTTP 401 is non-retryable
    class Error401(Exception):
        status_code = 401
    assert is_retryable_provider_error(Error401("Unauthorized")) is False

    # 3. HTTP 403 is non-retryable
    class Error403(Exception):
        status_code = 403
    assert is_retryable_provider_error(Error403("Forbidden")) is False

    # 4. HTTP 429 is retryable
    class Error429(Exception):
        status_code = 429
    assert is_retryable_provider_error(Error429("Rate limit exceeded")) is True

    # 5. HTTP 500 is retryable
    class Error500(Exception):
        status_code = 500
    assert is_retryable_provider_error(Error500("Internal Server Error")) is True

    # 6. HTTP 599 is retryable
    class Error599(Exception):
        status_code = 599
    assert is_retryable_provider_error(Error599("Gateway Timeout")) is True

    # 7. timeout is retryable
    assert is_retryable_provider_error(TimeoutError("Operation timed out")) is True

    # 8. connection failure is retryable
    assert is_retryable_provider_error(ConnectionError("Connection reset by peer")) is True

    # 9. unknown exception is non-retryable
    assert is_retryable_provider_error(RuntimeError("Unknown execution exception")) is False

    # 10. ProviderConfigurationError is non-retryable
    assert is_retryable_provider_error(ProviderConfigurationError("Config missing")) is False

    # 11. ProviderCapabilityError is non-retryable
    assert is_retryable_provider_error(ProviderCapabilityError("Embedding unsupported")) is False

    # 12. Pydantic ValidationError is non-retryable
    with pytest.raises(ValidationError) as validation_info:
        ProviderConfig(
            provider_name="",
            model_name="",
            api_key_env="invalid",
            timeout_seconds=-1,
            max_tokens=-1,
            temperature=-1,
            max_retries=-1,
        )
    assert is_retryable_provider_error(validation_info.value) is False

    # 13. Deterministic response nested status code check
    class NestedResponse:
        def __init__(self, code: int) -> None:
            self.status_code = code

    class NestedResponseError(Exception):
        def __init__(self, code: int) -> None:
            self.response = NestedResponse(code)

    assert is_retryable_provider_error(NestedResponseError(429)) is True
    assert is_retryable_provider_error(NestedResponseError(400)) is False

    # 14. Existing ProviderExecutionError preserves status and retryability
    pe_retry = ProviderExecutionError("Failed execution", status_code=503, is_retryable=True)
    assert is_retryable_provider_error(pe_retry) is True
    assert pe_retry.status_code == 503
    assert pe_retry.is_retryable is True

    pe_non_retry = ProviderExecutionError("Failed execution", status_code=400, is_retryable=False)
    assert is_retryable_provider_error(pe_non_retry) is False
    assert pe_non_retry.status_code == 400
    assert pe_non_retry.is_retryable is False


@pytest.mark.anyio
async def test_exception_secrecy_and_invocation_count(caplog: pytest.LogCaptureFixture) -> None:
    secret_prompt = "CONFIDENTIAL: API_KEY=gsk_secret_123, CUSTOMER=JohnDoe"
    messages = [{"role": "user", "content": secret_prompt}]
    
    provider = CompleteFakeProvider()
    original_err_msg = f"Failed Groq call with API key gsk_secret_123. Prompt context={secret_prompt}"
    provider.generate_completion = MagicMock(side_effect=RuntimeError(original_err_msg))

    caplog.clear()
    with pytest.raises(ProviderExecutionError) as exc_info:
        await provider.generate(messages=messages)
    
    # Verify provider exception text is absent from the public raised error
    assert "gsk_secret_123" not in str(exc_info.value)
    assert secret_prompt not in str(exc_info.value)
    assert original_err_msg not in str(exc_info.value)
    assert str(exc_info.value) == "AI provider execution failed."

    # Verify prompt content and raw secrets are absent from logs
    log_text = caplog.text
    assert "gsk_secret_123" not in log_text
    assert secret_prompt not in log_text
    assert original_err_msg not in log_text
    assert caplog.records[-1].exception_type == "RuntimeError"
    assert caplog.records[-1].provider == "FakeProvider"
    assert caplog.records[-1].retryable is False

    # Verify generate_completion is invoked exactly once
    provider.generate_completion.assert_called_once_with(
        messages=messages,
        temperature=None,
        max_tokens=None,
    )


@pytest.mark.anyio
async def test_get_health_handles_exception() -> None:
    provider = CompleteFakeProvider()
    provider.health_check = MagicMock(side_effect=RuntimeError("Health check crashed"))
    health = await provider.get_health()
    assert health == ProviderHealth.UNHEALTHY


def test_invalid_api_key_env_name_format_rejected() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(
            provider_name="Groq",
            model_name="llama-3.3",
            api_key_env="invalid-name-with-dashes",
            timeout_seconds=10.0,
            max_tokens=100,
            temperature=0.0,
            max_retries=1,
        )


def test_abstract_methods_raise_not_implemented_error() -> None:
    with pytest.raises(NotImplementedError):
        BaseAIProvider.generate_completion(None, [])  # type: ignore
    with pytest.raises(NotImplementedError):
        BaseAIProvider.provider_name(None)  # type: ignore
    with pytest.raises(NotImplementedError):
        BaseAIProvider.model_name(None)  # type: ignore
    with pytest.raises(NotImplementedError):
        BaseAIProvider.health_check(None)  # type: ignore


@pytest.mark.anyio
async def test_generate_preserves_existing_provider_execution_error() -> None:
    provider = CompleteFakeProvider()
    existing_error = ProviderExecutionError("Inner error", status_code=500, is_retryable=True)
    provider.generate_completion = MagicMock(side_effect=existing_error)

    with pytest.raises(ProviderExecutionError) as exc_info:
        await provider.generate(messages=[])
    
    assert exc_info.value.status_code == 500
    assert exc_info.value.is_retryable is True


@pytest.mark.anyio
async def test_generate_handles_nested_response_error() -> None:
    class NestedResponse:
        def __init__(self, code: int) -> None:
            self.status_code = code

    class NestedResponseError(Exception):
        def __init__(self, code: int) -> None:
            self.response = NestedResponse(code)

    provider = CompleteFakeProvider()
    provider.generate_completion = MagicMock(side_effect=NestedResponseError(429))

    with pytest.raises(ProviderExecutionError) as exc_info:
        await provider.generate(messages=[])
    
    assert exc_info.value.status_code == 429
    assert exc_info.value.is_retryable is True



