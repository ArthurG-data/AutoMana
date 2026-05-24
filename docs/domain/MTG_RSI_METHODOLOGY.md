# MTG Repeat-Sales Price Index: Full Methodology

**Version:** 1.0 — 2026-05-24  
**Reference notebook:** `notebooks/repeat_sales_index.ipynb`  
**Reference spec:** `docs/superpowers/specs/2026-05-24-mtg-repeat-sales-index-design.md`  
**Related research:** `docs/domain/MTG_QUANT_RESEARCH.md`

---

## Background

A **repeat-sales price index** measures price change by tracking the same assets across multiple time periods, rather than sampling from all available assets at each point. The method was originally developed for real estate, where properties sell infrequently and the composition of the market changes constantly — conditions that map precisely onto the MTG singles market.

The foundational paper is Bailey, Muth & Nourse (1963). Case & Shiller (1987, 1989) extended it with a variance correction that became the S&P/Case-Shiller Home Price Index. The Mei-Moses Art Index applies the same methodology to fine art auction records.

**Why repeat-sales for MTG?**

The MTG singles market has three properties that make standard index construction problematic:

1. **Composition changes constantly.** New sets release every 3 months, rotating thousands of cards in and out of competitive play. A simple average price across all cards in month T₁ vs. T₂ compares different sets of cards — measuring composition change, not price change.

2. **Cards are heterogeneous.** A $500 Black Lotus and a $1.00 common are not comparable data points. Hedonic adjustment (controlling for card characteristics) is possible but requires estimating coefficients for rarity, format, power level — all of which shift over time.

3. **The same card is observed repeatedly.** MTGStocks and TCGPlayer track the same `card_version_id` daily. This is exactly the repeat-sale structure: the same "property" observed at time T₁ and T₂.

---

## The Asset Unit

In real estate, the repeat-sale unit is a **specific house** (a property address). In MTG, the equivalent is a **specific printing of a card** in a specific condition and finish.

For V1, the unit is defined as:

```
asset = (card_version_id, source='tcg', condition='NM', finish='NONFOIL')
```

This corresponds to one row in `pricing.print_price_daily` after filtering. A `card_version_id` is a UUID uniquely identifying one physical print of a card (e.g., Sheoldred, the Apocalypse from Phyrexia: All Will Be One — set code ONE, collector number 97).

**Why NM nonfoil only for V1?**
- NM is the reference grade for all price guides — it has the most observations.
- Foil adds a second price series per card that would need its own index (prices move somewhat independently due to foil-specific supply).
- Mixing conditions would conflate condition degradation with market price change.

---

## Data Preparation

### Source query

```sql
SELECT
    DATE_TRUNC('week', price_date)::DATE  AS price_week,
    cv.card_version_id,
    ucr.card_name,
    s.set_code,
    r.code                                AS rarity,
    AVG(ppd.list_avg_cents)              AS list_avg_cents
FROM pricing.print_price_daily ppd
JOIN pricing.price_source       ps  ON ps.source_id    = ppd.source_id
JOIN pricing.card_condition     cc  ON cc.condition_id = ppd.condition_id
JOIN card_catalog.card_finished cf  ON cf.finish_id    = ppd.finish_id
JOIN card_catalog.card_version  cv  ON cv.card_version_id = ppd.card_version_id
JOIN card_catalog.unique_cards_ref ucr ON ucr.unique_card_id = cv.unique_card_id
JOIN card_catalog.sets          s   ON s.set_id        = cv.set_id
LEFT JOIN card_catalog.rarity_ref r ON r.rarity_id     = cv.rarity_id
WHERE ps.code  = 'tcg'
  AND cc.code  = 'NM'
  AND cf.code  = 'NONFOIL'
  AND ppd.list_avg_cents IS NOT NULL
GROUP BY
    DATE_TRUNC('week', price_date),
    cv.card_version_id, ucr.card_name, s.set_code, r.code
```

### Filters applied after query

| Filter | Rationale |
|---|---|
| `list_avg_cents ≥ 100` (≥ $1.00) | Cards below $1 add noise, have high relative price variance from rounding, and are not investment assets. The $1 floor removes ~60% of card-weeks by count but retains >95% of market cap. |
| At least 2 distinct `price_week` values per card | A card must be observed at least twice to form any pair. Single-observation cards contribute nothing to the index. |
| Log price jump guard: `|Δ ln P| ≤ ln(10)` | Excludes week-over-week changes of more than 10× in either direction. These are data artifacts (listing errors, identifier mismatches) not economic price changes. |

### Log transformation

All methods operate on log prices:

```
p(i, t) = ln( list_avg_cents(i, t) )
```

