"""MTGStock sanity / run-summary report.

A runner service that dispatches a selected subset of registered
``mtgstock.*`` metrics and wraps their outcomes in the same report envelope
used by ``ops.integrity.scryfall_*`` services — so the existing
``pipeline-health-check`` skill and any downstream consumers see a uniform
shape across pipelines.

Selection is by name-list, category, or path prefix (any combination). With
no filters the runner returns every registered ``mtgstock.*`` metric.
"""
from __future__ import annotations

import importlib
import inspect
import logging
from typing import Any

from automana.core.metrics import MetricConfig, MetricRegistry, MetricResult, Severity
# Importing the mtgstock metrics package triggers registration of all
# ``mtgstock.*`` metrics via their @MetricRegistry.register decorators.
import automana.core.metrics.mtgstock  # noqa: F401
from automana.core.repositories.app_integration.mtg_stock.price_repository import PriceRepository
from automana.core.repositories.ops.ops_repository import OpsRepository
from automana.core.service_registry import ServiceRegistry
from automana.core.services.ops.integrity_checks import _build_report

logger = logging.getLogger(__name__)

_MTGSTOCK_PREFIX = "mtgstock."


def _normalize_names(metrics: str | list[str] | None) -> list[str] | None:
    """Accept either a comma-separated CLI string or a list; return list or None.

    The ``automana-run`` CLI passes ``--metrics a,b,c`` through as a single
    string (the coercer only handles scalars); the runner absorbs the split
    so callers don't have to.
    """
    if metrics is None:
        return None
    if isinstance(metrics, str):
        return [m.strip() for m in metrics.split(",") if m.strip()]
    return list(metrics)


def _resolve_metric_function(config: MetricConfig):
    module = importlib.import_module(config.module)
    return getattr(module, config.function)


async def _invoke_metric(
    config: MetricConfig,
    *,
    price_repository: PriceRepository,
    ops_repository: OpsRepository,
    ingestion_run_id: int | None,
) -> MetricResult:
    """Invoke a metric function passing only the kwargs its signature accepts.

    Mirrors the signature-filtering pattern ``run_service`` uses so a metric
    can declare only the repos it needs without breaking when invoked from a
    runner that injects a superset.
    """
    func = _resolve_metric_function(config)
    candidate_kwargs = {
        "price_repository": price_repository,
        "ops_repository": ops_repository,
        "ingestion_run_id": ingestion_run_id,
    }
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


@ServiceRegistry.register(
    "ops.integrity.mtgstock_report",
    db_repositories=["price", "ops"],
    # Pure-read report: no BEGIN/COMMIT wrapper. One failing metric query
    # would otherwise poison the transaction and turn every subsequent
    # metric into `InFailedSQLTransactionError`, defeating the per-metric
    # exception-swallowing below.
    runs_in_transaction=False,
)
async def mtgstock_report(
    price_repository: PriceRepository,
    ops_repository: OpsRepository,
    metrics: str | list[str] | None = None,
    category: str | None = None,
    ingestion_run_id: int | None = None,
) -> dict:
    """Run the mtgstock sanity report.

    Args:
        metrics: comma-separated string (CLI) or list of metric paths. When
            omitted, every registered ``mtgstock.*`` metric runs.
        category: filter by category — ``health``, ``volume``, ``timing``,
            or ``status``.
        ingestion_run_id: target a specific run id. When omitted, each metric
            resolves to the most recent ``mtg_stock_all`` run via
            ``OpsRepository.get_latest_run_id``.
    """
    names = _normalize_names(metrics)
    selected = MetricRegistry.select(
        names=names, category=category, prefix=_MTGSTOCK_PREFIX
    )

    if not selected:
        logger.warning(
            "mtgstock_report_no_metrics_selected",
            extra={"metrics": names, "category": category},
        )

    rows: list[dict[str, Any]] = []
    for config in selected:
        try:
            result = await _invoke_metric(
                config,
                price_repository=price_repository,
                ops_repository=ops_repository,
                ingestion_run_id=ingestion_run_id,
            )
        # Intentional broad catch: one misbehaving metric must not take the
        # whole report down. Failed metrics surface as error-severity rows
        # with an ``exception`` detail — same shape as healthy rows — so
        # downstream consumers (pipeline-health-check, the TUI) render
        # them without special-casing.
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "metric_invocation_failed",
                extra={"metric": config.path},
            )
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

    return _build_report("mtgstock_report", rows)
