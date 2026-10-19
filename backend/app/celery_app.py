import os

from celery import Celery


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
# Celery configuration
# ---------------------------------------------------------------------------

celery_app.conf.update(
    task_always_eager=False,
    timezone="UTC",
    enable_utc=True,

    # Explicitly import the task module.
    #
    # This is important because app.tasks contains tasks that must be
    # registered on THIS celery_app instance.
    imports=(
        "app.tasks",
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

# Accessing the task ensures Celery's task registry has been populated.
#
# Do not raise an exception here because some test environments may import
# Celery before all application modules are available.
if "app.tasks.auto_requeue_dlq" not in celery_app.tasks:
    # Importing app.tasks above should normally register it.
    # This warning helps diagnose unusual circular-import situations.
    import logging

    logging.getLogger(__name__).warning(
        "app.tasks.auto_requeue_dlq is not registered with celery_app"
    )
