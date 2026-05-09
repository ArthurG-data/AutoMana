# MTG Finance Knowledge Base

*Compiled May 2026. Covers US, Canada, Europe, Japan, Australia/NZ markets.*

---

## Price Data Sources

### Primary Aggregators / APIs

| Name | Region | Type | API? | Notes |
|------|--------|------|------|-------|
| TCGPlayer | US (primary) | Retail market price + buylist | Yes — restricted (no new access since 2024) | Use JustTCG or TCGCSV as developer alternatives. Benchmark for US pricing. |
| CardMarket (MKM) | Europe (primary) | Retail market + buylist | Deprecated June 2024; Price Guide CSV downloadable | Not accepting new API applications. apiv2.cardmarket.com for approved partners. |
| MTGGoldfish | Global (US-centric) | Retail + buylist aggregator | No public API | Human-readable. Tracks spreads, buylist comparisons, metagame share, EV. |
| MTGStocks | Global | Price change tracker | No official API (community scrapers exist) | Free + Premium ($4.99/mo). Best spike detection. Interests page is the community's primary buyout signal. |
| MTGPrice / Trader Tools | US-centric | Retail tracker + buylist aggregator | No public API | ProTrader ($10/mo) unlocks full buylist aggregation and arbitrage tool across NA vendors. |
| Scryfall | Global | Card metadata + price snapshot | Yes — free, no key, rate-limited 10 req/s | TCGPlayer Market Price + CardMarket Trend embedded daily. Bulk JSON. Best developer API. |
| MTGJSON | Global | Card data + 90-day price history | Yes — open, bulk JSON/CSV/SQLite/PostgreSQL | Sources: CardKingdom, CardMarket, Cardsphere, TCGPlayer. Rebuilt daily. AllPrices.json + AllPricesToday.json. Best free foundation for pipelines. |
| Card Kingdom | US | Retail + buylist | No | Best US buylist especially for eternal/older cards. 30% store credit bonus. |
| Star City Games | US | Retail + buylist | No | Strong on eternal format staples; hosts major tournaments. |
| ChannelFireball | US | Retail + buylist | No | Competitive buylist; strict grading. |
| CardTrader | EU + Global | Retail marketplace | Yes — public REST at cardtrader.com/en/docs/api | Growing EU alternative to CardMarket. |
| EchoMTG | US-primary | Collection tracker + prices | Yes — echomtg.com/api | Finance-oriented collection management with email reports and trade tracking. |
| Cardsphere | Global | P2P trade/sell | No | 1% platform fee to seller; cash out at 10%. Often beats buylists. Tracked by MTGJSON as a price source. |

### Third-Party APIs and Specialized Tools

| Name | Region | Type | API? | Notes |
|------|--------|------|------|-------|
| JustTCG | US | TCGPlayer-derived retail | Yes | Condition-specific, foil pricing, bulk lookups. Best developer-friendly TCGPlayer alternative. |
| TCGCSV | US | TCGPlayer price dump | Yes (public JSON/CSV, no auth) | Free public endpoint for TCGPlayer product/price data. |
| TCGAPIs | Global | Multi-market aggregator | Yes | 80+ TCGs. Expanding to CardMarket/CardKingdom/Cardsphere. Unified schema. |
| Flipzi | EU/US | Portfolio tracker + arbitrage | No (SaaS) | Side-by-side CardMarket EUR vs TCGPlayer USD. Real last-sold data. Free tier + Founding Member plan. |
| Spellbook Finance | Global | Portfolio + arbitrage scanner | No (SaaS) | 14+ sources incl. TCGPlayer, CardKingdom, CardTrader, eBay. Transatlantic EU-to-US arbitrage scan. 10 buylist vendors. |
| TCGPriceTracker | Global | Cross-market arbitrage alerts | No (SaaS) | Tracks CardMarket, TCGPlayer, eBay simultaneously. |
| TCGSniper | US | Price drop alerts | No (SaaS) | Checks TCGPlayer and Card Kingdom multiple times/hour. Free forever tier. |
| Beat the Buylist | North America | Cross-vendor buylist comparison | No | Shows which store to sell to for max value across NA vendors. |
| MTG Collector Tools | US | Buyout detection + predictions | No (SaaS) | Tracks 35k+ cards; buyout alerts, price predictions, 23 active arbitrage opportunities. Free. |
| MTGSingles.co.nz | AU/NZ | Price comparison aggregator | No | Searches across AU/NZ game shops. |

