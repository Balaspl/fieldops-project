"""
Test suite for app.runtime.engine.AIRuntimeEngine

Covers every acceptance criterion from the spec:
  - 100 concurrent tasks supported
  - Memory limit: 256MB per task (resource limiter kills memory hog)
  - CPU timeout: 30s per task
  - 4 priority levels enforced (CRITICAL/HIGH bypass queue)
  - Cancellation <1s
  - Metrics: latency, throughput, error rate
  - Redis queue integration (via fakeredis)
  - Isolation: task A cannot access task B's data

Run with:
    pip install pytest pytest-asyncio fakeredis psutil pydantic --break-system-packages
    pytest test_engine.py -v
"""

import asyncio
from unittest.mock import patch
import time

import fakeredis
import pytest

from app.services.ai.FieldOpsAI.runtime.engine import (
    AIRuntimeEngine,
    TaskSpec,
    TaskResult,
    TaskStatus,
    ResourceLimitExceeded,
)
from app.services.task_queue import PriorityTaskQueue, TaskPriority


pytestmark = pytest.mark.asyncio


# ============================================================================
# HELPERS
# ============================================================================


def make_redis() -> "fakeredis.FakeRedis":
    # decode_responses=True is required — see task_queue.py's __init__ note.
    return fakeredis.FakeRedis(decode_responses=True)


async def fast_runner(spec: TaskSpec):
    """Trivial custom runner — bypasses real subprocess isolation for speed."""
    await asyncio.sleep(0.01)
    return {"task_id": spec.task_id, "echo": spec.context}


async def slow_runner(spec: TaskSpec):
    """Runner that hangs, for cancellation tests."""
    await asyncio.sleep(30)
    return "should never get here"


async def failing_runner(spec: TaskSpec):
    raise ValueError("boom")


# ============================================================================
# 1. TASK EXECUTION — basic contract
# ============================================================================


async def test_execute_task_returns_result():
    engine = AIRuntimeEngine(max_concurrency=5, agent_runner=fast_runner)

    spec = TaskSpec(agent_type="demo", tenant_id="org-1", context={"x": 1})
    result = await engine.execute_task(spec)

    assert isinstance(result, TaskResult)
    assert result.status == TaskStatus.SUCCEEDED
    assert result.result["echo"] == {"x": 1}
    assert result.duration_seconds is not None
    assert result.error is None


async def test_execute_task_records_failure():
    engine = AIRuntimeEngine(max_concurrency=5, agent_runner=failing_runner)

    spec = TaskSpec(agent_type="demo", tenant_id="org-1")
    result = await engine.execute_task(spec)

    assert result.status == TaskStatus.FAILED
    assert "boom" in result.error


async def test_tenant_id_is_required():
    """Confirms the tenant_id-required contract at the TaskSpec level."""
    with pytest.raises(Exception):
        TaskSpec(agent_type="demo", tenant_id="")

    with pytest.raises(Exception):
        TaskSpec(agent_type="demo")  # missing entirely


# ============================================================================
# 2. CONCURRENCY — 100 concurrent tasks
# ============================================================================


async def test_100_concurrent_tasks_execute_without_crash():
    engine = AIRuntimeEngine(max_concurrency=100, agent_runner=fast_runner)

    specs = [
        TaskSpec(agent_type="demo", tenant_id="org-1", context={"i": i})
        for i in range(100)
    ]

    results = await asyncio.gather(*(engine.execute_task(s) for s in specs))

    assert len(results) == 100
    assert all(r.status == TaskStatus.SUCCEEDED for r in results)
    # Every task's own context should come back untouched (isolation, see below).
    seen = {r.result["echo"]["i"] for r in results}
    assert seen == set(range(100))


