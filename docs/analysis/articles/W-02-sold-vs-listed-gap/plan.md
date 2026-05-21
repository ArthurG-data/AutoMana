# Plan — W-02: Sold vs. Listed Price Gap

**Target publish:** Week 2
**Recurring:** Monthly re-run
**Notebook:** `notebooks/sold_vs_list_finish_analysis.ipynb`

---

## Hypothesis

The spread between listed and eBay sold prices is non-random. It varies systematically by finish, price tier, and market conditions — and its compression or expansion is a leading indicator of market liquidity.

---

## Data Needed

| Source | Table / Field | Notes |
|--------|--------------|-------|
| AutoMana DB | `ebay.sold_listings` | Sold price, date, card_id, finish |
| AutoMana DB | `pricing.price_observations` | Listed price closest in time to each sale |
| AutoMana DB | `card_catalog.card_versions` | finish, treatment |

**Matching rule:** For each sold listing, find the nearest listed price observation within ±3 days for the same card + finish. Discard unmatched records.

**Filters:**
- Sold price > $1.00
- Condition stated as NM or LP only
- Last 90 days

---

## Key Metrics

- **Spread (absolute)** = listed − sold
- **Spread (%)** = (listed − sold) / listed × 100
- Median and mean spread by finish category
- Median spread by price tier (< $5 / $5–25 / $25–100 / $100+)
- Weekly average spread over time (liquidity trend)

---

## Figures (4)

| # | Type | What it shows |
|---|------|---------------|
| 1 | Histogram | Spread % distribution across all matched cards |
| 2 | Box plot | Spread % by finish (non-foil, foil, etched, special) |
| 3 | Sorted bar | Mean spread by price tier |
| 4 | Line chart | Weekly average spread over last 12 weeks |

---

## Outline

1. **Introduction** — listed price as asking price vs. sold price as revealed preference; the gap as a market efficiency signal
2. **Methodology** — matching methodology, date tolerance, exclusion rules
3. **Results** — histogram first (overall picture), then by finish, tier, time
4. **Discussion** — what a widening/narrowing spread means; which finish is most efficiently priced
5. **Takeaways** — where buyers have leverage, where sellers do
6. **Limitations** — condition mis-labeling, eBay fee differences not controlled for

---

## Notes / Pre-writing Observations

*(fill in after running the notebook)*
