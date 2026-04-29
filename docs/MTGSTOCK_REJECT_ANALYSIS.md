# MTGStock Reject Analysis

## Summary

After the full historical backfill (228 M raw rows, 2012–2026), **6,073,613 rows** from **5,978 distinct print_ids** remain unresolved in `pricing.stg_price_observation_reject`. This document explains why each category fails and the most actionable fix path for each.

---

## Numbers at a glance

| Metric | Value |
|---|---|
| Total open reject rows | 6,073,613 |
| Distinct unresolved print_ids | 5,978 |
| Print_id folders on disk | 102,891 |
| Prints with mtgstock_id in `card_external_identifier` | 92,121 |
| Prints resolved after case-insensitive fix (2026-04-29) | 2,150 |
| Prints with `scryfallId` in `info.json` | **1** (BLB Forest 0280 — catalog gap) |
| Prints with no `scryfallId` in info.json | 5,977 |

---

## Root-cause breakdown

| Category | Distinct prints | Reject rows | % of total rows | Fix complexity |
|---|---|---|---|---|
| **Tokens — no collector_number** | 3,024 | 4,217,863 | 69.4 % | Medium — needs token-set mapping |
| **Name mismatch in `map_fb`** | 1,099 | 634,950 | 10.5 % | Low–Medium (see details) |
| **No set abbreviation** | 351 | 509,218 | 8.4 % | None — structurally unresolvable |
| **Foil-treatment name suffix** | 853 | 402,851 | 6.6 % | **Low — one-line SQL fix** |
| **Art Cards** | 651 | 308,731 | 5.1 % | Medium — needs set-code + name mapping |

---

## Category 1 — Tokens without `collector_number` (69.4 %)

### What it is

3,024 token prints. Every `info.json` has `"collector_number": null`.

Sub-types:
- **2,330 double-sided tokens** — MTGStocks combines two Scryfall token faces into one product (e.g. "Wolf // Demon Double-Sided Token"). The combined product has no `collector_number` and uses a `tcgplayer.id` that does not match any entry in `card_external_identifier`.
- **442 single-face named tokens** — e.g. "Zombie Token". No `collector_number`.
- **188 unnamed tokens**.

### Why all three resolution paths fail

1. **print_id path**: none of the 3,024 have an `mtgstock_id` entry in `card_external_identifier`.
2. **scryfall_id path**: `scryfallId` is `null` in every `info.json`.
3. **set+collector path**: `collector_number` is `null` → `map_fb` WHERE clause excludes them immediately.

There is an additional structural mismatch: Scryfall stores token sets under prefixed codes (`tcmm`, `twho`, `tmh3`, …) while MTGStocks uses the base set code (`CMM`, `WHO`, `MH3`). Even if `collector_number` were present, the current set-code join would miss them.

### Fix path

Build a `mtgstock_token_set_map` lookup table:

```
MTGStocks set_abbr → Scryfall token set_code
CMM  → tcmm
WHO  → twho
MH3  → tmh3
2X2  → t2x2
...
```

Then add a fourth resolution path in `resolve_price_rejects` that:
1. Strips face names from double-sided token slugs ("Wolf // Demon" → try "Wolf", then "Demon").
2. Joins `card_catalog.card_version cv JOIN card_catalog.sets s ON s.set_code = token_set_code WHERE cv.name ILIKE r.card_name`.
3. Marks the resolved rows with `resolution_method = 'TOKEN_NAME'`.

---

## Category 2 — `map_fb` name filter blocking (10.5 %)

### What it is

1,099 prints that have a valid `set_abbr` in the catalog **and** a `collector_number` **and** a matching `card_version` in the DB — but the name cross-check inside `map_fb` eliminates them:

```sql
AND (r.card_name IS NULL OR uc.card_name IS NULL OR lower(uc.card_name) = lower(r.card_name))
```

Sub-types and counts:

| Sub-type | Prints | Notes |
|---|---|---|
| Double-sided tokens w/ cn | 853 | MTGStocks assigns the base card's `collector_number` to its token product; the name never matches |
| Art cards w/ set+cn | 368 | "X Art Card" ≠ "X // X" in catalog |
| Single-face tokens w/ cn | 134 | Token name differs from DB card at that set+cn |
| Other (Dungeons, SLD variants, PLST) | 70 | Various name drift |

### Important constraint

975 of the 2,147 set+cn combinations have multiple MTGStocks prints pointing to the same `card_version_id`. The name check was intended to disambiguate. Removing it entirely would not be safe.

### Fix path

Targeted per-sub-type adjustments rather than removing the name check globally:

- **Foil treatment** (handled in Category 4 below — same root cause, different symptom).
- **Double-sided tokens with cn**: detect `r.card_name LIKE '% // % %Token%'` and skip the name filter for that sub-class (tokens at the same set+cn are unambiguous in practice).
- **Art cards**: strip `' Art Card'` suffix before comparing names.

