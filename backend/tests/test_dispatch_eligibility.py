import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.services.dispatch_eligibility import evaluate_technician_dispatch_eligibility


class FakeRedis:
    def __init__(self, payload):
        self.payload = payload

    def get(self, key):
        return self.payload


_DEFAULT_HEARTBEAT = object()


def technician(status="AVAILABLE", last_ping=_DEFAULT_HEARTBEAT):
    return SimpleNamespace(
        technician_id=25, tech_id="tech-25", tenant_id="org-a",
        technician_status=status, current_jobs=0, max_jobs=2,
        last_ping=datetime.now(timezone.utc) if last_ping is _DEFAULT_HEARTBEAT else last_ping,
    )


def location(**overrides):
    data = {
        "tenant_id": "org-a", "latitude": 13.08, "longitude": 80.27,
        "accuracy": 20, "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    data.update(overrides)
    return json.dumps(data)


def test_offline_technician_becomes_eligible_after_fresh_available_heartbeat():
    redis = FakeRedis(location())
    offline = evaluate_technician_dispatch_eligibility(
        technician("OFFLINE"), job_tenant_id=None, redis_client=redis,
    )
    online = evaluate_technician_dispatch_eligibility(
        technician("AVAILABLE"), job_tenant_id=None, redis_client=redis,
    )
    assert not offline["eligible"]
    assert "not_available" in offline["reason"]
    assert online["eligible"]


def test_missing_and_stale_heartbeats_are_ineligible():
    redis = FakeRedis(location())
    missing = evaluate_technician_dispatch_eligibility(
        technician(last_ping=None), job_tenant_id=None, redis_client=FakeRedis(None),
    )
    stale = evaluate_technician_dispatch_eligibility(
        technician(last_ping=datetime.now(timezone.utc) - timedelta(minutes=10)),
        job_tenant_id=None, redis_client=redis,
    )
    assert "missing_or_future_heartbeat" in missing["reason"]
    assert "stale_heartbeat" in stale["reason"]


def test_stale_and_invalid_gps_are_ineligible():
    stale = evaluate_technician_dispatch_eligibility(
        technician(), job_tenant_id=None,
        redis_client=FakeRedis(location(timestamp=(datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat())),
    )
    invalid = evaluate_technician_dispatch_eligibility(
        technician(), job_tenant_id=None,
        redis_client=FakeRedis(location(latitude=999)),
    )
    assert "stale_location" in stale["reason"]
    assert "invalid_location_coordinates" in invalid["reason"]


def test_missing_location_keeps_fresh_heartbeat_but_reports_null_location_age():
    result = evaluate_technician_dispatch_eligibility(
        technician(), job_tenant_id=None, redis_client=FakeRedis(None),
    )
    assert result["heartbeat_age_seconds"] is not None
    assert result["location_age_seconds"] is None
    assert result["reason"] == "location_unavailable"


def test_fresh_location_update_is_eligible_and_returns_age_and_coordinates():
    result = evaluate_technician_dispatch_eligibility(
        technician(), job_tenant_id=None, redis_client=FakeRedis(location()),
    )
    assert result["eligible"] is True
    assert result["location_age_seconds"] is not None
    assert result["location_coordinates"] == (13.08, 80.27)


@pytest.mark.parametrize("accuracy", [0, 107, 150])
def test_accuracy_through_150_meters_is_eligible(accuracy):
    result = evaluate_technician_dispatch_eligibility(
        technician(), job_tenant_id="org-a",
        redis_client=FakeRedis(location(accuracy=accuracy)),
    )
    assert result["eligible"] is True
    assert "poor_location_accuracy" not in (result["reason"] or "")


def test_151_meter_reading_uses_configured_fallback_policy(monkeypatch):
    from app.services import dispatch_eligibility

    monkeypatch.setattr(dispatch_eligibility, "LOCATION_MAX_ACCURACY_METERS", 150)
    default_fallback = evaluate_technician_dispatch_eligibility(
        technician(), job_tenant_id="org-a",
        redis_client=FakeRedis(location(accuracy=151)),
    )
    assert default_fallback["eligible"] is False
    assert "poor_location_accuracy" in default_fallback["reason"]

    monkeypatch.setattr(dispatch_eligibility, "LOCATION_MAX_ACCURACY_METERS", 200)
    configured_fallback = evaluate_technician_dispatch_eligibility(
        technician(), job_tenant_id="org-a",
        redis_client=FakeRedis(location(accuracy=151)),
    )
    assert configured_fallback["eligible"] is True


def test_missing_location_remains_ineligible_under_existing_policy():
    result = evaluate_technician_dispatch_eligibility(
        technician(), job_tenant_id="org-a", redis_client=FakeRedis(None),
    )
    assert result["eligible"] is False
    assert result["reason"] == "location_unavailable"


def test_offline_technician_with_accurate_gps_remains_ineligible():
    result = evaluate_technician_dispatch_eligibility(
        technician("OFFLINE"), job_tenant_id="org-a",
        redis_client=FakeRedis(location(accuracy=50)),
    )
    assert result["eligible"] is False
    assert "not_available" in result["reason"]


def test_fresh_gps_does_not_make_stale_heartbeat_eligible():
    result = evaluate_technician_dispatch_eligibility(
        technician(last_ping=datetime.now(timezone.utc) - timedelta(minutes=10)),
        job_tenant_id="org-a", redis_client=FakeRedis(location(accuracy=50)),
    )
    assert result["eligible"] is False
    assert "stale_heartbeat" in result["reason"]
