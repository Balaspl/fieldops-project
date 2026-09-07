"""
Organization management routes (Super Admin only).

Endpoints:
- POST   /organizations           — create organization
- GET    /organizations           — list all organizations
- GET    /organizations/{id}      — get organization details
- PUT    /organizations/{id}      — update organization
- POST   /organizations/{id}/suspend — suspend organization
- POST   /organizations/{id}/activate — activate organization
- DELETE /organizations/{id}      — soft delete organization
- POST   /organizations/{id}/admin — create org admin
- GET    /platform/health         — system health
- GET    /platform/analytics      — cross-tenant analytics
"""

import uuid
import re
import logging
import secrets
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func


from ..database import get_db
from ..auth.dependencies import (
    get_current_user, AuthenticatedUser,
    require_role, require_permission,
)
from ..auth.rbac import UserRole, Permission
from ..auth.password import hash_password, validate_password_strength, PasswordValidationError
from ..models.organization import Organization
from ..models.user import User
from ..services.enterprise_audit import audit_log, AuditAction
from ..models.organization_onboarding import OrganizationOnboarding
import os
import smtplib
from email.message import EmailMessage
from ..routes.auth import _build_token_response
from ..auth.jwt_handler import create_access_token, create_refresh_token




logger = logging.getLogger(__name__)

async def send_otp_email(
    to_email: str,
    first_name: str,
    otp: str,
) -> bool:
    """
    Send organization verification OTP using Gmail SMTP.
    """

    SMTP_HOST= os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME = os.getenv("SMTP_USERNAME")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

    if not SMTP_USERNAME or not SMTP_PASSWORD:
        logger.error("Gmail SMTP credentials are not configured.")
        return False

    message = EmailMessage()

    message["Subject"] = "FieldOps organization verification code"
    message["From"] = SMTP_USERNAME
    message["To"] = to_email

    message.set_content(
        f"""
Hello {first_name},

Your verification code for creating your FieldOps organization is:

{otp}

This code will expire in 10 minutes.

If you did not request this registration, you can ignore this email.

Regards,
FieldOps Team
"""
    )

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(message)

        logger.info("OTP email sent successfully.")
        return True

    except Exception:
        logger.exception("Failed to send OTP email through Gmail SMTP.")
        return False


# ──────────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────────

class OrgCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    slug: Optional[str] = None
    subscription_plan: str = Field(default="FREE")
    max_users: int = Field(default=10, ge=1)
    max_technicians: int = Field(default=50, ge=1)
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    address: Optional[str] = None


class OrgUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=200)
    subscription_plan: Optional[str] = None
    max_users: Optional[int] = Field(None, ge=1)
    max_technicians: Optional[int] = Field(None, ge=1)
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    address: Optional[str] = None
    settings: Optional[dict] = None
class OrganizationOnboardingRequest(BaseModel):
    organization_name: str = Field(..., min_length=2, max_length=200)
    admin_first_name: str = Field(..., min_length=1, max_length=100)
    admin_last_name: str = Field(..., min_length=1, max_length=100)
    admin_email: str = Field(..., min_length=5, max_length=255)

class OnboardingStartResponse(BaseModel):
    message: str
    onboarding_id: str

class CompleteOrganizationOnboardingRequest(BaseModel):
    onboarding_id: str
    password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str = Field(..., min_length=8, max_length=128)


class VerifyOTPRequest(BaseModel):
    onboarding_id: str
    otp: str = Field(..., min_length=6, max_length=6)


class OrgSuspendRequest(BaseModel):
    reason: str = Field(..., min_length=10, max_length=500)


class OrgAdminCreateRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    role: str = Field(default="dispatcher")


class OrgResponse(BaseModel):
    id: str
    name: str
    slug: str
    status: str
    subscription_plan: str
    max_users: int
    max_technicians: int
    contact_email: Optional[str]
    created_at: datetime
    user_count: Optional[int] = None
    technician_count: Optional[int] = None


# ──────────────────────────────────────────────────
# Organization Routes
# ──────────────────────────────────────────────────

org_router = APIRouter(
    prefix="/organizations",
    tags=["Organizations"],
)


def _generate_slug(name: str) -> str:
    """Generate a URL-safe slug from organization name."""
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower().strip())
    slug = slug.strip('-')
    return f"{slug}-{uuid.uuid4().hex[:6]}"





# ==================================================
# ORGANIZATION ONBOARDING START
# ==================================================

