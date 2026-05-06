# AutoMana Database Tiers & Staging Architecture

**Last Updated:** 2026-05-06

## Overview

AutoMana implements a **4-tier price storage system** with intermediate **staging layers** to transform raw price observations into aggregated, queryable form. This document maps all tables, staging flows, and current deployment status.

---

## Data Flow Diagram

```
╔════════════════════════════════════════════════════════════════════════════╗
║                      RAW DATA INGESTION (Tier 0)                           ║
║                                                                            ║
║  pricing.raw_mtg_stock_price          pricing.mtgjson_card_prices_staging ║
║  └─ CLEARED each run                  └─ For MTGJson pipeline only        ║
║  └─ Landing table for parquet/CSV     └─ Direct stream → staging          ║
╚════════════════════════════════════════════════════════════════════════════╝
                                    ↓
                    ┌──────────────────┴────────────────┐
                    ↓                                    ↓
╔══════════════════════════════════════════════════════════════════════════╗
║                      STAGING LAYER (Tier 0.5)                            ║
║                                                                          ║
║  pricing.stg_price_observation          pricing.stg_price_observation_reject
║  ├─ Type: UNLOGGED table                ├─ Persistent table
║  ├─ Purpose: Bulks & transforms         ├─ Purpose: Failed resolutions
║  ├─ PK: stg_id (BIGSERIAL)              ├─ Match key: (ts_date, print_id,
║  ├─ Scope: One row per                  │   is_foil, source_code, ...)
║  │  (ts_date, source_product_id,        ├─ Tracking fields:
║  │   is_foil)                           │  - is_terminal: BOOL
║  ├─ Columns (wide model):               │  - terminal_reason: TEXT
║  │  • list_low_cents INTEGER            │  - resolved_at: TIMESTAMPTZ
║  │  • list_avg_cents INTEGER            │  - resolved_source_product_id
║  │  • sold_avg_cents INTEGER            │  - resolved_product_id UUID
║  │  • card_version_id UUID              │  - resolved_card_version_id
║  │  • product_id UUID                   │
║  ├─ Index: (ts_date, source_product_id,├─ Pre-created in schema
║  │  is_foil)                            │  (app_celery needs only USAGE)
║  ├─ Cleared between batches             │
║  ├─ Status: ✅ DEPLOYED                 └─ Status: ✅ DEPLOYED
║  └─ Flow: Raw → [resolution] →          
║    price_observation + rejects
╚══════════════════════════════════════════════════════════════════════════╝
                                    ↓
          ┌─────────────────────────┴────────────────────────────┐
          ↓                                                        ↓
╔═══════════════════════════════════════════╗  ╔════════════════════════════════╗
║  TIER 1: Raw Observations (Hot)           ║  ║  RESOLUTION & RETRY (Feedback) ║
║                                           ║  ║                                ║
║  pricing.price_observation                ║  ║  resolve_price_rejects()       ║
║  ├─ Type: TimescaleDB Hypertable          ║  ║  ├─ Attempts 3 resolution      ║
║  ├─ Scope: 7-day chunks                   ║  ║  │  strategies on rejects      ║
║  ├─ PK: (ts_date, source_product_id,      ║  ║  ├─ Re-feeds resolved to       ║
║  │       price_type_id, finish_id,        ║  ║  │  stg_price_observation     ║
║  │       condition_id, language_id,       ║  ║  └─ Updates reject table      ║
║  │       data_provider_id)                ║  ║    with resolution metadata   ║
║  ├─ Compression: After 180 days           ║  ║                               ║
║  ├─ Index: (source_product_id, ts_date)   ║  ║  Status: ✅ DEPLOYED          ║
║  ├─ Column model (wide):                  ║  └────────────────────────────────┘
║  │  • list_low_cents: MIN price           │              ↓ Re-fed rows
║  │  • list_avg_cents: AVG price           │
║  │  • sold_avg_cents: AVG sale price      │
║  │  • list_count: # listings              │
║  │  • sold_count: # sales                 │
║  ├─ Retention: ∞ (compress after 180d)    │  ┌──────────────────────────────┐
║  ├─ Status: ✅ DEPLOYED & POPULATED       │  │ CURRENT STATUS: 6.09M rejects│
║  │           (but 0% link rate!)          │  │ 0% successfully resolved     │
║  └─ Row count: ~37M (from MTGStocks)      │  └──────────────────────────────┘
╚═══════════════════════════════════════════╝
                    ↓
      load_staging_prices_batched()
      (INLINE PROMOTION to Tier 1)
                    ↓
╔═══════════════════════════════════════════╗
║  TIER 2: Daily Aggregates (Warm) ❌       ║
║                                           ║
║  pricing.print_price_daily                ║
║  ├─ Type: TimescaleDB Hypertable          ║
║  ├─ Scope: 7-day chunks                   ║
║  ├─ PK: (price_date, card_version_id,     ║
║  │       source_id, transaction_type_id,  ║
║  │       finish_id, condition_id,         ║
║  │       language_id)                     ║
║  ├─ Compression: After 30 days            ║
║  ├─ Indexes:                              ║
║  │  • (card_version_id, source_id, date)  ║
║  │  • (price_date, finish_id, ...)        ║
║  ├─ Population: refresh_daily_prices()    ║
║  │  (Tier 1 → Tier 2, batched)            ║
║  ├─ Retention: 5 years                    ║
║  ├─ Status: ❌ NOT DEPLOYED               ║
║  │  • Table exists in schema              ║
║  │  • Procedure written                   ║
║  │  • Never called by pipeline            ║
║  │  • No Python service wrapper           ║
║  └─ Impact: Queries force Tier 1 scans    ║
╚═══════════════════════════════════════════╝
                    ↓ (once Tier 2 deployed)
          archive_to_weekly()
                    ↓
╔═══════════════════════════════════════════╗
║  TIER 3: Weekly Rollups (Cold) ❌         ║
║                                           ║
║  pricing.print_price_weekly               ║
║  ├─ Type: TimescaleDB Hypertable          ║
║  ├─ Scope: 28-day chunks                  ║
║  ├─ PK: (price_week, card_version_id,     ║
║  │       source_id, transaction_type_id,  ║
║  │       finish_id, condition_id,         ║
║  │       language_id)                     ║
║  ├─ Compression: After 7 days             ║
║  ├─ Aggregates: n_days, n_providers       ║
║  ├─ Retention: ∞ (indefinite)             ║
║  ├─ Status: ❌ NOT DEPLOYED               ║
║  │  • Table exists in schema              ║
║  │  • Procedure written                   ║
║  │  • Blocked on Tier 2 deployment        ║
║  │  • No Python service wrapper           ║
║  └─ Impact: Long-term prices not archived ║
╚═══════════════════════════════════════════╝
                    ↓
╔═══════════════════════════════════════════╗
║  SNAPSHOT: Current Prices (Cache) ❌      ║
║                                           ║
║  pricing.print_price_latest               ║
║  ├─ Type: Regular table (not hypertable)  ║
║  ├─ PK: (card_version_id, source_id,      ║
║  │       transaction_type_id, finish_id,  ║
║  │       condition_id, language_id)       ║
║  ├─ Purpose: O(1) "current price" lookup  ║
║  ├─ One row per dimension key             ║
║  ├─ Updated by: refresh_daily_prices()    ║
║  ├─ Status: ❌ NOT DEPLOYED               ║
║  │  • Table exists                        ║
║  │  • Not populated by pipeline           ║
║  └─ Impact: Current-price queries slow    ║
╚═══════════════════════════════════════════╝

╔═══════════════════════════════════════════╗
║  WATERMARK: Resume State (Crash-safe)     ║
║                                           ║
║  pricing.tier_watermark                   ║
║  ├─ PK: tier_name ('daily', 'weekly')     ║
║  ├─ last_processed_date: DATE             ║
║  ├─ Purpose: Idempotent batch resumption  ║
║  ├─ Seeded: '1970-01-01' (epoch)          ║
║  ├─ Status: ✅ DEPLOYED                   ║
║  └─ Used by: refresh_daily_prices(),      ║
║    archive_to_weekly()                    ║
╚═══════════════════════════════════════════╝
```

