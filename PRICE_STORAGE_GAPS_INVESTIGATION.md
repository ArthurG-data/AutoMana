# AutoMana Price Storage: 3-Tier Architecture & Gaps Investigation
**Date:** 2026-05-05  
**Scope:** Comprehensive audit of price data storage tiers, pipeline, and data quality

---

## Executive Summary

AutoMana implements a **3-tier price storage architecture** designed to balance **freshness** (Tier 1: daily observations), **queryability** (Tier 2: aggregated daily), and **retention** (Tier 3: weekly archive). However, **critical gaps exist at every tier**:

| Tier | Status | Impact |
|------|--------|--------|
| **Tier 1** (`price_observation`) | Deployed, **0% link rate** | Data present but 6.09M rejected rows block ingestion |
| **Tier 2** (`print_price_daily`) | **Designed, not deployed** | No daily aggregates for UI/API |
| **Tier 3** (`print_price_weekly`) | **Designed, not deployed** | No long-term archive |
| **Snapshot** (`print_price_latest`) | **Designed, not deployed** | No fast path for "current price" queries |

**Root cause:** MTGStock pipeline has 0% link rate (6.09M rejects vs 0 linked rows), blocking all Tier 1 data ingestion. Tier 2/3 deployment is blocked waiting on pipeline fixes.

---

## Architecture Overview

### The 3 Tiers (Designed)

```
TIER 1 (Raw observations)
  pricing.price_observation
  Grain: (ts_date, source_product_id, data_provider_id, finish_id, condition_id, language_id)
  Retention: Live + compressed after 180 days
  TimescaleDB: 7-day chunks, auto-compress after 180 days
  Status: ✅ Deployed, structure correct
  Data: ❌ 0 rows (pipeline failing)

       │
       │ refresh_daily_prices() — daily, Celery beat
       ▼

TIER 2 (Daily rollup, source-preserving)
  pricing.print_price_daily
  Grain: (price_date, card_version_id, source_id, finish_id, condition_id, language_id)
  Retention: ~5 years
  TimescaleDB: 7-day chunks, auto-compress after 30 days
  Status: ❌ Designed in migration_18, NOT DEPLOYED
  Data: ❌ 0 rows
  
       │
       │ archive_to_weekly() — monthly, Celery beat
       ▼

TIER 3 (Weekly archive)
  pricing.print_price_weekly
  Grain: (price_week, card_version_id, source_id, finish_id, condition_id, language_id)
  Retention: Indefinite
  TimescaleDB: 4-week chunks, auto-compress after 7 days
  Status: ❌ Designed in migration_18, NOT DEPLOYED
  Data: ❌ 0 rows

SNAPSHOT TABLE (Current price fast path)
  pricing.print_price_latest
  Grain: (card_version_id, source_id, finish_id, condition_id, language_id) — one row per key
  Purpose: O(1) lookup for "what's the current price"
  Status: ❌ Designed in migration_18, NOT DEPLOYED
```

### Key Design Decisions

✅ **Source identity preserved at every tier** — `source_id` is in the PK of Tier 2 and 3, preventing cross-market aggregation that would destroy arbitrage signals.

✅ **3-column price interface** (same across all tiers):
- `list_low_cents` (MIN across providers)
- `list_avg_cents` (AVG across providers)
- `sold_avg_cents` (AVG across providers)

✅ **Aggregation across `data_provider_id` only** — multiple providers reporting the same source on the same day are collapsed; source-per-day remains granular.

✅ **Crash-safe resume** via `tier_watermark` table (designed but not deployed).

---

## Critical Gaps

### 🔴 **Gap 1: MTGStock Pipeline — 0% Link Rate (BLOCKING)**

**Problem:** The MTGStock ingestion pipeline is rejecting **6.09M rows** out of 6.09M, with **0 rows** successfully resolved to `card_version_id`.

**Details:**

| Metric | Value | Category |
|--------|-------|----------|
| Raw rows ingested | 6,090,227 | volume |
| Resolved to card_version | 0 | ❌ 0% link rate |
| Rejected (unresolved) | 5,801,810 | ❌ 95% of all data |
| Terminal rejects | 288,417 | (marked as failed in prior run) |
| Distinct prints linked | 0 | ❌ should be ~1000s |

