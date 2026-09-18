"""
Authentication API routes.

Endpoints:
- POST /auth/register
- POST /auth/login
- POST /auth/refresh
- POST /auth/logout
- POST /auth/forgot-password
- POST /auth/reset-password
- GET  /auth/me

Authentication history events are written to EnterpriseAuditLog and
never contain passwords, bearer tokens, refresh tokens, MFA codes, or
raw trusted-device/password-reset tokens.

Enterprise SSO/OIDC:
- GET  /auth/sso/login
- GET  /auth/sso/callback

Authentication sources:
- Bearer access token
- Enterprise SSO HttpOnly access-token cookie

Security model:
- OIDC authenticates the external identity.
- FieldOps maps the OIDC identity to an existing User.
- FieldOps remains the source of truth for tenant and role.
- No FieldOps user is automatically created from OIDC.
"""

import hashlib
import logging
import os
import secrets
import uuid

from datetime import datetime, timedelta, timezone
from typing import Optional, Union

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db

from ..auth.password import (
    PasswordValidationError,
    hash_password,
    validate_password_strength,
    verify_password,
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
)

from ..auth.jwt_handler import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
    blacklist_token,
    create_access_token,
    create_refresh_token,
)

from ..auth.rbac import UserRole

from ..auth.dependencies import (
    AuthenticatedUser,
    get_current_user,
)

from ..auth.session_service import (
    create_session,
    delete_session,
)

from ..models.user import (
    RefreshToken,
    User,
)

from ..models.trust_device import TrustedDevice

from app.models.mfa import MFA

from ..models.organization import Organization

from ..models.password_reset_token import PasswordResetToken

from ..services.email.email_service import EmailService

from .oauth2 import (
    GrantError,
    _password_grant,
    _refresh_token_grant,
    _authenticate_password,
    _issue_tokens,
)

from ..auth.mfa_service import (
    create_enrollment_secret,
    create_mfa_challenge,
    create_trusted_device,
    get_trusted_device,
    delete_mfa_challenge,
    generate_recovery_codes,
    get_mfa_challenge,
    get_user_mfa,
    is_mfa_required_for_role,
    save_recovery_codes,
    verify_mfa_challenge,
    verify_mfa_recovery,
    verify_totp,
    decrypt_secret,
)

from ..services.ai.FieldOpsAI.schemas.mfa import (
    MFAEnrollmentResponse,
    MFAVerifyRequest,
    MFARecoveryRequest,
    MFAStatusResponse,
    MFAChallengeResponse,
    MFAVerificationResponse,
    MFAEnrollmentVerifyRequest,
)

from ..auth.oidc import (
    OIDCValidationError,
    validate_google_id_token,
)

from ..models.oidc_identity import OIDCIdentity


logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


# ============================================================
# Constants
# ============================================================

SSO_ACCESS_COOKIE = "fieldops_access_token"
SSO_REFRESH_COOKIE = "fieldops_refresh_token"

PASSWORD_RESET_TOKEN_EXPIRE_MINUTES = 15

# Durable authentication history events. Keep these values stable so
# administrators can query a consistent authentication history.
AUTH_EVENT_LOGIN_SUCCESS = "LOGIN_SUCCESS"
AUTH_EVENT_LOGIN_FAILURE = "LOGIN_FAILURE"
AUTH_EVENT_ACCOUNT_LOCKED = "ACCOUNT_LOCKED"
AUTH_EVENT_LOGOUT = "LOGOUT"

AUTH_HISTORY_ACTIONS = {
    AUTH_EVENT_LOGIN_SUCCESS,
    AUTH_EVENT_LOGIN_FAILURE,
    AUTH_EVENT_ACCOUNT_LOCKED,
    AUTH_EVENT_LOGOUT,
}


# ============================================================
# Request / Response Schemas
# ============================================================


class RegisterRequest(BaseModel):
    email: str = Field(
        ...,
        min_length=5,
        max_length=255,
    )

    password: str = Field(
        ...,
        min_length=MIN_PASSWORD_LENGTH,
        max_length=MAX_PASSWORD_LENGTH,
    )

    first_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
    )

    last_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
    )

    tenant_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
    )

    phone_number: Optional[str] = None


class OrganizationOnboardRequest(BaseModel):
    organization_name: str = Field(
        ...,
        min_length=2,
        max_length=200,
    )

    admin_first_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
    )

    admin_last_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
    )

    admin_email: str = Field(
        ...,
        min_length=5,
        max_length=255,
    )

    admin_password: str = Field(
        ...,
        min_length=8,
        max_length=128,
    )

    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None


class LoginRequest(BaseModel):
    email: str = Field(
        ...,
        min_length=5,
        max_length=255,
    )

    password: str = Field(
        ...,
        min_length=1,
        max_length=128,
    )

    trusted_device_token: Optional[str] = Field(
        default=None,
        max_length=512,
    )


class RefreshRequest(BaseModel):
    """
    Refresh request.

    Normal login:
        {
            "refresh_token": "..."
        }

    Enterprise SSO:
        {}
        or no request body.

    For SSO, the refresh token is read from the
    HttpOnly cookie.
    """

    refresh_token: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict


class SSORefreshResponse(BaseModel):
    """
    Safe response for cookie-based SSO refresh.

    The refreshed tokens are NOT returned to JavaScript.
    They are stored in HttpOnly cookies.
    """

    status: str = "refreshed"
    token_type: str = "bearer"
    expires_in: int
    user: dict


class UserProfileResponse(BaseModel):
    id: str
    email: str
    first_name: str
    last_name: str
    role: str
    tenant_id: str
    is_active: bool
    is_email_verified: bool
    last_login: Optional[datetime] = None
    created_at: datetime


