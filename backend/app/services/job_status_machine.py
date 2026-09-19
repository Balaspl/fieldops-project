from enum import Enum
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, List, Callable, Dict
import logging
import json

logger = logging.getLogger(__name__)

class JobStatus(str, Enum):
    CREATED = "CREATED"
    ASSIGNED = "ASSIGNED"
    EN_ROUTE = "EN_ROUTE"
    ON_SITE = "ON_SITE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    CLOSED = "CLOSED"


@dataclass
class TransitionRule:
    allowed: bool
    requires_role: Optional[List[str]] = None
    requires_reason: bool = False
    side_effects: Optional[List[str]] = None


# Exception Classes
class InvalidTransitionError(Exception):
    def __init__(self, message: str, current: str, target: str, error_code: str = "FORBIDDEN_JUMP", **kwargs):
        self.message = message
        self.current = current
        self.target = target
        self.error_code = error_code
        self.details = kwargs
        super().__init__(self.message)
    
    def to_dict(self) -> dict:
        return {
            "error": "INVALID_TRANSITION",
            "error_code": self.error_code,
            "message": self.message,
            "current_status": self.current,
            "target_status": self.target,
            "suggestion": self.details.get("suggestion", ""),
            "missing_prerequisite": self.details.get("missing_prerequisite", ""),
        }


class PermissionDeniedError(Exception):
    def __init__(self, message: str, required: Optional[List[str]], actual: str):
        super().__init__(message)
        self.required = required
        self.actual = actual


import structlog
security_log = structlog.get_logger("security")