---

## Tier Deployment Status

| Tier | Table | Procedure | Status | Issue |
|------|-------|-----------|--------|-------|
| **0** | `raw_mtg_stock_price` | — | ✅ Live | Cleared each run |
| **0** | `stg_price_observation` | — | ✅ Live | Unlogged, cleared after batches |
| **0** | `stg_price_observation_reject` | — | ✅ Live | **6.09M rejected rows, 0% resolved** |
| **1** | `price_observation` | — | ✅ Live | 37M rows, hypertable (compressed 180d) |
| **1** | — | `resolve_price_rejects()` | ✅ Live | Returns 0 successful resolutions |
| **2** | `print_price_daily` | `refresh_daily_prices()` | ❌ **Not deployed** | Table exists but procedure never called |
| **3** | `print_price_weekly` | `archive_to_weekly()` | ❌ **Not deployed** | Blocked on Tier 2 |
| **Snapshot** | `print_price_latest` | — | ❌ **Not deployed** | Not populated; no Python wrapper |
| **Watermark** | `tier_watermark` | — | ✅ Live | Seeded, ready for Tier 2/3 |

---

## Pipeline Step Sequence

### Current Flow (mtgStock_download_pipeline)

```
1. bulk_load()
   └─ Service: mtg_stock.data_staging.bulk_load
   └─ Timeout: 3600s (60 min)
   └─ Action: COPY parquet files → pricing.raw_mtg_stock_price
   └─ Input: /data/automana_data/mtgstocks/raw/prints/

2. from_raw_to_staging()
   └─ Service: mtg_stock.data_staging.from_raw_to_staging
   └─ Timeout: 86400s (24 hrs — handles 14 years of history)
   └─ Action: load_staging_prices_batched() procedure
   └─ Output: 
      ├─ pricing.stg_price_observation (successful)
      └─ pricing.stg_price_observation_reject (failed resolutions)
   
   Resolution Strategy (Priority Order):
   ├─ 1st: mtgstock_id → card_external_identifier (fast path)
   ├─ 2nd: scryfall_id/tcgplayer_id/cardtrader_id + lookups (medium)
   └─ 3rd: set_code + collector_number + name match (slow)
   
   Back-fill: Successful resolutions update card_external_identifier for next run

3. retry_rejects()
   └─ Service: mtg_stock.data_staging.retry_rejects
   └─ Timeout: 3600s (60 min)
   └─ Action: resolve_price_rejects() procedure
   └─ Output:
      ├─ Re-fed rows → stg_price_observation (if resolved)
      └─ Updated metadata in stg_price_observation_reject
   
   ⚠️ BLOCKER: Returns 0 successfully resolved rows
       └─ 6.09M rows stuck in reject table
       └─ Root cause: Print-ID resolution failing

4. from_staging_to_prices()
   └─ Service: mtg_stock.data_staging.from_staging_to_prices
   └─ Timeout: 3600s (60 min)
   └─ Action: load_prices_from_staged_batched() procedure
   └─ Input: pricing.stg_price_observation (successes + re-fed)
   └─ Output: pricing.price_observation (Tier 1)
   └─ Flow: INLINE PROMOTION (batched, not deferred)
   └─ Idempotent: Yes (re-runs safe)

5. finish_run()
   └─ Service: ops.pipeline_services.finish_run
   └─ Status: "success"
   └─ Ops tracking: Updated in ops.ingestion_runs

❌ MISSING STEPS (Not in Celery pipeline):
   5. refresh_daily_prices() [would move Tier 1 → Tier 2]
   6. archive_to_weekly() [would move Tier 2 → Tier 3]
   
   └─ Why missing: No Python service wrappers, no Celery beat job
```

