# Plan — W-05: Reprint Risk & Price Floor Analysis

**Target publish:** Week 5
**Recurring:** No (revisit after each major reprint announcement)
**Notebook:** new — `notebooks/reprint_risk_analysis.ipynb`

---

## Hypothesis

Cards with high reprint probability trade at a discount to their "reprint-free" fair value. The market prices in some but not all reprint risk — meaning the discount is smaller than warranted for high-risk cards, and larger than warranted for low-risk cards.

---

## Data Needed

| Source | Table / Field | Notes |
|--------|--------------|-------|
| AutoMana DB | `pricing.price_observations` | Historical — 24-month window |
| AutoMana DB | `card_catalog.sets` | `set_type`, `release_date` — identify reprint vehicles |
| AutoMana DB | `card_catalog.card_versions` | Which sets a card has already appeared in |
| Manual | Reprint risk tier list | Author-assigned: Low / Medium / High / Certain |

**Reprint event detection:** Card appears in a new set_code after having a price history. Measure price trajectory T−8w to T+12w around the announcement date.

**Risk tier definition (author to assign):**
- **Low** — Reserved List, strong IP lock
- **Medium** — Not on RL but not reprinted in 5+ years
- **High** — Flagged in recent set announcements or interview hints
- **Certain** — Already announced but not yet released

---

## Key Metrics

- Average price drawdown from peak to post-reprint floor (by reprint vehicle type)
- % of cards back to pre-reprint price at T+12w
- Current cards priced above estimated reprint floor (at-risk premium)
- Speed of price decline: days from announcement to trough

---

## Figures (4)

| # | Type | What it shows |
|---|------|---------------|
| 1 | Line chart | Average price index relative to announcement date, by rarity |
| 2 | Bar chart | Average drawdown by reprint vehicle (Commander precon, Masters set, Standard set, etc.) |
| 3 | Scatter | Current price vs. estimated floor, colored by risk tier |
| 4 | Table | Top 15 "priced above floor" candidates with assigned risk tier |

---

## Outline

1. **Introduction** — reprint risk as a priced-in variable; the asymmetry between RL and non-RL cards
2. **Methodology** — how historical reprint events were identified, how risk tiers were assigned
3. **Results** — historical drawdown patterns first, then current at-risk cards
4. **Discussion** — which cards represent "reprints already priced in" vs. "the market is complacent"
5. **Takeaways** — cards to avoid, cards where fear is overblown
6. **Limitations** — tier assignment is subjective; Wizards is not predictable

---

## Notes / Pre-writing Observations

*(fill in after building the notebook)*
