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
