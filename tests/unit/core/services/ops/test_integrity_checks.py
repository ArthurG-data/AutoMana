"""
Tests for src/automana/core/services/ops/integrity_checks.py

Coverage target: >= 90% line + branch.

Units under test:
  - _build_report(check_set, rows) -> dict   [pure function]
  - scryfall_run_diff(ops_repository, ingestion_run_id) -> dict  [async]
  - scryfall_integrity(ops_repository) -> dict                   [async]
  - public_schema_leak(ops_repository) -> dict                   [async]

Mocking strategy:
  The three service functions each call one OpsRepository method and
  delegate to _build_report. We pass AsyncMock repositories and assert:
    (a) the correct repository method was called with correct args
    (b) the returned dict matches _build_report's expected shape

Note: _build_report is module-private but is the core logic. It is tested
directly by calling it; the three service tests then verify the delegation.
"""
import pytest
from unittest.mock import AsyncMock

pytestmark = pytest.mark.unit

from automana.core.services.ops.integrity_checks import (
    _build_report,
    public_schema_leak,
    scryfall_integrity,
    scryfall_run_diff,
)
from tests.unit.core.services.ops.conftest import make_check_row


# ---------------------------------------------------------------------------
# _build_report — pure function
# ---------------------------------------------------------------------------

class TestBuildReport:
    def test_empty_rows_all_counts_zero_all_lists_empty(self):
        report = _build_report("test_suite", [])
        assert report["check_set"] == "test_suite"
        assert report["total_checks"] == 0
        assert report["error_count"] == 0
        assert report["warn_count"] == 0
        assert report["ok_count"] == 0
        assert report["errors"] == []
        assert report["warnings"] == []
        assert report["passed"] == []
        assert report["rows"] == []

    def test_mixed_severities_partitioned_correctly(self):
        rows = [
            make_check_row("error", "fk_orphan"),
            make_check_row("warn",  "row_count_warn"),
            make_check_row("ok",    "schema_ok"),
            make_check_row("ok",    "index_ok"),
        ]
        report = _build_report("mixed_suite", rows)
        assert report["total_checks"] == 4
        assert report["error_count"] == 1
        assert report["warn_count"] == 1
        assert report["ok_count"] == 2
        assert len(report["errors"]) == 1
        assert len(report["warnings"]) == 1
        assert len(report["passed"]) == 2
        assert report["rows"] is rows  # same list object, not a copy

    def test_all_errors_no_ok_no_warn(self):
        rows = [make_check_row("error", f"err_{i}") for i in range(3)]
        report = _build_report("error_suite", rows)
        assert report["error_count"] == 3
        assert report["warn_count"] == 0
        assert report["ok_count"] == 0
        assert len(report["errors"]) == 3
        assert report["warnings"] == []
        assert report["passed"] == []

    def test_all_ok_rows(self):
        rows = [make_check_row("ok", f"check_{i}") for i in range(5)]
        report = _build_report("all_ok_suite", rows)
        assert report["error_count"] == 0
        assert report["ok_count"] == 5
        assert report["errors"] == []
        assert len(report["passed"]) == 5

    def test_check_set_name_preserved_in_report(self):
        report = _build_report("scryfall_run_diff", [])
        assert report["check_set"] == "scryfall_run_diff"

    def test_scalar_counts_match_list_lengths(self):
        rows = [
            make_check_row("error"),
            make_check_row("warn"),
            make_check_row("warn"),
            make_check_row("ok"),
        ]
        report = _build_report("count_verify", rows)
        assert report["error_count"] == len(report["errors"])
        assert report["warn_count"] == len(report["warnings"])
        assert report["ok_count"] == len(report["passed"])
        assert report["total_checks"] == len(report["rows"])


# ---------------------------------------------------------------------------
# scryfall_run_diff
# ---------------------------------------------------------------------------

class TestScryfallRunDiff:
    async def test_calls_repository_and_returns_report(self, mock_ops_repository):
        fixture_rows = [make_check_row("ok", "run_diff_ok")]
        mock_ops_repository.run_scryfall_run_diff.return_value = fixture_rows

        result = await scryfall_run_diff(ops_repository=mock_ops_repository)

        mock_ops_repository.run_scryfall_run_diff.assert_called_once_with(ingestion_run_id=None)
        assert result["check_set"] == "scryfall_run_diff"
        assert result["total_checks"] == 1
        assert result["ok_count"] == 1

    async def test_passes_ingestion_run_id_to_repository(self, mock_ops_repository):
        mock_ops_repository.run_scryfall_run_diff.return_value = []

        await scryfall_run_diff(ops_repository=mock_ops_repository, ingestion_run_id=42)

        mock_ops_repository.run_scryfall_run_diff.assert_called_once_with(ingestion_run_id=42)

    async def test_error_rows_surfaced_in_report(self, mock_ops_repository):
        fixture_rows = [make_check_row("error", "missing_cards")]
        mock_ops_repository.run_scryfall_run_diff.return_value = fixture_rows

        result = await scryfall_run_diff(ops_repository=mock_ops_repository)

        assert result["error_count"] == 1
        assert result["errors"][0]["check_name"] == "missing_cards"


# ---------------------------------------------------------------------------
# scryfall_integrity
# ---------------------------------------------------------------------------

class TestScryfallIntegrity:
    async def test_calls_repository_and_returns_report(self, mock_ops_repository):
        fixture_rows = [
            make_check_row("ok",    "fk_check"),
            make_check_row("warn",  "orphan_warn"),
        ]
        mock_ops_repository.run_scryfall_integrity_checks.return_value = fixture_rows

        result = await scryfall_integrity(ops_repository=mock_ops_repository)

        mock_ops_repository.run_scryfall_integrity_checks.assert_called_once_with()
        assert result["check_set"] == "scryfall_integrity"
        assert result["total_checks"] == 2
        assert result["warn_count"] == 1
        assert result["ok_count"] == 1


# ---------------------------------------------------------------------------
# public_schema_leak
# ---------------------------------------------------------------------------

class TestPublicSchemaLeak:
    async def test_calls_repository_and_returns_report(self, mock_ops_repository):
        fixture_rows = [make_check_row("ok", "no_public_objects")]
        mock_ops_repository.run_public_schema_leak_check.return_value = fixture_rows

        result = await public_schema_leak(ops_repository=mock_ops_repository)

        mock_ops_repository.run_public_schema_leak_check.assert_called_once_with()
        assert result["check_set"] == "public_schema_leak"
        assert result["error_count"] == 0
        assert result["ok_count"] == 1

    async def test_error_rows_indicate_schema_leak(self, mock_ops_repository):
        fixture_rows = [make_check_row("error", "public_table_found")]
        mock_ops_repository.run_public_schema_leak_check.return_value = fixture_rows

        result = await public_schema_leak(ops_repository=mock_ops_repository)

        assert result["error_count"] == 1
        assert result["errors"][0]["check_name"] == "public_table_found"
