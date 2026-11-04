"""Deliver a native push when a technician receives a job assignment."""

import logging

from app.database import SessionLocal
from app.services.fcm import send_job_assignment_notification

logger = logging.getLogger(__name__)


async def send_assignment_push(
    *,
    job_id: int | str,
    tenant_id: str,
    technician_id: str,
    job_title: str | None = None,
    location: str | None = None,
) -> None:
    """Send assignment push using the persisted technician token.

    The caller invokes this only after the assignment transaction commits.
    Delivery failures are logged and do not undo the assignment.
    """
    db = SessionLocal()
    try:
        result = await send_job_assignment_notification(
            db=db,
            job_id=str(job_id),
            tenant_id=str(tenant_id),
            job_title=job_title or f"Job {job_id}",
            location=location or "Customer location",
            tech_ids=[str(technician_id)],
            notification_title="New Job Assigned",
            notification_body=(
                f"You have been assigned to Job #{job_id}: "
                f"{job_title or 'Service Request'} at "
                f"{location or 'Customer location'}."
            ),
            notification_type="technician_job_assigned",
            priority="HIGH",
        )
        if not result.get("sent", 0):
            logger.warning(
                "Assignment push was not delivered job_id=%s technician_id=%s failed=%s reason=%s",
                job_id,
                technician_id,
                result.get("failed", 0),
                result.get("reason", "no_registered_token_or_fcm_failure"),
            )
    except Exception:
        logger.exception(
            "Assignment push delivery failed job_id=%s technician_id=%s",
            job_id,
            technician_id,
        )
    finally:
        db.close()
