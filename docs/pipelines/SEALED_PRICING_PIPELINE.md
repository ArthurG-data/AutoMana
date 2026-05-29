# Sealed Product Pricing Pipeline

## Overview

AutoMana tracks sealed MTG product prices (booster boxes, bundles, collector boxes, etc.)
alongside single-card prices. The sealed pipeline is separate from the card pipeline because:

- Sealed products are not cards — they have no `card_version_id` and no finish/condition splits.
- Sealed prices come from TCGPlayer (via tcgtracking.com), not MTGJson price feeds.
- The catalog is sourced from MTGJson per-set JSON files (`/api/v5/{SET}.json`), which
  expose a `sealedProduct[]` array with name, category, subtype, and external identifiers.

---

## Schema

```
card_catalog.sealed_type_ref          — product category (booster_box, bundle, …)
card_catalog.sealed_subtype_ref       — product subtype (collector, play, …) — nullable
card_catalog.sealed_product           — central entity: set + game + type + subtype + language
card_catalog.sealed_identifier_ref    — identifier types: mtgjson_uuid, tcgplayer_product_id, …
card_catalog.sealed_external_identifier — (sealed_product_id, type) → value

pricing.product_ref                   — base pricing entity (game-agnostic)
pricing.mtg_sealed_products           — pricing subtype: product_ref → sealed_product
pricing.sealed_price_latest           — current-price snapshot keyed on (product_id, source, type)
```

The lookup path from a tcgtracking.com price to the DB row:

```
tcgplayer_product_id
  → card_catalog.sealed_external_identifier   (value lookup)
  → card_catalog.sealed_product               (sealed_product_id)
  → pricing.mtg_sealed_products               (sealed_product_id → product_id)
  → pricing.sealed_price_latest               (product_id → price row)
```

---

## Registered Services

| Key | What it does |
|-----|-------------|
| `pricing.sealed.bootstrap_catalog_from_set` | Fetches `{SET}.json` from MTGJson, upserts all `sealedProduct[]` rows into the catalog. Idempotent — re-running updates name/type/identifiers in place. |
| `pricing.sealed.get_prices_by_set` | Reads `sealed_price_latest` for all products in a set. Used by the API. |
| `pricing.sealed.get_price_history` | Reads `price_observation` history for one product by mtgjson_uuid. Used by the API. |

---

## API Endpoints

```
GET /api/catalog/mtg/sealed/{set_code}/prices
GET /api/catalog/mtg/sealed/{set_code}/{mtgjson_uuid}/history
```

---

## Current State (2026-05-27)

Catalog is bootstrapped for 6 sets: BLB, DSK, FDN, MH3, OTJ, TDM (97 products, 86 with
TCGPlayer IDs). No prices have been ingested yet — `sealed_price_latest` is empty.

---

## Roadmap

### Step 1 — Extend opentcg price loader to detect sealed products

**File:** `src/automana/core/services/app_integration/open_tcg/data_loader.py`

The existing `pricing.opentcg.load_prices` service fetches all SKU pricing from
tcgtracking.com and maps `product_id → card_version` via `tcgplayer_id` in
`card_external_identifier`. Sealed products appear in the same feed but are currently
silently dropped when no matching card version is found.

The fix is a two-pass approach in the loader:

1. **Card pass (existing):** route `product_id` → `card_version` as today.
2. **Sealed pass (new):** for any `product_id` that matched nothing in the card pass,
   look up `card_catalog.sealed_external_identifier` (identifier `tcgplayer_product_id`).
   If a sealed product matches, write a `sealed_price_latest` row.

A sealed product has a single SKU with `var='N'` (no foil split) and no condition split.
The price fields to write are:
- `list_low_cents` ← `low * 100` (round to int)
- `list_avg_cents` ← `mkt * 100`
- `sold_avg_cents` ← NULL (tcgtracking does not expose sold prices for sealed)

**New repository method needed:** `SealedPricingRepository.upsert_sealed_price_latest(rows)`