---

## Category 3 — No set abbreviation (8.4 %)

### What it is

351 prints where `card_set.abbreviation` is `null` or empty in `info.json`. Examples:
- Oversized promotional cards (print_ids 34195+)
- Guild tokens (27730–27739)
- Miscellaneous promotional items

### Why unresolvable

No set code → `map_fb` WHERE clause excludes them. No `scryfallId`. No `tcg_id` match in catalog.

### Fix path

None with current data. These would require MTGStocks to populate the `abbreviation` field, or a manual mapping table keyed on `print_id`.

---

## Category 4 — Foil-treatment name suffix (6.6 %) ⭐ Most actionable

### What it is

853 prints whose `info.json` name includes a foil-treatment qualifier in parentheses:

```
"Aethergeode Miner (Ripple Foil)"
"Aerith, Last Ancient (Surge Foil)"
"Black Lotus (Galaxy Foil)"
```

The DB card name is just `"Aethergeode Miner"`. The set_abbr and `collector_number` match exactly and are unambiguous (one `card_version` per set+cn). The name check fails because of the suffix.

### Fix path — one-line SQL change

In `resolve_price_rejects` (and `load_staging_prices_batched`), extend the name predicate in `map_fb`:

```sql
-- Before:
AND (r.card_name IS NULL OR uc.card_name IS NULL OR lower(uc.card_name) = lower(r.card_name))

-- After:
AND (
    r.card_name IS NULL
    OR uc.card_name IS NULL
    OR lower(uc.card_name) = lower(r.card_name)
    OR lower(r.card_name) LIKE (lower(uc.card_name) || ' (%)')
)
```

This resolves 561+ foil-treatment prints unambiguously. The extra OR is safe because each affected set+cn maps to exactly one `card_version_id`.

---

## Category 5 — Art Cards (5.1 %)

### What it is

651 prints stored by MTGStocks as `"X Art Card"` or `"X Art Card (Gold-Stamped Signature)"`. Scryfall stores the same cards as `"X // X"` (double-faced art_series layout).

Set-code mismatches also apply: MTGStocks uses `AAINR`, `ADFT`, `AEOE`, `AFIN`, `AATDM`, etc., while Scryfall prefixes art-series set codes with `a` (`ainr`, `adft`, …).

### Fix path

1. Add an art-set-code mapping table:
   ```
   AAINR → ainr
   ADFT  → adft
   AEOE  → aeoe
   AFIN  → afin
   AATDM → aatdm
   ...
   ```
2. Add a dedicated `map_art` CTE in `resolve_price_rejects` that:
   - Strips `' Art Card'` and `' Art Card (Gold-Stamped Signature)'` from `r.card_name`.
   - Looks up `art_set_code` from the mapping table using `r.set_abbr`.
   - Joins `card_catalog.sets s ON s.set_code = art_set_code` and matches by collector_number.

---

## The one print with a scryfallId (BLB Forest 0280)

Print_id `114127` — "Forest (0280)" from Bloomburrow (BLB). Its `info.json` has a populated `scryfallId` (`0000419b-...`) and the reject row also carries this scryfall_id. It still fails because BLB collector_number 280 is absent from `card_catalog.card_version`. BLB does have Forests at cn 278, 279, 281, 377, 378 but not 280 — this is a catalog gap in the Scryfall data that was ingested.

---

## Genuinely unresolvable (~18.4 % / ~1.1 M rows)

- **351 prints with no set_abbr** — no resolution path exists.
- **~158 prints** with MTGStocks set codes that have no Scryfall equivalent.
- **~37 prints** present in MTGStocks but genuinely absent from the Scryfall-sourced catalog.
- **Mass of old tokens** (pre-2015) with no `collector_number` and no Scryfall cross-reference.

---

## Prioritised fix plan

| Priority | Fix | Rows recovered | Effort |
|---|---|---|---|
| 1 | Foil-treatment name suffix (`LIKE` extension in `map_fb`) | ~403 K | 1 SQL line, 1 migration |
| 2 | Art card set-code + name mapping | ~309 K | Mapping table + new CTE |
| 3 | Token resolution via `mtgstock_token_set_map` | ~4.2 M | New mapping table + 4th resolution path |
| — | No-set-abbr + old tokens | 0 | Structurally blocked |

Applying fixes 1–3 in order would reduce open rejects from **6.07 M → ~1.1 M** (~82 % reduction).

---

## Related docs

- [`docs/MTGSTOCK_PIPELINE.md`](MTGSTOCK_PIPELINE.md) — pipeline architecture and stage descriptions
- [`src/automana/database/SQL/schemas/06_prices.sql`](../src/automana/database/SQL/schemas/06_prices.sql) — `resolve_price_rejects` and `load_staging_prices_batched` source
