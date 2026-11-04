"""
communication.py

Pydantic schemas for the FieldOps Communication Agent.

The Communication Agent generates recipient-facing content for:

- Email
- SMS
- Push notifications
- In-app notifications

The agent only generates content.

It never:

- Sends notifications
- Updates the database
- Changes job status
- Assigns technicians
- Promises unsupported business actions
"""

from __future__ import annotations

from typing import Any, Literal, Self, Annotated
from enum import Enum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
    field_validator,
    model_serializer,
)
from app.services.ai.FieldOpsAI.services.prompt_locale_service import normalize_locale, InvalidLocaleError


# ==========================================================
# Shared Types
# ==========================================================


CommunicationChannel = Literal[
    "EMAIL",
    "SMS",
    "PUSH",
    "IN_APP",
]


class CommunicationRecipient(str, Enum):
    CUSTOMER = "CUSTOMER"
    TECHNICIAN = "TECHNICIAN"
    DISPATCHER = "DISPATCHER"
    MANAGER = "MANAGER"
    SYSTEM = "SYSTEM"


CommunicationTone = Literal[
    "PROFESSIONAL",
    "FRIENDLY",
    "EMPATHETIC",
    "URGENT",
]


CustomerSentiment = Literal[
    "POSITIVE",
    "NEUTRAL",
    "NEGATIVE",
]


JobStatus = Literal[
    "CREATED",
    "ASSIGNED",
    "EN_ROUTE",
    "ON_SITE",
    "WORK_IN_PROGRESS",
    "COMPLETED",
    "CANCELLED",
]


# ==========================================================
# Communication Context
# ==========================================================


class CommunicationContext(BaseModel):
    """
    Validated information provided to the Communication Agent.

    This schema defines exactly what the Communication Agent
    is allowed to receive from the business-service layer.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    job_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description=(
            "FieldOps job identifier. It is sanitized before "
            "being sent to an external AI provider."
        ),
    )

    correlation_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description=(
            "Correlation ID used to trace the complete "
            "communication workflow."
        ),
    )

    notification_type: str = Field(
        ...,
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9_]+$",
        description=(
            "Notification/template event type, such as "
            "job_assigned or technician_en_route."
        ),
        examples=[
            "job_assigned",
            "technician_en_route",
        ],
    )

    recipient_type: CommunicationRecipient = Field(
        ...,
        description=(
            "Type of recipient receiving the communication."
        ),
    )

    channel: CommunicationChannel = Field(
        ...,
        description="Requested delivery channel.",
    )

    locale: str = Field(
        default="en",
        description=(
            "Requested locale, such as en or en-US."
        ),
    )

    @field_validator("locale", mode="before")
    @classmethod
    def normalize_request_locale(cls, v: Any) -> str:
        if not v or not str(v).strip():
            return "en"
        try:
            return normalize_locale(str(v))
        except InvalidLocaleError:
            raise ValueError("Invalid or unsupported locale.")
    
    customer_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Customer identifier used for preference lookup.",
    )

    customer_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=150,
        description="Customer name when available.",
    )

    technician_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=150,
        description="Assigned technician name when available.",
    )

    job_status: JobStatus = Field(
        ...,
        description="Current FieldOps job status.",
    )

    job_title: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="Customer-readable service or job title.",
    )

    eta: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description=(
            "Estimated arrival time supplied by the backend."
        ),
    )

    appointment_time: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description=(
            "Scheduled appointment time supplied by the backend."
        ),
    )

    sentiment: CustomerSentiment = Field(
        default="NEUTRAL",
        description="Current customer sentiment.",
    )

    additional_context: str | None = Field(
        default=None,
        min_length=1,
        max_length=2000,
        description=(
            "Optional approved business context. "
            "This must not contain instructions that override "
            "system or business rules."
        ),
    )
    template: str | None = Field(
        default=None,
        min_length=1,
        max_length=5000,
        description="Optional Jinja2 personalization template.",
    )

    personalization_data: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Customer, job, technician and other data "
            "used for message personalization."
        ),
    )


class AgentCommunicationRequest(BaseModel):
    """Typed internal contract for another FieldOps agent to request copy.

    This carries no authority to change jobs or choose arbitrary recipients;
    the calling business service supplies a validated CommunicationContext.
    Delivery remains the responsibility of the existing channel layer.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    requester_agent: Literal[
        "SENTIMENT_AGENT",
        "SUPPORT_AGENT",
        "SCHEDULING_AGENT",
        "DISPATCH_AGENT",
        "SLA_AGENT",
    ]
    request_id: str = Field(min_length=1, max_length=100)
    context: CommunicationContext

    @model_validator(mode="after")
    def validate_context(self) -> Self:
        if self.context.recipient_type == CommunicationRecipient.SYSTEM:
            raise ValueError("Agent communication requests need a human recipient.")
        if (
            self.context.correlation_id
            and self.context.correlation_id != self.request_id
        ):
            raise ValueError("Request ID and context correlation ID must match.")
        return self


# ==========================================================
# Communication Output Schemas
# ==========================================================

class SMSMessageOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    channel: Literal["SMS"] = "SMS"
    text: str

class EmailMessageOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    channel: Literal["EMAIL"] = "EMAIL"
    subject: str
    text_body: str
    html_body: str | None = None
    mime_message: str | None = Field(default=None, exclude=True)


class MessageAction(BaseModel):
    """A client-renderable action associated with a notification."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    label: str
    action: str


class PushMessageOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    channel: Literal["PUSH"] = "PUSH"
    title: str
    body: str
    actions: tuple[MessageAction, ...] = ()

class PortalMessageOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    channel: Literal["PORTAL"] = "PORTAL"
    title: str | None = None
    body: str
    content_format: Literal["text", "html"] = "text"
    actions: tuple[MessageAction, ...] = ()
    payload: dict[str, Any] = Field(default_factory=dict)

FormattedCommunicationOutput = Annotated[
    SMSMessageOutput
    | EmailMessageOutput
    | PushMessageOutput
    | PortalMessageOutput,
    Field(discriminator="channel"),
]


def output_text_for_validation(output: FormattedCommunicationOutput) -> str:
    """Deterministic projection of the channel output for guardrail validation."""
    if output.channel == "SMS":
        return output.text
    elif output.channel == "EMAIL":
        return f"{output.subject}\n{output.text_body}".strip()
    elif output.channel == "PUSH":
        return f"{output.title}\n{output.body}".strip()
    elif output.channel == "PORTAL":
        parts = []
        if getattr(output, "title", None):
            parts.append(output.title) # type: ignore
        parts.append(output.body)
        return "\n".join(parts).strip()
    return ""


# ==========================================================
# Communication Decision
# ==========================================================


class CommunicationDecision(BaseModel):
    """
    Structured content generated by the Communication Agent.

    Maximum channel lengths are deliberately not enforced in
    this schema.LengthValidator will perform those
    guardrail checks and trigger Jinja2 fallback when violated.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    channel: CommunicationChannel = Field(
        ...,
        description=(
            "Communication channel. It must match the requested "
            "channel in CommunicationContext."
        ),
    )

    output: FormattedCommunicationOutput = Field(
        ...,
        description="The strict canonical formatted output for the channel.",
    )

    tone: CommunicationTone = Field(
        ...,
        description="Tone used by the generated content.",
    )

    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="AI confidence score.",
    )

    @property
    def message(self) -> str:
        """Legacy accessor for message body."""
        if self.channel == "SMS":
            return self.output.text
        elif self.channel == "EMAIL":
            return self.output.html_body if self.output.html_body else self.output.text_body
        else:
            return self.output.body

    @property
    def title(self) -> str | None:
        """Legacy accessor for message title."""
        if self.channel == "PUSH":
            return self.output.title
        elif self.channel in ("IN_APP", "PORTAL"):
            return getattr(self.output, "title", None)
        return None

    @property
    def subject(self) -> str | None:
        """Legacy accessor for message subject."""
        if self.channel == "EMAIL":
            return getattr(self.output, "subject", None)
        return None

    # ------------------------------------------------------

    @model_validator(mode="before")
    @classmethod
    def validate_legacy_fields_and_format(cls, data: Any) -> Any:
        """
        AI compatibility boundary. Validates legacy fields and formats output
        if the canonical output field is missing.
        """
        if not isinstance(data, dict):
            return data

        if "output" in data:
            return data
            
        channel = data.get("channel")
        if not channel:
            return data
            
        title = data.get("title")
        subject = data.get("subject")
        message = data.get("message")
        
        # Enforce legacy channel bounds to pass existing tests
        if channel == "EMAIL":
            if not subject:
                raise ValueError("EMAIL communication requires subject")
            if title is not None:
                raise ValueError("EMAIL communication must not include title")
        elif channel == "SMS":
            if title is not None:
                raise ValueError("SMS communication must not include title")
            if subject is not None:
                raise ValueError("SMS communication must not include subject")
        elif channel == "PUSH":
            if not title:
                raise ValueError("PUSH communication requires title")
            if subject is not None:
                raise ValueError("PUSH communication must not include subject")
        elif channel == "IN_APP":
            if subject is not None:
                raise ValueError("IN_APP communication must not include subject")
        
        # Determine rendered_title from legacy subject or title
        rendered_title = subject if channel == "EMAIL" else title
        rendered_body = message
        
        # Remove legacy fields so Pydantic doesn't see them as extra forbidden inputs
        data.pop("title", None)
        data.pop("subject", None)
        data.pop("message", None)

        if rendered_body is None:
            # Let the standard pydantic validation catch missing required fields
            return data

        # Avoid circular import by importing here
        from app.services.ai.FieldOpsAI.services.message_output_formatter import MessageOutputFormatter
        
        # Map IN_APP to PORTAL for output formatting
        format_channel = "PORTAL" if channel == "IN_APP" else channel

        try:
            data["output"] = MessageOutputFormatter.format(
                channel=format_channel,
                rendered_title=rendered_title,
                rendered_body=rendered_body,
                template_format="text" # AI outputs are text right now unless specified
            )
        except Exception as e:
            raise ValueError(f"Failed to format message output: {str(e)}")
            
        return data
