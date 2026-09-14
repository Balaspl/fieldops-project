"""
Authentication API routes.

Endpoints:
- POST /auth/register — create user account
- POST /auth/login — authenticate and get tokens
- POST /auth/refresh — rotate refresh token
- POST /auth/logout — revoke tokens
- POST /auth/forgot-password — request password reset
- POST /auth/reset-password — reset password with token
- GET  /auth/me — get current user profile
"""

import uuid
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.orm import Session

from ..database import get_db
from ..auth.password import hash_password, verify_password, validate_password_strength, PasswordValidationError
from ..auth.jwt_handler import (
    create_access_token, create_refresh_token,
    verify_refresh_token, blacklist_token,
    ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_DAYS,
)
from ..auth.rbac import UserRole, can_manage_role
from ..auth.dependencies import (
    get_current_user, AuthenticatedUser,
    require_role, require_permission,
)
from ..models.user import User, RefreshToken
from ..models.organization import Organization
from .oauth2 import _password_grant, _refresh_token_grant, GrantError

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


# ──────────────────────────────────────────────────
# Request/Response Schemas
# ──────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    tenant_id: str = Field(..., min_length=1, max_length=100)
    phone_number: Optional[str] = None

class OrganizationOnboardRequest(BaseModel):
    organization_name: str = Field(..., min_length=2, max_length=200)

    admin_first_name: str = Field(..., min_length=1, max_length=100)
    admin_last_name: str = Field(..., min_length=1, max_length=100)
    admin_email: str = Field(..., min_length=5, max_length=255)
    admin_password: str = Field(..., min_length=8, max_length=128)

    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None

class LoginRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
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
    email: str = Field(..., min_length=5, max_length=255)


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8, max_length=128)

class OAuth2ContractResponse(BaseModel):
    status: str
    auth_protocol: str
    token_type: str
    tenant_claim: str


# ──────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────

def _build_token_response(user: User, request: Request, db: Session) -> TokenResponse:
    """Create access + refresh tokens and persist the refresh token."""
    access_token = create_access_token(
        user_id=user.id,
        tenant_id=user.tenant_id,
        role=user.role,
    )
    refresh_token_str = create_refresh_token(
        user_id=user.id,
        tenant_id=user.tenant_id,
        role=user.role,
    )

    # Get organization name for the logged-in user's tenant
    org = db.query(Organization).filter(
        Organization.id == user.tenant_id
    ).first()


    # Store refresh token hash in DB
    token_hash = hashlib.sha256(refresh_token_str.encode()).hexdigest()
    refresh_record = RefreshToken(
        id=str(uuid.uuid4()),
        user_id=user.id,
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        device_info=request.headers.get("User-Agent", "unknown")[:255],
        ip_address=request.client.host if request.client else "unknown",
    )
    db.add(refresh_record)
    db.commit()

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
            "organization_name": org.name if org else None,

        },
    )


def _log_audit(db: Session, action: str, user_id: str, tenant_id: str,
               request: Request, severity: str = "INFO", details: dict = None):
    """Log an authentication event to the enterprise audit trail."""
    from ..models.enterprise_audit import EnterpriseAuditLog
    audit = EnterpriseAuditLog(
        id=str(uuid.uuid4()),
        user_id=user_id,
        tenant_id=tenant_id,
        action=action,
        ip_address=request.client.host if request.client else "unknown",
        user_agent=request.headers.get("User-Agent", "unknown")[:500],
        severity=severity,
        details=details,
        correlation_id=request.headers.get("X-Correlation-ID"),
    )
    db.add(audit)


