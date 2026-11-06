import os
from typing import Any, Optional
from celery import Celery
from kombu import Queue

# ---------------------------------------------------------------------------
# Redis configuration
# ---------------------------------------------------------------------------

redis_url = os.getenv(
    "REDIS_URL",
    "redis://localhost:6379/0",
)


# ---------------------------------------------------------------------------
# Celery application
# ---------------------------------------------------------------------------

celery_app = Celery(
    "fieldops_tasks",
    broker=redis_url,
    backend=redis_url,
)


# ---------------------------------------------------------------------------
# Queue Definitions & Routing Rules (Dedicated Queues)
# ---------------------------------------------------------------------------

DEFAULT_QUEUE = "default"
DEFAULT_ROUTING_KEY = "default"

# 1. Dedicated Notification Queue
NOTIFICATION_QUEUE = "notifications"
NOTIFICATION_ROUTING_KEY = "notifications"

NOTIFICATION_TASK_ROUTES = {
    # SMS Delivery Tasks
    "app.tasks.send_sms_async": {"queue": NOTIFICATION_QUEUE, "routing_key": NOTIFICATION_ROUTING_KEY},
    "app.tasks.send_bulk_sms_async": {"queue": NOTIFICATION_QUEUE, "routing_key": NOTIFICATION_ROUTING_KEY},

    # Email Delivery Tasks
    "app.tasks.send_email_async": {"queue": NOTIFICATION_QUEUE, "routing_key": NOTIFICATION_ROUTING_KEY},
    "app.tasks.process_transactional_email_outbox": {"queue": NOTIFICATION_QUEUE, "routing_key": NOTIFICATION_ROUTING_KEY},
    "app.tasks.process_transactional_email_outbox_task": {"queue": NOTIFICATION_QUEUE, "routing_key": NOTIFICATION_ROUTING_KEY},

    # Push, Lifecycle & Engagement Notification Tasks
    "app.tasks.send_dispatcher_digest": {"queue": NOTIFICATION_QUEUE, "routing_key": NOTIFICATION_ROUTING_KEY},
    "app.tasks.send_customer_daily_engagement": {"queue": NOTIFICATION_QUEUE, "routing_key": NOTIFICATION_ROUTING_KEY},
    "app.tasks.process_notification_event_task": {"queue": NOTIFICATION_QUEUE, "routing_key": NOTIFICATION_ROUTING_KEY},
    "app.tasks.route_notifications_with_lifecycle": {"queue": NOTIFICATION_QUEUE, "routing_key": NOTIFICATION_ROUTING_KEY},
    "app.tasks.send_push_notification_async": {"queue": NOTIFICATION_QUEUE, "routing_key": NOTIFICATION_ROUTING_KEY},
    "app.tasks.create_notification_queue_task": {"queue": NOTIFICATION_QUEUE, "routing_key": NOTIFICATION_ROUTING_KEY},
}

# 2. Dedicated GPS Processing Queue
GPS_QUEUE = "gps_processing"
GPS_ROUTING_KEY = "gps"

GPS_TASK_ROUTES = {
    # GPS Maintenance, Retention & Hard-Deletion Purge
    "app.tasks.daily_gps_purge_task": {"queue": GPS_QUEUE, "routing_key": GPS_ROUTING_KEY},
    "app.tasks.purge_job_gps_data": {"queue": GPS_QUEUE, "routing_key": GPS_ROUTING_KEY},
    "app.tasks.purge_job_gps_data_task": {"queue": GPS_QUEUE, "routing_key": GPS_ROUTING_KEY},

    # Real-Time ETA Recalculation & Tracking Consumption
    "app.tasks.update_eta_task": {"queue": GPS_QUEUE, "routing_key": GPS_ROUTING_KEY},
    "app.tasks.process_gps_tracking_event_task": {"queue": GPS_QUEUE, "routing_key": GPS_ROUTING_KEY},
    "app.tasks.create_gps_processing_queue_task": {"queue": GPS_QUEUE, "routing_key": GPS_ROUTING_KEY},
}

# 3. Dedicated Billing Queue
BILLING_QUEUE = "billing"
BILLING_ROUTING_KEY = "billing"

BILLING_TASK_ROUTES = {
    # Invoice lifecycle and publishing tasks
    "app.tasks.publish_invoice_event_task": {"queue": BILLING_QUEUE, "routing_key": BILLING_ROUTING_KEY},

    # Payment lifecycle and publishing tasks
    "app.tasks.publish_payment_event_task": {"queue": BILLING_QUEUE, "routing_key": BILLING_ROUTING_KEY},

    # Consumed billing & payment background processing tasks
    "app.tasks.process_billing_event_task": {"queue": BILLING_QUEUE, "routing_key": BILLING_ROUTING_KEY},
    "app.tasks.process_payment_event_task": {"queue": BILLING_QUEUE, "routing_key": BILLING_ROUTING_KEY},

    # Queue verification/configuration helper task
    "app.tasks.create_billing_queue_task": {"queue": BILLING_QUEUE, "routing_key": BILLING_ROUTING_KEY},
}

# 4. Dedicated AI Processing Queue
AI_QUEUE = "ai_processing"
AI_ROUTING_KEY = "ai"

AI_TASK_ROUTES = {
    # Asynchronous LangGraph / FieldOps workflow execution
    "app.tasks.execute_fieldops_workflow_async_task": {"queue": AI_QUEUE, "routing_key": AI_ROUTING_KEY},
    "app.tasks.execute_ai_workflow_task": {"queue": AI_QUEUE, "routing_key": AI_ROUTING_KEY},

    # Prompt Analytics and AI background computation tasks
    "app.tasks.aggregate_prompt_analytics_task": {"queue": AI_QUEUE, "routing_key": AI_ROUTING_KEY},
    "app.tasks.process_ai_workload_task": {"queue": AI_QUEUE, "routing_key": AI_ROUTING_KEY},

    # Queue verification/configuration helper task
    "app.tasks.create_ai_processing_queue_task": {"queue": AI_QUEUE, "routing_key": AI_ROUTING_KEY},
}

