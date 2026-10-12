
# """

# planning_graph.py

# LangGraph workflow for the FieldOps Planning Agent.
# Finds eligible technicians across organizations and performs deterministic ranking
# based on organization proximity and technician distance.
# """

# from __future__ import annotations

# from typing import Any, Dict, List, Optional, Tuple
# import logging

# from langgraph.graph import StateGraph, START, END
# from sqlalchemy import func

# from app.database import SessionLocal
# from app.models import Organization, Technician
# from app.services.ola_map_client import haversine_distance
# from app.utils import is_skill_matching
# from app.services.ai.FieldOpsAI.graph.state import (
#     PlanningGraphState,
#     TopTechnicianRecommendation,
#     ValidatedJobRequirement,
# )


# def get_coordinates_for_location(
#     site_lat: Optional[float],
#     site_lng: Optional[float],
#     location_str: Optional[str] = None,
# ) -> Tuple[float, float]:
#     """
#     Resolve coordinates from explicit latitude/longitude or a coordinate string.
#     Defaults to Chennai central coordinates if coordinates are unavailable.
#     """
#     if site_lat is not None and site_lng is not None:
#         try:
#             return float(site_lat), float(site_lng)
#         except (ValueError, TypeError):
#             pass

#     if location_str and "," in location_str:
#         parts = location_str.split(",")
#         if len(parts) == 2:
#             try:
#                 return float(parts[0].strip()), float(parts[1].strip())
#             except (ValueError, TypeError):
#                 pass

#     return 13.0827, 80.2707


# def _normalize_ids(values: List[Any] | None) -> set[int]:
#     """Convert ID values to integers, ignoring invalid values."""
#     normalized: set[int] = set()

#     for value in values or []:
#         try:
#             normalized.add(int(value))
#         except (TypeError, ValueError):
#             continue

#     return normalized


# def receive_validated_job_node(
#     state: PlanningGraphState,
# ) -> Dict[str, Any]:
#     """
#     Node 1: receive the validated job requirement produced by Intake.
#     """
#     job_req = state.get("job_requirement") or {}

#     cust_coords = get_coordinates_for_location(
#         job_req.get("site_latitude"),
#         job_req.get("site_longitude"),
#         job_req.get("location"),
#     )

#     return {
#         "customer_coordinates": cust_coords,
#         "eligible_organizations": [],
#         "all_eligible_technicians": [],
#         "all_ranked_technicians": [],
#         "top_3": [],
#         "total_eligible_technicians": 0,
#     }


# def find_nearest_organizations_node(
#     state: PlanningGraphState,
# ) -> Dict[str, Any]:
#     """
#     Node 2: find active organizations with at least one currently eligible
#     technician, then sort organizations by distance to the customer.

#     Eligibility here matches the ranking node: available status, required
#     skill, workload below 5, and not previously attempted.
#     """
#     job_req = state.get("job_requirement") or {}
#     req_skill = job_req.get("required_skill") or job_req.get("service") or ""
#     cust_coords = state.get("customer_coordinates") or (13.0827, 80.2707)
#     excluded_ids = _normalize_ids(state.get("excluded_technician_ids"))

#     db = state.get("db")
#     own_db = False

#     if db is None:
#         db = SessionLocal()
#         own_db = True

#     try:
#         orgs = (
#             db.query(Organization)
#             .filter(
#                 Organization.site_latitude.isnot(None),
#                 Organization.site_longitude.isnot(None),
#                 Organization.deleted_at.is_(None),
#             )
#             .all()
#         )

#         org_list = []

#         for org in orgs:
#             techs = (
#                 db.query(Technician)
#                 .filter(
#                     Technician.tenant_id == org.id,
#                     Technician.technician_skill.isnot(None),
#                     func.upper(Technician.technician_status) == "AVAILABLE",
#                 )
#                 .all()
#             )

#             has_eligible_technician = False

#             for tech in techs:
#                 try:
#                     technician_id = int(tech.technician_id)
#                 except (TypeError, ValueError):
#                     continue

#                 if technician_id in excluded_ids:
#                     continue

#                 if not is_skill_matching(
#                     tech.technician_skill or "",
#                     req_skill,
#                     job_req.get("service", ""),
#                 ):
#                     continue

#                 workload = (
#                     tech.current_jobs
#                     if tech.current_jobs is not None
#                     else 0
#                 )
#                 if workload >= 5:
#                     continue

#                 has_eligible_technician = True
#                 break

#             if not has_eligible_technician:
#                 continue

#             dist_to_cust = haversine_distance(
#                 cust_coords[0],
#                 cust_coords[1],
#                 float(org.site_latitude),
#                 float(org.site_longitude),
#             )

#             org_list.append(
#                 {
#                     "id": org.id,
#                     "name": org.name,
#                     "site_latitude": float(org.site_latitude),
#                     "site_longitude": float(org.site_longitude),
#                     "distance_km": round(float(dist_to_cust), 2),
#                 }
#             )

#         org_list.sort(key=lambda organization: organization["distance_km"])

#         return {"eligible_organizations": org_list}

