# eBay Daily Sold Collection — Design Spec

**Date:** 2026-05-24
**Status:** Approved

---

## Goal

Collect eBay sold prices daily with full 24-hour coverage per card, using a hybrid of a
category-wide sweep (discovery + broad reach) and a per-card watchlist scrape (targeted,
paginated). Raw API responses are staged as JSON files on disk before DB ingestion,
providing a replay buffer: if ingestion fails the task re-runs from disk without
re-hitting the eBay API.

---

## Architecture

```
06:45  fetch_fx_rates (existing)            → pricing.fx_rates

09:00  ebay_category_sweep_task (NEW)
         EbayFindingAPIRepository
         3 calls — EBAY-US / EBAY-AU / EBAY-ENCA, no keyword, category=2536, paginated
         → /data/ebay_raw/YYYY-MM-DD/sweep/{marketplace}.json   ← replay buffer
         → title match against all 378 eBay-sourced cards
         → pricing.ebay_scraped_sold

09:45  ebay_scrape_external_sold_task (ENHANCED)
         EbayFindingAPIRepository
         500 cards × 3 markets, min_date=yesterday, paginated (up to 3 pages)
         → /data/ebay_raw/YYYY-MM-DD/watchlist/{spid}_{marketplace}.json
         → pricing.ebay_scraped_sold

10:30  promote_sold_obs (existing — unchanged)
         → pricing.price_observation
```

Both tasks write to the existing `pricing.ebay_scraped_sold` staging table.
`promote_sold_obs` is unchanged — it aggregates whatever lands in staging.

---

## Scope

### In scope
- New `EbayCategorySweepService` and `ebay_category_sweep_task`
- Pagination added to `EbayFindingAPIRepository.find_completed_items`
- JSON staging added to `scrape_global_market_service` (replay buffer)
- New DB repository method `get_ebay_card_lookup()` for card name → source_product_id mapping
- Celery beat schedule updated (new task + shifted timings)
- 7-day JSON file cleanup maintenance task
- Redis API quota guard shared across both tasks
- Integration tests for both new pipelines

### Out of scope
- Changing `promote_sold_obs` or `price_observation` schema
- Creating new `source_product` rows from unmatched category sweep items
- FX normalisation (existing known limitation, tracked separately)
- Watchlist management changes

---

## Component Design

### 1. `find_completed_items` — Pagination

**File:** `src/automana/core/repositories/app_integration/ebay/ApiFinding_repository.py`

Add a `max_pages` parameter (default 3). Loop from page 1 until either:
- The response's `totalPages` is reached, or
- `max_pages` is reached, or
- The response returns 0 items

```python
async def find_completed_items(
    self,
    keywords: Optional[str],     # CHANGED — None omits the keywords filter (category sweep)
    app_id: str,
    *,
    global_id: str = "EBAY-US",
    category_id: int = 2536,
    condition_id: Optional[int] = None,
    min_date: Optional[datetime] = None,
    limit: int = 100,
    max_pages: int = 1,          # NEW — set to 3 for watchlist, 100 for sweep
) -> list[dict]:
```

When `keywords=None`, the `keywords` key is omitted from the API request entirely so
eBay returns all listings in the category. Rate-limit handling already exists and applies
per-page.

---

### 2. `EbayCategorySweepService`

**File:** `src/automana/core/services/app_integration/ebay/category_sweep_service.py`

Runs once per marketplace per day. Each marketplace invocation:

```
1. Check /data/ebay_raw/{today}/sweep/{marketplace}.json
   → exists: read items from file (replay path)
   → missing: call find_completed_items(keywords=None, max_pages=100)
              write raw items to JSON file

2. Load card lookup dict from DB via get_ebay_card_lookup()
   → {normalised_card_name: {source_product_id, card_name, set_code, ...}}
   (one DB query, 378 rows)

3. For each raw item:
   for each card in lookup:
     score = score_title(item.title, card.card_name, card.set_code, is_foil=None, frame=None)
   take highest-scoring card if score >= 0.5
   → matched: check frame conflict, parse finish/condition, insert to ebay_scraped_sold
   → unmatched: skip

4. Return {marketplace, fetched, matched, skipped, inserted}
```