---

## Detailed Table Specifications

### **Tier 0: Raw Ingestion**

#### `pricing.raw_mtg_stock_price`
- **Purpose:** Landing table for bulk-loaded parquet files
- **Schema:** `ts_date`, `print_id`, `price_low`, `price_avg`, `price_foil`, `market`, `market_foil`, `source_code`, `card_name`, `set_abbr`, `collector_number`, `scryfall_id`, `tcg_id`, `cardtrader_id`
- **Constraints:** None (bare table for staging)
- **Lifecycle:** DELETED at start of each bulk_load run
- **Index:** `idx_raw_price_date (print_id, ts_date)`
- **Status:** ✅ Live

#### `pricing.mtgjson_card_prices_staging`
- **Purpose:** Landing for MTGJson bulk data (direct stream)
- **Schema:** `id` (SERIAL PK), `card_uuid`, `price_source`, `price_type`, `finish_type`, `currency`, `price_value`, `price_date`
- **Lifecycle:** Cleared after each MTGJson pipeline run
- **Status:** ✅ Live

---

### **Tier 0.5: Staging & Transformation**

#### `pricing.stg_price_observation`
- **Type:** UNLOGGED table (no WAL, fast writes, ephemeral)
- **Purpose:** Batch transformation, resolution, enrichment
- **PK:** `stg_id BIGSERIAL`
- **Scope:** One row per `(ts_date, source_product_id, is_foil)`
- **Columns (Wide Model):**
  - `ts_date` (NOT NULL)
  - `game_code`, `print_id`, `is_foil` (NOT NULL)
  - `source_code`, `data_provider_id` (NOT NULL)
  - `product_id UUID`, `source_product_id BIGINT` (NOT NULL)
  - `list_low_cents`, `list_avg_cents`, `sold_avg_cents` (nullable)
  - `card_version_id UUID` (nullable, resolved)
  - `value NUMERIC(12,4)` (nullable)
