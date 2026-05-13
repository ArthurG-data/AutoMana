# eBay Sold Price Persistence — Design Spec

**Date:** 2026-05-13
**Status:** Approved

## Goal

Persist sold card prices from two eBay channels into `pricing.price_observation` for use as market reference data:

1. **Own sales** — the seller's own completed eBay orders (Fulfillment API)
2. **External scrape** — other sellers' completed listings on eBay (Finding API), scoped to cards the seller has listed

Both channels use the existing pricing chain and promote to `price_observation` via a shared nightly batch job.

---

## Architecture

### Pricing Chain (shared by both channels)

```
card_version_id
  └─► pricing.mtg_card_products   (1:1 with card_version)
        └─► pricing.product_ref
              └─► pricing.source_product  (source_id=5 / ebay)
                    └─► pricing.price_observation
                          ts_date, sold_avg_cents, sold_count
                          data_provider_id=4 (ebay), price_type_id=1 (sell)
```

`ensure_source_product(card_version_id, source_id=5)`:
1. `SELECT product_id FROM pricing.mtg_card_products WHERE card_version_id = $1`
2. `INSERT INTO pricing.source_product (product_id, source_id) ON CONFLICT DO NOTHING`
3. `SELECT source_product_id` if conflict — returns the ID either way

This function is a shared utility used by both channels and lives in `EbaySalesRepository`.

### Channel 1 — Own Sales Flow

```
POST /listing/from-card
  └─► ebay_active_listings (item_id → card_version_id)

[nightly] integrations.ebay.sync_own_sales
  └─► Fulfillment API get_history() (90 days)
  └─► for each order line:
        item_id → ebay_active_listings → card_version_id
        fallback: score_title() + card_repository.suggest() (score ≥ 0.7)
        ensure_source_product(card_version_id, source_id=5)
        upsert → ebay_order_status
        upsert → ebay_order_source_product (promoted_to_obs=false)

[nightly] integrations.ebay.promote_sold_obs
  └─► reads both staging tables → price_observation
```

### Channel 2 — External Scrape Flow

```
[nightly] integrations.ebay.scrape_external_sold
  └─► scope: DISTINCT card_version_id FROM ebay_active_listings
  └─► for each card:
        build_query_string(card_name, set_code, ...)
        Finding API find_completed_items()
        score_title() → keep score ≥ 0.7
        ensure_source_product(card_version_id, source_id=5)
        INSERT INTO pricing.ebay_scraped_sold ON CONFLICT (item_id) DO NOTHING

[nightly] integrations.ebay.promote_sold_obs  (shared with Channel 1)
```

---

## New Tables — migration_31

### `app_integration.ebay_active_listings`

Written when a listing is posted from AutoMana. Read by `sync_own_sales` to resolve `card_version_id` from `item_id`.

```sql
CREATE TABLE app_integration.ebay_active_listings (
    item_id         TEXT         PRIMARY KEY,
    app_code        VARCHAR(50)  NOT NULL
        REFERENCES app_integration.app_info(app_code) ON DELETE CASCADE,
    card_version_id UUID         NOT NULL
        REFERENCES card_catalog.card_version(card_version_id),
    listed_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    ended_at        TIMESTAMPTZ,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX idx_ebay_active_listings_app ON app_integration.ebay_active_listings (app_code);
CREATE INDEX idx_ebay_active_listings_card ON app_integration.ebay_active_listings (card_version_id);
```

### `pricing.ebay_scraped_sold`

Staging table for external Finding API results. One row per scraped sold listing. Deduplicates on `item_id`.

