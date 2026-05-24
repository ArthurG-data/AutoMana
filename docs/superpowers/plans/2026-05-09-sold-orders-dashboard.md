# Sold Orders Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface sold eBay orders in the Listings page Sold tab with lifecycle badges (Sold → Sent → In Transit → Complete) and inline "Mark as sent" / "Add tracking" actions that call eBay's Fulfillment API.

**Architecture:** eBay's `orderFulfillmentStatus` drives Sold/Sent/Complete; a new local table `app_integration.ebay_order_status` stores the In Transit override and tracking metadata. Two new backend endpoints handle fulfillment writes; the existing history endpoint is augmented to merge local status. Three new frontend components (LifecycleBadge, SoldOrdersTable, SoldOrderDetailPanel) wire into the existing Sold tab stub.

**Tech Stack:** Python/FastAPI, asyncpg, Pydantic v2, pytest-asyncio; React 18, TypeScript, CSS Modules, Vitest, @testing-library/react.

---

## Task 1: DB Migration

**Files:**
- Create: `src/automana/database/SQL/migrations/migration_26_ebay_order_status.sql`

- [ ] **Step 1: Write the migration**

```sql
-- migration_26_ebay_order_status.sql
BEGIN;

CREATE TABLE IF NOT EXISTS app_integration.ebay_order_status (
    order_id        TEXT         NOT NULL,
    app_code        VARCHAR(50)  NOT NULL
        REFERENCES app_integration.app_info(app_code) ON DELETE CASCADE,
    local_status    TEXT         NOT NULL
        CHECK (local_status IN ('sold', 'sent', 'in_transit', 'complete')),
    tracking_number TEXT,
    carrier_code    TEXT,
    shipped_at      TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (order_id, app_code)
);

GRANT SELECT, INSERT, UPDATE ON app_integration.ebay_order_status TO app_backend;
GRANT SELECT, INSERT, UPDATE ON app_integration.ebay_order_status TO app_celery;

COMMIT;
```

- [ ] **Step 2: Apply the migration**

```bash
docker exec -i automana-postgres-dev psql -U automana_admin automana \
  < src/automana/database/SQL/migrations/migration_26_ebay_order_status.sql
```

Expected: `CREATE TABLE` then `GRANT`.

- [ ] **Step 3: Verify**

```bash
docker exec automana-postgres-dev psql -U automana_admin automana \
  -c "\d app_integration.ebay_order_status"
```

Expected: table with columns `order_id`, `app_code`, `local_status`, `tracking_number`, `carrier_code`, `shipped_at`, `updated_at`.

- [ ] **Step 4: Commit**

```bash
git add src/automana/database/SQL/migrations/migration_26_ebay_order_status.sql
git commit -m "feat(ebay): add ebay_order_status migration for sold orders lifecycle"
```

---

## Task 2: App Repository — Order Status CRUD

**Files:**
- Modify: `src/automana/core/repositories/app_integration/ebay/app_queries.py`
- Modify: `src/automana/core/repositories/app_integration/ebay/app_repository.py`
- Create: `src/automana/tests/unit/repositories/ebay/test_order_status_repository.py`

- [ ] **Step 1: Write failing tests**

```python
# src/automana/tests/unit/repositories/ebay/test_order_status_repository.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from automana.core.repositories.app_integration.ebay.app_repository import EbayAppRepository


def make_repo():
    conn = MagicMock()
    repo = EbayAppRepository.__new__(EbayAppRepository)
    repo.connection = conn
    repo.executor = None
    return repo


@pytest.mark.asyncio
async def test_get_order_statuses_returns_dict_keyed_by_order_id(monkeypatch):
    repo = make_repo()
    fake_rows = [
        {"order_id": "ord-1", "local_status": "sent", "tracking_number": None,
         "carrier_code": None, "shipped_at": None},
    ]
    repo.execute_query = AsyncMock(return_value=fake_rows)

    result = await repo.get_order_statuses(app_code="myapp", order_ids=["ord-1", "ord-2"])

    assert result == {
        "ord-1": {"order_id": "ord-1", "local_status": "sent", "tracking_number": None,
                  "carrier_code": None, "shipped_at": None}
    }
    repo.execute_query.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_order_statuses_empty_returns_empty_dict(monkeypatch):
    repo = make_repo()
    repo.execute_query = AsyncMock(return_value=[])
    result = await repo.get_order_statuses(app_code="myapp", order_ids=[])
    assert result == {}


@pytest.mark.asyncio
async def test_upsert_order_status_calls_execute_command():
    repo = make_repo()
    repo.execute_command = AsyncMock(return_value=None)

    await repo.upsert_order_status(
        order_id="ord-1",
        app_code="myapp",
        local_status="sent",
        tracking_number="TRK123",
        carrier_code="AusPost",
        shipped_at=None,
    )

    repo.execute_command.assert_awaited_once()
    args = repo.execute_command.call_args[0]
    assert args[1] == ("ord-1", "myapp", "sent", "TRK123", "AusPost", None)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd src && python -m pytest automana/tests/unit/repositories/ebay/test_order_status_repository.py -v
```

Expected: `ImportError` or `AttributeError` — methods don't exist yet.

- [ ] **Step 3: Add SQL queries to app_queries.py**

Append to `src/automana/core/repositories/app_integration/ebay/app_queries.py`:

```python
get_order_statuses_query = """
SELECT order_id, local_status, tracking_number, carrier_code, shipped_at
FROM app_integration.ebay_order_status
WHERE app_code = $1
  AND order_id = ANY($2::TEXT[])
"""

upsert_order_status_query = """
INSERT INTO app_integration.ebay_order_status
    (order_id, app_code, local_status, tracking_number, carrier_code, shipped_at, updated_at)
VALUES ($1, $2, $3, $4, $5, $6, now())
ON CONFLICT (order_id, app_code) DO UPDATE SET
    local_status    = EXCLUDED.local_status,
    tracking_number = COALESCE(EXCLUDED.tracking_number,
                               app_integration.ebay_order_status.tracking_number),
    carrier_code    = COALESCE(EXCLUDED.carrier_code,
                               app_integration.ebay_order_status.carrier_code),
    shipped_at      = COALESCE(EXCLUDED.shipped_at,
                               app_integration.ebay_order_status.shipped_at),
    updated_at      = now()
"""
```

- [ ] **Step 4: Add repository methods to app_repository.py**

Append inside the `EbayAppRepository` class in `src/automana/core/repositories/app_integration/ebay/app_repository.py`:

```python
    async def get_order_statuses(
        self, app_code: str, order_ids: list[str]
    ) -> dict[str, dict]:
        rows = await self.execute_query(
            app_queries.get_order_statuses_query, (app_code, order_ids)
        )
        return {row["order_id"]: dict(row) for row in (rows or [])}

    async def upsert_order_status(
        self,
        order_id: str,
        app_code: str,
        local_status: str,
        tracking_number: str | None = None,
        carrier_code: str | None = None,
        shipped_at=None,
    ) -> None:
        await self.execute_command(
            app_queries.upsert_order_status_query,
            (order_id, app_code, local_status, tracking_number, carrier_code, shipped_at),
        )
```

- [ ] **Step 5: Run tests — expect green**

```bash
cd src && python -m pytest automana/tests/unit/repositories/ebay/test_order_status_repository.py -v
```

Expected: 3 PASSED.

- [ ] **Step 6: Commit**

```bash
git add src/automana/core/repositories/app_integration/ebay/app_queries.py \
        src/automana/core/repositories/app_integration/ebay/app_repository.py \
        src/automana/tests/unit/repositories/ebay/test_order_status_repository.py
git commit -m "feat(ebay): add get_order_statuses and upsert_order_status to app repository"
```

---

## Task 3: ApiSelling Repository — create_shipping_fulfillment

**Files:**
- Modify: `src/automana/core/repositories/app_integration/ebay/ApiSelling_repository.py`
- Create: `src/automana/tests/unit/repositories/ebay/test_api_selling_fulfill.py`

- [ ] **Step 1: Write failing tests**

```python
# src/automana/tests/unit/repositories/ebay/test_api_selling_fulfill.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from automana.core.repositories.app_integration.ebay.ApiSelling_repository import EbaySellingRepository


def make_repo(environment="sandbox"):
    repo = EbaySellingRepository.__new__(EbaySellingRepository)
    repo.environment = environment
    repo.timeout = 30
    repo.http2 = True
    repo.base_url = "https://api.sandbox.ebay.com/ws/api.dll"
    repo._client = None
    return repo


@pytest.mark.asyncio
async def test_create_shipping_fulfillment_posts_correct_url():
    repo = make_repo()
    mock_response = MagicMock()
    mock_response.status_code = 201
    repo.send = AsyncMock(return_value=mock_response)

    result = await repo.create_shipping_fulfillment({
        "token": "tok123",
        "order_id": "12-34567-89012",
        "line_item_ids": ["9876543210"],
    })

    assert result == {"success": True, "order_id": "12-34567-89012"}
    call_args = repo.send.call_args
    assert call_args[0][0] == "POST"
    assert "12-34567-89012/shippingFulfillment" in call_args[0][1]
    body = call_args[1]["json"]
    assert body["lineItems"] == [{"lineItemId": "9876543210", "quantity": 1}]
    assert "shippedDate" in body


@pytest.mark.asyncio
async def test_create_shipping_fulfillment_includes_tracking_when_provided():
    repo = make_repo()
    mock_response = MagicMock()
    mock_response.status_code = 201
    repo.send = AsyncMock(return_value=mock_response)

    await repo.create_shipping_fulfillment({
        "token": "tok123",
        "order_id": "ord-1",
        "line_item_ids": ["111"],
        "tracking_number": "TRK999",
        "carrier_code": "AusPost",
    })

    body = repo.send.call_args[1]["json"]
    assert body["trackingNumber"] == "TRK999"
    assert body["shippingCarrierCode"] == "AusPost"


@pytest.mark.asyncio
async def test_create_shipping_fulfillment_raises_on_missing_token():
    repo = make_repo()
    with pytest.raises(ValueError, match="Token is required"):
        await repo.create_shipping_fulfillment({"order_id": "ord-1", "line_item_ids": []})


@pytest.mark.asyncio
async def test_create_shipping_fulfillment_raises_on_missing_order_id():
    repo = make_repo()
    with pytest.raises(ValueError, match="order_id is required"):
        await repo.create_shipping_fulfillment({"token": "tok", "line_item_ids": []})
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd src && python -m pytest automana/tests/unit/repositories/ebay/test_api_selling_fulfill.py -v
```