- **Index:** `stg_price_obs_date_spid_foil_idx (ts_date, source_product_id, is_foil)`
- **Lifecycle:** Cleared between date windows during load_staging_prices_batched
- **Status:** ✅ Live
- **Row Count:** ~500k per batch (MTGStocks)

#### `pricing.stg_price_observation_reject`
- **Type:** Persistent table (survives runs)
- **Purpose:** Track rows that failed print-ID → product resolution
- **Match Key:** `(ts_date, print_id, is_foil, source_code, data_provider_id, scraped_at)`
- **Tracking Columns:**
  - `is_terminal BOOL DEFAULT false` — final attempt made
  - `terminal_reason TEXT` — why resolution failed
  - `resolved_at TIMESTAMPTZ` — when resolved (if terminal)
  - `resolved_source_product_id BIGINT` — if successful
  - `resolved_product_id UUID` — resolved to product
  - `resolved_card_version_id UUID` — resolved to card
  - `resolved_method TEXT` — which strategy worked
- **Pre-created:** Yes (app_celery has USAGE-only on pricing schema, needs no CREATE)
- **Status:** ✅ Live
- **Row Count:** 6.09M (stuck, 0% resolved)

---

### **Tier 1: Raw Daily Observations (Hot)**

#### `pricing.price_observation`
- **Type:** TimescaleDB Hypertable (auto-partitioned by date)
- **Purpose:** All raw daily price observations, never aggregated
- **Partitioning:**
  - `by_range('ts_date')` with 7-day chunks
  - NOT space-partitioned (original plan abandoned)
- **PK:** `(ts_date, source_product_id, price_type_id, finish_id, condition_id, language_id, data_provider_id)` (7-column)
- **Column Model (Wide):**
  - `list_low_cents` — minimum price observed
  - `list_avg_cents` — average list price
  - `sold_avg_cents` — average sold price
  - `list_count` — number of listings (rarely populated)
  - `sold_count` — number of sales (rarely populated)
- **Constraints:**
  - `chk_nonneg_prices`: All price columns ≥ 0 (or NULL)
  - ⚠️ NO `chk_low_le_avg`: removed during v3 rebuild (existing data may violate it)
- **Compression:**
  - Auto-compress chunks older than 180 days
  - Segment by: `source_product_id, price_type_id, finish_id`
  - Order by: `ts_date DESC`
  - Policy: `add_compression_policy(..., INTERVAL '180 days')`
- **Index:** `idx_price_date (source_product_id, ts_date DESC)`
- **Retention:** Indefinite (compressed after 6 months)
- **Status:** ✅ Live & Populated
- **Row Count:** ~37M from MTGStocks (2009–2026), compressed
- **Storage:** ~1.6 GB (after compression)

---

### **Tier 2: Daily Aggregates (Warm) — NOT DEPLOYED**

#### `pricing.print_price_daily`
- **Type:** TimescaleDB Hypertable
- **Purpose:** Daily aggregates per card version per source
- **Partitioning:** `by_range('price_date', INTERVAL '7 days')`
- **PK:** `(price_date, card_version_id, source_id, transaction_type_id, finish_id, condition_id, language_id)` (7-column)
- **Columns:**
  - `price_date` — the date (not ts_date)
  - `card_version_id UUID` — which card print
  - `source_id SMALLINT` — tcgplayer, cardkingdom, etc.
  - `transaction_type_id` — sell vs buy
  - `finish_id, condition_id, language_id` — variants
  - `list_low_cents, list_avg_cents, sold_avg_cents` — aggregates
  - `n_providers SMALLINT` — count of data sources averaged
