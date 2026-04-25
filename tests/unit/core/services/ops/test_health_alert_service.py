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
