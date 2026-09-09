
"""
Customer Portal API routes.

All endpoints are scoped to the authenticated customer.
Customers can only access their own profile, their own service requests,
and their own notifications.
"""

import uuid
import logging
import requests
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from math import radians, sin, cos, asin, sqrt
from typing import Optional

from ..database import get_db
from ..auth.dependencies import AuthenticatedUser, require_role
from ..auth.rbac import UserRole
from ..auth.password import hash_password, verify_password
from ..models import (
    Job, Technician, InAppNotification, ServiceRequest, Organization,
)
from ..models.customer_profile import CustomerProfileModel
from ..models.technician_profile import TechnicianProfile
from ..models.user import User
from ..portal_schemas import (
    CustomerProfileCreate,
    CustomerProfileUpdate,
    CustomerProfileResponse,
    ServiceRequestCreate,
    ServiceRequestUpdate,
    ServiceRequestResponse,
    CustomerDashboardResponse,
    CustomerJobTrackingResponse,
    ChangePasswordRequest,
)
from ..services.enterprise_audit import audit_log, AuditAction

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/customer",
    tags=["Customer Portal"],
)


# ──────────────────────────────────────────────────
# Location / Distance Helpers
# ──────────────────────────────────────────────────

def haversine_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """
    Calculate the great-circle distance between two coordinates in KM.
    """

    R = 6371.0

    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)

    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1))
        * cos(radians(lat2))
        * sin(dlon / 2) ** 2
    )

    return 2 * R * asin(sqrt(a))


def geocode_customer_location(address: str):
    """
    Convert a customer-entered address into latitude/longitude.

    Returns:
        {
            "longitude": float,
            "latitude": float
        }

    Returns None when geocoding fails or no location is found.
    """

    try:
        response = requests.get(
            "https://photon.komoot.io/api/",
            params={
                "q": address,
                "limit": 1,
            },
            headers={
                "User-Agent": "FieldOps/1.0",
            },
            timeout=10,
        )

        response.raise_for_status()

        data = response.json()
        features = data.get("features", [])

        if not features:
            return None

        coordinates = features[0]["geometry"]["coordinates"]

        return {
            "longitude": coordinates[0],
            "latitude": coordinates[1],
        }

    except (requests.RequestException, ValueError, KeyError, TypeError):
        logger.exception(
            "Failed to geocode customer location: %s",
            address,
        )
        return None


# ──────────────────────────────────────────────────
# Profile Endpoints
# ──────────────────────────────────────────────────

