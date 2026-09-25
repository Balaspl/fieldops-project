import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import InAppNotification, ServiceRequest


STATUS_NOTIFICATION_TEMPLATES = {
    "EN_ROUTE": {
        "title": "Technician is on the way",
        "body": (
            "Your technician has started travelling to "
            "your service request #{job_id}."
        ),
    },
    "ON_SITE": {
        "title": "Technician has arrived",
        "body": (
            "Your technician has arrived at the service location "
            "for service request #{job_id}."
        ),
    },
    "IN_PROGRESS": {
        "title": "Job in progress",
        "body": (
            "Your technician is now working on "
            "your service request #{job_id}."
        ),
    },
    "COMPLETED": {
        "title": "Job completed",
        "body": (
            "Your service request #{job_id} has been completed."
        ),
    },
    "CANCELLED": {
        "title": "Job cancelled",
        "body": (
            "Your service request #{job_id} has been cancelled."
        ),
    },
}


def create_customer_job_status_notification(
    db: Session,
    job,
    new_status: str,
) -> InAppNotification | None:
    """
    Create an in-app notification for the customer associated
    with the job's service request.

    Customer notifications are intentionally isolated from
    technician notifications:
        tech_id = None
        customer_user_id = service_request.customer_user_id

    Returns the notification object when created.
    Returns None when the job has no customer recipient.
    """

    status = str(new_status).upper().strip()

    template = STATUS_NOTIFICATION_TEMPLATES.get(status)

    if template is None:
        return None

    service_request = (
        db.query(ServiceRequest)
        .filter(
            ServiceRequest.linked_job_id == job.id,
        )
        .first()
    )

    if not service_request:
        return None

    if not service_request.customer_user_id:
        return None

    customer_user_id = str(service_request.customer_user_id)

    notification = InAppNotification(
        id=str(uuid.uuid4()),
        tenant_id=str(service_request.tenant_id),
        tech_id=None,
        customer_user_id=customer_user_id,
        job_id=str(job.id),
        type="JOB_STATUS_CHANGED",
        title=template["title"],
        body=template["body"].format(job_id=job.id),
        status="UNREAD",
        priority="NORMAL",
        created_at=datetime.now(timezone.utc),
    )

    db.add(notification)

    return notification