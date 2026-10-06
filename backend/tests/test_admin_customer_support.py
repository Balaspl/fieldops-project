"""Focused tests for staff-facing customer support management."""

import asyncio
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.auth.dependencies import AuthenticatedUser
from app.auth.rbac import UserRole
from app.models import (
    CustomerSupportRequest,
    InAppNotification,
    Job,
    Technician,
    User,
)
from app.portal_schemas import (
    CustomerSupportRequestAdminResponse,
    CustomerSupportRequestUpdate,
)
from app.routes.admin_customer_support import (
    _build_admin_response,
    _require_support_staff,
    get_customer_support_request_for_staff,
    list_customer_support_requests_for_staff,
    update_customer_support_request_for_staff,
)


class FakeQuery:
    def __init__(self, *, first=None, all_=None):
        self._first = first
        self._all = list(all_ or [])
        self.filters = []

    def filter(self, *expressions):
        self.filters.extend(expressions)
        return self

    def order_by(self, *expressions):
        return self

    def limit(self, value):
        return self

    def first(self):
        return self._first

    def all(self):
        return list(self._all)


class FakeDB:
    def __init__(
        self,
        *,
        support_request,
        customer=None,
        job=None,
        technician=None,
    ):
        self.support_query = FakeQuery(
            first=support_request,
            all_=[support_request],
        )
        self.customer_query = FakeQuery(first=customer)
        self.job_query = FakeQuery(first=job)
        self.technician_query = FakeQuery(first=technician)
        self.queries = []
        self.added = []
        self.commit_count = 0
        self.refresh_count = 0
        self.rollback_count = 0

    def query(self, model):
        if model is CustomerSupportRequest:
            query = self.support_query
        elif model is User:
            query = self.customer_query
        elif model is Job:
            query = self.job_query
        elif model is Technician:
            query = self.technician_query
        else:
            query = FakeQuery()

        self.queries.append((model, query))
        return query

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commit_count += 1

    def refresh(self, obj):
        self.refresh_count += 1

    def rollback(self):
        self.rollback_count += 1


def user(
    role: UserRole,
    tenant_id: str = "tenant-1",
    user_id: str | None = None,
):
    return AuthenticatedUser(
        user_id=(
            user_id
            or ("customer-1" if role == UserRole.CUSTOMER else "staff-1")
        ),
        tenant_id=tenant_id,
        role=role,
        jti="support-test-jti",
        session_id="support-test-session",
    )


def support(*, tenant_id="tenant-1"):
    return SimpleNamespace(
        id=11,
        request_number="SUP-TEST-001",
        customer_user_id="customer-1",
        tenant_id=tenant_id,
        subject="Invoice problem",
        description="Please check the invoice amount for my completed service.",
        status="OPEN",
        related_job_id=101,
        resolution_note=None,
        resolved_at=None,
        resolved_by=None,
        created_at=datetime(
            2026,
            10,
            6,
            10,
            0,
            tzinfo=timezone.utc,
        ),
        updated_at=datetime(
            2026,
            10,
            6,
            10,
            0,
            tzinfo=timezone.utc,
        ),
    )


def customer():
    return SimpleNamespace(
        id="customer-1",
        tenant_id="tenant-1",
        first_name="Test",
        last_name="Customer",
        email="customer@example.com",
        phone_number="9876543210",
        full_name="Test Customer",
    )


def related_job():
    return SimpleNamespace(
        id=101,
        customer_name="Test Customer",
        service_type="HVAC Repair",
        issue_description="Cooling issue",
        priority="HIGH",
        status="COMPLETED",
        location="Chennai",
        site_address="Chennai",
        preferred_service_date=date(2026, 10, 5),
        contact_number="9876543210",
        assigned_technician_id=55,
        assigned_at=datetime(
            2026,
            10,
            5,
            9,
            tzinfo=timezone.utc,
        ),
        en_route_at=datetime(
            2026,
            10,
            5,
            10,
            tzinfo=timezone.utc,
        ),
        on_site_at=datetime(
            2026,
            10,
            5,
            11,
            tzinfo=timezone.utc,
        ),
        completed_at=datetime(
            2026,
            10,
            5,
            12,
            tzinfo=timezone.utc,
        ),
        created_at=datetime(
            2026,
            10,
            5,
            8,
            tzinfo=timezone.utc,
        ),
        updated_at=datetime(
            2026,
            10,
            5,
            12,
            tzinfo=timezone.utc,
        ),
    )


def technician():
    return SimpleNamespace(
        technician_id=55,
        technician_name="Technician One",
        phone_number="9000000000",
    )


