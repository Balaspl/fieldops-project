from typing import List, Optional
from datetime import datetime, timezone
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from ..database import get_db
from .. import models, schemas, utils
from ..auth.dependencies import get_current_user_or_tenant, AuthenticatedUser

router = APIRouter(
    tags=["Assignment"]
)


@router.get(
    "/technicians/match-skill",
    response_model=List[schemas.TechnicianResponse]
)
def match_skill(
    job_type: str,
    user_tenant: tuple[Optional[AuthenticatedUser], str] = Depends(
        get_current_user_or_tenant
    ),
    db: Session = Depends(get_db)
):
    """
    Find available technicians matching the required skill.
    Falls back gracefully if exact match returns no results.
    """

    user, tenant_id = user_tenant

    pattern = f"%{job_type.strip()}%"

    tech_query = db.query(models.Technician).filter(
        models.Technician.technician_skill.ilike(pattern)
    )

    # Normal users are restricted to their tenant.
    # Super Admin can see technicians across tenants.
    if not user or not user.is_super_admin:
        tech_query = tech_query.filter(
            models.Technician.tenant_id == tenant_id
        )

    technicians = tech_query.all()

    if not technicians:
        fallback_query = db.query(models.Technician)

        if not user or not user.is_super_admin:
            fallback_query = fallback_query.filter(
                models.Technician.tenant_id == tenant_id
            )

        technicians = fallback_query.all()

    return technicians


@router.get(
    "/technicians/nearest",
    response_model=schemas.NearestTechnicianResponse
)
def get_nearest_technician(
    job_id: int,
    user_tenant: tuple[Optional[AuthenticatedUser], str] = Depends(
        get_current_user_or_tenant
    ),
    db: Session = Depends(get_db)
):
    """
    Identify the nearest available technician based on skill and location.
    """

    user, tenant_id = user_tenant

    job_query = db.query(models.Job).filter(
        models.Job.id == job_id
    )

    # Normal users can only access jobs from their tenant.
    # Super Admin can access jobs across tenants.
    if not user or not user.is_super_admin:
        job_query = job_query.filter(
            models.Job.tenant_id == tenant_id
        )

    job = job_query.first()

    if not job:
        raise HTTPException(
            status_code=404,
            detail="Job not found"
        )

    # For Super Admin, technicians can come from any tenant.
    # For normal users, restrict technicians to their tenant.
    tech_query = db.query(models.Technician).filter(
        models.Technician.technician_skill == job.required_skill,
        models.Technician.technician_status.in_(
            ["AVAILABLE", "ASSIGNED", "Available", "Assigned"]
        ),
        models.Technician.current_jobs < models.Technician.max_jobs
    )

    if not user or not user.is_super_admin:
        tech_query = tech_query.filter(
            models.Technician.tenant_id == tenant_id
        )

    technicians = tech_query.all()

    if not technicians:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No available technicians found with skill: "
                f"{job.required_skill}"
            )
        )

    # Calculate distances.
    tech_distances = []

    for tech in technicians:
        dist = utils.calculate_distance(
            job.location,
            tech.technician_location
        )

        tech_distances.append((tech, dist))

    # Sort by distance.
    tech_distances.sort(
        key=lambda x: x[1]
    )

    nearest_tech, min_dist = tech_distances[0]

    return {
        "technician": nearest_tech,
        "distance": min_dist
    }