@router.get("/profile", response_model=CustomerProfileResponse)
async def get_customer_profile(
    current_user: AuthenticatedUser = Depends(
        require_role(UserRole.CUSTOMER)
    ),
    db: Session = Depends(get_db),
):
    """Get the current customer's profile."""

    profile = db.query(CustomerProfileModel).filter(
        CustomerProfileModel.user_id == current_user.user_id,
        CustomerProfileModel.tenant_id == current_user.tenant_id,
    ).first()

    user = db.query(User).filter(
        User.id == current_user.user_id
    ).first()

    if not profile:
        return CustomerProfileResponse(
            id="",
            user_id=current_user.user_id,
            tenant_id=current_user.tenant_id,
            full_name=user.full_name if user else "",
            mobile_number=user.phone_number if user else "",
            profile_completed=False,
            email=user.email if user else "",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    return CustomerProfileResponse(
        id=profile.id,
        user_id=profile.user_id,
        tenant_id=profile.tenant_id,
        full_name=profile.full_name,
        mobile_number=profile.mobile_number,
        address=profile.address,
        city=profile.city,
        state=profile.state,
        pincode=profile.pincode,
        company_name=profile.company_name,
        profile_completed=profile.profile_completed,
        email=user.email if user else None,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


@router.post(
    "/profile",
    response_model=CustomerProfileResponse,
    status_code=201,
)
async def create_customer_profile(
    data: CustomerProfileCreate,
    request: Request,
    current_user: AuthenticatedUser = Depends(
        require_role(UserRole.CUSTOMER)
    ),
    db: Session = Depends(get_db),
):
    """Create customer profile (first-time setup)."""

    existing = db.query(CustomerProfileModel).filter(
        CustomerProfileModel.user_id == current_user.user_id,
        CustomerProfileModel.tenant_id == current_user.tenant_id,
    ).first()

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Profile already exists. Use PUT to update.",
        )

    profile = CustomerProfileModel(
        id=str(uuid.uuid4()),
        user_id=current_user.user_id,
        tenant_id=current_user.tenant_id,
        full_name=data.full_name,
        mobile_number=data.mobile_number,
        address=data.address,
        city=data.city,
        state=data.state,
        pincode=data.pincode,
        company_name=data.company_name,
        profile_completed=True,
    )

    db.add(profile)

    audit_log(
        db,
        action=AuditAction.PROFILE_CREATED,
        tenant_id=current_user.tenant_id,
        user_id=current_user.user_id,
        role=current_user.role.value,
        entity_type="customer_profile",
        entity_id=profile.id,
        new_value={
            "full_name": data.full_name
        },
        request=request,
    )

    db.commit()
    db.refresh(profile)

    user = db.query(User).filter(
        User.id == current_user.user_id
    ).first()

    return CustomerProfileResponse(
        id=profile.id,
        user_id=profile.user_id,
        tenant_id=profile.tenant_id,
        full_name=profile.full_name,
        mobile_number=profile.mobile_number,
        address=profile.address,
        city=profile.city,
        state=profile.state,
        pincode=profile.pincode,
        company_name=profile.company_name,
        profile_completed=profile.profile_completed,
        email=user.email if user else None,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


@router.put(
    "/profile",
    response_model=CustomerProfileResponse,
)
async def update_customer_profile(
    data: CustomerProfileUpdate,
    request: Request,
    current_user: AuthenticatedUser = Depends(
        require_role(UserRole.CUSTOMER)
    ),
    db: Session = Depends(get_db),
):
    """Update customer profile."""

    profile = db.query(CustomerProfileModel).filter(
        CustomerProfileModel.user_id == current_user.user_id,
        CustomerProfileModel.tenant_id == current_user.tenant_id,
    ).first()

    if not profile:
        raise HTTPException(
            status_code=404,
            detail="Profile not found. Create it first.",
        )

    update_data = data.model_dump(
        exclude_unset=True
    )

    for key, value in update_data.items():
        if value is not None:
            setattr(profile, key, value)

    profile.profile_completed = True

    audit_log(
        db,
        action=AuditAction.PROFILE_UPDATED,
        tenant_id=current_user.tenant_id,
        user_id=current_user.user_id,
        role=current_user.role.value,
        entity_type="customer_profile",
        entity_id=profile.id,
        new_value=update_data,
        request=request,
    )

    db.commit()
    db.refresh(profile)

    user = db.query(User).filter(
        User.id == current_user.user_id
    ).first()

    return CustomerProfileResponse(
        id=profile.id,
        user_id=profile.user_id,
        tenant_id=profile.tenant_id,
        full_name=profile.full_name,
        mobile_number=profile.mobile_number,
        address=profile.address,
        city=profile.city,
        state=profile.state,
        pincode=profile.pincode,
        company_name=profile.company_name,
        profile_completed=profile.profile_completed,
        email=user.email if user else None,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


# ──────────────────────────────────────────────────
# Change Password
# ──────────────────────────────────────────────────

@router.post("/change-password")
async def change_password(
    data: ChangePasswordRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(
        require_role(UserRole.CUSTOMER)
    ),
    db: Session = Depends(get_db),
):
    """Change customer password."""

    user = db.query(User).filter(
        User.id == current_user.user_id
    ).first()

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    if not verify_password(
        data.current_password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=400,
            detail="Current password is incorrect",
        )

    user.password_hash = hash_password(
        data.new_password
    )

    audit_log(
        db,
        action=AuditAction.PASSWORD_CHANGED,
        tenant_id=current_user.tenant_id,
        user_id=current_user.user_id,
        role=current_user.role.value,
        entity_type="user",
        entity_id=current_user.user_id,
        request=request,
    )

    db.commit()

    return {
        "message": "Password changed successfully"
    }


# ──────────────────────────────────────────────────
# Service Requests
# ──────────────────────────────────────────────────

def _generate_request_number() -> str:
    """Generate a unique service request number."""

    timestamp = datetime.now(
        timezone.utc
    ).strftime("%Y%m%d%H%M%S")

    short_id = str(uuid.uuid4())[:6].upper()

    return f"SR-{timestamp}-{short_id}"


@router.get(
    "/service-requests",
    response_model=list[ServiceRequestResponse],
)
async def list_service_requests(
    status_filter: Optional[str] = Query(
        None,
        alias="status",
    ),
    current_user: AuthenticatedUser = Depends(
        require_role(UserRole.CUSTOMER)
    ),
    db: Session = Depends(get_db),
):
    """List customer's own service requests."""

    query = db.query(ServiceRequest).filter(
        ServiceRequest.customer_user_id == current_user.user_id,
        ServiceRequest.tenant_id == current_user.tenant_id,
    )

    if status_filter:
        query = query.filter(
            func.lower(ServiceRequest.status)
            == status_filter.lower()
        )
    else:
        # CANCELLED requests should not appear in My Requests.
        # Keep them in DB for Service History.
        query = query.filter(
            func.lower(ServiceRequest.status)
            != "cancelled"
        )

    return query.order_by(
        ServiceRequest.created_at.desc()
    ).all()


@router.post(
    "/service-requests",
    response_model=ServiceRequestResponse,
    status_code=201,
)
async def create_service_request(
    data: ServiceRequestCreate,
    request: Request,
    current_user: AuthenticatedUser = Depends(
        require_role(UserRole.CUSTOMER)
    ),
    db: Session = Depends(get_db),
):
    """
    Create a new service request.

    Routing flow:

    Customer address
        ↓
    Geocode customer address
        ↓
    Get required skill from service type
        ↓
    Find ALL organizations having a technician with that skill
        ↓
    Ignore organizations without coordinates
        ↓
    Calculate distance from customer to every capable organization
        ↓
    Select nearest organization
        ↓
    Create Job with selected organization's tenant_id
        ↓
    Create ServiceRequest under customer's own tenant
    """

    from ..utils import map_service_type_to_skill

    # ──────────────────────────────────────────────
    # Customer details
    # ──────────────────────────────────────────────

    user_rec = db.query(User).filter(
        User.id == current_user.user_id
    ).first()

    cust_first = (
        (
            user_rec.first_name
            if user_rec and user_rec.first_name
            else ""
        ).strip()
    )

    cust_last = (
        (
            user_rec.last_name
            if user_rec and user_rec.last_name
            else ""
        ).strip()
    )

    cust_name = (
        f"{cust_first} {cust_last}".strip()
        or (
            user_rec.email
            if user_rec
            else "Customer"
        )
    )

    cust_email = (
        user_rec.email
        if user_rec
        else None
    )

    # ──────────────────────────────────────────────
    # Determine required technician skill
    # ──────────────────────────────────────────────

    req_skill = data.service_type or "General"

    # ──────────────────────────────────────────────
    # Customer location
    # ──────────────────────────────────────────────

    if not data.location or not data.location.strip():
        raise HTTPException(
            status_code=400,
            detail=(
                "Customer location is required "
                "for organization assignment."
            ),
        )

    customer_address = data.location.strip()

# Use exact GPS coordinates from customer current location.
    if data.site_latitude is not None and data.site_longitude is not None:
        customer_latitude = data.site_latitude
        customer_longitude = data.site_longitude
    else:
        raise HTTPException(
            status_code=400,
            detail="Customer GPS location is required.",
        )
    # ──────────────────────────────────────────────
    # Find all organizations having required skill
    # ──────────────────────────────────────────────

    capable_technician_tenants = (
    db.query(Technician.tenant_id)
    .filter(
        Technician.tenant_id.isnot(None),
        Technician.technician_skill.isnot(None),
        func.lower(
            Technician.technician_skill
        ).contains(req_skill.lower()),
    )
    .distinct()
    .all()
)

    capable_tenant_ids = {
        tenant_id
        for (tenant_id,) in capable_technician_tenants
        if tenant_id
    }

    if not capable_tenant_ids:
        raise HTTPException(
            status_code=400,
            detail=(
                f"No organization is available "
                f"with the required skill "
                f"'{req_skill}'."
            ),
        )

    # ──────────────────────────────────────────────
    # Get organizations with valid coordinates
    # ──────────────────────────────────────────────

    organizations = (
        db.query(Organization)
        .filter(
            Organization.id.in_(
                capable_tenant_ids
            ),
            Organization.site_latitude.isnot(None),
            Organization.site_longitude.isnot(None),
        )
        .all()
    )

    if not organizations:
        raise HTTPException(
            status_code=400,
            detail=(
                f"No organization is available "
                f"with the required skill "
                f"'{req_skill}' and a valid location."
            ),
        )

    # ──────────────────────────────────────────────
    # Compare customer against ALL organizations
    # ──────────────────────────────────────────────

    nearest_organization = min(
        organizations,
        key=lambda organization: haversine_km(
            customer_latitude,
            customer_longitude,
            organization.site_latitude,
            organization.site_longitude,
        ),
    )

    selected_tenant_id = (
        nearest_organization.id
    )

    # ──────────────────────────────────────────────
    # Create Job
    # ──────────────────────────────────────────────
    #
    # IMPORTANT:
    #
    # ServiceRequest tenant_id
    #     = customer's tenant
    #
    # Job tenant_id
    #     = selected service organization's tenant
    #
    # This is intentional.
    # ──────────────────────────────────────────────

    new_job = Job(
        tenant_id=selected_tenant_id,
        customer_name=cust_name,
        location=customer_address,
        site_latitude=customer_latitude,
        site_longitude=customer_longitude,
        site_address=customer_address,
        issue_description=(
            f"{data.title}: {data.description}"
        ),
        priority=data.priority or "MEDIUM",
        service_type=data.service_type or "General",
        contact_number=data.contact_number or "N/A",
        preferred_service_date=(
            data.preferred_visit_date
            or datetime.now(
                timezone.utc
            ).date()
        ),
        required_skill=req_skill,
        status="CREATED",
        customer_id=str(
            current_user.user_id
        ),
        customer_email=cust_email,
    )

    db.add(new_job)

    # Get Job ID before creating ServiceRequest.
    db.flush()

    # ──────────────────────────────────────────────
    # Create Service Request
    # ──────────────────────────────────────────────

    sr = ServiceRequest(
        request_number=_generate_request_number(),
        customer_user_id=current_user.user_id,
        tenant_id=current_user.tenant_id,
        title=data.title,
        description=data.description,
        service_type=data.service_type,
        priority=data.priority,
        preferred_visit_date=data.preferred_visit_date,
        images=data.images,
        location=data.location,
        contact_number=data.contact_number,
        status="PENDING",
        linked_job_id=new_job.id,
    )

    db.add(sr)

    # ──────────────────────────────────────────────
    # Audit
    # ──────────────────────────────────────────────

    audit_log(
        db,
        action=AuditAction.SERVICE_REQUEST_CREATED,
        tenant_id=current_user.tenant_id,
        user_id=current_user.user_id,
        role=current_user.role.value,
        entity_type="service_request",
        entity_id=sr.request_number,
        new_value={
            "title": data.title,
            "priority": data.priority,
            "job_id": new_job.id,
            "selected_organization_id": (
                selected_tenant_id
            ),
            "required_skill": req_skill,
            "customer_latitude": (
                customer_latitude
            ),
            "customer_longitude": (
                customer_longitude
            ),
        },
        request=request,
    )

    db.commit()

    db.refresh(sr)

    return sr


@router.get(
    "/service-requests/{sr_id}",
    response_model=ServiceRequestResponse,
)
async def get_service_request(
    sr_id: int,
    current_user: AuthenticatedUser = Depends(
        require_role(UserRole.CUSTOMER)
    ),
    db: Session = Depends(get_db),
):
    """View a specific service request (own only)."""

    sr = db.query(ServiceRequest).filter(
        ServiceRequest.id == sr_id,
        ServiceRequest.customer_user_id
        == current_user.user_id,
        ServiceRequest.tenant_id
        == current_user.tenant_id,
    ).first()

    if not sr:
        raise HTTPException(
            status_code=404,
            detail="Service request not found",
        )

    return sr


@router.put(
    "/service-requests/{sr_id}",
    response_model=ServiceRequestResponse,
)
async def update_service_request(
    sr_id: int,
    data: ServiceRequestUpdate,
    request: Request,
    current_user: AuthenticatedUser = Depends(
        require_role(UserRole.CUSTOMER)
    ),
    db: Session = Depends(get_db),
):
    """Edit a pending service request."""

    sr = db.query(ServiceRequest).filter(
        ServiceRequest.id == sr_id,
        ServiceRequest.customer_user_id
        == current_user.user_id,
        ServiceRequest.tenant_id
        == current_user.tenant_id,
    ).first()

    if not sr:
        raise HTTPException(
            status_code=404,
            detail="Service request not found",
        )

    if sr.status not in ("PENDING",):
        raise HTTPException(
            status_code=400,
            detail="Can only edit pending requests",
        )

    update_data = data.model_dump(
        mode="json",
        exclude_unset=True,
    )

    for key, value in update_data.items():
        if value is not None:
            setattr(
                sr,
                key,
                value,
            )

    audit_log(
        db,
        action=AuditAction.SERVICE_REQUEST_UPDATED,
        tenant_id=current_user.tenant_id,
        user_id=current_user.user_id,
        role=current_user.role.value,
        entity_type="service_request",
        entity_id=str(sr_id),
        new_value=update_data,
        request=request,
    )

    db.commit()

    db.refresh(sr)

    return sr


@router.post(
    "/service-requests/{sr_id}/cancel"
)
async def cancel_service_request(
    sr_id: int,
    request: Request,
    current_user: AuthenticatedUser = Depends(
        require_role(UserRole.CUSTOMER)
    ),
    db: Session = Depends(get_db),
):
    """Cancel a pending service request."""

    sr = db.query(ServiceRequest).filter(
        ServiceRequest.id == sr_id,
        ServiceRequest.customer_user_id
        == current_user.user_id,
        ServiceRequest.tenant_id
        == current_user.tenant_id,
    ).first()

    if not sr:
        raise HTTPException(
            status_code=404,
            detail="Service request not found",
        )

    if sr.status not in ("PENDING",):
        raise HTTPException(
            status_code=400,
            detail="Can only cancel pending requests",
        )

    sr.status = "CANCELLED"

    sr.cancelled_at = datetime.now(
        timezone.utc
    )

    audit_log(
        db,
        action=AuditAction.SERVICE_REQUEST_CANCELLED,
        tenant_id=current_user.tenant_id,
        user_id=current_user.user_id,
        role=current_user.role.value,
        entity_type="service_request",
        entity_id=str(sr_id),
        request=request,
    )

    db.commit()

    return {
        "message": "Service request cancelled",
        "id": sr_id,
    }


# ──────────────────────────────────────────────────
# Job Tracking
# ──────────────────────────────────────────────────

@router.get(
    "/jobs",
    response_model=list[CustomerJobTrackingResponse],
)
async def track_customer_jobs(
    current_user: AuthenticatedUser = Depends(
        require_role(UserRole.CUSTOMER)
    ),
    db: Session = Depends(get_db),
):
    """
    Track jobs related to the authenticated customer's
    service requests.

    IMPORTANT:
    Job.tenant_id can now belong to a different organization
    because routing selects the nearest capable organization.

    Therefore Job queries here must use customer ownership,
    not current_user.tenant_id.
    """

    # ──────────────────────────────────────────────
    # Get jobs linked to customer's service requests
    # ──────────────────────────────────────────────

    service_request_job_ids = (
        db.query(ServiceRequest.linked_job_id)
        .filter(
            ServiceRequest.customer_user_id
            == current_user.user_id,
            ServiceRequest.tenant_id
            == current_user.tenant_id,
            ServiceRequest.linked_job_id.isnot(None),
        )
        .all()
    )

    job_ids = [
        sr[0]
        for sr in service_request_job_ids
    ]

    # ──────────────────────────────────────────────
    # Also include jobs directly linked by customer_id
    # ──────────────────────────────────────────────
    #
    # DO NOT filter by current_user.tenant_id.
    #
    # Job.tenant_id = selected organization tenant.
    # Job.customer_id = customer who created the job.
    # ──────────────────────────────────────────────

    direct_jobs = db.query(Job).filter(
        Job.customer_id
        == str(current_user.user_id),
    ).all()

    # ──────────────────────────────────────────────
    # Linked jobs
    # ──────────────────────────────────────────────

    linked_jobs = []

    if job_ids:
        linked_jobs = db.query(Job).filter(
            Job.id.in_(job_ids),
        ).all()

    # ──────────────────────────────────────────────
    # Remove duplicates
    # ──────────────────────────────────────────────

    all_jobs = {
        job.id: job
        for job in direct_jobs
    }

    for job in linked_jobs:
        all_jobs[job.id] = job

    # ──────────────────────────────────────────────
    # Build response
    # ──────────────────────────────────────────────

    results = []

    for job in all_jobs.values():

        tech_name = None
        tech_photo = None
        tech_phone = None

        if job.assigned_technician_id:

            # Technician belongs to the organization
            # that currently owns the Job.
            tech = db.query(Technician).filter(
                Technician.technician_id
                == job.assigned_technician_id,
                Technician.tenant_id
                == job.tenant_id,
            ).first()

            if tech:

                tech_name = tech.technician_name
                tech_phone = tech.phone_number

                # Try to get photo from TechnicianProfile.
                if tech.tech_id:

                    tp = db.query(
                        TechnicianProfile
                    ).filter(
                        TechnicianProfile.user_id
                        == tech.tech_id
                    ).first()

                    if tp:
                        tech_photo = tp.profile_photo

        results.append(
            CustomerJobTrackingResponse(
                id=job.id,
                customer_name=job.customer_name,
                status=job.status,
                priority=job.priority,
                service_type=job.service_type,
                location=job.location,
                assigned_technician_name=tech_name,
                assigned_technician_photo=tech_photo,
                assigned_technician_phone=tech_phone,
                created_at=job.created_at,
                completed_at=job.completed_at,
            )
        )

    return results


@router.get(
    "/jobs/{job_id}",
    response_model=CustomerJobTrackingResponse,
)
async def get_customer_job_detail(
    job_id: int,
    current_user: AuthenticatedUser = Depends(
        require_role(UserRole.CUSTOMER)
    ),
    db: Session = Depends(get_db),
):
    """
    Get job detail only when it belongs to
    the authenticated customer.
    """

    # ──────────────────────────────────────────────
    # Primary ownership check
    # ──────────────────────────────────────────────

    job = db.query(Job).filter(
        Job.id == job_id,
        Job.customer_id
        == str(current_user.user_id),
    ).first()

    # ──────────────────────────────────────────────
    # Backward compatibility
    # ──────────────────────────────────────────────
    #
    # Older jobs may not have customer_id.
    # In that case check through ServiceRequest.
    # ──────────────────────────────────────────────

    if not job:

        job = (
            db.query(Job)
            .join(
                ServiceRequest,
                ServiceRequest.linked_job_id
                == Job.id,
            )
            .filter(
                Job.id == job_id,
                ServiceRequest.customer_user_id
                == current_user.user_id,
                ServiceRequest.tenant_id
                == current_user.tenant_id,
            )
            .first()
        )

    if not job:
        raise HTTPException(
            status_code=404,
            detail="Job not found",
        )

    # ──────────────────────────────────────────────
    # Technician details
    # ──────────────────────────────────────────────

    tech_name = None
    tech_photo = None
    tech_phone = None

    if job.assigned_technician_id:

        # Technician belongs to the organization
        # that owns the Job.
        tech = db.query(Technician).filter(
            Technician.technician_id
            == job.assigned_technician_id,
            Technician.tenant_id
            == job.tenant_id,
        ).first()

        if tech:

            tech_name = tech.technician_name
            tech_phone = tech.phone_number

            if tech.tech_id:

                tp = db.query(
                    TechnicianProfile
                ).filter(
                    TechnicianProfile.user_id
                    == tech.tech_id
                ).first()

                if tp:
                    tech_photo = tp.profile_photo

    return CustomerJobTrackingResponse(
        id=job.id,
        customer_name=job.customer_name,
        status=job.status,
        priority=job.priority,
        service_type=job.service_type,
        location=job.location,
        assigned_technician_name=tech_name,
        assigned_technician_photo=tech_photo,
        assigned_technician_phone=tech_phone,
        created_at=job.created_at,
        completed_at=job.completed_at,
    )


# ──────────────────────────────────────────────────
# Service History
# ──────────────────────────────────────────────────

@router.get(
    "/service-history",
    response_model=list[ServiceRequestResponse],
)
async def get_service_history(
    current_user: AuthenticatedUser = Depends(
        require_role(UserRole.CUSTOMER)
    ),
    db: Session = Depends(get_db),
):
    """Get completed/cancelled service requests."""

    return db.query(ServiceRequest).filter(
        ServiceRequest.customer_user_id
        == current_user.user_id,
        ServiceRequest.tenant_id
        == current_user.tenant_id,
        func.lower(
            ServiceRequest.status
        ).in_(
            [
                "completed",
                "cancelled",
            ]
        ),
    ).order_by(
        ServiceRequest.updated_at.desc()
    ).all()


# ──────────────────────────────────────────────────
# Notifications
# ──────────────────────────────────────────────────

@router.get("/notifications")
async def get_notifications(
    current_user: AuthenticatedUser = Depends(
        require_role(UserRole.CUSTOMER)
    ),
    db: Session = Depends(get_db),
):
    """Get customer notifications."""

    notifications = db.query(
        InAppNotification
    ).filter(
        InAppNotification.tenant_id
        == current_user.tenant_id,
        InAppNotification.tech_id
        == current_user.user_id,
    ).order_by(
        InAppNotification.created_at.desc()
    ).limit(100).all()

    unread_count = db.query(
        InAppNotification
    ).filter(
        InAppNotification.tech_id
        == current_user.user_id,
        InAppNotification.tenant_id
        == current_user.tenant_id,
        InAppNotification.status == "UNREAD",
    ).count()

    return {
        "notifications": [
            {
                "id": str(n.id),
                "type": n.type,
                "title": n.title,
                "message": n.body,
                "isRead": n.status != "UNREAD",
                "createdAt": (
                    n.created_at.isoformat()
                    if n.created_at
                    else None
                ),
                "jobId": n.job_id,
            }
            for n in notifications
        ],
        "unread_count": unread_count,
    }


@router.put(
    "/notifications/{notification_id}/read"
)
async def mark_notification_read(
    notification_id: str,
    current_user: AuthenticatedUser = Depends(
        require_role(UserRole.CUSTOMER)
    ),
    db: Session = Depends(get_db),
):
    """Mark one customer-owned notification as read."""

    notification = db.query(
        InAppNotification
    ).filter(
        InAppNotification.id == notification_id,
        InAppNotification.tenant_id
        == current_user.tenant_id,
        InAppNotification.tech_id
        == current_user.user_id,
    ).first()

    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )

    notification.status = "READ"

    notification.read_at = datetime.now(
        timezone.utc
    )

    try:
        db.commit()

    except Exception:
        db.rollback()

        logger.exception(
            "Failed to mark notification %s as read",
            notification_id,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to mark notification as read",
        )

    return {
        "message": "Marked as read"
    }


@router.put(
    "/notifications/read-all"
)
async def mark_all_read(
    current_user: AuthenticatedUser = Depends(
        require_role(UserRole.CUSTOMER)
    ),
    db: Session = Depends(get_db),
):
    """Mark all notifications as read."""

    db.query(
        InAppNotification
    ).filter(
        InAppNotification.tenant_id
        == current_user.tenant_id,
        InAppNotification.tech_id
        == current_user.user_id,
        InAppNotification.status == "UNREAD",
    ).update(
        {
            "status": "READ",
            "read_at": datetime.now(
                timezone.utc
            ),
        }
    )

    db.commit()

    return {
        "message": "All notifications marked as read"
    }


# ──────────────────────────────────────────────────
# Dashboard
# ──────────────────────────────────────────────────

@router.get(
    "/dashboard",
    response_model=CustomerDashboardResponse,
)
async def get_customer_dashboard(
    current_user: AuthenticatedUser = Depends(
        require_role(UserRole.CUSTOMER)
    ),
    db: Session = Depends(get_db),
):
    """Get customer dashboard statistics."""

    base = db.query(ServiceRequest).filter(
        ServiceRequest.customer_user_id
        == current_user.user_id,
        ServiceRequest.tenant_id
        == current_user.tenant_id,
    )

    total = base.count()

    pending = base.filter(
        ServiceRequest.status == "PENDING"
    ).count()

    active = base.filter(
        ServiceRequest.status.in_(
            [
                "ASSIGNED",
                "IN_PROGRESS",
            ]
        )
    ).count()

    completed = base.filter(
        ServiceRequest.status == "COMPLETED"
    ).count()

    return CustomerDashboardResponse(
        total_requests=total,
        pending_requests=pending,
        active_jobs=active,
        completed_jobs=completed,
    )