# Reprint Effect Analysis — Design Spec

**Date:** 2026-05-18  
**Notebook:** `notebooks/reprint_effect_analysis.ipynb`  
**Companion:** `notebooks/treatment_price_analysis.ipynb` (style reference)

---

## Research Questions

1. How much does a card's price drop after a reprint, and how quickly does it rebound?
2. Does the type of reprint set (masters, expansion, commander, special) drive different outcomes?
3. After a reprint, does the original printing recover better than the new reprint version?
4. Does rarity (mythic vs rare) change these dynamics?

---

## Data Sources

All data from the AutoMana PostgreSQL database.

| Table | Use |
|---|---|
| `card_catalog.card_version` | Card versions, frame effects, finish |
| `card_catalog.sets` + `set_type_list_ref` | Set release dates and set types |
| `card_catalog.unique_cards_ref` + `rarities_ref` | Card name, rarity |
| `pricing.print_price_daily` | Daily price history (NM, sell, English, TCGPlayer/MTGStocks) |

---

## Key Design Decisions

### Reprint Definition
- A **reprint event** is any appearance of a card (by `unique_card_id`) in a set that is **not** its earliest-ever printing.
- "First printing" = earliest `released_at` across all sets in the DB (including pre-2021 sets outside our price window).
- Scope: mythic + rare, non-digital, across **all set types** (expansion, masters, core, commander, special/Universes Beyond, secret lair).

### Event Time Axis
- `T = 0`: reprint set release date.
- `T = -45`: **clean baseline** — predates virtually all set announcements and spoiler-season movement.
- `T = -21`: secondary timestamp marking the start of active preview season.
- `T = +7`: end of release-week price shock.
- Window: `T-45` to `T+365` (capped by data availability — max `2026-05-16`).
- Three analytically distinct sub-windows:
  - `[T-45, T-21]` — **announcement effect** (set announced, market front-runs reprint probability)
  - `[T-21, T+7]` — **preview season effect** (individual cards spoiled, confirmed reprints drop)
  - `[T+7, T+365]` — **post-release trajectory** (price discovery, recovery or continued decline)

### Baseline Price
- For each reprint event, compute the **baseline price** as the median NM sell price of the card's `regular_nonfoil` finish in the `[T-52, T-38]` window (7-day buffer before T-45).
- If no price exists in that window, fall back to the earliest available price in `[T-90, T-38]`.
- If still no price, the event is excluded from normalized trajectory analysis (still counted in the catalog).
- Normalized price: `indexed_price = daily_price / baseline_price` (1.0 = pre-announcement clean baseline).

### Version Tracking
- **Primary comparison**: `regular_nonfoil` for both original print and reprint version — apples-to-apples, highest liquidity.
- **Parallel foil series**: also track `regular_foil` of the original print normalized to the same T-45 baseline, as a separate series (not merged into primary analysis).
- **Reprint foil flag**: each event is tagged `reprint_includes_foil = True/False` depending on whether the reprint set includes a foil version of the card. This is the single most important moderating variable.
- **Original print**: the `card_version_id` belonging to the card's first-ever set (or earliest set with price data).
- **Reprint version**: the `card_version_id` belonging to the reprint set being studied.

### Set Type Categories
```
masters        → UMA, 2XM, 2X2, CMM, DMR, MMA, MH2, MH3, etc.
expansion      → Standard-legal expansion sets (bonus sheet cards included)
core           → Core sets (M19, M20, M21, etc.)
commander      → Commander precon decks
ub_large       → Universes Beyond large sets (LTR, FIN, SPM, TLA, TMT, etc.)
secret_lair    → Secret Lair drops (print-to-demand, fixed supply window)
list_jumpstart → The List / Special Guests / Jumpstart (moderate pull rate reprints)
```

Note: Secret Lair and list_jumpstart will have low event counts — reported descriptively
if n < 5, excluded from aggregate regression/chart lines.

---

## Notebook Structure

### Part 0 — Setup
- Imports, DB config, helper functions (same pattern as `treatment_price_analysis.ipynb`)
- Constants: `EVENT_WINDOW = (-45, 365)`, `BASELINE_WINDOW = (-52, -38)`, `RARITY_FILTER = ['mythic', 'rare']`
- Set type category map: `masters / expansion / core / commander / ub_large / secret_lair / list_jumpstart`
- `REFRESH = True` flag for re-querying vs loading parquet cache

