"""Card-catalog sanity report. Runs every registered card_catalog.* metric."""
from __future__ import annotations

import logging

import automana.core.metrics.card_catalog  # noqa: F401  — register card_catalog.* metrics
from automana.core.repositories.card_catalog.card_repository import CardReferenceRepository
from automana.core.repositories.ops.ops_repository import OpsRepository
from automana.core.service_registry import ServiceRegistry
from automana.core.services.ops._metric_runner import run_metric_report

logger = logging.getLogger(__name__)


@ServiceRegistry.register(
    "ops.integrity.card_catalog_report",
    db_repositories=["card", "ops"],
)
async def card_catalog_report(
    card_repository: CardReferenceRepository,
    ops_repository: OpsRepository,
    metrics: str | list[str] | None = None,
    category: str | None = None,
) -> dict:
    """Run the card_catalog sanity report.

    Args:
        metrics:  comma-separated string (CLI) or list of metric paths.
        category: filter by category — ``health``, ``volume``, ``timing``, ``status``.
    """
    return await run_metric_report(
        check_set="card_catalog_report",
        prefix="card_catalog.",
        metrics=metrics,
        category=category,
        repositories={
            "card_repository": card_repository,
            "ops_repository": ops_repository,
        },
    )
