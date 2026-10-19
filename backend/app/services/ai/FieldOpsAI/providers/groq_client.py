"""
groq_client.py

Provider-execution client for FieldOps Commander AI.

Responsibilities
----------------
- Execute AI requests using the configured provider.
- Return the raw provider response.
- Translate provider failures into a safe application error.

The client never:
- Builds prompts
- Renders Jinja2 templates
- Selects fallback communication
- Restores placeholders
- Parses structured responses
- Updates the database
- Sends notifications

Fallback selection belongs to the business workflow, such as
CommunicationService.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.services.ai.FieldOpsAI.providers.base_provider import (
    BaseAIProvider,
    ProviderExecutionError,
)
from app.services.ai.FieldOpsAI.providers.provider_factory import (
    ProviderFactory,
)
from app.services.ai.FieldOpsAI.schemas.ai_task import AITask
from app.services.ai.FieldOpsAI.schemas.provider import (
    GenerationResult,
    UsageStats,
)

logger = logging.getLogger(__name__)


class AIProviderExecutionError(ProviderExecutionError):
    """Safe provider error preserving retry and HTTP status metadata."""


class GroqClient:
    """Execute requests through the configured AI provider."""

    def __init__(
        self,
        *,
        provider: BaseAIProvider | None = None,
    ) -> None:
        self.provider = (
            provider
            if provider is not None
            else ProviderFactory.create_provider()
        )

    def generate_result(
        self,
        task: AITask,
        messages: List[Dict[str, Any]],
        context: Dict[str, Any],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> GenerationResult:
        """Execute one provider request and return a typed result."""
        if not isinstance(task, AITask):
            raise TypeError("task must be an AITask.")
        if not isinstance(messages, list) or not messages:
            raise ValueError("messages must be a non-empty list.")
        if not isinstance(context, dict):
            raise TypeError("context must be a dictionary.")

        # Context is already sanitized by AIOrchestrator. Do not log prompts,
        # context, raw provider response, API keys, or exception messages.
        _ = context
        provider_name = self._safe_provider_name()

        logger.info(
            "Executing AI provider request. Provider=%s Task=%s",
            provider_name,
            task.value,
        )

        try:
            generate_result = getattr(self.provider, "generate_result", None)
            if callable(generate_result):
                provider_kwargs = {
                    "messages": messages,
                    "temperature": temperature,
                }
                # GroqProvider supports max_tokens. Do not silently drop the
                # limit: the orchestrator reserved this amount in its budget.
                if max_tokens is not None:
                    provider_kwargs["max_tokens"] = max_tokens

                result = generate_result(**provider_kwargs)
                if not isinstance(getattr(result, "text", None), str):
                    raise AIProviderExecutionError(
                        "AI provider returned an invalid response.",
                        status_code=None,
                        is_retryable=False,
                    )
                normalized_text = result.text.strip()
                if not normalized_text:
                    raise AIProviderExecutionError(
                        "AI provider returned an empty response.",
                        status_code=None,
                        is_retryable=False,
                    )

                logger.info(
                    "AI provider request completed. Provider=%s Task=%s",
                    provider_name,
                    task.value,
                )
                return GenerationResult(
                    text=normalized_text,
                    provider_name=result.provider_name,
                    model_name=result.model_name,
                    usage=result.usage,
                )

            generate_completion = getattr(
                self.provider, "generate_completion", None
            )
            if not callable(generate_completion):
                raise AIProviderExecutionError(
                    "AI provider has no supported generation method.",
                    status_code=None,
                    is_retryable=False,
                )

            raw_text = generate_completion(messages=messages)
            if not isinstance(raw_text, str):
                raise AIProviderExecutionError(
                    "AI provider returned an invalid response.",
                    status_code=None,
                    is_retryable=False,
                )
            normalized_text = raw_text.strip()
            if not normalized_text:
                raise AIProviderExecutionError(
                    "AI provider returned an empty response.",
                    status_code=None,
                    is_retryable=False,
                )

            provider_name_value = (
                self.provider.provider_name()
                if callable(getattr(self.provider, "provider_name", None))
                else "groq"
            )
            model_name_value = (
                self.provider.model_name()
                if callable(getattr(self.provider, "model_name", None))
                else "openai/gpt-oss-120b"
            )
            get_usage = getattr(self.provider, "get_usage", None)
            usage = (
                get_usage()
                if callable(get_usage)
                else UsageStats(
                    prompt_tokens=0,
                    completion_tokens=0,
                    total_tokens=0,
                    request_count=1,
                    latency_ms=0.0,
                    cost_usd=0.0,
                )
            )
            return GenerationResult(
                text=normalized_text,
                provider_name=provider_name_value,
                model_name=model_name_value,
                usage=usage,
            )

        except AIProviderExecutionError:
            raise
        except ProviderExecutionError as provider_error:
            logger.warning(
                "AI provider execution failed.",
                extra={
                    "provider": provider_name,
                    "task": task.value,
                    "error_type": type(provider_error).__name__,
                    "status_code": provider_error.status_code,
                    "is_retryable": provider_error.is_retryable,
                },
            )
            # Preserve the cause for internal diagnostics. The exception's
            # public message remains safe and does not expose provider details.
            raise AIProviderExecutionError(
                "AI provider execution failed.",
                status_code=provider_error.status_code,
                is_retryable=provider_error.is_retryable,
            ) from provider_error
        except Exception as exc:
            status_code = getattr(exc, "status_code", None)
            is_retryable = getattr(exc, "is_retryable", False)
            if not isinstance(is_retryable, bool):
                is_retryable = False
            if isinstance(status_code, bool) or not isinstance(status_code, int):
                status_code = None

            logger.warning(
                "Unexpected AI provider exception.",
                extra={
                    "provider": provider_name,
                    "task": task.value,
                    "error_type": type(exc).__name__,
                    "status_code": status_code,
                    "is_retryable": is_retryable,
                },
            )
            raise AIProviderExecutionError(
                "AI provider execution failed.",
                status_code=status_code,
                is_retryable=is_retryable,
            ) from exc

    def generate(
        self,
        task: AITask,
        messages: List[Dict[str, Any]],
        context: Dict[str, Any],
    ) -> str:
        """Compatibility wrapper returning the generated text."""
        return self.generate_result(
            task=task,
            messages=messages,
            context=context,
        ).text

    def _safe_provider_name(self) -> str:
        """Return a safe provider name for operational logging."""
        try:
            provider_name = self.provider.provider_name()
        except Exception:
            return "unknown"
        if not isinstance(provider_name, str):
            return "unknown"
        normalized_name = provider_name.strip()
        return normalized_name or "unknown"
