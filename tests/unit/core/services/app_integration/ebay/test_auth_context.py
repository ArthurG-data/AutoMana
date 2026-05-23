"""Unit tests for _auth_context.resolve_token."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

pytestmark = [pytest.mark.unit, pytest.mark.service]

_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
_APP_CODE = "test-app"
_ACCESS_TOKEN = "access-token-abc"


def _make_auth_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.fetch_refresh_token.return_value = MagicMock(
        refresh_token="refresh-tok",
        expires_at=None,
    )
    repo.get_app_settings.return_value = {
        "app_id": "APP-ID",
        "environment": "production",
        "decrypted_secret": "secret",
    }
    repo.get_app_scopes.return_value = ["https://api.ebay.com/oauth/api_scope"]
    repo.upsert_refresh_token = AsyncMock()
    return repo


@pytest.fixture(autouse=True)
def _patch_redis():
    redis_mock = AsyncMock()
    redis_mock.get.return_value = None  # cache miss by default
    redis_mock.setex = AsyncMock()
    with patch(
        "automana.core.services.app_integration.ebay._auth_context.get_redis_client",
        new=AsyncMock(return_value=redis_mock),
    ) as p:
        yield p, redis_mock


@pytest.fixture(autouse=True)
def _patch_api_repo():
    api_repo_mock = AsyncMock()
    api_repo_mock.exchange_refresh_token.return_value = {
        "access_token": _ACCESS_TOKEN,
        "expires_in": 7200,
    }
    with patch(
        "automana.core.repositories.app_integration.ebay.ApiAuth_repository.EbayAuthAPIRepository",
        return_value=api_repo_mock,
    ):
        yield api_repo_mock


class TestResolveToken:
    async def test_cache_hit_returns_token_without_repo(self, _patch_redis, _patch_api_repo):
        """Redis cache hit: returns token string and skips all repo calls."""
        _, redis_mock = _patch_redis
        redis_mock.get.return_value = json.dumps({"access_token": _ACCESS_TOKEN}).encode()

        from automana.core.services.app_integration.ebay._auth_context import resolve_token

        repo = _make_auth_repo()
        result = await resolve_token(repo, user_id=_USER_ID, app_code=_APP_CODE)

        assert result == _ACCESS_TOKEN
        repo.fetch_refresh_token.assert_not_called()

    async def test_cache_miss_fetches_and_returns_token(self, _patch_redis, _patch_api_repo):
        """Cache miss: fetches refresh token, exchanges it, returns access token."""
        from automana.core.services.app_integration.ebay._auth_context import resolve_token

        repo = _make_auth_repo()
        result = await resolve_token(repo, user_id=_USER_ID, app_code=_APP_CODE)

        assert result == _ACCESS_TOKEN
        repo.fetch_refresh_token.assert_awaited_once_with(user_id=_USER_ID, app_code=_APP_CODE)

    async def test_missing_refresh_token_raises_value_error(self, _patch_redis, _patch_api_repo):
        """No refresh token row in DB → ValueError (user hasn't completed OAuth)."""
        from automana.core.services.app_integration.ebay._auth_context import resolve_token

        repo = _make_auth_repo()
        repo.fetch_refresh_token.return_value = None

        with pytest.raises(ValueError, match="No valid eBay refresh token"):
            await resolve_token(repo, user_id=_USER_ID, app_code=_APP_CODE)

    async def test_empty_app_code_raises_value_error(self, _patch_redis, _patch_api_repo):
        """Empty app_code is rejected before any I/O."""
        from automana.core.services.app_integration.ebay._auth_context import resolve_token

        repo = _make_auth_repo()

        with pytest.raises(ValueError, match="app_code is required"):
            await resolve_token(repo, user_id=_USER_ID, app_code="")

    async def test_user_id_and_app_code_passed_through_unchanged(self, _patch_redis, _patch_api_repo):
        """user_id and app_code reach fetch_refresh_token without mutation."""
        from automana.core.services.app_integration.ebay._auth_context import resolve_token

        repo = _make_auth_repo()
        await resolve_token(repo, user_id=_USER_ID, app_code=_APP_CODE)

        call_kwargs = repo.fetch_refresh_token.call_args.kwargs
        assert call_kwargs["user_id"] == _USER_ID
        assert call_kwargs["app_code"] == _APP_CODE

    async def test_repo_exception_propagates(self, _patch_redis, _patch_api_repo):
        """Repository errors are not swallowed."""
        from automana.core.services.app_integration.ebay._auth_context import resolve_token

        repo = _make_auth_repo()
        repo.fetch_refresh_token.side_effect = RuntimeError("DB exploded")

        with pytest.raises(RuntimeError, match="DB exploded"):
            await resolve_token(repo, user_id=_USER_ID, app_code=_APP_CODE)
