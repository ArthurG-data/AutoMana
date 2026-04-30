# Pricing Tier 2 / Tier 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver migration 18 — replace the broken `print_price_daily` stub and create `print_price_weekly`, `print_price_latest`, and `tier_watermark` as TimescaleDB-backed tables with two stored procedures (`refresh_daily_prices`, `archive_to_weekly`) and integrity checks.

**Architecture:** Pure SQL migration. Tier 2 (`print_price_daily`) and tier 3 (`print_price_weekly`) are TimescaleDB hypertables that roll up from tier 1 (`price_observation`) via two stored procedures. A snapshot table (`print_price_latest`) makes current-price lookups O(1). A watermark table makes procedures resumable after crashes. No Python changes in this migration.

**Tech Stack:** PostgreSQL 15+, TimescaleDB, plpgsql stored procedures. Dev environment: `dcdev-automana` compose stack, `psql` against port 5433.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `src/automana/database/SQL/migrations/migration_18_pricing_tiers.sql` | **Create** | Full migration: DDL + hypertable setup + procedures + grants |
| `src/automana/database/SQL/schemas/06_prices.sql` | **Modify** | Replace tier 2/3 DDL stubs so fresh rebuilds match migration 18 |
| `src/automana/database/SQL/maintenance/pricing_integrity_checks.sql` | **Modify** | Add checks for new tables and watermark staleness |

---

## Task 1: Write the verification test script (run before migration — expect failures)

This script checks post-conditions. Run it first to see everything fail, then again after the migration to confirm everything passes. Pure read-only SQL — safe to run at any time.

**Files:**
- Create: `src/automana/database/SQL/maintenance/verify_migration_18.sql`

- [ ] **Step 1: Create the verification script**

```sql
-- verify_migration_18.sql
-- Run BEFORE migration to confirm failures, AFTER to confirm passes.
-- Every check outputs: check_name, status ('pass'/'fail'), detail

SELECT 'print_price_daily_exists' AS check_name,
       CASE WHEN EXISTS (
           SELECT 1 FROM pg_class c
           JOIN pg_namespace n ON n.oid = c.relnamespace
           WHERE n.nspname = 'pricing' AND c.relname = 'print_price_daily'
       ) THEN 'pass' ELSE 'fail' END AS status,
       'table must exist' AS detail

UNION ALL

SELECT 'print_price_daily_has_source_id',
       CASE WHEN EXISTS (
           SELECT 1 FROM information_schema.columns
           WHERE table_schema = 'pricing'
             AND table_name   = 'print_price_daily'
             AND column_name  = 'source_id'
       ) THEN 'pass' ELSE 'fail' END,
       'source_id column required (old stub lacked it)'

UNION ALL

SELECT 'print_price_daily_no_p25',
       CASE WHEN NOT EXISTS (
           SELECT 1 FROM information_schema.columns
           WHERE table_schema = 'pricing'
             AND table_name   = 'print_price_daily'
             AND column_name  = 'p25_price'
       ) THEN 'pass' ELSE 'fail' END,
       'p25_price must NOT exist (dropped)'

UNION ALL

SELECT 'print_price_daily_is_hypertable',
       CASE WHEN EXISTS (
           SELECT 1 FROM timescaledb_information.hypertables
           WHERE hypertable_schema = 'pricing'
             AND hypertable_name   = 'print_price_daily'
       ) THEN 'pass' ELSE 'fail' END,
       'must be a TimescaleDB hypertable'

UNION ALL

SELECT 'print_price_weekly_exists',
       CASE WHEN EXISTS (
           SELECT 1 FROM pg_class c
           JOIN pg_namespace n ON n.oid = c.relnamespace
           WHERE n.nspname = 'pricing' AND c.relname = 'print_price_weekly'
       ) THEN 'pass' ELSE 'fail' END,
       'table must exist'

UNION ALL

SELECT 'print_price_weekly_has_n_days',
       CASE WHEN EXISTS (
           SELECT 1 FROM information_schema.columns
           WHERE table_schema = 'pricing'
             AND table_name   = 'print_price_weekly'
             AND column_name  = 'n_days'
       ) THEN 'pass' ELSE 'fail' END,
       'n_days column required'

UNION ALL

SELECT 'print_price_latest_exists',
       CASE WHEN EXISTS (
           SELECT 1 FROM pg_class c
           JOIN pg_namespace n ON n.oid = c.relnamespace
           WHERE n.nspname = 'pricing' AND c.relname = 'print_price_latest'
       ) THEN 'pass' ELSE 'fail' END,
       'table must exist'

UNION ALL

SELECT 'tier_watermark_seeded',
       CASE WHEN (
           SELECT COUNT(*) FROM pricing.tier_watermark
           WHERE tier_name IN ('daily', 'weekly')
       ) = 2 THEN 'pass' ELSE 'fail' END,
       'must have 2 rows: daily + weekly'

UNION ALL

SELECT 'refresh_daily_prices_exists',
       CASE WHEN EXISTS (
           SELECT 1 FROM pg_proc p
           JOIN pg_namespace n ON n.oid = p.pronamespace
           WHERE n.nspname = 'pricing'
             AND p.proname = 'refresh_daily_prices'
       ) THEN 'pass' ELSE 'fail' END,
       'procedure must exist'

UNION ALL

SELECT 'archive_to_weekly_exists',
       CASE WHEN EXISTS (
           SELECT 1 FROM pg_proc p
           JOIN pg_namespace n ON n.oid = p.pronamespace
           WHERE n.nspname = 'pricing'
             AND p.proname = 'archive_to_weekly'
       ) THEN 'pass' ELSE 'fail' END,
       'procedure must exist'

ORDER BY check_name;
```

- [ ] **Step 2: Run the script — confirm pre-migration state**

```bash
psql -h localhost -p 5433 -U app_admin -d automana \
  -f src/automana/database/SQL/maintenance/verify_migration_18.sql
```

Expected before migration:
- `tier_watermark_seeded` will **error** (not just fail) because the table doesn't exist yet — that is expected and fine; psql will print the error and continue.
- All other checks should show `status = 'fail'`.
- `print_price_daily_exists` may show `pass` on the live DB (old stub was applied) — that is fine; `print_price_daily_has_source_id` and `print_price_daily_no_p25` will still show `fail`.

- [ ] **Step 3: Commit the verification script**

