# MTGStocks Ingestion Pipeline

## Overview

The MTGStocks pipeline ingests Magic: The Gathering price data scraped from MTGStocks and lands it in the `pricing` schema. Unlike the MTGJson and Scryfall feeds, MTGStocks uses a proprietary `print_id` identifier that must first be resolved to the local `card_version_id` before prices can be joined to the rest of the catalogue.

The pipeline is structured in **four stages**, each backed by a dedicated table or stored routine:

| Stage | Input | Routine | Output |
|---|---|---|---|
| 1. Raw landing | Scraper output | Bulk insert | `pricing.raw_mtg_stock_price` |
| 2. Resolve + stage | `raw_mtg_stock_price` | `pricing.load_staging_prices_batched` | `pricing.stg_price_observation` + `pricing.stg_price_observation_reject` |
| 3. Load fact | `stg_price_observation` | `pricing.load_prices_from_staged_batched` | `pricing.price_observation` |
| 4. Retry rejects | `stg_price_observation_reject` | `pricing.resolve_price_rejects` | Re-feeds back to `stg_price_observation` |

All DDL and routines live in [`src/automana/database/SQL/schemas/06_prices.sql`](../src/automana/database/SQL/schemas/06_prices.sql).

---

## Pricing data model

### The chain: Platonic card → printing → product → listing → observation

```
card_catalog.unique_cards_ref         Platonic card ("Lightning Bolt", the concept)
        │  unique_card_id  (UUID)
        ▼
card_catalog.card_version             A specific printing (set + collector_number + frame)
        │  card_version_id  (UUID)
        ▼
pricing.mtg_card_products             MTG-specific bridge: this printing IS this product (1-to-1)
        │  product_id  (UUID)
        ▼
pricing.product_ref                   Game-agnostic abstract product (MTG, Pokémon, Yu-Gi-Oh, …)
        │  product_id  (UUID)
        ▼
pricing.source_product                Product × Marketplace (e.g., this Bolt on TCGplayer)
        │  source_product_id  (BIGSERIAL)
        ▼
pricing.price_observation             Time-series fact table (TimescaleDB hypertable)
```

### Why the split exists

| Table | Role | Why separate |
|---|---|---|
| `unique_cards_ref` | The Platonic card | Query "all prints of Lightning Bolt" without duplicating rules text. |
| `card_version` | One specific printing | Each print has its own art, set, collector number — and its own price curve. |
| `mtg_card_products` | Bridge `card_version` ⇄ `product_ref` | Keeps MTG-specific join logic out of the game-agnostic `product_ref`. 1-to-1 (`UNIQUE(card_version_id)`). |
| `product_ref` | Game-agnostic product | Pricing schema stays TCG-neutral — sources, conditions, finishes are shared machinery. |
| `source_product` | Product × Source | Same product on multiple marketplaces = different price histories. Observations FK on `source_product_id`, not `product_id`. |
| `price_observation` | Raw time series | Per-source, per-day, TimescaleDB hypertable. Rolled up nightly into `print_price_daily` (Tier 2). |

### Dimension reference tables

| Dimension | Ref table | Default helper |
|---|---|---|
| Finish | `pricing.card_finished` | `pricing.default_finish_id()` → `NONFOIL` |
| Condition | `pricing.card_condition` | `pricing.default_condition_id()` → `NM` |
| Language | `card_catalog.language_ref` | `card_catalog.default_language_id()` → `en` |
| Transaction type | `pricing.transaction_type` | — (pipeline hardcodes `sell`) |
| Source | `pricing.price_source` | — (`tcg`, `cardkingdom`, `ebay`, …) |
| Currency | `pricing.currency_ref` | `USD` |
| Data provider | `pricing.data_provider` | — (`mtgstocks`, `mtgjson`, …) |
| Game | `card_catalog.card_games_ref` | — (`mtg`, `pokemon`, …) |

### `price_observation` — the fact table (wide model)

One row = one *(date, product-on-source, transaction type, foil, condition, language, data provider)* tuple, carrying three metric columns plus volume counts:

- `list_low_cents`, `list_avg_cents`, `sold_avg_cents` — prices in cents
- `list_count`, `sold_count` — volumes (not populated by MTGStocks; available for other sources)

**Primary key:** `(ts_date, source_product_id, price_type_id, finish_id, condition_id, language_id, data_provider_id)`

