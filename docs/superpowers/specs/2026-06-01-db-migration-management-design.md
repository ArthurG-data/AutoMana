# DB Migration Management — Design Spec

**Date:** 2026-06-01
**Status:** Approved design — ready for implementation planning

## Problem

1. The migration process is fragile — no tracking of which migrations have been applied to which DB, duplicate migration numbers (46, 60, 61), and manual application with no audit trail.
2. The production DB cannot be hosted cheaply because `price_observation` (Tier 1, ~377M rows) is the dominant table but is never read by the API.

This spec covers the first two parts of the fix: a Flyway migration runner and a core/pipeline schema split. Prod data promotion (dev → prod) is deferred to a separate spec.

## Scope

- **In:** Flyway migration runner, schema directory reorganization (core/pipeline split), migration squash, rebuild_dev_db.sh update.
- **Out:** Prod promotion job (dump Tier 2+ to prod), TimescaleDB retention policies.

---

## Part 1 — Migration Squash (Clean Baseline)

### What

Fold all 39 existing `migration_XX_*.sql` deltas into the relevant `schemas/` files so those files represent the true current DB state. A fresh `psql < schemas/**/*.sql` applied to a new cluster produces a DB identical to the live one — no migrations needed for a clean install.

### How

1. Read each migration file and apply its changes to the corresponding schema file (ALTER TABLE → update the CREATE TABLE; CREATE INDEX → add to the schema; etc.).
2. Resolve the 3 duplicate-numbered files (46, 60, 61) — the later file in each pair gets incorporated into the schema squash alongside the first.
3. Move the 39 original files to `migrations/archive/` — kept as a changelog but not executed by Flyway.
4. Run `flyway baseline --baselineVersion=0 --baselineDescription="squashed_schema"` on every existing DB (dev + prod) once, to stamp the `flyway_schema_history` table at V0.

After this step, new migrations start at V1.

---

## Part 2 — Core / Pipeline Schema Split

### Why

Prod only needs the tables the API reads. Pipeline tables (raw ingest, staging, ops) stay on dev where the workers run.

### Directory structure

```
src/automana/database/SQL/
├── schemas/
│   ├── core/        ← applied to prod + dev (fresh install)
│   └── pipeline/    ← applied to dev only (fresh install)
├── migrations/
│   ├── core/        ← Flyway V1+, applied to prod + dev
│   ├── pipeline/    ← Flyway V1+, applied to dev only
│   └── archive/     ← old migration_XX_*.sql files (history only)
├── flyway-dev.conf
├── flyway-prod.conf
└── maintenance/     ← unchanged
```

### Table assignment

| Core (prod + dev) | Pipeline (dev only) |
|---|---|
| `card_catalog.*` | `pricing.price_observation` (Tier 1) |
| `pricing.print_price_daily` | `pricing.stg_price_observation` |
| `pricing.print_price_weekly` | `pricing.stg_price_observation_reject` |
| `pricing.print_price_latest` | `pricing.raw_mtg_stock_price` |
| `pricing.print_price_watermark` | MTGJson / Scryfall staging tables |
| `users.*` | `ops.*` (all ingestion tracking) |
| `collection.*` | `shopify.*` |
| `ebay.*` | |
| `content.article` | |

### Schema file split during squash

During the squash pass, the existing schema files are split as needed. For example:
- `06_prices.sql` → `schemas/core/06_prices.sql` (Tier 2/3/snapshot) + `schemas/pipeline/06_prices_pipeline.sql` (Tier 1, staging, stored procedures that reference them)
- `07_shopify_staging.sql` → `schemas/pipeline/07_shopify.sql`
- `04_ops.sql` → `schemas/pipeline/04_ops.sql`

---

## Part 3 — Flyway Integration

### Config files

```toml
# flyway-dev.conf
flyway.url=jdbc:postgresql://postgres:5432/automana
flyway.user=automana_admin
flyway.locations=filesystem:/flyway/migrations/core,filesystem:/flyway/migrations/pipeline
flyway.baselineOnMigrate=false
flyway.validateOnMigrate=true

# flyway-prod.conf  (fill in prod host when DB hosting is confirmed)
flyway.url=jdbc:postgresql://<prod-host>:5432/automana
flyway.user=automana_admin
flyway.locations=filesystem:/flyway/migrations/core
flyway.baselineOnMigrate=false
flyway.validateOnMigrate=true
```

Passwords come from the `FLYWAY_PASSWORD` env var — never hardcoded.

### Docker service (dev)

A `flyway` service is added to `docker-compose.dev.yml`. It uses the official `flyway/flyway` image, mounts the `migrations/` directory, and runs `flyway migrate` once after postgres is healthy. It exits after completion — not a long-running container.

```yaml
flyway:
  image: flyway/flyway:10
  depends_on:
    postgres:
      condition: service_healthy
  volumes:
    - ./src/automana/database/SQL/migrations:/flyway/migrations
    - ./src/automana/database/SQL/flyway-dev.conf:/flyway/conf/flyway.conf
  command: migrate
  restart: "no"
```

The `flyway.locations` in the conf files must use absolute container paths:
`filesystem:/flyway/migrations/core,filesystem:/flyway/migrations/pipeline`

### rebuild_dev_db.sh update

- **Full rebuild path** (`--only rebuild`): applies `schemas/core/` then `schemas/pipeline/`, then runs `flyway baseline --baselineVersion=0`.
- **Preserve-data path** (`--preserve-data`): replaces the manual migration loop with `flyway migrate --config-files=flyway-dev.conf`.
- `flyway info` is added to the dry-run summary output.

### Day-to-day workflow

Adding a DB change going forward:
1. Create `migrations/core/V1__desc.sql` or `migrations/pipeline/V1__desc.sql`.
2. Run `flyway migrate` (or restart the dev stack — the Flyway service applies it automatically).
3. Commit the file. Flyway's checksum validation ensures the same file is applied identically on every DB.

Migration naming: `V<N>__snake_case_description.sql`, strictly sequential per directory. Core and pipeline share the same version sequence (both start at V1 and increment independently).

---

## Migration Naming Convention

- Format: `V<N>__<snake_case_description>.sql`
- Example: `V1__add_article_table.sql`, `V2__add_game_code_to_collection.sql`
- Numbers are strictly sequential within each directory (`core/` and `pipeline/` each have their own sequence starting at V1)
- No duplicate numbers — Flyway will reject them

---

## Out of Scope

- Prod data promotion job (dev Tier 2 → prod)
- TimescaleDB retention policy for `price_observation`
- Flyway repair / rollback workflow (out-of-scope for v1)
- Multi-schema Flyway placeholders
