# MTG Cards as a Financial Asset Class: Quantitative Research Landscape

**Compiled:** 2026-05-24  
**Purpose:** Background research for AutoMana's quantitative analytics layer — understanding the academic and practitioner state of the art before building systematic MTG portfolio tools.

---

## 1. Existing Academic Research

The academic literature is sparse but growing across three categories: student theses, working papers, and one peer-reviewed journal article.

### Peer-Reviewed

**Langelett & Wang (2023)** — *Global Journal of Accounting and Finance, Vol. 7 No. 1*  
The most rigorous published study to date. Analyzed sealed booster boxes across 109 product releases, reporting ~21% annual returns with low cross-asset correlations suggesting diversification utility. Flags illiquidity and high price volatility as practical barriers.  
→ `papers/langelett-wang-2023.pdf`

### Working Papers / Theses

**Harsanyi (2023)** — *Claremont McKenna College thesis*  
OLS regression of card characteristics (rarity, print run, tournament legality) against market price. Full text access-restricted; methodology confirmed from abstract.  
→ `papers/harsanyi-2023.pdf`

**Weber (2021)** — *IU International University of Applied Sciences, EconStor working paper*  
Descriptive market study of the MTG secondary market, examining price development and investment viability.  
→ `papers/weber-2021.pdf`

**Gasser (2022)** — *University of Graz dissertation*  
Economic sociology framing: MTG cards through community dynamics and price formation as tension between community value and market commoditization. Primarily sociological, not econometric.  
→ `papers/gasser-2022.pdf`

**Hilbert (2024)** — *College of Wooster: "Playground to Portfolio"*  
OLS on sports and Pokémon card sales data (PriceCharting, Jan 2021–Dec 2023) testing whether collectible card returns beat the S&P 500 and a bond index. Methodology is directly applicable to MTG singles.  
→ `papers/hilbert-2024.pdf`

### ML Practitioner Papers (Stanford CS229)

**Pawlicki, Polin & Zhang (2014)**  
Used MTGtop8.com tournament data + MTGprice.com price history to predict card price spikes via classification. Widely cited in the practitioner community.  
→ `papers/pawlicki-polin-zhang-2014.pdf`

**Stanford CS229 (2015)** — *"Financial Magic"*  
Framed MTG cards explicitly as stocks and applied supervised learning to price forecasting.  
→ `papers/stanford-cs229-2015.pdf`

### Key Gap
No paper has applied the standard collectible-asset methodology — repeat-sales indices (Case-Shiller style, as used for art via Mei-Moses and for wine in Dimson et al., JFE 2015) — to MTG singles. **This is the most important open methodological gap.**

---

## 2. Asset Class Characteristics

MTG cards share structural features with passion investments (art, wine, stamps, watches) but differ in several critical dimensions:

| Feature | MTG Cards | Equities | Art / Wine |
|---|---|---|---|
| Return distribution | Fat-tailed, right-skewed | Near-normal | Fat-tailed |
| Liquidity | Format-dependent | High | Very low |
| Maturity | Rotation ~24 months (Standard) / evergreen (Commander) | None | None |
| Condition sensitivity | Yes (NM/LP/MP/SP) | No | Yes (provenance) |
| Reprint risk | High, schedule-dependent | No analog | Low |

**Key comparisons:**
- A small fraction of cards (Reserve List power cards, key staples) account for most total market cap appreciation. Return distribution is highly right-skewed.
- Art Sharpe ratio estimated at 0.04 vs. 0.30 for U.S. equities over the same period (Goetzmann et al., NBER WP 9116).
- Fine wine: 4.1% real annual return over 1900–2012 (Dimson, Rousseau & Spaenjers, JFE 2015).
- "Emotional yield" sacrifice of ~2.6% is the sobering benchmark for passion assets (FAJ).
- TCGPlayer Market Price (median of recent completed sales) is the most manipulation-resistant price signal; the older TCG Median (listing-based) was susceptible to price manipulation.

---

## 3. Quantitative Frameworks Applicable to MTG

### 3.1 Factor Models

A coherent factor structure has been outlined by practitioners but never formally estimated in a published paper. The candidate factors:

| Factor | Mechanism | Evidence |
|---|---|---|
| Format legality | Each format defines a demand regime; rotation = scheduled demand destruction | Qualitative consensus |
| Reprint risk | Supply shock suppresses price | Mota (MathGathering Substack): −14.7% in 3-day announcement window, −40.2% cumulative by day 30, supply elasticity ≈ −0.57 for mythic rares |
| Print run size | More supply = lower price | MTG Salvation community OLS: 100% increase in print run → ~88% price reduction; explains ~40% of price variance |
| Tournament appearance rate | Demand driven by competitive play | Pawlicki et al. (2014): statistically significant predictor |
| EDHREC centrality | Commander demand is evergreen | Qualitative — no quantitative study yet |

### 3.2 Portfolio Optimization

Standard Markowitz mean-variance optimization is problematic given fat-tailed, illiquid, and skewed return distributions. Better alternatives:

- **CVaR (Conditional Value-at-Risk) optimization** — appropriate for downside management in fat-tailed distributions
- **Black-Litterman framework** — for incorporating format metagame conviction views as prior beliefs
- **Kelly criterion** — for speculative position sizing when win probabilities can be estimated

No published paper has applied any of these to MTG portfolios.

### 3.3 Time-Series Modeling

GARCH-family models for volatility estimation are a natural fit given clear heteroskedasticity around:
- Ban/unban announcements
- Reprint reveal events
- Large tournament results (PT/GP top 8 appearances)

Existing GitHub projects (unrefereed):
- `njhofmann/mtg-analysis` — time-series analysis of competitive play rates and card prices
- `Tsukalos/MTG-price-predictor` — 50 weeks of TCGPlayer history + Scryfall features in a neural network
- `MTGForecasting` (ChrisWeldon) — forecasting models applied to price series

### 3.4 Network / Graph Approaches

**EDHREC** uses a lift metric (probability of co-occurrence / product of individual rates) to score Commander synergies — the largest published card graph in MTG. **Lucky Paper** has produced network maps of the card landscape.

**Unexplored application:** connecting synergy-graph betweenness centrality to price resilience. Cards that are "hubs" across many archetypes should show more stable demand floors — analogous to stocks that are held by many institutional portfolios.

---

## 4. Data Availability

| Source | Coverage | Frequency | Key Limitation |
|---|---|---|---|
| TCGPlayer Market Price | US marketplace, all conditions, NM-foil split | Daily (current), historical sold | Full historical depth restricted behind commercial API tier |
| Cardmarket (EU) | EU marketplace, language/condition variants | Daily (trend/30d avg) | Currency baseline differs; spread from TCGPlayer creates arbitrage noise |
| MTGGoldfish Indices | Per-format aggregate indices (Standard, Modern, Legacy) | Daily | Index composition changes with rotation/bans; no published methodology for weighting |
| MTGStocks | Price alerts, spike tracking, historical charts | Daily | No public API; scraped informally |
| Scryfall / MTGJSON | Card metadata, oracle text, legality, set data | On-release update | No price data |
| AllPrintings.json (MTGJSON) | Complete reprint history | Versioned releases | Required for reprint-event identification |

**Critical quality issues:**
1. **Survivorship bias** — price trackers drop cards with zero sales activity; thin aftermarkets underrepresented.
2. **Condition conflation** — most indices report NM pricing only, ignoring played-condition market volume.
3. **TCGPlayer buylist sunset (July 2024)** — eliminated the cleanest observable bid-side liquidity signal.

---

## 5. Key Practitioners and Communities

| Name | URL | Notes |
|---|---|---|
| **MathGathering Substack** (Arthur Mota) | https://mathgathering.substack.com | Most quantitatively rigorous public practitioner work: event studies, regression, supply elasticity |
| **Quiet Speculation** | https://www.quietspeculation.com | Longest-running MTG finance publication (since 2009), Trader Tools database, insider analysis |
| **Spellbook Finance** | https://spellbook-finance.com | Real-time cross-market spread aggregation, sealed EV calculations, S&P 500 benchmarking |
| **MTGPrice Blog** | https://blog.mtgprice.com | Buylist arbitrage focus; practitioner-level analysis |
| **r/mtgfinance** | https://www.reddit.com/r/mtgfinance | Largest community by volume; variable quality — good for detecting emerging price narratives |
| **Lucky Paper** | https://luckypaper.co | Network maps of the card landscape, analytical articles |
| **EDHREC** | https://edhrec.com | Commander synergy lift scores — the largest published card graph in MTG |

