"""Downstream outcome metrics — rows promoted, per-batch errors in bulk_load."""
from __future__ import annotations

from automana.core.metrics.registry import (
    MetricRegistry,
    MetricResult,
    Threshold,
)
from automana.core.repositories.app_integration.mtg_stock.price_repository import PriceRepository
from automana.core.repositories.ops.ops_repository import OpsRepository

PIPELINE_NAME = "mtg_stock_all"


async def _resolve_run_id(ops_repository: OpsRepository, ingestion_run_id: int | None) -> int | None:
    if ingestion_run_id is not None:
        return ingestion_run_id
    return await ops_repository.get_latest_run_id(PIPELINE_NAME)


@MetricRegistry.register(
    path="mtgstock.bulk_load_folder_errors",
    category="health",
    description="Sum of per-batch items_failed recorded by bulk_load.",
    severity=Threshold(warn=100, error=1_000, direction="higher_is_worse"),
    db_repositories=["ops"],
)
async def bulk_load_folder_errors(
    ops_repository: OpsRepository, ingestion_run_id: int | None = None
) -> MetricResult:
    run_id = await _resolve_run_id(ops_repository, ingestion_run_id)
    if run_id is None:
        return MetricResult(row_count=None, details={"reason": "no_runs_found"})

    count = await ops_repository.fetch_bulk_folder_errors(run_id)
    return MetricResult(row_count=count, details={"ingestion_run_id": run_id})


@MetricRegistry.register(
    path="mtgstock.rows_promoted_to_price_observation",
    category="volume",
    description="Rows promoted to pricing.price_observation inside the run's wall-clock window.",
    severity=Threshold(warn=100_000, error=1_000, direction="lower_is_worse"),
    db_repositories=["price", "ops"],
)
async def rows_promoted_to_price_observation(
    price_repository: PriceRepository,
    ops_repository: OpsRepository,
    ingestion_run_id: int | None = None,
) -> MetricResult:
    run_id = await _resolve_run_id(ops_repository, ingestion_run_id)
    if run_id is None:
        return MetricResult(row_count=None, details={"reason": "no_runs_found"})

    summary = await ops_repository.fetch_run_summary(run_id) or {}
    started_at = summary.get("started_at")
    ended_at = summary.get("ended_at")

    if started_at is None or ended_at is None:
        return MetricResult(
            row_count=None,
            details={
                "ingestion_run_id": run_id,
                "reason": "run_not_finished",
            },
        )

    count = await price_repository.fetch_promoted_count(
        since=started_at, until=ended_at, source_code="mtgstocks"
    )
    return MetricResult(
        row_count=count,
        details={
            "ingestion_run_id": run_id,
            "since": str(started_at),
            "until": str(ended_at),
        },
    )
