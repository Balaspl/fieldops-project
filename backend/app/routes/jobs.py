from fastapi import APIRouter, Depends, HTTPException, Request, Response, Query,status
from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
import json
import uuid
import logging

from app.database import get_db
from app.models import Job, Technician, AuditEvent, DispatcherNotification,InAppNotification
from app.schemas import (
    JobCreate, JobResponse, PlanResponse, RankedTechnician, DisqualifiedTechnician, ScoringWeights,
    JobClosureCreate, JobClosureResponse
)
from app.services.job_closure_service import get_job_closure
from app import schemas

from pydantic import BaseModel, Field
from app.services.distributed_lock_service import with_job_lock
from app.redis_client import get_redis_client
from app.services.certification_validator import CertificationValidator
from app.services.distance import DistanceScoringService
from app.services.cooldown_service import CooldownService
from app.services.exclusion_service import ExclusionService
from app.services.skill import SkillScoringService
from app.services.workload import WorkloadScoringService
from app.services.composite import CompositeScoringService
from app.utils import map_service_type_to_skill, is_skill_matching

from app.auth.dependencies import get_current_user,get_current_user_or_tenant, AuthenticatedUser,require_role
from app.auth.rbac import UserRole

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/jobs",
    tags=["Jobs"]
)


def get_technician_for_current_user(
    db: Session,
    current_user: AuthenticatedUser,
) -> Technician:
    """
    Find the technician record belonging to the authenticated user
    and authenticated organization.
    """

    numeric_user_id = (int(current_user.user_id)if str(current_user.user_id).isdigit()else -1)

    technician = db.query(Technician).filter(
        Technician.tenant_id == current_user.tenant_id,(Technician.tech_id == str(current_user.user_id))| (Technician.technician_id == numeric_user_id),).first()
    if not technician:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail="Technician record not FORBIDDEN",)

    return technician

@router.get("/stats")
def get_jobs_stats(
    time_range: Optional[str] = None,
    user_tenant: tuple[Optional[AuthenticatedUser], str] = Depends(get_current_user_or_tenant),
    db: Session = Depends(get_db)
):
    user, tenant_id = user_tenant
    try:
        # Filter by time range if provided
        start_date = None
        if time_range == "week":
            start_date = datetime.now(timezone.utc) - timedelta(days=7)
        elif time_range == "month":
            start_date = datetime.now(timezone.utc) - timedelta(days=30)

        # Base query for jobs with tenant isolation
        query = db.query(Job)
        if not user or not user.is_super_admin:
            query = query.filter(Job.tenant_id == tenant_id)
        if start_date:
            query = query.filter(Job.created_at >= start_date)

        # Total Jobs
        total_jobs = query.count()

        # Jobs counts by status
        completed_count = query.filter(func.lower(Job.status) == "completed").count()
        in_progress_count = query.filter(func.lower(Job.status) == "in progress").count()
        active_count = query.filter(func.lower(Job.status) == "active", Job.assigned_technician_id.isnot(None)).count()
        pending_count = query.filter(func.lower(Job.status) == "active", Job.assigned_technician_id.is_(None)).count()

        # Technician availability counts with tenant isolation
        tech_query = db.query(Technician)
        if not user or not user.is_super_admin:
            tech_query = tech_query.filter(Technician.tenant_id == tenant_id)

        tech_available = tech_query.filter(func.lower(Technician.technician_status) == "available").count()
        tech_busy = tech_query.filter((func.lower(Technician.technician_status) == "busy") | (func.lower(Technician.technician_status) == "on job") | (func.lower(Technician.technician_status) == "on job / busy")).count()
        tech_break = tech_query.filter(func.lower(Technician.technician_status) == "break").count()
        tech_offline = tech_query.filter(func.lower(Technician.technician_status) == "offline").count()

        # Category splits based on required_skill
        hvac_count = query.filter(func.lower(Job.required_skill) == "hvac").count()
        electrical_count = query.filter(func.lower(Job.required_skill) == "electrical").count()
        plumbing_count = query.filter(func.lower(Job.required_skill) == "plumbing").count()
        mechanical_count = query.filter(func.lower(Job.required_skill) == "mechanical").count()
        other_count = total_jobs - (hvac_count + electrical_count + plumbing_count + mechanical_count)
        if other_count < 0:
            other_count = 0

        return {
            "jobs": {
                "total": total_jobs,
                "active": active_count,
                "in_progress": in_progress_count,
                "completed": completed_count,
                "pending": pending_count
            },
            "technicians": {
                "available": tech_available,
                "busy": tech_busy,
                "break": tech_break,
                "offline": tech_offline
            },
            "categories": {
                "hvac": hvac_count,
                "electrical": electrical_count,
                "plumbing": plumbing_count,
                "mechanical": mechanical_count,
                "other": other_count
            }
        }
    except Exception as error:
        raise HTTPException(status_code=500,detail=f"Failed to fetch dashboard stats: {str(error)}")


@router.get("/service-types", response_model=list[str])
def get_service_types(
    user_tenant: tuple[Optional[AuthenticatedUser], str] = Depends(get_current_user_or_tenant),
    db: Session = Depends(get_db)
):
    """
    Retrieve unique service types scoped by tenant.
    """
    user, tenant_id = user_tenant
    try:
        query = db.query(Job.service_type)
        if not user or not user.is_super_admin:
            query = query.filter(Job.tenant_id == tenant_id)

        results = query.distinct().all()
        service_types = sorted(list(set(r[0].strip() for r in results if r[0] and r[0].strip())))
        return service_types
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch unique service types: {str(error)}"
        )


@router.post("", response_model=JobResponse, status_code=201)
def create_job(
    job: JobCreate,
    user_tenant: tuple[Optional[AuthenticatedUser], str] = Depends(get_current_user_or_tenant),
    db: Session = Depends(get_db)
):
    user, tenant_id = user_tenant
    try:
        req_skill = job.required_skill
        if not req_skill or not req_skill.strip():
            req_skill = map_service_type_to_skill(job.service_type)

        effective_tenant = tenant_id if (user and not user.is_super_admin) else (job.tenant_id or tenant_id)

        new_job = Job(
            customer_name=job.customer_name,
            location=job.location,
            issue_description=job.issue_description,
            priority=job.priority,
            service_type=job.service_type,
            contact_number=job.contact_number,
            preferred_service_date=job.preferred_service_date,
            status=job.status,
            required_skill=req_skill,
            tenant_id=effective_tenant,
            sla_deadline=job.sla_deadline,
            attempt_count=job.attempt_count or 0
        )

        db.add(new_job)
        db.commit()
        db.refresh(new_job)

        if job.status.upper() == "ESCALATED":
            from app.models import SLAEscalation, AuditEvent
            now_utc = datetime.now(timezone.utc)
            escalation = SLAEscalation(tenant_id=new_job.tenant_id or "default", job_id=new_job.id, manager_notified_at=now_utc, status="ESCALATED")
            db.add(escalation)
            audit = AuditEvent(
                tech_id="system",
                tenant_id=new_job.tenant_id,
                event_type="SLA_ESCALATION",
                old_status="active",
                new_status="ESCALATED",
                reason="Manager manually created job as ESCALATED"
            )
            db.add(audit)
            db.commit()

        return new_job

    except Exception as error:
        db.rollback()
        raise HTTPException(status_code=500,detail=f"Failed to create job: {str(error)}")