async def test_concurrency_is_actually_bounded():
    """
    Verifies the semaphore really caps in-flight tasks at max_concurrency,
    rather than just "not crashing" with 100 tasks that happen to be fast.
    """
    max_concurrency = 5
    in_flight = 0
    peak_in_flight = 0
    lock = asyncio.Lock()

    async def tracking_runner(spec: TaskSpec):
        nonlocal in_flight, peak_in_flight
        async with lock:
            in_flight += 1
            peak_in_flight = max(peak_in_flight, in_flight)
        await asyncio.sleep(0.05)
        async with lock:
            in_flight -= 1
        return "ok"

    engine = AIRuntimeEngine(max_concurrency=max_concurrency, agent_runner=tracking_runner)

    specs = [TaskSpec(agent_type="demo", tenant_id="org-1") for _ in range(30)]
    results = await asyncio.gather(*(engine.execute_task(s) for s in specs))

    assert all(r.status == TaskStatus.SUCCEEDED for r in results)
    assert peak_in_flight <= max_concurrency, (
        f"peak in-flight was {peak_in_flight}, expected <= {max_concurrency} "
        "— the semaphore is not enforcing max_concurrency."
    )
    assert peak_in_flight == max_concurrency  # should actually saturate it


# ============================================================================
# 3. ISOLATION — task A cannot see task B's data
# ============================================================================


async def test_tasks_do_not_share_state():
    """
    Each task's context is independent; concurrently running tasks must
    never see another task's context or mutate shared state unexpectedly.
    """
    mutable_tracker = {}

    async def isolation_runner(spec: TaskSpec):
        # Simulate a runner that would leak state if isolation were broken:
        # write our own value, sleep to create overlap, then read it back.
        mutable_tracker[spec.task_id] = spec.context["secret"]
        await asyncio.sleep(0.02)
        # If another concurrently-running task overwrote a *shared* dict
        # keyed differently, this assertion still holds; the real isolation
        # guarantee under test is that spec.context itself is never mutated
        # by another task.
        return mutable_tracker[spec.task_id]

    engine = AIRuntimeEngine(max_concurrency=20, agent_runner=isolation_runner)

    specs = [
        TaskSpec(agent_type="demo", tenant_id="org-1", context={"secret": f"s-{i}"})
        for i in range(20)
    ]

    results = await asyncio.gather(*(engine.execute_task(s) for s in specs))

    returned = {r.result for r in results}
    expected = {f"s-{i}" for i in range(20)}
    assert returned == expected, "a task returned another task's secret — isolation broken"


@pytest.mark.slow
async def test_process_isolation_real_subprocess():
    """
    Exercises the REAL default path (no custom agent_runner) — spawns an
    actual subprocess per task via ResourceLimiter, proving OS-level
    process isolation rather than just asyncio-level concurrency.

    Requires a real importable entrypoint on disk; skip if not set up.
    """
    import os
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        module_path = os.path.join(tmp, "agent_mod.py")
        with open(module_path, "w") as f:
            f.write(
                "def run_agent(agent_type, context):\n"
                "    return {'pid_marker': context['marker']}\n"
            )

        import sys
        sys.path.insert(0, tmp)
        try:
            engine = AIRuntimeEngine(max_concurrency=5)  # no agent_runner -> real subprocess path
            spec = TaskSpec(
                agent_type="demo",
                tenant_id="org-1",
                context={"entrypoint": "agent_mod:run_agent", "marker": "abc"},
                max_memory_mb=128,
                max_cpu_seconds=5,
            )
            result = await engine.execute_task(spec)
            assert result.status == TaskStatus.SUCCEEDED
            assert result.result["pid_marker"] == "abc"
        finally:
            sys.path.remove(tmp)


# ============================================================================
# 4. RESOURCE LIMITS — memory and CPU
# ============================================================================


@pytest.mark.slow
async def test_memory_limit_kills_memory_hog():
    """
    Real subprocess test: a runner that allocates far more than its
    max_memory_mb budget must be terminated with ResourceLimitExceeded,
    surfaced as TaskStatus.TIMED_OUT.
    """
    import os
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        module_path = os.path.join(tmp, "memory_hog.py")
        with open(module_path, "w") as f:
            f.write(
                "def run_agent(agent_type, context):\n"
                "    # Allocate ~500MB, well past a 64MB limit.\n"
                "    hog = bytearray(500 * 1024 * 1024)\n"
                "    return len(hog)\n"
            )

        import sys
        sys.path.insert(0, tmp)
        try:
            engine = AIRuntimeEngine(max_concurrency=2)
            spec = TaskSpec(
                agent_type="demo",
                tenant_id="org-1",
                context={"entrypoint": "memory_hog:run_agent"},
                max_memory_mb=64,
                max_cpu_seconds=10,
            )
            result = await engine.execute_task(spec)

            assert result.status == TaskStatus.TIMED_OUT
            assert "memory" in result.error.lower() or "Memory" in result.error
        finally:
            sys.path.remove(tmp)