### Part 1 — Reprint Event Catalog
**SQL:** For every mythic/rare, find all printings ordered by `released_at`. Mark the earliest as the original, all subsequent as reprint events. Join to `set_type_list_ref` for categorization.

**Output:**
- DataFrame: `(event_id, card_name, unique_card_id, rarity, original_set, original_release, reprint_set, reprint_release, reprint_set_type)`
- Summary table: event count by `reprint_set_type` × `rarity`
- Saved to `data/reprint_events.parquet`

### Part 2 — Event Price Windows
**SQL:** For each reprint event, pull `print_price_daily` rows for all `card_version_id`s of that `unique_card_id`, filtered to:
- `finish IN (NONFOIL, FOIL)`, `condition = NM`, `transaction_type = sell`, `language = en`
- Date range: `[reprint_release - 52, reprint_release + 365]`

**Processing:**
1. Separate rows into `version_type`: `original_print` (earliest set) vs `reprint_version` (reprint set) vs `other_reprint` (any other earlier print also affected).
2. Separate `finish_code` column — primary analysis uses `NONFOIL`; foil data kept as parallel series.
3. Compute baseline price = median in `[T-52, T-38]` per `version_type` × `finish_code`. Exclude events with no nonfoil baseline.
4. Tag each event with `reprint_includes_foil` flag (True if the reprint set has a FOIL version of this card in our price data).
5. Compute `indexed_price = price_cents / baseline_cents`.
6. Add `days_from_release = price_date - reprint_release`.
7. Bin days into weekly intervals for smoothing.

**Output:**
- Long-form DataFrame: `(event_id, version_type, days_from_release, indexed_price)`
- Saved to `data/reprint_price_windows.parquet`

### Part 3 — Average Trajectory by Set Type
**Chart:** 2 subplots (mythic / rare), each with one line per `reprint_set_type`.
- X-axis: days from release (`-45` to `+365`), weekly resolution
- Y-axis: median indexed price across all events in that bucket (nonfoil primary)
- Shaded IQR band (p25–p75) per set type
- Three vertical dashed lines: `T-45` (baseline), `T-21` (preview season opens), `T=0` (release day)
- Horizontal dashed line at `y = 1.0` (baseline reference)

**Answers:** How much does each reprint category suppress price on average, and does it recover? Also reveals the announcement-effect phase (T-45 to T-21) vs the spoiler-season phase (T-21 to T0).

### Part 4 — Price Drop Depth
**Metrics per event:**
- `drop_week1`: `indexed_price_at_T+7 - 1.0` (% change, week 1)
- `trough_value`: `min(indexed_price)` in `[T0, T+90]`
- `trough_day`: day at which trough occurs

**Chart:** Box plots — `drop_week1` and `trough_value`, faceted by `reprint_set_type` × `rarity`.

**Summary table:** median + IQR of both metrics by set type and rarity.

**Answers:** How deep is the drop, and does it vary by set type?

### Part 5 — Rebound Analysis
**Metrics per event (computed from trough):**
- `rebound_T90`: `indexed_price_at_T+90 / trough_value - 1`
- `rebound_T180`: `indexed_price_at_T+180 / trough_value - 1`
- `rebound_T365`: `indexed_price_at_T+365 / trough_value - 1`

**Three recovery thresholds (all computed):**

1. **Nominal recovery**: `indexed_price_at_T+365 >= 1.0` — price returns to the T-45 pre-announcement level.
2. **Market-adjusted recovery**: `indexed_price_at_T+365 >= control_group_index_at_T+365` — price keeps pace with comparable unaffected cards over the same period. Control group = cards of same rarity + format tier with no reprints or bans in the window; their median price change from T-45 to each horizon forms the market index.
3. **Spread normalization**: `value_retention_ratio` (original/reprint) stabilizes within a consistent range (observed empirically from Part 6 data).

**Chart:** Line chart of median rebound over time by set type + rarity; three threshold lines overlaid.

**Summary table:** percent of events achieving each recovery threshold at T+90, T+180, T+365.

