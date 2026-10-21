import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone
from types import SimpleNamespace
from pydantic import ValidationError
import unittest
from app.models.organization import Organization
from app.services.ai.FieldOpsAI.schemas.communication_configuration import CommunicationMessageCategory, CommunicationChannelState, DeliveryDecision
from app.services.ai.FieldOpsAI.schemas.customer_profile import CustomerPreferenceDecision
from app.services.ai.FieldOpsAI.schemas.communication_delivery_policy import CommunicationDeliveryEligibilityDecision
from app.services.ai.FieldOpsAI.services.communication_delivery_policy_service import CommunicationDeliveryPolicyService
from app.services.ai.FieldOpsAI.services.customer_preference_service import CustomerPreferencePersistenceError
from app.models.organization import Organization
import app.services.notification_services as module
from app.services.notification_services import JobStatusEvent, NotificationRouter
from app.services.ai.FieldOpsAI.schemas.communication_configuration import CommunicationChannelDisabledError

# ---------------------------------------------------------
# Fixtures
# ---------------------------------------------------------

@pytest.fixture
def mock_config_service():
    return MagicMock()

@pytest.fixture
def mock_pref_service():
    return MagicMock()

@pytest.fixture
def policy_service(mock_config_service, mock_pref_service):
    return CommunicationDeliveryPolicyService(
        configuration_service=mock_config_service,
        preference_service=mock_pref_service,
    )

# ---------------------------------------------------------
# Service Contract (1-10)
# ---------------------------------------------------------

def test_1_2_supported_channels(policy_service, mock_config_service, mock_pref_service):
    # Setup happy path
    mock_config_service.evaluate_delivery.return_value = DeliveryDecision(
        allowed=True, channel="SMS", state=CommunicationChannelState.ENABLED,
        category=CommunicationMessageCategory.STANDARD, reason_code="GLOBAL_ALLOWED", revision=1
    )
    mock_pref_service.evaluate_channel.return_value = CustomerPreferenceDecision(
        allowed=True, channel="SMS", reason_code="PREF_ALLOWED", source="PROFILE", revision=1
    )
    
    dec_sms = policy_service.evaluate(
        channel="SMS", category=CommunicationMessageCategory.STANDARD,
        recipient_type="CUSTOMER", tenant_id="tenant-1", customer_id="c1"
    )
    assert dec_sms.channel == "SMS"
    
    mock_config_service.evaluate_delivery.return_value = DeliveryDecision(
        allowed=True, channel="EMAIL", state=CommunicationChannelState.ENABLED,
        category=CommunicationMessageCategory.STANDARD, reason_code="GLOBAL_ALLOWED", revision=1
    )
    mock_pref_service.evaluate_channel.return_value = CustomerPreferenceDecision(
        allowed=True, channel="EMAIL", reason_code="PREF_ALLOWED", source="PROFILE", revision=1
    )
    dec_email = policy_service.evaluate(
        channel="EMAIL", category=CommunicationMessageCategory.STANDARD,
        recipient_type="CUSTOMER", tenant_id="tenant-1", customer_id="c1"
    )
    assert dec_email.channel == "EMAIL"

@pytest.mark.parametrize("channel", ["", "PUSH", "IN_APP", "WHATSAPP"])
def test_3_unsupported_channel_rejected(policy_service, channel):
    with pytest.raises(ValidationError):
        policy_service.evaluate(
            channel=channel, category=CommunicationMessageCategory.STANDARD,
            recipient_type="CUSTOMER", tenant_id="tenant-1", customer_id="c1"
        )

@pytest.mark.parametrize("recipient", ["", "UNKNOWN", "CUSTOMER_ADMIN", "carrier-pigeon"])
def test_4_invalid_recipient_type_rejected(policy_service, recipient):
    with pytest.raises(ValidationError):
        policy_service.evaluate(
            channel="SMS", category=CommunicationMessageCategory.STANDARD,
            recipient_type=recipient, tenant_id="tenant-1", customer_id="c1"
        )

def test_5_customer_requires_tenant_id(policy_service, mock_config_service):
    mock_config_service.evaluate_delivery.return_value = DeliveryDecision(
        allowed=True, channel="SMS", state=CommunicationChannelState.ENABLED,
        category=CommunicationMessageCategory.STANDARD, reason_code="GLOBAL_ALLOWED", revision=1
    )
    dec = policy_service.evaluate(
        channel="SMS", category=CommunicationMessageCategory.STANDARD,
        recipient_type="CUSTOMER", tenant_id=None, customer_id="c1"
    )
    assert not dec.allowed
    assert dec.final_reason_code == "CUSTOMER_IDENTITY_REQUIRED"

def test_6_customer_requires_customer_id(policy_service, mock_config_service):
    mock_config_service.evaluate_delivery.return_value = DeliveryDecision(
        allowed=True, channel="SMS", state=CommunicationChannelState.ENABLED,
        category=CommunicationMessageCategory.STANDARD, reason_code="GLOBAL_ALLOWED", revision=1
    )
    dec = policy_service.evaluate(
        channel="SMS", category=CommunicationMessageCategory.STANDARD,
        recipient_type="CUSTOMER", tenant_id="tenant-1", customer_id=None
    )
    assert not dec.allowed
    assert dec.final_reason_code == "CUSTOMER_IDENTITY_REQUIRED"

def test_7_8_tech_system_bypasses_pref(policy_service, mock_config_service, mock_pref_service):
    mock_config_service.evaluate_delivery.return_value = DeliveryDecision(
        allowed=True, channel="SMS", state=CommunicationChannelState.ENABLED,
        category=CommunicationMessageCategory.STANDARD, reason_code="GLOBAL_ALLOWED", revision=1
    )
    
    for rtype in ["TECHNICIAN", "SYSTEM"]:
        dec = policy_service.evaluate(
            channel="SMS", category=CommunicationMessageCategory.STANDARD,
            recipient_type=rtype, tenant_id="tenant-1", customer_id="c1"
        )
        assert dec.allowed
        mock_pref_service.evaluate_channel.assert_not_called()
        
    # Test global block
    mock_config_service.evaluate_delivery.return_value = DeliveryDecision(
        allowed=False, channel="SMS", state=CommunicationChannelState.DISABLED,
        category=CommunicationMessageCategory.STANDARD, reason_code="GLOBAL_BLOCKED", revision=1
    )
    for rtype in ["TECHNICIAN", "SYSTEM"]:
        dec = policy_service.evaluate(
            channel="SMS", category=CommunicationMessageCategory.STANDARD,
            recipient_type=rtype, tenant_id="tenant-1", customer_id="c1"
        )
        assert not dec.allowed

