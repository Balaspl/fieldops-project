import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.services.consumer_retry_mechanism import (
    ConsumeReceipt,
    ConsumerRetryMechanism,
    AddRetryMechanismConsumer,
    Add_retry_mechanism,
    ConsumerRetryManager,
    RetryConsumer,
    ErrorClassification,
    classify_error,
    redact_sensitive_data,
)
from app.services.ai.FieldOpsAI.schemas.agent_messages import (
    AgentAddress,
    MessageEnvelope,
    MessageType,
)
from app.tasks import (
    _process_retry_mechanism_event_once,
    process_retry_mechanism_event_task,
)


@pytest.fixture
def fake_redis():
    class FakeRedis:
        def __init__(self):
            self.store = {}
            self.lists = {}

        def get(self, key):
            return self.store.get(key)

        def set(self, key, value, ex=None):
            self.store[key] = value

        def setex(self, key, time, value):
            self.store[key] = value

        def rpush(self, key, value):
            if key not in self.lists:
                self.lists[key] = []
            self.lists[key].append(value)
            return len(self.lists[key])

        def lrange(self, key, start, stop):
            items = self.lists.get(key, [])
            if stop == -1:
                return items[start:]
            return items[start : stop + 1]

        def delete(self, *keys):
            for k in keys:
                self.store.pop(k, None)
                self.lists.pop(k, None)

        def publish(self, channel, message):
            return 1

    return FakeRedis()


@pytest.fixture
def fake_consumer_manager():
    manager = MagicMock()
    manager.start = AsyncMock()
    manager.stop = AsyncMock()
    return manager


# ============================================================================
# 1. ConsumeReceipt tests
# ============================================================================

def test_consume_receipt_behavior():
    success_receipt = ConsumeReceipt(
        {"status": "PROCESSED", "consumer": "Add_retry_mechanism", "event_id": "evt_1", "attempt": 1}
    )
    assert success_receipt.is_success is True
    assert bool(success_receipt) is True
    assert success_receipt["consumer"] == "Add_retry_mechanism"
    assert success_receipt["status"] == "PROCESSED"

    failed_receipt = ConsumeReceipt(
        {"status": "FAILED", "consumer": "Add_retry_mechanism", "event_id": "evt_2", "attempt": 1, "error": "test"}
    )
    assert failed_receipt.is_success is False
    assert bool(failed_receipt) is False
    assert failed_receipt["status"] == "FAILED"


# ============================================================================
# 2. Aliases and Default Configuration
# ============================================================================

def test_aliases_and_defaults(fake_redis):
    consumer = ConsumerRetryMechanism(redis_client=fake_redis)
    assert consumer.CONSUMER_NAME == "Add_retry_mechanism"
    assert consumer.topic == "fieldops.events"
    assert consumer.group_id == "fieldops-retry-mechanism"
    assert consumer.max_retries == 3
    assert consumer.base_delay == 1.0
    assert consumer.max_delay == 30.0
    assert consumer.backoff_factor == 2.0
    assert consumer.dlq_key == "consumer:dlq"

    assert AddRetryMechanismConsumer is ConsumerRetryMechanism
    assert Add_retry_mechanism is ConsumerRetryMechanism
    assert ConsumerRetryManager is ConsumerRetryMechanism
    assert RetryConsumer is ConsumerRetryMechanism


# ============================================================================
# 3. Bounded Backoff Calculations
# ============================================================================

def test_calculate_backoff_bounded_exponential():
    consumer = ConsumerRetryMechanism(
        base_delay=1.0,
        max_delay=10.0,
        backoff_factor=2.0,
        jitter=False,
    )

    # Attempt 1 -> 1.0s
    assert consumer.calculate_backoff(1) == 1.0
    # Attempt 2 -> 1.0 * 2^1 = 2.0s
    assert consumer.calculate_backoff(2) == 2.0
    # Attempt 3 -> 1.0 * 2^2 = 4.0s
    assert consumer.calculate_backoff(3) == 4.0
    # Attempt 4 -> 1.0 * 2^3 = 8.0s
    assert consumer.calculate_backoff(4) == 8.0
    # Attempt 5 -> capped at max_delay 10.0s
    assert consumer.calculate_backoff(5) == 10.0
    # Attempt 10 -> capped at max_delay 10.0s
    assert consumer.calculate_backoff(10) == 10.0


