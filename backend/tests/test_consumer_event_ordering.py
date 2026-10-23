"""
test_consumer_event_ordering.py

Comprehensive test suite for Kafka consumer event ordering and monotonic progression
across jobs, technicians, billing, and payment aggregates.
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.redis_client import get_redis_client
from app.services.consumer_event_ordering import (
    ConsumerEventOrdering,
    EventOrderingReceipt,
    MaintainEventOrdering,
    Maintain_event_ordering,
    ConsumerEventOrderingService,
    EventOrderingManager,
)
from app.services.maintain_event_ordering import (
    ConsumerEventOrdering as AliasConsumerEventOrdering,
    MaintainEventOrdering as AliasMaintainEventOrdering,
)
from app.services.consumer_error_handler import ErrorClassification
from app.services.ai.FieldOpsAI.schemas.agent_messages import (
    AgentAddress,
    MessageEnvelope,
    MessageType,
)
from app.tasks import (
    _process_ordered_event_once,
    process_ordered_event_task,
    maintain_event_ordering_task,
)


# =============================================================================
# Fake Redis Fixtures & Message Helpers
# =============================================================================

class FakeRedis:
    def __init__(self):
        self.store = {}
        self.lists = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None, nx=False):
        if nx and key in self.store:
            return None
        self.store[key] = str(value)
        return True

    def delete(self, *keys):
        count = 0
        for k in keys:
            if k in self.store:
                del self.store[k]
                count += 1
            if k in self.lists:
                del self.lists[k]
                count += 1
        return count


@pytest.fixture
def fake_redis():
    return FakeRedis()


def make_test_event(
    event_id: str = "evt_01JEXAMPLE",
    tenant_id: str = "tenant-1",
    correlation_id: str = "corr-101",
    job_id: str = "job-101",
    status: str = "ASSIGNED",
    seq: int = 1,
    timestamp: str = "2026-10-23T10:00:00Z",
    payload_extra: dict = None,
    topic: str = "fieldops.job.events",
) -> dict:
    payload = {
        "event_id": event_id,
        "tenant_id": tenant_id,
        "schema_version": 1,
        "correlation_id": correlation_id,
        "job_id": job_id,
        "status": status,
        "timestamp": timestamp,
    }
    if seq is not None:
        payload["sequence_number"] = seq
    if payload_extra:
        payload.update(payload_extra)
    return {
        "event_id": event_id,
        "tenant_id": tenant_id,
        "correlation_id": correlation_id,
        "topic": topic,
        "payload": payload,
    }


# =============================================================================
# 1. Expected Output Contract Tests
# =============================================================================

@pytest.mark.asyncio
async def test_expected_output_contract_on_recovery(fake_redis):
    """
    Verify recovery returns the exact expected output contract specified in Story 7.11:
    {
        "status": "RECOVERED",
        "event_id": "evt_01JEXAMPLE",
        "retries": 1,
        "idempotent": True,
        "dlq": False
    }
    """
    consumer = ConsumerEventOrdering(redis_client=fake_redis)
    test_event = make_test_event(event_id="evt_01JEXAMPLE")

    receipt = await consumer.recover_event(test_event)

    assert receipt["status"] == "RECOVERED"
    assert receipt["event_id"] == "evt_01JEXAMPLE"
    assert receipt["retries"] == 1
    assert receipt["idempotent"] is True
    assert receipt["dlq"] is False
    assert receipt.is_success is True
    assert receipt.is_recovered is True
    assert bool(receipt) is True


def test_event_ordering_receipt_properties():
    """Verify boolean logic and property helpers of EventOrderingReceipt."""
    r_success = EventOrderingReceipt({
        "status": "PROCESSED",
        "event_id": "evt_1",
        "out_of_order": False,
        "stale": False,
        "dlq": False,
    })
    assert r_success.is_success is True
    assert r_success.is_stale is False
    assert r_success.is_out_of_order is False
    assert bool(r_success) is True

    r_stale = EventOrderingReceipt({
        "status": "STALE_IGNORED",
        "event_id": "evt_2",
        "out_of_order": True,
        "stale": True,
        "dlq": False,
    })
    assert r_stale.is_success is True
    assert r_stale.is_stale is True
    assert r_stale.is_out_of_order is True

    r_failed = EventOrderingReceipt({
        "status": "FAILED",
        "event_id": "evt_3",
        "dlq": True,
    })
    assert r_failed.is_success is False
    assert r_failed.is_dlq is True


# =============================================================================
# 2. Aliases and Naming Compatibility
# =============================================================================

def test_aliases_and_naming():
    """Verify story naming and aliases reference ConsumerEventOrdering."""
    assert MaintainEventOrdering is ConsumerEventOrdering
    assert Maintain_event_ordering is ConsumerEventOrdering
    assert ConsumerEventOrderingService is ConsumerEventOrdering
    assert EventOrderingManager is ConsumerEventOrdering
    assert AliasConsumerEventOrdering is ConsumerEventOrdering
    assert AliasMaintainEventOrdering is ConsumerEventOrdering
    assert ConsumerEventOrdering.CONSUMER_NAME == "Maintain_event_ordering"


# =============================================================================
# 3. Primary Success Path: Monotonic In-Order Lifecycle
# =============================================================================

@pytest.mark.asyncio
async def test_monotonic_in_order_progression(fake_redis):
    """
    Verify sequential status updates for the same job progress cleanly:
    CREATED (rank 1) -> ASSIGNED (rank 2) -> EN_ROUTE (rank 3) -> ON_SITE (rank 4) -> COMPLETED (rank 5)
    """
    applied_statuses = []

    def tracking_handler(payload):
        applied_statuses.append(payload["status"])
        return {"status": "SUCCESS"}

    consumer = ConsumerEventOrdering(redis_client=fake_redis, handler=tracking_handler)

    lifecycle = [
        ("evt_1", "CREATED", 1, "2026-10-23T10:00:00Z"),
        ("evt_2", "ASSIGNED", 2, "2026-10-23T10:15:00Z"),
        ("evt_3", "EN_ROUTE", 3, "2026-10-23T10:30:00Z"),
        ("evt_4", "ON_SITE", 4, "2026-10-23T10:45:00Z"),
        ("evt_5", "COMPLETED", 5, "2026-10-23T11:00:00Z"),
    ]

    for ev_id, st, seq, ts in lifecycle:
        event = make_test_event(event_id=ev_id, status=st, seq=seq, timestamp=ts)
        receipt = await consumer.process_event(event)
        assert receipt["status"] == "PROCESSED"
        assert receipt["out_of_order"] is False
        assert receipt["stale"] is False

    assert applied_statuses == ["CREATED", "ASSIGNED", "EN_ROUTE", "ON_SITE", "COMPLETED"]
    assert fake_redis.get("order:last_seq:job:job-101") == "5"
    assert fake_redis.get("order:last_rank:job:job-101") == "5"


# =============================================================================
# 4. Out-of-Order Status Progression Blocked (No Database State Regression)
# =============================================================================

@pytest.mark.asyncio
async def test_out_of_order_status_regression_blocked(fake_redis):
    """
    Verify that if a later status (e.g. COMPLETED) was already applied,
    an earlier status (e.g. EN_ROUTE) arriving out-of-order is safely ignored
    without invoking domain handler or regressing the job state.
    """
    handler_calls = []

    def domain_handler(payload):
        handler_calls.append(payload["status"])
        return {"status": "SUCCESS"}

    consumer = ConsumerEventOrdering(redis_client=fake_redis, handler=domain_handler)

    # 1. Job completed event arrives and is processed
    completed_event = make_test_event(
        event_id="evt_completed_99",
        status="COMPLETED",
        seq=5,
        timestamp="2026-10-23T11:00:00Z",
    )
    r1 = await consumer.process_event(completed_event)
    assert r1["status"] == "PROCESSED"
    assert handler_calls == ["COMPLETED"]

    # 2. Delayed out-of-order event arrives claiming EN_ROUTE
    delayed_en_route_event = make_test_event(
        event_id="evt_delayed_en_route_22",
        status="EN_ROUTE",
        seq=3,
        timestamp="2026-10-23T10:30:00Z",
    )
    r2 = await consumer.process_event(delayed_en_route_event)

    # Verified: flagged as STALE_IGNORED and handler NOT called again
    assert r2["status"] == "STALE_IGNORED"
    assert r2["out_of_order"] is True
    assert r2["stale"] is True
    assert "Out-of-order status regression" in r2["reason"] or "Stale sequence" in r2["reason"]
    assert handler_calls == ["COMPLETED"]  # State remains COMPLETED!


# =============================================================================
# 5. Out-of-Order Sequence Number Blocked
# =============================================================================

@pytest.mark.asyncio
async def test_stale_sequence_number_blocked(fake_redis):
    """Verify events arriving with an older or equal sequence number are safely ignored."""
    consumer = ConsumerEventOrdering(redis_client=fake_redis)

    # Process seq 10
    ev10 = make_test_event(event_id="evt_seq_10", seq=10)
    r10 = await consumer.process_event(ev10)
    assert r10["status"] == "PROCESSED"

    # Out-of-order seq 9 arrives
    ev9 = make_test_event(event_id="evt_seq_9", seq=9)
    r9 = await consumer.process_event(ev9)
    assert r9["status"] == "STALE_IGNORED"
    assert r9["stale"] is True
    assert r9["out_of_order"] is True
    assert "Stale sequence" in r9["reason"]


# =============================================================================
# 6. Out-of-Order Timestamp / Stale Location Blocked
# =============================================================================

@pytest.mark.asyncio
async def test_stale_timestamp_blocked(fake_redis):
    """Verify stale GPS location pings arriving after newer timestamps are dropped."""
    consumer = ConsumerEventOrdering(redis_client=fake_redis)

    # Newer location event at 11:00 AM
    newer_location = make_test_event(
        event_id="evt_gps_newer",
        topic="fieldops.gps.events",
        status="IN_PROGRESS",
        seq=None,
        timestamp="2026-10-23T11:00:00Z",
        payload_extra={"lat": 37.7749, "lng": -122.4194},
    )
    r1 = await consumer.process_event(newer_location)
    assert r1["status"] == "PROCESSED"

    # Delayed older GPS ping at 10:45 AM
    older_location = make_test_event(
        event_id="evt_gps_delayed",
        topic="fieldops.gps.events",
        status="IN_PROGRESS",
        seq=None,
        timestamp="2026-10-23T10:45:00Z",
        payload_extra={"lat": 37.7700, "lng": -122.4100},
    )
    r2 = await consumer.process_event(older_location)
    assert r2["status"] == "STALE_IGNORED"
    assert r2["stale"] is True
    assert "Stale timestamp" in r2["reason"]


# =============================================================================
# 7. Partition Key Strategy Resolution
# =============================================================================

def test_partition_key_resolution():
    """Verify compute_partition_key deterministically resolves single-partition keys."""
    # 1. Job stream -> job_id
    key_job = ConsumerEventOrdering.compute_partition_key(
        {"job_id": "job-777", "tenant_id": "tenant-1"},
        topic="fieldops.job.events",
    )
    assert key_job == "job-777"

    # 2. Technician tracking -> tech:{tech_id}
    key_tech = ConsumerEventOrdering.compute_partition_key(
        {"technician_id": "tech-888", "tenant_id": "tenant-1"},
        topic="fieldops.gps.events",
    )
    assert key_tech == "tech:tech-888"

    # 3. Invoice stream -> inv:{invoice_id}
    key_inv = ConsumerEventOrdering.compute_partition_key(
        {"invoice_id": "inv-505", "tenant_id": "tenant-1"},
        topic="fieldops.billing.events",
    )
    assert key_inv == "inv:inv-505"

    # 4. Payment stream -> pay:{payment_id}
    key_pay = ConsumerEventOrdering.compute_partition_key(
        {"payment_id": "pay-909", "tenant_id": "tenant-1"},
        topic="fieldops.payment.events",
    )
    assert key_pay == "pay:pay-909"

    # 5. Tenant-ordered stream -> tenant_id
    key_tenant = ConsumerEventOrdering.compute_partition_key(
        {"tenant_id": "tenant-corp", "event_id": "evt-1"},
        topic="fieldops.notification.events",
    )
    assert key_tenant == "tenant-corp"


# =============================================================================
# 8. Distributed Aggregate Locking & Concurrency
# =============================================================================

@pytest.mark.asyncio
async def test_aggregate_distributed_locking_and_contention(fake_redis):
    """Verify lock contention prevents parallel out-of-order execution for same aggregate."""
    consumer = ConsumerEventOrdering(redis_client=fake_redis)

    # Worker A holds lock for job-101
    fake_redis.set("lock:ordering:job:job-101", "worker-a-token")

    event = make_test_event(event_id="evt_race_1", job_id="job-101")
    receipt = await consumer.process_event(event)

    assert receipt["status"] == "LOCKED"
    assert receipt["retryable"] is True
    assert receipt["idempotent"] is True


@pytest.mark.asyncio
async def test_lock_released_on_handler_failure(fake_redis):
    """Verify aggregate lock is released when downstream handler throws an exception."""
    calls = 0

    def flaky_handler(payload):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ConnectionError("Database connection timeout")
        return {"status": "SUCCESS"}

    consumer = ConsumerEventOrdering(redis_client=fake_redis, handler=flaky_handler)
    event = make_test_event(event_id="evt_flaky_1", job_id="job-flaky-9")

    # Attempt 1 fails
    r1 = await consumer.process_event(event)
    assert r1["status"] == "FAILED"
    assert r1["retryable"] is True

    # Lock must be released!
    assert fake_redis.get("lock:ordering:job:job-flaky-9") is None

    # Attempt 2 succeeds
    r2 = await consumer.process_event(event)
    assert r2["status"] == "PROCESSED"
    assert r2["out_of_order"] is False


# =============================================================================
# 9. Security & Forbidden Keys Rejection
# =============================================================================

@pytest.mark.asyncio
async def test_security_violation_rejection(fake_redis):
    """Verify payloads containing forbidden sensitive keys are rejected immediately."""
    consumer = ConsumerEventOrdering(redis_client=fake_redis)

    for bad_key in ["password", "token", "secret", "api_key"]:
        bad_event = make_test_event(
            event_id=f"evt_bad_{bad_key}",
            payload_extra={bad_key: "exposed_secret_value"},
        )
        receipt = await consumer.process_event(bad_event)
        assert receipt["status"] == "FAILED"
        assert receipt["error_type"] == "SecurityPolicyError"
        assert receipt["dlq"] is True


# =============================================================================
# 10. Malformed Messages & Schema Validation
# =============================================================================

@pytest.mark.asyncio
async def test_malformed_messages_and_schema_validation(fake_redis):
    """Verify malformed JSON, invalid types, and unauthorized topics fail safely."""
    consumer = ConsumerEventOrdering(redis_client=fake_redis)

    # Malformed JSON
    r1 = await consumer.process_event("NOT_VALID_JSON{:::}")
    assert r1["status"] == "FAILED"
    assert r1["error_type"] == "JSONDecodeError"

    # Unsupported type
    r2 = await consumer.process_event(99999)
    assert r2["status"] == "FAILED"
    assert r2["error_type"] == "TypeError"

    # Missing required fields
    r3 = await consumer.process_event({"payload": {"event_id": "evt_only"}})
    assert r3["status"] == "FAILED"
    assert "ValidationError" in r3["error_type"]

    # Unauthorized topic
    bad_topic = make_test_event(topic="unauthorized.external.stream")
    r4 = await consumer.process_event(bad_topic)
    assert r4["status"] == "FAILED"
    assert r4["error_type"] == "TopicAuthorizationFailedError"


# =============================================================================
# 11. Metadata Preservation & Idempotency
# =============================================================================

@pytest.mark.asyncio
async def test_metadata_preservation_and_duplicate_check(fake_redis):
    """Verify tenant_id, correlation_id are preserved, and duplicate delivery is recognized."""
    consumer = ConsumerEventOrdering(redis_client=fake_redis)
    event = make_test_event(
        event_id="evt_preserve_1",
        tenant_id="tenant-alpha",
        correlation_id="corr-flow-888",
    )

    r1 = await consumer.process_event(event)
    assert r1["status"] == "PROCESSED"
    assert r1["tenant_id"] == "tenant-alpha"
    assert r1["correlation_id"] == "corr-flow-888"

    # Duplicate resend
    r2 = await consumer.process_event(event)
    assert r2["status"] == "PROCESSED"
    assert r2["idempotent_duplicate"] is True


# =============================================================================
# 12. MessageEnvelope Support
# =============================================================================

@pytest.mark.asyncio
async def test_message_envelope_support(fake_redis):
    """Verify ConsumerEventOrdering seamlessly unwraps MessageEnvelope objects."""
    consumer = ConsumerEventOrdering(redis_client=fake_redis)

    envelope = MessageEnvelope(
        sender=AgentAddress(
            agent_id="test-dispatch",
            agent_type="dispatch",
            tenant_id="tenant-envelope",
        ),
        recipient=None,
        message_type=MessageType.EVENT,
        correlation_id="corr-env-999",
        payload={
            "event_id": "evt_env_order_1",
            "tenant_id": "tenant-envelope",
            "schema_version": 1,
            "job_id": "job-env-1",
            "status": "ASSIGNED",
        },
        topic="fieldops.job.events",
    )

    receipt = await consumer.process_event(envelope)
    assert receipt["status"] == "PROCESSED"
    assert receipt["event_id"] == "evt_env_order_1"
    assert receipt["correlation_id"] == "corr-env-999"


# =============================================================================
# 13. Celery Background Tasks Integration
# =============================================================================

def test_celery_task_integration(monkeypatch, fake_redis):
    """Verify Celery task executes ordered processing and updates state."""
    monkeypatch.setattr("app.tasks.get_redis_client", lambda: fake_redis)

    payload = make_test_event(event_id="evt_celery_order_1")["payload"]

    res = _process_ordered_event_once(redis=fake_redis, event_payload=payload)
    assert res["status"] == "PROCESSED"
    assert res["event_id"] == "evt_celery_order_1"
    assert res["out_of_order"] is False


# =============================================================================
# 14. Admin Health & Metrics Endpoint
# =============================================================================

@pytest.mark.asyncio
async def test_admin_metrics_endpoint():
    """Verify get_kafka_ordering_metrics endpoint returns operational metrics."""
    from app.routes.admin_metrics import get_kafka_ordering_metrics
    result = await get_kafka_ordering_metrics()
    assert result["status"] == "healthy"
    assert result["consumer"] == "Maintain_event_ordering"
    assert "metrics" in result

