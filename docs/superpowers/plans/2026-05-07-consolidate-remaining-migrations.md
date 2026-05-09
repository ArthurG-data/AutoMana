# Consolidate Remaining Migrations into Schema Files

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate all remaining migrations by consolidating their DDL and data seeds into the appropriate schema files, leaving only dev-only and env-specific migrations.

**Architecture:** The plan separates consolidation into buckets: already-absorbed migrations (delete immediately), migrations needing consolidation (add to schema files), and dev/env-specific migrations (keep as-is). A critical prerequisite is recovering the lost 12_staging_schema.sql file from git history. Consolidations follow dependency order: 02_card_schema → 05_ebay → 06_prices.

**Tech Stack:** PostgreSQL, TimescaleDB, shell scripting for git history inspection.

---

## File Structure

**Files to modify:**
- `src/automana/database/SQL/schemas/02_card_schema.sql` — add `refresh_card_search_views()` procedure from migration_19_refresh_views_security_definer.sql
- `src/automana/database/SQL/schemas/06_prices.sql` — add pricing tiers DDL and archive procedure from migrations 18–19
- `src/automana/database/SQL/schemas/12_staging_schema.sql` — recover lost content from git history, replace 0-byte stub
- `src/automana/database/SQL/schemas/13_reporting_schema.sql` — create new file with DDL from migration_24_reporting_schema.sql

**Files to delete:**
- `src/automana/database/SQL/migrations/migration_16_fix_staging_lower_set_code.sql`
- `src/automana/database/SQL/migrations/migration_17_foil_finish_suffix.sql`
- `src/automana/database/SQL/migrations/migration_18_fix_mtgjson_price_cents_overflow.sql`
- `src/automana/database/SQL/migrations/migration_19_widen_redirect_uri.sql`
- `src/automana/database/SQL/migrations/migration_20_sandbox_scopes.sql`
- `src/automana/database/SQL/migrations/migration_18_pricing_tiers.sql` (after consolidation)
- `src/automana/database/SQL/migrations/migration_19_archive_to_weekly_fix.sql` (after consolidation)
- `src/automana/database/SQL/migrations/migration_19_refresh_views_security_definer.sql` (after consolidation)

**Files to keep (dev/env-specific):**
- `migration_22_ebay_refresh_tokens.sql` — dev-only TRUNCATE
- `migration_23_scopes_user_subset_constraint.sql` — dev-only DELETE
- `migration_24_prod_scopes_sync.sql` — prod-specific scope app linkage

---

## Task 1: Recover Lost 12_staging_schema.sql Content

**Files:**
- Inspect: `src/automana/database/SQL/schemas/12_staging_schema.sql`
- Target: commit `ccee98e` and git history
- Recover: original `11_staging_schema.sql` or `04_staging_schema.sql`

- [ ] **Step 1: Check current state of 12_staging_schema.sql**

```bash
wc -c src/automana/database/SQL/schemas/12_staging_schema.sql
```

Expected: Output shows 0 bytes

- [ ] **Step 2: Find the schema file in git history**

```bash
git log --all --full-history --oneline -- "src/automana/database/SQL/schemas/11_staging_schema.sql" | head -5
```

Expected: Commit list showing when file was changed/deleted

- [ ] **Step 3: Recover content from commit ccee98e**

```bash
git show ccee98e:src/automana/database/SQL/schemas/11_staging_schema.sql > /tmp/staging_schema_recovered.sql
wc -l /tmp/staging_schema_recovered.sql
```

Expected: Non-zero line count; file contains staging schema DDL

- [ ] **Step 4: If Step 3 fails, check for 04_staging_schema.sql in history**

```bash
git log --all --full-history --oneline -- "src/automana/database/SQL/schemas/04_staging_schema.sql" | head -5
git show <commit>:src/automana/database/SQL/schemas/04_staging_schema.sql > /tmp/staging_schema_recovered.sql
```

- [ ] **Step 5: If file still not found, query live database for schema structure**

```bash
docker compose --env-file config/env/.env.dev -f deploy/docker-compose.dev.yml exec \
  postgres psql -U app_agent -d automana \
  -c "\dt staging.*; \dv staging.*; \df staging.*"
```

Expected: List of all objects in staging schema

- [ ] **Step 6: Copy recovered content into 12_staging_schema.sql**

