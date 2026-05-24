# MTG Repeat-Sales Price Index — Design Spec

**Date:** 2026-05-24  
**Status:** Approved for implementation  
**Outputs:** `docs/domain/MTG_RSI_METHODOLOGY.md` + `notebooks/repeat_sales_index.ipynb`

---

## 1. Problem Statement

No repeat-sales price index exists for MTG singles. Standard collectible-asset methodology (Case-Shiller, Mei-Moses) has never been applied to this market. AutoMana has the data to build it: `pricing.print_price_daily` contains daily price observations per `card_version_id`, sourced from multiple platforms, stretching back years.

The index answers: **"If you held a representative basket of MTG cards, what return would you have earned?"** — the same question a real-estate investor asks of the S&P/Case-Shiller Home Price Index.

---

## 2. Scope of V1

| Dimension | Decision |
|---|---|
| Price signal | `list_avg_cents` (TCGPlayer market average, densest data) |
| Condition | NM only (`condition_id` where `code = 'NM'`) |
| Finish | Nonfoil only (`finish_id` where `code = 'NONFOIL'`) |
| Source | TCGPlayer (`source_id` where `code = 'tcg'`) |
| Card filter | Cards with `list_avg_cents ≥ 100` (≥ $1.00) in at least one observation |
| Temporal granularity | Weekly (ISO week, Monday anchor) |
| Methods built | A (chained geometric mean), B (BMN adjacent OLS), C (all-pairs WLS) |
| Base period | First week with ≥ 50 active cards, indexed to 100 |

---

## 3. Data Pipeline

### 3.1 Source Table

```sql
SELECT
    DATE_TRUNC('week', price_date)::DATE  AS price_week,
    card_version_id,
    AVG(list_avg_cents)                   AS list_avg_cents
FROM pricing.print_price_daily ppd
JOIN pricing.price_source      ps  USING (source_id)
JOIN pricing.card_condition    cc  ON cc.condition_id   = ppd.condition_id
JOIN card_catalog.card_finished cf  ON cf.finish_id     = ppd.finish_id
WHERE ps.code  = 'tcg'
  AND cc.code  = 'NM'
  AND cf.code  = 'NONFOIL'
  AND ppd.list_avg_cents IS NOT NULL
GROUP BY DATE_TRUNC('week', price_date), card_version_id
```

### 3.2 Filtering

After aggregation:
1. Drop rows where `list_avg_cents < 100` (< $1.00).
2. Drop cards with fewer than **2 distinct weeks** of observations (cannot form a pair).
3. Log-transform: `log_price = ln(list_avg_cents)`.

### 3.3 Output Schema

Each method produces a DataFrame with columns:

| Column | Type | Description |
|---|---|---|
| `price_week` | date | ISO week Monday |
| `index_value` | float | Index level (base = 100) |
| `n_cards` | int | Cards contributing to this period |
| `n_pairs` | int | Pairs used (B and C only) |
| `method` | str | `'A'`, `'B'`, or `'C'` |

---

## 4. Algorithm Designs

### Method A — Chained Geometric Mean

**Inputs:** weekly price panel `(price_week, card_version_id, log_price)`

**Steps:**
1. For each card, compute `delta_log = log_price(t) - log_price(t-1)` (week-over-week diff).
2. For each week `t`, compute `mean_delta = mean(delta_log)` across all cards active in both `t` and `t-1`.
3. Chain: `log_index(t) = log_index(t-1) + mean_delta`, with `log_index(base) = ln(100)`.
4. `index_value = exp(log_index)`.

**Edge cases:**
- Weeks with fewer than 10 active pairs → flag as low-confidence, include but annotate.
- Cards with a price jump > 10× in one week → exclude that pair (data artifact guard).

---

### Method B — BMN Adjacent-Pair OLS

**Inputs:** same weekly panel.

**Steps:**
1. Build adjacent pairs: for each card, pair week `t` with week `t-1` whenever both exist.
2. Assign integer week index `k` (0 = base week).
3. Build sparse design matrix `X` of shape `(n_pairs, n_weeks - 1)`:
   - Row for pair `(t-1, t)`: `+1` in column `t-1`, `-1` in column `t-2` (skip column 0).
   - Wait — correction: columns represent weeks 1..T (week 0 is the base = 0 by definition).
   - Row for pair going from week `k-1` to week `k`: `+1` at column index `k-1`, `-1` at column index `k-2` if `k-1 > 0` else no entry.
4. Solve: `β = lstsq(X, y)` where `y = delta_log` vector.
5. `log_index = [0] + β.tolist()` → `index_value = 100 * exp(log_index)`.

**Implementation note:** Use `scipy.sparse.lil_matrix` → `csr_matrix` for the design matrix; `scipy.sparse.linalg.lsqr` for the solve. Avoids dense matrix allocation at scale.

