"""
intake_agent.py

Intake Agent for FieldOps Commander AI.
Converts customer requests into structured intake information
for downstream planning.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

from app.services.ai.FieldOpsAI.agents.base import BaseAgent
from app.services.ai.FieldOpsAI.runtime.orchestrator import (
    AIOrchestrator,
    ai_orchestrator,
)
from app.services.ai.FieldOpsAI.schemas.agent_config import AgentConfig
from app.services.ai.FieldOpsAI.schemas.ai_task import AITask
from app.services.ai.FieldOpsAI.schemas.intake import IntakeDecision


logger = logging.getLogger(__name__)


class IntakeAgent(BaseAgent[IntakeDecision]):
    """
    AI agent responsible for converting customer requests
    into structured job intake information.
    """

    def __init__(
        self,
        config: AgentConfig,
        orchestrator: Optional[AIOrchestrator] = None,
    ) -> None:
        """
        Initialize the Intake Agent.
        """

        if config.agent_type != AITask.INTAKE:
            raise ValueError(
                "IntakeAgent requires an AITask.INTAKE configuration."
            )

        super().__init__(config)

        self.orchestrator = (
            ai_orchestrator
            if orchestrator is None
            else orchestrator
        )

    async def run(
        self,
        context: dict[str, Any],
    ) -> IntakeDecision:
        """
        Execute the AI intake task.

        The synchronous AIOrchestrator execution is moved to a
        worker thread so the async event loop is not blocked.
        """

        start_time = time.perf_counter()

        logger.info("Intake Agent run started.")

        # Validate the incoming context using the output contract.
        # The orchestrator will receive the original context and
        # return an IntakeDecision.
        decision = await asyncio.to_thread(
            self.orchestrator.execute,
            task=AITask.INTAKE,
            context=context,
            response_schema=IntakeDecision,
        )
        # Preserve backend-authoritative values.
        if context.get("job_id") is not None:
            decision.job_id = context["job_id"]

        customer_context = context.get("customer") or {}

        if not decision.customer.name and customer_context.get("name"):
            decision.customer.name = customer_context["name"]

        if not decision.customer.contact_number and customer_context.get("contact_number"):
            decision.customer.contact_number = customer_context["contact_number"]

        location_context = context.get("location") or {}

        if decision.location is None and location_context:
            from app.services.ai.FieldOpsAI.schemas.intake import IntakeLocationInfo

            decision.location = IntakeLocationInfo(
                address=location_context.get("address")
            )

        if decision.location and decision.location.address in {
            "{{service_address}}",
            "{{location}}",
            "{{job_location}}",
        }:
            decision.location.address = location_context.get("address")

        elapsed = time.perf_counter() - start_time

        logger.info(
            "Intake completed in %.2f sec | Job ID=%s",
            elapsed,
            decision.job_id,
        )

        return decision