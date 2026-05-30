import pytest
from unittest.mock import AsyncMock


def _make_repo():
    from automana.core.repositories.app_integration.mtg_stock.priority_repository import (
        MtgstockPriorityRepository,
    )
    repo = MtgstockPriorityRepository.__new__(MtgstockPriorityRepository)
    repo.execute_query = AsyncMock()
    return repo


@pytest.mark.asyncio
async def test_fetch_tier_print_ids_returns_sorted_ints():
    repo = _make_repo()
    repo.execute_query.return_value = [{"print_id": 30}, {"print_id": 10}, {"print_id": 20}]
    result = await repo.fetch_tier_print_ids(1)
    assert result == [10, 20, 30]


@pytest.mark.asyncio
async def test_fetch_tier_print_ids_uses_tier1_predicate():
    repo = _make_repo()
    repo.execute_query.return_value = []
    await repo.fetch_tier_print_ids(1)
    sql = repo.execute_query.call_args[0][0]
    assert "120 days" in sql
    assert "500" in sql


@pytest.mark.asyncio
async def test_fetch_tier_print_ids_tier2_predicate():
    repo = _make_repo()
    repo.execute_query.return_value = []
    await repo.fetch_tier_print_ids(2)
    sql = repo.execute_query.call_args[0][0]
    assert "100" in sql


@pytest.mark.asyncio
async def test_fetch_tier_print_ids_rejects_unknown_tier():
    repo = _make_repo()
    with pytest.raises(ValueError):
        await repo.fetch_tier_print_ids(99)
