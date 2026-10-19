"""
test_agent_config_manager.py

Unit tests for AgentConfigManager covering resolution logic, precedence rules,
input validation, edge cases, and safety constraints.
"""

from typing import Any
import pytest
from pydantic import ValidationError

from app.services.ai.FieldOpsAI.config.agent_config_manager import (
    AgentConfigManager,
    AgentConfigurationError,
    AgentConfigurationNotFoundError,
    AgentConfigurationOverrideError,
)
from app.services.ai.FieldOpsAI.config.config_loader import ConfigLoader
from app.services.ai.FieldOpsAI.schemas.agent_config import AgentConfig
from app.services.ai.FieldOpsAI.schemas.ai_task import AITask


class MockConfigLoader:
    """
    Mock loader implementing the same public snapshot method.
    """
    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config

    def get_config_snapshot(self) -> dict[str, Any]:
        import copy
        return copy.deepcopy(self._config)


@pytest.fixture
def base_config_data() -> dict[str, Any]:
    return {
        "agents": {
            "defaults": {
                "agent_version": "1.0",
                "timeout_seconds": 30.0,
                "max_retries": 2,
                "enabled": True,
            },
            "planning": {"timeout_seconds": 15.0},
            "dispatch": {"max_retries": 5},
            "monitoring": {},
            "sentiment": {},
            "communication": {"agent_version": "2.0"},
            "closure": {"enabled": False},
        }
    }


def test_resolve_six_aitasks(base_config_data: dict[str, Any]) -> None:
    """
    1. Resolving a valid configuration for each of the six AITask values
    """
    loader = MockConfigLoader(base_config_data)
    manager = AgentConfigManager(config_loader=loader)  # type: ignore

    for task in AITask:
        config = manager.resolve(agent_type=task, tenant_id="tenant-123")
        assert isinstance(config, AgentConfig)
        assert config.agent_type == task
        assert config.tenant_id == "tenant-123"


def test_real_communication_agent_config_resolves_with_generation_temperature():
    """Provider generation settings stay separate from strict AgentConfig."""
    loader = ConfigLoader()
    manager = AgentConfigManager(config_loader=loader)

    resolved = manager.resolve(
        agent_type=AITask.COMMUNICATION,
        tenant_id="customer-tenant",
    )

    assert resolved.timeout_seconds == 5.0
    assert resolved.tenant_id == "customer-tenant"
    assert (
        loader.get_config_snapshot()["communication_generation"][
            "in_app_temperature"
        ]
        == 0.7
    )


def test_shared_defaults(base_config_data: dict[str, Any]) -> None:
    """
    2. Shared defaults
    """
    loader = MockConfigLoader(base_config_data)
    manager = AgentConfigManager(config_loader=loader)  # type: ignore

    config = manager.resolve(agent_type=AITask.SENTIMENT, tenant_id="tenant-123")
    assert config.agent_version == "1.0"
    assert config.timeout_seconds == 30.0
    assert config.max_retries == 2
    assert config.enabled is True


def test_agent_specific_yaml_overrides(base_config_data: dict[str, Any]) -> None:
    """
    3. Agent-specific YAML overrides
    """
    loader = MockConfigLoader(base_config_data)
    manager = AgentConfigManager(config_loader=loader)  # type: ignore

    # Planning overrides timeout_seconds
    planning_config = manager.resolve(agent_type=AITask.PLANNING, tenant_id="tenant-123")
    assert planning_config.timeout_seconds == 15.0
    assert planning_config.agent_version == "1.0"  # fell back to defaults

    # Dispatch overrides max_retries
    dispatch_config = manager.resolve(agent_type=AITask.DISPATCH, tenant_id="tenant-123")
    assert dispatch_config.max_retries == 5
    assert dispatch_config.timeout_seconds == 30.0  # fell back to defaults


def test_runtime_override_precedence(base_config_data: dict[str, Any]) -> None:
    """
    4. Runtime override precedence
    """
    loader = MockConfigLoader(base_config_data)
    manager = AgentConfigManager(config_loader=loader)  # type: ignore

    # YAML defaults max_retries to 2, Dispatch overrides it to 5. Runtime overrides it to 10.
    config = manager.resolve(
        agent_type=AITask.DISPATCH,
        tenant_id="tenant-123",
        overrides={"max_retries": 10}
    )
    assert config.max_retries == 10


