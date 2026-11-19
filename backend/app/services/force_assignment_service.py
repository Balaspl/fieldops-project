
"""
Force assignment fallback for FieldOps.

This service is called only after normal broadcast offers are terminal.
It does not replace accept_broadcast_offer().

Rules:
- Candidate identities are tenant-scoped.
- Explicitly rejected technicians are excluded.
- Timed-out technicians may be reconsidered.
- Current GPS must be fresh.
- OFFLINE technicians can be considered when tenant policy allows it.
- Appointment duration defaults to 3 hours.
- Travel feasibility uses a configurable average speed estimate.
"""

from __future__ import annotations

import logging
import math
import uuid

from datetime import datetime, timedelta, timezone, time
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, or_

from app import models
from app.database import SessionLocal


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

DEFAULT_APPOINTMENT_DURATION_HOURS = 3
DEFAULT_GPS_FRESHNESS_SECONDS = 180

# This is an estimate, not a road-routing ETA.
AVERAGE_TRAVEL_SPEED_KMH = 25
TRAVEL_BUFFER_MINUTES = 15

ACTIVE_JOB_STATUSES = {
    "ASSIGNED",
    "ACCEPTED",
    "EN_ROUTE",
    "ON_SITE",
    "IN_PROGRESS",
    "ACTIVE",
}

NON_ACTIVE_JOB_STATUSES = {
    "COMPLETED",
    "CLOSED",
    "CANCELLED",
    "CANCELED",
    "REJECTED",
}


# ---------------------------------------------------------------------
# Basic helpers
# ---------------------------------------------------------------------

def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def _normalise_identity(value: Any) -> tuple[str, int] | None:
    if not isinstance(value, dict):
        return None

    tenant_id = value.get("tenant_id") or value.get("organization_id")
    technician_id = value.get("technician_id")

    if tenant_id is None or technician_id is None:
        return None

    try:
        return str(tenant_id), int(technician_id)
    except (TypeError, ValueError):
        return None


def _identity_payload(identity: tuple[str, int]) -> dict[str, Any]:
    return {
        "tenant_id": identity[0],
        "technician_id": identity[1],
    }


def _distance_km(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    """Haversine straight-line distance. Not road distance."""

    earth_radius_km = 6371.0

    lat_a = math.radians(latitude_a)
    lat_b = math.radians(latitude_b)

    delta_lat = math.radians(latitude_b - latitude_a)
    delta_lon = math.radians(longitude_b - longitude_a)

    value = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat_a)
        * math.cos(lat_b)
        * math.sin(delta_lon / 2) ** 2
    )

    return earth_radius_km * 2 * math.atan2(
        math.sqrt(value),
        math.sqrt(max(0.0, 1.0 - value)),
    )


def _estimated_travel_minutes(distance_km: float) -> float:
    """Approximate travel duration with a safety buffer."""

    travel_minutes = (
        distance_km / AVERAGE_TRAVEL_SPEED_KMH
    ) * 60

    return travel_minutes + TRAVEL_BUFFER_MINUTES


def _get_timezone(timezone_name: str | None) -> ZoneInfo:
    if timezone_name:
        try:
            return ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            logger.warning(
                "Invalid appointment timezone %s; using Asia/Kolkata",
                timezone_name,
            )

    return ZoneInfo("Asia/Kolkata")


def _appointment_window(job: Any) -> tuple[datetime, datetime] | None:
    """
    Return the appointment start and end.

    The current Job model has preferred_service_date,
    preferred_service_time and preferred_service_timezone.

    Until a service-duration field exists, the duration is three hours.
    """

    service_date = getattr(job, "preferred_service_date", None)
    service_time = getattr(job, "preferred_service_time", None)

    if service_date is None or service_time is None:
        return None

    if isinstance(service_date, datetime):
        service_date = service_date.date()

    if not isinstance(service_time, time):
        return None

    timezone_name = getattr(
        job,
        "preferred_service_timezone",
        None,
    )

    tz = _get_timezone(timezone_name)

    start = datetime.combine(
        service_date,
        service_time,
    ).replace(tzinfo=tz)

    end = start + timedelta(
        hours=DEFAULT_APPOINTMENT_DURATION_HOURS
    )

    return start, end


# ---------------------------------------------------------------------
# Organization policy and GPS validation
# ---------------------------------------------------------------------

