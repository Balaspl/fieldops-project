"""
dispatch_service.py

Dispatch Service for FieldOps Commander.
"""

from __future__ import annotations

import asyncio
from typing import Callable

from app.services.ai.FieldOpsAI.repositories.job_repository import JobRepository
from app.services.ai.FieldOpsAI.repositories.technician_repository import TechnicianRepository
from app.services.ai.FieldOpsAI.repositories.job_assignment_repository import JobAssignmentRepository

from app.services.ai.FieldOpsAI.agents.dispatch_agent import DispatchAgent
from app.services.ai.FieldOpsAI.schemas.agent_config import AgentConfig
from app.services.ai.FieldOpsAI.schemas.dispatch import DispatchContext, DispatchDecision
from app.services.ai.FieldOpsAI.config.agent_config_manager import AgentConfigManager
from app.services.ai.FieldOpsAI.schemas.ai_task import AITask
from app.services.ai.FieldOpsAI.runtime.lifecycle import AgentLifecycle
from app.services.ai.FieldOpsAI.runtime.agent_pool import AgentPool
from app.services.ai.FieldOpsAI.schemas.agent_result import AgentResultStatus
from app.services.ai.FieldOpsAI.runtime.orchestrator import AIOrchestrator


class DispatchService:
    """
    Service responsible for technician dispatch workflow.
    """

    def __init__(
        self,
        db,
        config_manager: AgentConfigManager | None = None,
        pool: AgentPool | None = None,
        agent_factory: Callable[[AgentConfig, AIOrchestrator | None], DispatchAgent] | None = None,
        orchestrator: AIOrchestrator | None = None,
    ):
        self.db = db

        self.job_repository = JobRepository(db)
        self.technician_repository = TechnicianRepository(db)
        self.assignment_repository = JobAssignmentRepository(db)

        self._config_manager = config_manager
        self._pool = pool
        self._agent_factory = agent_factory
        self._orchestrator = orchestrator
        self.agent = None

    # ---------------------------------------------------------

    async def dispatch_async(
        self,
        job_id: int,
        event: str,
    ) -> DispatchDecision:
        """
        AI-assisted technician dispatch workflow decision and side effects (Asynchronous).
        """
        # 1. Load Job
        job = self.job_repository.get_by_id(job_id)
        if job is None:
            raise ValueError(f"Job {job_id} was not found.")

        # 2. Determine the authoritative tenant
        tenant_id = job.tenant_id
        if not isinstance(tenant_id, str) or tenant_id.strip() == "":
            raise ValueError(f"Job {job_id} does not have a tenant_id.")

        # 3. Retrieve current candidate
        current_assignment = self.assignment_repository.get_current_candidate(job_id)
        if current_assignment is None:
            raise ValueError(f"No current technician assignment found for Job {job_id}.")

        # Correction 5: tenant/domain ownership verification
        if current_assignment.job_id != job.id:
            raise ValueError("Mismatched job ID in assignment record.")

        tech = self.technician_repository.get_by_id(current_assignment.technician_id)
        if tech is None:
            raise ValueError(f"Technician {current_assignment.technician_id} was not found.")

        # Required non-blank matching tenant_id (Correction 5)
        if not isinstance(tech.tenant_id, str) or tech.tenant_id.strip() == "":
            raise ValueError("Technician is missing a tenant ID.")
        if tech.tenant_id != tenant_id:
            raise ValueError("Cross-tenant technician detected.")

        # 4. Load remaining candidates and rejected IDs via repository method (Correction 4)
        remaining_assignments = self.assignment_repository.get_remaining_candidates(
            job_id=job_id,
            after_rank=current_assignment.rank,
        )

        remaining_candidates = []
        for r_assign in remaining_assignments:
            # Verify remaining assignment belongs to the correct job (Correction 4)
            if r_assign.job_id != job.id:
                raise ValueError("A remaining assignment belongs to another job.")
            
            r_tech = self.technician_repository.get_by_id(r_assign.technician_id)
            if r_tech is None:
                raise ValueError(
                    "A remaining assignment references an unavailable technician."
                )

            # Required non-blank matching tenant_id (Correction 5)
            if not isinstance(r_tech.tenant_id, str) or r_tech.tenant_id.strip() == "":
                raise ValueError("Technician in candidate pool is missing a tenant ID.")
            if r_tech.tenant_id != tenant_id:
                raise ValueError("Cross-tenant technician detected in candidate pool.")

            remaining_candidates.append(self.technician_repository.to_ai_dict(r_tech))

        rejected_ids = self.assignment_repository.get_rejected_technician_ids(job_id)

        # 5. Build DispatchContext
        job_dict = {
            "id": job.id,
            "customer_name": job.customer_name,
            "location": job.location,
            "priority": job.priority,
            "service_type": job.service_type,
            "required_skill": job.required_skill,
            "status": job.status,
        }

        tech_dict = self.technician_repository.to_ai_dict(tech)

        context = DispatchContext(
            job=job_dict,
            current_technician=tech_dict,
            event=event,
            remaining_candidates=remaining_candidates,
            rejected_technician_ids=rejected_ids,
        )

        # 6. Resolve AgentConfig (Preserving falsey ConfigManager double via None checks, Correction 9)
        config_manager = (
            self._config_manager
            if self._config_manager is not None
            else AgentConfigManager()
        )
        config = config_manager.resolve(
            agent_type=AITask.DISPATCH,
            tenant_id=tenant_id,
        )

        # 7. Create DispatchAgent (using custom agent_factory if supplied, otherwise standard constructor)
        if self._agent_factory is not None:
            agent = self._agent_factory(config, self._orchestrator)
        else:
            agent = DispatchAgent(config=config, orchestrator=self._orchestrator)
        self.agent = agent

        exec_context = context.model_dump(mode="json")
        exec_context["tenant_id"] = tenant_id

        # 8. Execute exactly one AgentLifecycle (Preserving falsey AgentPool double via None checks, Correction 9)
        pool = (
            self._pool
            if self._pool is not None
            else AgentPool()
        )

        async with AgentLifecycle(agent=agent, pool=pool) as lifecycle:
            result = await lifecycle.execute(exec_context)
            if result.status != AgentResultStatus.SUCCESS:
                raise RuntimeError("Dispatch Agent failed while generating a recommendation.")
            decision = result.output

            if not isinstance(decision, DispatchDecision):
                raise RuntimeError("Dispatch Agent returned an invalid decision.")

        # Correction 1: Bind AI output to authoritative entities (before database side effects)
        if decision.job_id != job.id:
            raise RuntimeError(
                "Dispatch Agent returned a decision for a different job."
            )

        if decision.technician_id != current_assignment.technician_id:
            raise RuntimeError(
                "Dispatch Agent returned a decision for a different technician."
            )

        # Correction 2: Validate event/action/status consistency
        self._validate_decision_contract(
            event=event,
            decision=decision,
            remaining_candidates_count=len(remaining_candidates),
        )

        # 9. Perform existing valid service-level database operations exactly once on success (Correction 6)
        if decision.action == "complete_assignment":
            self.assignment_repository.mark_accepted(current_assignment)
            self.job_repository.assign_technician(job_id, current_assignment.technician_id)
            self.job_repository.update_status(job_id, "ASSIGNED")
            self.technician_repository.increment_jobs(current_assignment.technician_id)
            self.assignment_repository.save()
        elif decision.action == "assign_next_candidate":
            current_rank = current_assignment.rank

            next_candidate = (
                self.assignment_repository.promote_next_candidate(
                    job_id,
                    after_rank=current_rank,
                )
            )
            if next_candidate is None:
                raise RuntimeError(
                    "The next technician candidate could not be promoted."
                )
            if decision.status == "REJECTED":
                self.assignment_repository.mark_rejected(
                    current_assignment
                )
            else:
                self.assignment_repository.mark_timeout(
                    current_assignment
                )
            self.assignment_repository.save()
        elif decision.action == "request_replanning":
            if decision.status == "REJECTED":
                self.assignment_repository.mark_rejected(current_assignment)
            else:
                self.assignment_repository.mark_timeout(current_assignment)
            self.assignment_repository.save()
        # Note: action == "manual_review" performs no database commit or mutations

        # 10. Return decision
        return decision

    def _validate_decision_contract(
        self,
        *,
        event: str,
        decision: DispatchDecision,
        remaining_candidates_count: int,
    ) -> None:
        """
        Validate consistency between event, action, and status in DispatchDecision.
        """
        # Defensive rejection of unsupported event or action
        if event not in ("TECHNICIAN_ACCEPTED", "TECHNICIAN_REJECTED", "TECHNICIAN_TIMEOUT"):
            raise RuntimeError("Unsupported event type.")
        if decision.action not in ("complete_assignment", "assign_next_candidate", "request_replanning", "manual_review"):
            raise RuntimeError("Dispatch Agent returned an unsupported action.")

        # 1. Resolve manual-review contract conflict (Correction 3)
        if decision.action == "manual_review":
            # Bypass other validation rules for manual_review
            return

        # 2. Verify event/status/action agreement first to catch mismatches clearly
        if event == "TECHNICIAN_ACCEPTED":
            if decision.status != "ACCEPTED":
                raise RuntimeError("Accepted event mismatch: status must be ACCEPTED.")
            if decision.action != "complete_assignment":
                raise RuntimeError("Accepted event mismatch: action must be complete_assignment.")
        elif event == "TECHNICIAN_REJECTED":
            if decision.status != "REJECTED":
                raise RuntimeError("Rejected event mismatch: status must be REJECTED.")
            if decision.action not in ("assign_next_candidate", "request_replanning"):
                raise RuntimeError("Rejected event mismatch: action must be assign_next_candidate or request_replanning.")
        else:
            # TECHNICIAN_TIMEOUT
            if decision.status != "TIMEOUT":
                raise RuntimeError("Timeout event mismatch: status must be TIMEOUT.")
            if decision.action not in ("assign_next_candidate", "request_replanning"):
                raise RuntimeError("Timeout event mismatch: action must be assign_next_candidate or request_replanning.")

        # 3. Explicitly validate action requirements (Correction 2)
        if decision.action == "assign_next_candidate":
            if remaining_candidates_count == 0:
                raise RuntimeError("Action assign_next_candidate is invalid when no remaining candidates exist.")
        elif decision.action == "request_replanning":
            if remaining_candidates_count > 0:
                raise RuntimeError("Action request_replanning is invalid when remaining candidates exist.")

    def dispatch(
        self,
        job_id: int,
        event: str,
    ) -> DispatchDecision:
        """
        AI-assisted technician dispatch workflow decision and side effects (Synchronous wrapper).
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise RuntimeError(
                "DispatchService.dispatch() cannot be called from an active "
                "event loop. Use await dispatch_async(...) instead."
            )

        return asyncio.run(
            self.dispatch_async(
                job_id=job_id,
                event=event,
            )
        )

    # ---------------------------------------------------------
    # Legacy direct workflow methods (retained for database tasks / triggers)
    # ---------------------------------------------------------

    def dispatch_candidate(
        self,
        job_id: int,
    ):
        """
        Legacy direct dispatch of current technician.
        """
        assignment = self.assignment_repository.get_current_candidate(
            job_id
        )

        if assignment is None:
            raise ValueError(
                "No technician available for dispatch."
            )

        self.assignment_repository.mark_assigned(
            assignment
        )

        self.assignment_repository.save()

        return assignment

    def accept(
        self,
        job_id: int,
    ):
        """
        Technician accepted the job.
        """
        assignment = self.assignment_repository.get_current_candidate(
            job_id
        )

        if assignment is None:
            raise ValueError(
                "No current technician."
            )

        self.assignment_repository.mark_accepted(
            assignment
        )

        job = self.job_repository.assign_technician(
            job_id,
            assignment.technician_id,
        )

        self.job_repository.update_status(
            job_id,
            "ASSIGNED",
        )

        self.technician_repository.increment_jobs(
            assignment.technician_id
        )

        self.assignment_repository.save()

        return job

    def reject(
        self,
        job_id: int,
    ):
        """
        Technician rejected the assignment.
        """
        assignment = self.assignment_repository.get_current_candidate(
            job_id
        )

        if assignment is None:
            raise ValueError(
                "No current technician."
            )

        current_rank = assignment.rank

        self.assignment_repository.mark_rejected(
            assignment
        )
        next_candidate = (
            self.assignment_repository.promote_next_candidate(
                job_id,
                after_rank=current_rank,
            )
        )
        self.assignment_repository.save()

        return next_candidate

    def timeout(
        self,
        job_id: int,
    ):
        """
        Technician did not respond.
        """
        assignment = self.assignment_repository.get_current_candidate(
            job_id
        )

        if assignment is None:
            raise ValueError(
                "No current technician."
            )

        current_rank = assignment.rank

        self.assignment_repository.mark_timeout(
            assignment
        )
        next_candidate = (
        self.assignment_repository.promote_next_candidate(
            job_id,
            after_rank=current_rank,
        )
    )
        self.assignment_repository.save()

        return next_candidate

    def get_current_dispatch(
        self,
        job_id: int,
    ):
        """
        Return the technician currently being dispatched.
        """
        return self.assignment_repository.get_current_candidate(
            job_id
        )

    def get_rejected_technicians(
        self,
        job_id: int,
    ):
        """
        Return technicians who already rejected or timed out.
        """
        return (
            self.assignment_repository.get_rejected_technician_ids(
                job_id
            )
        )