- **Compression:**
  - Auto-compress chunks older than 30 days
  - Segment by: `card_version_id, source_id, finish_id`
- **Indexes:**
  - `idx_ppd_card_source_date (card_version_id, source_id, price_date DESC)` — common query pattern
  - `idx_ppd_date_dims (price_date, finish_id, condition_id, language_id)` — range + filter
- **Population:** Via `refresh_daily_prices()` procedure
  - Batches 30 days at a time (tunable)
  - Reads from Tier 1, aggregates, inserts into Tier 2
  - Watermark tracks progress (crash-safe resume)
- **Retention:** 5 years
- **Status:** ❌ **NOT DEPLOYED**
  - Table exists in schema file
  - Procedure written & tested
  - Never called by pipeline
  - No Python service wrapper exists
- **Impact:** Queries must scan full Tier 1 (37M rows) for any historical price query

---

### **Tier 3: Weekly Rollups (Cold) — NOT DEPLOYED**

#### `pricing.print_price_weekly`
- **Type:** TimescaleDB Hypertable
- **Purpose:** Weekly aggregates, long-term archive
- **Partitioning:** `by_range('price_week', INTERVAL '28 days')` — one 4-week chunk per partition
- **PK:** `(price_week, card_version_id, source_id, transaction_type_id, finish_id, condition_id, language_id)`
- **Columns:**
  - `price_week` — Monday of ISO week (DATE_TRUNC('week', price_date))
  - Card + source dimensions (same as Tier 2)
  - `list_low_cents, list_avg_cents, sold_avg_cents` — aggregates
  - `n_days SMALLINT` — count of days in week (1–7)
  - `n_providers SMALLINT` — count of sources
- **Compression:**
  - Auto-compress chunks older than 7 days (more aggressive than Tier 2)
  - Segment by: `card_version_id, source_id, finish_id`
- **Indexes:**
  - `idx_ppw_card_source_week (card_version_id, source_id, price_week DESC)`
  - `idx_ppw_week_dims (price_week, finish_id, condition_id, language_id)`
- **Population:** Via `archive_to_weekly()` procedure
  - Reads from Tier 2, aggregates to weekly, inserts into Tier 3
  - Deletes archived rows from Tier 2 to cap 5-year retention
  - Default: Archive data older than 5 years
- **Retention:** Indefinite
- **Status:** ❌ **NOT DEPLOYED**
  - Table exists in schema file
  - Procedure written & tested
  - Blocked on Tier 2 deployment
  - No Python service wrapper
- **Impact:** No long-term archive; Tier 2 would grow indefinitely without this

---

### **Snapshot: Current Prices — NOT DEPLOYED**

#### `pricing.print_price_latest`
- **Type:** Regular table (not hypertable, no time-series)
- **Purpose:** O(1) "current price" lookups (cache)
- **PK:** `(card_version_id, source_id, transaction_type_id, finish_id, condition_id, language_id)` (6-column, no time)
- **Columns:**
  - Dimension columns (PK)
  - `price_date DATE` — most recent date in Tier 2
  - `list_low_cents, list_avg_cents, sold_avg_cents` — prices
  - `n_providers SMALLINT` — count of sources
  - `updated_at TIMESTAMPTZ` — last refresh
- **Index:** `idx_ppl_card_source (card_version_id, source_id)`
- **Population:** Via `refresh_daily_prices()` procedure (upsert after Tier 2 update)
- **Status:** ❌ **NOT DEPLOYED**
  - Table exists in schema file
  - No pipeline call
  - Empty
- **Impact:** Current-price queries force full Tier 1 hypertable scan instead of index lookup

---

### **Watermark: Resume State**

#### `pricing.tier_watermark`
- **Type:** Regular table (state tracking)
- **Purpose:** Crash-safe resumption for batch procedures
- **PK:** `tier_name TEXT` ('daily', 'weekly')
- **Columns:**
  - `last_processed_date DATE` — the last date successfully completed
  - `updated_at TIMESTAMPTZ`