No keyword is passed to the Finding API — the category filter (`categoryId=2536`,
`SoldItemsOnly=true`) is sufficient.

**Why 0.5 threshold:** eBay sellers rarely include set codes in titles. A unique card name
like "Sheoldred, the Apocalypse" scores ~0.5–0.6 without a set code match. 0.5 is the
floor that rejects generic noise ("MTG Lot 50 cards") while passing named singles.

---

### 3. `get_ebay_card_lookup()` — New Repository Method

**File:** `src/automana/core/repositories/app_integration/ebay/sales_repository.py`

```python
async def get_ebay_card_lookup(self) -> list[dict]:
    """Returns all eBay source_products with card metadata for title matching."""
```

Query:
```sql
SELECT sp.source_product_id,
       ucr.card_name,
       cs.set_code,
       ps.code          AS source_code
FROM   pricing.source_product sp
JOIN   pricing.price_source ps       ON sp.source_id    = ps.source_id
JOIN   pricing.mtg_card_products mcp ON sp.product_id   = mcp.product_id
JOIN   card_catalog.card_version cv  ON mcp.card_version_id = cv.card_version_id
JOIN   card_catalog.unique_cards_ref ucr ON cv.unique_card_id = ucr.unique_card_id
JOIN   card_catalog.sets cs          ON cv.set_id        = cs.set_id
WHERE  ps.code = 'ebay'
```

Returns one row per source_product_id. The service builds the lookup dict in memory.

---

### 4. `scrape_global_market_service` — JSON Staging Enhancement

**File:** `src/automana/core/services/app_integration/ebay/scrape_global_market_service.py`

Two additions per card+marketplace iteration:

**Before API call:**
```python
json_path = ebay_raw_dir / today / "watchlist" / f"{source_product_id}_{marketplace}.json"
if json_path.exists():
    items = load_items_from_json(json_path)   # replay path
else:
    items = await finding.find_completed_items(..., max_pages=3)
    write_items_to_json(json_path, items, marketplace, source_product_id)
```

**Pagination:** `max_pages=3` (300 items max per card per marketplace).

No other changes to scoring, filtering, or DB insertion logic.

---

### 5. JSON File Format

Identical schema for both sweep and watchlist files:

```json
{
  "fetched_at": "2026-05-24T09:00:00Z",
  "marketplace": "EBAY-US",
  "source_product_id": 12060647,
  "items": [
    {
      "item_id": "...",
      "title": "...",
      "price": 18.99,
      "currency": "USD",
      "condition": "Like New",
      "sold_date": "2026-05-23T14:22:00.000Z"
    }
  ]
}
```

`source_product_id` is `null` for sweep files (card identity is unknown at fetch time).

**Storage path:**
```
/data/ebay_raw/
  2026-05-24/
    sweep/
      EBAY-US.json
      EBAY-AU.json
      EBAY-ENCA.json
    watchlist/
      12060647_EBAY-US.json
      12060647_EBAY-AU.json
      ...
```

**Cleanup:** Files older than 7 days are deleted by a lightweight Celery beat maintenance
task that runs weekly (`find /data/ebay_raw -mtime +7 -delete`).

---

### 6. API Quota Guard

A Redis counter key `ebay:api_calls:{YYYY-MM-DD}` is incremented by both tasks on every
Finding API call (each page = 1 call). If the counter reaches 4,500 (90% of the 5,000
free-tier daily limit), the current task logs a warning and stops querying for the day.
Remaining cards/pages are skipped — not failed — so `promote_sold_obs` still runs on
whatever was collected.

---

