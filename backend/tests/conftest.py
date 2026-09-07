import pytest
import time
import os
import app.database
import app.redis_client
from app.services.ai.FieldOpsAI.services.communication_service import CommunicationService

from app.services.ai.FieldOpsAI.schemas.communication import (
    CommunicationContext,
    CommunicationDecision,
    CommunicationRecipient,
)
os.environ.setdefault(
    "AI_GUARDRAIL_AUDIT_HMAC_KEY",
    "test-only-fieldops-audit-key",
)


# Store original references
_orig_session_local = app.database.SessionLocal
_orig_get_redis = app.redis_client.get_redis_client

_current_request = None
_last_request_module = None

def dynamic_get_redis_client():
    module = None
    if _current_request and _current_request.module:
        module = _current_request.module
    elif _last_request_module:
        module = _last_request_module

    if module:
        for attr_name in ("fake_redis", "fake_sync_redis", "mock_redis", "fake_async_redis"):
            if hasattr(module, attr_name):
                return getattr(module, attr_name)
    return _orig_get_redis()

def dynamic_session_local(*args, **kwargs):
    module = None
    if _current_request and _current_request.module:
        module = _current_request.module
    elif _last_request_module:
        module = _last_request_module

    if module and hasattr(module, "TestingSessionLocal"):
        return getattr(module, "TestingSessionLocal")(*args, **kwargs)
    return _orig_session_local(*args, **kwargs)

# Apply global dynamic routing before importing main application
app.database.SessionLocal = dynamic_session_local
app.redis_client.get_redis_client = dynamic_get_redis_client

# Helper to prevent global import-time monkeypatch overwrites in test modules
def make_write_resistant(module_name):
    import sys
    if module_name in sys.modules:
        mod = sys.modules[module_name]
        class CustomModule(mod.__class__):
            def __setattr__(self, name, value):
                if name in ("SessionLocal", "get_redis_client"):
                    return
                super().__setattr__(name, value)
        mod.__class__ = CustomModule

make_write_resistant("app.database")
make_write_resistant("app.redis_client")

import app.main
from app.celery_app import celery_app

# Configure Celery eagerly for all tests
celery_app.conf.update(
    task_always_eager=True,
    task_eager_propagates=True
)

app.main.SessionLocal = dynamic_session_local

make_write_resistant("app.main")
import app.services.tracking_manager
make_write_resistant("app.services.tracking_manager")
try:
    import app.routes.tracking
    make_write_resistant("app.routes.tracking")
except ImportError:
    pass

@pytest.fixture(autouse=True)
def track_current_request(request):
    global _current_request, _last_request_module
    _current_request = request
    if request.module:
        _last_request_module = request.module
    yield
    _current_request = None

from unittest.mock import MagicMock, AsyncMock

class SimTimer:
    def __init__(self):
        self.now = 0.0

    def tick(self, seconds: float):
        self.now += seconds

    def time(self) -> float:
        return self.now


class FakeRedisClient:
    def __init__(self, timer: SimTimer):
        self.store: dict[str, tuple[str, float]] = {}
        self.timer = timer
        self.calls: list[str] = []
        self.fail_get = False
        self.fail_setex = False
        self.timeout_get = False
        self.fail_delete = False

    def _track(self, op: str, key: str):
        self.calls.append(f"{op}:{key}")

    def get(self, key: str) -> str | None:
        self._track("get", key)
        if self.timeout_get:
            raise TimeoutError("Simulated Redis timeout")
        if self.fail_get:
            raise ConnectionError("Simulated Redis get failure")
        if key in self.store:
            val, expires_at = self.store[key]
            if self.timer.time() >= expires_at:
                del self.store[key]
                return None
            return val
        return None

    def setex(self, key: str, time_seconds: int, value: str) -> bool:
        self._track("setex", key)
        if self.fail_setex:
            raise ConnectionError("Simulated Redis setex failure")
        self.store[key] = (value, self.timer.time() + time_seconds)
        return True

    def delete(self, key: str) -> int:
        self._track("delete", key)
        if self.fail_delete:
            raise ConnectionError("Simulated Redis delete failure")
        if key in self.store:
            del self.store[key]
            return 1
        return 0


