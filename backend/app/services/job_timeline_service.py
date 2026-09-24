"""
Authoritative job timeline aggregation.

This service reads existing persisted FieldOps sources and combines them into
one chronological, read-only event stream.

Sources:
- Job lifecycle timestamps
- AuditEvent
- EnterpriseAuditLog
- AssignmentOverride
- JobClosure
- SLAEscalation

No new lifecycle rules are introduced here.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import (
    AssignmentOverride,
    AuditEvent,
    EnterpriseAuditLog,
    Job,
    SLAEscalation,
    Technician,
)
from app.models.job_closure import JobClosure


# These actions already have canonical timestamps on Job or dedicated
# completion/cancellation/closure records. We do not duplicate them from the
# enterprise audit stream.
CANONICAL_ENTERPRISE_ACTIONS = {
    "JOB_CREATED",
    "JOB_ASSIGNED",
    "JOB_COMPLETED",
    "JOB_CANCELLED",
    "JOB_CLOSED",
}


# Enterprise audit actions that have useful job-timeline meaning.
ENTERPRISE_ACTION_MAP: dict[str, dict[str, str]] = {
    "JOB_REASSIGNED": {
        "event_type": "JOB_REASSIGNED",
        "event_category": "ASSIGNMENT",
        "title": "Technician Reassigned",
    },
    "JOB_REASSIGNED_FROM_DECLINED": {
        "event_type": "JOB_REASSIGNED_FROM_DECLINED",
        "event_category": "ASSIGNMENT",
        "title": "Job Reassigned After Decline",
    },
    "JOB_ACCEPTED": {
        "event_type": "JOB_ACCEPTED",
        "event_category": "STATUS",
        "title": "Job Accepted",
    },
    "JOB_REJECTED": {
        "event_type": "JOB_REJECTED",
        "event_category": "STATUS",
        "title": "Job Rejected",
    },
    "JOB_REJECTED_BY_TECHNICIAN": {
        "event_type": "JOB_REJECTED_BY_TECHNICIAN",
        "event_category": "STATUS",
        "title": "Technician Rejected Job",
    },
    "JOB_STARTED": {
        "event_type": "JOB_STARTED",
        "event_category": "STATUS",
        "title": "Job Started",
    },
    "JOB_PAUSED": {
        "event_type": "JOB_PAUSED",
        "event_category": "STATUS",
        "title": "Job Paused",
    },
    "JOB_RESUMED": {
        "event_type": "JOB_RESUMED",
        "event_category": "STATUS",
        "title": "Job Resumed",
    },
    "JOB_UPDATED": {
        "event_type": "JOB_UPDATED",
        "event_category": "OTHER",
        "title": "Job Updated",
    },
}


# Canonical lifecycle timestamps already stored on Job.
LIFECYCLE_TIMESTAMP_FIELDS = (
    ("created_at", "JOB_CREATED", "CREATION", "Job Created"),
    ("assigned_at", "JOB_ASSIGNED", "ASSIGNMENT", "Technician Assigned"),
    ("en_route_at", "JOB_EN_ROUTE", "STATUS", "Technician En Route"),
    ("on_site_at", "JOB_IN_PROGRESS", "STATUS", "Job In Progress"),
    ("completed_at", "JOB_COMPLETED", "COMPLETION", "Job Completed"),
    ("cancelled_at", "JOB_CANCELLED", "STATUS", "Job Cancelled"),
    ("closed_at", "JOB_CLOSED", "COMPLETION", "Job Closed"),
    (
        "rejected_at",
        "JOB_REJECTED_BY_TECHNICIAN",
        "STATUS",
        "Job Rejected by Technician",
    ),
)


def _utc(value: datetime | None) -> datetime | None:
    """Normalize timestamps to timezone-aware UTC for stable sorting."""
    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    """Serialize a datetime while preserving its actual timestamp."""
    normalized = _utc(value)
    return normalized.isoformat() if normalized else None


def _role_label(value: Any, fallback: str = "SYSTEM") -> str:
    """Normalize role values without exposing internal identifiers."""
    if value is None:
        return fallback

    raw = getattr(value, "value", value)
    text = str(raw).strip()

    return text.upper() if text else fallback


def _safe_actor_name(
    value: Any,
    fallback: str = "System",
) -> str:
    """
    Return a user-facing actor label.

    Internal actor IDs are never returned as actor names.
    """
    text = str(value).strip() if value is not None else ""

    return text or fallback


def _resolve_technician(
    db: Session,
    tenant_id: str,
    identifier: Any,
    cache: dict[str, Technician | None],
) -> Technician | None:
    """
    Resolve technician identity only inside the job tenant.

    Supports both:
    - Technician.tech_id
    - Technician.technician_id
    """

    if identifier is None:
        return None

    key = str(identifier)

    if key in cache:
        return cache[key]

    numeric_condition = (
        Technician.technician_id == int(key)
        if key.isdigit()
        else False
    )

    technician = (
        db.query(Technician)
        .filter(
            Technician.tenant_id == tenant_id,
            or_(
                Technician.tech_id == key,
                numeric_condition,
            ),
        )
        .first()
    )

    cache[key] = technician

    return technician


def _build_event(
    *,
    event_id: str,
    job_id: int,
    event_type: str,
    event_category: str,
    title: str,
    description: str,
    timestamp: datetime,
    from_status: str | None = None,
    to_status: str | None = None,
    actor_name: str = "System",
    actor_role: str = "SYSTEM",
    source: str,
) -> dict[str, Any]:
    """
    Build the canonical frontend timeline event shape.

    Only timeline-safe fields are returned.
    """

    return {
        "id": event_id,
        "job_id": job_id,
        "event_type": event_type,
        "event_category": event_category,
        "title": title,
        "description": description,
        "timestamp": _iso(timestamp),
        "from_status": from_status,
        "to_status": to_status,
        "actor_name": _safe_actor_name(actor_name),
        "actor_role": _role_label(actor_role),
        "source": source,
        "is_current": False,
    }


def _job_lifecycle_events(
    db: Session,
    job: Job,
) -> list[dict[str, Any]]:
    """
    Build canonical events from authoritative Job lifecycle timestamps.
    """

    events: list[dict[str, Any]] = []

    technician = getattr(job, "technician", None)

    technician_name = (
        getattr(technician, "technician_name", None)
        or "Technician"
    )

    technician_cache: dict[str, Technician | None] = {}

    previous_status: str | None = None

    for (
        field_name,
        event_type,
        event_category,
        title,
    ) in LIFECYCLE_TIMESTAMP_FIELDS:

        timestamp = getattr(job, field_name, None)

        if timestamp is None:
            continue

        if event_type == "JOB_CREATED":
            actor_name = "System"
            actor_role = "SYSTEM"

            from_status = None
            to_status = "CREATED"

            description = "Job record was created."

        elif event_type == "JOB_ASSIGNED":
            actor_name = "Staff"
            actor_role = "STAFF"

            from_status = previous_status or "CREATED"
            to_status = "ASSIGNED"

            description = (
                f"Job was assigned to {technician_name}."
            )

        elif event_type == "JOB_EN_ROUTE":
            actor = _resolve_technician(
                db,
                str(job.tenant_id),
                getattr(job, "en_route_by", None),
                technician_cache,
            )

            actor_name = (
                getattr(actor, "technician_name", None)
                or "Technician"
            )
            actor_role = "TECHNICIAN"

            from_status = previous_status or "ASSIGNED"
            to_status = "EN_ROUTE"

            description = (
                "Technician started travel to the job site."
            )

        elif event_type == "JOB_IN_PROGRESS":
            actor = _resolve_technician(
                db,
                str(job.tenant_id),
                getattr(job, "on_site_by", None),
                technician_cache,
            )

            actor_name = (
                getattr(actor, "technician_name", None)
                or "Technician"
            )
            actor_role = "TECHNICIAN"

            from_status = previous_status or "EN_ROUTE"
            to_status = "IN_PROGRESS"

            description = "Technician arrived at the job site and work is in progress."

        elif event_type == "JOB_COMPLETED":
            actor = _resolve_technician(
                db,
                str(job.tenant_id),
                getattr(job, "completed_by", None),
                technician_cache,
            )

            actor_name = (
                getattr(actor, "technician_name", None)
                or "Technician"
            )
            actor_role = "TECHNICIAN"

            from_status = previous_status or "IN_PROGRESS"
            to_status = "COMPLETED"

            description = "Job completion was recorded."

        elif event_type == "JOB_CANCELLED":
            actor = getattr(job, "cancelled_by", None)

            actor_name = "Staff"
            actor_role = "STAFF"

            from_status = previous_status
            to_status = "CANCELLED"

            reason = getattr(
                job,
                "cancellation_reason",
                None,
            )

            description = "Job was cancelled."

            if reason:
                description = (
                    "Job was cancelled. "
                    f"Reason: {str(reason).strip()}"
                )

        elif event_type == "JOB_CLOSED":
            actor_name = "Staff"
            actor_role = "STAFF"

            from_status = previous_status or "COMPLETED"
            to_status = "CLOSED"

            reason = getattr(
                job,
                "closure_reason",
                None,
            )

            description = "Job was closed."

            if reason:
                description = (
                    "Job was closed. "
                    f"Reason: {str(reason).strip()}"
                )

        elif event_type == "JOB_REJECTED_BY_TECHNICIAN":
            actor = _resolve_technician(
                db,
                str(job.tenant_id),
                getattr(
                    job,
                    "rejected_by_tech_id",
                    None,
                ),
                technician_cache,
            )

            actor_name = (
                getattr(actor, "technician_name", None)
                or "Technician"
            )
            actor_role = "TECHNICIAN"

            from_status = previous_status or "ASSIGNED"
            to_status = "REJECTED_BY_TECHNICIAN"

            reason = getattr(
                job,
                "rejection_reason",
                None,
            )

            description = (
                "Technician rejected the assigned job."
            )

            if reason:
                description = (
                    "Technician rejected the assigned job. "
                    f"Reason: {str(reason).strip()}"
                )

        else:
            continue

        events.append(
            _build_event(
                event_id=(
                    f"job:{job.id}:{event_type}"
                ),
                job_id=job.id,
                event_type=event_type,
                event_category=event_category,
                title=title,
                description=description,
                timestamp=timestamp,
                from_status=from_status,
                to_status=to_status,
                actor_name=actor_name,
                actor_role=actor_role,
                source="job",
            )
        )

        if to_status:
            previous_status = to_status

    return events


def _audit_event_items(
    db: Session,
    job: Job,
) -> list[dict[str, Any]]:
    """
    Read the existing AuditEvent table.

    This includes status-transition and other job audit events without exposing
    raw audit details.
    """

    rows = (
        db.query(AuditEvent)
        .filter(
            AuditEvent.tenant_id == job.tenant_id,
            AuditEvent.job_id == str(job.id),
        )
        .order_by(
            AuditEvent.created_at.asc(),
            AuditEvent.id.asc(),
        )
        .all()
    )

    events: list[dict[str, Any]] = []

    technician_cache: dict[str, Technician | None] = {}

    for row in rows:
        timestamp = row.timestamp or row.created_at

        if timestamp is None:
            continue

        event_type = str(
            row.event_type or "AUDIT_EVENT"
        ).upper()

        # Completion already has canonical Job.completed_at.
        if event_type == "JOB_COMPLETED":
            continue

        if event_type == "JOB_STATUS_TRANSITION":
            title = "Job Status Updated"
            category = "STATUS"

            description = (
                "Job status changed from "
                f"{row.old_status or 'UNKNOWN'} "
                "to "
                f"{row.new_status or 'UNKNOWN'}."
            )

            from_status = row.old_status
            to_status = row.new_status

        elif event_type.startswith("SLA_"):
            title = "SLA Event"
            category = "OTHER"

            description = (
                row.reason
                or f"Recorded SLA event: {event_type}."
            )

            from_status = row.old_status
            to_status = row.new_status

        else:
            title = event_type.replace(
                "_",
                " ",
            ).title()

            category = "OTHER"

            description = (
                row.reason
                or f"Recorded audit event: {event_type}."
            )

            from_status = row.old_status
            to_status = row.new_status

        actor = _resolve_technician(
            db,
            str(job.tenant_id),
            row.tech_id,
            technician_cache,
        )

        if actor:
            actor_name = actor.technician_name
            actor_role = "TECHNICIAN"

        elif row.actor_id:
            actor_name = "Staff"
            actor_role = "STAFF"

        else:
            actor_name = "System"
            actor_role = "SYSTEM"

        events.append(
            _build_event(
                event_id=f"audit:{row.id}",
                job_id=job.id,
                event_type=event_type,
                event_category=category,
                title=title,
                description=description,
                timestamp=timestamp,
                from_status=from_status,
                to_status=to_status,
                actor_name=actor_name,
                actor_role=actor_role,
                source="audit_event",
            )
        )

    return events


def _enterprise_audit_items(
    db: Session,
    job: Job,
) -> list[dict[str, Any]]:
    """
    Read the immutable EnterpriseAuditLog for this job.

    Sensitive fields such as:
    - user_id
    - user_email
    - old_value
    - new_value
    - details
    - IP address
    are intentionally not returned.
    """

    rows = (
        db.query(EnterpriseAuditLog)
        .filter(
            EnterpriseAuditLog.tenant_id == job.tenant_id,
            EnterpriseAuditLog.entity_type == "job",
            EnterpriseAuditLog.entity_id == str(job.id),
        )
        .order_by(
            EnterpriseAuditLog.timestamp.asc(),
            EnterpriseAuditLog.id.asc(),
        )
        .all()
    )

    events: list[dict[str, Any]] = []

    for row in rows:
        action = str(
            row.action or "AUDIT_EVENT"
        ).upper()

        timestamp = row.timestamp

        if timestamp is None:
            continue

        # These have canonical Job-level events already.
        if action in CANONICAL_ENTERPRISE_ACTIONS:
            continue

        mapping = ENTERPRISE_ACTION_MAP.get(action)

        if mapping:
            event_type = mapping["event_type"]
            category = mapping["event_category"]
            title = mapping["title"]
        else:
            event_type = action
            category = "OTHER"
            title = action.replace(
                "_",
                " ",
            ).title()

        old_value = (
            row.old_value
            if isinstance(row.old_value, dict)
            else {}
        )

        new_value = (
            row.new_value
            if isinstance(row.new_value, dict)
            else {}
        )

        from_status = old_value.get("status")
        to_status = new_value.get("status")

        if action == "JOB_ACCEPTED":
            to_status = to_status or "ACCEPTED"

            description = (
                "Assigned technician accepted the job."
            )

        elif action == "JOB_STARTED":
            to_status = to_status or "EN_ROUTE"

            description = (
                "Technician started the job journey."
            )

        elif action == "JOB_PAUSED":
            to_status = to_status or "PAUSED"

            description = "Job was paused."

        elif action == "JOB_RESUMED":
            to_status = to_status or "IN_PROGRESS"

            description = "Job was resumed."

        elif action in {
            "JOB_REJECTED",
            "JOB_REJECTED_BY_TECHNICIAN",
        }:
            to_status = (
                to_status
                or "REJECTED_BY_TECHNICIAN"
            )

            description = (
                "Assigned technician rejected the job."
            )

        elif action in {
            "JOB_REASSIGNED",
            "JOB_REASSIGNED_FROM_DECLINED",
        }:
            description = (
                "Technician assignment was changed."
            )

        elif action == "JOB_UPDATED":
            description = (
                "Job details were updated."
            )

        else:
            description = (
                f"Recorded audit action: {action}."
            )

        actor_role = _role_label(
            row.role,
            "STAFF",
        )

        actor_name = (
            "Technician"
            if actor_role == "TECHNICIAN"
            else "Staff"
        )

        events.append(
            _build_event(
                event_id=f"enterprise:{row.id}",
                job_id=job.id,
                event_type=event_type,
                event_category=category,
                title=title,
                description=description,
                timestamp=timestamp,
                from_status=from_status,
                to_status=to_status,
                actor_name=actor_name,
                actor_role=actor_role,
                source="enterprise_audit",
            )
        )

    return events


def _assignment_override_items(
    db: Session,
    job: Job,
) -> list[dict[str, Any]]:
    """
    Include the existing assignment override records.
    """

    rows = (
        db.query(AssignmentOverride)
        .filter(
            AssignmentOverride.tenant_id == job.tenant_id,
            AssignmentOverride.job_id == job.id,
        )
        .order_by(
            AssignmentOverride.created_at.asc(),
            AssignmentOverride.id.asc(),
        )
        .all()
    )

    events: list[dict[str, Any]] = []

    for row in rows:
        if row.created_at is None:
            continue

        description = (
            "Assignment changed from "
            f"{row.previous_technician_name or 'unassigned'} "
            "to "
            f"{row.new_technician_name}."
        )

        events.append(
            _build_event(
                event_id=(
                    f"assignment-override:{row.id}"
                ),
                job_id=job.id,
                event_type="ASSIGNMENT_OVERRIDE",
                event_category="ASSIGNMENT",
                title="Assignment Override",
                description=description,
                timestamp=row.created_at,
                actor_name=row.actor_name,
                actor_role=row.actor_role,
                source="assignment_override",
            )
        )

    return events


def _closure_items(
    db: Session,
    job: Job,
) -> list[dict[str, Any]]:
    """
    Include the existing JobClosure record as a separate completion-related
    event.

    The actual completion timestamp remains Job.completed_at.
    """

    rows = (
        db.query(JobClosure)
        .filter(
            JobClosure.tenant_id == job.tenant_id,
            JobClosure.job_id == job.id,
        )
        .order_by(
            JobClosure.created_at.asc(),
            JobClosure.id.asc(),
        )
        .all()
    )

    events: list[dict[str, Any]] = []

    for row in rows:
        if row.created_at is None:
            continue

        events.append(
            _build_event(
                event_id=f"closure:{row.id}",
                job_id=job.id,
                event_type="CLOSURE_RECORDED",
                event_category="COMPLETION",
                title="Completion Record Added",
                description=(
                    "Job completion details were recorded."
                ),
                timestamp=row.created_at,
                from_status="COMPLETED",
                to_status="COMPLETED",
                actor_name="Technician",
                actor_role="TECHNICIAN",
                source="job_closure",
            )
        )

    return events


def _sla_items(
    db: Session,
    job: Job,
) -> list[dict[str, Any]]:
    """
    Include existing SLA escalation milestones when available.
    """

    rows = (
        db.query(SLAEscalation)
        .filter(
            SLAEscalation.tenant_id == job.tenant_id,
            SLAEscalation.job_id == job.id,
        )
        .order_by(
            SLAEscalation.created_at.asc(),
            SLAEscalation.id.asc(),
        )
        .all()
    )

    events: list[dict[str, Any]] = []

    for row in rows:

        if row.manager_notified_at is not None:
            events.append(
                _build_event(
                    event_id=(
                        f"sla:{row.id}:manager-notified"
                    ),
                    job_id=job.id,
                    event_type="SLA_MANAGER_NOTIFIED",
                    event_category="OTHER",
                    title="SLA Escalation",
                    description=(
                        "SLA escalation notified the manager."
                    ),
                    timestamp=row.manager_notified_at,
                    actor_name="System",
                    actor_role="SYSTEM",
                    source="sla_escalation",
                )
            )

        if row.manager_responded_at is not None:
            events.append(
                _build_event(
                    event_id=(
                        f"sla:{row.id}:manager-responded"
                    ),
                    job_id=job.id,
                    event_type="SLA_MANAGER_RESPONDED",
                    event_category="OTHER",
                    title="SLA Escalation Response",
                    description=(
                        "Manager response to SLA escalation "
                        "was recorded."
                    ),
                    timestamp=row.manager_responded_at,
                    actor_name="Staff",
                    actor_role="STAFF",
                    source="sla_escalation",
                )
            )

        if row.cto_notified_at is not None:
            events.append(
                _build_event(
                    event_id=(
                        f"sla:{row.id}:cto-notified"
                    ),
                    job_id=job.id,
                    event_type="SLA_CTO_NOTIFIED",
                    event_category="OTHER",
                    title="SLA Escalation",
                    description=(
                        "SLA escalation notified the CTO."
                    ),
                    timestamp=row.cto_notified_at,
                    actor_name="System",
                    actor_role="SYSTEM",
                    source="sla_escalation",
                )
            )

    return events


def build_job_timeline(
    db: Session,
    job: Job,
) -> list[dict[str, Any]]:
    """
    Build the complete authoritative timeline for one already
    tenant-authorized Job.
    """

    events: list[dict[str, Any]] = []

    # 1. Canonical Job lifecycle timestamps.
    events.extend(
        _job_lifecycle_events(
            db,
            job,
        )
    )

    # 2. Existing domain audit events.
    events.extend(
        _audit_event_items(
            db,
            job,
        )
    )

    # 3. Immutable enterprise audit events.
    events.extend(
        _enterprise_audit_items(
            db,
            job,
        )
    )

    # 4. Existing assignment override history.
    events.extend(
        _assignment_override_items(
            db,
            job,
        )
    )

    # 5. Existing completion/closure record.
    events.extend(
        _closure_items(
            db,
            job,
        )
    )

    # 6. Existing SLA escalation milestones.
    events.extend(
        _sla_items(
            db,
            job,
        )
    )

    # Chronological ordering.
    def sort_key(event: dict[str, Any]):
        raw_timestamp = event.get("timestamp")

        if not raw_timestamp:
            timestamp = datetime.max.replace(
                tzinfo=timezone.utc,
            )
        else:
            timestamp = _utc(
                datetime.fromisoformat(
                    raw_timestamp,
                )
            )

        return (
            timestamp,
            str(event.get("id", "")),
        )

    events.sort(key=sort_key)

    # Mark the event(s) representing the current persisted state.
    current_status = str(
        job.status or ""
    ).upper()

    for event in events:
        to_status = event.get("to_status")

        event["is_current"] = bool(
            to_status
            and str(to_status).upper() == current_status
            and event.get("event_category")
            in {
                "STATUS",
                "ASSIGNMENT",
                "COMPLETION",
            }
        )

    return events