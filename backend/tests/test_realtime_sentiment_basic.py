from unittest.mock import AsyncMock, MagicMock, patch
from app.services.dispatcher_alert_service import DispatcherAlertService
import pytest
from app.services.ai.FieldOpsAI.services.realtime_sentiment import (
    RealTimeSentimentScorer,
)

@pytest.mark.asyncio
async def test_realtime_sentiment_scorer():
    db = MagicMock()
    db.query.return_value.filter.return_value.count.return_value = 0

    scorer = RealTimeSentimentScorer(db=db)

    scorer._get_tenant_id = MagicMock(
        return_value="test-tenant"
    )

    result = await scorer.score_reply(
        reply_text="Thank you, the technician fixed my issue. Great service!",
        customer_id="customer-1",
        job_id=1,
        channel="SMS",
        language="en",
        context=[],
    )

    assert result is not None
    assert result.sentiment is not None
    assert 0.0 <= result.confidence <= 1.0

    db.add.assert_called_once()
    db.commit.assert_called_once()
    db.refresh.assert_called_once()
def test_previous_three_messages_are_used():
    db = MagicMock()

    scorer = RealTimeSentimentScorer(db=db)

    # Simulate database result in DESC order:
    # newest message first.
    stored_messages = [
        MagicMock(message="Message 4"),
        MagicMock(message="Message 3"),
        MagicMock(message="Message 2"),
    ]

    (
        db.query.return_value
        .filter.return_value
        .order_by.return_value
        .limit.return_value
        .all.return_value
    ) = stored_messages

    messages = scorer._get_previous_messages(
        customer_id="customer-1",
        job_id=1,
    )

    assert messages == [
        "Message 2",
        "Message 3",
        "Message 4",
    ]

    db.query.return_value.filter.return_value.order_by.return_value.limit.assert_called_once_with(3)
@pytest.mark.asyncio
async def test_automated_reply_is_skipped():
    db = MagicMock()

    scorer = RealTimeSentimentScorer(db=db)

    result = await scorer.score_reply(
        reply_text="Automatic reply: I am currently out of office.",
        customer_id="customer-1",
        job_id=1,
        channel="SMS",
        language="en",
        context=[],
    )

    assert result is None

    db.add.assert_not_called()
    db.commit.assert_not_called()
def test_negative_high_confidence_triggers_alert():
    db = MagicMock()

    scorer = RealTimeSentimentScorer(db=db)

    negative_result = MagicMock(
        sentiment="NEGATIVE",
        confidence=0.95,
    )

    assert scorer._should_alert_negative(
        negative_result
    ) is True
def test_negative_low_confidence_does_not_trigger_alert():
    db = MagicMock()

    scorer = RealTimeSentimentScorer(db=db)

    negative_result = MagicMock(
        sentiment="NEGATIVE",
        confidence=0.75,
    )

    assert scorer._should_alert_negative(
        negative_result
    ) is False

@pytest.mark.asyncio
async def test_negative_sentiment_creates_alert():
    db = MagicMock()

    query = db.query.return_value
    query.filter.return_value.count.return_value = 0

    # Used by audit logging
    query.filter.return_value.order_by.return_value.first.return_value = None

    scorer = RealTimeSentimentScorer(db=db)

    job = MagicMock()
    job.id = 1
    job.tenant_id = "tenant-1"
    job.attempt_count = 0

    db.query.return_value.filter.return_value.first.return_value = job

    negative_result = MagicMock(
        sentiment="NEGATIVE",
        confidence=0.95,
    )

    scorer.sentiment_integration.analyze = MagicMock(
        return_value=negative_result
    )

    await scorer.score_reply(
        reply_text="This service was terrible.",
        customer_id="customer-1",
        job_id=1,
        channel="SMS",
        language="en",
        context=[],
    )

    assert db.add.called
    assert db.commit.called
def test_positive_to_negative_sentiment_shift():
    db = MagicMock()

    scorer = RealTimeSentimentScorer(db=db)

    previous_result = MagicMock(
        sentiment="POSITIVE",
        confidence=0.95,
    )

    scorer.sentiment_integration.analyze = MagicMock(
        return_value=previous_result
    )

    result = scorer._has_sentiment_shift(
        previous_messages=[
            "Thank you, the service was excellent."
        ],
        current_sentiment="NEGATIVE",
    )

    assert result is True
def test_no_shift_when_current_sentiment_is_positive():
    db = MagicMock()

    scorer = RealTimeSentimentScorer(db=db)

    result = scorer._has_sentiment_shift(
        previous_messages=[
            "Thank you, the service was excellent."
        ],
        current_sentiment="POSITIVE",
    )

    assert result is False

