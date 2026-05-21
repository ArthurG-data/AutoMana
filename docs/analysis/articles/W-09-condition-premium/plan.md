# Plan — W-09: Condition Premium Collapse

**Target publish:** Week 9
**Recurring:** No (run annually — structural trend, not fast-moving)
**Notebook:** new — `notebooks/condition_premium.ipynb`

---

## Hypothesis

The NM-to-LP price premium has compressed over recent years. Two forces are squeezing it: graded slabs siphon demand for near-perfect copies at the high end, and casual demand dominates the low end where condition matters less.

---

## Data Needed

| Source | Table / Field | Notes |
|--------|--------------|-------|
| AutoMana DB | `ebay.sold_listings` | Stratified by stated condition (NM, LP, MP) |
| AutoMana DB | `pricing.price_observations` | Listed prices by condition where available |
| AutoMana DB | `card_catalog.card_versions` | finish, price tier |

**NM/LP ratio:**
`ratio = NM_median_sold / LP_median_sold` for same card + finish, same 30-day window.
Only cards with ≥ 5 NM and ≥ 5 LP sales in window.

**Trend:** Compute ratio quarterly over last 24 months.

**Filters:**
- Exclude cards < $3 NM (condition premium noise at low prices)
- eBay Buy It Now only (auctions introduce condition-independent variance)
- US sellers only (international shipping conflates condition and logistics)

---

## Key Metrics

- Median NM/LP ratio by price tier
- Median NM/LP ratio by finish type
- Quarterly NM/LP ratio trend over 24 months
- Cards where LP median > NM median (data anomalies or genuine inversion)

---

## Figures (4)

| # | Type | What it shows |
|---|------|---------------|
| 1 | Box plot | NM/LP ratio by price tier |
| 2 | Line chart | Median NM/LP ratio by quarter over 24 months |
| 3 | Bar chart | NM/LP ratio by finish type |
| 4 | Scatter | NM price vs. NM/LP ratio (do expensive cards hold condition premium?) |

---

## Outline

1. **Introduction** — what condition premium measures; the NM-LP spread as a market signal; grading and casual demand as structural forces
2. **Methodology** — how the ratio is computed, matching methodology, filters
3. **Results** — current ratio by tier and finish, then trend analysis
4. **Discussion** — implications for sellers (is grading worth it?); for buyers (is LP a bargain?); structural vs. cyclical forces
5. **Takeaways** — at which price tiers does condition still command a real premium
6. **Limitations** — eBay condition descriptions are not standardized; LP from different sellers means different things

---

## Notes / Pre-writing Observations

*(fill in after building the notebook)*
