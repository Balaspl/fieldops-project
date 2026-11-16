from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models
from ..auth.dependencies import get_current_user, AuthenticatedUser
from ..auth.rbac import Permission
from ..auth.password import (
    PasswordValidationError,
    hash_password,
    validate_password_strength,
)
from ..services.enterprise_audit import AuditAction, audit_log

router = APIRouter(
    prefix="/dispatchers",
    tags=["Dispatchers"],
)


class ProvisionTechnicianRequest(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    phone_number: str | None = Field(default=None, max_length=20)
    # These two fields are optional for compatibility with the web service's
    # original four-field request. Mobile supplies them to create a ready-to-use
    # operational profile in the same transaction.
    technician_skill: str = Field(default="General", min_length=2, max_length=100)
    technician_location: str = Field(default="Unassigned", min_length=2, max_length=150)


@router.get("")
async def get_dispatchers(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return dispatcher accounts for the caller's organization only."""
    role_name = str(getattr(current_user.role, "value", current_user.role) or "").lower()
    if role_name != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Super Admins can view the dispatcher directory.",
        )

    tenant_id = current_user.tenant_id
    if not tenant_id or tenant_id == "__platform__":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A platform-level account must select an organization before viewing staff.",
        )

    dispatchers = (
        db.query(
            models.User,
            models.Organization.name.label("organization_name"),
        )
        .outerjoin(
            models.Organization,
            models.Organization.id == models.User.tenant_id,
        )
        .filter(
            models.User.tenant_id == tenant_id,
            models.User.role == "dispatcher",
            models.User.deleted_at.is_(None),
        )
        .order_by(models.User.first_name, models.User.last_name)
        .all()
    )

    return [
        {
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "name": f"{user.first_name} {user.last_name}".strip(),
            "role": user.role,
            "tenant_id": user.tenant_id,
            "organization_name": organization_name,
            "is_active": user.is_active,
            "is_on_duty": user.is_on_duty,
            "phone_number": user.phone_number,
            "last_login": user.last_login,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
        }
        for user, organization_name in dispatchers
    ]


@router.post("/provision-technician", status_code=status.HTTP_201_CREATED)
async def provision_technician_account(
    payload: ProvisionTechnicianRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create an authenticated technician User and its operational Technician row.

    The tenant is never accepted from the request body. It is derived from the
    verified JWT identity, and both rows are committed atomically.
    """
    role_name = str(getattr(current_user.role, "value", current_user.role) or "").strip().lower()
    if role_name not in {"super_admin", "dispatcher"} or not current_user.has_permission(Permission.TECHNICIANS_CREATE):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Technician provisioning is restricted to Super Admin and Dispatcher roles.",
        )

    tenant_id = str(current_user.tenant_id or "").strip()
    if not tenant_id or tenant_id == "__platform__":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Technician accounts must be provisioned inside an organization tenant.",
        )

    email = payload.email.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Enter a valid email address.")

    first_name = payload.first_name.strip()
    last_name = payload.last_name.strip()
    skill = payload.technician_skill.strip()
    location = payload.technician_location.strip()
    phone_number = payload.phone_number.strip() if payload.phone_number else None
    if not first_name or not last_name or not skill or not location:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Name, skill, and work location are required.")

    # Lock the tenant row while checking quotas so concurrent requests cannot
    # both pass the same user/technician capacity check.
    organization = (
        db.query(models.Organization)
        .filter(models.Organization.id == tenant_id)
        .with_for_update()
        .first()
    )
    if organization is None or organization.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="The authenticated organization no longer exists.")
    if str(organization.status or "").upper() != "ACTIVE":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Technician accounts cannot be provisioned while the organization is suspended.")

    current_user_count = db.query(func.count(models.User.id)).filter(
        models.User.tenant_id == tenant_id,
        models.User.deleted_at.is_(None),
    ).scalar() or 0
    if current_user_count >= organization.max_users:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Organization has reached its user limit ({organization.max_users}).",
        )

    current_technician_count = db.query(func.count(models.Technician.technician_id)).filter(
        models.Technician.tenant_id == tenant_id,
    ).scalar() or 0
    if current_technician_count >= organization.max_technicians:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Organization has reached its technician limit ({organization.max_technicians}).",
        )

    existing_user = db.query(models.User).filter(
        models.User.tenant_id == tenant_id,
        models.User.email == email,
    ).first()
    if existing_user is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists in your organization.")

    try:
        validate_password_strength(payload.password)
    except PasswordValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.errors)

    user_id = str(uuid.uuid4())
    full_name = f"{first_name} {last_name}".strip()
    user = models.User(
        id=user_id,
        email=email,
        password_hash=hash_password(payload.password),
        first_name=first_name,
        last_name=last_name,
        role="technician",
        tenant_id=tenant_id,
        phone_number=phone_number,
        is_active=True,
        # Accounts created by an authorized organization staff member are
        # treated like other admin-provisioned accounts in this backend.
        is_email_verified=True,
        is_on_duty=False,
    )
    technician = models.Technician(
        tech_id=user_id,
        tenant_id=tenant_id,
        technician_name=full_name,
        technician_skill=skill,
        technician_location=location,
        technician_status="OFFLINE",
        current_jobs=0,
        max_jobs=5,
        phone_number=phone_number,
    )

    try:
        db.add(user)
        db.add(technician)
        db.flush()

        # Keep identity creation and both audit entries in one transaction so
        # a successful provisioning operation is fully traceable.
        audit_log(
            db,
            action=AuditAction.USER_CREATED,
            tenant_id=tenant_id,
            user_id=current_user.user_id,
            role=role_name,
            entity_type="user",
            entity_id=user.id,
            new_value={
                "email": email,
                "role": "technician",
                "technician_record_id": technician.technician_id,
            },
            request=request,
        )
        audit_log(
            db,
            action=AuditAction.TECHNICIAN_CREATED,
            tenant_id=tenant_id,
            user_id=current_user.user_id,
            role=role_name,
            entity_type="technician",
            entity_id=technician.technician_id,
            new_value={
                "tech_id": user_id,
                "technician_name": full_name,
                "technician_skill": skill,
                "technician_location": location,
            },
            request=request,
        )

        db.commit()
        db.refresh(user)
        db.refresh(technician)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A technician account with this email or linked profile already exists.",
        )
    except Exception:
        db.rollback()
        raise

    # Never echo the password or password hash. The caller already holds the
    # one-time generated password and may disclose it once after this succeeds.
    return {
        "message": "Technician login and technician profile created successfully.",
        "user": {
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": user.role,
            "tenant_id": user.tenant_id,
            "is_active": user.is_active,
        },
        "technician": {
            "technician_id": technician.technician_id,
            "tech_id": technician.tech_id,
            "technician_name": technician.technician_name,
            "technician_skill": technician.technician_skill,
            "technician_location": technician.technician_location,
            "technician_status": technician.technician_status,
            "tenant_id": technician.tenant_id,
        },
    }
