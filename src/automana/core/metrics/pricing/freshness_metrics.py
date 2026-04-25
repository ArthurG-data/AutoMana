"""pricing.freshness.* — staleness detection across pricing sources."""
from __future__ import annotations

from automana.core.metrics.registry import MetricRegistry, MetricResult, Threshold
from automana.core.repositories.app_integration.mtg_stock.price_repository import PriceRepository


@MetricRegistry.register(
    path="pricing.freshness.price_observation_max_age_days",
    category="timing",
    description="Days since the most recent pricing.price_observation.ts_date across all sources.",
    severity=Threshold(warn=2, error=7, direction="higher_is_worse"),
    db_repositories=["price"],
)
async def price_observation_max_age_days(price_repository: PriceRepository) -> MetricResult:
    n = await price_repository.fetch_max_observation_age_days()
    return MetricResult(row_count=n)


@MetricRegistry.register(
    path="pricing.freshness.max_per_source_lag_hours",
    category="timing",
    description="Hours since the latest observation per source. Headline = MAX across sources; details carries per-source breakdown.",
    severity=Threshold(warn=48, error=120, direction="higher_is_worse"),
    db_repositories=["price"],
)
async def max_per_source_lag_hours(price_repository: PriceRepository) -> MetricResult:
    per_source = await price_repository.fetch_per_source_lag_hours()
    non_null = [v for v in per_source.values() if v is not None]
    headline = max(non_null) if non_null else None
    return MetricResult(row_count=headline, details={"per_source": per_source})