@pytest.mark.slow
async def test_cpu_limit_terminates_busy_loop():
    import os
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        module_path = os.path.join(tmp, "cpu_hog.py")
        with open(module_path, "w") as f:
            f.write(
                "def run_agent(agent_type, context):\n"
                "    x = 0\n"
                "    while True:\n"
                "        x += 1\n"
            )

        import sys
        sys.path.insert(0, tmp)
        try:
            engine = AIRuntimeEngine(max_concurrency=2)
            spec = TaskSpec(
                agent_type="demo",
                tenant_id="org-1",
                context={"entrypoint": "cpu_hog:run_agent"},
                max_memory_mb=256,
                max_cpu_seconds=1,  # short, so the test doesn't take forever
            )
            start = time.monotonic()
            result = await engine.execute_task(spec)
            elapsed = time.monotonic() - start

            assert result.status == TaskStatus.TIMED_OUT
            assert "CPU" in result.error
            # Safety timeout is max_cpu_seconds * 2; should terminate well
            # before that plus polling slack.
            assert elapsed < 5
        finally:
            sys.path.remove(tmp)


# ============================================================================
# 5. PRIORITY — CRITICAL/HIGH bypass, NORMAL/LOW go through Redis
# ============================================================================


async def test_high_and_critical_bypass_queue():
    """
    With a task_queue configured, CRITICAL/HIGH tasks must complete
    without ever touching the Redis queue (bypass path), while NORMAL/LOW
    go through it.
    """
    redis = make_redis()
    queue = PriorityTaskQueue(redis)
    engine = AIRuntimeEngine(max_concurrency=10, task_queue=queue, agent_runner=fast_runner)

    critical_spec = TaskSpec(agent_type="demo", tenant_id="org-1", priority=TaskPriority.CRITICAL)
    high_spec = TaskSpec(agent_type="demo", tenant_id="org-1", priority=TaskPriority.HIGH)

    critical_result = await engine.execute_task(critical_spec)
    high_result = await engine.execute_task(high_spec)

    assert critical_result.status == TaskStatus.SUCCEEDED
    assert high_result.status == TaskStatus.SUCCEEDED
    # Bypass path never enqueues into Redis at all.
    assert queue.total_depth() == 0

    await engine.shutdown(timeout=2)


async def test_normal_priority_goes_through_queue_and_completes():
    redis = make_redis()
    queue = PriorityTaskQueue(redis)
    engine = AIRuntimeEngine(max_concurrency=10, task_queue=queue, agent_runner=fast_runner)

    spec = TaskSpec(agent_type="demo", tenant_id="org-1", priority=TaskPriority.NORMAL)
    result = await engine.execute_task(spec)

    assert result.status == TaskStatus.SUCCEEDED
    await engine.shutdown(timeout=2)


async def test_all_four_priority_levels_complete():
    redis = make_redis()
    queue = PriorityTaskQueue(redis)
    engine = AIRuntimeEngine(max_concurrency=10, task_queue=queue, agent_runner=fast_runner)

    specs = [
        TaskSpec(agent_type="demo", tenant_id="org-1", priority=p)
        for p in (TaskPriority.CRITICAL, TaskPriority.HIGH, TaskPriority.NORMAL, TaskPriority.LOW)
    ]

    results = await asyncio.gather(*(engine.execute_task(s) for s in specs))
    assert all(r.status == TaskStatus.SUCCEEDED for r in results)

    await engine.shutdown(timeout=2)


async def test_critical_and_high_run_even_under_full_queue_backlog():
    """
    Regression guard for the earlier bug where only HIGH (not CRITICAL)
    bypassed the queue. Fill the queue with NORMAL/LOW noise, then confirm
    a CRITICAL task still completes promptly via the bypass path.
    """
    redis = make_redis()
    queue = PriorityTaskQueue(redis)
    engine = AIRuntimeEngine(max_concurrency=10, task_queue=queue, agent_runner=fast_runner)

    # Don't start the worker loop — simulate backlog by enqueueing directly
    # without ever draining it, then check bypass still works.
    for i in range(20):
        queue.enqueue({"noise": i}, TaskPriority.LOW, "org-1")

    spec = TaskSpec(agent_type="demo", tenant_id="org-1", priority=TaskPriority.CRITICAL)

    start = time.monotonic()
    result = await engine.execute_task(spec)
    elapsed = time.monotonic() - start

    assert result.status == TaskStatus.SUCCEEDED
    assert elapsed < 1.0, "CRITICAL task should not wait behind queued LOW tasks"

    await engine.shutdown(timeout=2)


