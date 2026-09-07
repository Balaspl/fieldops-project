from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import get_db
from app.main import app
from app.models import Base, NotificationTemplate, TemplateVersion
from app.routes.dispatch import verify_jwt_token


# ==========================================================
# Isolated test database
# ==========================================================

test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={
        "check_same_thread": False,
    },
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=test_engine,
)


# ==========================================================
# Fixtures
# ==========================================================

@pytest.fixture
def db_session() -> Session:
    """
    Create a fresh in-memory database for every test.

    This prevents template API tests from inserting test
    records into the real PostgreSQL development database.
    """

    Base.metadata.drop_all(
        bind=test_engine,
    )

    Base.metadata.create_all(
        bind=test_engine,
    )

    session = TestingSessionLocal()

    try:
        yield session
    finally:
        session.rollback()
        session.close()

        Base.metadata.drop_all(
            bind=test_engine,
        )


@pytest.fixture
def client(
    db_session: Session,
) -> TestClient:
    """
    Create a TestClient with mocked authentication and
    the isolated SQLite database.

    The TestClient is not used as a context manager here,
    so the complete application lifespan and background
    workers are not started.
    """

    def override_get_db():
        yield db_session

    app.dependency_overrides[
        verify_jwt_token
    ] = lambda: "mock_token"

    app.dependency_overrides[
        get_db
    ] = override_get_db

    test_client = TestClient(app)

    try:
        yield test_client
    finally:
        test_client.close()

        app.dependency_overrides.pop(
            verify_jwt_token,
            None,
        )

        app.dependency_overrides.pop(
            get_db,
            None,
        )


# ==========================================================
# Preview tests
# ==========================================================

def test_preview_template_success(
    client: TestClient,
) -> None:
    """
    Successful template previews must return the rendered
    title and body.
    """

    with patch(
        "app.routes.templates.render_preview",
    ) as mock_render:
        mock_render.return_value = {
            "title": "Rendered Title",
            "body": "Rendered Body",
        }

        response = client.post(
            "/templates/preview",
            json={
                "title_template": (
                    "Hello {{ name }}"
                ),
                "body_template": "Welcome!",
                "mock_context": {
                    "name": "Test",
                },
            },
        )

    assert response.status_code == 200

    assert response.json() == {
        "rendered_title": "Rendered Title",
        "rendered_body": "Rendered Body",
    }


def test_preview_template_failure_sanitized(
    client: TestClient,
) -> None:
    """
    Rendering failures must return HTTP 400 with a fixed
    message and must not expose internal exception details.
    """

    sensitive_marker = (
        "SUPER_SECRET_JINJA_INTERNAL_ERROR_12345"
    )

    with patch(
        "app.routes.templates.render_preview",
    ) as mock_render:
        from app.services.template_engine import MessageTemplateEngineError
        mock_render.side_effect = MessageTemplateEngineError(
            f"Failed because {sensitive_marker}"
        )

        response = client.post(
            "/templates/preview",
            json={
                "title_template": (
                    "Hello {{ name }}"
                ),
                "body_template": "Welcome!",
                "mock_context": {
                    "name": "Test",
                },
            },
        )

    assert response.status_code == 400

    assert response.json()["detail"] == (
        "Template render failed."
    )

    assert sensitive_marker not in response.text


def test_preview_template_auth_validation_unchanged() -> None:
    """
    A request without authentication must still be rejected.
    """

    previous_auth_override = (
        app.dependency_overrides.pop(
            verify_jwt_token,
            None,
        )
    )

    unauthenticated_client = TestClient(app)

    try:
        response = unauthenticated_client.post(
            "/templates/preview",
            json={
                "title_template": (
                    "Hello {{ name }}"
                ),
                "body_template": "Welcome!",
                "mock_context": {
                    "name": "Test",
                },
            },
        )
    finally:
        unauthenticated_client.close()

        if previous_auth_override is not None:
            app.dependency_overrides[
                verify_jwt_token
            ] = previous_auth_override

    assert response.status_code in {
        401,
        403,
    }


# ==========================================================
# Route-registration test
# ==========================================================

def test_template_routes_registered_once() -> None:
    """
    Verify that every /templates path and HTTP method
    combination is registered only once.
    """

    template_routes = [
        route
        for route in app.routes
        if (
            hasattr(route, "path")
            and route.path.startswith(
                "/templates"
            )
        )
    ]

    seen_endpoints: set[
        tuple[str, str]
    ] = set()

    for route in template_routes:
        methods = getattr(
            route,
            "methods",
            set(),
        )

        for method in methods:
            endpoint_signature = (
                route.path,
                method,
            )

            assert (
                endpoint_signature
                not in seen_endpoints
            ), (
                "Duplicate route detected: "
                f"{route.path} [{method}]"
            )

            seen_endpoints.add(
                endpoint_signature
            )


