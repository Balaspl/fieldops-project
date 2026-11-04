"""
closure_agent.py

Closure Agent for FieldOps Commander AI,
migrated to inherit from BaseAgent.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any, Optional

from app.services.ai.FieldOpsAI.agents.base import BaseAgent

if TYPE_CHECKING:
    from app.services.ai.FieldOpsAI.runtime.orchestrator import AIOrchestrator
from app.services.ai.FieldOpsAI.schemas.agent_config import AgentConfig
from app.services.ai.FieldOpsAI.schemas.ai_task import AITask
from app.services.ai.FieldOpsAI.schemas.closure import (
    ClosureContext,
    ClosureDecision,
)

logger = logging.getLogger(__name__)


class ClosureAgent(BaseAgent[ClosureDecision]):
    """
    AI agent responsible for generating structured
    job closure information.
    """

    def __init__(
        self,
        config: AgentConfig,
        orchestrator: Optional[AIOrchestrator] = None,
    ) -> None:
        """
        Initialize the Closure Agent.
        """

        if config.agent_type != AITask.CLOSURE:
            raise ValueError(
                "ClosureAgent requires an AITask.CLOSURE configuration."
            )

        super().__init__(config)

        self.orchestrator = orchestrator

    async def run(
        self,
        context: dict[str, Any],
    ) -> ClosureDecision:
        """
        Execute the AI closure task.

        The synchronous AIOrchestrator.execute call is moved to
        a worker thread so the async event loop is not blocked.
        """

        start_time = time.perf_counter()

        logger.info("Closure Agent run started.")

        closure_context = ClosureContext.model_validate(context)

        orchestrator_context = closure_context.model_dump(
            mode="json"
        )
        orchestrator_context["tenant_id"] = self.tenant_id

        orchestrator = self.orchestrator

        if orchestrator is None:
            from app.services.ai.FieldOpsAI.runtime.orchestrator import (
                ai_orchestrator,
            )

            orchestrator = ai_orchestrator
            self.orchestrator = orchestrator

        decision = await asyncio.to_thread(
            orchestrator.execute,
            task=AITask.CLOSURE,
            context=orchestrator_context,
            response_schema=ClosureDecision,
        )

        elapsed = time.perf_counter() - start_time

        logger.info(
            "Closure completed in %.2f sec | Follow-up=%s",
            elapsed,
            decision.follow_up_required,
        )

        return decision

    def generate(
        self,
        context: ClosureContext,
    ) -> ClosureDecision:
        """
        Compatibility adapter for legacy synchronous callers.

        The internal execution path uses BaseAgent.execute().
        """

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise RuntimeError(
                "generate() cannot be called from an active event loop. "
                "Use the asynchronous AgentLifecycle / execute path instead."
            )

        exec_context = context.model_dump(mode="json")
        exec_context["tenant_id"] = self.tenant_id

        async def _run_wrapped():
            if not self.is_setup:
                await self.setup()

            return await self.execute(exec_context)

        return asyncio.run(_run_wrapped())