def test_support_update_schema_has_bounded_statuses():
    assert (
        CustomerSupportRequestUpdate(status=" open ").status
        == "OPEN"
    )
    assert (
        CustomerSupportRequestUpdate(status="in_progress").status
        == "IN_PROGRESS"
    )
    assert (
        CustomerSupportRequestUpdate(
            status="RESOLVED",
            resolution_note="Fixed",
        ).status
        == "RESOLVED"
    )

    with pytest.raises(ValueError):
        CustomerSupportRequestUpdate(status="INVALID")


def test_staff_role_guard_allows_super_admin_and_dispatcher():
    assert (
        _require_support_staff(
            user(UserRole.SUPER_ADMIN)
        ).role
        == UserRole.SUPER_ADMIN
    )
    assert (
        _require_support_staff(
            user(UserRole.DISPATCHER)
        ).role
        == UserRole.DISPATCHER
    )

    with pytest.raises(HTTPException) as exc:
        _require_support_staff(user(UserRole.CUSTOMER))

    assert exc.value.status_code == 403


def test_super_admin_list_is_not_tenant_filtered():
    request = support(tenant_id="tenant-any")

    db = FakeDB(
        support_request=request,
        customer=customer(),
        job=related_job(),
        technician=technician(),
    )

    result = asyncio.run(
        list_customer_support_requests_for_staff(
            status_filter=None,
            current_user=user(UserRole.SUPER_ADMIN),
            db=db,
        )
    )

    assert len(result) == 1
    assert isinstance(
        result[0],
        CustomerSupportRequestAdminResponse,
    )

    support_filters = db.support_query.filters
    assert support_filters == []


def test_dispatcher_list_applies_tenant_filter():
    request = support(tenant_id="tenant-1")

    db = FakeDB(
        support_request=request,
        customer=customer(),
        job=related_job(),
        technician=technician(),
    )

    asyncio.run(
        list_customer_support_requests_for_staff(
            status_filter="OPEN",
            current_user=user(
                UserRole.DISPATCHER,
                tenant_id="tenant-1",
            ),
            db=db,
        )
    )

    assert len(db.support_query.filters) >= 2


def test_staff_detail_includes_safe_customer_and_job_context():
    request = support()

    db = FakeDB(
        support_request=request,
        customer=customer(),
        job=related_job(),
        technician=technician(),
    )

    result = asyncio.run(
        get_customer_support_request_for_staff(
            support_request_id=11,
            current_user=user(UserRole.DISPATCHER),
            db=db,
        )
    )

    assert result.customer["name"] == "Test Customer"
    assert result.customer["email"] == "customer@example.com"
    assert result.job["id"] == 101
    assert (
        result.job["assigned_technician_name"]
        == "Technician One"
    )


def test_staff_update_requires_resolution_note_and_notifies_customer(
    monkeypatch,
):
    request = support()

    db = FakeDB(
        support_request=request,
        customer=customer(),
        job=related_job(),
        technician=technician(),
    )

    monkeypatch.setattr(
        "app.routes.admin_customer_support.audit_log",
        lambda *args, **kwargs: None,
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            update_customer_support_request_for_staff(
                support_request_id=11,
                data=CustomerSupportRequestUpdate(
                    status="RESOLVED"
                ),
                current_user=user(UserRole.DISPATCHER),
                db=db,
            )
        )

    assert exc.value.status_code == 400

    result = asyncio.run(
        update_customer_support_request_for_staff(
            support_request_id=11,
            data=CustomerSupportRequestUpdate(
                status="RESOLVED",
                resolution_note="Invoice checked and corrected.",
            ),
            current_user=user(UserRole.DISPATCHER),
            db=db,
        )
    )

    assert result.status == "RESOLVED"
    assert (
        request.resolution_note
        == "Invoice checked and corrected."
    )
    assert request.resolved_by == "staff-1"
    assert request.resolved_at is not None
    assert db.commit_count == 1

    assert any(
        isinstance(item, InAppNotification)
        for item in db.added
    )

    notification = next(
        item
        for item in db.added
        if isinstance(item, InAppNotification)
    )

    assert notification.customer_user_id == "customer-1"
    assert notification.type == "CUSTOMER_SUPPORT_UPDATE"
    assert notification.job_id == "101"


def test_build_admin_response_without_related_job():
    request = support()
    request.related_job_id = None

    db = FakeDB(
        support_request=request,
        customer=customer(),
    )

    result = _build_admin_response(
        db,
        request,
    )

    assert result.job is None
    assert result.related_job_id is None