class TransitionValidator:
    FORBIDDEN_JUMPS = {
        # Skip intermediate states
        (JobStatus.CREATED, JobStatus.EN_ROUTE): "Must assign technician before en route",
        (JobStatus.CREATED, JobStatus.ON_SITE): "Must assign and start journey before on site",
        (JobStatus.CREATED, JobStatus.COMPLETED): "Must complete all prior stages",
        (JobStatus.ASSIGNED, JobStatus.ON_SITE): "Must be en route before arriving on site",
        (JobStatus.ASSIGNED, JobStatus.COMPLETED): "Must visit site before completion",
        (JobStatus.EN_ROUTE, JobStatus.COMPLETED): "Must arrive on site before completion",
        
        # Reverse from terminal states
        (JobStatus.COMPLETED, JobStatus.CREATED): "Cannot modify completed job",
        (JobStatus.COMPLETED, JobStatus.ASSIGNED): "Cannot modify completed job",
        (JobStatus.COMPLETED, JobStatus.EN_ROUTE): "Cannot modify completed job",
        (JobStatus.COMPLETED, JobStatus.ON_SITE): "Cannot modify completed job",
        (JobStatus.CLOSED, JobStatus.CREATED): "Cannot reopen closed job",
        (JobStatus.CLOSED, JobStatus.ASSIGNED): "Cannot reopen closed job",
        (JobStatus.CLOSED, JobStatus.EN_ROUTE): "Cannot reopen closed job",
        (JobStatus.CLOSED, JobStatus.ON_SITE): "Cannot reopen closed job",
        (JobStatus.CLOSED, JobStatus.COMPLETED): "Cannot modify closed job",
        (JobStatus.CANCELLED, JobStatus.CREATED): "Cannot uncancel job",
        (JobStatus.CANCELLED, JobStatus.ASSIGNED): "Cannot uncancel job",
        (JobStatus.CANCELLED, JobStatus.EN_ROUTE): "Cannot uncancel job",
        (JobStatus.CANCELLED, JobStatus.ON_SITE): "Cannot uncancel job",
        (JobStatus.CANCELLED, JobStatus.COMPLETED): "Cannot uncancel job",
        
        # Self-transitions
        (JobStatus.CREATED, JobStatus.CREATED): "Job already in CREATED status",
        (JobStatus.ASSIGNED, JobStatus.ASSIGNED): "Job already in ASSIGNED status",
        (JobStatus.EN_ROUTE, JobStatus.EN_ROUTE): "Job already en route",
        (JobStatus.ON_SITE, JobStatus.ON_SITE): "Job already on site",
        (JobStatus.COMPLETED, JobStatus.COMPLETED): "Job already completed",
        (JobStatus.CANCELLED, JobStatus.CANCELLED): "Job already cancelled",
        (JobStatus.CLOSED, JobStatus.CLOSED): "Job already closed",
    }
    
    PREREQUISITES = {
        JobStatus.EN_ROUTE: [
            lambda job: (getattr(job, "assigned_technician_id", None) is not None or getattr(job, "technician_id", None) is not None),
            "Technician must be assigned before starting journey"
        ],
        JobStatus.ON_SITE: [
            lambda job: getattr(job, "gps_active", False) is True,
            "GPS tracking must be active before arriving on site"
        ],
        JobStatus.COMPLETED: [
            lambda job: getattr(job, "work_report", None) is not None,
            "Work report must be submitted before completion"
        ],
        JobStatus.CANCELLED: [
            lambda job: str(job.status).upper().strip() not in ["COMPLETED", "CLOSED"],
            "Cannot cancel completed or closed job"
        ],
    }
    
    def validate(self, job, target_status: JobStatus, actor_role: str, is_override: bool = False) -> None:
        current_status = job.status
        if current_status in ("active", "ACTIVE", None):
            if job.assigned_technician_id is not None:
                current = JobStatus.ASSIGNED
            else:
                current = JobStatus.CREATED
        else:
            try:
                current = JobStatus(current_status)
            except ValueError:
                current = JobStatus.CREATED

        target = JobStatus(target_status)
        
        # Check forbidden jumps
        if (current, target) in self.FORBIDDEN_JUMPS:
            if is_override and actor_role == "admin":
                # Log admin override
                security_log.warning(
                    "admin_override_transition",
                    job_id=str(job.id),
                    from_status=current.value,
                    to_status=target.value,
                    actor_role=actor_role,
                    reason="emergency_override"
                )
                return  # Allow but logged
            
            error_code = "FORBIDDEN_JUMP"
            if current == target:
                error_code = "DUPLICATE_STATUS"
            
            raise InvalidTransitionError(
                message=self.FORBIDDEN_JUMPS[(current, target)],
                current=current.value,
                target=target.value,
                error_code=error_code,
                suggestion=self._get_suggestion(current, target)
            )
        
        # Check prerequisites (bypassed if override is active for admin)
        if is_override and actor_role == "admin":
            security_log.warning(
                "admin_override_transition",
                job_id=str(job.id),
                from_status=current.value,
                to_status=target.value,
                actor_role=actor_role,
                reason="emergency_override"
            )
            return

        if target in self.PREREQUISITES:
            check, message = self.PREREQUISITES[target]
            if not check(job):
                raise InvalidTransitionError(
                    message=message,
                    current=current.value,
                    target=target.value,
                    error_code="PREREQUISITE_FAILED",
                    missing_prerequisite=message
                )
        
        # Check transition matrix
        rule = TRANSITION_MATRIX.get((current, target))
        if not rule or not rule.allowed:
            raise InvalidTransitionError(
                message=f"No transition rule defined for {current.value} -> {target.value}",
                current=current.value,
                target=target.value,
                error_code="NO_RULE_DEFINED"
            )
            
        if rule.requires_role and actor_role not in rule.requires_role:
            raise PermissionDeniedError(
                f"Role {actor_role} cannot perform {current.value} -> {target.value}",
                required=rule.requires_role,
                actual=actor_role
            )
    
    def _get_suggestion(self, current: JobStatus, target: JobStatus) -> str:
        suggestions = {
            JobStatus.CREATED: "First assign a technician (CREATED -> ASSIGNED)",
            JobStatus.ASSIGNED: "Technician must start journey (ASSIGNED -> EN_ROUTE)",
            JobStatus.EN_ROUTE: "Technician must arrive on site (EN_ROUTE -> ON_SITE)",
            JobStatus.ON_SITE: "Technician must complete work (ON_SITE -> COMPLETED)",
        }
        return suggestions.get(current, "Contact support for assistance")
    
    def get_valid_transitions(self, job, actor_role: str) -> list[dict]:
        current_status = job.status
        if current_status in ("active", "ACTIVE", None):
            if job.assigned_technician_id is not None:
                current = JobStatus.ASSIGNED
            else:
                current = JobStatus.CREATED
        else:
            try:
                current = JobStatus(current_status)
            except ValueError:
                current = JobStatus.CREATED

        valid = []
        
        for status in JobStatus:
            if status == current:
                continue
            
            try:
                self.validate(job, status, actor_role)
                rule = TRANSITION_MATRIX.get((current, status))
                valid.append({
                    "status": status.value,
                    "allowed": True,
                    "requires_reason": rule.requires_reason if rule else False,
                    "requires_role": rule.requires_role if rule else [],
                })
            except InvalidTransitionError as e:
                valid.append({
                    "status": status.value,
                    "allowed": False,
                    "reason": e.message
                })
            except Exception as e:
                valid.append({
                    "status": status.value,
                    "allowed": False,
                    "reason": str(e)
                })
        
        return valid


