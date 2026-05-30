import pytest
from unittest.mock import AsyncMock
from automana.core.repositories.ops.ops_repository import OpsRepository


@pytest.mark.asyncio
async def test_get_run_status_for_key_returns_status_when_row_exists():
    repo = OpsRepository.__new__(OpsRepository)
    repo.execute_query = AsyncMock(return_value=[{"status": "running"}])
    result = await repo.get_run_status_for_key("mtgStock_All:2026-05-30")
    assert result == "running"
    repo.execute_query.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_run_status_for_key_returns_none_when_no_row():
    repo = OpsRepository.__new__(OpsRepository)
    repo.execute_query = AsyncMock(return_value=[])
    result = await repo.get_run_status_for_key("mtgStock_All:2026-05-30")
    assert result is None


@pytest.mark.asyncio
async def test_get_run_status_for_key_returns_success():
    repo = OpsRepository.__new__(OpsRepository)
    repo.execute_query = AsyncMock(return_value=[{"status": "success"}])
    result = await repo.get_run_status_for_key("scryfall_daily:2026-05-30")
    assert result == "success"


@pytest.mark.asyncio
async def test_get_run_status_for_key_returns_failed():
    repo = OpsRepository.__new__(OpsRepository)
    repo.execute_query = AsyncMock(return_value=[{"status": "failed"}])
    result = await repo.get_run_status_for_key("mtgjson_daily:2026-05-30")
    assert result == "failed"
