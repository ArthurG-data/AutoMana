# DB Migration Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fragile manual migration process with Flyway, squash 39 historical migrations into clean schema files, and split schemas into core (prod + dev) and pipeline (dev only) halves.

**Architecture:** All 39 existing migration files are folded back into the schema files (squash), which are then reorganized into `schemas/core/` and `schemas/pipeline/`. Flyway tracks all future migrations from V1 onward using two config files — `flyway-dev.conf` (both directories) and `flyway-prod.conf` (core only). Existing DBs are stamped with `flyway baseline --baselineVersion=0` once.

**Tech Stack:** Flyway 10 (Docker image `flyway/flyway:10`), PostgreSQL 17 / TimescaleDB, bash

**Spec:** `docs/superpowers/specs/2026-06-01-db-migration-management-design.md`

---

## Squash patterns reference

Before starting, read this — it defines how to fold each migration type:

| Migration contains | How to squash |
|---|---|
| `ALTER TABLE t ADD COLUMN c TYPE` | Add `c TYPE` to the `CREATE TABLE t` definition in the schema file |
| `ALTER TABLE t DROP COLUMN c` | Remove column `c` from `CREATE TABLE t` |
| `ALTER TABLE t ADD CONSTRAINT …` | Add the constraint inside `CREATE TABLE t` or as a standalone `ALTER` after it |
| `ALTER TABLE t DROP CONSTRAINT …` | Remove the constraint from `CREATE TABLE t` |
| `CREATE INDEX …` | Add the index after the relevant `CREATE TABLE` |
| `DROP INDEX …` | Remove that index from the schema file |
| `CREATE OR REPLACE FUNCTION/PROCEDURE` | Replace the old function body in the schema file with the new one from the migration |
| `DROP MATERIALIZED VIEW … CASCADE` + recreate | Replace the old MV definition in the schema file with the new one |
| `INSERT INTO … VALUES … ON CONFLICT DO NOTHING` (reference data seeds) | Keep the INSERT in the schema file — it must be idempotent |
| `UPDATE … SET` (data corrections) | Do NOT add to schema — these correct stale live data; a fresh install won't have stale data |

**Verification pattern** used after every squash task:

```bash
# Dump structure of target table/object from live DB
docker exec automana-postgres-dev psql -U automana_admin automana -c "\d+ <schema>.<table>"
```

After the full squash (Task 11), a structural diff against a fresh DB is the final gate.

---

## File map

**Created:**
- `src/automana/database/SQL/schemas/core/` — all core schema files (prod + dev)
- `src/automana/database/SQL/schemas/pipeline/` — pipeline-only schema files (dev only)
- `src/automana/database/SQL/migrations/core/` — future core migrations (V1+)
- `src/automana/database/SQL/migrations/pipeline/` — future pipeline migrations (V1+)
- `src/automana/database/SQL/migrations/archive/` — historical migration_XX_*.sql files
- `src/automana/database/SQL/flyway-dev.conf`
- `src/automana/database/SQL/flyway-prod.conf`

**Modified:**
- `deploy/docker-compose.dev.yml` — add `flyway` service
- `src/automana/database/SQL/maintenance/rebuild_dev_db.sh` — use Flyway in `--preserve-data` path

**Renamed/moved** (all 13 schema files split into core/ or pipeline/):

| Old | New location | Side |
|---|---|---|
| `01_set_schema.sql` | `core/01_set_schema.sql` | core |
| `02_card_schema.sql` | `core/02_card_schema.sql` | core |
| `03_users.sql` | `core/03_users.sql` | core |
| `04_online_shop.sql` | `core/04_collection.sql` | core |
| `05_ebay.sql` | `core/05_ebay.sql` | core |
| `08_ebay_orders.sql` | `core/08_ebay_orders.sql` | core |
| `08_markets_prices.sql` | `core/08_markets_prices.sql` | core |
| `12_sealed_pricing.sql` | `core/12_sealed_pricing.sql` | core |
| *(new)* | `core/13_content.sql` | core |
| `06_prices.sql` (split) | `core/06_prices.sql` + `pipeline/06_prices_pipeline.sql` | both |
| `07_shopify_staging.sql` | `pipeline/07_shopify.sql` | pipeline |
| `09_ops_schema.sql` | `pipeline/09_ops.sql` | pipeline |
| `10_mtgjson_schema.sql` | `pipeline/10_mtgjson.sql` | pipeline |
| `11_staging_schema.sql` | *(delete — file is empty)* | — |

---

## Task 1: Create directory structure + Flyway config files

**Files:**
- Create: `src/automana/database/SQL/schemas/core/` (directory)
- Create: `src/automana/database/SQL/schemas/pipeline/` (directory)
- Create: `src/automana/database/SQL/migrations/core/` (directory)
- Create: `src/automana/database/SQL/migrations/pipeline/` (directory)
- Create: `src/automana/database/SQL/migrations/archive/` (directory)
- Create: `src/automana/database/SQL/flyway-dev.conf`
- Create: `src/automana/database/SQL/flyway-prod.conf`

- [ ] **Step 1: Create directories**

```bash
mkdir -p src/automana/database/SQL/schemas/core
mkdir -p src/automana/database/SQL/schemas/pipeline
mkdir -p src/automana/database/SQL/migrations/core
mkdir -p src/automana/database/SQL/migrations/pipeline
mkdir -p src/automana/database/SQL/migrations/archive
```

- [ ] **Step 2: Create flyway-dev.conf**

```bash
cat > src/automana/database/SQL/flyway-dev.conf << 'EOF'
flyway.url=jdbc:postgresql://postgres:5432/automana
flyway.user=automana_admin
flyway.locations=filesystem:/flyway/migrations/core,filesystem:/flyway/migrations/pipeline
flyway.baselineOnMigrate=false
flyway.validateOnMigrate=true
flyway.outOfOrder=false
EOF
```

- [ ] **Step 3: Create flyway-prod.conf**

