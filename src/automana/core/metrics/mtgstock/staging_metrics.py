"""Staging-table metrics — raw counts, link rate, reject counts.

These metrics read the *current state* of the pricing staging tables. They
do not filter by ``ingestion_run_id`` because neither ``raw_mtg_stock_price``
nor ``stg_price_observation`` carries a run column — the staging tables are
repopulated per-run, so "current state after the most recent run" is the
only meaningful run-scope. Same semantic as ``ops.integrity.scryfall_run_diff``.
"""
from __future__ import annotations

from automana.core.metrics.registry import (
    MetricRegistry,
    MetricResult,
    Threshold,
)
from automana.core.repositories.app_integration.mtg_stock.price_repository import PriceRepository


@MetricRegistry.register(
    path="mtgstock.raw_prints_loaded",
    category="volume",
    description="Distinct print_id count currently in pricing.raw_mtg_stock_price.",
    severity=Threshold(warn=50_000, error=1_000, direction="lower_is_worse"),
    db_repositories=["price"],
)
async def raw_prints_loaded(
    price_repository: PriceRepository, ingestion_run_id: int | None = None
) -> MetricResult:
    count = await price_repository.fetch_raw_prints_count()
    return MetricResult(row_count=count)


@MetricRegistry.register(
    path="mtgstock.raw_rows_loaded",
    category="volume",
    description="Total row count currently in pricing.raw_mtg_stock_price.",
    severity=Threshold(warn=500_000, error=10_000, direction="lower_is_worse"),
    db_repositories=["price"],
)
async def raw_rows_loaded(
    price_repository: PriceRepository, ingestion_run_id: int | None = None
) -> MetricResult:
    count = await price_repository.fetch_raw_rows_count()
    return MetricResult(row_count=count)


@MetricRegistry.register(
    path="mtgstock.cards_linked_to_card_version",
    category="volume",
    description="Staged rows successfully resolved to a card_version_id.",
    severity=Threshold(warn=50_000, error=1_000, direction="lower_is_worse"),
    db_repositories=["price"],
)
async def cards_linked_to_card_version(
    price_repository: PriceRepository, ingestion_run_id: int | None = None
) -> MetricResult:
    count = await price_repository.fetch_linked_count()
    return MetricResult(row_count=count)


@MetricRegistry.register(
    path="mtgstock.cards_rejected",
    category="health",
    description="Rows that failed card_version resolution and landed in the reject table.",
    severity=Threshold(warn=5_000, error=50_000, direction="higher_is_worse"),
    db_repositories=["price"],
)
async def cards_rejected(
    price_repository: PriceRepository, ingestion_run_id: int | None = None
) -> MetricResult:
    count = await price_repository.fetch_rejected_count()
    return MetricResult(row_count=count)


@MetricRegistry.register(
    path="mtgstock.link_rate_pct",
    category="health",
    description="% of staged rows (linked + rejected) that resolved to a card_version_id.",
    severity=Threshold(warn=95, error=80, direction="lower_is_worse"),
    db_repositories=["price"],
)
async def link_rate_pct(
    price_repository: PriceRepository, ingestion_run_id: int | None = None
) -> MetricResult:
    linked = await price_repository.fetch_linked_count()
    rejected = await price_repository.fetch_rejected_count()
    denom = linked + rejected

    rate = round(100.0 * linked / denom, 2) if denom else None
    return MetricResult(
        row_count=rate,
        details={"linked": linked, "rejected": rejected, "denominator": denom},
    )
