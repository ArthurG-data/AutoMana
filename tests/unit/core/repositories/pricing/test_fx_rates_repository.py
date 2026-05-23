import pytest
from unittest.mock import AsyncMock
from automana.core.repositories.pricing.fx_rates_repository import FxRatesRepository
from datetime import date


@pytest.fixture
def repo():
    conn = AsyncMock()
    return FxRatesRepository(conn)


@pytest.mark.asyncio
async def test_get_rates_for_date_returns_rows(repo):
    repo.execute_query = AsyncMock(return_value=[
        {"from_currency": "AUD", "rate": 0.645},
        {"from_currency": "CAD", "rate": 0.731},
    ])
    rows = await repo.get_rates_for_date(date(2026, 5, 23))
    repo.execute_query.assert_called_once()
    args = repo.execute_query.call_args[0]
    assert "$1" in args[0]
    assert args[1] == (date(2026, 5, 23),)
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_get_rates_for_date_empty_when_no_rates(repo):
    repo.execute_query = AsyncMock(return_value=[])
    rows = await repo.get_rates_for_date(date(2026, 5, 23))
    assert rows == []
