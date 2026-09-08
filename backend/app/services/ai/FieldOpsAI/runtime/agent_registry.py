"""
agent_registry.py

Tenant-safe registry of agent definitions and factories.

Story 1.3 — Agent Registry.

Responsibilities
----------------
- Store agent type definitions (AgentRegistration) and optional custom factories.
- Validate and create fresh uninitialized agent instances on demand.
- Enforce duplicate-registration policy.
- Enforce tenant isolation during agent creation.
- Provide deterministic listing of registrations.

What this component does NOT do
--------------------------------
- Manage live agent execution.
- Register agents in AgentPool.
- Persist state to the database.
- Connect to Redis.
- Call external services.
- Hold live agent instances.

Separation of concerns
-----------------------
- AgentRegistry  — stores definitions and creates fresh instances.
- AgentPool      — stores live instances after initialization.
- AgentLifecycle — manages execution flow.
- AgentStateManager — persists runtime snapshots.

Thread safety
-------------
A threading.Lock guards all mutations and reads of internal dicts
(registrations, factories, and issued UUIDs).  The lock is NOT held
while resolving configuration, calling factories, or constructing
agents — these operations may block and must not starve other threads
waiting for the lock.
"""

from __future__ import annotations

import threading
from typing import Any, Callable
from uuid import UUID

import structlog

from app.services.ai.FieldOpsAI.agents.base import AgentState, BaseAgent
from app.services.ai.FieldOpsAI.config.agent_config_manager import AgentConfigManager
from app.services.ai.FieldOpsAI.schemas.agent_config import AgentConfig
from app.services.ai.FieldOpsAI.schemas.agent_registration import AgentRegistration
from app.services.ai.FieldOpsAI.schemas.ai_task import AITask


_logger = structlog.get_logger("fieldops.ai.agent_registry")


# Type alias for an agent factory callable.
# Receives a validated AgentConfig and an optional orchestrator object.
AgentFactory = Callable[
    [AgentConfig, "object | None"],
    BaseAgent[Any],
]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class AgentRegistryError(Exception):
    """
    Base exception for AgentRegistry errors.
    """


class AgentAlreadyRegisteredError(AgentRegistryError):
    """
    Raised when registering an agent_type that is already registered
    and ``replace=True`` was not specified.
    """


class AgentNotRegisteredError(AgentRegistryError):
    """
    Raised when looking up or creating an agent_type that has not
    been registered.
    """