#     finally:
#         if own_db:
#             db.close()



# def find_and_rank_technicians_node(
#     state: PlanningGraphState,
# ) -> Dict[str, Any]:
#     """
#     Nodes 3 & 4: find eligible technicians and rank them deterministically.

#     - Processes organizations in ascending organization-distance order.
#     - Does not filter by technician availability status.
#     - Excludes technicians attempted in previous dispatch batches.
#     - Requires matching skills and workload below 5.
#     - Sorts technicians within each organization by technician distance.
#     """

#     logger = logging.getLogger(__name__)

#     job_req = state.get("job_requirement") or {}
#     req_skill = (
#         job_req.get("required_skill")
#         or job_req.get("service")
#         or ""
#     )
#     cust_coords = state.get("customer_coordinates") or (
#         13.0827,
#         80.2707,
#     )
#     organizations = state.get("eligible_organizations") or []
#     excluded_ids = _normalize_ids(
#         state.get("excluded_technician_ids")
#     )

#     db = state.get("db")
#     own_db = False

#     if db is None:
#         db = SessionLocal()
#         own_db = True

#     try:
#         all_eligible_ranked: List[
#             TopTechnicianRecommendation
#         ] = []

#         # Log the filters applied before querying technicians.
#         logger.info(
#             "PLANNING TECHNICIAN FILTER | "
#             "job_id=%s | organization_count=%s | "
#             "required_skill=%s | excluded_ids=%s | "
#             "availability_status_filter=DISABLED | "
#             "workload_limit=5",
#             state.get("job_id"),
#             len(organizations),
#             req_skill,
#             sorted(excluded_ids),
#         )

#         for org in organizations:
#             org_id = org["id"]
#             org_name = org["name"]
#             org_dist = float(org["distance_km"])

#             # Intentionally do not filter by technician_status.
#             techs = (
#                 db.query(Technician)
#                 .filter(
#                     Technician.tenant_id == org_id,
#                 )
#                 .all()
#             )

#             logger.info(
#                 "PLANNING ORGANIZATION TECHNICIANS | "
#                 "job_id=%s | organization_id=%s | "
#                 "organization_name=%s | technicians_found=%s",
#                 state.get("job_id"),
#                 org_id,
#                 org_name,
#                 len(techs),
#             )

#             org_eligible_techs = []

#             # Track why technicians are rejected during filtering.
#             excluded_count = 0
#             invalid_id_count = 0
#             skill_rejected_count = 0
#             workload_rejected_count = 0

#             for tech in techs:
#                 try:
#                     technician_id = int(tech.technician_id)
#                 except (TypeError, ValueError):
#                     invalid_id_count += 1
#                     continue

#                 # Never return a technician already attempted
#                 # by Dispatcher.
#                 if technician_id in excluded_ids:
#                     excluded_count += 1
#                     continue

#                 # 1. Skill check.
#                 if not is_skill_matching(
#                     tech.technician_skill or "",
#                     req_skill,
#                     job_req.get("service", ""),
#                 ):
#                     skill_rejected_count += 1
#                     continue

#                 # 2. Workload must be less than 5.
#                 workload = (
#                     tech.current_jobs
#                     if tech.current_jobs is not None
#                     else 0
#                 )

#                 if workload >= 5:
#                     workload_rejected_count += 1
#                     continue

#                 # 3. Resolve technician coordinates.
#                 tech_lat = tech.latitude
#                 tech_lng = tech.longitude

#                 if (
#                     (tech_lat is None or tech_lng is None)
#                     and tech.technician_location
#                     and "," in tech.technician_location
#                 ):
#                     parts = tech.technician_location.split(",")

#                     if len(parts) == 2:
#                         try:
#                             tech_lat = float(parts[0].strip())
#                             tech_lng = float(parts[1].strip())
#                         except (ValueError, TypeError):
#                             pass

#                 # 4. Calculate technician distance to customer.
#                 if tech_lat is not None and tech_lng is not None:
#                     dist_to_cust = haversine_distance(
#                         cust_coords[0],
#                         cust_coords[1],
#                         float(tech_lat),
#                         float(tech_lng),
#                     )
#                 else:
#                     dist_to_cust = org_dist

#                 dist_to_cust = float(dist_to_cust)

#                 estimated_eta_mins = (
#                     max(
#                         0,
#                         int(round((dist_to_cust / 30.0) * 60)),
#                     )
#                     if dist_to_cust > 0
#                     else 0
#                 )

#                 resolved_org_id = (
#                     org_id or getattr(tech, "tenant_id", None)
#                 )

#                 org_eligible_techs.append(
#                     {
#                         "technician_id": technician_id,
#                         "technician_name": tech.technician_name,
#                         "organization_id": resolved_org_id,
#                         "organization_name": org_name,
#                         "confidence": 1.0,
#                         "estimated_eta": estimated_eta_mins,
#                         "organization_distance": org_dist,
#                         "technician_distance": dist_to_cust,
#                         "distance_km": round(dist_to_cust, 2),
#                         "workload": workload,
#                     }
#                 )