---

## Regional Marketplaces

### United States

| Store | URL | Notes |
|-------|-----|-------|
| TCGPlayer | tcgplayer.com | Dominant US marketplace; Market Price is the US benchmark |
| Card Kingdom | cardkingdom.com | Best US buylist reliability; retail above TCGPlayer |
| Star City Games | starcitygames.com | Strong on Alpha/Beta and eternal staples |
| ABU Games | abugames.com | Strong on Reserved List; store credit 20-30% above cash equivalency |
| CoolStuffInc | coolstuffinc.com | Competitive retail; $0.99 shipping on singles |
| ChannelFireball | shop.channelfireball.com | Major retailer; strict grading on buylists |

### Canada

#### Canadian Price Aggregators

| Tool | URL | Notes |
|------|-----|-------|
| Snapcaster.ca | snapcaster.ca | Primary Canadian MTG price aggregator; indexes 80+ Canadian stores for singles prices + dedicated buylist comparison tool (closest Canadian equivalent to MTGGoldfish). Free. |
| MTGList.com | mtglist.com | Aggregates Canadian buylist prices specifically; indexes Face to Face, 401 Games, Three Kings Loot, Wizard's Tower, and others. |

#### Ontario

| Store | URL | Buylist | Notes |
|-------|-----|---------|-------|
| Face to Face Games | facetofacegames.com | buylist.facetofacegames.com | Canada's largest MTG retailer; ships nationally |
| 401 Games | store.401games.ca | buylist.401games.ca | Toronto/Vaughan |
| Wizard's Tower | store.wizardtower.com | buylist.wizardtower.com | Ottawa; daily buylist support hours |
| Magic Stronghold | magicstronghold.com | Yes | Online-focused |
| Hairy Tarantula | hairyt.com | hairyt.crystalcommerce.com/buylist | Toronto; 25% extra in store credit; mail-in accepted; large MTG inventory |
| Black Knight Games | blackknightgames.ca | blackknightgames.ca/pages/sell-your-mtg | Hamilton; cash via e-transfer; pre-submit online before shipping |
| Hobbiesville | hobbiesville.com | buylist.hobbiesville.com/retailer/buylist | Ottawa/Toronto; ships nationally and internationally |
| Chimera Gaming | chimeragamingonline.com | chimeragamingonline.com/pages/buylist | Kitchener; mail-in accepted; hot items get trade bonus |
| The Mana Lounge | manalounge.ca | manalounge.ca/blogs/selling-your-cards/online-buy-list | London, ON; 1-business-day review; mail-in or in-store |
| Waypoint Games | waypointgames.ca | Yes | Ancaster (Hamilton area); strong Commander focus; on CardTrader |
| Carta Magica Ottawa | cartamagicaottawa.com | cartamagicaottawa.com/buylist | Ottawa; shared CrystalCommerce backend with Montreal location |
| Empire Trading | empiretradings.com | empiretradings.com/pages/buylist | Ottawa (Gloucester); bulk $5/1,000 cards; hosts events |
| Meta-Games Unlimited | mguinc.com | mguinc.com/buylist/ | Online; 50–65% of TCG price in trade credit |
| GT Games | gtgames.ca | Yes | Carleton Place, ON; ships to US; large multi-TCG inventory |

#### Quebec

