"""Pricing data-quality report. Runs every registered pricing.* metric."""
from __future__ import annotations

import logging

import automana.core.metrics.pricing  # noqa: F401  — register pricing.* metrics
from automana.core.repositories.app_integration.mtg_stock.price_repository import PriceRepository
from automana.core.repositories.ops.ops_repository import OpsRepository
from automana.core.service_registry import ServiceRegistry
from automana.core.services.ops._metric_runner import run_metric_report

logger = logging.getLogger(__name__)


@ServiceRegistry.register(
    "ops.integrity.pricing_report",
    db_repositories=["price", "ops"],
)
async def pricing_report(
    price_repository: PriceRepository,
    ops_repository: OpsRepository,
    metrics: str | list[str] | None = None,
    category: str | None = None,
) -> dict:
    """Run the pricing data-quality report.

    Args:
        metrics:  comma-separated string (CLI) or list of metric paths.
        category: filter by category — ``health``, ``volume``, ``timing``, ``status``.
    """
    return await run_metric_report(
        check_set="pricing_report",
        prefix="pricing.",
        metrics=metrics,
        category=category,
        repositories={
            "price_repository": price_repository,
            "ops_repository": ops_repository,
        },
    )