def test_runtime_override_does_not_mutate_loaded_yaml(base_config_data: dict[str, Any]) -> None:
    """
    5. Runtime override does not mutate loaded YAML
    """
    loader = MockConfigLoader(base_config_data)
    manager = AgentConfigManager(config_loader=loader)  # type: ignore

    overrides = {"timeout_seconds": 10.0}
    config1 = manager.resolve(
        agent_type=AITask.PLANNING,
        tenant_id="tenant-123",
        overrides=overrides
    )
    assert config1.timeout_seconds == 10.0

    config2 = manager.resolve(agent_type=AITask.PLANNING, tenant_id="tenant-123")
    assert config2.timeout_seconds == 15.0
    assert base_config_data["agents"]["planning"]["timeout_seconds"] == 15.0


def test_agent_type_is_authoritative(base_config_data: dict[str, Any]) -> None:
    """
    6. agent_type is authoritative
    """
    loader = MockConfigLoader(base_config_data)
    manager = AgentConfigManager(config_loader=loader)  # type: ignore

    config = manager.resolve(agent_type=AITask.MONITORING, tenant_id="tenant-123")
    assert config.agent_type == AITask.MONITORING


def test_tenant_id_is_authoritative(base_config_data: dict[str, Any]) -> None:
    """
    7. tenant_id is authoritative
    """
    loader = MockConfigLoader(base_config_data)
    manager = AgentConfigManager(config_loader=loader)  # type: ignore

    config = manager.resolve(agent_type=AITask.MONITORING, tenant_id="my-custom-tenant")
    assert config.tenant_id == "my-custom-tenant"


def test_reject_override_agent_type(base_config_data: dict[str, Any]) -> None:
    """
    8. Rejecting an override for agent_type
    """
    loader = MockConfigLoader(base_config_data)
    manager = AgentConfigManager(config_loader=loader)  # type: ignore

    with pytest.raises(AgentConfigurationOverrideError) as exc_info:
        manager.resolve(
            agent_type=AITask.PLANNING,
            tenant_id="tenant-123",
            overrides={"agent_type": AITask.DISPATCH}
        )
    assert "agent_type" in str(exc_info.value)


def test_reject_override_tenant_id(base_config_data: dict[str, Any]) -> None:
    """
    9. Rejecting an override for tenant_id
    """
    loader = MockConfigLoader(base_config_data)
    manager = AgentConfigManager(config_loader=loader)  # type: ignore

    with pytest.raises(AgentConfigurationOverrideError) as exc_info:
        manager.resolve(
            agent_type=AITask.PLANNING,
            tenant_id="tenant-123",
            overrides={"tenant_id": "malicious-tenant"}
        )
    assert "tenant_id" in str(exc_info.value)


def test_reject_unknown_override_key(base_config_data: dict[str, Any]) -> None:
    """
    10. Rejecting an unknown override key
    """
    loader = MockConfigLoader(base_config_data)
    manager = AgentConfigManager(config_loader=loader)  # type: ignore

    with pytest.raises(AgentConfigurationOverrideError) as exc_info:
        manager.resolve(
            agent_type=AITask.PLANNING,
            tenant_id="tenant-123",
            overrides={"spelling_mistake": "value"}
        )
    assert "spelling_mistake" in str(exc_info.value)


def test_reject_blank_tenant_id(base_config_data: dict[str, Any]) -> None:
    """
    11. Rejecting blank tenant ID
    """
    loader = MockConfigLoader(base_config_data)
    manager = AgentConfigManager(config_loader=loader)  # type: ignore

    with pytest.raises(AgentConfigurationError) as exc_info:
        manager.resolve(agent_type=AITask.PLANNING, tenant_id="   ")
    assert "tenant_id" in str(exc_info.value)


def test_reject_non_string_tenant_id(base_config_data: dict[str, Any]) -> None:
    """
    12. Rejecting non-string tenant ID
    """
    loader = MockConfigLoader(base_config_data)
    manager = AgentConfigManager(config_loader=loader)  # type: ignore

    with pytest.raises(AgentConfigurationError) as exc_info:
        manager.resolve(agent_type=AITask.PLANNING, tenant_id=123)  # type: ignore
    assert "tenant_id" in str(exc_info.value)


def test_reject_non_aitask_agent_type(base_config_data: dict[str, Any]) -> None:
    """
    13. Rejecting a non-AITask agent type
    """
    loader = MockConfigLoader(base_config_data)
    manager = AgentConfigManager(config_loader=loader)  # type: ignore

    with pytest.raises(AgentConfigurationError) as exc_info:
        manager.resolve(agent_type="not-an-aitask", tenant_id="tenant-123")  # type: ignore
    assert "agent_type" in str(exc_info.value)


