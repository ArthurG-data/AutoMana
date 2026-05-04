import pytest
from datetime import date, timedelta
from uuid import UUID
from unittest.mock import AsyncMock, MagicMock
from automana.core.repositories.card_catalog.card_repository import CardReferenceRepository

@pytest.fixture
def mock_pool():
    """Mock asyncpg connection pool."""
    pool = AsyncMock()
    return pool

pytestmark = pytest.mark.unit


def _make_repo(rows):
    """Build a CardReferenceRepository with a mocked execute_query that
    returns the provided rows on the next call."""
    repo = CardReferenceRepository.__new__(CardReferenceRepository)
    repo.execute_query = AsyncMock(return_value=rows)
    return repo


@pytest.mark.asyncio
async def test_get_price_history_returns_arrays():
    """Test that get_price_history() returns price arrays aggregated by date."""
    card_id = UUID("12345678-1234-5678-1234-567812345678")
    start_date = date(2026, 4, 4)
    end_date = date(2026, 5, 4)

    # Mock database response with asyncpg Record-like objects
    # Each "row" has ts_date, list_avg_price, sold_avg_price
    mock_rows = [
        {"ts_date": start_date, "list_avg_price": 10.50, "sold_avg_price": 9.80},
        {"ts_date": start_date + timedelta(days=1), "list_avg_price": 10.75, "sold_avg_price": 10.10},
        {"ts_date": start_date + timedelta(days=2), "list_avg_price": 11.00, "sold_avg_price": 10.30},
    ]

    repository = _make_repo(mock_rows)

    result = await repository.get_price_history(card_id, start_date, end_date)

    assert result["list_avg"] == [10.50, 10.75, 11.00]
    assert result["sold_avg"] == [9.80, 10.10, 10.30]
    assert len(result["dates"]) == 3


@pytest.mark.asyncio
async def test_get_price_history_with_missing_dates():
    """Test that get_price_history() null-fills missing dates.

    The database query uses generate_series to create a complete date range,
    so rows with NULL values for missing data are returned by the query.
    """
    card_id = UUID("12345678-1234-5678-1234-567812345678")
    start_date = date(2026, 4, 4)
    end_date = date(2026, 4, 6)

    # Mock response: database returns all 3 dates, with NULL for missing April 5
    mock_rows = [
        {"ts_date": start_date, "list_avg_price": 10.50, "sold_avg_price": 9.80},
        {"ts_date": start_date + timedelta(days=1), "list_avg_price": None, "sold_avg_price": None},
        {"ts_date": start_date + timedelta(days=2), "list_avg_price": 11.00, "sold_avg_price": 10.30},
    ]

    repository = _make_repo(mock_rows)

    result = await repository.get_price_history(card_id, start_date, end_date)

    # Should have 3 entries (database fills missing April 5 with null)
    assert len(result["list_avg"]) == 3
    assert result["list_avg"] == [10.50, None, 11.00]
    assert result["sold_avg"] == [9.80, None, 10.30]


@pytest.mark.asyncio
async def test_get_price_history_empty_result():
    """Test that get_price_history() returns empty lists for cards with no history."""
    card_id = UUID("12345678-1234-5678-1234-567812345678")
    start_date = date(2026, 4, 4)
    end_date = date(2026, 5, 4)

    repository = _make_repo([])

    result = await repository.get_price_history(card_id, start_date, end_date)

    assert result["list_avg"] == []
    assert result["sold_avg"] == []
    assert result["dates"] == []