- **Initialization:** Seeds to '1970-01-01' (epoch) in schema file
- **Usage:**
  - `refresh_daily_prices()`: Reads watermark, processes from +1 day, updates on success
  - `archive_to_weekly()`: Reads watermark (weekly tier), archives next batch
- **Status:** ✅ Live & Seeded
- **Idempotency:** Both procedures check watermark and skip already-processed dates

---

## Critical Blockers & Gaps

### **Gap 1: MTGStock Pipeline 0% Link Rate (BLOCKING)**

**Current State:**
- 6.09M rows in `stg_price_observation_reject`
- 0 rows successfully resolved in `resolve_price_rejects()`
- ~37M rows in Tier 1 (historical data, pre-rejection era)
- Recent MTGStocks runs contribute 0 to Tier 1

**Root Cause:**
Print-ID → card_version_id resolution failing because:
- Missing art-card mapping (which print art belongs to which card version)
- No token resolution (special card types not mapped to card_versions)
- Scryfall migration lookup incomplete

**Fix Required:**
- Implement art-card set-code mapping (see MTGSTOCK_REJECT_ANALYSIS.md)
- Add token type → card_version resolution
- Backfill card_external_identifier table to accelerate future runs

**Impact:**
- Tier 1 is stalled for new MTGStocks data
- Tier 2/3 have nothing to aggregate from recent runs
- Pricing data is 2–3 months stale

---

### **Gap 2: Tier 2 Not Deployed (BLOCKING Tier 3)**

**Current State:**
- Table exists in schema file
- Procedure `refresh_daily_prices()` fully implemented
- Never called by pipeline
- No Python service wrapper (`PriceRepository.call_refresh_daily_prices()` does not exist)
- No Celery beat job scheduled

**Fix Required:**
1. Create Python service wrapper in `PriceRepository`
2. Register Celery beat job to run daily (or on-demand after MTGStocks pipeline)
3. Test procedure end-to-end
4. Monitor aggregation quality

**Blocker For:**
- Tier 3 (depends on Tier 2 data)
- Current-price snapshot (updated by Tier 2 refresh)

**Impact:**
- Query performance degradation: All price queries force Tier 1 hypertable scans
- No daily aggregates for UI/API (must fetch raw 37M rows and aggregate in app)

---

### **Gap 3: Tier 3 Not Deployed (NOT CRITICAL)**

**Current State:**
- Table exists in schema file
- Procedure `archive_to_weekly()` fully implemented
- Blocked on Tier 2 deployment

**Fix Required:**
1. Deploy Tier 2 first (Gap 2)
2. Create Python service wrapper (`PriceRepository.call_archive_to_weekly()`)
3. Register Celery beat job to run monthly
4. Verify cascade delete from Tier 2 works

**Impact:**
- Tier 2 unbounded growth (5-year retention never triggered)
- No long-term archive for historical analysis

---

### **Gap 4: Current-Price Snapshot Not Deployed (NICE-TO-HAVE)**

**Current State:**
- Table exists in schema file
- Populated by `refresh_daily_prices()` upsert (when Tier 2 deployed)
- Currently empty

**Fix Required:**
1. Deploy Tier 2 (Gap 2) — automatic once refresh_daily_prices() runs
2. Index on `(card_version_id, source_id)` exists

**Impact:**
- Current-price queries slow; benefits realized once Tier 2 active

---

### **Gap 5: Pricing Metrics Failing**

**Current State:**
- 16+ metrics timeout on Tier 1 hypertable scans
- No time-bounded windows

**Fix Required:**
- Rewrite metrics SQL to use `pg_class.reltuples` estimates
- Add time-bounded CTEs (e.g., last 30 days only)
- Or increase Docker `shm_size` to 512MB for larger work_mem

**Impact:**
- No observability into pricing data quality
- Cannot detect stalls, duplicates, missing sources

---

### **Gap 6: Watermark Table Not Seeded (MINOR)**

**Current State:**
- Table created with '1970-01-01' sentinel values ✅
- Ready to use

**Fix Required:**
- None (already initialized in schema)

---

### **Gap 7: Python Service Layer Not Wired (BLOCKING Tier 2/3)**

**Current State:**
- No `PriceRepository.call_refresh_daily_prices()` method
- No `PriceRepository.call_archive_to_weekly()` method
- Procedures exist but cannot be invoked from Celery