def test_9_10_result_immutable_no_pii(policy_service, mock_config_service, mock_pref_service):
    mock_config_service.evaluate_delivery.return_value = DeliveryDecision(
        allowed=True, channel="SMS", state=CommunicationChannelState.ENABLED,
        category=CommunicationMessageCategory.STANDARD, reason_code="GLOBAL_ALLOWED", revision=1
    )
    mock_pref_service.evaluate_channel.return_value = CustomerPreferenceDecision(
        allowed=True, channel="SMS", reason_code="PREF_ALLOWED", source="PROFILE", revision=1
    )
    dec = policy_service.evaluate(
        channel="SMS", category=CommunicationMessageCategory.STANDARD,
        recipient_type="CUSTOMER", tenant_id="tenant-1", customer_id="c1"
    )
    # Immutable check
    with pytest.raises(ValidationError):
        dec.allowed = False
    
    # No PII check (must not contain tenant_id, customer_id, etc. in its dump)
    dump = dec.model_dump()
    assert "tenant_id" not in dump
    assert "customer_id" not in dump

# ---------------------------------------------------------
# Global Matrix & Override Matrix
# ---------------------------------------------------------

@pytest.mark.parametrize("channel", ["SMS", "EMAIL"])
@pytest.mark.parametrize("state", [
    CommunicationChannelState.ENABLED, 
    CommunicationChannelState.DISABLED, 
    CommunicationChannelState.EMERGENCY_ONLY
])
@pytest.mark.parametrize("category", [
    CommunicationMessageCategory.STANDARD, 
    CommunicationMessageCategory.EMERGENCY
])
def test_global_matrix_various(policy_service, mock_config_service, mock_pref_service, channel, state, category):
    # Simulate config service correctly rejecting based on global rules
    allowed = (state == CommunicationChannelState.ENABLED) or (state == CommunicationChannelState.EMERGENCY_ONLY and category == CommunicationMessageCategory.EMERGENCY)
    mock_config_service.evaluate_delivery.return_value = DeliveryDecision(
        allowed=allowed, channel=channel, state=state,
        category=category, reason_code="GLOBAL_ALLOWED" if allowed else "GLOBAL_BLOCKED", revision=1
    )
    
    mock_pref_service.evaluate_channel.return_value = CustomerPreferenceDecision(
        allowed=True, channel=channel, reason_code="PREF_ALLOWED", source="PROFILE", revision=1
    )
    
    dec = policy_service.evaluate(
        channel=channel, category=category,
        recipient_type="CUSTOMER", tenant_id="tenant-1", customer_id="c1"
    )
    
    assert dec.allowed == allowed

# ---------------------------------------------------------
# Customer Preference Matrix (11-20)
# ---------------------------------------------------------

def test_11_global_allowed_pref_enabled(policy_service, mock_config_service, mock_pref_service):
    mock_config_service.evaluate_delivery.return_value = DeliveryDecision(
        allowed=True, channel="SMS", state=CommunicationChannelState.ENABLED,
        category=CommunicationMessageCategory.STANDARD, reason_code="G", revision=1
    )
    mock_pref_service.evaluate_channel.return_value = CustomerPreferenceDecision(
        allowed=True, channel="SMS", reason_code="P", source="PROFILE", revision=1
    )
    dec = policy_service.evaluate(channel="SMS", category=CommunicationMessageCategory.STANDARD, recipient_type="CUSTOMER", tenant_id="tenant-1", customer_id="c1")
    assert dec.allowed
    assert dec.final_reason_code == "DELIVERY_POLICY_ALLOWED"

def test_12_global_allowed_pref_disabled(policy_service, mock_config_service, mock_pref_service):
    mock_config_service.evaluate_delivery.return_value = DeliveryDecision(
        allowed=True, channel="SMS", state=CommunicationChannelState.ENABLED,
        category=CommunicationMessageCategory.STANDARD, reason_code="G", revision=1
    )
    mock_pref_service.evaluate_channel.return_value = CustomerPreferenceDecision(
        allowed=False, channel="SMS", reason_code="P", source="PROFILE", revision=1
    )
    assert not policy_service.evaluate(channel="SMS", category=CommunicationMessageCategory.STANDARD, recipient_type="CUSTOMER", tenant_id="tenant-1", customer_id="c1").allowed

def test_13_global_blocked_pref_enabled(policy_service, mock_config_service, mock_pref_service):
    mock_config_service.evaluate_delivery.return_value = DeliveryDecision(
        allowed=False, channel="SMS", state=CommunicationChannelState.DISABLED,
        category=CommunicationMessageCategory.STANDARD, reason_code="G", revision=1
    )
    assert not policy_service.evaluate(channel="SMS", category=CommunicationMessageCategory.STANDARD, recipient_type="CUSTOMER", tenant_id="tenant-1", customer_id="c1").allowed

def test_14_global_blocked_does_not_query_pref(policy_service, mock_config_service, mock_pref_service):
    mock_config_service.evaluate_delivery.return_value = DeliveryDecision(
        allowed=False, channel="SMS", state=CommunicationChannelState.DISABLED,
        category=CommunicationMessageCategory.STANDARD, reason_code="G", revision=1
    )
    policy_service.evaluate(channel="SMS", category=CommunicationMessageCategory.STANDARD, recipient_type="CUSTOMER", tenant_id="tenant-1", customer_id="c1")
    mock_pref_service.evaluate_channel.assert_not_called()

def test_15_emergency_does_not_bypass_disabled_pref(policy_service, mock_config_service, mock_pref_service):
    mock_config_service.evaluate_delivery.return_value = DeliveryDecision(
        allowed=True, channel="SMS", state=CommunicationChannelState.ENABLED,
        category=CommunicationMessageCategory.EMERGENCY, reason_code="G", revision=1
    )
    mock_pref_service.evaluate_channel.return_value = CustomerPreferenceDecision(
        allowed=False, channel="SMS", reason_code="P", source="PROFILE", revision=1
    )
    assert not policy_service.evaluate(channel="SMS", category=CommunicationMessageCategory.EMERGENCY, recipient_type="CUSTOMER", tenant_id="tenant-1", customer_id="c1").allowed

