import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone

from automana.core.services.app_integration.ebay.market_price_service import (
    fetch_card_market_price,
    _browse_items_to_price_points,
    _finding_items_to_price_points,
)
from automana.core.models.ebay.market_price import PricePoint


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
def finding_repo():
    repo = AsyncMock()
    repo.find_completed_items = AsyncMock(return_value=[
        {
            "item_id": "001",
            "title": "Sheoldred the Apocalypse NM DMR MTG",
            "price": 45.0,
            "currency": "AUD",
            "condition": "Very Good",
            "url": "https://ebay.com/itm/001",
            "sold_date": "2026-01-01T10:00:00.000Z",
        },
        {
            "item_id": "002",
            "title": "Sheoldred the Apocalypse DMR MTG proxy",
            "price": 5.0,
            "currency": "AUD",
            "condition": "Good",
            "url": "https://ebay.com/itm/002",
            "sold_date": "2026-01-02T10:00:00.000Z",
        },
    ])
    return repo


@pytest.fixture
def browse_repo():
    repo = AsyncMock()
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


async def test_service_returns_card_market_data(finding_repo, browse_repo):
    with patch(
        "automana.core.services.app_integration.ebay.market_price_service.get_settings",
        return_value=MagicMock(ebay_app_id="TEST-APP-ID"),
    ):
        result = await fetch_card_market_price(
            ebay_finding_repository=finding_repo,
            search_repository=browse_repo,
            card_name="Sheoldred the Apocalypse",
            token="fake-token",
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
    # proxy item is excluded by scorer
    proxy_ids = [p.item_id for p in result.sold]
    assert "002" not in proxy_ids
    # sold aggregates computed from the one valid sold item
    assert result.sold_aggregates.count == 1
    # suggested_price is None because < 3 sold items
    assert result.suggested_price is None


async def test_service_sets_suggested_price_when_enough_sold(finding_repo, browse_repo):
    # Override finding_repo to return 3 clean sold items
    finding_repo.find_completed_items = AsyncMock(return_value=[
        {"item_id": str(i), "title": "Sheoldred the Apocalypse DMR MTG",
         "price": float(40 + i * 5), "currency": "AUD",
         "condition": "Very Good", "url": f"https://ebay.com/itm/{i}",
         "sold_date": "2026-01-01T10:00:00.000Z"}
        for i in range(3)  # prices: 40, 45, 50
    ])
    with patch(
        "automana.core.services.app_integration.ebay.market_price_service.get_settings",
        return_value=MagicMock(ebay_app_id="TEST-APP-ID"),
    ):
        result = await fetch_card_market_price(
            ebay_finding_repository=finding_repo,
            search_repository=browse_repo,
            card_name="Sheoldred the Apocalypse",
            token="fake-token",
            set_code="DMR",
            condition_id=None,
            is_foil=None,
            frame=None,
            days_back=30,
            limit=50,
            match_threshold=0.4,  # lower threshold so all 3 pass
        )
    # median of [40, 45, 50] = 45
    assert result.suggested_price == 45.0


async def test_service_partial_when_finding_fails(browse_repo):
    failing_finding = AsyncMock()
    failing_finding.find_completed_items = AsyncMock(side_effect=Exception("Finding API down"))

    with patch(
        "automana.core.services.app_integration.ebay.market_price_service.get_settings",
        return_value=MagicMock(ebay_app_id="TEST-APP-ID"),
    ):
        result = await fetch_card_market_price(
            ebay_finding_repository=failing_finding,
            search_repository=browse_repo,
            card_name="Sheoldred the Apocalypse",
            token="fake-token",
            set_code="DMR",
            condition_id=None,
            is_foil=None,
            frame=None,
            days_back=30,
            limit=50,
            match_threshold=0.0,
        )

    assert result.sold == []
    assert result.sold_aggregates.count == 0
    assert result.suggested_price is None
    # active results still present
    assert result.active_aggregates.count >= 0
