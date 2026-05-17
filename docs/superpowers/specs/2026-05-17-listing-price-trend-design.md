# Listing Price Trend — Design Spec

**Date:** 2026-05-17
**Branch:** feat/listing-price-trend
**Status:** Draft — pending user review

---

## Problem

An active eBay listing shows a card, its condition, and its finish. The seller currently sees no signal about whether the market price for that exact variant is trending up or down. The goal is to surface:

1. **A trend signal** — short (7-day), medium (30-day), and 90-day delta percentages with a classified direction: `UP`, `SIDEWAYS`, or `DOWN`.
2. **A recommendation enrichment** — feed the trend into the existing `compute_recommendation()` engine so the `raise / lower / hold / draft` output can factor in price momentum.

---

## Data Flow

```
GET /{item_id}/trend
        │
        ▼
ebay_recommendations router
        │
        ▼
ServiceRegistry → integrations.ebay.recommendations.trend
        │
        ├─► ApiSellingRepository.get_listing_meta(item_id, app_code)
        │       → ebay_active_listings: card_version_id, finish_id, condition_id
        │
        ├─► PricingTierRepository.get_price_history(card_version_id, finish_id, condition_id, days=90)
        │       → print_price_daily: date-ordered price series, best-available source
        │
        └─► compute_price_trend(price_series, windows=[7, 30, 90])
                → PriceTrend dataclass: deltas + signal + recommendation text
```

---

## Components

### 1. `ApiSellingRepository.get_listing_meta(item_id, app_code)`

**File:** `src/automana/core/repositories/app_integration/ebay/ApiSelling_repository.py`

New SQL query on `app_integration.ebay_active_listings`:

```sql
SELECT
    eal.card_version_id,
    eal.finish_id,
    eal.condition_id,
    eal.language_id,
    cf.code  AS finish_code,
    cc.code  AS condition_code
FROM app_integration.ebay_active_listings eal
JOIN card_catalog.card_finished   cf USING (finish_id)
JOIN pricing.card_condition       cc USING (condition_id)
WHERE eal.item_id = $1
  AND eal.app_code = $2
```

Returns `None` if the listing is not found or not yet linked to a card (i.e., `card_version_id IS NULL`).

> `finish_id` and `condition_id` are nullable in the schema (added in migration_37). If either is NULL, fall back to the schema defaults: `NONFOIL` and `NM`.

---

### 2. `PricingTierRepository.get_price_history(card_version_id, finish_id, condition_id, days=90)`

**File:** `src/automana/core/repositories/pricing/price_repository.py`

Queries `pricing.print_price_daily` for the last N days. Best-available source logic is embedded in SQL: prefer `tcg` (TCGPlayer), fall back to whichever source has the most rows for this card+variant combination over the window.

```sql
WITH source_priority AS (
    SELECT
        ppd.source_id,
        ps.code,
        COUNT(*)                                      AS n_rows,
        CASE WHEN ps.code = 'tcg' THEN 0 ELSE 1 END  AS preferred
    FROM pricing.print_price_daily ppd
    JOIN pricing.price_source ps USING (source_id)
    WHERE ppd.card_version_id = $1
      AND ppd.finish_id       = $2
      AND ppd.condition_id    = $3
      AND ppd.price_date      >= CURRENT_DATE - make_interval(days => $4)
    GROUP BY ppd.source_id, ps.code
    ORDER BY preferred, n_rows DESC
    LIMIT 1
),
best AS (SELECT source_id FROM source_priority)
SELECT
    ppd.price_date,
    ppd.list_avg_cents,
    ppd.list_low_cents
FROM pricing.print_price_daily ppd
JOIN best USING (source_id)
WHERE ppd.card_version_id = $1
  AND ppd.finish_id       = $2
  AND ppd.condition_id    = $3
  AND ppd.price_date      >= CURRENT_DATE - make_interval(days => $4)
ORDER BY ppd.price_date ASC
```

Returns a list of `{"price_date": date, "list_avg_cents": int, "list_low_cents": int}` dicts, oldest-first. Returns `[]` if no data.

---

### 3. `compute_price_trend(price_series, windows)` — pure function

**File:** `src/automana/core/services/app_integration/ebay/listing_recommendation_service.py`

No DB access. Takes a list of `{"price_date": date, "list_avg_cents": int}` rows (oldest-first) and a list of window sizes in days.

**Algorithm per window:**
- Find the price N days ago (closest observation on or before `today - N days`).
- Find the most recent price (last row).
- Compute `delta_pct = (latest - anchor) / anchor * 100`.
- If fewer than 2 data points span the window: set `delta_pct = None`.

