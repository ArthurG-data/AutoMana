"""Tests for the freshness helper added to OpsRepository for pricing metrics."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from automana.core.repositories.ops.ops_repository import OpsRepository

pytestmark = pytest.mark.unit


def _repo(rows):
    repo = OpsRepository.__new__(OpsRepository)
    repo.execute_query = AsyncMock(return_value=rows)
    return repo


@pytest.mark.asyncio
async def test_fetch_latest_successful_run_ended_at_returns_datetime():
    ts = datetime(2026, 4, 24, 10, 0, tzinfo=timezone.utc)
    repo = _repo([{"ended_at": ts}])
    out = await repo.fetch_latest_successful_run_ended_at("mtg_stock_all")
    assert out == ts
    repo.execute_query.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_latest_successful_run_ended_at_none_when_no_runs():
    repo = _repo([])
    assert await repo.fetch_latest_successful_run_ended_at("mtg_stock_all") is None


@pytest.mark.asyncio
async def test_fetch_latest_successful_run_ended_at_passes_pipeline_arg():
    repo = _repo([])
    await repo.fetch_latest_successful_run_ended_at("mtgjson_daily")
    args = repo.execute_query.await_args.args
    assert args[1] == ("mtgjson_daily",)
