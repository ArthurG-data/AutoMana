# eBay Local Sales Read Path — Design Spec

**Date:** 2026-05-21
**Branch:** worktree-feat+ebay-sales-persistence
**Status:** Approved

## Problem

The "Sold" tab in the AutoMana frontend calls `GET /integrations/ebay/listing/history`, which proxies the live eBay Fulfillment API. The eBay API has a 90-day window; AutoMana already runs a nightly Celery job (`ebay-sync-own-sales-nightly`) that persists sold orders into `app_integration.ebay_order_source_product`, but nothing reads that table back to the UI.

## Goal

Wire up a local-DB read path so the "Sold" tab shows locally-persisted orders instead of hitting the live eBay API. Fee/payout fields (`ebayFee`, `netPayout`) will be null for locally-stored rows; the frontend table already renders `—` for nulls.

## Scope

Six surgical changes in dependency order. No schema migrations required. No new Celery tasks.

---

## Layer 1 — SQL (`sales_queries.py`)

Two new constants appended to the existing file.

### `GET_LOCAL_SALES_PAGINATED`

```sql
SELECT
    osp.order_id,
    eos.local_status,
    MAX(osp.buyer_username)        AS buyer_username,
    MAX(osp.sold_at)               AS sold_at,
    MAX(osp.currency)              AS currency,
    SUM(osp.sold_price_cents)::INT AS total_price_cents,
    json_agg(json_build_object(
        'legacyItemId', osp.item_id,
        'title',        osp.title,
        'quantity',     osp.quantity
    ) ORDER BY osp.ebay_osp_id)    AS line_items
FROM app_integration.ebay_order_source_product osp
JOIN app_integration.ebay_order_status eos
    ON eos.order_id = osp.order_id AND eos.app_code = osp.app_code
WHERE osp.app_code = $1
GROUP BY osp.order_id, eos.local_status
ORDER BY MAX(osp.sold_at) DESC
LIMIT $2 OFFSET $3;
```

Groups by `(order_id, local_status)` so multi-item orders become one row with an aggregated `line_items` JSON array. `sold_price_cents` is summed across line items for `total_price_cents`.

### `COUNT_LOCAL_SALES`

```sql
SELECT COUNT(DISTINCT order_id)
FROM app_integration.ebay_order_source_product
WHERE app_code = $1;
```

Separate count query for pagination total — avoids a window function on the main query.

---

## Layer 2 — Repository (`sales_repository.py`)

One new method added to `EbaySalesRepository`:

```python
async def list_local_sales(
    self, app_code: str, limit: int, offset: int
) -> tuple[list[dict], int]:
```

Runs `GET_LOCAL_SALES_PAGINATED` and `COUNT_LOCAL_SALES` sequentially (two awaits). Returns `(rows_as_dicts, total_count_int)`.

---

## Layer 3 — Service (`local_sales_service.py`)

New file: `src/automana/core/services/app_integration/ebay/local_sales_service.py`

Registered as:
```python
@ServiceRegistry.register(
    path="integrations.ebay.selling.local_sales.list",
    db_repositories=["ebay_sales"],
    runs_in_transaction=False,
)
async def list_local_sales(
    ebay_sales_repository: EbaySalesRepository,
    app_code: str,
    limit: int = 25,
    offset: int = 0,
    **kwargs,
) -> dict:
```

Returns:
```json
{
  "items": [
    {
      "order_id": "...",
      "local_status": "sold",
      "buyer_username": "...",
      "sold_at": "2025-01-01T12:00:00+00:00",
      "currency": "AUD",
      "total_price_cents": 1250,
      "line_items": [{"legacyItemId": "...", "title": "...", "quantity": 1}]
    }
  ],
  "total": 42,
  "has_more": true
}
```

All fields are snake_case. No reshaping to eBay API format in this layer.

---

## Layer 4 — Router (`ebay_selling.py`)

New endpoint appended to `ebay_listing_router`:

```python
@ebay_listing_router.get("/local-history", description="Get locally-synced sold orders")
async def get_local_order_history(
    user: CurrentUserDep,
    service_manager: ServiceManagerDep,
    app_code: str = Query(...),
    limit: Annotated[int, Query(gt=0, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
):
```

- `CurrentUserDep` enforces authentication (same as every other endpoint).
- Does **not** pass `user_id` to the service — no eBay API token needed.
- Returns `PaginatedResponse` with `PaginationInfo`.
- `app_code` query param scopes results to the caller's eBay app.

---

## Layer 5 — Service Module Registration (`service_modules.py`)

Add `"automana.core.services.app_integration.ebay.local_sales_service"` to **all three** lists that currently contain `sales_sync_service` (lines 21, 57, 91 in the current file).

---

## Layer 6 — Frontend

### `soldOrders.ts` — new mapper

Add `mapLocalOrderToSoldOrder(raw, appCode, appName): SoldOrder`:

- `orderId` ← `raw.order_id`
- `creationDate` ← `raw.sold_at`
- `buyerUsername` ← `raw.buyer_username`
- `totalAmount` ← `raw.total_price_cents / 100`
- `currency` ← `raw.currency`
- `lineItems` ← map `raw.line_items` array (fields: `legacyItemId`, `title`, `quantity`; `lineItemId` and `lineItemFulfillmentStatus` set to `null`)
- `local_status` ← `raw.local_status`
- `displayStatus` ← `deriveDisplayStatus(null, raw.local_status)`
- `legacyOrderId`, `orderFulfillmentStatus`, `orderPaymentStatus` → `null`
- `ebayFee`, `netPayout`, `shippingCollected` → `null`
- `itemSubtotal` ← same as `totalAmount` (best local approximation)

The existing `mapRawToSoldOrder` is unchanged and stays in place for any future use of the live eBay endpoint.

### `api.ts` — update `fetchSoldOrders`

Change the API call URL from `/integrations/ebay/listing/history` to `/integrations/ebay/listing/local-history`.

Change the mapper call from `mapRawToSoldOrder(item, appCode, '')` to `mapLocalOrderToSoldOrder(item, appCode, '')`.

No other changes to `api.ts`.

---

## Data Flow

```
Frontend "Sold" tab
  → fetchSoldOrders()
  → GET /integrations/ebay/listing/local-history?app_code=X&limit=25&offset=0
  → get_local_order_history() [router]
  → service_manager.execute_service("integrations.ebay.selling.local_sales.list")
  → list_local_sales() [service]
  → ebay_sales_repository.list_local_sales(app_code, limit, offset)
  → GET_LOCAL_SALES_PAGINATED + COUNT_LOCAL_SALES [SQL]
  → app_integration.ebay_order_source_product JOIN ebay_order_status
  → PaginatedResponse { data: [...], pagination: {...} }
  → mapLocalOrderToSoldOrder() per item
  → SoldOrder[] displayed in SoldOrdersTable
```

---

## What Does NOT Change

- `GET /listing/history` (live eBay API endpoint) — kept as-is, unused by the Sold tab
- `SoldOrdersTable.tsx`, `LifecycleBadge.tsx`, `SoldOrderDetailPanel` — no changes
- `mapRawToSoldOrder` — unchanged
- All nightly sync jobs — unchanged
- No schema migrations required

---

## Testing

**Unit test:** `tests/unit/core/services/ebay/test_local_sales_service.py`

Key cases:
1. Returns paginated items with correct `has_more` flag
2. Empty result (no orders yet for app_code) returns `{"items": [], "total": 0, "has_more": false}`
3. `list_local_sales` is called with correct `app_code`, `limit`, `offset`

Mock `EbaySalesRepository.list_local_sales` — no DB required.
