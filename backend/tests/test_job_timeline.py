import pytest
from datetime import date, datetime, timezone, timedelta
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.services.job_timeline_service as timeline_service
from app.database import Base
from app.models import (
    AssignmentOverride,
    AuditEvent,
    EnterpriseAuditLog,
    Job,
    JobClosure,
    SLAEscalation,
    Technician,
)
from app.services.job_timeline_service import (
    _assignment_override_items,
    _audit_event_items,
    _build_event,
    _closure_items,
    _enterprise_audit_items,
    _iso,
    _job_lifecycle_events,
    _resolve_technician,
    _role_label,
    _safe_actor_name,
    _sla_items,
    _utc,
    build_job_timeline,
)


ENGINE = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

SessionLocal = sessionmaker(
    bind=ENGINE,
    autocommit=False,
    autoflush=False,
)


class QueryStub:
    def __init__(self, rows):
        self.rows = list(rows)

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return list(self.rows)


class FakeDB:
    def __init__(self, rows_by_model=None):
        self.rows_by_model = rows_by_model or {}

    def query(self, model):
        return QueryStub(self.rows_by_model.get(model, []))


def setup_function():
    Base.metadata.drop_all(bind=ENGINE)
    Base.metadata.create_all(bind=ENGINE)


def teardown_function():
    Base.metadata.drop_all(bind=ENGINE)


def _job(db, *, tenant_id: str = "tenant-1") -> Job:
    job = Job(
        tenant_id=tenant_id,
        customer_name="Customer",
        location="Chennai",
        issue_description="Service required",
        priority="HIGH",
        service_type="HVAC",
        contact_number="9000000000",
        preferred_service_date=date(2026, 9, 22),
        status="COMPLETED",
    )

    db.add(job)
    db.commit()
    db.refresh(job)

    return job


def _timeline_job(**overrides):
    values = {
        "id": 1,
        "tenant_id": "tenant-1",
        "status": "COMPLETED",
        "technician": None,
        "created_at": None,
        "assigned_at": None,
        "en_route_at": None,
        "on_site_at": None,
        "completed_at": None,
        "cancelled_at": None,
        "closed_at": None,
        "rejected_at": None,
        "assigned_by": None,
        "en_route_by": None,
        "on_site_by": None,
        "completed_by": None,
        "cancelled_by": None,
        "rejected_by_tech_id": None,
        "cancellation_reason": None,
        "closure_reason": None,
        "rejection_reason": None,
    }

    values.update(overrides)
    return SimpleNamespace(**values)


def _event(
    event_id,
    timestamp,
    *,
    to_status=None,
    category="STATUS",
):
    return _build_event(
        event_id=event_id,
        job_id=1,
        event_type="TEST_EVENT",
        event_category=category,
        title="Test Event",
        description="Test event",
        timestamp=timestamp,
        from_status=None,
        to_status=to_status,
        actor_name="System",
        actor_role="SYSTEM",
        source="test",
    )


# ---------------------------------------------------------------------------
# Helper coverage
# ---------------------------------------------------------------------------

def test_normalization_and_safe_labels_cover_edge_cases():
    naive = datetime(2026, 9, 22, 8, 0)
    aware = datetime(
        2026,
        9,
        22,
        8,
        0,
        tzinfo=timezone.utc,
    )

    normalized = _utc(naive)

    assert normalized.tzinfo == timezone.utc
    assert normalized.hour == 8

    assert _utc(None) is None
    assert _iso(None) is None
    assert _iso(aware) == aware.isoformat()

    assert _role_label(None) == "SYSTEM"
    assert _role_label("") == "SYSTEM"
    assert (
        _role_label(SimpleNamespace(value="technician"))
        == "TECHNICIAN"
    )
    assert _role_label(" dispatcher ") == "DISPATCHER"

    assert _safe_actor_name(None) == "System"
    assert _safe_actor_name("") == "System"
    assert _safe_actor_name(" Dispatcher ") == "Dispatcher"


def test_resolve_technician_handles_none_cache_numeric_and_text_identifier():
    technician = SimpleNamespace(
        technician_id=7,
        tech_id="tech-7",
        technician_name="Technician Seven",
    )

    db = FakeDB({Technician: [technician]})
    cache = {}

    assert _resolve_technician(
        db,
        "tenant-1",
        None,
        cache,
    ) is None

    resolved = _resolve_technician(
        db,
        "tenant-1",
        "tech-7",
        cache,
    )

    assert resolved is technician
    assert cache["tech-7"] is technician

    # Cache hit path.
    assert _resolve_technician(
        db,
        "tenant-1",
        "tech-7",
        cache,
    ) is technician

    # Numeric technician_id path.
    assert _resolve_technician(
        db,
        "tenant-1",
        "7",
        cache,
    ) is technician


# ---------------------------------------------------------------------------
# Lifecycle coverage
# ---------------------------------------------------------------------------

