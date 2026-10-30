"""Authoritative, fail-closed technician eligibility checks for dispatch."""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timedelta, timezone
from typing import Any


HEARTBEAT_MAX_AGE_SECONDS = int(os.getenv("DISPATCH_HEARTBEAT_MAX_AGE_SECONDS", "120"))
LOCATION_MAX_AGE_SECONDS = int(os.getenv("DISPATCH_LOCATION_MAX_AGE_SECONDS", "120"))
MINIMUM_ACCEPTED_GPS_ACCURACY_METERS = 150.0
LOCATION_MAX_ACCURACY_METERS = float(os.getenv("DISPATCH_MAX_GPS_ACCURACY_METERS", "150"))


def _age_seconds(value: Any, now: datetime) -> float | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    age = (now - value.astimezone(timezone.utc)).total_seconds()
    if age < -30:
        return None
    return age


def evaluate_technician_dispatch_eligibility(
    technician: Any,
    *,
    job_tenant_id: str | None,
    redis_client: Any,
    fallback_location: tuple[float, float] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return authoritative eligibility and safe diagnostic fields."""
    import app.services.dispatch_eligibility as _this_mod

    now = now or datetime.now(timezone.utc)
    tenant_id = str(getattr(technician, "tenant_id", "") or "")
    technician_id = getattr(technician, "technician_id", None)
    tech_user_id = getattr(technician, "tech_id", None)
    status = str(getattr(technician, "technician_status", "") or "").strip().upper()
    reasons: list[str] = []

    if status != "AVAILABLE":
        reasons.append("not_available")

    if job_tenant_id is not None and tenant_id != str(job_tenant_id):
        reasons.append("tenant_mismatch")

    raw_last_ping = getattr(technician, "last_ping", None)
    heartbeat_age = _age_seconds(raw_last_ping, now)
    if raw_last_ping is None:
        reasons.append("missing_or_future_heartbeat")
    elif heartbeat_age is None:
        reasons.append("missing_or_future_heartbeat")
    elif heartbeat_age > _this_mod.HEARTBEAT_MAX_AGE_SECONDS:
        reasons.append("stale_heartbeat")

    location: dict[str, Any] | None = None
    location_lookup_failed = False
    if redis_client is not None and tenant_id:
        for identity in (tech_user_id, technician_id):
            if identity is None:
                continue
            try:
                raw = redis_client.get(f"gps:availability:{tenant_id}:{identity}")
                if raw:
                    location = json.loads(raw) if isinstance(raw, (str, bytes, bytearray)) else raw
                    break
            except Exception:
                location_lookup_failed = True
                break
    else:
        location_lookup_failed = True

    location_age: float | None = None
    accuracy: float | None = None
    coordinates: tuple[float, float] | None = None
    has_raw_location = isinstance(location, dict)

    if has_raw_location:
        try:
            lat = float(location["latitude"])
            lng = float(location["longitude"])
            if not (math.isfinite(lat) and math.isfinite(lng) and -90 <= lat <= 90 and -180 <= lng <= 180):
                raise ValueError("invalid cached coordinates")
            coordinates = (lat, lng)
            raw_accuracy = location.get("accuracy")
            accuracy = float(raw_accuracy) if raw_accuracy is not None else None
            raw_timestamp = location.get("timestamp")
            if raw_timestamp:
                timestamp = datetime.fromisoformat(str(raw_timestamp).replace("Z", "+00:00"))
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
                location_age = (now - timestamp.astimezone(timezone.utc)).total_seconds()
        except (KeyError, TypeError, ValueError, OverflowError):
            coordinates = None
            reasons.append("invalid_location_coordinates")

        if location_age is not None and location_age > _this_mod.LOCATION_MAX_AGE_SECONDS:
            reasons.append("stale_location")

        max_accuracy = getattr(_this_mod, "LOCATION_MAX_ACCURACY_METERS", LOCATION_MAX_ACCURACY_METERS)
        if accuracy is not None and accuracy > max_accuracy:
            reasons.append("poor_location_accuracy")

    if coordinates is None:
        saved_location = str(getattr(technician, "technician_location", "") or "")
        try:
            lat_text, lng_text = saved_location.split(",", 1)
            lat, lng = float(lat_text.strip()), float(lng_text.strip())
            if math.isfinite(lat) and math.isfinite(lng) and -90 <= lat <= 90 and -180 <= lng <= 180:
                coordinates = (lat, lng)
        except (TypeError, ValueError):
            pass

    if coordinates is None:
        tech_lat = getattr(technician, "latitude", None)
        tech_lng = getattr(technician, "longitude", None)
        if tech_lat is not None and tech_lng is not None:
            try:
                lat, lng = float(tech_lat), float(tech_lng)
                if math.isfinite(lat) and math.isfinite(lng) and -90 <= lat <= 90 and -180 <= lng <= 180:
                    coordinates = (lat, lng)
            except (TypeError, ValueError):
                pass

    if coordinates is None and fallback_location is not None:
        try:
            lat, lng = float(fallback_location[0]), float(fallback_location[1])
            if math.isfinite(lat) and math.isfinite(lng) and -90 <= lat <= 90 and -180 <= lng <= 180:
                coordinates = (lat, lng)
        except (TypeError, ValueError, IndexError):
            pass

    if coordinates is None:
        if not has_raw_location or "invalid_location_coordinates" not in reasons:
            reasons.append("location_unavailable")

    return {
        "eligible": not reasons,
        "reason": ",".join(dict.fromkeys(reasons)) or None,
        "availability": status or "UNKNOWN",
        "heartbeat_age_seconds": round(heartbeat_age, 1) if heartbeat_age is not None else None,
        "location_age_seconds": round(location_age, 1) if location_age is not None else None,
        "accuracy_meters": accuracy,
        "location_coordinates": coordinates,
    }
