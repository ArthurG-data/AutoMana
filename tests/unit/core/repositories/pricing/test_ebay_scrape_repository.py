import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from automana.core.repositories.app_integration.ebay.ebay_scrape_repository import (
    EbayScrapeSoldRepository,
)


@pytest.fixture
def repo():
    conn = MagicMock()
    r = EbayScrapeSoldRepository(connection=conn, executor=None)
    r.execute_query = AsyncMock()
    r.execute_command = AsyncMock()
    return r


@pytest.mark.asyncio
async def test_insert_scraped_sold_calls_command(repo):
    now = datetime.now(timezone.utc)
    await repo.insert_scraped_sold(
        item_id="item-99",
        title="Lightning Bolt",
        source_product_id=10,
        price_cents=150,
        currency="USD",
        marketplace_id="EBAY-US",
        condition_id=2,
        finish_id=1,
        language_id=1,
        sold_at=now,
    )
    repo.execute_command.assert_called_once()
    args = repo.execute_command.call_args[0][1]
    assert args[0] == "item-99"
    assert args[3] == 150


@pytest.mark.asyncio
async def test_get_unpromoted_returns_dicts(repo):
    now = datetime.now(timezone.utc)
    repo.execute_query.return_value = [
        {
            "scrape_id": 5,
            "source_product_id": 10,
            "price_cents": 200,
            "sold_at": now,
            "finish_id": 1,
            "condition_id": 2,
            "language_id": 1,
        }
    ]
    result = await repo.get_unpromoted()
    assert len(result) == 1
    assert result[0]["scrape_id"] == 5


@pytest.mark.asyncio
async def test_get_unpromoted_empty(repo):
    repo.execute_query.return_value = []
    result = await repo.get_unpromoted()
    assert result == []


@pytest.mark.asyncio
async def test_mark_promoted_calls_command(repo):
    await repo.mark_promoted([5, 6, 7])
    repo.execute_command.assert_called_once()
    args = repo.execute_command.call_args[0][1]
    assert args[0] == [5, 6, 7]


@pytest.mark.asyncio
async def test_mark_promoted_skips_empty_list(repo):
    await repo.mark_promoted([])
    repo.execute_command.assert_not_called()
