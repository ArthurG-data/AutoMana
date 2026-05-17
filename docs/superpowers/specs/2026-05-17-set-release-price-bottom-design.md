# Set Release Price Bottom Analysis — Design Spec

**Date:** 2026-05-17  
**Research question:** When, after a new expansion set is released, do MTG card prices reach their lowest point?

---

## Scope

- **Sets:** Regular expansion sets (`set_type = 'expansion'`), 2021–2024 inclusive (data coverage starts 2021-05-10)
- **Window:** Days 0–150 post-release (≈5 months)
- **Day 0 anchor:** Official `released_at` date; pre-release prices (which exist in the DB) are excluded by filtering `price_date >= released_at`
- **Finish:** Nonfoil only (first pass)
- **Unit of analysis:** Set × rarity group (mythic, rare, uncommon, common)
- **Price metric:** `list_low_cents` from `pricing.print_price_daily` (most stable signal; sold prices are sparse)

---

## Data Extraction

Single SQL query joining:

```
pricing.print_price_daily
  → card_catalog.card_version       (rarity, set FK)
  → card_catalog.rarities_ref       (rarity name)
  → card_catalog.sets               (released_at)
  → card_catalog.set_type_list_ref  (filter: expansion)
  → card_catalog.card_finished      (filter: nonfoil)
```

Computed column: `(price_date - released_at)::int AS days_since_release`

Filter: `price_date BETWEEN released_at AND released_at + 150`

Output: one row per `(set_code, rarity_name, days_since_release, card_version_id)` with `list_low_cents`.

**Checkpoint:** Save raw extract to `notebooks/data/set_price_window.parquet`. Subsequent runs load from parquet unless `--refresh` flag is set.

---

## Analysis Pipeline

All steps in the notebook, in order:

### Step 1 — Daily aggregate per set × rarity

For each `(set_code, rarity_name, days_since_release)`:
- `median_price` = median of `list_low_cents` across all cards in that group
- Drop groups with fewer than 5 cards (tokens, promos that slip through)

### Step 2 — Normalize to day-0 index

```
price_index = (median_price / median_price[day=0]) * 100
```

Day 0 = the first available price on or after release date. If no price exists on day 0 exactly, use the first available day (up to day 7) as the anchor.

This normalizes out absolute price differences between sets so curves are comparable.

### Step 3 — Smooth

Apply a **7-day rolling median** on `price_index` per series. This removes weekly MTGStocks update artifacts and noise from thin markets.

### Step 4 — Rate of change (velocity)

Compute a **14-day rolling % change** on the smoothed index:

```
roc = smoothed_index.pct_change(periods=14) * 100
```

A strongly negative ROC = prices still falling fast. ROC near zero = prices stabilizing.

### Step 5 — Inflection detection

For each `(set_code, rarity)` series, find the **inflection day**: the first day where the 14-day ROC rises above a threshold (e.g., −5%) after having been below it for at least 7 consecutive days.

This marks the transition from "actively declining" to "stabilizing," which is a better signal than the raw minimum (which can be a one-day spike).

Fallback: if no inflection is found within 150 days, use the day of the raw minimum.

### Step 6 — Distribution across sets

Collect all `(rarity, inflection_day)` pairs across sets. Plot per-rarity:
- Histogram of inflection days (bin width = 7 days)
- Median and IQR summary

---

## Visualizations

1. **Average normalized price curve** — one line per rarity, median across all sets, with 25th–75th percentile band (shaded). X-axis = days since release, Y = price index (100 = day 0).

2. **Rate-of-change chart** — one recent set (e.g., Bloomburrow) showing smoothed index + ROC on a dual-axis, with the detected inflection day marked.

3. **Inflection day distribution** — 2×2 faceted histogram (one per rarity), showing where across sets the bottom tends to occur.

4. **Set-level heatmap** (optional) — sets on Y-axis, days on X-axis, color = price index value. Good for spotting outlier sets.

---

## Notebook Structure

```
notebooks/card_lowest_price_research.ipynb
├── Cell 0: Imports + DB connection helper
├── Cell 1: SQL extract → parquet checkpoint
├── Cell 2: Load parquet, inspect shape/nulls
├── Cell 3: Step 1 — daily aggregate
├── Cell 4: Step 2 — normalize
├── Cell 5: Step 3 — smooth
├── Cell 6: Step 4 — rate of change
├── Cell 7: Step 5 — inflection detection
├── Cell 8: Figure 1 — average price curve per rarity
├── Cell 9: Figure 2 — single-set ROC example
├── Cell 10: Figure 3 — inflection day distributions
└── Cell 11: Summary table — median inflection day per rarity
```

---

## DB Connection Approach

Use `psycopg2` + `pandas.read_sql()`. Connection string from environment variable `DATABASE_URL` (already set in `.env`). No ORM, no async — notebooks are synchronous.

```python
import os, psycopg2, pandas as pd
conn = psycopg2.connect(os.environ["DATABASE_URL"])
df = pd.read_sql(SQL_QUERY, conn)
df.to_parquet("data/set_price_window.parquet", index=False)
```

---

## Out of Scope (first pass)

- Foil prices
- Commander / Masters / other set types
- Per-card granularity
- Format legality correlation
- Pre-release price behavior