def test_job_lifecycle_covers_cancel_close_reject_and_unknown_event(
    monkeypatch,
):
    monkeypatch.setattr(
        timeline_service,
        "_resolve_technician",
        lambda *args, **kwargs: SimpleNamespace(
            technician_name="Assigned Technician",
        ),
    )

    original_fields = timeline_service.LIFECYCLE_TIMESTAMP_FIELDS

    timeline_service.LIFECYCLE_TIMESTAMP_FIELDS = (
        *original_fields,
        (
            "unknown_at",
            "UNKNOWN_EVENT",
            "OTHER",
            "Unknown Event",
        ),
    )

    try:
        base = datetime(
            2026,
            9,
            22,
            10,
            0,
            tzinfo=timezone.utc,
        )

        job = _timeline_job(
            status="REJECTED_BY_TECHNICIAN",
            technician=SimpleNamespace(
                technician_name="Assigned Technician",
            ),
            created_at=base,
            assigned_at=base + timedelta(minutes=1),
            en_route_at=base + timedelta(minutes=2),
            on_site_at=base + timedelta(minutes=3),
            completed_at=base + timedelta(minutes=4),
            cancelled_at=base + timedelta(minutes=5),
            closed_at=base + timedelta(minutes=6),
            rejected_at=base + timedelta(minutes=7),
            en_route_by="tech-7",
            on_site_by="tech-7",
            completed_by="tech-7",
            rejected_by_tech_id="tech-7",
            cancellation_reason="Customer requested cancellation",
            closure_reason="Administrative closure",
            rejection_reason="Technician unavailable",
            unknown_at=base + timedelta(minutes=8),
        )

        events = _job_lifecycle_events(None, job)

        assert [
            event["event_type"]
            for event in events
        ] == [
            "JOB_CREATED",
            "JOB_ASSIGNED",
            "JOB_EN_ROUTE",
            "JOB_IN_PROGRESS",
            "JOB_COMPLETED",
            "JOB_CANCELLED",
            "JOB_CLOSED",
            "JOB_REJECTED_BY_TECHNICIAN",
        ]

        cancelled = next(
            event
            for event in events
            if event["event_type"] == "JOB_CANCELLED"
        )
        assert cancelled["to_status"] == "CANCELLED"
        assert (
            cancelled["description"]
            == (
                "Job was cancelled. "
                "Reason: Customer requested cancellation"
            )
        )

        closed = next(
            event
            for event in events
            if event["event_type"] == "JOB_CLOSED"
        )
        assert closed["to_status"] == "CLOSED"
        assert (
            closed["description"]
            == (
                "Job was closed. "
                "Reason: Administrative closure"
            )
        )

        rejected = next(
            event
            for event in events
            if event["event_type"]
            == "JOB_REJECTED_BY_TECHNICIAN"
        )
        assert rejected["to_status"] == "REJECTED_BY_TECHNICIAN"
        assert (
            rejected["description"]
            == (
                "Technician rejected the assigned job. "
                "Reason: Technician unavailable"
            )
        )

        # False branches for each optional reason.
        plain_job = _timeline_job(
            created_at=base,
            cancelled_at=base + timedelta(minutes=1),
            closed_at=base + timedelta(minutes=2),
            rejected_at=base + timedelta(minutes=3),
            rejected_by_tech_id="tech-7",
        )

        plain_events = _job_lifecycle_events(
            None,
            plain_job,
        )

        cancelled_plain = next(
            event
            for event in plain_events
            if event["event_type"] == "JOB_CANCELLED"
        )

        closed_plain = next(
            event
            for event in plain_events
            if event["event_type"] == "JOB_CLOSED"
        )

        rejected_plain = next(
            event
            for event in plain_events
            if event["event_type"]
            == "JOB_REJECTED_BY_TECHNICIAN"
        )

        assert cancelled_plain["description"] == "Job was cancelled."
        assert closed_plain["description"] == "Job was closed."
        assert (
            rejected_plain["description"]
            == "Technician rejected the assigned job."
        )

    finally:
        timeline_service.LIFECYCLE_TIMESTAMP_FIELDS = original_fields


def test_job_lifecycle_covers_missing_to_status_branch(monkeypatch):
    """
    Exercise the false branch of the lifecycle status bookkeeping guard.

    Every canonical lifecycle event normally carries a to_status value, so
    the branch is reached by replacing the already-tested event builder with
    a narrowly scoped test double that removes the status from the built
    CREATED event. This leaves the production lifecycle logic untouched while
    proving the guard is safe when an event has no target status.
    """
    original_build_event = timeline_service._build_event

    def build_event_without_target_status(**kwargs):
        event = original_build_event(**kwargs)
        if kwargs["event_type"] == "JOB_CREATED":
            event["to_status"] = None
        return event

    monkeypatch.setattr(
        timeline_service,
        "_build_event",
        build_event_without_target_status,
    )

    base = datetime(
        2026,
        9,
        22,
        10,
        0,
        tzinfo=timezone.utc,
    )

    events = _job_lifecycle_events(
        None,
        _timeline_job(created_at=base),
    )

    assert len(events) == 1
    assert events[0]["event_type"] == "JOB_CREATED"
    assert events[0]["to_status"] is None


# ---------------------------------------------------------------------------
# AuditEvent coverage
# ---------------------------------------------------------------------------

def test_audit_event_items_covers_all_processing_paths(monkeypatch):
    technician = SimpleNamespace(
        technician_name="Audit Technician",
    )

    def resolve(db, tenant_id, identifier, cache):
        if identifier == "tech-1":
            return technician
        return None

    monkeypatch.setattr(
        timeline_service,
        "_resolve_technician",
        resolve,
    )

    base = datetime(
        2026,
        9,
        22,
        11,
        0,
        tzinfo=timezone.utc,
    )

    rows = [
        # No timestamp anywhere -> continue.
        SimpleNamespace(
            id=1,
            timestamp=None,
            created_at=None,
            event_type="IGNORED",
            old_status=None,
            new_status=None,
            reason=None,
            tech_id=None,
            actor_id=None,
        ),

        # Canonical completion event -> skip.
        SimpleNamespace(
            id=2,
            timestamp=base + timedelta(minutes=1),
            created_at=base,
            event_type="JOB_COMPLETED",
            old_status="IN_PROGRESS",
            new_status="COMPLETED",
            reason=None,
            tech_id=None,
            actor_id=None,
        ),

        # Status transition + technician actor.
        SimpleNamespace(
            id=3,
            timestamp=base + timedelta(minutes=2),
            created_at=base,
            event_type="JOB_STATUS_TRANSITION",
            old_status="ASSIGNED",
            new_status="EN_ROUTE",
            reason=None,
            tech_id="tech-1",
            actor_id=None,
        ),

        # SLA action + staff actor + reason.
        SimpleNamespace(
            id=4,
            timestamp=base + timedelta(minutes=3),
            created_at=base,
            event_type="SLA_BREACHED",
            old_status="EN_ROUTE",
            new_status="EN_ROUTE",
            reason="SLA breached for this job",
            tech_id=None,
            actor_id="staff-1",
        ),

        # Other action + system actor.
        SimpleNamespace(
            id=5,
            timestamp=base + timedelta(minutes=4),
            created_at=base,
            event_type="JOB_UPDATED",
            old_status=None,
            new_status=None,
            reason="Customer address updated",
            tech_id=None,
            actor_id=None,
        ),

        # Timestamp fallback to created_at + default AUDIT_EVENT.
        SimpleNamespace(
            id=6,
            timestamp=None,
            created_at=base + timedelta(minutes=5),
            event_type=None,
            old_status=None,
            new_status=None,
            reason=None,
            tech_id=None,
            actor_id=None,
        ),
    ]

    job = _timeline_job()
    db = FakeDB({AuditEvent: rows})

    events = _audit_event_items(db, job)

    assert [
        event["event_type"]
        for event in events
    ] == [
        "JOB_STATUS_TRANSITION",
        "SLA_BREACHED",
        "JOB_UPDATED",
        "AUDIT_EVENT",
    ]

    status_event = events[0]

    assert status_event["event_category"] == "STATUS"
    assert status_event["from_status"] == "ASSIGNED"
    assert status_event["to_status"] == "EN_ROUTE"
    assert status_event["actor_name"] == "Audit Technician"
    assert status_event["actor_role"] == "TECHNICIAN"

    sla_event = events[1]

    assert sla_event["event_category"] == "OTHER"
    assert sla_event["description"] == "SLA breached for this job"
    assert sla_event["actor_name"] == "Staff"
    assert sla_event["actor_role"] == "STAFF"

    updated_event = events[2]

    assert updated_event["title"] == "Job Updated"
    assert updated_event["description"] == "Customer address updated"
    assert updated_event["actor_name"] == "System"
    assert updated_event["actor_role"] == "SYSTEM"

    default_event = events[3]

    assert default_event["event_type"] == "AUDIT_EVENT"
    assert (
        default_event["description"]
        == "Recorded audit event: AUDIT_EVENT."
    )