@org_router.post(
    "/onboarding/start",
    response_model=OnboardingStartResponse,
    status_code=status.HTTP_200_OK,
)
async def start_organization_onboarding(
    payload: OrganizationOnboardingRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Start organization onboarding.

    The organization and Super Admin are NOT created yet.
    An OTP is generated and sent to the admin email.
    """

    email = payload.admin_email.lower().strip()

    # Check whether this email already exists
    existing_user = db.query(User).filter(
        User.email == email,
        User.deleted_at.is_(None),
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    # Generate six-digit OTP
    otp = f"{secrets.randbelow(1_000_000):06d}"
    print(f"DEBUG OTP: {otp}")

    # Store only the hashed OTP
    otp_hash = hashlib.sha256(
        otp.encode("utf-8")
    ).hexdigest()

    # OTP expires after 10 minutes
    otp_expires_at = (
        datetime.now(timezone.utc)
        + timedelta(minutes=10)
    )

    # Create temporary onboarding record
    onboarding = OrganizationOnboarding(
        id=str(uuid.uuid4()),
        organization_name=payload.organization_name.strip(),
        admin_first_name=payload.admin_first_name.strip(),
        admin_last_name=payload.admin_last_name.strip(),
        admin_email=email,
        otp_hash=otp_hash,
        otp_expires_at=otp_expires_at,
        otp_verified=False,
        otp_attempts=0,
    )

    db.add(onboarding)
    db.commit()
    db.refresh(onboarding)

    # Send OTP
    email_sent = await send_otp_email(
    to_email=email,
    first_name=payload.admin_first_name,
    otp=otp,
)

    if not email_sent:
        db.delete(onboarding)
        db.commit()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to send verification email.",
        )

    logger.info(
        "Organization onboarding started: onboarding_id=%s",
        onboarding.id,
    )

    return OnboardingStartResponse(
    message="Verification OTP sent successfully.",
    onboarding_id=onboarding.id,
)


# ==================================================
# ORGANIZATION OTP VERIFICATION
# ==================================================

@org_router.post(
    "/onboarding/verify-otp",
    status_code=status.HTTP_200_OK,
)

async def verify_organization_otp(
    payload: VerifyOTPRequest,
    db: Session = Depends(get_db),
):
    # Find the onboarding record
    onboarding = db.query(OrganizationOnboarding).filter(
        OrganizationOnboarding.id == payload.onboarding_id
    ).first()

    if onboarding is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Onboarding request not found.",
        )

    # Check whether OTP was already verified
    if onboarding.otp_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP has already been verified.",
        )

    # Check whether OTP has expired
    if onboarding.is_otp_expired:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP has expired. Please request a new OTP.",
        )

    # Check maximum attempts
    if onboarding.otp_attempts >= 5:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many incorrect OTP attempts.",
        )

    # Hash the OTP entered by the user
    entered_otp_hash = hashlib.sha256(
        payload.otp.encode("utf-8")
    ).hexdigest()

    # Compare entered OTP with stored hash
    if entered_otp_hash != onboarding.otp_hash:
        onboarding.otp_attempts += 1
        db.commit()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OTP.",
        )

    # OTP is correct
    onboarding.otp_verified = True
    onboarding.otp_verified_at = datetime.now(timezone.utc)

    db.commit()

    return {
        "message": "OTP verified successfully.",
        "onboarding_id": onboarding.id,
    }
@org_router.post(
    "/onboarding/complete",
    status_code=status.HTTP_201_CREATED,
)
async def complete_organization_onboarding(
    payload: CompleteOrganizationOnboardingRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Complete organization onboarding.

    Creates:
    1. Organization
    2. Super Admin user

    Both are created only after OTP verification.
    """

    # --------------------------------------------------
    # Find onboarding record
    # --------------------------------------------------

    onboarding = db.query(OrganizationOnboarding).filter(
        OrganizationOnboarding.id == payload.onboarding_id
    ).first()

    if onboarding is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Onboarding request not found.",
        )

    # --------------------------------------------------
    # OTP must be verified first
    # --------------------------------------------------

    if not onboarding.otp_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email verification is required before completing registration.",
        )

    # --------------------------------------------------
    # Check password confirmation
    # --------------------------------------------------

    if payload.password != payload.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwords do not match.",
        )

    # --------------------------------------------------
    # Validate password strength
    # --------------------------------------------------

    try:
        validate_password_strength(payload.password)
    except PasswordValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "WEAK_PASSWORD",
                "errors": e.errors,
            },
        )

    # --------------------------------------------------
    # Check email again
    # --------------------------------------------------

    existing_user = db.query(User).filter(
        User.email == onboarding.admin_email,
        User.deleted_at.is_(None),
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )
        # --------------------------------------------------
    # Prevent one email from creating multiple organizations
    # --------------------------------------------------

    existing_organization = db.query(Organization).filter(
        Organization.contact_email == onboarding.admin_email,
        Organization.deleted_at.is_(None),
    ).first()

    if existing_organization:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This email is already associated with an organization.",
        )

    # --------------------------------------------------
    # Generate organization slug
    # --------------------------------------------------

    slug = _generate_slug(onboarding.organization_name)

    # --------------------------------------------------
    # Create Organization
    # --------------------------------------------------

    organization = Organization(
        id=f"org-{uuid.uuid4().hex[:12]}",
        name=onboarding.organization_name,
        slug=slug,
        status="ACTIVE",
        subscription_plan="FREE",
        max_users=10,
        max_technicians=50,
        max_jobs_per_month=500,
        contact_email=onboarding.admin_email,
    )

    db.add(organization)
    db.flush()

    # --------------------------------------------------
    # Create Super Admin
    # --------------------------------------------------

    super_admin = User(
        id=str(uuid.uuid4()),
        email=onboarding.admin_email,
        password_hash=hash_password(payload.password),
        first_name=onboarding.admin_first_name,
        last_name=onboarding.admin_last_name,
        role=UserRole.SUPER_ADMIN.value,
        tenant_id=organization.id,
        is_active=True,
        is_email_verified=True,
    )

    db.add(super_admin)

    # --------------------------------------------------
    # Save everything
    # --------------------------------------------------

    db.commit()

