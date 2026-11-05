"""
test_agent_bus.py

Unit tests for AgentBus asynchronous in-process pub/sub bus.
"""

from __future__ import annotations

import asyncio
import pytest
import structlog
from datetime import datetime, UTC
from uuid import UUID, uuid4
from typing import Any
from unittest.mock import patch, MagicMock

from app.services.ai.FieldOpsAI.runtime.agent_bus import (
    AgentBus,
    AgentBusError,
    InvalidMessageHandlerError,
    MessageDeliveryError,
    create_agent_bus,
)
from app.services.ai.FieldOpsAI.schemas.agent_messages import (
    AgentAddress,
    MessageEnvelope,
    CommandMessage,
    EventMessage,
    PublishResult,
    DeliveryFailure,
    MessageType,
)
from app.services.ai.FieldOpsAI.schemas.agent_subscription import AgentSubscription


# Helper to create a standard AgentAddress
def make_address(agent_type: str = "planning", agent_id: str = "planner-01", tenant_id: str = "tenant-001") -> AgentAddress:
    return AgentAddress(agent_type=agent_type, agent_id=agent_id, tenant_id=tenant_id)


# ==========================================================
# AgentBus Tests (Tests 42-69)
# ==========================================================


def test_timeout_construction_validation():
    """
    Test 42: Timeout construction validation.
    """
    with pytest.raises(TypeError, match="must be a numeric value, not bool"):
        AgentBus(handler_timeout_seconds=True)  # type: ignore

    with pytest.raises(TypeError, match="must be an int or float"):
        AgentBus(handler_timeout_seconds="5.0")  # type: ignore

    with pytest.raises(ValueError, match="must be greater than zero"):
        AgentBus(handler_timeout_seconds=0)

    with pytest.raises(ValueError, match="exceeds maximum"):
        AgentBus(handler_timeout_seconds=30.1)


def test_independent_bus_factory():
    """
    Test 43: Independent bus factory.
    """
    bus1 = create_agent_bus(handler_timeout_seconds=10.0)
    bus2 = create_agent_bus(handler_timeout_seconds=10.0)
    assert bus1 is not bus2
    assert bus1._handler_timeout == 10.0


@pytest.mark.anyio
async def test_subscribe_returns_metadata():
    """
    Test 44: Subscribe returns metadata.
    """
    bus = AgentBus()
    sub_addr = make_address()

    def dummy_handler(msg: MessageEnvelope) -> None:
        pass

    sub = await bus.subscribe(
        tenant_id="tenant-001",
        topic="agent.command",
        handler=dummy_handler,
        subscriber=sub_addr,
    )

    assert isinstance(sub, AgentSubscription)
    assert isinstance(sub.subscription_id, UUID)
    assert sub.tenant_id == "tenant-001"
    assert sub.topic == "agent.command"
    assert sub.subscriber == sub_addr
    assert isinstance(sub.created_at, datetime)
    assert sub.created_at.tzinfo is not None

    # Verify handler is not exposed publicly
    assert not hasattr(sub, "handler")


@pytest.mark.anyio
async def test_handler_not_called_on_subscribe():
    """
    Test 45: Handler not called on subscribe.
    """
    bus = AgentBus()
    called = False

    def dummy_handler(msg: MessageEnvelope) -> None:
        nonlocal called
        called = True

    await bus.subscribe(
        tenant_id="tenant-001",
        topic="agent.command",
        handler=dummy_handler,
    )
    assert not called


@pytest.mark.anyio
async def test_exact_address_targeted_routing():
    """
    Test 46: Exact-address targeted routing.
    """
    bus = AgentBus()
    planner_addr = make_address("planning", "planner-01", "tenant-001")
    dispatch_addr = make_address("dispatch", "dispatcher-01", "tenant-001")

    received = []

    async def handler(msg: MessageEnvelope) -> None:
        received.append(msg)

    await bus.subscribe(
        tenant_id="tenant-001",
        topic="agent.command",
        handler=handler,
        subscriber=dispatch_addr,
    )

    msg = CommandMessage(
        sender=planner_addr,
        recipient=dispatch_addr,
        payload={"job_id": "JOB-100"},
    )

    res = await bus.publish(msg)
    assert res.matched_subscribers == 1
    assert res.delivered == 1
    assert len(received) == 1
    assert received[0].message_id == msg.message_id