```bash
git add src/automana/database/SQL/maintenance/verify_migration_18.sql
git commit -m "test(pricing): add migration-18 pre/post verification script"
```

---

## Task 2: Write migration_18 — DDL (tables + hypertable setup)

**Files:**
- Create: `src/automana/database/SQL/migrations/migration_18_pricing_tiers.sql`

- [ ] **Step 1: Create the migration file with the DDL section**

```sql
-- Migration 18: Pricing tier 2/3 — source-preserving daily/weekly rollup
--
-- Replaces the unpopulated print_price_daily stub (wrong grain, no source_id,
-- had p25/p75) and creates print_price_weekly (never applied to live DB),
-- print_price_latest (current-price snapshot), and tier_watermark (resumable
-- procedure state). Both tier 2 and tier 3 are TimescaleDB hypertables.
--
-- Safe to re-run for print_price_weekly / print_price_latest / tier_watermark
-- (CREATE IF NOT EXISTS). print_price_daily uses DROP + recreate because the
-- old stub has the wrong schema; the table was never populated.
--
-- See docs/superpowers/specs/2026-04-30-pricing-tier2-tier3-design.md

BEGIN;

-- =========================================================================
-- 1. print_price_daily (Tier 2)
--    DROP + recreate: old stub had wrong grain (no source_id, had p25/p75).
--    Table was defined in 06_prices.sql but never populated, so no data loss.
-- =========================================================================
DROP TABLE IF EXISTS pricing.print_price_daily CASCADE;

CREATE TABLE pricing.print_price_daily (
    price_date          DATE        NOT NULL,
    card_version_id     UUID        NOT NULL
        REFERENCES card_catalog.card_version(card_version_id),
    source_id           SMALLINT    NOT NULL
        REFERENCES pricing.price_source(source_id),
    transaction_type_id INTEGER     NOT NULL
        REFERENCES pricing.transaction_type(transaction_type_id),
    finish_id           SMALLINT    NOT NULL
        DEFAULT pricing.default_finish_id()
        REFERENCES pricing.card_finished(finish_id),
    condition_id        SMALLINT    NOT NULL
        DEFAULT pricing.default_condition_id()
        REFERENCES pricing.card_condition(condition_id),
    language_id         SMALLINT    NOT NULL
        DEFAULT card_catalog.default_language_id()
        REFERENCES card_catalog.language_ref(language_id),

    list_low_cents      INTEGER,
    list_avg_cents      INTEGER,
    sold_avg_cents      INTEGER,
    n_providers         SMALLINT,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT print_price_daily_pk PRIMARY KEY (
        price_date, card_version_id, source_id,
        transaction_type_id, finish_id, condition_id, language_id
    ),
    CONSTRAINT chk_ppd_prices_nonneg CHECK (
        (list_low_cents  IS NULL OR list_low_cents  >= 0) AND
        (list_avg_cents  IS NULL OR list_avg_cents  >= 0) AND
        (sold_avg_cents  IS NULL OR sold_avg_cents  >= 0)
    )
    -- chk_ppd_low_le_avg intentionally omitted: MIN(list_low) vs AVG(list_avg)
    -- across providers does not guarantee low <= avg.
);

SELECT create_hypertable(
    'pricing.print_price_daily',
    by_range('price_date', INTERVAL '7 days'),
    if_not_exists => TRUE
);

ALTER TABLE pricing.print_price_daily
    SET (
        timescaledb.compress,
        timescaledb.compress_segmentby = 'card_version_id, source_id, finish_id',
        timescaledb.compress_orderby   = 'price_date DESC'
    );

SELECT add_compression_policy(
    'pricing.print_price_daily',
    INTERVAL '30 days',
    if_not_exists => TRUE
);

-- =========================================================================
-- 2. print_price_weekly (Tier 3)
--    Never applied to the live DB (schema file had a syntax error and a
--    "never applied" comment). CREATE IF NOT EXISTS is safe.
-- =========================================================================
DROP TABLE IF EXISTS pricing.print_price_weekly CASCADE;

CREATE TABLE IF NOT EXISTS pricing.print_price_weekly (
    price_week          DATE        NOT NULL,
    card_version_id     UUID        NOT NULL
        REFERENCES card_catalog.card_version(card_version_id),
    source_id           SMALLINT    NOT NULL
        REFERENCES pricing.price_source(source_id),
    transaction_type_id INTEGER     NOT NULL
        REFERENCES pricing.transaction_type(transaction_type_id),
    finish_id           SMALLINT    NOT NULL
        DEFAULT pricing.default_finish_id()
        REFERENCES pricing.card_finished(finish_id),
    condition_id        SMALLINT    NOT NULL
        DEFAULT pricing.default_condition_id()
        REFERENCES pricing.card_condition(condition_id),
    language_id         SMALLINT    NOT NULL
        DEFAULT card_catalog.default_language_id()
        REFERENCES card_catalog.language_ref(language_id),

    list_low_cents      INTEGER,
    list_avg_cents      INTEGER,
    sold_avg_cents      INTEGER,
    n_days              SMALLINT,
    n_providers         SMALLINT,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT print_price_weekly_pk PRIMARY KEY (
        price_week, card_version_id, source_id,
        transaction_type_id, finish_id, condition_id, language_id
    ),
    CONSTRAINT chk_ppw_prices_nonneg CHECK (
        (list_low_cents  IS NULL OR list_low_cents  >= 0) AND
        (list_avg_cents  IS NULL OR list_avg_cents  >= 0) AND
        (sold_avg_cents  IS NULL OR sold_avg_cents  >= 0)
    ),
    CONSTRAINT chk_ppw_n_days CHECK (n_days IS NULL OR (n_days >= 1 AND n_days <= 7))
);

COMMENT ON COLUMN pricing.print_price_weekly.price_week IS
    'Monday of the ISO week (DATE_TRUNC(''week'', price_date))';

SELECT create_hypertable(
    'pricing.print_price_weekly',
    by_range('price_week', INTERVAL '28 days'),
    if_not_exists => TRUE
);

ALTER TABLE pricing.print_price_weekly
    SET (
        timescaledb.compress,
        timescaledb.compress_segmentby = 'card_version_id, source_id, finish_id',
        timescaledb.compress_orderby   = 'price_week DESC'
    );

SELECT add_compression_policy(
    'pricing.print_price_weekly',
    INTERVAL '7 days',
    if_not_exists => TRUE
);

-- =========================================================================
-- 3. print_price_latest — current-price snapshot (plain table, not hypertable)
-- =========================================================================
CREATE TABLE IF NOT EXISTS pricing.print_price_latest (
    card_version_id     UUID        NOT NULL
        REFERENCES card_catalog.card_version(card_version_id),
    source_id           SMALLINT    NOT NULL
        REFERENCES pricing.price_source(source_id),
    transaction_type_id INTEGER     NOT NULL
        REFERENCES pricing.transaction_type(transaction_type_id),
    finish_id           SMALLINT    NOT NULL
        DEFAULT pricing.default_finish_id()
        REFERENCES pricing.card_finished(finish_id),
    condition_id        SMALLINT    NOT NULL
        DEFAULT pricing.default_condition_id()
        REFERENCES pricing.card_condition(condition_id),
    language_id         SMALLINT    NOT NULL
        DEFAULT card_catalog.default_language_id()
        REFERENCES card_catalog.language_ref(language_id),

    price_date          DATE        NOT NULL,
    list_low_cents      INTEGER,
    list_avg_cents      INTEGER,
    sold_avg_cents      INTEGER,
    n_providers         SMALLINT,

    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT print_price_latest_pk PRIMARY KEY (
        card_version_id, source_id,
        transaction_type_id, finish_id, condition_id, language_id
    )
);

-- =========================================================================
-- 4. tier_watermark — one row per tier, tracks last successfully processed date
-- =========================================================================
CREATE TABLE IF NOT EXISTS pricing.tier_watermark (
    tier_name           TEXT        NOT NULL PRIMARY KEY,
    last_processed_date DATE        NOT NULL,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO pricing.tier_watermark (tier_name, last_processed_date) VALUES
    ('daily',  '1970-01-01'),
    ('weekly', '1970-01-01')
ON CONFLICT (tier_name) DO NOTHING;

-- =========================================================================
-- 5. Indexes
-- =========================================================================

-- print_price_daily
CREATE INDEX IF NOT EXISTS idx_ppd_card_source_date
    ON pricing.print_price_daily (card_version_id, source_id, price_date DESC);

CREATE INDEX IF NOT EXISTS idx_ppd_date_dims
    ON pricing.print_price_daily (price_date, finish_id, condition_id, language_id);

-- print_price_weekly
CREATE INDEX IF NOT EXISTS idx_ppw_card_source_week
    ON pricing.print_price_weekly (card_version_id, source_id, price_week DESC);

CREATE INDEX IF NOT EXISTS idx_ppw_week_dims
    ON pricing.print_price_weekly (price_week, finish_id, condition_id, language_id);

-- print_price_latest
CREATE INDEX IF NOT EXISTS idx_ppl_card_source
    ON pricing.print_price_latest (card_version_id, source_id);

COMMIT;
```

