import pytest
from unittest.mock import AsyncMock

from automana.core.metrics.registry import MetricRegistry, Severity
import automana.core.metrics.pricing  # noqa: F401
from automana.core.metrics.pricing.freshness_metrics import (
    price_observation_max_age_days,
    max_per_source_lag_hours,
)

pytestmark = pytest.mark.unit


def _price_repo(max_age=None, per_source_lag=None):
    repo = AsyncMock()
    repo.fetch_max_observation_age_days.return_value = max_age
    repo.fetch_per_source_lag_hours.return_value = per_source_lag or {}
    return repo


@pytest.mark.asyncio
async def test_price_observation_max_age_days_value_and_severity():
    repo = _price_repo(max_age=1)
    result = await price_observation_max_age_days(price_repository=repo)
    assert result.row_count == 1
    cfg = MetricRegistry.get("pricing.freshness.price_observation_max_age_days")
    assert MetricRegistry.evaluate(cfg, 1) == Severity.OK
    assert MetricRegistry.evaluate(cfg, 3) == Severity.WARN
    assert MetricRegistry.evaluate(cfg, 8) == Severity.ERROR


@pytest.mark.asyncio
async def test_price_observation_max_age_days_none_returns_none():
    repo = _price_repo(max_age=None)
    result = await price_observation_max_age_days(price_repository=repo)
    assert result.row_count is None


@pytest.mark.asyncio
async def test_max_per_source_lag_hours_picks_max_value_and_carries_per_source_details():
    repo = _price_repo(per_source_lag={"tcgplayer": 2.5, "mtgstocks": 26.0, "cardmarket": None})
    result = await max_per_source_lag_hours(price_repository=repo)
    assert result.row_count == 26.0
    assert result.details["per_source"] == {"tcgplayer": 2.5, "mtgstocks": 26.0, "cardmarket": None}


@pytest.mark.asyncio
async def test_max_per_source_lag_hours_empty_dict_returns_none():
    repo = _price_repo(per_source_lag={})
    result = await max_per_source_lag_hours(price_repository=repo)
    assert result.row_count is None