@pytest.mark.anyio
async def test_same_type_different_agent_instance_excluded():
    """
    Test 47: Same-type different agent instance excluded.
    """
    bus = AgentBus()
    sender_addr = make_address("planning", "planner-01", "tenant-001")
    dispatcher_1 = make_address("dispatch", "dispatcher-01", "tenant-001")
    dispatcher_2 = make_address("dispatch", "dispatcher-02", "tenant-001")

    received_1 = []
    received_2 = []

    await bus.subscribe(
        tenant_id="tenant-001",
        topic="agent.command",
        handler=lambda msg: received_1.append(msg),
        subscriber=dispatcher_1,
    )
    await bus.subscribe(
        tenant_id="tenant-001",
        topic="agent.command",
        handler=lambda msg: received_2.append(msg),
        subscriber=dispatcher_2,
    )

    msg = CommandMessage(
        sender=sender_addr,
        recipient=dispatcher_1,
        payload={"job_id": "JOB-1"},
    )

    res = await bus.publish(msg)
    assert res.matched_subscribers == 1
    assert res.delivered == 1
    assert len(received_1) == 1
    assert len(received_2) == 0


@pytest.mark.anyio
async def test_broadcast_routing():
    """
    Test 48: Broadcast routing (recipient=None).
    """
    bus = AgentBus()
    sender_addr = make_address("planning", "planner-01", "tenant-001")

    received = []

    await bus.subscribe(
        tenant_id="tenant-001",
        topic="agent.event",
        handler=lambda msg: received.append(msg),
    )

    msg = EventMessage(
        sender=sender_addr,
        recipient=None,
        payload={"status": "BROADCAST_ALL"},
    )

    res = await bus.publish(msg)
    assert res.matched_subscribers == 1
    assert res.delivered == 1
    assert len(received) == 1


@pytest.mark.anyio
async def test_subscriber_none_receives_broadcast():
    """
    Test 49: subscriber=None receives broadcast.
    """
    bus = AgentBus()
    sender_addr = make_address("planning", "planner-01", "tenant-001")

    received = []
    await bus.subscribe(
        tenant_id="tenant-001",
        topic="agent.event",
        handler=lambda msg: received.append(msg),
        subscriber=None,
    )

    msg = EventMessage(
        sender=sender_addr,
        recipient=None,
        payload={"status": "BROADCAST_NONE_SUB"},
    )

    await bus.publish(msg)
    assert len(received) == 1


@pytest.mark.anyio
async def test_subscriber_none_excluded_from_targeted_delivery():
    """
    Test 50: subscriber=None excluded from targeted delivery.
    """
    bus = AgentBus()
    sender_addr = make_address("planning", "planner-01", "tenant-001")
    dispatch_addr = make_address("dispatch", "dispatcher-01", "tenant-001")

    received = []
    await bus.subscribe(
        tenant_id="tenant-001",
        topic="agent.command",
        handler=lambda msg: received.append(msg),
        subscriber=None,
    )

    msg = CommandMessage(
        sender=sender_addr,
        recipient=dispatch_addr,
        payload={"action": "TARGETED"},
    )

    res = await bus.publish(msg)
    assert res.matched_subscribers == 0
    assert len(received) == 0


@pytest.mark.anyio
async def test_cross_tenant_subscription_excluded():
    """
    Test 51: Cross-tenant subscription excluded.
    """
    bus = AgentBus()
    sender_addr = make_address("planning", "planner-01", "tenant-001")

    received = []
    await bus.subscribe(
        tenant_id="tenant-002",  # Different tenant
        topic="agent.event",
        handler=lambda msg: received.append(msg),
    )

    msg = EventMessage(
        sender=sender_addr,
        recipient=None,
    )

    res = await bus.publish(msg)
    assert res.matched_subscribers == 0
    assert len(received) == 0