```python
# rows: list of (product_id, source_id, transaction_type_id, price_date, list_low_cents, list_avg_cents)
INSERT INTO pricing.sealed_price_latest
    (product_id, source_id, transaction_type_id, price_date, list_low_cents, list_avg_cents, updated_at)
VALUES (...)
ON CONFLICT (product_id, source_id, transaction_type_id)
    DO UPDATE SET
        list_low_cents = EXCLUDED.list_low_cents,
        list_avg_cents = EXCLUDED.list_avg_cents,
        price_date     = EXCLUDED.price_date,
        updated_at     = now()
```

### Step 2 — Add `fetch_product_id_by_tcgplayer_id` to SealedPricingRepository

The open_tcg loader needs to resolve `tcgplayer_product_id → product_id` in batch.
Add a bulk lookup method:

```python
async def fetch_product_ids_by_tcgplayer_ids(
    self, tcgplayer_ids: list[str]
) -> dict[str, UUID]:
    """Returns {tcgplayer_product_id: product_id} for matching sealed products."""
```

SQL sketch:
```sql
SELECT sei.value AS tcgplayer_product_id, msp.product_id
FROM card_catalog.sealed_external_identifier sei
JOIN card_catalog.sealed_identifier_ref sir
    ON sir.sealed_identifier_ref_id = sei.sealed_identifier_ref_id
   AND sir.identifier_name = 'tcgplayer_product_id'
JOIN card_catalog.sealed_product sp ON sp.sealed_product_id = sei.sealed_product_id
JOIN pricing.mtg_sealed_products msp ON msp.sealed_product_id = sp.sealed_product_id
WHERE sei.value = ANY($1::text[])
```

### Step 3 — Wire into the opentcg pipeline

The `opentcg_pricing_pipeline` Celery task currently runs:

```
start_run → load_prices → finish_run
```

`load_prices` should detect sealed product IDs during its loop and write sealed prices
directly. No new pipeline step is needed — the logic lives inside the existing service.

The `open_tcg` loader already resolves one set at a time; it can prefetch the full
sealed product ID map once per run and use it as a local lookup dict.

### Step 4 — Catalog bootstrap pipeline task

Add a `sealed_catalog_bootstrap_pipeline` Celery task (or a Beat schedule) that calls
`pricing.sealed.bootstrap_catalog_from_set` for every set in `card_catalog.sets` that
has a release date and has not been bootstrapped yet (i.e., no rows in
`card_catalog.sealed_product` for that set).

Alternatively, run it as part of the weekly Scryfall pipeline after sets are updated.

### Step 5 — Verification

After Step 3 is wired in, trigger a manual run of `opentcg_pricing_pipeline` and verify:

```sql
-- Should have rows after first run
SELECT COUNT(*) FROM pricing.sealed_price_latest;

-- Spot-check: BLB Collector Booster Box (tcgplayer_product_id = 541238)
SELECT spl.*, sp.name
FROM pricing.sealed_price_latest spl
JOIN pricing.mtg_sealed_products msp ON msp.product_id = spl.product_id
JOIN card_catalog.sealed_product sp ON sp.sealed_product_id = msp.sealed_product_id
JOIN card_catalog.sealed_external_identifier sei ON sei.sealed_product_id = sp.sealed_product_id
JOIN card_catalog.sealed_identifier_ref sir
    ON sir.sealed_identifier_ref_id = sei.sealed_identifier_ref_id
   AND sir.identifier_name = 'tcgplayer_product_id'
WHERE sei.value = '541238';
```

---

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Catalog in `card_catalog` schema, not `pricing` | Mirrors card_version pattern; catalog is not pricing-specific |
| Type and subtype as separate ref tables | Allows independent filtering (e.g. all `collector` subtype across all product types) |
| `sealed_price_latest` not `price_observation` | Sealed products don't need the full TimescaleDB hypertable; a simple snapshot table is enough for now. History via `price_observation` can be added later by routing through `source_product`. |
| TCGPlayer as price source | tcgtracking.com is the only aggregated sealed price feed currently integrated |
| Language column on sealed_product | Some products (e.g. Japanese collectors) are market-specific; extensible without schema change |
| Auto-seeding unknown type/subtype codes | MTGJson introduces new taxonomy values each set; auto-insert is more resilient than failing |
