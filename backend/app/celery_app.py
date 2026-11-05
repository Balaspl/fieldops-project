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

ALL_TASK_ROUTES = {
    **NOTIFICATION_TASK_ROUTES,
    **GPS_TASK_ROUTES,
    **BILLING_TASK_ROUTES,
    **AI_TASK_ROUTES,
    **HIGH_PRIORITY_TASK_ROUTES,
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