```sql
CREATE TABLE pricing.ebay_scraped_sold (
    scrape_id         BIGSERIAL    PRIMARY KEY,
    item_id           TEXT         NOT NULL UNIQUE,
    title             TEXT         NOT NULL,
    source_product_id BIGINT       REFERENCES pricing.source_product(source_product_id),
    price_cents       INTEGER      NOT NULL CHECK (price_cents >= 0),
    currency          VARCHAR(3)   NOT NULL,
    condition_id      SMALLINT     REFERENCES pricing.card_condition(condition_id),
    finish_id         SMALLINT     NOT NULL DEFAULT pricing.default_finish_id(),
    language_id       SMALLINT     NOT NULL DEFAULT card_catalog.default_language_id(),
    sold_at           TIMESTAMPTZ  NOT NULL,
    scraped_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    promoted_to_obs   BOOLEAN      NOT NULL DEFAULT false
);
CREATE INDEX idx_ebay_scraped_unpromoted ON pricing.ebay_scraped_sold (source_product_id)
    WHERE promoted_to_obs = false AND source_product_id IS NOT NULL;
CREATE INDEX idx_ebay_scraped_sold_at ON pricing.ebay_scraped_sold (sold_at DESC);
```

---

## Services

### `integrations.ebay.sync_own_sales`

- **Trigger:** Nightly Celery beat, 07:00 AEST — dedicated task `ebay_sync_own_sales_task` (not `run_service`), because it must iterate all active app_codes internally
- **Repos:** `auth`, `app`, `ebay_sales` (DB); `selling` (API)
- **Parameters:** `days_back=90` (fixed in beat entry; task iterates all app_codes with valid tokens)
- **Logic:**
  1. Query all active `app_codes` that have a non-expired eBay refresh token
  2. For each `app_code`:
     - Resolve OAuth token via `_auth_context.resolve_token()`
     - Call `selling_repository.get_history()` (Fulfillment API)
     - For each order + line item:
       - Look up `ebay_active_listings` by `item_id` → `card_version_id`
       - If not found: `score_title()` + `card_repository.suggest()`, threshold 0.7
       - If resolved: `ensure_source_product(card_version_id, source_id=5)` → `source_product_id`
       - `upsert_order_status(order_id, app_code, local_status='sold')`
       - `upsert_order_source_product(order_id, app_code, item_id, title, source_product_id, sold_price_cents, ...)`
  3. Unresolved lines (no card match) stored with `source_product_id = NULL` — not promoted until resolved

### `integrations.ebay.scrape_external_sold`

- **Trigger:** Nightly Celery beat, 07:15 AEST — dedicated task `ebay_scrape_external_sold_task`, iterates all active app_codes internally (same pattern as sync)
- **Repos:** `ebay_sales`, `ebay_scrape`, `card` (DB); `ebay_finding` (API)
- **Parameters:** `days_back=30`, `score_threshold=0.7`, `limit_per_card=50` (fixed in beat entry)
- **Logic:**
  1. `SELECT DISTINCT card_version_id FROM app_integration.ebay_active_listings WHERE app_code = $1`
  2. For each `card_version_id`:
     - `card_repository.get(card_version_id)` → `card_name`, `set_code`
     - `build_query_string(card_name, set_code)`
     - `ebay_finding_repository.find_completed_items(keywords, app_id, ...)`
     - For each result: `score_title()` ≥ threshold
     - Resolve `condition_id` from eBay condition string via lookup map
     - `ensure_source_product(card_version_id, source_id=5)`
     - `INSERT INTO pricing.ebay_scraped_sold ON CONFLICT (item_id) DO NOTHING`
  3. Rate-limit: 1 card per 0.5s to avoid Finding API throttling

### `integrations.ebay.promote_sold_obs`

- **Trigger:** Nightly Celery beat, 08:00 AEST (after both sync and scrape)
- **Repos:** `ebay_sales`, `ebay_scrape`, `pricing` (DB)
- **Logic:**
  1. **Channel 1:** `SELECT` from `ebay_order_source_product` WHERE `promoted_to_obs = false AND source_product_id IS NOT NULL`
     - `GROUP BY (source_product_id, DATE(sold_at), finish_id, condition_id, language_id)`
     - Upsert into `price_observation` (`sold_avg_cents`, `sold_count`, `data_provider_id=4`, `price_type_id=1`)
     - `UPDATE ebay_order_source_product SET promoted_to_obs = true`
  2. **Channel 2:** Same pattern from `pricing.ebay_scraped_sold`
  3. Runs in a single transaction per batch of 1000 rows

