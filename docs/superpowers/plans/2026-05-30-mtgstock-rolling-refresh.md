# MTGStock Rolling Price Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the one-shot MTGStock API scraper with a 7-day rolling window that refreshes ~2,276 print IDs per run, 6 runs/day, keeping prices at most 7 days stale without a multi-hour API session.

**Architecture:** Three new Celery tasks (`mtgstock_slice_refresh`, `mtgstock_incremental_load`, `mtgstock_discover_new_ids`) wire into the existing `run_service` chain pattern. Slice selection is stateless (date-modulo formula — no Redis cursor). The existing `bulk_load` service gains an `ids_filter` param so the incremental load processes only the ~13,659 IDs touched that day rather than all 95,615. A new `discover_and_fetch_new_ids` service probes for print IDs added since the last discovery run.

**Tech Stack:** Python, Celery (`chain`, `shared_task`), ServiceRegistry, asyncio, pytest + `unittest.mock`

---

## File Map

| File | Change |
|------|--------|
| `src/automana/core/services/app_integration/mtg_stock/data_staging.py` | Add `ids_filter` param to `bulk_load` |
| `src/automana/core/services/app_integration/mtg_stock/data_loader.py` | Add `discover_and_fetch_new_ids` registered service |
| `src/automana/worker/tasks/pipelines.py` | Add 3 tasks + 2 private helpers |
| `src/automana/worker/celeryconfig.py` | Add 8 beat schedule entries |
| `src/automana/tests/unit/services/mtg_stock/__init__.py` | New empty file (new package) |
| `src/automana/tests/unit/services/mtg_stock/test_bulk_load_ids_filter.py` | New — `ids_filter` tests |
| `src/automana/tests/unit/tasks/test_mtgstock_rolling_refresh.py` | New — 3 task tests |

---

### Task 1: Working branch

- [ ] **Step 1: Create branch off dev**

```bash
git fetch origin
git checkout dev
git pull origin dev
git checkout -b feat/2026-05-30-mtgstock-rolling-refresh
```

Expected: `Switched to a new branch 'feat/2026-05-30-mtgstock-rolling-refresh'`

---

### Task 2: `ids_filter` param on `bulk_load`

**Files:**
- Modify: `src/automana/core/services/app_integration/mtg_stock/data_staging.py:61`
- Create: `src/automana/tests/unit/services/mtg_stock/__init__.py`
- Create: `src/automana/tests/unit/services/mtg_stock/test_bulk_load_ids_filter.py`

- [ ] **Step 1: Write the failing tests**

Create `src/automana/tests/unit/services/mtg_stock/__init__.py` (empty).

