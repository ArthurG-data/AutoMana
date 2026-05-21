import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

from automana.core.repositories.app_integration.ebay.sales_repository import (
    EbaySalesRepository,
)


CARD_ID = UUID("12345678-1234-5678-1234-567812345678")
SOURCE_PRODUCT_ID = 42


@pytest.fixture
def repo():
    conn = MagicMock()
    r = EbaySalesRepository(connection=conn, executor=None)
    r.execute_query = AsyncMock()
    r.execute_command = AsyncMock()
    return r


@pytest.mark.asyncio
async def test_ensure_source_product_returns_id(repo):
    repo.execute_query.return_value = [{"source_product_id": SOURCE_PRODUCT_ID}]
    result = await repo.ensure_source_product(CARD_ID, source_id=5)
    assert result == SOURCE_PRODUCT_ID
    repo.execute_query.assert_called_once()


@pytest.mark.asyncio
async def test_ensure_source_product_returns_none_when_empty(repo):
    repo.execute_query.return_value = []
    result = await repo.ensure_source_product(CARD_ID, source_id=5)
    assert result is None


@pytest.mark.asyncio
async def test_upsert_active_listing_calls_command(repo):
    now = datetime.now(timezone.utc)
    await repo.upsert_active_listing("item-123", "my-app", CARD_ID, now)
    repo.execute_command.assert_called_once()
    args = repo.execute_command.call_args[0][1]
    assert args[0] == "item-123"
    assert args[1] == "my-app"
    assert args[7] == now  # listed_at is 8th param after condition/finish/language/marketplace


@pytest.mark.asyncio
async def test_get_card_version_by_item_returns_uuid(repo):
    repo.execute_query.return_value = [{"card_version_id": str(CARD_ID)}]
    result = await repo.get_card_version_by_item("item-123")
    assert result == CARD_ID


@pytest.mark.asyncio
async def test_get_card_version_by_item_returns_none_when_missing(repo):
    repo.execute_query.return_value = []
    result = await repo.get_card_version_by_item("unknown-item")
    assert result is None


@pytest.mark.asyncio
async def test_get_listed_card_versions_returns_list(repo):
    repo.execute_query.return_value = [
        {"card_version_id": str(CARD_ID)},
    ]
    result = await repo.get_listed_card_versions("my-app")
    assert result == [CARD_ID]


@pytest.mark.asyncio
async def test_get_listed_card_versions_empty(repo):
    repo.execute_query.return_value = []
    result = await repo.get_listed_card_versions("my-app")
    assert result == []


@pytest.mark.asyncio
async def test_upsert_order_source_product_calls_command(repo):
    now = datetime.now(timezone.utc)
    await repo.upsert_order_source_product(
        order_id="order-1",
        app_code="my-app",
        item_id="item-1",
        title="Bolt",
        source_product_id=SOURCE_PRODUCT_ID,
        quantity=1,
        sold_price_cents=200,
        currency="USD",
        finish_id=1,
        condition_id=2,
        language_id=1,
        sold_at=now,
        buyer_username="buyer1",
    )
    repo.execute_command.assert_called_once()


@pytest.mark.asyncio
async def test_get_unpromoted_returns_dicts(repo):
    repo.execute_query.return_value = [
        {
            "ebay_osp_id": 1,
            "source_product_id": SOURCE_PRODUCT_ID,
            "sold_price_cents": 300,
            "sold_at": datetime.now(timezone.utc),
            "finish_id": 1,
            "condition_id": 2,
            "language_id": 1,
        }
    ]
    result = await repo.get_unpromoted()
    assert len(result) == 1
    assert result[0]["ebay_osp_id"] == 1


@pytest.mark.asyncio
async def test_mark_promoted_calls_command(repo):
    await repo.mark_promoted([1, 2, 3])
    repo.execute_command.assert_called_once()
    args = repo.execute_command.call_args[0][1]
    assert args[0] == [1, 2, 3]


@pytest.mark.asyncio
async def test_mark_promoted_skips_empty_list(repo):
    await repo.mark_promoted([])
    repo.execute_command.assert_not_called()


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
