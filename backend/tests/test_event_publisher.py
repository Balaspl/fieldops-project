import json
from datetime import datetime, timezone

import pytest

from app.services.event_publisher import publish_dispatch_event


class FakeRedis:
    def __init__(self):
        self.calls = []

    def publish(self, channel, message):
        self.calls.append((channel, message))
        return 1


def test_publish_job_completed_uses_authoritative_timestamp():
    redis = FakeRedis()

    completed_at = datetime(
        2026,
        9,
        18,
        7,
        0,
        0,
        tzinfo=timezone.utc,
    )

    publish_dispatch_event(
        redis,
        event_type="JOB_COMPLETED",
        job_id="1001",
        old_status="ON_SITE",
        new_status="COMPLETED",
        tenant_id="org-1",
        technician_id="42",
        technician_name="John Tech",
        completed_at=completed_at,
        correlation_id="corr-123",
        event_id="JOB_COMPLETED:org-1:1001:9001",
    )

    channel, message = redis.calls[0]
    payload = json.loads(message)

    assert channel == "dispatch_events"

    assert payload["event"] == "JOB_COMPLETED"
    assert payload["event_type"] == "job_completed"
    assert payload["event_id"] == "JOB_COMPLETED:org-1:1001:9001"

    assert payload["job_id"] == "1001"
    assert payload["tenant_id"] == "org-1"

    assert payload["old_status"] == "ON_SITE"
    assert payload["new_status"] == "COMPLETED"

    assert payload["timestamp"] == "2026-09-18T07:00:00Z"
    assert payload["correlation_id"] == "corr-123"


def test_publish_rejects_naive_completion_timestamp():
    redis = FakeRedis()

    with pytest.raises(
        ValueError,
        match="timezone-aware",
    ):
        publish_dispatch_event(
            redis,
            event_type="JOB_COMPLETED",
            job_id="1001",
            old_status="ON_SITE",
            new_status="COMPLETED",
            tenant_id="org-1",
            completed_at=datetime(
                2026,
                9,
                18,
                7,
                0,
                0,
            ),
        )

    assert redis.calls == []