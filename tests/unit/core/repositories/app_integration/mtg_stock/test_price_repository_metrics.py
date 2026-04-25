"""Tests for the metric-support read methods on PriceRepository.

Methods are read-only and feed the pricing.* metric family. Covers freshness
(max age, per-source lag), coverage (per-source observation coverage),
referential soft-integrity, staging drain, and PK-collision detection.
"""
from unittest.mock import AsyncMock

import pytest

from automana.core.repositories.app_integration.mtg_stock.price_repository import (
    PriceRepository,
)

pytestmark = pytest.mark.unit


def _repo(rows):
    repo = PriceRepository.__new__(PriceRepository)
    repo.execute_query = AsyncMock(return_value=rows)
    return repo


# ---------- freshness ----------

@pytest.mark.asyncio
async def test_fetch_max_observation_age_days_returns_int():
    repo = _repo([{"age_days": 1}])
    assert await repo.fetch_max_observation_age_days() == 1


@pytest.mark.asyncio
async def test_fetch_max_observation_age_days_none_when_table_empty():
    repo = _repo([{"age_days": None}])
    assert await repo.fetch_max_observation_age_days() is None


@pytest.mark.asyncio
async def test_fetch_max_observation_age_days_no_rows_returns_none():
    repo = _repo([])
    assert await repo.fetch_max_observation_age_days() is None


@pytest.mark.asyncio
async def test_fetch_per_source_lag_hours_returns_dict():
    repo = _repo([
        {"source_code": "tcgplayer", "lag_hours": 2.5},
        {"source_code": "mtgstocks", "lag_hours": 26.0},
    ])
    out = await repo.fetch_per_source_lag_hours()
    assert out == {"tcgplayer": 2.5, "mtgstocks": 26.0}


@pytest.mark.asyncio
async def test_fetch_per_source_lag_hours_empty_returns_empty_dict():
    repo = _repo([])
    assert await repo.fetch_per_source_lag_hours() == {}


@pytest.mark.asyncio
async def test_fetch_per_source_observation_coverage_pct_returns_dict():
    repo = _repo([
        {"source_code": "tcgplayer", "pct": 90.0},
        {"source_code": "mtgstocks", "pct": 60.0},
    ])
    out = await repo.fetch_per_source_observation_coverage_pct(window_days=30)
    assert out == {"tcgplayer": 90.0, "mtgstocks": 60.0}
    args = repo.execute_query.await_args.args
    assert args[1] == (30,)


@pytest.mark.asyncio
async def test_fetch_per_source_observation_coverage_pct_default_window():
    repo = _repo([])
    await repo.fetch_per_source_observation_coverage_pct()
    args = repo.execute_query.await_args.args
    assert args[1] == (30,)


# ---------- referential / staging / PK ----------

@pytest.mark.asyncio
async def test_fetch_orphan_product_ref_mtg_count_returns_int():
    repo = _repo([{"n": 3}])
    assert await repo.fetch_orphan_product_ref_mtg_count() == 3


@pytest.mark.asyncio
async def test_fetch_orphan_product_ref_mtg_count_no_rows_returns_zero():
    repo = _repo([])
    assert await repo.fetch_orphan_product_ref_mtg_count() == 0


@pytest.mark.asyncio
async def test_fetch_orphan_observation_count_returns_int():
    repo = _repo([{"n": 0}])
    assert await repo.fetch_orphan_observation_count() == 0


@pytest.mark.asyncio
async def test_fetch_orphan_observation_count_no_rows_returns_zero():
    repo = _repo([])
    assert await repo.fetch_orphan_observation_count() == 0


@pytest.mark.asyncio
async def test_fetch_stg_residual_count_returns_int():
    repo = _repo([{"n": 1234}])
    assert await repo.fetch_stg_residual_count() == 1234


@pytest.mark.asyncio
async def test_fetch_stg_residual_count_no_rows_returns_zero():
    repo = _repo([])
    assert await repo.fetch_stg_residual_count() == 0


@pytest.mark.asyncio
async def test_fetch_observation_pk_collision_count_returns_int():
    repo = _repo([{"n": 0}])
    assert await repo.fetch_observation_pk_collision_count() == 0


@pytest.mark.asyncio
async def test_fetch_observation_pk_collision_count_no_rows_returns_zero():
    repo = _repo([])
    assert await repo.fetch_observation_pk_collision_count() == 0
