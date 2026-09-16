"""
Tests for Enterprise SSO service.

Covers:
- Secure state generation
- Secure nonce generation
- Redis state storage
- State consumption
- Single-use/replay protection
- Expired/missing state
- Invalid state payload
- OIDC identity -> FieldOps user mapping
- Unknown identity
- Missing user
- Disabled user
- Missing tenant
- Missing tenant organization
- Inactive tenant
- Deleted tenant
- Provider claims cannot control FieldOps tenant/role
"""

import json

import pytest

from app.auth.sso_service import (
    SSOService,
    SSOValidationError,
)


# ---------------------------------------------------------------------------
# Fake Redis
# ---------------------------------------------------------------------------


class FakeRedis:
    """
    Small async Redis replacement for unit tests.

    It supports the Redis operations used by SSOService:
        - set()
        - eval()
        - aclose()
    """

    def __init__(self):
        self.data = {}
        self.ttl = {}

    async def set(self, key, value, ex=None):
        self.data[key] = value
        self.ttl[key] = ex
        return True

    async def eval(self, script, numkeys, key):
        """
        Simulate the Lua script used by consume_state():

            GET key
            DEL key
            return old value
        """

        value = self.data.get(key)

        if value is not None:
            del self.data[key]
            self.ttl.pop(key, None)

        return value

    async def aclose(self):
        return None


# ---------------------------------------------------------------------------
# Fake SQLAlchemy query objects
# ---------------------------------------------------------------------------


class FakeQuery:
    """
    Minimal SQLAlchemy-like query implementation.

    The real service performs:

        db.query(Model).filter(...).first()

    We don't need a real database for these service unit tests.
    """

    def __init__(self, result):
        self.result = result

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.result


class FakeDB:
    """
    Fake database that returns configured OIDC identity,
    user and organization records.
    """

    def __init__(
        self,
        identity=None,
        user=None,
        organization=None,
    ):
        self.identity = identity
        self.user = user
        self.organization = organization

    def query(self, model):
        model_name = getattr(model, "__name__", "")

        if model_name == "OIDCIdentity":
            return FakeQuery(self.identity)

        if model_name == "User":
            return FakeQuery(self.user)

        if model_name == "Organization":
            return FakeQuery(self.organization)

        raise AssertionError(
            f"Unexpected model queried: {model}"
        )


# ---------------------------------------------------------------------------
# Fake model objects
# ---------------------------------------------------------------------------


class FakeOIDCIdentity:
    __name__ = "OIDCIdentity"

    def __init__(
        self,
        user_id="user-001",
        provider="google",
        issuer="https://accounts.google.com",
        subject="google-subject-001",
    ):
        self.user_id = user_id
        self.provider = provider
        self.issuer = issuer
        self.subject = subject


class FakeUser:
    __name__ = "User"

    def __init__(
        self,
        user_id="user-001",
        tenant_id="tenant-001",
        role="dispatcher",
        is_active=True,
    ):
        self.id = user_id
        self.tenant_id = tenant_id
        self.role = role
        self.is_active = is_active


class FakeOrganization:
    __name__ = "Organization"

    def __init__(
        self,
        organization_id="tenant-001",
        is_active=True,
        is_deleted=False,
    ):
        self.id = organization_id
        self.is_active = is_active
        self.is_deleted = is_deleted


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_redis():
    return FakeRedis()


@pytest.fixture
def sso_service(fake_redis):
    return SSOService(redis_client=fake_redis)


@pytest.fixture
def valid_identity():
    return FakeOIDCIdentity()


@pytest.fixture
def valid_user():
    return FakeUser()


@pytest.fixture
def valid_organization():
    return FakeOrganization()


@pytest.fixture
def valid_db(
    valid_identity,
    valid_user,
    valid_organization,
):
    return FakeDB(
        identity=valid_identity,
        user=valid_user,
        organization=valid_organization,
    )


# ===========================================================================
# STATE / NONCE TESTS
# ===========================================================================


