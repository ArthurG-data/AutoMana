# Shopify Storefront Price Ingestion Pipeline

## Overview

The Shopify ingestion pipeline is a weekly ETL process that fetches public product listings from registered Shopify storefronts (LGS shops), converts them to parquet, stages the data, and promotes prices into `pricing.price_observation` — the same table used by TCGPlayer, MTGStock, and eBay. Prices appear automatically in the existing frontend price chart with no new UI required.

The pipeline is **idempotent**: the promote step uses `ON CONFLICT DO NOTHING`, so re-running for the same `ts_date` is safe.

The pipeline has **four logical stages**:

| Stage | Responsibility |
|---|---|
| **Stage 1 – Fetch** | Paginate `/products.json` from each active storefront; save raw JSON pages to disk |
| **Stage 2 – Process** | Convert JSON pages to per-product parquet files; upsert product handles |
| **Stage 3 – Stage** | COPY parquet rows into `pricing.shopify_staging_raw`; stamp `source_id` on each row |
| **Stage 4 – Promote** | Resolve `tcg_id → card_version_id → source_product_id`; COPY into `pricing.price_observation`; truncate staging |

The Celery task `shopify_weekly_pipeline` in `worker/tasks/pipelines.py` runs this chain every **Sunday at 06:00 AEST** via the Beat scheduler:

| Step | Service key | What it does |
|------|-------------|--------------|
| 1 | `ops.pipeline_services.start_run` | Creates an `ops.ingestion_runs` record; returns `ingestion_run_id` |
| 2 | `shopify.pipeline.fetch_all_markets` | GETs `/products.json?limit=250` from each active market; follows `Link: <next>` pagination; saves `page_N_products.json` to disk |
| 3 | `shopify.pipeline.process_to_parquet` | Calls `process_json_dir_to_parquet`; upserts product handle + title into `markets.product_ref` |
| 4 | `shopify.pipeline.stage_raw` | Calls `stage_data_from_parquet` to COPY parquet into staging; then UPDATEs `source_id` on staged rows via `markets.product_ref` join |
| 5 | `shopify.pipeline.promote_observations` | Resolves tcg_ids, bootstraps `source_product`, builds DataFrame, inserts into `pricing.price_observation` ON CONFLICT DO NOTHING, truncates staging |
| 6 | `ops.pipeline_services.finish_run` | Marks the run as `success` |

---

## Registered services

| Service key | File | Purpose |
|---|---|---|
| `shopify.pipeline.fetch_all_markets` | `pipeline_service.py` | Fetch + paginate all active storefronts |
| `shopify.pipeline.process_to_parquet` | `pipeline_service.py` | JSON → parquet conversion |
| `shopify.pipeline.stage_raw` | `pipeline_service.py` | Parquet → staging table |
| `shopify.pipeline.promote_observations` | `pipeline_service.py` | Staging → price_observation |

---

## Data model

### Active storefronts — `markets.market_ref`

Each row represents one Shopify store. Two columns added by migration 46 wire it into the pipeline:

| Column | Type | Purpose |
|--------|------|---------|
| `api_url` | TEXT | Base URL of the Shopify store (e.g. `https://store.goodgames.com.au`) |
| `source_id` | SMALLINT FK | References `pricing.price_source` — the canonical price source for this store |

A market is only included in the pipeline run if **both** `api_url` and `source_id` are non-NULL.

### Product handles — `markets.product_ref`

| Column | Type | Purpose |
|--------|------|---------|
| `product_shop_id` | VARCHAR(64) PK | Shopify product ID (string) |
| `handle` | TEXT | Shopify URL handle — used to build buy-link URLs |
| `title` | TEXT | Product title from Shopify |
| `market_id` | INT FK | Parent storefront |

### Staging — `pricing.shopify_staging_raw`

Raw rows written by `stage_data_from_parquet`. One row per product variant per scrape date. The pipeline adds `source_id` after staging via a JOIN to `markets.product_ref`.

| Column | Purpose |
|--------|---------|
| `product_id` | Shopify product ID |
| `date` | Listing date |
| `variation` | Variant title (e.g. `"Near Mint Foil"`) |
| `price` | Listed price in the store's local currency |
| `tcg_id` | TCGPlayer ID — used to link back to `card_catalog` |
| `source_id` | FK to `pricing.price_source` (stamped by the stage step) |

### Price observation — `pricing.price_observation`

The canonical destination, shared with all other price sources. The Shopify pipeline writes:

| Field | Value |
|-------|-------|
| `price_type_id` | `sell` transaction type |
| `list_avg_cents` | Shopify listed price converted to cents |
| `list_low_cents` | NULL (not available from Shopify) |
| `condition_id` | Resolved from variant title (NM / LP / MP / HP / DMG) |
| `finish_id` | `foil` or `nonfoil`, resolved from variant title |
| `data_provider_id` | `shopify` data provider |

---

## Variant title → condition/finish mapping

The `_map_variation(variation: str)` function in `pipeline_repository.py` parses Shopify variant titles:

| Variant title | `condition_id` | `finish_id` |
|---|---|---|
| `Near Mint` | NM | nonfoil |
| `Near Mint Foil` | NM | foil |
| `Lightly Played` | LP | nonfoil |
| `Slightly Played` | LP | nonfoil |
| `Moderately Played` | MP | nonfoil |
| `Heavily Played` | HP | nonfoil |
| `Damaged` | DMG | nonfoil |
| Any Foil suffix | + foil finish | — |
| Unknown | NM (default) | nonfoil |

The rule is: strip a trailing ` Foil` suffix → that sets `finish = foil`; the remainder maps to a condition code. Anything unrecognised defaults to NM/nonfoil.

---

