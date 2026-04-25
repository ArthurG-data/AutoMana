"""Tests for ops.integrity.card_catalog_report.

The runner is a thin wrapper around _metric_runner.run_metric_report (already
unit-tested) — these tests assert the wiring: prefix, check_set, repositories
dict, and that the 8 card_catalog.* metrics are actually selectable through it.
"""
import pytest
from unittest.mock import AsyncMock

from automana.core.services.ops.card_catalog_report import card_catalog_report

pytestmark = pytest.mark.unit


def _repos():
    card = AsyncMock()
    card.fetch_identifier_coverage_pct.return_value = {"covered": 100, "total": 100, "pct": 100.0}
    # T16: oracle_id_coverage now uses the per-unique-card variant — stub it too.
    card.fetch_identifier_coverage_pct_by_unique_card.return_value = {
        "covered": 100, "total": 100, "pct": 100.0,
    }
    card.fetch_identifier_value_count.return_value = 0
    card.fetch_orphan_unique_cards_count.return_value = 0
    card.fetch_external_id_value_collisions.return_value = 0
    ops = AsyncMock()
    return card, ops


@pytest.mark.asyncio
async def test_card_catalog_report_runs_all_eight_metrics_with_no_filter():
    card, ops = _repos()
    out = await card_catalog_report(card_repository=card, ops_repository=ops)
    assert out["check_set"] == "card_catalog_report"
    assert out["total_checks"] == 8
    paths = {r["check_name"] for r in out["rows"]}
    expected = {
        "card_catalog.identifier_coverage.scryfall_id",
        "card_catalog.identifier_coverage.oracle_id",
        "card_catalog.identifier_coverage.tcgplayer_id",
        "card_catalog.identifier_coverage.cardmarket_id",
        "card_catalog.identifier_coverage.multiverse_id",
        "card_catalog.identifier_coverage.tcgplayer_etched_id",
        "card_catalog.print_coverage.orphan_unique_cards",
        "card_catalog.duplicate_detection.external_id_value_collision",
    }
    assert paths == expected


@pytest.mark.asyncio
async def test_card_catalog_report_category_filter_health_only():
    card, ops = _repos()
    out = await card_catalog_report(card_repository=card, ops_repository=ops, category="health")
    paths = {r["check_name"] for r in out["rows"]}
    # multiverse_id and tcgplayer_etched_id are category="volume" — should be excluded
    assert "card_catalog.identifier_coverage.multiverse_id" not in paths
    assert "card_catalog.identifier_coverage.tcgplayer_etched_id" not in paths
    assert "card_catalog.identifier_coverage.scryfall_id" in paths


@pytest.mark.asyncio
async def test_card_catalog_report_explicit_metric_string_runs_only_that_one():
    card, ops = _repos()
    out = await card_catalog_report(
        card_repository=card, ops_repository=ops,
        metrics="card_catalog.identifier_coverage.scryfall_id",
    )
    assert out["total_checks"] == 1
    assert out["rows"][0]["check_name"] == "card_catalog.identifier_coverage.scryfall_id"


@pytest.mark.asyncio
async def test_card_catalog_report_one_failing_metric_does_not_kill_report():
    card, ops = _repos()
    # Break all per-card_version coverage queries. After T16, oracle_id uses
    # the per-unique-card variant (still stubbed), so only the 3 per-printing
    # pct-coverage metrics fail (scryfall, tcgplayer, cardmarket).
    card.fetch_identifier_coverage_pct.side_effect = RuntimeError("db down")
    out = await card_catalog_report(card_repository=card, ops_repository=ops)
    assert out["error_count"] == 3
    assert out["total_checks"] == 8
