"""
Customer notification authorization tests.

These tests verify:

1. A customer can see their own notifications.
2. A customer cannot see another customer's notifications.
3. A customer cannot see notifications from another tenant.
4. A customer cannot mark another customer's notification as read.
5. Customer read-all only affects the authenticated customer's notifications.
6. A customer cannot mark another tenant's notification as read.

The customer API is mounted under:
    /api/customer
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.auth.rbac import UserRole
from app.database import SessionLocal
from app.main import app
from app.routes.in_app_notifications import InAppNotification
from app.models.organization import Organization
from app.models.user import User


client = TestClient(app)


# ============================================================================
# Database fixture
# ============================================================================


@pytest.fixture
def db():
    """
    Database session used for test setup and verification.

    The application uses its own DB session, so test data is committed
    before API requests are made.
    """
    session = SessionLocal()

    try:
        yield session
    finally:
        session.close()


# ============================================================================
# Test-data helpers
# ============================================================================


def create_organization(
    db,
    name=None,
    status="ACTIVE",
):
    """
    Create a valid test organization.
    """
    organization = Organization(
        id=f"org-{uuid.uuid4().hex[:12]}",
        name=name
        or f"Customer Notification Test Organization "
           f"{uuid.uuid4().hex[:8]}",
        slug=f"customer-notification-{uuid.uuid4().hex[:12]}",
        status=status,
        subscription_plan="FREE",
        max_users=100,
        max_technicians=50,
        max_jobs_per_month=500,
        settings={},
    )

    db.add(organization)
    db.commit()
    db.refresh(organization)

    return organization


def create_customer(
    db,
    organization,
    email=None,
):
    """
    Create a valid CUSTOMER belonging to the supplied organization.
    """
    user = User(
        id=str(uuid.uuid4()),
        email=email
        or f"customer-{uuid.uuid4().hex[:12]}@example.com",
        password_hash="test-password-hash",
        first_name="Test",
        last_name="Customer",
        role=UserRole.CUSTOMER,
        tenant_id=organization.id,
        phone_number=None,
        fcm_token=None,
        device_type=None,
        is_active=True,
        is_email_verified=True,
        is_on_duty=False,
        failed_login_attempts=0,
        locked_until=None,
        last_login=None,
        deleted_at=None,
        deleted_by=None,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


def create_notification(
    db,
    organization,
    customer_user_id,
    status="UNREAD",
    title="Test Notification",
    notification_type="JOB_ASSIGNED",
):
    """
    Create a customer-owned notification.

    Customer notifications use:
        customer_user_id=<customer id>

    Technician notifications use tech_id instead and are intentionally
    not created by these customer authorization tests.
    """
    notification = InAppNotification(
        id=str(uuid.uuid4()),
        tenant_id=organization.id,
        tech_id=None,
        customer_user_id=str(customer_user_id),
        job_id=str(uuid.uuid4()),
        type=notification_type,
        title=title,
        body="Test notification body",
        status=status,
        action_url=None,
        action_type=None,
        priority="NORMAL",
        notification_metadata={},
    )

    db.add(notification)
    db.commit()
    db.refresh(notification)

    return notification


# ============================================================================
# Authentication helpers
# ============================================================================


def override_customer_auth(customer):
    """
    Authenticate API requests as the supplied customer.
    """
    authenticated_user = AuthenticatedUser(
        user_id=str(customer.id),
        tenant_id=str(customer.tenant_id),
        role=UserRole.CUSTOMER,
        jti="customer-test-jti",
        session_id="customer-test-session",
    )

    app.dependency_overrides[get_current_user] = (
        lambda: authenticated_user
    )


def clear_customer_auth_override():
    """
    Remove the test authentication override.
    """
    app.dependency_overrides.pop(
        get_current_user,
        None,
    )


# ============================================================================
# 1. Customer can see own notification
# ============================================================================


def test_customer_can_see_own_notification(db):
    """
    A customer must be able to retrieve their own notification.
    """
    organization = create_organization(db)

    customer = create_customer(
        db,
        organization,
    )

    notification = create_notification(
        db,
        organization,
        customer_user_id=customer.id,
        title="Technician Assigned",
    )

    override_customer_auth(customer)

    try:
        response = client.get(
            "/api/customer/notifications"
        )
    finally:
        clear_customer_auth_override()

    assert response.status_code == 200

    body = response.json()

    assert "notifications" in body

    notification_ids = [
        item["id"]
        for item in body["notifications"]
    ]

    assert str(notification.id) in notification_ids


# ============================================================================
# 2. Customer cannot see another customer's notification
# ============================================================================


def test_customer_cannot_see_other_customer_notification(db):
    """
    Customer A must not receive Customer B's notification.
    """
    organization = create_organization(db)

    customer_a = create_customer(
        db,
        organization,
    )

    customer_b = create_customer(
        db,
        organization,
    )

    customer_a_notification = create_notification(
        db,
        organization,
        customer_user_id=customer_a.id,
        title="Customer A Notification",
    )

    customer_b_notification = create_notification(
        db,
        organization,
        customer_user_id=customer_b.id,
        title="Customer B Notification",
    )

    override_customer_auth(customer_a)

    try:
        response = client.get(
            "/api/customer/notifications"
        )
    finally:
        clear_customer_auth_override()

    assert response.status_code == 200

    body = response.json()

    notification_ids = [
        item["id"]
        for item in body["notifications"]
    ]

    assert str(customer_a_notification.id) in notification_ids

    assert str(customer_b_notification.id) not in notification_ids


# ============================================================================
# 3. Customer cannot see another tenant's notification
# ============================================================================


def test_customer_cannot_see_other_tenant_notification(db):
    """
    Customer A must not receive a notification belonging to another tenant.
    """
    organization_a = create_organization(
        db,
        name="Customer Tenant A",
    )

    organization_b = create_organization(
        db,
        name="Customer Tenant B",
    )

    customer_a = create_customer(
        db,
        organization_a,
    )

    customer_b = create_customer(
        db,
        organization_b,
    )

    own_notification = create_notification(
        db,
        organization_a,
        customer_user_id=customer_a.id,
        title="Own Tenant Notification",
    )

    other_tenant_notification = create_notification(
        db,
        organization_b,
        customer_user_id=customer_b.id,
        title="Other Tenant Notification",
    )

    override_customer_auth(customer_a)

    try:
        response = client.get(
            "/api/customer/notifications"
        )
    finally:
        clear_customer_auth_override()

    assert response.status_code == 200

    body = response.json()

    notification_ids = [
        item["id"]
        for item in body["notifications"]
    ]

    assert str(own_notification.id) in notification_ids

    assert str(other_tenant_notification.id) not in notification_ids


# ============================================================================
# 4. Customer cannot mark another customer's notification as read
# ============================================================================


def test_customer_cannot_mark_other_customer_notification_as_read(db):
    """
    Customer A must not be able to modify Customer B's notification.
    """
    organization = create_organization(db)

    customer_a = create_customer(
        db,
        organization,
    )

    customer_b = create_customer(
        db,
        organization,
    )

    other_customer_notification = create_notification(
        db,
        organization,
        customer_user_id=customer_b.id,
        status="UNREAD",
        title="Customer B Private Notification",
    )

    override_customer_auth(customer_a)

    try:
        response = client.put(
            f"/api/customer/notifications/"
            f"{other_customer_notification.id}/read"
        )
    finally:
        clear_customer_auth_override()

    assert response.status_code == 404

    db.expire_all()

    notification = (
        db.query(InAppNotification)
        .filter(
            InAppNotification.id
            == other_customer_notification.id
        )
        .first()
    )

    assert notification is not None
    assert notification.status == "UNREAD"
    assert notification.read_at is None


# ============================================================================
# 5. Read-all only affects authenticated customer's notifications
# ============================================================================


def test_customer_read_all_only_affects_own_notifications(db):
    """
    Customer A's read-all operation must affect only Customer A's
    notifications.

    Customer B's notifications must remain unread.
    """
    organization = create_organization(db)

    customer_a = create_customer(
        db,
        organization,
    )

    customer_b = create_customer(
        db,
        organization,
    )

    customer_a_notification_1 = create_notification(
        db,
        organization,
        customer_user_id=customer_a.id,
        status="UNREAD",
        title="Customer A Notification 1",
    )

    customer_a_notification_2 = create_notification(
        db,
        organization,
        customer_user_id=customer_a.id,
        status="UNREAD",
        title="Customer A Notification 2",
    )

    customer_b_notification = create_notification(
        db,
        organization,
        customer_user_id=customer_b.id,
        status="UNREAD",
        title="Customer B Notification",
    )

    override_customer_auth(customer_a)

    try:
        response = client.put(
            "/api/customer/notifications/read-all"
        )
    finally:
        clear_customer_auth_override()

    assert response.status_code == 200

    db.expire_all()

    notification_a1 = (
        db.query(InAppNotification)
        .filter(
            InAppNotification.id
            == customer_a_notification_1.id
        )
        .first()
    )

    notification_a2 = (
        db.query(InAppNotification)
        .filter(
            InAppNotification.id
            == customer_a_notification_2.id
        )
        .first()
    )

    notification_b = (
        db.query(InAppNotification)
        .filter(
            InAppNotification.id
            == customer_b_notification.id
        )
        .first()
    )

    assert notification_a1 is not None
    assert notification_a2 is not None
    assert notification_b is not None

    assert notification_a1.status == "READ"
    assert notification_a1.read_at is not None

    assert notification_a2.status == "READ"
    assert notification_a2.read_at is not None

    assert notification_b.status == "UNREAD"
    assert notification_b.read_at is None


# ============================================================================
# 6. Customer cannot mark another tenant's notification as read
# ============================================================================


def test_customer_cannot_mark_other_tenant_notification_as_read(db):
    """
    Tenant isolation must also apply when marking a notification as read.
    """
    organization_a = create_organization(
        db,
        name="Tenant A",
    )

    organization_b = create_organization(
        db,
        name="Tenant B",
    )

    customer_a = create_customer(
        db,
        organization_a,
    )

    customer_b = create_customer(
        db,
        organization_b,
    )

    other_tenant_notification = create_notification(
        db,
        organization_b,
        customer_user_id=customer_b.id,
        status="UNREAD",
        title="Other Tenant Notification",
    )

    override_customer_auth(customer_a)

    try:
        response = client.put(
            f"/api/customer/notifications/"
            f"{other_tenant_notification.id}/read"
        )
    finally:
        clear_customer_auth_override()

    assert response.status_code == 404

    db.expire_all()

    notification = (
        db.query(InAppNotification)
        .filter(
            InAppNotification.id
            == other_tenant_notification.id
        )
        .first()
    )

    assert notification is not None
    assert notification.status == "UNREAD"
    assert notification.read_at is None