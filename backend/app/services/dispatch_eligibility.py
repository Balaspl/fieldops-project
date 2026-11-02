"""
Authoritative, fail-closed technician eligibility checks for dispatch.

Rules:
- AVAILABLE, BUSY, and OFFLINE technicians can be considered.
- Presence status does not block dispatch planning.
- Heartbeat freshness does not block dispatch planning.
- Maximum workload is 5 active jobs.
- Technicians with current_jobs >= 5 are excluded.
- Tenant validation remains mandatory when job_tenant_id is provided.
- Valid location is required for distance-based planning.
- Location priority:
    1. Fresh and valid Redis GPS coordinates
    2. Saved technician coordinates
    3. Organization fallback coordinates
"""

from __future__ import annotations

import json
import logging
import math
import os

from datetime import datetime, timezone
from typing import Any


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

HEARTBEAT_MAX_AGE_SECONDS = int(
    os.getenv("DISPATCH_HEARTBEAT_MAX_AGE_SECONDS", "120")
)

LOCATION_MAX_AGE_SECONDS = int(
    os.getenv("DISPATCH_LOCATION_MAX_AGE_SECONDS", "120")
)

MINIMUM_ACCEPTED_GPS_ACCURACY_METERS = 150.0

LOCATION_MAX_ACCURACY_METERS = float(
    os.getenv("DISPATCH_MAX_GPS_ACCURACY_METERS", "150")
)

MAX_TECHNICIAN_WORKLOAD = 5


# ---------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------

def _age_seconds(
    value: Any,
    now: datetime,
) -> float | None:
    """
    Calculate the age of a datetime value.

    This is informational only. Heartbeat age does not determine
    technician dispatch eligibility.
    """

    if not isinstance(value, datetime):
        return None

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    age = (
        now - value.astimezone(timezone.utc)
    ).total_seconds()

    if age < -30:
        return None

    return age


# ---------------------------------------------------------------------
# Coordinate validation
# ---------------------------------------------------------------------

def _valid_coordinates(
    latitude: Any,
    longitude: Any,
) -> tuple[float, float] | None:
    """Validate latitude and longitude."""

    try:
        lat = float(latitude)
        lng = float(longitude)

    except (TypeError, ValueError, OverflowError):
        return None

    if not math.isfinite(lat) or not math.isfinite(lng):
        return None

    if not (-90 <= lat <= 90):
        return None

    if not (-180 <= lng <= 180):
        return None

    return lat, lng


def _parse_saved_location(
    technician: Any,
) -> tuple[float, float] | None:
    """
    Read saved technician coordinates.

    Expected format:
        latitude,longitude
    """

    saved_location = str(
        getattr(technician, "technician_location", "") or ""
    ).strip()

    if not saved_location:
        return None

    try:
        latitude_text, longitude_text = saved_location.split(",", 1)

        return _valid_coordinates(
            latitude_text.strip(),
            longitude_text.strip(),
        )

    except ValueError:
        return None


def _parse_fallback_location(
    fallback_location: tuple[float, float] | None,
) -> tuple[float, float] | None:
    """Validate organization fallback coordinates."""

    if fallback_location is None:
        return None

    try:
        return _valid_coordinates(
            fallback_location[0],
            fallback_location[1],
        )

    except (TypeError, ValueError, IndexError):
        return None


# ---------------------------------------------------------------------
# Redis GPS lookup
# ---------------------------------------------------------------------

def _get_redis_location(
    technician: Any,
    redis_client: Any,
    now: datetime,
) -> dict[str, Any]:
    """
    Retrieve a fresh, valid technician GPS location.

    Stale or inaccurate GPS data is not used for distance ranking.
    The caller can fall back to saved technician or organization
    coordinates instead.
    """

    result = {
        "coordinates": None,
        "location_age_seconds": None,
        "accuracy_meters": None,
        "reason": None,
    }

    tenant_id = str(
        getattr(technician, "tenant_id", "") or ""
    )

    if redis_client is None or not tenant_id:
        result["reason"] = "redis_location_unavailable"
        return result

    identities = (
        getattr(technician, "tech_id", None),
        getattr(technician, "technician_id", None),
    )

    for identity in identities:

        if identity is None:
            continue

        try:
            redis_key = (
                f"gps:availability:{tenant_id}:{identity}"
            )

            raw = redis_client.get(redis_key)

            if not raw:
                continue

            if isinstance(raw, (str, bytes, bytearray)):
                location = json.loads(raw)
            else:
                location = raw

            if not isinstance(location, dict):
                continue

            coordinates = _valid_coordinates(
                location.get("latitude"),
                location.get("longitude"),
            )

            if coordinates is None:
                result["reason"] = "invalid_location_coordinates"
                continue

            # ---------------------------------------------------------
            # Validate GPS timestamp
            # ---------------------------------------------------------

            raw_timestamp = location.get("timestamp")

            if not raw_timestamp:
                result["reason"] = "missing_location_timestamp"
                continue

            try:
                timestamp = datetime.fromisoformat(
                    str(raw_timestamp).replace("Z", "+00:00")
                )

                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(
                        tzinfo=timezone.utc
                    )

                location_age = (
                    now - timestamp.astimezone(timezone.utc)
                ).total_seconds()

            except (TypeError, ValueError, OverflowError):
                result["reason"] = "invalid_location_timestamp"
                continue

            if location_age < -30:
                result["reason"] = "future_location_timestamp"
                continue

            if location_age > LOCATION_MAX_AGE_SECONDS:
                result["reason"] = "stale_location"
                continue

            # ---------------------------------------------------------
            # Validate GPS accuracy
            # ---------------------------------------------------------

            raw_accuracy = location.get("accuracy")

            accuracy = None

            if raw_accuracy is not None:

                try:
                    accuracy = float(raw_accuracy)

                except (TypeError, ValueError, OverflowError):
                    result["reason"] = "invalid_location_accuracy"
                    continue

                if not math.isfinite(accuracy) or accuracy < 0:
                    result["reason"] = "invalid_location_accuracy"
                    continue

                if accuracy > LOCATION_MAX_ACCURACY_METERS:
                    result["reason"] = "poor_location_accuracy"
                    continue

            # ---------------------------------------------------------
            # Valid GPS location
            # ---------------------------------------------------------

            result["coordinates"] = coordinates

            result["location_age_seconds"] = round(
                location_age,
                1,
            )

            result["accuracy_meters"] = accuracy

            result["reason"] = None

            return result

        except Exception:

            logger.warning(
                "Technician GPS lookup failed for identity=%s",
                identity,
                exc_info=True,
            )

            result["reason"] = "location_lookup_failed"

    return result


