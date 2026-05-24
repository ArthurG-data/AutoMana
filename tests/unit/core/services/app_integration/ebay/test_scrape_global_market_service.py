import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from automana.core.services.app_integration.ebay.scrape_global_market_service import (
    _scrape_one_card,
)

_MODULE = "automana.core.services.app_integration.ebay.scrape_global_market_service"


def _make_item(title, price=5.0, currency="USD", condition=None, item_id=None):
    return {
        "item_id": item_id or "ITEM123",
        "title": title,
        "price": price,
        "currency": currency,
        "condition": condition,
        "sold_date": "2026-05-20T12:00:00.000Z",
    }


def _make_redis_mock(exhausted: bool = False):
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=b"5000" if exhausted else None)
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.aclose = AsyncMock()
    return mock_redis


def _fake_watchlist_path():
    return MagicMock(exists=MagicMock(return_value=False))


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
    scrape_repo = AsyncMock()
    finding_repo = AsyncMock()
    finding_repo.find_completed_items = AsyncMock(return_value=items)
    redis_client = _make_redis_mock()

    with patch(f"{_MODULE}.watchlist_path", return_value=_fake_watchlist_path()), \
         patch(f"{_MODULE}.write_items_to_json"):
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
            today="2026-05-24",
            redis_client=redis_client,
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
    scrape_repo = AsyncMock()
    finding_repo = AsyncMock()
    finding_repo.find_completed_items = AsyncMock(return_value=items)
    redis_client = _make_redis_mock()

    with patch(f"{_MODULE}.watchlist_path", return_value=_fake_watchlist_path()), \
         patch(f"{_MODULE}.write_items_to_json"):
        count = await _scrape_one_card(
            card_version_id=card_version_id,
            card=card,
            app_id="APP-ID",
            marketplace="EBAY-US",
            min_date=MagicMock(),
            limit_per_card=50,
            score_threshold=0.7,
            ebay_sales_repository=AsyncMock(),
            ebay_scrape_repository=scrape_repo,
            ebay_finding_repository=finding_repo,
            source_product_id=42,
            today="2026-05-24",
            redis_client=redis_client,
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
    scrape_repo = AsyncMock()
    finding_repo = AsyncMock()
    finding_repo.find_completed_items = AsyncMock(return_value=items)
    redis_client = _make_redis_mock()

    with patch(f"{_MODULE}.watchlist_path", return_value=_fake_watchlist_path()), \
         patch(f"{_MODULE}.write_items_to_json"):
        count = await _scrape_one_card(
            card_version_id=card_version_id,
            card=card,
            app_id="APP-ID",
            marketplace="EBAY-US",
            min_date=MagicMock(),
            limit_per_card=50,
            score_threshold=0.7,
            ebay_sales_repository=AsyncMock(),
            ebay_scrape_repository=scrape_repo,
            ebay_finding_repository=finding_repo,
            source_product_id=42,
            today="2026-05-24",
            redis_client=redis_client,
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
    mock_redis = _make_redis_mock()

    with patch(
        f"{_MODULE}.get_settings",
        return_value=type("S", (), {"ebay_app_id": "FAKE-APP-ID", "redis_host": "localhost", "redis_port": 6379})(),
    ), patch(f"{_MODULE}.aioredis") as mock_aioredis, \
       patch(f"{_MODULE}.watchlist_path", return_value=_fake_watchlist_path()), \
       patch(f"{_MODULE}.write_items_to_json"):
        mock_aioredis.from_url.return_value = mock_redis
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
async def test_scrape_global_market_skips_fetch_when_quota_exhausted():
    """When Redis quota is exhausted, find_completed_items is never called."""
    from automana.core.services.app_integration.ebay.scrape_global_market_service import scrape_global_market

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
    mock_redis = _make_redis_mock(exhausted=True)

    with patch(
        f"{_MODULE}.get_settings",
        return_value=type("S", (), {"ebay_app_id": "FAKE-APP-ID", "redis_host": "localhost", "redis_port": 6379})(),
    ), patch(f"{_MODULE}.aioredis") as mock_aioredis, \
       patch(f"{_MODULE}.watchlist_path", return_value=_fake_watchlist_path()):
        mock_aioredis.from_url.return_value = mock_redis
        result = await scrape_global_market(
            ebay_sales_repository=mock_sales,
            ebay_scrape_repository=mock_scrape,
            card_repository=mock_card,
            ebay_finding_repository=mock_finding,
        )

    mock_finding.find_completed_items.assert_not_called()
    assert result["scraped_items"] == 0


@pytest.mark.asyncio
async def test_scrape_global_market_logs_warning_when_quota_exhausted(caplog):
    """When Redis quota is exhausted, a warning is logged for each marketplace."""
    import logging
    from automana.core.services.app_integration.ebay.scrape_global_market_service import scrape_global_market

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
    mock_redis = _make_redis_mock(exhausted=True)

    with patch(
        f"{_MODULE}.get_settings",
        return_value=type("S", (), {"ebay_app_id": "FAKE-APP-ID", "redis_host": "localhost", "redis_port": 6379})(),
    ), patch(f"{_MODULE}.aioredis") as mock_aioredis, \
       patch(f"{_MODULE}.watchlist_path", return_value=_fake_watchlist_path()), \
       caplog.at_level(logging.WARNING, logger=_MODULE):
        mock_aioredis.from_url.return_value = mock_redis
        await scrape_global_market(
            ebay_sales_repository=mock_sales,
            ebay_scrape_repository=mock_scrape,
            card_repository=mock_card,
            ebay_finding_repository=mock_finding,
        )

    assert any("scrape_global_market_quota_exhausted" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_scrape_global_market_result_keys():
    """The return dict contains scraped_items and cards_processed."""
    from automana.core.services.app_integration.ebay.scrape_global_market_service import scrape_global_market

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
    mock_redis = _make_redis_mock()

    with patch(
        f"{_MODULE}.get_settings",
        return_value=type("S", (), {"ebay_app_id": "FAKE-APP-ID", "redis_host": "localhost", "redis_port": 6379})(),
    ), patch(f"{_MODULE}.aioredis") as mock_aioredis, \
       patch(f"{_MODULE}.watchlist_path", return_value=_fake_watchlist_path()), \
       patch(f"{_MODULE}.write_items_to_json"):
        mock_aioredis.from_url.return_value = mock_redis
        result = await scrape_global_market(
            ebay_sales_repository=mock_sales,
            ebay_scrape_repository=mock_scrape,
            card_repository=mock_card,
            ebay_finding_repository=mock_finding,
        )

    assert "scraped_items" in result
    assert "cards_processed" in result
    assert result["scraped_items"] == 0
    assert result["cards_processed"] == 1