@pytest.fixture
def sim_timer():
    return SimTimer()

@pytest.fixture
def fake_redis(sim_timer):
    return FakeRedisClient(sim_timer)

class _TrackingEmailService:
    def __init__(self):
        self.calls = []

    async def send_email(self, to_email: str, subject: str, html_content: str) -> bool:
        self.calls.append({"to": to_email, "subject": subject})
        return True

class _FakeCommIntegration:
    async def process_event(self, event, channel: str):
        pass

    async def generate(self, event, recipient_type, channel, notification_type, locale="en"):
        class FakeMessage:
            def __init__(self):
                self.body = "test body"
                self.html = "test html"
        class FakeOutput:
            def __init__(self):
                self.text = "test message"
                self.subject = "test subject"
                self.title = "test title"
                self.body = "test message"
                self.html_body = "test message"
                self.text_body = "test message"
        
        class FakeDecision:
            def __init__(self, c):
                self.channel = c
                self.message = "test message"
                self.subject = "test subject"
                self.title = "test title"
                self.output = FakeOutput()
        class FakeResult:
            def __init__(self, c):
                self.decision = FakeDecision(c)
                self.message = FakeMessage()
        return FakeResult(channel.upper().replace("-", "_"))

def _make_router(email_service, db_session):
    import app.services.notification_services as notif_mod
    return getattr(notif_mod, "NotificationRouter")(
        fcm_service=AsyncMock(return_value={"sent": 0, "failed": 0, "delivery_ids": []}),
        sms_service=AsyncMock(return_value={"sent": 0, "failed": 0, "blocked": 0, "blocked_reasons": {}}),
        email_service=email_service,
        ws_manager=MagicMock(),
        redis_client=MagicMock(),
        communication_integration=_FakeCommIntegration(),
    )


def _build_completed_event():
    from app.services.notification_services import JobStatusEvent
    import datetime
    return JobStatusEvent(
        job_id="99",
        tenant_id="tenant-test",
        from_status="IN_PROGRESS",
        to_status="COMPLETED",
        actor_id="actor-1",
        actor_role="technician",
        reason=None,
        timestamp=datetime.datetime.now(datetime.timezone.utc),
        job_title="Pipe Fix",
        job_location="1 Test St",
        technician_id="tech-99",
        technician_name="Bob",
        customer_id="cust-1",
        customer_name="Alice",
        customer_phone="+15555550101",
        customer_email="alice@example.com",
        eta=None,
        notification_channels=[],
    )

# ============================================================================
# Message generation test helpers
# ============================================================================

# Status -> (CommunicationContext.job_status, notification_type)
#
# "created" intentionally has no production fallback template.
# It is included so test_generation.py can document that gap.

STATUS_MAP: dict[str, tuple[str, str]] = {
    "created": ("CREATED", "job_created"),
    "assigned": ("ASSIGNED", "job_assigned"),
    "enroute": ("EN_ROUTE", "technician_en_route"),
    "onsite": ("ON_SITE", "technician_arrived"),
    "completed": ("COMPLETED", "job_completed"),
    "cancelled": ("CANCELLED", "job_cancelled"),
}

STATUSES = list(STATUS_MAP.keys())

# These are the valid CommunicationContext.channel values.
# PORTAL is intentionally tested separately because it is not a valid
# requestable channel in CommunicationContext.
CHANNELS = ["SMS", "EMAIL", "PUSH", "IN_APP"]

PATHS = ["ai", "fallback"]


