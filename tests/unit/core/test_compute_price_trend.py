from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4


async def test_get_listing_meta_returns_none_for_missing_item():
    from automana.core.repositories.app_integration.ebay.sales_repository import EbaySalesRepository

    repo = EbaySalesRepository(connection=MagicMock())
    repo.execute_query = AsyncMock(return_value=[])

    result = await repo.get_listing_meta("missing-item", "myapp")

    assert result is None


async def test_get_listing_meta_returns_dict_for_existing_item():
    from automana.core.repositories.app_integration.ebay.sales_repository import EbaySalesRepository

    card_id = uuid4()
    repo = EbaySalesRepository(connection=MagicMock())
    repo.execute_query = AsyncMock(return_value=[{
        "card_version_id": card_id,
        "finish_id": 1,
        "condition_id": 1,
        "language_id": 1,
        "finish_code": "NONFOIL",
        "condition_code": "NM",
    }])

    result = await repo.get_listing_meta("item-123", "myapp")

    assert result["card_version_id"] == card_id
    assert result["finish_code"] == "NONFOIL"
    assert result["condition_code"] == "NM"


async def test_get_listing_meta_returns_none_when_card_version_id_is_null():
    from automana.core.repositories.app_integration.ebay.sales_repository import EbaySalesRepository

    repo = EbaySalesRepository(connection=MagicMock())
    repo.execute_query = AsyncMock(return_value=[{
        "card_version_id": None,
        "finish_id": 1,
        "condition_id": 1,
        "language_id": 1,
        "finish_code": "NONFOIL",
        "condition_code": "NM",
    }])

    result = await repo.get_listing_meta("item-123", "myapp")

    assert result is None


from datetime import date


async def test_get_price_history_returns_empty_list_when_no_data():
    from automana.core.repositories.pricing.price_repository import PricingTierRepository
    from unittest.mock import AsyncMock, MagicMock
    from uuid import uuid4

    mock_conn = MagicMock()
    mock_conn.fetch = AsyncMock(return_value=[])
    repo = PricingTierRepository(connection=mock_conn)

    result = await repo.get_price_history(uuid4(), finish_id=1, condition_id=1, days=90)

    assert result == []


async def test_get_price_history_returns_sorted_dicts():
    from automana.core.repositories.pricing.price_repository import PricingTierRepository
    from unittest.mock import AsyncMock, MagicMock
    from uuid import uuid4

    mock_conn = MagicMock()
    mock_conn.fetch = AsyncMock(return_value=[
        {"price_date": date(2026, 4, 1), "list_avg_cents": 1000, "list_low_cents": 900, "source_code": "tcg"},
        {"price_date": date(2026, 5, 1), "list_avg_cents": 1200, "list_low_cents": 1100, "source_code": "tcg"},
    ])
    repo = PricingTierRepository(connection=mock_conn)

    result = await repo.get_price_history(uuid4(), finish_id=1, condition_id=1, days=90)

    assert len(result) == 2
    assert result[0]["price_date"] == date(2026, 4, 1)
    assert result[1]["list_avg_cents"] == 1200
    assert result[0]["source_code"] == "tcg"


from datetime import timedelta


def _make_series(n_days: int, start_cents: int, end_cents: int, source: str = "tcg") -> list[dict]:
    """Generate a linear price series from start to end over n_days."""
    today = date(2026, 5, 17)
    series = []
    for i in range(n_days):
        day = today - timedelta(days=n_days - 1 - i)
        price = int(start_cents + (end_cents - start_cents) * i / max(n_days - 1, 1))
        series.append({"price_date": day, "list_avg_cents": price, "list_low_cents": price - 50, "source_code": source})
    return series


def test_compute_price_trend_insufficient_data_empty():
    from automana.core.services.app_integration.ebay.listing_recommendation_service import compute_price_trend

    result = compute_price_trend([])
    assert result.signal == "INSUFFICIENT_DATA"
    assert result.n_observations == 0
    assert result.delta_30d_pct is None


def test_compute_price_trend_insufficient_data_single_row():
    from automana.core.services.app_integration.ebay.listing_recommendation_service import compute_price_trend

    series = _make_series(1, 1000, 1000)
    result = compute_price_trend(series)
    assert result.signal == "INSUFFICIENT_DATA"
    assert result.n_observations == 1
    assert result.latest_avg_cents == 1000


def test_compute_price_trend_up_signal():
    from automana.core.services.app_integration.ebay.listing_recommendation_service import compute_price_trend

    series = _make_series(35, 1000, 1200)
    result = compute_price_trend(series)
    assert result.signal == "UP"
    assert result.delta_30d_pct is not None
    assert result.delta_30d_pct >= 10.0


def test_compute_price_trend_down_signal():
    from automana.core.services.app_integration.ebay.listing_recommendation_service import compute_price_trend

    series = _make_series(35, 1200, 1000)
    result = compute_price_trend(series)
    assert result.signal == "DOWN"
    assert result.delta_30d_pct is not None
    assert result.delta_30d_pct <= -10.0


