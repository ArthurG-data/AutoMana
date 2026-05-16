# MTGStocks Bulk Load — Print ID Range & Parallel Processing

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `start_id`/`end_id` range filtering and concurrent folder reads (via `asyncio.as_completed` + semaphore) to `bulk_load`, with zero behaviour change when neither feature is used.

**Architecture:** The sequential folder loop in `bulk_load` is replaced by a chunked `itertools.batched` outer loop; within each chunk all folder reads run concurrently under a shared `asyncio.Semaphore`. Range filtering is applied to the folder list after `os.listdir` and before any I/O.

**Tech Stack:** Python 3.12, asyncio, pandas, tqdm, pytest-asyncio

---

## File Map

| Action | Path | What changes |
|--------|------|-------------|
| Modify | `src/automana/core/services/app_integration/mtg_stock/data_staging.py` | `import itertools`, new params, range filter, `_process_folder` inner fn, chunked `as_completed` loop |
| Modify | `tests/unit/core/services/app_integration/mtg_stock/test_data_staging.py` | New test classes for range filter and parallel behaviour |

No other files change.

---

## Context: `process_info_file` return shape

`process_info_file` (defined at the top of `data_staging.py`) returns this dict:

```python
{
    "mtgstock": <int print_id>,   # KEY IS "mtgstock", not "id"
    "card_name": <str | None>,
    "set_abbr": <str | None>,
    "collector_number": <str | None>,
    "cardtrader": <any | None>,
    "scryfallId": <str | None>,
    "multiverse_ids": <any | None>,
    "tcg_id": <int | None>,
    "cardtrader_id": <int | None>,
}
```

All test fakes must use `"mtgstock"` as the print-ID key or `id_dict["mtgstock"]` will raise `KeyError` at runtime.

---

## Shared test fixture (add once, reuse in both task test classes)

Both `TestBulkLoadRangeFilter` and `TestBulkLoadParallel` need a minimal `process_info_file` / `process_prices_file` pair. Define a module-level helper at the bottom of `test_data_staging.py` imports section (before the test classes):

```python
import pandas as pd


def _fake_folder_fns():
    """Return (fake_info, fake_prices) coroutine functions for testing bulk_load.

    fake_info reads the folder name from the path and returns a dict shaped
    exactly like the real process_info_file output (key "mtgstock" for the
    print ID).  fake_prices returns a one-row DataFrame shaped like
    raw_mtg_stock_price so pd.concat does not raise on column mismatches.
    """

    async def fake_info(path: str) -> dict:
        folder = path.split("/")[-2]          # .../root/<folder>/info.json
        pid = int(folder)
        return {
            "mtgstock": pid,
            "card_name": f"Card {pid}",
            "set_abbr": None,
            "collector_number": None,
            "cardtrader": None,
            "scryfallId": None,
            "multiverse_ids": None,
            "tcg_id": None,
            "cardtrader_id": None,
        }

    async def fake_prices(path: str, id_dict: dict) -> pd.DataFrame:
        return pd.DataFrame({
            "ts_date": ["2024-01-01"],
            "price_low": [1.0],
            "price_avg": [1.5],
            "price_foil": [None],
            "price_market": [None],
            "price_market_foil": [None],
            "print_id": [id_dict["mtgstock"]],
            "game_code": ["mtg"],
            "source_code": ["mtgstocks"],
            "scraped_at": [pd.Timestamp.now()],
        })

    return fake_info, fake_prices
```

---

## Task 1: Print ID range filtering

### Files
- Modify: `tests/unit/core/services/app_integration/mtg_stock/test_data_staging.py`
- Modify: `src/automana/core/services/app_integration/mtg_stock/data_staging.py`

- [ ] **Step 1.1 — Write the failing tests**

Add the `import pandas as pd` and `_fake_folder_fns` helper (from the shared fixture section above) to the top of the test file, then append this class:

```python
# ---------------------------------------------------------------------------
# bulk_load — print-ID range filtering
# ---------------------------------------------------------------------------

_PATCH_INFO   = "automana.core.services.app_integration.mtg_stock.data_staging.process_info_file"
_PATCH_PRICES = "automana.core.services.app_integration.mtg_stock.data_staging.process_prices_file"


class TestBulkLoadRangeFilter:
    async def test_no_filter_processes_empty_list(self):
        """When no filter is set and listdir returns nothing, no COPY fires."""
        price_repo = AsyncMock()
        price_repo.clear_raw_prices.return_value = 0
        ops_repo = AsyncMock()

        with patch("os.listdir", return_value=[]):
            await staging.bulk_load(
                price_repository=price_repo,
                ops_repository=ops_repo,
                root_folder="/fake/root",
            )

        price_repo.copy_prices_mtgstock.assert_not_awaited()

    async def test_start_id_excludes_lower_ids(self):
        """Folders with print_id < start_id must not be processed."""
        price_repo = AsyncMock()
        price_repo.clear_raw_prices.return_value = 0
        ops_repo = AsyncMock()
        fake_info, fake_prices = _fake_folder_fns()
        processed: list[int] = []

        async def tracking_info(path: str) -> dict:
            result = await fake_info(path)
            processed.append(result["mtgstock"])
            return result

        with patch("os.listdir", return_value=["100", "200", "300"]), \
             patch(_PATCH_INFO, side_effect=tracking_info), \
             patch(_PATCH_PRICES, side_effect=fake_prices):
            await staging.bulk_load(
                price_repository=price_repo,
                ops_repository=ops_repo,
                root_folder="/fake/root",
                start_id=200,
            )

        assert 100 not in processed
        assert 200 in processed
        assert 300 in processed

    async def test_end_id_excludes_higher_ids(self):
        """Folders with print_id > end_id must not be processed."""
        price_repo = AsyncMock()
        price_repo.clear_raw_prices.return_value = 0
        ops_repo = AsyncMock()
        fake_info, fake_prices = _fake_folder_fns()
        processed: list[int] = []

        async def tracking_info(path: str) -> dict:
            result = await fake_info(path)
            processed.append(result["mtgstock"])
            return result

        with patch("os.listdir", return_value=["100", "200", "300"]), \
             patch(_PATCH_INFO, side_effect=tracking_info), \
             patch(_PATCH_PRICES, side_effect=fake_prices):
            await staging.bulk_load(
                price_repository=price_repo,
                ops_repository=ops_repo,
                root_folder="/fake/root",
                end_id=200,
            )

        assert 100 in processed
        assert 200 in processed
        assert 300 not in processed

    async def test_both_bounds_narrow_window(self):
        """Only folders within [start_id, end_id] inclusive are processed."""
        price_repo = AsyncMock()
        price_repo.clear_raw_prices.return_value = 0
        ops_repo = AsyncMock()
        fake_info, fake_prices = _fake_folder_fns()
        processed: list[int] = []

        async def tracking_info(path: str) -> dict:
            result = await fake_info(path)
            processed.append(result["mtgstock"])
            return result

        with patch("os.listdir", return_value=["100", "200", "300", "400", "500"]), \
             patch(_PATCH_INFO, side_effect=tracking_info), \
             patch(_PATCH_PRICES, side_effect=fake_prices):
            await staging.bulk_load(
                price_repository=price_repo,
                ops_repository=ops_repo,
                root_folder="/fake/root",
                start_id=200,
                end_id=400,
            )

        assert set(processed) == {200, 300, 400}

    async def test_non_digit_folders_excluded_when_range_active(self):
        """Non-numeric folder names (e.g. 'existing_ids.json') must be skipped
        when range filtering is active — they must never reach process_info_file."""
        price_repo = AsyncMock()
        price_repo.clear_raw_prices.return_value = 0
        ops_repo = AsyncMock()
        fake_info, fake_prices = _fake_folder_fns()

        with patch("os.listdir", return_value=["existing_ids.json", "100", "200"]), \
             patch(_PATCH_INFO, side_effect=fake_info) as mock_info, \
             patch(_PATCH_PRICES, side_effect=fake_prices):
            await staging.bulk_load(
                price_repository=price_repo,
                ops_repository=ops_repo,
                root_folder="/fake/root",
                start_id=100,
                end_id=200,
            )

        calls = [c.args[0] for c in mock_info.await_args_list]
        assert not any("existing_ids.json" in c for c in calls)
```

- [ ] **Step 1.2 — Run the tests to confirm they fail**

