# Strategy Integration Design

**Date:** 2026-05-14
**Status:** Approved
**Scope:** Phase 1 — wire existing pricing strategies into the listings UI with a staged action queue. Phase 2 (LangChain agent) is documented but not in scope.

---

## Problem

The `PricingStrategyManager` and three Python pricing strategies (`QuickSaleStrategy`, `CompetitiveStrategy`, `PremiumStrategy`) exist in `core/services/analytics/strategies.py` but are disconnected from the listings UI. The five frontend strategy cards in `StrategyCard.tsx` use the listing's own price as a market proxy, the "Apply strategy" button does nothing, and the listings table has no per-listing intelligence.

---

## Goals

- Display strategy recommendations in the listings table (summary badge per row)
- Display the full strategy breakdown in the listing detail panel
- Let the user stage an action (Raise / Lower / Hold / Draft) that Celery executes against eBay
- Design Phase 1 interfaces to be agent-ready for Phase 2 with zero refactoring

---

## Architecture

```
eBay API → listings.tsx (fetch active listings)
                ↓
    GET /api/v1/ebay/listings/{item_id}/recommendation
                ↓
    RecommendationService
      ├── behavioral signals (daysListed, watchCount, price)
      └── market data (pricing.price_observation, if available)
                ↓
    PricingStrategyManager.recommend_strategy()
                ↓
    {suggested_action, suggested_price, strategy_kind, confidence, signals_used, all_strategies}
                ↓
    Frontend renders:
      ├── Table column: "↑ Raise $2.50" | "↓ Lower $1.00" | "⏸ Hold" | "◻ Draft"
      └── Detail panel: all 5 strategy cards, recommended pre-selected, "Stage action" button
                ↓
    POST /api/v1/ebay/listings/{item_id}/actions → listing_pending_actions (DB)
                ↓
    Celery task: drain_listing_actions → eBay API (revise price or end listing)
```

---

## Action Vocabulary

Four possible suggested actions:

| Action | Meaning | Maps to strategy |
|--------|---------|-----------------|
| `raise` | Increase price to strategy target | `PremiumStrategy` → `max` kind |
| `lower` | Decrease price to strategy target | `QuickSaleStrategy` → `quick` kind |
| `hold` | No change needed | `CompetitiveStrategy` → `balanced` kind |
| `draft` | Pull from eBay, save as draft | No price strategy |

### Signal Rules (behavioral fallback — no market data)

```
daysListed > 30 AND watchCount == 0  →  draft
daysListed > 14 AND watchCount < 2   →  lower  (QuickSaleStrategy)
daysListed < 7  AND watchCount >= 5  →  raise  (PremiumStrategy)
otherwise                            →  hold   (CompetitiveStrategy)
```

### Signal Rules (market data available — `pricing.price_observation`)

```
listed_price < p25 * 0.95            →  raise (already priced below market bottom)
listed_price > p75 * 1.05            →  lower (overpriced vs market top)
daysListed > 14 AND listed ≈ p25     →  draft (cheap and not moving)
otherwise                            →  PricingStrategyManager.recommend_strategy()
```

When market data is available it takes precedence over behavioral rules. `signals_used` in the response declares which path was taken.

---

## Strategy → Frontend Kind Mapping

| Python strategy | Frontend `StrategyKind` | Status |
|-----------------|------------------------|--------|
| `QuickSaleStrategy` | `quick` | Active |
| `CompetitiveStrategy` | `balanced` | Active |
| `PremiumStrategy` | `max` | Active |
| `Auction7Strategy` | `auction7` | Future (Phase 2+) |
| `AuctionReserveStrategy` | `auctionReserve` | Future (Phase 2+) |

`auction7` and `auctionReserve` display on the frontend using the existing `pctRange`-based price calculation. The recommendation engine never selects them until their Python strategies are implemented.

---

## Database

### New table: `app_integration.listing_pending_actions`

```sql
CREATE TABLE app_integration.listing_pending_actions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    item_id         TEXT        NOT NULL,
    user_id         UUID        NOT NULL REFERENCES auth.users(id),
    app_code        TEXT        NOT NULL,
    action_type     TEXT        NOT NULL CHECK (action_type IN ('raise','lower','hold','draft')),
    strategy_kind   TEXT        NOT NULL,
    suggested_price NUMERIC(10,2),
    status          TEXT        NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','processing','done','failed')),
    error           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    executed_at     TIMESTAMPTZ
);

CREATE INDEX ON app_integration.listing_pending_actions (status, created_at)
    WHERE status = 'pending';
CREATE INDEX ON app_integration.listing_pending_actions (item_id);
```

