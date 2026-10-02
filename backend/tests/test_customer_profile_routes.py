"""
Comprehensive customer_portal.py route coverage.

This file covers the complete customer portal route module, including:

- Location helpers
- Haversine distance
- Ola Maps / Photon geocoding
- Customer profile
- Password change
- Service requests
- Service request editing
- Service request cancellation
- Customer job tracking
- Job detail
- Completion reports
- Service history
- Notifications
- Notification read operations
- Dashboard statistics
"""

import asyncio
from datetime import date, datetime, timezone
from io import BytesIO
from types import SimpleNamespace

import pytest
import requests

from fastapi import HTTPException
from sqlalchemy import inspect

from app.auth.dependencies import AuthenticatedUser
from app.auth.rbac import UserRole
from app.models import (
    InAppNotification,
    Job,
    JobClosure,
    Organization,
    ServiceRequest,
    Technician,
)
from app.models.customer_profile import CustomerProfileModel
from app.models.technician_profile import TechnicianProfile
from app.models.user import User
from app.portal_schemas import (
    CustomerProfileCreate,
    CustomerProfileUpdate,
    ServiceRequestCreate,
    ServiceRequestUpdate,
)
from app.routes import customer_portal


# ============================================================
# CONSTANTS
# ============================================================

NOW = datetime.now(timezone.utc)


# ============================================================
# AUTHENTICATED USER HELPERS
# ============================================================


def customer(
    user_id="customer-1",
    tenant_id="tenant-1",
):
    return AuthenticatedUser(
        user_id=user_id,
        tenant_id=tenant_id,
        role=UserRole.CUSTOMER,
        jti="customer-test-jti",
        session_id="customer-test-session",
    )


# ============================================================
# GENERIC QUERY DOUBLE
# ============================================================


class FakeQuery:
    def __init__(
        self,
        *,
        first_result=None,
        all_result=None,
        count_results=None,
        update_result=0,
    ):
        self.first_result = first_result
        self.all_result = (
            [] if all_result is None else all_result
        )
        self.count_results = list(
            count_results or []
        )
        self.update_result = update_result
        self.filters = []
        self.update_values = None

    def filter(self, *conditions):
        self.filters.extend(conditions)
        return self

    def outerjoin(self, *args, **kwargs):
        return self

    def join(self, *args, **kwargs):
        return self

    def with_for_update(self):
        return self

    def distinct(self):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def first(self):
        return self.first_result

    def all(self):
        return self.all_result

    def count(self):
        if self.count_results:
            return self.count_results.pop(0)

        return len(self.all_result)

    def update(self, values):
        self.update_values = values
        return self.update_result


# ============================================================
# GENERIC DB DOUBLE
# ============================================================


class FakeDB:
    def __init__(
        self,
        query_map=None,
        *,
        flush_error=None,
        commit_error=None,
    ):
        self.query_map = {}

        for key, value in (query_map or {}).items():
            if isinstance(value, list):
                self.query_map[key] = list(value)
            else:
                self.query_map[key] = [value]

        self.added = []
        self.commit_count = 0
        self.rollback_count = 0
        self.refresh_count = 0
        self.flush_count = 0
        self.flush_error = flush_error
        self.commit_error = commit_error

    def query(self, *models):
        key = models[0]

        if hasattr(key, "class_"):
            key = key.class_

        queued = self.query_map.get(key)

        if queued:
            return queued.pop(0)

        return FakeQuery()

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        self.flush_count += 1

        if self.flush_error:
            raise self.flush_error

        # Assign IDs/timestamps to fake objects created by
        # create_service_request().
        for obj in self.added:
            if isinstance(obj, FakeJob):
                if getattr(obj, "id", None) is None:
                    obj.id = 700

            if isinstance(obj, FakeServiceRequest):
                if getattr(obj, "id", None) is None:
                    obj.id = 800

                if getattr(obj, "created_at", None) is None:
                    obj.created_at = NOW

                if getattr(obj, "updated_at", None) is None:
                    obj.updated_at = NOW

    def commit(self):
        self.commit_count += 1

        if self.commit_error:
            raise self.commit_error

    def rollback(self):
        self.rollback_count += 1

    def refresh(self, obj):
        self.refresh_count += 1

        if getattr(obj, "created_at", None) is None:
            obj.created_at = NOW

        if getattr(obj, "updated_at", None) is None:
            obj.updated_at = NOW


# ============================================================
# SIMPLE OBJECT BUILDERS
# ============================================================


def make_user(
    *,
    user_id="customer-1",
    tenant_id="tenant-1",
    email="customer@gmail.com",
    first_name="Test",
    last_name="Customer",
    full_name="Test Customer",
    phone_number="9876543210",
    password_hash="old-hash",
):
    return SimpleNamespace(
        id=user_id,
        tenant_id=tenant_id,
        email=email,
        first_name=first_name,
        last_name=last_name,
        full_name=full_name,
        phone_number=phone_number,
        password_hash=password_hash,
    )


def make_profile(
    *,
    profile_id="profile-1",
    user_id="customer-1",
    tenant_id="tenant-1",
    full_name="Existing Customer",
    mobile_number="9876543210",
    address="10 Test Street",
    city="Chennai",
    state="Tamil Nadu",
    pincode="600001",
    company_name="Test Company",
    profile_completed=True,
):
    return SimpleNamespace(
        id=profile_id,
        user_id=user_id,
        tenant_id=tenant_id,
        full_name=full_name,
        mobile_number=mobile_number,
        address=address,
        city=city,
        state=state,
        pincode=pincode,
        company_name=company_name,
        profile_completed=profile_completed,
        created_at=NOW,
        updated_at=NOW,
    )


def make_service_request(
    *,
    sr_id=1,
    user_id="customer-1",
    tenant_id="tenant-1",
    title="Repair the damaged equipment",
    description=(
        "Please repair the damaged equipment at the customer location."
    ),
    service_type="HVAC_REPAIR",
    priority="HIGH",
    preferred_visit_date=date.today(),
    images=None,
    location="Chennai",
    contact_number="9876543210",
    status="UNASSIGNED",
    linked_job_id=101,
):
    return SimpleNamespace(
        id=sr_id,
        request_number=f"SR-{sr_id}",
        customer_user_id=user_id,
        tenant_id=tenant_id,
        title=title,
        description=description,
        service_type=service_type,
        priority=priority,
        preferred_visit_date=preferred_visit_date,
        images=images if images is not None else [],
        location=location,
        contact_number=contact_number,
        status=status,
        linked_job_id=linked_job_id,
        cancellation_reason=None,
        cancelled_at=None,
        created_at=NOW,
        updated_at=NOW,
    )


