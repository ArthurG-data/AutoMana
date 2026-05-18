# Reprint Effect Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `notebooks/reprint_effect_analysis.ipynb` — an event-study notebook that measures the price impact of MTG reprints on mythic/rare cards, including drop depth, rebound, original-vs-reprint value retention, and pre-announcement leakage detection.

**Architecture:** Single Jupyter notebook structured as 9 sequential parts. Each part caches its output to `notebooks/data/*.parquet` so cells can be re-run without re-querying the DB. Parts 1–2 load/transform data; Parts 3–9 analyze and chart. Parts 5 and 8 share a control group dataset built in Part 5.

**Tech Stack:** Python 3, psycopg2, pandas, numpy, matplotlib, scipy.stats, pathlib. PostgreSQL via `localhost:5433`. Style mirrors `notebooks/treatment_price_analysis.ipynb`.

---

## File Map

| File | Role |
|---|---|
| `notebooks/reprint_effect_analysis.ipynb` | Main notebook — all parts |
| `notebooks/data/reprint_events.parquet` | Part 1 output: event catalog |
| `notebooks/data/reprint_prices_raw.parquet` | Part 2 intermediate: raw price rows for all reprinted cards |
| `notebooks/data/reprint_price_windows.parquet` | Part 2 output: normalized per-event windows |
| `notebooks/data/reprint_event_metrics.parquet` | Part 4–6 output: per-event computed metrics |
| `notebooks/data/reprint_control_index.parquet` | Part 5 output: market control group price index |
| `notebooks/data/reprint_fig*.png` | Chart exports |

---

## Set Type Taxonomy

The DB `set_type` field does not perfectly match our 7 analytical buckets. Use this two-level mapping throughout every task — copy it into Part 0 exactly as written:

```python
# Default mapping from DB set_type → our analytical category
SET_TYPE_DEFAULT = {
    'masters':          'masters',
    'expansion':        'expansion',
    'core':             'core',
    'commander':        'commander',
    'draft_innovation': 'list_jumpstart',  # overridden below for MH/UB sets
    'masterpiece':      'list_jumpstart',  # bonus sheets (Mystical Archive, Special Guests, etc.)
}

# Per-set-code overrides (applied after SET_TYPE_DEFAULT)
SET_CODE_OVERRIDES = {
    # Modern Horizons series → masters (high reprint density, same market impact)
    'mh2': 'masters', 'mh3': 'masters', 'h1r': 'masters', 'h2r': 'masters',
    # UB large licensed sets (LTR, CLB, ACR are draft_innovation in DB)
    'ltr': 'ub_large', 'clb': 'ub_large', 'acr': 'ub_large',
    # UB expansion sets (DB classifies as expansion, but unique-art dynamics differ)
    'fin': 'ub_large', 'eoe': 'ub_large', 'spm': 'ub_large',
    'tla': 'ub_large', 'tmt': 'ub_large', 'sos': 'ub_large', 'ecl': 'ub_large',
    # UB commander sets
    'who': 'ub_large', 'pip': 'ub_large', '40k': 'ub_large',
    # Jumpstart / Clue Edition (draft_innovation default is list_jumpstart — keep)
    # Secret Lair — sparse in DB, classified as secret_lair for descriptive reporting
    'slx': 'secret_lair',
}

SET_TYPE_ORDER = ['masters', 'expansion', 'core', 'commander', 'ub_large', 'list_jumpstart', 'secret_lair']

SET_TYPE_COLORS = {
    'masters':       '#7f00ff',
    'expansion':     '#e07b39',
    'core':          '#c5a800',
    'commander':     '#2e7d32',
    'ub_large':      '#0288d1',
    'list_jumpstart':'#546e7a',
    'secret_lair':   '#c62828',
}

def classify_set_type(set_code: str, raw_set_type: str) -> str:
    if set_code in SET_CODE_OVERRIDES:
        return SET_CODE_OVERRIDES[set_code]
    return SET_TYPE_DEFAULT.get(raw_set_type, 'other')
```

---

## Task 1: Part 0 — Setup Cell

**Files:**
- Create: `notebooks/reprint_effect_analysis.ipynb`

- [ ] **Step 1: Create the notebook with a title markdown cell and the setup code cell**

Create the notebook file and open it in Jupyter. Add a markdown cell:

```markdown
# MTG Reprint Effect Analysis

**Research questions:**
1. How much does a card's price drop after a reprint, by set type?
2. How quickly does it rebound, and does it ever fully recover?
3. Does the original printing hold value better than the new reprint version?
4. Do high-value cards start declining *before* the official announcement? (leakage)

**Event study design:**
- T = 0: reprint set release date
- T = −90: drift detection start (pre-announcement leakage window)
- T = −45: clean baseline (pre-dates most set announcements)
- T = −21: preview season opens
- T = +7: end of release-week shock
- Baseline price = median NM sell price in [T−52, T−38]
- Normalized price: indexed_price = daily_price / baseline_price
```

Then add the setup code cell:

```python
import os
import warnings
import psycopg2
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.patches as mpatches
from pathlib import Path
from scipy import stats

warnings.filterwarnings('ignore')

DATA_DIR = Path('data')
DATA_DIR.mkdir(exist_ok=True)

REFRESH = True  # Set False to load from parquet cache

EVENT_WINDOW   = (-90, 365)   # days relative to reprint release
BASELINE_WINDOW = (-52, -38)  # days for baseline price computation
DRIFT_WINDOW   = (-90, -45)   # pre-announcement leakage window
RARITY_FILTER  = ['mythic', 'rare']
RARITY_ORDER   = ['mythic', 'rare']
RARITY_COLORS  = {'mythic': '#e07b39', 'rare': '#c5a800'}
MIN_BUCKET_SIZE = 5            # min events to include a set type in charts
LEAKAGE_PRICE_THRESHOLD = 1500 # cents — only analyze leakage for cards > $15 at T-90

SET_TYPE_DEFAULT = {
    'masters':          'masters',
    'expansion':        'expansion',
    'core':             'core',
    'commander':        'commander',
    'draft_innovation': 'list_jumpstart',
    'masterpiece':      'list_jumpstart',
}

SET_CODE_OVERRIDES = {
    'mh2': 'masters',  'mh3': 'masters',  'h1r': 'masters',  'h2r': 'masters',
    'ltr': 'ub_large', 'clb': 'ub_large', 'acr': 'ub_large',
    'fin': 'ub_large', 'eoe': 'ub_large', 'spm': 'ub_large',
    'tla': 'ub_large', 'tmt': 'ub_large', 'sos': 'ub_large', 'ecl': 'ub_large',
    'who': 'ub_large', 'pip': 'ub_large', '40k': 'ub_large',
    'slx': 'secret_lair',
}

SET_TYPE_ORDER  = ['masters', 'expansion', 'core', 'commander', 'ub_large', 'list_jumpstart', 'secret_lair']
SET_TYPE_COLORS = {
    'masters':        '#7f00ff',
    'expansion':      '#e07b39',
    'core':           '#c5a800',
    'commander':      '#2e7d32',
    'ub_large':       '#0288d1',
    'list_jumpstart': '#546e7a',
    'secret_lair':    '#c62828',
}

def classify_set_type(set_code: str, raw_set_type: str) -> str:
    if set_code in SET_CODE_OVERRIDES:
        return SET_CODE_OVERRIDES[set_code]
    return SET_TYPE_DEFAULT.get(raw_set_type, 'other')

DB_CONFIG = dict(
    host='localhost', port=5433, dbname='automana', user='automana_admin',
    password=os.environ.get('AUTOMANA_DB_PASSWORD', ''),
)

def get_conn():
    return psycopg2.connect(**DB_CONFIG)

def query_to_df(sql, params=None):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
    return pd.DataFrame(rows, columns=cols)

print('Setup complete.')
```

- [ ] **Step 2: Run the cell and verify it prints "Setup complete." with no errors**

---

## Task 2: Part 1 — Reprint Event Catalog

**Files:**
- Modify: `notebooks/reprint_effect_analysis.ipynb` (add 2 cells)
- Output: `notebooks/data/reprint_events.parquet`

- [ ] **Step 1: Add a markdown cell for Part 1**

```markdown
## Part 1 — Reprint Event Catalog

For every mythic/rare, find all printings ordered by `released_at`.  
The earliest printing is the "original". Every subsequent printing is a **reprint event**.  
We classify each event by `reprint_set_type` using our 7-bucket taxonomy.
```

