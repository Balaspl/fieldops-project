import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.services.consumer_error_handler import (
    ConsumeReceipt,
    ConsumerErrorHandler,
    AddErrorHandlingConsumer,
    ConsumerBoundaryHandler,
    Add_error_handling,
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
    _process_error_handling_event_once,
    process_error_handling_event_task,
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
        {"status": "PROCESSED", "consumer": "Add_error_handling", "event_id": "evt_1", "attempt": 1}
    )
    assert success_receipt.is_success is True
    assert bool(success_receipt) is True
    assert success_receipt["consumer"] == "Add_error_handling"
    assert success_receipt["status"] == "PROCESSED"

    failed_receipt = ConsumeReceipt(
        {"status": "FAILED", "consumer": "Add_error_handling", "event_id": "evt_2", "attempt": 1, "error": "test"}
    )
    assert failed_receipt.is_success is False
    assert bool(failed_receipt) is False
    assert failed_receipt["status"] == "FAILED"


# ============================================================================
# 2. Redaction and Classification tests
# ============================================================================

def test_redact_sensitive_data():
    raw_payload = {
        "event_id": "evt_123",
        "tenant_id": "tenant-abc",
        "password": "super-secret-password",
        "api_key": "secret-api-key-999",
        "nested": {
            "token": "bearer-token-val",
            "safe_field": 42,
            "deep": [
                {"secret": "hidden_vault_key", "public": "visible"},
            ],
        },
    }

    redacted = redact_sensitive_data(raw_payload)

    assert redacted["event_id"] == "evt_123"
    assert redacted["tenant_id"] == "tenant-abc"
    assert redacted["password"] == "[REDACTED]"
    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["nested"]["token"] == "[REDACTED]"
    assert redacted["nested"]["safe_field"] == 42
    assert redacted["nested"]["deep"][0]["secret"] == "[REDACTED]"
    assert redacted["nested"]["deep"][0]["public"] == "visible"


def test_classify_error():
    # Transient / retryable error strings
    c1, r1 = classify_error("Connection timed out after 3000ms")
    assert c1 == ErrorClassification.RETRYABLE.value
    assert r1 is True

    c2, r2 = classify_error("503 Service Unavailable")
    assert c2 == ErrorClassification.RETRYABLE.value
    assert r2 is True

    # Transient / retryable exception classes
    c3, r3 = classify_error(ConnectionError("Broker connection dropped"))
    assert c3 == ErrorClassification.RETRYABLE.value
    assert r3 is True

    c4, r4 = classify_error(TimeoutError("Read operation timed out"))
    assert c4 == ErrorClassification.RETRYABLE.value
    assert r4 is True

    # Terminal error strings and exceptions
    c5, r5 = classify_error("Invalid json syntax at line 1")
    assert c5 == ErrorClassification.TERMINAL.value
    assert r5 is False

    c6, r6 = classify_error(ValueError("Invalid argument: status not allowed"))
    assert c6 == ErrorClassification.TERMINAL.value
    assert r6 is False

    c7, r7 = classify_error(KeyError("missing_field"))
    assert c7 == ErrorClassification.TERMINAL.value
    assert r7 is False


# ============================================================================
# 3. Aliases and Instantiation
# ============================================================================

def test_aliases_and_defaults(fake_redis):
    handler = ConsumerErrorHandler(redis_client=fake_redis)
    assert handler.CONSUMER_NAME == "Add_error_handling"
    assert handler.topic == "fieldops.events"
    assert handler.group_id == "fieldops-error-handling"
    assert handler.max_retries == 3
    assert handler.dlq_key == "consumer:dlq"

    assert AddErrorHandlingConsumer is ConsumerErrorHandler
    assert ConsumerBoundaryHandler is ConsumerErrorHandler
    assert Add_error_handling is ConsumerErrorHandler


# ============================================================================
# 4. Primary Success Path
# ============================================================================

