# Pricing Tier 2 / Tier 3 — Design Spec
**Date:** 2026-04-30  
**Branch:** fix/mtgstock-foil-finish-resolution  
**Status:** Approved — ready for implementation

---

## Background

Tier 1 (`pricing.price_observation`) is a live TimescaleDB hypertable keyed by
`(ts_date, source_product_id, price_type_id, finish_id, condition_id, language_id,
data_provider_id)`. It holds every price observation ingested from all sources and
is compressed after 180 days.

Tiers 2 and 3 were stubbed in `06_prices.sql` but never wired up:

- `print_price_daily` was created with the wrong grain (no `source_id`, had
  `p25`/`p75` columns, was a plain table).
- `print_price_weekly` was defined but the schema file itself notes it was
  **never applied to the live DB** and had a syntax error.
- Neither table had a population procedure, compression, or lifecycle management.

This spec replaces both stubs with a correct, source-preserving design.

---

## Design Decisions

### Source identity is preserved at every tier

Tier 2 and tier 3 keep `source_id` in their primary keys. Cross-source
aggregation (a single row per card per day across all markets) was explicitly
rejected — it destroys the per-market signal needed for arbitrage analysis.

### Same 3-column price interface as tier 1

Tier 1 stores `list_low_cents`, `list_avg_cents`, `sold_avg_cents`. Tier 2 and 3
use the same three columns, aggregated across `data_provider_id` (multiple
providers may report the same source on the same day):

- `list_low_cents` → `MIN` across providers
- `list_avg_cents` → `AVG` across providers  
- `sold_avg_cents` → `AVG` across providers
- `n_providers`    → `COUNT(DISTINCT data_provider_id)`

`p25_price` / `p75_price` / `median_price` are dropped: with 1–3 data points per
(source, card, day) these are statistically meaningless.

### TimescaleDB throughout

Tier 2 is a TimescaleDB hypertable (7-day chunks, compressed after 30 days).
Tier 3 is a TimescaleDB hypertable (4-week chunks, compressed after 7 days).
Consistent with tier 1 and `markets.product_prices`.

### Latest-price snapshot

A `print_price_latest` table holds one row per full dimension key — always the
most recent price regardless of tier. Every "current price" query hits this table
instead of scanning the hypertable for `MAX(price_date)`.

### Resumable procedures via watermark

A `tier_watermark` table records the last successfully processed date for each
tier refresh. Procedures read this on startup to skip already-processed windows
and resume cleanly after a crash.

---

## Tables

### `pricing.print_price_daily`

Replaces the existing stub (DROP + recreate — table has never been populated).

```
PK: (price_date, card_version_id, source_id, transaction_type_id, finish_id, condition_id, language_id)

price_date          DATE        NOT NULL
card_version_id     UUID        NOT NULL  → card_catalog.card_version
source_id           SMALLINT    NOT NULL  → pricing.price_source
transaction_type_id INTEGER     NOT NULL  → pricing.transaction_type
finish_id           SMALLINT    NOT NULL  → pricing.card_finished   (default: NONFOIL)
condition_id        SMALLINT    NOT NULL  → pricing.card_condition  (default: NM)
language_id         SMALLINT    NOT NULL  → card_catalog.language_ref (default: en)

list_low_cents      INTEGER     (MIN across providers, nullable)
list_avg_cents      INTEGER     (AVG across providers, nullable)
sold_avg_cents      INTEGER     (AVG across providers, nullable)
n_providers         SMALLINT    (COUNT DISTINCT data_provider_id)

created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
```

Constraints: `chk_ppd_prices_nonneg` (all price columns ≥ 0 when non-null).
`chk_ppd_low_le_avg` is intentionally omitted: after cross-provider aggregation
(`MIN(list_low)` vs `AVG(list_avg)`) the invariant is not guaranteed to hold.

TimescaleDB: hypertable on `price_date`, 7-day chunks, compressed after 30 days,
`compress_segmentby = 'card_version_id, source_id, finish_id'`,
`compress_orderby   = 'price_date DESC'`.