class ReasonRequiredError(Exception):
    pass


class SideEffectError(Exception):
    pass


# Transition Rule Matrix
TRANSITION_MATRIX: Dict[tuple[JobStatus, JobStatus], TransitionRule] = {
    # Forward progression
    (JobStatus.CREATED, JobStatus.ASSIGNED): TransitionRule(
        allowed=True,
        requires_role=["dispatcher", "admin", "system"],
        side_effects=["notify_technician", "start_planning_timer"]
    ),
    (JobStatus.ASSIGNED, JobStatus.EN_ROUTE): TransitionRule(
        allowed=True,
        requires_role=["technician", "system"],
        side_effects=["start_gps_tracking", "start_eta_calculation", "notify_customer"]
    ),
    (JobStatus.EN_ROUTE, JobStatus.ON_SITE): TransitionRule(
        allowed=True,
        requires_role=["technician", "system"],
        side_effects=["stop_eta_updates", "start_sla_timer", "geofence_entry"]
    ),
    (JobStatus.ON_SITE, JobStatus.COMPLETED): TransitionRule(
        allowed=True,
        requires_role=["technician", "dispatcher"],
        side_effects=["trigger_billing", "close_gps", "send_survey", "stop_sla_timer"]
    ),
    
    # Backward transitions
    (JobStatus.ASSIGNED, JobStatus.CREATED): TransitionRule(
        allowed=True,
        requires_role=["dispatcher", "admin"],
        requires_reason=True,
        side_effects=["notify_technician_unassign", "clear_planning"]
    ),
    (JobStatus.EN_ROUTE, JobStatus.ASSIGNED): TransitionRule(
        allowed=True,
        requires_role=["dispatcher", "admin"],
        requires_reason=True,
        side_effects=["stop_gps_tracking", "notify_customer_delay"]
    ),
    (JobStatus.ON_SITE, JobStatus.EN_ROUTE): TransitionRule(
        allowed=True,
        requires_role=["technician", "dispatcher", "admin"],
        side_effects=["start_gps_tracking", "notify_customer"]
    ),
    (JobStatus.ON_SITE, JobStatus.ASSIGNED): TransitionRule(
        allowed=True,
        requires_role=["dispatcher", "admin"],
        requires_reason=True,
        side_effects=["stop_gps_tracking"]
    ),
    
    # Terminal states (from any to CANCELLED)
    (JobStatus.CREATED, JobStatus.CANCELLED): TransitionRule(
        allowed=True,
        requires_role=["dispatcher", "admin", "customer"],
        requires_reason=True,
        side_effects=["purge_gps", "notify_all", "log_cancellation"]
    ),
    (JobStatus.ASSIGNED, JobStatus.CANCELLED): TransitionRule(
        allowed=True,
        requires_role=["dispatcher", "admin", "customer"],
        requires_reason=True,
        side_effects=["purge_gps", "notify_all", "log_cancellation", "free_technician"]
    ),
    (JobStatus.EN_ROUTE, JobStatus.CANCELLED): TransitionRule(
        allowed=True,
        requires_role=["dispatcher", "admin"],
        requires_reason=True,
        side_effects=["purge_gps", "notify_all", "log_cancellation", "refund_check"]
    ),
    (JobStatus.ON_SITE, JobStatus.CANCELLED): TransitionRule(
        allowed=True,
        requires_role=["dispatcher", "admin"],
        requires_reason=True,
        side_effects=["purge_gps", "notify_all", "log_cancellation", "partial_billing"]
    ),
    
    # Closure (from any to CLOSED)
    (JobStatus.CREATED, JobStatus.CLOSED): TransitionRule(
        allowed=True,
        requires_role=["system", "admin"],
        requires_reason=True,
        side_effects=["archive_job", "final_audit"]
    ),
    (JobStatus.ASSIGNED, JobStatus.CLOSED): TransitionRule(
        allowed=True,
        requires_role=["system", "admin"],
        requires_reason=True,
        side_effects=["archive_job", "final_audit"]
    ),
    (JobStatus.EN_ROUTE, JobStatus.CLOSED): TransitionRule(
        allowed=True,
        requires_role=["system", "admin"],
        requires_reason=True,
        side_effects=["archive_job", "final_audit"]
    ),
    (JobStatus.ON_SITE, JobStatus.CLOSED): TransitionRule(
        allowed=True,
        requires_role=["system", "admin"],
        requires_reason=True,
        side_effects=["archive_job", "final_audit"]
    ),
    (JobStatus.COMPLETED, JobStatus.CLOSED): TransitionRule(
        allowed=True,
        requires_role=["system", "admin"],
        requires_reason=True,
        side_effects=["archive_job", "final_audit", "close_all_timers"]
    ),
    (JobStatus.CANCELLED, JobStatus.CLOSED): TransitionRule(
        allowed=True,
        requires_role=["system", "admin"],
        requires_reason=True,
        side_effects=["archive_job", "final_audit"]
    ),
}

