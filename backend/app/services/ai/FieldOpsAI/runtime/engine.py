"""
AI Runtime Engine
=================

Core execution engine for FieldOps AI agents.

Tenant model
------------
tenant_id == organization_id (required on every TaskSpec). Organizations
own technicians, dispatchers, and their own priority queue. Customers are
not tenants — see app.models.domain for the full rationale. A job's
customer_id/technician_id live in TaskSpec.context, not in tenant_id.

Features
--------
- Async task execution
- Configurable maximum concurrency
- Per-task memory limit
- Per-task CPU-time limit
- Process isolation
- Explicit cancellation
- Timeout cancellation
- Priority execution (CRITICAL and HIGH bypass the Redis queue)
- Redis PriorityTaskQueue integration
- Celery integration
- Execution metrics
- Queue depth metrics
- Throughput metrics

Python 3.12
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import logging
import multiprocessing as mp
import time
import traceback
import uuid

from dataclasses import dataclass, field
from collections import deque
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable, Optional

import psutil
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.task_queue import PriorityTaskQueue, TaskPriority

logger = logging.getLogger("ai_runtime_engine")


# ============================================================================
# STATUS
# ============================================================================


class TaskStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"


# ============================================================================
# TASK MODELS
# ============================================================================


class TaskSpec(BaseModel):
    """
    Specification for one AI agent task.

    tenant_id is REQUIRED: it is the organization_id fulfilling the
    underlying job. Every task belongs to exactly one organization, even
    though the customer who triggered it (see context["customer_id"])
    may have jobs spread across many organizations.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    agent_type: str

    context: dict[str, Any] = Field(default_factory=dict)

    priority: TaskPriority = TaskPriority.NORMAL

    tenant_id: str  # organization_id — required, no default

    max_memory_mb: int = 256

    max_cpu_seconds: int = 30

    submitted_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @field_validator("tenant_id")
    @classmethod
    def _tenant_id_required(cls, value: str) -> str:
        if not value:
            raise ValueError(
                "tenant_id (organization_id) is required on every TaskSpec"
            )
        return value


