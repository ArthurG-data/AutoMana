"""MTGStock sanity / run-summary report.

A runner service that dispatches a selected subset of registered
``mtgstock.*`` metrics via the shared `_metric_runner.run_metric_report`
helper.
"""
from __future__ import annotations

import logging

# Importing the package triggers registration of all mtgstock.* metrics.
import automana.core.metrics.mtgstock  # noqa: F401
from automana.core.repositories.app_integration.mtg_stock.price_repository import PriceRepository
from automana.core.repositories.ops.ops_repository import OpsRepository
from automana.core.service_registry import ServiceRegistry
from automana.core.services.ops._metric_runner import _normalize_names, run_metric_report

logger = logging.getLogger(__name__)

# Re-exported so existing tests that import _normalize_names from this module
# keep working without modification.
__all__ = ["mtgstock_report", "_normalize_names"]


@ServiceRegistry.register(
    "ops.integrity.mtgstock_report",
    db_repositories=["price", "ops"],
)
async def mtgstock_report(
    price_repository: PriceRepository,
    ops_repository: OpsRepository,
    metrics: str | list[str] | None = None,
    category: str | None = None,
    ingestion_run_id: int | None = None,
) -> dict:
    """Run the mtgstock sanity report. See `MetricRegistry` docs for selection semantics."""
    report = await run_metric_report(
        check_set="mtgstock_report",
        prefix="mtgstock.",
        metrics=metrics,
        category=category,
        repositories={
            "price_repository": price_repository,
            "ops_repository": ops_repository,
        },
        extra_kwargs={"ingestion_run_id": ingestion_run_id},
    )
    if report["total_checks"] == 0:
        logger.warning(
            "mtgstock_report_no_metrics_selected",
            extra={"metrics_arg": metrics, "category": category},
        )
    return report