# Custom Side Effects Registry
SIDE_EFFECTS: Dict[str, Callable] = {}

def register_side_effect(name: str, func: Callable):
    SIDE_EFFECTS[name] = func

def clear_registered_side_effects():
    SIDE_EFFECTS.clear()

def execute_side_effect(effect: str, job, actor_id: str, reason: str = None):
    if effect == "start_gps_tracking":
        job.gps_active = True
    elif effect in ("close_gps", "purge_gps", "stop_eta_updates"):
        job.gps_active = False

    if effect in SIDE_EFFECTS:
        try:
            SIDE_EFFECTS[effect](job, actor_id, reason)
            logger.info(f"Executed custom side effect: {effect} for job {job.id}")
            return
        except Exception as e:
            logger.error(f"Failed custom side effect: {effect} - {e}")
            raise SideEffectError(f"Failed custom side effect {effect}: {e}")

    # Default fallback / stub execution
    logger.info(f"Executing side effect: {effect} for job {job.id}")
    try:
        if effect == "purge_gps":
            logger.info(f"Purging GPS data for job {job.id}")
    except Exception as e:
        logger.error(f"Failed default side effect {effect}: {e}")
        raise SideEffectError(f"Failed default side effect {effect}: {e}")


def transition_job(job, new_status: JobStatus, actor_id: str, actor_role: str, reason: str = None, is_override: bool = False) -> None:
    # 1. Parse current state (handle legacy 'active' status gracefully)
    current_status = job.status
    if current_status in ("active", "ACTIVE", None):
        if job.assigned_technician_id is not None:
            current = JobStatus.ASSIGNED
        else:
            current = JobStatus.CREATED
    else:
        try:
            current = JobStatus(current_status)
        except ValueError:
            current = JobStatus.CREATED

    target = JobStatus(new_status)

    # 2. Run new validation guards
    validator = TransitionValidator()
    validator.validate(job, target, actor_role, is_override)

    # 3. Get transition rule (checked by validator, but retrieved here for side effects)
    rule = TRANSITION_MATRIX.get((current, target))

    # 3b. Enforce reason requirement for backward/cancellation transitions
    if rule and rule.requires_reason and not reason and not is_override:
        raise ReasonRequiredError(
            f"Reason is required for {current.value} -> {target.value} transition"
        )

    # 4. Execute side effects (synchronously before committing)
    if rule and rule.side_effects:
        for effect in rule.side_effects:
            execute_side_effect(effect, job, actor_id, reason)

    # 5. Apply updates in-memory
    job.status = target.value
    
    now_utc = datetime.now(timezone.utc)
    # Update status timestamp
    ts_field = f"{target.value.lower()}_at"
    if hasattr(job, ts_field):
        setattr(job, ts_field, now_utc)

    # Update actor
    actor_field = f"{target.value.lower()}_by"
    if hasattr(job, actor_field):
        setattr(job, actor_field, actor_id)

    # Record cancellation or closure reason
    if target == JobStatus.CANCELLED:
        job.cancellation_reason = reason
    elif target == JobStatus.CLOSED:
        job.closure_reason = reason

    # Audit log entry
    logger.info(
        f"job_status_transition - job_id={job.id} from={current.value} to={target.value} actor={actor_id} role={actor_role}"
    )
