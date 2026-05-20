# Plan — W-06: Set Release Price Impact

**Target publish:** Week 6
**Recurring:** No (run after each major release)
**Notebook:** new — `notebooks/set_release_impact.ipynb`

---

## Hypothesis

New set releases depress prices of rotating formats more than commonly expected, and the price trough occurs 4–6 weeks post-release rather than at release day — because supply takes time to reach the secondary market through drafting and opening.

---

## Data Needed

| Source | Table / Field | Notes |
|--------|--------------|-------|
| AutoMana DB | `pricing.price_observations` | Aligned to release dates — 20-week window |
| AutoMana DB | `card_catalog.sets` | `release_date`, `set_type` |
| AutoMana DB | `card_catalog.card_versions` | Rarity, format legality |

**Event window:** T−8 weeks to T+12 weeks relative to each set's release date.

**Card pool:** Standard-legal cards from sets released in the last 3 years. Excludes land cycles and bulk rares (base price < $1).

**Normalization:** Price index = price(T) / price(T−4w) for each card. Then average across cards by rarity.

---

## Key Metrics

- Average price index at T+2, T+4, T+6, T+8, T+12 by rarity
- Trough depth (minimum index value) and timing (week of minimum)
- Recovery rate: % of cards back to T−4w price by T+12w
- Variance in trough timing (does it cluster around 4–6w?)

---

## Figures (4)

| # | Type | What it shows |
|---|------|---------------|
| 1 | Line chart | Average price index relative to release date by rarity (T−8w to T+12w) |
| 2 | Bar chart | Median trough depth by rarity |
| 3 | Bar chart | % recovery at T+4, T+8, T+12 by rarity |
| 4 | Scatter | Pre-release price vs. post-trough floor (which cards lose most) |

---

## Outline

1. **Introduction** — the set-release price cycle; why "buy the dip" is not as simple as release day
2. **Methodology** — how T is defined, how index is normalized, which sets were included
3. **Results** — time series first (Figure 1), then depth and recovery analysis
4. **Discussion** — optimal buy window by rarity; why mythics recover faster than rares
5. **Takeaways** — timing guide for new-set purchases
6. **Limitations** — driven by format playability (ban announcements confound); supply varies by set size

---

## Notes / Pre-writing Observations

*(fill in after building the notebook)*
