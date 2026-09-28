import pytest

from app.tools.examples import (
    fetch_customer_schema,
    generate_sms_schema,
    get_eta_schema,
)
from app.tools.registry import (
    ToolRegistry,
    create_default_registry,
)
from app.tools.schema import ToolSchema


# ============================================================
# Decorator
# ============================================================

def test_tool_decorator_registers_function():
    registry = ToolRegistry()

    @registry.tool(
        schema=generate_sms_schema(),
        category="communication",
        capabilities={"sms"},
    )
    def generate_sms(message: str, priority: str = "normal"):
        return message

    registered = registry.get_tool("generate_sms")

    assert registered is not None
    assert registered.schema.contract.name == "generate_sms"
    assert registered.handler is not None
    assert registered.category == "communication"
    assert "sms" in registered.capabilities

    assert generate_sms("Hello") == "Hello"


# ============================================================
# Search
# ============================================================

def test_registry_search_by_category():
    registry = ToolRegistry()

    registry.register_tool(
        generate_sms_schema(),
        category="communication",
        capabilities={"sms"},
    )

    results = registry.search_tools(category="communication")

    assert len(results) == 1
    assert results[0].schema.contract.name == "generate_sms"


def test_registry_search_by_capability():
    registry = ToolRegistry()

    registry.register_tool(
        generate_sms_schema(),
        category="communication",
        capabilities={"sms"},
    )

    results = registry.search_tools(capability="sms")

    assert len(results) == 1
    assert results[0].schema.contract.name == "generate_sms"


def test_registry_search_by_name():
    registry = ToolRegistry()

    registry.register_tool(
        generate_sms_schema(),
        category="communication",
        capabilities={"sms"},
    )

    results = registry.search_tools(name="generate_sms")

    assert len(results) == 1
    assert results[0].schema.contract.name == "generate_sms"


# ============================================================
# Health
# ============================================================

def test_registry_get_health():
    registry = ToolRegistry()

    registry.register_tool(
        generate_sms_schema(),
        category="communication",
        capabilities={"sms"},
    )

    assert registry.get_health("generate_sms") == "healthy"


def test_registry_set_health():
    registry = ToolRegistry()

    registry.register_tool(
        generate_sms_schema(),
        category="communication",
        capabilities={"sms"},
    )

    result = registry.set_health(
        "generate_sms",
        "unhealthy",
    )

    assert result is True
    assert registry.get_health("generate_sms") == "unhealthy"


def test_registry_health_unknown_tool():
    registry = ToolRegistry()

    assert registry.get_health("unknown_tool") is None
    assert registry.set_health(
        "unknown_tool",
        "unhealthy",
    ) is False


# ============================================================
# Dependencies
# ============================================================

def test_registry_get_dependencies():
    registry = ToolRegistry()

    registry.register_tool(
        generate_sms_schema(),
        category="communication",
        capabilities={"sms"},
        dependencies={"redis", "groq"},
    )

    dependencies = registry.get_dependencies(
        "generate_sms"
    )

    assert dependencies == {"redis", "groq"}


def test_registry_dependency_graph():
    registry = ToolRegistry()

    registry.register_tool(
        generate_sms_schema(),
        category="communication",
        capabilities={"sms"},
        dependencies={"redis"},
    )

    registry.register_tool(
        fetch_customer_schema(),
        category="customer",
        capabilities={"customer"},
        dependencies={"postgres"},
    )

    graph = registry.dependency_graph()

    assert graph["generate_sms"] == {"redis"}
    assert graph["fetch_customer"] == {"postgres"}


def test_validate_dependencies():
    registry = ToolRegistry()

    registry.register_tool(
        get_eta_schema(),
        dependencies={
            "fetch_customer",
            "missing_tool",
        },
    )

    registry.register_tool(
        fetch_customer_schema()
    )

    missing = registry.validate_dependencies(
        "get_eta"
    )

    assert missing == ["missing_tool"]


# ============================================================
# Permission
# ============================================================

