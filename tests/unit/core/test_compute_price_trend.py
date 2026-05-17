from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4


async def test_get_listing_meta_returns_none_for_missing_item():
    from automana.core.repositories.app_integration.ebay.sales_repository import EbaySalesRepository

    repo = EbaySalesRepository(connection=MagicMock())
    repo.execute_query = AsyncMock(return_value=[])

    result = await repo.get_listing_meta("missing-item", "myapp")

    assert result is None


async def test_get_listing_meta_returns_dict_for_existing_item():
    from automana.core.repositories.app_integration.ebay.sales_repository import EbaySalesRepository

    card_id = uuid4()
    repo = EbaySalesRepository(connection=MagicMock())
    repo.execute_query = AsyncMock(return_value=[{
        "card_version_id": card_id,
        "finish_id": 1,
        "condition_id": 1,
        "language_id": 1,
        "finish_code": "NONFOIL",
        "condition_code": "NM",
    }])

    result = await repo.get_listing_meta("item-123", "myapp")

    assert result["card_version_id"] == card_id
    assert result["finish_code"] == "NONFOIL"
    assert result["condition_code"] == "NM"


async def test_get_listing_meta_returns_none_when_card_version_id_is_null():
    from automana.core.repositories.app_integration.ebay.sales_repository import EbaySalesRepository

    repo = EbaySalesRepository(connection=MagicMock())
    repo.execute_query = AsyncMock(return_value=[{
        "card_version_id": None,
        "finish_id": 1,
        "condition_id": 1,
        "language_id": 1,
        "finish_code": "NONFOIL",
        "condition_code": "NM",
    }])

    result = await repo.get_listing_meta("item-123", "myapp")

    assert result is None
