# Editorial Guide — MTG Finance Analysis Series

## Folder Structure

```
articles/
├── EDITORIAL_GUIDE.md          ← this file
├── W-01-foil-premium-by-treatment/
│   ├── plan.md                 ← research plan (filled before writing)
│   ├── article.md              ← final article text
│   └── figures/                ← exported charts (PNG/SVG)
│       ├── fig1-*.png
│       └── ...
└── ...
```

---

## Article Template

Copy this into `article.md` when you start writing.

```markdown
# [Title]: [Subtitle]
**Edition #N · [Date] · ~[X] min read**

---

## Abstract
2–3 sentences. Question asked, data used, answer found.

---

## 1. Introduction
- Market context: why this topic matters right now
- Central hypothesis or question
- Scope (formats, time window, card pool)

## 2. Data & Methodology
- Source(s) and snapshot date
- Filters applied
- How key metrics were computed
- Known limitations of the data

## 3. Results

### 3.1 [Finding label]
*Figure 1 — [caption]*

![fig1](figures/fig1-*.png)

Interpretation paragraph.

### 3.2 [Finding label]
*Figure 2 — [caption]*

![fig2](figures/fig2-*.png)

Interpretation paragraph.

*(one section per figure)*

## 4. Discussion
- What results mean for players / collectors / speculators
- Comparison to prior editions if recurring
- Surprising or counter-intuitive findings

## 5. Key Takeaways
- Point 1
- Point 2
- Point 3

## 6. Limitations & Caveats
- Sample size, survivorship bias, data freshness, confounders

---
*Data collected: [date]. Next edition: [topic].*
```

---

## Format Rules

| Parameter | Target |
|-----------|--------|
| Word count | 900–1 300 words (body, no captions or tables) |
| Figures | 4–5 (never fewer than 3) |
| Tables | 0–2 supplementary |
| Tone | Analytical, hedged — "suggests", "indicates", not "proves" |
| Cadence | Weekly, same day |

**Preferred figure types:**
- Line chart — price over time, moving averages
- Box / violin plot — distribution by finish, treatment, rarity
- Scatter — two-variable relationships
- Sorted bar chart — rankings, premiums
- Histogram — spread distributions

---

## Publication Order

| Week | Folder |
|------|--------|
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

W-01, W-02, and W-04 are designed for monthly re-runs with updated data windows.
