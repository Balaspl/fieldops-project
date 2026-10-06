from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Optional


def calculate_distance(loc1: str, loc2: str) -> float:
    """
    Calculate the distance (Euclidean) between two points defined as "lat, lon".
    Returns distance in arbitrary units (degrees-like).

    If conversion fails (e.g. city names), returns a large number or 0
    depending on the comparison logic.

    For this engine, we assume "lat, lon" format.
    """
    try:
        lat1, lon1 = map(float, loc1.split(","))
        lat2, lon2 = map(float, loc2.split(","))

        # Simple Euclidean distance for comparison.
        # For production geographic distance, Haversine would be preferable.
        return math.sqrt(
            (lat1 - lat2) ** 2 + (lon1 - lon2) ** 2
        )

    except Exception:
        # Fallback if locations are city/place names.
        if loc1.strip().lower() == loc2.strip().lower():
            return 0.0

        return 999999.0


def map_service_type_to_skill(service_type: str) -> str:
    """
    Map a job service type or technician skill value to a canonical
    technician skill category.

    Canonical categories used by the assignment logic:

        HVAC
        Electrical
        Plumbing
        Network Support
        General Maintenance
        Appliance Repair
        Roofing & Carpentry
        CCTV & Security
        Other
    """
    if not service_type:
        return "Other"

    st = (
        service_type
        .strip()
        .upper()
        .replace("_", " ")
        .replace("-", " ")
    )

    # Normalize repeated whitespace.
    st = " ".join(st.split())

    # ------------------------------------------------------------------
    # HVAC
    # ------------------------------------------------------------------
    if any(
        keyword in st
        for keyword in (
            "HVAC",
            "HVAC REPAIR",
            "HVAC SERVICE",
            "AC SERVICE",
            "AC REPAIR",
            "AIR CONDITIONING",
            "AIR CONDITIONER",
            "COOLING SYSTEM",
            "COMPRESSOR",
            "CONDENSER",
            "AC GAS",
            "THERMOSTAT",
        )
    ):
        return "HVAC"

    # ------------------------------------------------------------------
    # Electrical
    # ------------------------------------------------------------------
    if any(
        keyword in st
        for keyword in (
            "ELECTRICAL",
            "ELECTRICIAN",
            "ELECTRIC",
            "WIRING",
            "SWITCHBOARD",
            "LIGHTING",
            "SHORT CIRCUIT",
            "GENERATOR",
            "POWER SUPPLY",
        )
    ):
        return "Electrical"

    # ------------------------------------------------------------------
    # Plumbing
    # ------------------------------------------------------------------
    if any(
        keyword in st
        for keyword in (
            "PLUMBING",
            "PLUMBER",
            "PLUMPING",
            "PIPE",
            "PIPING",
            "TAP",
            "FAUCET",
            "DRAIN",
            "DRAINAGE",
            "WATER LEAK",
            "WATER HEATER",
        )
    ):
        return "Plumbing"

    # ------------------------------------------------------------------
    # Network Support
    # ------------------------------------------------------------------
    if any(
        keyword in st
        for keyword in (
            "NETWORK SUPPORT",
            "NETWORK",
            "ROUTER",
            "SWITCH",
            "LAN",
            "WIFI",
            "WI FI",
            "INTERNET",
            "ETHERNET",
            "CABLE NETWORK",
        )
    ):
        return "Network Support"

    # ------------------------------------------------------------------
    # Appliance Repair / Home Appliances
    # ------------------------------------------------------------------
    if any(
        keyword in st
        for keyword in (
            "APPLIANCE REPAIR",
            "APPLIANCE",
            "HOME APPLIANCES",
            "HOME APPLIANCE",
            "WASHING MACHINE",
            "REFRIGERATOR",
            "FRIDGE",
            "MICROWAVE",
            "OVEN",
            "DISHWASHER",
        )
    ):
        return "Appliance Repair"

    # ------------------------------------------------------------------
    # Roofing & Carpentry
    # ------------------------------------------------------------------
    if any(
        keyword in st
        for keyword in (
            "ROOFING & CARPENTRY",
            "ROOFING AND CARPENTRY",
            "ROOFING CARPENTRY",
            "ROOFING",
            "CARPENTRY",
            "CARPENTER",
            "WOODWORK",
        )
    ):
        return "Roofing & Carpentry"

    # ------------------------------------------------------------------
    # CCTV & Security
    # ------------------------------------------------------------------
    if any(
        keyword in st
        for keyword in (
            "CCTV & SECURITY",
            "CCTV AND SECURITY",
            "CCTV SECURITY",
            "CCTV",
            "SECURITY",
            "SURVEILLANCE",
            "ACCESS CONTROL",
            "SECURITY SYSTEM",
        )
    ):
        return "CCTV & Security"

    # ------------------------------------------------------------------
    # General Maintenance
    # ------------------------------------------------------------------
    if any(
        keyword in st
        for keyword in (
            "GENERAL MAINTENANCE",
            "GENERAL MAINTENANCE SERVICE",
            "GENERAL",
            "MAINTENANCE",
            "MOTOR ALIGNMENT",
            "PUMP",
            "VALVE",
        )
    ):
        return "General Maintenance"

    return "Other"


