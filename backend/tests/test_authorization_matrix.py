from copy import deepcopy
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.main
from app.database import Base, get_db
from app.models_legacy import Job


# ============================================================================
# TEST DATABASE
# ============================================================================

# Import the complete legacy model module before create_all().
# This registers Job and all other legacy models with Base.metadata.
from app import models_legacy  # noqa: F401,E402


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# Create all tables used by the models.
Base.metadata.create_all(bind=engine)


# ============================================================================
# FASTAPI DATABASE OVERRIDE
# ============================================================================

@pytest.fixture(autouse=True)
def override_test_database():
    """
    Make FastAPI use the exact same SQLite database as db_session.

    Without this override:
        db_session -> test SQLite database
        FastAPI    -> application's DATABASE_URL

    That causes the test to create a Job in one database while the
    API searches for it in another database.
    """

    def _override_get_db():
        db = TestingSessionLocal()

        try:
            yield db
        finally:
            db.close()

    app.main.app.dependency_overrides[get_db] = _override_get_db

    yield

    app.main.app.dependency_overrides.pop(get_db, None)


# ============================================================================
# CONFIGURATION
# ============================================================================

JOBS_URL = "/jobs"


# ============================================================================
# TEST DATA
# ============================================================================

def valid_job_payload():
    """
    Payload accepted by JobCreate.
    """

    return {
        "customer_name": "Authorization Test Customer",
        "location": "Chennai",
        "issue_description": "Authorization matrix test",
        "priority": "HIGH",
        "service_type": "HVAC",
        "contact_number": "9876543210",
        "preferred_service_date": "2030-01-01",
        "status": "CREATED",
        "required_skill": "HVAC",
        "sla_deadline": None,
        "attempt_count": 0,
    }


# ============================================================================
# RESPONSE HELPERS
# ============================================================================

def assert_denied(response):
    """
    Authorization failures must not be successful.
    """

    assert response.status_code in {
        401,
        403,
        404,
    }


def assert_no_sensitive_job_data(response):
    """
    Do not expose protected job data when authorization fails.
    """

    assert_denied(response)

    if not response.content:
        return

    try:
        body = response.json()
    except Exception:
        return

    if isinstance(body, dict):
        forbidden_fields = {
            "customer_name",
            "contact_number",
            "issue_description",
            "site_address",
            "customer_email",
            "work_report",
        }

        leaked = forbidden_fields.intersection(body.keys())

        assert not leaked, (
            "Sensitive job fields leaked in unauthorized response: "
            f"{leaked}"
        )


# ============================================================================
# CLIENT
# ============================================================================

@pytest.fixture
def client():
    """
    FastAPI test client for authorization/integration tests.
    """

    return TestClient(app.main.app)


# ============================================================================
# AUTHENTICATION MATRIX
# ============================================================================

def test_jobs_without_token(client):
    response = client.get(JOBS_URL)

    assert response.status_code == 401


def test_job_update_without_token(client):
    response = client.put(
        f"{JOBS_URL}/999999",
        json=valid_job_payload(),
    )

    assert response.status_code == 401


def test_job_create_without_token(client):
    response = client.post(
        JOBS_URL,
        json=valid_job_payload(),
    )

    assert response.status_code == 401


def test_jobs_with_invalid_token(client):
    response = client.get(
        JOBS_URL,
        headers={
            "Authorization": "Bearer definitely-invalid-token"
        },
    )

    assert response.status_code == 401


def test_job_update_with_invalid_token(client):
    response = client.put(
        f"{JOBS_URL}/999999",
        headers={
            "Authorization": "Bearer definitely-invalid-token"
        },
        json=valid_job_payload(),
    )

    assert response.status_code == 401


# ============================================================================
# SAME-TENANT ACCESS
# ============================================================================

def test_update_job_same_tenant_allowed(
    client,
    authenticated_user,
    override_auth,
    db_session,
):
    override_auth(authenticated_user)
    user = authenticated_user

    job = Job(
        tenant_id=user.tenant_id,
        customer_tenant_id=user.tenant_id,
        customer_name="Original Customer",
        location="Chennai",
        issue_description="Original issue",
        priority="MEDIUM",
        service_type="HVAC",
        contact_number="9876543210",
        preferred_service_date=date(2030, 1, 1),
        status="CREATED",
        required_skill="HVAC",
    )

    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    original_id = job.id

    response = client.put(
        f"{JOBS_URL}/{original_id}",
        json=valid_job_payload(),
    )

    assert response.status_code in {
        200,
        201,
    }

    db_session.refresh(job)

    assert job.id == original_id
    assert job.tenant_id == user.tenant_id
    assert job.customer_name == "Authorization Test Customer"


