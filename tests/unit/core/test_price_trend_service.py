from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from datetime import date, timedelta
import pytest


def _make_series(n: int, start: int, end: int) -> list[dict]:
    today = date(2026, 5, 17)
    series = []
    for i in range(n):
        day = today - timedelta(days=n - 1 - i)
        price = int(start + (end - start) * i / max(n - 1, 1))
        series.append({"price_date": day, "list_avg_cents": price, "list_low_cents": price - 50, "source_code": "tcg"})
    return series


async def test_get_listing_price_trend_raises_for_unknown_item():
    from automana.core.services.app_integration.ebay.price_trend_service import get_listing_price_trend

    ebay_sales_repo = MagicMock()
    ebay_sales_repo.get_listing_meta = AsyncMock(return_value=None)
    pricing_repo = MagicMock()

    with pytest.raises(ValueError, match="not found"):
        await get_listing_price_trend(
            item_id="bad-item",
            app_code="myapp",
            ebay_sales_repository=ebay_sales_repo,
            pricing_repository=pricing_repo,
        )


async def test_get_listing_price_trend_returns_up_signal():
    from automana.core.services.app_integration.ebay.price_trend_service import get_listing_price_trend

    card_id = uuid4()
    ebay_sales_repo = MagicMock()
    ebay_sales_repo.get_listing_meta = AsyncMock(return_value={
        "card_version_id": card_id,
        "finish_id": 1,
        "condition_id": 1,
        "language_id": 1,
        "finish_code": "NONFOIL",
        "condition_code": "NM",
    })
    pricing_repo = MagicMock()
    pricing_repo.get_price_history = AsyncMock(return_value=_make_series(35, 1000, 1250))

    result = await get_listing_price_trend(
        item_id="item-123",
        app_code="myapp",
        ebay_sales_repository=ebay_sales_repo,
        pricing_repository=pricing_repo,
    )

    assert result["trend"]["signal"] == "UP"
    assert result["item_id"] == "item-123"
    assert result["finish"] == "NONFOIL"
    assert result["condition"] == "NM"
    assert result["recommendation"]["suggested_action"] in ("raise", "hold", "lower", "draft")


async def test_get_listing_price_trend_returns_insufficient_data_for_empty_history():
    from automana.core.services.app_integration.ebay.price_trend_service import get_listing_price_trend

    card_id = uuid4()
    ebay_sales_repo = MagicMock()
    ebay_sales_repo.get_listing_meta = AsyncMock(return_value={
        "card_version_id": card_id,
        "finish_id": 1,
        "condition_id": 1,
        "language_id": 1,
        "finish_code": "NONFOIL",
        "condition_code": "NM",
    })
    pricing_repo = MagicMock()
    pricing_repo.get_price_history = AsyncMock(return_value=[])

    result = await get_listing_price_trend(
        item_id="item-123",
        app_code="myapp",
        ebay_sales_repository=ebay_sales_repo,
        pricing_repository=pricing_repo,
    )

    assert result["trend"]["signal"] == "INSUFFICIENT_DATA"
    assert result["trend"]["n_observations"] == 0