# ---------------------------------------------------------------------------
# EnterpriseAuditLog coverage
# ---------------------------------------------------------------------------

def test_enterprise_audit_items_covers_all_mapped_and_fallback_actions(
    monkeypatch,
):
    monkeypatch.setattr(
        timeline_service,
        "_resolve_technician",
        lambda *args, **kwargs: None,
    )

    base = datetime(
        2026,
        9,
        22,
        12,
        0,
        tzinfo=timezone.utc,
    )

    rows = [
        # Missing timestamp -> continue.
        SimpleNamespace(
            id=1,
            action="JOB_UPDATED",
            timestamp=None,
            role="staff",
            old_value={},
            new_value={},
        ),

        # Canonical enterprise event -> continue.
        SimpleNamespace(
            id=2,
            action="JOB_CREATED",
            timestamp=base,
            role="staff",
            old_value={},
            new_value={},
        ),

        SimpleNamespace(
            id=3,
            action="JOB_ACCEPTED",
            timestamp=base + timedelta(minutes=1),
            role=SimpleNamespace(value="technician"),
            old_value=None,
            new_value={},
        ),

        SimpleNamespace(
            id=4,
            action="JOB_STARTED",
            timestamp=base + timedelta(minutes=2),
            role="staff",
            old_value="not-a-dict",
            new_value={},
        ),

        SimpleNamespace(
            id=5,
            action="JOB_PAUSED",
            timestamp=base + timedelta(minutes=3),
            role="staff",
            old_value={},
            new_value=None,
        ),

        SimpleNamespace(
            id=6,
            action="JOB_RESUMED",
            timestamp=base + timedelta(minutes=4),
            role="staff",
            old_value={},
            new_value={"status": "IN_PROGRESS"},
        ),

        SimpleNamespace(
            id=7,
            action="JOB_REJECTED",
            timestamp=base + timedelta(minutes=5),
            role="staff",
            old_value={},
            new_value={},
        ),

        SimpleNamespace(
            id=8,
            action="JOB_REJECTED_BY_TECHNICIAN",
            timestamp=base + timedelta(minutes=6),
            role="staff",
            old_value={},
            new_value={"status": None},
        ),

        SimpleNamespace(
            id=9,
            action="JOB_REASSIGNED",
            timestamp=base + timedelta(minutes=7),
            role="staff",
            old_value={"status": "ASSIGNED"},
            new_value={"status": "ASSIGNED"},
        ),

        SimpleNamespace(
            id=10,
            action="JOB_REASSIGNED_FROM_DECLINED",
            timestamp=base + timedelta(minutes=8),
            role="staff",
            old_value={},
            new_value={},
        ),

        SimpleNamespace(
            id=11,
            action="JOB_UPDATED",
            timestamp=base + timedelta(minutes=9),
            role="staff",
            old_value={},
            new_value={"field": "priority"},
        ),

        # Unmapped enterprise action.
        SimpleNamespace(
            id=12,
            action="JOB_CUSTOM_ACTION",
            timestamp=base + timedelta(minutes=10),
            role="staff",
            old_value={"status": "A"},
            new_value={"status": "B"},
        ),
    ]

    job = _timeline_job()
    db = FakeDB({EnterpriseAuditLog: rows})

    events = _enterprise_audit_items(db, job)

    assert [
        event["event_type"]
        for event in events
    ] == [
        "JOB_ACCEPTED",
        "JOB_STARTED",
        "JOB_PAUSED",
        "JOB_RESUMED",
        "JOB_REJECTED",
        "JOB_REJECTED_BY_TECHNICIAN",
        "JOB_REASSIGNED",
        "JOB_REASSIGNED_FROM_DECLINED",
        "JOB_UPDATED",
        "JOB_CUSTOM_ACTION",
    ]

    accepted = events[0]
    assert accepted["to_status"] == "ACCEPTED"
    assert accepted["actor_name"] == "Technician"
    assert accepted["actor_role"] == "TECHNICIAN"

    started = events[1]
    assert started["to_status"] == "EN_ROUTE"
    assert (
        started["description"]
        == "Technician started the job journey."
    )

    paused = events[2]
    assert paused["to_status"] == "PAUSED"

    resumed = events[3]
    assert resumed["to_status"] == "IN_PROGRESS"
    assert resumed["description"] == "Job was resumed."

    rejected = events[4]
    assert rejected["to_status"] == "REJECTED_BY_TECHNICIAN"

    rejected_by_technician = events[5]
    assert (
        rejected_by_technician["to_status"]
        == "REJECTED_BY_TECHNICIAN"
    )

    reassigned = events[6]
    assert reassigned["event_category"] == "ASSIGNMENT"
    assert (
        reassigned["description"]
        == "Technician assignment was changed."
    )

    reassigned_declined = events[7]
    assert (
        reassigned_declined["event_type"]
        == "JOB_REASSIGNED_FROM_DECLINED"
    )

    updated = events[8]
    assert updated["event_category"] == "OTHER"
    assert (
        updated["description"]
        == "Job details were updated."
    )

    custom = events[9]
    assert custom["title"] == "Job Custom Action"
    assert (
        custom["description"]
        == "Recorded audit action: JOB_CUSTOM_ACTION."
    )
    assert custom["from_status"] == "A"
    assert custom["to_status"] == "B"