def test_18_pref_service_failure_blocks(policy_service, mock_config_service, mock_pref_service):
    mock_config_service.evaluate_delivery.return_value = DeliveryDecision(
        allowed=True, channel="SMS", state=CommunicationChannelState.ENABLED,
        category=CommunicationMessageCategory.STANDARD, reason_code="G", revision=1
    )
    mock_pref_service.evaluate_channel.side_effect = CustomerPreferencePersistenceError("DB Down")
    dec = policy_service.evaluate(channel="SMS", category=CommunicationMessageCategory.STANDARD, recipient_type="CUSTOMER", tenant_id="tenant-1", customer_id="c1")
    assert not dec.allowed
    assert dec.final_reason_code == "CUSTOMER_PREFERENCE_UNAVAILABLE"

# Missing profile compatibility is managed inside the PreferenceService, which returns allowed=True, source=COMPATIBILITY
def test_16_17_missing_profile_compatibility(policy_service, mock_config_service, mock_pref_service):
    mock_config_service.evaluate_delivery.return_value = DeliveryDecision(
        allowed=True, channel="SMS", state=CommunicationChannelState.ENABLED,
        category=CommunicationMessageCategory.STANDARD, reason_code="G", revision=1
    )
    mock_pref_service.evaluate_channel.return_value = CustomerPreferenceDecision(
        allowed=True, channel="SMS", reason_code="COMPAT_ALLOWED", source="COMPATIBILITY_DEFAULT", revision=0
    )
    dec = policy_service.evaluate(channel="SMS", category=CommunicationMessageCategory.STANDARD, recipient_type="CUSTOMER", tenant_id="tenant-1", customer_id="c1")
    assert dec.allowed
    assert dec.final_reason_code == "DELIVERY_POLICY_ALLOWED"

# ---------------------------------------------------------
# Integrations and Execution Tests
# ---------------------------------------------------------

def get_fake_router():
    sms_mock = AsyncMock(return_value={"sent": 1, "failed": 0, "blocked": 0, "blocked_reasons": {}, "delivery_ids": [1]})
    email_mock = AsyncMock(return_value=True)
    router = NotificationRouter(
        fcm_service=AsyncMock(),
        sms_service=sms_mock,
        email_service=email_mock,
        ws_manager=MagicMock(),
        redis_client=MagicMock(),
        communication_integration=MagicMock(),
    )
    router._generate_safe_communication = AsyncMock(
        return_value=SimpleNamespace(decision=SimpleNamespace(
            message="Approved", subject="Approved", title="Approved",
            output=SimpleNamespace(text="Approved", subject="Approved", title="Approved", body="Approved", html_body="Approved", text_body="Approved")
        ))
    )
    return router, sms_mock, email_mock

def get_fallback_router():
    from app.services.ai.integrations.communication_integration import CommunicationIntegration
    from app.services.ai.FieldOpsAI.services.communication_service import CommunicationService
    from sqlalchemy.orm import Session
    
    sms_mock = AsyncMock(return_value={"sent": 1, "failed": 0, "blocked": 0, "blocked_reasons": {}, "delivery_ids": [1]})
    email_mock = AsyncMock(return_value=True)
    
    def failing_service_factory(**kwargs):
        agent_mock = MagicMock()
        agent_mock.generate.side_effect = Exception("AI Failure")
        kwargs["agent"] = agent_mock
        return CommunicationService(**kwargs)
        
    fake_session_factory = MagicMock(return_value=MagicMock(spec=Session))
    
    integration = CommunicationIntegration(
        session_factory=fake_session_factory,
        redis_client=MagicMock(),
        service_factory=failing_service_factory,
    )
    
    router = NotificationRouter(
        fcm_service=AsyncMock(),
        sms_service=sms_mock,
        email_service=email_mock,
        ws_manager=MagicMock(),
        redis_client=MagicMock(),
        communication_integration=integration,
    )
    
    return router, sms_mock, email_mock

def _make_event():
    return JobStatusEvent(
        job_id="1", tenant_id="tenant-1", from_status="CREATED", to_status="ASSIGNED",
        actor_id="actor-1", actor_role="dispatcher", reason=None, timestamp=datetime.now(timezone.utc),
        job_title="Repair", job_location="Test location", technician_id="tech-1",
        technician_name="Technician", customer_id="customer-1", customer_name="Customer",
        customer_phone="+15555550100", customer_email="customer@example.com",
        eta=None, notification_channels=[]
    )