class ForgotPasswordRequest(BaseModel):
    email: str = Field(
        ...,
        min_length=5,
        max_length=255,
    )


class ResetPasswordRequest(BaseModel):
    token: str

    new_password: str = Field(
        ...,
        min_length=MIN_PASSWORD_LENGTH,
        max_length=MAX_PASSWORD_LENGTH,
    )


class OAuth2ContractResponse(BaseModel):
    status: str
    auth_protocol: str
    token_type: str
    tenant_claim: str


class OIDCLoginRequest(BaseModel):
    id_token: str = Field(
        ...,
        min_length=1,
    )


# ============================================================
# Cookie Helpers
# ============================================================


def _cookie_secure() -> bool:
    """
    Development:
        COOKIE_SECURE=false

    Production HTTPS:
        COOKIE_SECURE=true
    """

    return (
        os.getenv(
            "COOKIE_SECURE",
            "false",
        )
        .strip()
        .lower()
        == "true"
    )


def _set_sso_cookies(
    response: Response,
    access_token: str,
    refresh_token: str,
) -> None:
    """
    Store SSO tokens as HttpOnly cookies.

    JavaScript cannot directly read these cookies.
    """

    secure = _cookie_secure()

    response.set_cookie(
        key=SSO_ACCESS_COOKIE,
        value=access_token,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

    response.set_cookie(
        key=SSO_REFRESH_COOKIE,
        value=refresh_token,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
    )


def _clear_sso_cookies(
    response: Response,
) -> None:
    """
    Remove SSO access and refresh cookies.
    """

    response.delete_cookie(
        key=SSO_ACCESS_COOKIE,
        path="/",
    )

    response.delete_cookie(
        key=SSO_REFRESH_COOKIE,
        path="/",
    )


# ============================================================
# Token Response Helper
# ============================================================


def _build_token_response(
    user: User,
    request: Request,
    db: Session,
) -> TokenResponse:
    """
    Create a new application session and issue
    access + refresh tokens.

    The session is the server-side source of truth
    for inactivity and maximum lifetime.

    Tenant and role are always taken from the
    FieldOps User record.
    """

    # ---------------------------------------------------------
    # Create server-side application session
    # ---------------------------------------------------------

    session = create_session(
        user_id=str(user.id),
        tenant_id=str(user.tenant_id),
    )

    session_id = session["session_id"]

    # ---------------------------------------------------------
    # Create access token
    # ---------------------------------------------------------

    access_token = create_access_token(
        user_id=user.id,
        tenant_id=user.tenant_id,
        role=user.role,
        session_id=session_id,
    )

    # ---------------------------------------------------------
    # Create refresh token
    # ---------------------------------------------------------

    refresh_token_str = create_refresh_token(
        user_id=user.id,
        tenant_id=user.tenant_id,
        role=user.role,
        session_id=session_id,
    )

    # ---------------------------------------------------------
    # Organization information
    # ---------------------------------------------------------

    org = (
        db.query(Organization)
        .filter(
            Organization.id == user.tenant_id,
        )
        .first()
    )

    # ---------------------------------------------------------
    # Hash refresh token before database storage
    # ---------------------------------------------------------

    token_hash = hashlib.sha256(
        refresh_token_str.encode(),
    ).hexdigest()

    # ---------------------------------------------------------
    # Persist refresh token
    # ---------------------------------------------------------

    refresh_record = RefreshToken(
        id=str(uuid.uuid4()),
        user_id=user.id,
        session_id=session_id,
        token_hash=token_hash,
        expires_at=(
            datetime.now(timezone.utc)
            + timedelta(
                days=REFRESH_TOKEN_EXPIRE_DAYS,
            )
        ),
        device_info=request.headers.get(
            "User-Agent",
            "unknown",
        )[:255],
        ip_address=(
            request.client.host
            if request.client
            else "unknown"
        ),
    )

    db.add(refresh_record)
    db.commit()

    # ---------------------------------------------------------
    # Return token response
    # ---------------------------------------------------------

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token_str,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user={
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": user.role,
            "tenant_id": user.tenant_id,
            "organization_name": (
                org.name
                if org
                else None
            ),
        },
    )


# ============================================================
# Password Reset Helper
# ============================================================


def hash_reset_token(token: str) -> str:
    """
    Hash a password reset token before
    database lookup/storage.
    """

    return hashlib.sha256(
        token.encode("utf-8"),
    ).hexdigest()


# ============================================================
# Audit Helper
# ============================================================


def _find_user_for_auth_audit(
    db: Session,
    email: Optional[str],
) -> Optional[User]:
    """Resolve a login identifier for internal audit attribution only.

    This does not change the public authentication response and never
    writes the supplied password or token to the audit log.
    """

    if not email:
        return None

    normalized_email = email.lower().strip()
    if not normalized_email:
        return None

    return (
        db.query(User)
        .filter(
            User.email == normalized_email,
            User.deleted_at.is_(None),
        )
        .first()
    )


def _log_audit(
    db: Session,
    action: str,
    user_id: Optional[str],
    tenant_id: Optional[str],
    request: Request,
    severity: str = "INFO",
    details: Optional[dict] = None,
):
    """
    Write authentication event to enterprise audit log.
    """

    from ..models.enterprise_audit import (
        EnterpriseAuditLog,
    )

    if not tenant_id:
        logger.warning(
            "Authentication audit event without tenant: "
            "action=%s user_id=%s details=%s",
            action,
            user_id,
            details,
        )
        return

    organization_exists = (
        db.query(Organization.id)
        .filter(
            Organization.id == tenant_id,
        )
        .first()
    )

    if organization_exists is None:
        logger.warning(
            "Authentication audit event skipped because "
            "tenant does not exist: action=%s tenant_id=%s "
            "user_id=%s details=%s",
            action,
            tenant_id,
            user_id,
            details,
        )
        return

    audit = EnterpriseAuditLog(
        id=str(uuid.uuid4()),
        user_id=user_id,
        tenant_id=tenant_id,
        action=action,
        ip_address=(
            request.client.host
            if request.client
            else "unknown"
        ),
        user_agent=request.headers.get(
            "User-Agent",
            "unknown",
        )[:500],
        severity=severity,
        details=details,
        correlation_id=request.headers.get(
            "X-Correlation-ID",
        ),
    )

    db.add(audit)