# ──────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Register a new user account.

    - Customers can self-register (tenant_id required)
    - Other roles require an admin to create them via this endpoint
      with proper authentication.
    """
    # Validate role
    # Public self-registration is customer-only.
    role = UserRole.CUSTOMER
    # Validate password strength
    try:
        validate_password_strength(payload.password)
    except PasswordValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "WEAK_PASSWORD", "errors": e.errors},
        )

    # Determine tenant
    tenant_id = payload.tenant_id
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="tenant_id is required",
        )

    # Verify organization exists and is active
    org = db.query(Organization).filter(
        Organization.id == tenant_id,
        Organization.status == "ACTIVE",
        Organization.deleted_at.is_(None),
    ).first()

    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found or inactive",
        )

    # Check for duplicate email within tenant
    existing = db.query(User).filter(
        User.email == payload.email.lower().strip(),
        User.tenant_id == tenant_id,
        User.deleted_at.is_(None),
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists in this organization",
        )

    # Create user
    user = User(
        id=str(uuid.uuid4()),
        email=payload.email.lower().strip(),
        password_hash=hash_password(payload.password),
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

    # Audit log
    _log_audit(db, "USER_REGISTERED", user.id, tenant_id, request, details={"role": role.value})

    response = _build_token_response(user, request, db)
    
    logger.info("User registered: email=%s role=%s tenant=%s", user.email, role.value, tenant_id)
    return response


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Legacy JSON-body login. Delegates credential checking and token
    issuance to _password_grant() so there is one code path shared
    with /oauth2/token.
    """
    try:
        user, access_token, refresh_token_str, _granted_scope = _password_grant(
            db, request, payload.email, payload.password,
        )
    except GrantError:
        _log_audit(db, "FAILED_LOGIN", "unknown", "unknown", request,
                   severity="WARNING", details={"email": payload.email.lower().strip()})
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    org = db.query(Organization).filter(Organization.id == user.tenant_id).first()
    _log_audit(db, "LOGIN", user.id, user.tenant_id, request)
    db.commit()

    logger.info("User logged in: email=%s role=%s tenant=%s", user.email, user.role, user.tenant_id)

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
            "organization_name": org.name if org else None,
        },
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_tokens(
    payload: RefreshRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Legacy JSON-body refresh. Delegates to _refresh_token_grant() so
    rotation logic is shared with /oauth2/token.
    """
    try:
        user, access_token, new_refresh_token, _granted_scope = _refresh_token_grant(
            db, request, payload.refresh_token,
        )
    except GrantError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    org = db.query(Organization).filter(Organization.id == user.tenant_id).first()
    logger.info("Tokens refreshed for user: %s", user.email)

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user={
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": user.role,
            "tenant_id": user.tenant_id,
            "organization_name": org.name if org else None,
        },
    )


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(
    request: Request,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Logout: blacklist the current access token and revoke all refresh tokens.
    """
    # Blacklist the current access token
    if current_user.jti:
        blacklist_token(current_user.jti, ACCESS_TOKEN_EXPIRE_MINUTES * 60)

    # Revoke all active refresh tokens for this user
    now = datetime.now(timezone.utc)
    db.query(RefreshToken).filter(
        RefreshToken.user_id == current_user.user_id,
        RefreshToken.revoked_at.is_(None),
    ).update({"revoked_at": now})

    _log_audit(db, "LOGOUT", current_user.user_id, current_user.tenant_id, request)
    db.commit()

    logger.info("User logged out: %s", current_user.user_id)
    return {"message": "Logged out successfully"}


class UpdateProfileRequest(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)


@router.get("/me", response_model=UserProfileResponse)
async def get_current_profile(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the current user's profile."""
    user = db.query(User).filter(User.id == current_user.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

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


@router.put("/profile", response_model=UserProfileResponse)
async def update_profile(
    payload: UpdateProfileRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update current user's first and last name."""
    user = db.query(User).filter(User.id == current_user.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.first_name = payload.first_name.strip()
    user.last_name = payload.last_name.strip()

    _log_audit(db, "USER_UPDATED", user.id, user.tenant_id, request,
               details={"first_name": user.first_name, "last_name": user.last_name})
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


@router.put("/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change current user's password."""
    user = db.query(User).filter(User.id == current_user.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    try:
        validate_password_strength(payload.new_password)
    except PasswordValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "WEAK_PASSWORD", "errors": e.errors},
        )

    user.password_hash = hash_password(payload.new_password)
    _log_audit(db, "PASSWORD_CHANGED", user.id, user.tenant_id, request)
    db.commit()

    return {"message": "Password changed successfully"}


@router.post("/forgot-password")
async def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Request a password reset.

    Always returns success to prevent email enumeration.
    In production, this would send an email with a reset link.
    """
    email = payload.email.lower().strip()
    user = db.query(User).filter(
        User.email == email,
        User.deleted_at.is_(None),
    ).first()

    if user:
        _log_audit(db, "PASSWORD_RESET_REQUESTED", user.id, user.tenant_id, request)
        db.commit()
        # TODO: Send email with reset token via SendGrid
        logger.info("Password reset requested for: %s", email)

    # Always return success to prevent email enumeration
    return {"message": "If an account with that email exists, a password reset link has been sent."}


@router.post("/reset-password")
async def reset_password(
    payload: ResetPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Reset password using a reset token.

    Stub implementation — in production, validate the reset token
    from the email link.
    """
    # Validate new password strength
    try:
        validate_password_strength(payload.new_password)
    except PasswordValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "WEAK_PASSWORD", "errors": e.errors},
        )

    # TODO: Validate reset token and find user
    # For now, return a placeholder
    return {"message": "Password reset functionality requires email integration. Token validation stub."}

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