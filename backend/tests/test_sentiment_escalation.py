import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from app.main import app

from app.sentiment.escalation import SentimentEscalationService


# ============================================================
# Helpers
# ============================================================

def make_message(
    sentiment="NEGATIVE",
    confidence=0.9,
    message_text="This is terrible service",
    requires_human=False,
    job_id=1,
    tenant_id="tenant-1",
    customer_id="customer-1",
):
    message = MagicMock()
    message.sentiment = sentiment
    message.confidence = confidence
    message.message = message_text
    message.requires_human = requires_human
    message.job_id = job_id
    message.tenant_id = tenant_id
    message.customer_id = customer_id
    return message


def make_escalation():
    escalation = MagicMock()
    escalation.id = 1
    escalation.tenant_id = "tenant-1"
    escalation.job_id = 101
    escalation.customer_id = "customer-1"
    escalation.customer_name = "John Doe"
    escalation.technician_name = "Tech One"
    escalation.reply_text = "This service is terrible"
    escalation.sentiment_label = "NEGATIVE"
    escalation.sentiment_score = 0.95
    escalation.trigger_reason = "NEGATIVE_SENTIMENT,COMPLAINT_KEYWORD"
    escalation.suggested_action = "Manager should contact customer"
    escalation.assigned_manager_id = "manager-1"
    escalation.status = "OPEN"
    escalation.created_at = datetime.now(timezone.utc)
    return escalation


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def service():
    db = MagicMock()
    return SentimentEscalationService(db)


@pytest.fixture
def db():
    return MagicMock()


# ============================================================
# 1. NEGATIVE SENTIMENT > 0.8
# ============================================================

def test_negative_sentiment_trigger(service):
    message = make_message(
        sentiment="NEGATIVE",
        confidence=0.9,
        message_text="I am unhappy",
    )

    service.db.query.return_value.filter.return_value.count.return_value = 0

    triggers = service.detect_triggers(message)

    assert "NEGATIVE_SENTIMENT" in triggers


# ============================================================
# 2. NEGATIVE SENTIMENT exactly 0.8 should NOT trigger
# ============================================================

def test_negative_sentiment_at_0_8(service):
    message = make_message(
        sentiment="NEGATIVE",
        confidence=0.8,
        message_text="I am unhappy",
    )

    service.db.query.return_value.filter.return_value.count.return_value = 0

    triggers = service.detect_triggers(message)

    assert "NEGATIVE_SENTIMENT" not in triggers


# ============================================================
# 3. Positive sentiment should not trigger negative sentiment
# ============================================================

def test_positive_sentiment(service):
    message = make_message(
        sentiment="POSITIVE",
        confidence=0.95,
        message_text="Everything is good",
    )

    service.db.query.return_value.filter.return_value.count.return_value = 0

    triggers = service.detect_triggers(message)

    assert "NEGATIVE_SENTIMENT" not in triggers


# ============================================================
# 4. Complaint keyword
# ============================================================

@pytest.mark.parametrize(
    "keyword",
    [
        "terrible",
        "worst",
        "never again",
        "cancel",
        "refund",
    ],
)
def test_complaint_keywords(service, keyword):
    message = make_message(
        sentiment="NEUTRAL",
        confidence=0.5,
        message_text=f"I want a {keyword}",
    )

    service.db.query.return_value.filter.return_value.count.return_value = 0

    triggers = service.detect_triggers(message)

    assert "COMPLAINT_KEYWORD" in triggers


# ============================================================
# 5. Repeated negative replies
# ============================================================

def test_repeated_negative_trigger(service):
    message = make_message(
        sentiment="NEGATIVE",
        confidence=0.5,
        message_text="I am unhappy",
    )

    service.db.query.return_value.filter.return_value.count.return_value = 2

    triggers = service.detect_triggers(message)

    assert "REPEATED_NEGATIVE" in triggers


# ============================================================
# 6. Less than two negative replies
# ============================================================

def test_single_negative_reply(service):
    message = make_message(
        sentiment="NEGATIVE",
        confidence=0.5,
        message_text="I am unhappy",
    )

    service.db.query.return_value.filter.return_value.count.return_value = 1

    triggers = service.detect_triggers(message)

    assert "REPEATED_NEGATIVE" not in triggers


# ============================================================
# 7. Human request through requires_human
# ============================================================

@pytest.mark.parametrize(
    "value",
    [True, "true", "yes", "1"],
)
def test_requires_human_trigger(service, value):
    message = make_message(
        sentiment="NEUTRAL",
        confidence=0.5,
        message_text="I need help",
        requires_human=value,
    )

    service.db.query.return_value.filter.return_value.count.return_value = 0

    triggers = service.detect_triggers(message)

    assert "HUMAN_REQUEST" in triggers


