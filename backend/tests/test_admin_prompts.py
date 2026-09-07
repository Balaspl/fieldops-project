from __future__ import annotations

from datetime import (
    datetime,
    timedelta,
    timezone,
)
from typing import Any

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import get_db
from app.main import app
from app.models import Base, NotificationTemplate, TemplateVersion
from app.redis_client import get_redis_client
from app.services.ai.FieldOpsAI.repositories.prompt_template_repository import (
    PromptTemplateRepository,
    RepositoryError,
)


# ==========================================================
# Test configuration
# ==========================================================


TEST_JWT_SECRET = "test-jwt-secret"
TEST_JWT_ALGORITHM = "HS256"


# ==========================================================
# Test database
# ==========================================================


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={
        "check_same_thread": False,
    },
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


# ==========================================================
# Fake Redis
# ==========================================================


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, Any] = {}
        self.expires: dict[str, int] = {}
        self.deleted_keys: list[str] = []

    def get(
        self,
        key: str,
    ) -> Any:
        return self.data.get(key)

    def setex(
        self,
        key: str,
        ttl: int,
        value: Any,
    ) -> bool:
        self.data[key] = value
        self.expires[key] = ttl
        return True

    def incr(
        self,
        key: str,
        amount: int = 1,
    ) -> int:
        current = int(
            self.data.get(
                key,
                0,
            )
        )

        updated = current + amount
        self.data[key] = updated

        return updated

    def delete(
        self,
        key: str,
    ) -> int:
        self.deleted_keys.append(key)
        self.data.pop(key, None)
        self.expires.pop(key, None)
        return 1

    def reset(self) -> None:
        self.data.clear()
        self.expires.clear()
        self.deleted_keys.clear()


fake_redis = FakeRedis()


# ==========================================================
# Fixtures
# ==========================================================


@pytest.fixture
def api_client(
    monkeypatch: pytest.MonkeyPatch,
):
    """
    Create one isolated API client per test.

    Each test receives:

    - A fresh SQLite schema
    - A clean Redis fake
    - A configured JWT secret
    - Fresh FastAPI dependency overrides
    """

    monkeypatch.setenv(
        "JWT_SECRET",
        TEST_JWT_SECRET,
    )

    monkeypatch.setenv(
        "JWT_ALGORITHM",
        TEST_JWT_ALGORITHM,
    )

    app.dependency_overrides.clear()

    Base.metadata.drop_all(
        bind=engine
    )

    Base.metadata.create_all(
        bind=engine
    )

    fake_redis.reset()

    def override_get_db():
        db: Session = TestingSessionLocal()

        try:
            yield db
        finally:
            db.close()

    def override_get_redis_client():
        return fake_redis

    app.dependency_overrides[
        get_db
    ] = override_get_db

    app.dependency_overrides[
        get_redis_client
    ] = override_get_redis_client

    client = TestClient(app)

    try:
        yield client
    finally:
        client.close()

        app.dependency_overrides.clear()

        Base.metadata.drop_all(
            bind=engine
        )

        fake_redis.reset()


# ==========================================================
# JWT helpers
# ==========================================================


def create_test_jwt(
    *,
    tenant_id: str = "tenant_1",
    user_id: str = "user_1",
    roles: Any = None,
    expires_in_minutes: int = 15,
    secret: str = TEST_JWT_SECRET,
    include_tenant: bool = True,
    include_user: bool = True,
    include_roles: bool = True,
) -> str:
    """
    Create a real signed JWT accepted by the production
    prompt-admin dependency.
    """

    if roles is None:
        roles = ["admin"]

    payload: dict[str, Any] = {
        "exp": (
            datetime.now(timezone.utc)
            + timedelta(
                minutes=expires_in_minutes
            )
        ),
    }

    if include_tenant:
        payload["tenant_id"] = tenant_id

    if include_user:
        payload["sub"] = user_id

    if include_roles:
        payload["roles"] = roles

    return jwt.encode(
        payload,
        secret,
        algorithm=TEST_JWT_ALGORITHM,
    )