def test_enterprise_audit_items_resolves_tenant_scoped_technician_identity(
    monkeypatch,
):
    """
    Verify technician actions in EnterpriseAuditLog resolve to the technician
    identity through the existing tenant-scoped resolver.
    """
    enterprise_technician = SimpleNamespace(
        technician_name="Enterprise Technician",
    )

    def resolve(db, tenant_id, identifier, cache):
        assert tenant_id == "tenant-1"
        if identifier == "enterprise-tech-1":
            return enterprise_technician
        return None

    monkeypatch.setattr(
        timeline_service,
        "_resolve_technician",
        resolve,
    )

    base = datetime(
        2026,
        9,
        22,
        12,
        30,
        tzinfo=timezone.utc,
    )

    row = SimpleNamespace(
        id=30,
        action="JOB_ACCEPTED",
        timestamp=base,
        role=SimpleNamespace(value="technician"),
        user_id="enterprise-tech-1",
        old_value={"status": "ASSIGNED"},
        new_value={"status": "ACCEPTED"},
    )

    events = _enterprise_audit_items(
        FakeDB({EnterpriseAuditLog: [row]}),
        _timeline_job(),
    )

    assert len(events) == 1
    event = events[0]

    assert event["event_type"] == "JOB_ACCEPTED"
    assert event["event_category"] == "STATUS"
    assert event["actor_name"] == "Enterprise Technician"
    assert event["actor_role"] == "TECHNICIAN"
    assert event["to_status"] == "ACCEPTED"
    assert event["source"] == "enterprise_audit"


# ---------------------------------------------------------------------------
# AssignmentOverride coverage
# ---------------------------------------------------------------------------

def test_assignment_override_items_covers_missing_and_valid_created_at():
    base = datetime(
        2026,
        9,
        22,
        13,
        0,
        tzinfo=timezone.utc,
    )

    rows = [
        SimpleNamespace(
            id=1,
            created_at=None,
            previous_technician_name="Old Tech",
            new_technician_name="New Tech",
            actor_name="Dispatcher",
            actor_role="dispatcher",
        ),
        SimpleNamespace(
            id=2,
            created_at=base,
            previous_technician_name=None,
            new_technician_name="New Tech",
            actor_name="Dispatcher",
            actor_role="dispatcher",
        ),
    ]

    db = FakeDB({AssignmentOverride: rows})
    job = _timeline_job()

    events = _assignment_override_items(db, job)

    assert len(events) == 1

    event = events[0]

    assert event["event_type"] == "ASSIGNMENT_OVERRIDE"
    assert event["event_category"] == "ASSIGNMENT"
    assert (
        event["description"]
        == "Assignment changed from unassigned to New Tech."
    )
    assert event["actor_name"] == "Dispatcher"
    assert event["actor_role"] == "DISPATCHER"


# ---------------------------------------------------------------------------
# JobClosure coverage
# ---------------------------------------------------------------------------

def test_closure_items_covers_missing_and_valid_created_at():
    base = datetime(
        2026,
        9,
        22,
        14,
        0,
        tzinfo=timezone.utc,
    )

    rows = [
        SimpleNamespace(
            id=1,
            created_at=None,
        ),
        SimpleNamespace(
            id=2,
            created_at=base,
        ),
    ]

    db = FakeDB({JobClosure: rows})
    job = _timeline_job()

    events = _closure_items(db, job)

    assert len(events) == 1

    event = events[0]

    assert event["event_type"] == "CLOSURE_RECORDED"
    assert event["event_category"] == "COMPLETION"
    assert event["from_status"] == "COMPLETED"
    assert event["to_status"] == "COMPLETED"
    assert event["actor_name"] == "Technician"
    assert event["actor_role"] == "TECHNICIAN"


# ---------------------------------------------------------------------------
# SLA coverage
# ---------------------------------------------------------------------------

def test_sla_items_covers_all_escalation_milestones():
    base = datetime(
        2026,
        9,
        22,
        15,
        0,
        tzinfo=timezone.utc,
    )

    row = SimpleNamespace(
        id=1,
        created_at=base,
        manager_notified_at=base + timedelta(minutes=1),
        manager_responded_at=base + timedelta(minutes=2),
        cto_notified_at=base + timedelta(minutes=3),
    )

    # Exercise the false branch of each optional escalation milestone.
    row_without_milestones = SimpleNamespace(
        id=2,
        created_at=base + timedelta(minutes=4),
        manager_notified_at=None,
        manager_responded_at=None,
        cto_notified_at=None,
    )

    db = FakeDB({
        SLAEscalation: [row, row_without_milestones],
    })
    job = _timeline_job()

    events = _sla_items(db, job)

    assert [
        event["event_type"]
        for event in events
    ] == [
        "SLA_MANAGER_NOTIFIED",
        "SLA_MANAGER_RESPONDED",
        "SLA_CTO_NOTIFIED",
    ]

    assert events[0]["event_category"] == "OTHER"
    assert events[0]["actor_name"] == "System"
    assert events[0]["actor_role"] == "SYSTEM"

    assert (
        events[1]["description"]
        == "Manager response to SLA escalation was recorded."
    )
    assert events[1]["actor_name"] == "Staff"
    assert events[1]["actor_role"] == "STAFF"

    assert (
        events[2]["description"]
        == "SLA escalation notified the CTO."
    )


# ---------------------------------------------------------------------------
# Existing integration coverage
# ---------------------------------------------------------------------------