def test_reject_non_mapping_overrides(base_config_data: dict[str, Any]) -> None:
    """
    14. Rejecting non-mapping overrides
    """
    loader = MockConfigLoader(base_config_data)
    manager = AgentConfigManager(config_loader=loader)  # type: ignore

    with pytest.raises(AgentConfigurationError) as exc_info:
        manager.resolve(
            agent_type=AITask.PLANNING,
            tenant_id="tenant-123",
            overrides=["not", "a", "mapping"]  # type: ignore
        )
    assert "overrides" in str(exc_info.value)


def test_missing_agents_section_falls_back_safely() -> None:
    """
    15. Missing agents section falls back safely
    """
    loader = MockConfigLoader({})  # empty config dict
    manager = AgentConfigManager(config_loader=loader)  # type: ignore

    config = manager.resolve(agent_type=AITask.PLANNING, tenant_id="tenant-123")
    assert config.agent_version == "1.0"
    assert config.timeout_seconds == 30.0


def test_missing_defaults_section_falls_back_safely() -> None:
    """
    16. Missing defaults section falls back safely
    """
    loader = MockConfigLoader({"agents": {}})
    manager = AgentConfigManager(config_loader=loader)  # type: ignore

    config = manager.resolve(agent_type=AITask.PLANNING, tenant_id="tenant-123")
    assert config.agent_version == "1.0"
    assert config.timeout_seconds == 30.0


def test_missing_agent_specific_section_falls_back_safely() -> None:
    """
    17. Missing agent-specific section falls back safely
    """
    loader = MockConfigLoader({
        "agents": {
            "defaults": {
                "agent_version": "1.5"
            }
        }
    })
    manager = AgentConfigManager(config_loader=loader)  # type: ignore

    config = manager.resolve(agent_type=AITask.PLANNING, tenant_id="tenant-123")
    assert config.agent_version == "1.5"
    assert config.timeout_seconds == 30.0


def test_invalid_agent_specific_yaml_section_type() -> None:
    """
    18. Invalid agent-specific YAML section type
    """
    loader = MockConfigLoader({
        "agents": {
            "planning": "should-be-a-mapping-but-is-string"
        }
    })
    manager = AgentConfigManager(config_loader=loader)  # type: ignore

    with pytest.raises(AgentConfigurationError) as exc_info:
        manager.resolve(agent_type=AITask.PLANNING, tenant_id="tenant-123")
    assert "agent-specific YAML section" in str(exc_info.value)


def test_invalid_final_agent_config_values(base_config_data: dict[str, Any]) -> None:
    """
    19. Invalid final AgentConfig values
    """
    loader = MockConfigLoader(base_config_data)
    manager = AgentConfigManager(config_loader=loader)  # type: ignore

    with pytest.raises(AgentConfigurationError) as exc_info:
        manager.resolve(
            agent_type=AITask.PLANNING,
            tenant_id="tenant-123",
            overrides={"timeout_seconds": -5.0}
        )
    assert exc_info.value.__cause__ is not None
    assert isinstance(exc_info.value.__cause__, ValidationError)
    assert "Failed to validate final resolved AgentConfig" in str(exc_info.value)


def test_independent_results_for_different_tenants(base_config_data: dict[str, Any]) -> None:
    """
    20. Independent results for different tenants
    """
    loader = MockConfigLoader(base_config_data)
    manager = AgentConfigManager(config_loader=loader)  # type: ignore

    config_t1 = manager.resolve(agent_type=AITask.PLANNING, tenant_id="tenant-1")
    config_t2 = manager.resolve(agent_type=AITask.PLANNING, tenant_id="tenant-2")

    assert config_t1.tenant_id == "tenant-1"
    assert config_t2.tenant_id == "tenant-2"
    assert config_t1 is not config_t2


def test_repeated_resolution_is_deterministic(base_config_data: dict[str, Any]) -> None:
    """
    21. Repeated resolution is deterministic
    """
    loader = MockConfigLoader(base_config_data)
    manager = AgentConfigManager(config_loader=loader)  # type: ignore

    config1 = manager.resolve(agent_type=AITask.PLANNING, tenant_id="tenant-123")
    config2 = manager.resolve(agent_type=AITask.PLANNING, tenant_id="tenant-123")

    assert config1.agent_version == config2.agent_version
    assert config1.timeout_seconds == config2.timeout_seconds
    assert config1.max_retries == config2.max_retries
    assert config1.enabled == config2.enabled