### 7. Celery Schedule Changes

**File:** `src/automana/worker/celeryconfig.py`

```python
# NEW
"ebay_category_sweep": {
    "task":     "automana.worker.tasks.ebay.ebay_category_sweep_task",
    "schedule": crontab(hour=9, minute=0),
},

# MODIFIED — shifted from 07:15 to 09:45
"ebay_scrape_external_sold": {
    "task":     "automana.worker.tasks.ebay.ebay_scrape_external_sold_task",
    "schedule": crontab(hour=9, minute=45),
},

# MODIFIED — shifted from 08:00 to 10:30
"promote_sold_obs": {
    "task":     "automana.worker.tasks.ebay.promote_sold_obs_task",
    "schedule": crontab(hour=10, minute=30),
},
```

All times AEST.

---

### 8. New Celery Task

**File:** `src/automana/worker/tasks/ebay.py`

```python
@celery_app.task(name="automana.worker.tasks.ebay.ebay_category_sweep_task")
def ebay_category_sweep_task():
    """Daily category-wide eBay sold sweep across EBAY-US, EBAY-AU, EBAY-ENCA."""
    run_service("EbayCategorySweepService")
```

Follows the existing `run_service` pattern — no `autoretry_for`, retry handled at the
`run_service` level.

`EbayCategorySweepService` must be decorated with `@ServiceRegistry.register(...)` so
`run_service` can resolve it by name. Use the same `db_repositories` and
`api_repositories` wiring pattern as `scrape_global_market_service.py`.

---

## Error Handling

| Failure | Behaviour |
|---|---|
| Rate-limited mid-sweep | Saves fetched pages to JSON, stops pagination, logs warning. Promote runs on partial data. |
| JSON write fails | Logs error, proceeds with direct DB insert (no replay for that file). |
| DB insert fails (partial) | Task fails, Celery retries. JSON file exists → replay path, no duplicate API call. |
| JSON file corrupt on replay | Deletes file, falls back to fresh API call, overwrites. |
| Disk full (`/data/ebay_raw/`) | Task fails with clear log. Weekly cleanup prevents accumulation. |
| Quota guard triggered | Remaining cards/pages skipped, warning logged, partial results promoted. |

---

## Testing

### `tests/integration/services/ebay/test_category_sweep.py`

**`test_category_sweep_ingest`** (CI-safe, no network):
- Seeds 3 eBay source_products in test DB
- Writes synthetic `sweep/EBAY-US.json` with 2 matching items + 1 noise item
- Runs `EbayCategorySweepService` in replay mode
- Asserts: 2 rows in `ebay_scraped_sold`, noise item skipped, `result["matched"] == 2`

**`test_watchlist_pagination_ingest`** (CI-safe, no network):
- Seeds 1 source_product in test DB
- Writes synthetic `watchlist/{spid}_EBAY-US.json` with 150 items
- Runs enhanced `scrape_global_market_service` in replay mode
- Asserts: 150 rows inserted, no duplicate `item_id`s

**`test_live_category_sweep`** (`@pytest.mark.live`, skipped in CI):
- Calls real eBay API (`EBAY_APP_ID` required), limit=20, page 1 only
- Asserts: JSON file written to disk, at least 1 item matched to a known card
- Prints matched/skipped counts

---

## File Map

| Action | Path |
|---|---|
| Create | `src/automana/core/services/app_integration/ebay/category_sweep_service.py` |
| Modify | `src/automana/core/repositories/app_integration/ebay/ApiFinding_repository.py` |
| Modify | `src/automana/core/repositories/app_integration/ebay/sales_repository.py` |
| Modify | `src/automana/core/services/app_integration/ebay/scrape_global_market_service.py` |
| Modify | `src/automana/worker/tasks/ebay.py` |
| Modify | `src/automana/worker/celeryconfig.py` |
| Create | `tests/integration/services/ebay/test_category_sweep.py` |
