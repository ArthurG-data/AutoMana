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


@pytest.mark.asyncio
async def test_promote_channel_applies_fx_conversion():
    """fx_map must flow through _promote_channel into _aggregate."""
    row = {
        "scrape_id": 1,
        "source_product_id": SOURCE_ID,
        "price_cents": 200,
        "currency": "AUD",
        "sold_at": datetime(2024, 1, 15, tzinfo=timezone.utc),
        "finish_id": 1,
        "condition_id": 1,
        "language_id": 1,
    }
    mark_fn = AsyncMock()
    upsert_fn = AsyncMock()
    await _promote_channel([row], mark_fn, upsert_fn, fx_map={"AUD": 0.65})
    call_kwargs = upsert_fn.call_args.kwargs
    assert call_kwargs["sold_avg_cents"] == 130  # 200 * 0.65 = 130


# ── promote_sold_obs ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_promote_sold_obs_both_channels():
    from automana.core.repositories.pricing.fx_rates_repository import FxRatesRepository

    ebay_sales = AsyncMock()
    ebay_sales.get_unpromoted = AsyncMock(return_value=[_row(1, 200)])
    ebay_sales.mark_promoted = AsyncMock()
    ebay_sales.upsert_price_observation = AsyncMock()

    ebay_scrape = AsyncMock()
    ebay_scrape.get_unpromoted = AsyncMock(return_value=[_scrape_row(10, 300)])
    ebay_scrape.mark_promoted = AsyncMock()

    fx_rates = AsyncMock(spec=FxRatesRepository)
    fx_rates.get_rates_for_date = AsyncMock(return_value=[])

    result = await promote_sold_obs(
        ebay_sales_repository=ebay_sales,
        ebay_scrape_repository=ebay_scrape,
        fx_rates_repository=fx_rates,
    )

    assert result["promoted"] == 2
    assert ebay_sales.upsert_price_observation.call_count == 2


@pytest.mark.asyncio
async def test_promote_sold_obs_empty_both():
    from automana.core.repositories.pricing.fx_rates_repository import FxRatesRepository

    ebay_sales = AsyncMock()
    ebay_sales.get_unpromoted = AsyncMock(return_value=[])
    ebay_scrape = AsyncMock()
    ebay_scrape.get_unpromoted = AsyncMock(return_value=[])
    fx_rates = AsyncMock(spec=FxRatesRepository)
    fx_rates.get_rates_for_date = AsyncMock(return_value=[])

    result = await promote_sold_obs(
        ebay_sales_repository=ebay_sales,
        ebay_scrape_repository=ebay_scrape,
        fx_rates_repository=fx_rates,
    )
    assert result == {"promoted": 0}


# ── FX conversion ─────────────────────────────────────────────────────────────

def _aud_scrape_row(scrape_id, price_cents):
    return {
        "scrape_id": scrape_id,
        "source_product_id": SOURCE_ID,
        "price_cents": price_cents,
        "currency": "AUD",
        "sold_at": datetime(2024, 1, 15, tzinfo=timezone.utc),
        "finish_id": 1,
        "condition_id": 1,
        "language_id": 1,
    }


def test_aggregate_converts_aud_to_usd():
    """AUD 200 cents × 0.65 rate = 130 USD cents."""
    fx_map = {"AUD": 0.65, "CAD": 0.73}
    rows = [_aud_scrape_row(1, 200)]
    groups = _aggregate(rows, fx_map=fx_map)
    key = (SOURCE_ID, date(2024, 1, 15), 1, 1, 1)
    assert groups[key]["total"] == 130


def test_aggregate_no_conversion_for_usd_rows():
    """USD rows must not be multiplied."""
    fx_map = {"AUD": 0.65}
    rows = [_scrape_row(1, 200)]  # no currency field → USD default
    groups = _aggregate(rows, fx_map=fx_map)
    key = (SOURCE_ID, date(2024, 1, 15), 1, 1, 1)
    assert groups[key]["total"] == 200