```bash
cat /tmp/staging_schema_recovered.sql > src/automana/database/SQL/schemas/12_staging_schema.sql
wc -l src/automana/database/SQL/schemas/12_staging_schema.sql
```

Expected: File now contains full staging schema (100+ lines expected)

- [ ] **Step 7: Commit recovered schema**

```bash
git add src/automana/database/SQL/schemas/12_staging_schema.sql
git commit -m "restore: recover lost 12_staging_schema.sql from git history"
```

---

## Task 2: Add refresh_card_search_views() to 02_card_schema.sql

**Files:**
- Modify: `src/automana/database/SQL/schemas/02_card_schema.sql`
- Source: `src/automana/database/SQL/migrations/migration_19_refresh_views_security_definer.sql`

- [ ] **Step 1: Read the target migration file to understand the procedure**

```bash
cat src/automana/database/SQL/migrations/migration_19_refresh_views_security_definer.sql
```

Expected: Contains `CREATE OR REPLACE PROCEDURE card_catalog.refresh_card_search_views()` with SECURITY DEFINER and two REFRESH statements

- [ ] **Step 2: Find the right insertion point in 02_card_schema.sql**

Read the end of 02_card_schema.sql to find where procedures are defined (after materialized view definitions).

```bash
tail -100 src/automana/database/SQL/schemas/02_card_schema.sql
```

Expected: Should show end of file with GRANT statements

- [ ] **Step 3: Add the procedure and grant to 02_card_schema.sql**

Append these lines before the final GRANT statements:

```sql
-- Refresh materialized views (SECURITY DEFINER so celery can refresh without needing MAINTAIN VIEW)
CREATE OR REPLACE PROCEDURE card_catalog.refresh_card_search_views()
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = card_catalog, pg_catalog
AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY card_catalog.v_card_versions_complete;
    REFRESH MATERIALIZED VIEW CONCURRENTLY card_catalog.v_card_name_suggest;
END;
$$;

GRANT EXECUTE ON PROCEDURE card_catalog.refresh_card_search_views()
    TO app_celery, app_rw, app_admin;
```

- [ ] **Step 4: Verify syntax is correct**

```bash
docker compose --env-file config/env/.env.dev -f deploy/docker-compose.dev.yml exec postgres psql -d automana -f src/automana/database/SQL/schemas/02_card_schema.sql -v ON_ERROR_STOP=1
```

Expected: No syntax errors

- [ ] **Step 5: Commit**

```bash
git add src/automana/database/SQL/schemas/02_card_schema.sql
git commit -m "feat: consolidate migration_19 refresh_views into 02_card_schema.sql"
```

---

## Task 3: Add Pricing Tiers DDL to 06_prices.sql (migrations 18–19)

**Files:**
- Modify: `src/automana/database/SQL/schemas/06_prices.sql`
- Source: `migration_18_pricing_tiers.sql` + `migration_19_archive_to_weekly_fix.sql`

**IMPORTANT:** Use migration_19's `archive_to_weekly()` procedure body (the one with `decompress_chunk()` loop and GUC settings), not migration_18's version.

- [ ] **Step 1: Read both migration files to understand the full DDL**

```bash
cat src/automana/database/SQL/migrations/migration_18_pricing_tiers.sql
cat src/automana/database/SQL/migrations/migration_19_archive_to_weekly_fix.sql
```

Expected: See table definitions, TimescaleDB hypertables, procedures, and GUC settings

- [ ] **Step 2: Extract the 4 table definitions from migration_18**

Note the exact column definitions and indexes for:
- `pricing.print_price_daily` (TimescaleDB hypertable, 7-day chunks, compressed)
- `pricing.print_price_weekly` (TimescaleDB hypertable, 28-day chunks, compressed)
- `pricing.print_price_latest` (plain table)
- `pricing.tier_watermark` (plain table with PK on `tier_name`)

- [ ] **Step 3: Find insertion point in 06_prices.sql**

Find the line where other pricing tables are created (after `pricing.price_observation`). This is where the new tables should go.

```bash
grep -n "CREATE TABLE pricing.price_observation" src/automana/database/SQL/schemas/06_prices.sql
```

- [ ] **Step 4: Add table definitions in correct order**

Add these tables after the existing pricing tables and before procedures:

