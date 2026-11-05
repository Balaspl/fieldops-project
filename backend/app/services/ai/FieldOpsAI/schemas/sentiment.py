"""
sentiment.py

Pydantic schemas representing the Sentiment Agent.

The Sentiment Agent analyzes customer communication
and returns structured information.

The backend uses this information to determine
priority, escalation, and communication tone.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


# ==========================================================
# Context
# ==========================================================


class SentimentContext(BaseModel):
    """
    Context provided to the Sentiment Agent.
    """

    channel: Literal[
        "EMAIL",
        "SMS",
        "CHAT",
        "WHATSAPP",
        "PORTAL",
        "SUPPORT_TICKET",
        "DISPATCH_NOTE",
        "JOB_CHAT",
        "SUPPORT_CHAT",
        "JOB_FEEDBACK",
        "SUPPORT_CASE",
    ] = Field(
        ...,
        description="Source of the customer communication."
    )

    message: str = Field(
        ...,
        min_length=1,
        description="Customer communication."
    )
    language: Literal[
        "en",
        "es",
        "ta",
        "hi",
    ] = Field(
        default="en",
        description="Language of the customer communication."
    )

    previous_messages: list[str] = Field(
        default_factory=list,
        max_length=3,
        description=(
            "Previous messages from the conversation thread. "
            "Only the last 3 messages should be provided."
        ),
    )

# ==========================================================
# AI Decision
# ==========================================================


class SentimentDecision(BaseModel):
    """
    Structured AI sentiment analysis.
    """

    sentiment: Literal[
        "POSITIVE",
        "NEUTRAL",
        "NEGATIVE",
        "MIXED",
    ] = Field(
        ...,
        description="Overall customer sentiment."
    )

    emotion: Literal[
        "CALM",
        "HAPPY",
        "SATISFIED",
        "CONFUSED",
        "CONCERNED",
        "FRUSTRATED",
        "ANGRY",
        "DISAPPOINTED",
        "ANXIOUS",
    ] = Field(
        ...,
        description="Primary customer emotion."
    )

    urgency: Literal[
        "LOW",
        "MEDIUM",
        "HIGH",
        "CRITICAL",
    ] = Field(
        ...,
        description="Business urgency level."
    )

    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = Field(
        default="LOW", description="Impact severity, separate from time urgency."
    )

    issue_categories: list[Literal[
        "TECHNICIAN_DELAY",
        "TECHNICIAN_BEHAVIOR",
        "SERVICE_QUALITY",
        "COMMUNICATION",
        "SCHEDULING",
        "PRICING_BILLING",
        "UNRESOLVED_ISSUE",
        "SAFETY",
        "GENERAL_FEEDBACK",
        "OTHER",
    ]] = Field(default_factory=list, max_length=5)

    requires_human: bool = Field(
        ...,
        description="Whether human intervention is recommended."
    )

    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="AI confidence score."
    )

    summary: Optional[str] = Field(
        default=None,
        min_length=10,
        description="Short factual summary of the customer's message."
    )

    recommended_action: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Suggested next step for a human operator; never execute automatically.",
    )
