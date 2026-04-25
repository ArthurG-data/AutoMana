"""
Tests for src/automana/core/metrics/mtgstock/run_metrics.py

Metrics under test (4):
    mtgstock.pipeline_duration_seconds  — Threshold(higher_is_worse)
    mtgstock.run_status                 — callable severity (_status_severity)
    mtgstock.steps_failed_count         — Threshold(higher_is_worse)
    mtgstock.step_durations             — severity=None (informational)

Each metric is tested across two paths:
    1. Happy path: get_latest_run_id returns a real run_id, downstream
       repo methods return realistic data → MetricResult has expected values.
    2. No-runs path: get_latest_run_id returns None → MetricResult signals
       no_runs_found and row_count is None.

The run_status callable severity is also tested directly for all branches.
"""
import pytest
from unittest.mock import AsyncMock

import automana.core.metrics.mtgstock.run_metrics as run_metrics_module
from automana.core.metrics.mtgstock.run_metrics import (
    _status_severity,
    pipeline_duration_seconds,
    run_status,
    step_durations,
    steps_failed_count,
)
from automana.core.metrics.registry import Severity

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# _status_severity — the callable escape hatch for categorical values
# ---------------------------------------------------------------------------

class TestStatusSeverity:
    def test_success_is_ok(self):
        assert _status_severity("success") == Severity.OK

    def test_partial_is_warn(self):
        assert _status_severity("partial") == Severity.WARN

    def test_running_is_warn(self):
        assert _status_severity("running") == Severity.WARN

    def test_pending_is_warn(self):
        assert _status_severity("pending") == Severity.WARN

    def test_failed_is_error(self):
        assert _status_severity("failed") == Severity.ERROR

    def test_unknown_string_is_error(self):
        assert _status_severity("corrupted_status_value") == Severity.ERROR

    def test_none_value_is_error(self):
        # No runs found → row_count=None → _status_severity(None) → ERROR.
        # This is the correct behavior: missing data is a real alert condition.
        assert _status_severity(None) == Severity.ERROR


# ---------------------------------------------------------------------------
# pipeline_duration_seconds
# ---------------------------------------------------------------------------

class TestPipelineDurationSeconds:
    async def test_happy_path_returns_duration_from_run_summary(self):
        ops_repo = AsyncMock()
        ops_repo.get_latest_run_id.return_value = 7
        ops_repo.fetch_run_summary.return_value = {
            "duration_seconds": 1200.5,
            "started_at": "2026-04-24T10:00:00",
            "ended_at": "2026-04-24T10:20:00",
        }

        result = await pipeline_duration_seconds(ops_repository=ops_repo)

        ops_repo.get_latest_run_id.assert_awaited_once_with(run_metrics_module.PIPELINE_NAME)
        ops_repo.fetch_run_summary.assert_awaited_once_with(7)
        assert result.row_count == 1200.5
        assert result.details["ingestion_run_id"] == 7

    async def test_explicit_run_id_skips_latest_resolution(self):
        ops_repo = AsyncMock()
        ops_repo.fetch_run_summary.return_value = {
            "duration_seconds": 600,
            "started_at": "2026-04-24T09:00:00",
            "ended_at": "2026-04-24T09:10:00",
        }

        await pipeline_duration_seconds(ops_repository=ops_repo, ingestion_run_id=42)

        ops_repo.get_latest_run_id.assert_not_awaited()
        ops_repo.fetch_run_summary.assert_awaited_once_with(42)

    async def test_no_runs_returns_none_row_count_with_reason(self):
        ops_repo = AsyncMock()
        ops_repo.get_latest_run_id.return_value = None

        result = await pipeline_duration_seconds(ops_repository=ops_repo)

        assert result.row_count is None
        assert result.details.get("reason") == "no_runs_found"
        ops_repo.fetch_run_summary.assert_not_awaited()

    async def test_empty_summary_produces_none_row_count(self):
        """fetch_run_summary returning None (run exists but summary missing)."""
        ops_repo = AsyncMock()
        ops_repo.get_latest_run_id.return_value = 99
        ops_repo.fetch_run_summary.return_value = None

        result = await pipeline_duration_seconds(ops_repository=ops_repo)

        # summary = None → `{}.get("duration_seconds")` → None
        assert result.row_count is None