@router.post("/assign-job")
@router.post("/assign-technician")
def assign_job(
    assignment: schemas.TechnicianAssignment,
    user_tenant: tuple[Optional[AuthenticatedUser], str] = Depends(
        get_current_user_or_tenant
    ),
    db: Session = Depends(get_db)
):
    """
    Assign a technician to a job.

    Rules:
    - Super Admin can assign technicians across tenants.
    - Normal users remain tenant restricted.
    - Duplicate assignments are prevented.
    - Technician availability/workload is validated.
    - Assignment notification is created for the technician.
    """

    user, tenant_id = user_tenant

    try:

        # ============================================================
        # 1. Parse Job ID
        # ============================================================

        job_id_str = str(assignment.job_id)

        if job_id_str.upper().startswith("JOB"):
            job_id = int(job_id_str[3:])
        else:
            job_id = int(job_id_str)

        # ============================================================
        # 2. Fetch Job
        # ============================================================

        job_query = db.query(models.Job).filter(
            models.Job.id == job_id
        )

        # Super Admin can access jobs across tenants.
        # Normal users remain tenant-isolated.
        if not user or not user.is_super_admin:
            job_query = job_query.filter(
                models.Job.tenant_id == tenant_id
            )

        job = job_query.first()

        if not job:
            raise HTTPException(
                status_code=404,
                detail="Job not found"
            )

        # ============================================================
        # 3. Prevent Duplicate Assignment
        # ============================================================

        if job.assigned_technician_id:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Job #{job.id} is already assigned to "
                    f"technician #{job.assigned_technician_id}"
                )
            )

        # ============================================================
        # 4. Find Technician
        # ============================================================

        technician = None

        if assignment.technician_id is not None:

            tech_val = assignment.technician_id

            # --------------------------------------------------------
            # 4A. Find by numeric technician_id
            # --------------------------------------------------------

            if (
                isinstance(tech_val, int)
                or (
                    isinstance(tech_val, str)
                    and tech_val.isdigit()
                )
            ):

                t_q = db.query(models.Technician).filter(
                    models.Technician.technician_id == int(tech_val)
                )

                # IMPORTANT:
                # Super Admin can assign across tenants.
                # Normal users can only assign technicians
                # from their own tenant.
                if not user or not user.is_super_admin:
                    t_q = t_q.filter(
                        models.Technician.tenant_id == tenant_id
                    )

                technician = t_q.first()

            # --------------------------------------------------------
            # 4B. Find by tech_id
            # --------------------------------------------------------

            if not technician:

                t_q = db.query(models.Technician).filter(
                    models.Technician.tech_id == str(tech_val)
                )

                # IMPORTANT:
                # Super Admin can assign across tenants.
                # Normal users remain tenant restricted.
                if not user or not user.is_super_admin:
                    t_q = t_q.filter(
                        models.Technician.tenant_id == tenant_id
                    )

                technician = t_q.first()

            if not technician:
                raise HTTPException(
                    status_code=404,
                    detail="Technician not found"
                )

        # ============================================================
        # 5. Auto Assignment
        # ============================================================

        elif assignment.job_type:

            t_q = db.query(models.Technician).filter(
                models.Technician.technician_skill == assignment.job_type,
                models.Technician.technician_status.in_(
                    [
                        "AVAILABLE",
                        "ASSIGNED",
                        "Available",
                        "Assigned"
                    ]
                ),
                models.Technician.current_jobs
                < models.Technician.max_jobs
            )

            # Normal users remain tenant restricted.
            # Super Admin can auto-assign across tenants.
            if not user or not user.is_super_admin:
                t_q = t_q.filter(
                    models.Technician.tenant_id == tenant_id
                )

            technicians = t_q.all()

            if not technicians:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"No available technicians found with skill: "
                        f"{assignment.job_type}"
                    )
                )

            technicians.sort(
                key=lambda t: t.current_jobs
            )

            technician = technicians[0]

        else:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Either technician_id or job_type "
                    "must be provided"
                )
            )

        # ============================================================
        # 6. Validate Technician
        # ============================================================

        from ..validation import validate_technician_for_assignment

        validate_technician_for_assignment(
            technician,
            job
        )

        # ============================================================
        # 7. Perform Assignment
        # ============================================================

        job.assigned_technician_id = technician.technician_id
        job.status = "ASSIGNED"

        # Update customer ServiceRequest status
        service_request = db.query(models.ServiceRequest).filter(
            models.ServiceRequest.linked_job_id == job.id
        ).first()

        if service_request:
            service_request.status = "ASSIGNED"

        # Assignment metadata.
        if hasattr(job, "assigned_at"):
            job.assigned_at = datetime.now(timezone.utc)

        if hasattr(job, "assigned_by") and user:
            job.assigned_by = str(user.user_id)

        print("========== BEFORE WORKLOAD UPDATE ==========")
        print("Job ID:", job.id)
        print("Job tenant ID:", job.tenant_id)
        print("Technician ID:", technician.technician_id)
        print("Technician tech_id:", technician.tech_id)
        print("Technician tenant ID:", technician.tenant_id)
        print(
            "Job assigned_technician_id:",
            job.assigned_technician_id
        )
        print("Job status:", job.status)

        # ============================================================
        # 8. Update Technician Workload
        # ============================================================

        from ..workload_utils import update_workload_count

        update_workload_count(
            db,
            technician.technician_id,
            1
        )

        print("========== AFTER WORKLOAD UPDATE ==========")
        print("Job ID:", job.id)
        print(
            "Job assigned_technician_id:",
            job.assigned_technician_id
        )
        print("Job status:", job.status)

        # ============================================================
        # 9. Create Technician Notification
        # ============================================================

        notification = models.InAppNotification(
            id=str(uuid.uuid4()),

            # IMPORTANT:
            # Notification belongs to the technician's tenant,
            # not the customer's job tenant.
            tenant_id=technician.tenant_id,

            # This identifies the technician account.
            tech_id=technician.tech_id,

            # The actual job being assigned.
            job_id=str(job.id),

            type="JOB_ASSIGNED",
            title="New Job Assigned",

            body=(
                f"You have been assigned to Job #{job.id}: "
                f"{job.service_type or 'Service Request'} "
                f"at {job.location or 'Customer location'}."
            ),

            status="UNREAD",
            priority=job.priority or "HIGH",
            created_at=datetime.now(timezone.utc),
        )

        db.add(notification)

        print("========== NOTIFICATION CREATED ==========")
        print("Notification ID:", notification.id)
        print("Notification tech_id:", notification.tech_id)
        print("Notification tenant_id:", notification.tenant_id)
        print("Notification job_id:", notification.job_id)
        print("Notification type:", notification.type)

        # ============================================================
        # 10. Commit Everything
        # ============================================================

        db.commit()

        print("========== COMMIT SUCCESS ==========")

        # ============================================================
        # 11. Refresh Objects
        # ============================================================

        db.refresh(job)
        db.refresh(technician)

        print("========== AFTER REFRESH ==========")
        print(
            "Job assigned_technician_id:",
            job.assigned_technician_id
        )
        print("Job status:", job.status)

        # ============================================================
        # 12. Return Response
        # ============================================================

        return {
            "message": "Technician assigned successfully",
            "job_id": job.id,
            "assigned_technician": {
                "id": technician.technician_id,
                "name": technician.technician_name,
                "skill": technician.technician_skill
            },
            "job_status": job.status
        }

    # ================================================================
    # HTTP Errors
    # ================================================================

    except HTTPException:
        raise

    # ================================================================
    # Database Errors
    # ================================================================

    except SQLAlchemyError as e:
        db.rollback()

        print(
            f"Database error during job assignment: {str(e)}"
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database connection error occurred"
        )

    # ================================================================
    # Unexpected Errors
    # ================================================================

    except Exception as e:
        db.rollback()

        print(
            f"Unexpected error during job assignment: {str(e)}"
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred"
        )