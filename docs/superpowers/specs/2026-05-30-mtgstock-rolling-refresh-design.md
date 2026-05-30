# MTGStock Rolling Price Refresh — Design Spec

**Date:** 2026-05-30
**Status:** Approved

---

## Problem

The `mtgStock_download_pipeline` task reads pre-downloaded parquet files from disk and loads them into the DB. It is not scheduled in celery beat. The API scraper (`run_full_load`) exists but runs as a manual one-shot — doing all 95,615 print IDs in one continuous session, which takes an estimated 26+ hours at the current 1 req/sec rate.

CardMarket (EU), CardKingdom, and StarCity Games prices are exclusive to this source. Without rolling refreshes, those prices go stale indefinitely.

---

## Solution: 7-Day Rolling Window, 6 Runs/Day

Divide the 95,615 known print IDs into a 42-slot ring (7 days × 6 runs/day). Each celery beat firing covers one slot (~2,276 IDs, ~38 min at 1 req/sec). After 7 days every ID has been refreshed exactly once. A separate nightly task stages all of that day's refreshed IDs into the DB. A weekly task probes for new print IDs above the current max.

### Key properties

- **Stateless slice selection:** `slice_idx = (day_offset * 6 + hour_slot) % 42` — no Redis cursor, no DB state. Same firing time always produces the same ID list, making reruns idempotent (the pipeline idempotency guard handles duplicate run_keys).
- **Disk-first, same as today:** API fetches update parquet files on disk; DB load is a separate task. No schema changes.
- **Incremental DB load:** the nightly load task passes only the IDs refreshed that day into the existing `bulk_load → raw_to_staging → retry_rejects → staging_to_prices` chain. The ~95K full load is retired.
- **Daily aggregate waits for next morning:** `refresh_daily_prices` already runs at 05:30 AEST; newly staged price observations are folded into Tier 2 naturally the next day. No change needed there.
- **TCG market only (v1):** CardMarket, CardKingdom, StarCity can be added later by widening to a 14-day window.

---

## Numbers

| Metric | Value |
|--------|-------|
| Total print IDs | 95,615 |
| ID range on disk | 1 – 131,977 |
| Window | 7 days |
| Runs per day | 6 |
| Total slots | 42 |
| IDs per run | ~2,276 |
| Run duration (1 req/sec) | ~38 min |
| Total daily API time | ~3.8 hrs (spread across 24h) |
| Max staleness for any card | 7 days |

---

## Beat Schedule (AEST)

Six download runs spread across the day, avoiding the heavy pipeline window (02:00–05:30):

| Time (AEST) | Task | Action |
|-------------|------|--------|
| 00:30 | `mtgstock-slice-0` | API fetch, hour_slot=0 |
| 06:30 | `mtgstock-slice-1` | API fetch, hour_slot=1 |
| 10:00 | `mtgstock-slice-2` | API fetch, hour_slot=2 |
| 14:00 | `mtgstock-slice-3` | API fetch, hour_slot=3 |
| 17:00 | `mtgstock-slice-4` | API fetch, hour_slot=4 |
| 20:00 | `mtgstock-slice-5` | API fetch, hour_slot=5 |
| 23:00 | `mtgstock-incremental-load` | DB stage all of today's IDs |
| Sunday 01:00 | `mtgstock-discover-new-ids` | Probe for new print IDs |

---

## New Components

### 1. `mtgstock_slice_refresh` Celery task (new)

Accepts `hour_slot: int` (0–5). `hour_slot` is **hardcoded as a kwarg in each beat_schedule entry** — it is never inferred from the current clock time, so timezone edge cases and sub-hour offsets are irrelevant.

Slice formula (reference epoch `2026-06-01`):
```python
EPOCH = date(2026, 6, 1)
WINDOW_DAYS, RUNS_PER_DAY, TOTAL_SLICES = 7, 6, 42
day_offset = (date.today() - EPOCH).days
slice_idx = (day_offset * RUNS_PER_DAY + hour_slot) % TOTAL_SLICES
```

Reads `existing_ids.json`, sorts IDs, takes `ids[slice_idx * slice_size : (slice_idx+1) * slice_size]`, then chains:

```
start_run → run_mtgstock_pipeline_selected_lists(ids=slice_ids) → finish_run
```

Run key: `mtgStock_slice:{date}:{hour_slot}` — the idempotency guard deduplicates reruns within the same day/slot.

### 2. `mtgstock_incremental_load` Celery task (new)

Computes the union of all 6 slices for today's `day_offset` — i.e. `ids_for_day = sorted_ids[day_start : day_start + daily_count]` where `day_start = (day_offset % WINDOW_DAYS) * daily_count`. This is deterministic and does not require the 6 download tasks to have all succeeded (the DB load simply re-stages whatever is on disk for those IDs). Chains into the existing staging pipeline with a new `ids_filter` param on `bulk_load`.

Run key: `mtgStock_load:{date}` — idempotency guard deduplicates if beat fires twice.

### 3. `mtgstock_discover_new_ids` Celery task (new)

Calls `get_last_print_id` starting from `max(existing_ids)`. For each new ID found, creates the on-disk directory structure and adds the ID to `existing_ids.json`. New IDs are folded into the rolling window naturally on the next cycle.

Run key: `mtgStock_discover:{date}` — weekly, Sunday only.

### 4. `bulk_load` — add `ids_filter: list[int] | None` param (modified)

When `ids_filter` is provided, skip folders not in the set. This keeps the incremental load O(slice) instead of O(95K).

---

## File Map

| File | Change |
|------|--------|
| `worker/tasks/pipelines.py` | Add 3 new tasks |
| `worker/celeryconfig.py` | Add 8 beat schedule entries |
| `core/services/app_integration/mtg_stock/data_staging.py` | `bulk_load` gets `ids_filter` param |
| `tests/unit/tasks/test_mtgstock_rolling_refresh.py` | New — unit tests for all 3 tasks |
| `tests/unit/services/mtg_stock/test_bulk_load_ids_filter.py` | New — tests for filtered bulk_load |

---

## Out of Scope (v1)

- CardMarket / CardKingdom / StarCity markets — add when window widens to 14 days
- Watchlist priority boosting (Approach C from brainstorm)
- Removing the legacy `mtgStock_download_pipeline` task — keep for manual full reloads
