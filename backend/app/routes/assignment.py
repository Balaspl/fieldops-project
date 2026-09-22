from typing import List, Optional
from datetime import datetime, timezone
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from ..database import get_db
from .. import models, schemas, utils
from ..auth.dependencies import get_current_user_or_tenant, AuthenticatedUser
from ..redis_client import get_redis_client
from ..services.timer_service import TimerService


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

    tech_distances = []

    for tech in technicians:
        dist = utils.calculate_distance(
            job.location,
            tech.technician_location
        )

        tech_distances.append((tech, dist))

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
    db: Session = Depends(get_db),
    redis_client=Depends(get_redis_client),
):
    """
    Assign a technician to a job.

    Rules:
    - Super Admin can assign technicians across tenants.
    - Normal users remain tenant restricted.
    - Duplicate assignments are prevented.
    - Technician availability/workload is validated.
    - Assignment notification is created for the technician.
    - Assignment timer is started after successful DB commit.
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

        # Assignment metadata
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

            tenant_id=technician.tenant_id,

            tech_id=technician.tech_id,

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
        # 12. START ASSIGNMENT TIMER
        # ============================================================

        timer_started = TimerService.start_timer(
            redis_client,
            str(job.id),
            technician.tech_id,
        )

        print("========== ASSIGNMENT TIMER ==========")
        print("Job ID:", job.id)
        print("Technician tech_id:", technician.tech_id)
        print("Timer started:", timer_started)

        # ============================================================
        # 13. Return Response
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


@router.post("/assign-jobs-bulk")
def assign_jobs_bulk(
    assignment: schemas.BulkTechnicianAssignment,
    user_tenant: tuple[Optional[AuthenticatedUser], str] = Depends(
        get_current_user_or_tenant
    ),
    db: Session = Depends(get_db)
):
    """
    Assign one technician to multiple jobs.

    All selected jobs are validated before any job is mutated.
    If any job fails validation, the entire batch is rejected.
    """

    user, tenant_id = user_tenant

    try:

        # ============================================================
        # 1. Validate request
        # ============================================================

        if not assignment.job_ids:
            raise HTTPException(
                status_code=400,
                detail="At least one job must be selected"
            )

        parsed_job_ids = []

        for raw_job_id in assignment.job_ids:
            job_id_str = str(raw_job_id).strip()

            try:
                if job_id_str.upper().startswith("JOB"):
                    job_id = int(job_id_str[3:])
                else:
                    job_id = int(job_id_str)
            except (ValueError, TypeError):
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid job ID: {raw_job_id}"
                )

            if job_id <= 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid job ID: {raw_job_id}"
                )

            if job_id not in parsed_job_ids:
                parsed_job_ids.append(job_id)

        if not parsed_job_ids:
            raise HTTPException(
                status_code=400,
                detail="No valid jobs were provided"
            )

        # ============================================================
        # 2. Find technician
        # ============================================================

        tech_val = assignment.technician_id

        technician = None

        if (
            isinstance(tech_val, int)
            or (
                isinstance(tech_val, str)
                and tech_val.isdigit()
            )
        ):
            technician_query = db.query(
                models.Technician
            ).filter(
                models.Technician.technician_id == int(tech_val)
            ).with_for_update()

            if not user or not user.is_super_admin:
                technician_query = technician_query.filter(
                    models.Technician.tenant_id == tenant_id
                )

            technician = technician_query.first()

        if not technician:
            technician_query = db.query(
                models.Technician
            ).filter(
                models.Technician.tech_id == str(tech_val)
            ).with_for_update()

            if not user or not user.is_super_admin:
                technician_query = technician_query.filter(
                    models.Technician.tenant_id == tenant_id
                )

            technician = technician_query.first()

        if not technician:
            raise HTTPException(
                status_code=404,
                detail="Technician not found"
            )

        # ============================================================
        # 3. Fetch all jobs
        # ============================================================

        job_query = db.query(models.Job).filter(
            models.Job.id.in_(parsed_job_ids)
        ).with_for_update()

        if not user or not user.is_super_admin:
            job_query = job_query.filter(
                models.Job.tenant_id == tenant_id
            )

        jobs = job_query.all()

        jobs_by_id = {
            job.id: job
            for job in jobs
        }

        # ============================================================
        # 4. Make sure every requested job exists
        # ============================================================

        missing_job_ids = [
            job_id
            for job_id in parsed_job_ids
            if job_id not in jobs_by_id
        ]

        if missing_job_ids:
            raise HTTPException(
                status_code=404,
                detail=(
                    "Job(s) not found or not accessible: "
                    + ", ".join(
                        str(job_id)
                        for job_id in missing_job_ids
                    )
                )
            )

        ordered_jobs = [
            jobs_by_id[job_id]
            for job_id in parsed_job_ids
        ]

        # ============================================================
        # 5. Validate EVERY job before mutation
        # ============================================================

        from ..validation import validate_technician_for_assignment

        for job in ordered_jobs:

            if job.assigned_technician_id:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Job #{job.id} is already assigned to "
                        f"technician #{job.assigned_technician_id}"
                    )
                )

            validate_technician_for_assignment(
                technician,
                job
            )

        # ============================================================
        # 6. Validate batch workload
        # ============================================================

        current_jobs = technician.current_jobs or 0
        max_jobs = technician.max_jobs

        if max_jobs is not None:
            requested_count = len(ordered_jobs)

            if current_jobs + requested_count > max_jobs:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Cannot assign {requested_count} jobs to "
                        f"{technician.technician_name}. "
                        f"Current workload: {current_jobs}/{max_jobs}."
                    )
                )

        # ============================================================
        # 7. Perform mutations
        # ============================================================

        assigned_at = datetime.now(timezone.utc)

        from ..workload_utils import update_workload_count

        results = []

        for job in ordered_jobs:

            job.assigned_technician_id = (
                technician.technician_id
            )

            job.status = "ASSIGNED"

            service_request = db.query(
                models.ServiceRequest
            ).filter(
                models.ServiceRequest.linked_job_id == job.id
            ).first()

            if service_request:
                service_request.status = "ASSIGNED"

            if hasattr(job, "assigned_at"):
                job.assigned_at = assigned_at

            if hasattr(job, "assigned_by") and user:
                job.assigned_by = str(user.user_id)

            update_workload_count(
                db,
                technician.technician_id,
                1
            )

            notification = models.InAppNotification(
                id=str(uuid.uuid4()),
                tenant_id=technician.tenant_id,
                tech_id=technician.tech_id,
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
                created_at=assigned_at,
            )

            db.add(notification)

            results.append({
                "job_id": job.id,
                "status": "ASSIGNED",
                "technician_id": technician.technician_id,
                "message": "Technician assigned successfully"
            })

        # ============================================================
        # 8. Commit entire batch
        # ============================================================

        db.commit()

        # ============================================================
        # 9. Return response
        # ============================================================

        return {
            "results": results,
            "total_requested": len(parsed_job_ids),
            "total_assigned": len(results)
        }

    except HTTPException:
        db.rollback()
        raise

    except SQLAlchemyError as e:
        db.rollback()

        print(
            f"Database error during bulk job assignment: {str(e)}"
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database connection error occurred"
        )

    except Exception as e:
        db.rollback()

        print(
            f"Unexpected error during bulk job assignment: {str(e)}"
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred"
        )