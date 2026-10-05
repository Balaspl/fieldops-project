"""
agent_messages.py

Standard message contracts for communication between AI agents.

Purpose
-------
This module defines the formal communication protocol used by
FieldOps Commander AI agents.

Every inter-agent communication must be wrapped inside a
MessageEnvelope and validated using Pydantic before processing.

Goals
-----
- Type-safe messaging
- Standardized communication
- JSON serialization
- Schema validation
- Versioned contracts
- Future compatibility
- Tenant isolation
- Privacy-safe payloads

These schemas are transport-agnostic and may be used with:

- Redis Pub/Sub
- Celery
- Kafka
- RabbitMQ
- HTTP
- gRPC
"""

from __future__ import annotations

import copy
import re
import math
from datetime import UTC, datetime
from enum import Enum
from typing import Any, ClassVar, Dict, Optional
from uuid import uuid4

from pydantic import (
    UUID4,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.context import correlation_id_ctx


# ==========================================================
# Privacy constants
# ==========================================================

_FORBIDDEN_KEYS: frozenset[str] = frozenset({
    "api_key",
    "secret",
    "password",
    "token",
    "auth_token",
    "authorization",
    "prompt",
    "system_prompt",
    "provider_response",
    "raw_response",
    "customer_name",
    "customer_address",
    "customer_email",
    "customer_phone",
    "phone_number",
    "gps",
    "latitude",
    "longitude",
    "coordinates",
})

# Topic validation pattern: letters, digits, dots, underscores, hyphens
_TOPIC_PATTERN = re.compile(r"^[a-z0-9._-]+$")


# ==========================================================
# Helpers
# ==========================================================


def _resolve_default_correlation_id() -> str:
    """
    Return the current request correlation ID if one is active,
    otherwise generate a fresh UUID4.

    Explicit correlation IDs passed to the envelope always take
    precedence over this default.
    """
    existing = correlation_id_ctx.get()
    if isinstance(existing, str):
        existing = existing.strip()
        if existing:
            return existing
    return str(uuid4())


def _validate_topic(value: Any) -> str:
    """
    Strip, normalize to lowercase, and validate a topic string.

    Allowed characters: letters, digits, dots, underscores, hyphens.
    Raises ValueError when the topic is blank or contains invalid chars.
    """
    if not isinstance(value, str):
        raise TypeError("topic must be a string.")
    value = value.strip().lower()
    if not value:
        raise ValueError("topic must not be blank.")
    if len(value) > 100:
        raise ValueError("topic must be at most 100 characters.")
    if not _TOPIC_PATTERN.fullmatch(value):
        raise ValueError(
            f"topic {value!r} contains invalid characters. "
            "Allowed: letters, digits, dots, underscores, hyphens."
        )
    return value


def _validate_json_and_privacy(
    data: Any,
    path: str = "",
    allow_gps_coordinates: bool = False,
) -> None:
    """
    Recursively validate that data is JSON-compatible and contains
    no forbidden sensitive keys.

    JSON-compatible types: dict, list, str, int, float, bool, None.
    Bool is intentionally allowed (JSON true/false).

    Raises ValueError for:
    - Non-JSON-compatible values.
    - Forbidden key names (checked case-insensitively, path reported).
    - Never logs or exposes the value associated with the forbidden key.
    """
    if isinstance(data, dict):
        for key, val in data.items():
            if not isinstance(key, str):
                raise ValueError(
                    f"Payload/metadata keys must be strings; "
                    f"got {type(key).__name__!r} at {path!r}."
                )
            key_path = f"{path}.{key}" if path else key
            if (
                key.lower() in _FORBIDDEN_KEYS
                and not (
                    allow_gps_coordinates
                    and key.lower() in {"latitude", "longitude"}
                )
            ):
                raise ValueError(
                    f"Forbidden sensitive key {key!r} found at path {key_path!r}. "
                    "This key is not permitted in message payloads or metadata."
                )
            _validate_json_and_privacy(
                val,
                path=key_path,
                allow_gps_coordinates=allow_gps_coordinates,
            )
    elif isinstance(data, float):
        if not math.isfinite(data):
            raise ValueError(
                f"Payload/metadata float at {path!r} "
                "must be finite for JSON compatibility."
            )

    elif data is None or isinstance(
        data,
        (bool, int, str),
    ):
        pass
    else:
        raise ValueError(
            f"Payload/metadata values must be JSON-compatible "
            f"(dict, list, str, int, float, bool, or None); "
            f"got {type(data).__name__!r} at {path!r}."
        )


# ==========================================================
# Message Types
# ==========================================================


class MessageType(str, Enum):
    """
    Supported AI message types.
    """

    COMMAND = "COMMAND"

    QUERY = "QUERY"

    EVENT = "EVENT"

    RESPONSE = "RESPONSE"

    ERROR = "ERROR"


# ==========================================================
# Agent Address
# ==========================================================


class AgentAddress(BaseModel):
    """
    Unique address of an AI agent.

    Format
    ------
    agent_type:agent_id:tenant_id

    Example
    -------
    planning:planner-01:tenant-001

    Validation
    ----------
    - All fields must be non-blank strings.
    - No field may contain ':' (reserved as address separator).
    - agent_type is normalized to lowercase and validated against
      known AITask values.
    - tenant_id maximum length is 50.
    - agent_type and agent_id maximum length is 100.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        str_strip_whitespace=True,
    )

    agent_type: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Agent type (planning, dispatch, monitoring, etc.)",
        examples=["planning"],
    )

    agent_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Unique agent identifier.",
        examples=["planner-01"],
    )

    tenant_id: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Tenant identifier.",
        examples=["tenant-001"],
    )

    @field_validator("agent_type", mode="before")
    @classmethod
    def normalize_agent_type(cls, value: str) -> str:
        """
        Strip whitespace and normalize agent_type to lowercase.
        """
        if not isinstance(value, str):
            raise ValueError("agent_type must be a string.")
        return value.strip().lower()

    @field_validator("agent_id", "tenant_id", mode="before")
    @classmethod
    def strip_address_fields(cls, value: str) -> str:
        """
        Strip surrounding whitespace from agent_id and tenant_id.
        """
        if not isinstance(value, str):
            raise ValueError("Address fields must be strings.")
        return value.strip()

    @field_validator("agent_type", "agent_id", "tenant_id", mode="after")
    @classmethod
    def validate_not_empty(cls, value: str) -> str:
        """
        Ensure address fields are not blank and do not contain ':'.
        """
        if not value:
            raise ValueError("Address fields cannot be empty.")

        if ":" in value:
            raise ValueError("Address fields cannot contain ':'.")

        return value

    @field_validator("agent_type", mode="after")
    @classmethod
    def validate_agent_type_known(cls, value: str) -> str:
        """
        Validate agent_type against known AITask values.

        Import is deferred to avoid circular imports at module load.
        """
        from app.services.ai.FieldOpsAI.schemas.ai_task import AITask

        known = {task.value for task in AITask}
        if value not in known:
            raise ValueError(
                f"agent_type {value!r} is not a known AITask value. "
                f"Known values: {sorted(known)!r}."
            )
        return value

    @property
    def task(self):
        """
        Return the AITask enum member corresponding to this agent_type.
        """
        from app.services.ai.FieldOpsAI.schemas.ai_task import AITask
        return AITask(self.agent_type)

    @property
    def address(self) -> str:
        """
        Return the canonical address string.
        """
        return (
            f"{self.agent_type}:"
            f"{self.agent_id}:"
            f"{self.tenant_id}"
        )

    def __str__(self) -> str:
        return self.address


# ==========================================================
# Message Envelope
# ==========================================================


class MessageEnvelope(BaseModel):
    """
    Standard envelope that wraps every AI message.

    Every communication between AI agents must include:

    - Sender
    - Message Type
    - Payload
    - Timestamp
    - Correlation ID
    - Contract Version

    Recipient is optional. When None, the message is a broadcast.
    When set to an AgentAddress, the message targets that agent exactly.

    Privacy
    -------
    Payload and metadata are deep-copied on construction and validated
    recursively for JSON compatibility and forbidden sensitive keys.
    They are never logged.

    Tenant consistency
    ------------------
    When recipient is supplied, its tenant_id must match sender.tenant_id.
    Cross-tenant envelopes are rejected during model validation.
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_default=True,
    )

    # GPS coordinates are sensitive by default. Only a dedicated
    # GPS event message may opt in to carrying latitude/longitude.
    allow_gps_coordinates: ClassVar[bool] = False

    message_id: UUID4 = Field(
        default_factory=uuid4,
        description="Unique UUID4 identifier for this message.",
    )

    sender: AgentAddress = Field(
        ...,
        description="Originating AI agent.",
    )

    recipient: Optional[AgentAddress] = Field(
        default=None,
        description=(
            "Destination AI agent. "
            "None represents a broadcast message."
        ),
    )

    message_type: MessageType = Field(
        ...,
        description="Communication type.",
    )

    payload: Dict[str, Any] = Field(
        default_factory=dict,
        description="Message payload.",
    )

    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp when the message was created.",
    )

    correlation_id: str = Field(
        default_factory=_resolve_default_correlation_id,
        max_length=100,
        description="Unique identifier used to correlate requests and responses.",
    )

    contract_version: str = Field(
        default="1.0",
        max_length=20,
        description="Communication contract version.",
    )

    timeout_seconds: float | None = Field(
        default=None,
        description=(
            "Optional timeout in seconds. "
            "Fractional values such as 0.5 are supported. "
            "Maximum is 30 seconds."
        ),
        examples=[5.0],
    )

    topic: str = Field(
        default="agent.message",
        min_length=1,
        max_length=100,
        description="Message routing topic.",
    )

    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Optional non-sensitive message metadata.",
    )

    @field_validator("timestamp", mode="after")
    @classmethod
    def validate_timestamp_aware(cls, value: datetime) -> datetime:
        """
        Reject naive datetimes.
        """
        if value.tzinfo is None:
            raise ValueError(
                "timestamp must be timezone-aware. "
                "Use datetime.now(UTC) or attach tzinfo."
            )
        return value

    @field_validator("correlation_id", mode="before")
    @classmethod
    def validate_correlation_id(cls, value: Any) -> str:
        """
        Strip and validate correlation_id is non-blank.
        """
        if not isinstance(value, str):
            raise ValueError("correlation_id must be a string.")
        value = value.strip()
        if not value:
            raise ValueError("correlation_id must not be blank.")
        return value

    @field_validator("contract_version", mode="before")
    @classmethod
    def validate_contract_version(cls, value: Any) -> str:
        """
        Validate contract_version is non-blank.
        """
        if not isinstance(value, str):
            raise ValueError("contract_version must be a string.")
        value = value.strip()
        if not value:
            raise ValueError("contract_version must not be blank.")
        return value

    @field_validator("timeout_seconds", mode="before")
    @classmethod
    def validate_timeout(cls, value: Any) -> Any:
        """
        Reject bool timeout values and enforce 0 < timeout <= 30.
        """
        if value is None:
            return value
        if isinstance(value, bool):
            raise ValueError(
                "timeout_seconds must be a numeric value, not bool."
            )
        if not isinstance(value, (int, float)):
            raise ValueError(
                "timeout_seconds must be a number (int or float)."
            )
        if value <= 0:
            raise ValueError("timeout_seconds must be greater than zero.")
        if value > 30:
            raise ValueError(
                f"timeout_seconds {value!r} exceeds maximum of 30 seconds."
            )
        return float(value)

    @field_validator("topic", mode="before")
    @classmethod
    def validate_topic(cls, value: Any) -> str:
        """
        Strip, normalize to lowercase, and validate the topic.
        """
        return _validate_topic(value)

    @field_validator("payload", mode="before")
    @classmethod
    def deep_copy_and_validate_payload(cls, value: Any) -> Any:
        """
        Deep-copy and validate payload for JSON compatibility and privacy.
        """
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("payload must be a dictionary.")
        value = copy.deepcopy(value)
        _validate_json_and_privacy(
            value,
            path="payload",
            allow_gps_coordinates=cls.allow_gps_coordinates,
        )
        return value

    @field_validator("metadata", mode="before")
    @classmethod
    def deep_copy_and_validate_metadata(cls, value: Any) -> Any:
        """
        Deep-copy and validate metadata for JSON compatibility and privacy.
        """
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("metadata must be a dictionary.")
        value = copy.deepcopy(value)
        _validate_json_and_privacy(value, path="metadata")
        return value

    @model_validator(mode="after")
    def validate_cross_tenant(self) -> "MessageEnvelope":
        """
        When recipient is set, require sender and recipient to share
        the same tenant_id.
        """
        if self.recipient is not None:
            if self.sender.tenant_id != self.recipient.tenant_id:
                raise ValueError(
                    "Cross-tenant messages are not allowed. "
                    f"sender.tenant_id={self.sender.tenant_id!r} "
                    f"!= recipient.tenant_id={self.recipient.tenant_id!r}."
                )
        return self

    @property
    def tenant_id(self) -> str:
        """
        Return the tenant that owns this message (derived from sender).
        """
        return self.sender.tenant_id

    @property
    def created_at(self) -> datetime:
        """
        Alias for timestamp. Allows bus internals to use created_at
        terminology while preserving the serialized field name.
        """
        return self.timestamp


