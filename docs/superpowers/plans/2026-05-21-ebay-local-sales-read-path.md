# eBay Local Sales Read Path Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the "Sold" tab to read from the local `ebay_order_source_product` table instead of the live eBay API.

**Architecture:** Add a SQL query → repository method → registered service → router endpoint chain on the backend. On the frontend, add a local-format mapper and point `fetchSoldOrders` at the new endpoint. No schema migrations, no new Celery tasks.

**Tech Stack:** Python/asyncpg (backend), FastAPI/ServiceRegistry pattern, TypeScript/Vitest (frontend).

---

## File Map

| Action | File |
|--------|------|
| Modify | `src/automana/core/repositories/app_integration/ebay/sales_queries.py` |
| Modify | `src/automana/core/repositories/app_integration/ebay/sales_repository.py` |
| Modify | `tests/unit/core/repositories/app_integration/ebay/test_sales_repository.py` |
| Create | `src/automana/core/services/app_integration/ebay/local_sales_service.py` |
| Create | `tests/unit/core/services/ebay/test_local_sales_service.py` |
| Modify | `src/automana/api/routers/integrations/ebay/ebay_selling.py` |
| Modify | `src/automana/core/framework/service_modules.py` |
| Modify | `src/frontend/src/features/ebay/soldOrders.ts` |
| Modify | `src/frontend/src/features/ebay/__tests__/soldOrders.test.ts` |
| Modify | `src/frontend/src/features/ebay/api.ts` |
| Modify | `src/frontend/src/features/ebay/__tests__/api.sold.test.ts` |

---

## Setup

**Frontend test prerequisite (worktree only):** The worktree does not have `node_modules` pre-installed. Before running any frontend test commands, symlink the main repo's node_modules into the worktree:

```bash
ln -s /home/arthur/projects/AutoMana/src/frontend/node_modules \
  src/frontend/node_modules
```

Run this once. All subsequent `node_modules/.bin/vitest` commands below assume this symlink exists and are run from `src/frontend/`.

---

## Task 1: SQL Queries + Repository Method

**Files:**
- Modify: `src/automana/core/repositories/app_integration/ebay/sales_queries.py`
- Modify: `src/automana/core/repositories/app_integration/ebay/sales_repository.py`
- Modify: `tests/unit/core/repositories/app_integration/ebay/test_sales_repository.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/core/repositories/app_integration/ebay/test_sales_repository.py`:

```python
@pytest.mark.asyncio
async def test_list_local_sales_returns_rows_and_total(repo):
    repo.execute_query.side_effect = [
        [
            {
                "order_id": "ord-1",
                "local_status": "sold",
                "buyer_username": "bob",
                "sold_at": datetime(2025, 1, 1, tzinfo=timezone.utc),
                "currency": "AUD",
                "total_price_cents": 1000,
                "line_items": [],
            }
        ],
        [{"total": 1}],
    ]
    rows, total = await repo.list_local_sales("my-app", limit=25, offset=0)
    assert total == 1
    assert rows[0]["order_id"] == "ord-1"
    assert rows[0]["total_price_cents"] == 1000


@pytest.mark.asyncio
async def test_list_local_sales_empty_returns_zero_total(repo):
    repo.execute_query.side_effect = [[], [{"total": 0}]]
    rows, total = await repo.list_local_sales("my-app", limit=25, offset=0)
    assert rows == []
    assert total == 0


@pytest.mark.asyncio
async def test_list_local_sales_passes_correct_args(repo):
    repo.execute_query.side_effect = [[], [{"total": 0}]]
    await repo.list_local_sales("app-X", limit=10, offset=30)
    first_call_args = repo.execute_query.call_args_list[0][0][1]
    assert first_call_args == ("app-X", 10, 30)
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
python3 -m pytest tests/unit/core/repositories/app_integration/ebay/test_sales_repository.py \
  -k "list_local_sales" -v
```

Expected: 3 errors — `AttributeError: EbaySalesRepository has no attribute 'list_local_sales'`

- [ ] **Step 3: Add SQL queries**

Append to `src/automana/core/repositories/app_integration/ebay/sales_queries.py`:

```python
GET_LOCAL_SALES_PAGINATED = """
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
"""

COUNT_LOCAL_SALES = """
SELECT COUNT(DISTINCT order_id) AS total
FROM app_integration.ebay_order_source_product
WHERE app_code = $1;
"""
```

- [ ] **Step 4: Add repository method**

Append to `EbaySalesRepository` in `src/automana/core/repositories/app_integration/ebay/sales_repository.py`:

```python
    async def list_local_sales(
        self, app_code: str, limit: int, offset: int
    ) -> tuple[list[dict], int]:
        rows = await self.execute_query(
            sales_queries.GET_LOCAL_SALES_PAGINATED,
            (app_code, limit, offset),
        )
        count_rows = await self.execute_query(
            sales_queries.COUNT_LOCAL_SALES,
            (app_code,),
        )
        total = count_rows[0]["total"] if count_rows else 0
        return [dict(r) for r in rows], int(total)
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
python3 -m pytest tests/unit/core/repositories/app_integration/ebay/test_sales_repository.py -v
```

Expected: all 14 tests pass.

- [ ] **Step 6: Commit**

```bash
git add \
  src/automana/core/repositories/app_integration/ebay/sales_queries.py \
  src/automana/core/repositories/app_integration/ebay/sales_repository.py \
  tests/unit/core/repositories/app_integration/ebay/test_sales_repository.py
git commit -m "feat(ebay): add local sales paginated query and repository method"
```

---

## Task 2: Local Sales Service

**Files:**
- Create: `src/automana/core/services/app_integration/ebay/local_sales_service.py`
- Create: `tests/unit/core/services/ebay/test_local_sales_service.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/core/services/ebay/test_local_sales_service.py`:

```python
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from automana.core.services.app_integration.ebay.local_sales_service import (
    list_local_sales,
)


def _repo(rows, total):
    r = MagicMock()
    r.list_local_sales = AsyncMock(return_value=(rows, total))
    return r


@pytest.mark.asyncio
async def test_returns_items_and_pagination():
    row = {
        "order_id": "ord-1",
        "local_status": "sold",
        "buyer_username": "bob",
        "sold_at": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "currency": "AUD",
        "total_price_cents": 1000,
        "line_items": [],
    }
    result = await list_local_sales(
        ebay_sales_repository=_repo([row], 1),
        app_code="my-app",
        limit=25,
        offset=0,
    )
    assert result["total"] == 1
    assert result["has_more"] is False
    assert result["items"][0]["order_id"] == "ord-1"


@pytest.mark.asyncio
async def test_has_more_true_when_more_rows_exist():
    rows = [{"order_id": f"ord-{i}"} for i in range(25)]
    result = await list_local_sales(
        ebay_sales_repository=_repo(rows, 100),
        app_code="my-app",
        limit=25,
        offset=0,
    )
    assert result["has_more"] is True


@pytest.mark.asyncio
async def test_has_more_false_at_last_page():
    rows = [{"order_id": "ord-1"}]
    result = await list_local_sales(
        ebay_sales_repository=_repo(rows, 26),
        app_code="my-app",
        limit=25,
        offset=25,
    )
    assert result["has_more"] is False


@pytest.mark.asyncio
async def test_empty_result():
    result = await list_local_sales(
        ebay_sales_repository=_repo([], 0),
        app_code="my-app",
        limit=25,
        offset=0,
    )
    assert result == {"items": [], "total": 0, "has_more": False}


@pytest.mark.asyncio
async def test_passes_app_code_and_pagination_to_repo():
    repo = _repo([], 0)
    await list_local_sales(
        ebay_sales_repository=repo,
        app_code="app-X",
        limit=10,
        offset=30,
    )
    repo.list_local_sales.assert_called_once_with(
        app_code="app-X", limit=10, offset=30
    )
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
python3 -m pytest tests/unit/core/services/ebay/test_local_sales_service.py -v
```

Expected: `ModuleNotFoundError: No module named 'automana.core.services.app_integration.ebay.local_sales_service'`

- [ ] **Step 3: Create the service file**

Create `src/automana/core/services/app_integration/ebay/local_sales_service.py`:

```python
"""Read-only service for locally-persisted eBay sold orders."""
from __future__ import annotations

import logging
from typing import Any

from automana.core.repositories.app_integration.ebay.sales_repository import (
    EbaySalesRepository,
)
from automana.core.framework.registry import ServiceRegistry

logger = logging.getLogger(__name__)


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
    **kwargs: Any,
) -> dict:
    """Return paginated locally-persisted sold orders for an eBay app."""
    rows, total = await ebay_sales_repository.list_local_sales(
        app_code=app_code,
        limit=limit,
        offset=offset,
    )
    has_more = (offset + len(rows)) < total
    logger.info(
        "ebay_local_sales_listed",
        extra={"app_code": app_code, "total": total, "returned": len(rows)},
    )
    return {"items": rows, "total": total, "has_more": has_more}
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
python3 -m pytest tests/unit/core/services/ebay/test_local_sales_service.py -v
```

Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add \
  src/automana/core/services/app_integration/ebay/local_sales_service.py \
  tests/unit/core/services/ebay/test_local_sales_service.py
