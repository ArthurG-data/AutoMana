"""Tests for _metric_runner.py — the shared dispatch helper used by every
ops.integrity.<family>_report service. Behavior asserted here mirrors what
test_mtgstock_report previously asserted directly against mtgstock_report;
mtgstock_report itself becomes a thin orchestration layer over this helper.
"""
import pytest
from unittest.mock import AsyncMock, patch

from automana.core.metrics.registry import MetricConfig, MetricRegistry, MetricResult, Severity, Threshold
from automana.core.services.ops._metric_runner import (
    _normalize_names,
    run_metric_report,
)

pytestmark = pytest.mark.unit


def test_normalize_names_none_returns_none():
    assert _normalize_names(None) is None


def test_normalize_names_string_splits_on_comma_and_strips():
    assert _normalize_names("a, b ,c") == ["a", "b", "c"]


def test_normalize_names_string_skips_empty_segments():
    assert _normalize_names("a, ,c,") == ["a", "c"]


def test_normalize_names_list_passes_through():
    assert _normalize_names(["a", "b"]) == ["a", "b"]


@pytest.fixture(autouse=True)
def _isolated_registry():
    """Save/restore registry state between tests."""
    saved = dict(MetricRegistry._metrics)
    yield
    MetricRegistry._metrics.clear()
    MetricRegistry._metrics.update(saved)


# Module-level metric functions for registry tests (must be at module level for getattr to work)
async def _test_takes_only_a(a_repo) -> MetricResult:
    return MetricResult(row_count=0, details={"got": "a"})


async def _test_boom() -> MetricResult:
    raise RuntimeError("kaboom")


async def _test_a() -> MetricResult:
    return MetricResult(row_count=1)


async def _test_b() -> MetricResult:
    return MetricResult(row_count=2)


async def _test_h() -> MetricResult:
    return MetricResult(row_count=1)


async def _test_v() -> MetricResult:
    return MetricResult(row_count=2)


@pytest.mark.asyncio
async def test_run_metric_report_invokes_only_signature_matching_kwargs():
    # Manually register the metric with correct module reference
    MetricRegistry._metrics["sig.test"] = MetricConfig(
        path="sig.test",
        category="health",
        description="d",
        severity=Threshold(warn=1, error=2, direction="higher_is_worse"),
        db_repositories=[],
        module="tests.unit.core.services.ops.test_metric_runner",
        function="_test_takes_only_a",
    )

    out = await run_metric_report(
        check_set="x_report",
        prefix="sig.",
        metrics=None,
        category=None,
        repositories={"a_repo": "REPO_A", "b_repo": "REPO_B"},
        extra_kwargs=None,
    )
    assert out["check_set"] == "x_report"
    assert out["total_checks"] == 1
    assert out["rows"][0]["row_count"] == 0
    assert out["rows"][0]["details"]["got"] == "a"


@pytest.mark.asyncio
async def test_run_metric_report_swallows_metric_exceptions_as_error_rows():
    MetricRegistry._metrics["exc.boom"] = MetricConfig(
        path="exc.boom",
        category="health",
        description="d",
        severity=Threshold(warn=1, error=2, direction="higher_is_worse"),
        db_repositories=[],
        module="tests.unit.core.services.ops.test_metric_runner",
        function="_test_boom",
    )

    out = await run_metric_report(
        check_set="x_report", prefix="exc.", metrics=None, category=None,
        repositories={}, extra_kwargs=None,
    )
    assert out["error_count"] == 1
    err = out["errors"][0]
    assert err["check_name"] == "exc.boom"
    assert err["severity"] == Severity.ERROR.value
    assert "RuntimeError" in err["details"]["exception"]


@pytest.mark.asyncio
async def test_run_metric_report_filters_by_explicit_names():
    MetricRegistry._metrics["filt.a"] = MetricConfig(
        path="filt.a", category="health", description="d", severity=None, db_repositories=[],
        module="tests.unit.core.services.ops.test_metric_runner", function="_test_a",
    )
    MetricRegistry._metrics["filt.b"] = MetricConfig(
        path="filt.b", category="health", description="d", severity=None, db_repositories=[],
        module="tests.unit.core.services.ops.test_metric_runner", function="_test_b",
    )

    out = await run_metric_report(
        check_set="x_report", prefix="filt.", metrics="filt.a", category=None,
        repositories={}, extra_kwargs=None,
    )
    assert [r["check_name"] for r in out["rows"]] == ["filt.a"]


@pytest.mark.asyncio
async def test_run_metric_report_filters_by_category():
    MetricRegistry._metrics["cat.h"] = MetricConfig(
        path="cat.h", category="health", description="d", severity=None, db_repositories=[],
        module="tests.unit.core.services.ops.test_metric_runner", function="_test_h",
    )
    MetricRegistry._metrics["cat.v"] = MetricConfig(
        path="cat.v", category="volume", description="d", severity=None, db_repositories=[],
        module="tests.unit.core.services.ops.test_metric_runner", function="_test_v",
    )

    out = await run_metric_report(
        check_set="x_report", prefix="cat.", metrics=None, category="health",
        repositories={}, extra_kwargs=None,
    )
    assert [r["check_name"] for r in out["rows"]] == ["cat.h"]