**Edge cases:**
- Same pair outlier guard as Method A (>10× jump excluded).
- Weeks with no pairs: β for that week interpolated linearly (annotated gap).

---

### Method C — All-Pairs WLS with Case-Shiller Variance Correction

**Inputs:** same weekly panel.

**Steps:**
1. For each card with observations at weeks `{w_1, w_2, ..., w_n}`, generate all `n*(n-1)/2` pairs `(w_i, w_j)` with `i < j`.
2. For each pair: `delta_log = log_price(w_j) - log_price(w_i)`, `gap = w_j - w_i` (in weeks).
3. Weight: `w = 1 / gap²`.
4. Build sparse design matrix (same structure as B but with non-adjacent columns).
5. Solve WLS: `β = lsqr(X, y, damp=0)` with row weights applied as `X_w = diag(sqrt(w)) @ X`, `y_w = sqrt(w) * y`.
6. `index_value = 100 * exp([0] + β)`.

**Memory guard:** For cards with > 52 weekly observations (1 year), cap pair generation to adjacent + quarterly samples (weeks 0, 13, 26, 39, 52) to prevent pair explosion. Flag these cards.

---

## 5. Notebook Structure

```
notebooks/repeat_sales_index.ipynb
│
├── [MD]  Title + research context (links to MTG_RSI_METHODOLOGY.md)
├── [MD]  ## 0. Setup & Imports
├── [CODE] imports, DB config, constants
│
├── [MD]  ## 1. Data Extraction
├── [CODE] SQL query → DataFrame, shape/null checks
├── [CODE] Filtering ($1 floor, min weeks), log-transform
├── [CODE] Summary stats: n_cards, date range, avg observations per card
│
├── [MD]  ## 2. Method A — Chained Geometric Mean
├── [MD]  Explanation of method with formula
├── [CODE] Compute delta_log, weekly mean, chain
├── [CODE] Plot index_A
│
├── [MD]  ## 3. Method B — BMN Adjacent-Pair OLS
├── [MD]  Explanation with design matrix diagram
├── [CODE] Build pairs, sparse X matrix, lstsq solve
├── [CODE] Plot index_B overlay with index_A
│
├── [MD]  ## 4. Method C — All-Pairs WLS (Case-Shiller)
├── [MD]  Explanation with variance correction rationale
├── [CODE] Pair generation with memory guard, WLS solve
├── [CODE] Plot all three indices overlaid
│
├── [MD]  ## 5. Diagnostics
├── [CODE] n_cards and n_pairs per week (coverage chart)
├── [CODE] Residual distribution (B and C)
├── [CODE] Top 10 highest-weight cards per period
│
├── [MD]  ## 6. Sub-Indices (stretch)
├── [CODE] Run Method B segmented by rarity (C / U / R / M)
├── [CODE] 4-panel rarity index plot
│
└── [MD]  ## 7. Interpretation & Next Steps
```

---

## 6. Visualizations

| Plot | Description |
|---|---|
| **Main index** | Line chart, all 3 methods overlaid, log scale Y, weekly X |
| **Coverage** | Bar chart of n_cards per week (secondary axis on main index) |
| **Residuals** | Histogram of OLS residuals for B and C |
| **Rarity sub-indices** | 4-panel line chart (C / U / R / M, Method B) |

All plots use the existing notebook style: `figsize=(14, 6)`, `plt.style.use('seaborn-v0_8-whitegrid')`, prices in USD (divide cents by 100).

---

## 7. Files Created

| File | Description |
|---|---|
| `docs/domain/MTG_RSI_METHODOLOGY.md` | Full mathematical derivation of all 3 methods with MTG-specific context |
| `notebooks/repeat_sales_index.ipynb` | Notebook with all 3 methods implemented and visualized |
| `docs/superpowers/specs/2026-05-24-mtg-repeat-sales-index-design.md` | This file |

---

## 8. Out of Scope for V1

- Foil sub-index (sparse data — Phase 2)
- Multi-source index combining TCGPlayer + Cardmarket (currency harmonisation needed first)
- Rolling index with confidence intervals
- Publishing the index as an API endpoint
- Wishlist demand-signal correlation (requires accumulating wishlist snapshots first)

---

## 9. Dependencies

- Python packages: `pandas`, `numpy`, `scipy`, `matplotlib`, `psycopg2` — all available in `.venv`
- `statsmodels` not required (using `numpy.linalg.lstsq` and `scipy.sparse.linalg.lsqr`)
- DB: read-only access to `pricing.print_price_daily`, `pricing.price_source`, `pricing.card_condition`, `card_catalog.card_finished`, `card_catalog.card_version`, `card_catalog.unique_cards_ref`, `card_catalog.sets`