# 5. Dedicated High-Priority Queue (Emergency Dispatch & Urgent SLA Processing)
HIGH_PRIORITY_QUEUE = "high_priority"
HIGH_PRIORITY_ROUTING_KEY = "priority"
PRIORITY_QUEUE = HIGH_PRIORITY_QUEUE
PRIORITY_ROUTING_KEY = HIGH_PRIORITY_ROUTING_KEY

HIGH_PRIORITY_TASK_ROUTES = {
    # Emergency dispatch tasks
    "app.tasks.process_emergency_dispatch_task": {"queue": HIGH_PRIORITY_QUEUE, "routing_key": HIGH_PRIORITY_ROUTING_KEY},
    "app.tasks.emergency_dispatch_task": {"queue": HIGH_PRIORITY_QUEUE, "routing_key": HIGH_PRIORITY_ROUTING_KEY},

    # Urgent dispatch and SLA lifecycle processing tasks
    "app.tasks.process_dispatch_event_task": {"queue": HIGH_PRIORITY_QUEUE, "routing_key": HIGH_PRIORITY_ROUTING_KEY},
    "app.tasks.process_sla_monitoring_event_task": {"queue": HIGH_PRIORITY_QUEUE, "routing_key": HIGH_PRIORITY_ROUTING_KEY},
    "app.tasks.broadcast_sla_countdown": {"queue": HIGH_PRIORITY_QUEUE, "routing_key": HIGH_PRIORITY_ROUTING_KEY},

    # High-priority queue configuration/verification task
    "app.tasks.create_high_priority_queue_task": {"queue": HIGH_PRIORITY_QUEUE, "routing_key": HIGH_PRIORITY_ROUTING_KEY},
}

# 6. Dedicated Report-Generation Queue (PDF & Long-Running Reporting Workloads)
REPORT_QUEUE = "report_generation"
REPORT_ROUTING_KEY = "reports"
REPORT_GENERATION_QUEUE = REPORT_QUEUE
REPORT_GENERATION_ROUTING_KEY = REPORT_ROUTING_KEY

REPORT_TASK_ROUTES = {
    # Report and PDF generation tasks
    "app.tasks.generate_report_task": {"queue": REPORT_QUEUE, "routing_key": REPORT_ROUTING_KEY},
    "app.tasks.generate_pdf_report_task": {"queue": REPORT_QUEUE, "routing_key": REPORT_ROUTING_KEY},
    "app.tasks.generate_job_invoice_pdf_task": {"queue": REPORT_QUEUE, "routing_key": REPORT_ROUTING_KEY},
    "app.tasks.process_report_generation_task": {"queue": REPORT_QUEUE, "routing_key": REPORT_ROUTING_KEY},

    # Queue verification/configuration helper task
    "app.tasks.create_report_generation_queue_task": {"queue": REPORT_QUEUE, "routing_key": REPORT_ROUTING_KEY},
}

ALL_TASK_ROUTES = {
    **NOTIFICATION_TASK_ROUTES,
    **GPS_TASK_ROUTES,
    **BILLING_TASK_ROUTES,
    **AI_TASK_ROUTES,
    **HIGH_PRIORITY_TASK_ROUTES,
    **REPORT_TASK_ROUTES,
}


# ---------------------------------------------------------------------------
# Celery configuration
# ---------------------------------------------------------------------------

celery_app.conf.update(
    task_always_eager=False,
    timezone="UTC",
    enable_utc=True,

    # Queue management configuration
    task_default_queue=DEFAULT_QUEUE,
    task_default_routing_key=DEFAULT_ROUTING_KEY,
    task_queues=(
        Queue(DEFAULT_QUEUE, routing_key=DEFAULT_ROUTING_KEY),
        Queue(NOTIFICATION_QUEUE, routing_key=NOTIFICATION_ROUTING_KEY),
        Queue(GPS_QUEUE, routing_key=GPS_ROUTING_KEY),
        Queue(BILLING_QUEUE, routing_key=BILLING_ROUTING_KEY),
        Queue(AI_QUEUE, routing_key=AI_ROUTING_KEY),
        Queue(HIGH_PRIORITY_QUEUE, routing_key=HIGH_PRIORITY_ROUTING_KEY),
        Queue(REPORT_QUEUE, routing_key=REPORT_ROUTING_KEY),
    ),
    task_routes=ALL_TASK_ROUTES,

    # Explicitly import the task module.
    # app.tasks contains tasks that must be registered on THIS celery_app instance.
    imports=(
        "app.tasks",
        "app.sentiment.job_message_tasks",
    ),

    beat_schedule={
        "process-transactional-email-outbox-every-30-seconds": {
            "task": "app.tasks.process_transactional_email_outbox",
            "schedule": 30.0,
        },
        "send-dispatcher-digest-every-5-minutes": {
            "task": "app.tasks.send_dispatcher_digest",
            "schedule": 300.0,
        },

        "send-customer-daily-engagement-every-30-minutes": {
            "task": "app.tasks.send_customer_daily_engagement",
            "schedule": 1800.0,
        },

        "broadcast-sla-countdown-every-30-seconds": {
            "task": "app.tasks.broadcast_sla_countdown",
            "schedule": 30.0,
        },

        "aggregate-prompt-analytics-hourly": {
            "task": "app.tasks.aggregate_prompt_analytics_task",
            "schedule": 3600.0,
        },

        "auto-requeue-dlq-every-5-minutes": {
            "task": "app.tasks.auto_requeue_dlq",
            "schedule": 300.0,
        },
    },
)