Expected: `AttributeError: 'EbaySellingRepository' object has no attribute 'create_shipping_fulfillment'`.

- [ ] **Step 3: Add the method to ApiSelling_repository.py**

Append inside the `EbaySellingRepository` class, after `upload_picture`:

```python
    async def create_shipping_fulfillment(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Mark an eBay order as shipped via the Fulfillment REST API.

        POST /sell/fulfillment/v1/order/{orderId}/shippingFulfillment
        Returns {"success": True, "order_id": ...} on 200/201/204.
        """
        token = payload.get("token")
        order_id = payload.get("order_id")
        if not token:
            raise ValueError("Token is required")
        if not order_id:
            raise ValueError("order_id is required")

        base = (
            "https://api.sandbox.ebay.com"
            if self.environment == "sandbox"
            else "https://api.ebay.com"
        )
        url = f"{base}/sell/fulfillment/v1/order/{order_id}/shippingFulfillment"

        from datetime import datetime, timezone
        body: Dict[str, Any] = {
            "lineItems": [
                {"lineItemId": lid, "quantity": 1}
                for lid in payload.get("line_item_ids", [])
            ],
            "shippedDate": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        }
        if payload.get("tracking_number"):
            body["trackingNumber"] = payload["tracking_number"]
        if payload.get("carrier_code"):
            body["shippingCarrierCode"] = payload["carrier_code"]

        headers = {**self.auth_header(token), "Content-Type": "application/json"}
        logger.info(
            "ebay_create_shipping_fulfillment",
            extra={"order_id": order_id},
        )
        response = await self.send("POST", url, json=body, headers=headers)
        if response.status_code in (200, 201, 204):
            return {"success": True, "order_id": order_id}
        return self._parse_response(response)
```

- [ ] **Step 4: Run tests — expect green**

```bash
cd src && python -m pytest automana/tests/unit/repositories/ebay/test_api_selling_fulfill.py -v
```

Expected: 4 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/repositories/app_integration/ebay/ApiSelling_repository.py \
        src/automana/tests/unit/repositories/ebay/test_api_selling_fulfill.py
git commit -m "feat(ebay): add create_shipping_fulfillment to ApiSelling repository"
```

---

## Task 4: FulfillmentResponse Model — local_status field

**Files:**
- Modify: `src/automana/core/models/ebay/listings.py`

- [ ] **Step 1: Add `local_status` to `FulfillmentResponse`**

In `src/automana/core/models/ebay/listings.py`, add `local_status` to the `FulfillmentResponse` class:

```python
class FulfillmentResponse(BaseModel):
    orderId: Optional[str]
    legacyOrderId: Optional[str]
    creationDate: Optional[str]
    lastModifiedDate: Optional[str]
    orderFulfillmentStatus: Optional[str]
    orderPaymentStatus: Optional[str]
    sellerId: Optional[str]
    buyer: Optional[BuyerType]
    pricingSummary: Optional[PricingSummaryType]
    cancelStatus: Optional[CancelStatusType]
    paymentSummary: Optional[PaymentSummaryType]
    fulfillmentStartInstructions: Optional[List[FulfillmentStartInstructionsType]]
    fulfillmentHrefs: Optional[List[str]]
    lineItems: Optional[List[LineItemType]]
    salesRecordReference: Optional[str]
    totalFeeBasisAmount: Optional[BaseCostType]
    totalMarketplaceFee: Optional[BaseCostType]
    local_status: Optional[str] = None   # AutoMana override — not from eBay
```

- [ ] **Step 2: Verify existing tests still pass**

```bash
cd src && python -m pytest automana/tests/ -q --tb=short 2>&1 | tail -10
```

Expected: same pass count as before (adding an optional field with a default cannot break existing behaviour).

- [ ] **Step 3: Commit**

```bash
git add src/automana/core/models/ebay/listings.py
git commit -m "feat(ebay): add local_status field to FulfillmentResponse model"
```

---

## Task 5: fulfillment_write_service — Mark Order Shipped

**Files:**
- Create: `src/automana/core/services/app_integration/ebay/fulfillment_write_service.py`
- Create: `src/automana/tests/unit/services/ebay/test_fulfillment_write_service.py`

- [ ] **Step 1: Write failing tests**

```python
# src/automana/tests/unit/services/ebay/test_fulfillment_write_service.py
import pytest
from unittest.mock import AsyncMock, patch
from uuid import UUID
from automana.core.services.app_integration.ebay.fulfillment_write_service import mark_order_shipped

USER_ID = UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
def auth_repo():
    return AsyncMock()


@pytest.fixture
def app_repo():
    repo = AsyncMock()
    repo.upsert_order_status = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def selling_repo():
    repo = AsyncMock()
    repo.create_shipping_fulfillment = AsyncMock(
        return_value={"success": True, "order_id": "ord-1"}
    )
    return repo


@pytest.mark.asyncio
async def test_mark_order_shipped_calls_ebay_and_upserts_local(auth_repo, app_repo, selling_repo):
    with patch(
        "automana.core.services.app_integration.ebay.fulfillment_write_service.resolve_token",
        new=AsyncMock(return_value="tok123"),
    ):
        result = await mark_order_shipped(
            auth_repository=auth_repo,
            app_repository=app_repo,
            selling_repository=selling_repo,
            user_id=USER_ID,
            app_code="myapp",
            order_id="ord-1",
            line_item_ids=["line-111"],
        )

    assert result == {"success": True, "order_id": "ord-1"}
    selling_repo.create_shipping_fulfillment.assert_awaited_once()
    payload = selling_repo.create_shipping_fulfillment.call_args[0][0]
    assert payload["token"] == "tok123"
    assert payload["order_id"] == "ord-1"
    assert payload["line_item_ids"] == ["line-111"]
    assert payload.get("tracking_number") is None

    app_repo.upsert_order_status.assert_awaited_once()
    upsert_kwargs = app_repo.upsert_order_status.call_args[1]
    assert upsert_kwargs["order_id"] == "ord-1"
    assert upsert_kwargs["local_status"] == "sent"


@pytest.mark.asyncio
async def test_mark_order_shipped_passes_tracking_when_provided(auth_repo, app_repo, selling_repo):
    with patch(
        "automana.core.services.app_integration.ebay.fulfillment_write_service.resolve_token",
        new=AsyncMock(return_value="tok"),
    ):
        await mark_order_shipped(
            auth_repository=auth_repo,
            app_repository=app_repo,
            selling_repository=selling_repo,
            user_id=USER_ID,
            app_code="myapp",
            order_id="ord-2",
            line_item_ids=["l2"],
            tracking_number="TRK999",
            carrier_code="AusPost",
        )

    payload = selling_repo.create_shipping_fulfillment.call_args[0][0]
    assert payload["tracking_number"] == "TRK999"
    assert payload["carrier_code"] == "AusPost"
    upsert_kwargs = app_repo.upsert_order_status.call_args[1]
    assert upsert_kwargs["tracking_number"] == "TRK999"
    assert upsert_kwargs["carrier_code"] == "AusPost"
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd src && python -m pytest automana/tests/unit/services/ebay/test_fulfillment_write_service.py -v
```

Expected: `ImportError` — module doesn't exist yet.

- [ ] **Step 3: Create fulfillment_write_service.py**

```python
# src/automana/core/services/app_integration/ebay/fulfillment_write_service.py
"""eBay fulfillment writes — marking orders as shipped.

Design patterns
───────────────
- CQS: this module owns fulfillment writes. Reads live in ``fulfillment_service``.
- Guard clause via ``_auth_context.resolve_token``.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from automana.core.repositories.app_integration.ebay.auth_repository import EbayAuthRepository
from automana.core.repositories.app_integration.ebay.app_repository import EbayAppRepository
from automana.core.repositories.app_integration.ebay.ApiSelling_repository import EbaySellingRepository
from automana.core.framework.registry import ServiceRegistry
from automana.core.services.app_integration.ebay._auth_context import resolve_token

logger = logging.getLogger(__name__)


@ServiceRegistry.register(
    path="integrations.ebay.selling.fulfillment.ship",
    db_repositories=["auth", "app"],
    api_repositories=["selling"],
)
async def mark_order_shipped(
    auth_repository: EbayAuthRepository,
    app_repository: EbayAppRepository,
    selling_repository: EbaySellingRepository,
    user_id: UUID,
    app_code: str,
    order_id: str,
    line_item_ids: List[str],
    tracking_number: Optional[str] = None,
    carrier_code: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Call eBay's Fulfillment API to mark an order shipped, then persist locally."""
    logger.info(
        "ebay_mark_order_shipped_requested",
        extra={
            "action": "mark_order_shipped",
            "user_id": str(user_id),
            "app_code": app_code,
            "order_id": order_id,
        },
    )

    token = await resolve_token(auth_repository, user_id=user_id, app_code=app_code)

    result = await selling_repository.create_shipping_fulfillment({
        "token": token,
        "order_id": order_id,
        "line_item_ids": line_item_ids,
        "tracking_number": tracking_number,
        "carrier_code": carrier_code,
    })

    await app_repository.upsert_order_status(
        order_id=order_id,
        app_code=app_code,
        local_status="sent",
        tracking_number=tracking_number,
        carrier_code=carrier_code,
        shipped_at=datetime.now(timezone.utc),
    )

    logger.info(
        "ebay_mark_order_shipped_success",
        extra={"action": "mark_order_shipped", "order_id": order_id},
    )
    return result
```

- [ ] **Step 4: Run tests — expect green**

```bash
cd src && python -m pytest automana/tests/unit/services/ebay/test_fulfillment_write_service.py -v
```

Expected: 2 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/services/app_integration/ebay/fulfillment_write_service.py \
        src/automana/tests/unit/services/ebay/test_fulfillment_write_service.py
git commit -m "feat(ebay): add fulfillment_write_service for marking orders shipped"
```

---

## Task 6: Augment get_order_history + local PATCH status

**Files:**
- Modify: `src/automana/core/services/app_integration/ebay/fulfillment_service.py`
- Create: `src/automana/tests/unit/services/ebay/test_fulfillment_service_augmented.py`

- [ ] **Step 1: Write failing tests**