**TimescaleDB characteristics:**
- Hypertable partitioned by `ts_date`
- Chunk interval: **7 days**
- Compression: `segmentby = (source_product_id, price_type_id, finish_id)`, `orderby = ts_date DESC`
- Auto-compression: anything older than **180 days**

### Rollup tiers

| Tier | Table | Grain | Retention |
|---|---|---|---|
| 1 | `pricing.price_observation` | Per source, per day | Live + compressed after 180 days |
| 2 | `pricing.print_price_daily` | Per `card_version_id`, per day (aggregated across sources) | ~5 years |
| 3 | `pricing.print_price_weekly` | Per `card_version_id`, per week (Monday-anchored) | Older than 5 years |

Tiers 2 and 3 collapse the `source_product_id` dimension — "what was this print worth on day X" rather than "what was it worth on TCGplayer on day X". Columns: `min`, `max`, `median`, `p25`, `p75`, `avg`, `n_sources`.

---

## Stage 1 — Raw landing

**Table:** `pricing.raw_mtg_stock_price`

The scraper bulk-inserts one row per *(print_id, ts_date)* carrying all the raw price columns reported by MTGStocks in source currency units (not cents):

| Column | Purpose |
|---|---|
| `ts_date` | Observation date |
| `game_code` | Always `mtg` for this feed |
| `print_id` | MTGStocks proprietary id — the resolution key |
| `price_low`, `price_avg`, `price_market` | Nonfoil price metrics (NUMERIC) |
| `price_foil`, `price_market_foil` | Foil price metrics (NUMERIC) |
| `source_code` | e.g. `tcg`, `cardmarket` |
| `scraped_at` | Ingestion timestamp |
| `card_name`, `set_abbr`, `collector_number` | Metadata for fallback lookup |
| `scryfall_id`, `tcg_id`, `cardtrader_id` | External identifiers for fallback lookup |

Index: `idx_raw_price_date (print_id, ts_date)`, `raw_mtg_stock_price_ts_date_idx (ts_date)`.

This table is a landing zone. It is neither cleaned nor deduplicated — the next stage does that.

---

## Stage 2 — Resolve + stage

**Routine:** `pricing.load_staging_prices_batched(source_name VARCHAR, batch_days INT DEFAULT 30)`

Reads `raw_mtg_stock_price`, resolves each row's `print_id` to a `card_version_id`, ensures the product/source-product rows exist, and writes the result to `stg_price_observation`. Anything it can't resolve goes to `stg_price_observation_reject`.

**Batched by date** (default 30-day windows) with per-batch `BEGIN/EXCEPTION/COMMIT` so a bad window doesn't poison the run.

### Resolution waterfall

For each raw row, `card_version_id` is resolved in strict priority order:

1. **`print_id` map** — join through `card_catalog.card_external_identifier` where `identifier_name = 'mtgstock_id'`. This is the happy path once back-fills have run.
2. **External IDs** (fallback): try in order `scryfall_id` → `tcgplayer_id` → `cardtrader_id`. Respects `card_catalog.scryfall_migration` for `merge`/`move` strategies.
3. **Set + collector number** (last resort): `set_abbr` + `collector_number`, with optional `card_name` cross-check when available.

The resolution method (`PRINT_ID` / `EXTERNAL_ID` / `SET_COLLECTOR` / `UNRESOLVED`) is recorded for observability.

### Back-fill of the print_id map

When a raw row is resolved via path (2) or (3), the procedure back-fills `card_external_identifier` so the next run resolves via path (1). Only unambiguous `print_id → card_version_id` pairs (no conflict within the batch) are back-filled.

### Ensure product + source_product

For every newly resolved `card_version_id` without a `pricing.mtg_card_products` row, the procedure generates a `product_id` UUID, inserts it into `product_ref` and `mtg_card_products`, then ensures a `(product_id, source_id)` row exists in `source_product`.

### Write to staging

Resolved rows are inserted into `pricing.stg_price_observation` (wide model — see below). Unresolved rows are inserted into `pricing.stg_price_observation_reject` with `reject_reason` = `'Could not resolve card_version_id via print_id/external_id/set+collector'`.

### `stg_price_observation` shape (wide)

