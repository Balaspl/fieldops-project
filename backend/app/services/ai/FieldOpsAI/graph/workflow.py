
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
import importlib
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



def _read_name_from_record(record: Any) -> Optional[str]:
    """Read a technician display name from common dictionary/object fields."""
    name_keys = ("technician_name", "full_name", "fullName", "display_name", "name")

    if isinstance(record, dict):
        for key in name_keys:
            value = record.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()

        first_name = record.get("first_name") or record.get("firstName")
        last_name = record.get("last_name") or record.get("lastName")
        full_name = " ".join(
            str(part).strip()
            for part in (first_name, last_name)
            if part is not None and str(part).strip()
        )
        if full_name:
            return full_name

        nested = record.get("technician") or record.get("technician_details")
        if isinstance(nested, dict):
            return _read_name_from_record(nested)
        if isinstance(nested, str) and nested.strip():
            return nested.strip()
        return None

    for key in name_keys:
        value = getattr(record, key, None)
        if value is not None and str(value).strip():
            return str(value).strip()

    first_name = getattr(record, "first_name", None)
    last_name = getattr(record, "last_name", None)
    full_name = " ".join(
        str(part).strip()
        for part in (first_name, last_name)
        if part is not None and str(part).strip()
    )
    return full_name or None


def _lookup_technician_name_in_db(technician_id: Any, db: Any) -> Optional[str]:
    """Best-effort DB lookup when the planning graph returns only an ID."""
    if db is None or technician_id is None:
        return None

    # Support both current and legacy model modules used by FieldOps.
    for module_name in ("app.models", "app.models_legacy"):
        try:
            module = importlib.import_module(module_name)
            technician_model = getattr(module, "Technician", None)
        except Exception:
            continue

        if technician_model is None:
            continue

        for id_field in ("technician_id", "tech_id", "id"):
            column = getattr(technician_model, id_field, None)
            if column is None:
                continue

            candidate_ids = [technician_id]
            if isinstance(technician_id, str):
                try:
                    candidate_ids.append(int(technician_id))
                except (TypeError, ValueError):
                    pass
            elif isinstance(technician_id, int):
                candidate_ids.append(str(technician_id))

            for candidate_id in candidate_ids:
                try:
                    row = db.query(technician_model).filter(column == candidate_id).first()
                except Exception:
                    continue
                if row is not None:
                    name = _read_name_from_record(row)
                    if name:
                        return name

    return None


def _enrich_technician_names(technicians: Any, db: Any = None) -> list[dict[str, Any]]:
    """Copy ranking records and ensure every technician has a display name."""
    enriched: list[dict[str, Any]] = []
    if not isinstance(technicians, list):
        return enriched

    for index, technician in enumerate(technicians, start=1):
        if isinstance(technician, dict):
            item = dict(technician)
        else:
            item = {
                "technician_id": getattr(technician, "technician_id", None)
                or getattr(technician, "tech_id", None)
                or getattr(technician, "id", None),
            }
            object_name = _read_name_from_record(technician)
            if object_name:
                item["technician_name"] = object_name

        technician_id = item.get("technician_id") or item.get("tech_id") or item.get("id")
        technician_name = _read_name_from_record(item)
        if not technician_name:
            technician_name = _lookup_technician_name_in_db(technician_id, db)

        item["technician_name"] = technician_name or (
            f"Unknown technician (ID: {technician_id})"
            if technician_id is not None
            else "Unknown technician"
        )
        item.setdefault("rank", index)
        enriched.append(item)

    return enriched


def log_dispatcher_handoff(
    top_3_technicians: list[dict[str, Any]],
    job_id: Optional[str | int] = None,
) -> None:
    """Print the top-three recommendations included in the response for Dispatcher."""
    print("=" * 50)
    print("PLANNING -> DISPATCHER HANDOFF")
    print("==============================")
    if job_id is not None:
        print(f"Job ID: {job_id}")
    print("Recommended technicians in the returned planning payload:")

    if not top_3_technicians:
        print("No technician recommendations are being handed off.")
    else:
        for index, technician in enumerate(top_3_technicians, start=1):
            rank = technician.get("rank", index)
            name = technician.get("technician_name") or "Unknown technician"
            technician_id = (
                technician.get("technician_id")
                or technician.get("tech_id")
                or technician.get("id")
                or "N/A"
            )
            organization = technician.get("organization_name") or "N/A"
            print(
                f"Rank {rank}: Technician {name} | ID: {technician_id} | "
                f"Organization: {organization}"
            )
    print("=" * 50)


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
                f"Name: {tech.get('technician_name') or 'N/A'} | "
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
    raw_top_3_list = planning_state.get("top_3") or []

    # The graph's all_eligible_technicians field contains the
    # complete list produced by find_and_rank_technicians_node.
    raw_all_ranked_list = (
        planning_state.get("all_ranked_technicians")
        or planning_state.get("all_eligible_technicians")
        or planning_state.get("all_candidates")
        or raw_top_3_list
    )

    # Some planning graph nodes return IDs without names. Enrich these
    # records from common name fields or the supplied DB session, so the
    # technician's name is visible in terminal output and the returned payload.
    all_ranked_list = _enrich_technician_names(raw_all_ranked_list, db)
    top_3_list = _enrich_technician_names(raw_top_3_list, db)

    # Use the complete ranking to derive the top three when not populated.
    if not top_3_list and all_ranked_list:
        top_3_list = [dict(tech) for tech in all_ranked_list[:3]]

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

    # Show the exact top-three names/IDs included for downstream Dispatcher handling.
    log_dispatcher_handoff(
        top_3_list,
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