**Signal classification** (based on the 30-day delta, the primary window):
- `delta_pct >= +10%` → `UP`
- `delta_pct <= -10%` → `DOWN`
- Otherwise → `SIDEWAYS`

If the 30-day window has no data, fall back to the 7-day window. If neither is available: `signal = "INSUFFICIENT_DATA"`.

**Output dataclass:**

```python
@dataclass
class PriceTrend:
    signal: Literal["UP", "DOWN", "SIDEWAYS", "INSUFFICIENT_DATA"]
    delta_7d_pct: Optional[float]   # None if <2 points in window
    delta_30d_pct: Optional[float]
    delta_90d_pct: Optional[float]
    latest_avg_cents: Optional[int]
    n_observations: int
    source_used: Optional[str]      # e.g. "tcg"
```

---

### 4. Recommendation enrichment

**File:** `src/automana/core/services/app_integration/ebay/listing_recommendation_service.py`

`compute_recommendation()` gains a third signal path: `trend`. When `price_trend` is passed in, it is layered on top of the existing `raise/lower/hold/draft` logic:

| Existing action | Trend signal | Final action |
|----------------|--------------|--------------|
| `hold`         | `UP`         | `raise`      |
| `hold`         | `DOWN`       | `lower`      |
| `raise`        | `DOWN`       | `hold`       |
| `lower`        | `UP`         | `hold`       |
| `draft`        | any          | `draft`      |
| any            | `SIDEWAYS` / `INSUFFICIENT_DATA` | unchanged |

Confidence is boosted by `+0.05` when trend agrees with the existing action, reduced by `0.05` when it conflicts.

---

### 5. New endpoint — `GET /{item_id}/trend`

**File:** `src/automana/api/routers/integrations/ebay/ebay_recommendations.py`

```
GET /integrations/ebay/recommendations/{item_id}/trend?app_code=<code>
```

Response shape:

```json
{
  "item_id": "...",
  "card_version_id": "...",
  "finish": "NONFOIL",
  "condition": "NM",
  "trend": {
    "signal": "UP",
    "delta_7d_pct": 3.2,
    "delta_30d_pct": 11.4,
    "delta_90d_pct": 18.7,
    "latest_avg_cents": 1450,
    "n_observations": 67,
    "source_used": "tcg"
  },
  "recommendation": {
    "suggested_action": "raise",
    "confidence": 0.80,
    "signals_used": "trend"
  }
}
```

Registered as `integrations.ebay.recommendations.trend`, `db_repositories=["pricing", "ebay_sales"]`.

**Error cases:**
- Listing not found → 404
- `card_version_id` is NULL (not yet linked) → 422 with `"detail": "Listing not yet linked to a card"`
- No price history → returns trend with `signal = "INSUFFICIENT_DATA"`, recommendation falls back to behavioral

---

## What is NOT in scope

- Writing trend data back to the DB (no materialized view, no caching).
- Collection items (`user_collection.collection_items`) — active eBay listings only for now.
- Sold order trend analysis (`ebay_order_source_product`).
- Language-scoped trend (always queries default language `en`).
- UI chart / sparkline — this spec covers the API only.

---

## Files to create / modify

| Action   | File |
|----------|------|
| Modify   | `src/automana/core/repositories/app_integration/ebay/sales_queries.py` — add `GET_LISTING_META` SQL constant |
| Modify   | `src/automana/core/repositories/app_integration/ebay/sales_repository.py` — add `get_listing_meta()` |
| Modify   | `src/automana/core/repositories/pricing/price_repository.py` — add `get_price_history()` |
| Modify   | `src/automana/core/services/app_integration/ebay/listing_recommendation_service.py` — add `PriceTrend`, `compute_price_trend()`, extend `compute_recommendation()` |
| Modify   | `src/automana/api/routers/integrations/ebay/ebay_recommendations.py` — add `GET /{item_id}/trend` |
| New file | `src/automana/core/services/app_integration/ebay/price_trend_service.py` — `get_listing_price_trend` service function (registered) |

---

## Testing

- `compute_price_trend()` is pure — unit-test with synthetic price series covering: trending up, down, flat, sparse data, insufficient data.
- `compute_recommendation()` — unit-test the new trend-overlay logic for each cell of the adjuster table.
- Integration test: `GET /{item_id}/trend` with a seeded `ebay_active_listings` row + `print_price_daily` rows.