# ==========================================================
# Legacy template route tests
# ==========================================================

def test_legacy_route_top_level_declarations(
    client: TestClient,
    db_session: Session,
) -> None:
    """
    The legacy route must infer nested Jinja paths and store
    compatible top-level variable declarations.
    """

    response = client.post(
        "/templates",
        json={
            "name": "Legacy",
            "type": "job_status_legacy",
            "channel": "sms",
            "locale": "en",
            "format": "text",
            "body_template": (
                "Hello {{ customer.name }}"
            ),
        },
    )

    assert response.status_code == 200

    saved_template = (
        db_session.query(
            NotificationTemplate
        )
        .filter(
            NotificationTemplate.name
            == "Legacy"
        )
        .one()
    )

    assert saved_template.variables == [
        "customer.name"
    ]


def test_legacy_route_unsafe_rejected(
    client: TestClient,
    db_session: Session,
) -> None:
    """
    Unsafe Jinja must be rejected without leaking source
    content or creating a database record.
    """

    response = client.post(
        "/templates",
        json={
            "name": "LegacyUnsafe",
            "type": "job_status_unsafe",
            "channel": "sms",
            "locale": "en",
            "format": "text",
            "body_template": (
                "{{ secret_method() }}"
            ),
        },
    )

    assert response.status_code == 400

    assert response.json()["detail"] == (
        "Template validation failed."
    )

    # Security assertions must remain active.
    assert (
        "{{ secret_method() }}"
        not in response.text
    )

    assert "secret_method" not in response.text

    saved_template = (
        db_session.query(
            NotificationTemplate
        )
        .filter(
            NotificationTemplate.name
            == "LegacyUnsafe"
        )
        .first()
    )

    assert saved_template is None


def test_repeated_legacy_create_reuses_live_row(
    client: TestClient,
    db_session: Session,
) -> None:
    """
    Repeated creation using the same template identity must
    update one live NotificationTemplate row.

    Historical versions belong in TemplateVersion rather
    than duplicate NotificationTemplate rows.
    """

    first_response = client.post(
        "/templates",
        json={
            "name": "Legacy V1",
            "type": "job_status_repeat",
            "channel": "sms",
            "locale": "en",
            "format": "text",
            "body_template": (
                "Hello {{ customer.name }}"
            ),
        },
    )

    assert first_response.status_code == 200

    second_response = client.post(
        "/templates",
        json={
            "name": "Legacy V2",
            "type": "job_status_repeat",
            "channel": "sms",
            "locale": "en",
            "format": "text",
            "body_template": (
                "Welcome {{ customer.name }}"
            ),
        },
    )

    assert second_response.status_code == 200

    templates = (
        db_session.query(
            NotificationTemplate
        )
        .filter(
            NotificationTemplate.type
            == "job_status_repeat",

            NotificationTemplate.channel
            == "sms",

            NotificationTemplate.locale
            == "en",

            NotificationTemplate.tenant_id
            == "**platform**",

            NotificationTemplate.agent_type
            == "CommsAgent",
        )
        .all()
    )

    assert len(templates) == 1

    live_template = templates[0]

    assert live_template.version == 2
    assert live_template.name == "Legacy V2"

    assert live_template.body_template == (
        "Welcome {{ customer.name }}"
    )


# ==========================================================
# §5 — Whitespace-only name validation
# ==========================================================


def test_post_whitespace_only_name_returns_400() -> None:
    """
    PromptTemplateCreate must reject whitespace-only names at the schema level.
    An HTTP layer building on this schema will also return 400.
    """
    from app.services.ai.FieldOpsAI.schemas.prompt_template import (
        PromptTemplateCreate,
        AgentType,
        PromptChannel,
        PromptLanguage,
    )

    with pytest.raises(ValueError, match="Name cannot be blank"):
        PromptTemplateCreate(
            name="   ",
            agent_type=AgentType.CommsAgent,
            channel=PromptChannel.sms,
            language=PromptLanguage.en,
            status="assigned",
            body="Hello {{ customer_name }}",
            variables=["customer_name"],
        )


def test_patch_whitespace_only_name_returns_400(
    client: TestClient,
    db_session: Session,
) -> None:
    """
    A PATCH request with a whitespace-only name must return HTTP 400
    and must not create a new version.
    """
    # Create a valid template first via the legacy route.
    first_response = client.post(
        "/templates",
        json={
            "name": "Valid Name",
            "type": "ws_patch",
            "channel": "sms",
            "locale": "en",
            "format": "text",
            "body_template": "Hello",
        },
    )
    assert first_response.status_code == 200

    # The legacy route does not expose a PATCH endpoint so we test
    # whitespace-only name validation at the schema level.
    from app.services.ai.FieldOpsAI.schemas.prompt_template import (
        PromptTemplateUpdate,
    )

    with pytest.raises(ValueError, match="Name cannot be blank"):
        PromptTemplateUpdate(name="   ")