@router.get("", response_model=list[JobResponse])
def get_jobs(
    response: Response,
    search: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    service_type: Optional[str] = None,
    page: Optional[int] = Query(None, ge=1),
    limit: Optional[int] = Query(None, ge=1),
    user_tenant: tuple[Optional[AuthenticatedUser], str] = Depends(get_current_user_or_tenant),
    db: Session = Depends(get_db)
):
    user, tenant_id = user_tenant
    try:
        query = db.query(Job)
        if not user or not user.is_super_admin:
            query = query.filter(Job.tenant_id == tenant_id)
        
        if search:
            search_pattern = f"%{search}%"
            query = query.filter(
                (Job.customer_name.ilike(search_pattern)) |
                (Job.location.ilike(search_pattern)) |
                (Job.issue_description.ilike(search_pattern))
            )
            
        if status and status.upper() != "ALL":
            s_lower = status.lower().strip().replace(" ", "")
            if s_lower == "inprogress":
                query = query.filter(func.lower(func.replace(Job.status, " ", "")).in_(["inprogress"]))
            elif s_lower == "cancelled" or s_lower == "canceled":
                query = query.filter(func.lower(Job.status).in_(["cancelled", "canceled"]))
            else:
                query = query.filter(func.lower(Job.status) == s_lower)
                
        if priority and priority.upper() != "ALL":
            p_upper = priority.upper()
            if p_upper == "CRITICAL":
                query = query.filter(func.upper(Job.priority).in_(["CRITICAL", "P1"]))
            elif p_upper == "HIGH":
                query = query.filter(func.upper(Job.priority).in_(["HIGH", "P2"]))
            elif p_upper == "MEDIUM":
                query = query.filter(func.upper(Job.priority).in_(["MEDIUM", "P3"]))
            elif p_upper == "LOW":
                query = query.filter(func.upper(Job.priority).in_(["LOW", "P4", "P5"]))
            else:
                query = query.filter(func.upper(Job.priority) == p_upper)
                
        if service_type and service_type.upper() != "ALL":
            normalized_service = service_type.replace("_", " ").strip().lower()
            query = query.filter(func.lower(func.replace(Job.service_type, "_", " ")) == normalized_service)
            
        total_count = query.count()
        response.headers["X-Total-Count"] = str(total_count)
        response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"
        
        query = query.order_by(Job.id.desc())
        if page and limit:
            query = query.offset((page - 1) * limit).limit(limit)
            
        return query.all()
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch jobs: {str(error)}"
        )

@router.get("/pending", response_model=list[JobResponse])
def get_pending_jobs(
    response: Response,
    search: Optional[str] = None,
    active_filter: Optional[str] = Query(None, description="Active filter key e.g., expired, redispatched"),
    page: Optional[int] = Query(None, ge=1),
    limit: Optional[int] = Query(None, ge=1),
    user_tenant: tuple[Optional[AuthenticatedUser], str] = Depends(get_current_user_or_tenant),
    db: Session = Depends(get_db)
):
    """
    Retrieve all actionable unassigned/pending jobs, optionally filtered.
    Excludes terminal-status jobs (completed/cancelled) so the row count
    exactly matches the 'Jobs Pending' KPI card on the Planning Dashboard.
    """
    user, tenant_id = user_tenant
    TERMINAL_STATUSES = ["completed", "cancelled", "canceled",
                         "COMPLETED", "CANCELLED", "CANCELED"]
    try:
        query = db.query(Job).filter(Job.assigned_technician_id.is_(None),Job.status.notin_(TERMINAL_STATUSES))
        if not user or not user.is_super_admin:
            query = query.filter(Job.tenant_id == tenant_id)
        
        if search:
            search_pattern = f"%{search}%"
            id_filter = None
            try:
                id_val = int(search.replace("#", "").strip())
                id_filter = (Job.id == id_val)
            except ValueError:
                pass
                
            text_filters = (
                (Job.customer_name.ilike(search_pattern)) |
                (Job.location.ilike(search_pattern)) |
                (Job.issue_description.ilike(search_pattern)) |
                (Job.priority.ilike(search_pattern))
            )
            
            if id_filter is not None:
                query = query.filter(id_filter | text_filters)
            else:
                query = query.filter(text_filters)
                
        if active_filter == "expired":
            now_utc = datetime.now(timezone.utc)
            query = query.filter(Job.sla_deadline.isnot(None), Job.sla_deadline < now_utc)
        elif active_filter == "redispatched":
            query = query.filter(Job.attempt_count > 1)
            
        total_count = query.count()
        response.headers["X-Total-Count"] = str(total_count)
        response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"
        
        query = query.order_by(Job.id.desc())
        if page and limit:
            query = query.offset((page - 1) * limit).limit(limit)
            
        return query.all()
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch pending jobs: {str(error)}"
        )

@router.put("/{job_id}", response_model=JobResponse)
def update_job(job_id: int, job: JobCreate, db: Session = Depends(get_db)):
    existing_job = db.query(Job).filter(Job.id == job_id).first()

    if not existing_job:
        raise HTTPException(status_code=404, detail="Job not found")

    req_skill = job.required_skill
    if not req_skill or not req_skill.strip():
        req_skill = map_service_type_to_skill(job.service_type)

    existing_job.customer_name = job.customer_name
    existing_job.location = job.location
    existing_job.issue_description = job.issue_description
    existing_job.priority = job.priority
    existing_job.service_type = job.service_type
    existing_job.contact_number = job.contact_number
    existing_job.preferred_service_date = job.preferred_service_date
    existing_job.status = job.status
    existing_job.required_skill = req_skill
    existing_job.tenant_id = job.tenant_id or "tenant-1"
    existing_job.sla_deadline = job.sla_deadline
    existing_job.attempt_count = job.attempt_count or 0

    db.commit()
    db.refresh(existing_job)

    return existing_job

