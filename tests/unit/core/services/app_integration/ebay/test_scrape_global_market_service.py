import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from automana.core.services.app_integration.ebay.scrape_global_market_service import (
    _scrape_one_card,
)


def _make_item(title, price=5.0, currency="USD", condition=None, item_id=None):
    return {
        "item_id": item_id or "ITEM123",
        "title": title,
        "price": price,
        "currency": currency,
        "condition": condition,
        "sold_date": "2026-05-20T12:00:00.000Z",
    }


@pytest.mark.asyncio
async def test_scrape_one_card_inserts_foil_nm_correctly():
    card_version_id = uuid4()
    card = {
        "card_name": "Sheoldred, the Apocalypse",
        "set_code": "mh2",
        "frame_effects": [],
        "is_promo": False,
        "promo_types": [],
        "border_color_name": "black",
        "full_art": False,
    }
    # Include all name tokens so score_title gives full 0.50 name bonus + 0.20 set + 0.15 foil = 0.85
    items = [_make_item("Sheoldred the Apocalypse MH2 Foil NM MTG", condition="Near Mint or Better")]
    sales_repo = AsyncMock()
    sales_repo.ensure_product = AsyncMock(return_value=uuid4())
    sales_repo.ensure_source_product = AsyncMock(return_value=42)
    scrape_repo = AsyncMock()
    finding_repo = AsyncMock()
    finding_repo.find_completed_items = AsyncMock(return_value=items)

    count = await _scrape_one_card(
        card_version_id=card_version_id,
        card=card,
        app_id="APP-ID",
        marketplace="EBAY-US",
        min_date=MagicMock(),
        limit_per_card=50,
        score_threshold=0.7,
        ebay_sales_repository=sales_repo,
        ebay_scrape_repository=scrape_repo,
        ebay_finding_repository=finding_repo,
    )

    assert count == 1
    call_kwargs = scrape_repo.insert_scraped_sold.call_args.kwargs
    assert call_kwargs["finish_id"] == 2          # FOIL
    assert call_kwargs["condition_id"] == 1        # NM
    assert call_kwargs["marketplace_id"] == "EBAY-US"
    assert call_kwargs["currency"] == "USD"


@pytest.mark.asyncio
async def test_scrape_one_card_skips_low_score():
    card_version_id = uuid4()
    card = {
        "card_name": "Sheoldred, the Apocalypse",
        "set_code": "mh2",
        "frame_effects": [],
        "is_promo": False,
        "promo_types": [],
        "border_color_name": "black",
        "full_art": False,
    }
    # Title completely unrelated — will score < 0.7
    items = [_make_item("Random Pokemon Card Charizard Holo")]
    sales_repo = AsyncMock()
    scrape_repo = AsyncMock()
    finding_repo = AsyncMock()
    finding_repo.find_completed_items = AsyncMock(return_value=items)

    count = await _scrape_one_card(
        card_version_id=card_version_id,
        card=card,
        app_id="APP-ID",
        marketplace="EBAY-US",
        min_date=MagicMock(),
        limit_per_card=50,
        score_threshold=0.7,
        ebay_sales_repository=sales_repo,
        ebay_scrape_repository=scrape_repo,
        ebay_finding_repository=finding_repo,
    )

    assert count == 0
    scrape_repo.insert_scraped_sold.assert_not_called()


@pytest.mark.asyncio
async def test_scrape_one_card_skips_frame_conflict():
    """Title says 'showcase' but card has no frame effects → conflict → skip."""
    card_version_id = uuid4()
    card = {
        "card_name": "Sheoldred, the Apocalypse",
        "set_code": "mh2",
        "frame_effects": [],          # regular version
        "is_promo": False,
        "promo_types": [],
        "border_color_name": "black",
        "full_art": False,
    }
    # Include all name tokens so it scores high enough to pass score gate, then hits frame conflict
    items = [_make_item("Sheoldred the Apocalypse MH2 Showcase Foil NM MTG")]
    sales_repo = AsyncMock()
    sales_repo.ensure_product = AsyncMock(return_value=uuid4())
    sales_repo.ensure_source_product = AsyncMock(return_value=42)
    scrape_repo = AsyncMock()
    finding_repo = AsyncMock()
    finding_repo.find_completed_items = AsyncMock(return_value=items)

    count = await _scrape_one_card(
        card_version_id=card_version_id,
        card=card,
        app_id="APP-ID",
        marketplace="EBAY-US",
        min_date=MagicMock(),
        limit_per_card=50,
        score_threshold=0.7,
        ebay_sales_repository=sales_repo,
        ebay_scrape_repository=scrape_repo,
        ebay_finding_repository=finding_repo,
    )

    assert count == 0
    scrape_repo.insert_scraped_sold.assert_not_called()
