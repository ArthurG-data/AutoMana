import pytest
from datetime import date
from unittest.mock import MagicMock, patch


def _make_task():
    m = MagicMock()
    m.request.id = "test-task-id"
    return m


# ── tier config ───────────────────────────────────────────────────────────────

def test_tier_config_markets():
    from automana.worker.tasks.pipelines import _TIER_MARKETS
    assert _TIER_MARKETS[1] == ["tcg", "cardmarket", "cardkingdom", "starcity"]
    assert _TIER_MARKETS[2] == ["tcg", "cardmarket"]
    assert _TIER_MARKETS[3] == ["tcg"]


# ── _tier_slice_pairs ─────────────────────────────────────────────────────────

def test_tier_slice_pairs_deterministic():
    """Same tier/slot/date -> same (print_id, market) slice."""
    from automana.worker.tasks.pipelines import _tier_slice_pairs
    ids = list(range(1, 2801))
    with patch("automana.worker.tasks.pipelines.date") as md:
        md.today.return_value = date(2026, 6, 1)
        md.side_effect = lambda *a, **k: date(*a, **k)
        a = _tier_slice_pairs(ids, tier=1, slot=0)
        b = _tier_slice_pairs(ids, tier=1, slot=0)
    assert a == b


def test_tier1_slices_cover_worklist_without_overlap():
    """Tier1's 28 slots over the window partition the (id x market) work-list."""
    from automana.worker.tasks.pipelines import _tier_slice_pairs, _TIER_MARKETS
    ids = list(range(1, 1401))  # 1400 ids x 4 markets = 5600 pairs
    seen = []
    with patch("automana.worker.tasks.pipelines.date") as md:
        md.side_effect = lambda *a, **k: date(*a, **k)
        for day in range(7):
            md.today.return_value = date(2026, 6, 1 + day)
            for slot in range(4):
                seen.extend(_tier_slice_pairs(ids, tier=1, slot=slot))
    full = {(i, m) for i in ids for m in _TIER_MARKETS[1]}
    assert set(seen) == full
    assert len(seen) == len(full)


def test_group_pairs_by_market():
    from automana.worker.tasks.pipelines import _group_pairs_by_market
    pairs = [(1, "tcg"), (2, "tcg"), (1, "cardmarket")]
    grouped = _group_pairs_by_market(pairs)
    assert grouped == {"tcg": [1, 2], "cardmarket": [1]}


# ── tier tasks idempotency ────────────────────────────────────────────────────

def test_tier1_refresh_returns_none_when_active():
    from automana.worker.tasks.pipelines import mtgstock_tier1_refresh
    with patch("automana.worker.tasks.pipelines.run_service",
               return_value={"is_active": True}):
        assert mtgstock_tier1_refresh.run.__func__(_make_task(), slot=0) is None


def test_tier1_run_key_includes_slot():
    from automana.worker.tasks.pipelines import mtgstock_tier1_refresh
    with patch("automana.worker.tasks.pipelines.run_service",
               return_value={"is_active": True}) as rs:
        mtgstock_tier1_refresh.run.__func__(_make_task(), slot=3)
    assert rs.call_args[1]["run_key"].startswith("mtgStock_tier1:")
    assert rs.call_args[1]["run_key"].endswith(":3")


def test_tier2_refresh_returns_none_when_active():
    from automana.worker.tasks.pipelines import mtgstock_tier2_refresh
    with patch("automana.worker.tasks.pipelines.run_service",
               return_value={"is_active": True}):
        assert mtgstock_tier2_refresh.run.__func__(_make_task()) is None


def test_tier3_refresh_returns_none_when_active():
    from automana.worker.tasks.pipelines import mtgstock_tier3_refresh
    with patch("automana.worker.tasks.pipelines.run_service",
               return_value={"is_active": True}):
        assert mtgstock_tier3_refresh.run.__func__(_make_task()) is None


def test_incremental_load_returns_none_when_active():
    from automana.worker.tasks.pipelines import mtgstock_incremental_load
    with patch("automana.worker.tasks.pipelines.run_service",
               return_value={"is_active": True}):
        assert mtgstock_incremental_load.run.__func__(_make_task()) is None


def test_slice_refresh_removed():
    """The flat slice task is gone; tier tasks replace it."""
    import automana.worker.tasks.pipelines as p
    assert not hasattr(p, "mtgstock_slice_refresh")
    assert not hasattr(p, "_mtgstock_slice_ids")