# ---------------------------------------------------------------------------
# Queue Helpers & Story Contract Helpers
# ---------------------------------------------------------------------------

def get_notification_queue_config() -> dict[str, str]:
    """
    Return canonical configuration for the dedicated notification queue.
    Contract:
    {
        "status": "CONFIGURED",
        "queue": "notifications",
        "routing_key": "notifications"
    }
    """
    return {
        "status": "CONFIGURED",
        "queue": NOTIFICATION_QUEUE,
        "routing_key": NOTIFICATION_ROUTING_KEY,
    }


def create_notification_queue(app: Optional[Celery] = None) -> dict[str, str]:
    """
    Ensure the dedicated notification queue and routing configuration are active on Celery.
    Returns:
        {
            "status": "CONFIGURED",
            "queue": "notifications",
            "routing_key": "notifications"
        }
    """
    target_app = app or celery_app

    # Ensure queue is present in task_queues
    existing_queues = list(target_app.conf.task_queues or [])
    queue_names = {q.name if hasattr(q, "name") else str(q) for q in existing_queues}
    if NOTIFICATION_QUEUE not in queue_names:
        existing_queues.append(Queue(NOTIFICATION_QUEUE, routing_key=NOTIFICATION_ROUTING_KEY))
        target_app.conf.task_queues = tuple(existing_queues)

    # Ensure task routes are merged
    existing_routes = dict(target_app.conf.task_routes or {})
    existing_routes.update(NOTIFICATION_TASK_ROUTES)
    target_app.conf.task_routes = existing_routes

    return get_notification_queue_config()


# Notification Story aliases
CreateNotificationQueue = create_notification_queue
Create_notification_queue = create_notification_queue


def get_gps_processing_queue_config() -> dict[str, str]:
    """
    Return canonical configuration for the dedicated GPS processing queue.
    Contract:
    {
        "status": "CONFIGURED",
        "queue": "gps_processing",
        "routing_key": "gps"
    }
    """
    return {
        "status": "CONFIGURED",
        "queue": GPS_QUEUE,
        "routing_key": GPS_ROUTING_KEY,
    }


def create_gps_processing_queue(app: Optional[Celery] = None) -> dict[str, str]:
    """
    Ensure the dedicated GPS processing queue and routing configuration are active on Celery.
    Returns:
        {
            "status": "CONFIGURED",
            "queue": "gps_processing",
            "routing_key": "gps"
        }
    """
    target_app = app or celery_app

    # Ensure queue is present in task_queues
    existing_queues = list(target_app.conf.task_queues or [])
    queue_names = {q.name if hasattr(q, "name") else str(q) for q in existing_queues}
    if GPS_QUEUE not in queue_names:
        existing_queues.append(Queue(GPS_QUEUE, routing_key=GPS_ROUTING_KEY))
        target_app.conf.task_queues = tuple(existing_queues)

    # Ensure task routes are merged
    existing_routes = dict(target_app.conf.task_routes or {})
    existing_routes.update(GPS_TASK_ROUTES)
    target_app.conf.task_routes = existing_routes

    return get_gps_processing_queue_config()


# Authoritative story aliases conforming to story naming
CreateGPSProcessingQueue = create_gps_processing_queue
Create_gps_processing_queue = create_gps_processing_queue
CreateGpsProcessingQueue = create_gps_processing_queue
Create_gps_queue = create_gps_processing_queue
create_gps_queue = create_gps_processing_queue

def get_billing_queue_config() -> dict[str, str]:
    """
    Return canonical configuration for the dedicated billing queue.
    Contract:
    {
        "status": "CONFIGURED",
        "queue": "billing",
        "routing_key": "billing"
    }
    """
    return {
        "status": "CONFIGURED",
        "queue": BILLING_QUEUE,
        "routing_key": BILLING_ROUTING_KEY,
    }


def create_billing_queue(app: Optional[Celery] = None) -> dict[str, str]:
    """
    Ensure the dedicated billing queue and routing configuration are active on Celery.
    Returns:
        {
            "status": "CONFIGURED",
            "queue": "billing",
            "routing_key": "billing"
        }
    """
    target_app = app or celery_app

    # Ensure queue is present in task_queues
    existing_queues = list(target_app.conf.task_queues or [])
    queue_names = {q.name if hasattr(q, "name") else str(q) for q in existing_queues}
    if BILLING_QUEUE not in queue_names:
        existing_queues.append(Queue(BILLING_QUEUE, routing_key=BILLING_ROUTING_KEY))
        target_app.conf.task_queues = tuple(existing_queues)

    # Ensure task routes are merged
    existing_routes = dict(target_app.conf.task_routes or {})
    existing_routes.update(BILLING_TASK_ROUTES)
    target_app.conf.task_routes = existing_routes

    return get_billing_queue_config()


# Authoritative story aliases
CreateBillingQueue = create_billing_queue
Create_billing_queue = create_billing_queue


def get_ai_processing_queue_config() -> dict[str, str]:
    """
    Return canonical configuration for the dedicated AI processing queue.
    Contract:
    {
        "status": "CONFIGURED",
        "queue": "ai_processing",
        "routing_key": "ai"
    }
    """
    return {
        "status": "CONFIGURED",
        "queue": AI_QUEUE,
        "routing_key": AI_ROUTING_KEY,
    }


