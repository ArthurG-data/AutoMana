"""Run-level metrics — duration, status, per-step timing.

All metrics resolve ``ingestion_run_id=None`` to the most recent
``mtg_stock_all`` run via ``OpsRepository.get_latest_run_id``.
"""
from __future__ import annotations

from automana.core.metrics.registry import (
    MetricRegistry,
    MetricResult,
    Severity,
    Threshold,
)
from automana.core.repositories.ops.ops_repository import OpsRepository

PIPELINE_NAME = "mtg_stock_all"


async def _resolve_run_id(ops_repository: OpsRepository, ingestion_run_id: int | None) -> int | None:
    if ingestion_run_id is not None:
        return ingestion_run_id
    return await ops_repository.get_latest_run_id(PIPELINE_NAME)


def _status_severity(value: str | None) -> Severity:
    # `run_status` is categorical — a Threshold isn't meaningful, so we use
    # the Callable escape hatch instead of shoehorning strings into numbers.
    if value in ("success",):
        return Severity.OK
    if value in ("partial", "running", "pending"):
        return Severity.WARN
    return Severity.ERROR  # 'failed' or unknown


@MetricRegistry.register(
    path="mtgstock.pipeline_duration_seconds",
    category="timing",
    description="Wall-clock duration of the most recent mtgStock pipeline run.",
    severity=Threshold(warn=1800, error=3600, direction="higher_is_worse"),
    db_repositories=["ops"],
)
async def pipeline_duration_seconds(
    ops_repository: OpsRepository, ingestion_run_id: int | None = None
) -> MetricResult:
    run_id = await _resolve_run_id(ops_repository, ingestion_run_id)
    if run_id is None:
        return MetricResult(row_count=None, details={"reason": "no_runs_found"})

    summary = await ops_repository.fetch_run_summary(run_id) or {}
    return MetricResult(
        row_count=summary.get("duration_seconds"),
        details={
            "ingestion_run_id": run_id,
            "started_at": str(summary.get("started_at")),
            "ended_at": str(summary.get("ended_at")),
        },
    )


@MetricRegistry.register(
    path="mtgstock.run_status",
    category="status",
    description="Final status of the most recent mtgStock pipeline run.",
    severity=_status_severity,
    db_repositories=["ops"],
)
async def run_status(
    ops_repository: OpsRepository, ingestion_run_id: int | None = None
) -> MetricResult:
    run_id = await _resolve_run_id(ops_repository, ingestion_run_id)
    if run_id is None:
        return MetricResult(row_count=None, details={"reason": "no_runs_found"})

    summary = await ops_repository.fetch_run_summary(run_id) or {}
    return MetricResult(
        row_count=summary.get("status"),
        details={
            "ingestion_run_id": run_id,
            "current_step": summary.get("current_step"),
            "error_code": summary.get("error_code"),
        },
    )


@MetricRegistry.register(
    path="mtgstock.steps_failed_count",
    category="health",
    description="Number of ingestion steps with status='failed' in the run.",
    severity=Threshold(warn=1, error=1, direction="higher_is_worse"),
    db_repositories=["ops"],
)
async def steps_failed_count(
    ops_repository: OpsRepository, ingestion_run_id: int | None = None
) -> MetricResult:
    run_id = await _resolve_run_id(ops_repository, ingestion_run_id)
    if run_id is None:
        return MetricResult(row_count=None, details={"reason": "no_runs_found"})

    count = await ops_repository.fetch_steps_failed_count(run_id)
    return MetricResult(row_count=count, details={"ingestion_run_id": run_id})


@MetricRegistry.register(
    path="mtgstock.step_durations",
    category="timing",
    description="Per-step wall-clock durations in seconds for the run.",
    severity=None,  # informational — no pass/fail threshold applies uniformly
    db_repositories=["ops"],
)
async def step_durations(
    ops_repository: OpsRepository, ingestion_run_id: int | None = None
) -> MetricResult:
    run_id = await _resolve_run_id(ops_repository, ingestion_run_id)
    if run_id is None:
        return MetricResult(row_count=None, details={"reason": "no_runs_found"})

    durations = await ops_repository.fetch_step_durations(run_id)
    total = sum((d for d in durations.values() if d is not None), 0.0)
    return MetricResult(
        row_count=total,
        details={
            "ingestion_run_id": run_id,
            "durations_seconds": durations,
        },
    )