def make_job(
    *,
    job_id=101,
    customer_name="Test Customer",
    status="CREATED",
    priority="HIGH",
    service_type="HVAC_REPAIR",
    location="Chennai",
    site_address="Chennai",
    site_latitude=13.0827,
    site_longitude=80.2707,
    assigned_technician_id=None,
    tenant_id="provider-tenant",
    customer_id="customer-1",
    created_at=NOW,
    completed_at=None,
):
    return SimpleNamespace(
        id=job_id,
        customer_name=customer_name,
        status=status,
        priority=priority,
        service_type=service_type,
        location=location,
        site_address=site_address,
        site_latitude=site_latitude,
        site_longitude=site_longitude,
        assigned_technician_id=assigned_technician_id,
        tenant_id=tenant_id,
        customer_id=customer_id,
        customer_tenant_id="tenant-1",
        created_at=created_at,
        completed_at=completed_at,
    )


def make_technician(
    *,
    technician_id=10,
    tenant_id="provider-tenant",
    tech_id="tech-user-1",
    name="Technician One",
    phone="9000000001",
):
    return SimpleNamespace(
        technician_id=technician_id,
        tenant_id=tenant_id,
        tech_id=tech_id,
        technician_name=name,
        phone_number=phone,
    )


def make_technician_profile(
    *,
    user_id="tech-user-1",
    tenant_id="provider-tenant",
    photo="/photos/tech.jpg",
):
    return SimpleNamespace(
        user_id=user_id,
        tenant_id=tenant_id,
        profile_photo=photo,
    )


def make_ping(
    *,
    latitude=13.0500,
    longitude=80.2500,
    accuracy=8.5,
    timestamp=NOW,
):
    return SimpleNamespace(
        latitude=latitude,
        longitude=longitude,
        accuracy=accuracy,
        timestamp=timestamp,
        created_at=NOW,
    )


def make_notification(
    *,
    notification_id="notification-1",
    tenant_id="tenant-1",
    user_id="customer-1",
    status="UNREAD",
    created_at=NOW,
):
    return SimpleNamespace(
        id=notification_id,
        tenant_id=tenant_id,
        customer_user_id=user_id,
        type="JOB_STATUS",
        title="Job update",
        body="Your job status changed.",
        status=status,
        created_at=created_at,
        job_id=101,
        read_at=None,
    )


# ============================================================
# FAKE CREATE-ROUTE ORM OBJECTS
# ============================================================


class FakeJob:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

        self.id = None
        self.assigned_technician_id = None


class FakeServiceRequest:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.id = None
        self.created_at = NOW
        self.updated_at = NOW
        self.cancellation_reason = None
        self.cancelled_at = None
        self.created_job = None


# ============================================================
# PROFILE COVERAGE
# ============================================================


def test_get_profile_missing_uses_user_defaults():
    db = FakeDB(
        {
            CustomerProfileModel: FakeQuery(
                first_result=None
            ),
            User: FakeQuery(
                first_result=make_user()
            ),
        }
    )

    result = asyncio.run(
        customer_portal.get_customer_profile(
            current_user=customer(),
            db=db,
        )
    )

    assert result.id == ""
    assert result.user_id == "customer-1"
    assert result.tenant_id == "tenant-1"
    assert result.full_name == "Test Customer"
    assert result.mobile_number == "9876543210"
    assert result.email == "customer@gmail.com"
    assert result.profile_completed is False


def test_get_profile_missing_user_returns_empty_defaults():
    db = FakeDB(
        {
            CustomerProfileModel: FakeQuery(
                first_result=None
            ),
            User: FakeQuery(
                first_result=None
            ),
        }
    )

    result = asyncio.run(
        customer_portal.get_customer_profile(
            current_user=customer(
                user_id="unknown-user",
                tenant_id="unknown-tenant",
            ),
            db=db,
        )
    )

    assert result.id == ""
    assert result.user_id == "unknown-user"
    assert result.tenant_id == "unknown-tenant"
    assert result.full_name == ""
    assert result.mobile_number == ""
    assert result.email == ""
    assert result.profile_completed is False


def test_get_profile_existing():
    db = FakeDB(
        {
            CustomerProfileModel: FakeQuery(
                first_result=make_profile()
            ),
            User: FakeQuery(
                first_result=make_user()
            ),
        }
    )

    result = asyncio.run(
        customer_portal.get_customer_profile(
            current_user=customer(),
            db=db,
        )
    )

    assert result.id == "profile-1"
    assert result.full_name == "Existing Customer"
    assert result.mobile_number == "9876543210"
    assert result.address == "10 Test Street"
    assert result.city == "Chennai"
    assert result.state == "Tamil Nadu"
    assert result.pincode == "600001"
    assert result.company_name == "Test Company"
    assert result.email == "customer@gmail.com"


def test_get_profile_existing_without_user():
    db = FakeDB(
        {
            CustomerProfileModel: FakeQuery(
                first_result=make_profile()
            ),
            User: FakeQuery(
                first_result=None
            ),
        }
    )

    result = asyncio.run(
        customer_portal.get_customer_profile(
            current_user=customer(),
            db=db,
        )
    )

    assert result.id == "profile-1"
    assert result.email is None


def test_create_profile_success(monkeypatch):
    monkeypatch.setattr(
        customer_portal,
        "audit_log",
        lambda *args, **kwargs: None,
    )

    db = FakeDB(
        {
            CustomerProfileModel: FakeQuery(
                first_result=None
            ),
            User: FakeQuery(
                first_result=make_user()
            ),
        }
    )

    payload = CustomerProfileCreate(
        full_name="New Customer",
        mobile_number="9876543210",
        address="20 New Street",
        city="Coimbatore",
        state="Tamil Nadu",
        pincode="641001",
        company_name="New Company",
    )

    result = asyncio.run(
        customer_portal.create_customer_profile(
            data=payload,
            request=None,
            current_user=customer(),
            db=db,
        )
    )

    assert len(db.added) == 1

    profile = db.added[0]

    assert profile.user_id == "customer-1"
    assert profile.tenant_id == "tenant-1"
    assert profile.full_name == "New Customer"
    assert profile.mobile_number == "9876543210"
    assert profile.address == "20 New Street"
    assert profile.city == "Coimbatore"
    assert profile.state == "Tamil Nadu"
    assert profile.pincode == "641001"
    assert profile.company_name == "New Company"
    assert profile.profile_completed is True

    assert result.full_name == "New Customer"
    assert result.email == "customer@gmail.com"


def test_create_profile_duplicate_returns_409(monkeypatch):
    monkeypatch.setattr(
        customer_portal,
        "audit_log",
        lambda *args, **kwargs: None,
    )

    db = FakeDB(
        {
            CustomerProfileModel: FakeQuery(
                first_result=make_profile()
            ),
        }
    )

    payload = CustomerProfileCreate(
        full_name="New Customer",
        mobile_number="9876543210",
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            customer_portal.create_customer_profile(
                data=payload,
                request=None,
                current_user=customer(),
                db=db,
            )
        )

    assert exc_info.value.status_code == 409
    assert db.added == []
    assert db.commit_count == 0