def test_build_job_timeline_merges_sources_in_timestamp_order():
    db = SessionLocal()

    try:
        job = _job(db)

        created = datetime(
            2026,
            9,
            22,
            8,
            0,
            tzinfo=timezone.utc,
        )

        assigned = created + timedelta(minutes=10)
        en_route = created + timedelta(minutes=20)
        in_progress = created + timedelta(minutes=35)
        completed = created + timedelta(minutes=60)

        job.created_at = created
        job.assigned_at = assigned
        job.en_route_at = en_route
        job.on_site_at = in_progress
        job.completed_at = completed

        job.assigned_by = "dispatcher-1"
        job.en_route_by = "tech-1"
        job.on_site_by = "tech-1"
        job.completed_by = "tech-1"

        db.commit()
        db.refresh(job)

        events = build_job_timeline(db, job)

        assert [
            event["event_type"]
            for event in events
        ] == [
            "JOB_CREATED",
            "JOB_ASSIGNED",
            "JOB_EN_ROUTE",
            "JOB_IN_PROGRESS",
            "JOB_COMPLETED",
        ]

        assert [
            event["timestamp"]
            for event in events
        ] == [
            created.isoformat(),
            assigned.isoformat(),
            en_route.isoformat(),
            in_progress.isoformat(),
            completed.isoformat(),
        ]

        en_route_events = [
            event
            for event in events
            if event["event_type"] == "JOB_EN_ROUTE"
        ]

        assert len(en_route_events) == 1
        assert (
            en_route_events[0]["timestamp"]
            == en_route.isoformat()
        )

        in_progress_events = [
            event
            for event in events
            if event["event_type"] == "JOB_IN_PROGRESS"
        ]

        assert len(in_progress_events) == 1
        assert (
            in_progress_events[0]["timestamp"]
            == in_progress.isoformat()
        )
        assert (
            in_progress_events[0]["to_status"]
            == "IN_PROGRESS"
        )

        assert events[-1]["event_type"] == "JOB_COMPLETED"
        assert events[-1]["to_status"] == "COMPLETED"
        assert events[-1]["is_current"] is True

        assert all(
            "details" not in event
            for event in events
        )

    finally:
        db.close()


def test_build_job_timeline_includes_override_and_closure_without_raw_sensitive_fields():
    db = SessionLocal()

    try:
        job = _job(db)

        created = datetime(
            2026,
            9,
            22,
            9,
            0,
            tzinfo=timezone.utc,
        )

        override_at = created + timedelta(minutes=15)
        completed = created + timedelta(hours=1)
        closure_at = completed + timedelta(minutes=5)

        job.created_at = created
        job.completed_at = completed

        db.add(
            AssignmentOverride(
                tenant_id="tenant-1",
                job_id=job.id,
                actor_name="Dispatcher",
                actor_role="dispatcher",
                justification="Sensitive internal justification",
                previous_technician_id=1,
                previous_technician_name="Old Tech",
                new_technician_id=2,
                new_technician_name="New Tech",
                created_at=override_at,
            )
        )

        db.add(
            JobClosure(
                job_id=job.id,
                tenant_id="tenant-1",
                completed_at=completed,
                created_at=closure_at,
                work_summary="Customer-facing work summary",
                after_images=[],
            )
        )

        db.commit()

        events = build_job_timeline(db, job)

        event_types = [
            event["event_type"]
            for event in events
        ]

        assert "ASSIGNMENT_OVERRIDE" in event_types
        assert "CLOSURE_RECORDED" in event_types

        assert all(
            "justification" not in event
            for event in events
        )

        assert all(
            "previous_technician_name" not in event
            for event in events
        )

        assert all(
            "new_technician_name" not in event
            for event in events
        )

    finally:
        db.close()


# ---------------------------------------------------------------------------
# Final sorting/current-state coverage
# ---------------------------------------------------------------------------

def test_build_job_timeline_sorts_missing_timestamp_last_and_marks_current(
    monkeypatch,
):
    base = datetime(
        2026,
        9,
        22,
        16,
        0,
        tzinfo=timezone.utc,
    )

    monkeypatch.setattr(
        timeline_service,
        "_job_lifecycle_events",
        lambda db, job: [
            _event(
                "known:1",
                base,
                to_status="IN_PROGRESS",
            )
        ],
    )

    monkeypatch.setattr(
        timeline_service,
        "_audit_event_items",
        lambda db, job: [
            _event(
                "missing:1",
                None,
                category="OTHER",
            )
        ],
    )

    monkeypatch.setattr(
        timeline_service,
        "_enterprise_audit_items",
        lambda db, job: [],
    )

    monkeypatch.setattr(
        timeline_service,
        "_assignment_override_items",
        lambda db, job: [],
    )

    monkeypatch.setattr(
        timeline_service,
        "_closure_items",
        lambda db, job: [],
    )

    monkeypatch.setattr(
        timeline_service,
        "_sla_items",
        lambda db, job: [],
    )

    job = _timeline_job(
        status="IN_PROGRESS",
    )

    events = build_job_timeline(None, job)

    assert events[0]["id"] == "known:1"
    assert events[0]["is_current"] is True

    assert events[1]["id"] == "missing:1"
    assert events[1]["timestamp"] is None
    assert events[1]["is_current"] is False


# ---------------------------------------------------------------------------
# Task 3: assignment/reassignment endpoint and identity coverage
# ---------------------------------------------------------------------------

def test_audit_event_items_assignment_identity_outcome_and_reason(monkeypatch):
    reassigned_technician = SimpleNamespace(
        technician_name="Rahul Kumar",
    )
    declined_reassignment_technician = SimpleNamespace(
        technician_name="Arun Kumar",
    )

    def resolve(db, tenant_id, identifier, cache):
        mapping = {
            "tech-reassigned": reassigned_technician,
            "tech-reassigned-after-decline": (
                declined_reassignment_technician
            ),
        }
        return mapping.get(identifier)

    monkeypatch.setattr(
        timeline_service,
        "_resolve_technician",
        resolve,
    )

    base = datetime(
        2026,
        9,
        24,
        10,
        0,
        tzinfo=timezone.utc,
    )

    rows = [
        SimpleNamespace(
            id=21,
            timestamp=base,
            created_at=base,
            event_type="JOB_REASSIGNED",
            old_status="ASSIGNED",
            new_status="ASSIGNED",
            reason="Dispatcher reassigned after routing conflict",
            tech_id="tech-reassigned",
            actor_id=None,
        ),
        SimpleNamespace(
            id=22,
            timestamp=base + timedelta(minutes=5),
            created_at=base + timedelta(minutes=5),
            event_type="JOB_REASSIGNED_FROM_DECLINED",
            old_status="REJECTED_BY_TECHNICIAN",
            new_status="ASSIGNED",
            reason="Original technician declined",
            tech_id="tech-reassigned-after-decline",
            actor_id=None,
        ),
    ]

    events = _audit_event_items(
        FakeDB({AuditEvent: rows}),
        _timeline_job(),
    )

    assert [
        event["event_type"]
        for event in events
    ] == [
        "JOB_REASSIGNED",
        "JOB_REASSIGNED_FROM_DECLINED",
    ]

    first = events[0]

    assert first["event_category"] == "ASSIGNMENT"
    assert first["timestamp"] == base.isoformat()
    assert first["actor_name"] == "Rahul Kumar"
    assert first["actor_role"] == "TECHNICIAN"
    assert first["to_status"] == "ASSIGNED"
    assert (
        first["description"]
        == (
            "Job was reassigned to Rahul Kumar. "
            "Reason: Dispatcher reassigned after routing conflict."
        )
    )

    second = events[1]

    assert second["event_category"] == "ASSIGNMENT"
    assert second["timestamp"] == (
        base + timedelta(minutes=5)
    ).isoformat()
    assert second["actor_name"] == "Arun Kumar"
    assert second["actor_role"] == "TECHNICIAN"
    assert second["to_status"] == "ASSIGNED"
    assert (
        second["description"]
        == (
            "Job was reassigned after technician decline to Arun Kumar. "
            "Reason: Original technician declined."
        )
    )


