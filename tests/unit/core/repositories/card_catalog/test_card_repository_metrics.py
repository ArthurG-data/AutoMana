"""Tests for the metric-support read methods added to CardReferenceRepository.

These methods feed the card_catalog.* metric family — they are read-only and
return small scalar / dict shapes specifically for the registry runner.
"""
import pytest
from unittest.mock import AsyncMock

from automana.core.repositories.card_catalog.card_repository import (
    CardReferenceRepository,
)

pytestmark = pytest.mark.unit


def _make_repo(rows):
    """Build a CardReferenceRepository with a mocked execute_query that
    returns the provided rows on the next call."""
    repo = CardReferenceRepository.__new__(CardReferenceRepository)
    repo.execute_query = AsyncMock(return_value=rows)
    return repo


@pytest.mark.asyncio
async def test_fetch_identifier_coverage_pct_returns_pct_and_counts():
    repo = _make_repo([{"covered": 95, "total": 100, "pct": 95.0}])
    out = await repo.fetch_identifier_coverage_pct("scryfall_id")
    assert out == {"covered": 95, "total": 100, "pct": 95.0}
    repo.execute_query.assert_awaited_once()
    args = repo.execute_query.await_args.args
    assert args[1] == ("scryfall_id",)


@pytest.mark.asyncio
async def test_fetch_identifier_coverage_pct_zero_total_returns_none_pct():
    repo = _make_repo([{"covered": 0, "total": 0, "pct": None}])
    out = await repo.fetch_identifier_coverage_pct("scryfall_id")
    assert out == {"covered": 0, "total": 0, "pct": None}
    repo.execute_query.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_identifier_coverage_pct_no_rows_returns_none():
    repo = _make_repo([])
    out = await repo.fetch_identifier_coverage_pct("scryfall_id")
    assert out is None
    repo.execute_query.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_orphan_unique_cards_count_returns_int():
    repo = _make_repo([{"n": 7}])
    n = await repo.fetch_orphan_unique_cards_count()
    assert n == 7
    repo.execute_query.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_orphan_unique_cards_count_no_rows_returns_zero():
    repo = _make_repo([])
    assert await repo.fetch_orphan_unique_cards_count() == 0
    repo.execute_query.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_external_id_value_collisions_returns_int():
    repo = _make_repo([{"n": 0}])
    assert await repo.fetch_external_id_value_collisions() == 0
    repo.execute_query.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_external_id_value_collisions_no_rows_returns_zero():
    repo = _make_repo([])
    assert await repo.fetch_external_id_value_collisions() == 0
    repo.execute_query.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_identifier_coverage_pct_by_unique_card_returns_pct_and_counts():
    repo = _make_repo([{"covered": 37236, "total": 37236, "pct": 100.0}])
    out = await repo.fetch_identifier_coverage_pct_by_unique_card("oracle_id")
    assert out == {"covered": 37236, "total": 37236, "pct": 100.0}
    args = repo.execute_query.await_args.args
    assert args[1] == ("oracle_id",)


@pytest.mark.asyncio
async def test_fetch_identifier_coverage_pct_by_unique_card_no_rows_returns_none():
    repo = _make_repo([])
    out = await repo.fetch_identifier_coverage_pct_by_unique_card("oracle_id")
    assert out is None
