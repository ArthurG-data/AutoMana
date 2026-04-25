"""Unit tests for HealthAlertService pure helpers.

The orchestration layer (the service function itself) is tested with
stubbed deps in a later test in this file. These tests cover the
side-effect-free helpers.
"""
from __future__ import annotations

import pytest

from automana.core.services.ops.health_alert_service import (
    classify_transition,
    derive_pipeline,
    derive_status,
    format_discord_payload,
)


# ---------- derive_status ----------

@pytest.mark.parametrize(
    "errors,warns,expected",
    [
        (0, 0, "ok"),
        (0, 5, "warn"),
        (1, 0, "error"),
        (3, 9, "error"),
    ],
)
def test_derive_status(errors, warns, expected):
    assert derive_status(error_count=errors, warn_count=warns) == expected


# ---------- derive_pipeline ----------

@pytest.mark.parametrize(
    "check_set,expected",
    [
        ("scryfall_integrity", "scryfall"),
        ("scryfall_run_diff", "scryfall"),
        ("mtgstock_report", "mtgstock"),
        ("mtgjson_orphans", "mtgjson"),
        ("public_schema_leak", "infrastructure"),
        ("vendor_x_audit", "infrastructure"),
    ],
)
def test_derive_pipeline(check_set, expected):
    assert derive_pipeline(check_set) == expected


# ---------- classify_transition ----------

def _snap(status: str) -> dict:
    return {"status": status, "error_count": 1 if status == "error" else 0,
            "warn_count": 1 if status == "warn" else 0}


def test_classify_baseline_when_no_prior():
    assert classify_transition(prior=None, current=_snap("error")) == "baseline"


def test_classify_unchanged_when_status_equal():
    assert classify_transition(prior=_snap("ok"), current=_snap("ok")) == "unchanged"
    assert classify_transition(prior=_snap("error"), current=_snap("error")) == "unchanged"


@pytest.mark.parametrize(
    "prior_status,current_status",
    [("ok", "warn"), ("ok", "error"), ("warn", "error")],
)
def test_classify_degraded(prior_status, current_status):
    assert classify_transition(
        prior=_snap(prior_status),
        current=_snap(current_status),
    ) == "degraded"


@pytest.mark.parametrize(
    "prior_status,current_status",
    [("warn", "ok"), ("error", "ok"), ("error", "warn")],
)
def test_classify_recovered(prior_status, current_status):
    assert classify_transition(
        prior=_snap(prior_status),
        current=_snap(current_status),
    ) == "recovered"


# ---------- format_discord_payload ----------

def test_format_discord_payload_returns_none_when_no_transitions():
    payload = format_discord_payload(
        captured_at_iso="2026-04-25T20:00:00+10:00",
        degraded=[],
        recovered=[],
    )
    assert payload is None


def test_format_discord_payload_degraded_only():
    payload = format_discord_payload(
        captured_at_iso="2026-04-25T20:00:00+10:00",
        degraded=[
            {
                "check_set": "mtgstock_report",
                "pipeline": "mtgstock",
                "from_status": "ok",
                "to_status": "error",
                "delta_summary": "10 new errors, top: pricing.stg_price_observation_reject does not exist",
            }
        ],
        recovered=[],
    )
    assert payload is not None
    assert "degraded" in payload.lower()
    assert "mtgstock" in payload
    assert "✅ → ❌" in payload


def test_format_discord_payload_truncates_when_more_than_five():
    many = [
        {
            "check_set": f"check_{i}",
            "pipeline": "infrastructure",
            "from_status": "ok",
            "to_status": "error",
            "delta_summary": f"err {i}",
        }
        for i in range(8)
    ]
    payload = format_discord_payload(
        captured_at_iso="2026-04-25T20:00:00+10:00",
        degraded=many,
        recovered=[],
    )
    assert payload is not None
    assert "and 3 more" in payload  # 8 - 5 = 3 truncated


# ---------- service orchestration ----------

import uuid as _uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest as _pytest


def _stub_repo(prior_per_check_set: dict[str, dict | None] | None = None):
    repo = AsyncMock()
    prior = prior_per_check_set or {}
    repo.insert_snapshots = AsyncMock()

    async def _latest(*, check_set, exclude_run_id):
        return prior.get(check_set)

    repo.latest_for_check_set.side_effect = _latest
    return repo


def _integrity_report(check_set: str, errors: int = 0, warns: int = 0):
    return {
        "check_set": check_set,
        "total_checks": 5,
        "error_count": errors,
        "warn_count": warns,
        "ok_count": max(5 - errors - warns, 0),
        "errors": [
            {"check_name": f"{check_set}.bad_thing", "severity": "error",
             "row_count": errors, "details": "boom"}
        ] if errors else [],
        "warnings": [],
        "passed": [],
        "rows": [],
    }


