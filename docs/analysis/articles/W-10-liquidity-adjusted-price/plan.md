# Plan — W-10: Liquidity-Adjusted Price Analysis

**Target publish:** Week 10
**Recurring:** No (run quarterly)
**Notebook:** new — `notebooks/liquidity_adjusted_price.ipynb`

---

## Hypothesis

Illiquid cards are systematically over-priced relative to liquid cards when controlling for format legality and card power. The spread between ask and realized price is wider for illiquid cards, meaning the "true" price is lower than the listed price suggests.

---

## Data Needed

| Source | Table / Field | Notes |
|--------|--------------|-------|
| AutoMana DB | `ebay.sold_listings` | Sales volume per card per week (liquidity score) |
| AutoMana DB | `pricing.price_observations` | Listed prices (ask side) |
| AutoMana DB | `card_catalog.card_versions` | Format legality, finish |
| AutoMana DB | `card_catalog.cards` | For deduplication (base card, not all printings) |

**Liquidity score:** Median weekly sales count over last 12 weeks.

**Liquidity buckets:**
- High: > 10 sales/week
- Medium: 3–10 sales/week
- Low: 1–3 sales/week
- Illiquid: < 1 sale/week

**Liquidity discount:**
`discount = (listed_price − sold_price) / listed_price`
Compute per card, then aggregate by liquidity bucket.

---

## Key Metrics

- Median liquidity discount by bucket
- Median ask/sold spread by liquidity bucket
- Price stability (std dev of weekly price) by liquidity bucket
- Correlation between liquidity score and price stability

---

## Figures (4)

| # | Type | What it shows |
|---|------|---------------|
| 1 | Scatter | Listed price vs. liquidity score (log-log), colored by format |
| 2 | Box plot | Ask/sold spread by liquidity bucket |
| 3 | Line chart | Price volatility (weekly std dev) vs. liquidity bucket over time |
| 4 | Table | High-price / low-liquidity "stranded value" candidates |

---

## Outline

1. **Introduction** — liquidity as a hidden cost; the illusion of a "market price" on thinly traded cards
2. **Methodology** — liquidity score definition, bucket thresholds, spread computation
3. **Results** — scatter overview first, then spread by bucket, then volatility
4. **Discussion** — when an illiquid card's listed price is not a reliable signal; implications for collection valuation
5. **Takeaways** — how to adjust your portfolio valuation for liquidity; cards to avoid as stores of value
6. **Limitations** — sales count conflates different printings; eBay is not the only marketplace

---

## Notes / Pre-writing Observations

*(fill in after building the notebook)*
