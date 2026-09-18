
"""
Refresh-token security tests.

Covers:
- Normal refresh-token rotation
- Replay protection
- Expired JWT refresh token
- Expired stored refresh token
- Revoked refresh token
- Wrong-user token
- Inactive user
- Deleted user
- Inactive organization
- Deleted organization
- Tenant mismatch
- Role mismatch
- Missing session ID
- Invalid server-side session
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import app.routes.oauth2 as oauth2
from app.routes.oauth2 import GrantError, _refresh_token_grant


# ============================================================================
# Constants
# ============================================================================

NOW = datetime.now(timezone.utc)

TECHNICIAN_ROLE = "technician"


# ============================================================================
# Fake RefreshToken
# ============================================================================


class FakeRefreshToken:
    def __init__(
        self,
        token_hash="stored-token-hash",
        user_id="user-1",
        session_id="session-1",
        expires_at=None,
        revoked_at=None,
    ):
        self.token_hash = token_hash
        self.user_id = user_id
        self.session_id = session_id

        self.expires_at = (
            expires_at
            if expires_at is not None
            else datetime.now(timezone.utc)
            + timedelta(days=7)
        )

        self.revoked_at = revoked_at

    @property
    def is_valid(self):
        now = datetime.now(timezone.utc)

        return (
            self.revoked_at is None
            and self.expires_at > now
        )


# ============================================================================
# Fake Query
# ============================================================================


class FakeQuery:
    def __init__(self, result=None):
        self.result = result

    def filter(self, *args, **kwargs):
        return self

    def where(self, *args, **kwargs):
        return self

    def with_for_update(self, *args, **kwargs):
        return self

    def first(self):
        return self.result

    def one_or_none(self):
        return self.result

    def scalar_one_or_none(self):
        return self.result


# ============================================================================
# Fake DB
# ============================================================================


class FakeDB:
    def __init__(
        self,
        user=None,
        organization=None,
        refresh_token=None,
    ):
        self.user = user
        self.organization = organization
        self.refresh_token = refresh_token

        self.added = []
        self.commit_called = False
        self.flush_called = False
        self.refresh_called = False

    def query(self, model):
        model_name = getattr(
            model,
            "__name__",
            str(model),
        )

        # ------------------------------------------------------------
        # RefreshToken
        # ------------------------------------------------------------

        if model_name == "RefreshToken":
            return FakeQuery(
                self.refresh_token
                if (
                    self.refresh_token is not None
                    and self.refresh_token.revoked_at is None
                )
                else None
            )

        # ------------------------------------------------------------
        # User
        # ------------------------------------------------------------

        if model_name == "User":

            if self.user is None:
                return FakeQuery(None)

            if not getattr(
                self.user,
                "is_active",
                False,
            ):
                return FakeQuery(None)

            if getattr(
                self.user,
                "deleted_at",
                None,
            ) is not None:
                return FakeQuery(None)

            return FakeQuery(self.user)

        # ------------------------------------------------------------
        # Organization
        # ------------------------------------------------------------

        if model_name == "Organization":

            if self.organization is None:
                return FakeQuery(None)

            if getattr(
                self.organization,
                "status",
                None,
            ) != "ACTIVE":
                return FakeQuery(None)

            if getattr(
                self.organization,
                "deleted_at",
                None,
            ) is not None:
                return FakeQuery(None)

            return FakeQuery(self.organization)

        return FakeQuery(None)

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commit_called = True

    def flush(self):
        self.flush_called = True

    def refresh(self, obj):
        self.refresh_called = True


# ============================================================================
# Fake User
# ============================================================================


def make_user(
    user_id="user-1",
    tenant_id="tenant-1",
    role=TECHNICIAN_ROLE,
    is_active=True,
    deleted_at=None,
):
    return SimpleNamespace(
        id=user_id,
        user_id=user_id,
        tenant_id=tenant_id,
        role=role,
        is_active=is_active,
        deleted_at=deleted_at,
        email="technician@example.com",
    )


# ============================================================================
# Fake Organization
# ============================================================================


def make_organization(
    organization_id="tenant-1",
    status="ACTIVE",
    deleted_at=None,
):
    return SimpleNamespace(
        id=organization_id,
        organization_id=organization_id,
        status=status,
        deleted_at=deleted_at,
    )


# ============================================================================
# JWT Claims
# ============================================================================


def make_claims(
    user_id="user-1",
    tenant_id="tenant-1",
    role=TECHNICIAN_ROLE,
    session_id="session-1",
    jti="jti-1",
):
    return {
        "sub": user_id,
        "tenant_id": tenant_id,
        "role": role,
        "session_id": session_id,
        "jti": jti,
        "type": "refresh",
        "iat": int(NOW.timestamp()),
        "exp": int(
            (
                NOW + timedelta(days=7)
            ).timestamp()
        ),
    }


# ============================================================================
# Fake Request
# ============================================================================


def make_request():
    request = MagicMock()

    request.client.host = "127.0.0.1"

    request.headers = {
        "User-Agent": "pytest",
    }

    return request


# ============================================================================
# Fake Session
# ============================================================================


def make_session():
    return SimpleNamespace(
        session_id="session-1",
        user_id="user-1",
        tenant_id="tenant-1",
    )


# ============================================================================
# 1. NORMAL REFRESH TOKEN ROTATION
# ============================================================================


def test_normal_refresh_token_rotation():
    user = make_user(
        user_id="user-1",
        tenant_id="tenant-1",
        role="technician",
        is_active=True,
    )

    organization = make_organization(
        organization_id="tenant-1",
        status="ACTIVE",
    )

    stored_refresh = FakeRefreshToken(
        token_hash="stored-token-hash",
        user_id="user-1",
        session_id="session-1",
    )

    db = FakeDB(
        user=user,
        organization=organization,
        refresh_token=stored_refresh,
    )

    claims = make_claims(
        user_id="user-1",
        tenant_id="tenant-1",
        role="technician",
        session_id="session-1",
    )

    session = make_session()

    new_access_token = "new-access-token"
    new_refresh_token = "new-refresh-token"

    with (
        patch.object(
            oauth2,
            "verify_refresh_token",
            return_value=claims,
        ),
        patch.object(
            oauth2,
            "validate_session",
            return_value=session,
        ),
        patch.object(
            oauth2,
            "touch_session",
            return_value=session,
        ),
        patch.object(
            oauth2,
            "create_access_token",
            return_value=new_access_token,
        ),
        patch.object(
            oauth2,
            "create_refresh_token",
            return_value=new_refresh_token,
        ),
        patch.object(
            oauth2,
            "_persist_refresh_token",
            return_value=None,
        ),
        patch.object(
            oauth2,
            "hashlib",
        ) as mock_hashlib,
    ):

        mock_hash = MagicMock()
        mock_hash.hexdigest.return_value = (
            "stored-token-hash"
        )
        mock_hashlib.sha256.return_value = mock_hash

        result = _refresh_token_grant(
            db=db,
            request=make_request(),
            refresh_token="old-refresh-token",
        )

    assert result[0] is user
    assert result[1] == new_access_token
    assert result[2] == new_refresh_token

    # Old refresh token is revoked.
    assert stored_refresh.revoked_at is not None

    # Transaction committed.
    assert db.commit_called is True


# ============================================================================
# 2. REPLAY PROTECTION
# ============================================================================


def test_refresh_token_replay_is_rejected():
    """
    A rotated/revoked token is not returned by the production query because
    the query explicitly requires revoked_at IS NULL.

    Therefore the expected production error is:
        Refresh token not found or already used
    """

    user = make_user()

    organization = make_organization()

    revoked_token = FakeRefreshToken(
        user_id="user-1",
        session_id="session-1",
        revoked_at=datetime.now(timezone.utc),
    )

    db = FakeDB(
        user=user,
        organization=organization,
        refresh_token=revoked_token,
    )

    claims = make_claims()

    with (
        patch.object(
            oauth2,
            "verify_refresh_token",
            return_value=claims,
        ),
        patch.object(
            oauth2,
            "hashlib",
        ) as mock_hashlib,
    ):

        mock_hash = MagicMock()
        mock_hash.hexdigest.return_value = (
            "stored-token-hash"
        )
        mock_hashlib.sha256.return_value = mock_hash

        with pytest.raises(
            GrantError
        ) as exc_info:

            _refresh_token_grant(
                db=db,
                request=make_request(),
                refresh_token="old-refresh-token",
            )

    assert (
        exc_info.value.error
        == "invalid_grant"
    )

    assert (
        exc_info.value.description
        == "Refresh token not found or already used"
    )

    assert (
        exc_info.value.status_code
        == 401
    )


# ============================================================================
# 3. EXPIRED JWT REFRESH TOKEN
# ============================================================================


def test_expired_refresh_token_is_rejected():
    """
    JWT verification rejects an expired refresh token.
    """

    db = FakeDB(
        user=make_user(),
        organization=make_organization(),
        refresh_token=FakeRefreshToken(),
    )

    expired_error = GrantError(
        "invalid_grant",
        "Refresh token is invalid or expired",
        401,
    )

    with patch.object(
        oauth2,
        "verify_refresh_token",
        side_effect=expired_error,
    ):

        with pytest.raises(
            GrantError
        ) as exc_info:

            _refresh_token_grant(
                db=db,
                request=make_request(),
                refresh_token="expired-refresh-token",
            )

    assert (
        exc_info.value.error
        == "invalid_grant"
    )

    assert (
        exc_info.value.description
        == "Refresh token is invalid or expired"
    )

    assert (
        exc_info.value.status_code
        == 401
    )


# ============================================================================
# 4. EXPIRED STORED REFRESH TOKEN
# ============================================================================


def test_expired_stored_refresh_token_is_rejected():
    """
    The database expiry must also be enforced.
    """

    user = make_user()

    organization = make_organization()

    expired_token = FakeRefreshToken(
        user_id="user-1",
        session_id="session-1",
        expires_at=(
            datetime.now(timezone.utc)
            - timedelta(seconds=1)
        ),
    )

    db = FakeDB(
        user=user,
        organization=organization,
        refresh_token=expired_token,
    )

    claims = make_claims()

    with (
        patch.object(
            oauth2,
            "verify_refresh_token",
            return_value=claims,
        ),
        patch.object(
            oauth2,
            "hashlib",
        ) as mock_hashlib,
    ):

        mock_hash = MagicMock()
        mock_hash.hexdigest.return_value = (
            "stored-token-hash"
        )
        mock_hashlib.sha256.return_value = mock_hash

        with pytest.raises(
            GrantError
        ) as exc_info:

            _refresh_token_grant(
                db=db,
                request=make_request(),
                refresh_token="expired-refresh-token",
            )

    assert (
        exc_info.value.error
        == "invalid_grant"
    )

    assert (
        exc_info.value.description
        == "Refresh token expired or already used"
    )

    assert (
        exc_info.value.status_code
        == 401
    )


# ============================================================================
# 5. REVOKED REFRESH TOKEN
# ============================================================================


def test_revoked_refresh_token_is_rejected():
    """
    A revoked token is filtered out by:

        RefreshToken.revoked_at.is_(None)

    Therefore production returns:

        Refresh token not found or already used
    """

    user = make_user()

    organization = make_organization()

    revoked_token = FakeRefreshToken(
        user_id="user-1",
        session_id="session-1",
        revoked_at=datetime.now(timezone.utc),
    )

    db = FakeDB(
        user=user,
        organization=organization,
        refresh_token=revoked_token,
    )

    claims = make_claims()

    with (
        patch.object(
            oauth2,
            "verify_refresh_token",
            return_value=claims,
        ),
        patch.object(
            oauth2,
            "hashlib",
        ) as mock_hashlib,
    ):

        mock_hash = MagicMock()
        mock_hash.hexdigest.return_value = (
            "stored-token-hash"
        )
        mock_hashlib.sha256.return_value = mock_hash

        with pytest.raises(
            GrantError
        ) as exc_info:

            _refresh_token_grant(
                db=db,
                request=make_request(),
                refresh_token="revoked-refresh-token",
            )

    assert (
        exc_info.value.error
        == "invalid_grant"
    )

    assert (
        exc_info.value.description
        == "Refresh token not found or already used"
    )

    assert (
        exc_info.value.status_code
        == 401
    )


# ============================================================================
# 6. WRONG USER
# ============================================================================


def test_refresh_token_wrong_user_is_rejected():
    user = make_user(
        user_id="user-2",
        tenant_id="tenant-1",
        role="technician",
    )

    organization = make_organization()

    stored_token = FakeRefreshToken(
        user_id="user-2",
        session_id="session-1",
    )

    db = FakeDB(
        user=user,
        organization=organization,
        refresh_token=stored_token,
    )

    claims = make_claims(
        user_id="user-1",
        tenant_id="tenant-1",
        role="technician",
    )

    with (
        patch.object(
            oauth2,
            "verify_refresh_token",
            return_value=claims,
        ),
        patch.object(
            oauth2,
            "hashlib",
        ) as mock_hashlib,
    ):

        mock_hash = MagicMock()
        mock_hash.hexdigest.return_value = (
            "stored-token-hash"
        )
        mock_hashlib.sha256.return_value = mock_hash

        with pytest.raises(
            GrantError
        ) as exc_info:

            _refresh_token_grant(
                db=db,
                request=make_request(),
                refresh_token="refresh-token",
            )

    assert (
        exc_info.value.description
        == "Refresh token ownership validation failed"
    )

    assert (
        exc_info.value.status_code
        == 401
    )


# ============================================================================
# 7. INACTIVE USER
# ============================================================================


def test_inactive_user_rejects_refresh():
    user = make_user(
        user_id="user-1",
        tenant_id="tenant-1",
        role="technician",
        is_active=False,
    )

    organization = make_organization()

    stored_token = FakeRefreshToken(
        user_id="user-1",
        session_id="session-1",
    )

    db = FakeDB(
        user=user,
        organization=organization,
        refresh_token=stored_token,
    )

    claims = make_claims()

    with (
        patch.object(
            oauth2,
            "verify_refresh_token",
            return_value=claims,
        ),
        patch.object(
            oauth2,
            "hashlib",
        ) as mock_hashlib,
    ):

        mock_hash = MagicMock()
        mock_hash.hexdigest.return_value = (
            "stored-token-hash"
        )
        mock_hashlib.sha256.return_value = mock_hash

        with pytest.raises(
            GrantError
        ) as exc_info:

            _refresh_token_grant(
                db=db,
                request=make_request(),
                refresh_token="refresh-token",
            )

    assert (
        exc_info.value.description
        == "User account not found or deactivated"
    )

    assert (
        exc_info.value.status_code
        == 401
    )


# ============================================================================
# 8. DELETED USER
# ============================================================================


def test_deleted_user_rejects_refresh():
    user = make_user(
        user_id="user-1",
        tenant_id="tenant-1",
        role="technician",
        is_active=True,
        deleted_at=datetime.now(timezone.utc),
    )

    organization = make_organization()

    stored_token = FakeRefreshToken(
        user_id="user-1",
        session_id="session-1",
    )

    db = FakeDB(
        user=user,
        organization=organization,
        refresh_token=stored_token,
    )

    claims = make_claims()

    with (
        patch.object(
            oauth2,
            "verify_refresh_token",
            return_value=claims,
        ),
        patch.object(
            oauth2,
            "hashlib",
        ) as mock_hashlib,
    ):

        mock_hash = MagicMock()
        mock_hash.hexdigest.return_value = (
            "stored-token-hash"
        )
        mock_hashlib.sha256.return_value = mock_hash

        with pytest.raises(
            GrantError
        ) as exc_info:

            _refresh_token_grant(
                db=db,
                request=make_request(),
                refresh_token="refresh-token",
            )

    assert (
        exc_info.value.description
        == "User account not found or deactivated"
    )

    assert (
        exc_info.value.status_code
        == 401
    )


# ============================================================================
# 9. INACTIVE ORGANIZATION
# ============================================================================


def test_inactive_organization_rejects_refresh():
    user = make_user(
        user_id="user-1",
        tenant_id="tenant-1",
        role="technician",
    )

    organization = make_organization(
        organization_id="tenant-1",
        status="INACTIVE",
    )

    stored_token = FakeRefreshToken(
        user_id="user-1",
        session_id="session-1",
    )

    db = FakeDB(
        user=user,
        organization=organization,
        refresh_token=stored_token,
    )

    claims = make_claims()

    with (
        patch.object(
            oauth2,
            "verify_refresh_token",
            return_value=claims,
        ),
        patch.object(
            oauth2,
            "hashlib",
        ) as mock_hashlib,
    ):

        mock_hash = MagicMock()
        mock_hash.hexdigest.return_value = (
            "stored-token-hash"
        )
        mock_hashlib.sha256.return_value = mock_hash

        with pytest.raises(
            GrantError
        ) as exc_info:

            _refresh_token_grant(
                db=db,
                request=make_request(),
                refresh_token="refresh-token",
            )

    assert (
        exc_info.value.description
        == "Organization is inactive or deleted"
    )

    assert (
        exc_info.value.status_code
        == 401
    )


# ============================================================================
# 10. DELETED ORGANIZATION
# ============================================================================


def test_deleted_organization_rejects_refresh():
    user = make_user(
        user_id="user-1",
        tenant_id="tenant-1",
        role="technician",
    )

    organization = make_organization(
        organization_id="tenant-1",
        status="ACTIVE",
        deleted_at=datetime.now(timezone.utc),
    )

    stored_token = FakeRefreshToken(
        user_id="user-1",
        session_id="session-1",
    )

    db = FakeDB(
        user=user,
        organization=organization,
        refresh_token=stored_token,
    )

    claims = make_claims()

    with (
        patch.object(
            oauth2,
            "verify_refresh_token",
            return_value=claims,
        ),
        patch.object(
            oauth2,
            "hashlib",
        ) as mock_hashlib,
    ):

        mock_hash = MagicMock()
        mock_hash.hexdigest.return_value = (
            "stored-token-hash"
        )
        mock_hashlib.sha256.return_value = mock_hash

        with pytest.raises(
            GrantError
        ) as exc_info:

            _refresh_token_grant(
                db=db,
                request=make_request(),
                refresh_token="refresh-token",
            )

    assert (
        exc_info.value.description
        == "Organization is inactive or deleted"
    )

    assert (
        exc_info.value.status_code
        == 401
    )


# ============================================================================
# 11. TENANT MISMATCH
# ============================================================================


def test_tenant_mismatch_rejects_refresh():
    user = make_user(
        user_id="user-1",
        tenant_id="tenant-1",
        role="technician",
    )

    organization = make_organization(
        organization_id="tenant-1",
    )

    stored_token = FakeRefreshToken(
        user_id="user-1",
        session_id="session-1",
    )

    db = FakeDB(
        user=user,
        organization=organization,
        refresh_token=stored_token,
    )

    claims = make_claims(
        user_id="user-1",
        tenant_id="tenant-2",
        role="technician",
    )

    with (
        patch.object(
            oauth2,
            "verify_refresh_token",
            return_value=claims,
        ),
        patch.object(
            oauth2,
            "hashlib",
        ) as mock_hashlib,
    ):

        mock_hash = MagicMock()
        mock_hash.hexdigest.return_value = (
            "stored-token-hash"
        )
        mock_hashlib.sha256.return_value = mock_hash

        with pytest.raises(
            GrantError
        ) as exc_info:

            _refresh_token_grant(
                db=db,
                request=make_request(),
                refresh_token="refresh-token",
            )

    assert (
        exc_info.value.description
        == "Refresh token tenant validation failed"
    )

    assert (
        exc_info.value.status_code
        == 401
    )


# ============================================================================
# 12. ROLE MISMATCH
# ============================================================================


def test_role_mismatch_rejects_refresh():
    user = make_user(
        user_id="user-1",
        tenant_id="tenant-1",
        role="dispatcher",
    )

    organization = make_organization(
        organization_id="tenant-1",
    )

    stored_token = FakeRefreshToken(
        user_id="user-1",
        session_id="session-1",
    )

    db = FakeDB(
        user=user,
        organization=organization,
        refresh_token=stored_token,
    )

    claims = make_claims(
        user_id="user-1",
        tenant_id="tenant-1",
        role="technician",
    )

    with (
        patch.object(
            oauth2,
            "verify_refresh_token",
            return_value=claims,
        ),
        patch.object(
            oauth2,
            "hashlib",
        ) as mock_hashlib,
    ):

        mock_hash = MagicMock()
        mock_hash.hexdigest.return_value = (
            "stored-token-hash"
        )
        mock_hashlib.sha256.return_value = mock_hash

        with pytest.raises(
            GrantError
        ) as exc_info:

            _refresh_token_grant(
                db=db,
                request=make_request(),
                refresh_token="refresh-token",
            )

    assert (
        exc_info.value.description
        == "Refresh token role validation failed"
    )

    assert (
        exc_info.value.status_code
        == 401
    )


# ============================================================================
# 13. MISSING SESSION ID
# ============================================================================


def test_missing_session_id_rejects_refresh():
    user = make_user()

    organization = make_organization()

    stored_token = FakeRefreshToken(
        user_id="user-1",
        session_id=None,
    )

    db = FakeDB(
        user=user,
        organization=organization,
        refresh_token=stored_token,
    )

    claims = make_claims(
        user_id="user-1",
        tenant_id="tenant-1",
        role="technician",
        session_id=None,
    )

    claims.pop(
        "session_id",
        None,
    )

    with (
        patch.object(
            oauth2,
            "verify_refresh_token",
            return_value=claims,
        ),
        patch.object(
            oauth2,
            "hashlib",
        ) as mock_hashlib,
    ):

        mock_hash = MagicMock()
        mock_hash.hexdigest.return_value = (
            "stored-token-hash"
        )
        mock_hashlib.sha256.return_value = mock_hash

        with pytest.raises(
            GrantError
        ) as exc_info:

            _refresh_token_grant(
                db=db,
                request=make_request(),
                refresh_token="refresh-token",
            )

    assert (
        exc_info.value.description
        == "Refresh token is not associated with a session"
    )

    assert (
        exc_info.value.status_code
        == 401
    )


# ============================================================================
# 14. INVALID SERVER-SIDE SESSION
# ============================================================================


def test_invalid_session_rejects_refresh():
    user = make_user(
        user_id="user-1",
        tenant_id="tenant-1",
        role="technician",
    )

    organization = make_organization(
        organization_id="tenant-1",
        status="ACTIVE",
    )

    stored_token = FakeRefreshToken(
        user_id="user-1",
        session_id="session-1",
    )

    db = FakeDB(
        user=user,
        organization=organization,
        refresh_token=stored_token,
    )

    claims = make_claims(
        user_id="user-1",
        tenant_id="tenant-1",
        role="technician",
        session_id="session-1",
    )

    with (
        patch.object(
            oauth2,
            "verify_refresh_token",
            return_value=claims,
        ),
        patch.object(
            oauth2,
            "validate_session",
            return_value=None,
        ),
        patch.object(
            oauth2,
            "hashlib",
        ) as mock_hashlib,
    ):

        mock_hash = MagicMock()
        mock_hash.hexdigest.return_value = (
            "stored-token-hash"
        )
        mock_hashlib.sha256.return_value = mock_hash

        with pytest.raises(
            GrantError
        ) as exc_info:

            _refresh_token_grant(
                db=db,
                request=make_request(),
                refresh_token="refresh-token",
            )

    assert (
        exc_info.value.description
        == "Session expired due to inactivity or maximum lifetime"
    )

    assert (
        exc_info.value.status_code
        == 401
    )

