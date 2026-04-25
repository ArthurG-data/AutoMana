# Shared TCGPlayer/Cardmarket ID Loss — Design Spec

**Date:** 2026-04-25
**Branch:** lands on top of `feat/db-health-metrics`
**Status:** Spec — awaiting approval to plan + implement
**Severity:** Medium — silent data loss with operational impact (price lookup misses)

## 1. Problem

The newly shipped `ops.audit.scryfall_identifier_coverage` service surfaced this on 2026-04-25 against the dev DB:

| Identifier | Source presence | DB stored | Gap | Collisions in source |
|---|---|---|---|---|
| tcgplayer_id | 85.99% (97,831 cards) | 84.92% (96,618 distinct values) | **1.07%** | **1,213 printings share a value with another printing** |
| cardmarket_id | 82.84% (94,256 cards) | 81.79% (93,060 distinct values) | **1.05%** | **1,196 printings** |

Both sit at refs/distinct ≈ 1.013 in the source — almost-but-not-quite per-printing.

### Why printings share an ID — characterized from the raw bulk file

Of the 1,212 tcgplayer_ids shared by ≥2 `card_version` rows in `1_20260425_default-cards-20260424211240.json` (113,776 cards):

| Cause | Count | % | Pattern |
|---|---|---|---|
| Foil/nonfoil pair, old-style starred collector_number | 1,052 | 87% | `Rogue Kavu 9ED #213` (nonfoil) + `#213★` (foil) — same physical product on TCGPlayer |
| Foil/nonfoil pair, modern convention | 135 | 11% | same shape, newer sets |
| Art variations (`†` collector number, `variation: True`) | 9 | <1% | `Gaea's Touch DRK #77` + `#77†` — TCGPlayer doesn't separate art variants |
| Secret Lair multi-card SKUs | 3 | <1% | `Cat #1517` + `Dog #1516` — sold as one bundle |
| Other one-offs | ~13 | rest | mixed (released_at, frame variants) |

**Not a factor:** language. The bulk file is `default-cards`, which is English-where-available; every shared-ID example was `lang=en`. Non-English printings live in a different bulk file (`all-cards`) and aren't part of this dataset. **Not a factor:** etched finishes (those have their own `tcgplayer_etched_id` field, separately tracked).

**The sharing is semantically correct upstream.** TCGPlayer issues one product ID per physical thing you can buy; Scryfall correctly models foil/nonfoil as separate `card_version` rows because they price differently and have different collector numbers. The DB should mirror that — both `card_version` rows owning their own external_identifier row pointing at the shared `tcgplayer_id` — so a price lookup by `tcgplayer_id` correctly attributes the price to both printings.

### Root cause in the schema

`card_catalog.card_external_identifier` has two constraints:
- `PRIMARY KEY (card_version_id, card_identifier_ref_id)` — one row per (printing, identifier-type)
- `UNIQUE (card_identifier_ref_id, value)` — one row per (identifier-type, value string)

The stored proc `card_catalog.insert_full_card_version` (`02_card_schema.sql` lines 734–747) does:

```sql
INSERT INTO card_catalog.card_external_identifier (card_identifier_ref_id, card_version_id, value)
SELECT r.card_identifier_ref_id, v_card_version_id, n.value
FROM (...) n
JOIN card_catalog.card_identifier_ref r ON r.identifier_name = n.name
WHERE n.value IS NOT NULL
ON CONFLICT DO NOTHING;
```

