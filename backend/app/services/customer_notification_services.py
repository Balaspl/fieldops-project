
"""Legacy customer notification entry point.

Job status notifications are now owned by the Communication Agent graph.
This shim remains so older imports fail safely without staging or publishing a
second hardcoded customer notification.
"""

from sqlalchemy.orm import Session

from ..models import InAppNotification


def create_customer_job_status_notification(
    db: Session,
    job,
    new_status: str,
) -> InAppNotification | None:
    """Compatibility shim; status updates are dispatched after commit by the model listener."""
    return None