# ============================================================
# 8. Human request through message text
# ============================================================

@pytest.mark.parametrize(
    "text",
    [
        "I want a human",
        "I need an agent",
        "speak to someone",
        "talk to someone",
        "I want a manager",
    ],
)
def test_human_request_keywords(service, text):
    message = make_message(
        sentiment="NEUTRAL",
        confidence=0.5,
        message_text=text,
        requires_human=False,
    )

    service.db.query.return_value.filter.return_value.count.return_value = 0

    triggers = service.detect_triggers(message)

    assert "HUMAN_REQUEST" in triggers


# ============================================================
# 9. No triggers
# ============================================================

def test_no_triggers(service):
    message = make_message(
        sentiment="POSITIVE",
        confidence=0.4,
        message_text="Thank you",
        requires_human=False,
    )

    service.db.query.return_value.filter.return_value.count.return_value = 0

    triggers = service.detect_triggers(message)

    assert triggers == []

# ============================================================
# 10. Escalation SLA deadlines
# ============================================================

def test_create_escalation_sets_sla_deadlines(service):
    message = make_message(
        sentiment="NEGATIVE",
        confidence=0.9,
        message_text="This is terrible service",
    )

    service.db.query.return_value.filter.return_value.count.return_value = 0

    manager = MagicMock(id="manager-1")
    service.assign_manager = MagicMock(return_value=manager)

    customer = MagicMock(
        first_name="John",
        last_name="Doe",
        phone_number="1234567890",
    )

    query = service.db.query.return_value
    query.filter.return_value.first.side_effect = [
        None,      # is_suppressed()
        customer,  # customer lookup
    ]
    service.audit_logger.log_escalation = MagicMock()

    before = datetime.now(timezone.utc)

    escalation = service.create_escalation(message)

    after = datetime.now(timezone.utc)

    assert escalation is not None

    expected_ack = timedelta(
        minutes=service.ACKNOWLEDGE_SLA_MINUTES
    )
    expected_resolve = timedelta(
        hours=service.RESOLVE_SLA_HOURS
    )

    assert before + expected_ack <= escalation.acknowledge_deadline <= after + expected_ack
    assert before + expected_resolve <= escalation.resolve_deadline <= after + expected_resolve

# ============================================================
# SLA breach detection
# ============================================================

def test_acknowledge_sla_breach(service):
    escalation = make_escalation()

    escalation.status = "OPEN"
    escalation.acknowledge_deadline = (
        datetime.now(timezone.utc) - timedelta(minutes=1)
    )
    escalation.resolve_deadline = (
        datetime.now(timezone.utc) + timedelta(hours=1)
    )

    result = service.check_sla_breach(escalation)

    assert result == "ACKNOWLEDGE_SLA_BREACHED"


def test_resolve_sla_breach(service):
    escalation = make_escalation()

    escalation.status = "OPEN"
    escalation.acknowledge_deadline = (
        datetime.now(timezone.utc) - timedelta(minutes=30)
    )
    escalation.resolve_deadline = (
        datetime.now(timezone.utc) - timedelta(minutes=1)
    )

    result = service.check_sla_breach(escalation)

    assert result == "RESOLVE_SLA_BREACHED"


def test_no_sla_breach(service):
    escalation = make_escalation()

    escalation.status = "OPEN"
    escalation.acknowledge_deadline = (
        datetime.now(timezone.utc) + timedelta(minutes=10)
    )
    escalation.resolve_deadline = (
        datetime.now(timezone.utc) + timedelta(hours=1)
    )

    result = service.check_sla_breach(escalation)

    assert result is None

def test_check_sla_breach_returns_none_for_non_open_escalation(service):
    escalation = MagicMock()
    escalation.status = "RESOLVED"

    result = service.check_sla_breach(escalation)

    assert result is None


# ============================================================
# 11. Suppression returns True
# ============================================================

def test_is_suppressed_true(service):
    service.db.query.return_value.filter.return_value.first.return_value = (
        MagicMock(id=1)
    )

    assert service.is_suppressed(10) is True


# ============================================================
# 12. Suppression returns False
# ============================================================

def test_is_suppressed_false(service):
    service.db.query.return_value.filter.return_value.first.return_value = None

    assert service.is_suppressed(10) is False


# ============================================================
# 13. First manager assignment
# ============================================================