**Answers:** Does the price come back? On what definition? How does the answer change if you adjust for market inflation?

### Part 6 — Original Print vs Reprint Version
Restricted to events where we have price data for **both** `original_print` and `reprint_version` (nonfoil primary; foil original tracked as a third line where available).

**Metrics:**
- `value_retention_ratio`: `indexed_price_original_nf / indexed_price_reprint_nf` at each time step.
  - Ratio > 1.0: original nonfoil is worth more than the reprint nonfoil (premium expanding)
  - Ratio < 1.0: reprint is priced higher (unusual but happens for premium-art reprints)
- `foil_multiplier_original`: `price_original_foil / price_original_nonfoil` tracked over time — does the foil premium expand after the nonfoil is reprinted?
- Both computed at `T+30, T+90, T+180, T+365`.
- Split by `reprint_includes_foil` flag — the dynamics differ significantly.

**Chart:**
- Panel A: Dual-line normalized trajectory (original NF vs reprint NF), faceted by set type + rarity.
- Panel B (where n ≥ 10): Triple-line chart (original NF / original foil / reprint NF), restricted to events where the reprint does NOT include a foil — cleanest case for foil premium expansion.

**Summary table:** median `value_retention_ratio` and `foil_multiplier_original` by set type, rarity, and `reprint_includes_foil` flag.

**Answers:** Does buying the original print protect you? Does the foil premium on the original expand after the nonfoil gets reprinted?

### Part 7 — Rarity Effect
Cross-cut of Parts 3–6 split by rarity. Focus: does rarity change drop depth, rebound speed, or original vs reprint retention?

**Chart:** Side-by-side comparison — mythic vs rare — for each key metric.

**Answers:** Are mythics more resilient to reprints than rares?

### Part 8 — Conclusions
Synthesized findings in a printed summary + a compact table:

| Set type | Rarity | Avg drop | Trough day | T+365 recovery | Original premium at T+365 |
|---|---|---|---|---|---|
| masters | mythic | ... | ... | ... | ... |
| ... | | | | | |

Human-readable takeaways (4–6 bullet points), in the same style as the treatment notebook.

---

## Technical Notes

- **Parquet caching**: `REFRESH = True` re-runs all SQL; `REFRESH = False` loads from `data/` parquet files.
- **Price source preference**: TCGPlayer first, MTGStocks as fallback (same as treatment notebook).
- **Event exclusion criteria**: No baseline price in `[T-28, T-14]` → excluded from Parts 3–7 but counted in Part 1 catalog.
- **Minimum event size**: Set type buckets with fewer than 5 events are reported but excluded from aggregate charts.
- **Day binning**: Weekly bins (`days // 7 * 7`) for smoothed trajectory lines; raw daily data used for trough/rebound metrics.
- **Data window cap**: Events released after `2025-05-16` (< 1 year of history) have truncated T+365 data; noted in chart footers.

---

## MTG Finance Expert Validation — Resolved

Consulted with MTG finance expert 2026-05-18. All four assumptions updated based on feedback:

| Assumption | Resolution |
|---|---|
| T-21 baseline | Changed to T-45 (clean pre-announcement); T-21 kept as secondary timestamp. Three sub-windows defined. |
| Regular nonfoil primary | Kept. Added parallel original-foil series + `reprint_includes_foil` flag per event. |
| Recovery = nominal price | Changed. Three definitions: nominal, market-adjusted (vs control cards), spread normalization. |
| "Special" catch-all | Split into `ub_large` / `secret_lair` / `list_jumpstart`. Thin buckets reported descriptively only. |

**Key domain insight from expert:** The `reprint_includes_foil` flag is the single most important moderating variable. When the reprint does NOT include a foil, the original foil often holds flat or rises (scarcity identity); when the reprint includes a foil, original foil drops but recovers faster than original nonfoil.

---

## Files

| File | Purpose |
|---|---|
| `notebooks/reprint_effect_analysis.ipynb` | Main notebook |
| `notebooks/data/reprint_events.parquet` | Reprint event catalog |
| `notebooks/data/reprint_price_windows.parquet` | Event price windows (long form) |
| `notebooks/data/reprint_*.png` | Exported charts |
