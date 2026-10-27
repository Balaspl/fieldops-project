"""
planning_service.py

Planning Service for FieldOps Commander.

Generates technician recommendations for a job.
Technician selection supports cross-organization dispatch.
Previously attempted technicians are excluded during replanning.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Callable

from app.services.ai.FieldOpsAI.repositories.job_repository import JobRepository
from app.services.ai.FieldOpsAI.repositories.technician_repository import (
    TechnicianRepository,
)

from app.services.ai.FieldOpsAI.agents.planning_agent import PlanningAgent
from app.services.ai.FieldOpsAI.schemas.agent_config import AgentConfig
from app.services.ai.FieldOpsAI.schemas.planning import (
    PlanningContext,
    PlanningDecision,
)
from app.services.ai.FieldOpsAI.config.agent_config_manager import (
    AgentConfigManager,
)
from app.services.ai.FieldOpsAI.schemas.ai_task import AITask
from app.services.ai.FieldOpsAI.runtime.lifecycle import AgentLifecycle
from app.services.ai.FieldOpsAI.runtime.agent_pool import AgentPool
from app.services.ai.FieldOpsAI.schemas.agent_result import AgentResultStatus
from app.services.ai.FieldOpsAI.runtime.orchestrator import AIOrchestrator
from app.redis_client import get_redis_client
from app.models import Organization
from app.services.dispatch_eligibility import evaluate_technician_dispatch_eligibility
from app.services.ai.FieldOpsAI.graph.planning_graph import check_skill_match_level

logger = logging.getLogger(__name__)


class PlanningService:
    """
    Service responsible for AI-assisted technician planning.

    Technician selection is cross-organization.

    The job tenant is used for agent configuration, but does not
    restrict the technician candidate pool.
    """

    def __init__(
        self,
        db,
        config_manager: AgentConfigManager | None = None,
        pool: AgentPool | None = None,
        agent_factory: (
            Callable[
                [AgentConfig, AIOrchestrator | None],
                PlanningAgent,
            ]
            | None
        ) = None,
        orchestrator: AIOrchestrator | None = None,
    ):
        self.db = db

        self.job_repository = JobRepository(db)
        self.technician_repository = TechnicianRepository(db)

        self._config_manager = config_manager
        self._pool = pool
        self._agent_factory = agent_factory
        self._orchestrator = orchestrator

        self.agent = None

    # ---------------------------------------------------------
    # ASYNC PLANNING
    # ---------------------------------------------------------

    async def plan_async(
        self,
        job_id: int,
        rejected_technician_ids: list[int] | None = None,
    ) -> PlanningDecision:
        """
        Generate technician recommendations asynchronously.

        Previously attempted technicians are excluded before the
        Planning Agent receives its candidate list.

        An empty recommendation result is returned to the caller
        without attempting to save an empty assignment batch.
        """

        # 1. Normalize attempted/rejected technician IDs.
        rejected_ids = {
            int(technician_id)
            for technician_id in (rejected_technician_ids or [])
        }

        # 2. Load the job.
        job = self.job_repository.get_by_id(job_id)

        if job is None:
            raise ValueError(f"Job {job_id} was not found.")

        # 3. Resolve the job tenant for AI configuration only.
        tenant_id = job.tenant_id

        # 4. Load available technicians across organizations.
        technicians = self.technician_repository.get_available()
        redis_client = get_redis_client()
        dispatch_eligible = []
        excluded_candidates: list[dict] = []
        active_organizations = {
            str(org_id): (latitude, longitude)
            for org_id, latitude, longitude in self.db.query(
                Organization.id,
                Organization.site_latitude,
                Organization.site_longitude,
            ).filter(
                Organization.status == "ACTIVE",
                Organization.deleted_at.is_(None),
            ).all()
        }
        for technician in technicians:
            technician_id = int(technician.technician_id)
            reason = None
            organization_location = active_organizations.get(str(technician.tenant_id))
            if organization_location is None:
                reason = "technician_tenant_inactive_or_missing"
                eligibility = {"eligible": False, "reason": reason}
            else:
                eligibility = evaluate_technician_dispatch_eligibility(
                    technician,
                    job_tenant_id=None,
                    redis_client=redis_client,
                    fallback_location=organization_location,
                )
            if eligibility["eligible"]:
                skill_level = check_skill_match_level(
                    technician.technician_skill,
                    job.required_skill or job.service_type,
                    job.service_type,
                    getattr(job, "title", None),
                    job.issue_description,
                )
                if skill_level < 1:
                    reason = "required_skill_mismatch"
                else:
                    location = eligibility["location_coordinates"]
                    technician_data = self.technician_repository.to_ai_dict(technician)
                    technician_data.update({
                        "tenant_id": str(technician.tenant_id),
                        "location": f"{location[0]},{location[1]}",
                        "location_accuracy_meters": eligibility["accuracy_meters"],
                        "location_age_seconds": eligibility["location_age_seconds"],
                        "heartbeat_age_seconds": eligibility["heartbeat_age_seconds"],
                        "eligible": True,
                        "exclusion_reason": None,
                    })
                    dispatch_eligible.append((technician, technician_data))
            else:
                reason = eligibility["reason"]
            if reason:
                excluded_candidates.append({
                    "technician_id": technician_id,
                    "eligible": False,
                    "exclusion_reason": reason,
                })
        technicians = [technician for technician, _ in dispatch_eligible]

        if not technicians:
            return PlanningDecision(
                action="no_assignment",
                job_id=int(job.id),
                priority=(str(job.priority or "MEDIUM").upper() if str(job.priority or "MEDIUM").upper() in {"LOW", "MEDIUM", "HIGH", "CRITICAL"} else "MEDIUM"),
                reason="No technicians met the current planning eligibility requirements.",
                excluded_candidates=excluded_candidates,
            )

        # 5. Exclude technicians already attempted by the dispatcher.
        available_technicians = []

        data_by_id = {int(technician.technician_id): data for technician, data in dispatch_eligible}
        for technician in technicians:
            technician_id = int(technician.technician_id)

            if technician_id in rejected_ids:
                excluded_candidates.append({
                    "technician_id": technician_id,
                    "eligible": False,
                    "exclusion_reason": "already_attempted_in_dispatch_cycle",
                })
                continue

            technician_data = data_by_id[technician_id]

            available_technicians.append(technician_data)

        logger.info(
            "PLANNING CANDIDATE POOL | job_id=%s | "
            "rejected_ids=%s | candidate_count=%s",
            job.id,
            sorted(rejected_ids),
            len(available_technicians),
        )

        logger.debug(
            "PLANNING AVAILABLE TECHNICIANS | job_id=%s | technicians=%s",
            job.id,
            available_technicians,
        )

        if not available_technicians:
            return PlanningDecision(
                action="no_assignment",
                job_id=int(job.id),
                priority=(str(job.priority or "MEDIUM").upper() if str(job.priority or "MEDIUM").upper() in {"LOW", "MEDIUM", "HIGH", "CRITICAL"} else "MEDIUM"),
                reason="No unattempted technicians meet the current planning eligibility requirements.",
                excluded_candidates=excluded_candidates,
            )

        # 6. Build planning context.
        context = PlanningContext(
            job_id=job.id,
            customer_request={
                "customer_name": job.customer_name,
                "location": job.location,
                "priority": job.priority,
                "required_skill": job.required_skill,
            },
            available_technicians=available_technicians,
            rejected_technician_ids=sorted(rejected_ids),
        )

        # 7. Resolve agent configuration.
        config_manager = (
            self._config_manager
            if self._config_manager is not None
            else AgentConfigManager()
        )

        config = config_manager.resolve(
            agent_type=AITask.PLANNING,
            tenant_id=tenant_id,
        )

        # 8. Create Planning Agent.
        if self._agent_factory is not None:
            agent = self._agent_factory(
                config,
                self._orchestrator,
            )
        else:
            agent = PlanningAgent(
                config=config,
                orchestrator=self._orchestrator,
            )

        self.agent = agent

        # 9. Prepare execution context.
        exec_context = context.model_dump(mode="json")
        exec_context["tenant_id"] = tenant_id

        logger.info(
            "PLANNING EXECUTION CONTEXT | job_id=%s | context=%s",
            job_id,
            json.dumps(exec_context, indent=2, default=str),
        )

        # 10. Resolve agent pool.
        pool = (
            self._pool
            if self._pool is not None
            else AgentPool()
        )

        # 11. Execute the Planning Agent lifecycle.
        async with AgentLifecycle(
            agent=agent,
            pool=pool,
        ) as lifecycle:
            result = await lifecycle.execute(exec_context)

            # 12. Validate execution result.
            if result.status != AgentResultStatus.SUCCESS:
                raise RuntimeError(
                    "Planning Agent failed while generating "
                    "technician recommendations."
                )

            decision = result.output

            # 13. Validate decision type.
            if not isinstance(decision, PlanningDecision):
                raise RuntimeError(
                    "Planning Agent returned an invalid decision."
                )

       
        # 14. Final safety check: remove attempted technicians
        # from the complete ranked pool and recommendations.
            eligible_ids = {int(item["technician_id"]) for item in available_technicians}
            if decision.all_ranked_technicians:
                filtered_ranked = []
                seen_ids: set[int] = set()

                for technician in decision.all_ranked_technicians:
                    technician_id = int(technician.technician_id)

                    if technician_id in rejected_ids:
                        logger.warning(
                            "PLANNING RETURNED PREVIOUSLY ATTEMPTED "
                            "TECHNICIAN | job_id=%s | technician_id=%s",
                            job.id,
                            technician_id,
                        )
                        continue

                    if technician_id not in eligible_ids:
                        excluded_candidates.append({
                            "technician_id": technician_id,
                            "eligible": False,
                            "exclusion_reason": "not_in_current_eligible_planning_pool",
                        })
                        continue

                    if technician_id in seen_ids:
                        continue

                    filtered_ranked.append(technician)
                    seen_ids.add(technician_id)

                # Preserve every remaining ranked candidate.
                decision.all_ranked_technicians = filtered_ranked
                decision.excluded_candidates = excluded_candidates

                # The current offer batch remains limited to three.
                decision.recommended_technicians = filtered_ranked[:3]

            else:
                # Fallback when Planning returns only the Top 3.
                filtered_recommendations = []
                seen_ids: set[int] = set()

                for technician in decision.recommended_technicians:
                    technician_id = int(technician.technician_id)

                    if technician_id in rejected_ids:
                        logger.warning(
                            "PLANNING RETURNED PREVIOUSLY ATTEMPTED "
                            "TECHNICIAN | job_id=%s | technician_id=%s",
                            job.id,
                            technician_id,
                        )
                        continue

                    if technician_id not in eligible_ids:
                        excluded_candidates.append({
                            "technician_id": technician_id,
                            "eligible": False,
                            "exclusion_reason": "not_in_current_eligible_planning_pool",
                        })
                        continue

                    if technician_id in seen_ids:
                        continue

                    filtered_recommendations.append(technician)
                    seen_ids.add(technician_id)

                decision.recommended_technicians = (
                    filtered_recommendations[:3]
                )
                decision.excluded_candidates = excluded_candidates
            decision.top_3 = (
                decision.all_ranked_technicians
                or decision.recommended_technicians
            )[:3]
            return decision


    # ---------------------------------------------------------
    # SYNC PLANNING
    # ---------------------------------------------------------

    def plan(
        self,
        job_id: int,
        rejected_technician_ids: list[int] | None = None,
    ) -> PlanningDecision:
        """
        Generate technician recommendations synchronously.

        Must not be called from an active event loop.
        """

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # No active event loop.
            pass
        else:
            raise RuntimeError(
                "PlanningService.plan() cannot be called from an "
                "active event loop. Use await plan_async(...) instead."
            )

        return asyncio.run(
            self.plan_async(
                job_id=job_id,
                rejected_technician_ids=rejected_technician_ids,
            )
        )