def test_boolean_strictness_for_enabled(base_config_data: dict[str, Any]) -> None:
    """
    22. Boolean strictness for enabled
    """
    loader = MockConfigLoader(base_config_data)
    manager = AgentConfigManager(config_loader=loader)  # type: ignore

    with pytest.raises(AgentConfigurationError) as exc_info:
        manager.resolve(
            agent_type=AITask.PLANNING,
            tenant_id="tenant-123",
            overrides={"enabled": "True"}  # type: ignore
        )
    assert "Failed to validate final resolved AgentConfig" in str(exc_info.value)


def test_no_mutation_across_repeated_calls(base_config_data: dict[str, Any]) -> None:
    """
    23. No mutation across repeated calls
    """
    loader = MockConfigLoader(base_config_data)
    manager = AgentConfigManager(config_loader=loader)  # type: ignore

    overrides = {"timeout_seconds": 12.0}
    config1 = manager.resolve(
        agent_type=AITask.PLANNING,
        tenant_id="tenant-123",
        overrides=overrides
    )
    assert config1.timeout_seconds == 12.0
    assert overrides == {"timeout_seconds": 12.0}

    config2 = manager.resolve(
        agent_type=AITask.PLANNING,
        tenant_id="tenant-123"
    )
    assert config2.timeout_seconds == 15.0


def test_config_loader_not_dictionary() -> None:
    """
    Test when config_loader is not valid config.
    """
    class BadConfigLoader:
        def get_config_snapshot(self) -> Any:
            return "not-a-dict"

    manager = AgentConfigManager(config_loader=BadConfigLoader())  # type: ignore
    with pytest.raises(AgentConfigurationNotFoundError) as exc_info:
        manager.resolve(agent_type=AITask.PLANNING, tenant_id="tenant-123")
    assert "Unable to retrieve underlying YAML configuration snapshot" in str(exc_info.value)


def test_agents_not_mapping() -> None:
    """
    Test when 'agents' is string instead of mapping.
    """
    loader = MockConfigLoader({"agents": "invalid-string"})
    manager = AgentConfigManager(config_loader=loader)  # type: ignore

    with pytest.raises(AgentConfigurationError) as exc_info:
        manager.resolve(agent_type=AITask.PLANNING, tenant_id="tenant-123")
    assert "The 'agents' section in YAML configuration must be a mapping" in str(exc_info.value)


def test_defaults_not_mapping() -> None:
    """
    Test when 'defaults' is string instead of mapping.
    """
    loader = MockConfigLoader({
        "agents": {
            "defaults": "invalid-string"
        }
    })
    manager = AgentConfigManager(config_loader=loader)  # type: ignore

    with pytest.raises(AgentConfigurationError) as exc_info:
        manager.resolve(agent_type=AITask.PLANNING, tenant_id="tenant-123")
    assert "The 'defaults' agent section in YAML must be a mapping" in str(exc_info.value)


# ==========================================================
# Hardening Review Scenario Additions
# ==========================================================

def test_closure_specific_yaml_enabled_false(base_config_data: dict[str, Any]) -> None:
    """
    Harden 1. Closure-specific YAML value `enabled: false`
    """
    loader = MockConfigLoader(base_config_data)
    manager = AgentConfigManager(config_loader=loader)  # type: ignore
    config = manager.resolve(agent_type=AITask.CLOSURE, tenant_id="tenant-123")
    assert config.enabled is False


def test_supplied_falsey_loader_is_not_replaced_by_configloader() -> None:
    """
    Harden 2. A supplied falsey loader is not replaced by ConfigLoader
    """
    class FalseyLoader:
        def __bool__(self) -> bool:
            return False

        def get_config_snapshot(self) -> dict[str, Any]:
            return {"agents": {"defaults": {"enabled": True}}}

    loader = FalseyLoader()
    manager = AgentConfigManager(config_loader=loader)  # type: ignore
    assert manager._config_loader is loader

    config = manager.resolve(agent_type=AITask.PLANNING, tenant_id="tenant-123")
    assert config.enabled is True


