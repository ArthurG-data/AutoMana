# MTG Finance Analysis — Editorial Plan

## Article Template

```
# [Title]: [Subtitle]
**Edition #N · [Date] · ~[X] min read**

---

## Abstract
2–3 sentences. What question was asked, what data was used, what the answer is.

---

## 1. Introduction
- Market context: why this topic matters *right now*
- The central hypothesis or question being tested
- Scope (formats, time window, card pool)

## 2. Data & Methodology
- Source(s): AutoMana DB / Scryfall / MTGStock / eBay sold listings
- Date range and snapshot date
- Filters applied (minimum price, print runs excluded, etc.)
- How metrics were computed (formulas if non-obvious)
- Known data limitations

## 3. Results

### 3.1 [First finding]
*Figure 1 — [caption]*

[Figure]

Interpretation paragraph.

### 3.2 [Second finding]
*Figure 2 — [caption]*

[Figure]

Interpretation paragraph.

*(repeat for each figure)*

## 4. Discussion
- What the results mean for players / collectors / speculators
- Comparison to prior editions (if recurring topic)
- Surprising or counter-intuitive findings

## 5. Key Takeaways
- Bullet 1
- Bullet 2
- Bullet 3

## 6. Limitations & Caveats
- Sample size, survivorship bias, data freshness, confounders

---
*Data collected: [date]. Next edition: [topic].*
```

---

## Format Guidelines

| Parameter | Recommendation |
|-----------|---------------|
| Word count | 900–1 300 words (body only, excluding captions and tables) |
| Figures | **4–5 per article** — never fewer than 3, rarely more than 6 |
| Tables | 0–2 supplementary tables (raw top-N lists, regression coefficients) |
| Reading level | Clear and precise; define jargon on first use |
| Tone | Analytical, hedged ("suggests", "indicates"), not prescriptive |
| Cadence | Weekly, same day each week |

**Figure types that work well:**
- Line chart — price over time, moving averages
- Box plot — distribution by finish / treatment / rarity
- Scatter plot — two-variable relationships (e.g. spread vs. liquidity)
- Bar chart (sorted) — rankings, premiums by category
- Histogram — price spread distribution, sold/list gap

---

## Article Series

### Standard Weekly (Recurring)

---

### Article W-01 — Foil vs. Non-Foil Premium by Treatment
**Hypothesis:** The foil premium varies significantly across treatment types (etched, borderless, showcase, extended art) and is not stable over time.

**Data needed:** `pricing.price_observations` joined to `card_catalog.card_versions` on `finish` and `treatment` columns; 90-day window.

**Key metrics:**
- Median foil multiplier per treatment type
- Coefficient of variation within each group
- Week-over-week delta

**Suggested figures:**
1. Box plot — foil multiplier distribution by treatment
2. Line chart — median foil multiplier over 12 weeks for top 4 treatments
3. Scatter — foil price vs. non-foil price, colored by treatment
4. Bar chart — ranked treatments by median premium

**Recurring cadence:** Monthly re-run with updated window.

---

### Article W-02 — Sold vs. Listed Price Gap (Market Efficiency)
**Hypothesis:** The spread between listed and eBay sold prices is non-random; it varies by finish, price tier, and market conditions.

**Data needed:** `ebay.sold_listings` joined to `pricing.price_observations`; matched by card + finish + date proximity.

**Key metrics:**
- Mean and median spread (listed − sold) absolute and %
- Spread by finish category
- Spread by price tier (< $5 / $5–25 / $25–100 / $100+)

**Suggested figures:**
1. Histogram — spread % distribution across all matched cards
2. Box plot — spread by finish (NM, foil, etched…)
3. Bar chart — mean spread by price tier
4. Line chart — weekly average spread over time (liquidity proxy)

---

### Article W-03 — Lowest Available Price Patterns
**Hypothesis:** The lowest-listed price on the market deviates from the median in predictable ways; extreme low outliers signal either condition misrepresentation or genuine arbitrage.

**Data needed:** `pricing.price_observations` with `source = 'tcgplayer'` (or equivalent); percentile calculation per card + finish.

**Key metrics:**
- P5 / P50 / P95 spread per card
- Outlier count (< P5 − 2σ) by set age
- Cards where P5 < buylist (value traps / arbitrage)

**Suggested figures:**
1. Scatter — P5 vs. P50 price, log scale
2. Histogram — (P50 − P5) / P50 distribution
3. Table — top 20 arbitrage candidates (P5 < buylist)
4. Bar chart — outlier rate by set age bucket

---

### Article W-04 — Treatment Price Distribution
**Hypothesis:** Card treatments create distinct price clusters, not a continuum; the gap between "standard" and "premium" art treatment has widened.

**Data needed:** `pricing.price_observations` × `card_catalog.card_versions.treatment`; same card in multiple treatments.

**Key metrics:**
- Mean price by treatment, normalized to base version
- Distribution overlap between adjacent treatment tiers
- Trend of treatment premium over 6-month window

