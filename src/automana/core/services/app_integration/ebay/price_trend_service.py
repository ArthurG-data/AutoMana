from __future__ import annotations

import logging
from uuid import UUID

from automana.core.service_registry import ServiceRegistry
from automana.core.services.app_integration.ebay.listing_recommendation_service import (
    PriceTrend,
    compute_price_trend,
    compute_recommendation,
)

logger = logging.getLogger(__name__)


async def get_listing_price_trend(
    item_id: str,
    app_code: str,
    ebay_sales_repository,
    pricing_repository,
) -> dict:
    meta = await ebay_sales_repository.get_listing_meta(item_id, app_code)
    if meta is None:
        raise ValueError(f"Listing {item_id!r} not found or not yet linked to a card")

    card_version_id: UUID = meta["card_version_id"]
    finish_id: int = meta["finish_id"]
    condition_id: int = meta["condition_id"]

    history = await pricing_repository.get_price_history(
        card_version_id, finish_id, condition_id, days=90
    )

    trend: PriceTrend = compute_price_trend(history)

    signals = {"days_listed": 0, "watch_count": 0, "price": (trend.latest_avg_cents or 0) / 100}
    rec = compute_recommendation(signals, price_trend=trend)

    logger.info(
        "Price trend computed",
        extra={
            "item_id": item_id,
            "signal": trend.signal,
            "action": rec.suggested_action,
            "n_observations": trend.n_observations,
        },
    )

    return {
        "item_id": item_id,
        "card_version_id": str(card_version_id),
        "finish": meta["finish_code"],
        "condition": meta["condition_code"],
        "trend": {
            "signal": trend.signal,
            "delta_7d_pct": trend.delta_7d_pct,
            "delta_30d_pct": trend.delta_30d_pct,
            "delta_90d_pct": trend.delta_90d_pct,
            "latest_avg_cents": trend.latest_avg_cents,
            "n_observations": trend.n_observations,
            "source_used": trend.source_used,
        },
        "recommendation": {
            "suggested_action": rec.suggested_action,
            "confidence": rec.confidence,
            "signals_used": rec.signals_used,
        },
    }


@ServiceRegistry.register(
    path="integrations.ebay.recommendations.trend",
    db_repositories=["pricing", "ebay_sales"],
    api_repositories=[],
)
async def _registered_get_listing_price_trend(
    item_id: str,
    app_code: str,
    pricing_repository=None,
    ebay_sales_repository=None,
) -> dict:
    return await get_listing_price_trend(
        item_id=item_id,
        app_code=app_code,
        ebay_sales_repository=ebay_sales_repository,
        pricing_repository=pricing_repository,
    )
