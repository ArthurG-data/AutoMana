# Set Release Price Bottom Analysis — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Jupyter notebook that identifies when, after a set release, MTG card prices reach their lowest point — per rarity group, per expansion set.

**Architecture:** Direct psycopg2 → pandas pipeline. One SQL query extracts the 0–150 day post-release window per set × rarity × card into a parquet checkpoint. All analysis (normalization, smoothing, rate of change, inflection detection) runs in pandas. Three matplotlib figures summarize the findings.

**Tech Stack:** Python 3, psycopg2, pandas, numpy, matplotlib, pathlib

---

## File Map

| File | Role |
|---|---|
| `notebooks/card_lowest_price_research.ipynb` | Main research notebook (all work goes here) |
| `notebooks/data/set_price_window.parquet` | Parquet checkpoint — written once, loaded on subsequent runs |

---

### Task 1: Imports, DB connection, and SQL extract → parquet

**Files:**
- Modify: `notebooks/card_lowest_price_research.ipynb` (cells 0–1)

- [ ] **Step 1: Clear the notebook and write Cell 0 — imports and connection helper**

Replace the notebook content entirely. Cell 0 source:

```python
import os
import psycopg2
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from pathlib import Path

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
PARQUET_PATH = DATA_DIR / "set_price_window.parquet"
REFRESH = False  # set True to re-query the DB

DB_CONFIG = dict(
    host="localhost",
    port=5433,
    dbname="automana",
    user="app_readonly",
    password=os.environ.get("AUTOMANA_READONLY_PASSWORD", ""),  # set this env var
)

def get_conn():
    return psycopg2.connect(**DB_CONFIG)
```

- [ ] **Step 2: Write Cell 1 — SQL query and parquet checkpoint**

Cell 1 source:

```python
SQL = """
SELECT
    s.set_code,
    s.set_name,
    s.released_at,
    r.rarity_name,
    cv.card_version_id,
    ppd.price_date,
    (ppd.price_date - s.released_at)::int AS days_since_release,
    ppd.list_low_cents
FROM pricing.print_price_daily ppd
JOIN card_catalog.card_version cv       ON cv.card_version_id = ppd.card_version_id
JOIN card_catalog.rarities_ref r        ON r.rarity_id = cv.rarity_id
JOIN card_catalog.sets s                ON s.set_id = cv.set_id
JOIN card_catalog.set_type_list_ref st  ON st.set_type_id = s.set_type_id
WHERE st.set_type = 'expansion'
  AND s.released_at BETWEEN '2021-01-01' AND '2025-01-01'
  AND ppd.price_date >= s.released_at
  AND ppd.price_date <= s.released_at + INTERVAL '150 days'
  AND ppd.finish_id = 1                 -- NONFOIL
  AND ppd.list_low_cents IS NOT NULL
  AND ppd.list_low_cents > 0
  AND r.rarity_name IN ('common', 'uncommon', 'rare', 'mythic')
"""

if REFRESH or not PARQUET_PATH.exists():
    print("Querying DB…")
    with get_conn() as conn:
        raw = pd.read_sql(SQL, conn, parse_dates=["released_at", "price_date"])
    raw.to_parquet(PARQUET_PATH, index=False)
    print(f"Saved {len(raw):,} rows → {PARQUET_PATH}")
else:
    raw = pd.read_parquet(PARQUET_PATH)
    print(f"Loaded {len(raw):,} rows from parquet")

print(raw.dtypes)
print(raw.head(3))
```

- [ ] **Step 3: Run Cell 0 then Cell 1 (set AUTOMANA_READONLY_PASSWORD first)**

In terminal before launching Jupyter:
```bash
export AUTOMANA_READONLY_PASSWORD="<your app_readonly password>"
jupyter notebook notebooks/card_lowest_price_research.ipynb
```

If you don't know the password for `app_readonly`, connect as `automana_admin` instead (change `user` in `DB_CONFIG`). The query is read-only.

Expected output: a row count (~2M rows) and parquet file written to `notebooks/data/set_price_window.parquet`.

- [ ] **Step 4: Inspect coverage**

Cell 2 source:

```python
print("Sets in data:", raw["set_code"].nunique())
print("Rarity breakdown:\n", raw["rarity_name"].value_counts())
print("Days range:", raw["days_since_release"].min(), "→", raw["days_since_release"].max())
print("Null list_low_cents:", raw["list_low_cents"].isna().sum())
sets_summary = (
    raw.groupby(["set_code", "set_name", "released_at"])
    .agg(cards=("card_version_id", "nunique"), rows=("list_low_cents", "count"))
    .sort_values("released_at")
)
display(sets_summary)
```

Verify: 20–25 sets, all four rarities present, zero nulls.

---

### Task 2: Daily aggregate per set × rarity

**Files:**
- Modify: `notebooks/card_lowest_price_research.ipynb` (cell 3)

- [ ] **Step 1: Write Cell 3 — daily median per set × rarity × day**

```python
# Median list_low_cents across all cards in the group for each day
daily = (
    raw.groupby(["set_code", "set_name", "released_at", "rarity_name", "days_since_release"])
    ["list_low_cents"]
    .agg(
        median_cents="median",
        card_count="nunique",
    )
    .reset_index()
)

# Drop groups with fewer than 5 distinct cards (thin markets / promos slipping through)
daily = daily[daily["card_count"] >= 5].copy()

print(f"Rows after aggregation: {len(daily):,}")
print(daily.head(10))
```

- [ ] **Step 2: Verify shape**

Expected: one row per `(set_code, rarity_name, days_since_release)`. Run `daily.groupby(["set_code","rarity_name"]).size().describe()` — each series should have ~140–150 days.

---

### Task 3: Normalize to day-0 index

**Files:**
- Modify: `notebooks/card_lowest_price_research.ipynb` (cell 4)

- [ ] **Step 1: Write Cell 4 — price index (day-0 = 100)**

```python
# Anchor = first available price day per (set_code, rarity_name) on or after release
# In practice this is always day 0, but we guard against gaps up to day 7
def day0_price(group):
    anchor = group[group["days_since_release"] <= 7].nsmallest(1, "days_since_release")
    if anchor.empty:
        return pd.Series(np.nan, index=group.index)
    base = anchor["median_cents"].values[0]
    if base == 0:
        return pd.Series(np.nan, index=group.index)
    return (group["median_cents"] / base) * 100

daily["price_index"] = (
    daily.groupby(["set_code", "rarity_name"], group_keys=False)
    .apply(day0_price)
)

# Drop series that couldn't be anchored
daily = daily.dropna(subset=["price_index"])
print(f"Rows after normalisation: {len(daily):,}")
print(daily[daily["days_since_release"] == 0][["set_code", "rarity_name", "price_index"]].head(8))
```

All day-0 rows should show `price_index ≈ 100`.

---

### Task 4: Smooth with 7-day rolling median

**Files:**
- Modify: `notebooks/card_lowest_price_research.ipynb` (cell 5)

- [ ] **Step 1: Write Cell 5 — smoothing**

```python
daily = daily.sort_values(["set_code", "rarity_name", "days_since_release"])

daily["smoothed"] = (
    daily.groupby(["set_code", "rarity_name"])["price_index"]
    .transform(lambda s: s.rolling(window=7, min_periods=3, center=True).median())
)

# Spot-check: one set, one rarity
sample = daily[(daily["set_code"] == "dmu") & (daily["rarity_name"] == "rare")]
print(sample[["days_since_release", "price_index", "smoothed"]].head(15))
```

---

### Task 5: Rate of change (14-day rolling % change)

**Files:**
- Modify: `notebooks/card_lowest_price_research.ipynb` (cell 6)

- [ ] **Step 1: Write Cell 6 — ROC**

```python
daily["roc_14d"] = (
    daily.groupby(["set_code", "rarity_name"])["smoothed"]
    .transform(lambda s: s.pct_change(periods=14) * 100)
)

print(daily[daily["set_code"] == "dmu"][
    ["days_since_release", "rarity_name", "smoothed", "roc_14d"]
].dropna().head(20))
```

A strongly negative `roc_14d` (e.g., −30%) means prices are still falling fast. Values near 0 mean prices have stabilized.

---

### Task 6: Inflection detection

**Files:**
- Modify: `notebooks/card_lowest_price_research.ipynb` (cell 7)