| Column | Notes |
|---|---|
| `stg_id BIGSERIAL PK` | Surrogate for the DELETE key in stage 3 |
| `ts_date`, `game_code`, `print_id` | From raw |
| `list_low_cents`, `list_avg_cents`, `sold_avg_cents` | Nullable — each staging row may carry only a subset |
| `is_foil` | Derived from which raw price column the row came from |
| `source_code`, `data_provider_id` | Source and provider (both NOT NULL) |
| `value` | Raw source-currency value (for audit) |
| `product_id UUID`, `card_version_id UUID`, `source_product_id BIGINT` | Resolved references |
| `set_abbr`, `collector_number`, `card_name`, `scryfall_id`, `tcg_id` | Audit metadata |
| `scraped_at` | From raw |

Indexes: `stg_price_obs_date_spid_foil_idx (ts_date, source_product_id, is_foil)`.

---

## Stage 3 — Load fact table

**Routine:** `pricing.load_prices_from_staged_batched(batch_days INT DEFAULT 30)`

Moves resolved staging rows into `pricing.price_observation`.

### Pre-flight (once per call)

1. `SET LOCAL work_mem = 512MB`, `maintenance_work_mem = 1GB`, `synchronous_commit = off`.
2. Resolve dimension ids once: `finish_default_id`, `finish_foil_id` (fallback to default if no FOIL row), `price_type_id` (`sell`, hard RAISE if empty), `condition_id` (`NM`), `language_id` (`en`).
3. Compute `min(ts_date)` and `max(ts_date)` across staging. Early RETURN if empty.

### Per-batch body (inside `BEGIN/EXCEPTION`)

**A. Build `_batch` (TEMP, `ON COMMIT DROP`)**
- Select from `stg_price_observation` where `ts_date` falls in the window.
- Map `is_foil → finish_id` via CASE on the pre-resolved smallints.
- Carry `stg_id` for the later DELETE.
- Skip rows where all three cents columns are NULL (nothing to observe).

**B. Build `_dedup`**
- `row_number() OVER (PARTITION BY <full fact PK> ORDER BY scraped_at DESC, stg_id DESC)`, keep `rn=1`.
- Secondary order by `stg_id DESC` makes ties deterministic.

**C. Upsert into `pricing.price_observation`**
- `ON CONFLICT (ts_date, source_product_id, price_type_id, finish_id, condition_id, language_id, data_provider_id)`
- `DO UPDATE`: per-column **"newest non-null wins"** on the three cents columns — a newer scrape with a NULL does not wipe a valid older value.
- `scraped_at = GREATEST(existing, EXCLUDED.scraped_at)`, `updated_at = now()`.

**D. Drain staging**
- `DELETE FROM stg_price_observation WHERE stg_id IN (SELECT stg_id FROM _batch)` — exact 1-to-1 match to what entered the batch.

**E. Commit or rollback**
- On success: `COMMIT` the batch.
- On exception: `RAISE WARNING` with `SQLERRM` + `SQLSTATE`, `ROLLBACK`, loop continues to the next batch.

### Known ceiling: compressed chunks

If staging ever carries rows older than 180 days, the upsert fails with `cannot update compressed chunk`. Mitigation is architectural: keep staging drained inside the compression window, or add an explicit decompression step for out-of-window batches.

---

## Stage 4 — Retry rejects

**Routine:** `pricing.resolve_price_rejects(p_limit INT DEFAULT 50000, p_only_unresolved BOOL DEFAULT TRUE)`

Picks up to `p_limit` unresolved rejects and retries resolution. Takes fresh `scryfall_migration` data into account, so rejects from before a migration landed can be retroactively resolved.

### Pipeline

1. Slice candidates into `tmp_rejects` (`resolved_at IS NULL AND is_terminal IS FALSE`, or everything if `p_only_unresolved := FALSE`).
2. Re-run the same resolution waterfall as stage 2 (`print_id` → external IDs → set+collector), producing `tmp_resolved`.
3. Ensure `product_ref` + `mtg_card_products` for any newly-resolved `card_version_id`.
4. Ensure `source_product` for each `(product_id, mtgstocks source_id)` pair.
5. **Re-feed** resolved rejects into `stg_price_observation` — with the full wide payload (`list_low_cents`, `list_avg_cents`, `sold_avg_cents`, `is_foil`, `data_provider_id`, `value`, and all audit metadata). Skips rows where all three cents columns are NULL.
6. **Mark** the reject row terminal:
   - Successful retries → `terminal_reason = 'Resolved via <METHOD> mapping'`.
   - Rows whose `scryfall_id` is in `scryfall_migration` with `migration_strategy = 'delete'` and no alternative identifiers → `terminal_reason = 'Scryfall migration delete and no alternative identifiers'`.