# ==========================================================
# Base Message
# ==========================================================


class BaseMessage(MessageEnvelope):
    """
    Base class for every AI message.

    Specialized message types inherit from this class.

    This avoids duplication while ensuring all
    communications follow the same contract.
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_default=True,
    )

    def to_json(self) -> str:
        """
        Serialize the message into JSON.
        """

        return self.model_dump_json(
            indent=2,
        )

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize the message into a dictionary.
        """

        return self.model_dump()

    @classmethod
    def from_dict(
        cls,
        data: Dict[str, Any],
    ) -> "BaseMessage":
        """
        Deserialize a dictionary into a message.
        """

        return cls.model_validate(data)


# ==========================================================
# Command Message
# ==========================================================


class CommandMessage(BaseMessage):
    """
    Command sent from one AI agent to another.

    Commands instruct another agent to perform an action.

    Example
    -------
    Planning Agent
            ↓
    Dispatch Agent

    "Assign technician TECH-101"
    """

    topic: str = Field(
        default="agent.command",
        min_length=1,
        max_length=100,
        description="Default routing topic for commands.",
    )

    message_type: MessageType = Field(
        default=MessageType.COMMAND,
        frozen=True,
    )


# ==========================================================
# Query Message
# ==========================================================


class QueryMessage(BaseMessage):
    """
    Query sent when an agent needs information.

    Example
    -------
    Monitoring Agent
            ↓
    Planning Agent

    "Who is the nearest technician?"
    """

    topic: str = Field(
        default="agent.query",
        min_length=1,
        max_length=100,
        description="Default routing topic for queries.",
    )

    message_type: MessageType = Field(
        default=MessageType.QUERY,
        frozen=True,
    )


