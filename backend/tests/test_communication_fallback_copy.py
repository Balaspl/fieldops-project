from types import SimpleNamespace

from app.services.ai.FieldOpsAI.agents.communication_agent.events import JobEvent
from app.services.ai.FieldOpsAI.agents.communication_agent.message import build_copy


def test_customer_fallback_copy_is_stable_for_retry_and_varies_by_version():
    recipient = SimpleNamespace(role="customer", id="customer-1", tenant_id="tenant-1")
    job = SimpleNamespace(id=214, service_type="Heating", eta_min=None)

    first = build_copy(JobEvent.EN_ROUTE, recipient, job, None, version=4)
    retry = build_copy(JobEvent.EN_ROUTE, recipient, job, None, version=4)
    next_event = build_copy(JobEvent.EN_ROUTE, recipient, job, None, version=5)

    assert first == retry
    assert first != next_event
    assert "on the way" in first[1].lower() or "heading" in first[1].lower() or "trip" in first[1].lower()
    assert "minutes" not in first[1].lower()
    assert any(emoji in first[0] for emoji in ("📍", "🧭", "✨", "🚶"))
    assert any(phrase in first[1].lower() for phrase in ("toolbox", "finish line", "next update", "next stop"))


def test_en_route_copy_uses_real_technician_and_eta_with_varied_wording():
    recipient = SimpleNamespace(role="customer", id="customer-3", tenant_id="tenant-1")
    job = SimpleNamespace(id=216, service_type="Heating", eta_min=6)
    technician = SimpleNamespace(technician_name="Guru Tech")

    first = build_copy(JobEvent.EN_ROUTE, recipient, job, technician, version=2)
    second = build_copy(JobEvent.EN_ROUTE, recipient, job, technician, version=3)

    assert first != second
    assert "Guru" in first[1] and "6 minutes" in first[1]
    assert "Guru" in second[1] and "6 minutes" in second[1]
    assert "Guru Tech" not in first[1]  # Use the available first name only.
    assert "Guru" in first[0] and "way" in first[0].lower()
    assert any(emoji in first[0] for emoji in ("📍", "🧭", "✨", "🚶"))
    assert "Track live" in first[1]


def test_customer_fallback_reflects_confirmed_status_without_inventing_context():
    recipient = SimpleNamespace(role="customer", id="customer-2", tenant_id="tenant-1")
    job = SimpleNamespace(id=215, service_type=None, eta_min=None)

    accepted = build_copy(JobEvent.TECHNICIAN_ACCEPTED, recipient, job, None, version=1)
    delayed = build_copy(JobEvent.DELAYED, recipient, job, None, version=2)
    completed = build_copy(JobEvent.COMPLETED, recipient, job, None, version=3)

    assert accepted[0] != delayed[0]
    assert "estimate" in delayed[1].lower()
    assert "minutes" not in delayed[1].lower()
    assert "complete" in completed[1].lower()
    # The generic role is safe without a verified technician identity.
    assert "your technician" in accepted[1].lower()
    assert "maya" not in accepted[1].lower()
