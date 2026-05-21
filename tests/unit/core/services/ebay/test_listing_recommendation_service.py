import pytest
from automana.core.services.app_integration.ebay.listing_recommendation_service import (
    compute_recommendation,
    ListingRecommendation,
)


def test_behavioral_draft_when_stale_no_watchers():
    rec = compute_recommendation({'days_listed': 31, 'watch_count': 0, 'price': 10.0})
    assert rec.suggested_action == 'draft'
    assert rec.signals_used == 'behavioral'
    assert rec.suggested_price is None


def test_behavioral_lower_when_stale_low_interest():
    rec = compute_recommendation({'days_listed': 15, 'watch_count': 1, 'price': 10.0})
    assert rec.suggested_action == 'lower'
    assert rec.strategy_kind == 'quick'
    assert rec.signals_used == 'behavioral'


def test_behavioral_raise_when_fresh_high_watchers():
    rec = compute_recommendation({'days_listed': 5, 'watch_count': 6, 'price': 10.0})
    assert rec.suggested_action == 'raise'
    assert rec.strategy_kind == 'max'


def test_behavioral_hold_otherwise():
    rec = compute_recommendation({'days_listed': 5, 'watch_count': 2, 'price': 10.0})
    assert rec.suggested_action == 'hold'
    assert rec.strategy_kind == 'balanced'


def test_market_raise_when_listed_below_p25():
    market_data = {
        'stats': {
            'median_price': 50.0, 'mean_price': 50.0, 'std_deviation': 5.0,
            'total_listings': 10, 'min_price': 30.0, 'max_price': 70.0,
            'price_range': 40.0,
        },
        'percentiles': {'p25': 40.0, 'p50': 50.0, 'p75': 60.0, 'p5': 30.0,
                        'p10': 35.0, 'p90': 65.0, 'p95': 68.0, 'p99': 70.0},
    }
    # Price $37 is below p25 ($40) * 0.95 = $38 → raise
    rec = compute_recommendation({'days_listed': 5, 'watch_count': 2, 'price': 37.0}, market_data)
    assert rec.suggested_action == 'raise'
    assert rec.signals_used == 'market'
    assert rec.suggested_price is not None


def test_market_lower_when_listed_above_p75():
    market_data = {
        'stats': {
            'median_price': 50.0, 'mean_price': 50.0, 'std_deviation': 5.0,
            'total_listings': 10, 'min_price': 30.0, 'max_price': 70.0,
            'price_range': 40.0,
        },
        'percentiles': {'p25': 40.0, 'p50': 50.0, 'p75': 60.0, 'p5': 30.0,
                        'p10': 35.0, 'p90': 65.0, 'p95': 68.0, 'p99': 70.0},
    }
    # Price $65 is above p75 ($60) * 1.05 = $63 → lower
    rec = compute_recommendation({'days_listed': 5, 'watch_count': 2, 'price': 65.0}, market_data)
    assert rec.suggested_action == 'lower'
    assert rec.signals_used == 'market'


def test_recommendation_is_dataclass():
    rec = compute_recommendation({'days_listed': 1, 'watch_count': 1, 'price': 10.0})
    assert isinstance(rec, ListingRecommendation)
    assert 0.0 <= rec.confidence <= 1.0