- [ ] **Step 2: Apply DDL section to dev DB and verify tables exist**

```bash
psql -h localhost -p 5433 -U app_admin -d automana \
  -f src/automana/database/SQL/migrations/migration_18_pricing_tiers.sql
```

Expected output (no errors) includes lines like:
```
CREATE TABLE
SELECT 1
ALTER TABLE
SELECT 1
...
INSERT 0 2
CREATE INDEX
```

- [ ] **Step 3: Spot-check structure**

```bash
psql -h localhost -p 5433 -U app_admin -d automana -c \
  "SELECT hypertable_name, num_chunks FROM timescaledb_information.hypertables WHERE hypertable_schema = 'pricing' ORDER BY hypertable_name;"
```

Expected: `print_price_daily` and `print_price_weekly` appear (plus existing `price_observation`).

```bash
psql -h localhost -p 5433 -U app_admin -d automana -c \
  "SELECT tier_name, last_processed_date FROM pricing.tier_watermark;"
```

Expected:
```
 tier_name | last_processed_date
-----------+---------------------
 daily     | 1970-01-01
 weekly    | 1970-01-01
```

---

## Task 3: Add `refresh_daily_prices` procedure to the migration

**Files:**
- Modify: `src/automana/database/SQL/migrations/migration_18_pricing_tiers.sql` (append after the COMMIT in Task 2 — or restructure as one file; see step below)

- [ ] **Step 1: Append the procedure to the migration file**

Open `migration_18_pricing_tiers.sql`. After the final `COMMIT;` from Task 2, append:

```sql
-- =========================================================================
-- 6. refresh_daily_prices — populate tier 2 + print_price_latest from tier 1
-- =========================================================================
CREATE OR REPLACE PROCEDURE pricing.refresh_daily_prices(
    p_from DATE DEFAULT NULL,
    p_to   DATE DEFAULT NULL
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_from         DATE;
    v_to           DATE;
    v_start        DATE;
    v_end          DATE;
    v_batch_days   INT  := 30;
    v_ok           BOOLEAN;
    cur_rows       BIGINT;
    total_daily    BIGINT := 0;
    total_latest   BIGINT := 0;
BEGIN
    -- -----------------------------------------------------------------------
    -- Resolve date range
    -- -----------------------------------------------------------------------
    IF p_from IS NULL THEN
        SELECT last_processed_date + 1
        INTO   v_from
        FROM   pricing.tier_watermark
        WHERE  tier_name = 'daily';

        IF v_from IS NULL THEN
            RAISE EXCEPTION 'tier_watermark has no daily row; re-seed or pass p_from explicitly';
        END IF;
    ELSE
        v_from := p_from;
    END IF;

    v_to := COALESCE(p_to, CURRENT_DATE - 1);

    IF v_from > v_to THEN
        RAISE NOTICE 'refresh_daily_prices: nothing to do (from=% > to=%)', v_from, v_to;
        RETURN;
    END IF;

    RAISE NOTICE 'refresh_daily_prices: processing % to %', v_from, v_to;

    -- -----------------------------------------------------------------------
    -- Batch loop (30-day windows, same pattern as load_staging_prices_batched)
    -- -----------------------------------------------------------------------
    v_start := v_from;
    WHILE v_start <= v_to LOOP
        v_end := LEAST(v_start + (v_batch_days - 1), v_to);
        v_ok  := FALSE;

        BEGIN
            SET LOCAL work_mem                        = '512MB';
            SET LOCAL maintenance_work_mem            = '1GB';
            SET LOCAL synchronous_commit              = off;
            SET LOCAL max_parallel_workers_per_gather = 4;

            -- Build the daily aggregate from tier 1 for this batch window.
            -- JOIN path: price_observation → source_product → mtg_card_products
            DROP TABLE IF EXISTS _daily_batch;
            CREATE TEMP TABLE _daily_batch ON COMMIT DROP AS
            SELECT
                po.ts_date                                      AS price_date,
                mcp.card_version_id,
                sp.source_id,
                po.price_type_id                               AS transaction_type_id,
                po.finish_id,
                po.condition_id,
                po.language_id,
                MIN(po.list_low_cents)::INTEGER                AS list_low_cents,
                AVG(po.list_avg_cents)::INTEGER                AS list_avg_cents,
                AVG(po.sold_avg_cents)::INTEGER                AS sold_avg_cents,
                COUNT(DISTINCT po.data_provider_id)::SMALLINT  AS n_providers
            FROM  pricing.price_observation po
            JOIN  pricing.source_product    sp  ON sp.source_product_id = po.source_product_id
            JOIN  pricing.mtg_card_products mcp ON mcp.product_id       = sp.product_id
            WHERE po.ts_date >= v_start
              AND po.ts_date <= v_end
              AND NOT (po.list_low_cents IS NULL
                   AND po.list_avg_cents IS NULL
                   AND po.sold_avg_cents IS NULL)
            GROUP BY
                po.ts_date,
                mcp.card_version_id, sp.source_id,
                po.price_type_id, po.finish_id, po.condition_id, po.language_id;

            -- Upsert into print_price_daily
            INSERT INTO pricing.print_price_daily (
                price_date, card_version_id, source_id, transaction_type_id,
                finish_id, condition_id, language_id,
                list_low_cents, list_avg_cents, sold_avg_cents, n_providers
            )
            SELECT
                price_date, card_version_id, source_id, transaction_type_id,
                finish_id, condition_id, language_id,
                list_low_cents, list_avg_cents, sold_avg_cents, n_providers
            FROM _daily_batch
            ON CONFLICT (price_date, card_version_id, source_id,
                         transaction_type_id, finish_id, condition_id, language_id)
            DO UPDATE SET
                list_low_cents = EXCLUDED.list_low_cents,
                list_avg_cents = EXCLUDED.list_avg_cents,
                sold_avg_cents = EXCLUDED.sold_avg_cents,
                n_providers    = EXCLUDED.n_providers,
                updated_at     = now();

            GET DIAGNOSTICS cur_rows = ROW_COUNT;
            total_daily := total_daily + cur_rows;

            -- Upsert into print_price_latest — only advance when newer
            INSERT INTO pricing.print_price_latest (
                card_version_id, source_id, transaction_type_id,
                finish_id, condition_id, language_id,
                price_date, list_low_cents, list_avg_cents, sold_avg_cents, n_providers
            )
            SELECT
                card_version_id, source_id, transaction_type_id,
                finish_id, condition_id, language_id,
                price_date, list_low_cents, list_avg_cents, sold_avg_cents, n_providers
            FROM _daily_batch
            ON CONFLICT (card_version_id, source_id, transaction_type_id,
                         finish_id, condition_id, language_id)
            DO UPDATE SET
                price_date     = EXCLUDED.price_date,
                list_low_cents = EXCLUDED.list_low_cents,
                list_avg_cents = EXCLUDED.list_avg_cents,
                sold_avg_cents = EXCLUDED.sold_avg_cents,
                n_providers    = EXCLUDED.n_providers,
                updated_at     = now()
            WHERE EXCLUDED.price_date >= pricing.print_price_latest.price_date;

            GET DIAGNOSTICS cur_rows = ROW_COUNT;
            total_latest := total_latest + cur_rows;

            RAISE NOTICE 'refresh_daily_prices: batch % to %: daily=%, latest_updated=%',
                         v_start, v_end, total_daily, total_latest;
            v_ok := TRUE;

        EXCEPTION WHEN OTHERS THEN
            RAISE WARNING 'refresh_daily_prices: batch % to % failed: % (SQLSTATE %)',
                          v_start, v_end, SQLERRM, SQLSTATE;
            v_ok := FALSE;
        END;

        IF v_ok THEN
            COMMIT;
            -- Advance watermark per batch so a crash mid-run is resumable.
            UPDATE pricing.tier_watermark
            SET    last_processed_date = v_end,
                   updated_at          = now()
            WHERE  tier_name = 'daily';
            COMMIT;
        ELSE
            ROLLBACK;
        END IF;

        v_start := v_end + 1;
    END LOOP;

    RAISE NOTICE 'refresh_daily_prices: done. total daily=%, total latest_updated=%',
                 total_daily, total_latest;
END;
$$;
```

- [ ] **Step 2: Apply the updated migration file to dev DB**

```bash
psql -h localhost -p 5433 -U app_admin -d automana \
  -f src/automana/database/SQL/migrations/migration_18_pricing_tiers.sql
```

Expected: `CREATE PROCEDURE` near the end, no errors.

- [ ] **Step 3: Smoke-test the procedure with a narrow date range**

Pick a 3-day window near the start of your actual price_observation data:

```bash
psql -h localhost -p 5433 -U app_admin -d automana -c \
  "CALL pricing.refresh_daily_prices('2024-01-01', '2024-01-03');"
```

Expected NOTICE output (counts will vary):
```
NOTICE:  refresh_daily_prices: processing 2024-01-01 to 2024-01-03
NOTICE:  refresh_daily_prices: batch 2024-01-01 to 2024-01-03: daily=NNN, latest_updated=NNN
NOTICE:  refresh_daily_prices: done. total daily=NNN, total latest_updated=NNN
```

- [ ] **Step 4: Verify rows were inserted**

```bash
psql -h localhost -p 5433 -U app_admin -d automana -c "
SELECT
    MIN(price_date) AS min_date,
    MAX(price_date) AS max_date,
    COUNT(*)        AS rows
FROM pricing.print_price_daily;
"
```

Expected: 3 distinct dates (2024-01-01 to 2024-01-03), row count > 0.

```bash
psql -h localhost -p 5433 -U app_admin -d automana -c "
SELECT COUNT(*) FROM pricing.print_price_latest;
"
```