def test_aggregate_unknown_currency_uses_face_value():
    """If fx_map has no entry for the currency, use face value and don't crash."""
    fx_map = {"AUD": 0.65}
    row = {
        "scrape_id": 1,
        "source_product_id": SOURCE_ID,
        "price_cents": 500,
        "currency": "GBP",  # not in fx_map
        "sold_at": datetime(2024, 1, 15, tzinfo=timezone.utc),
        "finish_id": 1,
        "condition_id": 1,
        "language_id": 1,
    }
    groups = _aggregate([row], fx_map=fx_map)
    key = (SOURCE_ID, date(2024, 1, 15), 1, 1, 1)
    assert groups[key]["total"] == 500


def test_aggregate_no_fx_map_uses_face_value():
    """Passing fx_map=None must be identical to current behaviour."""
    rows = [_aud_scrape_row(1, 200)]
    groups = _aggregate(rows, fx_map=None)
    key = (SOURCE_ID, date(2024, 1, 15), 1, 1, 1)
    assert groups[key]["total"] == 200


# ── FX wiring in promote_sold_obs ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_promote_sold_obs_applies_fx_to_scrape_channel():
    """AUD 200-cent scrape row should land as 130 USD cents (0.65 rate)."""
    from automana.core.repositories.pricing.fx_rates_repository import FxRatesRepository

    ebay_sales = AsyncMock()
    ebay_sales.get_unpromoted = AsyncMock(return_value=[])
    ebay_sales.mark_promoted = AsyncMock()
    ebay_sales.upsert_price_observation = AsyncMock()

    ebay_scrape = AsyncMock()
    ebay_scrape.get_unpromoted = AsyncMock(return_value=[{
        "scrape_id": 10,
        "source_product_id": SOURCE_ID,
        "price_cents": 200,
        "currency": "AUD",
        "sold_at": datetime(2024, 1, 15, tzinfo=timezone.utc),
        "finish_id": 1,
        "condition_id": 1,
        "language_id": 1,
    }])
    ebay_scrape.mark_promoted = AsyncMock()

    fx_rates = AsyncMock(spec=FxRatesRepository)
    fx_rates.get_rates_for_date = AsyncMock(return_value=[
        {"from_currency": "AUD", "rate": 0.65},
    ])

    result = await promote_sold_obs(
        ebay_sales_repository=ebay_sales,
        ebay_scrape_repository=ebay_scrape,
        fx_rates_repository=fx_rates,
    )

    assert result["promoted"] == 1
    upsert_call = ebay_sales.upsert_price_observation.call_args.kwargs
    assert upsert_call["sold_avg_cents"] == 130  # 200 * 0.65 = 130


@pytest.mark.asyncio
async def test_promote_sold_obs_skips_fx_when_no_rates_available():
    """If FX table has no rates today, promote at face value (no crash)."""
    from automana.core.repositories.pricing.fx_rates_repository import FxRatesRepository

    ebay_sales = AsyncMock()
    ebay_sales.get_unpromoted = AsyncMock(return_value=[])
    ebay_sales.mark_promoted = AsyncMock()
    ebay_sales.upsert_price_observation = AsyncMock()

    ebay_scrape = AsyncMock()
    ebay_scrape.get_unpromoted = AsyncMock(return_value=[{
        "scrape_id": 10,
        "source_product_id": SOURCE_ID,
        "price_cents": 200,
        "currency": "AUD",
        "sold_at": datetime(2024, 1, 15, tzinfo=timezone.utc),
        "finish_id": 1,
        "condition_id": 1,
        "language_id": 1,
    }])
    ebay_scrape.mark_promoted = AsyncMock()

    fx_rates = AsyncMock(spec=FxRatesRepository)
    fx_rates.get_rates_for_date = AsyncMock(return_value=[])  # empty — no rates today

    result = await promote_sold_obs(
        ebay_sales_repository=ebay_sales,
        ebay_scrape_repository=ebay_scrape,
        fx_rates_repository=fx_rates,
    )

    assert result["promoted"] == 1
    upsert_call = ebay_sales.upsert_price_observation.call_args.kwargs
    assert upsert_call["sold_avg_cents"] == 200  # face value fallback