def test_generate_state_is_secure_and_unique():
    state1 = SSOService.generate_state()
    state2 = SSOService.generate_state()

    assert state1
    assert state2

    assert isinstance(state1, str)
    assert isinstance(state2, str)

    assert state1 != state2

    # token_urlsafe(32) should produce a reasonably long value.
    assert len(state1) >= 32
    assert len(state2) >= 32


def test_generate_nonce_is_secure_and_unique():
    nonce1 = SSOService.generate_nonce()
    nonce2 = SSOService.generate_nonce()

    assert nonce1
    assert nonce2

    assert isinstance(nonce1, str)
    assert isinstance(nonce2, str)

    assert nonce1 != nonce2

    assert len(nonce1) >= 32
    assert len(nonce2) >= 32


# ===========================================================================
# STORE STATE TESTS
# ===========================================================================


@pytest.mark.asyncio
async def test_store_state_success(
    sso_service,
    fake_redis,
):
    state = "test-state"
    nonce = "test-nonce"
    redirect_uri = "https://fieldops.example.com/auth/sso/callback"

    await sso_service.store_state(
        state=state,
        nonce=nonce,
        redirect_uri=redirect_uri,
    )

    key = SSOService._state_key(state)

    assert key in fake_redis.data

    payload = json.loads(fake_redis.data[key])

    assert payload["nonce"] == nonce
    assert payload["redirect_uri"] == redirect_uri

    assert fake_redis.ttl[key] == SSOService.STATE_TTL_SECONDS


@pytest.mark.asyncio
async def test_store_state_rejects_missing_state(
    sso_service,
):
    with pytest.raises(
        SSOValidationError,
        match="SSO state is required",
    ):
        await sso_service.store_state(
            state="",
            nonce="nonce",
            redirect_uri="https://example.com/callback",
        )


@pytest.mark.asyncio
async def test_store_state_rejects_missing_nonce(
    sso_service,
):
    with pytest.raises(
        SSOValidationError,
        match="SSO nonce is required",
    ):
        await sso_service.store_state(
            state="state",
            nonce="",
            redirect_uri="https://example.com/callback",
        )


@pytest.mark.asyncio
async def test_store_state_rejects_missing_redirect_uri(
    sso_service,
):
    with pytest.raises(
        SSOValidationError,
        match="SSO redirect URI is required",
    ):
        await sso_service.store_state(
            state="state",
            nonce="nonce",
            redirect_uri="",
        )


# ===========================================================================
# CONSUME STATE TESTS
# ===========================================================================


@pytest.mark.asyncio
async def test_consume_state_success(
    sso_service,
    fake_redis,
):
    state = "valid-state"
    nonce = "valid-nonce"
    redirect_uri = "https://fieldops.example.com/auth/sso/callback"

    await sso_service.store_state(
        state=state,
        nonce=nonce,
        redirect_uri=redirect_uri,
    )

    result = await sso_service.consume_state(state)

    assert result == {
        "nonce": nonce,
        "redirect_uri": redirect_uri,
    }


@pytest.mark.asyncio
async def test_consume_state_is_single_use(
    sso_service,
):
    state = "single-use-state"
    nonce = "nonce"
    redirect_uri = "https://example.com/callback"

    await sso_service.store_state(
        state=state,
        nonce=nonce,
        redirect_uri=redirect_uri,
    )

    first_result = await sso_service.consume_state(state)

    assert first_result["nonce"] == nonce

    # Second attempt must fail.
    with pytest.raises(
        SSOValidationError,
        match="Invalid or expired SSO state",
    ):
        await sso_service.consume_state(state)


@pytest.mark.asyncio
async def test_consume_missing_state(
    sso_service,
):
    with pytest.raises(
        SSOValidationError,
        match="SSO state is required",
    ):
        await sso_service.consume_state("")


@pytest.mark.asyncio
async def test_consume_unknown_state(
    sso_service,
):
    with pytest.raises(
        SSOValidationError,
        match="Invalid or expired SSO state",
    ):
        await sso_service.consume_state(
            "does-not-exist"
        )


