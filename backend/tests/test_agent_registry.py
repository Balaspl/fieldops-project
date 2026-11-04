"""
test_agent_registry.py

Tests for AgentRegistry and AgentRegistration.

Story 1.3 — Agent Registry.

Coverage targets (57 tests)
-----------------------------
AgentRegistration schema:
  1.  Valid registration
  2.  Register valid BaseAgent subclass
  3.  Reject BaseAgent itself
  4.  Reject abstract BaseAgent subclass
  5.  Reject non-agent class
  6.  Reject non-class agent_class
  7.  Reject blank version
  8.  Reject non-string version
  9.  Description must be str or None (None accepted)
  10. Description non-str rejected
  11. Registration is frozen/immutable

Registry management:
  12. Empty registry has zero registrations
  13. Register valid agent type
  14. Duplicate registration rejected (no replace)
  15. Explicit replace=True works
  16. Get registration after register
  17. Missing registration raises AgentNotRegisteredError
  18. Contains returns True for registered type
  19. Contains returns False for missing type
  20. Unregister existing returns True
  21. Unregister missing returns False
  22. list_registrations is deterministic
  23. enabled_only filter excludes disabled
  24. Disabled registration discoverable via get()
  25. Disabled registration cannot create (AgentRegistrationDisabledError)
  26. Non-callable factory rejected
  27. Already_registered log semantics (replaced=True only on actual replacement)
  28. Invalid agent_type on get() raises TypeError
  29. Invalid agent_type on contains() raises TypeError
  30. Invalid agent_type on unregister() raises TypeError

Agent creation:
  31. Blank tenant_id raises ValueError
  32. Non-string tenant_id raises TypeError
  33. Whitespace-only tenant_id raises ValueError (strip enforced)
  34. Invalid config_manager (no resolve()) raises TypeError
  35. Non-callable config_manager.resolve raises TypeError
  36. ConfigManager called with correct agent_type and tenant_id
  37. Non-AgentConfig resolved result raises AgentRegistryError
  38. Wrong resolved config agent_type raises AgentRegistryError
  39. Wrong resolved config tenant_id raises AgentRegistryError
  40. Disabled resolved config raises AgentRegistryError
  41. create() returns a BaseAgent instance
  42. create() does not call setup (is_setup=False)
  43. create() returns IDLE state agent
  44. create() does not register agent in AgentPool
  45. Two create() calls return different instances

Custom factories:
  46. Custom factory receives config and orchestrator
  47. Falsey custom factory is retained (explicit None check)
  48. Non-agent factory result raises AgentRegistryError
  49. Wrong-type factory result raises AgentRegistryError
  50. Wrong-tenant factory result raises AgentRegistryError
  51. Initialized factory result raises AgentRegistryError (is_setup=True)
  52. Non-IDLE factory result raises AgentRegistryError
  53. Singleton/reused factory result raises AgentRegistryError (same UUID)
  54. Concurrent reuse detection raises AgentRegistryError

Default registry:
  55. Default registry contains Planning and Dispatch
  56. Default registry excludes unmigrated agents
  57. Two create_default_agent_registry() calls return independent registries

Structural / behavioral:
  58. Registry stores definitions, not live instances
  59. Concurrent registrations and lookups do not corrupt mappings
"""

from __future__ import annotations

import dataclasses
import threading
from abc import abstractmethod
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.services.ai.FieldOpsAI.agents.base import AgentState, BaseAgent
from app.services.ai.FieldOpsAI.config.agent_config_manager import AgentConfigManager
from app.services.ai.FieldOpsAI.runtime.agent_registry import (
    AgentAlreadyRegisteredError,
    AgentNotRegisteredError,
    AgentRegistrationDisabledError,
    AgentRegistry,
    AgentRegistryError,
    create_default_agent_registry,
)
from app.services.ai.FieldOpsAI.schemas.agent_config import AgentConfig
from app.services.ai.FieldOpsAI.schemas.agent_registration import AgentRegistration
from app.services.ai.FieldOpsAI.schemas.ai_task import AITask


# ---------------------------------------------------------------------------
# Minimal concrete agents for unit tests
# ---------------------------------------------------------------------------


class AlphaAgent(BaseAgent[dict[str, Any]]):
    """Minimal concrete agent used in registry unit tests."""

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        return {"agent": "alpha"}