**Classification of rejects** (from `docs/MTGSTOCK_REJECT_ANALYSIS.md`):
- **~680K rows** — art-card set-code mapping missing (Fix 2)
- **~3.8M rows** — tokens without token resolution (Fix 3)
- **~1.3M rows** — require Scryfall-side investigation
- **~0 rows** — currently linked ❌

**Impact:**
- Tier 1 has 0 price observations
- Tier 2/3 have no data to aggregate (all upstream is blocked)
- Metrics that query Tier 1 time out or fail entirely
- No price data reaching the frontend

**Root Cause:** The print_id → card_version_id resolution waterfall (PRINT_ID → EXTERNAL_ID → SET_COLLECTOR) is failing at every stage:

1. **PRINT_ID mapping** — `card_catalog.card_external_identifier` where `identifier_name = 'mtgstock_id'` has no entries (back-fill not yet run)
2. **EXTERNAL_ID fallback** — scryfall_id / tcgplayer_id / cardtrader_id not present in raw MTGStock rows
3. **SET_COLLECTOR fallback** — many rows have incorrect set_code (art-cards use nonstandard codes) or missing collector numbers

**Workaround:** Fixes 2 and 3 in `docs/PIPELINE_TECHNICAL_DEBT.md` are documented. Status: **not yet implemented**.

---

### 🔴 **Gap 2: Tier 2 Not Deployed (BLOCKING Tier 2 & 3)**

**Problem:** `pricing.print_price_daily` table and `refresh_daily_prices()` procedure are designed in `migration_18_pricing_tiers.sql` but **never applied to the database**.

**What should exist (per migration_18):**

```sql
CREATE TABLE pricing.print_price_daily (
  price_date DATE NOT NULL,
  card_version_id UUID NOT NULL,
  source_id SMALLINT NOT NULL,
  transaction_type_id INTEGER NOT NULL,
  finish_id SMALLINT NOT NULL,
  condition_id SMALLINT NOT NULL,
  language_id SMALLINT NOT NULL,
  
  list_low_cents INTEGER,
  list_avg_cents INTEGER,
  sold_avg_cents INTEGER,
  n_providers SMALLINT,
  
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  
  PRIMARY KEY (price_date, card_version_id, source_id, transaction_type_id, finish_id, condition_id, language_id)
) USING timescaledb;
```

**Status in database:** Table stubs exist in `06_prices.sql` but with **wrong schema** (old `p25`/`p75` columns, missing `source_id`, not a hypertable).

**Procedures designed but not wired:**
- `pricing.refresh_daily_prices(p_from DATE, p_to DATE)` — aggregates Tier 1 into daily rows (30-day batches)
- No Celery beat task to call it (designed to run daily, post-MTGStock pipeline)

**Impact:**
- UI and APIs cannot query aggregated daily prices
- Every price query must scan the raw Tier 1 hypertable for MAX(price_date) and aggregate on-the-fly
- No analytical dashboards possible without full table scans

**Blocker:** Tier 1 is empty (Gap 1), so deployment of Tier 2 will show 0 data. Recommend deploying now (procedures are idempotent) so data flows once Gap 1 is fixed.

---

### 🔴 **Gap 3: Tier 3 Not Deployed (BLOCKING Long-Term Archive)**

**Problem:** `pricing.print_price_weekly` table and `archive_to_weekly()` procedure are designed in `migration_18_pricing_tiers.sql` but **never applied to the database**.

**What should exist:**

```sql
CREATE TABLE pricing.print_price_weekly (
  price_week DATE NOT NULL,  -- DATE_TRUNC('week', price_date)
  card_version_id UUID NOT NULL,
  source_id SMALLINT NOT NULL,
  ...
  n_days SMALLINT,  -- 1 to 7
  n_providers SMALLINT,  -- MAX across the week
  PRIMARY KEY (price_week, card_version_id, source_id, ...)
) USING timescaledb;
```