def test_calculate_backoff_with_jitter():
    consumer = ConsumerRetryMechanism(
        base_delay=2.0,
        max_delay=20.0,
        backoff_factor=2.0,
        jitter=True,
    )

    delay = consumer.calculate_backoff(2)
    # Without jitter it would be 4.0; with jitter it is between 4.0 and 4.4
    assert 4.0 <= delay <= 4.5


# ============================================================================
# 4. Primary Success Path
# ============================================================================

@pytest.mark.asyncio
async def test_consumer_primary_success_path_dict(fake_redis, fake_consumer_manager):
    consumer = ConsumerRetryMechanism(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )

    event_id = "evt_01JEXAMPLE"
    payload = {
        "event_id": event_id,
        "tenant_id": "tenant-001",
        "schema_version": 1,
        "event_type": "job_created",
        "job_id": "JOB-101",
    }

    receipt = await consumer.process_event(payload, attempt=1)

    assert receipt["status"] == "PROCESSED"
    assert receipt["consumer"] == "Add_retry_mechanism"
    assert receipt["event_id"] == event_id
    assert receipt["attempt"] == 1
    assert bool(receipt) is True

    # Check idempotency marker set in Redis
    assert fake_redis.get(f"consumer_retry:event_processed:{event_id}") == "1"


@pytest.mark.asyncio
async def test_consumer_primary_success_path_json_string(fake_redis, fake_consumer_manager):
    consumer = ConsumerRetryMechanism(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )

    event_id = "evt_retry_json_001"
    raw_json = json.dumps({
        "event_id": event_id,
        "tenant_id": "tenant-002",
        "schema_version": 1,
        "event_type": "sla_checked",
    })

    receipt = await consumer.process_event(raw_json, attempt=1)

    assert receipt["status"] == "PROCESSED"
    assert receipt["consumer"] == "Add_retry_mechanism"
    assert receipt["event_id"] == event_id
    assert receipt["attempt"] == 1


@pytest.mark.asyncio
async def test_consumer_primary_success_path_envelope(fake_redis, fake_consumer_manager):
    consumer = ConsumerRetryMechanism(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )

    event_id = "evt_env_retry_001"
    envelope = MessageEnvelope(
        sender=AgentAddress(
            agent_type="dispatch",
            agent_id="dispatch-agent",
            tenant_id="tenant-003",
        ),
        recipient=None,
        message_type=MessageType.EVENT,
        payload={
            "event_id": event_id,
            "tenant_id": "tenant-003",
            "schema_version": 1,
            "event_type": "dispatch_assigned",
        },
        topic="fieldops.events",
    )

    receipt = await consumer.process_event(envelope, attempt=1)

    assert receipt["status"] == "PROCESSED"
    assert receipt["consumer"] == "Add_retry_mechanism"
    assert receipt["event_id"] == event_id
    assert receipt["attempt"] == 1


# ============================================================================
# 5. Idempotency & Duplicate Business Side Effects Prevention
# ============================================================================

@pytest.mark.asyncio
async def test_idempotency_prevents_duplicate_business_actions(fake_redis):
    side_effects = []

    def business_action_handler(msg):
        side_effects.append(msg["event_id"])
        return {"action": "executed"}

    consumer = ConsumerRetryMechanism(
        redis_client=fake_redis,
        handler=business_action_handler,
    )

    payload = {
        "event_id": "evt_idemp_retry_001",
        "tenant_id": "tenant-1",
        "schema_version": 1,
    }

    # First attempt: executes business action
    receipt1 = await consumer.process_event(payload, attempt=1)
    assert receipt1["status"] == "PROCESSED"
    assert receipt1.get("idempotent_duplicate") is not True
    assert len(side_effects) == 1

    # Second attempt (e.g. redelivery / retry): skipped!
    receipt2 = await consumer.process_event(payload, attempt=2)
    assert receipt2["status"] == "PROCESSED"
    assert receipt2["idempotent_duplicate"] is True
    # Side effects list must NOT increase!
    assert len(side_effects) == 1


