import pytest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from starlette.requests import Request

from app.routes.auth import (
    ForgotPasswordRequest,
    ResetPasswordRequest,
    forgot_password,
    reset_password,
    hash_password,
    hash_reset_token,
)
from app.models.password_reset_token import PasswordResetToken
from app.models.user import RefreshToken, User


def make_request():
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/auth/reset-password",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "scheme": "http",
        }
    )


def make_user():
    return SimpleNamespace(
        id="user-1",
        email="test@example.com",
        first_name="Test",
        last_name="User",
        tenant_id="tenant-1",
        password_hash=hash_password("OldPassword1!"),
        is_active=True,
        deleted_at=None,
    )


def make_token(
    raw_token="valid-reset-token",
    user_id="user-1",
    tenant_id="tenant-1",
    expires_at=None,
    used_at=None,
):
    return SimpleNamespace(
        id="reset-1",
        user_id=user_id,
        tenant_id=tenant_id,
        token_hash=hash_reset_token(raw_token),
        expires_at=expires_at
        or datetime.now(timezone.utc) + timedelta(minutes=15),
        used_at=used_at,
    )


class FakeQuery:
    def __init__(self, result=None, update_result=1):
        self.result = result
        self.update_result = update_result

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.result

    def update(self, *args, **kwargs):
        return self.update_result


class FakeDB:
    def __init__(self, token=None, user=None):
        self.token = token
        self.user = user
        self.added = []
        self.commits = 0
        self.refresh_update_calls = 0

    def query(self, model):
        if model is PasswordResetToken:
            return FakeQuery(self.token)
        if model is User:
            return FakeQuery(self.user)
        if model is RefreshToken:
            self.refresh_update_calls += 1
            return FakeQuery(update_result=1)
        raise AssertionError(f"Unexpected model queried: {model}")

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_valid_reset_token_resets_password_and_consumes_token():
    user = make_user()
    token = make_token()
    db = FakeDB(token=token, user=user)

    with patch(
        "app.routes.auth._log_audit"
    ), patch(
        "app.routes.auth.hash_password",
        return_value="NEW_HASH",
    ):
        result = await reset_password(
            ResetPasswordRequest(
                token="valid-reset-token",
                new_password="NewPassword1!",
            ),
            make_request(),
            db,
        )

    assert result["message"] == "Password reset successfully"
    assert user.password_hash == "NEW_HASH"
    assert token.used_at is not None
    assert db.refresh_update_calls == 1
    assert db.commits == 1