**Fix Required:**
1. Add wrapper methods to `PriceRepository`:
   ```python
   async def call_refresh_daily_prices(self, p_from=None, p_to=None) -> None:
       await self.connection.execute("CALL pricing.refresh_daily_prices($1, $2)", p_from, p_to)
   
   async def call_archive_to_weekly(self, older_than="5 years") -> None:
       await self.connection.execute("CALL pricing.archive_to_weekly($1)", older_than)
   ```
2. Register Celery beat job
3. Update MTGStock pipeline to call after from_staging_to_prices

**Impact:**
- Tier 2/3 cannot be automated without this

---

## Dependency Order for Remediation

```
1. Fix Gap 1 (Link Rate)
   └─ Enables Tier 1 to receive new data
   └─ Prerequisite for testing Tier 2

2. Gap 2 (Deploy Tier 2)
   ├─ Create Python wrappers (Gap 7 partial)
   ├─ Register Celery beat job
   └─ Enables aggregates, fixes query performance

3. Gap 4 (Current-Price Snapshot)
   └─ Automatic once Tier 2 running

4. Gap 3 (Deploy Tier 3)
   └─ Requires Gap 2 complete
   └─ Caps Tier 2 retention at 5 years

5. Gap 5 (Metrics)
   └─ Independent, can be tackled anytime
   └─ Improves observability

6. Gap 6 (Watermark)
   └─ Already done ✅
```

---

## Key Design Facts

### Resolution Waterfall
When load_staging_prices_batched processes a raw row:
1. **Fast path (0.1s):** Look up mtgstock_id in `card_external_identifier` → source_product_id
2. **Medium path (1–10s):** Try scryfall_id / tcgplayer_id / cardtrader_id lookups with optional scryfall_migration
3. **Slow path (100–1000s):** Try set_code + collector_number + fuzzy name match

If resolved via (2) or (3), back-fill `card_external_identifier` for next run (fast path acceleration).

### Inline Promotion
- load_staging_prices_batched promotes each batch to Tier 1 BEFORE moving to next date window
- Tier 1 is populated incrementally, not deferred
- load_prices_from_staged_batched (Stage 4) handles re-fed rejects, not new batches

### Idempotency
- Both refresh_daily_prices() and archive_to_weekly() are fully idempotent
- Check watermark, skip completed dates, resume from last_processed_date + 1
- Safe to re-run on failure or out-of-order

### Compression Strategy
- **Tier 1:** 7-day chunks, compress after 180 days (6-month hot window)
- **Tier 2:** 7-day chunks, compress after 30 days (aggressive, daily queries are time-bounded)
- **Tier 3:** 28-day chunks, compress after 7 days (very cold, rarely queried)

---

## File References

- **Schema:** `src/automana/database/SQL/schemas/06_prices.sql` (tables, procedures, procedures)
- **Migrations:** `src/automana/database/SQL/migrations/migration_18_pricing_tiers.sql` (Tier 2/3 DDL)
- **Pipeline:** `src/automana/worker/tasks/pipelines.py` (Celery chain definition)
- **Services:** `src/automana/database/repositories/price_repository.py` (data access layer)
- **Debt:** `docs/PIPELINE_TECHNICAL_DEBT.md` (error log and detailed fixes)

---

## Glossary

- **Tier 0:** Raw landing tables (raw_mtg_stock_price, mtgjson_card_prices_staging)
- **Tier 0.5:** Staging tables (stg_price_observation, stg_price_observation_reject)
- **Tier 1:** Raw daily observations (price_observation hypertable) — hot, uncompressed for 180d
- **Tier 2:** Daily aggregates (print_price_daily hypertable) — warm, 5-year retention
- **Tier 3:** Weekly rollups (print_price_weekly hypertable) — cold, indefinite retention
- **Snapshot:** Current prices (print_price_latest) — one row per dimension key, O(1) lookup
- **Watermark:** Crash-safe resume state (tier_watermark) — tracks last processed date per tier
- **Hypertable:** TimescaleDB time-series table with automatic partitioning & compression
- **UNLOGGED:** Table without WAL; fast writes, ephemeral (survives crashes but loses data)
- **Inline Promotion:** Promoting data to next tier during the same pipeline run (not deferred)
- **Composite PK:** Multi-column primary key, all columns must be non-NULL
