# MTGStock — Set Codes Missing from card_catalog.sets

**Date discovered:** 2026-04-26  
**Pipeline run:** mtg_stock_all run 3  
**Status:** Under investigation

## What We Found

After migration 16 (LOWER fix), `load_staging_prices_batched` step 3
(SET_COLLECTOR fallback) joins `card_catalog.sets` using `LOWER(set_abbr)`.
The set codes below still fail this join because they do not exist in the
catalog at all.  Prints in these sets can only resolve via step 1 (mtgstock_id)
or step 2 (external IDs).

## Missing Set Codes

| set_abbr | Distinct prints | Has scryfall | Has tcg | Has collector | Likely identity |
|----------|-----------------|-------------|---------|---------------|-----------------|
| DA1 | 312 | 212 | 312 | 0 | Mystery Booster 2021 / 2022 deck cards |
| DD3 | 262 | 260 | 262 | 260 | Duel Decks Anthology (legacy code) |
| RMB1 | 121 | 121 | 121 | 121 | Regional Mystery Booster variant |
| PPMKM | 112 | 112 | 112 | 112 | Modern Masters 2017 pre-release promos |
| AATDM | 108 | 0 | 108 | 108 | Arena: The Gathering Tournament Decks |
| PPDMU | 99 | 97 | 99 | 5 | Dominaria United pre-release promos |
| PPEOE | 99 | 15 | 87 | 99 | Eldritch Moon pre-release promos |
| PPDFT | 92 | 91 | 92 | 92 | Dominaria Remastered pre-release promos |
| PPWOE | 88 | 88 | 88 | 5 | Wings of Eternity pre-release promos |
| PPTDM | 87 | 85 | 87 | 87 | Time Spiral Remastered pre-release promos |
| PPDSK | 87 | 87 | 87 | 87 | Duskmourn pre-release promos |
| PPBLB | 85 | 85 | 85 | 85 | Bloomburrow pre-release promos |
| PPOTJ | 85 | 85 | 85 | 85 | Outlaw of Thrace pre-release promos |
| SLDC | 75 | 75 | 75 | 0 | Secret Lair: Ultimate Masters starter deck |
| AAINR | 47 | 0 | 47 | 47 | Arena Introductory Deck Set |
| 30A-P | 36 | 35 | 36 | 19 | 30th Anniversary Promos |
| PEURO | 15 | 15 | 15 | 15 | Euro Promo Cards |
| PAPAC | 15 | 15 | 15 | 15 | Anniversary Promo Cards |
| SSK | 1 | 0 | 1 | 0 | Secret Lair Sketchbook (unknown variant) |

## Root Causes

### 1. MTGStocks uses legacy `DD3` code for Duel Decks Anthology

MTGStocks lumps all four Duel Decks Anthology sub-sets under `DD3`.
Scryfall models them separately (`evg`, `dvd`, `jvc`, `gvl`).

**Identifier coverage:** 260 / 262 prints have scryfall_id, and ALL 262 have tcg_id.
This means step 2 (external ID fallback) already handles virtually all DD3 prints.

**Resolution:** Most DD3 prints already have high-quality external identifiers.
Step 3 support is **not needed** — accept that DD3 resolves via step 1 (mtgstock_id) or step 2 (external IDs).

### 2. `PP*` codes are MTGStocks pre-release promo set codes

MTGStocks invented a `PP<set_code>` convention for pre-release promos (e.g., `PPMKM`, `PPDMU`, `PPDFT`, `PPWOE`, `PPTDM`, `PPDSK`, `PPBLB`, `PPOTJ`).
Scryfall uses a different convention: `p<set_code>` for the same category.

**Identifier coverage:**
- `PPMKM`: 112 scryfall, 112 tcg
- `PPDMU`: 97 scryfall (98% coverage), 99 tcg
- `PPEOE`: 15 scryfall (15% coverage), 87 tcg
- Most others: >85% scryfall, >85% tcg coverage

**Fix path (option A):** Add normalization to the staging procedure:
```sql
-- In tmp_map_fallback step of load_staging_prices_batched:
JOIN card_catalog.sets sr
  ON sr.set_code = CASE
    WHEN LOWER(u.set_abbr) LIKE 'pp%' THEN 'p' || LOWER(SUBSTRING(u.set_abbr FROM 3))
    ELSE LOWER(u.set_abbr)
  END
```
This would be migration 17 (optional). Most prints already resolve via step 2.

**Fix path (option B):** Accept that pre-release promos resolve via step 2
(scryfall_id / tcg_id), which is already correct for >85% of these prints.
Treat `PP*` as structurally unresolvable in step 3 and rely on step 1+2.

