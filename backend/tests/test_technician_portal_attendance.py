import asyncio
import inspect

import pytest
from fastapi import HTTPException
from fastapi.params import Depends

from app.auth.dependencies import AuthenticatedUser
from app.auth.rbac import Permission, UserRole
from app.models import Technician, TechnicianProfile
from app.routes.technician_portal import (
    _get_tech_for_user,
    update_my_technician_status,
)
from app.schemas import TechnicianAvailabilityUpdate


# ============================================================
# Lightweight test doubles
# ============================================================

class FakeQuery:
    def __init__(
        self,
        model,
        profile=None,
        technician=None,
    ):
        self.model = model
        self.profile = profile
        self.technician = technician
        self.filters = []

    def filter(self, *expressions):
        self.filters.extend(expressions)
        return self

    def first(self):
        if self.model is TechnicianProfile:
            return self.profile

        if self.model is Technician:
            return self.technician

        return None


class FakeDB:
    def __init__(
        self,
        *,
        profile=None,
        technician=None,
    ):
        self.profile = profile
        self.technician = technician
        self.queries = []
        self.commit_count = 0
        self.refresh_count = 0

    def query(self, model):
        query = FakeQuery(
            model=model,
            profile=self.profile,
            technician=self.technician,
        )
        self.queries.append(query)
        return query

    def commit(self):
        self.commit_count += 1

    def refresh(self, obj):
        self.refresh_count += 1


def make_user(
    *,
    user_id="tech-user-1",
    tenant_id="tenant-1",
):
    return AuthenticatedUser(
        user_id=user_id,
        tenant_id=tenant_id,
        role=UserRole.TECHNICIAN,
        jti="attendance-test-jti",
        session_id="attendance-test-session",
    )


def make_profile(
    *,
    completed=True,
    user_id="tech-user-1",
    tenant_id="tenant-1",
):
    return TechnicianProfile(
        id="profile-1",
        user_id=user_id,
        tenant_id=tenant_id,
        full_name="Test Technician",
        mobile_number="+919999999999",
        profile_completed=completed,
    )


def make_technician(
    *,
    tenant_id="tenant-1",
    status="Available",
):
    return Technician(
        technician_id=1001,
        tech_id="tech-user-1",
        tenant_id=tenant_id,
        technician_name="Test Technician",
        technician_skill="HVAC",
        technician_location="Chennai",
        technician_status=status,
        current_jobs=0,
        max_jobs=5,
    )


# ============================================================
# Contract validation
# ============================================================

def test_attendance_status_schema_accepts_existing_contract_values():
    allowed_statuses = [
        "Available",
        "Busy",
        "Assigned",
        "Offline",
        "En Route",
        "On Site",
        "On Break",
        "Suspended",
        "AVAILABLE",
        "BUSY",
        "ASSIGNED",
        "OFFLINE",
        "EN_ROUTE",
        "ON_SITE",
        "ON_BREAK",
        "SUSPENDED",
    ]

    for status_value in allowed_statuses:
        payload = TechnicianAvailabilityUpdate(
            technician_status=status_value,
        )

        assert (
            payload.technician_status
            == status_value
        )


def test_attendance_status_schema_rejects_invalid_value():
    with pytest.raises(Exception):
        TechnicianAvailabilityUpdate(
            technician_status="NOT_A_VALID_STATUS",
        )


# ============================================================
# Authorization contract
# ============================================================

def test_attendance_update_requires_own_technician_permission():
    parameter = inspect.signature(
        update_my_technician_status,
    ).parameters["current_user"]

    dependency = parameter.default

    assert isinstance(dependency, Depends)

    permission_checker = dependency.dependency

    closure_values = [
        cell.cell_contents
        for cell in (
            permission_checker.__closure__
            or ()
        )
    ]

    assert any(
        Permission.TECHNICIANS_VIEW_OWN
        in (
            value
            if isinstance(value, tuple)
            else (value,)
        )
        for value in closure_values
    )


# ============================================================
# Tenant-scoped technician lookup
# ============================================================

