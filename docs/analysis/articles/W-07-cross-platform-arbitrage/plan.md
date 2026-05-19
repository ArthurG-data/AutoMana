# Plan — W-07: Cross-Platform Arbitrage Windows

**Target publish:** Week 7
**Recurring:** No (run quarterly — arbitrage windows close as markets mature)
**Notebook:** new — `notebooks/cross_platform_arbitrage.ipynb`

---

## Hypothesis

Persistent price gaps between platforms (TCGPlayer, eBay, CardKingdom) exceed all-in transaction costs (fees + shipping) for a meaningful subset of cards at any given time — and these windows last long enough to be actionable.

---

## Data Needed

| Source | Table / Field | Notes |
|--------|--------------|-------|
| AutoMana DB | `pricing.price_observations` | Multi-source: source field distinguishes platforms |
| AutoMana DB | `ebay.sold_listings` | eBay sold side |
| Manual / config | Fee model | TCGPlayer seller fee ~12.5%, eBay ~13%, shipping ~$1–4 |

**Platform pairs to analyze:**
1. TCGPlayer listed vs. eBay sold (most liquid pair)
2. eBay listed vs. CardKingdom buylist
3. TCGPlayer listed vs. CardKingdom buylist

**Gap metric (after fees):**
`net_gap = (sell_price × (1 − sell_fee)) − (buy_price + shipping)`

**Filters:**
- net_gap > $2.00 (minimum actionable threshold)
- Card must have ≥ 10 listings on buy side
- NM condition only

---

## Key Metrics

- After-fee spread by platform pair
- Median window duration (how many days gap persisted above threshold)
- Volume of cards with actionable gap on snapshot date
- Card characteristics of best candidates (price tier, liquidity, age)

---

## Figures (4)

| # | Type | What it shows |
|---|------|---------------|
| 1 | Box plot | After-fee spread distribution by platform pair |
| 2 | Scatter | Gap size vs. window duration (days above threshold) |
| 3 | Sorted bar | Top 20 cards by current arbitrage gap |
| 4 | Line chart | # actionable arbitrage opportunities per week (trend) |

---

## Outline

1. **Introduction** — price convergence theory; why gaps persist despite efficient markets
2. **Methodology** — fee model, gap formula, window duration definition
3. **Results** — platform pair comparison first, then persistence, then current opportunity list
4. **Discussion** — friction costs as the moat; why high-price cards have larger persistent gaps
5. **Takeaways** — how to screen for opportunities; which platform pairs are most productive
6. **Limitations** — snapshot bias (gaps close fast); condition risk on eBay buy side; shipping cost variance

---

## Notes / Pre-writing Observations

*(fill in after building the notebook)*