# ============================================================
# Register
# ============================================================


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    payload: RegisterRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Register a new customer account.
    """

    role = UserRole.CUSTOMER

    try:
        validate_password_strength(
            payload.password,
        )

    except PasswordValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "WEAK_PASSWORD",
                "errors": e.errors,
            },
        )

    tenant_id = payload.tenant_id

    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="tenant_id is required",
        )

    org = (
        db.query(Organization)
        .filter(
            Organization.id == tenant_id,
            Organization.status == "ACTIVE",
            Organization.deleted_at.is_(None),
        )
        .first()
    )

    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found or inactive",
        )

    existing = (
        db.query(User)
        .filter(
            User.email == payload.email.lower().strip(),
            User.tenant_id == tenant_id,
            User.deleted_at.is_(None),
        )
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "A user with this email already exists "
                "in this organization"
            ),
        )

    user = User(
        id=str(uuid.uuid4()),
        email=payload.email.lower().strip(),
        password_hash=hash_password(
            payload.password,
        ),
        first_name=payload.first_name.strip(),
        last_name=payload.last_name.strip(),
        role=role.value,
        tenant_id=tenant_id,
        phone_number=payload.phone_number,
        is_active=True,
        is_email_verified=False,
    )

    db.add(user)
    db.flush()

    _log_audit(
        db,
        "USER_REGISTERED",
        user.id,
        tenant_id,
        request,
        details={
            "role": role.value,
        },
    )

    response = _build_token_response(
        user,
        request,
        db,
    )

    logger.info(
        "User registered: email=%s role=%s tenant=%s",
        user.email,
        role.value,
        tenant_id,
    )

    return response


# ============================================================
# Normal Email / Password Login
# ============================================================


@router.post(
    "/login",
    response_model=Union[
        TokenResponse,
        MFAChallengeResponse,
    ],
)
async def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Email/password login with role-based MFA.

    A valid trusted-device token can skip MFA for
    the same user until the token expires.
    """

    try:
        user, granted_scope = _authenticate_password(
            db=db,
            request=request,
            username=payload.email,
            password=payload.password,
        )

    except GrantError as exc:
        # -----------------------------------------------------
        # ACCOUNT LOCKOUT
        # -----------------------------------------------------
        # Preserve HTTP 423 so the frontend can show the
        # account-locked message instead of treating it as
        # a normal invalid-password response.
        # -----------------------------------------------------
        if exc.error == "account_locked":
            locked_user = _find_user_for_auth_audit(
                db,
                payload.email,
            )

            _log_audit(
                db=db,
                action=AUTH_EVENT_ACCOUNT_LOCKED,
                user_id=(locked_user.id if locked_user else None),
                tenant_id=(
                    locked_user.tenant_id
                    if locked_user
                    else None
                ),
                request=request,
                severity="WARNING",
                details={
                    "outcome": "blocked",
                    "reason": "account_locked",
                },
            )

            db.commit()

            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail=exc.description,
            )

        # -----------------------------------------------------
        # NORMAL INVALID LOGIN
        # -----------------------------------------------------
        failed_user = _find_user_for_auth_audit(
            db,
            payload.email,
        )

        _log_audit(
            db=db,
            action=AUTH_EVENT_LOGIN_FAILURE,
            user_id=(failed_user.id if failed_user else None),
            tenant_id=(
                failed_user.tenant_id
                if failed_user
                else None
            ),
            request=request,
            severity="WARNING",
            details={
                "outcome": "failure",
                "reason": "invalid_email_or_password",
            },
        )

        db.commit()

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    mfa_required = is_mfa_required_for_role(user.role)

    mfa = get_user_mfa(
        db=db,
        user_id=user.id,
        tenant_id=user.tenant_id,
    )

    # ---------------------------------------------------------
    # Trusted device bypass
    # ---------------------------------------------------------
    # Password authentication has already succeeded. A trusted
    # device is accepted only for this exact user and only while
    # its server-side token is valid.
    # ---------------------------------------------------------
    if (
        mfa_required
        and mfa is not None
        and mfa.enabled
        and payload.trusted_device_token
    ):
        trusted_device = get_trusted_device(
            db=db,
            user_id=user.id,
            token=payload.trusted_device_token,
        )

        if trusted_device is not None:
            access_token, refresh_token = _issue_tokens(
                db=db,
                request=request,
                user=user,
                granted_scope=granted_scope,
            )

            org = (
                db.query(Organization)
                .filter(
                    Organization.id == user.tenant_id,
                )
                .first()
            )

            _log_audit(
                db=db,
                action=AUTH_EVENT_LOGIN_SUCCESS,
                user_id=user.id,
                tenant_id=user.tenant_id,
                request=request,
                details={
                    "mfa_required": True,
                    "mfa_enabled": True,
                    "trusted_device": True,
                    "authentication_method": "trusted_device",
                    "trusted_device": True,
                    "trusted_device_id": trusted_device.id,
                    "expires_at": trusted_device.expires_at.isoformat(),
                },
            )

            db.commit()

            logger.info(
                "Trusted-device login successful: user_id=%s tenant=%s",
                user.id,
                user.tenant_id,
            )

            return TokenResponse(
                access_token=access_token,
                refresh_token=refresh_token,
                token_type="bearer",
                expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                user={
                    "id": user.id,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "role": user.role,
                    "tenant_id": user.tenant_id,
                    "organization_name": (
                        org.name
                        if org
                        else None
                    ),
                },
            )

    # ---------------------------------------------------------
    # MFA challenge
    # ---------------------------------------------------------
    if (
        mfa_required
        and mfa is not None
        and mfa.enabled
    ):
        challenge_id = create_mfa_challenge(
            user_id=user.id,
            tenant_id=user.tenant_id,
        )

        _log_audit(
            db=db,
            action="MFA_CHALLENGE_CREATED",
            user_id=user.id,
            tenant_id=user.tenant_id,
            request=request,
            details={
                "method": "totp",
                "role": str(user.role),
            },
        )

        db.commit()

        return MFAChallengeResponse(
            status="MFA_REQUIRED",
            mfa_required=True,
            challenge=challenge_id,
            expires_in=300,
        )

    # ---------------------------------------------------------
    # MFA not required / not enabled
    # ---------------------------------------------------------
    access_token, refresh_token = _issue_tokens(
        db=db,
        request=request,
        user=user,
        granted_scope=granted_scope,
    )

    org = (
        db.query(Organization)
        .filter(
            Organization.id == user.tenant_id,
        )
        .first()
    )

    _log_audit(
        db=db,
        action=AUTH_EVENT_LOGIN_SUCCESS,
        user_id=user.id,
        tenant_id=user.tenant_id,
        request=request,
        details={
            "outcome": "success",
            "authentication_method": "password",
            "mfa_required": mfa_required,
            "mfa_enabled": bool(mfa and mfa.enabled),
        },
    )

    db.commit()

    logger.info(
        "User logged in: email=%s role=%s tenant=%s",
        user.email,
        user.role,
        user.tenant_id,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user={
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": user.role,
            "tenant_id": user.tenant_id,
            "organization_name": (
                org.name
                if org
                else None
            ),
        },
    )


