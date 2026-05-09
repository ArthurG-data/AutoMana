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
    with patch(
        "automana.core.services.app_integration.ebay.fulfillment_service.resolve_token",
        new=AsyncMock(return_value="tok"),
    ):
        result = await update_order_local_status(
            auth_repository=auth_repo,
            app_repository=app_repo,
            user_id=USER_ID,
            order_id="ord-1",
            app_code="myapp",
            local_status="in_transit",
        )
    app_repo.upsert_order_status.assert_awaited_once_with(
        order_id="ord-1",
        app_code="myapp",
        local_status="in_transit",
    )
    assert result == {"order_id": "ord-1", "local_status": "in_transit"}