Working in logs converts multiplicative price changes to additive returns, makes the distribution closer to normal, and produces index values that compound correctly.

---

## Method A: Chained Geometric Mean

### Concept

The simplest construction. At each period, observe which cards have prices in *both* the current and prior week. Compute the average log price change across those cards. Add it to a running cumulative sum to build the index.

This is the "chain-linking" principle used by GDP deflators and some commodity indices.

### Mathematics

Let `Ω(t)` be the set of cards with valid prices in both week `t` and week `t-1`.

**Step 1 — Period log return:**
```
r(t) = (1/|Ω(t)|) × Σᵢ∈Ω(t) [ p(i,t) − p(i,t−1) ]
```

This is the cross-sectional mean of log price changes — the geometric mean of the price ratios.

**Step 2 — Chained log index:**
```
L(t) = L(t−1) + r(t),    with L(base) = ln(100)
```

**Step 3 — Index level:**
```
Index_A(t) = exp( L(t) )
```

By construction `Index_A(base) = 100`. Each period's value represents the cumulative growth of the basket.

### Properties

| Property | Value |
|---|---|
| Equal-weighted | Yes — each card gets weight 1/\|Ω(t)\| |
| Handles gaps | No — a card missing week t is excluded from that period's return |
| Composition bias | Moderate — index depends on which cards happen to have observations |
| Computationally trivial | Yes — two groupby operations |

### Limitations

The primary limitation is **equal weighting**. A $1 card and a $500 card both get weight 1/N. The $1 card's price is noisier in relative terms (a 10-cent move is 10%; on a $500 card it's 0.02%). This inflates measured volatility and biases the index if cheap and expensive cards move differently — which they do, systematically (cheap bulk cards are stickier; expensive staples are more volatile).

Method A should be used as a **sanity check** against B and C, not as the primary index.

---

## Method B: Bailey-Muth-Nourse (BMN) Adjacent-Pair OLS

### Concept

Bailey, Muth & Nourse (1963) reframe index construction as a regression problem. Instead of averaging returns period-by-period, we simultaneously estimate all index values using a single regression across all pairs. The index values are the unknowns; the data are the observed log price changes.

This is equivalent to Maximum Likelihood estimation of the index under the assumption that log price changes are i.i.d. normal around the true index change.

### The Regression Model

For each card `i` observed in adjacent weeks `t−1` and `t`, we observe one data point:

```
Δp(i,t) = p(i,t) − p(i,t−1)
```

The model posits that this equals the true log index change plus card-specific noise:

```
Δp(i,t) = [L(t) − L(t−1)] + ε(i,t)
```

where `L(t)` is the log index level at week `t` (the parameter to estimate) and `ε(i,t) ~ N(0, σ²)` is i.i.d. noise.

### The Design Matrix

Collect all `N` adjacent pairs into a regression:

```
y = X β + ε
```

Where:
- `y` is an N-vector of observed Δp values
- `β` is a (T−1)-vector of unknowns: `β_k = L(k)` for k = 1, ..., T−1 (week 0 is the base: L(0) = 0)
- `X` is a sparse N × (T−1) matrix

Each row of `X` corresponds to one pair `(t−1, t)` for card `i`. The row has:
- `+1` in column `t−1` (if `t−1 > 0`)
- `−1` in column `t−2` (if `t−2 > 0`, i.e., the "minus previous period" entry)

Wait — let us be precise. Label weeks as `k = 0, 1, 2, ..., T-1`. The base period is k=0, L(0)=0. For a pair from k=3 to k=4:

```
Δp = L(4) − L(3) = β₄ − β₃
```

Row in X: `+1` at column index 3 (for β₄), `−1` at column index 2 (for β₃). Columns are indexed 0..T-2 corresponding to β₁..β_{T-1}.

**Example with 4 weeks (k = 0,1,2,3) and 3 cards:**

```
Pair            y        β₁    β₂    β₃
(k=0→1, A)    Δp_A1  [  +1     0     0  ]   →  β₁ = L(1)
(k=1→2, A)    Δp_A2  [  -1    +1     0  ]   →  β₂ - β₁ = L(2)-L(1)
(k=2→3, A)    Δp_A3  [   0    -1    +1  ]   →  β₃ - β₂ = L(3)-L(2)
(k=0→1, B)    Δp_B1  [  +1     0     0  ]
(k=1→2, B)    Δp_B2  [  -1    +1     0  ]
(k=0→1, C)    Δp_C1  [  +1     0     0  ]
(k=2→3, C)    Δp_C3  [   0    -1    +1  ]   ← C was absent in k=2
```