---

### `pricing.print_price_weekly`

Replaces the existing stub (never applied to live DB).

```
PK: (price_week, card_version_id, source_id, transaction_type_id, finish_id, condition_id, language_id)

price_week          DATE        NOT NULL  -- DATE_TRUNC('week', price_date) = Monday
card_version_id     UUID        NOT NULL  → card_catalog.card_version
source_id           SMALLINT    NOT NULL  → pricing.price_source
transaction_type_id INTEGER     NOT NULL  → pricing.transaction_type
finish_id           SMALLINT    NOT NULL  (default: NONFOIL)
condition_id        SMALLINT    NOT NULL  (default: NM)
language_id         SMALLINT    NOT NULL  (default: en)

list_low_cents      INTEGER     (MIN of daily list_low across the week)
list_avg_cents      INTEGER     (AVG of daily list_avg across the week)
sold_avg_cents      INTEGER     (AVG of daily sold_avg across the week)
n_days              SMALLINT    (COUNT DISTINCT price_date — 1 to 7)
n_providers         SMALLINT    (MAX n_providers seen on any day in the week)

created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
```

TimescaleDB: hypertable on `price_week`, 4-week chunks, compressed after 7 days,
same segmentby/orderby as tier 2.

---

### `pricing.print_price_latest`

One row per dimension key — the most recent price across all tiers.
Plain table (no hypertable needed — it is a snapshot, not time-series).

```
PK: (card_version_id, source_id, transaction_type_id, finish_id, condition_id, language_id)

card_version_id     UUID        NOT NULL
source_id           SMALLINT    NOT NULL
transaction_type_id INTEGER     NOT NULL
finish_id           SMALLINT    NOT NULL
condition_id        SMALLINT    NOT NULL
language_id         SMALLINT    NOT NULL

price_date          DATE        NOT NULL  -- date of the most recent observation
list_low_cents      INTEGER
list_avg_cents      INTEGER
sold_avg_cents      INTEGER
n_providers         SMALLINT

updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
```

Maintained by `refresh_daily_prices`: upsert with `DO UPDATE` only when
`EXCLUDED.price_date >= print_price_latest.price_date`.

---

### `pricing.tier_watermark`

```
PK: tier_name TEXT  ('daily', 'weekly')

tier_name           TEXT        NOT NULL
last_processed_date DATE        NOT NULL
updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
```

Seeded with `('daily', '1970-01-01')` and `('weekly', '1970-01-01')` on first
deploy (procedures treat the epoch sentinel as "nothing processed yet").

---

## Procedures

### `pricing.refresh_daily_prices(p_from DATE DEFAULT NULL, p_to DATE DEFAULT NULL)`

**Purpose:** Populate / refresh `print_price_daily` and `print_price_latest` from
tier 1.

**Date range resolution:**
- If `p_from` is NULL, read `last_processed_date` from `tier_watermark` where
  `tier_name = 'daily'` and add 1 day.
- If `p_to` is NULL, default to `CURRENT_DATE - 1` (yesterday — today's scrape
  may still be in progress).

**Loop (30-day batches, same pattern as `load_staging_prices_batched`):**

For each batch window:
1. JOIN `price_observation` → `source_product` → `mtg_card_products` to resolve
   `card_version_id` and `source_id`.
2. `GROUP BY (ts_date, card_version_id, source_id, price_type_id, finish_id,
   condition_id, language_id)`.
3. Aggregate: `MIN(list_low_cents)`, `AVG(list_avg_cents)::int`,
   `AVG(sold_avg_cents)::int`, `COUNT(DISTINCT data_provider_id)`.
4. Upsert into `print_price_daily` — `DO UPDATE SET ... updated_at = now()`.
5. Upsert the same rows into `print_price_latest` — `DO UPDATE` only when
   `EXCLUDED.price_date >= print_price_latest.price_date`.
6. COMMIT per batch. On batch exception: ROLLBACK + RAISE WARNING, continue.

**After loop:** Update `tier_watermark` (`tier_name = 'daily'`) to `p_to`.

