"""
fallback_service.py

Approved Jinja2 fallback rendering for FieldOps communication.

The service is used when:

- The external AI provider is unavailable
- The provider response cannot be parsed
- Generated communication fails the guardrail pipeline
- A required AI safety dependency fails closed

Rendering order
---------------
1. Active database template for the requested locale
2. Active database template for the base/English locale
3. Approved built-in FieldOps event template
4. Approved channel-specific emergency template

The service never:

- Calls an external AI provider
- Restores real PII values
- Sends a notification
- Commits or rolls back a database transaction
- Uses free-form additional_context in a template
"""

from __future__ import annotations

import re

from enum import StrEnum
from typing import Final

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)
from sqlalchemy.orm import Session
from app.services.template_engine import (
    render_managed_template,
    render_template_source,
    MessageTemplateLookupError,
    MessageTemplateRenderingError,
    MessageTemplateEngineError,
)

from app.services.ai.FieldOpsAI.services.prompt_locale_service import locale_candidates
import app.services.default_template as _default_template
from app.services.ai.FieldOpsAI.schemas.communication import (
    CommunicationContext,
    CommunicationDecision,
)

from app.services.email.email_template_renderer import (
    EmailTemplateRenderer,
)


# ==========================================================
# Fallback Result Contracts
# ==========================================================


class FallbackTemplateSource(StrEnum):
    """
    Origin of the approved fallback template.
    """

    DATABASE = "DATABASE"
    BUILTIN = "BUILTIN"
    EMERGENCY = "EMERGENCY"