Expected: count > 0.

```bash
psql -h localhost -p 5433 -U app_admin -d automana -c "
SELECT tier_name, last_processed_date FROM pricing.tier_watermark;
"
```

Expected: `daily` row shows `2024-01-03`.

- [ ] **Step 5: Verify watermark-based resume (call with no args)**

```bash
psql -h localhost -p 5433 -U app_admin -d automana -c \
  "CALL pricing.refresh_daily_prices('2024-01-04', '2024-01-05');"
```

Then verify watermark advanced to `2024-01-05`, and `print_price_daily` has rows for those two dates.

---

## Task 4: Add `archive_to_weekly` procedure to the migration

**Files:**
- Modify: `src/automana/database/SQL/migrations/migration_18_pricing_tiers.sql` (append)

- [ ] **Step 1: Append the procedure**

After the `refresh_daily_prices` procedure in the migration file, append:

```sql
-- =========================================================================
-- 7. archive_to_weekly — roll up tier 2 rows older than N years into tier 3
-- =========================================================================
CREATE OR REPLACE PROCEDURE pricing.archive_to_weekly(
    p_older_than INTERVAL DEFAULT '5 years'
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_cutoff        DATE;
    v_min_date      DATE;
    v_max_date      DATE;
    v_start         DATE;
    v_end           DATE;
    v_batch_weeks   INT  := 4;
    v_ok            BOOLEAN;
    cur_archived    BIGINT;
    cur_deleted     BIGINT;
    total_archived  BIGINT := 0;
    total_deleted   BIGINT := 0;
BEGIN
    -- Cutoff is floored to the previous Monday so we always archive complete weeks.
    v_cutoff := DATE_TRUNC('week', CURRENT_DATE - p_older_than)::DATE;

    SELECT MIN(price_date), MAX(price_date)
    INTO   v_min_date, v_max_date
    FROM   pricing.print_price_daily
    WHERE  price_date < v_cutoff;

    IF v_min_date IS NULL THEN
        RAISE NOTICE 'archive_to_weekly: no data older than % to archive', v_cutoff;
        RETURN;
    END IF;

    RAISE NOTICE 'archive_to_weekly: archiving % to % (cutoff=%, older_than=%)',
                 v_min_date, v_max_date, v_cutoff, p_older_than;

    v_start := DATE_TRUNC('week', v_min_date)::DATE;

    WHILE v_start < v_cutoff LOOP
        -- Batch = v_batch_weeks × 7 days, capped at cutoff.
        v_end := LEAST(v_start + (v_batch_weeks * 7 - 1), v_cutoff - 1);
        v_ok  := FALSE;

        BEGIN
            SET LOCAL work_mem             = '512MB';
            SET LOCAL maintenance_work_mem = '1GB';
            SET LOCAL synchronous_commit   = off;

            -- Aggregate tier 2 → tier 3 for this batch window.
            DROP TABLE IF EXISTS _weekly_batch;
            CREATE TEMP TABLE _weekly_batch ON COMMIT DROP AS
            SELECT
                DATE_TRUNC('week', price_date)::DATE         AS price_week,
                card_version_id,
                source_id,
                transaction_type_id,
                finish_id,
                condition_id,
                language_id,
                MIN(list_low_cents)::INTEGER                 AS list_low_cents,
                AVG(list_avg_cents)::INTEGER                 AS list_avg_cents,
                AVG(sold_avg_cents)::INTEGER                 AS sold_avg_cents,
                COUNT(DISTINCT price_date)::SMALLINT         AS n_days,
                MAX(n_providers)::SMALLINT                   AS n_providers
            FROM  pricing.print_price_daily
            WHERE price_date >= v_start
              AND price_date <= v_end
            GROUP BY
                DATE_TRUNC('week', price_date),
                card_version_id, source_id, transaction_type_id,
                finish_id, condition_id, language_id;

            -- Upsert into print_price_weekly (idempotent re-runs are safe)
            INSERT INTO pricing.print_price_weekly (
                price_week, card_version_id, source_id, transaction_type_id,
                finish_id, condition_id, language_id,
                list_low_cents, list_avg_cents, sold_avg_cents, n_days, n_providers
            )
            SELECT
                price_week, card_version_id, source_id, transaction_type_id,
                finish_id, condition_id, language_id,
                list_low_cents, list_avg_cents, sold_avg_cents, n_days, n_providers
            FROM _weekly_batch
            ON CONFLICT (price_week, card_version_id, source_id,
                         transaction_type_id, finish_id, condition_id, language_id)
            DO UPDATE SET
                list_low_cents = EXCLUDED.list_low_cents,
                list_avg_cents = EXCLUDED.list_avg_cents,
                sold_avg_cents = EXCLUDED.sold_avg_cents,
                n_days         = EXCLUDED.n_days,
                n_providers    = EXCLUDED.n_providers,
                updated_at     = now();

            GET DIAGNOSTICS cur_archived = ROW_COUNT;
            total_archived := total_archived + cur_archived;

            -- Delete the source daily rows only after a successful upsert.
            DELETE FROM pricing.print_price_daily
            WHERE price_date >= v_start
              AND price_date <= v_end;

            GET DIAGNOSTICS cur_deleted = ROW_COUNT;
            total_deleted := total_deleted + cur_deleted;

            RAISE NOTICE 'archive_to_weekly: batch % to %: archived=%, deleted=%',
                         v_start, v_end, cur_archived, cur_deleted;
            v_ok := TRUE;

        EXCEPTION WHEN OTHERS THEN
            RAISE WARNING 'archive_to_weekly: batch % to % failed: % (SQLSTATE %)',
                          v_start, v_end, SQLERRM, SQLSTATE;
            v_ok := FALSE;
        END;

        IF v_ok THEN
            COMMIT;
            UPDATE pricing.tier_watermark
            SET    last_processed_date = v_end,
                   updated_at          = now()
            WHERE  tier_name = 'weekly';
            COMMIT;
        ELSE
            ROLLBACK;
        END IF;

        v_start := v_end + 1;
    END LOOP;

    RAISE NOTICE 'archive_to_weekly: done. total archived=%, total deleted=%',
                 total_archived, total_deleted;
END;
$$;
```

- [ ] **Step 2: Apply the updated migration to dev DB**