**Procedures designed but not wired:**
- `pricing.archive_to_weekly(p_older_than INTERVAL DEFAULT '5 years')` — rolls Tier 2 into weekly starting 5 years ago
- No Celery beat task to call it (designed to run monthly)

**Impact:**
- No long-term price trend archive
- Cannot answer "what did this card cost in Q3 2023?"
- Tier 2 has unbounded growth (5 years of daily data)
- Cost of Tier 2 hypertable grows without purging old data

**Blocker:** Same as Gap 2 — depends on Tier 1 fix. But deployment can happen now.

---

### 🔴 **Gap 4: Latest Price Snapshot Not Deployed (BLOCKING Fast Queries)**

**Problem:** `pricing.print_price_latest` table is designed in `migration_18_pricing_tiers.sql` but **never applied to the database**.

**What should exist:**

```sql
CREATE TABLE pricing.print_price_latest (
  card_version_id UUID NOT NULL,
  source_id SMALLINT NOT NULL,
  transaction_type_id INTEGER NOT NULL,
  finish_id SMALLINT NOT NULL,
  condition_id SMALLINT NOT NULL,
  language_id SMALLINT NOT NULL,
  
  price_date DATE NOT NULL,
  list_low_cents INTEGER,
  list_avg_cents INTEGER,
  sold_avg_cents INTEGER,
  n_providers SMALLINT,
  
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  
  PRIMARY KEY (card_version_id, source_id, transaction_type_id, finish_id, condition_id, language_id)
);
```

**Current state:** Queries for "current price of card X on source Y" must:
1. Scan Tier 1 hypertable
2. Filter to most recent `ts_date`
3. Aggregate across `data_provider_id`
4. Return to caller

**With snapshot table:** O(1) lookup into a plain table.

**Impact:**
- Every "current price" query is slow (hypertable scan + aggregation)
- API response times degrade as Tier 1 grows
- No index-friendly fast path for the most common query pattern

---

### 🟡 **Gap 5: Pricing Report Metrics Failing (OPERATIONAL)**

**Problem:** The `pricing_report` runner (which runs hourly on beat) has **16+ metric checks failing** with `TimeoutError` or `InFailedSQLTransactionError`.

**Affected metrics:**
- `pricing.card_coverage.*` (3 metrics)
- `pricing.coverage.*` (1 metric)
- `pricing.freshness.*` (2 metrics)
- `pricing.referential.*` (2 metrics)
- `pricing.staging.*` (1 metric)
- `pricing.duplicate_detection.*` (1 metric)

**Root cause:** Full hypertable scans on `pricing.price_observation` without time-bounded CTEs. Each scan times out at 60–120 seconds (default `statement_timeout`).

**Workarounds (from PIPELINE_TECHNICAL_DEBT.md):**
1. **Rewrite SQL** to use `pg_class.reltuples` for row estimates, `pg_constraint` for PK checks, and time-bounded windows (e.g., last 90 days).
2. **Raise Docker `/dev/shm`** from default (64MB) to 512MB — allows in-memory sorts to succeed.