@pytest.mark.anyio
async def test_different_topic_excluded():
    """
    Test 52: Different topic excluded.
    """
    bus = AgentBus()
    sender_addr = make_address("planning", "planner-01", "tenant-001")

    received = []
    await bus.subscribe(
        tenant_id="tenant-001",
        topic="agent.event",
        handler=lambda msg: received.append(msg),
    )

    msg = CommandMessage(
        sender=sender_addr,
        recipient=None,
        topic="agent.command",  # Different topic
    )

    res = await bus.publish(msg)
    assert res.matched_subscribers == 0
    assert len(received) == 0


@pytest.mark.anyio
async def test_zero_subscriber_result():
    """
    Test 53: Zero-subscriber result.
    """
    bus = AgentBus()
    sender_addr = make_address("planning", "planner-01", "tenant-001")
    msg = EventMessage(sender=sender_addr, recipient=None)
    res = await bus.publish(msg)
    assert res.message_id == msg.message_id
    assert res.matched_subscribers == 0
    assert res.delivered == 0
    assert res.failed == 0
    assert res.failures == ()


@pytest.mark.anyio
async def test_sync_handler():
    """
    Test 54: Sync handler.
    """
    bus = AgentBus()
    sender_addr = make_address("planning", "planner-01", "tenant-001")
    called = False

    def sync_handler(msg: MessageEnvelope) -> None:
        nonlocal called
        called = True

    await bus.subscribe(
        tenant_id="tenant-001",
        topic="agent.event",
        handler=sync_handler,
    )

    msg = EventMessage(sender=sender_addr)
    res = await bus.publish(msg)
    assert res.delivered == 1
    assert called


@pytest.mark.anyio
async def test_async_handler():
    """
    Test 55: Async handler.
    """
    bus = AgentBus()
    sender_addr = make_address("planning", "planner-01", "tenant-001")
    called = False

    async def async_handler(msg: MessageEnvelope) -> None:
        nonlocal called
        await asyncio.sleep(0.01)
        called = True

    await bus.subscribe(
        tenant_id="tenant-001",
        topic="agent.event",
        handler=async_handler,
    )

    msg = EventMessage(sender=sender_addr)
    res = await bus.publish(msg)
    assert res.delivered == 1
    assert called


@pytest.mark.anyio
async def test_independent_handler_message_copies():
    """
    Test 56: Independent handler message copies.
    """
    bus = AgentBus()
    sender_addr = make_address("planning", "planner-01", "tenant-001")
    msg = EventMessage(sender=sender_addr, payload={"counter": 0})

    msgs = []

    async def handler_1(m: MessageEnvelope) -> None:
        msgs.append(m)

    async def handler_2(m: MessageEnvelope) -> None:
        msgs.append(m)

    await bus.subscribe(tenant_id="tenant-001", topic="agent.event", handler=handler_1)
    await bus.subscribe(tenant_id="tenant-001", topic="agent.event", handler=handler_2)

    await bus.publish(msg)
    assert len(msgs) == 2
    assert msgs[0] is not msgs[1]
    assert msgs[0].message_id == msg.message_id
    assert msgs[1].message_id == msg.message_id


@pytest.mark.anyio
async def test_handler_mutation_does_not_affect_another_handler():
    """
    Test 57: Handler mutation does not affect another handler.
    """
    bus = AgentBus()
    sender_addr = make_address("planning", "planner-01", "tenant-001")
    msg = EventMessage(sender=sender_addr, payload={"value": "original"})

    async def handler_mutator(m: MessageEnvelope) -> None:
        m.payload["value"] = "mutated"

    async def handler_observer(m: MessageEnvelope) -> None:
        await asyncio.sleep(0.02)
        assert m.payload["value"] == "original"

    await bus.subscribe(tenant_id="tenant-001", topic="agent.event", handler=handler_mutator)
    await bus.subscribe(tenant_id="tenant-001", topic="agent.event", handler=handler_observer)

    res = await bus.publish(msg)
    assert res.delivered == 2