def _get_technician_policy(db, technician) -> dict[str, Any]:
    organization = (
        db.query(models.Organization)
        .filter(
            models.Organization.id == str(technician.tenant_id)
        )
        .first()
    )

    settings = getattr(organization, "settings", None) or {}

    field_operations = settings.get("field_operations") or {}

    return field_operations


def _get_fresh_gps(technician, field_operations: dict) -> dict | None:
    """
    Use Technician.latitude, longitude and last_ping.

    These fields are updated by POST /api/v1/gps/availability.
    Do not use GPSPing history here because that endpoint represents
    job tracking rather than pre-assignment availability.
    """

    latitude = getattr(technician, "latitude", None)
    longitude = getattr(technician, "longitude", None)
    last_ping = _as_utc(getattr(technician, "last_ping", None))

    if latitude is None or longitude is None or last_ping is None:
        return None

    try:
        latitude = float(latitude)
        longitude = float(longitude)
    except (TypeError, ValueError):
        return None

    if not (
        math.isfinite(latitude)
        and math.isfinite(longitude)
        and -90 <= latitude <= 90
        and -180 <= longitude <= 180
    ):
        return None

    freshness_seconds = int(
        field_operations.get(
            "location_freshness_seconds",
            DEFAULT_GPS_FRESHNESS_SECONDS,
        )
    )

    now = datetime.now(timezone.utc)
    age_seconds = (now - last_ping).total_seconds()

    if age_seconds < -30 or age_seconds > freshness_seconds:
        return None

    return {
        "latitude": latitude,
        "longitude": longitude,
        "last_ping": last_ping,
        "age_seconds": age_seconds,
    }


# ---------------------------------------------------------------------
# Skills and workload
# ---------------------------------------------------------------------

def _has_required_skill(job, technician) -> bool:
    required_skill = (
        getattr(job, "required_skill", None) or ""
    ).strip().lower()

    if not required_skill:
        return True

    technician_skill = (
        getattr(technician, "technician_skill", None) or ""
    ).lower()

    certifications = (
        getattr(technician, "certifications_data", None) or {}
    )

    searchable_values = [
        technician_skill,
        str(certifications),
    ]

    searchable_text = " ".join(searchable_values)

    required_parts = [
        part.strip()
        for part in required_skill.replace(";", ",").split(",")
        if part.strip()
    ]

    return all(
        required_part in searchable_text
        for required_part in required_parts
    )


def _has_workload_capacity(technician) -> bool:
    current_jobs = max(
        0,
        int(getattr(technician, "current_jobs", 0) or 0),
    )

    max_jobs = int(
        getattr(technician, "max_jobs", 5) or 5
    )

    return current_jobs < max_jobs


# ---------------------------------------------------------------------
# Appointment and travel feasibility
# ---------------------------------------------------------------------

