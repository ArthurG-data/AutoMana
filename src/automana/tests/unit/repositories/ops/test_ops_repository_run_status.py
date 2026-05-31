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


@pytest.mark.asyncio
async def test_get_running_ingestion_runs_returns_running_rows():
    repo = OpsRepository.__new__(OpsRepository)
    repo.execute_query = AsyncMock(return_value=[
        {"id": 30, "pipeline_name": "mtg_stock_all", "run_key": "mtgStock_All:2026-05-25"},
        {"id": 31, "pipeline_name": "scryfall_daily", "run_key": "scryfall_daily:2026-05-25"},
    ])
    result = await repo.get_running_ingestion_runs()
    assert len(result) == 2
    assert result[0]["id"] == 30
    assert result[1]["pipeline_name"] == "scryfall_daily"
    repo.execute_query.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_running_ingestion_runs_returns_empty_list_when_none():
    repo = OpsRepository.__new__(OpsRepository)
    repo.execute_query = AsyncMock(return_value=[])
    result = await repo.get_running_ingestion_runs()
    assert result == []


@pytest.mark.asyncio
async def test_get_run_is_finished_true_when_ended_at_set():
    repo = OpsRepository.__new__(OpsRepository)
    repo.execute_query = AsyncMock(return_value=[{"finished": True}])
    result = await repo.get_run_is_finished(39)
    assert result is True
    repo.execute_query.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_run_is_finished_false_when_ended_at_null():
    repo = OpsRepository.__new__(OpsRepository)
    repo.execute_query = AsyncMock(return_value=[{"finished": False}])
    result = await repo.get_run_is_finished(39)
    assert result is False


@pytest.mark.asyncio
async def test_get_run_is_finished_false_when_no_row():
    repo = OpsRepository.__new__(OpsRepository)
    repo.execute_query = AsyncMock(return_value=[])
    result = await repo.get_run_is_finished(999)
    assert result is False