# ============================================================
# MFA Enrollment
# ============================================================


@router.post(
    "/mfa/enroll",
    response_model=MFAEnrollmentResponse,
)
async def enroll_mfa(
    request: Request,
    current_user: AuthenticatedUser = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    """
    Start MFA enrollment for the authenticated user.
    """

    user = (
        db.query(User)
        .filter(
            User.id == current_user.user_id,
            User.deleted_at.is_(None),
        )
        .first()
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    if not is_mfa_required_for_role(
        user.role
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="MFA is not required for this role",
        )

    existing = get_user_mfa(
        db=db,
        user_id=user.id,
        tenant_id=user.tenant_id,
    )

    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="MFA configuration already exists",
        )

    (
        raw_secret,
        encrypted_secret,
        provisioning_uri,
    ) = create_enrollment_secret(
        user_email=user.email,
    )

    mfa = MFA(
        id=str(uuid.uuid4()),
        user_id=user.id,
        tenant_id=user.tenant_id,
        secret_encrypted=encrypted_secret,
        enabled=False,
    )

    db.add(mfa)
    db.flush()

    _log_audit(
        db=db,
        action="MFA_ENROLLMENT_STARTED",
        user_id=user.id,
        tenant_id=user.tenant_id,
        request=request,
        details={
            "method": "totp",
        },
    )

    db.commit()

    return MFAEnrollmentResponse(
        status="ENROLLMENT_PENDING",
        mfa_required=True,
        secret=raw_secret,
        provisioning_uri=provisioning_uri,
        recovery_codes=[],
    )


# ============================================================
# MFA Enrollment Verification
# ============================================================


@router.post(
    "/mfa/enroll/verify",
)
async def verify_mfa_enrollment(
    payload: MFAEnrollmentVerifyRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    """
    Verify the first TOTP code and enable MFA.
    """

    user = (
        db.query(User)
        .filter(
            User.id == current_user.user_id,
            User.deleted_at.is_(None),
        )
        .first()
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    mfa = get_user_mfa(
        db=db,
        user_id=user.id,
        tenant_id=user.tenant_id,
    )

    if mfa is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="MFA enrollment has not been started",
        )

    if mfa.enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="MFA is already enabled",
        )

    try:
        secret = decrypt_secret(
            mfa.secret_encrypted
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to validate MFA configuration",
        )

    if not verify_totp(
        secret,
        payload.code,
    ):
        _log_audit(
            db=db,
            action="MFA_ENROLLMENT_FAILED",
            user_id=user.id,
            tenant_id=user.tenant_id,
            request=request,
            severity="WARNING",
            details={
                "reason": "invalid_totp",
            },
        )

        db.commit()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid MFA code",
        )

    recovery_codes = generate_recovery_codes()

    save_recovery_codes(
        db=db,
        mfa=mfa,
        tenant_id=user.tenant_id,
        recovery_codes=recovery_codes,
    )

    mfa.enabled = True
    mfa.enrolled_at = datetime.now(
        timezone.utc
    )

    _log_audit(
        db=db,
        action="MFA_ENABLED",
        user_id=user.id,
        tenant_id=user.tenant_id,
        request=request,
        details={
            "method": "totp",
            "recovery_codes_generated": len(
                recovery_codes
            ),
        },
    )

    db.commit()

    return {
        "status": "ENABLED",
        "mfa_required": True,
        "recovery_codes": recovery_codes,
    }


# ============================================================
# MFA Status
# ============================================================


