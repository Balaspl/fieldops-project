"""
celery_monitoring.py

Dedicated service module for Celery queue and worker operational monitoring.
Provides unified telemetry, queue depth tracking, worker health checks, failure/retry metrics,
latency recording, and abnormal backlog detection for FieldOps queue infrastructure.
"""

from __future__ import annotations

from typing import Any, Optional
from celery import Celery

from app.celery_app import (
    DEFAULT_CELERY_MONITORING,
    ALL_KNOWN_QUEUES,
    get_celery_monitoring_config,
    add_celery_monitoring,
    get_celery_queue_depth,
    get_all_queue_depths,
    record_task_failure,
    record_task_retry,
    record_task_latency,
    detect_abnormal_queue_growth,
    get_celery_worker_health,
    detect_stalled_workers,
    get_celery_monitoring_metrics,
    AddCeleryMonitoring,
    Add_celery_monitoring,
    configure_celery_monitoring,
    ConfigureCeleryMonitoring,
    get_celery_monitoring,
    GetCeleryMonitoring,
    celery_app,
)


class CeleryMonitoring:
    """Operational monitoring service for Celery queues and workers."""

    def __init__(self, app: Optional[Celery] = None, redis=None):
        self.app = app or celery_app
        self.redis = redis

    def get_config(self) -> dict[str, Any]:
        return get_celery_monitoring_config()

    def enable(self) -> dict[str, Any]:
        return add_celery_monitoring(app=self.app)

    def queue_depth(self, queue_name: str = "default") -> int:
        return get_celery_queue_depth(queue_name, redis=self.redis)

    def all_queue_depths(self) -> dict[str, int]:
        return get_all_queue_depths(redis=self.redis)

    def worker_health(self) -> dict[str, Any]:
        return get_celery_worker_health(app=self.app)

    def metrics(self) -> dict[str, Any]:
        return get_celery_monitoring_metrics(redis=self.redis, app=self.app)

    def record_failure(
        self,
        queue: str,
        task_id: str,
        error: Optional[Any] = None,
        tenant_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> dict[str, Any]:
        return record_task_failure(
            queue=queue,
            task_id=task_id,
            error=error,
            tenant_id=tenant_id,
            correlation_id=correlation_id,
            redis=self.redis,
        )

    def record_retry(
        self,
        queue: str,
        task_id: str,
        retry_count: int = 1,
        tenant_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> dict[str, Any]:
        return record_task_retry(
            queue=queue,
            task_id=task_id,
            retry_count=retry_count,
            tenant_id=tenant_id,
            correlation_id=correlation_id,
            redis=self.redis,
        )

    def record_latency(
        self,
        queue: str,
        task_id: str,
        latency_seconds: float = 0.0,
        tenant_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> dict[str, Any]:
        return record_task_latency(
            queue=queue,
            task_id=task_id,
            latency_seconds=latency_seconds,
            tenant_id=tenant_id,
            correlation_id=correlation_id,
            redis=self.redis,
        )

    def detect_growth(self, threshold: int = 100) -> dict[str, Any]:
        return detect_abnormal_queue_growth(threshold=threshold, redis=self.redis)


# Direct class aliases for service conformity
CeleryMonitoringService = CeleryMonitoring


__all__ = [
    "DEFAULT_CELERY_MONITORING",
    "ALL_KNOWN_QUEUES",
    "get_celery_monitoring_config",
    "add_celery_monitoring",
    "get_celery_queue_depth",
    "get_all_queue_depths",
    "record_task_failure",
    "record_task_retry",
    "record_task_latency",
    "detect_abnormal_queue_growth",
    "get_celery_worker_health",
    "detect_stalled_workers",
    "get_celery_monitoring_metrics",
    "AddCeleryMonitoring",
    "Add_celery_monitoring",
    "configure_celery_monitoring",
    "ConfigureCeleryMonitoring",
    "get_celery_monitoring",
    "GetCeleryMonitoring",
    "CeleryMonitoring",
    "CeleryMonitoringService",
]