class AgentRegistrationDisabledError(AgentRegistryError):
    """
    Raised when ``create()`` is called for a registered but disabled
    agent type.
    """


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class AgentRegistry:
    """
    Registry of agent definitions and optional factories.

    Each agent type (AITask) may be registered at most once unless
    ``replace=True`` is passed to ``register()``.

    Thread safety
    -------------
    All mutation and lookup of internal mappings (registrations,
    factories, issued UUIDs) is guarded by a ``threading.Lock``.
    Long-running operations (config resolution, agent construction)
    happen outside the lock.

    Falsey dependencies
    -------------------
    Custom factories are stored via explicit None checks so a factory
    that evaluates to False (e.g. a mock with __bool__ = False) is
    still retained.

    Fresh instance enforcement
    --------------------------
    ``create()`` tracks every agent UUID it has issued.  If a factory
    returns an agent whose UUID was already issued, the call raises
    ``AgentRegistryError``.  UUIDs are tracked — not live agent objects —
    so no live instance is held by the registry.
    """

    def __init__(self) -> None:
        self._registrations: dict[AITask, AgentRegistration] = {}
        self._factories: dict[AITask, AgentFactory | None] = {}
        # Track issued agent UUIDs to detect reuse — does NOT store agents.
        self._issued_uuids: set[UUID] = set()
        self._lock = threading.Lock()

        _logger.debug("agent_registry_created")

    # ------------------------------------------------------------------
    # Registration management
    # ------------------------------------------------------------------

    def register(
        self,
        *,
        registration: AgentRegistration,
        factory: AgentFactory | None = None,
        replace: bool = False,
    ) -> None:
        """
        Register an agent definition.

        Parameters
        ----------
        registration:
            Validated AgentRegistration describing the agent type.
        factory:
            Optional callable that creates agent instances.  When None,
            ``registration.agent_class`` is instantiated directly.
            Stored via explicit None check so falsey factories are retained.
            A non-None, non-callable value raises TypeError.
        replace:
            When True, silently replaces an existing registration.
            When False (the default), raises AgentAlreadyRegisteredError
            if the agent type is already registered.

        Raises
        ------
        TypeError
            When registration is not an AgentRegistration instance, or
            when factory is not None and not callable.
        AgentAlreadyRegisteredError
            When the agent type is already registered and replace=False.
        """

        if not isinstance(registration, AgentRegistration):
            raise TypeError(
                "registration must be an AgentRegistration instance, "
                f"got {type(registration).__name__!r}."
            )

        # Reject a non-None, non-callable factory immediately — before
        # acquiring the lock — so the error message is always informative.
        if factory is not None and not callable(factory):
            raise TypeError(
                "factory must be callable or None, "
                f"got {type(factory).__name__!r}."
            )

        agent_type = registration.agent_type

        with self._lock:
            # Calculate already_registered before modifying mappings so that
            # the log message below reflects the pre-mutation state correctly.
            already_registered = agent_type in self._registrations

            if already_registered and not replace:
                raise AgentAlreadyRegisteredError(
                    f"Agent type {agent_type.value!r} is already registered. "
                    "Use replace=True to overwrite."
                )

            self._registrations[agent_type] = registration
            # Use explicit None check so a falsey factory is not lost.
            self._factories[agent_type] = factory if factory is not None else None

        _logger.info(
            "agent_registered",
            agent_type=agent_type.value,
            agent_class=registration.agent_class.__name__,
            version=registration.version,
            enabled=registration.enabled,
            replaced=already_registered and replace,
        )

    def unregister(self, agent_type: AITask) -> bool:
        """
        Remove the registration for an agent type.

        Returns True when the registration existed and was removed.
        Returns False when no matching registration was found.

        Parameters
        ----------
        agent_type:
            AITask value to remove.

        Raises
        ------
        TypeError
            When agent_type is not an AITask member.
        """

        if not isinstance(agent_type, AITask):
            raise TypeError(
                "agent_type must be an AITask member, "
                f"got {type(agent_type).__name__!r}."
            )

        with self._lock:
            if agent_type not in self._registrations:
                return False

            del self._registrations[agent_type]
            self._factories.pop(agent_type, None)

        _logger.info("agent_unregistered", agent_type=agent_type.value)
        return True

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, agent_type: AITask) -> AgentRegistration:
        """
        Return the registration for the given agent type.

        Raises AgentNotRegisteredError when the type is not registered.
        Disabled registrations are returned normally.

        Parameters
        ----------
        agent_type:
            AITask value to look up.

        Raises
        ------
        TypeError
            When agent_type is not an AITask member.
        AgentNotRegisteredError
            When the agent type is not registered.
        """

        if not isinstance(agent_type, AITask):
            raise TypeError(
                "agent_type must be an AITask member, "
                f"got {type(agent_type).__name__!r}."
            )

        with self._lock:
            registration = self._registrations.get(agent_type)

        if registration is None:
            raise AgentNotRegisteredError(
                f"Agent type {agent_type.value!r} is not registered."
            )

        return registration

    def contains(self, agent_type: AITask) -> bool:
        """
        Return True when the agent type is registered.

        Both enabled and disabled registrations are counted.

        Parameters
        ----------
        agent_type:
            AITask value to check.

        Raises
        ------
        TypeError
            When agent_type is not an AITask member.
        """

        if not isinstance(agent_type, AITask):
            raise TypeError(
                "agent_type must be an AITask member, "
                f"got {type(agent_type).__name__!r}."
            )

        with self._lock:
            return agent_type in self._registrations

    def list_registrations(
        self,
        *,
        enabled_only: bool = False,
    ) -> tuple[AgentRegistration, ...]:
        """
        Return all registrations as an immutable tuple.

        Registrations are returned in the order they were inserted.

        Parameters
        ----------
        enabled_only:
            When True, only enabled registrations are returned.
        """

        with self._lock:
            registrations = tuple(self._registrations.values())

        if enabled_only:
            registrations = tuple(r for r in registrations if r.enabled)

        return registrations

    # ------------------------------------------------------------------
    # Agent creation
    # ------------------------------------------------------------------

    def create(
        self,
        *,
        agent_type: AITask,
        tenant_id: str,
        config_manager: AgentConfigManager,
        orchestrator: object | None = None,
    ) -> BaseAgent[Any]:
        """
        Create and return a fresh uninitialized agent instance.

        This method:
        1.  Validates tenant_id is a non-blank string (strips whitespace).
        2.  Validates agent_type is an AITask member.
        3.  Validates config_manager provides a callable resolve().
        4.  Looks up and validates the registration.
        5.  Rejects disabled registrations.
        6.  Resolves configuration via config_manager.resolve().
        7.  Validates the resolved object is an AgentConfig.
        8.  Validates resolved config matches agent_type, tenant_id, and enabled.
        9.  Constructs the agent via the factory or agent_class.
        10. Validates the returned object is a fresh BaseAgent:
            - isinstance(agent, BaseAgent)
            - matching agent_type
            - matching tenant_id
            - is_setup is False
            - state is AgentState.IDLE
            - UUID not previously issued by this registry
        11. Records the agent UUID and returns the uninitialized agent.

        The agent is returned in IDLE state.  setup() has NOT been
        called.  The agent is NOT registered in AgentPool.

        Parameters
        ----------
        agent_type:
            AITask value identifying the agent type to create.
        tenant_id:
            Non-blank string identifying the owning tenant.
            Leading and trailing whitespace is stripped after validation.
        config_manager:
            Must expose a callable ``resolve(agent_type, tenant_id)``
            method.  Preserved via explicit None-free checks.
        orchestrator:
            Optional orchestrator passed to the factory or constructor.
            Stored via explicit None check so falsey orchestrators are
            forwarded correctly.

        Returns
        -------
        BaseAgent
            A fresh, uninitialized agent instance.

        Raises
        ------
        TypeError
            When tenant_id is not a string, agent_type is not an AITask,
            or config_manager has no callable resolve().
        ValueError
            When tenant_id is blank.
        AgentNotRegisteredError
            When the agent type is not registered.
        AgentRegistrationDisabledError
            When the registration is disabled.
        AgentRegistryError
            When config validation fails, the factory returns an invalid
            object, or the returned agent UUID is already known to this
            registry (reuse detected).
        """

        # Step 1 — validate and normalize tenant_id
        if not isinstance(tenant_id, str):
            raise TypeError(
                "tenant_id must be a string, "
                f"got {type(tenant_id).__name__!r}."
            )
        tenant_id = tenant_id.strip()
        if not tenant_id:
            raise ValueError("tenant_id must not be blank.")

        # Step 2 — validate agent_type
        if not isinstance(agent_type, AITask):
            raise TypeError(
                "agent_type must be an AITask member, "
                f"got {type(agent_type).__name__!r}."
            )

        # Step 3 — validate config_manager provides callable resolve()
        # Use explicit None check so a falsey config_manager is preserved.
        resolve_fn = getattr(config_manager, "resolve", None)
        if resolve_fn is None or not callable(resolve_fn):
            raise TypeError(
                "config_manager must provide a callable resolve() method."
            )

        # Step 4 — retrieve registration + factory under lock
        with self._lock:
            registration = self._registrations.get(agent_type)
            factory = self._factories.get(agent_type)  # None when absent or unset

        if registration is None:
            raise AgentNotRegisteredError(
                f"Agent type {agent_type.value!r} is not registered."
            )

        # Step 5 — reject disabled registration
        if not registration.enabled:
            raise AgentRegistrationDisabledError(
                f"Agent type {agent_type.value!r} is disabled and "
                "cannot be used to create an agent."
            )

        # Step 6 — resolve config (outside the lock — may block)
        config = resolve_fn(
            agent_type=agent_type,
            tenant_id=tenant_id,
        )

        # Step 7 — validate resolved object is an AgentConfig
        if not isinstance(config, AgentConfig):
            raise AgentRegistryError(
                f"config_manager.resolve() must return an AgentConfig, "
                f"got {type(config).__name__!r}."
            )

        # Step 8 — validate resolved config fields
        if config.agent_type is not agent_type:
            raise AgentRegistryError(
                f"Resolved config agent_type {config.agent_type.value!r} "
                f"does not match requested {agent_type.value!r}."
            )

        if config.tenant_id != tenant_id:
            raise AgentRegistryError(
                f"Resolved config tenant_id {config.tenant_id!r} "
                f"does not match requested {tenant_id!r}."
            )

        if not config.enabled:
            raise AgentRegistryError(
                f"Resolved config for {agent_type.value!r} is disabled."
            )

        # Step 9 — construct agent (outside the lock — may block)
        # Use explicit check: `factory is not None` retains falsey factories.
        if factory is not None:
            agent = factory(config, orchestrator)
        else:
            # Fallback: BaseAgent subclasses accept at minimum (config,).
            # Orchestrator forwarding is the responsibility of custom factories
            # because concrete agents vary in their optional parameters.
            agent = registration.agent_class(config)

        # Step 10 — validate the returned object

        if not isinstance(agent, BaseAgent):
            raise AgentRegistryError(
                f"Factory or agent_class for {agent_type.value!r} "
                f"returned a non-BaseAgent object: {type(agent).__name__!r}."
            )

        if agent.config.agent_type is not agent_type:
            raise AgentRegistryError(
                f"Created agent has agent_type "
                f"{agent.config.agent_type.value!r} but "
                f"{agent_type.value!r} was requested."
            )

        if agent.tenant_id != tenant_id:
            raise AgentRegistryError(
                f"Created agent has tenant_id {agent.tenant_id!r} but "
                f"{tenant_id!r} was requested."
            )

        if agent.is_setup:
            raise AgentRegistryError(
                f"Factory for {agent_type.value!r} returned an agent "
                "that has already been set up (is_setup=True). "
                "create() must return a fresh uninitialized agent."
            )

        if agent.state is not AgentState.IDLE:
            raise AgentRegistryError(
                f"Factory for {agent_type.value!r} returned an agent "
                f"in state {agent.state.value!r}; expected IDLE. "
                "create() must return a fresh uninitialized agent."
            )

        # Step 11 — check and record UUID (under lock — no agent stored)
        agent_uuid = agent.agent_id
        with self._lock:
            if agent_uuid in self._issued_uuids:
                raise AgentRegistryError(
                    f"Factory for {agent_type.value!r} returned an agent "
                    f"with UUID {agent_uuid!s} that was already issued by "
                    "this registry. Each create() call must return a new "
                    "agent instance."
                )
            self._issued_uuids.add(agent_uuid)

        _logger.info(
            "agent_created",
            agent_id=str(agent_uuid),
            agent_type=agent_type.value,
            tenant_id=tenant_id,
            version=registration.version,
        )

        return agent


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------