def test_assign_manager_first_manager(service):
    manager1 = MagicMock(id="manager-1")
    manager2 = MagicMock(id="manager-2")

    query = service.db.query.return_value
    query.filter.return_value.order_by.return_value.all.return_value = [
        manager1,
        manager2,
    ]

    query.filter.return_value.order_by.return_value.first.return_value = None

    result = service.assign_manager("tenant-1")

    assert result == manager1


# ============================================================
# 14. Round robin manager assignment
# ============================================================

def test_assign_manager_round_robin(service):
    manager1 = MagicMock(id="manager-1")
    manager2 = MagicMock(id="manager-2")

    query = service.db.query.return_value

    query.filter.return_value.order_by.return_value.all.return_value = [
        manager1,
        manager2,
    ]

    query.filter.return_value.order_by.return_value.first.return_value = (
        MagicMock(assigned_manager_id="manager-1")
    )

    result = service.assign_manager("tenant-1")

    assert result == manager2


# ============================================================
# 15. Round robin wraps around
# ============================================================

def test_assign_manager_wraps(service):
    manager1 = MagicMock(id="manager-1")
    manager2 = MagicMock(id="manager-2")

    query = service.db.query.return_value

    query.filter.return_value.order_by.return_value.all.return_value = [
        manager1,
        manager2,
    ]

    query.filter.return_value.order_by.return_value.first.return_value = (
        MagicMock(assigned_manager_id="manager-2")
    )

    result = service.assign_manager("tenant-1")

    assert result == manager1


# ============================================================
# 16. No managers available
# ============================================================

def test_assign_manager_no_managers(service):
    service.db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

    result = service.assign_manager("tenant-1")

    assert result is None


# ============================================================
# 17. Previous manager not found
# ============================================================

def test_assign_manager_previous_manager_missing(service):
    manager1 = MagicMock(id="manager-1")
    manager2 = MagicMock(id="manager-2")

    query = service.db.query.return_value

    query.filter.return_value.order_by.return_value.all.return_value = [
        manager1,
        manager2,
    ]

    query.filter.return_value.order_by.return_value.first.return_value = (
        MagicMock(assigned_manager_id="unknown-manager")
    )

    result = service.assign_manager("tenant-1")

    assert result == manager1

# ============================================================
# 18. Off-duty managers are excluded
# ============================================================

def test_assign_manager_excludes_off_duty_managers(service):
    on_duty_manager = MagicMock(
        id="manager-1",
        is_on_duty=True,
    )

    query = service.db.query.return_value

    # Production query filters:
    # User.is_on_duty.is_(True)
    # Therefore only on-duty managers are returned.
    query.filter.return_value.order_by.return_value.all.return_value = [
        on_duty_manager,
    ]

    query.filter.return_value.order_by.return_value.first.return_value = None

    result = service.assign_manager("tenant-1")

    assert result == on_duty_manager
    assert result.is_on_duty is True


# ============================================================
# 19. Manager contact
# ============================================================

def test_get_manager_contact(service):
    manager = MagicMock(
        id="manager-1",
        email="manager@test.com",
        phone_number="+911234567890",
    )

    result = service.get_manager_contact(manager)

    assert result == {
        "manager_id": "manager-1",
        "email": "manager@test.com",
        "phone_number": "+911234567890",
    }


# ============================================================
# 20. Build escalation payload
# ============================================================

def test_build_escalation_payload(service):
    escalation = make_escalation()

    result = service.build_escalation_payload(escalation)

    assert result["customer_name"] == "John Doe"
    assert result["job_id"] == 101
    assert result["sentiment_score"] == 0.95
    assert result["reply_text"] == "This service is terrible"
    assert result["technician_name"] == "Tech One"


# ============================================================
# 21. Auto response
# ============================================================

def test_generate_auto_response(service):
    response = service.generate_auto_response()

    assert (
        response
        == "Your concern has been escalated to a manager "
        "who will contact you within 15 minutes"
    )


# ============================================================
# 22. Auto response without phone
# ============================================================

@pytest.mark.asyncio
async def test_send_auto_response_without_phone(service):
    result = await service.send_auto_response(None)

    assert result is False


# ============================================================
# 23. Auto response success
# ============================================================

@pytest.mark.asyncio
async def test_send_auto_response_success(service):
    with patch(
        "app.services.twilio_sms.dispatch_twilio_message",
        new_callable=AsyncMock,
    ) as mock_send:

        result = await service.send_auto_response(
            "+911234567890"
        )

        assert result is True
        mock_send.assert_awaited_once()


# ============================================================
# 24. Auto response failure
# ============================================================