- [ ] **Step 1: Write Cell 7 — detect bottom day per (set, rarity)**

The inflection day is the first day where `roc_14d` rises above −5% *after* having been below −5% for at least 7 consecutive days. Fallback: raw minimum of smoothed index if no inflection found.

```python
THRESHOLD = -5.0   # ROC above this = "stabilized"
MIN_DECLINE_DAYS = 7

def find_inflection(group):
    g = group.dropna(subset=["roc_14d"]).sort_values("days_since_release")
    if g.empty:
        return np.nan

    # Find stretches where ROC < threshold
    below = g["roc_14d"] < THRESHOLD
    # Require at least MIN_DECLINE_DAYS consecutive below-threshold rows
    streak = 0
    entered_decline = False
    for _, row in g.iterrows():
        if row["roc_14d"] < THRESHOLD:
            streak += 1
            if streak >= MIN_DECLINE_DAYS:
                entered_decline = True
        else:
            if entered_decline:
                return row["days_since_release"]
            streak = 0

    # Fallback: day of minimum smoothed index
    return g.loc[g["smoothed"].idxmin(), "days_since_release"]

inflections = (
    daily.groupby(["set_code", "set_name", "released_at", "rarity_name"])
    .apply(find_inflection, include_groups=False)
    .reset_index(name="inflection_day")
    .dropna(subset=["inflection_day"])
)
inflections["inflection_day"] = inflections["inflection_day"].astype(int)

print(inflections.groupby("rarity_name")["inflection_day"].describe().round(1))
```

- [ ] **Step 2: Verify sanity**

Run `inflections.groupby("rarity_name")["inflection_day"].median()` — expect values somewhere in the 20–90 day range. Mythics and rares should bottom later than commons/uncommons (more speculation driven). If all values cluster at 0 or 150, the threshold needs tuning.

---

### Task 7: Figure 1 — Average normalized price curve per rarity

**Files:**
- Modify: `notebooks/card_lowest_price_research.ipynb` (cell 8)

- [ ] **Step 1: Write Cell 8**

```python
RARITY_ORDER = ["mythic", "rare", "uncommon", "common"]
RARITY_COLORS = {"mythic": "#e07b39", "rare": "#c5a800", "uncommon": "#8fb5c2", "common": "#9e9e9e"}

fig, ax = plt.subplots(figsize=(12, 6))

for rarity in RARITY_ORDER:
    sub = daily[daily["rarity_name"] == rarity]
    # Aggregate across all sets: median + IQR per day
    agg = sub.groupby("days_since_release")["smoothed"].agg(
        median="median", p25=lambda x: x.quantile(0.25), p75=lambda x: x.quantile(0.75)
    )
    agg = agg[agg.index <= 150]
    color = RARITY_COLORS[rarity]
    ax.plot(agg.index, agg["median"], label=rarity.capitalize(), color=color, linewidth=2)
    ax.fill_between(agg.index, agg["p25"], agg["p75"], color=color, alpha=0.12)

ax.axhline(100, color="black", linestyle="--", linewidth=0.8, alpha=0.5)
ax.set_xlabel("Days since set release")
ax.set_ylabel("Price index (day-0 = 100)")
ax.set_title("Normalized price trajectory after set release\n(expansion sets 2021–2024, nonfoil, shaded = IQR)")
ax.legend()
ax.yaxis.set_major_formatter(mticker.PercentFormatter(xmax=100, decimals=0))
plt.tight_layout()
plt.savefig(DATA_DIR / "fig1_avg_price_curve.png", dpi=150)
plt.show()
```

---

### Task 8: Figure 2 — Single-set ROC example with inflection marked

**Files:**
- Modify: `notebooks/card_lowest_price_research.ipynb` (cell 9)

- [ ] **Step 1: Write Cell 9**