# ==========================================================
# Event Message
# ==========================================================


class EventMessage(BaseMessage):
    """
    Event broadcast between AI agents.

    Events announce that something happened.

    Example
    -------
    Dispatch Agent
            ↓
    Monitoring Agent

    Technician accepted job.
    """

    topic: str = Field(
        default="agent.event",
        min_length=1,
        max_length=100,
        description="Default routing topic for events.",
    )

    message_type: MessageType = Field(
        default=MessageType.EVENT,
        frozen=True,
    )


# ==========================================================
# GPS Location Event Message
# ==========================================================


class GPSLocationEventMessage(EventMessage):
    """
    Dedicated GPS location event.

    GPS coordinates are allowed only for this message type.
    All other message types continue to use the global privacy
    protection that forbids latitude/longitude keys.
    """

    allow_gps_coordinates: ClassVar[bool] = True

    topic: str = Field(
        default="fieldops.gps.events",
        min_length=1,
        max_length=100,
        description="Kafka topic for technician GPS location events.",
    )

    message_type: MessageType = Field(
        default=MessageType.EVENT,
        frozen=True,
    )

    @model_validator(mode="after")
    def validate_gps_event(self) -> "GPSLocationEventMessage":
        """
        Enforce the GPS event contract and coordinate bounds.
        """
        if self.topic != "fieldops.gps.events":
            raise ValueError(
                "GPS location events must use topic 'fieldops.gps.events'."
            )

        if self.payload.get("event_type") != "GPS-location":
            raise ValueError(
                "GPS location events must have event_type 'GPS-location'."
            )

        if "latitude" not in self.payload or "longitude" not in self.payload:
            raise ValueError(
                "GPS location events require latitude and longitude."
            )

        latitude = self.payload["latitude"]
        longitude = self.payload["longitude"]

        if not isinstance(latitude, (int, float)) or isinstance(latitude, bool):
            raise ValueError("GPS latitude must be a numeric value.")

        if not isinstance(longitude, (int, float)) or isinstance(longitude, bool):
            raise ValueError("GPS longitude must be a numeric value.")

        if not -90 <= latitude <= 90:
            raise ValueError("GPS latitude must be between -90 and 90.")

        if not -180 <= longitude <= 180:
            raise ValueError("GPS longitude must be between -180 and 180.")

        return self