def _check_existing_appointments(
    db,
    job,
    technician,
    target_start: datetime,
    target_end: datetime,
) -> tuple[bool, str]:
    """
    Check the technician's already assigned jobs.

    Checks:
    1. Appointment overlap.
    2. Travel time from the previous appointment.
    3. Travel time to the next appointment.

    Existing assigned jobs are found by the global technician PK.
    """

    existing_jobs = (
        db.query(models.Job)
        .filter(
            models.Job.assigned_technician_id
            == technician.technician_id,
            models.Job.id != job.id,
            func.upper(models.Job.status).notin_(
                list(NON_ACTIVE_JOB_STATUSES)
            ),
        )
        .all()
    )

    previous_jobs = []
    next_jobs = []

    for existing_job in existing_jobs:
        existing_status = str(
            getattr(existing_job, "status", "") or ""
        ).strip().upper()

        if existing_status in NON_ACTIVE_JOB_STATUSES:
            continue

        existing_window = _appointment_window(existing_job)

        # An active assigned job with no known appointment window
        # is treated conservatively.
        if existing_window is None:
            if existing_status in ACTIVE_JOB_STATUSES:
                return False, (
                    f"Existing active job {existing_job.id} "
                    "has no appointment time"
                )
            continue

        existing_start, existing_end = existing_window

        # Direct overlap.
        if (
            existing_start < target_end
            and existing_end > target_start
        ):
            return False, (
                f"Appointment overlaps with job {existing_job.id}"
            )

        if existing_end <= target_start:
            previous_jobs.append(
                (existing_job, existing_start, existing_end)
            )

        elif existing_start >= target_end:
            next_jobs.append(
                (existing_job, existing_start, existing_end)
            )

    # Check the closest preceding appointment.
    if previous_jobs:
        previous_job, _, previous_end = max(
            previous_jobs,
            key=lambda item: item[2],
        )

        previous_lat = getattr(previous_job, "site_latitude", None)
        previous_lon = getattr(previous_job, "site_longitude", None)

        target_lat = getattr(job, "site_latitude", None)
        target_lon = getattr(job, "site_longitude", None)

        available_minutes = (
            target_start - previous_end
        ).total_seconds() / 60

        if (
            previous_lat is not None
            and previous_lon is not None
            and target_lat is not None
            and target_lon is not None
        ):
            distance = _distance_km(
                float(previous_lat),
                float(previous_lon),
                float(target_lat),
                float(target_lon),
            )

            required_minutes = _estimated_travel_minutes(distance)

            if available_minutes < required_minutes:
                return False, (
                    f"Insufficient travel gap after job "
                    f"{previous_job.id}"
                )

        elif available_minutes < 60:
            return False, (
                f"Cannot verify travel gap after job "
                f"{previous_job.id}"
            )

    # Check the closest following appointment.
    if next_jobs:
        next_job, next_start, _ = min(
            next_jobs,
            key=lambda item: item[1],
        )

        target_lat = getattr(job, "site_latitude", None)
        target_lon = getattr(job, "site_longitude", None)

        next_lat = getattr(next_job, "site_latitude", None)
        next_lon = getattr(next_job, "site_longitude", None)

        available_minutes = (
            next_start - target_end
        ).total_seconds() / 60

        if (
            target_lat is not None
            and target_lon is not None
            and next_lat is not None
            and next_lon is not None
        ):
            distance = _distance_km(
                float(target_lat),
                float(target_lon),
                float(next_lat),
                float(next_lon),
            )

            required_minutes = _estimated_travel_minutes(distance)

            if available_minutes < required_minutes:
                return False, (
                    f"Insufficient travel gap before job "
                    f"{next_job.id}"
                )

        elif available_minutes < 60:
            return False, (
                f"Cannot verify travel gap before job "
                f"{next_job.id}"
            )

    return True, "Schedule available"


def _check_current_location_arrival(
    gps: dict,
    job,
    target_start: datetime,
) -> tuple[bool, float]:
    """
    For appointments starting within 24 hours, estimate whether
    the technician can reach the customer from the latest GPS fix.

    For appointments further in the future, GPS is used for ranking,
    not as a guaranteed future starting position.
    """

    target_lat = getattr(job, "site_latitude", None)
    target_lon = getattr(job, "site_longitude", None)

    if target_lat is None or target_lon is None:
        return False, 0.0

    distance = _distance_km(
        gps["latitude"],
        gps["longitude"],
        float(target_lat),
        float(target_lon),
    )

    now = datetime.now(timezone.utc)
    target_start_utc = target_start.astimezone(timezone.utc)

    minutes_until_appointment = (
        target_start_utc - now
    ).total_seconds() / 60

    if minutes_until_appointment < 0:
        return False, distance

    if minutes_until_appointment <= 24 * 60:
        required_minutes = _estimated_travel_minutes(distance)

        if minutes_until_appointment < required_minutes:
            return False, distance

    return True, distance


# ---------------------------------------------------------------------
# Candidate collection
# ---------------------------------------------------------------------

def _collect_candidate_identities(
    dispatch_state: dict[str, Any],
) -> tuple[set[tuple[str, int]], set[tuple[str, int]]]:
    """
    Return:
      candidate identities
      explicitly rejected identities

    Timed-out technicians remain eligible for force assignment.
    """

    candidates: set[tuple[str, int]] = set()
    rejected: set[tuple[str, int]] = set()

    for candidate in (
        dispatch_state.get("all_candidates") or []
    ):
        identity = _normalise_identity(candidate)
        if identity:
            candidates.add(identity)

    for candidate in (
        dispatch_state.get("attempted_technicians") or []
    ):
        identity = _normalise_identity(candidate)
        if identity:
            candidates.add(identity)

    for candidate in (
        dispatch_state.get("workload_excluded_technicians") or []
    ):
        identity = _normalise_identity(candidate)
        if identity:
            candidates.add(identity)

    for candidate in (
        dispatch_state.get("rejected_technicians") or []
    ):
        identity = _normalise_identity(candidate)
        if identity:
            rejected.add(identity)

    return candidates, rejected


# ---------------------------------------------------------------------
# Main force assignment
# ---------------------------------------------------------------------