class TaskResult(BaseModel):
    """Standard result returned by the runtime engine."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    task_id: str

    status: TaskStatus

    result: Optional[Any] = None

    error: Optional[str] = None

    started_at: Optional[datetime] = None

    finished_at: Optional[datetime] = None

    duration_seconds: Optional[float] = None

    queue_wait_seconds: Optional[float] = None


# ============================================================================
# RESOURCE LIMIT
# ============================================================================


class ResourceLimitExceeded(Exception):
    """Raised when a task exceeds CPU or memory limits."""

    def __init__(self, task_id: str, reason: str) -> None:
        self.task_id = task_id
        self.reason = reason
        super().__init__(f"Task {task_id} exceeded resource limit: {reason}")


# ============================================================================
# SUBPROCESS EXECUTION
# ============================================================================


def _sandbox_entrypoint(
    entrypoint: str,
    task_id: str,
    agent_type: str,
    context: dict[str, Any],
    max_memory_mb: int,
    connection: Any,
) -> None:
    """
    Entry point executed inside an isolated process.

    The child process imports the requested agent function and executes it.

    Expected function:

        def run_agent(agent_type, context):
            ...

    or an async function:

        async def run_agent(agent_type, context):
            ...
    """

    try:
        try:
            import resource

            limit_bytes = max_memory_mb * 1024 * 1024

            resource.setrlimit(resource.RLIMIT_AS, (limit_bytes, limit_bytes))

        except (ImportError, AttributeError, OSError, ValueError):
            # psutil parent-side monitoring is used as fallback on systems
            # without RLIMIT_AS.
            pass

        module_path, function_name = entrypoint.rsplit(":", 1)

        module = importlib.import_module(module_path)

        agent_function = getattr(module, function_name)

        result = agent_function(agent_type, context)

        if asyncio.iscoroutine(result):
            result = asyncio.run(result)

        connection.send(("ok", result))

    except MemoryError:
        connection.send(
            ("memory_error", f"MemoryError: task exceeded {max_memory_mb}MB")
        )

    except Exception as exc:
        connection.send(
            (
                "error",
                f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}",
            )
        )

    finally:
        with contextlib.suppress(Exception):
            connection.close()


# ============================================================================
# RESOURCE LIMITER
# ============================================================================


class ResourceLimiter:
    """
    Runs each task in its own process.

    Resource enforcement:
    - Memory: psutil monitoring
    - CPU: psutil process CPU time
    - Unix: RLIMIT_AS is also applied
    """

    def __init__(self, mp_context: str = "spawn", poll_interval: float = 0.05) -> None:
        self._ctx = mp.get_context(mp_context)
        self.poll_interval = poll_interval

    async def run_isolated(
        self,
        *,
        entrypoint: str,
        task_id: str,
        agent_type: str,
        context: dict[str, Any],
        max_memory_mb: int,
        max_cpu_seconds: int,
    ) -> Any:

        if max_memory_mb <= 0:
            raise ValueError("max_memory_mb must be greater than zero")

        if max_cpu_seconds <= 0:
            raise ValueError("max_cpu_seconds must be greater than zero")

        parent_conn, child_conn = self._ctx.Pipe(duplex=False)

        process = self._ctx.Process(
            target=_sandbox_entrypoint,
            args=(entrypoint, task_id, agent_type, context, max_memory_mb, child_conn),
            daemon=True,
        )

        process.start()
        child_conn.close()

        loop = asyncio.get_running_loop()
        ps_process = psutil.Process(process.pid)
        started_monotonic = loop.time()

        try:
            while True:

                if parent_conn.poll():
                    status, payload = await loop.run_in_executor(None, parent_conn.recv)

                    if status == "ok":
                        return payload

                    if status == "memory_error":
                        raise ResourceLimitExceeded(task_id, payload)

                    raise RuntimeError(payload)

                if not process.is_alive():
                    if process.exitcode not in (0, None):
                        raise RuntimeError(
                            f"Task {task_id} process exited with code {process.exitcode}"
                        )

                    raise RuntimeError(
                        f"Task {task_id} process exited without returning a result"
                    )

                try:
                    memory_bytes = ps_process.memory_info().rss
                    memory_mb = memory_bytes / (1024 * 1024)

                    if memory_mb > max_memory_mb:
                        logger.warning(
                            "Task exceeded memory limit",
                            extra={
                                "task_id": task_id,
                                "memory_mb": memory_mb,
                                "limit_mb": max_memory_mb,
                            },
                        )

                        process.terminate()
                        await loop.run_in_executor(None, process.join, 0.5)

                        if process.is_alive():
                            process.kill()

                        raise ResourceLimitExceeded(
                            task_id,
                            f"Memory limit exceeded: {memory_mb:.2f}MB > {max_memory_mb}MB",
                        )

                except psutil.NoSuchProcess:
                    pass

                try:
                    cpu_times = ps_process.cpu_times()
                    cpu_seconds = cpu_times.user + cpu_times.system

                    if cpu_seconds >= max_cpu_seconds:
                        logger.warning(
                            "Task exceeded CPU limit",
                            extra={
                                "task_id": task_id,
                                "cpu_seconds": cpu_seconds,
                                "limit_seconds": max_cpu_seconds,
                            },
                        )

                        process.terminate()
                        await loop.run_in_executor(None, process.join, 0.5)

                        if process.is_alive():
                            process.kill()

                        raise ResourceLimitExceeded(
                            task_id,
                            f"CPU limit exceeded: {cpu_seconds:.2f}s >= {max_cpu_seconds}s",
                        )

                except psutil.NoSuchProcess:
                    pass

                # Hard wall-clock safety limit: CPU limit is monitored
                # separately above; this prevents a task from hanging
                # forever while merely sleeping (not burning CPU).
                wall_time = loop.time() - started_monotonic
                safety_timeout = max_cpu_seconds * 2

                if wall_time >= safety_timeout:
                    process.terminate()
                    await loop.run_in_executor(None, process.join, 0.5)

                    if process.is_alive():
                        process.kill()

                    raise ResourceLimitExceeded(
                        task_id, f"Execution safety timeout after {safety_timeout}s"
                    )

                await asyncio.sleep(self.poll_interval)

        except asyncio.CancelledError:
            if process.is_alive():
                process.terminate()
                await loop.run_in_executor(None, process.join, 0.5)

                if process.is_alive():
                    process.kill()

            raise

        finally:
            if process.is_alive():
                process.terminate()
                await loop.run_in_executor(None, process.join, 0.5)

                if process.is_alive():
                    process.kill()

            with contextlib.suppress(Exception):
                parent_conn.close()


# ============================================================================
# METRICS
# ============================================================================


@dataclass
class EngineMetrics:
    """Runtime metrics."""

    total_submitted: int = 0
    total_succeeded: int = 0
    total_failed: int = 0
    total_cancelled: int = 0
    total_timed_out: int = 0
    total_duration_seconds: float = 0.0
    total_queue_wait_seconds: float = 0.0

    started_at: float = field(default_factory=time.monotonic)

    # Keep only a bounded latency history.
    # This prevents sustained load from growing memory indefinitely.
    _durations: deque[float] = field(
        default_factory=lambda: deque(maxlen=10_000)
    )

    # Total number of tasks for which duration was recorded.
    total_duration_samples: int = 0

    def record(self, result: TaskResult) -> None:
        if result.status == TaskStatus.SUCCEEDED:
            self.total_succeeded += 1
        elif result.status == TaskStatus.FAILED:
            self.total_failed += 1
        elif result.status == TaskStatus.CANCELLED:
            self.total_cancelled += 1
        elif result.status == TaskStatus.TIMED_OUT:
            self.total_timed_out += 1

        if result.duration_seconds is not None:
            self.total_duration_seconds += result.duration_seconds
            self.total_duration_samples += 1
            self._durations.append(result.duration_seconds)

        if result.queue_wait_seconds is not None:
            self.total_queue_wait_seconds += result.queue_wait_seconds

    @property
    def completed(self) -> int:
        return (
            self.total_succeeded
            + self.total_failed
            + self.total_cancelled
            + self.total_timed_out
        )

    @property
    def success_rate(self) -> float:
        if self.completed == 0:
            return 0.0
        return self.total_succeeded / self.completed

    @property
    def error_rate(self) -> float:
        if self.completed == 0:
            return 0.0
        return (self.total_failed + self.total_timed_out) / self.completed

    @property
    def avg_latency_seconds(self) -> float:
        if self.total_duration_samples == 0:
            return 0.0

        return (
            self.total_duration_seconds
            / self.total_duration_samples
        )

    @property
    def throughput(self) -> float:
        elapsed = time.monotonic() - self.started_at

        if elapsed <= 0:
            return 0.0

        return self.completed / elapsed

    def snapshot(
        self,
        *,
        queue_depth: int,
        in_flight: int,
    ) -> dict[str, Any]:
        return {
            "submitted": self.total_submitted,
            "completed": self.completed,
            "succeeded": self.total_succeeded,
            "failed": self.total_failed,
            "cancelled": self.total_cancelled,
            "timed_out": self.total_timed_out,
            "success_rate": round(self.success_rate, 4),
            "error_rate": round(self.error_rate, 4),
            "avg_latency_seconds": round(
                self.avg_latency_seconds,
                4,
            ),
            "avg_queue_wait_seconds": round(
                (
                    self.total_queue_wait_seconds / self.completed
                )
                if self.completed
                else 0.0,
                4,
            ),
            "throughput_tasks_per_second": round(
                self.throughput,
                4,
            ),
            "queue_depth": queue_depth,
            "in_flight": in_flight,
        }

# ============================================================================
# TYPES
# ============================================================================


AgentRunner = Callable[[TaskSpec], Awaitable[Any]]


@dataclass
class _TaskHandle:
    """Internal task bookkeeping."""

    spec: TaskSpec
    future: asyncio.Future
    queue_task_id: Optional[str] = None
    running_task: Optional[asyncio.Task] = None
    cancelled: bool = False


# ============================================================================
# ENGINE
# ============================================================================


class AIRuntimeEngine:
    """
    Core AI execution engine.

    Architecture:

        execute_task()
              |
              v
        Priority handling (CRITICAL/HIGH bypass queue)
              |
              v
        Redis PriorityTaskQueue (per-organization)
              |
              v
        bounded worker pool
              |
              v
        Semaphore
              |
              v
        ResourceLimiter
              |
              v
        isolated process
              |
              v
        TaskResult
              |
              v
        Metrics
    """

    # Priorities that bypass the Redis queue entirely and run immediately,
    # subject only to the concurrency semaphore.
    _BYPASS_PRIORITIES = (TaskPriority.CRITICAL, TaskPriority.HIGH)

    def __init__(
        self,
        *,
        max_concurrency: int = 100,
        task_queue: Optional[PriorityTaskQueue] = None,
        agent_runner: Optional[AgentRunner] = None,
        celery_app: Optional[Any] = None,
        high_priority_bypass_queue: bool = True,
    ) -> None:

        if max_concurrency <= 0:
            raise ValueError("max_concurrency must be greater than zero")

        self.max_concurrency = max_concurrency
        self._task_queue = task_queue
        self._celery_app = celery_app
        self._high_priority_bypass_queue = high_priority_bypass_queue

        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._resource_limiter = ResourceLimiter()

        # A custom runner is treated as trusted code. The default path
        # always uses process isolation.
        self._agent_runner = agent_runner

        self._handles: dict[str, _TaskHandle] = {}
        self._running_tasks: dict[str, asyncio.Task] = {}
        self._worker_tasks: list[asyncio.Task] = []

        self._metrics = EngineMetrics()

        self._closed = False
        self._started = False
        self._lifecycle_lock = asyncio.Lock()

    # ========================================================================
    # LIFECYCLE
    # ========================================================================

    async def start(self) -> None:
        """Start the Redis worker pool."""

        async with self._lifecycle_lock:
            if self._started:
                return

            if self._closed:
                raise RuntimeError("AIRuntimeEngine is shut down.")

            self._started = True

            if self._task_queue is None:
                return

            for index in range(self.max_concurrency):
                worker = asyncio.create_task(self._worker_loop(worker_id=index))
                self._worker_tasks.append(worker)

    async def shutdown(self, timeout: float = 10.0) -> None:
        """Gracefully shut down the engine."""

        if timeout <= 0:
            timeout = 0.1

        self._closed = True

        workers = list(self._worker_tasks)
        for worker in workers:
            worker.cancel()

        if workers:
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.gather(*workers, return_exceptions=True)

        self._worker_tasks.clear()

        running = list(self._running_tasks.keys())

        if running:
            try:
                await asyncio.wait_for(
                    asyncio.gather(
                        *(self.cancel_task(task_id) for task_id in running),
                        return_exceptions=True,
                    ),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                logger.warning("Runtime shutdown timed out")

        for task_id, handle in list(self._handles.items()):
            if not handle.future.done():
                result = TaskResult(
                    task_id=task_id,
                    status=TaskStatus.CANCELLED,
                    error="Engine shutdown",
                    finished_at=datetime.now(timezone.utc),
                )

                self._metrics.record(result)
                handle.future.set_result(result)

        self._handles.clear()
        self._started = False

    # ========================================================================
    # PUBLIC EXECUTION API
    # ========================================================================

    async def execute_task(self, spec: TaskSpec) -> TaskResult:
        """
        Submit a task and wait for its result.

        CRITICAL and HIGH priority bypass Redis when
        high_priority_bypass_queue=True, running immediately subject only
        to the concurrency semaphore.
        """

        if self._closed:
            raise RuntimeError("AIRuntimeEngine is shut down.")

        if spec.max_memory_mb <= 0:
            raise ValueError("max_memory_mb must be greater than zero")

        if spec.max_cpu_seconds <= 0:
            raise ValueError("max_cpu_seconds must be greater than zero")

        self._metrics.total_submitted += 1

        loop = asyncio.get_running_loop()
        future = loop.create_future()

        handle = _TaskHandle(spec=spec, future=future)
        self._handles[spec.task_id] = handle

        try:
            # ==============================================================
            # PRIORITY BYPASS (CRITICAL, HIGH)
            # ==============================================================

            if (
                self._task_queue is not None
                and self._high_priority_bypass_queue
                and spec.priority in self._BYPASS_PRIORITIES
            ):
                task = asyncio.create_task(self._run_task(spec, queue_wait=0.0))
                handle.running_task = task
                self._running_tasks[spec.task_id] = task

                try:
                    return await task
                except asyncio.CancelledError:
                    # _run_task already built a CANCELLED TaskResult and set
                    # it on handle.future before re-raising (see _run_task's
                    # CancelledError handler). Awaiting an already-cancelled
                    # Task re-raises CancelledError to every awaiter, so we
                    # must not let that propagate to our own caller — return
                    # the real result instead of surfacing a bare exception.
                    if handle.future.done():
                        return handle.future.result()
                    raise
                finally:
                    self._running_tasks.pop(spec.task_id, None)

            # ==============================================================
            # LOCAL EXECUTION (no queue configured at all)
            # ==============================================================

            if self._task_queue is None:
                task = asyncio.create_task(self._run_task(spec, queue_wait=0.0))
                handle.running_task = task
                self._running_tasks[spec.task_id] = task

                try:
                    return await task
                except asyncio.CancelledError:
                    if handle.future.done():
                        return handle.future.result()
                    raise
                finally:
                    self._running_tasks.pop(spec.task_id, None)

            # ==============================================================
            # REDIS QUEUE (NORMAL, LOW)
            # ==============================================================

            
            if not self._started:
                await self.start()
            
            queue_task_id = await asyncio.to_thread(
                self._task_queue.enqueue,
                task={"task_spec": spec.model_dump(mode="json")},
                priority=spec.priority,
                tenant_id=spec.tenant_id,
            )

            handle.queue_task_id = queue_task_id
            
            if handle.cancelled:
                if not handle.future.done():
                    result = TaskResult(
                        task_id=spec.task_id,
                        status=TaskStatus.CANCELLED,
                        error="Cancelled while queued",
                        finished_at=datetime.now(timezone.utc),
                    )
                    self._metrics.record(result)
                    handle.future.set_result(result)
                return await future

            try:
                return await future
            except asyncio.CancelledError:
                raise
                

        finally:
            # Don't remove a queued handle until the worker has completed it.
            if spec.task_id not in self._running_tasks:
                handle = self._handles.get(spec.task_id)

                if handle is not None and handle.future.done():
                    self._handles.pop(spec.task_id, None)

    # ========================================================================
    # CANCELLATION
    # ========================================================================

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel either a queued or running task."""

        handle = self._handles.get(task_id)

        if handle is None:
            return False

        handle.cancelled = True

        running = self._running_tasks.get(task_id)
        if running is None and handle.queue_task_id is not None:
            running = self._running_tasks.get(handle.queue_task_id)

        if running is not None:
            running.cancel()

            with contextlib.suppress(asyncio.CancelledError):
                await running

            return True
        
        if (
            running is None
            and self._task_queue is not None
            and handle.queue_task_id is not None
        ):
            removed = await asyncio.to_thread(
                self._task_queue.cancel,
                handle.queue_task_id,
                handle.spec.tenant_id,
            )

            if removed:
                if not handle.future.done():
                    result = TaskResult(
                        task_id=task_id,
                        status=TaskStatus.CANCELLED,
                        error="Cancelled",
                        finished_at=datetime.now(timezone.utc),
                    )

                    self._metrics.record(result)
                    handle.future.set_result(result)

                return True

            if not handle.future.done():
                result = TaskResult(
                    task_id=task_id,
                    status=TaskStatus.CANCELLED,
                    error="Cancelled",
                    finished_at=datetime.now(timezone.utc),
                )

                self._metrics.record(result)
                handle.future.set_result(result)

                return True

        return False
        

    async def _cancel_handle(self, task_id: str) -> None:
        handle = self._handles.get(task_id)

        if handle is None:
            return

        handle.cancelled = True

        running = self._running_tasks.get(task_id)

        if running is not None:
            running.cancel()

            with contextlib.suppress(asyncio.CancelledError):
                await running

            return

        if not handle.future.done():
            result = TaskResult(
                task_id=task_id,
                status=TaskStatus.CANCELLED,
                error="Cancelled",
                finished_at=datetime.now(timezone.utc),
            )

            self._metrics.record(result)
            handle.future.set_result(result)

    # ========================================================================
    # METRICS
    # ========================================================================

    def metrics(self) -> dict[str, Any]:
        """Return runtime metrics."""

        queue_depth = 0

        if self._task_queue is not None:
            try:
                queue_depth = self._task_queue.total_depth()
            except Exception:
                logger.exception("Failed to read queue depth")

        return self._metrics.snapshot(
            queue_depth=queue_depth,
            in_flight=len(self._running_tasks),
        )

    # ========================================================================
    # WORKER POOL
    # ========================================================================

    async def _worker_loop(self, worker_id: int) -> None:
        """Long-running Redis queue worker. Number of workers equals max_concurrency."""

        logger.debug("Runtime worker started", extra={"worker_id": worker_id})

        while not self._closed:
            try:
                queue_task = await asyncio.to_thread(self._task_queue.dequeue)

                if queue_task is None:
                    await asyncio.sleep(0.05)
                    continue

                await self._process_queued_task(queue_task)

            except asyncio.CancelledError:
                raise

            except Exception:
                logger.exception("Runtime worker failed", extra={"worker_id": worker_id})
                await asyncio.sleep(0.1)

    # ========================================================================
    # QUEUED TASK PROCESSING
    # ========================================================================

    async def _process_queued_task(self, queue_task: dict[str, Any]) -> None:

        queue_task_id = queue_task.get("task_id")

        if not queue_task_id:
            logger.error("Queue task missing task_id")
            return

        handle = self._find_handle(queue_task_id)
        
        payload = queue_task.get("payload", {})
        spec_data = payload.get("task_spec")

        if not spec_data:
            result = TaskResult(
                task_id=queue_task_id,
                status=TaskStatus.FAILED,
                error="Queue task does not contain task_spec",
                finished_at=datetime.now(timezone.utc),
            )

            self._metrics.record(result)

            if handle is not None and not handle.future.done():
                handle.future.set_result(result)

            return

        try:
            spec = TaskSpec.model_validate(spec_data)
        except Exception as exc:
            result = TaskResult(
                task_id=queue_task_id,
                status=TaskStatus.FAILED,
                error=f"Invalid TaskSpec: {exc}",
                finished_at=datetime.now(timezone.utc),
            )

            self._metrics.record(result)

            if handle is not None and not handle.future.done():
                handle.future.set_result(result)

            return

        # Redis queue ID becomes execution ID.
        spec = spec.model_copy(update={"task_id": queue_task_id})

        if handle is not None and handle.cancelled:
            if not handle.future.done():
                result = TaskResult(
                    task_id=queue_task_id,
                    status=TaskStatus.CANCELLED,
                    error="Cancelled while queued",
                    finished_at=datetime.now(timezone.utc),
                )

                self._metrics.record(result)
                handle.future.set_result(result)

            self._handles.pop(handle.spec.task_id, None)
            return

        created_at = queue_task.get("created_at")

        if created_at is None:
            queue_wait = 0.0
        else:
            try:
                queue_wait = max(0.0, time.time() - float(created_at))
            except (TypeError, ValueError):
                queue_wait = 0.0

        # Check cancellation again immediately before execution.
        # This closes the race where cancel_task() runs after the
        # first queued-state check but before _run_task().
        if handle is not None and handle.cancelled:
            if not handle.future.done():
                result = TaskResult(
                    task_id=spec.task_id,
                    status=TaskStatus.CANCELLED,
                    error="Cancelled while queued",
                    finished_at=datetime.now(timezone.utc),
                )

                self._metrics.record(result)
                handle.future.set_result(result)

            self._handles.pop(handle.spec.task_id, None)
            return
        handle = self._find_handle(spec.task_id)

        if handle is not None and handle.cancelled:
            if not handle.future.done():
                result = TaskResult(
                    task_id=spec.task_id,
                    status=TaskStatus.CANCELLED,
                    error="Cancelled before execution",
                    finished_at=datetime.now(timezone.utc),
                    queue_wait_seconds=queue_wait,
                )
                self._metrics.record(result)
                handle.future.set_result(result)

            self._handles.pop(handle.spec.task_id, None)
            return
    
        result = await self._run_task(spec, queue_wait=queue_wait)

        # IMPORTANT: handles are keyed by the ORIGINAL spec.task_id, but
        # queue_task_id is a different id assigned by PriorityTaskQueue.enqueue().
        # A direct self._handles.get(queue_task_id) here always misses and
        # silently strands the caller's future forever. Use _find_handle(),
        # same as the cancellation check above.
        handle = self._find_handle(queue_task_id)

        if handle is not None and not handle.future.done():
            handle.future.set_result(result)

        if handle is not None:
            self._handles.pop(handle.spec.task_id, None)

    def _find_handle(self, task_id: str) -> Optional[_TaskHandle]:
        handle = self._handles.get(task_id)

        if handle is not None:
            return handle

        # Redis queue ID may differ from original TaskSpec ID.
        for candidate in self._handles.values():
            if candidate.queue_task_id == task_id:
                return candidate

        return None

    # ========================================================================
    # TASK EXECUTION
    # ========================================================================

    async def _run_task(self, spec: TaskSpec, *, queue_wait: float) -> TaskResult:
        handle = self._find_handle(spec.task_id)

        if handle is not None and handle.cancelled:
            result = TaskResult(
                task_id=spec.task_id,
                status=TaskStatus.CANCELLED,
                error="Cancelled before execution",
                finished_at=datetime.now(timezone.utc),
                queue_wait_seconds=queue_wait,
            )

            self._metrics.record(result)

            if not handle.future.done():
                handle.future.set_result(result)

            return result

        await self._semaphore.acquire()

        started_at = datetime.now(timezone.utc)
        started_monotonic = time.perf_counter()

        current_task = asyncio.current_task()

        if current_task is not None:
            self._running_tasks[spec.task_id] = current_task

        status = TaskStatus.FAILED
        result_payload = None
        error: Optional[str] = None

        try:
            try:
                result_payload = await self._execute_agent(spec)
                status = TaskStatus.SUCCEEDED

            except ResourceLimitExceeded as exc:
                status = TaskStatus.TIMED_OUT
                error = str(exc)

            except asyncio.CancelledError:
                status = TaskStatus.CANCELLED
                error = "Cancelled"
                # finally will still run; re-raise so the outer handler
                # records metrics and resolves the caller's future.
                raise

            except Exception as exc:
                status = TaskStatus.FAILED
                error = f"{type(exc).__name__}: {exc}"

                logger.exception("AI task failed", extra={"task_id": spec.task_id})

        except asyncio.CancelledError:
            finished_at = datetime.now(timezone.utc)
            duration = time.perf_counter() - started_monotonic

            result = TaskResult(
                task_id=spec.task_id,
                status=TaskStatus.CANCELLED,
                result=None,
                error="Cancelled",
                started_at=started_at,
                finished_at=finished_at,
                duration_seconds=duration,
                queue_wait_seconds=queue_wait,
            )

            self._metrics.record(result)

            handle = self._find_handle(spec.task_id)          # <-- change this line


            if handle is not None and not handle.future.done():
                handle.future.set_result(result)

            raise

        finally:
            self._running_tasks.pop(spec.task_id, None)
            self._semaphore.release()

        finished_at = datetime.now(timezone.utc)
        duration = time.perf_counter() - started_monotonic

        result = TaskResult(
            task_id=spec.task_id,
            status=status,
            result=result_payload if status == TaskStatus.SUCCEEDED else None,
            error=error,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=duration,
            queue_wait_seconds=queue_wait,
        )

        self._metrics.record(result)
        self._handles.pop(spec.task_id, None)

        return result

    # ========================================================================
    # AGENT EXECUTION
    # ========================================================================

    async def _execute_agent(self, spec: TaskSpec) -> Any:
        """
        Execute an agent.

        Default: isolated subprocess.
        Custom agent runner: trusted in-process runner.

        For strict sandboxing, do not provide a custom agent_runner.
        """

        if self._agent_runner is not None:
            return await self._agent_runner(spec)

        entrypoint = spec.context.get("entrypoint")

        if not entrypoint:
            raise ValueError("TaskSpec.context['entrypoint'] is required.")

        return await self._resource_limiter.run_isolated(
            entrypoint=entrypoint,
            task_id=spec.task_id,
            agent_type=spec.agent_type,
            context=spec.context,
            max_memory_mb=spec.max_memory_mb,
            max_cpu_seconds=spec.max_cpu_seconds,
        )

    # ========================================================================
    # CELERY
    # ========================================================================

    def submit_to_celery(
        self,
        spec: TaskSpec,
        task_name: str = "ai_runtime.run_agent_task",
    ) -> Any:
        """
        Submit task to Celery.

        Celery handles cross-process and cross-machine execution with
        distributed workers.
        """

        if self._celery_app is None:
            raise RuntimeError("No celery_app configured.")

        return self._celery_app.send_task(
            task_name,
            kwargs={"spec": spec.model_dump(mode="json")},
            priority=(
                spec.priority.value if hasattr(spec.priority, "value") else spec.priority
            ),
        )