@pytest.mark.anyio
async def test_handler_failure_isolation():
    """
    Test 58: Handler failure isolation.
    """
    bus = AgentBus()
    sender_addr = make_address("planning", "planner-01", "tenant-001")

    async def handler_failing(m: MessageEnvelope) -> None:
        raise RuntimeError("boom")

    async def handler_working(m: MessageEnvelope) -> None:
        pass

    await bus.subscribe(tenant_id="tenant-001", topic="agent.event", handler=handler_failing)
    await bus.subscribe(tenant_id="tenant-001", topic="agent.event", handler=handler_working)

    res = await bus.publish(EventMessage(sender=sender_addr))
    assert res.matched_subscribers == 2
    assert res.delivered == 1
    assert res.failed == 1
    assert len(res.failures) == 1
    assert res.failures[0].error_code == "HANDLER_FAILED"
    assert "unexpected exception" in res.failures[0].safe_message


@pytest.mark.anyio
async def test_handler_timeout_isolation():
    """
    Test 59: Handler timeout isolation.
    """
    bus = AgentBus(handler_timeout_seconds=0.05)
    sender_addr = make_address("planning", "planner-01", "tenant-001")

    async def handler_slow(m: MessageEnvelope) -> None:
        await asyncio.sleep(0.2)

    async def handler_fast(m: MessageEnvelope) -> None:
        pass

    await bus.subscribe(tenant_id="tenant-001", topic="agent.event", handler=handler_slow)
    await bus.subscribe(tenant_id="tenant-001", topic="agent.event", handler=handler_fast)

    res = await bus.publish(EventMessage(sender=sender_addr))
    assert res.matched_subscribers == 2
    assert res.delivered == 1
    assert res.failed == 1
    assert res.failures[0].error_code == "HANDLER_TIMEOUT"
    assert "timeout" in res.failures[0].safe_message


@pytest.mark.anyio
async def test_safe_failure_result():
    """
    Test 60: Safe failure result (no exception traces, payload leaks, etc).
    """
    bus = AgentBus()
    sender_addr = make_address("planning", "planner-01", "tenant-001")

    async def failing_handler(m: MessageEnvelope) -> None:
        raise ValueError("extremely_sensitive_api_key_value")

    await bus.subscribe(tenant_id="tenant-001", topic="agent.event", handler=failing_handler)

    res = await bus.publish(EventMessage(sender=sender_addr, payload={"leak": "me"}))
    assert res.failed == 1
    failure = res.failures[0]
    assert "sensitive" not in failure.safe_message
    assert "leak" not in failure.safe_message
    assert "ValueError" not in failure.safe_message


@pytest.mark.anyio
async def test_unsubscribe():
    """
    Test 61: Unsubscribe.
    """
    bus = AgentBus()
    sub = await bus.subscribe(
        tenant_id="tenant-001",
        topic="agent.event",
        handler=lambda msg: None,
    )
    assert await bus.unsubscribe(sub.subscription_id) is True
    assert await bus.unsubscribe(sub.subscription_id) is False

    with pytest.raises(TypeError, match="subscription_id must be a UUID"):
        await bus.unsubscribe("invalid-uuid")  # type: ignore


@pytest.mark.anyio
async def test_subscriber_counts():
    """
    Test 62: Subscriber counts.
    """
    bus = AgentBus()
    await bus.subscribe(tenant_id="tenant-001", topic="agent.event", handler=lambda m: None)
    await bus.subscribe(tenant_id="tenant-001", topic="agent.command", handler=lambda m: None)
    await bus.subscribe(tenant_id="tenant-002", topic="agent.event", handler=lambda m: None)

    assert await bus.subscriber_count() == 3
    assert await bus.subscriber_count(tenant_id="tenant-001") == 2
    assert await bus.subscriber_count(topic="agent.event") == 2
    assert await bus.subscriber_count(tenant_id="tenant-001", topic="agent.event") == 1
    assert await bus.subscriber_count(tenant_id="tenant-002", topic="agent.command") == 0