def test_registry_check_permission():
    registry = ToolRegistry()

    registry.register_tool(
        generate_sms_schema(),
        category="communication",
        capabilities={"sms"},
        permissions={"tools.sms.generate"},
    )

    assert registry.check_permission(
        "generate_sms",
        "tools.sms.generate",
    ) is True

    assert registry.check_permission(
        "generate_sms",
        "tools.sms.delete",
    ) is False


# ============================================================
# Versions
# ============================================================

def test_registry_get_version():
    registry = ToolRegistry()

    registry.register_tool(
        generate_sms_schema()
    )

    assert (
        registry.get_version("generate_sms")
        == "v1"
    )


def test_registry_get_tool_version():
    registry = ToolRegistry()

    registry.register_tool(
        generate_sms_schema()
    )

    tool = registry.get_tool_version(
        "generate_sms",
        "v1",
    )

    assert tool is not None
    assert (
        tool.schema.contract.version
        == "v1"
    )


def test_registry_returns_none_for_wrong_version():
    registry = ToolRegistry()

    registry.register_tool(
        generate_sms_schema()
    )

    assert (
        registry.get_tool_version(
            "generate_sms",
            "v2",
        )
        is None
    )


def test_multiple_tool_versions():
    registry = ToolRegistry()

    v1 = get_eta_schema()

    v2_contract = v1.contract.model_copy(
        update={"version": "v2"}
    )
    v2 = ToolSchema(v2_contract)

    registry.register_tool(v1)
    registry.register_tool(v2)

    assert (
        registry.get_tool_version(
            "get_eta",
            "v1",
        )
        is not None
    )

    assert (
        registry.get_tool_version(
            "get_eta",
            "v2",
        )
        is not None
    )


# ============================================================
# Registration
# ============================================================

def test_register_and_get_tool():
    registry = ToolRegistry()

    tool = generate_sms_schema()

    registry.register(tool)

    result = registry.get("generate_sms")

    assert result is tool


def test_register_tool_returns_tool_id():
    registry = ToolRegistry()

    tool_id = registry.register_tool(
        generate_sms_schema()
    )

    assert tool_id == "generate_sms"
    assert (
        registry.get_tool("generate_sms")
        is not None
    )


def test_register_tool_rejects_non_positive_cache_ttl():
    registry = ToolRegistry()

    with pytest.raises(
        ValueError,
        match="cache_ttl must be greater than 0",
    ):
        registry.register_tool(
            generate_sms_schema(),
            cache_ttl=0,
        )

    with pytest.raises(
        ValueError,
        match="cache_ttl must be greater than 0",
    ):
        registry.register_tool(
            generate_sms_schema(),
            cache_ttl=-1,
        )


def test_register_tool_rejects_fallback_value_without_flag():
    registry = ToolRegistry()

    with pytest.raises(
        ValueError,
        match=(
            "fallback_value was provided but "
            "has_fallback_value is False"
        ),
    ):
        registry.register_tool(
            generate_sms_schema(),
            fallback_value="fallback",
            has_fallback_value=False,
        )


def test_register_tool_requires_fallback_value_when_flag_enabled():
    registry = ToolRegistry()

    with pytest.raises(
        ValueError,
        match=(
            "has_fallback_value=True requires "
            "a fallback_value"
        ),
    ):
        registry.register_tool(
            generate_sms_schema(),
            fallback_value=None,
            has_fallback_value=True,
        )


def test_register_tool_rejects_self_fallback():
    registry = ToolRegistry()

    with pytest.raises(
        ValueError,
        match=(
            "fallback_tool_id cannot reference "
            "the same tool"
        ),
    ):
        registry.register_tool(
            generate_sms_schema(),
            fallback_tool_id="generate_sms",
        )


# ============================================================
# Discovery
# ============================================================

def test_discover_tools_package():
    registry = ToolRegistry()

    discovered = registry.discover(
        "app.tools"
    )

    assert "app.tools.examples" in discovered
    assert "app.tools.registry" in discovered


