# Sealed Product Pricing — Design Spec

**Date:** 2026-05-26
**Status:** Approved
**Approach:** Option A — parallel sealed branch, isolated from existing card pipeline

---

## Overview

Extend AutoMana's pricing infrastructure to track sealed MTG product prices (booster boxes, collector boosters, bundles, commander decks, etc.) sourced from MTGJson's bulk data files. Sealed products plug into the existing T1 (`price_observation`) table, which is already product-agnostic. A new `sealed_price_latest` snapshot provides O(1) current-price queries. Tiers 2 and 3 are deferred — sealed product volume does not justify them at this stage.

The existing card pricing pipeline is **not modified** — sealed pricing is a fully isolated branch that shares only the product-agnostic T1 table.

---

## Data Model

### `pricing.sealed_products`
Subtype of `pricing.product_ref`, parallel to `pricing.mtg_card_products`.

```sql
product_id      UUID        PRIMARY KEY REFERENCES pricing.product_ref(product_id)
set_id          UUID        REFERENCES card_catalog.sets(set_id)  -- nullable
name            TEXT        NOT NULL   -- e.g. "Bloomburrow Collector Booster Box"
product_type    TEXT        NOT NULL   -- see Product Types below
mtgjson_uuid    TEXT        UNIQUE NOT NULL
created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
```

**Product types** (direct from MTGJson `category`/`subtype` fields):
`booster_box`, `collector_booster`, `collector_booster_box`, `draft_booster`,
`set_booster`, `set_booster_box`, `bundle`, `commander_deck`,
`prerelease_pack`, `starter_kit`, `theme_booster`, and any future types
MTGJson introduces — stored as-is, no enum constraint.

### `pricing.sealed_price_latest`
Current-price snapshot keyed on `product_id` (not `card_version_id`).

```sql
product_id          UUID        NOT NULL REFERENCES pricing.product_ref(product_id)
source_id           SMALLINT    NOT NULL REFERENCES pricing.price_source(source_id)
transaction_type_id INTEGER     NOT NULL REFERENCES pricing.transaction_type(transaction_type_id)
price_date          DATE        NOT NULL
list_low_cents      INTEGER
list_avg_cents      INTEGER
sold_avg_cents      INTEGER
n_providers         SMALLINT
updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()

PRIMARY KEY (product_id, source_id, transaction_type_id)
```

### `pricing.mtgjson_sealed_prices_staging`
Landing table for MTGJson sealed prices, parallel to `mtgjson_card_prices_staging`.

```sql
id              SERIAL      PRIMARY KEY
sealed_uuid     TEXT        NOT NULL
price_source    TEXT        NOT NULL
price_type      TEXT                    -- normalized to 'sell'/'buy' before promotion
currency        TEXT        NOT NULL
price_value     FLOAT       NOT NULL
price_date      DATE        NOT NULL
created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
```

### Unchanged tables
`pricing.product_ref`, `pricing.source_product`, `pricing.price_observation` (T1) —
all unchanged. Sealed observations land in T1 via `source_product_id` exactly like card observations.

---

## ETL Pipeline

### Step 0 — Sealed catalog bootstrap
Run once per new set release (or full refresh when MTGJson publishes a new bulk file).

- Source: MTGJson `SealedProduct.json` — one file, all sets, each product has `uuid`, `name`, `setCode`, `category`, `subType`
- Python service `SealedPricingService.bootstrap_sealed_catalog(data)`:
  1. Resolve `setCode → set_id` via `card_catalog.sets`
  2. Upsert `pricing.product_ref` (with `game_id = MTG`)
  3. Upsert `pricing.sealed_products` on conflict on `mtgjson_uuid`
- Called as part of the MTGJson pipeline task, or standalone Celery task for catalog-only refresh

### Step 1 — Staging ingestion
MTGJson's `AllPricings.json` (already downloaded by the existing pipeline) contains sealed product prices under the same JSON schema as card prices, keyed by sealed UUIDs.

**Dependency:** the sealed catalog (Step 0) must be populated before this step runs — `stream_to_staging` identifies sealed UUIDs by matching against the catalog. If the catalog is empty, all sealed UUIDs fall through to card staging and are silently skipped (no data loss — they stay in `mtgjson_card_prices_staging` unresolved and can be re-routed after a catalog bootstrap).