**Impact:**
- Health checks are blind (metrics don't run)
- No alerting on pricing data quality issues
- `pipeline-health-check` skill cannot auto-discover pricing problems

**Timeline:** Blocking but lower priority than Gaps 1–4. Workaround is temporary (rewrite to efficient SQL once Tier 1 is fixed).

---

### 🟡 **Gap 6: No Watermark Initialization (OPERATIONAL)**

**Problem:** The `tier_watermark` table is designed to track the last successfully processed date for each tier (`daily`, `weekly`) but is **not created or seeded**.

**What should happen on first deploy:**

```sql
INSERT INTO pricing.tier_watermark (tier_name, last_processed_date)
  VALUES ('daily', '1970-01-01'), ('weekly', '1970-01-01');
```

**Impact:**
- `refresh_daily_prices()` and `archive_to_weekly()` will fail on first call (no watermark row to read)
- Manual backfill requires passing explicit date ranges (`p_from`, `p_to`) instead of resuming from watermark
- Crash recovery is not possible (no state to resume from)

**Workaround:** Manual initialization or explicit date ranges.

---

### 🟢 **Gap 7: Python Service Layer Not Wired (INTEGRATION)**

**Problem:** The procedures exist but no Python service code calls them.

**Missing:**
- `PriceRepository.call_refresh_daily_prices()` — analogous to existing `call_load_stage_from_raw()`, `call_resolve_price_rejects()`, etc.
- `PriceRepository.call_archive_to_weekly()` — similar wrapper
- Celery beat tasks in `worker/tasks/pipelines.py` or `celeryconfig.py` to invoke these services

**Impact:**
- Tier 2/3 procedures have no way to be called from the pipeline
- Manual SQL invocation required for backfill and maintenance

**Workaround:** Until Python service layer is built, procedures can be called manually or via `automana-run`:

```bash
# Manual refresh (all unprocessed dates since last watermark)
automana-run -raw "CALL pricing.refresh_daily_prices();"

# Or with explicit range
automana-run -raw "CALL pricing.refresh_daily_prices('2026-01-01', '2026-04-30');"
```

---

## Dependency Chain

```
Fix Gap 1 (MTGStock 0% link rate)
  ↓
Tier 1 has data (price_observation)
  ↓
Deploy Tier 2 (Gap 2) + Fix pricing report queries (Gap 5)
  ↓
Tier 2 has data (print_price_daily)
  ↓
Deploy Tier 3 (Gap 3) + Wire Celery beat + Build Python service layer (Gap 7)
  ↓
Full 3-tier system operational
```

---

## Remediation Plan

### Immediate (Blocking User-Facing Data)

| Gap | Action | Owner | Timeline | Blocker |
|-----|--------|-------|----------|---------|
| 1 | Implement Fix 2 + Fix 3 from MTGSTOCK_REJECT_ANALYSIS.md | data team | TBD | Yes |
| 1 | Re-run MTGStock pipeline with fixes | data team | TBD | Yes |
| 2 | Deploy migration_18 (`print_price_daily` table + procedures) | DBA | ASAP after Gap 1 data exists | No (Gap 1) |
| 4 | Deploy migration_18 (`print_price_latest` snapshot table) | DBA | Same as Gap 2 | No (Gap 1) |
| 6 | Seed `tier_watermark` table | DBA | Same as Gap 2 | No |

### Short Term (Fixing Observability)

| Gap | Action | Owner | Timeline | Notes |
|-----|--------|-------|----------|-------|
| 5 | Rewrite pricing metrics to use time-bounded windows | backend team | 1 day | Critical for health checks |
| 7 | Add `PriceRepository.call_refresh_daily_prices()` wrapper | backend team | 1 day | ~30 lines of code |
| 7 | Add `PriceRepository.call_archive_to_weekly()` wrapper | backend team | 1 day | ~30 lines of code |

### Medium Term (Automating Tier 2/3)

| Gap | Action | Owner | Timeline | Notes |
|-----|--------|-------|----------|-------|
| 7 | Wire Celery beat for daily `refresh_daily_prices()` | backend team | 1 day | After Python wrapper |
| 7 | Wire Celery beat for monthly `archive_to_weekly()` | backend team | 1 day | After Python wrapper |
| 2 | Backfill Tier 2 from historical Tier 1 data | data team | ~2 hours | After Gap 1 + Gap 2 deployed |
| 3 | Backfill Tier 3 from historical Tier 2 data | data team | ~1 hour | After Tier 2 backfill |

### Long Term (Operational Excellence)

| Gap | Action | Owner | Timeline | Notes |
|-----|--------|-------|----------|-------|
| 5 | Add more granular metrics (e.g., per-source freshness breakdown) | backend team | 1 week | Depends on Gap 5 fix |
| — | Add indexes on Tier 2/3 for common query patterns | DBA | 1 week | After backfill to test cardinality |
| — | Document Tier 2/3 query patterns for analytics | docs team | 1 week | UI/API consumption guide |

---

## Query Patterns by Tier

### Tier 1 (Raw observations)

```sql
-- Niche: audit a specific scrape
SELECT * FROM pricing.price_observation
WHERE source_product_id = 123 AND ts_date = '2026-04-25'
ORDER BY data_provider_id;
```

**Current use:** Mostly internal validation. Raw data seldom queried directly.

---

### Tier 2 (Daily aggregates — PRIMARY for UI/API)

```sql
-- Chart: Lightning Bolt price history on TCGplayer, last 90 days
SELECT price_date, list_avg_cents, sold_avg_cents, n_providers
FROM pricing.print_price_daily
WHERE card_version_id = '...' AND source_id = 1 AND finish_id = 1
  AND price_date >= CURRENT_DATE - 90
ORDER BY price_date DESC;

-- Current price lookup
SELECT list_avg_cents, list_low_cents
FROM pricing.print_price_latest
WHERE card_version_id = '...' AND source_id = 1 AND finish_id = 1;
```

**Expected use:** ~99% of all price queries (frontend, API, analytics).

---

### Tier 3 (Weekly archive — LONG-TERM TRENDS)

```sql
-- Trend: average price of card over 5 years, weekly
SELECT price_week, AVG(list_avg_cents) as avg_price
FROM pricing.print_price_weekly
WHERE card_version_id = '...' AND source_id IN (1, 2, 3)  -- TCGplayer, CardMarket, CK
GROUP BY price_week
ORDER BY price_week DESC;
```

**Expected use:** Historical analysis, trend detection, volatility studies.

---

## Testing Checklist (Post-Fix)

- [ ] `pricing.price_observation` has > 1M rows (post-Gap 1 fix)
- [ ] `CALL pricing.refresh_daily_prices()` completes without error (post-migration_18)
- [ ] `pricing.print_price_daily` has data for all dates since Tier 1 backfill (post-Gap 2)
- [ ] `pricing.print_price_latest` returns O(1) results for a known card/source
- [ ] `CALL pricing.archive_to_weekly()` completes without error (post-migration_18)
- [ ] `pricing.print_price_weekly` has weekly rollups for old data (post-Gap 3)
- [ ] All `pricing_report` metrics pass (post-Gap 5 fix)
- [ ] Celery beat tasks fire daily (Tier 2) and monthly (Tier 3) without errors
- [ ] API `/prices` endpoint returns data from Tier 2 instead of scanning Tier 1

---

## Related Documentation

- [`docs/MTGSTOCK_PIPELINE.md`](docs/MTGSTOCK_PIPELINE.md) — end-to-end pipeline flow and stages
- [`docs/HEALTH_METRICS.md`](docs/HEALTH_METRICS.md) — pricing metrics and health checks
- [`docs/PIPELINE_TECHNICAL_DEBT.md`](docs/PIPELINE_TECHNICAL_DEBT.md) — current open issues and fixes
- [`src/automana/database/SQL/migrations/migration_18_pricing_tiers.sql`](src/automana/database/SQL/migrations/migration_18_pricing_tiers.sql) — full Tier 2/3 DDL and procedures
- [`src/automana/database/SQL/schemas/06_prices.sql`](src/automana/database/SQL/schemas/06_prices.sql) — reference schema definitions (may be out of sync with migration)

---

## Summary Table

| Layer | Status | Severity | Data | Deployed | Wired | Notes |
|-------|--------|----------|------|----------|-------|-------|
| **Tier 1** | Broken | 🔴 Critical | 0 rows | ✅ | ✅ | 0% link rate from MTGStock |
| **Tier 2** | Missing | 🔴 Critical | — | ❌ | ❌ | migration_18 ready; blocked on Tier 1 |
| **Tier 3** | Missing | 🔴 Critical | — | ❌ | ❌ | migration_18 ready; blocked on Tier 2 |
| **Snapshot** | Missing | 🔴 Critical | — | ❌ | ❌ | migration_18 ready; enables fast queries |
| **Watermark** | Missing | 🟡 Important | — | ❌ | ❌ | Needed for crash recovery |
| **Metrics** | Failing | 🟡 Important | — | ✅ | ❌ | Timeouts on hypertable scans |
| **Service layer** | Missing | 🟡 Important | — | — | ❌ | Python wrappers for procedures |
