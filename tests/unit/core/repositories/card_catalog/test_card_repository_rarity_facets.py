"""Unit tests: card_repository.search() rarity_facets."""
import pytest
from unittest.mock import AsyncMock
from automana.core.repositories.card_catalog.card_repository import CardReferenceRepository

pytestmark = pytest.mark.unit

_CARD_ROW = {
    "card_version_id": "aaaaaaaa-0000-0000-0000-000000000000",
    "card_name": "Ragavan",
    "rarity_name": "mythic",
    "set_name": "Modern Horizons 2",
    "set_code": "mh2",
    "cmc": 1,
    "oracle_text": "...",
    "digital": False,
    "released_at": "2021-06-18",
    "image_normal": None,
}


def _make_repo(cards_rows, count_rows, promo_facet_rows, rarity_facet_rows):
    repo = CardReferenceRepository.__new__(CardReferenceRepository)
    # When cards_rows is non-empty, _fetch_prices_for_cards inserts an extra
    # execute_query call (Redis miss → DB lookup returning []). When empty,
    # the price lookup is short-circuited and that call is skipped.
    price_call = [[]] if cards_rows else []
    repo.execute_query = AsyncMock(
        side_effect=[cards_rows, *price_call, count_rows, promo_facet_rows, rarity_facet_rows]
    )
    return repo


@pytest.mark.asyncio
async def test_search_returns_rarity_facets():
    repo = _make_repo(
        [_CARD_ROW],
        [{"total_count": 1}],
        [{"promo_type_facets": []}],
        [{"rarity_facets": ["mythic", "rare"]}],
    )
    result = await repo.search()
    assert result["rarity_facets"] == ["mythic", "rare"]


@pytest.mark.asyncio
async def test_search_returns_empty_rarity_facets_when_none():
    repo = _make_repo(
        [],
        [{"total_count": 0}],
        [{"promo_type_facets": []}],
        [{"rarity_facets": None}],
    )
    result = await repo.search()
    assert result["rarity_facets"] == []


@pytest.mark.asyncio
async def test_rarity_facet_query_excludes_rarity_predicate():
    """When rarity is filtered, rarity facet query must NOT apply that predicate."""
    repo = _make_repo(
        [_CARD_ROW],
        [{"total_count": 1}],
        [{"promo_type_facets": []}],
        [{"rarity_facets": ["mythic"]}],
    )
    await repo.search(rarity="mythic")
    main_sql = repo.execute_query.call_args_list[0][0][0]
    rarity_facet_sql = repo.execute_query.call_args_list[4][0][0]
    assert "v.rarity_name ILIKE" in main_sql          # rarity predicate in main WHERE
    assert "v.rarity_name ILIKE" not in rarity_facet_sql  # rarity predicate absent from facet WHERE
