"""
planning_graph.py

LangGraph workflow for the FieldOps Planning Agent.
Finds eligible technicians across organizations and performs deterministic ranking
based on organization proximity and technician distance.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from langgraph.graph import StateGraph, START, END

from app.database import SessionLocal
from app.models import Organization, Technician
from app.services.ola_map_client import haversine_distance
from app.utils import is_skill_matching
from app.services.ai.FieldOpsAI.graph.state import (
    PlanningGraphState,
    TopTechnicianRecommendation,
    ValidatedJobRequirement,
)


def get_coordinates_for_location(
    site_lat: Optional[float],
    site_lng: Optional[float],
    location_str: Optional[str] = None,
) -> Tuple[float, float]:
    """
    Resolve coordinates from explicit latitude/longitude or string.
    Defaults to Chennai central coordinates (13.0827, 80.2707) if no coordinates available.
    """
    if site_lat is not None and site_lng is not None:
        try:
            return float(site_lat), float(site_lng)
        except (ValueError, TypeError):
            pass

    if location_str and "," in location_str:
        parts = location_str.split(",")
        if len(parts) == 2:
            try:
                return float(parts[0].strip()), float(parts[1].strip())
            except (ValueError, TypeError):
                pass

    # Default location (Chennai center) if address only
    return 13.0827, 80.2707


# ─────────────────────────────────────────────────────────────
# Graph Nodes
# ─────────────────────────────────────────────────────────────

def receive_validated_job_node(state: PlanningGraphState) -> Dict[str, Any]:
    """
    Node 1: receive_validated_job
    Receives ONLY the validated job requirement produced by the Intake Agent.
    """
    job_req = state.get("job_requirement") or {}
    site_lat = job_req.get("site_latitude")
    site_lng = job_req.get("site_longitude")
    loc_str = job_req.get("location")

    cust_coords = get_coordinates_for_location(site_lat, site_lng, loc_str)

    return {
        "customer_coordinates": cust_coords,
        "eligible_organizations": [],
        "all_eligible_technicians": [],
    }


def find_nearest_organizations_node(state: PlanningGraphState) -> Dict[str, Any]:
    """
    Node 2: find_nearest_organizations
    Finds all active organizations that can handle the required service,
    calculates distance to customer, and sorts them ascending by distance.
    """
    job_req = state.get("job_requirement") or {}
    req_skill = job_req.get("required_skill") or job_req.get("service") or ""
    cust_coords = state.get("customer_coordinates") or (13.0827, 80.2707)

    db = state.get("db")
    own_db = False
    if db is None:
        db = SessionLocal()
        own_db = True

    try:
        # Query active organizations with coordinates
        orgs = (
            db.query(Organization)
            .filter(
                Organization.site_latitude.isnot(None),
                Organization.site_longitude.isnot(None),
                Organization.deleted_at.is_(None),
            )
            .all()
        )

        org_list = []
        for org in orgs:
            # Check if this organization has any technician with the required skill
            techs = (
                db.query(Technician)
                .filter(
                    Technician.tenant_id == org.id,
                    Technician.technician_skill.isnot(None),
                )
                .all()
            )

            has_skill = any(
                is_skill_matching(
                    tech.technician_skill or "",
                    req_skill,
                    job_req.get("service", ""),
                )
                and ((tech.current_jobs if tech.current_jobs is not None else 0) < 5)
                for tech in techs
            )

            if not has_skill:
                continue

            dist_to_cust = haversine_distance(
                cust_coords[0],
                cust_coords[1],
                float(org.site_latitude),
                float(org.site_longitude),
            )

            org_list.append({
                "id": org.id,
                "name": org.name,
                "site_latitude": float(org.site_latitude),
                "site_longitude": float(org.site_longitude),
                "distance_km": round(dist_to_cust, 2),
            })

        # Sort organizations ascending by distance to customer
        org_list.sort(key=lambda o: o["distance_km"])

        return {
            "eligible_organizations": org_list,
        }
    finally:
        if own_db:
            db.close()


def find_and_rank_technicians_node(state: PlanningGraphState) -> Dict[str, Any]:
    """
    Nodes 3 & 4: find_eligible_technicians & rank_technicians
    Iterates organization-by-organization in order of distance.
    Enforces workload < 5 rule.
    Enforces Same-Organization-First ranking rule.
    """
    job_req = state.get("job_requirement") or {}
    req_skill = job_req.get("required_skill") or job_req.get("service") or ""
    cust_coords = state.get("customer_coordinates") or (13.0827, 80.2707)
    organizations = state.get("eligible_organizations") or []

    db = state.get("db")
    own_db = False
    if db is None:
        db = SessionLocal()
        own_db = True

    try:
        all_eligible_ranked: List[TopTechnicianRecommendation] = []

        for org in organizations:
            org_id = org["id"]
            org_name = org["name"]
            org_dist = org["distance_km"]

            # Query technicians in this organization
            techs = (
                db.query(Technician)
                .filter(Technician.tenant_id == org_id)
                .all()
            )

            org_eligible_techs = []
            for tech in techs:
                # 1. Skill check
                if not is_skill_matching(
                    tech.technician_skill or "",
                    req_skill,
                    job_req.get("service", ""),
                ):
                    continue

                # 2. Workload rule: workload MUST be LESS THAN 5 (0,1,2,3,4 eligible; 5+ NOT eligible)
                workload = tech.current_jobs if tech.current_jobs is not None else 0
                if workload >= 5:
                    # Ineligible due to max capacity
                    continue

                # 3. Calculate technician distance to customer
                tech_lat = tech.latitude
                tech_lng = tech.longitude

                # Fallback to technician_location if "lat, lng" string
                if (tech_lat is None or tech_lng is None) and tech.technician_location and "," in tech.technician_location:
                    parts = tech.technician_location.split(",")
                    if len(parts) == 2:
                        try:
                            tech_lat = float(parts[0].strip())
                            tech_lng = float(parts[1].strip())
                        except (ValueError, TypeError):
                            pass

                if tech_lat is not None and tech_lng is not None:
                    dist_to_cust = haversine_distance(
                        cust_coords[0],
                        cust_coords[1],
                        float(tech_lat),
                        float(tech_lng),
                    )
                else:
                    # Fallback to organization distance if technician has no specific coordinates
                    dist_to_cust = org_dist

                dist_to_cust = float(dist_to_cust)
                org_dist_val = float(org_dist)

                # Estimated arrival time in minutes (assuming ~30 km/h average speed in city)
                estimated_eta_mins = max(0, int(round((dist_to_cust / 30.0) * 60))) if dist_to_cust > 0 else 0

                resolved_org_id = org_id or getattr(tech, "tenant_id", None)

                org_eligible_techs.append({
                    "technician_id": int(tech.technician_id) if str(tech.technician_id).isdigit() else tech.technician_id,
                    "technician_name": tech.technician_name,
                    "organization_id": resolved_org_id,
                    "organization_name": org_name,
                    "confidence": 1.0,
                    "estimated_eta": estimated_eta_mins,
                    "organization_distance": org_dist_val,
                    "technician_distance": dist_to_cust,
                    "distance_km": round(dist_to_cust, 2),
                    "workload": workload,
                })

            # If no eligible technician in this organization (e.g. all workload >= 5), move to next org
            if not org_eligible_techs:
                continue

            # STEP 2: SAME ORGANIZATION FIRST
            # Sort all eligible technicians in this organization by distance to customer
            org_eligible_techs.sort(key=lambda t: t["distance_km"])

            # Append all eligible technicians from this organization before moving to next
            for tech_data in org_eligible_techs:
                all_eligible_ranked.append(tech_data)

        # Set final rank number for all evaluated eligible technicians
        for i, t in enumerate(all_eligible_ranked):
            t["rank"] = i + 1

        return {
            "all_eligible_technicians": all_eligible_ranked,
            "total_eligible_technicians": len(all_eligible_ranked),
        }
    finally:
        if own_db:
            db.close()


def select_top_3_node(state: PlanningGraphState) -> Dict[str, Any]:
    """
    Node 5: select_top_3
    Takes at most the top 3 ranked technicians.
    If only 1 or 2 are eligible, returns however many exist.
    """
    all_eligible = state.get("all_eligible_technicians") or []
    top_3 = all_eligible[:3]

    return {
        "top_3": top_3,
    }


def build_planning_response_node(state: PlanningGraphState) -> Dict[str, Any]:
    """
    Node 6: build_planning_response
    Constructs the final Planning Agent response.
    Ensures real job_id is used (never generic JOB-AUTO) and output structure matches Image 3.
    """
    job_req = state.get("job_requirement") or {}
    job_id = state.get("job_id") or job_req.get("job_id")

    if not job_id or str(job_id) == "JOB-AUTO":
        db = state.get("db")
        if db is not None:
            try:
                from app.models import Job
                from sqlalchemy import func
                max_id = db.query(func.max(Job.id)).scalar()
                job_id = int(max_id or 100) + 1
            except Exception:
                job_id = 101
        else:
            job_id = 101
    else:
        try:
            job_id = int(job_id)
        except (ValueError, TypeError):
            pass

    total_count = state.get("total_eligible_technicians", 0)
    top_3 = state.get("top_3") or []

    response = {
        "job_id": job_id,
        "total_eligible_technicians": total_count,
        "top_3": top_3,
    }

    return {
        "job_id": job_id,
        "top_3": top_3,
        "planning_response": response,
    }


# ─────────────────────────────────────────────────────────────
# Graph Builder
# ─────────────────────────────────────────────────────────────

def build_planning_graph():
    """
    Compiles and returns the Planning LangGraph workflow.
    """
    builder = StateGraph(PlanningGraphState)

    builder.add_node("receive_validated_job", receive_validated_job_node)
    builder.add_node("find_nearest_organizations", find_nearest_organizations_node)
    builder.add_node("find_and_rank_technicians", find_and_rank_technicians_node)
    builder.add_node("select_top_3", select_top_3_node)
    builder.add_node("build_planning_response", build_planning_response_node)

    builder.add_edge(START, "receive_validated_job")
    builder.add_edge("receive_validated_job", "find_nearest_organizations")
    builder.add_edge("find_nearest_organizations", "find_and_rank_technicians")
    builder.add_edge("find_and_rank_technicians", "select_top_3")
    builder.add_edge("select_top_3", "build_planning_response")
    builder.add_edge("build_planning_response", END)

    return builder.compile()


# Pre-compiled planning graph instance
planning_graph = build_planning_graph()
