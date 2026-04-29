# MTGStock Reject Analysis

## Summary

After the full historical backfill (228 M raw rows, 2012–2026) and the first
two fix passes, **5,801,810 rows** from **5,301 distinct print_ids** remain
unresolved in `pricing.stg_price_observation_reject`.

---

## Progress log

| Date | Action | Rows resolved | Open rejects after |
|---|---|---|---|
| 2026-04-27 | Full historical backfill (228 M raw rows) | — | 6,073,613 |
| 2026-04-29 | Case-insensitive set_code fix (`LOWER()` on both sides) | 2,150 prints | ~6,073,613\* |
| 2026-04-29 | **Fix 4** — foil-treatment name suffix + granular finish_ids | 271,803 rows | **5,801,810** |

\* Row count unchanged; 2,150 prints that failed due to case mismatch resolved into `price_observation` on the next run.

---

## Numbers at a glance (current state)

| Metric | Value |
|---|---|
| Total open reject rows | **5,801,810** |
| Distinct unresolved print_ids | **5,301** |
| Terminal (resolved + scryfall delete) | 288,417 |
| New finish types added | SURGE_FOIL (65 867 obs), RIPPLE_FOIL (171 523 obs), RAINBOW_FOIL (22 181 obs) |

---

## Current root-cause breakdown

| Category | Distinct prints | Reject rows | % of open | Fix status |
|---|---|---|---|---|
| **Tokens — no collector_number** | 3,612 | 5,002,675 | 86.2 % | Pending — Fix 3 |
| **Name mismatch in `map_fb` / art cards** | 1,274 | 684,755 | 11.8 % | Pending — Fix 2 |
| **Foil-suffix (unresolvable — no catalog match)** | 391 | 106,158 | 1.8 % | Partially blocked — see below |
| **No set abbreviation** | 24 | 8,222 | 0.1 % | None — structurally blocked |

---

## ✅ Category 4 — Foil-treatment name suffix (DONE)

### What was done

853 prints whose `info.json` name included a foil-treatment qualifier:
```
"Aethergeode Miner (Ripple Foil)"
"Aerith, Last Ancient (Surge Foil)"
"Black Lotus (Galaxy Foil)"
```

**Fix applied (migration 17, 2026-04-29):**
1. Added `pricing.card_finished` codes: `SURGE_FOIL` (16), `RIPPLE_FOIL` (17), `RAINBOW_FOIL` (18).
2. Created `pricing.mtgstock_name_finish_suffix` mapping table (suffix → finish_id) seeded with Surge Foil, Ripple Foil, Rainbow Foil, Foil Etched, Ripper Foil, Textured Foil.
3. Extended the `map_fb` / `tmp_map_fallback` name check in all three procedures with `OR lower(r.card_name) LIKE (lower(uc.card_name) || ' (%')`. Empirically verified safe: zero ambiguous set+cn combinations across all 187 paren-suffix patterns in the reject data.
4. Updated `_prom_batch` (inline promotion) and `_batch` (safety-net `load_prices_from_staged_batched`) to use `COALESCE(fsm.finish_id, CASE WHEN is_foil THEN foil_id ELSE default_id END)`.

**Result:** 271,803 rows resolved; price_observation now has 259,571 new granular-finish observations.

### Remaining foil-suffix rows (391 prints, 106 K rows)

These foil-suffix prints have a set_abbr + collector_number, but the
`card_version` at that position does not exist in the catalog:

| Suffix | Prints | Rows | Root cause |
|---|---|---|---|
| Gold-Stamped Signature | 242 | 66,749 | Art-card set-code mismatch (`AINR` vs `ainr`) — Fix 2 territory |
| Gold-Stamped Planeswalker Symbol | 26 | 5,581 | Same art-card issue |
| Surge Foil | 17 | 3,655 | Set codes not in catalog (9 missing MTGStocks set codes) |
| Top 8 / Winner | 16 | 6,206 | Promo set codes absent from Scryfall catalog |
| Rainbow Foil | 6 | 2,078 | Same missing set code issue |
| Other (art card numbers, misc) | 84 | 21,889 | Various — art cards or catalog gaps |

---

## Category 1 — Tokens without `collector_number` (86.2 %)

### What it is

3,612 token prints. Every `info.json` has `"collector_number": null`.

Sub-types:
- **~2,500 double-sided tokens** — MTGStocks combines two Scryfall token faces into one product (e.g. "Wolf // Demon Double-Sided Token"). No `collector_number`; combined name has no Scryfall match.
- **~700 single-face named tokens** — e.g. "Zombie Token". No `collector_number`.
- **~400 unnamed tokens**.

### Why all three resolution paths fail

1. **print_id path**: none have an `mtgstock_id` entry in `card_external_identifier`.
2. **scryfall_id path**: `scryfallId` is `null` in every `info.json`.
3. **set+collector path**: `collector_number` is `null` → `map_fb` WHERE clause excludes them.