def test_30_31_43_44_sms_email_integration(monkeypatch):
    router, sms_mock, email_mock = get_fake_router()

    import app.services.twilio_sms as twilio_module
    dispatch_mock = MagicMock(
        return_value="SM_test_message"
    )

    monkeypatch.setattr(
        twilio_module,
        "TWILIO_ACCOUNT_SID",
        "AC_test_account",
    )

    monkeypatch.setattr(
        twilio_module,
        "dispatch_twilio_message",
        dispatch_mock,
    )
    # We mock _evaluate_customer_delivery_policy to simulate global allowed/blocked
    # This proves the boundary respects the decision.
    dec_allowed = CommunicationDeliveryEligibilityDecision(
        allowed=True, channel="SMS", category=CommunicationMessageCategory.STANDARD, recipient_type="CUSTOMER",
        global_allowed=True, global_state=CommunicationChannelState.ENABLED, global_reason_code="G", global_revision=1,
        preference_applied=True, preference_allowed=True, preference_reason_code="P", preference_source="P", preference_revision=1,
        final_reason_code="ALLOWED"
    )
    router._evaluate_customer_delivery_policy = MagicMock(return_value=dec_allowed)
    
    # Test SMS Allowed
    res = asyncio.run(router._send_sms(_make_event(), "customer", {}, "job_assigned", category=CommunicationMessageCategory.STANDARD))
    assert res is True
    router._evaluate_customer_delivery_policy.assert_called_with(
        event=unittest.mock.ANY, channel="SMS", category=CommunicationMessageCategory.STANDARD
    )
    dispatch_mock.assert_called_once_with(body="Approved",to_phone="+15555550100",)
    dispatch_mock.reset_mock()
    # Test SMS Blocked
    dec_blocked = CommunicationDeliveryEligibilityDecision(
        allowed=False, channel="SMS", category=CommunicationMessageCategory.STANDARD, recipient_type="CUSTOMER",
        global_allowed=False, global_state=CommunicationChannelState.DISABLED, global_reason_code="G", global_revision=1,
        preference_applied=False, preference_allowed=None, preference_reason_code=None, preference_source=None, preference_revision=None,
        final_reason_code="BLOCKED"
    )
    router._evaluate_customer_delivery_policy = MagicMock(return_value=dec_blocked)
    
    with pytest.raises(CommunicationChannelDisabledError):
        asyncio.run(router._send_sms(_make_event(), "customer", {}, "job_assigned", category=CommunicationMessageCategory.STANDARD))
    dispatch_mock.assert_not_called()
    # Email allowed
    dec_email_allowed = CommunicationDeliveryEligibilityDecision(
        allowed=True, channel="EMAIL", category=CommunicationMessageCategory.STANDARD, recipient_type="CUSTOMER",
        global_allowed=True, global_state=CommunicationChannelState.ENABLED, global_reason_code="G", global_revision=1,
        preference_applied=True, preference_allowed=True, preference_reason_code="P", preference_source="P", preference_revision=1,
        final_reason_code="ALLOWED"
    )
    router._evaluate_customer_delivery_policy = MagicMock(return_value=dec_email_allowed)
    asyncio.run(router._send_email(_make_event(), "customer", {}, {}, "job_assigned", category=CommunicationMessageCategory.STANDARD))
    email_mock.send_email.assert_called_once()
    router._evaluate_customer_delivery_policy.assert_called_with(
        event=unittest.mock.ANY, channel="EMAIL", category=CommunicationMessageCategory.STANDARD
    )
    
    # Email blocked
    dec_email_blocked = CommunicationDeliveryEligibilityDecision(
        allowed=False, channel="EMAIL", category=CommunicationMessageCategory.STANDARD, recipient_type="CUSTOMER",
        global_allowed=False, global_state=CommunicationChannelState.DISABLED, global_reason_code="G", global_revision=1,
        preference_applied=False, preference_allowed=None, preference_reason_code=None, preference_source=None, preference_revision=None,
        final_reason_code="BLOCKED"
    )
    router._evaluate_customer_delivery_policy = MagicMock(return_value=dec_email_blocked)
    with pytest.raises(CommunicationChannelDisabledError):
        asyncio.run(router._send_email(_make_event(), "customer", {}, {}, "job_assigned", category=CommunicationMessageCategory.STANDARD))

# ---------------------------------------------------------
# Queued Execution (53-60)
# ---------------------------------------------------------
def test_53_54_execution_time_policy(monkeypatch):
    import app.tasks as tasks_module
    from app.tasks import process_job_status_transition_task
    import app.services.twilio_sms as twilio_module
    import app.services.notification_services as ns_module
    monkeypatch.setattr(
        ns_module.NotificationRouter,
        "_send_push",
        AsyncMock(return_value=False),
    )
    
    mock_db = MagicMock()
    mock_job = MagicMock()
    mock_job.id = 1
    mock_job.tenant_id = "tenant-1"
    mock_job.customer_id = "customer-1"
    mock_job.customer_name = "Customer"
    mock_job.contact_number = "+15555550100"
    mock_job.customer_email = "customer@example.com"
    mock_job.assigned_technician_id = "tech-1"
    mock_job.sla_deadline = None
    
    mock_tech = MagicMock()
    mock_tech.technician_name = "Technician"
    
    def fake_query(model):
        m = MagicMock()
        if model.__name__ == "Job":
            m.filter.return_value.first.return_value = mock_job
        else:
            m.filter.return_value.first.return_value = mock_tech
        return m
    
    mock_db.query = fake_query
    
    # Prove the task-scoped database session closes
    mock_session_class = MagicMock(return_value=mock_db)
    monkeypatch.setattr(tasks_module, "SessionLocal", mock_session_class)
    monkeypatch.setattr(ns_module, "SessionLocal", mock_session_class)
    
    # Narrowly mock unrelated dependencies
    import app.services.fcm as fcm_module
    monkeypatch.setattr(fcm_module, "send_job_assignment_notification", AsyncMock(return_value={"success": 1}))
    
    import app.services.socket_manager as sm_module
    monkeypatch.setattr(sm_module.ws_manager, "broadcast", AsyncMock())
    
    # Mock communication integration so we don't need real AI keys
    async def fake_generate(*args, **kwargs):
        return SimpleNamespace(decision=SimpleNamespace(
            message="Test", subject="Test", title="Test", used_fallback=False, channel=kwargs.get("channel", "sms").upper(),
            output=SimpleNamespace(text="Test", subject="Test", title="Test", body="Test", html_body="Test", text_body="Test")
        ))
    monkeypatch.setattr("app.services.ai.integrations.communication_integration.CommunicationIntegration.generate", fake_generate)
    
    # Patch providers
    mock_twilio = MagicMock(return_value="SM_task_test")
    monkeypatch.setattr(twilio_module, "TWILIO_ACCOUNT_SID", "AC_test_account")
    monkeypatch.setattr(twilio_module, "dispatch_twilio_message", mock_twilio)
    
    mock_smtp = AsyncMock(return_value=True)
    monkeypatch.setattr(ns_module.SMTPEmailService, "send_email", mock_smtp)
    
    # Mock policy outcomes during task execution
    import app.services.ai.FieldOpsAI.services.communication_delivery_policy_service as policy_mod
    
    # --- Scenario 1: SMS was ENABLED at enqueue, becomes DISABLED before task execution ---
    dec_blocked = CommunicationDeliveryEligibilityDecision(
        allowed=False, channel="SMS", category=CommunicationMessageCategory.STANDARD, recipient_type="CUSTOMER",
        global_allowed=False, global_state=CommunicationChannelState.DISABLED, global_reason_code="G", global_revision=1,
        preference_applied=False, preference_allowed=None, preference_reason_code=None, preference_source=None, preference_revision=None,
        final_reason_code="BLOCKED"
    )
    monkeypatch.setattr(policy_mod.CommunicationDeliveryPolicyService, "evaluate", MagicMock(return_value=dec_blocked))
    
    # Execute the Celery task synchronously for EN_ROUTE (which selects SMS)
    process_job_status_transition_task(
        job_id=1, from_status="CREATED", to_status="EN_ROUTE",
        actor_id="actor-1", actor_role="dispatcher", reason=None
    )
    
    # Twilio helper not called because it evaluated to BLOCKED inside _send_sms
    mock_twilio.assert_not_called()
    
    # Prove the task-scoped DB session was closed
    mock_db.close.assert_called()

    mock_twilio.reset_mock()
    mock_smtp.reset_mock()
    # --- Scenario 2: SMS was DISABLED at enqueue, becomes ENABLED before task execution ---
    dec_allowed = CommunicationDeliveryEligibilityDecision(
        allowed=True, channel="SMS", category=CommunicationMessageCategory.STANDARD, recipient_type="CUSTOMER",
        global_allowed=True, global_state=CommunicationChannelState.ENABLED, global_reason_code="G", global_revision=1,
        preference_applied=True, preference_allowed=True, preference_reason_code="P", preference_source="P", preference_revision=1,
        final_reason_code="ALLOWED"
    )
    policy_evaluate_mock = MagicMock(return_value=dec_allowed)

    monkeypatch.setattr(
        policy_mod.CommunicationDeliveryPolicyService,
        "evaluate",
        policy_evaluate_mock,
    )
    
    process_job_status_transition_task(
        job_id=1, from_status="CREATED", to_status="EN_ROUTE",
        actor_id="actor-1", actor_role="dispatcher", reason=None
    )
    
    # The SMS provider is called because execution-time policy now allows it.
    mock_twilio.assert_called_once()
    mock_smtp.assert_not_called()

    policy_evaluate_mock.assert_any_call(
        channel="SMS",
        category=CommunicationMessageCategory.STANDARD,
        recipient_type="CUSTOMER",
        tenant_id="tenant-1",
        customer_id="customer-1",
    )

