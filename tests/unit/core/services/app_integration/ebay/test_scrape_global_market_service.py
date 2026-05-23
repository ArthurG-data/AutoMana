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
        source_product_id=42,
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
        source_product_id=42,
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
        source_product_id=42,
    )

    assert count == 0
    scrape_repo.insert_scraped_sold.assert_not_called()


@pytest.mark.asyncio
async def test_scrape_global_market_calls_ensure_product_before_source_product():
    """ensure_product must be called before ensure_source_product — critical order."""
    from automana.core.services.app_integration.ebay.scrape_global_market_service import scrape_global_market
    from unittest.mock import patch, AsyncMock, MagicMock
    from uuid import uuid4

    card_id = uuid4()
    mock_sales = AsyncMock()
    mock_sales.ensure_product = AsyncMock(return_value=uuid4())
    mock_sales.ensure_source_product = AsyncMock(return_value=99)
    mock_scrape = AsyncMock()
    mock_scrape.get_scrape_targets = AsyncMock(return_value=[card_id])
    mock_scrape.update_target_last_scraped = AsyncMock()
    mock_card = AsyncMock()
    mock_card.get_scrape_metadata = AsyncMock(return_value={
        "card_name": "Sheoldred, the Apocalypse",
        "set_code": "mh2",
        "frame_effects": [],
        "is_promo": False,
        "promo_types": [],
        "border_color_name": "black",
        "full_art": False,
    })
    mock_finding = AsyncMock()
    mock_finding.find_completed_items = AsyncMock(return_value=[])

    with patch(
        "automana.core.services.app_integration.ebay.scrape_global_market_service.get_settings",
        return_value=type("S", (), {"ebay_app_id": "FAKE-APP-ID"})(),
    ):
        await scrape_global_market(
            ebay_sales_repository=mock_sales,
            ebay_scrape_repository=mock_scrape,
            card_repository=mock_card,
            ebay_finding_repository=mock_finding,
        )

    mock_sales.ensure_product.assert_called_once_with(card_id)
    mock_sales.ensure_source_product.assert_called_once()
    # ensure_product must be called before ensure_source_product
    ensure_product_call_idx = [c[0] for c in mock_sales.method_calls].index("ensure_product")
    ensure_source_product_call_idx = [c[0] for c in mock_sales.method_calls].index("ensure_source_product")
    assert ensure_product_call_idx < ensure_source_product_call_idx


@pytest.mark.asyncio
async def test_scrape_global_market_stops_at_budget():
    """When api_calls reaches _API_DAILY_BUDGET, the outer loop breaks."""
    from automana.core.services.app_integration.ebay.scrape_global_market_service import scrape_global_market
    from unittest.mock import patch, AsyncMock
    from uuid import uuid4

    card_ids = [uuid4(), uuid4()]
    mock_sales = AsyncMock()
    mock_sales.ensure_product = AsyncMock(return_value=uuid4())
    mock_sales.ensure_source_product = AsyncMock(return_value=99)
    mock_scrape = AsyncMock()
    mock_scrape.get_scrape_targets = AsyncMock(return_value=card_ids)
    mock_scrape.update_target_last_scraped = AsyncMock()
    mock_card = AsyncMock()
    mock_card.get_scrape_metadata = AsyncMock(return_value={
        "card_name": "Sheoldred, the Apocalypse",
        "set_code": "mh2",
        "frame_effects": [],
        "is_promo": False,
        "promo_types": [],
        "border_color_name": "black",
        "full_art": False,
    })
    mock_finding = AsyncMock()
    mock_finding.find_completed_items = AsyncMock(return_value=[])

    with patch(
        "automana.core.services.app_integration.ebay.scrape_global_market_service.get_settings",
        return_value=type("S", (), {"ebay_app_id": "FAKE-APP-ID"})(),
    ), patch(
        "automana.core.services.app_integration.ebay.scrape_global_market_service._API_DAILY_BUDGET",
        3,
    ):
        result = await scrape_global_market(
            ebay_sales_repository=mock_sales,
            ebay_scrape_repository=mock_scrape,
            card_repository=mock_card,
            ebay_finding_repository=mock_finding,
        )

    assert mock_finding.find_completed_items.call_count == 3
    assert result["api_calls"] == 3


