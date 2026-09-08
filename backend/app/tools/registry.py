from __future__ import annotations

import importlib
import json
import pkgutil
from dataclasses import dataclass, field
from typing import Any, Callable

from app.redis_client import get_redis_client

from app.tools.examples import (
    fetch_customer_schema,
    generate_sms_schema,
    get_eta_schema,
)
from app.tools.schema import ToolSchema


# ============================================================
# Registered Tool
# ============================================================


@dataclass
class RegisteredTool:
    schema: ToolSchema

    handler: Callable[..., Any] | None = None

    category: str = "general"

    capabilities: set[str] = field(
        default_factory=set
    )

    dependencies: set[str] = field(
        default_factory=set
    )

    permissions: set[str] = field(
        default_factory=set
    )

    health: str = "healthy"

    cacheable: bool = True

    cache_ttl: int = 60

    # --------------------------------------------------------
    # Fallback configuration
    # --------------------------------------------------------

    fallback_value: Any = None

    has_fallback_value: bool = False

    fallback_tool_id: str | None = None


# ============================================================
# Tool Registry
# ============================================================


class ToolRegistry:

    def __init__(
        self,
        redis_client: Any | None = None,
    ) -> None:

        self._tools: dict[
            str,
            ToolSchema,
        ] = {}

        self._registered_tools: dict[
            str,
            RegisteredTool,
        ] = {}

        self._tool_versions: dict[
            str,
            dict[str, RegisteredTool],
        ] = {}

        # Reuse an injected Redis client.
        #
        # This is important because ToolErrorHandler,
        # CircuitBreaker and ErrorRateTracker should use
        # the same Redis connection/client.
        self._redis = (
            redis_client
            if redis_client is not None
            else get_redis_client()
        )

    # ========================================================
    # Redis
    # ========================================================

    @property
    def redis(self) -> Any | None:
        """
        Return the Redis client used by the registry.
        """
        return self._redis

    # ========================================================
    # Decorator
    # ========================================================

    def tool(
        self,
        schema: ToolSchema,
        category: str = "general",
        capabilities: set[str] | None = None,
        dependencies: set[str] | None = None,
        permissions: set[str] | None = None,
        cacheable: bool = True,
        cache_ttl: int = 60,
        fallback_value: Any = None,
        fallback_tool_id: str | None = None,
        has_fallback_value: bool = False,
    ):
        """
        Decorator for registering an executable tool.

        Example:

            @registry.tool(
                schema=generate_sms_schema(),
                category="communication",
                capabilities={"sms"},
                fallback_value="SMS unavailable",
                has_fallback_value=True,
            )
            def generate_sms(message: str):
                return message
        """

        def decorator(
            func: Callable[..., Any],
        ) -> Callable[..., Any]:

            self.register_tool(
                tool=schema,
                handler=func,
                category=category,
                capabilities=capabilities,
                dependencies=dependencies,
                permissions=permissions,
                cacheable=cacheable,
                cache_ttl=cache_ttl,
                fallback_value=fallback_value,
                fallback_tool_id=fallback_tool_id,
                has_fallback_value=has_fallback_value,
            )

            return func

        return decorator

    # ========================================================
    # Basic Registry API
    # ========================================================

    def register(
        self,
        tool: ToolSchema,
    ) -> None:
        """
        Register a schema-only tool.

        This does not register an executable handler.
        """

        tool_id = tool.contract.name

        self._tools[tool_id] = tool

    def get(
        self,
        name: str,
    ) -> ToolSchema | None:
        """
        Get a tool schema by name.
        """

        return self._tools.get(name)

    # ========================================================
    # Discovery
    # ========================================================

    def discover(
        self,
        package_name: str,
    ) -> list[str]:
        """
        Discover and import tool modules from a package.
        """

        package = importlib.import_module(
            package_name
        )

        # The package itself is a module without
        # submodules.
        if not hasattr(
            package,
            "__path__",
        ):
            return [package_name]

        discovered: list[str] = []

        for module_info in pkgutil.walk_packages(
            package.__path__,
            prefix=f"{package_name}.",
        ):
            module_name = module_info.name

            importlib.import_module(
                module_name
            )

            discovered.append(
                module_name
            )

        return discovered

    # ========================================================
    # Tool Registration
    # ========================================================

    def register_tool(
        self,
        tool: ToolSchema,
        handler: Callable[..., Any] | None = None,
        category: str = "general",
        capabilities: set[str] | None = None,
        dependencies: set[str] | None = None,
        permissions: set[str] | None = None,
        cacheable: bool = True,
        cache_ttl: int = 60,
        fallback_value: Any = None,
        fallback_tool_id: str | None = None,
        has_fallback_value: bool = False,
    ) -> str:
        """
        Register a tool schema and optional executable handler.
        """

        if cache_ttl <= 0:
            raise ValueError(
                "cache_ttl must be greater than 0"
            )

        tool_id = tool.contract.name

        # ----------------------------------------------------
        # Validate fallback configuration
        # ----------------------------------------------------

        if (
            fallback_value is not None
            and not has_fallback_value
        ):
            raise ValueError(
                "fallback_value was provided but "
                "has_fallback_value is False"
            )

        if (
            has_fallback_value
            and fallback_value is None
        ):
            raise ValueError(
                "has_fallback_value=True requires "
                "a fallback_value"
            )

        if (
            fallback_tool_id is not None
            and fallback_tool_id == tool_id
        ):
            raise ValueError(
                "fallback_tool_id cannot reference "
                "the same tool"
            )

        # ----------------------------------------------------
        # Store schema
        # ----------------------------------------------------

        self._tools[tool_id] = tool

        # ----------------------------------------------------
        # Create registered tool
        # ----------------------------------------------------

        registered_tool = RegisteredTool(
            schema=tool,
            handler=handler,

            category=category,

            capabilities=set(
                capabilities or set()
            ),

            dependencies=set(
                dependencies or set()
            ),

            permissions=set(
                permissions or set()
            ),

            cacheable=cacheable,

            cache_ttl=cache_ttl,

            fallback_value=fallback_value,

            has_fallback_value=has_fallback_value,

            fallback_tool_id=fallback_tool_id,
        )

        self._registered_tools[
            tool_id
        ] = registered_tool

        # ----------------------------------------------------
        # Version registration
        # ----------------------------------------------------

        version = tool.contract.version

        self._tool_versions.setdefault(
            tool_id,
            {},
        )[version] = registered_tool

        return tool_id

    # ========================================================
    # Lookup
    # ========================================================

    def get_tool(
        self,
        tool_id: str,
    ) -> RegisteredTool | None:
        """
        Return a registered executable tool.
        """

        return self._registered_tools.get(
            tool_id
        )

    def list_tools(
        self,
    ) -> list[str]:
        """
        Return all registered tool IDs.
        """

        return list(
            self._tools.keys()
        )

    # ========================================================
    # Catalog
    # ========================================================

    def cache_catalog(
        self,
        ttl_seconds: int = 300,
    ) -> bool:
        """
        Cache the current tool catalog in Redis.
        """

        if ttl_seconds <= 0:
            raise ValueError(
                "ttl_seconds must be greater than 0"
            )

        if self._redis is None:
            return False

        catalog: list[dict[str, Any]] = []

        for tool in (
            self._registered_tools.values()
        ):

            catalog.append(
                {
                    "id": (
                        tool.schema
                        .contract
                        .name
                    ),

                    "name": (
                        tool.schema
                        .contract
                        .name
                    ),

                    "description": (
                        tool.schema
                        .contract
                        .description
                    ),

                    "version": (
                        tool.schema
                        .contract
                        .version
                    ),

                    "category": tool.category,

                    "capabilities": sorted(
                        tool.capabilities
                    ),

                    "dependencies": sorted(
                        tool.dependencies
                    ),

                    "permissions": sorted(
                        tool.permissions
                    ),

                    "health": tool.health,

                    "cacheable": tool.cacheable,

                    "cache_ttl": tool.cache_ttl,

                    "has_fallback_value": (
                        tool.has_fallback_value
                    ),

                    "fallback_tool_id": (
                        tool.fallback_tool_id
                    ),
                }
            )

        try:

            result = self._redis.setex(
                "fieldops:tools:catalog",
                ttl_seconds,
                json.dumps(
                    catalog,
                    default=str,
                ),
            )

            return bool(result)

        except Exception:
            # Redis failure must not break
            # tool registration/execution.
            return False

    # ========================================================
    # Search
    # ========================================================

    def search_tools(
        self,
        name: str | None = None,
        category: str | None = None,
        capability: str | None = None,
    ) -> list[RegisteredTool]:
        """
        Search registered tools using optional filters.
        """

        results = list(
            self._registered_tools.values()
        )

        if name is not None:

            results = [
                tool
                for tool in results
                if (
                    tool.schema.contract.name
                    == name
                )
            ]

        if category is not None:

            results = [
                tool
                for tool in results
                if tool.category == category
            ]

        if capability is not None:

            results = [
                tool
                for tool in results
                if capability
                in tool.capabilities
            ]

        return results

    # ========================================================
    # Health
    # ========================================================

    def get_health(
        self,
        tool_id: str,
    ) -> str | None:
        """
        Return current tool health.
        """

        tool = self._registered_tools.get(
            tool_id
        )

        if tool is None:
            return None

        return tool.health

    def set_health(
        self,
        tool_id: str,
        health: str,
    ) -> bool:
        """
        Update tool health.
        """

        tool = self._registered_tools.get(
            tool_id
        )

        if tool is None:
            return False

        tool.health = health

        return True

    # ========================================================
    # Dependencies
    # ========================================================

    def get_dependencies(
        self,
        tool_id: str,
    ) -> set[str] | None:
        """
        Return dependencies for a tool.
        """

        tool = self._registered_tools.get(
            tool_id
        )

        if tool is None:
            return None

        return set(
            tool.dependencies
        )

    def dependency_graph(
        self,
    ) -> dict[str, set[str]]:
        """
        Return the complete dependency graph.
        """

        return {
            tool_id: set(
                tool.dependencies
            )
            for (
                tool_id,
                tool,
            ) in self._registered_tools.items()
        }

    def validate_dependencies(
        self,
        tool_id: str,
    ) -> list[str]:
        """
        Return dependencies that are not registered.
        """

        tool = self._registered_tools.get(
            tool_id
        )

        if tool is None:
            return []

        return [
            dependency
            for dependency
            in tool.dependencies
            if dependency
            not in self._registered_tools
        ]

    # ========================================================
    # Permissions
    # ========================================================

    def check_permission(
        self,
        tool_id: str,
        permission: str,
    ) -> bool:
        """
        Check whether a tool has a permission.
        """

        tool = self._registered_tools.get(
            tool_id
        )

        if tool is None:
            return False

        return permission in tool.permissions

    # ========================================================
    # Versions
    # ========================================================

    def get_version(
        self,
        tool_id: str,
    ) -> str | None:
        """
        Return the current registered version.
        """

        tool = self._registered_tools.get(
            tool_id
        )

        if tool is None:
            return None

        return (
            tool.schema
            .contract
            .version
        )

    def get_tool_version(
        self,
        tool_id: str,
        version: str,
    ) -> RegisteredTool | None:
        """
        Return a specific tool version.
        """

        return (
            self._tool_versions
            .get(tool_id, {})
            .get(version)
        )