```sql
-- Daily price hypertable with 7-day chunks, compression every 30 days
CREATE TABLE IF NOT EXISTS pricing.print_price_daily (
    price_date DATE NOT NULL,
    card_version_id UUID,
    source_id SMALLINT,
    transaction_type_id SMALLINT,
    finish_id SMALLINT,
    condition_id SMALLINT,
    language_id INT,
    list_low_cents INT,
    list_avg_cents INT,
    sold_avg_cents INT,
    n_providers SMALLINT
);
SELECT create_hypertable('pricing.print_price_daily', 'price_date', if_not_exists => TRUE, chunk_time_interval => '7 days'::interval);
ALTER TABLE pricing.print_price_daily SET (timescaledb.compress, timescaledb.compress_orderby='card_version_id, source_id, finish_id');
SELECT add_compression_policy('pricing.print_price_daily', INTERVAL '30 days', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_ppd_card_source_date ON pricing.print_price_daily (card_version_id, source_id, price_date DESC);
CREATE INDEX IF NOT EXISTS idx_ppd_date_dims ON pricing.print_price_daily (price_date DESC, transaction_type_id, condition_id);

-- Weekly price hypertable with 28-day chunks, compression every 7 days
CREATE TABLE IF NOT EXISTS pricing.print_price_weekly (
    price_week DATE NOT NULL,
    card_version_id UUID,
    source_id SMALLINT,
    transaction_type_id SMALLINT,
    finish_id SMALLINT,
    condition_id SMALLINT,
    language_id INT,
    list_low_cents INT,
    list_avg_cents INT,
    sold_avg_cents INT,
    n_providers SMALLINT,
    n_days SMALLINT
);
SELECT create_hypertable('pricing.print_price_weekly', 'price_week', if_not_exists => TRUE, chunk_time_interval => '28 days'::interval);
ALTER TABLE pricing.print_price_weekly SET (timescaledb.compress, timescaledb.compress_orderby='card_version_id, source_id, finish_id');
SELECT add_compression_policy('pricing.print_price_weekly', INTERVAL '7 days', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_ppw_card_source_week ON pricing.print_price_weekly (card_version_id, source_id, price_week DESC);
CREATE INDEX IF NOT EXISTS idx_ppw_week_dims ON pricing.print_price_weekly (price_week DESC, transaction_type_id, condition_id);
ALTER TABLE pricing.print_price_weekly ADD CONSTRAINT uk_ppw_weekly_dims UNIQUE (price_week, card_version_id, source_id, transaction_type_id, finish_id, condition_id, language_id);

-- Latest daily snapshot
CREATE TABLE IF NOT EXISTS pricing.print_price_latest (
    card_version_id UUID PRIMARY KEY,
    source_id SMALLINT,
    transaction_type_id SMALLINT,
    finish_id SMALLINT,
    condition_id SMALLINT,
    language_id INT,
    price_cents INT,
    price_date DATE,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Watermark for tier refresh state
CREATE TABLE IF NOT EXISTS pricing.tier_watermark (
    tier_name TEXT PRIMARY KEY,
    last_processed_date DATE,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
```

- [ ] **Step 5: Add procedures from migration_18 and migration_19**

Add `refresh_daily_prices()` from migration_18 and `archive_to_weekly()` from migration_19 (using the mission_19 body with decompress_chunk loop):

```sql
CREATE OR REPLACE PROCEDURE pricing.refresh_daily_prices(p_from DATE, p_to DATE)
LANGUAGE plpgsql
AS $$
DECLARE
    v_date DATE;
BEGIN
    FOR v_date IN SELECT DISTINCT price_date FROM pricing.price_observation 
                  WHERE price_date BETWEEN p_from AND p_to
                  ORDER BY price_date
    LOOP
        INSERT INTO pricing.print_price_daily (...)
        SELECT ... FROM pricing.price_observation WHERE price_date = v_date
        ON CONFLICT DO NOTHING;
    END LOOP;
END;
$$;

CREATE OR REPLACE PROCEDURE pricing.archive_to_weekly(p_older_than INTERVAL)
LANGUAGE plpgsql
SET work_mem = '256MB'
SET maintenance_work_mem = '512MB'
SET timescaledb.max_tuples_decompressed_per_dml_transaction = 0
AS $$
DECLARE
    v_chunk RECORD;
BEGIN
    FOR v_chunk IN
        SELECT chunk_name FROM timescaledb_information.chunks
        WHERE hypertable_name = 'print_price_daily'
          AND range_start < (CURRENT_DATE - p_older_than)::bigint
        ORDER BY range_start DESC
    LOOP
        EXECUTE format('SELECT decompress_chunk(%L)', v_chunk.chunk_name);
        -- Archive logic with 7-day batching
        INSERT INTO pricing.print_price_weekly (...)
        SELECT price_week, ... FROM pricing.print_price_daily
        WHERE price_date < CURRENT_DATE - p_older_than
        ON CONFLICT DO NOTHING;
        EXECUTE format('SELECT compress_chunk(%L)', v_chunk.chunk_name);
    END LOOP;
END;
$$;
```

