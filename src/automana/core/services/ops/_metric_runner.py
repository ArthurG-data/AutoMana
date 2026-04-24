"""Shared dispatch helper for ops.integrity.<family>_report services.

Mirrors the original `mtgstock_report.py` private helpers verbatim, then
generalizes the kwargs injection so every runner can declare its own
repository set without copy-pasting the dispatch loop.
"""
from __future__ import annotations

import importlib
import inspect
import logging
from typing import Any

from automana.core.metrics import MetricConfig, MetricRegistry, MetricResult, Severity
from automana.core.services.ops.integrity_checks import _build_report

logger = logging.getLogger(__name__)


def _normalize_names(metrics: str | list[str] | None) -> list[str] | None:
    """Accept either a comma-separated CLI string or a list; return list or None."""
    if metrics is None:
        return None
    if isinstance(metrics, str):
        return [m.strip() for m in metrics.split(",") if m.strip()]
    return list(metrics)


def _resolve_metric_function(config: MetricConfig):
    module = importlib.import_module(config.module)
    return getattr(module, config.function)


async def _invoke_metric(config: MetricConfig, candidate_kwargs: dict[str, Any]) -> MetricResult:
    """Invoke a metric function passing only the kwargs its signature accepts."""
    func = _resolve_metric_function(config)
    allowed = set(inspect.signature(func).parameters.keys())
    kwargs = {k: v for k, v in candidate_kwargs.items() if k in allowed}
    return await func(**kwargs)


def _result_to_row(config: MetricConfig, result: MetricResult) -> dict[str, Any]:
    severity = MetricRegistry.evaluate(config, result.row_count)
    return {
        "check_name": config.path,
        "severity": severity.value if isinstance(severity, Severity) else str(severity),
        "row_count": result.row_count,
        "details": {
            **result.details,
            "description": config.description,
            "category": config.category,
        },
    }


async def run_metric_report(
    *,
    check_set: str,
    prefix: str,
    metrics: str | list[str] | None,
    category: str | None,
    repositories: dict[str, Any],
    extra_kwargs: dict[str, Any] | None = None,
) -> dict:
    """Run every metric matching prefix + filters and return the standard envelope.

    `repositories` is the full kwargs dict the caller wants to make available
    (e.g. {"price_repository": ..., "ops_repository": ...}). `extra_kwargs`
    folds in non-repository values like `ingestion_run_id`. Per metric, only
    the kwargs whose names match the function signature are passed.
    """
    names = _normalize_names(metrics)
    selected = MetricRegistry.select(names=names, category=category, prefix=prefix)

    if not selected:
        logger.warning(
            "metric_report_no_metrics_selected",
            extra={"check_set": check_set, "metrics": names, "category": category},
        )

    candidate_kwargs: dict[str, Any] = {**repositories, **(extra_kwargs or {})}
    rows: list[dict[str, Any]] = []
    for config in selected:
        try:
            result = await _invoke_metric(config, candidate_kwargs)
        except Exception as exc:  # noqa: BLE001 — one bad metric must not take the report down
            logger.exception("metric_invocation_failed", extra={"metric": config.path})
            rows.append({
                "check_name": config.path,
                "severity": Severity.ERROR.value,
                "row_count": None,
                "details": {
                    "exception": f"{type(exc).__name__}: {exc}",
                    "description": config.description,
                    "category": config.category,
                },
            })
            continue
        rows.append(_result_to_row(config, result))

    return _build_report(check_set, rows)