# ============================================================
# Default Executable Handlers
# ============================================================


def _generate_sms_handler(
    message: str,
    priority: str = "normal",
) -> str:
    """
    Default SMS generation handler.
    """

    _ = priority

    return message


def _fetch_customer_handler(
    customer_id: str,
) -> dict[str, Any]:
    """
    Default customer lookup handler.
    """

    return {
        "customer_id": customer_id,
        "name": f"Customer {customer_id}",
        "phone": "+15555550123",
    }


def _get_eta_handler(
    job_id: str,
) -> dict[str, Any]:
    """
    Default ETA handler.
    """

    return {
        "job_id": job_id,
        "eta_minutes": 15,
    }


# ============================================================
# Default Registry
# ============================================================


def create_default_registry() -> ToolRegistry:
    """
    Create and populate the default tool registry.
    """

    registry = ToolRegistry()

    # --------------------------------------------------------
    # Generate SMS
    # --------------------------------------------------------

    registry.register_tool(
        generate_sms_schema(),
        handler=_generate_sms_handler,
    )

    # --------------------------------------------------------
    # Fetch Customer
    # --------------------------------------------------------

    registry.register_tool(
        fetch_customer_schema(),
        handler=_fetch_customer_handler,
    )

    # --------------------------------------------------------
    # Get ETA
    # --------------------------------------------------------

    registry.register_tool(
        get_eta_schema(),
        handler=_get_eta_handler,
    )

    return registry