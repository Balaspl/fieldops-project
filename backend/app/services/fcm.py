import firebase_admin
from firebase_admin import credentials, messaging
import asyncio
import uuid
from sqlalchemy.orm import Session
from ..logger import logger
from ..models import Technician, NotificationDelivery
from .preferences import get_technician_preferences

# Initialize Firebase Admin with default credentials if available
try:
    if not firebase_admin._apps:
        firebase_admin.initialize_app()
    logger.info("Firebase Admin initialized successfully.")
except Exception as e:
    logger.warning(f"Could not initialize Firebase Admin SDK (it might need GOOGLE_APPLICATION_CREDENTIALS): {e}")

async def send_job_assignment_notification(
    db: Session,
    job_id: str,
    tenant_id: str,
    job_title: str,
    location: str,
    tech_ids: list[str],
    correlation_id: str = None,
    max_retries: int = 3,
    notification_title: str | None = None,
    notification_body: str | None = None,
    notification_type: str = "job_assignment",
    priority: str = "HIGH",
) -> dict:
    
    correlation_id = correlation_id or str(uuid.uuid4())
    log_extra = {"correlation_id": correlation_id, "job_id": job_id}
    safe_title = (
        notification_title.strip()
        if isinstance(
            notification_title,
            str,
        )
        and notification_title.strip()
        else "FieldOps Update"
    )

    safe_body = (
        notification_body.strip()
        if isinstance(
            notification_body,
            str,
        )
        and notification_body.strip()
        else "A FieldOps job has an update."
    )

    safe_notification_type = (
        str(
            notification_type
        )
        .strip()
        .lower()
    )

    safe_priority = (
        str(
            priority
        )
        .strip()
        .upper()
    )

    if not safe_notification_type:
        raise ValueError(
            "notification_type must not be empty."
        )

    # Final transport-level validation after placeholders have
    # been restored.
    if len(safe_title) > 50:
        raise ValueError(
            "Push title exceeds 50 characters."
        )    
    
    techs = db.query(Technician).filter(Technician.tech_id.in_(tech_ids)).all()
    valid_techs = [t for t in techs if t.fcm_token]
    
    final_valid_techs = []
    failed_count = len(tech_ids) - len(valid_techs)
    
    for t in valid_techs:
        prefs = get_technician_preferences(db, t.tech_id)
        if prefs.get("push_enabled", True):
            final_valid_techs.append(t)
        else:
            logger.info(f"Skipping tech {t.tech_id} (push notifications disabled)", extra=log_extra)
            failed_count += 1
    
    if not final_valid_techs:
        logger.info("No technicians with valid FCM tokens and push enabled found.", extra=log_extra)
        return {"sent": 0, "failed": failed_count, "delivery_ids": []}

    tech_map = {t.fcm_token: t.tech_id for t in final_valid_techs}
    current_tokens = list(tech_map.keys())
    
    # Payload Construction
    data_payload = {
        "job_id": str(job_id),
        "job_title": str(job_title),
        "location": str(location),
        "priority": safe_priority,
        "type": safe_notification_type,
    }

    # Assignment actions are included only for assignment events.
    if safe_notification_type in {
        "job_assignment",
        "technician_job_assigned",
    }:
        data_payload.update(
            {
                "accept_url": (
                    "https://api.fieldops.io/v1/jobs/"
                    f"{job_id}/accept"
                ),
                "reject_url": (
                    "https://api.fieldops.io/v1/jobs/"
                    f"{job_id}/reject"
                ),
                "expires_in": "600",
            }
        )

    notification = messaging.Notification(
        title=safe_title,
        body=safe_body,
    )

    android_config = messaging.AndroidConfig(
        priority=(
            "high"
            if safe_priority == "HIGH"
            else "normal"
        ),
        notification=messaging.AndroidNotification(
            channel_id="job_assignments",
            sound="default"
        )
    )

    apns_config = messaging.APNSConfig(
        payload=messaging.APNSPayload(
            aps=messaging.Aps(
                alert=messaging.ApsAlert(
                    title=safe_title,
                    body=safe_body,
                ),
                badge=1,
                sound="default",
                category=(
                    "JOB_ASSIGNMENT"
                    if safe_notification_type
                    in {
                        "job_assignment",
                        "technician_job_assigned",
                    }
                    else "JOB_UPDATE"
                )
            )
        )
    )

    sent_count = 0
    delivery_ids = []

    for attempt in range(max_retries):
        if not current_tokens:
            break
            
        message = messaging.MulticastMessage(
            tokens=current_tokens,
            notification=notification,
            data=data_payload,
            android=android_config,
            apns=apns_config
        )
        
        try:
            logger.info(f"Attempting to send push notifications to {len(current_tokens)} tokens (Attempt {attempt+1}/{max_retries})", extra=log_extra)
            response = messaging.send_each_for_multicast(message)
            failed_tokens_next_round = []
            
            for idx, resp in enumerate(response.responses):
                token = current_tokens[idx]
                tech_id = tech_map[token]
                
                if resp.success:
                    sent_count += 1
                    delivery = NotificationDelivery(
                        tenant_id=tenant_id,
                        tech_id=tech_id,
                        job_id=str(job_id),
                        status="delivered",
                        fcm_message_id=resp.message_id
                    )
                    db.add(delivery)
                    db.commit()
                    db.refresh(delivery)
                    delivery_ids.append(delivery.id)
                else:
                    err_type = type(resp.exception).__name__
                    if "UnregisteredError" in err_type or "InvalidArgumentError" in err_type:
                        # Invalid token - cleanup
                        tech = db.query(Technician).filter(Technician.tech_id == tech_id).first()
                        if tech:
                            tech.fcm_token = None
                            logger.info(f"Cleaned up invalid token for tech_id {tech_id}", extra=log_extra)
                        failed_count += 1
                        delivery = NotificationDelivery(
                            tenant_id=tenant_id,
                            tech_id=tech_id, 
                            job_id=str(job_id), 
                            status="failed", 
                            error_message=str(resp.exception)
                        )
                        db.add(delivery)
                        db.commit()
                        db.refresh(delivery)
                        delivery_ids.append(delivery.id)
                    else:
                        # Transient error, add to retry queue
                        if attempt == max_retries - 1:
                            failed_count += 1
                            delivery = NotificationDelivery(
                                tenant_id=tenant_id,
                                tech_id=tech_id,
                                job_id=str(job_id),
                                status="failed",
                                error_message=str(resp.exception)
                            )
                            db.add(delivery)
                            db.commit()
                            db.refresh(delivery)
                            delivery_ids.append(delivery.id)
                        else:
                            failed_tokens_next_round.append(token)
            
            current_tokens = failed_tokens_next_round
            if current_tokens:
                logger.warning(f"{len(current_tokens)} tokens failed with transient errors. Retrying...", extra=log_extra)
                await asyncio.sleep(2 ** attempt)
                
        except Exception as e:
            logger.error(f"FCM batch send globally failed: {e}", extra=log_extra)
            if attempt == max_retries - 1:
                # Final attempt failed
                for token in current_tokens:
                    failed_count += 1
                    tech_id = tech_map[token]
                    delivery = NotificationDelivery(
                        tenant_id=tenant_id,
                        tech_id=tech_id,
                        job_id=str(job_id),
                        status="failed",
                        error_message=str(e)
                    )
                    db.add(delivery)
                    db.commit()
                    db.refresh(delivery)
                    delivery_ids.append(delivery.id)
            else:
                await asyncio.sleep(2 ** attempt)

    return {"sent": sent_count, "failed": failed_count, "delivery_ids": delivery_ids}
