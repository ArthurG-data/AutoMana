"""
Tests for src/automana/core/models/card_catalog/price_history.py

Units under test:
    - DateRange model
    - PriceHistoryResponse model
"""
import pytest
from automana.core.models.card_catalog.price_history import PriceHistoryResponse, DateRange

pytestmark = pytest.mark.unit


class TestDateRange:
    """Tests for DateRange model."""

    def test_date_range_creation_with_all_fields(self):
        """Test that DateRange can be created with all fields."""
        date_range = DateRange(
            start="2026-04-04",
            end="2026-05-04",
            days_back=30
        )
        assert date_range.start == "2026-04-04"
        assert date_range.end == "2026-05-04"
        assert date_range.days_back == 30

    def test_date_range_creation_without_days_back(self):
        """Test that DateRange can be created without days_back (None default)."""
        date_range = DateRange(
            start="2026-01-01",
            end="2026-05-04"
        )
        assert date_range.start == "2026-01-01"
        assert date_range.end == "2026-05-04"
        assert date_range.days_back is None

    def test_date_range_requires_start_and_end(self):
        """Test that start and end are required fields."""
        with pytest.raises(ValueError):
            DateRange(start="2026-04-04")

        with pytest.raises(ValueError):
            DateRange(end="2026-05-04")


class TestPriceHistoryResponse:
    """Tests for PriceHistoryResponse model."""

    def test_price_history_response_creation(self):
        """Test that PriceHistoryResponse can be created with price arrays."""
        response = PriceHistoryResponse(
            price_history_list_avg=[10.5, 10.75, 11.0],
            price_history_sold_avg=[9.8, 10.1, 10.3],
            date_range={
                "start": "2026-04-04",
                "end": "2026-05-04",
                "days_back": 30
            }
        )
        assert response.price_history_list_avg == [10.5, 10.75, 11.0]
        assert response.price_history_sold_avg == [9.8, 10.1, 10.3]
        assert response.date_range.start == "2026-04-04"
        assert response.date_range.end == "2026-05-04"
        assert response.date_range.days_back == 30

    def test_price_history_response_with_no_data(self):
        """Test that PriceHistoryResponse can be created with None for missing history."""
        response = PriceHistoryResponse(
            price_history_list_avg=None,
            price_history_sold_avg=None,
            date_range={
                "start": "2026-04-04",
                "end": "2026-05-04",
                "days_back": 30
            }
        )
        assert response.price_history_list_avg is None
        assert response.price_history_sold_avg is None

    def test_price_history_response_with_empty_arrays(self):
        """Test that PriceHistoryResponse accepts empty price arrays."""
        response = PriceHistoryResponse(
            price_history_list_avg=[],
            price_history_sold_avg=[],
            date_range={
                "start": "2026-05-04",
                "end": "2026-05-04",
                "days_back": 0
            }
        )
        assert response.price_history_list_avg == []
        assert response.price_history_sold_avg == []

    def test_price_history_response_with_date_range_object(self):
        """Test that PriceHistoryResponse accepts DateRange object directly."""
        date_range = DateRange(
            start="2026-04-04",
            end="2026-05-04",
            days_back=30
        )
        response = PriceHistoryResponse(
            price_history_list_avg=[10.5, 10.75, 11.0],
            price_history_sold_avg=[9.8, 10.1, 10.3],
            date_range=date_range
        )
        assert response.date_range.days_back == 30
