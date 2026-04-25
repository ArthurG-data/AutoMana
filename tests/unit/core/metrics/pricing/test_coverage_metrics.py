import pytest
from unittest.mock import AsyncMock

from automana.core.metrics.registry import MetricRegistry, Severity
import automana.core.metrics.pricing  # noqa: F401
from automana.core.metrics.pricing.coverage_metrics import (
    min_per_source_observation_coverage_pct,
)

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_min_per_source_observation_coverage_picks_min_value():
    repo = AsyncMock()
    repo.fetch_per_source_observation_coverage_pct.return_value = {
        "tcgplayer": 90.0, "mtgstocks": 30.0, "cardmarket": 60.0,
    }
    result = await min_per_source_observation_coverage_pct(price_repository=repo)
    assert result.row_count == 30.0
    assert result.details["per_source"] == {"tcgplayer": 90.0, "mtgstocks": 30.0, "cardmarket": 60.0}
    cfg = MetricRegistry.get("pricing.coverage.min_per_source_observation_coverage_pct")
    assert MetricRegistry.evaluate(cfg, 30.0) == Severity.WARN


@pytest.mark.asyncio
async def test_min_per_source_observation_coverage_excludes_none_for_min():
    repo = AsyncMock()
    repo.fetch_per_source_observation_coverage_pct.return_value = {
        "tcgplayer": 90.0, "cardmarket": None,
    }
    result = await min_per_source_observation_coverage_pct(price_repository=repo)
    assert result.row_count == 90.0


@pytest.mark.asyncio
async def test_min_per_source_observation_coverage_empty_returns_none():
    repo = AsyncMock()
    repo.fetch_per_source_observation_coverage_pct.return_value = {}
    result = await min_per_source_observation_coverage_pct(price_repository=repo)
    assert result.row_count is None
