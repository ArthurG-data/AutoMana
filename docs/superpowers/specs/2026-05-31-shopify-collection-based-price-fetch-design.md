# Shopify Collection-Based Price Fetch

**Date:** 2026-05-31
**Status:** Approved
**Extends:** `2026-05-22-shopify-multi-store-pipeline-design.md`, `2026-05-23-shopify-collection-sync-and-market-wiring-design.md`

---

## Problem

The existing `fetch_all_markets` step hits `/products.json` directly, which:
- Has no Link-header pagination on the public storefront — the existing `iter_products_pages` reads `response.headers.get("link")`, gets nothing, and stops after 250 products
- Even if pagination worked, Shopify caps public `/products.json` at ~3,000 products total

`tcg.goodgames.com.au` (gg-brisbane) has far more MTG singles than 250.

The TCG ID link is confirmed working — every single product embeds `data-tcgid` in `body_html` inside `<div class="catalogMetaData">`. Condition variants (`Near Mint`, `Lightly Played`, `Moderately Played`) are also confirmed present.

---

## Verified Store Facts (live curl checks)

| Check | Result |
|-------|--------|
| Correct store URL | `tcg.goodgames.com.au` (not `gg-brisbane.myshopify.com`) |
| Pagination mechanism | `?since_id={last_product_id}` — no Link headers |
| `data-tcgid` in collection products | ✅ confirmed |
| Condition variants on singles | ✅ `Near Mint`, `Lightly Played`, `Moderately Played` |
| Collection discovery endpoint | `/sitemap.xml` → `/sitemap_collections_1.xml` |
| Total collections on store | 447 |
| MTG-relevant collections | ~57 pure MTG + ~30 per-set (e.g. `bloomburrow-singles`) |
| Dedicated MTG singles collection | `magic-the-gathering-singles-in-stock` |
| `custom_collections.json` | Not public (admin API only) |

---

## Solution

Replace the broken `/products.json` fetcher with a two-phase approach:

1. **Explore**: fetch all collection handles from the store sitemap, store them unclassified
2. **Configure**: operator marks the in-stock MTG collections `game_code = 'mtg'` (one-time per store)
3. **Produce**: subsequent runs only fetch products from `game_code = 'mtg'` collections

**Dual coverage:** mark both the in-stock aggregator collection (`magic-the-gathering-singles-in-stock`) AND per-set collections (`bloomburrow-singles`, `foundations-singles`, etc.) as `game_code = 'mtg'`. The in-stock collection provides confirmed-available prices; the per-set collections fill any curation gaps. Duplicate products are resolved with explicit priority logic — see **Deduplication Resolution** below.

**Abstract and reusable:** the pipeline is entirely driven by `market_ref.api_url` + `collection_handles.game_code`. Adding a new Shopify store requires no code changes — only a new `market_ref` row with the store's URL, one `fetch_collections` run to discover its collections, and a SQL update to mark the right ones. All logic lives in the shared pipeline.

---

## Pipeline Shape

```
start_run
  → fetch_collections          ← NEW: discover all collections via sitemap
  → fetch_all_markets          ← MODIFIED: iterate per MTG collection with since_id
  → process_to_parquet         ← unchanged
  → stage_raw                  ← unchanged
  → promote_observations       ← unchanged
  → finish_run
```

---

## Parallelism

**Within a market** — `asyncio.gather` + semaphore inside `fetch_all_markets`.
Each collection handle is fetched concurrently on the same worker's event loop.

**Critical client-lifecycle constraint:** `ShopifyAPIRepository` uses `async with self:` to manage its HTTP client. With a semaphore-gated gather, N coroutines share one repository instance — the first to exit `async with self:` calls `aclose()` on the shared client. Fix: open the HTTP client once around the entire gather, and have per-collection iterators reuse the already-open client without entering/exiting the context manager.

```python
async with shopify_api_repository:            # open client ONCE
    sem = asyncio.Semaphore(5)

    async def fetch_one(handle):
        async with sem:
            page = 0
            since_id = 0
            while True:
                products = await shopify_api_repository.get_collection_products_page(
                    api_url, handle, since_id=since_id, limit=250
                )
                if not products:
                    break
                await storage_service.save_json(
                    f"{source_id}_fetch/{handle}_page_{page}_products.json",
                    {"items": products},
                )
                since_id = products[-1]["id"]
                page += 1

    await asyncio.gather(*[fetch_one(h) for h in mtg_handles])
```

**Across markets** — Celery `group` dispatches one sub-task per market so multiple stores fetch simultaneously on separate workers.

---

## Database Changes

### migration_61_collection_game_code.sql

Two changes in one migration:

```sql
-- 1. Fix incorrect store URL from migration_48
UPDATE markets.market_ref
SET api_url = 'https://tcg.goodgames.com.au'
WHERE name = 'Good Games Brisbane';

-- 2. Add game classification column to collection handles
ALTER TABLE markets.collection_handles
    ADD COLUMN IF NOT EXISTS game_code VARCHAR;
```

`game_code` values:
- `NULL` — unclassified (all collections start here after first `fetch_collections` run)
- `'mtg'` — active MTG collections, products fetched every run
- `'pokemon'`, `'lorcana'`, etc. — stored but ignored by the pipeline

### Exploration workflow (after first `fetch_collections` run)

```sql
-- Inspect what collections the store has
SELECT name, game_code
FROM markets.collection_handles
WHERE market_id = <gg_brisbane_market_id>
ORDER BY name;

-- Mark both the in-stock aggregator AND per-set singles collections
-- In-stock aggregator: confirmed-available prices
UPDATE markets.collection_handles
SET game_code = 'mtg'
WHERE market_id = <gg_brisbane_market_id>
  AND name = 'magic-the-gathering-singles-in-stock';

-- Per-set singles: fill curation gaps (identified after inspecting sitemap results)
UPDATE markets.collection_handles
SET game_code = 'mtg'
WHERE market_id = <gg_brisbane_market_id>
  AND name ILIKE ANY(ARRAY['%-singles', '%-mtg-singles', 'mtg-singles-%', 'commander-staples'])
  AND name NOT ILIKE ANY(ARRAY['%-sealed%', '%-booster%', '%-pack%', 'pokemon%', 'lorcana%',
                                'flesh-and-blood%', 'one-piece%', 'digimon%']);

-- For future stores: same pattern — inspect handles after fetch_collections,
-- mark in-stock aggregator + per-set singles, skip sealed/non-MTG.
```

---

## Code Changes

### 1. `ShopifyAPIRepository` — replace `iter_products_pages`, add collection methods

**Remove Link-header logic** from `iter_products_pages` — it never fires on the public storefront and silently stops after one page.

**Add `get_collection_products_page(api_url, handle, since_id, limit=250) -> list[dict]`**
Single page fetch: `GET {api_url}/collections/{handle}/products.json?limit=250&since_id={since_id}`.
Returns the products list (empty list signals end of pagination).
Does NOT use `async with self:` — the caller holds the client open across the full gather.

**Add `get_sitemap_collection_handles(api_url) -> list[str]`**
1. `GET {api_url}/sitemap.xml` → parse XML to find `sitemap_collections_*.xml` links
2. `GET` each sitemap XML → extract collection handles via regex
3. Returns deduplicated list of handles

### 2. `ShopifyPipelineRepository` — one new query method

**`get_mtg_collection_handles(market_id) -> list[str]`**
```sql
SELECT name
FROM markets.collection_handles
WHERE market_id = $1 AND game_code = 'mtg'
```

### 3. `ShopifyCollectionRepository` — preserve existing `add_many`

`add_many` already uses `ON CONFLICT (name, market_id) DO NOTHING` — this is the **correct** behaviour. Re-running `fetch_collections` every Sunday preserves the operator's `game_code` marks because `DO NOTHING` skips rows that already exist. Do NOT introduce a new `upsert_many` that touches existing rows.

### 4. `pipeline_service.py` — add `fetch_collections` service

```python
@ServiceRegistry.register(
    path="shopify.pipeline.fetch_collections",
    db_repositories=["shopify_pipeline", "collection", "ops"],
    api_repositories=["shopify_api"],
    runs_in_transaction=False,
    command_timeout=3600,
)
async def fetch_collections(
    shopify_pipeline_repository: ShopifyPipelineRepository,
    collection_repository: ShopifyCollectionRepository,
    ops_repository: OpsRepository,
    shopify_api_repository: ShopifyAPIRepository,
    ingestion_run_id: int = None,
) -> dict:
```

For each active market:
1. `track_step(ops_repository, ingestion_run_id, f"fetch_collections_{market_id}")`
2. Call `shopify_api_repository.get_sitemap_collection_handles(api_url)`
3. `collection_repository.add_many(rows)` — DO NOTHING preserves existing `game_code`
4. Log count of new vs existing handles

Returns `{"collections_synced": int}`. Downstream steps read from DB directly.

### 5. `pipeline_service.py` — modify `fetch_all_markets`

1. For each active market, call `get_mtg_collection_handles(market_id)`
2. If empty → `logger.warning(...)`, skip market (exploration mode — not an error)
3. If found → open HTTP client once, then `asyncio.gather` with `Semaphore(5)` across all handles
4. Each handle fetches all pages via `since_id` loop, saves JSON to `{source_id}_fetch/{handle}_page_{n}_products.json`