```python
EXAMPLE_SET = "blb"   # Bloomburrow — change to any set_code from the data

fig, ax1 = plt.subplots(figsize=(12, 5))
ax2 = ax1.twinx()

for rarity in RARITY_ORDER:
    sub = daily[(daily["set_code"] == EXAMPLE_SET) & (daily["rarity_name"] == rarity)].sort_values("days_since_release")
    if sub.empty:
        continue
    color = RARITY_COLORS[rarity]
    ax1.plot(sub["days_since_release"], sub["smoothed"], color=color, linewidth=2, label=rarity.capitalize())
    ax2.plot(sub["days_since_release"], sub["roc_14d"], color=color, linewidth=1, linestyle=":", alpha=0.6)

    infl = inflections[(inflections["set_code"] == EXAMPLE_SET) & (inflections["rarity_name"] == rarity)]
    if not infl.empty:
        day = infl["inflection_day"].values[0]
        ax1.axvline(day, color=color, linestyle="--", linewidth=1, alpha=0.7)

ax1.axhline(100, color="black", linestyle="--", linewidth=0.8, alpha=0.4)
ax2.axhline(-5, color="grey", linestyle=":", linewidth=0.8, alpha=0.6)
ax1.set_xlabel("Days since release")
ax1.set_ylabel("Price index (day-0 = 100)")
ax2.set_ylabel("14-day ROC (%)")
ax1.legend(loc="upper right")

set_name = daily[daily["set_code"] == EXAMPLE_SET]["set_name"].iloc[0]
ax1.set_title(f"{set_name} — price index + rate of change\n(dashed verticals = detected inflection day)")
plt.tight_layout()
plt.savefig(DATA_DIR / f"fig2_roc_{EXAMPLE_SET}.png", dpi=150)
plt.show()
```

---

### Task 9: Figure 3 — Inflection day distribution per rarity

**Files:**
- Modify: `notebooks/card_lowest_price_research.ipynb` (cell 10)

- [ ] **Step 1: Write Cell 10**

```python
fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharey=False)
axes = axes.flatten()

for i, rarity in enumerate(RARITY_ORDER):
    ax = axes[i]
    sub = inflections[inflections["rarity_name"] == rarity]["inflection_day"]
    if sub.empty:
        continue
    ax.hist(sub, bins=range(0, 155, 7), color=RARITY_COLORS[rarity], edgecolor="white", alpha=0.85)
    median_day = int(sub.median())
    ax.axvline(median_day, color="black", linestyle="--", linewidth=1.2)
    ax.set_title(f"{rarity.capitalize()}  (n={len(sub)}, median={median_day}d)")
    ax.set_xlabel("Inflection day")
    ax.set_ylabel("Number of sets")
    ax.set_xlim(0, 150)

fig.suptitle("Distribution of price bottom (inflection day) by rarity\nExpansion sets 2021–2024", fontsize=13)
plt.tight_layout()
plt.savefig(DATA_DIR / "fig3_inflection_distribution.png", dpi=150)
plt.show()
```

---

### Task 10: Summary table

**Files:**
- Modify: `notebooks/card_lowest_price_research.ipynb` (cell 11)

- [ ] **Step 1: Write Cell 11**

```python
summary = (
    inflections.groupby("rarity_name")["inflection_day"]
    .agg(
        sets="count",
        median="median",
        p25=lambda x: x.quantile(0.25),
        p75=lambda x: x.quantile(0.75),
        min="min",
        max="max",
    )
    .loc[RARITY_ORDER]
    .round(1)
)
summary.index.name = "Rarity"
summary.columns = ["Sets", "Median day", "25th pct", "75th pct", "Min", "Max"]
display(summary)

print("\nConclusion:")
for rarity in RARITY_ORDER:
    row = summary.loc[rarity]
    print(f"  {rarity.capitalize():10s} → prices bottom around day {int(row['Median day'])} "
          f"(IQR {int(row['25th pct'])}–{int(row['75th pct'])})")
```

---

## Notes

- **Password**: if `app_readonly` password is unknown, swap `user` in `DB_CONFIG` to `"automana_admin"` — the query is read-only.
- **REFRESH flag**: set `REFRESH = True` in Cell 0 to re-pull from DB (e.g., after new sets are ingested).
- **Threshold tuning**: the `THRESHOLD = -5.0` in Task 6 is a starting point. If inflection days cluster unnaturally at 0 or 150, try −3.0 or −8.0.
- **Rarity filter**: `special` and `bonus` rarities are excluded — too few cards per set for stable aggregation.