def get_headers(
    *,
    role: str = "admin",
    roles: Any = None,
    tenant: str = "tenant_1",
    user_id: str = "user_1",
    include_consistency_headers: bool = True,
) -> dict[str, str]:
    if roles is None:
        roles = [role]

    token = create_test_jwt(
        tenant_id=tenant,
        user_id=user_id,
        roles=roles,
    )

    headers = {
        "Authorization": (
            f"Bearer {token}"
        ),
    }

    if include_consistency_headers:
        headers["X-Tenant-ID"] = tenant
        headers["X-User-ID"] = user_id

    return headers


def prompt_payload(
    *,
    name: str = "Test Prompt",
    prompt_status: str = "default",
    body: str = "Hello {{ name }}",
    variables: list[str] | None = None,
    agent_type: str = "CommsAgent",
    channel: str = "sms",
    language: str = "en",
    format_value: str = "text",
) -> dict[str, Any]:
    from app.services.ai.FieldOpsAI.schemas.prompt_template import (
        normalize_template_status,
        UnsupportedTemplateStatusError,
    )
    try:
        norm = normalize_template_status(prompt_status, allow_default=True)
        status_val = norm.value if hasattr(norm, "value") else str(norm)
    except UnsupportedTemplateStatusError:
        if prompt_status in {"closed", "active", "pending", "new", "open", "in_progress", "invalid_status_xyz", "random_status", "foo_bar", "   ", ""}:
            status_val = prompt_status
        else:
            status_val = "default"

    if variables is None:
        variables = ["name"]

    payload: dict[str, Any] = {
        "name": name,
        "agent_type": agent_type,
        "channel": channel,
        "language": language,
        "status": status_val,
        "body": body,
        "variables": variables,
        "format": format_value,
    }

    return payload


# ==========================================================
# Authentication tests
# ==========================================================


def test_authentication_is_required(
    api_client: TestClient,
) -> None:
    response = api_client.get(
        "/admin/prompts"
    )

    # HTTPBearer may use either 401 or 403 depending on
    # the installed FastAPI/Starlette version.
    assert response.status_code in {
        401,
        403,
    }


