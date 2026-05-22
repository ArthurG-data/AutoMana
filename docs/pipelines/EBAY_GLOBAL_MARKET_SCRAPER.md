# eBay Global Market Scraper

## Overview

The global market scraper collects eBay sold prices for high-value MTG cards across three marketplaces — **EBAY-US** (USD), **EBAY-AU** (AUD), and **EBAY-ENCA** (CAD) — using a single App ID and the public eBay Finding API. Results land in `pricing.ebay_scraped_sold` and feed into the existing `promote_sold_obs` pipeline for price observation storage.

This complements the own-sales sync (`ebay_sync_own_sales`) with external market data: what competitors' cards actually sold for.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  Nightly Celery beat (AEST)                                      │
│                                                                  │
│  06:45  fetch_fx_rates          → pricing.fx_rates              │
│  07:00  ebay_sync_own_sales     → pricing.ebay_own_sales         │
│  07:15  ebay_scrape_ext_sold    → pricing.ebay_scraped_sold      │
│  08:00  promote_sold_obs        → pricing.price_observation      │
│  08:30  refresh_scrape_targets  → pricing.ebay_scrape_targets    │
│  08:45  scrape_global_market    → pricing.ebay_scraped_sold      │
└──────────────────────────────────────────────────────────────────┘
```

`scrape_global_market` runs after `promote_sold_obs` so the watchlist refresh (08:30) has fresh `price_observation` data to evaluate the value threshold.

---

## Services

### `integrations.pricing.fetch_fx_rates`

Fetches the day's USD→AUD and USD→CAD exchange rates from [frankfurter.dev](https://api.frankfurter.dev) and stores them **inverted** (as AUD→USD, CAD→USD) in `pricing.fx_rates`.

The inverse is stored so price queries can multiply a foreign-currency amount directly by the rate to get USD: `price_aud * aud_to_usd_rate = price_usd`.

**Source:** `src/automana/core/services/pricing/fetch_fx_rates_service.py`

**Result:**
```json
{"rates_upserted": 2}
```

**Table:** `pricing.fx_rates`
| Column | Type | Notes |
|---|---|---|
| `rate_date` | DATE | Composite PK |
| `from_currency` | VARCHAR(3) | `AUD` or `CAD` |
| `to_currency` | VARCHAR(3) | Always `USD` |
| `rate` | NUMERIC(12,6) | Inverted rate: 1 / (USD per foreign unit) |
| `fetched_at` | TIMESTAMPTZ | Auto-set on upsert |

---

### `integrations.ebay.refresh_scrape_targets`

Maintains the scrape watchlist in `pricing.ebay_scrape_targets`. Two steps run in order:

1. **Deactivate stale targets** — sets `is_active = false` for cards that no longer meet the threshold (rare/mythic/promo with `sold_avg_cents >= min_cents` in the last 7 days).
2. **Upsert active targets** — inserts or reactivates cards that do meet the threshold.

The default minimum is `$1.00 USD` (`min_cents = 100`). Override via `EBAY_SCRAPE_TARGET_MIN_CENTS` env var.

**Source:** `src/automana/core/services/app_integration/ebay/refresh_scrape_targets_service.py`

**Result:**
```json
{"status": "ok", "min_cents": 100}
```

**Table:** `pricing.ebay_scrape_targets`
| Column | Type | Notes |
|---|---|---|
| `card_version_id` | UUID | PK, FK → `card_catalog.card_version` |
| `added_at` | TIMESTAMPTZ | When first added |
| `last_scraped_at` | TIMESTAMPTZ | Updated after each scrape run |
| `is_active` | BOOLEAN | Deactivated when card drops below threshold |
| `added_by` | TEXT | `'auto'` for nightly refresh, `'manual'` for manual inserts |

---

### `integrations.ebay.scrape_global_market`

The main scraper. For each active target card, queries EBAY-US, EBAY-AU, and EBAY-ENCA for sold listings in the last N days using the eBay Finding API (`findCompletedItems`).

Each result is scored and filtered before insertion:

| Step | Details |
|---|---|
| Query | `build_query_string(card_name, set_code, frame)` from `market_price_scorer.py` |
| Score | `score_title(title, ...)` — must be ≥ `score_threshold` (default 0.7) |
| Frame check | `conflicts_with_expected(parsed, card)` — drops listings claiming a frame effect the card doesn't have |
| Finish | `parse_finish_code(title)` → FOIL / ETCHED / SURGE_FOIL / etc. |
| Condition | `parse_condition_code(ebay_condition, title)` → NM / LP / MP / HP / DMG |
| Insert | `pricing.ebay_scraped_sold` with `marketplace_id` set to the source marketplace |

A 300ms inter-marketplace delay is applied per card to avoid rate-limiting.

**Parameters:**
| Param | Default | Description |
|---|---|---|
| `days_back` | `30` | Look back N days for sold listings |
| `score_threshold` | `0.7` | Minimum title-match score to accept (0–1) |
| `limit_per_card` | `50` | Max listings to fetch per card × marketplace |

**Source:** `src/automana/core/services/app_integration/ebay/scrape_global_market_service.py`

**Result:**
```json
{"scraped_items": 1247, "cards_processed": 500}
```

**Requires:** `EBAY_APP_ID` env var (the eBay App ID from `app_integration.app_info`).

---

## Title Parser

**Source:** `src/automana/core/services/app_integration/ebay/title_parser.py`

Extracts structured attributes from raw eBay listing titles. Used by `scrape_global_market` but also available standalone.

### `parse_finish_code(title) → str`

Returns a finish code: `NONFOIL`, `FOIL`, `ETCHED`, `SURGE_FOIL`, `RIPPLE_FOIL`, `RAINBOW_FOIL`.

Pattern matching is most-specific-first: "surge foil" matches before bare "foil".

```python
parse_finish_code("Lightning Bolt Foil NM") → "FOIL"
parse_finish_code("Sheoldred Etched NM")    → "ETCHED"
parse_finish_code("Black Lotus LP")         → "NONFOIL"
```

### `parse_condition_code(ebay_condition, title) → str`

Tries the eBay structured condition field first, then falls back to regex patterns in the title. Returns `NM` when ambiguous.

```python
parse_condition_code("Near Mint or Better", "...")  → "NM"
parse_condition_code(None, "Bolt LP/EX")            → "LP"
parse_condition_code(None, "Black Lotus HP/PLD")    → "HP"
```

### `parse_frame_variant(title) → dict`

Detects treatment signals: frame effects, borderless, full-art, promo types.

```python
parse_frame_variant("Jace Showcase Extended Art Foil") → {
    "frame_effects": ["extendedart", "showcase"],
    "is_borderless": False,
    "is_full_art": False,
    "promo_types": []
}
```

### `conflicts_with_expected(parsed, card) → bool`

Returns `True` only on hard conflicts (title claims a treatment the card doesn't have). Permissive by design — a title with no frame signal never conflicts, since most sellers don't mention treatment.

```python
# Card is a normal-border regular print:
conflicts_with_expected({"frame_effects": ["showcase"], ...}, card_without_showcase) → True
conflicts_with_expected({"frame_effects": [], ...}, card_with_showcase)              → False
```

---

## Database Schema

Migration 45 (`src/automana/database/SQL/migrations/migration_45_ebay_global_market_scraper.sql`):

```sql
-- Scrape watchlist
CREATE TABLE pricing.ebay_scrape_targets (
    card_version_id UUID PRIMARY KEY REFERENCES card_catalog.card_version,
    added_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_scraped_at TIMESTAMPTZ,
    is_active       BOOLEAN NOT NULL DEFAULT true,
    added_by        TEXT NOT NULL DEFAULT 'auto'
);