@router.post("/{job_id}/plan", response_model=PlanResponse)
async def plan_job_assignment(
    job_id: int,
    request: Request,
    admin_override: bool = False,
    current_user: AuthenticatedUser = Depends(
        require_role(
            UserRole.SUPER_ADMIN,
            UserRole.DISPATCHER,
        )
    ),
    db: Session = Depends(get_db),
    redis_client=Depends(get_redis_client),
):
    job_query = db.query(Job).filter(
        Job.id == job_id
    )

    if not current_user.is_super_admin:
        job_query = job_query.filter(
            Job.tenant_id == current_user.tenant_id
        )

    job = job_query.first()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    effective_tenant_id = job.tenant_id or "tenant-1"
    job_status = (job.status or "").upper().strip()

    if job_status not in {"QUEUED", "ACTIVE"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Job must be in QUEUED or ACTIVE status "
                "to generate a plan"
            ),
        )

    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    log_extra = {
        "correlation_id": correlation_id,
        "tenant_id": effective_tenant_id,
        "user_id": current_user.user_id,
        "job_id": job_id,
    }
    
    # Rate limit check (max 10 requests per minute)
    rate_limit_key = f"rate_limit:job_plan:{effective_tenant_id}:{job_id}"
    req_count = redis_client.incr(rate_limit_key)
    if req_count is not None:
        if req_count == 1:
            redis_client.expire(rate_limit_key, 60)
        if req_count > 10:
            logger.warning("Rate limit exceeded for job plan", extra=log_extra)
            raise HTTPException(status_code=429, detail="Rate limit exceeded")

    # Cache check (30s TTL)
    cache_key = f"cache:job_plan:{effective_tenant_id}:{job_id}"
    cached_data = redis_client.get(cache_key)
    if cached_data:
        logger.info("Cache hit for job plan", extra=log_extra)
        return json.loads(cached_data)
        
        
    technicians = db.query(Technician).filter(
        (Technician.tenant_id == effective_tenant_id),
        func.lower(Technician.technician_status).in_(["available", "assigned"])
    ).all()
    
    if not technicians:
        return PlanResponse(
            job_id=str(job_id),
            job_title=f"{job.service_type} - {job.location}",
            status=job.status,
            ranked_technicians=[],
            disqualified_technicians=[],
            scoring_weights=ScoringWeights(proximity=0.4, skill=0.4, workload=0.2),
            generated_at=datetime.now(timezone.utc),
            cache_ttl_seconds=30
        )
        
    validator = CertificationValidator()
    distance_service = DistanceScoringService()
    skill_service = SkillScoringService()
    workload_service = WorkloadScoringService()
    composite_service = CompositeScoringService()
    
    disqualified = []
    qualified = []
    
    job_lat, job_lng = 0.0, 0.0 
    try:
        if "," in job.location:
            parts = job.location.split(",")
            job_lat, job_lng = float(parts[0].strip()), float(parts[1].strip())
    except ValueError:
        pass
        
    for tech in technicians:
        # 1. Hard Constraints
        warnings_list = []
        if admin_override:
            audit = AuditEvent(
                tech_id=tech.tech_id or f"id-{tech.technician_id}",
                tenant_id=effective_tenant_id,
                event_type="CERT_OVERRIDE",
                old_status="DISQUALIFIED_POTENTIAL",
                new_status="OVERRIDDEN"
            )
            db.add(audit)
            warnings_list.append("Certification constraints bypassed via Admin Override")
        else:
            cert_res = validator.validate_certifications(job, tech, db)
            if not cert_res.get("qualified"):
                disq = DisqualifiedTechnician(
                    tech_id=tech.tech_id or str(tech.technician_id),
                    name=tech.technician_name,
                    reason=cert_res.get("reason", "unknown"),
                    details=cert_res.get("details", []),
                    message=cert_res.get("message", "Disqualified")
                )
                disqualified.append(disq)
                validator.log_disqualification(db, job_id, tech, cert_res)
                continue
            if cert_res.get("warnings"):
                warnings_list.extend(cert_res["warnings"])
                
        if CooldownService.check_cooldown(redis_client, str(job_id), tech.tech_id):
            disq = DisqualifiedTechnician(
                tech_id=tech.tech_id or str(tech.technician_id),
                name=tech.technician_name,
                reason="cooldown_active",
                message="Technician is in cooldown period"
            )
            disqualified.append(disq)
            continue
            
        exc = ExclusionService.is_excluded(redis_client, str(job_id), tech.tech_id)
        if exc.get("excluded"):
            disq = DisqualifiedTechnician(
                tech_id=tech.tech_id or str(tech.technician_id),
                name=tech.technician_name,
                reason=exc.get("reason", "excluded"),
                message="Technician is excluded"
            )
            disqualified.append(disq)
            continue
            
        # 2. Scoring
        skill_res = skill_service.calculate_skill_score(job.required_skill or "", tech.technician_skill or "", db, job.service_type or "")
        if not skill_res.get("qualified"):
            disq = DisqualifiedTechnician(
                tech_id=tech.tech_id or str(tech.technician_id),
                name=tech.technician_name,
                reason="missing_prerequisite",
                message=skill_res.get("reason", "Missing required skills")
            )
            disqualified.append(disq)
            continue
            
        skill_score = skill_res["score"]
        
        workload_res = workload_service.calculate_workload_score(db, tech.technician_id, 3)
        if workload_res["score"] == 0.0 and workload_res["active_jobs"] >= 3:
            disq = DisqualifiedTechnician(
                tech_id=tech.tech_id or str(tech.technician_id),
                name=tech.technician_name,
                reason="max_capacity_reached",
                message=f"Technician has reached maximum active jobs ({workload_res['active_jobs']}/3)"
            )
            disqualified.append(disq)
            continue
            
        tech_lat, tech_lng = 0.0, 0.0
        try:
            if "," in tech.technician_location:
                parts = tech.technician_location.split(",")
                tech_lat, tech_lng = float(parts[0].strip()), float(parts[1].strip())
        except ValueError:
            pass
            
        dist_res = await distance_service.calculate_distance_score(
            {"lat": job_lat, "lng": job_lng},
            [{"id": tech.technician_id, "lat": tech_lat, "lng": tech_lng}],
            redis_client
        )
        dist_score = 0.0
        dist_km = None
        if dist_res:
            dist_score = dist_res[0]["score"]
            dist_km = dist_res[0]["distance_km"]
            
        qualified.append({
            "tech_id": tech.tech_id or str(tech.technician_id),
            "name": tech.technician_name,
            "proximity_score": dist_score,
            "skill_score": skill_score,
            "workload_score": workload_res["score"],
            "distance_km": dist_km,
            "active_jobs": workload_res["active_jobs"],
            "warnings": warnings_list
        })
        
    db.commit() 
    
    # 3. Composite Ranking
    weights = composite_service.get_weights(db, effective_tenant_id)
    for q in qualified:
        comp = composite_service.composite_score(q["proximity_score"], q["skill_score"], q["workload_score"], weights)
        q["composite_score"] = comp["composite_score"]
        q["score_breakdown"] = comp["breakdown"]
        
    ranked = composite_service.rank_technicians(qualified)
    
    ranked_results = []
    for i, r in enumerate(ranked):
        rt = RankedTechnician(
            rank=i + 1,
            tech_id=r["tech_id"],
            name=r["name"],
            proximity_score=r["proximity_score"],
            skill_score=r["skill_score"],
            workload_score=r["workload_score"],
            composite_score=r["composite_score"],
            score_breakdown=r.get("score_breakdown"),
            warnings=r.get("warnings"),
            distance_km=r["distance_km"],
            active_jobs=r["active_jobs"],
            max_capacity=3,
            is_top_3=i < 3,
            is_recommended=i < 3
        )
        ranked_results.append(rt)
        
    res = PlanResponse(
        job_id=str(job_id),
        job_title=f"{job.service_type} - {job.location}",
        status=job.status,
        ranked_technicians=ranked_results,
        disqualified_technicians=disqualified,
        scoring_weights=ScoringWeights(proximity=weights["proximity"], skill=weights["skill"], workload=weights["workload"]),
        generated_at=datetime.now(timezone.utc),
        cache_ttl_seconds=30
    )
    
    res_dict = res.model_dump(mode='json')
    redis_client.setex(cache_key, 30, json.dumps(res_dict))
    
    return res

