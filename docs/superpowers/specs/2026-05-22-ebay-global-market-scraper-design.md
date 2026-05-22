# eBay Global Market Scraper — Design Spec

**Date:** 2026-05-22
**Status:** Approved

---

## Goal

Build a nightly pipeline that scrapes sold MTG card prices from three eBay marketplaces
(US, AU, CA) in their native currencies (USD, AUD, CAD), stores raw prices with full
condition/finish/frame enrichment, and normalises to USD at query time via daily FX rates.

Primary use case: cross-regional MTG finance analytics and arbitrage detection.

---

## Scope

- **Cards targeted:** mythic, rare, special rarity, and `is_promo = true` cards with a
  current market value ≥ $1.00 USD, managed via a configurable watchlist table.
- **eBay marketplaces:** `EBAY-US` (USD), `EBAY-AU` (AUD), `EBAY-ENCA` (CAD).
- **No user OAuth required:** the Finding API uses only the App ID (`settings.ebay_app_id`).
  This pipeline is fully independent of any user having a connected eBay account.
- **Out of scope:** re-scraping all cards in the catalog, per-user listing scope, real-time
  price alerts, currency conversion at ingest time.

---

## Architecture Overview

```
[06:45 AEST] integrations.pricing.fetch_fx_rates
    └─► GET frankfurter.app/latest?from=USD&to=AUD,CAD
    └─► upsert pricing.fx_rates (today, AUD→USD, CAD→USD)

[07:00 AEST] integrations.ebay.refresh_scrape_targets
    └─► INSERT rare/mythic/promo cards where sell_avg_cents >= 100
        INTO pricing.ebay_scrape_targets ON CONFLICT DO UPDATE is_active=true

[07:15 AEST] integrations.ebay.scrape_global_market
    └─► for each card_version_id in ebay_scrape_targets (is_active=true):
          ensure_product(card_version_id)        ← guarantees product_ref + mtg_card_products
          ensure_source_product(card_version_id, source_id=5)
          for each marketplace in [EBAY-US, EBAY-AU, EBAY-ENCA]:
              find_completed_items(keywords, global_id=marketplace)
              score + validate + parse each result
              INSERT INTO pricing.ebay_scraped_sold ON CONFLICT DO NOTHING

[08:00 AEST] integrations.ebay.promote_sold_obs  (existing, shared)
    └─► GROUP BY (source_product_id, date, finish_id, condition_id, language_id)
    └─► upsert → pricing.price_observation
```

---

## DB Schema Changes

### New table: `pricing.ebay_scrape_targets`

Watchlist of card versions to scrape. One row per `card_version_id`. Auto-populated
nightly; manual rows can also be inserted (`added_by = 'manual'`).

```sql
CREATE TABLE pricing.ebay_scrape_targets (
    card_version_id  UUID         PRIMARY KEY
        REFERENCES card_catalog.card_version(card_version_id),
    added_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    last_scraped_at  TIMESTAMPTZ,
    is_active        BOOLEAN      NOT NULL DEFAULT true,
    added_by         TEXT         NOT NULL DEFAULT 'auto'  -- 'auto' | 'manual'
);
```

### New column: `pricing.ebay_scraped_sold.marketplace_id`

`currency` alone is ambiguous (CAD transactions appear on ebay.com). `marketplace_id`
pins every row to its source market.

```sql
ALTER TABLE pricing.ebay_scraped_sold
    ADD COLUMN marketplace_id VARCHAR(20) NOT NULL DEFAULT 'EBAY-US';
```

### New table: `pricing.fx_rates`

One row per currency pair per day. Only AUD and CAD are fetched; USD is the base.

```sql
CREATE TABLE pricing.fx_rates (
    rate_date      DATE          NOT NULL,
    from_currency  VARCHAR(3)    NOT NULL,
    to_currency    VARCHAR(3)    NOT NULL DEFAULT 'USD',
    rate           NUMERIC(12,6) NOT NULL,
    fetched_at     TIMESTAMPTZ   NOT NULL DEFAULT now(),
    PRIMARY KEY (rate_date, from_currency, to_currency)
);
```

All three changes ship in a single migration file:
`database/SQL/migrations/migration_XX_ebay_global_market_scraper.sql`

Grants: `SELECT, INSERT, UPDATE` on new tables to `app_backend`, `app_celery`.

---

## New Pipelines

### `integrations.pricing.fetch_fx_rates`