def test_compute_price_trend_sideways_signal():
    from automana.core.services.app_integration.ebay.listing_recommendation_service import compute_price_trend

    series = _make_series(35, 1000, 1050)
    result = compute_price_trend(series)
    assert result.signal == "SIDEWAYS"


def test_compute_price_trend_falls_back_to_7d_when_no_30d_anchor():
    from automana.core.services.app_integration.ebay.listing_recommendation_service import compute_price_trend

    series = _make_series(10, 1000, 1200)
    result = compute_price_trend(series)
    assert result.delta_30d_pct is None
    assert result.delta_7d_pct is not None
    assert result.signal in ("UP", "DOWN", "SIDEWAYS")


def test_compute_price_trend_sets_source_and_latest_cents():
    from automana.core.services.app_integration.ebay.listing_recommendation_service import compute_price_trend

    series = _make_series(35, 1000, 1200, source="cardkingdom")
    result = compute_price_trend(series)
    assert result.source_used == "cardkingdom"
    assert result.latest_avg_cents == 1200


def _trend(signal: str):
    from automana.core.services.app_integration.ebay.listing_recommendation_service import PriceTrend
    return PriceTrend(
        signal=signal,  # type: ignore[arg-type]
        delta_7d_pct=None, delta_30d_pct=None, delta_90d_pct=None,
        latest_avg_cents=1000, n_observations=30, source_used="tcg",
    )


def test_trend_overlay_hold_up_becomes_raise():
    from automana.core.services.app_integration.ebay.listing_recommendation_service import compute_recommendation
    # Behavioral: 10 days listed, 1 watch → hold
    signals = {"days_listed": 10, "watch_count": 1, "price": 10.0}
    rec = compute_recommendation(signals, price_trend=_trend("UP"))
    assert rec.suggested_action == "raise"
    assert rec.signals_used == "trend"


def test_trend_overlay_hold_down_becomes_lower():
    from automana.core.services.app_integration.ebay.listing_recommendation_service import compute_recommendation
    signals = {"days_listed": 10, "watch_count": 1, "price": 10.0}
    rec = compute_recommendation(signals, price_trend=_trend("DOWN"))
    assert rec.suggested_action == "lower"
    assert rec.signals_used == "trend"


def test_trend_overlay_draft_unchanged():
    from automana.core.services.app_integration.ebay.listing_recommendation_service import compute_recommendation
    # Behavioral: 35 days listed, 0 watches → draft
    signals = {"days_listed": 35, "watch_count": 0, "price": 10.0}
    rec = compute_recommendation(signals, price_trend=_trend("UP"))
    assert rec.suggested_action == "draft"


def test_trend_overlay_sideways_leaves_action_unchanged():
    from automana.core.services.app_integration.ebay.listing_recommendation_service import compute_recommendation
    signals = {"days_listed": 10, "watch_count": 1, "price": 10.0}
    rec_no_trend = compute_recommendation(signals)
    rec_sideways = compute_recommendation(signals, price_trend=_trend("SIDEWAYS"))
    assert rec_sideways.suggested_action == rec_no_trend.suggested_action
    assert rec_sideways.signals_used == rec_no_trend.signals_used


def test_trend_overlay_insufficient_data_leaves_action_unchanged():
    from automana.core.services.app_integration.ebay.listing_recommendation_service import compute_recommendation
    signals = {"days_listed": 10, "watch_count": 1, "price": 10.0}
    rec_no_trend = compute_recommendation(signals)
    rec = compute_recommendation(signals, price_trend=_trend("INSUFFICIENT_DATA"))
    assert rec.suggested_action == rec_no_trend.suggested_action


def test_trend_overlay_raise_down_becomes_hold():
    from automana.core.services.app_integration.ebay.listing_recommendation_service import compute_recommendation
    # Behavioral: 3 days listed, 6 watches → raise
    signals = {"days_listed": 3, "watch_count": 6, "price": 10.0}
    rec = compute_recommendation(signals, price_trend=_trend("DOWN"))
    assert rec.suggested_action == "hold"


def test_trend_overlay_lower_up_becomes_hold():
    from automana.core.services.app_integration.ebay.listing_recommendation_service import compute_recommendation
    # Behavioral: 20 days listed, 1 watch → lower
    signals = {"days_listed": 20, "watch_count": 1, "price": 10.0}
    rec = compute_recommendation(signals, price_trend=_trend("UP"))
    assert rec.suggested_action == "hold"


def test_compute_price_trend_handles_series_with_zero_anchor():
    from automana.core.services.app_integration.ebay.listing_recommendation_service import compute_price_trend
    from datetime import date, timedelta

    # If anchor row has list_avg_cents=0 (edge case), _delta_pct returns None (division by zero guard)
    today = date(2026, 5, 17)
    series = [
        {"price_date": today - timedelta(days=35), "list_avg_cents": 0, "list_low_cents": 0, "source_code": "tcg"},
        {"price_date": today, "list_avg_cents": 1000, "list_low_cents": 900, "source_code": "tcg"},
    ]
    result = compute_price_trend(series)
    # anchor=0 → _delta_pct returns None for d30; signal degrades to INSUFFICIENT_DATA
    assert result.delta_30d_pct is None
    assert result.signal == "INSUFFICIENT_DATA"