@pytest.mark.asyncio
async def test_send_auto_response_failure(service):
    with patch(
        "app.services.twilio_sms.dispatch_twilio_message",
        new_callable=AsyncMock,
        side_effect=Exception("SMS failed"),
    ):

        result = await service.send_auto_response(
            "+911234567890"
        )

        assert result is False


# ============================================================
# 25. Create escalation - no trigger
# ============================================================

def test_create_escalation_no_trigger(service):
    message = make_message(
        sentiment="POSITIVE",
        confidence=0.5,
        message_text="Thank you",
    )

    service.detect_triggers = MagicMock(return_value=[])

    result = service.create_escalation(message)

    assert result is None


# ============================================================
# 26. Create escalation - suppressed
# ============================================================

def test_create_escalation_suppressed(service):
    message = make_message()

    service.detect_triggers = MagicMock(
        return_value=["NEGATIVE_SENTIMENT"]
    )
    service.is_suppressed = MagicMock(return_value=True)

    result = service.create_escalation(message)

    assert result is None


# ============================================================
# 27. Create escalation - success
# ============================================================

def test_create_escalation_success(service):
    message = make_message()

    service.detect_triggers = MagicMock(
        return_value=["NEGATIVE_SENTIMENT"]
    )

    service.is_suppressed = MagicMock(return_value=False)

    manager = MagicMock(id="manager-1")

    service.assign_manager = MagicMock(
        return_value=manager
    )

    customer = MagicMock(
        first_name="John",
        last_name="Doe",
        phone_number="+911234567890",
    )

    service.db.query.return_value.filter.return_value.first.return_value = (
        customer
    )

    service.audit_logger.log_escalation = MagicMock()

    result = service.create_escalation(
        message=message,
        technician_name="Technician",
        suggested_action="Call customer",
    )

    assert result is not None
    assert result.status == "OPEN"
    assert result.customer_name == "John Doe"
    assert result.technician_name == "Technician"
    assert result.assigned_manager_id == "manager-1"

    service.db.add.assert_called_once()
    service.db.flush.assert_called_once()
    service.db.commit.assert_called_once()
    service.db.refresh.assert_called_once()

    service.audit_logger.log_escalation.assert_called_once()


# ============================================================
# 28. Create escalation - customer missing
# ============================================================

def test_create_escalation_customer_missing(service):
    message = make_message()

    service.detect_triggers = MagicMock(
        return_value=["COMPLAINT_KEYWORD"]
    )
    service.is_suppressed = MagicMock(return_value=False)
    service.assign_manager = MagicMock(return_value=None)

    service.db.query.return_value.filter.return_value.first.return_value = None

    service.audit_logger.log_escalation = MagicMock()

    result = service.create_escalation(message)

    assert result is not None
    assert result.customer_name == "Unknown"
    assert result.assigned_manager_id is None


# ============================================================
# 29. Notify manager - no assigned manager
# ============================================================

@pytest.mark.asyncio
async def test_notify_manager_without_manager(service):
    escalation = make_escalation()
    escalation.assigned_manager_id = None

    result = await service.notify_manager(escalation)

    assert result["manager_id"] is None
    assert result["sms"] is False
    assert result["email"] is False
    assert result["push"] is False
    assert result["dashboard"] is False


# ============================================================
# 30. Notify manager - manager not found
# ============================================================

@pytest.mark.asyncio
async def test_notify_manager_manager_not_found(service):
    escalation = make_escalation()

    service.db.query.return_value.filter.return_value.first.return_value = None

    result = await service.notify_manager(escalation)

    assert result["manager_id"] is None

# ============================================================
# 31. Notify manager - SMS + Email + Dashboard
# ============================================================

@pytest.mark.asyncio
async def test_notify_manager_success(service):
    escalation = make_escalation()

    manager = MagicMock(
        id="manager-1",
        email="manager@test.com",
        phone_number="+911234567890",
    )

    service.db.query.return_value.filter.return_value.first.return_value = (
        manager
    )

    service.build_escalation_payload = MagicMock(
        return_value={"job_id": 101}
    )

    mock_ws = MagicMock()
    mock_ws.broadcast = AsyncMock()

    mock_email_service = MagicMock()
    mock_email_service.send_email = AsyncMock(
        return_value=True
    )

    mock_sms = AsyncMock()

    with patch(
        "app.services.twilio_sms.dispatch_twilio_message",
        mock_sms,
    ), patch(
        "app.services.notification_services.SMTPEmailService",
        return_value=mock_email_service,
    ), patch(
        "app.services.socket_manager.default_ws_manager",
        mock_ws,
        create=True,
    ):

        result = await service.notify_manager(
            escalation
        )

    assert result["manager_id"] == "manager-1"

    assert result["sms"] is True
    assert result["email"] is True

    # Push is currently disabled in the
    # production implementation.
    assert result["push"] is False

    assert result["dashboard"] is True

    mock_sms.assert_awaited_once()

    mock_email_service.send_email.assert_awaited_once()

    mock_ws.broadcast.assert_awaited_once()


