# Plan — W-03: Lowest Available Price Patterns

**Target publish:** Week 3
**Recurring:** No (one-shot; revisit if arbitrage landscape shifts)
**Notebook:** `notebooks/card_lowest_price_research.ipynb`

---

## Hypothesis

The lowest-listed price on the market deviates from the median in predictable ways. Extreme low outliers signal condition misrepresentation, regional pricing, or genuine short-lived arbitrage — and their distribution is not uniform across card tiers.

---

## Data Needed

| Source | Table / Field | Notes |
|--------|--------------|-------|
| AutoMana DB | `pricing.price_observations` | Per-card P5, P50, P95 — snapshot date |
| AutoMana DB | `card_catalog.card_versions` | finish, set_code |
| AutoMana DB | `card_catalog.sets` | set age (release_date) |
| External | Buylist prices (CardKingdom) | For buylist comparison on outliers |

**Computation:**
- For each card + finish, compute P5, P50, P95 across all active listings on snapshot date
- Outlier threshold: P5 < P50 − 2σ (where σ = std dev across all listings for that card)

**Filters:**
- Minimum 10 listings per card + finish
- NM condition only
- Exclude listings flagged as auction (Buy It Now only)

---

## Key Metrics

- **(P50 − P5) / P50** — relative low-end discount
- Outlier rate per set-age bucket (< 1yr / 1–3yr / 3yr+)
- Cards where P5 < buylist price (arbitrage candidates)
- Correlation between liquidity (# listings) and outlier rate

---

## Figures (4–5)

| # | Type | What it shows |
|---|------|---------------|
| 1 | Scatter | P5 vs. P50 price (log scale) — all cards |
| 2 | Histogram | (P50 − P5) / P50 distribution |
| 3 | Bar chart | Outlier rate by set age bucket |
| 4 | Scatter | Outlier rate vs. # listings (liquidity) |
| 5 | Table | Top 20 arbitrage candidates (P5 < buylist) |

---

## Outline

1. **Introduction** — what "lowest price" means in practice; condition risk vs. genuine value
2. **Methodology** — percentile calculation, outlier threshold definition, buylist data source
3. **Results** — overall P5/P50 picture, then set age, liquidity, then arbitrage table
4. **Discussion** — where low prices are probably noise vs. signal; how to act on the table
5. **Takeaways** — practical screen for bargain hunters
6. **Limitations** — condition trust, snapshot bias (listings change hourly)

---

## Notes / Pre-writing Observations

*(fill in after running the notebook)*