```python
# src/automana/tests/unit/services/ebay/test_fulfillment_service_augmented.py
import pytest
from unittest.mock import AsyncMock, patch
from uuid import UUID
from automana.core.services.app_integration.ebay.fulfillment_service import (
    get_order_history,
    update_order_local_status,
)

USER_ID = UUID("00000000-0000-0000-0000-000000000002")

RAW_ORDERS = {
    "orders": [
        {
            "orderId": "ord-1",
            "orderFulfillmentStatus": "NOT_STARTED",
            "orderPaymentStatus": "FULLY_PAID",
            "buyer": None,
            "pricingSummary": None,
            "cancelStatus": None,
            "paymentSummary": None,
            "fulfillmentStartInstructions": None,
            "fulfillmentHrefs": None,
            "lineItems": [{"lineItemId": "line-1", "legacyItemId": None, "title": "Ragavan",
                           "lineItemCost": None, "quantity": 1, "soldFormat": None,
                           "listingMarketplaceId": None, "purchaseMarketplaceId": None,
                           "lineItemFulfillmentStatus": None, "total": None,
                           "deliveryCost": None, "appliedPromotions": None,
                           "taxes": None, "properties": None,
                           "lineItemFulfillmentInstructions": None, "itemLocation": None}],
        }
    ],
    "total": 1,
}


@pytest.fixture
def auth_repo():
    return AsyncMock()


@pytest.fixture
def app_repo():
    repo = AsyncMock()
    repo.get_order_statuses = AsyncMock(return_value={})
    repo.upsert_order_status = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def selling_repo():
    repo = AsyncMock()
    repo.get_history = AsyncMock(return_value=RAW_ORDERS)
    return repo


@pytest.mark.asyncio
async def test_get_order_history_merges_local_status(auth_repo, app_repo, selling_repo):
    app_repo.get_order_statuses = AsyncMock(
        return_value={"ord-1": {"local_status": "in_transit"}}
    )
    with patch(
        "automana.core.services.app_integration.ebay.fulfillment_service.resolve_token",
        new=AsyncMock(return_value="tok"),
    ):
        result = await get_order_history(
            auth_repository=auth_repo,
            app_repository=app_repo,
            selling_repository=selling_repo,
            user_id=USER_ID,
            app_code="myapp",
        )

    assert result.items[0].local_status == "in_transit"


@pytest.mark.asyncio
async def test_get_order_history_local_status_none_when_no_row(auth_repo, app_repo, selling_repo):
    with patch(
        "automana.core.services.app_integration.ebay.fulfillment_service.resolve_token",
        new=AsyncMock(return_value="tok"),
    ):
        result = await get_order_history(
            auth_repository=auth_repo,
            app_repository=app_repo,
            selling_repository=selling_repo,
            user_id=USER_ID,
            app_code="myapp",
        )

    assert result.items[0].local_status is None


@pytest.mark.asyncio
async def test_update_order_local_status_upserts(auth_repo, app_repo):
    await update_order_local_status(
        app_repository=app_repo,
        order_id="ord-1",
        app_code="myapp",
        local_status="in_transit",
    )
    app_repo.upsert_order_status.assert_awaited_once_with(
        order_id="ord-1",
        app_code="myapp",
        local_status="in_transit",
    )
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd src && python -m pytest automana/tests/unit/services/ebay/test_fulfillment_service_augmented.py -v
```

Expected: `ImportError` for `update_order_local_status`, and attribute errors for the `app_repository` parameter.

- [ ] **Step 3: Rewrite fulfillment_service.py**

Replace the entire content of `src/automana/core/services/app_integration/ebay/fulfillment_service.py`:

```python
"""eBay fulfillment — order history query and local status transitions.

Design patterns
───────────────
- CQS: reads and simple local writes share this module; heavyweight writes
  (eBay API calls) live in ``fulfillment_write_service``.
- Guard Clause via ``_auth_context.resolve_token``.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from automana.core.models.ebay import listings as listings_model
from automana.core.repositories.app_integration.ebay.auth_repository import EbayAuthRepository
from automana.core.repositories.app_integration.ebay.app_repository import EbayAppRepository
from automana.core.repositories.app_integration.ebay.ApiSelling_repository import EbaySellingRepository
from automana.core.framework.registry import ServiceRegistry
from automana.core.services.app_integration.ebay._auth_context import resolve_token

logger = logging.getLogger(__name__)


@ServiceRegistry.register(
    path="integrations.ebay.selling.fulfillment.history",
    db_repositories=["auth", "app"],
    api_repositories=["selling"],
)
async def get_order_history(
    auth_repository: EbayAuthRepository,
    app_repository: EbayAppRepository,
    selling_repository: EbaySellingRepository,
    user_id: UUID,
    app_code: str,
    limit: int = 10,
    offset: int = 0,
    **kwargs: Any,
) -> listings_model.PaginatedOrders:
    """Fetch order history from the eBay Fulfillment API, merged with local status."""
    logger.info(
        "ebay_get_order_history_requested",
        extra={
            "action": "get_order_history",
            "user_id": str(user_id),
            "app_code": app_code,
            "limit": limit,
            "offset": offset,
        },
    )

    token = await resolve_token(auth_repository, user_id=user_id, app_code=app_code)
    payload: Dict[str, Any] = {"token": token, "limit": limit, "offset": offset}
    raw = await selling_repository.get_history(payload)

    raw_orders = raw.get("orders") or []
    items: List[listings_model.FulfillmentResponse] = []
    for order in raw_orders:
        if isinstance(order, dict):
            items.append(listings_model.FulfillmentResponse.model_validate(order))

    # Merge local status overrides.
    if items:
        order_ids = [o.orderId for o in items if o.orderId]
        local_map = await app_repository.get_order_statuses(
            app_code=app_code, order_ids=order_ids
        )
        for item in items:
            if item.orderId and item.orderId in local_map:
                item.local_status = local_map[item.orderId].get("local_status")

    raw_total: Optional[Any] = raw.get("total")
    total: Optional[int] = None
    if raw_total is not None:
        try:
            total = int(raw_total)
        except (ValueError, TypeError):
            logger.warning(
                "ebay_order_history_total_parse_failed",
                extra={"action": "get_order_history", "raw_total": str(raw_total)},
            )

    return listings_model.PaginatedOrders.from_parts(
        items=items, total=total, offset=offset, limit=limit,
    )


@ServiceRegistry.register(
    path="integrations.ebay.selling.fulfillment.local_status",
    db_repositories=["app"],
    api_repositories=[],
)
async def update_order_local_status(
    app_repository: EbayAppRepository,
    order_id: str,
    app_code: str,
    local_status: str,
    **kwargs: Any,
) -> Dict[str, str]:
    """Update the AutoMana-local lifecycle status for an order (no eBay call)."""
    logger.info(
        "ebay_update_order_local_status",
        extra={"action": "update_order_local_status", "order_id": order_id, "local_status": local_status},
    )
    await app_repository.upsert_order_status(
        order_id=order_id,
        app_code=app_code,
        local_status=local_status,
    )
    return {"order_id": order_id, "local_status": local_status}
```

- [ ] **Step 4: Run tests — expect green**

```bash
cd src && python -m pytest automana/tests/unit/services/ebay/test_fulfillment_service_augmented.py -v
```

Expected: 3 PASSED.

- [ ] **Step 5: Run full suite to check nothing regressed**

```bash
cd src && python -m pytest automana/tests/ -q --tb=short 2>&1 | tail -15
```

Expected: all previously passing tests still green.

- [ ] **Step 6: Commit**

```bash
git add src/automana/core/services/app_integration/ebay/fulfillment_service.py \
        src/automana/tests/unit/services/ebay/test_fulfillment_service_augmented.py
git commit -m "feat(ebay): augment get_order_history with local status merge; add update_order_local_status"
```

---

## Task 7: Router — POST /orders/{order_id}/fulfill and PATCH /orders/{order_id}/status

**Files:**
- Modify: `src/automana/api/routers/integrations/ebay/ebay_selling.py`

- [ ] **Step 1: Add request models and endpoints**

Append to `src/automana/api/routers/integrations/ebay/ebay_selling.py`, after the existing imports and before the final upload endpoint. First add two new request body models at the top of the file alongside `BuildListingRequest`:

```python
class FulfillOrderRequest(BaseModel):
    app_code: str
    line_item_ids: List[str]
    tracking_number: Optional[str] = None
    carrier_code: Optional[str] = None

class UpdateOrderStatusRequest(BaseModel):
    app_code: str
    local_status: str
```

Then add `List` to the existing `from typing import` line — it already has `Optional`, add `List`:

```python
from typing import Annotated, Any, Dict, List, Optional
```

Then append the two new endpoints at the end of the file:

```python
@ebay_listing_router.post("/orders/{order_id}/fulfill", description="Mark an order as shipped on eBay")
async def fulfill_order(
    order_id: str,
    body: FulfillOrderRequest,
    user: CurrentUserDep,
    service_manager: ServiceManagerDep,
):
    if body.local_status_validate := body.local_status if hasattr(body, "local_status") else None:
        pass  # unused branch — kept for symmetry
    try:
        result = await service_manager.execute_service(
            "integrations.ebay.selling.fulfillment.ship",
            user_id=user.unique_id,
            app_code=body.app_code,
            order_id=order_id,
            line_item_ids=body.line_item_ids,
            tracking_number=body.tracking_number,
            carrier_code=body.carrier_code,
        )
        return ApiResponse(data=result, message="Order marked as shipped")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@ebay_listing_router.patch("/orders/{order_id}/status", description="Update local order lifecycle status")
async def patch_order_status(
    order_id: str,
    body: UpdateOrderStatusRequest,
    user: CurrentUserDep,
    service_manager: ServiceManagerDep,
):
    allowed = {"in_transit", "complete"}
    if body.local_status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"local_status must be one of {sorted(allowed)}",
        )
    try:
        result = await service_manager.execute_service(
            "integrations.ebay.selling.fulfillment.local_status",
            order_id=order_id,
            app_code=body.app_code,
            local_status=body.local_status,
        )
        return ApiResponse(data=result, message="Order status updated")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
```

Note: remove the dead walrus-operator line above — it was a placeholder. The clean version:

```python
@ebay_listing_router.post("/orders/{order_id}/fulfill", description="Mark an order as shipped on eBay")
async def fulfill_order(
    order_id: str,
    body: FulfillOrderRequest,
    user: CurrentUserDep,
    service_manager: ServiceManagerDep,
):
    try:
        result = await service_manager.execute_service(
            "integrations.ebay.selling.fulfillment.ship",
            user_id=user.unique_id,
            app_code=body.app_code,
            order_id=order_id,
            line_item_ids=body.line_item_ids,
            tracking_number=body.tracking_number,
            carrier_code=body.carrier_code,
        )
        return ApiResponse(data=result, message="Order marked as shipped")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@ebay_listing_router.patch("/orders/{order_id}/status", description="Update local order lifecycle status")
async def patch_order_status(
    order_id: str,
    body: UpdateOrderStatusRequest,
    user: CurrentUserDep,
    service_manager: ServiceManagerDep,
):
    if body.local_status not in {"in_transit", "complete"}:
        raise HTTPException(
            status_code=400,
            detail="local_status must be one of ['complete', 'in_transit']",
        )
    try:
        result = await service_manager.execute_service(
            "integrations.ebay.selling.fulfillment.local_status",
            order_id=order_id,
            app_code=body.app_code,
            local_status=body.local_status,
        )
        return ApiResponse(data=result, message="Order status updated")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
```

- [ ] **Step 2: Verify the app starts**

```bash
cd src && python -c "from automana.api.routers.integrations.ebay.ebay_selling import ebay_listing_router; print('OK')"
```

Expected: `OK`.

- [ ] **Step 3: Run the full test suite**

```bash
cd src && python -m pytest automana/tests/ -q --tb=short 2>&1 | tail -10
```

Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add src/automana/api/routers/integrations/ebay/ebay_selling.py
git commit -m "feat(ebay): add POST fulfill and PATCH status endpoints for sold orders"
```

---

## Task 8: Frontend — soldOrders.ts types and helpers

**Files:**
- Create: `src/frontend/src/features/ebay/soldOrders.ts`
- Create: `src/frontend/src/features/ebay/__tests__/soldOrders.test.ts`

- [ ] **Step 1: Write failing tests**

```typescript
// src/frontend/src/features/ebay/__tests__/soldOrders.test.ts
import { describe, it, expect } from 'vitest'
import { deriveDisplayStatus } from '../soldOrders'

describe('deriveDisplayStatus', () => {
  it('returns complete when eBay status is FULFILLED regardless of local', () => {
    expect(deriveDisplayStatus('FULFILLED', 'in_transit')).toBe('complete')
    expect(deriveDisplayStatus('FULFILLED', null)).toBe('complete')
  })

  it('returns in_transit when local_status is in_transit and eBay is not FULFILLED', () => {
    expect(deriveDisplayStatus('NOT_STARTED', 'in_transit')).toBe('in_transit')
    expect(deriveDisplayStatus('IN_PROGRESS', 'in_transit')).toBe('in_transit')
  })

  it('returns sold when eBay status is NOT_STARTED and no in_transit override', () => {
    expect(deriveDisplayStatus('NOT_STARTED', null)).toBe('sold')
    expect(deriveDisplayStatus('NOT_STARTED', 'sent')).toBe('sold')
  })

  it('returns sent when eBay status is IN_PROGRESS and not in_transit', () => {
    expect(deriveDisplayStatus('IN_PROGRESS', null)).toBe('sent')
    expect(deriveDisplayStatus('IN_PROGRESS', 'sent')).toBe('sent')
  })

  it('returns sold for unknown eBay status', () => {
    expect(deriveDisplayStatus(null, null)).toBe('sold')
    expect(deriveDisplayStatus(undefined, null)).toBe('sold')
  })
})
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd src/frontend && npx vitest run src/features/ebay/__tests__/soldOrders.test.ts 2>&1 | tail -10
```

Expected: `Error: Cannot find module '../soldOrders'`.

- [ ] **Step 3: Create soldOrders.ts**

```typescript
// src/frontend/src/features/ebay/soldOrders.ts

export type DisplayStatus = 'sold' | 'sent' | 'in_transit' | 'complete'

export interface SoldOrderLineItem {
  lineItemId: string | null
  legacyItemId: string | null
  title: string | null
  quantity: number | null
  lineItemFulfillmentStatus: string | null
}

export interface SoldOrder {
  orderId: string
  legacyOrderId: string | null
  creationDate: string | null
  orderFulfillmentStatus: string | null
  orderPaymentStatus: string | null
  buyerUsername: string | null
  totalAmount: number | null
  currency: string | null
  lineItems: SoldOrderLineItem[]
  local_status: string | null
  displayStatus: DisplayStatus
  appCode: string
  appName: string
}

/**
 * Derives the display lifecycle stage from eBay's fulfillment status and the
 * AutoMana-local override. Priority:
 * 1. eBay FULFILLED → complete (terminal, eBay always wins)
 * 2. local_status = in_transit → in_transit
 * 3. eBay IN_PROGRESS → sent
 * 4. Everything else → sold
 */
export function deriveDisplayStatus(
  ebayStatus: string | null | undefined,
  localStatus: string | null | undefined,
): DisplayStatus {
  if (ebayStatus === 'FULFILLED') return 'complete'
  if (localStatus === 'in_transit') return 'in_transit'
  if (ebayStatus === 'IN_PROGRESS') return 'sent'
  return 'sold'
}

export function mapRawToSoldOrder(
  raw: Record<string, unknown>,
  appCode: string,
  appName: string,
): SoldOrder {
  const buyer = raw.buyer as Record<string, unknown> | null
  const pricing = raw.pricingSummary as Record<string, unknown> | null
  const total = pricing?.total as Record<string, unknown> | null
  const lineItems = (raw.lineItems as Record<string, unknown>[] | null) ?? []
  const ebayStatus = (raw.orderFulfillmentStatus as string | null) ?? null
  const localStatus = (raw.local_status as string | null) ?? null

  return {
    orderId: (raw.orderId as string) ?? '',
    legacyOrderId: (raw.legacyOrderId as string | null) ?? null,
    creationDate: (raw.creationDate as string | null) ?? null,
    orderFulfillmentStatus: ebayStatus,
    orderPaymentStatus: (raw.orderPaymentStatus as string | null) ?? null,
    buyerUsername: (buyer?.username as string | null) ?? null,
    totalAmount: total?.value != null ? Number(total.value) : null,
    currency: (total?.currency as string | null) ?? null,
    lineItems: lineItems.map((li) => ({
      lineItemId: (li.lineItemId as string | null) ?? null,
      legacyItemId: (li.legacyItemId as string | null) ?? null,
      title: (li.title as string | null) ?? null,
      quantity: (li.quantity as number | null) ?? null,
      lineItemFulfillmentStatus: (li.lineItemFulfillmentStatus as string | null) ?? null,
    })),
    local_status: localStatus,
    displayStatus: deriveDisplayStatus(ebayStatus, localStatus),
    appCode,
    appName,
  }
}
```

- [ ] **Step 4: Run tests — expect green**

```bash
cd src/frontend && npx vitest run src/features/ebay/__tests__/soldOrders.test.ts
```

Expected: 5 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/frontend/src/features/ebay/soldOrders.ts \
        src/frontend/src/features/ebay/__tests__/soldOrders.test.ts
git commit -m "feat(ebay): add SoldOrder types, deriveDisplayStatus, and mapRawToSoldOrder"
```

---

## Task 9: Frontend API — fetchSoldOrders and order action functions

**Files:**
- Modify: `src/frontend/src/features/ebay/api.ts`
- Create: `src/frontend/src/features/ebay/__tests__/api.sold.test.ts`

- [ ] **Step 1: Write failing tests**

```typescript
// src/frontend/src/features/ebay/__tests__/api.sold.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fetchSoldOrders, markOrderSent, markOrderSentWithTracking, updateOrderLocalStatus } from '../api'

vi.mock('../../../lib/apiClient', () => ({
  apiClient: vi.fn(),
  ApiError: class ApiError extends Error {
    constructor(msg: string, public status: number) { super(msg) }
  },
}))

import { apiClient } from '../../../lib/apiClient'
const mockApiClient = vi.mocked(apiClient)

beforeEach(() => { mockApiClient.mockReset() })

describe('fetchSoldOrders', () => {
  it('maps raw orders to SoldOrder array', async () => {
    mockApiClient.mockResolvedValue({
      data: [
        {
          orderId: 'ord-1',
          orderFulfillmentStatus: 'NOT_STARTED',
          orderPaymentStatus: 'FULLY_PAID',
          creationDate: '2026-05-09T00:00:00Z',
          buyer: { username: 'buyer_xyz', taxAddress: null, buyerRegistrationAddress: null },
          pricingSummary: { total: { value: '42.00', currency: 'AUD' } },
          lineItems: [],
          local_status: null,
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
  })
})

describe('markOrderSent', () => {
  it('posts to the fulfill endpoint without tracking', async () => {
    mockApiClient.mockResolvedValue({ data: { success: true } })
    await markOrderSent('myapp', 'ord-1', ['line-1'])
    expect(mockApiClient).toHaveBeenCalledWith(
      '/integrations/ebay/listing/orders/ord-1/fulfill',
      expect.objectContaining({ method: 'POST' }),
    )
    const body = JSON.parse(mockApiClient.mock.calls[0][1].body)
    expect(body.app_code).toBe('myapp')
    expect(body.line_item_ids).toEqual(['line-1'])
    expect(body.tracking_number).toBeUndefined()
  })
})

describe('markOrderSentWithTracking', () => {
  it('posts with tracking fields', async () => {
    mockApiClient.mockResolvedValue({ data: { success: true } })
    await markOrderSentWithTracking('myapp', 'ord-1', ['line-1'], 'AusPost', 'TRK999')
    const body = JSON.parse(mockApiClient.mock.calls[0][1].body)
    expect(body.tracking_number).toBe('TRK999')
    expect(body.carrier_code).toBe('AusPost')
  })
})

describe('updateOrderLocalStatus', () => {
  it('patches the status endpoint', async () => {
    mockApiClient.mockResolvedValue({ data: { local_status: 'in_transit' } })
    await updateOrderLocalStatus('myapp', 'ord-1', 'in_transit')
    expect(mockApiClient).toHaveBeenCalledWith(
      '/integrations/ebay/listing/orders/ord-1/status',
      expect.objectContaining({ method: 'PATCH' }),
    )
    const body = JSON.parse(mockApiClient.mock.calls[0][1].body)
    expect(body.local_status).toBe('in_transit')
  })
})
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd src/frontend && npx vitest run src/features/ebay/__tests__/api.sold.test.ts 2>&1 | tail -10
```