@pytest.mark.anyio
async def test_clear_tenant_isolation():
    """
    Test 63: Clear tenant isolation.
    """
    bus = AgentBus()
    await bus.subscribe(tenant_id="tenant-001", topic="agent.event", handler=lambda m: None)
    await bus.subscribe(tenant_id="tenant-002", topic="agent.event", handler=lambda m: None)

    removed = await bus.clear_tenant("tenant-001")
    assert removed == 1
    assert await bus.subscriber_count(tenant_id="tenant-001") == 0
    assert await bus.subscriber_count(tenant_id="tenant-002") == 1

    with pytest.raises(TypeError, match="tenant_id must be a string"):
        await bus.clear_tenant(123)  # type: ignore

    with pytest.raises(ValueError, match="tenant_id must not be blank"):
        await bus.clear_tenant("   ")


@pytest.mark.anyio
async def test_concurrent_publish_safety():
    """
    Test 64: Concurrent publish safety.
    """
    bus = AgentBus()
    sender_addr = make_address("planning", "planner-01", "tenant-001")

    count = 0

    async def handler(m: MessageEnvelope) -> None:
        nonlocal count
        await asyncio.sleep(0.01)
        count += 1

    await bus.subscribe(tenant_id="tenant-001", topic="agent.event", handler=handler)

    async def pub_task() -> None:
        await bus.publish(EventMessage(sender=sender_addr))

    async with asyncio.TaskGroup() as tg:
        for _ in range(10):
            tg.create_task(pub_task())

    assert count == 10


@pytest.mark.anyio
async def test_concurrent_subscribe_unsubscribe_safety():
    """
    Test 65: Concurrent subscribe/unsubscribe safety.
    """
    bus = AgentBus()

    async def sub_unsub_task() -> None:
        sub = await bus.subscribe(tenant_id="tenant-001", topic="agent.event", handler=lambda m: None)
        await asyncio.sleep(0.005)
        await bus.unsubscribe(sub.subscription_id)

    async with asyncio.TaskGroup() as tg:
        for _ in range(50):
            tg.create_task(sub_unsub_task())

    assert await bus.subscriber_count() == 0


@pytest.mark.anyio
async def test_lock_released_during_handler_execution():
    """
    Test 66: Lock released during handler execution.
    """
    bus = AgentBus()
    sender_addr = make_address("planning", "planner-01", "tenant-001")

    handler_entered = asyncio.Event()
    handler_resume = asyncio.Event()

    async def slow_handler(m: MessageEnvelope) -> None:
        handler_entered.set()
        await handler_resume.wait()

    await bus.subscribe(tenant_id="tenant-001", topic="agent.event", handler=slow_handler)

    async def publish_task() -> None:
        await bus.publish(EventMessage(sender=sender_addr))

    # Start publishing
    task = asyncio.create_task(publish_task())

    # Wait until handler is entered
    await handler_entered.wait()

    # Now verify we can subscribe and count while the publish is in progress (lock is released)
    # This will block if the lock is held during handler execution!
    sub = await bus.subscribe(tenant_id="tenant-001", topic="agent.command", handler=lambda m: None)
    assert await bus.subscriber_count() == 2

    # Let the handler finish
    handler_resume.set()
    await task


@pytest.mark.anyio
async def test_unsubscribe_during_delivery_affects_later_messages_only():
    """
    Test 67: Unsubscribe during delivery affects later messages only.
    """
    bus = AgentBus()
    sender_addr = make_address("planning", "planner-01", "tenant-001")

    sub_id = None
    first_received = asyncio.Event()
    second_received = False

    async def handler(m: MessageEnvelope) -> None:
        nonlocal second_received
        if m.payload.get("seq") == 1:
            first_received.set()
            # Unsubscribe ourselves while processing the first message
            assert await bus.unsubscribe(sub_id) is True
        elif m.payload.get("seq") == 2:
            second_received = True

    sub = await bus.subscribe(tenant_id="tenant-001", topic="agent.event", handler=handler)
    sub_id = sub.subscription_id

    # Publish message 1
    await bus.publish(EventMessage(sender=sender_addr, payload={"seq": 1}))
    await first_received.wait()

    # Publish message 2
    await bus.publish(EventMessage(sender=sender_addr, payload={"seq": 2}))
    assert not second_received