```bash
pytest tests/unit/core/services/app_integration/mtg_stock/test_data_staging.py::TestBulkLoadRangeFilter -v
```

Expected: `FAILED` — `bulk_load` does not yet accept `start_id`/`end_id`.

- [ ] **Step 1.3 — Add `import itertools` and new parameters to `bulk_load`**

Open `src/automana/core/services/app_integration/mtg_stock/data_staging.py`.

Change:
```python
import asyncio
import os, json, logging
```
to:
```python
import asyncio
import itertools
import os, json, logging
```

Change the `bulk_load` signature from:
```python
async def bulk_load(price_repository: PriceRepository
                    , ops_repository: OpsRepository
                    , root_folder
                    , batch_size=2000
                    , ingestion_run_id: int = None
                    , market: str = "tcg"):
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
                    concurrency: int = 20):
```

- [ ] **Step 1.4 — Add range filter after `os.listdir`**

Locate this block in `bulk_load`:

```python
    # Cache listdir once — the directory can hold ~500k entries on a full load.
    folders = os.listdir(root_folder)
    deleted = await price_repository.clear_raw_prices()
```

Replace with:

```python
    # Cache listdir once — the directory can hold ~500k entries on a full load.
    folders = os.listdir(root_folder)
    if start_id is not None or end_id is not None:
        folders = [
            f for f in folders
            if f.isdigit()
            and (start_id is None or int(f) >= start_id)
            and (end_id is None or int(f) <= end_id)
        ]
    deleted = await price_repository.clear_raw_prices()
```

- [ ] **Step 1.5 — Run the range tests to confirm they pass**

```bash
pytest tests/unit/core/services/app_integration/mtg_stock/test_data_staging.py::TestBulkLoadRangeFilter -v
```

Expected: all 5 tests `PASSED`.

- [ ] **Step 1.6 — Run the full staging test suite**

```bash
pytest tests/unit/core/services/app_integration/mtg_stock/test_data_staging.py -v
```

Expected: all tests `PASSED`.

- [ ] **Step 1.7 — Commit**

```bash
git add src/automana/core/services/app_integration/mtg_stock/data_staging.py \
        tests/unit/core/services/app_integration/mtg_stock/test_data_staging.py
git commit -m "feat(mtgstock): add start_id/end_id range filter to bulk_load"
```

---

## Task 2: Parallel folder processing

### Files
- Modify: `tests/unit/core/services/app_integration/mtg_stock/test_data_staging.py`
- Modify: `src/automana/core/services/app_integration/mtg_stock/data_staging.py`

- [ ] **Step 2.1 — Write the failing parallel tests**

Append this class to the test file:

```python
# ---------------------------------------------------------------------------
# bulk_load — parallel processing with as_completed + semaphore
# ---------------------------------------------------------------------------

class TestBulkLoadParallel:

    async def test_copy_called_once_per_batch_chunk(self):
        """With 6 folders and batch_size=2, copy_prices_mtgstock must be
        called exactly 3 times — one flush per chunk."""
        price_repo = AsyncMock()
        price_repo.clear_raw_prices.return_value = 0
        ops_repo = AsyncMock()
        fake_info, fake_prices = _fake_folder_fns()

        with patch("os.listdir", return_value=["10", "20", "30", "40", "50", "60"]), \
             patch(_PATCH_INFO, side_effect=fake_info), \
             patch(_PATCH_PRICES, side_effect=fake_prices):
            await staging.bulk_load(
                price_repository=price_repo,
                ops_repository=ops_repo,
                root_folder="/fake/root",
                batch_size=2,
                concurrency=4,
            )

        assert price_repo.copy_prices_mtgstock.await_count == 3

    async def test_insert_batch_step_called_per_chunk(self):
        """ops_repository.insert_batch_step must be called once per chunk
        that produces at least one successful row."""
        price_repo = AsyncMock()
        price_repo.clear_raw_prices.return_value = 0
        ops_repo = AsyncMock()
        fake_info, fake_prices = _fake_folder_fns()

        with patch("os.listdir", return_value=["10", "20", "30", "40"]), \
             patch(_PATCH_INFO, side_effect=fake_info), \
             patch(_PATCH_PRICES, side_effect=fake_prices):
            await staging.bulk_load(
                price_repository=price_repo,
                ops_repository=ops_repo,
                root_folder="/fake/root",
                batch_size=2,
                concurrency=2,
            )

        assert ops_repo.insert_batch_step.await_count == 2

    async def test_error_in_one_folder_does_not_cancel_others(self):
        """If one folder's read raises, remaining folders in the same chunk
        still produce rows and are COPYed. The error is counted but does not
        propagate."""
        price_repo = AsyncMock()
        price_repo.clear_raw_prices.return_value = 0
        ops_repo = AsyncMock()
        _, fake_prices = _fake_folder_fns()

        async def failing_info(path: str) -> dict:
            folder = path.split("/")[-2]
            if folder == "20":
                raise OSError("parquet missing")
            return {
                "mtgstock": int(folder), "card_name": None, "set_abbr": None,
                "collector_number": None, "cardtrader": None, "scryfallId": None,
                "multiverse_ids": None, "tcg_id": None, "cardtrader_id": None,
            }

        with patch("os.listdir", return_value=["10", "20", "30"]), \
             patch(_PATCH_INFO, side_effect=failing_info), \
             patch(_PATCH_PRICES, side_effect=fake_prices):
            await staging.bulk_load(
                price_repository=price_repo,
                ops_repository=ops_repo,
                root_folder="/fake/root",
                batch_size=10,
                concurrency=3,
            )

        # COPY must fire — 2 successful folders produce rows.
        price_repo.copy_prices_mtgstock.assert_awaited_once()
        df_arg = price_repo.copy_prices_mtgstock.await_args.args[0]
        assert len(df_arg) == 2   # one row per successful folder

    async def test_concurrency_one_matches_sequential_output(self):
        """concurrency=1 (only one folder at a time) produces the same
        observable result as the old sequential loop: one COPY with all rows."""
        price_repo = AsyncMock()
        price_repo.clear_raw_prices.return_value = 0
        ops_repo = AsyncMock()
        fake_info, fake_prices = _fake_folder_fns()

        with patch("os.listdir", return_value=["1", "2", "3"]), \
             patch(_PATCH_INFO, side_effect=fake_info), \
             patch(_PATCH_PRICES, side_effect=fake_prices):
            await staging.bulk_load(
                price_repository=price_repo,
                ops_repository=ops_repo,
                root_folder="/fake/root",
                batch_size=10,
                concurrency=1,
            )

        # All 3 folders fit in one chunk → one COPY call with 3 rows.
        price_repo.copy_prices_mtgstock.assert_awaited_once()
        df_arg = price_repo.copy_prices_mtgstock.await_args.args[0]
        assert len(df_arg) == 3
```

- [ ] **Step 2.2 — Run the parallel tests to confirm they fail**

```bash
pytest tests/unit/core/services/app_integration/mtg_stock/test_data_staging.py::TestBulkLoadParallel -v
```

Expected: `FAILED` — the sequential loop doesn't honour `concurrency` and the `as_completed` structure isn't in place yet.

- [ ] **Step 2.3 — Replace the sequential folder loop with the parallel implementation**

In `data_staging.py`, find the entire `bulk_load` function body (from the `step_name = "bulk_load"` line to the end of the function, including the tail-flush block). Replace it with:

```python
    step_name = "bulk_load"
    batch_number = 1

    folders = os.listdir(root_folder)
    if start_id is not None or end_id is not None:
        folders = [
            f for f in folders
            if f.isdigit()
            and (start_id is None or int(f) >= start_id)
            and (end_id is None or int(f) <= end_id)
        ]

    deleted = await price_repository.clear_raw_prices()
    logger.info("bulk_load: cleared stale rows from raw_mtg_stock_price", extra={"deleted": deleted})

    sem = asyncio.Semaphore(concurrency)

    async def _process_folder(folder: str):
        async with sem:
            try:
                pdir = os.path.join(root_folder, folder)
                id_dict = await process_info_file(os.path.join(pdir, "info.json"))
                price_df = await process_prices_file(
                    os.path.join(pdir, f"prices.{market}.parquet"), id_dict
                )
                price_df["card_name"] = id_dict.get("card_name")
                price_df["set_abbr"] = id_dict.get("set_abbr")
                price_df["collector_number"] = id_dict.get("collector_number")
                price_df["scryfall_id"] = id_dict.get("scryfallId")
                price_df["tcg_id"] = id_dict.get("tcg_id")
                price_df["cardtrader_id"] = id_dict.get("cardtrader_id")
                return folder, price_df, id_dict, None
            except Exception as exc:
                return folder, None, None, exc

    pbar = tqdm(total=len(folders), desc="Processing MTG Stock folders")

    async with track_step(ops_repository, ingestion_run_id, step_name):
        chunk_start_idx = 0
        for chunk in itertools.batched(folders, batch_size):
            price_rows: list = []
            folder_errors = 0
            ids_master_dict: dict = {}

            tasks = [_process_folder(f) for f in chunk]
            for coro in asyncio.as_completed(tasks):
                folder_name, price_df, id_dict, error = await coro
                if error is not None:
                    folder_errors += 1
                    logger.warning("Error processing folder", extra={"folder": folder_name, "error": str(error)})
                else:
                    price_rows.append(price_df)
                    ids_master_dict[id_dict["mtgstock"]] = {
                        k: v for k, v in id_dict.items() if k != "mtgstock"
                    }
                pbar.update(1)

            chunk_end_idx = chunk_start_idx + len(chunk)

            if price_rows:
                big_price_df = pd.concat(price_rows, ignore_index=True)
                start = time.perf_counter()
                if ingestion_run_id is not None:
                    await ops_repository.update_run(
                        ingestion_run_id=ingestion_run_id, current_step=step_name, status="running"
                    )
                await price_repository.copy_prices_mtgstock(big_price_df)
                if ingestion_run_id is not None:
                    await ops_repository.update_ids_master_dict(
                        ingestion_run_id=ingestion_run_id, ids_master_dict=ids_master_dict
                    )
                elapsed = time.perf_counter() - start
                batch_result = MTGStockBatchStep(
                    ingestion_run_id=ingestion_run_id,
                    step_name=step_name,
                    batch_seq=batch_number,
                    range_start=chunk_start_idx,
                    range_end=chunk_end_idx,
                    total_in_batch=len(big_price_df),
                    items_ok=len(big_price_df),
                    items_failed=folder_errors,
                    status="success" if folder_errors == 0 else "partial",
                    bytes_processed=int(big_price_df.memory_usage(deep=True).sum()),
                    duration_ms=int(elapsed * 1000),
                )
                await ops_repository.insert_batch_step(batch_result)
                batch_number += 1
                logger.info(
                    "copy_prices batch complete",
                    extra={"elapsed_s": round(elapsed, 3), "rows": len(big_price_df)},
                )

            chunk_start_idx = chunk_end_idx

    pbar.close()
```

- [ ] **Step 2.4 — Run the parallel tests to confirm they pass**

```bash
pytest tests/unit/core/services/app_integration/mtg_stock/test_data_staging.py::TestBulkLoadParallel -v
```

Expected: all 4 tests `PASSED`.

- [ ] **Step 2.5 — Run the full mtgstock test suite**

```bash
pytest tests/unit/core/services/app_integration/mtg_stock/ \
       tests/unit/worker/test_mtgstock_pipeline_wiring.py -v
```

Expected: all tests `PASSED`.

- [ ] **Step 2.6 — Commit**

```bash
git add src/automana/core/services/app_integration/mtg_stock/data_staging.py \
        tests/unit/core/services/app_integration/mtg_stock/test_data_staging.py
git commit -m "feat(mtgstock): parallel folder reads via as_completed + semaphore in bulk_load"
```

---

## Task 3: Final validation

- [ ] **Step 3.1 — Run the full unit test suite**

```bash
pytest tests/unit/ -q --tb=short 2>&1 | tail -15
```

Expected: same 20 pre-existing failures (in `test_strategies.py`, `test_market_price_service.py`, `test_listing_actions_service.py`, `test_pricing_report.py`), zero new failures.

- [ ] **Step 3.2 — Verify the ServiceRegistry config flags still hold**

```bash
pytest tests/unit/core/services/app_integration/mtg_stock/test_data_staging.py::TestServiceConfigFlags -v
```

Expected: all 4 tests `PASSED`.

- [ ] **Step 3.3 — Finish**

Both steps pass → feature is complete. Proceed to the `superpowers:finishing-a-development-branch` skill or open a PR.