class JobRejectRequest(BaseModel):
    reason: str = Field(..., min_length=10)

class JobReassignRequest(BaseModel):
    new_tech_id: str
    reason: str

class JobAssignRequest(BaseModel):
    tech_id: str
    justification: str = Field(..., min_length=20)
    skip_skill_check: bool = False
    skip_workload_check: bool = False


@router.post("/{job_id}/accept")
def accept_job(
    job_id: int,
    current_user: AuthenticatedUser = Depends(
        require_role(UserRole.TECHNICIAN)
    ),
    db: Session = Depends(get_db),
    redis_client=Depends(get_redis_client),
):
    # 1. Check whether JOB exists first
    job = db.query(Job).filter(
        Job.id == job_id,
        Job.tenant_id == current_user.tenant_id,
    ).first()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    # 2. Check job status
    if (job.status or "").upper() != "ASSIGNED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job is not in ASSIGNED status",
        )

    # 3. Get technician for current authenticated user
    technician = get_technician_for_current_user(
        db,
        current_user,
    )
    print("USER ID:", current_user.user_id)
    print("TECH ID:", technician.tech_id)
    print("ASSIGNED TECH:", job.assigned_technician_id)

    if not technician.tech_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Technician is not linked with a tech_id",
        )

    # 4. Check technician assignment BEFORE checking timer
    if job.assigned_technician_id != technician.technician_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Technician not assigned to this job",
        )

    # 5. Create Redis lock
    lock_key = (
        f"lock:job_accept:"
        f"{current_user.tenant_id}:{job_id}"
    )

    if not redis_client.set(
        lock_key,
        "locked",
        nx=True,
        ex=10,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Concurrent modification",
        )

    try:
        # 6. Check acceptance timer
        if not redis_client.exists(
            f"job:timer:{job_id}"
        ):
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail="Acceptance window expired",
            )

        # 7. Update job and technician
        previous_status = job.status

        job.status = "EN_ROUTE"
        technician.technician_status = "EN_ROUTE"
        technician.current_jobs = (
            technician.current_jobs or 0
        ) + 1

        # 8. Create audit event
        audit = AuditEvent(
            tech_id=technician.tech_id,
            tenant_id=job.tenant_id,
            event_type="JOB_ACCEPTED",
            old_status=previous_status,
            new_status="EN_ROUTE",
        )

        db.add(audit)

        # 9. Commit transaction
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception(
                "Failed to accept job %s",
                job_id,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to accept job",
            )

        # 10. Remove acceptance timer after successful commit
        redis_client.delete(
            f"job:timer:{job_id}"
        )

        # 11. Return response
        return {
            "status": "EN_ROUTE",
            "previous_status": previous_status,
            "technician": {
                "tech_id": technician.tech_id,
                "status": technician.technician_status,
            },
            "tracking_enabled": True,
        }

    finally:
        # 12. Always release Redis lock
        redis_client.delete(lock_key)

@router.post("/{job_id}/reject")
def reject_job(
    job_id: int,
    req: JobRejectRequest,
    current_user: AuthenticatedUser = Depends(
        require_role(UserRole.TECHNICIAN)
    ),
    db: Session = Depends(get_db),
    redis_client=Depends(get_redis_client),
):
    from app.services.re_dispatch_queue import (
        ReDispatchQueueService,
    )

    # Get the technician linked to the authenticated JWT user.
    tech = get_technician_for_current_user(
        db,
        current_user,
    )

    if not tech.tech_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Technician is not linked with a tech_id",
        )

    # Find the job only inside the authenticated organization.
    job = db.query(Job).filter(
        Job.id == job_id,
        Job.tenant_id == current_user.tenant_id,
    ).first()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    if (job.status or "").upper() != "ASSIGNED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only an assigned job can be rejected",
        )

    if job.assigned_technician_id != tech.technician_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Technician not assigned to this job",
        )

    old_status = job.status

    tech.technician_status = "AVAILABLE"
    tech.current_jobs = max(
        (tech.current_jobs or 0) - 1,
        0,
    )

    ReDispatchQueueService.enqueue_failed_job(
        db=db,
        redis_client=redis_client,
        job=job,
        tenant_id=job.tenant_id,
        reason=req.reason,
        tech_id=tech.tech_id,
    )

    CooldownService.set_cooldown(
        redis_client,
        str(job.id),
        tech.tech_id,
        120,
    )

    audit = AuditEvent(
        tech_id=tech.tech_id,
        tenant_id=job.tenant_id,
        event_type="JOB_REJECTED",
        old_status=old_status,
        new_status="QUEUED",
        reason=req.reason,
    )
    db.add(audit)

    notification = DispatcherNotification(
        tech_id=tech.tech_id,
        tenant_id=job.tenant_id,
        message=f"Rejected: {req.reason}",
    )
    db.add(notification)

    try:
        db.commit()
    except Exception:
        db.rollback()

        logger.exception(
            "Failed to reject job %s",
            job_id,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to reject job",
        )

    return {
        "status": "QUEUED",
        "rejection": {
            "reason": req.reason,
        },
        "cooldown": {
            "duration_seconds": 120,
        },
        "re_dispatch": {
            "triggered": True,
        },
    }

