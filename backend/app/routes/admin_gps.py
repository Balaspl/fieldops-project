from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
from typing import Optional
import uuid

from ..database import get_db
from ..redis_client import get_redis_client
from ..logger import logger
from .. import models
from ..auth.dependencies import (
    get_current_user_or_tenant,
    AuthenticatedUser,
    require_role,
)

from ..auth.rbac import UserRole
from ..auth.dependencies import (
    get_current_user_or_tenant,
    AuthenticatedUser,
)
from ..tasks import execute_job_gps_purge_sync


router = APIRouter(
    prefix="/api/v1/admin/gps",
    tags=["Admin GPS"],
)


class AdminPurgeRequest(BaseModel):
    dry_run: bool = False


class TenantConfigPatchRequest(BaseModel):
    retention_days: int = Field(
        ...,
        ge=1,
        le=90,
        description="Retention period in days (1-90)",
    )


@router.post("/purge/{job_id}", status_code=200)
def manual_job_gps_purge(
    job_id: str,
    payload: AdminPurgeRequest,
    request: Request,
    user_tenant: tuple[AuthenticatedUser, str] = Depends(
        get_current_user_or_tenant
    ),
    db: Session = Depends(get_db),
):
    user, x_tenant_id = user_tenant

    # Enforce admin permission
    if "admin" not in user.role.lower():
        logger.warning(
            f"Unauthorized purge attempt by user: {user.user_id}"
        )
        raise HTTPException(
            status_code=403,
            detail="Access denied: Admin role required",
        )

    correlation_id = request.headers.get(
        "X-Correlation-ID",
        str(uuid.uuid4()),
    )
    log_extra = {
        "correlation_id": correlation_id,
        "tenant_id": x_tenant_id,
        "job_id": job_id,
    }

    # Verify job exists within the authenticated tenant
    job = None
    if job_id.isdigit():
        job = db.query(models.Job).filter(
            models.Job.id == int(job_id),
            models.Job.tenant_id == x_tenant_id,
        ).first()

    if not job and job_id.isdigit():
        # Distinguish a cross-tenant job from a non-existent job.
        any_job = db.query(models.Job).filter(
            models.Job.id == int(job_id)
        ).first()

        if any_job:
            logger.error(
                f"Cross-tenant access attempted for job: {job_id}",
                extra=log_extra,
            )
            raise HTTPException(
                status_code=403,
                detail="Access denied",
            )

    if payload.dry_run:
        # Dry-run: count matching pings without deleting
        count = db.query(models.GPSPing).filter(
            models.GPSPing.job_id == job_id,
            models.GPSPing.tenant_id == x_tenant_id,
        ).count()

        logger.info(
            f"Dry run GPS purge preview for job {job_id}: "
            f"{count} records would be deleted",
            extra=log_extra,
        )

        return {
            "status": "dry_run_preview",
            "deleted_count": count,
            "job_id": job_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # Perform actual purge
    deleted_count = execute_job_gps_purge_sync(
        db=db,
        job_id=job_id,
        tenant_id=x_tenant_id,
        purge_type="manual",
        correlation_id=correlation_id,
    )

    return {
        "status": "purged",
        "deleted_count": deleted_count,
        "job_id": job_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/purge-stats", status_code=200)
def get_gps_purge_stats(
    current_user: AuthenticatedUser = Depends(
        require_role(UserRole.HEAD)
    ),
    redis_client=Depends(get_redis_client),
):

    now = datetime.now(timezone.utc)

    # These are global/system-level purge statistics.
    total_purged_30d = 0
    last_purge_run = None
    next_scheduled = None

    try:
        if redis_client:
            raw_total = redis_client.get(
                "gps_purge:total_purged_30d"
            )
            if raw_total:
                total_purged_30d = int(raw_total)

            raw_last = redis_client.get(
                "gps_purge:last_purge_run"
            )
            if raw_last:
                last_purge_run = raw_last

            raw_next = redis_client.get(
                "gps_purge:next_scheduled"
            )
            if raw_next:
                next_scheduled = raw_next
    except Exception as e:
        logger.warning(
            f"Redis stats fetch failed: {e}"
        )

    # Compute fallback if not set in Redis
    if not next_scheduled:
        next_run = datetime(
            now.year,
            now.month,
            now.day,
            2,
            0,
            tzinfo=timezone.utc,
        )

        if next_run <= now:
            next_run += timedelta(days=1)

        next_scheduled = next_run.isoformat()

    return {
        "total_purged_30d": total_purged_30d,
        "last_purge_run": last_purge_run,
        "next_scheduled": next_scheduled,
    }


@router.post("/config", status_code=200)
def set_tenant_retention_config(
    payload: TenantConfigPatchRequest,
    user_tenant: tuple[AuthenticatedUser, str] = Depends(
        get_current_user_or_tenant
    ),
    db: Session = Depends(get_db),
):
    user, x_tenant_id = user_tenant

    if "admin" not in user.role.lower():
        raise HTTPException(
            status_code=403,
            detail="Access denied: Admin role required",
        )

    config = db.query(
        models.TenantGPSConfiguration
    ).filter(
        models.TenantGPSConfiguration.tenant_id == x_tenant_id
    ).first()

    if not config:
        config = models.TenantGPSConfiguration(
            tenant_id=x_tenant_id,
            retention_days=payload.retention_days,
        )
        db.add(config)
    else:
        config.retention_days = payload.retention_days

    db.commit()
    db.refresh(config)

    return {
        "tenant_id": config.tenant_id,
        "retention_days": config.retention_days,
    }


@router.get("/purge-audit", status_code=200)
def get_purge_audit_logs(
    job_id: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    user_tenant: tuple[AuthenticatedUser, str] = Depends(
        get_current_user_or_tenant
    ),
    db: Session = Depends(get_db),
):
    user, x_tenant_id = user_tenant

    if "admin" not in user.role.lower():
        raise HTTPException(
            status_code=403,
            detail="Access denied: Admin role required",
        )

    query = db.query(
        models.GPSPurgeAuditLog
    ).filter(
        models.GPSPurgeAuditLog.tenant_id == x_tenant_id
    )

    if job_id:
        query = query.filter(
            models.GPSPurgeAuditLog.job_id == job_id
        )

    if start_date:
        query = query.filter(
            models.GPSPurgeAuditLog.created_at >= start_date
        )

    if end_date:
        query = query.filter(
            models.GPSPurgeAuditLog.created_at <= end_date
        )

    return query.order_by(
        models.GPSPurgeAuditLog.created_at.desc()
    ).all()


@router.get("/purge-status/{job_id}", status_code=200)
def get_purge_status(
    job_id: str,
    user_tenant: tuple[AuthenticatedUser, str] = Depends(
        get_current_user_or_tenant
    ),
    redis_client=Depends(get_redis_client),
    db: Session = Depends(get_db),
):
    user, x_tenant_id = user_tenant

    if "admin" not in user.role.lower():
        raise HTTPException(
            status_code=403,
            detail="Access denied: Admin role required",
        )

    # Check if job exists within the authenticated tenant
    job = None
    if job_id.isdigit():
        job = db.query(models.Job).filter(
            models.Job.id == int(job_id),
            models.Job.tenant_id == x_tenant_id,
        ).first()

        if not job:
            any_job = db.query(models.Job).filter(
                models.Job.id == int(job_id)
            ).first()

            if any_job:
                raise HTTPException(
                    status_code=403,
                    detail="Access denied",
                )

    status_key = f"gps_purge_status:{job_id}"

    if redis_client:
        try:
            raw_data = redis_client.get(status_key)
            if raw_data:
                import json

                return json.loads(raw_data)
        except Exception as e:
            logger.warning(
                f"Failed to read purge status from Redis: {e}"
            )

    # Fallback: look at DB audit logs
    audit = db.query(
        models.GPSPurgeAuditLog
    ).filter(
        models.GPSPurgeAuditLog.job_id == job_id,
        models.GPSPurgeAuditLog.tenant_id == x_tenant_id,
    ).order_by(
        models.GPSPurgeAuditLog.created_at.desc()
    ).first()

    if audit:
        return {
            "job_id": str(job_id),
            "purge_status": "completed",
            "purged_at": audit.created_at.isoformat(),
            "deleted_count": audit.deleted_count,
        }

    return {
        "job_id": str(job_id),
        "purge_status": "not_started",
        "purged_at": None,
        "deleted_count": 0,
    }


@router.get("/rejected-pings", status_code=200)
def get_rejected_pings(
    technician_id: Optional[str] = None,
    job_id: Optional[str] = None,
    user_tenant: tuple[AuthenticatedUser, str] = Depends(
        get_current_user_or_tenant
    ),
    db: Session = Depends(get_db),
):
    user, x_tenant_id = user_tenant

    if "admin" not in user.role.lower():
        raise HTTPException(
            status_code=403,
            detail="Access denied: Admin role required",
        )

    query = db.query(
        models.GPSRejectedPingLog
    ).filter(
        models.GPSRejectedPingLog.tenant_id == x_tenant_id
    )

    if technician_id:
        query = query.filter(
            models.GPSRejectedPingLog.technician_id == technician_id
        )

    if job_id:
        query = query.filter(
            models.GPSRejectedPingLog.job_id == job_id
        )

    return query.order_by(
        models.GPSRejectedPingLog.timestamp.desc()
    ).all()