@pytest.mark.anyio
async def test_clear_tenant_during_delivery_affects_later_messages_only():
    """
    Test 68: Clear tenant during delivery affects later messages only.
    """
    bus = AgentBus()
    sender_addr = make_address("planning", "planner-01", "tenant-001")

    first_received = asyncio.Event()
    second_received = False

    async def handler(m: MessageEnvelope) -> None:
        nonlocal second_received
        if m.payload.get("seq") == 1:
            first_received.set()
            # Clear tenant during execution of first message
            removed = await bus.clear_tenant("tenant-001")
            assert removed == 1
        elif m.payload.get("seq") == 2:
            second_received = True

    await bus.subscribe(tenant_id="tenant-001", topic="agent.event", handler=handler)

    await bus.publish(EventMessage(sender=sender_addr, payload={"seq": 1}))
    await first_received.wait()

    await bus.publish(EventMessage(sender=sender_addr, payload={"seq": 2}))
    assert not second_received


@pytest.mark.anyio
async def test_payload_and_metadata_absent_from_logs():
    """
    Test 69: Payload and metadata absent from logs.
    """
    bus = AgentBus()
    sender_addr = make_address("planning", "planner-01", "tenant-001")

    async def handler(m: MessageEnvelope) -> None:
        pass

    await bus.subscribe(tenant_id="tenant-001", topic="agent.event", handler=handler)

    # Mock structlog logger warn and info calls
    with patch("app.services.ai.FieldOpsAI.runtime.agent_bus._logger") as mock_logger:
        msg = EventMessage(
            sender=sender_addr,
            payload={"super_secret_payload_key": "some_secret_value"},
            metadata={"another_private_key": "private_value"}
        )
        await bus.publish(msg)

        # Check all mock calls to make sure they do not leak the payload or metadata keys or values
        for method_name in ["info", "debug", "warning"]:
            method = getattr(mock_logger, method_name)
            for call in method.call_args_list:
                log_args, log_kwargs = call
                log_str = str(log_args) + str(log_kwargs)
                assert "super_secret_payload_key" not in log_str
                assert "some_secret_value" not in log_str
                assert "another_private_key" not in log_str
                assert "private_value" not in log_str


@pytest.mark.anyio
async def test_slow_sync_handler_timeout():
    """
    Test 70: Slow sync handler timeout.
    """
    import time
    bus = AgentBus(handler_timeout_seconds=0.05)
    sender_addr = make_address("planning", "planner-01", "tenant-001")

    def slow_sync(msg: MessageEnvelope) -> None:
        time.sleep(0.15)

    await bus.subscribe(tenant_id="tenant-001", topic="agent.event", handler=slow_sync)
    res = await bus.publish(EventMessage(sender=sender_addr))
    assert res.matched_subscribers == 1
    assert res.delivered == 0
    assert res.failed == 1
    assert res.failures[0].error_code == "HANDLER_TIMEOUT"