Create `src/automana/tests/unit/services/mtg_stock/test_bulk_load_ids_filter.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
import pandas as pd
from automana.core.services.app_integration.mtg_stock.data_staging import bulk_load


def _make_id_dict(mtgstock_id: int) -> dict:
    return {
        "mtgstock": mtgstock_id,
        "card_name": f"Card {mtgstock_id}",
        "set_abbr": "TST",
        "collector_number": "1",
        "scryfallId": None,
        "tcg_id": None,
        "cardtrader_id": None,
    }


def _make_repos():
    price_repo = MagicMock()
    price_repo.clear_raw_prices = AsyncMock(return_value=0)
    price_repo.copy_prices_mtgstock = AsyncMock()
    price_repo.update_ids_master_dict = AsyncMock()
    ops_repo = MagicMock()
    ops_repo.update_run = AsyncMock()
    ops_repo.insert_batch_step = AsyncMock()
    ops_repo.update_ids_master_dict = AsyncMock()
    return price_repo, ops_repo


@pytest.mark.asyncio
async def test_bulk_load_ids_filter_restricts_folders():
    """bulk_load with ids_filter only processes folders whose names are in the filter."""
    price_repo, ops_repo = _make_repos()
    processed_folders = []

    async def fake_process_info(path):
        folder_id = int(path.split("/")[-2])
        processed_folders.append(folder_id)
        return _make_id_dict(folder_id)

    with patch("os.listdir", return_value=["100", "200", "300", "400", "500", "notdigit"]), \
         patch(
             "automana.core.services.app_integration.mtg_stock.data_staging.process_info_file",
             side_effect=fake_process_info,
         ), \
         patch(
             "automana.core.services.app_integration.mtg_stock.data_staging.process_prices_file",
             new=AsyncMock(return_value=pd.DataFrame(columns=["date", "price_low", "price_avg",
                                                               "price_foil", "price_market",
                                                               "price_market_foil", "print_id",
                                                               "source_code", "card_name",
                                                               "set_abbr", "collector_number",
                                                               "scryfall_id", "tcg_id",
                                                               "cardtrader_id"])),
         ):
        await bulk_load(
            price_repository=price_repo,
            ops_repository=ops_repo,
            root_folder="/fake/path",
            ingestion_run_id=1,
            ids_filter=[200, 400],
        )

    assert sorted(processed_folders) == [200, 400]


@pytest.mark.asyncio
async def test_bulk_load_no_ids_filter_processes_all_digit_folders():
    """bulk_load without ids_filter processes all digit-named folders (existing behaviour)."""
    price_repo, ops_repo = _make_repos()
    processed_folders = []

    async def fake_process_info(path):
        folder_id = int(path.split("/")[-2])
        processed_folders.append(folder_id)
        return _make_id_dict(folder_id)

    with patch("os.listdir", return_value=["100", "200", "notdigit"]), \
         patch(
             "automana.core.services.app_integration.mtg_stock.data_staging.process_info_file",
             side_effect=fake_process_info,
         ), \
         patch(
             "automana.core.services.app_integration.mtg_stock.data_staging.process_prices_file",
             new=AsyncMock(return_value=pd.DataFrame(columns=["date", "price_low", "price_avg",
                                                               "price_foil", "price_market",
                                                               "price_market_foil", "print_id",
                                                               "source_code", "card_name",
                                                               "set_abbr", "collector_number",
                                                               "scryfall_id", "tcg_id",
                                                               "cardtrader_id"])),
         ):
        await bulk_load(
            price_repository=price_repo,
            ops_repository=ops_repo,
            root_folder="/fake/path",
            ingestion_run_id=1,
        )

    assert sorted(processed_folders) == [100, 200]


@pytest.mark.asyncio
async def test_bulk_load_ids_filter_empty_list_processes_nothing():
    """ids_filter=[] means nothing passes the filter — no folders processed."""
    price_repo, ops_repo = _make_repos()
    processed_folders = []

    async def fake_process_info(path):
        processed_folders.append(path)
        return _make_id_dict(0)

    with patch("os.listdir", return_value=["100", "200", "300"]), \
         patch(
             "automana.core.services.app_integration.mtg_stock.data_staging.process_info_file",
             side_effect=fake_process_info,
         ):
        await bulk_load(
            price_repository=price_repo,
            ops_repository=ops_repo,
            root_folder="/fake/path",
            ingestion_run_id=1,
            ids_filter=[],
        )

    assert processed_folders == []
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd src && python -m pytest automana/tests/unit/services/mtg_stock/test_bulk_load_ids_filter.py -v
```

Expected: 3 failures — `TypeError` or assertion errors because `ids_filter` param doesn't exist yet.

- [ ] **Step 3: Add `ids_filter` to `bulk_load` signature and filtering logic**

In `src/automana/core/services/app_integration/mtg_stock/data_staging.py`, change the `bulk_load` signature from:

```python
async def bulk_load(price_repository: PriceRepository,
                    ops_repository: OpsRepository,
                    root_folder,
                    batch_size: int = 2000,
                    ingestion_run_id: int = None,
                    market: str = "tcg",
                    start_id: int | None = None,
                    end_id: int | None = None,
                    concurrency: int = 20):
```

to:

