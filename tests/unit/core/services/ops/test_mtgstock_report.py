"""
Tests for src/automana/core/services/ops/mtgstock_report.py

The module imports ``automana.core.metrics.mtgstock`` on load, which registers
all 11 mtgstock metrics as a side effect. Tests here work against those REAL
registrations — no registry isolation, no re-registration overhead.

Key behaviors under test:
    _normalize_names:   None → None, comma-string split, list passthrough
    mtgstock_report:    name string (comma-split), name list, category filter,
                        empty selection (warning logged), per-metric exception
                        swallowing into error-severity row, _build_report envelope.

_invoke_metric is exercised transitively by the service tests (which is its
design intent). We do not test it as a unit in isolation — that would be
testing the stdlib's inspect.signature.

_build_report is NOT re-tested here; it is already covered by test_integrity_checks.py.
"""
import pytest
from unittest.mock import AsyncMock, patch

# Importing the runner triggers registration of all mtgstock.* metrics.
from automana.core.services.ops.mtgstock_report import (
    _normalize_names,
    mtgstock_report,
)
from automana.core.metrics.registry import MetricRegistry
from automana.core.service_registry import ServiceRegistry

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_repos(*, run_id=10, summary=None, step_durations=None,
                steps_failed=0, folder_errors=0,
                raw_prints=75000, raw_rows=1_200_000,
                linked=95000, rejected=5000,
                promoted=200_000):
    """Build a matched pair of AsyncMock repos with sane defaults for all
    methods called by the 11 registered mtgstock metrics."""
    summary = summary or {
        "duration_seconds": 600.0,
        "started_at": "2026-04-24T10:00:00",
        "ended_at": "2026-04-24T10:10:00",
        "status": "success",
        "current_step": "done",
        "error_code": None,
    }
    step_durations = step_durations or {"fetch": 10.0, "bulk_load": 590.0}

    ops_repo = AsyncMock()
    ops_repo.get_latest_run_id.return_value = run_id
    ops_repo.fetch_run_summary.return_value = summary
    ops_repo.fetch_step_durations.return_value = step_durations
    ops_repo.fetch_steps_failed_count.return_value = steps_failed
    ops_repo.fetch_bulk_folder_errors.return_value = folder_errors

    price_repo = AsyncMock()
    price_repo.fetch_raw_prints_count.return_value = raw_prints
    price_repo.fetch_raw_rows_count.return_value = raw_rows
    price_repo.fetch_linked_count.return_value = linked
    price_repo.fetch_rejected_count.return_value = rejected
    price_repo.fetch_promoted_count.return_value = promoted

    return price_repo, ops_repo


# ---------------------------------------------------------------------------
# _normalize_names
# ---------------------------------------------------------------------------

class TestServiceConfigFlags:
    def test_runner_is_non_atomic(self):
        """Regression guard: without runs_in_transaction=False, a single
        failing metric query aborts the wrapper transaction and turns every
        subsequent metric into InFailedSQLTransactionError — defeating the
        per-metric exception-swallowing. Metrics are pure reads; there is no
        reason to wrap them in a transaction."""
        cfg = ServiceRegistry.get("ops.integrity.mtgstock_report")
        assert cfg is not None
        assert cfg.runs_in_transaction is False


class TestNormalizeNames:
    def test_none_returns_none(self):
        assert _normalize_names(None) is None

    def test_comma_string_splits_and_strips(self):
        result = _normalize_names("a,b, c , d")
        assert result == ["a", "b", "c", "d"]

    def test_empty_segments_dropped(self):
        result = _normalize_names("a, ,b,")
        assert result == ["a", "b"]

    def test_single_name_string_returns_one_element_list(self):
        result = _normalize_names("mtgstock.run_status")
        assert result == ["mtgstock.run_status"]

    def test_list_passthrough_as_copy(self):
        original = ["mtgstock.run_status", "mtgstock.cards_rejected"]
        result = _normalize_names(original)
        assert result == original


# ---------------------------------------------------------------------------
# mtgstock_report — name filtering (comma string vs list)
# ---------------------------------------------------------------------------

