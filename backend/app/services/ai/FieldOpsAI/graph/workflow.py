
"""
workflow.py

Unified FieldOps workflow coordinating Intake Agent (LangGraph)
and Planning Agent (LangGraph).

Includes terminal logging for Intake and Planning Agent inputs
and outputs, preserving both the top-three recommendations and
the complete ranked technician list.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from app.services.ai.FieldOpsAI.graph.intake_graph import intake_graph
from app.services.ai.FieldOpsAI.graph.planning_graph import planning_graph


def format_terminal_log_block(
    title: str,
    subtitle: Optional[str] = None,
    data: Any = None,
) -> str:
    """Format a standard terminal logging block."""
    lines = [
        "=" * 50,
        title,
        "=" * len(title),
    ]

    if subtitle:
        lines.extend(["", f"{subtitle}:"])

    if data is not None:
        if isinstance(data, (dict, list)):
            lines.append(json.dumps(data, indent=2, default=str))
        else:
            lines.append(str(data))

    lines.append("")
    return "\n".join(lines)


def log_intake_io(
    input_data: Dict[str, Any],
    output_data: Dict[str, Any],
) -> None:
    """Print Intake Agent terminal logging."""
    print("=" * 50)
    print("INTAKE AGENT")
    print("============")
    print("")
    print("INPUT:")
    print(json.dumps(input_data, indent=2, default=str))
    print("")
    print("OUTPUT:")
    print(json.dumps(output_data, indent=2, default=str))
    print("")


def log_planning_io(
    input_data: Dict[str, Any],
    output_data: Dict[str, Any],
) -> None:
    """Print Planning Agent terminal logging."""
    print("=" * 50)
    print("PLANNING AGENT")
    print("==============")
    print("")
    print("INPUT:")
    print(json.dumps(input_data, indent=2, default=str))
    print("")
    print("OUTPUT:")
    print(json.dumps(output_data, indent=2, default=str))
    print("")


def log_planning_top_3(
    top_3_technicians: list[dict[str, Any]],
    job_id: Optional[str | int] = None,
    total_eligible_technicians: Optional[int] = None,
) -> None:
    """Print the top-three Planning Agent recommendations."""
    print("=" * 50)
    print("PLANNING TOP 3")
    print("==============")

    if job_id is not None:
        print(f"Job ID: {job_id}")

    if total_eligible_technicians is not None:
        print(
            "Total Eligible Technicians: "
            f"{total_eligible_technicians}"
        )

    print("")

    if not top_3_technicians:
        print("No eligible technicians found.")
    else:
        for tech in top_3_technicians:
            print(f"Rank {tech.get('rank', 1)}:")

            tech_id = tech.get("technician_id")
            tech_name = tech.get("technician_name") or tech_id

            if (
                tech_id is not None
                and tech_name
                and str(tech_name) != str(tech_id)
            ):
                print(
                    f"Technician: {tech_name} "
                    f"(ID: {tech_id})"
                )
            elif tech_name:
                print(f"Technician: {tech_name}")
            elif tech_id is not None:
                print(f"Technician: ID {tech_id}")

            print(
                f"Organization: {tech.get('organization_name')} "
                f"(ID: {tech.get('organization_id')})"
            )

            if tech.get("organization_distance") is not None:
                print(
                    "Organization Distance: "
                    f"{tech.get('organization_distance')} km"
                )

            if tech.get("technician_distance") is not None:
                print(
                    "Technician Distance: "
                    f"{tech.get('technician_distance')} km"
                )
            elif tech.get("distance_km") is not None:
                print(f"Distance: {tech.get('distance_km')} km")

            if tech.get("confidence") is not None:
                print(f"Confidence: {tech.get('confidence')}")

            if tech.get("estimated_eta") is not None:
                print(
                    f"Estimated ETA: {tech.get('estimated_eta')} mins"
                )

            print(f"Workload: {tech.get('workload', 0)}")
            print("")

    print("=" * 50)


def log_all_ranked_technicians(
    all_ranked_technicians: list[dict[str, Any]],
    job_id: Optional[str | int] = None,
) -> None:
    """Print every technician in the complete ranked list."""
    print("=" * 50)
    print("ALL RANKED TECHNICIANS")
    print("======================")

    if job_id is not None:
        print(f"Job ID: {job_id}")

    print(f"Total Ranked: {len(all_ranked_technicians)}")
    print("")

    if not all_ranked_technicians:
        print("No eligible technicians found.")
    else:
        for tech in all_ranked_technicians:
            print(
                f"Rank {tech.get('rank')} | "
                f"Technician ID: {tech.get('technician_id')} | "
                f"Name: {tech.get('technician_name', 'N/A')} | "
                f"Organization: "
                f"{tech.get('organization_name', 'N/A')} | "
                f"Distance: "
                f"{tech.get('technician_distance', tech.get('distance_km', 'N/A'))} | "
                f"ETA: {tech.get('estimated_eta', 'N/A')} mins | "
                f"Workload: {tech.get('workload', 'N/A')}"
            )

    print("=" * 50)


def execute_fieldops_workflow(
    request_data: Dict[str, Any],
    db: Any = None,
    job_id: Optional[str | int] = None,
) -> Dict[str, Any]:
    """
    Execute the FieldOps workflow end-to-end.

    Flow:
        Customer Request
            |
        Intake Agent
            |
        Validate Request
            |
        Planning Agent
            |
        Rank Eligible Technicians
            |
        Return Top Three and Complete Ranking
    """

    # ---------------------------------------------------------
    # 1. INTAKE AGENT
    # ---------------------------------------------------------
    intake_input = {"raw_request": request_data}
    intake_result = intake_graph.invoke(intake_input)

    is_valid = intake_result.get("valid", False)

    if not is_valid:
        intake_output = {
            "valid": False,
            "error_type": intake_result.get(
                "error_type",
                "unclear",
            ),
            "field": intake_result.get("field", "service"),
            "message": intake_result.get(
                "message",
                "Validation failed.",
            ),
        }

        if intake_result.get("detected_value") is not None:
            intake_output["detected_value"] = (
                intake_result.get("detected_value")
            )

        if intake_result.get("expected_value") is not None:
            intake_output["expected_value"] = (
                intake_result.get("expected_value")
            )

        log_intake_io(request_data, intake_output)

        # Planning must not execute when Intake validation fails.
        return intake_output

    # ---------------------------------------------------------
    # 2. PREPARE VALIDATED JOB
    # ---------------------------------------------------------
    job_requirement = (
        intake_result.get("job_requirement") or {}
    )

    if job_id is None:
        if db is not None:
            try:
                from sqlalchemy import func
                from app.models import Job

                max_id = db.query(func.max(Job.id)).scalar()
                job_id = (max_id or 100) + 1

            except Exception:
                job_id = 101
        else:
            job_id = 101
    else:
        try:
            job_id = int(job_id)
        except (ValueError, TypeError):
            pass

    job_requirement["job_id"] = job_id

    intake_output = {
        "valid": True,
        "job_requirement": job_requirement,
    }

    log_intake_io(request_data, intake_output)

    # ---------------------------------------------------------
    # 3. PLANNING AGENT
    # ---------------------------------------------------------
    planning_input = {
        "job_requirement": job_requirement,
        "db": db,
        "job_id": job_id,
    }

    planning_state = planning_graph.invoke(planning_input)

    # ---------------------------------------------------------
    # 4. EXTRACT TOP THREE AND COMPLETE RANKING
    # ---------------------------------------------------------
    top_3_list = planning_state.get("top_3") or []

    # The graph's all_eligible_technicians field contains the
    # complete list produced by find_and_rank_technicians_node.
    all_ranked_list = (
        planning_state.get("all_ranked_technicians")
        or planning_state.get("all_eligible_technicians")
        or planning_state.get("all_candidates")
        or top_3_list
    )

    # Use the full ranking to derive the top three if the graph
    # did not explicitly populate its top_3 field.
    if not top_3_list and all_ranked_list:
        top_3_list = all_ranked_list[:3]

    total_eligible = planning_state.get(
        "total_eligible_technicians",
        len(all_ranked_list),
    )

    # Preserve fields already produced by the Planning graph,
    # while ensuring its ranking fields contain the full list.
    existing_response = planning_state.get("planning_response") or {}

    planning_response = dict(existing_response)

    planning_response.update({
        "job_id": job_id,
        "total_eligible_technicians": total_eligible,
        "top_3": top_3_list,
        "all_ranked_technicians": all_ranked_list,
    })

    # ---------------------------------------------------------
    # 5. TERMINAL LOGGING
    # ---------------------------------------------------------
    log_planning_io(
        job_requirement,
        planning_response,
    )

    log_planning_top_3(
        top_3_list,
        job_id=job_id,
        total_eligible_technicians=total_eligible,
    )

    log_all_ranked_technicians(
        all_ranked_list,
        job_id=job_id,
    )

    # ---------------------------------------------------------
    # 6. FINAL RESPONSE
    # ---------------------------------------------------------
    return {
        "valid": True,
        "job_requirement": job_requirement,
        "planning": planning_response,
    }