@router.get(
    "/mfa/status",
    response_model=MFAStatusResponse,
)
async def mfa_status(
    current_user: AuthenticatedUser = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    user = (
        db.query(User)
        .filter(
            User.id == current_user.user_id,
            User.deleted_at.is_(None),
        )
        .first()
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    mfa = get_user_mfa(
        db=db,
        user_id=user.id,
        tenant_id=user.tenant_id,
    )

    return MFAStatusResponse(
        status="SUPPORTED",
        mfa_required=is_mfa_required_for_role(
            user.role
        ),
        enrolled=mfa is not None,
        enabled=(
            bool(mfa.enabled)
            if mfa is not None
            else False
        ),
    )


# ============================================================
# Reset MFA
# ============================================================


@router.post(
    "/mfa/reset",
)
async def reset_mfa(
    request: Request,
    current_user: AuthenticatedUser = Depends(
        get_current_user,
    ),
    db: Session = Depends(get_db),
):
    """
    Reset the currently authenticated user's MFA configuration.
    """

    user = (
        db.query(User)
        .filter(
            User.id == current_user.user_id,
            User.deleted_at.is_(None),
        )
        .first()
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    if not is_mfa_required_for_role(user.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="MFA is not required for this role",
        )

    mfa = get_user_mfa(
        db=db,
        user_id=user.id,
        tenant_id=user.tenant_id,
    )

    if mfa is None:
        return {
            "status": "NOT_ENROLLED",
            "message": "MFA is not currently enrolled",
        }

    # Resetting MFA also invalidates all trusted devices so an old
    # trusted-device credential cannot bypass the new MFA setup.
    db.query(TrustedDevice).filter(
        TrustedDevice.user_id == user.id,
    ).delete(
        synchronize_session=False,
    )

    db.delete(mfa)

    _log_audit(
        db=db,
        action="MFA_RESET",
        user_id=user.id,
        tenant_id=user.tenant_id,
        request=request,
        severity="WARNING",
        details={
            "method": "totp",
        },
    )

    db.commit()

    return {
        "status": "RESET",
        "message": (
            "MFA has been reset. "
            "You can enroll a new authenticator."
        ),
    }


# ============================================================
# MFA Verification
# ============================================================


@router.post(
    "/mfa/verify",
    response_model=MFAVerificationResponse,
)
def verify_mfa(
    request: Request,
    payload: MFAVerifyRequest,
    db: Session = Depends(get_db),
):
    """
    Verify MFA and issue application tokens.

    If trust_device=True, create a 30-day trusted-device
    credential. Only the hash is stored in the database.
    """

    challenge = get_mfa_challenge(payload.challenge)

    if challenge is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired MFA challenge",
        )

    challenge_tenant_id = str(
        challenge.get("tenant_id", "")
    )

    if not challenge_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid MFA challenge",
        )

    success, user_id = verify_mfa_challenge(
        db=db,
        challenge_id=payload.challenge,
        code=payload.code,
        tenant_id=challenge_tenant_id,
    )

    if not success or not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid MFA code",
        )

    user = (
        db.query(User)
        .filter(
            User.id == user_id,
            User.tenant_id == challenge_tenant_id,
            User.deleted_at.is_(None),
        )
        .first()
    )

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    trusted_device_token = None

    # ---------------------------------------------------------
    # Create trusted device only AFTER successful MFA.
    # ---------------------------------------------------------
    if payload.trust_device:
        (
            trusted_device_token,
            trusted_device,
        ) = create_trusted_device(
            db=db,
            user_id=user.id,
        )

        _log_audit(
            db=db,
            action="TRUSTED_DEVICE_CREATED",
            user_id=user.id,
            tenant_id=user.tenant_id,
            request=request,
            details={
                "trusted_device_id": trusted_device.id,
                "expires_at": trusted_device.expires_at.isoformat(),
            },
        )

    token_response = _build_token_response(
        request=request,
        db=db,
        user=user,
    )

    _log_audit(
        db=db,
        action=AUTH_EVENT_LOGIN_SUCCESS,
        user_id=user.id,
        tenant_id=user.tenant_id,
        request=request,
        details={
            "outcome": "success",
            "authentication_method": "password_plus_totp",
            "mfa_required": True,
            "mfa_enabled": True,
            "trusted_device": bool(payload.trust_device),
        },
    )

    db.commit()

    return MFAVerificationResponse(
        status="VERIFIED",
        mfa_required=True,
        challenge=payload.challenge,
        replay_protected=True,
        access_token=token_response.access_token,
        refresh_token=token_response.refresh_token,
        token_type=token_response.token_type,
        expires_in=token_response.expires_in,
        user=token_response.user,
        trusted_device_token=trusted_device_token,
    )


# ============================================================
# MFA Recovery
# ============================================================


@router.post(
    "/mfa/recovery",
    response_model=MFAVerificationResponse,
)
def verify_mfa_recovery_code(
    request: Request,
    payload: MFARecoveryRequest,
    db: Session = Depends(get_db),
):
    """
    Verify MFA recovery code and issue normal FieldOps tokens.
    """

    challenge = get_mfa_challenge(payload.challenge)

    if challenge is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired MFA challenge",
        )

    challenge_tenant_id = str(
        challenge.get("tenant_id", "")
    )

    if not challenge_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid MFA challenge",
        )

    success, user_id = verify_mfa_recovery(
        db=db,
        challenge_id=payload.challenge,
        recovery_code=payload.recovery_code,
        tenant_id=challenge_tenant_id,
    )

    if not success or not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid recovery code",
        )

    user = (
        db.query(User)
        .filter(
            User.id == user_id,
            User.tenant_id == challenge_tenant_id,
            User.deleted_at.is_(None),
        )
        .first()
    )

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    token_response = _build_token_response(
        request=request,
        db=db,
        user=user,
    )

    _log_audit(
        db=db,
        action=AUTH_EVENT_LOGIN_SUCCESS,
        user_id=user.id,
        tenant_id=user.tenant_id,
        request=request,
        details={
            "outcome": "success",
            "authentication_method": "mfa_recovery_code",
            "mfa_required": True,
            "mfa_enabled": True,
        },
    )

    db.commit()

    return MFAVerificationResponse(
        status="VERIFIED",
        mfa_required=True,
        challenge=payload.challenge,
        replay_protected=True,
        access_token=token_response.access_token,
        refresh_token=token_response.refresh_token,
        token_type=token_response.token_type,
        expires_in=token_response.expires_in,
        user=token_response.user,
    )