@pytest.mark.asyncio
async def test_negative_sentiment_triggers_alert():
    db = MagicMock()
    db.query.return_value.filter.return_value.count.return_value = 0
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

    scorer = RealTimeSentimentScorer(db=db)

    job = MagicMock()
    job.id = 1
    job.tenant_id = "tenant-1"
    job.attempt_count = 0

    db.query.return_value.filter.return_value.first.return_value = job

    negative_result = MagicMock(
        sentiment="NEGATIVE",
        confidence=0.95,
    )

    scorer.sentiment_integration.analyze = MagicMock(
        return_value=negative_result
    )

    await scorer.score_reply(
        reply_text="This service was terrible.",
        customer_id="customer-1",
        job_id=1,
        channel="SMS",
        language="en",
        context=[],
    )

    assert db.add.called
    assert db.commit.called

@pytest.mark.asyncio
async def test_supported_sentiment_channels():
    db = MagicMock()
    db.query.return_value.filter.return_value.count.return_value = 0

    scorer = RealTimeSentimentScorer(db=db)

    result = MagicMock(
        sentiment="POSITIVE",
        confidence=0.95,
    )

    scorer.sentiment_integration.analyze = MagicMock(
        return_value=result
    )

    for channel in ["SMS", "EMAIL", "PORTAL"]:
        response = await scorer.score_reply(
            reply_text="Thank you for the great service.",
            customer_id="customer-1",
            job_id=1,
            channel=channel,
            language="en",
            context=[],
        )

        assert response is not None

    assert scorer.sentiment_integration.analyze.call_count == 3

def test_job_sentiment_summary():
    db = MagicMock()

    scorer = RealTimeSentimentScorer(db=db)

    records = [
        MagicMock(sentiment="POSITIVE"),
        MagicMock(sentiment="NEUTRAL"),
        MagicMock(sentiment="NEGATIVE"),
    ]

    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = records

    summary = scorer.get_job_sentiment_summary(job_id=1)

    assert summary["job_id"] == 1
    assert summary["average_score"] == 0.0
    assert summary["trend"] == "DECLINING"

def test_job_sentiment_trend_improving():
    db = MagicMock()
    scorer = RealTimeSentimentScorer(db=db)

    records = [
        MagicMock(sentiment="NEGATIVE"),
        MagicMock(sentiment="POSITIVE"),
    ]

    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = records

    summary = scorer.get_job_sentiment_summary(job_id=1)

    assert summary["trend"] == "IMPROVING"

def test_job_sentiment_trend_stable():
    db = MagicMock()
    scorer = RealTimeSentimentScorer(db=db)

    records = [
        MagicMock(sentiment="POSITIVE"),
        MagicMock(sentiment="POSITIVE"),
    ]

    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = records

    summary = scorer.get_job_sentiment_summary(job_id=1)

    assert summary["trend"] == "STABLE"
def test_job_sentiment_summary_empty():
    db = MagicMock()
    scorer = RealTimeSentimentScorer(db=db)

    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

    summary = scorer.get_job_sentiment_summary(job_id=1)

    assert summary["job_id"] == 1
    assert summary["average_score"] == 0.0
    assert summary["trend"] == "NEUTRAL"

@pytest.mark.asyncio
async def test_automated_replies_are_skipped():
    db = MagicMock()
    scorer = RealTimeSentimentScorer(db=db)

    analyze_mock = MagicMock()
    scorer.sentiment_integration.analyze = analyze_mock

    automated_messages = [
        "Out of office until Monday.",
        "This is an automatic reply.",
        "Mail delivery failed.",
        "Message could not be delivered.",
    ]

    for message in automated_messages:
        result = await scorer.score_reply(
            reply_text=message,
            customer_id="customer-1",
            job_id=1,
            channel="EMAIL",
            language="en",
            context=[],
        )

        assert result is None

    analyze_mock.assert_not_called()
@pytest.mark.asyncio
async def test_unsupported_sentiment_channel_rejected():
    db = MagicMock()
    scorer = RealTimeSentimentScorer(db=db)

    with pytest.raises(ValueError, match="Unsupported sentiment channel"):
        await scorer.score_reply(
            reply_text="I need help with my service.",
            customer_id="customer-1",
            job_id=1,
            channel="FAX",
            language="en",
            context=[],
        )

def test_negative_confidence_at_threshold_does_not_trigger_alert():
    db = MagicMock()
    scorer = RealTimeSentimentScorer(db=db)

    result = MagicMock(
        sentiment="NEGATIVE",
        confidence=0.8,
    )

    assert scorer._should_alert_negative(result) is False

