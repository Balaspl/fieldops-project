from enum import IntEnum
from typing import Any, Optional
import json
import time
import uuid


class QueueBackpressureError(Exception):
    """Raised when queue ingestion is paused because the queue is too deep."""


class TaskPriority(IntEnum):
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3


class PriorityTaskQueue:
    """
    Redis-backed priority task queue.

    Tenant model
    ------------
    tenant_id == organization_id.

    Every organization owns its own technicians, dispatchers, and job
    queue. Customers are NOT tenants: a customer may book jobs across
    many different organizations, so a customer cannot be the sharding
    key. Jobs are tagged with tenant_id = the organization fulfilling
    them; customer_id/technician_id/job_id live inside the task payload
    (context), not in the tenant boundary.

    tenant_id is REQUIRED on every enqueue. There is deliberately no
    "global"/tenant-less queue: a task with no owning organization has
    no dispatcher who could ever act on it, and a bare global queue is
    unreachable by dequeue() by design (previously this was silently
    dead code — now it's a hard error at submission time instead of a
    silent hang at dequeue time).

    Queue structure:
        task_queue:tenant:{tenant_id}

    Lower priority number means higher priority.
    """

    TENANT_QUEUE_PREFIX = "task_queue:tenant:"

    TENANT_REGISTRY = "task_queue:tenants"
    ROUND_ROBIN_TENANT = "task_queue:round_robin_tenant"
    DLQ_KEY = "task_queue:dlq"
    BACKPRESSURE_THRESHOLD = 10_000
    THROUGHPUT_KEY = "task_queue:throughput"

    def __init__(self, redis_client):
        # NOTE: redis_client MUST be constructed with decode_responses=True.
        # Without it, smembers()/get() return bytes and the round-robin
        # tenant comparisons below (str-to-str) will silently misbehave
        # or raise TypeError when compared against str tenant ids.
        self.redis = redis_client

    def _queue_key(self, tenant_id: str) -> str:
        return f"{self.TENANT_QUEUE_PREFIX}{tenant_id}"

    def enqueue(
        self,
        task: dict[str, Any],
        priority: TaskPriority,
        tenant_id: str,
    ) -> str:
        """
        Add a task to the organization's Redis sorted set.

        Args:
            task: arbitrary task payload (e.g. {"task_spec": ...})
            priority: TaskPriority
            tenant_id: organization_id. Required — every job belongs to
                the organization fulfilling it, even though the customer
                who booked it may not.

        Returns:
            task_id
        """

        if not tenant_id:
            raise ValueError(
                "tenant_id (organization_id) is required — "
                "every task must belong to the organization fulfilling it."
            )

        if not isinstance(priority, TaskPriority):
            priority = TaskPriority(priority)

        if self.is_backpressured():
            raise QueueBackpressureError(
                "Task queue ingestion paused: queue depth exceeds "
                f"{self.BACKPRESSURE_THRESHOLD}"
            )

        task_id = str(uuid.uuid4())

        payload = {
            "task_id": task_id,
            "tenant_id": tenant_id,
            "priority": priority.name,
            "created_at": time.time(),
            "payload": task,
        }

        self.redis.sadd(self.TENANT_REGISTRY, tenant_id)

        queue_key = self._queue_key(tenant_id)

        # Priority comes first, creation time is used as tie breaker.
        score = (priority.value * 1_000_000_000_000) + time.time()

        self.redis.zadd(queue_key, {json.dumps(payload): score})

        return task_id
    
    def cancel(self, task_id: str, tenant_id: str) -> bool:
        """Remove a queued task from Redis before it is dequeued."""

        queue_key = self._queue_key(tenant_id)

        for raw_task in self.redis.zrange(queue_key, 0, -1):
            task = json.loads(raw_task)

            if task.get("task_id") == task_id:
                removed = self.redis.zrem(queue_key, raw_task)

                if removed:
                    if self.redis.zcard(queue_key) == 0:
                        self.redis.srem(self.TENANT_REGISTRY, tenant_id)

                    return True

        return False

    def depth(self, tenant_id: str) -> int:
        """Return number of tasks currently waiting for one organization."""

        return self.redis.zcard(self._queue_key(tenant_id))

    def peek(self, tenant_id: str) -> Optional[dict[str, Any]]:
        """Look at the highest-priority task for one org without removing it."""

        result = self.redis.zrange(self._queue_key(tenant_id), 0, 0)

        if not result:
            return None

        return json.loads(result[0])

    def dequeue(self) -> Optional[dict[str, Any]]:
        """
        Dequeue one task using priority first and round-robin fairness
        between organizations sharing the same highest priority.

        Priority:
            CRITICAL > HIGH > NORMAL > LOW

        Fairness:
            Organizations sharing the same priority get round-robin turns,
            so one large organization can't starve a smaller one.
        """

        tenants = sorted(self.redis.smembers(self.TENANT_REGISTRY))

        if not tenants:
            return None

        candidates = []

        for tenant_id in tenants:
            queue_key = self._queue_key(tenant_id)

            result = self.redis.zrange(queue_key, 0, 0)

            if not result:
                continue

            raw_task = result[0]
            task = json.loads(raw_task)

            candidates.append(
                {
                    "tenant_id": tenant_id,
                    "raw_task": raw_task,
                    "task": task,
                }
            )

        if not candidates:
            return None

        highest_priority = min(
            TaskPriority[candidate["task"]["priority"]].value
            for candidate in candidates
        )

        priority_candidates = [
            candidate
            for candidate in candidates
            if TaskPriority[candidate["task"]["priority"]].value
            == highest_priority
        ]

        last_tenant = self.redis.get(self.ROUND_ROBIN_TENANT)

        priority_tenants = [c["tenant_id"] for c in priority_candidates]

        if last_tenant in priority_tenants:
            last_index = priority_tenants.index(last_tenant)
            selected_index = (last_index + 1) % len(priority_tenants)
        else:
            # The previous tenant may have become empty and been removed
            # from the registry. Continue with the next surviving tenant
            # in sorted order after it, for stable round-robin progress.
            selected_index = 0

            if last_tenant is not None:
                for index, tenant_id in enumerate(priority_tenants):
                    if tenant_id > last_tenant:
                        selected_index = index
                        break

        selected = priority_candidates[selected_index]

        tenant_id = selected["tenant_id"]
        raw_task = selected["raw_task"]

        queue_key = self._queue_key(tenant_id)

        removed = self.redis.zrem(queue_key, raw_task)

        if not removed:
            # Lost a race with another worker for the same task.
            return None

        self.redis.incr(self.THROUGHPUT_KEY)
        self.redis.set(self.ROUND_ROBIN_TENANT, tenant_id)

        if self.redis.zcard(queue_key) == 0:
            self.redis.srem(self.TENANT_REGISTRY, tenant_id)

        return selected["task"]

    def move_to_dlq(self, task: dict[str, Any], reason: str) -> None:
        """Move a failed task to the dead letter queue."""

        dlq_entry = {
            "task": task,
            "reason": reason,
            "moved_at": time.time(),
        }

        self.redis.rpush(self.DLQ_KEY, json.dumps(dlq_entry))

    def is_backpressured(self, tenant_id: Optional[str] = None) -> bool:
        """Return True when total queue depth is above the threshold."""

        return self.total_depth() > self.BACKPRESSURE_THRESHOLD

    def oldest_task_age(self, tenant_id: str) -> float:
        """Return the age in seconds of the oldest queued task for an org."""

        task = self.peek(tenant_id)

        if task is None:
            return 0.0

        return max(0.0, time.time() - task["created_at"])

    def throughput(self) -> int:
        """Return the number of successfully dequeued tasks, across all orgs."""

        return int(self.redis.get(self.THROUGHPUT_KEY) or 0)

    def stats(self, tenant_id: str) -> dict[str, Any]:
        """Return current queue statistics for one organization."""

        return {
            "tenant_id": tenant_id,
            "depth": self.depth(tenant_id),
            "oldest_task_age": self.oldest_task_age(tenant_id),
            "throughput": self.throughput(),
        }

    def total_depth(self) -> int:
        """Return the total number of queued tasks across all organizations."""

        total = 0

        tenant_queue_pattern = f"{self.TENANT_QUEUE_PREFIX}*"

        for queue_key in self.redis.scan_iter(match=tenant_queue_pattern):
            total += self.redis.zcard(queue_key)

        return total

# ---------------------------------------------------------------------------
# Task Retry Rules Re-exports (Story: Configure task retry rules)
# ---------------------------------------------------------------------------

from app.celery_app import (
    get_task_retry_rules_config,
    configure_task_retry_rules,
    ConfigureTaskRetryRules,
    Configure_task_retry_rules,
    configure_retry_rules,
    ConfigureRetryRules,
    get_retry_rules_config,
)

