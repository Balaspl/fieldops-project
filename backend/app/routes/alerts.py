from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from datetime import datetime, timezone
import logging

from app.database import get_db
from app.models import DispatcherAlert
from app.sentiment.audit import SentimentAuditLogger
from app.schemas import AlertAcknowledgeRequest, DispatcherAlertResponse
from app.routes.dispatch import verify_jwt_token

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/alerts",
    tags=["Alerts"]
)

@router.post("/{alert_id}/acknowledge")
def acknowledge_alert(
    alert_id: str, 
    payload: AlertAcknowledgeRequest,
    db: Session = Depends(get_db),
    authorization: str = Depends(verify_jwt_token)
):
    alert = db.query(DispatcherAlert).filter(DispatcherAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
        
    alert.acknowledged = 1 if payload.acknowledged else 0
    if alert.type == "customer_sentiment":
        audit_logger = SentimentAuditLogger(db)

        audit_logger.log_manager_action(
            {
                "tenant_id": alert.tenant_id,
                "job_id": alert.job_id,
                "action": (
                    "acknowledge"
                    if payload.acknowledged
                    else "unacknowledge"
                ),
                "notes": None,
            }
        )
    db.commit()
    
    logger.info(f"Alert {alert_id} acknowledged by user {authorization}")
    return {"message": "Alert acknowledged successfully"}

@router.get("/", response_model=list[DispatcherAlertResponse])
def get_alerts(db: Session = Depends(get_db), authorization: str = Depends(verify_jwt_token)):
    alerts = db.query(DispatcherAlert).order_by(DispatcherAlert.created_at.desc()).limit(50).all()
    
    results = []
    for a in alerts:
        results.append(
            DispatcherAlertResponse(
                alert_id=a.id,
                type=a.type,
                severity=a.severity,
                job_id=str(a.job_id),
                job_title=f"Job {a.job_id}", # In a real scenario we'd join with Job
                attempt_count=a.attempt_count,
                max_attempts=a.max_attempts,
                excluded_technicians=a.excluded_technicians or [],
                recommended_action=a.recommended_action,
                created_at=a.created_at,
                acknowledged=bool(a.acknowledged)
            )
        )
    return results