@pytest.mark.asyncio
async def test_consumer_primary_success_path_dict(fake_redis, fake_consumer_manager):
    consumer = ConsumerErrorHandler(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )

    event_id = "evt_01JEXAMPLE"
    payload = {
        "event_id": event_id,
        "tenant_id": "tenant-001",
        "schema_version": 1,
        "event_type": "job_created",
        "job_id": "JOB-123",
    }

    receipt = await consumer.process_event(payload, attempt=1)

    assert receipt["status"] == "PROCESSED"
    assert receipt["consumer"] == "Add_error_handling"
    assert receipt["event_id"] == event_id
    assert receipt["attempt"] == 1
    assert bool(receipt) is True

    # Check idempotency marker set in Redis
    assert fake_redis.get(f"consumer_error_handling:event_processed:{event_id}") == "1"


@pytest.mark.asyncio
async def test_consumer_primary_success_path_json_string(fake_redis, fake_consumer_manager):
    consumer = ConsumerErrorHandler(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )

    event_id = "evt_json_str_001"
    raw_json = json.dumps({
        "event_id": event_id,
        "tenant_id": "tenant-002",
        "schema_version": 1,
        "event_type": "dispatch_scheduled",
    })

    receipt = await consumer.process_event(raw_json, attempt=1)

    assert receipt["status"] == "PROCESSED"
    assert receipt["consumer"] == "Add_error_handling"
    assert receipt["event_id"] == event_id
    assert receipt["attempt"] == 1


@pytest.mark.asyncio
async def test_consumer_primary_success_path_envelope(fake_redis, fake_consumer_manager):
    consumer = ConsumerErrorHandler(
        consumer_manager=fake_consumer_manager,
        redis_client=fake_redis,
    )

    event_id = "evt_env_001"
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
    assert receipt["consumer"] == "Add_error_handling"
    assert receipt["event_id"] == event_id
    assert receipt["attempt"] == 1


# ============================================================================
# 5. Malformed Messages & Encodings (Preventing Crashes)
# ============================================================================

@pytest.mark.asyncio
async def test_malformed_json_string_does_not_crash(fake_redis):
    consumer = ConsumerErrorHandler(redis_client=fake_redis)

    malformed = "{ broken json: [1, 2, "
    receipt = await consumer.process_event(malformed, attempt=1)

    assert receipt["status"] == "FAILED"
    assert receipt["consumer"] == "Add_error_handling"
    assert receipt["event_id"] == "unknown"
    assert receipt["error_type"] == "JSONDecodeError"
    assert receipt["error_classification"] == "TERMINAL"
    assert receipt["retryable"] is False
    assert bool(receipt) is False

    # Verify DLQ received entry
    dlq_items = fake_redis.lrange("consumer:dlq", 0, -1)
    assert len(dlq_items) == 1
    dlq_data = json.loads(dlq_items[0])
    assert dlq_data["error_type"] == "JSONDecodeError"
    assert dlq_data["consumer"] == "Add_error_handling"


@pytest.mark.asyncio
async def test_malformed_bytes_encoding_does_not_crash(fake_redis):
    consumer = ConsumerErrorHandler(redis_client=fake_redis)

    # Invalid non-UTF-8 byte sequence
    bad_bytes = b"\xff\xfe\xfa\x80"
    receipt = await consumer.process_event(bad_bytes, attempt=1)

    assert receipt["status"] == "FAILED"
    assert receipt["consumer"] == "Add_error_handling"
    assert receipt["error_type"] == "UnicodeDecodeError"
    assert receipt["error_classification"] == "TERMINAL"
    assert receipt["retryable"] is False

    dlq_items = fake_redis.lrange("consumer:dlq", 0, -1)
    assert len(dlq_items) == 1
    dlq_data = json.loads(dlq_items[0])
    assert dlq_data["error_type"] == "UnicodeDecodeError"