# ---------------------------------------------------------
# Retry-time changes (61-66)
# ---------------------------------------------------------
def test_61_63_retry_time_changes_sms(monkeypatch):
    # This is handled directly in twilio_sms.py where `policy_service.evaluate(...)` is 
    # inside the `for attempt in range(max_retries):` loop.
    import app.services.twilio_sms as sms_module
    from app.services.twilio_sms import send_job_assignment_sms
    
    mock_tech = MagicMock()
    mock_tech.tech_id = "tech-1"
    mock_tech.sms_opt_out = False
    mock_tech.phone_number = "+15555555555"
    
    mock_query = MagicMock()
    mock_filter = MagicMock()
    mock_filter.all.return_value = [mock_tech]
    mock_query.filter.return_value = mock_filter
    mock_db = MagicMock()
    mock_db.query.return_value = mock_query
    
    mock_config = MagicMock()
    mock_pref = MagicMock()
    
    # We will patch CommunicationDeliveryPolicyService inside twilio_sms to return allowed on 1st attempt, blocked on 2nd.
    mock_policy_svc = MagicMock()
    mock_policy_svc.evaluate.side_effect = [
        CommunicationDeliveryEligibilityDecision(
            allowed=True, channel="SMS", category=CommunicationMessageCategory.STANDARD, recipient_type="TECHNICIAN",
            global_allowed=True, global_state=CommunicationChannelState.ENABLED, global_reason_code="G", global_revision=1,
            preference_applied=False, preference_allowed=None, preference_reason_code=None, preference_source=None, preference_revision=None,
            final_reason_code="ALLOWED"
        ),
        CommunicationDeliveryEligibilityDecision(
            allowed=False, channel="SMS", category=CommunicationMessageCategory.STANDARD, recipient_type="TECHNICIAN",
            global_allowed=False, global_state=CommunicationChannelState.DISABLED, global_reason_code="G", global_revision=1,
            preference_applied=False, preference_allowed=None, preference_reason_code=None, preference_source=None, preference_revision=None,
            final_reason_code="DISABLED"
        )
    ]
    
    class FakePolicyService:
        def __new__(cls, *args, **kwargs):
            return mock_policy_svc
            
    # Mock dispatch_twilio_message to throw TwilioRestException
    from twilio.base.exceptions import TwilioRestException
    fake_dispatch = MagicMock(side_effect=TwilioRestException(500, "uri", "Internal Server Error"))
            
    monkeypatch.setattr(sms_module, "dispatch_twilio_message", fake_dispatch)
    monkeypatch.setattr(sms_module, "CommunicationDeliveryPolicyService", FakePolicyService)
    monkeypatch.setattr(sms_module, "check_rate_limit", MagicMock(return_value=True))
    
    # Patch asyncio.sleep
    mock_sleep = AsyncMock()
    monkeypatch.setattr(asyncio, "sleep", mock_sleep)
    
    async def run():
        return await send_job_assignment_sms(
            db=mock_db, job_id="1", job_title="Repair", location="123 Main", priority="HIGH", tech_ids=["tech-1"]
        )
        
    result = asyncio.run(run())
    
    # policy evaluated twice
    assert mock_policy_svc.evaluate.call_count == 2
    # provider called once
    fake_dispatch.assert_called_once()
    # one retry backoff occurred after the transient failure
    mock_sleep.assert_called_once()
    # blocked count = 1
    assert result["blocked"] == 1
    # failed count follows contract
    assert result["failed"] == 1 # The technician delivery ended without a successful send.
    # sent count = 0
    assert result["sent"] == 0
    assert result["blocked_reasons"].get("DISABLED", 0) == 1


