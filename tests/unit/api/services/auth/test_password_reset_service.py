import hashlib
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

pytestmark = [pytest.mark.unit, pytest.mark.service]


def _make_user(email="user@example.com"):
    return {
        "unique_id": uuid4(),
        "email": email,
        "username": "testuser",
        "disabled": False,
    }


def _make_token_row(user_id, raw_token, minutes_until_expiry=30):
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    return {
        "id": uuid4(),
        "user_id": user_id,
        "token_hash": token_hash,
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=minutes_until_expiry),
        "used_at": None,
    }


class TestRequestReset:
    async def test_unknown_email_returns_ok_silently(self):
        """No error raised when email not found (prevents user enumeration)."""
        from automana.api.services.auth.password_reset_service import request_reset

        user_repo = AsyncMock()
        user_repo.get_by_email.return_value = None
        reset_repo = AsyncMock()

        result = await request_reset(
            user_repository=user_repo,
            password_reset_repository=reset_repo,
            email="nobody@example.com",
        )

        assert result == {"status": "ok"}
        reset_repo.invalidate_for_user.assert_not_called()
        reset_repo.create.assert_not_called()

    async def test_known_email_creates_token_and_sends_email(self):
        """Creates a token and calls EmailService when email exists."""
        from automana.api.services.auth.password_reset_service import request_reset

        user = _make_user()
        user_repo = AsyncMock()
        user_repo.get_by_email.return_value = user
        reset_repo = AsyncMock()
        reset_repo.create.return_value = {"id": uuid4()}

        with patch(
            "automana.api.services.auth.password_reset_service.EmailService.send_reset_email"
        ) as mock_send:
            result = await request_reset(
                user_repository=user_repo,
                password_reset_repository=reset_repo,
                email=user["email"],
            )

        assert result == {"status": "ok"}
        reset_repo.invalidate_for_user.assert_called_once_with(user["unique_id"])
        reset_repo.create.assert_called_once()
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["to"] == user["email"]
        assert len(call_kwargs["token"]) > 0


class TestResetPassword:
    async def test_invalid_token_raises_domain_error(self):
        """Raises InvalidResetTokenError (not HTTPException) when token not found."""
        from automana.api.services.auth.password_reset_service import reset_password
        from automana.core.exceptions.service_layer_exceptions.user_management.user_exceptions import InvalidResetTokenError

        user_repo = AsyncMock()
        reset_repo = AsyncMock()
        reset_repo.get_by_token_hash.return_value = None
        session_repo = AsyncMock()

        with pytest.raises(InvalidResetTokenError):
            await reset_password(
                user_repository=user_repo,
                password_reset_repository=reset_repo,
                session_repository=session_repo,
                token="badtoken",
                new_password="NewPass123!",
            )

    async def test_expired_token_raises_domain_error(self):
        """Raises InvalidResetTokenError when token is past its expiry."""
        from automana.api.services.auth.password_reset_service import reset_password
        from automana.core.exceptions.service_layer_exceptions.user_management.user_exceptions import InvalidResetTokenError

        user_id = uuid4()
        expired_row = {
            "id": uuid4(),
            "user_id": user_id,
            "token_hash": "any",
            "expires_at": datetime.now(timezone.utc) - timedelta(minutes=1),
            "used_at": None,
        }
        user_repo = AsyncMock()
        reset_repo = AsyncMock()
        reset_repo.get_by_token_hash.return_value = expired_row
        session_repo = AsyncMock()

        with pytest.raises(InvalidResetTokenError):
            await reset_password(
                user_repository=user_repo,
                password_reset_repository=reset_repo,
                session_repository=session_repo,
                token="expiredtoken",
                new_password="NewPass123!",
            )

    async def test_already_used_token_raises_domain_error(self):
        """Raises InvalidResetTokenError when token was already consumed."""
        from automana.api.services.auth.password_reset_service import reset_password
        from automana.core.exceptions.service_layer_exceptions.user_management.user_exceptions import InvalidResetTokenError

        user_id = uuid4()
        used_row = {
            "id": uuid4(),
            "user_id": user_id,
            "token_hash": "any",
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=15),
            "used_at": datetime.now(timezone.utc) - timedelta(minutes=5),
        }
        user_repo = AsyncMock()
        reset_repo = AsyncMock()
        reset_repo.get_by_token_hash.return_value = used_row
        session_repo = AsyncMock()

        with pytest.raises(InvalidResetTokenError):
            await reset_password(
                user_repository=user_repo,
                password_reset_repository=reset_repo,
                session_repository=session_repo,
                token="usedtoken",
                new_password="NewPass123!",
            )

    async def test_valid_token_updates_password_and_invalidates_sessions(self):
        """Valid token → password updated, token marked used, sessions cleared."""
        from automana.api.services.auth.password_reset_service import reset_password

        user_id = uuid4()
        raw_token = "validtoken"
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        token_row = {
            "id": uuid4(),
            "user_id": user_id,
            "token_hash": token_hash,
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=25),
            "used_at": None,
        }
        user_repo = AsyncMock()
        reset_repo = AsyncMock()
        reset_repo.get_by_token_hash.return_value = token_row
        session_repo = AsyncMock()

        result = await reset_password(
            user_repository=user_repo,
            password_reset_repository=reset_repo,
            session_repository=session_repo,
            token=raw_token,
            new_password="NewPass123!",
        )

        assert result == {"status": "ok"}
        user_repo.update_password.assert_called_once()
        update_call = user_repo.update_password.call_args
        assert update_call.kwargs["user_id"] == user_id
        # Stored password must be a bcrypt hash, not plaintext
        assert update_call.kwargs["hashed_password"] != "NewPass123!"
        assert update_call.kwargs["hashed_password"].startswith("$2b$")
        reset_repo.mark_used.assert_called_once_with(token_row["id"])
        session_repo.invalidate_all_for_user.assert_called_once_with(user_id)