```python
async def bulk_load(price_repository: PriceRepository,
                    ops_repository: OpsRepository,
                    root_folder,
                    batch_size: int = 2000,
                    ingestion_run_id: int = None,
                    market: str = "tcg",
                    start_id: int | None = None,
                    end_id: int | None = None,
                    ids_filter: list[int] | None = None,
                    concurrency: int = 20):
```

Then, immediately after the existing `start_id`/`end_id` filtering block (which currently ends after the `if start_id is not None or end_id is not None:` block), add:

```python
    if ids_filter is not None:
        _ids_set = set(ids_filter)
        folders = [f for f in folders if f.isdigit() and int(f) in _ids_set]
```

The full filtering section should read:

```python
    folders = os.listdir(root_folder)
    if start_id is not None or end_id is not None:
        if start_id is not None and end_id is not None and start_id > end_id:
            logger.warning(
                "bulk_load: start_id > end_id, no folders will be processed",
                extra={"start_id": start_id, "end_id": end_id},
            )
        folders = [
            f for f in folders
            if f.isdigit()
            and (start_id is None or int(f) >= start_id)
            and (end_id is None or int(f) <= end_id)
        ]
    if ids_filter is not None:
        _ids_set = set(ids_filter)
        folders = [f for f in folders if f.isdigit() and int(f) in _ids_set]
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd src && python -m pytest automana/tests/unit/services/mtg_stock/test_bulk_load_ids_filter.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/services/app_integration/mtg_stock/data_staging.py \
        src/automana/tests/unit/services/mtg_stock/__init__.py \
        src/automana/tests/unit/services/mtg_stock/test_bulk_load_ids_filter.py
git commit -m "feat(mtgstock): add ids_filter param to bulk_load for incremental staging"
```

---

### Task 3: `discover_and_fetch_new_ids` service

**Files:**
- Modify: `src/automana/core/services/app_integration/mtg_stock/data_loader.py`

This service probes the MTGStocks API for print IDs above the current known maximum and downloads their details + prices to disk. It is called by the weekly discovery task.

- [ ] **Step 1: Add `discover_and_fetch_new_ids` after the existing `run_mtgstock_pipeline_selected_lists` in `data_loader.py`**

Append to `src/automana/core/services/app_integration/mtg_stock/data_loader.py`:

```python
@ServiceRegistry.register(
    "mtg_stock.data_loader.discover_and_fetch_new_ids",
    api_repositories=["mtg_stock"],
    db_repositories=["ops"],
)
async def discover_and_fetch_new_ids(
        mtg_stock_repository: ApiMtgStockRepository,
        destination_folder: str,
        ingestion_run_id: int,
        batch_size: int = 500,
        ops_repository: OpsRepository | None = None,
        market: str = "tcg",
) -> dict:
    """Probe for print IDs beyond the current local maximum and download them."""
    ids_path = Path(destination_folder) / "existing_ids.json"
    existing_ids: List[int] = sorted(json.loads(ids_path.read_text())) if ids_path.exists() else []
    max_known = max(existing_ids) if existing_ids else 0

    last_id = await get_last_print_id(mtg_stock_repository, max_known)

    if last_id <= max_known:
        logger.info("No new print IDs discovered", extra={"max_known": max_known})
        return {"new_ids_count": 0, "processed": 0}

    new_ids = list(range(max_known + 1, last_id + 1))
    logger.info(
        "New print IDs discovered",
        extra={"count": len(new_ids), "from": max_known + 1, "to": last_id},
    )

    if ops_repository and ingestion_run_id is not None:
        await ops_repository.update_run(
            ingestion_run_id, status="running", current_step="discover_new_ids"
        )

    processed = 0
    for start in range(0, len(new_ids), batch_size):
        batch_ids = new_ids[start : start + batch_size]
        batch_result = await mtg_stock_repository.fetch_card_data_batches(batch_ids, market=market)
        cleaned = [d for d in batch_result.get("data", []) if "error" not in d]
        await write_batch(cleaned, Path(destination_folder), market=market)
        processed += len(cleaned)
        logger.info(
            "discover_new_ids batch complete",
            extra={"batch_start": start, "fetched": len(cleaned)},
        )

    all_ids = sorted(set(existing_ids) | set(new_ids))
    ids_path.write_text(json.dumps(all_ids))
    logger.info("existing_ids.json updated", extra={"total_ids": len(all_ids)})

    return {"new_ids_count": len(new_ids), "processed": processed}
```