def test_create_profile_without_user_returns_none_email(monkeypatch):
    monkeypatch.setattr(
        customer_portal,
        "audit_log",
        lambda *args, **kwargs: None,
    )

    db = FakeDB(
        {
            CustomerProfileModel: FakeQuery(
                first_result=None
            ),
            User: FakeQuery(
                first_result=None
            ),
        }
    )

    payload = CustomerProfileCreate(
        full_name="New Customer",
        mobile_number="9876543210",
    )

    result = asyncio.run(
        customer_portal.create_customer_profile(
            data=payload,
            request=None,
            current_user=customer(),
            db=db,
        )
    )

    assert result.email is None
    assert result.profile_completed is True


def test_update_profile_missing_returns_404():
    db = FakeDB(
        {
            CustomerProfileModel: FakeQuery(
                first_result=None
            ),
        }
    )

    payload = CustomerProfileUpdate(
        full_name="Updated Customer"
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            customer_portal.update_customer_profile(
                data=payload,
                request=None,
                current_user=customer(),
                db=db,
            )
        )

    assert exc_info.value.status_code == 404
    assert db.commit_count == 0


def test_update_profile_success(monkeypatch):
    monkeypatch.setattr(
        customer_portal,
        "audit_log",
        lambda *args, **kwargs: None,
    )

    profile = make_profile()

    db = FakeDB(
        {
            CustomerProfileModel: FakeQuery(
                first_result=profile
            ),
            User: FakeQuery(
                first_result=make_user()
            ),
        }
    )

    payload = CustomerProfileUpdate(
        full_name="Updated Customer",
        city="Madurai",
        company_name=None,
    )

    result = asyncio.run(
        customer_portal.update_customer_profile(
            data=payload,
            request=None,
            current_user=customer(),
            db=db,
        )
    )

    assert profile.full_name == "Updated Customer"
    assert profile.city == "Madurai"
    assert profile.company_name == "Test Company"
    assert profile.profile_completed is True
    assert result.full_name == "Updated Customer"
    assert result.city == "Madurai"


def test_update_profile_without_user(monkeypatch):
    monkeypatch.setattr(
        customer_portal,
        "audit_log",
        lambda *args, **kwargs: None,
    )

    profile = make_profile()

    db = FakeDB(
        {
            CustomerProfileModel: FakeQuery(
                first_result=profile
            ),
            User: FakeQuery(
                first_result=None
            ),
        }
    )

    result = asyncio.run(
        customer_portal.update_customer_profile(
            data=CustomerProfileUpdate(
                full_name="Updated Customer"
            ),
            request=None,
            current_user=customer(),
            db=db,
        )
    )

    assert result.email is None


# ============================================================
# LOCATION HELPERS
# ============================================================


def test_haversine_same_point():
    result = customer_portal.haversine_km(
        13.0827,
        80.2707,
        13.0827,
        80.2707,
    )

    assert result == pytest.approx(0.0)


def test_haversine_different_points():
    result = customer_portal.haversine_km(
        13.0827,
        80.2707,
        12.9716,
        77.5946,
    )

    assert result > 0


class FakeHTTPResponse:
    def __init__(
        self,
        payload,
        *,
        raise_error=None,
    ):
        self.payload = payload
        self.raise_error = raise_error

    def raise_for_status(self):
        if self.raise_error:
            raise self.raise_error

    def json(self):
        return self.payload


def test_geocode_ola_success(monkeypatch):
    monkeypatch.setenv(
        "OLA_MAPS_API_KEY",
        "ola-test-key",
    )

    response = FakeHTTPResponse(
        {
            "geocodingResults": [
                {
                    "geometry": {
                        "location": {
                            "lat": 13.0827,
                            "lng": 80.2707,
                        }
                    }
                }
            ]
        }
    )

    monkeypatch.setattr(
        customer_portal.requests,
        "get",
        lambda *args, **kwargs: response,
    )

    result = customer_portal.geocode_customer_location(
        "Chennai"
    )

    assert result == {
        "longitude": 80.2707,
        "latitude": 13.0827,
    }


