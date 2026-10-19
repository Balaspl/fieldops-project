
"""
planning_graph.py

LangGraph workflow for the FieldOps Planning Agent.

Features:
- Considers technicians regardless of AVAILABLE, BUSY, or OFFLINE status.
- Does not exclude technicians based on current workload.
- Matches skills such as HVAC with HVAC Repair.
- Ranks organizations by distance to the customer.
- Ranks technicians within each organization by distance.
- Returns the top three technicians and the complete ranked list.
- Logs eligibility filtering details for debugging.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from langgraph.graph import StateGraph, START, END

from app.database import SessionLocal
from app.models import Organization, Technician
from app.services.ola_map_client import haversine_distance
from app.services.ai.FieldOpsAI.graph.state import PlanningGraphState


logger = logging.getLogger(__name__)

DEFAULT_CUSTOMER_COORDINATES = (13.0827, 80.2707)


# ---------------------------------------------------------
# LOCATION HELPERS
# ---------------------------------------------------------

def get_coordinates_for_location(
    site_lat: Optional[float],
    site_lng: Optional[float],
    location_str: Optional[str] = None,
) -> Tuple[float, float]:
    """Resolve customer coordinates, falling back to Chennai central."""

    if site_lat is not None and site_lng is not None:
        try:
            lat = float(site_lat)
            lng = float(site_lng)

            if -90 <= lat <= 90 and -180 <= lng <= 180:
                return lat, lng
        except (TypeError, ValueError):
            pass

    # Accept a location string only when it contains exactly
    # two comma-separated numeric coordinates.
    if location_str and "," in location_str:
        parts = location_str.split(",")

        if len(parts) == 2:
            try:
                lat = float(parts[0].strip())
                lng = float(parts[1].strip())

                if -90 <= lat <= 90 and -180 <= lng <= 180:
                    return lat, lng
            except (TypeError, ValueError):
                pass

    return DEFAULT_CUSTOMER_COORDINATES


def normalize_ids(values: Optional[List[Any]]) -> set[int]:
    """Normalize excluded technician IDs."""

    result: set[int] = set()

    for value in values or []:
        try:
            result.add(int(value))
        except (TypeError, ValueError):
            continue

    return result


# ---------------------------------------------------------
# SKILL MATCHING
# ---------------------------------------------------------

def normalize_skill(value: Any) -> str:
    """Normalize a skill name for comparisons."""

    if value is None:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value).strip().casefold().replace("&", " and "),
    )


def technician_has_required_skill(
    technician_skills: Any,
    required_skill: Any,
    service: Any = None,
) -> bool:
    """
    Match a required skill against a technician's skill list.

    Examples:
        Required: HVAC
        Technician skills: Electrical, HVAC Repair
        Result: match

        Required: Plumbing
        Technician skills: Electrical
        Result: no match
    """

    requirements = {
        normalize_skill(required_skill),
        normalize_skill(service),
    }
    requirements.discard("")

    if not requirements:
        # Do not accidentally match every technician when
        # the job has no required skill.
        return False

    if isinstance(technician_skills, str):
        skills = technician_skills.split(",")
    elif isinstance(technician_skills, (list, tuple, set)):
        skills = list(technician_skills)
    else:
        skills = []

    normalized_skills = [
        normalize_skill(skill)
        for skill in skills
        if normalize_skill(skill)
    ]

    for required in requirements:
        for skill in normalized_skills:
            if required == skill:
                return True

            # Permit specific service variants, such as
            # HVAC matching HVAC Repair.
            if (
                len(required) >= 3
                and re.search(
                    rf"(?<![a-z0-9]){re.escape(required)}(?![a-z0-9])",
                    skill,
                )
            ):
                return True

    return False


# ---------------------------------------------------------
# DATABASE SESSION HELPERS
# ---------------------------------------------------------

def get_database(state: PlanningGraphState):
    """Return the provided database session or create one."""

    db = state.get("db")

    if db is not None:
        return db, False

    return SessionLocal(), True


# ---------------------------------------------------------
# NODE 1: RECEIVE VALIDATED JOB
# ---------------------------------------------------------

def receive_validated_job_node(
    state: PlanningGraphState,
) -> Dict[str, Any]:
    """Read the validated job requirement from Intake."""

    job_req = state.get("job_requirement") or {}

    coordinates = get_coordinates_for_location(
        job_req.get("site_latitude"),
        job_req.get("site_longitude"),
        job_req.get("location"),
    )

    return {
        "customer_coordinates": coordinates,
        "eligible_organizations": [],
        "all_eligible_technicians": [],
        "all_ranked_technicians": [],
        "top_3": [],
        "total_eligible_technicians": 0,
    }


# ---------------------------------------------------------
# NODE 2: FIND ORGANIZATIONS
# ---------------------------------------------------------

def find_nearest_organizations_node(
    state: PlanningGraphState,
) -> Dict[str, Any]:
    """
    Find active organizations with coordinates and at least
    one technician matching the job skill.

    Technician status and workload do not affect eligibility.
    """

    job_req = state.get("job_requirement") or {}

    required_skill = (
        job_req.get("required_skill")
        or job_req.get("service")
        or job_req.get("service_type")
        or ""
    )
    service = (
        job_req.get("service")
        or job_req.get("service_type")
        or ""
    )

    customer_coords = (
        state.get("customer_coordinates")
        or DEFAULT_CUSTOMER_COORDINATES
    )

    db, own_db = get_database(state)

    try:
        organizations = (
            db.query(Organization)
            .filter(
                Organization.site_latitude.isnot(None),
                Organization.site_longitude.isnot(None),
                Organization.deleted_at.is_(None),
            )
            .all()
        )

        eligible_organizations = []

        for org in organizations:
            technicians = (
                db.query(Technician)
                .filter(
                    Technician.tenant_id == org.id,
                    Technician.technician_skill.isnot(None),
                )
                .all()
            )

            # Do not filter on technician_status or current_jobs.
            matching_technicians = [
                tech
                for tech in technicians
                if technician_has_required_skill(
                    tech.technician_skill,
                    required_skill,
                    service,
                )
            ]

            logger.info(
                "PLANNING ORGANIZATION CHECK | "
                "job_id=%s | org_id=%s | org_name=%s | "
                "technicians=%s | skill_matches=%s",
                state.get("job_id"),
                org.id,
                org.name,
                len(technicians),
                len(matching_technicians),
            )

            if not matching_technicians:
                continue

            try:
                org_lat = float(org.site_latitude)
                org_lng = float(org.site_longitude)

                distance = float(
                    haversine_distance(
                        customer_coords[0],
                        customer_coords[1],
                        org_lat,
                        org_lng,
                    )
                )
            except (TypeError, ValueError):
                logger.warning(
                    "Skipping organization with invalid coordinates: %s",
                    org.id,
                )
                continue

            eligible_organizations.append(
                {
                    "id": org.id,
                    "name": org.name,
                    "site_latitude": org_lat,
                    "site_longitude": org_lng,
                    "distance_km": round(distance, 2),
                }
            )

        eligible_organizations.sort(
            key=lambda org: org["distance_km"]
        )

        logger.info(
            "PLANNING ORGANIZATIONS COMPLETE | "
            "job_id=%s | eligible_organizations=%s",
            state.get("job_id"),
            len(eligible_organizations),
        )

        return {
            "eligible_organizations": eligible_organizations,
        }

    finally:
        if own_db:
            db.close()


# ---------------------------------------------------------
# NODE 3: FIND AND RANK TECHNICIANS
# ---------------------------------------------------------

def find_and_rank_technicians_node(
    state: PlanningGraphState,
) -> Dict[str, Any]:
    """
    Rank technicians by organization distance first, then
    technician distance within each organization.

    Eligibility:
    - Required skill must match.
    - Previously attempted technician IDs are excluded.

    Intentionally NOT used as eligibility filters:
    - AVAILABLE / BUSY / OFFLINE status.
    - current_jobs workload.
    """

    job_req = state.get("job_requirement") or {}

    required_skill = (
        job_req.get("required_skill")
        or job_req.get("service")
        or job_req.get("service_type")
        or ""
    )
    service = (
        job_req.get("service")
        or job_req.get("service_type")
        or ""
    )

    customer_coords = (
        state.get("customer_coordinates")
        or DEFAULT_CUSTOMER_COORDINATES
    )

    organizations = state.get("eligible_organizations") or []
    excluded_ids = normalize_ids(
        state.get("excluded_technician_ids")
    )

    db, own_db = get_database(state)

    try:
        all_ranked: List[Dict[str, Any]] = []

        logger.info(
            "PLANNING FILTERS | job_id=%s | skill=%s | "
            "status_filter=DISABLED | workload_filter=DISABLED | "
            "excluded_ids=%s | organizations=%s",
            state.get("job_id"),
            required_skill,
            sorted(excluded_ids),
            len(organizations),
        )

        for org in organizations:
            org_id = org["id"]
            org_name = org["name"]
            org_distance = float(org["distance_km"])

            # Fetch technicians without a status or workload filter.
            technicians = (
                db.query(Technician)
                .filter(Technician.tenant_id == org_id)
                .all()
            )

            eligible_for_org = []

            excluded_count = 0
            invalid_id_count = 0
            skill_rejected_count = 0

            for tech in technicians:
                try:
                    technician_id = int(tech.technician_id)
                except (TypeError, ValueError):
                    invalid_id_count += 1
                    continue

                if technician_id in excluded_ids:
                    excluded_count += 1
                    continue

                if not technician_has_required_skill(
                    tech.technician_skill,
                    required_skill,
                    service,
                ):
                    skill_rejected_count += 1
                    continue

                workload = (
                    tech.current_jobs
                    if tech.current_jobs is not None
                    else 0
                )

                # Resolve technician GPS coordinates.
                tech_lat = tech.latitude
                tech_lng = tech.longitude

                if (
                    (tech_lat is None or tech_lng is None)
                    and tech.technician_location
                ):
                    location_parts = (
                        tech.technician_location.split(",")
                    )

                    if len(location_parts) == 2:
                        try:
                            tech_lat = float(
                                location_parts[0].strip()
                            )
                            tech_lng = float(
                                location_parts[1].strip()
                            )
                        except (TypeError, ValueError):
                            tech_lat = None
                            tech_lng = None

                # Fall back to the organization's coordinates
                # when technician GPS coordinates are missing.
                if tech_lat is not None and tech_lng is not None:
                    try:
                        tech_lat = float(tech_lat)
                        tech_lng = float(tech_lng)

                        if not (
                            -90 <= tech_lat <= 90
                            and -180 <= tech_lng <= 180
                        ):
                            raise ValueError("Invalid GPS coordinates")

                        distance = float(
                            haversine_distance(
                                customer_coords[0],
                                customer_coords[1],
                                tech_lat,
                                tech_lng,
                            )
                        )
                    except (TypeError, ValueError):
                        distance = org_distance
                else:
                    distance = org_distance

                distance = max(0.0, distance)

                # Approximate ETA: average urban speed of 30 km/h.
                estimated_eta = int(round(distance * 2))

                eligible_for_org.append(
                    {
                        "technician_id": technician_id,
                        "technician_name": (
                            tech.technician_name
                            or f"Technician {technician_id}"
                        ),
                        "organization_id": org_id,
                        "organization_name": org_name,
                        "technician_status": (
                            tech.technician_status
                        ),
                        "confidence": 1.0,
                        "estimated_eta": estimated_eta,
                        "organization_distance": org_distance,
                        "technician_distance": distance,
                        "distance_km": round(distance, 2),
                        "workload": workload,
                    }
                )

            logger.info(
                "PLANNING FILTER RESULTS | job_id=%s | "
                "org_id=%s | fetched=%s | eligible=%s | "
                "excluded_attempted=%s | invalid_id=%s | "
                "skill_rejected=%s",
                state.get("job_id"),
                org_id,
                len(technicians),
                len(eligible_for_org),
                excluded_count,
                invalid_id_count,
                skill_rejected_count,
            )

            # Rank technicians within this organization by distance.
            eligible_for_org.sort(
                key=lambda tech: tech["distance_km"]
            )

            # Keep the organization-first ranking strategy.
            all_ranked.extend(eligible_for_org)

        # Assign sequential ranks across all organizations.
        for rank, technician in enumerate(all_ranked, start=1):
            technician["rank"] = rank

        logger.info(
            "PLANNING RANKING COMPLETE | job_id=%s | "
            "eligible_count=%s | ranked_ids=%s",
            state.get("job_id"),
            len(all_ranked),
            [
                tech["technician_id"]
                for tech in all_ranked
            ],
        )

        return {
            "all_eligible_technicians": all_ranked,
            "all_ranked_technicians": all_ranked,
            "total_eligible_technicians": len(all_ranked),
        }

    finally:
        if own_db:
            db.close()


# ---------------------------------------------------------
# NODE 4: SELECT TOP THREE
# ---------------------------------------------------------

def select_top_3_node(
    state: PlanningGraphState,
) -> Dict[str, Any]:
    """Select the first three technicians from the ranking."""

    all_eligible = (
        state.get("all_ranked_technicians")
        or state.get("all_eligible_technicians")
        or []
    )

    return {
        "top_3": all_eligible[:3],
    }


# ---------------------------------------------------------
# NODE 5: BUILD RESPONSE
# ---------------------------------------------------------

def build_planning_response_node(
    state: PlanningGraphState,
) -> Dict[str, Any]:
    """Build the planning response while preserving the full ranking."""

    job_req = state.get("job_requirement") or {}

    job_id = state.get("job_id") or job_req.get("job_id")

    if job_id is not None:
        try:
            job_id = int(job_id)
        except (TypeError, ValueError):
            pass

    all_ranked = (
        state.get("all_ranked_technicians")
        or state.get("all_eligible_technicians")
        or []
    )

    top_3 = state.get("top_3") or all_ranked[:3]

    total_count = state.get(
        "total_eligible_technicians",
        len(all_ranked),
    )

    response = {
        "job_id": job_id,
        "total_eligible_technicians": total_count,
        "top_3": top_3,
        "all_ranked_technicians": all_ranked,
    }

    return {
        "job_id": job_id,
        "top_3": top_3,
        "top_3_technicians": top_3,
        "all_eligible_technicians": all_ranked,
        "all_ranked_technicians": all_ranked,
        "all_candidates": all_ranked,
        "total_eligible_technicians": total_count,
        "planning_response": response,
    }


# ---------------------------------------------------------
# GRAPH BUILDER
# ---------------------------------------------------------

def build_planning_graph():
    """Compile the FieldOps Planning LangGraph workflow."""

    builder = StateGraph(PlanningGraphState)

    builder.add_node(
        "receive_validated_job",
        receive_validated_job_node,
    )
    builder.add_node(
        "find_nearest_organizations",
        find_nearest_organizations_node,
    )
    builder.add_node(
        "find_and_rank_technicians",
        find_and_rank_technicians_node,
    )
    builder.add_node(
        "select_top_3",
        select_top_3_node,
    )
    builder.add_node(
        "build_planning_response",
        build_planning_response_node,
    )

    builder.add_edge(START, "receive_validated_job")
    builder.add_edge(
        "receive_validated_job",
        "find_nearest_organizations",
    )
    builder.add_edge(
        "find_nearest_organizations",
        "find_and_rank_technicians",
    )
    builder.add_edge(
        "find_and_rank_technicians",
        "select_top_3",
    )
    builder.add_edge(
        "select_top_3",
        "build_planning_response",
    )
    builder.add_edge("build_planning_response", END)

    return builder.compile()


# Precompiled planning graph instance.
planning_graph = build_planning_graph()
