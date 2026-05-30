import pytest
from unittest.mock import AsyncMock
from automana.core.services.ops.pipeline_services import is_run_active


@pytest.mark.asyncio
async def test_is_run_active_true_when_running():
    repo = AsyncMock()
    repo.get_run_status_for_key = AsyncMock(return_value="running")
    result = await is_run_active(ops_repository=repo, run_key="mtgStock_All:2026-05-30")
    assert result == {"is_active": True}


@pytest.mark.asyncio
async def test_is_run_active_true_when_success():
    repo = AsyncMock()
    repo.get_run_status_for_key = AsyncMock(return_value="success")
    result = await is_run_active(ops_repository=repo, run_key="mtgStock_All:2026-05-30")
    assert result == {"is_active": True}


@pytest.mark.asyncio
async def test_is_run_active_false_when_failed():
    repo = AsyncMock()
    repo.get_run_status_for_key = AsyncMock(return_value="failed")
    result = await is_run_active(ops_repository=repo, run_key="mtgStock_All:2026-05-30")
    assert result == {"is_active": False}


@pytest.mark.asyncio
async def test_is_run_active_false_when_no_row():
    repo = AsyncMock()
    repo.get_run_status_for_key = AsyncMock(return_value=None)
    result = await is_run_active(ops_repository=repo, run_key="mtgStock_All:2026-05-30")
    assert result == {"is_active": False}