| Store | URL | Buylist | Notes |
|-------|-----|---------|-------|
| Three Kings Loot | threekingsloot.com | threekingsloot.com/buylist | Montreal; 30% trade bonus; cash via PayPal |
| Carta Magica Montreal | cartamagica.com | cartamagica.com/buylist | Montreal; long-established MTG specialist (10+ years) |
| The Mythic Store | themythicstore.com | themythicstore.com/pages/sell-your-cards-buylist | Quebec; pays up to 80% of selling price; 25% store credit bonus; 24h processing; free tracked shipping over $250 CAD |
| Le Coin du Jeu | lecoindujeu.ca | lecoindujeu.ca/pages/buylist | Terrebonne (north of Montreal); 25% store credit bonus |
| Game Keeper Online | gamekeeperonline.com | gamekeeperonline.com/our-buylist | Montreal; 30% more in store credit; same-day processing; usable at physical Montreal store |
| Card Brawlers | cardbrawlers.com | Yes | Montreal; free shipping over $40 CAD; hosts tournaments |
| Silver Goblin | silvergoblin.cards | Yes | Downtown Montreal; bilingual; MTG + Flesh and Blood |
| L'Imaginaire | imaginaire.com/en/magic | No prominent buylist | Large Quebec chain; free shipping from $79 in QC/ON/NB |

#### Manitoba

| Store | URL | Buylist | Notes |
|-------|-----|---------|-------|
| Fusion Gaming | fusiongamingonline.com | fusiongamingonline.com/buylist | Winnipeg; mail-in accepted; store credit never expires |
| GameKnight Games | gameknight.ca | gameknight.ca/pages/buylist | Winnipeg; in-person only (no mail-in); 25% store credit bonus |

#### Alberta

| Store | URL | Buylist | Notes |
|-------|-----|---------|-------|
| Taps Games | tapsgames.com | tapsgames.com/pages/buy-list | Edmonton; WPN Premium store; prices guaranteed 4 days |
| Sentry Box Cards | sentryboxcards.com | sentryboxcards.com/buylist | Calgary; premier Western Canada retailer; ships nationally; two weekly Pioneer tournaments |

#### British Columbia

| Store | URL | Buylist | Notes |
|-------|-----|---------|-------|
| Gauntlet Games Victoria | gauntletgamesvictoria.ca | gauntletgamesvictoria.ca/buylist/magic_singles/8 | Victoria; birthplace of Canadian Highlander format (1999); top dollar for MTG singles |

#### Atlantic Canada

| Store | URL | Buylist | Notes |
|-------|-----|---------|-------|
| The Comic Hunter | comichunter.net | comichunter.net/buylist/multi_search | Moncton + Fredericton, NB; serves Atlantic Canada; store credit never expires |
| Vortex Games | vortexgames.ca | vortexgames.ca/pages/buylist-instructions | Sackville, NB; cash via PayPal or store credit |

#### Online-Only / National

| Store | URL | Buylist | Notes |
|-------|-----|---------|-------|
| Magic Market Canada | magicmarketcanada.com | No public buylist | Family-run; free shipping over $200 CAD; frequently cited as competitively priced |
| MTG North | mtgnorth.ca | mtgnorth.ca/buylist | 20% store credit bonus over cash; online only |

#### Canadian Market Dynamics

**2025 Tariff (critical):** As of March 13, 2025, Canada imposed a **25% counter-tariff on playing cards** as part of the US-Canada trade war. This applies to sealed TCG product crossing from the US into Canada, directly raising costs for sealed product at Canadian retailers. Singles in envelopes are less directly affected but carry increased customs inspection risk.

**CAD/USD pricing conventions:**
- Sealed product: Canadian stores typically price 25–30% above USD retail (exchange rate + distributor costs), compounded by the 2025 tariff
- Singles: Most stores price in CAD at 1.3–1.5x the TCGPlayer USD market price; Canadian stores lag in adjusting to US price spikes
- Premium foils: Canadian foil prices frequently run 1.5–2x the equivalent US price (especially older foils from Time Spiral Remastered, Masters sets) — historically creates cross-border arbitrage at GP/event vendor halls
- Store credit bonuses of 20–30% over cash are the industry norm