def test_invalid_signature_returns_401(
    api_client: TestClient,
) -> None:
    token = create_test_jwt(
        secret="wrong-secret",
    )

    response = api_client.get(
        "/admin/prompts",
        headers={
            "Authorization": (
                f"Bearer {token}"
            ),
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == (
        "Invalid token."
    )


def test_expired_token_returns_401(
    api_client: TestClient,
) -> None:
    token = create_test_jwt(
        expires_in_minutes=-1,
    )

    response = api_client.get(
        "/admin/prompts",
        headers={
            "Authorization": (
                f"Bearer {token}"
            ),
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == (
        "Token has expired."
    )


def test_missing_jwt_secret_fails_closed(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(
        "JWT_SECRET",
        raising=False,
    )

    token = create_test_jwt()

    response = api_client.get(
        "/admin/prompts",
        headers={
            "Authorization": (
                f"Bearer {token}"
            ),
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Authentication service unavailable."
    )


def test_forbidden_role_returns_403(
    api_client: TestClient,
) -> None:
    response = api_client.get(
        "/admin/prompts",
        headers=get_headers(
            role="technician"
        ),
    )

    assert response.status_code == 403


def test_roles_string_is_supported(
    api_client: TestClient,
) -> None:
    token = create_test_jwt(
        roles="admin",
    )

    response = api_client.get(
        "/admin/prompts",
        headers={
            "Authorization": (
                f"Bearer {token}"
            ),
        },
    )

    assert response.status_code == 200


def test_comma_separated_roles_string_is_supported(
    api_client: TestClient,
) -> None:
    token = create_test_jwt(
        roles="manager,admin",
    )

    response = api_client.get(
        "/admin/prompts",
        headers={
            "Authorization": (
                f"Bearer {token}"
            ),
        },
    )

    assert response.status_code == 200


def test_roles_list_is_supported(
    api_client: TestClient,
) -> None:
    response = api_client.get(
        "/admin/prompts",
        headers=get_headers(
            roles=[
                "manager",
                "admin",
            ]
        ),
    )

    assert response.status_code == 200


def test_missing_tenant_claim_returns_403(
    api_client: TestClient,
) -> None:
    token = create_test_jwt(
        include_tenant=False,
    )

    response = api_client.get(
        "/admin/prompts",
        headers={
            "Authorization": (
                f"Bearer {token}"
            ),
        },
    )

    assert response.status_code == 403


def test_missing_user_claim_returns_403(
    api_client: TestClient,
) -> None:
    token = create_test_jwt(
        include_user=False,
    )

    response = api_client.get(
        "/admin/prompts",
        headers={
            "Authorization": (
                f"Bearer {token}"
            ),
        },
    )

    assert response.status_code == 403


def test_missing_roles_claim_returns_403(
    api_client: TestClient,
) -> None:
    token = create_test_jwt(
        include_roles=False,
    )

    response = api_client.get(
        "/admin/prompts",
        headers={
            "Authorization": (
                f"Bearer {token}"
            ),
        },
    )

    assert response.status_code == 403


def test_tenant_header_mismatch_returns_403(
    api_client: TestClient,
) -> None:
    token = create_test_jwt(
        tenant_id="tenant_1",
    )

    response = api_client.get(
        "/admin/prompts",
        headers={
            "Authorization": (
                f"Bearer {token}"
            ),
            "X-Tenant-ID": "tenant_2",
        },
    )

    assert response.status_code == 403


def test_user_header_mismatch_returns_403(
    api_client: TestClient,
) -> None:
    token = create_test_jwt(
        user_id="user_1",
    )

    response = api_client.get(
        "/admin/prompts",
        headers={
            "Authorization": (
                f"Bearer {token}"
            ),
            "X-User-ID": "user_2",
        },
    )

    assert response.status_code == 403


def test_permission_header_cannot_add_role(
    api_client: TestClient,
) -> None:
    token = create_test_jwt(
        roles=["admin"],
    )

    response = api_client.get(
        "/admin/prompts",
        headers={
            "Authorization": (
                f"Bearer {token}"
            ),
            "X-Permissions": (
                "admin,super_admin"
            ),
        },
    )

    assert response.status_code == 403


def test_platform_requires_super_admin(
    api_client: TestClient,
) -> None:
    response = api_client.get(
        "/admin/prompts",
        headers=get_headers(
            tenant="**platform**",
            roles=["admin"],
        ),
    )

    assert response.status_code == 403


def test_platform_accepts_multiple_roles_with_super_admin(
    api_client: TestClient,
) -> None:
    response = api_client.get(
        "/admin/prompts",
        headers=get_headers(
            tenant="**platform**",
            roles=[
                "admin",
                "super_admin",
            ],
        ),
    )

    assert response.status_code == 200


# ==========================================================
# CRUD API tests
# ==========================================================


def test_post_works(
    api_client: TestClient,
) -> None:
    response = api_client.post(
        "/admin/prompts",
        json=prompt_payload(),
        headers=get_headers(),
    )

    assert response.status_code == 201

    result = response.json()

    assert result["name"] == "Test Prompt"
    assert result["agent_type"] == "CommsAgent"
    assert result["channel"] == "sms"
    assert result["language"] == "en"
    assert result["status"] == "default"


def test_post_whitespace_preserved(
    api_client: TestClient,
) -> None:
    body_with_spaces = "  Hello \n  "
    response = api_client.post(
        "/admin/prompts",
        json=prompt_payload(
            name="  spaced name  ",
            prompt_status=" ASSIGNED ",
            body=body_with_spaces,
            variables=[]
        ),
        headers=get_headers(),
    )

    assert response.status_code == 201

    result = response.json()

    assert result["name"] == "spaced name"
    assert result["status"] == "assigned"
    assert result["body"] == body_with_spaces


def test_get_collection(
    api_client: TestClient,
) -> None:
    create_response = api_client.post(
        "/admin/prompts",
        json=prompt_payload(
            prompt_status="collection",
            body="Collection prompt",
            variables=[],
        ),
        headers=get_headers(),
    )

    assert create_response.status_code == 201

    response = api_client.get(
        "/admin/prompts",
        params={
            "channel": "sms",
        },
        headers=get_headers(),
    )

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_get_lookup(
    api_client: TestClient,
) -> None:
    create_response = api_client.post(
        "/admin/prompts",
        json=prompt_payload(
            prompt_status="assigned",
            agent_type="CommsAgent",
            body="Lookup prompt",
            variables=[],
        ),
        headers=get_headers(),
    )

    assert create_response.status_code == 201

    response = api_client.get(
        "/admin/prompts/lookup",
        params={
            "agent_type": "CommsAgent",
            "channel": "sms",
            "language": "en",
            "status": "assigned",
        },
        headers=get_headers(),
    )

    assert response.status_code == 200
    assert response.json()["source"] == "tenant"
    assert response.json()["body"] == "Lookup prompt"


def test_get_by_id(
    api_client: TestClient,
) -> None:
    create_response = api_client.post(
        "/admin/prompts",
        json=prompt_payload(
            prompt_status="get_by_id",
            body="Get by ID",
            variables=[],
        ),
        headers=get_headers(),
    )

    assert create_response.status_code == 201

    template_id = create_response.json()["id"]

    response = api_client.get(
        f"/admin/prompts/{template_id}",
        headers=get_headers(),
    )

    assert response.status_code == 200
    assert response.json()["id"] == template_id


def test_patch_works(
    api_client: TestClient,
) -> None:
    create_response = api_client.post(
        "/admin/prompts",
        json=prompt_payload(
            prompt_status="patch",
            body="Original",
            variables=[],
        ),
        headers=get_headers(),
    )

    assert create_response.status_code == 201

    template_id = create_response.json()["id"]

    response = api_client.patch(
        f"/admin/prompts/{template_id}",
        json={
            "name": "Updated",
        },
        headers=get_headers(),
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Updated"


def test_patch_agent_channel_and_language(
    api_client: TestClient,
) -> None:
    # Create English template first
    api_client.post(
        "/admin/prompts",
        json=prompt_payload(
            prompt_status="patch_lookup_fields",
            body="Original",
            variables=[],
            language="en"
        ),
        headers=get_headers(),
    )
    create_response = api_client.post(
        "/admin/prompts",
        json=prompt_payload(
            prompt_status="patch_lookup_fields",
            body="Original",
            variables=[],
            language="es"
        ),
        headers=get_headers(),
    )

    assert create_response.status_code == 201

    template_id = create_response.json()["id"]

    # Create the en sibling for SentimentAgent/email
    api_client.post(
        "/admin/prompts",
        json=prompt_payload(
            agent_type="SentimentAgent",
            channel="email",
            language="en",
            prompt_status="patch_lookup_fields",
            body="Original",
            variables=[],
        ),
        headers=get_headers(),
    )
    response = api_client.patch(
        f"/admin/prompts/{template_id}",
        json={
            "agent_type": "SentimentAgent",
            "channel": "email",
            "language": "ta",
        },
        headers=get_headers(),
    )

    assert response.status_code == 200

    result = response.json()

    assert result["agent_type"] == (
        "SentimentAgent"
    )

    assert result["channel"] == "email"
    assert result["language"] == "ta"


def test_delete_soft_deactivates_template(
    api_client: TestClient,
) -> None:
    create_response = api_client.post(
        "/admin/prompts",
        json=prompt_payload(
            prompt_status="delete",
            body="Delete test",
            variables=[],
        ),
        headers=get_headers(),
    )

    assert create_response.status_code == 201

    template_id = create_response.json()["id"]

    delete_response = api_client.delete(
        f"/admin/prompts/{template_id}",
        headers=get_headers(),
    )

    assert delete_response.status_code == 204

    get_response = api_client.get(
        f"/admin/prompts/{template_id}",
        headers=get_headers(),
    )

    assert get_response.status_code == 404
    assert get_response.json()["detail"] == "Template not found."


def test_cross_tenant_access_returns_404(
    api_client: TestClient,
) -> None:
    create_response = api_client.post(
        "/admin/prompts",
        json=prompt_payload(
            prompt_status="cross_tenant",
            body="Tenant one",
            variables=[],
        ),
        headers=get_headers(
            tenant="tenant_1"
        ),
    )

    assert create_response.status_code == 201

    template_id = create_response.json()["id"]

    response = api_client.get(
        f"/admin/prompts/{template_id}",
        headers=get_headers(
            tenant="tenant_2"
        ),
    )

    assert response.status_code == 404


# ==========================================================
# Validation and error tests
# ==========================================================


def test_invalid_name_returns_400(
    api_client: TestClient,
) -> None:
    payload = prompt_payload()
    payload["name"] = ""

    response = api_client.post(
        "/admin/prompts",
        json=payload,
        headers=get_headers(),
    )

    assert response.status_code == 400


def test_undeclared_variable_returns_400(
    api_client: TestClient,
) -> None:
    payload = prompt_payload(
        prompt_status="invalid_variables",
        body="{{ secret_value }}",
        variables=[],
    )

    response = api_client.post(
        "/admin/prompts",
        json=payload,
        headers=get_headers(),
    )

    assert response.status_code == 400

    # The raw prompt body must not be returned.
    assert "{{ secret_value }}" not in (
        response.text
    )


def test_invalid_lookup_enum_returns_400(
    api_client: TestClient,
) -> None:
    response = api_client.get(
        "/admin/prompts/lookup",
        params={
            "agent_type": "UnknownAgent",
            "channel": "sms",
            "language": "en",
            "status": "assigned",
        },
        headers=get_headers(),
    )

    assert response.status_code == 400


def test_persistence_error_returns_503(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_repository_error(
        *args,
        **kwargs,
    ):
        raise RepositoryError(
            "Sensitive database information"
        )

    monkeypatch.setattr(
        PromptTemplateRepository,
        "create",
        raise_repository_error,
    )

    response = api_client.post(
        "/admin/prompts",
        json=prompt_payload(
            prompt_status="persistence_error",
            body="Persistence",
            variables=[],
        ),
        headers=get_headers(),
    )

    assert response.status_code == 503

    assert (
        "Sensitive database information"
        not in response.text
    )


def test_platform_completeness_super_admin(api_client):
    headers = get_headers(tenant="**platform**", role="super_admin")
    resp = api_client.get(
        "/admin/prompts/translations/completeness",
        headers=headers,
    )
    assert resp.status_code == 200


def test_tenant_cannot_select_platform_completeness(
    api_client,
):
    response = api_client.get(
        (
            "/admin/prompts/"
            "translations/completeness"
            "?tenant_id=**platform**"
        ),
        headers=get_headers(
            tenant="tenant_1",
            role="admin",
        ),
    )

    # The unknown query parameter must not change
    # the authenticated tenant scope.
    assert response.status_code == 200

    data = response.json()

    # This clean test has no tenant_1 families.
    # It must not return platform families.
    assert data["total_families"] == 0
    assert data["items"] == []


# ==========================================================
# Story 8.1 HTTP Contract & Mutation Safety Tests (§6)
# ==========================================================


def test_http_post_with_client_version_returns_400(
    api_client: TestClient,
) -> None:
    """
    POST /admin/prompts including a version field must return HTTP 400,
    creating no database prompt row or version history row.
    """
    payload = prompt_payload(prompt_status="http_version_test")
    payload["version"] = 99

    response = api_client.post(
        "/admin/prompts",
        json=payload,
        headers=get_headers(),
    )

    assert response.status_code == 400

    # Verify no template row created
    list_resp = api_client.get(
        "/admin/prompts",
        params={"status": payload["status"]},
        headers=get_headers(),
    )
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 0


def test_http_patch_whitespace_only_name_returns_400(
    api_client: TestClient,
) -> None:
    """
    PATCH /admin/prompts/{id} with whitespace-only name returns HTTP 400.
    Live row name, version, and TemplateVersion count remain unchanged.
    """
    create_resp = api_client.post(
        "/admin/prompts",
        json=prompt_payload(name="Original Name", prompt_status="ws_patch_http"),
        headers=get_headers(),
    )
    assert create_resp.status_code == 201
    prompt_id = create_resp.json()["id"]

    db_session = TestingSessionLocal()
    try:
        versions_before = (
            db_session.query(TemplateVersion)
            .filter(TemplateVersion.template_id == prompt_id)
            .count()
        )
    finally:
        db_session.close()

    patch_resp = api_client.patch(
        f"/admin/prompts/{prompt_id}",
        json={"name": "   "},
        headers=get_headers(),
    )
    assert patch_resp.status_code == 400

    # Verify live row & version count unchanged
    get_resp = api_client.get(
        f"/admin/prompts/{prompt_id}",
        headers=get_headers(),
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "Original Name"
    assert get_resp.json()["version"] == 1

    db_session = TestingSessionLocal()
    try:
        versions_after = (
            db_session.query(TemplateVersion)
            .filter(TemplateVersion.template_id == prompt_id)
            .count()
        )
    finally:
        db_session.close()
    assert versions_after == versions_before


def test_http_post_unsupported_format_returns_400(
    api_client: TestClient,
) -> None:
    """
    POST /admin/prompts with unsupported format returns HTTP 400 and causes no DB mutation.
    """
    payload = prompt_payload(prompt_status="unsupported_fmt_post")
    payload["format"] = "markdown"

    response = api_client.post(
        "/admin/prompts",
        json=payload,
        headers=get_headers(),
    )
    assert response.status_code == 400

    list_resp = api_client.get(
        "/admin/prompts",
        params={"status": payload["status"]},
        headers=get_headers(),
    )
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 0


def test_http_patch_unsupported_format_returns_400(
    api_client: TestClient,
) -> None:
    """
    PATCH /admin/prompts/{id} with unsupported format returns HTTP 400.
    Live row format, version, and TemplateVersion count remain unchanged.
    """
    create_resp = api_client.post(
        "/admin/prompts",
        json=prompt_payload(prompt_status="unsupported_fmt_patch"),
        headers=get_headers(),
    )
    assert create_resp.status_code == 201
    prompt_id = create_resp.json()["id"]

    db_session = TestingSessionLocal()
    try:
        versions_before = (
            db_session.query(TemplateVersion)
            .filter(TemplateVersion.template_id == prompt_id)
            .count()
        )
    finally:
        db_session.close()

    patch_resp = api_client.patch(
        f"/admin/prompts/{prompt_id}",
        json={"format": "xml"},
        headers=get_headers(),
    )
    assert patch_resp.status_code == 400

    get_resp = api_client.get(
        f"/admin/prompts/{prompt_id}",
        headers=get_headers(),
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["format"] == "text"
    assert get_resp.json()["version"] == 1

    db_session = TestingSessionLocal()
    try:
        versions_after = (
            db_session.query(TemplateVersion)
            .filter(TemplateVersion.template_id == prompt_id)
            .count()
        )
    finally:
        db_session.close()
    assert versions_after == versions_before


def test_http_patch_invalid_source_returns_400(
    api_client: TestClient,
) -> None:
    """
    PATCH /admin/prompts/{id} with invalid Jinja body returns HTTP 400.
    Live row body, version, and TemplateVersion count remain unchanged.
    """
    create_resp = api_client.post(
        "/admin/prompts",
        json=prompt_payload(prompt_status="invalid_source_patch"),
        headers=get_headers(),
    )
    assert create_resp.status_code == 201
    prompt_id = create_resp.json()["id"]

    db_session = TestingSessionLocal()
    try:
        versions_before = (
            db_session.query(TemplateVersion)
            .filter(TemplateVersion.template_id == prompt_id)
            .count()
        )
    finally:
        db_session.close()

    patch_resp = api_client.patch(
        f"/admin/prompts/{prompt_id}",
        json={"body": "{% if %}"},
        headers=get_headers(),
    )
    assert patch_resp.status_code == 400

    get_resp = api_client.get(
        f"/admin/prompts/{prompt_id}",
        headers=get_headers(),
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["body"] == "Hello {{ name }}"
    assert get_resp.json()["version"] == 1

    db_session = TestingSessionLocal()
    try:
        versions_after = (
            db_session.query(TemplateVersion)
            .filter(TemplateVersion.template_id == prompt_id)
            .count()
        )
    finally:
        db_session.close()
    assert versions_after == versions_before


def test_http_patch_text_to_html_succeeds(
    api_client: TestClient,
) -> None:
    """
    PATCH /admin/prompts/{id} from text to html succeeds (HTTP 200).
    Live format becomes html, version is incremented once, and new TemplateVersion snapshot is created with html format.
    """
    create_resp = api_client.post(
        "/admin/prompts",
        json=prompt_payload(prompt_status="patch_text_html", channel="email"),
        headers=get_headers(),
    )
    assert create_resp.status_code == 201
    prompt_id = create_resp.json()["id"]
    assert create_resp.json()["format"] == "text"

    db_session = TestingSessionLocal()
    try:
        versions_before = (
            db_session.query(TemplateVersion)
            .filter(TemplateVersion.template_id == prompt_id)
            .count()
        )
    finally:
        db_session.close()

    patch_resp = api_client.patch(
        f"/admin/prompts/{prompt_id}",
        json={"format": "html"},
        headers=get_headers(),
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["format"] == "html"
    assert patch_resp.json()["version"] == 2

    db_session = TestingSessionLocal()
    try:
        versions_after = (
            db_session.query(TemplateVersion)
            .filter(TemplateVersion.template_id == prompt_id)
            .count()
        )
        latest_version = (
            db_session.query(TemplateVersion)
            .filter(TemplateVersion.template_id == prompt_id)
            .order_by(TemplateVersion.version_number.desc())
            .first()
        )
        assert latest_version is not None
        assert latest_version.format == "html"
    finally:
        db_session.close()
    assert versions_after == versions_before + 1


def test_sanitized_exceptions_do_not_leak_sensitive_markers(
    api_client: TestClient,
    capsys,
) -> None:
    """
    Ensures sensitive error markers do not leak to HTTP responses, stdout, or stderr.
    """
    SENSITIVE_MARKER = "SENSITIVE_SECRET_MARKER_999"

    # Injecting invalid syntax body
    payload = prompt_payload(
        prompt_status="sensitive_leak_test",
        body=f"Hello {{{{ {SENSITIVE_MARKER} | invalid_filter }}}}",
    )

    response = api_client.post(
        "/admin/prompts",
        json=payload,
        headers=get_headers(),
    )

    captured = capsys.readouterr()

    assert SENSITIVE_MARKER not in response.text
    assert SENSITIVE_MARKER not in captured.out
    assert SENSITIVE_MARKER not in captured.err