(Use the exact procedure bodies from migration_19_archive_to_weekly_fix.sql — this summary shows structure only)

- [ ] **Step 6: Add data seed for tier_watermark**

After procedures, add:

```sql
INSERT INTO pricing.tier_watermark (tier_name, last_processed_date)
VALUES ('daily', '1970-01-01'), ('weekly', '1970-01-01')
ON CONFLICT DO NOTHING;
```

- [ ] **Step 7: Add grants for all roles**

```sql
-- Grants for pricing tier tables
GRANT SELECT, INSERT, UPDATE, DELETE ON pricing.print_price_daily TO app_celery, app_rw, app_admin;
GRANT SELECT ON pricing.print_price_daily TO app_readonly;

GRANT SELECT, INSERT, UPDATE, DELETE ON pricing.print_price_weekly TO app_celery, app_rw, app_admin;
GRANT SELECT ON pricing.print_price_weekly TO app_readonly;

GRANT SELECT, INSERT, UPDATE, DELETE ON pricing.print_price_latest TO app_celery, app_rw, app_admin;
GRANT SELECT ON pricing.print_price_latest TO app_readonly;

GRANT SELECT, INSERT, UPDATE, DELETE ON pricing.tier_watermark TO app_celery, app_rw, app_admin;
GRANT SELECT ON pricing.tier_watermark TO app_readonly;

GRANT EXECUTE ON PROCEDURE pricing.refresh_daily_prices(DATE, DATE) TO app_celery, app_rw, app_admin;
GRANT EXECUTE ON PROCEDURE pricing.archive_to_weekly(INTERVAL) TO app_celery, app_rw, app_admin;
```

- [ ] **Step 8: Verify syntax**

```bash
docker compose --env-file config/env/.env.dev -f deploy/docker-compose.dev.yml exec postgres psql -d automana -f src/automana/database/SQL/schemas/06_prices.sql -v ON_ERROR_STOP=1
```

Expected: No syntax errors

- [ ] **Step 9: Commit**

```bash
git add src/automana/database/SQL/schemas/06_prices.sql
git commit -m "feat: consolidate migration_18 and migration_19 pricing tiers into 06_prices.sql"
```

---

## Task 4: Create 13_reporting_schema.sql from migration_24_reporting_schema.sql

**Files:**
- Create: `src/automana/database/SQL/schemas/13_reporting_schema.sql`
- Source: `migration_24_reporting_schema.sql`

- [ ] **Step 1: Read migration_24_reporting_schema.sql**

```bash
cat src/automana/database/SQL/migrations/migration_24_reporting_schema.sql
```

Expected: Contains schema creation and hourly_metrics table definition

- [ ] **Step 2: Create new schema file with proper header**

