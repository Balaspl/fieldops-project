"""
orchestrator.py

Central orchestration layer for the FieldOps Commander AI.

Responsibilities
----------------
- Build the complete system prompt.
- Load the task-specific prompt.
- Sanitize PII before external AI provider calls.
- Validate that no detectable PII remains in user prompts.
- Execute the provider failover chain.
- Apply per-provider circuit breaker and token budget handling.
- Read and write sanitized provider responses through ProviderCache.
- Restore permitted placeholder values locally.
- Parse and validate structured AI responses.

Privacy rule
------------
The original context must never be passed to Groq or another
external AI provider. Only sanitized context and prompts may
cross the provider boundary.
"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type

import asyncio
from dataclasses import dataclass, field
from uuid import uuid4

from app.services.ai.FieldOpsAI.runtime.agent_registry import AgentRegistry
from app.services.ai.FieldOpsAI.runtime.agent_bus import AgentBus
from app.services.ai.FieldOpsAI.runtime.engine import AIRuntimeEngine, TaskSpec, TaskStatus
from app.services.ai.FieldOpsAI.config.agent_config_manager import AgentConfigManager

from pydantic import BaseModel

from app.redis_client import get_redis_client
from app.services.ai.FieldOpsAI.config.config_loader import (
    ConfigLoader,
)
from app.services.ai.FieldOpsAI.providers.base_provider import (
    BaseAIProvider,
    ProviderConfigurationError,
    ProviderExecutionError,
)
from app.services.ai.FieldOpsAI.providers.budget import (
    BudgetExceededError,
    BudgetInfrastructureError,
    SyncTokenBudgetManager,
    TokenBudgetConfig,
    count_tokens,
)
from app.services.ai.FieldOpsAI.providers.cache import (
    CacheTTLPolicy,
    CachedProviderResponse,
    ProviderCacheConfig,
    ProviderCacheRequest,
    SyncProviderCache,
)
from app.services.ai.FieldOpsAI.providers.groq_client import (
    GroqClient,
)
from app.services.ai.FieldOpsAI.providers.provider_factory import (
    ProviderFactory,
)
from app.services.ai.FieldOpsAI.providers.provider_failover import (
    ProviderFailoverExecutor,
    ProviderFailoverExhaustedError,
)
from app.services.ai.FieldOpsAI.providers.provider_health import (
    ProviderHealthInfrastructureError,
    ProviderHealthMonitor,
)
from app.services.ai.FieldOpsAI.runtime.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerInfrastructureError,
    CircuitOpenError,
    CircuitPermit,
)
from app.services.ai.FieldOpsAI.runtime.prompt_builder import (
    PromptBuilder,
)
from app.services.ai.FieldOpsAI.runtime.response_parser import (
    ResponseParser,
)
from app.services.ai.FieldOpsAI.runtime.runtime_interface import (
    RuntimeInterface,
)
from app.services.ai.FieldOpsAI.schemas.ai_task import (
    AITask,
)
from app.services.ai.FieldOpsAI.schemas.provider import (
    GenerationResult,
    UsageStats,
)
from app.services.ai.pii_sanitizer import (
    PIISanitizer,
    PIILeakageError,
    PlaceholderMap,
    pii_sanitizer,
)


logger = logging.getLogger(__name__)


def estimate_chat_input_tokens(messages: list[dict[str, str]], model: str) -> int:
    """Estimate the complete serialized chat envelope with bounded headroom.

    Provider framing differs slightly from the local tokenizer. A 20% margin
    plus 16 framing tokens covers measured provider/local-count variance while
    remaining proportional and bounded; output and daily reservations remain
    governed by the existing budget manager.
    """
    serialized = json.dumps(messages, ensure_ascii=False, separators=(",", ":"))
    base = count_tokens(serialized, model) + (4 * len(messages))
    return max(1, math.ceil(base * 1.20) + 16)


class _LegacyClientProviderAdapter(BaseAIProvider):
    """
    Provider metadata adapter for injected legacy clients.

    The adapter supplies provider and model metadata only.
    Provider execution remains the responsibility of the
    injected client.
    """

    def __init__(
        self,
        name: str = "groq",
        model: str = "openai/gpt-oss-120b",
    ) -> None:
        self._name = name
        self._model = model

    def generate_completion(
        self,
        messages,
        temperature=None,
        max_tokens=None,
    ) -> str:
        raise NotImplementedError(
            "Legacy adapter does not perform provider calls."
        )

    def provider_name(self) -> str:
        return self._name

    def model_name(self) -> str:
        return self._model

    def health_check(self) -> bool:
        return True

@dataclass
class SubTask:
    task_id: str
    task: str
    agent_type: AITask
    context: dict[str, Any]
    dependencies: list[str] = field(default_factory=list)
    priority: str = "normal"


@dataclass
class AgentMapping:
    assignments: dict[str, AITask]


@dataclass
class AgentResult:
    task_id: str
    agent_type: AITask
    result: Any
    confidence: float = 1.0
    status: str = "succeeded"
    error: str | None = None


@dataclass
class FinalResult:
    task_id: str
    results: list[AgentResult]
    result: Any
    status: str = "succeeded"


@dataclass
class ResolvedResult:
    result: Any
    confidence: float
    source_task_id: str | None = None

class AIOrchestrator(RuntimeInterface):
    """
    Coordinates prompt construction, privacy, provider failover,
    circuit protection, budget accounting, caching, placeholder
    restoration, and structured response validation.
    """

    def __init__(
    self,
    *,
    config: Any | None = None,
    failover_executor: ProviderFailoverExecutor | None = None,
    provider_health_monitor: ProviderHealthMonitor | None = None,
    provider_client_factory: (
        Callable[[BaseAIProvider], Any] | None
    ) = None,
    client: Any | None = None,
    sanitizer: PIISanitizer | None = None,
    prompt_builder: PromptBuilder | None = None,
    response_parser: ResponseParser | None = None,
    budget_manager: SyncTokenBudgetManager | None = None,
    provider_cache: SyncProviderCache | None = None,
    circuit_breaker: CircuitBreaker | None = None,
    redis_client: Any | None = None,
) -> None:
        """
        Initialize the AI orchestrator.

        Dependencies may be injected by tests or other runtime
        integrations. Production dependencies are created only
        when an injected dependency is not supplied.
        """

        self.prompt_builder = (
            prompt_builder
            if prompt_builder is not None
            else PromptBuilder()
        )

        self.pii_sanitizer = (
            sanitizer
            if sanitizer is not None
            else pii_sanitizer
        )

        self.response_parser = (
            response_parser
            if response_parser is not None
            else ResponseParser()
        )

        self.client = client

        base_config_loader = ConfigLoader()

        # --------------------------------------------------
        # Shared synchronous Redis client
        # --------------------------------------------------

        

        if redis_client is None and circuit_breaker is not None:
            try:
                redis_client = vars(
                    circuit_breaker
                ).get("redis")
            except TypeError:
                redis_client = None

        if (
            redis_client is None
            and budget_manager is not None
        ):
            try:
                redis_client = vars(
                    budget_manager
                ).get("redis")
            except TypeError:
                redis_client = None

        if redis_client is None:
            redis_client = get_redis_client()

        # --------------------------------------------------
        # Provider health monitor
        # --------------------------------------------------

        if provider_health_monitor is not None:
            self.provider_health_monitor = (
                provider_health_monitor
            )
        else:
            self.provider_health_monitor = (
                ProviderHealthMonitor(
                    redis_client,
                    config=(
                        base_config_loader
                        .provider_health
                    ),
                )
            )

        # --------------------------------------------------
        # Injected-client provider factory
        # --------------------------------------------------

        if client is not None:
            raw_provider = getattr(
                client,
                "provider",
                None,
            )

            candidate_name: str | None = None
            candidate_model: str | None = None

            if raw_provider is not None:
                try:
                    raw_name = (
                        raw_provider.provider_name()
                    )

                    raw_model = (
                        raw_provider.model_name()
                    )

                    if (
                        isinstance(raw_name, str)
                        and raw_name.strip()
                        and isinstance(raw_model, str)
                        and raw_model.strip()
                    ):
                        candidate_name = (
                            raw_name.strip().lower()
                        )

                        candidate_model = (
                            raw_model.strip()
                        )

                except Exception:
                    candidate_name = None
                    candidate_model = None

            if (
                candidate_name is not None
                and candidate_model is not None
            ):
                injected_provider = raw_provider
                injected_provider_name = candidate_name

            else:
                injected_provider_name = "groq"

                injected_provider = (
                    _LegacyClientProviderAdapter(
                        name=injected_provider_name,
                        model=(
                            base_config_loader
                            .model_name
                        ),
                    )
                )

            class SingleClientProviderFactory:
                """
                Provider factory used for one injected client.
                """

                @classmethod
                def create_provider(
                    cls,
                    name: str,
                    config=None,
                    provider_kwargs=None,
                ) -> BaseAIProvider:
                    normalized_name = (
                        name.strip().lower()
                    )

                    if (
                        normalized_name
                        != injected_provider_name
                    ):
                        raise ProviderConfigurationError(
                            "Configured AI provider "
                            "is unsupported."
                        )

                    return injected_provider

                @classmethod
                def registered_names(
                    cls,
                ) -> list[str]:
                    return [
                        injected_provider_name
                    ]

            class InjectedSingleConfigLoader:
                """
                Config wrapper that limits an injected client
                to one provider.
                """

                def __getattr__(
                    self,
                    name: str,
                ) -> Any:
                    return getattr(
                        base_config_loader,
                        name,
                    )

                @property
                def provider_fallback_order(
                    self,
                ) -> list[str]:
                    return [
                        injected_provider_name
                    ]

            factory_to_use = (
                SingleClientProviderFactory
            )

            config_loader: Any = (
                InjectedSingleConfigLoader()
            )

            # Do not perform production provider-health Redis
            # lookups for an injected single client.
            executor_health_monitor = None

        else:
            factory_to_use = ProviderFactory
            config_loader = base_config_loader

            executor_health_monitor = (
                self.provider_health_monitor
            )

        self.model_temperature = float(config_loader.temperature)
        communication_settings = config_loader.get_config_snapshot().get(
            "communication_generation", {}
        )
        self.communication_in_app_temperature = float(
            communication_settings.get(
                "in_app_temperature",
                self.model_temperature,
            )
        )
        if not 0.0 <= self.communication_in_app_temperature <= 1.0:
            raise ValueError(
                "communication_generation.in_app_temperature must be between 0 and 1"
            )

        # --------------------------------------------------
        # Failover executor
        # --------------------------------------------------

        if failover_executor is not None:
            self.failover_executor = (
                failover_executor
            )
        else:
            self.failover_executor = (
                ProviderFailoverExecutor(
                    provider_factory=(
                        factory_to_use
                    ),
                    health_monitor=(
                        executor_health_monitor
                    ),
                    config=config_loader,
                )
            )

        # --------------------------------------------------
        # Token budget
        # --------------------------------------------------

        if budget_manager is not None:
            self.token_budget_manager = (
                budget_manager
            )
        else:
            budget_config = (
                TokenBudgetConfig.from_mapping(
                    config_loader.provider_budget
                )
            )

            self.token_budget_manager = (
                SyncTokenBudgetManager(
                    redis_client,
                    budget_config,
                )
            )

        # --------------------------------------------------
        # Provider cache
        # --------------------------------------------------

        if provider_cache is not None:
            self.provider_cache = provider_cache
        else:
            raw_cache_config = getattr(
                config_loader,
                "provider_cache",
                {},
            )

            if isinstance(
                raw_cache_config,
                dict,
            ):
                cache_config = (
                    ProviderCacheConfig(
                        **raw_cache_config
                    )
                )
            else:
                cache_config = (
                    ProviderCacheConfig()
                )

            self.provider_cache = (
                SyncProviderCache(
                    redis_client,
                    cache_config,
                )
            )

        # --------------------------------------------------
        # Circuit breaker
        # --------------------------------------------------

        if circuit_breaker is not None:
            self.circuit_breaker = (
                circuit_breaker
            )
        else:
            circuit_config = (
                CircuitBreakerConfig.from_mapping(
                    config_loader
                    .provider_circuit_breaker
                )
            )

            self.circuit_breaker = (
                CircuitBreaker(
                    redis_client,
                    circuit_config,
                )
            )

        # --------------------------------------------------
        # Provider-client construction
        # --------------------------------------------------

        if provider_client_factory is not None:
            self.provider_client_factory = (
                provider_client_factory
            )

        elif self.client is not None:
            self.provider_client_factory = (
                lambda provider: self.client
            )

        else:
            self.provider_client_factory = (
                lambda provider: GroqClient(
                    provider=provider
                )
            )

    def _load_task_prompt(
        self,
        task: AITask,
    ) -> str:
        """
        Load a task prompt from the prompt registry.
        (Kept as a compatibility wrapper).
        """
        return self.prompt_builder.get_task_prompt(task)

    def execute(
        self,
        task: AITask,
        context: Dict[str, Any],
        response_schema: (
            Optional[Type[BaseModel]]
        ) = None,
    ) -> str | BaseModel:
        """
        Execute one AI task using only sanitized provider-bound
        data.
        """

        placeholder_map: (
            PlaceholderMap | None
        ) = None

        try:
            logger.info(
                "Starting AI task '%s'.",
                task.value,
            )

            # ----------------------------------------------
            # 1. Build prompts once
            # ----------------------------------------------

            system_prompt = (
                self.prompt_builder.build()
                + "\n\n"
                + self._load_task_prompt(task)
            )

            # ----------------------------------------------
            # 2. Sanitize context once
            # ----------------------------------------------

            sanitization_result = (
                self.pii_sanitizer.sanitize(
                    context
                )
            )

            sanitized_context = (
                sanitization_result
                .sanitized_data
            )

            placeholder_map = (
                sanitization_result
                .placeholder_map
            )

            if not isinstance(
                sanitized_context,
                dict,
            ):
                raise TypeError(
                    "Sanitized AI context must "
                    "be a dictionary."
                )

            logger.info(
                "Structured context sanitized "
                "for task '%s'. Replacement "
                "count: %s.",
                task.value,
                sanitization_result
                .replacement_count,
            )

            # ----------------------------------------------
            # 3. Build user prompt from sanitized context
            # ----------------------------------------------

            user_prompt = (
                self._build_user_prompt(
                    task=task,
                    context=sanitized_context,
                )
            )

            (
                sanitized_user_prompt,
                placeholder_map,
            ) = (
                self.pii_sanitizer
                .sanitize_prompt(
                    prompt=user_prompt,
                    placeholder_map=(
                        placeholder_map
                    ),
                )
            )

            messages: List[
                Dict[str, str]
            ] = [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": (
                        sanitized_user_prompt
                    ),
                },
            ]

            # ----------------------------------------------
            # 4. Request metadata
            # ----------------------------------------------

            category = "general"

            if task == AITask.SENTIMENT:
                category = "sentiment"

            elif task == AITask.CUSTOMER_SUPPORT:
                category = "customer_support"

            elif task == AITask.COMMUNICATION:
                channel = (
                    sanitized_context.get(
                        "channel"
                    )
                )

                if isinstance(channel, str):
                    normalized_channel = (
                        channel.lower()
                    )

                    if normalized_channel in (
                        "sms",
                        "email",
                        "push",
                    ):
                        category = (
                            normalized_channel
                        )

                    elif normalized_channel in (
                        "in_app",
                        "portal",
                    ):
                        category = "portal"

            generation_temperature = self.model_temperature
            if (
                task == AITask.COMMUNICATION
                and str(sanitized_context.get("channel", "")).upper()
                in {"IN_APP", "PORTAL"}
            ):
                generation_temperature = (
                    self.communication_in_app_temperature
                )

            tenant_id = (
                sanitized_context.get(
                    "tenant_id"
                )
            )

            # ----------------------------------------------
            # 5. Per-provider execution
            # ----------------------------------------------

            def attempt_runner(
                provider_name: str,
                provider: BaseAIProvider,
            ) -> GenerationResult:
                normalized_provider = (
                    provider_name
                    .strip()
                    .lower()
                )

                # ------------------------------------------
                # Provider metadata
                # ------------------------------------------

                try:
                    model_name = (
                        provider.model_name()
                    )

                    if (
                        not isinstance(
                            model_name,
                            str,
                        )
                        or not model_name.strip()
                    ):
                        raise ValueError(
                            "Invalid model name."
                        )

                    model_name = (
                        model_name.strip()
                    )

                except Exception:
                    raise ProviderExecutionError(
                        "Invalid provider metadata.",
                        is_retryable=False,
                    ) from None

                # Estimate the exact serialized messages sent to the provider,
                # including role metadata and a bounded provider framing margin.
                estimated_input_tokens = estimate_chat_input_tokens(messages, model_name)

                max_output_tokens = (
                    self.token_budget_manager
                    .config
                    .per_request
                    .get(
                        category,
                        4096,
                    )
                )

                # ------------------------------------------
                # Cache lookup before circuit and budget
                # ------------------------------------------

                cache_request = (
                    ProviderCacheRequest(
                        tenant_id=tenant_id,
                        provider=(
                            normalized_provider
                        ),
                        model=model_name,
                        sanitized_messages=(
                            messages
                        ),
                        temperature=generation_temperature,
                        max_tokens=(
                            max_output_tokens
                        ),
                        ttl_policy=(
                            CacheTTLPolicy.DYNAMIC
                        ),
                        explicit_safety_verification=True,
                    )
                )

                cached_response = (
                    self.provider_cache.get(
                        cache_request
                    )
                )

                if cached_response is not None:
                    return GenerationResult(
                        text=(
                            cached_response.text
                        ),
                        provider_name=(
                            normalized_provider
                        ),
                        model_name=model_name,
                        usage=UsageStats(
                            prompt_tokens=0,
                            completion_tokens=0,
                            total_tokens=0,
                            request_count=0,
                            latency_ms=0.0,
                            cost_usd=0.0,
                        ),
                    )

                permit: CircuitPermit | None = None

                reservation_id: (
                    str | None
                ) = None

                generation_result: (
                    GenerationResult | None
                ) = None

                provider_error: (
                    BaseException | None
                ) = None

                cleanup_error: (
                    ProviderExecutionError | None
                ) = None

                client_construction_failed = (
                    False
                )

                # ------------------------------------------
                # Provider attempt
                # ------------------------------------------

                try:
                    permit = (
                        self.circuit_breaker
                        .check_permission(
                            normalized_provider
                        )
                    )

                    try:
                        reservation_id = (
                            self
                            .token_budget_manager
                            .reserve(
                                estimated_input_tokens=(
                                    estimated_input_tokens
                                ),
                                max_output_tokens=(
                                    max_output_tokens
                                ),
                                category=category,
                                provider=(
                                    normalized_provider
                                ),
                                model=model_name,
                                tenant_id=tenant_id,
                            )
                        )

                    except BudgetExceededError as exc:
                        correlation_id = sanitized_context.get("correlation_id")
                        logger.warning(
                            "AI_BUDGET_REJECTED provider=%s category=%s "
                            "model=%s estimated_input=%s max_output=%s "
                            "correlation_id=%s reason=%s",
                            normalized_provider,
                            category,
                            model_name,
                            estimated_input_tokens,
                            max_output_tokens,
                            correlation_id,
                            str(exc)[:160],
                            extra={
                                "provider": normalized_provider,
                                "category": category,
                                "model": model_name,
                                "estimated_input_tokens": estimated_input_tokens,
                                "max_output_tokens": max_output_tokens,
                                "correlation_id": correlation_id,
                                "budget_reason": str(exc)[:160],
                            },
                        )

                        raise ProviderExecutionError(
                            "Daily AI token budget "
                            "exceeded.",
                            status_code=None,
                            is_retryable=False,
                        ) from None

                    except BudgetInfrastructureError as exc:
                        correlation_id = sanitized_context.get("correlation_id")
                        logger.warning(
                            "AI_BUDGET_INFRASTRUCTURE_FAILURE provider=%s "
                            "category=%s correlation_id=%s error_type=%s",
                            normalized_provider,
                            category,
                            correlation_id,
                            type(exc).__name__,
                            extra={
                                "provider": normalized_provider,
                                "category": category,
                                "correlation_id": correlation_id,
                                "error_type": type(exc).__name__,
                            },
                        )

                        raise ProviderExecutionError(
                            "AI budget infrastructure "
                            "failure.",
                            status_code=None,
                            is_retryable=False,
                        ) from None

                    try:
                        provider_client = (
                            self
                            .provider_client_factory(
                                provider
                            )
                        )

                    except Exception:
                        client_construction_failed = (
                            True
                        )

                        raise ProviderExecutionError(
                            "Provider client "
                            "construction failed.",
                            is_retryable=False,
                        ) from None

                    generate_result_method = (
                        getattr(
                            provider_client,
                            "generate_result",
                            None,
                        )
                    )

                    if callable(
                        generate_result_method
                    ):
                        generation_kwargs = {
                            "task": task,
                            "messages": messages,
                            "context": sanitized_context,
                        }
                        if isinstance(provider_client, GroqClient):
                            generation_kwargs["temperature"] = (
                                generation_temperature
                            )
                            # Enforce the same output limit that was reserved
                            # by the token budget manager.
                            generation_kwargs["max_tokens"] = (
                                max_output_tokens
                            )
                        raw_result = generate_result_method(
                            **generation_kwargs
                        )

                    else:
                        generate_method = getattr(
                            provider_client,
                            "generate",
                            None,
                        )

                        if not callable(
                            generate_method
                        ):
                            raise ProviderExecutionError(
                                "Provider client has "
                                "no supported generation "
                                "method.",
                                is_retryable=False,
                            )

                        raw_text = generate_method(
                            task=task,
                            messages=messages,
                            context=(
                                sanitized_context
                            ),
                        )

                        if isinstance(
                            raw_text,
                            GenerationResult,
                        ):
                            raw_result = raw_text

                        elif isinstance(
                            raw_text,
                            str,
                        ):
                            actual_output_tokens = count_tokens(
                                raw_text, model_name
                            )

                            usage = UsageStats(
                                prompt_tokens=(
                                    estimated_input_tokens
                                ),
                                completion_tokens=(
                                    actual_output_tokens
                                ),
                                total_tokens=(
                                    estimated_input_tokens
                                    + actual_output_tokens
                                ),
                                request_count=1,
                                latency_ms=0.0,
                                cost_usd=0.0,
                            )

                            raw_result = (
                                GenerationResult(
                                    text=raw_text,
                                    provider_name=(
                                        normalized_provider
                                    ),
                                    model_name=(
                                        model_name
                                    ),
                                    usage=usage,
                                )
                            )

                        else:
                            raise ProviderExecutionError(
                                "Provider output must "
                                "be a string or "
                                "GenerationResult.",
                                is_retryable=False,
                            )

                    # --------------------------------------
                    # Validate provider response
                    # --------------------------------------

                    if not isinstance(
                        raw_result,
                        GenerationResult,
                    ):
                        raise ProviderExecutionError(
                            "Invalid provider response "
                            "metadata.",
                            is_retryable=False,
                        )

                    if (
                        not isinstance(
                            raw_result.text,
                            str,
                        )
                        or not raw_result.text.strip()
                    ):
                        raise ProviderExecutionError(
                            "Invalid provider response "
                            "metadata.",
                            is_retryable=False,
                        )

                    if (
                        not isinstance(
                            raw_result.provider_name,
                            str,
                        )
                        or (
                            raw_result
                            .provider_name
                            .strip()
                            .lower()
                            != normalized_provider
                        )
                    ):
                        raise ProviderExecutionError(
                            "Invalid provider response "
                            "metadata.",
                            is_retryable=False,
                        )

                    if (
                        not isinstance(
                            raw_result.model_name,
                            str,
                        )
                        or not (
                            raw_result
                            .model_name
                            .strip()
                        )
                    ):
                        raise ProviderExecutionError(
                            "Invalid provider response "
                            "metadata.",
                            is_retryable=False,
                        )

                    if (
                        raw_result
                        .model_name
                        .strip()
                        != model_name
                    ):
                        raise ProviderExecutionError(
                            "Invalid provider response "
                            "metadata.",
                            is_retryable=False,
                        )

                    if not isinstance(
                        raw_result.usage,
                        UsageStats,
                    ):
                        raise ProviderExecutionError(
                            "Invalid provider response "
                            "metadata.",
                            is_retryable=False,
                        )

                    generation_result = (
                        raw_result
                    )

                except (
                    ProviderExecutionError,
                    ProviderHealthInfrastructureError,
                    CircuitBreakerInfrastructureError,
                    CircuitOpenError,
                ) as error:
                    provider_error = error

                # except Exception:
                #     provider_error = (
                #         ProviderExecutionError(
                #             "AI provider execution "
                #             "failed.",
                #             is_retryable=False,
                #         )
                #     )

                except Exception as exc:
                    # Preserve the real provider/client exception in logs.
                    # The old code printed a traceback and then replaced the
                    # exception with a generic error, making the root cause
                    # difficult to identify from application logs.
                    logger.exception(
                        "Unexpected exception during AI provider execution.",
                        extra={
                            "task": task.value,
                            "provider": normalized_provider,
                            "model": model_name,
                            "exception_type": type(exc).__name__,
                            "exception_message": str(exc)[:1000],
                            "category": category,
                        },
                    )
                    provider_error = ProviderExecutionError(
                        (
                            "AI provider execution failed "
                            f"({type(exc).__name__}): {str(exc)[:500]}"
                        ),
                        is_retryable=False,
                    )

                # ------------------------------------------
                # Exactly-once reservation cleanup
                # ------------------------------------------

                if reservation_id is not None:
                    if generation_result is not None:
                        try:
                            actual_input = generation_result.usage.prompt_tokens
                            logger.info(
                                "AI_TOKEN_ESTIMATE_RECONCILIATION provider=%s model=%s estimated_input=%s actual_input=%s underestimation=%s",
                                normalized_provider, model_name, estimated_input_tokens,
                                actual_input, max(0, actual_input - estimated_input_tokens),
                            )
                            (
                                self
                                .token_budget_manager
                                .reconcile(
                                    reservation_id=(
                                        reservation_id
                                    ),
                                    actual_input_tokens=actual_input,
                                    actual_output_tokens=(
                                        generation_result
                                        .usage
                                        .completion_tokens
                                    ),
                                    provider=(
                                        normalized_provider
                                    ),
                                )
                            )

                        except BudgetExceededError as exc:
                            logger.warning(
                                "AI_BUDGET_RECONCILE_OVERRUN provider=%s category=%s "
                                "est_in=%s actual_in=%s max_out=%s actual_out=%s reason=%s",
                                normalized_provider,
                                category,
                                estimated_input_tokens,
                                generation_result.usage.prompt_tokens,
                                max_output_tokens,
                                generation_result.usage.completion_tokens,
                                str(exc)[:200],
                            )
                            cleanup_error = ProviderExecutionError(
                                "AI token budget overrun detected.",
                                is_retryable=False,
                            )
                        except Exception:
                            cleanup_error = (
                                ProviderExecutionError(
                                    "AI budget "
                                    "infrastructure "
                                    "failure.",
                                    is_retryable=False,
                                )
                            )

                    else:
                        try:
                            (
                                self
                                .token_budget_manager
                                .cancel(
                                    reservation_id=(
                                        reservation_id
                                    ),
                                    provider=(
                                        normalized_provider
                                    ),
                                )
                            )

                        except Exception:
                            cleanup_error = (
                                ProviderExecutionError(
                                    "AI budget "
                                    "infrastructure "
                                    "failure.",
                                    is_retryable=False,
                                )
                            )

                # ------------------------------------------
                # Exactly-once permit cleanup
                # ------------------------------------------

                if permit is not None:
                    try:
                        if (
                            generation_result
                            is not None
                        ):
                            (
                                self
                                .circuit_breaker
                                .record_success(
                                    permit
                                )
                            )

                        elif (
                            reservation_id is None
                            or client_construction_failed
                        ):
                            # No provider call took place.
                            # For HALF_OPEN permits this
                            # releases the probe lock.
                            (
                                self
                                .circuit_breaker
                                .release_probe_lock(
                                    permit
                                )
                            )

                        else:
                            failure_for_circuit = (
                                provider_error
                                if provider_error
                                is not None
                                else ProviderExecutionError(
                                    "AI provider execution "
                                    "failed.",
                                    is_retryable=False,
                                )
                            )

                            (
                                self
                                .circuit_breaker
                                .record_failure(
                                    permit,
                                    failure_for_circuit,
                                )
                            )

                    except Exception:
                        if cleanup_error is None:
                            cleanup_error = (
                                ProviderExecutionError(
                                    "Circuit breaker "
                                    "infrastructure "
                                    "failure.",
                                    is_retryable=False,
                                )
                            )

                # Cleanup failures must not be swallowed.
                if cleanup_error is not None:
                    raise cleanup_error from None

                # Re-raise the provider failure after cleanup.
                if provider_error is not None:
                    raise provider_error from None

                if generation_result is None:    # pragma: no cover
                    raise ProviderExecutionError(
                        "AI provider execution failed.",
                        is_retryable=False,
                    ) from None

                # ------------------------------------------
                # Cache only successful finalized responses
                # ------------------------------------------

                self.provider_cache.set(
                    cache_request,
                    CachedProviderResponse(
                        text=(
                            generation_result.text
                        ),
                        usage=(
                            generation_result.usage
                        ),
                    ),
                )

                return generation_result

            # ----------------------------------------------
            # 6. Provider failover
            # ----------------------------------------------

            try:
                failover_result = (
                    self.failover_executor
                    .execute(
                        attempt_runner
                    )
                )

            except (
                PIILeakageError,
                CircuitOpenError,
                ProviderFailoverExhaustedError,
                ProviderExecutionError,
                CircuitBreakerInfrastructureError,
                ProviderHealthInfrastructureError,
            ) as exc:
                logger.error(
                    "AI_PROVIDER_PIPELINE_FAILED task=%s correlation_id=%s "
                    "error_type=%s status_code=%s retryable=%s",
                    task.value,
                    sanitized_context.get("correlation_id"),
                    type(exc).__name__,
                    getattr(exc, "status_code", None),
                    getattr(exc, "is_retryable", None),
                    extra={
                        "task": task.value,
                        "correlation_id": sanitized_context.get("correlation_id"),
                        "error_type": type(exc).__name__,
                        "status_code": getattr(exc, "status_code", None),
                        "is_retryable": getattr(exc, "is_retryable", None),
                    },
                )
                raise

            except Exception as exc:
                correlation_id = sanitized_context.get("correlation_id")
                logger.exception(
                    "AI orchestration failed for task '%s' "
                    "correlation_id=%s error_type=%s.",
                    task.value,
                    correlation_id,
                    type(exc).__name__,
                )

                raise RuntimeError(
                    "AI orchestration failed "
                    f"for task '{task.value}'."
                ) from None
            print("FAILOVER RESULT:", failover_result)
            print(
                "FAILOVER GENERATION RESULT:",
                failover_result.generation_result,
            )

            if failover_result.generation_result is None:
                raise ProviderExecutionError(
                    "AI provider execution failed.",
                    is_retryable=False,
                )

            print(
                "FAILOVER TEXT:",
                failover_result.generation_result.text,
            )

            raw_response = (
                failover_result
                .generation_result
                .text
            )
            # ----------------------------------------------
            # 7. Restore placeholders locally
            # ----------------------------------------------

            restored_response = (
                self.pii_sanitizer
                .restore_data(
                    data=raw_response,
                    placeholder_map=(
                        placeholder_map
                    ),
                    clear_mapping=False,
                )
            )

            if not isinstance(
                restored_response,
                str,
            ):
                raise TypeError(
                    "Restored AI response must "
                    "be a string."
                )

            # ----------------------------------------------
            # 8. Parse optional response schema
            # ----------------------------------------------

            if response_schema is not None:
                logger.info(
                    "Validating AI response "
                    "using schema '%s'.",
                    response_schema.__name__,
                )

                try:
                    return self.response_parser.parse(
                        restored_response,
                        response_schema,
                        correlation_id=sanitized_context.get("correlation_id"),
                    )
                except (ValueError, TypeError) as exc:
                    logger.error(
                        "AI_RESPONSE_SCHEMA_REJECTED task=%s schema=%s "
                        "correlation_id=%s error_type=%s",
                        task.value,
                        response_schema.__name__,
                        sanitized_context.get("correlation_id"),
                        type(exc).__name__,
                        extra={
                            "task": task.value,
                            "schema": response_schema.__name__,
                            "correlation_id": sanitized_context.get("correlation_id"),
                            "error_type": type(exc).__name__,
                        },
                    )
                    raise

            return restored_response

        finally:
            if placeholder_map is not None:
                placeholder_map.clear()

    @staticmethod
    def _build_user_prompt(
        task: AITask,
        context: Dict[str, Any],
    ) -> str:
        """
        Build a task prompt using sanitized context only.
        """

        context_text = json.dumps(
            context,
            indent=2,
            ensure_ascii=False,
            default=str,
        )

        return (
            f"TASK:\n"
            f"{task.value}\n\n"
            f"CONTEXT:\n"
            f"{context_text}\n\n"
            "IMPORTANT INSTRUCTIONS\n"
            "----------------------\n"
            "1. Return ONLY a valid JSON object.\n"
            "2. Do NOT use markdown.\n"
            "3. Do NOT explain your answer.\n"
            "4. Do NOT include headings.\n"
            "5. Do NOT include bullet points.\n"
            "6. Do NOT wrap the JSON inside ```json.\n"
            "7. Follow the schema defined in the system "
            "prompt exactly.\n"
            "8. Use ONLY the information provided in "
            "CONTEXT.\n"
            "9. Never invent facts, IDs, names, dates, "
            "or values.\n"
            "10. If required information is missing, "
            "respond according to the task schema.\n\n"
            "Return ONLY the JSON object."
        )

    def runtime_name(self) -> str:
        """
        Return the provider-neutral runtime name.
        """

        return "FieldOps AI Runtime"

    def health_check(self) -> bool:
        """
        Verify basic runtime initialization.
        """

        try:
            return (
                self.pii_sanitizer is not None
                and self.failover_executor
                is not None
            )

        except Exception:
            return False

class AgentOrchestrator:
    """
    Coordinates multiple FieldOps agents for complex tasks.

    Flow:

        Task
          ?
        Decompose
          ?
        Select Agents
          ?
        Execute
          ?
        Aggregate
          ?
        Resolve Conflicts
          ?
        Final Result
    """

    MAX_ORCHESTRATION_SECONDS = 30.0
    MAX_SUBTASK_SECONDS = 10.0

    def __init__(
        self,
        *,
        agent_registry: AgentRegistry,
        agent_bus: AgentBus,
        runtime_engine: AIRuntimeEngine,
        config_manager: AgentConfigManager,
    ) -> None:
        self.agent_registry = agent_registry
        self.agent_bus = agent_bus
        self.runtime_engine = runtime_engine
        self.config_manager = config_manager

    def decompose(
        self,
        task: str,
        *,
        tenant_id: str,
        context: dict[str, Any] | None = None,
    ) -> list[SubTask]:
        """
        Break a high-level task into agent-specific subtasks.
        """

        if not isinstance(task, str) or not task.strip():
            raise ValueError("task must be a non-empty string.")

        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("tenant_id must be a non-empty string.")

        context = dict(context or {})
        context["tenant_id"] = tenant_id

        task_id = str(uuid4())

        return [
            SubTask(
                task_id=task_id,
                task=task,
                agent_type=AITask.PLANNING,
                context=context,
            )
        ]

    async def select_agents(
        self,
        sub_tasks: list[SubTask],
    ) -> AgentMapping:
        """
        Select an enabled registered agent for each subtask.
        """

        assignments: dict[str, AITask] = {}

        for sub_task in sub_tasks:
            registration = self.agent_registry.get(
                sub_task.agent_type
            )

            if not registration.enabled:
                raise RuntimeError(
                    f"Agent {sub_task.agent_type.value} is disabled."
                )

            assignments[sub_task.task_id] = sub_task.agent_type

        return AgentMapping(assignments=assignments)

    async def _execute_one(
        self,
        sub_task: SubTask,
        agent_mapping: AgentMapping,
    ) -> AgentResult:
        """
        Execute one subtask through the existing Runtime Engine.
        """

        agent_type = agent_mapping.assignments.get(
            sub_task.task_id
        )

        if agent_type is None:
            return AgentResult(
                task_id=sub_task.task_id,
                agent_type=sub_task.agent_type,
                result=None,
                confidence=0.0,
                status="failed",
                error="No agent assigned to subtask.",
            )

        try:
            task_spec = TaskSpec(
                task_id=sub_task.task_id,
                tenant_id=sub_task.context["tenant_id"],
                agent_type=agent_type,
                context=sub_task.context,
            )

            task_result = await asyncio.wait_for(
                self.runtime_engine.execute_task(task_spec),
                timeout=self.MAX_SUBTASK_SECONDS,
            )

            if getattr(task_result, "status", None) == TaskStatus.SUCCEEDED:
                return AgentResult(
                    task_id=sub_task.task_id,
                    agent_type=agent_type,
                    result=getattr(task_result, "result", task_result),
                    confidence=1.0,
                    status="succeeded",
                )

            return AgentResult(
                task_id=sub_task.task_id,
                agent_type=agent_type,
                result=None,
                confidence=0.0,
                status=str(getattr(task_result, "status", "failed")),
                error=getattr(task_result, "error", "Agent execution failed."),
            )

        except asyncio.TimeoutError:
            return AgentResult(
                task_id=sub_task.task_id,
                agent_type=agent_type,
                result=None,
                confidence=0.0,
                status="timed_out",
                error="Subtask exceeded 10 second timeout.",
            )

        except Exception as exc:
            return AgentResult(
                task_id=sub_task.task_id,
                agent_type=agent_type,
                result=None,
                confidence=0.0,
                status="failed",
                error=f"{type(exc).__name__}: {exc}",
            )

    async def execute_parallel(
        self,
        sub_tasks: list[SubTask],
        agent_mapping: AgentMapping,
    ) -> list[AgentResult]:
        """
        Execute independent subtasks concurrently.
        """

        return list(
            await asyncio.gather(
                *(
                    self._execute_one(
                        sub_task,
                        agent_mapping,
                    )
                    for sub_task in sub_tasks
                )
            )
        )

    async def execute_sequential(
        self,
        sub_tasks: list[SubTask],
        agent_mapping: AgentMapping,
    ) -> list[AgentResult]:
        """
        Execute subtasks sequentially while respecting dependencies.
        """

        completed: dict[str, AgentResult] = {}
        results: list[AgentResult] = []
        remaining = list(sub_tasks)

        while remaining:
            progress = False

            for sub_task in remaining[:]:
                if not all(
                    dependency in completed
                    for dependency in sub_task.dependencies
                ):
                    continue

                progress = True
                remaining.remove(sub_task)

                result = await self._execute_one(
                    sub_task,
                    agent_mapping,
                )

                completed[sub_task.task_id] = result
                results.append(result)

            if not progress:
                raise RuntimeError(
                    "Unable to resolve subtask dependencies."
                )

        return results

    def resolve_conflicts(
        self,
        results: list[AgentResult],
    ) -> ResolvedResult:
        """
        Resolve contradictory results using confidence scoring.
        """

        successful = [
            result
            for result in results
            if result.status == "succeeded"
        ]

        if not successful:
            return ResolvedResult(
                result=None,
                confidence=0.0,
                source_task_id=None,
            )

        winner = max(
            successful,
            key=lambda result: result.confidence,
        )

        return ResolvedResult(
            result=winner.result,
            confidence=winner.confidence,
            source_task_id=winner.task_id,
        )

    def aggregate(
        self,
        results: list[AgentResult],
    ) -> FinalResult:
        """
        Combine all subtask results into a final result.
        """

        if not results:
            return FinalResult(
                task_id=str(uuid4()),
                results=[],
                result=None,
                status="failed",
            )

        resolved = self.resolve_conflicts(results)

        failed = [
            result
            for result in results
            if result.status != "succeeded"
        ]

        status = "failed" if failed and not resolved.result else "succeeded"

        return FinalResult(
            task_id=results[0].task_id,
            results=results,
            result=resolved.result,
            status=status,
        )

    def execution_graph(
        self,
        sub_tasks: list[SubTask],
    ) -> str:
        """
        Generate a Mermaid execution graph.
        """

        lines = [
            "graph TD",
            "    TASK[Orchestration Task]",
        ]

        for index, sub_task in enumerate(sub_tasks):
            node = f"SUB{index}"
            label = sub_task.agent_type.value
            lines.append(
                f"    TASK --> {node}[{label}]"
            )

            for dependency in sub_task.dependencies:
                for dep_index, dependency_task in enumerate(sub_tasks):
                    if dependency_task.task_id == dependency:
                        lines.append(
                            f"    SUB{dep_index} --> {node}"
                        )

        return "\n".join(lines)

    async def orchestrate(
        self,
        task: str,
        *,
        tenant_id: str,
        context: dict[str, Any] | None = None,
        sequential: bool = False,
    ) -> FinalResult:
        """
        Execute the complete orchestration flow.

        Entire orchestration is limited to 30 seconds.
        """

        async def _run() -> FinalResult:
            sub_tasks = self.decompose(
                task,
                tenant_id=tenant_id,
                context=context,
            )

            agent_mapping = await self.select_agents(
                sub_tasks
            )

            if sequential:
                results = await self.execute_sequential(
                    sub_tasks,
                    agent_mapping,
                )
            else:
                results = await self.execute_parallel(
                    sub_tasks,
                    agent_mapping,
                )

            return self.aggregate(results)

        try:
            return await asyncio.wait_for(
                _run(),
                timeout=self.MAX_ORCHESTRATION_SECONDS,
            )

        except asyncio.TimeoutError:
            return FinalResult(
                task_id=str(uuid4()),
                results=[],
                result=None,
                status="timed_out",
            )


ai_orchestrator = AIOrchestrator()