def test_audit_event_items_assignment_fallback_actor_without_reason(monkeypatch):
    """Cover fallback assignment actor and the no-reason branch."""
    monkeypatch.setattr(
        timeline_service,
        "_resolve_technician",
        lambda *args, **kwargs: None,
    )

    base = datetime(
        2026,
        9,
        24,
        11,
        0,
        tzinfo=timezone.utc,
    )

    row = SimpleNamespace(
        id=31,
        timestamp=base,
        created_at=base,
        event_type="JOB_REASSIGNED",
        old_status="ASSIGNED",
        new_status="ASSIGNED",
        reason=None,
        tech_id="unknown-tech",
        actor_id=None,
    )

    events = _audit_event_items(
        FakeDB({AuditEvent: [row]}),
        _timeline_job(),
    )

    assert len(events) == 1
    event = events[0]

    assert event["event_type"] == "JOB_REASSIGNED"
    assert event["event_category"] == "ASSIGNMENT"
    assert event["actor_name"] == "System"
    assert event["actor_role"] == "SYSTEM"
    assert event["description"] == "Job was reassigned."


def test_get_job_timeline_endpoint_filters_and_paginates_assignment_events(
    monkeypatch,
):
    from app.routes.jobs import get_job_timeline

    db = SessionLocal()

    try:
        job = _job(db)

        events = [
            {
                "id": "assignment:1",
                "job_id": job.id,
                "event_type": "JOB_REASSIGNED",
                "event_category": "ASSIGNMENT",
                "title": "Technician Reassigned",
                "description": "Job was reassigned to Rahul Kumar.",
                "timestamp": "2026-09-24T10:00:00+00:00",
                "from_status": "ASSIGNED",
                "to_status": "ASSIGNED",
                "actor_name": "Rahul Kumar",
                "actor_role": "TECHNICIAN",
                "source": "audit_event",
                "is_current": False,
            },
            {
                "id": "assignment:2",
                "job_id": job.id,
                "event_type": "JOB_REASSIGNED_FROM_DECLINED",
                "event_category": "ASSIGNMENT",
                "title": "Job Reassigned After Decline",
                "description": (
                    "Job was reassigned after technician decline "
                    "to Arun Kumar."
                ),
                "timestamp": "2026-09-24T10:05:00+00:00",
                "from_status": "REJECTED_BY_TECHNICIAN",
                "to_status": "ASSIGNED",
                "actor_name": "Arun Kumar",
                "actor_role": "TECHNICIAN",
                "source": "audit_event",
                "is_current": False,
            },
            {
                "id": "status:1",
                "job_id": job.id,
                "event_type": "JOB_IN_PROGRESS",
                "event_category": "STATUS",
                "title": "Job In Progress",
                "description": "Job entered IN_PROGRESS.",
                "timestamp": "2026-09-24T10:10:00+00:00",
                "from_status": "ASSIGNED",
                "to_status": "IN_PROGRESS",
                "actor_name": "Arun Kumar",
                "actor_role": "TECHNICIAN",
                "source": "job_lifecycle",
                "is_current": True,
            },
        ]

        monkeypatch.setattr(
            timeline_service,
            "build_job_timeline",
            lambda db, job: events,
        )

        response = get_job_timeline(
            job_id=job.id,
            category=" assignment ",
            page=2,
            page_size=1,
            current_user=SimpleNamespace(
                tenant_id="tenant-1",
            ),
            db=db,
        )

        assert response["job_id"] == job.id
        assert response["page"] == 2
        assert response["page_size"] == 1
        assert response["total"] == 2
        assert response["has_more"] is False
        assert len(response["events"]) == 1
        assert response["events"][0]["id"] == "assignment:2"
        assert response["events"][0]["actor_name"] == "Arun Kumar"

    finally:
        db.close()


def test_get_job_timeline_endpoint_returns_unfiltered_events_and_has_more(
    monkeypatch,
):
    """Cover the no-category endpoint branch and the has_more=True path."""
    from app.routes.jobs import get_job_timeline

    db = SessionLocal()

    try:
        job = _job(db)

        events = [
            {
                "id": "event:1",
                "job_id": job.id,
                "event_type": "JOB_CREATED",
                "event_category": "CREATION",
                "title": "Job Created",
                "description": "Job record was created.",
                "timestamp": "2026-09-24T09:00:00+00:00",
                "from_status": None,
                "to_status": "CREATED",
                "actor_name": "System",
                "actor_role": "SYSTEM",
                "source": "job",
                "is_current": False,
            },
            {
                "id": "event:2",
                "job_id": job.id,
                "event_type": "JOB_ASSIGNED",
                "event_category": "ASSIGNMENT",
                "title": "Technician Assigned",
                "description": "Job was assigned to Vijay Iyer.",
                "timestamp": "2026-09-24T09:05:00+00:00",
                "from_status": "CREATED",
                "to_status": "ASSIGNED",
                "actor_name": "Vijay Iyer",
                "actor_role": "TECHNICIAN",
                "source": "job",
                "is_current": True,
            },
        ]

        monkeypatch.setattr(
            timeline_service,
            "build_job_timeline",
            lambda db, job: events,
        )

        response = get_job_timeline(
            job_id=job.id,
            category=None,
            page=1,
            page_size=1,
            current_user=SimpleNamespace(
                tenant_id="tenant-1",
            ),
            db=db,
        )

        assert response["job_id"] == job.id
        assert response["page"] == 1
        assert response["page_size"] == 1
        assert response["total"] == 2
        assert response["has_more"] is True
        assert len(response["events"]) == 1
        assert response["events"][0]["id"] == "event:1"
        assert response["events"][0]["event_category"] == "CREATION"

    finally:
        db.close()