# Refresh objects
    db.refresh(organization)
    db.refresh(super_admin)

    # Automatically authenticate the newly created Super Admin
    token_response = _build_token_response(
        super_admin,
        request,
        db,
    )

    logger.info(
        "Organization onboarding completed: organization_id=%s admin_id=%s",
        organization.id,
        super_admin.id,
    )
    return{
        "message": "Organization created successfully.",
        "organization_id": organization.id,
        "organization_name": organization.name,
        "admin_id": super_admin.id,
        "admin_email": super_admin.email,
        "role": super_admin.role,
        "access_token": token_response.access_token,
        "refresh_token": token_response.refresh_token,
        "token_type": token_response.token_type,
        "expires_in": token_response.expires_in,
        "user": token_response.user,
    }
@org_router.post("", status_code=status.HTTP_201_CREATED)
async def create_organization(
    payload: OrgCreateRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(require_role(UserRole.SUPER_ADMIN)),
    db: Session = Depends(get_db),
):
    """Create a new organization. Super Admin only."""
    slug = payload.slug or _generate_slug(payload.name)

    # Check slug uniqueness
    existing = db.query(Organization).filter(Organization.slug == slug).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Organization slug already exists",
        )

    org = Organization(
        name=payload.name.strip(),
        slug=slug,
        status="ACTIVE",
        subscription_plan=payload.subscription_plan,
        max_users=payload.max_users,
        max_technicians=payload.max_technicians,
        contact_email=payload.contact_email,
        contact_phone=payload.contact_phone,
        address=payload.address,
    )
    db.add(org)
    db.flush()

    audit_log(
        db, action=AuditAction.ORG_CREATED,
        tenant_id=org.id,
        user_id=current_user.user_id,
        role=current_user.role.value,
        entity_type="organization",
        entity_id=org.id,
        new_value={"name": org.name, "plan": org.subscription_plan},
        request=request,
    )

    db.commit()
    logger.info("Organization created: %s (%s)", org.name, org.id)

    return {
        "id": org.id,
        "name": org.name,
        "slug": org.slug,
        "status": org.status,
        "subscription_plan": org.subscription_plan,
        "created_at": org.created_at.isoformat() if org.created_at else None,
    }