def test_manager_uses_public_config_loader_interface(base_config_data: dict[str, Any]) -> None:
    """
    Harden 3. The manager uses the public ConfigLoader interface (get_config_snapshot)
    """
    from unittest.mock import MagicMock
    mock_loader = MagicMock()
    del mock_loader._config
    mock_loader.get_config_snapshot.return_value = base_config_data
    manager = AgentConfigManager(config_loader=mock_loader)

    manager.resolve(agent_type=AITask.PLANNING, tenant_id="tenant-123")
    mock_loader.get_config_snapshot.assert_called_once()


def test_public_config_loader_snapshot_cannot_mutate_internal_config() -> None:
    """
    Harden 4. The public ConfigLoader snapshot cannot mutate internal configuration
    """
    loader = ConfigLoader()
    snapshot = loader.get_config_snapshot()

    # Modify the snapshot dictionary structure
    snapshot["agents"]["defaults"]["agent_version"] = "CORRUPTED"

    # Get a fresh snapshot and check that original value is preserved
    snapshot2 = loader.get_config_snapshot()
    assert snapshot2["agents"]["defaults"]["agent_version"] == "1.0"


def test_loader_failure_wrapped_in_not_found_error() -> None:
    """
    Harden 5. Loader failure is wrapped in AgentConfigurationNotFoundError with the original cause
    """
    class FailingLoader:
        def get_config_snapshot(self) -> dict[str, Any]:
            raise OSError("Simulated disk read failure")

    manager = AgentConfigManager(config_loader=FailingLoader())  # type: ignore
    with pytest.raises(AgentConfigurationNotFoundError) as exc_info:
        manager.resolve(agent_type=AITask.PLANNING, tenant_id="tenant-123")
    assert isinstance(exc_info.value.__cause__, OSError)
    assert str(exc_info.value.__cause__) == "Simulated disk read failure"


def test_loader_init_failure_wrapped_in_not_found_error() -> None:
    """
    Harden 5 (continued). Loader init failure is wrapped in AgentConfigurationNotFoundError
    """
    from unittest.mock import patch
    with patch("app.services.ai.FieldOpsAI.config.config_loader.ConfigLoader.__init__", side_effect=FileNotFoundError("File not found")):
        with pytest.raises(AgentConfigurationNotFoundError) as exc_info:
            AgentConfigManager(config_loader=None)
        assert isinstance(exc_info.value.__cause__, FileNotFoundError)


def test_unexpected_non_validation_exceptions_propagate() -> None:
    """
    Harden 6. Unexpected non-validation exceptions are not incorrectly reported as Pydantic validation failures
    """
    from unittest.mock import patch
    manager = AgentConfigManager()
    with patch("app.services.ai.FieldOpsAI.config.agent_config_manager.AgentConfig", side_effect=RuntimeError("Unexpected DB / system fail")):
        with pytest.raises(RuntimeError) as exc_info:
            manager.resolve(agent_type=AITask.PLANNING, tenant_id="tenant-123")
        # Assert that it propagated directly and is NOT wrapped in AgentConfigurationError
        assert str(exc_info.value) == "Unexpected DB / system fail"


def test_existing_runtime_overrides_remain_unmodified(base_config_data: dict[str, Any]) -> None:
    """
    Harden 7. Existing runtime overrides remain unmodified
    """
    loader = MockConfigLoader(base_config_data)
    manager = AgentConfigManager(config_loader=loader)  # type: ignore
    overrides = {"agent_version": "3.5", "timeout_seconds": 22.0}

    manager.resolve(agent_type=AITask.PLANNING, tenant_id="tenant-123", overrides=overrides)
    assert overrides == {"agent_version": "3.5", "timeout_seconds": 22.0}


def test_existing_yaml_config_remains_unmodified(base_config_data: dict[str, Any]) -> None:
    """
    Harden 8. Existing YAML configuration remains unmodified
    """
    loader = MockConfigLoader(base_config_data)
    manager = AgentConfigManager(config_loader=loader)  # type: ignore

    manager.resolve(agent_type=AITask.PLANNING, tenant_id="tenant-123")
    assert base_config_data["agents"]["planning"]["timeout_seconds"] == 15.0


def test_real_ai_yaml_resolves_all_six_aitasks() -> None:
    """
    Harden 9. Real ai.yaml still resolves all six AITask values
    """
    manager = AgentConfigManager()
    for task in AITask:
        config = manager.resolve(agent_type=task, tenant_id="real-tenant-test")
        assert isinstance(config, AgentConfig)
        assert config.agent_type == task
        assert config.tenant_id == "real-tenant-test"