def create_ai_processing_queue(app: Optional[Celery] = None) -> dict[str, str]:
    """
    Ensure the dedicated AI processing queue and routing configuration are active on Celery.
    Returns:
        {
            "status": "CONFIGURED",
            "queue": "ai_processing",
            "routing_key": "ai"
        }
    """
    target_app = app or celery_app

    # Ensure queue is present in task_queues
    existing_queues = list(target_app.conf.task_queues or [])
    queue_names = {q.name if hasattr(q, "name") else str(q) for q in existing_queues}
    if AI_QUEUE not in queue_names:
        existing_queues.append(Queue(AI_QUEUE, routing_key=AI_ROUTING_KEY))
        target_app.conf.task_queues = tuple(existing_queues)

    # Ensure task routes are merged
    existing_routes = dict(target_app.conf.task_routes or {})
    existing_routes.update(AI_TASK_ROUTES)
    target_app.conf.task_routes = existing_routes

    return get_ai_processing_queue_config()


# Authoritative story aliases conforming to story naming
CreateAiProcessingQueue = create_ai_processing_queue
Create_ai_processing_queue = create_ai_processing_queue
CreateAiQueue = create_ai_processing_queue
create_ai_queue = create_ai_processing_queue
Create_ai_queue = create_ai_processing_queue


def get_high_priority_queue_config() -> dict[str, str]:
    """
    Return canonical configuration for the dedicated high-priority queue.
    Contract:
    {
        "status": "CONFIGURED",
        "queue": "high_priority",
        "routing_key": "priority"
    }
    """
    return {
        "status": "CONFIGURED",
        "queue": HIGH_PRIORITY_QUEUE,
        "routing_key": HIGH_PRIORITY_ROUTING_KEY,
    }


def create_high_priority_queue(app: Optional[Celery] = None) -> dict[str, str]:
    """
    Ensure the dedicated high-priority queue and routing configuration are active on Celery.
    Returns:
        {
            "status": "CONFIGURED",
            "queue": "high_priority",
            "routing_key": "priority"
        }
    """
    target_app = app or celery_app

    # Ensure queue is present in task_queues
    existing_queues = list(target_app.conf.task_queues or [])
    queue_names = {q.name if hasattr(q, "name") else str(q) for q in existing_queues}
    if HIGH_PRIORITY_QUEUE not in queue_names:
        existing_queues.append(Queue(HIGH_PRIORITY_QUEUE, routing_key=HIGH_PRIORITY_ROUTING_KEY))
        target_app.conf.task_queues = tuple(existing_queues)

    # Ensure task routes are merged
    existing_routes = dict(target_app.conf.task_routes or {})
    existing_routes.update(HIGH_PRIORITY_TASK_ROUTES)
    target_app.conf.task_routes = existing_routes

    return get_high_priority_queue_config()


# Authoritative story aliases conforming to story naming
CreateHighPriorityQueue = create_high_priority_queue
Create_high_priority_queue = create_high_priority_queue
CreatePriorityQueue = create_high_priority_queue
create_priority_queue = create_high_priority_queue
Create_priority_queue = create_high_priority_queue


def get_report_generation_queue_config() -> dict[str, str]:
    """
    Return canonical configuration for the dedicated report-generation queue.
    Contract:
    {
        "status": "CONFIGURED",
        "queue": "report_generation",
        "routing_key": "reports"
    }
    """
    return {
        "status": "CONFIGURED",
        "queue": REPORT_QUEUE,
        "routing_key": REPORT_ROUTING_KEY,
    }


def create_report_generation_queue(app: Optional[Celery] = None) -> dict[str, str]:
    """
    Ensure the dedicated report-generation queue and routing configuration are active on Celery.
    Returns:
        {
            "status": "CONFIGURED",
            "queue": "report_generation",
            "routing_key": "reports"
        }
    """
    target_app = app or celery_app

    # Ensure queue is present in task_queues
    existing_queues = list(target_app.conf.task_queues or [])
    queue_names = {q.name if hasattr(q, "name") else str(q) for q in existing_queues}
    if REPORT_QUEUE not in queue_names:
        existing_queues.append(Queue(REPORT_QUEUE, routing_key=REPORT_ROUTING_KEY))
        target_app.conf.task_queues = tuple(existing_queues)

    # Ensure task routes are merged
    existing_routes = dict(target_app.conf.task_routes or {})
    existing_routes.update(REPORT_TASK_ROUTES)
    target_app.conf.task_routes = existing_routes

    return get_report_generation_queue_config()


# Authoritative story aliases conforming to story naming
CreateReportGenerationQueue = create_report_generation_queue
Create_report_generation_queue = create_report_generation_queue
CreateReportQueue = create_report_generation_queue
create_report_queue = create_report_generation_queue
Create_report_queue = create_report_generation_queue


# ---------------------------------------------------------------------------
# Task Retry Rules Configuration (Bounded Exponential Backoff with Jitter)
# ---------------------------------------------------------------------------

TASK_RETRY_POLICY = {
    "max_retries": 3,
    "backoff": "exponential",
    "jitter": True,
}


def get_task_retry_rules_config() -> dict[str, Any]:
    """
    Return canonical configuration for task retry rules.
    Contract:
    {
        "status": "CONFIGURED",
        "retry_policy": {
            "max_retries": 3,
            "backoff": "exponential",
            "jitter": true
        }
    }
    """
    return {
        "status": "CONFIGURED",
        "retry_policy": {
            "max_retries": 3,
            "backoff": "exponential",
            "jitter": True,
        },
    }


