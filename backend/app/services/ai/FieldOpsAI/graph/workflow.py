"""
workflow.py

Unified FieldOps workflow coordinating Intake Agent (LangGraph)
and Planning Agent (LangGraph).
Includes terminal logging formatting matching the exact project specification.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from app.services.ai.FieldOpsAI.graph.intake_graph import intake_graph
from app.services.ai.FieldOpsAI.graph.planning_graph import planning_graph


def format_terminal_log_block(title: str, subtitle: Optional[str] = None, data: Any = None) -> str:
    """Format standard terminal logging block."""
    lines = []
    lines.append("=" * 50)
    lines.append(title)
    lines.append("=" * len(title))
    if subtitle:
        lines.append("")
        lines.append(f"{subtitle}:")
    if data is not None:
        if isinstance(data, (dict, list)):
            lines.append(json.dumps(data, indent=2, default=str))
        else:
            lines.append(str(data))
    lines.append("")
    return "\n".join(lines)


def log_intake_io(input_data: Dict[str, Any], output_data: Dict[str, Any]) -> None:
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


def log_planning_io(input_data: Dict[str, Any], output_data: Dict[str, Any]) -> None:
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
    """Print Planning TOP 3 recommendations."""
    print("=" * 50)
    print("PLANNING TOP 3")
    print("==============")
    if job_id is not None:
        print(f"Job ID: {job_id}")
    if total_eligible_technicians is not None:
        print(f"Total Eligible Technicians: {total_eligible_technicians}")
    print("")
    if not top_3_technicians:
        print("No eligible technicians found.")
    else:
        for tech in top_3_technicians:
            print(f"Rank {tech.get('rank', 1)}:")
            tech_id = tech.get("technician_id")
            tech_name = tech.get("technician_name") or tech_id
            if tech_id is not None and tech_name and str(tech_name) != str(tech_id):
                print(f"Technician: {tech_name} (ID: {tech_id})")
            elif tech_name:
                print(f"Technician: {tech_name}")
            elif tech_id is not None:
                print(f"Technician: ID {tech_id}")
            print(f"Organization: {tech.get('organization_name')} (ID: {tech.get('organization_id')})")
            if tech.get("organization_distance") is not None:
                print(f"Organization Distance: {tech.get('organization_distance')} km")
            if tech.get("technician_distance") is not None:
                print(f"Technician Distance: {tech.get('technician_distance')} km")
            elif tech.get("distance_km") is not None:
                print(f"Distance: {tech.get('distance_km')} km")
            if tech.get("confidence") is not None:
                print(f"Confidence: {tech.get('confidence')}")
            if tech.get("estimated_eta") is not None:
                print(f"Estimated ETA: {tech.get('estimated_eta')} mins")
            print(f"Workload: {tech.get('workload', 0)}")
            print("")
    print("=" * 50)


def execute_fieldops_workflow(
    request_data: Dict[str, Any],
    db: Any = None,
    job_id: Optional[str | int] = None,
) -> Dict[str, Any]:
    """
    Executes the automated FieldOps workflow end-to-end:
    
    Customer Request
      ↓
    Intake Agent (LangGraph)
      ↓
    VALID?
    ┌────┴────┐
    NO        YES
    ↓          ↓
    Error       Validated Job Requirement
    Response       ↓
                Planning Agent (LangGraph)
                   ↓
                Eligible Technicians
                   ↓
                Organization & Distance Ranking
                   ↓
                Total Count + TOP 3 Technicians
    """
    # ─────────────────────────────────────────────────────────
    # 1. INTAKE AGENT (LangGraph)
    # ─────────────────────────────────────────────────────────
    intake_input = {"raw_request": request_data}
    intake_result = intake_graph.invoke(intake_input)

    is_valid = intake_result.get("valid", False)

    if not is_valid:
        intake_output = {
            "valid": False,
            "error_type": intake_result.get("error_type", "unclear"),
            "field": intake_result.get("field", "service"),
            "message": intake_result.get("message", "Validation failed."),
        }
        if intake_result.get("detected_value") is not None:
            intake_output["detected_value"] = intake_result.get("detected_value")
        if intake_result.get("expected_value") is not None:
            intake_output["expected_value"] = intake_result.get("expected_value")

        # Terminal logging for failed Intake
        log_intake_io(request_data, intake_output)

        # HARD REQUIREMENT: Planning Agent MUST NOT execute if Intake is invalid
        return intake_output

    # Valid Intake outcome
    job_requirement = intake_result.get("job_requirement") or {}

    # Resolve concrete integer job_id (never generic JOB-AUTO)
    if job_id is None:
        if db is not None:
            try:
                from app.models import Job
                from sqlalchemy import func
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

    # Terminal logging for valid Intake
    log_intake_io(request_data, intake_output)

    # ─────────────────────────────────────────────────────────
    # 2. PLANNING AGENT (LangGraph)
    # ─────────────────────────────────────────────────────────
    # Planning Agent receives ONLY the validated job requirement from Intake
    planning_input = {
        "job_requirement": job_requirement,
        "db": db,
        "job_id": job_id,
    }

    planning_state = planning_graph.invoke(planning_input)
    top_3_list = planning_state.get("top_3") or []

    planning_response = planning_state.get("planning_response") or {
        "job_id": job_id,
        "total_eligible_technicians": planning_state.get("total_eligible_technicians", 0),
        "top_3": top_3_list,
    }

    # Terminal logging for Planning Agent
    log_planning_io(job_requirement, planning_response)
    log_planning_top_3(top_3_list, job_id=job_id, total_eligible_technicians=planning_response.get("total_eligible_technicians"))

    return {
        "valid": True,
        "job_requirement": job_requirement,
        "planning": planning_response,
    }