def test_get_job_timeline_endpoint_enforces_tenant_and_category_validation(
    monkeypatch,
):
    from fastapi import HTTPException
    from app.routes.jobs import get_job_timeline

    db = SessionLocal()

    try:
        job = _job(db)

        monkeypatch.setattr(
            timeline_service,
            "build_job_timeline",
            lambda db, job: [],
        )

        with pytest.raises(HTTPException) as tenant_error:
            get_job_timeline(
                job_id=job.id,
                category=None,
                page=1,
                page_size=25,
                current_user=SimpleNamespace(
                    tenant_id="tenant-2",
                ),
                db=db,
            )

        assert tenant_error.value.status_code == 404
        assert tenant_error.value.detail == "Job not found"

        with pytest.raises(HTTPException) as category_error:
            get_job_timeline(
                job_id=job.id,
                category="UNKNOWN_CATEGORY",
                page=1,
                page_size=25,
                current_user=SimpleNamespace(
                    tenant_id="tenant-1",
                ),
                db=db,
            )

        assert category_error.value.status_code == 400
        assert "Invalid timeline category" in (
            category_error.value.detail
        )

    finally:
        db.close()


def test_get_job_timeline_route_declares_jobs_view_all_permission():
    import inspect

    from app.auth.rbac import Permission
    from app.routes.jobs import get_job_timeline

    source = inspect.getsource(get_job_timeline)

    assert (
        "require_permission(Permission.JOBS_VIEW_ALL)"
        in source
    )
# ---------------------------------------------------------------------------
# Task 4: permitted audit history endpoint coverage
# ---------------------------------------------------------------------------

def _audit_history_event(
    event_id,
    event_type,
    source,
    *,
    category="OTHER",
    timestamp="2026-09-24T12:00:00+00:00",
    description="Permitted audit event.",
):
    return {
        "id": event_id,
        "job_id": 1,
        "event_type": event_type,
        "event_category": category,
        "title": event_type.replace("_", " ").title(),
        "description": description,
        "timestamp": timestamp,
        "from_status": "ASSIGNED",
        "to_status": "ASSIGNED",
        "actor_name": "Dispatcher",
        "actor_role": "DISPATCHER",
        "source": source,
        "is_current": False,
    }


def test_get_job_audit_history_returns_only_permitted_normalized_audit_fields(
    monkeypatch,
):
    from app.routes.jobs import get_job_audit_history

    db = SessionLocal()

    try:
        job = _job(db)

        source_events = [
            _audit_history_event(
                "audit:1",
                "JOB_UPDATED",
                "audit_event",
                description="Job details were updated.",
            ),
            _audit_history_event(
                "enterprise:2",
                "JOB_REASSIGNED",
                "enterprise_audit",
                category="ASSIGNMENT",
                description="Technician assignment was changed.",
            ),
            _audit_history_event(
                "assignment-override:3",
                "ASSIGNMENT_OVERRIDE",
                "assignment_override",
                category="ASSIGNMENT",
                description="Assignment changed from Old Tech to New Tech.",
            ),
            {
                **_audit_history_event(
                    "job:4",
                    "JOB_CREATED",
                    "job_lifecycle",
                    category="CREATION",
                    description="Job record was created.",
                ),
                "details": {
                    "internal_ip": "10.0.0.1",
                    "secret": "do-not-expose",
                },
                "user_email": "internal@example.com",
                "user_id": "internal-user-id",
                "old_value": {"status": "QUEUED"},
                "new_value": {"status": "ACTIVE"},
            },
        ]

        monkeypatch.setattr(
            timeline_service,
            "build_job_timeline",
            lambda db, job: source_events,
        )

        response = get_job_audit_history(
            job_id=job.id,
            event_type=None,
            source=None,
            page=1,
            page_size=25,
            current_user=SimpleNamespace(tenant_id="tenant-1"),
            db=db,
        )

        assert response["job_id"] == job.id
        assert response["total"] == 3
        assert response["has_more"] is False
        assert [
            event["source"]
            for event in response["events"]
        ] == [
            "audit_event",
            "enterprise_audit",
            "assignment_override",
        ]

        allowed_keys = {
            "id",
            "job_id",
            "event_type",
            "event_category",
            "title",
            "description",
            "timestamp",
            "from_status",
            "to_status",
            "actor_name",
            "actor_role",
            "source",
            "is_current",
        }

        for event in response["events"]:
            assert set(event.keys()) == allowed_keys
            assert "details" not in event
            assert "user_email" not in event
            assert "user_id" not in event
            assert "old_value" not in event
            assert "new_value" not in event

    finally:
        db.close()


def test_get_job_audit_history_filters_by_event_type(monkeypatch):
    from app.routes.jobs import get_job_audit_history

    db = SessionLocal()

    try:
        job = _job(db)

        events = [
            _audit_history_event(
                "audit:1",
                "JOB_UPDATED",
                "audit_event",
            ),
            _audit_history_event(
                "audit:2",
                "JOB_REASSIGNED",
                "audit_event",
                category="ASSIGNMENT",
            ),
            _audit_history_event(
                "enterprise:3",
                "JOB_REASSIGNED",
                "enterprise_audit",
                category="ASSIGNMENT",
            ),
        ]

        monkeypatch.setattr(
            timeline_service,
            "build_job_timeline",
            lambda db, job: events,
        )

        response = get_job_audit_history(
            job_id=job.id,
            event_type=" job_reassigned ",
            source=None,
            page=1,
            page_size=25,
            current_user=SimpleNamespace(tenant_id="tenant-1"),
            db=db,
        )

        assert response["total"] == 2
        assert all(
            event["event_type"] == "JOB_REASSIGNED"
            for event in response["events"]
        )

    finally:
        db.close()