def test_sms_retry_callback_fires_before_next_attempt(monkeypatch):
    import app.services.twilio_sms as sms_module
    from app.services.twilio_sms import send_job_assignment_sms

    mock_tech = MagicMock()
    mock_tech.tech_id = "tech-1"
    mock_tech.sms_opt_out = False
    mock_tech.phone_number = "+15555555555"

    mock_query = MagicMock()
    mock_filter = MagicMock()
    mock_filter.all.return_value = [mock_tech]
    mock_query.filter.return_value = mock_filter

    mock_db = MagicMock()
    mock_db.query.return_value = mock_query

    mock_policy_svc = MagicMock()
    mock_policy_svc.evaluate.return_value = (
        CommunicationDeliveryEligibilityDecision(
            allowed=True,
            channel="SMS",
            category=CommunicationMessageCategory.STANDARD,
            recipient_type="TECHNICIAN",
            global_allowed=True,
            global_state=CommunicationChannelState.ENABLED,
            global_reason_code="G",
            global_revision=1,
            preference_applied=False,
            preference_allowed=None,
            preference_reason_code=None,
            preference_source=None,
            preference_revision=None,
            final_reason_code="ALLOWED",
        )
    )

    class FakePolicyService:
        def __new__(cls, *args, **kwargs):
            return mock_policy_svc

    from twilio.base.exceptions import TwilioRestException

    fake_dispatch = MagicMock(
        side_effect=[
            TwilioRestException(
                500,
                "uri",
                "Internal Server Error",
            ),
            "SMmock_retry_success",
        ]
    )

    retry_callback = AsyncMock()

    monkeypatch.setattr(
        sms_module,
        "dispatch_twilio_message",
        fake_dispatch,
    )
    monkeypatch.setattr(
        sms_module,
        "CommunicationDeliveryPolicyService",
        FakePolicyService,
    )
    monkeypatch.setattr(
        sms_module,
        "check_rate_limit",
        MagicMock(return_value=True),
    )
    monkeypatch.setattr(
        asyncio,
        "sleep",
        AsyncMock(),
    )

    async def run():
        return await send_job_assignment_sms(
            db=mock_db,
            job_id="1",
            job_title="Repair",
            location="123 Main",
            priority="HIGH",
            tech_ids=["tech-1"],
            on_retry=retry_callback,
        )

    result = asyncio.run(run())

    retry_callback.assert_awaited_once_with(
        attempt=2,
        delivery_id=mock_db.add.call_args.args[0].id,
    )
    fake_dispatch.assert_called()
    assert result["sent"] == 1


def test_email_single_attempt_behavior(monkeypatch):
    """
    Email delivery in notification_services.py currently has no retry loop.
    This test verifies that policy is evaluated immediately before its single provider attempt.
    """
    router, sms_mock, email_mock = get_fake_router()
    email_mock.send_email.return_value = False
    
    dec_allowed = CommunicationDeliveryEligibilityDecision(
        allowed=True, channel="EMAIL", category=CommunicationMessageCategory.STANDARD, recipient_type="CUSTOMER",
        global_allowed=True, global_state=CommunicationChannelState.ENABLED, global_reason_code="G", global_revision=1,
        preference_applied=True, preference_allowed=True, preference_reason_code="P", preference_source="P", preference_revision=1,
        final_reason_code="ALLOWED"
    )
    router._evaluate_customer_delivery_policy = MagicMock(return_value=dec_allowed)
    
    # Try sending email. It fails because provider returns False, and no retry happens.
    res = asyncio.run(router._send_email(_make_event(), "customer", {}, {}, "job_assigned", category=CommunicationMessageCategory.STANDARD))
    
    # Since send_email returned False, _send_email returns False
    assert res is False
    
    # Policy evaluated exactly once
    router._evaluate_customer_delivery_policy.assert_called_once()
    
    # Provider called exactly once
    email_mock.send_email.assert_called_once()

# ---------------------------------------------------------
# Fallback paths (67-73)
# ---------------------------------------------------------
@pytest.mark.parametrize("scenario,channel,global_allowed,global_state,category,pref_allowed,expected_allow", [
    ("SMS fallback + global DISABLED", "SMS", False, CommunicationChannelState.DISABLED, CommunicationMessageCategory.STANDARD, True, False),
    ("SMS fallback + EMERGENCY_ONLY + STANDARD", "SMS", False, CommunicationChannelState.EMERGENCY_ONLY, CommunicationMessageCategory.STANDARD, True, False),
    ("SMS fallback + EMERGENCY_ONLY + EMERGENCY", "SMS", True, CommunicationChannelState.EMERGENCY_ONLY, CommunicationMessageCategory.EMERGENCY, True, True),
    ("EMAIL fallback + pref disabled", "EMAIL", True, CommunicationChannelState.ENABLED, CommunicationMessageCategory.STANDARD, False, False),
])
def test_7_fallback_path(
    monkeypatch,
    scenario,
    channel,
    global_allowed,
    global_state,
    category,
    pref_allowed,
    expected_allow,
):
    router, sms_mock, email_mock = get_fallback_router()

    import app.services.twilio_sms as twilio_module

    dispatch_mock = MagicMock(
        return_value="SM_fallback_test"
    )

    monkeypatch.setattr(
        twilio_module,
        "TWILIO_ACCOUNT_SID",
        "AC_test_account",
    )

    monkeypatch.setattr(
        twilio_module,
        "dispatch_twilio_message",
        dispatch_mock,
    )

    mock_config = MagicMock()
    mock_pref = MagicMock()

    # Patch the names actually used by NotificationRouter.
    monkeypatch.setattr(
        module,
        "CommunicationConfigurationService",
        MagicMock(return_value=mock_config),
    )

    monkeypatch.setattr(
        module,
        "CustomerPreferenceService",
        MagicMock(return_value=mock_pref),
    )

    decision = CommunicationDeliveryEligibilityDecision(
        allowed=expected_allow,
        channel=channel,
        category=category,
        recipient_type="CUSTOMER",
        global_allowed=global_allowed,
        global_state=global_state,
        global_reason_code="G",
        global_revision=1,
        preference_applied=True,
        preference_allowed=pref_allowed,
        preference_reason_code="P",
        preference_source="PROFILE",
        preference_revision=1,
        final_reason_code=(
            "DELIVERY_POLICY_ALLOWED"
            if expected_allow
            else "BLOCKED"
        ),
    )

    router._evaluate_customer_delivery_policy = MagicMock(
        return_value=decision
    )

    event = _make_event()

    if channel == "SMS":
        if expected_allow:
            result = asyncio.run(
                router._send_sms(
                    event,
                    "customer",
                    {},
                    "job_assigned",
                    category=category,
                )
            )

            assert result is True

            dispatch_mock.assert_called_once_with(
                body=unittest.mock.ANY,
                to_phone="+15555550100",
            )

        else:
            with pytest.raises(
                CommunicationChannelDisabledError
            ):
                asyncio.run(
                    router._send_sms(
                        event,
                        "customer",
                        {},
                        "job_assigned",
                        category=category,
                    )
                )

            dispatch_mock.assert_not_called()

        email_mock.send_email.assert_not_called()

    elif channel == "EMAIL":
        if expected_allow:
            result = asyncio.run(
                router._send_email(
                    event,
                    "customer",
                    {},
                    {},
                    "job_assigned",
                    category=category,
                )
            )

            assert result is True
            email_mock.send_email.assert_called_once()

        else:
            with pytest.raises(
                CommunicationChannelDisabledError
            ):
                asyncio.run(
                    router._send_email(
                        event,
                        "customer",
                        {},
                        {},
                        "job_assigned",
                        category=category,
                    )
                )

            email_mock.send_email.assert_not_called()

        dispatch_mock.assert_not_called()

    # Fallback status must not convert STANDARD into EMERGENCY.
    router._evaluate_customer_delivery_policy.assert_called_once_with(
        event=unittest.mock.ANY,
        channel=channel,
        category=category,
    )

    # The mocked policy layer, not fallback generation, owns
    # configuration and preference evaluation.
    mock_config.evaluate_delivery.assert_not_called()
    mock_pref.evaluate_channel.assert_not_called()