def test_technician_lookup_is_scoped_to_current_tenant():
    technician = make_technician(
        tenant_id="tenant-1",
    )

    db = FakeDB(
        technician=technician,
    )

    result = _get_tech_for_user(
        db=db,
        user_id="tech-user-1",
        tenant_id="tenant-1",
    )

    assert result is technician

    technician_queries = [
        query
        for query in db.queries
        if query.model is Technician
    ]

    assert technician_queries

    first_filter_text = str(
        technician_queries[0].filters[0]
    )

    assert "technicians.tenant_id" in (
        first_filter_text
    )

    assert ":tenant_id" in first_filter_text


# ============================================================
# Successful backend-authoritative update
# ============================================================

def test_attendance_update_changes_backend_technician_status():
    profile = make_profile(
        completed=True,
    )

    technician = make_technician(
        status="Available",
    )

    db = FakeDB(
        profile=profile,
        technician=technician,
    )

    user = make_user()

    response = asyncio.run(
        update_my_technician_status(
            data=TechnicianAvailabilityUpdate(
                technician_status="Busy",
            ),
            current_user=user,
            db=db,
        )
    )

    assert response == {
        "technician_id": 1001,
        "technician_status": "Busy",
    }

    assert technician.technician_status == "Busy"
    assert db.commit_count == 1
    assert db.refresh_count == 1


# ============================================================
# Profile guard
# ============================================================

def test_attendance_update_requires_completed_profile():
    profile = make_profile(
        completed=False,
    )

    technician = make_technician(
        status="Available",
    )

    db = FakeDB(
        profile=profile,
        technician=technician,
    )

    user = make_user()

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            update_my_technician_status(
                data=TechnicianAvailabilityUpdate(
                    technician_status="Busy",
                ),
                current_user=user,
                db=db,
            )
        )

    assert exc_info.value.status_code == 403

    assert (
        exc_info.value.detail
        == "Please complete your profile to change technician status."
    )

    assert technician.technician_status == "Available"
    assert db.commit_count == 0


# ============================================================
# Missing technician record
# ============================================================

def test_attendance_update_returns_not_found_when_technician_is_missing():
    profile = make_profile(
        completed=True,
    )

    db = FakeDB(
        profile=profile,
        technician=None,
    )

    user = make_user()

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            update_my_technician_status(
                data=TechnicianAvailabilityUpdate(
                    technician_status="Offline",
                ),
                current_user=user,
                db=db,
            )
        )

    assert exc_info.value.status_code == 404
    assert (
        exc_info.value.detail
        == "Technician record not found"
    )

    assert db.commit_count == 0
# ============================================================
# Full app.routes.technician_portal statement coverage
# ============================================================

from datetime import date, datetime, timezone
from types import SimpleNamespace
import sys
import types

from fastapi import Request

import app.routes.technician_portal as tp
from app.portal_schemas import (
    ChangePasswordRequest,
    TechnicianJobCompleteRequest,
    TechnicianJobRejectRequest,
    TechnicianProfileCreate,
    TechnicianProfileUpdate,
)


class Q:
    def __init__(self, first=None, all_=None, counts=None, update=0, first_values=None):
        self._first = first
        self._first_values = list(first_values or [])
        self._all = list(all_ or [])
        self._counts = list(counts or [])
        self._update = update
        self.ops = []

    def filter(self, *args):
        self.ops.append(("filter", args))
        return self

    def order_by(self, *args):
        self.ops.append(("order_by", args))
        return self

    def limit(self, value):
        self.ops.append(("limit", value))
        return self

    def join(self, *args):
        self.ops.append(("join", args))
        return self

    def first(self):
        if self._first_values:
            return self._first_values.pop(0)
        return self._first

    def all(self):
        return list(self._all)

    def count(self):
        return self._counts.pop(0) if self._counts else 0

    def update(self, *args, **kwargs):
        self.ops.append(("update", args, kwargs))
        return self._update


class DB:
    def __init__(self, *queries, commit_error=False):
        self._queries = list(queries)
        self.commit_error = commit_error
        self.added = []
        self.commit_count = 0
        self.rollback_count = 0
        self.refresh_count = 0

    def query(self, *args):
        return self._queries.pop(0) if self._queries else Q()

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commit_count += 1
        if self.commit_error:
            raise RuntimeError("forced commit failure")

    def rollback(self):
        self.rollback_count += 1

    def refresh(self, obj):
        self.refresh_count += 1


