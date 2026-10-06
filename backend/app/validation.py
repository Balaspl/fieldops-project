import logging

from fastapi import HTTPException, status

from . import models
from .utils import is_skill_matching


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def validate_workload_constraints(
    technician: models.Technician,
):
    """
    Validate basic workload constraints.

    Returns:
        (is_valid, message)
    """
    if technician.current_jobs < 0:
        logger.error(
            f"Invalid workload: Technician "
            f"{technician.technician_id} has negative jobs: "
            f"{technician.current_jobs}"
        )
        return False, "Workload values cannot be negative"

    if technician.current_jobs >= technician.max_jobs:
        logger.info(
            f"Validation failure: Technician "
            f"{technician.technician_id} at max capacity "
            f"({technician.current_jobs}/{technician.max_jobs})"
        )
        return False, "Maximum workload reached"

    return True, "Workload valid"


def validate_technician_for_assignment(
    technician: models.Technician,
    job: models.Job,
):
    """
    Comprehensive validation before assignment.

    Checks:
    - Technician availability/status
    - Workload capacity
    - Technician skill matches the job service type/required skill

    A technician who does not have the required skill is rejected.
    """

    # ------------------------------------------------------------------
    # 1. Status Check
    # ------------------------------------------------------------------
    status_upper = (
        technician.technician_status or ""
    ).upper().strip()

    if status_upper in ["OFFLINE", "BUSY"]:
        logger.warning(
            f"Assignment blocked: Technician "
            f"{technician.technician_id} is "
            f"{technician.technician_status}"
        )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Technician is unavailable. "
                "Busy or Offline technicians cannot be assigned jobs."
            ),
        )

    # ------------------------------------------------------------------
    # 2. Workload Check
    # ------------------------------------------------------------------
    is_valid, msg = validate_workload_constraints(
        technician
    )

    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=msg,
        )

    # ------------------------------------------------------------------
    # 3. Skill Match Check
    # ------------------------------------------------------------------
    skill_matches = is_skill_matching(
        technician.technician_skill,
        job.required_skill,
        job.service_type,
    )

    if not skill_matches:
        required_skill = (
            job.service_type
            or job.required_skill
            or "Unknown"
        )

        technician_skill = (
            technician.technician_skill
            or "No skill specified"
        )

        logger.warning(
            f"Assignment blocked due to skill mismatch: "
            f"Technician {technician.technician_id} "
            f"has skill '{technician_skill}', "
            f"but job #{job.id} requires '{required_skill}'."
        )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Technician does not have the required skill "
                f"for this job. Required skill: {required_skill}. "
                f"Technician skill: {technician_skill}."
            ),
        )

    return True


def get_workload_validation_status(
    technician: models.Technician,
):
    """
    Returns data for the validate-workload API.
    """
    can_assign, msg = validate_workload_constraints(
        technician
    )

    status_upper = (
        technician.technician_status or ""
    ).upper().strip()

    # Also check if status is OFFLINE/BUSY for the final can_assign flag.
    final_can_assign = (
        can_assign
        and status_upper == "AVAILABLE"
    )

    if status_upper == "OFFLINE":
        msg = "Technician is offline"

    elif status_upper == "BUSY" and can_assign:
        msg = "Technician is currently unavailable"

    elif not can_assign:
        msg = "Maximum workload reached"

    elif final_can_assign:
        msg = "Assignment allowed"

    return {
        "technician": technician.technician_name,
        "current_jobs": technician.current_jobs,
        "max_jobs": technician.max_jobs,
        "can_assign": final_can_assign,
        "message": msg,
    }