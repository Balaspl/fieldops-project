"""
closure_integration.py

Integration layer between the backend
job completion workflow and the AI Closure Agent.
"""

from __future__ import annotations

import asyncio
from typing import Any, Mapping

from app.services.ai.FieldOpsAI.agents.base import (
    AgentLifecycleError,
    AgentState,
    TenantIsolationError,
)
from app.services.ai.FieldOpsAI.agents.closure_agent import ClosureAgent
from app.services.ai.FieldOpsAI.runtime.agent_pool import AgentPool
from app.services.ai.FieldOpsAI.runtime.lifecycle import AgentLifecycle
from app.services.ai.FieldOpsAI.schemas.agent_result import AgentResultStatus
from app.services.ai.FieldOpsAI.schemas.ai_task import AITask
from app.services.ai.FieldOpsAI.schemas.closure import (
    ClosureContext,
    ClosureDecision,
)


class ClosureIntegration:
    """Adapter for AI-generated closure summaries and recommendations."""

    def __init__(self, agent: ClosureAgent | None = None) -> None:
        self.agent = agent

    async def generate_async(
        self,
        context: Mapping[str, Any],
        tenant_id: str,
    ) -> ClosureDecision:
        """Generate closure information through the agent lifecycle."""
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("tenant_id must be a non-blank string.")

        tenant_id = tenant_id.strip()
        if self.agent is not None:
            if self.agent.state is AgentState.TERMINATED:
                raise AgentLifecycleError(
                    "The injected agent is already terminated."
                )
            if self.agent.tenant_id != tenant_id:
                raise TenantIsolationError(
                    "The injected ClosureAgent does not belong to the requested tenant."
                )
            agent_to_use = self.agent
        else:
            from app.services.ai.FieldOpsAI.config.agent_config_manager import (
                AgentConfigManager,
            )

            config = AgentConfigManager().resolve(
                agent_type=AITask.CLOSURE,
                tenant_id=tenant_id,
            )
            agent_to_use = ClosureAgent(config=config)

        closure_context = ClosureContext.model_validate(context)
        exec_context = closure_context.model_dump(mode="json")
        exec_context["tenant_id"] = tenant_id

        pool = AgentPool()
        async with AgentLifecycle(agent=agent_to_use, pool=pool) as lifecycle:
            result = await lifecycle.execute(exec_context)
            if result.status != AgentResultStatus.SUCCESS:
                raise RuntimeError(
                    "Closure Agent failed while generating closure information."
                )
            decision = result.output
            if not isinstance(decision, ClosureDecision):
                raise RuntimeError(
                    "Closure Agent returned an invalid decision."
                )
            return decision

    def generate(
        self,
        context: Mapping[str, Any],
        tenant_id: str,
    ) -> ClosureDecision:
        """Synchronous adapter for callers outside an active event loop."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise RuntimeError(
                "ClosureIntegration.generate() cannot be called from an active "
                "event loop. Use await generate_async(...) instead."
            )

        return asyncio.run(
            self.generate_async(context=context, tenant_id=tenant_id)
        )