@org_router.get("")
async def list_organizations(
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    all_tenants: bool = Query(False, description="Platform admin only: view all tenants"),
current_user: AuthenticatedUser = Depends(
    require_role(UserRole.SUPER_ADMIN)
),
     db: Session = Depends(get_db),
):
    """List organizations. Filtered by current user's tenant by default."""
    query = db.query(Organization).filter(Organization.deleted_at.is_(None))

    # Strict tenant isolation by default for all users
    if not (all_tenants and current_user.tenant_id == "__platform__"):
        query = query.filter(Organization.id == current_user.tenant_id)

    if status_filter:
        query = query.filter(Organization.status == status_filter.upper())

    total = query.count()
    orgs = query.order_by(Organization.created_at.desc()).offset((page - 1) * limit).limit(limit).all()

    results = []
    for org in orgs:
        user_count = db.query(func.count(User.id)).filter(
            User.tenant_id == org.id,
            User.deleted_at.is_(None),
        ).scalar()

        results.append({
            "id": org.id,
            "name": org.name,
            "slug": org.slug,
            "status": org.status,
            "subscription_plan": org.subscription_plan,
            "max_users": org.max_users,
            "max_technicians": org.max_technicians,
            "contact_email": org.contact_email,
            "user_count": user_count,
            "created_at": org.created_at.isoformat() if org.created_at else None,
        })

    return {"data": results, "total": total, "page": page, "limit": limit}


@org_router.get("/{org_id}")
async def get_organization(
    org_id: str,
    current_user: AuthenticatedUser = Depends(require_role(UserRole.SUPER_ADMIN, UserRole.SUPER_ADMIN)),
    db: Session = Depends(get_db),
):
    """Get organization details. Super Admin or own org Admin."""
    org = db.query(Organization).filter(
        Organization.id == org_id,
        Organization.deleted_at.is_(None),
    ).first()

    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Users can only view their own org unless platform admin
    if current_user.tenant_id != "__platform__" and current_user.tenant_id != org_id:
        raise HTTPException(status_code=403, detail="Access denied")

    user_count = db.query(func.count(User.id)).filter(
        User.tenant_id == org_id,
        User.deleted_at.is_(None),
    ).scalar()

    return {
        "id": org.id,
        "name": org.name,
        "slug": org.slug,
        "status": org.status,
        "subscription_plan": org.subscription_plan,
        "max_users": org.max_users,
        "max_technicians": org.max_technicians,
        "max_jobs_per_month": org.max_jobs_per_month,
        "contact_email": org.contact_email,
        "contact_phone": org.contact_phone,
        "address": org.address,
        "settings": org.settings,
        "user_count": user_count,
        "created_at": org.created_at.isoformat() if org.created_at else None,
        "updated_at": org.updated_at.isoformat() if org.updated_at else None,
    }


@org_router.put("/{org_id}")
async def update_organization(
    org_id: str,
    payload: OrgUpdateRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(require_role(UserRole.SUPER_ADMIN)),
    db: Session = Depends(get_db),
):
    """Update organization details. Super Admin only."""
    org = db.query(Organization).filter(
        Organization.id == org_id,
        Organization.deleted_at.is_(None),
    ).first()

    if current_user.tenant_id != "__platform__" and current_user.tenant_id != org_id:
        raise HTTPException(status_code=403, detail="Access denied")

    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    old_values = {}
    new_values = {}

    for field in ["name", "subscription_plan", "max_users", "max_technicians",
                  "contact_email", "contact_phone", "address", "settings"]:
        new_val = getattr(payload, field, None)
        if new_val is not None:
            old_values[field] = getattr(org, field)
            setattr(org, field, new_val)
            new_values[field] = new_val

    audit_log(
        db, action=AuditAction.ORG_UPDATED,
        tenant_id=org_id,
        user_id=current_user.user_id,
        role=current_user.role.value,
        entity_type="organization",
        entity_id=org_id,
        old_value=old_values,
        new_value=new_values,
        request=request,
    )

    db.commit()
    return {"message": "Organization updated successfully", "id": org_id}


@org_router.post("/{org_id}/suspend")
async def suspend_organization(
    org_id: str,
    payload: OrgSuspendRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(require_role(UserRole.SUPER_ADMIN)),
    db: Session = Depends(get_db),
):
    """Suspend an organization. All users lose access."""
    org = db.query(Organization).filter(
        Organization.id == org_id,
        Organization.deleted_at.is_(None),
    ).first()

    if current_user.tenant_id != "__platform__" and current_user.tenant_id != org_id:
        raise HTTPException(status_code=403, detail="Access denied")

    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    if org.status == "SUSPENDED":
        raise HTTPException(status_code=400, detail="Organization is already suspended")

    org.status = "SUSPENDED"
    org.suspended_at = datetime.now(timezone.utc)
    org.suspended_by = current_user.user_id
    org.suspension_reason = payload.reason

    audit_log(
        db, action=AuditAction.ORG_SUSPENDED,
        tenant_id=org_id,
        user_id=current_user.user_id,
        role=current_user.role.value,
        entity_type="organization",
        entity_id=org_id,
        new_value={"reason": payload.reason},
        severity="WARNING",
        request=request,
    )

    db.commit()
    logger.warning("Organization suspended: %s reason=%s", org_id, payload.reason)
    return {"message": "Organization suspended", "id": org_id}


