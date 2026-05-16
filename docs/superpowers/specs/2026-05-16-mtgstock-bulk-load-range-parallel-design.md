# MTGStocks Bulk Load — Print ID Range & Parallel Processing

**Date:** 2026-05-16  
**Status:** Approved  
**File:** `src/automana/core/services/app_integration/mtg_stock/data_staging.py`

---

## Problem

`bulk_load` processes every folder under `root_folder` sequentially — one parquet file at a time. For a full historical load (~500 k folders) this means:

- No way to scope a run to a subset of cards (e.g. "only IDs 50 000–100 000 for a quick backfill").
- File I/O is single-threaded; CPU and disk sit idle while the event loop awaits each read.

---

## Goals

1. **Print ID range** — add optional `start_id` / `end_id` parameters that gate which card folders are processed.
2. **Parallel folder reads** — use `asyncio.as_completed` + a semaphore so up to `concurrency` folders are read concurrently within each batch window.
3. **Zero behaviour change** when neither feature is used — existing Celery pipeline task (`pipelines.py`) continues to work without modification.

---

## Non-goals

- Parallelising the PostgreSQL COPY (it stays single-writer per batch, as today).
- Changing the download phase (`data_loader.py`).
- Modifying `from_raw_to_staging`, `retry_rejects`, or `from_staging_to_prices`.

---

## New Parameters on `bulk_load`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `start_id` | `int \| None` | `None` | Minimum print_id (inclusive). `None` = no lower bound. |
| `end_id` | `int \| None` | `None` | Maximum print_id (inclusive). `None` = no upper bound. |
| `concurrency` | `int` | `20` | Semaphore width — max concurrent folder reads per batch. |

---

## Architecture

### Range filtering

Applied immediately after `os.listdir(root_folder)`, before any I/O:

```python
if start_id is not None or end_id is not None:
    folders = [
        f for f in folders
        if f.isdigit()
        and (start_id is None or int(f) >= start_id)
        and (end_id is None or int(f) <= end_id)
    ]
```

Non-digit entries are silently skipped (they were already skipped implicitly by failing `process_info_file`).

### Parallel folder reads

The sequential `for i, folder in enumerate(folders)` loop is replaced with:

1. **`_process_folder(folder, sem)` inner async function** — acquires `sem`, calls `process_info_file` + `process_prices_file`, appends metadata columns, returns `(folder_name, price_df, id_dict, None)` on success or `(folder_name, None, None, exc)` on error. Errors are *returned*, not raised, so one bad folder does not cancel sibling tasks.

2. **Outer chunked loop** — iterates over `batch_size`-sized chunks of `folders` using `itertools.batched` (Python 3.12 stdlib):

```
for chunk in itertools.batched(folders, batch_size):
    sem = asyncio.Semaphore(concurrency)
    tasks = [_process_folder(f, sem) for f in chunk]

    for coro in asyncio.as_completed(tasks):
        folder_name, price_df, id_dict, error = await coro
        if error:
            folder_errors += 1
            logger.warning(...)
        else:
            price_rows.append(price_df)
            ids_master_dict[...] = ...

    # flush chunk → DB (same COPY + ops tracking as today)
    if price_rows:
        big_df = pd.concat(price_rows, ignore_index=True)
        price_rows.clear()
        await price_repository.copy_prices_mtgstock(big_df)
        await ops_repository.update_ids_master_dict(...)
        ids_master_dict = {}
        await ops_repository.insert_batch_step(MTGStockBatchStep(...))
        batch_number += 1
        folder_errors = 0
```

The semaphore is created once before the outer loop and shared across all chunks.

### Ops tracking

| Field | Behaviour |
|-------|-----------|
| `batch_number` | Increments once per chunk flush — unchanged. |
| `range_start` / `range_end` | Global folder-list index of the first / last folder in the chunk (not print_id values). Same semantics as today. |
| `folder_errors` | Counts errors within the chunk, reset after each flush. |
| `ids_master_dict` | Accumulated per folder within chunk, flushed + cleared after COPY. |

### tqdm

`tqdm(enumerate(folders))` is replaced with a manual progress bar (`tqdm(total=len(folders))`) updated by `pbar.update(1)` after each `await coro`.

---

## Data Flow (updated)

```
os.listdir(root_folder)
        │
        ▼  [range filter: start_id / end_id]
        │
        ▼  itertools.batched(folders, batch_size)
        │
 ┌──────▼──────┐
 │  chunk loop  │
 │              │   asyncio.as_completed + Semaphore(concurrency)
 │  folder tasks├──► _process_folder(f) × len(chunk)
 │              │       • process_info_file  (asyncio.to_thread)
 │              │       • process_prices_file (asyncio.to_thread)
 │              │       returns (name, df, id_dict, err)
 │   accumulate ◄────────────────────────────────────────────────
 │   price_rows │
 │   ids_master │
 └──────┬───────┘
        │ (when chunk done)
        ▼
  pd.concat + COPY → pricing.raw_mtg_stock_price
        │
        ▼
  ops: update_ids_master_dict, insert_batch_step
```

---

## Unchanged

- `process_info_file`, `process_prices_file` — untouched.
- `price_repository.copy_prices_mtgstock` — untouched.
- `pipelines.py` — no changes; `start_id`, `end_id`, `concurrency` default to values that reproduce existing behaviour exactly.
- All four downstream services (`from_raw_to_staging`, `retry_rejects`, `from_staging_to_prices`, `finish_run`).
- `ServiceRegistry` registration options (`runs_in_transaction=False`, `command_timeout=3600`).

---

## Testing Plan

- **Unit — range filter**: parametrize over `(start_id, end_id, folders_input, expected_folders_after_filter)`.
- **Unit — parallel happy path**: mock `process_info_file` + `process_prices_file`; assert COPY called once per `batch_size` folders, `insert_batch_step` called correct number of times.
- **Unit — error isolation**: one folder raises; assert `folder_errors == 1`, remaining rows still COPYed.
- **Unit — no-filter baseline**: `start_id=None, end_id=None, concurrency=1` → behaviour identical to sequential original.