**Canadian Highlander:** 100-card singleton 1v1 format originated in Victoria, BC (1999). Points system allows up to 10 points for restricted-list cards. Creates niche Canadian demand for Power Nine and dual lands beyond Legacy/Vintage. Official site: canadianhighlander.ca

**TCGPlayer and Canada:** TCGPlayer does not ship to Canada from most sellers. Canadians use package-forwarding services (longstanding workaround). Cardsphere and Deckbox are the cleanest cross-border P2P trading mechanisms (card-for-card trades avoid customs treatment).

**Canadian Community:**
- r/CanadianGamingSales — primary Canadian gaming subreddit for P2P transactions; reputation/flair system
- Facebook: "MTG Buy Sell Trade Canada Only" (facebook.com/groups/657130297692602) — national P2P; Interac e-transfer dominant
- Facebook: "MTG Canadian Highlander: There Can Be Only One" (facebook.com/groups/288447914624649)
- Canadian Highlander Discord — canadianhighlander.ca — active tournament org and weekly events

### Europe

| Store/Platform | URL | Notes |
|-------|-----|-------|
| CardMarket | cardmarket.com/en/Magic | Dominant EU marketplace; 30+ countries, 2M+ buyers; 5% commission; EUR pricing |
| Three for One Trading | threeforonetrading.com/en | "Europe's leading Magic cards trader"; professional buylist |
| CardTrader | cardtrader.com | Pan-EU alternative; has public API |
| MagicMadhouse | magicmadhouse.co.uk | UK-based retailer |

### Japan / Asia-Pacific

| Store | URL | Notes |
|-------|-----|-------|
| Hareruya | hareruyamtg.com/en | Largest MTG store in Japan; 41 stores; ships internationally; competitive on staples buylist |
| Grey Ogre Games | greyogregames.com | Singapore-based; buylist service available |
| MTG Mint Card | mtgmintcard.com | Hong Kong-based; ships to EU; has buylist |

### Australia / New Zealand

| Store | URL | Notes |
|-------|-----|-------|
| Good Games TCG | tcg.goodgames.com.au | Australia's largest TCG chain; physical + online |
| MTG Mate | mtgmate.com.au | AU-based; fast domestic shipping |
| Ozzie Collectables | ozziecollectables.com | Singles and sealed |
| Gameology | gameology.com.au | Broad TCG retailer |
| MTGSingles.co.nz | mtgsingles.co.nz | NZ price comparison aggregator |
| Trade Magic | trademagic.com.au | AU peer-to-peer trading platform |

---

## Community & Media Sources

### Subreddits

| Subreddit | Focus |
|-----------|-------|
| r/mtgfinance | Primary finance community; Wednesday AMA threads; spreadsheet/scraper sharing |
| r/magicTCG | General MTG; large audience; spikes often surface here first |
| r/EDH | Commander demand side; heavily influences card prices |
| r/CompetitiveEDH | High-power Commander; staple demand signals |

### Podcasts

| Podcast | Notes |
|---------|-------|
| Brainstorm Brewery | Biweekly; oldest MTG finance podcast; covers speculation, buylist, Commander |
| MTG Fast Finance | Biweekly; meta analysis, fast movers; produced via MTGPrice; James Chillcott + Cliff Daigle |
| Quiet Speculation Podcast | Irregular; paired with Insider subscription |

### YouTube (Finance-Focused)

| Channel | Focus |
|---------|-------|
| Alpha Investments (Rudy) | Sealed product, Reserved List, long-term; large & influential audience |
| Jake and Joel are Magic | Singles speculation, weekly price movement rundowns |
| MTG Mox Man | Short-term speculation; near "day trading" style |
| MTGStocks TV | Official MTGStocks market trends channel |
| Tolarian Community College | Broad MTG; product reviews drive buy/sell signals; #1 MTG channel globally |
| The Command Zone | Commander deck techs drive weekly price spikes |
| MTGGoldfish (YouTube) | Budget brews + weekly meta reports |
| EDHREC | Most-added cards list is a spike-prediction signal |