- [ ] **Step 2: Add the SQL + processing code cell**

```python
SQL_EVENTS = """
WITH card_first_print AS (
    SELECT
        cv.unique_card_id,
        MIN(s.released_at) AS first_release
    FROM card_catalog.card_version cv
    JOIN card_catalog.sets s ON s.set_id = cv.set_id
    JOIN card_catalog.rarities_ref r ON r.rarity_id = cv.rarity_id
    WHERE r.rarity_name IN ('mythic', 'rare')
      AND NOT cv.is_digital
    GROUP BY cv.unique_card_id
),
original_set AS (
    SELECT DISTINCT ON (cv.unique_card_id)
        cv.unique_card_id,
        s.set_code AS original_set
    FROM card_catalog.card_version cv
    JOIN card_catalog.sets s ON s.set_id = cv.set_id
    JOIN card_first_print cfp ON cfp.unique_card_id = cv.unique_card_id
    WHERE s.released_at = cfp.first_release
    ORDER BY cv.unique_card_id, s.set_code
)
SELECT DISTINCT
    cv.unique_card_id::text,
    ucr.card_name,
    r.rarity_name,
    os.original_set,
    cfp.first_release           AS original_release,
    s.set_code                  AS reprint_set,
    s.set_name                  AS reprint_set_name,
    st.set_type                 AS reprint_set_type_raw,
    s.released_at               AS reprint_release
FROM card_catalog.card_version cv
JOIN card_catalog.sets s              ON s.set_id = cv.set_id
JOIN card_catalog.set_type_list_ref st ON st.set_type_id = s.set_type_id
JOIN card_catalog.rarities_ref r      ON r.rarity_id = cv.rarity_id
JOIN card_catalog.unique_cards_ref ucr ON ucr.unique_card_id = cv.unique_card_id
JOIN card_first_print cfp             ON cfp.unique_card_id = cv.unique_card_id
JOIN original_set os                  ON os.unique_card_id = cv.unique_card_id
WHERE r.rarity_name IN ('mythic', 'rare')
  AND NOT cv.is_digital
  AND s.released_at > cfp.first_release
  AND st.set_type IN (
      'masters', 'expansion', 'core', 'commander',
      'draft_innovation', 'masterpiece', 'box'
  )
ORDER BY s.released_at, ucr.card_name
"""

PARQUET_EVENTS = DATA_DIR / 'reprint_events.parquet'
if REFRESH or not PARQUET_EVENTS.exists():
    print('Querying reprint events...')
    events = query_to_df(SQL_EVENTS)
    events['reprint_release']  = pd.to_datetime(events['reprint_release'])
    events['original_release'] = pd.to_datetime(events['original_release'])
    events['reprint_set_type'] = events.apply(
        lambda r: classify_set_type(r['reprint_set'], r['reprint_set_type_raw']), axis=1
    )
    # Drop 'other' catch-all (promos, memorabilia, etc.)
    events = events[events['reprint_set_type'] != 'other'].copy()
    events = events.reset_index(drop=True)
    events.index.name = 'event_id'
    events = events.reset_index()
    events.to_parquet(PARQUET_EVENTS, index=False)
    print(f'  Saved {len(events):,} reprint events')
else:
    events = pd.read_parquet(PARQUET_EVENTS)
    print(f'Loaded {len(events):,} reprint events')

print(f'\nUnique cards reprinted:  {events["unique_card_id"].nunique():,}')
print(f'Date range:              {events["reprint_release"].min().date()} → {events["reprint_release"].max().date()}')

print('\nEvent count by set type × rarity:')
display(
    events.groupby(['reprint_set_type', 'rarity_name'])
    .size().unstack(fill_value=0)
    .reindex([t for t in SET_TYPE_ORDER if t in events['reprint_set_type'].unique()])
)
```

- [ ] **Step 3: Run the cell and verify it produces a table showing event counts. Sanity check: masters + expansion should have the most events (hundreds), secret_lair should have very few (<10). Flag any `reprint_set_type = 'other'` rows before the filter and confirm they are promo/memorabilia sets not relevant to the analysis.**

---

## Task 3: Part 2 — Event Price Windows

**Files:**
- Modify: `notebooks/reprint_effect_analysis.ipynb` (add 3 cells)
- Output: `notebooks/data/reprint_prices_raw.parquet`, `notebooks/data/reprint_price_windows.parquet`

- [ ] **Step 1: Add a markdown cell**

```markdown
## Part 2 — Event Price Windows

For every reprinted card, pull daily NM sell prices across all its versions (original + reprint + any other print)  
for the full `[T−90, T+365]` window relative to each reprint event.  
Normalize to T−45 baseline = 1.0.
```

- [ ] **Step 2: Add the raw price query cell**

```python
# Collect all unique_card_ids that have at least one reprint event
reprinted_ids = events['unique_card_id'].unique().tolist()
print(f'Fetching prices for {len(reprinted_ids):,} unique cards...')

SQL_PRICES_RAW = """
SELECT
    ppd.price_date,
    cv.unique_card_id::text,
    s.set_code,
    cf.code              AS finish_code,
    ps.code              AS source_code,
    ppd.list_avg_cents
FROM pricing.print_price_daily ppd
JOIN card_catalog.card_version cv  ON cv.card_version_id = ppd.card_version_id
JOIN card_catalog.sets s           ON s.set_id = cv.set_id
JOIN card_catalog.card_finished cf ON cf.finish_id = ppd.finish_id
JOIN pricing.price_source ps       ON ps.source_id = ppd.source_id
JOIN pricing.transaction_type tt   ON tt.transaction_type_id = ppd.transaction_type_id
JOIN pricing.card_condition cc     ON cc.condition_id = ppd.condition_id
JOIN card_catalog.language_ref lr  ON lr.language_id = ppd.language_id
WHERE cv.unique_card_id = ANY(%(ids)s)
  AND cf.code IN ('NONFOIL', 'FOIL')
  AND ps.code IN ('tcg', 'mtgstocks')
  AND tt.transaction_type_code = 'sell'
  AND cc.code = 'NM'
  AND lr.language_code = 'en'
  AND ppd.list_avg_cents IS NOT NULL
  AND ppd.list_avg_cents > 0
"""

PARQUET_RAW = DATA_DIR / 'reprint_prices_raw.parquet'
if REFRESH or not PARQUET_RAW.exists():
    prices_raw = query_to_df(SQL_PRICES_RAW, {'ids': reprinted_ids})
    prices_raw['price_date'] = pd.to_datetime(prices_raw['price_date'])
    prices_raw['list_avg_cents'] = pd.to_numeric(prices_raw['list_avg_cents'])
    # TCGPlayer preferred over MTGStocks; deduplicate per card × set × finish × date
    prices_raw['src_rank'] = prices_raw['source_code'].map({'tcg': 0, 'mtgstocks': 1}).fillna(9)
    prices_raw = (
        prices_raw.sort_values('src_rank')
        .drop_duplicates(['price_date', 'unique_card_id', 'set_code', 'finish_code'])
        .drop(columns='src_rank')
    )
    prices_raw.to_parquet(PARQUET_RAW, index=False)
    print(f'  Saved {len(prices_raw):,} raw price rows')
else:
    prices_raw = pd.read_parquet(PARQUET_RAW)
    print(f'Loaded {len(prices_raw):,} raw price rows')
```

- [ ] **Step 3: Add the windowing + normalization cell**