def try_force_assign_job(
    job_id: int,
    dispatch_state: dict[str, Any],
) -> dict[str, Any]:
    """
    Select and directly assign the best eligible technician.

    This function:
    - Does not create a PENDING offer.
    - Does not wait for technician acceptance.
    - Does not call accept_broadcast_offer().
    - Commits assignment, assignment history, notification and audit.
    """

    candidate_identities, rejected_identities = (
        _collect_candidate_identities(dispatch_state)
    )

    if not candidate_identities:
        return {
            "assigned": False,
            "reason": "No previously ranked candidates available",
        }

    ranked_candidates = []

    with SessionLocal() as db:
        # Lock the job first. This prevents two force-assignment
        # workers from assigning the same job simultaneously.
        job = (
            db.query(models.Job)
            .filter(models.Job.id == job_id)
            .with_for_update()
            .first()
        )

        if job is None:
            return {
                "assigned": False,
                "reason": "Job not found",
            }

        # Job.tenant_id is the service-provider organization.
        # customer_tenant_id may identify the originating customer and
        # must not be used to select the technician's tenant.
        job_tenant_id = str(getattr(job, "tenant_id", None) or "").strip()
        if not job_tenant_id:
            return {
                "assigned": False,
                "reason": "Job has no service-provider tenant; refusing cross-tenant assignment",
            }

        if getattr(job, "assigned_technician_id", None) is not None:
            return {
                "assigned": False,
                "reason": "Job already assigned",
            }

        job_status = str(
            getattr(job, "status", "") or ""
        ).strip().upper()

        if job_status in NON_ACTIVE_JOB_STATUSES:
            return {
                "assigned": False,
                "reason": f"Job is not dispatchable: {job_status}",
            }

        target_window = _appointment_window(job)

        if target_window is None:
            return {
                "assigned": False,
                "reason": (
                    "Appointment date or time is missing; "
                    "cannot safely force assign"
                ),
            }

        target_start, target_end = target_window

        customer_lat = getattr(job, "site_latitude", None)
        customer_lon = getattr(job, "site_longitude", None)

        if customer_lat is None or customer_lon is None:
            return {
                "assigned": False,
                "reason": "Customer GPS coordinates are missing",
            }

        rejected_count = 0
        gps_rejected_count = 0
        workload_rejected_count = 0
        skill_rejected_count = 0
        schedule_rejected_count = 0

        for tenant_id, technician_id in sorted(candidate_identities):
            # Enforce service-provider tenant isolation before querying or
            # evaluating a candidate. Technician IDs alone are not enough.
            if tenant_id != job_tenant_id:
                logger.warning(
                    "force_assignment_cross_tenant_candidate_rejected "
                    "job_id=%s job_tenant_id=%s candidate_tenant_id=%s "
                    "technician_id=%s",
                    job_id,
                    job_tenant_id,
                    tenant_id,
                    technician_id,
                )
                continue

            if (tenant_id, technician_id) in rejected_identities:
                rejected_count += 1
                continue

            technician = (
                db.query(models.Technician)
                .filter(
                    models.Technician.tenant_id == tenant_id,
                    models.Technician.technician_id == technician_id,
                )
                .with_for_update()
                .first()
            )

            if technician is None:
                continue

            field_operations = _get_technician_policy(
                db,
                technician,
            )

            # OFFLINE is not an automatic exclusion. The tenant
            # policy can explicitly disable offline force assignment.
            technician_status = str(
                getattr(technician, "technician_status", "") or ""
            ).strip().upper()

            allow_offline = field_operations.get(
                "allow_offline_force_assignment",
                True,
            )

            if technician_status == "OFFLINE" and not allow_offline:
                continue

            gps = _get_fresh_gps(
                technician,
                field_operations,
            )

            if gps is None:
                gps_rejected_count += 1
                continue

            if not _has_required_skill(job, technician):
                skill_rejected_count += 1
                continue

            if not _has_workload_capacity(technician):
                workload_rejected_count += 1
                continue

            schedule_ok, schedule_reason = (
                _check_existing_appointments(
                    db,
                    job,
                    technician,
                    target_start,
                    target_end,
                )
            )

            if not schedule_ok:
                schedule_rejected_count += 1
                logger.info(
                    "force_assignment_candidate_rejected "
                    "job_id=%s technician_id=%s reason=%s",
                    job_id,
                    technician_id,
                    schedule_reason,
                )
                continue

            arrival_ok, distance_km = (
                _check_current_location_arrival(
                    gps,
                    job,
                    target_start,
                )
            )

            if not arrival_ok:
                schedule_rejected_count += 1
                continue

            current_jobs = int(
                getattr(technician, "current_jobs", 0) or 0
            )

            # Nearest technician first; workload and original
            # Planning rank break ties.
            candidate_rank = 9999

            for candidate in (
                dispatch_state.get("all_candidates") or []
            ):
                identity = _normalise_identity(candidate)

                if identity == (tenant_id, technician_id):
                    try:
                        candidate_rank = int(
                            candidate.get("rank") or 9999
                        )
                    except (TypeError, ValueError):
                        pass
                    break

            ranked_candidates.append({
                "technician": technician,
                "gps": gps,
                "distance_km": distance_km,
                "current_jobs": current_jobs,
                "rank": candidate_rank,
            })

        logger.info(
            "force_assignment_candidate_scan job_id=%s "
            "total=%s rejected=%s stale_gps=%s "
            "workload=%s skill=%s schedule=%s eligible=%s",
            job_id,
            len(candidate_identities),
            rejected_count,
            gps_rejected_count,
            workload_rejected_count,
            skill_rejected_count,
            schedule_rejected_count,
            len(ranked_candidates),
        )

        if not ranked_candidates:
            return {
                "assigned": False,
                "reason": "No technician passed force-assignment checks",
                "rejected_count": rejected_count,
                "stale_gps_count": gps_rejected_count,
                "workload_rejected_count": workload_rejected_count,
                "skill_rejected_count": skill_rejected_count,
                "schedule_rejected_count": schedule_rejected_count,
            }

        ranked_candidates.sort(
            key=lambda item: (
                item["distance_km"],
                item["current_jobs"],
                item["rank"],
            )
        )

        winner = ranked_candidates[0]

        technician = winner["technician"]
        now = datetime.now(timezone.utc)

        # A force assignment is immediately accepted, so reserve workload in
        # the same transaction as the job assignment.
        locked_technician = (
            db.query(models.Technician)
            .filter(
                models.Technician.technician_id == technician.technician_id,
                models.Technician.tenant_id == str(technician.tenant_id),
            )
            .with_for_update()
            .first()
        )
        if locked_technician is None:
            return {
                "assigned": False,
                "reason": "Selected technician is no longer available",
            }
        current_workload = max(0, int(locked_technician.current_jobs or 0))
        workload_limit = max(1, int(locked_technician.max_jobs or 5))
        if current_workload >= workload_limit:
            return {
                "assigned": False,
                "reason": "Selected technician reached the workload limit",
            }
        locked_technician.current_jobs = current_workload + 1

        # Final assignment is committed under the locked Job row.
        job.assigned_technician_id = technician.technician_id
        job.status = "ACCEPTED"
        job.assigned_at = now
        job.assigned_by = "SYSTEM_FORCE_ASSIGNMENT"

        # Force assignment is accepted immediately, matching the status after
        # a technician accepts a normal assignment.
        service_request = (
            db.query(models.ServiceRequest)
            .filter(models.ServiceRequest.linked_job_id == job.id)
            .with_for_update()
            .first()
        )
        if service_request is not None:
            service_request.status = "ACCEPTED"

        chat_message = None
        chat_customer_user_id = (
            str(service_request.customer_user_id)
            if service_request is not None and service_request.customer_user_id
            else str(job.customer_id) if job.customer_id else None
        )
        technician_user_id = str(technician.tech_id or "").strip()
        if chat_customer_user_id and technician_user_id:
            technician_user = (
                db.query(models.User)
                .filter(
                    models.User.id == technician_user_id,
                    models.User.tenant_id == str(technician.tenant_id),
                )
                .first()
            )
            if technician_user is not None:
                organization_name = (
                    getattr(getattr(technician, "organization", None), "name", None)
                    or "your service provider"
                )
                contact_number = (
                    technician.phone_number
                    or "the number on your service request"
                )
                chat_message = models.JobMessage(
                    job_id=job.id,
                    tenant_id=str(job.tenant_id),
                    sender_user_id=technician_user_id,
                    sender_role="TECHNICIAN",
                    body=(
                        f"Hi, I’m {technician.technician_name}, your technician "
                        f"for job #{job.id} ({job.service_type}). You can reach "
                        f"me at {contact_number}. I’m with {organization_name}."
                    ),
                )
                db.add(chat_message)
                db.flush()

        # Use the same durable customer booking email as a normal acceptance.
        if callable(getattr(db, "get_bind", None)):
            from app.services.email.transactional_outbox import persist_booking_email

            persist_booking_email(db, job)

        # This is assignment history, not a broadcast offer.
        existing_assignment = (
            db.query(models.JobAssignment)
            .filter(
                models.JobAssignment.job_id == job.id,
                models.JobAssignment.tenant_id == str(technician.tenant_id),
                models.JobAssignment.technician_id == technician.technician_id,
            )
            .first()
        )

        if existing_assignment is None:
            existing_assignment = models.JobAssignment(
                job_id=job.id,
                tenant_id=str(technician.tenant_id),
                technician_id=technician.technician_id,
                rank=int(winner["rank"]),
                status="ACCEPTED",
                assigned_at=now,
                responded_at=now,
                is_current=True,
            )
            db.add(existing_assignment)
        else:
            existing_assignment.status = "ACCEPTED"
            existing_assignment.assigned_at = now
            existing_assignment.responded_at = now
            existing_assignment.is_current = True

        # Other outstanding offers are no longer active.
        (
            db.query(models.JobAssignment)
            .filter(
                models.JobAssignment.job_id == job.id,
                models.JobAssignment.status == "PENDING",
                models.JobAssignment.technician_id
                != technician.technician_id,
            )
            .update(
                {
                    "status": "LOST",
                    "is_current": False,
                },
                synchronize_session=False,
            )
        )

        # Immutable audit record.
        db.add(
            models.AuditEvent(
                tech_id=technician.tech_id,
                tenant_id=str(job.tenant_id or technician.tenant_id),
                event_type="FORCE_ASSIGNMENT",
                old_status=job_status,
                new_status="ACCEPTED",
                reason="All normal broadcast offers were exhausted",
                job_id=str(job.id),
                actor_id="SYSTEM_FORCE_ASSIGNMENT",
                details={
                    "assignment_mode": "FORCE_ASSIGNED",
                    "technician_id": technician.technician_id,
                    "technician_tenant_id": str(technician.tenant_id),
                    "distance_km": round(winner["distance_km"], 2),
                    "gps_last_ping": winner["gps"]["last_ping"].isoformat(),
                    "appointment_duration_hours": (
                        DEFAULT_APPOINTMENT_DURATION_HOURS
                    ),
                },
                timestamp=now,
                correlation_id=str(
                    dispatch_state.get("dispatch_attempt_id") or ""
                )[:36] or None,
            )
        )

        # Persist dispatch result with the assignment transaction.
        final_state = dict(dispatch_state)
        final_state.update({
            "status": "FORCE_ASSIGNED",
            "next_action": "END",
            "dispatch_exhausted": False,
            "force_assignment": {
                "assigned": True,
                "status": "ACCEPTED",
                "technician_id": technician.technician_id,
                "technician_tenant_id": str(technician.tenant_id),
                "technician_name": technician.technician_name,
                "distance_km": round(winner["distance_km"], 2),
                "gps_last_ping": winner["gps"]["last_ping"].isoformat(),
                "assigned_at": now.isoformat(),
                "accepted_at": now.isoformat(),
            },
        })

        job.dispatch_state = final_state

        try:
            db.commit()
            if chat_message is not None:
                db.refresh(chat_message)
        except Exception:
            db.rollback()
            logger.exception(
                "force_assignment_commit_failed job_id=%s technician_id=%s",
                job_id,
                technician.technician_id,
            )
            raise

        logger.warning(
            "FORCE_ASSIGNMENT_SUCCESS job_id=%s technician_id=%s "
            "tenant_id=%s distance_km=%.2f",
            job.id,
            technician.technician_id,
            technician.tenant_id,
            winner["distance_km"],
        )

        return {
            "assigned": True,
            "job_id": job.id,
            "technician_id": technician.technician_id,
            "technician_tenant_id": str(technician.tenant_id),
            "technician_uuid": str(technician.tech_id or ""),
            "technician_name": technician.technician_name,
            "job_title": getattr(job, "service_type", None),
            "location": getattr(job, "location", None),
            "distance_km": round(winner["distance_km"], 2),
            "chat_customer_user_id": chat_customer_user_id,
            "chat_message": (
                {
                    "id": chat_message.id,
                    "job_id": chat_message.job_id,
                    "sender_user_id": chat_message.sender_user_id,
                    "sender_role": chat_message.sender_role,
                    "body": chat_message.body,
                    "created_at": (
                        chat_message.created_at.isoformat()
                        if chat_message.created_at
                        else now.isoformat()
                    ),
                }
                if chat_message is not None
                else None
            ),
            "dispatch_state": final_state,
        }
