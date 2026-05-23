"""Unit tests for listings_write_service — create, update, end commands."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

pytestmark = [pytest.mark.unit, pytest.mark.service]

_USER_ID = UUID("00000000-0000-0000-0000-000000000002")
_APP_CODE = "au-store"
_TOKEN = "bearer-token-xyz"
_ITEM_ID = "v1|123456789|0"


def _make_item(item_id: str = _ITEM_ID):
    item = MagicMock()
    item.ItemID = item_id
    return item


def _make_auth_repo() -> AsyncMock:
    return AsyncMock()


def _make_selling_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.create_listing.return_value = {"item_id": _ITEM_ID, "status": "created"}
    repo.update_listing.return_value = {"item_id": _ITEM_ID, "status": "updated"}
    repo.delete_listing.return_value = {"item_id": _ITEM_ID, "status": "ended"}
    return repo


@pytest.fixture(autouse=True)
def _patch_resolve_token():
    with patch(
        "automana.core.services.app_integration.ebay.listings_write_service.resolve_token",
        new=AsyncMock(return_value=_TOKEN),
    ) as mock:
        yield mock


@pytest.fixture(autouse=True)
def _patch_invalidate_cache():
    with patch(
        "automana.core.services.app_integration.ebay.listings_write_service.invalidate_cache_pattern",
        new=AsyncMock(),
    ):
        yield


class TestCreateListing:
    async def test_idempotency_cache_hit_returns_cached_result(self):
        """Cache hit: returns stored result without calling the selling repository."""
        from automana.core.services.app_integration.ebay.listings_write_service import create_listing
        from automana.core.services.app_integration.ebay._idempotency import (
            InMemoryIdempotencyStore, set_idempotency_store,
        )

        cached_result = {"item_id": _ITEM_ID, "status": "created"}
        store = InMemoryIdempotencyStore()
        store.set_if_absent("idem-key-1", json.dumps(cached_result))
        set_idempotency_store(store)

        selling_repo = _make_selling_repo()
        result = await create_listing(
            auth_repository=_make_auth_repo(),
            selling_repository=selling_repo,
            user_id=_USER_ID,
            app_code=_APP_CODE,
            item=_make_item(),
            idempotency_key="idem-key-1",
        )

        assert result == cached_result
        selling_repo.create_listing.assert_not_called()

        set_idempotency_store(None)

    async def test_cache_miss_calls_repo_and_caches_result(self):
        """Cache miss: calls selling repository and stores result."""
        from automana.core.services.app_integration.ebay.listings_write_service import create_listing
        from automana.core.services.app_integration.ebay._idempotency import (
            InMemoryIdempotencyStore, set_idempotency_store,
        )

        store = InMemoryIdempotencyStore()
        set_idempotency_store(store)

        selling_repo = _make_selling_repo()
        result = await create_listing(
            auth_repository=_make_auth_repo(),
            selling_repository=selling_repo,
            user_id=_USER_ID,
            app_code=_APP_CODE,
            item=_make_item(),
            idempotency_key="idem-key-2",
        )

        assert result["status"] == "created"
        selling_repo.create_listing.assert_awaited_once()
        # Result must now be cached
        assert store.get("idem-key-2") is not None

        set_idempotency_store(None)

    async def test_missing_idempotency_key_raises_value_error(self):
        """Empty idempotency_key is rejected before any I/O."""
        from automana.core.services.app_integration.ebay.listings_write_service import create_listing

        with pytest.raises(ValueError, match="idempotency_key is required"):
            await create_listing(
                auth_repository=_make_auth_repo(),
                selling_repository=_make_selling_repo(),
                user_id=_USER_ID,
                app_code=_APP_CODE,
                item=_make_item(),
                idempotency_key="",
            )


class TestUpdateListing:
    async def test_calls_resolve_token(self, _patch_resolve_token):
        """resolve_token is called with correct user_id and app_code."""
        from automana.core.services.app_integration.ebay.listings_write_service import update_listing

        await update_listing(
            auth_repository=_make_auth_repo(),
            selling_repository=_make_selling_repo(),
            user_id=_USER_ID,
            app_code=_APP_CODE,
            item=_make_item(),
        )

        _patch_resolve_token.assert_awaited_once()
        call_kwargs = _patch_resolve_token.call_args
        assert call_kwargs.kwargs["user_id"] == _USER_ID
        assert call_kwargs.kwargs["app_code"] == _APP_CODE

    async def test_passes_token_in_payload(self, _patch_resolve_token):
        """Token from resolve_token is forwarded to the selling repository."""
        from automana.core.services.app_integration.ebay.listings_write_service import update_listing

        selling_repo = _make_selling_repo()
        await update_listing(
            auth_repository=_make_auth_repo(),
            selling_repository=selling_repo,
            user_id=_USER_ID,
            app_code=_APP_CODE,
            item=_make_item(),
        )

        payload = selling_repo.update_listing.call_args.args[0]
        assert payload["token"] == _TOKEN

    async def test_returns_repo_result(self):
        """Return value is the raw selling repository result."""
        from automana.core.services.app_integration.ebay.listings_write_service import update_listing

        selling_repo = _make_selling_repo()
        result = await update_listing(
            auth_repository=_make_auth_repo(),
            selling_repository=selling_repo,
            user_id=_USER_ID,
            app_code=_APP_CODE,
            item=_make_item(),
        )

        assert result == {"item_id": _ITEM_ID, "status": "updated"}


class TestEndListing:
    async def test_calls_resolve_token(self, _patch_resolve_token):
        """resolve_token is called before ending the listing."""
        from automana.core.services.app_integration.ebay.listings_write_service import end_listing

        await end_listing(
            auth_repository=_make_auth_repo(),
            selling_repository=_make_selling_repo(),
            user_id=_USER_ID,
            app_code=_APP_CODE,
            item_id=_ITEM_ID,
        )

        _patch_resolve_token.assert_awaited_once()

    async def test_passes_ending_reason_in_payload(self):
        """ending_reason is forwarded to the selling repository unchanged."""
        from automana.core.services.app_integration.ebay.listings_write_service import end_listing

        selling_repo = _make_selling_repo()
        await end_listing(
            auth_repository=_make_auth_repo(),
            selling_repository=selling_repo,
            user_id=_USER_ID,
            app_code=_APP_CODE,
            item_id=_ITEM_ID,
            ending_reason="LostOrBroken",
        )

        payload = selling_repo.delete_listing.call_args.args[0]
        assert payload["ending_reason"] == "LostOrBroken"
        assert payload["item_id"] == _ITEM_ID

    async def test_missing_item_id_raises_value_error(self):
        """Empty item_id is rejected before any I/O."""
        from automana.core.services.app_integration.ebay.listings_write_service import end_listing

        with pytest.raises(ValueError, match="item_id is required"):
            await end_listing(
                auth_repository=_make_auth_repo(),
                selling_repository=_make_selling_repo(),
                user_id=_USER_ID,
                app_code=_APP_CODE,
                item_id="",
            )

    async def test_default_ending_reason_is_not_available(self):
        """Default ending_reason is 'NotAvailable' per eBay convention."""
        from automana.core.services.app_integration.ebay.listings_write_service import end_listing

        selling_repo = _make_selling_repo()
        await end_listing(
            auth_repository=_make_auth_repo(),
            selling_repository=selling_repo,
            user_id=_USER_ID,
            app_code=_APP_CODE,
            item_id=_ITEM_ID,
        )

        payload = selling_repo.delete_listing.call_args.args[0]
        assert payload["ending_reason"] == "NotAvailable"