#             # Log filter outcomes for this organization.
#             logger.info(
#                 "PLANNING ORGANIZATION FILTER RESULTS | "
#                 "job_id=%s | organization_id=%s | "
#                 "fetched=%s | eligible=%s | "
#                 "excluded_attempted=%s | invalid_id=%s | "
#                 "skill_rejected=%s | workload_rejected=%s",
#                 state.get("job_id"),
#                 org_id,
#                 len(techs),
#                 len(org_eligible_techs),
#                 excluded_count,
#                 invalid_id_count,
#                 skill_rejected_count,
#                 workload_rejected_count,
#             )

#             if not org_eligible_techs:
#                 logger.info(
#                     "PLANNING ORGANIZATION SKIPPED | "
#                     "job_id=%s | organization_id=%s | "
#                     "reason=no_eligible_technicians",
#                     state.get("job_id"),
#                     org_id,
#                 )
#                 continue

#             # Preserve organization-first ranking;
#             # sort technicians within each organization.
#             org_eligible_techs.sort(
#                 key=lambda technician: technician["distance_km"]
#             )

#             all_eligible_ranked.extend(org_eligible_techs)

#         # Re-number ranks after skill, workload and exclusion filtering.
#         for index, technician in enumerate(
#             all_eligible_ranked,
#             start=1,
#         ):
#             technician["rank"] = index

#         logger.info(
#             "PLANNING DETERMINISTIC RANKING | "
#             "job_id=%s | excluded_ids=%s | "
#             "eligible_count=%s | ranked_ids=%s",
#             state.get("job_id"),
#             sorted(excluded_ids),
#             len(all_eligible_ranked),
#             [
#                 technician["technician_id"]
#                 for technician in all_eligible_ranked
#             ],
#         )

#         return {
#             "all_eligible_technicians": all_eligible_ranked,
#             "all_ranked_technicians": all_eligible_ranked,
#             "total_eligible_technicians": len(
#                 all_eligible_ranked
#             ),
#         }

#     finally:
#         if own_db:
#             db.close()



# def select_top_3_node(
#     state: PlanningGraphState,
# ) -> Dict[str, Any]:
#     """
#     Node 5: return up to three technicians from the fresh ranked list.
#     """
#     all_eligible = state.get("all_eligible_technicians") or []

#     return {"top_3": all_eligible[:3]}


# def build_planning_response_node(
#     state: PlanningGraphState,
# ) -> Dict[str, Any]:
#     """
#     Build the planning response while preserving the full ranked list.
#     The UI and Dispatcher can use only the Top 3 for the current batch.
#     """
#     job_req = state.get("job_requirement") or {}
#     job_id = state.get("job_id") or job_req.get("job_id")

#     if not job_id or str(job_id) == "JOB-AUTO":
#         db = state.get("db")
#         if db is not None:
#             try:
#                 from app.models import Job
#                 from sqlalchemy import func as sqlalchemy_func

#                 max_id = db.query(sqlalchemy_func.max(Job.id)).scalar()
#                 job_id = int(max_id or 100) + 1
#             except Exception:
#                 job_id = 101
#         else:
#             job_id = 101
#     else:
#         try:
#             job_id = int(job_id)
#         except (ValueError, TypeError):
#             pass

#     all_ranked = state.get("all_eligible_technicians") or []
#     top_3 = state.get("top_3") or all_ranked[:3]
#     total_count = state.get(
#         "total_eligible_technicians",
#         len(all_ranked),
#     )

#     response = {
#         "job_id": job_id,
#         "total_eligible_technicians": total_count,
#         "top_3": top_3,
#         "all_ranked_technicians": all_ranked,
#     }

#     return {
#         "job_id": job_id,
#         "all_eligible_technicians": all_ranked,
#         "all_ranked_technicians": all_ranked,
#         "total_eligible_technicians": total_count,
#         "top_3": top_3,
#         "top_3_technicians": top_3,
#         "planning_response": response,
#     }


# def build_planning_graph():
#     """Compile and return the deterministic Planning LangGraph workflow."""
#     builder = StateGraph(PlanningGraphState)

#     builder.add_node("receive_validated_job", receive_validated_job_node)
#     builder.add_node("find_nearest_organizations", find_nearest_organizations_node)
#     builder.add_node("find_and_rank_technicians", find_and_rank_technicians_node)
#     builder.add_node("select_top_3", select_top_3_node)
#     builder.add_node("build_planning_response", build_planning_response_node)

#     builder.add_edge(START, "receive_validated_job")
#     builder.add_edge("receive_validated_job", "find_nearest_organizations")
#     builder.add_edge("find_nearest_organizations", "find_and_rank_technicians")
#     builder.add_edge("find_and_rank_technicians", "select_top_3")
#     builder.add_edge("select_top_3", "build_planning_response")
#     builder.add_edge("build_planning_response", END)

#     return builder.compile()


# # Pre-compiled planning graph instance.
# planning_graph = build_planning_graph()


"""
planning_graph.py

LangGraph workflow for the FieldOps Planning Agent.
Finds eligible technicians across organizations and performs deterministic ranking
based on organization proximity and technician distance.
"""

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