def test_discover_single_module():
    registry = ToolRegistry()

    result = registry.discover(
        "app.tools.schema"
    )

    assert result == ["app.tools.schema"]


# ============================================================
# Catalog / Redis
# ============================================================

def test_cache_catalog():
    class FakeRedis:
        def __init__(self):
            self.data = {}

        def setex(
            self,
            key,
            ttl,
            value,
        ):
            self.data[key] = {
                "ttl": ttl,
                "value": value,
            }
            return True

    redis = FakeRedis()
    registry = ToolRegistry(
        redis_client=redis
    )

    registry.register_tool(
        get_eta_schema()
    )

    result = registry.cache_catalog(
        ttl_seconds=300
    )

    assert result is True
    assert (
        "fieldops:tools:catalog"
        in redis.data
    )


def test_cache_catalog_without_redis():
    registry = ToolRegistry()

    registry._redis = None

    result = registry.cache_catalog()

    assert result is False


def test_cache_catalog_rejects_non_positive_ttl():
    registry = ToolRegistry()

    with pytest.raises(
        ValueError,
        match="ttl_seconds must be greater than 0",
    ):
        registry.cache_catalog(
            ttl_seconds=0
        )

    with pytest.raises(
        ValueError,
        match="ttl_seconds must be greater than 0",
    ):
        registry.cache_catalog(
            ttl_seconds=-1
        )


def test_cache_catalog_redis_failure():
    class FailingRedis:
        def setex(
            self,
            key,
            ttl,
            value,
        ):
            raise RuntimeError(
                "Redis unavailable"
            )

    registry = ToolRegistry(
        redis_client=FailingRedis()
    )

    registry.register_tool(
        get_eta_schema()
    )

    result = registry.cache_catalog()

    assert result is False


# ============================================================
# Default Registry / Default Handlers
# ============================================================

def test_create_default_registry():
    registry = create_default_registry()

    assert (
        registry.get_tool(
            "generate_sms"
        )
        is not None
    )

    assert (
        registry.get_tool(
            "fetch_customer"
        )
        is not None
    )

    assert (
        registry.get_tool(
            "get_eta"
        )
        is not None
    )


def test_default_generate_sms_handler():
    registry = create_default_registry()

    tool = registry.get_tool(
        "generate_sms"
    )

    assert tool is not None
    assert tool.handler is not None

    assert (
        tool.handler(
            "Hello",
            "high",
        )
        == "Hello"
    )


def test_default_fetch_customer_handler():
    registry = create_default_registry()

    tool = registry.get_tool(
        "fetch_customer"
    )

    assert tool is not None
    assert tool.handler is not None

    result = tool.handler(
        "customer-123"
    )

    assert result == {
        "customer_id": "customer-123",
        "name": "Customer customer-123",
        "phone": "+15555550123",
    }


def test_default_get_eta_handler():
    registry = create_default_registry()

    tool = registry.get_tool(
        "get_eta"
    )

    assert tool is not None
    assert tool.handler is not None

    result = tool.handler(
        "job-123"
    )

    assert result == {
        "job_id": "job-123",
        "eta_minutes": 15,
    }


# ============================================================
# Unknown Tool Branches
# ============================================================

def test_unknown_tool_branches():
    registry = ToolRegistry()

    assert (
        registry.get_dependencies(
            "unknown_tool"
        )
        is None
    )

    assert (
        registry.validate_dependencies(
            "unknown_tool"
        )
        == []
    )

    assert (
        registry.check_permission(
            "unknown_tool",
            "admin",
        )
        is False
    )

    assert (
        registry.get_version(
            "unknown_tool"
        )
        is None
    )

    assert (
        registry.get_tool_version(
            "unknown_tool",
            "v1",
        )
        is None
    )


# ============================================================
# List Tools
# ============================================================

def test_list_tools():
    registry = ToolRegistry()

    registry.register_tool(
        generate_sms_schema()
    )
    registry.register_tool(
        get_eta_schema()
    )

    result = registry.list_tools()

    assert result == [
        "generate_sms",
        "get_eta",
    ]
