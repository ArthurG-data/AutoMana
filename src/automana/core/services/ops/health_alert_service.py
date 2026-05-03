"""HealthAlertService — runs every ops.integrity.* service, persists each
result as a row in ops.pipeline_health_snapshot, and posts a Discord alert
only when a check_set's health status transitions vs the prior run.

Registered as ``ops.health.alert_check`` (registration is added in this file
in the next task).

Pure helpers live at module scope so they are unit-testable without a DB.
"""
from __future__ import annotations

from typing import Any, Optional

# Pipelines we recognize as a source-prefix on check_set names. New pipelines
# get added here by editing this list; unknown prefixes fall through to
# 'infrastructure' so the table stays tidy.
# "pricing" covers check_sets whose names start with "pricing_" (e.g.
# "pricing_tier_health", "pricing_report", "pricing_integrity").
_KNOWN_PIPELINES = {"scryfall", "mtgjson", "mtgstock", "pricing"}

_ICON = {"ok": "✅", "warn": "⚠️", "error": "❌"}


def derive_status(*, error_count: int, warn_count: int) -> str:
    """Derive 'ok' | 'warn' | 'error' from the integrity report counts."""
    if error_count > 0:
        return "error"
    if warn_count > 0:
        return "warn"
    return "ok"


def derive_pipeline(check_set: str) -> str:
    """Map a check_set to a pipeline group.

    Rule: take the substring before the first '_'. If that prefix matches a
    known pipeline name, use it; otherwise the check_set is a cross-cutting
    concern and lives under 'infrastructure'.
    """
    prefix = check_set.split("_", 1)[0]
    return prefix if prefix in _KNOWN_PIPELINES else "infrastructure"


def classify_transition(
    *,
    prior: Optional[dict[str, Any]],
    current: dict[str, Any],
) -> str:
    """Classify the new snapshot relative to the prior one.

    Returns one of: 'baseline', 'unchanged', 'degraded', 'recovered'.
    """
    if prior is None:
        return "baseline"
    rank = {"ok": 0, "warn": 1, "error": 2}
    prev = rank[prior["status"]]
    cur = rank[current["status"]]
    if cur == prev:
        return "unchanged"
    return "degraded" if cur > prev else "recovered"


def _format_line(t: dict[str, Any]) -> str:
    icon_from = _ICON[t["from_status"]]
    icon_to = _ICON[t["to_status"]]
    return f"· {t['check_set']}: {icon_from} → {icon_to} ({t['delta_summary']})"


def format_discord_payload(
    *,
    captured_at_iso: str,
    degraded: list[dict[str, Any]],
    recovered: list[dict[str, Any]],
    run_id: str,
) -> Optional[str]:
    """Build the transition-only Discord message body.

    Returns None when there is nothing to alert on. The 2000-char Discord
    limit is enforced by truncating to the top 5 transitions of each kind
    and appending a count of how many were dropped.
    """
    if not degraded and not recovered:
        return None

    MAX = 5

    def _block(label: str, items: list[dict[str, Any]]) -> list[str]:
        if not items:
            return []
        head = items[:MAX]
        tail = items[MAX:]
        lines = [label + ":"] + [_format_line(t) for t in head]
        if tail:
            lines.append(f"… and {len(tail)} more (run_id={run_id})")
        return lines

    if degraded and recovered:
        header = f"⚠️ Pipeline health changed — {captured_at_iso}"
        body = _block("Degraded", degraded) + _block("Recovered", recovered)
    elif degraded:
        header = f"⚠️ Pipeline health degraded — {captured_at_iso}"
        body = [_format_line(t) for t in degraded[:MAX]]
        if len(degraded) > MAX:
            body.append(f"… and {len(degraded) - MAX} more (run_id={run_id})")
    else:
        header = f"✅ Pipeline health recovered — {captured_at_iso}"
        body = [_format_line(t) for t in recovered[:MAX]]
        if len(recovered) > MAX:
            body.append(f"… and {len(recovered) - MAX} more (run_id={run_id})")

    return "\n".join([header] + body)


import logging
import traceback
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx

_SYDNEY_TZ = ZoneInfo("Australia/Sydney")

from automana.core.repositories.ops.pipeline_health_snapshot_repository import (
    PipelineHealthSnapshotRepository,
    PipelineHealthSnapshotRow,
)
from automana.core.service_registry import ServiceRegistry
from automana.core.settings import get_settings

logger = logging.getLogger(__name__)


# ---------- side-effecting helpers (overridable for testing) ----------

def _discover_integrity_services() -> list[str]:
    """Return all registered service keys whose name starts with 'ops.integrity.'."""
    return sorted(
        k for k in ServiceRegistry.list_services()
        if k.startswith("ops.integrity.")
    )


async def _run_integrity_service(service_key: str) -> dict:
    """Run a single integrity service in-process via ServiceManager.

    We deliberately do NOT go through ``automana.worker.main.run_service``
    here — that's the Celery task wrapper used to schedule services as
    Celery jobs. Inside another service we want a direct, awaited call.
    ``ServiceManager.execute_service`` is the right entry point: it
    instantiates declared repositories from the registry and runs the
    target service in the current event loop.
    """
    from automana.core.service_manager import ServiceManager
    return await ServiceManager.execute_service(service_key)


