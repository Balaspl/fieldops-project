import base64
import json
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query, Header
from sqlalchemy.orm import Session
from sqlalchemy import or_, desc, asc

from app.database import get_db
from app.models import Job, Technician
from app.routes.dispatch import verify_jwt_token
from app.schemas import (
    DispatchQueueResponse,
    DispatchQueueJob,
    SLADetail,
    QueueTechnicianDetail,
    DispatchQueuePagination
)

router = APIRouter(
    prefix="/dispatch",
    tags=["Dispatch"]
)

def calculate_sla_risk(deadline: Optional[datetime]) -> tuple[Optional[float], str]:
    if not deadline:
        return None, "LOW"
    
    now_utc = datetime.now(timezone.utc)
    remaining_minutes = (deadline - now_utc).total_seconds() / 60
    
    if remaining_minutes < 0:
        return remaining_minutes, "CRITICAL"
    elif remaining_minutes < 10:
        return remaining_minutes, "CRITICAL"
    elif remaining_minutes < 30:
        return remaining_minutes, "HIGH"
    elif remaining_minutes < 60:
        return remaining_minutes, "MEDIUM"
    else:
        return remaining_minutes, "LOW"

@router.get("/queue", response_model=DispatchQueueResponse)
def get_dispatch_queue(
    status: Optional[str] = Query(None, description="Filter by status (e.g., QUEUED, ASSIGNED)"),
    priority: Optional[str] = Query(None, description="Filter by priority"),
    zone: Optional[str] = Query(None, description="Filter by zone (matches location)"),
    cursor: Optional[str] = Query(None, description="Pagination cursor"),
    limit: int = Query(50, le=100, description="Max jobs to return"),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    authorization: str = Depends(verify_jwt_token),
    db: Session = Depends(get_db)
):
    start_time = time.time()
    
    query = db.query(Job).filter(Job.tenant_id == x_tenant_id)
    
    if status:
        query = query.filter(Job.status == status)
    else:
        query = query.filter(Job.status.in_(["QUEUED", "ASSIGNED"]))
        
    if priority:
        query = query.filter(Job.priority == priority)
        
    if zone:
        query = query.filter(Job.location.ilike(f"%{zone}%"))
        
    # Apply cursor pagination if present
    # Using sla_deadline ASC (nulls last) as primary sort, and id ASC as secondary
    if cursor:
        try:
            cursor_str = base64.b64decode(cursor).decode('utf-8')
            # format: "iso_date|job_id" or "null|job_id"
            c_date_str, c_id_str = cursor_str.split("|")
            c_id = int(c_id_str)
            if c_date_str != "null":
                c_date = datetime.fromisoformat(c_date_str)
                query = query.filter(
                    or_(
                        Job.sla_deadline > c_date,
                        (Job.sla_deadline == c_date) & (Job.id > c_id)
                    )
                )
            else:
                # If the previous page's last item had no deadline, we only look at items with no deadline and id > c_id
                query = query.filter(
                    Job.sla_deadline.is_(None),
                    Job.id > c_id
                )
        except Exception:
            pass # Invalid cursor, ignore

    # Sort: highest SLA risk first means earliest deadline first
    # Nulls last so jobs without SLA don't clog the top
    query = query.order_by(
        Job.sla_deadline.asc().nulls_last(),
        Job.id.asc()
    )
    
    # Fetch limit + 1 to know if there's a next page
    jobs = query.limit(limit + 1).all()
    has_more = len(jobs) > limit
    results = jobs[:limit]
    
    data = []
    for job in results:
        minutes_remaining, risk_level = calculate_sla_risk(job.sla_deadline)
        
        tech_detail = None
        if job.technician:
            tech_detail = QueueTechnicianDetail(
                tech_id=job.technician.tech_id or str(job.technician.technician_id),
                name=job.technician.technician_name,
                status=job.technician.technician_status
            )
            
        data.append(DispatchQueueJob(
            job_id=str(job.id),
            title=job.service_type, # Using service_type as title
            status=job.status,
            priority=job.priority,
            customer=job.customer_name,
            location=job.location,
            technician=tech_detail,
            sla=SLADetail(
                deadline=job.sla_deadline,
                minutes_remaining=minutes_remaining,
                risk_level=risk_level
            ),
            assigned_at=job.updated_at if job.status == "ASSIGNED" else None,
            acceptance_expires_at=None # Ideally fetched from TimerService if needed
        ))
        
    next_cursor = None
    if has_more and results:
        last_item = results[-1]
        c_date_str = last_item.sla_deadline.isoformat() if last_item.sla_deadline else "null"
        cursor_str = f"{c_date_str}|{last_item.id}"
        next_cursor = base64.b64encode(cursor_str.encode('utf-8')).decode('utf-8')
        
    execution_time_ms = (time.time() - start_time) * 1000
    # Log metrics to ensure NFR-001 (P95 < 200ms) is visible
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"dispatch_queue_accessed - {len(results)} items in {execution_time_ms:.2f}ms")

    return DispatchQueueResponse(
        data=data,
        pagination=DispatchQueuePagination(
            next_cursor=next_cursor,
            has_more=has_more
        )
    )