class Capture(dict):
    def __init__(self, **kwargs):
        super().__init__(kwargs)


def req(method="GET", path="/api/technician"):
    return Request(
        scope={
            "type": "http",
            "method": method,
            "path": path,
            "headers": [],
        }
    )


def u():
    return AuthenticatedUser(
        user_id="tech-user-1",
        tenant_id="tenant-1",
        role=UserRole.TECHNICIAN,
        jti="jti",
        session_id="session",
    )


def profile(*, completed=True, dob=None, full_name="Test Technician", mobile="+919999999999"):
    return SimpleNamespace(
        id="profile-1",
        user_id="tech-user-1",
        tenant_id="tenant-1",
        full_name=full_name,
        profile_photo="photo",
        mobile_number=mobile,
        date_of_birth=dob,
        gender="Male",
        address="Address",
        city="Chennai",
        state="Tamil Nadu",
        pincode="600001",
        emergency_contact="+919888888888",
        skills=["HVAC"],
        experience="5 years",
        certifications=["EPA"],
        profile_completed=completed,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def tech(*, current_jobs=1, tech_id="tech-user-1", status="AVAILABLE"):
    return SimpleNamespace(
        technician_id=1001,
        tech_id=tech_id,
        tenant_id="tenant-1",
        technician_name="Test Technician",
        technician_skill="HVAC",
        technician_location="Chennai",
        technician_status=status,
        current_jobs=current_jobs,
        max_jobs=5,
        phone_number="+919999999999",
    )


def job(*, status="ASSIGNED", job_id=1):
    return SimpleNamespace(
        id=job_id,
        tenant_id="tenant-1",
        assigned_technician_id=1001,
        status=status,
        rejection_reason=None,
        rejected_at=None,
        rejected_by_tech_id=None,
        on_site_at=None,
        on_site_by=None,
        completed_at=None,
        completed_by=None,
        work_report=None,
        priority="HIGH",
        customer_name="Customer",
        service_type="HVAC",
        location="Chennai",
        site_address="Chennai",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def usr():
    return SimpleNamespace(
        id="tech-user-1",
        tenant_id="tenant-1",
        full_name="Test Technician",
        phone_number="+919999999999",
        email="tech@example.com",
        password_hash="old-hash",
    )


def nfy(*, job_id="1", status="UNREAD", nid="n1", created=True):
    return SimpleNamespace(
        id=nid,
        tenant_id="tenant-1",
        tech_id="tech-user-1",
        job_id=job_id,
        type="JOB_ASSIGNED",
        title="Job Assigned",
        body="Assigned",
        status=status,
        created_at=datetime.now(timezone.utc) if created else None,
        read_at=None,
    )


@pytest.fixture
def patch_tp(monkeypatch):
    monkeypatch.setattr(tp, "audit_log", lambda *a, **k: None)
    monkeypatch.setattr(
        tp,
        "create_customer_job_status_notification",
        lambda *a, **k: None,
    )


def test_json_safe_all_types():
    value_dt = datetime.now(timezone.utc)
    value_date = date.today()
    assert tp._json_safe(value_dt) == value_dt.isoformat()
    assert tp._json_safe(value_date) == value_date.isoformat()
    assert tp._json_safe(None) is None


def test_get_tech_name_fallback():
    matched = tech(tech_id=None)
    tech_query = Q(first_values=[None, matched])
    db = DB(tech_query, Q(first=profile()), Q(first=usr()))
    assert tp._get_tech_for_user(db, "tech-user-1", "tenant-1") is matched
    assert matched.tech_id == "tech-user-1"
    assert db.commit_count == 1


def test_get_tech_name_fallback_commit_failure():
    matched = tech(tech_id=None)
    tech_query = Q(first_values=[None, matched])
    db = DB(tech_query, Q(first=profile()), Q(first=usr()), commit_error=True)
    with pytest.raises(RuntimeError):
        tp._get_tech_for_user(db, "tech-user-1", "tenant-1")
    assert db.rollback_count == 1


def test_get_tech_phone_fallback():
    matched = tech(tech_id=None)
    tech_query = Q(first_values=[None, matched])
    db = DB(tech_query, Q(first=profile(full_name=None)), Q(first=None))
    assert tp._get_tech_for_user(db, "tech-user-1", "tenant-1") is matched
    assert matched.tech_id == "tech-user-1"
    assert db.commit_count == 1


def test_get_tech_phone_fallback_commit_failure():
    matched = tech(tech_id=None)
    tech_query = Q(first_values=[None, matched])
    db = DB(tech_query, Q(first=profile(full_name=None)), Q(first=None), commit_error=True)
    with pytest.raises(RuntimeError):
        tp._get_tech_for_user(db, "tech-user-1", "tenant-1")
    assert db.rollback_count == 1


def test_get_tech_no_fallback():
    db = DB(Q(first=None), Q(first=None), Q(first=None))
    assert tp._get_tech_for_user(db, "tech-user-1", "tenant-1") is None


def test_recipient_ids_with_tech():
    assert set(tp._get_notification_recipient_ids("tech-user-1", tech())) == {"tech-user-1", "1001"}


def test_get_profile_missing_user(monkeypatch):
    monkeypatch.setattr(tp, "TechnicianProfileResponse", Capture)
    result = asyncio.run(tp.get_technician_profile(current_user=u(), db=DB(Q(first=None), Q(first=usr()))))
    assert result["profile_completed"] is False


def test_get_profile_full(monkeypatch):
    monkeypatch.setattr(tp, "TechnicianProfileResponse", Capture)
    dob = date(date.today().year - 30, date.today().month, date.today().day)
    result = asyncio.run(tp.get_technician_profile(current_user=u(), db=DB(Q(first=profile(dob=dob)), Q(first=usr()))))
    assert result["age"] == 30


def create_payload():
    return TechnicianProfileCreate(
        full_name="New Technician",
        mobile_number="+919111111111",
        date_of_birth=date(1990, 1, 1),
        gender="Male",
        address="10 Main Road",
        city="Chennai",
        state="Tamil Nadu",
        pincode="600002",
        emergency_contact="+919222222222",
        skills=["HVAC", "Electrical"],
        experience="7 years",
        certifications=["EPA"],
        profile_photo="photo",
    )


def test_create_profile_existing():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(tp.create_technician_profile(data=create_payload(), request=req("POST", "/profile"), current_user=u(), db=DB(Q(first=profile()))))
    assert exc.value.status_code == 409


def test_create_profile_new_tech(monkeypatch, patch_tp):
    monkeypatch.setattr(tp, "TechnicianProfileResponse", Capture)
    db = DB(Q(first=None), Q(first=None), Q(first=usr()))
    result = asyncio.run(tp.create_technician_profile(data=create_payload(), request=req("POST", "/profile"), current_user=u(), db=db))
    assert result["profile_completed"] is True
    assert any(isinstance(x, Technician) for x in db.added)


def test_create_profile_existing_tech(monkeypatch, patch_tp):
    monkeypatch.setattr(tp, "TechnicianProfileResponse", Capture)
    result = asyncio.run(tp.create_technician_profile(data=create_payload(), request=req("POST", "/profile"), current_user=u(), db=DB(Q(first=None), Q(first=tech()), Q(first=usr()))))
    assert result["full_name"] == "New Technician"


def test_create_profile_sync_failure(monkeypatch, patch_tp):
    monkeypatch.setattr(tp, "TechnicianProfileResponse", Capture)
    class BrokenDB(DB):
        def query(self, *args):
            if args and args[0] is Technician:
                raise RuntimeError("sync failed")
            return super().query(*args)
    result = asyncio.run(tp.create_technician_profile(data=create_payload(), request=req("POST", "/profile"), current_user=u(), db=BrokenDB(Q(first=None), Q(first=usr()))))
    assert result["profile_completed"] is True


def update_payload():
    return TechnicianProfileUpdate(full_name="Updated Technician", mobile_number="+919444444444", skills=["HVAC"], city="Bengaluru")


def test_update_profile_missing():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(tp.update_technician_profile(data=update_payload(), request=req("PUT", "/profile"), current_user=u(), db=DB(Q(first=None))))
    assert exc.value.status_code == 404


def test_update_profile_existing_tech(monkeypatch, patch_tp):
    monkeypatch.setattr(tp, "TechnicianProfileResponse", Capture)
    dob = date(date.today().year - 30, date.today().month, date.today().day)
    result = asyncio.run(
        tp.update_technician_profile(
            data=update_payload(),
            request=req("PUT", "/profile"),
            current_user=u(),
            db=DB(Q(first=profile(dob=dob)), Q(first=tech()), Q(first=usr())),
        )
    )
    assert result["profile_completed"] is True
    assert result["age"] == 30


def test_update_profile_missing_tech(monkeypatch, patch_tp):
    monkeypatch.setattr(tp, "TechnicianProfileResponse", Capture)
    db = DB(Q(first=profile()), Q(first=None), Q(first=usr()))
    result = asyncio.run(tp.update_technician_profile(data=TechnicianProfileUpdate(city="Chennai"), request=req("PUT", "/profile"), current_user=u(), db=db))
    assert result["profile_completed"] is True
    assert any(isinstance(x, Technician) for x in db.added)


def test_update_profile_sync_failure(monkeypatch, patch_tp):
    monkeypatch.setattr(tp, "TechnicianProfileResponse", Capture)
    class BrokenDB(DB):
        def query(self, *args):
            if args and args[0] is Technician:
                raise RuntimeError("sync failed")
            return super().query(*args)
    result = asyncio.run(tp.update_technician_profile(data=TechnicianProfileUpdate(city="Chennai"), request=req("PUT", "/profile"), current_user=u(), db=BrokenDB(Q(first=profile()), Q(first=usr()))))
    assert result["profile_completed"] is True


def test_change_password_paths(monkeypatch, patch_tp):
    with pytest.raises(HTTPException):
        asyncio.run(tp.change_password(data=ChangePasswordRequest(current_password="old", new_password="new-password", confirm_password="new-password"), request=req("POST", "/change-password"), current_user=u(), db=DB(Q(first=None))))

    monkeypatch.setattr(tp, "verify_password", lambda *a: False)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(tp.change_password(data=ChangePasswordRequest(current_password="old", new_password="new-password", confirm_password="new-password"), request=req("POST", "/change-password"), current_user=u(), db=DB(Q(first=usr()))))
    assert exc.value.status_code == 400

    user = usr()
    monkeypatch.setattr(tp, "verify_password", lambda *a: True)
    monkeypatch.setattr(tp, "hash_password", lambda value: "new-hash")
    result = asyncio.run(tp.change_password(data=ChangePasswordRequest(current_password="old", new_password="new-password", confirm_password="new-password"), request=req("POST", "/change-password"), current_user=u(), db=DB(Q(first=user))))
    assert result["message"] == "Password changed successfully"
    assert user.password_hash == "new-hash"


def test_assigned_jobs_query_present_and_missing():
    empty_query = Q()
    missing_db = DB(Q(first=None), Q(first=None), Q(first=None), empty_query)
    assert tp._get_assigned_jobs_query(missing_db, "tech-user-1", "tenant-1") is empty_query

    jobs_query = Q()
    assert tp._get_assigned_jobs_query(DB(Q(first=tech()), jobs_query), "tech-user-1", "tenant-1") is jobs_query


def test_get_assigned_jobs_both_paths(monkeypatch):
    q = Q(all_=[job()])
    monkeypatch.setattr(tp, "_get_assigned_jobs_query", lambda *a: q)
    assert asyncio.run(tp.get_assigned_jobs(status_filter="ACCEPTED", current_user=u(), db=DB()))
    q2 = Q(all_=[job()])
    monkeypatch.setattr(tp, "_get_assigned_jobs_query", lambda *a: q2)
    assert asyncio.run(tp.get_assigned_jobs(status_filter=None, current_user=u(), db=DB()))


def test_get_job_history(monkeypatch):
    q = Q(all_=[job(status="COMPLETED")])
    monkeypatch.setattr(tp, "_get_assigned_jobs_query", lambda *a: q)
    assert asyncio.run(tp.get_job_history(current_user=u(), db=DB()))


def test_get_job_detail_paths():
    with pytest.raises(HTTPException):
        asyncio.run(tp.get_job_detail(job_id=1, current_user=u(), db=DB(Q(first=None))))
    with pytest.raises(HTTPException):
        asyncio.run(tp.get_job_detail(job_id=1, current_user=u(), db=DB(Q(first=tech()), Q(first=None))))
    found = job()
    assert asyncio.run(tp.get_job_detail(job_id=1, current_user=u(), db=DB(Q(first=tech()), Q(first=found)))) is found


def test_accept_job_paths(patch_tp):
    with pytest.raises(HTTPException):
        asyncio.run(tp.accept_job(job_id=1, request=req("POST", "/accept"), current_user=u(), db=DB(Q(first=None))))
    with pytest.raises(HTTPException):
        asyncio.run(tp.accept_job(job_id=1, request=req("POST", "/accept"), current_user=u(), db=DB(Q(first=tech()), Q(first=None))))
    j = job()
    sr = SimpleNamespace(linked_job_id=1, status="ASSIGNED")
    result = asyncio.run(tp.accept_job(job_id=1, request=req("POST", "/accept"), current_user=u(), db=DB(Q(first=tech()), Q(first=j), Q(first=sr), Q(update=1))))
    assert result["status"] == "ACCEPTED"
    assert sr.status == "ACCEPTED"


def test_reject_job_paths(patch_tp):
    data = TechnicianJobRejectRequest(reason="Technician unavailable today")
    with pytest.raises(HTTPException):
        asyncio.run(tp.reject_job(job_id=1, data=data, request=req("POST", "/reject"), current_user=u(), db=DB(Q(first=None))))
    with pytest.raises(HTTPException):
        asyncio.run(tp.reject_job(job_id=1, data=data, request=req("POST", "/reject"), current_user=u(), db=DB(Q(first=tech()), Q(first=None))))
    t = tech(current_jobs=2, tech_id=None)
    j = job()
    result = asyncio.run(tp.reject_job(job_id=1, data=data, request=req("POST", "/reject"), current_user=u(), db=DB(Q(first=t), Q(first=j), Q())))
    assert result["status"] == "REJECTED_BY_TECHNICIAN"
    assert t.current_jobs == 1
    assert j.assigned_technician_id is None


def test_start_job_paths(patch_tp):
    with pytest.raises(HTTPException):
        asyncio.run(tp.start_job(job_id=1, request=req("POST", "/start"), current_user=u(), db=DB(Q(first=None))))
    with pytest.raises(HTTPException):
        asyncio.run(tp.start_job(job_id=1, request=req("POST", "/start"), current_user=u(), db=DB(Q(first=tech()), Q(first=None))))
    j = job(status="ACCEPTED")
    sr = SimpleNamespace(linked_job_id=1, tenant_id="tenant-1", status="ACCEPTED")
    result = asyncio.run(tp.start_job(job_id=1, request=req("POST", "/start"), current_user=u(), db=DB(Q(first=tech()), Q(first=j), Q(first=sr))))
    assert result["status"] == "EN_ROUTE"
    assert sr.status == "EN_ROUTE"


def test_on_site_job_paths(patch_tp):
    with pytest.raises(HTTPException):
        asyncio.run(tp.on_site_job(job_id=1, request=req("POST", "/on-site"), current_user=u(), db=DB(Q(first=None))))
    with pytest.raises(HTTPException):
        asyncio.run(tp.on_site_job(job_id=1, request=req("POST", "/on-site"), current_user=u(), db=DB(Q(first=tech()), Q(first=None))))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(tp.on_site_job(job_id=1, request=req("POST", "/on-site"), current_user=u(), db=DB(Q(first=tech()), Q(first=job(status="ACCEPTED")))))
    assert exc.value.status_code == 400
    j = job(status="EN_ROUTE")
    sr = SimpleNamespace(linked_job_id=1, status="EN_ROUTE")
    result = asyncio.run(tp.on_site_job(job_id=1, request=req("POST", "/on-site"), current_user=u(), db=DB(Q(first=tech()), Q(first=j), Q(first=sr))))
    assert result["status"] == "IN_PROGRESS"
    assert sr.status == "IN_PROGRESS"
    assert j.on_site_by == "tech-user-1"


def test_pause_job_paths(patch_tp):
    result = asyncio.run(tp.pause_job(job_id=1, request=req("POST", "/pause"), current_user=u(), db=DB(Q(first=tech()), Q(first=job(status="IN_PROGRESS")))))
    assert result["status"] == "PAUSED"
    with pytest.raises(HTTPException):
        asyncio.run(tp.pause_job(job_id=1, request=req("POST", "/pause"), current_user=u(), db=DB(Q(first=None))))
    with pytest.raises(HTTPException):
        asyncio.run(tp.pause_job(job_id=1, request=req("POST", "/pause"), current_user=u(), db=DB(Q(first=tech()), Q(first=None))))


def test_resume_job_paths(patch_tp):
    result = asyncio.run(tp.resume_job(job_id=1, request=req("POST", "/resume"), current_user=u(), db=DB(Q(first=tech()), Q(first=job(status="PAUSED")))))
    assert result["status"] == "IN_PROGRESS"
    with pytest.raises(HTTPException):
        asyncio.run(tp.resume_job(job_id=1, request=req("POST", "/resume"), current_user=u(), db=DB(Q(first=None))) )
    with pytest.raises(HTTPException):
        asyncio.run(tp.resume_job(job_id=1, request=req("POST", "/resume"), current_user=u(), db=DB(Q(first=tech()), Q(first=None))))


def test_complete_job_paths(patch_tp):
    t = tech(current_jobs=2)
    j = job(status="IN_PROGRESS")
    sr = SimpleNamespace(linked_job_id=1, tenant_id="tenant-1", status="IN_PROGRESS")
    result = asyncio.run(tp.complete_job(job_id=1, data=TechnicianJobCompleteRequest(completion_notes="Completed repair", photos=["after.jpg"], signature="signature"), request=req("POST", "/complete"), current_user=u(), db=DB(Q(first=t), Q(first=j), Q(first=sr))))
    assert result["status"] == "COMPLETED"
    assert j.work_report == "Completed repair"
    assert sr.status == "COMPLETED"
    assert t.current_jobs == 1
    with pytest.raises(HTTPException):
        asyncio.run(tp.complete_job(job_id=1, data=TechnicianJobCompleteRequest(), request=req("POST", "/complete"), current_user=u(), db=DB(Q(first=None))))
    with pytest.raises(HTTPException):
        asyncio.run(tp.complete_job(job_id=1, data=TechnicianJobCompleteRequest(), request=req("POST", "/complete"), current_user=u(), db=DB(Q(first=tech()), Q(first=None))))


def test_get_notifications_success_and_failure(patch_tp):
    initial = [
        nfy(job_id="1", status="UNREAD"),
        nfy(job_id="bad", status="READ", nid="n2", created=False),
    ]
    pending = SimpleNamespace(
        id=2,
        tenant_id="tenant-1",
        assigned_technician_id=1001,
        service_type="HVAC",
        location="Chennai",
        priority="HIGH",
        created_at=datetime.now(timezone.utc),
    )
    existing_row = SimpleNamespace(job_id="1")
    status_row = SimpleNamespace(id=1, status="ACCEPTED")

    success_db = DB(
        Q(first=tech()),
        Q(all_=initial),
        Q(all_=[pending]),
        Q(all_=[existing_row]),
        Q(all_=initial),
        Q(all_=[status_row]),
    )
    result = asyncio.run(tp.get_notifications(current_user=u(), db=success_db))
    assert result["unread_count"] == 1
    assert result["notifications"][0]["jobStatus"] == "ACCEPTED"
    assert success_db.commit_count == 1

    failure_db = DB(
        Q(first=tech()),
        Q(all_=[]),
        Q(all_=[pending]),
        Q(all_=[]),
        commit_error=True,
    )
    with pytest.raises(HTTPException) as exc:
        asyncio.run(tp.get_notifications(current_user=u(), db=failure_db))
    assert exc.value.status_code == 500
    assert failure_db.rollback_count == 1


def test_mark_notification_read_paths():
    with pytest.raises(HTTPException):
        asyncio.run(tp.mark_notification_read(notification_id="missing", current_user=u(), db=DB(Q(first=tech()), Q(first=None))))
    unread = nfy(status="UNREAD")
    result = asyncio.run(tp.mark_notification_read(notification_id="n1", current_user=u(), db=DB(Q(first=tech()), Q(first=unread))))
    assert result["status"] == "READ"
    already = nfy(status="READ")
    result = asyncio.run(tp.mark_notification_read(notification_id="n1", current_user=u(), db=DB(Q(first=tech()), Q(first=already))))
    assert result["status"] == "READ"


def test_mark_all_notifications_read():
    result = asyncio.run(tp.mark_all_notifications_read(current_user=u(), db=DB(Q(first=tech()), Q(update=3))))
    assert result["updated"] == 3


def test_billing_reports_paths():
    c = SimpleNamespace(id=10, subtotal=1000, labour_cost=600, material_cost=400, work_summary="Completed", completed_at=datetime.now(timezone.utc), created_at=datetime.now(timezone.utc))
    j = SimpleNamespace(id=10, customer_name=None, service_type=None, location=None, site_address="Fallback")
    with pytest.raises(HTTPException):
        asyncio.run(tp.get_billing_reports(current_user=u(), db=DB(Q(first=None))))
    result = asyncio.run(tp.get_billing_reports(current_user=u(), db=DB(Q(first=tech()), Q(all_=[(c, j)]))))
    assert result["count"] == 1
    assert result["reports"][0]["total_amount"] == 1050.0


def test_download_billing_report_pdf_paths(monkeypatch):
    with pytest.raises(HTTPException):
        asyncio.run(tp.download_billing_report_pdf(closure_id=10, current_user=u(), db=DB(Q(first=None))))
    with pytest.raises(HTTPException):
        asyncio.run(tp.download_billing_report_pdf(closure_id=10, current_user=u(), db=DB(Q(first=tech()), Q(first=None))))

    class FakeCanvas:
        def __init__(self, *a, **k): pass
        def setTitle(self, *a, **k): pass
        def setFont(self, *a, **k): pass
        def drawString(self, *a, **k): pass
        def drawRightString(self, *a, **k): pass
        def save(self): pass

    reportlab = types.ModuleType("reportlab")
    lib = types.ModuleType("reportlab.lib")
    pagesizes = types.ModuleType("reportlab.lib.pagesizes")
    pdfgen = types.ModuleType("reportlab.pdfgen")
    canvas_mod = types.ModuleType("reportlab.pdfgen.canvas")
    pagesizes.A4 = (595, 842)
    canvas_mod.Canvas = FakeCanvas
    reportlab.lib = lib
    reportlab.pdfgen = pdfgen
    lib.pagesizes = pagesizes
    pdfgen.canvas = canvas_mod
    monkeypatch.setitem(sys.modules, "reportlab", reportlab)
    monkeypatch.setitem(sys.modules, "reportlab.lib", lib)
    monkeypatch.setitem(sys.modules, "reportlab.lib.pagesizes", pagesizes)
    monkeypatch.setitem(sys.modules, "reportlab.pdfgen", pdfgen)
    monkeypatch.setitem(sys.modules, "reportlab.pdfgen.canvas", canvas_mod)

    long_summary = " ".join(["Detailed"] * 40)
    c = SimpleNamespace(id=10, subtotal=1234, labour_cost=700, material_cost=534, work_summary=long_summary, completed_at=None, created_at=datetime.now(timezone.utc))
    j = SimpleNamespace(id=55, customer_name="Customer", service_type="HVAC", location="Chennai", site_address="Chennai")
    result = asyncio.run(tp.download_billing_report_pdf(closure_id=10, current_user=u(), db=DB(Q(first=tech()), Q(first=(c, j)))))
    assert result.media_type == "application/pdf"


def test_dashboard_paths(monkeypatch):
    monkeypatch.setattr(tp, "TechnicianDashboardResponse", Capture)
    result = asyncio.run(tp.get_technician_dashboard(current_user=u(), db=DB(Q(first=None), Q(first=profile(completed=False)))))
    assert result["profile_completed"] is False
    result = asyncio.run(tp.get_technician_dashboard(current_user=u(), db=DB(Q(first=tech(status="BUSY")), Q(first=profile()), Q(counts=[7, 4, 2, 1, 6]), Q(counts=[3]))))
    assert result["total_assigned"] == 7
    assert result["active_jobs"] == 4
    assert result["completed_today"] == 2
    assert result["pending_acceptance"] == 1
    assert result["total_completed"] == 6
    assert result["rejected_jobs"] == 3