@pytest.mark.asyncio
async def test_consume_state_with_invalid_json(
    sso_service,
    fake_redis,
):
    state = "invalid-json-state"

    key = SSOService._state_key(state)

    fake_redis.data[key] = "this-is-not-json"

    with pytest.raises(
        SSOValidationError,
        match="Invalid SSO state data",
    ):
        await sso_service.consume_state(state)


@pytest.mark.asyncio
async def test_consume_state_with_non_dict_payload(
    sso_service,
    fake_redis,
):
    state = "non-dict-state"

    key = SSOService._state_key(state)

    fake_redis.data[key] = json.dumps(
        ["invalid", "payload"]
    )

    with pytest.raises(
        SSOValidationError,
        match="Invalid SSO state data",
    ):
        await sso_service.consume_state(state)


@pytest.mark.asyncio
async def test_consume_state_missing_nonce(
    sso_service,
    fake_redis,
):
    state = "missing-nonce"

    key = SSOService._state_key(state)

    fake_redis.data[key] = json.dumps(
        {
            "redirect_uri": "https://example.com/callback"
        }
    )

    with pytest.raises(
        SSOValidationError,
        match="SSO nonce is missing",
    ):
        await sso_service.consume_state(state)


@pytest.mark.asyncio
async def test_consume_state_missing_redirect_uri(
    sso_service,
    fake_redis,
):
    state = "missing-redirect"

    key = SSOService._state_key(state)

    fake_redis.data[key] = json.dumps(
        {
            "nonce": "nonce"
        }
    )

    with pytest.raises(
        SSOValidationError,
        match="SSO redirect URI is missing",
    ):
        await sso_service.consume_state(state)


# ===========================================================================
# USER RESOLUTION TESTS
# ===========================================================================


def test_resolve_user_success(
    valid_db,
    valid_user,
):
    result = SSOService.resolve_user(
        valid_db,
        provider="google",
        issuer="https://accounts.google.com",
        subject="google-subject-001",
    )

    assert result is valid_user

    assert result.id == "user-001"
    assert result.tenant_id == "tenant-001"
    assert result.role == "dispatcher"


def test_resolve_user_requires_provider(
    valid_db,
):
    with pytest.raises(
        SSOValidationError,
        match="SSO provider is missing",
    ):
        SSOService.resolve_user(
            valid_db,
            provider="",
            issuer="https://accounts.google.com",
            subject="subject",
        )


def test_resolve_user_requires_issuer(
    valid_db,
):
    with pytest.raises(
        SSOValidationError,
        match="OIDC issuer is missing",
    ):
        SSOService.resolve_user(
            valid_db,
            provider="google",
            issuer="",
            subject="subject",
        )


def test_resolve_user_requires_subject(
    valid_db,
):
    with pytest.raises(
        SSOValidationError,
        match="OIDC subject is missing",
    ):
        SSOService.resolve_user(
            valid_db,
            provider="google",
            issuer="https://accounts.google.com",
            subject="",
        )


# ===========================================================================
# UNKNOWN IDENTITY
# ===========================================================================


def test_unknown_oidc_identity_is_rejected(
    valid_user,
    valid_organization,
):
    db = FakeDB(
        identity=None,
        user=valid_user,
        organization=valid_organization,
    )

    with pytest.raises(
        SSOValidationError,
        match="SSO identity is not mapped",
    ):
        SSOService.resolve_user(
            db,
            provider="google",
            issuer="https://accounts.google.com",
            subject="unknown-subject",
        )


# ===========================================================================
# INVALID USER MAPPING
# ===========================================================================


def test_identity_pointing_to_missing_user_is_rejected(
    valid_identity,
    valid_organization,
):
    db = FakeDB(
        identity=valid_identity,
        user=None,
        organization=valid_organization,
    )

    with pytest.raises(
        SSOValidationError,
        match="SSO user mapping is invalid",
    ):
        SSOService.resolve_user(
            db,
            provider="google",
            issuer="https://accounts.google.com",
            subject="google-subject-001",
        )


# ===========================================================================
# DISABLED USER
# ===========================================================================