# ============================================================
# Direct Google OIDC Compatibility Endpoint
# ============================================================


@router.post(
    "/oidc/google",
    response_model=TokenResponse,
)
async def google_oidc_login(
    payload: OIDCLoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Authenticate using a previously linked Google identity.
    """

    try:
        claims = await validate_google_id_token(
            payload.id_token,
        )

    except OIDCValidationError:
        _log_audit(
            db=db,
            action="FAILED_OIDC_LOGIN",
            user_id=None,
            tenant_id=None,
            request=request,
            severity="WARNING",
            details={
                "provider": "google",
                "reason": "invalid_oidc_identity",
            },
        )

        db.commit()

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid OIDC identity",
        )

    issuer = str(
        claims["iss"],
    ).rstrip("/")

    subject = str(
        claims["sub"],
    )

    identity = (
        db.query(OIDCIdentity)
        .filter(
            OIDCIdentity.issuer == issuer,
            OIDCIdentity.subject == subject,
            OIDCIdentity.provider == "google",
        )
        .first()
    )

    if identity is None:
        _log_audit(
            db=db,
            action="FAILED_OIDC_LOGIN_UNKNOWN_IDENTITY",
            user_id=None,
            tenant_id=None,
            request=request,
            severity="WARNING",
            details={
                "provider": "google",
                "reason": "identity_not_linked",
                "issuer": issuer,
                "subject": subject,
            },
        )

        db.commit()

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Google account is not linked "
                "to a FieldOps account"
            ),
        )

    user = (
        db.query(User)
        .filter(
            User.id == identity.user_id,
            User.deleted_at.is_(None),
        )
        .first()
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="FieldOps account not found",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="FieldOps account is disabled",
        )

    organization = (
        db.query(Organization)
        .filter(
            Organization.id == user.tenant_id,
            Organization.status == "ACTIVE",
            Organization.deleted_at.is_(None),
        )
        .first()
    )

    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization is inactive",
        )

    response = _build_token_response(
        user=user,
        request=request,
        db=db,
    )

    _log_audit(
        db=db,
        action=AUTH_EVENT_LOGIN_SUCCESS,
        user_id=user.id,
        tenant_id=user.tenant_id,
        request=request,
        details={
            "outcome": "success",
            "authentication_method": "oidc",
            "provider": "google",
        },
    )

    db.commit()

    logger.info(
        "OIDC login successful: user_id=%s provider=google",
        user.id,
    )

    return response


# ============================================================
# Refresh Token
# ============================================================


@router.post(
    "/refresh",
    response_model=Union[
        TokenResponse,
        SSORefreshResponse,
    ],
)
async def refresh_tokens(
    request: Request,
    response: Response,
    payload: Optional[RefreshRequest] = None,
    db: Session = Depends(get_db),
):
    """
    Refresh an access token.

    Normal mode:
        refresh_token in JSON body.

    SSO mode:
        refresh_token comes from HttpOnly cookie.
    """

    body_refresh_token = None

    if payload is not None:
        body_refresh_token = payload.refresh_token

    cookie_refresh_token = request.cookies.get(
        SSO_REFRESH_COOKIE,
    )

    using_sso_cookie = (
        not body_refresh_token
        and bool(cookie_refresh_token)
    )

    refresh_token = (
        body_refresh_token
        or cookie_refresh_token
    )

    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is required",
        )

    try:
        (
            user,
            access_token,
            new_refresh_token,
            _granted_scope,
        ) = _refresh_token_grant(
            db,
            request,
            refresh_token,
        )

    except GrantError:
        if using_sso_cookie:
            _clear_sso_cookies(response)

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    org = (
        db.query(Organization)
        .filter(
            Organization.id == user.tenant_id,
        )
        .first()
    )

    user_data = {
        "id": user.id,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "role": user.role,
        "tenant_id": user.tenant_id,
        "organization_name": (
            org.name
            if org
            else None
        ),
    }

    logger.info(
        "Tokens refreshed for user: %s",
        user.email,
    )

    if using_sso_cookie:
        _set_sso_cookies(
            response=response,
            access_token=access_token,
            refresh_token=new_refresh_token,
        )

        return SSORefreshResponse(
            status="refreshed",
            token_type="bearer",
            expires_in=(
                ACCESS_TOKEN_EXPIRE_MINUTES * 60
            ),
            user=user_data,
        )

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
        expires_in=(
            ACCESS_TOKEN_EXPIRE_MINUTES * 60
        ),
        user=user_data,
    )


# ============================================================
# Logout
# ============================================================


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
)
async def logout(
    response: Response,
    request: Request,
    current_user: AuthenticatedUser = Depends(
        get_current_user,
    ),
    db: Session = Depends(get_db),
):
    """
    Logout the CURRENT application session.

    Important:
    - Does not revoke all sessions for the user.
    - Only the current session is revoked.
    - The Redis session is deleted.
    - The current access token is blacklisted.
    - SSO cookies are cleared.
    """

    # ---------------------------------------------------------
    # Blacklist current access token
    # ---------------------------------------------------------

    if current_user.jti:
        blacklist_token(
            current_user.jti,
            ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    now = datetime.now(timezone.utc)

    # ---------------------------------------------------------
    # Get current session ID
    # ---------------------------------------------------------

    session_id = getattr(
        current_user,
        "session_id",
        None,
    )

    # ---------------------------------------------------------
    # Revoke ONLY refresh tokens belonging
    # to the current application session.
    # ---------------------------------------------------------

    if session_id:
        db.query(
            RefreshToken,
        ).filter(
            RefreshToken.user_id == current_user.user_id,
            RefreshToken.session_id == session_id,
            RefreshToken.revoked_at.is_(None),
        ).update(
            {
                "revoked_at": now,
            },
            synchronize_session=False,
        )

        # -----------------------------------------------------
        # Delete server-side session
        # -----------------------------------------------------

        delete_session(session_id)

    else:
        # -----------------------------------------------------
        # Defensive fallback.
        #
        # New tokens should always have session_id.
        # Do NOT revoke all sessions here because doing so
        # would break concurrent-session isolation.
        # -----------------------------------------------------

        logger.warning(
            "Logout request without session_id: user_id=%s",
            current_user.user_id,
        )

    _log_audit(
        db,
        AUTH_EVENT_LOGOUT,
        current_user.user_id,
        current_user.tenant_id,
        request,
        details={
            "outcome": "success",
            "session_terminated": bool(session_id),
        },
    )

    db.commit()

    # ---------------------------------------------------------
    # Always clear SSO cookies
    # ---------------------------------------------------------

    _clear_sso_cookies(response)

    logger.info(
        "User session logged out: user_id=%s session_id=%s",
        current_user.user_id,
        session_id,
    )

    return {
        "message": "Logged out successfully",
    }


# ============================================================
# Current User
# ============================================================


@router.get(
    "/me",
    response_model=UserProfileResponse,
)
async def get_current_profile(
    current_user: AuthenticatedUser = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    """
    Get current user's profile.
    """

    user = (
        db.query(User)
        .filter(
            User.id == current_user.user_id,
        )
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return UserProfileResponse(
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        role=user.role,
        tenant_id=user.tenant_id,
        is_active=user.is_active,
        is_email_verified=user.is_email_verified,
        last_login=user.last_login,
        created_at=user.created_at,
    )


# ============================================================
# Profile
# ============================================================


class UpdateProfileRequest(BaseModel):
    first_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
    )

    last_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
    )


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(
        ...,
        min_length=MIN_PASSWORD_LENGTH,
        max_length=MAX_PASSWORD_LENGTH,
    )

    new_password: str = Field(
        ...,
        min_length=8,
        max_length=128,
    )


@router.put(
    "/profile",
    response_model=UserProfileResponse,
)
async def update_profile(
    payload: UpdateProfileRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    """
    Update current user's first and last name.
    """

    user = (
        db.query(User)
        .filter(
            User.id == current_user.user_id,
        )
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user.first_name = payload.first_name.strip()
    user.last_name = payload.last_name.strip()

    _log_audit(
        db,
        "USER_UPDATED",
        user.id,
        user.tenant_id,
        request,
        details={
            "first_name": user.first_name,
            "last_name": user.last_name,
        },
    )

    db.commit()

    return UserProfileResponse(
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        role=user.role,
        tenant_id=user.tenant_id,
        is_active=user.is_active,
        is_email_verified=user.is_email_verified,
        last_login=user.last_login,
        created_at=user.created_at,
    )


# ============================================================
# Change Password
# ============================================================


@router.put(
    "/change-password",
)
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    """
    Change current user's password.
    """

    user = (
        db.query(User)
        .filter(
            User.id == current_user.user_id,
        )
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if not verify_password(
        payload.current_password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    try:
        validate_password_strength(
            payload.new_password,
        )

    except PasswordValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "WEAK_PASSWORD",
                "errors": e.errors,
            },
        )

    user.password_hash = hash_password(
        payload.new_password,
    )

    _log_audit(
        db,
        "PASSWORD_CHANGED",
        user.id,
        user.tenant_id,
        request,
    )

    db.commit()

    return {
        "message": "Password changed successfully",
    }


# ============================================================
# Forgot Password
# ============================================================


@router.post(
    "/forgot-password",
)
async def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Request a password reset.

    Always returns the same response to prevent
    account enumeration.
    """

    generic_response = {
        "message": (
            "If an account with that email exists, "
            "a password reset link has been sent."
        )
    }

    email = payload.email.lower().strip()

    user = (
        db.query(User)
        .filter(
            User.email == email,
            User.deleted_at.is_(None),
        )
        .first()
    )

    if user is None:
        return generic_response

    now = datetime.now(timezone.utc)

    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.tenant_id == user.tenant_id,
        PasswordResetToken.used_at.is_(None),
    ).update(
        {
            "used_at": now,
        },
        synchronize_session=False,
    )

    raw_token = secrets.token_urlsafe(32)

    token_hash = hash_reset_token(raw_token)

    expires_at = (
        now
        + timedelta(
            minutes=PASSWORD_RESET_TOKEN_EXPIRE_MINUTES
        )
    )

    reset_token = PasswordResetToken(
        id=str(uuid.uuid4()),
        user_id=user.id,
        tenant_id=user.tenant_id,
        token_hash=token_hash,
        expires_at=expires_at,
    )

    db.add(reset_token)

    _log_audit(
        db=db,
        action="PASSWORD_RESET_REQUESTED",
        user_id=user.id,
        tenant_id=user.tenant_id,
        request=request,
    )

    frontend_url = os.getenv(
        "FRONTEND_URL",
        "http://localhost:5173",
    ).rstrip("/")

    reset_url = (
        f"{frontend_url}/reset-password"
        f"?token={raw_token}"
    )

    email_service = EmailService()

    email_text = f"""
Hello {user.first_name},

We received a request to reset your FieldOps password.

Reset your password using the link below:

{reset_url}

This link will expire in {PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} minutes
and can only be used once.

If you did not request a password reset, you can ignore this email.

Regards,
FieldOps Team
"""

    email_html = f"""
<html>
<body>
    <p>Hello {user.first_name},</p>

    <p>
        We received a request to reset your FieldOps password.
    </p>

    <p>
        <a href="{reset_url}">
            Reset your password
        </a>
    </p>

    <p>
        This link will expire in
        {PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} minutes
        and can only be used once.
    </p>

    <p>
        If you did not request a password reset,
        you can ignore this email.
    </p>

    <p>Regards,<br>FieldOps Team</p>
</body>
</html>
"""

    sent = await email_service.send_email(
        to_email=user.email,
        subject="Reset your FieldOps password",
        text=email_text,
        html=email_html,
    )

    if not sent:
        db.rollback()

        logger.error(
            "Password reset email delivery failed for user_id=%s",
            user.id,
        )

        return generic_response

    db.commit()

    return generic_response