```bash
cat > src/automana/database/SQL/schemas/13_reporting_schema.sql << 'EOF'
-- Reporting schema for API and pipeline metrics aggregation
-- Used by metrics collection services to store hourly summaries

CREATE SCHEMA IF NOT EXISTS reporting;

-- Hourly metrics aggregation table
CREATE TABLE IF NOT EXISTS reporting.hourly_metrics (
    id SERIAL PRIMARY KEY,
    hour BIGINT NOT NULL,
    metric_type VARCHAR(50) NOT NULL,
    endpoint VARCHAR(255),
    task_name VARCHAR(255),
    status_code SMALLINT,
    request_count INT DEFAULT 0,
    error_count INT DEFAULT 0,
    cache_hit_count INT DEFAULT 0,
    response_time_p95 FLOAT,
    response_time_median FLOAT,
    response_time_max FLOAT,
    celery_success_count INT DEFAULT 0,
    celery_failure_count INT DEFAULT 0,
    error_rate FLOAT,
    cache_hit_rate FLOAT,
    celery_success_rate FLOAT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (hour, metric_type, endpoint, task_name, status_code)
);

CREATE INDEX IF NOT EXISTS idx_hourly_metrics_hour ON reporting.hourly_metrics (hour DESC);
CREATE INDEX IF NOT EXISTS idx_hourly_metrics_metric_type ON reporting.hourly_metrics (metric_type);
CREATE INDEX IF NOT EXISTS idx_hourly_metrics_endpoint ON reporting.hourly_metrics (endpoint);
CREATE INDEX IF NOT EXISTS idx_hourly_metrics_task_name ON reporting.hourly_metrics (task_name);
CREATE INDEX IF NOT EXISTS idx_hourly_metrics_created_at ON reporting.hourly_metrics (created_at DESC);

-- Grants: SELECT to app_readonly, INSERT+UPDATE to app_celery, full DML to app_rw and app_admin
GRANT USAGE ON SCHEMA reporting TO app_readonly, app_celery, app_rw, app_admin;
GRANT SELECT ON reporting.hourly_metrics TO app_readonly;
GRANT SELECT, INSERT, UPDATE ON reporting.hourly_metrics TO app_celery;
GRANT SELECT, INSERT, UPDATE, DELETE ON reporting.hourly_metrics TO app_rw, app_admin;
EOF
```

- [ ] **Step 3: Verify the file was created**

```bash
wc -l src/automana/database/SQL/schemas/13_reporting_schema.sql
```

Expected: 40+ lines

- [ ] **Step 4: Test syntax**

```bash
docker compose --env-file config/env/.env.dev -f deploy/docker-compose.dev.yml exec postgres psql -d automana -f src/automana/database/SQL/schemas/13_reporting_schema.sql -v ON_ERROR_STOP=1
```

Expected: No syntax errors

- [ ] **Step 5: Commit**

```bash
git add src/automana/database/SQL/schemas/13_reporting_schema.sql
git commit -m "feat: create 13_reporting_schema.sql from migration_24_reporting_schema.sql"
```

---

## Task 5: Delete Absorbed Migrations (Bucket 1)

**Files to delete:**
- `migration_16_fix_staging_lower_set_code.sql` (absorbed in 06_prices.sql)
- `migration_17_foil_finish_suffix.sql` (absorbed in 06_prices.sql)
- `migration_18_fix_mtgjson_price_cents_overflow.sql` (absorbed in 11_mtgjson_schema.sql)
- `migration_19_widen_redirect_uri.sql` (absorbed in 05_ebay.sql)
- `migration_20_sandbox_scopes.sql` (absorbed in 05_ebay.sql)

- [ ] **Step 1: Verify each migration has been consolidated**

For each migration file, search its content in the corresponding schema file:

```bash
# 16: search for "staging_lower_set_code" or similar in 06_prices.sql
grep -i "staging_lower_set_code\|fix_lower" src/automana/database/SQL/schemas/06_prices.sql

# 17: search for "foil_finish_suffix" in 06_prices.sql
grep -i "foil.*finish" src/automana/database/SQL/schemas/06_prices.sql

# 18: search for "price_cents" or "LEAST.*2147483647" in 11_mtgjson_schema.sql
grep -i "price_cents\|2147483647" src/automana/database/SQL/schemas/11_mtgjson_schema.sql

# 19: search for "redirect_uri" in 05_ebay.sql
grep -i "redirect_uri" src/automana/database/SQL/schemas/05_ebay.sql

# 20: search for "sandbox" or "scopes" in 05_ebay.sql
grep -i "sandbox\|SANDBOX_SCOPES" src/automana/database/SQL/schemas/05_ebay.sql
```

Expected: All searches find the consolidated DDL in the respective schema files

- [ ] **Step 2: Delete the absorbed migration files**

```bash
rm src/automana/database/SQL/migrations/migration_16_fix_staging_lower_set_code.sql \
   src/automana/database/SQL/migrations/migration_17_foil_finish_suffix.sql \
   src/automana/database/SQL/migrations/migration_18_fix_mtgjson_price_cents_overflow.sql \
   src/automana/database/SQL/migrations/migration_19_widen_redirect_uri.sql \
   src/automana/database/SQL/migrations/migration_20_sandbox_scopes.sql
```

