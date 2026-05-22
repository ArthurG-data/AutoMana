# Shopify Multi-Store Price Ingestion Pipeline

**Date:** 2026-05-22  
**Status:** Approved

## Goal

Fix and extend the existing Shopify price ingestion so that weekly price snapshots from multiple LGS Shopify storefronts (starting with Australian stores, extending to Face2Face and others) flow into `pricing.price_observation` — the same table used by TCGPlayer, Cardmarket, and MTGStock. The existing frontend price chart and source comparison UI then picks up store prices automatically with no new UI work.

---

## What Already Exists

| Component | Location | Status |
|-----------|----------|--------|
| Store registry | `markets.market_ref` (market_id, name, api_url, country_code) | Working |
| Product registry | `markets.product_ref` (product_shop_id, product_id, market_id) | Working, needs `handle` + `title` columns |
| Raw staging table | `pricing.shopify_staging_raw` | Working |
| JSON→parquet ETL | `core/services/app_integration/shopify/data_staging_service.py` | Working, used as-is |
| `raw_to_stage()` SQL | `07_shopify_staging.sql` | Working |
| `stage_to_price_observation()` SQL | `07_shopify_staging.sql` | **Broken** — explicit RAISE EXCEPTION |
| Shop metadata CRUD | `/api/integrations/shopify/shop-meta/` | Working |
| Data loading endpoints | `/api/integrations/shopify/data_loading/` | Working (file-based, admin only) |
| `markets.card_products_ref` | `08_markets_prices.sql` | Not used in new flow |

---

## What We Are Building

A proper Celery pipeline that:

1. **Fetches** `/products.json` from each registered Shopify storefront (weekly, Sunday)
2. **Processes** JSON to per-product parquet files (reusing existing logic)
3. **Stages** parquet data into `pricing.shopify_staging_raw` via COPY
4. **Promotes** staged data into `pricing.price_observation` (fixing the broken SQL procedure)

Each store appears as a `pricing.price_source` row, so existing frontend price charts show Shopify store prices alongside TCGPlayer/Cardmarket/MTGStock automatically.

---

## Architecture

```
Celery beat (weekly, Sunday)
  → shopify_ingest_pipeline task  [worker/tasks/pipelines.py]
      for each active market in markets.market_ref:
          → fetch_storefront      GET {api_url}/products.json (paginated)
          → process_to_parquet    JSON → per-product parquet (existing service)
          → stage_raw             parquet → pricing.shopify_staging_raw (existing COPY)
          → promote_observations  CALL pricing.raw_to_stage(); raw→price_observation
```

Each step is wrapped in `track_step(ops_repository, run_id, "step_name")`. One `ops.ingestion_run` per market per week.

The pipeline is registered via `@ServiceRegistry.register` under `"pipelines.shopify.ingest"` — same pattern as MTGStock and Scryfall.

---

## Database Changes

Four changes, all in a single migration file:

### 1. Link markets to price sources

```sql
ALTER TABLE markets.market_ref
    ADD COLUMN IF NOT EXISTS source_id INT REFERENCES pricing.price_source(source_id);
```

Each store must have a matching `pricing.price_source` row (e.g., code `gg_brisbane`, `gg_sydney`). The pipeline uses this `source_id` when promoting observations.

### 2. Add handle and title to product_ref

```sql
ALTER TABLE markets.product_ref
    ADD COLUMN IF NOT EXISTS handle TEXT,
    ADD COLUMN IF NOT EXISTS title TEXT;
```

`handle` enables constructing buy links as `{api_url}/products/{handle}`. Both columns are populated during the `process_to_parquet` step (already extracted in `info.json`).

### 3. Fix `pricing.stage_to_price_observation()`

Rewrite the procedure in `07_shopify_staging.sql` to correctly map staging columns to the current `pricing.price_observation` schema:

- `staging_raw.product_id` (Shopify numeric ID) → `markets.product_ref` → `pricing.source_product.source_product_id`  
- `staging_raw.variation` → `pricing.card_condition.condition_id` + `card_catalog.card_finished.finish_id`  
- `staging_raw.price` / `price_usd` → `value_cents` columns  
- `source_id` from `markets.market_ref.source_id`

### 4. (Not needed) `markets.card_products_ref`

This table used `tcgplayer_id` as an ad-hoc card link. The new flow uses the canonical `pricing.mtg_card_products → pricing.product_ref → pricing.source_product` chain instead. The table is left in place but not written to by this pipeline.

---

## Data Fetching

- **Endpoint:** `GET {api_url}/products.json?limit=250`
- **Pagination:** Shopify returns a `Link: <next_url>; rel="next"` header. The fetcher follows until no `next` link is present.
- **Currency:** Derived from `markets.market_ref.country_code` (already defaults `'AUD'`). FX conversion uses existing `fetch_fx_rate(from, 'USD', date, app_id)`.
- **International stores:** Face2Face (Canada) and others added by inserting a new `market_ref` row with the correct `country_code` (`'CAD'` etc.). No pipeline code changes needed.

---

## What Is Not Changing

- `markets.product_prices` TimescaleDB hypertable — not written to by this pipeline
- Frontend — no new components or routes; store prices appear in the existing price source UI automatically
- No new API endpoint for store listings — the existing price chart infrastructure handles it

---

## Out of Scope

- Live Shopify Admin API / webhooks
- User-scoped store access (all Shopify ingestion is admin-level, same as MTGStock)
- `stage_to_price_observation` for the eBay scrape path (separate concern)