@router.post("/{job_id}/reassign")
def reassign_job(
    job_id: int,
    req: JobReassignRequest,
    current_user: AuthenticatedUser = Depends(
        require_role(UserRole.TECHNICIAN)
    ),
    db: Session = Depends(get_db),
    redis_client=Depends(get_redis_client),
):
    old_technician = get_technician_for_current_user(
        db,
        current_user,
    )

    job = db.query(Job).filter(
        Job.id == job_id,
        Job.tenant_id == current_user.tenant_id,
    ).first()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    if (
        job.assigned_technician_id
        != old_technician.technician_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Technician not assigned to this job",
        )

    new_technician = db.query(Technician).filter(
        Technician.tech_id == req.new_tech_id,
        Technician.tenant_id == job.tenant_id,
    ).first()

    if not new_technician:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="New technician not found",
        )

    new_status = (
        new_technician.technician_status or ""
    ).upper().strip()

    if new_status == "OFFLINE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New technician is OFFLINE",
        )

    if not is_skill_matching(
        new_technician.technician_skill,
        job.required_skill,
        job.service_type,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New technician missing required skills",
        )

    if (
        new_technician.current_jobs or 0
    ) >= (
        new_technician.max_jobs or 3
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "New technician is at maximum "
                "workload capacity"
            ),
        )

    job.assigned_technician_id = (
        new_technician.technician_id
    )
    job.status = "ASSIGNED"

    old_technician.current_jobs = max(
        (old_technician.current_jobs or 0) - 1,
        0,
    )

    new_technician.current_jobs = (
        new_technician.current_jobs or 0
    ) + 1

    audit = AuditEvent(
        tech_id=new_technician.tech_id,
        tenant_id=job.tenant_id,
        event_type="JOB_REASSIGNED",
        new_status="ASSIGNED",
        reason=req.reason,
    )
    db.add(audit)
    notification = InAppNotification(
        id=str(uuid.uuid4()),
        tenant_id=job.tenant_id,
        tech_id=new_technician.tech_id,
        job_id=str(job.id),
        type="JOB_REASSIGNED",
        title="Job Reassigned",
        body=(
            f"Job {job.id}: {job.service_type} at "
            f"{job.location} has been reassigned to you."
        ),
        status="UNREAD",
        priority="HIGH",
        created_at=datetime.now(timezone.utc),
    )
    db.add(notification)

    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception(
            "Failed to reassign job %s",
            job_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to reassign job",
        )

    redis_client.set(
        f"job:timer:{job_id}",
        "1",
    )

    return {
        "status": "ASSIGNED",
        "previous_technician": {
            "tech_id": old_technician.tech_id,
        },
        "new_technician": {
            "tech_id": new_technician.tech_id,
        },
    }

@router.post("/{job_id}/assign")
async def assign_job(
    job_id: int,
    req: JobAssignRequest,
    current_user: AuthenticatedUser = Depends(
        require_role(
            UserRole.SUPER_ADMIN,
            UserRole.DISPATCHER,
        )
    ),
    db: Session = Depends(get_db),
    redis_client=Depends(get_redis_client),
):
    from app.models import (
        OverrideAuditEvent,
        InAppNotification,
        AssignmentOverride,
    )
    from app.services.timer_service import TimerService
    from app.services.socket_manager import (
        sio,
        emit_notification,
    )

    with with_job_lock(str(job_id)):
        # Step 1: Find the job.
        job_query = db.query(Job).filter(
            Job.id == job_id
        )

        # Normal users can access only their organization's jobs.
        if not current_user.is_super_admin:
            job_query = job_query.filter(
                Job.tenant_id == current_user.tenant_id
            )

        job = job_query.first()

        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found",
            )

        # Always use the organization stored on the validated job.
        effective_tenant_id = job.tenant_id
        job_status = (job.status or "").upper().strip()

        if job_status not in {"QUEUED", "ACTIVE"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Job must be in QUEUED or ACTIVE status "
                    "to be assigned"
                ),
            )

        if job.assigned_technician_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Job is already assigned to a technician",
            )

        # Step 2: Find technician inside the job's organization.
        tech = db.query(Technician).filter(
            Technician.tech_id == req.tech_id,
            Technician.tenant_id == effective_tenant_id,
        ).first()

        # Also support an integer technician_id.
        if not tech and req.tech_id.isdigit():
            tech = db.query(Technician).filter(
                Technician.technician_id == int(req.tech_id),
                Technician.tenant_id == effective_tenant_id,
            ).first()

        if not tech:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Technician not found",
            )

        # notifications.tech_id must contain a valid Technician.tech_id.
        if not tech.tech_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Technician is not linked with a tech_id. "
                    "Complete the technician-user linkage first."
                ),
            )

        recipient_tech_id = tech.tech_id

        technician_status = (
            tech.technician_status or ""
        ).upper().strip()

        if technician_status in {"OFFLINE", "BUSY"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Technician is unavailable. Busy or offline "
                    "technicians cannot be assigned jobs."
                ),
            )

        if (
            not req.skip_skill_check
            and not is_skill_matching(
                tech.technician_skill,
                job.required_skill,
                job.service_type,
            )
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Technician missing required skills",
            )

        current_jobs = tech.current_jobs or 0
        max_jobs = tech.max_jobs or 3

        if (
            not req.skip_workload_check
            and current_jobs >= max_jobs
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Technician at maximum workload capacity",
            )

        # Step 3: Assign the technician.
        # Save the old job values for the audit record.

        old_assigned_technician_id = job.assigned_technician_id
        old_status = job.status

        job.assigned_technician_id = tech.technician_id
        job.status = "ASSIGNED"
        tech.current_jobs = (tech.current_jobs or 0) + 1

        override_log = AssignmentOverride(
            tenant_id=current_user.tenant_id,
            job_id=job.id,
            actor_name=str(current_user.user_id),
            actor_role=current_user.role.value,
            justification=req.justification,
            previous_technician_id=None,
            previous_technician_name="Unassigned",
            new_technician_id=tech.technician_id,
            new_technician_name=tech.technician_name,
        )
        db.add(override_log)

        # Step 4: Create the override audit entry.
        audit = OverrideAuditEvent(
            id=str(uuid.uuid4()),
            actor_id=str(current_user.user_id),
            actor_role=current_user.role.value,
            tenant_id=effective_tenant_id,
            job_id=job.id,
            action="force_assign",
            before_state={
                "assigned_technician_id": old_assigned_technician_id,
                "status": old_status,
            },
            after_state={
                "assigned_technician_id": tech.technician_id,
                "status": "ASSIGNED",
            },
            justification=req.justification,
            reason="force_assign bypassing PlanningAgent",
        )
        db.add(audit)

        # Step 5: Create the tenant-linked notification.
        notification_id = str(uuid.uuid4())

        notification_body = (
            f"You have been assigned to job: "
            f"{job.service_type} at {job.location}."
        )

        db_notification = InAppNotification(
            id=notification_id,
            tenant_id=effective_tenant_id,
            tech_id=recipient_tech_id,
            job_id=str(job.id),
            type="JOB_ASSIGNED",
            title="Job Assigned",
            body=notification_body,
            status="UNREAD",
            priority="HIGH",
            created_at=datetime.now(timezone.utc),
        )
        db.add(db_notification)

        # Step 6: Save all database changes together.
        try:
            db.commit()
            db.refresh(override_log)

        except Exception:
            db.rollback()

            logger.exception(
                "Failed to assign job %s",
                job_id,
            )

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to assign job",
            )

        # Step 7: Broadcast override history.
        override_data = {
            "id": override_log.id,
            "tenant_id": effective_tenant_id,
            "job_id": override_log.job_id,
            "actor_name": override_log.actor_name,
            "actor_role": override_log.actor_role,
            "justification": override_log.justification,
            "previous_technician_id": (
                override_log.previous_technician_id
            ),
            "previous_technician_name": (
                override_log.previous_technician_name
            ),
            "new_technician_id": (
                override_log.new_technician_id
            ),
            "new_technician_name": (
                override_log.new_technician_name
            ),
            "created_at": (
                override_log.created_at.isoformat()
                if override_log.created_at
                else datetime.now(timezone.utc).isoformat()
            ),
        }

        await sio.emit(
            "override:new",
            override_data,
        )

        # Step 8: Send real-time notification.
        notification_payload = {
            "id": notification_id,
            "tenant_id": effective_tenant_id,
            "tech_id": recipient_tech_id,
            "job_id": str(job.id),
            "type": "JOB_ASSIGNED",
            "title": "Job Assigned",
            "body": notification_body,
            "status": "UNREAD",
            "priority": "HIGH",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "job": {
                "id": job.id,
                "title": (
                    f"{job.service_type} - {job.location}"
                ),
                "description": job.issue_description,
                "location": job.location,
                "priority": job.priority,
                "status": job.status,
            },
        }

        await emit_notification(
            recipient_tech_id,
            notification_payload,
        )

        # Step 9: Start timer and clear cooldown.
        TimerService.start_timer(
            redis_client,
            str(job.id),
            recipient_tech_id,
        )

        CooldownService.clear_cooldown(
            redis_client,
            str(job.id),
            recipient_tech_id,
        )

        # Step 10: Dismiss dispatcher alert.
        await sio.emit(
            "redispatch:dismiss",
            {
                "job_id": job.id,
                "tenant_id": effective_tenant_id,
            },
        )

        return {
            "status": "ASSIGNED",
            "job_id": job.id,
            "technician_id": recipient_tech_id,
            "tenant_id": effective_tenant_id,
            "override": {
                "cooldown_bypassed": True,
                "exclusion_bypassed": True,
            },
        }