### Discord Servers

| Server | Notes |
|--------|-------|
| MTG Marketplace | 10,000+ members; buy/sell/trade |
| MTGPrice Pro Trader | Via subscription; fastest signal delivery |
| Quiet Speculation Insider | Via QS subscription; serious speculation community |
| EchoMTG Discord | Meta and finance discussion |

### Blogs & Written Content

| Source | URL | Notes |
|--------|-----|-------|
| Quiet Speculation | quietspeculation.com | Oldest MTG finance site; Insider paywall for premium |
| MTGPrice Blog | blog.mtgprice.com | Free articles; finance strategy |
| Cardsphere Blog | blog.cardsphere.com | Trading and selling focus |
| Draftsim MTG Finance Guide | draftsim.com/mtg-finance | Comprehensive free guide |
| TCGPlayer Infinite | infinite.tcgplayer.com | Finance articles |
| MTGRocks | mtgrocks.com | Finance news and price movement |

---

## MTG Finance Strategies

### 1. Speculation (Long Positions)
Buy underpriced cards expected to rise from format shifts, Commander adoption, or supply constraints. Sell into the spike, not after plateau. Typical hold: 3–24 months. Best targets: high casual/Commander ceiling, old low-print-run sets, synergy pieces adjacent to powerful new cards.

### 2. Buylist Arbitrage
Buy retail below another vendor's buylist price. Spread = buylist price − retail price. Near-zero or negative spread = trigger. Workflow: MTGPrice Trader Tools or MTGGoldfish buylist comparison → buy on TCGPlayer → sell to Card Kingdom (best US buylist) or SCG. Card Kingdom offers 30% store credit bonus.

### 3. Cross-Regional Arbitrage (EU-to-US)
Commander cards significantly cheaper on CardMarket EU than TCGPlayer US. Buy in EU → ship to US → sell on TCGPlayer or to a US buylist. Optimal: EUR/USD below 1.10; gap > 15% post-fees; card is Commander-only (Standard/Modern staples equalize faster). Requires EU forwarding address.

Tools: Flipzi, Spellbook Finance, TCGPriceTracker.

### 4. Reserved List Speculation
Cards on Wizards' Reserved List cannot be reprinted. Fixed supply + growing player base = long-term appreciation. Buy during market dips (post-buyout correction, summer slowdown). Risk: coordinated buyouts can create artificial spikes that correct.

### 5. Reprint Risk Analysis
Non-RL cards face reprint risk from Masters sets, Bonus Sheets, Commander precons, Secret Lairs. Reprint risk score factors: retail price, Commander/casual demand, reprint frequency, RL status. Mitigation: maintain high-velocity inventory; avoid large positions in expensive, eligible non-RL cards.

### 6. Set Release Cycle Timing
- Spoiler/pre-release: Peak prices for new cards — sell hype here
- Weeks 2–8 post-release: Supply saturates; most new card prices fall 20–60% — buy window
- 3–6 months pre-rotation: Standard-only staples decline — sell or avoid
- Post-rotation floor: Buy eternal/Commander staples at cheapest
- Reprint spoiler: Affected card craters immediately — sell on first hint

### 7. Ban/Unban Speculation
Highest-volatility events. Unban plays: pre-buy candidates discussed as unban targets. 2025 examples: Panoptic Mirror $15 → $50+; Braids, Cabal Minion +1000%. Ban plays: identify likely bans; sell into strength before confirmation.

### 8. Commander Spike (Content Creator Pickup)
A prominent Commander YouTuber/streamer features a card → price spikes within 24–72 hours. Monitor Tolarian, Command Zone, EDHRec "most added this week." Maintain watchlist of cheap, high-potential Commander cards with low stock.

