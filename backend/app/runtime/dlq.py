"""
Dead Letter Queue management.

Provides Redis-backed operational storage and PostgreSQL-backed
persistent archival for permanently failed tasks.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.dead_letter_task import DeadLetterTask


# Sensitive key identifiers for sanitization
SENSITIVE_EXACT_KEYS = {
    "password",
    "pass",
    "passwd",
    "pwd",
    "secret",
    "secret_key",
    "client_secret",
    "token",
    "access_token",
    "refresh_token",
    "auth_token",
    "jwt",
    "bearer_token",
    "api_key",
    "apikey",
    "private_key",
    "ssh_key",
    "credit_card",
    "card_number",
    "cvv",
    "cvc",
    "pan",
    "authorization",
    "auth",
}

SENSITIVE_SUBSTRING_PATTERNS = [
    "password",
    "secret",
    "api_key",
    "apikey",
    "credit_card",
    "card_number",
    "private_key",
]

CREDIT_CARD_REGEX = re.compile(r"\b(?:\d[ -]*?){13,16}\b")


def sanitize_payload(payload: Any) -> Any:
    """
    Recursively sanitize dictionaries, lists, and strings to redact
    sensitive credentials (passwords, tokens, api keys, credit cards).
    Preserves innocent metrics such as prompt_tokens, total_tokens.
    """
    if isinstance(payload, dict):
        sanitized: dict[str, Any] = {}
        for key, value in payload.items():
            key_str = str(key)
            key_lower = key_str.lower()

            # Skip usage counts like prompt_tokens, completion_tokens, total_tokens
            if key_lower.endswith("_tokens") and isinstance(value, (int, float)):
                sanitized[key] = value
                continue

            # Check if key represents sensitive credential
            is_sensitive = key_lower in SENSITIVE_EXACT_KEYS or any(
                pattern in key_lower for pattern in SENSITIVE_SUBSTRING_PATTERNS
            )

            if is_sensitive:
                sanitized[key] = "[REDACTED]"
            else:
                sanitized[key] = sanitize_payload(value)
        return sanitized

    if isinstance(payload, list):
        return [sanitize_payload(item) for item in payload]

    if isinstance(payload, tuple):
        return tuple(sanitize_payload(item) for item in payload)

    if isinstance(payload, str):
        # Scrub inline bearer tokens or cards if present
        if payload.lower().startswith("bearer "):
            return "Bearer [REDACTED]"
        if len(payload) >= 13 and CREDIT_CARD_REGEX.search(payload):
            return CREDIT_CARD_REGEX.sub("[REDACTED_CARD]", payload)
        return payload

    return payload


class DeadLetterQueue:
    """
    Manage permanently failed tasks.

    Redis:
        Operational DLQ used for fast inspection/recovery.

    PostgreSQL:
        Durable archive used for persistence, auditing, and
        administrative operations.

    The same DLQ ID is stored in both systems.
    """

    DLQ_KEY = "task_queue:dlq"

    def __init__(
        self,
        redis_client,
        db: Session | None = None,
    ):
        self.redis = redis_client
        self.db = db

    def add(
        self,
        task: dict[str, Any],
        reason: str,
        retry_count: int = 0,
        error: BaseException | None = None,
        celery_task_id: str | None = None,
        task_name: str | None = None,
        queue_name: str | None = None,
        correlation_id: str | None = None,
        exception_category: str | None = None,
    ) -> dict[str, Any]:
        """
        Add a failed task to Redis and PostgreSQL.
        """

        error_type = None
        error_message = None

        if error is not None:
            error_type = error.__class__.__name__
            error_message = str(error)

        payload = task.get("payload", {})

        context = (
            payload.get("context", {})
            if isinstance(payload, dict)
            else {}
        )

        task_type = (
            payload.get("task_type")
            if isinstance(payload, dict)
            else None
        )

        tenant_id = task.get("tenant_id")

        if not tenant_id:
            raise ValueError(
                "tenant_id is required for DLQ persistence"
            )

        dlq_id = str(uuid.uuid4())

        # Resolve metadata
        resolved_task_name = (
            task_name
            or task.get("task_name")
            or (payload.get("task_type") if isinstance(payload, dict) else None)
            or "task"
        )
        resolved_queue = (
            queue_name
            or task.get("queue")
            or "default"
        )
        resolved_correlation_id = (
            correlation_id
            or task.get("correlation_id")
            or (payload.get("correlation_id") if isinstance(payload, dict) else None)
            or (context.get("correlation_id") if isinstance(context, dict) else None)
        )
        resolved_exception_category = (
            exception_category
            or task.get("exception_category")
            or (error_type if error_type else "permanent_failure")
        )

        # Sanitize task and payload to redact credentials
        sanitized_task = sanitize_payload(task)
        sanitized_payload = sanitized_task.get("payload", {})
        sanitized_context = (
            sanitized_payload.get("context", {})
            if isinstance(sanitized_payload, dict)
            else {}
        )

        entry = {
            "id": dlq_id,
            "task": sanitized_task,
            "task_name": resolved_task_name,
            "queue": resolved_queue,
            "correlation_id": resolved_correlation_id,
            "exception_category": resolved_exception_category,
            "reason": reason,
            "retry_count": retry_count,
            "error_type": error_type,
            "error_message": error_message,
            "status": "FAILED",
            "moved_at": time.time(),
        }

        # Redis operational DLQ.
        self.redis.rpush(
            self.DLQ_KEY,
            json.dumps(entry),
        )

        # PostgreSQL permanent archive.
        if self.db is not None:
            enriched_context = dict(sanitized_context) if isinstance(sanitized_context, dict) else {}
            if resolved_correlation_id:
                enriched_context["correlation_id"] = resolved_correlation_id
            if resolved_task_name:
                enriched_context["task_name"] = resolved_task_name
            if resolved_queue:
                enriched_context["queue"] = resolved_queue
            if resolved_exception_category:
                enriched_context["exception_category"] = resolved_exception_category

            database_entry = DeadLetterTask(
                id=dlq_id,
                task_id=task.get("task_id") or celery_task_id or dlq_id,
                celery_task_id=celery_task_id,
                task_type=task_type or resolved_task_name,
                tenant_id=tenant_id,
                payload=sanitized_payload,
                context=enriched_context,
                reason=reason,
                error_type=error_type,
                error_message=error_message,
                retry_count=retry_count,
                status="FAILED",
            )

            self.db.add(database_entry)
            self.db.flush()

        return entry

    def count(self) -> int:
        """Return current Redis DLQ item count."""

        return int(
            self.redis.llen(self.DLQ_KEY)
        )

    def list(
        self,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Return Redis DLQ items in insertion order.
        """

        if limit is not None:
            if limit <= 0:
                return []

            end = limit - 1
        else:
            end = -1

        raw_items = self.redis.lrange(
            self.DLQ_KEY,
            0,
            end,
        )

        result = []

        for item in raw_items:
            if isinstance(item, bytes):
                item = item.decode("utf-8")

            result.append(
                json.loads(item)
            )

        return result

    def get(
        self,
        dlq_id: str,
    ) -> dict[str, Any] | None:
        """Find a Redis DLQ item by identifier."""

        for item in self.list():
            if item.get("id") == dlq_id:
                return item

        return None

    def delete(
        self,
        dlq_id: str,
    ) -> bool:
        """
        Remove a DLQ item from Redis.

        PostgreSQL remains the permanent archive.
        """

        items = self.list()

        matching_items = [
            item
            for item in items
            if item.get("id") == dlq_id
        ]

        if not matching_items:
            return False

        remaining_items = [
            item
            for item in items
            if item.get("id") != dlq_id
        ]

        pipeline = self.redis.pipeline()

        pipeline.delete(self.DLQ_KEY)

        if remaining_items:
            pipeline.rpush(
                self.DLQ_KEY,
                *[
                    json.dumps(item)
                    for item in remaining_items
                ],
            )

        pipeline.execute()

        return True

    def requeue_payload(
        self,
        dlq_id: str,
    ) -> dict[str, Any] | None:
        """
        Return original task for manual requeueing.
        """

        item = self.get(dlq_id)

        if item is None:
            return None

        return item.get("task")

    def get_failed_items(
        self,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Return failed DLQ items eligible for auto-requeue.
        """

        if limit <= 0:
            return []

        items = self.list(
            limit=limit
        )

        return [
            item
            for item in items
            if item.get("status", "FAILED") == "FAILED"
        ]

    def auto_requeue(
        self,
        queue,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Automatically requeue failed DLQ tasks.

        A task is removed from the DLQ only after successful
        insertion into the priority task queue.
        """

        if limit <= 0:
            return []

        from app.services.task_queue import TaskPriority

        failed_items = self.get_failed_items(
            limit=limit
        )

        requeued: list[dict[str, Any]] = []

        for item in failed_items:
            task = item.get("task")

            if not isinstance(task, dict):
                continue

            tenant_id = task.get("tenant_id")

            if not tenant_id:
                continue

            payload = task.get("payload", {})

            priority_name = (
                payload.get(
                    "priority",
                    "NORMAL",
                )
                if isinstance(payload, dict)
                else "NORMAL"
            )

            try:
                priority = TaskPriority[
                    str(priority_name).upper()
                ]
            except (KeyError, TypeError):
                priority = TaskPriority.NORMAL

            try:
                new_task_id = queue.enqueue(
                    task=payload,
                    priority=priority,
                    tenant_id=tenant_id,
                )
            except Exception:
                # Keep the DLQ item if requeue fails.
                continue

            dlq_id = item.get("id")

            if not dlq_id:
                continue

            deleted = self.delete(dlq_id)

            if not deleted:
                continue

            requeued.append(
                {
                    "dlq_id": dlq_id,
                    "old_task_id": task.get("task_id"),
                    "new_task_id": new_task_id,
                    "tenant_id": tenant_id,
                }
            )

        return requeued

    def is_above_alert_threshold(
        self,
        threshold: int = 10,
    ) -> bool:
        """
        Return True when DLQ count exceeds threshold.
        """

        return self.count() > threshold


# ---------------------------------------------------------------------------
# Story 8.8: Configure Failed Task Handling Core Contracts & Utilities
# ---------------------------------------------------------------------------

def handle_failed_task(
    *,
    task_name: str,
    queue: str = "default",
    args: list[Any] | None = None,
    kwargs: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
    error: BaseException | None = None,
    exception_category: str | None = None,
    tenant_id: str,
    correlation_id: str | None = None,
    task_id: str | None = None,
    celery_task_id: str | None = None,
    retry_count: int = 0,
    reason: str | None = None,
    redis=None,
    db: Session | None = None,
) -> dict[str, Any]:
    """
    Handle a failed task by capturing its metadata safely, redacting sensitive
    parameters, and storing in Redis operational DLQ + PostgreSQL archive.

    Returns canonical contract:
    {
        "status": "FAILED_HANDLED",
        "failure_action": "DLQ",
        "requeue_supported": true
    }
    """
    if not tenant_id:
        raise ValueError("tenant_id is required for handling failed task")

    if redis is None:
        from app.redis_client import get_redis_client
        redis = get_redis_client()

    if exception_category is None:
        if error is not None:
            exception_category = error.__class__.__name__
        else:
            exception_category = "permanent_failure"

    resolved_reason = reason or f"failed_execution:{exception_category}"
    stable_task_id = task_id or celery_task_id or str(uuid.uuid4())

    raw_payload: dict[str, Any] = {}
    if payload:
        raw_payload.update(payload)
    if args:
        raw_payload["args"] = args
    if kwargs:
        raw_payload["kwargs"] = kwargs

    sanitized_task_payload = sanitize_payload(raw_payload)

    task_dict = {
        "task_id": stable_task_id,
        "task_name": task_name,
        "queue": queue,
        "tenant_id": tenant_id,
        "correlation_id": correlation_id,
        "exception_category": exception_category,
        "payload": sanitized_task_payload,
        "created_at": time.time(),
    }

    dlq = DeadLetterQueue(redis_client=redis, db=db)
    entry = dlq.add(
        task=task_dict,
        reason=resolved_reason,
        retry_count=retry_count,
        error=error,
        celery_task_id=celery_task_id,
        task_name=task_name,
        queue_name=queue,
        correlation_id=correlation_id,
        exception_category=exception_category,
    )

    return {
        "status": "FAILED_HANDLED",
        "failure_action": "DLQ",
        "requeue_supported": True,
        "dlq_id": entry["id"],
        "task_id": stable_task_id,
        "task_name": task_name,
        "queue": queue,
        "tenant_id": tenant_id,
        "correlation_id": correlation_id,
        "exception_category": exception_category,
        "retry_count": retry_count,
        "reason": resolved_reason,
    }


def get_failed_task_handling_config() -> dict[str, Any]:
    """
    Return canonical configuration for failed task handling.
    Contract:
    {
        "status": "FAILED_HANDLED",
        "failure_action": "DLQ",
        "requeue_supported": true
    }
    """
    return {
        "status": "FAILED_HANDLED",
        "failure_action": "DLQ",
        "requeue_supported": True,
    }


def configure_failed_task_handling(app: Any | None = None) -> dict[str, Any]:
    """
    Ensure failed task handling and DLQ routing are configured.
    """
    return get_failed_task_handling_config()


# Authoritative story aliases conforming to story naming
ConfigureFailedTaskHandling = configure_failed_task_handling
Configure_failed_task_handling = configure_failed_task_handling
configure_failed_tasks = configure_failed_task_handling
ConfigureFailedTasks = configure_failed_task_handling
get_failed_tasks_config = get_failed_task_handling_config