def build_context(
    status_key: str,
    channel: str,
    *,
    customer_name: str = "Priya Raman",
    technician_name: str = "Arun Kumar",
    job_title: str = "AC Repair",
    job_id: str = "JOB-1001",
    eta: str | None = "15 minutes",
    locale: str = "en",
) -> CommunicationContext:
    """
    Build a valid CommunicationContext for one
    (status, channel) test combination.
    """

    job_status, notification_type = STATUS_MAP[status_key]

    return CommunicationContext(
        job_id=job_id,
        notification_type=notification_type,
        recipient_type=CommunicationRecipient.CUSTOMER,
        channel=channel,
        locale=locale,
        customer_name=customer_name,
        technician_name=technician_name,
        job_status=job_status,
        job_title=job_title,
        eta=eta,
        sentiment="NEUTRAL",
    )


def _decision_kwargs_for_channel(
    channel: str,
    customer_name: str,
    technician_name: str,
    job_title: str,
):
    """
    Build CommunicationDecision fields appropriate for each channel.
    """

    if channel == "SMS":
        return {
            "title": None,
            "subject": None,
            "message": (
                f"Hi {customer_name}, your {job_title} job is being "
                f"handled by {technician_name}."
            ),
        }

    if channel == "EMAIL":
        return {
            "title": None,
            "subject": f"Update on your {job_title} job",
            "message": (
                f"<p>Hi {customer_name},</p>"
                f"<p>{technician_name} has an update on your "
                f"{job_title} job.</p>"
            ),
        }

    if channel == "PUSH":
        return {
            "title": "FieldOps Update",
            "subject": None,
            "message": (
                f"{technician_name} has an update for {customer_name}."
            ),
        }

    if channel == "IN_APP":
        return {
            "title": None,
            "subject": None,
            "message": (
                f"{customer_name}'s {job_title} job: "
                f"update from {technician_name}."
            ),
        }

    raise ValueError(
        f"Unsupported channel in test fixture: {channel}"
    )


class FakeSuccessAgent:
    """
    Fast, deterministic AI agent for generation tests.

    This represents the successful AI path without calling
    a real AI provider.
    """

    def __init__(self, latency_seconds: float = 0.0):
        self._latency = latency_seconds

    def generate(
        self,
        context: CommunicationContext,
    ) -> CommunicationDecision:

        if self._latency:
            time.sleep(self._latency)

        kwargs = _decision_kwargs_for_channel(
            context.channel,
            context.customer_name or "Customer",
            context.technician_name or "your technician",
            context.job_title or "your service",
        )

        return CommunicationDecision(
            channel=context.channel,
            tone="PROFESSIONAL",
            confidence=0.95,
            **kwargs,
        )


class FakeFailureAgent:
    """
    AI agent that always fails.

    This forces CommunicationService.generate() to exercise
    the real fallback path.
    """

    def generate(
        self,
        context: CommunicationContext,
    ) -> CommunicationDecision:

        raise RuntimeError(
            "Simulated AI generation failure (forces fallback)."
        )


@pytest.fixture()
def fake_success_agent():
    return FakeSuccessAgent()


@pytest.fixture()
def fake_failure_agent():
    return FakeFailureAgent()


@pytest.fixture
def db_session():
    """
    Provide a real test database session for CommunicationService.

    The individual test module must expose:
        TestingSessionLocal
    """

    module = None

    if _current_request and _current_request.module:
        module = _current_request.module
    elif _last_request_module:
        module = _last_request_module

    if module and hasattr(module, "TestingSessionLocal"):
        session = module.TestingSessionLocal()

        try:
            yield session
        finally:
            session.close()

        return

    pytest.fail(
        "TestingSessionLocal was not found in the current test module."
    )


@pytest.fixture
def generation_service(db_session):
    """
    Factory for CommunicationService generation tests.

    Uses the test database instead of db=None so that
    CommunicationService and its fallback/template services
    can query NotificationTemplate and related records.
    """

    def _make_service(agent):
        return CommunicationService(
            db=db_session,
            tenant_id="tenant-test",
            agent=agent,
            audit_logger=MagicMock(),
        )

    return _make_service