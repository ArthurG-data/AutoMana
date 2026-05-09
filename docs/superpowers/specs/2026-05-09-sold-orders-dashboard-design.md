# Sold Orders Dashboard — Design Spec

**Date:** 2026-05-09
**Branch:** feat/ebay-hub-docs
**Status:** Approved

---

## Overview

Surface sold-but-not-shipped eBay orders inside the existing Listings page. Each order shows a lifecycle badge (Sold → Sent → In Transit → Complete) and a buyer message indicator. Users can mark an order as sent (with or without a tracking number) directly from the dashboard; the action calls eBay's Fulfillment API so buyer notifications and seller metrics stay in sync.

---

## Lifecycle Stages

| Stage | Icon | Colour | Source |
|---|---|---|---|
| Sold | 💰 | Red | eBay `orderFulfillmentStatus = NOT_STARTED` |
| Sent | 📦 | Blue | eBay `orderFulfillmentStatus = IN_PROGRESS` |
| In Transit | 🚚 | Amber | Local `ebay_order_status.local_status = in_transit` |
| Complete | ✅ | Green | eBay `orderFulfillmentStatus = FULFILLED` |

Display status derivation (priority order):
1. If eBay `orderFulfillmentStatus = FULFILLED` → Complete (eBay always wins for terminal state)
2. If `local_status = in_transit` → In Transit
3. Else map eBay's `orderFulfillmentStatus`: `NOT_STARTED` → Sold, `IN_PROGRESS` → Sent

---

## Data Layer

### New migration table: `app_integration.ebay_order_status`

```sql
CREATE TABLE IF NOT EXISTS app_integration.ebay_order_status (
    order_id        TEXT         NOT NULL,
    app_code        VARCHAR(50)  NOT NULL REFERENCES app_integration.app_info(app_code) ON DELETE CASCADE,
    local_status    TEXT         NOT NULL CHECK (local_status IN ('sold','sent','in_transit','complete')),
    tracking_number TEXT,
    carrier_code    TEXT,
    shipped_at      TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (order_id, app_code)
);
```

- Rows are created only when the user takes an action (mark sent, add tracking, etc.)
- eBay's `orderFulfillmentStatus` remains the primary source; this table holds overrides and extra metadata

---

## Backend

### Augmented endpoint

`GET /integrations/ebay/listing/history` — existing endpoint, augmented:

After fetching orders from eBay, the service bulk-fetches matching rows from `ebay_order_status` and merges them. The response shape gains one optional field per order:

```json
{ "local_status": "in_transit" | null }
```

New repository methods on `app_repository.py`:
- `get_order_statuses(order_ids: list[str], app_code: str) -> dict[str, OrderStatusRow]`
- `upsert_order_status(order_id, app_code, **fields) -> None`

### New endpoints

#### `POST /integrations/ebay/listing/orders/{order_id}/fulfill`

Marks an order as shipped on eBay and records it locally.

Request body:
```json
{
  "app_code": "my-app",
  "line_item_ids": ["1234567890123"],
  "tracking_number": "optional",
  "carrier_code": "optional"
}
```

Actions:
1. Calls `POST /sell/fulfillment/v1/order/{orderId}/shippingFulfillment` on eBay
2. Upserts `ebay_order_status` with `local_status='sent'`, `shipped_at=now()`, tracking fields if provided

New service: `fulfillment_write_service.py`
New repository method: `ApiSelling_repository.create_shipping_fulfillment(order_id, payload)`

#### `PATCH /integrations/ebay/listing/orders/{order_id}/status`

Local-only status transition (no eBay call). Used for In Transit and Complete.

Request body:
```json
{
  "app_code": "my-app",
  "local_status": "in_transit" | "complete"
}
```

Logic lives in `fulfillment_service.py` — too small to warrant its own file.

---

## Frontend

### Modified files

**`src/routes/listings.tsx`**
- Wire up the `"sold"` tab: on switch, call `fetchSoldOrders()` and render `<SoldOrdersTable>` + `<SoldOrderDetailPanel>` in the same split layout used by active listings
- Add sold-count badge to the Sold tab pill (populated once orders are fetched)