```bash
cat > src/automana/database/SQL/flyway-prod.conf << 'EOF'
flyway.url=jdbc:postgresql://<prod-host>:5432/automana
flyway.user=automana_admin
flyway.locations=filesystem:/flyway/migrations/core
flyway.baselineOnMigrate=false
flyway.validateOnMigrate=true
flyway.outOfOrder=false
EOF
```

Note: `<prod-host>` is a placeholder — fill in when prod DB hosting is confirmed.
Password is always provided via `FLYWAY_PASSWORD` env var, never hardcoded.

- [ ] **Step 4: Add .gitkeep files to empty migration dirs**

```bash
touch src/automana/database/SQL/migrations/core/.gitkeep
touch src/automana/database/SQL/migrations/pipeline/.gitkeep
```

- [ ] **Step 5: Commit**

```bash
git add src/automana/database/SQL/schemas/core \
        src/automana/database/SQL/schemas/pipeline \
        src/automana/database/SQL/migrations/core \
        src/automana/database/SQL/migrations/pipeline \
        src/automana/database/SQL/migrations/archive \
        src/automana/database/SQL/flyway-dev.conf \
        src/automana/database/SQL/flyway-prod.conf
git commit -m "feat(db): add Flyway directory structure and config files"
```

---

## Task 2: Add Flyway service to docker-compose.dev.yml

**Files:**
- Modify: `deploy/docker-compose.dev.yml`

- [ ] **Step 1: Open docker-compose.dev.yml and add the flyway service after the postgres service definition**

Find the section with the `postgres` service and add the following after it (before the next service):

```yaml
  flyway:
    image: flyway/flyway:10
    depends_on:
      postgres:
        condition: service_healthy
    volumes:
      - ../src/automana/database/SQL/migrations:/flyway/migrations
      - ../src/automana/database/SQL/flyway-dev.conf:/flyway/conf/flyway.conf
    environment:
      FLYWAY_PASSWORD: ${AUTOMANA_ADMIN_DB_PASSWORD}
    command: migrate
    restart: "no"
    networks:
      - default
```

Note: The volume path `../src/...` assumes the compose file lives in `deploy/`. Adjust the relative path if needed by checking `docker-compose.dev.yml`'s location relative to the repo root.

- [ ] **Step 2: Verify the compose file parses correctly**

```bash
docker compose -f deploy/docker-compose.dev.yml config --quiet
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add deploy/docker-compose.dev.yml
git commit -m "feat(db): add Flyway migrate service to dev compose"
```

---

## Task 3: Squash card catalog schemas (01_set_schema + 02_card_schema)

**Migrations to fold in:**

| File | Lines | What it does | Target schema |
|---|---|---|---|
| `migration_28_card_back_id.sql` | 5 | ADD COLUMN card_back_id to card_version | 02_card_schema.sql |
| `migration_29_japanese_card_filter.sql` | 278 | DROP + recreate `v_card_versions_complete` MV with JP filter | 02_card_schema.sql |
| `migration_30_face_illustration_image_uris.sql` | 46 | ADD COLUMN face_illustration_id and image_uri columns | 02_card_schema.sql |
| `migration_46_fix_cv_name_token_resolution.sql` | 1030 | CREATE OR REPLACE `load_staging_prices_batched` + `resolve_price_rejects` (lives in 06_prices — skip here) | skip for this task |
| `migration_49_dfc_uuid_alias.sql` | 338 | Add DFC uuid alias view/table | 02_card_schema.sql |
| `migration_57_drop_redundant_indexes.sql` | 27 | DROP 4 redundant indexes (card_catalog ones: `idx_artists_name`, `sets_set_code_idx`, `idx_card_version_set_id`) | 02_card_schema.sql + 01_set_schema.sql |
| `migration_58_unique_cards_fk_and_tz_fixes.sql` | 39 | ADD CONSTRAINT fk_unique_cards_other_face + index on unique_cards_ref | 02_card_schema.sql |
| `migration_60_mtgstock_identifier.sql` | 5 | INSERT 'mtgstock_id' into card_identifier_ref | 02_card_schema.sql |
| `migration_61_add_pricecharting_identifier.sql` | 21 | INSERT 'pricecharting_id' into card_identifier_ref | 02_card_schema.sql |

**Files:**
- Copy then modify: `src/automana/database/SQL/schemas/core/01_set_schema.sql`
- Copy then modify: `src/automana/database/SQL/schemas/core/02_card_schema.sql`

