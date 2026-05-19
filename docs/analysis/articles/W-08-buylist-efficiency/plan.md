# Plan — W-08: Buylist Efficiency Index

**Target publish:** Week 8
**Recurring:** No (run quarterly — buylist rates change slowly)
**Notebook:** new — `notebooks/buylist_efficiency.ipynb`

---

## Hypothesis

Store buylist-to-market ratios are not uniform. Specific card archetypes and price tiers are systematically over- or under-bought by stores, creating predictable patterns in where sellers get the best value.

---

## Data Needed

| Source | Table / Field | Notes |
|--------|--------------|-------|
| AutoMana DB | `pricing.price_observations` | Market (TCGPlayer) prices, NM |
| External | CardKingdom buylist | Scraped or manually collected |
| External | CFB buylist | Scraped or manually collected |
| External | SCG buylist | Scraped or manually collected |

**Matching:** Match buylist entries to AutoMana card_versions by card name + set + finish. Join to price observations at same snapshot date.

**Buylist efficiency (BLE):**
`BLE = buylist_price / market_price`

**Filters:**
- Market price ≥ $2.00
- NM condition only
- At least 2 stores have a buylist price for the card

---

## Key Metrics

- Median BLE by price tier (< $5 / $5–25 / $25–100 / $100+)
- Median BLE by finish (non-foil vs. foil vs. etched)
- Store comparison: which store has highest BLE for each category
- Cards where BLE > 1.0 (buylist exceeds market — genuine opportunity)

---

## Figures (4)

| # | Type | What it shows |
|---|------|---------------|
| 1 | Bar chart | Median BLE by price tier |
| 2 | Scatter | Buylist price vs. market price (log-log), colored by finish |
| 3 | Grouped bar | BLE by store for same card pool (CardKingdom vs. CFB vs. SCG) |
| 4 | Table | Top 20 "buy from market, sell to buylist" candidates |

---

## Outline

1. **Introduction** — what buylist efficiency means; why stores pay differently; the cost of holding cash vs. inventory
2. **Methodology** — data sources, snapshot date, BLE formula
3. **Results** — overall BLE distribution, then by tier, then store comparison, then opportunity table
4. **Discussion** — which stores optimize for which segments; when to prefer a buylist over eBay
5. **Takeaways** — seller's checklist before listing on eBay
6. **Limitations** — buylist data is point-in-time; stores limit quantities; grading standards differ

---

## Notes / Pre-writing Observations

*(fill in after building the notebook)*
