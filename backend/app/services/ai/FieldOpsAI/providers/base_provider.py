"""
base_provider.py

Purpose
-------
Defines the common interface that every AI provider
(Groq, OpenAI, Anthropic, Ollama, etc.) must implement.
"""

from __future__ import annotations

from pydantic import ValidationError
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Sequence

from app.services.ai.FieldOpsAI.schemas.provider import (
    GenerationResult,
    ProviderHealth,
    UsageStats,
)

logger = logging.getLogger(__name__)


class ProviderError(Exception):
    """
    Base exception for all provider errors.
    """
    pass


class ProviderExecutionError(ProviderError):
    """
    Raised when AI execution fails or returns an invalid response.
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        is_retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.is_retryable = is_retryable


class ProviderCapabilityError(ProviderError):
    """
    Raised when a requested capability is not supported by the provider.
    """
    pass


class ProviderConfigurationError(ProviderError):
    """
    Raised when provider configuration is invalid or missing.
    """
    pass


def is_retryable_provider_error(
    error: BaseException,
) -> bool:
    """
    Determine if a provider error is retryable based on defined classification rules.
    """
    

    # ProviderConfigurationError, ProviderCapabilityError, ValidationError are non-retryable
    if isinstance(error, (ProviderConfigurationError, ProviderCapabilityError, ValidationError)):
        return False

    # ProviderExecutionError is retryable if is_retryable is True
    if isinstance(error, ProviderExecutionError):
        return error.is_retryable

    # TimeoutError and ConnectionError are retryable
    if isinstance(error, (TimeoutError, ConnectionError)):
        return True

    # Obtain HTTP status code deterministically
    status_code = getattr(error, "status_code", None)
    if status_code is None:
        response = getattr(error, "response", None)
        if response is not None:
            status_code = getattr(response, "status_code", None)

    if isinstance(status_code, int):
        if status_code == 429 or (500 <= status_code <= 599):
            return True
        if status_code in {400, 401, 403}:
            return False

    return False


class BaseAIProvider(ABC):
    """
    Abstract interface implemented by every AI provider.
    """

    @abstractmethod
    def generate_completion(
        self,
        messages: Sequence[Dict[str, Any]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Generate a chat completion.

        Parameters
        ----------
        messages
            Conversation messages in OpenAI-compatible format.
        temperature
            Optional override for model creativity.
        max_tokens
            Optional maximum response length.

        Returns
        -------
        str
            Raw AI response.
        """
        raise NotImplementedError

    @abstractmethod
    def provider_name(self) -> str:
        """
        Return the provider name.
        """
        raise NotImplementedError

    @abstractmethod
    def model_name(self) -> str:
        """
        Return the configured model name.
        """
        raise NotImplementedError

    @abstractmethod
    def health_check(self) -> bool:
        """
        Verify that the provider is reachable.
        """
        raise NotImplementedError

    def generate_result(
        self,
        messages: Sequence[Dict[str, Any]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> GenerationResult:
        """
        Synchronously generate a completion and return a typed GenerationResult.

        Default implementation calls generate_completion(), measures latency,
        validates response text, and attaches usage stats.
        """
        import time

        start_time = time.perf_counter()
        try:
            response_text = self.generate_completion(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            if isinstance(exc, ProviderExecutionError):
                status_code = exc.status_code
                is_retryable = exc.is_retryable
            else:
                status_code = getattr(exc, "status_code", None)
                if status_code is None:
                    response = getattr(exc, "response", None)
                    if response is not None:
                        status_code = getattr(response, "status_code", None)

                if not isinstance(status_code, int):
                    status_code = None

                is_retryable = is_retryable_provider_error(exc)

            # Keep the original provider exception private, but preserve
            # useful sanitized diagnostics before translating it into the
            # stable public ProviderExecutionError contract.
            try:
                provider_label = self.provider_name()
            except Exception:
                provider_label = type(self).__name__
            logger.warning(
                "AI provider execution failed during generate call",
                extra={
                    "provider": provider_label,
                    "exception_type": type(exc).__name__,
                    "status_code": status_code,
                    "retryable": is_retryable,
                },
            )

            raise ProviderExecutionError(
                "AI provider execution failed.",
                status_code=status_code,
                is_retryable=is_retryable,
            ) from None

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        if not isinstance(response_text, str):
            raise ProviderExecutionError("Provider output is not a string.")

        normalized_text = response_text.strip()
        if not normalized_text:
            raise ProviderExecutionError("Provider output is a blank string.")

        usage = self.get_usage()
        usage_data = usage.model_dump()
        usage_data["latency_ms"] = elapsed_ms
        validated_usage = UsageStats(**usage_data)

        return GenerationResult(
            text=normalized_text,
            provider_name=self.provider_name(),
            model_name=self.model_name(),
            usage=validated_usage,
        )

    # Backward-compatible new asynchronous adapter methods

    async def generate(
        self,
        messages: Sequence[Dict[str, Any]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> GenerationResult:
        """
        Asynchronously generate a chat completion.

        Delegates to generate_result() through asyncio.to_thread().
        """
        import asyncio

        return await asyncio.to_thread(
            self.generate_result,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def get_health(self) -> ProviderHealth:
        """
        Asynchronously check provider health using health_check.
        """
        import asyncio

        try:
            is_healthy = await asyncio.to_thread(self.health_check)
            return ProviderHealth.HEALTHY if is_healthy else ProviderHealth.UNHEALTHY
        except Exception:
            return ProviderHealth.UNHEALTHY

    def get_models(self) -> list[str]:
        """
        Return the configured model as a single-item list.
        """
        return [self.model_name()]

    def get_usage(self) -> UsageStats:
        """
        Return validated zero usage stats.
        """
        return UsageStats(
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            request_count=0,
            latency_ms=0.0,
            cost_usd=0.0,
        )

    async def embed(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        """
        Raise a capability error as embeddings are unsupported.
        """
        raise ProviderCapabilityError("Embeddings are not supported by this provider.")
