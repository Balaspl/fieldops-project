"""
test_scheduled_tasks.py

Comprehensive test suite for Story: Add scheduled tasks (Celery Queue Management).
Validates:
- Canonical JSON contract:
    {
        "status": "SCHEDULED",
        "scheduler": "celery_beat"
    }
- Preservation of foundational schedules (email outbox, dispatcher digest, customer engagement, SLA countdown, prompt analytics, DLQ auto-requeue).
- Extending Celery Beat schedule with custom recurring work without regressions.
- Timezone configured as UTC.
- Idempotency guard preventing concurrent overlapping executions.
- Story aliases across celery_app and tasks.
- FastAPI administrative endpoints and aliases.
"""

from unittest.mock import MagicMock
import pytest

from app.celery_app import (
    celery_app,
    FOUNDATIONAL_BEAT_SCHEDULES,
    get_scheduled_tasks_config,
    add_scheduled_tasks,
    AddScheduledTasks,
    Add_scheduled_tasks,
    add_scheduled_task,
    AddScheduledTask,
    get_scheduled_tasks,
    get_scheduled_task_config,
)
from app.tasks import (
    add_scheduled_tasks_task,
    run_scheduled_task_idempotently,
    FOUNDATIONAL_BEAT_SCHEDULES as TASKS_FOUNDATIONAL_SCHEDULES,
    get_scheduled_tasks_config as tasks_get_config,
    add_scheduled_tasks as tasks_add_scheduled_tasks,
    AddScheduledTasks as TasksAddScheduledTasks,
    Add_scheduled_tasks as TasksAdd_scheduled_tasks,
    add_scheduled_task as tasks_add_scheduled_task,
    AddScheduledTask as TasksAddScheduledTask,
    get_scheduled_tasks as tasks_get_scheduled_tasks,
    get_scheduled_task_config as tasks_get_scheduled_task_config,
)


# =============================================================================
# Fake Redis Fixture
# =============================================================================

class FakeRedis:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None, nx=False):
        if nx and key in self.store:
            return False
        self.store[key] = str(value)
        return True


@pytest.fixture
def fake_redis():
    return FakeRedis()


# =============================================================================
# 1. Output Contract & Basic Configuration Tests
# =============================================================================

def test_scheduled_tasks_contract():
    """Verify exact JSON contract matches specification."""
    config = get_scheduled_tasks_config()
    assert config == {
        "status": "SCHEDULED",
        "scheduler": "celery_beat",
    }


def test_add_scheduled_tasks_activation():
    """Verify add_scheduled_tasks registers beat schedules and returns contract."""
    res = add_scheduled_tasks()
    assert res == {
        "status": "SCHEDULED",
        "scheduler": "celery_beat",
    }
    assert celery_app.conf.timezone == "UTC"


def test_scheduled_tasks_aliases_and_module_exports():
    """Verify all story aliases across celery_app and tasks are consistent."""
    expected = {
        "status": "SCHEDULED",
        "scheduler": "celery_beat",
    }

    assert AddScheduledTasks() == expected
    assert Add_scheduled_tasks() == expected
    assert add_scheduled_task() == expected
    assert AddScheduledTask() == expected
    assert get_scheduled_tasks() == expected
    assert get_scheduled_task_config() == expected

    # Tasks re-exports
    assert tasks_get_config() == expected
    assert tasks_add_scheduled_tasks() == expected
    assert TasksAddScheduledTasks() == expected
    assert TasksAdd_scheduled_tasks() == expected
    assert tasks_add_scheduled_task() == expected
    assert TasksAddScheduledTask() == expected
    assert tasks_get_scheduled_tasks() == expected
    assert tasks_get_scheduled_task_config() == expected
    assert TASKS_FOUNDATIONAL_SCHEDULES == FOUNDATIONAL_BEAT_SCHEDULES


# =============================================================================
# 2. Preservation of Existing Foundational Schedules
# =============================================================================