Additional structural mismatch: Scryfall stores token sets under prefixed codes (`tcmm`, `twho`, `tmh3`, …) while MTGStocks uses the base set code (`CMM`, `WHO`, `MH3`). Even if `collector_number` were present, the current set-code join would miss them.

### Fix path — Fix 3 (pending)

Build a `mtgstock_token_set_map` lookup table:
```
CMM  → tcmm
WHO  → twho
MH3  → tmh3
2X2  → t2x2
...
```

Then add a fourth resolution path in `resolve_price_rejects` / `load_staging_prices_batched` that:
1. Strips face names from double-sided token slugs ("Wolf // Demon" → try "Wolf", then "Demon").
2. Joins `card_catalog.card_version cv JOIN card_catalog.sets s ON s.set_code = token_set_code WHERE cv.name ILIKE r.card_name`.
3. Marks resolved rows with `resolution_method = 'TOKEN_NAME'`.

---

## Category 2 — `map_fb` name mismatch (11.8 %)

### What it is

1,274 prints that have a valid `set_abbr`, `collector_number`, and a matching `card_version` — but the name cross-check in `map_fb` blocks them even with the Fix 4 LIKE extension.

Sub-types:

| Sub-type | Prints | Notes |
|---|---|---|
| Art cards (`AAINR`, `ADFT`, etc.) | ~800 | "X Art Card" ≠ "X // X" in catalog; **plus** MTGStocks uses `AAINR` while Scryfall uses `ainr` |
| Gold-Stamped (art-card territory) | ~268 | Same set-code mismatch as art cards |
| SLD variants / PLST / other promos | ~206 | Various name drift / missing set codes |

### Fix path — Fix 2 (pending)

1. Add an art-set-code mapping table:
   ```
   AAINR → ainr,  ADFT → adft,  AEOE → aeoe,  AFIN → afin,  AATDM → aatdm, …
   ```
2. Add a `map_art` CTE in `resolve_price_rejects` and `load_staging_prices_batched` that:
   - Strips `' Art Card'` and `' Art Card (Gold-Stamped Signature)'` from `r.card_name`.
   - Looks up `art_set_code` from the mapping table using `r.set_abbr`.
   - Joins `card_catalog.sets s ON s.set_code = art_set_code` and matches by collector_number.

---

## Category 3 — No set abbreviation (0.1 %, structurally blocked)

351 prints → now reduced to **24 prints / 8,222 rows** after case-insensitive fix.

`card_set.abbreviation` is null/empty in `info.json`. No set code → `map_fb` WHERE clause excludes them. No `scryfallId`. No `tcg_id` match. Requires MTGStocks to populate the `abbreviation` field, or a manual mapping table keyed on `print_id`.

---

## The one print with a scryfallId (BLB Forest 0280)

Print_id `114127` — "Forest (0280)" from Bloomburrow. Its `info.json` has a populated `scryfallId` (`0000419b-...`) but BLB collector_number 280 is absent from `card_catalog.card_version` (BLB has Forests at cn 278, 279, 281, 377, 378 but not 280). This is a catalog gap in the Scryfall data that was ingested. Still unresolved — tracked in the foil-suffix bucket above under suffix `0280`.

---

## What remains genuinely unresolvable

| Reason | Prints | Rows |
|---|---|---|
| No set_abbr | 24 | 8,222 |
| MTGStocks set codes with no Scryfall equivalent (promos, PLST variants) | ~150 | ~80,000 |
| Old tokens (pre-2015) with no collector_number and no Scryfall cross-reference | ~1,000 | ~1,200,000 |
| Catalog gaps (card_version absent from Scryfall ingest) | ~30 | ~25,000 |

Estimated irreducible floor: **~1.3 M rows (~22.4 % of current open rejects)**

---

## Remaining fix plan

| Priority | Fix | Rows recoverable | Effort | Status |
|---|---|---|---|---|
| ~~1~~ | ~~Foil-treatment name suffix~~ | ~~403 K~~ | ~~1 SQL line + migration~~ | ✅ **Done** (271 803 rows, 2026-04-29) |
| 2 | Art card set-code + name mapping | ~680 K | Mapping table + new `map_art` CTE | Pending |
| 3 | Token resolution via `mtgstock_token_set_map` | ~3.8 M | New mapping table + 4th resolution path | Pending |
| — | No-set-abbr + old tokens + catalog gaps | 0–small | Structurally blocked / requires upstream data | Blocked |

Applying fixes 2–3 would reduce open rejects from **5.8 M → ~1.3 M** (~78 % reduction on remaining).

---

## Related docs

- [`docs/MTGSTOCK_PIPELINE.md`](MTGSTOCK_PIPELINE.md) — pipeline architecture and stage descriptions
- [`src/automana/database/SQL/schemas/06_prices.sql`](../src/automana/database/SQL/schemas/06_prices.sql) — `resolve_price_rejects`, `load_staging_prices_batched`, `load_prices_from_staged_batched`
- [`src/automana/database/SQL/migrations/migration_17_foil_finish_suffix.sql`](../src/automana/database/SQL/migrations/migration_17_foil_finish_suffix.sql) — Fix 4 migration
