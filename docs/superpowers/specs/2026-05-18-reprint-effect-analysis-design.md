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
- `T = -21`: proxy for announcement/spoiler season start (~3 weeks before release).
- Window: `T-21` to `T+365` (capped by data availability — max `2026-05-16`).

### Baseline Price
- For each reprint event, compute the **baseline price** as the median NM sell price of the card's `regular_nonfoil` finish in the `[T-28, T-14]` window.
- If no price exists in that window, the event is excluded from normalized trajectory analysis (still counted in the catalog).
- Normalized price: `indexed_price = daily_price / baseline_price` (1.0 = pre-announcement level).

### Version Tracking
- **Original print**: the `card_version_id` belonging to the card's first-ever set (or earliest set with price data).
- **Reprint version**: the `card_version_id` belonging to the reprint set.
- Both tracked in `regular_nonfoil` finish for a clean apples-to-apples comparison.

### Set Type Categories
```
masters        → UMA, 2XM, 2X2, CMM, DMR, MMA, etc.
expansion      → Standard-legal expansion sets
core           → Core sets (M19, M20, M21, etc.)
commander      → Commander precon decks
special        → Universes Beyond, Secret Lair, Jumpstart, etc.
```

---

## Notebook Structure

### Part 0 — Setup
- Imports, DB config, helper functions (same pattern as `treatment_price_analysis.ipynb`)
- Constants: `EVENT_WINDOW = (-21, 365)`, `RARITY_FILTER = ['mythic', 'rare']`
- `REFRESH = True` flag for re-querying vs loading parquet cache

### Part 1 — Reprint Event Catalog
**SQL:** For every mythic/rare, find all printings ordered by `released_at`. Mark the earliest as the original, all subsequent as reprint events. Join to `set_type_list_ref` for categorization.

**Output:**
- DataFrame: `(event_id, card_name, unique_card_id, rarity, original_set, original_release, reprint_set, reprint_release, reprint_set_type)`
- Summary table: event count by `reprint_set_type` × `rarity`
- Saved to `data/reprint_events.parquet`

### Part 2 — Event Price Windows
**SQL:** For each reprint event, pull `print_price_daily` rows for all `card_version_id`s of that `unique_card_id`, filtered to:
- `finish = NONFOIL`, `condition = NM`, `transaction_type = sell`, `language = en`
- Date range: `[reprint_release - 28, reprint_release + 365]`

**Processing:**
1. Separate rows into `version_type`: `original_print` (earliest set) vs `reprint_version` (reprint set) vs `other_reprint` (any other earlier print also affected).
2. Compute baseline price = median in `[T-28, T-14]` per `version_type`. Exclude events with no baseline.
3. Compute `indexed_price = price_cents / baseline_cents`.
4. Add `days_from_release = price_date - reprint_release`.
5. Bin days into weekly intervals for smoothing.

**Output:**
- Long-form DataFrame: `(event_id, version_type, days_from_release, indexed_price)`
- Saved to `data/reprint_price_windows.parquet`

### Part 3 — Average Trajectory by Set Type
**Chart:** 2 subplots (mythic / rare), each with one line per `reprint_set_type`.
- X-axis: days from release (`-21` to `+365`), weekly resolution
- Y-axis: median indexed price across all events in that bucket
- Shaded IQR band (p25–p75) per set type
- Horizontal dashed line at `y = 1.0` (pre-announcement baseline)
- Vertical dashed line at `x = 0` (release day)

**Answers:** How much does each reprint category suppress price on average, and does it recover?

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
- `full_recovery_flag`: boolean — does `indexed_price_at_T+365 >= 1.0`?

**Chart:** Line chart of median rebound over time, by set type + rarity.

**Summary table:** percent of events achieving full recovery at T+90, T+180, T+365.

**Answers:** Does the price ever come back, and how long does it take?

### Part 6 — Original Print vs Reprint Version
Restricted to events where we have price data for **both** `original_print` and `reprint_version`.

**Metrics:**
- `value_retention_ratio`: `indexed_price_original / indexed_price_reprint` at each time step
- If `ratio > 1`: original is holding value better than the reprint
- Computed at `T+30, T+90, T+180, T+365`

**Chart:** Dual-line normalized trajectory — original vs reprint, for each `reprint_set_type`. Faceted by rarity.

**Summary table:** median `value_retention_ratio` by set type and rarity at each horizon.

**Answers:** Does buying the original print protect you better than buying the reprint?

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

## MTG Finance Assumptions to Validate

The following assumptions should be reviewed by the MTG finance expert before finalizing:

1. **T-21 as announcement proxy**: WotC typically previews cards 2–3 weeks before release. Some cards are revealed earlier via pack leaks or official previews. This is a simplification.
2. **Regular nonfoil as price proxy**: We compare `regular_nonfoil` for both original and reprint versions. Foil/treatment price dynamics after reprints may differ significantly.
3. **"Recovery" definition**: We define full recovery as returning to the pre-announcement price. In finance terms this ignores opportunity cost and market-wide MTG price trends (which have been inflationary 2021–2026).
4. **Set type taxonomy**: "Special" is a catch-all for Universes Beyond, Secret Lair, Jumpstart. These have different print run dynamics and may warrant separation.

---

## Files

| File | Purpose |
|---|---|
| `notebooks/reprint_effect_analysis.ipynb` | Main notebook |
| `notebooks/data/reprint_events.parquet` | Reprint event catalog |
| `notebooks/data/reprint_price_windows.parquet` | Event price windows (long form) |
| `notebooks/data/reprint_*.png` | Exported charts |
