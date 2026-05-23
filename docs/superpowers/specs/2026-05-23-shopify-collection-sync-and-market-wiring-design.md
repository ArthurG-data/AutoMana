# Shopify Collection Sync + Market Wiring

**Date:** 2026-05-23
**Status:** Approved
**Extends:** `2026-05-22-shopify-multi-store-pipeline-design.md`

## Goal

Wire GG Sydney and GG Brisbane into the pipeline so it actually runs, add an efficient
collection-sync step (2 REST calls per market), and fix three correctness bugs that would
have caused the pipeline to silently fail on first run.

---

## Prerequisites from Yesterday's Spec

The base pipeline (fetch → parquet → stage → promote) is assumed to be in place per
`2026-05-22-shopify-multi-store-pipeline-design.md`. This spec adds to it.

---

## DB Wiring

`migration_46_shopify_market_pipeline.sql` already added the `source_id` column and
inserted both `gg_brisbane` (source_id=1727) and `gg_sydney` (source_id=1728) into
`pricing.price_source`. However the UPDATEs in that migration did not fire because the
`market_ref` rows were created after the migration ran. A new migration completes the job.

### migration_48_wire_gg_markets.sql

```sql
BEGIN;

-- Wire GG Sydney (market already exists, source row already exists)
UPDATE markets.market_ref
SET source_id = (SELECT source_id FROM pricing.price_source WHERE code = 'gg_sydney')
WHERE name = 'Good Games Sydney'
  AND source_id IS NULL;

-- Add GG Brisbane market_ref row (source row already exists)
INSERT INTO markets.market_ref (name, city, country_code, api_url, source_id)
SELECT 'Good Games Brisbane', 'Brisbane', 'AUD',
       'https://gg-brisbane.myshopify.com',
       source_id
FROM pricing.price_source
WHERE code = 'gg_brisbane'
ON CONFLICT (name) DO NOTHING;

COMMIT;
```

`get_active_pipeline_markets()` filters `WHERE api_url IS NOT NULL AND source_id IS NOT NULL`,
so both stores become active after this migration.

---

## Bug Fixes

Three bugs would cause silent failures on first run:

| # | File | Bug | Fix |
|---|------|-----|-----|
| 1 | `market_repository.py` `get_market_code` | Queries `price_source` without schema prefix | Change to `pricing.price_source` |
| 2 | `product_repository.py` `bulk_copy_prices` | Copies to `"shopify_staging_raw"` without schema | Change to `"pricing.shopify_staging_raw"` |
| 3 | `product_repository.py` `bulk_copy_prices` | Manual `COMMIT` on asyncpg connection | Remove the `execute('COMMIT;')` call |

No behaviour change intended — these are correctness fixes.

---

## Collection Sync Step

### Rationale

Shopify's REST API exposes two collection endpoints:
- `GET /custom_collections.json?limit=250`
- `GET /smart_collections.json?limit=250`

Both paginate via `Link: <next_url>; rel="next"` header (same pattern as `/products.json`).
A store with 500 collections takes 4 API calls total. This is the minimum possible — any
per-product approach would cost thousands of calls.

### New API method — `ShopifyAPIRepository`

```python
async def iter_collection_pages(
    self, api_url: str, endpoint: str  # "custom_collections" or "smart_collections"
) -> AsyncIterator[list[dict]]:
    """Paginate a Shopify collection endpoint, yielding one page at a time."""
```

Shares the Link-header pagination logic already used in `iter_products_pages`.

### New DB method — `ShopifyCollectionRepository`

```python
async def upsert_many(self, rows: list[dict]) -> None:
    """
    Upsert collection handles for a market.
    rows: [{"market_id": int, "name": str}, ...]
    ON CONFLICT (market_id, name) DO UPDATE SET updated_at = NOW()
    """
```

Single `executemany` — one DB round-trip for the full collection list.

### New pipeline service — `shopify.pipeline.fetch_collections`

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
2. Fetch `/custom_collections.json` pages, accumulate handles
3. Fetch `/smart_collections.json` pages, accumulate handles
4. Deduplicate by handle name (smart and custom can overlap)
5. `collection_repository.upsert_many([{"market_id": market_id, "name": handle}, ...])`
6. Log count

Returns `{"collections_synced": int}`. The context key does not collide with downstream
step parameters so it passes through `run_service` harmlessly.

### Error handling

| Scenario | Behaviour |
|----------|-----------|
| HTTP error on one collection endpoint | Log warning, continue to the other endpoint |
| Market has zero collections | Log info, skip upsert — not an error |
| DB upsert fails | Bubble through `track_step` → step marked `failed`, pipeline halts for that market |
| One market fails | Other markets continue — isolated by per-market `track_step` |

---

## Updated Pipeline Step Order

```python
chain(
    run_service.s("shopify.pipeline.fetch_collections"),   # step 0 — NEW
    run_service.s("shopify.pipeline.fetch_all_markets"),   # step 1
    run_service.s("shopify.pipeline.process_to_parquet"),  # step 2
    run_service.s("shopify.pipeline.stage_raw"),           # step 3
    run_service.s("shopify.pipeline.promote_observations"),# step 4
)
```

---

## Success Criteria (GG Sydney first run)

| Check | Query |
|-------|-------|
| Pipeline created | `SELECT status, created_at FROM ops.ingestion_runs WHERE pipeline_name = 'shopify_weekly' ORDER BY created_at DESC LIMIT 1` |
| Collections synced | `SELECT COUNT(*) FROM markets.collection_handles WHERE market_id = 2` → > 0 |
| Products fetched | Storage JSON files exist under `1728_fetch/` |
| Staging populated | `SELECT COUNT(*) FROM pricing.shopify_staging_raw` → > 0 during stage_raw |
| Observations promoted | `SELECT COUNT(*) FROM pricing.price_observation po JOIN pricing.source_product sp ON sp.source_product_id = po.source_product_id WHERE sp.source_id = 1728` → > 0 |
| No failed steps | `SELECT step_name, status FROM ops.ingestion_run_steps WHERE ingestion_run_id = <id>` → all `success` |

---

## Out of Scope

- Collection-to-product linking (the `markets.handles_theme` join table) — populated manually via existing API endpoints
- GG Brisbane live test — follows after GG Sydney green
- Caching/skipping collection re-fetch (can be added later as Option C optimisation)
