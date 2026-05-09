# eBay Market Price Research — Design Spec

**Date:** 2026-05-09
**Status:** Approved
**Branch:** feat/ebay-hub-docs

---

## Goal

Given a card (name, set, finish, frame, condition), fetch both **sold** and **active** eBay listings, score each result for relevance, and return aggregated price data. The primary consumers are:

1. A new API endpoint (`GET /api/v1/integrations/ebay/market-price`) used by the backend.
2. A Jupyter notebook that visualises price distributions and derives a suggested listing price.

Pricing strategies (how to convert market data into a price decision) are a separate concern and are not part of this spec.

---

## Data Sources

| Source | API | Auth | Data |
|---|---|---|---|
| Sold / completed listings | eBay Finding API (`findCompletedItems`) | App ID via `X-EBAY-SOA-SECURITY-APPNAME` | What buyers actually paid |
| Active listings | eBay Browse API (`/item_summary/search`) | User OAuth token (via `app_code`) | Current competition |

Both calls run concurrently with `asyncio.gather`. The Finding API call does **not** require a user OAuth token — it uses the App ID from `core/settings.py`.

---

## New Files

```
core/
  models/ebay/
    market_price.py               ← PricePoint, PriceAggregates, CardMarketData
  repositories/app_integration/ebay/
    ApiFinding_repository.py      ← EbayFindingAPIRepository
  services/app_integration/ebay/
    market_price_service.py       ← fetch_card_market_price service
api/routers/integrations/ebay/
  ebay_market.py                  ← GET /market-price router
notebooks/
  ebay_price_research.ipynb       ← demo notebook
```

---

## Data Models

### `core/models/ebay/market_price.py`

```python
class PricePoint(BaseModel):
    item_id: str
    title: str
    price: float
    currency: str
    condition: Optional[str]
    url: Optional[str]
    sold_date: Optional[datetime]   # None for active listings
    relevance_score: float          # 0.0–1.0; results below threshold are excluded

class PriceAggregates(BaseModel):
    count: int
    min: Optional[float]
    max: Optional[float]
    mean: Optional[float]
    median: Optional[float]
    p25: Optional[float]
    p75: Optional[float]

class CardMarketData(BaseModel):
    query: str                      # the keyword string sent to eBay
    card_name: str
    set_code: Optional[str]
    condition_id: Optional[int]
    is_foil: Optional[bool]
    frame: Optional[str]
    as_of: datetime
    sold: list[PricePoint]
    active: list[PricePoint]
    sold_aggregates: PriceAggregates
    active_aggregates: PriceAggregates
    suggested_price: Optional[float]  # sold median; None if < 3 sold results
```

`PriceAggregates` is computed with Python's `statistics` module (no extra dependencies). `p25` / `p75` use `statistics.quantiles`.

---

## Repository Layer

### `EbayFindingAPIRepository`

**Base URL:**
- Sandbox: `https://svcs.sandbox.ebay.com/services/search/FindingService/v1`
- Production: `https://svcs.ebay.com/services/search/FindingService/v1`

**Auth header:** `X-EBAY-SOA-SECURITY-APPNAME: <APP_ID>` (app-level, from `settings.ebay_app_id`)

**Method:** `find_completed_items(keywords, category_ids, condition_ids, min_date, limit)`

- Sends a `findCompletedItems` XML request (same XML pattern as the existing Trading API in `xml_utils.py`)
- Parses the XML response into a list of `PricePoint` dicts
- Category ID for MTG cards — verify during implementation (likely 2536 "Magic: The Gathering" under 183454 "Collectible Card Games"; 213 is a top-level placeholder)
- `min_date` enforces the `days_back` lookback window

The Browse API is called via the existing `EbayBrowseAPIRepository.search_items` with category 213 + optional `conditionIds` filter.

---

## Service Layer

### `fetch_card_market_price`

Registered: `@ServiceRegistry.register(path="integrations.ebay.market_price", ...)`

