import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone
from uuid import UUID

from automana.core.services.app_integration.ebay.market_price_service import (
    fetch_card_market_price,
    _browse_items_to_price_points,
    _finding_items_to_price_points,
)
from automana.core.models.ebay.market_price import PricePoint

_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
_APP_CODE = "test-app"
_APP_SETTINGS = {
    "environment": "production",
    "client_id": "CLIENT-ID",
    "client_secret": "CLIENT-SECRET",
    "dev_id": "DEV-ID",
    "ru_name": None,
}


# ── helper parsers ──────────────────────────────────────────────────────────

def test_browse_items_to_price_points_basic():
    raw = {
        "itemSummaries": [
            {
                "itemId": "v1|999|0",
                "title": "Sheoldred Apocalypse NM",
                "price": {"value": "42.00", "currency": "AUD"},
                "condition": "Near Mint",
                "itemWebUrl": "https://ebay.com.au/itm/999",
            }
        ]
    }
    points = _browse_items_to_price_points(raw)
    assert len(points) == 1
    assert points[0].item_id == "v1|999|0"
    assert points[0].price == 42.0
    assert points[0].currency == "AUD"
    assert points[0].sold_date is None


def test_browse_items_to_price_points_missing_price_defaults_to_zero():
    raw = {"itemSummaries": [{"itemId": "x", "title": "bad", "price": {}}]}
    points = _browse_items_to_price_points(raw)
    # price value is 0.0 — we keep it; the relevance filter will handle it
    assert points[0].price == 0.0


def test_finding_items_to_price_points_basic():
    raw_items = [
        {
            "item_id": "111",
            "title": "Sheoldred Apocalypse NM DMR MTG",
            "price": 45.0,
            "currency": "AUD",
            "condition": "Very Good",
            "url": "https://www.ebay.com.au/itm/111",
            "sold_date": "2026-01-01T10:00:00.000Z",
        }
    ]
    points = _finding_items_to_price_points(raw_items)
    assert len(points) == 1
    assert points[0].item_id == "111"
    assert points[0].price == 45.0
    assert points[0].sold_date is not None


# ── full service ────────────────────────────────────────────────────────────

@pytest.fixture
def auth_repo():
    repo = AsyncMock()
    repo.get_app_settings = AsyncMock(return_value=_APP_SETTINGS)
    return repo


@pytest.fixture
def browse_repo():
    repo = AsyncMock()
    repo.environment = "production"
    repo.search_items = AsyncMock(return_value={
        "itemSummaries": [
            {
                "itemId": "v1|003|0",
                "title": "Sheoldred the Apocalypse DMR NM MTG",
                "price": {"value": "50.00", "currency": "AUD"},
                "condition": "Near Mint",
                "itemWebUrl": "https://ebay.com.au/itm/003",
            }
        ]
    })
    return repo


async def test_service_returns_card_market_data(auth_repo, browse_repo):
    with patch(
        "automana.core.services.app_integration.ebay.market_price_service.resolve_app_token",
        new=AsyncMock(return_value="fake-token"),
    ):
        result = await fetch_card_market_price(
            auth_repository=auth_repo,
            search_repository=browse_repo,
            card_name="Sheoldred the Apocalypse",
            user_id=_USER_ID,
            app_code=_APP_CODE,
            set_code="DMR",
            condition_id=None,
            is_foil=None,
            frame=None,
            days_back=30,
            limit=50,
            match_threshold=0.6,
        )

    assert result.card_name == "Sheoldred the Apocalypse"
    assert result.set_code == "DMR"
    # Finding API was decommissioned Feb 2025; sold is always empty
    assert result.sold == []
    assert result.sold_aggregates.count == 0
    assert result.suggested_price is None
    # Browse API returns one active listing
    assert result.active_aggregates.count >= 1


async def test_service_active_aggregates_computed_from_browse(auth_repo, browse_repo):
    """Active price aggregates are populated from Browse API results."""
    with patch(
        "automana.core.services.app_integration.ebay.market_price_service.resolve_app_token",
        new=AsyncMock(return_value="fake-token"),
    ):
        result = await fetch_card_market_price(
            auth_repository=auth_repo,
            search_repository=browse_repo,
            card_name="Sheoldred the Apocalypse",
            user_id=_USER_ID,
            app_code=_APP_CODE,
            set_code="DMR",
            condition_id=None,
            is_foil=None,
            frame=None,
            days_back=30,
            limit=50,
            match_threshold=0.4,
        )
    assert result.active_aggregates.count == 1
    assert result.active_aggregates.median == 50.0


async def test_service_browse_api_failure_returns_empty_active(auth_repo):
    failing_browse = AsyncMock()
    failing_browse.environment = "production"
    failing_browse.search_items = AsyncMock(side_effect=Exception("Browse API down"))

    with patch(
        "automana.core.services.app_integration.ebay.market_price_service.resolve_app_token",
        new=AsyncMock(return_value="fake-token"),
    ):
        result = await fetch_card_market_price(
            auth_repository=auth_repo,
            search_repository=failing_browse,
            card_name="Sheoldred the Apocalypse",
            user_id=_USER_ID,
            app_code=_APP_CODE,
            set_code="DMR",
            condition_id=None,
            is_foil=None,
            frame=None,
            days_back=30,
            limit=50,
            match_threshold=0.0,
        )

    assert result.sold == []
    assert result.active == []
    assert result.suggested_price is None