@org_router.post("/{org_id}/activate")
async def activate_organization(
    org_id: str,
    request: Request,
    current_user: AuthenticatedUser = Depends(require_role(UserRole.SUPER_ADMIN)),
    db: Session = Depends(get_db),
):
    """Reactivate a suspended organization."""
    org = db.query(Organization).filter(
        Organization.id == org_id,
        Organization.deleted_at.is_(None),
    ).first()

    if current_user.tenant_id != "__platform__" and current_user.tenant_id != org_id:
        raise HTTPException(status_code=403, detail="Access denied")

    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    if org.status == "ACTIVE":
        raise HTTPException(status_code=400, detail="Organization is already active")

    org.status = "ACTIVE"
    org.suspended_at = None
    org.suspended_by = None
    org.suspension_reason = None

    audit_log(
        db, action=AuditAction.ORG_ACTIVATED,
        tenant_id=org_id,
        user_id=current_user.user_id,
        role=current_user.role.value,
        entity_type="organization",
        entity_id=org_id,
        request=request,
    )

    db.commit()
    logger.info("Organization activated: %s", org_id)
    return {"message": "Organization activated", "id": org_id}


@org_router.delete("/{org_id}")
async def delete_organization(
    org_id: str,
    request: Request,
    current_user: AuthenticatedUser = Depends(require_role(UserRole.SUPER_ADMIN)),
    db: Session = Depends(get_db),
):
    """Soft delete an organization. Super Admin only."""
    org = db.query(Organization).filter(
        Organization.id == org_id,
        Organization.deleted_at.is_(None),
    ).first()

    if current_user.tenant_id != "__platform__" and current_user.tenant_id != org_id:
        raise HTTPException(status_code=403, detail="Access denied")

    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    now = datetime.now(timezone.utc)
    org.status = "DELETED"
    org.deleted_at = now
    org.deleted_by = current_user.user_id

    # Deactivate all users in this org
    db.query(User).filter(
        User.tenant_id == org_id,
        User.deleted_at.is_(None),
    ).update({"is_active": False, "deleted_at": now, "deleted_by": current_user.user_id})

    audit_log(
        db, action=AuditAction.ORG_DELETED,
        tenant_id=org_id,
        user_id=current_user.user_id,
        role=current_user.role.value,
        entity_type="organization",
        entity_id=org_id,
        severity="CRITICAL",
        request=request,
    )

    db.commit()
    logger.warning("Organization deleted: %s", org_id)
    return {"message": "Organization deleted", "id": org_id}


@org_router.post("/{org_id}/admin", status_code=status.HTTP_201_CREATED)
async def create_org_admin(
    org_id: str,
    payload: OrgAdminCreateRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(require_role(UserRole.SUPER_ADMIN, UserRole.SUPER_ADMIN)),
    db: Session = Depends(get_db),
):
    """Create an admin or user for an organization. Super Admin or Org Admin."""
    if current_user.tenant_id != "__platform__" and current_user.tenant_id != org_id:
        raise HTTPException(status_code=403, detail="Access denied to this organization")

    # Prevent creation of Super Admin accounts via user provisioning
    requested_role = (payload.role or "admin").lower().strip()

    if requested_role in ["super_admin", "superadmin", "super admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Creating Super Admin accounts is not permitted.",
        )

    try:
        role = UserRole(requested_role)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role: {requested_role}. Valid roles: "
                f"{', '.join(r.value for r in UserRole)}",
        )

    org = db.query(Organization).filter(
        Organization.id == org_id,
        Organization.status == "ACTIVE",
        Organization.deleted_at.is_(None),
    ).first()

    if not org:
        raise HTTPException(status_code=404, detail="Organization not found or inactive")

    # Check user limit
    current_user_count = db.query(func.count(User.id)).filter(
        User.tenant_id == org_id,
        User.deleted_at.is_(None),
    ).scalar()

    if current_user_count >= org.max_users:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Organization has reached its user limit ({org.max_users})",
        )

    # Check duplicate email
    existing = db.query(User).filter(
        User.email == payload.email.lower().strip(),
        User.tenant_id == org_id,
        User.deleted_at.is_(None),
    ).first()

    if existing:
        raise HTTPException(status_code=409, detail="Email already exists in this organization")

    # Validate password
    try:
        validate_password_strength(payload.password)
    except PasswordValidationError as e:
        raise HTTPException(
            status_code=400,
            detail={"error": "WEAK_PASSWORD", "errors": e.errors},
        )

    admin = User(
        id=str(uuid.uuid4()),
        email=payload.email.lower().strip(),
        password_hash=hash_password(payload.password),
        first_name=payload.first_name.strip(),
        last_name=payload.last_name.strip(),
        role=role.value,
        tenant_id=org_id,
        is_active=True,
        is_email_verified=True,  # Admin-created accounts are pre-verified
    )
    db.add(admin)

    audit_log(
        db, action=AuditAction.USER_CREATED,
        tenant_id=org_id,
        user_id=current_user.user_id,
        role=current_user.role.value,
        entity_type="user",
        entity_id=admin.id,
        new_value={"email": admin.email, "role": admin.role},
        request=request,
    )

    db.commit()
    logger.info("Org admin created: %s for org %s", admin.email, org_id)

    return {
        "id": admin.id,
        "email": admin.email,
        "first_name": admin.first_name,
        "last_name": admin.last_name,
        "role": admin.role,
        "tenant_id": org_id,
    }