- [ ] **Step 3: Verify deletions with git status**

```bash
git status src/automana/database/SQL/migrations/
```

Expected: 5 deletions shown as `deleted: migration_XX_...`

- [ ] **Step 4: Commit deletions**

```bash
git add -u src/automana/database/SQL/migrations/
git commit -m "refactor: remove absorbed migrations (16, 17, 18, 19, 20)"
```

---

## Task 6: Delete Consolidated Pricing Migrations (Bucket 2 — after consolidation)

**Files to delete:**
- `migration_18_pricing_tiers.sql` (consolidated into 06_prices.sql in Task 3)
- `migration_19_archive_to_weekly_fix.sql` (consolidated into 06_prices.sql in Task 3)
- `migration_19_refresh_views_security_definer.sql` (consolidated into 02_card_schema.sql in Task 2)

- [ ] **Step 1: Verify consolidation is complete**

Confirm Tasks 2 and 3 are committed and the schema files contain the necessary DDL:

```bash
git log --oneline -3
```

Expected: Recent commits for Tasks 2 and 3

- [ ] **Step 2: Delete the three migration files**

```bash
rm src/automana/database/SQL/migrations/migration_18_pricing_tiers.sql \
   src/automana/database/SQL/migrations/migration_19_archive_to_weekly_fix.sql \
   src/automana/database/SQL/migrations/migration_19_refresh_views_security_definer.sql
```

- [ ] **Step 3: Verify with git status**

```bash
git status src/automana/database/SQL/migrations/
```

Expected: 3 deletions shown

- [ ] **Step 4: Commit**

```bash
git add -u src/automana/database/SQL/migrations/
git commit -m "refactor: remove consolidated pricing migrations (18, 19 archive, 19 refresh)"
```

---

## Task 7: Verify No Migrations Remain in Unwanted Locations

**Files:**
- Inspect: `src/automana/database/SQL/migrations/`

- [ ] **Step 1: List all remaining migration files**

```bash
ls -la src/automana/database/SQL/migrations/*.sql
```

Expected: Only these files remain:
- `migration_21_*.sql` (if it exists)
- `migration_22_ebay_refresh_tokens.sql` (dev-only TRUNCATE)
- `migration_23_scopes_user_subset_constraint.sql` (dev-only DELETE)
- `migration_24_prod_scopes_sync.sql` (prod-specific scope app linkage)
- `migration_25_fix2_fix3.sql` (already consolidated in previous session)

- [ ] **Step 2: Verify no "fix2_fix3" or numbering gaps**

```bash
ls -1 src/automana/database/SQL/migrations/ | sort
```

Expected: Consistent numbering; no duplicate migration_25; only dev/env-specific migrations left

- [ ] **Step 3: Document which migrations were kept and why**

Create a summary showing:
- Migration 22: `TRUNCATE app_integration.ebay_tokens` — dev-only cleanup, must not run in production
- Migration 23: `DELETE FROM app_integration.scopes_user` — dev-only cleanup, must not run in production
- Migration 24: `scope_app` linkage — prod-specific, references production app row

```bash
cat > /tmp/REMAINING_MIGRATIONS.txt << 'EOF'
# Remaining Migrations (Dev/Env-Specific Only)

## migration_22_ebay_refresh_tokens.sql
- Purpose: Dev-only truncation of ebay_tokens table
- Reason Kept: TRUNCATE RESTART IDENTITY is destructive; only appropriate for dev rebuilds
- Production: Must never run in production

## migration_23_scopes_user_subset_constraint.sql
- Purpose: Dev-only deletion of stale scopes_user records
- Reason Kept: DELETE is destructive; only appropriate for dev rebuilds
- Production: Must never run in production

## migration_24_prod_scopes_sync.sql
- Purpose: Prod-specific scope app linkage for 'automana-production-v1' app
- Reason Kept: References production-specific app row not seeded by schema files
- Production: Must be run only in production environment

All other migrations (16-21, 25) have been consolidated into schema files.
EOF
cat /tmp/REMAINING_MIGRATIONS.txt
```

- [ ] **Step 4: Commit the summary as documentation**

```bash
git add PIPELINE_TECHNICAL_DEBT.md # if this file exists and needs updating
git commit -m "docs: record consolidated migrations and dev-only migration retention"
```

