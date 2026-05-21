import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

from automana.core.services.app_integration.ebay.scrape_sold_service import (
    _to_cents,
    _parse_sold_date,
    scrape_external_sold,
    _scrape_one_card,
)

CARD_ID = UUID("12345678-1234-5678-1234-567812345678")


def test_to_cents_string():
    assert _to_cents("3.50") == 350


def test_to_cents_none():
    assert _to_cents(None) is None


def test_to_cents_invalid():
    assert _to_cents("bad") is None


def test_parse_sold_date_iso():
    result = _parse_sold_date("2024-03-10T08:00:00Z")
    assert result.year == 2024 and result.month == 3


def test_parse_sold_date_none():
    before = datetime.now(timezone.utc)
    result = _parse_sold_date(None)
    after = datetime.now(timezone.utc)
    assert before <= result <= after


@pytest.mark.asyncio
async def test_scrape_external_sold_no_app_id():
    auth = AsyncMock()
    with patch(
        "automana.core.services.app_integration.ebay.scrape_sold_service.get_settings"
    ) as mock_settings:
        mock_settings.return_value.ebay_app_id = None
        result = await scrape_external_sold(
            auth_repository=auth,
            ebay_sales_repository=AsyncMock(),
            ebay_scrape_repository=AsyncMock(),
            card_repository=AsyncMock(),
            ebay_finding_repository=AsyncMock(),
        )
    assert result == {"scraped_items": 0}


@pytest.mark.asyncio
async def test_scrape_external_sold_no_active_users():
    auth = AsyncMock()
    auth.get_active_app_code_users = AsyncMock(return_value=[])
    with patch(
        "automana.core.services.app_integration.ebay.scrape_sold_service.get_settings"
    ) as mock_settings:
        mock_settings.return_value.ebay_app_id = "test-app-id"
        result = await scrape_external_sold(
            auth_repository=auth,
            ebay_sales_repository=AsyncMock(),
            ebay_scrape_repository=AsyncMock(),
            card_repository=AsyncMock(),
            ebay_finding_repository=AsyncMock(),
        )
    assert result == {"scraped_items": 0}


@pytest.mark.asyncio
async def test_scrape_one_card_returns_zero_for_unknown_card():
    card_repo = AsyncMock()
    card_repo.get = AsyncMock(return_value=None)

    count = await _scrape_one_card(
        card_version_id=CARD_ID,
        app_id="app-id",
        min_date=datetime.now(timezone.utc),
        limit_per_card=50,
        score_threshold=0.7,
        card_repository=card_repo,
        ebay_finding_repository=AsyncMock(),
        ebay_sales_repository=AsyncMock(),
        ebay_scrape_repository=AsyncMock(),
    )
    assert count == 0


@pytest.mark.asyncio
async def test_scrape_one_card_filters_low_score():
    card_repo = AsyncMock()
    card_repo.get = AsyncMock(return_value={"card_name": "Lightning Bolt", "set_code": "M10"})

    finding = AsyncMock()
    # Item with title that won't match "Lightning Bolt M10"
    finding.find_completed_items = AsyncMock(return_value=[
        {"item_id": "1", "title": "Counterspell XYZ MTG", "price": "2.00", "currency": "USD", "sold_date": None},
    ])

    sales = AsyncMock()
    scrape = AsyncMock()

    count = await _scrape_one_card(
        card_version_id=CARD_ID,
        app_id="app-id",
        min_date=datetime.now(timezone.utc),
        limit_per_card=50,
        score_threshold=0.7,
        card_repository=card_repo,
        ebay_finding_repository=finding,
        ebay_sales_repository=sales,
        ebay_scrape_repository=scrape,
    )
    assert count == 0
    scrape.insert_scraped_sold.assert_not_called()


@pytest.mark.asyncio
async def test_scrape_one_card_inserts_matching_item():
    card_repo = AsyncMock()
    card_repo.get = AsyncMock(return_value={"card_name": "Lightning Bolt", "set_code": "M10"})

    finding = AsyncMock()
    finding.find_completed_items = AsyncMock(return_value=[
        {
            "item_id": "item-1",
            "title": "Lightning Bolt M10 MTG",
            "price": "5.00",
            "currency": "USD",
            "sold_date": "2024-01-01T00:00:00Z",
        },
    ])

    sales = AsyncMock()
    sales.ensure_source_product = AsyncMock(return_value=42)
    scrape = AsyncMock()

    count = await _scrape_one_card(
        card_version_id=CARD_ID,
        app_id="app-id",
        min_date=datetime.now(timezone.utc),
        limit_per_card=50,
        score_threshold=0.7,
        card_repository=card_repo,
        ebay_finding_repository=finding,
        ebay_sales_repository=sales,
        ebay_scrape_repository=scrape,
    )
    assert count == 1
    scrape.insert_scraped_sold.assert_called_once()
    call_kwargs = scrape.insert_scraped_sold.call_args.kwargs
    assert call_kwargs["item_id"] == "item-1"
    assert call_kwargs["price_cents"] == 500
