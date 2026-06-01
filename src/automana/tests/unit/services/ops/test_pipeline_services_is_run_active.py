import pytest
from unittest.mock import AsyncMock
from automana.core.services.ops.pipeline_services import (
    is_run_active,
    is_run_finished,
    reconcile_orphaned_runs,
)


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


@pytest.mark.asyncio
async def test_is_run_finished_true_when_repo_reports_finished():
    repo = AsyncMock()
    repo.get_run_is_finished = AsyncMock(return_value=True)
    result = await is_run_finished(ops_repository=repo, ingestion_run_id=39)
    assert result == {"is_finished": True}
    repo.get_run_is_finished.assert_awaited_once_with(ingestion_run_id=39)


@pytest.mark.asyncio
async def test_is_run_finished_false_when_repo_reports_not_finished():
    repo = AsyncMock()
    repo.get_run_is_finished = AsyncMock(return_value=False)
    result = await is_run_finished(ops_repository=repo, ingestion_run_id=39)
    assert result == {"is_finished": False}


@pytest.mark.asyncio
async def test_reconcile_orphaned_runs_marks_all_running_as_failed():
    repo = AsyncMock()
    repo.get_running_ingestion_runs = AsyncMock(return_value=[
        {"id": 30, "pipeline_name": "mtg_stock_all", "run_key": "mtgStock_All:2026-05-25"},
        {"id": 31, "pipeline_name": "scryfall_daily", "run_key": "scryfall_daily:2026-05-25"},
    ])
    repo.fail_run = AsyncMock(return_value=None)

    result = await reconcile_orphaned_runs(ops_repository=repo)

    assert result["reconciled"] == 2
    assert len(result["runs"]) == 2
    assert repo.fail_run.call_count == 2
    repo.fail_run.assert_any_call(
        30,
        error_code="orphaned_by_restart",
        error_details={"message": "Worker restarted while run was in progress"},
    )


@pytest.mark.asyncio
async def test_reconcile_orphaned_runs_returns_zero_when_none_running():
    repo = AsyncMock()
    repo.get_running_ingestion_runs = AsyncMock(return_value=[])
    repo.fail_run = AsyncMock()

    result = await reconcile_orphaned_runs(ops_repository=repo)

    assert result == {"reconciled": 0, "runs": []}
    repo.fail_run.assert_not_called()


@pytest.mark.asyncio
async def test_reconcile_orphaned_runs_returns_run_details():
    repo = AsyncMock()
    repo.get_running_ingestion_runs = AsyncMock(return_value=[
        {"id": 42, "pipeline_name": "shopify_weekly", "run_key": "shopify_weekly:2026-05-25"},
    ])
    repo.fail_run = AsyncMock(return_value=None)

    result = await reconcile_orphaned_runs(ops_repository=repo)

    assert result["runs"][0]["id"] == 42
    assert result["runs"][0]["pipeline_name"] == "shopify_weekly"