```bash
psql -h localhost -p 5433 -U app_admin -d automana \
  -f src/automana/database/SQL/migrations/migration_18_pricing_tiers.sql
```

Expected: `CREATE PROCEDURE` for `archive_to_weekly`, no errors.

- [ ] **Step 3: Smoke-test `archive_to_weekly` with synthetic old data**

Insert two rows of fake daily data dated 6 years ago, then archive them:

```bash
psql -h localhost -p 5433 -U app_admin -d automana -c "
-- Insert a fake daily row 6 years ago using a real card_version_id and source_id
-- from the live data so FK constraints pass.
INSERT INTO pricing.print_price_daily
    (price_date, card_version_id, source_id, transaction_type_id,
     finish_id, condition_id, language_id,
     list_low_cents, list_avg_cents, n_providers)
SELECT
    CURRENT_DATE - INTERVAL '6 years' AS price_date,
    mcp.card_version_id,
    sp.source_id,
    po.price_type_id,
    po.finish_id,
    po.condition_id,
    po.language_id,
    999   AS list_low_cents,
    1000  AS list_avg_cents,
    1     AS n_providers
FROM   pricing.price_observation po
JOIN   pricing.source_product    sp  ON sp.source_product_id = po.source_product_id
JOIN   pricing.mtg_card_products mcp ON mcp.product_id       = sp.product_id
ORDER  BY po.ts_date
LIMIT  2
ON CONFLICT DO NOTHING;
"
```

```bash
psql -h localhost -p 5433 -U app_admin -d automana -c \
  "CALL pricing.archive_to_weekly('5 years');"
```

Expected: NOTICE lines showing archived > 0, deleted > 0.

- [ ] **Step 4: Verify weekly table populated and daily rows removed**

```bash
psql -h localhost -p 5433 -U app_admin -d automana -c "
SELECT price_week, COUNT(*) AS rows
FROM   pricing.print_price_weekly
GROUP  BY price_week
ORDER  BY price_week DESC
LIMIT  5;
"
```

Expected: at least one week around `CURRENT_DATE - 6 years` appears.

```bash
psql -h localhost -p 5433 -U app_admin -d automana -c "
SELECT COUNT(*) AS old_daily_rows
FROM   pricing.print_price_daily
WHERE  price_date < CURRENT_DATE - INTERVAL '5 years';
"
```

Expected: `0` — the archived rows were deleted.

---

## Task 5: Add grants to the migration

**Files:**
- Modify: `src/automana/database/SQL/migrations/migration_18_pricing_tiers.sql` (append)

- [ ] **Step 1: Append grant block**

After the `archive_to_weekly` procedure in the migration file, append:

```sql
-- =========================================================================
-- 8. Grants
--    Mirrors the pattern in migration_17 and apply_schema_grants.sql.
--    app_celery: full DML on the new tables + EXECUTE on procedures.
--    app_rw / app_admin: full DML (covered by apply_schema_grants but explicit
--    here for migrations run before a full grant refresh).
--    app_ro: SELECT only.
-- =========================================================================

-- print_price_daily
GRANT SELECT, INSERT, UPDATE, DELETE ON pricing.print_price_daily TO app_celery, app_rw, app_admin;
GRANT SELECT ON pricing.print_price_daily TO app_ro;

-- print_price_weekly
GRANT SELECT, INSERT, UPDATE, DELETE ON pricing.print_price_weekly TO app_celery, app_rw, app_admin;
GRANT SELECT ON pricing.print_price_weekly TO app_ro;

-- print_price_latest
GRANT SELECT, INSERT, UPDATE, DELETE ON pricing.print_price_latest TO app_celery, app_rw, app_admin;
GRANT SELECT ON pricing.print_price_latest TO app_ro;

-- tier_watermark
GRANT SELECT, INSERT, UPDATE ON pricing.tier_watermark TO app_celery, app_rw, app_admin;
GRANT SELECT ON pricing.tier_watermark TO app_ro;

-- Procedures
GRANT EXECUTE ON PROCEDURE pricing.refresh_daily_prices(DATE, DATE) TO app_celery, app_rw, app_admin;
GRANT EXECUTE ON PROCEDURE pricing.archive_to_weekly(INTERVAL)      TO app_celery, app_rw, app_admin;
```

- [ ] **Step 2: Apply and verify grants**

```bash
psql -h localhost -p 5433 -U app_admin -d automana \
  -f src/automana/database/SQL/migrations/migration_18_pricing_tiers.sql
```

```bash
psql -h localhost -p 5433 -U app_admin -d automana -c "
SELECT grantee, privilege_type
FROM   information_schema.role_table_grants
WHERE  table_schema = 'pricing'
  AND  table_name   IN ('print_price_daily','print_price_latest','print_price_weekly','tier_watermark')
ORDER  BY table_name, grantee, privilege_type;
"
```

Expected: `app_celery`, `app_rw`, `app_admin` appear with INSERT/SELECT/UPDATE/DELETE; `app_ro` with SELECT.

---

## Task 6: Update `06_prices.sql` schema stubs

The schema file is used by fresh rebuilds (`rebuild_dev_db.sh`). It must match what migration 18 creates so a fresh rebuild produces the same schema as applying the migration on an existing DB.

**Files:**
- Modify: `src/automana/database/SQL/schemas/06_prices.sql`

- [ ] **Step 1: Replace the Tier 2 block in `06_prices.sql`**

Find the block starting with `--TIer 2: daily -> 5 years` (around line 255) and replace the entire `print_price_daily` DDL block (lines 256–316) with:

```sql
--Tier 2: daily -> 5 years
-- Populated by pricing.refresh_daily_prices(). TimescaleDB hypertable.
-- See migration_18_pricing_tiers.sql for the full DDL rationale.
CREATE TABLE IF NOT EXISTS pricing.print_price_daily (
    price_date          DATE        NOT NULL,
    card_version_id     UUID        NOT NULL
        REFERENCES card_catalog.card_version(card_version_id),
    source_id           SMALLINT    NOT NULL
        REFERENCES pricing.price_source(source_id),
    transaction_type_id INTEGER     NOT NULL
        REFERENCES pricing.transaction_type(transaction_type_id),
    finish_id           SMALLINT    NOT NULL
        DEFAULT pricing.default_finish_id()
        REFERENCES pricing.card_finished(finish_id),
    condition_id        SMALLINT    NOT NULL
        DEFAULT pricing.default_condition_id()
        REFERENCES pricing.card_condition(condition_id),
    language_id         SMALLINT    NOT NULL
        DEFAULT card_catalog.default_language_id()
        REFERENCES card_catalog.language_ref(language_id),

    list_low_cents      INTEGER,
    list_avg_cents      INTEGER,
    sold_avg_cents      INTEGER,
    n_providers         SMALLINT,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT print_price_daily_pk PRIMARY KEY (
        price_date, card_version_id, source_id,
        transaction_type_id, finish_id, condition_id, language_id
    ),
    CONSTRAINT chk_ppd_prices_nonneg CHECK (
        (list_low_cents IS NULL OR list_low_cents >= 0) AND
        (list_avg_cents IS NULL OR list_avg_cents >= 0) AND
        (sold_avg_cents IS NULL OR sold_avg_cents >= 0)
    )
);

SELECT create_hypertable(
    'pricing.print_price_daily',
    by_range('price_date', INTERVAL '7 days'),
    if_not_exists => TRUE
);

ALTER TABLE pricing.print_price_daily
    SET (
        timescaledb.compress,
        timescaledb.compress_segmentby = 'card_version_id, source_id, finish_id',
        timescaledb.compress_orderby   = 'price_date DESC'
    );

SELECT add_compression_policy('pricing.print_price_daily', INTERVAL '30 days', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_ppd_card_source_date
    ON pricing.print_price_daily (card_version_id, source_id, price_date DESC);
CREATE INDEX IF NOT EXISTS idx_ppd_date_dims
    ON pricing.print_price_daily (price_date, finish_id, condition_id, language_id);
```

- [ ] **Step 2: Replace the Tier 3 block in `06_prices.sql`**

Find the block starting with `--Tier 3: weekly aggre for older than 5 years` (around line 319) and replace the entire `print_price_weekly` DDL block (lines 319–377) with:

```sql
--Tier 3: weekly aggregate for data older than 5 years
-- Populated by pricing.archive_to_weekly(). TimescaleDB hypertable.
CREATE TABLE IF NOT EXISTS pricing.print_price_weekly (
    price_week          DATE        NOT NULL,
    card_version_id     UUID        NOT NULL
        REFERENCES card_catalog.card_version(card_version_id),
    source_id           SMALLINT    NOT NULL
        REFERENCES pricing.price_source(source_id),
    transaction_type_id INTEGER     NOT NULL
        REFERENCES pricing.transaction_type(transaction_type_id),
    finish_id           SMALLINT    NOT NULL
        DEFAULT pricing.default_finish_id()
        REFERENCES pricing.card_finished(finish_id),
    condition_id        SMALLINT    NOT NULL
        DEFAULT pricing.default_condition_id()
        REFERENCES pricing.card_condition(condition_id),
    language_id         SMALLINT    NOT NULL
        DEFAULT card_catalog.default_language_id()
        REFERENCES card_catalog.language_ref(language_id),

    list_low_cents      INTEGER,
    list_avg_cents      INTEGER,
    sold_avg_cents      INTEGER,
    n_days              SMALLINT,
    n_providers         SMALLINT,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT print_price_weekly_pk PRIMARY KEY (
        price_week, card_version_id, source_id,
        transaction_type_id, finish_id, condition_id, language_id
    ),
    CONSTRAINT chk_ppw_prices_nonneg CHECK (
        (list_low_cents IS NULL OR list_low_cents >= 0) AND
        (list_avg_cents IS NULL OR list_avg_cents >= 0) AND
        (sold_avg_cents IS NULL OR sold_avg_cents >= 0)
    ),
    CONSTRAINT chk_ppw_n_days CHECK (n_days IS NULL OR (n_days >= 1 AND n_days <= 7))
);

COMMENT ON COLUMN pricing.print_price_weekly.price_week IS
    'Monday of the ISO week (DATE_TRUNC(''week'', price_date))';

SELECT create_hypertable(
    'pricing.print_price_weekly',
    by_range('price_week', INTERVAL '28 days'),
    if_not_exists => TRUE
);

ALTER TABLE pricing.print_price_weekly
    SET (
        timescaledb.compress,
        timescaledb.compress_segmentby = 'card_version_id, source_id, finish_id',
        timescaledb.compress_orderby   = 'price_week DESC'
    );

SELECT add_compression_policy('pricing.print_price_weekly', INTERVAL '7 days', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_ppw_card_source_week
    ON pricing.print_price_weekly (card_version_id, source_id, price_week DESC);
CREATE INDEX IF NOT EXISTS idx_ppw_week_dims
    ON pricing.print_price_weekly (price_week, finish_id, condition_id, language_id);
```

- [ ] **Step 3: Add `print_price_latest` and `tier_watermark` to `06_prices.sql`**

After the Tier 3 block (and before the `--migration` section at line ~378), insert:

```sql
-- print_price_latest — current-price snapshot (one row per dimension key)
CREATE TABLE IF NOT EXISTS pricing.print_price_latest (
    card_version_id     UUID        NOT NULL
        REFERENCES card_catalog.card_version(card_version_id),
    source_id           SMALLINT    NOT NULL
        REFERENCES pricing.price_source(source_id),
    transaction_type_id INTEGER     NOT NULL
        REFERENCES pricing.transaction_type(transaction_type_id),
    finish_id           SMALLINT    NOT NULL
        DEFAULT pricing.default_finish_id()
        REFERENCES pricing.card_finished(finish_id),
    condition_id        SMALLINT    NOT NULL
        DEFAULT pricing.default_condition_id()
        REFERENCES pricing.card_condition(condition_id),
    language_id         SMALLINT    NOT NULL
        DEFAULT card_catalog.default_language_id()
        REFERENCES card_catalog.language_ref(language_id),

    price_date          DATE        NOT NULL,
    list_low_cents      INTEGER,
    list_avg_cents      INTEGER,
    sold_avg_cents      INTEGER,
    n_providers         SMALLINT,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT print_price_latest_pk PRIMARY KEY (
        card_version_id, source_id,
        transaction_type_id, finish_id, condition_id, language_id
    )
);

CREATE INDEX IF NOT EXISTS idx_ppl_card_source
    ON pricing.print_price_latest (card_version_id, source_id);

-- tier_watermark — tracks last successfully processed date per tier
CREATE TABLE IF NOT EXISTS pricing.tier_watermark (
    tier_name           TEXT        NOT NULL PRIMARY KEY,
    last_processed_date DATE        NOT NULL,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO pricing.tier_watermark (tier_name, last_processed_date) VALUES
    ('daily',  '1970-01-01'),
    ('weekly', '1970-01-01')
ON CONFLICT (tier_name) DO NOTHING;
```

