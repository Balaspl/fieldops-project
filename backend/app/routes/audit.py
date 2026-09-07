from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
import logging

from app.database import get_db
from app.models import (
    OverrideAuditEvent,
    Job,
    SecurityAuditLog,
)
from app.models.sentiment_audit import SentimentAuditRecord
from app.schemas import OverrideAuditResponse
from app.dependencies.override_authorization import verify_jwt_token
from app.sentiment.audit import SentimentAuditLogger

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/audit",
    tags=["Audit"]
)


@router.get(
    "/overrides/{job_id}",
    response_model=list[OverrideAuditResponse],
)
def get_override_audits_for_job(
    job_id: str,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    authorization: str = Depends(verify_jwt_token),
    db: Session = Depends(get_db),
):
    try:
        job_db_id = int(job_id)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid job ID format",
        )

    # Verify job belongs to tenant
    job = (
        db.query(Job)
        .filter(
            Job.id == job_db_id,
            Job.tenant_id == x_tenant_id,
        )
        .first()
    )

    if not job:
        raise HTTPException(
            status_code=404,
            detail="Job not found",
        )

    audits = (
        db.query(OverrideAuditEvent)
        .filter(
            OverrideAuditEvent.job_id == job_db_id,
            OverrideAuditEvent.tenant_id == x_tenant_id,
        )
        .order_by(
            OverrideAuditEvent.created_at.desc()
        )
        .all()
    )

    return audits


@router.get("/security")
def get_security_audit_logs(
    tenant_id: str,
    event_type: str = None,
    start_date: str = None,
    end_date: str = None,
    db: Session = Depends(get_db),
):
    query = db.query(SecurityAuditLog).filter(
        SecurityAuditLog.tenant_id == tenant_id
    )

    if event_type:
        query = query.filter(
            SecurityAuditLog.event == event_type
        )

    if start_date:
        try:
            dt = datetime.fromisoformat(start_date)
            query = query.filter(
                SecurityAuditLog.timestamp >= dt
            )
        except ValueError:
            query = query.filter(
                SecurityAuditLog.timestamp >= start_date
            )

    if end_date:
        try:
            dt = datetime.fromisoformat(end_date)
            query = query.filter(
                SecurityAuditLog.timestamp <= dt
            )
        except ValueError:
            query = query.filter(
                SecurityAuditLog.timestamp <= end_date
            )

    logs = (
        query
        .order_by(
            SecurityAuditLog.timestamp.desc()
        )
        .all()
    )

    return [
        {
            "id": log.id,
            "event": log.event,
            "timestamp": (
                log.timestamp.isoformat()
                if log.timestamp
                else None
            ),
            "severity": log.severity,
            "user_tenant": log.user_tenant,
            "attempted_channel": log.attempted_channel,
            "ip_address": log.ip_address,
            "websocket_id": log.websocket_id,
            "action_taken": log.action_taken,
            "payload_tenant": log.payload_tenant,
            "target_tenant": log.target_tenant,
            "technician_id": log.technician_id,
            "job_id": log.job_id,
            "tenant_id": log.tenant_id,
        }
        for log in logs
    ]


@router.get("/sentiment")
def get_sentiment_audit_logs(
    tenant_id: str,
    customer_id: str | None = None,
    job_id: int | None = None,
    manager_id: str | None = None,
    sentiment_label: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
):
    """
    Search sentiment audit records.

    Supported filters:
        - customer_id
        - job_id
        - manager_id
        - sentiment_label
        - start_date
        - end_date
    """

    try:
        parsed_start_date = (
            datetime.fromisoformat(start_date)
            if start_date
            else None
        )

        parsed_end_date = (
            datetime.fromisoformat(end_date)
            if end_date
            else None
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid date format. Use ISO-8601 format.",
        ) from exc

    logger_service = SentimentAuditLogger(db)

    records = logger_service.search(
        tenant_id=tenant_id,
        customer_id=customer_id,
        job_id=job_id,
        manager_id=manager_id,
        sentiment_label=sentiment_label,
        start_date=parsed_start_date,
        end_date=parsed_end_date,
    )

    return [
        {
            "id": record.id,
            "tenant_id": record.tenant_id,
            "event_type": record.event_type,
            "customer_id": record.customer_id,
            "job_id": record.job_id,
            "manager_id": record.manager_id,
            "input_text": record.input_text,
            "sentiment_label": record.sentiment_label,
            "confidence": record.confidence,
            "model_used": record.model_used,
            "cost": record.cost,
            "trigger_reason": record.trigger_reason,
            "action": record.action,
            "notes": record.notes,
            "timestamp": (
                record.timestamp.isoformat()
                if record.timestamp
                else None
            ),
            "sequence_number": record.sequence_number,
            "previous_hash": record.previous_hash,
            "record_hash": record.record_hash,
            "archived_at": (
                record.archived_at.isoformat()
                if record.archived_at
                else None
            ),
        }
        for record in records
    ]