Expected: import errors for the new functions.

- [ ] **Step 3: Add the four new functions to api.ts**

Append to the bottom of `src/frontend/src/features/ebay/api.ts`:

```typescript
// ── Sold orders ────────────────────────────────────────────────────────────

import { mapRawToSoldOrder, type SoldOrder } from './soldOrders'

export async function fetchSoldOrders(
  appCode: string,
  limit = 25,
  offset = 0,
): Promise<{ orders: SoldOrder[]; hasMore: boolean }> {
  const raw = await apiClient<unknown>(
    `/integrations/ebay/listing/history?app_code=${encodeURIComponent(appCode)}&limit=${limit}&offset=${offset}`
  )
  const paged = raw as { data?: unknown; pagination?: { has_next?: boolean } }
  const items = Array.isArray(paged.data) ? (paged.data as Record<string, unknown>[]) : []
  const hasMore = paged.pagination?.has_next ?? false
  return {
    orders: items.map((item) => mapRawToSoldOrder(item, appCode, '')),
    hasMore,
  }
}

export async function markOrderSent(
  appCode: string,
  orderId: string,
  lineItemIds: string[],
): Promise<void> {
  await apiClient<unknown>(
    `/integrations/ebay/listing/orders/${encodeURIComponent(orderId)}/fulfill`,
    {
      method: 'POST',
      body: JSON.stringify({ app_code: appCode, line_item_ids: lineItemIds }),
    },
  )
}

export async function markOrderSentWithTracking(
  appCode: string,
  orderId: string,
  lineItemIds: string[],
  carrierCode: string,
  trackingNumber: string,
): Promise<void> {
  await apiClient<unknown>(
    `/integrations/ebay/listing/orders/${encodeURIComponent(orderId)}/fulfill`,
    {
      method: 'POST',
      body: JSON.stringify({
        app_code: appCode,
        line_item_ids: lineItemIds,
        carrier_code: carrierCode,
        tracking_number: trackingNumber,
      }),
    },
  )
}

export async function updateOrderLocalStatus(
  appCode: string,
  orderId: string,
  localStatus: 'in_transit' | 'complete',
): Promise<void> {
  await apiClient<unknown>(
    `/integrations/ebay/listing/orders/${encodeURIComponent(orderId)}/status`,
    {
      method: 'PATCH',
      body: JSON.stringify({ app_code: appCode, local_status: localStatus }),
    },
  )
}
```

- [ ] **Step 4: Run tests — expect green**

```bash
cd src/frontend && npx vitest run src/features/ebay/__tests__/api.sold.test.ts
```

Expected: 4 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/frontend/src/features/ebay/api.ts \
        src/frontend/src/features/ebay/__tests__/api.sold.test.ts
git commit -m "feat(ebay): add fetchSoldOrders, markOrderSent, markOrderSentWithTracking, updateOrderLocalStatus to api.ts"
```

---

## Task 10: LifecycleBadge component

**Files:**
- Create: `src/frontend/src/features/ebay/components/LifecycleBadge.tsx`
- Create: `src/frontend/src/features/ebay/components/LifecycleBadge.module.css`
- Create: `src/frontend/src/features/ebay/components/__tests__/LifecycleBadge.test.tsx`

- [ ] **Step 1: Write failing tests**

```typescript
// src/frontend/src/features/ebay/components/__tests__/LifecycleBadge.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { LifecycleBadge } from '../LifecycleBadge'

describe('LifecycleBadge', () => {
  it('renders Sold for sold status', () => {
    render(<LifecycleBadge status="sold" />)
    expect(screen.getByText(/Sold/i)).toBeTruthy()
  })

  it('renders Sent for sent status', () => {
    render(<LifecycleBadge status="sent" />)
    expect(screen.getByText(/Sent/i)).toBeTruthy()
  })

  it('renders Transit for in_transit status', () => {
    render(<LifecycleBadge status="in_transit" />)
    expect(screen.getByText(/Transit/i)).toBeTruthy()
  })

  it('renders Done for complete status', () => {
    render(<LifecycleBadge status="complete" />)
    expect(screen.getByText(/Done/i)).toBeTruthy()
  })
})
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd src/frontend && npx vitest run src/features/ebay/components/__tests__/LifecycleBadge.test.tsx 2>&1 | tail -5
```

Expected: `Cannot find module '../LifecycleBadge'`.

- [ ] **Step 3: Create LifecycleBadge.tsx**

```tsx
// src/frontend/src/features/ebay/components/LifecycleBadge.tsx
import type { DisplayStatus } from '../soldOrders'
import styles from './LifecycleBadge.module.css'

interface LifecycleBadgeProps {
  status: DisplayStatus
}

const CONFIG: Record<DisplayStatus, { icon: string; label: string; mod: string }> = {
  sold:       { icon: '💰', label: 'Sold',    mod: 'sold' },
  sent:       { icon: '📦', label: 'Sent',    mod: 'sent' },
  in_transit: { icon: '🚚', label: 'Transit', mod: 'transit' },
  complete:   { icon: '✅', label: 'Done',    mod: 'complete' },
}

export function LifecycleBadge({ status }: LifecycleBadgeProps) {
  const { icon, label, mod } = CONFIG[status]
  return (
    <span className={`${styles.badge} ${styles[mod]}`}>
      {icon} {label}
    </span>
  )
}
```

- [ ] **Step 4: Create LifecycleBadge.module.css**

```css
/* src/frontend/src/features/ebay/components/LifecycleBadge.module.css */
.badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border-radius: 12px;
  padding: 3px 10px;
  font-size: 11px;
  font-weight: 600;
  border: 1px solid transparent;
  white-space: nowrap;
}

