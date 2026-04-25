"""
Tests for src/automana/core/metrics/mtgstock/staging_metrics.py

Metrics under test (5):
    mtgstock.raw_prints_loaded          — fetch_raw_prints_count
    mtgstock.raw_rows_loaded            — fetch_raw_rows_count
    mtgstock.cards_linked_to_card_version — fetch_linked_count
    mtgstock.cards_rejected             — fetch_rejected_count
    mtgstock.link_rate_pct              — computed ratio with denominator-zero guard

These metrics read current staging table state; they accept ingestion_run_id
but never use it (the staging tables have no run column). We ignore the param
in mock setup accordingly.
"""
import pytest
from unittest.mock import AsyncMock

from automana.core.metrics.mtgstock.staging_metrics import (
    cards_linked_to_card_version,
    cards_rejected,
    link_rate_pct,
    raw_prints_loaded,
    raw_rows_loaded,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# raw_prints_loaded
# ---------------------------------------------------------------------------

class TestRawPrintsLoaded:
    async def test_returns_count_from_repository(self):
        price_repo = AsyncMock()
        price_repo.fetch_raw_prints_count.return_value = 75000

        result = await raw_prints_loaded(price_repository=price_repo)

        price_repo.fetch_raw_prints_count.assert_awaited_once()
        assert result.row_count == 75000

    async def test_zero_count_returned_faithfully(self):
        price_repo = AsyncMock()
        price_repo.fetch_raw_prints_count.return_value = 0

        result = await raw_prints_loaded(price_repository=price_repo)

        assert result.row_count == 0


# ---------------------------------------------------------------------------
# raw_rows_loaded
# ---------------------------------------------------------------------------

class TestRawRowsLoaded:
    async def test_returns_count_from_repository(self):
        price_repo = AsyncMock()
        price_repo.fetch_raw_rows_count.return_value = 1_200_000

        result = await raw_rows_loaded(price_repository=price_repo)

        price_repo.fetch_raw_rows_count.assert_awaited_once()
        assert result.row_count == 1_200_000


# ---------------------------------------------------------------------------
# cards_linked_to_card_version
# ---------------------------------------------------------------------------

class TestCardsLinkedToCardVersion:
    async def test_returns_linked_count(self):
        price_repo = AsyncMock()
        price_repo.fetch_linked_count.return_value = 68000

        result = await cards_linked_to_card_version(price_repository=price_repo)

        price_repo.fetch_linked_count.assert_awaited_once()
        assert result.row_count == 68000


# ---------------------------------------------------------------------------
# cards_rejected
# ---------------------------------------------------------------------------

class TestCardsRejected:
    async def test_returns_rejected_count(self):
        price_repo = AsyncMock()
        price_repo.fetch_rejected_count.return_value = 250

        result = await cards_rejected(price_repository=price_repo)

        price_repo.fetch_rejected_count.assert_awaited_once()
        assert result.row_count == 250

    async def test_zero_rejections_returned_faithfully(self):
        price_repo = AsyncMock()
        price_repo.fetch_rejected_count.return_value = 0

        result = await cards_rejected(price_repository=price_repo)

        assert result.row_count == 0


# ---------------------------------------------------------------------------
# link_rate_pct — the most interesting staging metric
# ---------------------------------------------------------------------------

class TestLinkRatePct:
    async def test_happy_path_computes_correct_percentage(self):
        price_repo = AsyncMock()
        price_repo.fetch_linked_count.return_value = 950
        price_repo.fetch_rejected_count.return_value = 50

        result = await link_rate_pct(price_repository=price_repo)

        # 950 / 1000 = 95.0 %
        assert result.row_count == 95.0
        assert result.details["linked"] == 950
        assert result.details["rejected"] == 50
        assert result.details["denominator"] == 1000

    async def test_perfect_link_rate(self):
        price_repo = AsyncMock()
        price_repo.fetch_linked_count.return_value = 10000
        price_repo.fetch_rejected_count.return_value = 0

        result = await link_rate_pct(price_repository=price_repo)

        assert result.row_count == 100.0

    async def test_denominator_zero_returns_none_not_division_error(self):
        """Both linked and rejected are 0 (staging table is empty).
        Must return None rather than raise ZeroDivisionError."""
        price_repo = AsyncMock()
        price_repo.fetch_linked_count.return_value = 0
        price_repo.fetch_rejected_count.return_value = 0

        result = await link_rate_pct(price_repository=price_repo)

        assert result.row_count is None
        assert result.details["denominator"] == 0

    async def test_details_include_both_counts(self):
        price_repo = AsyncMock()
        price_repo.fetch_linked_count.return_value = 800
        price_repo.fetch_rejected_count.return_value = 200

        result = await link_rate_pct(price_repository=price_repo)

        assert result.details["linked"] == 800
        assert result.details["rejected"] == 200

    async def test_result_is_rounded_to_two_decimal_places(self):
        price_repo = AsyncMock()
        # 1 / 3 = 33.333...% — must be rounded
        price_repo.fetch_linked_count.return_value = 1
        price_repo.fetch_rejected_count.return_value = 2

        result = await link_rate_pct(price_repository=price_repo)

        assert result.row_count == round(100.0 / 3, 2)