Delivered as `migration_28_listing_pending_actions.sql`.

---

## Backend

### New service: `listing_recommendation_service.py`

Location: `core/services/app_integration/ebay/listing_recommendation_service.py`

```
Input:
  item_id: str
  listing_signals: dict          # daysListed, watchCount, price, currency
  market_data: dict | None       # percentiles from pricing.price_observation

Output (ListingRecommendation):
  suggested_action: Literal['raise','lower','hold','draft']
  suggested_price: float | None
  strategy_kind: StrategyKind
  confidence: float              # 0.0–1.0
  signals_used: Literal['behavioral','market']  # 'market' = percentiles available; 'behavioral' = fallback
  all_strategies: dict[str, PricingResult]
```

Logic:
1. If `market_data` is available and has percentiles → use market signal rules + `PricingStrategyManager`
2. Otherwise → apply behavioral signal rules to select strategy
3. Call `strategy.calculate_price(stats, percentiles, market_conditions)`
4. Return `ListingRecommendation`

The service is a pure function (no DB access) so it wraps directly into a LangChain `@tool` in Phase 2.

### New repository: `listing_actions_repository.py`

Location: `core/repositories/app_integration/ebay/listing_actions_repository.py`

Methods:
- `insert_action(user_id, item_id, app_code, action_type, strategy_kind, suggested_price) → UUID`
- `get_pending_actions(limit=50) → list[PendingAction]`
- `mark_processing(action_id) → None`
- `mark_done(action_id) → None`
- `mark_failed(action_id, error) → None`
- `get_pending_for_item(item_id) → PendingAction | None`

### New endpoints (in existing eBay router)

```
GET  /api/v1/ebay/listings/{item_id}/recommendation
     Query params: days_listed, watch_count, price, currency
     Response: ListingRecommendation

POST /api/v1/ebay/listings/{item_id}/actions
     Body: {action_type, strategy_kind, suggested_price, app_code}
     Response: {action_id, status: 'pending'}

GET  /api/v1/ebay/listings/{item_id}/actions/pending
     Response: PendingAction | null
```

The recommendation endpoint accepts listing signals as query params so the frontend can call it immediately after fetching listings without a separate DB lookup.

---

## Celery Task

### `drain_listing_actions`

Location: `worker/tasks/pipelines.py` (new task entry) or a dedicated `worker/tasks/ebay_actions.py`

Schedule: every 5 minutes via Celery beat

Logic per pending action:
- `raise` / `lower` → call `listings_write_service.update_listing()` with `suggested_price`
- `draft` → call eBay `endItem` API, insert row into `app_integration.saved_drafts`. This table is out of scope for Phase 1 — if `draft` action is executed before the table exists, log a warning and mark the action `failed`. A follow-up design will spec `saved_drafts` fully.
- `hold` → mark done immediately (no eBay call needed). Note: the UI "Stage action" button does not appear for `hold` recommendations — `hold` rows only enter the queue from the Phase 2 agent acting in bulk.
- On success: `mark_done(action_id)`
- On failure: `mark_failed(action_id, error)`, retry up to 3× with exponential backoff at the `run_service` level

---

## Frontend

### `EbayLiveListing` type additions

```typescript
recommendation?: {
  suggested_action: 'raise' | 'lower' | 'hold' | 'draft'
  suggested_price: number | null
  strategy_kind: StrategyKind
  confidence: number
  signals_used: 'behavioral' | 'market'
}
pendingAction?: {
  action_id: string
  action_type: 'raise' | 'lower' | 'hold' | 'draft'
  status: 'pending' | 'processing' | 'done' | 'failed'
}
```

### Listings table — new "Signal" column

Rendered after existing columns. Lazy-loaded: after listings are fetched, fire `GET /recommendation` per listing serially (bounded by the existing IntersectionObserver viewport). A future batch endpoint (`POST /recommendations/batch`) will replace this. Shows:

| State | Badge |
|-------|-------|
| Loading | `·· ·` (skeleton) |
| `raise` | `↑ Raise $X.XX` (accent) |
| `lower` | `↓ Lower $X.XX` (warning yellow) |
| `hold` | `⏸ Hold` (neutral) |
| `draft` | `◻ Draft` (muted red) |
| Pending action staged | `⏳ Queued` |
| No data | `—` |