**`src/features/ebay/api.ts`** — four new functions:
- `fetchSoldOrders(appCode, limit, offset)` — hits `/listing/history`, maps raw response to `SoldOrder[]`
- `markOrderSent(appCode, orderId, lineItemIds[])` — POST to fulfill endpoint, no tracking
- `markOrderSentWithTracking(appCode, orderId, lineItemIds[], carrier, trackingNumber)` — POST with tracking fields
- `updateOrderLocalStatus(appCode, orderId, status)` — PATCH for in_transit / complete transitions

### New files

**`src/features/ebay/soldOrders.ts`**
- `SoldOrder` type (mapped from `FulfillmentResponse` + `local_status`)
- `deriveDisplayStatus(ebayStatus, localStatus) -> DisplayStatus` helper
- `DisplayStatus` union type: `'sold' | 'sent' | 'in_transit' | 'complete'`

**`src/features/ebay/components/LifecycleBadge.tsx`**
- Props: `status: DisplayStatus`
- Renders the coloured pill (💰 red · 📦 blue · 🚚 amber · ✅ green)
- Shared between `SoldOrdersTable` row and `SoldOrderDetailPanel` header

**`src/features/ebay/components/SoldOrdersTable.tsx`**
- Columns: Card · Price · Buyer · Msg · Status · Sold
- Props: `orders`, `isLoading`, `selectedId`, `onRowClick(orderId)`
- Msg column: speech-bubble icon always shown for non-complete orders (the Fulfillment API response does not carry message counts; the icon is a static shortcut to eBay messages, not a live unread indicator)
- Status column: `<LifecycleBadge>`

**`src/features/ebay/components/SoldOrderDetailPanel.tsx`**
- Lifecycle strip: 4-step progress bar, current step highlighted
- Order info block: price, buyer username, sale date, eBay order ID
- Message banner: static "Messages from buyer" label + "View on eBay ↗" link (no content fetched — eBay Messaging API is out of scope)
- Action buttons (context-sensitive by stage):
  - **Sold stage**: "📦 Mark as sent" (one-click, calls `markOrderSent`) + "🔗 Add tracking number" (inline form → `markOrderSentWithTracking`)
  - **Sent stage**: "🚚 Mark in transit" (calls `updateOrderLocalStatus`)
  - **In Transit stage**: "✅ Mark complete" (calls `updateOrderLocalStatus`)
  - **Complete stage**: no action buttons
- Optimistic UI: status updates immediately in local state; reverts on API error with toast

### CSS module files
- `SoldOrdersTable.module.css`
- `SoldOrderDetailPanel.module.css`
- `LifecycleBadge.module.css`

---

## Out of Scope (v1)

- Fetching buyer message content or unread count via Commerce Messaging API — message indicator links to eBay messages only
- Pagination for the Sold tab (eBay's history endpoint returns newest first; initial load of 25 is sufficient)
- Automated "In Transit → Complete" based on tracking updates (no tracking API integration)

---

## Files to Create / Modify

### Backend
| Action | File |
|---|---|
| New migration | `database/SQL/migrations/migration_26_ebay_order_status.sql` |
| New service | `core/services/app_integration/ebay/fulfillment_write_service.py` |
| Augment service | `core/services/app_integration/ebay/fulfillment_service.py` |
| New repo method | `core/repositories/app_integration/ebay/ApiSelling_repository.py` |
| New repo methods | `core/repositories/app_integration/ebay/app_repository.py` |
| New router endpoints | `api/routers/integrations/ebay/ebay_selling.py` |

### Frontend
| Action | File |
|---|---|
| Modify | `src/routes/listings.tsx` |
| Modify | `src/features/ebay/api.ts` |
| New | `src/features/ebay/soldOrders.ts` |
| New | `src/features/ebay/components/LifecycleBadge.tsx` + `.module.css` |
| New | `src/features/ebay/components/SoldOrdersTable.tsx` + `.module.css` |
| New | `src/features/ebay/components/SoldOrderDetailPanel.tsx` + `.module.css` |