# ---------------------------------------------------------
# Privacy and Regression
# ---------------------------------------------------------
def test_74_76_no_message_or_env_in_decision(policy_service, mock_config_service, mock_pref_service):
    mock_config_service.evaluate_delivery.return_value = DeliveryDecision(
        allowed=True, channel="SMS", state=CommunicationChannelState.ENABLED,
        category=CommunicationMessageCategory.STANDARD, reason_code="G", revision=1
    )
    mock_pref_service.evaluate_channel.return_value = CustomerPreferenceDecision(
        allowed=True, channel="SMS", reason_code="P", source="PROFILE", revision=1
    )
    
    dec = policy_service.evaluate(
        channel="SMS", category=CommunicationMessageCategory.STANDARD,
        recipient_type="CUSTOMER", tenant_id="tenant-1", customer_id="c1"
    )
    
    dump = dec.model_dump()
    assert "message" not in dump
    assert "body" not in dump
    assert "email" not in dump
    assert "phone" not in dump
    assert "env" not in dump

def test_missing_customer_identity_fails_closed(policy_service, mock_config_service):
    mock_config_service.evaluate_delivery.return_value = DeliveryDecision(
        allowed=True, channel="SMS", state=CommunicationChannelState.ENABLED,
        category=CommunicationMessageCategory.STANDARD, reason_code="GLOBAL_ALLOWED", revision=1
    )
    dec = policy_service.evaluate(
        channel="SMS", category=CommunicationMessageCategory.STANDARD,
        recipient_type="CUSTOMER", tenant_id="tenant-1", customer_id=None
    )
    
    assert dec.allowed is False
    assert dec.final_reason_code == "CUSTOMER_IDENTITY_REQUIRED"
    assert dec.preference_reason_code == "CUSTOMER_IDENTITY_REQUIRED"

def test_8_policy_composition(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.database import Base
    from app.models import CommunicationChannelConfiguration, CustomerProfile
    from app.services.ai.FieldOpsAI.repositories.communication_configuration_repository import CommunicationConfigurationRepository
    from app.services.ai.FieldOpsAI.repositories.customer_profile_repository import CustomerProfileRepository
    from app.services.ai.FieldOpsAI.services.communication_configuration_service import CommunicationConfigurationService
    from app.services.ai.FieldOpsAI.services.customer_preference_service import CustomerPreferenceService
    
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine)
    db = TestingSessionLocal()
    org_a = Organization(
    id="tenant-a",
    name="Tenant A",
    slug="tenant-a",
    )

    org_b = Organization(
    id="tenant-b",
    name="Tenant B",
    slug="tenant-b",
    )

    db.add_all([org_a, org_b])
    db.commit()

    org = Organization(
        id="t1",
        name="Test Organization",
        slug="test-organization",
    )

    db.add(org)
    db.commit()
    
    db.add(CommunicationChannelConfiguration(tenant_id="tenant-1",
        channel="SMS",
        state=CommunicationChannelState.ENABLED,
        revision=1,
        updated_by="sys"
    ))

    db.add(CommunicationChannelConfiguration(tenant_id="tenant-1",
        channel="EMAIL",
        state=CommunicationChannelState.DISABLED,
        revision=1,
        updated_by="sys"
    ))
    
    db.add(CustomerProfile(tenant_id="tenant-1", customer_id="c1", sms_enabled=True, email_enabled=False, revision=1, updated_by="sys"))
    db.commit()
    
    config_repo = CommunicationConfigurationRepository(db)
    env_mapping = {}
    config_svc = CommunicationConfigurationService(
        config_repo,
        db,
        redis_client=None,
        environment=env_mapping,
    )
    pref_repo = CustomerProfileRepository(db)
    pref_svc = CustomerPreferenceService(pref_repo)
    
    policy_svc = CommunicationDeliveryPolicyService(config_svc, pref_svc)
    
    # 1. persistent ENABLED, override INHERIT, preference enabled => allowed
    env_mapping.clear()
    dec = policy_svc.evaluate(channel="SMS", category=CommunicationMessageCategory.STANDARD, recipient_type="CUSTOMER", tenant_id="tenant-1", customer_id="c1")
    assert dec.allowed is True
    
    # 2. persistent ENABLED, override DISABLED, preference enabled => blocked
    env_mapping["FIELDOPS_SMS_EMERGENCY_OVERRIDE"] = "DISABLED"
    dec = policy_svc.evaluate(channel="SMS", category=CommunicationMessageCategory.STANDARD, recipient_type="CUSTOMER", tenant_id="tenant-1", customer_id="c1")
    assert dec.allowed is False
    assert dec.global_reason_code == "ENV_OVERRIDE_DISABLED"
    
    # 3. persistent ENABLED, override EMERGENCY_ONLY, STANDARD => blocked
    env_mapping["FIELDOPS_SMS_EMERGENCY_OVERRIDE"] = "EMERGENCY_ONLY"
    dec = policy_svc.evaluate(channel="SMS", category=CommunicationMessageCategory.STANDARD, recipient_type="CUSTOMER", tenant_id="tenant-1", customer_id="c1")
    assert dec.allowed is False
    
    # 4. persistent ENABLED, override EMERGENCY_ONLY, EMERGENCY, preference enabled => allowed
    dec = policy_svc.evaluate(channel="SMS", category=CommunicationMessageCategory.EMERGENCY, recipient_type="CUSTOMER", tenant_id="tenant-1", customer_id="c1")
    assert dec.allowed is True
    
    # 5. persistent DISABLED, override EMERGENCY_ONLY, EMERGENCY => blocked
    # Email is persistent DISABLED in db
    env_mapping["FIELDOPS_EMAIL_EMERGENCY_OVERRIDE"] = "EMERGENCY_ONLY"
    dec = policy_svc.evaluate(channel="EMAIL", category=CommunicationMessageCategory.EMERGENCY, recipient_type="CUSTOMER", tenant_id="tenant-1", customer_id="c1")
    assert dec.allowed is False
    assert dec.global_reason_code == "EMAIL_DISABLED" # Because DB is more restrictive than override
    
    # 6. persistent ENABLED, invalid override => blocked
    env_mapping["FIELDOPS_SMS_EMERGENCY_OVERRIDE"] = "INVALID_STATE"
    dec = policy_svc.evaluate(channel="SMS", category=CommunicationMessageCategory.STANDARD, recipient_type="CUSTOMER", tenant_id="tenant-1", customer_id="c1")
    assert dec.allowed is False
    
    # 7. persistent ENABLED, preference disabled, EMERGENCY => blocked
    env_mapping.clear()
    # Email preference is disabled for this customer in DB
    # We update EMAIL config to ENABLED in db to test preference block
    email_config = db.query(CommunicationChannelConfiguration).filter_by(channel="EMAIL").first()
    email_config.state = CommunicationChannelState.ENABLED
    db.commit()
    
    dec = policy_svc.evaluate(channel="EMAIL", category=CommunicationMessageCategory.EMERGENCY, recipient_type="CUSTOMER", tenant_id="tenant-1", customer_id="c1")
    assert dec.allowed is False
    assert dec.preference_allowed is False
    
    db.close()