# ============================================================================
# CROSS-TENANT ACCESS
# ============================================================================

def test_update_job_other_tenant_blocked(
    client,
    authenticated_user,
    override_auth,
    db_session,
):
    override_auth(authenticated_user)
    user = authenticated_user

    other_tenant = "different-tenant-id"

    assert str(user.tenant_id) != other_tenant

    job = Job(
        tenant_id=other_tenant,
        customer_tenant_id=other_tenant,
        customer_name="Other Tenant Customer",
        location="Secret Location",
        issue_description="Private issue",
        priority="HIGH",
        service_type="HVAC",
        contact_number="9000000000",
        preferred_service_date=date(2030, 1, 1),
        status="CREATED",
        required_skill="HVAC",
    )

    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    original_customer = job.customer_name
    original_issue = job.issue_description
    original_tenant = job.tenant_id

    response = client.put(
        f"{JOBS_URL}/{job.id}",
        json=valid_job_payload(),
    )

    assert_denied(response)

    db_session.refresh(job)

    assert job.customer_name == original_customer
    assert job.issue_description == original_issue
    assert job.tenant_id == original_tenant


def test_get_other_tenant_job_by_id_blocked(
    client,
    authenticated_user,
    override_auth,
    db_session,
):
    override_auth(authenticated_user)
    job = Job(
        tenant_id="another-tenant",
        customer_tenant_id="another-tenant",
        customer_name="PRIVATE CUSTOMER",
        location="PRIVATE LOCATION",
        issue_description="PRIVATE ISSUE",
        priority="HIGH",
        service_type="HVAC",
        contact_number="9999999999",
        preferred_service_date=date(2030, 1, 1),
        status="CREATED",
        required_skill="HVAC",
    )

    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    response = client.get(
        f"{JOBS_URL}/{job.id}",
    )

    assert_denied(response)

    assert_no_sensitive_job_data(response)


# ============================================================================
# ID TAMPERING
# ============================================================================

def test_job_id_tampering_blocked(
    client,
    authenticated_user,
    override_auth,
    db_session,
):
    override_auth(authenticated_user)
    user = authenticated_user

    own_job = Job(
        tenant_id=user.tenant_id,
        customer_tenant_id=user.tenant_id,
        customer_name="OWN CUSTOMER",
        location="Own Location",
        issue_description="Own issue",
        priority="LOW",
        service_type="HVAC",
        contact_number="9876543210",
        preferred_service_date=date(2030, 1, 1),
        status="CREATED",
        required_skill="HVAC",
    )

    foreign_job = Job(
        tenant_id="foreign-tenant",
        customer_tenant_id="foreign-tenant",
        customer_name="FOREIGN CUSTOMER",
        location="FOREIGN LOCATION",
        issue_description="FOREIGN SECRET",
        priority="CRITICAL",
        service_type="HVAC",
        contact_number="8888888888",
        preferred_service_date=date(2030, 1, 1),
        status="CREATED",
        required_skill="HVAC",
    )

    db_session.add_all([
        own_job,
        foreign_job,
    ])

    db_session.commit()

    db_session.refresh(own_job)
    db_session.refresh(foreign_job)

    response = client.put(
        f"{JOBS_URL}/{foreign_job.id}",
        json=valid_job_payload(),
    )

    assert_denied(response)

    db_session.refresh(foreign_job)

    assert foreign_job.customer_name == "FOREIGN CUSTOMER"
    assert foreign_job.location == "FOREIGN LOCATION"
    assert foreign_job.issue_description == "FOREIGN SECRET"


# ============================================================================
# NON-EXISTENT OBJECT
# ============================================================================

def test_update_nonexistent_job_blocked(client):
    response = client.put(
        f"{JOBS_URL}/999999999",
        json=valid_job_payload(),
    )

    assert_denied(response)


def test_get_nonexistent_job_blocked(client):
    response = client.get(
        f"{JOBS_URL}/999999999",
    )

    assert_denied(response)


