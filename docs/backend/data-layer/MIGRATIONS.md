# Database Migrations

This document explains how to safely evolve the database schema over time, with patterns for zero-downtime migrations, backward compatibility, and testing strategies.

**Migration Files:** [`src/automana/database/SQL/migrations/`](../../../src/automana/database/SQL/migrations/)

---

## Table of Contents

1. [Migration Strategy & Framework](#migration-strategy--framework)
2. [Safe Migration Patterns](#safe-migration-patterns)
3. [Common Scenarios](#common-scenarios)
4. [Testing Migrations](#testing-migrations)
5. [Rollback Strategy](#rollback-strategy)
6. [Deployment Strategy](#deployment-strategy)
7. [Real Examples from Codebase](#real-examples-from-codebase)

---

## Migration Strategy & Framework

### Tool: SQL Scripts (Manual)

AutoMana uses **manual SQL migration files** rather than a framework like Alembic or Flyway.

**Why?**
1. **Transparency:** Migration logic is plain SQL (no ORM abstractions)
2. **Control:** Complex transformations stay in SQL (stored procedures, bulk updates)
3. **Debugging:** Easy to inspect what changed by reading the file
4. **Flexibility:** Can mix DDL, DML, and PL/pgSQL procedures in one file

### Migration Naming Convention

```
migration_N_descriptive_name.sql
```

**Examples:**
- `migration_17_foil_finish_suffix.sql` — add finish codes and mapping table
- `migration_18_pricing_tiers.sql` — restructure pricing tables
- `migration_19_refresh_views_security_definer.sql` — fix view permissions
- `migration_22_ebay_refresh_tokens.sql` — add token storage

### Execution Framework

**File:** [`src/automana/database/SQL/maintenance/rebuild_dev_db.sh`](../../../src/automana/database/SQL/maintenance/rebuild_dev_db.sh)

Migrations are run by:
1. **Development:** `bash rebuild_dev_db.sh` (idempotent, runs all migrations)
2. **Production:** CI/CD pipeline applies migrations during deployment

**File ordering:**
- Schemas first (`01_set_schema.sql`, `02_card_schema.sql`, ...)
- Then migrations in numeric order (`migration_17_...`, `migration_18_...`, ...)
- Ensures dependencies resolve correctly

### Idempotency

Every migration must be **idempotent** — safe to run multiple times without error:

**✓ CORRECT (idempotent):**
```sql
CREATE TABLE IF NOT EXISTS pricing.card_finished(
    finish_id SMALLSERIAL PRIMARY KEY,
    code TEXT UNIQUE NOT NULL
);

INSERT INTO pricing.card_finished (code) VALUES ('FOIL')
ON CONFLICT (code) DO NOTHING;  -- Skip if already exists
```

**✗ WRONG (not idempotent):**
```sql
CREATE TABLE pricing.card_finished(...);  -- Fails on 2nd run (table exists)
INSERT INTO pricing.card_finished (code) VALUES ('FOIL');  -- Fails on 2nd run (duplicate)
```

---

## Safe Migration Patterns

### Pattern 1: Add a Column (with Default)

**Use case:** New feature requires storing new data.

```sql
BEGIN;

-- Step 1: Add column with temporary default
ALTER TABLE card_catalog.card_version
ADD COLUMN foil_finish_id SMALLINT
DEFAULT (SELECT finish_id FROM pricing.card_finished WHERE code = 'NONFOIL');

-- Step 2: Backfill existing rows
UPDATE card_catalog.card_version
SET foil_finish_id = (SELECT finish_id FROM pricing.card_finished WHERE code = 'NONFOIL')
WHERE foil_finish_id IS NULL;

-- Step 3: Add foreign key constraint
ALTER TABLE card_catalog.card_version
ADD CONSTRAINT fk_card_version_foil_finish
FOREIGN KEY (foil_finish_id) REFERENCES pricing.card_finished(finish_id);

-- Step 4: Remove temporary default and make NOT NULL
ALTER TABLE card_catalog.card_version
ALTER COLUMN foil_finish_id DROP DEFAULT,
ALTER COLUMN foil_finish_id SET NOT NULL;

COMMIT;
```

**Why this sequence?**
1. Default enables insertion of rows without specifying the new column
2. Backfill ensures existing rows have valid values
3. FK constraint prevents invalid references going forward
4. Drop default and set NOT NULL enforces the schema contract

**Zero-downtime impact:**
- ADD COLUMN with DEFAULT is fast (metadata only)
- UPDATE is online (locks table briefly)
- ADD CONSTRAINT is online (scans to verify)

### Pattern 2: Drop a Column (Safely)

**Use case:** Remove a column that's no longer needed.

**Approach A: One-step removal (fast, if safe)**

```sql
BEGIN;
ALTER TABLE card_catalog.card_version DROP COLUMN legacy_field;
COMMIT;
```

**Approach B: Staged removal (for backward compatibility)**

If code still reads the column, stage removal:

1. **Phase 1 (Week N):** Mark column as deprecated in docs, but don't use it in new code
2. **Phase 2 (Week N+1):** Deploy code that doesn't read/write the column
3. **Phase 3 (Week N+2):** Run migration to drop column

```sql
-- Migration (Phase 3)
BEGIN;
ALTER TABLE card_catalog.card_version DROP COLUMN legacy_field;
COMMIT;
```

**Why staged approach?**
- Prevents "column not found" errors in production
- Gives time for code review and testing
- Rollback is simple (revert code, skip migration)

### Pattern 3: Rename a Column (with Compatibility)

**Use case:** Improve naming for clarity.

**Approach: Add new column, migrate data, drop old column**

```sql
BEGIN;

-- Step 1: Add new column with same data type
ALTER TABLE pricing.price_observation
ADD COLUMN list_price_cents INTEGER;

-- Step 2: Copy existing data
UPDATE pricing.price_observation
SET list_price_cents = list_low_cents;

-- Step 3: Add triggers or views to keep old column in sync (optional)
-- If old column still used by old code
CREATE OR REPLACE TRIGGER trg_price_observation_sync
AFTER UPDATE ON pricing.price_observation
FOR EACH ROW
EXECUTE FUNCTION pricing.sync_price_columns();

-- Step 4: (Later, after code updated) Drop old column
-- ALTER TABLE pricing.price_observation DROP COLUMN list_low_cents;

COMMIT;
```

**Alternative: Just alias via view**

```sql
-- If column only read (not written), create a view
CREATE OR REPLACE VIEW pricing.v_price_observation AS
SELECT *, list_price_cents AS list_low_cents
FROM pricing.price_observation;
```

### Pattern 4: Add/Drop Indexes (Online)

**Add index:**
```sql
-- Without blocking reads
CREATE INDEX CONCURRENTLY idx_card_name_trgm
ON card_catalog.unique_cards_ref USING gin (card_name gin_trgm_ops);
```

**Drop index:**
```sql
-- Can run while table is in use
DROP INDEX CONCURRENTLY idx_card_name_trgm;
```

**Why CONCURRENTLY?**
- Without it, locks the table (blocks reads/writes)
- With it, allows concurrent DML during index build
- Takes longer but keeps system responsive

### Pattern 5: Add/Modify Constraint

**Add UNIQUE constraint:**
```sql
BEGIN;
-- First, deduplicate any existing violators
DELETE FROM card_catalog.artists_ref
WHERE artist_id NOT IN (
    SELECT artist_id FROM card_catalog.artists_ref
    ORDER BY artist_id LIMIT 1
)
AND artist_name = (SELECT artist_name FROM card_catalog.artists_ref LIMIT 1);

-- Then add constraint
ALTER TABLE card_catalog.artists_ref
ADD CONSTRAINT unique_artist_name UNIQUE (artist_name);

COMMIT;
```

**Add NOT NULL constraint:**
```sql
BEGIN;
-- First backfill NULLs
UPDATE pricing.print_price_daily
SET condition_id = (SELECT condition_id FROM pricing.card_condition WHERE code = 'NM')
WHERE condition_id IS NULL;

-- Then add constraint
ALTER TABLE pricing.print_price_daily
ALTER COLUMN condition_id SET NOT NULL;

COMMIT;
```

**Add CHECK constraint:**
```sql
ALTER TABLE pricing.price_observation
ADD CONSTRAINT chk_nonneg_prices
CHECK (
    (list_low_cents IS NULL OR list_low_cents >= 0) AND
    (list_avg_cents IS NULL OR list_avg_cents >= 0)
);
```

### Pattern 6: Data Transformation

**Use case:** Denormalization, format conversion, aggregation.

**Example: Populate denormalized columns during ETL:**

```sql
BEGIN;

-- Step 1: Add new columns to card_version
ALTER TABLE card_catalog.card_version
ADD COLUMN card_name TEXT,
ADD COLUMN set_code VARCHAR(5),
ADD COLUMN rarity_name VARCHAR(20);

-- Step 2: Backfill from related tables
UPDATE card_catalog.card_version cv
SET card_name = uc.card_name,
    set_code = s.set_code,
    rarity_name = r.rarity_name
FROM card_catalog.unique_cards_ref uc
JOIN card_catalog.sets s ON s.set_id = cv.set_id
JOIN card_catalog.rarities_ref r ON r.rarity_id = cv.rarity_id
WHERE cv.unique_card_id = uc.unique_card_id;

-- Step 3: Make NOT NULL (optional, if safe)
ALTER TABLE card_catalog.card_version
ALTER COLUMN card_name SET NOT NULL;

COMMIT;
```

**Why denormalize?**
- Query performance: avoid JOINs on high-volume searches
- Trade-off: Storage and maintenance complexity
- Acceptable if data is immutable after load (ETL-only)

---

## Common Scenarios

### Scenario 1: Add a Pricing Tier

**Context:** New time-series table to store weekly aggregates.

**Migration:**

```sql
-- migration_18_pricing_tiers.sql

BEGIN;

-- Create new hypertable for weekly aggregates
CREATE TABLE IF NOT EXISTS pricing.print_price_weekly (
    price_week          DATE        NOT NULL,
    card_version_id     UUID        NOT NULL
        REFERENCES card_catalog.card_version(card_version_id),
    source_id           SMALLINT    NOT NULL
        REFERENCES pricing.price_source(source_id),
    transaction_type_id INTEGER     NOT NULL
        REFERENCES pricing.transaction_type(transaction_type_id),
    finish_id           SMALLINT    NOT NULL
        DEFAULT (SELECT finish_id FROM pricing.card_finished WHERE code = 'NONFOIL')
        REFERENCES pricing.card_finished(finish_id),
    condition_id        SMALLINT    NOT NULL
        DEFAULT (SELECT condition_id FROM pricing.card_condition WHERE code = 'NM')
        REFERENCES pricing.card_condition(condition_id),
    language_id         SMALLINT    NOT NULL
        DEFAULT (SELECT language_id FROM card_catalog.language_ref WHERE language_code = 'en')
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
    )
);

-- Convert to TimescaleDB hypertable
SELECT create_hypertable(
    'pricing.print_price_weekly',
    by_range('price_week', INTERVAL '28 days'),
    if_not_exists => TRUE
);

-- Enable compression
ALTER TABLE pricing.print_price_weekly
    SET (timescaledb.compress,
         timescaledb.compress_segmentby = 'card_version_id, source_id, finish_id',
         timescaledb.compress_orderby   = 'price_week DESC');

-- Auto-compress after 7 days
SELECT add_compression_policy('pricing.print_price_weekly', INTERVAL '7 days');

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_ppw_card_source_week
    ON pricing.print_price_weekly (card_version_id, source_id, price_week DESC);

-- Create view for backward compatibility
CREATE OR REPLACE VIEW pricing.v_weekly_summary AS
SELECT price_week, card_version_id, source_id, list_avg_cents, n_providers
FROM pricing.print_price_weekly;

COMMIT;
```

**Zero-downtime:**
- No existing data modified (new table)
- Can run while application is running
- Application code deployed separately to start writing to new table

### Scenario 2: Add OAuth Scope

**Context:** New integration requires new permissions.

**Migration:**

```sql
-- migration_20_sandbox_scopes.sql

BEGIN;

-- Add new OAuth scope to enum
ALTER TABLE app_integration.oauth_scopes
ADD CONSTRAINT valid_scope CHECK (scope_name IN (
    'read:cards',
    'write:collection',
    'read:pricing',
    'write:oauth',
    'sandbox'  -- NEW SCOPE
));

-- Optionally grant default scope to existing users
INSERT INTO user_management.user_oauth_scopes (user_id, scope_name)
SELECT unique_id, 'sandbox'
FROM user_management.users
WHERE unique_id NOT IN (
    SELECT user_id FROM user_management.user_oauth_scopes WHERE scope_name = 'sandbox'
)
ON CONFLICT DO NOTHING;

COMMIT;
```

### Scenario 3: Fix Data Consistency Issue

**Context:** Migration discovered to resolve corruption (e.g., duplicate cards).

**Migration:**

```sql
-- migration_25_deduplicate_artists.sql

BEGIN;

-- Find duplicate artists
WITH dups AS (
    SELECT artist_name, min(artist_id) AS first_id, array_agg(artist_id) AS all_ids
    FROM card_catalog.artists_ref
    GROUP BY artist_name
    HAVING count(*) > 1
)
-- Redirect all references to the first (keep) ID
UPDATE card_catalog.card_version cv
SET illustration_artist = (
    SELECT first_id FROM dups WHERE cv.illustration_artist = ANY(dups.all_ids)
)
WHERE EXISTS (
    SELECT 1 FROM dups WHERE cv.illustration_artist = ANY(dups.all_ids)
);

-- Delete duplicates
DELETE FROM card_catalog.artists_ref ar
WHERE EXISTS (
    WITH dups AS (
        SELECT artist_name, min(artist_id) AS first_id
        FROM card_catalog.artists_ref
        GROUP BY artist_name
        HAVING count(*) > 1
    )
    SELECT 1 FROM dups WHERE ar.artist_id != dups.first_id AND ar.artist_name = dups.artist_name
);

COMMIT;
```

---

## Testing Migrations

### Unit Test: Schema Validation

```python
# tests/migrations/test_migration_20_sandbox_scopes.py
import pytest
import asyncpg

@pytest.mark.asyncio
async def test_migration_adds_sandbox_scope(test_db_url):
    """Verify migration_20_sandbox_scopes adds the 'sandbox' scope."""
    
    connection = await asyncpg.connect(test_db_url)
    
    try:
        # Run migration
        with open('src/automana/database/SQL/migrations/migration_20_sandbox_scopes.sql') as f:
            await connection.execute(f.read())
        
        # Verify scope exists
        result = await connection.fetchval(
            "SELECT COUNT(*) FROM app_integration.oauth_scopes WHERE scope_name = 'sandbox'"
        )
        assert result > 0, "sandbox scope not created"
        
        # Verify existing users got the scope
        users_with_scope = await connection.fetchval(
            "SELECT COUNT(*) FROM user_management.user_oauth_scopes WHERE scope_name = 'sandbox'"
        )
        total_users = await connection.fetchval("SELECT COUNT(*) FROM user_management.users")
        assert users_with_scope > 0, "No users assigned sandbox scope"
        
    finally:
        await connection.close()
```

### Integration Test: Full Migration Sequence

```python
# tests/migrations/test_all_migrations.py
@pytest.mark.asyncio
async def test_all_migrations_apply(test_db_url):
    """Apply all migrations to a test database and verify schema integrity."""
    
    import subprocess
    import tempfile
    
    # Run all schema and migration files
    with tempfile.TemporaryDirectory() as tmpdir:
        result = subprocess.run([
            'bash',
            'src/automana/database/SQL/maintenance/rebuild_dev_db.sh',
            '--only', 'rebuild',
            '--db-url', test_db_url
        ], cwd='/home/arthur/projects/AutoMana')
        
        assert result.returncode == 0, "Migrations failed"
    
    # Verify key tables exist
    connection = await asyncpg.connect(test_db_url)
    try:
        tables = await connection.fetch("""
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
            ORDER BY table_schema, table_name
        """)
        
        expected_tables = {
            ('card_catalog', 'card_version'),
            ('card_catalog', 'unique_cards_ref'),
            ('pricing', 'price_observation'),
            ('pricing', 'print_price_daily'),
            ('user_management', 'users'),
        }
        
        actual = {(t['table_schema'], t['table_name']) for t in tables}
        assert expected_tables.issubset(actual), f"Missing tables: {expected_tables - actual}"
    finally:
        await connection.close()
```

### Backward Compatibility Test

```python
# tests/migrations/test_backward_compat.py
@pytest.mark.asyncio
async def test_migration_backward_compatible(test_db_url):
    """Verify old application code still works after migration."""
    
    import subprocess
    connection = await asyncpg.connect(test_db_url)
    
    try:
        # Apply migration
        with open('migration_20_sandbox_scopes.sql') as f:
            await connection.execute(f.read())
        
        # Simulate old code that doesn't know about 'sandbox' scope
        # (should not error)
        result = await connection.fetchval(
            "SELECT COUNT(*) FROM app_integration.oauth_scopes WHERE scope_name IN ('read:cards', 'write:collection')"
        )
        assert result > 0, "Old scopes were removed"
        
    finally:
        await connection.close()
```

---

## Rollback Strategy

### Rollback Approach 1: Full Database Restore

**Use when:** Migration corrupted or caused data loss.

```bash
# Restore from backup taken before migration
pg_restore -d automana automana_backup_20250501_before_migration.dump
```

**Pros:** Guaranteed to undo all changes
**Cons:** Lost all data since backup (may lose transactions)

### Rollback Approach 2: Reverse Migration

**Use when:** Migration is safe to reverse (e.g., just added a column).

**Create a reverse migration file:**

```sql
-- migration_20_sandbox_scopes_reverse.sql
-- Undoes migration_20_sandbox_scopes.sql

BEGIN;

-- Remove sandbox scope assignments
DELETE FROM user_management.user_oauth_scopes WHERE scope_name = 'sandbox';

-- Remove constraint on scope_name enum
ALTER TABLE app_integration.oauth_scopes
DROP CONSTRAINT valid_scope;

-- Add old constraint back (without sandbox)
ALTER TABLE app_integration.oauth_scopes
ADD CONSTRAINT valid_scope CHECK (scope_name IN (
    'read:cards',
    'write:collection',
    'read:pricing',
    'write:oauth'
));

COMMIT;
```

**Apply reverse migration:**

```bash
psql -d automana < migration_20_sandbox_scopes_reverse.sql
```

**Pros:** Surgical, preserves newer data
**Cons:** Only works for reversible migrations; data transformations can't be undone perfectly

### Rollback Approach 3: Re-execute with Conditions

**Use when:** Migration is idempotent and can be "reverted" by running it backward.

```sql
-- migration_18_pricing_tiers.sql (reversible)

BEGIN;

-- Check if table exists; if yes, drop (rollback)
-- Otherwise, create (forward)
DROP TABLE IF EXISTS pricing.print_price_weekly;

CREATE TABLE pricing.print_price_weekly (...);
-- ... rest of migration

COMMIT;
```

**Run for rollback:**
```bash
psql -d automana < migration_18_pricing_tiers.sql  # Drops and recreates (or leaves as-is if already exists)
```

---

## Deployment Strategy

### Pre-Deployment

1. **Test on staging:** Run migration on exact copy of production
2. **Review migration file:** Verify no hardcoded passwords or sensitive data
3. **Estimate duration:** Large tables = long locks; schedule downtime if needed
4. **Backup production:** `pg_dump -Fc automana > backup_20250501.dump`

### Deployment (Zero-Downtime Ideal)

**Option A: Blue-Green (safest)**

1. Deploy new schema to a separate database
2. Verify schema and run sanity checks
3. Cutover: Change application connection string to new DB
4. Keep old DB as backup for 24 hours

**Option B: In-Place Migrations (typical)**

1. Run migration during low-traffic window (e.g., 2 AM UTC)
2. Monitor locks: `SELECT * FROM pg_locks WHERE mode != 'AccessShareLock'`
3. If migration hangs, kill blocking query: `SELECT pg_cancel_backend(pid)`
4. Verify application still works post-migration

**Option C: Online Schema Change Tools (for large tables)**

Use tools like `pg_chameleon` or `pg_repack` for zero-downtime large table modifications:

```bash
# Install pg_repack
sudo apt-get install postgresql-13-repack

# Rebuild table without exclusive lock
pg_repack -t pricing.price_observation -d automana
```

### Post-Deployment

1. **Monitor application logs:** Look for "column not found" or schema mismatch errors
2. **Check table stats:** `ANALYZE` to refresh query planner
3. **Verify data integrity:**
   ```sql
   SELECT COUNT(*) FROM card_catalog.card_version;
   SELECT COUNT(*) FROM pricing.price_observation;
   -- Compare to expected counts
   ```
4. **Re-index if needed:** `REINDEX INDEX CONCURRENTLY idx_name`

### CI/CD Integration

**Example (GitHub Actions):**

```yaml
# .github/workflows/deploy.yml
name: Deploy to Production

on:
  push:
    branches: [main]

jobs:
  migrate:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15-timescaledb
        env:
          POSTGRES_PASSWORD: postgres
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v3
      - name: Run migrations
        run: |
          psql -h localhost -U postgres -d automana < \
            src/automana/database/SQL/migrations/*.sql
      - name: Verify schema
        run: |
          psql -h localhost -U postgres -d automana -c \
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'card_catalog'"
```

---

## Real Examples from Codebase

### Example 1: migration_17_foil_finish_suffix.sql

**Context:** Add fine-grained card finish codes (Surge Foil, Ripple Foil) instead of generic FOIL.

**File:** [`migration_17_foil_finish_suffix.sql`](../../../src/automana/database/SQL/migrations/migration_17_foil_finish_suffix.sql)

**Key steps:**
1. Insert new finish codes (SURGE_FOIL, RIPPLE_FOIL, RAINBOW_FOIL)
2. Create suffix mapping table (ties MTGStocks name → finish_id)
3. Update three pricing procedures to use granular finishes
4. Safe to re-run: all INSERTs use `ON CONFLICT DO NOTHING`

### Example 2: migration_18_pricing_tiers.sql

**Context:** Restructure pricing from single table to three-tier (observation → daily → weekly).

**File:** [`migration_18_pricing_tiers.sql`](../../../src/automana/database/SQL/migrations/migration_18_pricing_tiers.sql)

**Key steps:**
1. Create new hypertables (print_price_daily, print_price_weekly)
2. Create stored procedures (refresh_daily_prices, archive_to_weekly)
3. Set up compression policies
4. Create tier_watermark tracking table
5. Create indexes for query performance

**Complexity:** High (restructures core pricing schema), but safe because:
- New tables created (no existing data harmed)
- Old table kept intact (no data loss)
- Application code updated separately to start writing to new tables

### Example 3: migration_19_refresh_views_security_definer.sql

**Context:** Fix view permissions to work with RBAC roles.

**File:** [`migration_19_refresh_views_security_definer.sql`](../../../src/automana/database/SQL/migrations/migration_19_refresh_views_security_definer.sql)

**Key step:**
```sql
CREATE OR REPLACE VIEW user_management.v_active_sessions
WITH (security_definer = true)
AS SELECT ... FROM ...;
```

**Why SECURITY DEFINER?**
- View runs with owner's privileges (db_owner)
- Allows app_readonly role to see data even if they don't have direct table access
- Essential for role-based access control

---

## See Also

- [`docs/DATABASE_SCHEMA.md`](DATABASE_SCHEMA.md) — Table definitions affected by migrations
- [`docs/DEPLOYMENT.md`](../DEPLOYMENT.md) — Deployment pipeline and infrastructure
- [`docs/TROUBLESHOOTING.md`](../TROUBLESHOOTING.md) — Migration debugging tips
- [`src/automana/database/SQL/schemas/`](../../../src/automana/database/SQL/schemas/) — Initial schema files
- [`src/automana/database/SQL/migrations/`](../../../src/automana/database/SQL/migrations/) — All migration files