**Trigger:** `run_service`, 06:45 AEST  
**Repos:** `fx_rates` (DB only)  
**Logic:**

1. `GET https://api.frankfurter.app/latest?from=USD&to=AUD,CAD`
2. Parse response: `{"rates": {"AUD": 1.58, "CAD": 1.36}}`
3. For each currency, upsert into `pricing.fx_rates`:
   - `(today, 'AUD', 'USD', 1/rate)` — store AUD→USD (inverse of USD→AUD)
   - `(today, 'CAD', 'USD', 1/rate)`

Uses a plain `httpx.AsyncClient` (no auth). On failure, logs and returns — analytics
queries use `LEFT JOIN fx_rates` so a missing rate degrades gracefully to native price.

---

### `integrations.ebay.refresh_scrape_targets`

**Trigger:** `run_service`, 07:00 AEST  
**Repos:** `card`, `pricing` (DB only)  
**Logic:**

```sql
INSERT INTO pricing.ebay_scrape_targets (card_version_id, added_by)
SELECT cv.card_version_id, 'auto'
FROM card_catalog.v_card_versions_complete cv
JOIN pricing.mtg_card_products mcp ON mcp.card_version_id = cv.card_version_id
JOIN pricing.source_product sp ON sp.product_id = mcp.product_id
JOIN pricing.price_observation po ON po.source_product_id = sp.source_product_id
WHERE (cv.rarity IN ('mythic', 'rare', 'special') OR cv.is_promo = true)
  AND po.sell_avg_cents >= 100          -- $1.00 USD, configurable via settings
  AND po.ts_date >= now() - interval '7 days'
ON CONFLICT (card_version_id) DO UPDATE SET is_active = true;
```

The value threshold (`min_scrape_target_cents`) is a settings field so it can be tuned
without code changes.

---

### `integrations.ebay.scrape_global_market`

**Trigger:** `run_service`, 07:15 AEST  
**Repos:** `ebay_sales`, `ebay_scrape`, `card` (DB); `ebay_finding` (API)  
**Parameters:** `days_back=30`, `score_threshold=0.7`, `limit_per_card=50` (beat kwargs)

**Logic per card version:**

```
card = card_repository.get(card_version_id)
# Returns frame_effects, is_promo, promo_types, border_color_name, full_art, rarity

primary_frame = card.frame_effects[0] if card.frame_effects else None
is_borderless = (card.border_color_name == 'borderless')
frame_hint = primary_frame or ('borderless' if is_borderless else None)

keywords = build_query_string(card_name, set_code, is_foil=None, frame=frame_hint)

# Guarantee the full product chain exists before inserting prices
product_id = await ensure_product(card_version_id)          # product_ref + mtg_card_products
source_product_id = await ensure_source_product(card_version_id, source_id=5)

for marketplace in [EBAY-US, EBAY-AU, EBAY-ENCA]:
    items = find_completed_items(keywords, app_id, global_id=marketplace,
                                 days_back=days_back, limit=limit_per_card)
    for item in items:
        if score_title(item.title, card_name, set_code, ...) < score_threshold:
            continue
        parsed_frame = parse_frame_variant(item.title)
        if conflicts_with_expected(parsed_frame, card):
            continue                     # hard conflict only (e.g. title=showcase, card=regular)
        finish_id    = parse_finish(item.title)
        condition_id = parse_condition(item.ebay_condition, item.title)

        INSERT INTO pricing.ebay_scraped_sold (
            item_id, title, source_product_id,
            price_cents, currency, marketplace_id,
            finish_id, condition_id, sold_at
        ) ON CONFLICT (item_id) DO NOTHING

    sleep(0.3s)   # rate limit between marketplace calls

UPDATE ebay_scrape_targets SET last_scraped_at = now()
```

**Rate limit:** 3 marketplaces × up to 50 results × N cards. Finding API free tier is
5,000 calls/day. At 3 calls/card, the scraper supports ~1,600 target cards per night
before hitting the limit. The watchlist filter (rarity + value ≥ $1) naturally caps this.

---

## New Module: `title_parser.py`

Lives at `core/services/app_integration/ebay/title_parser.py`, alongside
`market_price_scorer.py`.

### `parse_finish(title: str) → int`

Returns a `finish_id` from `card_catalog.card_finished`. Checked in priority order
(most specific first). A small in-process dict maps code → id (loaded once at import).

