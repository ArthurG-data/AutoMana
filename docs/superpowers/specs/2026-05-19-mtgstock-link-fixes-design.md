# MTGStock Link Rate Fixes — Design Spec

**Date:** 2026-05-19  
**Status:** Approved  
**Fixes:** Fix 2 (art cards) + Fix 3 (tokens)  
**Target link rate improvement:** 0% → ~78% of previously-rejected rows resolved on next pipeline run

---

## Background

The MTGStock pricing pipeline ingests historical price data (228M raw rows) and resolves each row to a `card_version_id` via three paths: PRINT_ID → EXTERNAL_ID → SET_COLLECTOR. As of 2026-04-30, 6.09M rows (100% of staged rows) failed resolution and landed in `stg_price_observation_reject`. Two root causes account for ~98% of rejects:

- **Category 2 — Art cards** (~680K rows, ~1,274 prints): MTGStocks uses `A`-prefixed art set codes (e.g. `ADFT`) while Scryfall uses `a`-prefixed lowercase codes (e.g. `adft`). The name cross-check in `map_fb` also fails because MTGStocks appends ` Art Card` / ` Art Card (Gold-Stamped Signature)` to card names.
- **Category 1 — Tokens** (~3.8M rows, ~3,612 prints): MTGStocks uses base set codes (e.g. `CMM`) while Scryfall stores tokens under `t`-prefixed codes (e.g. `tcmm`). Token rows have `collector_number = NULL`, so all three existing paths fail.

The reject table is currently empty (cleared by the 2026-05-10 pipeline run). This fix prevents future rejects when the next download runs.

---

## What Changes

### Files

| File | Change |
|------|--------|
| `src/automana/database/SQL/schemas/06_prices.sql` | Add seed INSERTs for both mapping tables; extend both procedures with new CTEs |
| `src/automana/database/SQL/migrations/migration_40_mtgstock_link_fixes.sql` | Applies the same changes on the live DB |

### Mapping table seeds (no schema changes — tables already exist)

**`pricing.mtgstock_art_set_map`** — add 31 missing rows (total: 39)  
Pattern: MTGStocks code = `A` + UPPER(Scryfall code without leading `a`). Exception already in table: `AAINR` → `ainr`.

**`pricing.mtgstock_token_set_map`** — add 186 rows  
Pattern: MTGStocks code = UPPER(Scryfall token set code without leading `t`). Derived from all sets in `card_catalog.sets` where `set_name ILIKE '%Tokens'`.

### Procedure changes

Both `pricing.resolve_price_rejects` and `pricing.load_staging_prices_batched` get two new resolution paths appended after the existing SET_COLLECTOR path:

```
PRINT_ID → EXTERNAL_ID → SET_COLLECTOR → ART_CARD → TOKEN_NAME → UNRESOLVED
```

`resolution_method` column gains two new values: `'ART_CARD'` and `'TOKEN_NAME'`.

---

## Resolution Data Flow

### ART_CARD path (Fix 2)

Triggered when: row has `set_abbr` with an entry in `mtgstock_art_set_map` AND `collector_number IS NOT NULL` AND PRINT_ID/EXTERNAL_ID/SET_COLLECTOR all failed.

```
set_abbr='ADFT', collector_number='003', card_name='Atraxa Art Card'
  → lookup mtgstock_art_set_map WHERE mtgstocks_set_code = UPPER(r.set_abbr)
  → scryfall_set_code = 'adft'
  → strip suffix: REGEXP_REPLACE(card_name, ' Art Card.*$', '', 'i') → 'Atraxa'
  → JOIN card_catalog.sets ON set_code = 'adft'
  → JOIN card_catalog.card_version ON set_id AND collector_number = '003'
  → resolution_method = 'ART_CARD'
```

Name stripping regex `' Art Card.*$'` handles all variants:
- `Atraxa Art Card` → `Atraxa`
- `Atraxa Art Card (Gold-Stamped Signature)` → `Atraxa`
- `Atraxa Art Card (Gold-Stamped Planeswalker Symbol)` → `Atraxa`

No name cross-check is applied after stripping (the collector_number match is the primary key; art cards within a set have unique collector numbers).

### TOKEN_NAME path (Fix 3)

Triggered when: row has `set_abbr` with an entry in `mtgstock_token_set_map` AND `collector_number IS NULL`.