# ==========================================================
# Response Message
# ==========================================================


class ResponseMessage(BaseMessage):
    """
    Successful response returned after a
    command or query.

    Example
    -------
    Planning Agent

    Recommended Technician:
    TECH-101
    """

    topic: str = Field(
        default="agent.response",
        min_length=1,
        max_length=100,
        description="Default routing topic for responses.",
    )

    message_type: MessageType = Field(
        default=MessageType.RESPONSE,
        frozen=True,
    )

    success: bool = Field(
        default=True,
        description="Indicates successful execution.",
    )


# ==========================================================
# Error Message
# ==========================================================


class ErrorMessage(BaseMessage):
    """
    Error returned when an AI request fails.

    Example
    -------
    Dispatch Agent

    Technician unavailable.
    """

    topic: str = Field(
        default="agent.error",
        min_length=1,
        max_length=100,
        description="Default routing topic for errors.",
    )

    message_type: MessageType = Field(
        default=MessageType.ERROR,
        frozen=True,
    )

    success: bool = Field(
        default=False,
        description="Indicates failed execution.",
    )

    error_code: str = Field(
        ...,
        description="Machine-readable error code.",
        examples=["TECHNICIAN_NOT_AVAILABLE"],
    )

    error_message: str = Field(
        ...,
        description="Human-readable error message.",
    )

    details: Dict[str, Any] = Field(
        default_factory=dict,
        description="Optional error details.",
    )

    @field_validator("details", mode="before")
    @classmethod
    def deep_copy_and_validate_details(cls, value: Any) -> Any:
        """
        Deep-copy and validate details for JSON compatibility and privacy.
        """
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("details must be a dictionary.")
        value = copy.deepcopy(value)
        _validate_json_and_privacy(value, path="details")
        return value


