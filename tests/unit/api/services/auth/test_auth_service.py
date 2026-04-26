"""
Tests for automana.api.services.auth.auth_service

Bug 1 — login calls create_access_token with settings.secret_key (missing attribute);
         the correct field is settings.jwt_secret_key.
Bug 3 — login unpacks create_new_session's dict by iterating keys, not values:
         `session_id, refresh_token = await create_new_session(...)`
         iterates {'session_id': <uuid>, 'refresh_token': <str>} and assigns
         the key *names* ('session_id', 'refresh_token') to the variables
         instead of the actual UUID and token string.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from automana.api.services.auth.auth_service import login
from automana.api.services.auth.auth import decode_access_token
from automana.api.schemas.user_management.user import UserInDB

pytestmark = pytest.mark.unit

_JWT_SECRET = "test-jwt-secret-unit"
_ALGO = "HS256"


class _StrictSettings:
    """Has jwt_secret_key but no secret_key — any access to secret_key raises AttributeError."""
    jwt_secret_key = _JWT_SECRET
    jwt_algorithm = _ALGO
    encrypt_algorithm = _ALGO
    access_token_expiry = 30


def _make_user(username: str = "alice") -> MagicMock:
    user = MagicMock(spec=UserInDB)
    user.unique_id = uuid4()
    user.username = username
    return user


# ---------------------------------------------------------------------------
# Bug 3 — login correctly unpacks dict values (not dict keys)
# ---------------------------------------------------------------------------

class TestLoginDictUnpack:
    async def test_session_id_in_result_is_uuid_string_not_dict_key(
        self, monkeypatch, mock_session_repository, mock_user_repository
    ):
        """login() must read session_id from the dict VALUE returned by create_new_session.

        Before fix: session_id = 'session_id' (the string key name).
        After fix:  session_id = str(known_uuid).
        """
        known_uuid = uuid4()
        known_token = "actual-refresh-token-value"

        monkeypatch.setattr(
            "automana.api.services.auth.auth_service.get_general_settings",
            lambda: _StrictSettings(),
        )
        monkeypatch.setattr(
            "automana.api.services.auth.auth_service.create_new_session",
            AsyncMock(return_value={"session_id": known_uuid, "refresh_token": known_token}),
        )
        monkeypatch.setattr(
            "automana.api.services.auth.auth_service.authenticate_user",
            AsyncMock(return_value=_make_user()),
        )
        mock_session_repository.get_by_user_id = AsyncMock(return_value=[])

        result = await login(
            user_repository=mock_user_repository,
            session_repository=mock_session_repository,
            username="alice",
            password="any",
            ip_address="127.0.0.1",
            user_agent="pytest",
        )

        assert result.get("session_id") == str(known_uuid), (
            f"Expected '{known_uuid}', got '{result.get('session_id')}' — "
            "dict keys were iterated instead of values"
        )

    async def test_refresh_token_in_result_is_token_value_not_dict_key(
        self, monkeypatch, mock_session_repository, mock_user_repository
    ):
        """login() must read refresh_token from the dict VALUE, not the key name.

        Before fix: refresh_token = 'refresh_token' (the string key name).
        After fix:  refresh_token = 'actual-refresh-token-value'.
        """
        known_uuid = uuid4()
        known_token = "actual-refresh-token-value"

        monkeypatch.setattr(
            "automana.api.services.auth.auth_service.get_general_settings",
            lambda: _StrictSettings(),
        )
        monkeypatch.setattr(
            "automana.api.services.auth.auth_service.create_new_session",
            AsyncMock(return_value={"session_id": known_uuid, "refresh_token": known_token}),
        )
        monkeypatch.setattr(
            "automana.api.services.auth.auth_service.authenticate_user",
            AsyncMock(return_value=_make_user()),
        )
        mock_session_repository.get_by_user_id = AsyncMock(return_value=[])

        result = await login(
            user_repository=mock_user_repository,
            session_repository=mock_session_repository,
            username="alice",
            password="any",
            ip_address="127.0.0.1",
            user_agent="pytest",
        )

        assert result.get("refresh_token") == known_token, (
            f"Expected '{known_token}', got '{result.get('refresh_token')}' — "
            "dict keys were iterated instead of values"
        )


# ---------------------------------------------------------------------------
# Bug 1 — login access token signed with jwt_secret_key
# ---------------------------------------------------------------------------

class TestLoginAccessTokenSigning:
    async def test_access_token_decodable_with_jwt_secret_key(
        self, monkeypatch, mock_session_repository, mock_user_repository
    ):
        """login() must pass settings.jwt_secret_key to create_access_token.

        Before fix: settings.secret_key raises AttributeError (field missing on Settings).
        After fix:  access_token is present and decodable with jwt_secret_key.
        """
        known_uuid = uuid4()

        monkeypatch.setattr(
            "automana.api.services.auth.auth_service.get_general_settings",
            lambda: _StrictSettings(),
        )
        monkeypatch.setattr(
            "automana.api.services.auth.auth_service.create_new_session",
            AsyncMock(return_value={"session_id": known_uuid, "refresh_token": "rt"}),
        )
        monkeypatch.setattr(
            "automana.api.services.auth.auth_service.authenticate_user",
            AsyncMock(return_value=_make_user("alice")),
        )
        mock_session_repository.get_by_user_id = AsyncMock(return_value=[])

        result = await login(
            user_repository=mock_user_repository,
            session_repository=mock_session_repository,
            username="alice",
            password="any",
            ip_address="127.0.0.1",
            user_agent="pytest",
        )

        assert "access_token" in result, f"Expected access_token in result, got: {result}"
        decoded = decode_access_token(result["access_token"], _JWT_SECRET, _ALGO)
        assert decoded["sub"] == "alice"