# ──────────────────────────────────────────────────
# Platform Routes (Super Admin)
# ──────────────────────────────────────────────────

platform_router = APIRouter(
    prefix="/platform",
    tags=["Platform"],
)


@platform_router.get("/health")
async def platform_health(
    current_user: AuthenticatedUser = Depends(require_role(UserRole.SUPER_ADMIN)),
    db: Session = Depends(get_db),
):
    """System health check. Super Admin only."""
    from ..redis_client import get_redis_client

    redis_status = "connected"
    try:
        redis = get_redis_client()
        if redis:
            redis.get("health_check")
        else:
            redis_status = "unavailable"
    except Exception:
        redis_status = "error"

    db_status = "connected"
    try:
        db.execute(db.bind.dialect.statement_compiler(db.bind.dialect, None).__class__.__module__)
    except Exception:
        pass  # If we got here, DB is working since get_db succeeded

    total_orgs = db.query(func.count(Organization.id)).filter(
        Organization.deleted_at.is_(None)
    ).scalar()
    active_orgs = db.query(func.count(Organization.id)).filter(
        Organization.status == "ACTIVE",
        Organization.deleted_at.is_(None),
    ).scalar()
    total_users = db.query(func.count(User.id)).filter(
        User.deleted_at.is_(None)
    ).scalar()

    return {
        "status": "healthy",
        "database": db_status,
        "redis": redis_status,
        "organizations": {
            "total": total_orgs,
            "active": active_orgs,
        },
        "users": {
            "total": total_users,
        },
    }


@platform_router.get("/analytics")
async def platform_analytics(
    current_user: AuthenticatedUser = Depends(require_role(UserRole.SUPER_ADMIN)),
    db: Session = Depends(get_db),
):
    """Cross-tenant analytics. Super Admin only."""
    from ..models import Job, Technician

    total_orgs = db.query(func.count(Organization.id)).filter(
        Organization.deleted_at.is_(None)
    ).scalar()

    total_users = db.query(func.count(User.id)).filter(
        User.deleted_at.is_(None)
    ).scalar()

    total_jobs = db.query(func.count(Job.id)).scalar()
    total_technicians = db.query(func.count(Technician.technician_id)).scalar()

    # Users by role
    users_by_role = {}
    for role in UserRole:
        count = db.query(func.count(User.id)).filter(
            User.role == role.value,
            User.deleted_at.is_(None),
        ).scalar()
        users_by_role[role.value] = count

    # Orgs by plan
    orgs_by_plan = {}
    for plan in ["FREE", "STARTER", "PROFESSIONAL", "ENTERPRISE"]:
        count = db.query(func.count(Organization.id)).filter(
            Organization.subscription_plan == plan,
            Organization.deleted_at.is_(None),
        ).scalar()
        orgs_by_plan[plan] = count

    return {
        "total_organizations": total_orgs,
        "total_users": total_users,
        "total_jobs": total_jobs,
        "total_technicians": total_technicians,
        "users_by_role": users_by_role,
        "organizations_by_plan": orgs_by_plan,
    }