@pytest.mark.asyncio
async def test_unsupported_message_type_does_not_crash(fake_redis):
    consumer = ConsumerErrorHandler(redis_client=fake_redis)

    receipt = await consumer.process_event(1234567, attempt=1)

    assert receipt["status"] == "FAILED"
    assert receipt["consumer"] == "Add_error_handling"
    assert receipt["error_type"] == "TypeError"
    assert receipt["error_classification"] == "TERMINAL"
    assert receipt["retryable"] is False

    dlq_items = fake_redis.lrange("consumer:dlq", 0, -1)
    assert len(dlq_items) == 1


# ============================================================================
# 6. Authorization and Domain Validation Errors
# ============================================================================

@pytest.mark.asyncio
async def test_unauthorized_topic_rejected(fake_redis):
    consumer = ConsumerErrorHandler(redis_client=fake_redis)

    payload = {
        "event_id": "evt_unauth_001",
        "tenant_id": "tenant-001",
        "schema_version": 1,
        "topic": "unauthorized.internal.secrets",
    }

    receipt = await consumer.process_event(payload, attempt=1)

    assert receipt["status"] == "FAILED"
    assert receipt["consumer"] == "Add_error_handling"
    assert receipt["error_type"] == "TopicAuthorizationFailedError"
    assert receipt["error_classification"] == "TERMINAL"
    assert receipt["retryable"] is False

    dlq_items = fake_redis.lrange("consumer:dlq", 0, -1)
    assert len(dlq_items) == 1
    dlq_data = json.loads(dlq_items[0])
    assert "Topic 'unauthorized.internal.secrets' is not authorized" in dlq_data["error"]


@pytest.mark.asyncio
async def test_missing_required_fields_fails_validation(fake_redis):
    consumer = ConsumerErrorHandler(redis_client=fake_redis)

    # Missing event_id, tenant_id, schema_version
    invalid_payload = {
        "event_type": "job_created",
        "data": "some-data",
    }

    receipt = await consumer.process_event(invalid_payload, attempt=1)

    assert receipt["status"] == "FAILED"
    assert receipt["consumer"] == "Add_error_handling"
    assert receipt["error_type"] == "ValidationError"
    assert receipt["error_classification"] == "TERMINAL"
    assert receipt["retryable"] is False
    assert "Missing required fields" in receipt["error"]

    dlq_items = fake_redis.lrange("consumer:dlq", 0, -1)
    assert len(dlq_items) == 1


@pytest.mark.asyncio
async def test_forbidden_sensitive_keys_rejected_and_redacted(fake_redis):
    consumer = ConsumerErrorHandler(redis_client=fake_redis)

    payload = {
        "event_id": "evt_sensitive_001",
        "tenant_id": "tenant-001",
        "schema_version": 1,
        "password": "plain-text-pwd-12345",
    }

    receipt = await consumer.process_event(payload, attempt=1)

    assert receipt["status"] == "FAILED"
    assert receipt["consumer"] == "Add_error_handling"
    assert receipt["error_type"] == "SecurityPolicyError"
    assert receipt["error_classification"] == "TERMINAL"
    assert receipt["retryable"] is False

    # Check DLQ does not leak plaintext password
    dlq_items = fake_redis.lrange("consumer:dlq", 0, -1)
    assert len(dlq_items) == 1
    dlq_str = dlq_items[0]
    assert "plain-text-pwd-12345" not in dlq_str


# ============================================================================
# 7. Downstream Handlers, Retries, and DLQ Routing
# ============================================================================

@pytest.mark.asyncio
async def test_downstream_sync_handler_success(fake_redis):
    processed = []

    def sync_handler(msg):
        processed.append(msg["event_id"])
        return {"ok": True}

    consumer = ConsumerErrorHandler(redis_client=fake_redis, handler=sync_handler)

    receipt = await consumer.process_event(
        {"event_id": "evt_sync_1", "tenant_id": "tenant-1", "schema_version": 1},
        attempt=1,
    )

    assert receipt["status"] == "PROCESSED"
    assert receipt["consumer"] == "Add_error_handling"
    assert len(processed) == 1
    assert processed[0] == "evt_sync_1"