# ============================================================================
# RBAC / ROLE PERMISSION
# ============================================================================

def test_update_job_without_edit_permission_blocked(
    client,
    authenticated_user_without_edit_permission,
    override_auth,
    db_session
):
    override_auth(authenticated_user_without_edit_permission)
    user = authenticated_user_without_edit_permission

    job = Job(
        tenant_id=user.tenant_id,
        customer_tenant_id=user.tenant_id,
        customer_name="Protected Customer",
        location="Chennai",
        issue_description="Protected issue",
        priority="HIGH",
        service_type="HVAC",
        contact_number="9876543210",
        preferred_service_date=date(2030, 1, 1),
        status="CREATED",
        required_skill="HVAC",
    )

    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    original = {
        "customer_name": job.customer_name,
        "location": job.location,
        "issue_description": job.issue_description,
        "priority": job.priority,
    }

    response = client.put(
        f"{JOBS_URL}/{job.id}",
        json=valid_job_payload(),
    )

    assert response.status_code == 403

    db_session.refresh(job)

    assert job.customer_name == original["customer_name"]
    assert job.location == original["location"]
    assert job.issue_description == original["issue_description"]
    assert job.priority == original["priority"]


# ============================================================================
# UNAUTHORIZED MUTATION / DATABASE INTEGRITY
# ============================================================================

def test_cross_tenant_update_does_not_modify_database(
    client,
    authenticated_user,
    override_auth,
    db_session
):
    
    foreign_job = Job(
        tenant_id="tenant-attacker-target",
        customer_tenant_id="tenant-attacker-target",
        customer_name="DO NOT CHANGE",
        location="DO NOT CHANGE",
        issue_description="DO NOT CHANGE",
        priority="HIGH",
        service_type="HVAC",
        contact_number="9000000000",
        preferred_service_date=date(2030, 1, 1),
        status="CREATED",
        required_skill="HVAC",
    )

    db_session.add(foreign_job)
    db_session.commit()
    db_session.refresh(foreign_job)

    before = {
        "customer_name": foreign_job.customer_name,
        "location": foreign_job.location,
        "issue_description": foreign_job.issue_description,
        "priority": foreign_job.priority,
        "tenant_id": foreign_job.tenant_id,
        "status": foreign_job.status,
    }

    response = client.put(
        f"{JOBS_URL}/{foreign_job.id}",
        json={
            **valid_job_payload(),
            "customer_name": "ATTACKER CHANGED THIS",
            "location": "ATTACKER LOCATION",
        },
    )

    assert_denied(response)

    db_session.expire_all()

    after = db_session.query(Job).filter(
        Job.id == foreign_job.id
    ).first()

    assert after is not None

    assert after.customer_name == before["customer_name"]
    assert after.location == before["location"]
    assert after.issue_description == before["issue_description"]
    assert after.priority == before["priority"]
    assert after.tenant_id == before["tenant_id"]
    assert after.status == before["status"]


# ============================================================================
# TENANT FILTERING
# ============================================================================

def test_job_list_does_not_return_other_tenant_jobs(
    client,
    authenticated_user,
    override_auth,
    db_session
):
    override_auth(authenticated_user)
    user = authenticated_user

    own_job = Job(
        tenant_id=user.tenant_id,
        customer_tenant_id=user.tenant_id,
        customer_name="OWN CUSTOMER",
        location="Own Location",
        issue_description="Own Issue",
        priority="LOW",
        service_type="HVAC",
        contact_number="9876543210",
        preferred_service_date=date(2030, 1, 1),
        status="CREATED",
        required_skill="HVAC",
    )

    foreign_job = Job(
        tenant_id="foreign-tenant",
        customer_tenant_id="foreign-tenant",
        customer_name="FOREIGN SECRET CUSTOMER",
        location="Foreign Secret Location",
        issue_description="Foreign Secret Issue",
        priority="CRITICAL",
        service_type="HVAC",
        contact_number="8888888888",
        preferred_service_date=date(2030, 1, 1),
        status="CREATED",
        required_skill="HVAC",
    )

    db_session.add_all([
        own_job,
        foreign_job,
    ])

    db_session.commit()

    response = client.get(JOBS_URL)

    assert response.status_code == 200

    data = response.json()

    if isinstance(data, list):
        returned_text = str(data)

        assert "FOREIGN SECRET CUSTOMER" not in returned_text
        assert "Foreign Secret Location" not in returned_text
        assert "Foreign Secret Issue" not in returned_text