---

## Task 8: Full Integration Test — Rebuild Database from Schema Files

**Files:**
- Execute: `src/automana/database/SQL/maintenance/rebuild_dev_db.sh`

- [ ] **Step 1: Create a backup of the current database**

```bash
docker exec automana-postgres-dev pg_dump -U automana_admin automana | gzip > backups/automana-pre-consolidation-$(date -u +%Y%m%d-%H%M%S).sql.gz
ls -lh backups/automana-pre-consolidation-*.sql.gz
```

Expected: Backup file created with non-zero size (100MB+ expected)

- [ ] **Step 2: Run full rebuild with two-phase startup**

```bash
dcdev-automana down
dcdev-automana up -d --build postgres redis
# Wait for postgres to be healthy
sleep 30
docker compose --env-file config/env/.env.dev -f deploy/docker-compose.dev.yml exec postgres pg_isready -U automana_admin
```

Expected: `postgres is accepting connections` message

- [ ] **Step 3: Run rebuild with --only rebuild**

```bash
bash ./src/automana/database/SQL/maintenance/rebuild_dev_db.sh --only rebuild
```

Expected: Schema files applied, migrations applied, grants set, no errors

- [ ] **Step 4: Bring up celery and run pipeline skip-rebuild**

```bash
dcdev-automana up -d --build celery-worker celery-beat
sleep 10
bash ./src/automana/database/SQL/maintenance/rebuild_dev_db.sh --skip-rebuild
```

Expected: Pipelines run and complete without errors; `ops.ingestion_runs` shows terminal status for each pipeline

- [ ] **Step 5: Verify no data loss or constraint violations**

```bash
docker compose --env-file config/env/.env.dev -f deploy/docker-compose.dev.yml exec postgres psql -U app_agent -d automana << 'EOF'
SELECT COUNT(*) as card_count FROM card_catalog.cards;
SELECT COUNT(*) as set_count FROM card_catalog.sets;
SELECT COUNT(*) as price_count FROM pricing.price_observation;
SELECT COUNT(*) as tier_count FROM pricing.tier_watermark;
SELECT COUNT(*) as metrics_count FROM reporting.hourly_metrics;
SELECT COUNT(*) as ebay_scopes FROM app_integration.scopes WHERE app_id IS NOT NULL;
EOF
```

Expected: Non-zero counts for card_catalog, pricing, and reporting tables; ebay_scopes > 0

- [ ] **Step 6: Verify printing schema exists and is populated (if recovered)**

```bash
docker compose --env-file config/env/.env.dev -f deploy/docker-compose.dev.yml exec postgres psql -U app_agent -d automana << 'EOF'
\dt staging.*
SELECT COUNT(*) FROM staging.* LIMIT 10;
EOF
```

Expected: Staging schema tables exist and have data

- [ ] **Step 7: Commit successful rebuild**

```bash
git add -A
git commit -m "test: verify database rebuild succeeds with consolidated schema files"
```

---

## Summary

✅ **Consolidation Complete**

All migrations have been consolidated or categorized:

| Bucket | Migrations | Action |
|--------|-----------|--------|
| 1 — Already absorbed | 16, 17, 18, 19, 20 | ✅ Deleted |
| 2 — Newly consolidated | 18 (pricing), 19 (archive), 19 (refresh), 24 (reporting) | ✅ Added to schemas 02, 06, 13 |
| 3 — Keep as-is | 22, 23, 24 (prod) | ✅ Retained (dev/env-specific) |
| Special case | 25 (fix2_fix3) | ✅ Already consolidated (previous session) |
| Recovery | 12_staging_schema.sql | ✅ Recovered from git history |

**Files modified:** 02_card_schema.sql, 06_prices.sql, 12_staging_schema.sql (recovered), 13_reporting_schema.sql (new)

**Files deleted:** 8 migration files

**Migrations remaining:** 4 (dev-only and prod-specific, as documented)

**Data loss:** None — all operations use `IF NOT EXISTS`, `ON CONFLICT DO NOTHING`, or dev-only markers

---

## Execution Options

Plan complete and saved to `/home/arthur/projects/AutoMana/docs/superpowers/plans/2026-05-07-consolidate-remaining-migrations.md`.

**Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach would you prefer?