@pytest.mark.asyncio
async def test_empty_reply_is_skipped():
    db = MagicMock()
    scorer = RealTimeSentimentScorer(db=db)

    analyze_mock = MagicMock()
    scorer.sentiment_integration.analyze = analyze_mock

    for message in ["", "   ", "\n\t"]:
        result = await scorer.score_reply(
            reply_text=message,
            customer_id="customer-1",
            job_id=1,
            channel="SMS",
            language="en",
            context=[],
        )

        assert result is None

    analyze_mock.assert_not_called()
def test_job_sentiment_summary_single_message():
    db = MagicMock()
    scorer = RealTimeSentimentScorer(db=db)

    records = [
        MagicMock(sentiment="NEGATIVE"),
    ]

    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = records

    summary = scorer.get_job_sentiment_summary(job_id=1)

    assert summary["job_id"] == 1
    assert summary["average_score"] == -1.0
    assert summary["trend"] == "NEUTRAL"

def test_job_sentiment_average_score():
    db = MagicMock()
    scorer = RealTimeSentimentScorer(db=db)

    records = [
        MagicMock(sentiment="POSITIVE"),
        MagicMock(sentiment="MIXED"),
        MagicMock(sentiment="NEGATIVE"),
    ]

    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = records

    summary = scorer.get_job_sentiment_summary(job_id=1)

    # (1.0 + 0.5 - 1.0) / 3 = 0.1667
    assert summary["average_score"] == 0.167

def test_get_tenant_id_returns_tenant_id():
    db = MagicMock()

    scorer = RealTimeSentimentScorer(db=db)

    job = MagicMock()
    job.tenant_id = "tenant-123"

    db.query.return_value.filter.return_value.first.return_value = job

    result = scorer._get_tenant_id(job_id=1)

    assert result == "tenant-123"


def test_get_tenant_id_raises_when_job_not_found():
    db = MagicMock()

    scorer = RealTimeSentimentScorer(db=db)

    db.query.return_value.filter.return_value.first.return_value = None

    with pytest.raises(ValueError, match="Job 1 not found"):
        scorer._get_tenant_id(job_id=1)


def test_get_tenant_id_raises_when_tenant_id_missing():
    db = MagicMock()

    scorer = RealTimeSentimentScorer(db=db)

    job = MagicMock()
    job.tenant_id = None

    db.query.return_value.filter.return_value.first.return_value = job

    with pytest.raises(
        ValueError,
        match="does not have a tenant_id",
    ):
        scorer._get_tenant_id(job_id=1)

@pytest.mark.asyncio
async def test_realtime_sentiment_completes_under_3_seconds():
    import time

    db = MagicMock()
    db.query.return_value.filter.return_value.count.return_value = 0

    scorer = RealTimeSentimentScorer(db=db)

    scorer._get_tenant_id = MagicMock(
        return_value="test-tenant"
    )

    # Mock the AI sentiment call so this test measures
    # realtime scoring workflow, not external Groq/network latency.
    scorer.sentiment_integration.analyze = MagicMock(
        return_value=MagicMock(
            sentiment="POSITIVE",
            confidence=0.95,
        )
    )

    start = time.perf_counter()

    result = await scorer.score_reply(
        reply_text="Thank you, the technician fixed my issue.",
        customer_id="customer-1",
        job_id=1,
        channel="SMS",
        language="en",
        context=[],
    )

    elapsed = time.perf_counter() - start

    assert result is not None
    assert elapsed < 3.0

@pytest.mark.asyncio
async def test_escalation_with_customer_notifies_customer_and_manager(monkeypatch):
    db = MagicMock()
    db.query.return_value.filter.return_value.count.return_value = 0

    scorer = RealTimeSentimentScorer(db=db)
    monkeypatch.setattr(
    DispatcherAlertService,
    "trigger_sentiment_alert",
    MagicMock(),
    )
    scorer.escalation_service.create_escalation = MagicMock(
    return_value=MagicMock()
    )

    scorer._get_tenant_id = MagicMock(
        return_value="test-tenant"
    )

    customer = MagicMock()
    customer.phone_number = "9876543210"

    escalation = MagicMock()

    scorer.escalation_service.create_escalation = MagicMock(
        return_value=escalation
    )
    scorer.escalation_service.send_auto_response = AsyncMock()
    scorer.escalation_service.notify_manager = AsyncMock()

    # First query is for the customer.
    # Second query is for the job.
    db.query.return_value.filter.return_value.first.side_effect = [
    MagicMock(tenant_id="tenant-1"),  # Alert job lookup
    customer,                         # Customer lookup
    MagicMock(tenant_id="tenant-1"),  # Retention job lookup
    ]

    result = await scorer.score_reply(
        reply_text="This service was terrible and completely unacceptable.",
        customer_id="customer-1",
        job_id=1,
        channel="SMS",
        language="en",
        context=[],
    )

    assert result is not None

    scorer.escalation_service.create_escalation.assert_called_once()

    scorer.escalation_service.send_auto_response.assert_awaited_once_with(
        customer_phone="9876543210",
        escalation=escalation,
    )

    scorer.escalation_service.notify_manager.assert_awaited_once_with(
        escalation
    )