.sold     { color: var(--hd-red,    #e05252); background: color-mix(in srgb, var(--hd-red,    #e05252) 10%, transparent); border-color: color-mix(in srgb, var(--hd-red,    #e05252) 30%, transparent); }
.sent     { color: var(--hd-accent, #7c6af7); background: color-mix(in srgb, var(--hd-accent, #7c6af7) 10%, transparent); border-color: color-mix(in srgb, var(--hd-accent, #7c6af7) 30%, transparent); }
.transit  { color: var(--hd-amber,  #f7a535); background: color-mix(in srgb, var(--hd-amber,  #f7a535) 10%, transparent); border-color: color-mix(in srgb, var(--hd-amber,  #f7a535) 30%, transparent); }
.complete { color: var(--hd-green,  #3fc870); background: color-mix(in srgb, var(--hd-green,  #3fc870) 10%, transparent); border-color: color-mix(in srgb, var(--hd-green,  #3fc870) 30%, transparent); }
```

- [ ] **Step 5: Run tests — expect green**

```bash
cd src/frontend && npx vitest run src/features/ebay/components/__tests__/LifecycleBadge.test.tsx
```

Expected: 4 PASSED.

- [ ] **Step 6: Commit**

```bash
git add src/frontend/src/features/ebay/components/LifecycleBadge.tsx \
        src/frontend/src/features/ebay/components/LifecycleBadge.module.css \
        src/frontend/src/features/ebay/components/__tests__/LifecycleBadge.test.tsx
git commit -m "feat(ebay): add LifecycleBadge component"
```

---

## Task 11: SoldOrdersTable component

**Files:**
- Create: `src/frontend/src/features/ebay/components/SoldOrdersTable.tsx`
- Create: `src/frontend/src/features/ebay/components/SoldOrdersTable.module.css`
- Create: `src/frontend/src/features/ebay/components/__tests__/SoldOrdersTable.test.tsx`

- [ ] **Step 1: Write failing tests**

```typescript
// src/frontend/src/features/ebay/components/__tests__/SoldOrdersTable.test.tsx
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { SoldOrdersTable } from '../SoldOrdersTable'
import type { SoldOrder } from '../../soldOrders'

function makeOrder(overrides: Partial<SoldOrder> = {}): SoldOrder {
  return {
    orderId: 'ord-1',
    legacyOrderId: null,
    creationDate: '2026-05-09T00:00:00Z',
    orderFulfillmentStatus: 'NOT_STARTED',
    orderPaymentStatus: 'FULLY_PAID',
    buyerUsername: 'buyer_xyz',
    totalAmount: 42,
    currency: 'AUD',
    lineItems: [],
    local_status: null,
    displayStatus: 'sold',
    appCode: 'myapp',
    appName: 'My App',
    ...overrides,
  }
}

describe('SoldOrdersTable', () => {
  it('renders column headers', () => {
    render(<SoldOrdersTable orders={[]} isLoading={false} selectedId={undefined} onRowClick={vi.fn()} />)
    expect(screen.getByText('CARD')).toBeTruthy()
    expect(screen.getByText('PRICE')).toBeTruthy()
    expect(screen.getByText('BUYER')).toBeTruthy()
    expect(screen.getByText('STATUS')).toBeTruthy()
  })

  it('shows skeleton rows when loading', () => {
    const { container } = render(
      <SoldOrdersTable orders={[]} isLoading={true} selectedId={undefined} onRowClick={vi.fn()} />
    )
    expect(container.querySelectorAll('[data-testid="skeleton-row"]').length).toBeGreaterThan(0)
  })

  it('renders order row with buyer name', () => {
    render(
      <SoldOrdersTable orders={[makeOrder()]} isLoading={false} selectedId={undefined} onRowClick={vi.fn()} />
    )
    expect(screen.getByText('buyer_xyz')).toBeTruthy()
  })

  it('calls onRowClick with orderId when row clicked', () => {
    const onClick = vi.fn()
    render(
      <SoldOrdersTable orders={[makeOrder()]} isLoading={false} selectedId={undefined} onRowClick={onClick} />
    )
    fireEvent.click(screen.getByText('buyer_xyz').closest('tr')!)
    expect(onClick).toHaveBeenCalledWith('ord-1')
  })

  it('highlights the selected row', () => {
    const { container } = render(
      <SoldOrdersTable orders={[makeOrder()]} isLoading={false} selectedId="ord-1" onRowClick={vi.fn()} />
    )
    const row = container.querySelector('[data-selected="true"]')
    expect(row).toBeTruthy()
  })

  it('shows message icon for non-complete orders', () => {
    const { container } = render(
      <SoldOrdersTable orders={[makeOrder({ displayStatus: 'sold' })]} isLoading={false} selectedId={undefined} onRowClick={vi.fn()} />
    )
    expect(container.querySelector('[data-testid="msg-icon"]')).toBeTruthy()
  })

  it('hides message icon for complete orders', () => {
    const { container } = render(
      <SoldOrdersTable orders={[makeOrder({ displayStatus: 'complete' })]} isLoading={false} selectedId={undefined} onRowClick={vi.fn()} />
    )
    expect(container.querySelector('[data-testid="msg-icon"]')).toBeNull()
  })
})
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd src/frontend && npx vitest run src/features/ebay/components/__tests__/SoldOrdersTable.test.tsx 2>&1 | tail -5
```

Expected: `Cannot find module '../SoldOrdersTable'`.

- [ ] **Step 3: Create SoldOrdersTable.tsx**

```tsx
// src/frontend/src/features/ebay/components/SoldOrdersTable.tsx
import { LifecycleBadge } from './LifecycleBadge'
import type { SoldOrder } from '../soldOrders'
import styles from './SoldOrdersTable.module.css'

interface SoldOrdersTableProps {
  orders: SoldOrder[]
  isLoading: boolean
  selectedId: string | undefined
  onRowClick: (orderId: string) => void
}

function MsgIcon({ orderId }: { orderId: string }) {
  return (
    <a
      data-testid="msg-icon"
      href={`https://www.ebay.com.au/msg/inbox`}
      target="_blank"
      rel="noreferrer"
      className={styles.msgIcon}
      title="View messages on eBay"
      onClick={(e) => e.stopPropagation()}
    >
      <svg width="13" height="13" viewBox="0 0 16 16" fill="none" aria-hidden>
        <path
          d="M2 3a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v7a1 1 0 0 1-1 1H9l-3 2v-2H3a1 1 0 0 1-1-1V3Z"
          stroke="currentColor"
          strokeWidth="1.4"
          fill="none"
        />
      </svg>
    </a>
  )
}

function SkeletonRow() {
  return (
    <tr data-testid="skeleton-row" className={styles.skeletonRow}>
      <td><div className={styles.skeletonCell} /></td>
      <td><div className={styles.skeletonCell} style={{ width: 50 }} /></td>
      <td><div className={styles.skeletonCell} style={{ width: 70 }} /></td>
      <td />
      <td><div className={styles.skeletonCell} style={{ width: 80 }} /></td>
      <td><div className={styles.skeletonCell} style={{ width: 55 }} /></td>
    </tr>
  )
}

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  const diff = Math.floor((Date.now() - d.getTime()) / 3_600_000)
  if (diff < 1) return 'Just now'
  if (diff < 24) return `${diff}h ago`
  const days = Math.floor(diff / 24)
  if (days === 1) return 'Yesterday'
  if (days < 7) return `${days} days ago`
  return d.toLocaleDateString()
}

export function SoldOrdersTable({ orders, isLoading, selectedId, onRowClick }: SoldOrdersTableProps) {
  return (
    <table className={styles.table}>
      <thead>
        <tr>
          <th>CARD</th>
          <th>PRICE</th>
          <th>BUYER</th>
          <th>MSG</th>
          <th>STATUS</th>
          <th>SOLD</th>
        </tr>
      </thead>
      <tbody>
        {isLoading
          ? Array.from({ length: 5 }, (_, i) => <SkeletonRow key={i} />)
          : orders.map((order) => (
              <tr
                key={order.orderId}
                className={[styles.row, order.displayStatus === 'complete' ? styles.rowFaded : ''].filter(Boolean).join(' ')}
                data-selected={order.orderId === selectedId ? 'true' : undefined}
                onClick={() => onRowClick(order.orderId)}
              >
                <td className={styles.cardCell}>
                  <div className={styles.cardTitle}>
                    {order.lineItems[0]?.title ?? 'Order'}
                  </div>
                  <div className={styles.cardMeta}>#{order.legacyOrderId ?? order.orderId}</div>
                </td>
                <td className={styles.priceCell}>
                  {order.totalAmount != null
                    ? `$${order.totalAmount.toFixed(2)}`
                    : '—'}
                </td>
                <td className={styles.buyerCell}>{order.buyerUsername ?? '—'}</td>
                <td className={styles.msgCell}>
                  {order.displayStatus !== 'complete' && <MsgIcon orderId={order.orderId} />}
                </td>
                <td>
                  <LifecycleBadge status={order.displayStatus} />
                </td>
                <td className={styles.dateCell}>{formatDate(order.creationDate)}</td>
              </tr>
            ))}
      </tbody>
    </table>
  )
}
```

- [ ] **Step 4: Create SoldOrdersTable.module.css**

```css
/* src/frontend/src/features/ebay/components/SoldOrdersTable.module.css */
.table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.table th {
  padding: 8px 12px;
  text-align: left;
  font-size: 11px;
  color: var(--hd-sub, #555);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  border-bottom: 1px solid var(--hd-border, #1a1a1f);
  background: var(--hd-surface-alt, #090909);
}

.row {
  cursor: pointer;
  border-bottom: 1px solid var(--hd-border-subtle, #13131a);
  transition: background 120ms;
}
.row:hover { background: var(--hd-hover, #111118); }
.row[data-selected="true"] {
  background: color-mix(in srgb, var(--hd-accent, #7c6af7) 8%, transparent);
  border-left: 2px solid var(--hd-accent, #7c6af7);
}

.rowFaded { opacity: 0.55; }
.rowFaded:hover { opacity: 1; }

.table td { padding: 11px 12px; vertical-align: middle; }

.cardTitle { color: var(--hd-text, #e8e8e8); font-weight: 500; }
.cardMeta  { font-size: 11px; color: var(--hd-sub, #555); margin-top: 2px; }

.priceCell { color: var(--hd-text, #e8e8e8); font-variant-numeric: tabular-nums; }
.buyerCell { font-size: 12px; color: var(--hd-sub2, #777); }
.msgCell   { text-align: center; width: 36px; }
.dateCell  { font-size: 11px; color: var(--hd-sub, #555); white-space: nowrap; }

.msgIcon {
  color: var(--hd-sub, #555);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  transition: color 120ms, background 120ms;
}
.msgIcon:hover {
  color: var(--hd-accent, #7c6af7);
  background: color-mix(in srgb, var(--hd-accent, #7c6af7) 12%, transparent);
}

.skeletonRow td { padding: 12px 12px; }
.skeletonCell {
  height: 12px;
  width: 100%;
  border-radius: 4px;
  background: var(--hd-skeleton, #1a1a1f);
  animation: shimmer 1.4s ease-in-out infinite;
}

@keyframes shimmer {
  0%, 100% { opacity: 0.4; }
  50%       { opacity: 0.8; }
}
```

- [ ] **Step 5: Run tests — expect green**

```bash
cd src/frontend && npx vitest run src/features/ebay/components/__tests__/SoldOrdersTable.test.tsx
```

Expected: 7 PASSED.

- [ ] **Step 6: Commit**

```bash
git add src/frontend/src/features/ebay/components/SoldOrdersTable.tsx \
        src/frontend/src/features/ebay/components/SoldOrdersTable.module.css \
        src/frontend/src/features/ebay/components/__tests__/SoldOrdersTable.test.tsx
git commit -m "feat(ebay): add SoldOrdersTable component"
```

---

## Task 12: SoldOrderDetailPanel component

**Files:**
- Create: `src/frontend/src/features/ebay/components/SoldOrderDetailPanel.tsx`
- Create: `src/frontend/src/features/ebay/components/SoldOrderDetailPanel.module.css`
- Create: `src/frontend/src/features/ebay/components/__tests__/SoldOrderDetailPanel.test.tsx`

- [ ] **Step 1: Write failing tests**

```typescript
// src/frontend/src/features/ebay/components/__tests__/SoldOrderDetailPanel.test.tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { SoldOrderDetailPanel } from '../SoldOrderDetailPanel'
import type { SoldOrder } from '../../soldOrders'

vi.mock('../../api', () => ({
  markOrderSent: vi.fn().mockResolvedValue(undefined),
  markOrderSentWithTracking: vi.fn().mockResolvedValue(undefined),
  updateOrderLocalStatus: vi.fn().mockResolvedValue(undefined),
}))

import { markOrderSent, updateOrderLocalStatus } from '../../api'

function makeOrder(overrides: Partial<SoldOrder> = {}): SoldOrder {
  return {
    orderId: 'ord-1',
    legacyOrderId: '12-34567',
    creationDate: '2026-05-09T00:00:00Z',
    orderFulfillmentStatus: 'NOT_STARTED',
    orderPaymentStatus: 'FULLY_PAID',
    buyerUsername: 'buyer_xyz',
    totalAmount: 42,
    currency: 'AUD',
    lineItems: [{ lineItemId: 'li-1', legacyItemId: null, title: 'Sheoldred', quantity: 1, lineItemFulfillmentStatus: null }],
    local_status: null,
    displayStatus: 'sold',
    appCode: 'myapp',
    appName: 'My App',
    ...overrides,
  }
}

describe('SoldOrderDetailPanel', () => {
  beforeEach(() => {
    vi.mocked(markOrderSent).mockClear()
    vi.mocked(updateOrderLocalStatus).mockClear()
  })

  it('renders order info', () => {
    render(<SoldOrderDetailPanel order={makeOrder()} onClose={vi.fn()} onStatusChange={vi.fn()} />)
    expect(screen.getByText('buyer_xyz')).toBeTruthy()
    expect(screen.getByText('$42.00 AUD')).toBeTruthy()
  })

  it('shows Mark as sent and Add tracking buttons for sold stage', () => {
    render(<SoldOrderDetailPanel order={makeOrder()} onClose={vi.fn()} onStatusChange={vi.fn()} />)
    expect(screen.getByText(/Mark as sent/i)).toBeTruthy()
    expect(screen.getByText(/Add tracking/i)).toBeTruthy()
  })

  it('calls markOrderSent and onStatusChange on mark sent click', async () => {
    const onStatusChange = vi.fn()
    render(<SoldOrderDetailPanel order={makeOrder()} onClose={vi.fn()} onStatusChange={onStatusChange} />)
    fireEvent.click(screen.getByText(/Mark as sent/i))
    await waitFor(() => expect(markOrderSent).toHaveBeenCalledWith('myapp', 'ord-1', ['li-1']))
    expect(onStatusChange).toHaveBeenCalledWith('ord-1', 'sent')
  })

  it('shows Mark in transit button for sent stage', () => {
    render(<SoldOrderDetailPanel order={makeOrder({ displayStatus: 'sent' })} onClose={vi.fn()} onStatusChange={vi.fn()} />)
    expect(screen.getByText(/Mark in transit/i)).toBeTruthy()
  })

  it('shows Mark complete button for in_transit stage', () => {
    render(<SoldOrderDetailPanel order={makeOrder({ displayStatus: 'in_transit' })} onClose={vi.fn()} onStatusChange={vi.fn()} />)
    expect(screen.getByText(/Mark complete/i)).toBeTruthy()
  })

  it('shows no action buttons for complete stage', () => {
    render(<SoldOrderDetailPanel order={makeOrder({ displayStatus: 'complete' })} onClose={vi.fn()} onStatusChange={vi.fn()} />)
    expect(screen.queryByText(/Mark/i)).toBeNull()
  })

  it('reveals tracking form when Add tracking clicked', () => {
    render(<SoldOrderDetailPanel order={makeOrder()} onClose={vi.fn()} onStatusChange={vi.fn()} />)
    fireEvent.click(screen.getByText(/Add tracking/i))
    expect(screen.getByPlaceholderText(/Tracking number/i)).toBeTruthy()
  })

  it('calls onClose when close button clicked', () => {
    const onClose = vi.fn()
    render(<SoldOrderDetailPanel order={makeOrder()} onClose={onClose} onStatusChange={vi.fn()} />)
    fireEvent.click(screen.getByLabelText('Close panel'))
    expect(onClose).toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd src/frontend && npx vitest run src/features/ebay/components/__tests__/SoldOrderDetailPanel.test.tsx 2>&1 | tail -5
```

Expected: `Cannot find module '../SoldOrderDetailPanel'`.

- [ ] **Step 3: Create SoldOrderDetailPanel.tsx**

```tsx
// src/frontend/src/features/ebay/components/SoldOrderDetailPanel.tsx
import { useState } from 'react'
import type { SoldOrder, DisplayStatus } from '../soldOrders'
import { markOrderSent, markOrderSentWithTracking, updateOrderLocalStatus } from '../api'
import { LifecycleBadge } from './LifecycleBadge'
import styles from './SoldOrderDetailPanel.module.css'

const STAGES: DisplayStatus[] = ['sold', 'sent', 'in_transit', 'complete']
const STAGE_ICONS: Record<DisplayStatus, string> = {
  sold: '💰', sent: '📦', in_transit: '🚚', complete: '✅',
}
const STAGE_LABELS: Record<DisplayStatus, string> = {
  sold: 'Sold', sent: 'Sent', in_transit: 'Transit', complete: 'Done',
}

const COMMON_CARRIERS = ['AusPost', 'DHL', 'FedEx', 'UPS', 'TNT', 'StarTrack', 'CouriersPlease']

interface Props {
  order: SoldOrder
  onClose: () => void
  onStatusChange: (orderId: string, newStatus: DisplayStatus) => void
}

export function SoldOrderDetailPanel({ order, onClose, onStatusChange }: Props) {
  const [showTrackingForm, setShowTrackingForm] = useState(false)
  const [carrier, setCarrier] = useState(COMMON_CARRIERS[0])
  const [trackingNum, setTrackingNum] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const lineItemIds = order.lineItems.map((li) => li.lineItemId).filter(Boolean) as string[]

  async function handleMarkSent() {
    setIsSubmitting(true)
    setError(null)
    try {
      await markOrderSent(order.appCode, order.orderId, lineItemIds)
      onStatusChange(order.orderId, 'sent')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to mark as sent')
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleMarkSentWithTracking(e: React.FormEvent) {
    e.preventDefault()
    if (!trackingNum.trim()) return
    setIsSubmitting(true)
    setError(null)
    try {
      await markOrderSentWithTracking(order.appCode, order.orderId, lineItemIds, carrier, trackingNum.trim())
      onStatusChange(order.orderId, 'sent')
      setShowTrackingForm(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to mark as sent')
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleLocalStatus(newStatus: 'in_transit' | 'complete') {
    setIsSubmitting(true)
    setError(null)
    try {
      await updateOrderLocalStatus(order.appCode, order.orderId, newStatus)
      onStatusChange(order.orderId, newStatus)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update status')
    } finally {
      setIsSubmitting(false)
    }
  }

  const currentIdx = STAGES.indexOf(order.displayStatus)
  const cardTitle = order.lineItems[0]?.title ?? 'Order'

  return (
    <aside className={styles.panel}>
      {/* Header */}
      <div className={styles.header}>
        <div>
          <div className={styles.headerTitle}>{cardTitle}</div>
          <div className={styles.headerMeta}>#{order.legacyOrderId ?? order.orderId}</div>
        </div>
        <button className={styles.closeBtn} aria-label="Close panel" onClick={onClose}>✕</button>
      </div>

      {/* Lifecycle strip */}
      <div className={styles.section}>
        <div className={styles.sectionLabel}>Lifecycle</div>
        <div className={styles.strip}>
          {STAGES.map((stage, i) => (
            <div key={stage} className={styles.stripItem}>
              <div className={[styles.stripDot, i === currentIdx ? styles.stripDotActive : i < currentIdx ? styles.stripDotDone : styles.stripDotFuture].join(' ')}>
                {STAGE_ICONS[stage]}
              </div>
              <div className={[styles.stripLabel, i === currentIdx ? styles.stripLabelActive : ''].join(' ')}>
                {STAGE_LABELS[stage]}
              </div>
              {i < STAGES.length - 1 && (
                <div className={[styles.stripLine, i < currentIdx ? styles.stripLineDone : ''].join(' ')} />
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Order info */}
      <div className={styles.section}>
        <div className={styles.sectionLabel}>Order</div>
        <div className={styles.infoRow}>
          <span className={styles.infoKey}>Sale price</span>
          <span className={styles.infoVal}>
            {order.totalAmount != null ? `$${order.totalAmount.toFixed(2)} ${order.currency ?? ''}` : '—'}
          </span>
        </div>
        <div className={styles.infoRow}>
          <span className={styles.infoKey}>Buyer</span>
          <span className={styles.infoValAccent}>{order.buyerUsername ?? '—'}</span>
        </div>
        <div className={styles.infoRow}>
          <span className={styles.infoKey}>Sold</span>
          <span className={styles.infoVal}>
            {order.creationDate ? new Date(order.creationDate).toLocaleDateString() : '—'}
          </span>
        </div>
        <div className={styles.infoRow}>
          <span className={styles.infoKey}>Order ID</span>
          <span className={styles.infoValMono}>{order.orderId}</span>
        </div>
      </div>

      {/* Message banner */}
      <div className={styles.messageBanner}>
        <span className={styles.messageBannerIcon}>💬</span>
        <div className={styles.messageBannerBody}>
          <div className={styles.messageBannerTitle}>Messages from buyer</div>
        </div>
        <a
          className={styles.messageBannerLink}
          href="https://www.ebay.com.au/msg/inbox"
          target="_blank"
          rel="noreferrer"
        >
          View ↗
        </a>
      </div>

      {/* Error */}
      {error && <div className={styles.errorMsg}>{error}</div>}

      {/* Actions */}
      <div className={styles.actions}>
        {order.displayStatus === 'sold' && !showTrackingForm && (
          <>
            <button
              className={styles.btnPrimary}
              disabled={isSubmitting}
              onClick={handleMarkSent}
            >
              📦 Mark as sent
            </button>
            <button
              className={styles.btnSecondary}
              disabled={isSubmitting}
              onClick={() => setShowTrackingForm(true)}
            >
              🔗 Add tracking number
            </button>
          </>
        )}

        {order.displayStatus === 'sold' && showTrackingForm && (
          <form onSubmit={handleMarkSentWithTracking} className={styles.trackingForm}>
            <select
              className={styles.trackingSelect}
              value={carrier}
              onChange={(e) => setCarrier(e.target.value)}
            >
              {COMMON_CARRIERS.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
            <input
              className={styles.trackingInput}
              placeholder="Tracking number"
              value={trackingNum}
              onChange={(e) => setTrackingNum(e.target.value)}
              required
            />
            <button className={styles.btnPrimary} type="submit" disabled={isSubmitting}>
              📦 Confirm & send
            </button>
            <button
              className={styles.btnGhost}
              type="button"
              onClick={() => setShowTrackingForm(false)}
            >
              Cancel
            </button>
          </form>
        )}

        {order.displayStatus === 'sent' && (
          <button
            className={styles.btnSecondary}
            disabled={isSubmitting}
            onClick={() => handleLocalStatus('in_transit')}
          >
            🚚 Mark in transit
          </button>
        )}

        {order.displayStatus === 'in_transit' && (
          <button
            className={styles.btnSecondary}
            disabled={isSubmitting}
            onClick={() => handleLocalStatus('complete')}
          >
            ✅ Mark complete
          </button>
        )}

        <a
          className={styles.btnGhost}
          href={`https://www.ebay.com.au/vod/FetchOrderDetails?orderId=${order.legacyOrderId ?? order.orderId}`}
          target="_blank"
          rel="noreferrer"
        >
          View order on eBay ↗
        </a>
      </div>
    </aside>
  )
}
```

- [ ] **Step 4: Create SoldOrderDetailPanel.module.css**

```css
/* src/frontend/src/features/ebay/components/SoldOrderDetailPanel.module.css */
.panel {
  width: 300px;
  min-width: 280px;
  background: var(--hd-surface-panel, #0a0a10);
  border-left: 1px solid var(--hd-border, #1a1a1f);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  height: 100%;
}

.header {
  padding: 14px 16px;
  border-bottom: 1px solid var(--hd-border, #1a1a1f);
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
}
.headerTitle { font-size: 13px; color: var(--hd-text, #e8e8e8); font-weight: 600; line-height: 1.3; }
.headerMeta  { font-size: 11px; color: var(--hd-sub, #555); margin-top: 3px; }
.closeBtn    { background: none; border: none; color: var(--hd-sub, #888); cursor: pointer; padding: 2px 4px; font-size: 14px; }
.closeBtn:hover { color: var(--hd-text, #e8e8e8); }

.section { padding: 14px 16px; border-bottom: 1px solid var(--hd-border, #1a1a1f); }
.sectionLabel { font-size: 10px; color: var(--hd-sub, #555); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 10px; }

/* Lifecycle strip */
.strip { display: flex; align-items: flex-start; position: relative; }
.stripItem { display: flex; flex-direction: column; align-items: center; gap: 3px; position: relative; flex: 1; }
.stripDot {
  width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
  font-size: 13px; border: 2px solid var(--hd-border-strong, #2a2a32);
  background: var(--hd-surface-alt, #1a1a1f);
}
.stripDotActive { border-color: var(--hd-accent, #7c6af7); background: color-mix(in srgb, var(--hd-accent, #7c6af7) 15%, transparent); }
.stripDotDone   { border-color: var(--hd-border-strong, #2a2a32); opacity: 0.6; }
.stripDotFuture { opacity: 0.3; }
.stripLabel       { font-size: 9px; color: var(--hd-sub, #555); font-weight: 600; text-align: center; }
.stripLabelActive { color: var(--hd-accent, #7c6af7); }
.stripLine {
  position: absolute; top: 14px; left: 50%; width: 100%;
  height: 2px; background: var(--hd-border, #1e1e24);
}
.stripLineDone { background: color-mix(in srgb, var(--hd-accent, #7c6af7) 40%, transparent); }

/* Order info */
.infoRow        { display: flex; justify-content: space-between; margin-bottom: 6px; }
.infoKey        { font-size: 12px; color: var(--hd-sub, #555); }
.infoVal        { font-size: 12px; color: var(--hd-text, #e8e8e8); }
.infoValAccent  { font-size: 12px; color: var(--hd-accent, #7c6af7); }
.infoValMono    { font-size: 11px; color: var(--hd-sub, #555); font-family: monospace; }

/* Message banner */
.messageBanner {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--hd-border, #1a1a1f);
  background: color-mix(in srgb, var(--hd-accent, #7c6af7) 4%, transparent);
}
.messageBannerIcon { font-size: 16px; }
.messageBannerBody { flex: 1; }
.messageBannerTitle { font-size: 12px; color: var(--hd-text, #e8e8e8); font-weight: 500; }
.messageBannerLink  { font-size: 11px; color: var(--hd-accent, #7c6af7); text-decoration: none; white-space: nowrap; }
.messageBannerLink:hover { text-decoration: underline; }

/* Error */
.errorMsg { margin: 8px 16px; font-size: 12px; color: var(--hd-red, #e05252); background: color-mix(in srgb, var(--hd-red, #e05252) 8%, transparent); padding: 8px 12px; border-radius: 6px; }

/* Actions */
.actions { padding: 14px 16px; display: flex; flex-direction: column; gap: 8px; }

.btnPrimary {
  width: 100%; background: var(--hd-accent, #7c6af7); color: #fff; border: none;
  border-radius: 7px; padding: 9px 14px; font-size: 13px; font-weight: 600; cursor: pointer;
  display: flex; align-items: center; justify-content: center; gap: 6px;
}
.btnPrimary:hover:not(:disabled) { opacity: 0.9; }
.btnPrimary:disabled { opacity: 0.5; cursor: not-allowed; }

.btnSecondary {
  width: 100%; background: var(--hd-surface-alt, #1a1a1f);
  color: var(--hd-text-sub, #bbb);
  border: 1px solid var(--hd-border-strong, #2a2a32);
  border-radius: 7px; padding: 8px 14px; font-size: 12px; cursor: pointer;
  display: flex; align-items: center; justify-content: center; gap: 6px;
}
.btnSecondary:hover:not(:disabled) { border-color: var(--hd-accent, #7c6af7); color: var(--hd-text, #e8e8e8); }
.btnSecondary:disabled { opacity: 0.5; cursor: not-allowed; }

.btnGhost {
  width: 100%; background: transparent; color: var(--hd-sub, #555); border: none;
  border-radius: 7px; padding: 6px 14px; font-size: 11px; cursor: pointer;
  text-align: center; text-decoration: none; display: block;
}
.btnGhost:hover { color: var(--hd-text, #e8e8e8); }

.trackingForm { display: flex; flex-direction: column; gap: 8px; }
.trackingSelect, .trackingInput {
  width: 100%; background: var(--hd-surface-alt, #1a1a1f);
  border: 1px solid var(--hd-border-strong, #2a2a32);
  border-radius: 6px; padding: 7px 10px; font-size: 12px;
  color: var(--hd-text, #e8e8e8); outline: none;
}
.trackingSelect:focus, .trackingInput:focus { border-color: var(--hd-accent, #7c6af7); }
```

- [ ] **Step 5: Run tests — expect green**

```bash
cd src/frontend && npx vitest run src/features/ebay/components/__tests__/SoldOrderDetailPanel.test.tsx
```

Expected: 8 PASSED.

- [ ] **Step 6: Commit**

```bash
git add src/frontend/src/features/ebay/components/SoldOrderDetailPanel.tsx \
        src/frontend/src/features/ebay/components/SoldOrderDetailPanel.module.css \
        src/frontend/src/features/ebay/components/__tests__/SoldOrderDetailPanel.test.tsx
git commit -m "feat(ebay): add SoldOrderDetailPanel component with lifecycle strip and action buttons"
```

---

## Task 13: Wire up the Sold tab in listings.tsx

**Files:**
- Modify: `src/frontend/src/routes/listings.tsx`
- Modify: `src/frontend/src/routes/__tests__/listings.test.tsx` (add sold-tab test)

- [ ] **Step 1: Add a sold-tab smoke test to the existing test file**

Open `src/frontend/src/routes/__tests__/listings.test.tsx` and add:

```typescript
it('shows sold tab and switches to it', async () => {
  render(<ListingsPage />)
  const soldTab = screen.getByRole('tab', { name: /sold/i })
  expect(soldTab).toBeTruthy()
  fireEvent.click(soldTab)
  // After clicking Sold, the active listings table should be gone and sold content visible
  await waitFor(() => {
    expect(screen.queryByText('Order history coming soon')).toBeNull()
  })
})
```

- [ ] **Step 2: Run to confirm the "coming soon" assertion still passes (it will until we wire up)**

```bash
cd src/frontend && npx vitest run src/routes/__tests__/listings.test.tsx 2>&1 | tail -10
```

Note the existing pass count.

- [ ] **Step 3: Wire up the Sold tab in listings.tsx**

At the top of `src/frontend/src/routes/listings.tsx`, add new imports:

```typescript
import { SoldOrdersTable } from '../features/ebay/components/SoldOrdersTable'
import { SoldOrderDetailPanel } from '../features/ebay/components/SoldOrderDetailPanel'
import {
  fetchSoldOrders,
  markOrderSent,
  markOrderSentWithTracking,
  updateOrderLocalStatus,
} from '../features/ebay/api'
import type { SoldOrder, DisplayStatus } from '../features/ebay/soldOrders'
```

Inside `ListingsPage`, add state for sold orders after the existing state declarations:

```typescript
const [soldOrders, setSoldOrders] = useState<SoldOrder[]>([])
const [isSoldLoading, setIsSoldLoading] = useState(false)
const [selectedOrderId, setSelectedOrderId] = useState<string | null>(null)
```

Add a `useEffect` that fires when the tab switches to `'sold'`:

```typescript
useEffect(() => {
  if (tab !== 'sold') return
  let cancelled = false
  async function loadSold() {
    setIsSoldLoading(true)
    try {
      const results = await Promise.allSettled(
        productionApps.map((app) =>
          fetchSoldOrders(app.app_code, 25, 0).then(({ orders }) =>
            orders.map((o) => ({ ...o, appName: app.app_name }))
          )
        )
      )
      if (cancelled) return
      const merged: SoldOrder[] = []
      results.forEach((r) => { if (r.status === 'fulfilled') merged.push(...r.value) })
      setSoldOrders(merged)
    } finally {
      if (!cancelled) setIsSoldLoading(false)
    }
  }
  loadSold()
  return () => { cancelled = true }
}, [tab, productionApps])
```

Add a status-change handler:

```typescript
function handleOrderStatusChange(orderId: string, newStatus: DisplayStatus) {
  setSoldOrders((prev) =>
    prev.map((o) => o.orderId === orderId ? { ...o, displayStatus: newStatus, local_status: newStatus } : o)
  )
}
```

Replace the existing `{tab === 'sold' && ...}` block with:

```tsx
{tab === 'sold' && (
  <div className={selectedOrderId ? styles.withPanel : undefined}>
    <div>
      <SoldOrdersTable
        orders={soldOrders}
        isLoading={isSoldLoading}
        selectedId={selectedOrderId ?? undefined}
        onRowClick={(id) => setSelectedOrderId(id)}
      />
    </div>
    {selectedOrderId && (() => {
      const order = soldOrders.find((o) => o.orderId === selectedOrderId)
      return order ? (
        <div>
          <SoldOrderDetailPanel
            order={order}
            onClose={() => setSelectedOrderId(null)}
            onStatusChange={handleOrderStatusChange}
          />
        </div>
      ) : null
    })()}
  </div>
)}
```

Also update the Sold tab pill count in the tab bar — find the existing tab render and add the count for sold:

```tsx
{t === 'sold' && !isSoldLoading && soldOrders.length > 0 && (
  <span className={styles.tabCount}>{soldOrders.length}</span>
)}
```

- [ ] **Step 4: Run the full frontend test suite**

```bash
cd src/frontend && npx vitest run 2>&1 | tail -15
```

Expected: all previously passing tests still pass; the new sold-tab smoke test passes.

- [ ] **Step 5: Commit**

```bash
git add src/frontend/src/routes/listings.tsx \
        src/frontend/src/routes/__tests__/listings.test.tsx
git commit -m "feat(ebay): wire sold tab to SoldOrdersTable + SoldOrderDetailPanel in listings page"
```

---

## Self-Review Checklist (run after all tasks)

```bash
# Full backend test suite
cd src && python -m pytest automana/tests/ -q --tb=short

# Full frontend test suite
cd src/frontend && npx vitest run

# App import sanity (catches circular imports & registry conflicts)
cd src && python -c "from automana.api.app import create_app; print('app OK')"

# Check migration is listed
docker exec automana-postgres-dev psql -U automana_admin automana \
  -c "SELECT column_name FROM information_schema.columns WHERE table_name='ebay_order_status' ORDER BY ordinal_position;"
```
