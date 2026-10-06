"""Staff-facing customer support management endpoints."""

from datetime import datetime, timezone
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import exists, or_
from sqlalchemy.orm import Session

from ..auth.dependencies import AuthenticatedUser, require_permission
from ..auth.rbac import Permission, UserRole
from ..database import get_db
from ..models import (
    CustomerSupportRequest,
    Job,
    Technician,
    User,
)
from ..portal_schemas import (
    CustomerSupportRequestAdminResponse,
    CustomerSupportRequestUpdate,
)
from ..services.enterprise_audit import AuditAction, audit_log


router = APIRouter(
    prefix="/api/admin/customer-support",
    tags=["Customer Support Management"],
)


def _require_support_staff(
    current_user: AuthenticatedUser = Depends(
        require_permission(Permission.CUSTOMERS_MANAGE)
    ),
) -> AuthenticatedUser:
    """Allow only Super Admin and Dispatcher staff to manage support."""

    allowed_roles = {
        UserRole.SUPER_ADMIN,
        UserRole.DISPATCHER,
    }

    if current_user.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Customer support management is restricted to Super Admin and Dispatcher roles.",
        )

    return current_user


def _support_query(
    db: Session,
    current_user: AuthenticatedUser,
):
    query = db.query(CustomerSupportRequest)

    if current_user.role != UserRole.SUPER_ADMIN:
        related_job_for_tenant = exists().where(
            Job.id == CustomerSupportRequest.related_job_id,
            Job.tenant_id == current_user.tenant_id,
        )

        query = query.filter(
            or_(
                CustomerSupportRequest.tenant_id
                == current_user.tenant_id,
                related_job_for_tenant,
            )
        )

    return query


def _build_admin_response(
    db: Session,
    support_request: CustomerSupportRequest,
) -> CustomerSupportRequestAdminResponse:
    customer = (
        db.query(User)
        .filter(
            User.id == support_request.customer_user_id,
            User.tenant_id == support_request.tenant_id,
        )
        .first()
    )

    customer_data = {
        "name": (
            customer.full_name
            if customer and customer.full_name
            else (
                f"{customer.first_name or ''} {customer.last_name or ''}".strip()
                if customer
                else "Customer"
            )
        ),
        "email": customer.email if customer else None,
        "phone_number": customer.phone_number if customer else None,
    }

    job_data = None

    if support_request.related_job_id is not None:
        job = (
            db.query(Job)
            .filter(Job.id == support_request.related_job_id)
            .first()
        )

        if job:
            technician_name = None
            technician_phone = None

            if job.assigned_technician_id is not None:
                technician = (
                    db.query(Technician)
                    .filter(
                        Technician.technician_id
                        == job.assigned_technician_id
                    )
                    .first()
                )

                if technician:
                    technician_name = technician.technician_name
                    technician_phone = technician.phone_number

            job_data = {
                "id": job.id,
                "customer_name": job.customer_name,
                "service_type": job.service_type,
                "issue_description": job.issue_description,
                "priority": job.priority,
                "status": job.status,
                "location": job.location,
                "site_address": job.site_address,
                "preferred_service_date": job.preferred_service_date,
                "contact_number": job.contact_number,
                "assigned_technician_name": technician_name,
                "assigned_technician_phone": technician_phone,
                "assigned_at": job.assigned_at,
                "en_route_at": job.en_route_at,
                "on_site_at": job.on_site_at,
                "completed_at": job.completed_at,
                "created_at": job.created_at,
                "updated_at": job.updated_at,
            }

    return CustomerSupportRequestAdminResponse(
        id=support_request.id,
        request_number=support_request.request_number,
        subject=support_request.subject,
        description=support_request.description,
        status=support_request.status,
        related_job_id=support_request.related_job_id,
        resolution_note=support_request.resolution_note,
        resolved_at=support_request.resolved_at,
        created_at=support_request.created_at,
        updated_at=support_request.updated_at,
        customer=customer_data,
        job=job_data,
    )