def _get_webhook_url() -> Optional[str]:
    return get_settings().DISCORD_WEBHOOK_URL


async def _post_to_discord(webhook_url: str, body: str) -> tuple[int, str]:
    """POST the body to Discord. Returns (status_code, response_body); never logs the URL."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(webhook_url, json={"content": body})
    return resp.status_code, resp.text


# ---------- main service ----------

def _delta_summary(report: dict) -> str:
    err = report.get("error_count", 0)
    warns = report.get("warn_count", 0)
    if err > 0:
        errors = report.get("errors") or []
        top = errors[0] if errors else None
        if top is not None:
            details = (top.get("details") or "")
            if isinstance(details, list):
                details = f"[{len(details)} rows]"
            details = str(details)[:60]
            return f"{err} new error(s), top: {top.get('check_name')} {details}".rstrip()
        return f"{err} new error(s)"
    if warns > 0:
        return f"{warns} new warning(s)"
    return "all clear"


def _row_from_report(run_id: uuid.UUID, report: dict) -> PipelineHealthSnapshotRow:
    cs = report.get("check_set") or "unknown"
    err = int(report.get("error_count", 0))
    warn = int(report.get("warn_count", 0))
    return PipelineHealthSnapshotRow(
        run_id=run_id,
        check_set=cs,
        pipeline=derive_pipeline(cs),
        status=derive_status(error_count=err, warn_count=warn),
        error_count=err,
        warn_count=warn,
        total_checks=int(report.get("total_checks", 0)),
        report=report,
    )


def _row_from_exception(run_id: uuid.UUID, service_key: str, exc: BaseException) -> PipelineHealthSnapshotRow:
    cs = service_key.removeprefix("ops.integrity.")
    return PipelineHealthSnapshotRow(
        run_id=run_id,
        check_set=cs,
        pipeline=derive_pipeline(cs),
        status="error",
        error_count=1,
        warn_count=0,
        total_checks=0,
        report={
            "check_set": cs,
            "exception": "".join(traceback.format_exception_only(type(exc), exc)).strip(),
            "traceback": "".join(traceback.format_exception(exc)),
            "service_key": service_key,
        },
    )


@ServiceRegistry.register(
    "ops.health.alert_check",
    db_repositories=["pipeline_health_snapshot"],
)
async def run_alert_check(
    pipeline_health_snapshot_repository: PipelineHealthSnapshotRepository,
) -> dict:
    """Run every ops.integrity.* service, persist a snapshot row per result,
    diff against the prior snapshot for each check_set, and alert Discord
    only when status transitions exist.
    """
    run_id = uuid.uuid4()
    captured_at = datetime.now(timezone.utc)
    captured_at_str = captured_at.astimezone(_SYDNEY_TZ).strftime("%Y-%m-%d %H:%M %Z")

    keys = _discover_integrity_services()
    rows: list[PipelineHealthSnapshotRow] = []
    for key in keys:
        try:
            report = await _run_integrity_service(key)
            rows.append(_row_from_report(run_id, report))
        except BaseException as exc:  # capture even SystemExit-shaped tracebacks
            logger.warning(
                "integrity_service_failed",
                extra={"service_key": key, "exc_type": type(exc).__name__},
            )
            rows.append(_row_from_exception(run_id, key, exc))

    await pipeline_health_snapshot_repository.insert_snapshots(rows)

    degraded: list[dict] = []
    recovered: list[dict] = []
    baselines: list[str] = []
    for r in rows:
        prior = await pipeline_health_snapshot_repository.latest_for_check_set(
            check_set=r.check_set, exclude_run_id=run_id,
        )
        current = {
            "status": r.status,
            "error_count": r.error_count,
            "warn_count": r.warn_count,
        }
        verdict = classify_transition(prior=prior, current=current)
        if verdict == "baseline":
            baselines.append(r.check_set)
            continue
        if verdict == "unchanged":
            continue
        item = {
            "check_set": r.check_set,
            "pipeline": r.pipeline,
            "from_status": prior["status"] if prior else "ok",
            "to_status": r.status,
            "delta_summary": _delta_summary(r.report),
        }
        (degraded if verdict == "degraded" else recovered).append(item)

    payload = format_discord_payload(
        captured_at_iso=captured_at_str,
        degraded=degraded,
        recovered=recovered,
        run_id=str(run_id),
    )

    alerted = False
    webhook = _get_webhook_url()
    if payload is not None and webhook:
        try:
            status, response_body = await _post_to_discord(webhook, payload)
            alerted = 200 <= status < 300
            if alerted:
                logger.info(
                    "discord_alert_sent",
                    extra={"degraded": len(degraded), "recovered": len(recovered)},
                )
            else:
                logger.warning(
                    "discord_post_non_2xx",
                    extra={"http_status": status, "response_body": response_body[:500]},
                )
        except Exception as exc:
            logger.warning("discord_post_failed", extra={"exc_type": type(exc).__name__})
    elif payload is not None:
        logger.warning("discord_webhook_unset_skipping_alert")

    return {
        "run_id": str(run_id),
        "total_check_sets": len(rows),
        "degraded": degraded,
        "recovered": recovered,
        "baselines": baselines,
        "alerted": alerted,
    }
