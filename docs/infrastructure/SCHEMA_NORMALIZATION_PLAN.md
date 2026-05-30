# AutoMana Database Normalization Plan

**Date:** 2026-05-30
**Status (updated 2026-05-30):** Phases 0, 1, 3 **APPLIED** to the dev DB (ANALYZE/VACUUM; `migration_57` indexes; `migration_58` unique_cards FK + tz fix). Phase 2 (`card_game` consolidation, would be `migration_59`) **DEFERRED** to backlog issue [#331](https://github.com/ArthurG-data/AutoMana/issues/331). Phase 4 **INVESTIGATED + actioned**: `ingestion_run_resources` scryfall lineage wired ✅ (verified); `price_metric` cleanup → [#335](https://github.com/ArthurG-data/AutoMana/issues/335); mtgjson lineage → [#336](https://github.com/ArthurG-data/AutoMana/issues/336); `ingestion_step_metrics` kept as scaffolding.
**Scope:** All ~115 user tables across 8 application schemas (`card_catalog`, `pricing`, `ops`, `app_integration`, `user_management`, `markets`, `user_collection`, `reporting`). TimescaleDB chunk internals (`_timescaledb_*`) excluded.
**Method:** Every verdict is backed by three signals — real `COUNT(*)`, the FK graph from `pg_constraint` (inbound + outbound), and a grep of `src/` + `database/SQL/` + migrations. `reltuples = -1`/`0` estimates were **not** used to judge "unused".

---

## Executive Summary

The schema is in better shape than the "find dead/duplicate/dangling tables" framing assumed.

- **No table qualifies for dropping.** Every table that looks empty is *dev-empty* (this instance has no real users/orders), not unused — all are FK-wired and referenced in code.
- **The `markets` schema is NOT dead.** It is the live Shopify storefront/market integration layer (Good Games Sydney/Brisbane). Initially suspected, refuted by evidence. **Keep.**
- **`pricing.product_ref` vs `markets.product_ref`** share a name but are structurally different tables. **Not duplicates.**
- **`product_ref` / `mtg_card_products` / `mtg_sealed_products`** is a *justified* supertype/subtype split (108,872 + 97 + 1 sentinel = 108,970, math closes exactly). **Do not merge.**
- **Exactly one genuine normalization defect:** the game taxonomy is duplicated across `pricing.card_game` and `card_catalog.card_games_ref` — same single `mtg` row, two tables, each with its own FK dependents. This can silently diverge. **This is the only structural change worth making.**
- **The highest-value action is operational, not structural:** ~95 of ~115 tables have **never been `ANALYZE`d**, so the query planner is using default estimates for tables with hundreds of thousands of rows. This degrades plans across the whole app and is a zero-risk fix.

The plan below is sequenced by **risk × value**: free hygiene first, then low-risk index cleanup, then the single real normalization, then small correctness fixes, then investigate-only items.

---

## Phase 0 — Operational hygiene (do first; zero schema risk)

These are not migrations. They are read-safe maintenance commands. Highest value-to-risk ratio in the whole plan.

### 0.1 ANALYZE the database (HIGH value)

**Problem:** ~95 tables have `last_analyze IS NULL AND last_autoanalyze IS NULL`, including `card_catalog.card_version` (171K), `card_external_identifier` (825K), `legalities` (341K), `games_card_version` (311K). Root cause: they were bulk-`INSERT`ed with no later UPDATE/DELETE, so `n_dead_tup` stayed 0 and autovacuum's analyze threshold was never crossed. The planner therefore estimates these huge tables at ~0 rows → wrong join strategies and index choices.

**Action:**
```sql
ANALYZE VERBOSE;            -- whole DB, safe, read-only w.r.t. data
```
**Verification:** `SELECT relname, last_analyze FROM pg_stat_user_tables WHERE schemaname='card_catalog' ORDER BY n_live_tup DESC;` — confirm timestamps populate.
**Rollback:** none needed (statistics only).

### 0.2 Clear dead-tuple bloat on the ops mapping table

`ops.ingestion_ids_mapping`: 205,780 live rows, ~10,427 dead (5%).
```sql
VACUUM ANALYZE ops.ingestion_ids_mapping;
```

### 0.3 Prevent recurrence ✅ DECIDED (no standing service)

**Decision:** No app-level scheduled ANALYZE service. Two reasons it isn't needed:
- The Celery worker connects as `app_celery` (member of `app_rw`), which **cannot** `ANALYZE` tables it doesn't own — it returns `WARNING: permission denied … skipping it` and silently no-ops. PG has no ANALYZE-only grant; the only enabling privilege is `MAINTAIN` (PG16+), which also bundles VACUUM/CLUSTER/REINDEX/REFRESH/LOCK and would over-widen the deliberately DML-only `app_rw`. Rejected (consistent with the roles-doc precedent that ownership-gated maintenance runs as `automana_admin`).
- `autovacuum` is `on` and, now that a baseline ANALYZE has run (`n_mod_since_analyze = 0` across the big tables), it will re-analyze them after future bulk loads once the per-table threshold (~50 + 10%·rows) is crossed.

**What was wired instead:** `ANALYZE;` added as the final step of the `verify` stage in `rebuild_dev_db.sh` (runs as `automana_admin`/`$SUPERUSER`, the only role that may analyze unowned tables). This guarantees a freshly rebuilt DB is never left with blind stats — the one scenario autovacuum doesn't cover promptly. No role change, no migration, no new service.

---

## Phase 1 — Redundant index cleanup → `migration_57` ✅ APPLIED

Four indexes are fully covered by an existing UNIQUE constraint index or are a strict left-prefix of a broader composite. Dropping them reduces write amplification and storage with no read-plan regression.

| Drop | Table | Why redundant | Covered by |
|---|---|---|---|
| `idx_artists_name` | `card_catalog.artists_ref` | exact dup, non-unique | `artists_ref_artist_name_key` UNIQUE(artist_name) |
| `sets_set_code_idx` | `card_catalog.sets` | exact dup, non-unique | `sets_set_code_key` UNIQUE(set_code) |
| `idx_sealed_ext_id_type_value` | `card_catalog.sealed_external_identifier` | exact dup, non-unique | `sealed_external_identifier_type_value_key` UNIQUE(sealed_identifier_ref_id, value) |
| `idx_card_version_set_id` | `card_catalog.card_version` | strict left-prefix | `card_version_set_coll_idx` btree(set_id, collector_number) |

**Draft `migration_57_drop_redundant_indexes.sql` (NOT applied):**
```sql
BEGIN;
DROP INDEX IF EXISTS card_catalog.idx_artists_name;
DROP INDEX IF EXISTS card_catalog.sets_set_code_idx;
DROP INDEX IF EXISTS card_catalog.idx_sealed_ext_id_type_value;
DROP INDEX IF EXISTS card_catalog.idx_card_version_set_id;
COMMIT;
```
**Pre-check (run before writing the migration — index definitions can drift):**
```sql
SELECT schemaname, tablename, indexname, indexdef
FROM pg_indexes
WHERE indexname IN ('idx_artists_name','sets_set_code_idx',
                    'idx_sealed_ext_id_type_value','idx_card_version_set_id',
                    'artists_ref_artist_name_key','sets_set_code_key',
                    'sealed_external_identifier_type_value_key','card_version_set_coll_idx')
ORDER BY tablename;
```
**Verification after apply:** re-run the pricing/catalog read paths or `EXPLAIN` a `WHERE set_id = …` query on `card_version` and confirm it uses `card_version_set_coll_idx`.
**Rollback:** recreate the dropped indexes (keep their `CREATE INDEX` DDL in the migration's comment header).
**Risk:** LOW.

---

## Phase 2 — The one real normalization: consolidate the game taxonomy → `migration_59` ⏸️ DEFERRED → issue [#331](https://github.com/ArthurG-data/AutoMana/issues/331)

**Defect (verified):**
- `pricing.card_game` — 1 row `(1, mtg, Magic: The Gathering)`; FK dependent: `markets.handles_theme.theme_id`.
- `card_catalog.card_games_ref` — 1 row, identical; FK dependents: `pricing.product_ref.game_id`, `card_catalog.sealed_product.game_id`.

Two tables modelling the same concept, each maintained independently → they can diverge (a new game added to one but not the other). Canonical home is `card_catalog.card_games_ref` (a catalog reference belongs in `card_catalog`).

**Full dependency surface (verified 2026-05-30 — larger than first estimated):**

Consolidation is NOT a one-file migration. `pricing.card_game` is referenced across schema DDL *and* live application code in two integration layers:

*Schema / DDL (3 files):*
1. `schemas/06_prices.sql:183` — the table definition itself.
2. `schemas/07_shopify_staging.sql:42` — a staging-table FK `game_id INT NOT NULL REFERENCES pricing.card_game(game_id)`; `:67` — a JOIN on `pricing.card_game cg ON cg.code='mtg'`.
3. `schemas/08_markets_prices.sql:85` — `markets.handles_theme.theme_id` FK; `:132-134` — the `BEFORE DELETE` soft-delete trigger bound to `pricing.card_game`.

*Python repositories (4 methods, incl. a live writer):*
4. `shopify/collection_repository.py:65` — **`INSERT INTO pricing.card_game (code, name)`** (actively writes the table).
5. `shopify/collection_repository.py:49`, `shopify/pipeline_repository.py:117`, `mtg_stock/price_repository.py:267` — JOINs.

**Implication:** this is a coordinated code + schema refactor (own PR + tests), not an ad-hoc migration. The FK re-point + trigger move below is necessary but **not sufficient** — every Python reference and the staging-table FK in schema 07 must be repointed to `card_catalog.card_games_ref` first, or the Shopify/MTGStock pipelines break at runtime.

**Severity vs effort:** divergence risk is LOW (both tables hold the single identical `mtg` row; they only diverge if a *new* game is added to one and not the other). Effort is now MEDIUM-HIGH. Recommend treating as a tracked refactor, or deferring in favour of a lightweight sync safeguard — see Decision below.

**Sequenced approach (if pursued):**
1. Repoint all 4 Python repo methods + the schema-07 staging FK/JOIN + schema-06/08 DDL to `card_catalog.card_games_ref`.
2. Apply the data-safety insert + FK re-wire + trigger move + drop in one transaction.
3. Run the Shopify + MTGStock pipelines end-to-end against the change.

**Draft `migration_59_consolidate_card_game_ref.sql` (NOT applied — deferred to #331; repoint all code + schema refs first):**
```sql
BEGIN;

-- 1. Safety: ensure every pricing.card_game row exists in the canonical table
INSERT INTO card_catalog.card_games_ref (code, name)
SELECT cg.code, cg.name FROM pricing.card_game cg
WHERE NOT EXISTS (SELECT 1 FROM card_catalog.card_games_ref c WHERE c.code = cg.code)
ON CONFLICT (code) DO NOTHING;

-- 2. Drop the cross-schema soft-delete trigger on the old table
DROP TRIGGER IF EXISTS soft_delete_handles_theme_trigger ON pricing.card_game;

-- 3. Re-point markets.handles_theme.theme_id to the canonical table
ALTER TABLE markets.handles_theme DROP CONSTRAINT IF EXISTS handles_theme_theme_id_fkey;
ALTER TABLE markets.handles_theme
  ADD CONSTRAINT handles_theme_game_id_fkey
  FOREIGN KEY (theme_id) REFERENCES card_catalog.card_games_ref(game_id) ON DELETE SET NULL;

-- 4. Recreate the soft-delete trigger against the new parent
CREATE OR REPLACE FUNCTION markets.soft_delete_handles_theme()
RETURNS TRIGGER AS $$
BEGIN
  UPDATE markets.handles_theme SET is_active = FALSE WHERE theme_id = OLD.game_id;
  RETURN OLD;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER soft_delete_handles_theme_trigger
  BEFORE DELETE ON card_catalog.card_games_ref
  FOR EACH ROW EXECUTE FUNCTION markets.soft_delete_handles_theme();

-- 5. Drop the duplicate (only after step 2-prereq updates the stored proc)
DROP TABLE pricing.card_game;

COMMIT;
```
**Verification:** `markets.handles_theme` FK now points at `card_catalog.card_games_ref`; Shopify pipeline (`pipeline_service.py`) runs end-to-end; `pricing.price_observation_stage` proc still executes.
**Rollback:** recreate `pricing.card_game` (1 row), restore its FK + trigger, revert the schema-07 proc. Keep the original DDL in the migration header.
**Risk:** MEDIUM — touches a trigger and a stored proc across `pricing` ↔ `markets` ↔ `card_catalog`. Do not apply without completing the step-2 prerequisite and testing the Shopify staging proc.

---

## Phase 3 — Small correctness / normalization fixes → `migration_58` ✅ APPLIED

Independent, low-risk, batchable.

### 3.1 `card_catalog.unique_cards_ref.other_face_id` — add self-FK + index
Nullable self-reference (DFC/split-card pairing) with **no FK and no index** → seq scans on 37K rows when traversed, and no referential integrity.
```sql
ALTER TABLE card_catalog.unique_cards_ref
  ADD CONSTRAINT fk_unique_cards_other_face
  FOREIGN KEY (other_face_id) REFERENCES card_catalog.unique_cards_ref(unique_card_id);
CREATE INDEX IF NOT EXISTS idx_unique_cards_ref_other_face
  ON card_catalog.unique_cards_ref(other_face_id) WHERE other_face_id IS NOT NULL;
```
**Pre-check:** confirm no orphan `other_face_id` values before adding the FK:
`SELECT count(*) FROM card_catalog.unique_cards_ref u WHERE other_face_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM card_catalog.unique_cards_ref p WHERE p.unique_card_id = u.other_face_id);` — must be 0.

### 3.2 `pricing.shopify_staging_raw.scraped_at` → `TIMESTAMPTZ`
Only timestamp column in the schema using `TIMESTAMP WITHOUT TIME ZONE`; every other uses `TIMESTAMPTZ`. Timezone-confusion risk for a scraper.
```sql
ALTER TABLE pricing.shopify_staging_raw
  ALTER COLUMN scraped_at TYPE TIMESTAMPTZ USING scraped_at AT TIME ZONE 'UTC';
```
(Table is a transient staging buffer — currently empty — so this is effectively free.)

**Risk:** LOW.

---

## Phase 4 — Investigate before touching ✅ INVESTIGATED

These were *suspected* relics. Investigation done — none are accidental dead tables.

**Investigation complete (2026-05-30).** Headline: **no accidental dead tables** — two items are deliberately-retained scaffolding, one is a half-built feature. Evidence below.

| Item | Investigation result | Verdict |
|---|---|---|
| `pricing.price_metric` (3 rows) + `raw_to_stage()` / `stage_to_price_observation()` procs + `price_observation_stage` unlogged table | The proc chain that references `price_metric` is **never invoked**; `stage_to_price_observation()` is **explicitly a no-op** (`07_shopify_staging.sql:124`: *"intentionally a no-op. Shopify observations are promoted in Python by the shopify.pipeline.promote_observations service step"*). So this is the superseded SQL-staging design, deliberately stubbed rather than deleted. No inbound FKs. | **RELIC, intentionally retained → ticketed [#335](https://github.com/ArthurG-data/AutoMana/issues/335).** Cleanup (drop `price_metric` + the two procs + the unlogged-table DDL, spanning schema files 06 + 07) tracked rather than auto-deleted — same class as the deferred `card_game` refactor. Harm of leaving: ~nil (3 lookup rows + 2 no-op procs). |
| `ops.ingestion_step_metrics` (0 rows) | Referenced **only** by its own DDL in `09_ops_schema.sql` — no writer, no reader, no inbound FK. Coherent sibling of `ingestion_run_metrics` (which has a Python writer, though also 0 rows in dev). | **KEEP — designed-but-unwired scaffolding.** Costs nothing empty; part of the ops telemetry tier and would be re-added if step-level metrics get wired. (Drop only if you want strict YAGNI.) |
| `ops.ingestion_run_resources` (0 rows) | **READ** by the scryfall/mtgjson run-diff maintenance SQL (the run→resource→resource_versions lineage join) but **never written**. | **WIRED UP (scryfall) ✅.** Added a data-modifying CTE `link_run_resources` to `update_bulk_scryfall_data_sql` (`ops/scryfall_data.py`) that links the ingestion run (`$2`) to each newly-inserted `resource_version`, guarded on a non-null run id. Verified live in a rolled-back transaction: `versions_inserted=1` → `run_resources_linked=1, status='processed'`. **mtgjson follow-up → ticketed [#336](https://github.com/ArthurG-data/AutoMana/issues/336), DEFERRED:** investigation found the daily mtgjson pipeline never downloads/ingests `AllPrintings` at all — it's a *future* `mtgjson_weekly` pipeline (`pipelines.py:116`); the daily run only checks the catalog version via `Meta.json` (the `check_version` gate). So there's no real file download with `bytes`/`sha256` to attach lineage to. A version-only MVP at the gate was rejected (NULL integrity fields + status overclaim). Lineage to be wired when the AllPrintings ingest pipeline is built. |

---

## Explicitly NOT changing (and why)

| Kept | Reason |
|---|---|
| `markets` schema (all tables) | Live Shopify integration (market_ref = real stores; FKs into `pricing`; written by `shopify/*` repos + `scrape_global_market_service`). |
| `pricing.product_ref` / `mtg_card_products` / `mtg_sealed_products` | Justified supertype/subtype; row math closes exactly. Merging would break the polymorphic price-observation chain. |
| `card_catalog.card_stats_ref` + `card_version_stats` (EAV) | MTG stats are non-numeric (`*`, `1+*`, `X`) → `TEXT` EAV is correct, open-ended by design. |
| All dev-empty tables (`app_integration.*`, `user_management.*`, `reporting.hourly_metrics`, etc.) | Empty because dev has no users/orders, not unused — all FK-wired and code-referenced. |

---

## Sequencing & dependencies

```
Phase 0  (ANALYZE + VACUUM)        ── no dependencies, do immediately, repeatable
Phase 1  (migration_57 indexes)    ── APPLIED
Phase 3  (migration_58 fixes)      ── APPLIED
Phase 2  (migration_59 card_game)  ── DEFERRED → #331 (coordinated code + schema refactor)
Phase 4  (investigations)          ── produces decisions that may add a later migration
```

Recommended order: **0 → 1 → 3 → (investigate Phase 4) → 2**. Phase 2 last because it carries the only medium risk and has a hard code prerequisite.

## Risk / rollback summary

| Phase | Change | Risk | Rollback |
|---|---|---|---|
| 0 | ANALYZE / VACUUM | none | n/a |
| 1 | drop 4 indexes | low | recreate indexes (DDL in header) |
| 3.1 | self-FK + index | low | drop FK + index |
| 3.2 | scraped_at → TIMESTAMPTZ | low | ALTER back (table empty) |
| 2 | consolidate card_game | medium | recreate table + FK + trigger + revert proc |

## Open questions / decisions

1. **Phase 0.3 (DECIDED):** No standing ANALYZE service — `app_celery` lacks privilege to analyze unowned tables, and granting `MAINTAIN` would over-widen `app_rw`. Wired `ANALYZE;` into the `rebuild_dev_db.sh` verify stage (runs as `automana_admin`); autovacuum covers incremental loads. See §0.3.
2. **Phase 2 (DECIDED):** Deferred to a tracked refactor — backlog issue [#331](https://github.com/ArthurG-data/AutoMana/issues/331). Effort (3 schema files + 4 repos + FK + trigger) outweighs the low divergence risk, so it gets its own PR + pipeline tests rather than an inline migration.
3. **Materialize migrations (DONE):** `migration_57` and `migration_58` written and applied; `migration_59` (card_game) intentionally NOT written — its SQL stays inline here and in #331 until the refactor is scheduled.
