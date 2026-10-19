"""Job events, status-transition mapping, card steps and recipient rules."""
from enum import Enum

# Channels
IN, SMS, EMAIL = "in_app", "sms", "email"


class JobEvent(str, Enum):
    JOB_CREATED = "job_created"
    TECHNICIAN_ASSIGNED = "technician_assigned"
    TECHNICIAN_ACCEPTED = "technician_accepted"
    TECHNICIAN_REJECTED = "technician_rejected"   # also used when a job goes back to CREATED
    DELAYED = "delayed"                           # trip paused / job moved back to ASSIGNED
    EN_ROUTE = "en_route"
    ON_SITE = "on_site"
    SERVICE_STARTED = "service_started"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    CLOSED = "closed"
    INVOICE_READY = "invoice_ready"


# ---------------------------------------------------------------------------
# Status transition -> event
#
# The event depends on the (old, new) pair, not on the new status alone,
# because the job state machine allows backward moves.
#
# The status mapping sends a customer update when the technician is assigned;
# acceptance is a separate update from the accept endpoint.
# Not mapped on purpose (no notification):
#   *        -> CLOSED     from CREATED / ASSIGNED / EN_ROUTE / ON_SITE (housekeeping)
#   JOB_CREATED            sent from the job-creation endpoint (INSERT, not an update).
# ---------------------------------------------------------------------------

TRANSITION_TO_EVENT = {
    ("CREATED", "ASSIGNED"): JobEvent.TECHNICIAN_ASSIGNED,
    ("QUEUED", "ASSIGNED"): JobEvent.TECHNICIAN_ASSIGNED,
    ("ACTIVE", "ASSIGNED"): JobEvent.TECHNICIAN_ASSIGNED,
    # Technician acceptance/rejection
    ("ASSIGNED", "ACCEPTED"): JobEvent.TECHNICIAN_ACCEPTED,
    ("ASSIGNED", "REJECTED_BY_TECHNICIAN"): JobEvent.TECHNICIAN_REJECTED,
    ("ASSIGNED", "QUEUED"): JobEvent.TECHNICIAN_REJECTED,

    # Forward
    ("ASSIGNED", "EN_ROUTE"): JobEvent.EN_ROUTE,
    ("ACCEPTED", "EN_ROUTE"): JobEvent.EN_ROUTE,
    ("EN_ROUTE", "ON_SITE"): JobEvent.ON_SITE,
    ("ON_SITE", "COMPLETED"): JobEvent.COMPLETED,

    # Backward / redispatch
    ("ASSIGNED", "CREATED"): JobEvent.TECHNICIAN_REJECTED,
    ("EN_ROUTE", "ASSIGNED"): JobEvent.DELAYED,
    ("ON_SITE", "ASSIGNED"): JobEvent.DELAYED,
    ("ON_SITE", "EN_ROUTE"): JobEvent.EN_ROUTE,

    # Cancelled
    ("CREATED", "CANCELLED"): JobEvent.CANCELLED,
    ("ASSIGNED", "CANCELLED"): JobEvent.CANCELLED,
    ("EN_ROUTE", "CANCELLED"): JobEvent.CANCELLED,
    ("ON_SITE", "CANCELLED"): JobEvent.CANCELLED,

    # Closed
    ("COMPLETED", "CLOSED"): JobEvent.CLOSED,
    ("CANCELLED", "CLOSED"): JobEvent.CLOSED,
}



def _norm(status) -> str:
    s = str(getattr(status, "value", status)).upper().strip()
    if s in {"CANCELED", "CANCELLED"}:
        return "CANCELLED"
    # The technician portal currently persists IN_PROGRESS when marking
    # arrival; normalize it to the lifecycle's ON_SITE stage for notifications.
    if s == "IN_PROGRESS":
        return "ON_SITE"
    return s


def event_for_transition(old_status, new_status) -> JobEvent | None:
    """Return the JobEvent for a status change, or None if nothing should be sent."""
    raw_old = str(getattr(old_status, "value", old_status)).upper().strip()
    raw_new = str(getattr(new_status, "value", new_status)).upper().strip()
    if raw_old == "EN_ROUTE" and raw_new == "IN_PROGRESS":
        return JobEvent.SERVICE_STARTED
    return TRANSITION_TO_EVENT.get((_norm(old_status), _norm(new_status)))


# ---------------------------------------------------------------------------
# Live card: progress stepper (5 steps, indexes 0-4; -1 means cancelled)
# ---------------------------------------------------------------------------
STEPS = ["Booked", "Accepted", "On the way", "Arrived", "Done"]

EVENT_STEP = {
    JobEvent.JOB_CREATED: 0,
    JobEvent.TECHNICIAN_ASSIGNED: 1,
    JobEvent.TECHNICIAN_REJECTED: 0,
    JobEvent.TECHNICIAN_ACCEPTED: 1,
    JobEvent.DELAYED: 1,
    JobEvent.EN_ROUTE: 2,
    JobEvent.ON_SITE: 3,
    JobEvent.SERVICE_STARTED: 3,
    JobEvent.COMPLETED: 4,
    JobEvent.CLOSED: 4,
    JobEvent.CANCELLED: -1,
    JobEvent.INVOICE_READY: 4,
}


# ---------------------------------------------------------------------------
# Who gets what.  role -> channels
#
# "technician_org_admin" only applies when the technician's organization differs
# from the job's organization (checked in recipients.py).
# ---------------------------------------------------------------------------
RECIPIENT_RULES = {
    JobEvent.JOB_CREATED: {
        "customer": [IN, SMS, EMAIL],
        "org_admin": [IN, EMAIL],
        "super_admin": [IN],
    },
    JobEvent.TECHNICIAN_ASSIGNED: {
        "customer": [IN, EMAIL],
        "org_admin": [IN, EMAIL],
        "technician_org_admin": [IN, EMAIL],
    },
    JobEvent.TECHNICIAN_ACCEPTED: {
        "customer": [IN, SMS, EMAIL],
        "org_admin": [IN, EMAIL],
        "technician_org_admin": [IN, EMAIL],
        "super_admin": [IN],
    },
    JobEvent.TECHNICIAN_REJECTED: {
        "customer": [IN],
        "org_admin": [IN, EMAIL],
        "technician_org_admin": [IN, EMAIL],
        "super_admin": [IN],
    },
    JobEvent.DELAYED: {
        "customer": [IN],
        "org_admin": [IN],
        "super_admin": [IN],
    },
    JobEvent.EN_ROUTE: {
        "customer": [IN, SMS, EMAIL],
        "org_admin": [IN],
        "super_admin": [IN],
    },
    JobEvent.ON_SITE: {
        "customer": [IN, SMS, EMAIL],
        "org_admin": [IN],
        "super_admin": [IN],
    },
    JobEvent.SERVICE_STARTED: {
        "customer": [IN, EMAIL],
        "org_admin": [IN],
    },
    JobEvent.COMPLETED: {
        "customer": [IN, SMS, EMAIL],
        "org_admin": [IN, EMAIL],
        "technician_org_admin": [IN, EMAIL],
        "super_admin": [IN],
    },
    JobEvent.CANCELLED: {
        "customer": [IN, SMS, EMAIL],
        "technician": [IN],
        "org_admin": [IN, EMAIL],
        "technician_org_admin": [IN, EMAIL],
        "super_admin": [IN],
    },
    JobEvent.CLOSED: {
        "org_admin": [IN],
        "super_admin": [IN],
    },
    JobEvent.INVOICE_READY: {
        "customer": [IN, EMAIL],
        "org_admin": [IN],
    },
}