- [ ] **Step 1: Copy the two schema files into core/**

```bash
cp src/automana/database/SQL/schemas/01_set_schema.sql \
   src/automana/database/SQL/schemas/core/01_set_schema.sql
cp src/automana/database/SQL/schemas/02_card_schema.sql \
   src/automana/database/SQL/schemas/core/02_card_schema.sql
```

- [ ] **Step 2: Fold migration_28 into core/02_card_schema.sql**

Read `migrations/migration_28_card_back_id.sql` (5 lines). Find `CREATE TABLE card_catalog.card_version` in `core/02_card_schema.sql` and add the column from the migration to the column list. Remove the migration's ALTER TABLE statement — the column is now part of the CREATE TABLE.

- [ ] **Step 3: Fold migration_30 into core/02_card_schema.sql**

Read `migrations/migration_30_face_illustration_image_uris.sql`. Find `CREATE TABLE card_catalog.card_version` and `card_catalog.card_face` and add the columns listed. Follow the same pattern as Step 2.

- [ ] **Step 4: Fold migration_29 into core/02_card_schema.sql**

Read `migrations/migration_29_japanese_card_filter.sql`. This file `DROP MATERIALIZED VIEW v_card_versions_complete CASCADE` then recreates it with a JP filter. Find the old `CREATE MATERIALIZED VIEW card_catalog.v_card_versions_complete` in `core/02_card_schema.sql` and replace the entire definition with the new one from migration_29. Also replace any dependent views that were dropped + recreated in the migration.

- [ ] **Step 5: Fold migration_49 into core/02_card_schema.sql**

Read `migrations/migration_49_dfc_uuid_alias.sql`. Add whatever new tables/views/aliases it creates to `core/02_card_schema.sql` after the relevant existing objects.

- [ ] **Step 6: Fold migration_57 (card_catalog indexes) into core/**

Read `migrations/migration_57_drop_redundant_indexes.sql`. It drops four indexes. For each one in `card_catalog`:
- Remove `idx_artists_name` from `core/01_set_schema.sql` (it's a duplicate of the UNIQUE constraint)
- Remove `sets_set_code_idx` from `core/01_set_schema.sql`
- Remove `idx_card_version_set_id` from `core/02_card_schema.sql`
(The fourth index — `idx_sealed_ext_id_type_value` — belongs to sealed pricing; handle it in Task 9.)

- [ ] **Step 7: Fold migration_58 (unique_cards FK + index) into core/02_card_schema.sql**

Read `migrations/migration_58_unique_cards_fk_and_tz_fixes.sql`. Add the FK constraint and index to `unique_cards_ref` in `core/02_card_schema.sql`. The Shopify timestamp fix from the same migration belongs to the pipeline schema — skip it here.

- [ ] **Step 8: Fold migration_60 + migration_61 (identifier seeds) into core/02_card_schema.sql**

Read both files. Each is an `INSERT INTO card_catalog.card_identifier_ref (identifier_name) VALUES (...) ON CONFLICT DO NOTHING`. Add both INSERTs at the end of `core/02_card_schema.sql` after the table + seed data for `card_identifier_ref`.

- [ ] **Step 9: Verify structure matches live DB**

```bash
docker exec automana-postgres-dev psql -U automana_admin automana \
  -c "\d card_catalog.card_version" \
  -c "\d card_catalog.v_card_versions_complete" \
  -c "SELECT identifier_name FROM card_catalog.card_identifier_ref ORDER BY 1;"
```

Confirm the columns, view definition, and identifier rows match what you see in the new schema files.

- [ ] **Step 10: Commit**

```bash
git add src/automana/database/SQL/schemas/core/01_set_schema.sql \
        src/automana/database/SQL/schemas/core/02_card_schema.sql
git commit -m "feat(db): squash card_catalog migrations into core schemas"
```

---

## Task 4: Squash users + collection schemas (03_users + 04_online_shop)

**Migrations to fold in:**

| File | Lines | What it does | Target schema |
|---|---|---|---|
| `migration_41_collection_items_unique_constraint.sql` | 12 | ADD UNIQUE constraint on collection_items | 04_collection.sql |
| `migration_42_collection_items_status.sql` | 15 | ADD COLUMN status to collection_items | 04_collection.sql |
| `migration_44_drop_collection_items_unique_constraint.sql` | 11 | DROP the same constraint added in 41 | 04_collection.sql |
| `migration_43_password_reset_tokens.sql` | 11 | CREATE TABLE password_reset_tokens | 03_users.sql |
| `migration_50_collection_wishlist.sql` | 11 | ADD COLUMN is_wishlist to collection_items | 04_collection.sql |
| `migration_63_collection_game_code.sql` (partial) | 14 | ADD COLUMN game_code to markets.collection_handles; UPDATE GG Brisbane URL | 04_collection.sql + 08_markets_prices.sql |

**Files:**
- Copy then modify: `src/automana/database/SQL/schemas/core/03_users.sql`
- Copy then modify: `src/automana/database/SQL/schemas/core/04_collection.sql`

- [ ] **Step 1: Copy schemas into core/**

```bash
cp src/automana/database/SQL/schemas/03_users.sql \
   src/automana/database/SQL/schemas/core/03_users.sql
cp src/automana/database/SQL/schemas/04_online_shop.sql \
   src/automana/database/SQL/schemas/core/04_collection.sql
```

- [ ] **Step 2: Fold migration_43 into core/03_users.sql**

Read `migrations/migration_43_password_reset_tokens.sql`. It creates `user_management.password_reset_tokens`. Add the full `CREATE TABLE` definition into `core/03_users.sql` after the `users` table.

- [ ] **Step 3: Fold migrations 41, 42, 44, 50 into core/04_collection.sql**

Read all four files. Apply in order:
- 41 adds a UNIQUE constraint → add it to the CREATE TABLE, then
- 44 drops that same constraint → remove it from CREATE TABLE (net result: no constraint)
- 42 adds `status` column → add to CREATE TABLE
- 50 adds `is_wishlist BOOLEAN NOT NULL DEFAULT false` → add to CREATE TABLE

The net result after 41+44 is no unique constraint on collection_items. Only 42 and 50 survive.

- [ ] **Step 4: Fold migration_63 (collection_handles column) into core/**

Read `migrations/migration_63_collection_game_code.sql`. It:
1. Updates GG Brisbane URL in `markets.market_ref` — this is a data correction; **do not add to schema** (stale data won't exist on fresh install).
2. Adds `game_code VARCHAR` to `markets.collection_handles` → add to the CREATE TABLE in `core/08_markets_prices.sql` (handle in Task 5 when you process that file, or open it now and add the column).

- [ ] **Step 5: Verify**

```bash
docker exec automana-postgres-dev psql -U automana_admin automana \
  -c "\d user_management.password_reset_tokens" \
  -c "\d collection_management.collection_items" \
  -c "\d markets.collection_handles"
```

Confirm columns match the new schema files.

- [ ] **Step 6: Commit**

```bash
git add src/automana/database/SQL/schemas/core/03_users.sql \
        src/automana/database/SQL/schemas/core/04_collection.sql
git commit -m "feat(db): squash users + collection migrations into core schemas"
```

---

## Task 5: Squash eBay + markets schemas (05_ebay, 08_ebay_orders, 08_markets_prices)

**Migrations to fold in:**

| File | Lines | What it does | Target schema |
|---|---|---|---|
| `migration_31_ebay_listings_scrape.sql` | 51 | ADD columns to ebay_active_listings (scrape columns) | 05_ebay.sql |
| `migration_32_listing_pending_actions.sql` | 33 | CREATE TABLE listing_pending_actions | 05_ebay.sql |
| `migration_37_listing_product_mapping.sql` | 53 | ADD product mapping columns to ebay_active_listings | 05_ebay.sql |
| `migration_38_ebay_active_listings_title.sql` | 6 | ADD COLUMN title to ebay_active_listings | 05_ebay.sql |
| `migration_39_ebay_active_listings_match_score.sql` | 4 | ADD COLUMN match_score | 05_ebay.sql |
| `migration_45_ebay_global_market_scraper.sql` | 33 | CREATE TABLE ebay_global_scrape_results or similar | 05_ebay.sql |
| `migration_47_ebay_scrape_targets_priority.sql` | 9 | ADD COLUMN priority to ebay_scrape_targets | 05_ebay.sql |
| `migration_60_drop_ebay_scrape_targets.sql` | 23 | DROP TABLE ebay_scrape_targets | 05_ebay.sql |
| `migration_63_collection_game_code.sql` (game_code column) | — | ADD COLUMN game_code to markets.collection_handles | 08_markets_prices.sql |

**Files:**
- Copy then modify: `src/automana/database/SQL/schemas/core/05_ebay.sql`
- Copy then modify: `src/automana/database/SQL/schemas/core/08_ebay_orders.sql`
- Copy then modify: `src/automana/database/SQL/schemas/core/08_markets_prices.sql`

- [ ] **Step 1: Copy schemas into core/**

```bash
cp src/automana/database/SQL/schemas/05_ebay.sql         src/automana/database/SQL/schemas/core/05_ebay.sql
cp src/automana/database/SQL/schemas/08_ebay_orders.sql  src/automana/database/SQL/schemas/core/08_ebay_orders.sql
cp src/automana/database/SQL/schemas/08_markets_prices.sql src/automana/database/SQL/schemas/core/08_markets_prices.sql
```

- [ ] **Step 2: Fold eBay listing migrations (31, 37, 38, 39) into core/05_ebay.sql**

Read each file. Find `CREATE TABLE ebay.ebay_active_listings` (or equivalent) in `core/05_ebay.sql` and add all columns from these four migrations to the column list.

- [ ] **Step 3: Fold migration_32 into core/05_ebay.sql**

Read `migration_32_listing_pending_actions.sql`. It creates a new table. Add the full `CREATE TABLE` definition to `core/05_ebay.sql`.

- [ ] **Step 4: Fold migration_45 into core/05_ebay.sql**

Read `migration_45_ebay_global_market_scraper.sql`. Add whatever table/columns it creates to `core/05_ebay.sql`.

- [ ] **Step 5: Fold migration_47 into core/05_ebay.sql**

Read `migration_47_ebay_scrape_targets_priority.sql`. It adds a `priority` column to `ebay_scrape_targets`. **Then** fold migration_60 which drops that entire table. Net result: `ebay_scrape_targets` is dropped — remove the table entirely from `core/05_ebay.sql`.

- [ ] **Step 6: Fold migration_63 game_code into core/08_markets_prices.sql**

Find `CREATE TABLE markets.collection_handles` in `core/08_markets_prices.sql` and add `game_code VARCHAR` to the column list.

- [ ] **Step 7: Verify**

```bash
docker exec automana-postgres-dev psql -U automana_admin automana \
  -c "\d ebay.ebay_active_listings" \
  -c "\dt ebay.*" \
  -c "\d markets.collection_handles"
```

Confirm `ebay_scrape_targets` is gone, all new columns are present, and `game_code` is in `collection_handles`.

- [ ] **Step 8: Commit**

```bash
git add src/automana/database/SQL/schemas/core/05_ebay.sql \
        src/automana/database/SQL/schemas/core/08_ebay_orders.sql \
        src/automana/database/SQL/schemas/core/08_markets_prices.sql
git commit -m "feat(db): squash eBay + markets migrations into core schemas"
```

---

## Task 6: Squash prices schema — core half

This is the most complex task. `06_prices.sql` (2344 lines) gets split into two files. This task produces `core/06_prices.sql` containing Tier 2/3/snapshot tables and all stored procedures. The pipeline half (Tier 1 + staging) is Task 7.

**What belongs in core/06_prices.sql:**
- `pricing.source_product` and related source reference tables
- `pricing.print_price_daily` (Tier 2)
- `pricing.print_price_weekly` (Tier 3)
- `pricing.print_price_latest` (snapshot)
- `pricing.print_price_watermark`
- All stored procedures: `refresh_daily_prices`, `archive_to_weekly`, `load_staging_prices_batched`, `resolve_price_rejects`, etc.
- `pricing.shopify_staging_raw` (used by the scraper, core)

**Migrations to fold into core/06_prices.sql:**

| File | Lines | What it does |
|---|---|---|
| `migration_33_scryfall_prices.sql` | 21 | Add Scryfall as a source in `pricing.source_ref` |
| `migration_34_opentcg_source.sql` | 17 | Add OpenTCG as a source in `pricing.source_ref` |
| `migration_36_card_price_spark_mv.sql` | 119 | CREATE MATERIALIZED VIEW card_price_spark |
| `migration_40_mtgstock_link_fixes.sql` | 1085 | Seed `mtgstock_art_set_map` + `mtgstock_token_set_map`; CREATE OR REPLACE `load_staging_prices_batched` + `resolve_price_rejects` |
| `migration_46_fix_cv_name_token_resolution.sql` | 1030 | CREATE OR REPLACE `load_staging_prices_batched` + `resolve_price_rejects` (supersedes migration_40's version) |
| `migration_58_unique_cards_fk_and_tz_fixes.sql` (partial) | — | ALTER `shopify_staging_raw.scraped_at` to TIMESTAMPTZ |
| `migration_59_usd_market_spark.sql` | 123 | CREATE MATERIALIZED VIEW usd_market_spark |
| `migration_62_pricecharting_card_map.sql` | 43 | CREATE TABLE `pricing.pricecharting_card_map` |

**Files:**
- Create: `src/automana/database/SQL/schemas/core/06_prices.sql`

- [ ] **Step 1: Copy 06_prices.sql to core/ as a starting point**

```bash
cp src/automana/database/SQL/schemas/06_prices.sql \
   src/automana/database/SQL/schemas/core/06_prices.sql
```

You'll remove the pipeline sections in Task 7. For now work only on folding migrations into this copy.

- [ ] **Step 2: Fold migrations 33 + 34 (source seeds)**

Read both files. Each inserts a row into `pricing.source_ref`. Find the existing source seeds in `core/06_prices.sql` and add the Scryfall and OpenTCG rows as `INSERT ... ON CONFLICT DO NOTHING`.

- [ ] **Step 3: Fold migration_36 (card_price_spark MV)**

Read `migration_36_card_price_spark_mv.sql`. Add the `CREATE MATERIALIZED VIEW pricing.card_price_spark` definition to `core/06_prices.sql` after the snapshot table.

- [ ] **Step 4: Fold migration_40 seeds into core/06_prices.sql**

Read `migration_40_mtgstock_link_fixes.sql`. The first two sections are `INSERT INTO pricing.mtgstock_art_set_map` and `INSERT INTO pricing.mtgstock_token_set_map` with `ON CONFLICT DO NOTHING`. Find the table definitions in the schema file and add these INSERTs after the CREATE TABLE. The stored procedure replacements from migration_40 are superseded by migration_46 — **skip the procedure parts of migration_40** and apply migration_46's versions instead (next step).

- [ ] **Step 5: Fold migration_46 (procedure replacements) into core/06_prices.sql**

Read `migration_46_fix_cv_name_token_resolution.sql`. It contains `CREATE OR REPLACE FUNCTION/PROCEDURE` for `load_staging_prices_batched` and `resolve_price_rejects`. Find the old versions of these functions in `core/06_prices.sql` and replace them entirely with the versions from migration_46. This is the final correct version.

- [ ] **Step 6: Fold migration_58 (shopify_staging_raw timestamp) into core/06_prices.sql**

Read `migration_58_unique_cards_fk_and_tz_fixes.sql`. Find `shopify_staging_raw.scraped_at` in `core/06_prices.sql` and change its type to `TIMESTAMPTZ` (it was `TIMESTAMP WITHOUT TIME ZONE`).

- [ ] **Step 7: Fold migration_59 (usd_market_spark MV)**

Read `migration_59_usd_market_spark.sql`. Add the `CREATE MATERIALIZED VIEW pricing.usd_market_spark` definition to `core/06_prices.sql`.

- [ ] **Step 8: Fold migration_62 (pricecharting_card_map)**

Read `migration_62_pricecharting_card_map.sql`. Add the `CREATE TABLE pricing.pricecharting_card_map` definition to `core/06_prices.sql`.

- [ ] **Step 9: Verify**

```bash
docker exec automana-postgres-dev psql -U automana_admin automana \
  -c "\d pricing.print_price_daily" \
  -c "\d pricing.print_price_latest" \
  -c "\d pricing.pricecharting_card_map" \
  -c "\d pricing.card_price_spark" \
  -c "SELECT source_name FROM pricing.source_ref ORDER BY 1;"
```

Confirm Tier 2/3/snapshot tables are present, views exist, sources include Scryfall + OpenTCG.

- [ ] **Step 10: Commit**

```bash
git add src/automana/database/SQL/schemas/core/06_prices.sql
git commit -m "feat(db): squash pricing migrations into core/06_prices.sql"
```

---

## Task 7: Split prices schema — remove pipeline objects from core/06_prices.sql

**What to remove from core/06_prices.sql (these go to pipeline/06_prices_pipeline.sql):**
- `pricing.price_observation` hypertable + compression policy + its indexes
- `pricing.stg_price_observation` unlogged table + its index
- `pricing.stg_price_observation_reject` table
- `pricing.raw_mtg_stock_price` table (if present in 06_prices.sql)
- `load_staging_prices_batched` stored procedure (it writes to `price_observation` — pipeline only)
- `resolve_price_rejects` stored procedure (same)
- Any `SELECT create_hypertable(...)` calls for `price_observation`
- `SELECT add_compression_policy(...)` for `price_observation`

**Files:**
- Modify: `src/automana/database/SQL/schemas/core/06_prices.sql` (remove pipeline objects)
- Create: `src/automana/database/SQL/schemas/pipeline/06_prices_pipeline.sql`

- [ ] **Step 1: Create pipeline/06_prices_pipeline.sql**

Cut the following sections from `core/06_prices.sql` and paste them into a new `pipeline/06_prices_pipeline.sql`:
- `CREATE TABLE pricing.price_observation` + `SELECT create_hypertable(...)` + compression + indexes
- `CREATE UNLOGGED TABLE pricing.stg_price_observation` + its index
- `CREATE TABLE pricing.stg_price_observation_reject`
- `CREATE OR REPLACE PROCEDURE pricing.load_staging_prices_batched` (the full procedure)
- `CREATE OR REPLACE FUNCTION pricing.resolve_price_rejects` (the full function)

Add appropriate schema header and grants to `pipeline/06_prices_pipeline.sql`.

- [ ] **Step 2: Verify core/06_prices.sql has no pipeline references**

```bash
grep -n "price_observation\|stg_price\|load_staging_prices" \
  src/automana/database/SQL/schemas/core/06_prices.sql
```

Expected: no matches (or only comments/references in non-DDL context).

- [ ] **Step 3: Verify pipeline schema has all pipeline objects**

```bash
grep -c "CREATE TABLE\|CREATE.*PROCEDURE\|create_hypertable" \
  src/automana/database/SQL/schemas/pipeline/06_prices_pipeline.sql
```

Expected: at least 4 matches (3 tables + 1 procedure or more).

- [ ] **Step 4: Commit**

```bash
git add src/automana/database/SQL/schemas/core/06_prices.sql \
        src/automana/database/SQL/schemas/pipeline/06_prices_pipeline.sql
git commit -m "feat(db): split prices schema into core/pipeline halves"
```

---

## Task 8: Squash pipeline-only schemas (shopify, ops, mtgjson)

**Migrations to fold in:**

| File | Lines | Target schema | What it does |
|---|---|---|---|
| `migration_46_shopify_market_pipeline.sql` | 46 | pipeline/07_shopify.sql | ADD tables/columns for Shopify market pipeline |
| `migration_48_wire_gg_markets.sql` | 24 | pipeline/07_shopify.sql | INSERT Good Games market rows |
| `migration_35_mtgjson_bootstrap_product_mapping.sql` | 395 | pipeline/10_mtgjson.sql | CREATE OR REPLACE procedure for MTGJson bootstrap |

**Files:**
- Copy then modify: `src/automana/database/SQL/schemas/pipeline/07_shopify.sql`
- Copy then modify: `src/automana/database/SQL/schemas/pipeline/09_ops.sql`
- Copy then modify: `src/automana/database/SQL/schemas/pipeline/10_mtgjson.sql`

- [ ] **Step 1: Copy schemas into pipeline/**

```bash
cp src/automana/database/SQL/schemas/07_shopify_staging.sql \
   src/automana/database/SQL/schemas/pipeline/07_shopify.sql
cp src/automana/database/SQL/schemas/09_ops_schema.sql \
   src/automana/database/SQL/schemas/pipeline/09_ops.sql
cp src/automana/database/SQL/schemas/10_mtgjson_schema.sql \
   src/automana/database/SQL/schemas/pipeline/10_mtgjson.sql
```

- [ ] **Step 2: Fold migration_46_shopify + migration_48 into pipeline/07_shopify.sql**

Read both files. Apply:
- `migration_46_shopify_market_pipeline.sql` — add any new tables/columns to `pipeline/07_shopify.sql`
- `migration_48_wire_gg_markets.sql` — adds rows to `markets.market_ref` with `ON CONFLICT DO NOTHING`. Add the INSERT at the end of `pipeline/07_shopify.sql`.

- [ ] **Step 3: Fold migration_35 into pipeline/10_mtgjson.sql**

Read `migration_35_mtgjson_bootstrap_product_mapping.sql`. It:
1. Backfills existing staging rows (data correction — skip, don't add to schema)
2. CREATE OR REPLACE PROCEDURE for MTGJson bootstrap

Find the old procedure in `pipeline/10_mtgjson.sql` and replace it with the version from migration_35.

- [ ] **Step 4: Verify**

```bash
docker exec automana-postgres-dev psql -U automana_admin automana \
  -c "\dt markets.*" \
  -c "\dt ops.*" \
  -c "\dt pricing.mtgjson*"
```

- [ ] **Step 5: Commit**

```bash
git add src/automana/database/SQL/schemas/pipeline/07_shopify.sql \
        src/automana/database/SQL/schemas/pipeline/09_ops.sql \
        src/automana/database/SQL/schemas/pipeline/10_mtgjson.sql
git commit -m "feat(db): squash pipeline-only schemas (shopify, ops, mtgjson)"
```

---

## Task 9: Squash sealed pricing + create article schema

**Migrations to fold into core/12_sealed_pricing.sql:**

| File | Lines | What it does |
|---|---|---|
| `migration_51_sealed_product_pricing.sql` | 326 | Core sealed pricing tables |
| `migration_52_graded_card_conditions.sql` | 37 | ADD condition reference data |
| `migration_53_sealed_external_identifiers.sql` | 58 | ADD external identifier tables |
| `migration_54_sealed_catalog_schema.sql` | 148 | Extend sealed catalog |
| `migration_55_sealed_type_subtype_ref.sql` | 80 | ADD type/subtype reference tables |
| `migration_56_sealed_ref_grants.sql` | 16 | GRANT statements for new tables |
| `migration_57_drop_redundant_indexes.sql` (partial) | — | DROP `idx_sealed_ext_id_type_value` |

**Files:**
- Copy then modify: `src/automana/database/SQL/schemas/core/12_sealed_pricing.sql`
- Create: `src/automana/database/SQL/schemas/core/13_content.sql`

- [ ] **Step 1: Copy 12_sealed_pricing.sql into core/**

```bash
cp src/automana/database/SQL/schemas/12_sealed_pricing.sql \
   src/automana/database/SQL/schemas/core/12_sealed_pricing.sql
```

- [ ] **Step 2: Fold sealed migrations 51–56 into core/12_sealed_pricing.sql**

Read each file in order (51 → 56). Apply:
- 51: Add new tables (CREATE TABLE ... IF NOT EXISTS). If the table already exists in the schema, merge the columns; otherwise append the full CREATE TABLE.
- 52: Add condition reference rows as `INSERT ... ON CONFLICT DO NOTHING`.
- 53: Add external identifier tables.
- 54: Extend the catalog with new tables/columns.
- 55: Add type/subtype reference tables.
- 56: Add GRANT statements for all new tables.

- [ ] **Step 3: Fold migration_57 sealed index drop into core/12_sealed_pricing.sql**

Find `idx_sealed_ext_id_type_value` in `core/12_sealed_pricing.sql` and remove it (the UNIQUE constraint already covers it).

- [ ] **Step 4: Create core/13_content.sql from migration_61_article.sql**

Read `migrations/migration_61_article.sql` (43 lines). Create a new file `core/13_content.sql` containing the schema and table definition. Remove the `BEGIN;`/`COMMIT;` transaction wrappers (schema files are applied without explicit transactions by the rebuild script):

```sql
-- 13_content.sql
-- Editorial articles feature.

CREATE SCHEMA IF NOT EXISTS content;
GRANT USAGE ON SCHEMA content TO app_celery, app_rw, app_admin, app_ro;

CREATE TABLE IF NOT EXISTS content.article (
    article_id       UUID        NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
    slug             TEXT        NOT NULL UNIQUE,
    title            TEXT        NOT NULL,
    excerpt          TEXT        NOT NULL DEFAULT '',
    cover_image_url  TEXT,
    body_markdown    TEXT        NOT NULL DEFAULT '',
    status           TEXT        NOT NULL DEFAULT 'draft'
                                 CHECK (status IN ('draft', 'published')),
    tags             TEXT[]      NOT NULL DEFAULT '{}',
    read_minutes     INTEGER     NOT NULL DEFAULT 1,
    author_id        UUID        REFERENCES user_management.users(unique_id),
    published_at     TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_article_published
    ON content.article (published_at DESC)
    WHERE status = 'published';

GRANT SELECT, INSERT, UPDATE, DELETE ON content.article TO app_celery, app_rw, app_admin;
GRANT SELECT ON content.article TO app_ro;
```

- [ ] **Step 5: Verify**

```bash
docker exec automana-postgres-dev psql -U automana_admin automana \
  -c "\dt card_catalog.sealed*" \
  -c "\d content.article"
```

- [ ] **Step 6: Commit**

```bash
git add src/automana/database/SQL/schemas/core/12_sealed_pricing.sql \
        src/automana/database/SQL/schemas/core/13_content.sql
git commit -m "feat(db): squash sealed pricing + add content schema"
```

---

## Task 10: Archive old migration files + delete empty schema files

**Files:**
- Move: all `migration_XX_*.sql` files → `migrations/archive/`
- Delete: `schemas/11_staging_schema.sql` (empty)
- Delete: original flat schema files (replaced by core/ and pipeline/ versions)

- [ ] **Step 1: Move all historical migrations to archive/**

```bash
mv src/automana/database/SQL/migrations/migration_*.sql \
   src/automana/database/SQL/migrations/archive/
```

- [ ] **Step 2: Delete empty schema file**

```bash
rm src/automana/database/SQL/schemas/11_staging_schema.sql
```

- [ ] **Step 3: Delete original flat schema files (now replaced by core/ and pipeline/)**

```bash
rm src/automana/database/SQL/schemas/01_set_schema.sql \
   src/automana/database/SQL/schemas/02_card_schema.sql \
   src/automana/database/SQL/schemas/03_users.sql \
   src/automana/database/SQL/schemas/04_online_shop.sql \
   src/automana/database/SQL/schemas/05_ebay.sql \
   src/automana/database/SQL/schemas/06_prices.sql \
   src/automana/database/SQL/schemas/07_shopify_staging.sql \
   src/automana/database/SQL/schemas/08_ebay_orders.sql \
   src/automana/database/SQL/schemas/08_markets_prices.sql \
   src/automana/database/SQL/schemas/09_ops_schema.sql \
   src/automana/database/SQL/schemas/10_mtgjson_schema.sql \
   src/automana/database/SQL/schemas/12_sealed_pricing.sql
```

- [ ] **Step 4: Verify only core/ and pipeline/ remain (plus maintenance/ + archive/)**

```bash
find src/automana/database/SQL/schemas -type f -name "*.sql" | sort
```

Expected: only `schemas/core/*.sql`, `schemas/pipeline/*.sql`, `schemas/integrity_checks.sql`.

```bash
find src/automana/database/SQL/migrations -type f -name "*.sql" | sort
```

Expected: only `migrations/archive/migration_*.sql`.

- [ ] **Step 5: Commit**

```bash
git add -A src/automana/database/SQL/
git commit -m "feat(db): archive historical migrations + clean up flat schema files"
```

---

## Task 11: Verify squash — structural diff against live DB

This is the critical gate. A fresh install from the new schema files must produce a DB structurally identical to the live one.

**Files:** No file changes — verification only.

- [ ] **Step 1: Dump the live DB schema**

```bash
docker exec automana-postgres-dev pg_dump -U automana_admin \
  --schema-only automana > /tmp/live_schema.sql
```

- [ ] **Step 2: Create a fresh DB from squashed schemas**

```bash
# Create a temp database
docker exec automana-postgres-dev psql -U automana_admin -d postgres \
  -c "CREATE DATABASE automana_squash_test OWNER automana_admin;"

# Apply core schemas
for f in $(ls src/automana/database/SQL/schemas/core/*.sql | sort); do
  docker exec -i automana-postgres-dev psql -U automana_admin automana_squash_test < "$f"
done

# Apply pipeline schemas
for f in $(ls src/automana/database/SQL/schemas/pipeline/*.sql | sort); do
  docker exec -i automana-postgres-dev psql -U automana_admin automana_squash_test < "$f"
done
```

- [ ] **Step 3: Dump the fresh DB schema**

```bash
docker exec automana-postgres-dev pg_dump -U automana_admin \
  --schema-only automana_squash_test > /tmp/fresh_schema.sql
```

- [ ] **Step 4: Diff and resolve any gaps**

```bash
diff <(grep -v "^--\|^$\|SET \|SELECT pg_catalog" /tmp/live_schema.sql | sort) \
     <(grep -v "^--\|^$\|SET \|SELECT pg_catalog" /tmp/fresh_schema.sql | sort) \
  | head -100
```

For any table/column/index present in live but missing from fresh: find the responsible migration in `archive/` and fold it into the appropriate schema file. Re-run the diff until clean.

- [ ] **Step 5: Drop the test DB**

```bash
docker exec automana-postgres-dev psql -U automana_admin -d postgres \
  -c "DROP DATABASE automana_squash_test;"
```

- [ ] **Step 6: Commit any gap fixes**

```bash
git add src/automana/database/SQL/schemas/
git commit -m "fix(db): resolve squash gaps found during structural diff"
```

---

## Task 12: Update rebuild_dev_db.sh

The current script has two schema-application loops (one in `--preserve-data`, one in full rebuild). Both use `for f in "$SCHEMAS_DIR"/*.sql` and explicitly skip `integrity_checks.sql`. The migration loop in `--preserve-data` iterates `$MIGRATIONS_DIR/*.sql`. Both loops need to be updated.

Flyway runs in its own container — **not via `$EXEC`** (which targets the postgres container). Use `dcdev-automana run --rm flyway` instead.

**Files:**
- Modify: `src/automana/database/SQL/maintenance/rebuild_dev_db.sh`

- [ ] **Step 1: Replace the schema glob in `--preserve-data` (around line 437)**

Find:
```bash
    for f in "$SCHEMAS_DIR"/*.sql; do
      [[ "$(basename "$f")" == "integrity_checks.sql" ]] && continue
      echo "  → $(basename "$f")"
      $EXEC psql -v ON_ERROR_STOP=1 -U "$DBOWNER" -d "$DBNAME" < "$f" > /dev/null || true
    done
```

Replace with:
```bash
    for f in "$SCHEMAS_DIR"/core/*.sql "$SCHEMAS_DIR"/pipeline/*.sql; do
      [[ -f "$f" ]] || continue
      echo "  → $(basename "$f")"
      $EXEC psql -v ON_ERROR_STOP=1 -U "$DBOWNER" -d "$DBNAME" < "$f" > /dev/null || true
    done
```

(No `integrity_checks.sql` skip needed — it stays in `schemas/` root and is never globbed.)

- [ ] **Step 2: Replace the migration loop in `--preserve-data` (around line 448)**

Find:
```bash
    echo "== Applying migrations (incremental updates) =="
    for f in "$MIGRATIONS_DIR"/*.sql; do
      echo "  → $(basename "$f")"
      $EXEC psql -v ON_ERROR_STOP=1 -U "$DBOWNER" -d "$DBNAME" < "$f" > /dev/null || true
    done
```

Replace with:
```bash
    echo "== Flyway: applying pending migrations =="
    dcdev-automana run --rm flyway migrate
```

- [ ] **Step 3: Replace the schema glob in the full rebuild path (around line 465)**

Find:
```bash
    echo "== Applying schemas =="
    for f in "$SCHEMAS_DIR"/*.sql; do
      [[ "$(basename "$f")" == "integrity_checks.sql" ]] && continue
      echo "  → $(basename "$f")"
      $EXEC psql -v ON_ERROR_STOP=1 -U "$DBOWNER" -d "$DBNAME" < "$f" > /dev/null
    done
```

Replace with:
```bash
    echo "== Applying schemas =="
    for f in "$SCHEMAS_DIR"/core/*.sql "$SCHEMAS_DIR"/pipeline/*.sql; do
      [[ -f "$f" ]] || continue
      echo "  → $(basename "$f")"
      $EXEC psql -v ON_ERROR_STOP=1 -U "$DBOWNER" -d "$DBNAME" < "$f" > /dev/null
    done
```

- [ ] **Step 4: Add Flyway baseline after schema application in the full rebuild path (after the apply_schema_grants block, around line 473)**

After the grants block in the full rebuild path, add:
```bash
    echo "== Flyway: baseline V0 (fresh install) =="
    dcdev-automana run --rm flyway \
      baseline -baselineVersion=0 -baselineDescription="squashed_schema"
```

- [ ] **Step 5: Add flyway info to dry-run summary**

Find `_dry_run_summary()`. Add:
```bash
  echo "  Flyway      : migrations/core + migrations/pipeline (baseline V0 on fresh install)"
```

- [ ] **Step 6: Verify the script parses**

```bash
bash -n src/automana/database/SQL/maintenance/rebuild_dev_db.sh
```

Expected: no syntax errors.

- [ ] **Step 7: Commit**

```bash
git add src/automana/database/SQL/maintenance/rebuild_dev_db.sh
git commit -m "feat(db): update rebuild_dev_db.sh to use Flyway for migrations"
```

---

## Task 13: Baseline existing dev DB + smoke test

- [ ] **Step 1: Stamp the existing dev DB with Flyway baseline V0**

This tells Flyway "everything that exists in this DB was already applied before Flyway started tracking."

```bash
docker compose -f deploy/docker-compose.dev.yml run --rm \
  -e FLYWAY_PASSWORD=$(cat config/env/.env.dev | grep AUTOMANA_ADMIN_DB_PASSWORD | cut -d= -f2) \
  flyway \
  -url=jdbc:postgresql://postgres:5432/automana \
  -user=automana_admin \
  baseline -baselineVersion=0 -baselineDescription="squashed_schema"
```

Expected output: `Successfully baselined schema with version 0`

- [ ] **Step 2: Verify Flyway sees a clean state**

```bash
docker compose -f deploy/docker-compose.dev.yml run --rm \
  -e FLYWAY_PASSWORD=$(cat config/env/.env.dev | grep AUTOMANA_ADMIN_DB_PASSWORD | cut -d= -f2) \
  flyway info
```

Expected: one row showing `<< Flyway Baseline >>` at V0 with status `Baseline`. No `Pending` migrations.

- [ ] **Step 3: Create a trivial V1 migration to confirm end-to-end tracking works**

```bash
cat > src/automana/database/SQL/migrations/core/V1__smoke_test_comment.sql << 'EOF'
-- Smoke test: confirms Flyway tracking is working end-to-end.
-- Safe to keep; adds no schema objects.
COMMENT ON SCHEMA card_catalog IS 'MTG card catalog — sets, cards, card versions';
EOF
```

- [ ] **Step 4: Apply it**

```bash
docker compose -f deploy/docker-compose.dev.yml run --rm \
  -e FLYWAY_PASSWORD=$(cat config/env/.env.dev | grep AUTOMANA_ADMIN_DB_PASSWORD | cut -d= -f2) \
  flyway migrate
```

Expected: `Successfully applied 1 migration to schema "public"`

- [ ] **Step 5: Verify info shows V1 as applied**

```bash
docker compose -f deploy/docker-compose.dev.yml run --rm \
  -e FLYWAY_PASSWORD=$(cat config/env/.env.dev | grep AUTOMANA_ADMIN_DB_PASSWORD | cut -d= -f2) \
  flyway info
```

Expected: V0 (Baseline) and V1 (Success). No Pending.

- [ ] **Step 6: Commit**

```bash
git add src/automana/database/SQL/migrations/core/V1__smoke_test_comment.sql
git commit -m "feat(db): baseline dev DB at V0 + smoke test V1 migration confirms Flyway tracking"
```

---

## Day-to-day workflow after this plan

Adding a new DB change:
1. Create `migrations/core/V<N>__desc.sql` (or `pipeline/`) — use the next sequential number.
2. Restart the dev stack (the Flyway service applies it automatically) or run `docker compose run --rm flyway migrate`.
3. Commit the migration file.

Checking DB state: `docker compose run --rm flyway info`
