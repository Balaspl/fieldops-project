import asyncio
import inspect
from decimal import Decimal

import pytest
from fastapi import HTTPException
from fastapi.params import Depends

from app.auth.dependencies import AuthenticatedUser
from app.auth.rbac import Permission, UserRole
from app.models import Job, Technician
from app.routes.technician_portal import submit_job_expense
from app.schemas import JobExpenseCreate
from app.services.job_expense_service import create_job_expense


class FakeQuery:
    def __init__(self, result):
        self.result = result
        self.filters = []

    def filter(self, *expressions):
        self.filters.extend(expressions)
        return self

    def with_for_update(self):
        return self

    def first(self):
        return self.result


class FakeDB:
    def __init__(
        self,
        *,
        job=None,
        technician=None,
        commit_error=None,
    ):
        self.job = job
        self.technician = technician
        self.commit_error = commit_error
        self.added = []
        self.commit_count = 0
        self.refresh_count = 0
        self.rollback_count = 0

    def query(self, model):
        if model is Job:
            return FakeQuery(self.job)

        if model is Technician:
            return FakeQuery(self.technician)

        raise AssertionError(
            f"Unexpected query model: {model!r}"
        )

    def add(self, value):
        self.added.append(value)

    def commit(self):
        self.commit_count += 1

        if self.commit_error:
            raise self.commit_error

    def refresh(self, value):
        self.refresh_count += 1

    def rollback(self):
        self.rollback_count += 1


def make_job(
    *,
    job_id=101,
    tenant_id="tenant-1",
    assigned_technician_id=1001,
):
    return Job(
        id=job_id,
        tenant_id=tenant_id,
        customer_name="Test Customer",
        location="Chennai",
        issue_description="AC issue",
        priority="HIGH",
        service_type="HVAC_REPAIR",
        contact_number="9876543210",
        status="IN_PROGRESS",
        assigned_technician_id=assigned_technician_id,
    )


def make_technician(
    *,
    technician_id=1001,
    tenant_id="tenant-1",
):
    return Technician(
        technician_id=technician_id,
        tech_id="tech-user-1",
        tenant_id=tenant_id,
        technician_name="Test Technician",
        technician_skill="HVAC",
        technician_location="Chennai",
        technician_status="BUSY",
        current_jobs=1,
        max_jobs=5,
    )


def make_user(
    *,
    user_id="tech-user-1",
    tenant_id="tenant-1",
):
    return AuthenticatedUser(
        user_id=user_id,
        tenant_id=tenant_id,
        role=UserRole.TECHNICIAN,
        jti="expense-test-jti",
    )


def test_expense_schema_accepts_fixed_precision_decimal():
    payload = JobExpenseCreate(
        amount=Decimal("125.50"),
        description="Parking fee",
    )

    assert payload.amount == Decimal("125.50")
    assert payload.description == "Parking fee"


@pytest.mark.parametrize(
    "amount",
    [
        Decimal("0"),
        Decimal("-1"),
        Decimal("10.001"),
        Decimal("123456789012.00"),
    ],
)
def test_expense_schema_rejects_invalid_money(amount):
    with pytest.raises(Exception):
        JobExpenseCreate(
            amount=amount,
            description="Expense",
        )


def test_expense_schema_rejects_blank_description():
    with pytest.raises(Exception):
        JobExpenseCreate(
            amount=Decimal("10.00"),
            description="   ",
        )


def test_create_job_expense_is_tenant_and_object_scoped():
    job = make_job()
    technician = make_technician()

    db = FakeDB(
        job=job,
        technician=technician,
    )

    expense = create_job_expense(
        db=db,
        job_id=101,
        expense_data=JobExpenseCreate(
            amount=Decimal("125.50"),
            description=" Parking fee ",
        ),
        technician_id=1001,
        tenant_id="tenant-1",
    )

    assert expense.job_id == 101
    assert expense.technician_id == 1001
    assert expense.tenant_id == "tenant-1"
    assert expense.amount == Decimal("125.50")
    assert expense.description == "Parking fee"

    assert db.added == [expense]
    assert db.commit_count == 1
    assert db.refresh_count == 1
    assert db.rollback_count == 0