# ---------------------------------------------------------------------
# Main eligibility function
# ---------------------------------------------------------------------

def evaluate_technician_dispatch_eligibility(
    technician: Any,
    *,
    job_tenant_id: str | None,
    redis_client: Any,
    fallback_location: tuple[float, float] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    Evaluate whether a technician can be considered for dispatch.

    Eligibility requirements:

    1. Tenant must match when job_tenant_id is provided.
    2. Technician workload must be below 5.
    3. A valid location must be available.

    The following are informational only and never block eligibility:

    - AVAILABLE status
    - BUSY status
    - OFFLINE status
    - Missing heartbeat
    - Stale heartbeat
    """

    now = now or datetime.now(timezone.utc)

    # -----------------------------------------------------------------
    # Technician information
    # -----------------------------------------------------------------

    technician_id = getattr(
        technician,
        "technician_id",
        None,
    )

    tech_user_id = getattr(
        technician,
        "tech_id",
        None,
    )

    tenant_id = str(
        getattr(technician, "tenant_id", "") or ""
    )

    status = str(
        getattr(technician, "technician_status", "") or ""
    ).strip().upper()

    reasons: list[str] = []

    # -----------------------------------------------------------------
    # Tenant validation
    # -----------------------------------------------------------------

    if (
        job_tenant_id is not None
        and tenant_id != str(job_tenant_id)
    ):

        reasons.append("tenant_mismatch")

    # -----------------------------------------------------------------
    # Workload validation
    # -----------------------------------------------------------------

    raw_workload = getattr(
        technician,
        "current_jobs",
        0,
    )

    try:
        workload = int(raw_workload or 0)

    except (TypeError, ValueError, OverflowError):

        workload = MAX_TECHNICIAN_WORKLOAD

        reasons.append("invalid_workload")

    if workload < 0:
        reasons.append("invalid_workload")

    elif workload >= MAX_TECHNICIAN_WORKLOAD:

        reasons.append("workload_limit_reached")

    # -----------------------------------------------------------------
    # Heartbeat information
    # -----------------------------------------------------------------

    heartbeat_age = _age_seconds(
        getattr(technician, "last_ping", None),
        now,
    )

    # IMPORTANT:
    # Do not add a blocking reason for missing or stale heartbeat.
    # Offline technicians are valid dispatch candidates.

    # -----------------------------------------------------------------
    # Location lookup
    # -----------------------------------------------------------------

    gps_result = _get_redis_location(
        technician=technician,
        redis_client=redis_client,
        now=now,
    )

    coordinates = gps_result["coordinates"]

    location_age = gps_result["location_age_seconds"]

    accuracy = gps_result["accuracy_meters"]

    location_source = None

    if coordinates is not None:

        location_source = "redis_gps"

    # -----------------------------------------------------------------
    # Saved technician location fallback
    # -----------------------------------------------------------------

    if coordinates is None:

        coordinates = _parse_saved_location(
            technician
        )

        if coordinates is not None:

            location_source = "technician_saved_location"

    # -----------------------------------------------------------------
    # Organization location fallback
    # -----------------------------------------------------------------

    if coordinates is None:

        coordinates = _parse_fallback_location(
            fallback_location
        )

        if coordinates is not None:

            location_source = "organization_location"

    # -----------------------------------------------------------------
    # Location requirement
    # -----------------------------------------------------------------

    if coordinates is None:

        reasons.append("location_unavailable")

    # -----------------------------------------------------------------
    # Final result
    # -----------------------------------------------------------------

    eligible = not reasons

    return {
        "eligible": eligible,

        "reason": (
            ",".join(dict.fromkeys(reasons))
            if reasons
            else None
        ),

        "technician_id": technician_id,

        "tech_user_id": tech_user_id,

        "tenant_id": tenant_id,

        # Presence is informational only.
        "availability": status or "UNKNOWN",

        # Workload is mandatory.
        "workload": workload,

        "workload_limit": MAX_TECHNICIAN_WORKLOAD,

        "remaining_capacity": max(
            0,
            MAX_TECHNICIAN_WORKLOAD - workload,
        ),

        # Heartbeat is informational only.
        "heartbeat_age_seconds": (
            round(heartbeat_age, 1)
            if heartbeat_age is not None
            else None
        ),

        "location_age_seconds": location_age,

        "accuracy_meters": accuracy,

        "location_coordinates": coordinates,

        "location_source": location_source,
    }