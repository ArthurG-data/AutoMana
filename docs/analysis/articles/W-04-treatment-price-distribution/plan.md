# Plan — W-04: Treatment Price Distribution

**Target publish:** Week 4
**Recurring:** Monthly re-run
**Notebook:** `notebooks/treatment_price_analysis.ipynb`

---

## Hypothesis

Card treatments create distinct price clusters, not a continuum. The gap between standard and premium art treatments has widened, and the premium is not explained by card power level alone.

---

## Data Needed

| Source | Table / Field | Notes |
|--------|--------------|-------|
| AutoMana DB | `pricing.price_observations` | Last 90 days, NM |
| AutoMana DB | `card_catalog.card_versions` | `treatment` field |
| AutoMana DB | `card_catalog.cards` | For base (non-treatment) version price |

**Treatment buckets:**
- `standard` (baseline)
- `extended_art`
- `borderless`
- `showcase`
- `etched` (non-foil etched)
- `serialized` (if present)

**Normalization:** Treatment premium = treatment price / same-card standard price. Requires at least one standard printing to exist.

**Filters:**
- Cards with at least 2 treatment variants
- Base price > $1.00 (to avoid noise in the multiplier)
- Minimum 5 observations per variant

---

## Key Metrics

- Mean and median normalized treatment premium per bucket
- Distribution overlap coefficient between adjacent buckets (are they really distinct?)
- 6-month trend of premium per treatment
- Correlation between treatment premium and card liquidity (# sales/week)

---

## Figures (4)

| # | Type | What it shows |
|---|------|---------------|
| 1 | Violin plot | Price distribution by treatment type |
| 2 | Sorted bar | Normalized treatment premium, base = 1.0, with IQR |
| 3 | Line chart | Treatment premium trend over 6 months — top 3 treatments |
| 4 | Scatter | Treatment premium vs. liquidity (# sold/week) |

---

## Outline

1. **Introduction** — why treatment matters to collectors and the secondary market; "art tax" hypothesis
2. **Methodology** — how premium is normalized, how treatments are bucketed
3. **Results** — distribution first (clusters vs. continuum), then premium ranking, trend, liquidity link
4. **Discussion** — which treatments are "worth it" by premium stability; which are driven by hype
5. **Takeaways** — collector vs. investor framing for each treatment tier
6. **Limitations** — confound: some treatments only exist for high-power cards; sample sizes differ by treatment

---

## Notes / Pre-writing Observations

*(fill in after running the notebook)*