@pytest.mark.anyio
async def test_sync_handler_does_not_block_event_loop():
    import threading
    import time

    bus = AgentBus(
        handler_timeout_seconds=2.0,
    )

    sender = make_address(
        "planning",
        "planner-01",
        "tenant-001",
    )

    handler_started = threading.Event()
    handler_finished = threading.Event()

    def blocking_sync(
        message: MessageEnvelope,
    ) -> None:
        handler_started.set()
        time.sleep(0.4)
        handler_finished.set()

    await bus.subscribe(
        tenant_id="tenant-001",
        topic="agent.event",
        handler=blocking_sync,
    )

    publish_task = asyncio.create_task(
        bus.publish(
            EventMessage(sender=sender)
        )
    )

    started = await asyncio.to_thread(
        handler_started.wait,
        3.0,
    )

    assert started is True

    # Measure whether event loop is unblocked while blocking_sync is actively sleeping
    loop_step_start = time.perf_counter()
    await asyncio.sleep(0.02)
    loop_step_duration = time.perf_counter() - loop_step_start

    # If the event loop were blocked by the sync handler, this loop step would take >= 0.4 seconds.
    # Because it is properly run in a worker thread, this loop step resumes promptly (< 0.25s)
    # and the handler is still in the middle of its blocking sleep.
    assert loop_step_duration < 0.25
    assert not handler_finished.is_set()

    result = await publish_task

    assert result.delivered == 1
@pytest.mark.anyio
async def test_fast_handler_succeeds_beside_slow_sync_handler():
    """
    Test 72: Fast handler succeeds beside slow sync handler.
    """
    import time
    bus = AgentBus(handler_timeout_seconds=0.05)
    sender_addr = make_address("planning", "planner-01", "tenant-001")

    def slow_sync(msg: MessageEnvelope) -> None:
        time.sleep(0.1)

    fast_called = False

    async def fast_async(msg: MessageEnvelope) -> None:
        nonlocal fast_called
        fast_called = True

    await bus.subscribe(tenant_id="tenant-001", topic="agent.event", handler=slow_sync)
    await bus.subscribe(tenant_id="tenant-001", topic="agent.event", handler=fast_async)

    res = await bus.publish(EventMessage(sender=sender_addr))
    assert res.matched_subscribers == 2
    assert res.delivered == 1
    assert res.failed == 1
    assert fast_called


@pytest.mark.anyio
async def test_invalid_sync_handler_return_value():
    """
    Test 73: Invalid sync handler return value.
    """
    bus = AgentBus()
    sender_addr = make_address("planning", "planner-01", "tenant-001")

    def bad_sync(msg: MessageEnvelope) -> Any:
        return 42  # non-None, non-awaitable return value

    await bus.subscribe(tenant_id="tenant-001", topic="agent.event", handler=bad_sync)
    res = await bus.publish(EventMessage(sender=sender_addr))
    assert res.failed == 1
    assert res.failures[0].error_code == "HANDLER_FAILED"


@pytest.mark.anyio
async def test_topic_over_100_rejected_during_subscribe():
    """
    Test 74: topic over 100 rejected during subscribe.
    """
    bus = AgentBus()
    long_topic = "a" * 101
    with pytest.raises(ValueError, match="at most 100 characters"):
        await bus.subscribe(tenant_id="tenant-001", topic=long_topic, handler=lambda m: None)


@pytest.mark.anyio
async def test_tenant_over_50_rejected_during_subscribe():
    """
    Test 75: tenant over 50 rejected during subscribe.
    """
    bus = AgentBus()
    long_tenant = "t" * 51
    with pytest.raises(ValueError, match="at most 50 characters"):
        await bus.subscribe(tenant_id=long_tenant, topic="agent.event", handler=lambda m: None)


@pytest.mark.anyio
async def test_invalid_subscription_leaves_count_unchanged():
    """
    Test 76: Invalid subscription leaves count unchanged.
    """
    from pydantic import ValidationError
    bus = AgentBus()
    assert await bus.subscriber_count() == 0

    sub_addr = make_address(tenant_id="tenant-different")

    # This should fail validation because of tenant mismatch
    with pytest.raises(ValidationError, match="must match subscription tenant_id|tenant_id must match"):
        await bus.subscribe(
            tenant_id="tenant-001",
            topic="agent.event",
            handler=lambda m: None,
            subscriber=sub_addr,
        )

    # Verify count is still 0
    assert await bus.subscriber_count() == 0