Storage path change: downstream `process_to_parquet` globs `f"{market_id}_*/**/*products.json"` — this still matches.

When saving each JSON page, embed the collection handle in the payload:
```python
await storage_service.save_json(
    f"{source_id}_fetch/{handle}_page_{page}_products.json",
    {"items": products, "_collection_handle": handle},   # ← NEW
)
```
This lets the parquet step know the source collection of each product row.

### 6. `pipelines.py` — wire `fetch_collections` into the chain

```python
wf = chain(
    run_service.s("ops.pipeline_services.start_run", pipeline_name="shopify_weekly", ...),
    run_service.s("shopify.pipeline.fetch_collections"),   # ← new
    run_service.s("shopify.pipeline.fetch_all_markets"),   # ← modified
    run_service.s("shopify.pipeline.process_to_parquet"),
    run_service.s("shopify.pipeline.stage_raw"),
    run_service.s("shopify.pipeline.promote_observations"),
    run_service.s("ops.pipeline_services.finish_run", status="success"),
)
```

---

## Deduplication Resolution

When the same card appears in both the in-stock aggregator and a per-set collection, the two rows have identical `(product_id, date, variation)` but may have different prices. Resolution rule: **in-stock collection wins**.

### How it works

**Step 1 — tag rows in `process_to_parquet`**

When processing each JSON file, read `_collection_handle` from the file metadata. Derive a `collection_tier` column:
- `1` — handle contains `in-stock` or `instock` (in-stock aggregator)
- `0` — all other collections (per-set)

```python
handle = file_metadata.get("_collection_handle", "")
df_item["collection_tier"] = 1 if "in-stock" in handle or "instock" in handle else 0
```

**Step 2 — priority-based dedup in `_dedupe_batch`**

Replace the existing sort-and-keep-last with:

```python
def _dedupe_batch(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    return (
        df.sort_values(["product_id", "date", "variation", "collection_tier"])
        .drop_duplicates(["product_id", "date", "variation"], keep="last")  # last = highest tier
        .drop(columns=["collection_tier"])
    )
```

`collection_tier` is sorted ascending, so `tier=1` (in-stock) rows end up last and are kept. `tier=0` rows are dropped for any product that also appears in the in-stock collection. When both are the same tier (e.g. two per-set collections), the higher price is not specifically preferred — last-by-scraped_at wins, which is fine since both represent valid listed prices.

**Step 3 — `collection_tier` stays in parquet only**

The `collection_tier` column is dropped before staging into `pricing.shopify_staging_raw`. The staging table schema does not change.

---

## Price Flow into `pricing.price_observation`

The existing `promote_observations` step already implements the full `source_product` chain:

```
staging_raw.tcg_id
  → card_catalog.card_external_identifier   (tcg_id → card_version_id)
  → pricing.mtg_card_products               (card_version_id → product_id)
  → pricing.source_product                  (product_id + source_id → source_product_id)
  → pricing.price_observation               (source_product_id + condition + finish + price)
```

`bootstrap_source_products` creates the `product_ref`, `mtg_card_products`, and `source_product` rows on first encounter — subsequent runs find them already present. `bulk_copy_observations` uses `ON CONFLICT DO NOTHING` so re-running on the same date is safe.

The `source_id` used is `pricing.price_source.source_id` for `code = 'gg_brisbane'` (registered in migration_46). This is already wired — no additional changes needed.

---

## First Run Behaviour

| Step | What happens |
|------|-------------|
| `fetch_collections` | Fetches sitemap, populates `markets.collection_handles` with all 447 handles, `game_code = NULL` |
| `fetch_all_markets` | Finds no `game_code = 'mtg'` handles → logs warning per market → skips product fetch |
| Downstream steps | Run with empty input → no rows inserted (idempotent) |

Operator then runs the SQL classification update. Next run fetches the full MTG singles catalog.

---

## Coverage Sanity Check

After first classified run, verify product coverage:

```sql
-- Count distinct products promoted from this source
SELECT COUNT(DISTINCT sp.source_product_id)
FROM pricing.price_observation po
JOIN pricing.source_product sp ON sp.source_product_id = po.source_product_id
JOIN pricing.price_source ps ON ps.source_id = sp.source_id
WHERE ps.code = 'gg_brisbane';
```

Compare against total product count from `magic-the-gathering-singles-in-stock`. A large gap indicates a collection was missed or products lack `data-tcgid`.

---

## What Is Not Changing

- `process_to_parquet`, `stage_raw`, `promote_observations` — unchanged
- Beat schedule (`shopify-ingest-weekly`) — unchanged
- All existing DB migrations (46, 48) — unchanged except URL fix in migration_61
- No new API endpoints
