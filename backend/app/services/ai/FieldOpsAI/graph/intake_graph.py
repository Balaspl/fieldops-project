"""
intake_graph.py

LangGraph workflow for the FieldOps Intake Agent.
Validates customer service requests, distinguishes between VALID, MISMATCH,
and UNCLEAR requests, and produces a structured validated job requirement.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from langgraph.graph import StateGraph, START, END

from app.utils import map_service_type_to_skill
from app.services.ai.FieldOpsAI.graph.state import (
    IntakeGraphState,
    ValidationErrorDetail,
    ValidatedJobRequirement,
)

# Service detection keywords mapping to canonical categories
SERVICE_KEYWORDS: Dict[str, List[str]] = {
    "Plumbing": [
        "plumb", "plumber", "plumbing", "pipe", "piping", "leak", "leaking", "tap",
        "faucet", "drain", "drainage", "water heater", "toilet", "sink",
        "bathroom pipe", "water leak", "clogged", "sewage", "flush", "geyser",
        "water leakage", "pipeline", "flush tank", "commode",
    ],
    "Electrical": [
        "electric", "electrician", "electrical", "wiring", "wire", "wires",
        "short circuit", "switch", "switchboard", "socket", "light", "lighting",
        "lights", "bulb", "tube light", "tubelight", "lamp", "plug",
        "fan", "fans", "ceiling fan", "exhaust fan", "table fan", "pedestal fan",
        "regulator", "fan regulator", "generator", "power supply", "fuse",
        "breaker", "power outage", "power cut", "spark", "tripping", "meter",
        "mcb", "power trip", "phase", "inverter", "stabilizer", "shock", "electric shock",
    ],
    "HVAC": [
        "ac", "air condition", "air conditioning", "air conditioner", "air conditionar",
        "conditionar", "cooling", "cool", "compressor", "condenser", "thermostat",
        "ventilation", "heating", "hvac", "chiller", "freon", "gas refill",
        "aircon", "a/c", "split ac", "window ac", "duct", "ducts", "air cooler",
        "ac fan", "cooling fan", "blower",
    ],
    "Network Support": [
        "router", "wifi", "wi fi", "wi-fi", "internet", "lan", "ethernet",
        "network", "modem", "broadband", "cabling", "cat6", "fiber", "fibre",
    ],
    "Appliance Repair": [
        "washing machine", "fridge", "refrigerator", "microwave", "oven",
        "dishwasher", "dryer", "appliance", "stove", "induction", "chimney",
    ],
    "Roofing & Carpentry": [
        "roof", "roofing", "carpentry", "carpenter", "woodwork", "door",
        "furniture", "timber", "wood", "cabinet", "cupboard",
    ],
    "CCTV & Security": [
        "cctv", "security camera", "surveillance", "access control",
        "security system", "alarm", "dvr", "nvr", "ip camera",
    ],
    "General Maintenance": [
        "motor alignment", "pump", "valve", "general maintenance",
        "handyman", "general repair", "painting", "masonry",
    ],
}

# Generic words that indicate an unclear/vague request without actionable service info
GENERIC_VAGUE_PATTERNS = [
    r"^\s*i\s+need\s+help\b",
    r"^\s*help\s*$",
    r"^\s*please\s+help\b",
    r"^\s*service\s+needed\b",
    r"^\s*need\s+service\b",
    r"^\s*please\s+fix\b",
    r"^\s*fix\s+this\b",
    r"^\s*something\s+is\s+broken\b",
    r"^\s*issue\s*$",
    r"^\s*problem\s*$",
]


def detect_service_from_text(text: str) -> Optional[str]:
    """
    Detect the most probable service category from natural-language text.
    Returns the canonical service category name, or None if unclear.
    """
    if not text or not text.strip():
        return None

    cleaned = text.lower()

    # Check for purely generic/vague statements
    for pattern in GENERIC_VAGUE_PATTERNS:
        if re.search(pattern, cleaned):
            # Check if any specific keyword overrides it
            has_specific = False
            for cat, keywords in SERVICE_KEYWORDS.items():
                for kw in keywords:
                    if re.search(r"\b" + re.escape(kw) + r"\b", cleaned):
                        has_specific = True
                        break
                if has_specific:
                    break
            if not has_specific:
                return None

    # Score each category based on keyword matches
    category_scores: Dict[str, int] = {}
    for category, keywords in SERVICE_KEYWORDS.items():
        score = 0
        for kw in keywords:
            # Word boundary matching
            matches = len(re.findall(r"\b" + re.escape(kw) + r"\b", cleaned))
            score += matches
        if score > 0:
            category_scores[category] = score

    if not category_scores:
        return None

    # Return category with highest match score
    best_category = max(category_scores.items(), key=lambda item: item[1])[0]
    return best_category


# ─────────────────────────────────────────────────────────────
# Graph Nodes
# ─────────────────────────────────────────────────────────────

def parse_request_node(state: IntakeGraphState) -> Dict[str, Any]:
    """
    Node 1: parse_request
    Extracts and normalizes raw request data.
    """
    raw = state.get("raw_request") or {}

    service = raw.get("service") or raw.get("service_type") or state.get("service") or state.get("service_type")
    title = raw.get("title") or state.get("title") or ""
    description = raw.get("description") or raw.get("request") or raw.get("issue_description") or state.get("description") or ""
    location = raw.get("location") or state.get("location") or ""
    priority = (raw.get("priority") or state.get("priority") or "MEDIUM").upper()
    contact_number = raw.get("contact_number") or state.get("contact_number") or ""
    customer_name = raw.get("customer_name") or raw.get("customer", {}).get("name") if isinstance(raw.get("customer"), dict) else None
    customer_name = customer_name or state.get("customer_name") or "Customer"
    preferred_visit_date = raw.get("preferred_visit_date") or state.get("preferred_visit_date")

    site_lat = raw.get("site_latitude")
    site_lng = raw.get("site_longitude")

    # If coordinates are embedded in location string e.g. "12.9815, 80.221"
    if (site_lat is None or site_lng is None) and location and "," in location:
        parts = location.split(",")
        if len(parts) == 2:
            try:
                site_lat = float(parts[0].strip())
                site_lng = float(parts[1].strip())
            except ValueError:
                pass

    return {
        "service": str(service).strip() if service else None,
        "service_type": str(service).strip() if service else None,
        "title": str(title).strip(),
        "description": str(description).strip(),
        "location": str(location).strip() if location else None,
        "priority": priority,
        "site_latitude": site_lat,
        "site_longitude": site_lng,
        "contact_number": str(contact_number).strip(),
        "customer_name": str(customer_name).strip(),
        "preferred_visit_date": str(preferred_visit_date).strip() if preferred_visit_date else None,
        "validation_errors": [],
    }


def validate_request_node(state: IntakeGraphState) -> Dict[str, Any]:
    """
    Node 2: validate_request
    Performs deterministic validation across service, description, location, etc.
    Distinguishes between VALID, MISMATCH, and UNCLEAR.
    """
    errors: List[ValidationErrorDetail] = []

    service_input = state.get("service") or state.get("service_type")
    description = state.get("description") or ""
    title = state.get("title") or ""
    location = state.get("location")

    combined_text = f"{title} {description}".strip()

    # 1. Location Validation
    if not location or not location.strip():
        errors.append({
            "error_type": "unclear",
            "field": "location",
            "message": "Customer location is required to find the nearest eligible technicians.",
            "detected_value": None,
            "expected_value": "Valid address or coordinates",
        })

    # 2. Service & Description Validation
    UNCLEAR_ERROR_MSG = (
        "The problem could not be understood clearly. Please provide more specific details "
        "about the problem and select the appropriate Service Type."
    )

    if not description or len(description.strip()) < 5:
        errors.append({
            "error_type": "unclear",
            "field": "service",
            "message": UNCLEAR_ERROR_MSG,
            "detected_value": None,
            "expected_value": service_input or "Described service requirement",
        })
    else:
        # Detect service from description
        desc_category = detect_service_from_text(description)
        # Detect service from title (if title contains identifiable service keywords)
        title_category = detect_service_from_text(title) if title else None

        if not service_input or service_input.lower() in ["select service", "select service type", "other", "general"]:
            detected_cat = desc_category or title_category
            errors.append({
                "error_type": "unclear",
                "field": "service",
                "message": (
                    f"The problem could not be understood clearly. Based on your request, "
                    f"this appears to be {detected_cat}. Please select the appropriate Service Type."
                    if detected_cat else UNCLEAR_ERROR_MSG
                ),
                "detected_value": detected_cat,
                "expected_value": detected_cat or "Valid Service Type",
            })
        elif not desc_category and not title_category:
            errors.append({
                "error_type": "unclear",
                "field": "service",
                "message": UNCLEAR_ERROR_MSG,
                "detected_value": None,
                "expected_value": service_input or "Identifiable service description",
            })
        else:
            canonical_selected = map_service_type_to_skill(service_input)

            if canonical_selected == "Other":
                # Check direct match with detected category
                canonical_selected = service_input.strip()

            # Rule: title, description, and selected service must all match the same service
            if title_category and desc_category and title_category.upper() != desc_category.upper():
                errors.append({
                    "error_type": "mismatch",
                    "field": "service",
                    "message": (
                        f"Your request describes a {desc_category}-related problem, but title indicates {title_category} "
                        f"while description indicates {desc_category}. Title, description, and selected service must all match. "
                        f"Please select the appropriate Service Type."
                    ),
                    "detected_value": desc_category,
                    "expected_value": service_input,
                })
            elif desc_category and desc_category.upper() != canonical_selected.upper():
                errors.append({
                    "error_type": "mismatch",
                    "field": "service",
                    "message": (
                        f"Your request describes a {desc_category}-related problem, but you selected {service_input}. "
                        f"Please select the appropriate Service Type."
                    ),
                    "detected_value": desc_category,
                    "expected_value": service_input,
                })
            elif title_category and title_category.upper() != canonical_selected.upper():
                errors.append({
                    "error_type": "mismatch",
                    "field": "service",
                    "message": (
                        f"Your request describes a {title_category}-related problem, but you selected {service_input}. "
                        f"Please select the appropriate Service Type."
                    ),
                    "detected_value": title_category,
                    "expected_value": service_input,
                })
            elif not desc_category:
                # Description lacks clear service details/keywords
                errors.append({
                    "error_type": "unclear",
                    "field": "service",
                    "message": UNCLEAR_ERROR_MSG,
                    "detected_value": None,
                    "expected_value": service_input or "Identifiable service description",
                })
            else:
                # MATCH! Title (if specified), Description, and Selected Service all agree
                detected_category = desc_category

    if errors:
        primary_error = errors[0]
        return {
            "valid": False,
            "error_type": primary_error["error_type"],
            "field": primary_error["field"],
            "message": primary_error["message"],
            "detected_value": primary_error.get("detected_value"),
            "expected_value": primary_error.get("expected_value"),
            "validation_errors": errors,
            "detected_service": primary_error.get("detected_value"),
        }

    # Everything is valid
    canonical_skill = map_service_type_to_skill(service_input)
    return {
        "valid": True,
        "error_type": None,
        "field": None,
        "message": None,
        "detected_value": detected_category if 'detected_category' in locals() else canonical_skill,
        "expected_value": service_input,
        "validation_errors": [],
        "detected_service": detected_category if 'detected_category' in locals() else canonical_skill,
        "detected_skill": canonical_skill,
    }


def validation_router(state: IntakeGraphState) -> str:
    """
    Router condition: valid -> build_validated_job, invalid -> build_validation_error.
    """
    if state.get("valid", False):
        return "build_validated_job"
    return "build_validation_error"


def build_validation_error_node(state: IntakeGraphState) -> Dict[str, Any]:
    """
    Node: build_validation_error
    Formats the structured validation error response.
    """
    return {
        "valid": False,
        "error_type": state.get("error_type", "unclear"),
        "field": state.get("field", "service"),
        "message": state.get("message", "Validation failed."),
        "detected_value": state.get("detected_value"),
        "expected_value": state.get("expected_value"),
        "validation_errors": state.get("validation_errors", []),
        "job_requirement": None,
    }


def build_validated_job_node(state: IntakeGraphState) -> Dict[str, Any]:
    """
    Node: build_validated_job
    Packages the validated job requirement to hand off to Planning Agent.
    """
    service = state.get("service") or "General"
    canonical_skill = state.get("detected_skill") or map_service_type_to_skill(service)

    job_req: ValidatedJobRequirement = {
        "service": service,
        "required_skill": canonical_skill,
        "location": state.get("location") or "",
        "priority": state.get("priority") or "MEDIUM",
        "title": state.get("title") or service,
        "description": state.get("description") or "",
        "site_latitude": state.get("site_latitude"),
        "site_longitude": state.get("site_longitude"),
        "contact_number": state.get("contact_number"),
        "customer_name": state.get("customer_name"),
        "preferred_visit_date": state.get("preferred_visit_date"),
    }

    return {
        "valid": True,
        "job_requirement": job_req,
    }


# ─────────────────────────────────────────────────────────────
# Graph Builder
# ─────────────────────────────────────────────────────────────

def build_intake_graph():
    """
    Compiles and returns the Intake LangGraph workflow.
    """
    builder = StateGraph(IntakeGraphState)

    builder.add_node("parse_request", parse_request_node)
    builder.add_node("validate_request", validate_request_node)
    builder.add_node("build_validation_error", build_validation_error_node)
    builder.add_node("build_validated_job", build_validated_job_node)

    builder.add_edge(START, "parse_request")
    builder.add_edge("parse_request", "validate_request")

    builder.add_conditional_edges(
        "validate_request",
        validation_router,
        {
            "build_validated_job": "build_validated_job",
            "build_validation_error": "build_validation_error",
        },
    )

    builder.add_edge("build_validated_job", END)
    builder.add_edge("build_validation_error", END)

    return builder.compile()


# Pre-compiled intake graph instance
intake_graph = build_intake_graph()