def test_create_job_expense_rejects_wrong_technician():
    job = make_job(
        assigned_technician_id=2002,
    )

    technician = make_technician(
        technician_id=1001,
    )

    db = FakeDB(
        job=job,
        technician=technician,
    )

    with pytest.raises(HTTPException) as exc_info:
        create_job_expense(
            db=db,
            job_id=101,
            expense_data=JobExpenseCreate(
                amount=Decimal("25.00"),
                description="Parking",
            ),
            technician_id=1001,
            tenant_id="tenant-1",
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == (
        "Technician is not assigned to this job"
    )

    assert db.added == []
    assert db.commit_count == 0
    assert db.refresh_count == 0


def test_create_job_expense_hides_cross_tenant_job():
    db = FakeDB(
        job=None,
        technician=make_technician(),
    )

    with pytest.raises(HTTPException) as exc_info:
        create_job_expense(
            db=db,
            job_id=101,
            expense_data=JobExpenseCreate(
                amount=Decimal("25.00"),
                description="Parking",
            ),
            technician_id=1001,
            tenant_id="tenant-2",
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Job not found"

    assert db.added == []
    assert db.commit_count == 0


def test_create_job_expense_rejects_unassigned_job():
    job = make_job(
        assigned_technician_id=None,
    )

    technician = make_technician()

    db = FakeDB(
        job=job,
        technician=technician,
    )

    with pytest.raises(HTTPException) as exc_info:
        create_job_expense(
            db=db,
            job_id=101,
            expense_data=JobExpenseCreate(
                amount=Decimal("25.00"),
                description="Parking",
            ),
            technician_id=1001,
            tenant_id="tenant-1",
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == (
        "Job is not assigned to any technician"
    )

    assert db.added == []
    assert db.commit_count == 0


def test_create_job_expense_rejects_missing_technician_record():
    job = make_job()

    db = FakeDB(
        job=job,
        technician=None,
    )

    with pytest.raises(HTTPException) as exc_info:
        create_job_expense(
            db=db,
            job_id=101,
            expense_data=JobExpenseCreate(
                amount=Decimal("25.00"),
                description="Parking",
            ),
            technician_id=1001,
            tenant_id="tenant-1",
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == (
        "Technician record not found"
    )

    assert db.added == []
    assert db.commit_count == 0


def test_create_job_expense_rolls_back_on_persistence_failure():
    job = make_job()
    technician = make_technician()

    db = FakeDB(
        job=job,
        technician=technician,
        commit_error=RuntimeError(
            "database failure",
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        create_job_expense(
            db=db,
            job_id=101,
            expense_data=JobExpenseCreate(
                amount=Decimal("25.00"),
                description="Parking",
            ),
            technician_id=1001,
            tenant_id="tenant-1",
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == (
        "Unable to save job expense"
    )

    assert db.commit_count == 1
    assert db.rollback_count == 1


def test_expense_route_requires_manage_permission():
    parameter = inspect.signature(
        submit_job_expense
    ).parameters["current_user"]

    dependency = parameter.default

    assert isinstance(
        dependency,
        Depends,
    )

    permission_checker = dependency.dependency

    closure_values = [
        cell.cell_contents
        for cell in (
            permission_checker.__closure__ or ()
        )
    ]

    assert any(
        Permission.JOB_EXPENSES_MANAGE
        in (
            value
            if isinstance(value, tuple)
            else (value,)
        )
        for value in closure_values
    )


def test_expense_route_uses_authenticated_identity_and_tenant(
    monkeypatch,
):
    calls = {}

    class Tech:
        technician_id = 1001

    def fake_get_tech(
        db,
        user_id,
        tenant_id,
    ):
        calls["lookup"] = (
            user_id,
            tenant_id,
        )

        return Tech()

    def fake_create_job_expense(
        **kwargs,
    ):
        calls["create"] = kwargs
        return kwargs["expense_data"]

    monkeypatch.setattr(
        "app.routes.technician_portal._get_tech_for_user",
        fake_get_tech,
    )

    monkeypatch.setattr(
        "app.routes.technician_portal.create_job_expense",
        fake_create_job_expense,
    )

    user = make_user(
        user_id="tech-user-42",
        tenant_id="tenant-42",
    )

    payload = JobExpenseCreate(
        amount=Decimal("99.90"),
        description="Fuel",
    )

    response = asyncio.run(
        submit_job_expense(
            job_id=777,
            data=payload,
            current_user=user,
            db=object(),
        )
    )

    assert response is payload

    assert calls["lookup"] == (
        "tech-user-42",
        "tenant-42",
    )

    assert calls["create"]["job_id"] == 777

    assert calls["create"]["technician_id"] == 1001

    assert calls["create"]["tenant_id"] == "tenant-42"

    assert calls["create"]["expense_data"] is payload