@pytest.mark.asyncio
async def test_downstream_async_handler_success(fake_redis):
    processed = []

    async def async_handler(msg):
        processed.append(msg["event_id"])
        return {"ok": True}

    consumer = ConsumerErrorHandler(redis_client=fake_redis, handler=async_handler)

    receipt = await consumer.process_event(
        {"event_id": "evt_async_1", "tenant_id": "tenant-1", "schema_version": 1},
        attempt=1,
    )

    assert receipt["status"] == "PROCESSED"
    assert receipt["consumer"] == "Add_error_handling"
    assert len(processed) == 1
    assert processed[0] == "evt_async_1"


@pytest.mark.asyncio
async def test_transient_dependency_failure_is_retryable_before_max_retries(fake_redis):
    def failing_handler(msg):
        raise ConnectionError("Database cluster unavailable 503")

    consumer = ConsumerErrorHandler(
        redis_client=fake_redis,
        handler=failing_handler,
        max_retries=3,
    )

    payload = {"event_id": "evt_retry_1", "tenant_id": "tenant-1", "schema_version": 1}

    # Attempt 1: should be marked retryable, NOT in DLQ yet
    receipt1 = await consumer.process_event(payload, attempt=1)
    assert receipt1["status"] == "FAILED"
    assert receipt1["error_classification"] == "RETRYABLE"
    assert receipt1["retryable"] is True
    assert fake_redis.lrange("consumer:dlq", 0, -1) == []

    # Attempt 2: still retryable, NOT in DLQ yet
    receipt2 = await consumer.process_event(payload, attempt=2)
    assert receipt2["status"] == "FAILED"
    assert receipt2["error_classification"] == "RETRYABLE"
    assert receipt2["retryable"] is True
    assert fake_redis.lrange("consumer:dlq", 0, -1) == []

    # Attempt 3: retries exhausted -> retryable is False, pushed to DLQ!
    receipt3 = await consumer.process_event(payload, attempt=3)
    assert receipt3["status"] == "FAILED"
    assert receipt3["retryable"] is False
    dlq_items = fake_redis.lrange("consumer:dlq", 0, -1)
    assert len(dlq_items) == 1
    assert "Database cluster unavailable" in dlq_items[0]


@pytest.mark.asyncio
async def test_terminal_exception_in_handler_routes_to_dlq_immediately(fake_redis):
    def terminal_handler(msg):
        raise ValueError("Invalid domain logic calculation: division by zero or invalid state")

    consumer = ConsumerErrorHandler(
        redis_client=fake_redis,
        handler=terminal_handler,
        max_retries=3,
    )

    payload = {"event_id": "evt_term_1", "tenant_id": "tenant-1", "schema_version": 1}

    # Attempt 1: immediate DLQ push because error is TERMINAL
    receipt = await consumer.process_event(payload, attempt=1)
    assert receipt["status"] == "FAILED"
    assert receipt["error_classification"] == "TERMINAL"
    assert receipt["retryable"] is False

    dlq_items = fake_redis.lrange("consumer:dlq", 0, -1)
    assert len(dlq_items) == 1
    assert "Invalid domain logic calculation" in dlq_items[0]


@pytest.mark.asyncio
async def test_downstream_handler_returning_failed_dict(fake_redis):
    def dict_failing_handler(msg):
        return {"status": "FAILED", "error": "upstream service 503 unavailable"}

    consumer = ConsumerErrorHandler(
        redis_client=fake_redis,
        handler=dict_failing_handler,
        max_retries=3,
    )

    payload = {"event_id": "evt_dict_fail_1", "tenant_id": "tenant-1", "schema_version": 1}

    receipt = await consumer.process_event(payload, attempt=1)
    assert receipt["status"] == "FAILED"
    assert receipt["error_classification"] == "RETRYABLE"
    assert receipt["retryable"] is True


# ============================================================================
# 8. Idempotency Handling
# ============================================================================