@pytest.mark.anyio
async def test_subscriber_count_tenant_validation_and_normalization():
    """
    Test 77: subscriber_count tenant validation and normalization.
    """
    bus = AgentBus()
    await bus.subscribe(tenant_id="tenant-001", topic="agent.event", handler=lambda m: None)

    # Valid normalized tenant_id should succeed
    count = await bus.subscriber_count(tenant_id="   tenant-001   ")
    assert count == 1

    # Invalid long tenant_id should raise ValueError
    with pytest.raises(ValueError, match="at most 50 characters"):
        await bus.subscriber_count(tenant_id="t" * 51)


def test_failed_failures_count_mismatch():
    """
    Test 78: failed/failures count mismatch in PublishResult.
    """
    from pydantic import ValidationError
    with pytest.raises(ValidationError, match="must equal number of failures"):
        PublishResult(
            message_id=uuid4(),
            matched_subscribers=2,
            delivered=1,
            failed=1,
            failures=(), # 0 failures but failed=1
        )

@pytest.mark.anyio
async def test_subscribe_invalid_handler():
    """Test: subscribe raises InvalidMessageHandlerError for non-callable handler."""
    bus = AgentBus()
    with pytest.raises(InvalidMessageHandlerError, match="handler must be callable"):
        await bus.subscribe(tenant_id="tenant-001", topic="agent.event", handler="not_callable")

@pytest.mark.anyio
async def test_subscribe_invalid_subscriber():
    """Test: subscribe raises TypeError if subscriber is not an AgentAddress or None."""
    bus = AgentBus()
    with pytest.raises(TypeError, match="subscriber must be an AgentAddress or None"):
        await bus.subscribe(tenant_id="tenant-001", topic="agent.event", handler=lambda m: None, subscriber="not_an_address")

@pytest.mark.anyio
async def test_publish_invalid_message():
    """Test: publish raises TypeError if message is not a MessageEnvelope instance."""
    bus = AgentBus()
    with pytest.raises(TypeError, match="message must be a MessageEnvelope instance"):
        await bus.publish("not_a_message")

@pytest.mark.anyio
async def test_async_handler_returning_non_none():
    """Test: async-inspected handler returning non-None non-awaitable triggers handler failure."""
    bus = AgentBus()
    def async_non_awaitable_mock(msg):
        return "not_none"

    with patch("inspect.iscoroutinefunction", return_value=True):
        await bus.subscribe(tenant_id="tenant-001", topic="agent.test.asyncnonawaited", handler=async_non_awaitable_mock)
        msg = MessageEnvelope(
            sender=make_address(),
            message_type=MessageType.EVENT,
            topic="agent.test.asyncnonawaited"
        )
        res = await bus.publish(msg)
        assert res.failed == 1
        assert res.failures[0].error_code == "HANDLER_FAILED"

@pytest.mark.anyio
async def test_async_handler_returning_awaitable_non_none():
    """Test: async handler returning awaitable that yields non-None triggers handler failure."""
    bus = AgentBus()
    async def bad_async_handler(msg):
        return "some_value"

    await bus.subscribe(tenant_id="tenant-001", topic="agent.test.asyncawaitedval", handler=bad_async_handler)
    msg = MessageEnvelope(
        sender=make_address(),
        message_type=MessageType.EVENT,
        topic="agent.test.asyncawaitedval"
    )
    res = await bus.publish(msg)
    assert res.failed == 1
    assert res.failures[0].error_code == "HANDLER_FAILED"

@pytest.mark.anyio
async def test_sync_handler_returning_awaitable_non_none():
    """Test: sync handler returning awaitable that yields non-None triggers handler failure."""
    bus = AgentBus()
    def bad_sync_handler(msg):
        async def inner():
            return "some_value"
        return inner()

    await bus.subscribe(tenant_id="tenant-001", topic="agent.test.syncawaitedval", handler=bad_sync_handler)
    msg = MessageEnvelope(
        sender=make_address(),
        message_type=MessageType.EVENT,
        topic="agent.test.syncawaitedval"
    )
    res = await bus.publish(msg)
    assert res.failed == 1
    assert res.failures[0].error_code == "HANDLER_FAILED"


