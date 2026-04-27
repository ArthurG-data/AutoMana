"""
Tests for automana.api.services.auth.session_service

Bug 1 — create_new_session and rotate_session_token access settings.secret_key
         (attribute does not exist on Settings); correct field is jwt_secret_key.
Bug 2 — get_user_from_session is never registered with @ServiceRegistry.register,
         so every cookie-authenticated endpoint raises a service-not-found error.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from datetime import datetime, timezone, timedelta

from automana.api.services.auth.session_service import create_new_session, rotate_session_token
from automana.api.services.auth.auth import decode_access_token
from automana.api.schemas.user_management.user import UserInDB
from automana.core.service_registry import ServiceRegistry

pytestmark = pytest.mark.unit

_JWT_SECRET = "test-jwt-secret-unit"
_ALGO = "HS256"


class _StrictSettings:
    """Settings substitute with jwt_secret_key and jwt_algorithm but no secret_key.

    Any access to settings.secret_key raises AttributeError, proving the code
    uses the correct field.
    """
    jwt_secret_key = _JWT_SECRET
    jwt_algorithm = _ALGO


# ---------------------------------------------------------------------------
# Bug 2 — service registration
# ---------------------------------------------------------------------------

class TestGetUserFromSessionRegistration:
    def test_is_registered_in_service_registry(self):
        import automana.api.services.auth.session_service  # noqa: F401 — trigger decorator
        config = ServiceRegistry.get("auth.session.get_user_from_session")
        assert config is not None, (
            "get_user_from_session must be decorated with "
            "@ServiceRegistry.register('auth.session.get_user_from_session')"
        )

    def test_registration_declares_session_and_user_repositories(self):
        import automana.api.services.auth.session_service  # noqa: F401
        config = ServiceRegistry.get("auth.session.get_user_from_session")
        assert config is not None
        assert "session" in config.db_repositories
        assert "user" in config.db_repositories


# ---------------------------------------------------------------------------
# Bug 1 — create_new_session uses jwt_secret_key
# ---------------------------------------------------------------------------

class TestCreateNewSessionTokenSigning:
    async def test_refresh_token_decodable_with_jwt_secret_key(
        self, monkeypatch, mock_session_repository
    ):
        """create_new_session must sign the refresh token with settings.jwt_secret_key.

        Before fix: settings.secret_key raises AttributeError (field missing).
        After fix:  token is signed with jwt_secret_key and is decodable.
        """
        monkeypatch.setattr(
            "automana.api.services.auth.session_service.get_general_settings",
            lambda: _StrictSettings(),
        )
        session_uuid = uuid4()
        mock_session_repository.add = AsyncMock(return_value=None)
        mock_session_repository.get = AsyncMock(
            return_value=[{"session_id": session_uuid, "refresh_token": "db-placeholder"}]
        )

        user = MagicMock(spec=UserInDB)
        user.unique_id = uuid4()
        user.username = "alice"

        result = await create_new_session(
            mock_session_repository,
            user,
            "10.0.0.1",
            "pytest-agent/1.0",
            datetime.now(timezone.utc) + timedelta(days=7),
        )

        decoded = decode_access_token(result["refresh_token"], _JWT_SECRET, _ALGO)
        assert "session_id" in decoded


# ---------------------------------------------------------------------------
# Bug 1 — rotate_session_token uses jwt_secret_key
# ---------------------------------------------------------------------------

class TestRotateSessionTokenSigning:
    async def test_rotated_token_decodable_with_jwt_secret_key(
        self, monkeypatch, mock_session_repository
    ):
        """rotate_session_token must sign the new refresh token with settings.jwt_secret_key.

        Before fix: settings.secret_key raises AttributeError.
        After fix:  token is decodable with jwt_secret_key.
        """
        monkeypatch.setattr(
            "automana.api.services.auth.session_service.get_general_settings",
            lambda: _StrictSettings(),
        )
        mock_session_repository.rotate_token = AsyncMock(return_value=None)

        result = await rotate_session_token(
            mock_session_repository,
            session_id=uuid4(),
            refresh_token="old-token",
            expire_time=datetime.now(timezone.utc) + timedelta(days=7),
            token_id=uuid4(),
        )

        decoded = decode_access_token(result["refresh_token"], _JWT_SECRET, _ALGO)
        assert "session_id" in decoded