# ============================================================================
# 6. Malformed Messages & Encodings (Preventing Crashes)
# ============================================================================

@pytest.mark.asyncio
async def test_malformed_json_does_not_crash_and_routes_to_dlq(fake_redis):
    consumer = ConsumerRetryMechanism(redis_client=fake_redis)

    malformed = "{ broken json: [1, 2, "
    receipt = await consumer.process_event(malformed, attempt=1)

    assert receipt["status"] == "FAILED"
    assert receipt["consumer"] == "Add_retry_mechanism"
    assert receipt["event_id"] == "unknown"
    assert receipt["error_type"] == "JSONDecodeError"
    assert receipt["error_classification"] == "TERMINAL"
    assert receipt["retryable"] is False

    # DLQ contains failure record
    dlq_items = fake_redis.lrange("consumer:dlq", 0, -1)
    assert len(dlq_items) == 1
    dlq_data = json.loads(dlq_items[0])
    assert dlq_data["error_type"] == "JSONDecodeError"
    assert dlq_data["consumer"] == "Add_retry_mechanism"


@pytest.mark.asyncio
async def test_malformed_bytes_encoding_does_not_crash(fake_redis):
    consumer = ConsumerRetryMechanism(redis_client=fake_redis)

    bad_bytes = b"\xff\xfe\xfa\x80"
    receipt = await consumer.process_event(bad_bytes, attempt=1)

    assert receipt["status"] == "FAILED"
    assert receipt["consumer"] == "Add_retry_mechanism"
    assert receipt["error_type"] == "UnicodeDecodeError"
    assert receipt["retryable"] is False


@pytest.mark.asyncio
async def test_unsupported_message_type_does_not_crash(fake_redis):
    consumer = ConsumerRetryMechanism(redis_client=fake_redis)

    receipt = await consumer.process_event(9876543, attempt=1)

    assert receipt["status"] == "FAILED"
    assert receipt["consumer"] == "Add_retry_mechanism"
    assert receipt["error_type"] == "TypeError"
    assert receipt["retryable"] is False


# ============================================================================
# 7. Authorization and Domain Validation Errors (Terminal, No Retry)
# ============================================================================

@pytest.mark.asyncio
async def test_unauthorized_topic_rejected(fake_redis):
    consumer = ConsumerRetryMechanism(redis_client=fake_redis)

    payload = {
        "event_id": "evt_unauth_002",
        "tenant_id": "tenant-001",
        "schema_version": 1,
        "topic": "unauthorized.topic.leak",
    }

    receipt = await consumer.process_event(payload, attempt=1)

    assert receipt["status"] == "FAILED"
    assert receipt["consumer"] == "Add_retry_mechanism"
    assert receipt["error_type"] == "TopicAuthorizationFailedError"
    assert receipt["error_classification"] == "TERMINAL"
    assert receipt["retryable"] is False


@pytest.mark.asyncio
async def test_missing_required_fields_fails_validation(fake_redis):
    consumer = ConsumerRetryMechanism(redis_client=fake_redis)

    invalid_payload = {
        "event_type": "job_created",
    }

    receipt = await consumer.process_event(invalid_payload, attempt=1)

    assert receipt["status"] == "FAILED"
    assert receipt["consumer"] == "Add_retry_mechanism"
    assert receipt["error_type"] == "ValidationError"
    assert receipt["retryable"] is False


@pytest.mark.asyncio
async def test_forbidden_sensitive_keys_rejected_and_redacted(fake_redis):
    consumer = ConsumerRetryMechanism(redis_client=fake_redis)

    payload = {
        "event_id": "evt_sensitive_002",
        "tenant_id": "tenant-001",
        "schema_version": 1,
        "api_key": "raw-api-key-secret-value",
    }

    receipt = await consumer.process_event(payload, attempt=1)

    assert receipt["status"] == "FAILED"
    assert receipt["consumer"] == "Add_retry_mechanism"
    assert receipt["error_type"] == "SecurityPolicyError"
    assert receipt["retryable"] is False

    dlq_items = fake_redis.lrange("consumer:dlq", 0, -1)
    assert len(dlq_items) == 1
    assert "raw-api-key-secret-value" not in dlq_items[0]