@_pytest.mark.asyncio
async def test_service_baseline_run_writes_rows_does_not_alert(monkeypatch):
    from automana.core.services.ops import health_alert_service as svc

    repo = _stub_repo()
    service_results = {
        "ops.integrity.scryfall_integrity": _integrity_report("scryfall_integrity"),
        "ops.integrity.public_schema_leak": _integrity_report("public_schema_leak"),
    }

    discover = MagicMock(return_value=list(service_results.keys()))
    run_other = AsyncMock(side_effect=lambda key: service_results[key])
    poster = AsyncMock(return_value=204)
    monkeypatch.setattr(svc, "_discover_integrity_services", discover)
    monkeypatch.setattr(svc, "_run_integrity_service", run_other)
    monkeypatch.setattr(svc, "_post_to_discord", poster)
    monkeypatch.setattr(svc, "_get_webhook_url", lambda: "https://example/webhook")

    out = await svc.run_alert_check(pipeline_health_snapshot_repository=repo)
    assert out["alerted"] is False
    assert out["degraded"] == []
    assert out["recovered"] == []
    assert len(out["baselines"]) == 2
    repo.insert_snapshots.assert_awaited_once()
    poster.assert_not_called()


@_pytest.mark.asyncio
async def test_service_degraded_transition_posts_to_discord(monkeypatch):
    from automana.core.services.ops import health_alert_service as svc

    prior = {
        "scryfall_integrity": {"status": "ok", "error_count": 0, "warn_count": 0,
                                "run_id": _uuid.uuid4()},
    }
    repo = _stub_repo(prior)
    discover = MagicMock(return_value=["ops.integrity.scryfall_integrity"])
    run_other = AsyncMock(return_value=_integrity_report("scryfall_integrity", errors=2))
    poster = AsyncMock(return_value=204)
    monkeypatch.setattr(svc, "_discover_integrity_services", discover)
    monkeypatch.setattr(svc, "_run_integrity_service", run_other)
    monkeypatch.setattr(svc, "_post_to_discord", poster)
    monkeypatch.setattr(svc, "_get_webhook_url", lambda: "https://example/webhook")

    out = await svc.run_alert_check(pipeline_health_snapshot_repository=repo)
    assert out["alerted"] is True
    assert len(out["degraded"]) == 1
    assert out["degraded"][0]["check_set"] == "scryfall_integrity"
    assert out["degraded"][0]["from_status"] == "ok"
    assert out["degraded"][0]["to_status"] == "error"
    poster.assert_awaited_once()
    sent_body = poster.await_args.args[1]
    assert "degraded" in sent_body.lower()
    assert "scryfall_integrity" in sent_body


@_pytest.mark.asyncio
async def test_service_unchanged_status_does_not_alert(monkeypatch):
    from automana.core.services.ops import health_alert_service as svc

    prior = {"mtgstock_report": {"status": "error", "error_count": 10, "warn_count": 1,
                                   "run_id": _uuid.uuid4()}}
    repo = _stub_repo(prior)
    discover = MagicMock(return_value=["ops.integrity.mtgstock_report"])
    run_other = AsyncMock(return_value=_integrity_report("mtgstock_report", errors=12))
    poster = AsyncMock()
    monkeypatch.setattr(svc, "_discover_integrity_services", discover)
    monkeypatch.setattr(svc, "_run_integrity_service", run_other)
    monkeypatch.setattr(svc, "_post_to_discord", poster)
    monkeypatch.setattr(svc, "_get_webhook_url", lambda: "https://example/webhook")

    out = await svc.run_alert_check(pipeline_health_snapshot_repository=repo)
    assert out["alerted"] is False
    poster.assert_not_called()


@_pytest.mark.asyncio
async def test_service_integrity_exception_becomes_synthetic_error_row(monkeypatch):
    from automana.core.services.ops import health_alert_service as svc

    repo = _stub_repo({"scryfall_integrity": {"status": "ok", "error_count": 0,
                                                "warn_count": 0,
                                                "run_id": _uuid.uuid4()}})
    discover = MagicMock(return_value=["ops.integrity.scryfall_integrity"])
    run_other = AsyncMock(side_effect=RuntimeError("DB exploded"))
    poster = AsyncMock(return_value=204)
    monkeypatch.setattr(svc, "_discover_integrity_services", discover)
    monkeypatch.setattr(svc, "_run_integrity_service", run_other)
    monkeypatch.setattr(svc, "_post_to_discord", poster)
    monkeypatch.setattr(svc, "_get_webhook_url", lambda: "https://example/webhook")

    out = await svc.run_alert_check(pipeline_health_snapshot_repository=repo)
    # The synthetic error row triggers an ok→error transition.
    assert out["alerted"] is True
    assert len(out["degraded"]) == 1
    inserted_rows = repo.insert_snapshots.await_args.args[0]
    assert any(
        row.status == "error" and "DB exploded" in str(row.report.get("exception", ""))
        for row in inserted_rows
    )


@_pytest.mark.asyncio
async def test_service_missing_webhook_skips_post_but_still_writes(monkeypatch):
    from automana.core.services.ops import health_alert_service as svc

    repo = _stub_repo({"x_check": {"status": "ok", "error_count": 0,
                                      "warn_count": 0, "run_id": _uuid.uuid4()}})
    discover = MagicMock(return_value=["ops.integrity.x_check"])
    run_other = AsyncMock(return_value=_integrity_report("x_check", errors=1))
    poster = AsyncMock()
    monkeypatch.setattr(svc, "_discover_integrity_services", discover)
    monkeypatch.setattr(svc, "_run_integrity_service", run_other)
    monkeypatch.setattr(svc, "_post_to_discord", poster)
    monkeypatch.setattr(svc, "_get_webhook_url", lambda: None)

    out = await svc.run_alert_check(pipeline_health_snapshot_repository=repo)
    assert out["alerted"] is False
    poster.assert_not_called()
    repo.insert_snapshots.assert_awaited_once()