**Suggested figures:**
1. Violin plot — price distribution by treatment type
2. Bar chart — normalized treatment premium (base = 1.0)
3. Line chart — treatment premium trend over time (top 3 treatments)
4. Scatter — treatment premium vs. card liquidity (# sold/week)

---

### Article W-05 — Reprint Risk & Price Floor Analysis
**Hypothesis:** Cards with high reprint probability trade at a discount to their "reprint-free" fair value; quantifying this discount reveals which fears are already priced in.

**Data needed:** `pricing.price_observations` historical; reprint events from `card_catalog.sets` (set_type, release_date); manual reprint-risk tier list.

**Key metrics:**
- Price trajectory before/after reprint announcement
- Average drawdown from peak to post-reprint floor
- Cards currently priced above estimated reprint floor

**Suggested figures:**
1. Line chart — price index before/after reprint announcement (averaged across N cards)
2. Bar chart — average drawdown by reprint vehicle (Commander precon, Masters set, etc.)
3. Scatter — current price vs. estimated floor, colored by risk tier
4. Table — top 15 "priced-above-floor" candidates with risk tier

---

### Article W-06 — Set Release Price Impact
**Hypothesis:** New set releases depress prices of rotating formats more than expected, and the trough occurs 4–6 weeks post-release, not at release.

**Data needed:** `pricing.price_observations` aligned to `card_catalog.sets.release_date`; Standard-legal cards only.

**Key metrics:**
- Price index relative to release date (T−8w to T+12w)
- Depth and timing of trough by rarity
- Recovery rate (% cards back to pre-release price by T+12w)

**Suggested figures:**
1. Line chart — average price index relative to release date by rarity
2. Bar chart — trough depth by rarity
3. Line chart — % recovery at T+4, T+8, T+12 weeks
4. Scatter — pre-release price vs. post-trough floor (sorting cards)

---

### Article W-07 — Cross-Platform Arbitrage Windows
**Hypothesis:** Persistent price gaps between platforms (TCGPlayer, eBay, CardKingdom) exceed transaction costs for a subset of cards at any given time.

**Data needed:** Multi-source `pricing.price_observations` for same card + finish + condition; shipping/fee model.

**Key metrics:**
- After-fee spread by platform pair
- Arbitrage window duration (how many days gap persisted)
- Card characteristics of best arbitrage candidates (liquidity, price tier)

**Suggested figures:**
1. Box plot — after-fee spread by platform pair
2. Scatter — gap size vs. window duration
3. Bar chart — top cards by arbitrage frequency
4. Line chart — arbitrage opportunity count per week (market efficiency trend)

---

### Article W-08 — Buylist Efficiency Index
**Hypothesis:** Buylist-to-market ratios are not uniform; specific card archetypes and price tiers are systematically under- or over-bought by stores.

**Data needed:** Buylist prices (CardKingdom / CFB / SCG) vs. `pricing.price_observations`; matched by card + finish + NM condition.

**Key metrics:**
- Buylist % of market by price tier
- Outliers (buylist > market = opportunity)
- Store comparison: which store pays best by category

**Suggested figures:**
1. Bar chart — median buylist % by price tier
2. Scatter — buylist price vs. market price, log-log
3. Bar chart — store-by-store buylist % (same card pool)
4. Table — top 20 "buy from market, sell to buylist" candidates

---

### Article W-09 — Condition Premium Collapse
**Hypothesis:** The NM-to-LP premium has compressed in recent years as graded cards siphon the high end and casual demand dominates the low end.

**Data needed:** eBay sold listings stratified by stated condition; `pricing.price_observations` by condition where available.

**Key metrics:**
- NM/LP ratio by price tier and finish
- Year-over-year trend in NM/LP ratio
- Cards where LP > NM (data quality / market anomaly)

**Suggested figures:**
1. Box plot — NM/LP ratio by price tier
2. Line chart — median NM/LP ratio over 24 months
3. Bar chart — NM/LP ratio by finish type
4. Scatter — NM price vs. NM/LP ratio (do expensive cards hold condition premium?)

---

### Article W-10 — Liquidity-Adjusted Price Analysis
**Hypothesis:** Illiquid cards are systematically over-priced relative to liquid cards when controlling for power level and format legality.

**Data needed:** Sold frequency (eBay volume) per card per week; `pricing.price_observations`; format legality from Scryfall.

**Key metrics:**
- Liquidity score (sales/week) per card
- Price-to-liquidity ratio vs. format-playability proxy
- Spread premium for illiquid cards

**Suggested figures:**
1. Scatter — price vs. liquidity (log-log), colored by format
2. Bar chart — average spread (ask/sold) by liquidity bucket
3. Line chart — illiquid card price stability vs. liquid card price stability
4. Table — high-price / low-liquidity "stranded value" candidates

---

## Publication Order (Suggested)

| Week | Article |
|------|---------|
| 1 | W-01 — Foil Premium by Treatment |
| 2 | W-02 — Sold vs. Listed Gap |
| 3 | W-03 — Lowest Price Patterns |
| 4 | W-04 — Treatment Price Distribution |
| 5 | W-05 — Reprint Risk |
| 6 | W-06 — Set Release Impact |
| 7 | W-07 — Cross-Platform Arbitrage |
| 8 | W-08 — Buylist Efficiency |
| 9 | W-09 — Condition Premium |
| 10 | W-10 — Liquidity-Adjusted Price |

After Week 10, restart with updated data — the recurring cadence begins with articles flagged as **"Monthly re-run"** (W-01, W-02, W-04).