# ============================================================================
# 8. Bounded Retry Accounting and DLQ Routing
# ============================================================================

@pytest.mark.asyncio
async def test_transient_failure_retryable_until_exhausted(fake_redis):
    def transient_handler(msg):
        raise ConnectionError("External ERP connection dropped")

    consumer = ConsumerRetryMechanism(
        redis_client=fake_redis,
        handler=transient_handler,
        max_retries=3,
        base_delay=0.1,
    )

    payload = {"event_id": "evt_transient_1", "tenant_id": "t1", "schema_version": 1}

    # Attempt 1: retryable
    res1 = await consumer.process_event(payload, attempt=1)
    assert res1["status"] == "FAILED"
    assert res1["error_classification"] == "RETRYABLE"
    assert res1["retryable"] is True
    assert res1["next_attempt"] == 2
    assert res1["backoff_delay"] == 0.1
    assert fake_redis.lrange("consumer:dlq", 0, -1) == []

    # Attempt 2: retryable
    res2 = await consumer.process_event(payload, attempt=2)
    assert res2["status"] == "FAILED"
    assert res2["error_classification"] == "RETRYABLE"
    assert res2["retryable"] is True
    assert res2["next_attempt"] == 3
    assert res2["backoff_delay"] == 0.2
    assert fake_redis.lrange("consumer:dlq", 0, -1) == []

    # Attempt 3: retries exhausted -> routed to DLQ!
    res3 = await consumer.process_event(payload, attempt=3)
    assert res3["status"] == "FAILED"
    assert res3["retryable"] is False
    assert res3["exhausted"] is True
    assert res3["next_attempt"] is None

    dlq_items = fake_redis.lrange("consumer:dlq", 0, -1)
    assert len(dlq_items) == 1
    assert "External ERP connection dropped" in dlq_items[0]


@pytest.mark.asyncio
async def test_terminal_failure_routes_to_dlq_immediately(fake_redis):
    def terminal_handler(msg):
        raise KeyError("missing_required_key_in_domain_entity")

    consumer = ConsumerRetryMechanism(
        redis_client=fake_redis,
        handler=terminal_handler,
        max_retries=3,
    )

    payload = {"event_id": "evt_term_fast_1", "tenant_id": "t1", "schema_version": 1}

    # Attempt 1 immediately sent to DLQ because error is not retryable
    res = await consumer.process_event(payload, attempt=1)
    assert res["status"] == "FAILED"
    assert res["error_classification"] == "TERMINAL"
    assert res["retryable"] is False
    assert res["exhausted"] is False

    dlq_items = fake_redis.lrange("consumer:dlq", 0, -1)
    assert len(dlq_items) == 1


# ============================================================================
# 9. Automated process_with_retry Loop
# ============================================================================

@pytest.mark.asyncio
async def test_process_with_retry_succeeds_after_transient_failures(fake_redis):
    attempts = 0

    def flaky_service(msg):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise TimeoutError(f"Temporary database timeout on attempt {attempts}")
        return {"result": "success"}

    consumer = ConsumerRetryMechanism(
        redis_client=fake_redis,
        handler=flaky_service,
        max_retries=3,
        base_delay=0.01,  # Fast backoff for tests
    )

    payload = {"event_id": "evt_flaky_001", "tenant_id": "tenant-1", "schema_version": 1}

    receipt = await consumer.process_with_retry(payload)

    assert receipt["status"] == "PROCESSED"
    assert receipt["consumer"] == "Add_retry_mechanism"
    assert receipt["attempt"] == 3
    assert attempts == 3


@pytest.mark.asyncio
async def test_process_with_retry_stops_on_terminal_error(fake_redis):
    attempts = 0

    def terminal_service(msg):
        nonlocal attempts
        attempts += 1
        raise ValueError("Fatal domain validation constraint")

    consumer = ConsumerRetryMechanism(
        redis_client=fake_redis,
        handler=terminal_service,
        max_retries=3,
        base_delay=0.01,
    )

    payload = {"event_id": "evt_fatal_001", "tenant_id": "tenant-1", "schema_version": 1}

    receipt = await consumer.process_with_retry(payload)

    assert receipt["status"] == "FAILED"
    assert receipt["retryable"] is False
    # Must stop immediately on 1st attempt!
    assert attempts == 1