Card C was absent in week k=2. It contributes no pair for that period. This is how unbalanced panels are handled naturally — no imputation needed.

### Solving the System

OLS estimate:

```
β̂ = (X'X)⁻¹ X'y
```

In practice, `X` is large and sparse — use `scipy.sparse.linalg.lsqr` rather than dense matrix inversion.

### Index Construction

```
log_index = [0] + β̂.tolist()      # length T, base period = 0
Index_B(t) = 100 × exp( log_index[t] )
```

### Why This Is Better Than Method A

1. **All cards simultaneously.** Each card's full price history is used to constrain *all* the index values it spans. A card observed for 52 weeks provides 51 constraints on 52 index values — they must be mutually consistent.

2. **Implicit down-weighting of thin periods.** Weeks where few cards have data have few rows in the regression → less influence on nearby β estimates. The OLS solution automatically concentrates precision where data is dense.

3. **No composition bias.** The same β values explain observations from all cards. Adding a new card to the data changes the estimates only to the extent it adds new information, not merely by changing the average.

4. **Handles gaps.** A card absent for 3 weeks contributes pairs for the weeks it is observed; the missing weeks contribute no pairs, but the β values for those weeks are still constrained by other cards.

### Properties

| Property | Value |
|---|---|
| Equal-weighted | No — implicitly value-agnostic (OLS treats all pairs equally) |
| Handles gaps | Yes — absent weeks simply have no pairs for that card |
| Statistically efficient | Yes — BLUE under homoskedastic errors |
| Published methodology | Yes — Bailey, Muth & Nourse (1963) |
| Suitable for publication | Yes |

### Limitation: Homoskedasticity Assumption

BMN assumes `Var(ε) = σ²` constant across all pairs. In practice, the variance of a log price change grows with the time between observations. A price observed today and one year ago has more noise than one observed today and one week ago. For adjacent-only pairs, the time gap is always exactly one week, so this assumption is not violated. But if any non-adjacent pairs were included, it would be.

This is exactly the limitation that Case & Shiller address with Method C.

---

## Method C: Case-Shiller All-Pairs WLS

### Concept

Case & Shiller (1987 NBER Working Paper 2788) observe that the variance of log price changes is not constant — it grows with the time between observations. Specifically, if prices follow a random walk with drift and noise:

```
p(i,t) = α(i) + μt + η(i,t) + ε(i,t)
```

where `η(i,t)` is an "individual random walk" term and `ε(i,t)` is i.i.d. noise, then:

```
Var[ p(i,t₂) − p(i,t₁) ] = σ²_η × (t₂ − t₁) + 2σ²_ε
```

The variance grows linearly with the gap. Pairs separated by a long time interval are noisier — they should receive lower weight in the regression.

Case & Shiller also use **all pairs** (not just adjacent), which recovers information from cards that are observed infrequently.

### Weight Function

The simplest variance-inverse weighting:

```
w(i, t₁, t₂) = 1 / (t₂ − t₁)²
```

(In full Case-Shiller, the weights also include a σ²_ε term estimated from adjacent pairs, but 1/gap² is a close and simpler approximation for weekly data.)

### The WLS Regression

Same design matrix structure as Method B, but now includes **all pairs**, not just adjacent ones.

For card `i` observed at weeks `{k₁, k₂, k₃, k₄}`, all pairs generated:

```
(k₁, k₂), (k₁, k₃), (k₁, k₄)
           (k₂, k₃), (k₂, k₄)
                      (k₃, k₄)
```

For N_i observations, card i contributes N_i × (N_i − 1) / 2 pairs.

The WLS objective:

```
β̂ = argmin Σ_pairs w(i,t₁,t₂) × [ Δp(i,t₁,t₂) − (β_{t₂} − β_{t₁}) ]²
```

Solved as weighted OLS:

```
β̂ = (X'WX)⁻¹ X'Wy

where W = diag(w₁, w₂, ..., w_N)
```

Equivalently, pre-multiply rows by √w and run unweighted OLS:

```
X_w = diag(√w) × X,    y_w = √w ⊙ y
β̂ = lstsq(X_w, y_w)
```

### Memory Management

**The pair explosion problem.** A card observed for 104 weeks (2 years) generates 104×103/2 = 5,356 pairs. With 20,000 active cards, this approaches 100M rows — infeasible for dense storage.

**V1 mitigation strategy:**

For cards with more than `MAX_OBS = 52` weekly observations:
1. Always include all adjacent pairs (gap = 1 week).
2. For longer gaps, subsample at quarterly intervals: pairs with gaps of 13, 26, 39, 52 weeks only.
3. Flag these cards in the output metadata.

This preserves the short-term precision from adjacent pairs and the long-run anchoring from widely-spaced pairs, without the quadratic memory cost.

