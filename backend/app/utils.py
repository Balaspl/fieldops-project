from __future__ import annotations

import math

def calculate_distance(loc1: str, loc2: str) -> float:
    """
    Calculate the distance (Euclidean) between two points defined as "lat, lon".
    Returns distance in arbitrary units (degrees-like).
    
    If conversion fails (e.g. city names), returns a large number or 0 depending on logic.
    For this engine, we assume "lat, lon" format.
    """
    try:
        lat1, lon1 = map(float, loc1.split(','))
        lat2, lon2 = map(float, loc2.split(','))
        
        # Simple Euclidean distance for simplicity
        # For real-world use Haversine, but this satisfies "Compare nearest"
        return math.sqrt((lat1 - lat2)**2 + (lon1 - lon2)**2)
    except Exception:
        # Fallback if locations are names
        if loc1.lower() == loc2.lower():
            return 0.0
        return 999999.0

def map_service_type_to_skill(service_type: str) -> str:
    if not service_type:
        return "Other"
    st = service_type.strip().upper().replace("_", " ")
    
    # HVAC
    if any(x in st for x in ["HVAC", "AC SERVICE", "COOLING SYSTEM", "COMPRESSOR", "CONDENSER", "AC GAS", "THERMOSTAT", "HVAC REPAIR"]):
        return "HVAC"
        
    # Electrical
    if any(x in st for x in ["WIRING", "SWITCHBOARD", "LIGHTING", "SHORT CIRCUIT", "GENERATOR", "ELECTRICAL", "CCTV"]):
        return "Electrical"
        
    # Plumbing
    if any(x in st for x in ["PIPE", "TAP", "DRAIN", "PLUMBING", "WATER HEATER"]):
        return "Plumbing"
        
    # Network Support
    if any(x in st for x in ["NETWORK", "ROUTER", "CABLE"]):
        return "Network Support"
        
    # General Maintenance
    if any(x in st for x in ["GENERAL", "MAINTENANCE", "MOTOR ALIGNMENT", "PUMP", "VALVE"]):
        return "General Maintenance"
        
    return "Other"

def is_skill_matching(tech_skill: str, job_skill: str, job_service_type: str) -> bool:
    if not tech_skill:
        return True
        
    t_skill = tech_skill.strip().upper().replace("_", " ")
    j_skill = job_skill.strip().upper().replace("_", " ") if job_skill else ""
    j_type = job_service_type.strip().upper().replace("_", " ") if job_service_type else ""
    
    # 1. Direct equality
    if (j_skill and t_skill == j_skill) or (j_type and t_skill == j_type):
        return True
        
    # 2. Substring / partial match
    if j_skill and (j_skill in t_skill or t_skill in j_skill):
        return True
    if j_type and (j_type in t_skill or t_skill in j_type):
        return True
        
    # 3. Standardized skill category mapping
    mapped_j_type = map_service_type_to_skill(j_type or j_skill).upper()
    mapped_t_skill = map_service_type_to_skill(t_skill).upper()
    if mapped_j_type and mapped_t_skill and mapped_j_type == mapped_t_skill:
        return True
        
    # 4. Common typo / keyword tolerance (Plumbing / Plumping / Electrical / HVAC)
    if ("PLUMP" in t_skill or "PLUMB" in t_skill) and any("PLUMP" in x or "PLUMB" in x for x in [j_skill, j_type]):
        return True
    if "ELEC" in t_skill and any("ELEC" in x for x in [j_skill, j_type]):
        return True
    if ("HVAC" in t_skill or "AC" in t_skill) and any(k in j_type or k in j_skill for k in ["HVAC", "AC", "COOL"]):
        return True

    return False


"""
app/utils/time.py
─────────────────
UTC helpers so every timestamp that leaves the backend carries an explicit
timezone. A naive ISO string ("2026-09-29T10:00:00") is read by browsers as
LOCAL time, which makes every ping look ~5.5 h old in IST.
"""


from datetime import datetime, timezone
from typing import Optional


def as_utc(dt: datetime) -> datetime:
    """Return an aware UTC datetime. Naive datetimes are assumed to be UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iso_utc(dt: Optional[datetime]) -> Optional[str]:
    """ISO-8601 string in UTC with a trailing 'Z'. None stays None."""
    if dt is None:
        return None
    if not isinstance(dt, datetime):
        return str(dt)
    return as_utc(dt).isoformat().replace("+00:00", "Z")


def parse_iso_utc(value: str) -> datetime:
    """Parse an ISO string (with 'Z' or offset, or naive) into aware UTC."""
    return as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))