**Error handling:** Mirrors `load_staging_prices_batched` — per-batch
BEGIN/EXCEPTION/COMMIT so one bad window does not abort the run.

---

### `pricing.archive_to_weekly(p_older_than INTERVAL DEFAULT '5 years')`

**Purpose:** Roll up `print_price_daily` rows older than the cutoff into
`print_price_weekly`, then delete them from tier 2.

**Cutoff:** `cutoff_date := CURRENT_DATE - p_older_than`.

**Loop (4-week batches):**

For each 4-week window of `print_price_daily` where `price_date < cutoff_date`:
1. `GROUP BY (DATE_TRUNC('week', price_date), card_version_id, source_id,
   transaction_type_id, finish_id, condition_id, language_id)`.
2. Aggregate: `MIN(list_low_cents)`, `AVG(list_avg_cents)::int`,
   `AVG(sold_avg_cents)::int`, `COUNT(DISTINCT price_date)` as `n_days`,
   `MAX(n_providers)` as `n_providers`.
3. Upsert into `print_price_weekly` — `DO UPDATE` merges (re-running is safe).
4. DELETE from `print_price_daily` for the processed window.
5. COMMIT per batch.

**After loop:** Update `tier_watermark` (`tier_name = 'weekly'`) to last
processed week.

---

## Indexes

**`print_price_daily`**

```sql
-- Fast chart: one card over time (primary use case)
idx_ppd_card_source_date ON (card_version_id, source_id, price_date DESC)

-- Fast cross-source scan for a date range
idx_ppd_date_dims ON (price_date, finish_id, condition_id, language_id)
```

**`print_price_weekly`**

```sql
idx_ppw_card_source_week ON (card_version_id, source_id, price_week DESC)
idx_ppw_week_dims        ON (price_week, finish_id, condition_id, language_id)
```

**`print_price_latest`**

```sql
-- Card lookup (PK covers it; this supports source-filtered lookups)
idx_ppl_card_source ON (card_version_id, source_id)
```

---

## Lifecycle Summary

| Event | Procedure | Trigger |
|---|---|---|
| Daily (after mtgstock pipeline) | `refresh_daily_prices()` | Celery beat |
| Monthly | `archive_to_weekly()` | Celery beat |
| Tier 2 max age | 5 years of daily rows | Purged by `archive_to_weekly` |
| Tier 3 retention | Indefinite weekly rows | Never deleted |

---

## Migration

**Migration 18** (`migration_18_pricing_tiers.sql`):

1. Drop and recreate `pricing.print_price_daily` with new DDL.
2. Create `pricing.print_price_weekly` (was never applied to live DB).
3. Create `pricing.print_price_latest`.
4. Create `pricing.tier_watermark` and seed with epoch sentinels.
5. Create `pricing.refresh_daily_prices` procedure.
6. Create `pricing.archive_to_weekly` procedure.
7. Create all indexes listed above.
8. Grant `EXECUTE` on both procedures to `app_celery`.
9. Grant `SELECT, INSERT, UPDATE, DELETE` on the three new tables to `app_celery`.
10. Grant `SELECT` on the three new tables to `app_ro`.

---

## Files Touched

| File | Change |
|---|---|
| `src/automana/database/SQL/migrations/migration_18_pricing_tiers.sql` | New — full migration |
| `src/automana/database/SQL/schemas/06_prices.sql` | Update tier 2/3 DDL stubs to match migration (sync reference) |
| `src/automana/database/SQL/maintenance/pricing_integrity_checks.sql` | Add checks for tier 2/3 table existence and `tier_watermark` staleness |

---

## Out of Scope

- Celery beat schedule wiring (separate ticket — procedures exist; wiring them into
  the beat schedule is a pipeline task, not a schema migration).
- Service-layer / repository Python code to call the new procedures.
- Backfill of historical tier 1 data into tier 2 (run manually after migration via
  `CALL pricing.refresh_daily_prices('2012-01-01', CURRENT_DATE - 1)`).
