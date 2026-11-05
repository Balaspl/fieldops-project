"""Agent-to-agent entry point for safe communication generation."""

from __future__ import annotations

from app.services.ai.FieldOpsAI.schemas.communication import (
    AgentCommunicationRequest,
)
from app.services.ai.FieldOpsAI.services.communication_service import (
    CommunicationService,
    CommunicationServiceResult,
)


class AgentCommunicationCoordinator:
    """Validate internal requests, then delegate to the existing safe service."""

    def __init__(self, *, db, tenant_id: str):
        self.db = db
        self.tenant_id = str(tenant_id).strip()
        if not self.tenant_id or len(self.tenant_id) > 50:
            raise ValueError("A valid trusted tenant_id is required.")

    def generate(
        self,
        request: AgentCommunicationRequest,
    ) -> CommunicationServiceResult:
        """Generate guardrail-checked copy for an approved recipient/channel."""
        context = request.context
        if context.customer_id and len(context.customer_id) > 100:
            raise ValueError("Invalid customer identifier in communication request.")
        service = CommunicationService(
            db=self.db,
            tenant_id=self.tenant_id,
        )
        return service.generate(context=context)
