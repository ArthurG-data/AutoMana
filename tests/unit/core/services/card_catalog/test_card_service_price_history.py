"""
Unit tests for card_catalog.card.get_price_history.

Scope:
  - All behavioral paths through the service function (happy path with days_back,
    happy path with days_back=None for all-time, empty result, repo-level DB error).
  - ServiceRegistry invariants (registration, db_repositories).

Not in scope:
  - Repository SQL correctness — that belongs in the integration suite.
  - Date arithmetic edge cases (handled by repository).
"""
from unittest.mock import AsyncMock
from uuid import UUID
from datetime import date, timedelta

import pytest

# Importing the module causes @ServiceRegistry.register to execute, which is
# required for the invariant assertions below.
import automana.core.services.card_catalog.card_service as card_service
from automana.core.repositories.card_catalog.card_repository import CardReferenceRepository
from automana.core.models.card_catalog.price_history import PriceHistoryResponse, DateRange
from automana.core.exceptions.service_layer_exceptions.card_catalogue.card_exception import (
    CardRetrievalError,
)
from automana.core.service_registry import ServiceRegistry

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

_CARD_VERSION_ID = UUID("12345678-1234-5678-1234-567812345678")


def _make_repo(*, list_avg=None, sold_avg=None, dates=None) -> AsyncMock:
    """Return a mocked CardReferenceRepository pre-configured with the given response."""
    repo = AsyncMock(spec=CardReferenceRepository)
    repo.get_price_history.return_value = {
        "list_avg": list_avg or [],
        "sold_avg": sold_avg or [],
        "dates": dates or []
    }
    return repo


# ---------------------------------------------------------------------------
# Behavioral tests
# ---------------------------------------------------------------------------

class TestGetCardPriceHistoryHappyPaths:
    @pytest.mark.asyncio
    async def test_get_card_price_history_1m_default(self):
        """Test that get_card_price_history() defaults to 30 days and returns PriceHistoryResponse."""
        list_prices = [10.50, 10.75, 11.00]
        sold_prices = [9.80, 10.10, 10.30]
        price_dates = [
            date.today() - timedelta(days=30),
            date.today() - timedelta(days=29),
            date.today(),
        ]

        repo = _make_repo(
            list_avg=list_prices,
            sold_avg=sold_prices,
            dates=price_dates
        )

        result = await card_service.get_card_price_history(
            card_repository=repo,
            card_id=_CARD_VERSION_ID,
            days_back=30
        )

        assert isinstance(result, PriceHistoryResponse)
        assert result.price_history_list_avg == list_prices
        assert result.price_history_sold_avg == sold_prices
        assert result.date_range.days_back == 30
        assert result.date_range.start == price_dates[0]
        assert result.date_range.end == price_dates[-1]

        # Verify repo was called with correct date range
        repo.get_price_history.assert_awaited_once()
        call_args = repo.get_price_history.call_args
        assert call_args[0][0] == _CARD_VERSION_ID

    @pytest.mark.asyncio
    async def test_get_card_price_history_all_time(self):
        """Test that get_card_price_history() handles days_back=None for all time."""
        list_prices = [5.0, 6.0, 10.5]
        sold_prices = [4.5, 5.5, 9.8]
        price_dates = [date(2024, 1, 1), date(2025, 1, 1), date.today()]

        repo = _make_repo(
            list_avg=list_prices,
            sold_avg=sold_prices,
            dates=price_dates
        )

        result = await card_service.get_card_price_history(
            card_repository=repo,
            card_id=_CARD_VERSION_ID,
            days_back=None
        )

        assert isinstance(result, PriceHistoryResponse)
        assert result.date_range.days_back is None
        assert len(result.price_history_list_avg) == 3
        assert result.price_history_list_avg == list_prices
        assert result.price_history_sold_avg == sold_prices

    @pytest.mark.asyncio
    async def test_get_card_price_history_empty_result(self):
        """Test that get_card_price_history() handles empty result gracefully."""
        repo = _make_repo(
            list_avg=[],
            sold_avg=[],
            dates=[]
        )

        result = await card_service.get_card_price_history(
            card_repository=repo,
            card_id=_CARD_VERSION_ID,
            days_back=30
        )

        assert isinstance(result, PriceHistoryResponse)
        assert result.price_history_list_avg == []
        assert result.price_history_sold_avg == []


class TestGetCardPriceHistoryFailurePaths:
    @pytest.mark.asyncio
    async def test_db_error_wrapped_in_card_retrieval_error(self):
        """A repo-side exception must be translated to CardRetrievalError."""
        repo = AsyncMock(spec=CardReferenceRepository)
        repo.get_price_history.side_effect = Exception("DB connection failed")

        with pytest.raises(CardRetrievalError) as exc_info:
            await card_service.get_card_price_history(
                card_repository=repo,
                card_id=_CARD_VERSION_ID,
                days_back=30
            )

        error_msg = str(exc_info.value)
        assert "DB connection failed" in error_msg


# ---------------------------------------------------------------------------
# ServiceRegistry invariants
# ---------------------------------------------------------------------------

class TestServiceRegistryInvariants:
    def test_service_registration(self):
        """Verify the service is registered with correct db_repositories."""
        cfg = ServiceRegistry.get("card_catalog.card.get_price_history")
        assert cfg is not None
        assert cfg.db_repositories == ["card"]