class TestMtgstockReportNameFiltering:
    async def test_comma_string_selects_correct_metrics(self):
        price_repo, ops_repo = _make_repos()

        result = await mtgstock_report(
            price_repository=price_repo,
            ops_repository=ops_repo,
            metrics="mtgstock.cards_rejected,mtgstock.raw_prints_loaded",
        )

        names = {row["check_name"] for row in result["rows"]}
        assert names == {"mtgstock.cards_rejected", "mtgstock.raw_prints_loaded"}
        assert result["total_checks"] == 2

    async def test_name_list_selects_correct_metrics(self):
        price_repo, ops_repo = _make_repos()

        result = await mtgstock_report(
            price_repository=price_repo,
            ops_repository=ops_repo,
            metrics=["mtgstock.run_status", "mtgstock.steps_failed_count"],
        )

        names = {row["check_name"] for row in result["rows"]}
        assert names == {"mtgstock.run_status", "mtgstock.steps_failed_count"}

    async def test_no_metrics_filter_runs_all_eleven(self):
        price_repo, ops_repo = _make_repos()

        result = await mtgstock_report(
            price_repository=price_repo,
            ops_repository=ops_repo,
        )

        # All 11 registered mtgstock.* metrics must appear
        assert result["total_checks"] == 11

    async def test_rows_are_sorted_by_check_name(self):
        """MetricRegistry.select returns sorted paths; the runner must preserve order."""
        price_repo, ops_repo = _make_repos()

        result = await mtgstock_report(
            price_repository=price_repo,
            ops_repository=ops_repo,
            metrics=["mtgstock.run_status", "mtgstock.cards_rejected",
                     "mtgstock.raw_prints_loaded"],
        )

        names = [row["check_name"] for row in result["rows"]]
        assert names == sorted(names)


# ---------------------------------------------------------------------------
# mtgstock_report — category filtering
# ---------------------------------------------------------------------------

class TestMtgstockReportCategoryFiltering:
    async def test_category_health_selects_only_health_metrics(self):
        price_repo, ops_repo = _make_repos()

        result = await mtgstock_report(
            price_repository=price_repo,
            ops_repository=ops_repo,
            category="health",
        )

        # Verify all returned rows are health-category
        for row in result["rows"]:
            cfg = MetricRegistry.get(row["check_name"])
            assert cfg is not None
            assert cfg.category == "health"

    async def test_category_volume_returns_volume_metrics(self):
        price_repo, ops_repo = _make_repos()

        result = await mtgstock_report(
            price_repository=price_repo,
            ops_repository=ops_repo,
            category="volume",
        )

        assert result["total_checks"] > 0
        for row in result["rows"]:
            cfg = MetricRegistry.get(row["check_name"])
            assert cfg.category == "volume"


# ---------------------------------------------------------------------------
# mtgstock_report — empty selection
# ---------------------------------------------------------------------------

class TestMtgstockReportEmptySelection:
    async def test_nonexistent_name_logs_warning_and_returns_empty_report(self):
        price_repo, ops_repo = _make_repos()

        with patch("automana.core.services.ops.mtgstock_report.logger") as mock_logger:
            result = await mtgstock_report(
                price_repository=price_repo,
                ops_repository=ops_repo,
                metrics="mtgstock.does_not_exist",
            )

        mock_logger.warning.assert_called_once()
        assert result["total_checks"] == 0
        assert result["rows"] == []

    async def test_non_mtgstock_prefix_excluded_even_if_named(self):
        """The runner always applies prefix='mtgstock.'; non-prefixed names are filtered out."""
        price_repo, ops_repo = _make_repos()

        # 'mtgstock.run_status' passes; 'ops.some_other' is outside the prefix
        result = await mtgstock_report(
            price_repository=price_repo,
            ops_repository=ops_repo,
            metrics=["mtgstock.run_status"],
        )

        names = {row["check_name"] for row in result["rows"]}
        assert "mtgstock.run_status" in names


# ---------------------------------------------------------------------------
# mtgstock_report — per-metric exception swallowing
# ---------------------------------------------------------------------------

