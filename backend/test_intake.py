import asyncio

from app.services.ai.FieldOpsAI.runtime.agent_registry import (
    create_default_agent_registry,
)
from app.services.ai.FieldOpsAI.config.agent_config_manager import (
    AgentConfigManager,
)
from app.services.ai.FieldOpsAI.schemas.ai_task import AITask


async def main():
    registry = create_default_agent_registry()
    config_manager = AgentConfigManager()

    agent = registry.create(
        agent_type=AITask.INTAKE,
        tenant_id="test-tenant",
        config_manager=config_manager,
    )

    await agent.setup()

    context = {
        "tenant_id": "test-tenant",
        "job_id": 101,
        "customer": {
            "customer_id": "customer-001",
            "name": "John",
            "contact_number": "9876543210",
        },
        "request": (
            "My AC is not cooling properly. "
            "Please send a technician tomorrow morning."
        ),
        "service_type": "AC Repair",
        "priority": "normal",
        "required_skill": "AC Technician",
        "location": "Chennai",
        "preferred_visit_date": "2026-09-09",
        "current_date": "2026-09-08",
    }

    result = await agent.execute(context)

    print("\n========== INTAKE RESULT ==========")
    print(result)
    print("====================================")


if __name__ == "__main__":
    asyncio.run(main())