**V1 implementation uses `scipy.sparse` throughout:**

```python
from scipy.sparse import lil_matrix, csr_matrix
from scipy.sparse.linalg import lsqr

X = lil_matrix((n_pairs, n_weeks - 1))
# ... fill rows ...
X_csr = X.tocsr()
# Apply weights
W_sqrt = diags(np.sqrt(weights))
X_w = W_sqrt @ X_csr
y_w = np.sqrt(weights) * y
result = lsqr(X_w, y_w)
beta = result[0]
```

### Properties

| Property | Value |
|---|---|
| Variance-corrected | Yes — long gaps down-weighted |
| Uses all pairs | Yes (with memory guard for dense cards) |
| Handles sparse history | Best of the three methods |
| Published methodology | Yes — Case & Shiller (1987, 1989) |
| Computationally intensive | Yes — sparse matrix required |
| Upgrade from B | Yes — B is Method C restricted to adjacent pairs with uniform weights |

---

## Comparing the Three Methods

### When they agree

If the market is liquid (all cards observed every week with no gaps) and returns are homoskedastic, all three methods converge to the same index. Divergence between A and B/C signals composition bias in Method A. Divergence between B and C signals the importance of the variance correction — usually only material in thin markets or over long time horizons.

### Expected divergence in MTG data

| Source of divergence | Magnitude |
|---|---|
| A vs. B/C: cheap-card noise | Low-to-moderate — $1 floor reduces this |
| A vs. B/C: composition change | Moderate — 3-month set rotation changes active card pool significantly |
| B vs. C: sparse card history | Low in short windows; increases over 2+ year windows |
| B vs. C: long-gap variance | Low for adjacent-only B; becomes visible when comparing 6-month periods |

---

## Index Interpretation

### What the index measures

`Index(t) = 100` at base period. `Index(t) = 150` means a representative card purchased at the base period would be worth 50% more at time `t` in nominal terms.

The index measures **listed market price change** — not sold/transaction price change. This distinction matters because listed prices can diverge from actual trading prices during market dislocations (high buy pressure, post-ban crashes). A sold-price index would require `sold_avg_cents` data, which is significantly sparser.

### What it does not measure

- **Total return.** The index measures price appreciation only. It does not include the "emotional yield" (enjoyment from playing with the cards), transaction costs, storage costs, or the cost of capital tied up in inventory.
- **Individual card returns.** The index is a basket — individual cards may dramatically outperform or underperform.
- **Liquidity.** A card with a listed price may be impossible to actually sell at that price. The illiquidity premium analysis (Gap 2 in `MTG_QUANT_RESEARCH.md`) addresses this separately.

### Benchmark comparisons

Once constructed, the index can be benchmarked against:
- S&P 500 total return (via `^GSPC` from Yahoo Finance)
- Consumer Price Index (CPI) — real vs. nominal MTG returns
- Other collectible indices (Pokémon, sports cards — via PriceCharting public data)

---

## Upgrade Path (V2+)

| Enhancement | Prerequisite |
|---|---|
| Full Case-Shiller σ²_ε estimation | V1 adjacent-pair residuals |
| Foil sub-index | Separate foil price data cleaning |
| Multi-source index (TCGPlayer + Cardmarket) | Currency harmonisation layer |
| Confidence intervals via bootstrap | V1 β estimates |
| Rolling 52-week index | V1 weekly index |
| Format sub-indices (Standard vs. Commander vs. Legacy) | Format legality join from Scryfall |
| Wishlist demand-signal lead-time | Wishlist snapshot accumulation |
| Real (inflation-adjusted) index | CPI data join |

---

## References

| Source | Notes |
|---|---|
| Bailey, Muth & Nourse (1963), *Management Science* | Original BMN repeat-sales paper — Method B |
| Case & Shiller (1987), NBER WP 2788 | Variance correction and all-pairs extension — Method C |
| Case & Shiller (1989), *AREUEA Journal* | The published version with empirical results |
| Mei & Moses (2002), *American Economic Review* | Application to fine art — the closest analogue to MTG |
| Dimson, Rousseau & Spaenjers (2015), *JFE* | Fine wine repeat-sales index — `papers/dimson-rousseau-spaenjers-2015-wine.pdf` |
| Goetzmann et al. (2002), NBER WP 9116 | Art as an alternative asset — `papers/goetzmann-2002-art-sharpe.pdf` |
| Langelett & Wang (2023), *GJAF* | MTG sealed product investment — the only peer-reviewed MTG finance paper |

---

*Document version 1.0 — 2026-05-24. Update when V2 methodology is implemented.*
