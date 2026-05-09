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
