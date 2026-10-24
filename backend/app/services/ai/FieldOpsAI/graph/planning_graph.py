
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


def check_skill_match_level(
    technician_skills: Any,
    required_skill: Any,
    service: Any = None,
    category: Any = None,
    issue: Any = None,
) -> int:
    """
    Computes taxonomy match level for a technician:
      3 = Full match: Matches service AND category (title) AND issue
      2 = Partial match: Matches service AND category (or issue)
      1 = Base match: Matches service or required_skill
      0 = No match
    """
    if not technician_skills:
        return 0

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

    if not normalized_skills:
        return 0

    # 1. Base Service / Trade match
    service_reqs = {
        normalize_skill(required_skill),
        normalize_skill(service),
    }
    service_reqs.discard("")

    service_matched = False
    for req in service_reqs:
        for s in normalized_skills:
            if req == s:
                service_matched = True
                break
            if len(req) >= 3 and re.search(rf"(?<![a-z0-9]){re.escape(req)}(?![a-z0-9])", s):
                service_matched = True
                break
            if len(s) >= 3 and re.search(rf"(?<![a-z0-9]){re.escape(s)}(?![a-z0-9])", req):
                service_matched = True
                break
        if service_matched:
            break

    if not service_matched:
        return 0

    # 2. Check Category and Issue
    def matches_target(target: Any) -> bool:
        if not target:
            return False
        norm = normalize_skill(target)
        if not norm:
            return False
        for s in normalized_skills:
            if norm == s:
                return True
            if len(norm) >= 3 and re.search(rf"(?<![a-z0-9]){re.escape(norm)}(?![a-z0-9])", s):
                return True
            if len(s) >= 3 and re.search(rf"(?<![a-z0-9]){re.escape(s)}(?![a-z0-9])", norm):
                return True
        return False

    has_cat = matches_target(category) if category else False
    has_issue = matches_target(issue) if issue else False

    if category and issue:
        if has_cat and has_issue:
            return 3
        elif has_cat or has_issue:
            return 2
        else:
            return 1
    elif category:
        return 3 if has_cat else 1
    elif issue:
        return 3 if has_issue else 1
    return 1


def technician_has_required_skill(
    technician_skills: Any,
    required_skill: Any,
    service: Any = None,
    category: Any = None,
    issue: Any = None,
    min_match_level: int = 1,
) -> bool:
    """Check if technician meets the required skill / taxonomy level."""
    level = check_skill_match_level(
        technician_skills,
        required_skill,
        service,
        category,
        issue,
    )
    return level >= min_match_level


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
    category = job_req.get("category") or job_req.get("title") or ""
    issue = job_req.get("issue") or ""
    if not issue and job_req.get("description"):
        parts = str(job_req["description"]).split(" - ")
        if len(parts) >= 2 and parts[0].strip():
            issue = parts[0].strip()

    customer_coords = (
        state.get("customer_coordinates")
        or DEFAULT_CUSTOMER_COORDINATES
    )

    db, own_db = get_database(state)

    try:
        from collections import defaultdict

        # Fetch all candidate technicians across active organizations in a single query
        all_candidate_techs = (
            db.query(Technician)
            .join(Organization, Organization.id == Technician.tenant_id)
            .filter(
                Organization.site_latitude.isnot(None),
                Organization.site_longitude.isnot(None),
                Organization.deleted_at.is_(None),
                Technician.technician_skill.isnot(None),
            )
            .all()
        )

        techs_by_org = defaultdict(list)
        for t in all_candidate_techs:
            techs_by_org[t.tenant_id].append(t)

        candidate_org_ids = list(techs_by_org.keys())

        # Query only organizations that actually employ candidate technicians
        organizations = (
            db.query(Organization)
            .filter(
                Organization.id.in_(candidate_org_ids),
                Organization.site_latitude.isnot(None),
                Organization.site_longitude.isnot(None),
                Organization.deleted_at.is_(None),
            )
            .all()
            if candidate_org_ids
            else []
        )

        scores = [
            check_skill_match_level(t.technician_skill, required_skill, service, category, issue)
            for t in all_candidate_techs
        ]
        max_level = max(scores, default=0)
        min_level_needed = max(1, max_level)

        logger.info(
            "PLANNING TAXONOMY SCAN | job_id=%s | category=%s | issue=%s | max_level_found=%s",
            state.get("job_id"),
            category,
            issue,
            max_level,
        )

        eligible_organizations = []

        for org in organizations:
            # Use in-memory grouping instead of N+1 database queries
            technicians = techs_by_org.get(org.id, [])

            # Match only technicians meeting the required taxonomy depth (e.g. Level 3 when title/category/issue match exists)
            matching_technicians = [
                tech
                for tech in technicians
                if check_skill_match_level(
                    tech.technician_skill,
                    required_skill,
                    service,
                    category,
                    issue,
                ) >= min_level_needed
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
            "required_match_level": min_level_needed,
            "taxonomy_category": category,
            "taxonomy_issue": issue,
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
    min_level_needed = state.get("required_match_level", 1)
    taxonomy_category = state.get("taxonomy_category") or job_req.get("category") or job_req.get("title") or ""
    taxonomy_issue = state.get("taxonomy_issue") or job_req.get("issue") or ""
    if not taxonomy_issue and job_req.get("description"):
        parts = str(job_req["description"]).split(" - ")
        if len(parts) >= 2 and parts[0].strip():
            taxonomy_issue = parts[0].strip()

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

                match_lvl = check_skill_match_level(
                    tech.technician_skill,
                    required_skill,
                    service,
                    taxonomy_category,
                    taxonomy_issue,
                )
                if match_lvl < min_level_needed:
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
                        "technician_skill": tech.technician_skill,
                        "match_level": match_lvl,
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

            # Rank technicians within this organization by taxonomy match level then distance.
            eligible_for_org.sort(
                key=lambda tech: (-tech.get("match_level", 1), tech["distance_km"])
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