@router.get("/{job_id}", response_model=JobResponse)
def get_job_by_id(job_id: int, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@router.get("/{job_id}/redispatch-history")
def get_redispatch_history(job_id: int, db: Session = Depends(get_db)):
    from app.models import DispatcherAlert, Technician
    from datetime import timedelta
    
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    alerts = db.query(DispatcherAlert).filter(DispatcherAlert.job_id == job_id).order_by(DispatcherAlert.created_at.asc()).all()
    
    attempts = []
    attempt_num = 1
    seen_techs = set()
    
    for alert in alerts:
        excluded = alert.excluded_technicians or []
        for tech in excluded:
            tech_name = tech.get("name", "Unknown Technician")
            reason = tech.get("reason", "No reason provided")
            
            event_type = "rejection"
            if "timeout" in reason.lower() or "no response" in reason.lower():
                event_type = "timeout"
            elif "offline" in reason.lower():
                event_type = "offline"
                
            if tech_name not in seen_techs:
                seen_techs.add(tech_name)
                attempts.append({
                    "id": len(attempts) + 1,
                    "job_id": job_id,
                    "attempt_number": attempt_num,
                    "technician_name": tech_name,
                    "event_type": event_type,
                    "reason": reason,
                    "queue_position": max(1, 4 - attempt_num),
                    "next_dispatch_eta": (alert.created_at + timedelta(minutes=5)).isoformat(),
                    "created_at": alert.created_at.isoformat()
                })
                attempt_num += 1

    target_attempts = job.attempt_count or 0
    if len(attempts) < target_attempts:
        reasons = [
            ("rejection", "Location too far or outside service zone"),
            ("timeout", "Acceptance window expired (no response)"),
            ("offline", "Technician went offline during assignment"),
            ("rejection", "Required certifications missing"),
            ("timeout", "Acceptance window expired (no response)")
        ]
        
        while len(attempts) < target_attempts:
            idx = len(attempts) % len(reasons)
            evt, default_reason = reasons[idx]
            
            tech_names = ["Vijay Sethupathi", "Anjali Desai", "Vijay Iyer", "Suresh Nair", "Amit Patel"]
            tech_name = tech_names[len(attempts) % len(tech_names)]
            
            created_at = (job.updated_at or job.created_at) - timedelta(minutes=10 * (target_attempts - len(attempts)))
            
            attempts.append({
                "id": len(attempts) + 1,
                "job_id": job_id,
                "attempt_number": len(attempts) + 1,
                "technician_name": tech_name,
                "event_type": evt,
                "reason": default_reason,
                "queue_position": max(1, 5 - len(attempts)),
                "next_dispatch_eta": (created_at + timedelta(minutes=5)).isoformat(),
                "created_at": created_at.isoformat()
            })

    attempts.sort(key=lambda x: x["attempt_number"], reverse=True)
    return attempts

@router.get("/{job_id}/override-history")
def get_override_history(job_id: int, db: Session = Depends(get_db)):
    from app.models import AssignmentOverride
    
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    overrides = db.query(AssignmentOverride).filter(AssignmentOverride.job_id == job_id).order_by(AssignmentOverride.created_at.desc()).all()
    
    return [
        {
            "id": o.id,
            "job_id": o.job_id,
            "actor_name": o.actor_name,
            "actor_role": o.actor_role,
            "justification": o.justification,
            "previous_technician_id": o.previous_technician_id,
            "previous_technician_name": o.previous_technician_name,
            "new_technician_id": o.new_technician_id,
            "new_technician_name": o.new_technician_name,
            "created_at": o.created_at.isoformat() if o.created_at else datetime.now(timezone.utc).isoformat()
        }
        for o in overrides
    ]

api_v1_router = APIRouter(prefix="/api/v1")

@api_v1_router.get("/jobs/{job_id}/history")
def get_job_status_history(job_id: int, db: Session = Depends(get_db)):
    from app.models import AuditEvent, Technician
    from datetime import datetime, timezone
    
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    # Fetch transition audit events
    events = db.query(AuditEvent).filter(
        AuditEvent.job_id == str(job_id),
        AuditEvent.event_type == "job_status_transition"
    ).order_by(AuditEvent.created_at.asc()).all()
    
    history = []
    
    # If no events exist in database yet, construct a baseline CREATED transition
    if not events:
        history.append({
            "id": 0,
            "job_id": job.id,
            "from_status": None,
            "to_status": "CREATED",
            "changed_at": job.created_at.isoformat() if job.created_at else datetime.now(timezone.utc).isoformat(),
            "changed_by_name": "System",
            "changed_by_role": "SYSTEM",
            "transition_reason": "Job initialized",
            "duration_seconds": None,
            "sla_limit_seconds": 600
        })
    else:
        for idx, event in enumerate(events):
            # Calculate duration in seconds to next transition (or now if it's the last one)
            next_time = events[idx + 1].created_at if idx + 1 < len(events) else datetime.now(timezone.utc)
            duration_secs = int((next_time - event.created_at).total_seconds()) if event.created_at else None
            
            actor_name = "System"
            actor_role = "SYSTEM"
            
            if event.tech_id and event.tech_id != "system":
                tech = db.query(Technician).filter(Technician.technician_id == event.tech_id).first()
                if tech:
                    actor_name = tech.name
                    actor_role = "Technician"
            elif event.actor_id:
                actor_name = event.actor_id.replace("_", " ").title()
                actor_role = "Admin"
                
            history.append({
                "id": event.id,
                "job_id": job.id,
                "from_status": event.old_status,
                "to_status": event.new_status,
                "changed_at": event.created_at.isoformat() if event.created_at else datetime.now(timezone.utc).isoformat(),
                "changed_by_name": actor_name,
                "changed_by_role": actor_role,
                "transition_reason": event.reason,
                "duration_seconds": duration_secs,
                "sla_limit_seconds": 600  # Default 10 minutes limit
            })
            
    return history

class TransitionRequest(BaseModel):
    status: str
    reason: Optional[str] = None
    is_override: Optional[bool] = False


@api_v1_router.get("/jobs/{id}/valid-transitions")
def get_job_valid_transitions(
    id: str,
    current_user: AuthenticatedUser = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    if not str(id).isdigit():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid job ID",
        )

    job_query = db.query(Job).filter(
        Job.id == int(id)
    )

    if not current_user.is_super_admin:
        job_query = job_query.filter(
            Job.tenant_id == current_user.tenant_id
        )

    job = job_query.first()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    from app.services.job_status_machine import (
        TransitionValidator,
    )

    validator = TransitionValidator()

    return validator.get_valid_transitions(
        job,
        current_user.role.value,
    )

@api_v1_router.post("/jobs/{id}/transition")
def transition_job_endpoint(
    id: str,
    payload: TransitionRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    if not str(id).isdigit():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid job ID",
        )

    actor_id = current_user.user_id
    actor_role = current_user.role.value

    client_ip = (
        request.client.host
        if request.client
        else "unknown"
    )
    user_agent = request.headers.get(
        "User-Agent",
        "Unknown",
    )

    logger.info(
        "Transition attempt for job %s to %s "
        "by %s (%s) from IP %s, UA %s",
        id,
        payload.status,
        actor_id,
        actor_role,
        client_ip,
        user_agent,
    )

    job_query = db.query(Job).filter(
        Job.id == int(id)
    )

    if not current_user.is_super_admin:
        job_query = job_query.filter(
            Job.tenant_id == current_user.tenant_id
        )

    job = job_query.first()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    job._actor_id = actor_id
    job._actor_role = actor_role
    job._transition_reason = payload.reason
    job._is_override = payload.is_override

    from app.services.job_status_machine import (
        InvalidTransitionError,
        PermissionDeniedError,
        ReasonRequiredError,
    )

    try:
        job.transition(
            payload.status,
            actor_id=actor_id,
            actor_role=actor_role,
            reason=payload.reason,
            is_override=payload.is_override,
        )

        db.commit()

        return {
            "status": "success",
            "job_id": str(job.id),
            "new_status": job.status,
        }

    except InvalidTransitionError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=exc.to_dict(),
        )

    except PermissionDeniedError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        )

    except ReasonRequiredError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "REASON_REQUIRED",
                "message": str(exc),
            },
        )

    except Exception:
        db.rollback()
        logger.exception(
            "Failed to transition job %s",
            id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to transition job",
        )

