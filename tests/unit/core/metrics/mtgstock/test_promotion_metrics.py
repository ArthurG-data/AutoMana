"""
Tests for src/automana/core/metrics/mtgstock/promotion_metrics.py

Metrics under test (2):
    mtgstock.bulk_load_folder_errors          — OpsRepository only
    mtgstock.rows_promoted_to_price_observation — OpsRepository + PriceRepository,
                                                  with a "run not finished" guard path

Each metric has:
    - happy path with a resolved run_id
    - no-runs path (get_latest_run_id returns None)
rows_promoted_to_price_observation also has:
    - run_not_finished path (started_at or ended_at is None in the summary)
"""
import pytest
from unittest.mock import AsyncMock

from automana.core.metrics.mtgstock.promotion_metrics import (
    bulk_load_folder_errors,
    rows_promoted_to_price_observation,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# bulk_load_folder_errors
# ---------------------------------------------------------------------------

class TestBulkLoadFolderErrors:
    async def test_happy_path_returns_error_count(self):
        ops_repo = AsyncMock()
        ops_repo.get_latest_run_id.return_value = 15
        ops_repo.fetch_bulk_folder_errors.return_value = 42

        result = await bulk_load_folder_errors(ops_repository=ops_repo)

        ops_repo.fetch_bulk_folder_errors.assert_awaited_once_with(15)
        assert result.row_count == 42
        assert result.details["ingestion_run_id"] == 15

    async def test_explicit_run_id_skips_latest_resolution(self):
        ops_repo = AsyncMock()
        ops_repo.fetch_bulk_folder_errors.return_value = 0

        await bulk_load_folder_errors(ops_repository=ops_repo, ingestion_run_id=77)

        ops_repo.get_latest_run_id.assert_not_awaited()
        ops_repo.fetch_bulk_folder_errors.assert_awaited_once_with(77)

    async def test_no_runs_returns_none(self):
        ops_repo = AsyncMock()
        ops_repo.get_latest_run_id.return_value = None

        result = await bulk_load_folder_errors(ops_repository=ops_repo)

        assert result.row_count is None
        assert result.details.get("reason") == "no_runs_found"
        ops_repo.fetch_bulk_folder_errors.assert_not_awaited()

    async def test_zero_errors_returned_faithfully(self):
        ops_repo = AsyncMock()
        ops_repo.get_latest_run_id.return_value = 1
        ops_repo.fetch_bulk_folder_errors.return_value = 0

        result = await bulk_load_folder_errors(ops_repository=ops_repo)

        assert result.row_count == 0


# ---------------------------------------------------------------------------
# rows_promoted_to_price_observation
# ---------------------------------------------------------------------------

class TestRowsPromotedToPriceObservation:
    async def test_happy_path_calls_price_repo_with_run_window(self):
        ops_repo = AsyncMock()
        price_repo = AsyncMock()

        ops_repo.get_latest_run_id.return_value = 20
        ops_repo.fetch_run_summary.return_value = {
            "started_at": "2026-04-24T10:00:00",
            "ended_at": "2026-04-24T10:30:00",
        }
        price_repo.fetch_promoted_count.return_value = 250_000

        result = await rows_promoted_to_price_observation(
            price_repository=price_repo,
            ops_repository=ops_repo,
        )

        price_repo.fetch_promoted_count.assert_awaited_once_with(
            since="2026-04-24T10:00:00",
            until="2026-04-24T10:30:00",
            source_code="mtgstocks",
        )
        assert result.row_count == 250_000
        assert result.details["ingestion_run_id"] == 20
        assert "since" in result.details
        assert "until" in result.details

    async def test_explicit_run_id_skips_latest_resolution(self):
        ops_repo = AsyncMock()
        price_repo = AsyncMock()
        ops_repo.fetch_run_summary.return_value = {
            "started_at": "2026-04-24T08:00:00",
            "ended_at": "2026-04-24T08:15:00",
        }
        price_repo.fetch_promoted_count.return_value = 5000

        await rows_promoted_to_price_observation(
            price_repository=price_repo,
            ops_repository=ops_repo,
            ingestion_run_id=55,
        )

        ops_repo.get_latest_run_id.assert_not_awaited()
        ops_repo.fetch_run_summary.assert_awaited_once_with(55)

    async def test_no_runs_returns_none(self):
        ops_repo = AsyncMock()
        price_repo = AsyncMock()
        ops_repo.get_latest_run_id.return_value = None

        result = await rows_promoted_to_price_observation(
            price_repository=price_repo,
            ops_repository=ops_repo,
        )

        assert result.row_count is None
        assert result.details.get("reason") == "no_runs_found"
        price_repo.fetch_promoted_count.assert_not_awaited()

    async def test_run_not_finished_started_at_none(self):
        """started_at is None → run still in progress → return run_not_finished."""
        ops_repo = AsyncMock()
        price_repo = AsyncMock()
        ops_repo.get_latest_run_id.return_value = 30
        ops_repo.fetch_run_summary.return_value = {
            "started_at": None,
            "ended_at": "2026-04-24T12:00:00",
        }

        result = await rows_promoted_to_price_observation(
            price_repository=price_repo,
            ops_repository=ops_repo,
        )

        assert result.row_count is None
        assert result.details.get("reason") == "run_not_finished"
        price_repo.fetch_promoted_count.assert_not_awaited()

    async def test_run_not_finished_ended_at_none(self):
        """ended_at is None → run still in progress → return run_not_finished."""
        ops_repo = AsyncMock()
        price_repo = AsyncMock()
        ops_repo.get_latest_run_id.return_value = 31
        ops_repo.fetch_run_summary.return_value = {
            "started_at": "2026-04-24T11:00:00",
            "ended_at": None,
        }

        result = await rows_promoted_to_price_observation(
            price_repository=price_repo,
            ops_repository=ops_repo,
        )

        assert result.row_count is None
        assert result.details.get("reason") == "run_not_finished"
        assert result.details.get("ingestion_run_id") == 31
        price_repo.fetch_promoted_count.assert_not_awaited()

    async def test_none_summary_treated_as_run_not_finished(self):
        """fetch_run_summary returns None → both started/ended absent → run_not_finished."""
        ops_repo = AsyncMock()
        price_repo = AsyncMock()
        ops_repo.get_latest_run_id.return_value = 32
        ops_repo.fetch_run_summary.return_value = None

        result = await rows_promoted_to_price_observation(
            price_repository=price_repo,
            ops_repository=ops_repo,
        )

        assert result.row_count is None
        assert result.details.get("reason") == "run_not_finished"
        price_repo.fetch_promoted_count.assert_not_awaited()