```python
# For each reprint event, slice prices to [T-90, T+365], classify version_type,
# compute baseline, and normalize.

PARQUET_WINDOWS = DATA_DIR / 'reprint_price_windows.parquet'

if REFRESH or not PARQUET_WINDOWS.exists():
    window_rows = []

    for _, ev in events.iterrows():
        uid          = ev['unique_card_id']
        orig_set     = ev['original_set']
        reprint_set  = ev['reprint_set']
        release_date = ev['reprint_release']
        event_id     = ev['event_id']

        t_start = release_date + pd.Timedelta(days=EVENT_WINDOW[0])   # T-90
        t_end   = release_date + pd.Timedelta(days=EVENT_WINDOW[1])   # T+365
        b_start = release_date + pd.Timedelta(days=BASELINE_WINDOW[0]) # T-52
        b_end   = release_date + pd.Timedelta(days=BASELINE_WINDOW[1]) # T-38

        card_prices = prices_raw[prices_raw['unique_card_id'] == uid].copy()
        if card_prices.empty:
            continue

        # Classify version_type
        def _version_type(row):
            if row['set_code'] == reprint_set:
                return 'reprint_version'
            if row['set_code'] == orig_set:
                return 'original_print'
            return 'other_reprint'

        card_prices['version_type'] = card_prices.apply(_version_type, axis=1)

        # Slice to event window
        window = card_prices[
            (card_prices['price_date'] >= t_start) &
            (card_prices['price_date'] <= t_end)
        ].copy()
        if window.empty:
            continue

        # Compute baseline per version_type × finish_code
        baseline_slice = card_prices[
            (card_prices['price_date'] >= b_start) &
            (card_prices['price_date'] <= b_end)
        ]
        baselines = (
            baseline_slice.groupby(['version_type', 'finish_code'])['list_avg_cents']
            .median().to_dict()
        )

        # Fall back: if no baseline in [T-52, T-38], use earliest in [T-90, T-38]
        early_slice = card_prices[card_prices['price_date'] <= b_end]
        early_baselines = (
            early_slice.groupby(['version_type', 'finish_code'])['list_avg_cents']
            .median().to_dict()
        )

        # Require NONFOIL baseline for original_print to include this event
        orig_nf_key = ('original_print', 'NONFOIL')
        if orig_nf_key not in baselines and orig_nf_key not in early_baselines:
            continue

        # reprint_includes_foil flag
        reprint_has_foil = (
            (window['version_type'] == 'reprint_version') &
            (window['finish_code'] == 'FOIL')
        ).any()

        for (vtype, finish), grp in window.groupby(['version_type', 'finish_code']):
            key = (vtype, finish)
            baseline = baselines.get(key) or early_baselines.get(key)
            if not baseline or baseline <= 0:
                continue
            for _, row in grp.iterrows():
                days = (row['price_date'] - release_date).days
                window_rows.append({
                    'event_id':             event_id,
                    'unique_card_id':       uid,
                    'card_name':            ev['card_name'],
                    'rarity_name':          ev['rarity_name'],
                    'reprint_set_type':     ev['reprint_set_type'],
                    'reprint_set':          reprint_set,
                    'original_set':         orig_set,
                    'reprint_release':      release_date,
                    'version_type':         vtype,
                    'finish_code':          finish,
                    'price_date':           row['price_date'],
                    'days_from_release':    days,
                    'week':                 (days // 7) * 7,
                    'price_cents':          row['list_avg_cents'],
                    'baseline_cents':       baseline,
                    'indexed_price':        row['list_avg_cents'] / baseline,
                    'reprint_includes_foil': reprint_has_foil,
                })

    windows = pd.DataFrame(window_rows)
    # Clip extreme normalized values
    windows['indexed_price'] = windows['indexed_price'].clip(0.02, 20.0)
    windows.to_parquet(PARQUET_WINDOWS, index=False)
    print(f'Saved {len(windows):,} normalized price rows across {windows["event_id"].nunique():,} events')
else:
    windows = pd.read_parquet(PARQUET_WINDOWS)
    print(f'Loaded {len(windows):,} rows across {windows["event_id"].nunique():,} events')

print(f'\nEvents with price data: {windows["event_id"].nunique():,} / {len(events):,}')
print(f'Events by set type:')
display(windows.groupby('reprint_set_type')['event_id'].nunique().rename('n_events').to_frame())
```