---

## Router Change

`POST /listing/from-card` in `ebay_selling.py`:
- `card_version_id` is already in the request body; `item_id` is returned in the eBay API response
- After a successful eBay response, write `(item_id, app_code, card_version_id, listed_at=now())` to `ebay_active_listings`
- If the write fails, log a warning but do not fail the request — the listing was created on eBay; the tracking write is best-effort

---

## New Repositories

### `EbaySalesRepository` (`sales_repository.py`)

Methods:
- `upsert_order_source_product(...)` — INSERT ON CONFLICT UPDATE (update sold_price_cents, updated_at)
- `get_unresolved_items(app_code)` — WHERE `source_product_id IS NULL`
- `get_unpromoted(app_code)` — WHERE `promoted_to_obs = false AND source_product_id IS NOT NULL`
- `mark_promoted(ebay_osp_ids: list[int])` — bulk UPDATE `promoted_to_obs = true`
- `upsert_active_listing(item_id, app_code, card_version_id, listed_at)` — ON CONFLICT UPDATE `ended_at`
- `get_card_version_by_item(item_id)` → `card_version_id | None`
- `get_listed_card_versions(app_code)` → list of `card_version_id` for scrape scope
- `ensure_source_product(card_version_id, source_id)` → `source_product_id`

### `EbayScrapeSoldRepository` (`ebay_scrape_repository.py`)

Methods:
- `insert_scraped_sold(item_id, title, source_product_id, price_cents, ...)` — ON CONFLICT DO NOTHING
- `get_unpromoted()` — WHERE `promoted_to_obs = false AND source_product_id IS NOT NULL`
- `mark_promoted(scrape_ids: list[int])` — bulk UPDATE

---

## Celery Beat Schedule (celeryconfig.py additions)

Sync and scrape use dedicated task functions (not `run_service`) because they iterate all active app_codes internally. Promote uses `run_service` since it takes no per-user params.

```python
"ebay-sync-own-sales-nightly": {
    "task": "automana.worker.tasks.ebay.ebay_sync_own_sales_task",
    "schedule": crontab(hour=7, minute=0),   # 07:00 AEST
},
"ebay-scrape-external-sold-nightly": {
    "task": "automana.worker.tasks.ebay.ebay_scrape_external_sold_task",
    "schedule": crontab(hour=7, minute=15),  # 07:15 AEST
},
"ebay-promote-sold-obs-nightly": {
    "task": "run_service",
    "schedule": crontab(hour=8, minute=0),   # 08:00 AEST — after both above
    "kwargs": {"path": "integrations.ebay.promote_sold_obs"},
},
```

---

## Error Handling

- **Fulfillment API failure:** Log + skip, do not fail the entire beat run. Retry next night.
- **Finding API throttle:** Catch 429, log, stop scraping for that run. Already-inserted rows are safe.
- **Title resolution failure (score < 0.7):** Store row with `source_product_id = NULL`. These accumulate until manually resolved or a future re-resolution pass handles them.
- **`ensure_source_product` failure:** Raise — this is a hard dependency. The caller catches and logs.
- **Promotion failure:** Wrap each batch in a transaction. On rollback, the `promoted_to_obs` flags remain false — the next night's run will retry the same rows.

---

## Migration File

`src/automana/database/SQL/migrations/migration_31_ebay_listings_scrape.sql`

Grants:
- `ebay_active_listings`: SELECT, INSERT, UPDATE to `app_backend`, `app_celery`
- `ebay_scraped_sold`: SELECT, INSERT, UPDATE to `app_backend`, `app_celery`

---

## Out of Scope

- Re-resolution pass for `source_product_id = NULL` rows (future work)
- Multi-user beat scheduling (the beat runs per `app_code`; user iteration is inside the service, not a separate beat entry per user)
- Currency normalisation (USD assumed; AUD → USD conversion is future work)
