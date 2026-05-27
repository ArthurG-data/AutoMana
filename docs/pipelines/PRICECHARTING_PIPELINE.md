# PriceCharting Sold Price Pipeline

## Overview

The PriceCharting pipeline replaces the eBay Finding API (`findCompletedItems`, decommissioned February 2025) as the source of historical sold prices for MTG singles. It scrapes sold listings directly from [pricecharting.com](https://www.pricecharting.com), matches each product to a `card_version_id` in the DB, and inserts results into the same `pricing.ebay_scraped_sold` staging table used by the rest of the pricing layer.

---

## Architecture

```
PriceCharting set catalog page
  └─ Playwright (lazy-load scroll)
       └─ pricecharting_{set}.json          ← cached daily

PriceCharting individual card pages
  └─ httpx (server-rendered HTML, no JS needed)
       └─ pricecharting_{set}_sales.json    ← cached daily

2-pass DB matching
  └─ Pass 1: collector number exact match
  └─ Pass 2: name + treatment scoring
       └─ Tiebreaker 1: TCGPlayer ID match
       └─ Tiebreaker 2: lowest collector number

pricing.ebay_scraped_sold  (staging)
  └─ promote_sold_obs
       └─ pricing.price_observation  (TimescaleDB hypertable)
```

---

## Data Sources

### Set catalog (`/console/{set-slug}`)

Lazy-loads card rows as the user scrolls. Playwright is required — a plain httpx request captures only the first ~50 rows.

Scraped columns per product:

| Field | Source |
|---|---|
| `product_id` | `tr[data-product]` attribute |
| `title` | `td.title a` text |
| `product_type` | `single` if title contains `#NNN`, else `sealed` |
| `ungraded_cents` | `td.used_price span.js-price` |
| `grade9_cents` | `td.cib_price span.js-price` |
| `psa10_cents` | `td.new_price span.js-price` |

Results are cached to `data/pricecharting_{set}.json` and replayed within the same calendar day.

### Individual card pages (`/game/{set-slug}/{card-slug}`)

Server-rendered HTML. httpx is sufficient. Each page exposes up to five sold-listing tables identified by CSS class:

| CSS class | Grade label |
|---|---|
| `completed-auctions-used` | `ungraded` |
| `completed-auctions-cib` | `grade7` |
| `completed-auctions-new` | `grade8` |
| `completed-auctions-graded` | `grade9` |
| `completed-auctions-manual-only` | `psa10` |

Each row in these tables yields: `sale_date`, `listing_title`, `price_cents`, `source` (eBay or TCGPlayer detected from link text/href).

The TCGPlayer product ID is extracted from the first `<a class="js-tcgplayer-completed-sale">` href (`/product/{id}` after URL-decoding) and stored in `pc_tcgplayer_map` for use as a tiebreaker during DB matching.

Results are cached to `data/pricecharting_{set}_sales.json` with `tcgplayer_map` included.

---

## DB Matching

For each single product in the set catalog, the pipeline maps the PriceCharting product to a `card_version_id` in two passes.

### Pass 1 — Collector number

Products whose title contains `#NNN` are matched directly:

```sql
SELECT cv.card_version_id, ...
FROM   card_catalog.card_version cv
JOIN   card_catalog.sets s ON s.set_id = cv.set_id
WHERE  UPPER(s.set_code) = UPPER($1) AND cv.collector_number = $2
```

The first row is used (collector numbers within a set are unique per print, though foil/non-foil variants share the number — Pass 1 picks the first and finish is resolved separately from the title bracket).

### Pass 2 — Name + treatment scoring

Products without a collector number (promos, some alternate arts) are matched by card name plus a treatment score:

```
score += 3  if title bracket signals a treatment the candidate has
score -= 2  if title bracket signals a treatment the candidate lacks
```

Finish words (`foil`, `etched foil`, etc.) are stripped from the bracket before scoring so `[Showcase Foil]` scores on `showcase` only.

**Tiebreaker 1 — TCGPlayer ID:** if the PC page exposed a TCGPlayer product ID and exactly one winner's `card_external_identifier.value` (for `identifier_name = 'tcgplayer_id'`) matches, that card wins.

**Tiebreaker 2 — Lowest collector number:** falls back to the most canonical variant (lowest collector number within the set).

---

## Finish Parsing

Finish is parsed from the bracket tag in the PC product title:

| Bracket content | `finish_id` |
|---|---|
| `[… Etched …]` | 3 (etched) |
| `[… Foil …]`, `Prerelease` | 2 (foil) |
| anything else or no bracket | 1 (non-foil) |

---

## Condition Parsing

### Ungraded sales

Condition is inferred from the listing title using regex patterns:

| Pattern | `condition_id` |
|---|---|
| near mint / NM | 1 |
| lightly played / LP | 2 |
| moderately played / MP | 3 |
| heavily played / HP | 4 |
| damaged / DMG / poor | 5 |
| no match | 1 (NM default) |

### Graded sales

Graded slabs use dedicated condition IDs that extend `pricing.card_condition` (added in migration 52):

| Grade label | `condition_id` | Code | Description |
|---|---|---|---|
| `grade7` | 7 | GR7 | Graded 7 |
| `grade8` | 8 | GR8 | Graded 8 |
| `grade9` | 9 | GR9 | Graded 9 |
| `psa10` | 10 | PSA10 | PSA 10 / Gem Mint |

Graded and ungraded items are mutually exclusive, so reusing the `condition_id` dimension avoids adding a new column to the TimescaleDB `price_observation` hypertable.

---

## Source Registration

PriceCharting is registered in `pricing.price_source` on first run (idempotent):

| Field | Value |
|---|---|
| `code` | `pricecharting` |
| `currency_code` | `USD` |
| `name` | `PriceCharting` |

For each matched `card_version_id`, a `pricing.source_product` row is created (if not already present) by walking:

```
card_version_id
  → pricing.mtg_card_products   (get or create product_id)
  → pricing.source_product      (get or create source_product_id for pricecharting)
```

---

## Staging Insert

Each accepted sale is inserted into `pricing.ebay_scraped_sold` with:

| Column | Value |
|---|---|
| `item_id` | `pc-{sha1(product_id + sold_at + price_cents + listing_title)[:12]}` |
| `title` | listing title from the sold table |
| `source_product_id` | PriceCharting source_product_id for the matched card |
| `price_cents` | sale price in USD cents |
| `condition_id` | from condition/grade parsing above |
| `finish_id` | from finish parsing above |
| `marketplace_id` | `EBAY-US` or `TCGPLAYER` (from detected sale source) |
| `sold_at` | parsed sale date (UTC) |

The synthetic `item_id` is deterministic — re-running on the same cached data produces the same IDs, making the delete-before-insert idempotent.

---

## Sealed Products

Booster boxes, bundles, prerelease packs, and commander decks are identified by the absence of `#NNN` in the title combined with sealed keywords. They are excluded from the DB-matching and staging-insert flow and displayed separately in the notebook as a summary-price reference only.

---

## Related Tables

| Table | Purpose |
|---|---|
| `pricing.card_condition` | Condition + graded-tier lookup (condition_id 1–6 raw, 7–10 graded) |
| `pricing.price_source` | Source registry; `pricecharting` added by pipeline on first run |
| `pricing.source_product` | Links `product_id` + `source_id` → `source_product_id` |
| `pricing.mtg_card_products` | Bridges `card_version_id` ↔ `product_id` |
| `pricing.ebay_scraped_sold` | Staging table for all sold observations |
| `pricing.price_observation` | TimescaleDB hypertable; populated by `promote_sold_obs` |
| `card_catalog.card_external_identifier` | Stores TCGPlayer IDs used as matching tiebreaker |