@pytest.mark.asyncio
async def test_scrape_global_market_warns_at_threshold(caplog):
    """A warning is logged when api_calls reaches the warn threshold."""
    import logging
    from automana.core.services.app_integration.ebay.scrape_global_market_service import scrape_global_market
    from unittest.mock import patch, AsyncMock
    from uuid import uuid4

    card_ids = [uuid4()]
    mock_sales = AsyncMock()
    mock_sales.ensure_product = AsyncMock(return_value=uuid4())
    mock_sales.ensure_source_product = AsyncMock(return_value=99)
    mock_scrape = AsyncMock()
    mock_scrape.get_scrape_targets = AsyncMock(return_value=card_ids)
    mock_scrape.update_target_last_scraped = AsyncMock()
    mock_card = AsyncMock()
    mock_card.get_scrape_metadata = AsyncMock(return_value={
        "card_name": "Sheoldred, the Apocalypse",
        "set_code": "mh2",
        "frame_effects": [],
        "is_promo": False,
        "promo_types": [],
        "border_color_name": "black",
        "full_art": False,
    })
    mock_finding = AsyncMock()
    mock_finding.find_completed_items = AsyncMock(return_value=[])

    # budget=4, threshold=0.75 → warn_at = round(4*0.75) = 3 → triggered on 3rd call (1 card × 3 marketplaces)
    with patch(
        "automana.core.services.app_integration.ebay.scrape_global_market_service.get_settings",
        return_value=type("S", (), {"ebay_app_id": "FAKE-APP-ID"})(),
    ), patch(
        "automana.core.services.app_integration.ebay.scrape_global_market_service._API_DAILY_BUDGET",
        4,
    ), patch(
        "automana.core.services.app_integration.ebay.scrape_global_market_service._API_WARN_THRESHOLD",
        0.75,
    ), caplog.at_level(logging.WARNING, logger="automana.core.services.app_integration.ebay.scrape_global_market_service"):
        await scrape_global_market(
            ebay_sales_repository=mock_sales,
            ebay_scrape_repository=mock_scrape,
            card_repository=mock_card,
            ebay_finding_repository=mock_finding,
        )

    assert any("scrape_global_market_api_budget_warning" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_scrape_global_market_result_includes_api_calls():
    """The return dict includes api_calls."""
    from automana.core.services.app_integration.ebay.scrape_global_market_service import scrape_global_market
    from unittest.mock import patch, AsyncMock
    from uuid import uuid4

    mock_sales = AsyncMock()
    mock_sales.ensure_product = AsyncMock(return_value=uuid4())
    mock_sales.ensure_source_product = AsyncMock(return_value=99)
    mock_scrape = AsyncMock()
    mock_scrape.get_scrape_targets = AsyncMock(return_value=[uuid4()])
    mock_scrape.update_target_last_scraped = AsyncMock()
    mock_card = AsyncMock()
    mock_card.get_scrape_metadata = AsyncMock(return_value={
        "card_name": "Sheoldred, the Apocalypse",
        "set_code": "mh2",
        "frame_effects": [],
        "is_promo": False,
        "promo_types": [],
        "border_color_name": "black",
        "full_art": False,
    })
    mock_finding = AsyncMock()
    mock_finding.find_completed_items = AsyncMock(return_value=[])

    with patch(
        "automana.core.services.app_integration.ebay.scrape_global_market_service.get_settings",
        return_value=type("S", (), {"ebay_app_id": "FAKE-APP-ID"})(),
    ):
        result = await scrape_global_market(
            ebay_sales_repository=mock_sales,
            ebay_scrape_repository=mock_scrape,
            card_repository=mock_card,
            ebay_finding_repository=mock_finding,
        )

    assert "api_calls" in result
    assert result["api_calls"] == 3  # 1 card × 3 marketplaces