### 9. Premium Treatment / Foil Arbitrage
Modern sets have Extended Art, Borderless, Showcase, Serialized, Surge Foil, Halo Foil, Japanese Alt Art SKUs. Each has independent scarcity and price.

Reference multipliers:
- Foil: 1.5–3x non-foil
- Extended Art: ~1.8–2.5x regular
- Foil Extended Art (FEA) mythic: ~0.825% collector booster drop rate — very scarce
- Japanese showcase foils: large global premiums; source from Hareruya directly

### 10. MTGO-to-Paper Redemption Arbitrage
Assemble a complete digital MTGO set and redeem for paper. MTGO prices often below paper. Requires capital, patience, and understanding of redemption cutoff dates. Less common as redemption windows have tightened.

### 11. CAD/USD Swing (Canada Arbitrage)
When CAD weakens (>1.40 USD/CAD), Face to Face Games and 401 Games CAD-denominated buylists effectively offer USD sellers a premium. Monitor the exchange rate.

---

## Key Trend Signals to Monitor

### Tier 1 — Act within 24–48 hours

| Signal | Source | Action |
|--------|--------|--------|
| Ban/Unban announcement | Wizards official site, Commander RC | Pre-buy unban candidates 1–7 days pre-announcement; sell banned cards immediately |
| Content creator card pickup | Tolarian, Command Zone, EDHRec weekly | Buy before full view count materializes; sell into spike |
| TCGPlayer buyout detected | MTG Collector Tools, MTGStocks | Buy immediately or hold if already positioned |
| MTGStocks weekly Interests | mtgstocks.com/news | Confirmation spike in motion; assess remaining upside |

### Tier 2 — Days to Weeks

| Signal | Source | Action |
|--------|--------|--------|
| Set spoiler reveals | Magic official site, social | Buy synergy/enabler cards before headline card peaks |
| Major tournament results | MTGTop8, SCG/RC coverage | Buy 4-of staples in winning deck immediately post-event |
| CardMarket vs TCGPlayer spread | Flipzi, Spellbook Finance | >15% gap = EU arbitrage candidate |
| Format rotation calendar | Wizards schedule | 3 months out: sell Standard-only staples; buy eternal staples near floor |
| EDHREC "top added commanders" | edhrec.com | New popular Commander drives synergy card prices within 1–2 weeks |
| Reprint set spoiler | Magic official site | Sell affected cards on first hint; buy after dust settles |

### Tier 3 — Structural (Weeks to Months)

| Signal | Source | Action |
|--------|--------|--------|
| Reserved List policy statements | Wizards announcements | Any RL mention = immediate RL card price reaction |
| EUR/USD, JPY/USD, AUD/USD exchange rates | Financial data feeds | EUR/USD <1.10 = EU arbitrage window opens |
| Print run sell-through speed | Vendor stock levels, community reports | Fast sellout = limited print run; long-term supply constraint |
| Sealed product EV vs MSRP | MTGGoldfish sealed EV, Spellbook Finance | EV > MSRP = buy sealed; EV < MSRP = sell singles early |
| Foil multiplier drift | MTGJSON price data, Scryfall | Expanding multiplier = foil demand growing; contracting = correction |
| MTGGoldfish daily movers | mtggoldfish.com/movers | Confirmation signal; rarely early but useful for trend validation |

---

## Cross-Regional Arbitrage — Patterns and Methods

### Pattern 1: EU (CardMarket) → US (TCGPlayer)
**Why it works**: Commander dramatically more popular in US. Commander staples consistently 15–40% cheaper on CardMarket EU. EUR/USD differential amplifies the gap.

**Optimal conditions**: EUR/USD below 1.10; gap > 15% post-fees; Commander/casual-demand card only; new set release weeks 1–6.

**Logistics**: CardMarket requires a European address. Use EU forwarding/reshipping service. Model: CardMarket seller fees (5–9%) + EU shipping + reshipping + international postage + TCGPlayer seller fees (10–15%).

