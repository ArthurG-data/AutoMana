"""
Tests for src/automana/core/services/analytics/strategies.py

Pure-logic module — no mocks required except for the recommend_strategy
fallback path. All tests are synchronous.
Coverage target: >= 95% line + branch.

Classes under test:
  - QuickSaleStrategy
  - CompetitiveStrategy
  - PremiumStrategy
  - PricingStrategyManager

--- PLAN CORRECTION (§5.7) ---
PricingStrategyManager.recommend_strategy fallback hard-codes
self.strategies['competitive']. A manager without that key raises KeyError
on the fallback path. The fallback test must include 'competitive' in the
manager and use MagicMock to force all is_suitable to return False.

"""
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.unit

from automana.core.services.analytics.strategies import (
    CompetitiveStrategy,
    PremiumStrategy,
    PricingStrategy,
    PricingStrategyManager,
    QuickSaleStrategy,
)
from automana.core.services.analytics.models import PricingResult


# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

_STATS = {
    "median_price": 10.0,
    "mean_price": 10.0,
    "std_deviation": 1.0,
}
_PERCENTILES = {
    "p25": 7.0,
    "p75": 13.0,
}


# ---------------------------------------------------------------------------
# QuickSaleStrategy
# ---------------------------------------------------------------------------

class TestQuickSaleStrategyCalculatePrice:
    def setup_method(self):
        self.strategy = QuickSaleStrategy()

    def test_high_volatility_reduces_price_by_5_percent(self):
        market = {"volatility": 0.5}
        result = self.strategy.calculate_price(_STATS, _PERCENTILES, market)
        assert result.price == round(_PERCENTILES["p25"] * 0.95, 2)
        assert result.confidence == 0.9

    def test_normal_market_uses_p25_at_full_price(self):
        market = {"volatility": 0.1}
        result = self.strategy.calculate_price(_STATS, _PERCENTILES, market)
        assert result.price == _PERCENTILES["p25"]
        assert result.confidence == 0.85

    def test_volatility_exactly_at_threshold_is_not_high(self):
        # boundary condition: > 0.3, not >= 0.3
        market = {"volatility": 0.3}
        result = self.strategy.calculate_price(_STATS, _PERCENTILES, market)
        assert result.price == _PERCENTILES["p25"]
        assert result.confidence == 0.85

    def test_market_data_none_uses_p25_no_error(self):
        result = self.strategy.calculate_price(_STATS, _PERCENTILES, market_data=None)
        assert result.price == _PERCENTILES["p25"]
        assert result.confidence == 0.85

    def test_metadata_reflects_actual_volatility(self):
        market = {"volatility": 0.4}
        result = self.strategy.calculate_price(_STATS, _PERCENTILES, market)
        assert result.metadata["volatility_adjustment"] == 0.4

    def test_metadata_zero_volatility_when_market_none(self):
        result = self.strategy.calculate_price(_STATS, _PERCENTILES, None)
        assert result.metadata["volatility_adjustment"] == 0

    def test_returns_pricing_result_instance(self):
        result = self.strategy.calculate_price(_STATS, _PERCENTILES, None)
        assert isinstance(result, PricingResult)


class TestQuickSaleStrategyIsSuitable:
    def setup_method(self):
        self.strategy = QuickSaleStrategy()

    @pytest.mark.parametrize("conditions,expected", [
        ({"inventory_level": "high"}, True),
        ({"cash_flow_priority": True}, True),
        ({"volatility": 0.35}, True),
        ({"inventory_level": "medium", "cash_flow_priority": False, "volatility": 0.1}, False),
        ({}, False),
    ])
    def test_is_suitable_branches(self, conditions, expected):
        assert self.strategy.is_suitable(conditions) is expected


# ---------------------------------------------------------------------------
# CompetitiveStrategy
# ---------------------------------------------------------------------------