The existing `stream_to_staging` service is extended:
- At startup, load the set of known sealed UUIDs from `pricing.sealed_products.mtgjson_uuid` into memory
- During streaming, if a UUID matches the sealed set → write to `mtgjson_sealed_prices_staging`; otherwise → existing `mtgjson_card_prices_staging` (current behaviour, unchanged)

### Step 2 — Staging promotion
New stored procedure: `pricing.load_price_observation_from_mtgjson_sealed_staging(batch_days INT DEFAULT 30)`

```
1. Normalize price_type: retail/market → 'sell', buylist/directlow → 'buy'
2. Normalize source names: tcgplayer → 'tcg'
3. Batch loop (30-day windows, same pattern as card procedure):
   a. Upsert pricing.price_source rows for any new source codes
   b. Resolve sealed_uuid → product_id via sealed_products.mtgjson_uuid
   c. Upsert pricing.source_product (product_id, source_id) → source_product_id
   d. Upsert into pricing.price_observation (T1) — no schema change
   e. Upsert into pricing.sealed_price_latest (advance only if price_date >= existing)
   f. Delete resolved rows from staging
4. Unresolved rows (sealed_uuid not in catalog): logged as WARNING, left in staging
   for re-run after catalog refresh. No separate reject table — volume is low.
```

### Step 3 — Celery task
New task in `worker/tasks/pipelines.py`:
`run_mtgjson_sealed_pricing_pipeline` — calls catalog bootstrap then promotion procedure.
Follows the existing `run_service` dispatcher pattern with `track_step` for ops tracking.

---

## Service Layer

### `SealedPricingDBRepository(AbstractDBRepository)`
All methods follow CQS naming conventions.

| Method | Type |
|--------|------|
| `get_sealed_products_by_set(set_code)` | query |
| `get_sealed_price_latest(product_id)` | query |
| `get_sealed_prices_by_set(set_code)` | query |
| `get_sealed_price_history(product_id, from_date, to_date)` | query |
| `upsert_sealed_products(products)` | command |

### `SealedPricingService`
Registered via `@ServiceRegistry.register`. Wraps the repository. Handles `set_code → set_id` resolution and formats response data. Exposes `bootstrap_sealed_catalog(mtgjson_data)` for pipeline use.

---

## API Endpoints

Two read-only endpoints added to the pricing router. No write endpoints — ingestion is pipeline-only.

```
GET /api/v1/pricing/sealed/{set_code}
    Returns current sealed prices for all products in a set.
    Response groups by product_type, sorted by name.

GET /api/v1/pricing/sealed/{set_code}/{mtgjson_uuid}/history
    Returns T1 daily price history for one sealed product.
    Query params: from_date, to_date, source (all optional)
```

---

## Files to Create / Modify

| Action | Path |
|--------|------|
| CREATE | `src/automana/database/SQL/migrations/migration_51_sealed_product_pricing.sql` |
| CREATE | `src/automana/database/SQL/schemas/12_sealed_pricing.sql` |
| CREATE | `src/automana/core/repositories/pricing/sealed_pricing_repository.py` |
| CREATE | `src/automana/core/services/pricing/sealed_pricing_service.py` |
| MODIFY | `src/automana/core/services/pipelines/mtgjson/stream_to_staging.py` |
| MODIFY | `src/automana/core/routers/pricing.py` |
| MODIFY | `src/automana/worker/tasks/pipelines.py` |

---

## What's Out of Scope

- T2 (`sealed_price_daily`) and T3 (`sealed_price_weekly`) rollup tables — deferred until volume justifies it
- MTGStocks sealed product prices — deferred, MTGJson covers the data need
- Collection tracking for sealed products (owned sealed inventory)
- Frontend UI for sealed prices

---

## Key Invariants

- The card pricing pipeline (`mtgjson_card_prices_staging`, `load_price_observation_from_mtgjson_staging_batched`) is **not modified**
- All DB access goes through `SealedPricingDBRepository` — no raw queries in service or router
- Sealed UUIDs never overlap with card UUIDs (MTGJson guarantees distinct UUID spaces)
- `sealed_price_latest` is only advanced when `price_date >= existing price_date` (same guard as `print_price_latest`)