# ---------------------------------------------------------------------------
# run_status
# ---------------------------------------------------------------------------

class TestRunStatus:
    async def test_happy_path_returns_status_string(self):
        ops_repo = AsyncMock()
        ops_repo.get_latest_run_id.return_value = 5
        ops_repo.fetch_run_summary.return_value = {
            "status": "success",
            "current_step": "done",
            "error_code": None,
        }

        result = await run_status(ops_repository=ops_repo)

        assert result.row_count == "success"
        assert result.details["current_step"] == "done"
        assert result.details["ingestion_run_id"] == 5

    async def test_no_runs_returns_none_row_count(self):
        ops_repo = AsyncMock()
        ops_repo.get_latest_run_id.return_value = None

        result = await run_status(ops_repository=ops_repo)

        assert result.row_count is None
        assert result.details.get("reason") == "no_runs_found"

    async def test_failed_status_reported_faithfully(self):
        ops_repo = AsyncMock()
        ops_repo.get_latest_run_id.return_value = 3
        ops_repo.fetch_run_summary.return_value = {
            "status": "failed",
            "current_step": "bulk_load",
            "error_code": "TIMEOUT",
        }

        result = await run_status(ops_repository=ops_repo)

        assert result.row_count == "failed"
        assert result.details["error_code"] == "TIMEOUT"


# ---------------------------------------------------------------------------
# steps_failed_count
# ---------------------------------------------------------------------------

class TestStepsFailedCount:
    async def test_happy_path_returns_count(self):
        ops_repo = AsyncMock()
        ops_repo.get_latest_run_id.return_value = 10
        ops_repo.fetch_steps_failed_count.return_value = 3

        result = await steps_failed_count(ops_repository=ops_repo)

        ops_repo.fetch_steps_failed_count.assert_awaited_once_with(10)
        assert result.row_count == 3
        assert result.details["ingestion_run_id"] == 10

    async def test_no_runs_returns_none(self):
        ops_repo = AsyncMock()
        ops_repo.get_latest_run_id.return_value = None

        result = await steps_failed_count(ops_repository=ops_repo)

        assert result.row_count is None
        ops_repo.fetch_steps_failed_count.assert_not_awaited()

    async def test_zero_failures_is_valid(self):
        ops_repo = AsyncMock()
        ops_repo.get_latest_run_id.return_value = 1
        ops_repo.fetch_steps_failed_count.return_value = 0

        result = await steps_failed_count(ops_repository=ops_repo)

        assert result.row_count == 0


# ---------------------------------------------------------------------------
# step_durations
# ---------------------------------------------------------------------------

class TestStepDurations:
    async def test_happy_path_sums_durations(self):
        ops_repo = AsyncMock()
        ops_repo.get_latest_run_id.return_value = 8
        ops_repo.fetch_step_durations.return_value = {
            "fetch": 10.5,
            "transform": 25.0,
            "bulk_load": 120.0,
        }

        result = await step_durations(ops_repository=ops_repo)

        assert result.row_count == pytest.approx(155.5)
        assert result.details["durations_seconds"] == {
            "fetch": 10.5,
            "transform": 25.0,
            "bulk_load": 120.0,
        }
        assert result.details["ingestion_run_id"] == 8

    async def test_none_duration_steps_excluded_from_sum(self):
        """Steps still running may have None duration — should not crash sum."""
        ops_repo = AsyncMock()
        ops_repo.get_latest_run_id.return_value = 2
        ops_repo.fetch_step_durations.return_value = {
            "fetch": 10.0,
            "transform": None,
        }

        result = await step_durations(ops_repository=ops_repo)

        assert result.row_count == pytest.approx(10.0)

    async def test_no_runs_returns_none(self):
        ops_repo = AsyncMock()
        ops_repo.get_latest_run_id.return_value = None

        result = await step_durations(ops_repository=ops_repo)

        assert result.row_count is None
        ops_repo.fetch_step_durations.assert_not_awaited()

    async def test_empty_durations_dict_yields_zero_total(self):
        ops_repo = AsyncMock()
        ops_repo.get_latest_run_id.return_value = 4
        ops_repo.fetch_step_durations.return_value = {}

        result = await step_durations(ops_repository=ops_repo)

        assert result.row_count == 0.0
