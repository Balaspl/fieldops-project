"""
groq_provider.py

Concrete implementation of BaseAIProvider using the Groq API.
Hardened with 5-second logical deadline, 429 retries with backoff, thread-safe usage tracking,
and typed error mapping.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from groq import Groq, APIConnectionError, APITimeoutError

from app.services.ai.FieldOpsAI.config.config_loader import ConfigLoader
from app.services.ai.FieldOpsAI.providers.base_provider import (
    BaseAIProvider,
    ProviderConfigurationError,
    ProviderExecutionError,
    is_retryable_provider_error,
)
from app.services.ai.FieldOpsAI.schemas.provider import (
    GenerationResult,
    UsageStats,
)


logger = logging.getLogger(__name__)

ALLOWED_MODEL = "openai/gpt-oss-120b"

# gpt-oss is a reasoning model. Short customer messages do not need deep
# reasoning, and low effort leaves more of max_tokens for the actual answer.
ALLOWED_REASONING_EFFORTS = {"low", "medium", "high"}
DEFAULT_REASONING_EFFORT = "low"


class GroqProvider(BaseAIProvider):
    """
    Hardened Groq implementation of the AI provider interface.
    """

    def __init__(
        self,
        client: Optional[Any] = None,
        config: Optional[ConfigLoader | Any] = None,
        clock: Optional[Callable[[], float] | Any] = None,
        sleep_fn: Optional[Callable[[float], None]] = None,
    ) -> None:
        """
        Initialize the Groq provider.
        Supports dependency injection for client, config, clock, and sleep_fn.
        """
        self.config = config if config is not None else ConfigLoader()
        self._clock = clock
        self._sleep_fn = sleep_fn if sleep_fn is not None else time.sleep

        # Validate configured model
        configured_model = getattr(self.config, "model_name", ALLOWED_MODEL)
        if configured_model and configured_model != ALLOWED_MODEL:
            raise ProviderConfigurationError(f"Unsupported model configuration: {configured_model}")

        self.model = ALLOWED_MODEL
        self.default_temperature = getattr(self.config, "temperature", 0.0)
        self.default_max_tokens = getattr(self.config, "max_tokens", 4096)

        # Optional config override: config.reasoning_effort = "low" | "medium" | "high"
        configured_effort = getattr(self.config, "reasoning_effort", DEFAULT_REASONING_EFFORT)
        if (
            isinstance(configured_effort, str)
            and configured_effort.strip().lower() in ALLOWED_REASONING_EFFORTS
        ):
            self.reasoning_effort = configured_effort.strip().lower()
        else:
            self.reasoning_effort = DEFAULT_REASONING_EFFORT

        if client is not None:
            self.client = client
        else:
            api_key = os.getenv("GROQ_API_KEY")
            if not api_key:
                raise ProviderConfigurationError("GROQ_API_KEY environment variable was not found.")

            self.client = Groq(
                api_key=api_key,
                max_retries=0,
                timeout=5.0,
            )

        # Thread-safe cumulative usage stats
        self._lock = threading.Lock()
        self._cumulative_prompt_tokens = 0
        self._cumulative_completion_tokens = 0
        self._cumulative_total_tokens = 0
        self._cumulative_request_count = 0

    def _now(self) -> float:
        if self._clock is None:
            return time.monotonic()

        if callable(self._clock):
            value = self._clock()

            if isinstance(value, (int, float)):
                return float(value)

        raise TypeError(
            "clock must be a callable returning a number."
        )

    def _validate_inputs(
        self,
        messages: Sequence[Dict[str, Any]],
        temperature: Optional[float],
        max_tokens: Optional[int],
    ) -> tuple[float, int]:
        if not isinstance(messages, Sequence) or isinstance(messages, (str, bytes)) or len(messages) == 0:
            raise ValueError("messages must be a non-empty sequence.")

        for msg in messages:
            if not isinstance(msg, Mapping):
                raise ValueError("each message must be a mapping.")
            role = msg.get("role")
            if not isinstance(role, str) or not role.strip():
                raise ValueError("message role must be a non-blank string.")
            content = msg.get("content")
            if not isinstance(content, str):
                raise ValueError("message content must be a string.")

        eff_temp = temperature if temperature is not None else self.default_temperature
        if not (0.0 <= eff_temp <= 1.0):
            raise ValueError("temperature must be between 0.0 and 1.0.")

        eff_max_tokens = max_tokens if max_tokens is not None else self.default_max_tokens
        if eff_max_tokens <= 0:
            raise ValueError("max_tokens must be positive.")
        if eff_max_tokens > self.default_max_tokens:
            raise ValueError("max_tokens exceeds configured maximum.")

        return eff_temp, eff_max_tokens

    def _log_empty_response(
        self,
        *,
        response: Any,
        choice: Any,
        message: Any,
        content: Any,
        eff_max_tokens: int,
    ) -> None:
        """
        Log safe diagnostics for an empty provider response.

        Only flags, counts and the finish reason are logged. The prompt,
        the response text and the reasoning text are never logged.
        """
        usage_dbg = getattr(response, "usage", None)

        logger.warning(
            "GROQ_EMPTY_CONTENT finish_reason=%s content_is_none=%s "
            "content_type=%s has_reasoning=%s has_tool_calls=%s "
            "has_refusal=%s completion_tokens=%s max_tokens=%s",
            getattr(choice, "finish_reason", None),
            content is None,
            type(content).__name__,
            bool(getattr(message, "reasoning", None)),
            bool(getattr(message, "tool_calls", None)),
            getattr(message, "refusal", None) is not None,
            getattr(usage_dbg, "completion_tokens", None),
            eff_max_tokens,
        )

    def generate_result(
        self,
        messages: Sequence[Dict[str, Any]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> GenerationResult:
        eff_temp, eff_max_tokens = self._validate_inputs(messages, temperature, max_tokens)

        overall_deadline = 5.0
        start_time = self._now()
        backoff_delays = [1.0, 2.0]
        attempt = 0
        total_http_attempts = 0

        while True:
            elapsed = (
                self._now()
                - start_time
            )

            remaining_time = (
                overall_deadline
                - elapsed
            )

            if remaining_time <= 0:
                with self._lock:
                    self._cumulative_request_count += (
                        total_http_attempts
                    )

                logger.warning(
                    "Groq provider request execution timed out."
                )

                raise ProviderExecutionError(
                    "AI provider execution timed out.",
                    status_code=None,
                    is_retryable=True,
                ) from None

            # These lines must be OUTSIDE the timeout block.
            attempt += 1
            total_http_attempts += 1

            try:
                response = (
                    self.client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        temperature=eff_temp,
                        max_tokens=eff_max_tokens,
                        timeout=min(
                            remaining_time,
                            overall_deadline,
                        ),
                        # extra_body works on any version of the groq SDK.
                        extra_body={
                            "reasoning_effort": self.reasoning_effort,
                        },
                    )
                )

                call_elapsed_ms = (self._now() - start_time) * 1000.0

                choices = getattr(response, "choices", None)
                if not choices:
                    usage_dbg = getattr(response, "usage", None)
                    logger.warning(
                        "GROQ_EMPTY_CHOICES completion_tokens=%s max_tokens=%s",
                        getattr(usage_dbg, "completion_tokens", None),
                        eff_max_tokens,
                    )

                    raise ProviderExecutionError(
                        "AI provider returned an empty or invalid response.",
                        status_code=None,
                        is_retryable=False,
                    ) from None

                choice = choices[0]
                message = getattr(choice, "message", None)
                content = getattr(message, "content", None) if message else None

                if (
                    content is None
                    or not isinstance(content, str)
                    or not content.strip()
                ):
                    self._log_empty_response(
                        response=response,
                        choice=choice,
                        message=message,
                        content=content,
                        eff_max_tokens=eff_max_tokens,
                    )

                    raise ProviderExecutionError(
                        "AI provider returned an empty or invalid response.",
                        status_code=None,
                        is_retryable=False,
                    ) from None

                normalized_text = content.strip()

                usage_obj = getattr(
                    response,
                    "usage",
                    None,
                )

                raw_prompt_tokens = (
                    getattr(
                        usage_obj,
                        "prompt_tokens",
                        0,
                    )
                    if usage_obj
                    else 0
                )

                raw_completion_tokens = (
                    getattr(
                        usage_obj,
                        "completion_tokens",
                        0,
                    )
                    if usage_obj
                    else 0
                )

                try:
                    prompt_tokens = max(
                        int(raw_prompt_tokens or 0),
                        0,
                    )

                    completion_tokens = max(
                        int(raw_completion_tokens or 0),
                        0,
                    )

                except (TypeError, ValueError):
                    raise ProviderExecutionError(
                        "AI provider returned invalid usage data.",
                        status_code=None,
                        is_retryable=False,
                    ) from None

                # Always calculate this ourselves.
                # Do not trust an inconsistent provider total.
                total_tokens = (
                    prompt_tokens
                    + completion_tokens
                )

                call_usage = UsageStats(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    request_count=total_http_attempts,
                    latency_ms=call_elapsed_ms,
                    cost_usd=0.0,
                )

                # Update cumulative values only after UsageStats validates.
                with self._lock:
                    self._cumulative_prompt_tokens += (
                        prompt_tokens
                    )

                    self._cumulative_completion_tokens += (
                        completion_tokens
                    )

                    self._cumulative_total_tokens += (
                        total_tokens
                    )

                    self._cumulative_request_count += (
                        total_http_attempts
                    )

                return GenerationResult(
                    text=normalized_text,
                    provider_name=self.provider_name(),
                    model_name=self.model_name(),
                    usage=call_usage,
                )

            except ProviderExecutionError:
                with self._lock:
                    self._cumulative_request_count += total_http_attempts
                raise

            except Exception as exc:
                status_code = getattr(exc, "status_code", None)
                if status_code is None:
                    resp = getattr(exc, "response", None)
                    if resp is not None:
                        status_code = getattr(resp, "status_code", None)

                if status_code == 429 and attempt <= len(backoff_delays):
                    delay = backoff_delays[attempt - 1]
                    rem = overall_deadline - (self._now() - start_time)
                    if rem > delay:
                        logger.warning("Groq rate limit 429 encountered; retrying.")
                        self._sleep_fn(delay)
                        continue

                with self._lock:
                    self._cumulative_request_count += total_http_attempts

                is_retryable = (
                    status_code == 429
                    or (isinstance(status_code, int) and 500 <= status_code <= 599)
                    or isinstance(
                        exc,
                        (
                            TimeoutError,
                            ConnectionError,
                            APITimeoutError,
                            APIConnectionError,
                        ),
                    )
                    or is_retryable_provider_error(exc)
                )

                if status_code in {400, 401, 403}:
                    is_retryable = False

                # Log only safe diagnostics. Do not log the prompt, response body,
                # API key, or raw exception message because these may contain secrets.
                logger.error(
                    "Groq provider request execution failed.",
                    extra={
                        "provider": "Groq",
                        "model": self.model,
                        "error_type": type(exc).__name__,
                        "status_code": (
                            status_code
                            if isinstance(status_code, int)
                            else None
                        ),
                        "is_retryable": is_retryable,
                        "attempt": attempt,
                        "elapsed_ms": round(
                            (self._now() - start_time) * 1000.0,
                            2,
                        ),
                    },
                )

                if status_code == 401:
                    msg = "AI provider request unauthorized."
                elif status_code == 429:
                    msg = "AI provider rate limit exceeded."
                else:
                    msg = "AI provider execution failed."

                # Preserve the original exception as the cause for internal
                # debugging while keeping the public error message sanitized.
                raise ProviderExecutionError(
                    msg,
                    status_code=status_code if isinstance(status_code, int) else None,
                    is_retryable=is_retryable,
                ) from exc

    def generate_completion(
        self,
        messages: Sequence[Dict[str, Any]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        res = self.generate_result(messages=messages, temperature=temperature, max_tokens=max_tokens)
        return res.text

    def provider_name(self) -> str:
        return "Groq"

    def model_name(self) -> str:
        return self.model

    def get_models(self) -> List[str]:
        """
        Return the allowed Groq model only when it is
        available from the models endpoint.
        """

        try:
            response = self.client.models.list()

            data = getattr(
                response,
                "data",
                [],
            )

            available_models: list[str] = []

            for model in data:
                model_id = getattr(
                    model,
                    "id",
                    None,
                )

                if isinstance(model_id, str):
                    available_models.append(
                        model_id
                    )

            if ALLOWED_MODEL in available_models:
                return [ALLOWED_MODEL]

            return []

        except Exception:
            logger.warning(
                "Groq models endpoint request failed."
            )

            return []

    def health_check(self) -> bool:
        """
        Return True only when the allowed model is
        available from Groq.
        """

        return ALLOWED_MODEL in self.get_models()

    def get_usage(self) -> UsageStats:
        """
        Return a thread-safe cumulative usage snapshot.
        """

        with self._lock:
            return UsageStats(
                prompt_tokens=(
                    self._cumulative_prompt_tokens
                ),
                completion_tokens=(
                    self._cumulative_completion_tokens
                ),
                total_tokens=(
                    self._cumulative_total_tokens
                ),
                request_count=(
                    self._cumulative_request_count
                ),
                latency_ms=0.0,
                cost_usd=0.0,
            )