git commit -m "feat(ebay): add local_sales_service for DB-backed sold order reads"
```

---

## Task 3: Router Endpoint + Service Registration

**Files:**
- Modify: `src/automana/api/routers/integrations/ebay/ebay_selling.py`
- Modify: `src/automana/core/framework/service_modules.py`

No unit test for this task — routing + module wiring is covered by integration tests and smoke-tested manually.

- [ ] **Step 1: Add the router endpoint**

Append the following to `src/automana/api/routers/integrations/ebay/ebay_selling.py`, after the `patch_order_status` endpoint (after line 326):

```python
@ebay_listing_router.get("/local-history", description="Get locally-synced sold orders")
async def get_local_order_history(
    user: CurrentUserDep,
    service_manager: ServiceManagerDep,
    app_code: str = Query(..., description="eBay application code"),
    limit: Annotated[int, Query(gt=0, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    try:
        result = await service_manager.execute_service(
            "integrations.ebay.selling.local_sales.list",
            app_code=app_code,
            limit=limit,
            offset=offset,
        )
        return PaginatedResponse(
            message="Local sold orders retrieved successfully",
            data=result["items"],
            pagination=PaginationInfo(
                limit=limit,
                offset=offset,
                total_count=result["total"],
                has_next=result["has_more"],
                has_previous=offset > 0,
            ),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
```

- [ ] **Step 2: Register the service module**

In `src/automana/core/framework/service_modules.py`, add `"automana.core.services.app_integration.ebay.local_sales_service"` after `sales_sync_service` in both the `"backend"` list (after line 21) and the `"all"` list (after line 90). Do NOT add it to `"celery"` — this is a request-time read service, not a background job.

After edit, the `"backend"` block should look like:
```python
"automana.core.services.app_integration.ebay.sales_sync_service",
"automana.core.services.app_integration.ebay.local_sales_service",
"automana.core.services.app_integration.ebay.scrape_sold_service",
```

And the `"all"` block should look like:
```python
"automana.core.services.app_integration.ebay.sales_sync_service",
"automana.core.services.app_integration.ebay.local_sales_service",
"automana.core.services.app_integration.ebay.scrape_sold_service",
```

- [ ] **Step 3: Verify the app can be imported cleanly**

```bash
python3 -c "from automana.api.routers.integrations.ebay.ebay_selling import ebay_listing_router; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add \
  src/automana/api/routers/integrations/ebay/ebay_selling.py \
  src/automana/core/framework/service_modules.py
git commit -m "feat(ebay): add GET /listing/local-history endpoint and register service module"
```

---

## Task 4: Frontend Mapper

**Files:**
- Modify: `src/frontend/src/features/ebay/soldOrders.ts`
- Modify: `src/frontend/src/features/ebay/__tests__/soldOrders.test.ts`

- [ ] **Step 1: Write the failing tests**

Append to `src/frontend/src/features/ebay/__tests__/soldOrders.test.ts`:

```typescript
import { mapLocalOrderToSoldOrder } from '../soldOrders'

const BASE_RAW = {
  order_id: 'ord-123',
  local_status: 'sold',
  buyer_username: 'buyer_oz',
  sold_at: '2025-01-01T00:00:00Z',
  currency: 'AUD',
  total_price_cents: 1250,
  line_items: [
    { legacyItemId: 'item-1', title: 'Lightning Bolt', quantity: 2 },
  ],
}

describe('mapLocalOrderToSoldOrder', () => {
  it('maps core fields', () => {
    const order = mapLocalOrderToSoldOrder(BASE_RAW, 'myapp', '')
    expect(order.orderId).toBe('ord-123')
    expect(order.buyerUsername).toBe('buyer_oz')
    expect(order.totalAmount).toBe(12.5)
    expect(order.currency).toBe('AUD')
    expect(order.creationDate).toBe('2025-01-01T00:00:00Z')
    expect(order.appCode).toBe('myapp')
  })

  it('maps line items', () => {
    const order = mapLocalOrderToSoldOrder(BASE_RAW, 'myapp', '')
    expect(order.lineItems).toHaveLength(1)
    expect(order.lineItems[0].legacyItemId).toBe('item-1')
    expect(order.lineItems[0].title).toBe('Lightning Bolt')
    expect(order.lineItems[0].quantity).toBe(2)
    expect(order.lineItems[0].lineItemId).toBeNull()
    expect(order.lineItems[0].lineItemFulfillmentStatus).toBeNull()
  })

  it('sets fee and payout fields to null', () => {
    const order = mapLocalOrderToSoldOrder(BASE_RAW, 'myapp', '')
    expect(order.ebayFee).toBeNull()
    expect(order.netPayout).toBeNull()
    expect(order.shippingCollected).toBeNull()
    expect(order.orderFulfillmentStatus).toBeNull()
    expect(order.legacyOrderId).toBeNull()
  })

  it('derives displayStatus from local_status only', () => {
    const inTransit = mapLocalOrderToSoldOrder({ ...BASE_RAW, local_status: 'in_transit' }, 'myapp', '')
    expect(inTransit.displayStatus).toBe('in_transit')
    const noStatus = mapLocalOrderToSoldOrder({ ...BASE_RAW, local_status: null }, 'myapp', '')
    expect(noStatus.displayStatus).toBe('sold')
    const sent = mapLocalOrderToSoldOrder({ ...BASE_RAW, local_status: 'sent' }, 'myapp', '')
    expect(sent.displayStatus).toBe('sent')
  })

  it('handles null price gracefully', () => {
    const order = mapLocalOrderToSoldOrder({ ...BASE_RAW, total_price_cents: null }, 'myapp', '')
    expect(order.totalAmount).toBeNull()
    expect(order.itemSubtotal).toBeNull()
  })

  it('handles missing line_items gracefully', () => {
    const order = mapLocalOrderToSoldOrder({ ...BASE_RAW, line_items: null }, 'myapp', '')
    expect(order.lineItems).toEqual([])
  })
})
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
cd src/frontend && node_modules/.bin/vitest run src/features/ebay/__tests__/soldOrders.test.ts
```

Expected: 6 new failures — `mapLocalOrderToSoldOrder is not a function`

- [ ] **Step 3: Add the mapper function**

Append to `src/frontend/src/features/ebay/soldOrders.ts`:

```typescript
export function mapLocalOrderToSoldOrder(
  raw: Record<string, unknown>,
  appCode: string,
  appName: string,
): SoldOrder {
  const priceCents = raw.total_price_cents as number | null
  const totalAmount = priceCents != null ? priceCents / 100 : null
  const localStatus = (raw.local_status as string | null) ?? null
  const lineItems = (raw.line_items as Record<string, unknown>[] | null) ?? []

  return {
    orderId: (raw.order_id as string) ?? '',
    legacyOrderId: null,
    creationDate: (raw.sold_at as string | null) ?? null,
    orderFulfillmentStatus: null,
    orderPaymentStatus: null,
    buyerUsername: (raw.buyer_username as string | null) ?? null,
    totalAmount,
    currency: (raw.currency as string | null) ?? null,
    lineItems: lineItems.map((li) => ({
      lineItemId: null,
      legacyItemId: (li.legacyItemId as string | null) ?? null,
      title: (li.title as string | null) ?? null,
      quantity: (li.quantity as number | null) ?? null,
      lineItemFulfillmentStatus: null,
    })),
    local_status: localStatus,
    displayStatus: deriveDisplayStatus(null, localStatus),
    appCode,
    appName,
    itemSubtotal: totalAmount,
    shippingCollected: null,
    ebayFee: null,
    netPayout: null,
  }
}
```

- [ ] **Step 4: Run tests to confirm all pass**

```bash
cd src/frontend && node_modules/.bin/vitest run src/features/ebay/__tests__/soldOrders.test.ts
```

Expected: 12 tests pass (6 original + 6 new).

- [ ] **Step 5: Commit**

```bash
git add \
  src/frontend/src/features/ebay/soldOrders.ts \
  src/frontend/src/features/ebay/__tests__/soldOrders.test.ts
git commit -m "feat(ebay): add mapLocalOrderToSoldOrder for local DB order shape"
```

---

## Task 5: Update fetchSoldOrders

**Files:**
- Modify: `src/frontend/src/features/ebay/api.ts`
- Modify: `src/frontend/src/features/ebay/__tests__/api.sold.test.ts`

- [ ] **Step 1: Update the test to expect local DB format**

In `src/frontend/src/features/ebay/__tests__/api.sold.test.ts`, replace the entire `describe('fetchSoldOrders', ...)` block with:

```typescript
describe('fetchSoldOrders', () => {
  it('calls local-history endpoint and maps local DB orders to SoldOrder array', async () => {
    mockApiClient.mockResolvedValue({
      data: [
        {
          order_id: 'ord-1',
          local_status: 'sold',
          buyer_username: 'buyer_xyz',
          sold_at: '2026-05-09T00:00:00Z',
          currency: 'AUD',
          total_price_cents: 4200,
          line_items: [{ legacyItemId: 'item-1', title: 'Bolt', quantity: 1 }],
        },
      ],
      pagination: { has_next: false },
    })

    const result = await fetchSoldOrders('myapp', 25, 0)
    expect(result.orders).toHaveLength(1)
    expect(result.orders[0].orderId).toBe('ord-1')
    expect(result.orders[0].displayStatus).toBe('sold')
    expect(result.orders[0].buyerUsername).toBe('buyer_xyz')
    expect(result.orders[0].totalAmount).toBe(42)
    expect(result.hasMore).toBe(false)
    expect(mockApiClient).toHaveBeenCalledWith(
      expect.stringContaining('/integrations/ebay/listing/local-history'),
    )
  })
})
```

- [ ] **Step 2: Run to confirm the test fails**

```bash
cd src/frontend && node_modules/.bin/vitest run src/features/ebay/__tests__/api.sold.test.ts
```

Expected: the `fetchSoldOrders` test fails — either wrong URL assertion or wrong field mapping.

- [ ] **Step 3: Update the import in api.ts**

Change line 4 of `src/frontend/src/features/ebay/api.ts` from:

```typescript
import { mapRawToSoldOrder, type SoldOrder } from './soldOrders'
```

to:

```typescript
import { mapRawToSoldOrder, mapLocalOrderToSoldOrder, type SoldOrder } from './soldOrders'
```

- [ ] **Step 4: Update fetchSoldOrders**

In `src/frontend/src/features/ebay/api.ts`, find the `fetchSoldOrders` function (starts at line 385) and make two edits:

**Edit 1** — change the URL (in the `apiClient` call):

```typescript
// Before
`/integrations/ebay/listing/history?app_code=${encodeURIComponent(appCode)}&limit=${limit}&offset=${offset}`

// After
`/integrations/ebay/listing/local-history?app_code=${encodeURIComponent(appCode)}&limit=${limit}&offset=${offset}`
```

**Edit 2** — change the mapper (in the return statement):

```typescript
// Before
orders: items.map((item) => mapRawToSoldOrder(item, appCode, '')),

// After
orders: items.map((item) => mapLocalOrderToSoldOrder(item, appCode, '')),
```

- [ ] **Step 5: Run tests to confirm all pass**

```bash
cd src/frontend && node_modules/.bin/vitest run src/features/ebay/__tests__/api.sold.test.ts
```

Expected: 4 tests pass.

- [ ] **Step 6: Run the full frontend test suite to check for regressions**

```bash
cd src/frontend && node_modules/.bin/vitest run
```

Expected: all tests pass with no regressions.

- [ ] **Step 7: Commit**

```bash
git add \
  src/frontend/src/features/ebay/api.ts \
  src/frontend/src/features/ebay/__tests__/api.sold.test.ts
git commit -m "feat(ebay): switch fetchSoldOrders to local-history endpoint"
```

---

## Task 6: Final Backend Test Pass

- [ ] **Step 1: Run all backend unit tests**

```bash
python3 -m pytest tests/unit/ -q --ignore=tests/unit/core/routers/ebay/test_build_and_create_tracking.py
```

The `test_build_and_create_tracking.py` tests are excluded — they have a pre-existing failure unrelated to this feature (see note below).

Expected: all other tests pass.

> **Note:** `tests/unit/core/routers/ebay/test_build_and_create_tracking.py` has 3 pre-existing failures caused by `ebay_auth.py` calling `get_settings()` at module import time (requires a DB password env var). This is not caused by this feature and should be fixed in a separate PR.

- [ ] **Step 2: Commit final state if needed**

If no additional uncommitted changes remain, the feature branch is ready for PR.

```bash
git log --oneline -6
```

Expected output (5 commits from this feature):
```
<hash> feat(ebay): switch fetchSoldOrders to local-history endpoint
<hash> feat(ebay): add mapLocalOrderToSoldOrder for local DB order shape
<hash> feat(ebay): add GET /listing/local-history endpoint and register service module
<hash> feat(ebay): add local_sales_service for DB-backed sold order reads
<hash> feat(ebay): add local sales paginated query and repository method
<hash> docs: add design spec for eBay local sales read path
```