# ============================================================================
# 6. CANCELLATION — must stop within 1s
# ============================================================================


async def test_cancel_running_task_under_one_second():
    engine = AIRuntimeEngine(max_concurrency=5, agent_runner=slow_runner)

    spec = TaskSpec(agent_type="demo", tenant_id="org-1")
    task = asyncio.create_task(engine.execute_task(spec))

    await asyncio.sleep(0.1)  # let it actually start running

    start = time.monotonic()
    cancelled = await engine.cancel_task(spec.task_id)
    elapsed = time.monotonic() - start

    assert cancelled is True
    assert elapsed < 1.0, f"cancellation took {elapsed:.2f}s, must be < 1s"

    result = await task
    assert result.status == TaskStatus.CANCELLED


async def test_cancel_queued_task_before_it_runs():
    """Cancelling a task still sitting in Redis (not yet running) should
    resolve immediately without ever executing the agent."""
    redis = make_redis()
    queue = PriorityTaskQueue(redis)

    executed = False

    async def marking_runner(spec: TaskSpec):
        nonlocal executed
        await asyncio.sleep(0.1)
        executed = True
        return "ran"


    # Engine with no worker started (task_queue set but .start() not called
    # implicitly until execute_task enqueues) — cancel before draining.
    engine = AIRuntimeEngine(max_concurrency=1, task_queue=queue, agent_runner=marking_runner)

    spec = TaskSpec(agent_type="demo", tenant_id="org-1", priority=TaskPriority.NORMAL)
    exec_task = asyncio.create_task(engine.execute_task(spec))

    # Give it a moment to enqueue but try to cancel almost immediately.
    await asyncio.sleep(0.01)
    await engine.cancel_task(spec.task_id)

    # Let workers spin briefly; the cancelled flag should prevent execution.
    try:
        result = await asyncio.wait_for(exec_task, timeout=2)
        assert result.status == TaskStatus.CANCELLED
    except asyncio.TimeoutError:
        pytest.fail("cancelled queued task never resolved")

    await engine.shutdown(timeout=2)


async def test_shutdown_cancels_all_in_flight_tasks():
    engine = AIRuntimeEngine(max_concurrency=5, agent_runner=slow_runner)

    specs = [TaskSpec(agent_type="demo", tenant_id="org-1") for _ in range(3)]
    tasks = [asyncio.create_task(engine.execute_task(s)) for s in specs]

    await asyncio.sleep(0.1)

    start = time.monotonic()
    await engine.shutdown(timeout=2)
    elapsed = time.monotonic() - start

    results = await asyncio.gather(*tasks, return_exceptions=True)
    assert all(
        isinstance(r, TaskResult) and r.status == TaskStatus.CANCELLED for r in results
    )
    assert elapsed < 3


# ============================================================================
# 7. METRICS — latency, throughput, error rate
# ============================================================================


async def test_metrics_accuracy():
    engine = AIRuntimeEngine(max_concurrency=10, agent_runner=fast_runner)

    ok_specs = [TaskSpec(agent_type="demo", tenant_id="org-1") for _ in range(7)]
    await asyncio.gather(*(engine.execute_task(s) for s in ok_specs))

    fail_engine = AIRuntimeEngine(max_concurrency=10, agent_runner=failing_runner)
    fail_specs = [TaskSpec(agent_type="demo", tenant_id="org-1") for _ in range(3)]
    await asyncio.gather(*(fail_engine.execute_task(s) for s in fail_specs))

    ok_metrics = engine.metrics()
    fail_metrics = fail_engine.metrics()

    assert ok_metrics["submitted"] == 7
    assert ok_metrics["succeeded"] == 7
    assert ok_metrics["failed"] == 0
    assert ok_metrics["success_rate"] == 1.0
    assert ok_metrics["error_rate"] == 0.0
    assert ok_metrics["avg_latency_seconds"] > 0

    assert fail_metrics["submitted"] == 3
    assert fail_metrics["failed"] == 3
    assert fail_metrics["success_rate"] == 0.0
    assert fail_metrics["error_rate"] == 1.0


