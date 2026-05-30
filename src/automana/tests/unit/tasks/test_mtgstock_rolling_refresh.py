import json
import pytest
from datetime import date
from unittest.mock import MagicMock, patch


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_task():
    mock = MagicMock()
    mock.request.id = "test-task-id"
    return mock


_FAKE_IDS = list(range(1, 42001))  # 42000 IDs → 1000 per slice (42 slices)
_FAKE_IDS_JSON = json.dumps(_FAKE_IDS)


# ── _mtgstock_slice_ids ───────────────────────────────────────────────────────

def test_slice_ids_deterministic_same_date_slot():
    """Same date + hour_slot always returns the same IDs."""
    from automana.worker.tasks.pipelines import _mtgstock_slice_ids

    with patch("pathlib.Path.read_text", return_value=_FAKE_IDS_JSON), \
         patch("automana.worker.tasks.pipelines.date") as mock_date:
        mock_date.today.return_value = date(2026, 6, 2)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

        result_a = _mtgstock_slice_ids(3)
        result_b = _mtgstock_slice_ids(3)

    assert result_a == result_b


def test_slice_ids_no_overlap_across_slots():
    """All 6 same-day slots together cover every ID exactly once."""
    from automana.worker.tasks.pipelines import _mtgstock_slice_ids

    with patch("pathlib.Path.read_text", return_value=_FAKE_IDS_JSON), \
         patch("automana.worker.tasks.pipelines.date") as mock_date:
        mock_date.today.return_value = date(2026, 6, 1)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

        slices = [_mtgstock_slice_ids(slot) for slot in range(6)]

    flat = [id_ for s in slices for id_ in s]
    assert sorted(flat) == sorted(set(flat)), "IDs must not repeat across same-day slots"


def test_slice_ids_wraps_after_42_slots():
    """Slot at day_offset=42 produces the same IDs as day_offset=0 for the same hour_slot."""
    from automana.worker.tasks.pipelines import _mtgstock_slice_ids

    with patch("pathlib.Path.read_text", return_value=_FAKE_IDS_JSON), \
         patch("automana.worker.tasks.pipelines.date") as mock_date:
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

        mock_date.today.return_value = date(2026, 6, 1)   # day_offset = 0
        ids_day0 = _mtgstock_slice_ids(0)

        mock_date.today.return_value = date(2026, 7, 13)  # day_offset = 42
        ids_day42 = _mtgstock_slice_ids(0)

    assert ids_day0 == ids_day42


# ── _mtgstock_daily_ids ───────────────────────────────────────────────────────

def test_daily_ids_covers_one_seventh():
    """Daily ID list is approximately 1/7 of all IDs."""
    from automana.worker.tasks.pipelines import _mtgstock_daily_ids

    with patch("pathlib.Path.read_text", return_value=_FAKE_IDS_JSON), \
         patch("automana.worker.tasks.pipelines.date") as mock_date:
        mock_date.today.return_value = date(2026, 6, 1)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

        ids = _mtgstock_daily_ids()

    assert abs(len(ids) - len(_FAKE_IDS) // 7) <= 1


# ── mtgstock_slice_refresh ────────────────────────────────────────────────────

def test_slice_refresh_returns_none_when_active():
    from automana.worker.tasks.pipelines import mtgstock_slice_refresh

    with patch("automana.worker.tasks.pipelines.run_service",
               return_value={"is_active": True}):
        result = mtgstock_slice_refresh.run.__func__(_make_task(), hour_slot=2)

    assert result is None


def test_slice_refresh_guard_uses_correct_run_key():
    from automana.worker.tasks.pipelines import mtgstock_slice_refresh

    with patch("automana.worker.tasks.pipelines.run_service",
               return_value={"is_active": True}) as mock_rs:
        mtgstock_slice_refresh.run.__func__(_make_task(), hour_slot=4)

    assert mock_rs.call_args[1]["run_key"].startswith("mtgStock_slice:")
    assert mock_rs.call_args[1]["run_key"].endswith(":4")


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
