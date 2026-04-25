"""pricing.coverage.* — per-source observation coverage."""
from __future__ import annotations

from automana.core.metrics.registry import MetricRegistry, MetricResult, Threshold
from automana.core.repositories.app_integration.mtg_stock.price_repository import PriceRepository


@MetricRegistry.register(
    path="pricing.coverage.min_per_source_observation_coverage_pct",
    category="health",
    description="MIN across sources of % of source_product rows with a price_observation in the last 30 days.",
    severity=Threshold(warn=50, error=20, direction="lower_is_worse"),
    db_repositories=["price"],
)
async def min_per_source_observation_coverage_pct(
    price_repository: PriceRepository,
) -> MetricResult:
    per_source = await price_repository.fetch_per_source_observation_coverage_pct()
    non_null = [v for v in per_source.values() if v is not None]
    headline = min(non_null) if non_null else None
    return MetricResult(row_count=headline, details={"per_source": per_source})
