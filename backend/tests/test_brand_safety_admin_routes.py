"""
Integration tests for protected brand-safety administration
routes.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import (
    Session,
    sessionmaker,
)
from sqlalchemy.pool import StaticPool

from app.database import get_db
from app.models import AIBrandSafetyRule
from app.redis_client import get_redis_client
from app.routes.brand_safety_admin import router


class FakeRedis:
    """
    Minimal Redis replacement for route integration tests.
    """

    def __init__(
        self,
    ) -> None:
        self.values: dict[str, str] = {}
        self.deleted_keys: list[str] = []

    def get(
        self,
        key: str,
    ) -> str | None:
        return self.values.get(
            key
        )

    def setex(
        self,
        key: str,
        seconds: int,
        value: str,
    ) -> bool:
        _ = seconds

        self.values[key] = value

        return True

    def delete(
        self,
        key: str,
    ) -> bool:
        self.deleted_keys.append(
            key
        )

        return (
            self.values.pop(
                key,
                None,
            )
            is not None
        )


@pytest.fixture
def db_session() -> Iterator[Session]:
    """
    Create an isolated in-memory database.
    """

    engine = create_engine(
        "sqlite://",
        connect_args={
            "check_same_thread": False,
        },
        poolclass=StaticPool,
    )

    AIBrandSafetyRule.__table__.create(
        bind=engine
    )

    testing_session = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    session = testing_session()

    try:
        yield session

    finally:
        session.close()

        AIBrandSafetyRule.__table__.drop(
            bind=engine
        )

        engine.dispose()


@pytest.fixture
def route_client(
    db_session: Session,
) -> Iterator[
    tuple[
        TestClient,
        FakeRedis,
    ]
]:
    """
    Build a small FastAPI application using real routes and
    test dependencies.
    """

    redis = FakeRedis()

    test_app = FastAPI()

    test_app.include_router(
        router
    )

    def override_get_db() -> Iterator[Session]:
        yield db_session

    def override_get_redis():
        return redis

    test_app.dependency_overrides[
        get_db
    ] = override_get_db

    test_app.dependency_overrides[
        get_redis_client
    ] = override_get_redis

    with TestClient(
        test_app
    ) as client:
        yield client, redis


def build_headers(
    *,
    tenant_id: str = "tenant-1",
    user_id: str = "admin-1",
    role: str = "tenant_admin",
) -> dict[str, str]:
    """
    Build authenticated administration headers.
    """

    return {
        "Authorization": "Bearer local-test-token",
        "X-Tenant-ID": tenant_id,
        "X-User-ID": user_id,
        "X-Permissions": role,
    }


def build_payload(
    *,
    rule_id: str = "COMPETITOR_ACME",
    pattern: str = "Acme Services",
    active: bool = True,
) -> dict:
    """
    Build a valid create request.
    """

    return {
        "rule_id": rule_id,
        "category": "COMPETITOR",
        "match_type": "PHRASE",
        "pattern": pattern,
        "severity": "ERROR",
        "active": active,
        "case_sensitive": False,
    }


def test_create_route_persists_rule_and_clears_cache(
    route_client,
) -> None:
    """
    An authorized administrator can create a rule.
    """

    client, redis = route_client

    response = client.post(
        "/api/v1/admin/ai/brand-safety-rules",
        headers=build_headers(),
        json=build_payload(),
    )

    assert response.status_code == 201

    body = response.json()

    assert body["tenant_id"] == "tenant-1"
    assert body["rule_id"] == "COMPETITOR_ACME"
    assert body["created_by"] == "admin-1"

    assert redis.deleted_keys == [
        (
            "ai:guardrails:brand-safety:v1:"
            "tenant-1"
        )
    ]


def test_duplicate_rule_returns_conflict(
    route_client,
) -> None:
    """
    Duplicate tenant rule IDs return HTTP 409.
    """

    client, _ = route_client

    first = client.post(
        "/api/v1/admin/ai/brand-safety-rules",
        headers=build_headers(),
        json=build_payload(),
    )

    second = client.post(
        "/api/v1/admin/ai/brand-safety-rules",
        headers=build_headers(),
        json=build_payload(),
    )

    assert first.status_code == 201
    assert second.status_code == 409


def test_route_requires_bearer_token(
    route_client,
) -> None:
    """
    Requests without authentication are rejected.
    """

    client, _ = route_client

    headers = build_headers()

    headers.pop(
        "Authorization"
    )

    response = client.get(
        "/api/v1/admin/ai/brand-safety-rules",
        headers=headers,
    )

    assert response.status_code in {
        401,
        403,
    }


def test_route_rejects_unauthorized_role(
    route_client,
) -> None:
    """
    Technician users cannot administer safety rules.
    """

    client, _ = route_client

    response = client.get(
        "/api/v1/admin/ai/brand-safety-rules",
        headers=build_headers(
            role="technician"
        ),
    )

    assert response.status_code == 403


def test_list_route_is_tenant_isolated(
    route_client,
) -> None:
    """
    Each tenant receives only its own stored rules.
    """

    client, _ = route_client

    client.post(
        "/api/v1/admin/ai/brand-safety-rules",
        headers=build_headers(
            tenant_id="tenant-1"
        ),
        json=build_payload(
            rule_id="TENANT_ONE_RULE",
            pattern="Tenant One Competitor",
        ),
    )

    client.post(
        "/api/v1/admin/ai/brand-safety-rules",
        headers=build_headers(
            tenant_id="tenant-2"
        ),
        json=build_payload(
            rule_id="TENANT_TWO_RULE",
            pattern="Tenant Two Competitor",
        ),
    )

    response = client.get(
        "/api/v1/admin/ai/brand-safety-rules",
        headers=build_headers(
            tenant_id="tenant-1"
        ),
    )

    assert response.status_code == 200

    body = response.json()

    assert len(body) == 1
    assert body[0]["rule_id"] == "TENANT_ONE_RULE"


def test_list_route_filters_active_rules(
    route_client,
) -> None:
    """
    Active-state query filtering works.
    """

    client, _ = route_client

    client.post(
        "/api/v1/admin/ai/brand-safety-rules",
        headers=build_headers(),
        json=build_payload(
            rule_id="ACTIVE_RULE",
            pattern="Active Competitor",
            active=True,
        ),
    )

    client.post(
        "/api/v1/admin/ai/brand-safety-rules",
        headers=build_headers(),
        json=build_payload(
            rule_id="INACTIVE_RULE",
            pattern="Inactive Competitor",
            active=False,
        ),
    )

    response = client.get(
        (
            "/api/v1/admin/ai/brand-safety-rules"
            "?active=false"
        ),
        headers=build_headers(),
    )

    assert response.status_code == 200

    body = response.json()

    assert len(body) == 1
    assert body[0]["rule_id"] == "INACTIVE_RULE"


def test_get_unknown_rule_returns_not_found(
    route_client,
) -> None:
    """
    Unknown tenant rules return HTTP 404.
    """

    client, _ = route_client

    response = client.get(
        (
            "/api/v1/admin/ai/brand-safety-rules/"
            "MISSING_RULE"
        ),
        headers=build_headers(),
    )

    assert response.status_code == 404


def test_update_route_changes_rule(
    route_client,
) -> None:
    """
    Authorized administrators can update a stored rule.
    """

    client, _ = route_client

    client.post(
        "/api/v1/admin/ai/brand-safety-rules",
        headers=build_headers(),
        json=build_payload(),
    )

    response = client.patch(
        (
            "/api/v1/admin/ai/brand-safety-rules/"
            "COMPETITOR_ACME"
        ),
        headers=build_headers(
            user_id="manager-1",
            role="manager",
        ),
        json={
            "severity": "CRITICAL",
            "pattern": "Updated Acme Group",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["severity"] == "CRITICAL"
    assert body["pattern"] == "Updated Acme Group"
    assert body["updated_by"] == "manager-1"


def test_deactivate_route_keeps_database_record(
    route_client,
) -> None:
    """
    Deactivation changes active to false without deletion.
    """

    client, _ = route_client

    client.post(
        "/api/v1/admin/ai/brand-safety-rules",
        headers=build_headers(),
        json=build_payload(),
    )

    response = client.post(
        (
            "/api/v1/admin/ai/brand-safety-rules/"
            "COMPETITOR_ACME/deactivate"
        ),
        headers=build_headers(
            user_id="manager-1",
            role="manager",
        ),
    )

    assert response.status_code == 200
    assert response.json()["active"] is False

    get_response = client.get(
        (
            "/api/v1/admin/ai/brand-safety-rules/"
            "COMPETITOR_ACME"
        ),
        headers=build_headers(),
    )

    assert get_response.status_code == 200
    assert get_response.json()["active"] is False


def test_invalid_create_payload_is_rejected(
    route_client,
) -> None:
    """
    Invalid rule identifiers fail request validation.
    """

    client, _ = route_client

    response = client.post(
        "/api/v1/admin/ai/brand-safety-rules",
        headers=build_headers(),
        json=build_payload(
            rule_id="invalid-rule-id"
        ),
    )

    assert response.status_code == 422