### Detail panel — strategy advisor section

Added to `ListingDetailPanel` (not the standalone `listing.$id.tsx` page, which can remain as-is for now):

- All 5 `StrategyCard` components rendered
- Backend-recommended strategy kind pre-selected
- Confidence badge: Low (< 0.7) / Medium (0.7–0.85) / High (> 0.85)
- `signals_used` label: "Based on market data" or "Based on listing activity"
- "Stage action" button → `POST /actions` → updates `pendingAction` in store
- If `pendingAction` exists: show "Action queued — waiting for sync" banner with action details
- `auction7` and `auctionReserve` cards show frontend-computed price with a "No backend data" footnote

---

## Phase 2: LangChain Agent (planned — not in scope)

Documented here so Phase 1 interfaces support it without refactoring.

### Agent tools (Phase 2)

Each wraps a Phase 1 service or endpoint with no internal changes:

```python
@tool
def get_listing_recommendation(item_id: str, days_listed: int, watch_count: int, price: float) -> dict:
    """Returns suggested action and price for a single listing."""
    # calls listing_recommendation_service directly

@tool
def stage_listing_action(item_id: str, action_type: str, strategy_kind: str, suggested_price: float, app_code: str) -> dict:
    """Stages an action to be executed against eBay."""
    # calls listing_actions_repository.insert_action

@tool
def get_all_active_listings(app_code: str) -> list[dict]:
    """Returns all active listings with signals for the given app."""
```

### Agent entry point

A chat sidebar on the listings page. User sends natural language ("move all stale listings fast") → agent fetches all listings, calls `get_listing_recommendation` per listing, filters by action type, calls `stage_listing_action` in bulk.

### Strategy tools (Phase 2)

Each Python strategy gets a `@tool` wrapper:

```python
@tool
def apply_quick_sale_strategy(stats: dict, percentiles: dict, market_data: dict) -> dict: ...
@tool
def apply_competitive_strategy(stats: dict, percentiles: dict, market_data: dict) -> dict: ...
@tool
def apply_premium_strategy(stats: dict, percentiles: dict, market_data: dict) -> dict: ...
```

`Auction7Strategy` and `AuctionReserveStrategy` are implemented in this phase.

---

## Future Strategy Improvements

| Strategy | Current limitation | Improvement path |
|----------|--------------------|-----------------|
| `QuickSaleStrategy` | Flat 5% volatility discount | Calibrate with days-to-sell from `sales_sync_service` sold history |
| `CompetitiveStrategy` | Competition level from `total_listings > 20` | Real supply/demand ratio from MTGStock per-card |
| `PremiumStrategy` | `card_rarity` hardcoded to `'rare'` | Read from `card_catalog` (already in DB) |
| `PremiumStrategy` | `seller_reputation` hardcoded to `'high'` | Read from eBay seller profile API |
| All strategies | Volatility from one-shot active listings snapshot | 30-day trend from `pricing.price_observation` |
| `Auction7Strategy` | Does not exist | Phase 2: starting bid = p10, 7-day duration |
| `AuctionReserveStrategy` | Does not exist | Phase 2: starting bid = p25, reserve = p50 |

---

## Files to Create / Modify

### New files
- `database/SQL/migrations/migration_28_listing_pending_actions.sql`
- `core/services/app_integration/ebay/listing_recommendation_service.py`
- `core/repositories/app_integration/ebay/listing_actions_repository.py`
- `src/frontend/src/features/ebay/components/SignalBadge.tsx`
- `src/frontend/src/features/ebay/components/SignalBadge.module.css`

### Modified files
- `core/service_modules.py` — register new service
- `api/routers/integrations/ebay/__init__.py` — add 3 new endpoints
- `worker/tasks/` — add `drain_listing_actions` task
- `worker/celeryconfig.py` — add beat schedule entry
- `src/frontend/src/features/ebay/mockListings.ts` — extend `EbayLiveListing` type
- `src/frontend/src/store/listings.ts` — add `recommendation` and `pendingAction` fields
- `src/frontend/src/routes/listings.tsx` — fetch recommendations after listing load, add Signal column
- `src/frontend/src/features/ebay/components/ListingsTable.tsx` — add Signal column
- `src/frontend/src/features/ebay/components/ListingDetailPanel.tsx` — add strategy advisor section
- `src/frontend/src/features/ebay/api.ts` — add recommendation + action API calls
