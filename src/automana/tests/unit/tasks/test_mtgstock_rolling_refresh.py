import pytest
from unittest.mock import MagicMock, patch


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_task():
    mock = MagicMock()
    mock.request.id = "test-task-id"
    return mock


# NB: the flat slice tasks (_mtgstock_slice_ids / mtgstock_slice_refresh /
# _mtgstock_daily_ids) were superseded by the tiered refresh; their tests now
# live in test_mtgstock_tiered_refresh.py. This file covers the surviving
# incremental-load and discovery tasks.


# ── mtgstock_incremental_load ─────────────────────────────────────────────────

def test_incremental_load_returns_none_when_active():
    from automana.worker.tasks.pipelines import mtgstock_incremental_load

    with patch("automana.worker.tasks.pipelines.run_service",
               return_value={"is_active": True}):
        result = mtgstock_incremental_load.run.__func__(_make_task())

    assert result is None


def test_incremental_load_guard_uses_correct_run_key():
    from automana.worker.tasks.pipelines import mtgstock_incremental_load

    with patch("automana.worker.tasks.pipelines.run_service",
               return_value={"is_active": True}) as mock_rs:
        mtgstock_incremental_load.run.__func__(_make_task())

    assert mock_rs.call_args[1]["run_key"].startswith("mtgStock_load:")


# ── mtgstock_discover_new_ids ─────────────────────────────────────────────────

def test_discover_new_ids_returns_none_when_active():
    from automana.worker.tasks.pipelines import mtgstock_discover_new_ids

    with patch("automana.worker.tasks.pipelines.run_service",
               return_value={"is_active": True}):
        result = mtgstock_discover_new_ids.run.__func__(_make_task())

    assert result is None


def test_discover_new_ids_guard_uses_correct_run_key():
    from automana.worker.tasks.pipelines import mtgstock_discover_new_ids

    with patch("automana.worker.tasks.pipelines.run_service",
               return_value={"is_active": True}) as mock_rs:
        mtgstock_discover_new_ids.run.__func__(_make_task())

    assert mock_rs.call_args[1]["run_key"].startswith("mtgStock_discover:")