def test_geocode_ola_error_falls_back_to_photon(monkeypatch):
    monkeypatch.setenv(
        "OLA_MAPS_API_KEY",
        "ola-test-key",
    )

    calls = []

    def fake_get(*args, **kwargs):
        calls.append(args[0])

        if len(calls) == 1:
            raise requests.RequestException(
                "Ola unavailable"
            )

        return FakeHTTPResponse(
            {
                "features": [
                    {
                        "geometry": {
                            "coordinates": [
                                80.27,
                                13.08,
                            ]
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr(
        customer_portal.requests,
        "get",
        fake_get,
    )

    result = customer_portal.geocode_customer_location(
        "Chennai"
    )

    assert result == {
        "longitude": 80.27,
        "latitude": 13.08,
    }
    assert len(calls) == 2


def test_geocode_ola_missing_coordinates_falls_back(monkeypatch):
    monkeypatch.setenv(
        "OLA_MAPS_API_KEY",
        "ola-test-key",
    )

    calls = []

    def fake_get(*args, **kwargs):
        calls.append(args[0])

        if len(calls) == 1:
            return FakeHTTPResponse(
                {
                    "geocodingResults": [
                        {
                            "geometry": {
                                "location": {}
                            }
                        }
                    ]
                }
            )

        return FakeHTTPResponse(
            {
                "features": [
                    {
                        "geometry": {
                            "coordinates": [
                                80.3,
                                13.1,
                            ]
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr(
        customer_portal.requests,
        "get",
        fake_get,
    )

    result = customer_portal.geocode_customer_location(
        "Chennai"
    )

    assert result == {
        "longitude": 80.3,
        "latitude": 13.1,
    }


def test_geocode_photon_no_features(monkeypatch):
    monkeypatch.delenv(
        "OLA_MAPS_API_KEY",
        raising=False,
    )

    monkeypatch.setattr(
        customer_portal.requests,
        "get",
        lambda *args, **kwargs: FakeHTTPResponse(
            {
                "features": []
            }
        ),
    )

    result = customer_portal.geocode_customer_location(
        "Unknown"
    )

    assert result is None


def test_geocode_photon_error(monkeypatch):
    monkeypatch.delenv(
        "OLA_MAPS_API_KEY",
        raising=False,
    )

    def fail(*args, **kwargs):
        raise requests.RequestException(
            "Photon unavailable"
        )

    monkeypatch.setattr(
        customer_portal.requests,
        "get",
        fail,
    )

    assert (
        customer_portal.geocode_customer_location(
            "Unknown"
        )
        is None
    )


def test_latest_technician_ping():
    ping = make_ping()

    db = FakeDB(
        {
            customer_portal.GPSPing: FakeQuery(
                first_result=ping
            )
        }
    )

    result = customer_portal._latest_technician_ping(
        db,
        101,
    )

    assert result is ping


# ============================================================
# PASSWORD CHANGE
# ============================================================


def test_change_password_user_missing():
    db = FakeDB(
        {
            User: FakeQuery(
                first_result=None
            )
        }
    )

    payload = SimpleNamespace(
        current_password="old",
        new_password="NewPassword123",
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            customer_portal.change_password(
                data=payload,
                request=None,
                current_user=customer(),
                db=db,
            )
        )

    assert exc_info.value.status_code == 404


def test_change_password_wrong_current_password(monkeypatch):
    monkeypatch.setattr(
        customer_portal,
        "verify_password",
        lambda password, password_hash: False,
    )

    db = FakeDB(
        {
            User: FakeQuery(
                first_result=make_user()
            )
        }
    )

    payload = SimpleNamespace(
        current_password="wrong-password",
        new_password="NewPassword123",
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            customer_portal.change_password(
                data=payload,
                request=None,
                current_user=customer(),
                db=db,
            )
        )

    assert exc_info.value.status_code == 400
    assert (
        exc_info.value.detail
        == "Current password is incorrect"
    )


def test_change_password_success(monkeypatch):
    monkeypatch.setattr(
        customer_portal,
        "verify_password",
        lambda password, password_hash: True,
    )

    monkeypatch.setattr(
        customer_portal,
        "hash_password",
        lambda password: "new-hash",
    )

    monkeypatch.setattr(
        customer_portal,
        "audit_log",
        lambda *args, **kwargs: None,
    )

    user = make_user()

    db = FakeDB(
        {
            User: FakeQuery(
                first_result=user
            )
        }
    )

    payload = SimpleNamespace(
        current_password="old-password",
        new_password="NewPassword123",
    )

    result = asyncio.run(
        customer_portal.change_password(
            data=payload,
            request=None,
            current_user=customer(),
            db=db,
        )
    )

    assert user.password_hash == "new-hash"
    assert db.commit_count == 1
    assert result == {
        "message": "Password changed successfully"
    }


# ============================================================
# SERVICE REQUEST HELPERS
# ============================================================


def test_generate_request_number_format():
    request_number = (
        customer_portal._generate_request_number()
    )

    assert request_number.startswith("SR-")
    assert len(request_number) > 15


# ============================================================
# SERVICE REQUEST LIST
# ============================================================


def test_list_service_requests_with_status_filter():
    sr_one = make_service_request(
        sr_id=1,
        status="ASSIGNED",
    )

    db = FakeDB(
        {
            ServiceRequest: FakeQuery(
                all_result=[
                    (sr_one, "ASSIGNED")
                ]
            )
        }
    )

    result = asyncio.run(
        customer_portal.list_service_requests(
            status_filter="assigned",
            current_user=customer(),
            db=db,
        )
    )

    assert result == [sr_one]
    assert sr_one.status == "ASSIGNED"


def test_list_service_requests_without_status_filter():
    sr_one = make_service_request(
        sr_id=1,
        status="UNASSIGNED",
    )

    sr_two = make_service_request(
        sr_id=2,
        status="UNASSIGNED",
    )

    db = FakeDB(
        {
            ServiceRequest: FakeQuery(
                all_result=[
                    (sr_one, "ASSIGNED"),
                    (sr_two, None),
                ]
            )
        }
    )

    result = asyncio.run(
        customer_portal.list_service_requests(
            status_filter=None,
            current_user=customer(),
            db=db,
        )
    )

    assert result == [
        sr_one,
        sr_two,
    ]

    assert sr_one.status == "ASSIGNED"
    assert sr_two.status == "UNASSIGNED"


# ============================================================
# CREATE SERVICE REQUEST
# ============================================================


def create_service_request_payload(
    *,
    service_type="HVAC_REPAIR",
    location="Chennai",
    latitude=13.0827,
    longitude=80.2707,
):
    return ServiceRequestCreate(
        title="Air conditioner repair",
        description=(
            "The air conditioner is not cooling and requires repair."
        ),
        service_type=service_type,
        priority="HIGH",
        preferred_visit_date=date.today(),
        images=["before.jpg"],
        location=location,
        contact_number="9876543210",
        site_latitude=latitude,
        site_longitude=longitude,
    )


def test_create_service_request_missing_location():
    payload = create_service_request_payload(
        location=" ",
    )

    db = FakeDB(
        {
            User: FakeQuery(
                first_result=make_user()
            )
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            customer_portal.create_service_request(
                data=payload,
                request=None,
                current_user=customer(),
                db=db,
            )
        )

    assert exc_info.value.status_code == 400
    assert "location is required" in exc_info.value.detail.lower()


def test_create_service_request_missing_gps(monkeypatch):
    payload = create_service_request_payload()

    monkeypatch.setattr(
        customer_portal,
        "is_valid_coordinate",
        lambda lat, lng: False,
    )

    db = FakeDB(
        {
            User: FakeQuery(
                first_result=make_user()
            )
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            customer_portal.create_service_request(
                data=payload,
                request=None,
                current_user=customer(),
                db=db,
            )
        )

    assert exc_info.value.status_code == 400
    assert (
        exc_info.value.detail
        == "Customer GPS location is required."
    )


def test_create_service_request_no_capable_organization(
    monkeypatch,
):
    payload = create_service_request_payload()

    monkeypatch.setattr(
        customer_portal,
        "is_valid_coordinate",
        lambda lat, lng: True,
    )

    db = FakeDB(
        {
            User: FakeQuery(
                first_result=make_user()
            ),
            Technician: FakeQuery(
                all_result=[]
            ),
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            customer_portal.create_service_request(
                data=payload,
                request=None,
                current_user=customer(),
                db=db,
            )
        )

    assert exc_info.value.status_code == 400
    assert "No organization is available" in (
        exc_info.value.detail
    )


def test_create_service_request_no_organization_coordinates(
    monkeypatch,
):
    payload = create_service_request_payload()

    monkeypatch.setattr(
        customer_portal,
        "is_valid_coordinate",
        lambda lat, lng: True,
    )

    db = FakeDB(
        {
            User: FakeQuery(
                first_result=make_user()
            ),
            Technician: FakeQuery(
                all_result=[
                    ("provider-tenant",),
                ]
            ),
            Organization: FakeQuery(
                all_result=[]
            ),
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            customer_portal.create_service_request(
                data=payload,
                request=None,
                current_user=customer(),
                db=db,
            )
        )

    assert exc_info.value.status_code == 400
    assert "valid location" in exc_info.value.detail


def test_create_service_request_success(monkeypatch):
    payload = create_service_request_payload()

    monkeypatch.setattr(
        customer_portal,
        "is_valid_coordinate",
        lambda lat, lng: True,
    )

    monkeypatch.setattr(
        customer_portal,
        "audit_log",
        lambda *args, **kwargs: None,
    )

    monkeypatch.setattr(
        customer_portal,
        "Job",
        FakeJob,
    )

    monkeypatch.setattr(
        customer_portal,
        "ServiceRequest",
        FakeServiceRequest,
    )

    user = make_user(
        first_name="Test",
        last_name="Customer",
        email="customer@gmail.com",
    )

    organization_one = SimpleNamespace(
        id="provider-tenant",
        site_latitude=13.10,
        site_longitude=80.30,
    )

    organization_two = SimpleNamespace(
        id="provider-tenant-two",
        site_latitude=13.20,
        site_longitude=80.40,
    )

    db = FakeDB(
        {
            User: FakeQuery(
                first_result=user
            ),
            Technician: FakeQuery(
                all_result=[
                    ("provider-tenant",),
                    ("provider-tenant-two",),
                    (None,),
                ]
            ),
            Organization: FakeQuery(
                all_result=[
                    organization_one,
                    organization_two,
                ]
            ),
        }
    )

    result = asyncio.run(
        customer_portal.create_service_request(
            data=payload,
            request=None,
            current_user=customer(),
            db=db,
        )
    )

    assert result["customer_user_id"] == "customer-1"
    assert result["status"] == "UNASSIGNED"
    assert result["linked_job_id"] == 700

    assert result["created_job"]["id"] == 700
    assert result["created_job"]["customer_id"] == "customer-1"
    assert result["created_job"]["customer_tenant_id"] == "tenant-1"

    assert db.commit_count == 1
    assert db.flush_count == 2


def test_create_service_request_user_fallback_and_optional_values(
    monkeypatch,
):
    payload = ServiceRequestCreate(
        title="General service",
        description="General service request description",
        service_type=None,
        priority="MEDIUM",
        preferred_visit_date=None,
        images=[],
        location="Chennai",
        contact_number=None,
        site_latitude=13.0827,
        site_longitude=80.2707,
    )

    monkeypatch.setattr(
        customer_portal,
        "is_valid_coordinate",
        lambda lat, lng: True,
    )

    monkeypatch.setattr(
        customer_portal,
        "audit_log",
        lambda *args, **kwargs: None,
    )

    monkeypatch.setattr(
        customer_portal,
        "Job",
        FakeJob,
    )

    monkeypatch.setattr(
        customer_portal,
        "ServiceRequest",
        FakeServiceRequest,
    )

    organization = SimpleNamespace(
        id="provider-tenant",
        site_latitude=13.10,
        site_longitude=80.30,
    )

    db = FakeDB(
        {
            User: FakeQuery(
                first_result=None
            ),
            Technician: FakeQuery(
                all_result=[
                    ("provider-tenant",)
                ]
            ),
            Organization: FakeQuery(
                all_result=[
                    organization
                ]
            ),
        }
    )

    result = asyncio.run(
        customer_portal.create_service_request(
            data=payload,
            request=None,
            current_user=customer(),
            db=db,
        )
    )

    assert result["status"] == "UNASSIGNED"
    assert result["created_job"]["status"] == "CREATED"


def test_create_service_request_transaction_failure(
    monkeypatch,
):
    payload = create_service_request_payload()

    monkeypatch.setattr(
        customer_portal,
        "is_valid_coordinate",
        lambda lat, lng: True,
    )

    monkeypatch.setattr(
        customer_portal,
        "audit_log",
        lambda *args, **kwargs: None,
    )

    monkeypatch.setattr(
        customer_portal,
        "Job",
        FakeJob,
    )

    monkeypatch.setattr(
        customer_portal,
        "ServiceRequest",
        FakeServiceRequest,
    )

    organization = SimpleNamespace(
        id="provider-tenant",
        site_latitude=13.10,
        site_longitude=80.30,
    )

    db = FakeDB(
        {
            User: FakeQuery(
                first_result=make_user()
            ),
            Technician: FakeQuery(
                all_result=[
                    ("provider-tenant",)
                ]
            ),
            Organization: FakeQuery(
                all_result=[
                    organization
                ]
            ),
        },
        flush_error=RuntimeError(
            "forced flush failure"
        ),
    )

    with pytest.raises(RuntimeError):
        asyncio.run(
            customer_portal.create_service_request(
                data=payload,
                request=None,
                current_user=customer(),
                db=db,
            )
        )

    assert db.rollback_count == 1


# ============================================================
# GET SERVICE REQUEST
# ============================================================


def test_get_service_request_not_found():
    db = FakeDB(
        {
            ServiceRequest: FakeQuery(
                first_result=None
            )
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            customer_portal.get_service_request(
                sr_id=999,
                current_user=customer(),
                db=db,
            )
        )

    assert exc_info.value.status_code == 404


def test_get_service_request_success():
    sr = make_service_request()

    db = FakeDB(
        {
            ServiceRequest: FakeQuery(
                first_result=sr
            )
        }
    )

    result = asyncio.run(
        customer_portal.get_service_request(
            sr_id=1,
            current_user=customer(),
            db=db,
        )
    )

    assert result is sr


# ============================================================
# UPDATE SERVICE REQUEST
# ============================================================


def full_update_payload():
    return ServiceRequestUpdate(
        title="Updated equipment repair request",
        description=(
            "Please update all details for this customer repair request."
        ),
        service_type="PLUMBING",
        priority="CRITICAL",
        preferred_visit_date=date.today(),
        images=["updated.jpg"],
        location="Madurai",
        contact_number="9123456789",
    )


def test_update_service_request_not_found():
    db = FakeDB(
        {
            ServiceRequest: FakeQuery(
                first_result=None
            )
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            customer_portal.update_service_request(
                sr_id=1,
                data=ServiceRequestUpdate(
                    title="Updated title"
                ),
                request=None,
                current_user=customer(),
                db=db,
            )
        )

    assert exc_info.value.status_code == 404


def test_update_service_request_rejects_non_pending():
    sr = make_service_request(
        status="ASSIGNED",
        linked_job_id=None,
    )

    db = FakeDB(
        {
            ServiceRequest: FakeQuery(
                first_result=sr
            )
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            customer_portal.update_service_request(
                sr_id=1,
                data=ServiceRequestUpdate(
                    title="Updated title"
                ),
                request=None,
                current_user=customer(),
                db=db,
            )
        )

    assert exc_info.value.status_code == 400


def test_update_service_request_missing_linked_job(
    monkeypatch,
):
    monkeypatch.setattr(
        customer_portal,
        "audit_log",
        lambda *args, **kwargs: None,
    )

    sr = make_service_request(
        linked_job_id=101,
    )

    db = FakeDB(
        {
            ServiceRequest: FakeQuery(
                first_result=sr
            ),
            Job: FakeQuery(
                first_result=None
            ),
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            customer_portal.update_service_request(
                sr_id=1,
                data=ServiceRequestUpdate(
                    title="Updated title"
                ),
                request=None,
                current_user=customer(),
                db=db,
            )
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Linked job not found"


def test_update_service_request_all_fields(monkeypatch):
    monkeypatch.setattr(
        customer_portal,
        "audit_log",
        lambda *args, **kwargs: None,
    )

    sr = make_service_request(
        linked_job_id=101,
        status="UNASSIGNED",
    )

    linked_job = make_job(
        job_id=101,
        status="CREATED",
        assigned_technician_id=None,
    )

    db = FakeDB(
        {
            ServiceRequest: FakeQuery(
                first_result=sr
            ),
            Job: FakeQuery(
                first_result=linked_job
            ),
        }
    )

    result = asyncio.run(
        customer_portal.update_service_request(
            sr_id=1,
            data=full_update_payload(),
            request=None,
            current_user=customer(),
            db=db,
        )
    )

    assert result is sr

    assert sr.title == "Updated equipment repair request"
    assert sr.service_type == "PLUMBING"
    assert sr.priority == "CRITICAL"
    assert sr.location == "Madurai"
    assert sr.contact_number == "9123456789"

    assert (
        linked_job.issue_description
        == (
            "Updated equipment repair request: "
            "Please update all details for this customer repair request."
        )
    )

    assert linked_job.service_type == "PLUMBING"
    assert linked_job.required_skill == "PLUMBING"
    assert linked_job.priority == "CRITICAL"
    assert linked_job.location == "Madurai"
    assert linked_job.site_address == "Madurai"
    assert linked_job.contact_number == "9123456789"
    assert linked_job.preferred_service_date == date.today()

    assert db.commit_count == 1


def test_update_service_request_without_linked_job():
    sr = make_service_request(
        linked_job_id=None,
        status="UNASSIGNED",
    )

    db = FakeDB(
        {
            ServiceRequest: FakeQuery(
                first_result=sr
            )
        }
    )

    monkeypatch = pytest.MonkeyPatch()

    try:
        monkeypatch.setattr(
            customer_portal,
            "audit_log",
            lambda *args, **kwargs: None,
        )

        result = asyncio.run(
            customer_portal.update_service_request(
                sr_id=1,
                data=ServiceRequestUpdate(
                    title="Updated customer request"
                ),
                request=None,
                current_user=customer(),
                db=db,
            )
        )
    finally:
        monkeypatch.undo()

    assert result is sr
    assert sr.title == "Updated customer request"


# ============================================================
# CANCEL SERVICE REQUEST
# ============================================================


def test_cancel_service_request_not_found():
    db = FakeDB(
        {
            ServiceRequest: FakeQuery(
                first_result=None
            )
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            customer_portal.cancel_service_request(
                sr_id=1,
                request=None,
                current_user=customer(),
                db=db,
            )
        )

    assert exc_info.value.status_code == 404


def test_cancel_service_request_rejects_non_pending():
    sr = make_service_request(
        status="COMPLETED",
        linked_job_id=None,
    )

    db = FakeDB(
        {
            ServiceRequest: FakeQuery(
                first_result=sr
            )
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            customer_portal.cancel_service_request(
                sr_id=1,
                request=None,
                current_user=customer(),
                db=db,
            )
        )

    assert exc_info.value.status_code == 400


def test_cancel_service_request_missing_linked_job():
    sr = make_service_request(
        linked_job_id=101,
    )

    db = FakeDB(
        {
            ServiceRequest: FakeQuery(
                first_result=sr
            ),
            Job: FakeQuery(
                first_result=None
            ),
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            customer_portal.cancel_service_request(
                sr_id=1,
                request=None,
                current_user=customer(),
                db=db,
            )
        )

    assert exc_info.value.status_code == 400 or (
        exc_info.value.status_code == 404
    )


def test_cancel_service_request_success_with_linked_job(
    monkeypatch,
):
    monkeypatch.setattr(
        customer_portal,
        "audit_log",
        lambda *args, **kwargs: None,
    )

    sr = make_service_request(
        linked_job_id=101,
        status="ASSIGNED",
    )

    linked_job = make_job(
        job_id=101,
        status="ASSIGNED",
    )

    def transition(
        new_status,
        actor_id,
        actor_role,
        reason,
    ):
        assert new_status == "CANCELLED"
        assert actor_id == "customer-1"
        assert actor_role == "customer"
        assert reason == "Cancelled by customer"

        linked_job.status = "CANCELLED"

    linked_job.transition = transition

    db = FakeDB(
        {
            ServiceRequest: FakeQuery(
                first_result=sr
            ),
            Job: FakeQuery(
                first_result=linked_job
            ),
        }
    )

    result = asyncio.run(
        customer_portal.cancel_service_request(
            sr_id=1,
            request=None,
            current_user=customer(),
            db=db,
        )
    )

    assert result == {
        "message": "Service request cancelled",
        "id": 1,
    }

    assert sr.status == "CANCELLED"
    assert sr.cancellation_reason == "Cancelled by customer"
    assert sr.cancelled_at is not None
    assert linked_job.status == "CANCELLED"


def test_cancel_service_request_success_without_linked_job(
    monkeypatch,
):
    monkeypatch.setattr(
        customer_portal,
        "audit_log",
        lambda *args, **kwargs: None,
    )

    sr = make_service_request(
        linked_job_id=None,
        status="UNASSIGNED",
    )

    db = FakeDB(
        {
            ServiceRequest: FakeQuery(
                first_result=sr
            )
        }
    )

    result = asyncio.run(
        customer_portal.cancel_service_request(
            sr_id=1,
            request=None,
            current_user=customer(),
            db=db,
        )
    )

    assert result["message"] == "Service request cancelled"
    assert sr.status == "CANCELLED"


@pytest.mark.parametrize(
    "exception_kind",
    [
        "invalid",
        "permission",
        "reason",
        "generic",
    ],
)
def test_cancel_service_request_transition_exceptions(
    monkeypatch,
    exception_kind,
):
    import app.services.job_status_machine as jsm

    class FakeInvalidTransitionError(Exception):
        def __init__(self, message):
            self.message = message
            super().__init__(message)

    class FakePermissionDeniedError(Exception):
        pass

    class FakeReasonRequiredError(Exception):
        pass

    monkeypatch.setattr(
        jsm,
        "InvalidTransitionError",
        FakeInvalidTransitionError,
    )

    monkeypatch.setattr(
        jsm,
        "PermissionDeniedError",
        FakePermissionDeniedError,
    )

    monkeypatch.setattr(
        jsm,
        "ReasonRequiredError",
        FakeReasonRequiredError,
    )

    sr = make_service_request(
        linked_job_id=101,
        status="ASSIGNED",
    )

    linked_job = make_job(
        job_id=101,
        status="ASSIGNED",
    )

    if exception_kind == "invalid":

        def transition(*args, **kwargs):
            raise FakeInvalidTransitionError(
                "Invalid transition"
            )

    elif exception_kind == "permission":

        def transition(*args, **kwargs):
            raise FakePermissionDeniedError(
                "Permission denied"
            )

    elif exception_kind == "reason":

        def transition(*args, **kwargs):
            raise FakeReasonRequiredError(
                "Reason required"
            )

    else:

        def transition(*args, **kwargs):
            raise RuntimeError(
                "Generic failure"
            )

    linked_job.transition = transition

    db = FakeDB(
        {
            ServiceRequest: FakeQuery(
                first_result=sr
            ),
            Job: FakeQuery(
                first_result=linked_job
            ),
        }
    )

    if exception_kind == "generic":
        with pytest.raises(
            RuntimeError,
            match="Generic failure",
        ):
            asyncio.run(
                customer_portal.cancel_service_request(
                    sr_id=1,
                    request=None,
                    current_user=customer(),
                    db=db,
                )
            )

        assert db.rollback_count == 1
        return

    with pytest.raises(
        HTTPException
    ) as exc_info:
        asyncio.run(
            customer_portal.cancel_service_request(
                sr_id=1,
                request=None,
                current_user=customer(),
                db=db,
            )
        )

    assert db.rollback_count == 1

    if exception_kind == "invalid":
        assert exc_info.value.status_code == 400
        assert (
            exc_info.value.detail
            == "Invalid transition"
        )

    elif exception_kind == "permission":
        assert exc_info.value.status_code == 400
        assert (
            exc_info.value.detail
            == "Permission denied"
        )

    elif exception_kind == "reason":
        assert exc_info.value.status_code == 400
        assert (
            exc_info.value.detail
            == "Reason required"
        )


# ============================================================
# CUSTOMER JOB TRACKING
# ============================================================


def test_track_customer_jobs_full_path():
    job_one = make_job(
        job_id=101,
        status="EN_ROUTE",
        assigned_technician_id=10,
        tenant_id="provider-tenant",
        site_address="10 Main Street",
    )

    job_two = make_job(
        job_id=102,
        status="ASSIGNED",
        assigned_technician_id=20,
        tenant_id="provider-tenant-2",
        site_address=None,
        location="Fallback Location",
    )

    tech_one = make_technician(
        technician_id=10,
        tenant_id="provider-tenant",
        tech_id="tech-user-1",
        name="Technician One",
        phone="9000000001",
    )

    tech_two = make_technician(
        technician_id=20,
        tenant_id="provider-tenant-2",
        tech_id=None,
        name="Technician Two",
        phone="9000000002",
    )

    profile = make_technician_profile(
        user_id="tech-user-1",
        tenant_id="provider-tenant",
        photo="/photos/one.jpg",
    )

    ping_one = make_ping(
        latitude=13.05,
        longitude=80.25,
        accuracy=7.0,
    )

    db = FakeDB(
        {
            Job: FakeQuery(
                all_result=[
                    job_one,
                    job_two,
                ]
            ),
            Technician: FakeQuery(
                all_result=[
                    tech_one,
                    tech_two,
                ]
            ),
            TechnicianProfile: FakeQuery(
                all_result=[
                    profile,
                ]
            ),
            customer_portal.GPSPing: [
                FakeQuery(
                    first_result=ping_one
                ),
                FakeQuery(
                    first_result=None
                ),
            ],
        }
    )

    result = asyncio.run(
        customer_portal.track_customer_jobs(
            current_user=customer(),
            db=db,
        )
    )

    assert len(result) == 2

    first = result[0]
    second = result[1]

    assert first.assigned_technician_name == (
        "Technician One"
    )
    assert first.assigned_technician_photo == (
        "/photos/one.jpg"
    )
    assert first.assigned_technician_phone == (
        "9000000001"
    )
    assert first.technician_latitude == 13.05
    assert first.technician_longitude == 80.25
    assert first.technician_accuracy == 7.0
    assert first.live_tracking is True
    assert first.site_address == "10 Main Street"

    assert second.assigned_technician_name == (
        "Technician Two"
    )
    assert second.assigned_technician_photo is None
    assert second.technician_latitude is None
    assert second.live_tracking is False
    assert second.site_address == "Fallback Location"


def test_track_customer_jobs_empty():
    db = FakeDB(
        {
            Job: FakeQuery(
                all_result=[]
            ),
            Technician: FakeQuery(
                all_result=[]
            ),
            TechnicianProfile: FakeQuery(
                all_result=[]
            ),
        }
    )

    result = asyncio.run(
        customer_portal.track_customer_jobs(
            current_user=customer(),
            db=db,
        )
    )

    assert result == []


# ============================================================
# CUSTOMER JOB DETAIL
# ============================================================


def test_get_customer_job_detail_not_found():
    db = FakeDB(
        {
            Job: FakeQuery(
                first_result=None
            )
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            customer_portal.get_customer_job_detail(
                job_id=999,
                current_user=customer(),
                db=db,
            )
        )

    assert exc_info.value.status_code == 404


def test_get_customer_job_detail_without_technician():
    job = make_job(
        assigned_technician_id=None,
        site_address=None,
    )

    db = FakeDB(
        {
            Job: FakeQuery(
                first_result=job
            ),
            customer_portal.GPSPing: FakeQuery(
                first_result=None
            ),
        }
    )

    result = asyncio.run(
        customer_portal.get_customer_job_detail(
            job_id=101,
            current_user=customer(),
            db=db,
        )
    )

    assert result.id == 101
    assert result.assigned_technician_name is None
    assert result.site_address == job.location
    assert result.live_tracking is False


def test_get_customer_job_detail_with_technician_and_profile():
    job = make_job(
        assigned_technician_id=10,
        status="EN_ROUTE",
        tenant_id="provider-tenant",
    )

    tech = make_technician(
        technician_id=10,
        tenant_id="provider-tenant",
        tech_id="tech-user-1",
        name="Technician One",
        phone="9000000001",
    )

    profile = make_technician_profile(
        user_id="tech-user-1",
        tenant_id="provider-tenant",
        photo="/photos/one.jpg",
    )

    ping = make_ping(
        latitude=13.05,
        longitude=80.25,
        accuracy=5.0,
    )

    db = FakeDB(
        {
            Job: FakeQuery(
                first_result=job
            ),
            Technician: FakeQuery(
                first_result=tech
            ),
            TechnicianProfile: FakeQuery(
                first_result=profile
            ),
            customer_portal.GPSPing: FakeQuery(
                first_result=ping
            ),
        }
    )

    result = asyncio.run(
        customer_portal.get_customer_job_detail(
            job_id=101,
            current_user=customer(),
            db=db,
        )
    )

    assert result.assigned_technician_name == (
        "Technician One"
    )
    assert result.assigned_technician_photo == (
        "/photos/one.jpg"
    )
    assert result.assigned_technician_phone == (
        "9000000001"
    )
    assert result.technician_latitude == 13.05
    assert result.technician_longitude == 80.25
    assert result.technician_accuracy == 5.0
    assert result.live_tracking is True


def test_get_customer_job_detail_technician_without_profile():
    job = make_job(
        assigned_technician_id=10,
        tenant_id="provider-tenant",
    )

    tech = make_technician(
        technician_id=10,
        tenant_id="provider-tenant",
        tech_id="tech-user-1",
    )

    db = FakeDB(
        {
            Job: FakeQuery(
                first_result=job
            ),
            Technician: FakeQuery(
                first_result=tech
            ),
            TechnicianProfile: FakeQuery(
                first_result=None
            ),
            customer_portal.GPSPing: FakeQuery(
                first_result=None
            ),
        }
    )

    result = asyncio.run(
        customer_portal.get_customer_job_detail(
            job_id=101,
            current_user=customer(),
            db=db,
        )
    )

    assert result.assigned_technician_photo is None


# ============================================================
# CUSTOMER REPORT
# ============================================================


def test_download_customer_job_report_not_found():
    db = FakeDB(
        {
            JobClosure: FakeQuery(
                first_result=None
            )
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            customer_portal.download_customer_job_report(
                job_id=101,
                current_user=customer(),
                db=db,
            )
        )

    assert exc_info.value.status_code == 404


def test_download_customer_job_report_success(monkeypatch):
    import reportlab.lib.pagesizes as pagesizes
    import reportlab.pdfgen.canvas as canvas_module

    monkeypatch.setattr(
        pagesizes,
        "A4",
        (100, 100),
    )

    calls = {
        "pages": 0,
        "strings": 0,
    }

    class FakeCanvas:
        def __init__(self, buffer, pagesize):
            self.buffer = buffer
            self.pagesize = pagesize

        def setTitle(self, value):
            self.title = value

        def setFont(self, name, size):
            self.font = (name, size)

        def drawString(self, x, y, value):
            calls["strings"] += 1

        def showPage(self):
            calls["pages"] += 1

        def save(self):
            pass

    monkeypatch.setattr(
        canvas_module,
        "Canvas",
        FakeCanvas,
    )

    closure = SimpleNamespace(
        completed_at=NOW,
        work_summary="Completed repair successfully.",
        id=1,
    )

    job = make_job(
        job_id=101,
        service_type="HVAC_REPAIR",
        status="COMPLETED",
        location="Chennai",
    )

    db = FakeDB(
        {
            JobClosure: FakeQuery(
                first_result=(closure, job)
            )
        }
    )

    response = asyncio.run(
        customer_portal.download_customer_job_report(
            job_id=101,
            current_user=customer(),
            db=db,
        )
    )

    assert response.media_type == "application/pdf"
    assert (
        "service_report_job_101.pdf"
        in response.headers["content-disposition"]
    )
    assert calls["strings"] > 0
    assert calls["pages"] > 0


def test_download_customer_job_report_fallback_fields(
    monkeypatch,
):
    import reportlab.lib.pagesizes as pagesizes
    import reportlab.pdfgen.canvas as canvas_module

    monkeypatch.setattr(
        pagesizes,
        "A4",
        (100, 100),
    )

    class FakeCanvas:
        def __init__(self, buffer, pagesize):
            pass

        def setTitle(self, value):
            pass

        def setFont(self, name, size):
            pass

        def drawString(self, x, y, value):
            pass

        def showPage(self):
            pass

        def save(self):
            pass

    monkeypatch.setattr(
        canvas_module,
        "Canvas",
        FakeCanvas,
    )

    closure = SimpleNamespace(
        completed_at=None,
        work_summary=None,
        id=2,
    )

    job = SimpleNamespace(
        id=102,
        service_type=None,
        status=None,
        location=None,
        site_address="Fallback Address",
    )

    db = FakeDB(
        {
            JobClosure: FakeQuery(
                first_result=(closure, job)
            )
        }
    )

    response = asyncio.run(
        customer_portal.download_customer_job_report(
            job_id=102,
            current_user=customer(),
            db=db,
        )
    )

    assert response.media_type == "application/pdf"


# ============================================================
# SERVICE HISTORY
# ============================================================


def test_get_service_history():
    completed = make_service_request(
        sr_id=1,
        status="COMPLETED",
    )

    cancelled = make_service_request(
        sr_id=2,
        status="CANCELLED",
    )

    db = FakeDB(
        {
            ServiceRequest: FakeQuery(
                all_result=[
                    completed,
                    cancelled,
                ]
            )
        }
    )

    result = asyncio.run(
        customer_portal.get_service_history(
            current_user=customer(),
            db=db,
        )
    )

    assert result == [
        completed,
        cancelled,
    ]


# ============================================================
# NOTIFICATIONS
# ============================================================


def test_get_notifications():
    unread = make_notification(
        notification_id="1",
        status="UNREAD",
        created_at=NOW,
    )

    read = make_notification(
        notification_id="2",
        status="READ",
        created_at=None,
    )

    db = FakeDB(
        {
            InAppNotification: [
                FakeQuery(
                    all_result=[
                        unread,
                        read,
                    ]
                ),
                FakeQuery(
                    count_results=[1]
                ),
            ]
        }
    )

    result = asyncio.run(
        customer_portal.get_notifications(
            current_user=customer(),
            db=db,
        )
    )

    assert result["unread_count"] == 1
    assert len(result["notifications"]) == 2

    first = result["notifications"][0]
    second = result["notifications"][1]

    assert first["id"] == "1"
    assert first["isRead"] is False
    assert first["createdAt"] == NOW.isoformat()

    assert second["id"] == "2"
    assert second["isRead"] is True
    assert second["createdAt"] is None


# ============================================================
# MARK NOTIFICATION READ
# ============================================================


def test_mark_notification_read_not_found():
    db = FakeDB(
        {
            InAppNotification: FakeQuery(
                first_result=None
            )
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            customer_portal.mark_notification_read(
                notification_id="missing",
                current_user=customer(),
                db=db,
            )
        )

    assert exc_info.value.status_code == 404


def test_mark_notification_read_success():
    notification = make_notification(
        status="UNREAD"
    )

    db = FakeDB(
        {
            InAppNotification: FakeQuery(
                first_result=notification
            )
        }
    )

    result = asyncio.run(
        customer_portal.mark_notification_read(
            notification_id="notification-1",
            current_user=customer(),
            db=db,
        )
    )

    assert notification.status == "READ"
    assert notification.read_at is not None
    assert db.commit_count == 1
    assert result == {
        "message": "Marked as read"
    }


def test_mark_notification_read_commit_failure(
    monkeypatch,
):
    notification = make_notification(
        status="UNREAD"
    )

    db = FakeDB(
        {
            InAppNotification: FakeQuery(
                first_result=notification
            )
        },
        commit_error=RuntimeError(
            "forced commit failure"
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            customer_portal.mark_notification_read(
                notification_id="notification-1",
                current_user=customer(),
                db=db,
            )
        )

    assert (
        exc_info.value.status_code == 500
    )

    assert (
        exc_info.value.detail
        == "Unable to mark notification as read"
    )

    assert db.rollback_count == 1


# ============================================================
# MARK ALL READ
# ============================================================


def test_mark_all_read():
    query = FakeQuery(
        update_result=4
    )

    db = FakeDB(
        {
            InAppNotification: query
        }
    )

    result = asyncio.run(
        customer_portal.mark_all_read(
            current_user=customer(),
            db=db,
        )
    )

    assert result == {
        "message": "All notifications marked as read"
    }

    assert db.commit_count == 1

    assert query.update_values["status"] == "READ"
    assert query.update_values["read_at"] is not None


# ============================================================
# DASHBOARD
# ============================================================


def test_get_customer_dashboard():
    db = FakeDB(
        {
            ServiceRequest: FakeQuery(
                count_results=[
                    8,
                    3,
                    4,
                    1,
                ]
            )
        }
    )

    result = asyncio.run(
        customer_portal.get_customer_dashboard(
            current_user=customer(),
            db=db,
        )
    )

    assert result.total_requests == 8
    assert result.pending_requests == 3
    assert result.active_jobs == 4
    assert result.completed_jobs == 1