@router.get(
    "",
    response_model=list[CustomerSupportRequestAdminResponse],
)
async def list_customer_support_requests_for_staff(
    status_filter: str | None = Query(
        default=None,
        alias="status",
    ),
    current_user: AuthenticatedUser = Depends(
        _require_support_staff
    ),
    db: Session = Depends(get_db),
):
    """List support requests visible to the authenticated staff member."""

    if status_filter:
        status_value = status_filter.strip().upper()
        allowed = {"OPEN", "IN_PROGRESS", "RESOLVED", "CLOSED"}

        if status_value not in allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Status must be OPEN, IN_PROGRESS, RESOLVED, or CLOSED"
                ),
            )
    else:
        status_value = None

    query = _support_query(db, current_user)

    if status_value:
        query = query.filter(
            CustomerSupportRequest.status == status_value
        )

    requests = (
        query.order_by(
            CustomerSupportRequest.created_at.desc(),
            CustomerSupportRequest.id.desc(),
        )
        .limit(200)
        .all()
    )

    return [
        _build_admin_response(db, support_request)
        for support_request in requests
    ]


@router.get(
    "/{support_request_id}",
    response_model=CustomerSupportRequestAdminResponse,
)
async def get_customer_support_request_for_staff(
    support_request_id: int,
    current_user: AuthenticatedUser = Depends(
        _require_support_staff
    ),
    db: Session = Depends(get_db),
):
    """Return one staff-visible support request with customer/job context."""

    support_request = (
        _support_query(db, current_user)
        .filter(CustomerSupportRequest.id == support_request_id)
        .first()
    )

    if not support_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer support request not found",
        )

    return _build_admin_response(db, support_request)


@router.patch(
    "/{support_request_id}",
    response_model=CustomerSupportRequestAdminResponse,
)
async def update_customer_support_request_for_staff(
    support_request_id: int,
    data: CustomerSupportRequestUpdate,
    current_user: AuthenticatedUser = Depends(
        _require_support_staff
    ),
    db: Session = Depends(get_db),
):
    """Update support status/resolution and notify the customer."""

    support_request = (
        _support_query(db, current_user)
        .filter(CustomerSupportRequest.id == support_request_id)
        .first()
    )

    if not support_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer support request not found",
        )

    if data.status in {"RESOLVED", "CLOSED"} and not data.resolution_note:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A resolution note is required before resolving or closing a support request.",
        )

    now = datetime.now(timezone.utc)
    old_status = support_request.status

    support_request.status = data.status
    support_request.resolution_note = data.resolution_note

    if data.status in {"RESOLVED", "CLOSED"}:
        if support_request.resolved_at is None:
            support_request.resolved_at = now
        support_request.resolved_by = current_user.user_id
    else:
        support_request.resolved_at = None
        support_request.resolved_by = None

    audit_log(
        db,
        action=AuditAction.CUSTOMER_SUPPORT_UPDATED,
        tenant_id=support_request.tenant_id,
        user_id=current_user.user_id,
        role=current_user.role.value,
        entity_type="customer_support_request",
        entity_id=str(support_request.id),
        old_value={"status": old_status},
        new_value={
            "status": data.status,
            "resolution_note": data.resolution_note,
        },
    )

    from ..models_legacy import InAppNotification

    notification = InAppNotification(
        id=str(uuid.uuid4()),
        tenant_id=support_request.tenant_id,
        customer_user_id=str(support_request.customer_user_id),
        tech_id=None,
        job_id=(
            str(support_request.related_job_id)
            if support_request.related_job_id is not None
            else None
        ),
        type="CUSTOMER_SUPPORT_UPDATE",
        title="Customer Support Request Updated",
        body=(
            f"Support request {support_request.request_number} "
            f"is now {support_request.status}."
            + (
                f" Resolution: {support_request.resolution_note}"
                if support_request.resolution_note
                else ""
            )
        ),
        status="UNREAD",
        priority="HIGH",
        created_at=now,
        notification_metadata={
            "support_request_id": support_request.id,
            "status": support_request.status,
        },
    )

    db.add(notification)

    try:
        db.commit()
        db.refresh(support_request)
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to update customer support request",
        ) from exc

    return _build_admin_response(db, support_request)