# ============================================================================
# TENANT ID MANIPULATION
# ============================================================================

def test_request_tenant_id_cannot_override_authenticated_tenant(
    client,
    authenticated_user,
    db_session
):
    foreign_job = Job(
        tenant_id="foreign-tenant",
        customer_tenant_id="foreign-tenant",
        customer_name="FOREIGN DATA",
        location="FOREIGN DATA",
        issue_description="FOREIGN DATA",
        priority="HIGH",
        service_type="HVAC",
        contact_number="8888888888",
        preferred_service_date=date(2030, 1, 1),
        status="CREATED",
        required_skill="HVAC",
    )

    db_session.add(foreign_job)
    db_session.commit()
    db_session.refresh(foreign_job)

    response = client.get(
        f"{JOBS_URL}/{foreign_job.id}",
        headers={
            "X-Tenant-ID": "foreign-tenant",
        },
    )

    assert_denied(response)

    assert_no_sensitive_job_data(response)


# ============================================================================
# CUSTOMER / TECHNICIAN OBJECT OWNERSHIP
# ============================================================================

def test_customer_cannot_access_another_customer_job(
    client,
    authenticated_customer,
    customer_job,
    another_customer_job,
):
    response = client.get(
        f"{JOBS_URL}/{another_customer_job.id}"
    )

    assert_denied(response)

    assert_no_sensitive_job_data(response)


def test_technician_cannot_update_unassigned_job(
    client,
    authenticated_technician,
    unassigned_job,
):
    response = client.put(
        f"{JOBS_URL}/{unassigned_job.id}",
        json=valid_job_payload(),
    )

    assert_denied(response)


def test_technician_cannot_access_another_technician_job(
    client,
    authenticated_technician,
    another_technician_job,
):
    response = client.get(
        f"{JOBS_URL}/{another_technician_job.id}"
    )

    assert_denied(response)

    assert_no_sensitive_job_data(response)


# ============================================================================
# DELETE / OTHER MUTATIONS
# ============================================================================

def test_unauthorized_delete_does_not_modify_database(
    client,
    authenticated_user_without_delete_permission,
    protected_job,
    db_session
):
    job_id = protected_job.id

    before_status = protected_job.status
    before_tenant = protected_job.tenant_id

    response = client.delete(
        f"{JOBS_URL}/{job_id}"
    )

    assert response.status_code in {
        403,
        404,
        405,
    }

    db_session.expire_all()

    after = db_session.query(Job).filter(
        Job.id == job_id
    ).first()

    if after is not None:
        assert after.status == before_status
        assert after.tenant_id == before_tenant


# ============================================================================
# PRIVILEGE ESCALATION
# ============================================================================

def test_user_cannot_change_job_tenant_during_update(
    client,
    authenticated_user,
    override_auth,
    db_session
):
    override_auth(authenticated_user)
    user = authenticated_user

    job = Job(
        tenant_id=user.tenant_id,
        customer_tenant_id=user.tenant_id,
        customer_name="Original",
        location="Original",
        issue_description="Original",
        priority="LOW",
        service_type="HVAC",
        contact_number="9876543210",
        preferred_service_date=date(2030, 1, 1),
        status="CREATED",
        required_skill="HVAC",
    )

    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    payload = {
        **valid_job_payload(),
        "tenant_id": "ATTACKER_CONTROLLED_TENANT",
        "customer_tenant_id": "ATTACKER_CONTROLLED_TENANT",
    }

    response = client.put(
        f"{JOBS_URL}/{job.id}",
        json=payload,
    )

    if response.status_code in {200, 201}:
        db_session.refresh(job)

        assert str(job.tenant_id) == str(
            user.tenant_id
        )
    else:
        assert_denied(response)


# ============================================================================
# REGRESSION / OBJECT EXISTENCE
# ============================================================================

def test_same_tenant_nonexistent_job_does_not_create_object(
    client,
    authenticated_user,
    db_session
):
    before_count = db_session.query(Job).count()

    response = client.put(
        f"{JOBS_URL}/999999999",
        json=valid_job_payload(),
    )

    assert_denied(response)

    after_count = db_session.query(Job).count()

    assert after_count == before_count