| Title pattern (case-insensitive) | Finish code |
|---|---|
| `surge foil` | `SURGE_FOIL` |
| `ripple foil` | `RIPPLE_FOIL` |
| `rainbow foil` | `RAINBOW_FOIL` |
| `etched foil` / `foil etched` | `ETCHED` |
| `foil` (not preceded by `non-`) | `FOIL` |
| *(none of the above)* | `NONFOIL` |

Falls back to `default_finish_id()` if lookup fails.

### `parse_condition(ebay_condition: str | None, title: str) → int | None`

Tries eBay's `conditionDisplayName` field first (more reliable), falls back to title.

| eBay condition / title keyword | Condition code |
|---|---|
| `Near Mint or Better` / `NM`, `NM/M`, `M/NM` | `NM` |
| `Lightly Played` / `Excellent` / `LP`, `EX` | `LP` |
| `Slightly Played` / `SP` | `SP` |
| `Moderately Played` / `Very Good` / `MP`, `VG` | `MP` |
| `Heavily Played` / `Good` / `HP`, `G`, `PLD` | `HP` |
| `Damaged` / `Poor` / `DMG` | `DMG` |

Returns `None` if neither source yields a confident match. Rows with `condition_id = NULL`
are still inserted into `ebay_scraped_sold` but are not promoted to `price_observation`
until resolved.

### `parse_frame_variant(title: str) → dict`