- [ ] **Step 4: Verify fresh rebuild produces the correct schema**

```bash
dcdev-automana down
dcdev-automana up -d --build postgres redis
# wait for postgres to be healthy (check with: dcdev-automana ps)
bash ./src/automana/database/SQL/maintenance/rebuild_dev_db.sh --only rebuild
```

```bash
psql -h localhost -p 5433 -U app_admin -d automana \
  -f src/automana/database/SQL/maintenance/verify_migration_18.sql
```

Expected: all checks show `status = 'pass'`.

---

## Task 7: Update `pricing_integrity_checks.sql`

Add two new checks so the daily monitoring script catches regressions.

**Files:**
- Modify: `src/automana/database/SQL/maintenance/pricing_integrity_checks.sql`

- [ ] **Step 1: Add checks to `pricing_integrity_checks.sql`**

Open the file. After `chk_10_last_run_failed_steps` (around line 281) and before the final `SELECT` block, insert:

```sql
-- ---------------------------------------------------------------------------
-- CHECK 11: tier_watermark staleness.
--           daily watermark older than 2 days indicates refresh_daily_prices
--           has not run recently. weekly watermark is not time-sensitive.
--           Severity: warn if stale.
-- ---------------------------------------------------------------------------
,chk_11_watermark_staleness AS (
    SELECT
        'tier-watermark-daily-staleness'::TEXT            AS check_name,
        CASE WHEN w.last_processed_date < CURRENT_DATE - 2 THEN 1 ELSE 0 END::BIGINT
                                                          AS bad_count,
        jsonb_build_object(
            'last_processed_date', w.last_processed_date,
            'days_behind', (CURRENT_DATE - w.last_processed_date),
            'note', 'daily watermark should be within 2 days of today'
        )                                                 AS details
    FROM pricing.tier_watermark w
    WHERE w.tier_name = 'daily'
),

-- ---------------------------------------------------------------------------
-- CHECK 12: print_price_daily must be a TimescaleDB hypertable.
--           If it reverts to a plain table (e.g. after a bad migration), this
--           fires. bad_count = 1 means NOT a hypertable (error).
-- ---------------------------------------------------------------------------
chk_12_daily_is_hypertable AS (
    SELECT
        'print-price-daily-is-hypertable'::TEXT           AS check_name,
        CASE WHEN EXISTS (
            SELECT 1
            FROM timescaledb_information.hypertables
            WHERE hypertable_schema = 'pricing'
              AND hypertable_name   = 'print_price_daily'
        ) THEN 0 ELSE 1 END::BIGINT                       AS bad_count,
        jsonb_build_object(
            'note', 'print_price_daily must be a TimescaleDB hypertable'
        )                                                 AS details
)
```

Then in the final `SELECT` block (the UNION ALL list), add before the closing `;`:

```sql
    UNION ALL
    SELECT check_name, bad_count, details FROM chk_11_watermark_staleness
    UNION ALL
    SELECT check_name, bad_count, details FROM chk_12_daily_is_hypertable
```

And in the severity CASE (around line 290), add:

```sql
        WHEN check_name = 'tier-watermark-daily-staleness'
            THEN CASE WHEN bad_count > 0 THEN 'warn' ELSE 'ok' END
        WHEN check_name = 'print-price-daily-is-hypertable'
            THEN CASE WHEN bad_count > 0 THEN 'error' ELSE 'ok' END
```

- [ ] **Step 2: Run the integrity checks to confirm new checks pass**

```bash
psql -h localhost -p 5433 -U app_admin -d automana \
  -f src/automana/database/SQL/maintenance/pricing_integrity_checks.sql
```

Expected: `chk_11` shows `warn` (watermark at epoch — not yet refreshed in CI), `chk_12` shows `ok`.

---

## Task 8: Run the full verification suite and commit

- [ ] **Step 1: Run verify_migration_18.sql — expect all pass**

```bash
psql -h localhost -p 5433 -U app_admin -d automana \
  -f src/automana/database/SQL/maintenance/verify_migration_18.sql
```

Expected: every row shows `status = 'pass'`.

- [ ] **Step 2: Run pricing_integrity_checks.sql — no new errors**

```bash
psql -h localhost -p 5433 -U app_admin -d automana \
  -f src/automana/database/SQL/maintenance/pricing_integrity_checks.sql
```

Expected: no rows with `severity = 'error'`. `chk_11_watermark_staleness` may show `warn` (epoch sentinel — normal until first real backfill run).

- [ ] **Step 3: Commit**

```bash
git add \
  src/automana/database/SQL/migrations/migration_18_pricing_tiers.sql \
  src/automana/database/SQL/schemas/06_prices.sql \
  src/automana/database/SQL/maintenance/pricing_integrity_checks.sql \
  src/automana/database/SQL/maintenance/verify_migration_18.sql
git commit -m "feat(pricing): migration 18 — tier 2/3 TimescaleDB rollup tables and procedures

Adds print_price_daily (hypertable, 7-day chunks, compressed after 30d),
print_price_weekly (hypertable, 28-day chunks, compressed after 7d),
print_price_latest (snapshot), and tier_watermark. Two stored procedures:
refresh_daily_prices (tier 1 → tier 2 + latest, batched, resumable) and
archive_to_weekly (tier 2 → tier 3 for data >5 years, then deletes daily).
Source identity (source_id) preserved at every tier. Updates 06_prices.sql
to sync schema stubs and adds two integrity checks."
```

---

## Backfill note (out of scope for this migration — run manually)

After merging, to populate tier 2 from the full historical tier 1 data:

```bash
psql -h localhost -p 5433 -U app_admin -d automana -c \
  "CALL pricing.refresh_daily_prices('2012-01-01', CURRENT_DATE - 1);"
```

This will run for several hours on 220M+ rows. Monitor with:

```bash
psql -h localhost -p 5433 -U app_admin -d automana -c \
  "SELECT tier_name, last_processed_date FROM pricing.tier_watermark;"
```