def test_9_tenant_isolation(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.database import Base
    from app.models import CommunicationChannelConfiguration, CustomerProfile
    from app.services.ai.FieldOpsAI.repositories.communication_configuration_repository import CommunicationConfigurationRepository
    from app.services.ai.FieldOpsAI.repositories.customer_profile_repository import CustomerProfileRepository
    from app.services.ai.FieldOpsAI.services.communication_configuration_service import CommunicationConfigurationService
    from app.services.ai.FieldOpsAI.services.customer_preference_service import CustomerPreferenceService
    
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine)
    db = TestingSessionLocal()

    org_a = Organization(
        id="tenant-a",
        name="Tenant A",
        slug="tenant-a"
    )

    org_b = Organization(
       id="tenant-b",
       name="Tenant B",
       slug="tenant-b"
    )

    db.add_all([org_a, org_b])
    db.commit()
    
    # Global config is enabled for both SMS and EMAIL
    db.add(CommunicationChannelConfiguration(
        tenant_id="tenant-a",
        channel="SMS",
        state=CommunicationChannelState.ENABLED,
        revision=1,
        updated_by="sys"
    ))

    db.add(CommunicationChannelConfiguration(
        tenant_id="tenant-a",
        channel="EMAIL",
        state=CommunicationChannelState.ENABLED,
        revision=1,
        updated_by="sys"
    ))
    # Tenant a: SMS disabled, EMAIL enabled
    db.add(CustomerProfile(tenant_id="tenant-a", customer_id="shared-customer", sms_enabled=False, email_enabled=True, revision=1, updated_by="sys"))
    
    # Tenant b: SMS enabled, EMAIL disabled
    db.add(CustomerProfile(tenant_id="tenant-b", customer_id="shared-customer", sms_enabled=True, email_enabled=False, revision=1, updated_by="sys"))
    db.commit()
    
    config_repo = CommunicationConfigurationRepository(db)
    config_svc = CommunicationConfigurationService(config_repo, db, redis_client=MagicMock())
    pref_repo = CustomerProfileRepository(db)
    
    # Spy on pref_repo.get_by_customer
    original_get = pref_repo.get_by_customer
    pref_repo.get_by_customer = MagicMock(side_effect=original_get)
    
    pref_svc = CustomerPreferenceService(pref_repo)
    
    policy_svc = CommunicationDeliveryPolicyService(config_svc, pref_svc)
    
    # tenant-a
    dec_a_sms = policy_svc.evaluate(channel="SMS", category=CommunicationMessageCategory.STANDARD, recipient_type="CUSTOMER", tenant_id="tenant-a", customer_id="shared-customer")
    assert dec_a_sms.allowed is False
    pref_repo.get_by_customer.assert_called_with("tenant-a", "shared-customer")
    
    dec_a_email = policy_svc.evaluate(channel="EMAIL", category=CommunicationMessageCategory.STANDARD, recipient_type="CUSTOMER", tenant_id="tenant-a", customer_id="shared-customer")
    assert dec_a_email.allowed is True
    
    # tenant-b
    dec_b_sms = policy_svc.evaluate(channel="SMS", category=CommunicationMessageCategory.STANDARD, recipient_type="CUSTOMER", tenant_id="tenant-b", customer_id="shared-customer")
    assert dec_b_sms.allowed is True
    pref_repo.get_by_customer.assert_called_with("tenant-b", "shared-customer")
    
    dec_b_email = policy_svc.evaluate(channel="EMAIL", category=CommunicationMessageCategory.STANDARD, recipient_type="CUSTOMER", tenant_id="tenant-b", customer_id="shared-customer")
    assert dec_b_email.allowed is False
    
    db.close()

def test_11_boundary_audit():
    import os
    import glob
    
    app_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app"))
    py_files = glob.glob(os.path.join(app_dir, "**", "*.py"), recursive=True)
    
    count = 0
    for f in py_files:
        with open(f, "r", encoding="utf-8") as file:
            content = file.read()
            count += content.count("twilio_client.messages.create")
            
    # Should only be exactly 1 in twilio_sms.py (dispatch_twilio_message)
    assert count == 1