async def test_metrics_queue_depth_reflects_redis():
    redis = make_redis()
    queue = PriorityTaskQueue(redis)
    engine = AIRuntimeEngine(max_concurrency=1, task_queue=queue, agent_runner=fast_runner)

    # Enqueue extra noise directly so depth > 0 while nothing drains it yet.
    queue.enqueue({"noise": 1}, TaskPriority.NORMAL, "org-1")
    queue.enqueue({"noise": 2}, TaskPriority.NORMAL, "org-1")

    metrics = engine.metrics()
    assert metrics["queue_depth"] >= 2

    await engine.shutdown(timeout=2)


async def test_avg_latency_reasonable_under_load():
    engine = AIRuntimeEngine(max_concurrency=50, agent_runner=fast_runner)

    specs = [TaskSpec(agent_type="demo", tenant_id="org-1") for _ in range(50)]
    await asyncio.gather(*(engine.execute_task(s) for s in specs))

    metrics = engine.metrics()
    # fast_runner sleeps 0.01s; latency should be in that ballpark, not
    # blown up by queueing/semaphore contention at this concurrency.
    assert metrics["avg_latency_seconds"] < 0.5
    assert metrics["throughput_tasks_per_second"] >= 0


# ============================================================================
# 8. VALIDATION — bad inputs rejected
# ============================================================================


@pytest.mark.parametrize("field,value", [("max_memory_mb", 0), ("max_cpu_seconds", -1)])
async def test_invalid_resource_limits_rejected(field, value):
    engine = AIRuntimeEngine(max_concurrency=5, agent_runner=fast_runner)
    spec = TaskSpec(agent_type="demo", tenant_id="org-1", **{field: value})

    with pytest.raises(ValueError):
        await engine.execute_task(spec)


async def test_execute_after_shutdown_raises():
    engine = AIRuntimeEngine(max_concurrency=5, agent_runner=fast_runner)
    await engine.shutdown(timeout=1)

    spec = TaskSpec(agent_type="demo", tenant_id="org-1")
    with pytest.raises(RuntimeError):
        await engine.execute_task(spec)


def test_sandbox_entrypoint_async_success():
    from unittest.mock import MagicMock

    connection = MagicMock()

    async def run_agent(agent_type, context):
        return {"agent": agent_type, "value": context["value"]}

    with patch("importlib.import_module") as mock_import:
        module = MagicMock()
        module.run_agent = run_agent
        mock_import.return_value = module

        from app.services.ai.FieldOpsAI.runtime.engine import _sandbox_entrypoint

        _sandbox_entrypoint(
            "fake_module:run_agent",
            "task-1",
            "demo",
            {"value": "ok"},
            128,
            connection,
        )

    connection.send.assert_called_once_with(
        ("ok", {"agent": "demo", "value": "ok"})
    )


def test_sandbox_entrypoint_memory_error():
    from unittest.mock import MagicMock

    connection = MagicMock()

    with patch("importlib.import_module") as mock_import:
        module = MagicMock()

        def run_agent(agent_type, context):
            raise MemoryError()

        module.run_agent = run_agent
        mock_import.return_value = module

        from app.services.ai.FieldOpsAI.runtime.engine import _sandbox_entrypoint

        _sandbox_entrypoint(
            "fake_module:run_agent",
            "task-1",
            "demo",
            {},
            128,
            connection,
        )

    connection.send.assert_called_once_with(
        ("memory_error", "MemoryError: task exceeded 128MB")
    )


def test_sandbox_entrypoint_general_exception():
    from unittest.mock import MagicMock

    connection = MagicMock()

    with patch("importlib.import_module") as mock_import:
        module = MagicMock()

        def run_agent(agent_type, context):
            raise ValueError("test error")

        module.run_agent = run_agent
        mock_import.return_value = module

        from app.services.ai.FieldOpsAI.runtime.engine import _sandbox_entrypoint

        _sandbox_entrypoint(
            "fake_module:run_agent",
            "task-1",
            "demo",
            {},
            128,
            connection,
        )

    status, message = connection.send.call_args[0][0]

    assert status == "error"
    assert "ValueError: test error" in message