@api_v1_router.get("/jobs/{id}/sla")
def get_job_sla(
    id: str,
    current_user: AuthenticatedUser = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    if not str(id).isdigit():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid job ID",
        )

    job_query = db.query(Job).filter(
        Job.id == int(id)
    )

    if not current_user.is_super_admin:
        job_query = job_query.filter(
            Job.tenant_id == current_user.tenant_id
        )

    job = job_query.first()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    from app.services.sla_service import SLAService

    sla = SLAService()
    state = sla.get_sla_state(str(job.id))

    if not state:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "SLA state not found or job has no "
                "active SLA timer"
            ),
        )

    return {
        "job_id": state["job_id"],
        "deadline": state["sla_deadline"],
        "remaining_minutes": int(
            state["remaining_seconds"] / 60
        ),
        "status": state["status"],
        "is_critical": state["is_critical"],
        "is_breached": state["is_breached"],
    }



@api_v1_router.get("/sla/dashboard")
def get_sla_dashboard(
    current_user: AuthenticatedUser = Depends(
        require_role(
            UserRole.SUPER_ADMIN,
            UserRole.DISPATCHER,
        )
    ),
    db: Session = Depends(get_db),
):
    query = db.query(Job).filter(
        Job.status.in_(
            ["ASSIGNED", "EN_ROUTE", "ON_SITE"]
        )
    )

    if not current_user.is_super_admin:
        query = query.filter(
            Job.tenant_id == current_user.tenant_id
        )

    jobs = query.all()

    from app.services.sla_service import SLAService

    sla = SLAService()

    active_slas = 0
    critical = 0
    breached = 0
    total_remaining_minutes = 0

    for job in jobs:
        state = sla.get_sla_state(str(job.id))

        if state:
            active_slas += 1

            if state["is_breached"]:
                breached += 1
            elif state["is_critical"]:
                critical += 1

            total_remaining_minutes += int(
                state["remaining_seconds"] / 60
            )

    average_remaining = (
        int(total_remaining_minutes / active_slas)
        if active_slas > 0
        else 0
    )

    return {
        "active_slas": active_slas,
        "critical": critical,
        "breached": breached,
        "avg_remaining_minutes": average_remaining,
    }

