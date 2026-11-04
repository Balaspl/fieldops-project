"""Send technician remote pushes through the Expo Push Service.

The module keeps its historical name and function contract so existing
notification callers continue to work. Device tokens stored in the legacy
``fcm_token`` column are ExpoPushTokens; the backend does not initialize or
authenticate with Firebase Admin.
"""

from __future__ import annotations

import asyncio
import os
import uuid

import requests
from sqlalchemy.orm import Session

from ..logger import logger
from ..models import NotificationDelivery, Technician
from .preferences import get_technician_preferences

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
ANDROID_CHANNEL_ID = "fieldops_job_assignments_v2"
EXPO_TOKEN_PREFIXES = ("ExponentPushToken[", "ExpoPushToken[")


def _record_delivery(
    db: Session,
    *,
    tenant_id: str,
    technician_id: str,
    job_id: str,
    status: str,
    ticket_id: str | None = None,
    error_message: str | None = None,
) -> int | str:
    delivery = NotificationDelivery(
        tenant_id=tenant_id,
        tech_id=technician_id,
        job_id=job_id,
        status=status,
        fcm_message_id=ticket_id,
        error_message=error_message,
    )
    db.add(delivery)
    db.commit()
    db.refresh(delivery)
    return delivery.id


async def send_job_assignment_notification(
    db: Session,
    job_id: str,
    tenant_id: str,
    job_title: str,
    location: str,
    tech_ids: list[str],
    correlation_id: str | None = None,
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
        if isinstance(notification_title, str) and notification_title.strip()
        else "FieldOps Update"
    )
    safe_body = (
        notification_body.strip()
        if isinstance(notification_body, str) and notification_body.strip()
        else "A FieldOps job has an update."
    )
    safe_notification_type = str(notification_type).strip().lower()
    safe_priority = str(priority).strip().upper()

    if not safe_notification_type:
        raise ValueError("notification_type must not be empty.")
    if len(safe_title) > 50:
        raise ValueError("Push title exceeds 50 characters.")

    if not tech_ids:
        return {"sent": 0, "failed": 0, "delivery_ids": []}

    technicians = (
        db.query(Technician)
        .filter(Technician.tech_id.in_(tech_ids))
        .all()
    )
    valid_technicians = [tech for tech in technicians if tech.fcm_token]
    technician_by_token = {
        str(tech.fcm_token): tech for tech in valid_technicians
    }
    failed_count = len(tech_ids) - len(valid_technicians)
    enabled_technicians = []

    for tech in valid_technicians:
        preferences = get_technician_preferences(db, tech.tech_id)
        if preferences.get("push_enabled", True):
            enabled_technicians.append(tech)
        else:
            failed_count += 1
            logger.info(
                "Skipping technician push because push notifications are disabled",
                extra={**log_extra, "technician_id": tech.tech_id},
            )

    if not enabled_technicians:
        logger.info(
            "No technicians with registered Expo push tokens and push enabled",
            extra=log_extra,
        )
        return {"sent": 0, "failed": failed_count, "delivery_ids": []}

    data_payload = {
        "job_id": str(job_id),
        "job_title": str(job_title),
        "location": str(location),
        "priority": safe_priority,
        "type": safe_notification_type,
    }
    if safe_notification_type in {"job_assignment", "technician_job_assigned"}:
        data_payload.update(
            {
                "accept_url": f"https://api.fieldops.io/v1/jobs/{job_id}/accept",
                "reject_url": f"https://api.fieldops.io/v1/jobs/{job_id}/reject",
                "expires_in": "600",
            }
        )

    sent_count = 0
    delivery_ids: list[int | str] = []
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    expo_access_token = os.getenv("EXPO_ACCESS_TOKEN", "").strip()
    if expo_access_token:
        headers["Authorization"] = f"Bearer {expo_access_token}"

    for tech in enabled_technicians:
        token = str(tech.fcm_token)
        if not token.startswith(EXPO_TOKEN_PREFIXES):
            failed_count += 1
            logger.warning(
                "Stored technician token is not an Expo push token; technician must reopen the updated app",
                extra={**log_extra, "technician_id": tech.tech_id},
            )
            delivery_ids.append(
                _record_delivery(
                    db,
                    tenant_id=tenant_id,
                    technician_id=str(tech.tech_id),
                    job_id=str(job_id),
                    status="failed",
                    error_message="Technician must register an Expo push token.",
                )
            )
            continue

        message = {
            "to": token,
            "title": safe_title,
            "body": safe_body,
            "sound": "default",
            "priority": "high" if safe_priority == "HIGH" else "default",
            "channelId": ANDROID_CHANNEL_ID,
            "data": data_payload,
            "categoryId": (
                "JOB_ASSIGNMENT"
                if safe_notification_type
                in {"job_assignment", "technician_job_assigned"}
                else "JOB_UPDATE"
            ),
        }

        ticket: dict = {}
        last_error: Exception | None = None
        for attempt in range(max(1, max_retries)):
            try:
                response = await asyncio.to_thread(
                    requests.post,
                    EXPO_PUSH_URL,
                    json=message,
                    headers=headers,
                    timeout=10,
                )
                response.raise_for_status()
                response_data = response.json().get("data")
                if isinstance(response_data, list):
                    ticket = response_data[0] if response_data else {}
                elif isinstance(response_data, dict):
                    ticket = response_data
                else:
                    ticket = {}
                last_error = None
                break
            except (requests.RequestException, ValueError) as exc:
                last_error = exc
                status_code = (
                    exc.response.status_code
                    if isinstance(exc, requests.HTTPError) and exc.response
                    else None
                )
                should_retry = (
                    status_code is None
                    or status_code == 429
                    or status_code >= 500
                )
                if not should_retry or attempt + 1 >= max(1, max_retries):
                    break
                await asyncio.sleep(2**attempt)

        if last_error is not None:
            failed_count += 1
            logger.warning(
                "Expo Push Service request failed",
                extra={
                    **log_extra,
                    "technician_id": tech.tech_id,
                    "error_type": type(last_error).__name__,
                },
            )
            delivery_ids.append(
                _record_delivery(
                    db,
                    tenant_id=tenant_id,
                    technician_id=str(tech.tech_id),
                    job_id=str(job_id),
                    status="failed",
                    error_message=f"Expo push request failed: {type(last_error).__name__}",
                )
            )
            continue

        if ticket.get("status") == "ok":
            sent_count += 1
            delivery_ids.append(
                _record_delivery(
                    db,
                    tenant_id=tenant_id,
                    technician_id=str(tech.tech_id),
                    job_id=str(job_id),
                    status="delivered",
                    ticket_id=ticket.get("id"),
                )
            )
            continue

        failed_count += 1
        error_code = (ticket.get("details") or {}).get("error")
        error_message = str(ticket.get("message") or "Expo rejected the push.")
        if error_code == "DeviceNotRegistered":
            db.query(Technician).filter(
                Technician.tech_id == tech.tech_id,
                Technician.tenant_id == tenant_id,
                Technician.fcm_token == token,
            ).update(
                {"fcm_token": None, "device_type": None},
                synchronize_session=False,
            )
            db.commit()
        logger.warning(
            "Expo Push Service rejected a technician notification",
            extra={
                **log_extra,
                "technician_id": tech.tech_id,
                "error_code": error_code,
            },
        )
        delivery_ids.append(
            _record_delivery(
                db,
                tenant_id=tenant_id,
                technician_id=str(tech.tech_id),
                job_id=str(job_id),
                status="failed",
                error_message=error_message[:500],
            )
        )

    return {
        "sent": sent_count,
        "failed": failed_count,
        "delivery_ids": delivery_ids,
    }
