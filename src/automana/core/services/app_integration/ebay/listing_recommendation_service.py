from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal, Optional
from uuid import UUID

from automana.core.service_registry import ServiceRegistry
from automana.core.services.analytics.strategies import (
    CompetitiveStrategy,
    PremiumStrategy,
    PricingStrategyManager,
    QuickSaleStrategy,
)

logger = logging.getLogger(__name__)

_MANAGER = PricingStrategyManager({
    'quick': QuickSaleStrategy(),
    'balanced': CompetitiveStrategy(),
    'max': PremiumStrategy(),
})


@dataclass
class ListingRecommendation:
    suggested_action: Literal['raise', 'lower', 'hold', 'draft']
    strategy_kind: str
    suggested_price: Optional[float]
    confidence: float
    signals_used: Literal['behavioral', 'market']  # 'market' = percentiles available; 'behavioral' = fallback
    all_strategies: dict = field(default_factory=dict)


def compute_recommendation(
    signals: dict,
    market_data: dict | None = None,
) -> ListingRecommendation:
    """Pure recommendation engine — no DB access. Safe to call from router or agent tool."""
    days_listed = signals.get('days_listed', 0)
    watch_count = signals.get('watch_count', 0)
    price = signals.get('price', 0.0)

    if market_data is None:
        return _behavioral_recommendation(days_listed, watch_count)

    return _market_recommendation(days_listed, price, market_data)


def _behavioral_recommendation(days_listed: int, watch_count: int) -> ListingRecommendation:
    if days_listed > 30 and watch_count == 0:
        return ListingRecommendation(
            suggested_action='draft', strategy_kind='balanced',
            suggested_price=None, confidence=0.9, signals_used='behavioral',
        )
    if days_listed > 14 and watch_count < 2:
        return ListingRecommendation(
            suggested_action='lower', strategy_kind='quick',
            suggested_price=None, confidence=0.8, signals_used='behavioral',
        )
    if days_listed < 7 and watch_count >= 5:
        return ListingRecommendation(
            suggested_action='raise', strategy_kind='max',
            suggested_price=None, confidence=0.75, signals_used='behavioral',
        )
    return ListingRecommendation(
        suggested_action='hold', strategy_kind='balanced',
        suggested_price=None, confidence=0.7, signals_used='behavioral',
    )


def _market_recommendation(days_listed: int, price: float, market_data: dict) -> ListingRecommendation:
    stats = market_data['stats']
    percentiles = market_data['percentiles']
    p25 = percentiles.get('p25', price)
    p75 = percentiles.get('p75', price)

    market_conditions = {
        'volatility': stats.get('std_deviation', 0) / max(stats.get('mean_price', 1), 1),
        'competition_level': 'high' if stats.get('total_listings', 0) > 20 else 'medium',
        'inventory_level': 'medium',
        'cash_flow_priority': False,
        'card_rarity': market_data.get('card_rarity', 'rare'),
        'seller_reputation': 'high',
    }

    strategy_name, result = _MANAGER.recommend_strategy(market_conditions, stats, percentiles)

    if price < p25 * 0.95:
        action: Literal['raise', 'lower', 'hold', 'draft'] = 'raise'
    elif price > p75 * 1.05:
        action = 'lower'
    elif days_listed > 14 and price <= p25:
        action = 'draft'
    else:
        action = {'quick': 'lower', 'balanced': 'hold', 'max': 'raise'}.get(strategy_name, 'hold')  # type: ignore[assignment]

    all_strats = _MANAGER.get_all_strategies(stats, percentiles, market_conditions)

    return ListingRecommendation(
        suggested_action=action,
        strategy_kind=strategy_name,
        suggested_price=round(result.price, 2),
        confidence=result.confidence,
        signals_used='market',
        all_strategies={
            k: {'price': round(v.price, 2), 'description': v.description, 'confidence': v.confidence}
            for k, v in all_strats.items()
        },
    )


@ServiceRegistry.register(
    path="integrations.ebay.recommendations.get",
    db_repositories=[],
    api_repositories=[],
)
async def get_listing_recommendation(
    user_id: UUID,
    app_code: str,
    item_id: str,
    days_listed: int,
    watch_count: int,
    price: float,
    currency: str = "AUD",
) -> dict:
    signals = {
        'days_listed': days_listed,
        'watch_count': watch_count,
        'price': price,
        'currency': currency,
    }
    rec = compute_recommendation(signals, market_data=None)
    logger.info("Recommendation computed", extra={
        "item_id": item_id, "action": rec.suggested_action, "signals_used": rec.signals_used,
    })
    return {
        'item_id': item_id,
        'suggested_action': rec.suggested_action,
        'strategy_kind': rec.strategy_kind,
        'suggested_price': rec.suggested_price,
        'confidence': rec.confidence,
        'signals_used': rec.signals_used,
        'all_strategies': rec.all_strategies,
    }