### Match key for the terminal update

The reject table has no surrogate key yet. The match predicate is
`(ts_date, print_id, is_foil, source_code, data_provider_id, scraped_at)` — one natural row per scrape per `(day, product, foil, provider)`. If this is ever not unique in practice, add `rej_id BIGSERIAL PRIMARY KEY` to `stg_price_observation_reject` and carry it through `tmp_rejects → tmp_resolved`.

### Returns

`bigint` — number of rows re-fed into `stg_price_observation`. After a successful retry those rows go through stage 3 normally on the next run.

---

## End-to-end flow

```
scraper
   │
   ▼
pricing.raw_mtg_stock_price
   │
   │  pricing.load_staging_prices_batched(source_name, batch_days)
   │    • print_id / external_id / set+collector resolution
   │    • back-fill card_external_identifier (mtgstock_id → card_version_id)
   │    • ensure product_ref + mtg_card_products + source_product
   │    ├──── unresolved ────►  pricing.stg_price_observation_reject
   │    │                                 │
   │    │                                 │  pricing.resolve_price_rejects(limit, only_unresolved)
   │    │                                 │    • retries resolution with fresh mappings
   │    │                                 │    • marks terminal on success or scryfall delete
   │    │                                 └── resolved ─────┐
   │    └── resolved ─────────────────────────────────────► │
   │                                                        ▼
   │                                           pricing.stg_price_observation
   │                                                        │
   │  pricing.load_prices_from_staged_batched(batch_days)   │
   │    • build _batch → dedup on fact PK → upsert fact ────┤
   │    • DELETE consumed staging rows by stg_id            │
   │                                                        ▼
   │                                           pricing.price_observation  (Tier 1)
   │                                                        │
   │  (future rollup)                                       ▼
   │                                           pricing.print_price_daily  (Tier 2)
   │                                                        │
   │  (future rollup)                                       ▼
   │                                           pricing.print_price_weekly (Tier 3)
```

---

## Operational notes

### Idempotency

- Stage 2 is idempotent on a per-row basis: re-inserting the same `(ts_date, print_id, scraped_at)` produces a duplicate staging row, but stage 3's dedup collapses them before the upsert. Still, avoid re-running stage 2 over the same raw window without draining staging first — it wastes work.
- Stage 3 is strictly idempotent: the ON CONFLICT clause ensures re-running over the same window is a no-op if nothing has changed.
- Stage 4 is safe to run repeatedly — it only picks rejects that are not yet terminal.

### Chaining under Celery

The Celery chain that drives this pipeline (once wired) should follow the pattern established by [`docs/MTGJSON_PIPELINE.md`](MTGJSON_PIPELINE.md):

1. `ops.pipeline_services.start_run`
2. (scraper service — writes to `raw_mtg_stock_price`)
3. `staging.mtgstock.load_to_staging` → calls `load_staging_prices_batched`
4. `staging.mtgstock.load_to_fact` → calls `load_prices_from_staged_batched`
5. `staging.mtgstock.retry_rejects` → calls `resolve_price_rejects` (optional, periodic)
6. `ops.pipeline_services.finish_run`

Context keys between steps must match parameter names (the `run_service` dispatcher filters by signature — see [`CLAUDE.md`](../CLAUDE.md)).

### Observability

Each routine emits `RAISE NOTICE` per batch and a final summary. Exceptions emit `RAISE WARNING` with `SQLERRM` + `SQLSTATE`. When invoked from a Celery step, those surface in the worker logs via PostgreSQL's client messages.

---

## Related docs

- [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — layered architecture and request flow
- [`docs/MTGJSON_PIPELINE.md`](MTGJSON_PIPELINE.md) — alternative price feed via MTGJson
- [`docs/SCRYFALL_PIPELINE.md`](SCRYFALL_PIPELINE.md) — catalogue feed (populates `card_catalog.*`, not prices)
- [`docs/DATABASE_ROLES.md`](DATABASE_ROLES.md) — DB roles permitted to `CALL` these routines