class TestCompetitiveStrategyCalculatePrice:
    def setup_method(self):
        self.strategy = CompetitiveStrategy()

    @pytest.mark.parametrize("competition_level,expected_factor,expected_confidence", [
        ("high",   0.92, 0.80),
        ("low",    0.98, 0.90),
        ("medium", 0.95, 0.85),
    ])
    def test_competition_level_branches(self, competition_level, expected_factor, expected_confidence):
        market = {"competition_level": competition_level}
        result = self.strategy.calculate_price(_STATS, _PERCENTILES, market)
        expected_price = _STATS["median_price"] * expected_factor
        assert abs(result.price - expected_price) < 1e-9
        assert result.confidence == expected_confidence

    def test_market_data_none_defaults_to_medium_competition(self):
        result = self.strategy.calculate_price(_STATS, _PERCENTILES, market_data=None)
        assert abs(result.price - _STATS["median_price"] * 0.95) < 1e-9
        assert result.confidence == 0.85

    def test_missing_competition_key_defaults_to_medium(self):
        result = self.strategy.calculate_price(_STATS, _PERCENTILES, {})
        assert abs(result.price - _STATS["median_price"] * 0.95) < 1e-9

    def test_returns_pricing_result_instance(self):
        result = self.strategy.calculate_price(_STATS, _PERCENTILES, None)
        assert isinstance(result, PricingResult)


class TestCompetitiveStrategyIsSuitable:
    def test_always_returns_true(self):
        strategy = CompetitiveStrategy()
        assert strategy.is_suitable({}) is True
        assert strategy.is_suitable({"any": "condition"}) is True


# ---------------------------------------------------------------------------
# PremiumStrategy
# ---------------------------------------------------------------------------

class TestPremiumStrategyCalculatePrice:
    def setup_method(self):
        self.strategy = PremiumStrategy()

    def test_mythic_high_reputation_applies_premium_bump(self):
        market = {"card_rarity": "mythic", "seller_reputation": "high"}
        result = self.strategy.calculate_price(_STATS, _PERCENTILES, market)
        assert abs(result.price - _PERCENTILES["p75"] * 1.05) < 1e-9
        assert result.confidence == 0.75
        assert result.metadata["rarity_bonus"] is True
        assert result.metadata["reputation_bonus"] is True

    def test_rare_high_reputation_applies_premium_bump(self):
        market = {"card_rarity": "rare", "seller_reputation": "high"}
        result = self.strategy.calculate_price(_STATS, _PERCENTILES, market)
        assert abs(result.price - _PERCENTILES["p75"] * 1.05) < 1e-9

    def test_common_card_no_bump(self):
        market = {"card_rarity": "common", "seller_reputation": "high"}
        result = self.strategy.calculate_price(_STATS, _PERCENTILES, market)
        assert result.price == _PERCENTILES["p75"]
        assert result.confidence == 0.6

    def test_rare_average_reputation_no_bump(self):
        market = {"card_rarity": "rare", "seller_reputation": "average"}
        result = self.strategy.calculate_price(_STATS, _PERCENTILES, market)
        assert result.price == _PERCENTILES["p75"]
        assert result.confidence == 0.6

    def test_market_data_none_no_bump(self):
        result = self.strategy.calculate_price(_STATS, _PERCENTILES, market_data=None)
        assert result.price == _PERCENTILES["p75"]
        assert result.confidence == 0.6
        assert result.metadata["rarity_bonus"] is False
        assert result.metadata["reputation_bonus"] is False

    def test_returns_pricing_result_instance(self):
        result = self.strategy.calculate_price(_STATS, _PERCENTILES, None)
        assert isinstance(result, PricingResult)


class TestPremiumStrategyIsSuitable:
    def setup_method(self):
        self.strategy = PremiumStrategy()

    @pytest.mark.parametrize("conditions,expected", [
        ({"card_rarity": "mythic", "seller_reputation": "high",      "volatility": 0.1},  True),
        ({"card_rarity": "rare",   "seller_reputation": "excellent",  "volatility": 0.0},  True),
        ({"card_rarity": "common", "seller_reputation": "high",       "volatility": 0.1},  False),
        ({"card_rarity": "mythic", "seller_reputation": "average",    "volatility": 0.1},  False),
        ({"card_rarity": "mythic", "seller_reputation": "high",       "volatility": 0.25}, False),
        ({}, False),
    ])
    def test_is_suitable_branches(self, conditions, expected):
        assert self.strategy.is_suitable(conditions) is expected


