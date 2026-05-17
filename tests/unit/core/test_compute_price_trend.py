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


from datetime import date


async def test_get_price_history_returns_empty_list_when_no_data():
    from automana.core.repositories.pricing.price_repository import PricingTierRepository
    from unittest.mock import AsyncMock, MagicMock
    from uuid import uuid4

    mock_conn = MagicMock()
    mock_conn.fetch = AsyncMock(return_value=[])
    repo = PricingTierRepository(connection=mock_conn)

    result = await repo.get_price_history(uuid4(), finish_id=1, condition_id=1, days=90)

    assert result == []


async def test_get_price_history_returns_sorted_dicts():
    from automana.core.repositories.pricing.price_repository import PricingTierRepository
    from unittest.mock import AsyncMock, MagicMock
    from uuid import uuid4

    mock_conn = MagicMock()
    mock_conn.fetch = AsyncMock(return_value=[
        {"price_date": date(2026, 4, 1), "list_avg_cents": 1000, "list_low_cents": 900, "source_code": "tcg"},
        {"price_date": date(2026, 5, 1), "list_avg_cents": 1200, "list_low_cents": 1100, "source_code": "tcg"},
    ])
    repo = PricingTierRepository(connection=mock_conn)

    result = await repo.get_price_history(uuid4(), finish_id=1, condition_id=1, days=90)

    assert len(result) == 2
    assert result[0]["price_date"] == date(2026, 4, 1)
    assert result[1]["list_avg_cents"] == 1200
    assert result[0]["source_code"] == "tcg"
