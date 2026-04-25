"""Tests for card_catalog.identifier_coverage.* metrics.

Each metric is a thin wrapper over CardReferenceRepository.fetch_identifier_coverage_pct
(or .fetch_identifier_value_count for the informational ones). Tests mock
the repository and assert the returned MetricResult shape — including the
details dict — and the threshold-evaluated severity.
"""
import pytest
from unittest.mock import AsyncMock

from automana.core.metrics.registry import MetricRegistry, Severity
# Importing the package triggers registration of all card_catalog.* metrics.
import automana.core.metrics.card_catalog  # noqa: F401
from automana.core.metrics.card_catalog.identifier_metrics import (
    scryfall_id_coverage,
    oracle_id_coverage,
    tcgplayer_id_coverage,
    cardmarket_id_coverage,
    multiverse_id_count,
    tcgplayer_etched_id_count,
)

pytestmark = pytest.mark.unit


def _repo(coverage=None, value_count=None, coverage_by_unique_card=None):
    repo = AsyncMock()
    repo.fetch_identifier_coverage_pct.return_value = coverage
    repo.fetch_identifier_value_count.return_value = value_count
    repo.fetch_identifier_coverage_pct_by_unique_card.return_value = coverage_by_unique_card
    return repo


@pytest.mark.asyncio
async def test_scryfall_id_coverage_healthy_value_returns_ok():
    repo = _repo(coverage={"covered": 99500, "total": 100000, "pct": 99.5})
    result = await scryfall_id_coverage(card_repository=repo)
    assert result.row_count == 99.5
    assert result.details == {"identifier_name": "scryfall_id", "covered": 99500, "total": 100000}
    cfg = MetricRegistry.get("card_catalog.identifier_coverage.scryfall_id")
    assert MetricRegistry.evaluate(cfg, result.row_count) == Severity.OK


@pytest.mark.asyncio
async def test_scryfall_id_coverage_below_warn_returns_warn():
    repo = _repo(coverage={"covered": 96000, "total": 100000, "pct": 96.0})
    result = await scryfall_id_coverage(card_repository=repo)
    cfg = MetricRegistry.get("card_catalog.identifier_coverage.scryfall_id")
    assert MetricRegistry.evaluate(cfg, result.row_count) == Severity.WARN


@pytest.mark.asyncio
async def test_scryfall_id_coverage_below_error_returns_error():
    repo = _repo(coverage={"covered": 80000, "total": 100000, "pct": 80.0})
    result = await scryfall_id_coverage(card_repository=repo)
    cfg = MetricRegistry.get("card_catalog.identifier_coverage.scryfall_id")
    assert MetricRegistry.evaluate(cfg, result.row_count) == Severity.ERROR


@pytest.mark.asyncio
async def test_scryfall_id_coverage_zero_total_returns_none_warns():
    repo = _repo(coverage={"covered": 0, "total": 0, "pct": None})
    result = await scryfall_id_coverage(card_repository=repo)
    assert result.row_count is None
    cfg = MetricRegistry.get("card_catalog.identifier_coverage.scryfall_id")
    assert MetricRegistry.evaluate(cfg, result.row_count) == Severity.WARN


@pytest.mark.asyncio
async def test_scryfall_id_coverage_repo_returns_none_returns_none():
    repo = _repo(coverage=None)
    result = await scryfall_id_coverage(card_repository=repo)
    assert result.row_count is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "metric_fn,name",
    [
        (tcgplayer_id_coverage, "tcgplayer_id"),
        (cardmarket_id_coverage, "cardmarket_id"),
    ],
)
async def test_other_pct_coverage_metrics_pass_correct_identifier_name(metric_fn, name):
    repo = _repo(coverage={"covered": 50, "total": 100, "pct": 50.0})
    await metric_fn(card_repository=repo)
    repo.fetch_identifier_coverage_pct.assert_awaited_once_with(name)


@pytest.mark.asyncio
async def test_oracle_id_coverage_uses_per_unique_card_repository_method():
    """Regression: oracle_id is per-abstract-card, not per-printing — the metric
    must call fetch_identifier_coverage_pct_by_unique_card. Without this, the
    per-printing denominator divides by the average reprint rate (~3x) and
    produces a false ERROR even when every abstract card has its identifier row.
    """
    repo = _repo(coverage_by_unique_card={"covered": 37236, "total": 37236, "pct": 100.0})
    result = await oracle_id_coverage(card_repository=repo)
    repo.fetch_identifier_coverage_pct_by_unique_card.assert_awaited_once_with("oracle_id")
    repo.fetch_identifier_coverage_pct.assert_not_called()
    assert result.row_count == 100.0
    assert result.details["scope"] == "unique_cards_ref"
    assert result.details["covered"] == 37236
    assert result.details["total"] == 37236


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "metric_fn,name,path",
    [
        (multiverse_id_count, "multiverse_id", "card_catalog.identifier_coverage.multiverse_id"),
        (tcgplayer_etched_id_count, "tcgplayer_etched_id", "card_catalog.identifier_coverage.tcgplayer_etched_id"),
    ],
)
async def test_informational_count_metrics_return_count_no_threshold(metric_fn, name, path):
    repo = _repo(value_count=42)
    result = await metric_fn(card_repository=repo)
    assert result.row_count == 42
    assert result.details == {"identifier_name": name}
    repo.fetch_identifier_value_count.assert_awaited_once_with(name)
    cfg = MetricRegistry.get(path)
    assert cfg.severity is None
    assert MetricRegistry.evaluate(cfg, result.row_count) == Severity.OK