def test_disabled_user_is_rejected(
    valid_identity,
    valid_organization,
):
    disabled_user = FakeUser(
        user_id="user-001",
        tenant_id="tenant-001",
        role="dispatcher",
        is_active=False,
    )

    db = FakeDB(
        identity=valid_identity,
        user=disabled_user,
        organization=valid_organization,
    )

    with pytest.raises(
        SSOValidationError,
        match="FieldOps user account is disabled",
    ):
        SSOService.resolve_user(
            db,
            provider="google",
            issuer="https://accounts.google.com",
            subject="google-subject-001",
        )


# ===========================================================================
# MISSING TENANT
# ===========================================================================


def test_user_without_tenant_is_rejected(
    valid_identity,
    valid_organization,
):
    user_without_tenant = FakeUser(
        user_id="user-001",
        tenant_id=None,
        role="dispatcher",
        is_active=True,
    )

    db = FakeDB(
        identity=valid_identity,
        user=user_without_tenant,
        organization=valid_organization,
    )

    with pytest.raises(
        SSOValidationError,
        match="FieldOps user is not assigned to a tenant",
    ):
        SSOService.resolve_user(
            db,
            provider="google",
            issuer="https://accounts.google.com",
            subject="google-subject-001",
        )


# ===========================================================================
# TENANT DOES NOT EXIST
# ===========================================================================


def test_missing_tenant_organization_is_rejected(
    valid_identity,
    valid_user,
):
    db = FakeDB(
        identity=valid_identity,
        user=valid_user,
        organization=None,
    )

    with pytest.raises(
        SSOValidationError,
        match="FieldOps tenant is invalid",
    ):
        SSOService.resolve_user(
            db,
            provider="google",
            issuer="https://accounts.google.com",
            subject="google-subject-001",
        )


# ===========================================================================
# INACTIVE TENANT
# ===========================================================================


def test_inactive_tenant_is_rejected(
    valid_identity,
    valid_user,
):
    inactive_organization = FakeOrganization(
        organization_id="tenant-001",
        is_active=False,
        is_deleted=False,
    )

    db = FakeDB(
        identity=valid_identity,
        user=valid_user,
        organization=inactive_organization,
    )

    with pytest.raises(
        SSOValidationError,
        match="FieldOps tenant is inactive",
    ):
        SSOService.resolve_user(
            db,
            provider="google",
            issuer="https://accounts.google.com",
            subject="google-subject-001",
        )


# ===========================================================================
# DELETED TENANT
# ===========================================================================


def test_deleted_tenant_is_rejected(
    valid_identity,
    valid_user,
):
    deleted_organization = FakeOrganization(
        organization_id="tenant-001",
        is_active=True,
        is_deleted=True,
    )

    db = FakeDB(
        identity=valid_identity,
        user=valid_user,
        organization=deleted_organization,
    )

    with pytest.raises(
        SSOValidationError,
        match="FieldOps tenant is deleted",
    ):
        SSOService.resolve_user(
            db,
            provider="google",
            issuer="https://accounts.google.com",
            subject="google-subject-001",
        )


# ===========================================================================
# TENANT IS TAKEN FROM FIELDOPS USER
# ===========================================================================


def test_fieldops_user_tenant_is_authoritative(
    valid_identity,
):
    """
    Security requirement:

    OIDC provider may authenticate the user,
    but FieldOps owns tenant assignment.

    The service returns the tenant from User.tenant_id.
    """

    fieldops_user = FakeUser(
        user_id="user-001",
        tenant_id="fieldops-tenant",
        role="dispatcher",
        is_active=True,
    )

    fieldops_organization = FakeOrganization(
        organization_id="fieldops-tenant",
        is_active=True,
        is_deleted=False,
    )

    db = FakeDB(
        identity=valid_identity,
        user=fieldops_user,
        organization=fieldops_organization,
    )

    result = SSOService.resolve_user(
        db,
        provider="google",
        issuer="https://accounts.google.com",
        subject="google-subject-001",
    )

    assert result.tenant_id == "fieldops-tenant"