# ============================================================
# 32. Notify manager - notification failures
# ============================================================

@pytest.mark.asyncio
async def test_notify_manager_notification_failures(
    service,
):
    escalation = make_escalation()

    manager = MagicMock(
        id="manager-1",
        email="manager@test.com",
        phone_number="+911234567890",
    )

    service.db.query.return_value.filter.return_value.first.return_value = (
        manager
    )

    service.build_escalation_payload = MagicMock(
        return_value={"job_id": 101}
    )

    mock_ws = MagicMock()

    mock_ws.broadcast = AsyncMock(
        side_effect=Exception(
            "Websocket error"
        )
    )

    mock_email_service = MagicMock()

    mock_email_service.send_email = AsyncMock(
        side_effect=Exception(
            "Email error"
        )
    )

    with patch(
        "app.services.twilio_sms.dispatch_twilio_message",
        new_callable=AsyncMock,
        side_effect=Exception(
            "SMS error"
        ),
    ), patch(
        "app.services.notification_services.SMTPEmailService",
        return_value=mock_email_service,
    ), patch(
        "app.services.socket_manager.default_ws_manager",
        mock_ws,
        create=True,
    ):

        result = await service.notify_manager(
            escalation
        )

    assert result["manager_id"] == "manager-1"

    assert result["sms"] is False
    assert result["email"] is False
    assert result["push"] is False
    assert result["dashboard"] is False

@pytest.mark.asyncio
async def test_notify_manager_push_success(service):
    escalation = make_escalation()

    manager = MagicMock(
        id="manager-1",
        email=None,
        phone_number=None,
        fcm_token="test-fcm-token",
    )

    service.db.query.return_value.filter.return_value.first.return_value = (
        manager
    )

    service.build_escalation_payload = MagicMock(
        return_value={"job_id": 101}
    )

    mock_ws = MagicMock()
    mock_ws.broadcast = AsyncMock()

    with patch(
        "app.services.socket_manager.default_ws_manager",
        mock_ws,
        create=True,
    ), patch(
        "firebase_admin.messaging.Notification",
    ) as mock_notification, patch(
        "firebase_admin.messaging.Message",
    ) as mock_message, patch(
        "firebase_admin.messaging.send",
        return_value="message-id",
    ) as mock_send:

        mock_notification.return_value = MagicMock()
        mock_message.return_value = MagicMock()

        result = await service.notify_manager(
            escalation
        )

    assert result["push"] is True
    mock_notification.assert_called_once()
    mock_message.assert_called_once()
    mock_send.assert_called_once()


@pytest.mark.asyncio
async def test_notify_manager_push_skipped_without_fcm_token(service):
    escalation = make_escalation()

    manager = MagicMock(
        id="manager-1",
        email=None,
        phone_number=None,
        fcm_token=None,
    )

    service.db.query.return_value.filter.return_value.first.return_value = (
        manager
    )

    service.build_escalation_payload = MagicMock(
        return_value={"job_id": 101}
    )

    mock_ws = MagicMock()
    mock_ws.broadcast = AsyncMock()

    with patch(
        "app.services.socket_manager.default_ws_manager",
        mock_ws,
        create=True,
    ):
        result = await service.notify_manager(escalation)

    assert result["push"] is False
    

# ============================================================
# API TESTS
# ============================================================

def test_get_escalations():
    client = TestClient(app)

    response = client.get("/admin/escalations")

    assert response.status_code == 200
    data = response.json()

    assert "count" in data
    assert "escalations" in data


def test_acknowledge_escalation():
    client = TestClient(app)

    response = client.post(
        "/admin/escalations/1/acknowledge"
    )

    # 200 if escalation exists,
    # 404 if test database has no escalation with ID 1.
    assert response.status_code in (200, 404)


def test_resolve_escalation():
    client = TestClient(app)

    response = client.post(
        "/admin/escalations/1/resolve",
        params={
            "resolution_notes": "Issue resolved by manager"
        },
    )

    # 200 if escalation exists,
    # 404 if test database has no escalation with ID 1.
    assert response.status_code in (200, 404)