class GuardrailFallbackResult(BaseModel):
    """
    Safe result returned after fallback rendering.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    decision: CommunicationDecision

    source: FallbackTemplateSource

    requested_locale: str = Field(
        min_length=2,
        max_length=10,
    )

    resolved_locale: str = Field(
        min_length=2,
        max_length=10,
    )

    template_id: int | None = None

    template_version: int | None = None


class GuardrailFallbackError(RuntimeError):
    """
    Raised only when no approved safe fallback can be built.
    """


# ==========================================================
# Fallback Service
# ==========================================================


class GuardrailFallbackService:
    """
    Render deterministic, approved fallback communication.
    """

    # ------------------------------------------------------
    # Allowed template variables
    # ------------------------------------------------------

    ALLOWED_TEMPLATE_VARIABLES: Final[
        frozenset[str]
    ] = frozenset(
        {
            "job_id",
            "notification_type",
            "recipient_type",
            "channel",
            "locale",
            "customer_name",
            "technician_name",
            "job_status",
            "job_title",
            "eta",
            "appointment_time",
            "sentiment",
        }
    )

    SAFE_OPTIONAL_DEFAULTS: Final[
        dict[str, dict[str, str]]
    ] = {
        "en": {
            "customer_name": "Customer",
            "technician_name": "Your technician",
            "job_title": "your service request",
            "eta": "not yet available",
            "appointment_time": "the scheduled time",
        },
        "es": {
            "customer_name": "Cliente",
            "technician_name": "Su técnico",
            "job_title": "su solicitud de servicio",
            "eta": "aún no disponible",
            "appointment_time": "la hora programada",
        },
        "ta": {
            "customer_name": "வாடிக்கையாளர்",
            "technician_name": "உங்கள் தொழில்நுட்பவியலாளர்",
            "job_title": "உங்கள் சேவை கோரிக்கை",
            "eta": "இன்னும் கிடைக்கவில்லை",
            "appointment_time": "திட்டமிடப்பட்ட நேரம்",
        },
        "hi": {
            "customer_name": "ग्राहक",
            "technician_name": "आपके तकनीशियन",
            "job_title": "आपका सेवा अनुरोध",
            "eta": "अभी उपलब्ध नहीं है",
            "appointment_time": "निर्धारित समय",
        }
    }

    # ------------------------------------------------------
    # Final emergency fallback
    # ------------------------------------------------------

    EMERGENCY_TEMPLATES: Final[
        dict[
            str,
            dict[str, str | None],
        ]
    ] = {
        "SMS": {
            "title": None,
            "body": (
                "Your FieldOps service request has an update. "
                "Please check the app."
            ),
        },

        "EMAIL": {
            "title": "FieldOps service update",
            "body": (
                "<p>"
                "Your FieldOps service request has an update. "
                "Please check the portal for details."
                "</p>"
            ),
        },

        "PUSH": {
            "title": "FieldOps update",
            "body": (
                "Your service request has a new update."
            ),
        },

        "IN_APP": {
            "title": "FieldOps update",
            "body": (
                "Your service request has a new update."
            ),
        },
    }

    INVALID_OUTPUT_TOKEN_PATTERN: Final[
        re.Pattern[str]
    ] = re.compile(
        r"\b(?:none|null|undefined)\b",
        re.IGNORECASE,
    )

    SMS_MAX_LENGTH: Final[int] = 160

    EMAIL_SUBJECT_MAX_LENGTH: Final[int] = 78

    PUSH_TITLE_MAX_LENGTH: Final[int] = 50

    # ------------------------------------------------------

    def __init__(
        self,
        *,
        db: Session,
        tenant_id:str,
    ) -> None:
        """
        Initialize the fallback service.

        Parameters
        ----------
        db
            Existing SQLAlchemy session used to retrieve
            approved NotificationTemplate records.
        """

        self._db = db
        self._tenant_id=tenant_id.strip()
        if not self._tenant_id:
            raise ValueError('tenant_id must not be empty')
    # ------------------------------------------------------

    def render(
        self,
        *,
        context: CommunicationContext,
    ) -> GuardrailFallbackResult:
        """
        Render the safest available fallback.

        Selection order:

        1. Database template
        2. Built-in event template
        3. Emergency template
        """
        # --------------------------------------------------
        # 1. Approved database template
        #
        # Pass the original requested locale to render_managed_template.
        # The registry and locale service perform exact → base → English
        # fallback internally and report the actual selected locale via
        # RenderedMessageResult.resolved_locale.
        # --------------------------------------------------

        try:
            tenant_id=self._tenant_id
            # tenant_id = (
            #     getattr(context, "tenant_id", None)
            #     or "**platform**"
            # )

            # Build an allowlisted rendering context — never pass the raw
            # model dump so that additional_context and other sensitive
            # fields cannot reach the template engine.
            ctx_dump = self._build_render_context(context)

            # Determine locale defaults: use base language when no exact
            # match exists in SAFE_OPTIONAL_DEFAULTS.
            locale_for_defaults = context.locale
            if locale_for_defaults not in self.SAFE_OPTIONAL_DEFAULTS:
                base = locale_for_defaults.split("-")[0]
                locale_for_defaults = base if base in self.SAFE_OPTIONAL_DEFAULTS else "en"

            defaults = self.SAFE_OPTIONAL_DEFAULTS[locale_for_defaults]
            for k, v in defaults.items():
                if ctx_dump.get(k) is None:
                    ctx_dump[k] = v

            res = render_managed_template(
                db=self._db,
                tenant_id=tenant_id,
                agent_type="CommsAgent",
                channel=context.channel.lower(),
                language=context.locale,
                status=context.job_status,
                context=ctx_dump,
                allowed_variable_paths=self.ALLOWED_TEMPLATE_VARIABLES,
            )

            # Only accept a real DB template, not the 'builtin_default' sentinel.
            # When the registry has no matching DB template, it returns a sentinel
            # with source='builtin_default'; we must fall through to step 2.
            if res.source in ("tenant", "platform"):
                decision = self._build_decision_from_res(res, context)
                if decision is not None:
                    src = FallbackTemplateSource.DATABASE
                    actual_locale = res.resolved_locale or context.locale
                    return GuardrailFallbackResult(
                        decision=decision,
                        source=src,
                        requested_locale=context.locale,
                        resolved_locale=actual_locale,
                        template_id=res.template_id,
                        template_version=res.template_version,
                    )

        except MessageTemplateEngineError:
            pass

        # --------------------------------------------------
        # 2. Approved built-in event template
        # --------------------------------------------------

        builtin_result = self._get_builtin_template(
            context=context
        )

        if builtin_result is not None:
            builtin, builtin_locale = builtin_result
            decision = self._try_build_decision_builtin(
                context=context,
                title_template=builtin["title"],
                body_template=builtin["body"],
                resolved_locale=builtin_locale,
            )

            if decision is not None:
                return GuardrailFallbackResult(
                    decision=decision,
                    source=FallbackTemplateSource.BUILTIN,
                    requested_locale=context.locale,
                    resolved_locale=builtin_locale,
                )

        # --------------------------------------------------
        # 3. Approved emergency template
        # --------------------------------------------------

        emergency = self.EMERGENCY_TEMPLATES.get(
            context.channel
        )

        if emergency is None:
            raise GuardrailFallbackError(
                "No approved fallback is configured for "
                "the communication channel."
            )

        decision = self._try_build_decision_builtin(
            context=context,
            title_template=emergency["title"],
            body_template=emergency["body"],
            resolved_locale="en",
        )

        if decision is None:
            raise GuardrailFallbackError(
                "Approved emergency fallback could not be "
                "rendered."
            )

        return GuardrailFallbackResult(
            decision=decision,
            source=FallbackTemplateSource.EMERGENCY,
            requested_locale=context.locale,
            resolved_locale="en",
        )

    def _build_decision_from_res(
        self,
        result,
        context: CommunicationContext,
    ):
        from app.services.ai.FieldOpsAI.services.message_output_formatter import (
            MessageOutputFormatter,
        )

        try:
            format_channel = (
                "PORTAL"
                if context.channel == "IN_APP"
                else context.channel
            )

            template_format = getattr(
                result,
                "template_format",
                "text",
            )

            # --------------------------------------------------
            # EMAIL
            #
            # Wrap the already-approved transactional content
            # with the reusable FieldOps email template system.
            # --------------------------------------------------

            if context.channel == "EMAIL":
                renderer = EmailTemplateRenderer()

                rendered_body = renderer.render(
                    "transactional.html",
                    {
                        "email_title": (
                            result.title
                            or "FieldOps Notification"
                        ),
                        "email_heading": (
                            result.title
                            or "FieldOps Notification"
                        ),
                        "email_body": result.body,
                    },
                )

                output = MessageOutputFormatter.format(
                    channel=format_channel,
                    rendered_title=result.title,
                    rendered_body=rendered_body,
                    template_format="html",
                )

            # --------------------------------------------------
            # NON-EMAIL CHANNELS
            #
            # Preserve the existing behavior for SMS, PUSH,
            # and IN_APP/PORTAL communications.
            # --------------------------------------------------

            else:
                output = MessageOutputFormatter.format(
                    channel=format_channel,
                    rendered_title=result.title,
                    rendered_body=result.body,
                    template_format=template_format,
                )

            # --------------------------------------------------
            # Build canonical communication decision.
            # --------------------------------------------------

            decision = CommunicationDecision(
                channel=context.channel,
                output=output,
                tone="PROFESSIONAL",
                confidence=1.0,
            )

            # --------------------------------------------------
            # Existing output validation.
            # --------------------------------------------------

            if self.INVALID_OUTPUT_TOKEN_PATTERN.search(
                decision.message
            ):
                return None

            if (
                decision.title
                and self.INVALID_OUTPUT_TOKEN_PATTERN.search(
                    decision.title
                )
            ):
                return None

            if (
                decision.subject
                and self.INVALID_OUTPUT_TOKEN_PATTERN.search(
                    decision.subject
                )
            ):
                return None

            if not self._within_channel_limits(decision):
                return None

            return decision

        except ValueError:
            return None

    def _try_build_decision_builtin(
        self,
        *,
        context: CommunicationContext,
        title_template: str | None,
        body_template: str,
        resolved_locale: str = "en",
    ) -> CommunicationDecision | None:
        """
        Attempt to render an approved built-in template.

        Inference failures (unsafe or invalid syntax) propagate
        as errors and cause this candidate to be skipped so the
        service continues to the emergency template.

        Exception text is never printed or logged.
        """
        from app.services.template_engine import (
            infer_template_declarations,
            UnsupportedTemplateFormatError,
        )
        from app.services.ai.FieldOpsAI.schemas.prompt_variable import PromptVariableDefinition
        from app.services.ai.FieldOpsAI.services.prompt_variable_injector import (
            PromptVariableInjectionError,
        )

        try:
            render_context = self._build_render_context(context)

            # Infer declarations from the built-in template.
            # Do NOT swallow inference failure: an unsafe or invalid
            # built-in template must skip this candidate.
            try:
                paths = infer_template_declarations(body=body_template, title=title_template)
            except (MessageTemplateEngineError, PromptVariableInjectionError):
                # Propagate as a rendering error so the outer except
                # handler skips this candidate.
                raise MessageTemplateRenderingError(
                    "Built-in template inference failed."
                )

            # Determine locale defaults using the resolved locale.
            base_for_defaults = resolved_locale.split("-")[0]
            locale_defaults = self.SAFE_OPTIONAL_DEFAULTS.get(
                resolved_locale,
                self.SAFE_OPTIONAL_DEFAULTS.get(
                    base_for_defaults,
                    self.SAFE_OPTIONAL_DEFAULTS["en"],
                )
            )

            variables = []
            seen_roots: set[str] = set()

            for path in paths:
                # Validate the exact path — never collapse nested names.
                root = path.split(".")[0]

                if root not in self.ALLOWED_TEMPLATE_VARIABLES:
                    # Path is not allowlisted — reject this candidate.
                    raise MessageTemplateRenderingError(
                        "Built-in template uses disallowed variable."
                    )

                # Avoid duplicate declarations when several nested paths
                # share the same simple root (e.g. customer.name and
                # customer.address both start with customer).
                if path in seen_roots:
                    continue
                seen_roots.add(path)

                # Look up defaults using the exact path first, then root.
                if path in locale_defaults:
                    variables.append(
                        PromptVariableDefinition(
                            name=path,
                            required=False,
                            default=locale_defaults[path],
                        )
                    )
                elif root in locale_defaults:
                    variables.append(
                        PromptVariableDefinition(
                            name=path,
                            required=False,
                            default=locale_defaults[root],
                        )
                    )
                else:
                    variables.append(
                        PromptVariableDefinition(
                            name=path,
                            required=True,
                        )
                    )

            res = render_template_source(
                body=body_template,
                title=title_template,
                variables=variables,
                context=render_context,
                format="html" if context.channel == "EMAIL" else "text"
            )

            return self._build_decision_from_res(res, context)

        except (MessageTemplateEngineError, PromptVariableInjectionError):
            # A typed rendering failure means this candidate cannot be
            # used. Return None so fallback selection continues.
            # Exception text is never printed or logged.
            return None



    # ======================================================
    # Built-in Template Selection
    # ======================================================

    @staticmethod
    def _get_builtin_template(
        *,
        context: CommunicationContext,
    ) -> tuple[
        dict[str, str | None],
        str
    ] | None:
        """
        Return an approved built-in event template.

        Built-in templates come from:

        app/services/default_template.py
        """
        from app.services.ai.FieldOpsAI.schemas.prompt_template import (
            normalize_template_status,
            UnsupportedTemplateStatusError,
            STATUS_LOOKUP_CANDIDATES,
        )

        try:
            canon_enum = normalize_template_status(context.job_status)
            canon_status = canon_enum.value if hasattr(canon_enum, "value") else str(canon_enum)
        except UnsupportedTemplateStatusError:
            return None

        status_candidates = STATUS_LOOKUP_CANDIDATES.get(canon_enum, (canon_status,))

        candidates = locale_candidates(context.locale)

        for cand in candidates:
            # Access the catalog at call-time so monkeypatching works in tests.
            catalog = _default_template.LOCALIZED_NOTIFICATION_TYPES.get(cand)
            if catalog is None:
                continue

            event_template = None
            for status_cand in status_candidates:
                if status_cand in catalog:
                    event_template = catalog[status_cand]
                    break

            if event_template is None:
                continue

            body = event_template.get(
                context.channel.lower()
            )

            if (
                not isinstance(
                    body,
                    str,
                )
                or not body.strip()
            ):
                continue

            title: str | None = None

            if context.channel in {
                "EMAIL",
                "PUSH",
                "IN_APP",
            }:
                candidate_title = event_template.get(
                    "title"
                )

                if isinstance(
                    candidate_title,
                    str,
                ):
                    title = candidate_title

            return {
                "title": title,
                "body": body,
            }, cand

        return None



    # ======================================================
    # Safe Template Context (allowlisted)
    # ======================================================

    def _build_render_context(
        self,
        context: CommunicationContext,
    ) -> dict[str, object]:
        """
        Build a null-safe, allow-listed rendering context.

        Only the 12 explicitly approved fields are included.
        Fields such as additional_context, correlation internals,
        tenant authentication metadata, recipient addresses,
        phone numbers, provider data, and unknown model extras
        are never passed to the template engine.
        """
        raw = context.model_dump(mode="python")

        return {
            key: raw.get(key)
            for key in self.ALLOWED_TEMPLATE_VARIABLES
        }

    # ======================================================
    # Channel Limits
    # ======================================================

    @classmethod
    def _within_channel_limits(
        cls,
        decision: CommunicationDecision,
    ) -> bool:
        """
        Ensure the fallback itself respects hard channel limits.
        """

        if decision.channel == "SMS":
            return (
                len(
                    decision.message
                )
                <= cls.SMS_MAX_LENGTH
            )

        if decision.channel == "EMAIL":
            return (
                decision.subject is not None
                and len(
                    decision.subject
                )
                <= cls.EMAIL_SUBJECT_MAX_LENGTH
            )

        if decision.channel == "PUSH":
            return (
                decision.title is not None
                and len(
                    decision.title
                )
                <= cls.PUSH_TITLE_MAX_LENGTH
            )

        return True
