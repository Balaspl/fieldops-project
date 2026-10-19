"""
communication_agent.py

Communication Agent for FieldOps Commander AI.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

from app.services.ai.FieldOpsAI.agents.base import (
    AgentLifecycleError,
    AgentState,
    BaseAgent,
)
from app.services.ai.FieldOpsAI.agents.channel_selector import (
    ChannelSelector,
)
from app.services.ai.FieldOpsAI.agents.escalation_tree import (
    EscalationContext,
    EscalationDecision,
    EscalationDecisionTree,
)
from app.services.ai.FieldOpsAI.agents.personalization import (
    PersonalizationPipeline,
)
from app.services.ai.FieldOpsAI.runtime.agent_pool import AgentPool
from app.services.ai.FieldOpsAI.runtime.lifecycle import AgentLifecycle
from app.services.ai.FieldOpsAI.runtime.orchestrator import (
    AIOrchestrator,
    ai_orchestrator,
)
from app.services.ai.FieldOpsAI.schemas.agent_config import AgentConfig
from app.services.ai.FieldOpsAI.schemas.agent_result import AgentResultStatus
from app.services.ai.FieldOpsAI.schemas.ai_task import AITask
from app.services.ai.FieldOpsAI.schemas.communication import (
    CommunicationContext,
    CommunicationDecision,
)
from app.services.ai.guardrails.message_validator import MessageValidator
from app.services.template_engine import (
    MessageTemplateEngineError,
    render_managed_template,
)

logger = logging.getLogger(__name__)


class CommunicationAgent(BaseAgent[CommunicationDecision]):
    """
    Generates and validates customer-facing communication.

    The agent is responsible for generation only.

    Delivery is handled by the notification/delivery layer.

    Generation flow:

        CommunicationContext
                |
                v
        Personalization
                |
                v
        AI generation
                |
        +-------+-------+
        |               |
      success          timeout
        |               |
        |          Jinja2 fallback
        |               |
        +-------+-------+
                |
                v
            Guardrails
                |
                v
        CommunicationDecision
    """

    AI_TIMEOUT_SECONDS = 5.0

    SUPPORTED_CHANNELS = {
        "SMS",
        "EMAIL",
        "PUSH",
        "IN_APP",
    }

    def __init__(
        self,
        config: AgentConfig,
        orchestrator: Optional[AIOrchestrator] = None,
        personalization_pipeline: Optional[
            PersonalizationPipeline
        ] = None,
        message_validator: Optional[MessageValidator] = None,
        channel_selector: Optional[ChannelSelector] = None,
        escalation_tree: Optional[EscalationDecisionTree] = None,
        db: Any = None,
    ) -> None:
        """
        Initialize the Communication Agent.

        Parameters
        ----------
        config:
            Communication agent configuration.

        orchestrator:
            Existing AI orchestrator. Injected for testing.

        personalization_pipeline:
            Existing personalization pipeline.

        message_validator:
            Existing communication guardrail validator.

        channel_selector:
            Existing channel selector.

        db:
            Optional SQLAlchemy database session used by the
            managed Jinja2 fallback template engine.
        """

        if config.agent_type != AITask.COMMUNICATION:
            raise ValueError(
                "CommunicationAgent requires an "
                "AITask.COMMUNICATION configuration."
            )

        super().__init__(config)

        self.orchestrator = (
            ai_orchestrator
            if orchestrator is None
            else orchestrator
        )
        # This lets graph callers distinguish provider output from the
        # existing validated template fallback without changing the schema.
        self.last_generation_used_fallback: bool | None = None

        self.personalization_pipeline = (
            personalization_pipeline
            if personalization_pipeline is not None
            else PersonalizationPipeline()
        )

        self.channel_selector = (
            channel_selector
            if channel_selector is not None
            else ChannelSelector()
        )

        self.escalation_tree = (
            escalation_tree
            if escalation_tree is not None
            else EscalationDecisionTree()
        )

        self.message_validator = (
            message_validator
            if message_validator is not None
            else MessageValidator()
        )

        self.db = db

    def evaluate_escalation(
        self,
        context: EscalationContext | dict[str, Any],
    ) -> EscalationDecision:
        """Evaluate an inbound communication using the shared decision tree."""
        escalation_context = (
            context
            if isinstance(context, EscalationContext)
            else EscalationContext.model_validate(context)
        )
        return self.escalation_tree.evaluate(escalation_context)

    # ==========================================================
    # Personalization
    # ==========================================================

    def personalize(
        self,
        template: str,
        context: dict[str, Any],
    ) -> str:
        """
        Apply the existing personalization pipeline.
        """

        return self.personalization_pipeline.apply_template(
            template=template,
            variables=context,
        )

    # ==========================================================
    # AI GENERATION
    # ==========================================================

    async def _generate_with_ai(
        self,
        context: CommunicationContext,
    ) -> CommunicationDecision:
        """
        Execute the existing AI orchestrator with a strict timeout.

        AIOrchestrator.execute() is synchronous, therefore it runs
        in a worker thread.

        IMPORTANT:
        Only timeout is converted into fallback-triggering behavior.

        Other exceptions are intentionally allowed to propagate so
        BaseAgent and existing CommunicationAgent behavior remain
        unchanged.
        """

        try:
            decision = await asyncio.wait_for(
                asyncio.to_thread(
                    self.orchestrator.execute,
                    task=AITask.COMMUNICATION,
                    context=context.model_dump(mode="json"),
                    response_schema=CommunicationDecision,
                ),
                timeout=self.AI_TIMEOUT_SECONDS,
            )

        except asyncio.TimeoutError as exc:
            logger.warning(
                "Communication AI generation timed out.",
                extra={
                    "agent_id": str(self.agent_id),
                    "channel": context.channel,
                    "notification_type": (
                        context.notification_type
                    ),
                    "timeout_seconds": (
                        self.AI_TIMEOUT_SECONDS
                    ),
                },
            )

            raise TimeoutError(
                "Communication AI generation timed out."
            ) from exc

        except Exception as exc:
            # Include the original traceback so the logs reveal the real
            # provider/orchestrator failure instead of only its exception type.
            logger.exception(
                "Communication AI generation failed.",
                extra={
                    "agent_id": str(self.agent_id),
                    "channel": context.channel,
                    "notification_type": context.notification_type,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc)[:1000],
                },
            )

            # Preserve the existing behavior: let BaseAgent and the outer
            # communication graph handle provider failures and approved fallback.
            raise

        if not isinstance(
            decision,
            CommunicationDecision,
        ):
            raise TypeError(
                "Returned object is not a CommunicationDecision."
            )

        return decision

    # ==========================================================
    # FALLBACK
    # ==========================================================

    def _get_fallback_db(self) -> Any:
        """
        Resolve the database session used by the managed-template
        fallback.

        Priority:

        1. Explicit db supplied to CommunicationAgent.
        2. DB attached to PersonalizationPipeline.
        """

        if self.db is not None:
            return self.db

        pipeline_db = getattr(
            self.personalization_pipeline,
            "db",
            None,
        )

        if pipeline_db is not None:
            return pipeline_db

        return None

    def _render_fallback(
        self,
        *,
        context: CommunicationContext,
    ) -> CommunicationDecision:
        """
        Render the managed Jinja2 template and convert it into the
        canonical CommunicationDecision schema.
        """

        db = self._get_fallback_db()

        if db is None:
            logger.error(
                "Communication fallback unavailable because no "
                "database session was supplied.",
                extra={
                    "agent_id": str(self.agent_id),
                    "channel": context.channel,
                    "notification_type": (
                        context.notification_type
                    ),
                    "locale": context.locale,
                },
            )

            raise ValueError(
                "Communication fallback is unavailable because "
                "no database session was supplied."
            )

        template_channel = (
            "PORTAL"
            if context.channel == "IN_APP"
            else context.channel
        )

        try:
            rendered = render_managed_template(
                db=db,
                tenant_id=self.tenant_id,
                agent_type="CommsAgent",
                channel=template_channel,
                language=context.locale,
                status=context.notification_type,
                context=context.model_dump(
                    mode="python"
                ),
            )

        except MessageTemplateEngineError as exc:
            logger.warning(
                "Communication fallback template rendering failed.",
                extra={
                    "agent_id": str(self.agent_id),
                    "channel": context.channel,
                    "notification_type": (
                        context.notification_type
                    ),
                    "locale": context.locale,
                    "error_type": type(exc).__name__,
                },
            )

            raise ValueError(
                "Communication fallback template rendering failed."
            ) from exc

        # ------------------------------------------------------
        # Convert rendered template into canonical output.
        # ------------------------------------------------------

        if context.channel == "SMS":

            output: dict[str, Any] = {
                "channel": "SMS",
                "text": rendered.body,
            }

        elif context.channel == "EMAIL":

            output = {
                "channel": "EMAIL",
                "subject": rendered.title or "",
                "text_body": rendered.body,
            }

            if rendered.template_format == "html":
                output["html_body"] = rendered.body

        elif context.channel == "PUSH":

            output = {
                "channel": "PUSH",
                "title": rendered.title or "",
                "body": rendered.body,
            }

        elif context.channel == "IN_APP":

            output = {
                "channel": "PORTAL",
                "title": rendered.title,
                "body": rendered.body,
                "content_format": (
                    rendered.template_format
                    if rendered.template_format
                    in {"text", "html"}
                    else "text"
                ),
            }

        else:
            raise ValueError(
                f"Unsupported fallback channel: "
                f"{context.channel}"
            )

        decision = CommunicationDecision(
            channel=context.channel,
            output=output,
            tone="PROFESSIONAL",
            confidence=1.0,
        )

        logger.info(
            "Communication fallback generated successfully.",
            extra={
                "agent_id": str(self.agent_id),
                "channel": context.channel,
                "notification_type": (
                    context.notification_type
                ),
                "locale": context.locale,
                "template_id": rendered.template_id,
                "template_version": (
                    rendered.template_version
                ),
                "source": rendered.source,
            },
        )

        return decision

    # ==========================================================
    # GUARDRAILS
    # ==========================================================

    def _validate_decision(
        self,
        *,
        context: CommunicationContext,
        decision: CommunicationDecision,
    ):
        """
        Run the existing complete communication guardrail suite.
        """

        return self.message_validator.validate(
            context=context,
            decision=decision,
        )

    # ==========================================================
    # MAIN AGENT RUN
    # ==========================================================

    async def run(
        self,
        context: dict[str, Any],
    ) -> CommunicationDecision:
        """
        Execute the complete communication generation flow.

        Flow:

        1. Validate CommunicationContext.
        2. Personalize when a template is supplied.
        3. Attempt AI generation with a 5-second timeout.
        4. Fall back to managed Jinja2 templates on timeout.
        5. Validate AI output using guardrails.
        6. If guardrails explicitly require fallback:
           use Jinja2 only when a DB is available.
        7. Validate fallback output.
        8. Return CommunicationDecision.
        """

        start_time = time.perf_counter()
        self.last_generation_used_fallback = None

        # ------------------------------------------------------
        # Context validation
        # ------------------------------------------------------

        exec_context = context.copy()

        # BaseAgent owns tenant isolation.
        #CommunicationContext does not contain tenant_id.
        exec_context.pop("tenant_id", None)

        validated_context = CommunicationContext.model_validate(
            exec_context
        )

        # ------------------------------------------------------
        # Personalization
        # ------------------------------------------------------

        if validated_context.template:

            personalization_context = (
                validated_context.model_dump(
                    mode="python"
                )
            )

            personalization_context.update(
                validated_context.personalization_data
            )

            personalized_message = (
                self.personalization_pipeline.ai_enhance(
                    context=personalization_context,
                    template=validated_context.template,
                )
            )

            exec_context["additional_context"] = (
                personalized_message
            )

            validated_context = (
                CommunicationContext.model_validate(
                    exec_context
                )
            )

        # ------------------------------------------------------
        # AI generation
        # ------------------------------------------------------

        decision: CommunicationDecision | None = None
        ai_failed = False
        used_fallback = False

        try:
            decision = await self._generate_with_ai(
                validated_context
            )

        except TimeoutError as exc:
            # ONLY timeout automatically triggers the fallback.
            ai_failed = True

            logger.warning(
                "Communication AI timed out. "
                "Using Jinja2 fallback.",
                extra={
                    "agent_id": str(self.agent_id),
                    "channel": validated_context.channel,
                    "notification_type": (
                        validated_context.notification_type
                    ),
                    "error_type": type(exc).__name__,
                },
            )

        # ------------------------------------------------------
        # Fallback after AI timeout
        # ------------------------------------------------------

        if ai_failed:
            used_fallback = True

            decision = self._render_fallback(
                context=validated_context
            )

            fallback_validation = self._validate_decision(
                context=validated_context,
                decision=decision,
            )

            if not fallback_validation.passed:

                logger.error(
                    "Communication fallback failed "
                    "guardrail validation.",
                    extra={
                        "agent_id": str(self.agent_id),
                        "channel": validated_context.channel,
                        "notification_type": (
                            validated_context.notification_type
                        ),
                        "quality_score": (
                            fallback_validation.quality_score
                        ),
                    },
                )

                raise ValueError(
                    "Communication fallback failed "
                    "message validation."
                )

        else:

            # This cannot normally happen because
            # _generate_with_ai either returns a decision
            # or raises.
            if decision is None:  # pragma: no cover
                raise RuntimeError(
                    "Communication generation returned "
                    "no decision."
                )

            # --------------------------------------------------
            # Guardrail validation for AI output
            # --------------------------------------------------

            validation_result = self._validate_decision(
                context=validated_context,
                decision=decision,
            )

            if not validation_result.passed:

                logger.warning(
                    "Communication AI output failed validation.",
                    extra={
                        "agent_id": str(self.agent_id),
                        "agent_type": (
                            self.config.agent_type.value
                        ),
                        "channel": validated_context.channel,
                        "notification_type": (
                            validated_context.notification_type
                        ),
                        "quality_score": (
                            validation_result.quality_score
                        ),
                    },
                )

                # --------------------------------------------------
                # Guardrail explicitly requests fallback
                # --------------------------------------------------

                if validation_result.requires_fallback:

                    logger.info(
                        "Guardrails requested Jinja2 fallback.",
                        extra={
                            "agent_id": str(self.agent_id),
                            "channel": (
                                validated_context.channel
                            ),
                            "notification_type": (
                                validated_context.notification_type
                            ),
                        },
                    )

                    # IMPORTANT:
                    #
                    # Existing CommunicationAgent tests expect the
                    # original fallback-required error when there is
                    # no DB available.
                    #
                    # Do not call the template engine in that case.
                    fallback_db = self._get_fallback_db()

                    if fallback_db is None:

                        raise ValueError(
                            "Generated communication failed "
                            "message validation and requires fallback."
                        )

                    decision = self._render_fallback(
                        context=validated_context
                    )
                    used_fallback = True

                    fallback_validation = (
                        self._validate_decision(
                            context=validated_context,
                            decision=decision,
                        )
                    )

                    if not fallback_validation.passed:

                        raise ValueError(
                            "Communication fallback failed "
                            "message validation."
                        )

                else:

                    raise ValueError(
                        "Generated communication failed "
                        "message validation."
                    )

        # ------------------------------------------------------
        # Completion logging
        # ------------------------------------------------------

        elapsed = (
            time.perf_counter()
            - start_time
        )

        logger.info(
            "Communication generation run completed.",
            extra={
                "agent_id": str(self.agent_id),
                "agent_type": (
                    self.config.agent_type.value
                ),
                "channel": validated_context.channel,
                "notification_type": (
                    validated_context.notification_type
                ),
                "elapsed": elapsed,
                "used_fallback": used_fallback,
            },
        )

        self.last_generation_used_fallback = used_fallback

        return decision

    # ==========================================================
    # PUBLIC API
    # ==========================================================

    async def generate_message(
        self,
        context: CommunicationContext | dict[str, Any],
        channel: str | None = None,
        template_key: str | None = None,
    ) -> CommunicationDecision:
        """
        Generate a validated communication message.

        Parameters
        ----------
        context:
            CommunicationContext or dictionary.

        channel:
            Optional channel override.

            Supported story-level channels:

                sms
                email
                push
                portal

            Existing project compatibility:

                IN_APP

        template_key:
            Optional notification/template key.

            It maps to the existing notification_type field.

        Returns
        -------
        CommunicationDecision
            Validated communication result.
        """

        # ------------------------------------------------------
        # Context normalization
        # ------------------------------------------------------

        if isinstance(
            context,
            CommunicationContext,
        ):

            context_data = context.model_dump(
                mode="python"
            )

        elif isinstance(context, dict):

            context_data = dict(context)

        else:

            raise TypeError(
                "context must be a CommunicationContext or dict."
            )

        # ------------------------------------------------------
        # Template selection
        # ------------------------------------------------------

        if template_key is not None:

            if not isinstance(
                template_key,
                str,
            ):
                raise TypeError(
                    "template_key must be a string."
                )

            normalized_template_key = (
                template_key.strip()
            )

            if not normalized_template_key:

                raise ValueError(
                    "template_key cannot be empty."
                )

            context_data[
                "notification_type"
            ] = normalized_template_key

        # ------------------------------------------------------
        # Channel routing
        # ------------------------------------------------------

        if channel is not None:

            if not isinstance(
                channel,
                str,
            ):
                raise TypeError(
                    "channel must be a string."
                )

            normalized_channel = (
                channel.strip().upper()
            )

            # Story-level PORTAL maps to the existing
            # IN_APP compatibility channel.
            if normalized_channel == "PORTAL":
                normalized_channel = "IN_APP"

            if normalized_channel not in (
                self.SUPPORTED_CHANNELS
            ):

                raise ValueError(
                    "Unsupported communication channel: "
                    f"{channel}"
                )

            context_data[
                "channel"
            ] = normalized_channel

        # ------------------------------------------------------
        # Canonical execution path
        # ------------------------------------------------------

        return await self.run(
            context_data
        )

    # ==========================================================
    # SYNCHRONOUS COMPATIBILITY API
    # ==========================================================

    def generate(
        self,
        context: CommunicationContext,
    ) -> CommunicationDecision:
        """
        Synchronous compatibility adapter.

        Existing callers can continue using generate().
        """

        try:
            asyncio.get_running_loop()

        except RuntimeError:
            pass

        else:
            raise RuntimeError(
                "generate() cannot be called from an active "
                "event loop. Use the asynchronous AgentLifecycle "
                "/ execute path instead."
            )

        if self.state is AgentState.TERMINATED:

            raise AgentLifecycleError(
                "A terminated agent cannot execute work."
            )

        exec_context = context.model_dump(
            mode="json"
        )

        exec_context[
            "tenant_id"
        ] = self.tenant_id

        async def _run_wrapped() -> CommunicationDecision:

            pool = AgentPool()

            async with AgentLifecycle(
                agent=self,
                pool=pool,
            ) as lifecycle:

                result = await lifecycle.execute(
                    exec_context
                )

                if (
                    result.status
                    != AgentResultStatus.SUCCESS
                ):

                    raise RuntimeError(
                        "Communication agent execution failed "
                        "with status: "
                        f"{result.status}"
                    )

                if not isinstance(
                    result.output,
                    CommunicationDecision,
                ):

                    raise TypeError(
                        "Communication agent returned an "
                        "invalid output type."
                    )

                return result.output

        return asyncio.run(
            _run_wrapped()
        )