@pytest.mark.asyncio
async def test_process_with_retry_exhausts_and_routes_to_dlq(fake_redis):
    attempts = 0

    def persistent_down_service(msg):
        nonlocal attempts
        attempts += 1
        raise ConnectionError("Upstream server is completely down 503")

    consumer = ConsumerRetryMechanism(
        redis_client=fake_redis,
        handler=persistent_down_service,
        max_retries=3,
        base_delay=0.01,
    )

    payload = {"event_id": "evt_exhaust_001", "tenant_id": "tenant-1", "schema_version": 1}

    receipt = await consumer.process_with_retry(payload)

    assert receipt["status"] == "FAILED"
    assert receipt["retryable"] is False
    assert receipt["exhausted"] is True
    assert attempts == 3

    dlq_items = fake_redis.lrange("consumer:dlq", 0, -1)
    assert len(dlq_items) == 1


# ============================================================================
# 10. wrap_with_retry Decorator
# ============================================================================

@pytest.mark.asyncio
async def test_wrap_with_retry_decorator(fake_redis):
    attempts = 0

    def unstable_handler(msg):
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise ConnectionError("Transient network drop")
        return {"completed": True}

    consumer = ConsumerRetryMechanism(
        redis_client=fake_redis,
        max_retries=3,
        base_delay=0.01,
    )

    wrapped_fn = consumer.wrap_with_retry(unstable_handler)

    receipt = await wrapped_fn({
        "event_id": "evt_wrap_retry_1",
        "tenant_id": "t1",
        "schema_version": 1,
    })

    assert receipt["status"] == "PROCESSED"
    assert receipt["consumer"] == "Add_retry_mechanism"
    assert attempts == 2


# ============================================================================
# 11. Lifecycle Context Manager
# ============================================================================

@pytest.mark.asyncio
async def test_lifecycle_methods(fake_consumer_manager):
    consumer = ConsumerRetryMechanism(
        consumer_manager=fake_consumer_manager,
    )

    async with consumer:
        fake_consumer_manager.start.assert_awaited_once()

    fake_consumer_manager.stop.assert_awaited_once()


# ============================================================================
# 12. Celery Tasks and Helpers
# ============================================================================

def test_process_retry_mechanism_event_once_helper(fake_redis):
    # Missing event_id
    bad_res = _process_retry_mechanism_event_once(
        redis=fake_redis,
        event_payload={"tenant_id": "t1"},
        attempt=1,
    )
    assert bad_res["status"] == "FAILED"
    assert bad_res["consumer"] == "Add_retry_mechanism"

    # Valid payload
    payload = {
        "event_id": "evt_celery_retry_001",
        "tenant_id": "tenant-celery",
        "schema_version": 1,
    }
    good_res = _process_retry_mechanism_event_once(
        redis=fake_redis,
        event_payload=payload,
        attempt=1,
    )
    assert good_res["status"] == "PROCESSED"
    assert good_res["consumer"] == "Add_retry_mechanism"
    assert good_res["event_id"] == "evt_celery_retry_001"

    # Duplicate call
    dup_res = _process_retry_mechanism_event_once(
        redis=fake_redis,
        event_payload=payload,
        attempt=1,
    )
    assert dup_res["status"] == "PROCESSED"
    assert dup_res["idempotent_duplicate"] is True


def test_process_retry_mechanism_event_task(fake_redis):
    with patch("app.tasks.get_redis_client", return_value=fake_redis):
        payload = {
            "event_id": "evt_celery_task_retry_001",
            "tenant_id": "tenant-celery",
            "schema_version": 1,
        }
        res = process_retry_mechanism_event_task(payload, attempt=1)
        assert res["status"] == "PROCESSED"
        assert res["consumer"] == "Add_retry_mechanism"