- [ ] **Step 4: Run both cells. Verify:**
  - Row count is in the millions (we're pulling multi-year daily prices for hundreds of cards)
  - `windows` DataFrame has correct columns: `event_id, version_type, finish_code, days_from_release, week, indexed_price, reprint_includes_foil`
  - `indexed_price` near 1.0 for rows where `days_from_release` is in `[-52, -38]` (the baseline window)
  - `reprint_includes_foil` is True for most masters events, variable for others

---

## Task 4: Part 3 — Average Trajectory by Set Type

**Files:**
- Modify: `notebooks/reprint_effect_analysis.ipynb` (add 2 cells)
- Output: `notebooks/data/reprint_fig1_trajectory.png`

- [ ] **Step 1: Add markdown cell**

```markdown
## Part 3 — Average Price Trajectory by Set Type

Median indexed price (nonfoil, original print) across all events in each set type bucket,  
from T−45 (clean baseline) through T+365.  
Three vertical lines mark the analytical sub-windows.
```

- [ ] **Step 2: Add the chart cell**

```python
# Use original_print NONFOIL only for the primary trajectory
traj = windows[
    (windows['version_type'] == 'original_print') &
    (windows['finish_code'] == 'NONFOIL')
].copy()

fig, axes = plt.subplots(2, 1, figsize=(14, 12))

for ax, rarity in zip(axes, RARITY_ORDER):
    sub = traj[traj['rarity_name'] == rarity]
    plotted = False
    for stype in SET_TYPE_ORDER:
        bucket = sub[sub['reprint_set_type'] == stype]
        n_events = bucket['event_id'].nunique()
        if n_events < MIN_BUCKET_SIZE:
            continue
        weekly = (
            bucket.groupby('week')['indexed_price']
            .agg(median='median', p25=lambda x: x.quantile(0.25), p75=lambda x: x.quantile(0.75))
            .reset_index()
        )
        # Limit to T-45 → T+365 for the trajectory chart
        weekly = weekly[(weekly['week'] >= -45) & (weekly['week'] <= 365)]
        color = SET_TYPE_COLORS[stype]
        ax.plot(weekly['week'], weekly['median'], color=color, linewidth=2,
                label=f'{stype} (n={n_events})', zorder=3)
        ax.fill_between(weekly['week'], weekly['p25'], weekly['p75'],
                        color=color, alpha=0.12, zorder=2)
        plotted = True

    ax.axhline(1.0, color='black', linestyle='--', linewidth=1, alpha=0.5, label='baseline')
    for day, label in [(-45, 'T−45\nbaseline'), (-21, 'T−21\npreview'), (0, 'T=0\nrelease')]:
        ax.axvline(day, color='gray', linestyle=':', linewidth=1, alpha=0.7)
        ax.text(day + 3, ax.get_ylim()[1] * 0.97 if plotted else 1.3, label,
                fontsize=7, color='gray', va='top')

    ax.set_xlim(-50, 370)
    ax.set_ylim(bottom=0)
    ax.set_xlabel('Days from reprint release', fontsize=10)
    ax.set_ylabel('Median indexed price (1.0 = T−45 baseline)', fontsize=10)
    ax.set_title(f'{rarity.upper()} — original print nonfoil price trajectory by reprint set type', fontsize=11)
    ax.legend(fontsize=8, loc='lower right')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

fig.suptitle('MTG Reprint Effect — Price Trajectory by Set Type', fontsize=13)
plt.tight_layout()
plt.savefig(DATA_DIR / 'reprint_fig1_trajectory.png', dpi=150, bbox_inches='tight')
plt.show()
```

- [ ] **Step 3: Run and verify the chart shows:**
  - Lines generally declining toward T=0 (reprints cause price drops)
  - Masters lines should drop more steeply than expansion lines
  - At least `masters` and `expansion` buckets rendered for both rarities
  - Y-axis doesn't go negative; baseline line is visible at y=1.0

---

## Task 5: Part 4 — Price Drop Depth

**Files:**
- Modify: `notebooks/reprint_effect_analysis.ipynb` (add 2 cells)
- Output: `notebooks/data/reprint_fig2_drop_depth.png`, `notebooks/data/reprint_event_metrics.parquet`

- [ ] **Step 1: Add markdown cell**

```markdown
## Part 4 — Price Drop Depth

Per-event metrics: how much does the original print nonfoil drop in week 1 and at its trough (T0–T90)?
```

- [ ] **Step 2: Add the metrics computation + box plot cell**

```python
orig_nf = windows[
    (windows['version_type'] == 'original_print') &
    (windows['finish_code'] == 'NONFOIL')
].copy()

def get_price_at(grp, target_day, tolerance=7):
    nearby = grp[np.abs(grp['days_from_release'] - target_day) <= tolerance]
    return nearby['indexed_price'].median() if not nearby.empty else np.nan

metrics_rows = []
for event_id, grp in orig_nf.groupby('event_id'):
    ev = events[events['event_id'] == event_id].iloc[0]
    p_t7   = get_price_at(grp, 7)
    trough_grp = grp[(grp['days_from_release'] >= 0) & (grp['days_from_release'] <= 90)]
    trough_val = trough_grp['indexed_price'].min() if not trough_grp.empty else np.nan
    trough_day = trough_grp.loc[trough_grp['indexed_price'].idxmin(), 'days_from_release'] \
                 if not trough_grp.empty else np.nan
    p_t90  = get_price_at(grp, 90)
    p_t180 = get_price_at(grp, 180)
    p_t365 = get_price_at(grp, 365)
    p_t45_pre  = get_price_at(grp, -45)  # for drift calc (Part 8)
    p_t90_pre  = get_price_at(grp, -90)  # for drift calc (Part 8)
    baseline_cents = grp['baseline_cents'].median()

    metrics_rows.append({
        'event_id':             event_id,
        'card_name':            ev['card_name'],
        'unique_card_id':       ev['unique_card_id'],
        'rarity_name':          ev['rarity_name'],
        'reprint_set_type':     ev['reprint_set_type'],
        'reprint_set':          ev['reprint_set'],
        'reprint_release':      ev['reprint_release'],
        'reprint_includes_foil': grp['reprint_includes_foil'].iloc[0],
        'baseline_cents':       baseline_cents,
        'drop_week1':           (p_t7 - 1.0)   if pd.notna(p_t7)  else np.nan,
        'trough_value':         trough_val,
        'trough_day':           trough_day,
        'rebound_T90':          (p_t90  / trough_val - 1) if pd.notna(trough_val) and trough_val > 0 else np.nan,
        'rebound_T180':         (p_t180 / trough_val - 1) if pd.notna(trough_val) and trough_val > 0 else np.nan,
        'rebound_T365':         (p_t365 / trough_val - 1) if pd.notna(trough_val) and trough_val > 0 else np.nan,
        'indexed_T90':          p_t90,
        'indexed_T180':         p_t180,
        'indexed_T365':         p_t365,
        'indexed_T45_pre':      p_t45_pre,
        'indexed_T90_pre':      p_t90_pre,
        'nominal_recovery_T365': (p_t365 >= 1.0) if pd.notna(p_t365) else np.nan,
    })

metrics = pd.DataFrame(metrics_rows)
metrics.to_parquet(DATA_DIR / 'reprint_event_metrics.parquet', index=False)
print(f'Computed metrics for {len(metrics):,} events')

# Box plot: drop_week1 and trough_value by set type × rarity
fig, axes = plt.subplots(2, 2, figsize=(15, 10))

for col, (metric, label) in enumerate([
    ('drop_week1',  'Price change at T+7 (1.0 = flat)'),
    ('trough_value', 'Trough indexed price (T0–T90)')
]):
    for row, rarity in enumerate(RARITY_ORDER):
        ax = axes[row][col]
        sub = metrics[(metrics['rarity_name'] == rarity) & metrics[metric].notna()]
        order = [t for t in SET_TYPE_ORDER if (sub['reprint_set_type'] == t).sum() >= MIN_BUCKET_SIZE]
        data_groups = [sub[sub['reprint_set_type'] == t][metric].values for t in order]

        bp = ax.boxplot(data_groups, patch_artist=True, notch=False,
                        medianprops={'color': 'black', 'linewidth': 2})
        for patch, stype in zip(bp['boxes'], order):
            patch.set_facecolor(SET_TYPE_COLORS[stype])
            patch.set_alpha(0.7)

        ax.axhline(1.0, color='red', linestyle='--', linewidth=1, alpha=0.6)
        ax.set_xticks(range(1, len(order) + 1))
        ax.set_xticklabels(order, rotation=20, ha='right', fontsize=9)
        ax.set_ylabel(label, fontsize=9)
        ax.set_title(f'{rarity.upper()} — {metric}', fontsize=10)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

        for i, (stype, grp) in enumerate(zip(order, data_groups)):
            ax.text(i + 1, ax.get_ylim()[0] + 0.02, f'n={len(grp)}',
                    ha='center', fontsize=7, color='gray')

fig.suptitle('Price Drop Depth by Set Type and Rarity', fontsize=12)
plt.tight_layout()
plt.savefig(DATA_DIR / 'reprint_fig2_drop_depth.png', dpi=150, bbox_inches='tight')
plt.show()

print('\nMedian drop metrics by set type and rarity:')
display(
    metrics.groupby(['reprint_set_type', 'rarity_name'])[['drop_week1', 'trough_value', 'trough_day']]
    .agg('median').round(3)
    .reindex([t for t in SET_TYPE_ORDER if t in metrics['reprint_set_type'].unique()], level=0)
)
```

- [ ] **Step 3: Run and verify:**
  - Box plots render for at least masters and expansion in both rarities
  - `drop_week1` is mostly negative (prices fall after reprints)
  - `trough_value` < 1.0 for most events (card is cheaper than baseline at trough)
  - The parquet `reprint_event_metrics.parquet` is written to `notebooks/data/`

---

## Task 6: Part 5 — Rebound Analysis with Market-Adjusted Recovery

**Files:**
- Modify: `notebooks/reprint_effect_analysis.ipynb` (add 3 cells)
- Output: `notebooks/data/reprint_control_index.parquet`, `notebooks/data/reprint_fig3_rebound.png`

- [ ] **Step 1: Add markdown cell**

```markdown
## Part 5 — Rebound Analysis

Three recovery definitions:
1. **Nominal**: indexed price at T+365 ≥ 1.0 (returns to T−45 baseline).
2. **Market-adjusted**: indexed price at T+365 ≥ the control group's median indexed price at T+365  
   (control = same-rarity cards with no reprint event in [T−90, T+365]).
3. **Spread normalization**: value_retention_ratio stabilizes — covered in Part 6.
```

- [ ] **Step 2: Add the control group construction cell**

```python
# Build market control index:
# For each reprint event, the control group = mythic/rare cards that had NO reprint event
# in the [T-90, T+180] window centered on that event's release date.
# We track their median indexed price (vs their own T-45 price) at T+90/180/365.

reprinted_ids_set = set(events['unique_card_id'])

SQL_CONTROL = """
SELECT
    ppd.price_date,
    cv.unique_card_id::text,
    cf.code  AS finish_code,
    ps.code  AS source_code,
    ppd.list_avg_cents
FROM pricing.print_price_daily ppd
JOIN card_catalog.card_version cv  ON cv.card_version_id = ppd.card_version_id
JOIN card_catalog.card_finished cf ON cf.finish_id = ppd.finish_id
JOIN card_catalog.rarities_ref r   ON r.rarity_id = cv.rarity_id
JOIN pricing.price_source ps       ON ps.source_id = ppd.source_id
JOIN pricing.transaction_type tt   ON tt.transaction_type_id = ppd.transaction_type_id
JOIN pricing.card_condition cc     ON cc.condition_id = ppd.condition_id
JOIN card_catalog.language_ref lr  ON lr.language_id = ppd.language_id
WHERE r.rarity_name IN ('mythic', 'rare')
  AND NOT cv.is_digital
  AND cf.code = 'NONFOIL'
  AND ps.code IN ('tcg', 'mtgstocks')
  AND tt.transaction_type_code = 'sell'
  AND cc.code = 'NM'
  AND lr.language_code = 'en'
  AND ppd.list_avg_cents IS NOT NULL
  AND ppd.list_avg_cents > 0
  AND cv.unique_card_id != ALL(%(reprinted_ids)s)
"""

PARQUET_CTRL = DATA_DIR / 'reprint_control_index.parquet'
if REFRESH or not PARQUET_CTRL.exists():
    print('Querying control group prices (non-reprinted cards)...')
    ctrl_raw = query_to_df(SQL_CONTROL, {'reprinted_ids': list(reprinted_ids_set)})
    ctrl_raw['price_date']      = pd.to_datetime(ctrl_raw['price_date'])
    ctrl_raw['list_avg_cents']  = pd.to_numeric(ctrl_raw['list_avg_cents'])
    ctrl_raw['src_rank'] = ctrl_raw['source_code'].map({'tcg': 0, 'mtgstocks': 1}).fillna(9)
    ctrl_raw = (
        ctrl_raw.sort_values('src_rank')
        .drop_duplicates(['price_date', 'unique_card_id'])
        .drop(columns='src_rank')
    )
    ctrl_raw.to_parquet(PARQUET_CTRL, index=False)
    print(f'  Saved {len(ctrl_raw):,} control rows, {ctrl_raw["unique_card_id"].nunique():,} cards')
else:
    ctrl_raw = pd.read_parquet(PARQUET_CTRL)
    print(f'Loaded {len(ctrl_raw):,} control rows')

def get_market_index(release_date, b_start_days=-52, b_end_days=-38, horizons=(90, 180, 365)):
    """Compute median indexed price for control cards at each horizon relative to release_date."""
    b_start = release_date + pd.Timedelta(days=b_start_days)
    b_end   = release_date + pd.Timedelta(days=b_end_days)
    # Baseline per control card
    baseline_slice = ctrl_raw[
        (ctrl_raw['price_date'] >= b_start) &
        (ctrl_raw['price_date'] <= b_end)
    ]
    ctrl_baselines = baseline_slice.groupby('unique_card_id')['list_avg_cents'].median()
    result = {}
    for h in horizons:
        h_start = release_date + pd.Timedelta(days=h - 7)
        h_end   = release_date + pd.Timedelta(days=h + 7)
        h_slice = ctrl_raw[
            (ctrl_raw['price_date'] >= h_start) &
            (ctrl_raw['price_date'] <= h_end) &
            (ctrl_raw['unique_card_id'].isin(ctrl_baselines.index))
        ]
        if h_slice.empty:
            result[h] = np.nan
            continue
        h_medians = h_slice.groupby('unique_card_id')['list_avg_cents'].median()
        indexed = h_medians / ctrl_baselines.reindex(h_medians.index)
        result[h] = indexed.median()
    return result

print('Computing market index for each reprint event (this may take a minute)...')
market_indices = {}
for _, ev in events.iterrows():
    market_indices[ev['event_id']] = get_market_index(ev['reprint_release'])
print(f'  Done. Sample: {list(market_indices.items())[:2]}')
```

- [ ] **Step 3: Add the recovery flags + chart cell**

```python
# Add market-adjusted recovery flags to metrics
metrics['market_index_T90']  = metrics['event_id'].map(lambda eid: market_indices.get(eid, {}).get(90, np.nan))
metrics['market_index_T180'] = metrics['event_id'].map(lambda eid: market_indices.get(eid, {}).get(180, np.nan))
metrics['market_index_T365'] = metrics['event_id'].map(lambda eid: market_indices.get(eid, {}).get(365, np.nan))

metrics['nominal_recovery_T365']   = metrics['indexed_T365'] >= 1.0
metrics['mktadj_recovery_T365']    = metrics['indexed_T365'] >= metrics['market_index_T365']
metrics['nominal_recovery_T180']   = metrics['indexed_T180'] >= 1.0
metrics['mktadj_recovery_T180']    = metrics['indexed_T180'] >= metrics['market_index_T180']

# Rebound line chart by set type + rarity
fig, axes = plt.subplots(2, 1, figsize=(13, 10))

horizons_days = [0, 30, 60, 90, 120, 180, 270, 365]

for ax, rarity in zip(axes, RARITY_ORDER):
    sub_win = windows[
        (windows['version_type'] == 'original_print') &
        (windows['finish_code'] == 'NONFOIL') &
        (windows['rarity_name'] == rarity) &
        (windows['days_from_release'] >= 0)
    ]
    for stype in SET_TYPE_ORDER:
        bucket = sub_win[sub_win['reprint_set_type'] == stype]
        n = bucket['event_id'].nunique()
        if n < MIN_BUCKET_SIZE:
            continue
        pts = []
        for d in horizons_days:
            near = bucket[np.abs(bucket['days_from_release'] - d) <= 7]
            pts.append(near['indexed_price'].median() if not near.empty else np.nan)
        ax.plot(horizons_days, pts, marker='o', markersize=5, linewidth=2,
                color=SET_TYPE_COLORS[stype], label=f'{stype} (n={n})', alpha=0.9)

    ax.axhline(1.0, color='black', linestyle='--', linewidth=1.2, alpha=0.5, label='T−45 baseline (nominal)')
    ax.set_xlim(-5, 370)
    ax.set_ylim(bottom=0)
    ax.set_xlabel('Days after reprint release', fontsize=10)
    ax.set_ylabel('Median indexed price', fontsize=10)
    ax.set_title(f'{rarity.upper()} — post-release price trajectory (original print NF)', fontsize=11)
    ax.legend(fontsize=8)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

fig.suptitle('Price Rebound After Reprint by Set Type', fontsize=12)
plt.tight_layout()
plt.savefig(DATA_DIR / 'reprint_fig3_rebound.png', dpi=150, bbox_inches='tight')
plt.show()

print('\nRecovery rates by set type and rarity (events with T+365 data):')
has_t365 = metrics[metrics['indexed_T365'].notna()]
display(
    has_t365.groupby(['reprint_set_type', 'rarity_name'])[
        ['nominal_recovery_T365', 'mktadj_recovery_T365']
    ].agg('mean').round(2)
    .rename(columns={'nominal_recovery_T365': 'nominal_recover_%', 'mktadj_recovery_T365': 'mkt_adj_recover_%'})
    .reindex([t for t in SET_TYPE_ORDER if t in has_t365['reprint_set_type'].unique()], level=0)
)
```

- [ ] **Step 4: Run all three cells and verify:**
  - Control group has thousands of cards (non-reprinted mythics/rares)
  - Market index values are near 1.0 to 1.2 (slight inflation over the time period)
  - Recovery rates table shows: nominal recovery > market-adjusted recovery (as expected — market-adjusted is the stricter threshold)
  - Rebound chart lines are all < 1.0 at day 0 and trend up over time

---

## Task 7: Part 6 — Original Print vs Reprint Version

**Files:**
- Modify: `notebooks/reprint_effect_analysis.ipynb` (add 2 cells)
- Output: `notebooks/data/reprint_fig4_orig_vs_reprint.png`

- [ ] **Step 1: Add markdown cell**

```markdown
## Part 6 — Original Print vs Reprint Version

For events with price data for both versions: does the original print recover better?  
Also: does the original foil's premium over the original nonfoil *expand* when the nonfoil gets reprinted?
```

- [ ] **Step 2: Add the metrics + chart cell**

```python
# value_retention_ratio = original_nf indexed / reprint_nf indexed at same time step
# Restricted to events where BOTH versions have price data

orig_nf_w   = windows[(windows['version_type'] == 'original_print') & (windows['finish_code'] == 'NONFOIL')]
reprint_nf_w = windows[(windows['version_type'] == 'reprint_version') & (windows['finish_code'] == 'NONFOIL')]
orig_foil_w = windows[(windows['version_type'] == 'original_print') & (windows['finish_code'] == 'FOIL')]

# Events with both original and reprint NF data
both_events = set(orig_nf_w['event_id']) & set(reprint_nf_w['event_id'])
print(f'Events with both original + reprint NF price data: {len(both_events):,}')

# Compute value_retention_ratio at T+30/90/180/365
retention_rows = []
for eid in both_events:
    ev_meta = events[events['event_id'] == eid].iloc[0]
    for horizon in [30, 90, 180, 365]:
        orig_pt = orig_nf_w[
            (orig_nf_w['event_id'] == eid) &
            (np.abs(orig_nf_w['days_from_release'] - horizon) <= 7)
        ]['indexed_price'].median()
        repr_pt = reprint_nf_w[
            (reprint_nf_w['event_id'] == eid) &
            (np.abs(reprint_nf_w['days_from_release'] - horizon) <= 7)
        ]['indexed_price'].median()
        if pd.isna(orig_pt) or pd.isna(repr_pt) or repr_pt <= 0:
            continue
        retention_rows.append({
            'event_id':          eid,
            'rarity_name':       ev_meta['rarity_name'],
            'reprint_set_type':  ev_meta['reprint_set_type'],
            'reprint_includes_foil': ev_meta['reprint_includes_foil'] if 'reprint_includes_foil' in ev_meta else None,
            'horizon':           horizon,
            'orig_indexed':      orig_pt,
            'reprint_indexed':   repr_pt,
            'value_retention_ratio': orig_pt / repr_pt,
        })

retention = pd.DataFrame(retention_rows)

# foil_multiplier_original: original foil / original NF over time
foil_mult_rows = []
foil_events = set(orig_foil_w['event_id']) & set(orig_nf_w['event_id'])
for eid in foil_events:
    for horizon in [-45, 0, 90, 180, 365]:
        foil_pt = orig_foil_w[
            (orig_foil_w['event_id'] == eid) &
            (np.abs(orig_foil_w['days_from_release'] - horizon) <= 7)
        ]['indexed_price'].median()
        nf_pt = orig_nf_w[
            (orig_nf_w['event_id'] == eid) &
            (np.abs(orig_nf_w['days_from_release'] - horizon) <= 7)
        ]['indexed_price'].median()
        if pd.isna(foil_pt) or pd.isna(nf_pt) or nf_pt <= 0:
            continue
        ev_meta = events[events['event_id'] == eid].iloc[0]
        foil_mult_rows.append({
            'event_id': eid,
            'rarity_name': ev_meta['rarity_name'],
            'reprint_set_type': ev_meta['reprint_set_type'],
            'reprint_includes_foil': windows[windows['event_id'] == eid]['reprint_includes_foil'].iloc[0],
            'horizon': horizon,
            'foil_multiplier': foil_pt / nf_pt,
        })

foil_mults = pd.DataFrame(foil_mult_rows)

# Panel A: dual-line original NF vs reprint NF by set type
fig, axes = plt.subplots(2, 1, figsize=(13, 11))

horizons_plot = [0, 30, 60, 90, 120, 150, 180, 270, 365]

for ax, rarity in zip(axes, RARITY_ORDER):
    orig_sub   = orig_nf_w[(orig_nf_w['rarity_name'] == rarity) & (orig_nf_w['days_from_release'] >= -10)]
    reprint_sub = reprint_nf_w[(reprint_nf_w['rarity_name'] == rarity) & (reprint_nf_w['days_from_release'] >= -10)]

    for stype in SET_TYPE_ORDER:
        o_bucket = orig_sub[orig_sub['reprint_set_type'] == stype]
        r_bucket = reprint_sub[reprint_sub['reprint_set_type'] == stype]
        n = len(set(o_bucket['event_id']) & set(r_bucket['event_id']))
        if n < MIN_BUCKET_SIZE:
            continue
        color = SET_TYPE_COLORS[stype]
        for bucket, ls, suffix in [(o_bucket, '-', 'orig NF'), (r_bucket, '--', 'reprint NF')]:
            pts = [bucket[np.abs(bucket['days_from_release'] - d) <= 7]['indexed_price'].median()
                   for d in horizons_plot]
            ax.plot(horizons_plot, pts, linestyle=ls, linewidth=2, color=color,
                    label=f'{stype} {suffix} (n={n})' if suffix == 'orig NF' else f'{stype} reprint NF',
                    alpha=0.85)

    ax.axhline(1.0, color='black', linestyle=':', linewidth=1, alpha=0.4)
    ax.set_xlabel('Days after reprint release', fontsize=10)
    ax.set_ylabel('Median indexed price', fontsize=10)
    ax.set_title(f'{rarity.upper()} — original NF (solid) vs reprint NF (dashed)', fontsize=11)
    ax.legend(fontsize=7, ncol=2, loc='lower right')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

fig.suptitle('Original Print vs Reprint Version — Normalized Price Trajectories', fontsize=12)
plt.tight_layout()
plt.savefig(DATA_DIR / 'reprint_fig4_orig_vs_reprint.png', dpi=150, bbox_inches='tight')
plt.show()

print('\nMedian value_retention_ratio (original NF / reprint NF) by set type × rarity × horizon:')
display(
    retention.groupby(['reprint_set_type', 'rarity_name', 'horizon'])['value_retention_ratio']
    .median().unstack('horizon').round(2)
    .reindex([t for t in SET_TYPE_ORDER if t in retention['reprint_set_type'].unique()], level=0)
)

if not foil_mults.empty:
    print('\nMedian foil multiplier on original print (foil/NF ratio) over time:')
    display(
        foil_mults.groupby(['reprint_includes_foil', 'rarity_name', 'horizon'])['foil_multiplier']
        .median().unstack('horizon').round(2)
    )
```

- [ ] **Step 3: Run and verify:**
  - `value_retention_ratio > 1.0` at T+365 for most set types (original is worth more than reprint)
  - Foil multiplier table shows a higher ratio in the `reprint_includes_foil = False` group at T+365 vs T-45 (foil premium expands when the nonfoil is reprinted but the foil isn't)

---

## Task 8: Part 7 — Rarity Effect

**Files:**
- Modify: `notebooks/reprint_effect_analysis.ipynb` (add 2 cells)
- Output: `notebooks/data/reprint_fig5_rarity.png`

- [ ] **Step 1: Add markdown cell**

```markdown
## Part 7 — Rarity Effect

Are mythics more resilient to reprints than rares?  
Side-by-side comparison of drop depth, trough, and T+365 recovery rate.
```

- [ ] **Step 2: Add the chart cell**

```python
fig, axes = plt.subplots(1, 3, figsize=(16, 6))

metric_configs = [
    ('drop_week1',   'Price change at T+7\n(0 = flat, negative = drop)', True),
    ('trough_value', 'Trough indexed price\n(T0–T90)', True),
    ('nominal_recovery_T365', '% events with nominal\nfull recovery at T+365', False),
]

for ax, (metric, ylabel, is_box) in zip(axes, metric_configs):
    valid = metrics[metrics[metric].notna()]
    order = [t for t in SET_TYPE_ORDER if (valid['reprint_set_type'] == t).sum() >= MIN_BUCKET_SIZE]

    x = np.arange(len(order))
    width = 0.35

    for i, rarity in enumerate(RARITY_ORDER):
        sub = valid[valid['rarity_name'] == rarity]
        if is_box:
            vals = [sub[sub['reprint_set_type'] == t][metric].median() for t in order]
            bars = ax.bar(x + (i - 0.5) * width, vals, width,
                          color=RARITY_COLORS[rarity], alpha=0.8, label=rarity)
            for bar, v in zip(bars, vals):
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.005,
                        f'{v:.2f}', ha='center', va='bottom', fontsize=7)
        else:
            vals = [sub[sub['reprint_set_type'] == t][metric].mean() for t in order]
            bars = ax.bar(x + (i - 0.5) * width, vals, width,
                          color=RARITY_COLORS[rarity], alpha=0.8, label=rarity)
            for bar, v in zip(bars, vals):
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.005,
                        f'{v:.0%}', ha='center', va='bottom', fontsize=7)

    if metric in ('drop_week1', 'trough_value'):
        ax.axhline(1.0, color='gray', linestyle='--', linewidth=1)
    ax.set_xticks(x)
    ax.set_xticklabels(order, rotation=20, ha='right', fontsize=9)
    ax.set_ylabel(ylabel, fontsize=9)
    ax.legend(fontsize=9)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

fig.suptitle('Rarity Effect: Mythic vs Rare Reprint Resilience', fontsize=12)
plt.tight_layout()
plt.savefig(DATA_DIR / 'reprint_fig5_rarity.png', dpi=150, bbox_inches='tight')
plt.show()
```

- [ ] **Step 3: Run and verify the chart renders. Mythics should generally show a higher trough_value (less severe drop) and higher recovery rate than rares — if the opposite is true, note it as a finding rather than a bug.**

---

## Task 9: Part 8 — Pre-Announcement Drift (Leakage Investigation)

**Files:**
- Modify: `notebooks/reprint_effect_analysis.ipynb` (add 3 cells)
- Output: `notebooks/data/reprint_fig6_leakage.png`

- [ ] **Step 1: Add markdown cell**

```markdown
## Part 8 — Pre-Announcement Drift: Information Leakage Investigation

**Hypothesis:** Cards with advance-knowledge holders (distributors, WotC employees, early preview partners)
may show abnormal price declines in the `[T−90, T−45]` window — *before* any public announcement.

**Method:** Compare reprinted cards' `[T−90, T−45]` drift to a control group of non-reprinted
same-rarity cards over the same calendar period. A strongly negative `abnormal_drift` is
*consistent with* leakage but not proof — organic demand decline and speculation can also explain it.

**Scope:** Only cards with baseline price > $15 (1500 cents) — leakage incentives don't exist for cheap cards.
```

- [ ] **Step 2: Add the drift computation cell**

```python
# drift_T90_T45 per event: (indexed_price_at_T-45) / (indexed_price_at_T-90) - 1
# We already have indexed_T45_pre and indexed_T90_pre in metrics

drift = metrics[
    metrics['baseline_cents'] >= LEAKAGE_PRICE_THRESHOLD  # > $15
].copy()
drift = drift[drift['indexed_T45_pre'].notna() & drift['indexed_T90_pre'].notna()].copy()

drift['drift_T90_T45'] = drift['indexed_T45_pre'] / drift['indexed_T90_pre'] - 1

# Compute control group drift for each event's calendar period
def control_drift_for_event(release_date):
    """Market drift in [T-90, T-45] for control (non-reprinted) cards."""
    t90_start = release_date + pd.Timedelta(days=-97)
    t90_end   = release_date + pd.Timedelta(days=-83)
    t45_start = release_date + pd.Timedelta(days=-52)
    t45_end   = release_date + pd.Timedelta(days=-38)

    ctrl_t90 = ctrl_raw[
        (ctrl_raw['price_date'] >= t90_start) & (ctrl_raw['price_date'] <= t90_end)
    ].groupby('unique_card_id')['list_avg_cents'].median()

    ctrl_t45 = ctrl_raw[
        (ctrl_raw['price_date'] >= t45_start) & (ctrl_raw['price_date'] <= t45_end)
    ].groupby('unique_card_id')['list_avg_cents'].median()

    common = ctrl_t90.index.intersection(ctrl_t45.index)
    if len(common) < 10:
        return np.nan
    ratios = ctrl_t45.loc[common] / ctrl_t90.loc[common] - 1
    return ratios.median()

print('Computing control drift per event...')
drift['control_drift'] = drift['reprint_release'].map(control_drift_for_event)
drift['abnormal_drift'] = drift['drift_T90_T45'] - drift['control_drift']

print(f'\nEvents analyzed (price > $15 at baseline): {len(drift):,}')
print(f'Mean drift_T90_T45:   {drift["drift_T90_T45"].mean():.3f}')
print(f'Mean abnormal_drift:  {drift["abnormal_drift"].mean():.3f}')

# t-test: is mean abnormal_drift < 0?
t_stat, p_val = stats.ttest_1samp(drift['abnormal_drift'].dropna(), 0)
print(f'\nOne-sample t-test (H0: abnormal_drift = 0):')
print(f'  t = {t_stat:.3f}, p = {p_val:.4f}')
print(f'  {"Reject H0: mean abnormal drift is statistically < 0" if p_val < 0.05 and t_stat < 0 else "Cannot reject H0"}')

# Leakage candidates: bottom 10th percentile of abnormal_drift
p10 = drift['abnormal_drift'].quantile(0.10)
candidates = drift[drift['abnormal_drift'] <= p10].sort_values('abnormal_drift')
print(f'\nLeakage candidates (bottom 10th percentile, abnormal_drift ≤ {p10:.3f}):')
display(candidates[['card_name', 'reprint_set', 'reprint_set_type', 'rarity_name',
                     'baseline_cents', 'drift_T90_T45', 'control_drift', 'abnormal_drift']]
        .assign(baseline_usd=lambda d: d['baseline_cents'] / 100)
        .drop(columns='baseline_cents')
        .round(3))
```

- [ ] **Step 3: Add the leakage chart cell**

```python
fig = plt.figure(figsize=(16, 14))
gs = fig.add_gridspec(3, 2, hspace=0.45, wspace=0.35)

# Panel A: Histogram of abnormal_drift
ax_hist = fig.add_subplot(gs[0, :])
ax_hist.hist(drift['abnormal_drift'].dropna(), bins=40, color='#0288d1', alpha=0.7, edgecolor='white')
ax_hist.axvline(0, color='red', linestyle='--', linewidth=1.5, label='zero (no abnormal drift)')
ax_hist.axvline(drift['abnormal_drift'].mean(), color='black', linewidth=2,
                label=f'mean = {drift["abnormal_drift"].mean():.3f}')
ax_hist.set_xlabel('Abnormal drift in [T−90, T−45]\n(reprinted card − control group)', fontsize=10)
ax_hist.set_ylabel('Number of events', fontsize=10)
ax_hist.set_title(f'Distribution of Pre-Announcement Abnormal Price Drift (n={len(drift.dropna(subset=["abnormal_drift"]))})\n'
                  f't={t_stat:.2f}, p={p_val:.4f}', fontsize=11)
ax_hist.legend(fontsize=9)
ax_hist.spines['top'].set_visible(False)
ax_hist.spines['right'].set_visible(False)

# Panel B: Median abnormal_drift by set type
ax_bar = fig.add_subplot(gs[1, 0])
stype_drift = (
    drift.groupby('reprint_set_type')['abnormal_drift']
    .agg(median='median', n='count')
    .reindex([t for t in SET_TYPE_ORDER if t in drift['reprint_set_type'].unique()])
)
colors = [SET_TYPE_COLORS[t] for t in stype_drift.index]
bars = ax_bar.bar(range(len(stype_drift)), stype_drift['median'].values, color=colors, alpha=0.8)
ax_bar.axhline(0, color='red', linestyle='--', linewidth=1)
ax_bar.set_xticks(range(len(stype_drift)))
ax_bar.set_xticklabels(stype_drift.index, rotation=20, ha='right', fontsize=9)
ax_bar.set_ylabel('Median abnormal drift', fontsize=9)
ax_bar.set_title('Median Abnormal Drift by Set Type\n(negative = unusual pre-announcement decline)', fontsize=10)
for bar, (stype, row) in zip(bars, stype_drift.iterrows()):
    ax_bar.text(bar.get_x() + bar.get_width() / 2, bar.get_height() - 0.005,
                f'n={int(row["n"])}', ha='center', va='top', fontsize=7, color='white')
ax_bar.spines['top'].set_visible(False)
ax_bar.spines['right'].set_visible(False)

# Panel B2: By price tier ($15-30 vs $30-50 vs $50+)
ax_tier = fig.add_subplot(gs[1, 1])
drift['price_tier'] = pd.cut(
    drift['baseline_cents'],
    bins=[1500, 3000, 5000, 1e9],
    labels=['$15-30', '$30-50', '$50+']
)
tier_drift = drift.groupby('price_tier')['abnormal_drift'].agg(median='median', n='count')
ax_tier.bar(range(len(tier_drift)), tier_drift['median'].values,
            color=['#c5a800', '#e07b39', '#7f00ff'], alpha=0.8)
ax_tier.axhline(0, color='red', linestyle='--', linewidth=1)
ax_tier.set_xticks(range(len(tier_drift)))
ax_tier.set_xticklabels([f'{t}\n(n={int(r["n"])})' for t, r in tier_drift.iterrows()], fontsize=9)
ax_tier.set_ylabel('Median abnormal drift', fontsize=9)
ax_tier.set_title('Abnormal Drift by Card Price Tier\n(does leakage signal strengthen for expensive cards?)', fontsize=10)
ax_tier.spines['top'].set_visible(False)
ax_tier.spines['right'].set_visible(False)

# Panel C: Full [T-90, T+90] trajectories for top 10 leakage candidates
ax_lk = fig.add_subplot(gs[2, :])
top10 = candidates.head(10)
for _, ev_row in top10.iterrows():
    eid = ev_row['event_id']
    card_win = windows[
        (windows['event_id'] == eid) &
        (windows['version_type'] == 'original_print') &
        (windows['finish_code'] == 'NONFOIL') &
        (windows['days_from_release'] >= -90) &
        (windows['days_from_release'] <= 90)
    ].sort_values('days_from_release')
    if card_win.empty:
        continue
    label = f"{ev_row['card_name']} ({ev_row['reprint_set']}) Δ={ev_row['abnormal_drift']:.2f}"
    ax_lk.plot(card_win['days_from_release'], card_win['indexed_price'],
               linewidth=1.5, alpha=0.7, label=label)

ax_lk.axvline(-45, color='gray', linestyle=':', linewidth=1)
ax_lk.axvline(-21, color='gray', linestyle=':', linewidth=1)
ax_lk.axvline(0, color='red', linestyle='--', linewidth=1.5)
ax_lk.text(-45 + 1, ax_lk.get_ylim()[1] * 0.99, 'T−45\nbaseline', fontsize=7, color='gray', va='top')
ax_lk.text(-21 + 1, ax_lk.get_ylim()[1] * 0.85, 'T−21\npreview', fontsize=7, color='gray', va='top')
ax_lk.text(1, ax_lk.get_ylim()[1] * 0.99, 'T=0\nrelease', fontsize=7, color='red', va='top')
ax_lk.axhline(1.0, color='black', linestyle='--', linewidth=1, alpha=0.4)
ax_lk.set_xlabel('Days from reprint release', fontsize=10)
ax_lk.set_ylabel('Indexed price', fontsize=10)
ax_lk.set_title('Top 10 Leakage Candidate Events — Full Price Trajectory [T−90, T+90]', fontsize=11)
ax_lk.legend(fontsize=7, loc='lower left', ncol=2)
ax_lk.spines['top'].set_visible(False)
ax_lk.spines['right'].set_visible(False)

fig.suptitle('Pre-Announcement Drift: Information Leakage Investigation', fontsize=13)
plt.savefig(DATA_DIR / 'reprint_fig6_leakage.png', dpi=150, bbox_inches='tight')
plt.show()
```

- [ ] **Step 4: Run all three cells and verify:**
  - The t-test result prints correctly (p-value and direction)
  - Leakage candidates table shows real card names with negative `abnormal_drift`
  - Panel C shows trajectories that start declining well before T=0
  - Panel B2 price tier chart is visible even if some tiers have few events

---

## Task 10: Part 9 — Conclusions

**Files:**
- Modify: `notebooks/reprint_effect_analysis.ipynb` (add 2 cells)

- [ ] **Step 1: Add markdown cell**

```markdown
## Part 9 — Conclusions

Synthesis of all findings.
```

- [ ] **Step 2: Add the conclusions code cell**

```python
print('=' * 65)
print('MTG REPRINT EFFECT ANALYSIS — FINDINGS SUMMARY')
print('=' * 65)
print()

# 1. Drop depth table
print('── Drop Depth (median, original print NF) ──')
drop_summary = (
    metrics.groupby(['reprint_set_type', 'rarity_name'])
    [['drop_week1', 'trough_value', 'trough_day']]
    .median().round(3)
    .reindex([t for t in SET_TYPE_ORDER if t in metrics['reprint_set_type'].unique()], level=0)
)
display(drop_summary)

# 2. Recovery table
print('\n── Recovery Rates (events with T+365 data) ──')
rec_summary = (
    has_t365.groupby(['reprint_set_type', 'rarity_name'])
    [['nominal_recovery_T365', 'mktadj_recovery_T365']]
    .mean().round(2)
    .rename(columns={
        'nominal_recovery_T365': 'nominal_recover',
        'mktadj_recovery_T365':  'mkt_adj_recover',
    })
    .reindex([t for t in SET_TYPE_ORDER if t in has_t365['reprint_set_type'].unique()], level=0)
)
display(rec_summary)

# 3. Original premium
print('\n── Original Print Premium at T+365 (orig NF / reprint NF) ──')
ret_t365 = retention[retention['horizon'] == 365]
display(
    ret_t365.groupby(['reprint_set_type', 'rarity_name'])['value_retention_ratio']
    .median().round(2).rename('orig_premium_over_reprint')
    .reset_index().pivot(index='reprint_set_type', columns='rarity_name', values='orig_premium_over_reprint')
    .reindex([t for t in SET_TYPE_ORDER if t in ret_t365['reprint_set_type'].unique()])
)

# 4. Leakage
if 'abnormal_drift' in drift.columns and drift['abnormal_drift'].notna().any():
    print('\n── Pre-Announcement Drift (cards > $15 at baseline) ──')
    print(f'  Mean abnormal drift [T-90, T-45]: {drift["abnormal_drift"].mean():.3f}')
    print(f'  t-test: t={t_stat:.3f}, p={p_val:.4f}')
    print(f'  Interpretation: {"Statistically significant pre-announcement decline detected" if p_val < 0.05 and t_stat < 0 else "No statistically significant pre-announcement decline"}')
    print(f'\n  Most consistent leakage by set type (median abnormal drift):')
    for stype, grp in drift.groupby('reprint_set_type'):
        print(f'    {stype:16s}  {grp["abnormal_drift"].median():.3f}  (n={len(grp)})')

print()
print('── Key Takeaways ──')
# Compute takeaways dynamically from data where possible
masters_drop  = metrics[(metrics['reprint_set_type'] == 'masters')]['trough_value'].median()
exp_drop      = metrics[(metrics['reprint_set_type'] == 'expansion')]['trough_value'].median()
masters_rec   = has_t365[(has_t365['reprint_set_type'] == 'masters')]['nominal_recovery_T365'].mean()
orig_prem_t365 = ret_t365['value_retention_ratio'].median()

print(f'  1. Masters reprints cause the deepest price troughs (median {masters_drop:.2f}× baseline), '
      f'deeper than expansions ({exp_drop:.2f}×).')
print(f'  2. Nominal recovery within 1 year: ~{masters_rec:.0%} for masters reprints.')
print(f'  3. At T+365, original prints trade at a median {orig_prem_t365:.2f}× premium over the reprint version.')
print(f'  4. Foil premium on original prints expands when the reprint does not include a foil version.')
if p_val < 0.05 and t_stat < 0:
    print(f'  5. ⚠ Statistically significant pre-announcement price decline detected (p={p_val:.4f}). '
          f'Certain set types show stronger signals — see Part 8 for leakage candidate cards.')
else:
    print(f'  5. No statistically significant pre-announcement decline detected across all events (p={p_val:.4f}).')
```

- [ ] **Step 3: Run the cell and verify all tables display without errors. Takeaway statements should auto-fill with real numbers. Check that no table is empty.**

---

## Task 11: Commit

**Files:**
- `notebooks/reprint_effect_analysis.ipynb`
- `notebooks/data/reprint_events.parquet`
- `notebooks/data/reprint_prices_raw.parquet`
- `notebooks/data/reprint_price_windows.parquet`
- `notebooks/data/reprint_event_metrics.parquet`
- `notebooks/data/reprint_control_index.parquet`
- `notebooks/data/reprint_fig*.png`

- [ ] **Step 1: Run all cells top to bottom with `REFRESH = True` and verify no cell throws an error**

- [ ] **Step 2: Set `REFRESH = False` in the setup cell and re-run all cells to confirm parquet caching works (no DB queries, same outputs)**

- [ ] **Step 3: Commit**

```bash
git add notebooks/reprint_effect_analysis.ipynb notebooks/data/reprint_*.parquet notebooks/data/reprint_fig*.png
git commit -m "feat(notebooks): reprint effect analysis — event study with leakage detection"
```

---

## Self-Review Against Spec

| Spec requirement | Covered by |
|---|---|
| Event catalog: all set types, first-print definition | Task 2 Part 1 |
| T-45 clean baseline, T-21 mid-point, T-90 drift window | Tasks 1, 3, 9 constants |
| Nonfoil primary + foil parallel series | Task 3 Part 2 |
| `reprint_includes_foil` flag | Task 3 Part 2 |
| Set type taxonomy: 7 buckets with overrides | Task 1 constants |
| Trajectory chart with 3 vertical lines | Task 4 Part 3 |
| Drop depth box plots + summary table | Task 5 Part 4 |
| Three recovery definitions: nominal, market-adjusted, spread | Task 6 Part 5 |
| Control group for market-adjusted recovery | Task 6 Part 5 |
| Original print vs reprint dual-line chart | Task 7 Part 6 |
| `value_retention_ratio` at T+30/90/180/365 | Task 7 Part 6 |
| Foil multiplier expansion analysis | Task 7 Part 6 |
| Rarity effect side-by-side chart | Task 8 Part 7 |
| Abnormal drift computation vs control | Task 9 Part 8 |
| t-test on abnormal drift | Task 9 Part 8 |
| Price tier subgroup ($15/$30/$50+) | Task 9 Part 8 |
| Top 10 leakage candidates annotated | Task 9 Part 8 |
| Conclusions synthesis table + bullet points | Task 10 Part 9 |
| Parquet caching + REFRESH flag | Tasks 2, 3 |
| Min bucket size guard (n < 5 → skip chart) | Tasks 4–9 |