Bare `ON CONFLICT DO NOTHING` (no target listed) silently absorbs violations of *either* constraint. For `oracle_id` this is correct (T16 was the right call — measure differently, don't change the schema). For `tcgplayer_id` and `cardmarket_id`, the second printing of a foil/nonfoil pair hits `UNIQUE (ref_id, value)` and is dropped — even though it should logically own its own row pointing at the shared TCGPlayer product.

### Operational impact

The pricing pipeline does the reverse lookup: TCGPlayer scrape returns prices keyed by `tcgplayer_id`; we need to find which `card_version` rows to attribute the price to. Currently `JOIN card_external_identifier ON value = $tcgplayer_id` returns *at most one* `card_version` per shared ID, so 1,213 printings get no TCGPlayer price even though the source data covers them.

Concretely: for almost every starred-collector-number set in 8ED–10E, the foil printing and the nonfoil printing have the same TCGPlayer price (correctly — it's one product), but our DB only routes that price to one of them. The other `card_version` comes back priceless.

## 2. Out of scope

- The `oracle_id` semantics — already handled correctly by T16 (measure against `unique_cards_ref`).
- A general redesign of `card_external_identifier` (e.g., splitting per-identifier-type into separate tables). This spec is the minimal targeted fix.
- Other identifiers (`scryfall_id`, `multiverse_id`, `tcgplayer_etched_id`) — they show 0 collisions in the source.
- Non-English bulk file (`all-cards`) handling — current pipeline ingests `default-cards` only; if `all-cards` is ever ingested, language differences become another source of legitimate collisions.

## 3. Approach options

### Option A — Drop the `UNIQUE (card_identifier_ref_id, value)` constraint

Replace it with a non-unique B-tree index `(card_identifier_ref_id, value)` so reverse lookups stay fast. Update the stored proc's conflict clause to be explicit: `ON CONFLICT (card_version_id, card_identifier_ref_id) DO NOTHING` (the PK — preserves idempotent re-insert behavior on retries).

**Pros:**
- Simplest fix. One DDL change + one proc-body change + one re-ingestion.
- Restores correct semantics: every `card_version` that has a TCGPlayer ID in source gets its row in the table.
- `oracle_id` storage grows from ~37k rows to ~113k rows (one per `card_version`) — negligible at this scale, and the per-unique-card metric measurement (T16) is unaffected.

**Cons:**
- Loses a soft invariant ("each `(ref_id, value)` appears at most once in the table"). But since the source data demonstrably issues the same `tcgplayer_id` for multiple printings (per the §1 characterization), that invariant was always wrong for tcgplayer_id and cardmarket_id.
- Existing reverse-lookup queries that assumed at most one row will return multiple now. Audit any consumers — likely just the pricing pipeline (`pricing.mtg_card_products` population path).

### Option B — Per-identifier UNIQUE via partial unique indexes

Drop `UNIQUE (ref_id, value)`. Replace with **partial** unique indexes per identifier name where uniqueness IS expected:

```sql
CREATE UNIQUE INDEX ux_cei_scryfall_id_value
  ON card_external_identifier (value)
  WHERE card_identifier_ref_id = <scryfall_id_ref_id>;
```

…and so on per identifier where uniqueness IS desirable.

**Pros:**
- Preserves the invariant where it's truly true (`scryfall_id` is globally unique per Scryfall).

**Cons:**
- Five+ partial indexes instead of one. Maintenance burden.
- Partial index predicates require IMMUTABLE expressions, so the `card_identifier_ref_id` integer must be hardcoded into the index DDL — fragile if seed IDs ever change.
- Most identifiers (oracle_id, multiverse_id, tcgplayer_id, cardmarket_id) explicitly *are not* unique in their respective source catalogs (proven for tcgplayer_id by the §1 characterization; oracle_id by T16; multiverse_id by Scryfall's array shape). The protection is only useful for `scryfall_id` — for which Scryfall already guarantees uniqueness upstream.

### Option C — Application-side deduplication

Leave the schema alone. Change the price lookup to pre-fetch the tcgplayer_id → unique_card_id mapping via a JOIN through `card_version`, then enumerate all matching card_versions per shared ID at the pricing service layer.

**Pros:**
- No schema change.

**Cons:**
- Pushes complexity into every consumer of identifier lookups instead of fixing the root cause.
- Doesn't restore the missing rows — so any future code that does the simple JOIN still has the bug.
- Dev/test data continues to look wrong; the audit metric continues to flag WARN forever.

## 4. Recommendation

**Option A.** It's the smallest blast-radius fix that restores correct semantics. The lost invariant was misleading (it implied uniqueness that the upstream data demonstrably doesn't have — characterized in §1).

## 5. Implementation outline

Five tasks, each TDD-able and independently reviewable:

1. **Schema change** (per `CLAUDE.md` rules — *new schema changes require a migration file under `database/SQL/migrations/`*. Open question §7.1 — is the project ready for migration files yet, or still rebuilding-from-base?):
   - Drop `UNIQUE (card_identifier_ref_id, value)`.
   - Add `CREATE INDEX idx_cei_ref_value ON card_catalog.card_external_identifier (card_identifier_ref_id, value);`.

2. **Stored proc update** (`02_card_schema.sql`, body of `insert_full_card_version`):
   - Change `ON CONFLICT DO NOTHING` → `ON CONFLICT (card_version_id, card_identifier_ref_id) DO NOTHING`.

3. **Backfill** for the dev DB:
   - Re-process the most recent Scryfall raw bulk file via `card_catalog.card.process_large_json`. The fixed proc will now insert the previously-dropped rows on idempotent re-run.

4. **Verify with the audit service:**
   - `automana-run ops.audit.scryfall_identifier_coverage`
   - Expected post-fix: `tcgplayer_id` and `cardmarket_id` → OK, `gap_pct ≈ 0`. `oracle_id` source/stored both around 100% (DB now has ~113k oracle_id rows instead of ~37k). The `scryfall_identifier_coverage` audit row counts of `db_distinct_card_versions` will match `source_presence` for all per-printing identifiers.
   - Update the audit's interpretation guidance in `HEALTH_METRICS.md` (the live-output sample shows the post-fix numbers).

5. **Audit consumers of `card_external_identifier`:**
   - Search for `card_external_identifier` in services and SQL — any query that did `SELECT … FROM card_external_identifier WHERE value = $1` and assumed a single row will now need to handle multiple. Most likely the pricing-side `mtg_card_products` population.
   - Add an integration test that confirms a shared tcgplayer_id resolves to ≥2 `card_version` rows for a known foil/non-foil pair (e.g., `Rogue Kavu 9ED` `tcgplayer_id=12793` per §1).

## 6. Risk

- **Low for the schema change itself** — purely additive (drop UNIQUE, add INDEX with same columns). No data movement at DDL time.
- **Medium for downstream consumers** — any consumer assuming uniqueness will silently start picking arbitrary "first" matches if it does `LIMIT 1`. Search-and-test the consumers up front (task 5).
- **No rollback hazard** — if the change misbehaves, re-applying the UNIQUE constraint requires deleting duplicate rows first, but that's mechanical (delete all but one per `(ref_id, value)`).

## 7. Open questions

1. **Migration strategy.** `CLAUDE.md` says new schema changes require a migration file under `database/SQL/migrations/`. The parallel pipeline-health-alert spec notes the project is currently rebuilding-from-base SQL with no migrations yet. Should this be the first real migration file, or follow the rebuild pattern? **Defer to user.**
2. **Backfill scope.** Just dev for now, or also document/script the prod backfill? **Defer to user.**
3. **`oracle_id` storage growth (~37k → ~113k rows) is a side-effect of Option A.** No issue I can see; flagged for visibility.

## 8. Acceptance criteria

- After implementation, `ops.audit.scryfall_identifier_coverage` shows `gap_pct < 0.1%` for both `tcgplayer_id` and `cardmarket_id`.
- Existing 207-test unit suite still passes.
- One new integration test demonstrates a shared `tcgplayer_id` resolves to ≥2 distinct `card_version_id`s (use `Rogue Kavu 9ED tcgplayer_id=12793` as the fixture — known to have foil + nonfoil printings sharing the ID).