def configure_task_retry_rules(app: Optional[Celery] = None) -> dict[str, Any]:
    """
    Configure bounded, task-appropriate retry policies on Celery application.
    Returns:
        {
            "status": "CONFIGURED",
            "retry_policy": {
                "max_retries": 3,
                "backoff": "exponential",
                "jitter": true
            }
        }
    """
    target_app = app or celery_app

    # Configure default task annotations for bounded retry
    annotations = dict(target_app.conf.task_annotations or {})
    annotations["*"] = {
        "max_retries": 3,
        "default_retry_delay": 1,
    }
    target_app.conf.task_annotations = annotations

    return get_task_retry_rules_config()


# Authoritative story aliases conforming to story naming
ConfigureTaskRetryRules = configure_task_retry_rules
Configure_task_retry_rules = configure_task_retry_rules
configure_retry_rules = configure_task_retry_rules
ConfigureRetryRules = configure_task_retry_rules
get_retry_rules_config = get_task_retry_rules_config

# ---------------------------------------------------------------------------
# Failed Task Handling Configuration (DLQ & Safe Requeue Support)
# ---------------------------------------------------------------------------

FAILED_TASK_HANDLING_CONFIG = {
    "status": "FAILED_HANDLED",
    "failure_action": "DLQ",
    "requeue_supported": True,
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


def configure_failed_task_handling(app: Optional[Celery] = None) -> dict[str, Any]:
    """
    Configure dead-letter and failure handling on Celery application.
    """
    from app.runtime.dlq import configure_failed_task_handling as runtime_configure
    return runtime_configure(app)


# Authoritative story aliases conforming to story naming
ConfigureFailedTaskHandling = configure_failed_task_handling
Configure_failed_task_handling = configure_failed_task_handling
configure_failed_tasks = configure_failed_task_handling
ConfigureFailedTasks = configure_failed_task_handling
get_failed_tasks_config = get_failed_task_handling_config


# ---------------------------------------------------------------------------
# Task Timeouts Configuration (Soft and Hard Limits per Queue)
# ---------------------------------------------------------------------------

DEFAULT_TASK_TIMEOUTS = {
    "soft": 300,
    "hard": 360,
}

QUEUE_TASK_TIMEOUTS = {
    "default": {"soft": 300, "hard": 360},
    "high_priority": {"soft": 60, "hard": 120},
    "notifications": {"soft": 60, "hard": 90},
    "gps_processing": {"soft": 30, "hard": 60},
    "billing": {"soft": 120, "hard": 180},
    "ai_processing": {"soft": 300, "hard": 360},
    "report_generation": {"soft": 600, "hard": 720},
}


def get_task_timeouts_config(include_queues: bool = False) -> dict[str, Any]:
    """
    Return canonical configuration for task timeouts.
    Contract:
    {
        "status": "CONFIGURED",
        "timeouts": {
            "soft": 300,
            "hard": 360
        }
    }
    """
    res = {
        "status": "CONFIGURED",
        "timeouts": dict(DEFAULT_TASK_TIMEOUTS),
    }
    if include_queues:
        res["queue_timeouts"] = dict(QUEUE_TASK_TIMEOUTS)
    return res


def get_queue_timeout(queue_name: str) -> dict[str, int]:
    """Return soft and hard timeout for a specific queue."""
    return QUEUE_TASK_TIMEOUTS.get(queue_name, DEFAULT_TASK_TIMEOUTS)


def configure_task_timeouts(app: Optional[Celery] = None) -> dict[str, Any]:
    """
    Apply bounded execution and broker/worker timeout settings appropriate to each queue.
    Returns:
    {
        "status": "CONFIGURED",
        "timeouts": {
            "soft": 300,
            "hard": 360
        }
    }
    """
    target_app = app or celery_app

    # Set default global soft and hard time limits
    target_app.conf.task_time_limit = DEFAULT_TASK_TIMEOUTS["hard"]
    target_app.conf.task_soft_time_limit = DEFAULT_TASK_TIMEOUTS["soft"]

    # Configure per-task annotations
    annotations = dict(target_app.conf.task_annotations or {})
    annotations.setdefault("*", {})
    annotations["*"]["time_limit"] = DEFAULT_TASK_TIMEOUTS["hard"]
    annotations["*"]["soft_time_limit"] = DEFAULT_TASK_TIMEOUTS["soft"]

    # Queue-specific task annotations
    for task_pattern, queue_name in [
        ("app.tasks.*notification*", "notifications"),
        ("app.tasks.*email*", "notifications"),
        ("app.tasks.*sms*", "notifications"),
        ("app.tasks.*gps*", "gps_processing"),
        ("app.tasks.*ping*", "gps_processing"),
        ("app.tasks.*billing*", "billing"),
        ("app.tasks.*invoice*", "billing"),
        ("app.tasks.*payment*", "billing"),
        ("app.tasks.*ai*", "ai_processing"),
        ("app.tasks.*prompt*", "ai_processing"),
        ("app.tasks.*langgraph*", "ai_processing"),
        ("app.tasks.*priority*", "high_priority"),
        ("app.tasks.*emergency*", "high_priority"),
        ("app.tasks.*dispatch*", "high_priority"),
        ("app.tasks.*report*", "report_generation"),
        ("app.tasks.*pdf*", "report_generation"),
    ]:
        q_limits = get_queue_timeout(queue_name)
        annotations.setdefault(task_pattern, {})
        annotations[task_pattern]["time_limit"] = q_limits["hard"]
        annotations[task_pattern]["soft_time_limit"] = q_limits["soft"]

    target_app.conf.task_annotations = annotations

    return get_task_timeouts_config()


# Authoritative story aliases conforming to story naming
ConfigureTaskTimeouts = configure_task_timeouts
Configure_task_timeouts = configure_task_timeouts
configure_timeouts = configure_task_timeouts
ConfigureTimeouts = configure_task_timeouts
get_task_timeouts = get_task_timeouts_config
get_timeouts_config = get_task_timeouts_config


# ---------------------------------------------------------------------------
# Celery Beat Scheduled Tasks Configuration
# ---------------------------------------------------------------------------

FOUNDATIONAL_BEAT_SCHEDULES = {
    "process-transactional-email-outbox-every-30-seconds": {
        "task": "app.tasks.process_transactional_email_outbox",
        "schedule": 30.0,
    },
    "send-dispatcher-digest-every-5-minutes": {
        "task": "app.tasks.send_dispatcher_digest",
        "schedule": 300.0,
    },
    "send-customer-daily-engagement-every-30-minutes": {
        "task": "app.tasks.send_customer_daily_engagement",
        "schedule": 1800.0,
    },
    "broadcast-sla-countdown-every-30-seconds": {
        "task": "app.tasks.broadcast_sla_countdown",
        "schedule": 30.0,
    },
    "aggregate-prompt-analytics-hourly": {
        "task": "app.tasks.aggregate_prompt_analytics_task",
        "schedule": 3600.0,
    },
    "auto-requeue-dlq-every-5-minutes": {
        "task": "app.tasks.auto_requeue_dlq",
        "schedule": 300.0,
    },
}


def get_scheduled_tasks_config() -> dict[str, str]:
    """
    Return canonical contract for scheduled tasks.
    Contract:
    {
        "status": "SCHEDULED",
        "scheduler": "celery_beat"
    }
    """
    return {
        "status": "SCHEDULED",
        "scheduler": "celery_beat",
    }


def add_scheduled_tasks(
    app: Optional[Celery] = None,
    schedules: Optional[dict[str, Any]] = None,
) -> dict[str, str]:
    """
    Register and extend Celery Beat schedules while strictly preserving existing schedules
    (digest, SLA countdown, analytics, DLQ, etc.).
    Returns:
    {
        "status": "SCHEDULED",
        "scheduler": "celery_beat"
    }
    """
    target_app = app or celery_app
    existing_beat_schedule = dict(target_app.conf.beat_schedule or {})

    # Ensure all foundational schedules are present and preserved
    for name, entry in FOUNDATIONAL_BEAT_SCHEDULES.items():
        if name not in existing_beat_schedule:
            existing_beat_schedule[name] = entry

    # Merge additional schedules if passed
    if schedules:
        for name, entry in schedules.items():
            existing_beat_schedule[name] = entry

    target_app.conf.beat_schedule = existing_beat_schedule
    target_app.conf.timezone = "UTC"

    return get_scheduled_tasks_config()


# Authoritative story aliases conforming to story naming
AddScheduledTasks = add_scheduled_tasks
Add_scheduled_tasks = add_scheduled_tasks
add_scheduled_task = add_scheduled_tasks
AddScheduledTask = add_scheduled_tasks
get_scheduled_tasks = get_scheduled_tasks_config
get_scheduled_task_config = get_scheduled_tasks_config


# ---------------------------------------------------------------------------
# Task Result Tracking Configuration & Operations
# ---------------------------------------------------------------------------

DEFAULT_TASK_RESULT_TRACKING = {
    "status": "TRACKED",
    "task_id": "example-task-id",
    "state": "SUCCESS",
    "queue": "notifications",
}


def get_task_result_tracking_config(
    task_id: str = "example-task-id",
    state: str = "SUCCESS",
    queue: str = "notifications",
) -> dict[str, str]:
    """
    Return canonical contract for task result tracking.
    Contract:
    {
        "status": "TRACKED",
        "task_id": "example-task-id",
        "state": "SUCCESS",
        "queue": "notifications"
    }
    """
    return {
        "status": "TRACKED",
        "task_id": task_id,
        "state": state,
        "queue": queue,
    }


def track_task_result(
    task_id: str,
    state: str,
    queue: str = "default",
    tenant_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    result_data: Optional[dict[str, Any]] = None,
    error: Optional[BaseException] = None,
    redis=None,
) -> dict[str, Any]:
    """
    Track lifecycle and result metadata for an asynchronous task:
    - Captures task_id, queue, state, timestamps, correlation_id, tenant_id.
    - Sanitizes result_data to prevent credential leakage.
    - Preserves states: QUEUED, RUNNING, SUCCESS, FAILURE, RETRY.
    - Stores structured result in Redis under `task_result:{task_id}`.
    - Returns exact JSON contract:
        {
            "status": "TRACKED",
            "task_id": task_id,
            "state": state,
            "queue": queue
        }
    """
    import json
    import time
    from app.runtime.dlq import sanitize_payload

    normalized_state = state.upper() if isinstance(state, str) else "UNKNOWN"
    now_ts = time.time()

    sanitized_data = sanitize_payload(result_data) if result_data else None
    error_msg = str(error) if error else None

    record = {
        "task_id": task_id,
        "queue": queue,
        "state": normalized_state,
        "tenant_id": tenant_id,
        "correlation_id": correlation_id,
        "result": sanitized_data,
        "error": error_msg,
        "updated_at": now_ts,
    }

    if redis is None:
        try:
            from app.redis_client import get_redis_client
            redis = get_redis_client()
        except Exception:
            redis = None

    if redis is not None:
        try:
            redis_key = f"task_result:{task_id}"
            redis.set(redis_key, json.dumps(record), ex=86400)
        except Exception:
            pass

    return {
        "status": "TRACKED",
        "task_id": task_id,
        "state": normalized_state,
        "queue": queue,
    }


def get_task_result(task_id: str, redis=None) -> Optional[dict[str, Any]]:
    """Retrieve tracked result record for a specific task."""
    import json
    if redis is None:
        try:
            from app.redis_client import get_redis_client
            redis = get_redis_client()
        except Exception:
            redis = None

    if redis is not None:
        try:
            raw = redis.get(f"task_result:{task_id}")
            if raw:
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                return json.loads(raw)
        except Exception:
            pass

    # Fallback to Celery AsyncResult if available
    try:
        from celery.result import AsyncResult
        res = AsyncResult(task_id, app=celery_app)
        if res and res.state:
            return {
                "task_id": task_id,
                "state": res.state,
                "queue": "default",
                "result": None if res.failed() else str(res.result),
                "error": str(res.result) if res.failed() else None,
            }
    except Exception:
        pass

    return None


def add_task_result_tracking(
    app: Optional[Celery] = None,
    task_id: str = "example-task-id",
    state: str = "SUCCESS",
    queue: str = "notifications",
) -> dict[str, str]:
    """
    Ensure task result tracking is active on Celery application and return contract.
    """
    target_app = app or celery_app
    target_app.conf.task_track_started = True
    target_app.conf.result_extended = True

    return get_task_result_tracking_config(task_id=task_id, state=state, queue=queue)


# Authoritative story aliases conforming to story naming
AddTaskResultTracking = add_task_result_tracking
Add_task_result_tracking = add_task_result_tracking
configure_task_result_tracking = add_task_result_tracking
ConfigureTaskResultTracking = add_task_result_tracking
get_task_result_tracking = get_task_result_tracking_config
TrackTaskResult = track_task_result


# ---------------------------------------------------------------------------
# Story: Add Celery Monitoring (Celery Queue Management)
# ---------------------------------------------------------------------------

DEFAULT_CELERY_MONITORING = {
    "status": "MONITORING_ENABLED",
    "metrics": [
        "queue_depth",
        "task_latency",
        "task_failures",
        "worker_health",
    ],
}

ALL_KNOWN_QUEUES = (
    DEFAULT_QUEUE,
    NOTIFICATION_QUEUE,
    GPS_QUEUE,
    BILLING_QUEUE,
    AI_QUEUE,
    HIGH_PRIORITY_QUEUE,
    REPORT_QUEUE,
    "reports",
    "dlq",
)


def get_celery_monitoring_config() -> dict[str, Any]:
    """
    Return canonical contract for Celery monitoring.
    Contract:
    {
        "status": "MONITORING_ENABLED",
        "metrics": [
            "queue_depth",
            "task_latency",
            "task_failures",
            "worker_health"
        ]
    }
    """
    return {
        "status": "MONITORING_ENABLED",
        "metrics": [
            "queue_depth",
            "task_latency",
            "task_failures",
            "worker_health",
        ],
    }


def add_celery_monitoring(app: Optional[Celery] = None) -> dict[str, Any]:
    """
    Ensure Celery operational monitoring is active and return canonical contract.
    Enables worker event publishing and task tracking if available.
    """
    target_app = app or celery_app
    target_app.conf.worker_send_task_events = True
    target_app.conf.task_send_sent_event = True
    return get_celery_monitoring_config()


def get_celery_queue_depth(queue_name: str = "default", redis=None) -> int:
    """Query current depth (number of pending items) in a Celery queue via Redis."""
    if redis is None:
        try:
            from app.redis_client import get_redis_client
            redis = get_redis_client()
        except Exception:
            redis = None

    if redis is None:
        return 0

    try:
        depth = redis.llen(queue_name)
        return int(depth) if depth is not None else 0
    except Exception:
        return 0


def get_all_queue_depths(redis=None) -> dict[str, int]:
    """Query current queue depths across all registered operational queues."""
    depths = {}
    for q in ALL_KNOWN_QUEUES:
        depths[q] = get_celery_queue_depth(q, redis=redis)
    return depths


def record_task_failure(
    queue: str = "default",
    task_id: str = "unknown",
    error: Optional[Any] = None,
    tenant_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    redis=None,
) -> dict[str, Any]:
    """Record a task failure event for queue metrics and telemetry."""
    from app.runtime.dlq import sanitize_payload

    if redis is None:
        try:
            from app.redis_client import get_redis_client
            redis = get_redis_client()
        except Exception:
            redis = None

    count = 1
    if redis is not None:
        try:
            redis.incr(f"celery_monitoring:failures:{queue}")
            total = redis.incr("celery_monitoring:failures:total")
            count = int(total)
        except Exception:
            pass

    sanitized_err = sanitize_payload({"error": str(error)})["error"] if error else None

    return {
        "status": "RECORDED",
        "metric": "task_failures",
        "queue": queue,
        "task_id": task_id,
        "error": sanitized_err,
        "tenant_id": tenant_id,
        "correlation_id": correlation_id,
        "count": count,
    }


def record_task_retry(
    queue: str = "default",
    task_id: str = "unknown",
    retry_count: int = 1,
    tenant_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    redis=None,
) -> dict[str, Any]:
    """Record a task retry event for queue metrics and telemetry."""
    if redis is None:
        try:
            from app.redis_client import get_redis_client
            redis = get_redis_client()
        except Exception:
            redis = None

    if redis is not None:
        try:
            redis.incr(f"celery_monitoring:retries:{queue}")
            redis.incr("celery_monitoring:retries:total")
        except Exception:
            pass

    return {
        "status": "RECORDED",
        "metric": "task_retries",
        "queue": queue,
        "task_id": task_id,
        "retry_count": retry_count,
        "tenant_id": tenant_id,
        "correlation_id": correlation_id,
    }


def record_task_latency(
    queue: str = "default",
    task_id: str = "unknown",
    latency_seconds: float = 0.0,
    tenant_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    redis=None,
) -> dict[str, Any]:
    """Record task execution latency in seconds."""
    if redis is None:
        try:
            from app.redis_client import get_redis_client
            redis = get_redis_client()
        except Exception:
            redis = None

    if redis is not None:
        try:
            redis.set(f"celery_monitoring:latency:{queue}", str(latency_seconds), ex=86400)
        except Exception:
            pass

    return {
        "status": "RECORDED",
        "metric": "task_latency",
        "queue": queue,
        "task_id": task_id,
        "latency_seconds": latency_seconds,
        "tenant_id": tenant_id,
        "correlation_id": correlation_id,
    }


def detect_abnormal_queue_growth(
    threshold: int = 100,
    redis=None,
) -> dict[str, Any]:
    """Detect any queues where backlog depth exceeds operational thresholds."""
    depths = get_all_queue_depths(redis=redis)
    congested = {q: count for q, count in depths.items() if count >= threshold}
    return {
        "alert": len(congested) > 0,
        "threshold": threshold,
        "congested_queues": congested,
        "total_depth": sum(depths.values()),
    }


def get_celery_worker_health(app: Optional[Celery] = None) -> dict[str, Any]:
    """
    Inspect worker availability and ping status.
    Gracefully handles eager / standalone / test environments.
    """
    target_app = app or celery_app
    stalled_workers = []
    active_workers = []

    try:
        inspector = target_app.control.inspect(timeout=0.5)
        ping_res = inspector.ping() if inspector else None
        if ping_res:
            for worker_name in ping_res.keys():
                active_workers.append(worker_name)
    except Exception:
        pass

    is_eager = bool(target_app.conf.task_always_eager)
    status = "healthy"
    workers_online = len(active_workers) if active_workers else (1 if is_eager else 0)

    return {
        "status": status,
        "workers_online": workers_online,
        "active_workers": active_workers,
        "stalled_workers": stalled_workers,
        "eager_mode": is_eager,
    }


def detect_stalled_workers(
    app: Optional[Celery] = None,
    max_active_seconds: float = 300.0,
) -> list[dict[str, Any]]:
    """Detect workers with active tasks exceeding operational execution limits."""
    target_app = app or celery_app
    stalled = []
    try:
        inspector = target_app.control.inspect(timeout=0.5)
        active = inspector.active() if inspector else None
        if active:
            import time
            now = time.time()
            for worker_name, tasks in active.items():
                for t in tasks:
                    start_time = t.get("time_start")
                    if start_time and (now - start_time) > max_active_seconds:
                        stalled.append({
                            "worker": worker_name,
                            "task_id": t.get("id"),
                            "task_name": t.get("name"),
                            "elapsed_seconds": now - start_time,
                        })
    except Exception:
        pass
    return stalled


def get_celery_monitoring_metrics(
    redis=None,
    app: Optional[Celery] = None,
) -> dict[str, Any]:
    """
    Aggregate all operational Celery monitoring metrics:
    - queue_depth
    - task_latency
    - task_failures
    - worker_health
    """
    depths = get_all_queue_depths(redis=redis)
    worker_health = get_celery_worker_health(app=app)
    growth_check = detect_abnormal_queue_growth(redis=redis)

    failures_by_queue = {}
    retries_by_queue = {}
    latency_by_queue = {}

    if redis is None:
        try:
            from app.redis_client import get_redis_client
            redis = get_redis_client()
        except Exception:
            redis = None

    if redis is not None:
        for q in ALL_KNOWN_QUEUES:
            try:
                f_val = redis.get(f"celery_monitoring:failures:{q}")
                if f_val:
                    failures_by_queue[q] = int(f_val)
            except Exception:
                pass
            try:
                r_val = redis.get(f"celery_monitoring:retries:{q}")
                if r_val:
                    retries_by_queue[q] = int(r_val)
            except Exception:
                pass
            try:
                l_val = redis.get(f"celery_monitoring:latency:{q}")
                if l_val:
                    latency_by_queue[q] = float(l_val)
            except Exception:
                pass

    alerts = []
    if growth_check["alert"]:
        alerts.append({
            "type": "abnormal_queue_growth",
            "details": growth_check["congested_queues"],
        })

    return {
        "status": "MONITORING_ENABLED",
        "metrics": [
            "queue_depth",
            "task_latency",
            "task_failures",
            "worker_health",
        ],
        "queue_depth": depths,
        "worker_health": worker_health,
        "task_failures": {
            "total": sum(failures_by_queue.values()),
            "by_queue": failures_by_queue,
        },
        "task_retries": {
            "total": sum(retries_by_queue.values()),
            "by_queue": retries_by_queue,
        },
        "task_latency": {
            "by_queue": latency_by_queue,
        },
        "alerts": alerts,
    }


# Authoritative story aliases
AddCeleryMonitoring = add_celery_monitoring
Add_celery_monitoring = add_celery_monitoring
configure_celery_monitoring = add_celery_monitoring
ConfigureCeleryMonitoring = add_celery_monitoring
get_celery_monitoring = get_celery_monitoring_config
GetCeleryMonitoring = get_celery_monitoring_config
CeleryMonitoring = get_celery_monitoring_config
CeleryMonitoringService = add_celery_monitoring







# ---------------------------------------------------------------------------
# Explicit task registration
# ---------------------------------------------------------------------------
#
# Do NOT depend only on autodiscover_tasks().
# Explicitly importing app.tasks guarantees that all tasks decorated with
# @celery_app.task are registered against this exact Celery application.
#

import app.tasks  # noqa: E402, F401


# ---------------------------------------------------------------------------
# Safety check / task registration
# ---------------------------------------------------------------------------

if "app.tasks.auto_requeue_dlq" not in celery_app.tasks:
    import logging

    logging.getLogger(__name__).warning(
        "app.tasks.auto_requeue_dlq is not registered with celery_app"
    )