def test_preserves_all_foundational_schedules():
    """Verify existing operational schedules are preserved and active."""
    add_scheduled_tasks()
    beat = celery_app.conf.beat_schedule

    # 1. Transactional Email Outbox (every 30 seconds)
    assert "process-transactional-email-outbox-every-30-seconds" in beat
    assert beat["process-transactional-email-outbox-every-30-seconds"]["task"] == "app.tasks.process_transactional_email_outbox"
    assert beat["process-transactional-email-outbox-every-30-seconds"]["schedule"] == 30.0

    # 2. Dispatcher Digest (every 5 minutes)
    assert "send-dispatcher-digest-every-5-minutes" in beat
    assert beat["send-dispatcher-digest-every-5-minutes"]["task"] == "app.tasks.send_dispatcher_digest"
    assert beat["send-dispatcher-digest-every-5-minutes"]["schedule"] == 300.0

    # 3. Customer Daily Engagement (every 30 minutes)
    assert "send-customer-daily-engagement-every-30-minutes" in beat
    assert beat["send-customer-daily-engagement-every-30-minutes"]["task"] == "app.tasks.send_customer_daily_engagement"
    assert beat["send-customer-daily-engagement-every-30-minutes"]["schedule"] == 1800.0

    # 4. SLA Countdown broadcast (every 30 seconds)
    assert "broadcast-sla-countdown-every-30-seconds" in beat
    assert beat["broadcast-sla-countdown-every-30-seconds"]["task"] == "app.tasks.broadcast_sla_countdown"
    assert beat["broadcast-sla-countdown-every-30-seconds"]["schedule"] == 30.0

    # 5. Prompt Analytics aggregation (hourly)
    assert "aggregate-prompt-analytics-hourly" in beat
    assert beat["aggregate-prompt-analytics-hourly"]["task"] == "app.tasks.aggregate_prompt_analytics_task"
    assert beat["aggregate-prompt-analytics-hourly"]["schedule"] == 3600.0

    # 6. DLQ Auto-requeue (every 5 minutes)
    assert "auto-requeue-dlq-every-5-minutes" in beat
    assert beat["auto-requeue-dlq-every-5-minutes"]["task"] == "app.tasks.auto_requeue_dlq"
    assert beat["auto-requeue-dlq-every-5-minutes"]["schedule"] == 300.0


def test_extending_schedules_preserves_foundational():
    """Verify adding custom operational schedules merges cleanly without dropping existing ones."""
    custom_schedules = {
        "cleanup-expired-locks-every-10-minutes": {
            "task": "app.tasks.cleanup_expired_locks",
            "schedule": 600.0,
        }
    }
    add_scheduled_tasks(schedules=custom_schedules)
    beat = celery_app.conf.beat_schedule

    assert "cleanup-expired-locks-every-10-minutes" in beat
    assert beat["cleanup-expired-locks-every-10-minutes"]["task"] == "app.tasks.cleanup_expired_locks"
    # Ensure foundational still present
    assert "send-dispatcher-digest-every-5-minutes" in beat
    assert "auto-requeue-dlq-every-5-minutes" in beat


# =============================================================================
# 3. Idempotency & Overlap Prevention Tests
# =============================================================================

def test_scheduled_task_idempotency_prevents_overlapping_runs(fake_redis):
    """Verify run_scheduled_task_idempotently allows execution only once per time window."""
    counter = {"runs": 0}

    def sample_recurring_job():
        counter["runs"] += 1
        return "SUCCESS"

    # First run in interval -> Acquired lock, executed
    res1 = run_scheduled_task_idempotently(
        schedule_key="sample_digest",
        interval_seconds=300,
        func=sample_recurring_job,
        redis=fake_redis,
    )
    assert res1 == "SUCCESS"
    assert counter["runs"] == 1

    # Second concurrent run in same window -> Skipped duplicate
    res2 = run_scheduled_task_idempotently(
        schedule_key="sample_digest",
        interval_seconds=300,
        func=sample_recurring_job,
        redis=fake_redis,
    )
    assert res2 == {"status": "SKIPPED_DUPLICATE", "schedule_key": "sample_digest"}
    assert counter["runs"] == 1


# =============================================================================
# 4. Celery Task Execution Tests
# =============================================================================

def test_add_scheduled_tasks_celery_task():
    """Verify Celery task executes and returns canonical contract."""
    res = add_scheduled_tasks_task(
        tenant_id="tenant-beat-test",
        correlation_id="corr-beat-123",
    )
    assert res == {
        "status": "SCHEDULED",
        "scheduler": "celery_beat",
    }


# =============================================================================
# 5. Admin Queue REST Endpoints Tests
# =============================================================================

def test_admin_queue_schedules_endpoints():
    """Verify FastAPI admin queue endpoints return expected scheduled tasks contract."""
    from app.routes.admin_queue import (
        get_scheduled_tasks_status,
        configure_scheduled_tasks_endpoint,
        get_scheduled_tasks_status_alias,
        configure_scheduled_tasks_endpoint_alias,
    )

    expected = {
        "status": "SCHEDULED",
        "scheduler": "celery_beat",
    }

    assert get_scheduled_tasks_status() == expected
    assert configure_scheduled_tasks_endpoint() == expected
    assert get_scheduled_tasks_status_alias() == expected
    assert configure_scheduled_tasks_endpoint_alias() == expected