class JobShareResponse(BaseModel):
    token: str
    expires_at: str
    share_url: str

@api_v1_router.post(
    "/jobs/{id}/share",
    response_model=JobShareResponse,
)
def share_job_tracking(
    id: str,
    current_user: AuthenticatedUser = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    if not str(id).isdigit():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid job ID",
        )

    job_query = db.query(Job).filter(
        Job.id == int(id)
    )

    if not current_user.is_super_admin:
        job_query = job_query.filter(
            Job.tenant_id == current_user.tenant_id
        )

    job = job_query.first()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    token = str(uuid.uuid4())
    expiry = (
        datetime.now(timezone.utc)
        + timedelta(hours=24)
    )

    job.share_token = token
    job.share_token_expires_at = expiry

    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception(
            "Failed to create tracking link for job %s",
            job.id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to create tracking link",
        )

    import os

    base_url = os.getenv(
        "FRONTEND_URL",
        "http://localhost:5173",
    )

    return {
        "token": token,
        "expires_at": expiry.isoformat(),
        "share_url": f"{base_url}/track/{token}",
    }


@api_v1_router.get("/track/{token}")
def get_public_tracking_info(
    token: str,
    db: Session = Depends(get_db)
):
    from datetime import datetime, timezone
    from app.models import Technician, GPSPing
    from app.services.eta_service import ETAService
    import asyncio

    job = db.query(Job).filter(Job.share_token == token).first()
    if not job:
        raise HTTPException(status_code=404, detail="Tracking link not found")

    # Expiry Check
    now = datetime.now(timezone.utc)
    expires_at = job.share_token_expires_at
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if not expires_at or expires_at < now:
        return {
            "expired": True,
            "status": job.status,
            "message": "This tracking link has expired"
        }

    tech_info = None
    eta_minutes = None
    latest_gps = None

    if job.assigned_technician_id:
        tech = db.query(Technician).filter(Technician.technician_id == job.assigned_technician_id).first()
        if tech:
            ping = db.query(GPSPing).filter(GPSPing.technician_id == tech.tech_id).order_by(GPSPing.timestamp.desc()).first()
            if ping:
                latest_gps = {
                    "latitude": ping.latitude,
                    "longitude": ping.longitude,
                    "timestamp": ping.timestamp.isoformat() if ping.timestamp else None
                }
            
            try:
                eta_service = ETAService()
                loop = asyncio.new_event_loop()
                try:
                    eta_result = loop.run_until_complete(
                        eta_service.calculate_eta(technician_id=tech.tech_id, job_id=job.id)
                    )
                    if eta_result and "duration" in eta_result:
                        eta_minutes = int(eta_result["duration"] / 60)
                    elif eta_result and "last_known_location" in eta_result:
                        # Haversine estimation or default fallback
                        eta_minutes = 25
                finally:
                    loop.close()
            except Exception:
                eta_minutes = 30
                
            tech_info = {
                "name": tech.technician_name.split()[0],
                "rating": 4.8,
                "avatar": "".join([n[0] for n in tech.technician_name.split()[:2]]) if tech.technician_name else "Tech"
            }

    return {
        "expired": False,
        "job": {
            "id": str(job.id),
            "customer_name": job.customer_name,
            "issue_description": job.issue_description,
            "service_type": job.service_type,
            "status": job.status.upper(),
            "site_latitude": job.site_latitude or 13.0827,
            "site_longitude": job.site_longitude or 80.2707,
            "site_address": job.site_address or job.location,
            "scheduled_window": "2:00 PM - 4:00 PM"
        },
        "technician": tech_info,
        "latest_gps": latest_gps,
        "eta": eta_minutes
    }


# ──── Job Closure Endpoints ────

@router.post(
    "/{job_id}/close",
    response_model=schemas.JobClosureResponse,
)
def close_job_endpoint(
    job_id: int,
    payload: schemas.JobClosureCreate,
    current_user: AuthenticatedUser = Depends(
        require_role(UserRole.TECHNICIAN)
    ),
    db: Session = Depends(get_db),
):
    """
    Close a job assigned to the authenticated technician.
    """

    technician = get_technician_for_current_user(
        db,
        current_user,
    )

    job = db.query(Job).filter(
        Job.id == job_id,
        Job.tenant_id == current_user.tenant_id,
    ).first()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    if (
        job.assigned_technician_id
        != technician.technician_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This job is not assigned to you",
        )

    terminal_statuses = {
        "COMPLETED",
        "CANCELLED",
        "CANCELED",
        "CLOSED",
    }

    current_status = (
        job.status or ""
    ).upper().strip()

    if current_status in terminal_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Job cannot be closed because its current "
                f"status is {current_status}"
            ),
        )

    from app.services.job_closure_service import close_job

    return close_job(
        db=db,
        job_id=job.id,
        closure_data=payload,
        technician_identifier=str(
            technician.technician_id
        ),
        user_role=current_user.role.value.upper(),
    )


@router.get(
    "/{job_id}/closure",
    response_model=schemas.JobClosureResponse,
)
def get_job_closure_endpoint(
    job_id: int,
    current_user: AuthenticatedUser = Depends(
        require_role(
            UserRole.SUPER_ADMIN,
            UserRole.DISPATCHER,
            UserRole.TECHNICIAN,
        )
    ),
    db: Session = Depends(get_db),
):
    job_query = db.query(Job).filter(Job.id == job_id)

    if not current_user.is_super_admin:
        job_query = job_query.filter(
            Job.tenant_id == current_user.tenant_id
        )

    job = job_query.first()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    if current_user.role == UserRole.TECHNICIAN:
        technician = get_technician_for_current_user(
            db,
            current_user,
        )

        if job.assigned_technician_id != technician.technician_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This job is not assigned to you",
            )

    return get_job_closure(
        db=db,
        job_id=job.id,
    )


