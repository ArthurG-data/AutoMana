"""pricing.* — referential soft-integrity, staging drain, duplicate detection."""
from __future__ import annotations

from automana.core.metrics.registry import MetricRegistry, MetricResult, Threshold
from automana.core.repositories.app_integration.mtg_stock.price_repository import PriceRepository


@MetricRegistry.register(
    path="pricing.referential.product_without_mtg_card_products",
    category="health",
    description="pricing.product_ref rows with game=mtg but no mtg_card_products row.",
    severity=Threshold(warn=5, error=20, direction="higher_is_worse"),
    db_repositories=["price"],
)
async def product_without_mtg_card_products(price_repository: PriceRepository) -> MetricResult:
    n = await price_repository.fetch_orphan_product_ref_mtg_count()
    return MetricResult(row_count=n)


@MetricRegistry.register(
    path="pricing.referential.observation_without_source_product",
    category="health",
    description="pricing.price_observation rows whose source_product_id no longer exists in source_product.",
    severity=Threshold(warn=1, error=10, direction="higher_is_worse"),
    db_repositories=["price"],
)
async def observation_without_source_product(price_repository: PriceRepository) -> MetricResult:
    n = await price_repository.fetch_orphan_observation_count()
    return MetricResult(row_count=n)


@MetricRegistry.register(
    path="pricing.staging.stg_price_observation_residual_count",
    category="volume",
    description="Estimated row count of stg_price_observation (should drain to ~0 between runs).",
    severity=Threshold(warn=1_000_000, error=5_000_000, direction="higher_is_worse"),
    db_repositories=["price"],
)
async def stg_price_observation_residual_count(price_repository: PriceRepository) -> MetricResult:
    n = await price_repository.fetch_stg_residual_count()
    return MetricResult(row_count=n)


@MetricRegistry.register(
    path="pricing.duplicate_detection.observation_duplicates_on_pk",
    category="health",
    description="Composite-PK violations in price_observation (should always be 0).",
    severity=Threshold(warn=1, error=1, direction="higher_is_worse"),
    db_repositories=["price"],
)
async def observation_duplicates_on_pk(price_repository: PriceRepository) -> MetricResult:
    n = await price_repository.fetch_observation_pk_collision_count()
    return MetricResult(row_count=n)