**Tools**: Flipzi, Spellbook Finance, TCGPriceTracker.

### Pattern 2: Japan (Hareruya) → US/EU
**Why it works**: Japanese alternate art, serialized, and special-frame cards often cheaper at Japanese source than international resale. JPY weakness in 2024–2025 amplified this.

**Optimal conditions**: JPY weak vs USD/EUR; Japanese-exclusive showcase foils or serialized cards in stock; gap > 20% after international shipping.

**Logistics**: Hareruya ships internationally; English-language site. EMS or DHL; 1–2 week transit.

### Pattern 3: US → Australia (Supply Arbitrage)
US-sourced singles (TCGPlayer) + shipping to AU buyers at AUD premium (50–80% above USD equivalent). Viable for higher-value singles where shipping cost is proportionally small.

### Pattern 4: Canada (CAD/USD Swing)
When CAD weakens sharply against USD (>1.40 CAD/USD), Face to Face Games and 401 Games CAD buylists effectively pay USD sellers a premium. Monitor the exchange rate.

---

## AutoMana Integration Recommendations

### Priority Data Sources for Pipeline

1. **MTGJSON** (AllPricesToday.json + AllPrices.json) — free, daily rebuild, covers CardKingdom/CardMarket/Cardsphere/TCGPlayer retail and buylist with 90-day history. Best free machine-readable foundation.
2. **Scryfall bulk data** — already integrated; card metadata + TCGPlayer/CardMarket price snapshots
3. **TCGCSV or JustTCG** — real-time US retail pricing without TCGPlayer API restrictions
4. **CardMarket Price Guide CSV** — EU pricing layer; requires authentication
5. **MTGStocks signals** — buyout detection and spike early warning

### Price Signals to Surface in Analytics Layer

| Signal | Formula | Threshold |
|--------|---------|-----------|
| Buylist spread | `lowest_buylist / lowest_retail` | Values approaching 1.0 = arbitrage trigger |
| Foil multiplier | `foil_price / non_foil_price` | Compare to set median; outliers = opportunity |
| Cross-regional spread | `(TCGPlayer_USD - CardMarket_EUR × FX_rate) / TCGPlayer_USD` | > 15% = EU arbitrage candidate |
| Buyout alert | Copies at lowest price tier dropping to zero faster than replenishment rate | Spike incoming |
| Reprint risk score | RL status + reprint count last 5 years + retail price tier + set age | Higher = more risk |

---

## Pre-2012 Historical Price Data

*Researched May 2026. The pre-2012 gap is real and severe — no single clean, machine-readable, comprehensive paper card price dataset exists from before 2012.*

### Era Breakdown

| Era | State of price data |
|-----|-------------------|
| 1993–1999 (pre-internet) | Print media only (Scrye, InQuest magazines). Partially scanned on archive.org. Not structured data. |
| 2000–2009 (early internet) | Retail sites (SCG, MagicTraders, CrystalKeep) had prices. No systematic aggregator archived them. Ark42.com began scraping SCG around 2009. |
| 2010–2012 (bridge era) | MTGPrice.com launched November 2011. MTGStocks launched Spring 2012. MTGGoldfish paper data starts January 19, 2013. |

### Source-by-Source Floors