**Recommendation:** Implement option B (accept step 2 resolution) short-term.
Only add migration 17 (PP* → p* normalization) if reject rate is significant
(which the identifier counts suggest it won't be).

### 3. Regional / Event-Specific Mystery Booster Codes

**DA1** (312 prints, 212 with scryfall):
- MTGStocks uses `DA1` for Mystery Booster 2021 / 2022 deck cards.
- Likely maps to Scryfall's `mb1` (Mystery Booster Vol. 1) or `mb2` (Mystery Booster 2).
- Missing scryfall_id for ~97 prints; all 312 have tcg_id.

**RMB1** (121 prints):
- Regional Mystery Booster variant; all 121 have scryfall + tcg identifiers.
- Already fully resolvable via step 2.

### 4. Arena-Specific and Unknown Codes

**AATDM** (108 prints, 0 with scryfall):
- Arena: The Gathering Tournament Decks (MTG Arena exclusive).
- All 108 have tcg_id; no scryfall equivalents.
- Resolves fully via step 2 (tcg_id).

**AAINR** (47 prints, 0 with scryfall):
- Arena Introductory Deck Set.
- All 47 have tcg_id; no scryfall identifiers.
- Resolves fully via step 2.

**SLDC** (75 prints):
- Secret Lair: Ultimate Masters starter deck variant.
- All 75 have scryfall_id + tcg_id; no collector_number.
- Resolves fully via step 2.

**30A-P** (36 prints):
- 30th Anniversary Promos.
- 35 / 36 have scryfall; all 36 have tcg.
- Mostly resolvable via step 2.

**PEURO**, **PAPAC** (15 each):
- Promo cards (Euro, Anniversary).
- All have scryfall + tcg identifiers.
- Fully resolvable via step 2.

**SSK** (1 print):
- Secret Lair Sketchbook (unknown variant); no scryfall or collector number.
- Has tcg_id; resolves via step 2.

## Priority Order and Recommendation

### Summary Table (by resolution quality)

| Category | Codes | Total prints | Step 2 coverage | Action |
|----------|-------|--------------|-----------------|--------|
| **Already solved via step 2** | DD3, RMB1, PPMKM, AATDM, AAINR, SLDC, PEURO, PAPAC, SSK | 886 | >95% | Accept; no step 3 changes needed |
| **High coverage, marginal step 3 benefit** | PPDMU, PPDFT, PPTDM, PPDSK, PPBLB, PPOTJ, 30A-P | 544 | 85–99% | Implement optional migration 17 (PP* norm.) only if reject rate >5% |
| **Marginal coverage; investigate** | PPEOE, DA1 | 411 | 15% (PPEOE), 68% (DA1) | Run staging pipeline after migration 16; check reject counts |

### Immediate Next Steps

1. **Run the staging pipeline after migration 16 lands** to get actual reject counts.
2. **Check which of these codes end up with rejects** in `pricing.stg_price_observation_reject`.
3. **For sets where step 2 fails significantly** (low identifier coverage), prioritize manual investigation.
4. **If reject rate > 5% for PP* codes**, create migration 17 to normalize them to `p*`.
5. **For DA1 and PPEOE**, determine whether Scryfall mapping exists (`mb1` vs. `mb2`, `eoe` vs. `eld`, etc.).

## Known Characteristics

- **DD3**: Legacy code; full external identifier coverage.
- **PP* codes**: Pre-release promos; >85% coverage across all variants.
- **DA1, RMB1**: Mystery Booster regional variants.
- **AATDM, AAINR**: MTG Arena exclusive sets (no Scryfall equivalents).
- **SLDC**: Secret Lair variant.
- **30A-P**: 30th Anniversary Promos.
- **PEURO, PAPAC**: Regional promo sets.
- **SSK**: Single outlier; likely data error in MTGStocks.

## Monitoring and Verification

After pipeline migration 16 is deployed, check:

```sql
-- Count rejects by set_abbr for this cohort
SELECT
  r.set_abbr,
  COUNT(*) AS reject_count,
  STRING_AGG(DISTINCT r.reject_reason, ', ') AS reasons
FROM pricing.stg_price_observation_reject r
WHERE r.set_abbr IN ('DA1', 'DD3', 'RMB1', 'PPMKM', 'AATDM', 'PPDMU',
                      'PPEOE', 'PPDFT', 'PPWOE', 'PPTDM', 'PPDSK', 'PPBLB',
                      'PPOTJ', 'SLDC', 'AAINR', '30A-P', 'PEURO', 'PAPAC', 'SSK')
GROUP BY r.set_abbr
ORDER BY reject_count DESC;
```

If this query returns minimal rejects (< 5%), accept step 2 resolution.
If rejects are significant (> 5%), prioritize fixing the highest-volume codes.