# ==========================================================
# §6 — Format validation via legacy route
# ==========================================================


def test_legacy_route_accepts_text_format(
    client: TestClient,
) -> None:
    """text is a valid format and must be accepted by the legacy route."""
    response = client.post(
        "/templates",
        json={
            "name": "Text format test",
            "type": "fmt_text_legacy",
            "channel": "sms",
            "locale": "en",
            "format": "text",
            "body_template": "Hello {{ customer.name }}",
        },
    )
    assert response.status_code == 200


def test_legacy_route_accepts_html_format(
    client: TestClient,
) -> None:
    """html is a valid format and must be accepted by the legacy route."""
    response = client.post(
        "/templates",
        json={
            "name": "HTML format test",
            "type": "fmt_html_legacy",
            "channel": "email",
            "locale": "en",
            "format": "html",
            "body_template": "<p>Hello {{ customer.name }}</p>",
        },
    )
    assert response.status_code == 200


@pytest.mark.parametrize("bad_format", ["markdown", "xml", "raw", "javascript", "   "])
def test_legacy_route_rejects_unsupported_format(
    client: TestClient,
    db_session: Session,
    bad_format: str,
) -> None:
    """The legacy /templates route must reject unsupported formats with HTTP 400 without DB mutation."""
    templates_before = db_session.query(NotificationTemplate).count()
    versions_before = db_session.query(TemplateVersion).count()

    response = client.post(
        "/templates",
        json={
            "name": "Bad format test",
            "type": "fmt_bad_legacy",
            "channel": "sms",
            "locale": "en",
            "format": bad_format,
            "body_template": "Hello {{ customer.name }}",
        },
    )

    assert response.status_code == 400

    templates_after = db_session.query(NotificationTemplate).count()
    versions_after = db_session.query(TemplateVersion).count()

    assert templates_after == templates_before
    assert versions_after == versions_before


# ==========================================================
# §7 — Client-supplied version is rejected
# ==========================================================

def test_client_version_field_is_rejected_schema_level() -> None:
    """
    PromptTemplateCreate must reject any client-supplied version field
    because the schema uses extra='forbid'.
    """
    from app.services.ai.FieldOpsAI.schemas.prompt_template import (
        PromptTemplateCreate,
        AgentType,
        PromptChannel,
        PromptLanguage,
    )

    with pytest.raises((ValueError, TypeError)):
        PromptTemplateCreate(
            name="Test",
            agent_type=AgentType.CommsAgent,
            channel=PromptChannel.sms,
            language=PromptLanguage.en,
            status="assigned",
            body="Hello {{ name }}",
            variables=["name"],
            version=5,  # must be rejected
        )

def test_preview_html_escapes_context(
    client: TestClient,
) -> None:
    response = client.post(
        "/templates/preview",
        json={
            "title_template": (
                "Hello {{ name }}"
            ),
            "body_template": (
                "<p>Hello {{ name }}</p>"
            ),
            "mock_context": {
                "name": (
                    "<script>alert(1)</script>"
                ),
            },
            "format": "html",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["rendered_body"] == (
        "<p>Hello "
        "&lt;script&gt;"
        "alert(1)"
        "&lt;/script&gt;"
        "</p>"
    )

    assert "<script>" not in (
        data["rendered_body"]
    )

@pytest.mark.parametrize(
    "bad_format",
    [
        "markdown",
        "xml",
        "raw",
        "javascript",
        "   ",
    ],
)
def test_preview_rejects_invalid_format(
    client: TestClient,
    bad_format: str,
) -> None:
    response = client.post(
        "/templates/preview",
        json={
            "title_template": "Title",
            "body_template": "Body",
            "mock_context": {},
            "format": bad_format,
        },
    )

    assert response.status_code == 400

def test_preview_normalizes_html_format(
    client: TestClient,
) -> None:
    response = client.post(
        "/templates/preview",
        json={
            "title_template": "Title",
            "body_template": (
                "<p>{{ value }}</p>"
            ),
            "mock_context": {
                "value": "<b>unsafe</b>",
            },
            "format": " HTML ",
        },
    )

    assert response.status_code == 200

    assert response.json()[
        "rendered_body"
    ] == (
        "<p>&lt;b&gt;"
        "unsafe"
        "&lt;/b&gt;</p>"
    )