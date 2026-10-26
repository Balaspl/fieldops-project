from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.auth.rbac import UserRole
from app.database import get_db
from app.main import app


TENANT_ID = "tenant-fcm-test"


@pytest.fixture
def registration_context(monkeypatch):
    user_id = str(uuid.uuid4())
    technician = MagicMock()
    technician.tech_id = user_id

    state = {
        "user": AuthenticatedUser(
            user_id=user_id,
            tenant_id=TENANT_ID,
            role=UserRole.TECHNICIAN,
            jti="test-fcm-registration",
            session_id="test-session",
        ),
        "technician": technician,
    }

    db = MagicMock()
    previous_overrides = app.dependency_overrides.copy()

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    monkeypatch.setattr(
        "app.routes.notifications._get_tech_for_user",
        lambda _db, user_id_arg, tenant_id_arg: (
            state["technician"]
            if user_id_arg == state["user"].user_id
            and tenant_id_arg == state["user"].tenant_id
            else None
        ),
    )

    try:
        with TestClient(app) as client:
            yield {
                "client": client,
                "db": db,
                "state": state,
                "user_id": user_id,
            }
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)


def register_token(client, technician_id: str, tenant_id: str = TENANT_ID):
    return client.post(
        f"/technicians/{technician_id}/fcm-token",
        headers={"X-Tenant-ID": tenant_id},
        json={
            "token": "test-device-push-token",
            "device_type": "android",
        },
    )


def test_register_token_for_authenticated_technician(registration_context):
    context = registration_context
    technician = context["state"]["technician"]

    response = register_token(context["client"], context["user_id"])

    assert response.status_code == 200, response.text
    assert response.json() == {
        "status": "registered",
        "tech_id": context["user_id"],
    }
    assert technician.fcm_token == "test-device-push-token"
    assert technician.device_type == "android"
    context["db"].commit.assert_called_once()


def test_reject_token_registration_for_another_technician(registration_context):
    context = registration_context
    another_technician_id = str(uuid.uuid4())

    response = register_token(context["client"], another_technician_id)

    assert response.status_code == 403
    context["db"].commit.assert_not_called()


def test_reject_tenant_header_mismatch(registration_context):
    context = registration_context

    response = register_token(
        context["client"], context["user_id"], tenant_id="another-tenant"
    )

    assert response.status_code == 403
    context["db"].commit.assert_not_called()


def test_reject_non_technician_role(registration_context):
    context = registration_context
    context["state"]["user"] = AuthenticatedUser(
        user_id=context["user_id"],
        tenant_id=TENANT_ID,
        role=UserRole.CUSTOMER,
        jti="test-customer",
        session_id="test-session",
    )

    response = register_token(context["client"], context["user_id"])

    assert response.status_code == 403
    context["db"].commit.assert_not_called()


def test_reject_missing_authentication(registration_context):
    context = registration_context
    app.dependency_overrides.pop(get_current_user, None)

    response = register_token(context["client"], context["user_id"])

    assert response.status_code == 401
    context["db"].commit.assert_not_called()


def test_return_not_found_when_technician_does_not_exist(registration_context):
    context = registration_context
    context["state"]["technician"] = None

    response = register_token(context["client"], context["user_id"])

    assert response.status_code == 404, response.text
    context["db"].commit.assert_not_called()


def test_rollback_when_token_registration_commit_fails(registration_context):
    context = registration_context
    context["db"].commit.side_effect = RuntimeError(
        "Simulated database failure"
    )

    response = register_token(context["client"], context["user_id"])

    assert response.status_code == 500, response.text
    context["db"].rollback.assert_called_once()