# ============================================================
# Reset Password
# ============================================================


@router.post(
    "/reset-password",
)
async def reset_password(
    payload: ResetPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Reset a user's password using a valid,
    single-use reset token.
    """

    try:
        validate_password_strength(
            payload.new_password
        )

    except PasswordValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "WEAK_PASSWORD",
                "errors": e.errors,
            },
        )

    if not payload.token or len(payload.token) > 512:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    token_hash = hash_reset_token(
        payload.token
    )

    reset_token = (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.token_hash == token_hash,
        )
        .first()
    )

    if reset_token is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    if reset_token.used_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    now = datetime.now(timezone.utc)

    expires_at = reset_token.expires_at

    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(
            tzinfo=timezone.utc
        )

    if expires_at <= now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    user = (
        db.query(User)
        .filter(
            User.id == reset_token.user_id,
            User.tenant_id == reset_token.tenant_id,
            User.deleted_at.is_(None),
        )
        .first()
    )

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    user.password_hash = hash_password(
        payload.new_password
    )

    reset_token.used_at = now

    # ---------------------------------------------------------
    # Password reset invalidates all sessions.
    # This is intentional because the password changed.
    # ---------------------------------------------------------

    db.query(RefreshToken).filter(
        RefreshToken.user_id == user.id,
        RefreshToken.revoked_at.is_(None),
    ).update(
        {
            "revoked_at": now,
        },
        synchronize_session=False,
    )

    # Password reset invalidates trusted-device credentials too.
    db.query(TrustedDevice).filter(
        TrustedDevice.user_id == user.id,
    ).delete(
        synchronize_session=False,
    )

    _log_audit(
        db=db,
        action="PASSWORD_RESET_COMPLETED",
        user_id=user.id,
        tenant_id=user.tenant_id,
        request=request,
    )

    db.commit()

    logger.info(
        "Password reset completed: user_id=%s",
        user.id,
    )

    return {
        "message": "Password reset successfully",
    }


# ============================================================
# OAuth2 Contract
# ============================================================


@router.get(
    "/oauth2/contract",
    response_model=OAuth2ContractResponse,
)
async def get_oauth2_contract():
    return OAuth2ContractResponse(
        status="SUPPORTED",
        auth_protocol="oauth2",
        token_type="bearer",
        tenant_claim="server_derived",
    )


# ============================================================
# Google OIDC Account Linking
# ============================================================


@router.post(
    "/oidc/google/link",
)
async def link_google_account(
    payload: OIDCLoginRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    """
    Link one Google identity to the currently
    authenticated FieldOps user.
    """

    user = (
        db.query(User)
        .filter(
            User.id == current_user.user_id,
            User.deleted_at.is_(None),
        )
        .first()
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="FieldOps user not found",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="FieldOps account is disabled",
        )

    try:
        claims = await validate_google_id_token(
            payload.id_token,
        )

    except OIDCValidationError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google identity",
        )

    issuer = str(
        claims["iss"],
    ).rstrip("/")

    subject = str(
        claims["sub"],
    )

    google_email = str(
        claims.get("email", ""),
    ).strip().lower()

    fieldops_email = str(
        user.email,
    ).strip().lower()

    if not google_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google account email is missing",
        )

    if google_email != fieldops_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Google account email must match "
                "the FieldOps account email"
            ),
        )

    existing_user_identity = (
        db.query(OIDCIdentity)
        .filter(
            OIDCIdentity.user_id == user.id,
        )
        .first()
    )

    if existing_user_identity is not None:

        if (
            existing_user_identity.issuer == issuer
            and existing_user_identity.subject == subject
        ):
            return {
                "status": "ALREADY_LINKED",
                "provider": "google",
            }

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "A Google account is already linked "
                "to this FieldOps account."
            ),
        )

    existing = (
        db.query(OIDCIdentity)
        .filter(
            OIDCIdentity.issuer == issuer,
            OIDCIdentity.subject == subject,
        )
        .first()
    )

    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This Google account is already linked "
                "to another FieldOps account"
            ),
        )

    identity = OIDCIdentity(
        id=str(uuid.uuid4()),
        user_id=user.id,
        provider="google",
        issuer=issuer,
        subject=subject,
    )

    db.add(identity)

    _log_audit(
        db,
        "OIDC_ACCOUNT_LINKED",
        user.id,
        user.tenant_id,
        request,
        details={
            "provider": "google",
        },
    )

    db.commit()

    logger.info(
        "Google OIDC identity linked: "
        "user_id=%s provider=google",
        user.id,
    )

    return {
        "status": "LINKED",
        "provider": "google",
    }