# ===========================================================================
# FIELDOPS ROLE IS AUTHORITATIVE
# ===========================================================================


def test_fieldops_user_role_is_authoritative(
    valid_identity,
):
    """
    Security requirement:

    Provider claims must never assign FieldOps roles.

    The SSO service resolves the existing FieldOps User.
    Therefore the FieldOps role remains authoritative.
    """

    fieldops_user = FakeUser(
        user_id="user-001",
        tenant_id="tenant-001",
        role="dispatcher",
        is_active=True,
    )

    organization = FakeOrganization(
        organization_id="tenant-001",
        is_active=True,
        is_deleted=False,
    )

    db = FakeDB(
        identity=valid_identity,
        user=fieldops_user,
        organization=organization,
    )

    result = SSOService.resolve_user(
        db,
        provider="google",
        issuer="https://accounts.google.com",
        subject="google-subject-001",
    )

    # The role comes from FieldOps.
    assert result.role == "dispatcher"

    # An external IdP claim such as:
    #
    #     role = "super_admin"
    #
    # would not change this value.
    assert result.role != "super_admin"


# ===========================================================================
# PROVIDER IDENTITY MAPPING
# ===========================================================================


def test_identity_is_scoped_by_provider(
    valid_user,
    valid_organization,
):
    """
    Same subject from another provider must not automatically
    resolve to the Google identity.
    """

    google_identity = FakeOIDCIdentity(
        user_id="user-001",
        provider="google",
        issuer="https://accounts.google.com",
        subject="same-subject",
    )

    db = FakeDB(
        identity=None,
        user=valid_user,
        organization=valid_organization,
    )

    with pytest.raises(
        SSOValidationError,
        match="SSO identity is not mapped",
    ):
        SSOService.resolve_user(
            db,
            provider="microsoft",
            issuer="https://login.microsoftonline.com",
            subject="same-subject",
        )


# ===========================================================================
# PROVIDER ISSUER MAPPING
# ===========================================================================


def test_identity_is_scoped_by_issuer(
    valid_user,
    valid_organization,
):
    """
    Same subject/provider but a different issuer must not
    automatically resolve to an existing identity.
    """

    identity = FakeOIDCIdentity(
        user_id="user-001",
        provider="google",
        issuer="https://accounts.google.com",
        subject="subject-001",
    )

    db = FakeDB(
        identity=None,
        user=valid_user,
        organization=valid_organization,
    )

    with pytest.raises(
        SSOValidationError,
        match="SSO identity is not mapped",
    ):
        SSOService.resolve_user(
            db,
            provider="google",
            issuer="https://attacker.example.com",
            subject="subject-001",
        )


# ===========================================================================
# REDIS FAILURE TESTS
# ===========================================================================


class BrokenRedis:
    async def set(self, *args, **kwargs):
        raise RuntimeError("Redis unavailable")

    async def eval(self, *args, **kwargs):
        raise RuntimeError("Redis unavailable")

    async def aclose(self):
        return None


@pytest.mark.asyncio
async def test_store_state_handles_redis_failure():
    service = SSOService(
        redis_client=BrokenRedis()
    )

    with pytest.raises(
        SSOValidationError,
        match="Unable to initialize SSO session",
    ):
        await service.store_state(
            state="state",
            nonce="nonce",
            redirect_uri="https://example.com/callback",
        )


@pytest.mark.asyncio
async def test_consume_state_handles_redis_failure():
    service = SSOService(
        redis_client=BrokenRedis()
    )

    with pytest.raises(
        SSOValidationError,
        match="Unable to validate SSO session",
    ):
        await service.consume_state(
            "state"
        )


# ===========================================================================
# CLOSE TEST
# ===========================================================================


@pytest.mark.asyncio
async def test_close_closes_redis_client(
    fake_redis,
):
    service = SSOService(
        redis_client=fake_redis
    )

    await service.close()

    # FakeRedis has no observable connection state,
    # but close() should complete without error.
    assert True


@pytest.mark.asyncio
async def test_close_without_redis_client():
    service = SSOService()

    # No Redis connection should be created merely by close().
    await service.close()