- [ ] **Step 2: Verify the module imports cleanly**

```bash
cd src && python -c "from automana.core.services.app_integration.mtg_stock.data_loader import discover_and_fetch_new_ids; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add src/automana/core/services/app_integration/mtg_stock/data_loader.py
git commit -m "feat(mtgstock): add discover_and_fetch_new_ids service for weekly new-ID probe"
```

---

### Task 4: Helper functions + 3 new Celery tasks

**Files:**
- Modify: `src/automana/worker/tasks/pipelines.py`
- Create: `src/automana/tests/unit/tasks/test_mtgstock_rolling_refresh.py`

- [ ] **Step 1: Write the failing tests**

Create `src/automana/tests/unit/tasks/test_mtgstock_rolling_refresh.py`:

```python
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd src && python -m pytest automana/tests/unit/tasks/test_mtgstock_rolling_refresh.py -v
```

Expected: all fail with `ImportError` — `_mtgstock_slice_ids`, `_mtgstock_daily_ids`, and the three tasks don't exist yet.

- [ ] **Step 3: Add helper functions and tasks to `pipelines.py`**

In `src/automana/worker/tasks/pipelines.py`, `datetime` is already imported as `from datetime import datetime`. Change that line to also import `date`, and add `json` and `Path`:

```python
# change this existing line:
from datetime import datetime
# to:
from datetime import datetime, date
```

Then add two more imports after the existing import block:

```python
import json
from pathlib import Path
```

Then append all of the following to the end of `src/automana/worker/tasks/pipelines.py`:

```python
# ── MTGStock rolling refresh ──────────────────────────────────────────────────

_MTGSTOCK_IDS_PATH = Path("/data/automana_data/mtgstocks/raw/prints/existing_ids.json")
_MTGSTOCK_EPOCH = date(2026, 6, 1)
_WINDOW_DAYS = 7
_RUNS_PER_DAY = 6
_TOTAL_SLICES = _WINDOW_DAYS * _RUNS_PER_DAY  # 42


def _mtgstock_slice_ids(hour_slot: int) -> list[int]:
    """Return the sorted print IDs assigned to this hour_slot on today's date.

    Slice index = (day_offset * 6 + hour_slot) % 42.  Deterministic and
    stateless — identical inputs always produce the same list.
    """
    existing_ids = sorted(json.loads(_MTGSTOCK_IDS_PATH.read_text()))
    total = len(existing_ids)
    slice_size = total // _TOTAL_SLICES

    day_offset = (date.today() - _MTGSTOCK_EPOCH).days
    slice_idx = (day_offset * _RUNS_PER_DAY + hour_slot) % _TOTAL_SLICES

    start = slice_idx * slice_size
    end = start + slice_size if slice_idx < _TOTAL_SLICES - 1 else total
    return existing_ids[start:end]


def _mtgstock_daily_ids() -> list[int]:
    """Return all print IDs assigned to today in the 7-day window.

    Day-in-window = day_offset % 7.  Union of all 6 hour_slot slices for today.
    """
    existing_ids = sorted(json.loads(_MTGSTOCK_IDS_PATH.read_text()))
    total = len(existing_ids)
    daily_size = total // _WINDOW_DAYS

    day_offset = (date.today() - _MTGSTOCK_EPOCH).days
    day_in_window = day_offset % _WINDOW_DAYS
    start = day_in_window * daily_size
    end = start + daily_size if day_in_window < _WINDOW_DAYS - 1 else total
    return existing_ids[start:end]


@shared_task(name="automana.worker.tasks.pipelines.mtgstock_slice_refresh", bind=True)
def mtgstock_slice_refresh(self, hour_slot: int):
    """Fetch one 1/42 slice of MTGStock print IDs from the API and update disk files."""
    set_task_id(self.request.id)
    today = datetime.utcnow().date().isoformat()
    run_key = f"mtgStock_slice:{today}:{hour_slot}"
    logger.info("Starting MTGStock slice refresh", extra={"run_key": run_key, "hour_slot": hour_slot})

    result = run_service("ops.pipeline_services.is_run_active", run_key=run_key)
    if result.get("is_active"):
        logger.warning("Duplicate pipeline skipped", extra={"run_key": run_key})
        return

    slice_ids = _mtgstock_slice_ids(hour_slot)
    logger.info("MTGStock slice computed", extra={"hour_slot": hour_slot, "count": len(slice_ids)})

    wf = chain(
        run_service.s("ops.pipeline_services.start_run",
                      pipeline_name="mtgstock_slice_refresh",
                      source_name="mtgstocks",
                      run_key=run_key,
                      celery_task_id=self.request.id),
        run_service.s("mtg_stock.data_loader.run_list_id_load",
                      destination_folder="/data/automana_data/mtgstocks/raw/prints/",
                      batch_size=500,
                      ids_list=slice_ids,
                      market="tcg"),
        run_service.s("ops.pipeline_services.finish_run", status="success"),
    )
    return wf.apply_async().id


@shared_task(name="automana.worker.tasks.pipelines.mtgstock_incremental_load", bind=True)
def mtgstock_incremental_load(self):
    """Stage and promote today's refreshed MTGStock IDs into price_observation."""
    set_task_id(self.request.id)
    today = datetime.utcnow().date().isoformat()
    run_key = f"mtgStock_load:{today}"
    logger.info("Starting MTGStock incremental DB load", extra={"run_key": run_key})

    result = run_service("ops.pipeline_services.is_run_active", run_key=run_key)
    if result.get("is_active"):
        logger.warning("Duplicate pipeline skipped", extra={"run_key": run_key})
        return

    today_ids = _mtgstock_daily_ids()
    logger.info("MTGStock daily IDs computed", extra={"count": len(today_ids)})

    wf = chain(
        run_service.s("ops.pipeline_services.start_run",
                      pipeline_name="mtgstock_incremental_load",
                      source_name="mtgstocks",
                      run_key=run_key,
                      celery_task_id=self.request.id),
        run_service.s("mtg_stock.data_staging.bulk_load",
                      root_folder="/data/automana_data/mtgstocks/raw/prints/",
                      batch_size=2000,
                      ids_filter=today_ids,
                      market="tcg"),
        run_service.s("mtg_stock.data_staging.from_raw_to_staging",
                      source_name="mtgstocks"),
        run_service.s("mtg_stock.data_staging.retry_rejects"),
        run_service.s("mtg_stock.data_staging.from_staging_to_prices"),
        run_service.s("ops.pipeline_services.finish_run", status="success"),
    )
    return wf.apply_async().id


@shared_task(name="automana.worker.tasks.pipelines.mtgstock_discover_new_ids", bind=True)
def mtgstock_discover_new_ids(self):
    """Weekly: probe MTGStocks for print IDs beyond the local maximum and download them."""
    set_task_id(self.request.id)
    today = datetime.utcnow().date().isoformat()
    run_key = f"mtgStock_discover:{today}"
    logger.info("Starting MTGStock new ID discovery", extra={"run_key": run_key})

    result = run_service("ops.pipeline_services.is_run_active", run_key=run_key)
    if result.get("is_active"):
        logger.warning("Duplicate pipeline skipped", extra={"run_key": run_key})
        return

    wf = chain(
        run_service.s("ops.pipeline_services.start_run",
                      pipeline_name="mtgstock_discover_new_ids",
                      source_name="mtgstocks",
                      run_key=run_key,
                      celery_task_id=self.request.id),
        run_service.s("mtg_stock.data_loader.discover_and_fetch_new_ids",
                      destination_folder="/data/automana_data/mtgstocks/raw/prints/",
                      batch_size=500,
                      market="tcg"),
        run_service.s("ops.pipeline_services.finish_run", status="success"),
    )
    return wf.apply_async().id
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd src && python -m pytest automana/tests/unit/tasks/test_mtgstock_rolling_refresh.py -v
```