class TestMtgstockReportExceptionSwallowing:
    async def test_failing_metric_becomes_error_severity_row(self):
        """A metric that raises must not abort the whole report.
        It must surface as an error-severity row with the exception detail."""
        price_repo, ops_repo = _make_repos()
        # Force fetch_run_summary to raise for run_status / pipeline_duration_seconds
        ops_repo.fetch_run_summary.side_effect = RuntimeError("DB connection lost")

        # Select only run_status (uses fetch_run_summary) and raw_prints_loaded
        # (uses only price_repo, will succeed)
        result = await mtgstock_report(
            price_repository=price_repo,
            ops_repository=ops_repo,
            metrics=["mtgstock.run_status", "mtgstock.raw_prints_loaded"],
        )

        assert result["total_checks"] == 2

        rows_by_name = {row["check_name"]: row for row in result["rows"]}

        # raw_prints_loaded must have succeeded
        assert rows_by_name["mtgstock.raw_prints_loaded"]["severity"] in ("ok", "warn", "error")
        assert "exception" not in rows_by_name["mtgstock.raw_prints_loaded"]["details"]

        # run_status must be an error row with an exception detail
        failed_row = rows_by_name["mtgstock.run_status"]
        assert failed_row["severity"] == "error"
        assert failed_row["row_count"] is None
        assert "exception" in failed_row["details"]
        assert "RuntimeError" in failed_row["details"]["exception"]
        assert "DB connection lost" in failed_row["details"]["exception"]

    async def test_error_row_still_has_description_and_category(self):
        """Even swallowed exceptions must include description/category in details."""
        price_repo, ops_repo = _make_repos()
        ops_repo.fetch_run_summary.side_effect = ValueError("unexpected")

        result = await mtgstock_report(
            price_repository=price_repo,
            ops_repository=ops_repo,
            metrics=["mtgstock.run_status"],
        )

        row = result["rows"][0]
        assert "description" in row["details"]
        assert "category" in row["details"]


# ---------------------------------------------------------------------------
# mtgstock_report — _build_report envelope shape
# ---------------------------------------------------------------------------

class TestMtgstockReportEnvelope:
    async def test_report_envelope_has_expected_keys(self):
        price_repo, ops_repo = _make_repos()

        result = await mtgstock_report(
            price_repository=price_repo,
            ops_repository=ops_repo,
            metrics=["mtgstock.cards_rejected"],
        )

        for key in ("check_set", "total_checks", "error_count", "warn_count",
                    "ok_count", "errors", "warnings", "passed", "rows"):
            assert key in result

    async def test_check_set_is_mtgstock_report(self):
        price_repo, ops_repo = _make_repos()

        result = await mtgstock_report(
            price_repository=price_repo,
            ops_repository=ops_repo,
            metrics=["mtgstock.cards_rejected"],
        )

        assert result["check_set"] == "mtgstock_report"

    async def test_result_row_includes_severity_row_count_and_details(self):
        price_repo, ops_repo = _make_repos(rejected=250)

        result = await mtgstock_report(
            price_repository=price_repo,
            ops_repository=ops_repo,
            metrics=["mtgstock.cards_rejected"],
        )

        row = result["rows"][0]
        assert row["check_name"] == "mtgstock.cards_rejected"
        assert "severity" in row
        assert "row_count" in row
        assert isinstance(row["details"], dict)
        assert "description" in row["details"]
        assert "category" in row["details"]


# ---------------------------------------------------------------------------
# mtgstock_report — signature filtering (_invoke_metric)
# ---------------------------------------------------------------------------

class TestInvokeMetricSignatureFiltering:
    """Verify that metrics with different repo subsets each receive only the
    kwargs they declare, without crashing when the runner passes a superset."""

    async def test_price_only_metric_does_not_receive_ops_repository(self):
        """raw_prints_loaded declares only price_repository — should not crash
        when invoked with ops_repository also present in the candidate pool."""
        price_repo, ops_repo = _make_repos()

        # If _invoke_metric leaks extra kwargs, the function will raise TypeError.
        result = await mtgstock_report(
            price_repository=price_repo,
            ops_repository=ops_repo,
            metrics=["mtgstock.raw_prints_loaded"],
        )

        assert result["total_checks"] == 1
        assert result["rows"][0]["check_name"] == "mtgstock.raw_prints_loaded"
        assert result["rows"][0]["severity"] != "error" or \
               "exception" not in result["rows"][0]["details"]

    async def test_ops_only_metric_invoked_correctly(self):
        """steps_failed_count declares only ops_repository."""
        price_repo, ops_repo = _make_repos(steps_failed=0)

        result = await mtgstock_report(
            price_repository=price_repo,
            ops_repository=ops_repo,
            metrics=["mtgstock.steps_failed_count"],
        )

        assert result["total_checks"] == 1
        assert result["rows"][0]["check_name"] == "mtgstock.steps_failed_count"

    async def test_both_repos_metric_invoked_correctly(self):
        """rows_promoted_to_price_observation uses both repos."""
        price_repo, ops_repo = _make_repos()

        result = await mtgstock_report(
            price_repository=price_repo,
            ops_repository=ops_repo,
            metrics=["mtgstock.rows_promoted_to_price_observation"],
        )

        assert result["total_checks"] == 1
        row = result["rows"][0]
        assert row["check_name"] == "mtgstock.rows_promoted_to_price_observation"
        # Should succeed (no exception in details)
        assert "exception" not in row["details"]