-- Daily FX rates
CREATE TABLE pricing.fx_rates (
    rate_date      DATE          NOT NULL,
    from_currency  VARCHAR(3)    NOT NULL,
    to_currency    VARCHAR(3)    NOT NULL DEFAULT 'USD',
    rate           NUMERIC(12,6) NOT NULL,
    fetched_at     TIMESTAMPTZ   NOT NULL DEFAULT now(),
    PRIMARY KEY (rate_date, from_currency, to_currency)
);

-- Marketplace tag on existing scraped_sold table
ALTER TABLE pricing.ebay_scraped_sold
    ADD COLUMN marketplace_id VARCHAR(20) NOT NULL DEFAULT 'EBAY-US';
```

---

## Configuration

| Env var | Default | Description |
|---|---|---|
| `EBAY_APP_ID` | `None` | eBay Application ID (required for `scrape_global_market`) |
| `EBAY_SCRAPE_TARGET_MIN_CENTS` | `100` | Minimum `sold_avg_cents` for watchlist inclusion ($1.00 USD) |

The eBay App ID is stored in `app_integration.app_info.app_id`. Use the `PRODUCTION` environment row value.

---

## Running Manually

All three services run via `automana-run`. Run them in order to simulate the nightly pipeline:

```bash
# 1. Refresh FX rates (needed for cross-currency price queries later)
automana-run integrations.pricing.fetch_fx_rates

# 2. Rebuild the watchlist
automana-run integrations.ebay.refresh_scrape_targets

# 3. Scrape sold prices — use small limits for dev testing
EBAY_APP_ID=<your-app-id> automana-run integrations.ebay.scrape_global_market \
  --days_back 7 \
  --score_threshold 0.7 \
  --limit_per_card 5
```

The `promote_sold_obs` service will pick up any new `ebay_scraped_sold` rows (where `promoted_to_obs = false`) on its next run:

```bash
automana-run integrations.ebay.promote_sold_obs
```

---

## Verifying Results

```sql
-- FX rates
SELECT * FROM pricing.fx_rates ORDER BY rate_date DESC;

-- Watchlist size
SELECT COUNT(*) FILTER (WHERE is_active) AS active,
       COUNT(*) FILTER (WHERE last_scraped_at IS NOT NULL) AS scraped
FROM pricing.ebay_scrape_targets;

-- Recent scraped sold by marketplace
SELECT marketplace_id, currency, COUNT(*) AS sales,
       ROUND(AVG(price_cents) / 100.0, 2) AS avg_price
FROM pricing.ebay_scraped_sold
WHERE inserted_at >= now() - interval '1 day'
GROUP BY marketplace_id, currency
ORDER BY sales DESC;

-- Unpromoted rows waiting for promote_sold_obs
SELECT COUNT(*)
FROM pricing.ebay_scraped_sold
WHERE promoted_to_obs = false AND source_product_id IS NOT NULL;
```

---

## Known Limitations

**FX normalization in promote_sold_obs:** The promotion step currently treats all prices as USD regardless of `currency` or `marketplace_id`. AUD and CAD prices land in `price_observation` at face value. Normalization requires either converting at scrape time (multiply by `fx_rates.rate`) or making `promote_sold_obs` FX-aware. This is deferred to a follow-up PR.

**Watchlist cap:** `GET_SCRAPE_TARGETS` limits the nightly run to 500 cards. With 3 marketplaces × 50 items each, that's up to 75,000 Finding API calls per night. Raise `limit_per_card` or the watchlist cap conservatively once production throughput is measured.

**eBay Finding API rate limits:** The Finding API allows ~5,000 calls/day per App ID on the free tier. With 500 cards × 3 marketplaces = 1,500 calls, there is headroom. Monitor via eBay Developer Portal.
