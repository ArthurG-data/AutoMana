import pytest
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, call

from automana.core.services.app_integration.ebay.promote_sold_obs_service import (
    _aggregate,
    promote_sold_obs,
    _promote_channel,
)

SOURCE_ID = 42


def _row(ebay_osp_id, price_cents, sold_at=None, finish_id=1, cond_id=1, lang_id=1):
    return {
        "ebay_osp_id": ebay_osp_id,
        "source_product_id": SOURCE_ID,
        "sold_price_cents": price_cents,
        "sold_at": sold_at or datetime(2024, 1, 15, tzinfo=timezone.utc),
        "finish_id": finish_id,
        "condition_id": cond_id,
        "language_id": lang_id,
    }


def _scrape_row(scrape_id, price_cents):
    return {
        "scrape_id": scrape_id,
        "source_product_id": SOURCE_ID,
        "price_cents": price_cents,
        "sold_at": datetime(2024, 1, 15, tzinfo=timezone.utc),
        "finish_id": 1,
        "condition_id": 1,
        "language_id": 1,
    }


# ── _aggregate ────────────────────────────────────────────────────────────────

def test_aggregate_groups_by_date():
    rows = [
        _row(1, 200, datetime(2024, 1, 15, tzinfo=timezone.utc)),
        _row(2, 400, datetime(2024, 1, 15, tzinfo=timezone.utc)),
        _row(3, 300, datetime(2024, 1, 16, tzinfo=timezone.utc)),
    ]
    groups = _aggregate(rows)
    assert len(groups) == 2
    key_15 = (SOURCE_ID, date(2024, 1, 15), 1, 1, 1)
    assert groups[key_15]["count"] == 2
    assert groups[key_15]["total"] == 600


def test_aggregate_uses_scrape_id_key():
    rows = [_scrape_row(99, 150)]
    groups = _aggregate(rows)
    key = (SOURCE_ID, date(2024, 1, 15), 1, 1, 1)
    assert groups[key]["ids"] == [99]


def test_aggregate_null_condition_defaults_to_1():
    row = _row(1, 100)
    row["condition_id"] = None
    groups = _aggregate([row])
    key = (SOURCE_ID, date(2024, 1, 15), 1, 1, 1)
    assert key in groups


# ── _promote_channel ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_promote_channel_empty_returns_zero():
    mark_fn = AsyncMock()
    upsert_fn = AsyncMock()
    count = await _promote_channel([], mark_fn, upsert_fn)
    assert count == 0
    upsert_fn.assert_not_called()
    mark_fn.assert_not_called()


@pytest.mark.asyncio
async def test_promote_channel_upserts_and_marks():
    rows = [_row(1, 300), _row(2, 500)]
    mark_fn = AsyncMock()
    upsert_fn = AsyncMock()
    count = await _promote_channel(rows, mark_fn, upsert_fn)
    assert count == 2
    upsert_fn.assert_called_once()
    call_kwargs = upsert_fn.call_args.kwargs
    assert call_kwargs["sold_avg_cents"] == 400
    assert call_kwargs["sold_count"] == 2
    mark_fn.assert_called_once_with([1, 2])


@pytest.mark.asyncio
async def test_promote_channel_mark_failure_does_not_raise():
    rows = [_row(1, 100)]
    mark_fn = AsyncMock(side_effect=RuntimeError("DB error"))
    upsert_fn = AsyncMock()
    # Should not raise
    count = await _promote_channel(rows, mark_fn, upsert_fn)
    assert isinstance(count, int)


# ── promote_sold_obs ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_promote_sold_obs_both_channels():
    ebay_sales = AsyncMock()
    ebay_sales.get_unpromoted = AsyncMock(return_value=[_row(1, 200)])
    ebay_sales.mark_promoted = AsyncMock()
    ebay_sales.upsert_price_observation = AsyncMock()

    ebay_scrape = AsyncMock()
    ebay_scrape.get_unpromoted = AsyncMock(return_value=[_scrape_row(10, 300)])
    ebay_scrape.mark_promoted = AsyncMock()

    result = await promote_sold_obs(
        ebay_sales_repository=ebay_sales,
        ebay_scrape_repository=ebay_scrape,
    )

    assert result["promoted"] == 2
    assert ebay_sales.upsert_price_observation.call_count == 2


@pytest.mark.asyncio
async def test_promote_sold_obs_empty_both():
    ebay_sales = AsyncMock()
    ebay_sales.get_unpromoted = AsyncMock(return_value=[])
    ebay_scrape = AsyncMock()
    ebay_scrape.get_unpromoted = AsyncMock(return_value=[])

    result = await promote_sold_obs(
        ebay_sales_repository=ebay_sales,
        ebay_scrape_repository=ebay_scrape,
    )
    assert result == {"promoted": 0}
