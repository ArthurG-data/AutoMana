# Plan — W-01: Foil Premium by Treatment

**Target publish:** Week 1
**Recurring:** Monthly re-run with updated window
**Notebook:** `notebooks/finish_analysis.ipynb`

---

## Introduction

The allure of wealth, the promiese of a prize of great value and a unique experience. Foiled card have a special place in the heart of card collectible. But a feeble dfream in the eye of ealy player, lightning dragon was the harbringer of new dawn for mtg player. First card printed in fiopl tratement, hint of what was to come, we had to wait until 1998 and the release of Urza's saga to consistently find these prizwe cards in sets. Immediatly, they gathered interest, and despite being the bane of competetive player fdue to a unique fonfness for curling, they beame proze item for colletor. 

Random and rare at first, foil droprate was increased in {}, demoratinsng said prozed items and increasing availble. The offereing of tretment pick up steam in {} with the introduction of etched foil, and more recently Wizard surge and fracture ofld in {} {}, showing the appetite of Hasbro to expend the offerent of premium treatment. the water is murkier. Etched treament gathered littler enthousias, denuting in MH2. Now speculator are faced with a simple dilemna: in a vacumm, wich treatmenet select, and what impact has the recent explosion of offereubn had?

The scarcistyu of foil cards compared to regulare treament commanded a premium on prise, which was easy to quantify when cards only had 2 treament. HOwever, nowadays,

Eager to investigate the mater, that's what we will investaget in this article , bukle up for a time ap[sule of nostalgia], a spiral into the depth of what was and is for foiled cards in Magic the Gathering.

## Hypothesis

The foil premium varies significantly across treatment types (etched, borderless, showcase, extended art) and is not stable over time. Some treatments command a structurally higher multiplier than others, independent of the underlying card's base price. 

---

## Data Needed

Data was collected from 2012 unti {}. Because of scarcity of data, listeed prices in USD where used. The baseline for any given card was the non-foil price of standard art cards. Only mythics and rare cards wher considered. Cards with proce lower than 50C was considerent bulk and not counted, to remove noise.

| Source | Table / Field | Notes |
|--------|--------------|-------|
| AutoMana DB | `pricing.price_observations` | Filter: last 90 days |
| AutoMana DB | `card_catalog.card_versions` | Join on `finish`, `treatment` |
| AutoMana DB | `card_catalog.cards` | For base price (non-foil, standard art) |

**Filters:**
- Exclude cards with fewer than 5 price observations in the window
- Exclude base price < $0.50 (noise)
- Condition: NM only for comparability

---

## Key Metrics

- **Foil multiplier** = foil price / non-foil price (same card, same treatment tier)
- Median and P25/P75 multiplier per treatment type
- Coefficient of variation within each group (stability signal)
- Week-over-week delta on median multiplier

---

## Figures (4)

| # | Type | What it shows |
|---|------|---------------|
| 1 | Box plot | Foil multiplier distribution per treatment type |
| 2 | Line chart | Median foil multiplier over 12 weeks — top 4 treatments |
| 3 | Scatter | Foil price vs. non-foil price, colored by treatment |
| 4 | Sorted bar | Treatments ranked by median premium, with IQR error bars |

---

## Outline

1. **Introduction** — why foil premium matters (financial exposure, mismatched pricing), scope: all Standard-legal sets last 12 months
2. **Methodology** — how multiplier was computed, how treatments were bucketed
3. **Results** — one section per figure
4. **Discussion** — which treatments are good value, which are overpaying for aesthetics
5. **Takeaways** — 3 bullet actionable points
6. **Limitations** — cross-set confounds, supply variance by set print run

---

## Notes / Pre-writing Observations

*(fill in after running the notebook)*
