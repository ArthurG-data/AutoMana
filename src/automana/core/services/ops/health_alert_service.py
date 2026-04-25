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
_KNOWN_PIPELINES = {"scryfall", "mtgjson", "mtgstock"}

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
            lines.append(f"… and {len(tail)} more")
        return lines

    if degraded and recovered:
        header = f"⚠️ Pipeline health changed — {captured_at_iso}"
        body = _block("Degraded", degraded) + _block("Recovered", recovered)
    elif degraded:
        header = f"⚠️ Pipeline health degraded — {captured_at_iso}"
        body = [_format_line(t) for t in degraded[:MAX]]
        if len(degraded) > MAX:
            body.append(f"… and {len(degraded) - MAX} more")
    else:
        header = f"✅ Pipeline health recovered — {captured_at_iso}"
        body = [_format_line(t) for t in recovered[:MAX]]
        if len(recovered) > MAX:
            body.append(f"… and {len(recovered) - MAX} more")

    return "\n".join([header] + body)