Returns detected treatment signals used for conflict-checking against the card's known
attributes. Does not return a `finish_id` (that is `parse_finish`'s job).

```python
{
    "frame_effects": list[str],   # e.g. ["showcase"], ["extendedart"], ["retro"]
    "is_borderless": bool,
    "is_full_art": bool,
    "promo_types": list[str],     # e.g. ["promopack"], ["prerelease"]
}
```

| Title pattern | Detected attribute |
|---|---|
| `showcase` | `frame_effects: ['showcase']` |
| `extended art`, `ext art`, `EA` | `frame_effects: ['extendedart']` |
| `borderless` | `is_borderless: True` |
| `retro`, `old border`, `old frame` | `frame_effects: ['retro']` |
| `full art`, `full-art` | `is_full_art: True` |
| `promo pack`, `promo` | `promo_types: ['promopack']` |
| `prerelease`, `pre-release` | `promo_types: ['prerelease']` |
| `buy a box`, `buyabox`, `bab` | `promo_types: ['buyabox']` |
| `judge` | `promo_types: ['judgegift']` |

### `conflicts_with_expected(parsed: dict, card: dict) → bool`

Returns `True` only on hard conflicts — title asserts a treatment the card doesn't have,
or asserts no treatment when the card requires one. Permissive by design: ambiguous titles
(no treatment signal) are always kept.

Examples of hard conflicts:
- Title says `showcase`, card has `frame_effects = []` → conflict
- Title says `borderless`, card has `border_color_name = 'black'` → conflict
- Card has `frame_effects = ['showcase']`, title has no showcase signal → **not** a conflict
  (many sellers don't write "showcase" explicitly)

---

## Finding API Extension

`EbayFindingAPIRepository.find_completed_items()` gains a `global_id` parameter:

```python
async def find_completed_items(
    self,
    keywords: str,
    app_id: str,
    *,
    global_id: str = "EBAY-US",   # new
    category_id: int = 2536,
    ...
) -> list[dict]:
    params["X-EBAY-SOA-GLOBAL-ID"] = global_id   # added to request headers/params
```

No other changes to the existing method or its callers.

---

## Product Chain Fix

The current `scrape_external_sold` calls `ensure_source_product` without first calling
`ensure_product`. This silently returns `None` for any `card_version_id` not yet in
`pricing.mtg_card_products`.

`scrape_global_market` always calls both in order:

```python
product_id = await ebay_sales_repository.ensure_product(card_version_id)
if not product_id:
    logger.warning("ensure_product_failed", extra={"card_version_id": str(card_version_id)})
    continue

source_product_id = await ebay_sales_repository.ensure_source_product(
    card_version_id, _EBAY_SOURCE_ID
)
if not source_product_id:
    logger.warning("ensure_source_product_failed", extra={"card_version_id": str(card_version_id)})
    continue
```

Note: `ENSURE_PRODUCT` hardcodes `game_id = 1` (MTG paper). This is correct for the
current scope but should be resolved dynamically in a future iteration.

---

## Analytics Query Pattern

Cross-market price comparison normalised to USD at query time:

```sql
SELECT
    cv.card_name,
    cv.set_code,
    ess.marketplace_id,
    ess.currency,
    cc.code                              AS condition,
    cf.code                              AS finish,
    AVG(ess.price_cents)                        AS avg_native_cents,
    AVG(ess.price_cents * COALESCE(fx.rate, 1.0)) AS avg_usd_cents  -- USD rows have no FX row; COALESCE to 1.0
FROM pricing.ebay_scraped_sold ess
JOIN pricing.source_product sp
    ON sp.source_product_id = ess.source_product_id
JOIN pricing.mtg_card_products mcp
    ON mcp.product_id = sp.product_id
JOIN card_catalog.card_version cv
    ON cv.card_version_id = mcp.card_version_id
LEFT JOIN pricing.card_condition cc
    ON cc.condition_id = ess.condition_id
LEFT JOIN card_catalog.card_finished cf
    ON cf.finish_id = ess.finish_id
LEFT JOIN pricing.fx_rates fx
    ON fx.rate_date    = ess.sold_at::date
    AND fx.from_currency = ess.currency
    AND fx.to_currency   = 'USD'
WHERE ess.sold_at >= now() - interval '30 days'
GROUP BY cv.card_name, cv.set_code, ess.marketplace_id, ess.currency, cc.code, cf.code
ORDER BY avg_usd_cents DESC;
```

USD rows (`ess.currency = 'USD'`) have no matching FX row. `COALESCE(fx.rate, 1.0)`
treats NULL as 1.0 so USD prices pass through unchanged. No USD→USD row needs to be
inserted into `pricing.fx_rates`.

---

## Celery Beat Schedule

Three new entries in `celeryconfig.py`:

```python
"pricing-fetch-fx-rates-nightly": {
    "task": "run_service",
    "schedule": crontab(hour=6, minute=45),
    "kwargs": {"path": "integrations.pricing.fetch_fx_rates"},
},
"ebay-refresh-scrape-targets-nightly": {
    "task": "run_service",
    "schedule": crontab(hour=7, minute=0),
    "kwargs": {"path": "integrations.ebay.refresh_scrape_targets"},
},
"ebay-scrape-global-market-nightly": {
    "task": "run_service",
    "schedule": crontab(hour=7, minute=15),
    "kwargs": {"path": "integrations.ebay.scrape_global_market",
               "days_back": 30, "score_threshold": 0.7, "limit_per_card": 50},
},
# existing promote_sold_obs at 08:00 picks up global market rows automatically
```

---

## Error Handling

| Failure | Behaviour |
|---|---|
| `ensure_product` returns None | Log warning, skip card, continue |
| `ensure_source_product` returns None | Log warning, skip card, continue |
| Finding API 429 throttle | Catch, log, stop that marketplace for the run; already-inserted rows are safe |
| Title parse ambiguous (finish/condition) | Store defaults (`default_finish_id()`, `condition_id=NULL`); row inserted but not promoted until condition resolved |
| `conflicts_with_expected` hard conflict | Drop item silently (debug log only) |
| FX rate fetch fails | Log error, skip upsert; analytics degrade to native price via `LEFT JOIN` |
| Any card-level exception | Log exception, continue to next card |

---

## New Files

```
core/services/app_integration/ebay/
    title_parser.py                   ← parse_finish, parse_condition,
                                         parse_frame_variant, conflicts_with_expected
    scrape_global_market_service.py   ← integrations.ebay.scrape_global_market
    refresh_scrape_targets_service.py ← integrations.ebay.refresh_scrape_targets

core/services/pricing/
    fetch_fx_rates_service.py         ← integrations.pricing.fetch_fx_rates

core/repositories/app_integration/ebay/
    ApiFinding_repository.py          ← add global_id param (modify existing)

database/SQL/migrations/
    migration_XX_ebay_global_market_scraper.sql

celeryconfig.py                       ← 3 new beat entries
```

---

## Out of Scope

- Re-scraping the full card catalog (watchlist filter keeps API calls within free tier)
- Currency conversion at ingest time (native prices stored, FX applied at query time)
- Re-resolution pass for `condition_id = NULL` rows
- Backfilling historical sold prices beyond `days_back=30`
- Fixing the `game_id = 1` hardcode in `ENSURE_PRODUCT` (tracked separately)
- Applying the `ensure_product` fix to the existing `scrape_external_sold` service
  (should be fixed but is a separate PR)