```
set_abbr='CMM', collector_number=NULL, card_name='Wolf // Demon Double-Sided Token'
  → lookup mtgstock_token_set_map WHERE mtgstocks_set_code = UPPER(r.set_abbr)
  → token_set_code = 'tcmm'
  → strip suffix: REGEXP_REPLACE(card_name, '\s*(Token|Double-Sided Token)$', '', 'i') → 'Wolf // Demon'
  → face1 = SPLIT_PART(stripped, ' // ', 1) = 'Wolf'
  → face2 = SPLIT_PART(stripped, ' // ', 2) = 'Demon' (empty string for single-face tokens)
  → JOIN card_catalog.sets ON set_code = 'tcmm'
  → JOIN card_catalog.card_version cv ON set_id
       AND (cv.name ILIKE face1 OR (face2 <> '' AND cv.name ILIKE face2))
  → DISTINCT ON (print_id) ORDER BY print_id, cv.card_version_id  ← tie-break
  → resolution_method = 'TOKEN_NAME'
```

---

## Edge Cases and Error Handling

| Case | Behavior |
|------|----------|
| Art `set_abbr` not in `mtgstock_art_set_map` | CTE returns nothing → row stays UNRESOLVED |
| Token `set_abbr` not in `mtgstock_token_set_map` | CTE returns nothing → row stays UNRESOLVED |
| Two token cards match same face name in same set | `DISTINCT ON (print_id)` picks one deterministically |
| `card_name IS NULL` token row | `WHERE r.card_name IS NOT NULL` guard → UNRESOLVED |
| Rows with no `set_abbr` (8,222 rows) | Structurally blocked → UNRESOLVED (no fix possible) |
| Re-running `resolve_price_rejects` | Idempotent: `WHERE resolved_at IS NULL` guard excludes already-resolved rows |

---

## Testing

### After applying migration_40

```sql
SELECT COUNT(*) FROM pricing.mtgstock_art_set_map;   -- expect 39
SELECT COUNT(*) FROM pricing.mtgstock_token_set_map;  -- expect 186
```

### Smoke test name stripping (run before next pipeline)

```sql
SELECT REGEXP_REPLACE('Atraxa Art Card (Gold-Stamped Signature)', ' Art Card.*$', '', 'i');
-- expect: 'Atraxa'

SELECT REGEXP_REPLACE('Wolf // Demon Double-Sided Token', '\s*(Token|Double-Sided Token)$', '', 'i');
-- expect: 'Wolf // Demon'
```

### After next `mtg_stock_all` run (or manual `resolve_price_rejects()` call)

```sql
-- Resolution method distribution
SELECT resolved_method, COUNT(*)
FROM pricing.stg_price_observation_reject
WHERE resolved_at IS NOT NULL
GROUP BY resolved_method;
-- expect: ART_CARD and TOKEN_NAME rows present

-- Overall link rate
SELECT
  COUNT(*) FILTER (WHERE resolved_at IS NOT NULL) AS resolved,
  COUNT(*) FILTER (WHERE resolved_at IS NULL)     AS open,
  ROUND(100.0 * COUNT(*) FILTER (WHERE resolved_at IS NOT NULL) / NULLIF(COUNT(*), 0), 1) AS link_pct
FROM pricing.stg_price_observation_reject;
-- expect: link_pct approaching ~78% of reject rows resolved
```

---

## What Remains Unresolvable (~22% floor)

| Reason | Estimated rows |
|--------|---------------|
| No `set_abbr` in MTGStocks data | ~8,222 |
| MTGStocks set codes with no Scryfall equivalent | ~80,000 |
| Pre-2015 tokens with no collector_number and no Scryfall cross-reference | ~1,200,000 |
| Catalog gaps (card_version absent from Scryfall ingest) | ~25,000 |

These are structurally blocked and require upstream data from MTGStocks or Scryfall to resolve.

---

## Related Docs

- [`docs/MTGSTOCK_REJECT_ANALYSIS.md`](../MTGSTOCK_REJECT_ANALYSIS.md) — full reject breakdown and fix history
- [`docs/MTGSTOCK_PIPELINE.md`](../MTGSTOCK_PIPELINE.md) — pipeline architecture
- `src/automana/database/SQL/schemas/06_prices.sql` — canonical procedure definitions
- `src/automana/database/SQL/migrations/migration_17_foil_finish_suffix.sql` — Fix 4 (completed 2026-04-29)