@pytest.mark.asyncio
async def test_score_reply_when_alert_job_does_not_exist(monkeypatch):
    db = MagicMock()

    scorer = RealTimeSentimentScorer(db=db)

    class FakeResult:
        sentiment = "NEGATIVE"
        confidence = 0.95
        emotion = "anger"
        urgency = "HIGH"
        requires_human = True
        summary = "Customer is unhappy"

    monkeypatch.setattr(
        scorer.sentiment_integration,
        "analyze",
        lambda **kwargs: FakeResult(),
    )

    # Force the alert-job lookup to return no job.
    db.query.return_value.filter.return_value.first.return_value = None

    # Still allow the sentiment record to be saved.
    scorer._get_tenant_id = MagicMock(return_value="tenant-1")

    # Prevent escalation from affecting this branch test.
    scorer.escalation_service.create_escalation = MagicMock(
        return_value=None
    )

    result = await scorer.score_reply(
        reply_text="This is terrible service",
        customer_id="customer-1",
        job_id=999999,
        channel="SMS",
    )

    assert result.sentiment == "NEGATIVE"
    db.add.assert_called_once()
    db.commit.assert_called_once()

@pytest.mark.asyncio
async def test_score_reply_when_escalation_is_created():
    db = MagicMock()

    scorer = RealTimeSentimentScorer(db=db)

    class FakeResult:
        sentiment = "NEGATIVE"
        confidence = 0.95
        emotion = "anger"
        urgency = "HIGH"
        requires_human = True
        summary = "Customer is unhappy"

    scorer.sentiment_integration.analyze = MagicMock(
        return_value=FakeResult()
    )

    scorer._get_tenant_id = MagicMock(
        return_value="tenant-1"
    )

    escalation = MagicMock()

    scorer.escalation_service.create_escalation = MagicMock(
        return_value=escalation
    )

    scorer.escalation_service.notify_manager = AsyncMock()

    customer = MagicMock()
    customer.phone_number = "+919999999999"

    query_mock = MagicMock()
    query_mock.filter.return_value.first.return_value = customer
    db.query.return_value = query_mock

    with patch(
        "app.services.ai.FieldOpsAI.services.realtime_sentiment.DispatcherAlertService.trigger_sentiment_alert"
    ):
        result = await scorer.score_reply(
            reply_text="This is terrible service",
            customer_id="customer-1",
            job_id=1,
            channel="SMS",
        )

    assert result.sentiment == "NEGATIVE"

    scorer.escalation_service.create_escalation.assert_called_once()
    scorer.escalation_service.notify_manager.assert_called_once_with(
        escalation
    )

@pytest.mark.asyncio
async def test_score_reply_when_customer_does_not_exist():
    db = MagicMock()

    scorer = RealTimeSentimentScorer(db=db)

    class FakeResult:
        sentiment = "NEGATIVE"
        confidence = 0.95
        emotion = "anger"
        urgency = "HIGH"
        requires_human = True
        summary = "Customer is unhappy"

    scorer.sentiment_integration.analyze = MagicMock(
        return_value=FakeResult()
    )

    scorer._get_tenant_id = MagicMock(
        return_value="tenant-1"
    )

    escalation = MagicMock()

    scorer.escalation_service.create_escalation = MagicMock(
        return_value=escalation
    )

    scorer.escalation_service.send_auto_response = AsyncMock()
    scorer.escalation_service.notify_manager = AsyncMock()

    # Customer lookup returns None.
    query_mock = MagicMock()
    query_mock.filter.return_value.first.return_value = None
    db.query.return_value = query_mock

    with patch(
        "app.services.ai.FieldOpsAI.services.realtime_sentiment.DispatcherAlertService.trigger_sentiment_alert"
    ):
        result = await scorer.score_reply(
            reply_text="This is terrible service",
            customer_id="customer-1",
            job_id=1,
            channel="SMS",
        )

    assert result.sentiment == "NEGATIVE"

    scorer.escalation_service.create_escalation.assert_called_once()
    scorer.escalation_service.send_auto_response.assert_not_awaited()
    scorer.escalation_service.notify_manager.assert_awaited_once_with(
        escalation
    )