class BetaAgent(BaseAgent[dict[str, Any]]):
    """Second concrete agent used in registry unit tests."""

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        return {"agent": "beta"}


class AbstractSubAgent(BaseAgent[dict[str, Any]]):
    """Abstract BaseAgent subclass — has an unimplemented abstract method."""

    @abstractmethod
    def extra_abstract(self) -> None:
        """Intentionally left unimplemented to remain abstract."""

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        return {}


class WrongTenantAgent(BaseAgent[dict[str, Any]]):
    """Agent whose constructor always sets tenant_id to 'wrong-tenant'."""

    def __init__(
        self,
        config: AgentConfig,
        orchestrator: object | None = None,
    ) -> None:
        bad_config = AgentConfig(
            agent_type=config.agent_type,
            tenant_id="wrong-tenant",
        )
        super().__init__(bad_config)

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        return {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_registration(
    agent_type: AITask = AITask.DISPATCH,
    agent_class: type = AlphaAgent,
    version: str = "1.0",
    enabled: bool = True,
    description: str | None = None,
) -> AgentRegistration:
    return AgentRegistration(
        agent_type=agent_type,
        agent_class=agent_class,
        version=version,
        enabled=enabled,
        description=description,
    )


def make_mock_config_manager(
    agent_type: AITask = AITask.DISPATCH,
    tenant_id: str = "tenant-reg",
    enabled: bool = True,
) -> MagicMock:
    """Return a mock AgentConfigManager that resolves a fixed config."""
    config = AgentConfig(
        agent_type=agent_type,
        tenant_id=tenant_id,
        enabled=enabled,
    )
    manager = MagicMock(spec=AgentConfigManager)
    manager.resolve.return_value = config
    return manager


# ===========================================================================
# AgentRegistration schema tests (1–11)
# ===========================================================================

class TestAgentRegistration:

    def test_valid_registration(self):
        """Test 1: Valid registration is constructed without error."""
        reg = make_registration()
        assert reg.agent_type is AITask.DISPATCH
        assert reg.agent_class is AlphaAgent
        assert reg.version == "1.0"
        assert reg.enabled is True

    def test_register_valid_agent_subclass(self):
        """Test 2: A concrete BaseAgent subclass is accepted."""
        reg = make_registration(agent_class=BetaAgent)
        assert reg.agent_class is BetaAgent

    def test_reject_base_agent_itself(self):
        """Test 3: BaseAgent itself is rejected (it is abstract)."""
        with pytest.raises(ValueError, match="abstract"):
            AgentRegistration(
                agent_type=AITask.DISPATCH,
                agent_class=BaseAgent,
                version="1.0",
            )

    def test_reject_abstract_base_agent_subclass(self):
        """Test 4: An abstract BaseAgent subclass is rejected."""
        with pytest.raises(ValueError, match="abstract|concrete"):
            AgentRegistration(
                agent_type=AITask.DISPATCH,
                agent_class=AbstractSubAgent,
                version="1.0",
            )

    def test_reject_non_agent_class(self):
        """Test 5: A class that is not a BaseAgent subclass is rejected."""
        with pytest.raises(ValueError, match="subclass"):
            AgentRegistration(
                agent_type=AITask.DISPATCH,
                agent_class=str,
                version="1.0",
            )

    def test_reject_non_class_agent_class(self):
        """Test 6: A non-class value for agent_class is rejected."""
        with pytest.raises(TypeError, match="class"):
            AgentRegistration(
                agent_type=AITask.DISPATCH,
                agent_class="not-a-class",  # type: ignore[arg-type]
                version="1.0",
            )

    def test_reject_blank_version(self):
        """Test 7: A blank version string is rejected."""
        with pytest.raises(ValueError, match="blank"):
            AgentRegistration(
                agent_type=AITask.DISPATCH,
                agent_class=AlphaAgent,
                version="   ",
            )

    def test_reject_non_string_version(self):
        """Test 8: A non-string version is rejected."""
        with pytest.raises(TypeError, match="string"):
            AgentRegistration(
                agent_type=AITask.DISPATCH,
                agent_class=AlphaAgent,
                version=42,  # type: ignore[arg-type]
            )

    def test_description_none_accepted(self):
        """Test 9: description=None is accepted."""
        reg = make_registration(description=None)
        assert reg.description is None

    def test_description_non_str_rejected(self):
        """Test 10: A non-str description (that is not None) is rejected."""
        with pytest.raises(TypeError, match="str or None"):
            AgentRegistration(
                agent_type=AITask.DISPATCH,
                agent_class=AlphaAgent,
                version="1.0",
                description=42,  # type: ignore[arg-type]
            )

    def test_registration_is_frozen(self):
        """Test 11: Registration is immutable after construction."""
        reg = make_registration()
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            reg.enabled = False  # type: ignore[misc]


# ===========================================================================
# Registry management tests (12–30)
# ===========================================================================

class TestAgentRegistry:

    @pytest.fixture
    def registry(self) -> AgentRegistry:
        return AgentRegistry()

    def test_empty_registry_has_zero_registrations(self, registry):
        """Test 12: An empty registry returns no registrations."""
        assert registry.list_registrations() == ()

    def test_register_valid_agent(self, registry):
        """Test 13: Registering a valid agent stores the registration."""
        reg = make_registration()
        registry.register(registration=reg)
        assert registry.contains(AITask.DISPATCH)

    def test_duplicate_registration_rejected(self, registry):
        """Test 14: Registering the same agent_type twice without replace raises."""
        reg = make_registration()
        registry.register(registration=reg)
        with pytest.raises(AgentAlreadyRegisteredError):
            registry.register(registration=reg)

    def test_explicit_replace_works(self, registry):
        """Test 15: replace=True silently replaces an existing registration."""
        reg_v1 = make_registration(version="1.0")
        reg_v2 = make_registration(version="2.0")
        registry.register(registration=reg_v1)
        registry.register(registration=reg_v2, replace=True)
        assert registry.get(AITask.DISPATCH).version == "2.0"

    def test_get_registration(self, registry):
        """Test 16: get() returns the stored registration."""
        reg = make_registration()
        registry.register(registration=reg)
        result = registry.get(AITask.DISPATCH)
        assert result is reg

    def test_get_missing_raises(self, registry):
        """Test 17: get() raises AgentNotRegisteredError for unregistered type."""
        with pytest.raises(AgentNotRegisteredError):
            registry.get(AITask.PLANNING)

    def test_contains_true(self, registry):
        """Test 18: contains() returns True for registered type."""
        registry.register(registration=make_registration())
        assert registry.contains(AITask.DISPATCH) is True

    def test_contains_false(self, registry):
        """Test 19: contains() returns False for missing type."""
        assert registry.contains(AITask.PLANNING) is False

    def test_unregister_existing_returns_true(self, registry):
        """Test 20: unregister() returns True when the registration existed."""
        registry.register(registration=make_registration())
        result = registry.unregister(AITask.DISPATCH)
        assert result is True
        assert not registry.contains(AITask.DISPATCH)

    def test_unregister_missing_returns_false(self, registry):
        """Test 21: unregister() returns False when nothing was registered."""
        result = registry.unregister(AITask.PLANNING)
        assert result is False

    def test_list_registrations_deterministic(self, registry):
        """Test 22: list_registrations() is deterministic (insertion order)."""
        reg_a = make_registration(agent_type=AITask.PLANNING, agent_class=AlphaAgent)
        reg_b = make_registration(agent_type=AITask.DISPATCH, agent_class=BetaAgent)
        registry.register(registration=reg_a)
        registry.register(registration=reg_b)
        result = registry.list_registrations()
        assert result[0].agent_type is AITask.PLANNING
        assert result[1].agent_type is AITask.DISPATCH

    def test_enabled_only_filter(self, registry):
        """Test 23: enabled_only=True excludes disabled registrations."""
        enabled_reg = make_registration(agent_type=AITask.PLANNING, agent_class=AlphaAgent, enabled=True)
        disabled_reg = make_registration(agent_type=AITask.DISPATCH, agent_class=BetaAgent, enabled=False)
        registry.register(registration=enabled_reg)
        registry.register(registration=disabled_reg)
        enabled = registry.list_registrations(enabled_only=True)
        types = {r.agent_type for r in enabled}
        assert AITask.PLANNING in types
        assert AITask.DISPATCH not in types

    def test_disabled_registration_discoverable(self, registry):
        """Test 24: get() returns disabled registrations."""
        reg = make_registration(enabled=False)
        registry.register(registration=reg)
        result = registry.get(AITask.DISPATCH)
        assert result.enabled is False

    def test_disabled_registration_cannot_create(self, registry):
        """Test 25: create() raises AgentRegistrationDisabledError for disabled types."""
        reg = make_registration(enabled=False)
        registry.register(registration=reg)
        mgr = make_mock_config_manager()
        with pytest.raises(AgentRegistrationDisabledError):
            registry.create(
                agent_type=AITask.DISPATCH,
                tenant_id="tenant-reg",
                config_manager=mgr,
            )

    def test_non_callable_factory_rejected(self, registry):
        """Test 26: A non-callable, non-None factory raises TypeError."""
        with pytest.raises(TypeError, match="callable"):
            registry.register(
                registration=make_registration(),
                factory="not-callable",  # type: ignore[arg-type]
            )

    def test_replaced_log_semantics(self, registry):
        """
        Test 27: replaced=True is logged only when an existing
        registration is actually replaced.
        """

        reg_v1 = make_registration(version="1.0")
        reg_v2 = make_registration(version="2.0")

        with patch(
            "app.services.ai.FieldOpsAI.runtime.agent_registry._logger.info"
        ) as log_mock:

            registry.register(
                registration=reg_v1,
                replace=True,
            )

            first_log = log_mock.call_args

            assert first_log.kwargs["replaced"] is False

            registry.register(
                registration=reg_v2,
                replace=True,
            )

            second_log = log_mock.call_args

            assert second_log.kwargs["replaced"] is True

        assert (
            registry.get(AITask.DISPATCH).version
            == "2.0"
        )
    def test_invalid_agent_type_on_get_raises_type_error(self, registry):
        """Test 28: get() with a non-AITask raises TypeError."""
        with pytest.raises(TypeError, match="AITask"):
            registry.get("dispatch")  # type: ignore[arg-type]

    def test_invalid_agent_type_on_contains_raises_type_error(self, registry):
        """Test 29: contains() with a non-AITask raises TypeError."""
        with pytest.raises(TypeError, match="AITask"):
            registry.contains(99)  # type: ignore[arg-type]

    def test_invalid_agent_type_on_unregister_raises_type_error(self, registry):
        """Test 30: unregister() with a non-AITask raises TypeError."""
        with pytest.raises(TypeError, match="AITask"):
            registry.unregister(None)  # type: ignore[arg-type]


# ===========================================================================
# Agent creation tests (31–45)
# ===========================================================================

class TestAgentRegistryCreate:

    @pytest.fixture
    def registry(self) -> AgentRegistry:
        r = AgentRegistry()
        r.register(registration=make_registration())
        return r

    def test_blank_tenant_raises_value_error(self, registry):
        """Test 31: Blank tenant_id raises ValueError."""
        mgr = make_mock_config_manager()
        with pytest.raises(ValueError, match="blank"):
            registry.create(
                agent_type=AITask.DISPATCH,
                tenant_id="",
                config_manager=mgr,
            )

    def test_non_string_tenant_raises_type_error(self, registry):
        """Test 32: Non-string tenant_id raises TypeError."""
        mgr = make_mock_config_manager()
        with pytest.raises(TypeError, match="string"):
            registry.create(
                agent_type=AITask.DISPATCH,
                tenant_id=123,  # type: ignore[arg-type]
                config_manager=mgr,
            )

    def test_whitespace_tenant_raises_value_error(self, registry):
        """Test 33: Whitespace-only tenant_id raises ValueError after strip."""
        mgr = make_mock_config_manager()
        with pytest.raises(ValueError, match="blank"):
            registry.create(
                agent_type=AITask.DISPATCH,
                tenant_id="   ",
                config_manager=mgr,
            )

    def test_config_manager_without_resolve_raises_type_error(self, registry):
        """Test 34: config_manager with no resolve() raises TypeError."""
        class NoResolve:
            pass

        with pytest.raises(TypeError, match="resolve"):
            registry.create(
                agent_type=AITask.DISPATCH,
                tenant_id="tenant-reg",
                config_manager=NoResolve(),  # type: ignore[arg-type]
            )

    def test_config_manager_non_callable_resolve_raises_type_error(self, registry):
        """Test 35: config_manager.resolve that is not callable raises TypeError."""
        class BadResolve:
            resolve = "not-callable"

        with pytest.raises(TypeError, match="resolve"):
            registry.create(
                agent_type=AITask.DISPATCH,
                tenant_id="tenant-reg",
                config_manager=BadResolve(),  # type: ignore[arg-type]
            )

    def test_config_manager_called_with_correct_args(self, registry):
        """Test 36: config_manager.resolve is called with agent_type and tenant_id."""
        mgr = make_mock_config_manager()
        registry.create(
            agent_type=AITask.DISPATCH,
            tenant_id="tenant-reg",
            config_manager=mgr,
        )
        mgr.resolve.assert_called_once_with(
            agent_type=AITask.DISPATCH,
            tenant_id="tenant-reg",
        )

    def test_non_agent_config_resolved_result_rejected(self, registry):
        """Test 37: resolve() returning a non-AgentConfig raises AgentRegistryError."""
        mgr = MagicMock(spec=AgentConfigManager)
        mgr.resolve.return_value = {"agent_type": "dispatch"}  # dict, not AgentConfig
        with pytest.raises(AgentRegistryError, match="AgentConfig"):
            registry.create(
                agent_type=AITask.DISPATCH,
                tenant_id="tenant-reg",
                config_manager=mgr,
            )

    def test_wrong_resolved_config_agent_type_rejected(self, registry):
        """Test 38: Resolved config with wrong agent_type raises AgentRegistryError."""
        config = AgentConfig(agent_type=AITask.PLANNING, tenant_id="tenant-reg")
        mgr = MagicMock(spec=AgentConfigManager)
        mgr.resolve.return_value = config
        with pytest.raises(AgentRegistryError, match="agent_type"):
            registry.create(
                agent_type=AITask.DISPATCH,
                tenant_id="tenant-reg",
                config_manager=mgr,
            )

    def test_wrong_resolved_config_tenant_rejected(self, registry):
        """Test 39: Resolved config with wrong tenant_id raises AgentRegistryError."""
        config = AgentConfig(agent_type=AITask.DISPATCH, tenant_id="tenant-OTHER")
        mgr = MagicMock(spec=AgentConfigManager)
        mgr.resolve.return_value = config
        with pytest.raises(AgentRegistryError, match="tenant_id"):
            registry.create(
                agent_type=AITask.DISPATCH,
                tenant_id="tenant-reg",
                config_manager=mgr,
            )

    def test_disabled_resolved_config_rejected(self, registry):
        """Test 40: Resolved config with enabled=False raises AgentRegistryError."""
        mgr = make_mock_config_manager(enabled=False)
        with pytest.raises(AgentRegistryError, match="disabled"):
            registry.create(
                agent_type=AITask.DISPATCH,
                tenant_id="tenant-reg",
                config_manager=mgr,
            )

    def test_create_returns_base_agent(self, registry):
        """Test 41: create() returns a BaseAgent instance."""
        mgr = make_mock_config_manager()
        agent = registry.create(
            agent_type=AITask.DISPATCH,
            tenant_id="tenant-reg",
            config_manager=mgr,
        )
        assert isinstance(agent, BaseAgent)

    def test_create_does_not_call_setup(self, registry):
        """Test 42: The returned agent has is_setup=False."""
        mgr = make_mock_config_manager()
        agent = registry.create(
            agent_type=AITask.DISPATCH,
            tenant_id="tenant-reg",
            config_manager=mgr,
        )
        assert agent.is_setup is False

    def test_create_returns_idle_agent(self, registry):
        """Test 43: The returned agent is in IDLE state (never ran)."""
        mgr = make_mock_config_manager()
        agent = registry.create(
            agent_type=AITask.DISPATCH,
            tenant_id="tenant-reg",
            config_manager=mgr,
        )
        assert agent.state is AgentState.IDLE

    def test_create_does_not_register_in_agent_pool(self):
        """Test 44: create() never registers the agent in AgentPool.

        Patches AgentPool.register at the class level so any pool
        instance that create() might access internally is covered.
        """
        from app.services.ai.FieldOpsAI.runtime.agent_pool import AgentPool

        registry = AgentRegistry()
        registry.register(registration=make_registration())
        mgr = make_mock_config_manager()

        with patch.object(AgentPool, "register") as mock_register:
            registry.create(
                agent_type=AITask.DISPATCH,
                tenant_id="tenant-reg",
                config_manager=mgr,
            )
            mock_register.assert_not_called()

    def test_two_creates_return_different_instances(self, registry):
        """Test 45: Each create() call returns a distinct agent instance."""
        mgr = make_mock_config_manager()
        agent_a = registry.create(
            agent_type=AITask.DISPATCH,
            tenant_id="tenant-reg",
            config_manager=mgr,
        )
        agent_b = registry.create(
            agent_type=AITask.DISPATCH,
            tenant_id="tenant-reg",
            config_manager=mgr,
        )
        assert agent_a is not agent_b
        assert agent_a.agent_id != agent_b.agent_id


# ===========================================================================
# Custom factory tests (46–54)
# ===========================================================================

class TestAgentRegistryFactory:

    def test_custom_factory_receives_config_and_orchestrator(self):
        """Test 46: Custom factory is called with config and orchestrator."""
        received: dict[str, Any] = {}

        def my_factory(config: AgentConfig, orchestrator: object | None) -> AlphaAgent:
            received["config"] = config
            received["orchestrator"] = orchestrator
            return AlphaAgent(config)

        registry = AgentRegistry()
        registry.register(registration=make_registration(), factory=my_factory)
        sentinel = object()
        mgr = make_mock_config_manager()
        registry.create(
            agent_type=AITask.DISPATCH,
            tenant_id="tenant-reg",
            config_manager=mgr,
            orchestrator=sentinel,
        )
        assert received["orchestrator"] is sentinel
        assert isinstance(received["config"], AgentConfig)

    def test_falsey_factory_is_retained(self):
        """Test 47: A falsey factory is stored via explicit None check.

        A factory whose __bool__ returns False must still be called
        by create() — it must not be silently discarded.
        """
        call_log: list[str] = []

        class FalseyCallable:
            def __bool__(self) -> bool:
                return False

            def __call__(
                self, config: AgentConfig, orchestrator: object | None
            ) -> AlphaAgent:
                call_log.append("called")
                return AlphaAgent(config)

        factory = FalseyCallable()
        assert not bool(factory)

        registry = AgentRegistry()
        registry.register(registration=make_registration(), factory=factory)  # type: ignore[arg-type]
        mgr = make_mock_config_manager()
        registry.create(
            agent_type=AITask.DISPATCH,
            tenant_id="tenant-reg",
            config_manager=mgr,
        )
        assert "called" in call_log

    def test_non_agent_factory_result_rejected(self):
        """Test 48: A factory returning a non-BaseAgent raises AgentRegistryError."""
        def bad_factory(config: AgentConfig, orchestrator: object | None) -> object:
            return object()

        registry = AgentRegistry()
        registry.register(registration=make_registration(), factory=bad_factory)  # type: ignore[arg-type]
        mgr = make_mock_config_manager()
        with pytest.raises(AgentRegistryError, match="non-BaseAgent"):
            registry.create(
                agent_type=AITask.DISPATCH,
                tenant_id="tenant-reg",
                config_manager=mgr,
            )

    def test_wrong_type_factory_result_rejected(self):
        """Test 49: A factory returning an agent with the wrong agent_type raises."""
        def wrong_type_factory(
            config: AgentConfig, orchestrator: object | None
        ) -> AlphaAgent:
            wrong_config = AgentConfig(
                agent_type=AITask.PLANNING,
                tenant_id=config.tenant_id,
            )
            return AlphaAgent(wrong_config)

        registry = AgentRegistry()
        registry.register(registration=make_registration(agent_type=AITask.DISPATCH), factory=wrong_type_factory)
        mgr = make_mock_config_manager(agent_type=AITask.DISPATCH)
        with pytest.raises(AgentRegistryError, match="agent_type"):
            registry.create(
                agent_type=AITask.DISPATCH,
                tenant_id="tenant-reg",
                config_manager=mgr,
            )

    def test_wrong_tenant_factory_result_rejected(self):
        """Test 50: A factory returning an agent with the wrong tenant raises."""
        registry = AgentRegistry()
        registry.register(
            registration=make_registration(agent_type=AITask.DISPATCH, agent_class=WrongTenantAgent),
        )
        mgr = make_mock_config_manager(agent_type=AITask.DISPATCH, tenant_id="tenant-reg")
        with pytest.raises(AgentRegistryError, match="tenant_id"):
            registry.create(
                agent_type=AITask.DISPATCH,
                tenant_id="tenant-reg",
                config_manager=mgr,
            )

    def test_initialized_factory_result_rejected(self):
        """Test 51: A factory returning an already set-up agent raises AgentRegistryError."""
        import asyncio

        def setup_factory(
            config: AgentConfig, orchestrator: object | None
        ) -> AlphaAgent:
            agent = AlphaAgent(config)
            # Force is_setup=True without calling the full async setup
            agent._is_setup = True
            return agent

        registry = AgentRegistry()
        registry.register(registration=make_registration(), factory=setup_factory)
        mgr = make_mock_config_manager()
        with pytest.raises(AgentRegistryError, match="is_setup"):
            registry.create(
                agent_type=AITask.DISPATCH,
                tenant_id="tenant-reg",
                config_manager=mgr,
            )

    def test_non_idle_factory_result_rejected(self):
        """Test 52: A factory returning an agent not in IDLE state raises AgentRegistryError."""
        def non_idle_factory(
            config: AgentConfig, orchestrator: object | None
        ) -> AlphaAgent:
            agent = AlphaAgent(config)
            agent._state = AgentState.ERROR
            return agent

        registry = AgentRegistry()
        registry.register(registration=make_registration(), factory=non_idle_factory)
        mgr = make_mock_config_manager()
        with pytest.raises(AgentRegistryError, match="IDLE|state"):
            registry.create(
                agent_type=AITask.DISPATCH,
                tenant_id="tenant-reg",
                config_manager=mgr,
            )

    def test_singleton_factory_result_rejected(self):
        """Test 53: A factory that returns the same agent (reused UUID) raises AgentRegistryError."""
        singleton = AlphaAgent(AgentConfig(agent_type=AITask.DISPATCH, tenant_id="tenant-reg"))

        def singleton_factory(
            config: AgentConfig, orchestrator: object | None
        ) -> AlphaAgent:
            return singleton

        registry = AgentRegistry()
        registry.register(registration=make_registration(), factory=singleton_factory)
        mgr = make_mock_config_manager()

        # First call should succeed
        agent = registry.create(
            agent_type=AITask.DISPATCH,
            tenant_id="tenant-reg",
            config_manager=mgr,
        )
        assert agent is singleton

        # Second call must fail — same UUID already issued
        with pytest.raises(AgentRegistryError, match="UUID|reused|already issued"):
            registry.create(
                agent_type=AITask.DISPATCH,
                tenant_id="tenant-reg",
                config_manager=mgr,
            )

    def test_concurrent_reuse_detection(self):
        """Test 54: Concurrent calls with a shared singleton detect UUID reuse."""
        singleton = AlphaAgent(AgentConfig(agent_type=AITask.DISPATCH, tenant_id="tenant-reg"))
        call_count = 0
        first_return_count = 0

        def singleton_factory(
            config: AgentConfig, orchestrator: object | None
        ) -> AlphaAgent:
            return singleton

        registry = AgentRegistry()
        registry.register(registration=make_registration(), factory=singleton_factory)

        errors: list[Exception] = []
        successes: list[Any] = []

        def try_create() -> None:
            mgr = make_mock_config_manager()
            try:
                agent = registry.create(
                    agent_type=AITask.DISPATCH,
                    tenant_id="tenant-reg",
                    config_manager=mgr,
                )
                successes.append(agent)
            except AgentRegistryError:
                errors.append(AgentRegistryError("reuse detected"))

        threads = [threading.Thread(target=try_create) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Exactly one success; all others must have raised AgentRegistryError
        assert len(successes) == 1
        assert len(errors) == 9


# ===========================================================================
# Default registry tests (55–57)
# ===========================================================================

class TestDefaultRegistry:

    def test_default_registry_contains_planning_and_dispatch(self):
        """Test 55: Default registry has Planning and Dispatch registered."""
        registry = create_default_agent_registry()
        assert registry.contains(AITask.PLANNING)
        assert registry.contains(AITask.DISPATCH)

    def test_default_registry_excludes_unmigrated_agents(self):
        """Test 56: Unmigrated agents are NOT registered."""
        registry = create_default_agent_registry()
        assert registry.contains(AITask.CLOSURE)
        unmigrated = [AITask.MONITORING, AITask.SENTIMENT, AITask.COMMUNICATION]
        for task in unmigrated:
            assert not registry.contains(task), f"{task.value} should not be registered"

    def test_default_registry_calls_return_independent_registries(self):
        """Test 57: Two calls return separate registry objects."""
        r1 = create_default_agent_registry()
        r2 = create_default_agent_registry()
        assert r1 is not r2
        r1.unregister(AITask.PLANNING)
        assert not r1.contains(AITask.PLANNING)
        assert r2.contains(AITask.PLANNING)

    def test_planning_creation_succeeds(self):
        """Planning creation with mocked config manager succeeds."""
        from app.services.ai.FieldOpsAI.agents.planning_agent import PlanningAgent
        registry = create_default_agent_registry()
        config = AgentConfig(agent_type=AITask.PLANNING, tenant_id="tenant-plan")
        mgr = MagicMock(spec=AgentConfigManager)
        mgr.resolve.return_value = config
        agent = registry.create(
            agent_type=AITask.PLANNING,
            tenant_id="tenant-plan",
            config_manager=mgr,
        )
        assert isinstance(agent, PlanningAgent)
        assert agent.tenant_id == "tenant-plan"
        assert agent.state is AgentState.IDLE

    def test_dispatch_creation_succeeds(self):
        """Dispatch creation with mocked config manager succeeds."""
        from app.services.ai.FieldOpsAI.agents.dispatch_agent import DispatchAgent
        registry = create_default_agent_registry()
        config = AgentConfig(agent_type=AITask.DISPATCH, tenant_id="tenant-disp")
        mgr = MagicMock(spec=AgentConfigManager)
        mgr.resolve.return_value = config
        agent = registry.create(
            agent_type=AITask.DISPATCH,
            tenant_id="tenant-disp",
            config_manager=mgr,
        )
        assert isinstance(agent, DispatchAgent)
        assert agent.tenant_id == "tenant-disp"
        assert agent.state is AgentState.IDLE


# ===========================================================================
# Structural / behavioral tests (58–59)
# ===========================================================================

class TestRegistryStructuralBehavior:

    def test_registry_stores_definitions_not_live_instances(self):
        """Test 58: Registry's internal mapping stores AgentRegistration, not BaseAgent."""
        registry = AgentRegistry()
        registry.register(registration=make_registration())
        for value in registry._registrations.values():
            assert isinstance(value, AgentRegistration)
            assert not isinstance(value, BaseAgent)

    def test_concurrent_registration_and_lookup_correctness(self):
        """Test 59: Concurrent registrations and lookups do not corrupt mappings."""
        registry = AgentRegistry()
        errors: list[str] = []

        def register_worker(n: int) -> None:
            try:
                if n % 2 == 0:
                    registry.register(
                        registration=make_registration(agent_type=AITask.DISPATCH, agent_class=AlphaAgent),
                        replace=True,
                    )
                else:
                    registry.register(
                        registration=make_registration(agent_type=AITask.PLANNING, agent_class=BetaAgent),
                        replace=True,
                    )
            except Exception as e:
                errors.append(str(e))

        def lookup_worker() -> None:
            try:
                _ = registry.list_registrations()
                _ = registry.contains(AITask.DISPATCH)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=register_worker, args=(i,)) for i in range(20)]
        threads += [threading.Thread(target=lookup_worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Concurrent errors: {errors}"
        _ = registry.list_registrations()


class TestRegistryValidationEdgeCases:
    def test_register_invalid_registration(self):
        """Test: register raises TypeError if registration is not an AgentRegistration."""
        registry = AgentRegistry()
        with pytest.raises(TypeError, match="registration must be an AgentRegistration instance"):
            registry.register(registration="not-a-registration")

    def test_create_invalid_agent_type(self):
        """Test: create raises TypeError if agent_type is not an AITask member."""
        registry = AgentRegistry()
        config_mgr = MagicMock(spec=AgentConfigManager)
        with pytest.raises(TypeError, match="agent_type must be an AITask member"):
            registry.create(agent_type="not-an-ai-task", tenant_id="tenant-1", config_manager=config_mgr)

    def test_create_unregistered_agent_type(self):
        """Test: create raises AgentNotRegisteredError if agent_type is unregistered."""
        registry = AgentRegistry()
        config_mgr = MagicMock(spec=AgentConfigManager)
        with pytest.raises(AgentNotRegisteredError, match="is not registered"):
            registry.create(agent_type=AITask.PLANNING, tenant_id="tenant-1", config_manager=config_mgr)