def is_skill_matching(
    tech_skill: str,
    job_skill: str,
    job_service_type: str,
) -> bool:
    """
    Return True only when the technician has a skill that matches
    the job's required service category.

    Technician skills may be stored as comma-separated values.

    The job service type is treated as the authoritative requirement
    when available. The job_skill is used only when service type is
    unavailable.

    Examples:

        technician = "HVAC Repair"
        job = "HVAC Repair"
        -> True

        technician = "HVAC Repair"
        job = "Electrical"
        -> False

        technician = "Electrical, HVAC Repair"
        job = "HVAC Repair"
        -> True

        technician = "Plumbing"
        job = "HVAC Repair"
        -> False

        technician = ""
        job = "HVAC Repair"
        -> False
    """

    # A technician without a skill must never be considered eligible.
    if not tech_skill or not tech_skill.strip():
        return False

    # Service type is the primary/authoritative requirement.
    required_value = (
        job_service_type.strip()
        if job_service_type and job_service_type.strip()
        else job_skill.strip()
        if job_skill and job_skill.strip()
        else ""
    )

    # A job without a usable skill/service requirement cannot be
    # matched safely.
    if not required_value:
        return False

    required_normalized = (
        required_value
        .upper()
        .replace("_", " ")
        .replace("-", " ")
        .strip()
    )

    required_normalized = " ".join(
        required_normalized.split()
    )

    required_category = map_service_type_to_skill(
        required_normalized
    )

    # If we cannot determine the required category, do not
    # allow a permissive assignment.
    if required_category == "Other":
        return False

    # Technician skills may contain multiple comma-separated values.
    technician_skills = [
        skill.strip()
        for skill in tech_skill.split(",")
        if skill and skill.strip()
    ]

    if not technician_skills:
        return False

    for skill in technician_skills:
        skill_normalized = (
            skill
            .upper()
            .replace("_", " ")
            .replace("-", " ")
            .strip()
        )

        skill_normalized = " ".join(
            skill_normalized.split()
        )

        # Direct exact match.
        if skill_normalized == required_normalized:
            return True

        # Compare both values through the canonical category.
        technician_category = map_service_type_to_skill(
            skill_normalized
        )

        if technician_category == required_category:
            return True

    return False


# ---------------------------------------------------------------------------
# UTC helpers
# ---------------------------------------------------------------------------

def as_utc(dt: datetime) -> datetime:
    """
    Return an aware UTC datetime.

    Naive datetimes are assumed to already represent UTC.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)


def iso_utc(dt: Optional[datetime]) -> Optional[str]:
    """
    Convert a datetime to an ISO-8601 UTC string ending in 'Z'.

    None stays None.
    Non-datetime values are returned as strings.
    """
    if dt is None:
        return None

    if not isinstance(dt, datetime):
        return str(dt)

    return as_utc(dt).isoformat().replace(
        "+00:00",
        "Z",
    )


def parse_iso_utc(value: str) -> datetime:
    """
    Parse an ISO-8601 datetime containing Z, an explicit offset,
    or no timezone into an aware UTC datetime.
    """
    return as_utc(
        datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    )