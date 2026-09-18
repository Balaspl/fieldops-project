from typing import Optional

from pydantic import BaseModel, Field


class MFAEnrollmentResponse(BaseModel):
    status: str
    mfa_required: bool
    secret: str
    provisioning_uri: str
    recovery_codes: list[str]


class MFAVerifyRequest(BaseModel):
    challenge: str = Field(min_length=1)
    code: str = Field(min_length=6, max_length=6)

    # User can choose "Trust this device"
    trust_device: bool = False


class MFARecoveryRequest(BaseModel):
    challenge: str = Field(min_length=1)
    recovery_code: str = Field(min_length=1)


class MFAStatusResponse(BaseModel):
    status: str
    mfa_required: bool
    enrolled: bool
    enabled: bool


class MFAChallengeResponse(BaseModel):
    status: str
    mfa_required: bool
    challenge: str
    expires_in: int


class MFAVerificationResponse(BaseModel):
    status: str
    mfa_required: bool
    challenge: str
    replay_protected: bool

    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
    user: dict

    # Returned only when trust_device=True
    trusted_device_token: Optional[str] = None


class MFAEnrollmentVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)