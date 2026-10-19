from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from typing import Literal, Optional
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import re

CustomerPreferenceChannel = Literal["SMS", "EMAIL", "PUSH", "PORTAL"]

class CustomerPreferenceValues(BaseModel):
    sms_enabled: bool
    email_enabled: bool
    push_enabled: bool
    portal_enabled: bool
    preferred_locale: str
    daily_engagement_enabled: bool = False
    timezone: str = "UTC"
    quiet_hours_start: str = "21:00"
    quiet_hours_end: str = "08:00"

    model_config = ConfigDict(extra="forbid", frozen=True)

class CustomerPreferenceUpdate(BaseModel):
    sms_enabled: Optional[bool] = None
    email_enabled: Optional[bool] = None
    push_enabled: Optional[bool] = None
    portal_enabled: Optional[bool] = None
    preferred_locale: Optional[str] = None
    daily_engagement_enabled: Optional[bool] = None
    timezone: Optional[str] = None
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, TypeError):
            raise ValueError("timezone must be a valid IANA timezone")
        return value

    @field_validator("quiet_hours_start", "quiet_hours_end")
    @classmethod
    def validate_quiet_time(cls, value):
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError("quiet hours must use HH:MM (24-hour) format")
        return value

    @model_validator(mode="after")
    def validate_update(self):
        if not self.model_fields_set:
            raise ValueError(
                "At least one update field must be provided."
            )

        null_fields = [
            field
            for field in self.model_fields_set
            if getattr(self, field) is None
        ]

        if null_fields:
            raise ValueError(
                "Explicit null preference values are not allowed."
            )

        return self

class CustomerPreferenceResponse(BaseModel):
    profile_id: Optional[str]
    tenant_id: str
    customer_id: str
    sms_enabled: bool
    email_enabled: bool
    push_enabled: bool
    portal_enabled: bool
    preferred_locale: str
    daily_engagement_enabled: bool = False
    timezone: str = "UTC"
    quiet_hours_start: str = "21:00"
    quiet_hours_end: str = "08:00"
    revision: int
    source: Literal["PROFILE", "COMPATIBILITY_DEFAULT"]
    updated_at: Optional[datetime]
    updated_by: Optional[str]

    model_config = ConfigDict(extra="forbid", frozen=True)

class CustomerPreferenceDecision(BaseModel):
    allowed: bool
    channel: CustomerPreferenceChannel
    reason_code: str
    source: Literal["PROFILE", "COMPATIBILITY_DEFAULT"]
    revision: int

    model_config = ConfigDict(extra="forbid", frozen=True)