# ---------------------------------------------------------------------------
# PricingStrategyManager
# ---------------------------------------------------------------------------

class TestPricingStrategyManagerGetAllStrategies:
    def test_returns_result_for_every_registered_strategy(self):
        strategies = {
            "quick": QuickSaleStrategy(),
            "competitive": CompetitiveStrategy(),
        }
        manager = PricingStrategyManager(strategies)
        results = manager.get_all_strategies(_STATS, _PERCENTILES, {})
        assert set(results.keys()) == {"quick", "competitive"}
        for result in results.values():
            assert isinstance(result, PricingResult)

    def test_empty_strategies_returns_empty_dict(self):
        manager = PricingStrategyManager({})
        assert manager.get_all_strategies(_STATS, _PERCENTILES, {}) == {}


class TestPricingStrategyManagerGetSuitableStrategies:
    def test_returns_only_suitable_strategies(self):
        strategies = {
            "quick": QuickSaleStrategy(),
            "competitive": CompetitiveStrategy(),
            "premium": PremiumStrategy(),
        }
        manager = PricingStrategyManager(strategies)
        # Conditions: no high inventory, no cash priority, no volatility, common card
        conditions = {"inventory_level": "medium", "cash_flow_priority": False, "volatility": 0.1}
        results = manager.get_suitable_strategies(conditions, _STATS, _PERCENTILES)
        assert "competitive" in results       # always suitable
        assert "quick" not in results         # none of its conditions met
        assert "premium" not in results       # rarity/reputation/volatility conditions not met

    def test_all_suitable_strategies_included(self):
        strategies = {
            "quick": QuickSaleStrategy(),
            "competitive": CompetitiveStrategy(),
        }
        manager = PricingStrategyManager(strategies)
        conditions = {"inventory_level": "high"}   # quick is suitable here
        results = manager.get_suitable_strategies(conditions, _STATS, _PERCENTILES)
        assert set(results.keys()) == {"quick", "competitive"}


class TestPricingStrategyManagerRecommendStrategy:
    def test_recommend_returns_highest_confidence_strategy(self):
        # quick.calculate_price(volatility>0.3) → confidence 0.9
        # competitive.calculate_price(competition=high) → confidence 0.8
        strategies = {
            "quick": QuickSaleStrategy(),
            "competitive": CompetitiveStrategy(),
        }
        manager = PricingStrategyManager(strategies)
        conditions = {"volatility": 0.5, "competition_level": "high"}
        name, result = manager.recommend_strategy(conditions, _STATS, _PERCENTILES)
        assert name == "quick"
        assert result.confidence == 0.9

    def test_fallback_to_competitive_when_no_suitable_strategy(self):
        """
        Plan §5.7 correction: the fallback path hard-codes self.strategies['competitive'].
        Manager without 'competitive' would KeyError. To reach fallback, include
        'competitive' but force all is_suitable to return False via MagicMock.
        """
        mock_premium = MagicMock(spec=PricingStrategy)
        mock_premium.is_suitable.return_value = False

        mock_competitive = MagicMock(spec=PricingStrategy)
        mock_competitive.is_suitable.return_value = False
        mock_competitive.calculate_price.return_value = PricingResult(
            price=5.0,
            description="fallback competitive",
            expected_speed="Fast",
            profit_margin="Medium",
            confidence=0.85,
        )

        manager = PricingStrategyManager(
            {"premium": mock_premium, "competitive": mock_competitive}
        )
        name, result = manager.recommend_strategy({}, _STATS, _PERCENTILES)
        assert name == "competitive"
        assert result.price == 5.0
        mock_competitive.calculate_price.assert_called_once()