# ==========================================================
# Delivery Result Models
# ==========================================================


class DeliveryFailure(BaseModel):
    """
    Record of a single failed handler delivery.

    Does not include payload, metadata, exception traces,
    or raw exception messages — only safe operational data.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        str_strip_whitespace=True,
    )

    subscription_id: UUID4 = Field(
        description="UUID of the subscription whose handler failed.",
    )

    subscriber: Optional[AgentAddress] = Field(
        default=None,
        description="Subscriber address, or None for broadcast-only subscriptions.",
    )

    error_code: str = Field(
        ...,
        min_length=1,
        description="Machine-readable failure code (e.g. HANDLER_TIMEOUT).",
    )

    safe_message: str = Field(
        ...,
        min_length=1,
        description="Generic, safe human-readable description of the failure.",
    )


class PublishResult(BaseModel):
    """
    Summary result of a publish() call.

    Counts are non-negative and delivered + failed == matched_subscribers.
    Does not include payload, metadata, exception traces or raw errors.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    message_id: UUID4 = Field(
        description="UUID of the published message.",
    )

    matched_subscribers: int = Field(
        ge=0,
        description="Number of subscriptions that matched routing rules.",
    )

    delivered: int = Field(
        ge=0,
        description="Number of handlers that completed successfully.",
    )

    failed: int = Field(
        ge=0,
        description="Number of handlers that failed or timed out.",
    )

    failures: tuple[DeliveryFailure, ...] = Field(
        default=(),
        description="Details of each failed delivery.",
    )

    @model_validator(mode="after")
    def validate_count_consistency(self) -> "PublishResult":
        """
        Validate that delivered + failed equals matched_subscribers,
        and failed equals len(failures).
        """
        if self.delivered + self.failed != self.matched_subscribers:
            raise ValueError(
                f"delivered ({self.delivered}) + failed ({self.failed}) "
                f"must equal matched_subscribers ({self.matched_subscribers})."
            )
        if self.failed != len(self.failures):
            raise ValueError(
                f"failed ({self.failed}) must equal number of failures "
                f"({len(self.failures)})."
            )
        return self