## Card linkage

The pipeline resolves Shopify products to card versions via the TCGPlayer ID embedded in each product's HTML body:

```
Shopify product
  └─ tcg_id (from body_html)
       └─ card_catalog.card_external_identifier (identifier_name = 'tcgplayer_id')
            └─ card_version_id
                 └─ pricing.mtg_card_products
                      └─ pricing.product_ref
                           └─ pricing.source_product (source_id = this store)
                                └─ pricing.price_observation
```

The `bootstrap_source_products` method in `ShopifyPipelineRepository` ensures the `product_ref → mtg_card_products → source_product` chain exists for every new card version using the canonical CTE pattern (same as `06_prices.sql`).

---

## On-disk directory layout

```
{SHOPIFY_DATA_ROOT}/
  {source_id}_fetch/          ← raw JSON pages from fetch step
    page_0_products.json
    page_1_products.json
    ...
  parquet/
    {market_id}/              ← parquet output per market
      {product_id}/
        data.parquet
        info.json             ← product metadata (title, handle, tcg_id, ...)
```

`SHOPIFY_DATA_ROOT` defaults to `/data/automana_data/shopify`. Override via the `SHOPIFY_DATA_ROOT` environment variable.

The `{source_id}_fetch` directory name matches the glob pattern `{source_id}_*/**/*products.json` used by `process_json_dir_to_parquet` — the variable is named `market_id` inside that function but holds the `price_source.source_id` value returned by `get_market_code`.

---

## Adding a new storefront

1. **Insert a `pricing.price_source` row:**
   ```sql
   INSERT INTO pricing.price_source (code, name, currency_code)
   VALUES ('store_code', 'Store Display Name', 'AUD');
   ```

2. **Insert a `markets.market_ref` row and wire the source:**
   ```sql
   INSERT INTO markets.market_ref (name, api_url, country_code, city, source_id)
   SELECT 'Store Name', 'https://store.example.com', 'AU', 'Melbourne', source_id
   FROM pricing.price_source WHERE code = 'store_code';
   ```

3. **That's it.** The pipeline reads all active markets at runtime — no code change required.

For non-AUD stores, the `country_code` should reflect the store's currency region. FX conversion is not yet implemented in the Shopify pipeline — prices are stored as-is in cents of the local currency (see [Technical Debt](#known-limitations--technical-debt)).

---

## Idempotency and re-run safety

- **Fetch step**: Overwrites page files on re-run. Safe — raw JSON is stateless.
- **Process step**: `process_json_dir_to_parquet` appends and de-dupes within a run. Re-running produces the same parquet output.
- **Stage step**: `staging.shopify_staging_raw` is truncated at the end of a successful promote step. A mid-run failure leaves staging intact for retry.
- **Promote step**: `INSERT ... ON CONFLICT DO NOTHING` — re-inserting the same `(ts_date, source_product_id, …)` combination is a no-op. Safe to re-run.

---

## Configuration

| Env var | Default | Purpose |
|---------|---------|---------|
| `SHOPIFY_DATA_ROOT` | `/data/automana_data/shopify` | Root directory for raw JSON pages and parquet output |

The Celery beat schedule is in `src/automana/worker/celeryconfig.py` under the key `shopify-ingest-weekly`. The task name is `automana.worker.tasks.pipelines.shopify_weekly_pipeline`.

---

## Relevant files

| File | Purpose |
|------|---------|
| `src/automana/worker/tasks/pipelines.py` | Celery task + chain definition |
| `src/automana/worker/celeryconfig.py` | Beat schedule entry |
| `src/automana/core/services/app_integration/shopify/pipeline_service.py` | 4 registered pipeline steps |
| `src/automana/core/repositories/app_integration/shopify/pipeline_repository.py` | All DB operations for the pipeline |
| `src/automana/core/services/app_integration/shopify/data_staging_service.py` | `process_json_dir_to_parquet` + `stage_data_from_parquet` (shared with the file-based ingestion endpoint) |
| `src/automana/core/repositories/app_integration/shopify/market_queries.py` | SQL for market lookups |
| `src/automana/database/SQL/migrations/migration_46_shopify_market_pipeline.sql` | Schema additions + seed data |
| `src/automana/database/SQL/schemas/07_shopify_staging.sql` | Staging table + no-op `stage_to_price_observation` procedure |
| `tests/unit/core/test_shopify_pipeline.py` | Unit tests for `_map_variation`, `_price_to_cents`, `_build_obs_dataframe` |

---

## Known limitations / technical debt

See [`PIPELINE_TECHNICAL_DEBT.md`](PIPELINE_TECHNICAL_DEBT.md) for tracked items. Key open items:

- **No HTTP retry/backoff in `_fetch_all_pages`**: A single 429 or 5xx mid-pagination aborts the entire store fetch. The project retry policy operates at whole-step granularity (re-fetches all stores from page 0). A per-request backoff with `Retry-After` header support would make this robust under Shopify rate limits.
- **FX conversion not implemented**: Prices are stored in the store's local currency (AUD, CAD, etc.) without conversion to USD. The existing `fetch_fx_rate` utility exists but is not yet wired into the Shopify promote step.
- **Dead SQL in `07_shopify_staging.sql`**: `pricing.raw_to_stage()` hardcodes `source_code = 'gg_brisbane'` and is not called by the pipeline. The promotion is handled in Python by `promote_observations`.
- **`info.json` is write-once**: Parquet directories created before migration 46 (when `handle` was added) will have `info.json` files without a `handle` key. Re-running the pipeline on existing directories will not regenerate `info.json`. To backfill handles, delete `{SHOPIFY_DATA_ROOT}/parquet/*/*/info.json` and re-run the process step.