**Inputs:**

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `card_name` | str | required | e.g. `"Sheoldred, the Apocalypse"` |
| `token` | str | required | User OAuth token for Browse API |
| `set_code` | str \| None | None | e.g. `"DMR"` |
| `condition_id` | int \| None | None | eBay condition ID |
| `is_foil` | bool \| None | None | Foil / non-foil |
| `frame` | str \| None | None | `"showcase"`, `"extended_art"`, `"borderless"`, `"normal"` |
| `days_back` | int | 30 | Lookback window for sold items, max 90 |
| `limit` | int | 50 | Max results per source, max 200 |
| `match_threshold` | float | 0.6 | Results below this relevance score are dropped |

**Steps:**

1. **Build query string** — strip punctuation from `card_name`, append `set_code`, `"foil"` / `"non-foil"` if `is_foil` is set, frame variant if provided, `"MTG"` suffix.
2. **Concurrent fetch** — `asyncio.gather(find_completed_items(...), search_items(...))`.
3. **Score & filter** — run relevance scorer on every returned title; drop results below `match_threshold`.
4. **Aggregate** — compute `PriceAggregates` for sold and active sets separately.
5. **Suggested price** — sold median if `sold_aggregates.count >= 3`, else `None`.
6. Return `CardMarketData`.

### Relevance Scorer

Pure function `score_title(title: str, card_name: str, set_code, is_foil, frame) -> float`.

| Signal | Score contribution |
|---|---|
| All card name words present in title | +0.50 |
| Set code or set name present | +0.20 |
| Foil flag matches | +0.15 |
| Frame variant keyword matches | +0.15 |
| Any reject keyword found | → 0.0 (hard exclude) |

**Reject keywords:** `proxy`, `fake`, `alter`, `custom`, `token`, `lot`, `playset`, `bundle`, `signed`, `PSA`, `BGS`, `CGC`, `graded`, `reprint lot`

---

## API Endpoint

**Router:** `api/routers/integrations/ebay/ebay_market.py`
Mounted at `/api/v1/integrations/ebay/market-price` (registered in the main router alongside existing eBay routers).

```
GET /api/v1/integrations/ebay/market-price
```

**Query parameters:**

| Param | Type | Default |
|---|---|---|
| `card_name` | str | required |
| `app_code` | str | required |
| `set_code` | str | None |
| `condition_id` | int | None |
| `is_foil` | bool | None |
| `frame` | str | None |
| `days_back` | int | 30 |
| `limit` | int | 50 |
| `match_threshold` | float | 0.6 |

**Response:** `CardMarketData` as JSON.

**Auth flow:** The router resolves `app_code` → user OAuth token (same pattern as existing listing endpoints) and passes the token to the service. The service passes it to the Browse API call; the Finding API call uses the App ID from settings.

**Error handling:**
- If the Browse API call fails, return partial data with `active: []` and `active_aggregates.count: 0`.
- If the Finding API call fails, return partial data with `sold: []` and `suggested_price: null`.
- Either partial result is still useful; both failing raises a 502.

---

## Notebook

**File:** `notebooks/ebay_price_research.ipynb`

Dependencies: `httpx`, `pandas`, `matplotlib` (all lightweight).

| Cell | Content |
|---|---|
| 1 — Config | `BASE_URL`, `APP_CODE`, card inputs: `card_name`, `set_code`, `is_foil`, `frame`, `condition_id` |
| 2 — Fetch | `httpx.get(...)` call; pretty-print `CardMarketData` summary |
| 3 — DataFrames | Two `pd.DataFrame` tables (sold, active), sorted by relevance score descending |
| 4 — Distribution chart | Side-by-side histogram: sold (blue) vs active (orange), vertical median lines, IQR band |
| 5 — Price suggestion box | Prints `suggested_price`, `sold_aggregates` summary (count, median, p25–p75), active floor |
| 6 — Threshold tuning | Re-runs fetch with `match_threshold=0.4` to show impact of looser/tighter relevance filtering |

---

## What This Is Not

- No pricing strategies (those are a separate spec).
- No frontend UI changes.
- No caching layer (can be added later via Redis TTL on the endpoint).
- No stale listing detection (separate feature).
