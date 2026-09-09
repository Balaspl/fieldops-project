"""
ai_generator.py

AI Generator for FieldOps Commander.

Responsibilities
----------------
- Generate AI responses.
- Use the GroqClient.
- Hide AI provider details from higher layers.

The AI Generator NEVER:
- Falls back to templates.
- Updates the database.
- Contains business logic.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.ai.FieldOpsAI.schemas.communication import (
    CommunicationContext,
    CommunicationDecision,
)

from app.services.ai.pii_sanitizer import pii_sanitizer


from app.services.ai.guardrails.fallback_service import (
    GuardrailFallbackService,
    GuardrailFallbackResult,
)

from app.services.ai.FieldOpsAI.providers.budget import (
    SyncTokenBudgetManager,
)

from app.services.ai.FieldOpsAI.providers.groq_client import (
    GroqClient,
)

from app.services.ai.FieldOpsAI.schemas.ai_task import (
    AITask,
)

from app.services.ai.guardrails.pipeline import (
    GuardrailPipeline,
)

from app.services.ai.FieldOpsAI.services.message_output_formatter import (
    MessageOutputFormatter,
)

from app.services.email.email_template_renderer import (
    EmailTemplateRenderer,
)

from typing import Any, Dict

from app.services.ai.FieldOpsAI.runtime.orchestrator import AIOrchestrator


class AIGenerator:
    """
    High-level AI message generator.
    """

    def __init__(self):
        """
        Initialize the AI orchestrator.
        """

        self.orchestrator = AIOrchestrator()

    # ---------------------------------------------------------

    def generate(
        self,
        task: str,
        context: Dict[str, Any],
    ) -> str:
        """
        Generate AI output.

        Parameters
        ----------
        task
            AI task name.

            Examples

            planning

            communication

            sentiment

            closure

        context
            Task context.

        Returns
        -------
        str
            Raw AI response.
        """

        return self.orchestrator.execute(
            task=task,
            context=context,
        )



class AIMessageGenerator:
    """
    AI-powered communication generator for Story 8.4.

    Responsibilities:
    - Validate generation inputs
    - Sanitize PII from communication context
    - Build the AI prompt
    - Sanitize the final prompt before sending to Groq
    - Check the token budget
    - Use Jinja2 fallback when the budget is exceeded
    - Execute the AI request through GroqClient
    - Use fallback when Groq fails
    - Restore PII locally after generation
    - Format generated content for the requested channel
    - Convert formatted content into CommunicationDecision
    - Validate generated message with guardrails
    - Use fallback when guardrails fail
    """

    def __init__(
        self,
        *,
        db: Session,
        budget_manager: SyncTokenBudgetManager,
    ) -> None:
        # Database session used by the fallback service
        # and database-backed operations.
        self.db = db

        
        # Redis connection and TokenBudgetConfig are created by the
        # application runtime/orchestrator and injected here.
        self.budget_manager = budget_manager

        # Existing provider client.
        # AIGenerator does not directly call the Groq API.
        self.groq_client = GroqClient()

        # Existing deterministic Jinja2 fallback service.
        # It selects the safest available fallback template.
        self.fallback_service = GuardrailFallbackService(
            db=db,
        )

        # Existing local guardrail pipeline.
        # It validates the generated communication before
        # allowing it to continue.
        self.guardrail_pipeline = GuardrailPipeline.default()

    async def message_generate(
        self,
        context: CommunicationContext,
        template_key: str,
        channel: str,
    ) -> CommunicationDecision | GuardrailFallbackResult:
        """
        Generate an AI-powered communication message.

        Flow:
        1. Validate input.
        2. Sanitize PII in the context.
        3. Build the AI prompt.
        4. Sanitize the final prompt.
        5. Check the token budget.
        6. Use fallback if the budget is exceeded.
        7. Send the sanitized prompt to Groq.
        8. Use fallback if Groq fails.
        9. Restore PII locally.
        10. Format the generated content.
        11. Build CommunicationDecision.
        12. Run guardrails.
        13. Use fallback if guardrails fail.
        14. Return the validated communication.
        """

        # --------------------------------------------------
        # 1. Validate input
        # --------------------------------------------------

        # Validate the communication context.
        if not isinstance(context, CommunicationContext):
            raise TypeError(
                "context must be a CommunicationContext."
            )

        # Validate the template identifier.
        if not isinstance(template_key, str) or not template_key.strip():
            raise ValueError(
                "template_key must be a non-empty string."
            )

        # Remove accidental whitespace before using
        # the template key.
        template_key = template_key.strip()

        # Validate the communication channel.
        if not isinstance(channel, str) or not channel.strip():
            raise ValueError(
                "channel must be a non-empty string."
            )

        # Normalize the requested channel.
        channel = channel.strip().upper()

        # --------------------------------------------------
        # Validate channel consistency
        # --------------------------------------------------

        # CommunicationContext may store channel either as
        # an enum or as a string depending on the schema.
        #
        # Convert both possibilities into a normalized string
        # before comparing them.
        context_channel = (
            context.channel.value
            if hasattr(context.channel, "value")
            else str(context.channel)
        )

        context_channel = context_channel.strip().upper()

        # The requested channel must match the channel stored
        # in the communication context.
        #
        # This prevents generating content for a different
        # channel than the workflow requested.
        if channel != context_channel:
            raise ValueError(
                "channel must match context.channel."
            )

        # --------------------------------------------------
        # 2. Sanitize PII from communication context
        # --------------------------------------------------

        try:
            # Remove PII before any data reaches the
            # external AI provider.
            sanitization_result = pii_sanitizer.sanitize(
                context,
            )

        except Exception:
            # If sanitization fails, never send potentially
            # sensitive data to Groq.
            #
            # Use the local deterministic fallback instead.
            return self._fallback(
                context=context,
                template_key=template_key,
            )

        # Only sanitized data is allowed to enter the prompt.
        sanitized_context = sanitization_result.sanitized_data

        # Keep the placeholder map so the real values can
        # be restored locally after the AI response.
        placeholder_map = sanitization_result.placeholder_map

        # --------------------------------------------------
        # 3. Build the AI prompt
        # --------------------------------------------------

        # Identify the type of AI task being performed.
        task = AITask.COMMUNICATION

        # Build the prompt using only sanitized context.
        prompt = (
            f"Generate a {channel} communication message "
            f"using template '{template_key}'.\n"
            f"Context:\n{sanitized_context}"
        )

        # --------------------------------------------------
        # 4. Final PII sanitization boundary
        # --------------------------------------------------

        # Perform one final sanitization immediately before
        # the prompt is sent to the external AI provider.
        #
        # The existing placeholder map is passed in so that
        # the same real-data → placeholder relationship is kept.
        try:
            sanitized_prompt, placeholder_map = (
                pii_sanitizer.sanitize_prompt(
                    prompt,
                    placeholder_map,
                )
            )

        except Exception:
            # If final prompt sanitization fails, do not send
            # the prompt to Groq.
            return self._fallback(
                context=context,
                template_key=template_key,
            )

        # --------------------------------------------------
        # 5. Estimate tokens and check budget
        # --------------------------------------------------

        # This is an approximate token estimate.
        # The budget manager uses it before the external
        # provider request is made.
        estimated_input_tokens = len(sanitized_prompt) // 4

        try:
            # Check per-request, daily and rate limits.
            budget_decision = self.budget_manager.check(
            estimated_input_tokens=estimated_input_tokens,
            max_output_tokens=512,
            category=channel.lower(),
            provider="groq",
            model="openai/gpt-oss-120b",
        )

        except Exception:
            # If the budget system itself is unavailable,
            # fail safely by using the local fallback.
            return self._fallback(
                context=context,
                template_key=template_key,
            )

        # --------------------------------------------------
        # 6. Budget exceeded → deterministic fallback
        # --------------------------------------------------

        if not budget_decision.allowed:
            # Do not call Groq when the request is outside
            # the configured budget or rate limits.
            return self._fallback(
                context=context,
                template_key=template_key,
            )

        # --------------------------------------------------
        # 7. Execute AI request through GroqClient
        # --------------------------------------------------

        try:
            # Send only the sanitized prompt to Groq.
            result = self.groq_client.generate_result(
                task=task,
                messages=[
                    {
                        "role": "user",
                        "content": sanitized_prompt,
                    }
                ],
                context=sanitized_context,
            )

        except Exception:
            # Provider failures must not expose internal
            # provider details to the caller.
            #
            # Use the deterministic local fallback instead.
            return self._fallback(
                context=context,
                template_key=template_key,
            )

        # --------------------------------------------------
        # 8. Validate provider response
        # --------------------------------------------------

        # Extract the generated text.
        generated_text = result.text

        # Reject empty or invalid provider responses.
        if (
            not isinstance(generated_text, str)
            or not generated_text.strip()
        ):
            return self._fallback(
                context=context,
                template_key=template_key,
            )

        # --------------------------------------------------
        # 9. Restore PII locally
        # --------------------------------------------------

        try:
            # Groq only received placeholders.
            # Restore the original values locally after
            # generation has completed.
            restored_text = pii_sanitizer.restore_data(
                generated_text,
                placeholder_map,
            )

        except Exception:
            # If restoration fails, do not return partially
            # processed AI content.
            return self._fallback(
                context=context,
                template_key=template_key,
            )

        # --------------------------------------------------
        # 10. Format output according to channel
        # --------------------------------------------------

        try:
            # The current AI response is treated as the body.
            #
            # Channel-specific title/subject extraction can
            # be added later if the prompt contract requires it.
            rendered_title = None

            # Convert the AI text into the canonical
            # channel-specific output format.
            formatted_output = MessageOutputFormatter.format(
                channel=channel,
                rendered_title=rendered_title,
                rendered_body=restored_text,
                template_format="text",
            )

        except Exception:
            # If the generated content cannot satisfy the
            # canonical channel formatter, use fallback.
            return self._fallback(
                context=context,
                template_key=template_key,
            )

        # --------------------------------------------------
        # 11. Build CommunicationDecision
        # --------------------------------------------------

        try:
            # Convert the formatted channel-specific output
            # into the project's canonical communication model.
            decision = CommunicationDecision(
                channel=channel,
                output=formatted_output,
                tone="PROFESSIONAL",
                confidence=1.0,
            )

        except Exception:
            # Invalid structured output must not be returned.
            return self._fallback(
                context=context,
                template_key=template_key,
            )

        # --------------------------------------------------
        # 12. Run guardrails
        # --------------------------------------------------

        try:
            # Run all configured guardrail checks against
            # the generated CommunicationDecision.
            #
            # The pipeline checks whether the generated message
            # is safe and valid for the requested communication.
            guardrail_result = self.guardrail_pipeline.run(
                context=context,
                decision=decision,
            )

        except Exception:
            # If the guardrail pipeline itself fails,
            # fail safely and use the deterministic fallback.
            return self._fallback(
                context=context,
                template_key=template_key,
            )

        # --------------------------------------------------
        # 13. Guardrail failure → fallback
        # --------------------------------------------------

        if not guardrail_result.passed:
            # The guardrail pipeline did not allow the generated
            # communication to continue.
            #
            # Instead of returning unsafe AI output, use the
            # deterministic Jinja2 fallback.
            return self._fallback(
                context=context,
                template_key=template_key,
            )

        # --------------------------------------------------
        # 14. Apply reusable email presentation
        # --------------------------------------------------

        # All validations and guardrails have passed.
        #
        # The reusable email template is intentionally applied
        # AFTER guardrail validation. This keeps the guardrails
        # focused on the original generated communication content
        # instead of the HTML presentation layer.

        if channel == "EMAIL":
            try:
                renderer = EmailTemplateRenderer()

                rendered_body = renderer.render(
                    "transactional.html",
                    {
                        "email_title": (
                            decision.subject
                            or "FieldOps Notification"
                        ),
                        "email_heading": (
                            decision.subject
                            or "FieldOps Notification"
                        ),
                        "email_body": decision.message,
                    },
                )

                formatted_email = MessageOutputFormatter.format(
                    channel="EMAIL",
                    rendered_title=decision.subject,
                    rendered_body=rendered_body,
                    template_format="html",
                )

                decision = CommunicationDecision(
                    channel="EMAIL",
                    output=formatted_email,
                    tone=decision.tone,
                    confidence=decision.confidence,
                )

            except Exception:
                # If the reusable email presentation fails,
                # do not return partially formatted content.
                # Use the existing deterministic fallback.
                return self._fallback(
                    context=context,
                    template_key=template_key,
                )

        # --------------------------------------------------
        # 15. Return validated communication
        # --------------------------------------------------

        return decision

    def _fallback(
        self,
        *,
        context: CommunicationContext,
        template_key: str | None = None,
    ) -> GuardrailFallbackResult:
        """
        Render the approved deterministic fallback.

        The fallback service is responsible for selecting
        the safest available template.

        Selection order:
        1. Database template
        2. Built-in template
        3. Emergency template

        The template_key is accepted for compatibility with
        the generator workflow. The fallback service decides
        which approved template should actually be used.
        """

        return self.fallback_service.render(
            context=context,
        )