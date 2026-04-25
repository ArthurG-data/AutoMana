"""pricing.card_coverage.* — catalog-side price coverage metrics.

Measures how many of the known MTG card versions actually have price
observations in the canonical table, broken down by foil finish.

Distinct from ``pricing.coverage.*`` which measures coverage from the
source-product side (% of source-registered products with a recent price).
"""
from __future__ import annotations

from automana.core.metrics.registry import MetricRegistry, MetricResult, Threshold
from automana.core.repositories.app_integration.mtg_stock.price_repository import PriceRepository


async def _get_stats(price_repository: PriceRepository) -> dict:
    return await price_repository.fetch_card_coverage_stats()


@MetricRegistry.register(
    path="pricing.card_coverage.catalog_coverage_pct",
    category="health",
    description="% of card_versions in card_catalog that have at least one price_observation.",
    severity=Threshold(warn=50, error=20, direction="lower_is_worse"),
    db_repositories=["price"],
)
async def catalog_coverage_pct(price_repository: PriceRepository) -> MetricResult:
    stats = await _get_stats(price_repository)
    total = stats["total_card_versions"]
    with_price = stats["with_price"]
    pct = round(100.0 * with_price / total, 2) if total else None
    return MetricResult(
        row_count=pct,
        details={
            "total_card_versions": total,
            "with_price": with_price,
            "without_price": stats["without_price"],
        },
    )


@MetricRegistry.register(
    path="pricing.card_coverage.card_versions_with_any_price",
    category="volume",
    description="Count of card_versions with at least one price_observation (any finish).",
    severity=None,
    db_repositories=["price"],
)
async def card_versions_with_any_price(price_repository: PriceRepository) -> MetricResult:
    stats = await _get_stats(price_repository)
    return MetricResult(
        row_count=stats["with_price"],
        details={"total_card_versions": stats["total_card_versions"]},
    )


@MetricRegistry.register(
    path="pricing.card_coverage.card_versions_without_price",
    category="health",
    description="Count of card_versions with zero price observations.",
    severity=Threshold(warn=10_000, error=50_000, direction="higher_is_worse"),
    db_repositories=["price"],
)
async def card_versions_without_price(price_repository: PriceRepository) -> MetricResult:
    stats = await _get_stats(price_repository)
    return MetricResult(
        row_count=stats["without_price"],
        details={"total_card_versions": stats["total_card_versions"]},
    )


@MetricRegistry.register(
    path="pricing.card_coverage.card_versions_with_nonfoil_price",
    category="volume",
    description="Count of card_versions with at least one NONFOIL price observation.",
    severity=None,
    db_repositories=["price"],
)
async def card_versions_with_nonfoil_price(price_repository: PriceRepository) -> MetricResult:
    stats = await _get_stats(price_repository)
    return MetricResult(
        row_count=stats["with_nonfoil_price"],
        details={"total_card_versions": stats["total_card_versions"]},
    )


@MetricRegistry.register(
    path="pricing.card_coverage.card_versions_with_foil_price",
    category="volume",
    description="Count of card_versions with at least one foil (FOIL/ETCHED) price observation.",
    severity=None,
    db_repositories=["price"],
)
async def card_versions_with_foil_price(price_repository: PriceRepository) -> MetricResult:
    stats = await _get_stats(price_repository)
    return MetricResult(
        row_count=stats["with_foil_price"],
        details={"total_card_versions": stats["total_card_versions"]},
    )


@MetricRegistry.register(
    path="pricing.card_coverage.total_observation_rows",
    category="volume",
    description="Estimated total rows in pricing.price_observation (via pg_class.reltuples — fast, not exact).",
    severity=Threshold(warn=500_000, error=10_000, direction="lower_is_worse"),
    db_repositories=["price"],
)
async def total_observation_rows(price_repository: PriceRepository) -> MetricResult:
    n = await price_repository.fetch_total_observation_count()
    return MetricResult(row_count=n)
