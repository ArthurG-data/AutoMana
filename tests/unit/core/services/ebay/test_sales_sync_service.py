import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

from automana.core.services.app_integration.ebay.sales_sync_service import (
    _price_to_cents,
    _parse_sold_at,
    _resolve_card_version,
    track_active_listing,
    sync_own_sales,
)

CARD_ID = UUID("12345678-1234-5678-1234-567812345678")
USER_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
SOURCE_PRODUCT_ID = 42


def _repo():
    r = MagicMock()
    r.execute_query = AsyncMock()
    r.execute_command = AsyncMock()
    return r


# ── Pure helpers ──────────────────────────────────────────────────────────────

def test_price_to_cents_float_string():
    assert _price_to_cents("5.00") == 500


def test_price_to_cents_int():
    assert _price_to_cents(3) == 300


def test_price_to_cents_none():
    assert _price_to_cents(None) is None


def test_price_to_cents_invalid():
    assert _price_to_cents("N/A") is None


def test_parse_sold_at_iso():
    result = _parse_sold_at("2024-01-15T10:00:00Z")
    assert result.year == 2024
    assert result.month == 1


def test_parse_sold_at_none_returns_now():
    before = datetime.now(timezone.utc)
    result = _parse_sold_at(None)
    after = datetime.now(timezone.utc)
    assert before <= result <= after


# ── _resolve_card_version ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resolve_card_version_from_active_listing():
    ebay_sales = AsyncMock()
    ebay_sales.get_card_version_by_item = AsyncMock(return_value=CARD_ID)
    card_repo = AsyncMock()

    result = await _resolve_card_version("item-1", "Lightning Bolt", ebay_sales, card_repo)
    assert result == CARD_ID
    card_repo.suggest.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_card_version_falls_back_to_suggest():
    ebay_sales = AsyncMock()
    ebay_sales.get_card_version_by_item = AsyncMock(return_value=None)
    card_repo = AsyncMock()
    card_repo.suggest = AsyncMock(return_value=[
        {"card_version_id": str(CARD_ID), "card_name": "Lightning Bolt", "set_code": "M10"},
    ])

    result = await _resolve_card_version(None, "Lightning Bolt M10 MTG", ebay_sales, card_repo)
    assert result == CARD_ID


@pytest.mark.asyncio
async def test_resolve_card_version_returns_none_when_score_low():
    ebay_sales = AsyncMock()
    ebay_sales.get_card_version_by_item = AsyncMock(return_value=None)
    card_repo = AsyncMock()
    card_repo.suggest = AsyncMock(return_value=[
        {"card_version_id": str(CARD_ID), "card_name": "Counterspell", "set_code": "XYZ"},
    ])

    result = await _resolve_card_version(None, "Lightning Bolt MTG", ebay_sales, card_repo)
    assert result is None


# ── track_active_listing ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_track_active_listing_calls_upsert():
    ebay_sales = AsyncMock()
    await track_active_listing(
        ebay_sales_repository=ebay_sales,
        item_id="item-99",
        app_code="my-app",
        card_version_id=CARD_ID,
    )
    ebay_sales.upsert_active_listing.assert_called_once()
    kwargs = ebay_sales.upsert_active_listing.call_args.kwargs
    assert kwargs["item_id"] == "item-99"
    assert kwargs["app_code"] == "my-app"
    assert kwargs["card_version_id"] == CARD_ID


# ── sync_own_sales ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sync_own_sales_no_active_users():
    auth = AsyncMock()
    auth.get_active_app_code_users = AsyncMock(return_value=[])
    result = await sync_own_sales(
        auth_repository=auth,
        app_repository=AsyncMock(),
        ebay_sales_repository=AsyncMock(),
        card_repository=AsyncMock(),
        selling_repository=AsyncMock(),
    )
    assert result == {"synced_orders": 0}


@pytest.mark.asyncio
async def test_sync_own_sales_skips_user_on_error():
    auth = AsyncMock()
    auth.get_active_app_code_users = AsyncMock(return_value=[
        {"user_id": str(USER_ID), "app_code": "my-app"},
    ])
    auth.get_environment = AsyncMock(return_value="production")

    selling = AsyncMock()
    selling.get_history = AsyncMock(side_effect=RuntimeError("API down"))

    result = await sync_own_sales(
        auth_repository=auth,
        app_repository=AsyncMock(),
        ebay_sales_repository=AsyncMock(),
        card_repository=AsyncMock(),
        selling_repository=selling,
    )
    # User errored but function continues; count is 0 for this user
    assert isinstance(result, dict)
