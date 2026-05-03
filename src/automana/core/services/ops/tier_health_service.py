"""Tier 2 / Tier 3 health-check service.

Registered service key: ``ops.integrity.pricing_tier_health``

This service runs every ``pricing.tier.*`` metric (registered in
``automana.core.metrics.pricing.tier_metrics``) and returns the standard
integrity-report envelope used by every other ``ops.integrity.*`` service::

    {
        "check_set":     "pricing_tier_health",
        "total_checks":  int,
        "error_count":   int,
        "warn_count":    int,
        "ok_count":      int,
        "errors":        list[dict],
        "warnings":      list[dict],
        "passed":        list[dict],
        "rows":          list[dict],
    }

Each row dict carries the metric path as ``check_name``, a severity of
``"ok"`` / ``"warn"`` / ``"error"``, the scalar ``row_count``, and a
``details`` dict with supporting context (e.g. ``tier1_rows``, ``tier2_rows``,
``cutoff_date``).

The service is automatically included in the
``ops.health.alert_check`` sweep because that service discovers all registered
``ops.integrity.*`` keys at runtime.  Discord alerts for this check_set are
bucketed under the ``pricing`` pipeline (see ``health_alert_service.py``
``_KNOWN_PIPELINES``).

Metrics wired in
────────────────
  pricing.tier.tier2_row_count            — Tier 2 estimated row count (volume)
  pricing.tier.tier3_row_count            — Tier 3 estimated row count (volume)
  pricing.tier.sync_diff                  — abs(tier1 - tier2) row count diff (health)
  pricing.tier.archival_ready_rows        — Tier 2 rows > 5 years old (status)
  pricing.tier.daily_watermark_lag_days   — days since daily watermark advanced (timing)
  pricing.tier.weekly_watermark_lag_days  — days since weekly watermark advanced (timing)

Relationship to pricing_report
───────────────────────────────
``ops.integrity.pricing_report`` filters with ``prefix="pricing."`` so the
same tier metrics are also reported there.  This dedicated service exists so
an operator can run tier-health in isolation (useful in alerting rules that
want a single focused check-set) and so that ``ops.health.alert_check`` can
track tier health transitions independently of the broader pricing report.
"""
from __future__ import annotations

import logging

# Side-effect import: registers all pricing.* metrics (including pricing.tier.*)
# into MetricRegistry so that run_metric_report can find them via prefix.
import automana.core.metrics.pricing  # noqa: F401

from automana.core.repositories.app_integration.mtg_stock.price_repository import (
    PriceRepository,
)
from automana.core.service_registry import ServiceRegistry
from automana.core.services.ops._metric_runner import run_metric_report

logger = logging.getLogger(__name__)


@ServiceRegistry.register(
    "ops.integrity.pricing_tier_health",
    db_repositories=["price"],
)
async def pricing_tier_health(
    price_repository: PriceRepository,
    metrics: str | list[str] | None = None,
    category: str | None = None,
) -> dict:
    """Run all pricing.tier.* health metrics and return the standard report envelope.

    Args:
        metrics:  Comma-separated string (CLI) or list of exact metric paths to
                  run.  When None all ``pricing.tier.*`` metrics are executed.
        category: Optional category filter — ``health``, ``volume``,
                  ``timing``, or ``status``.  Ignored when ``metrics`` is set.

    Returns:
        Standard integrity-report dict (see module docstring).
    """
    return await run_metric_report(
        check_set="pricing_tier_health",
        prefix="pricing.tier.",
        metrics=metrics,
        category=category,
        repositories={"price_repository": price_repository},
    )