def test_get_job_audit_history_filters_by_source(monkeypatch):
    from app.routes.jobs import get_job_audit_history

    db = SessionLocal()

    try:
        job = _job(db)

        events = [
            _audit_history_event(
                "audit:1",
                "JOB_REASSIGNED",
                "audit_event",
                category="ASSIGNMENT",
            ),
            _audit_history_event(
                "enterprise:2",
                "JOB_REASSIGNED",
                "enterprise_audit",
                category="ASSIGNMENT",
            ),
            _audit_history_event(
                "override:3",
                "ASSIGNMENT_OVERRIDE",
                "assignment_override",
                category="ASSIGNMENT",
            ),
        ]

        monkeypatch.setattr(
            timeline_service,
            "build_job_timeline",
            lambda db, job: events,
        )

        response = get_job_audit_history(
            job_id=job.id,
            event_type=None,
            source=" ENTERPRISE_AUDIT ",
            page=1,
            page_size=25,
            current_user=SimpleNamespace(tenant_id="tenant-1"),
            db=db,
        )

        assert response["total"] == 1
        assert response["events"][0]["source"] == "enterprise_audit"
        assert response["events"][0]["event_type"] == "JOB_REASSIGNED"

    finally:
        db.close()


def test_get_job_audit_history_rejects_invalid_source():
    from fastapi import HTTPException
    from app.routes.jobs import get_job_audit_history

    db = SessionLocal()

    try:
        job = _job(db)

        with pytest.raises(HTTPException) as exc_info:
            get_job_audit_history(
                job_id=job.id,
                event_type=None,
                source="internal_database",
                page=1,
                page_size=25,
                current_user=SimpleNamespace(tenant_id="tenant-1"),
                db=db,
            )

        assert exc_info.value.status_code == 400
        assert "Invalid audit history source" in exc_info.value.detail

    finally:
        db.close()


def test_get_job_audit_history_enforces_tenant_object_access(monkeypatch):
    from fastapi import HTTPException
    from app.routes.jobs import get_job_audit_history

    db = SessionLocal()

    try:
        job = _job(db)

        monkeypatch.setattr(
            timeline_service,
            "build_job_timeline",
            lambda db, job: [],
        )

        with pytest.raises(HTTPException) as exc_info:
            get_job_audit_history(
                job_id=job.id,
                event_type=None,
                source=None,
                page=1,
                page_size=25,
                current_user=SimpleNamespace(tenant_id="tenant-2"),
                db=db,
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Job not found"

    finally:
        db.close()


def test_get_job_audit_history_paginates_and_reports_has_more(monkeypatch):
    from app.routes.jobs import get_job_audit_history

    db = SessionLocal()

    try:
        job = _job(db)

        events = [
            _audit_history_event(
                f"audit:{index}",
                "JOB_UPDATED",
                "audit_event",
                timestamp=f"2026-09-24T12:{index:02d}:00+00:00",
            )
            for index in range(1, 4)
        ]

        monkeypatch.setattr(
            timeline_service,
            "build_job_timeline",
            lambda db, job: events,
        )

        first_page = get_job_audit_history(
            job_id=job.id,
            event_type=None,
            source=None,
            page=1,
            page_size=2,
            current_user=SimpleNamespace(tenant_id="tenant-1"),
            db=db,
        )

        second_page = get_job_audit_history(
            job_id=job.id,
            event_type=None,
            source=None,
            page=2,
            page_size=2,
            current_user=SimpleNamespace(tenant_id="tenant-1"),
            db=db,
        )

        assert first_page["total"] == 3
        assert first_page["page"] == 1
        assert first_page["page_size"] == 2
        assert first_page["has_more"] is True
        assert len(first_page["events"]) == 2

        assert second_page["page"] == 2
        assert second_page["has_more"] is False
        assert len(second_page["events"]) == 1
        assert second_page["events"][0]["id"] == "audit:3"

    finally:
        db.close()


def test_get_job_audit_history_returns_empty_result_without_synthetic_events(
    monkeypatch,
):
    from app.routes.jobs import get_job_audit_history

    db = SessionLocal()

    try:
        job = _job(db)

        monkeypatch.setattr(
            timeline_service,
            "build_job_timeline",
            lambda db, job: [],
        )

        response = get_job_audit_history(
            job_id=job.id,
            event_type=None,
            source=None,
            page=1,
            page_size=25,
            current_user=SimpleNamespace(tenant_id="tenant-1"),
            db=db,
        )

        assert response["job_id"] == job.id
        assert response["events"] == []
        assert response["total"] == 0
        assert response["has_more"] is False

    finally:
        db.close()


def test_get_job_audit_history_declares_audit_view_permission():
    import inspect
    from app.routes.jobs import get_job_audit_history

    source = inspect.getsource(get_job_audit_history)

    assert (
        "require_permission(Permission.AUDIT_VIEW)"
        in source
    )


def test_get_job_audit_history_does_not_expose_raw_sensitive_names_or_payloads(
    monkeypatch,
):
    from app.routes.jobs import get_job_audit_history

    db = SessionLocal()

    try:
        job = _job(db)

        event = {
            **_audit_history_event(
                "enterprise:77",
                "JOB_UPDATED",
                "enterprise_audit",
                description="Safe normalized description.",
            ),
            "user_id": "super-sensitive-user-id",
            "user_email": "person@example.com",
            "old_value": {"password": "secret"},
            "new_value": {"token": "secret-token"},
            "details": {
                "ip_address": "192.168.1.10",
                "internal_trace": "trace-data",
            },
        }

        monkeypatch.setattr(
            timeline_service,
            "build_job_timeline",
            lambda db, job: [event],
        )

        response = get_job_audit_history(
            job_id=job.id,
            event_type=None,
            source=None,
            page=1,
            page_size=25,
            current_user=SimpleNamespace(tenant_id="tenant-1"),
            db=db,
        )

        returned = response["events"][0]

        assert returned["description"] == "Safe normalized description."
        assert returned["actor_name"] == "Dispatcher"

        forbidden_keys = {
            "user_id",
            "user_email",
            "old_value",
            "new_value",
            "details",
            "ip_address",
            "internal_trace",
        }

        assert forbidden_keys.isdisjoint(returned.keys())

    finally:
        db.close()