@pytest.mark.asyncio
async def test_expired_reset_token_is_rejected():
    user = make_user()
    token = make_token(
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)
    )
    db = FakeDB(token=token, user=user)

    with pytest.raises(HTTPException) as exc:
        await reset_password(
            ResetPasswordRequest(
                token="valid-reset-token",
                new_password="NewPassword1!",
            ),
            make_request(),
            db,
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "Invalid or expired reset token"
    assert user.password_hash != "NEW_HASH"
    assert db.commits == 0


@pytest.mark.asyncio
async def test_already_used_reset_token_is_rejected():
    user = make_user()
    token = make_token(
        used_at=datetime.now(timezone.utc) - timedelta(minutes=1)
    )
    db = FakeDB(token=token, user=user)

    with pytest.raises(HTTPException) as exc:
        await reset_password(
            ResetPasswordRequest(
                token="valid-reset-token",
                new_password="NewPassword1!",
            ),
            make_request(),
            db,
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "Invalid or expired reset token"
    assert db.commits == 0


@pytest.mark.asyncio
async def test_malformed_or_unknown_reset_token_is_rejected():
    user = make_user()
    db = FakeDB(token=None, user=user)

    with pytest.raises(HTTPException) as exc:
        await reset_password(
            ResetPasswordRequest(
                token="not-a-real-token",
                new_password="NewPassword1!",
            ),
            make_request(),
            db,
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "Invalid or expired reset token"
    assert db.commits == 0


@pytest.mark.asyncio
async def test_forgot_password_unknown_email_returns_generic_response():
    db = FakeDB(user=None)
    email_service = AsyncMock()

    with patch(
        "app.routes.auth.EmailService",
        return_value=SimpleNamespace(send_email=email_service),
    ):
        result = await forgot_password(
            ForgotPasswordRequest(email="unknown@example.com"),
            make_request(),
            db,
        )

    assert result["message"] == (
        "If an account with that email exists, "
        "a password reset link has been sent."
    )
    email_service.assert_not_awaited()
    assert db.added == []
    assert db.commits == 0


@pytest.mark.asyncio
async def test_repeated_reset_requests_create_reset_tokens():
    """
    A newer password-reset request invalidates the previous
    unused reset token.

    Expected behavior:
        Token A -> invalidated after Token B is requested
        Token B -> remains valid
    """

    from app.models.password_reset_token import PasswordResetToken
    from app.routes import auth

    user = SimpleNamespace(
        id="user-123",
        tenant_id="tenant-123",
        email="user@example.com",
        first_name="Test",
        deleted_at=None,
    )

    # Store created reset tokens.
    tokens = []

    class FakeQuery:
        def __init__(self, model):
            self.model = model
            self.tokens = tokens

        def filter(self, *conditions, **kwargs):
            return self

        def first(self):
            # User lookup.
            if self.model is auth.User:
                return user

            # Password reset token lookup.
            if self.model is PasswordResetToken:
                if not self.tokens:
                    return None

                return self.tokens[-1]

            return None

        def update(self, values, synchronize_session=False):
            if self.model is PasswordResetToken:
                count = 0

                for token in self.tokens:
                    if token.used_at is None:
                        token.used_at = values["used_at"]
                        count += 1

                return count

            return 0

    class FakeDB:
        def query(self, model):
            return FakeQuery(model)

        def add(self, obj):
            if isinstance(obj, PasswordResetToken):
                tokens.append(obj)

        def commit(self):
            pass

    db = FakeDB()

    request = SimpleNamespace(
        client=SimpleNamespace(
            host="127.0.0.1"
        ),
        headers={},
    )

    # Capture tokens sent through the email.
    sent_tokens = []

    class FakeEmailService:
        async def send_email(
            self,
            to_email,
            subject,
            text,
            html=None,
        ):
            marker = "token="

            if marker in text:
                token = (
                    text
                    .split(marker, 1)[1]
                    .split()[0]
                )

                sent_tokens.append(token)

            return True

    original_email_service = auth.EmailService
    original_token_urlsafe = auth.secrets.token_urlsafe

    generated_tokens = iter(
        [
            "TOKEN_A",
            "TOKEN_B",
        ]
    )

    try:
        auth.EmailService = FakeEmailService

        auth.secrets.token_urlsafe = (
            lambda n: next(generated_tokens)
        )

        payload = SimpleNamespace(
            email="user@example.com"
        )

        # =====================================================
        # FIRST RESET REQUEST
        # =====================================================

        response_a = await auth.forgot_password(
            payload=payload,
            request=request,
            db=db,
        )

        assert response_a["message"] == (
            "If an account with that email exists, "
            "a password reset link has been sent."
        )

        assert len(tokens) == 1
        assert sent_tokens == ["TOKEN_A"]

        first_token = tokens[0]

        # First token should initially be valid.
        assert first_token.used_at is None
        assert first_token.is_valid is True

        # =====================================================
        # SECOND RESET REQUEST
        # =====================================================

        response_b = await auth.forgot_password(
            payload=payload,
            request=request,
            db=db,
        )

        assert response_b["message"] == (
            "If an account with that email exists, "
            "a password reset link has been sent."
        )

        assert len(tokens) == 2
        assert sent_tokens == [
            "TOKEN_A",
            "TOKEN_B",
        ]

        first_token = tokens[0]
        second_token = tokens[1]

        # =====================================================
        # SECURITY ASSERTIONS
        # =====================================================

        # Old token must be invalidated.
        assert first_token.used_at is not None
        assert first_token.is_valid is False

        # New token must remain valid.
        assert second_token.used_at is None
        assert second_token.is_valid is True

        # Tokens must be different.
        assert first_token.token_hash != second_token.token_hash

    finally:
        # Restore patched objects.
        auth.EmailService = original_email_service
        auth.secrets.token_urlsafe = (
            original_token_urlsafe
        )