Expected: 10 passed.

- [ ] **Step 5: Extend the idempotency guard test to cover all three new tasks**

In `src/automana/tests/unit/tasks/test_pipeline_idempotency_guard.py`, add the three new tasks to the `PIPELINES` list:

```python
PIPELINES = [
    ("automana.worker.tasks.pipelines.daily_scryfall_data_pipeline", "daily_scryfall_data_pipeline"),
    ("automana.worker.tasks.pipelines.mtgStock_download_pipeline", "mtgStock_download_pipeline"),
    ("automana.worker.tasks.pipelines.daily_mtgjson_data_pipeline", "daily_mtgjson_data_pipeline"),
    ("automana.worker.tasks.pipelines.daily_mtgjson_sealed_pipeline", "daily_mtgjson_sealed_pipeline"),
    ("automana.worker.tasks.pipelines.open_tcg_pricing_pipeline", "open_tcg_pricing_pipeline"),
    ("automana.worker.tasks.pipelines.shopify_weekly_pipeline", "shopify_weekly_pipeline"),
    # Rolling refresh tasks
    ("automana.worker.tasks.pipelines.mtgstock_slice_refresh", "mtgstock_slice_refresh"),
    ("automana.worker.tasks.pipelines.mtgstock_incremental_load", "mtgstock_incremental_load"),
    ("automana.worker.tasks.pipelines.mtgstock_discover_new_ids", "mtgstock_discover_new_ids"),
]
```

Note: `mtgstock_slice_refresh` requires `hour_slot` — the parametrized test calls `pipeline_fn.run.__func__(_make_task())` with no extra args, which will raise `TypeError`. Wrap the call for this task:

Add a helper at the top of the test file:

```python
_EXTRA_KWARGS = {
    "mtgstock_slice_refresh": {"hour_slot": 0},
}
```

Then change both parametrized test bodies to:

```python
    extra = _EXTRA_KWARGS.get(func_name, {})
    with patch(
        "automana.worker.tasks.pipelines.run_service",
        return_value={"is_active": True},
    ):
        result = pipeline_fn.run.__func__(_make_task(), **extra)
    assert result is None
```

and:

```python
    extra = _EXTRA_KWARGS.get(func_name, {})
    with patch(
        "automana.worker.tasks.pipelines.run_service",
        return_value={"is_active": True},
    ) as mock_rs:
        pipeline_fn.run.__func__(_make_task(), **extra)
    mock_rs.assert_called_once()
    assert mock_rs.call_args[0][0] == "ops.pipeline_services.is_run_active"
    assert "run_key" in mock_rs.call_args[1]
```

- [ ] **Step 6: Run the idempotency guard tests**

```bash
cd src && python -m pytest automana/tests/unit/tasks/test_pipeline_idempotency_guard.py -v
```

Expected: all parametrized cases pass (previously 12 cases; now 18 cases).

- [ ] **Step 7: Commit**

```bash
git add src/automana/worker/tasks/pipelines.py \
        src/automana/tests/unit/tasks/test_mtgstock_rolling_refresh.py \
        src/automana/tests/unit/tasks/test_pipeline_idempotency_guard.py
git commit -m "feat(mtgstock): add rolling refresh tasks and slice/daily helpers"
```

---

### Task 5: Beat schedule entries

**Files:**
- Modify: `src/automana/worker/celeryconfig.py`

- [ ] **Step 1: Add 8 entries to `beat_schedule` in `celeryconfig.py`**

Append the following inside the `beat_schedule = { ... }` dict, before the closing `}`:

```python
    # MTGStock rolling refresh — 6 API download slices spread across 24h.
    # Each slice covers ~2,276 of the 95,615 known print IDs (~38 min at 1 req/sec).
    # Avoids the 02:00–05:30 AEST heavy-pipeline window.
    "mtgstock-slice-0": {
        "task": "automana.worker.tasks.pipelines.mtgstock_slice_refresh",
        "schedule": crontab(hour=0, minute=30),   # 00:30 AEST
        "kwargs": {"hour_slot": 0},
    },
    "mtgstock-slice-1": {
        "task": "automana.worker.tasks.pipelines.mtgstock_slice_refresh",
        "schedule": crontab(hour=6, minute=30),   # 06:30 AEST
        "kwargs": {"hour_slot": 1},
    },
    "mtgstock-slice-2": {
        "task": "automana.worker.tasks.pipelines.mtgstock_slice_refresh",
        "schedule": crontab(hour=10, minute=0),   # 10:00 AEST
        "kwargs": {"hour_slot": 2},
    },
    "mtgstock-slice-3": {
        "task": "automana.worker.tasks.pipelines.mtgstock_slice_refresh",
        "schedule": crontab(hour=14, minute=0),   # 14:00 AEST
        "kwargs": {"hour_slot": 3},
    },
    "mtgstock-slice-4": {
        "task": "automana.worker.tasks.pipelines.mtgstock_slice_refresh",
        "schedule": crontab(hour=17, minute=0),   # 17:00 AEST
        "kwargs": {"hour_slot": 4},
    },
    "mtgstock-slice-5": {
        "task": "automana.worker.tasks.pipelines.mtgstock_slice_refresh",
        "schedule": crontab(hour=20, minute=0),   # 20:00 AEST
        "kwargs": {"hour_slot": 5},
    },
    # Incremental DB load: stage all of today's refreshed IDs into price_observation.
    # Runs at 23:00 AEST after all 6 slice downloads have had time to complete.
    "mtgstock-incremental-load": {
        "task": "automana.worker.tasks.pipelines.mtgstock_incremental_load",
        "schedule": crontab(hour=23, minute=0),   # 23:00 AEST
    },
    # Weekly new-ID discovery: probe API for print IDs above current local maximum.
    "mtgstock-discover-new-ids": {
        "task": "automana.worker.tasks.pipelines.mtgstock_discover_new_ids",
        "schedule": crontab(hour=1, minute=0, day_of_week=0),  # Sunday 01:00 AEST
    },
```

- [ ] **Step 2: Verify celeryconfig imports cleanly**

```bash
cd src && python -c "import automana.worker.celeryconfig; print('beat entries:', len(automana.worker.celeryconfig.beat_schedule))"
```

Expected: prints a number ≥ 25 (was 22 before; now 22 + 8 = 30 — exact count depends on any additions since last count). No import error.

- [ ] **Step 3: Commit**

```bash
git add src/automana/worker/celeryconfig.py
git commit -m "feat(mtgstock): wire 6 slice + incremental load + discovery tasks to celery beat"
```

---

### Task 6: Full test run + PR

- [ ] **Step 1: Run all unit tests**

```bash
cd src && python -m pytest automana/tests/unit/ -v --tb=short 2>&1 | tail -30
```

Expected: no new failures. All previously passing tests still pass.

- [ ] **Step 2: Verify pipelines module task names are registered correctly**

```bash
cd src && python -c "
from automana.worker.tasks import pipelines
tasks = [
    'mtgstock_slice_refresh',
    'mtgstock_incremental_load',
    'mtgstock_discover_new_ids',
]
for t in tasks:
    fn = getattr(pipelines, t)
    print(f'{t}: name={fn.name}')
"
```

Expected:
```
mtgstock_slice_refresh: name=automana.worker.tasks.pipelines.mtgstock_slice_refresh
mtgstock_incremental_load: name=automana.worker.tasks.pipelines.mtgstock_incremental_load
mtgstock_discover_new_ids: name=automana.worker.tasks.pipelines.mtgstock_discover_new_ids
```

- [ ] **Step 3: Invoke finishing-a-development-branch skill to open PR**

Use `superpowers:finishing-a-development-branch` to open the PR against `dev`.
