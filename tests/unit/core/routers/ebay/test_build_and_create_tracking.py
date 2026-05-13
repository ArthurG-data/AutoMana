import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

CARD_VERSION_ID = UUID("12345678-1234-5678-1234-567812345678")
USER_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


def _make_service_manager(side_effects):
    """service_manager.execute_service with sequential side effects."""
    sm = MagicMock()
    sm.execute_service = AsyncMock(side_effect=side_effects)
    return sm


def _ebay_success_result(item_id: str) -> dict:
    return {"AddItemResponse": {"Ack": "Success", "ItemID": item_id}}


def _ebay_result_no_item_id() -> dict:
    return {"AddItemResponse": {"Ack": "Success"}}


@pytest.mark.asyncio
async def test_tracking_called_on_success():
    from automana.api.routers.integrations.ebay.ebay_selling import build_and_create_listing
    from automana.api.routers.integrations.ebay.ebay_selling import BuildListingRequest

    sm = _make_service_manager([
        _ebay_success_result("12345"),
        None,
    ])
    user = MagicMock(unique_id=USER_ID)
    body = BuildListingRequest(
        card_version_id=CARD_VERSION_ID,
        condition="NM",
        quantity=1,
        price_aud="5.00",
    )

    with patch("automana.api.routers.integrations.ebay.ebay_selling.logger"):
        result = await build_and_create_listing(
            body=body, user=user, service_manager=sm,
            app_code="my-app", idempotency_key="idem-1",
        )

    assert result.data == _ebay_success_result("12345")
    assert sm.execute_service.call_count == 2
    track_call = sm.execute_service.call_args_list[1]
    assert track_call.kwargs["item_id"] == "12345"
    assert track_call.kwargs["card_version_id"] == CARD_VERSION_ID


@pytest.mark.asyncio
async def test_tracking_skipped_when_no_item_id():
    from automana.api.routers.integrations.ebay.ebay_selling import build_and_create_listing
    from automana.api.routers.integrations.ebay.ebay_selling import BuildListingRequest

    sm = _make_service_manager([_ebay_result_no_item_id()])
    user = MagicMock(unique_id=USER_ID)
    body = BuildListingRequest(
        card_version_id=CARD_VERSION_ID,
        condition="NM",
        quantity=1,
        price_aud="5.00",
    )

    result = await build_and_create_listing(
        body=body, user=user, service_manager=sm,
        app_code="my-app", idempotency_key="idem-2",
    )

    assert result.data == _ebay_result_no_item_id()
    assert sm.execute_service.call_count == 1


@pytest.mark.asyncio
async def test_tracking_failure_does_not_fail_request():
    from automana.api.routers.integrations.ebay.ebay_selling import build_and_create_listing
    from automana.api.routers.integrations.ebay.ebay_selling import BuildListingRequest

    sm = _make_service_manager([
        _ebay_success_result("67890"),
        RuntimeError("DB unavailable"),
    ])
    user = MagicMock(unique_id=USER_ID)
    body = BuildListingRequest(
        card_version_id=CARD_VERSION_ID,
        condition="NM",
        quantity=1,
        price_aud="5.00",
    )

    with patch("automana.api.routers.integrations.ebay.ebay_selling.logger") as mock_log:
        result = await build_and_create_listing(
            body=body, user=user, service_manager=sm,
            app_code="my-app", idempotency_key="idem-3",
        )

    assert result.data == _ebay_success_result("67890")
    mock_log.warning.assert_called_once()
    assert sm.execute_service.call_count == 2