| Source | Earliest Paper Data | Pre-2012? | Format | Free? | Notes |
|--------|-------------------|-----------|--------|-------|-------|
| MTGGoldfish | Jan 19, 2013 | No | Charts + Premium CSV | Mostly | Pre-2013 data is MTGO Supernovabots only |
| MTGPrice.com | Nov 2011 | Barely | Charts | Partly | ProTrader for full history |
| MTGStocks | Spring 2012 | No | Charts | Partly | Launched ~March 2012 |
| Kaggle MTG dataset | May 2012 | No | CSV | Free | Derived from MTGPrice.com |
| MTGJSON | 90-day rolling | No | JSON/CSV | Free | No historical depth |
| TCGPlayer | ~2010 (internal) | No (public) | API restricted | Partly | Data not exposed before ~2014 |
| **SvenskaMagic.com** | **~2005** | **Yes** | Web charts (SEK) | Free | The only live site with pre-2012 paper price charts. Swedish language, SEK currency. Covers all major sets. URL: svenskamagic.com — navigate via "Prishistorik". Requires scraping + FX conversion. |
| **PriceCharting.com** | **~2010 (MTG)** | **Partially** | Charts + paid CSV | Free browse | eBay hammer prices (actual sales, not list prices). Best for high-value vintage cards (Power 9, duals). Monthly CSV export available per set at paid tier. |
| ark42.com | ~2009 | Yes (DEFUNCT) | Web charts | Was free | Scraped SCG prices. Site shut down ~2013. Data effectively lost unless owner preserved dumps. Wayback Machine captures at `web.archive.org/web/*/ark42.com/mtg/` |
| Wayback Machine (SCG) | ~1999–2000 | Yes | HTML snapshots | Free | Star City Games has been online since ~1999. Thousands of individual card pages. No bulk export — requires crawling. Use `web.archive.org` CDX API to enumerate captured URLs. |
| PSA Auction Prices | ~2003 | Yes | Web (graded only) | Free | Real auction hammer prices. Covers Power 9 and Alpha/Beta staples. Thin coverage for non-vintage cards. URL: psacard.com/auctionprices |

### Print Magazine Archives (Require OCR)

These are the only sources for systematic pre-internet MTG prices. Both are on archive.org as PDF/image scans — not machine-readable without OCR.

| Magazine | Run | Coverage | archive.org |
|----------|-----|----------|-------------|
| **Scrye** | June 1994 – April 2009 | Monthly Low/Mid/High for every card in every set. Was the de facto US price standard at game stores. | Confirmed issues: #1, #4, #7, #8, #52, #58, #68. Partial digitization. Full index at magiclibrarities.net |
| **InQuest / InQuest Gamer** | May 1995 – 2007 | Similar monthly price guide. Competitor to Scrye. | Confirmed issues: #1, #6, #9, #17, #33, #40, #41, #65. Partial collection (20 issues 1995-2006) at archive.org/details/IQ.Gamer.Partial.Collection |
| **Beckett Magic** | ~2000+ | Graded + ungraded price guides | Partial archive; some on archive.org |

Key reference: MTGInformation.com digitized the Scrye #9 (Sept 1995) top-40 price list at `mtginformation.com/1995-scrye-prices`.

### MTGO Pre-2012

- **Supernovabots** (defunct) was an MTGO bot network that tracked digital card prices. MTGGoldfish absorbed their data but does not expose it as a raw download. The network was active by at least September 2011.
- **GoatBots** (goatbots.com/card/tracker) tracks MTGO prices with a multi-year chart window but no bulk historical export.
- MTGO price archives before 2013 are effectively inaccessible in public structured form.

### Recommendation for AutoMana

**Treat 2012 as the practical start date for automated historical price ingestion.**

- For 2012-present: MTGPrice.com, MTGGoldfish (paper from Jan 2013), MTGStocks are the reliable automated sources.
- For 2009–2012: Only SvenskaMagic.com (SEK, scrapeable) and Wayback Machine captures of ark42.com are candidates. High effort for partial coverage.
- For 2003–2009 (vintage/Power 9 only): PriceCharting.com (eBay actuals) and PSA auction records provide real transaction prices for high-value cards.
- For pre-2010 all-card coverage: Scrye/InQuest OCR is the only path. Significant engineering effort; data would be monthly, image-derived, US retail Mid price.

If pre-2012 data points ever appear in the DB (e.g., from manual entry or a future OCR project), annotate them with `source: "scrye_scan"` or `source: "wayback_scg"` and a lower confidence flag. Do not architect the AutoMana pricing pipeline expecting a clean pre-2012 dataset.