@pytest.mark.asyncio
async def test_idempotency_duplicate_skips_handler(fake_redis):
    call_count = 0

    def counter_handler(msg):
        nonlocal call_count
        call_count += 1
        return {"ok": True}

    consumer = ConsumerErrorHandler(
        redis_client=fake_redis,
        handler=counter_handler,
    )

    payload = {
        "event_id": "evt_idemp_001",
        "tenant_id": "tenant-1",
        "schema_version": 1,
    }

    # First execution
    receipt1 = await consumer.process_event(payload, attempt=1)
    assert receipt1["status"] == "PROCESSED"
    assert receipt1.get("idempotent_duplicate") is not True
    assert call_count == 1

    # Second execution (duplicate)
    receipt2 = await consumer.process_event(payload, attempt=1)
    assert receipt2["status"] == "PROCESSED"
    assert receipt2["idempotent_duplicate"] is True
    # Handler must NOT have been called a second time
    assert call_count == 1


# ============================================================================
# 9. wrap_handler Decorator
# ============================================================================

@pytest.mark.asyncio
async def test_wrap_handler_interception(fake_redis):
    def risky_downstream(payload):
        if payload.get("should_fail"):
            raise RuntimeError("Database connection timed out")
        return {"done": True}

    handler = ConsumerErrorHandler(redis_client=fake_redis)
    safe_func = handler.wrap_handler(risky_downstream)

    # Success call
    ok_receipt = await safe_func({
        "event_id": "evt_wrap_1",
        "tenant_id": "tenant-1",
        "schema_version": 1,
        "should_fail": False,
    })
    assert ok_receipt["status"] == "PROCESSED"
    assert ok_receipt["consumer"] == "Add_error_handling"

    # Failing call
    fail_receipt = await safe_func({
        "event_id": "evt_wrap_2",
        "tenant_id": "tenant-1",
        "schema_version": 1,
        "should_fail": True,
    })
    assert fail_receipt["status"] == "FAILED"
    assert fail_receipt["error_classification"] == "RETRYABLE"


# ============================================================================
# 10. Lifecycle Context Manager
# ============================================================================

@pytest.mark.asyncio
async def test_lifecycle_methods(fake_consumer_manager):
    consumer = ConsumerErrorHandler(
        consumer_manager=fake_consumer_manager,
    )

    async with consumer:
        fake_consumer_manager.start.assert_awaited_once()

    fake_consumer_manager.stop.assert_awaited_once()


# ============================================================================
# 11. Celery Tasks and Helpers
# ============================================================================

def test_process_error_handling_event_once_helper(fake_redis):
    # Missing event_id
    bad_res = _process_error_handling_event_once(
        redis=fake_redis,
        event_payload={"tenant_id": "t1"},
        attempt=1,
    )
    assert bad_res["status"] == "FAILED"
    assert bad_res["consumer"] == "Add_error_handling"

    # Valid payload
    payload = {
        "event_id": "evt_celery_001",
        "tenant_id": "tenant-celery",
        "schema_version": 1,
    }
    good_res = _process_error_handling_event_once(
        redis=fake_redis,
        event_payload=payload,
        attempt=1,
    )
    assert good_res["status"] == "PROCESSED"
    assert good_res["consumer"] == "Add_error_handling"
    assert good_res["event_id"] == "evt_celery_001"

    # Duplicate call
    dup_res = _process_error_handling_event_once(
        redis=fake_redis,
        event_payload=payload,
        attempt=1,
    )
    assert dup_res["status"] == "PROCESSED"
    assert dup_res["idempotent_duplicate"] is True


def test_process_error_handling_event_task(fake_redis):
    with patch("app.tasks.get_redis_client", return_value=fake_redis):
        payload = {
            "event_id": "evt_celery_task_001",
            "tenant_id": "tenant-celery",
            "schema_version": 1,
        }
        res = process_error_handling_event_task(payload, attempt=1)
        assert res["status"] == "PROCESSED"
        assert res["consumer"] == "Add_error_handling"