def create_default_agent_registry() -> AgentRegistry:
    """
    Create and return a new AgentRegistry pre-loaded with the two
    migrated agent implementations.

    Registered types
    ----------------
    - AITask.PLANNING → PlanningAgent
    - AITask.DISPATCH → DispatchAgent

    Excluded types (not yet migrated)
    ----------------------------------
    - AITask.MONITORING
    - AITask.SENTIMENT
    - AITask.COMMUNICATION
    - AITask.CLOSURE

    Returns a new registry each time — there is no module-level
    global singleton.

    Provider dependencies (e.g. ai_orchestrator) are NOT imported here.
    Registry bootstrap must not initialize provider-related dependencies.
    """

    # Import here to avoid circular imports at module load time.
    from app.services.ai.FieldOpsAI.agents.planning_agent import PlanningAgent
    from app.services.ai.FieldOpsAI.agents.dispatch_agent import DispatchAgent
    from app.services.ai.FieldOpsAI.agents.intake_agent import IntakeAgent

    registry = AgentRegistry()

    # PlanningAgent factory — forwards the optional orchestrator.
    def _planning_factory(
        config: AgentConfig,
        orchestrator: object | None,
    ) -> PlanningAgent:
        return PlanningAgent(
            config=config,
            orchestrator=orchestrator,  # type: ignore[arg-type]
        )

    # DispatchAgent factory — forwards the optional orchestrator.
    def _dispatch_factory(
        config: AgentConfig,
        orchestrator: object | None,
    ) -> DispatchAgent:
        return DispatchAgent(
            config=config,
            orchestrator=orchestrator,  # type: ignore[arg-type]
        )

    # IntakeAgent factory — forwards the optional orchestrator.
    def _intake_factory(
        config: AgentConfig,
        orchestrator: object | None,
    ) -> IntakeAgent:
        return IntakeAgent(
            config=config,
            orchestrator=orchestrator,  # type: ignore[arg-type]
        )

    registry.register(
        registration=AgentRegistration(
            agent_type=AITask.PLANNING,
            agent_class=PlanningAgent,
            version="1.0",
            enabled=True,
            description="AI agent responsible for technician assignment recommendations.",
        ),
        factory=_planning_factory,
    )

    registry.register(
        registration=AgentRegistration(
            agent_type=AITask.DISPATCH,
            agent_class=DispatchAgent,
            version="1.0",
            enabled=True,
            description="AI agent responsible for technician dispatch workflow decisions.",
        ),
        factory=_dispatch_factory,
    )

    registry.register(
        registration=AgentRegistration(
            agent_type=AITask.INTAKE,
            agent_class=IntakeAgent,
            version="1.0",
            enabled=True,
            description=(
                "AI agent responsible for converting customer requests "
                "into structured intake information."
            ),
        ),
        factory=_intake_factory,
    )

    return registry