---

## 6. Open Research Gaps (Priority for AutoMana)

These are the most important unanswered questions for a systematic MTG collection management platform:

### Gap 1: No Repeat-Sales Price Index
The standard methodology for thinly-traded collectibles (Case-Shiller, Mei-Moses for art) has never been applied to MTG singles. AutoMana holds transaction history + price observations that could construct **the first repeat-sales price index for MTG singles**. This would enable true risk-adjusted return estimation.

### Gap 2: Illiquidity Premium Unmeasured
The bid-ask spread between TCGPlayer market price and Card Kingdom buylist represents an observable illiquidity cost. A time series of this spread per card, segmented by format legality and price tier, has never been analyzed systematically. AutoMana's buylist ingestion is the input.

### Gap 3: No Multi-Factor Model Estimated
The qualitative factor list (format legality, reprint risk, print run, tournament frequency, EDHREC rank) exists but no paper has estimated factor loadings or orthogonalized the factors. A simple OLS or PCA on AutoMana's card+price dataset would be the first published result.

### Gap 4: Reprint Announcement Drift
The pre-announcement −8.3% drift (per Mota) suggests information leakage or sentiment front-running — testable with a proper event study using MTGJSON reprint dates cross-referenced against price series. AutoMana's combination of reprint history and daily price observations makes this directly executable.

### Gap 5: Format-Specific Duration Matching
Commander staples are "perpetuity-like" (evergreen demand); Standard-legal cards have a known maturity date (rotation). A duration-immunization framework analogous to bond portfolio management — matching collection "cash flows" to holder time horizon — has not been formalized.

### Gap 6: Wishlist as Leading Demand Signal
User wishlist data (including AutoMana's `is_wishlist` column added in migration_50) represents an observable leading indicator of demand, analogous to options open interest in equities. No practitioner has published a systematic study of wishlist-to-price-spike lead times. AutoMana is uniquely positioned to measure this.

---

## 7. Recommended First Studies for AutoMana

Ordered by data availability vs. research novelty:

1. **Repeat-sales index** — AutoMana has the price history; methodology is established (Case-Shiller). High novelty, available data.
2. **Illiquidity premium time series** — requires buylist + market price. Medium novelty, data partially available.
3. **Reprint event study** — MTGJSON reprint dates + AutoMana price observations. Medium novelty, data available.
4. **Wishlist lead-time analysis** — requires collecting wishlist snapshots over time first. High novelty, data not yet accumulated.
5. **Multi-factor OLS** — simple regression on existing card metadata + price. Low novelty relative to practitioner work, but first peer-replicable version.

---

## References

| Paper | File |
|---|---|
| Langelett & Wang (2023), GJAF Vol. 7 No. 1 | `papers/langelett-wang-2023.pdf` |
| Harsanyi (2023), CMC Thesis | `papers/harsanyi-2023.pdf` |
| Weber (2021), IU Working Paper | `papers/weber-2021.pdf` |
| Gasser (2022), U. Graz Dissertation | `papers/gasser-2022.pdf` |
| Hilbert (2024), College of Wooster | `papers/hilbert-2024.pdf` |
| Pawlicki, Polin & Zhang (2014), Stanford CS229 | `papers/pawlicki-polin-zhang-2014.pdf` |
| Stanford CS229 (2015), "Financial Magic" | `papers/stanford-cs229-2015.pdf` |
| Dimson, Rousseau & Spaenjers (2015), JFE | `papers/dimson-rousseau-spaenjers-2015-wine.pdf` |
| Goetzmann et al. (2002), NBER WP 9116 | `papers/goetzmann-2002-art-sharpe.pdf` |
| Mota, MathGathering Substack — Reprint Math | https://mathgathering.substack.com/p/the-math-behind-mtg-reprints-and |

---

*Last updated: 2026-05-24*
